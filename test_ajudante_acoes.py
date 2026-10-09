"""Provas dos PEDIDOS no `ajudante_servidor.py` (entrega C).

O ajudante roda como root no servidor do dono e, desde a entrega C, pode fazer
duas coisas a pedido do painel: reiniciar um sistema e voltar a versao anterior
de um projeto. Tudo que decide se ele FAZ mora aqui, e cada guarda e provado
sabotando o codigo (a lista das sabotagens esta no commit).

REGRA DO VETOR DE FORA. A conferencia da assinatura e conta de criptografia
transcrita a mao, e conta testada so com dado que ela mesma produziu prova que
concorda consigo, nao que esta certa. `VETOR_DE_FORA` abaixo foi produzido pelo
OpenSSL; aqui entram so as chaves PUBLICAS (a privada foi apagada).

O que a conta P-256 do ajudante tem de ser: a MESMA do `p256.py` (comparada por
`ast`, ja sem o docstring) e a que bate com a RFC 6979 A.2.5. Os casos que
precisam de uma ordem para um alvo que o vetor nao cobre (bloqueado,
desconhecido, repetida, teto...) usam um assinador de TESTE: ele so serve para
rotear a ordem ate a conferencia que se quer provar, nunca para provar a conta.
"""

import ast
import base64
import builtins
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import ajudante_servidor as aj
import p256
import passkey
import tarefas
from test_p256 import PRIVADA, PUBLICA_X, PUBLICA_Y, SAMPLE_R, SAMPLE_S, TEST_R, TEST_S

# openssl 3.5.7 (9 jun 2026), 09/10/2026. Para cada caso, o ajudante monta os
# dados com um script que NAO assina, e o OpenSSL assina:
#   openssl ecparam -name prime256v1 -genkey -noout -outform DER -out k1
#   openssl ec -inform DER -in k1 -pubout -outform DER -out k1pub   (x,y = ultimos 64 bytes)
#   openssl dgst -sha256 -sign k1 -keyform DER -out sig_<caso> assinado_<caso>
# assinado_<caso> = autenticador (37 bytes) || sha256(cliente). `outra_chave` e
# assinada por k2. As privadas foram apagadas; so as publicas ficam.
VETOR_DE_FORA = {
    "publica_k1": {"x": "da35c732bcf5c4e3d25745854ac73ff3da4a4d767f131742bc08e87c2a42f417", "y": "251b5ae0b813e40c294632b2ea656b896dd06522c05c8c744a38971b3b1d3f0b"},
    "publica_k2": {"x": "cd76e4d947930fde2013be2bd12400fc2ad841d65e05f1c017cb203250bc265b", "y": "1a60e3c80137f10e95cd7a438d235bdb6ffa82fc15debc5466a4bcf983673f5f"},
    "valido": {
        "cliente": '{"type":"webauthn.get","challenge":"I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ","origin":"https://dervs.com.br","crossOrigin":false}',
        "autenticador": "4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff70500000001",
        "assinatura": "3046022100f01f96dd104d103992e4e293099fe8f21e6cbc48387dfc164f4035ddee1e66a6022100abd599e6ddad201b9dbea420afcf7966cb510c295c19af8a205a6f661f8b6bdf"},
    "valido_voltar": {
        "cliente": '{"type":"webauthn.get","challenge":"J6WU23PG9EXfXUeLPjLaejTvUgTWQUVyPFEgnvxiaPw","origin":"https://dervs.com.br","crossOrigin":false}',
        "autenticador": "4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff70500000001",
        "assinatura": "3044022015651a5111331fcb08a543a48c1d7ac73d6adec642ae406f42f297db7cd913f502206bce25a5e37f563c389db96a08d85bfe7c15bf15ae0652eae09ffa2db96b7063"},
    "outra_chave": {
        "cliente": '{"type":"webauthn.get","challenge":"I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ","origin":"https://dervs.com.br","crossOrigin":false}',
        "autenticador": "4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff70500000001",
        "assinatura": "30450220460bd11c5df71d45fbfe52233d36df0a6b47a3c24f7a1215a89bf56648f3b95a022100ac748d4485d5c50b3f305d6313d8f75d1268c9582a4404d253de3caaec39ab15"},
    "outro_desafio": {
        "cliente": '{"type":"webauthn.get","challenge":"Sa0bQoXXiF9-GUnY80LJZuJFfEbP3pkiCUcyWnPsRMY","origin":"https://dervs.com.br","crossOrigin":false}',
        "autenticador": "4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff70500000001",
        "assinatura": "3045022100f4a6c2417dffb1417ad0d88cc3f8621abfe839899738fdb56f42b109880bbf96022069c674746f797f2a0dbe306b65b23e455bd6dd61de1741cc15c8ce1f7df84f5a"},
    "tipo_errado": {
        "cliente": '{"type":"webauthn.create","challenge":"I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ","origin":"https://dervs.com.br","crossOrigin":false}',
        "autenticador": "4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff70500000001",
        "assinatura": "304502203613036a8c99e65e205441c3f8dff63df44a4d3978906e36e773cd0107e6de7b022100f59cdecfee8f28836e23857ead2beb42f9e05787e04b427eeb31e263a466ec53"},
    "outra_origem": {
        "cliente": '{"type":"webauthn.get","challenge":"I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ","origin":"https://dervs.com.br.exemplo.net","crossOrigin":false}',
        "autenticador": "4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff70500000001",
        "assinatura": "304502204b6e59c1bf932238204ee699e43a824b98675f58dc4495ff84aadbbe452911b802210082657338095fec8b69426a001758c0a32658f8304bd9462d2655a9d3853ae23e"},
    "cruzado": {
        "cliente": '{"type":"webauthn.get","challenge":"I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ","origin":"https://dervs.com.br","crossOrigin":true}',
        "autenticador": "4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff70500000001",
        "assinatura": "304502203daed80541d1aa90112766bb5a6b6b565205a3fa15270cd3b21a3a6c0882fb4d022100e5829854e373cae8e8ce591edc8367a3b75a28e6f9720e616c4885a8735aaa7d"},
    "outro_rp": {
        "cliente": '{"type":"webauthn.get","challenge":"I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ","origin":"https://dervs.com.br","crossOrigin":false}',
        "autenticador": "6f2b2e1c0e31390141fc933307836e027dc706eddabe65e9e837cd84050e273d0500000001",
        "assinatura": "3045022001b63c54abf8af07fa9b8e22b90fd3d7ccd8fd95400c001ac2b56711d02b9810022100c966226c58ad3a9af23df5f2f5c63f19bf5d3a616104a77971c7823065abc1fd"},
    "sem_uv": {
        "cliente": '{"type":"webauthn.get","challenge":"I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ","origin":"https://dervs.com.br","crossOrigin":false}',
        "autenticador": "4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff70100000001",
        "assinatura": "304402202321ad271d6929d30a3116158dd7c6593e279b3b4174cafaeda5b56e78214ab7022046f6406005dae0535dd314ef6c6af6177c34a552c12e9d4b95ac772f45205f08"},
    "com_at": {
        "cliente": '{"type":"webauthn.get","challenge":"I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ","origin":"https://dervs.com.br","crossOrigin":false}',
        "autenticador": "4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff74500000001",
        "assinatura": "3045022100d452c1701bfc6b0c601a10c7123181388ca9e3d1d2d1cc0458fc26577b537ae202206c25a0f479e42e34f1262f0552a81a3007139e35ad7fe53a29daa03a9cecbd65"},
}

SERVIDOR = "7f3a9c2e5b8d41f6a0c3e9b2d4f6a8c1"
NUMERO = "4e1d2c3b5a6978f0e1d2c3b4a5968778"
CRIADO, VENCE = 1791558000, 1791558300
AGORA = 1791558010
ORIGEM, RP = "https://dervs.com.br", "dervs.com.br"
TOKEN = "tok-de-teste"

CAMPOS = {"servidor": SERVIDOR, "tipo": "reiniciar", "alvo": "grimoire-web",
          "numero": NUMERO, "criado": CRIADO, "vence": VENCE}
CAMPOS_VOLTAR = dict(CAMPOS, tipo="voltar", alvo="grimoire")

# Escritos a mao aqui, e a MESMA tabela esta em test_tarefas (lado do DERVS).
HASH_REINICIAR = "2358580c05214c6639569a105fe02350d2cea31d76f4fd6f6ead896445090d84"
B64_REINICIAR = "I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ"
HASH_VOLTAR = "27a594db73c6f445df5d478b3e32da7a34ef5204d64145723c51209efc6268fc"
B64_VOLTAR = "J6WU23PG9EXfXUeLPjLaejTvUgTWQUVyPFEgnvxiaPw"


def b64(cru):
    return base64.urlsafe_b64encode(cru).rstrip(b"=").decode("ascii")


def chave_de(nome):
    return (int(VETOR_DE_FORA[nome]["x"], 16), int(VETOR_DE_FORA[nome]["y"], 16))


def do_vetor(caso, base=CAMPOS):
    """A ordem como o painel a entregaria, com os dados do OpenSSL."""
    v = VETOR_DE_FORA[caso]
    return dict(base, cliente=b64(v["cliente"].encode("ascii")),
                autenticador=b64(bytes.fromhex(v["autenticador"])),
                assinatura=b64(bytes.fromhex(v["assinatura"])))


# ------------------------------------------- o assinador de TESTE (so roteia)

def _der(r, s):
    def inteiro(v):
        b = v.to_bytes((v.bit_length() + 7) // 8 or 1, "big")
        return b"\x02" + bytes([len(b) + (b[0] >> 7)]) + (b"\x00" if b[0] & 0x80 else b"") + b
    corpo = inteiro(r) + inteiro(s)
    return b"\x30" + bytes([len(corpo)]) + corpo


def assinar_de_teste(mensagem):
    k = 0x1F2E3D4C5B6A79880123456789ABCDEF0123456789ABCDEF0123456789ABCD
    e = int.from_bytes(hashlib.sha256(mensagem).digest(), "big")
    r = p256.multiplicar(k, p256.G)[0] % p256.N
    s = pow(k, -1, p256.N) * (e + r * PRIVADA) % p256.N
    return _der(r, s)


PUBLICA_DE_TESTE = p256.multiplicar(PRIVADA, p256.G)


def ordem_de_teste(tipo="reiniciar", alvo="grimoire-web", numero=NUMERO,
                   criado=CRIADO, servidor=SERVIDOR, flags=0x05):
    campos = {"servidor": servidor, "tipo": tipo, "alvo": alvo, "numero": numero,
              "criado": criado, "vence": criado + 300}
    texto = aj.texto_da_ordem(campos)
    cliente = json.dumps({"type": "webauthn.get", "origin": ORIGEM,
                          "challenge": b64(hashlib.sha256(texto.encode("ascii")).digest()),
                          "crossOrigin": False}, separators=(",", ":")).encode("ascii")
    auth = hashlib.sha256(RP.encode("ascii")).digest() + bytes([flags]) + b"\x00\x00\x00\x01"
    sig = assinar_de_teste(auth + hashlib.sha256(cliente).digest())
    return dict(campos, cliente=b64(cliente), autenticador=b64(auth), assinatura=b64(sig))


def config(chaves=None, voltaveis=("grimoire", "dervs"), ident=SERVIDOR):
    chaves = chaves if chaves is not None else [chave_de("publica_k1"), PUBLICA_DE_TESTE]
    return {"versao": 1, "ident": ident, "origem": ORIGEM, "rp_id": RP,
            "chaves": [["%064x" % x, "%064x" % y] for x, y in chaves],
            "voltaveis": list(voltaveis)}


def sistemas(*pares):
    pares = pares or (("grimoire-web", "grimoire"), ("dervs-app", "dervs"))
    return lambda: [{"nome": n, "projeto": p} for n, p in pares]


def confere(ordem, cfg=None, numeros=None, feitas=None, agora=AGORA, sist=None):
    return aj.conferir_ordem(ordem, cfg or config(), numeros or {}, feitas or [],
                             agora, sist or sistemas())


# ----------------------------------------------------------------- a ordem (C0)

class OTextoDaOrdem(unittest.TestCase):

    def test_a_tabela_do_contrato(self):
        for campos, hexa, base in ((CAMPOS, HASH_REINICIAR, B64_REINICIAR),
                                   (CAMPOS_VOLTAR, HASH_VOLTAR, B64_VOLTAR)):
            texto = aj.texto_da_ordem(campos)
            resumo = hashlib.sha256(texto.encode("ascii")).digest()
            self.assertEqual(hexa, resumo.hex())
            self.assertEqual(base, b64(resumo))

    def test_sete_linhas_sem_quebra_no_fim(self):
        self.assertEqual(
            "dervs-ordem=1\nservidor=" + SERVIDOR + "\ntipo=reiniciar\n"
            "alvo=grimoire-web\nnumero=" + NUMERO + "\ncriado=1791558000\n"
            "vence=1791558300", aj.texto_da_ordem(CAMPOS))

    def test_o_que_nao_e_ordem_nao_existe(self):
        casos = {
            "alvo com =": dict(CAMPOS, alvo="a=b"),
            "alvo com quebra": dict(CAMPOS, alvo="a\nb"),
            "alvo com quebra no fim": dict(CAMPOS, alvo="grimoire\n"),
            "voltar com maiuscula": dict(CAMPOS_VOLTAR, alvo="Grimoire"),
            "voltar com _": dict(CAMPOS_VOLTAR, alvo="gri_moire"),
            "reiniciar comecando por -": dict(CAMPOS, alvo="-web"),
            "alvo vazio": dict(CAMPOS, alvo=""),
            "alvo de 129": dict(CAMPOS, alvo="a" * 129),
            "voltar de 64": dict(CAMPOS_VOLTAR, alvo="a" * 64),
            "numero de 31": dict(CAMPOS, numero=NUMERO[:31]),
            "numero de 33": dict(CAMPOS, numero=NUMERO + "a"),
            "numero com maiuscula": dict(CAMPOS, numero=NUMERO.upper()),
            "servidor com g": dict(CAMPOS, servidor="g" + SERVIDOR[1:]),
            "criado com zero a esquerda": dict(CAMPOS, criado="01791558000"),
            "criado de 11 digitos": dict(CAMPOS, criado=17915580000, vence=17915580300),
            "vence 299 depois": dict(CAMPOS, vence=CRIADO + 299),
            "criado booleano": dict(CAMPOS, criado=True, vence=301),
            "criado negativo": dict(CAMPOS, criado=-1, vence=299),
            "tipo publicar": dict(CAMPOS, tipo="publicar"),
            "campo a mais": dict(CAMPOS, extra="x"),
            "campo faltando": {k: v for k, v in CAMPOS.items() if k != "numero"},
            "nao e dict": None,
        }
        for nome, campos in casos.items():
            with self.subTest(nome):
                self.assertIsNone(aj.texto_da_ordem(campos))

    def test_zero_e_um_inteiro_valido(self):
        self.assertIsNotNone(aj.texto_da_ordem(dict(CAMPOS, criado=0, vence=300)))


class AImpressao(unittest.TestCase):

    def test_o_gerador_da_p256(self):
        self.assertEqual("d875db7def232236", aj.impressao(p256.G[0], p256.G[1]))

    def test_sao_os_16_primeiros_hex_do_resumo_dos_64_bytes(self):
        x, y = chave_de("publica_k1")
        esperado = hashlib.sha256(x.to_bytes(32, "big") + y.to_bytes(32, "big")).hexdigest()[:16]
        self.assertEqual(esperado, aj.impressao(x, y))


# ------------------------------------------- a conta P-256 e a do p256.py (C3)

COPIADAS = ("somar", "multiplicar", "ponto_valido", "conferir",
            "assinatura_de_der", "_inteiro")
CONSTANTES = ("P", "A", "B", "N", "G", "TETO_DO_DER")


def _sem_docstring(no):
    corpo = list(no.body)
    if (corpo and isinstance(corpo[0], ast.Expr)
            and isinstance(corpo[0].value, ast.Constant)
            and isinstance(corpo[0].value.value, str)):
        corpo = corpo[1:]
    return (no.name, ast.dump(no.args),
            ast.dump(no.returns) if no.returns else "",
            ast.dump(ast.Module(body=corpo, type_ignores=[])))


def funcoes_de(fonte, nomes):
    achadas = {}
    for no in ast.parse(fonte).body:
        if isinstance(no, ast.FunctionDef) and no.name in nomes:
            achadas[no.name] = no
    return achadas


def nomes_livres(no):
    """Nomes que a funcao le e que nao sao dela nem da linguagem."""
    proprios = {a.arg for a in no.args.args}
    lidos = set()
    for n in ast.walk(no):
        if isinstance(n, ast.Name):
            if isinstance(n.ctx, ast.Store):
                proprios.add(n.id)
            else:
                lidos.add(n.id)
    return {n for n in lidos - proprios if not hasattr(builtins, n)}


class AContaP256EAMesmaDoP256(unittest.TestCase):
    """O ajudante e LIDO do disco e nao importa `p256.py`: a conta e uma copia, e
    copia que diverge reprova. O docstring fica de fora da comparacao (a copia nao
    o leva); o resto da arvore tem de ser igual."""

    def setUp(self):
        self.dele = funcoes_de(Path(aj.__file__).read_text(encoding="ascii"), COPIADAS)
        self.do_p256 = funcoes_de(Path(p256.__file__).read_text(encoding="utf-8"), COPIADAS)

    def test_as_seis_funcoes_existem_nos_dois(self):
        self.assertEqual(set(COPIADAS), set(self.dele))
        self.assertEqual(set(COPIADAS), set(self.do_p256))

    def test_cada_funcao_tem_a_mesma_arvore(self):
        for nome in COPIADAS:
            with self.subTest(nome):
                self.assertEqual(_sem_docstring(self.do_p256[nome]),
                                 _sem_docstring(self.dele[nome]))

    def test_cada_constante_tem_o_mesmo_valor(self):
        for nome in CONSTANTES:
            with self.subTest(nome):
                self.assertEqual(getattr(p256, nome), getattr(aj, nome))

    def test_nada_que_as_copias_citem_fica_de_fora_da_conferencia(self):
        conferido = set(CONSTANTES) | set(COPIADAS)
        for nome, no in self.dele.items():
            livres = nomes_livres(no)
            with self.subTest(nome):
                self.assertLessEqual(livres, conferido)
                for citado in livres:
                    self.assertTrue(hasattr(aj, citado), citado)

    def test_o_guarda_acusa_uma_copia_adulterada(self):
        fonte = Path(aj.__file__).read_text(encoding="ascii")
        torta = fonte.replace("m = (y2 - y1) * pow(x2 - x1, -1, P) % P",
                              "m = (y1 - y2) * pow(x2 - x1, -1, P) % P")
        self.assertNotEqual(fonte, torta)
        copia = funcoes_de(torta, COPIADAS)
        self.assertNotEqual(_sem_docstring(self.do_p256["somar"]),
                            _sem_docstring(copia["somar"]))


class ARfc6979(unittest.TestCase):
    """Os mesmos vetores de `test_p256.py` (RFC 6979 A.2.5), pela cópia."""

    PUBLICA = (PUBLICA_X, PUBLICA_Y)

    def resumo(self, texto):
        return hashlib.sha256(texto.encode("ascii")).digest()

    def test_confere_as_duas_assinaturas_da_norma(self):
        self.assertTrue(aj.conferir(self.PUBLICA, self.resumo("sample"), SAMPLE_R, SAMPLE_S))
        self.assertTrue(aj.conferir(self.PUBLICA, self.resumo("test"), TEST_R, TEST_S))

    def test_uma_nao_vale_para_a_outra_mensagem(self):
        self.assertFalse(aj.conferir(self.PUBLICA, self.resumo("test"), SAMPLE_R, SAMPLE_S))

    def test_a_chave_nasce_da_privada(self):
        self.assertEqual(self.PUBLICA, aj.multiplicar(PRIVADA, aj.G))
        self.assertTrue(aj.ponto_valido(self.PUBLICA))
        self.assertIsNone(aj.multiplicar(aj.N, aj.G))

    def test_o_der_do_openssl_desembrulha(self):
        der = bytes.fromhex(VETOR_DE_FORA["valido"]["assinatura"])
        r, s = aj.assinatura_de_der(der)
        self.assertEqual(der, _der(r, s))


# --------------------------------------------------- o vetor de fora (C12)

MOTIVO_DO_CASO = {
    "outra_chave": "assinatura", "outro_desafio": "desafio", "tipo_errado": "desafio",
    "outra_origem": "origem", "cruzado": "origem", "outro_rp": "aparelho",
    "sem_uv": "aparelho", "com_at": "aparelho"}


class OVetorDeFora(unittest.TestCase):

    def cfg(self):
        return config(chaves=[chave_de("publica_k1")])

    def test_o_valido_passa(self):
        self.assertIsNone(confere(do_vetor("valido"), self.cfg()))

    def test_o_valido_de_voltar_passa(self):
        self.assertIsNone(confere(do_vetor("valido_voltar", CAMPOS_VOLTAR), self.cfg()))

    def test_cada_caso_e_recusado_pelo_motivo_dele(self):
        for caso, motivo in MOTIVO_DO_CASO.items():
            with self.subTest(caso):
                self.assertEqual(motivo, confere(do_vetor(caso), self.cfg()))

    def test_sem_assinatura(self):
        self.assertEqual("assinatura", confere(dict(do_vetor("valido"), assinatura=""), self.cfg()))

    def test_vencida(self):
        self.assertEqual("vencida", confere(do_vetor("valido"), self.cfg(), agora=1791558301))

    def test_aceita_no_instante_do_contrato(self):
        self.assertIsNone(confere(do_vetor("valido"), self.cfg(), agora=1791558010))

    def test_repetida(self):
        self.assertEqual("repetida", confere(do_vetor("valido"), self.cfg(),
                                             numeros={NUMERO: VENCE}))

    def test_testemunha_cruzada_o_derv_aceita_a_mesma_assinatura(self):
        """A conferencia do DERVS (passkey.conferir_entrada) aceita o que o
        ajudante aceita - e recusa o que o ajudante recusa por assinatura."""
        v = VETOR_DE_FORA["valido"]
        desafio = hashlib.sha256(aj.texto_da_ordem(CAMPOS).encode("ascii")).digest()
        visto = passkey.conferir_entrada(
            v["cliente"].encode("ascii"), bytes.fromhex(v["autenticador"]),
            bytes.fromhex(v["assinatura"]), chave_de("publica_k1"), desafio, RP,
            {ORIGEM})
        self.assertEqual({"contador": 1}, visto)
        o = VETOR_DE_FORA["outra_chave"]
        self.assertIsNone(passkey.conferir_entrada(
            o["cliente"].encode("ascii"), bytes.fromhex(o["autenticador"]),
            bytes.fromhex(o["assinatura"]), chave_de("publica_k1"), desafio, RP,
            {ORIGEM}))


# ------------------------------------------------ as onze conferencias (C3)

class AsOnzeConferencias(unittest.TestCase):

    def test_1_forma(self):
        boa = ordem_de_teste()
        casos = {
            "cliente de 4097": dict(boa, cliente=b64(b"x" * 4097)),
            "autenticador de 36": dict(boa, autenticador=b64(b"x" * 36)),
            "autenticador de 38": dict(boa, autenticador=b64(b"x" * 38)),
            "assinatura de 81": dict(boa, assinatura=b64(b"x" * 81)),
            "base64 invalido": dict(boa, cliente="!!!!"),
            "base64 com padding": dict(boa, assinatura=boa["assinatura"] + "="),
            "base64 que nao e texto": dict(boa, assinatura=7),
            "campo faltando": {k: v for k, v in boa.items() if k != "cliente"},
            "numero torto": dict(boa, numero="zz"),
            "tipo publicar": dict(boa, tipo="publicar"),
            "alvo com quebra": dict(boa, alvo="a\nb"),
            "nao e dict": "ordem",
        }
        for nome, ordem in casos.items():
            with self.subTest(nome):
                self.assertEqual("forma", confere(ordem))

    def test_2_outro_servidor_vem_antes_da_assinatura(self):
        """Uma ordem de outro servidor, bem formada e ate bem assinada, para
        antes de qualquer conta de criptografia."""
        ordem = ordem_de_teste(servidor="a" * 32)
        self.assertEqual("outro_servidor", confere(ordem))
        sem_sig = dict(ordem, assinatura="")
        self.assertEqual("outro_servidor", confere(sem_sig))

    def test_4_vencida(self):
        ordem = ordem_de_teste()
        self.assertEqual("vencida", confere(ordem, agora=CRIADO - 122))
        self.assertEqual("vencida", confere(ordem, agora=VENCE + 1))
        self.assertIsNone(confere(ordem, agora=CRIADO - 120))
        self.assertIsNone(confere(ordem, agora=VENCE))
        # janela de 300 s exatos: vem como forma de vencida, nunca aceita
        fora = dict(ordem, vence=VENCE + 1)
        self.assertEqual("vencida", confere(fora))

    def test_5_assinatura_de_chave_desconhecida(self):
        ordem = ordem_de_teste()
        self.assertEqual("assinatura", confere(ordem, config(chaves=[chave_de("publica_k2")])))
        self.assertEqual("assinatura", confere(ordem, config(chaves=[])))

    def test_5_qualquer_das_chaves_guardadas_serve(self):
        ordem = ordem_de_teste()
        for ordem_das in ([chave_de("publica_k1"), PUBLICA_DE_TESTE],
                          [PUBLICA_DE_TESTE, chave_de("publica_k1")]):
            self.assertIsNone(confere(ordem, config(chaves=ordem_das)))

    def test_6_desafio_de_outra_ordem(self):
        a = ordem_de_teste()
        b = ordem_de_teste(alvo="dervs-app")
        trocada = dict(a, cliente=b["cliente"], assinatura=b["assinatura"])
        self.assertEqual("desafio", confere(trocada))

    def test_6_cliente_que_nao_e_json(self):
        ordem = ordem_de_teste()
        cru = b"nao e json"
        auth = base64.urlsafe_b64decode(ordem["autenticador"] + "==")
        sig = assinar_de_teste(auth + hashlib.sha256(cru).digest())
        self.assertEqual("desafio", confere(dict(ordem, cliente=b64(cru), assinatura=b64(sig))))

    def test_8_flags(self):
        for flags in (0x01, 0x04, 0x45, 0x85, 0xC5, 0x00):
            with self.subTest(flags=hex(flags)):
                self.assertEqual("aparelho", confere(ordem_de_teste(flags=flags)))
        # chave sincronizada (BE/BS ligados) e normal
        self.assertIsNone(confere(ordem_de_teste(flags=0x1D)))

    def test_9_voltar_bloqueado_pelo_nome_do_projeto(self):
        # `voltar` so aceita minusculas e hifen; a variacao de caixa e de `_`
        # so passa pela forma em `reiniciar` (testado abaixo).
        for nome in ("ajudei-saude", "ajudei-saude-web"):
            with self.subTest(nome):
                self.assertEqual("bloqueado", confere(
                    ordem_de_teste("voltar", nome), config(voltaveis=[nome])))

    def test_9_reiniciar_bloqueado_pelo_nome_do_conteiner(self):
        for nome in ("ajudei-saude", "Ajudei_Saude", "ajudei.saude-web"):
            with self.subTest(nome):
                self.assertEqual("bloqueado", confere(
                    ordem_de_teste("reiniciar", nome), sist=sistemas((nome, "outro"))))

    def test_9_reiniciar_bloqueado_pelo_rotulo_de_projeto(self):
        """O nome do conteiner e inocente; o projeto dele nao."""
        for rotulo in ("ajudei-saude", "Ajudei_Saude"):
            with self.subTest(rotulo):
                self.assertEqual("bloqueado", confere(
                    ordem_de_teste("reiniciar", "grimoire-web"),
                    sist=sistemas(("grimoire-web", rotulo))))

    def test_9_vem_antes_do_alvo_conhecido(self):
        """Bloqueado e bloqueado mesmo que o alvo nem exista: o motivo nao
        revela se o sistema existe."""
        self.assertEqual("bloqueado", confere(
            ordem_de_teste("reiniciar", "ajudei-saude"), sist=sistemas()))

    def test_10_desconhecido(self):
        self.assertEqual("desconhecido", confere(ordem_de_teste("voltar", "outro"),
                                                 config(voltaveis=["grimoire"])))
        self.assertEqual("desconhecido", confere(ordem_de_teste("reiniciar", "sumiu-web")))
        self.assertEqual("desconhecido", confere(ordem_de_teste("reiniciar"),
                                                 sist=lambda: []))

    def test_10_o_ps_so_e_perguntado_quando_precisa(self):
        chamadas = []

        def sist():
            chamadas.append(1)
            return []
        confere(ordem_de_teste("voltar", "grimoire"), sist=sist)
        confere(dict(ordem_de_teste(), servidor="a" * 32), sist=sist)
        self.assertEqual([], chamadas)
        confere(ordem_de_teste("reiniciar"), sist=sist)
        self.assertEqual(1, len(chamadas))

    def test_11_repetida(self):
        self.assertEqual("repetida", confere(ordem_de_teste(), numeros={NUMERO: VENCE}))

    def test_a_ordem_boa_passa(self):
        self.assertIsNone(confere(ordem_de_teste()))
        self.assertIsNone(confere(ordem_de_teste("voltar", "grimoire")))

    def test_conferir_nunca_levanta(self):
        for ordem in (None, 7, {}, {"servidor": 1}, dict(ordem_de_teste(), criado="x")):
            with self.subTest(ordem=ordem):
                self.assertIn(confere(ordem), aj.MOTIVOS_DA_RECUSA)

    def test_config_torta_nao_levanta_nem_passa(self):
        for cfg in ({}, {"chaves": "x"}, {"chaves": [["zz", "zz"]]}, None):
            with self.subTest(cfg=cfg):
                motivo = aj.conferir_ordem(ordem_de_teste(), cfg, {}, [], AGORA, sistemas())
                self.assertIn(motivo, aj.MOTIVOS_DA_RECUSA)


# ------------------------------------- o fio de `ordens`, com dubles (C3, C4)

INSPECT = ("/grimoire-web\trunning\thealthy\t2026-10-08T12:00:00Z\t0\timg:1\tgrimoire\t\n"
           "/dervs-app\trunning\t\t2026-10-08T12:00:00Z\t0\timg:2\tdervs\t\n")


class ComRaizDeOrdens(unittest.TestCase):
    ALVO = "https://painel.exemplo.test"

    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="ajudante-ordens-")
        self.addCleanup(shutil.rmtree, self.raiz, True)
        self.feitos = []
        self.pedidos = []
        self.rodadas = []
        self.pasta_dados = Path(self.raiz) / "var" / "lib" / "dervs-ajudante"
        self.pasta_dados.mkdir(parents=True)
        (self.pasta_dados / "agente.json").write_text(
            json.dumps({"alvo": self.ALVO, "token": TOKEN}))
        self.ordem = ordem_de_teste()
        self.cfg = config()
        self.codigo_de_fazer = 0
        self.ligar(self.cfg)

    def ligar(self, cfg):
        pasta = Path(self.raiz) / "etc" / "dervs-ajudante"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "ordens.json").write_text(json.dumps(cfg))

    def numeros(self, **dados):
        (self.pasta_dados / "numeros.json").write_text(json.dumps(
            {"numeros": dados.get("numeros", {}), "feitas": dados.get("feitas", [])}))

    def lidos(self):
        return json.loads((self.pasta_dados / "numeros.json").read_text())

    def abrir(self, metodo, url, corpo, token, prazo):
        self.pedidos.append((metodo, url, corpo, token))
        if url.endswith("/agente/servidor/ordens"):
            return 200, {"ordem": self.ordem}
        if url.endswith("/agente/servidor/desfecho"):
            return 200, {"ok": True}
        return 0, None

    def rodar(self, argv, prazo):
        self.rodadas.append(list(argv))
        if tuple(argv) == aj.ARGV_DO_PS:
            return True, "abc123\n"
        if tuple(argv[:3]) == aj.ARGV_DO_INSPECT[:3]:
            return True, INSPECT
        return True, ""

    def fazer(self, argv, prazo):
        self.feitos.append((list(argv), prazo))
        return self.codigo_de_fazer

    def rodar_ordens(self, agora=AGORA, **extra):
        args = dict(alvo=self.ALVO, raiz=self.raiz, rodar=self.rodar,
                    abrir=self.abrir, fazer=self.fazer, agora=agora)
        args.update(extra)
        return aj.ordens(**args)

    def desfecho(self):
        achados = [p for p in self.pedidos if p[1].endswith("/agente/servidor/desfecho")]
        self.assertEqual(1, len(achados), self.pedidos)
        return achados[0][2]


class DesligadoPorPadrao(ComRaizDeOrdens):

    def test_sem_o_arquivo_nada_e_buscado_nem_feito(self):
        os.unlink(Path(self.raiz) / "etc" / "dervs-ajudante" / "ordens.json")
        self.assertEqual(aj.OK, self.rodar_ordens())
        self.assertEqual([], self.pedidos)
        self.assertEqual([], self.feitos)
        self.assertEqual([], self.rodadas)

    def test_arquivo_torto_tambem_desliga(self):
        (Path(self.raiz) / "etc" / "dervs-ajudante" / "ordens.json").write_text("{nao")
        self.assertEqual(aj.OK, self.rodar_ordens())
        self.assertEqual([], self.pedidos)
        self.assertEqual([], self.feitos)

    def test_arquivo_com_versao_errada_desliga(self):
        self.ligar(dict(self.cfg, versao=2))
        self.rodar_ordens()
        self.assertEqual([], self.pedidos)


class ODesfechoDeCadaCaminho(ComRaizDeOrdens):

    def test_feita(self):
        self.assertEqual(aj.OK, self.rodar_ordens())
        self.assertEqual([(["docker", "restart", "grimoire-web"], 120)], self.feitos)
        self.assertEqual({"numero": NUMERO, "desfecho": "feita", "codigo": 0,
                          "motivo": None}, self.desfecho())
        self.assertEqual(TOKEN, self.pedidos[-1][3])
        self.assertEqual({}, self.pedidos[0][2])
        self.assertEqual(self.ALVO + "/agente/servidor/ordens", self.pedidos[0][1])

    def test_falhou_com_o_codigo(self):
        self.codigo_de_fazer = 3
        self.rodar_ordens()
        self.assertEqual({"numero": NUMERO, "desfecho": "falhou", "codigo": 3,
                          "motivo": None}, self.desfecho())

    def test_sem_saber_e_nao_sei(self):
        self.codigo_de_fazer = None
        self.rodar_ordens()
        self.assertEqual({"numero": NUMERO, "desfecho": "nao_sei", "codigo": None,
                          "motivo": None}, self.desfecho())

    def test_recusada_diz_o_motivo_e_nao_faz(self):
        self.ordem = dict(self.ordem, servidor="a" * 32)
        self.rodar_ordens()
        self.assertEqual([], self.feitos)
        self.assertEqual({"numero": NUMERO, "desfecho": "recusada", "codigo": None,
                          "motivo": "outro_servidor"}, self.desfecho())

    def test_voltar(self):
        self.ordem = ordem_de_teste("voltar", "grimoire")
        self.rodar_ordens()
        self.assertEqual([(["sudo", "-n", "/usr/local/bin/deploy", "grimoire", "--voltar"],
                           1200)], self.feitos)
        self.assertEqual("feita", self.desfecho()["desfecho"])

    def test_sem_ordem_nao_faz_nada(self):
        self.ordem = None
        self.rodar_ordens()
        self.assertEqual([], self.feitos)
        self.assertEqual(1, len(self.pedidos))

    def test_numero_ilegivel_sai_calado(self):
        """Sem numero nao ha a quem amarrar o desfecho: o DERVS mostra
        `sem_resposta` passado o prazo."""
        self.ordem = dict(self.ordem, numero="zz")
        self.rodar_ordens()
        self.assertEqual([], self.feitos)
        self.assertEqual(1, len(self.pedidos))

    def test_o_painel_fora_do_ar_nao_levanta(self):
        for resposta, esperado in ((0, aj.SEM_REDE), (401, aj.SEM_PAREAMENTO),
                                   (429, aj.OK), (500, aj.SEM_REDE)):
            with self.subTest(resposta):
                self.abrir = lambda m, u, c, t, p, r=resposta: (r, None)
                self.assertEqual(esperado, self.rodar_ordens())
                self.assertEqual([], self.feitos)

    def test_sem_pareamento_nao_busca(self):
        os.unlink(self.pasta_dados / "agente.json")
        self.assertEqual(aj.SEM_PAREAMENTO, self.rodar_ordens())
        self.assertEqual([], self.pedidos)

    def test_o_agora_pode_ser_funcao_ou_numero(self):
        self.assertEqual(aj.OK, self.rodar_ordens(agora=lambda: AGORA))
        self.assertEqual(1, len(self.feitos))

    def test_ordem_vencida_pelo_relogio(self):
        self.rodar_ordens(agora=VENCE + 5)
        self.assertEqual("vencida", self.desfecho()["motivo"])
        self.assertEqual([], self.feitos)


class ONumeroUnico(ComRaizDeOrdens):

    def test_gravado_antes_de_fazer(self):
        vistos = []

        def fazer(argv, prazo):
            vistos.append(self.lidos())
            return 0
        self.rodar_ordens(fazer=fazer)
        self.assertEqual(1, len(vistos))
        self.assertEqual({NUMERO: VENCE}, vistos[0]["numeros"])

    def test_a_segunda_vez_e_repetida_e_nao_faz(self):
        self.rodar_ordens()
        self.pedidos.clear()
        self.rodar_ordens()
        self.assertEqual(1, len(self.feitos))
        self.assertEqual({"numero": NUMERO, "desfecho": "recusada", "codigo": None,
                          "motivo": "repetida"}, self.desfecho())

    def test_poda_o_vencido(self):
        self.numeros(numeros={"a" * 32: AGORA - 1, "b" * 32: AGORA + 50})
        self.rodar_ordens()
        gravado = self.lidos()["numeros"]
        self.assertNotIn("a" * 32, gravado)
        self.assertIn("b" * 32, gravado)
        self.assertIn(NUMERO, gravado)

    def test_o_que_vence_agora_ainda_nao_e_podado(self):
        self.numeros(numeros={"a" * 32: AGORA})
        self.rodar_ordens()
        self.assertIn("a" * 32, self.lidos()["numeros"])

    def test_cheio_de_vivos_recusa_e_nao_descarta_nenhum(self):
        vivos = {"%032x" % i: AGORA + 100 + i for i in range(aj.MAX_NUMEROS)}
        self.numeros(numeros=vivos)
        self.rodar_ordens()
        self.assertEqual([], self.feitos)
        self.assertEqual("cheio", self.desfecho()["motivo"])
        self.assertEqual(vivos, self.lidos()["numeros"])

    def test_cheio_de_vencidos_nao_atrapalha(self):
        mortos = {"%032x" % i: AGORA - 10 - i for i in range(aj.MAX_NUMEROS + 50)}
        self.numeros(numeros=mortos)
        self.rodar_ordens()
        self.assertEqual(1, len(self.feitos))

    def test_199_vivos_ainda_cabe_mais_um(self):
        vivos = {"%032x" % i: AGORA + 100 + i for i in range(aj.MAX_NUMEROS - 1)}
        self.numeros(numeros=vivos)
        self.rodar_ordens()
        self.assertEqual(1, len(self.feitos))

    def test_gravacao_que_falha_recusa_e_nao_faz(self):
        with unittest.mock.patch.object(aj, "_gravar", side_effect=OSError("disco")):
            self.rodar_ordens()
        self.assertEqual([], self.feitos)
        self.assertEqual({"numero": NUMERO, "desfecho": "recusada", "codigo": None,
                          "motivo": "cheio"}, self.desfecho())

    def test_arquivo_de_numeros_estragado_recusa(self):
        """Esquecer os numeros reabriria a repeticao: falha fechada."""
        (self.pasta_dados / "numeros.json").write_text("{estragado")
        self.rodar_ordens()
        self.assertEqual([], self.feitos)
        self.assertEqual("cheio", self.desfecho()["motivo"])

    def test_o_arquivo_de_numeros_so_o_dono_le(self):
        self.rodar_ordens()
        if os.name != "nt":
            self.assertEqual(0o600, (self.pasta_dados / "numeros.json").stat().st_mode & 0o777)

    def test_recusada_nao_gasta_numero(self):
        self.ordem = dict(self.ordem, servidor="a" * 32)
        self.rodar_ordens()
        self.assertFalse((self.pasta_dados / "numeros.json").exists())


class OTetoPorHora(ComRaizDeOrdens):

    def test_a_setima_na_mesma_hora_e_recusada(self):
        self.numeros(feitas=[AGORA - 60 * i for i in range(1, 7)])
        self.rodar_ordens()
        self.assertEqual([], self.feitos)
        self.assertEqual("teto", self.desfecho()["motivo"])

    def test_a_de_61_minutos_atras_nao_conta(self):
        self.numeros(feitas=[AGORA - 3660] + [AGORA - 60 * i for i in range(1, 6)])
        self.rodar_ordens()
        self.assertEqual(1, len(self.feitos))

    def test_seis_na_hora_e_a_ultima_que_passa(self):
        self.numeros(feitas=[AGORA - 60 * i for i in range(1, 6)])
        self.rodar_ordens()
        self.assertEqual(1, len(self.feitos))
        self.assertEqual(6, len(self.lidos()["feitas"]))

    def test_a_feita_e_contada_na_hora_da_gravacao(self):
        self.rodar_ordens()
        self.assertEqual([AGORA], self.lidos()["feitas"])

    def test_o_teto_e_depois_da_repetida(self):
        self.numeros(numeros={NUMERO: VENCE}, feitas=[AGORA - 60 * i for i in range(1, 7)])
        self.rodar_ordens()
        self.assertEqual("repetida", self.desfecho()["motivo"])


# ----------------------------------------------------------------- fazer (C5)

class OFazer(unittest.TestCase):

    def com(self, **retorno):
        fim = unittest.mock.Mock()
        fim.returncode = retorno.get("codigo", 0)
        return unittest.mock.patch.object(aj.subprocess, "run", return_value=fim,
                                          side_effect=retorno.get("erro"))

    def test_o_argv_e_o_ambiente_exatos(self):
        with self.com() as run:
            self.assertEqual(0, aj.fazer(["docker", "restart", "grimoire-web"], 120))
        args, kw = run.call_args
        self.assertEqual(["docker", "restart", "grimoire-web"], args[0])
        self.assertFalse(kw.get("shell", False))
        self.assertIs(aj.subprocess.DEVNULL, kw["stdin"])
        self.assertIs(aj.subprocess.DEVNULL, kw["stdout"])
        self.assertIs(aj.subprocess.DEVNULL, kw["stderr"])
        self.assertEqual({"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"}, kw["env"])
        self.assertEqual(120, kw["timeout"])

    def test_devolve_o_codigo_de_saida(self):
        for codigo in (0, 1, 255):
            with self.com(codigo=codigo):
                self.assertEqual(codigo, aj.fazer(["x"], 5))

    def test_sem_saber_e_none(self):
        for erro in (aj.subprocess.TimeoutExpired("x", 1), OSError("nao existe"),
                     aj.subprocess.SubprocessError("x")):
            with self.subTest(erro=type(erro).__name__), self.com(erro=erro):
                self.assertIsNone(aj.fazer(["x"], 5))

    def test_morto_por_sinal_nao_e_codigo(self):
        with self.com(codigo=-9):
            self.assertIsNone(aj.fazer(["x"], 5))

    def test_a_lista_fechada(self):
        self.assertEqual(("docker", "restart"), aj.ARGV_DO_REINICIO)
        self.assertEqual(("sudo", "-n", "/usr/local/bin/deploy"), aj.ARGV_DA_VOLTA)
        self.assertEqual((120, 1200), (aj.PRAZO_DO_REINICIO, aj.PRAZO_DA_VOLTA))
        self.assertEqual((200, 6), (aj.MAX_NUMEROS, aj.TETO_POR_HORA))

    def test_o_motivo_e_a_lista_fechada(self):
        self.assertEqual(
            ("forma", "outro_servidor", "vencida", "assinatura", "desafio", "origem",
             "aparelho", "bloqueado", "desconhecido", "repetida", "cheio", "teto"),
            aj.MOTIVOS_DA_RECUSA)


# ----------------------------------------------------------------- C11

class OBloqueioEOMesmoDoDervs(unittest.TestCase):

    def test_o_conjunto_e_o_mesmo(self):
        self.assertEqual(frozenset(tarefas.PROJETOS_BLOQUEADOS), aj.PROJETOS_BLOQUEADOS)

    def test_a_resposta_e_a_mesma_numa_tabela_de_variacoes(self):
        for nome in ("Ajudei-Saude", "ajudei_saude", "AJUDEI SAUDE", "ajudei.saude-web",
                     "ajudeisaude", "ajudei-saudex", "grimoire", "", " ajudei-saude ",
                     "ajudei--saude", "ajudei-saude-", "dervs"):
            with self.subTest(nome):
                self.assertEqual(tarefas.projeto_bloqueado(nome), aj._bloqueado(nome))

    def test_o_que_tem_de_ser_bloqueado_e(self):
        for nome in ("Ajudei-Saude", "ajudei_saude", "AJUDEI SAUDE", "ajudei.saude-web"):
            self.assertTrue(aj._bloqueado(nome), nome)
        for nome in ("ajudeisaude", "ajudei-saudex", "grimoire"):
            self.assertFalse(aj._bloqueado(nome), nome)

    def test_nao_texto_nao_e_bloqueado(self):
        self.assertEqual(tarefas.projeto_bloqueado(None), aj._bloqueado(None))
        self.assertFalse(aj._bloqueado(7))


# ----------------------------------------------------------------- C2

class AMedicaoContaOsPedidos(unittest.TestCase):
    ALVO = "https://painel.exemplo.test"

    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="ajudante-medicao-")
        self.addCleanup(shutil.rmtree, self.raiz, True)
        pasta = Path(self.raiz) / "var" / "lib" / "dervs-ajudante"
        pasta.mkdir(parents=True)
        (pasta / "agente.json").write_text(json.dumps({"alvo": self.ALVO, "token": TOKEN}))
        self.enviado = []

    def abrir(self, metodo, url, corpo, token, prazo):
        self.enviado.append(corpo)
        return 200, {"ok": True}

    def rodar(self, argv, prazo):
        return True, ""

    def medir(self):
        self.assertEqual(aj.OK, aj.medir(alvo=self.ALVO, raiz=self.raiz, rodar=self.rodar,
                                         abrir=self.abrir, saida=lambda t: None))
        return self.enviado[-1]

    def escrever(self, texto):
        pasta = Path(self.raiz) / "etc" / "dervs-ajudante"
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "ordens.json").write_text(texto)

    def test_sem_arquivo_a_chave_nao_vai(self):
        self.assertEqual({"versao", "docker_mudo", "servidor", "sistemas", "publicacoes"},
                         set(self.medir()))

    def test_com_arquivo_vai_exatamente_o_contrato(self):
        cfg = config()
        self.escrever(json.dumps(cfg))
        corpo = self.medir()
        self.assertEqual({"versao", "docker_mudo", "servidor", "sistemas", "publicacoes",
                          "ordens"}, set(corpo))
        k1, g = chave_de("publica_k1"), PUBLICA_DE_TESTE
        self.assertEqual({"versao": 1, "ident": SERVIDOR,
                          "chaves": [aj.impressao(*k1), aj.impressao(*g)],
                          "voltaveis": ["grimoire", "dervs"]}, corpo["ordens"])

    def test_nunca_sobe_a_chave_inteira_nem_a_origem(self):
        self.escrever(json.dumps(config()))
        texto = json.dumps(self.medir())
        self.assertNotIn(VETOR_DE_FORA["publica_k1"]["x"], texto)
        self.assertNotIn("rp_id", texto)
        self.assertNotIn("origem", texto)

    def test_torto_nao_vai(self):
        for torto in ("{nao", "[]", json.dumps(dict(config(), versao=2)),
                      json.dumps(dict(config(), ident="zz")),
                      json.dumps(dict(config(), chaves=[["zz", "zz"]])),
                      json.dumps(dict(config(), chaves=[["%064x" % 1, "%064x" % 2]])),
                      json.dumps(dict(config(), voltaveis="x")),
                      json.dumps(dict(config(), voltaveis=["Maiuscula"]))):
            with self.subTest(torto=torto[:50]):
                self.enviado.clear()
                self.escrever(torto)
                self.assertNotIn("ordens", self.medir())

    def test_o_corpo_serializa_em_ascii(self):
        self.escrever(json.dumps(config()))
        json.dumps(self.medir()).encode("ascii")


class OMainDosPedidos(unittest.TestCase):

    def test_ordens_vai_para_a_funcao_certa(self):
        with unittest.mock.patch.object(aj, "ordens", return_value=7) as f:
            self.assertEqual(7, aj.main(["ordens"]))
            f.assert_called_once_with()

    def test_instalar_com_chaves_leva_a_lista(self):
        with unittest.mock.patch.object(aj, "instalar", return_value=7) as f:
            self.assertEqual(7, aj.main(["instalar", "--ordens", "aa.bb,cc.dd"]))
            f.assert_called_once_with(ordens=["aa.bb", "cc.dd"])

    def test_instalar_sem_chaves_chama_sem_nada(self):
        with unittest.mock.patch.object(aj, "instalar", return_value=7) as f:
            aj.main(["instalar"])
            f.assert_called_once_with()

    def test_argumento_estranho_nao_instala(self):
        for argv in (["instalar", "--outra", "x"], ["instalar", "--ordens"],
                     ["instalar", "--ordens", "a", "b"]):
            with self.subTest(argv=argv), \
                    unittest.mock.patch.object(aj, "instalar") as f:
                self.assertEqual(1, aj.main(argv))
                f.assert_not_called()


class OFonteSegueAsLeis(unittest.TestCase):
    def test_ascii_e_uma_marca(self):
        fonte = Path(aj.__file__).read_text(encoding="ascii")
        self.assertTrue(fonte.isascii())
        self.assertEqual(1, sum(1 for l in fonte.splitlines()
                                if l.rstrip().endswith("# DERVS:ALVO")))


if __name__ == "__main__":
    unittest.main()
