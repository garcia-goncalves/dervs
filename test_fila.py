"""Testes da fila que conserta. `python test_fila.py`."""
import os
import tempfile
import unittest
from pathlib import Path

import banco
import execucao


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


class TetoDiario(unittest.TestCase):

    def test_sem_gasto_cabe(self):
        self.assertTrue(fila.cabe_no_teto(0.0))

    def test_vespera_do_teto_ainda_cabe(self):
        quase = (fila.TETO_DIARIO_BRL - 0.01) / execucao.USD_BRL
        self.assertTrue(fila.cabe_no_teto(quase))

    def test_exatamente_no_teto_nao_cabe(self):
        no_ponto = fila.TETO_DIARIO_BRL / execucao.USD_BRL
        self.assertFalse(fila.cabe_no_teto(no_ponto))

    def test_passou_do_teto_nao_cabe(self):
        self.assertFalse(fila.cabe_no_teto(fila.TETO_DIARIO_BRL))

    def test_quanto_falta_nunca_e_negativo(self):
        self.assertEqual(fila.quanto_falta(999.0), 0.0)

    def test_quanto_falta_sem_gasto_e_o_teto_inteiro(self):
        self.assertAlmostEqual(fila.quanto_falta(0.0), fila.TETO_DIARIO_BRL, places=2)

    def test_hoje_local_tem_formato_de_data(self):
        hoje = fila.hoje_local()
        self.assertEqual(len(hoje), 10)
        self.assertEqual(hoje[4], "-")
        self.assertEqual(hoje[7], "-")


class AntiLaco(unittest.TestCase):

    def _item(self, **campos):
        base = {"id": "env_drift:dents", "projeto": "dents", "regra": "env_drift",
                "gravidade": "media", "risco": 0, "trilho": "claude",
                "estado": "esperando", "tentativas": 0, "terminado_em": None}
        base.update(campos)
        return base

    def test_primeira_tentativa_pode(self):
        self.assertTrue(fila.pode_tentar(self._item(tentativas=0), "2026-08-25"))

    def test_segunda_tentativa_pode(self):
        self.assertTrue(fila.pode_tentar(self._item(tentativas=1), "2026-08-25"))

    def test_terceira_tentativa_nao_pode(self):
        self.assertFalse(fila.pode_tentar(self._item(tentativas=2), "2026-08-25"))

    def test_falha_de_hoje_nao_volta_hoje(self):
        item = self._item(estado="falha", tentativas=1,
                          terminado_em="2026-08-25T14:00:00+00:00")
        self.assertFalse(fila.pode_tentar(item, "2026-08-25"))

    def test_falha_de_ontem_volta_hoje(self):
        item = self._item(estado="falha", tentativas=1,
                          terminado_em="2026-08-24T14:00:00+00:00")
        self.assertTrue(fila.pode_tentar(item, "2026-08-25"))


class Proximo(unittest.TestCase):

    def _item(self, id_, gravidade="media", risco=0, **campos):
        base = {"id": id_, "projeto": id_.split(":")[-1], "regra": "env_drift",
                "gravidade": gravidade, "risco": risco, "trilho": "claude",
                "estado": "esperando", "tentativas": 0, "terminado_em": None}
        base.update(campos)
        return base

    def test_fila_vazia_devolve_nada(self):
        self.assertIsNone(fila.proximo([], 0.0, "2026-08-25"))

    def test_grave_vem_antes(self):
        itens = [self._item("a:zz", "baixa"), self._item("b:aa", "alta")]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["id"], "b:aa")

    def test_dentro_da_gravidade_o_risco_desempata(self):
        itens = [self._item("a:aa", "alta", risco=0),
                 self._item("b:zz", "alta", risco=100)]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["id"], "b:zz")

    def test_risco_nao_atravessa_gravidade(self):
        itens = [self._item("a:aa", "media", risco=100),
                 self._item("b:zz", "alta", risco=0)]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["id"], "b:zz")

    def test_empate_total_ordena_pelo_projeto(self):
        itens = [self._item("a:zz", "alta"), self._item("b:aa", "alta")]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["projeto"], "aa")

    def test_teto_estourado_devolve_nada_mesmo_com_fila_cheia(self):
        itens = [self._item("a:aa", "alta")]
        self.assertIsNone(fila.proximo(itens, 999.0, "2026-08-25"))

    def test_item_rodando_nao_e_escolhido_de_novo(self):
        itens = [self._item("a:aa", "alta", estado="rodando")]
        self.assertIsNone(fila.proximo(itens, 0.0, "2026-08-25"))

    def test_item_esgotado_e_pulado_e_o_seguinte_entra(self):
        itens = [self._item("a:aa", "alta", tentativas=2),
                 self._item("b:bb", "baixa")]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["id"], "b:bb")


class TesteApagado(unittest.TestCase):

    def test_diff_limpo_passa(self):
        diff = ("diff --git a/regras.py b/regras.py\n"
                "--- a/regras.py\n+++ b/regras.py\n"
                "@@ -1,2 +1,2 @@\n-antigo\n+novo\n")
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_apagar_test_py_reprova(self):
        diff = ("diff --git a/test_regras.py b/test_regras.py\n"
                "deleted file mode 100644\n"
                "--- a/test_regras.py\n+++ /dev/null\n")
        self.assertIn("test_regras.py", fila.diff_mexeu_em_teste(diff))

    def test_apagar_spec_ts_reprova(self):
        diff = ("--- a/src/login.spec.ts\n+++ /dev/null\n")
        self.assertIn("login.spec.ts", fila.diff_mexeu_em_teste(diff))

    def test_apagar_dot_test_js_reprova(self):
        diff = ("--- a/src/soma.test.js\n+++ /dev/null\n")
        self.assertIn("soma.test.js", fila.diff_mexeu_em_teste(diff))

    def test_apagar_arquivo_comum_passa(self):
        diff = ("--- a/README.md\n+++ /dev/null\n")
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_adicionar_arquivo_de_teste_passa(self):
        diff = ("--- /dev/null\n+++ b/test_novo.py\n+def test_x(): pass\n")
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_unittest_skip_reprova(self):
        diff = "+    @unittest.skip('quebrado')\n"
        self.assertIn("unittest.skip", fila.diff_mexeu_em_teste(diff))

    def test_pytest_mark_skip_reprova(self):
        diff = "+@pytest.mark.skip\n"
        self.assertIn("pytest.mark.skip", fila.diff_mexeu_em_teste(diff))

    def test_it_skip_reprova(self):
        diff = "+  it.skip('faz coisa', () => {})\n"
        self.assertIn("it.skip(", fila.diff_mexeu_em_teste(diff))

    def test_xit_reprova(self):
        diff = "+  xit('faz coisa', () => {})\n"
        self.assertIn("xit(", fila.diff_mexeu_em_teste(diff))

    def test_skip_em_linha_REMOVIDA_passa(self):
        """Tirar um skip e o oposto de burlar: e religar o teste."""
        diff = "-    @unittest.skip('quebrado')\n"
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_cabecalho_mais_mais_mais_nao_e_linha_adicionada(self):
        diff = "+++ b/it.skip(coisa).py\n"
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_diff_vazio_passa(self):
        self.assertEqual(fila.diff_mexeu_em_teste(""), "")
        self.assertEqual(fila.diff_mexeu_em_teste(None), "")


class SegredoNoEnvExample(unittest.TestCase):

    def test_chave_vazia_passa(self):
        self.assertEqual(fila.env_example_tem_valor("+DATABASE_URL=\n"), "")

    def test_chave_com_valor_reprova(self):
        motivo = fila.env_example_tem_valor("+DATABASE_URL=postgres://a:b@c/d\n")
        self.assertIn("DATABASE_URL", motivo)

    def test_espaco_reservado_tambem_reprova(self):
        self.assertIn("API_KEY", fila.env_example_tem_valor("+API_KEY=troque-aqui\n"))

    def test_comentario_passa(self):
        self.assertEqual(fila.env_example_tem_valor("+# banco de dados\n"), "")

    def test_linha_em_branco_passa(self):
        self.assertEqual(fila.env_example_tem_valor("+\n"), "")

    def test_linha_removida_nao_e_avaliada(self):
        self.assertEqual(fila.env_example_tem_valor("-SENHA=abc123\n"), "")

    def test_cabecalho_do_diff_nao_e_avaliado(self):
        self.assertEqual(fila.env_example_tem_valor("+++ b/.env.example\n"), "")

    def test_linha_sem_igual_passa(self):
        self.assertEqual(fila.env_example_tem_valor("+apenas texto\n"), "")


class Reprovar(unittest.TestCase):

    def test_env_drift_checa_as_duas_travas(self):
        self.assertIn("DATABASE_URL",
                      fila.reprovar("+DATABASE_URL=segredo\n", "env_drift"))

    def test_dependencia_nao_checa_a_trava_do_env(self):
        """So o env_drift toca o arquivo de exemplo. Cobrar dos outros seria ruido."""
        self.assertEqual(fila.reprovar("+DATABASE_URL=segredo\n",
                                       "dependencia_insegura"), "")

    def test_trava_do_teste_vale_para_toda_regra(self):
        diff = "--- a/test_x.py\n+++ /dev/null\n"
        self.assertIn("test_x.py", fila.reprovar(diff, "dependencia_insegura"))
        self.assertIn("test_x.py", fila.reprovar(diff, "env_drift"))

    def test_diff_limpo_aprova(self):
        self.assertEqual(fila.reprovar("+print('oi')\n", "env_drift"), "")


class Lacar(BancoTemporario):

    def _pendencia(self, regra="memoria_crlf", projeto="dents", gravidade="alta"):
        return {"id": "%s:%s" % (regra, projeto), "regra": regra,
                "projeto": projeto, "gravidade": gravidade, "risco": 0}

    def _executores(self, resultado=(True, 0.0, "", "")):
        self.chamadas = []

        def fingir(item):
            self.chamadas.append(item["id"])
            return resultado

        return {"mecanico": fingir, "claude": fingir}

    def test_fila_vazia_relata_zero(self):
        rel = fila.trabalhar([], self._executores())
        self.assertEqual(rel["feitos"], 0)
        self.assertEqual(rel["motivo_da_parada"], "nada na fila")

    def test_um_item_mecanico_e_feito(self):
        rel = fila.trabalhar([self._pendencia()], self._executores())
        self.assertEqual(rel["feitos"], 1)
        self.assertEqual(self.chamadas, ["memoria_crlf:dents"])

    def test_pendencia_nao_elegivel_nao_entra(self):
        rel = fila.trabalhar([self._pendencia("ci_vermelha")], self._executores())
        self.assertEqual(rel["feitos"], 0)
        self.assertEqual(self.chamadas, [])

    def test_item_feito_fica_ok_e_sai_da_fila_aberta(self):
        fila.trabalhar([self._pendencia()], self._executores())
        self.assertEqual(banco.fila_aberta(), [])

    def test_falha_conta_tentativa_e_guarda_o_erro(self):
        exec_ = self._executores((False, 0.10, "", "o teste continuou vermelho"))
        rel = fila.trabalhar([self._pendencia()], exec_)
        self.assertEqual(rel["falhas"], 1)
        item = banco.fila_aberta()[0]
        self.assertEqual(item["estado"], "falha")
        self.assertEqual(item["tentativas"], 1)
        self.assertIn("vermelho", item["erro"])

    def test_falha_nao_e_retentada_no_mesmo_laco(self):
        exec_ = self._executores((False, 0.0, "", "quebrou"))
        fila.trabalhar([self._pendencia()], exec_)
        self.assertEqual(len(self.chamadas), 1)

    def test_teto_estourado_para_o_laco_com_motivo(self):
        exec_ = self._executores((True, 999.0, "", ""))
        rel = fila.trabalhar(
            [self._pendencia(projeto="a"), self._pendencia(projeto="b")], exec_)
        self.assertEqual(rel["feitos"], 1)
        self.assertIn("teto", rel["motivo_da_parada"])

    def test_o_dono_mandando_parar_interrompe(self):
        exec_ = self._executores()
        rel = fila.trabalhar(
            [self._pendencia(projeto="a"), self._pendencia(projeto="b")],
            exec_, parar_agora=lambda: True)
        self.assertEqual(rel["feitos"], 0)
        self.assertIn("parou", rel["motivo_da_parada"])

    def test_o_grave_e_atendido_primeiro(self):
        exec_ = self._executores()
        fila.trabalhar([self._pendencia("env_drift", "zz", "media"),
                        self._pendencia("memoria_crlf", "aa", "alta")], exec_)
        self.assertEqual(self.chamadas[0], "memoria_crlf:aa")

    def test_pr_url_e_guardado(self):
        exec_ = self._executores((True, 1.0, "https://github.com/x/y/pull/9", ""))
        fila.trabalhar([self._pendencia("env_drift")], exec_)
        con = banco.conectar()
        linha = con.execute("SELECT pr_url FROM fila WHERE id = 'env_drift:dents'").fetchone()
        con.close()
        self.assertEqual(linha["pr_url"], "https://github.com/x/y/pull/9")

    def test_trilho_errado_no_executor_e_erro_visivel(self):
        rel = fila.trabalhar([self._pendencia()], {"claude": lambda i: (True, 0, "", "")})
        self.assertEqual(rel["falhas"], 1)
        self.assertIn("sem executor", banco.fila_aberta()[0]["erro"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
