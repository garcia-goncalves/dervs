# -*- coding: utf-8 -*-
"""Testes do servidor do HUB.

Este arquivo era, até a etapa 7 do DERVS, quase todo sobre o proxy do grafo de
código: 40 testes de tradução de caminho, reescrita de corpo, compressão e
cabeçalho. O proxy foi removido junto com as rotas que executavam comando, e
os testes dele saíram no mesmo commit — teste de código que não existe mais é
peso morto que dá a falsa impressão de cobertura.

O que ficou aqui são os dois amarres que o servidor ainda precisa:

  - importar `servir.py` não pode quebrar por causa da linha de comando;
  - a tela não pode chamar rota que o servidor não tem.

A pergunta "este servidor executa comando?" mora em `test_rotas.py`, e lá ela é
respondida pela estrutura em memória, não por este arquivo.

    python test_servir.py
"""
from __future__ import annotations

import http.client
import json
import os
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco    # noqa: E402
import cortina  # noqa: E402
import servir   # noqa: E402


class PortaDaLinhaDeComando(unittest.TestCase):
    """Importar servir.py nao pode quebrar so porque ha argumento na linha.

    `python -m pytest test_servir.py` explodia com ValueError antes de rodar um
    unico teste: o argumento era o nome do arquivo.
    """

    def test_argumento_que_nao_e_numero_e_ignorado(self):
        self.assertEqual(servir.porta_de(["servir.py"], 4777), 4777)
        self.assertEqual(servir.porta_de(["servir.py", "-v"], 4777), 4777)
        self.assertEqual(servir.porta_de(["x", "test_servir.py"], 4777), 4777)

    def test_numero_valido_vale(self):
        self.assertEqual(servir.porta_de(["servir.py", "4780"], 4777), 4780)

    def test_numero_fora_da_faixa_e_ignorado(self):
        self.assertEqual(servir.porta_de(["servir.py", "0"], 4777), 4777)
        self.assertEqual(servir.porta_de(["servir.py", "99999"], 4777), 4777)


class ATelaSoChamaRotaQueExiste(unittest.TestCase):
    """O sucessor de `PaletaNaoInventaComando`, e pelo mesmo motivo.

    Aquele teste lia os `comando: "..."` do index.html e exigia que cada um
    existisse na lista branca do servidor. A lista branca acabou junto com
    `/api/acao`; o risco que ele cobria, nao. Uma rota escrita com erro de
    digitacao no `fetch()` falha calada na cara do dono: o botao roda, o
    servidor responde 404, e a tela nao mostra nada.

    Agora o amarre e direto — os caminhos que o index.html busca contra
    `servir.ROTAS`.
    """

    def _rotas_do_html(self):
        html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        # Pega o primeiro argumento de fetch(), que e sempre um literal aqui.
        # Query e concatenacao ficam de fora: a tabela casa so o caminho.
        cruas = re.findall(r'fetch\(\s*"(/[^"?]*)', html)
        return {c for c in cruas}

    def test_todo_fetch_da_tela_tem_rota_no_servidor(self):
        for caminho in self._rotas_do_html():
            self.assertIn(caminho, servir.ROTAS,
                          "a tela busca %r, que o servidor nao serve" % caminho)

    def test_a_extracao_realmente_acha_alguma_coisa(self):
        """Se a extracao parar de achar nada, o teste acima passa vazio e mente."""
        achadas = self._rotas_do_html()
        self.assertTrue(achadas)
        self.assertIn("/api/dados", achadas)

    def test_a_tela_nao_chama_mais_as_rotas_amputadas(self):
        html = (Path(__file__).parent / "index.html").read_text(encoding="utf-8")
        # `fetch(` e `src=` sao os dois jeitos pelos quais a tela alcancava o
        # que foi removido — o segundo era o quadro do grafo.
        for morta in ("/api/acao", "/api/execucao", "/api/grafo", "/grafo/"):
            with self.subTest(rota=morta):
                self.assertNotIn('fetch("%s' % morta, html)
                self.assertNotIn('src = "%s"' % morta, html)


class ServidorDeVerdade(unittest.TestCase):
    """Sobe o servidor de verdade numa porta livre e CONVERSA com ele.

    Os outros testes deste arquivo leem estrutura em memoria, e isso e bom para
    o que eles cobram. Mas "a tela abriu" nao e prova de que o botao dispara --
    ja afirmei isso uma vez tendo visto so a faixa aparecer. Aqui o pedido sai
    pelo soquete e a resposta vem pelo soquete.
    """

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.caminho = Path(cls.dir.name) / "hub.db"
        cls._banco_antigo = banco.BANCO
        banco.BANCO = cls.caminho

        con = banco.conectar()
        cls.combinacao = cortina.garantir_combinacao(con) or "000000"
        cls.uid = banco.criar_usuario("dono@teste.local", con=con)
        banco.ligar_github(cls.uid, "4242", con=con)
        con.close()

        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servir.Hub)
        cls.porta = cls.srv.server_address[1]
        # O servidor confere Host e Origin contra a porta com que o modulo foi
        # importado. Como o teste sobe noutra porta, os tres conjuntos mudam
        # junto -- e sao restaurados no fim para nao contaminar outro teste.
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
    def pedir(self, caminho, metodo="GET", corpo=None, cookies=None,
              com_origem=True, cabecalhos=None, corpo_cru=None):
        """Fala HTTP na mao, de proposito.

        `urllib` segue redirecionamento em silencio e junta cabecalhos
        repetidos num so — e sao exatamente o 302 e os varios `Set-Cookie` que
        este teste precisa ver.
        """
        dados = corpo_cru
        if dados is None and corpo is not None:
            dados = json.dumps(corpo).encode("utf-8")
        cab = {"Host": "127.0.0.1:%d" % self.porta}
        if dados is not None:
            cab["Content-Type"] = "application/json"
            cab["Content-Length"] = str(len(dados))
        if com_origem:
            cab["Origin"] = "http://127.0.0.1:%d" % self.porta
        if cookies:
            cab["Cookie"] = "; ".join("%s=%s" % kv for kv in cookies.items())
        cab.update(cabecalhos or {})
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        try:
            c.request(metodo, caminho, body=dados, headers=cab)
            r = c.getresponse()
            lido = (r.read() or b"").decode("utf-8", "replace")
            postos = r.headers.get_all("Set-Cookie") or []
            return _Resposta(r.status, lido, r.headers, postos)
        finally:
            c.close()

    def abrir_cortina(self):
        r = self.pedir("/entrada", "POST", {"combinacao": self.combinacao})
        self.assertIn("cortina", r.cookies)
        return {"cortina": r.cookies["cortina"]}

    def com_sessao(self):
        """Uma sessao completa, aberta pela porta dos fundos do banco.

        O caminho do GitHub e testado em test_autenticacao.py com duble de rede;
        aqui interessa o que a SESSAO libera, nao como ela nasceu.
        """
        cookie = banco.novo_token()
        con = banco.conectar()
        try:
            banco.abrir_sessao(self.uid, cookie, banco.prazo(3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
        finally:
            con.close()
        return {"sessao": final}

    # ---------------------------------------------------------------- a capa
    def test_a_capa_nao_entrega_o_formulario_de_login(self):
        corpo = self.pedir("/").corpo.lower()
        for proibido in ("oauth", "github", "client_id", "entrar com",
                         "/entrar/", "dervs", "__porta_aberta__"):
            self.assertNotIn(proibido, corpo, proibido)

    def test_a_capa_nao_diz_o_que_este_sistema_e(self):
        corpo = self.pedir("/").corpo.lower()
        for proibido in ("painel", "projeto", "pendencia", "hub do dev"):
            self.assertNotIn(proibido, corpo, proibido)

    def test_a_capa_pede_para_nao_ser_indexada(self):
        r = self.pedir("/")
        self.assertIn("noindex", r.cabecalhos.get("X-Robots-Tag", ""))

    # ------------------------------------------------------------- a cortina
    def test_errar_e_acertar_devolvem_a_mesma_resposta(self):
        errado = self.pedir("/entrada", "POST", {"combinacao": "111111"})
        cortina.zerar_tentativas()
        certo = self.pedir("/entrada", "POST", {"combinacao": self.combinacao})
        self.assertEqual(errado.status, certo.status)
        self.assertEqual(errado.corpo, certo.corpo)
        # A UNICA diferenca observavel e o cookie.
        self.assertNotIn("cortina", errado.cookies)
        self.assertIn("cortina", certo.cookies)

    def test_a_combinacao_certa_revela_o_botao(self):
        antes = self.pedir("/").corpo.lower()
        self.assertNotIn("/entrar/github", antes)
        depois = self.pedir("/", cookies=self.abrir_cortina()).corpo.lower()
        self.assertIn("/entrar/github", depois)

    def test_o_selo_e_HttpOnly_e_SameSite(self):
        r = self.pedir("/entrada", "POST", {"combinacao": self.combinacao})
        cru = " ".join(r.postos).lower()
        self.assertIn("httponly", cru)
        self.assertIn("samesite=lax", cru)

    def test_selo_forjado_nao_abre_a_porta(self):
        forjado = {"cortina": "99999999999.%s" % ("a" * 64)}
        self.assertNotIn("/entrar/github", self.pedir("/", cookies=forjado).corpo)
        self.assertEqual(self.pedir("/entrar/github", cookies=forjado).status, 404)

    def test_a_sexta_tentativa_responde_igual_e_nao_confere_nada(self):
        for _ in range(cortina.TETO):
            self.pedir("/entrada", "POST", {"combinacao": "111111"})
        bloqueado = self.pedir("/entrada", "POST",
                               {"combinacao": self.combinacao})
        self.assertEqual(bloqueado.status, 204)
        self.assertNotIn("cortina", bloqueado.cookies)

    def test_a_cortina_recusa_pedido_de_outra_origem(self):
        r = self.pedir("/entrada", "POST", {"combinacao": self.combinacao},
                       com_origem=False)
        self.assertEqual(r.status, 204)
        self.assertNotIn("cortina", r.cookies)

    def test_corpo_torto_na_entrada_nao_derruba_nada(self):
        for ruim in (b"[]", b'"x"', b"{", b"", b"null", b"9" * 5000):
            with self.subTest(corpo=ruim[:12]):
                cortina.zerar_tentativas()
                r = self.pedir("/entrada", "POST", corpo_cru=ruim)
                self.assertEqual(r.status, 204)
                self.assertEqual(r.cookies, {})

    # -------------------------------------------------------- rota de dado
    def test_toda_rota_de_dado_nega_sem_sessao(self):
        for caminho, rota in servir.ROTAS.items():
            if rota.acesso != "dado":
                continue
            with self.subTest(rota=caminho):
                r = self.pedir(caminho, rota.metodo,
                               {} if rota.metodo == "POST" else None)
                self.assertIn(r.status, (401, 302), caminho)
                # E o corpo nao pode trazer nome de projeto nenhum.
                for vazamento in ("projeto", "dervs", "pendencia"):
                    self.assertNotIn(vazamento, r.corpo.lower(), caminho)

    def test_o_selo_da_cortina_nao_vale_como_sessao(self):
        """A cortina nao e a fechadura, e isto e o teste que prova a frase."""
        r = self.pedir("/api/dados", cookies=self.abrir_cortina())
        self.assertEqual(r.status, 401)

    def test_com_sessao_a_rota_de_dado_responde(self):
        r = self.pedir("/api/dados", cookies=self.com_sessao())
        self.assertEqual(r.status, 200)
        self.assertIn("projetos", json.loads(r.corpo))

    def test_com_sessao_a_pagina_e_o_painel(self):
        corpo = self.pedir("/", cookies=self.com_sessao()).corpo
        self.assertNotIn("Sala de Leitura", corpo)
        self.assertNotIn("__TOKEN__", corpo)

    def test_sessao_encerrada_para_de_valer(self):
        cookies = self.com_sessao()
        self.assertEqual(self.pedir("/api/dados", cookies=cookies).status, 200)
        self.pedir("/sair", "POST", cookies=cookies)
        self.assertEqual(self.pedir("/api/dados", cookies=cookies).status, 401)

    def test_cookie_de_sessao_inventado_nao_entra(self):
        for ruim in ("x", "a" * 200, "../../etc", ""):
            with self.subTest(cookie=ruim):
                self.assertEqual(
                    self.pedir("/api/dados", cookies={"sessao": ruim}).status, 401)

    # ------------------------------------------------------------ anti-CSRF
    def test_silenciar_exige_o_anti_csrf_daquela_sessao(self):
        cookies = self.com_sessao()
        sem = self.pedir("/api/silenciar", "POST", {"id": "x:y"}, cookies=cookies)
        self.assertEqual(sem.status, 403)
        errado = self.pedir("/api/silenciar", "POST", {"id": "x:y"},
                            cookies=cookies, cabecalhos={"X-Token": "a" * 64})
        self.assertEqual(errado.status, 403)

    def test_o_anti_csrf_de_uma_sessao_nao_serve_na_outra(self):
        """Era um token global ate a etapa 9. Com multiusuario, um token so
        para o servidor inteiro seria a chave de todo mundo."""
        a, b = self.com_sessao(), self.com_sessao()
        token_de_a = self._token_da_pagina(a)
        ok = self.pedir("/api/silenciar", "POST", {"id": "r:p"}, cookies=a,
                        cabecalhos={"X-Token": token_de_a})
        self.assertEqual(ok.status, 200)
        cruzado = self.pedir("/api/silenciar", "POST", {"id": "r:p"}, cookies=b,
                             cabecalhos={"X-Token": token_de_a})
        self.assertEqual(cruzado.status, 403)

    def _token_da_pagina(self, cookies):
        corpo = self.pedir("/", cookies=cookies).corpo
        achado = re.search(r'"([0-9a-f]{64})"', corpo)
        self.assertIsNotNone(achado, "o anti-CSRF nao foi injetado na pagina")
        return achado.group(1)

    def test_o_token_global_nao_existe_mais(self):
        self.assertFalse(hasattr(servir, "TOKEN"),
                         "servir.TOKEN voltou: ele e anti-CSRF e nao pode virar"
                         " credencial de usuario")

    # -------------------------------------------------------------- segredo
    def test_nenhuma_resposta_traz_a_combinacao(self):
        for caminho, rota in servir.ROTAS.items():
            if rota.metodo != "GET":
                continue
            with self.subTest(rota=caminho):
                corpo = self.pedir(caminho, cookies=self.com_sessao()).corpo
                self.assertNotIn(self.combinacao, corpo)

    def test_a_rota_de_entrar_nao_existe_sem_aplicativo_registrado(self):
        """Falha FECHADA: melhor nao ter porta do que ter porta que nao tranca."""
        self.assertEqual(servir.GITHUB_ID, "")
        self.assertEqual(
            self.pedir("/entrar/github", cookies=self.abrir_cortina()).status, 404)

    def test_nao_existe_rota_de_registro(self):
        self.assertNotIn("/api/registro", servir.ROTAS)
        self.assertEqual(self.pedir("/api/registro", "POST", {}).status, 404)


class _Resposta:
    def __init__(self, status, corpo, cabecalhos, postos):
        self.status = status
        self.corpo = corpo
        self.cabecalhos = cabecalhos
        self.postos = postos
        self.cookies = {}
        for cru in postos:
            nome, _, resto = cru.partition("=")
            valor = resto.split(";", 1)[0]
            # Max-Age=0 e um cookie sendo APAGADO, nao posto.
            if valor and "max-age=0" not in cru.lower():
                self.cookies[nome.strip()] = valor


if __name__ == "__main__":
    unittest.main(verbosity=0)
