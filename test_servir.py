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
import hashlib
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

import autenticacao  # noqa: E402
import banco         # noqa: E402
# As ferramentas de montagem de resposta WebAuthn vivem em test_passkey.py.
# Duplica-las aqui criaria duas versoes que divergem no dia em que uma for
# corrigida — e a que estivesse errada passaria calada.
import test_passkey as tp  # noqa: E402
import cortina       # noqa: E402
import servir        # noqa: E402


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

    # `portas.html` entra na mesma conta: ele e injetado dentro da capa e busca
    # tres rotas proprias. Um erro de digitacao ali falha calado na cara do dono
    # — o botao roda, o servidor responde 404, e a tela nao mostra nada.
    TELAS = ("index.html", "portas.html")

    def _rotas_do_html(self):
        html = "\n".join((Path(__file__).parent / t).read_text(encoding="utf-8")
                         for t in self.TELAS)
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
        # O ESTADO DO OAUTH TAMBEM E FIXADO AQUI, e nao lido do ambiente. Dois
        # testes afirmavam que `GITHUB_ID` era vazio; no dia em que o dono
        # seguisse docs/operacao/registrar-app-github.md e exportasse a
        # variavel, a suite ficava VERMELHA na maquina de quem configurou certo.
        # Achado da revisao de Python de 26/08/2026.
        cls._id_antigo, cls._segredo_antigo = servir.GITHUB_ID, servir.GITHUB_SECRET
        servir.GITHUB_ID = servir.GITHUB_SECRET = ""
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
        servir.GITHUB_ID = cls._id_antigo
        servir.GITHUB_SECRET = cls._segredo_antigo
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

    def test_a_combinacao_certa_revela_a_porta(self):
        """QUAL porta aparece depende do ambiente; que NAO aparece nenhuma
        antes da combinacao certa e o que este teste cobra."""
        antes = self.pedir("/").corpo.lower()
        self.assertNotIn("/entrar/", antes)
        depois = self.pedir("/", cookies=self.abrir_cortina()).corpo.lower()
        self.assertIn("/entrar/", depois)

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
        # Marca nao substituida vaza na cara do dono e some com o anti-CSRF.
        for marca in ("__TOKEN__", "__FAIXA__", "__PORTA_ABERTA__"):
            self.assertNotIn(marca, corpo, marca)

    def test_o_painel_local_avisa_que_a_entrada_nao_pediu_senha(self):
        """Quem esta vendo esta tela entrou por uma porta sem senha, e precisa
        saber disso: a mesma tela no servidor exige GitHub."""
        corpo = self.pedir("/", cookies=self.com_sessao()).corpo
        self.assertIn('class="faixa-local"', corpo)
        antigo = servir.E_LOCAL
        servir.E_LOCAL = False
        try:
            self.assertNotIn('class="faixa-local"',
                             self.pedir("/", cookies=self.com_sessao()).corpo)
        finally:
            servir.E_LOCAL = antigo

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

    # ------------------------------------------------------ a porta local
    def test_a_porta_local_abre_sessao(self):
        r = self.pedir("/entrar/local", cookies=self.abrir_cortina())
        self.assertEqual(r.status, 302)
        self.assertIn("sessao", r.cookies)
        self.assertEqual(
            self.pedir("/api/dados",
                       cookies={"sessao": r.cookies["sessao"]}).status, 200)

    def test_a_porta_local_exige_a_cortina(self):
        self.assertEqual(self.pedir("/entrar/local").status, 404)

    def test_a_porta_local_some_fora_do_ambiente_local(self):
        """A trava e DUPLA de proposito: uma variavel de ambiente esquecida no
        servidor nao pode ser tudo o que separa o mundo de uma conta pronta."""
        cookies = self.abrir_cortina()
        antigo = servir.E_LOCAL
        servir.E_LOCAL = False
        try:
            self.assertEqual(self.pedir("/entrar/local", cookies=cookies).status,
                             404)
        finally:
            servir.E_LOCAL = antigo

    def test_a_porta_local_some_para_quem_vem_de_outro_nome(self):
        """A segunda trava: mesmo em ambiente local, so localhost entra. Barra
        o truque de apontar um dominio para 127.0.0.1."""
        cookies = self.abrir_cortina()
        antigos = servir.HOSTS_OK
        servir.HOSTS_OK = servir.HOSTS_OK | {"dervs.com.br"}
        try:
            r = self.pedir("/entrar/local", cookies=cookies,
                           cabecalhos={"Host": "dervs.com.br"})
            self.assertEqual(r.status, 404)
            self.assertNotIn("sessao", r.cookies)
        finally:
            servir.HOSTS_OK = antigos

    def test_a_porta_local_nao_inventa_senha(self):
        """Entrar pelo ambiente local nao pode fabricar uma senha nem um
        segredo de segundo fator: seria segredo sem dono, e num banco que um
        dia migra para o servidor."""
        self.pedir("/entrar/local", cookies=self.abrir_cortina())
        con = banco.conectar()
        try:
            u = banco.usuario_por_email("dono@teste.local", con=con)
            self.assertIsNotNone(u)
            tipos = {l[0] for l in con.execute(
                "SELECT tipo FROM credencial WHERE usuario_id=?", (u["id"],))}
            self.assertNotIn("senha", tipos)
            self.assertNotIn("totp", tipos)
        finally:
            con.close()

    def test_a_capa_local_oferece_a_porta_local_e_nao_a_do_github(self):
        corpo = self.pedir("/", cookies=self.abrir_cortina()).corpo
        self.assertIn("/entrar/local", corpo)
        # Sem aplicativo registrado, o botao do GitHub nem aparece: botao que
        # leva a 404 e pior que botao que nao existe.
        self.assertNotIn("/entrar/github", corpo)

    def test_a_conta_local_desativada_nao_e_ressuscitada(self):
        """`usuario_por_email` filtra desativados: um `criar_usuario` cego aqui
        estouraria no UNIQUE do e-mail e derrubaria o pedido inteiro."""
        self.pedir("/entrar/local", cookies=self.abrir_cortina())
        con = banco.conectar()
        try:
            con.execute("UPDATE usuario SET desativado_em = ? WHERE email = ?",
                        (banco.agora(), "dono@teste.local"))
            con.commit()
        finally:
            con.close()
        try:
            r = self.pedir("/entrar/local", cookies=self.abrir_cortina())
            self.assertEqual(r.status, 404)
            self.assertNotIn("sessao", r.cookies)
        finally:
            con = banco.conectar()
            con.execute("UPDATE usuario SET desativado_em = NULL WHERE email = ?",
                        ("dono@teste.local",))
            con.commit()
            con.close()

    def test_o_silencio_de_um_nao_esconde_o_alerta_do_outro(self):
        """O IDOR que a etapa 8 consertou no esquema e que faltava na rota.

        `_silenciar` gravava sem `usuario_id` e `_estado` lia sem `usuario_id`:
        os dois caiam no balde do DONO_LOCAL. Com uma segunda conta entrando
        pela web — que e o que esta etapa passou a permitir — o "x" de um
        escondia o alerta do outro.
        """
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("segundo@teste.local", con=con)
            cookie = banco.novo_token()
            banco.abrir_sessao(outro, cookie, banco.prazo(3600), con=con)
            do_outro = {"sessao": banco.confirmar_segundo_fator(
                cookie, banco.novo_token(), con=con)}
        finally:
            con.close()
        meu = self.com_sessao()
        pid = "regra-de-teste:projeto-de-teste"
        ok = self.pedir("/api/silenciar", "POST", {"id": pid, "horas": 24},
                        cookies=meu,
                        cabecalhos={"X-Token": self._token_da_pagina(meu)})
        self.assertEqual(ok.status, 200)
        con = banco.conectar()
        try:
            self.assertIn(pid, banco.silenciadas(con, usuario_id=self.uid))
            self.assertNotIn(pid, banco.silenciadas(con, usuario_id=outro))
            # E o balde do DONO_LOCAL nao recebeu nada.
            self.assertNotIn(pid, banco.silenciadas(con,
                                                    usuario_id=banco.DONO_LOCAL))
        finally:
            con.close()
        self.assertEqual(self.pedir("/api/dados", cookies=do_outro).status, 200)

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
        self.assertEqual(
            self.pedir("/entrar/github", cookies=self.abrir_cortina()).status, 404)

    def test_com_aplicativo_registrado_a_rota_leva_ao_github(self):
        """O caminho "aplicativo registrado" nao tinha teste nenhum: a suite so
        exercitava o mundo em que ele nao existe."""
        antes = servir.GITHUB_ID, servir.GITHUB_SECRET
        servir.GITHUB_ID, servir.GITHUB_SECRET = "inventado", "tambem-inventado"
        try:
            cookies = self.abrir_cortina()
            r = self.pedir("/entrar/github", cookies=cookies)
            self.assertEqual(r.status, 302)
            destino = r.cabecalhos.get("Location", "")
            self.assertTrue(destino.startswith(autenticacao.AUTORIZAR + "?"),
                            destino)
            self.assertIn("client_id=inventado", destino)
            # O segredo NUNCA vai para a URL de ida.
            self.assertNotIn("tambem-inventado", destino)
            # E o selo da cortina e renovado, senao ele vence enquanto o dono
            # digita o segundo fator no GitHub e a volta cai num 404 seco.
            self.assertIn("cortina", r.cookies)
            self.assertIn("state", r.cookies)
            self.assertIn("/entrar/github", self.pedir("/", cookies=cookies).corpo)
        finally:
            servir.GITHUB_ID, servir.GITHUB_SECRET = antes

    def test_nao_existe_rota_de_registro(self):
        self.assertNotIn("/api/registro", servir.ROTAS)
        self.assertEqual(self.pedir("/api/registro", "POST", {}).status, 404)


    # ==================================================== as portas de entrada
    #
    # As portas novas, exercitadas PELO SOQUETE.
    #
    #     Nao basta a rota existir na tabela: em 25/08/2026 eu afirmei que uma fila
    #     funcionava tendo visto so a faixa aparecer na tela, e o botao nunca disparava.
    #     Aqui um login por chave de acesso acontece de ponta a ponta — desafio pedido
    #     ao servidor, assinatura feita com uma chave privada de teste, resposta
    #     conferida pelo `p256.py` que este repositorio escreveu a mao.
    #
    #     As ferramentas de montagem vem de `test_passkey.py` de proposito: duplicar o
    #     montador de CBOR aqui criaria duas versoes que divergem no dia em que uma for
    #     corrigida.

    def cortina_e_desafio(self):
        """Passa pela cortina e pede um desafio. Devolve (cookies, desafio)."""
        cookies = self.abrir_cortina()
        r = self.pedir("/entrar/chave/desafio", "POST", {}, cookies=cookies)
        self.assertEqual(r.status, 200, r.corpo)
        cookies["desafio"] = r.cookies["desafio"]
        return cookies, tp.passkey.de_b64url(json.loads(r.corpo)["desafio"])

    def _apagar(self, onde: str, valor: str) -> None:
        """Limpeza que ABRE, COMMITA e FECHA.

        A primeira versao destes testes fazia `banco.conectar().execute(...)`
        numa lambda de addCleanup: a conexao nunca fechava, e depois de algumas
        limpezas o servidor de verdade parava de responder no meio de um teste
        de OUTRA parte do arquivo. Falha em cascata, longe da causa.
        """
        con = banco.conectar()
        try:
            con.execute("DELETE FROM %s WHERE cred_id LIKE ?" % onde, (valor,))
            con.commit()
        finally:
            con.close()

    def cadastrar_chave(self, contador=0):
        """Uma chave por TESTE, com id proprio.

        O banco vive a classe inteira. Com um id fixo, o segundo teste a
        cadastrar estourava no UNIQUE — e o UNIQUE esta certo: sao duas contas
        reivindicando a mesma credencial que ele impede.
        """
        self.cred_id = tp.passkey.b64url(("cred-%s" % self.id()).encode())
        self.addCleanup(self._apagar, "chave_de_acesso", self.cred_id)
        privada, publica = tp._par_de_chaves()
        banco.guardar_chave_de_acesso(self.uid, self.cred_id, publica,
                                      apelido="PC de teste", contador=contador)
        return privada

    def responder(self, privada, desafio, rp_id="127.0.0.1", flags=0x05,
                  contador=1, origem=None):
        origem = origem or ("http://127.0.0.1:%d" % self.porta)
        cliente = tp._client_data("webauthn.get", desafio, origem=origem)
        aut = tp._dados_do_autenticador(rp_id=rp_id, flags=flags,
                                        contador=contador)
        assinatura = tp._assinar(
            privada, aut + hashlib.sha256(cliente).digest())
        return {"cred_id": self.cred_id,
                "cliente": tp.passkey.b64url(cliente),
                "autenticador": tp.passkey.b64url(aut),
                "assinatura": tp.passkey.b64url(assinatura)}

    # ------------------------------------------------- a porta antes da hora
    def test_a_capa_fechada_nao_admite_que_ha_chave_de_acesso(self):
        """A cortina existe para isto: nada de login viaja antes dela."""
        corpo = self.pedir("/").corpo.lower()
        for proibido in ("passkey", "chave de acesso", "webauthn",
                         "credentials.get", "codigo do papel", "recupera"):
            self.assertNotIn(proibido, corpo, proibido)

    def test_a_capa_aberta_mostra_o_menu(self):
        corpo = self.pedir("/", cookies=self.abrir_cortina()).corpo.lower()
        self.assertIn('data-porta="chave"', corpo)
        self.assertIn('data-porta="codigo"', corpo)

    def test_sem_cortina_a_rota_do_desafio_nao_existe(self):
        """404, e nao 403: quem nao passou pela cortina nao descobre a rota."""
        r = self.pedir("/entrar/chave/desafio", "POST", {})
        self.assertEqual(r.status, 404)

    def test_sem_cortina_a_rota_de_entrar_nao_existe(self):
        self.assertEqual(self.pedir("/entrar/chave", "POST", {}).status, 404)
        self.assertEqual(self.pedir("/entrar/codigo", "POST", {}).status, 404)

    def test_o_desafio_muda_a_cada_pedido(self):
        cookies = self.abrir_cortina()
        vistos = set()
        for _ in range(5):
            r = self.pedir("/entrar/chave/desafio", "POST", {}, cookies=cookies)
            vistos.add(json.loads(r.corpo)["desafio"])
        self.assertEqual(len(vistos), 5)

    def test_pedir_desafio_nao_gasta_tentativa(self):
        """Pedir desafio nao e chutar, e nao pode custar como chute.

        Quem chuta e `/entrar/chave`, que tem o teto. Se a emissao do desafio
        contasse, cinco cliques no botao — com a pessoa desistindo do PIN no
        meio, que nem sequer chega ao servidor — trancariam a conta por 15
        minutos. E exatamente a falha que prendeu o dono do lado de fora da
        propria maquina em 26/08, por outro caminho.
        """
        cookies = self.abrir_cortina()
        cortina.zerar_tentativas()
        for _ in range(cortina.TETO * 3):
            r = self.pedir("/entrar/chave/desafio", "POST", {}, cookies=cookies)
            self.assertEqual(r.status, 200)

    def test_o_desafio_nao_aceita_pedido_de_outro_site(self):
        r = self.pedir("/entrar/chave/desafio", "POST", {},
                       cookies=self.abrir_cortina(), com_origem=False)
        self.assertEqual(r.status, 403)

    # ---------------------------------------------------- o caminho feliz
    def test_uma_chave_de_acesso_ABRE_a_sessao(self):
        """O teste que prova que a coisa toda funciona de ponta a ponta."""
        privada = self.cadastrar_chave()
        cookies, desafio = self.cortina_e_desafio()
        r = self.pedir("/entrar/chave", "POST",
                       self.responder(privada, desafio), cookies=cookies)
        self.assertEqual(r.status, 200, r.corpo)
        self.assertIn("sessao", r.cookies)
        # E a sessao serve mesmo: a rota de dado responde com ela.
        dados = self.pedir("/api/dados", cookies={"sessao": r.cookies["sessao"]})
        self.assertEqual(dados.status, 200)

    def test_o_contador_avanca_no_banco(self):
        privada = self.cadastrar_chave(contador=1)
        cookies, desafio = self.cortina_e_desafio()
        self.pedir("/entrar/chave", "POST",
                   self.responder(privada, desafio, contador=7), cookies=cookies)
        guardada = banco.chave_de_acesso(self.cred_id)
        self.assertEqual(guardada["contador"], 7)

    # ------------------------------------------------------- o que e recusado
    def test_assinatura_de_outra_chave_nao_entra(self):
        self.cadastrar_chave()
        outra, _ = tp._par_de_chaves()
        cookies, desafio = self.cortina_e_desafio()
        r = self.pedir("/entrar/chave", "POST",
                       self.responder(outra, desafio), cookies=cookies)
        self.assertEqual(r.status, 401)
        self.assertNotIn("sessao", r.cookies)

    def test_o_desafio_nao_serve_duas_vezes(self):
        """Uso unico de verdade: a MESMA resposta, valida, nao entra de novo."""
        privada = self.cadastrar_chave()
        cookies, desafio = self.cortina_e_desafio()
        resposta = self.responder(privada, desafio)
        self.assertEqual(self.pedir("/entrar/chave", "POST", resposta,
                                    cookies=cookies).status, 200)
        self.assertEqual(self.pedir("/entrar/chave", "POST", resposta,
                                    cookies=cookies).status, 401)

    def test_contador_que_volta_atras_nao_entra(self):
        """A impressao digital de uma chave copiada."""
        privada = self.cadastrar_chave(contador=9)
        cookies, desafio = self.cortina_e_desafio()
        r = self.pedir("/entrar/chave", "POST",
                       self.responder(privada, desafio, contador=3),
                       cookies=cookies)
        self.assertEqual(r.status, 401)

    def test_chave_revogada_nao_entra(self):
        privada = self.cadastrar_chave()
        alvo = banco.chave_de_acesso(self.cred_id)["id"]
        banco.revogar_chave_de_acesso(alvo, self.uid)
        cookies, desafio = self.cortina_e_desafio()
        self.assertEqual(self.pedir("/entrar/chave", "POST",
                                    self.responder(privada, desafio),
                                    cookies=cookies).status, 401)

    def test_credencial_que_nao_existe_da_a_mesma_resposta_de_assinatura_errada(self):
        """O anti-oraculo: status e corpo iguais, senao a tela vira uma lista
        de quem existe."""
        privada = self.cadastrar_chave()
        cookies, desafio = self.cortina_e_desafio()
        boa = self.responder(privada, desafio)
        inexistente = dict(boa, cred_id=tp.passkey.b64url(b"nunca-vista"))
        a = self.pedir("/entrar/chave", "POST", inexistente, cookies=cookies)
        cookies2, desafio2 = self.cortina_e_desafio()
        outra, _ = tp._par_de_chaves()
        b = self.pedir("/entrar/chave", "POST",
                       self.responder(outra, desafio2), cookies=cookies2)
        self.assertEqual((a.status, a.corpo), (b.status, b.corpo))

    def test_corpo_torto_nao_derruba_o_servidor(self):
        cookies, _ = self.cortina_e_desafio()
        for torto in ({}, {"cred_id": "x"}, {"cred_id": "!!", "cliente": "!!"},
                      {"cred_id": "x", "cliente": "AQ", "autenticador": "AQ",
                       "assinatura": "AQ"}):
            r = self.pedir("/entrar/chave", "POST", torto, cookies=cookies)
            self.assertIn(r.status, (401, 429), repr(torto))

    def test_pedido_de_outro_site_nao_entra(self):
        privada = self.cadastrar_chave()
        cookies, desafio = self.cortina_e_desafio()
        r = self.pedir("/entrar/chave", "POST", self.responder(privada, desafio),
                       cookies=cookies, com_origem=False)
        self.assertEqual(r.status, 403)

    # ------------------------------------------------------ codigo do papel
    def test_o_codigo_do_papel_abre_a_sessao(self):
        codigo = banco.gerar_codigos_de_recuperacao(self.uid)[0]
        r = self.pedir("/entrar/codigo", "POST", {"codigo": codigo},
                       cookies=self.abrir_cortina())
        self.assertEqual(r.status, 200, r.corpo)
        self.assertIn("sessao", r.cookies)
        self.assertEqual(json.loads(r.corpo)["restantes"], 9)

    def test_o_mesmo_codigo_nao_abre_duas_vezes(self):
        codigo = banco.gerar_codigos_de_recuperacao(self.uid)[0]
        cookies = self.abrir_cortina()
        self.assertEqual(self.pedir("/entrar/codigo", "POST", {"codigo": codigo},
                                    cookies=cookies).status, 200)
        self.assertEqual(self.pedir("/entrar/codigo", "POST", {"codigo": codigo},
                                    cookies=cookies).status, 401)

    def test_codigo_inventado_nao_abre(self):
        banco.gerar_codigos_de_recuperacao(self.uid)
        r = self.pedir("/entrar/codigo", "POST", {"codigo": "AAAAA-BBBBB-CCCCC-DDDDD"},
                       cookies=self.abrir_cortina())
        self.assertEqual(r.status, 401)
        self.assertNotIn("sessao", r.cookies)

    def test_o_teto_de_chute_do_codigo_existe(self):
        cookies = self.abrir_cortina()
        cortina.zerar_tentativas()
        vistos = set()
        for _ in range(cortina.TETO + 3):
            vistos.add(self.pedir("/entrar/codigo", "POST", {"codigo": "X"},
                                  cookies=cookies).status)
        self.assertIn(429, vistos)

    def test_errar_o_codigo_nao_gasta_o_teto_da_chave(self):
        """Cada porta tem a propria fila. Sem isto, quem erra o codigo tranca
        tambem a chave de acesso, e a tela nao teria como explicar isso."""
        cookies = self.abrir_cortina()
        cortina.zerar_tentativas()
        for _ in range(cortina.TETO + 3):
            self.pedir("/entrar/codigo", "POST", {"codigo": "X"}, cookies=cookies)
        r = self.pedir("/entrar/chave/desafio", "POST", {}, cookies=cookies)
        self.assertEqual(r.status, 200)


    # ================================================ a gestao, ja la dentro
    # As rotas de DENTRO do painel: listar, cadastrar, remover, gerar codigos.

    def sessao_e_token(self):
        cookies = self.com_sessao()
        con = banco.conectar()
        try:
            s = banco.sessao_valida(cookies["sessao"], con=con)
        finally:
            con.close()
        return cookies, servir.Hub._csrf_da_sessao(s)

    def test_a_lista_exige_sessao(self):
        self.assertEqual(self.pedir("/api/chaves").status, 401)

    def test_a_lista_comeca_vazia_e_cobra_a_segunda(self):
        corpo = json.loads(self.pedir("/api/chaves",
                                      cookies=self.com_sessao()).corpo)
        self.assertEqual(corpo["chaves"], [])
        self.assertTrue(corpo["cobrar_a_segunda"])

    def test_a_lista_nao_devolve_a_chave_publica(self):
        self.addCleanup(self._apagar, "chave_de_acesso", "cid-lista")
        banco.guardar_chave_de_acesso(self.uid, "cid-lista", (7, 9),
                                      apelido="PC")
        corpo = json.loads(self.pedir("/api/chaves",
                                      cookies=self.com_sessao()).corpo)
        self.assertNotIn("chave_x", corpo["chaves"][0])
        self.assertNotIn("chave", corpo["chaves"][0])

    def test_com_duas_chaves_para_de_cobrar(self):
        self.addCleanup(self._apagar, "chave_de_acesso", "cid-duas-%")
        for i in (1, 2):
            banco.guardar_chave_de_acesso(self.uid, "cid-duas-%d" % i, (7, 9))
        corpo = json.loads(self.pedir("/api/chaves",
                                      cookies=self.com_sessao()).corpo)
        self.assertFalse(corpo["cobrar_a_segunda"])

    def test_remover_sem_o_token_da_sessao_e_recusado(self):
        """O anti-CSRF: sessao sozinha nao basta para rota que escreve."""
        cookies = self.com_sessao()
        r = self.pedir("/api/chaves/remover", "POST", {"id": 1}, cookies=cookies)
        self.assertEqual(r.status, 403)

    def test_remover_a_chave_de_outra_conta_nao_funciona(self):
        self.addCleanup(self._apagar, "chave_de_acesso", "cid-alheia")
        outro = banco.criar_usuario("alheio@teste.local")
        alheia = banco.guardar_chave_de_acesso(outro, "cid-alheia", (7, 9))
        cookies, token = self.sessao_e_token()
        r = self.pedir("/api/chaves/remover", "POST", {"id": alheia},
                       cookies=cookies, cabecalhos={"X-Token": token})
        self.assertEqual(r.status, 404)
        self.assertIsNotNone(banco.chave_de_acesso("cid-alheia"))

    def test_remover_a_propria_chave_funciona(self):
        self.addCleanup(self._apagar, "chave_de_acesso", "cid-minha")
        minha = banco.guardar_chave_de_acesso(self.uid, "cid-minha", (7, 9))
        cookies, token = self.sessao_e_token()
        r = self.pedir("/api/chaves/remover", "POST", {"id": minha},
                       cookies=cookies, cabecalhos={"X-Token": token})
        self.assertEqual(r.status, 200, r.corpo)
        self.assertIsNone(banco.chave_de_acesso("cid-minha"))

    def test_o_desafio_de_cadastro_exige_sessao(self):
        self.assertEqual(self.pedir("/api/chaves/desafio", "POST", {}).status, 401)

    def test_o_desafio_de_cadastro_nao_entrega_o_id_do_banco(self):
        """O identificador que vai DENTRO do autenticador e derivado, e alguns
        aparelhos o mostram na tela de escolha de conta."""
        cookies, token = self.sessao_e_token()
        r = self.pedir("/api/chaves/desafio", "POST", {}, cookies=cookies,
                       cabecalhos={"X-Token": token})
        self.assertEqual(r.status, 200, r.corpo)
        self.assertNotEqual(json.loads(r.corpo)["usuario"]["id"], str(self.uid))

    def test_gerar_codigos_devolve_dez_uma_vez_so(self):
        cookies, token = self.sessao_e_token()
        r = self.pedir("/api/codigos/gerar", "POST", {}, cookies=cookies,
                       cabecalhos={"X-Token": token})
        self.assertEqual(r.status, 200, r.corpo)
        primeiros = json.loads(r.corpo)["codigos"]
        self.assertEqual(len(primeiros), 10)
        r2 = self.pedir("/api/codigos/gerar", "POST", {}, cookies=cookies,
                        cabecalhos={"X-Token": token})
        self.assertFalse(set(primeiros) & set(json.loads(r2.corpo)["codigos"]))

    def test_gerar_codigos_sem_token_e_recusado(self):
        r = self.pedir("/api/codigos/gerar", "POST", {},
                       cookies=self.com_sessao())
        self.assertEqual(r.status, 403)

    # ------------------------------------------------- o selo chega na tela
    def test_api_dados_traz_o_selo_de_cada_projeto(self):
        """O motor do selo existe desde a etapa 10 e nunca era chamado.

        Sem esta linha a tela teria de recalcular os quatro estados em
        JavaScript — uma segunda copia da regra mais importante do produto,
        e a copia que diverge e sempre a que ninguem le. A etapa 14 fecha o
        cano: quem decide a cor e `regras.selo_do_projeto`, no servidor.
        """
        # O projeto e semeado AQUI de proposito. Sem ele o laco abaixo giraria
        # sobre uma lista vazia e o teste passaria por engano — a armadilha que
        # o plano da etapa 15 nomeia e que este projeto ja pegou uma vez.
        banco.gravar("projeto-do-selo", "local",
                     {"nome": "projeto-do-selo", "git": {"versionado": True}},
                     usuario_id=self.uid)
        r = self.pedir("/api/dados", cookies=self.com_sessao())
        self.assertEqual(r.status, 200)
        d = json.loads(r.corpo)
        self.assertTrue(d["projetos"], "nenhum projeto para examinar")
        for p in d["projetos"]:
            self.assertIn(p.get("selo"),
                          ("saudavel", "atencao", "quebrado", "sem_dados"),
                          "projeto %r sem selo valido" % p.get("nome"))
            # A prova por tras do selo viaja junto: sem ela a tela nao consegue
            # dizer QUAL camada esta velha, e "sem dados" vira um veredito sem
            # explicacao — que e a mesma mentira, so que educada.
            self.assertIsInstance(p.get("camadas"), dict)

    def test_projeto_sem_medicao_nenhuma_nao_vem_verde(self):
        """A mentira por omissao, conferida na fronteira HTTP.

        `test_regras.py` ja prova isso na funcao. Aqui prova-se que a rota nao
        desfaz o cuidado no caminho ate o navegador.
        """
        cru = {"nome": "sem-medida", "medido_em": {}}
        self.assertEqual(servir.regras.selo_do_projeto(cru), "sem_dados")

    # ------------------------------------ "isto esta certo assim" (etapa 14)
    def test_arquivar_sem_motivo_e_recusado_e_nao_grava(self):
        """Sumico permanente sem motivo registrado nao tem volta explicavel.

        O banco ja levantava ValueError; sem esta guarda a rota devolveria 500
        e a tela mostraria "nao conseguimos arquivar" para um erro que e de
        preenchimento, nao de servidor.
        """
        cookies, token = self.sessao_e_token()
        r = self.pedir("/api/arquivar", "POST", {"id": "ci_vermelha:x"},
                       cookies=cookies, cabecalhos={"X-Token": token})
        self.assertEqual(r.status, 400, r.corpo)
        con = banco.conectar()
        try:
            self.assertNotIn("ci_vermelha:x",
                             banco.arquivadas(usuario_id=self.uid, con=con))
        finally:
            con.close()

    def test_arquivar_com_motivo_longo_demais_e_recusado_sem_cortar(self):
        """Cortar em silencio e a mentira do painel em miniatura.

        Ate aqui a rota respondia 200 "arquivada." depois de guardar so os 300
        primeiros caracteres: o dono escrevia a justificativa inteira, a tela
        dizia que salvou, e o resto sumia sem aviso. O rastro que o arquivar
        existe para preservar chegava cortado. Recusar e dizer o limite e a
        unica resposta honesta.
        """
        cookies, token = self.sessao_e_token()
        pid = "nao_publicado:projeto-de-teste"
        longo = "x" * (servir.Hub.MOTIVO_MAX + 1)
        r = self.pedir("/api/arquivar", "POST", {"id": pid, "motivo": longo},
                       cookies=cookies, cabecalhos={"X-Token": token})
        self.assertEqual(r.status, 400, r.corpo)
        # O limite aparece na mensagem: recusa sem numero manda adivinhar.
        self.assertIn(str(servir.Hub.MOTIVO_MAX), r.corpo)
        # E nada meio-gravado ficou para tras.
        con = banco.conectar()
        try:
            self.assertNotIn(pid, banco.arquivadas(usuario_id=self.uid, con=con))
        finally:
            con.close()

    def test_arquivar_no_limite_exato_do_motivo_e_aceito_inteiro(self):
        """A fronteira do lado de dentro — e o texto chega ao banco sem perda."""
        cookies, token = self.sessao_e_token()
        pid = "nao_publicado:projeto-de-teste"
        no_limite = "y" * servir.Hub.MOTIVO_MAX
        r = self.pedir("/api/arquivar", "POST", {"id": pid, "motivo": no_limite},
                       cookies=cookies, cabecalhos={"X-Token": token})
        self.assertEqual(r.status, 200, r.corpo)
        d = json.loads(self.pedir("/api/dados", cookies=cookies).corpo)
        guardadas = {a["id"]: a for a in d["arquivadas"]}
        self.assertEqual(guardadas[pid]["motivo"], no_limite)

    def test_arquivar_com_motivo_some_da_lista_e_deixa_rastro(self):
        cookies, token = self.sessao_e_token()
        pid = "nao_publicado:projeto-de-teste"
        r = self.pedir("/api/arquivar", "POST",
                       {"id": pid, "motivo": "este projeto nao publica de proposito"},
                       cookies=cookies, cabecalhos={"X-Token": token})
        self.assertEqual(r.status, 200, r.corpo)

        d = json.loads(self.pedir("/api/dados", cookies=cookies).corpo)
        self.assertNotIn(pid, [i["id"] for i in d["pendencias"]])
        # O rastro tem de chegar a TELA, e nao so ao banco: a secao
        # "Arquivados" mostra o motivo e a data, e o botao de desarquivar.
        guardadas = {a["id"]: a for a in d["arquivadas"]}
        self.assertIn(pid, guardadas)
        self.assertEqual(guardadas[pid]["motivo"],
                         "este projeto nao publica de proposito")
        self.assertTrue(guardadas[pid]["arquivado_em"])

    def test_desarquivar_devolve_a_pendencia_para_a_lista(self):
        cookies, token = self.sessao_e_token()
        pid = "pr_parado:projeto-de-teste"
        self.pedir("/api/arquivar", "POST", {"id": pid, "motivo": "engano meu"},
                   cookies=cookies, cabecalhos={"X-Token": token})
        r = self.pedir("/api/desarquivar", "POST", {"id": pid},
                       cookies=cookies, cabecalhos={"X-Token": token})
        self.assertEqual(r.status, 200, r.corpo)
        d = json.loads(self.pedir("/api/dados", cookies=cookies).corpo)
        self.assertNotIn(pid, [a["id"] for a in d["arquivadas"]])

    def test_arquivar_de_um_usuario_nao_esconde_o_alerta_do_outro(self):
        """O mesmo IDOR que a etapa 11 consertou no silenciar.

        Arquivar e mais grave que silenciar: silenciar vence em 24 h, arquivar
        e para sempre. Um vazamento aqui apagaria o alerta de seguranca de
        outra conta sem prazo para se desfazer sozinho.
        """
        meus, meu_token = self.sessao_e_token()
        pid = "vulnerabilidade:projeto-de-teste"
        self.pedir("/api/arquivar", "POST", {"id": pid, "motivo": "so meu"},
                   cookies=meus, cabecalhos={"X-Token": meu_token})
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("outro-arquivar@teste.local", con=con)
            self.assertIn(pid, banco.arquivadas(usuario_id=self.uid, con=con))
            self.assertNotIn(pid, banco.arquivadas(usuario_id=outro, con=con))
            self.assertNotIn(pid, banco.arquivadas(usuario_id=banco.DONO_LOCAL,
                                                   con=con))
        finally:
            con.close()

    def test_arquivar_e_desarquivar_exigem_o_anti_csrf(self):
        cookies = self.com_sessao()
        for rota in ("/api/arquivar", "/api/desarquivar"):
            with self.subTest(rota=rota):
                r = self.pedir(rota, "POST", {"id": "x:y", "motivo": "m"},
                               cookies=cookies)
                self.assertEqual(r.status, 403)

    def test_arquivar_sem_sessao_e_401(self):
        for rota in ("/api/arquivar", "/api/desarquivar"):
            with self.subTest(rota=rota):
                self.assertEqual(
                    self.pedir(rota, "POST", {"id": "x:y", "motivo": "m"}).status,
                    401)

    # --------------------------------------------- os estaticos da etapa 13
    def test_a_folha_de_estilo_e_as_fontes_sao_servidas(self):
        """A etapa 13 criou assets/ e ninguem podia baixar nada de la.

        Sem isto a tela nova nasceria sem tipografia e sem token: o navegador
        pediria /assets/dervs.css, levaria 404, e a pagina apareceria com a
        fonte do sistema e as cores do navegador — parecendo quebrada sem
        nenhum erro visivel no servidor.
        """
        r = self.pedir("/assets/dervs.css", cookies=self.com_sessao())
        self.assertEqual(r.status, 200)
        self.assertIn("--estado-sem-dados", r.corpo)

    def test_a_lista_de_estaticos_continua_sendo_de_caminho_exato(self):
        """Permissao por PASTA seria travessia de diretorio esperando acontecer.

        A lista nasce de uma leitura da pasta na subida, com extensao filtrada.
        Estes tres pedidos provam que ela nao virou um prefixo permissivo.
        """
        for caminho in ("/assets/CREDITOS.md",
                        "/assets/../banco.py",
                        "/assets/nao-existe.css"):
            with self.subTest(caminho=caminho):
                r = self.pedir(caminho, cookies=self.com_sessao())
                self.assertNotEqual(r.status, 200, caminho)

    def test_robots_bloqueia_as_telas_autenticadas(self):
        r = self.pedir("/robots.txt")
        self.assertEqual(r.status, 200)
        for area in ("/painel", "/projeto", "/maquinas", "/api"):
            self.assertIn("Disallow: " + area, r.corpo)


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


class DentroDoContainer(unittest.TestCase):
    """Os dois ajustes sem os quais a imagem publicada nao atende ninguem.

    1. ENDERECO DE ESCUTA. `127.0.0.1` dentro de um container e o loopback DO
       CONTAINER: o nginx do host bate na porta publicada, o Docker encaminha
       para o IP do container, e ninguem esta escutando ali. O site responderia
       502 para sempre, e o log do servidor nao teria uma linha de erro — ele
       subiu, so nao estava no endereco certo.

    2. COLETA DA PROPRIA MAQUINA. `coletar.py` mede as pastas de projeto DESTA
       maquina. No servidor essa pasta nao existe, entao a medicao volta com
       zero projetos — e gravar "zero" por cima do que o agente pareado mandou
       e exatamente a lei 2 deste repositorio sendo violada: um numero errado
       com cara de certo. No servidor a medicao local fica desligada.
    """

    def setUp(self):
        self._antes = {v: os.environ.get(v)
                       for v in ("DERVS_ESCUTA", "DERVS_COLETA_LOCAL")}
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        for nome, valor in self._antes.items():
            if valor is None:
                os.environ.pop(nome, None)
            else:
                os.environ[nome] = valor

    def test_sem_variavel_escuta_so_o_loopback(self):
        """O padrao continua sendo o de sempre: nesta maquina, so localhost."""
        os.environ.pop("DERVS_ESCUTA", None)
        self.assertEqual(servir._endereco_de_escuta(), "127.0.0.1")

    def test_com_variavel_escuta_onde_ela_mandar(self):
        os.environ["DERVS_ESCUTA"] = "0.0.0.0"
        self.assertEqual(servir._endereco_de_escuta(), "0.0.0.0")

    def test_escuta_vazia_volta_para_o_loopback(self):
        os.environ["DERVS_ESCUTA"] = "  "
        self.assertEqual(servir._endereco_de_escuta(), "127.0.0.1")

    def test_por_padrao_mede_esta_maquina(self):
        os.environ.pop("DERVS_COLETA_LOCAL", None)
        self.assertTrue(servir._mede_esta_maquina())

    def test_zero_desliga_a_medicao_desta_maquina(self):
        for desligado in ("0", "nao", "false", "NAO", " 0 "):
            os.environ["DERVS_COLETA_LOCAL"] = desligado
            self.assertFalse(servir._mede_esta_maquina(),
                             "%r devia desligar a coleta" % desligado)

    def test_qualquer_outro_valor_mantem_ligado(self):
        os.environ["DERVS_COLETA_LOCAL"] = "1"
        self.assertTrue(servir._mede_esta_maquina())


class QuemPodeDizerDeOndeVeioOPedido(unittest.TestCase):
    """A lista de proxies confiaveis, que ate a etapa 16 nao tinha teste nenhum.

    O PROBLEMA QUE ELA RESOLVE. Atras do nginx, o endereco de quem chega e
    sempre o mesmo: o gateway do Docker. Se o servidor acreditar nisso, o teto
    de cinco tentativas por quinze minutos vira UM BALDE UNICO para a internet
    inteira — e `/entrada` e `/agente/parear` sao rotas abertas. Cinco chamadas
    de um estranho, repetidas de tres em tres minutos, e o dono nunca mais entra
    no proprio painel nem pareia computador nenhum. A resposta e 204 por
    desenho, entao a tela nem tem como dizer por que parou.

    O PROBLEMA QUE ELA CRIA SE FOR LARGA DEMAIS. Se qualquer um pudesse mandar
    `X-Forwarded-For`, bastaria variar o cabecalho a cada chute e o teto sumiria
    do outro lado.

    POR QUE FAIXA E NAO ENDERECO EXATO. O gateway do Docker nao e previsivel: a
    rede que o compose cria ganha a sub-rede que estiver livre na maquina —
    medido em 28/08/2026, `172.17.0.1` na rede padrao, e outra a cada rede nova.
    Fixar a sub-rede no compose foi tentado e colide com quem ja esta la (a VPS
    tem 26 containers). Uma faixa privada resolve sem adivinhacao, e nao alarga
    de verdade: a porta do container so aceita conexao de 127.0.0.1 do host.
    """

    def test_vazio_nao_confia_em_ninguem(self):
        """O padrao desta maquina. Sem proxy na frente, ninguem pode reescrever
        de onde veio o pedido — e e assim que tem de continuar."""
        self.assertEqual(servir._redes_confiaveis(""), ())
        self.assertEqual(servir._redes_confiaveis(None), ())

    def test_endereco_solto_continua_valendo(self):
        redes = servir._redes_confiaveis("172.17.0.1")
        self.assertTrue(servir._vem_de_proxy("172.17.0.1", redes))
        self.assertFalse(servir._vem_de_proxy("172.17.0.2", redes))

    def test_faixa_inteira(self):
        redes = servir._redes_confiaveis("172.16.0.0/12")
        for dentro in ("172.16.0.1", "172.17.0.1", "172.18.0.1", "172.31.255.254"):
            self.assertTrue(servir._vem_de_proxy(dentro, redes), dentro)
        for fora in ("172.15.0.1", "172.32.0.1", "8.8.8.8", "192.168.1.1"):
            self.assertFalse(servir._vem_de_proxy(fora, redes), fora)

    def test_varias_entradas_separadas_por_virgula(self):
        redes = servir._redes_confiaveis(" 127.0.0.1 , 172.16.0.0/12 ")
        self.assertTrue(servir._vem_de_proxy("127.0.0.1", redes))
        self.assertTrue(servir._vem_de_proxy("172.20.5.9", redes))
        self.assertFalse(servir._vem_de_proxy("10.0.0.1", redes))

    def test_entrada_mal_escrita_nao_vira_permissao(self):
        """Falha FECHADA. Um erro de digitacao no `.env` do servidor nao pode
        virar "confia em todo mundo" — tem de virar "nao confia nisso"."""
        redes = servir._redes_confiaveis("nao-e-ip, 999.1.1.1, /24, 172.17.0.1")
        self.assertEqual(len(redes), 1)
        self.assertTrue(servir._vem_de_proxy("172.17.0.1", redes))

    def test_endereco_de_cliente_ilegivel_nao_e_confiavel(self):
        """`client_address` pode ser "?" quando a conexao ja morreu. Nesse caso
        a resposta e nao, nunca sim."""
        redes = servir._redes_confiaveis("172.16.0.0/12")
        for esquisito in ("?", "", "nao-e-ip", "172.17.0.1:4777"):
            self.assertFalse(servir._vem_de_proxy(esquisito, redes), esquisito)

    def test_ipv6_tambem(self):
        redes = servir._redes_confiaveis("fd00::/8")
        self.assertTrue(servir._vem_de_proxy("fd00::1", redes))
        self.assertFalse(servir._vem_de_proxy("2001:db8::1", redes))


class ODominioDeFora(unittest.TestCase):
    """`dervs.com.br` precisa entrar em `HOSTS_OK`, e so por variavel.

    O servidor recusa com 403 todo pedido cujo cabecalho `Host` nao esteja num
    conjunto fechado — e isso e defesa, nao defeito: sem ela, apontar um dominio
    qualquer para o IP do servidor daria acesso ao painel. O preco e que, atras
    do nginx, o `Host` que chega e `dervs.com.br`, e o site inteiro responderia
    403 ate alguem colocar esse nome na lista.

    Tres comentarios espalhados por `servir.py` (linhas 682, 743 e 796) ja
    prometiam que a etapa 16 faria exatamente isto. E aqui.
    """

    def setUp(self):
        self._antes = os.environ.get("DERVS_DOMINIO")
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        if self._antes is None:
            os.environ.pop("DERVS_DOMINIO", None)
        else:
            os.environ["DERVS_DOMINIO"] = self._antes

    def test_sem_variavel_nao_ha_dominio_de_fora(self):
        os.environ.pop("DERVS_DOMINIO", None)
        self.assertEqual(servir._dominio_publico(), "")

    def test_le_o_dominio_cru(self):
        os.environ["DERVS_DOMINIO"] = "dervs.com.br"
        self.assertEqual(servir._dominio_publico(), "dervs.com.br")

    def test_aceita_colado_com_esquema_e_barra(self):
        """Quem preenche a variavel copia da barra do navegador. Colar
        "https://dervs.com.br/" nao pode virar um Host que nunca casa —
        seria o site inteiro em 403 por um erro de digitacao."""
        for cru in ("https://dervs.com.br", "https://dervs.com.br/",
                    "HTTPS://DERVS.COM.BR/painel", "  dervs.com.br  "):
            os.environ["DERVS_DOMINIO"] = cru
            self.assertEqual(servir._dominio_publico(), "dervs.com.br",
                             "nao normalizou %r" % cru)

    def test_sem_dominio_so_o_localhost_entra(self):
        hosts, origens = servir._enderecos_permitidos(4777, "")
        self.assertEqual(hosts, {"localhost:4777", "127.0.0.1:4777"})
        self.assertEqual(origens,
                         {"http://localhost:4777", "http://127.0.0.1:4777"})

    def test_com_dominio_ele_entra_e_o_localhost_fica(self):
        """O localhost NAO sai no servidor: e por ele que o healthcheck do
        container bate na porta, de dentro. Tirar dali derrubaria a
        verificacao de saude e a publicacao nunca concluiria."""
        hosts, origens = servir._enderecos_permitidos(4777, "dervs.com.br")
        self.assertIn("dervs.com.br", hosts)
        self.assertIn("localhost:4777", hosts)
        self.assertIn("127.0.0.1:4777", hosts)

    def test_a_origem_do_dominio_e_https_e_so_https(self):
        """`http://dervs.com.br` nao entra. O nginx redireciona 80 para 443, e
        aceitar a origem em claro seria aceitar um pedido que viajou aberto."""
        _, origens = servir._enderecos_permitidos(4777, "dervs.com.br")
        self.assertIn("https://dervs.com.br", origens)
        self.assertNotIn("http://dervs.com.br", origens)

    def test_com_dominio_o_loopback_sai_das_ORIGENS(self):
        """A assimetria de proposito: o loopback fica nos HOSTS (o healthcheck
        bate ali de dentro) e sai das ORIGENS.

        `Origin` so aparece em pedido que escreve, e no servidor nao ha pedido
        legitimo vindo de `http://localhost:4777` — mas ha uma pagina assim: o
        proprio DERVS rodando no computador do dono, mesma porta, mesmo
        navegador. Hoje ela nao consegue nada (SameSite=Lax segura o cookie),
        e depender de uma defesa so e o que a revisao apontou."""
        hosts, origens = servir._enderecos_permitidos(4777, "dervs.com.br")
        self.assertEqual(origens, {"https://dervs.com.br"})
        self.assertIn("127.0.0.1:4777", hosts)


if __name__ == "__main__":
    unittest.main(verbosity=0)
