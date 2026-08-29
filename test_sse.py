# -*- coding: utf-8 -*-
"""Testes do fluxo ao vivo — `/api/eventos`.

TODA leitura aqui tem prazo. Teste de fluxo sem prazo nao falha: ele PENDURA,
e uma suite pendurada e pior que uma suite vermelha, porque ninguem sabe o que
esta esperando.

Duas coisas sao conferidas, e a segunda nao roda codigo nenhum:

  1. O SERVIDOR. Sobe de verdade, o pedido sai pelo soquete, e a resposta e
     lida em pedacos enquanto chega.
  2. O NGINX, por leitura. O bloco de `location` e conferido como TEXTO. Nao
     prova que o servidor de producao esta configurado assim — prova que o
     arquivo que vai para la esta certo. A prova de verdade e um curl contra
     `dervs.com.br`, e ela e da etapa 16.

    python test_sse.py
"""
from __future__ import annotations

import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco     # noqa: E402
import cortina   # noqa: E402
import servir    # noqa: E402

AQUI = Path(__file__).resolve().parent
NGINX = AQUI / "infra" / "nginx-dervs.conf"


class OFluxoAoVivo(unittest.TestCase):
    """O servidor de verdade, empurrando."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls._banco_antigo = banco.BANCO
        banco.BANCO = Path(cls.dir.name) / "hub.db"
        con = banco.conectar()
        cortina.garantir_combinacao(con)
        cls.uid = banco.criar_usuario("dono@teste.local", con=con)
        con.close()

        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servir.Hub)
        cls.porta = cls.srv.server_address[1]
        cls._porta_antiga = servir.PORTA
        cls._origens = servir.ORIGENS_OK
        cls._hosts = servir.HOSTS_OK
        servir.PORTA = cls.porta
        servir.ORIGENS_OK = {"http://127.0.0.1:%d" % cls.porta}
        servir.HOSTS_OK = {"127.0.0.1:%d" % cls.porta}
        # O fluxo real vive cinco minutos. Aqui ele vive tres segundos: o que
        # este arquivo prova e o COMPORTAMENTO (chega, pinga, fecha sozinho), e
        # esperar cinco minutos por isso seria uma suite que ninguem roda.
        cls._vida = servir.Hub.SEGUNDOS_DE_VIDA
        cls._ping = servir.Hub.SEGUNDOS_ENTRE_PINGS
        servir.Hub.SEGUNDOS_DE_VIDA = 3
        servir.Hub.SEGUNDOS_ENTRE_PINGS = 1
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        servir.PORTA = cls._porta_antiga
        servir.ORIGENS_OK = cls._origens
        servir.HOSTS_OK = cls._hosts
        servir.Hub.SEGUNDOS_DE_VIDA = cls._vida
        servir.Hub.SEGUNDOS_ENTRE_PINGS = cls._ping
        banco.BANCO = cls._banco_antigo
        cls.dir.cleanup()

    def setUp(self):
        cortina.zerar_tentativas()
        self.addCleanup(cortina.zerar_tentativas)
        servir.Hub._fluxos.clear()
        self.addCleanup(servir.Hub._fluxos.clear)

    # ------------------------------------------------------------ utilidades

    def com_sessao(self):
        cookie = banco.novo_token()
        con = banco.conectar()
        try:
            banco.abrir_sessao(self.uid, cookie, banco.prazo(3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
        finally:
            con.close()
        return final

    def abrir_fluxo(self, caminho="/api/eventos", sessao=None, prazo=10):
        """Abre a conexao e devolve (resposta, conexao). NAO le o corpo."""
        cab = {"Host": "127.0.0.1:%d" % self.porta}
        if sessao:
            cab["Cookie"] = "sessao=%s" % sessao
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=prazo)
        c.request("GET", caminho, headers=cab)
        return c.getresponse(), c

    def ler_ate(self, resposta, marca: str, segundos=8) -> str:
        """Le em pedacos ate achar `marca`, ou desiste no prazo.

        `readline` bloquearia ate o fim da resposta se ela nao tivesse fim. O
        prazo do soquete e o que impede este teste de pendurar a suite.
        """
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
                return junto
        return junto

    # ------------------------------------------------------------ o servidor

    def test_sem_sessao_o_fluxo_nao_abre(self):
        r, c = self.abrir_fluxo()
        try:
            self.assertEqual(r.status, 401)
        finally:
            c.close()

    def test_com_sessao_e_um_fluxo_de_eventos(self):
        r, c = self.abrir_fluxo(sessao=self.com_sessao())
        try:
            self.assertEqual(r.status, 200)
            self.assertIn("text/event-stream", r.headers.get("Content-Type"))
            self.assertEqual(r.headers.get("Cache-Control"), "no-cache")
        finally:
            c.close()

    def test_o_cabecalho_que_faz_o_nginx_deixar_passar_esta_la(self):
        """Sem `X-Accel-Buffering: no` o nginx segura a resposta, e o dono ve a
        tela parada enquanto o trabalho acontece."""
        r, c = self.abrir_fluxo(sessao=self.com_sessao())
        try:
            self.assertEqual(r.headers.get("X-Accel-Buffering"), "no")
        finally:
            c.close()

    def test_o_fluxo_nao_diz_o_tamanho_dele(self):
        """`Content-Length` numa resposta que ainda nao acabou e uma promessa
        que o servidor nao pode cumprir."""
        r, c = self.abrir_fluxo(sessao=self.com_sessao())
        try:
            self.assertIsNone(r.headers.get("Content-Length"))
        finally:
            c.close()

    def test_uma_linha_gravada_no_banco_chega_a_quem_esta_lendo(self):
        """O coracao do criterio 8: o dono ve o trabalho acontecendo."""
        con = banco.conectar()
        try:
            con.execute("INSERT OR REPLACE INTO fila"
                        " (id, projeto, regra, trilho, criado_em, estado)"
                        " VALUES ('d:vivo','dervs','env_drift','claude',?, 'rodando')",
                        (banco.agora(),))
            con.commit()
        finally:
            con.close()
        r, c = self.abrir_fluxo("/api/eventos?id=d:vivo",
                                sessao=self.com_sessao())
        try:
            self.assertEqual(r.status, 200)
            con = banco.conectar()
            try:
                banco.registrar_progresso("d:vivo", None,
                                          linhas=[(1, "abrindo a copia")],
                                          con=con)
                # A maquina e None de proposito: a gravacao direta prova que o
                # FLUXO le o banco, sem depender do caminho do agente.
                con.execute("INSERT OR IGNORE INTO tarefa_linha"
                            " (tarefa_id, n, texto, quando)"
                            " VALUES ('d:vivo', 1, 'abrindo a copia', ?)",
                            (banco.agora(),))
                con.commit()
            finally:
                con.close()
            corpo = self.ler_ate(r, "abrindo a copia", segundos=6)
            self.assertIn("abrindo a copia", corpo)
            self.assertIn("event: linha", corpo)
        finally:
            c.close()

    def test_a_conexao_fecha_sozinha_e_avisa(self):
        """Conexao eterna em ThreadingHTTPServer e thread eterna. O EventSource
        reconecta sozinho; o aviso existe para a tela nao pintar isso como
        queda."""
        r, c = self.abrir_fluxo(sessao=self.com_sessao(), prazo=15)
        try:
            corpo = self.ler_ate(r, "event: fim", segundos=10)
            self.assertIn("event: fim", corpo)
        finally:
            c.close()

    def test_o_ping_mantem_a_conexao_viva(self):
        """O `proxy_read_timeout` do nginx e 60 s: um minuto de silencio derruba
        a conexao no meio de uma sessao que so esta pensando."""
        r, c = self.abrir_fluxo(sessao=self.com_sessao(), prazo=15)
        try:
            corpo = self.ler_ate(r, ": ping", segundos=8)
            self.assertIn(": ping", corpo)
        finally:
            c.close()

    def test_a_quinta_janela_da_mesma_sessao_e_recusada(self):
        """Dez abas abertas seriam dez threads paradas, e o publico deste
        servidor sao duas pessoas."""
        sessao = self.com_sessao()
        abertas = []
        try:
            for _ in range(servir.Hub.FLUXOS_POR_SESSAO):
                r, c = self.abrir_fluxo(sessao=sessao, prazo=15)
                abertas.append(c)
                self.assertEqual(r.status, 200)
            r, c = self.abrir_fluxo(sessao=sessao, prazo=15)
            abertas.append(c)
            self.assertEqual(r.status, 503)
        finally:
            for c in abertas:
                c.close()

    def test_fechar_a_aba_devolve_a_vaga(self):
        """Se a vaga nao voltasse, quatro recargas de pagina trancariam o dono
        fora do proprio painel por cinco minutos.

        A vaga NAO volta na hora, e este teste diz a verdade sobre isso: o
        servidor so descobre que a aba fechou quando tenta escrever nela, e ele
        escreve a sonda uma vez por segundo. Entao a devolucao leva ate uns dois
        segundos — o teste espera por ela em vez de fingir que e instantanea.
        """
        sessao = self.com_sessao()
        abertas = []
        for _ in range(servir.Hub.FLUXOS_POR_SESSAO):
            r, c = self.abrir_fluxo(sessao=sessao, prazo=15)
            self.assertEqual(r.status, 200)
            abertas.append((r, c))
        # A quinta e recusada — as quatro vagas estao ocupadas de verdade.
        r, c = self.abrir_fluxo(sessao=sessao, prazo=15)
        self.assertEqual(r.status, 503)
        c.close()
        for _r, aberta in abertas:
            aberta.close()
        # Agora espera a devolucao. Ate 10 s, e falha se nao vier.
        prazo = time.time() + 10
        while time.time() < prazo:
            time.sleep(0.5)
            r, c = self.abrir_fluxo(sessao=sessao, prazo=15)
            estado = r.status
            c.close()
            if estado == 200:
                return
            time.sleep(0.5)
        self.fail("a vaga nao voltou em 10 s depois de a aba fechar")

    def test_id_de_tarefa_que_nao_existe_nao_derruba_o_fluxo(self):
        r, c = self.abrir_fluxo("/api/eventos?id=nao-existe",
                                sessao=self.com_sessao(), prazo=15)
        try:
            self.assertEqual(r.status, 200)
            self.assertIn("event: estado", self.ler_ate(r, "event: estado", 6))
        finally:
            c.close()


class ONginxDeixaOFluxoPassar(unittest.TestCase):
    """O arquivo de configuracao, lido como texto.

    Isto NAO prova que o servidor de producao esta assim — prova que o arquivo
    que vai para la esta certo. A prova de verdade e um curl com sessao contra
    `dervs.com.br`, e ela e da etapa 16. Cinco defeitos da primeira publicacao
    so existiam fora do localhost.
    """

    @classmethod
    def setUpClass(cls):
        cls.texto = NGINX.read_text(encoding="utf-8")

    def bloco(self, cabecalho: str) -> str:
        """O corpo de um `location`, do `{` ate o `}` no mesmo recuo."""
        inicio = self.texto.find(cabecalho)
        self.assertNotEqual(inicio, -1, "nao achei %r" % cabecalho)
        fim = self.texto.find("\n    }", inicio)
        self.assertNotEqual(fim, -1, "o bloco %r nao fecha" % cabecalho)
        return self.texto[inicio:fim]

    def test_o_bloco_do_fluxo_existe(self):
        self.assertIn("location = /api/eventos {", self.texto)

    def test_o_bloco_do_fluxo_desliga_o_buffer(self):
        corpo = self.bloco("location = /api/eventos {")
        self.assertIn("proxy_buffering off;", corpo)

    def test_o_bloco_do_fluxo_espera_muito_mais_que_um_minuto(self):
        corpo = self.bloco("location = /api/eventos {")
        self.assertIn("proxy_read_timeout 3600s;", corpo)
        self.assertIn("proxy_http_version 1.1;", corpo)

    def test_o_bloco_do_fluxo_nao_tem_add_header(self):
        """Um `add_header` dentro de um `location` ANULA os seis cabecalhos de
        seguranca do `server`. E regra do nginx, e ja esta escrita no proprio
        arquivo — este teste e o que a faz doer."""
        self.assertNotIn("add_header", self.bloco("location = /api/eventos {"))

    def test_o_repasse_normal_continua_com_buffer(self):
        """A guarda da guarda: se alguem desligasse o buffer no `location /`
        para "resolver" o fluxo, todas as respostas do site virariam varios
        pacotes pequenos, e nenhum teste reclamaria.

        O arquivo tem DOIS `location /`: o primeiro e o desvio de HTTP para
        HTTPS, no `server` da porta 80. O que interessa e o segundo, e por isso
        a busca comeca depois do comentario que o anuncia.
        """
        marca = "o repasse"
        depois = self.texto[self.texto.find(marca):]
        self.assertNotEqual(self.texto.find(marca), -1)
        corpo = depois[depois.find("location / {"):
                       depois.find("\n    }", depois.find("location / {"))]
        self.assertIn("proxy_buffering on;", corpo)

    def test_o_bloco_do_fluxo_repassa_os_mesmos_cabecalhos(self):
        corpo = self.bloco("location = /api/eventos {")
        for cabecalho in ("Host              $host",
                          "X-Real-IP         $remote_addr",
                          "X-Forwarded-For   $proxy_add_x_forwarded_for",
                          "X-Forwarded-Proto https"):
            self.assertIn(cabecalho, corpo)


if __name__ == "__main__":
    unittest.main(verbosity=0)
