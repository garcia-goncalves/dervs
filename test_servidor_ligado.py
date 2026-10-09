# -*- coding: utf-8 -*-
"""Conectar simples, entrega B: o servidor ligado, do lado do DERVS (E2).

    python test_servidor_ligado.py

Contratos C0 a C6 de `docs/superpowers/plans/dervs-conectar-servidor-b.md`:
o `tipo` no pedido e na maquina, a medicao do servidor, o 403 de quem so olha,
a linha do ajudante e o aviso no fluxo ao vivo.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco     # noqa: E402
import cortina   # noqa: E402
import servir    # noqa: E402
from test_servir import BaseServidorDeVerdade  # noqa: E402

SHA = "96eb3fc"
PONTA = "a" * 40
SO_OLHA = {"erro": "este servidor so olha"}


def _corpo(**troca):
    """O corpo de C3, com o que o teste quiser trocar."""
    corpo = {
        "versao": 1,
        "docker_mudo": False,
        "servidor": {"ligado_s": 123456, "carga_1m": 0.12, "carga_5m": 0.3,
                     "carga_15m": 0.25, "memoria_total_kb": 4000000,
                     "memoria_disponivel_kb": 1200000,
                     "disco_total_b": 80000000000,
                     "disco_livre_b": 30000000000},
        "sistemas": [{"nome": "dervs-app", "projeto": "dervs",
                      "estado": "running", "saude": "healthy",
                      "desde": "2026-10-08T12:00:00+00:00", "reinicios": 0,
                      "imagem": "dervs:vps", "sha": ""}],
        "publicacoes": [{"projeto": "dervs",
                         "quando": "2026-09-29T15:15:00+00:00",
                         "sha": SHA, "resultado": "OK"}],
    }
    corpo.update(troca)
    return corpo


class _Base(BaseServidorDeVerdade):
    """O computador (sem cookie), o dono (cookie + token) e o servidor."""

    def json(self, r):
        return json.loads(r.corpo)

    def computador(self, caminho, corpo=None, metodo="POST"):
        return self.pedir(caminho, metodo, corpo, com_origem=False)

    def dono(self, caminho, corpo=None, metodo="POST", sessao=None):
        cookies, csrf = sessao or self.sessao_e_token()
        return self.pedir(caminho, metodo, corpo, cookies=cookies,
                          cabecalhos={"X-Token": csrf})

    def como_maquina(self, segredo, caminho, corpo=None, metodo="POST"):
        return self.pedir(caminho, metodo, corpo, com_origem=False,
                          cabecalhos={"Authorization": "Token " + segredo})

    def sessao_de(self, uid):
        """Sessao completa e anti-CSRF de OUTRA conta."""
        cookie = banco.novo_token()
        con = banco.conectar()
        try:
            banco.abrir_sessao(uid, cookie, banco.prazo(3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
            s = banco.sessao_valida(final, con=con)
        finally:
            con.close()
        return {"sessao": final}, servir.Hub._csrf_da_sessao(s)

    def ligar_servidor(self, nome="vps-ovh", sessao=None):
        """Pede como servidor, o dono autoriza, resgata. (segredo, maquina)."""
        r = self.computador("/agente/pedir", {"maquina": nome,
                                              "tipo": "servidor"})
        self.assertEqual(200, r.status, r.corpo)
        p = self.json(r)
        r = self.dono("/api/pedido/autorizar", {"codigo": p["codigo"]},
                      sessao=sessao)
        self.assertEqual(200, r.status, r.corpo)
        r = self.computador("/agente/esperar", {"pedido": p["pedido"]})
        self.assertEqual(200, r.status, r.corpo)
        segredo = self.json(r)["token"]
        return segredo, banco.maquina_por_token(segredo)

    def medir(self, segredo, corpo=None):
        return self.como_maquina(segredo, "/agente/servidor",
                                 _corpo() if corpo is None else corpo)

    def dados(self, sessao=None):
        cookies, _ = sessao or self.sessao_e_token()
        r = self.pedir("/api/dados", cookies=cookies)
        self.assertEqual(200, r.status, r.corpo)
        return self.json(r)

    def envelhecer(self, maquina_id, segundos):
        velho = (datetime.now(timezone.utc) - timedelta(seconds=segundos)
                 ).isoformat(timespec="seconds")
        con = banco.conectar()
        try:
            con.execute("UPDATE medicao_de_servidor SET medido_em = ?"
                        " WHERE maquina_id = ?", (velho, maquina_id))
            con.commit()
        finally:
            con.close()


class OTipoDoPedido(_Base):
    """C1: o pedido diz se e computador ou servidor, e a maquina herda."""

    def test_pedir_servidor_chega_a_tela_e_a_maquina(self):
        r = self.computador("/agente/pedir", {"maquina": "vps-ovh",
                                              "tipo": "servidor"})
        self.assertEqual(200, r.status, r.corpo)
        p = self.json(r)
        sessao = self.sessao_e_token()
        visto = self.json(self.dono("/api/pedido?codigo=" + p["codigo"],
                                    metodo="GET", sessao=sessao))
        self.assertEqual("servidor", visto["tipo"])
        self.dono("/api/pedido/autorizar", {"codigo": p["codigo"]},
                  sessao=sessao)
        segredo = self.json(self.computador(
            "/agente/esperar", {"pedido": p["pedido"]}))["token"]
        m = banco.maquina_por_token(segredo)
        self.assertEqual(("servidor", 1), (m["tipo"], m["so_mede"]))

    def test_tipo_desconhecido_e_400(self):
        for torto in ("x", 1, None, ["servidor"], "Servidor"):
            r = self.computador("/agente/pedir", {"maquina": "a",
                                                  "tipo": torto})
            self.assertEqual(400, r.status, torto)
            self.assertEqual({"erro": "pedido invalido"}, self.json(r))

    def test_sem_tipo_e_computador(self):
        p = self.json(self.computador("/agente/pedir", {"maquina": "PC"}))
        sessao = self.sessao_e_token()
        visto = self.json(self.dono("/api/pedido?codigo=" + p["codigo"],
                                    metodo="GET", sessao=sessao))
        self.assertEqual("computador", visto["tipo"])
        self.dono("/api/pedido/autorizar", {"codigo": p["codigo"]},
                  sessao=sessao)
        segredo = self.json(self.computador(
            "/agente/esperar", {"pedido": p["pedido"]}))["token"]
        self.assertEqual("computador", banco.maquina_por_token(segredo)["tipo"])


class AMigracao(unittest.TestCase):
    """C2: um hub.db de antes ganha `tipo` nas duas tabelas, sem perder linha."""

    TIRA_O_TIPO = re.compile(
        r",\s*(?:--[^\n]*\n\s*)*tipo\s+TEXT.*?'servidor'\)\)", re.DOTALL)

    def _banco_sem_tipo(self, caminho):
        con = banco.conectar(caminho)
        con.close()
        con = sqlite3.connect(caminho)
        try:
            con.execute("PRAGMA foreign_keys=OFF")
            con.execute("PRAGMA legacy_alter_table=ON")
            for tabela in ("maquina", "pedido_de_computador"):
                ddl = con.execute("SELECT sql FROM sqlite_master WHERE"
                                  " type='table' AND name=?",
                                  (tabela,)).fetchone()[0]
                sem = self.TIRA_O_TIPO.sub("", ddl)
                self.assertNotEqual(ddl, sem, "o teste nao achou o tipo")
                con.execute("ALTER TABLE %s RENAME TO %s_velha"
                            % (tabela, tabela))
                con.execute(sem)
                con.execute("DROP TABLE %s_velha" % tabela)
            con.execute("INSERT INTO usuario (email, criado_em) VALUES"
                        " ('velho@teste.local', '2026-01-01T00:00:00+00:00')")
            uid = con.execute("SELECT id FROM usuario").fetchone()[0]
            con.execute("INSERT INTO maquina (usuario_id, nome, token_hash,"
                        " criado_em) VALUES (?, 'antiga', 'h', 'x')", (uid,))
            con.commit()
            cols = {l[1] for l in con.execute("PRAGMA table_info(maquina)")}
            self.assertNotIn("tipo", cols)
        finally:
            con.close()

    def test_o_banco_antigo_ganha_o_tipo_computador(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "hub.db"
            self._banco_sem_tipo(caminho)
            for _ in range(2):              # a segunda vez nao levanta
                con = banco.conectar(caminho)
                try:
                    for tabela in ("maquina", "pedido_de_computador"):
                        cols = {l[1] for l in con.execute(
                            "PRAGMA table_info(%s)" % tabela)}
                        self.assertIn("tipo", cols, tabela)
                    self.assertEqual("computador", con.execute(
                        "SELECT tipo FROM maquina WHERE nome = 'antiga'"
                    ).fetchone()[0])
                    self.assertTrue(con.execute(
                        "PRAGMA foreign_keys").fetchone()[0])
                finally:
                    con.close()

    def test_a_medicao_e_filha_da_conta(self):
        self.assertIn("medicao_de_servidor", banco.FILHAS_DE_USUARIO)
        self.assertEqual(128 * 1024, banco.MAX_BYTES_DA_MEDICAO)

    def test_tipo_fora_da_lista_e_recusado_pelo_banco(self):
        with tempfile.TemporaryDirectory() as pasta:
            con = banco.conectar(Path(pasta) / "hub.db")
            try:
                uid = banco.criar_usuario("x@teste.local", con=con)
                with self.assertRaises(sqlite3.IntegrityError):
                    con.execute("INSERT INTO maquina (usuario_id, token_hash,"
                                " criado_em, tipo) VALUES (?, 'h', 'x', 'pc')",
                                (uid,))
            finally:
                con.close()


class OServidorSoOlha(_Base):
    """C1: token de servidor leva 403 em tudo que nao e a medicao dele."""

    ROTAS = (("/agente/relatorio", "POST"), ("/agente/resultado", "POST"),
             ("/agente/pacote", "GET"), ("/agente/voz/estado", "POST"),
             ("/agente/voz/recados", "GET"), ("/agente/voz/resultado", "POST"),
             ("/agente/voz/pedido", "POST"))

    def test_403_so_olha_em_cada_rota_de_computador(self):
        segredo, _m = self.ligar_servidor()
        for caminho, metodo in self.ROTAS:
            r = self.como_maquina(segredo, caminho,
                                  {"projetos": []} if metodo == "POST"
                                  else None, metodo)
            self.assertEqual((403, SO_OLHA), (r.status, self.json(r)), caminho)

    def test_o_403_vem_antes_do_balcao(self):
        segredo, m = self.ligar_servidor()
        for balcao in ("relatorio", "resultado", "pacote", "voz"):
            for _ in range(700):
                cortina.registrar_tentativa("maquina:%d" % m["id"],
                                            time.time(), balcao=balcao,
                                            teto=10 ** 6)
        for caminho, metodo in self.ROTAS:
            r = self.como_maquina(segredo, caminho,
                                  {} if metodo == "POST" else None, metodo)
            self.assertEqual(403, r.status, caminho)

    def test_o_servidor_nao_recebe_tarefa_nem_projeto(self):
        segredo, m = self.ligar_servidor()
        self.como_maquina(segredo, "/agente/relatorio",
                          {"projetos": [{"nome": "x"}]})
        con = banco.conectar()
        try:
            self.assertIsNone(con.execute(
                "SELECT 1 FROM projeto_conectado WHERE maquina_id = ?",
                (m["id"],)).fetchone())
        finally:
            con.close()

    def test_computador_em_agente_servidor_e_403(self):
        segredo, _m = self.maquina_com_token()
        r = self.medir(segredo)
        self.assertEqual((403, {"erro": "so servidor"}),
                         (r.status, self.json(r)))

    def test_sem_token_e_401(self):
        r = self.computador("/agente/servidor", _corpo())
        self.assertEqual(401, r.status)


class AMedicaoDoServidor(_Base):
    """C3: a lista fechada, o carimbo do DERVS e o teto."""

    def gravada(self, m):
        con = banco.conectar()
        try:
            l = con.execute("SELECT medido_em, dados FROM medicao_de_servidor"
                            " WHERE maquina_id = ?", (m["id"],)).fetchone()
        finally:
            con.close()
        return (l[0], json.loads(l[1])) if l else (None, None)

    def test_o_corpo_do_contrato_entra_e_a_resposta_e_curta(self):
        segredo, m = self.ligar_servidor()
        r = self.medir(segredo)
        self.assertEqual(200, r.status, r.corpo)
        self.assertEqual({"ok": True, "invalidos": 0}, self.json(r))
        _quando, dados = self.gravada(m)
        self.assertEqual("dervs-app", dados["sistemas"][0]["nome"])
        self.assertEqual(SHA, dados["publicacoes"][0]["sha"])
        self.assertEqual(4000000, dados["servidor"]["memoria_total_kb"])
        self.assertIs(False, dados["docker_mudo"])

    def test_chave_desconhecida_e_descartada_e_contada(self):
        segredo, m = self.ligar_servidor()
        sistema = dict(_corpo()["sistemas"][0], Env=["SEGREDO_ZZ=1"])
        r = self.medir(segredo, _corpo(Env={"SEGREDO_ZZ": "1"},
                                       sistemas=[sistema]))
        self.assertEqual(200, r.status, r.corpo)
        self.assertGreaterEqual(self.json(r)["invalidos"], 2)
        _q, dados = self.gravada(m)
        self.assertNotIn("SEGREDO_ZZ", json.dumps(dados))
        self.assertGreaterEqual(dados["invalidos"], 2)
        self.assertNotIn("SEGREDO_ZZ", json.dumps(self.dados()))

    def test_campo_torto_vira_vazio_ou_descarta_o_item(self):
        segredo, m = self.ligar_servidor()
        base = _corpo()["sistemas"][0]
        sistemas = [dict(base, nome="a", sha="ZZZ"),
                    dict(base, nome="b", estado="hacked"),
                    dict(base, nome="c", reinicios=10 ** 30),
                    dict(base, nome="\ud800"),
                    dict(base, nome="d", desde="2026-10-08 12:00:00"),
                    dict(base, nome="e", saude="morto")]
        r = self.medir(segredo, _corpo(sistemas=sistemas))
        self.assertEqual(200, r.status, r.corpo)
        _q, dados = self.gravada(m)
        por_nome = {s["nome"]: s for s in dados["sistemas"]}
        self.assertEqual({"a", "c", "d", "e"}, set(por_nome))
        self.assertEqual("", por_nome["a"]["sha"])
        self.assertIsNone(por_nome["c"]["reinicios"])
        self.assertEqual("", por_nome["d"]["desde"])
        self.assertEqual("", por_nome["e"]["saude"])
        self.assertEqual(2, self.json(r)["invalidos"])

    def test_numero_torto_no_servidor_vira_none(self):
        segredo, m = self.ligar_servidor()
        servidor = dict(_corpo()["servidor"], carga_1m=-1, ligado_s=True,
                        disco_livre_b=2 ** 63, memoria_total_kb="9")
        self.assertEqual(200, self.medir(segredo,
                                         _corpo(servidor=servidor)).status)
        _q, dados = self.gravada(m)
        for campo in ("carga_1m", "ligado_s", "disco_livre_b",
                      "memoria_total_kb"):
            self.assertIsNone(dados["servidor"][campo], campo)
        self.assertEqual(0.3, dados["servidor"]["carga_5m"])

    def test_publicacao_torta(self):
        segredo, m = self.ligar_servidor()
        pubs = [{"projeto": "a", "quando": "x", "sha": "ABCDEF1",
                 "resultado": "OK; rm"},
                {"projeto": "", "quando": "2026-09-29T15:15:00+00:00"},
                {"projeto": "b", "quando": "2026-09-29T15:15:00+00:00",
                 "sha": SHA, "resultado": "FALHOU(build)-voltou",
                 "quem": "tiba"}]
        r = self.medir(segredo, _corpo(publicacoes=pubs))
        _q, dados = self.gravada(m)
        self.assertEqual(["a", "b"],
                         [p["projeto"] for p in dados["publicacoes"]])
        self.assertEqual(("", "", ""),
                         tuple(dados["publicacoes"][0][k]
                               for k in ("quando", "sha", "resultado")))
        self.assertEqual("FALHOU(build)-voltou",
                         dados["publicacoes"][1]["resultado"])
        self.assertNotIn("tiba", json.dumps(dados))
        self.assertEqual(2, self.json(r)["invalidos"])

    def test_201_sistemas_passa_cortado(self):
        segredo, m = self.ligar_servidor()
        base = _corpo()["sistemas"][0]
        r = self.medir(segredo, _corpo(sistemas=[
            dict(base, nome="s%d" % i) for i in range(201)]))
        self.assertEqual(200, r.status, r.corpo)
        self.assertEqual(200, len(self.gravada(m)[1]["sistemas"]))

    def test_medicao_grande_demais_e_400(self):
        segredo, m = self.ligar_servidor()
        base = dict(_corpo()["sistemas"][0], projeto="p" * 128,
                    imagem="i" * 200)
        pub = {"projeto": "q" * 128, "quando": "2026-09-29T15:15:00+00:00",
               "sha": "f" * 40, "resultado": "r" * 40}
        r = self.medir(segredo, _corpo(
            sistemas=[dict(base, nome=("n%d" % i).ljust(128, "x"))
                      for i in range(200)],
            publicacoes=[pub] * 200))
        self.assertEqual((400, {"erro": "medicao grande demais"}),
                         (r.status, self.json(r)))
        self.assertEqual((None, None), self.gravada(m))

    def test_corpo_que_nao_e_dicionario_e_400_e_sem_json_e_415(self):
        segredo, _m = self.ligar_servidor()
        r = self.medir(segredo, [1, 2])
        self.assertEqual((400, {"erro": "corpo invalido"}),
                         (r.status, self.json(r)))
        r = self.pedir("/agente/servidor", "POST", corpo_cru=b"{}",
                       com_origem=False,
                       cabecalhos={"Authorization": "Token " + segredo,
                                   "Content-Type": "text/plain"})
        self.assertEqual(415, r.status)

    def test_61_medicoes_e_429_e_o_pedido_continua_vivo(self):
        segredo, _m = self.ligar_servidor()
        for i in range(60):
            self.assertEqual(200, self.medir(segredo).status, i)
        r = self.medir(segredo)
        self.assertEqual((429, {"erro": "nao deu"}), (r.status, self.json(r)))
        p = self.json(self.computador("/agente/pedir", {"maquina": "outro"}))
        r = self.computador("/agente/esperar", {"pedido": p["pedido"]})
        self.assertEqual(202, r.status)

    def test_o_carimbo_e_do_dervs_e_o_visto_em_anda(self):
        segredo, m = self.ligar_servidor()
        con = banco.conectar()
        try:
            con.execute("UPDATE maquina SET visto_em = '2020-01-01T00:00:00"
                        "+00:00' WHERE id = ?", (m["id"],))
            con.commit()
        finally:
            con.close()
        antes = banco.agora()
        self.medir(segredo, _corpo(medido_em="1999-01-01T00:00:00+00:00"))
        quando, dados = self.gravada(m)
        self.assertGreaterEqual(quando, antes)
        self.assertNotIn("medido_em", dados)
        self.assertEqual(quando, banco.maquina_por_token(segredo)["visto_em"])

    def test_a_resposta_nunca_leva_tarefa(self):
        segredo, _m = self.ligar_servidor()
        self.assertNotIn("tarefa", self.json(self.medir(segredo)))


class OsDadosDoPainel(_Base):
    """C5: `servidores_ligados` e `no_ar`, postos depois do motor."""

    def setUp(self):
        super().setUp()
        con = banco.conectar()
        try:
            con.execute("DELETE FROM maquina WHERE tipo = 'servidor'")
            con.execute("DELETE FROM medida WHERE usuario_id = ?", (self.uid,))
            con.commit()
        finally:
            con.close()
        banco.gravar("clinica-agenda", "local", {"nome": "clinica-agenda"},
                     usuario_id=self.uid)
        banco.gravar("clinica-agenda", "github",
                     {"head_sha": PONTA,
                      "no_ar": [{"sha": SHA, "atras": 3}]},
                     usuario_id=self.uid)

    def corpo_da_clinica(self, sha=SHA, projeto="clinicaagenda"):
        return _corpo(sistemas=[{"nome": "clinica-web", "projeto": projeto,
                                 "estado": "running", "saude": "healthy",
                                 "desde": "2026-10-08T12:00:00+00:00",
                                 "reinicios": 2, "imagem": "clinica:vps",
                                 "sha": sha}],
                      publicacoes=[])

    def projeto(self, estado, nome="clinica-agenda"):
        return next(p for p in estado["projetos"] if p["nome"] == nome)

    def test_o_servidor_ligado_e_o_no_ar(self):
        segredo, m = self.ligar_servidor()
        self.assertEqual(200, self.medir(segredo,
                                         self.corpo_da_clinica()).status)
        estado = self.dados()
        s = estado["servidores_ligados"][0]
        self.assertEqual({"maquina_id", "nome", "estado", "medido_em",
                          "docker_mudo", "sistemas"}, set(s))
        self.assertEqual((m["id"], "vps-ovh", "medido", False),
                         (s["maquina_id"], s["nome"], s["estado"],
                          s["docker_mudo"]))
        self.assertEqual([{"nome": "clinica-web", "projeto": "clinicaagenda",
                           "estado": "running", "saude": "healthy",
                           "desde": "2026-10-08T12:00:00+00:00",
                           "reinicios": 2}], s["sistemas"])
        n = self.projeto(estado)["no_ar"]
        self.assertEqual(1, len(n))
        self.assertEqual({"maquina_id", "servidor", "estado", "medido_em",
                          "sha", "publicado_em", "veredito", "atras"},
                         set(n[0]))
        self.assertEqual((m["id"], "vps-ovh", "medido", SHA, None, "atras", 3),
                         (n[0]["maquina_id"], n[0]["servidor"],
                          n[0]["estado"], n[0]["sha"], n[0]["publicado_em"],
                          n[0]["veredito"], n[0]["atras"]))
        self.assertEqual(s["medido_em"], n[0]["medido_em"])

    def test_medicao_velha_vira_sem_dados_e_nao_sei(self):
        segredo, m = self.ligar_servidor()
        self.medir(segredo, self.corpo_da_clinica())
        self.envelhecer(m["id"], 400)
        estado = self.dados()
        self.assertEqual("sem_dados", estado["servidores_ligados"][0]["estado"])
        n = self.projeto(estado)["no_ar"][0]
        self.assertEqual(("sem_dados", "nao_sei", None),
                         (n["estado"], n["veredito"], n["atras"]))

    def test_sem_casamento_e_lista_vazia_e_sem_servidor_tambem(self):
        self.assertEqual([], self.dados()["servidores_ligados"])
        self.assertEqual([], self.projeto(self.dados())["no_ar"])
        segredo, _m = self.ligar_servidor()
        estado = self.dados()
        s = estado["servidores_ligados"][0]
        self.assertEqual(("sem_dados", None, None, []),
                         (s["estado"], s["medido_em"], s["docker_mudo"],
                          s["sistemas"]))
        self.medir(segredo, self.corpo_da_clinica(projeto="outro"))
        self.assertEqual([], self.projeto(self.dados())["no_ar"])

    def test_montar_estado_nao_muda(self):
        segredo, _m = self.ligar_servidor()
        self.medir(segredo, self.corpo_da_clinica())
        e = banco.montar_estado(usuario_id=self.uid)
        self.assertNotIn("servidores_ligados", e)
        for p in e["projetos"]:
            self.assertNotIn("no_ar", p)

    def test_outra_conta_nunca_aparece(self):
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        sessao_dele = self.sessao_de(outro)
        segredo, _m = self.ligar_servidor("vps-dele", sessao=sessao_dele)
        self.medir(segredo, self.corpo_da_clinica())
        self.assertEqual([], self.dados()["servidores_ligados"])
        self.assertEqual([], self.projeto(self.dados())["no_ar"])
        self.assertEqual(["vps-dele"], [s["nome"] for s in self.dados(
            sessao=sessao_dele)["servidores_ligados"]])

    def test_o_servidor_nao_e_computador(self):
        segredo, m = self.ligar_servidor()
        self.medir(segredo, self.corpo_da_clinica())
        cookies, _ = self.sessao_e_token()
        maquinas = self.json(self.pedir("/api/maquinas",
                                        cookies=cookies))["maquinas"]
        self.assertNotIn(m["id"], [x["id"] for x in maquinas])
        con = banco.conectar()
        try:
            con.execute("UPDATE maquina SET visto_em = '2020-01-01T00:00:00"
                        "+00:00' WHERE id = ?", (m["id"],))
            con.commit()
        finally:
            con.close()
        caladas = banco.maquinas_que_calaram(self.uid, banco.agora())
        self.assertNotIn(m["id"], [x["maquina_id"] for x in caladas])

    def test_servidor_revogado_some(self):
        segredo, m = self.ligar_servidor()
        self.medir(segredo, self.corpo_da_clinica())
        banco.revogar_maquina(m["id"], self.uid)
        self.assertEqual([], self.dados()["servidores_ligados"])
        self.assertIsNone(banco.ultima_medicao_de_servidor(self.uid))


class DesligarUmServidorPelaTela(_Base):
    """S1: o dono revoga o servidor pela MESMA rota de tirar computador."""

    def test_o_dono_desliga_o_proprio_servidor_e_o_token_morre(self):
        segredo, m = self.ligar_servidor()
        self.assertEqual(200, self.medir(segredo).status)
        r = self.dono("/api/maquinas/remover", {"id": m["id"]})
        self.assertEqual(200, r.status, r.corpo)
        self.assertEqual([], self.dados()["servidores_ligados"])
        self.assertEqual(401, self.medir(segredo).status)

    def test_outra_conta_nao_desliga(self):
        outro = banco.criar_usuario("outro-%s@teste.local"
                                    % banco.novo_token()[:6])
        sessao_dele = self.sessao_de(outro)
        segredo, m = self.ligar_servidor("vps-dele", sessao=sessao_dele)
        r = self.dono("/api/maquinas/remover", {"id": m["id"]})
        self.assertEqual(404, r.status, r.corpo)
        self.assertEqual(["vps-dele"], [s["nome"] for s in self.dados(
            sessao=sessao_dele)["servidores_ligados"]])
        self.assertEqual(200, self.medir(segredo).status)


class ALinhaDoAjudante(_Base):
    """C4: o arquivo e a linha saem da MESMA funcao, e o sha bate."""

    FONTE = ('# -*- coding: ascii -*-\nALVO = ""   # DERVS:ALVO\n'
             'print(ALVO)\n')

    def setUp(self):
        super().setUp()
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.arquivo = Path(self.pasta.name) / "ajudante_servidor.py"
        self.arquivo.write_text(self.FONTE, encoding="utf-8")
        trocar = mock.patch.object(servir.Hub, "AJUDANTE", self.arquivo)
        trocar.start()
        self.addCleanup(trocar.stop)

    def baixar(self):
        return self.pedir("/ajudante/servidor.py", com_origem=False)

    def pedir_linha(self):
        cookies, _ = self.sessao_e_token()
        return self.pedir("/api/ajudante/linha", cookies=cookies)

    def pedidos(self):
        con = banco.conectar()
        try:
            return con.execute(
                "SELECT COUNT(*) FROM pedido_de_computador").fetchone()[0]
        finally:
            con.close()

    def test_o_arquivo_sem_sessao_e_o_sha_da_linha_batem(self):
        antes = self.pedidos()
        r = self.pedir("/ajudante/servidor.py", com_origem=False)
        self.assertEqual(200, r.status)
        self.assertEqual("application/octet-stream",
                         r.cabecalhos["Content-Type"])
        self.assertEqual('attachment; filename="dervs-ajudante.py"',
                         r.cabecalhos["Content-Disposition"])
        alvo = "http://127.0.0.1:%d" % self.porta
        self.assertIn('ALVO = "%s"   # DERVS:ALVO' % alvo, r.corpo)
        bruto = r.corpo.encode("ascii")
        self.assertEqual(str(len(bruto)), r.cabecalhos["Content-Length"])
        d = json.loads(self.pedir_linha().corpo)
        self.assertEqual(hashlib.sha256(bruto).hexdigest(), d["sha256"])
        self.assertEqual(alvo + "/ajudante/servidor.py", d["endereco"])
        self.assertEqual(
            'cd "$(mktemp -d)" && curl -fsSL %s/ajudante/servidor.py -o '
            'dervs-ajudante.py && echo "%s  dervs-ajudante.py" | sha256sum -c'
            ' - && sudo python3 -I dervs-ajudante.py' % (alvo, d["sha256"]),
            d["linha"])
        self.assertEqual(antes, self.pedidos())

    def test_sem_marca_ou_com_acento_e_503_nas_duas(self):
        for fonte in ('ALVO = ""\n', 'ALVO = ""   # DERVS:ALVO\n# olá\n',
                      'ALVO = ""   # DERVS:ALVO\nB = ""   # DERVS:ALVO\n'):
            self.arquivo.write_text(fonte, encoding="utf-8")
            r = self.baixar()
            self.assertEqual(503, r.status, fonte)
            self.assertEqual({"erro": "o ajudante nao esta nesta copia"},
                             self.json(r))
            self.assertEqual(503, self.pedir_linha().status, fonte)
        self.arquivo.unlink()
        self.assertEqual(503, self.baixar().status)
        self.assertEqual(503, self.pedir_linha().status)

    def test_a_linha_sem_sessao_e_401(self):
        self.assertEqual(401, self.pedir("/api/ajudante/linha").status)

    def test_o_31o_download_e_429(self):
        for i in range(30):
            self.assertEqual(200, self.baixar().status, i)
        r = self.baixar()
        self.assertEqual(429, r.status)
        self.assertEqual(200, self.pedir_linha().status)   # a linha nao paga balcao


class OFluxoAvisaQueOServidorMediu(_Base):
    """C6: `/api/eventos` sem id avisa quando um servidor da conta mediu."""

    def setUp(self):
        super().setUp()
        servir.Hub._fluxos.clear()
        self.addCleanup(servir.Hub._fluxos.clear)
        vida = servir.Hub.SEGUNDOS_DE_VIDA
        servir.Hub.SEGUNDOS_DE_VIDA = 10
        self.addCleanup(setattr, servir.Hub, "SEGUNDOS_DE_VIDA", vida)

    def abrir(self, caminho):
        cookies = self.com_sessao()
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=2)
        c.request("GET", caminho, headers={
            "Host": "127.0.0.1:%d" % self.porta,
            "Cookie": "sessao=%s" % cookies["sessao"]})
        r = c.getresponse()
        self.addCleanup(c.close)
        self.assertEqual(200, r.status)
        return r

    @staticmethod
    def ler_ate(resposta, marca, segundos):
        """Le em pedacos ate `marca` ou o prazo. Nunca pendura."""
        junto = ""
        fim = time.time() + segundos
        while time.time() < fim:
            try:
                pedaco = resposta.read(1)
            except (TimeoutError, OSError):
                break
            if not pedaco:
                break
            junto += pedaco.decode("utf-8", "replace")
            if marca in junto:
                break
        return junto

    def test_sem_id_chega_o_evento_com_o_carimbo(self):
        _segredo, m = self.ligar_servidor()
        r = self.abrir("/api/eventos")
        self.ler_ate(r, ":\n\n", 3)              # a base ja foi lida
        quando = banco.gravar_medicao_de_servidor(m["id"], self.uid,
                                                  {"sistemas": []})
        lido = self.ler_ate(r, "event: servidor", 6)
        self.assertIn("event: servidor", lido)
        lido += self.ler_ate(r, "\n\n", 2)
        dados = lido.split("event: servidor", 1)[1]
        self.assertIn(json.dumps({"medido_em": quando}), dados)
        self.assertNotIn("id:", lido.split("event: servidor", 1)[0]
                         .rsplit("\n\n", 1)[-1])

    def test_a_primeira_leitura_e_base(self):
        _segredo, m = self.ligar_servidor()
        banco.gravar_medicao_de_servidor(m["id"], self.uid, {"sistemas": []})
        r = self.abrir("/api/eventos")
        self.assertNotIn("event: servidor", self.ler_ate(r, "nunca", 3))

    def test_banco_ocupado_ao_ler_a_medicao_nao_derruba_o_fluxo(self):
        """`sqlite3.Error` na leitura e "nao mudou": o fluxo segue vivo."""
        _segredo, _m = self.ligar_servidor()
        chamadas = []

        def ocupado(uid, con=None):
            chamadas.append(uid)
            raise sqlite3.OperationalError("database is locked")
        with mock.patch.object(banco, "ultima_medicao_de_servidor", ocupado):
            r = self.abrir("/api/eventos")
            lido = self.ler_ate(r, "nunca", 3)
        self.assertGreaterEqual(len(chamadas), 2)
        self.assertGreaterEqual(lido.count(":\n\n"), 2)    # a sonda segue viva
        self.assertNotIn("event: servidor", lido)

    def test_com_id_nao_chega_nada_do_servidor(self):
        _segredo, m = self.ligar_servidor()
        r = self.abrir("/api/eventos?id=x")
        self.ler_ate(r, ":\n\n", 3)
        banco.gravar_medicao_de_servidor(m["id"], self.uid, {"sistemas": []})
        self.assertNotIn("event: servidor", self.ler_ate(r, "nunca", 3))


if __name__ == "__main__":
    unittest.main(verbosity=0)
