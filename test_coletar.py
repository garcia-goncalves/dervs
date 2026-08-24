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


class ReconhecerArquivoDeTeste(unittest.TestCase):
    """O HUB dizia que ELE MESMO nao tinha teste, com 56 no disco."""

    def test_convencao_do_python(self):
        for nome in ("test_regras.py", "test_coletar.py", "conftest.py"):
            self.assertTrue(coletar.EH_TESTE.search(nome), nome)

    def test_convencao_do_javascript(self):
        for nome in ("botao.test.tsx", "api.spec.ts", "util_test.js"):
            self.assertTrue(coletar.EH_TESTE.search(nome), nome)

    def test_convencao_do_csharp(self):
        self.assertTrue(coletar.EH_TESTE.search("PedidoTests.cs"))

    def test_nao_confunde_arquivo_comum(self):
        for nome in ("regras.py", "servir.py", "index.html", "latest.py",
                     "protester.js"):
            self.assertFalse(coletar.EH_TESTE.search(nome), nome)


class PastasDeProjeto(unittest.TestCase):
    """O HUB tem de se vigiar. Ele mora fora de source/repos e ficava de fora."""

    def test_inclui_a_pasta_do_proprio_hub(self):
        nomes = {p.name for p in coletar.pastas_de_projeto()}
        self.assertIn(coletar.AQUI.name, nomes)

    def test_nao_duplica_se_a_avulsa_ja_estiver_na_raiz(self):
        """Se um dia o projeto for movido para source/repos, nao pode aparecer duas vezes."""
        caminhos = [str(p).lower() for p in coletar.pastas_de_projeto()]
        self.assertEqual(len(caminhos), len(set(caminhos)))

    def test_sem_a_pasta_de_repositorios_ainda_devolve_o_hub(self):
        """Contrato: a lista nunca fica vazia por causa do que ha na maquina.

        A primeira versao deste teste era "tem mais de 1 pasta", e passava so
        porque source/repos existe NESTA maquina. A CI pegou: no servidor do
        GitHub essa pasta nao existe. Teste que depende da maquina nao e teste.
        """
        original = coletar.RAIZ
        coletar.RAIZ = Path(r"C:\pasta\que\nao\existe")
        self.addCleanup(setattr, coletar, "RAIZ", original)
        nomes = {p.name for p in coletar.pastas_de_projeto()}
        self.assertEqual(nomes, {coletar.AQUI.name})


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


class ProntidaoSoCobraOQueSeAplica(unittest.TestCase):
    """A regua cobrava contêiner, deploy e docs/ de todo mundo.

    O proprio HUB tirava 64%: descontado por nao ter contêiner, nao ter arquivo
    de variaveis e nao ter workflow de publicacao — sendo que "sem dependencia e
    sem build" e virtude declarada dele, e ele nunca vai para servidor nenhum.
    Nota que cobra o impossivel treina o dono a ignorar a nota.
    """

    def _repo(self, *arquivos, pastas=()):
        d = Path(tempfile.mkdtemp())
        for nome in arquivos:
            (d / nome).parent.mkdir(parents=True, exist_ok=True)
            (d / nome).write_text("x", encoding="utf-8")
        for nome in pastas:
            (d / nome).mkdir(parents=True, exist_ok=True)
        return d

    def _arq(self, arquivos=10, testaveis=0, testes=0):
        return {"arquivos": arquivos, "linhas": arquivos * 10,
                "linhas_testaveis": testaveis, "arquivos_teste": testes,
                "linguagens": []}

    def _por_chave(self, pr):
        return {i["chave"]: i for i in pr["itens"]}

    # ---------------------------------------------------------------- Docker
    def test_docker_nao_se_aplica_a_quem_nao_declara_conteiner(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(), {})
        self.assertFalse(self._por_chave(pr)["docker"]["aplica"])

    def test_docker_se_aplica_a_quem_declara_conteiner_no_casos_json(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(), {"containers": ["medcrm"]})
        item = self._por_chave(pr)["docker"]
        self.assertTrue(item["aplica"])
        self.assertFalse(item["ok"])          # declara contêiner e nao tem compose

    # ---------------------------------------------------------------- deploy
    def test_deploy_nao_se_aplica_a_projeto_que_nunca_publica(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(), {})
        self.assertFalse(self._por_chave(pr)["deploy"]["aplica"])

    def test_deploy_se_aplica_a_quem_tem_endereco_de_producao(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(), {"url_prod": "https://x.com.br"})
        self.assertTrue(self._por_chave(pr)["deploy"]["aplica"])

    # ------------------------------------------------------------------ docs
    def test_docs_nao_se_aplica_a_projeto_pequeno(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(arquivos=24), {})
        self.assertFalse(self._por_chave(pr)["docs"]["aplica"])

    def test_docs_se_aplica_a_projeto_grande(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(arquivos=2602), {})
        self.assertTrue(self._por_chave(pr)["docs"]["aplica"])

    # ---------------------------------------------------------------- testes
    def test_teste_nao_e_cobrado_de_site_estatico(self):
        """Regra da casa: CSS, layout e texto de tela sao isentos de TDD."""
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(arquivos=35, testaveis=40), {})
        self.assertFalse(self._por_chave(pr)["testes"]["aplica"])

    def test_teste_e_cobrado_de_quem_tem_logica(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(arquivos=300, testaveis=25000), {})
        self.assertTrue(self._por_chave(pr)["testes"]["aplica"])

    # -------------------------------------------------------------------- CI
    def test_ci_nao_e_cobrada_de_pasta_sem_github(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"),
                                      {"versionado": True, "tem_remoto": False},
                                      self._arq(), {})
        self.assertFalse(self._por_chave(pr)["ci"]["aplica"])

    def test_nada_de_git_e_cobrado_de_pasta_sem_git(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": False},
                                      self._arq(), {})
        por = self._por_chave(pr)
        for chave in ("git_limpo", "ci", "gitignore"):
            self.assertFalse(por[chave]["aplica"], chave)

    # --------------------------------------------------------------- segredo
    def test_ter_arquivo_de_variaveis_local_nao_e_pecado(self):
        """Local e de mentira: senha de teste no arquivo e o certo, nao o errado.

        A regra antiga reprovava a mera existencia do arquivo, com o peso mais
        alto da regua — e derrubava 6 dos 17 projetos por fazerem o certo.
        """
        pr = coletar.coleta_prontidao(self._repo("README.md", coletar.ARQ_SEGREDO),
                                      {"versionado": True, "env_versionado": False},
                                      self._arq(), {})
        item = self._por_chave(pr)["segredo"]
        self.assertTrue(item["aplica"])
        self.assertTrue(item["ok"])

    def test_segredo_dentro_do_historico_e_pecado(self):
        pr = coletar.coleta_prontidao(self._repo("README.md", coletar.ARQ_SEGREDO),
                                      {"versionado": True, "env_versionado": True},
                                      self._arq(), {})
        self.assertFalse(self._por_chave(pr)["segredo"]["ok"])

    def test_sem_arquivo_de_variaveis_nao_ha_o_que_verificar(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"),
                                      {"versionado": True}, self._arq(), {})
        self.assertFalse(self._por_chave(pr)["segredo"]["aplica"])

    # ------------------------------------------------- exemplo de variaveis
    def test_exemplo_so_e_cobrado_de_quem_usa_variavel(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(), {})
        self.assertFalse(self._por_chave(pr)["env_exemplo"]["aplica"])
        pr2 = coletar.coleta_prontidao(self._repo("README.md", coletar.ARQ_SEGREDO),
                                       {"versionado": True}, self._arq(), {})
        self.assertTrue(self._por_chave(pr2)["env_exemplo"]["aplica"])

    # --------------------------------------------------------------- a conta
    def test_o_que_nao_se_aplica_sai_do_denominador(self):
        pr = coletar.coleta_prontidao(
            self._repo("README.md", ".gitignore"),
            {"versionado": True, "tem_remoto": False, "sujos": 0, "ahead": 0},
            self._arq(arquivos=24), {})
        aplicaveis = [i for i in pr["itens"] if i["aplica"]]
        self.assertEqual(pr["total"], sum(i["peso"] for i in aplicaveis))
        self.assertEqual(pr["pct"], 100)

    def test_dono_pode_desligar_um_criterio_pelo_casos_json(self):
        caso = {"url_prod": "https://x.com.br", "prontidao": {"deploy": False}}
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(), caso)
        self.assertFalse(self._por_chave(pr)["deploy"]["aplica"])

    def test_dono_pode_ligar_um_criterio_pelo_casos_json(self):
        caso = {"prontidao": {"docker": True}}
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq(), caso)
        item = self._por_chave(pr)["docker"]
        self.assertTrue(item["aplica"])
        self.assertFalse(item["ok"])

    def test_criterio_que_nao_se_aplica_nunca_conta_como_feito(self):
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": False},
                                      self._arq(), {})
        for i in pr["itens"]:
            if not i["aplica"]:
                self.assertFalse(i["ok"], i["chave"])

    def test_criterio_quebrado_nao_derruba_a_coleta(self):
        """Nenhum criterio pode explodir a coleta inteira de um projeto."""
        pr = coletar.coleta_prontidao(Path("nao/existe/em/lugar/nenhum"),
                                      {"versionado": True}, self._arq(), {})
        self.assertIsInstance(pr["pct"], int)

    def test_a_chamada_antiga_continua_valendo(self):
        """coleta_prontidao sem casos.json nao pode explodir."""
        pr = coletar.coleta_prontidao(self._repo("README.md"), {"versionado": True},
                                      self._arq())
        self.assertIsInstance(pr["pct"], int)


class LinhasTestaveis(unittest.TestCase):
    """Site de CSS e HTML nao devia ser cobrado por falta de teste."""

    def test_conta_so_linguagem_com_logica(self):
        d = Path(tempfile.mkdtemp())
        (d / "estilo.css").write_text("a{color:red}\n" * 300, encoding="utf-8")
        (d / "app.py").write_text("x = 1\n" * 40, encoding="utf-8")
        arq = coletar.coleta_arquivos(d)
        por_ling = {l["nome"]: l["linhas"] for l in arq["linguagens"]}
        # O numero exato segue a convencao antiga da casa (conta \n e soma 1
        # pela ultima linha). O contrato aqui e outro: so o Python entra.
        self.assertEqual(arq["linhas_testaveis"], por_ling["Python"])
        self.assertLess(arq["linhas_testaveis"], arq["linhas"])

    def test_css_e_html_sozinhos_nao_pedem_teste(self):
        d = Path(tempfile.mkdtemp())
        (d / "estilo.css").write_text("a{color:red}\n" * 300, encoding="utf-8")
        (d / "index.html").write_text("<p>oi</p>\n" * 300, encoding="utf-8")
        self.assertEqual(coletar.coleta_arquivos(d)["linhas_testaveis"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
