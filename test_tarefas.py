# -*- coding: utf-8 -*-
"""Testes do semaforo — `tarefas.py`.

Este arquivo cobra tres coisas, e a terceira e a que costuma faltar:

  1. O COMPORTAMENTO. Vermelha sem aprovacao nao roda; verde roda; `publicar`
     nunca fica verde.
  2. O ISOLAMENTO. Importar `tarefas` NAO pode arrastar `execucao` nem `fila`.
     Se arrastasse, `servir.py` nao poderia importar `tarefas` (a tabela de
     rotas e amputada) e a imagem nao fecharia (`test_imagem` proibe os dois
     arquivos dentro dela).
  3. A GUARDA DA GUARDA. Um teste que le o FONTE de `pode_rodar` e cobra que a
     checagem de aprovacao esteja escrita la. Sem ele, alguem que apagasse a
     guarda veria so uma assercao ficar vermelha — e assercao vermelha se
     "conserta" mudando a assercao. Guarda apagada tem de deixar o ARQUIVO
     vermelho.

    python test_tarefas.py
"""
from __future__ import annotations

import hashlib
import inspect
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

import tarefas

AQUI = Path(__file__).resolve().parent
AGORA = datetime(2026, 8, 29, 14, 0, 0, tzinfo=timezone.utc)
AGORA_ISO = AGORA.isoformat(timespec="seconds")


def tarefa(**kw) -> dict:
    """Uma tarefa minima e valida. Os testes trocam so o que interessa a eles."""
    base = {"id": "d:1", "projeto": "dervs", "regra": "env_drift",
            "trilho": "claude", "tentativas": 0}
    base.update(kw)
    return base


class Semaforo(unittest.TestCase):
    """"esta tarefa pode rodar agora?" — a pergunta unica."""

    def test_regra_desconhecida_nasce_vermelha(self):
        """Nao ha lista de regras verdes no codigo. O padrao e a recusa."""
        self.assertEqual(tarefas.cor_da_regra("regra_que_nunca_existiu"),
                         tarefas.VERMELHO)
        self.assertEqual(tarefas.cor_da_regra("env_drift"), tarefas.VERMELHO)

    def test_dicionario_de_repintura_vazio_ou_nulo_e_vermelho(self):
        for repinturas in (None, {}, {"outra": "verde"}, {"env_drift": "azul"}):
            self.assertEqual(tarefas.cor_da_regra("env_drift", repinturas),
                             tarefas.VERMELHO)

    def test_regra_repintada_de_verde_fica_verde(self):
        self.assertEqual(tarefas.cor_da_regra("env_drift",
                                              {"env_drift": "verde"}),
                         tarefas.VERDE)

    def test_publicar_recusa_repintura_para_verde(self):
        """Decisao do dono em 28/08/2026: vermelho para sempre, e nao
        repintavel. Nao ha caminho de configuracao que atravesse isto."""
        self.assertFalse(tarefas.pode_repintar("publicar", "verde"))
        self.assertEqual(
            tarefas.cor_da_regra("publicar", {"publicar": "verde"}),
            tarefas.VERMELHO)

    def test_publicar_aceita_repintura_para_vermelho(self):
        """Fechar nunca precisa de licenca."""
        self.assertTrue(tarefas.pode_repintar("publicar", "vermelho"))

    def test_repintar_com_cor_inventada_e_recusado(self):
        for lixo in ("azul", "VERDE", "", None, 1):
            self.assertFalse(tarefas.pode_repintar("env_drift", lixo))

    def test_verde_sem_aprovacao_roda(self):
        pode, motivo = tarefas.pode_rodar(
            tarefa(), 0.0, AGORA_ISO, {"env_drift": "verde"})
        self.assertTrue(pode, motivo)
        self.assertEqual(motivo, "")

    def test_vermelha_sem_aprovacao_nao_roda(self):
        pode, motivo = tarefas.pode_rodar(tarefa(), 0.0, AGORA_ISO, {})
        self.assertFalse(pode)
        self.assertIn("clique", motivo)

    def test_vermelha_com_aprovacao_roda(self):
        pode, motivo = tarefas.pode_rodar(
            tarefa(aprovado_em=AGORA_ISO), 0.0, AGORA_ISO, {})
        self.assertTrue(pode, motivo)

    def test_publicar_nao_roda_nem_aprovada(self):
        """O clique do dono aprova UMA tarefa; ele nao levanta o NUNCA_VERDE.
        Mas mesmo aprovada, a frase da tela tem de dizer o motivo certo."""
        pode, motivo = tarefas.pode_rodar(
            tarefa(regra="publicar"), 0.0, AGORA_ISO, {"publicar": "verde"})
        self.assertFalse(pode)
        self.assertIn("nunca anda sozinha", motivo)

    def test_teto_estourado_recusa_antes_de_qualquer_outra_coisa(self):
        """Uma tarefa que nao cabe no dia nao deve nem ser avaliada pelo resto.
        Ate a verde e aprovada para."""
        gasto_usd = (tarefas.TETO_DIARIO_BRL / tarefas.USD_BRL) + 1
        pode, motivo = tarefas.pode_rodar(
            tarefa(aprovado_em=AGORA_ISO), gasto_usd, AGORA_ISO,
            {"env_drift": "verde"})
        self.assertFalse(pode)
        self.assertIn("teto", motivo)

    def test_no_ponto_exato_do_teto_ja_nao_cabe(self):
        gasto_usd = tarefas.TETO_DIARIO_BRL / tarefas.USD_BRL
        self.assertFalse(tarefas.cabe_no_teto(gasto_usd))

    def test_tentativas_esgotadas_nao_rodam(self):
        pode, motivo = tarefas.pode_rodar(
            tarefa(tentativas=tarefas.MAX_TENTATIVAS), 0.0, AGORA_ISO,
            {"env_drift": "verde"})
        self.assertFalse(pode)
        self.assertIn("tentativas", motivo)

    def test_maquina_sem_executa_nao_roda(self):
        pode, motivo = tarefas.pode_rodar(
            tarefa(), 0.0, AGORA_ISO, {"env_drift": "verde"},
            maquina={"id": 3, "executa": 0})
        self.assertFalse(pode)
        self.assertIn("autorizado", motivo)

    def test_maquina_com_executa_roda(self):
        pode, motivo = tarefas.pode_rodar(
            tarefa(), 0.0, AGORA_ISO, {"env_drift": "verde"},
            maquina={"id": 3, "executa": 1})
        self.assertTrue(pode, motivo)

    def test_parada_pedida_nao_roda(self):
        pode, motivo = tarefas.pode_rodar(
            tarefa(parada_pedida_em=AGORA_ISO), 0.0, AGORA_ISO,
            {"env_drift": "verde"})
        self.assertFalse(pode)
        self.assertIn("parar", motivo)

    def test_entrada_torta_vira_recusa_e_nao_traceback(self):
        """Lei 3 do repositorio: caminho de autorizacao falha FECHADO. Um
        `except` esquecido aqui viraria porta aberta, porque quem chamou
        trataria a excecao como "deu erro, deixa passar"."""
        for lixo in (None, {}, {"id": ""}, {"id": "d:1"},
                     {"id": "d:1", "regra": ""}):
            pode, motivo = tarefas.pode_rodar(lixo, 0.0, AGORA_ISO,
                                              {"env_drift": "verde"})
            self.assertFalse(pode)
            self.assertTrue(motivo)

    def test_gasto_ilegivel_nao_abre_o_teto(self):
        for lixo in (None, "muito", object()):
            self.assertTrue(tarefas.cabe_no_teto(lixo))   # trata como zero
        self.assertEqual(tarefas.quanto_falta("muito"), tarefas.TETO_DIARIO_BRL)

    def test_o_motivo_e_uma_frase_em_portugues_nao_um_codigo(self):
        """A frase vai direto para a tela. Codigo de erro na tela obriga o dono
        a procurar o significado, e ele nao vai procurar."""
        _, motivo = tarefas.pode_rodar(tarefa(), 0.0, AGORA_ISO, {})
        self.assertIn(" ", motivo.strip())
        self.assertNotIn("_", motivo)


class ProvaPodeRodar(unittest.TestCase):
    """A regra `provar`: mesma pergunta nos dois lados, sem abrir sessao de IA."""

    def _prova(self, **kw):
        base = {"regra": "provar", "executor": "prova",
                "aprovado_em": AGORA_ISO}
        base.update(kw)
        return tarefa(**base)

    def test_aprovada_roda(self):
        pode, motivo = tarefas.pode_rodar(self._prova(), 0.0, AGORA_ISO, {})
        self.assertTrue(pode, motivo)

    def test_sem_aprovacao_nao_roda_nem_repintada_de_verde(self):
        t = self._prova()
        t.pop("aprovado_em")
        for rep in ({}, {"provar": "verde"}):
            pode, motivo = tarefas.pode_rodar(t, 0.0, AGORA_ISO, rep)
            self.assertFalse(pode)
            self.assertIn("clique", motivo)

    def test_executor_errado_nao_roda(self):
        for ex in ("claude", "mecanico", "", None):
            pode, motivo = tarefas.pode_rodar(
                self._prova(executor=ex), 0.0, AGORA_ISO, {})
            self.assertFalse(pode, ex)
            self.assertIn("executor", motivo)

    def test_projeto_bloqueado_ou_nexa_nao_roda(self):
        for proj in ("ajudei-saude", "Ajudei_Saude", "ccvp", "Nexa-x",
                     "aninha-site", "", None):
            pode, motivo = tarefas.pode_rodar(
                self._prova(projeto=proj), 0.0, AGORA_ISO, {})
            self.assertFalse(pode, proj)
            self.assertIn("provas", motivo)


class GuardaDaGuarda(unittest.TestCase):
    """Apagar a guarda tem de deixar o ARQUIVO vermelho, nao so a assercao."""

    def test_pode_rodar_confere_aprovado_em_no_fonte(self):
        fonte = inspect.getsource(tarefas.pode_rodar)
        self.assertIn("aprovado_em", fonte)
        self.assertIn("cor_da_regra", fonte)

    def test_pode_rodar_confere_o_teto_no_fonte(self):
        self.assertIn("cabe_no_teto", inspect.getsource(tarefas.pode_rodar))

    def test_publicar_esta_em_nunca_verde(self):
        self.assertIn("publicar", tarefas.NUNCA_VERDE)

    def test_nunca_verde_e_imutavel(self):
        """`set` comum deixaria qualquer modulo importado depois acrescentar ou
        remover um nome em tempo de execucao."""
        self.assertIsInstance(tarefas.NUNCA_VERDE, frozenset)


class Isolamento(unittest.TestCase):
    """`tarefas` nao pode arrastar `execucao` nem `fila`."""

    def test_importar_tarefas_nao_arrasta_execucao_nem_fila(self):
        """Rodado num processo NOVO de proposito: neste aqui, outro teste ja
        pode ter importado os dois, e a assercao passaria por engano."""
        codigo = ("import sys; import tarefas; "
                  "print(int('execucao' in sys.modules), "
                  "int('fila' in sys.modules), "
                  "int('banco' in sys.modules))")
        saida = subprocess.run([sys.executable, "-c", codigo], cwd=str(AQUI),
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(saida.returncode, 0, saida.stderr)
        self.assertEqual(saida.stdout.split(), ["0", "0", "0"])

    def test_o_fonte_nao_importa_execucao_nem_fila(self):
        fonte = (AQUI / "tarefas.py").read_text(encoding="utf-8")
        for linha in fonte.splitlines():
            nu = linha.strip()
            if nu.startswith("import ") or nu.startswith("from "):
                self.assertNotIn("execucao", nu)
                self.assertNotIn("fila", nu)
                self.assertNotIn("banco", nu)


class UmValorSo(unittest.TestCase):
    """Os tetos mudaram de casa. Nao ficou copia."""

    def test_fila_e_execucao_apontam_para_o_mesmo_objeto(self):
        import execucao
        import fila
        self.assertIs(fila.TETO_DIARIO_BRL, tarefas.TETO_DIARIO_BRL)
        self.assertIs(fila.cabe_no_teto, tarefas.cabe_no_teto)
        self.assertIs(fila.teto_da_sessao, tarefas.teto_da_sessao)
        self.assertIs(fila.hoje_local, tarefas.hoje_local)
        self.assertIs(fila.dia_local_de, tarefas.dia_local_de)
        self.assertIs(execucao.TETO_USD, tarefas.TETO_USD)
        self.assertIs(execucao.USD_BRL, tarefas.USD_BRL)
        self.assertIs(execucao.em_reais, tarefas.em_reais)

    def test_nao_ha_um_segundo_valor_do_teto_no_repositorio(self):
        """O dia em que um mudar, o outro mente com autoridade."""
        for nome in ("fila.py", "execucao.py"):
            fonte = (AQUI / nome).read_text(encoding="utf-8")
            for linha in fonte.splitlines():
                nu = linha.strip()
                if nu.startswith("#"):
                    continue
                for proibido in ("TETO_DIARIO_BRL = 5", "USD_BRL = 5.",
                                 "TETO_USD = 3", "MAX_TURNOS = 4",
                                 "MAX_TENTATIVAS = 2"):
                    self.assertNotIn(proibido, nu,
                                     "%s: %s voltou a ter valor proprio"
                                     % (nome, nu))

    def test_em_reais_usa_virgula(self):
        self.assertEqual(tarefas.em_reais(1), "R$ 5,14")


class DiffEmPortugues(unittest.TestCase):
    """A traducao do diff (etapa 12). Funcao pura, sem modelo de linguagem."""

    def test_diff_vazio_diz_que_nada_mudou(self):
        """Lista vazia na tela e indistinguivel de "nao consegui ler", e essa e
        exatamente a diferenca que a lei 2 exige que apareca."""
        for vazio in ("", "   ", None):
            frases = tarefas.frases_do_diff(vazio)
            self.assertEqual(len(frases), 1)
            self.assertIn("Nada mudou", frases[0])

    def test_arquivo_criado(self):
        diff = ("--- /dev/null\n+++ b/novo.py\n@@ -0,0 +1,2 @@\n"
                "+uma\n+duas\n")
        frases = tarefas.frases_do_diff(diff)
        self.assertEqual(len(frases), 1)
        self.assertIn("`novo.py` foi criado", frases[0])
        self.assertIn("2 linhas", frases[0])

    def test_arquivo_apagado(self):
        diff = "--- a/velho.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-uma\n-duas\n"
        self.assertIn("`velho.py` foi apagado", tarefas.frases_do_diff(diff)[0])

    def test_renomeacao(self):
        diff = "--- a/antes.py\n+++ b/depois.py\n@@ -1 +1 @@\n-x\n+x\n"
        self.assertIn("`antes.py` virou `depois.py`",
                      tarefas.frases_do_diff(diff)[0])

    def test_linhas_trocadas(self):
        diff = ("--- a/banco.py\n+++ b/banco.py\n@@ -1,3 +1,3 @@\n"
                " igual\n-a\n-b\n-c\n+A\n+B\n+C\n")
        self.assertEqual(tarefas.frases_do_diff(diff),
                         ["3 linhas trocadas em `banco.py`"])

    def test_uma_linha_no_singular(self):
        diff = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+A\n"
        self.assertEqual(tarefas.frases_do_diff(diff),
                         ["1 linha trocada em `x.py`"])

    def test_so_acrescimo_e_so_remocao(self):
        mais = "--- a/x.py\n+++ b/x.py\n@@ -1 +1,3 @@\n a\n+b\n+c\n"
        self.assertIn("2 linhas a mais", tarefas.frases_do_diff(mais)[0])
        menos = "--- a/x.py\n+++ b/x.py\n@@ -1,3 +1 @@\n a\n-b\n-c\n"
        self.assertIn("2 linhas a menos", tarefas.frases_do_diff(menos)[0])

    def test_varios_arquivos_uma_frase_cada(self):
        diff = ("--- a/um.py\n+++ b/um.py\n@@ -1 +1 @@\n-a\n+A\n"
                "--- a/dois.py\n+++ b/dois.py\n@@ -1 +1 @@\n-b\n+B\n")
        self.assertEqual(len(tarefas.frases_do_diff(diff)), 2)

    def test_lixo_no_lugar_do_diff_nao_explode(self):
        self.assertTrue(tarefas.frases_do_diff("isto nao e um diff nenhum"))


class Fuso(unittest.TestCase):
    """As contas de dia local. Em UTC-3, as 21h de terca ja e quarta em UTC."""

    def test_dia_local_de_carimbo_vazio_ou_torto_e_vazio(self):
        for lixo in ("", None, "ontem", "2026-13-45T99:99:99+00:00"):
            self.assertEqual(tarefas.dia_local_de(lixo), "")

    def test_a_janela_de_um_dia_local_tem_24_horas(self):
        inicio, fim = tarefas.janela_local_em_utc("2026-08-29")
        i = datetime.fromisoformat(inicio)
        f = datetime.fromisoformat(fim)
        self.assertEqual((f - i).total_seconds(), 24 * 3600)

    def test_o_dia_local_de_um_carimbo_da_propria_janela_bate(self):
        inicio, _ = tarefas.janela_local_em_utc("2026-08-29")
        self.assertEqual(tarefas.dia_local_de(inicio), "2026-08-29")

    def test_teto_da_sessao_nunca_passa_do_que_sobra(self):
        """Achado do revisor em 25/08/2026: com R$ 49 gastos, a sessao saia com
        R$ 15,42 de teto e podia levar o dia a R$ 64."""
        quase_tudo = 49.0 / tarefas.USD_BRL
        self.assertLess(tarefas.teto_da_sessao(quase_tudo), 0.2)
        self.assertEqual(tarefas.teto_da_sessao(0.0), tarefas.TETO_USD)

    def test_teto_da_sessao_nunca_e_negativo(self):
        estourado = 100.0 / tarefas.USD_BRL
        self.assertEqual(tarefas.teto_da_sessao(estourado), 0.0)


class OTextoDaOrdem(unittest.TestCase):
    """C0 da entrega C: o texto que vira desafio. A tabela e escrita a mao,
    com os hashes de `docs/superpowers/plans/dervs-conectar-acoes-c.md` (I0):
    o ajudante tem a mesma conta, e as duas pontas precisam dar os mesmos
    bytes."""

    BASE = {"servidor": "7f3a9c2e5b8d41f6a0c3e9b2d4f6a8c1",
            "tipo": "reiniciar", "alvo": "grimoire-web",
            "numero": "4e1d2c3b5a6978f0e1d2c3b4a5968778",
            "criado": 1791558000, "vence": 1791558300}

    def test_reiniciar_da_o_texto_e_o_hash_da_tabela(self):
        texto = tarefas.texto_da_ordem(dict(self.BASE))
        self.assertEqual(
            "dervs-ordem=1\nservidor=7f3a9c2e5b8d41f6a0c3e9b2d4f6a8c1\n"
            "tipo=reiniciar\nalvo=grimoire-web\n"
            "numero=4e1d2c3b5a6978f0e1d2c3b4a5968778\n"
            "criado=1791558000\nvence=1791558300", texto)
        self.assertEqual(
            "2358580c05214c6639569a105fe02350d2cea31d76f4fd6f6ead896445090d84",
            hashlib.sha256(texto.encode("ascii")).hexdigest())

    def test_voltar_da_o_hash_da_tabela(self):
        texto = tarefas.texto_da_ordem(dict(self.BASE, tipo="voltar",
                                            alvo="grimoire"))
        self.assertEqual(
            "27a594db73c6f445df5d478b3e32da7a34ef5204d64145723c51209efc6268fc",
            hashlib.sha256(texto.encode("ascii")).hexdigest())

    def test_cada_campo_fora_do_formato_nao_gera_ordem(self):
        tortos = [
            {"alvo": "a=b"}, {"alvo": "a\nb"}, {"alvo": "-a"}, {"alvo": ""},
            {"alvo": "a" * 129}, {"alvo": "café"},
            {"tipo": "voltar", "alvo": "Grimoire"},
            {"tipo": "voltar", "alvo": "gri_moire"},
            {"tipo": "voltar", "alvo": "-gri"},
            {"tipo": "voltar", "alvo": "g" * 64},
            {"numero": "4e1d2c3b5a6978f0e1d2c3b4a596877"},
            {"numero": "4e1d2c3b5a6978f0e1d2c3b4a59687788"},
            {"numero": "4E1D2C3B5A6978F0E1D2C3B4A5968778"},
            {"servidor": "g" + "0" * 31},
            {"criado": "01791558000"}, {"criado": 12345678901},
            {"criado": "1791558000"}, {"criado": True}, {"criado": -1},
            {"vence": 1791558299}, {"vence": 1791558301},
            {"tipo": "publicar"}, {"tipo": None},
        ]
        for troca in tortos:
            self.assertIsNone(tarefas.texto_da_ordem(dict(self.BASE, **troca)),
                              troca)

    def test_campo_faltando_ou_a_mais_nao_gera_ordem(self):
        for campo in self.BASE:
            falta = dict(self.BASE)
            del falta[campo]
            self.assertIsNone(tarefas.texto_da_ordem(falta), campo)
        self.assertIsNone(tarefas.texto_da_ordem(dict(self.BASE, extra="x")))
        self.assertIsNone(tarefas.texto_da_ordem("nao e dicionario"))
        self.assertIsNone(tarefas.texto_da_ordem(None))

    def test_a_lista_de_motivos_e_a_do_contrato(self):
        self.assertEqual(
            ("forma", "outro_servidor", "vencida", "assinatura", "desafio",
             "origem", "aparelho", "bloqueado", "desconhecido", "repetida",
             "cheio", "teto"), tarefas.MOTIVOS_DA_RECUSA)


if __name__ == "__main__":
    unittest.main(verbosity=2)
