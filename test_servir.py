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
import io
import os
import re
import tempfile
import threading
import time
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import auditoria     # noqa: E402
import autenticacao  # noqa: E402
import banco         # noqa: E402
# As ferramentas de montagem de resposta WebAuthn vivem em test_passkey.py.
# Duplica-las aqui criaria duas versoes que divergem no dia em que uma for
# corrigida — e a que estivesse errada passaria calada.
import test_passkey as tp  # noqa: E402
import cortina       # noqa: E402
import servir        # noqa: E402
import tarefas       # noqa: E402


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
    #
    # OS `.js` DE `assets/` ESTAO AQUI PORQUE E LA QUE OS `fetch()` MORAM AGORA.
    # Ate 28/08/2026 o script vivia dentro do proprio HTML; a CSP que o nginx
    # manda em producao (`default-src 'self'`, sem `script-src`) descarta script
    # embutido, e por isso ele foi para arquivo. Quando isso aconteceu este
    # vigia passou a achar zero `fetch()` — e ficou vermelho sozinho, pelo
    # teste-companheiro logo abaixo. Era para ser assim: um vigia que passa
    # vazio nao vigia nada.
    TELAS = ("index.html", "portas.html",
             "assets/painel.js", "assets/portas.js", "assets/cortina.js")

    def _rotas_do_html(self):
        html = "\n".join((Path(__file__).parent / t).read_text(encoding="utf-8")
                         for t in self.TELAS)
        # Pega o primeiro argumento de fetch(), que e sempre um literal aqui.
        # Query e concatenacao ficam de fora: a tabela casa so o caminho.
        cruas = re.findall(r'fetch\(\s*"(/[^"?]*)', html)
        # O FLUXO AO VIVO NAO E UM `fetch`. Sem esta linha, `/api/eventos`
        # seria a unica rota da tela que ninguem cobra existir — e um erro de
        # digitacao ali deixaria a tela muda sem nenhum teste vermelho.
        cruas += re.findall(r'new\s+EventSource\(\s*"(/[^"?]*)', html)
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
        # O mesmo motivo da lista acima: o que a tela "chama" hoje esta no
        # painel.js, nao no index.html. Ler so o HTML faria este teste passar
        # por ausencia — a rota amputada podia voltar no .js sem ninguem ver.
        html = "\n".join((Path(__file__).parent / t).read_text(encoding="utf-8")
                         for t in ("index.html", "assets/painel.js"))
        # `fetch(` e `src=` sao os dois jeitos pelos quais a tela alcancava o
        # que foi removido — o segundo era o quadro do grafo.
        for morta in ("/api/acao", "/api/execucao", "/api/grafo", "/grafo/"):
            with self.subTest(rota=morta):
                self.assertNotIn('fetch("%s' % morta, html)
                self.assertNotIn('src = "%s"' % morta, html)


class BaseServidorDeVerdade(unittest.TestCase):
    """O ANDAIME: sobe o servidor de verdade numa porta livre.

    Nao tem teste nenhum, de proposito. Quem tem os testes e
    `ServidorDeVerdade`, logo abaixo, e as classes que precisarem do mesmo
    servidor herdam DAQUI — herdar daquela faria os cem testes dela rodarem
    de novo, contra um segundo servidor, a cada classe nova.

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

    def sessao_e_token(self):
        """A sessao E o anti-CSRF dela. Toda rota de escrita precisa dos dois."""
        cookies = self.com_sessao()
        con = banco.conectar()
        try:
            s = banco.sessao_valida(cookies["sessao"], con=con)
        finally:
            con.close()
        return cookies, servir.Hub._csrf_da_sessao(s)

    # --------------------------------------------------------- o fio do agente
    #
    # As quatro subiram de `AsTarefasNoServidorDeVerdade` para ca (Etapa 5 da
    # Auditoria Profunda): os testes de `/api/auditoria` precisam do MESMO
    # fio (maquina pareada, tarefa na fila, POST com token) sem herdar a
    # classe inteira e reexecutar os testes dela.

    def maquina_com_token(self, nome="laptop", autorizada=True):
        """Uma maquina pareada de verdade, e o token dela."""
        codigo = banco.novo_codigo(6)
        con = banco.conectar()
        try:
            banco.abrir_pareamento(self.uid, codigo, banco.prazo(600), con=con)
            token = banco.usar_pareamento(codigo, nome, con=con)
            m = banco.maquina_por_token(token, con=con)
            if autorizada:
                banco.ligar_execucao(m["id"], self.uid, True, con=con)
        finally:
            con.close()
        return token, m["id"]

    def enfileirar_tarefa(self, id_="d:1", regra="env_drift", verde=True,
                          executor="claude"):
        con = banco.conectar()
        try:
            con.execute(
                "INSERT OR REPLACE INTO fila"
                " (id, projeto, regra, trilho, executor, criado_em, estado)"
                " VALUES (?, 'dervs', ?, 'claude', ?, ?, 'esperando')",
                (id_, regra, executor, banco.agora()))
            con.commit()
            if verde:
                banco.repintar_regra(regra, "verde", self.uid, con=con)
        finally:
            con.close()

    def limpar_fila(self):
        con = banco.conectar()
        try:
            con.execute("DELETE FROM fila")
            con.execute("DELETE FROM tarefa_linha")
            con.execute("DELETE FROM cor_da_regra")
            con.execute("DELETE FROM auditoria")
            con.execute("DELETE FROM achado")
            con.commit()
        finally:
            con.close()

    def como_agente(self, token, caminho, corpo):
        return self.pedir(caminho, "POST", corpo, com_origem=False,
                          cabecalhos={"Authorization": "Token " + token})


class ServidorDeVerdade(BaseServidorDeVerdade):
    """Os testes que CONVERSAM com o servidor de verdade.

    Os outros testes deste arquivo leem estrutura em memoria, e isso e bom para
    o que eles cobram. Mas "a tela abriu" nao e prova de que o botao dispara --
    ja afirmei isso uma vez tendo visto so a faixa aparecer. Aqui o pedido sai
    pelo soquete e a resposta vem pelo soquete.
    """

    # ------------------------------------------------------------ estaticos
    #
    # A tabela de rotas ja e cobrada em `test_rotas.py`. Aqui a pergunta e
    # outra e so o servidor de verdade responde: o despacho REALMENTE barra o
    # arquivo, ou a classificacao e um rotulo que ninguem le no caminho do
    # `_estatico`? As duas ja divergiram neste repositorio.

    def test_o_script_do_painel_nao_sai_sem_sessao(self):
        for caminho in ("/assets/painel.js", "/assets/painel.css"):
            with self.subTest(arquivo=caminho):
                r = self.pedir(caminho)
                self.assertEqual(r.status, 401, caminho)
                self.assertNotIn("fetch(", r.corpo)

    def test_o_script_do_painel_sai_para_quem_entrou(self):
        """A outra metade: trava que tranca todo mundo quebra a tela."""
        r = self.pedir("/assets/painel.js", cookies=self.com_sessao())
        self.assertEqual(r.status, 200)
        self.assertIn("fetch(", r.corpo)

    def test_a_folha_da_cortina_continua_saindo_sem_nada(self):
        r = self.pedir("/assets/cortina.css")
        self.assertEqual(r.status, 200)
        self.assertTrue(r.corpo.strip())

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
        # `/api/eventos` fica aberto por cinco minutos de proposito, e uma
        # varredura ingenua penduraria a suite inteira nele. A saida NAO e
        # pular a rota — ela responde com sessao e precisa ser conferida como
        # as outras: e encurtar a vida do fluxo para zero, para ele mandar o
        # aviso de fim e fechar na hora. Assim a varredura continua completa.
        vida = servir.Hub.SEGUNDOS_DE_VIDA
        servir.Hub.SEGUNDOS_DE_VIDA = 0
        self.addCleanup(setattr, servir.Hub, "SEGUNDOS_DE_VIDA", vida)
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

    def test_o_silencio_e_o_perigo_entao_ele_grita(self):
        """Lista vazia COM dominio publico = o balde unico de volta, e nada
        avisava. Duas formas de cair nisso, e a segunda nao depende de erro
        humano: o pool padrao do Docker cai em 192.168.0.0/16 quando as faixas
        172 acabam, e a VPS tem 26 containers — a faixa estaria escrita certa e
        seria inutil. Achado da conferencia das correcoes."""
        self.assertIsNotNone(servir._aviso_do_teto("dervs.com.br", ()))
        self.assertIn("balde unico", servir._aviso_do_teto("dervs.com.br", ()))

    def test_sem_dominio_nao_grita(self):
        """Nesta maquina a lista vazia e o certo: nao ha proxy na frente."""
        self.assertIsNone(servir._aviso_do_teto("", ()))

    def test_com_lista_preenchida_nao_grita(self):
        redes = servir._redes_confiaveis("172.16.0.0/12")
        self.assertIsNone(servir._aviso_do_teto("dervs.com.br", redes))

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


class AsTarefasNoServidorDeVerdade(BaseServidorDeVerdade):
    """O fio de volta, pelo soquete.

    Ler a tabela de rotas nao basta: a classificacao de acesso e um rotulo, e
    ja divergiu do que o despacho faz de verdade neste repositorio. Aqui o
    pedido sai pela rede e a resposta volta pela rede.
    """

    # As quatro utilidades (`maquina_com_token`, `enfileirar_tarefa`,
    # `limpar_fila`, `como_agente`) moraram aqui ate a Etapa 5 da Auditoria
    # Profunda, quando subiram para `BaseServidorDeVerdade` — os testes de
    # `/api/auditoria` precisam do mesmo fio sem herdar esta classe inteira.

    def setUp(self):
        super().setUp()
        self.addCleanup(self.limpar_fila)

    # ------------------------------------------------------ o fio descendo

    def test_relatorio_de_maquina_nao_autorizada_volta_sem_tarefa(self):
        """A lei 3: `maquina.executa` nasce 0, e o padrao manda. Parear um
        computador nunca deu a ele o direito de rodar codigo."""
        token, _ = self.maquina_com_token(autorizada=False)
        self.enfileirar_tarefa()
        r = self.como_agente(token, "/agente/relatorio", {"projetos": []})
        self.assertEqual(r.status, 200)
        self.assertIsNone(json.loads(r.corpo)["tarefa"])

    def test_relatorio_de_maquina_autorizada_traz_a_tarefa_verde(self):
        token, _ = self.maquina_com_token()
        self.enfileirar_tarefa()
        r = self.como_agente(token, "/agente/relatorio", {"projetos": []})
        tarefa = json.loads(r.corpo)["tarefa"]
        self.assertIsNotNone(tarefa)
        self.assertEqual(tarefa["id"], "d:1")
        self.assertEqual(tarefa["projeto"], "dervs")
        self.assertGreater(tarefa["teto_usd"], 0)

    def test_tarefa_vermelha_nao_desce_sem_o_clique_do_dono(self):
        token, _ = self.maquina_com_token()
        self.enfileirar_tarefa(verde=False)
        r = self.como_agente(token, "/agente/relatorio", {"projetos": []})
        self.assertIsNone(json.loads(r.corpo)["tarefa"])

    def test_a_mesma_tarefa_nao_desce_duas_vezes(self):
        """Uma sessao por vez. O segundo pedido nao pode levar a mesma."""
        token, _ = self.maquina_com_token()
        self.enfileirar_tarefa()
        primeira = self.como_agente(token, "/agente/relatorio", {"projetos": []})
        segunda = self.como_agente(token, "/agente/relatorio", {"projetos": []})
        self.assertIsNotNone(json.loads(primeira.corpo)["tarefa"])
        self.assertIsNone(json.loads(segunda.corpo)["tarefa"])

    # ------------------------------------------------------- o fio subindo

    def test_resultado_sem_token_e_401(self):
        self.assertEqual(self.pedir("/agente/resultado", "POST",
                                    {"id": "d:1"}).status, 401)

    def test_resultado_com_token_de_outra_maquina_nao_alcanca_a_tarefa(self):
        """O token da vizinha nao empurra linha na sessao desta."""
        meu, _ = self.maquina_com_token("laptop")
        outro, _ = self.maquina_com_token("vps")
        self.enfileirar_tarefa()
        self.como_agente(meu, "/agente/relatorio", {"projetos": []})
        r = self.como_agente(outro, "/agente/resultado",
                             {"tipo": "progresso", "id": "d:1",
                              "linhas": [[1, "invasao"]]})
        self.assertEqual(r.status, 200)
        con = banco.conectar()
        try:
            self.assertEqual(banco.linhas_da_tarefa("d:1", con=con), [])
        finally:
            con.close()

    def test_o_progresso_grava_e_a_resposta_diz_se_e_para_parar(self):
        token, _ = self.maquina_com_token()
        self.enfileirar_tarefa()
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        r = self.como_agente(token, "/agente/resultado",
                             {"tipo": "progresso", "id": "d:1",
                              "frase": "rodando os testes",
                              "linhas": [[1, "abrindo a copia"]]})
        self.assertEqual(r.status, 200)
        self.assertFalse(json.loads(r.corpo)["pare"])
        con = banco.conectar()
        try:
            self.assertEqual(len(banco.linhas_da_tarefa("d:1", con=con)), 1)
        finally:
            con.close()

    def test_o_pedido_de_parada_desce_na_resposta_do_progresso(self):
        """O botao Parar viaja no proximo alo do agente. Nao ha conexao nova,
        e a latencia disso e o que a tela precisa dizer."""
        cookies, csrf = self.sessao_e_token()
        token, _ = self.maquina_com_token()
        self.enfileirar_tarefa()
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        parar = self.pedir("/api/tarefas/parar", "POST", {"id": "d:1"},
                           cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(parar.status, 200)
        r = self.como_agente(token, "/agente/resultado",
                             {"tipo": "progresso", "id": "d:1"})
        self.assertTrue(json.loads(r.corpo)["pare"])

    def test_o_desfecho_fecha_a_tarefa(self):
        token, _ = self.maquina_com_token()
        self.enfileirar_tarefa()
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        r = self.como_agente(token, "/agente/resultado",
                             {"tipo": "desfecho", "id": "d:1", "estado": "ok",
                              "ramo": "hub/env-drift-1", "resumo": "pronto",
                              "diff": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
                              "rodadas": 3, "custo_usd": 0.5})
        self.assertEqual(r.status, 200)
        con = banco.conectar()
        try:
            t = banco.tarefa("d:1", con=con)
        finally:
            con.close()
        self.assertEqual(t["estado"], "ok")
        self.assertEqual(t["ramo"], "hub/env-drift-1")

    def test_tipo_desconhecido_e_recusado(self):
        token, _ = self.maquina_com_token()
        self.enfileirar_tarefa()
        r = self.como_agente(token, "/agente/resultado",
                             {"tipo": "qualquer", "id": "d:1"})
        self.assertEqual(r.status, 400)

    # ------------------------------------------------------ as rotas do dono

    def test_as_quatro_rotas_de_tarefa_exigem_sessao(self):
        self.assertEqual(self.pedir("/api/tarefas").status, 401)
        for caminho in ("/api/tarefas/aprovar", "/api/tarefas/parar",
                        "/api/tarefas/cor"):
            with self.subTest(caminho=caminho):
                self.assertEqual(self.pedir(caminho, "POST", {}).status, 401)

    def test_aprovar_com_sessao_e_sem_anti_csrf_e_403(self):
        self.enfileirar_tarefa(verde=False)
        r = self.pedir("/api/tarefas/aprovar", "POST", {"id": "d:1"},
                       cookies=self.com_sessao(),
                       cabecalhos={"X-Token": "a" * 64})
        self.assertEqual(r.status, 403)

    def test_aprovar_deixa_a_tarefa_vermelha_descer(self):
        cookies, csrf = self.sessao_e_token()
        token, _ = self.maquina_com_token()
        self.enfileirar_tarefa(verde=False)
        antes = self.como_agente(token, "/agente/relatorio", {"projetos": []})
        self.assertIsNone(json.loads(antes.corpo)["tarefa"])
        r = self.pedir("/api/tarefas/aprovar", "POST", {"id": "d:1"},
                       cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(r.status, 200)
        depois = self.como_agente(token, "/agente/relatorio", {"projetos": []})
        self.assertIsNotNone(json.loads(depois.corpo)["tarefa"])

    def test_repintar_publicar_de_verde_e_recusado_com_frase_em_portugues(self):
        cookies, csrf = self.sessao_e_token()
        r = self.pedir("/api/tarefas/cor", "POST",
                       {"regra": "publicar", "cor": "verde"},
                       cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(r.status, 409)
        self.assertIn("nunca anda sozinha", json.loads(r.corpo)["erro"])

    def test_repintar_uma_regra_comum_funciona_nos_dois_sentidos(self):
        cookies, csrf = self.sessao_e_token()
        for cor in ("verde", "vermelho"):
            r = self.pedir("/api/tarefas/cor", "POST",
                           {"regra": "env_drift", "cor": cor},
                           cookies=cookies, cabecalhos={"X-Token": csrf})
            self.assertEqual(r.status, 200, cor)

    def test_a_lista_de_tarefas_diz_quando_foi_medida(self):
        """"Nao sei" e "zero" sao estados diferentes, e o carimbo e o que
        permite a tela distinguir os dois."""
        self.enfileirar_tarefa()
        corpo = json.loads(self.pedir("/api/tarefas",
                                      cookies=self.com_sessao()).corpo)
        self.assertIn("medido_em", corpo)
        self.assertIn("publicar", corpo["nunca_verde"])
        self.assertEqual([t["id"] for t in corpo["tarefas"]], ["d:1"])

    def test_a_lista_nao_carrega_o_diff_e_a_tarefa_carrega(self):
        token, _ = self.maquina_com_token()
        self.enfileirar_tarefa()
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        self.como_agente(token, "/agente/resultado",
                         {"tipo": "desfecho", "id": "d:1", "estado": "ok",
                          "diff": "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"})
        cookies = self.com_sessao()
        lista = json.loads(self.pedir("/api/tarefas", cookies=cookies).corpo)
        self.assertNotIn("diff", lista["tarefas"][0])
        uma = json.loads(self.pedir("/api/tarefas?id=d:1",
                                    cookies=cookies).corpo)["tarefa"]
        self.assertIn("diff", uma)
        self.assertTrue(uma["frases_do_diff"])

    def test_autorizar_maquina_de_outra_conta_e_recusado(self):
        cookies, csrf = self.sessao_e_token()
        _token, mid = self.maquina_com_token(autorizada=False)
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("outro@teste.local", con=con)
            con.execute("UPDATE maquina SET usuario_id = ? WHERE id = ?",
                        (outro, mid))
            con.commit()
        finally:
            con.close()
        r = self.pedir("/api/maquinas/autorizar", "POST",
                       {"id": mid, "ligado": True},
                       cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(r.status, 404)

    def test_tarefa_muda_ha_muito_tempo_vira_falha_e_nao_fica_rodando(self):
        """Agente que morreu no meio nao pode deixar a tela dizendo
        "trabalhando" para sempre. Painel que mente e pior que painel vazio."""
        token, mid = self.maquina_com_token()
        self.enfileirar_tarefa()
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        con = banco.conectar()
        try:
            velho = (datetime.now(timezone.utc)
                     - timedelta(minutes=60)).isoformat(timespec="seconds")
            con.execute("UPDATE fila SET visto_em = ?, iniciado_em = ?"
                        " WHERE id = 'd:1'", (velho, velho))
            con.commit()
        finally:
            con.close()
        self.pedir("/api/tarefas", cookies=self.com_sessao())
        con = banco.conectar()
        try:
            t = banco.tarefa("d:1", con=con)
        finally:
            con.close()
        self.assertEqual(t["estado"], "falha")
        self.assertIn("noticia", t["erro"])


class OConsumoDaSemana(BaseServidorDeVerdade):
    """A rota que torna a semana de observacao uma medicao."""

    def test_o_consumo_exige_sessao(self):
        self.assertEqual(self.pedir("/api/consumo").status, 401)

    def test_com_sessao_devolve_a_forma_completa(self):
        corpo = json.loads(self.pedir("/api/consumo",
                                      cookies=self.com_sessao()).corpo)
        for chave in ("por_dia", "por_projeto", "por_regra", "total",
                      "medido_em", "dias", "custo_em_reais"):
            self.assertIn(chave, corpo)
        self.assertEqual(corpo["dias"], banco.DIAS_DE_CONSUMO)

    def test_semana_vazia_devolve_zeros_e_o_carimbo_e_nao_um_corpo_vazio(self):
        corpo = json.loads(self.pedir("/api/consumo",
                                      cookies=self.com_sessao()).corpo)
        self.assertEqual(corpo["total"]["sessoes"], 0)
        self.assertTrue(corpo["medido_em"])

    def test_o_dinheiro_vem_rotulado_como_referencia(self):
        """Com assinatura, o recurso escasso e cota. Chamar o custo em dolar de
        "quanto o painel consumiu" seria o numero errado com cara de certo."""
        corpo = json.loads(self.pedir("/api/consumo",
                                      cookies=self.com_sessao()).corpo)
        self.assertEqual(corpo["o_que_e_escasso"], "sessoes e rodadas")
        self.assertTrue(corpo["custo_em_reais"].startswith("R$ "))

    def test_uma_janela_absurda_e_aparada(self):
        """Sem teto, uma janela de dez anos pedida pela barra de endereco vira
        varredura completa da fila a cada recarga."""
        corpo = json.loads(self.pedir("/api/consumo?dias=99999",
                                      cookies=self.com_sessao()).corpo)
        self.assertEqual(corpo["dias"], 90)
        corpo = json.loads(self.pedir("/api/consumo?dias=abacaxi",
                                      cookies=self.com_sessao()).corpo)
        self.assertEqual(corpo["dias"], banco.DIAS_DE_CONSUMO)


class OConectadorNoServidorDeVerdade(BaseServidorDeVerdade):
    """A rota que entrega o `conectador.py` com o codigo dentro (etapa A3).

    Ler a tabela de rotas nao basta e ja nao bastou aqui: a classificacao e a
    trava real ja divergiram neste repositorio. Estes casos saem pelo soquete.
    """

    CAMINHO = "/api/conectador"

    def test_sem_sessao_nao_sai_nada(self):
        r = self.pedir(self.CAMINHO, "POST", {})
        self.assertEqual(401, r.status)
        self.assertNotIn("DERVS:CODIGO", r.corpo)
        self.assertNotIn("schtasks", r.corpo)

    def test_com_sessao_e_sem_anti_csrf_e_recusado(self):
        """Um POST que CRIA codigo, acionavel de outro site, queima codigos."""
        r = self.pedir(self.CAMINHO, "POST", {}, cookies=self.com_sessao())
        self.assertEqual(403, r.status)

    def test_com_sessao_e_sem_origem_e_recusado(self):
        cookies, token = self.sessao_e_token()
        r = self.pedir(self.CAMINHO, "POST", {}, cookies=cookies,
                       com_origem=False, cabecalhos={"X-Token": token})
        self.assertEqual(403, r.status)

    def _baixar(self):
        cookies, token = self.sessao_e_token()
        return self.pedir(self.CAMINHO, "POST", {}, cookies=cookies,
                          cabecalhos={"X-Token": token})

    def test_com_sessao_sai_o_arquivo_com_codigo_e_endereco(self):
        r = self._baixar()
        self.assertEqual(200, r.status)
        achado = re.search(r'^CODIGO = "(\d{6})"', r.corpo, re.M)
        self.assertIsNotNone(achado, "o codigo de seis digitos nao foi injetado")
        alvo = re.search(r'^ALVO = "([^"]+)"', r.corpo, re.M)
        self.assertIsNotNone(alvo, "o endereco do painel nao foi injetado")
        self.assertEqual("http://127.0.0.1:%d" % self.porta, alvo.group(1))

    def test_o_que_sai_e_python_valido(self):
        """Injecao que quebra o arquivo entrega um erro de sintaxe ao dono."""
        import ast
        ast.parse(self._baixar().corpo)

    def test_o_navegador_nao_renderiza_o_arquivo(self):
        r = self._baixar()
        tipo = (r.cabecalhos.get("Content-Type") or "").lower()
        self.assertNotIn("text/html", tipo)
        self.assertIn("attachment", (r.cabecalhos.get("Content-Disposition") or ""))

    def test_o_codigo_foi_aberto_PARA_QUEM_PEDIU(self):
        """Um codigo aberto na conta errada poe a maquina de um no painel do outro."""
        r = self._baixar()
        codigo = re.search(r'^CODIGO = "(\d{6})"', r.corpo, re.M).group(1)
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("outra@teste.local", con=con)
            linhas = con.execute(
                "SELECT usuario_id FROM pareamento WHERE usado_em IS NULL"
            ).fetchall()
        finally:
            con.close()
        donos = {l[0] for l in linhas}
        self.assertIn(self.uid, donos)
        self.assertNotIn(outro, donos)
        # E o codigo vale de verdade: quem o digita vira maquina DESTA conta.
        self.assertTrue(banco.usar_pareamento(codigo, "pc-de-teste"))

    def test_dois_pedidos_dao_codigos_diferentes(self):
        um = re.search(r'^CODIGO = "(\d{6})"', self._baixar().corpo, re.M).group(1)
        dois = re.search(r'^CODIGO = "(\d{6})"', self._baixar().corpo, re.M).group(1)
        self.assertNotEqual(um, dois)

    def test_o_servidor_nao_ganhou_atributo_conectador(self):
        """Importar o conectador arrastaria `tkinter` para dentro do servidor."""
        self.assertFalse(hasattr(servir, "conectador"))
        self.assertNotIn("conectador", getattr(servir, "__dict__", {}))


class OEnderecoDoServidorNoServidorDeVerdade(BaseServidorDeVerdade):
    """A porta 3: o painel passa a BUSCAR uma URL que o usuario digitou.

    E a superficie classica de pedir ao servidor que bata em endereco interno,
    entao cada faixa e provada UMA A UMA. Nada aqui bate na internet: a peneira
    recusa antes, e o unico caso que chegaria a rede usa um duble de
    `mede_site`.
    """

    GUARDAR = "/api/enderecos/guardar"
    LER = "/api/enderecos"

    def setUp(self):
        super().setUp()
        # `mede_site` bate na rede de verdade. A CI nao tem internet garantida,
        # e um teste que depende dela falha por motivo errado — e teste que
        # falha por motivo errado e desligado em duas semanas.
        self._medir = servir.coletar_github.mede_site
        servir.coletar_github.mede_site = lambda url: {
            "url": url, "ok": True, "codigo": 200, "erro": "", "ms": 12,
            "tentativas": 1}
        self.addCleanup(setattr, servir.coletar_github, "mede_site", self._medir)
        # `host_publico` faz DNS DE VERDADE. Aqui ele so pode dizer sim: os
        # casos que provam a recusa por resolucao trocam este duble sozinhos, e
        # os vinte enderecos internos sao barrados por `url_segura`, que e pura
        # e nao toca na rede.
        self._resolver = servir.coletar_github.host_publico
        servir.coletar_github.host_publico = lambda h: True
        self.addCleanup(setattr, servir.coletar_github, "host_publico",
                        self._resolver)
        con = banco.conectar()
        try:
            con.execute("DELETE FROM endereco_producao")
            con.commit()
        finally:
            con.close()

    def guardar(self, projeto, url, cookies=None, token=None, com_origem=True):
        if cookies is None:
            cookies, token = self.sessao_e_token()
        cab = {} if token is None else {"X-Token": token}
        return self.pedir(self.GUARDAR, "POST", {"projeto": projeto, "url": url},
                          cookies=cookies, com_origem=com_origem, cabecalhos=cab)

    # ------------------------------------------------------------ as travas
    def test_sem_sessao_nao_grava_e_nao_le(self):
        self.assertEqual(401, self.pedir(self.GUARDAR, "POST",
                                         {"projeto": "x", "url": "https://a.com"}).status)
        self.assertEqual(401, self.pedir(self.LER).status)

    def test_com_sessao_e_sem_anti_csrf_e_recusado(self):
        cookies = self.com_sessao()
        r = self.pedir(self.GUARDAR, "POST", {"projeto": "x", "url": "https://a.com"},
                       cookies=cookies)
        self.assertEqual(403, r.status)

    def test_sem_origem_e_recusado(self):
        cookies, token = self.sessao_e_token()
        r = self.guardar("x", "https://exemplo.com.br", cookies, token,
                         com_origem=False)
        self.assertEqual(403, r.status)

    # ---------------------------------------------------- a peneira, faixa a faixa
    #
    # Cada uma destas ja foi um SSRF de verdade em algum projeto. A faixa CGNAT
    # (100.64/10) esteve aberta NESTE repositorio ate 29/08/2026, com a suite
    # inteira verde: ela nao e um caso a mais, e o caso que prova que a lista
    # sem teste envelhece.
    INTERNOS = [
        "http://localhost/",
        "http://localhost:8080/",
        "http://127.0.0.1/",
        "http://127.1.2.3/",
        "http://10.0.0.5/",
        "http://172.16.9.9/",
        "http://172.31.255.254/",
        "http://192.168.1.10/",
        "http://169.254.169.254/",          # o metadado da nuvem
        "http://[::1]/",
        "http://100.64.5.5/",               # CGNAT
        "http://100.127.255.254/",          # CGNAT, a outra ponta
        "http://[::ffff:10.0.0.1]/",        # IPv4 mapeado em IPv6
        "http://[::ffff:100.64.5.5]/",      # CGNAT mapeado
        "http://0.0.0.0/",
        "http://meu-pc.local/",
        "http://algo.localhost/",
        "ftp://exemplo.com.br/",            # nem http nem https
        "file:///etc/passwd",
        "https://",                         # sem host nenhum
    ]

    def test_cada_faixa_interna_e_recusada_uma_a_uma(self):
        cookies, token = self.sessao_e_token()
        for url in self.INTERNOS:
            with self.subTest(url=url):
                r = self.guardar("projeto-x", url, cookies, token)
                self.assertEqual(400, r.status, url)
                self.assertIn("rede privada", r.corpo)
                # E NADA foi gravado: recusar depois de gravar e gravar.
                corpo = self.pedir(self.LER, cookies=cookies).corpo
                self.assertEqual({}, json.loads(corpo)["enderecos"], url)

    def test_a_peneira_usada_e_a_do_coletor_e_nao_uma_copia(self):
        """Uma segunda copia dessa peneira ja matou o drift em silencio, com
        926 testes verdes. Este caso amarra a identidade: sabotar a do coletor
        tem de derrubar a rota."""
        import coletar_github
        self.assertIs(servir.coletar_github, coletar_github)
        antes = coletar_github.url_segura
        coletar_github.url_segura = lambda u: False
        self.addCleanup(setattr, coletar_github, "url_segura", antes)
        cookies, token = self.sessao_e_token()
        r = self.guardar("projeto-x", "https://exemplo.com.br", cookies, token)
        self.assertEqual(400, r.status,
                         "a rota nao esta usando a peneira do coletor")

    def test_nome_que_resolve_para_dentro_e_recusado(self):
        """`url_segura` nao faz DNS de proposito. Quem resolve e `host_publico`,
        e um nome publico apontando para 127.0.0.1 e o SSRF classico."""
        import coletar_github
        antes = coletar_github.host_publico
        coletar_github.host_publico = lambda h: False
        self.addCleanup(setattr, coletar_github, "host_publico", antes)
        cookies, token = self.sessao_e_token()
        r = self.guardar("projeto-x", "https://parece-publico.com.br", cookies, token)
        self.assertEqual(400, r.status)
        corpo = self.pedir(self.LER, cookies=cookies).corpo
        self.assertEqual({}, json.loads(corpo)["enderecos"])

    def test_o_redirecionamento_nunca_e_seguido(self):
        """A defesa mais forte possivel contra o pulo de publico para interno:
        nao seguir nenhum. A prova e estrutural — o abridor de `mede_site` monta
        `_SemRedirecionar`, e ela devolve None."""
        import coletar_github
        self.assertIsNone(
            coletar_github._SemRedirecionar().redirect_request(
                None, None, 302, "", {}, "http://10.0.0.1/"))

    # ------------------------------------------------------- o caminho feliz
    def test_endereco_publico_e_gravado_e_medido(self):
        cookies, token = self.sessao_e_token()
        r = self.guardar("loja", "https://exemplo.com.br", cookies, token)
        self.assertEqual(200, r.status, r.corpo)
        d = json.loads(r.corpo)
        self.assertTrue(d["guardado"])
        self.assertIs(True, d["ok"])
        self.assertTrue(d["medido_em"], "todo numero medido leva carimbo")
        corpo = self.pedir(self.LER, cookies=cookies).corpo
        self.assertEqual({"loja": "https://exemplo.com.br"},
                         json.loads(corpo)["enderecos"])

    def test_nao_deu_para_medir_NAO_e_fora_do_ar(self):
        """A invariante do proprio `mede_site`: `ok` como None e o quarto
        estado, e apagar essa diferenca e o defeito que este painel existe para
        nao ter."""
        servir.coletar_github.mede_site = lambda url: {
            "url": url, "ok": None, "codigo": 0, "erro": "nao_resolveu",
            "ms": 0, "tentativas": 0}
        cookies, token = self.sessao_e_token()
        d = json.loads(self.guardar("loja", "https://exemplo.com.br",
                                    cookies, token).corpo)
        self.assertIsNone(d["ok"])
        self.assertIsNot(False, d["ok"], "None nao pode virar False no caminho")
        self.assertTrue(d["guardado"], "nao medir nao desfaz a gravacao")

    def test_apagar_o_endereco_nao_bate_em_lugar_nenhum(self):
        def explodir(url):
            raise AssertionError("apagar nao pode medir nada")

        cookies, token = self.sessao_e_token()
        self.guardar("loja", "https://exemplo.com.br", cookies, token)
        servir.coletar_github.mede_site = explodir
        r = self.guardar("loja", "", cookies, token)
        self.assertEqual(200, r.status, r.corpo)
        corpo = self.pedir(self.LER, cookies=cookies).corpo
        self.assertEqual({}, json.loads(corpo)["enderecos"])

    def test_projeto_vazio_e_recusado(self):
        cookies, token = self.sessao_e_token()
        r = self.guardar("   ", "https://exemplo.com.br", cookies, token)
        self.assertEqual(400, r.status)

    def test_o_endereco_de_outra_conta_nao_e_legivel(self):
        cookies, token = self.sessao_e_token()
        self.guardar("loja", "https://minha.com.br", cookies, token)
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("vizinho@teste.local", con=con)
            banco.guardar_endereco_de_producao(outro, "loja",
                                               "https://do-vizinho.com.br", con=con)
        finally:
            con.close()
        corpo = self.pedir(self.LER, cookies=cookies).corpo
        self.assertEqual({"loja": "https://minha.com.br"},
                         json.loads(corpo)["enderecos"],
                         "o endereco do vizinho vazou para esta sessao")

    def test_o_teto_por_origem_tem_balcao_PROPRIO(self):
        """Misturar balcoes tranca a maquina legitima, e isso ja aconteceu duas
        vezes nesta casa. Gastar o teto do endereco nao pode fechar a cortina."""
        cookies, token = self.sessao_e_token()
        for _ in range(servir.Hub.TETO_DE_ENDERECOS + 2):
            self.guardar("loja", "https://exemplo.com.br", cookies, token)
        r = self.guardar("loja", "https://exemplo.com.br", cookies, token)
        self.assertEqual(429, r.status, "o teto do endereco nao segurou")
        # E a cortina continua de pe para quem chega.
        self.assertEqual(204, self.pedir("/entrada", "POST",
                                 {"combinacao": self.combinacao}).status)


class AContaDoGithubNoServidorDeVerdade(BaseServidorDeVerdade):
    """A porta 2. O caso que da nome a esta classe e um so:

        O `installation_id` chega pela QUERY STRING, e a documentacao do GitHub
        avisa que qualquer um pode bater na setup URL com um numero forjado.
        Aceita-lo por ter vindo na URL e gravar o que o visitante escreveu.

    Nada aqui bate no GitHub: a CI nao tem credencial nenhuma, e um teste que
    dependesse disso ficaria vermelho por motivo errado.
    """

    IDA = "/api/github/instalar"
    VOLTA = "/github/instalado"
    ESTADO = "/api/github"

    def setUp(self):
        super().setUp()
        self._slug = servir.APP_DO_GITHUB
        servir.APP_DO_GITHUB = "dervs-de-teste"
        self.addCleanup(setattr, servir, "APP_DO_GITHUB", self._slug)
        self._confirmar = servir.github_app.confirmar_instalacao
        self.addCleanup(setattr, servir.github_app, "confirmar_instalacao",
                        self._confirmar)
        # Por padrao o GitHub CONFIRMA. Cada caso que precisa do contrario
        # troca este duble, e o que ele devolve nunca carrega segredo.
        # O duble devolve o `account` porque e ELE que prova a posse: a conta
        # de teste esta amarrada ao id "4242" do GitHub (ver o andaime).
        servir.github_app.confirmar_instalacao = \
            lambda app_id, chave, inst, **k: {"id": int(inst), "app_id": 1,
                                              "account": {"id": 4242,
                                                          "login": "dono"}}
        con = banco.conectar()
        try:
            con.execute("DELETE FROM instalacao_github")
            con.commit()
        finally:
            con.close()

    def gravada(self, usuario_id=None):
        return banco.instalacao_do_github(
            self.uid if usuario_id is None else usuario_id)

    def selo(self, usuario_id=None, minutos=30):
        ate = int(time.time()) + minutos * 60
        return servir.Hub._selo_da_instalacao(
            self.uid if usuario_id is None else usuario_id, ate)

    def voltar(self, selo, instalacao):
        """A volta do GitHub, com o cookie da cortina junto.

        A rota e `cortina`, e o navegador que volta do GitHub carrega esse
        cookie: e um salto de pagina de primeiro nivel, e o cookie e
        `SameSite=Lax`. Sem ele a rota responde 404 — a MESMA resposta de rota
        inexistente, de proposito: quem nao passou pela cortina nao pode nem
        descobrir que esta porta existe.
        """
        return self.pedir("%s?state=%s&installation_id=%s"
                          % (self.VOLTA, urllib.parse.quote(selo), instalacao),
                          cookies=self.abrir_cortina())

    def test_a_volta_sem_a_cortina_e_indistinguivel_de_rota_inexistente(self):
        r = self.pedir("%s?state=%s&installation_id=424242"
                       % (self.VOLTA, urllib.parse.quote(self.selo())))
        self.assertEqual(404, r.status)
        self.assertIsNone(self.gravada(), "gravou sem passar pela cortina")

    # ------------------------------------------------------------ a ida
    def test_a_ida_sem_sessao_e_recusada(self):
        self.assertEqual(401, self.pedir(self.IDA, "POST", {}).status)

    def test_a_ida_sem_anti_csrf_e_recusada(self):
        r = self.pedir(self.IDA, "POST", {}, cookies=self.com_sessao())
        self.assertEqual(403, r.status)

    def test_a_ida_devolve_o_endereco_com_o_selo(self):
        cookies, token = self.sessao_e_token()
        r = self.pedir(self.IDA, "POST", {}, cookies=cookies,
                       cabecalhos={"X-Token": token})
        self.assertEqual(200, r.status, r.corpo)
        url = json.loads(r.corpo)["url"]
        self.assertIn("github.com/apps/dervs-de-teste/installations/new", url)
        self.assertIn("state=", url)
        selo = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["state"][0]
        self.assertEqual(self.uid, servir.Hub._dono_do_selo(selo))

    def test_sem_app_registrado_a_porta_diz_que_nao_existe(self):
        """Falha FECHADA: melhor nao ter porta do que ter porta que leva a um
        endereco que nao abre."""
        servir.APP_DO_GITHUB = ""
        cookies, token = self.sessao_e_token()
        r = self.pedir(self.IDA, "POST", {}, cookies=cookies,
                       cabecalhos={"X-Token": token})
        self.assertEqual(404, r.status)

    # ---------------------------------------------------------- a volta
    def test_installation_id_na_query_SEM_selo_valido_nao_grava_nada(self):
        """O caso central. O numero na URL nao e prova de coisa nenhuma."""
        r = self.voltar("mentira.999.abcdef", "12345")
        self.assertEqual(302, r.status)
        self.assertIn("nao-deu", r.cabecalhos.get("Location"))
        self.assertIsNone(self.gravada())

    def test_selo_sem_assinatura_nao_grava(self):
        self.assertIsNone(self.gravada())
        r = self.voltar("%d.%d." % (self.uid, int(time.time()) + 600), "12345")
        self.assertIn("nao-deu", r.cabecalhos.get("Location"))
        self.assertIsNone(self.gravada())

    def test_selo_de_OUTRO_usuario_nao_grava_na_minha_conta(self):
        """O selo diz DE QUEM e a volta, e ele nao pode escrever na conta ao
        lado. Para o caso ficar completo, a outra conta tem GitHub proprio: sem
        isso a conferencia de posse recusaria por outro motivo, e o teste
        provaria a trava errada."""
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("outro-c2@teste.local", con=con)
            banco.ligar_github(outro, "8888", con=con)
            con.commit()
        finally:
            con.close()
        servir.github_app.confirmar_instalacao =             lambda app_id, chave, inst, **k: {"id": int(inst), "app_id": 1,
                                              "account": {"id": 8888,
                                                          "login": "outro"}}
        self.voltar(self.selo(outro), "777")
        self.assertIsNone(self.gravada(self.uid),
                          "a instalacao caiu na conta errada")
        self.assertEqual("777", self.gravada(outro))

    def test_selo_vencido_nao_grava(self):
        r = self.voltar(self.selo(minutos=-1), "12345")
        self.assertIn("nao-deu", r.cabecalhos.get("Location"))
        self.assertIsNone(self.gravada())

    def test_selo_valido_mas_a_API_nao_confirma_NAO_GRAVA(self):
        """Este e o unico caso que prova que o parametro da URL nao e a prova.

        Sem ele, um selo valido do proprio dono bastaria para gravar qualquer
        numero — inclusive a instalacao de outra pessoa, colada na URL.
        """
        servir.github_app.confirmar_instalacao = lambda *a, **k: None
        r = self.voltar(self.selo(), "999999")
        self.assertEqual(302, r.status)
        self.assertIn("nao-deu", r.cabecalhos.get("Location"))
        self.assertIsNone(self.gravada())

    def test_selo_valido_E_API_confirma_grava_PARA_AQUELE_usuario(self):
        r = self.voltar(self.selo(), "424242")
        self.assertEqual(302, r.status)
        self.assertIn("ligado", r.cabecalhos.get("Location"))
        self.assertEqual("424242", self.gravada())

    def test_o_recado_da_volta_vai_ANTES_do_fragmento(self):
        """`/#/conectar?github=x` poe o parametro DENTRO do fragmento, e
        `location.search` sai vazio: a tela nunca le o recado. O 302 fica
        certo e a tela fica muda — achado clicando, nao lendo."""
        for selo, esperado in ((self.selo(), "ligado"),
                               ("forjado.1.abc", "nao-deu")):
            with self.subTest(esperado=esperado):
                destino = self.voltar(selo, "424242").cabecalhos.get("Location")
                self.assertIn("?github=" + esperado, destino)
                self.assertLess(destino.index("?"), destino.index("#"),
                                "a query ficou depois do # e a tela nao le: "
                                + destino)

    # ------------------------------------------------ a POSSE da instalacao
    #
    # O achado das duas revisoes de 01/09/2026, e o mais grave da esteira:
    # `confirmar_instalacao` prova que a instalacao EXISTE e que e deste App.
    # NAO prova que ela e SUA. O `installation_id` e publico e sequencial.

    def test_instalacao_de_OUTRA_pessoa_nao_gruda_na_minha_conta(self):
        """O ataque inteiro, escrito: peco o MEU selo, e chamo a volta com o
        numero DA OUTRA PESSOA, iterando ate acertar."""
        servir.github_app.confirmar_instalacao = \
            lambda app_id, chave, inst, **k: {"id": int(inst), "app_id": 1,
                                              "account": {"id": 9999,
                                                          "login": "outra-pessoa"}}
        r = self.voltar(self.selo(), "555555")
        self.assertIn("nao-deu", r.cabecalhos.get("Location"))
        self.assertIsNone(self.gravada(),
                          "gravou a instalacao de outra pessoa na minha conta")

    def test_instalacao_sem_account_nao_grava(self):
        """Falha fechada: sem saber de quem e, nao e de ninguem."""
        servir.github_app.confirmar_instalacao = \
            lambda *a, **k: {"id": 424242, "app_id": 1}
        self.voltar(self.selo(), "424242")
        self.assertIsNone(self.gravada())

    def test_instalacao_de_ORGANIZACAO_e_recusada_e_isso_e_deliberado(self):
        """Divida NOMEADA, e nao esquecimento: provar que alguem e membro de uma
        organizacao exige o fluxo de token DO USUARIO, que e outra etapa.

        Recusar quem tem direito e um incomodo; aceitar quem nao tem e uma
        porta. Este caso existe para que a escolha nao seja redescoberta como
        se fosse um defeito.
        """
        servir.github_app.confirmar_instalacao = \
            lambda *a, **k: {"id": 424242, "app_id": 1,
                             "account": {"id": 777, "login": "minha-org",
                                         "type": "Organization"}}
        self.voltar(self.selo(), "424242")
        self.assertIsNone(self.gravada())

    def test_numero_ja_gravado_por_outra_conta_nao_e_roubado(self):
        """A segunda tranca, no banco. A primeira e a conferencia do dono."""
        con = banco.conectar()
        try:
            vizinho = banco.criar_usuario("vizinho-posse@teste.local", con=con)
            banco.guardar_instalacao_do_github(vizinho, "313131", con=con)
            con.commit()
        finally:
            con.close()
        r = self.voltar(self.selo(), "313131")
        self.assertIn("nao-deu", r.cabecalhos.get("Location"))
        self.assertIsNone(self.gravada(self.uid))
        self.assertEqual("313131", self.gravada(vizinho))

    # ------------------------------------------------------- a leitura
    def test_o_estado_sem_sessao_e_recusado(self):
        self.assertEqual(401, self.pedir(self.ESTADO).status)

    def test_uma_conta_nao_le_a_instalacao_da_outra(self):
        con = banco.conectar()
        try:
            outro = banco.criar_usuario("vizinho-c2@teste.local", con=con)
            banco.guardar_instalacao_do_github(outro, "999888", con=con)
        finally:
            con.close()
        cookies = self.com_sessao()
        d = json.loads(self.pedir(self.ESTADO, cookies=cookies).corpo)
        self.assertEqual("", d["instalacao"],
                         "a instalacao do vizinho vazou para esta sessao")
        self.assertTrue(d["lido_em"], "toda leitura leva carimbo")

    def test_nenhuma_resposta_desta_porta_carrega_segredo(self):
        """Chave privada e token nunca saem por HTTP. A guarda e por forma."""
        cookies, token = self.sessao_e_token()
        corpos = [self.pedir(self.ESTADO, cookies=cookies).corpo,
                  self.pedir(self.IDA, "POST", {}, cookies=cookies,
                             cabecalhos={"X-Token": token}).corpo,
                  self.voltar(self.selo(), "424242").corpo]
        for corpo in corpos:
            for proibido in ("BEGIN", "PRIVATE KEY", "ghs_", "ghp_",
                             "DERVS_COFRE", "DERVS_GITHUB_APP_KEY"):
                self.assertNotIn(proibido, corpo, proibido)


class OEspacoDosCodigosNaoSeEnche(BaseServidorDeVerdade):
    """`codigo_hash` e PRIMARY KEY GLOBAL, e nada era apagado nunca.

    Duas travas nasceram do achado da revisao de seguranca de 01/09/2026: um
    teto de CRIACAO por origem, com balcao proprio, e a limpeza do vencido
    antes de sortear. Sem elas, quem gerasse codigos em laco enchia um espaco de
    um milhao compartilhado por todas as contas — e trancava o dono junto.
    """

    def test_o_teto_de_criacao_vale_para_as_DUAS_portas(self):
        """O conectador e o botao 'Gerar o numero' criam o mesmo tipo de
        estado. Um teto so numa delas e uma porta aberta ao lado da fechada."""
        cookies, token = self.sessao_e_token()
        cab = {"X-Token": token}
        for _ in range(servir.Hub.TETO_DE_CODIGOS + 2):
            self.pedir("/api/maquinas/parear", "POST", {}, cookies=cookies,
                       cabecalhos=cab)
        self.assertEqual(503, self.pedir("/api/maquinas/parear", "POST", {},
                                         cookies=cookies, cabecalhos=cab).status)
        self.assertEqual(503, self.pedir("/api/conectador", "POST", {},
                                         cookies=cookies, cabecalhos=cab).status)

    def test_gastar_o_teto_de_codigos_NAO_tranca_a_cortina(self):
        """Balcao proprio. Misturar balcoes tranca o dono, e isso ja aconteceu
        duas vezes nesta casa."""
        cookies, token = self.sessao_e_token()
        for _ in range(servir.Hub.TETO_DE_CODIGOS + 2):
            self.pedir("/api/maquinas/parear", "POST", {}, cookies=cookies,
                       cabecalhos={"X-Token": token})
        self.assertEqual(204, self.pedir("/entrada", "POST",
                                         {"combinacao": self.combinacao}).status)

    def test_o_codigo_vencido_e_apagado_antes_de_sortear(self):
        cookies, token = self.sessao_e_token()
        con = banco.conectar()
        try:
            con.execute("DELETE FROM pareamento")
            con.commit()
            banco.abrir_pareamento(self.uid, "111111", banco.prazo(-60), con=con)
            con.commit()
        finally:
            con.close()
        self.pedir("/api/maquinas/parear", "POST", {}, cookies=cookies,
                   cabecalhos={"X-Token": token})
        con = banco.conectar()
        try:
            vencidos = con.execute(
                "SELECT COUNT(*) FROM pareamento WHERE expira_em < ?",
                (banco.agora(),)).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(0, vencidos, "o codigo vencido continuou ocupando vaga")



# ---------------------------------------------------------------------------
# O CORPO QUE NINGUEM LEU, E O 401 QUE NUNCA CHEGOU.
#
# Sintoma: `test_servir.py` reprovava sozinho, em teste DIFERENTE a cada vez,
# com `ConnectionAbortedError: [WinError 10053]` lendo a linha de status --
# antes do primeiro byte da resposta. Medido em 02/09/2026: 2 falhas em 24
# corridas, 8,3%.
#
# A causa nao e do teste. `Hub.protocol_version` e HTTP/1.0, entao o soquete
# fecha depois de TODA resposta. E quem recusa um POST (401, 403, 404, 500)
# devolve antes de qualquer rota rodar, e as rotas sao os unicos lugares que
# leem `rfile`: recusa = corpo INTOCADO. Fechar um soquete com bytes por ler
# no buffer de recepcao faz o sistema mandar um RST em vez do FIN -- e o RST
# DESCARTA a resposta que ja estava no buffer do outro lado. A resposta foi
# escrita, viajou, e morreu a um passo de ser lida.
#
# Fora do teste isso e pior: e o navegador de quem usa o painel levando
# "conexao perdida" no lugar do 401 que o servidor montou com cuidado. Toda
# tela que trata `401` mostrando "sua sessao venceu" mostra, em vez disso, um
# erro de rede -- de vez em quando, sem padrao.
#
# POR QUE ESTE TESTE NAO SOBE SERVIDOR. A falha pelo soquete e probabilistica:
# medido em 02/09, corpo de 2 KB nunca falhou em 200 tentativas, e corpo de
# 256 KB falhou 5% das vezes. Um teste assim ficaria verde quase sempre com o
# defeito de pe -- exatamente o tipo de guarda que este repositorio recusa.
# Aqui o pedido inteiro entra por um soquete de mentira, e a pergunta e a do
# mecanismo, que e deterministica: sobrou byte por ler?
# ---------------------------------------------------------------------------


class _NaoFecha(io.BytesIO):
    """O handler fecha `rfile` ao terminar, e isso apagaria a prova."""

    def close(self):
        pass


class _SoqueteDeMentira:
    """O minimo que `BaseHTTPRequestHandler` pede de um soquete."""

    def __init__(self, entrada: bytes):
        self.entrada = _NaoFecha(entrada)
        self.saida = _NaoFecha()

    def makefile(self, modo, *a, **k):
        return self.entrada if "r" in modo else self.saida

    def sendall(self, dados):
        self.saida.write(dados)

    def close(self):
        pass


class OCorpoDoPedidoEDrenado(unittest.TestCase):
    """Depois de responder, nao pode sobrar byte por ler no soquete."""

    def pedir(self, caminho, corpo: bytes, metodo="POST", declarado=None):
        """Um pedido inteiro, por soquete de mentira.

        Devolve `(status, quanto sobrou por ler)`. `declarado` mente no
        `Content-Length` de proposito nos casos que precisam disso.
        """
        n = len(corpo) if declarado is None else declarado
        cru = ("%s %s HTTP/1.1\r\n"
               "Host: localhost:4777\r\n"
               "Content-Type: application/json\r\n"
               "Content-Length: %d\r\n\r\n" % (metodo, caminho, n)
               ).encode("ascii") + corpo
        s = _SoqueteDeMentira(cru)
        servir.Hub(s, ("127.0.0.1", 5555), object())
        resposta = s.saida.getvalue()
        primeira = resposta.split(b"\r\n", 1)[0].decode("latin1")
        self.assertTrue(
            primeira.startswith("HTTP/"),
            "o arreio quebrou: a resposta nao comeca com uma linha de status "
            "(%r). Sem isto os casos abaixo mediriam o nada." % primeira[:80])
        return primeira, len(s.entrada.read())

    def test_recusa_por_falta_de_sessao_drena_o_corpo(self):
        status, sobrou = self.pedir("/api/arquivar", b'{"projeto": "x"}')
        self.assertIn("401", status)
        self.assertEqual(
            0, sobrou,
            "o servidor respondeu %s e deixou %d bytes por ler. Ao fechar, "
            "isso vira RST e a resposta e DESCARTADA no cliente."
            % (status, sobrou))

    def test_rota_inexistente_drena_o_corpo(self):
        status, sobrou = self.pedir("/nao/existe/mesmo", b'{"a": 1}')
        self.assertIn("404", status)
        self.assertEqual(0, sobrou, "404 deixou %d bytes por ler." % sobrou)

    def test_corpo_maior_que_o_teto_da_rota_tambem_e_drenado(self):
        """O outro caminho: a rota LE, mas so ate o teto dela.

        `_corpo_json` faz `read(min(n, teto))`. Corpo acima do teto deixa o
        resto no soquete mesmo com a rota tendo rodado -- e o desfecho e o
        mesmo. Foi um destes que apareceu na medicao (5000 bytes num teto de
        4096).
        """
        corpo = b'{"codigo": "' + b"9" * 5000 + b'"}'
        status, sobrou = self.pedir("/entrada", corpo)
        self.assertEqual(
            0, sobrou,
            "a rota leu ate o teto e sobraram %d bytes por ler." % sobrou)

    def test_corpo_maior_que_uma_leitura_e_drenado_ATE_O_FIM(self):
        """O dreno le em pedacos de 64 KiB. Um pedaco nao pode bastar.

        POR QUE ESTE CASO EXISTE. Sem ele a guarda era cega para metade do
        defeito: sabotando o laco do dreno para parar depois do primeiro
        pedaco, os outros casos continuavam VERDES -- todo corpo deles cabia
        numa leitura so, e "leu alguma coisa" passava por "leu tudo". Achado
        sabotando, em 02/09/2026, nao lendo.

        200 KiB obrigam quatro voltas do laco.
        """
        corpo = b'{"lixo": "' + b"z" * (200 * 1024) + b'"}'
        status, sobrou = self.pedir("/api/arquivar", corpo)
        self.assertIn("401", status)
        self.assertEqual(
            0, sobrou,
            "sobraram %d bytes de um corpo de %d: o dreno parou no meio."
            % (sobrou, len(corpo)))

    def test_o_dreno_para_no_fim_do_fluxo_e_nao_no_numero_prometido(self):
        """Prometer 10 MB e mandar 5 bytes nao pode prender o dreno em laco.

        O QUE ESTE CASO PROVA E O QUE NAO PROVA. Ele prova que o dreno para
        quando a leitura devolve vazio, em vez de insistir ate completar o
        numero prometido. Ele NAO prova nada sobre um cliente de verdade que
        prometa e fique calado sem fechar: contra um soquete real a leitura
        BLOQUEIA, e nao ha prazo neste servidor -- nem pode haver, porque
        `/api/eventos` e uma conexao longa de proposito.

        Isso nao e exposicao nova. Toda rota que le corpo ja faz
        `read(min(n, teto))` sobre o mesmo soquete e ja fica presa do mesmo
        jeito; o dreno le no maximo o que a rota leria. `TETO_A_DRENAR`
        (8 MiB) limita o VOLUME, e `SEGUNDOS_PARA_DRENAR` (5) limita a ESPERA
        -- o prazo vale so para o dreno, e por isso nao toca `/api/eventos`,
        que a essa altura ja terminou.
        """
        pronto = threading.Event()

        def sozinho():
            try:
                self.pedir("/api/arquivar", b"12345", declarado=10_000_000)
            finally:
                pronto.set()

        t = threading.Thread(target=sozinho, daemon=True)
        t.start()
        self.assertTrue(
            pronto.wait(10),
            "o servidor ficou preso esperando um corpo que o cliente prometeu "
            "e nao mandou. Um pedido assim tranca uma thread para sempre.")

    def test_todo_verbo_drena_e_nao_so_GET_e_POST(self):
        """O dreno mora no laco do pedido, nao no despacho.

        A primeira versao vivia em `_despachar` e cobria GET e POST e mais
        nada: `do_HEAD` responde 405 por fora, e PUT/DELETE/PATCH caem no 501
        do `BaseHTTPRequestHandler` sem passar por rota nenhuma. Os tres
        deixavam 16 de 16 bytes por ler -- e levavam o mesmo RST. Achado pela
        revisao de 02/09/2026, contra uma mensagem de commit que dizia "num
        lugar so": era verdade para ROTA, nao para VERBO.
        """
        for metodo in ("HEAD", "PUT", "DELETE", "PATCH"):
            with self.subTest(metodo=metodo):
                status, sobrou = self.pedir(
                    "/api/arquivar", b'{"projeto": "x"}', metodo=metodo)
                self.assertEqual(
                    0, sobrou,
                    "%s respondeu %s e deixou %d bytes por ler."
                    % (metodo, status, sobrou))

    def test_o_dreno_para_no_teto_e_nao_le_o_que_o_cliente_prometeu(self):
        """Drenar sem teto e pagar a banda de quem ataca.

        `TETO_A_DRENAR` existia sem NENHUMA assercao: trocar
        `min(n, self.TETO_A_DRENAR)` por `n` deixava a suite verde, e o
        servidor passaria a ler os gigabytes que um cliente hostil declarasse.
        Achado por sabotagem na revisao de 02/09/2026.

        O teto e baixado aqui de proposito: o que se mede e se ele e
        RESPEITADO, e um corpo de 8 MiB num teste custaria memoria e segundos
        para provar a mesma coisa.
        """
        anterior = servir.Hub.TETO_A_DRENAR
        servir.Hub.TETO_A_DRENAR = 1024
        try:
            corpo = b"z" * 5000
            status, sobrou = self.pedir("/api/arquivar", corpo)
            self.assertIn("401", status)
            self.assertEqual(
                len(corpo) - 1024, sobrou,
                "com teto de 1024 o dreno devia parar deixando %d bytes, e "
                "deixou %d. Teto que nao segura nao e teto."
                % (len(corpo) - 1024, sobrou))
        finally:
            servir.Hub.TETO_A_DRENAR = anterior

    def test_cliente_que_some_no_meio_nao_derruba_o_pedido(self):
        """Ler de um soquete morto levanta OSError, e isso nao e um erro.

        O ramo `except OSError` do dreno nao era tocado por caso nenhum:
        trocar o `break` por `pass` poria o laco em espera infinita sem que
        nada acusasse.
        """
        class MorreNaSegundaLeitura(_NaoFecha):
            """Devolve dados uma vez, depois levanta OSError PARA SEMPRE.

            "Para sempre" e o ponto. Se o dreno tratasse o OSError com
            `continue` em vez de `break`, isto seria um laco infinito e o
            teste PENDURARIA -- que e como se prova que o `break` esta la.
            A primeira versao deste dublê so levantava a partir da terceira
            leitura, e a segunda ja devolvia vazio: o laco saia pelo
            `if not pedaco: break` e o ramo do OSError nunca era tocado.
            Verde pelo motivo errado.
            """

            def __init__(self, dados):
                super().__init__(dados)
                self.leituras = 0

            def read(self, k=-1):
                self.leituras += 1
                if self.leituras >= 2:
                    raise OSError("o cliente foi embora")
                return super().read(k)

        cru = (b"POST /api/arquivar HTTP/1.1\r\n"
               b"Host: localhost:4777\r\n"
               b"Content-Length: 500000\r\n\r\n" + b"z" * 1000)
        s = _SoqueteDeMentira(b"")
        s.entrada = MorreNaSegundaLeitura(cru)
        # Sem prazo aqui de proposito: se o laco nao parar no OSError, este
        # teste PENDURA, e suite pendurada e o sintoma que se quer ver.
        servir.Hub(s, ("127.0.0.1", 5555), object())
        self.assertIn(
            b"401", s.saida.getvalue()[:20],
            "o pedido nao chegou a ser respondido antes de o cliente sumir.")
        self.assertGreaterEqual(
            s.entrada.leituras, 2,
            "o dublê nunca chegou a levantar OSError: o caso passou sem "
            "tocar o ramo que diz testar.")

    def test_content_length_negativo_nao_pendura_a_thread(self):
        """`read(-1)` num soquete de verdade le ATE O FIM.

        `_corpo_json` fazia `read(min(n, teto))`: com `Content-Length: -1`
        isso vira `read(-1)`, e a thread fica presa ate o cliente fechar.
        Anterior ao dreno (`n <= 0` desvia dele), e latente porque o nginx
        recusa antes -- mas essa defesa mora num arquivo que nenhum workflow
        aplica. `max(0, ...)` fecha. Achado da revisao de seguranca de
        02/09/2026.

        Aqui o soquete de mentira devolve vazio na hora, entao o que se prova
        e que a leitura pede ZERO byte, e nao "ate o fim": sabotando o
        `max(0, ...)` de volta, o arreio le o resto do fluxo e a assercao de
        `sobrou` acusa.
        """
        status, sobrou = self.pedir(
            "/entrada", b'{"codigo": "123456"}', declarado=-1)
        self.assertTrue(status.startswith("HTTP/"))
        self.assertEqual(
            len(b'{"codigo": "123456"}'), sobrou,
            "com Content-Length negativo nada devia ser lido do corpo, e "
            "foram lidos %d bytes."
            % (len(b'{"codigo": "123456"}') - sobrou))

    def test_get_sem_corpo_continua_funcionando(self):
        """A guarda da guarda: o dreno nao pode ter quebrado o caminho comum."""
        status, sobrou = self.pedir("/robots.txt", b"", metodo="GET")
        self.assertIn("200", status)
        self.assertEqual(0, sobrou)


# ---------------------------------------------------------------------------
# Etapa 5 da Auditoria Profunda — a fronteira. `/api/auditoria`,
# `/api/auditoria/pedir`, e a validacao dentro de `_resultado` quando o
# desfecho traz `achados`. As sete sabotagens obrigatorias (5a-5g) do plano
# estao marcadas nos casos abaixo.
# ---------------------------------------------------------------------------

class AAuditoriaNoServidorDeVerdade(BaseServidorDeVerdade):
    """As duas rotas novas, e a validacao dentro de `_resultado`."""

    def setUp(self):
        super().setUp()
        self.addCleanup(self.limpar_fila)

    @staticmethod
    def _achados_validos(n, offset=0):
        """`n` achados que passam em `auditoria.validar` sem duvida."""
        return [{"arquivo": "a%d.py" % i, "linha": 1, "categoria": "bug",
                 "gravidade": "media",
                 "frase": "um problema real numero %d, com detalhe" % i,
                 "o_que_fazer": "corrigir o problema numero %d com calma "
                                "e sem pressa nenhuma" % i}
                for i in range(offset, offset + n)]

    @staticmethod
    def _achados_json(lista):
        return json.dumps({"achados": lista})

    # ------------------------------------------------------- GET /api/auditoria

    def test_auditoria_sem_sessao_e_401(self):
        self.assertEqual(self.pedir("/api/auditoria").status, 401)

    def test_auditoria_e_acesso_dado_5a(self):
        """Sabotagem 5a: trocar o acesso para "cortina" tem de reprovar isto."""
        self.assertEqual(servir.ROTAS["/api/auditoria"].acesso, "dado")
        self.assertEqual(servir.ROTAS["/api/auditoria/pedir"].acesso, "dado")

    def test_com_sessao_projeto_nunca_auditado_devolve_none(self):
        """Lei 2: nunca `{}` nem `{"achados": []}` para "nao sei"."""
        con = banco.conectar()
        try:
            banco.gravar("dervs", "local", {"nome": "dervs"}, con=con,
                        usuario_id=self.uid)
            con.commit()
        finally:
            con.close()
        corpo = json.loads(
            self.pedir("/api/auditoria", cookies=self.com_sessao()).corpo)
        alvo = [p for p in corpo["projetos"] if p["projeto"] == "dervs"]
        self.assertEqual(len(alvo), 1)
        self.assertIsNone(alvo[0]["auditoria"])

    # ------------------------------- o estado geral nao carrega o que nao usa

    def _projeto_com_achados(self, nome="dervs", n=3):
        """Um projeto com uma corrida `ok` e `n` achados no banco."""
        con = banco.conectar()
        try:
            banco.gravar(nome, "local", {"nome": nome}, con=con,
                         usuario_id=self.uid)
            con.commit()
        finally:
            con.close()
        # O id e carimbado por quem chama, como `servir._resultado` faz.
        achados = []
        for a in self._achados_validos(n):
            pronto = dict(a)
            regra = auditoria.REGRAS[a["categoria"]]
            pronto["regra"] = regra
            pronto["id"] = auditoria.id_do_achado(regra, nome, a)
            achados.append(pronto)
        banco.gravar_auditoria(self.uid, nome, "ok", achados)

    def test_o_estado_geral_nao_carrega_a_lista_de_achados(self):
        """`/api/dados` e o poll de 60 segundos de TODA aba, inclusive as que
        nao mostram achado nenhum.

        A lista de achados carrega `frase`, `o_que_fazer` e `trecho` — ate 1.200
        caracteres por achado. Mandar isso a cada minuto para desenhar uma tela
        que nao usa o dado e peso puro, e o dado ja tem rota propria
        (`/api/auditoria`), buscada so quando a tela de Auditoria abre.

        O RESUMO fica: `achados_n` e o que o selo e o card precisam, e tira-lo
        seria trocar um problema de peso por uma tela cega.

        Achado da revisao de Python de 02/09/2026. O conserto que ela propos —
        tirar os achados de `banco.montar_estado` — teria quebrado a entrega
        inteira: e de `montar_estado` que `regras.avaliar` (`servir.py:816`) le
        os achados para virar pendencia. A poda tem de ser DEPOIS do motor, na
        saida da rota, e e isso que este caso trava.
        """
        self._projeto_com_achados()
        corpo = json.loads(
            self.pedir("/api/dados", cookies=self.com_sessao()).corpo)
        alvo = [p for p in corpo["projetos"] if p.get("nome") == "dervs"]
        self.assertEqual(len(alvo), 1, "o projeto tem de estar no estado")
        camada = alvo[0]["auditoria"]
        self.assertIsNotNone(camada, "a corrida existe; a camada nao pode sumir")
        self.assertNotIn("achados", camada,
                         "o poll de 60s nao carrega a lista de achados")
        self.assertEqual(camada["achados_n"], 3,
                         "mas o RESUMO fica: sem ele a tela ficaria cega")

    def test_a_rota_dedicada_continua_trazendo_os_achados(self):
        """A outra metade do caso acima, e a que impede o conserto de virar
        uma tela de Auditoria vazia.

        Sem este caso, podar os achados em `/api/dados` E em `/api/auditoria`
        deixaria os dois testes verdes e a tela sem nada para mostrar.
        """
        self._projeto_com_achados()
        corpo = json.loads(
            self.pedir("/api/auditoria", cookies=self.com_sessao()).corpo)
        alvo = [p for p in corpo["projetos"] if p["projeto"] == "dervs"][0]
        self.assertEqual(len(alvo["auditoria"]["achados"]), 3)

    def test_o_motor_de_regras_ainda_enxerga_os_achados(self):
        """A terceira ponta: a poda e DEPOIS do motor, nunca antes.

        Se alguem 'consertar' isto tirando os achados de `banco.montar_estado`,
        o motor para de gerar pendencia de achado — em silencio, com os dois
        testes acima verdes. Este caso le a mesma fonte que `servir._estado` le
        e exige que os achados estejam la.
        """
        self._projeto_com_achados()
        con = banco.conectar()
        try:
            estado = banco.montar_estado(con, usuario_id=self.uid)
        finally:
            con.close()
        alvo = [p for p in estado["projetos"] if p.get("nome") == "dervs"][0]
        self.assertEqual(len(alvo["auditoria"]["achados"]), 3,
                         "o motor le daqui; podar aqui quebra a entrega")

    # ------------------------------------------------- POST /api/auditoria/pedir

    def test_pedir_sem_sessao_e_401(self):
        self.assertEqual(
            self.pedir("/api/auditoria/pedir", "POST", {"projeto": "dervs"}
                      ).status, 401)

    def test_pedir_sem_anti_csrf_e_403(self):
        r = self.pedir("/api/auditoria/pedir", "POST", {"projeto": "dervs"},
                       cookies=self.com_sessao())
        self.assertEqual(r.status, 403)

    def test_pedir_enfileira_com_trilho_claude_e_executor_auditor(self):
        cookies, csrf = self.sessao_e_token()
        r = self.pedir("/api/auditoria/pedir", "POST", {"projeto": "dervs"},
                       cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(r.status, 200)
        con = banco.conectar()
        try:
            linha = con.execute(
                "SELECT trilho, executor, regra FROM fila"
                " WHERE projeto = 'dervs'").fetchone()
        finally:
            con.close()
        self.assertIsNotNone(linha)
        self.assertEqual(linha["trilho"], "claude")
        self.assertEqual(linha["executor"], auditoria.EXECUTOR)
        self.assertEqual(linha["regra"], auditoria.REGRA_DE_VENCIMENTO)

    def test_pedir_o_mesmo_projeto_duas_vezes_nao_duplica(self):
        cookies, csrf = self.sessao_e_token()
        for _ in range(2):
            self.pedir("/api/auditoria/pedir", "POST", {"projeto": "dervs"},
                      cookies=cookies, cabecalhos={"X-Token": csrf})
        con = banco.conectar()
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM fila WHERE projeto = 'dervs'"
            ).fetchone()[0]
        finally:
            con.close()
        self.assertEqual(n, 1)

    def test_pedir_sem_projeto_e_400(self):
        cookies, csrf = self.sessao_e_token()
        r = self.pedir("/api/auditoria/pedir", "POST", {},
                       cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(r.status, 400)

    def test_5f_o_balcao_de_pedir_tranca_no_teto(self):
        """Sabotagem 5f: tirar `cortina.registrar_tentativa` daqui tem de
        fazer este caso parar de reprovar (nao ha mais 429 nenhum)."""
        cookies, csrf = self.sessao_e_token()
        ultimo = None
        for i in range(servir.Hub.TETO_DE_AUDITORIAS + 1):
            ultimo = self.pedir(
                "/api/auditoria/pedir", "POST", {"projeto": "projeto-%d" % i},
                cookies=cookies, cabecalhos={"X-Token": csrf})
        self.assertEqual(ultimo.status, 429)

    # --------------------------------------- a validacao dentro de _resultado

    def test_5c_achados_malformados_gravam_corrida_falha_sem_achado_nenhum(self):
        """Sabotagem 5c: gravar sem passar por `auditoria.validar`."""
        token, _mid = self.maquina_com_token()
        self.enfileirar_tarefa(id_="a:1", regra=auditoria.REGRA_DE_VENCIMENTO,
                               executor=auditoria.EXECUTOR)
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        r = self.como_agente(
            token, "/agente/resultado",
            {"tipo": "desfecho", "id": "a:1", "estado": "ok",
             "achados": "isto nao e json valido nenhum"})
        self.assertEqual(r.status, 200)
        con = banco.conectar()
        try:
            corrida = banco.auditoria_do_projeto(self.uid, "dervs", con=con)
            abertos = banco.achados_do_projeto(self.uid, "dervs", con=con)
        finally:
            con.close()
        self.assertIsNotNone(corrida)
        self.assertEqual(corrida["estado"], "falha")
        self.assertTrue(corrida["motivo"])
        self.assertEqual(abertos, [])

    def test_achados_validos_gravam_a_corrida_ok(self):
        token, _mid = self.maquina_com_token()
        self.enfileirar_tarefa(id_="a:1", regra=auditoria.REGRA_DE_VENCIMENTO,
                               executor=auditoria.EXECUTOR)
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        r = self.como_agente(
            token, "/agente/resultado",
            {"tipo": "desfecho", "id": "a:1", "estado": "ok",
             "achados": self._achados_json(self._achados_validos(3))})
        self.assertEqual(r.status, 200)
        con = banco.conectar()
        try:
            corrida = banco.auditoria_do_projeto(self.uid, "dervs", con=con)
            abertos = banco.achados_do_projeto(self.uid, "dervs", con=con)
        finally:
            con.close()
        self.assertEqual(corrida["estado"], "ok")
        self.assertEqual(corrida["achados_n"], 3)
        self.assertEqual(len(abertos), 3)

    def test_5d_auditoria_que_falha_nao_fecha_os_achados_da_anterior(self):
        """Sabotagem 5d: fazer a corrida invalida FECHAR os achados
        anteriores."""
        token, _mid = self.maquina_com_token()
        self.enfileirar_tarefa(id_="a:1", regra=auditoria.REGRA_DE_VENCIMENTO,
                               executor=auditoria.EXECUTOR)
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        self.como_agente(
            token, "/agente/resultado",
            {"tipo": "desfecho", "id": "a:1", "estado": "ok",
             "achados": self._achados_json(self._achados_validos(2))})
        self.enfileirar_tarefa(id_="a:2", regra=auditoria.REGRA_DE_VENCIMENTO,
                               executor=auditoria.EXECUTOR)
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        self.como_agente(
            token, "/agente/resultado",
            {"tipo": "desfecho", "id": "a:2", "estado": "ok",
             "achados": "quebrado"})
        con = banco.conectar()
        try:
            abertos = banco.achados_do_projeto(self.uid, "dervs", con=con)
        finally:
            con.close()
        self.assertEqual(len(abertos), 2)

    def test_5e_61_achados_validos_sao_recusados_inteiros(self):
        """Sabotagem 5e, POR TAMANHO: cortar em 60 e aceitar."""
        token, _mid = self.maquina_com_token()
        self.enfileirar_tarefa(id_="a:1", regra=auditoria.REGRA_DE_VENCIMENTO,
                               executor=auditoria.EXECUTOR)
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        r = self.como_agente(
            token, "/agente/resultado",
            {"tipo": "desfecho", "id": "a:1", "estado": "ok",
             "achados": self._achados_json(self._achados_validos(61))})
        self.assertEqual(r.status, 200)
        con = banco.conectar()
        try:
            corrida = banco.auditoria_do_projeto(self.uid, "dervs", con=con)
            abertos = banco.achados_do_projeto(self.uid, "dervs", con=con)
        finally:
            con.close()
        self.assertEqual(corrida["estado"], "falha")
        self.assertEqual(abertos, [])

    def test_desfecho_sem_achados_nao_mexe_na_auditoria(self):
        """Tarefa comum (sem a chave `achados`) nao cria corrida nenhuma."""
        token, _mid = self.maquina_com_token()
        self.enfileirar_tarefa(id_="d:1", regra="env_drift")
        self.como_agente(token, "/agente/relatorio", {"projetos": []})
        self.como_agente(
            token, "/agente/resultado",
            {"tipo": "desfecho", "id": "d:1", "estado": "ok"})
        con = banco.conectar()
        try:
            corrida = banco.auditoria_do_projeto(self.uid, "dervs", con=con)
        finally:
            con.close()
        self.assertIsNone(corrida)

    def test_teto_usd_da_tarefa_de_auditoria_usa_teto_da_auditoria(self):
        """Item 5 do plano: `teto_da_auditoria`, e nao `teto_da_sessao`,
        quando o executor e o auditor."""
        token, _mid = self.maquina_com_token()
        self.enfileirar_tarefa(id_="a:1", regra=auditoria.REGRA_DE_VENCIMENTO,
                               executor=auditoria.EXECUTOR)
        r = self.como_agente(token, "/agente/relatorio", {"projetos": []})
        tarefa = json.loads(r.corpo)["tarefa"]
        self.assertEqual(tarefa["executor"], auditoria.EXECUTOR)
        self.assertAlmostEqual(tarefa["teto_usd"],
                               tarefas.teto_da_auditoria(0.0), places=6)
        self.assertNotAlmostEqual(tarefa["teto_usd"],
                                  tarefas.teto_da_sessao(0.0), places=6)


if __name__ == "__main__":
    unittest.main(verbosity=0)
