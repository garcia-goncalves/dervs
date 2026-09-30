# -*- coding: utf-8 -*-
"""Os avisos que o painel gera sozinho para o DERVS-VOZ (tipo `avisar`).

  1. Um aviso por OCORRENCIA: a segunda varredura nao repete.
  2. No maximo 5 avisos novos por varredura e por conta.
  3. Conta sem VOZ de estado fresco nao recebe nada, e nada se acumula.
  4. Duas contas nao se cruzam: o aviso de uma nunca vai para a maquina da outra.
  5. `avisar` e sempre `leitura`: `muda_estado` e recusado (rota e banco).
  6. Computador que NUNCA mediu nao "calou": sem um "mediu" nao ha "parou".

    python test_voz_avisos.py
"""
from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco     # noqa: E402
import cortina   # noqa: E402
import servir    # noqa: E402

AGORA = "2026-09-30T12:00:00+00:00"


def _antes(segundos: int) -> str:
    return (datetime.fromisoformat(AGORA)
            - timedelta(seconds=segundos)).isoformat(timespec="seconds")


def _estado():
    return {"versao": 1, "enviado_em": AGORA, "cerebro_ativo": "claude_code",
            "cerebros": {}, "gasto_dia_usd": 0.0}


def _alta(n, projeto="dervs"):
    return {"id": "vulnerabilidade:%s:%d" % (projeto, n), "regra": "x",
            "gravidade": "alta", "projeto": projeto,
            "texto": "problema %d" % n}


class _Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        antigo, banco.BANCO = banco.BANCO, Path(self.dir.name) / "hub.db"
        self.addCleanup(lambda: setattr(banco, "BANCO", antigo))
        self.con = banco.conectar()
        self.addCleanup(self.con.close)
        self.uid = banco.criar_usuario("dono@teste.local", con=self.con)
        self.outro = banco.criar_usuario("vizinho@teste.local", con=self.con)
        self.hub = servir.Hub.__new__(servir.Hub)   # sem atender pedido

    def maquina(self, uid, nome, visto=None, voz=False):
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(uid, codigo, banco.prazo(600), con=self.con)
        token = banco.usar_pareamento(codigo, nome, con=self.con)
        mid = banco.maquina_por_token(token, con=self.con)["id"]
        if visto:
            self.con.execute("UPDATE maquina SET visto_em = ? WHERE id = ?",
                             (visto, mid))
            self.con.commit()
        if voz:
            banco.guardar_voz_estado(mid, uid, _estado(),
                                     agora_iso=_antes(30), con=self.con)
        return mid

    def varrer(self, pendencias=()):
        with mock.patch.object(servir.regras, "avaliar",
                               return_value=list(pendencias)):
            self.hub._varrer_vigilia(agora_iso=AGORA, forcar=True)

    def avisos(self, mid=None):
        sql = "SELECT * FROM voz_recado WHERE tipo = 'avisar'"
        args = ()
        if mid is not None:
            sql, args = sql + " AND maquina_id = ?", (mid,)
        return [dict(l) for l in self.con.execute(sql + " ORDER BY rowid", args)]


class OsAvisos(_Base):
    def test_calou_gera_um_aviso_em_portugues_e_nao_repete(self):
        voz = self.maquina(self.uid, "voz", voz=True)
        muda = self.maquina(self.uid, "notebook\x1b[31m" + "x" * 200,
                            visto=_antes(1800))
        self.varrer()
        self.varrer()                                   # segunda: nao repete
        a, = self.avisos(voz)
        self.assertEqual(a["nivel"], "leitura")
        self.assertEqual(a["alvo"], "vigilia")
        self.assertIn("parou de medir há 30 minutos", a["texto"])
        self.assertIn("Não sei como ele está.", a["texto"])
        self.assertNotIn("\x1b", a["texto"])
        nome = a["texto"].split("O computador ")[1].split(" parou")[0]
        self.assertLessEqual(len(nome), 80)
        chave, = [l["chave"] for l in self.con.execute(
            "SELECT chave FROM voz_aviso")]
        self.assertEqual(chave, "calou:%d:2026-09-30" % muda)

    def test_maquina_nunca_medida_nao_calou(self):
        voz = self.maquina(self.uid, "voz", voz=True)
        self.maquina(self.uid, "recem-pareado")           # visto_em nulo
        self.varrer()
        self.assertEqual(self.avisos(voz), [])

    def test_maquina_medindo_em_dia_nao_calou(self):
        voz = self.maquina(self.uid, "voz", voz=True)
        self.maquina(self.uid, "ok", visto=_antes(banco.VIGILIA_LIMITE_S))
        self.varrer()
        self.assertEqual(self.avisos(voz), [])

    def test_pendencia_alta_avisa_uma_vez_com_projeto_no_texto(self):
        voz = self.maquina(self.uid, "voz", voz=True)
        self.varrer([_alta(1)])
        self.varrer([_alta(1)])
        a, = self.avisos(voz)
        self.assertEqual(a["alvo"], "dervs")
        self.assertIn("dervs", a["texto"])
        self.assertIn("problema 1", a["texto"])

    def test_pendencia_que_nao_e_alta_nao_avisa(self):
        voz = self.maquina(self.uid, "voz", voz=True)
        media = dict(_alta(1), gravidade="media")
        self.varrer([media])
        self.assertEqual(self.avisos(voz), [])

    def test_teto_de_cinco_por_varredura_e_o_resto_vem_na_proxima(self):
        voz = self.maquina(self.uid, "voz", voz=True)
        pend = [_alta(n) for n in range(8)]
        self.varrer(pend)
        self.assertEqual(len(self.avisos(voz)), 5)
        self.varrer(pend)
        self.assertEqual(len(self.avisos(voz)), 8)

    def test_sem_voz_vivo_nao_gera_nem_acumula(self):
        self.maquina(self.uid, "sem-voz")                        # sem estado
        velho = self.maquina(self.uid, "voz-velho")
        banco.guardar_voz_estado(velho, self.uid, _estado(),
                                 agora_iso=_antes(1201), con=self.con)
        self.varrer([_alta(1)])
        self.assertEqual(self.avisos(), [])
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM voz_aviso").fetchone()[0], 0)
        # Quando o VOZ volta, o aviso ainda nao existe: nasce agora, uma vez.
        banco.guardar_voz_estado(velho, self.uid, _estado(),
                                 agora_iso=_antes(5), con=self.con)
        self.varrer([_alta(1)])
        self.assertEqual(len(self.avisos(velho)), 1)

    def test_voz_revogado_nao_e_destino(self):
        voz = self.maquina(self.uid, "voz", voz=True)
        banco.revogar_maquina(voz, self.uid, con=self.con)
        self.varrer([_alta(1)])
        self.assertEqual(self.avisos(), [])

    def test_duas_contas_nao_se_cruzam(self):
        voz_a = self.maquina(self.uid, "voz-a", voz=True)
        voz_b = self.maquina(self.outro, "voz-b", voz=True)
        muda_b = self.maquina(self.outro, "pc-b", visto=_antes(5000))
        # O motor roda por conta: so a conta A tem pendencia.
        def avaliar(projetos, **kw):
            return [_alta(1)] if self._conta_atual == self.uid else []
        chamadas = []
        real = banco.montar_estado

        def montar(con=None, *, usuario_id):
            self._conta_atual = usuario_id
            chamadas.append(usuario_id)
            return real(con, usuario_id=usuario_id)
        with mock.patch.object(servir.regras, "avaliar", side_effect=avaliar), \
                mock.patch.object(banco, "montar_estado", side_effect=montar):
            self.hub._varrer_vigilia(agora_iso=AGORA, forcar=True)
        self.assertEqual(sorted(chamadas), sorted([self.uid, self.outro]))
        self.assertEqual([a["usuario_id"] for a in self.avisos(voz_a)],
                         [self.uid])
        self.assertIn("problema 1", self.avisos(voz_a)[0]["texto"])
        # A conta B so recebe o DELA (o pc-b calou) e na maquina DELA.
        b = self.avisos(voz_b)
        self.assertEqual([x["usuario_id"] for x in b], [self.outro])
        self.assertIn("pc-b", b[0]["texto"])
        self.assertEqual(len(self.avisos()), 2)
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM voz_aviso WHERE usuario_id = ?",
            (self.uid,)).fetchone()[0], 1)
        self.assertIsNotNone(muda_b)

    def test_a_chave_de_uma_conta_nao_silencia_a_outra(self):
        voz_a = self.maquina(self.uid, "voz-a", voz=True)
        voz_b = self.maquina(self.outro, "voz-b", voz=True)
        self.assertTrue(banco.avisar_uma_vez(self.uid, voz_a, "k", "vigilia",
                                             "t", AGORA, con=self.con))
        self.assertFalse(banco.avisar_uma_vez(self.uid, voz_a, "k", "vigilia",
                                              "t", AGORA, con=self.con))
        self.assertTrue(banco.avisar_uma_vez(self.outro, voz_b, "k", "vigilia",
                                             "t", AGORA, con=self.con))

    def test_aviso_para_maquina_de_outra_conta_e_recusado(self):
        voz_b = self.maquina(self.outro, "voz-b", voz=True)
        self.assertFalse(banco.avisar_uma_vez(self.uid, voz_b, "k", "vigilia",
                                              "t", AGORA, con=self.con))
        # E a chave nao fica gravada: a transacao inteira foi desfeita.
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM voz_aviso").fetchone()[0], 0)

    def test_recado_que_nao_coube_desfaz_a_chave(self):
        voz = self.maquina(self.uid, "voz", voz=True)
        self.assertFalse(banco.avisar_uma_vez(
            self.uid, voz, "k", "vigilia", "t", AGORA, con=self.con,
            teto_pendentes=0))
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM voz_aviso").fetchone()[0], 0)

    def test_avisar_com_muda_estado_e_recusado_no_banco(self):
        voz = self.maquina(self.uid, "voz", voz=True)
        self.assertEqual(banco.criar_voz_recado(
            self.uid, voz, "avisar", "vigilia", "t", "muda_estado", "auto",
            20, agora_iso=AGORA, con=self.con), (None, "nivel"))
        self.assertEqual(self.avisos(), [])

    def test_avisos_e_recados_do_dono_tem_tetos_separados(self):
        """Fila cheia de avisos nao tranca o dono, e recado do dono nao cala os
        avisos: cada um paga o proprio teto."""
        voz = self.maquina(self.uid, "voz", voz=True)
        for n in range(3):
            self.assertEqual(banco.criar_voz_recado(
                self.uid, voz, "avisar", "vigilia", "t%d" % n, "leitura",
                "auto", 3, agora_iso=AGORA, con=self.con)[1], None)
        self.assertEqual(banco.criar_voz_recado(
            self.uid, voz, "avisar", "vigilia", "t", "leitura", "auto", 3,
            agora_iso=AGORA, con=self.con), (None, "teto"))
        # Os 3 avisos pendentes NAO contam para o dono.
        for n in range(3):
            self.assertEqual(banco.criar_voz_recado(
                self.uid, voz, "status", "dervs", "t", "leitura", "auto", 3,
                agora_iso=AGORA, con=self.con)[1], None)
        self.assertEqual(banco.criar_voz_recado(
            self.uid, voz, "status", "dervs", "t", "leitura", "auto", 3,
            agora_iso=AGORA, con=self.con), (None, "teto"))

    def test_a_varredura_nunca_levanta(self):
        self.maquina(self.uid, "voz", voz=True)
        with mock.patch.object(banco, "montar_estado",
                               side_effect=RuntimeError("quebrou")):
            self.hub._varrer_vigilia(agora_iso=AGORA, forcar=True)
        with mock.patch.object(banco, "voz_destinos_de_aviso",
                               side_effect=RuntimeError("quebrou")):
            self.hub._varrer_vigilia(agora_iso=AGORA, forcar=True)

    def test_o_codigo_da_varredura_nao_executa_comando(self):
        import inspect
        fonte = (inspect.getsource(servir.Hub._varrer_vigilia)
                 + inspect.getsource(servir.Hub._avisos_da_conta))
        for proibido in ("subprocess", "os.system", "Popen"):
            self.assertNotIn(proibido, fonte)


class AsRotas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls._banco_antigo = banco.BANCO
        banco.BANCO = Path(cls.dir.name) / "hub.db"
        con = banco.conectar()
        cls.uid = banco.criar_usuario("dono@teste.local", con=con)
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(cls.uid, codigo, banco.prazo(600), con=con)
        token = banco.usar_pareamento(codigo, "pc", con=con)
        cls.mid = banco.maquina_por_token(token, con=con)["id"]
        con.close()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servir.Hub)
        cls.porta = cls.srv.server_address[1]
        cls._antigos = (servir.PORTA, servir.ORIGENS_OK, servir.HOSTS_OK)
        servir.PORTA = cls.porta
        servir.ORIGENS_OK = {"http://127.0.0.1:%d" % cls.porta}
        servir.HOSTS_OK = {"127.0.0.1:%d" % cls.porta}
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        servir.PORTA, servir.ORIGENS_OK, servir.HOSTS_OK = cls._antigos
        banco.BANCO = cls._banco_antigo
        cls.dir.cleanup()

    def setUp(self):
        cortina.zerar_tentativas()
        self.addCleanup(cortina.zerar_tentativas)

    def _pedir(self, caminho, metodo="GET", corpo=None):
        cookie = banco.novo_token()
        con = banco.conectar()
        try:
            banco.abrir_sessao(self.uid, cookie, banco.prazo(3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
        finally:
            con.close()
        s = banco.sessao_valida(final)
        cab = {"Host": "127.0.0.1:%d" % self.porta,
               "Cookie": "sessao=%s" % final,
               "Origin": "http://127.0.0.1:%d" % self.porta,
               "X-Token": servir.Hub._csrf_da_sessao(s)}
        dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
        if dados is not None:
            cab["Content-Type"] = "application/json"
            cab["Content-Length"] = str(len(dados))
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        try:
            c.request(metodo, caminho, body=dados, headers=cab)
            r = c.getresponse()
            return r.status, json.loads(r.read() or b"{}")
        finally:
            c.close()

    def _corpo(self, **troca):
        c = {"maquina_id": self.mid, "tipo": "avisar", "alvo": "vigilia",
             "texto": "", "nivel": "leitura", "cerebro_pedido": "auto"}
        c.update(troca)
        return c

    def test_rota_do_dono_recusa_avisar_com_muda_estado(self):
        status, _ = self._pedir("/api/voz/recado", "POST",
                                self._corpo(nivel="muda_estado"))
        self.assertEqual(status, 400)
        con = banco.conectar()
        try:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM voz_recado WHERE nivel = 'muda_estado'"
            ).fetchone()[0], 0)
        finally:
            con.close()

    def test_avisar_leitura_entra_e_aparece_na_lista(self):
        status, r = self._pedir("/api/voz/recado", "POST", self._corpo())
        self.assertEqual(status, 200, r)
        status, lista = self._pedir("/api/voz")
        self.assertEqual(status, 200)
        self.assertEqual([x["tipo"] for x in lista["recados"]], ["avisar"])

    def test_a_tela_nomeia_o_tipo_avisar_e_nao_o_oferece(self):
        raiz = Path(servir.__file__).parent
        js = (raiz / "assets" / "painel.js").read_text(encoding="utf-8")
        html = (raiz / "index.html").read_text(encoding="utf-8")
        self.assertIn('avisar: "Aviso do painel"', js)
        self.assertNotIn('value="avisar"', html)


if __name__ == "__main__":
    unittest.main()
