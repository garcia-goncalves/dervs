# -*- coding: utf-8 -*-
"""Testes da cortina (etapa 9).

A CORTINA NAO E A FECHADURA. Seis digitos sao um milhao de combinacoes; quem
protege o dado e o login do GitHub mais a lista de contas em `credencial`. O
que este arquivo cobra e que a cortina nao seja PIOR do que aquilo que ela
promete ser:

  1. O NUMERO NUNCA FICA GUARDADO. So a impressao digital, por scrypt.
  2. FALHA FECHADA. Sem combinacao gravada, ninguem passa.
  3. O SELO NAO SE FALSIFICA nem sobrevive ao prazo, e lixo nao derruba.
  4. O TETO E POR ORIGEM. Cinco chutes de um estranho nao trancam a casa
     inteira — foi exatamente esse defeito que a etapa 8 removeu da tabela de
     pareamento, e repeti-lo aqui seria reintroduzi-lo pela porta da frente.

    python test_cortina.py
"""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path

# Chave fixa do cofre e ambiente local: o teste nao pode depender de arquivo no
# disco do dono nem gravar um. Tem de vir ANTES de importar banco.
os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco    # noqa: E402
import cortina  # noqa: E402


class Combinacao(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.con = banco.conectar(str(Path(self.dir.name) / "hub.db"))
        self.addCleanup(self.con.close)

    def test_gera_seis_digitos_e_so_na_primeira_vez(self):
        numero = cortina.garantir_combinacao(self.con)
        self.assertRegex(numero, r"^\d{6}$")
        self.assertIsNone(cortina.garantir_combinacao(self.con))

    def test_o_numero_nao_fica_no_banco(self):
        cortina.trocar("314159", self.con)
        guardado = cortina.combinacao_atual(self.con)
        self.assertTrue(guardado)
        self.assertNotIn("314159", guardado)
        self.assertTrue(guardado.startswith("scrypt$"))

    def test_confere_o_certo_e_recusa_o_errado(self):
        cortina.trocar("314159", self.con)
        self.assertTrue(cortina.conferir("314159", self.con))
        self.assertFalse(cortina.conferir("314158", self.con))
        self.assertFalse(cortina.conferir("", self.con))
        self.assertFalse(cortina.conferir(None, self.con))

    def test_sem_combinacao_gravada_ninguem_entra(self):
        """Falha FECHADA. Banco novo, cortina nao gerada, nada passa."""
        self.assertFalse(cortina.combinacao_atual(self.con))
        self.assertFalse(cortina.conferir("000000", self.con))
        self.assertFalse(cortina.conferir("", self.con))

    def test_trocar_invalida_a_anterior(self):
        antigo = cortina.garantir_combinacao(self.con)
        cortina.trocar("271828", self.con)
        self.assertFalse(cortina.conferir(antigo, self.con))
        self.assertTrue(cortina.conferir("271828", self.con))

    def test_zero_a_esquerda_sobrevive(self):
        """`000123` nao pode virar 123 no caminho: seria um digito a menos de
        espaco de busca por cada zero perdido."""
        cortina.trocar("000123", self.con)
        self.assertTrue(cortina.conferir("000123", self.con))
        self.assertFalse(cortina.conferir("123", self.con))

    def test_combinacao_que_nao_e_seis_digitos_e_recusada_na_troca(self):
        for ruim in ("", "12345", "1234567", "12345a", "abcdef", None):
            with self.assertRaises(ValueError, msg=repr(ruim)):
                cortina.trocar(ruim, self.con)

    def test_no_ambiente_local_a_combinacao_e_a_documentada(self):
        """Local e de mentira, e senha de teste nao e segredo: e dado de teste,
        escrito no README para o dono nao ter de decorar nada aqui."""
        self.assertEqual(cortina.garantir_combinacao(self.con),
                         cortina.COMBINACAO_LOCAL)


class Selo(unittest.TestCase):
    CHAVE = b"x" * 32

    def test_vale_dentro_do_prazo(self):
        s = cortina.selar(1000.0, self.CHAVE, minutos=10)
        self.assertTrue(cortina.selo_valido(s, 1000.0, self.CHAVE))
        self.assertTrue(cortina.selo_valido(s, 1000.0 + 599, self.CHAVE))

    def test_vence(self):
        s = cortina.selar(1000.0, self.CHAVE, minutos=10)
        self.assertFalse(cortina.selo_valido(s, 1000.0 + 601, self.CHAVE))

    def test_de_outra_chave_nao_vale(self):
        s = cortina.selar(1000.0, self.CHAVE)
        self.assertFalse(cortina.selo_valido(s, 1000.0, b"y" * 32))

    def test_prazo_esticado_a_mao_nao_vale(self):
        """Trocar o numero sem refazer a assinatura e a tentativa obvia."""
        s = cortina.selar(1000.0, self.CHAVE, minutos=10)
        _, _, assinatura = s.partition(".")
        forjado = "99999999999." + assinatura
        self.assertFalse(cortina.selo_valido(forjado, 1000.0, self.CHAVE))

    def test_lixo_nao_derruba(self):
        for ruim in ("", ".", "abc", "1000.", ".deadbeef", "-1.x", "x" * 5000,
                     None):
            self.assertFalse(cortina.selo_valido(ruim, 1000.0, self.CHAVE),
                             repr(ruim))


class Teto(unittest.TestCase):
    def setUp(self):
        cortina.zerar_tentativas()
        self.addCleanup(cortina.zerar_tentativas)

    def test_a_sexta_tentativa_nao_passa(self):
        for _ in range(cortina.TETO):
            self.assertTrue(cortina.registrar_tentativa("10.0.0.1", 100.0))
        self.assertFalse(cortina.registrar_tentativa("10.0.0.1", 100.0))

    def test_uma_origem_nao_derruba_a_outra(self):
        """O defeito que a etapa 8 removeu da tabela de pareamento: contador
        global deixava um estranho matar o acesso de todo mundo."""
        for _ in range(cortina.TETO):
            cortina.registrar_tentativa("10.0.0.1", 100.0)
        self.assertFalse(cortina.registrar_tentativa("10.0.0.1", 100.0))
        self.assertTrue(cortina.registrar_tentativa("10.0.0.2", 100.0))

    def test_a_janela_vira(self):
        for _ in range(cortina.TETO):
            cortina.registrar_tentativa("10.0.0.1", 100.0)
        self.assertTrue(
            cortina.registrar_tentativa("10.0.0.1", 100.0 + cortina.JANELA + 1))

    def test_a_janela_desliza_uma_vaga_por_vez(self):
        """A vaga volta quando o chute que a ocupava vence, e so ela.

        Sustentado, isso da cinco chutes a cada quinze minutos — cerca de 480
        por dia. Varrer o milhao de combinacoes assim levaria uns dois mil dias.
        """
        for i in range(cortina.TETO):
            cortina.registrar_tentativa("10.0.0.1", 100.0 + i)
        # Um instante ANTES de o primeiro chute vencer: ainda travado.
        self.assertFalse(
            cortina.registrar_tentativa("10.0.0.1", 100.0 + cortina.JANELA - 1))
        # O primeiro venceu: uma vaga, nao cinco.
        agora_s = 100.0 + cortina.JANELA
        self.assertTrue(cortina.registrar_tentativa("10.0.0.1", agora_s))
        self.assertFalse(cortina.registrar_tentativa("10.0.0.1", agora_s))

    def test_conferir_e_anotar_acontecem_SOB_O_MESMO_LOCK(self):
        """O achado da revisao: eram duas funcoes, cada uma pegando o lock por
        conta propria. N pedidos simultaneos liam todos "ainda cabe" antes de
        qualquer um anotar, e o teto de cinco virava "o quanto eu paralelizo".

        O servidor e ThreadingHTTPServer, entao os N chegam mesmo. Aqui as
        threads sao soltas de uma vez por uma barreira, e o total de "pode"
        NUNCA pode passar do teto.
        """
        largada = threading.Barrier(24)
        passaram = []
        trava = threading.Lock()

        def bater():
            largada.wait()
            if cortina.registrar_tentativa("10.9.9.9", 100.0):
                with trava:
                    passaram.append(1)

        linhas = [threading.Thread(target=bater) for _ in range(24)]
        for t in linhas:
            t.start()
        for t in linhas:
            t.join()
        self.assertEqual(len(passaram), cortina.TETO)

    def test_origem_antiga_e_esquecida(self):
        """Sem poda, o dicionario cresce por IP ate o processo morrer."""
        cortina.registrar_tentativa("10.0.0.1", 100.0)
        cortina.registrar_tentativa("10.0.0.2", 100.0 + cortina.JANELA * 3)
        self.assertNotIn("10.0.0.1", cortina.origens_lembradas())
        self.assertIn("10.0.0.2", cortina.origens_lembradas())


class CadaPortaTemAPropriaFila(unittest.TestCase):
    """Errar numa porta nao pode gastar o teto da outra.

    Em 26/08/2026 o dono ficou preso do lado de fora da propria maquina com a
    chave certa na mao, porque um teto compartilhado tinha estourado. Com as
    portas de entrada sao quatro caminhos; se todos contassem na mesma fila,
    quem errasse o codigo de recuperacao trancaria tambem a chave de acesso, e
    a tela nao teria como explicar isso a ninguem.
    """

    def setUp(self):
        cortina.zerar_tentativas()
        self.addCleanup(cortina.zerar_tentativas)

    def test_estourar_uma_porta_nao_fecha_a_outra(self):
        for _ in range(cortina.TETO):
            cortina.registrar_tentativa("10.0.0.1", 100.0, balcao="codigo")
        self.assertFalse(cortina.registrar_tentativa("10.0.0.1", 100.0,
                                                     balcao="codigo"))
        self.assertTrue(cortina.registrar_tentativa("10.0.0.1", 100.0,
                                                    balcao="passkey"))

    def test_a_cortina_continua_sendo_o_balcao_padrao(self):
        """Chamada antiga, sem `balcao`, tem de cair na mesma fila de sempre."""
        for _ in range(cortina.TETO):
            cortina.registrar_tentativa("10.0.0.1", 100.0)
        self.assertFalse(cortina.registrar_tentativa("10.0.0.1", 100.0,
                                                     balcao="cortina"))

    def test_a_origem_continua_separando_dentro_da_porta(self):
        for _ in range(cortina.TETO):
            cortina.registrar_tentativa("10.0.0.1", 100.0, balcao="passkey")
        self.assertTrue(cortina.registrar_tentativa("10.0.0.2", 100.0,
                                                    balcao="passkey"))

    def test_a_poda_limpa_as_duas_filas(self):
        cortina.registrar_tentativa("10.0.0.1", 100.0, balcao="passkey")
        cortina.registrar_tentativa("10.0.0.1", 100.0, balcao="codigo")
        cortina.registrar_tentativa("10.0.0.9", 100.0 + cortina.JANELA * 3)
        self.assertEqual(cortina.origens_lembradas(), {"10.0.0.9"})

    def test_string_longa_nao_paga_scrypt(self):
        """`conferir` recebia qualquer coisa ate 1 KiB e pagava um scrypt de
        ~16 MiB por ela. A forma e fixa e conhecida: barra-se pela forma."""
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        con = banco.conectar(str(Path(d.name) / "hub.db"))
        self.addCleanup(con.close)
        cortina.trocar("314159", con)
        for ruim in ("9" * 5000, "31415", "3141599", "abcdef", "31415a"):
            self.assertFalse(cortina.conferir(ruim, con), ruim[:10])



class LimitesPorAmbiente(unittest.TestCase):
    """Local e servidor nao merecem a mesma regra, e a diferenca e testavel.

    O que motivou: em 26/08 o dono foi barrado na propria maquina pelo teto de
    5 tentativas, com a chave certa na mao, e o selo de 10 minutos o mandava
    digitar de novo a cada intervalo. Local e dado de mentira atras de
    127.0.0.1 — apertar ali nao protege ninguem e afasta quem trabalha.
    """

    def test_no_servidor_a_regra_e_apertada(self):
        self.assertEqual(cortina.limites(False), (5, 10))

    def test_no_local_a_regra_afrouxa(self):
        teto, minutos = cortina.limites(True)
        self.assertGreater(teto, 5)
        self.assertGreaterEqual(minutos, 12 * 60)

    def test_o_modulo_usa_a_funcao_e_nao_um_numero_solto(self):
        """Sem isto, alguem afrouxa o local e afrouxa o servidor junto."""
        self.assertIn((cortina.TETO, cortina.MINUTOS_DO_SELO),
                      (cortina.limites(True), cortina.limites(False)))

if __name__ == "__main__":
    unittest.main(verbosity=2)
