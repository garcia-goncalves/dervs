# -*- coding: utf-8 -*-
"""Testes da tomada dos bracos — `agente/executor.py`.

**O binario `claude` NUNCA e chamado aqui.** Ele gastaria cota da assinatura do
dono a cada corrida da CI, e a CI roda numa maquina sem login nenhum: o teste
ficaria vermelho pelo motivo errado. No lugar dele entra um script Python de
mentira que cospe `stream-json` linha a linha, como o de verdade faz.

O que este arquivo prova, na ordem em que importa:

  1. O CRITERIO 1 do briefing: o braco roda uma sessao sobre uma copia isolada
     e devolve ramo, resumo e diff.
  2. As linhas sao lidas UMA A UMA, enquanto a sessao roda — e nao todas no
     fim. E isso que sustenta "o dono ve o trabalho acontecendo".
  3. O CRITERIO 5: com o teto do dia consumido, o argv NUNCA E MONTADO. Nao
     basta a sessao terminar em recusa: ela nao pode comecar.
  4. O Codex existe, esta desligado, e diz por que.

    python test_executor.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import execucao                    # noqa: E402
import tarefas                     # noqa: E402
from agente import executor as ex  # noqa: E402


# O que o `claude` de verdade cospe: uma linha de JSON por evento. Este script
# imita o formato e nada mais — nao pensa, nao pede rede, nao custa cota.
SESSAO_DE_MENTIRA = textwrap.dedent('''
    import json, sys, time
    def diga(o):
        sys.stdout.write(json.dumps(o) + "\\n")
        sys.stdout.flush()
    diga({"type": "system", "subtype": "init"})
    time.sleep(0.2)
    diga({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": "x.py"}}]}})
    time.sleep(0.2)
    diga({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "x.py"}}]}})
    time.sleep(0.2)
    diga({"type": "result", "subtype": "success", "is_error": False,
          "terminal_reason": "end_turn", "num_turns": 7,
          "total_cost_usd": 1.02, "result": "troquei o valor de x"})
''').strip()


class ComRepositorioDeMentira(unittest.TestCase):
    """Um repositorio de verdade, criado do zero, com `git init`.

    De verdade porque `execucao.criar_copia` roda `git` de verdade: um duble de
    repositorio provaria que o duble funciona.
    """

    @classmethod
    def setUpClass(cls):
        cls.tem_git = bool(shutil.which("git"))

    def setUp(self):
        if not self.tem_git:
            self.skipTest("sem git nesta maquina")
        self.pasta = tempfile.mkdtemp()
        self.projeto = Path(self.pasta) / "alvo"
        self.projeto.mkdir()
        self.script = Path(self.pasta) / "sessao_de_mentira.py"
        self.script.write_text(SESSAO_DE_MENTIRA, encoding="utf-8")
        for argv in (["git", "init", "-q", "-b", "main"],
                     ["git", "config", "user.email", "teste@teste.local"],
                     ["git", "config", "user.name", "Teste"]):
            subprocess.run(argv, cwd=str(self.projeto), capture_output=True)
        (self.projeto / "x.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.projeto),
                       capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "inicio"],
                       cwd=str(self.projeto), capture_output=True)
        # A copia isolada nasce dentro da pasta temporaria, e nao no disco do
        # dono. `execucao.caminho_da_copia` respeita a base que recebe.
        self._base_antiga = getattr(execucao, "BASE_DAS_COPIAS", None)
        execucao._execucao = execucao._zerado()
        execucao._proc = None
        self.addCleanup(self.derrubar)

    def derrubar(self):
        try:
            execucao.parar()
        except Exception:                       # noqa: BLE001
            pass
        execucao._execucao = execucao._zerado()
        execucao._proc = None
        shutil.rmtree(self.pasta, ignore_errors=True)

    def com_sessao_de_mentira(self):
        """Troca `montar_comando` por um argv que roda o script de mentira."""
        original = execucao.montar_comando
        execucao.montar_comando = lambda *a, **k: [sys.executable,
                                                   str(self.script)]
        self.addCleanup(setattr, execucao, "montar_comando", original)

    def tarefa(self, **kw):
        base = {"id": "d:1", "projeto": "alvo", "regra": "env_drift",
                "trilho": "claude", "executor": "claude",
                "detalhe": "trocar o valor de x",
                "caminho": str(self.projeto), "teto_usd": 3.0,
                "tentativas": 0}
        base.update(kw)
        return base


class OBracoRoda(ComRepositorioDeMentira):

    def test_uma_sessao_inteira_devolve_ramo_resumo_e_diff(self):
        """O criterio 1 do briefing, ao pe da letra."""
        self.com_sessao_de_mentira()
        vistos = []
        fora = ex.ExecutorClaude().rodar(
            self.tarefa(), ao_progredir=lambda r: vistos.append(r) or False,
            repinturas={"env_drift": "verde"})
        self.assertEqual(fora["tipo"], "desfecho")
        self.assertEqual(fora["id"], "d:1")
        self.assertIn(fora["estado"], ("ok", "falha"))
        self.assertTrue(fora["ramo"], "a sessao terminou sem ramo")
        self.assertIn("hub/", fora["ramo"])

    def test_as_linhas_chegam_UMA_A_UMA_e_nao_todas_no_fim(self):
        """O que sustenta "o dono ve o trabalho acontecendo".

        Se `ao_progredir` fosse chamado uma vez so, no fim, a tela mostraria a
        sessao inteira de uma vez — e a diferenca entre isso e o relogio de 60
        segundos seria nenhuma.
        """
        self.com_sessao_de_mentira()
        chamadas = []
        ex.ExecutorClaude().rodar(
            self.tarefa(),
            ao_progredir=lambda r: chamadas.append(r.get("total_de_linhas"))
                                   or False,
            repinturas={"env_drift": "verde"})
        self.assertGreater(len(chamadas), 1,
                           "o progresso foi entregue uma vez so")
        # E o numero de linhas CRESCEU durante a sessao.
        self.assertGreater(max(chamadas), min(chamadas),
                           "o log nao cresceu enquanto a sessao rodava")

    def test_o_custo_e_as_rodadas_do_evento_final_chegam_ao_desfecho(self):
        """Com assinatura, o numero que manda e rodadas. Ele so existe se
        alguem o contar — e quem conta e o `execucao`, evento a evento."""
        self.com_sessao_de_mentira()
        fora = ex.ExecutorClaude().rodar(self.tarefa(),
                                         repinturas={"env_drift": "verde"})
        self.assertEqual(fora["rodadas"], 7)
        self.assertAlmostEqual(fora["custo_usd"], 1.02, places=2)

    def test_pedir_parada_pelo_retorno_do_progresso_mata_a_sessao(self):
        """O botao Parar nao tem fio proprio: ele volta como `True` no retorno
        de `ao_progredir`."""
        self.com_sessao_de_mentira()
        fora = ex.ExecutorClaude().rodar(self.tarefa(),
                                         ao_progredir=lambda r: True,
                                         repinturas={"env_drift": "verde"})
        self.assertEqual(fora["estado"], "falha")

    def test_falha_ao_falar_com_o_painel_nao_mata_a_sessao(self):
        """O trabalho ja esta feito pela metade; perde-lo por um cabo de rede
        seria o pior dos dois mundos."""
        self.com_sessao_de_mentira()

        def explode(_retrato):
            raise ConnectionError("a rede caiu")

        fora = ex.ExecutorClaude().rodar(self.tarefa(), ao_progredir=explode,
                                         repinturas={"env_drift": "verde"})
        self.assertEqual(fora["tipo"], "desfecho")
        self.assertTrue(fora["ramo"])


class OTetoRecusaAntesDeComecar(ComRepositorioDeMentira):
    """O criterio 5, e a parte dele que costuma faltar."""

    def test_com_o_teto_do_dia_consumido_o_argv_NUNCA_E_MONTADO(self):
        """Nao basta a sessao terminar em recusa: ela nao pode COMECAR.

        O duble estoura se for chamado. Se `pode_rodar` fosse conferido depois
        de montar o comando, este teste ficaria vermelho — e e exatamente esse
        o erro que ele existe para pegar.
        """
        def nao_deveria(*_a, **_k):
            raise AssertionError("o argv foi montado com o teto estourado")

        original = execucao.montar_comando
        execucao.montar_comando = nao_deveria
        self.addCleanup(setattr, execucao, "montar_comando", original)

        estourado = (tarefas.TETO_DIARIO_BRL / tarefas.USD_BRL) + 1
        fora = ex.ExecutorClaude().rodar(self.tarefa(), gasto_usd=estourado,
                                         repinturas={"env_drift": "verde"})
        self.assertEqual(fora["estado"], "falha")
        self.assertTrue(fora.get("recusada"))
        self.assertIn("teto", fora["erro"])

    def test_tarefa_vermelha_tambem_nao_monta_argv(self):
        """A segunda camada do semaforo. O servidor ja recusou entregar; o
        agente recusa de novo, e sem depender de o painel estar certo."""
        def nao_deveria(*_a, **_k):
            raise AssertionError("o argv foi montado com a tarefa vermelha")

        original = execucao.montar_comando
        execucao.montar_comando = nao_deveria
        self.addCleanup(setattr, execucao, "montar_comando", original)

        fora = ex.ExecutorClaude().rodar(self.tarefa(), repinturas={})
        self.assertEqual(fora["estado"], "falha")
        self.assertTrue(fora.get("recusada"))

    def test_maquina_sem_autorizacao_tambem_nao_monta_argv(self):
        def nao_deveria(*_a, **_k):
            raise AssertionError("o argv foi montado sem autorizacao")

        original = execucao.montar_comando
        execucao.montar_comando = nao_deveria
        self.addCleanup(setattr, execucao, "montar_comando", original)

        fora = ex.ExecutorClaude().rodar(
            self.tarefa(), repinturas={"env_drift": "verde"},
            maquina={"id": 3, "executa": 0})
        self.assertTrue(fora.get("recusada"))


class ATomada(unittest.TestCase):
    """A interface, e o braco que ainda nao existe."""

    def test_o_codex_existe_esta_desligado_e_diz_por_que(self):
        codex = ex.ExecutorCodex()
        self.assertEqual(codex.nome, "codex")
        self.assertFalse(codex.disponivel())
        with self.assertRaises(NotImplementedError) as erro:
            codex.rodar({"id": "d:1"})
        self.assertIn("Fatia 3", str(erro.exception))

    def test_o_claude_esta_na_tabela_e_e_o_padrao_do_painel(self):
        self.assertIn("claude", ex.EXECUTORES)
        self.assertIsInstance(ex.executor_de("claude"), ex.ExecutorClaude)

    def test_nome_desconhecido_devolve_nada_e_nao_o_padrao(self):
        """Falha fechada. Um nome torto que caisse no padrao faria o painel
        rodar Claude achando que pediu outra coisa."""
        for lixo in ("gpt", "", None, "CLAUDE", "claude2"):
            self.assertIsNone(ex.executor_de(lixo), repr(lixo))
        # Espaco em volta e aparado, e isso e de proposito: o nome vem do
        # banco, e um espaco a mais nao e um braco diferente.
        self.assertIsInstance(ex.executor_de("  claude  "), ex.ExecutorClaude)

    def test_a_base_exige_que_todo_braco_responda_as_tres_perguntas(self):
        base = ex.Executor()
        with self.assertRaises(NotImplementedError):
            base.disponivel()
        with self.assertRaises(NotImplementedError):
            base.rodar({"id": "d:1"})

    def test_a_guarda_do_teto_mora_na_base_e_nao_em_cada_braco(self):
        """Duas copias da mesma guarda divergem, e a que diverge e sempre a que
        ninguem le."""
        import inspect
        self.assertIn("pode_rodar",
                      inspect.getsource(ex.Executor._recusar_se_nao_pode))
        self.assertIn("_recusar_se_nao_pode",
                      inspect.getsource(ex.ExecutorClaude.rodar))

    def test_o_duble_da_sessao_nao_pede_rede_nem_cota(self):
        """A guarda da guarda: se alguem trocar o duble por uma chamada real, a
        CI passaria a gastar cota da conta do dono a cada corrida — e ficaria
        vermelha na maquina da CI, que nao tem login nenhum.

        Conferido no SCRIPT DE MENTIRA, e nao neste arquivo: procurar a palavra
        no proprio fonte acharia a linha que faz a busca, e o teste falharia
        sozinho. Ja aconteceu, nesta funcao, em 29/08/2026.
        """
        self.assertNotIn("claude", SESSAO_DE_MENTIRA)
        for proibido in ("http", "socket", "requests", "urllib", "anthropic"):
            self.assertNotIn(proibido, SESSAO_DE_MENTIRA, proibido)
        self.assertIn("stdout.write", SESSAO_DE_MENTIRA)


if __name__ == "__main__":
    unittest.main(verbosity=0)
