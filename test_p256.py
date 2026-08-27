# -*- coding: utf-8 -*-
"""A aritmetica da curva P-256, provada contra vetor publicado.

POR QUE ISTO EXISTE, e por que se testa deste jeito: `p256.py` e a unica
matematica de criptografia escrita a mao neste repositorio. A decisao esta
declarada em docs/superpowers/specs/2026-08-26-portas-de-entrada-design.md — o
projeto nao adota dependencia externa, e conferir uma assinatura ECDSA e a
unica coisa que o Python nao traz pronto.

Codigo de criptografia escrito a mao que so foi testado com dado que ele mesmo
produziu NAO esta testado: prova que concorda consigo, nao que esta certo. Por
isso todo vetor abaixo vem de FORA — RFC 6979, secao A.2.5 (curva P-256, resumo
SHA-256), o mesmo par de valores reproduzido pelo NIST.

E ha uma trava contra o erro mais provavel deste arquivo, que e eu digitar um
numero errado. Vetor com digito trocado faz o teste FALHAR, e falha de
conferencia sozinha nao diz se o culpado foi o vetor ou a conta. Entao
`test_a_chave_publica_nasce_da_privada` confere o PAR de chaves por um caminho
independente da assinatura: se aquele passa, X e Y estao certos, e uma falha na
assinatura acusa r/s ou a conta.
"""
from __future__ import annotations

import hashlib
import unittest

import p256


# RFC 6979, A.2.5 — curva P-256.
PRIVADA = 0xC9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721
PUBLICA_X = 0x60FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB6
PUBLICA_Y = 0x7903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299
PUBLICA = (PUBLICA_X, PUBLICA_Y)

# Mensagem "sample", resumo SHA-256.
SAMPLE_R = 0xEFD48B2AACB6A8FD1140DD9CD45E81D69D2C877B56AAF991C34D0EA84EAF3716
SAMPLE_S = 0xF7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8

# Mensagem "test", resumo SHA-256.
TEST_R = 0xF1ABB023518351CD71D881567B1EA663ED3EFCF6C5132B354F28D3B0B7D38367
TEST_S = 0x019F4113742A2B14BD25926B49C649155F267E60D3814B4C0CC84250E46F0083


def resumo(texto):
    return hashlib.sha256(texto.encode("ascii")).digest()


class OsNumerosDaCurva(unittest.TestCase):
    """Antes de qualquer conta, os parametros publicados da P-256."""

    def test_o_primo_e_o_da_norma(self):
        self.assertEqual(
            p256.P,
            0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF)

    def test_a_ordem_e_a_da_norma(self):
        self.assertEqual(
            p256.N,
            0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551)

    def test_a_curva_fecha_no_gerador(self):
        """y^2 == x^3 + ax + b, no ponto de partida publicado."""
        x, y = p256.G
        self.assertEqual((y * y) % p256.P,
                         (x * x * x + p256.A * x + p256.B) % p256.P)

    def test_a_ordem_leva_o_gerador_ao_infinito(self):
        """N*G e o elemento neutro. E a definicao de N, e trava de digitacao."""
        self.assertIsNone(p256.multiplicar(p256.N, p256.G))


class AChaveDeTeste(unittest.TestCase):
    """Conferencia do PAR de chaves por caminho independente da assinatura."""

    def test_a_chave_publica_esta_na_curva(self):
        self.assertTrue(p256.ponto_valido(PUBLICA))

    def test_a_chave_publica_nasce_da_privada(self):
        """Se este passa, X e Y do vetor estao certos e a conta tambem."""
        self.assertEqual(p256.multiplicar(PRIVADA, p256.G), PUBLICA)


class OVetorDaNorma(unittest.TestCase):

    def test_confere_a_assinatura_de_sample(self):
        self.assertTrue(p256.conferir(PUBLICA, resumo("sample"),
                                      SAMPLE_R, SAMPLE_S))

    def test_confere_a_assinatura_de_test(self):
        self.assertTrue(p256.conferir(PUBLICA, resumo("test"),
                                      TEST_R, TEST_S))

    def test_a_assinatura_de_sample_nao_vale_para_test(self):
        """A trava que pega implementacao que devolve True para tudo."""
        self.assertFalse(p256.conferir(PUBLICA, resumo("test"),
                                       SAMPLE_R, SAMPLE_S))


class OQueTemDeSerRecusado(unittest.TestCase):
    """Cada recusa aqui e um ataque conhecido, nao um capricho de cobertura."""

    def test_mensagem_trocada(self):
        self.assertFalse(p256.conferir(PUBLICA, resumo("sampl3"),
                                       SAMPLE_R, SAMPLE_S))

    def test_r_adulterado_em_um_bit(self):
        self.assertFalse(p256.conferir(PUBLICA, resumo("sample"),
                                       SAMPLE_R ^ 1, SAMPLE_S))

    def test_s_adulterado_em_um_bit(self):
        self.assertFalse(p256.conferir(PUBLICA, resumo("sample"),
                                       SAMPLE_R, SAMPLE_S ^ 1))

    def test_r_zero(self):
        """r = 0 e s = 0 fazem a conta degenerar; a norma manda recusar."""
        self.assertFalse(p256.conferir(PUBLICA, resumo("sample"), 0, SAMPLE_S))

    def test_s_zero(self):
        self.assertFalse(p256.conferir(PUBLICA, resumo("sample"), SAMPLE_R, 0))

    def test_r_igual_a_ordem(self):
        self.assertFalse(p256.conferir(PUBLICA, resumo("sample"),
                                       p256.N, SAMPLE_S))

    def test_s_acima_da_ordem(self):
        self.assertFalse(p256.conferir(PUBLICA, resumo("sample"),
                                       SAMPLE_R, p256.N + SAMPLE_S))

    def test_r_negativo(self):
        self.assertFalse(p256.conferir(PUBLICA, resumo("sample"),
                                       -SAMPLE_R, SAMPLE_S))

    def test_chave_publica_fora_da_curva(self):
        """Ponto invalido e ataque, nao acidente. Recusar e a regra da norma."""
        self.assertFalse(p256.conferir((PUBLICA_X, PUBLICA_Y ^ 1),
                                       resumo("sample"), SAMPLE_R, SAMPLE_S))

    def test_chave_publica_no_infinito(self):
        self.assertFalse(p256.conferir(None, resumo("sample"),
                                       SAMPLE_R, SAMPLE_S))

    def test_resumo_que_nao_e_bytes(self):
        self.assertFalse(p256.conferir(PUBLICA, "sample", SAMPLE_R, SAMPLE_S))


class OPontoEmBytes(unittest.TestCase):
    """O formato que o navegador manda: 0x04, X e Y, 32 bytes cada."""

    def test_le_o_formato_nao_comprimido(self):
        cru = b"\x04" + PUBLICA_X.to_bytes(32, "big") + PUBLICA_Y.to_bytes(32, "big")
        self.assertEqual(p256.ponto_de_bytes(cru), PUBLICA)

    def test_recusa_ponto_comprimido(self):
        """Nao implementamos descompressao; recusar e melhor que fingir."""
        self.assertIsNone(p256.ponto_de_bytes(
            b"\x02" + PUBLICA_X.to_bytes(32, "big")))

    def test_recusa_tamanho_errado(self):
        self.assertIsNone(p256.ponto_de_bytes(b"\x04" + b"\x00" * 63))

    def test_recusa_vazio(self):
        self.assertIsNone(p256.ponto_de_bytes(b""))

    def test_recusa_ponto_fora_da_curva(self):
        cru = b"\x04" + PUBLICA_X.to_bytes(32, "big") + (
            PUBLICA_Y ^ 1).to_bytes(32, "big")
        self.assertIsNone(p256.ponto_de_bytes(cru))


class AAssinaturaEmDer(unittest.TestCase):
    """O navegador entrega r e s embrulhados em DER. Desembrulhar e parser.

    Parser de dado que vem de fora e superficie de ataque, e a regra da casa e
    tratar como hostil. Cada teste aqui e uma forma de DER torto.
    """

    def montar(self, r, s):
        def inteiro(v):
            b = v.to_bytes((v.bit_length() + 8) // 8 or 1, "big")
            return b"\x02" + bytes([len(b)]) + b
        corpo = inteiro(r) + inteiro(s)
        return b"\x30" + bytes([len(corpo)]) + corpo

    def test_le_o_par_de_volta(self):
        self.assertEqual(p256.assinatura_de_der(self.montar(SAMPLE_R, SAMPLE_S)),
                         (SAMPLE_R, SAMPLE_S))

    def test_le_valores_pequenos(self):
        self.assertEqual(p256.assinatura_de_der(self.montar(1, 2)), (1, 2))

    def test_recusa_vazio(self):
        self.assertIsNone(p256.assinatura_de_der(b""))

    def test_recusa_sem_sequencia(self):
        torto = self.montar(SAMPLE_R, SAMPLE_S)
        self.assertIsNone(p256.assinatura_de_der(b"\x31" + torto[1:]))

    def test_recusa_comprimento_que_nao_bate_com_o_corpo(self):
        torto = self.montar(SAMPLE_R, SAMPLE_S)
        self.assertIsNone(p256.assinatura_de_der(torto[:1] + b"\x7f" + torto[2:]))

    def test_recusa_sobra_no_fim(self):
        """Bytes depois da estrutura sao um pedido de maleabilidade."""
        self.assertIsNone(p256.assinatura_de_der(
            self.montar(SAMPLE_R, SAMPLE_S) + b"\x00"))

    def test_recusa_inteiro_negativo(self):
        """DER poe um zero na frente quando o primeiro bit e 1. Sem ele, negativo."""
        corpo = b"\x02\x01\xff" + b"\x02\x01\x02"
        self.assertIsNone(p256.assinatura_de_der(
            b"\x30" + bytes([len(corpo)]) + corpo))

    def test_recusa_inteiro_de_comprimento_zero(self):
        corpo = b"\x02\x00" + b"\x02\x01\x02"
        self.assertIsNone(p256.assinatura_de_der(
            b"\x30" + bytes([len(corpo)]) + corpo))

    def test_recusa_gigante(self):
        """Sem teto, um DER de 1 MiB vira inteiro de 1 MiB e a conta trava."""
        self.assertIsNone(p256.assinatura_de_der(self.montar(
            int.from_bytes(b"\x01" * 200, "big"), SAMPLE_S)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
