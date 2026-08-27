# -*- coding: utf-8 -*-
"""A chave de acesso (passkey): conferir o que o navegador entrega.

O MAL-ENTENDIDO QUE ESTE ARQUIVO DESFAZ, e ele esta escrito aqui porque quem
mexer neste codigo daqui a um ano vai ter a mesma duvida: **passkey nao e
digital.** Digital e rosto sao so a maneira de DESTRANCAR a chave dentro do
aparelho. Num PC sem camera e sem leitor — que e exatamente o caso do dono —
quem destranca e o PIN do Windows Hello, e a chave mora no chip TPM da placa.
Sem TPM, o navegador mostra um QR, o celular confirma com a digital, e a chave
mora no celular. As tres situacoes chegam aqui identicas.

O QUE CHEGA, e o que cada peca vale:

  clientDataJSON      o que o NAVEGADOR afirma que aconteceu — para qual site,
                      qual desafio, que tipo de operacao. Nao e assinado por
                      ele; vale porque a assinatura do chip cobre o resumo dele.
  authenticatorData   o que o CHIP afirma — para qual dominio, se a pessoa
                      estava presente, se foi verificada, e o contador.
  assinatura          o que amarra os dois. Sem ela os outros dois sao texto
                      que qualquer um digita.

E POR QUE ISTO E IMUNE A SITE FALSO. A chave privada nunca sai do aparelho, e o
navegador so a oferece para o endereco em que ela foi cadastrada. Num site com
endereco parecido o navegador simplesmente nao encontra chave nenhuma para
oferecer — nao ha o que a pessoa possa digitar errado, porque nao ha nada a
digitar. E a unica forma de login em uso que resolve phishing por construcao, e
nao por atencao de quem usa.

O QUE NAO CONFERIMOS, DE PROPOSITO: o atestado (`attStmt`) do fabricante do
chip. Ele serve para uma empresa exigir "so chave da marca X"; aqui sao duas
pessoas e qualquer aparelho serve. Aceitar `fmt: none` e a escolha certa para
este caso, e escrever isto e melhor que deixar quem ler achar que foi esquecido.

FALHA FECHADA em toda funcao: qualquer desvio devolve None ou False, e nenhuma
levanta excecao para quem chamou. Motivo da recusa nao volta para quem pediu —
"esta credencial nao existe" ja e um oraculo sobre quem existe.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading

import p256

# Tetos. Todos existem pelo mesmo motivo: sao a fronteira com dado de fora, e
# dado de fora e hostil ate prova em contrario.
TETO_DO_CORPO = 16 * 1024      # o attestationObject de um autenticador real: ~1 KiB
TETO_DO_B64 = 32 * 1024
TETO_DO_CRED_ID = 1023         # o teto da propria norma
PROFUNDIDADE = 16              # aninhamento maximo de CBOR
DESAFIO_MINIMO = 16            # bytes; a norma pede 16, nos geramos 32
TAMANHO_DO_DESAFIO = 32

# Os bits de `flags` no bloco do autenticador.
UP = 0x01    # user present   — alguem tocou o aparelho
UV = 0x04    # user verified  — PIN, digital ou rosto conferido no aparelho
AT = 0x40    # attested data  — o bloco traz uma chave publica nova
ED = 0x80    # extension data — extensoes, que nao usamos mas temos de pular

_B64URL = re.compile(r"^[A-Za-z0-9_-]+={0,2}$")


# ------------------------------------------------------------ base64 da web

def b64url(cru: bytes) -> str:
    """Sem o `=` do fim: e o que o navegador manda e o que ele espera de volta."""
    return base64.urlsafe_b64encode(cru).decode("ascii").rstrip("=")


def de_b64url(texto):
    """Devolve os bytes, ou None. Aceita com ou sem `=`; nunca levanta."""
    if not isinstance(texto, str):
        return None
    texto = texto.strip()
    if not texto or len(texto) > TETO_DO_B64 or not _B64URL.match(texto):
        return None
    sem = texto.rstrip("=")
    if len(sem) % 4 == 1:
        # Um bloco de base64 tem 2, 3 ou 4 caracteres uteis — nunca 1. Sobra de
        # 1 e comprimento impossivel, e `b64decode` aceitaria calado
        # descartando bits. (A primeira versao desta linha testava o resto
        # errado e recusava "AQI=", que e legitimo. Pego pelo teste.)
        return None
    try:
        return base64.urlsafe_b64decode(sem + "=" * ((-len(sem)) % 4))
    except (ValueError, TypeError):
        return None


def novo_desafio() -> bytes:
    """O numero de uso unico que a resposta tem de citar.

    E o que impede repetir uma resposta capturada: sem ele, a mesma assinatura
    de ontem entra hoje. Sorteado, nunca contado — contador seria previsivel.
    """
    return secrets.token_bytes(TAMANHO_DO_DESAFIO)


# ------------------------------------------------------------------- CBOR
#
# O attestationObject vem em CBOR, e este e um leitor MINIMO de proposito:
# so os cinco tipos que o WebAuthn usa. Tudo que nao esta na lista — float,
# tag, comprimento indefinido, nulo, booleano solto — e RECUSADO em vez de
# ignorado. Formato de embrulho que aceita o que nao entende vira caminho para
# duas pontas lerem coisas diferentes do mesmo byte.

def cbor_ler(dados, _fundo: int = 0):
    """Devolve (valor, o que sobrou). (None, b"") em qualquer problema."""
    if not isinstance(dados, (bytes, bytearray)) or not dados:
        return None, b""
    if _fundo > PROFUNDIDADE:
        # Sem teto, uma lista dentro de lista 10 mil vezes estoura a pilha do
        # Python e derruba a linha de execucao que atende o pedido.
        return None, b""
    dados = bytes(dados)
    maior, curto = dados[0] >> 5, dados[0] & 0x1F
    resto = dados[1:]

    if curto < 24:
        n = curto
    elif curto in (24, 25, 26, 27):
        quantos = 1 << (curto - 24)
        if len(resto) < quantos:
            return None, b""
        n, resto = int.from_bytes(resto[:quantos], "big"), resto[quantos:]
    else:
        # 28-30 nao existem; 31 e comprimento indefinido, que o WebAuthn nao usa.
        return None, b""

    if maior == 0:                                   # inteiro positivo
        return n, resto
    if maior == 1:                                   # inteiro negativo
        return -1 - n, resto
    if maior in (2, 3):                              # bytes / texto
        if n > len(resto):
            # A checagem que impede um cabecalho dizendo "tenho 1 GiB".
            return None, b""
        pedaco, resto = resto[:n], resto[n:]
        if maior == 2:
            return pedaco, resto
        try:
            return pedaco.decode("utf-8"), resto
        except UnicodeDecodeError:
            return None, b""
    if maior == 4:                                   # lista
        if n > len(resto):
            return None, b""
        itens = []
        for _ in range(n):
            item, resto = cbor_ler(resto, _fundo + 1)
            if item is None:
                return None, b""
            itens.append(item)
        return itens, resto
    if maior == 5:                                   # mapa
        if n > len(resto):
            return None, b""
        mapa = {}
        for _ in range(n):
            chave, resto = cbor_ler(resto, _fundo + 1)
            if chave is None or not isinstance(chave, (int, str)):
                return None, b""
            if chave in mapa:
                # Chave repetida deixa dois leitores lerem valores diferentes
                # do MESMO documento — um pega o primeiro, outro o ultimo.
                return None, b""
            valor, resto = cbor_ler(resto, _fundo + 1)
            if valor is None:
                return None, b""
            mapa[chave] = valor
        return mapa, resto
    # maior 6 (tag) e 7 (float, booleano, nulo): fora do que o WebAuthn usa.
    return None, b""


def cbor_completo(dados):
    """Le UM valor e exige que nao sobre byte nenhum depois dele."""
    valor, resto = cbor_ler(dados)
    return valor if not resto else None


# ---------------------------------------------------------- a chave COSE
#
# Os numeros abaixo sao rotulos do COSE, nao invencao: 1 = tipo de chave,
# 3 = algoritmo, -1 = curva, -2 = X, -3 = Y. Chave de mapa negativa e como o
# COSE separa o que vale para toda chave do que e especifico daquele tipo.

COSE_TIPO, COSE_ALG, COSE_CURVA, COSE_X, COSE_Y = 1, 3, -1, -2, -3
TIPO_EC2 = 2      # chave de curva eliptica
ALG_ES256 = -7    # ECDSA com P-256 e SHA-256
CURVA_P256 = 1


def chave_de_cose(cose):
    """Extrai (x, y) da chave publica. None se nao for exatamente ES256/P-256.

    Recusar outro algoritmo e o ponto: aceitar RS256 calado e prometer uma
    conferencia que este servidor nao sabe fazer.
    """
    if not isinstance(cose, dict):
        return None
    if cose.get(COSE_TIPO) != TIPO_EC2:
        return None
    if cose.get(COSE_ALG) != ALG_ES256:
        return None
    if cose.get(COSE_CURVA) != CURVA_P256:
        return None
    x, y = cose.get(COSE_X), cose.get(COSE_Y)
    if not isinstance(x, bytes) or not isinstance(y, bytes):
        return None
    if len(x) != p256.TAMANHO or len(y) != p256.TAMANHO:
        return None
    # Passa por `ponto_de_bytes` para herdar a checagem de curva de la — a
    # defesa contra chave forjada que cai numa curva vizinha.
    return p256.ponto_de_bytes(b"\x04" + x + y)


# --------------------------------------------------- os dados do autenticador
#
# O bloco tem forma fixa e conhecida:
#   32 bytes  resumo do dominio (rpIdHash)
#    1 byte   flags
#    4 bytes  contador de assinaturas
#   e, so quando a flag AT esta ligada:
#   16 bytes  aaguid (o modelo do autenticador; nao usamos)
#    2 bytes  tamanho do id da credencial
#    N bytes  o id da credencial
#    resto    a chave publica em COSE

MINIMO = 32 + 1 + 4


def dados_do_autenticador(cru):
    """Abre o bloco. None se a forma nao bater EXATAMENTE."""
    if not isinstance(cru, (bytes, bytearray)) or len(cru) < MINIMO:
        return None
    cru = bytes(cru)
    flags = cru[32]
    lido = {"rp_id_hash": cru[:32], "flags": flags,
            "presente": bool(flags & UP), "verificado": bool(flags & UV),
            "contador": int.from_bytes(cru[33:37], "big"),
            "cred_id": None, "cose": None}
    resto = cru[MINIMO:]

    if flags & AT:
        if len(resto) < 18:
            return None
        tamanho = int.from_bytes(resto[16:18], "big")
        resto = resto[18:]
        if tamanho == 0 or tamanho > TETO_DO_CRED_ID or tamanho > len(resto):
            return None
        lido["cred_id"], resto = resto[:tamanho], resto[tamanho:]
        cose, resto = cbor_ler(resto)
        if cose is None:
            return None
        lido["cose"] = cose

    if flags & ED:
        # Extensoes: nao usamos nenhuma, mas o bloco pode traze-las e a
        # assinatura as cobre. Le-se para conferir que o bloco termina certo.
        extensoes, resto = cbor_ler(resto)
        if extensoes is None:
            return None

    if resto:
        # Sobra e o vetor classico: um segundo bloco escondido atras do
        # primeiro, para que dois leitores discordem sobre onde termina o dado.
        return None
    return lido


# ------------------------------------------------- o que o navegador afirma

def _client_data(cru, tipo_esperado, desafio, origens_ok):
    """Confere o clientDataJSON. Devolve o objeto lido, ou None."""
    if not isinstance(cru, (bytes, bytearray)) or not cru:
        return None
    if len(cru) > TETO_DO_CORPO:
        return None
    try:
        corpo = json.loads(bytes(cru).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(corpo, dict):
        return None
    if corpo.get("type") != tipo_esperado:
        # `webauthn.create` reaproveitado como `webauthn.get` (ou o contrario)
        # e troca de contexto: uma resposta de cadastro virando login.
        return None
    esperado = b64url(desafio)
    visto = corpo.get("challenge")
    if not isinstance(visto, str) or not hmac.compare_digest(visto, esperado):
        return None
    if corpo.get("origin") not in origens_ok:
        # A amarra ao endereco. Num site falso o navegador nem oferece a chave,
        # mas conferir aqui e a camada que nao depende do navegador se comportar.
        return None
    if corpo.get("crossOrigin"):
        # Login dentro de um iframe de outro site nao e login do dono.
        return None
    return corpo


def _bloco_ok(lido, rp_id, exigir_verificacao):
    if lido is None:
        return False
    if not hmac.compare_digest(lido["rp_id_hash"],
                               hashlib.sha256(rp_id.encode("utf-8")).digest()):
        return False
    if not lido["presente"]:
        # Sem presenca, um site consegue disparar o login sem ninguem tocar em
        # nada — que e o mesmo que nao ter login.
        return False
    if exigir_verificacao and not lido["verificado"]:
        return False
    return True


# ------------------------------------------------------------- o cadastro

def conferir_cadastro(client_data_json, attestation_object, desafio, rp_id,
                      origens_ok, exigir_verificacao=True):
    """Uma chave de acesso NOVA. Devolve o que gravar, ou None.

    Devolve `{"cred_id", "chave", "contador", "fmt"}`. `chave` e o par (x, y)
    da chave PUBLICA — e ela nao abre nada: serve so para conferir assinatura.
    Vazar a tabela inteira nao entrega a conta de ninguem, e essa e a diferenca
    entre isto e guardar senha.
    """
    if not isinstance(desafio, (bytes, bytearray)) or len(desafio) < DESAFIO_MINIMO:
        # Desafio curto e adivinhavel, e desafio adivinhavel nao impede repetir
        # uma resposta capturada.
        return None
    if not isinstance(attestation_object, (bytes, bytearray)):
        return None
    if len(attestation_object) > TETO_DO_CORPO:
        return None
    if _client_data(client_data_json, "webauthn.create", desafio,
                    origens_ok) is None:
        return None
    atestado = cbor_completo(attestation_object)
    if not isinstance(atestado, dict):
        return None
    lido = dados_do_autenticador(atestado.get("authData"))
    if not _bloco_ok(lido, rp_id, exigir_verificacao):
        return None
    if lido["cred_id"] is None:
        # Cadastro sem chave nova nao e cadastro.
        return None
    chave = chave_de_cose(lido["cose"])
    if chave is None:
        return None
    fmt = atestado.get("fmt")
    return {"cred_id": lido["cred_id"], "chave": chave,
            "contador": lido["contador"],
            "fmt": fmt if isinstance(fmt, str) else ""}


# --------------------------------------------------------------- a entrada

def conferir_entrada(client_data_json, authenticator_data, assinatura, chave,
                     desafio, rp_id, origens_ok, exigir_verificacao=True):
    """Uma tentativa de ENTRAR com chave ja cadastrada. Devolve dict ou None.

    O que o chip assinou e a concatenacao `authenticatorData || sha256(
    clientDataJSON)` — e por isso mexer em um bit de qualquer um dos dois
    invalida a assinatura. Nao ha campo "de fora" da assinatura.
    """
    if not isinstance(desafio, (bytes, bytearray)) or len(desafio) < DESAFIO_MINIMO:
        return None
    if not isinstance(authenticator_data, (bytes, bytearray)):
        return None
    if len(authenticator_data) > TETO_DO_CORPO:
        return None
    if not isinstance(client_data_json, (bytes, bytearray)):
        return None
    if _client_data(client_data_json, "webauthn.get", desafio,
                    origens_ok) is None:
        return None
    lido = dados_do_autenticador(authenticator_data)
    if not _bloco_ok(lido, rp_id, exigir_verificacao):
        return None
    assinado = bytes(authenticator_data) + hashlib.sha256(
        bytes(client_data_json)).digest()
    if not p256.conferir_bytes(chave, assinado, assinatura):
        return None
    return {"contador": lido["contador"]}


# ------------------------------------------------- onde o desafio fica guardado
#
# POR QUE NAO NUM COOKIE ASSINADO, que e como a cortina guarda o selo dela: o
# selo da cortina PODE ser reapresentado dentro do prazo — e um passe de dez
# minutos. O desafio nao pode ser reapresentado NUNCA, e uso unico de verdade
# exige alguem lembrando o que ja foi gasto. Cookie assinado nao esquece.
#
# EM MEMORIA, e reiniciar o servidor esquece tudo. E aceitavel: o pior efeito e
# quem estava no meio do login apertar o botao de novo. Persistir daria a quem
# chega de fora um jeito de encher o disco de outra pessoa, uma linha por
# pedido — o mesmo raciocinio do contador da cortina.

PRAZO_DO_DESAFIO = 300      # segundos; login e ida ao PIN cabem folgados
TETO_DE_DESAFIOS = 500      # sem teto, pedir desafio em laco enche a memoria


class Desafios:
    """Os desafios abertos. Uso unico: resgatar APAGA."""

    def __init__(self, prazo: int = PRAZO_DO_DESAFIO,
                 teto: int = TETO_DE_DESAFIOS):
        self._prazo, self._teto = prazo, teto
        self._abertos = {}
        # O servidor e `ThreadingHTTPServer`: dois logins simultaneos mexeriam
        # neste dicionario ao mesmo tempo.
        self._trava = threading.Lock()

    def abrir(self, agora_s: float):
        """Devolve (senha_do_bilhete, desafio). O bilhete vai num cookie."""
        with self._trava:
            self._podar(agora_s)
            if len(self._abertos) >= self._teto:
                # Cheio: o mais velho sai. Recusar em vez disso deixaria quem
                # enche a memoria trancar o login de todo mundo.
                self._abertos.pop(next(iter(self._abertos)), None)
            bilhete = secrets.token_urlsafe(18)
            desafio = novo_desafio()
            self._abertos[bilhete] = (desafio, agora_s + self._prazo)
            return bilhete, desafio

    def resgatar(self, bilhete, agora_s: float):
        """O desafio daquele bilhete, UMA vez. None se nao existe ou venceu."""
        if not isinstance(bilhete, str) or not bilhete:
            return None
        with self._trava:
            self._podar(agora_s)
            # `pop`, e nao `get`: e o pop que faz o uso ser unico. Com `get`, a
            # mesma resposta capturada entraria de novo dentro do prazo.
            achado = self._abertos.pop(bilhete, None)
        if achado is None:
            return None
        desafio, ate = achado
        return desafio if agora_s <= ate else None

    def quantos(self) -> int:
        with self._trava:
            return len(self._abertos)

    def esquecer_tudo(self) -> None:
        with self._trava:
            self._abertos.clear()

    def _podar(self, agora_s: float) -> None:
        for bilhete in [b for b, (_, ate) in self._abertos.items()
                        if agora_s > ate]:
            del self._abertos[bilhete]


def contador_ok(guardado: int, novo: int) -> bool:
    """O contador andou para a frente?

    Todo autenticador que conta soma 1 a cada uso. Se o servidor ve um numero
    IGUAL ou MENOR que o ultimo, ha duas copias da mesma chave no mundo — e uma
    passkey copiada e a unica falha que a criptografia daqui nao pega sozinha.

    A excecao esta na propria norma: quem nao implementa contador manda zero
    para sempre, e ai nao ha o que comparar. Note a assimetria de proposito —
    zero-para-sempre passa, mas quem JA contou e volta a zero e regressao, nao
    "parou de contar".
    """
    if guardado == 0 and novo == 0:
        return True
    return novo > guardado
