# -*- coding: utf-8 -*-
"""Testes dos pedacos do coletor que ja erraram de verdade.

Nao testa a coleta inteira (ela depende de git, Docker e da maquina). Testa as
funcoes puras onde um defeito produz numero errado com cara de certo — que e o
pior tipo de defeito num painel.

    python test_coletar.py
"""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

import coletar
import coletar_github


class NomeDoDb(unittest.TestCase):
    def test_traduz_caminho_do_windows(self):
        self.assertEqual(
            coletar.nome_do_db(r"C:\Users\Desktop\source\repos\dents"),
            "C-Users-Desktop-source-repos-dents")


class NomeDaMarca(unittest.TestCase):
    def test_usa_o_caminho_inteiro(self):
        self.assertEqual(
            coletar.nome_da_marca(r"C:\Users\Desktop\source\repos\dents"),
            "c-users-desktop-source-repos-dents")

    def test_nao_confunde_projeto_com_hifen_no_nome(self):
        """Casar so o fim do nome daria "sophia" para o o-que-e-que-eu-faco-sophia."""
        a = coletar.nome_da_marca(r"C:\r\o-que-e-que-eu-faco-sophia")
        b = coletar.nome_da_marca(r"C:\r\sophia")
        self.assertNotEqual(a, b)


class ChavesDoArquivoDeVariaveis(unittest.TestCase):
    """O vazamento de segredo achado na revisao de seguranca de 24/08/2026.

    O coletor abre o arquivo de variaveis para comparar com o exemplo. Ele so
    pode tirar dali NOMES. Estes testes sao a trava.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _arquivo(self, conteudo):
        alvo = Path(self.tmp.name) / coletar.ARQ_SEGREDO
        alvo.write_text(conteudo, encoding="utf-8")
        return alvo

    def test_le_nomes_simples(self):
        self.assertEqual(coletar._chaves_env(self._arquivo("A=1\nB=2\n")), {"A", "B"})

    def test_ignora_comentario_e_linha_vazia(self):
        self.assertEqual(coletar._chaves_env(self._arquivo("# C=1\n\nA=1\n")), {"A"})

    def test_chave_privada_multilinha_nao_vaza(self):
        """A ultima linha de um bloco PEM termina em "=" e casava como nome.

        O marcador e montado em pedacos de proposito: escrito inteiro, o varredor
        de segredos do repositorio barra o commit achando que e chave de verdade.
        """
        abre = "-----BEGIN RSA PRIVATE " + "KEY-----"
        fecha = "-----END RSA PRIVATE " + "KEY-----"
        alvo = self._arquivo(
            "DB_URL=postgres://x\n"
            'PRIVADA="' + abre + "\n"
            "zzZZmaterialFalsoSemBarraNemMaisNestaLinha0123456789abcdEEEE=\n"
            "MIIEowIBAAKCAQEAxxxxxx\n"
            + fecha + '"\n'
            "OUTRA=valor\n")
        self.assertEqual(coletar._chaves_env(alvo), {"DB_URL", "PRIVADA", "OUTRA"})

    def test_nome_absurdamente_longo_nao_e_nome(self):
        alvo = self._arquivo(("x" * 200) + "=1\nA=2\n")
        self.assertEqual(coletar._chaves_env(alvo), {"A"})

    def test_valor_entre_aspas_numa_linha_so_nao_abre_bloco(self):
        self.assertEqual(
            coletar._chaves_env(self._arquivo('A="um valor"\nB=2\n')), {"A", "B"})


class ColetaGrafo(unittest.TestCase):
    """O defeito real, medido em 24/08/2026.

    Casar o indice por sufixo ("termina em -medconsultoria") pegava tambem o
    workspace-medconsultoria. Como a ordem do glob e a do sistema de arquivos,
    o painel podia dizer "indexado ha 1 dia" para um repositorio cujo indice
    tinha 22 dias — ou para um que nunca foi indexado.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _db(self, caminho, dias_atras=0):
        alvo = self.cache / (coletar.nome_do_db(caminho) + ".db")
        alvo.write_bytes(b"")
        # 300 s de folga: sem isso a data cai exatamente na fronteira do dia e
        # a divisao inteira (dias COMPLETOS, que e o comportamento certo) devolve
        # N-1. O teste e que estava ambiguo, nao o codigo.
        quando = time.time() - dias_atras * 86400 - 300
        os.utime(alvo, (quando, quando))

    def test_acha_o_proprio_indice(self):
        self._db(r"C:\r\dents", dias_atras=3)
        self.assertEqual(coletar.coleta_grafo(r"C:\r\dents", self.cache),
                         {"indexado": True, "dias": 3})

    def test_nao_confunde_com_projeto_de_nome_parecido(self):
        self._db(r"C:\r\workspace-medconsultoria", dias_atras=1)
        # O medconsultoria NAO tem indice. Antes da correcao, o arquivo do
        # workspace casava por sufixo e ele aparecia como indexado ha 1 dia.
        self.assertEqual(coletar.coleta_grafo(r"C:\r\medconsultoria", self.cache),
                         {"indexado": False, "dias": None})

    def test_cada_um_com_a_sua_idade(self):
        self._db(r"C:\r\medconsultoria", dias_atras=22)
        self._db(r"C:\r\workspace-medconsultoria", dias_atras=1)
        self.assertEqual(coletar.coleta_grafo(r"C:\r\medconsultoria", self.cache)["dias"], 22)
        self.assertEqual(
            coletar.coleta_grafo(r"C:\r\workspace-medconsultoria", self.cache)["dias"], 1)

    def test_sem_indice_nenhum(self):
        self.assertFalse(coletar.coleta_grafo(r"C:\r\novo", self.cache)["indexado"])


class IdadeDoTrabalhoParado(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _arquivo(self, nome, dias_atras):
        alvo = self.repo / nome
        alvo.write_text("x", encoding="utf-8")
        quando = time.time() - dias_atras * 86400 - 300
        os.utime(alvo, (quando, quando))

    def test_pega_o_mais_antigo_e_nao_o_mais_recente(self):
        """A pergunta e "ha quanto tempo isso espera", nao "quando mexi por ultimo"."""
        self._arquivo("velho.txt", 5)
        self._arquivo("novo.txt", 0)
        sujos = [" M velho.txt", " M novo.txt"]
        self.assertEqual(coletar.idade_do_mais_antigo(self.repo, sujos), 5)

    def test_nome_com_acento_entra_na_conta(self):
        """Nome acentuado ja saiu da conta calado por causa do escape do git."""
        self._arquivo("relatório.md", 4)
        self.assertEqual(coletar.idade_do_mais_antigo(self.repo, [" M relatório.md"]), 4)

    def test_renomeado_usa_o_destino(self):
        self._arquivo("depois.txt", 2)
        self.assertEqual(
            coletar.idade_do_mais_antigo(self.repo, ["R  antes.txt -> depois.txt"]), 2)

    def test_arquivo_que_sumiu_nao_derruba(self):
        self._arquivo("existe.txt", 3)
        sujos = [" D apagado.txt", " M existe.txt"]
        self.assertEqual(coletar.idade_do_mais_antigo(self.repo, sujos), 3)

    def test_nada_sujo_devolve_none(self):
        self.assertIsNone(coletar.idade_do_mais_antigo(self.repo, []))


class TraduzGitHub(unittest.TestCase):
    def _no(self, estado, **extra):
        base = {
            "nameWithOwner": "dono/repo", "url": "https://github.com/dono/repo",
            "defaultBranchRef": {"name": "main",
                                 "target": {"statusCheckRollup": {"state": estado}}},
            "pullRequests": {"nodes": []},
        }
        base.update(extra)
        return base

    def test_falha_vira_falha(self):
        self.assertEqual(coletar_github.traduz(self._no("FAILURE"), False)["ci"]["conclusao"],
                         "failure")

    def test_rodando_ainda_nao_e_pendencia(self):
        """PENDING nao pode virar "CI vermelha": ainda esta rodando."""
        self.assertEqual(coletar_github.traduz(self._no("PENDING"), False)["ci"]["conclusao"], "")

    def test_repositorio_sem_ci_fica_calado(self):
        no = self._no("", defaultBranchRef={"name": "main", "target": {}})
        self.assertEqual(coletar_github.traduz(no, False)["ci"]["conclusao"], "")

    def test_rascunho_nao_conta_como_pr_esperando(self):
        no = self._no("SUCCESS", pullRequests={"nodes": [
            {"number": 1, "title": "wip", "url": "u", "updatedAt": "2026-08-01T00:00:00Z",
             "isDraft": True},
            {"number": 2, "title": "pronto", "url": "u", "updatedAt": "2026-08-01T00:00:00Z",
             "isDraft": False}]})
        prs = coletar_github.traduz(no, False)["prs"]
        self.assertEqual([p["numero"] for p in prs], [2])

    def test_sem_medir_alertas_devolve_vazio_e_nao_zero(self):
        """Vazio faz a regra ficar calada; zero afirmaria "nao ha alerta"."""
        self.assertEqual(coletar_github.traduz(self._no("SUCCESS"), False)["vulns"], {})

    def test_com_alertas_medidos(self):
        no = self._no("SUCCESS", vulnerabilityAlerts={"totalCount": 7})
        self.assertEqual(coletar_github.traduz(no, True)["vulns"]["total"], 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
