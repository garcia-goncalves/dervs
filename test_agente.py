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
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco     # noqa: E402
import coletar   # noqa: E402
import cortina   # noqa: E402
import servir    # noqa: E402

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
