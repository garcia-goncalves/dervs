# -*- coding: utf-8 -*-
"""Testes do agente local e do pareamento por código de seis dígitos.

A pergunta deste arquivo é uma só: **o que impede um estranho de virar uma
máquina desta conta?** Seis dígitos são um milhão de possibilidades — pouco,
se o chute for de graça. O que os segura são três coisas, e cada uma tem um
teste nominal aqui:

  1. o prazo curto (dez minutos);
  2. o uso único (código gasto não vale de novo);
  3. o teto de chute POR ORIGEM, que mora na rota — dívida nomeada da etapa 8
     e obrigação declarada da 11.

E mais duas, sobre o que vem depois do pareamento: o token nasce preso a UM
usuário e UMA máquina (relatório com token de outra máquina não escreve na
conta errada), e **o envio de dado é o sinal de vida**. Não existe rota de
"estou vivo" separada: máquina que parou de medir tem de parecer parada, e não
viva. A mentira contrária é a pior possível neste produto.

    python test_agente.py
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import auditoria  # noqa: E402
import banco      # noqa: E402
import coletar    # noqa: E402
import cortina    # noqa: E402
import execucao   # noqa: E402
import servir     # noqa: E402

from agente import enviar  # noqa: E402


class OQueMedeNaoGrava(unittest.TestCase):
    """`coletar.medir()` mede e devolve. Se ele gravar, o agente grava na
    máquina errada — a dele, e não a do painel remoto."""

    def test_medir_existe_e_nao_toca_no_banco(self):
        self.assertTrue(callable(coletar.medir))
        fonte = Path("coletar.py").read_text(encoding="utf-8")
        corpo = fonte[fonte.index("def medir()"):fonte.index("def main()")]
        self.assertNotIn("banco.gravar", corpo,
                         "medir() voltou a escrever no banco: o agente passaria "
                         "a medir a maquina certa e gravar na errada.")

    def test_a_medicao_carrega_o_docker_mudo_separado_do_vazio(self):
        """A família de defeito de `7b4221c`: lista vazia e `None` dizem coisas
        opostas, e quem recebe do outro lado não tem como distinguir depois."""
        fonte = Path("coletar.py").read_text(encoding="utf-8")
        corpo = fonte[fonte.index("def medir()"):fonte.index("def main()")]
        self.assertIn("docker_mudo", corpo)
        self.assertIn("portas_mudas", corpo)


class OPareamentoNoBanco(unittest.TestCase):
    """A camada de baixo, sem servidor no meio."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self._antigo, banco.BANCO = banco.BANCO, Path(self.dir.name) / "hub.db"
        self.addCleanup(lambda: setattr(banco, "BANCO", self._antigo))
        self.con = banco.conectar()
        self.addCleanup(self.con.close)
        self.uid = banco.criar_usuario("dono@teste.local", con=self.con)
        self.outro = banco.criar_usuario("outro@teste.local", con=self.con)

    def test_codigo_vence_em_dez_minutos(self):
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(self.uid, codigo, banco.prazo(600), con=self.con)
        # Um segundo depois do prazo, o mesmo código não vale mais nada.
        depois = banco.prazo(601)
        self.assertIsNone(
            banco.usar_pareamento(codigo, agora_iso=depois, con=self.con),
            "codigo vencido ainda pareou — o prazo curto e uma das tres coisas "
            "que seguram seis digitos.")

    def test_codigo_usado_nao_serve_duas_vezes(self):
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(self.uid, codigo, banco.prazo(600), con=self.con)
        self.assertTrue(banco.usar_pareamento(codigo, "primeira", con=self.con))
        self.assertIsNone(banco.usar_pareamento(codigo, "segunda", con=self.con),
                          "o mesmo codigo pareou duas maquinas.")

    def test_o_token_nasce_preso_a_um_usuario_e_uma_maquina(self):
        a, b = banco.novo_codigo(6), banco.novo_codigo(6)
        banco.abrir_pareamento(self.uid, a, banco.prazo(600), con=self.con)
        banco.abrir_pareamento(self.outro, b, banco.prazo(600), con=self.con)
        ta = banco.usar_pareamento(a, "maquina-a", con=self.con)
        tb = banco.usar_pareamento(b, "maquina-b", con=self.con)
        ma = banco.maquina_por_token(ta, con=self.con)
        mb = banco.maquina_por_token(tb, con=self.con)
        self.assertEqual(ma["usuario_id"], self.uid)
        self.assertEqual(mb["usuario_id"], self.outro)
        self.assertNotEqual(ma["id"], mb["id"])
        self.assertNotEqual(ta, tb)

    def test_token_revogado_nao_abre_mais(self):
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(self.uid, codigo, banco.prazo(600), con=self.con)
        token = banco.usar_pareamento(codigo, con=self.con)
        maq = banco.maquina_por_token(token, con=self.con)
        self.assertTrue(banco.revogar_maquina(maq["id"], self.uid, con=self.con))
        self.assertIsNone(banco.maquina_por_token(token, con=self.con))

    def test_ninguem_revoga_a_maquina_do_vizinho(self):
        """O IDOR clássico da rota de remoção: o id vem do navegador."""
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(self.uid, codigo, banco.prazo(600), con=self.con)
        token = banco.usar_pareamento(codigo, con=self.con)
        maq = banco.maquina_por_token(token, con=self.con)
        self.assertFalse(banco.revogar_maquina(maq["id"], self.outro, con=self.con))
        self.assertIsNotNone(banco.maquina_por_token(token, con=self.con))

    def test_o_relatorio_e_que_carimba_a_vida(self):
        """Não há sinal de vida separado. `visto_em` só anda quando dado chega."""
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(self.uid, codigo, banco.prazo(600), con=self.con)
        token = banco.usar_pareamento(codigo, agora_iso="2020-01-01T00:00:00+00:00",
                                      con=self.con)
        maq = banco.maquina_por_token(token, con=self.con)
        self.assertEqual(maq["visto_em"], "2020-01-01T00:00:00+00:00")
        banco.receber_relatorio(maq["id"], [{"nome": "dervs", "caminho": "/x"}],
                                {"containers": [], "docker_mudo": False},
                                con=self.con)
        depois = banco.maquina_por_token(token, con=self.con)
        self.assertGreater(depois["visto_em"], maq["visto_em"])

    def test_projeto_que_sumiu_da_maquina_e_arquivado(self):
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(self.uid, codigo, banco.prazo(600), con=self.con)
        maq = banco.maquina_por_token(
            banco.usar_pareamento(codigo, con=self.con), con=self.con)
        banco.receber_relatorio(maq["id"], [{"nome": "a"}, {"nome": "b"}],
                                None, con=self.con)
        self.assertEqual({p["projeto"] for p in
                          banco.projetos_da_maquina(maq["id"], con=self.con)},
                         {"a", "b"})
        banco.receber_relatorio(maq["id"], [{"nome": "a"}], None, con=self.con)
        self.assertEqual({p["projeto"] for p in
                          banco.projetos_da_maquina(maq["id"], con=self.con)},
                         {"a"}, "o projeto que sumiu continuou na lista")

    def test_relatorio_vazio_nao_arquiva_a_conta_inteira(self):
        """Uma coleta que falhou inteira manda lista vazia. Arquivar tudo aí
        apagaria da tela projetos que continuam existindo."""
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(self.uid, codigo, banco.prazo(600), con=self.con)
        maq = banco.maquina_por_token(
            banco.usar_pareamento(codigo, con=self.con), con=self.con)
        banco.receber_relatorio(maq["id"], [{"nome": "a"}], None, con=self.con)
        banco.receber_relatorio(maq["id"], [], None, con=self.con)
        self.assertEqual([p["projeto"] for p in
                          banco.projetos_da_maquina(maq["id"], con=self.con)],
                         ["a"])


class MaquinaAutorizadaNaoEMaquinaConfiavel(unittest.TestCase):
    """Token vazado, ou agente adulterado, escreve o que quiser neste banco.

    Achado da releitura de segurança desta etapa: pareamento diz *quem* é, e
    não que o conteúdo é são. Sem teto, um relatório repetido enche o disco do
    servidor e deixa o painel ilegível com dez mil projetos inventados.
    """

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self._antigo, banco.BANCO = banco.BANCO, Path(self.dir.name) / "hub.db"
        self.addCleanup(lambda: setattr(banco, "BANCO", self._antigo))
        self.con = banco.conectar()
        self.addCleanup(self.con.close)
        uid = banco.criar_usuario("dono@teste.local", con=self.con)
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(uid, codigo, banco.prazo(600), con=self.con)
        self.maq = banco.maquina_por_token(
            banco.usar_pareamento(codigo, con=self.con), con=self.con)

    def test_ha_teto_de_projetos_por_relatorio(self):
        demais = banco.MAX_PROJETOS_POR_RELATORIO + 40
        r = banco.receber_relatorio(
            self.maq["id"], [{"nome": "p%d" % n} for n in range(demais)],
            None, con=self.con)
        self.assertEqual(r["projetos"], banco.MAX_PROJETOS_POR_RELATORIO)
        # E o corte NÃO é silencioso: "enviado: 300 projetos" pareceria a conta
        # inteira, e o agente imprime o aviso a partir deste número.
        self.assertEqual(r["cortados"], 40)

    def test_nome_e_caminho_gigantes_sao_cortados(self):
        banco.receber_relatorio(self.maq["id"],
                                [{"nome": "n" * 5000, "caminho": "c" * 9000}],
                                None, con=self.con)
        p = banco.projetos_da_maquina(self.maq["id"], con=self.con)[0]
        self.assertEqual(len(p["projeto"]), banco.MAX_NOME_DE_PROJETO)
        self.assertEqual(len(p["caminho"]), banco.MAX_CAMINHO)

    def test_lixo_no_lugar_de_projeto_e_ignorado_sem_estourar(self):
        r = banco.receber_relatorio(
            self.maq["id"], ["texto solto", None, 42, {"nome": ""}, {"nome": "ok"}],
            None, con=self.con)
        self.assertEqual(r["projetos"], 1)


class _Resposta:
    def __init__(self, status, corpo, cookies=()):
        self.status, self.corpo = status, corpo
        self.cabecalho_de_cookie = "; ".join(cookies)

    @property
    def json(self):
        try:
            return json.loads(self.corpo)
        except ValueError:
            return {}


class OServidorDeVerdade(unittest.TestCase):
    """Sobe o servidor numa porta livre e conversa com ele pelo soquete.

    O agente não é um navegador: ele não tem cookie, não manda `Origin` e não
    tem token anti-CSRF. Se a rota de ingestão exigir qualquer uma dessas três
    coisas, o agente nunca reporta — e é por isso que estes testes falam HTTP
    na mão em vez de reaproveitar o `pedir()` de `test_servir.py`.
    """

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls._banco_antigo = banco.BANCO
        banco.BANCO = Path(cls.dir.name) / "hub.db"
        con = banco.conectar()
        cls.combinacao = cortina.garantir_combinacao(con) or "000000"
        cls.uid = banco.criar_usuario("dono@teste.local", con=con)
        cls.outro = banco.criar_usuario("vizinho@teste.local", con=con)
        con.close()

        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servir.Hub)
        cls.porta = cls.srv.server_address[1]
        cls._porta_antiga = servir.PORTA
        cls._origens_antigas = servir.ORIGENS_OK
        cls._hosts_antigos = servir.HOSTS_OK
        servir.PORTA = cls.porta
        servir.ORIGENS_OK = {"http://127.0.0.1:%d" % cls.porta}
        servir.HOSTS_OK = {"127.0.0.1:%d" % cls.porta}
        cls.linha = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.linha.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        servir.PORTA = cls._porta_antiga
        servir.ORIGENS_OK = cls._origens_antigas
        servir.HOSTS_OK = cls._hosts_antigos
        banco.BANCO = cls._banco_antigo
        cls.dir.cleanup()

    def setUp(self):
        cortina.zerar_tentativas()
        self.addCleanup(cortina.zerar_tentativas)

    # ------------------------------------------------------------ utilidades
    def pedir(self, caminho, metodo="GET", corpo=None, cabecalhos=None,
              cookies=None):
        dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
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
            return _Resposta(r.status,
                             (r.read() or b"").decode("utf-8", "replace"),
                             r.headers.get_all("Set-Cookie") or [])
        finally:
            c.close()

    def com_sessao(self, uid=None):
        cookie = banco.novo_token()
        con = banco.conectar()
        try:
            banco.abrir_sessao(uid or self.uid, cookie, banco.prazo(3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(), con=con)
        finally:
            con.close()
        return {"sessao": final}

    def parear(self, uid=None):
        """Um código pelo caminho de dentro, e o token que ele vira."""
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(uid or self.uid, codigo, banco.prazo(600))
        r = self.pedir("/agente/parear", "POST",
                       {"codigo": codigo, "maquina": "maquina-de-teste"})
        self.assertEqual(r.status, 200, r.corpo)
        return r.json["token"]

    # --------------------------------------------------------------- o teto
    def test_o_teto_de_chute_por_origem_existe(self):
        """A obrigação nominal da etapa 11. Sem isto, seis dígitos são um
        milhão de tentativas de graça.

        O número do teto vem de `cortina.TETO`, e não escrito à mão aqui: ele é
        20 na máquina do dono e 5 no servidor, e um teste que fixasse "5"
        passaria verde na CI local enquanto o servidor mudava debaixo dele.
        """
        teto = cortina.TETO
        vistos = [self.pedir("/agente/parear", "POST",
                             {"codigo": "%06d" % n}).status
                  for n in range(teto + 2)]
        self.assertEqual(vistos[:teto], [401] * teto, vistos)
        self.assertEqual(vistos[teto:], [429, 429],
                         "o chute %d passou: nao ha teto por origem." % (teto + 1))

    def test_o_teto_do_agente_nao_tranca_a_cortina(self):
        """Fila própria por balcão: gastar o teto do pareamento não pode
        trancar o dono do lado de fora da capa — foi o que aconteceu com ele
        em 26/08/2026, por outro caminho."""
        for n in range(cortina.TETO + 1):
            self.pedir("/agente/parear", "POST", {"codigo": "%06d" % n})
        # `/entrada` responde 204 sempre — acerto e erro tem a MESMA cara, de
        # propósito. Quem diz que a combinação passou é o cookie, e é ele que
        # este teste olha.
        r = self.pedir("/entrada", "POST", {"combinacao": self.combinacao},
                       cabecalhos={"Origin": "http://127.0.0.1:%d" % self.porta})
        self.assertIn("cortina=", r.cabecalho_de_cookie,
                      "a cortina foi trancada pelo teto do agente")

    # ----------------------------------------------------------- a ingestão
    def test_relatorio_sem_token_nao_entra(self):
        r = self.pedir("/agente/relatorio", "POST", {"projetos": []})
        self.assertEqual(r.status, 401)

    def test_relatorio_com_token_de_outra_maquina_recebe_403(self):
        """O token é de UMA máquina. Revogada aquela, o token não abre nada —
        e nunca abre a conta do vizinho."""
        token = self.parear()
        maq = banco.maquina_por_token(token)
        banco.revogar_maquina(maq["id"], self.uid)
        r = self.pedir("/agente/relatorio", "POST", {"projetos": []},
                       cabecalhos={"Authorization": "Token " + token})
        self.assertIn(r.status, (401, 403), r.corpo)

    def test_token_inventado_nao_entra(self):
        r = self.pedir("/agente/relatorio", "POST", {"projetos": []},
                       cabecalhos={"Authorization": "Token " + banco.novo_token()})
        self.assertEqual(r.status, 401)

    def test_o_relatorio_grava_e_carimba_a_vida(self):
        token = self.parear()
        r = self.pedir("/agente/relatorio", "POST", {
            "projetos": [{"nome": "dervs", "caminho": "C:/x/dervs",
                          "git": {"sujos": []}}],
            "infra": {"containers": [], "docker_mudo": True, "portas": None},
            "avisos": ["o docker nao respondeu"],
        }, cabecalhos={"Authorization": "Token " + token})
        self.assertEqual(r.status, 200, r.corpo)
        self.assertEqual(r.json.get("projetos"), 1)

        # E o painel do dono vê o carimbo, com nome de máquina e sem token.
        # A máquina é procurada pelo id, e não por "a primeira da lista": o
        # banco é da classe inteira, e outro teste desta suíte já pareou outra.
        maq = banco.maquina_por_token(token)
        r2 = self.pedir("/api/maquinas", cookies=self.com_sessao())
        self.assertEqual(r2.status, 200, r2.corpo)
        maquinas = r2.json["maquinas"]
        minha = [m for m in maquinas if m["id"] == maq["id"]]
        self.assertEqual(len(minha), 1, maquinas)
        self.assertTrue(minha[0]["visto_em"])
        self.assertEqual(minha[0]["projetos"], 1)
        self.assertEqual(minha[0]["nome"], "maquina-de-teste")
        self.assertNotIn("token_hash", json.dumps(maquinas))

    def test_o_relatorio_nao_exige_origem_nem_cookie(self):
        """O agente não é navegador. Exigir `Origin` aqui seria escrever uma
        defesa que só atrapalha quem tem o token e não atrapalha quem não tem."""
        token = self.parear()
        r = self.pedir("/agente/relatorio", "POST", {"projetos": []},
                       cabecalhos={"Authorization": "Token " + token})
        self.assertEqual(r.status, 200, r.corpo)

    def test_nao_existe_rota_de_sinal_de_vida_separada(self):
        """A armadilha declarada da etapa 11: um "estou vivo" separado deixa a
        máquina parecer viva com a medição parada."""
        for inventada in ("/agente/vivo", "/agente/ping", "/agente/alo",
                          "/api/maquinas/vivo", "/agente/sinal"):
            self.assertNotIn(inventada, servir.ROTAS, inventada)

    # ------------------------------------------------- as rotas do dono
    def test_as_rotas_do_dono_exigem_sessao(self):
        for caminho, metodo in (("/api/maquinas", "GET"),
                                ("/api/maquinas/parear", "POST"),
                                ("/api/maquinas/remover", "POST")):
            with self.subTest(rota=caminho):
                r = self.pedir(caminho, metodo, {} if metodo == "POST" else None)
                self.assertEqual(r.status, 401, caminho)

    def test_o_dono_gera_um_codigo_de_seis_digitos(self):
        cookies = self.com_sessao()
        r = self.pedir("/api/maquinas/parear", "POST", {},
                       cookies=cookies, cabecalhos=self._csrf(cookies))
        self.assertEqual(r.status, 200, r.corpo)
        self.assertRegex(r.json["codigo"], r"^\d{6}$")
        self.assertEqual(r.json["minutos"], 10)

    def test_o_codigo_do_dono_pareia_de_verdade(self):
        cookies = self.com_sessao()
        r = self.pedir("/api/maquinas/parear", "POST", {},
                       cookies=cookies, cabecalhos=self._csrf(cookies))
        r2 = self.pedir("/agente/parear", "POST", {"codigo": r.json["codigo"],
                                                   "maquina": "ponta-a-ponta"})
        self.assertEqual(r2.status, 200, r2.corpo)
        self.assertEqual(banco.maquina_por_token(r2.json["token"])["usuario_id"],
                         self.uid)

    def test_o_vizinho_nao_remove_a_maquina_do_dono(self):
        token = self.parear()
        maq = banco.maquina_por_token(token)
        cookies = self.com_sessao(self.outro)
        r = self.pedir("/api/maquinas/remover", "POST", {"id": maq["id"]},
                       cookies=cookies, cabecalhos=self._csrf(cookies))
        self.assertIn(r.status, (403, 404), r.corpo)
        self.assertIsNotNone(banco.maquina_por_token(token),
                             "o vizinho revogou a maquina do dono (IDOR)")

    def _csrf(self, cookies):
        s = banco.sessao_valida(cookies["sessao"])
        return {"Origin": "http://127.0.0.1:%d" % self.porta,
                "X-Token": servir.Hub._csrf_da_sessao(s)}


    # ------------------------------------------------- duas contas, um servidor
    def _relatar(self, token, projetos, infra=None):
        return self.pedir("/agente/relatorio", "POST",
                          {"projetos": projetos, "infra": infra},
                          cabecalhos={"Authorization": "Token %s" % token})

    def _projetos_vistos(self, uid):
        r = self.pedir("/api/dados", cookies=self.com_sessao(uid))
        self.assertEqual(r.status, 200, r.corpo)
        return {p["nome"]: p for p in r.json["projetos"]}

    def test_o_relatorio_de_uma_conta_nao_toca_o_painel_da_outra(self):
        """O BLOQUEANTE da revisao, virado teste.

        `medida` tinha chave (projeto, camada) SEM dono, e `ler_tudo` devolvia a
        tabela inteira. Duas contas com um projeto de mesmo nome — "site", "api",
        nada exotico — se sobrescreviam pelo ON CONFLICT, e o painel de uma
        mostrava o numero da outra. Com uma maquina pareada, isso deixou de
        exigir intervencao humana: passou a acontecer sozinho, a cada relatorio.

        Um alerta real virando zero e a unica coisa que este produto promete
        nunca fazer.
        """
        meu = self.parear(self.uid)
        dele = self.parear(self.outro)

        r = self._relatar(meu, [{"nome": "site", "alertas": 7, "de": "mim"}])
        self.assertEqual(r.status, 200, r.corpo)
        r = self._relatar(dele, [{"nome": "site", "alertas": 0, "de": "vizinho"}])
        self.assertEqual(r.status, 200, r.corpo)

        meus = self._projetos_vistos(self.uid)
        dele_ve = self._projetos_vistos(self.outro)
        self.assertEqual(meus["site"]["de"], "mim",
                         "o relatorio do vizinho sobrescreveu o meu projeto")
        self.assertEqual(meus["site"]["alertas"], 7,
                         "meu alerta virou o numero do vizinho")
        self.assertEqual(dele_ve["site"]["de"], "vizinho")

    def test_uma_conta_nao_enxerga_o_projeto_da_outra(self):
        """A outra metade do mesmo furo: alem de sobrescrever, VAZAVA.

        `/api/dados` devolvia a `medida` inteira para qualquer sessao, com
        `usuario_id` filtrando so o que estava silenciado e arquivado.
        """
        meu = self.parear(self.uid)
        dele = self.parear(self.outro)
        self._relatar(meu, [{"nome": "so-meu", "alertas": 1}])
        self._relatar(dele, [{"nome": "so-dele", "alertas": 1}])

        self.assertNotIn("so-dele", self._projetos_vistos(self.uid),
                         "vi um projeto que nao e da minha conta")
        self.assertNotIn("so-meu", self._projetos_vistos(self.outro))

    def test_relatorio_nao_escreve_no_bloco_de_infra(self):
        """`_infra` e `_quota` sao linhas de sistema dentro da mesma tabela.

        Um projeto chamado `_infra` caia no `gravar(INFRA, ...)` e sequestrava o
        bloco de infraestrutura do painel — "Docker OK, nada quebrado" escrito
        por quem mandou o relatorio.
        """
        token = self.parear(self.uid)
        r = self._relatar(token,
                          [{"nome": banco.INFRA, "docker_mudo": False,
                            "containers": []},
                           {"nome": banco.QUOTA, "pct": 0},
                           {"nome": "de-verdade"}],
                          infra={"docker_mudo": True, "containers": []})
        self.assertEqual(r.status, 200, r.corpo)
        self.assertEqual(r.json["projetos"], 1, "nome reservado entrou")
        self.assertEqual(r.json["invalidos"], 2,
                         "os reservados sumiram sem contagem: %s" % r.corpo)
        d = self.pedir("/api/dados", cookies=self.com_sessao(self.uid)).json
        self.assertTrue(d["infra"]["docker_mudo"],
                        "o relatorio reescreveu o bloco de infra")

    def test_o_que_veio_malformado_e_contado(self):
        """`cortados` contava so o estouro do teto de 300. Entrada malformada
        sumia sem contagem nenhuma, e um bug de serializacao do lado do agente
        ficava invisivel dos dois lados — a mesma mentira por omissao que o
        proprio `cortados` existe para evitar."""
        token = self.parear(self.uid)
        r = self._relatar(token, ["nao sou dicionario", {"nome": ""},
                                  {"nome": "bom"}])
        self.assertEqual(r.status, 200, r.corpo)
        self.assertEqual((r.json["projetos"], r.json["invalidos"]), (1, 2),
                         r.corpo)


    # ------------------------------------------------ teto e classificacao
    def test_a_ingestao_tem_teto_por_maquina(self):
        """Sem teto, um token vazado enchia o disco do servidor num laco.

        O teto de 300 e POR RELATORIO; nada limitava quantos relatorios. O balde
        e por MAQUINA e nao por origem: a maquina legitima muda de IP, e o token
        e o que a identifica.
        """
        token = self.parear(self.uid)
        teto = servir.Hub.TETO_DE_RELATORIOS
        vistos = [self._relatar(token, [{"nome": "p%d" % i}]).status
                  for i in range(teto + 2)]
        self.assertEqual(vistos[:teto], [200] * teto, vistos)
        self.assertEqual(vistos[teto:], [429, 429],
                         "o relatorio %d passou: nao ha teto de ingestao."
                         % (teto + 1))

    def test_o_teto_de_uma_maquina_nao_tranca_a_outra(self):
        """Balde por maquina. Uma maquina barulhenta nao pode calar a do
        vizinho — seria negacao de servico de graca."""
        meu, dele = self.parear(self.uid), self.parear(self.outro)
        for i in range(servir.Hub.TETO_DE_RELATORIOS):
            self._relatar(meu, [{"nome": "p%d" % i}])
        self.assertEqual(self._relatar(meu, [{"nome": "x"}]).status, 429)
        self.assertEqual(self._relatar(dele, [{"nome": "x"}]).status, 200)

    def test_rota_mal_classificada_nao_executa(self):
        """NEGAR POR PADRAO em tempo de execucao, e nao so na CI.

        `test_rotas.py` cobra que toda rota declare `acesso`, mas ele e garantia
        de suite: uma rota com "Dado" — maiuscula trocada — caia por todos os
        `if` do despacho e EXECUTAVA sem autenticacao nenhuma.
        """
        servir.ROTAS["/teste/mal-classificada"] = servir.Rota(
            "GET", servir.Hub._pagina, "Dado")
        self.addCleanup(servir.ROTAS.pop, "/teste/mal-classificada", None)
        r = self.pedir("/teste/mal-classificada")
        self.assertEqual(r.status, 500, "rota fora das 4 classes executou")


    def test_projeto_gordo_demais_e_recusado(self):
        """O teto de 4 MiB e do CORPO, e o de 60 envios e da FREQUENCIA.

        Sem um teto por projeto, mil relatorios de um projeto de 4 MiB davam
        ~4 GiB numa conta — e `montar_estado` faz `json.loads` de tudo aquilo,
        num processo unico compartilhado por todos os inquilinos: o painel do
        dono legitimo derrubava o servidor. Achado da revisao da correcao.
        """
        token = self.parear(self.uid)
        gordo = {"nome": "gordo", "lixo": "x" * (banco.MAX_BYTES_POR_PROJETO + 1)}
        r = self._relatar(token, [gordo, {"nome": "magro"}])
        self.assertEqual(r.status, 200, r.corpo)
        self.assertEqual((r.json["projetos"], r.json["invalidos"]), (1, 1),
                         r.corpo)
        self.assertNotIn("gordo", self._projetos_vistos(self.uid))


class OEnderecoDoAlvo(unittest.TestCase):
    """`--alvo` sem https manda o token em claro no cabecalho."""

    def test_http_para_fora_e_recusado(self):
        for alvo in ("http://dervs.com.br", "http://192.168.1.9:4777"):
            with self.assertRaises(enviar.ErroDoAlvo, msg=alvo):
                enviar.conferir_alvo(alvo)

    def test_http_na_propria_maquina_continua_valendo(self):
        self.assertEqual(enviar.conferir_alvo("http://localhost:4777/"),
                         "http://localhost:4777")
        self.assertEqual(enviar.conferir_alvo("http://127.0.0.1:4777"),
                         "http://127.0.0.1:4777")

    def test_https_passa_e_o_resto_nao(self):
        self.assertEqual(enviar.conferir_alvo(" https://dervs.com.br/ "),
                         "https://dervs.com.br")
        for ruim in ("", "dervs.com.br", "ftp://dervs.com.br"):
            with self.assertRaises(enviar.ErroDoAlvo, msg=repr(ruim)):
                enviar.conferir_alvo(ruim)


    def test_endereco_com_query_ou_fragmento_e_recusado(self):
        """`--alvo http://x#y` passava e depois engolia o caminho na
        concatenacao, virando um 404 sem explicacao."""
        for ruim in ("https://dervs.com.br#x", "https://dervs.com.br?a=1"):
            with self.assertRaises(enviar.ErroDoAlvo, msg=ruim):
                enviar.conferir_alvo(ruim)

    def test_endereco_impossivel_vira_frase_e_nao_traceback(self):
        """`urlsplit` levanta ValueError cru em alguns enderecos, e `main` so
        captura `ErroDoAlvo`: o dono levava um traceback."""
        with self.assertRaises(enviar.ErroDoAlvo):
            enviar.conferir_alvo("http://[::1")

    def test_nao_segue_desvio(self):
        """O `urlopen` repassa o `Authorization` no redirecionamento, sem tirar
        na troca de host: um 302 do alvo entregava o token da maquina em texto
        para outro servidor. Quem controla o alvo hoje so tem o HASH dele."""
        with self.assertRaises(enviar.ErroDoAlvo) as e:
            enviar._SemRedirecionar().redirect_request(
                None, None, 302, "Found", {}, "http://outro-host/x")
        self.assertIn("outro-host", str(e.exception))


class OArquivoDoToken(unittest.TestCase):
    """Ele nasce fechado, e nao aberto com um chmod na linha seguinte."""

    @unittest.skipIf(os.name == "nt", "permissao POSIX nao existe no Windows")
    def test_nasce_com_600(self):
        with tempfile.TemporaryDirectory() as pasta:
            antes = enviar.arquivo_do_token
            enviar.arquivo_do_token = lambda: Path(pasta) / "sub" / "agente.json"
            self.addCleanup(setattr, enviar, "arquivo_do_token", antes)
            destino = enviar.guardar_token("https://x", "segredo", "maquina")
            self.assertEqual(oct(destino.stat().st_mode & 0o777), "0o600")


class OAgenteNaoEscutaPorta(unittest.TestCase):
    """O agente roda na máquina do dono, atrás do roteador dele. Abrir porta
    ali é a diferença entre "reporta para fora" e "aceita de fora"."""

    FONTE = Path("agente")

    def test_nenhum_arquivo_do_agente_abre_soquete_de_escuta(self):
        for arq in self.FONTE.glob("*.py"):
            texto = arq.read_text(encoding="utf-8")
            for proibido in ("HTTPServer", "socketserver", "bind(", "listen(",
                             "socket.socket"):
                self.assertNotIn(proibido, texto, "%s: %s" % (arq.name, proibido))

    def test_o_agente_guarda_o_token_fora_do_repositorio(self):
        """Token commitado é token vazado. O arquivo mora na pasta do usuário."""
        destino = enviar.arquivo_do_token()
        self.assertNotIn(str(Path.cwd()).lower(), str(destino).lower())

    def test_o_token_nao_vai_para_a_linha_de_comando(self):
        """Argumento de linha de comando aparece na lista de processos da
        máquina inteira. O código de pareamento é de uso único e vive dez
        minutos; o token, não — e por isso ele só entra por arquivo."""
        texto = (self.FONTE / "enviar.py").read_text(encoding="utf-8")
        self.assertNotIn('"--token"', texto)


class OAgenteTrabalha(unittest.TestCase):
    """O fio inteiro, com o painel dublado.

    Nada aqui fala com rede nem roda o `claude`: `_falar` e trocado por uma
    funcao que anota o que foi pedido e devolve o que o teste mandar. O que
    esta em jogo e o COMPORTAMENTO do agente — o que ele manda, quando manda, e
    o que ele faz com a resposta.
    """

    def setUp(self):
        from agente import enviar as e
        self.e = e
        self.pedidos = []
        self.respostas = {}
        self._falar_antigo = e._falar

        def falar_de_mentira(alvo, caminho, corpo, token=""):
            self.pedidos.append((caminho, corpo, token))
            resposta = self.respostas.get(caminho, {"ok": True})
            if callable(resposta):
                return resposta(corpo)
            return dict(resposta)

        e._falar = falar_de_mentira
        self.addCleanup(setattr, e, "_falar", self._falar_antigo)

        self._token_antigo = e.token_de
        e.token_de = lambda alvo: "token-de-mentira"
        self.addCleanup(setattr, e, "token_de", self._token_antigo)

    MEDICAO = {"projetos": [{"nome": "alvo", "caminho": "/tmp/alvo"}],
               "infra": {}, "avisos": []}

    def tarefa(self, **kw):
        base = {"id": "d:1", "projeto": "alvo", "regra": "env_drift",
                "trilho": "claude", "executor": "claude", "cor": "verde",
                "detalhe": "trocar x", "teto_usd": 3.0, "rodadas": 0}
        base.update(kw)
        return base

    def com_braco(self, funcao, disponivel=True):
        """Troca o braco por um duble que roda `funcao(tarefa, ao_progredir)`."""
        from agente import executor as ex

        class Duble(ex.Executor):
            nome = "claude"

            def disponivel(_self):
                return disponivel

            def rodar(_self, tarefa, teto_usd=None, ao_progredir=None,
                      gasto_usd=0.0, repinturas=None, maquina=None):
                return funcao(tarefa, ao_progredir)

        antigo = ex.EXECUTORES["claude"]
        ex.EXECUTORES["claude"] = Duble
        self.addCleanup(lambda: ex.EXECUTORES.__setitem__("claude", antigo))

    def caminhos(self):
        return [c for c, _corpo, _t in self.pedidos]

    # ------------------------------------------------------------ o fio

    def test_resposta_sem_tarefa_nao_dispara_nada(self):
        self.respostas["/agente/relatorio"] = {"ok": True, "tarefa": None}
        self.com_braco(lambda *_a: self.fail("o braco nao devia rodar"))
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO)
        self.assertEqual(self.caminhos(), ["/agente/relatorio"])

    def test_resposta_com_tarefa_dispara_o_braco_UMA_vez(self):
        self.respostas["/agente/relatorio"] = {"ok": True,
                                               "tarefa": self.tarefa()}
        vezes = []

        def rodar(tarefa, _ao_progredir):
            vezes.append(tarefa["id"])
            return {"tipo": "desfecho", "id": tarefa["id"], "estado": "ok",
                    "ramo": "hub/x-1", "resumo": "pronto", "diff": "",
                    "pr_url": "", "rodadas": 3, "custo_usd": 0.4, "erro": ""}

        self.com_braco(rodar)
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO)
        self.assertEqual(vezes, ["d:1"])

    def test_o_desfecho_sobe_sempre_inclusive_na_falha(self):
        """Sem o desfecho, a tarefa fica `rodando` no painel ate a varredura de
        15 minutos — e ate la a tela mente dizendo que ha trabalho acontecendo.
        """
        self.respostas["/agente/relatorio"] = {"ok": True,
                                               "tarefa": self.tarefa()}
        self.com_braco(lambda t, _p: {"tipo": "desfecho", "id": t["id"],
                                      "estado": "falha", "erro": "deu ruim"})
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO)
        self.assertIn("/agente/resultado", self.caminhos())
        ultimo = self.pedidos[-1][1]
        self.assertEqual(ultimo["estado"], "falha")

    def test_o_progresso_e_enviado_MAIS_DE_UMA_VEZ_numa_sessao_longa(self):
        """Duble de relogio: o tempo anda de dez em dez segundos, entao cada
        volta passa do intervalo de cinco. Sem isto, o teste dependeria de o
        computador ser lento."""
        self.respostas["/agente/relatorio"] = {"ok": True,
                                               "tarefa": self.tarefa()}
        batidas = iter([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
        relogio = lambda: next(batidas, 999)   # noqa: E731

        def rodar(t, ao_progredir):
            for i in range(4):
                ao_progredir({"linhas": ["linha %d" % i], "frase": "indo",
                              "rodadas": i, "custo_usd": 0.1,
                              "total_de_linhas": i + 1})
            return {"tipo": "desfecho", "id": t["id"], "estado": "ok"}

        self.com_braco(rodar)
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO,
                              relogio=relogio)
        progressos = [c for c, corpo, _t in self.pedidos
                      if corpo.get("tipo") == "progresso"]
        self.assertGreater(len(progressos), 1,
                           "o progresso foi enviado uma vez so")

    def test_o_progresso_respeita_o_intervalo_e_nao_inunda_o_painel(self):
        """O balcao do painel tem teto. Falar mais que o combinado leva 429, e
        a tela congela sem explicacao."""
        self.respostas["/agente/relatorio"] = {"ok": True,
                                               "tarefa": self.tarefa()}
        parado = lambda: 0.0                   # noqa: E731 — o tempo nao anda

        def rodar(t, ao_progredir):
            for _ in range(20):
                ao_progredir({"linhas": ["x"], "frase": "", "rodadas": 1,
                              "custo_usd": 0.0, "total_de_linhas": 1})
            return {"tipo": "desfecho", "id": t["id"], "estado": "ok"}

        self.com_braco(rodar)
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO,
                              relogio=parado)
        progressos = [c for c, corpo, _t in self.pedidos
                      if corpo.get("tipo") == "progresso"]
        self.assertLessEqual(len(progressos), 1)

    def test_a_resposta_pare_chega_ao_braco(self):
        """O botao Parar nao tem fio proprio: ele volta na resposta do pedido
        que o agente ja ia fazer."""
        self.respostas["/agente/relatorio"] = {"ok": True,
                                               "tarefa": self.tarefa()}
        self.respostas["/agente/resultado"] = {"ok": True, "pare": True}
        vistos = []

        def rodar(t, ao_progredir):
            vistos.append(ao_progredir({"linhas": ["x"], "frase": "",
                                        "rodadas": 1, "custo_usd": 0.0,
                                        "total_de_linhas": 1}))
            return {"tipo": "desfecho", "id": t["id"], "estado": "falha"}

        self.com_braco(rodar)
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO,
                              relogio=iter(range(0, 10000, 100)).__next__)
        self.assertEqual(vistos, [True])

    def test_falha_de_rede_no_progresso_NAO_interrompe_a_sessao(self):
        """Devolver "pare" por causa de um cabo de rede faria uma falha de rede
        parecer, para o dono, um clique dele no botao Parar."""
        self.respostas["/agente/relatorio"] = {"ok": True,
                                               "tarefa": self.tarefa()}

        def explode(_corpo):
            raise self.e.ErroDoAlvo("a rede caiu")

        self.respostas["/agente/resultado"] = explode
        vistos = []

        def rodar(t, ao_progredir):
            vistos.append(ao_progredir({"linhas": ["x"], "frase": "",
                                        "rodadas": 1, "custo_usd": 0.0,
                                        "total_de_linhas": 1}))
            return {"tipo": "desfecho", "id": t["id"], "estado": "ok"}

        self.com_braco(rodar)
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO,
                              relogio=iter(range(0, 10000, 100)).__next__)
        self.assertEqual(vistos, [False])

    def test_uma_tarefa_que_explode_nao_mata_o_laco_do_agente(self):
        """Parar de medir por causa de uma sessao ruim deixaria o painel cego
        exatamente quando ha problema."""
        self.respostas["/agente/relatorio"] = {"ok": True,
                                               "tarefa": self.tarefa()}

        def rodar(_t, _p):
            raise RuntimeError("o braco quebrou")

        self.com_braco(rodar)
        fora = self.e.enviar_uma_vez("https://dervs.com.br",
                                     medicao=self.MEDICAO)
        self.assertEqual(fora["desfecho"]["estado"], "falha")
        self.assertIn("RuntimeError", fora["desfecho"]["erro"])

    def test_braco_que_esta_maquina_nao_tem_vira_desfecho_de_falha(self):
        self.respostas["/agente/relatorio"] = {
            "ok": True, "tarefa": self.tarefa(executor="codex")}
        fora = self.e.enviar_uma_vez("https://dervs.com.br",
                                     medicao=self.MEDICAO)
        self.assertEqual(fora["desfecho"]["estado"], "falha")
        self.assertIn("codex", fora["desfecho"]["erro"])
        self.assertIn("/agente/resultado", self.caminhos())

    def test_trabalhar_desligado_so_mede(self):
        """A maquina que o dono ainda nao autorizou continua reportando — e nao
        executa nada."""
        self.respostas["/agente/relatorio"] = {"ok": True,
                                               "tarefa": self.tarefa()}
        self.com_braco(lambda *_a: self.fail("o braco nao devia rodar"))
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO,
                              trabalhar=False)
        self.assertEqual(self.caminhos(), ["/agente/relatorio"])

    def test_o_caminho_do_projeto_sai_da_MEDICAO_e_nao_da_rede(self):
        """Um caminho vindo do painel seria a rede dizendo em que pasta desta
        maquina mexer."""
        self.assertEqual(
            self.e.caminho_do_projeto("alvo", self.MEDICAO), "/tmp/alvo")
        self.assertEqual(
            self.e.caminho_do_projeto("nao-existe", self.MEDICAO), "")

    def test_o_painel_nao_consegue_apontar_para_uma_pasta_qualquer(self):
        """Mesmo que a tarefa venha com `caminho`, quem manda e a medicao."""
        self.respostas["/agente/relatorio"] = {
            "ok": True,
            "tarefa": self.tarefa(caminho="C:/Windows/System32")}
        vistos = []
        self.com_braco(lambda t, _p: vistos.append(t.get("caminho"))
                       or {"tipo": "desfecho", "id": t["id"], "estado": "ok"})
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO)
        self.assertEqual(vistos, ["/tmp/alvo"])

    def test_o_token_continua_indo_so_em_cabecalho(self):
        self.respostas["/agente/relatorio"] = {"ok": True,
                                               "tarefa": self.tarefa()}
        self.com_braco(lambda t, _p: {"tipo": "desfecho", "id": t["id"],
                                      "estado": "ok"})
        self.e.enviar_uma_vez("https://dervs.com.br", medicao=self.MEDICAO)
        for caminho, corpo, token in self.pedidos:
            self.assertEqual(token, "token-de-mentira", caminho)
            self.assertNotIn("token", corpo, caminho)

    def test_a_latencia_do_parar_esta_declarada_e_e_de_cinco_segundos(self):
        """O botao NAO e instantaneo, e nenhuma etapa o torna. O numero mora em
        `tarefas.py`, num lugar so, e a tela le dali."""
        import tarefas as t
        self.assertEqual(t.SEGUNDOS_ENTRE_PROGRESSOS, 5)
        import inspect
        self.assertIn("SEGUNDOS_ENTRE_PROGRESSOS",
                      inspect.getsource(self.e.fazer_a_tarefa))


class OCodigoRecusadoDizOsQuatroMotivos(unittest.TestCase):
    """Quem tem DOIS DERVS erra o quarto motivo, e a frase nao o citava.

    Em 29/08/2026 o dono pareou no servidor e tentou o MESMO numero no DERVS
    da propria maquina. Os dois tem banco separado, entao o segundo respondeu
    401 — comportamento certo. Mas a frase listava tres motivos ("digitado
    errado, venceu, ja foi usado") e nenhum deles era o dele; ele leu como
    defeito do produto. Uma mensagem de erro que nao contem a causa real
    manda a pessoa depurar a hipotese errada.
    """

    def test_a_frase_do_401_cita_o_outro_dervs(self):
        frase = enviar._explicar("/agente/parear", 401)
        self.assertIn("outro DERVS", frase)

    def test_a_frase_do_401_continua_com_os_tres_motivos_antigos(self):
        """O motivo novo ENTRA; nenhum sai. Trocar uma causa por outra so
        move o problema de lugar."""
        frase = enviar._explicar("/agente/parear", 401).lower()
        for pedaco in ("digitado errado", "dez minutos", "outra maquina"):
            self.assertIn(pedaco, frase)

    def test_toda_frase_impressa_pelo_agente_e_ascii(self):
        """O console do Windows troca o que nao e ASCII por `?`.

        A frase do agente nao aparece numa pagina: ela e IMPRESSA no PowerShell
        do dono. Um travessao no meio dela vira `?` e a frase fica com cara de
        corrompida justamente no momento em que a pessoa ja esta perdida.

        O teste cobra as frases DEVOLVIDAS, e nao o arquivo: comentario e
        docstring podem ter travessao a vontade, porque ninguem os imprime.
        Medir o arquivo inteiro reprovaria onze comentarios legitimos e a
        proxima pessoa desligaria o teste.

        Achado em 29/08/2026: a frase do 429 ja saia com `?` desde que foi
        escrita, e ninguem tinha visto porque so aparece com o alvo recusando.
        """
        frases = [enviar._explicar(caminho, codigo)
                  for caminho in ("/agente/parear", "/agente/relatorio")
                  for codigo in (401, 403, 404, 429, 500)]
        for ruim in ("", "dervs.com.br", "ftp://x", "http://dervs.com.br",
                     "https://x#y", "http://[::1"):
            try:
                enviar.conferir_alvo(ruim)
            except enviar.ErroDoAlvo as e:
                frases.append(str(e))

        self.assertGreaterEqual(len(frases), 15, "o teste parou de coletar "
                                "frases; sem isto ele aprova qualquer coisa")
        for frase in frases:
            fora = sorted({c for c in frase if ord(c) > 127})
            self.assertEqual(fora, [], "caractere que o console do Windows nao "
                             "mostra (%r) na frase: %r" % (fora, frase))

    def test_o_401_fora_do_pareamento_nao_fala_de_codigo(self):
        """Guarda: se o `if` do caminho quebrar, esta frase vaza para o 401 de
        maquina revogada, e o dono vai gerar codigo para um problema que codigo
        nenhum resolve."""
        frase = enviar._explicar("/agente/relatorio", 401)
        self.assertNotIn("outro DERVS", frase)
        self.assertIn("nao esta mais autorizada", frase)


# O duble da sessao de auditoria: o MESMO molde de `test_executor.py`, um
# script Python que cospe `stream-json` linha a linha. O binario `claude` nao
# e chamado em lugar nenhum deste arquivo — a CI nao tem login, e cada corrida
# gastaria a assinatura do dono.
SESSAO_DE_AUDITORIA_DE_MENTIRA = textwrap.dedent('''
    import json, sys, time
    def diga(o):
        sys.stdout.write(json.dumps(o) + "\\n")
        sys.stdout.flush()
    diga({"type": "system", "subtype": "init"})
    time.sleep(0.1)
    diga({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Read", "input": {"file_path": "x.py"}}]}})
    time.sleep(0.1)
    achados = {"achados": [
        {"arquivo": "x.py", "linha": 1, "categoria": "seguranca",
         "gravidade": "alta",
         "frase": "x comeca fixado em 1, e deveria vir de configuracao.",
         "o_que_fazer": "Ler o valor de uma variavel de ambiente ou arquivo."},
        {"arquivo": "x.py", "linha": 2, "categoria": "teste",
         "gravidade": "baixa",
         "frase": "nao ha teste nenhum cobrindo o valor de x neste arquivo.",
         "o_que_fazer": "Escrever um caso que reprove quando x mudar sozinho."}
    ]}
    diga({"type": "result", "subtype": "success", "is_error": False,
          "terminal_reason": "completed", "num_turns": 2,
          "total_cost_usd": 0.42, "result": json.dumps(achados)})
''').strip()


class OFioDaAuditoriaVaiAteOBanco(unittest.TestCase):
    """**O teste que faltava.** Uma corrida de auditoria inteira, do script de
    mentira ate a linha gravada no banco — sem duble no meio.

    Cada metade disto ja tinha teste, e a suite ficava verde com o produto
    quebrado: `test_executor.py` provava que o braco devolve o JSON, e
    `test_servir.py` provava que `_resultado` grava quando recebe `achados`.
    Faltava ligar as pontas — e nada, em lugar nenhum do repositorio, produzia
    a chave `achados`. A auditoria disparava o binario, gastava o teto do dia,
    e o bloco de gravacao era INALCANCAVEL.

    Por isso este caso sobe um servidor de verdade, roda o braco de verdade
    sobre um repositorio git de verdade, e pergunta ao BANCO — nunca ao
    desfecho que o braco devolveu.
    """

    @classmethod
    def setUpClass(cls):
        cls.tem_git = bool(shutil.which("git"))
        cls.dir = tempfile.TemporaryDirectory()
        cls._banco_antigo = banco.BANCO
        banco.BANCO = Path(cls.dir.name) / "hub.db"
        con = banco.conectar()
        cls.uid = banco.criar_usuario("dono@teste.local", con=con)
        con.close()
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servir.Hub)
        cls.porta = cls.srv.server_address[1]
        cls._porta_antiga, servir.PORTA = servir.PORTA, cls.porta
        cls._hosts_antigos = servir.HOSTS_OK
        servir.HOSTS_OK = {"127.0.0.1:%d" % cls.porta}
        cls.linha = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.linha.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        servir.PORTA = cls._porta_antiga
        servir.HOSTS_OK = cls._hosts_antigos
        banco.BANCO = cls._banco_antigo
        cls.dir.cleanup()

    def setUp(self):
        if not self.tem_git:
            self.skipTest("sem git nesta maquina")
        cortina.zerar_tentativas()
        self.addCleanup(cortina.zerar_tentativas)
        self.pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.projeto = Path(self.pasta) / "alvo"
        self.projeto.mkdir()
        for argv in (["git", "init", "-q", "-b", "main"],
                     ["git", "config", "user.email", "teste@teste.local"],
                     ["git", "config", "user.name", "Teste"]):
            subprocess.run(argv, cwd=str(self.projeto), capture_output=True)
        (self.projeto / "x.py").write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(self.projeto),
                       capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", "inicio"],
                       cwd=str(self.projeto), capture_output=True)

        execucao._auditoria = execucao._zerada_auditoria()
        execucao._proc = None
        self.addCleanup(setattr, execucao, "_proc", None)
        script = Path(self.pasta) / "sessao_de_auditoria_de_mentira.py"
        script.write_text(SESSAO_DE_AUDITORIA_DE_MENTIRA, encoding="utf-8")
        original = execucao.montar_comando_de_auditoria
        execucao.montar_comando_de_auditoria = lambda *a, **k: [
            sys.executable, str(script)]
        self.addCleanup(setattr, execucao, "montar_comando_de_auditoria",
                        original)

    def token_de_maquina(self):
        codigo = banco.novo_codigo(6)
        banco.abrir_pareamento(self.uid, codigo, banco.prazo(600))
        dados = json.dumps({"codigo": codigo,
                            "maquina": "maquina-de-teste"}).encode("utf-8")
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        try:
            c.request("POST", "/agente/parear", body=dados, headers={
                "Host": "127.0.0.1:%d" % self.porta,
                "Content-Type": "application/json",
                "Content-Length": str(len(dados))})
            r = c.getresponse()
            corpo = json.loads((r.read() or b"").decode("utf-8"))
        finally:
            c.close()
        return corpo["token"]

    def subir(self, desfecho, token):
        dados = json.dumps(desfecho).encode("utf-8")
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=30)
        try:
            c.request("POST", "/agente/resultado", body=dados, headers={
                "Host": "127.0.0.1:%d" % self.porta,
                "Authorization": "Token " + token,
                "Content-Type": "application/json",
                "Content-Length": str(len(dados))})
            r = c.getresponse()
            return r.status, (r.read() or b"").decode("utf-8", "replace")
        finally:
            c.close()

    def test_a_auditoria_ponta_a_ponta_TERMINA_COM_ACHADOS_NO_BANCO(self):
        from agente import executor as ex

        token = self.token_de_maquina()
        maquina = banco.maquina_por_token(token)
        tarefa_id = "%s:alvo" % auditoria.REGRA_DE_VENCIMENTO
        banco.enfileirar([{"id": tarefa_id, "projeto": "alvo",
                           "regra": auditoria.REGRA_DE_VENCIMENTO,
                           "gravidade": "baixa", "trilho": "claude",
                           "executor": auditoria.EXECUTOR}])
        self.assertTrue(banco.entregar_tarefa(tarefa_id, maquina["id"]))

        desfecho = ex.ExecutorAuditor().rodar(
            {"id": tarefa_id, "projeto": "alvo",
             "regra": auditoria.REGRA_DE_VENCIMENTO, "trilho": "claude",
             "executor": auditoria.EXECUTOR, "detalhe": "",
             "caminho": str(self.projeto), "teto_usd": 1.5, "tentativas": 0},
            repinturas={auditoria.REGRA_DE_VENCIMENTO: "verde"})
        self.assertEqual(desfecho["estado"], "ok", desfecho)

        status, corpo = self.subir(desfecho, token)
        self.assertEqual(status, 200, corpo)

        corrida = banco.auditoria_do_projeto(self.uid, "alvo")
        self.assertIsNotNone(corrida, "a corrida de auditoria nao foi gravada: "
                             "o desfecho subiu sem a chave `achados` e o bloco "
                             "de gravacao de `_resultado` ficou inalcancavel.")
        self.assertEqual(corrida["estado"], "ok", corrida["motivo"])
        self.assertEqual(corrida["achados_n"], 2)
        gravados = banco.achados_do_projeto(self.uid, "alvo")
        self.assertEqual(len(gravados), 2, gravados)
        self.assertEqual(sorted(a["categoria"] for a in gravados),
                         ["seguranca", "teste"])

    def test_uma_auditoria_grande_nao_e_destruida_pelo_corte_do_resumo(self):
        """O corte de 4.000 caracteres do `resumo` (`servir.py`) destruiria o
        JSON de uma auditoria de verdade — 60 achados passam disso com folga.

        Por isso os achados sobem em campo PROPRIO, com teto proprio. Este
        caso monta 60 achados validos (o maximo do esquema), sobe pelo fio e
        exige os 60 gravados.
        """
        token = self.token_de_maquina()
        maquina = banco.maquina_por_token(token)
        tarefa_id = "%s:grande" % auditoria.REGRA_DE_VENCIMENTO
        banco.enfileirar([{"id": tarefa_id, "projeto": "grande",
                           "regra": auditoria.REGRA_DE_VENCIMENTO,
                           "gravidade": "baixa", "trilho": "claude",
                           "executor": auditoria.EXECUTOR}])
        self.assertTrue(banco.entregar_tarefa(tarefa_id, maquina["id"]))

        crus = json.dumps({"achados": [
            {"arquivo": "modulo_%02d.py" % n, "linha": n + 1,
             "categoria": "bug", "gravidade": "media",
             "frase": "o achado numero %02d descreve um defeito de verdade." % n,
             "o_que_fazer": "Conserte o defeito %02d do jeito descrito acima." % n}
            for n in range(auditoria.MAX_ACHADOS)]})
        self.assertGreater(len(crus), 4000,
                           "o corpo do teste encolheu: ele precisa passar do "
                           "corte de 4.000 do `resumo` para provar algo")

        status, corpo = self.subir({
            "tipo": "desfecho", "id": tarefa_id, "estado": "ok", "ramo": "",
            "diff": "", "pr_url": "", "resumo": "", "achados": crus,
            "rodadas": 9, "custo_usd": 1.5, "erro": ""}, token)
        self.assertEqual(status, 200, corpo)
        corrida = banco.auditoria_do_projeto(self.uid, "grande")
        self.assertEqual(corrida["estado"], "ok", corrida["motivo"])
        self.assertEqual(corrida["achados_n"], auditoria.MAX_ACHADOS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
