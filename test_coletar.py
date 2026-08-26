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


class UrlSegura(unittest.TestCase):
    """A checagem que impede o coletor de virar varredor da rede interna.

    Hoje o casos.json e escrito so pelo dono e nada disso e necessario. Existe
    para o dia em que essa lista vier de outro lugar — e porque em 25/08/2026
    este projeto ja pagou caro por confiar em texto que vinha de fora.
    """

    def test_aceita_endereco_publico(self):
        self.assertTrue(coletar_github.url_segura("https://exemplo.com.br"))

    def test_recusa_localhost(self):
        self.assertFalse(coletar_github.url_segura("http://localhost:4777/"))
        self.assertFalse(coletar_github.url_segura("http://127.0.0.1/"))

    def test_recusa_rede_interna(self):
        self.assertFalse(coletar_github.url_segura("http://192.168.0.1/"))
        self.assertFalse(coletar_github.url_segura("http://10.0.0.5/"))

    def test_recusa_esquema_que_nao_e_web(self):
        for u in ("file:///C:/Users/Desktop/.ssh/id_rsa", "ftp://x.com",
                  "gopher://x.com", "", "nao e url"):
            self.assertFalse(coletar_github.url_segura(u), u)

    def test_recusa_o_nome_localhost_alem_do_ip(self):
        for u in ("http://localhost/", "http://meu.localhost/", "http://x.local/"):
            self.assertFalse(coletar_github.url_segura(u), u)

    def test_e_offline_nao_depende_de_dns(self):
        """Teste que consulta DNS e teste que falha na CI numa terca-feira.

        A resolucao de nome vive em host_publico(), chamada so por mede_site().
        """
        self.assertTrue(coletar_github.url_segura(
            "https://este-dominio-nao-existe-mesmo-987654.invalid"))


class HostPublico(unittest.TestCase):
    def test_nome_que_nao_resolve_nao_e_publico(self):
        self.assertFalse(coletar_github.host_publico(
            "este-dominio-nao-existe-mesmo-987654.invalid"))

    def test_ip_de_dentro_nao_e_publico(self):
        self.assertFalse(coletar_github.host_publico("127.0.0.1"))
        self.assertFalse(coletar_github.host_publico("192.168.0.1"))


class EscolherWorkflow(unittest.TestCase):
    def test_acha_pelo_caminho_do_arquivo(self):
        ws = [{"id": 1, "name": "CI", "path": ".github/workflows/ci.yml"},
              {"id": 2, "name": "Publicar", "path": ".github/workflows/deploy.yml"}]
        self.assertEqual(coletar_github.escolher_workflow(ws)["id"], 2)

    def test_acha_pelo_nome_em_portugues(self):
        ws = [{"id": 7, "name": "Publicar no servidor", "path": ".github/workflows/x.yml"}]
        self.assertEqual(coletar_github.escolher_workflow(ws)["id"], 7)

    def test_repositorio_sem_publicacao_devolve_vazio(self):
        ws = [{"id": 1, "name": "CI", "path": ".github/workflows/ci.yml"},
              {"id": 2, "name": "Testes", "path": ".github/workflows/test.yml"}]
        self.assertEqual(coletar_github.escolher_workflow(ws), {})

    def test_lista_ausente_nao_estoura(self):
        self.assertEqual(coletar_github.escolher_workflow(None), {})


class AtrasDe(unittest.TestCase):
    def test_le_o_numero_da_comparacao(self):
        self.assertEqual(coletar_github.atras_de({"ahead_by": 7}), 7)

    def test_em_dia_e_zero_e_nao_none(self):
        """Zero e uma medicao; None e 'nao sei'. A regra 16 trata os dois
        diferente — zero cala por estar em dia, None cala por ignorancia."""
        self.assertEqual(coletar_github.atras_de({"ahead_by": 0}), 0)

    def test_resposta_estranha_vira_nao_sei(self):
        for r in (None, {}, {"ahead_by": "sete"}, "erro", []):
            self.assertIsNone(coletar_github.atras_de(r), repr(r))


class MedeSite(unittest.TestCase):
    """Sobe um servidor de mentira em 127.0.0.1 e mede o classificador.

    Como a url_segura barra loopback de proposito, os testes chamam o
    classificador por dentro, com MEDIR_SITE ligado e a checagem substituida —
    a alternativa seria depender de um site real, e teste que depende da
    internet e teste que vai falhar na CI numa terca-feira qualquer.
    """

    def _mede(self, codigo):
        import http.server
        import threading

        class Mao(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(codigo)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), Mao)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        antes = (coletar_github.url_segura, coletar_github.host_publico)
        coletar_github.url_segura = lambda u: True
        coletar_github.host_publico = lambda h: True
        try:
            return coletar_github.mede_site("http://127.0.0.1:%d/" % srv.server_port)
        finally:
            coletar_github.url_segura, coletar_github.host_publico = antes
            srv.shutdown()

    def test_200_e_site_no_ar(self):
        r = self._mede(200)
        self.assertTrue(r["ok"])
        self.assertEqual(r["codigo"], 200)

    def test_redirecionamento_conta_como_vivo_e_nao_e_seguido(self):
        """301 ja e prova de que o servidor respondeu. Seguir o pulo levaria a
        requisicao para um dominio que este painel nao escolheu."""
        r = self._mede(301)
        self.assertTrue(r["ok"])
        self.assertEqual(r["codigo"], 301)

    def test_404_e_servidor_vivo_com_pagina_errada(self):
        self.assertTrue(self._mede(404)["ok"])

    def test_500_e_fora_do_ar(self):
        r = self._mede(503)
        self.assertFalse(r["ok"])
        self.assertEqual(r["codigo"], 503)

    def test_nao_respondeu_e_fora_do_ar(self):
        antes = (coletar_github.url_segura, coletar_github.host_publico)
        coletar_github.url_segura = lambda u: True
        coletar_github.host_publico = lambda h: True
        try:
            r = coletar_github.mede_site("http://127.0.0.1:9/")   # porta descartada
        finally:
            coletar_github.url_segura, coletar_github.host_publico = antes
        self.assertFalse(r["ok"])
        self.assertTrue(r["erro"])

    def test_url_recusada_devolve_nao_medido_e_nao_fora_do_ar(self):
        """A diferenca que evita alarme falso: None e 'nao medi', False e 'caiu'."""
        r = coletar_github.mede_site("http://localhost:1/")
        self.assertIsNone(r["ok"])

    def test_interruptor_desligado_nao_mede_nada(self):
        antes = coletar_github.MEDIR_SITE
        coletar_github.MEDIR_SITE = False
        try:
            self.assertIsNone(coletar_github.mede_site("https://exemplo.com.br")["ok"])
        finally:
            coletar_github.MEDIR_SITE = antes


class AlertaTemSeveridadeNaoSoContagem(unittest.TestCase):
    """"93 alertas" nao diz se sao 93 baixos ou 2 criticos.

    Medido em 25/08/2026: os 203 alertas dos quatro projetos vinham de 32
    pacotes, e os 6 "criticos" do workspace-medconsultoria eram DOIS CVEs de
    vitest repetidos por tres manifestos. Contagem bruta inverte a ordem do
    risco na tela.
    """

    def _no(self, alertas, total=None):
        return {"nameWithOwner": "o/r", "url": "https://g/o/r",
                "defaultBranchRef": {"name": "main", "target": {}},
                "pullRequests": {"nodes": []},
                "vulnerabilityAlerts": {
                    "totalCount": len(alertas) if total is None else total,
                    "nodes": alertas}}

    @staticmethod
    def _a(sev, pacote, ghsa, escopo="RUNTIME"):
        return {"dependencyScope": escopo,
                "securityAdvisory": {"ghsaId": ghsa},
                "securityVulnerability": {
                    "severity": sev,
                    "package": {"name": pacote, "ecosystem": "NPM"}}}

    def test_conta_por_severidade(self):
        no = self._no([self._a("CRITICAL", "vitest", "GHSA-1"),
                       self._a("CRITICAL", "vitest", "GHSA-2"),
                       self._a("HIGH", "next", "GHSA-3"),
                       self._a("MODERATE", "vite", "GHSA-4"),
                       self._a("LOW", "esbuild", "GHSA-5")])
        sev = coletar_github.traduz(no, True)["vulns"]["sev"]
        self.assertEqual(sev, {"critical": 2, "high": 1, "moderate": 1, "low": 1})

    def test_pacotes_distintos_e_o_tamanho_real_do_trabalho(self):
        """Tres alertas do mesmo pacote sao UM `npm update`, nao tres tarefas."""
        no = self._no([self._a("HIGH", "brace-expansion", "GHSA-1"),
                       self._a("HIGH", "brace-expansion", "GHSA-1"),
                       self._a("HIGH", "brace-expansion", "GHSA-1")])
        v = coletar_github.traduz(no, True)["vulns"]
        self.assertEqual(v["total"], 3)
        self.assertEqual(v["pacotes"], 1)
        self.assertEqual(v["defeitos"], 1)

    def test_mesmo_pacote_com_avisos_diferentes_sao_defeitos_diferentes(self):
        no = self._no([self._a("CRITICAL", "vitest", "GHSA-1"),
                       self._a("CRITICAL", "vitest", "GHSA-2")])
        v = coletar_github.traduz(no, True)["vulns"]
        self.assertEqual((v["pacotes"], v["defeitos"]), (1, 2))

    def test_escopo_e_exibido_como_fato_nunca_usado_para_rebaixar(self):
        """MEDIDO: o mesmo vitest volta DEVELOPMENT num manifesto e RUNTIME noutro.

        Rebaixar "e so ferramenta de teste" esconderia um critico de producao.
        O escopo entra no banco como numero, e a gravidade NAO olha para ele.
        """
        no = self._no([self._a("CRITICAL", "vitest", "GHSA-1", "DEVELOPMENT"),
                       self._a("CRITICAL", "vitest", "GHSA-1", "RUNTIME")])
        v = coletar_github.traduz(no, True)["vulns"]
        self.assertEqual(v["escopo"], {"runtime": 1, "development": 1})
        self.assertEqual(v["sev"]["critical"], 2)

    def test_severidade_desconhecida_nao_vira_baixa(self):
        """Campo que o GitHub nao mandou nao pode virar "moderado" por omissao."""
        no = self._no([{"dependencyScope": None, "securityAdvisory": {},
                        "securityVulnerability": {}}])
        v = coletar_github.traduz(no, True)["vulns"]
        self.assertEqual(v["total"], 1)
        self.assertEqual(sum(v["sev"].values()), 0)

    def test_sem_nodes_o_total_sobrevive_sozinho(self):
        """A permissao pode dar totalCount e recusar os nodes. O total vale.

        Sem esta trava, um degrau novo de permissao apagaria da tela um numero
        que hoje funciona.
        """
        no = {"nameWithOwner": "o/r", "url": "https://g/o/r",
              "defaultBranchRef": {"name": "main", "target": {}},
              "pullRequests": {"nodes": []},
              "vulnerabilityAlerts": {"totalCount": 93}}
        v = coletar_github.traduz(no, True)["vulns"]
        self.assertEqual(v["total"], 93)
        self.assertNotIn("sev", v)

    def test_nodes_truncados_nao_mentem_sobre_o_total(self):
        """O GraphQL traz no maximo 100 nos; 203 alertas nao cabem.

        Se os nos forem menos que o total, a soma das severidades NAO fecha e a
        tela nao pode dizer "6 criticos de 19" com base numa amostra.
        """
        no = self._no([self._a("HIGH", "next", "GHSA-1")], total=93)
        v = coletar_github.traduz(no, True)["vulns"]
        self.assertEqual(v["total"], 93)
        self.assertTrue(v["amostra"], "deveria marcar que a contagem e parcial")

class MemoriaCrlf(unittest.TestCase):
    """O varredor de fim de linha nas memorias. MEMORY.md fica de fora."""

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.antigo = coletar.PROJETOS_CLAUDE
        coletar.PROJETOS_CLAUDE = Path(self.pasta.name)
        self.repo = Path("C:/tmp/projeto-x")
        slug = str(self.repo).replace("\\", "-").replace("/", "-").replace(":", "-")
        self.memory = Path(self.pasta.name) / slug / "memory"
        self.memory.mkdir(parents=True)

    def tearDown(self):
        coletar.PROJETOS_CLAUDE = self.antigo
        self.pasta.cleanup()

    def _gravar(self, nome, crlf):
        fim = b"\r\n" if crlf else b"\n"
        (self.memory / nome).write_bytes(b"---" + fim + b"name: x" + fim + b"---" + fim)

    def test_memoria_em_crlf_e_apontada(self):
        self._gravar("uma-coisa.md", crlf=True)
        self.assertEqual(coletar.coleta_memoria_crlf(self.repo), ["uma-coisa.md"])

    def test_memoria_em_lf_nao_e_apontada(self):
        self._gravar("uma-coisa.md", crlf=False)
        self.assertEqual(coletar.coleta_memoria_crlf(self.repo), [])

    def test_MEMORY_md_em_crlf_NAO_e_apontado(self):
        """Ele nao tem frontmatter para o harness ignorar — nao ha falha ali."""
        self._gravar("MEMORY.md", crlf=True)
        self.assertEqual(coletar.coleta_memoria_crlf(self.repo), [])

    def test_MEMORY_md_nao_esconde_os_outros(self):
        self._gravar("MEMORY.md", crlf=True)
        self._gravar("outra.md", crlf=True)
        self.assertEqual(coletar.coleta_memoria_crlf(self.repo), ["outra.md"])


class PortasDoProc(unittest.TestCase):
    """O leitor de /proc/net/tcp — como o Linux conta quem esta escutando.

    Fora do Windows nao ha Get-NetTCPConnection. Sem este caminho, o coletor
    devolvia lista vazia em silencio e TODA porta de TODO projeto virava
    "fora do ar" — inclusive as que estavam respondendo.
    """

    CABECALHO = ("  sl  local_address rem_address   st tx_queue rx_queue tr "
                 "tm->when retrnsmt   uid  timeout inode\n")

    def test_le_a_porta_de_quem_escuta(self):
        # 1F90 = 8080. 0A = TCP_LISTEN.
        texto = self.CABECALHO + "   0: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 12345 1\n"
        self.assertEqual(coletar.portas_do_proc(texto), {8080})

    def test_ignora_conexao_que_nao_esta_escutando(self):
        # 01 = TCP_ESTABLISHED: e trafego saindo, nao servico de pe.
        texto = self.CABECALHO + "   0: 0100007F:1F90 0100007F:C350 01 00000000:00000000 00:00000000 00000000  1000        0 12345 1\n"
        self.assertEqual(coletar.portas_do_proc(texto), set())

    def test_aceita_endereco_ipv6_do_tcp6(self):
        seis = "00000000000000000000000001000000"
        texto = self.CABECALHO + "   0: " + seis + ":12A1 " + ("0" * 32) + ":0000 0A 00000000:00000000 00:00000000 00000000  1000        0 12345 1\n"
        self.assertEqual(coletar.portas_do_proc(texto), {4769})

    def test_linha_estragada_nao_derruba_a_leitura(self):
        texto = (self.CABECALHO
                 + "lixo que nao e linha nenhuma\n"
                 + "   1: 0100007F:1F90 00000000:0000 0A 0 0 0 0 0 0 1\n")
        self.assertEqual(coletar.portas_do_proc(texto), {8080})

    def test_texto_vazio_da_conjunto_vazio(self):
        self.assertEqual(coletar.portas_do_proc(""), set())


class NaoSaberNaoEDizerNao(unittest.TestCase):
    """Sem lista de portas, a decisao volta para a conexao de verdade.

    O defeito real (26/08/2026): `p in portas and porta_viva(p)`. Quando
    portas_escutando() nao conseguia responder, `portas` vinha vazio e o `and`
    dava False ANTES de tentar a conexao — o painel jurava que estava tudo fora
    do ar sem ter batido em porta nenhuma. Mentira por omissao.
    """

    def test_sem_lista_manda_testar(self):
        self.assertTrue(coletar.deve_testar(4777, None))

    def test_porta_na_lista_manda_testar(self):
        self.assertTrue(coletar.deve_testar(4777, {4777, 5432}))

    def test_porta_fora_da_lista_dispensa_o_teste(self):
        self.assertFalse(coletar.deve_testar(4777, {5432}))

    def test_lista_vazia_de_verdade_dispensa_o_teste(self):
        # Conjunto vazio e resposta: "medi, nao ha ninguem escutando".
        # E diferente de None, que e "nao consegui medir".
        self.assertFalse(coletar.deve_testar(4777, set()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
