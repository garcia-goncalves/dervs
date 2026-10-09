# -*- coding: utf-8 -*-
"""Conectar simples, entrega A: o lado do SERVIDOR.

    python test_conectar_servidor.py

Contratos C1 a C14 de `docs/superpowers/plans/dervs-conectar-simples-a.md`.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco     # noqa: E402
import servir    # noqa: E402
from test_servir import BaseServidorDeVerdade  # noqa: E402

AQUI = Path(__file__).resolve().parent
CODIGO_CURTO = re.compile(r"^[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}$")
FRASE = "recarregue a pagina (token vencido)"


class APaginaVelhaTemMotivo(BaseServidorDeVerdade):
    """C1: todo 403 de anti-CSRF vencido carrega `motivo: pagina_velha`."""

    def test_toda_rota_de_escrita_do_dono_devolve_o_motivo(self):
        cookies, _csrf = self.sessao_e_token()
        vistas = []
        for caminho, rota in servir.ROTAS.items():
            if rota.metodo != "POST" or rota.acesso != "dado":
                continue
            r = self.pedir(caminho, "POST", {}, cookies=cookies,
                           cabecalhos={"X-Token": "token-errado"})
            vistas.append(caminho)
            self.assertEqual(403, r.status, caminho)
            corpo = json.loads(r.corpo)
            self.assertEqual("pagina_velha", corpo.get("motivo"), caminho)
            self.assertEqual(FRASE, corpo.get("erro"), caminho)
        self.assertGreater(len(vistas), 10)

    def test_os_outros_403_nao_ganham_motivo(self):
        cookies, csrf = self.sessao_e_token()
        r = self.pedir("/api/silenciar", "POST", {}, cookies=cookies,
                       com_origem=False, cabecalhos={"X-Token": csrf})
        self.assertEqual(403, r.status)
        self.assertNotIn("motivo", json.loads(r.corpo))

    def test_a_frase_mora_num_lugar_so(self):
        self.assertEqual(1, inspect.getsource(servir).count("token vencido"))


class _Base(BaseServidorDeVerdade):
    """Atalhos: o computador (sem cookie, sem Origin) e o dono (cookie + token)."""

    def computador(self, caminho, corpo=None, metodo="POST"):
        return self.pedir(caminho, metodo, corpo, com_origem=False)

    def json(self, r):
        return json.loads(r.corpo)

    def dono(self, caminho, corpo=None, metodo="POST", sessao=None):
        cookies, csrf = sessao or self.sessao_e_token()
        return self.pedir(caminho, metodo, corpo, cookies=cookies,
                          cabecalhos={"X-Token": csrf})

    def pedir_um(self, nome="PC-ESCRITORIO"):
        r = self.computador("/agente/pedir", {"maquina": nome})
        self.assertEqual(200, r.status, r.corpo)
        return self.json(r)

    def vencer(self, codigo):
        con = banco.conectar()
        try:
            con.execute("UPDATE pedido_de_computador SET expira_em = ?"
                        " WHERE codigo_hash = ?",
                        (banco.prazo(-3600), banco.hash_codigo(codigo)))
            con.commit()
        finally:
            con.close()


class OPedidoDeComputador(_Base):
    """C2 a C5 e C10 (so_mede)."""

    def test_pedir_devolve_os_campos_e_um_codigo_no_alfabeto(self):
        p = self.pedir_um()
        self.assertGreaterEqual(len(p["pedido"]), 43)
        self.assertRegex(p["codigo"], CODIGO_CURTO)
        self.assertEqual((10, 5), (p["minutos"], p["intervalo"]))

    def test_pedir_sem_nome_vira_computador_e_corpo_torto_e_400(self):
        c = self.pedir_um("")["codigo"]
        self.assertEqual("computador", self.json(
            self.dono("/api/pedido?codigo=" + c, metodo="GET"))["maquina"])
        r = self.computador("/agente/pedir", [1, 2])
        self.assertEqual(400, r.status)
        self.assertEqual({"erro": "pedido invalido"}, self.json(r))

    def test_esperar_antes_de_autorizar_e_202(self):
        p = self.pedir_um()
        r = self.computador("/agente/esperar", {"pedido": p["pedido"]})
        self.assertEqual(202, r.status)
        self.assertEqual({"estado": "esperando", "intervalo": 5}, self.json(r))

    def test_o_dono_ve_o_pedido_em_minuscula_e_sem_hifen(self):
        p = self.pedir_um("PC-A")
        sessao = self.sessao_e_token()
        for forma in (p["codigo"], p["codigo"].lower(),
                      p["codigo"].replace("-", "").lower()):
            r = self.dono("/api/pedido?codigo=" + forma, metodo="GET",
                          sessao=sessao)
            self.assertEqual(200, r.status, forma)
            corpo = self.json(r)
            self.assertEqual(
                (p["codigo"], "PC-A", "esperando"),
                (corpo["codigo"], corpo["maquina"], corpo["estado"]))
            self.assertIn(corpo["minutos"], (9, 10))

    def test_codigo_desconhecido_404_e_torto_400(self):
        sessao = self.sessao_e_token()
        r = self.dono("/api/pedido?codigo=ABCD-EFGH", metodo="GET", sessao=sessao)
        self.assertEqual((404, {"erro": "nao existe"}), (r.status, self.json(r)))
        for torto in ("K7M0-2QXP", "abc", ""):
            r = self.dono("/api/pedido?codigo=" + torto, metodo="GET",
                          sessao=sessao)
            self.assertEqual(400, r.status, torto)
            self.assertEqual({"erro": "codigo invalido"}, self.json(r))

    def test_pedido_sem_sessao_e_401(self):
        self.assertEqual(401, self.pedir("/api/pedido?codigo=ABCD-EFGH").status)

    def test_autorizar_e_resgatar_uma_vez_so(self):
        p = self.pedir_um("PC-B")
        r = self.dono("/api/pedido/autorizar", {"codigo": p["codigo"]})
        self.assertEqual(200, r.status, r.corpo)
        self.assertEqual({"ok": True, "maquina": "PC-B", "ja_estava": False},
                         self.json(r))
        r = self.dono("/api/pedido/autorizar", {"codigo": p["codigo"].lower()})
        self.assertTrue(self.json(r)["ja_estava"])
        r = self.computador("/agente/esperar", {"pedido": p["pedido"]})
        self.assertEqual(200, r.status, r.corpo)
        token = self.json(r)["token"]
        m = banco.maquina_por_token(token)
        self.assertEqual((self.uid, 1, 0, "PC-B"),
                         (m["usuario_id"], m["so_mede"], m["executa"], m["nome"]))
        self.assertIsNotNone(m["visto_em"])
        r = self.computador("/agente/esperar", {"pedido": p["pedido"]})
        self.assertEqual((404, {"erro": "nao existe"}), (r.status, self.json(r)))
        # E o dono agora le "conectado".
        r = self.dono("/api/pedido?codigo=" + p["codigo"], metodo="GET")
        self.assertEqual("conectado", self.json(r)["estado"])

    def test_esperar_com_pedido_torto_e_400_e_inventado_404(self):
        for torto in ({}, {"pedido": 5}, {"pedido": "curto"}, {"pedido": "x" * 129}):
            r = self.computador("/agente/esperar", torto)
            self.assertEqual(400, r.status, torto)
        r = self.computador("/agente/esperar", {"pedido": "x" * 43})
        self.assertEqual(404, r.status)

    def test_outra_conta_recebe_o_mesmo_404_de_nao_existe(self):
        p = self.pedir_um()
        self.assertEqual(200, self.dono("/api/pedido/autorizar",
                                        {"codigo": p["codigo"]}).status)
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("outra-pedido@teste.local", con=con)
            cookie = banco.novo_token()
            banco.abrir_sessao(outro, cookie, banco.prazo(3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
            s = banco.sessao_valida(final, con=con)
        finally:
            con.close()
        sessao = ({"sessao": final}, servir.Hub._csrf_da_sessao(s))
        nao = self.dono("/api/pedido?codigo=ABCD-EFGH", metodo="GET",
                        sessao=sessao)
        ver = self.dono("/api/pedido?codigo=" + p["codigo"], metodo="GET",
                        sessao=sessao)
        aut = self.dono("/api/pedido/autorizar", {"codigo": p["codigo"]},
                        sessao=sessao)
        self.assertEqual((404, self.json(nao)), (ver.status, self.json(ver)))
        self.assertEqual((404, self.json(nao)), (aut.status, self.json(aut)))

    def test_pedido_vencido_e_404_em_todo_lado(self):
        p = self.pedir_um()
        self.vencer(p["codigo"])
        self.assertEqual(404, self.dono("/api/pedido?codigo=" + p["codigo"],
                                        metodo="GET").status)
        self.assertEqual(404, self.dono("/api/pedido/autorizar",
                                        {"codigo": p["codigo"]}).status)
        self.assertEqual(404, self.computador(
            "/agente/esperar", {"pedido": p["pedido"]}).status)

    def test_pedir_limpa_o_pedido_vencido(self):
        p = self.pedir_um()
        self.vencer(p["codigo"])
        self.pedir_um()
        con = banco.conectar()
        try:
            n = con.execute("SELECT COUNT(*) FROM pedido_de_computador"
                            " WHERE codigo_hash = ?",
                            (banco.hash_codigo(p["codigo"]),)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(0, n)

    def test_autorizar_sem_origem_ou_com_token_errado(self):
        p = self.pedir_um()
        cookies, csrf = self.sessao_e_token()
        r = self.pedir("/api/pedido/autorizar", "POST", {"codigo": p["codigo"]},
                       cookies=cookies, com_origem=False,
                       cabecalhos={"X-Token": csrf})
        self.assertEqual(403, r.status)
        r = self.pedir("/api/pedido/autorizar", "POST", {"codigo": p["codigo"]},
                       cookies=cookies, cabecalhos={"X-Token": "errado"})
        self.assertEqual("pagina_velha", self.json(r)["motivo"])
        r = self.dono("/api/pedido/autorizar", {"codigo": "torto"})
        self.assertEqual((400, {"erro": "codigo invalido"}),
                         (r.status, self.json(r)))

    def test_tetos_sao_balcoes_separados(self):
        for _ in range(servir.Hub.TETO_DE_PEDIDOS):
            self.assertEqual(200, self.computador("/agente/pedir", {}).status)
        r = self.computador("/agente/pedir", {})
        self.assertEqual((429, {"erro": "nao deu"}), (r.status, self.json(r)))
        sessao = self.sessao_e_token()
        for _ in range(servir.Hub.TETO_DE_CODIGOS_CURTOS):
            self.dono("/api/pedido?codigo=ABCD-EFGH", metodo="GET", sessao=sessao)
        self.assertEqual(429, self.dono("/api/pedido?codigo=ABCD-EFGH",
                                        metodo="GET", sessao=sessao).status)
        self.assertEqual(429, self.dono("/api/pedido/autorizar",
                                        {"codigo": "ABCD-EFGH"},
                                        sessao=sessao).status)
        # Nenhum deles tranca a cortina do dono, nem o chute de pareamento.
        self.assertEqual(204, self.pedir(
            "/entrada", "POST", {"combinacao": self.combinacao}).status)
        self.assertNotEqual(429, self.computador(
            "/agente/esperar", {"pedido": "x" * 43}).status)

    def test_o_teto_de_esperas(self):
        for _ in range(servir.Hub.TETO_DE_ESPERAS):
            self.computador("/agente/esperar", {"pedido": "x" * 43})
        self.assertEqual(429, self.computador(
            "/agente/esperar", {"pedido": "x" * 43}).status)

    def test_ligar_a_execucao_de_quem_so_mede_e_409(self):
        p = self.pedir_um()
        self.dono("/api/pedido/autorizar", {"codigo": p["codigo"]})
        token = self.json(self.computador(
            "/agente/esperar", {"pedido": p["pedido"]}))["token"]
        mid = banco.maquina_por_token(token)["id"]
        r = self.dono("/api/maquinas/autorizar", {"id": mid, "ligado": True})
        self.assertEqual((409, {"erro": "este computador so mede"}),
                         (r.status, self.json(r)))
        self.assertEqual(0, banco.maquina_por_token(token)["executa"])
        # Desligar continua valendo.
        r = self.dono("/api/maquinas/autorizar", {"id": mid, "ligado": False})
        self.assertEqual(200, r.status)

    def test_maquinas_traz_so_mede_e_relatado_em(self):
        p = self.pedir_um("PC-C")
        self.dono("/api/pedido/autorizar", {"codigo": p["codigo"]})
        self.computador("/agente/esperar", {"pedido": p["pedido"]})
        lista = self.json(self.dono("/api/maquinas", metodo="GET"))
        itens = lista["maquinas"] if isinstance(lista, dict) else lista
        m = next(x for x in itens if x["nome"] == "PC-C")
        self.assertIs(True, m["so_mede"])
        self.assertIsNone(m["relatado_em"])
        self.assertEqual([], m["projetos_vistos"])


class OPacote(_Base):
    """C6."""

    def token(self):
        return self.maquina_com_token("pc-pacote", autorizada=False)

    def pegar(self, token):
        return self.pedir("/agente/pacote", "GET", com_origem=False,
                          cabecalhos={"Authorization": "Token " + token})

    def test_sem_token_e_401(self):
        self.assertEqual(401, self.pedir("/agente/pacote", com_origem=False).status)

    def test_entrega_na_ordem_com_o_conteudo_do_disco(self):
        t, _ = self.token()
        r = self.pegar(t)
        self.assertEqual(200, r.status)
        corpo = self.json(r)
        self.assertEqual(list(servir.Hub.PACOTE),
                         [a["caminho"] for a in corpo["arquivos"]])
        total = ""
        for a in corpo["arquivos"]:
            disco = (AQUI / a["caminho"]).read_bytes().decode("utf-8")
            self.assertEqual(disco, a["conteudo"])
            total += a["caminho"] + "\n" + a["conteudo"] + "\n"
        self.assertEqual(hashlib.sha256(total.encode("utf-8")).hexdigest(),
                         corpo["versao"])
        self.assertIs(False, corpo["so_mede"])

    def test_so_mede_vem_verdadeiro_para_quem_pareou_pelo_arquivo(self):
        p = self.pedir_um()
        self.dono("/api/pedido/autorizar", {"codigo": p["codigo"]})
        token = self.json(self.computador(
            "/agente/esperar", {"pedido": p["pedido"]}))["token"]
        self.assertIs(True, self.json(self.pegar(token))["so_mede"])

    def test_o_decimo_primeiro_pedido_e_429(self):
        t, _ = self.token()
        for _ in range(servir.Hub.TETO_DE_PACOTES):
            self.assertEqual(200, self.pegar(t).status)
        r = self.pegar(t)
        self.assertEqual((429, {"erro": "nao deu"}), (r.status, self.json(r)))

    def test_pacote_parcial_nunca_sai(self):
        t, _ = self.token()
        falso = servir.Hub.PACOTE + ("nao_existe_aqui.py",)
        with mock.patch.object(servir.Hub, "PACOTE", falso):
            r = self.pegar(t)
        self.assertEqual(503, r.status)
        self.assertEqual({"erro": "o pacote nao esta nesta copia"}, self.json(r))

    def test_os_imports_do_ajudante_cabem_no_pacote(self):
        """O passeio so olha import de NIVEL DE MODULO: o `from agente import
        executor` de dentro de funcao fica de fora de proposito."""
        modulos = {Path(c).stem for c in servir.Hub.PACOTE if "/" not in c}
        vistos, fila = set(), ["agente/enviar.py"]
        while fila:
            caminho = fila.pop()
            arvore = ast.parse((AQUI / caminho).read_text(encoding="utf-8"))
            for nomes in _imports_de_modulo(arvore):
                for nome in nomes:
                    if (AQUI / (nome + ".py")).exists() and nome not in vistos:
                        vistos.add(nome)
                        fila.append(nome + ".py")
        self.assertGreaterEqual(vistos, {"coletar", "tarefas"})
        self.assertLessEqual(vistos, modulos)
        for fora in ("execucao", "fila", "barreira", "executor"):
            self.assertNotIn(fora, vistos)
        self.assertNotIn("agente/executor.py", servir.Hub.PACOTE)


def _imports_de_modulo(arvore):
    """Os nomes importados fora de qualquer funcao."""
    achados = []

    def andar(no):
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.Lambda)):
                continue
            if isinstance(filho, ast.Import):
                achados.append([a.name.split(".")[0] for a in filho.names])
            elif (isinstance(filho, ast.ImportFrom) and filho.module
                  and not filho.level):
                achados.append([filho.module.split(".")[0]])
            andar(filho)
    andar(arvore)
    return achados


class OArquivoDeConectar(_Base):
    """C7. Os dois arquivos vem de fixture propria, sem depender do E1."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cmd = Path(self.tmp.name) / "conectador.cmd"
        py = Path(self.tmp.name) / "conectador.py"
        cmd.write_bytes(b"@echo off\nrem molde\nexit /b %ERRORLEVEL%\n")
        py.write_bytes(b'ALVO = "http://x"   # DERVS:ALVO\nprint(ALVO)\n')
        for nome, caminho in (("CONECTADOR_CMD", cmd), ("CONECTADOR", py)):
            p = mock.patch.object(servir.Hub, nome, caminho)
            p.start()
            self.addCleanup(p.stop)
        self.cmd, self.py = cmd, py

    def baixar(self):
        return self.pedir("/api/conectar.cmd", "GET", cookies=self.com_sessao())

    def test_sem_sessao_e_401(self):
        self.assertEqual(401, self.pedir("/api/conectar.cmd").status)

    def test_cabecalhos_e_corpo(self):
        r = self.baixar()
        self.assertEqual(200, r.status)
        self.assertEqual("application/octet-stream",
                         r.cabecalhos.get("Content-Type"))
        self.assertEqual('attachment; filename="conectar-dervs.cmd"',
                         r.cabecalhos.get("Content-Disposition"))
        cru = r.corpo.encode("ascii")
        self.assertIsNone(re.search(rb"(?<!\r)\n", cru))
        linhas = r.corpo.split("\r\n")
        self.assertEqual(1, linhas.count("#:DERVS-PYTHON"))
        i = linhas.index("#:DERVS-PYTHON")
        self.assertTrue(linhas[i - 1].startswith("exit /b"))
        self.assertIn('ALVO = "http://127.0.0.1:%d"   # DERVS:ALVO' % self.porta,
                      linhas)
        self.assertEqual("", linhas[-1])

    def test_o_endereco_do_dominio_publico_e_https(self):
        with mock.patch.object(servir, "DOMINIO", "dervs.exemplo.br"):
            r = self.baixar()
        self.assertIn('ALVO = "https://dervs.exemplo.br"', r.corpo)

    def test_a_rota_nao_cria_pareamento(self):
        def contas():
            con = banco.conectar()
            try:
                return (con.execute("SELECT COUNT(*) FROM pareamento").fetchone()[0],
                        con.execute("SELECT COUNT(*) FROM pedido_de_computador"
                                    ).fetchone()[0])
            finally:
                con.close()
        antes = contas()
        self.baixar()
        self.assertEqual(antes, contas())

    def test_arquivo_ausente_e_503(self):
        for nome in ("CONECTADOR_CMD", "CONECTADOR"):
            with mock.patch.object(servir.Hub, nome, Path(self.tmp.name) / "nada"):
                r = self.baixar()
            self.assertEqual(503, r.status, nome)
            self.assertEqual({"erro": "o arquivo de conectar nao esta nesta copia"},
                             self.json(r))

    def test_sem_a_marca_do_alvo_ou_nao_ascii_nao_sai(self):
        self.py.write_bytes(b"print(1)\n")
        self.assertEqual(503, self.baixar().status)
        self.py.write_bytes('ALVO = "x"   # DERVS:ALVO\n# café\n'.encode("utf-8"))
        self.assertEqual(503, self.baixar().status)

    def test_o_servidor_nao_ganhou_atributo_conectador(self):
        """Importar o conectador arrastaria `tkinter` para dentro do servidor."""
        self.assertFalse(hasattr(servir, "conectador"))
        self.assertNotIn("conectador", getattr(servir, "__dict__", {}))

    def test_a_rota_antiga_morreu(self):
        self.assertNotIn("/api/conectador", servir.ROTAS)
        self.assertFalse(hasattr(servir.Hub, "_conectador"))


def _projeto(nome, caminho=None):
    """Um projeto com UMA pendencia (exemplo de variaveis divergente)."""
    return {"nome": nome, "caminho": caminho or "C:/p/" + nome,
            "git": {"versionado": True},
            "env_drift": {"faltando": ["A"], "sobrando": []}}


class OProjetoOculto(_Base):
    """C8, C9 e a parte `projetos_vistos` de C10."""

    def setUp(self):
        super().setUp()
        con = banco.conectar()
        try:
            for t in ("projeto_oculto", "projeto_conectado", "medida"):
                con.execute("DELETE FROM %s" % t)
            con.execute("DELETE FROM maquina")
            con.commit()
        finally:
            con.close()
        self.token, self.mid = self.maquina_com_token("pc-oculto",
                                                      autorizada=False)

    def relatar(self, *nomes):
        banco.receber_relatorio(self.mid, [_projeto(n) for n in nomes])

    def dados(self):
        r = self.dono("/api/dados", metodo="GET")
        self.assertEqual(200, r.status)
        return self.json(r)

    def mostrar(self, projeto, mostrar, sessao=None):
        return self.dono("/api/projetos/mostrar",
                         {"projeto": projeto, "mostrar": mostrar}, sessao=sessao)

    def test_esconder_tira_de_projetos_pendencias_e_grupos(self):
        self.relatar("x", "y")
        antes = self.dados()
        self.assertEqual([], antes["ocultos"])
        self.assertEqual({"x", "y"}, {p["nome"] for p in antes["projetos"]})
        r = self.mostrar("x", False)
        self.assertEqual(200, r.status, r.corpo)
        self.assertEqual({"projeto": "x", "mostrar": False, "ocultos_n": 1},
                         self.json(r))
        d = self.dados()
        self.assertEqual(["x"], d["ocultos"])
        self.assertEqual(["y"], [p["nome"] for p in d["projetos"]])
        self.assertEqual({"y"}, {p["projeto"] for p in d["pendencias"]})
        self.assertNotIn('"x"', json.dumps(d["grupos"]))
        self.assertNotIn("projeto x", d["briefing"])

    def test_relatorio_novo_nao_traz_de_volta_e_mostrar_traz(self):
        self.relatar("x", "y")
        self.mostrar("x", False)
        self.relatar("x", "y")
        self.assertEqual(["y"], [p["nome"] for p in self.dados()["projetos"]])
        r = self.mostrar("x", True)
        self.assertEqual(0, self.json(r)["ocultos_n"])
        d = self.dados()
        self.assertEqual({"x", "y"}, {p["nome"] for p in d["projetos"]})
        self.assertEqual([], d["ocultos"])

    def test_o_estado_do_banco_continua_com_o_escondido(self):
        """A poda e em `_dados`, DEPOIS do motor: o motor (e a vigilia do VOZ)
        leem `montar_estado` inteiro."""
        self.relatar("x", "y")
        self.mostrar("x", False)
        con = banco.conectar()
        try:
            e = banco.montar_estado(con, usuario_id=self.uid)
        finally:
            con.close()
        self.assertIn("x", {p["nome"] for p in e["projetos"]})
        self.assertIn("x", {p["projeto"] for p in self.estado_da_conta()["pendencias"]})

    def estado_da_conta(self):
        h = servir.Hub.__new__(servir.Hub)
        return h._estado(self.uid)

    def test_projeto_desconhecido_ou_de_outra_conta_e_404(self):
        self.relatar("x")
        r = self.mostrar("nao-existe", False)
        self.assertEqual((404, {"erro": "nao existe"}), (r.status, self.json(r)))
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("outro-oculto@teste.local", con=con)
            banco.gravar("so-do-outro", "local", {"nome": "so-do-outro"},
                         con=con, usuario_id=outro)
        finally:
            con.close()
        self.assertEqual(404, self.mostrar("so-do-outro", False).status)

    def test_corpo_torto_e_400(self):
        self.relatar("x")
        for corpo in ({"projeto": "x", "mostrar": "nao"},
                      {"projeto": "x", "mostrar": 0},
                      {"projeto": "x"},
                      {"projeto": "", "mostrar": False},
                      {"projeto": "a" * 201, "mostrar": False},
                      {"mostrar": False}):
            r = self.dono("/api/projetos/mostrar", corpo)
            self.assertEqual(400, r.status, corpo)
            self.assertEqual({"erro": "diga o projeto e se ele aparece"},
                             self.json(r))

    def test_anti_csrf_vencido_e_429(self):
        self.relatar("x")
        cookies, _csrf = self.sessao_e_token()
        r = self.pedir("/api/projetos/mostrar", "POST",
                       {"projeto": "x", "mostrar": False}, cookies=cookies,
                       cabecalhos={"X-Token": "errado"})
        self.assertEqual("pagina_velha", self.json(r)["motivo"])
        sessao = self.sessao_e_token()
        for _ in range(servir.Hub.TETO_DE_MOSTRAR):
            self.mostrar("x", True, sessao=sessao)
        self.assertEqual(429, self.mostrar("x", True, sessao=sessao).status)

    def test_maquinas_traz_os_projetos_vistos(self):
        antes = self.json(self.dono("/api/maquinas", metodo="GET"))
        antes = antes["maquinas"] if isinstance(antes, dict) else antes
        m = next(x for x in antes if x["id"] == self.mid)
        self.assertEqual(([], False), (m["projetos_vistos"], m["so_mede"]))
        self.relatar("b", "a")
        self.mostrar("b", False)
        depois = self.json(self.dono("/api/maquinas", metodo="GET"))
        depois = depois["maquinas"] if isinstance(depois, dict) else depois
        m = next(x for x in depois if x["id"] == self.mid)
        self.assertIsNotNone(m["relatado_em"])
        self.assertEqual(
            [("a", "C:/p/a", False), ("b", "C:/p/b", True)],
            [(v["projeto"], v["caminho"], v["oculto"])
             for v in m["projetos_vistos"]])
        self.assertTrue(all(v["visto_em"] for v in m["projetos_vistos"]))


class OGithubComRepositorios(_Base):
    """C11."""

    def setUp(self):
        super().setUp()
        con = banco.conectar()
        try:
            for t in ("projeto_oculto", "projeto_conectado", "medida",
                      "instalacao_github"):
                con.execute("DELETE FROM %s" % t)
            con.commit()
        finally:
            con.close()
        banco.guardar_instalacao_do_github(
            self.uid, "9001", conta_login="loja-da-ana", conta_tipo="User")

    def projeto(self, nome, slug, uid=None):
        banco.gravar(nome, "local", {"nome": nome, "git": {"remoto_slug": slug}},
                     usuario_id=self.uid if uid is None else uid)

    def repos(self):
        r = self.dono("/api/github", metodo="GET")
        self.assertEqual(200, r.status)
        return self.json(r)["instalacoes"][0]["repositorios"]

    def test_so_entra_o_projeto_cujo_dono_do_slug_e_a_conta(self):
        self.projeto("loja", "Loja-Da-Ana/site")
        self.projeto("outro", "outra/x")
        self.assertEqual(
            [{"projeto": "loja", "slug": "Loja-Da-Ana/site", "medido": False,
              "oculto": False}], self.repos())

    def test_medido_oculto_e_ordem(self):
        self.projeto("b", "loja-da-ana/b")
        self.projeto("a", "loja-da-ana/a")
        banco.gravar("a", "github", {"ok": True}, usuario_id=self.uid)
        banco.mostrar_projeto(self.uid, "b", False)
        self.assertEqual([("a", True, False), ("b", False, True)],
                         [(r["projeto"], r["medido"], r["oculto"])
                          for r in self.repos()])

    def test_projeto_de_outra_conta_nunca_aparece(self):
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("outro-gh@teste.local", con=con)
        finally:
            con.close()
        self.projeto("do-outro", "loja-da-ana/x", uid=outro)
        self.assertEqual([], self.repos())

    def test_slug_torto_e_ignorado_sem_levantar(self):
        for i, torto in enumerate(("a/b/c", 5, None, "sem-barra", "/x", "x/",
                                   "a" * 201 + "/b", ["loja-da-ana/x"])):
            self.projeto("t%d" % i, torto)
        banco.gravar("sem-git", "local", {"nome": "sem-git"}, usuario_id=self.uid)
        banco.gravar("git-torto", "local", {"nome": "git-torto", "git": "x"},
                     usuario_id=self.uid)
        self.assertEqual([], self.repos())

    def test_sem_login_a_lista_vem_vazia(self):
        con = banco.conectar()
        try:
            con.execute("UPDATE instalacao_github SET conta_login = NULL")
            con.commit()
        finally:
            con.close()
        self.projeto("loja", "loja-da-ana/site")
        self.assertEqual([], self.repos())


class OMedirSemGravar(_Base):
    """C12: medir um site antes de guardar. A rota NUNCA grava."""

    MEDIDA = {"url": "https://loja-da-ana.com.br", "ok": True, "codigo": 200,
              "erro": "", "ms": 42, "tentativas": 1}

    def setUp(self):
        super().setUp()
        for alvo, retorno in (("mede_site", dict(self.MEDIDA)),
                              ("host_publico", True)):
            p = mock.patch.object(servir.coletar_github, alvo,
                                  return_value=retorno)
            setattr(self, alvo, p.start())
            self.addCleanup(p.stop)

    def enderecos(self):
        con = banco.conectar()
        try:
            return con.execute(
                "SELECT COUNT(*) FROM endereco_producao").fetchone()[0]
        finally:
            con.close()

    def medir(self, url, sessao=None):
        return self.dono("/api/enderecos/medir", {"url": url}, sessao=sessao)

    def test_mede_devolve_os_campos_e_nao_grava(self):
        antes = self.enderecos()
        r = self.medir("https://loja-da-ana.com.br")
        self.assertEqual(200, r.status, r.corpo)
        corpo = self.json(r)
        self.assertEqual(
            {"url": "https://loja-da-ana.com.br", "ok": True, "codigo": 200,
             "erro": "", "ms": 42},
            {k: corpo[k] for k in ("url", "ok", "codigo", "erro", "ms")})
        self.assertIn("medido_em", corpo)
        self.mede_site.assert_called_once_with("https://loja-da-ana.com.br")
        self.assertEqual(antes, self.enderecos())

    def test_forma_torta_e_400_forma(self):
        for torto in ("loja", "", "ftp://loja.com.br", "http://", "https:///x",
                      "https://" + "a" * 2050):
            r = self.medir(torto)
            self.assertEqual(400, r.status, torto)
            self.assertEqual(
                {"erro": "escreva o endereco completo, comecando por https://",
                 "motivo": "forma"}, self.json(r))
        self.mede_site.assert_not_called()

    def test_endereco_interno_e_400_nao_publico(self):
        r = self.medir("http://10.0.0.1")
        self.assertEqual((400, "nao_publico"),
                         (r.status, self.json(r)["motivo"]))
        self.assertEqual(servir.Hub.ENDERECO_RECUSADO, self.json(r)["erro"])
        self.mede_site.assert_not_called()

    def test_nome_que_resolve_para_dentro_nao_e_medido(self):
        self.host_publico.return_value = False
        r = self.medir("https://parece-publico.exemplo.br")
        self.assertEqual((400, "nao_publico"),
                         (r.status, self.json(r)["motivo"]))
        self.mede_site.assert_not_called()

    def test_balcao_proprio_e_separado_do_guardar(self):
        sessao = self.sessao_e_token()
        for _ in range(servir.Hub.TETO_DE_MEDICOES):
            self.assertEqual(200, self.medir("https://a.com.br",
                                             sessao=sessao).status)
        self.assertEqual(429, self.medir("https://a.com.br",
                                         sessao=sessao).status)
        # O guardar tem balcao proprio e segue respondendo.
        r = self.dono("/api/enderecos/guardar",
                      {"projeto": "x", "url": "https://a.com.br",
                       "servidor_id": 999999}, sessao=sessao)
        self.assertNotEqual(429, r.status)

    def test_sem_sessao_e_401_e_token_errado_e_pagina_velha(self):
        self.assertEqual(401, self.pedir("/api/enderecos/medir", "POST",
                                         {"url": "https://a.com.br"}).status)
        cookies, _ = self.sessao_e_token()
        r = self.pedir("/api/enderecos/medir", "POST", {"url": "https://a.com.br"},
                       cookies=cookies, cabecalhos={"X-Token": "errado"})
        self.assertEqual("pagina_velha", self.json(r)["motivo"])

    def test_guardar_sem_medir_nao_chama_mede_site(self):
        sessao = self.sessao_e_token()
        s = self.json(self.dono("/api/servidores/guardar", {"nome": "Meus sites"},
                                sessao=sessao))
        servidor_id = s.get("id") or s["servidor"]["id"]
        r = self.dono("/api/enderecos/guardar",
                      {"projeto": "x", "url": "https://a.com.br",
                       "servidor_id": servidor_id, "medir": False},
                      sessao=sessao)
        self.assertEqual(200, r.status, r.corpo)
        self.assertEqual(
            {"projeto": "x", "url": "https://a.com.br", "guardado": True,
             "ok": None, "codigo": None, "erro": "", "medido_em": None},
            self.json(r))
        self.mede_site.assert_not_called()
        # Sem o campo, nada muda: mede como sempre.
        r = self.dono("/api/enderecos/guardar",
                      {"projeto": "x", "url": "https://a.com.br",
                       "servidor_id": servidor_id}, sessao=sessao)
        self.assertEqual(True, self.json(r)["ok"])
        self.mede_site.assert_called_once()


if __name__ == "__main__":
    unittest.main()
