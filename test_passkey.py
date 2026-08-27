# -*- coding: utf-8 -*-
"""A conferencia de uma chave de acesso (passkey), do lado do servidor.

O QUE ESTA SENDO TESTADO. O navegador entrega tres embrulhos e este modulo tem
de abrir os tres sem confiar em nenhum: `clientDataJSON` (o que o navegador
afirma que aconteceu), `authenticatorData` (o que o chip afirma) e a assinatura
que amarra os dois. Cada campo conferido aqui e um ataque conhecido barrado, e
o teste diz qual.

A LICAO DE 26/08/2026 ESTA APLICADA AQUI. Naquele dia tres arquivos de teste
deste repositorio tinham o `if __name__` no MEIO, e tudo depois dele nunca
rodava por `python test_arquivo.py`: um teste novo veio VERDE antes de a funcao
existir. Neste arquivo o `if __name__` esta na ultima linha, e
`test_o_arquivo_roda_inteiro` confere isso de dentro.

O ASSINADOR AQUI DENTRO E DE TESTE, E SO. `p256.py` de proposito so confere —
o servidor nunca assina nada. Mas para provar que a conferencia aceita o
legitimo (e nao so que recusa o torto) e preciso produzir um legitimo, e e o
que `_assinar` faz. Ele nao e importado por nenhum codigo de producao.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unittest

import p256
import passkey


RP_ID = "localhost"
ORIGEM = "http://localhost:4777"
ORIGENS = {ORIGEM}


# ------------------------------------------------------ ferramentas de teste

def _assinar(privada, mensagem):
    """Assina como um autenticador assinaria, e devolve o DER.

    So de teste. O `k` vem de `os.urandom` porque aqui nao ha segredo real a
    proteger — a chave e sorteada dentro do proprio teste e morre com ele.
    """
    e = int.from_bytes(hashlib.sha256(mensagem).digest(), "big")
    while True:
        k = int.from_bytes(os.urandom(32), "big") % p256.N
        if k == 0:
            continue
        ponto = p256.multiplicar(k, p256.G)
        r = ponto[0] % p256.N
        if r == 0:
            continue
        s = pow(k, -1, p256.N) * (e + r * privada) % p256.N
        if s:
            return _der(r, s)


def _der(r, s):
    def inteiro(v):
        b = v.to_bytes((v.bit_length() + 8) // 8 or 1, "big")
        return b"\x02" + bytes([len(b)]) + b
    corpo = inteiro(r) + inteiro(s)
    return b"\x30" + bytes([len(corpo)]) + corpo


def _cbor(valor):
    """Codificador CBOR minimo, so para montar o que o navegador mandaria."""
    if isinstance(valor, int) and valor >= 0:
        return _cabeca(0, valor)
    if isinstance(valor, int):
        return _cabeca(1, -valor - 1)
    if isinstance(valor, bytes):
        return _cabeca(2, len(valor)) + valor
    if isinstance(valor, str):
        cru = valor.encode("utf-8")
        return _cabeca(3, len(cru)) + cru
    if isinstance(valor, list):
        return _cabeca(4, len(valor)) + b"".join(_cbor(v) for v in valor)
    if isinstance(valor, dict):
        return _cabeca(5, len(valor)) + b"".join(
            _cbor(c) + _cbor(v) for c, v in valor.items())
    raise TypeError(valor)


def _cabeca(maior, n):
    if n < 24:
        return bytes([(maior << 5) | n])
    if n < 0x100:
        return bytes([(maior << 5) | 24, n])
    if n < 0x10000:
        return bytes([(maior << 5) | 25]) + n.to_bytes(2, "big")
    if n < 0x100000000:
        return bytes([(maior << 5) | 26]) + n.to_bytes(4, "big")
    return bytes([(maior << 5) | 27]) + n.to_bytes(8, "big")


def _trocar(mapa, chave, valor):
    """`dict(m, **{1: 2})` nao existe em Python: chave de keyword e string."""
    novo = dict(mapa)
    novo[chave] = valor
    return novo


def _par_de_chaves():
    privada = int.from_bytes(os.urandom(32), "big") % p256.N or 1
    return privada, p256.multiplicar(privada, p256.G)


def _cose(publica):
    """A chave publica no formato COSE, como o autenticador a entrega.

    1 = tipo de chave (2 = curva eliptica), 3 = algoritmo (-7 = ES256),
    -1 = curva (1 = P-256), -2 = X, -3 = Y. Os numeros negativos como chave de
    mapa nao sao esquisitice: e assim que o COSE separa o que e comum a toda
    chave do que e especifico daquele tipo.
    """
    return {1: 2, 3: -7, -1: 1,
            -2: publica[0].to_bytes(32, "big"),
            -3: publica[1].to_bytes(32, "big")}


def _dados_do_autenticador(rp_id=RP_ID, flags=0x45, contador=1,
                           cred_id=None, cose=None):
    """Monta o bloco que o chip assina. flags 0x45 = presente + verificado + tem chave.

    Sem chave nova, a flag AT (0x40) sai: bloco que ANUNCIA chave e nao traz
    chave e um bloco torto, e o proprio `passkey.dados_do_autenticador` o
    recusa. Montar assim aqui seria testar o parser contra um dado que nenhum
    autenticador produz.
    """
    cru = hashlib.sha256(rp_id.encode("utf-8")).digest()
    if cred_id is None:
        flags &= ~passkey.AT
    cru += bytes([flags]) + contador.to_bytes(4, "big")
    if cred_id is not None:
        cru += b"\x00" * 16                       # aaguid
        cru += len(cred_id).to_bytes(2, "big") + cred_id
        cru += _cbor(cose)
    return cru


def _client_data(tipo, desafio, origem=ORIGEM, **extra):
    corpo = {"type": tipo, "challenge": passkey.b64url(desafio),
             "origin": origem, "crossOrigin": False}
    corpo.update(extra)
    return json.dumps(corpo).encode("utf-8")


def _cadastro(privada_publica=None, **kw):
    """Devolve (clientDataJSON, attestationObject, desafio, privada)."""
    privada, publica = privada_publica or _par_de_chaves()
    desafio = os.urandom(32)
    cred_id = os.urandom(32)
    autenticador = _dados_do_autenticador(
        cred_id=cred_id, cose=_cose(publica),
        **{c: v for c, v in kw.items() if c in ("rp_id", "flags", "contador")})
    atestado = _cbor({"fmt": kw.get("fmt", "none"),
                      "attStmt": kw.get("attStmt", {}),
                      "authData": autenticador})
    return (_client_data("webauthn.create", desafio,
                         origem=kw.get("origem", ORIGEM)),
            atestado, desafio, privada, cred_id)


# --------------------------------------------------------------- o CBOR

class OLeitorDeCbor(unittest.TestCase):
    """CBOR e o formato do embrulho do cadastro. Ler e parsear dado hostil."""

    def volta(self, valor):
        lido, resto = passkey.cbor_ler(_cbor(valor))
        self.assertEqual(resto, b"")
        return lido

    def test_inteiro_pequeno(self):
        self.assertEqual(self.volta(7), 7)

    def test_inteiro_de_um_byte(self):
        self.assertEqual(self.volta(200), 200)

    def test_inteiro_de_dois_bytes(self):
        self.assertEqual(self.volta(70000), 70000)

    def test_inteiro_de_oito_bytes(self):
        self.assertEqual(self.volta(2 ** 40), 2 ** 40)

    def test_inteiro_negativo(self):
        self.assertEqual(self.volta(-7), -7)

    def test_texto(self):
        self.assertEqual(self.volta("passkey"), "passkey")

    def test_texto_com_acento(self):
        self.assertEqual(self.volta("chave de acesso — ção"),
                         "chave de acesso — ção")

    def test_bytes(self):
        self.assertEqual(self.volta(b"\x00\xff"), b"\x00\xff")

    def test_lista(self):
        self.assertEqual(self.volta([1, "dois", b"\x03"]), [1, "dois", b"\x03"])

    def test_mapa(self):
        self.assertEqual(self.volta({1: 2, -1: "x"}), {1: 2, -1: "x"})

    def test_mapa_aninhado(self):
        self.assertEqual(self.volta({"a": {"b": [1, 2]}}), {"a": {"b": [1, 2]}})

    def test_recusa_vazio(self):
        self.assertIsNone(passkey.cbor_ler(b"")[0])

    def test_recusa_corte_no_meio(self):
        cru = _cbor({"fmt": "none"})
        self.assertIsNone(passkey.cbor_ler(cru[:-2])[0])

    def test_recusa_comprimento_maior_que_o_dado(self):
        """Um byte-string que diz ter 1 GiB e um pedido de derrubar o servidor."""
        self.assertIsNone(passkey.cbor_ler(b"\x5a\x40\x00\x00\x00")[0])

    def test_recusa_tipo_que_nao_usamos(self):
        """Float, tag e indefinido nao aparecem em WebAuthn. Recusar e a regra."""
        self.assertIsNone(passkey.cbor_ler(b"\xfb\x00\x00\x00\x00\x00\x00\x00\x00")[0])
        self.assertIsNone(passkey.cbor_ler(b"\x5f\x41\x01\xff")[0])   # indefinido

    def test_recusa_aninhamento_fundo(self):
        """Sem teto de profundidade, uma lista de listas estoura a pilha."""
        cru = b"\x81" * 500 + b"\x01"
        self.assertIsNone(passkey.cbor_ler(cru)[0])

    def test_recusa_chave_de_mapa_repetida(self):
        """Chave repetida deixa dois leitores lerem coisas diferentes."""
        cru = b"\xa2" + _cbor(1) + _cbor(1) + _cbor(1) + _cbor(2)
        self.assertIsNone(passkey.cbor_ler(cru)[0])


# ------------------------------------------------------ a chave COSE

class AChaveCose(unittest.TestCase):

    def test_le_a_chave_publica(self):
        _, publica = _par_de_chaves()
        self.assertEqual(passkey.chave_de_cose(_cose(publica)), publica)

    def test_recusa_algoritmo_que_nao_e_es256(self):
        """RS256 (-257) e outro mundo. Aceitar calado seria fingir conferencia."""
        _, publica = _par_de_chaves()
        torta = _trocar(_cose(publica), 3, -257)
        self.assertIsNone(passkey.chave_de_cose(torta))

    def test_recusa_curva_diferente(self):
        _, publica = _par_de_chaves()
        self.assertIsNone(passkey.chave_de_cose(_trocar(_cose(publica), -1, 2)))

    def test_recusa_tipo_de_chave_diferente(self):
        _, publica = _par_de_chaves()
        self.assertIsNone(passkey.chave_de_cose(_trocar(_cose(publica), 1, 3)))

    def test_recusa_coordenada_de_tamanho_errado(self):
        _, publica = _par_de_chaves()
        self.assertIsNone(passkey.chave_de_cose(
            _trocar(_cose(publica), -2, b"\x01")))

    def test_recusa_ponto_fora_da_curva(self):
        _, publica = _par_de_chaves()
        torta = _trocar(_cose(publica), -3,
                        (publica[1] ^ 1).to_bytes(32, "big"))
        self.assertIsNone(passkey.chave_de_cose(torta))

    def test_recusa_o_que_nao_e_mapa(self):
        self.assertIsNone(passkey.chave_de_cose("nada"))
        self.assertIsNone(passkey.chave_de_cose(None))


# -------------------------------------------- os dados do autenticador

class OsDadosDoAutenticador(unittest.TestCase):

    def test_le_o_bloco_sem_chave(self):
        lido = passkey.dados_do_autenticador(_dados_do_autenticador(contador=9))
        self.assertEqual(lido["contador"], 9)
        self.assertTrue(lido["presente"])
        self.assertTrue(lido["verificado"])
        self.assertIsNone(lido["cred_id"])

    def test_le_o_bloco_com_chave(self):
        cred_id = os.urandom(20)
        _, publica = _par_de_chaves()
        lido = passkey.dados_do_autenticador(
            _dados_do_autenticador(cred_id=cred_id, cose=_cose(publica)))
        self.assertEqual(lido["cred_id"], cred_id)
        self.assertEqual(passkey.chave_de_cose(lido["cose"]), publica)

    def test_flags_dizem_quando_nao_houve_verificacao(self):
        lido = passkey.dados_do_autenticador(_dados_do_autenticador(flags=0x01))
        self.assertTrue(lido["presente"])
        self.assertFalse(lido["verificado"])

    def test_recusa_bloco_curto(self):
        self.assertIsNone(passkey.dados_do_autenticador(b"\x00" * 20))

    def test_recusa_sobra_depois_da_chave(self):
        """Sobra e o vetor classico: um segundo bloco escondido atras do primeiro."""
        cred_id = os.urandom(20)
        _, publica = _par_de_chaves()
        cru = _dados_do_autenticador(cred_id=cred_id, cose=_cose(publica))
        self.assertIsNone(passkey.dados_do_autenticador(cru + b"\x00"))

    def test_recusa_cred_id_maior_que_o_bloco(self):
        cru = hashlib.sha256(RP_ID.encode()).digest() + bytes([0x45])
        cru += (1).to_bytes(4, "big") + b"\x00" * 16 + b"\xff\xff" + b"\x01"
        self.assertIsNone(passkey.dados_do_autenticador(cru))

    def test_recusa_cred_id_vazio(self):
        cru = hashlib.sha256(RP_ID.encode()).digest() + bytes([0x45])
        cru += (1).to_bytes(4, "big") + b"\x00" * 16 + b"\x00\x00"
        self.assertIsNone(passkey.dados_do_autenticador(cru))

    def test_recusa_cred_id_absurdamente_longo(self):
        """A norma poe teto em 1023 bytes. Sem teto, o id vira campo de despejo."""
        cred_id = os.urandom(1100)
        _, publica = _par_de_chaves()
        self.assertIsNone(passkey.dados_do_autenticador(
            _dados_do_autenticador(cred_id=cred_id, cose=_cose(publica))))


# ------------------------------------------------------------ o cadastro

class OCadastro(unittest.TestCase):

    def test_aceita_um_cadastro_legitimo(self):
        cliente, atestado, desafio, _, cred_id = _cadastro()
        r = passkey.conferir_cadastro(cliente, atestado, desafio, RP_ID, ORIGENS)
        self.assertIsNotNone(r)
        self.assertEqual(r["cred_id"], cred_id)
        self.assertTrue(p256.ponto_valido(r["chave"]))

    def test_recusa_desafio_diferente(self):
        """A defesa contra repetir um cadastro capturado."""
        cliente, atestado, _, _, _ = _cadastro()
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, atestado, os.urandom(32), RP_ID, ORIGENS))

    def test_recusa_origem_de_outro_site(self):
        """A defesa contra site falso: a passkey e amarrada ao endereco."""
        cliente, atestado, desafio, _, _ = _cadastro(origem="http://mal.example")
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, atestado, desafio, RP_ID, ORIGENS))

    def test_recusa_rp_id_de_outro_dominio(self):
        cliente, atestado, desafio, _, _ = _cadastro(rp_id="outro.example")
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, atestado, desafio, RP_ID, ORIGENS))

    def test_recusa_tipo_de_operacao_trocado(self):
        """Um `webauthn.get` reaproveitado como cadastro e troca de contexto."""
        _, atestado, desafio, _, _ = _cadastro()
        cliente = _client_data("webauthn.get", desafio)
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, atestado, desafio, RP_ID, ORIGENS))

    def test_recusa_sem_presenca_do_usuario(self):
        cliente, atestado, desafio, _, _ = _cadastro(flags=0x40)
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, atestado, desafio, RP_ID, ORIGENS))

    def test_recusa_sem_verificacao_quando_exigida(self):
        """Sem PIN nem digital, a passkey vira um fator so. A tela pede os dois."""
        cliente, atestado, desafio, _, _ = _cadastro(flags=0x41)
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, atestado, desafio, RP_ID, ORIGENS))

    def test_aceita_sem_verificacao_quando_nao_exigida(self):
        cliente, atestado, desafio, _, _ = _cadastro(flags=0x41)
        self.assertIsNotNone(passkey.conferir_cadastro(
            cliente, atestado, desafio, RP_ID, ORIGENS, exigir_verificacao=False))

    def test_recusa_cross_origin(self):
        """Cadastro dentro de um iframe de outro site nao e cadastro do dono."""
        _, atestado, desafio, _, _ = _cadastro()
        cliente = _client_data("webauthn.create", desafio, crossOrigin=True)
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, atestado, desafio, RP_ID, ORIGENS))

    def test_recusa_atestado_sem_chave(self):
        cliente, _, desafio, _, _ = _cadastro()
        atestado = _cbor({"fmt": "none", "attStmt": {},
                          "authData": _dados_do_autenticador(flags=0x05)})
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, atestado, desafio, RP_ID, ORIGENS))

    def test_recusa_json_que_nao_e_json(self):
        _, atestado, desafio, _, _ = _cadastro()
        self.assertIsNone(passkey.conferir_cadastro(
            b"{nao e json", atestado, desafio, RP_ID, ORIGENS))

    def test_recusa_json_que_nao_e_objeto(self):
        _, atestado, desafio, _, _ = _cadastro()
        self.assertIsNone(passkey.conferir_cadastro(
            b'"so um texto"', atestado, desafio, RP_ID, ORIGENS))

    def test_recusa_atestado_torto(self):
        cliente, _, desafio, _, _ = _cadastro()
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, b"\xff\xff", desafio, RP_ID, ORIGENS))

    def test_recusa_corpo_gigante(self):
        """Sem teto, o cadastro vira um jeito de mandar 50 MiB para o servidor."""
        cliente, _, desafio, _, _ = _cadastro()
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, b"\x00" * (passkey.TETO_DO_CORPO + 1), desafio,
            RP_ID, ORIGENS))

    def test_recusa_desafio_curto(self):
        """Desafio curto e adivinhavel; a norma pede 16 bytes no minimo."""
        cliente, atestado, _, _, _ = _cadastro()
        self.assertIsNone(passkey.conferir_cadastro(
            cliente, atestado, b"\x01\x02", RP_ID, ORIGENS))


# -------------------------------------------------------------- a entrada

class AEntrada(unittest.TestCase):

    def montar(self, **kw):
        privada, publica = _par_de_chaves()
        desafio = os.urandom(32)
        cliente = _client_data("webauthn.get", desafio,
                              origem=kw.get("origem", ORIGEM))
        autenticador = _dados_do_autenticador(
            rp_id=kw.get("rp_id", RP_ID), flags=kw.get("flags", 0x05),
            contador=kw.get("contador", 5))
        assinatura = _assinar(
            kw.get("privada_que_assina", privada),
            autenticador + hashlib.sha256(cliente).digest())
        return cliente, autenticador, assinatura, publica, desafio

    def test_aceita_uma_entrada_legitima(self):
        cliente, aut, assin, publica, desafio = self.montar()
        r = passkey.conferir_entrada(cliente, aut, assin, publica, desafio,
                                     RP_ID, ORIGENS)
        self.assertIsNotNone(r)
        self.assertEqual(r["contador"], 5)

    def test_recusa_assinatura_de_outra_chave(self):
        """O coracao da coisa: so a chave privada certa produz o par (r, s)."""
        outra, _ = _par_de_chaves()
        cliente, aut, assin, publica, desafio = self.montar(
            privada_que_assina=outra)
        self.assertIsNone(passkey.conferir_entrada(
            cliente, aut, assin, publica, desafio, RP_ID, ORIGENS))

    def test_recusa_assinatura_adulterada(self):
        cliente, aut, assin, publica, desafio = self.montar()
        torta = assin[:-1] + bytes([assin[-1] ^ 1])
        self.assertIsNone(passkey.conferir_entrada(
            cliente, aut, torta, publica, desafio, RP_ID, ORIGENS))

    def test_recusa_dados_do_autenticador_adulterados(self):
        """A assinatura cobre authData INTEIRO — mexer nas flags a invalida."""
        cliente, aut, assin, publica, desafio = self.montar()
        torto = aut[:32] + bytes([0x45]) + aut[33:]
        self.assertIsNone(passkey.conferir_entrada(
            cliente, torto, assin, publica, desafio, RP_ID, ORIGENS))

    def test_recusa_client_data_adulterado(self):
        cliente, aut, assin, publica, desafio = self.montar()
        self.assertIsNone(passkey.conferir_entrada(
            cliente + b" ", aut, assin, publica, desafio, RP_ID, ORIGENS))

    def test_recusa_desafio_de_outra_sessao(self):
        """Sem isto, uma resposta capturada serve para sempre."""
        cliente, aut, assin, publica, _ = self.montar()
        self.assertIsNone(passkey.conferir_entrada(
            cliente, aut, assin, publica, os.urandom(32), RP_ID, ORIGENS))

    def test_recusa_origem_de_site_falso(self):
        cliente, aut, assin, publica, desafio = self.montar(
            origem="http://phish.example")
        self.assertIsNone(passkey.conferir_entrada(
            cliente, aut, assin, publica, desafio, RP_ID, ORIGENS))

    def test_recusa_rp_id_errado(self):
        cliente, aut, assin, publica, desafio = self.montar(rp_id="mal.example")
        self.assertIsNone(passkey.conferir_entrada(
            cliente, aut, assin, publica, desafio, RP_ID, ORIGENS))

    def test_recusa_sem_presenca(self):
        cliente, aut, assin, publica, desafio = self.montar(flags=0x00)
        self.assertIsNone(passkey.conferir_entrada(
            cliente, aut, assin, publica, desafio, RP_ID, ORIGENS))

    def test_recusa_tipo_de_operacao_trocado(self):
        privada, publica = _par_de_chaves()
        desafio = os.urandom(32)
        cliente = _client_data("webauthn.create", desafio)
        aut = _dados_do_autenticador(flags=0x05)
        assin = _assinar(privada, aut + hashlib.sha256(cliente).digest())
        self.assertIsNone(passkey.conferir_entrada(
            cliente, aut, assin, publica, desafio, RP_ID, ORIGENS))

    def test_recusa_chave_publica_invalida(self):
        cliente, aut, assin, publica, desafio = self.montar()
        self.assertIsNone(passkey.conferir_entrada(
            cliente, aut, assin, (publica[0], publica[1] ^ 1), desafio,
            RP_ID, ORIGENS))


class OContadorDeClone(unittest.TestCase):
    """O contador so serve se a decisao dele estiver escrita numa funcao.

    A regra: contador que ANDA para tras (ou repete) e a impressao digital de
    uma chave copiada. Autenticador que nao conta usa zero para sempre, e nesse
    caso nao ha o que comparar — a norma prevê e manda deixar passar.
    """

    def test_avanco_normal_passa(self):
        self.assertTrue(passkey.contador_ok(guardado=5, novo=6))

    def test_salto_grande_passa(self):
        self.assertTrue(passkey.contador_ok(guardado=5, novo=500))

    def test_repetir_e_clone(self):
        self.assertFalse(passkey.contador_ok(guardado=5, novo=5))

    def test_voltar_e_clone(self):
        self.assertFalse(passkey.contador_ok(guardado=5, novo=4))

    def test_autenticador_que_nao_conta_passa(self):
        self.assertTrue(passkey.contador_ok(guardado=0, novo=0))

    def test_primeiro_uso_de_quem_conta(self):
        self.assertTrue(passkey.contador_ok(guardado=0, novo=1))

    def test_quem_contava_e_parou_e_clone(self):
        """Contador que ja andou e volta a zero e regressao, nao 'nao conta'."""
        self.assertFalse(passkey.contador_ok(guardado=7, novo=0))


class ABase64DaWeb(unittest.TestCase):
    """base64url sem `=` no fim: e o que o navegador manda e espera."""

    def test_ida_e_volta(self):
        cru = os.urandom(33)
        self.assertEqual(passkey.de_b64url(passkey.b64url(cru)), cru)

    def test_nao_tem_enchimento(self):
        self.assertNotIn("=", passkey.b64url(b"\x01\x02"))

    def test_nao_tem_barra_nem_mais(self):
        for _ in range(50):
            texto = passkey.b64url(os.urandom(32))
            self.assertNotIn("/", texto)
            self.assertNotIn("+", texto)

    def test_aceita_com_enchimento(self):
        """Alguns navegadores mandam com `=`. Aceitar na entrada, nunca na saida."""
        self.assertEqual(passkey.de_b64url("AQI="), b"\x01\x02")

    def test_recusa_lixo(self):
        self.assertIsNone(passkey.de_b64url("!!!"))

    def test_recusa_none(self):
        self.assertIsNone(passkey.de_b64url(None))

    def test_recusa_texto_gigante(self):
        self.assertIsNone(passkey.de_b64url("A" * 100_000))


class ODesafio(unittest.TestCase):

    def test_tem_pelo_menos_32_bytes(self):
        self.assertGreaterEqual(len(passkey.novo_desafio()), 32)

    def test_nunca_repete(self):
        vistos = {passkey.novo_desafio() for _ in range(200)}
        self.assertEqual(len(vistos), 200)


class OArquivoInteiro(unittest.TestCase):
    """A trava contra o defeito de 26/08: `if __name__` no meio do arquivo."""

    def test_o_arquivo_roda_inteiro(self):
        texto = open(__file__, encoding="utf-8").read()
        linhas = texto.splitlines()
        marcas = [i for i, l in enumerate(linhas)
                  if re.match(r'^if __name__', l)]
        self.assertEqual(len(marcas), 1, "so pode haver um `if __name__`")
        sobra = [l for l in linhas[marcas[0] + 1:] if l.strip()]
        self.assertLessEqual(len(sobra), 1,
                             "ha teste depois do `if __name__` — ele nunca roda")


if __name__ == "__main__":
    unittest.main(verbosity=2)
