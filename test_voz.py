# -*- coding: utf-8 -*-
"""Testes da ponte entre o painel e o DERVS-VOZ.

O servidor SO GUARDA E ENTREGA: estes testes cobram o que isso exige.

  1. Nada daqui carimba `visto_em`. O estado que o VOZ conta de si NAO e sinal
     de vida — so o relatorio e. Se carimbasse, o painel ficaria "viva" com a
     medicao parada (lei 2).
  2. Toda consulta filtra por dono. Ha DUAS contas e as cinco rotas sao
     cruzadas: a segunda nao ve, nao escreve e nao le nada da primeira.
  3. "Nao e seu" e "nao existe" dao a MESMA resposta.
  4. O balcao `voz` e proprio: esgotado, as outras rotas continuam respondendo.

    python test_voz.py
"""
from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco     # noqa: E402
import cortina   # noqa: E402
import servir    # noqa: E402

AGORA = "2026-09-30T12:00:00+00:00"


def _antes(segundos: int) -> str:
    """`AGORA` menos `segundos`, no formato do banco."""
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(AGORA)
            - timedelta(seconds=segundos)).isoformat(timespec="seconds")


def _estado_bom(**troca):
    e = {"versao": 1, "enviado_em": AGORA, "cerebro_ativo": "claude_code",
         "cerebros": {"claude_code": {"disponivel": True, "motivo": ""},
                      "hermes": {"disponivel": False, "motivo": "nao instalado"},
                      "jev": {"disponivel": False, "motivo": "sem chave"}},
         "gasto_dia_usd": 1.25}
    e.update(troca)
    return e


def _recado_bom(maquina_id, **troca):
    r = {"maquina_id": maquina_id, "tipo": "analisar", "alvo": "dervs",
         "texto": "olhe o que mudou", "nivel": "leitura",
         "cerebro_pedido": "auto"}
    r.update(troca)
    return r


def _resultado_bom(id_, **troca):
    r = {"id": id_, "cerebro": "claude_code", "estado": "feito",
         "resumo": "tudo certo", "custo_usd": 0.12, "duracao_s": 3.5,
         "terminado_em": AGORA}
    r.update(troca)
    return r


class _Resposta:
    def __init__(self, status, corpo):
        self.status, self.corpo = status, corpo

    @property
    def json(self):
        try:
            return json.loads(self.corpo)
        except ValueError:
            return {}


class OReloginhoDaVigilia(unittest.TestCase):
    """`voz_do_usuario` com relogio fixo: nada aqui depende de "agora"."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        antigo, banco.BANCO = banco.BANCO, Path(self.dir.name) / "hub.db"
        self.addCleanup(lambda: setattr(banco, "BANCO", antigo))
        self.con = banco.conectar()
        self.addCleanup(self.con.close)
        self.uid = banco.criar_usuario("dono@teste.local", con=self.con)
        self.mid = self._maquina(self.uid, "pc")

    def _maquina(self, uid, nome):
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(uid, codigo, banco.prazo(600), con=self.con)
        token = banco.usar_pareamento(codigo, nome, con=self.con)
        return banco.maquina_por_token(token, con=self.con)["id"]

    def _visto(self, valor):
        self.con.execute("UPDATE maquina SET visto_em = ? WHERE id = ?",
                         (valor, self.mid))
        self.con.commit()

    def _vigilia(self):
        m, = banco.voz_do_usuario(self.uid, agora_iso=AGORA,
                                  con=self.con)["maquinas"]
        return m

    def test_viva_no_limite_e_sem_dados_um_segundo_depois(self):
        self.assertEqual(banco.VIGILIA_LIMITE_S, 1200)
        self._visto(_antes(1200))
        self.assertEqual(self._vigilia()["vigilia"], "viva")
        self.assertEqual(self._vigilia()["atraso_s"], 1200)
        self._visto(_antes(1201))
        self.assertEqual(self._vigilia()["vigilia"], "sem_dados")

    def test_sem_carimbo_ou_com_carimbo_ilegivel_e_sem_dados(self):
        for valor in (None, "", "ontem de tarde", "2026-09-30T12:00:00"):
            with self.subTest(visto_em=valor):
                self._visto(valor)
                m = self._vigilia()
                self.assertEqual(m["vigilia"], "sem_dados")
                self.assertIsNone(m["atraso_s"])

    def test_nunca_inventa_morta_nem_erro(self):
        for atraso in (0, 60, 1200, 1201, 10 ** 7):
            self._visto(_antes(atraso))
            self.assertIn(self._vigilia()["vigilia"], ("viva", "sem_dados"))

    def test_o_estado_e_fresco_so_dentro_do_limite(self):
        banco.guardar_voz_estado(self.mid, self.uid, _estado_bom(),
                                 agora_iso=_antes(1200), con=self.con)
        m = self._vigilia()
        self.assertTrue(m["estado"]["fresco"])
        self.assertEqual(m["estado"]["cerebro_ativo"], "claude_code")
        banco.guardar_voz_estado(self.mid, self.uid, _estado_bom(),
                                 agora_iso=_antes(1201), con=self.con)
        self.assertFalse(self._vigilia()["estado"]["fresco"])

    def test_sem_estado_e_nulo_e_nao_inventado(self):
        self.assertIsNone(self._vigilia()["estado"])

    def test_maquina_revogada_nao_aparece(self):
        banco.revogar_maquina(self.mid, self.uid, con=self.con)
        self.assertEqual(banco.voz_do_usuario(
            self.uid, agora_iso=AGORA, con=self.con)["maquinas"], [])

    def test_so_os_20_ultimos_recados(self):
        for n in range(25):
            banco.criar_voz_recado(self.uid, self.mid, "status", "dervs", "",
                                   "leitura", "auto", teto_pendentes=100,
                                   agora_iso=_antes(1000 - n), con=self.con)
        recados = banco.voz_do_usuario(self.uid, agora_iso=AGORA,
                                       con=self.con)["recados"]
        self.assertEqual(len(recados), 20)
        self.assertEqual(recados[0]["criado_em"], _antes(1000 - 24))


class AServidorDeVerdade(unittest.TestCase):
    """Sobe o servidor numa porta livre e fala HTTP na mao."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls._banco_antigo = banco.BANCO
        banco.BANCO = Path(cls.dir.name) / "hub.db"
        con = banco.conectar()
        cls.uid = banco.criar_usuario("dono@teste.local", con=con)
        cls.outro = banco.criar_usuario("vizinho@teste.local", con=con)
        con.close()

        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servir.Hub)
        cls.porta = cls.srv.server_address[1]
        cls._antigos = (servir.PORTA, servir.ORIGENS_OK, servir.HOSTS_OK)
        servir.PORTA = cls.porta
        servir.ORIGENS_OK = {"http://127.0.0.1:%d" % cls.porta}
        servir.HOSTS_OK = {"127.0.0.1:%d" % cls.porta}
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        # Duas maquinas do dono e uma do vizinho.
        cls.t_a1, cls.m_a1 = cls._parear(cls.uid, "a1")
        cls.t_a2, cls.m_a2 = cls._parear(cls.uid, "a2")
        cls.t_b1, cls.m_b1 = cls._parear(cls.outro, "b1")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        servir.PORTA, servir.ORIGENS_OK, servir.HOSTS_OK = cls._antigos
        banco.BANCO = cls._banco_antigo
        cls.dir.cleanup()

    @staticmethod
    def _parear(uid, nome):
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(uid, codigo, banco.prazo(600))
        token = banco.usar_pareamento(codigo, nome)
        return token, banco.maquina_por_token(token)["id"]

    def setUp(self):
        cortina.zerar_tentativas()
        self.addCleanup(cortina.zerar_tentativas)
        con = banco.conectar()
        con.execute("DELETE FROM voz_recado")
        con.execute("DELETE FROM voz_estado")
        con.commit()
        con.close()

    # ------------------------------------------------------------ utilidades
    def pedir(self, caminho, metodo="GET", corpo=None, cabecalhos=None,
              cookies=None, bruto=None):
        dados = bruto if bruto is not None else (
            None if corpo is None else json.dumps(corpo).encode("utf-8"))
        cab = {"Host": "127.0.0.1:%d" % self.porta}
        if dados is not None:
            cab["Content-Type"] = "application/json"
            cab["Content-Length"] = str(len(dados))
        if cookies:
            cab["Cookie"] = "; ".join("%s=%s" % kv for kv in cookies.items())
        cab.update(cabecalhos or {})
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        try:
            c.request(metodo, caminho, body=dados, headers=cab)
            r = c.getresponse()
            return _Resposta(r.status, (r.read() or b"").decode("utf-8", "replace"))
        finally:
            c.close()

    def maquina(self, token, caminho, metodo="POST", corpo=None, bruto=None):
        return self.pedir(caminho, metodo, corpo, bruto=bruto,
                          cabecalhos={"Authorization": "Token " + token})

    def sessao(self, uid):
        cookie = banco.novo_token()
        con = banco.conectar()
        try:
            banco.abrir_sessao(uid, cookie, banco.prazo(3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
        finally:
            con.close()
        s = banco.sessao_valida(final)
        return ({"sessao": final},
                {"Origin": "http://127.0.0.1:%d" % self.porta,
                 "X-Token": servir.Hub._csrf_da_sessao(s)})

    def dono(self, uid, caminho, metodo="GET", corpo=None):
        cookies, cab = self.sessao(uid)
        return self.pedir(caminho, metodo, corpo, cabecalhos=cab, cookies=cookies)

    def recado(self, uid, mid, **troca):
        return self.dono(uid, "/api/voz/recado", "POST",
                         _recado_bom(mid, **troca))

    def visto_em(self, mid):
        con = banco.conectar()
        try:
            return con.execute("SELECT visto_em FROM maquina WHERE id = ?",
                               (mid,)).fetchone()[0]
        finally:
            con.close()

    def linha(self, id_):
        con = banco.conectar()
        try:
            return dict(con.execute("SELECT * FROM voz_recado WHERE id = ?",
                                    (id_,)).fetchone())
        finally:
            con.close()

    # ------------------------------------------------------------------ auth
    def test_as_tres_rotas_da_maquina_sem_token_dao_401(self):
        for caminho, metodo in (("/agente/voz/estado", "POST"),
                                ("/agente/voz/recados", "GET"),
                                ("/agente/voz/resultado", "POST")):
            with self.subTest(rota=caminho):
                corpo = {} if metodo == "POST" else None
                self.assertEqual(self.pedir(caminho, metodo, corpo).status, 401)
                r = self.maquina(banco.novo_token(), caminho, metodo, corpo)
                self.assertEqual(r.status, 401, "token inventado entrou")

    def test_as_duas_rotas_do_dono_sem_sessao_dao_401(self):
        self.assertEqual(self.pedir("/api/voz").status, 401)
        self.assertEqual(self.pedir("/api/voz/recado", "POST",
                                    _recado_bom(self.m_a1)).status, 401)

    def test_o_token_de_maquina_nao_abre_as_rotas_do_dono(self):
        self.assertEqual(self.maquina(self.t_a1, "/api/voz", "GET").status, 401)
        self.assertEqual(self.maquina(self.t_a1, "/api/voz/recado", "POST",
                                      _recado_bom(self.m_a1)).status, 401)

    def test_recado_sem_csrf_ou_origem_e_recusado(self):
        cookies, cab = self.sessao(self.uid)
        corpo = _recado_bom(self.m_a1)
        r = self.pedir("/api/voz/recado", "POST", corpo, cookies=cookies,
                       cabecalhos={"Origin": cab["Origin"]})
        self.assertEqual(r.status, 403)
        r = self.pedir("/api/voz/recado", "POST", corpo, cookies=cookies,
                       cabecalhos={"X-Token": cab["X-Token"]})
        self.assertEqual(r.status, 403)

    def test_maquina_revogada_perde_as_tres_rotas_e_some_do_painel(self):
        token, mid = self._parear(self.uid, "vai-sair")
        banco.revogar_maquina(mid, self.uid)
        self.assertEqual(self.maquina(token, "/agente/voz/estado", "POST",
                                      _estado_bom()).status, 401)
        self.assertEqual(self.recado(self.uid, mid).status, 404)
        ids = [m["maquina_id"] for m in
               self.dono(self.uid, "/api/voz").json["maquinas"]]
        self.assertNotIn(mid, ids)

    # ---------------------------------------------------------------- estado
    def test_o_estado_e_guardado_e_o_painel_o_mostra(self):
        r = self.maquina(self.t_a1, "/agente/voz/estado", "POST", _estado_bom())
        self.assertEqual(r.status, 200, r.corpo)
        v = self.dono(self.uid, "/api/voz").json
        a1 = next(m for m in v["maquinas"] if m["maquina_id"] == self.m_a1)
        self.assertEqual(a1["estado"]["cerebro_ativo"], "claude_code")
        self.assertTrue(a1["estado"]["fresco"])
        self.assertEqual(a1["estado"]["gasto_dia_usd"], 1.25)
        self.assertEqual(a1["estado"]["cerebros"]["hermes"]["motivo"],
                         "nao instalado")
        a2 = next(m for m in v["maquinas"] if m["maquina_id"] == self.m_a2)
        self.assertIsNone(a2["estado"], "o estado de a1 vazou para a2")

    def test_o_estado_nao_carimba_visto_em(self):
        """NAO E SINAL DE VIDA. Se carimbasse, a maquina calada pareceria viva."""
        con = banco.conectar()
        velho = "2020-01-01T00:00:00+00:00"
        con.execute("UPDATE maquina SET visto_em = ? WHERE id = ?",
                    (velho, self.m_a1))
        con.commit()
        con.close()
        for _ in range(3):
            self.assertEqual(self.maquina(self.t_a1, "/agente/voz/estado",
                                          "POST", _estado_bom()).status, 200)
        self.assertEqual(self.visto_em(self.m_a1), velho)
        # E pelos outros dois verbos da ponte tambem.
        self.maquina(self.t_a1, "/agente/voz/recados", "GET")
        self.assertEqual(self.visto_em(self.m_a1), velho)
        a1 = next(m for m in self.dono(self.uid, "/api/voz").json["maquinas"]
                  if m["maquina_id"] == self.m_a1)
        self.assertEqual(a1["vigilia"], "sem_dados")
        self.assertTrue(a1["estado"]["fresco"])

    def test_so_o_relatorio_deixa_a_maquina_viva(self):
        con = banco.conectar()
        con.execute("UPDATE maquina SET visto_em = ? WHERE id = ?",
                    ("2020-01-01T00:00:00+00:00", self.m_a1))
        con.commit()
        con.close()
        r = self.maquina(self.t_a1, "/agente/relatorio", "POST",
                         {"projetos": [{"nome": "dervs"}]})
        self.assertEqual(r.status, 200, r.corpo)
        a1 = next(m for m in self.dono(self.uid, "/api/voz").json["maquinas"]
                  if m["maquina_id"] == self.m_a1)
        self.assertEqual(a1["vigilia"], "viva")

    def test_estado_invalido_e_400(self):
        ruins = {
            "versao 2": _estado_bom(versao=2),
            "versao bool": _estado_bom(versao=True),
            "enviado_em lixo": _estado_bom(enviado_em="ontem"),
            "enviado_em nao texto": _estado_bom(enviado_em=5),
            "cerebro_ativo desconhecido": _estado_bom(cerebro_ativo="gpt"),
            "cerebro_ativo jev": _estado_bom(cerebro_ativo="jev"),
            "cerebros lista": _estado_bom(cerebros=[]),
            "cerebro desconhecido": _estado_bom(
                cerebros={"gpt": {"disponivel": True, "motivo": ""}}),
            "disponivel texto": _estado_bom(
                cerebros={"hermes": {"disponivel": "sim", "motivo": ""}}),
            "sem disponivel": _estado_bom(cerebros={"hermes": {"motivo": ""}}),
            "motivo grande": _estado_bom(
                cerebros={"hermes": {"disponivel": False, "motivo": "x" * 201}}),
            "motivo nao texto": _estado_bom(
                cerebros={"hermes": {"disponivel": False, "motivo": 3}}),
            "chave extra no cerebro": _estado_bom(
                cerebros={"hermes": {"disponivel": True, "motivo": "",
                                     "comando": "rm"}}),
            "gasto negativo": _estado_bom(gasto_dia_usd=-1),
            "gasto texto": _estado_bom(gasto_dia_usd="1"),
            "gasto bool": _estado_bom(gasto_dia_usd=True),
            "chave extra": dict(_estado_bom(), extra=1),
        }
        for nome, corpo in ruins.items():
            with self.subTest(caso=nome):
                r = self.maquina(self.t_a1, "/agente/voz/estado", "POST", corpo)
                self.assertEqual(r.status, 400, r.corpo)
        faltando = _estado_bom()
        del faltando["cerebros"]
        self.assertEqual(self.maquina(self.t_a1, "/agente/voz/estado", "POST",
                                      faltando).status, 400)
        # NaN e Infinity sao JSON invalido, mas o `json` do Python os aceita.
        bruto = json.dumps(_estado_bom()).replace("1.25", "NaN").encode()
        self.assertEqual(self.maquina(self.t_a1, "/agente/voz/estado", "POST",
                                      bruto=bruto).status, 400)
        self.assertEqual(self.maquina(self.t_a1, "/agente/voz/estado", "POST",
                                      bruto=b"{isto nao e json").status, 400)
        self.assertEqual(self.maquina(self.t_a1, "/agente/voz/estado", "POST",
                                      bruto=b"[1,2]").status, 400)
        con = banco.conectar()
        n = con.execute("SELECT COUNT(*) FROM voz_estado").fetchone()[0]
        con.close()
        self.assertEqual(n, 0, "um estado recusado foi gravado mesmo assim")

    def test_estado_acima_de_64kb_e_recusado(self):
        grande = _estado_bom(cerebros={"hermes": {
            "disponivel": True, "motivo": "x" * (70 * 1024)}})
        r = self.maquina(self.t_a1, "/agente/voz/estado", "POST", grande)
        self.assertEqual(r.status, 400)

    def test_o_estado_novo_substitui_o_velho(self):
        self.maquina(self.t_a1, "/agente/voz/estado", "POST", _estado_bom())
        self.maquina(self.t_a1, "/agente/voz/estado", "POST",
                     _estado_bom(cerebro_ativo="hermes", gasto_dia_usd=9))
        con = banco.conectar()
        n = con.execute("SELECT COUNT(*) FROM voz_estado WHERE maquina_id = ?",
                        (self.m_a1,)).fetchone()[0]
        con.close()
        self.assertEqual(n, 1)
        a1 = next(m for m in self.dono(self.uid, "/api/voz").json["maquinas"]
                  if m["maquina_id"] == self.m_a1)
        self.assertEqual(a1["estado"]["cerebro_ativo"], "hermes")

    # ---------------------------------------------------------------- recado
    def test_o_dono_deixa_um_recado_e_o_vozs_o_recebe_uma_vez(self):
        r = self.recado(self.uid, self.m_a1, alvo="dervs", texto="oi")
        self.assertEqual(r.status, 200, r.corpo)
        id_ = r.json["id"]
        import uuid
        self.assertEqual(str(uuid.UUID(id_, version=4)), id_)
        entrega = self.maquina(self.t_a1, "/agente/voz/recados", "GET")
        self.assertEqual(entrega.status, 200, entrega.corpo)
        itens = entrega.json["recados"]
        self.assertEqual([i["id"] for i in itens], [id_])
        self.assertEqual(set(itens[0]), {"id", "criado_em", "tipo", "alvo",
                                         "texto", "nivel", "cerebro_pedido"})
        self.assertEqual(self.linha(id_)["estado"], "entregue")
        again = self.maquina(self.t_a1, "/agente/voz/recados", "GET")
        self.assertEqual(again.json["recados"], [], "o recado saiu duas vezes")

    def test_a_entrega_e_de_no_maximo_dez_por_vez(self):
        for n in range(12):
            self.assertEqual(self.recado(self.uid, self.m_a1,
                                         texto=str(n)).status, 200)
        primeira = self.maquina(self.t_a1, "/agente/voz/recados", "GET")
        self.assertEqual(len(primeira.json["recados"]), 10)
        segunda = self.maquina(self.t_a1, "/agente/voz/recados", "GET")
        self.assertEqual(len(segunda.json["recados"]), 2)

    def test_o_recado_so_chega_na_maquina_a_que_se_destina(self):
        self.recado(self.uid, self.m_a2)
        self.assertEqual(self.maquina(self.t_a1, "/agente/voz/recados",
                                      "GET").json["recados"], [])
        self.assertEqual(len(self.maquina(self.t_a2, "/agente/voz/recados",
                                          "GET").json["recados"]), 1)

    def test_recado_invalido_e_400(self):
        m = self.m_a1
        ruins = {
            "tipo": _recado_bom(m, tipo="executar"),
            "nivel": _recado_bom(m, nivel="tudo"),
            "cerebro": _recado_bom(m, cerebro_pedido="jev"),
            "alvo vazio": _recado_bom(m, alvo=""),
            "alvo nulo": _recado_bom(m, alvo=None),
            "alvo barra": _recado_bom(m, alvo="a/b"),
            "alvo contrabarra": _recado_bom(m, alvo="a\\b"),
            "alvo ..": _recado_bom(m, alvo=".."),
            "alvo a..b": _recado_bom(m, alvo="a..b"),
            "alvo dois-pontos": _recado_bom(m, alvo="C:dervs"),
            "alvo espaco": _recado_bom(m, alvo="a b"),
            "alvo longo": _recado_bom(m, alvo="a" * 101),
            "alvo quebra de linha": _recado_bom(m, alvo="dervs\n"),
            "texto longo": _recado_bom(m, texto="x" * 501),
            "texto NUL": _recado_bom(m, texto="a\x00b"),
            "texto numero": _recado_bom(m, texto=5),
            "maquina texto": _recado_bom("1"),
            "maquina bool": _recado_bom(True),
        }
        for nome, corpo in ruins.items():
            with self.subTest(caso=nome):
                r = self.dono(self.uid, "/api/voz/recado", "POST", corpo)
                self.assertEqual(r.status, 400, r.corpo)
        con = banco.conectar()
        n = con.execute("SELECT COUNT(*) FROM voz_recado").fetchone()[0]
        con.close()
        self.assertEqual(n, 0)

    def test_o_texto_e_dado_e_nao_e_interpretado(self):
        perigoso = "'; DROP TABLE voz_recado; -- $(rm -rf /) <script>"
        r = self.recado(self.uid, self.m_a1, texto=perigoso)
        self.assertEqual(r.status, 200, r.corpo)
        self.assertEqual(self.linha(r.json["id"])["texto"], perigoso)

    def test_teto_de_pendentes_por_conta(self):
        for n in range(servir.Hub.TETO_DE_PENDENTES):
            self.assertEqual(self.recado(self.uid, self.m_a1).status, 200, n)
        r = self.recado(self.uid, self.m_a1)
        self.assertEqual(r.status, 429, r.corpo)
        self.assertIn("recados", r.json["erro"])
        # O vizinho tem o teto dele, e o teto do dono nao o afeta.
        self.assertEqual(self.recado(self.outro, self.m_b1).status, 200)
        # Entregar nao libera a vaga (o VOZ ainda nao respondeu)? Libera: so
        # `pendente` conta, e `entregue` ja esta nas maos do VOZ.
        self.maquina(self.t_a1, "/agente/voz/recados", "GET")
        self.assertEqual(self.recado(self.uid, self.m_a1).status, 200)

    # ------------------------------------------------------------- resultado
    def _recado_entregue(self, uid=None, token=None, mid=None):
        r = self.recado(uid or self.uid, mid or self.m_a1)
        self.assertEqual(r.status, 200, r.corpo)
        self.maquina(token or self.t_a1, "/agente/voz/recados", "GET")
        return r.json["id"]

    def test_o_resultado_entra_e_aparece_no_painel(self):
        id_ = self._recado_entregue()
        r = self.maquina(self.t_a1, "/agente/voz/resultado", "POST",
                         _resultado_bom(id_, cerebro="hermes", custo_usd=0.5))
        self.assertEqual(r.status, 200, r.corpo)
        rec = next(x for x in self.dono(self.uid, "/api/voz").json["recados"]
                   if x["id"] == id_)
        self.assertEqual((rec["estado"], rec["cerebro"], rec["resumo"],
                          rec["custo_usd"]),
                         ("feito", "hermes", "tudo certo", 0.5))
        self.assertEqual(set(rec), {"id", "criado_em", "maquina_id", "tipo",
                                    "alvo", "nivel", "cerebro_pedido", "estado",
                                    "cerebro", "resumo", "custo_usd",
                                    "terminado_em"})

    def test_resultado_repetido_nao_sobrescreve(self):
        id_ = self._recado_entregue()
        self.maquina(self.t_a1, "/agente/voz/resultado", "POST",
                     _resultado_bom(id_, resumo="primeiro"))
        r = self.maquina(self.t_a1, "/agente/voz/resultado", "POST",
                         _resultado_bom(id_, estado="falhou", resumo="segundo",
                                        custo_usd=99))
        self.assertEqual(r.status, 200, r.corpo)
        linha = self.linha(id_)
        self.assertEqual((linha["estado"], linha["resumo"], linha["custo_usd"]),
                         ("feito", "primeiro", 0.12))

    def test_aguardando_clique_ainda_pode_virar_feito(self):
        id_ = self._recado_entregue()
        self.maquina(self.t_a1, "/agente/voz/resultado", "POST",
                     _resultado_bom(id_, estado="aguardando_clique"))
        self.assertEqual(self.linha(id_)["estado"], "aguardando_clique")
        self.maquina(self.t_a1, "/agente/voz/resultado", "POST",
                     _resultado_bom(id_, estado="feito"))
        self.assertEqual(self.linha(id_)["estado"], "feito")

    def test_resultado_invalido_e_400(self):
        id_ = self._recado_entregue()
        ruins = {
            "sem id": _resultado_bom(None),
            "estado": _resultado_bom(id_, estado="pendente"),
            "estado desconhecido": _resultado_bom(id_, estado="ok"),
            "cerebro": _resultado_bom(id_, cerebro="gpt"),
            "resumo longo": _resultado_bom(id_, resumo="x" * 1001),
            "resumo numero": _resultado_bom(id_, resumo=3),
            "custo negativo": _resultado_bom(id_, custo_usd=-0.01),
            "custo texto": _resultado_bom(id_, custo_usd="1"),
            "duracao negativa": _resultado_bom(id_, duracao_s=-1),
            "terminado_em lixo": _resultado_bom(id_, terminado_em="amanha"),
            "id gigante": _resultado_bom("x" * 65),
        }
        for nome, corpo in ruins.items():
            with self.subTest(caso=nome):
                r = self.maquina(self.t_a1, "/agente/voz/resultado", "POST", corpo)
                self.assertEqual(r.status, 400, r.corpo)
        self.assertEqual(self.linha(id_)["estado"], "entregue")

    def test_inexistente_e_de_outra_maquina_dao_a_mesma_resposta(self):
        id_ = self._recado_entregue()
        inventado = self.maquina(self.t_a1, "/agente/voz/resultado", "POST",
                                 _resultado_bom("nao-existe"))
        outra_maquina_do_mesmo_dono = self.maquina(
            self.t_a2, "/agente/voz/resultado", "POST", _resultado_bom(id_))
        outra_conta = self.maquina(self.t_b1, "/agente/voz/resultado", "POST",
                                   _resultado_bom(id_))
        for r in (inventado, outra_maquina_do_mesmo_dono, outra_conta):
            self.assertEqual(r.status, 404, r.corpo)
        self.assertEqual({inventado.corpo, outra_maquina_do_mesmo_dono.corpo,
                          outra_conta.corpo}, {inventado.corpo})
        self.assertEqual(self.linha(id_)["estado"], "entregue",
                         "uma maquina alheia respondeu o recado")

    # ------------------------------------------ duas contas, as cinco rotas
    def test_isolamento_1_estado_vai_so_para_a_maquina_de_quem_mandou(self):
        self.maquina(self.t_a1, "/agente/voz/estado", "POST",
                     _estado_bom(cerebro_ativo="hermes"))
        self.maquina(self.t_b1, "/agente/voz/estado", "POST",
                     _estado_bom(cerebro_ativo="jev_triagem"))
        con = banco.conectar()
        linhas = {r["maquina_id"]: (r["usuario_id"], json.loads(r["dados"]))
                  for r in con.execute("SELECT * FROM voz_estado")}
        con.close()
        self.assertEqual(linhas[self.m_a1][0], self.uid)
        self.assertEqual(linhas[self.m_b1][0], self.outro)
        self.assertEqual(linhas[self.m_a1][1]["cerebro_ativo"], "hermes")
        self.assertEqual(linhas[self.m_b1][1]["cerebro_ativo"], "jev_triagem")

    def test_isolamento_2_recados_so_para_a_maquina_do_dono(self):
        self.assertEqual(self.recado(self.uid, self.m_a1).status, 200)
        self.assertEqual(self.recado(self.outro, self.m_b1).status, 200)
        de_b = self.maquina(self.t_b1, "/agente/voz/recados", "GET").json["recados"]
        self.assertEqual(len(de_b), 1)
        self.assertEqual(self.linha(de_b[0]["id"])["usuario_id"], self.outro)
        de_a = self.maquina(self.t_a1, "/agente/voz/recados", "GET").json["recados"]
        self.assertEqual(len(de_a), 1)
        self.assertEqual(self.linha(de_a[0]["id"])["usuario_id"], self.uid)

    def test_isolamento_3_resultado_de_outra_conta_e_404_e_nao_muda_nada(self):
        id_ = self._recado_entregue()
        r = self.maquina(self.t_b1, "/agente/voz/resultado", "POST",
                         _resultado_bom(id_, estado="falhou"))
        self.assertEqual(r.status, 404)
        self.assertEqual(self.linha(id_)["estado"], "entregue")

    def test_isolamento_4_o_painel_so_mostra_o_que_e_da_conta(self):
        self.maquina(self.t_a1, "/agente/voz/estado", "POST", _estado_bom())
        id_a = self.recado(self.uid, self.m_a1).json["id"]
        id_b = self.recado(self.outro, self.m_b1).json["id"]
        va = self.dono(self.uid, "/api/voz").json
        vb = self.dono(self.outro, "/api/voz").json
        self.assertEqual({m["maquina_id"] for m in va["maquinas"]},
                         {self.m_a1, self.m_a2})
        self.assertEqual({m["maquina_id"] for m in vb["maquinas"]}, {self.m_b1})
        self.assertEqual([r["id"] for r in va["recados"]], [id_a])
        self.assertEqual([r["id"] for r in vb["recados"]], [id_b])
        self.assertIsNone(vb["maquinas"][0]["estado"],
                          "o estado da conta A apareceu na conta B")

    def test_isolamento_5_recado_para_maquina_alheia_ou_inexistente_e_a_mesma_404(self):
        alheia = self.recado(self.outro, self.m_a1)
        inexistente = self.recado(self.outro, 999999)
        self.assertEqual(alheia.status, 404, alheia.corpo)
        self.assertEqual(inexistente.status, 404)
        self.assertEqual(alheia.corpo, inexistente.corpo)
        con = banco.conectar()
        n = con.execute("SELECT COUNT(*) FROM voz_recado").fetchone()[0]
        con.close()
        self.assertEqual(n, 0, "o recado da conta B entrou na maquina da A")

    # ---------------------------------------------------------------- balcao
    def test_o_balcao_voz_esgota_e_as_outras_rotas_continuam(self):
        antigo = servir.Hub.TETO_DE_RECADOS
        servir.Hub.TETO_DE_RECADOS = 3
        self.addCleanup(lambda: setattr(servir.Hub, "TETO_DE_RECADOS", antigo))
        cookies, cab = self.sessao(self.uid)
        vistos = [self.pedir("/api/voz/recado", "POST", {}, cookies=cookies,
                             cabecalhos=cab).status for _ in range(5)]
        self.assertEqual(vistos, [400, 400, 400, 429, 429], vistos)
        self.assertEqual(self.pedir("/api/maquinas", cookies=cookies).status, 200)
        self.assertEqual(self.pedir("/api/voz", cookies=cookies).status, 200)
        self.assertEqual(self.maquina(self.t_a1, "/agente/relatorio", "POST",
                                      {"projetos": []}).status, 200)
        # Nem o pareamento (balcao `pareamento`) nem a cortina foram gastos.
        self.assertEqual(self.pedir("/agente/parear", "POST",
                                    {"codigo": "000000"}).status, 401)

    def test_o_balcao_da_maquina_esgota_e_o_relatorio_continua(self):
        antigo = servir.Hub.TETO_DA_VOZ
        servir.Hub.TETO_DA_VOZ = 2
        self.addCleanup(lambda: setattr(servir.Hub, "TETO_DA_VOZ", antigo))
        vistos = [self.maquina(self.t_a1, "/agente/voz/recados", "GET").status
                  for _ in range(4)]
        self.assertEqual(vistos, [200, 200, 429, 429], vistos)
        # O teto e POR MAQUINA: a outra responde, e o relatorio tambem.
        self.assertEqual(self.maquina(self.t_a2, "/agente/voz/recados",
                                      "GET").status, 200)
        self.assertEqual(self.maquina(self.t_a1, "/agente/relatorio", "POST",
                                      {"projetos": []}).status, 200)

    def test_o_balcao_voz_nao_e_emprestado_de_outro(self):
        """Quem le o codigo ve os nomes; um balcao emprestado esgotaria junto."""
        import inspect
        for nome in ("_voz_recado", "_voz_maquina"):
            fonte = inspect.getsource(getattr(servir.Hub, nome))
            self.assertIn('balcao="voz"', fonte, nome)
            self.assertNotIn("TETO_DE_ENDERECOS", fonte, nome)


class AsRotasDaPonte(unittest.TestCase):
    CLASSES = {
        "/agente/voz/estado": ("POST", "maquina"),
        "/agente/voz/recados": ("GET", "maquina"),
        "/agente/voz/resultado": ("POST", "maquina"),
        "/api/voz": ("GET", "dado"),
        "/api/voz/recado": ("POST", "dado"),
    }

    def test_cada_rota_tem_metodo_e_classe_declarados(self):
        for caminho, (metodo, acesso) in self.CLASSES.items():
            with self.subTest(rota=caminho):
                self.assertIn(caminho, servir.ROTAS)
                self.assertEqual(servir.ROTAS[caminho].metodo, metodo)
                self.assertEqual(servir.ROTAS[caminho].acesso, acesso)

    def test_nao_ha_outra_rota_de_voz(self):
        """Rota nova na ponte exige mexer aqui: de proposito."""
        achadas = {c for c in servir.ROTAS if "voz" in c.lower()}
        self.assertEqual(achadas, set(self.CLASSES))

    def test_nenhuma_rota_abre_terminal_shell_ou_ssh(self):
        for caminho in self.CLASSES:
            rota = servir.ROTAS[caminho]
            for palavra in ("terminal", "shell", "ssh", "pty", "exec", "comando"):
                self.assertNotIn(palavra, caminho.lower())
                self.assertNotIn(palavra, rota.funcao.__name__.lower())
        import inspect
        for caminho in self.CLASSES:
            fonte = inspect.getsource(servir.ROTAS[caminho].funcao)
            for chamada in ("subprocess", "os.system", "Popen", "paramiko",
                            "socket."):
                self.assertNotIn(chamada, fonte, caminho)

    def test_a_ponte_nao_carimba_visto_em_no_codigo(self):
        """Guarda de codigo-fonte: o comportamento ja e testado pelo servidor,
        e este pega o dia em que alguem chame o carimbo por outro caminho."""
        import inspect
        for caminho in self.CLASSES:
            fonte = inspect.getsource(servir.ROTAS[caminho].funcao)
            self.assertNotIn("visto_em", fonte, caminho)
            self.assertNotIn("receber_relatorio", fonte, caminho)
        for nome in ("guardar_voz_estado", "criar_voz_recado",
                     "entregar_voz_recados", "registrar_voz_resultado",
                     "voz_do_usuario"):
            fonte = inspect.getsource(getattr(banco, nome))
            self.assertNotIn("UPDATE maquina", fonte, nome)

    def test_toda_consulta_da_ponte_filtra_por_usuario(self):
        """O filtro por dono tem de estar no SQL de cada funcao do banco."""
        import inspect
        for nome in ("guardar_voz_estado", "criar_voz_recado",
                     "entregar_voz_recados", "registrar_voz_resultado",
                     "voz_do_usuario"):
            fonte = inspect.getsource(getattr(banco, nome))
            self.assertIn("usuario_id", fonte, nome)
        fonte = inspect.getsource(banco.entregar_voz_recados)
        self.assertIn("maquina_id = ? AND usuario_id = ?", fonte)
        fonte = inspect.getsource(banco.registrar_voz_resultado)
        self.assertIn("AND usuario_id = ?", fonte)


if __name__ == "__main__":
    unittest.main()
