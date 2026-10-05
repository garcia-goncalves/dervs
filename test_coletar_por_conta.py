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
CREDENCIAIS = {"111": "ghs-conta-a", "222": "ghs-conta-b"}
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
                dados[alias] = None if slug in self.sem_alcance else {
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
        codigo, _s, _e = self.rodar()
        self.assertEqual(codigo, 1)
        for uid in (self.a, self.b):
            self.assertIn("sem o aplicativo", self.linha_github(uid)["motivo"])
        self.assertEqual(self.chamadas, [])

    def test_erro_inesperado_numa_conta_nao_derruba_a_outra(self):
        self.instalar_b()
        original = coletar_github._gravar_medicao

        def explode_na_b(con, dono, *a, **k):
            if dono == self.b:
                raise RuntimeError("segredo-na-excecao")
            return original(con, dono, *a, **k)
        self.addCleanup(setattr, coletar_github, "_gravar_medicao", original)
        coletar_github._gravar_medicao = explode_na_b
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
        self.assertEqual(c.TETO_CHAMADAS_POR_CONTA, 1 + 2 + 3 * c.TETO_REPOS_POR_CONTA)
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


class OCaminhoPorContaNaoTemCredencialImplicita(unittest.TestCase):
    """Guarda de codigo-fonte: o por conta nao alcanca nada que leia o ambiente,
    o app guardado ou o `gh`. Comportamento prova o caso que rodou; isto prova
    que nao existe o caminho."""

    PROIBIDOS = ("_token(", "_app(", "_gh_graphql(", "_gh_json(", "subprocess")

    def test_as_funcoes_do_por_conta_nao_tocam_o_caminho_antigo(self):
        for nome in ("coletar_por_conta", "_medir_uma_conta", "_graphql_com",
                     "_json_com", "_http_com"):
            fonte = inspect.getsource(getattr(coletar_github, nome))
            for proibido in self.PROIBIDOS:
                self.assertNotIn(proibido, fonte, "%s contem %s" % (nome, proibido))


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
