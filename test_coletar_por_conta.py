# -*- coding: utf-8 -*-
"""A coleta do GitHub POR CONTA (plano dervs-github-por-conta, etapas 3 e 4).

No servidor, o coletor antigo lia so a conta de teste e o bloco "No GitHub"
dizia "nunca foi medido" em todo projeto. O modo por conta mede cada conta com
a instalacao DELA. O risco que este arquivo vigia e o classico deste projeto:
a identidade sem o dono — a conta B lendo com a credencial da A, ou com o
token do ambiente, ou com o app guardado no modulo.

O duble de rede fica no ultimo degrau (`OpenerDirector.open`) e registra o
`Authorization` de CADA chamada, inclusive a troca da chave por token.

    python test_coletar_por_conta.py
"""
from __future__ import annotations

import contextlib
import inspect
import io
import json
import os
import re
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco            # noqa: E402
import coletar_github   # noqa: E402
from test_github_app import PEM_PKCS1   # noqa: E402

# Nomes compridos de proposito: "um" casaria dentro de "nenhum" e a busca por
# nome de projeto na saida ficaria verde (ou vermelha) por acidente.
PROJETOS_A = {"alfa-primeiro": "org-a/alfa-primeiro",
              "alfa-segundo": "org-a/alfa-segundo"}
PROJETOS_B = {"beta-terceiro": "org-b/beta-terceiro"}
CREDENCIAIS = {"111": "ghs-conta-a", "222": "ghs-conta-b",
               "333": "ghs-conta-a-org"}
PROIBIDAS = ("env-proibido", "app-global")
PEDACO = re.compile(r'(\w+): repository\(owner: "([^"]+)", name: "([^"]+)"\)')


class _Resposta:
    def __init__(self, corpo):
        self.corpo = json.dumps(corpo).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.corpo


class _AppGlobal:
    """O app guardado no modulo pelo caminho antigo. O por conta nunca o usa."""

    def token(self, agora=None):
        return "app-global"


class Base(unittest.TestCase):
    VARIAVEIS = ("DERVS_GITHUB_TOKEN", "DERVS_GITHUB_APP_ID",
                 "DERVS_GITHUB_INSTALLATION_ID", "DERVS_GITHUB_APP_KEY",
                 "DERVS_AMBIENTE")

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        antigo = banco.BANCO
        banco.BANCO = Path(self.dir.name) / "hub.db"
        self.addCleanup(setattr, banco, "BANCO", antigo)

        antes = {v: os.environ.get(v) for v in self.VARIAVEIS}

        def restaurar():
            for v, valor in antes.items():
                os.environ.pop(v, None)
                if valor is not None:
                    os.environ[v] = valor
        self.addCleanup(restaurar)
        os.environ["DERVS_GITHUB_APP_ID"] = "4739197"
        os.environ["DERVS_GITHUB_APP_KEY"] = PEM_PKCS1
        os.environ["DERVS_GITHUB_TOKEN"] = "env-proibido"
        os.environ["DERVS_GITHUB_INSTALLATION_ID"] = "999"

        self.addCleanup(setattr, coletar_github, "_APP_GUARDADO",
                        coletar_github._APP_GUARDADO)
        coletar_github._APP_GUARDADO = _AppGlobal()

        self.processos = []

        def sem_processo(*a, **k):
            self.processos.append(a)
            raise AssertionError("o caminho por conta rodou um processo")
        self.addCleanup(setattr, coletar_github.subprocess, "run",
                        coletar_github.subprocess.run)
        coletar_github.subprocess.run = sem_processo

        self.chamadas = []          # (url, metodo, authorization, corpo)
        self.recusar = set()        # instalacoes cujo access_tokens da 404
        self.sem_alcance = set()    # slugs que o GraphQL devolve como null
        self.alcance = {}           # token -> slugs que ELE enxerga (se houver)
        original = urllib.request.OpenerDirector.open
        self.addCleanup(setattr, urllib.request.OpenerDirector, "open", original)
        # Funcao solta, e nao `self._rede`: metodo ja ligado nao se liga de
        # novo ao abridor, e o pedido chegaria no parametro errado.
        urllib.request.OpenerDirector.open = (
            lambda abridor, pedido, timeout=None: self._rede(pedido))

        self.con = banco.conectar()
        self.addCleanup(self.con.close)
        self.a = banco.criar_usuario("a@teste.local", con=self.con)
        self.b = banco.criar_usuario("b@teste.local", con=self.con)
        for uid, projetos in ((self.a, PROJETOS_A), (self.b, PROJETOS_B)):
            for nome, slug in projetos.items():
                banco.gravar(nome, "local",
                             {"nome": nome, "git": {"remoto_slug": slug}},
                             self.con, usuario_id=uid)
        banco.guardar_instalacao_do_github(self.a, "111", con=self.con)
        self.con.commit()

    def instalar_b(self):
        banco.guardar_instalacao_do_github(self.b, "222", con=self.con)
        self.con.commit()

    # ------------------------------------------------------------ a rede falsa
    def _rede(self, pedido):
        url = pedido.full_url
        corpo = pedido.data.decode("utf-8") if pedido.data else ""
        self.chamadas.append((url, pedido.get_method(),
                              pedido.get_header("Authorization") or "", corpo))
        m = re.search(r"/app/installations/(\d+)/access_tokens$", url)
        if m:
            inst = m.group(1)
            if inst in self.recusar or inst not in CREDENCIAIS:
                raise urllib.error.HTTPError(url, 404, "nao existe", {}, None)
            return _Resposta({"token": CREDENCIAIS[inst],
                              "expires_at": "2099-01-01T00:00:00Z"})
        if url.endswith("/graphql"):
            consulta = json.loads(corpo)["query"]
            dados = {}
            for alias, dono, repo in PEDACO.findall(consulta):
                slug = "%s/%s" % (dono, repo)
                token = (pedido.get_header("Authorization") or "")[7:]
                nao_vejo = (token in self.alcance
                            and slug not in self.alcance[token])
                dados[alias] = None if (slug in self.sem_alcance
                                        or nao_vejo) else {
                    "nameWithOwner": slug, "url": "https://github.com/" + slug,
                    "defaultBranchRef": {"name": "main", "target": {}}}
            return _Resposta({"data": dados})
        if url.endswith("/actions/workflows"):
            return _Resposta({"workflows": []})
        raise urllib.error.HTTPError(url, 404, "nao existe", {}, None)

    def rodar(self):
        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            codigo = coletar_github.coletar_por_conta()
        return codigo, saida.getvalue(), erro.getvalue()

    def linha_github(self, uid):
        return banco.montar_estado(self.con, usuario_id=uid)["github_da_conta"]

    def com_github(self, uid):
        tudo = banco.ler_tudo(self.con, usuario_id=uid)
        return {n for n, c in tudo.items()
                if "github" in c and n not in banco.RESERVADOS}


class UmaContaUmaInstalacao(Base):
    """Criterio 2: cada conta so com os repositorios dela e a credencial dela."""

    def test_cada_conta_le_com_a_propria_credencial_e_so_os_proprios_slugs(self):
        self.instalar_b()
        codigo, _saida, _erro = self.rodar()
        self.assertEqual(codigo, 0)
        graphql = [c for c in self.chamadas if c[0].endswith("/graphql")]
        self.assertTrue(graphql)
        vistas = set()
        for _url, metodo, autorizacao, corpo in graphql:
            self.assertEqual(metodo, "POST")
            slugs = {"%s/%s" % (d, r) for _a, d, r in
                     PEDACO.findall(json.loads(corpo)["query"])}
            if slugs <= set(PROJETOS_A.values()):
                self.assertEqual(autorizacao, "Bearer ghs-conta-a")
                vistas.add("a")
            elif slugs <= set(PROJETOS_B.values()):
                self.assertEqual(autorizacao, "Bearer ghs-conta-b")
                vistas.add("b")
            else:
                self.fail("uma consulta misturou slugs de duas contas: %s" % slugs)
        self.assertEqual(vistas, {"a", "b"})
        # A REST da publicacao tambem vai com a credencial do dono do slug.
        for url, _m, autorizacao, _c in self.chamadas:
            if "/repos/org-a/" in url:
                self.assertEqual(autorizacao, "Bearer ghs-conta-a")
            if "/repos/org-b/" in url:
                self.assertEqual(autorizacao, "Bearer ghs-conta-b")
        self.assertEqual(self.com_github(self.a), set(PROJETOS_A))
        self.assertEqual(self.com_github(self.b), set(PROJETOS_B))
        self.assertIsNone(self.linha_github(self.a)["motivo"])
        self.assertEqual(self.linha_github(self.a)["medidos"], 2)
        self.assertEqual(self.linha_github(self.b)["medidos"], 1)

    def test_repositorio_que_nao_voltou_aparece_como_sem_alcance(self):
        self.instalar_b()
        self.sem_alcance = {"org-a/alfa-segundo"}
        self.rodar()
        linha = self.linha_github(self.a)
        self.assertEqual(linha["medidos"], 1)
        self.assertEqual(linha["repositorios"], 2)
        self.assertEqual(linha["sem_alcance"], ["alfa-segundo"])


class UmaContaComVariasInstalacoes(Base):
    """06/10/2026: pessoal + organizacao. Cada repositorio e medido pela
    instalacao que o alcanca, com a credencial DELA."""

    def duas(self):
        banco.guardar_instalacao_do_github(self.a, "333", con=self.con)
        self.con.commit()
        self.alcance = {"ghs-conta-a": {"org-a/alfa-primeiro"},
                        "ghs-conta-a-org": {"org-a/alfa-segundo"}}

    def test_cada_instalacao_mede_o_que_alcanca(self):
        self.duas()
        codigo, _s, _e = self.rodar()
        self.assertEqual(0, codigo)
        self.assertEqual(set(PROJETOS_A), self.com_github(self.a))
        linha = self.linha_github(self.a)
        self.assertEqual(2, linha["medidos"])
        self.assertEqual([], linha["sem_alcance"])
        self.assertIsNone(linha["motivo"])
        # a REST de cada repositorio vai com a credencial de quem o alcanca
        for url, _m, aut, _c in self.chamadas:
            if "/repos/org-a/alfa-segundo/" in url:
                self.assertEqual("Bearer ghs-conta-a-org", aut)
            if "/repos/org-a/alfa-primeiro/" in url:
                self.assertEqual("Bearer ghs-conta-a", aut)
        # a segunda instalacao so foi perguntar o que a primeira nao alcancou
        org = [json.loads(c[3])["query"] for c in self.chamadas
               if c[0].endswith("/graphql") and c[2] == "Bearer ghs-conta-a-org"]
        self.assertTrue(org)
        self.assertNotIn("alfa-primeiro", org[0])

    def test_a_contagem_por_instalacao_fica_gravada(self):
        self.duas()
        self.rodar()
        por = {i["installation_id"]: i["medidos"]
               for i in banco.instalacoes_da_conta(self.a, con=self.con)}
        self.assertEqual({"111": 1, "333": 1}, por)

    def test_instalacao_quebrada_nao_impede_a_outra(self):
        self.duas()
        self.recusar = {"111"}
        self.alcance = {}                 # a 333 enxerga tudo
        self.rodar()
        self.assertEqual(set(PROJETOS_A), self.com_github(self.a))
        self.assertEqual(2, self.linha_github(self.a)["medidos"])
        # A MORTA aparece no motivo, e "nao tentei" NUNCA vira "mediu 0" (Lei 2).
        self.assertIn("aplicativo desinstalado", self.linha_github(self.a)["motivo"])
        por = {i["installation_id"]: i["medidos"]
               for i in banco.instalacoes_da_conta(self.a, con=self.con)}
        self.assertIsNone(por["111"])
        self.assertEqual(2, por["333"])

    def test_nada_devolvido_por_uma_nao_apaga_o_aviso_das_outras(self):
        """A frase "o GitHub nao devolveu nenhum" de uma instalacao so vale se
        NINGUEM mediu; e o filtro nao pode levar junto os outros avisos."""
        self.duas()
        self.alcance = {"ghs-conta-a": set(),
                        "ghs-conta-a-org": set()}
        self.rodar()
        self.assertIn("o GitHub não devolveu nenhum",
                      self.linha_github(self.a)["motivo"])
        self.alcance = {"ghs-conta-a": set(),
                        "ghs-conta-a-org": {"org-a/alfa-primeiro",
                                            "org-a/alfa-segundo"}}
        self.rodar()
        self.assertIsNone(self.linha_github(self.a)["motivo"])

    def test_o_que_nenhuma_alcanca_continua_sem_alcance(self):
        self.duas()
        self.alcance = {"ghs-conta-a": {"org-a/alfa-primeiro"},
                        "ghs-conta-a-org": set()}
        self.rodar()
        linha = self.linha_github(self.a)
        self.assertEqual(1, linha["medidos"])
        self.assertEqual(["alfa-segundo"], linha["sem_alcance"])


class ContaSemInstalacaoNaoFicaVazia(Base):
    """Criterio 3: sem dados COM motivo, e a rodada segue para as outras."""

    def test_sem_instalacao_grava_motivo_e_a_outra_conta_e_medida(self):
        codigo, _s, _e = self.rodar()
        self.assertEqual(codigo, 0)
        linha = self.linha_github(self.b)
        self.assertTrue(linha["motivo"])
        self.assertIn("não conectou", linha["motivo"])
        self.assertEqual(self.com_github(self.b), set())
        self.assertEqual(self.com_github(self.a), set(PROJETOS_A))

    def test_instalacao_quebrada_grava_motivo_e_a_outra_conta_e_medida(self):
        self.instalar_b()
        self.recusar = {"222"}
        self.rodar()
        self.assertTrue(self.linha_github(self.b)["motivo"])
        self.assertEqual(self.com_github(self.b), set())
        self.assertEqual(self.com_github(self.a), set(PROJETOS_A))

    def test_servidor_sem_a_chave_do_app_diz_isso_em_cada_conta(self):
        os.environ.pop("DERVS_GITHUB_APP_KEY")
        codigo, _s, erro = self.rodar()
        self.assertEqual(codigo, 1)
        # `stderr` vai para `falhas_de_coleta` de TODAS as contas: sem numero.
        self.assertIn("FALHA: nenhuma conta foi medida nesta rodada", erro)
        self.assertNotRegex(erro, r"\d")
        for uid in (self.a, self.b):
            self.assertIn("sem o aplicativo", self.linha_github(uid)["motivo"])
        self.assertEqual(self.chamadas, [])

    def test_erro_inesperado_numa_conta_nao_derruba_a_outra(self):
        # Explode FORA do laco por repositorio (que tem `try` proprio): e o
        # `except` da conta que este caso vigia.
        self.instalar_b()
        original = coletar_github._graphql_com

        def explode_na_b(credencial, *a, **k):
            if credencial == CREDENCIAIS["222"]:
                raise RuntimeError("segredo-na-excecao")
            return original(credencial, *a, **k)
        self.addCleanup(setattr, coletar_github, "_graphql_com", original)
        coletar_github._graphql_com = explode_na_b
        codigo, saida, erro = self.rodar()
        self.assertEqual(codigo, 0)
        motivo = self.linha_github(self.b)["motivo"]
        self.assertEqual(motivo, "erro interno ao medir esta conta")
        self.assertNotIn("segredo-na-excecao", saida + erro)
        self.assertEqual(self.com_github(self.a), set(PROJETOS_A))


class FalhaFechadaDeToken(Base):
    """Criterio 4: token da conta B falhou -> nada de B sai com outra credencial."""

    def test_nada_de_b_vai_com_credencial_alheia(self):
        self.instalar_b()
        self.recusar = {"222"}
        self.rodar()
        for url, _m, autorizacao, corpo in self.chamadas:
            for proibida in PROIBIDAS:
                self.assertNotIn(proibida, autorizacao)
            self.assertNotIn("installations/999", url)
            if "org-b" in url or "org-b" in corpo:
                self.fail("uma chamada levou slug da conta B: %s" % url)
        self.assertEqual(self.processos, [])

    def test_mesmo_sem_falha_nada_vai_com_credencial_do_ambiente(self):
        self.instalar_b()
        self.rodar()
        for url, _m, autorizacao, _c in self.chamadas:
            for proibida in PROIBIDAS:
                self.assertNotIn(proibida, autorizacao)
            self.assertNotIn("installations/999", url)
        self.assertEqual(self.processos, [])


class SegredoNaoVaza(Base):
    """Criterio 5: nenhum token na saida, no erro nem no banco."""

    def test_nenhum_token_na_saida_nem_no_estado(self):
        self.instalar_b()
        self.recusar = {"222"}        # forca um caminho de falha tambem
        self.sem_alcance = {"org-a/alfa-segundo"}
        _codigo, saida, erro = self.rodar()
        jwts = {c[2].split(" ", 1)[-1] for c in self.chamadas
                if c[0].endswith("/access_tokens")}
        self.assertTrue(jwts)
        segredos = set(CREDENCIAIS.values()) | set(PROIBIDAS) | jwts | {PEM_PKCS1}
        gravado = " ".join(l[0] for l in self.con.execute(
            "SELECT dados FROM medida"))
        for segredo in segredos:
            self.assertNotIn(segredo, saida)
            self.assertNotIn(segredo, erro)
            self.assertNotIn(segredo, gravado)
        for nome in list(PROJETOS_A) + list(PROJETOS_B) + ["org-a", "org-b"]:
            self.assertNotIn(nome, erro)
            self.assertNotIn(nome, saida)


class TetoDeChamadasEPrazo(Base):
    """Criterio 6: mais contas multiplicam chamadas. O teto e por rodada, e
    estourar vira motivo escrito — nunca silencio, nunca "zero repositorios".

    Conta do duble, por rodada: A gasta 4 (token, GraphQL, workflows x2) e B
    gasta 3 (token, GraphQL, workflows)."""

    def teto(self, nome, valor):
        self.addCleanup(setattr, coletar_github, nome, getattr(coletar_github, nome))
        setattr(coletar_github, nome, valor)

    def test_as_constantes_sao_derivadas_e_o_prazo_cabe_no_do_servidor(self):
        c = coletar_github
        self.assertEqual(c.TETO_CHAMADAS_POR_CONTA, 1 + 2 + (3 + c.MAX_SHAS_NO_AR) * c.TETO_REPOS_POR_CONTA)
        self.assertEqual(c.TETO_CHAMADAS_POR_RODADA, 5 * c.TETO_CHAMADAS_POR_CONTA)
        fonte = Path("servir.py").read_text(encoding="utf-8")
        self.assertIn("timeout=600", fonte)
        self.assertLess(c.PRAZO_DA_RODADA, 600)

    def test_teto_da_rodada_acaba_antes_da_segunda_conta(self):
        self.instalar_b()
        self.teto("TETO_CHAMADAS_POR_RODADA", 4)
        self.rodar()
        self.assertLessEqual(len(self.chamadas), 4)
        self.assertEqual(self.com_github(self.a), set(PROJETOS_A))
        self.assertIn("teto", self.linha_github(self.b)["motivo"])
        self.assertEqual(self.com_github(self.b), set())

    def test_teto_no_meio_da_conta_diz_que_a_publicacao_nao_foi_relida(self):
        self.instalar_b()
        self.teto("TETO_CHAMADAS_POR_RODADA", 3)
        self.rodar()
        self.assertLessEqual(len(self.chamadas), 3)
        linha_a = self.linha_github(self.a)
        self.assertEqual(linha_a["medidos"], 2)
        self.assertIn("publicação de 1 projeto", linha_a["motivo"])
        self.assertIn("teto", self.linha_github(self.b)["motivo"])

    def test_teto_por_conta_tambem_vale(self):
        self.instalar_b()
        self.teto("TETO_CHAMADAS_POR_CONTA", 2)
        self.rodar()
        por_conta = {"a": 0, "b": 0}
        for url, _m, autorizacao, _c in self.chamadas:
            if "ghs-conta-a" in autorizacao:
                por_conta["a"] += 1
            if "ghs-conta-b" in autorizacao:
                por_conta["b"] += 1
        # O token gasta 1 (vai com o JWT); sobra 1 de credencial por conta.
        self.assertEqual(por_conta, {"a": 1, "b": 1})
        self.assertIn("publicação", self.linha_github(self.a)["motivo"])

    def test_repositorios_alem_do_teto_sao_anunciados(self):
        self.instalar_b()
        self.teto("TETO_REPOS_POR_CONTA", 1)
        self.rodar()
        linha = self.linha_github(self.a)
        self.assertEqual(linha["medidos"], 1)
        self.assertEqual(linha["repositorios"], 2)
        self.assertIn("1 de 2", linha["motivo"])
        for _url, _m, _a, corpo in self.chamadas:
            if corpo:
                self.assertLessEqual(len(PEDACO.findall(
                    json.loads(corpo)["query"])), 1)

    def test_prazo_vencido_vira_motivo_de_tempo_sem_chamar_nada(self):
        self.instalar_b()
        self.teto("PRAZO_DA_RODADA", 0)
        codigo, _s, _e = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertEqual(self.chamadas, [])
        for uid in (self.a, self.b):
            self.assertIn("tempo", self.linha_github(uid)["motivo"])


class OPrazoCobreOsSites(Base):
    """O prazo da rodada vale tambem para a medicao de sites: um site morto
    custa ~17 s em `mede_site`, e essa rede nao passa pelo orcamento."""

    ANTIGO = [{"servidor_id": 0, "servidor": "", "url": "https://antigo.example",
               "ok": False, "codigo": 503, "erro": "", "ms": 9,
               "medido_em": "2026-01-01T00:00:00+00:00"}]

    def test_prazo_vencido_depois_da_consulta_preserva_os_sites_antigos(self):
        for nome, slug in PROJETOS_A.items():
            banco.gravar(nome, "local",
                         {"nome": nome, "git": {"remoto_slug": slug},
                          "url_prod": "https://%s.example" % nome},
                         self.con, usuario_id=self.a)
            banco.gravar(nome, "github", {"slug": slug, "sites": self.ANTIGO},
                         self.con, usuario_id=self.a)
        self.con.commit()
        medidos = []

        def mede_site(url):
            medidos.append(url)
            return {"url": url, "ok": True, "codigo": 200, "erro": "", "ms": 1}
        self.addCleanup(setattr, coletar_github, "mede_site", coletar_github.mede_site)
        coletar_github.mede_site = mede_site
        original = coletar_github._graphql_com

        def e_o_tempo_acaba(credencial, consulta, orcamento=None):
            r = original(credencial, consulta, orcamento)
            orcamento.fim = 0        # o relogio passou do prazo DEPOIS da consulta
            return r
        self.addCleanup(setattr, coletar_github, "_graphql_com", original)
        coletar_github._graphql_com = e_o_tempo_acaba

        self.rodar()
        self.assertEqual(medidos, [])
        tudo = banco.ler_tudo(self.con, usuario_id=self.a)
        for nome in PROJETOS_A:
            self.assertEqual(tudo[nome]["github"]["dados"]["sites"], self.ANTIGO)
        linha = self.linha_github(self.a)
        self.assertEqual(linha["medidos"], 2)
        self.assertIn("a medição de sites de 2 projeto(s) ficou para a próxima "
                      "rodada", linha["motivo"])


class UmRepositorioRuimNaoDerrubaAConta(Base):
    """Cada repositorio e gravado e commitado por si: um que quebra nao apaga
    a medicao dos outros da mesma conta, nem a da conta seguinte."""

    def test_o_bom_e_gravado_e_o_ruim_vira_motivo_sem_o_texto_da_excecao(self):
        self.instalar_b()
        original = coletar_github.traduz

        def traduz(no, com_vulns):
            if no.get("nameWithOwner") == PROJETOS_A["alfa-segundo"]:
                raise RuntimeError("segredo-na-excecao")
            return original(no, com_vulns)
        self.addCleanup(setattr, coletar_github, "traduz", original)
        coletar_github.traduz = traduz
        codigo, saida, erro = self.rodar()
        self.assertEqual(codigo, 0)
        self.assertEqual(self.com_github(self.a), {"alfa-primeiro"})
        linha = self.linha_github(self.a)
        self.assertEqual(linha["medidos"], 1)
        self.assertIn("1 repositório(s) não puderam ser medidos", linha["motivo"])
        self.assertIn("alfa-segundo", linha["sem_alcance"])
        self.assertNotIn("segredo-na-excecao", linha["motivo"] + saida + erro)
        self.assertEqual(self.com_github(self.b), set(PROJETOS_B))


class AFalhaAoGravarOMotivoNaoContamina(Base):
    """O ramo `continue` de `coletar_por_conta`: a linha `_github` de uma
    conta nao grava; a outra conta segue, e sem herdar transacao aberta."""

    def test_a_outra_conta_segue_sem_transacao_aberta(self):
        self.instalar_b()
        gravar, ler_tudo = banco.gravar, banco.ler_tudo
        abertas = []

        def gravar_que_quebra(projeto, camada, dados, con, usuario_id=None, **k):
            r = gravar(projeto, camada, dados, con, usuario_id=usuario_id, **k)
            if projeto == banco.GITHUB_DA_CONTA and usuario_id == self.a:
                raise RuntimeError("disco cheio")     # DEPOIS de escrever
            return r

        def ler_tudo_espiao(con=None, usuario_id=None, **k):
            if usuario_id == self.b and con is not None:
                abertas.append(con.in_transaction)
            return ler_tudo(con, usuario_id=usuario_id, **k)
        self.addCleanup(setattr, banco, "gravar", gravar)
        self.addCleanup(setattr, banco, "ler_tudo", ler_tudo)
        banco.gravar, banco.ler_tudo = gravar_que_quebra, ler_tudo_espiao
        codigo, _s, _e = self.rodar()
        banco.gravar, banco.ler_tudo = gravar, ler_tudo
        self.assertEqual(codigo, 0)
        self.assertEqual(abertas[:1], [False])
        self.assertIsNone(self.linha_github(self.a))
        self.assertIsNone(self.linha_github(self.b)["motivo"])
        self.assertEqual(self.com_github(self.b), set(PROJETOS_B))


MALICIOSO = 'x"/y") { id } #'


class ODadoDoAgenteNaoDerrubaARodada(Base):
    """O relatorio do agente e dado de fora: `git` e `remoto_slug` podem vir
    em qualquer forma. Nada disso pode derrubar a rodada das outras contas,
    nem entrar cru na consulta GraphQL."""

    RUINS = {"ruim-nulo": None, "ruim-texto": "x", "ruim-numero": 5,
             "ruim-slug-numero": {"remoto_slug": 5},
             "ruim-aspas": {"remoto_slug": MALICIOSO}}

    def corpos(self):
        return " ".join(c[3] for c in self.chamadas if c[0].endswith("/graphql"))

    def test_relatorios_malformados_sao_descartados_e_as_contas_medidas(self):
        self.instalar_b()
        for nome, git in self.RUINS.items():
            banco.gravar(nome, "local", {"nome": nome, "git": git},
                         self.con, usuario_id=self.a)
        self.con.commit()
        codigo, _s, _e = self.rodar()
        self.assertEqual(codigo, 0)
        self.assertEqual(self.com_github(self.a), set(PROJETOS_A))
        self.assertEqual(self.com_github(self.b), set(PROJETOS_B))
        linha = self.linha_github(self.a)
        self.assertEqual(linha["repositorios"], 2)
        self.assertEqual(linha["sem_alcance"], [])
        self.assertNotIn('x\\"/y', self.corpos())
        self.assertNotIn("{ id }", self.corpos())

    def test_excecao_ao_ler_a_conta_vira_erro_interno_e_a_outra_segue(self):
        self.instalar_b()
        ler_tudo = banco.ler_tudo

        def quebra_na_a(con=None, usuario_id=None, **k):
            if usuario_id == self.a:
                raise TypeError("segredo-na-excecao")
            return ler_tudo(con, usuario_id=usuario_id, **k)
        self.addCleanup(setattr, banco, "ler_tudo", ler_tudo)
        banco.ler_tudo = quebra_na_a
        codigo, saida, erro = self.rodar()
        banco.ler_tudo = ler_tudo
        self.assertEqual(codigo, 0)
        self.assertEqual(self.linha_github(self.a)["motivo"],
                         coletar_github.ERRO_INTERNO)
        self.assertNotIn("segredo-na-excecao", saida + erro)
        self.assertEqual(self.com_github(self.b), set(PROJETOS_B))

    def test_slug_malicioso_nunca_entra_na_consulta(self):
        """Mesmo que `_slugs` deixe passar, `_consulta` recusa sozinha."""
        original = coletar_github._slugs

        def com_malicioso(tudo):
            slugs, por_alias = original(tudo)
            if "alfa-primeiro" in por_alias.values():
                slugs["r9"], por_alias["r9"] = MALICIOSO, "malicioso"
            return slugs, por_alias
        self.addCleanup(setattr, coletar_github, "_slugs", original)
        coletar_github._slugs = com_malicioso
        self.rodar()
        self.assertTrue(self.corpos())
        self.assertNotIn('x\\"/y', self.corpos())
        self.assertNotIn("r9:", self.corpos())
        self.assertEqual(self.com_github(self.a), set(PROJETOS_A))
        self.assertIn("malicioso", self.linha_github(self.a)["sem_alcance"])

    def test_consulta_direta_ignora_slug_invalido(self):
        q = coletar_github._consulta({"r0": MALICIOSO, "r1": "org-a/alfa-primeiro",
                                      "r2": "a/b/c", "r3": 5}, com_vulns=False)
        self.assertNotIn("r0:", q)
        self.assertNotIn("r2:", q)
        self.assertNotIn("r3:", q)
        self.assertIn('r1: repository(owner: "org-a", name: "alfa-primeiro")', q)


class OsSitesRespeitamPrazoETeto(Base):
    """O prazo e checado ANTES DE CADA site, e cada conta tem um teto de
    sites por rodada; o que sobrar fica para a proxima, anunciado."""

    ANTES = {"servidor_id": 2, "servidor": "s2", "url": "https://s2.example",
             "ok": False, "codigo": 503, "erro": "", "ms": 9,
             "medido_em": "2026-01-01T00:00:00+00:00"}

    def enderecos(self, mapa):
        def por_servidor(uid, con=None):
            return {nome: [{"servidor_id": i, "servidor": "s%d" % i,
                            "url": "https://%s-s%d.example" % (nome, i)}
                           for i in range(1, n + 1)]
                    for nome, n in mapa.items()}
        self.addCleanup(setattr, banco, "enderecos_por_servidor",
                        banco.enderecos_por_servidor)
        banco.enderecos_por_servidor = por_servidor

    def espiar_sites(self, ao_medir=None):
        medidos = []

        def mede_site(url):
            medidos.append(url)
            if ao_medir:
                ao_medir()
            return {"url": url, "ok": True, "codigo": 200, "erro": "", "ms": 1}
        self.addCleanup(setattr, coletar_github, "mede_site", coletar_github.mede_site)
        coletar_github.mede_site = mede_site
        return medidos

    def test_prazo_vence_no_meio_dos_sites_de_um_projeto(self):
        banco.gravar("alfa-primeiro", "github",
                     {"slug": "org-a/alfa-primeiro", "sites": [self.ANTES]},
                     self.con, usuario_id=self.a)
        self.con.commit()
        self.enderecos({"alfa-primeiro": 3})
        orcamentos = []
        original = coletar_github._graphql_com

        def guarda(credencial, consulta, orcamento=None):
            orcamentos.append(orcamento)
            return original(credencial, consulta, orcamento)
        self.addCleanup(setattr, coletar_github, "_graphql_com", original)
        coletar_github._graphql_com = guarda

        def vence():
            orcamentos[-1].fim = 0
        medidos = self.espiar_sites(vence)
        self.rodar()
        self.assertEqual(medidos, ["https://alfa-primeiro-s1.example"])
        sites = banco.ler_tudo(self.con, usuario_id=self.a)[
            "alfa-primeiro"]["github"]["dados"]["sites"]
        self.assertEqual([s["servidor_id"] for s in sites], [1, 2, 3])
        self.assertIs(sites[0]["ok"], True)
        self.assertEqual(sites[1], self.ANTES)          # preservado, carimbo antigo
        self.assertIsNone(sites[2]["ok"])               # nao medido nao e "fora"
        self.assertIn("a medição de sites de 1 projeto(s) ficou para a próxima",
                      self.linha_github(self.a)["motivo"])

    def test_teto_de_sites_por_conta(self):
        self.instalar_b()
        self.addCleanup(setattr, coletar_github, "TETO_SITES_POR_CONTA",
                        coletar_github.TETO_SITES_POR_CONTA)
        coletar_github.TETO_SITES_POR_CONTA = 2
        self.enderecos({"alfa-primeiro": 3, "alfa-segundo": 1, "beta-terceiro": 1})
        medidos = self.espiar_sites()
        self.rodar()
        da_a = [u for u in medidos if "alfa" in u]
        self.assertEqual(len(da_a), 2)
        # O teto e POR CONTA: a B tem o dela.
        self.assertIn("https://beta-terceiro-s1.example", medidos)
        self.assertIn("ficou para a próxima rodada", self.linha_github(self.a)["motivo"])
        self.assertIsNone(self.linha_github(self.b)["motivo"])

    def test_as_constantes_dos_sites_sao_derivadas(self):
        c = coletar_github
        self.assertGreaterEqual(c.PRAZO_POR_SITE, c.TENTATIVAS_SITE * c.TETO_SITE
                                + (c.TENTATIVAS_SITE - 1) * c.PAUSA_ENTRE_TENTATIVAS)
        self.assertEqual(c.TETO_SITES_POR_CONTA,
                         int(c.PRAZO_DA_RODADA * 3 / 4 // c.PRAZO_POR_SITE))
        self.assertGreater(c.TETO_SITES_POR_CONTA, 0)


class UmSiteQuePenduraTemPrazoTotal(unittest.TestCase):
    """`getresponse()` so tem prazo por leitura: um servidor que pinga um
    byte a cada 7 s pendura a medicao. O prazo total vem de fora."""

    def setUp(self):
        for nome in ("mede_site", "PRAZO_POR_SITE"):
            self.addCleanup(setattr, coletar_github, nome, getattr(coletar_github, nome))

    def test_site_que_pendura_vira_sem_resposta(self):
        import time as _t
        coletar_github.PRAZO_POR_SITE = 0.2
        coletar_github.mede_site = lambda url: _t.sleep(3) or {"ok": True}
        inicio = _t.monotonic()
        sites = coletar_github._monta_sites("x", [], "https://x.example", {})
        self.assertLess(_t.monotonic() - inicio, 2)
        self.assertEqual(len(sites), 1)
        self.assertIsNone(sites[0]["ok"])

    def test_excecao_da_medicao_continua_subindo(self):
        def quebra(url):
            raise RuntimeError("quebrou")
        coletar_github.mede_site = quebra
        with self.assertRaises(RuntimeError):
            coletar_github._monta_sites("x", [], "https://x.example", {})


class OCaminhoPorContaNaoTemCredencialImplicita(unittest.TestCase):
    """Guarda de codigo-fonte: o por conta nao alcanca nada que leia o ambiente,
    o app guardado ou o `gh`. Comportamento prova o caso que rodou; isto prova
    que nao existe o caminho."""

    PROIBIDOS = ("_token(", "_app(", "_gh_graphql(", "_gh_json(", "subprocess")

    def test_as_funcoes_do_por_conta_nao_tocam_o_caminho_antigo(self):
        for nome in ("coletar_por_conta", "_medir_uma_conta",
                     "_medir_com_instalacao", "_graphql_com",
                     "_json_com", "_http_com", "_gravar_medicao", "mede_deploy",
                     "mede_no_ar"):
            fonte = inspect.getsource(getattr(coletar_github, nome))
            for proibido in self.PROIBIDOS:
                self.assertNotIn(proibido, fonte, "%s contem %s" % (nome, proibido))

    def test_modo_por_conta_sem_buscar_e_recusado(self):
        """`buscar=None` cai em `_gh_json` dentro de `mede_deploy`. O modo por
        conta sempre passa `parar`; com ele, `buscar` e obrigatorio."""
        with self.assertRaises(ValueError):
            coletar_github._gravar_medicao(None, 1, {}, {}, {}, True, None,
                                           parar=lambda: False)

    def test_medir_uma_conta_passa_buscar_e_parar(self):
        fonte = inspect.getsource(coletar_github._medir_com_instalacao)
        self.assertRegex(fonte, r"_gravar_medicao\([^)]*buscar=buscar[^)]*parar=")


class ATrocaDeModo(unittest.TestCase):
    """O por conta so liga no servidor com o App configurado."""

    def setUp(self):
        antes = {v: os.environ.get(v) for v in Base.VARIAVEIS}

        def restaurar():
            for v, valor in antes.items():
                os.environ.pop(v, None)
                if valor is not None:
                    os.environ[v] = valor
        self.addCleanup(restaurar)
        for v in Base.VARIAVEIS:
            os.environ.pop(v, None)
        self.chamado = []
        self.addCleanup(setattr, coletar_github, "coletar_por_conta",
                        coletar_github.coletar_por_conta)
        coletar_github.coletar_por_conta = lambda: self.chamado.append(1) or 0
        # O caminho antigo, se rodar, nao acha slug nenhum e sai calado.
        for alvo, nome, valor in (
                (banco, "ler_tudo", lambda *a, **k: {}),
                (banco, "conta_local", lambda *a, **k: 1)):
            self.addCleanup(setattr, alvo, nome, getattr(alvo, nome))
            setattr(alvo, nome, valor)

    def _main(self):
        with contextlib.redirect_stderr(io.StringIO()):
            return coletar_github.main()

    def test_local_com_app_segue_no_caminho_antigo(self):
        os.environ["DERVS_AMBIENTE"] = "local"
        os.environ["DERVS_GITHUB_APP_ID"] = "4739197"
        self._main()
        self.assertEqual(self.chamado, [])

    def test_servidor_sem_app_segue_no_caminho_antigo(self):
        os.environ["DERVS_AMBIENTE"] = "producao"
        self._main()
        self.assertEqual(self.chamado, [])

    def test_servidor_com_app_vai_por_conta(self):
        os.environ["DERVS_AMBIENTE"] = "producao"
        os.environ["DERVS_GITHUB_APP_KEY"] = "qualquer"
        self._main()
        self.assertEqual(self.chamado, [1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
