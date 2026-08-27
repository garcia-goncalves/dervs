# -*- coding: utf-8 -*-
"""Trocar a chave privada de um GitHub App por um token de instalacao.

O QUE ISTO RESOLVE. Um GitHub App nao entrega um token pronto. Ele entrega uma
chave privada, e com ela o sistema PEDE um token — que vale uma hora e precisa
ser pedido de novo. O pedido e um JWT assinado em RS256: RSA com resumo SHA-256
no esquema de preenchimento PKCS#1 v1.5.

POR QUE ESCRITO A MAO. O Python nao traz RSA na biblioteca padrao e o projeto
nao adota dependencia externa — decisao antiga, registrada em `banco.py`. A
mesma escolha ja foi feita em `p256.py`. A diferenca importante: la o codigo
CONFERE assinatura, aqui ele PRODUZ, e produzir mexe com a chave secreta. Duas
consequencias, ditas de frente:

1. `pow(m, d, n)` do Python nao e de tempo constante. Isso importaria se um
   estranho pudesse cronometrar milhares de assinaturas nossas. Nao pode: quem
   assina e um processo local, o resultado vai para o GitHub e para mais
   ninguem, e sao ~24 assinaturas por dia. Nao ha oraculo para medir.
2. A chave nunca e impressa, nem gravada, nem entra em mensagem de erro. Toda
   mensagem que sai daqui e escrita por nos, nunca repassada da excecao.

FALHA FECHADA em toda porta: qualquer coisa fora do esperado devolve `None`,
nunca uma excecao para quem chamou tratar. `except` esquecido em caminho de
autenticacao vira porta aberta — e aqui a falha correta e "o painel fica sem os
numeros do GitHub", nunca "o painel cai".

Os valores publicos deste app (App ID, Installation ID) e o roteiro de como ele
foi criado estao em `docs/operacao/token-do-coletor.md`.
"""
from __future__ import annotations

import base64
import calendar
import hashlib
import json
import re
import sys
import time
import urllib.request
from typing import NamedTuple

API = "https://api.github.com/app/installations/%s/access_tokens"
AGENTE = "dervs-coletor"

# Teto do JWT no GitHub e 10 min. 9 deixa folga para o relogio dos dois lados
# andar diferente, sem chegar perto da recusa.
VIDA_DO_JWT = 540
# E o relogio pode ADIANTAR: um JWT emitido "no futuro" e recusado. Um minuto
# para tras custa nada e cobre o desvio comum de um servidor sem NTP em dia.
FOLGA_PARA_TRAS = 60
# Renovar o token no minuto do vencimento perde a corrida com a rede. Cinco
# minutos garantem que uma coleta demorada nao termine com token vencido.
MARGEM_DE_RENOVACAO = 300
# Sem isto, um arquivo trocado por engano vira um inteiro gigante e a conta
# trava em vez de recusar. Uma chave de 8192 bits cabe folgada aqui.
TETO_DO_ARQUIVO = 20000
MENOR_MODULO, MAIOR_MODULO = 1024, 8192

# O DigestInfo de SHA-256, em DER, como manda o RFC 8017 (PKCS#1 v2.2). E uma
# constante publicada, nao um numero nosso: descreve "o que vem depois e um
# resumo SHA-256 de 32 bytes".
DIGESTINFO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")

SO_DIGITOS = re.compile(r"[0-9]{1,20}")


class Chave(NamedTuple):
    """Os tres numeros que a assinatura usa. `e` so serve para conferencia."""
    n: int
    e: int
    d: int


def _diga(motivo: str) -> None:
    """Fala na saida de erro, se houver uma. Sob pythonw nao ha, e tudo bem.

    Saida de erro e nao saida normal porque e dali que o `servir.py` tira o
    motivo quando a coleta falha.
    """
    if sys.stderr is not None:
        print("github_app: %s" % motivo, file=sys.stderr)


# ---------------------------------------------------------------- ler o DER
#
# Um leitor minimo de DER, so o que um arquivo de chave RSA usa: SEQUENCE,
# INTEGER e OCTET STRING. Nao e um decodificador de ASN.1 de uso geral, e nao
# deve virar um: cada tipo a mais e superficie a mais lendo arquivo de fora.


def _tlv(cru: bytes, i: int):
    """Le UM elemento a partir de `i`. Devolve (tag, valor, proximo) ou None."""
    if i + 2 > len(cru):
        return None
    tag = cru[i]
    tamanho = cru[i + 1]
    j = i + 2
    if tamanho & 0x80:
        # Forma longa: o byte diz quantos bytes de tamanho vem a seguir. Zero e
        # a forma "indefinida", que DER proibe; mais de 4 e um arquivo que nao
        # queremos ler de qualquer jeito.
        quantos = tamanho & 0x7F
        if quantos == 0 or quantos > 4 or j + quantos > len(cru):
            return None
        tamanho = int.from_bytes(cru[j:j + quantos], "big")
        j += quantos
    if j + tamanho > len(cru):
        return None
    return tag, cru[j:j + tamanho], j + tamanho


def _inteiro(valor: bytes):
    """INTEGER do DER -> int. Recusa vazio e recusa negativo."""
    if not valor or valor[0] & 0x80:
        return None
    return int.from_bytes(valor, "big")


def _rsa_de_pkcs1(corpo: bytes):
    """RSAPrivateKey ::= SEQUENCE { versao, n, e, d, p, q, ... }.

    Le so os quatro primeiros. `p` e `q` acelerariam a conta pelo Teorema
    Chines do Resto — descartados de proposito: uma assinatura por hora nao
    paga o codigo a mais, e cada linha aqui e uma linha para revisar.
    """
    seq = _tlv(corpo, 0)
    if not seq or seq[0] != 0x30:
        return None
    dentro, i, numeros = seq[1], 0, []
    for _ in range(4):
        campo = _tlv(dentro, i)
        if not campo or campo[0] != 0x02:
            return None
        n = _inteiro(campo[1])
        if n is None:
            return None
        numeros.append(n)
        i = campo[2]
    versao, n, e, d = numeros
    if versao != 0:
        # Versao 1 e chave multi-primo, com campos a mais. O GitHub nao emite
        # uma, e adivinhar o formato de um arquivo que nao entendemos e pior
        # que recusar.
        return None
    if not (MENOR_MODULO <= n.bit_length() <= MAIOR_MODULO) or e < 3 or d < 1:
        return None
    return Chave(n, e, d)


def chave_de_pem(texto):
    """O conteudo de um arquivo de chave -> `Chave`, ou `None`.

    Aceita os dois formatos que aparecem na pratica: o que o GitHub entrega
    (`BEGIN RSA PRIVATE KEY`, PKCS#1) e o que sai de uma conversao feita por
    engano (`BEGIN PRIVATE KEY`, PKCS#8). O formato e descoberto pelo conteudo,
    nao pelo rotulo: rotulo trocado a mao e mais comum que arquivo corrompido.
    """
    if not isinstance(texto, str) or len(texto) > TETO_DO_ARQUIVO:
        return None
    miolo = "".join(l.strip() for l in texto.splitlines()
                    if l.strip() and not l.startswith("-----"))
    if not miolo:
        return None
    try:
        cru = base64.b64decode(miolo, validate=True)
    except Exception:
        return None

    direto = _rsa_de_pkcs1(cru)
    if direto:
        return direto

    # PKCS#8: SEQUENCE { versao, SEQUENCE(algoritmo), OCTET STRING(a chave) }.
    seq = _tlv(cru, 0)
    if not seq or seq[0] != 0x30:
        return None
    dentro = seq[1]
    versao = _tlv(dentro, 0)
    if not versao or versao[0] != 0x02:
        return None
    algoritmo = _tlv(dentro, versao[2])
    if not algoritmo or algoritmo[0] != 0x30:
        return None
    envelope = _tlv(dentro, algoritmo[2])
    if not envelope or envelope[0] != 0x04:
        return None
    return _rsa_de_pkcs1(envelope[1])


# ------------------------------------------------------------- assinar (RS256)


def assinar_rs256(chave, mensagem: bytes):
    """Assinatura RSASSA-PKCS1-v1_5 com SHA-256. `None` se nao der.

    O bloco montado abaixo e o EMSA-PKCS1-v1_5 do RFC 8017:

        00 01 FF FF ... FF 00 <DigestInfo> <resumo>

    Os `FF` sao enchimento ate o tamanho exato do modulo. O `00` inicial e o
    que garante que o numero seja menor que o modulo; e por isso que o
    resultado volta com `to_bytes(k)` e nao com o tamanho natural do inteiro —
    uma assinatura de 255 bytes onde o GitHub espera 256 vira um 401 sem
    explicacao nenhuma.
    """
    if chave is None or not isinstance(mensagem, (bytes, bytearray)):
        return None
    k = (chave.n.bit_length() + 7) // 8
    miolo = DIGESTINFO_SHA256 + hashlib.sha256(mensagem).digest()
    # O RFC exige pelo menos 8 bytes de enchimento; abaixo disso a chave e
    # pequena demais para o esquema e assinar seria produzir lixo aceito.
    if k < len(miolo) + 11:
        return None
    bloco = b"\x00\x01" + b"\xff" * (k - 3 - len(miolo)) + b"\x00" + miolo
    return pow(int.from_bytes(bloco, "big"), chave.d, chave.n).to_bytes(k, "big")


def _b64url(cru: bytes) -> str:
    return base64.urlsafe_b64encode(cru).decode("ascii").rstrip("=")


def montar_jwt(app_id, chave, agora=None):
    """O bilhete que prova ao GitHub que somos o app. Vale 9 minutos."""
    if chave is None or not isinstance(app_id, str) or not SO_DIGITOS.fullmatch(app_id):
        return None
    agora = int(time.time()) if agora is None else int(agora)
    cabecalho = {"alg": "RS256", "typ": "JWT"}
    corpo = {"iat": agora - FOLGA_PARA_TRAS,
             "exp": agora + VIDA_DO_JWT,
             "iss": app_id}

    def parte(d):
        return _b64url(json.dumps(d, separators=(",", ":")).encode("ascii"))

    assinado = parte(cabecalho) + "." + parte(corpo)
    assinatura = assinar_rs256(chave, assinado.encode("ascii"))
    if assinatura is None:
        return None
    return assinado + "." + _b64url(assinatura)


def quando_vence(texto):
    """`2026-08-27T21:00:00Z` -> segundos desde 1970. `None` se nao der.

    `None` e tratado por quem chama como "nao sei quando vence", e nao como
    "nunca vence": um formato inesperado nao pode virar token eterno.
    """
    if not isinstance(texto, str):
        return None
    try:
        return calendar.timegm(time.strptime(texto, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None


# --------------------------------------------------------------- pedir o token


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """Um 302 levaria o cabecalho `Authorization` — o JWT — para o host que o
    outro lado escolher. E a mesma licao ja aprendida no coletar_github."""

    def redirect_request(self, *a, **k):
        return None


def _pedir_ao_github(url: str, jwt: str, teto: int):
    """POST na API, com o JWT. Levanta em qualquer falha; quem chama traduz."""
    pedido = urllib.request.Request(
        url, data=b"", method="POST",
        headers={"Authorization": "Bearer " + jwt,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": AGENTE})
    abridor = urllib.request.build_opener(_SemRedirecionar)
    with abridor.open(pedido, timeout=teto) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


class Coletor:
    """Guarda a chave e devolve um token valido, renovando quando precisa.

    Uma instancia por processo. O token fica so na memoria: gravar em disco
    seria trocar um segredo de uma hora por um segredo permanente no disco.
    """

    def __init__(self, app_id, instalacao_id, chave_pem, _pedir=None):
        self._app_id = app_id
        self._instalacao_id = instalacao_id
        self._chave_pem = chave_pem
        # `_pedir` e parametro do desenho, e nao concessao ao teste: e o unico
        # ponto deste arquivo que toca a rede, e isola-lo deixa a decisao de
        # renovar testavel sem inventar um servidor.
        self._pedir = _pedir or _pedir_ao_github
        self._token = None
        self._vence_em = None

    def token(self, agora=None):
        """O token de instalacao, ou `None` se nao der para conseguir um."""
        agora = int(time.time()) if agora is None else int(agora)
        if (self._token and self._vence_em
                and agora < self._vence_em - MARGEM_DE_RENOVACAO):
            return self._token

        if not isinstance(self._instalacao_id, str) or \
                not SO_DIGITOS.fullmatch(self._instalacao_id):
            # O id entra numa URL. Um valor com `../` apontaria a requisicao —
            # com o JWT junto — para outro caminho da API.
            _diga("o identificador da instalacao nao e um numero; nao pedi token")
            return None
        chave = chave_de_pem(self._chave_pem)
        if chave is None:
            _diga("a chave privada do app nao foi lida; sem ela nao ha token")
            return None
        jwt = montar_jwt(self._app_id, chave, agora)
        if jwt is None:
            _diga("nao consegui montar o pedido; confira o App ID")
            return None

        try:
            resposta = self._pedir(API % self._instalacao_id, jwt, 30)
        except Exception:
            # A excecao NAO e repassada: `URLError` carrega a URL e `ValueError`
            # do http.client carrega o valor do cabecalho — isto e, o JWT.
            _diga("o GitHub nao entregou um token (rede, ou o app nao esta "
                  "instalado); a coleta segue sem os numeros do GitHub")
            return None

        novo = resposta.get("token") if isinstance(resposta, dict) else None
        if not isinstance(novo, str) or not novo.strip():
            _diga("a resposta do GitHub veio sem token")
            return None
        novo = novo.strip()
        if not (novo.isascii() and novo.isprintable()):
            # Mesma trava do `_token` do coletar_github: um valor com quebra de
            # linha faz o http.client levantar com o cabecalho — o token —
            # dentro da mensagem.
            _diga("o token recebido tem caractere que nao vai em cabecalho HTTP")
            return None

        vence = quando_vence(resposta.get("expires_at"))
        # Sem data legivel, assume o pior prazo plausivel em vez de "eterno".
        self._vence_em = vence if vence else agora + 600
        self._token = novo
        return novo
