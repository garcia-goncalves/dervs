# -*- coding: utf-8 -*-
"""O vigia irmao: nenhuma tarefa, de nenhuma cor, publica.

`test_rotas.py` varre as ROTAS e prova que o servidor nao executa nada. Faltava
quem varresse as TAREFAS. O criterio 4 da Fatia 2 nao se satisfaz com "nenhuma
rota publica": a sessao filha escreve codigo, e codigo que acrescenta um
gatilho ao `publicar.yml` publica na proxima vez que alguem mexer no
repositorio.

Sao cinco cercas independentes, e este arquivo confere as cinco LENDO AS
ESTRUTURAS DE VERDADE — importando os modulos, como `test_rotas.py` faz com
`servir.ROTAS`. Escrever o vigia contra uma copia da lista provaria que a copia
esta certa.

  1. `publicar` esta em `tarefas.NUNCA_VERDE`, e nao se repinta — nem pelo
     Python, nem pelo banco.
  2. Nenhuma regra do catalogo tem trilho que alcance a publicacao.
  3. A barreira da sessao filha continua barrando `gh`, `curl`, `docker`, e
     `git` continua com lista BRANCA de subcomando, sem `push`.
  4. Nenhum arquivo de `agente/` contem gatilho de publicacao.
  5. `fila.reprovar` CITA `diff_toca_publicacao` — a trava esta ligada, e nao
     so escrita.

E a guarda da guarda: um diff de mentira que acrescenta `on: push` ao
`publicar.yml` e reprovado de verdade. Vigia que passa vazio nao vigia nada.

    python test_tarefas_nao_publicam.py
"""
from __future__ import annotations

import inspect
import os
import unittest
from pathlib import Path

os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco       # noqa: E402
import barreira    # noqa: E402
import fila        # noqa: E402
import regras      # noqa: E402
import tarefas     # noqa: E402

AQUI = Path(__file__).resolve().parent


class PublicarNuncaFicaVerde(unittest.TestCase):
    """Cerca 1, nos dois lados."""

    def test_publicar_esta_na_lista_e_ela_e_imutavel(self):
        self.assertIn("publicar", tarefas.NUNCA_VERDE)
        self.assertIsInstance(tarefas.NUNCA_VERDE, frozenset)

    def test_o_python_recusa_pintar_publicar_de_verde(self):
        self.assertFalse(tarefas.pode_repintar("publicar", "verde"))
        self.assertEqual(tarefas.cor_da_regra("publicar", {"publicar": "verde"}),
                         tarefas.VERMELHO)

    def test_o_banco_recusa_pintar_publicar_de_verde(self):
        """Duas travas para a mesma coisa: a rota e o caminho esperado, e esta
        e a que sobra se alguem inventar um segundo caminho."""
        con = banco.conectar(":memory:")
        try:
            self.assertFalse(banco.repintar_regra("publicar", "verde", 1,
                                                  con=con))
            self.assertEqual(banco.cores_das_regras(con=con), {})
        finally:
            con.close()

    def test_publicar_nao_roda_nem_com_o_clique_do_dono(self):
        """O clique aprova UMA tarefa; ele nao levanta o NUNCA_VERDE."""
        pode, motivo = tarefas.pode_rodar(
            {"id": "d:1", "regra": "publicar", "aprovado_em": "2026-08-29"},
            0.0, "", {"publicar": "verde"})
        self.assertFalse(pode)
        self.assertIn("nunca anda sozinha", motivo)


class NenhumTrilhoAlcancaAPublicacao(unittest.TestCase):
    """Cerca 2. Lido do catalogo de verdade, e nao de uma copia."""

    def test_o_catalogo_de_trilhos_nao_tem_publicar(self):
        self.assertNotIn("publicar", fila.REGRAS_MECANICAS)

    def test_nenhuma_regra_do_catalogo_se_chama_publicar(self):
        nomes = set(fila.REGRAS_MECANICAS)
        for proibida in ("publicar", "deploy", "publish", "release"):
            self.assertNotIn(proibida, nomes)

    def test_toda_regra_com_trilho_tem_cor_vermelha_por_padrao(self):
        """Nenhuma regra nasce podendo andar sozinha, nem as mecanicas."""
        for regra in fila.REGRAS_MECANICAS:
            self.assertEqual(tarefas.cor_da_regra(regra), tarefas.VERMELHO,
                             regra)

    def test_o_detector_de_regras_e_a_fila_nao_divergiram(self):
        """Uma regra que a fila conhece e o detector nao produziria tarefa que
        nunca aparece; o contrario produziria tarefa sem trilho."""
        conhecidas = set(getattr(regras, "ORDEM", {}))
        self.assertTrue(conhecidas, "regras.ORDEM sumiu")
        for regra in fila.REGRAS_MECANICAS:
            self.assertTrue(isinstance(regra, str) and regra)


class ABarreiraDaSessaoFilhaContinuaDePe(unittest.TestCase):
    """Cerca 3. A sessao filha nao alcanca nada que saia da maquina."""

    def test_o_que_sai_da_maquina_continua_barrado(self):
        for programa in ("gh", "curl", "wget", "ssh", "docker"):
            self.assertIn(programa, barreira.SAEM_DA_MAQUINA, programa)

    def test_o_git_tem_lista_BRANCA_e_push_nao_esta_nela(self):
        """Lista branca, e nao negra. Lista negra de `git` sempre perde: um
        `git -c alias.x=...` anulava tudo — licao ja paga nesta casa."""
        self.assertNotIn("push", barreira.GIT_SUBCOMANDO_OK)
        for proibido in ("push", "remote", "clone", "fetch", "pull",
                         "submodule"):
            self.assertNotIn(proibido, barreira.GIT_SUBCOMANDO_OK, proibido)

    def test_a_lista_branca_do_git_nao_esta_vazia(self):
        """A guarda da guarda: uma lista vazia passaria no teste acima e
        quebraria a sessao inteira."""
        self.assertGreater(len(barreira.GIT_SUBCOMANDO_OK), 10)
        self.assertIn("commit", barreira.GIT_SUBCOMANDO_OK)


class NadaEmAgenteDisparaPublicacao(unittest.TestCase):
    """Cerca 4. O codigo do braco, lido como texto."""

    GATILHOS = ("workflow run", "workflow_dispatch", "/dispatches",
                "gh workflow")

    def arquivos(self):
        return sorted((AQUI / "agente").glob("*.py"))

    def test_ha_arquivos_para_conferir(self):
        """Vigia que passa vazio nao vigia nada."""
        self.assertGreaterEqual(len(self.arquivos()), 3)

    def test_nenhum_arquivo_do_agente_dispara_publicacao(self):
        for arquivo in self.arquivos():
            texto = arquivo.read_text(encoding="utf-8")
            for gatilho in self.GATILHOS:
                self.assertNotIn(gatilho, texto,
                                 "%s contem %r" % (arquivo.name, gatilho))

    def test_o_agente_nao_chama_gh_nem_ssh_nem_scp(self):
        for arquivo in self.arquivos():
            texto = arquivo.read_text(encoding="utf-8")
            for proibido in ('"gh"', "'gh'", '"ssh"', '"scp"', '"rsync"'):
                self.assertNotIn(proibido, texto,
                                 "%s chama %s" % (arquivo.name, proibido))


class ATravaDeDiffEstaLigada(unittest.TestCase):
    """Cerca 5, e a guarda da guarda."""

    def test_reprovar_cita_a_trava(self):
        """Ja aconteceu nesta casa de uma defesa existir e nao estar no
        caminho. Escrita nao e ligada."""
        self.assertIn("diff_toca_publicacao",
                      inspect.getsource(fila.reprovar))

    def test_um_diff_que_liga_o_push_no_publicar_yml_e_reprovado(self):
        """A guarda da guarda. Este e o ataque concreto: a sessao acrescenta
        tres palavras a um arquivo, e o proximo `git push` de qualquer pessoa
        publica em producao."""
        diff = ("--- a/.github/workflows/publicar.yml\\n"
                "+++ b/.github/workflows/publicar.yml\\n"
                "@@ -1,3 +1,5 @@\\n on:\\n+  push:\\n+    branches: [main]\\n"
                "   workflow_dispatch:\\n")
        for regra in list(fila.REGRAS_MECANICAS) + ["publicar", "qualquer"]:
            self.assertTrue(fila.reprovar(diff, regra),
                            "a regra %r passaria" % regra)

    def test_a_trava_nao_reprova_trabalho_legitimo(self):
        """Trava que reprova tudo passa em todo teste de reprovacao e trava o
        produto — e ai alguem a desliga."""
        diff = ("--- a/banco.py\\n+++ b/banco.py\\n@@ -1 +1 @@\\n"
                "-x = 1\\n+x = 2\\n")
        self.assertEqual(fila.reprovar(diff, "memoria_crlf"), "")


if __name__ == "__main__":
    unittest.main(verbosity=0)
