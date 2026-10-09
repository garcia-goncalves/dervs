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


if __name__ == "__main__":
    unittest.main()
