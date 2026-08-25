"""Testes da fila que conserta. `python test_fila.py`."""
import os
import tempfile
import unittest
from pathlib import Path

import banco


class BancoTemporario(unittest.TestCase):
    """Cada teste com seu proprio hub.db, jogado fora no fim."""

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.antigo = banco.BANCO
        banco.BANCO = Path(self.pasta.name) / "hub.db"

    def tearDown(self):
        banco.BANCO = self.antigo
        self.pasta.cleanup()


class Enfileirar(BancoTemporario):

    def _pendencia(self, id_="memoria_crlf:dents", projeto="dents",
                   regra="memoria_crlf", gravidade="alta"):
        return {"id": id_, "projeto": projeto, "regra": regra,
                "gravidade": gravidade, "risco": 0}

    def test_insere_o_que_nao_existe(self):
        entraram = banco.enfileirar([self._pendencia()])
        self.assertEqual(entraram, 1)
        self.assertEqual(len(banco.fila_aberta()), 1)

    def test_nao_duplica_o_mesmo_id(self):
        banco.enfileirar([self._pendencia()])
        entraram = banco.enfileirar([self._pendencia()])
        self.assertEqual(entraram, 0)
        self.assertEqual(len(banco.fila_aberta()), 1)

    def test_item_nasce_esperando_com_zero_tentativas(self):
        banco.enfileirar([self._pendencia()])
        item = banco.fila_aberta()[0]
        self.assertEqual(item["estado"], "esperando")
        self.assertEqual(item["tentativas"], 0)
        self.assertEqual(item["custo_usd"], 0.0)

    def test_terminado_em_ok_sai_da_fila_aberta(self):
        banco.enfileirar([self._pendencia()])
        banco.marcar_fila("memoria_crlf:dents", estado="ok",
                          terminado_em="2026-08-25T12:00:00+00:00")
        self.assertEqual(banco.fila_aberta(), [])

    def test_falha_continua_na_fila_aberta(self):
        banco.enfileirar([self._pendencia()])
        banco.marcar_fila("memoria_crlf:dents", estado="falha",
                          terminado_em="2026-08-25T12:00:00+00:00")
        self.assertEqual(len(banco.fila_aberta()), 1)


class GastoDoDia(BancoTemporario):

    def _terminar(self, id_, custo, quando):
        banco.enfileirar([{"id": id_, "projeto": "x", "regra": "env_drift",
                           "gravidade": "media", "risco": 0}])
        banco.marcar_fila(id_, estado="ok", custo_usd=custo, terminado_em=quando)

    def test_dia_sem_nada_e_zero(self):
        self.assertEqual(banco.gasto_do_dia("2026-08-25"), 0.0)

    def test_soma_so_o_dia_pedido(self):
        self._terminar("a:1", 1.50, "2026-08-25T10:00:00+00:00")
        self._terminar("b:1", 0.50, "2026-08-25T18:00:00+00:00")
        self._terminar("c:1", 9.99, "2026-08-24T10:00:00+00:00")
        self.assertAlmostEqual(banco.gasto_do_dia("2026-08-25"), 2.00, places=6)

    def test_item_nao_terminado_nao_conta(self):
        banco.enfileirar([{"id": "d:1", "projeto": "x", "regra": "env_drift",
                           "gravidade": "media", "risco": 0}])
        banco.marcar_fila("d:1", estado="rodando", custo_usd=3.0)
        self.assertEqual(banco.gasto_do_dia("2026-08-25"), 0.0)


import fila


class Elegibilidade(unittest.TestCase):

    def _p(self, regra, projeto="dents"):
        return {"id": "%s:%s" % (regra, projeto), "regra": regra,
                "projeto": projeto, "gravidade": "media", "risco": 0}

    def test_memoria_crlf_vai_pelo_trilho_mecanico(self):
        self.assertEqual(fila.trilho_de(self._p("memoria_crlf")), "mecanico")

    def test_env_drift_vai_pelo_claude(self):
        self.assertEqual(fila.trilho_de(self._p("env_drift")), "claude")

    def test_dependencia_insegura_vai_pelo_claude(self):
        self.assertEqual(fila.trilho_de(self._p("dependencia_insegura")), "claude")

    def test_ci_vermelha_fica_de_fora(self):
        self.assertEqual(fila.trilho_de(self._p("ci_vermelha")), "")

    def test_grafo_velho_fica_de_fora(self):
        self.assertEqual(fila.trilho_de(self._p("grafo_velho")), "")

    def test_sem_remoto_fica_de_fora(self):
        self.assertEqual(fila.trilho_de(self._p("sem_remoto")), "")

    def test_projeto_bloqueado_nao_entra_nem_com_regra_aceita(self):
        bloqueado = sorted(fila.execucao.PROJETOS_BLOQUEADOS)[0]
        self.assertEqual(fila.trilho_de(self._p("memoria_crlf", bloqueado)), "")

    def test_bloqueio_ignora_caixa_alta(self):
        bloqueado = sorted(fila.execucao.PROJETOS_BLOQUEADOS)[0].upper()
        self.assertEqual(fila.trilho_de(self._p("memoria_crlf", bloqueado)), "")

    def test_pendencia_sem_projeto_nao_tem_onde_agir(self):
        self.assertEqual(fila.trilho_de(self._p("memoria_crlf", "")), "")

    def test_elegiveis_carimba_o_trilho(self):
        saida = fila.elegiveis([self._p("memoria_crlf"), self._p("ci_vermelha")])
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["trilho"], "mecanico")

    def test_elegiveis_nao_altera_a_lista_recebida(self):
        entrada = [self._p("memoria_crlf")]
        fila.elegiveis(entrada)
        self.assertNotIn("trilho", entrada[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
