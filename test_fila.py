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

    def test_auditoria_vencida_vai_pelo_claude(self):
        self.assertEqual(fila.trilho_de(self._p("auditoria_vencida")), "claude")

    def test_achado_de_auditoria_fica_de_fora_por_enquanto(self):
        """As cinco `auditoria_<categoria>` sao pendencia de CONSERTO — nao
        entram na fila mecanica ate o dono autorizar. Fora e' o estado seguro."""
        for regra in ("auditoria_seguranca", "auditoria_bug", "auditoria_teste",
                      "auditoria_doc", "auditoria_estilo"):
            with self.subTest(regra=regra):
                self.assertEqual(fila.trilho_de(self._p(regra)), "")

    def test_elegiveis_carimba_o_executor_do_auditor(self):
        saida = fila.elegiveis([self._p("auditoria_vencida")])
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["executor"], "auditor")

    def test_elegiveis_carimba_claude_para_regra_comum(self):
        saida = fila.elegiveis([self._p("memoria_crlf")])
        self.assertEqual(saida[0]["executor"], "claude")


class RiscoDaAuditoriaTocandoPublicacao(unittest.TestCase):
    """Risco 1 do briefing: o `o_que_fazer` de um achado pode mandar mexer
    em `.github/workflows/ci.yml`. A trava que impede publicacao automatica
    tem de continuar pegando isso, mesmo vindo de uma regra nova."""

    def test_diff_que_toca_o_ci_e_reprovado_para_regra_de_auditoria(self):
        diff = ("--- a/.github/workflows/ci.yml\n"
                "+++ b/.github/workflows/ci.yml\n"
                "@@\n+besteira\n")
        motivo = fila.reprovar(diff, "auditoria_seguranca")
        self.assertTrue(motivo)


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

        self.tetos = []

        def fingir(item, teto_usd=None):
            self.chamadas.append(item["id"])
            self.tetos.append(teto_usd)
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
        rel = fila.trabalhar([self._pendencia()], {"claude": lambda i, teto=None: (True, 0, "", "")})
        self.assertEqual(rel["falhas"], 1)
        self.assertIn("sem executor", banco.fila_aberta()[0]["erro"])


class FusoDoTeto(BancoTemporario):
    """A janela das 21h a meia-noite, onde a data local e a UTC divergem."""

    def test_janela_cobre_24_horas(self):
        ini, fim = fila.janela_local_em_utc("2026-08-25")
        from datetime import datetime
        horas = (datetime.fromisoformat(fim) - datetime.fromisoformat(ini)).total_seconds() / 3600
        self.assertEqual(horas, 24)

    def test_dia_local_de_carimbo_utc_de_madrugada(self):
        """01h UTC do dia 26 e, em UTC-3, ainda 22h do dia 25."""
        from datetime import datetime, timedelta, timezone
        fuso = datetime.now().astimezone().utcoffset()
        local = datetime(2026, 8, 25, 22, 0, tzinfo=timezone(fuso))
        utc = local.astimezone(timezone.utc).isoformat(timespec="seconds")
        self.assertEqual(fila.dia_local_de(utc), "2026-08-25")

    def test_carimbo_ilegivel_nao_explode(self):
        self.assertEqual(fila.dia_local_de("nao e data"), "")
        self.assertEqual(fila.dia_local_de(""), "")
        self.assertEqual(fila.dia_local_de(None), "")

    def test_falha_das_22h_nao_volta_no_mesmo_dia_local(self):
        """Era aqui que o anti-laco furava: [:10] em UTC dava o dia seguinte."""
        from datetime import datetime, timezone
        fuso = datetime.now().astimezone().utcoffset()
        local = datetime(2026, 8, 25, 22, 0, tzinfo=timezone(fuso))
        utc = local.astimezone(timezone.utc).isoformat(timespec="seconds")
        item = {"id": "x:y", "tentativas": 1, "estado": "falha", "terminado_em": utc}
        self.assertFalse(fila.pode_tentar(item, "2026-08-25"))

    def test_gasto_das_22h_conta_no_dia_local(self):
        """O teto tem de fechar mesmo com o item terminado apos as 21h."""
        from datetime import datetime, timezone
        fuso = datetime.now().astimezone().utcoffset()
        local = datetime(2026, 8, 25, 22, 0, tzinfo=timezone(fuso))
        utc = local.astimezone(timezone.utc).isoformat(timespec="seconds")
        banco.enfileirar([{"id": "x:y", "projeto": "y", "regra": "env_drift",
                           "gravidade": "media", "risco": 0}])
        banco.marcar_fila("x:y", estado="ok", custo_usd=7.0, terminado_em=utc)
        self.assertAlmostEqual(
            banco.gasto_entre(*fila.janela_local_em_utc("2026-08-25")), 7.0, places=6)

    def test_gasto_de_outro_dia_local_nao_entra(self):
        from datetime import datetime, timezone
        fuso = datetime.now().astimezone().utcoffset()
        local = datetime(2026, 8, 24, 22, 0, tzinfo=timezone(fuso))
        utc = local.astimezone(timezone.utc).isoformat(timespec="seconds")
        banco.enfileirar([{"id": "x:y", "projeto": "y", "regra": "env_drift",
                           "gravidade": "media", "risco": 0}])
        banco.marcar_fila("x:y", estado="ok", custo_usd=7.0, terminado_em=utc)
        self.assertEqual(
            banco.gasto_entre(*fila.janela_local_em_utc("2026-08-25")), 0.0)


class RenomearTeste(unittest.TestCase):
    """Renomear apaga o teste na pratica e nao produz `+++ /dev/null`."""

    def test_renomear_arquivo_de_teste_reprova(self):
        diff = ("diff --git a/test_x.py b/x.bak\nsimilarity index 100%\n"
                "rename from test_x.py\nrename to x.bak\n")
        self.assertIn("test_x.py", fila.diff_mexeu_em_teste(diff))

    def test_renomear_arquivo_comum_passa(self):
        diff = ("rename from leiame.md\nrename to README.md\n")
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_renomear_spec_ts_reprova(self):
        diff = "rename from src/login.spec.ts\nrename to src/login.velho\n"
        self.assertIn("login.spec.ts", fila.diff_mexeu_em_teste(diff))


class OTetoDoDiaLimitaOTetoDaSessao(BancoTemporario):
    """Achado do revisor em 25/08/2026.

    O teto do dia era conferido ANTES do item, e a sessao saia sempre com o
    teto cheio de US$ 3 (~R$ 15,42). Com R$ 49 gastos de R$ 50, a fila via
    "cabe" e comecava um item que podia levar o dia a R$ 64 — sem que
    `cabe_no_teto` jamais tivesse dito que estourou.
    """

    def test_com_folga_a_sessao_leva_o_teto_cheio(self):
        self.assertAlmostEqual(fila.teto_da_sessao(0.0), execucao.TETO_USD)

    def test_com_pouca_folga_a_sessao_leva_so_o_que_sobra(self):
        """R$ 49 gastos de R$ 50: sobra R$ 1, e a sessao sai com R$ 1."""
        gasto_usd = 49.0 / execucao.USD_BRL
        teto = fila.teto_da_sessao(gasto_usd)
        self.assertLess(teto, execucao.TETO_USD)
        self.assertAlmostEqual(teto * execucao.USD_BRL, 1.0, places=6)

    def test_teto_ja_estourado_nao_da_teto_negativo(self):
        self.assertEqual(fila.teto_da_sessao(100.0), 0.0)

    def test_o_executor_recebe_o_teto_da_sessao(self):
        """Nao adianta calcular e nao entregar."""
        chamadas = []

        def fingir(item, teto_usd=None):
            chamadas.append(teto_usd)
            return (True, 0.0, "", "")

        fila.trabalhar([{"id": "memoria_crlf:dents", "regra": "memoria_crlf",
                         "projeto": "dents", "gravidade": "alta", "risco": 0}],
                       {"mecanico": fingir, "claude": fingir})
        self.assertTrue(chamadas)
        self.assertAlmostEqual(chamadas[0], execucao.TETO_USD)


class OBotaoResolverContaParaOTeto(BancoTemporario):
    """O botao dispara a mesma sessao, com o mesmo custo, e nao encostava na
    tabela `fila` — entao o teto do dia nao o enxergava. Duas sessoes em
    paralelo (uma da fila, uma do botao) gastavam sem ver uma a outra."""

    def test_gasto_de_fora_da_fila_entra_na_soma_do_dia(self):
        quando = "2026-08-25T12:00:00+00:00"
        banco.registrar_gasto(0.75, origem="botao:dents", quando=quando)
        total = banco.gasto_entre("2026-08-25T00:00:00+00:00",
                                  "2026-08-26T00:00:00+00:00")
        self.assertAlmostEqual(total, 0.75)

    def test_gasto_fora_da_janela_nao_entra(self):
        banco.registrar_gasto(0.75, origem="botao:dents",
                              quando="2026-08-24T12:00:00+00:00")
        total = banco.gasto_entre("2026-08-25T00:00:00+00:00",
                                  "2026-08-26T00:00:00+00:00")
        self.assertAlmostEqual(total, 0.0)

    def test_custo_zero_nao_vira_linha(self):
        self.assertFalse(banco.registrar_gasto(0.0, origem="botao:x"))
        self.assertFalse(banco.registrar_gasto(None, origem="botao:x"))

    def test_a_soma_junta_a_fila_e_o_botao(self):
        quando = "2026-08-25T12:00:00+00:00"
        banco.enfileirar([{"id": "r:p", "regra": "r", "projeto": "p",
                           "gravidade": "alta", "risco": 0, "trilho": "claude"}])
        banco.marcar_fila("r:p", estado="ok", terminado_em=quando, custo_usd=0.25)
        banco.registrar_gasto(0.75, origem="botao:p", quando=quando)
        total = banco.gasto_entre("2026-08-25T00:00:00+00:00",
                                  "2026-08-26T00:00:00+00:00")
        self.assertAlmostEqual(total, 1.00)


class TravaDePublicacao(unittest.TestCase):
    """Nenhum DIFF, de nenhuma cor, altera o caminho que publica.

    O criterio 4 da Fatia 2 nao se satisfaz com "nenhuma rota publica". A
    sessao filha escreve codigo; se ela puder acrescentar um gatilho ao
    `publicar.yml`, ela publica na proxima vez que alguem mexer no repositorio.
    """

    def test_acrescentar_gatilho_ao_publicar_yml_e_reprovado(self):
        diff = ("--- a/.github/workflows/publicar.yml\n"
                "+++ b/.github/workflows/publicar.yml\n"
                "@@ -1,3 +1,4 @@\n on:\n+  push:\n   workflow_dispatch:\n")
        self.assertTrue(fila.diff_toca_publicacao(diff))

    def test_o_dockerfile_e_o_compose_sao_caminho_de_publicacao(self):
        for arquivo in ("Dockerfile", "docker-compose.yml", "infra/nginx.conf"):
            diff = "--- a/%s\n+++ b/%s\n@@ -1 +1 @@\n-a\n+b\n" % (arquivo, arquivo)
            self.assertTrue(fila.diff_toca_publicacao(diff), arquivo)

    def test_renomear_workflow_e_reprovado(self):
        """Renomear tira o arquivo do lugar sem produzir `+++ /dev/null`."""
        diff = ("diff --git a/.github/workflows/publicar.yml b/publicar.yml\n"
                "similarity index 100%\n"
                "rename from .github/workflows/publicar.yml\n"
                "rename to publicar.yml\n")
        self.assertTrue(fila.diff_toca_publicacao(diff))

    def test_linha_nova_que_dispara_publicacao_e_reprovada(self):
        """Nao basta proteger os arquivos: um script novo em qualquer pasta que
        chame `gh workflow run` publica igual."""
        for gatilho in ("gh workflow run publicar.yml",
                        "curl -X POST .../actions/workflows/1/dispatches",
                        "on: workflow_dispatch"):
            diff = "--- a/scripts/x.sh\n+++ b/scripts/x.sh\n@@ -1 +1,2 @@\n a\n+%s\n" % gatilho
            self.assertTrue(fila.diff_toca_publicacao(diff), gatilho)

    def test_mexer_so_no_readme_passa(self):
        diff = ("--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n"
                "-titulo\n+Titulo\n")
        self.assertEqual(fila.diff_toca_publicacao(diff), "")

    def test_infra_dentro_de_outro_nome_nao_e_reprovado(self):
        """`infra` dentro de `src/infraestrutura.ts` reprovaria trabalho
        legitimo, e uma trava que reprova trabalho legitimo e desligada."""
        diff = ("--- a/src/infraestrutura.ts\n+++ b/src/infraestrutura.ts\n"
                "@@ -1 +1 @@\n-a\n+b\n")
        self.assertEqual(fila.diff_toca_publicacao(diff), "")

    def test_diff_vazio_nao_e_reprovado(self):
        """A guarda da guarda. Uma trava que reprova tudo passa em todo teste
        de reprovacao e trava o produto inteiro."""
        for vazio in ("", "   ", None):
            self.assertEqual(fila.diff_toca_publicacao(vazio), "")

    def test_a_trava_vale_para_TODA_regra(self):
        """Nao ha regra que compre o direito de publicar."""
        diff = ("--- a/.github/workflows/ci.yml\n+++ b/.github/workflows/ci.yml\n"
                "@@ -1 +1 @@\n-a\n+b\n")
        for regra in ("env_drift", "memoria_crlf", "dependencia_insegura",
                      "regra_que_nao_existe", ""):
            self.assertTrue(fila.reprovar(diff, regra), regra)

    def test_reprovar_cita_a_trava_no_fonte(self):
        """A guarda da guarda: a trava esta LIGADA, e nao so escrita. Ja
        aconteceu nesta casa de uma defesa existir e nao estar no caminho."""
        import inspect
        self.assertIn("diff_toca_publicacao", inspect.getsource(fila.reprovar))

    def test_um_diff_inofensivo_continua_passando_por_reprovar(self):
        diff = ("--- a/banco.py\n+++ b/banco.py\n@@ -1 +1 @@\n"
                "-x = 1\n+x = 2\n")
        self.assertEqual(fila.reprovar(diff, "memoria_crlf"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
