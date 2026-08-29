"""O comando que o painel entrega funciona? Roda ele, de verdade.

POR QUE ESTE ARQUIVO EXISTE, e por que os testes que ja havia nao bastavam.

`test_agente.OServidorDeVerdade` prova o SERVIDOR: ele fala HTTP na mao com
`/agente/parear` e confere o que o banco guardou. Nunca executa
`python -m agente.enviar`. Entre a rota que funciona e o comando que a pessoa
cola no terminal cabem tres coisas que aquele teste nao ve:

  1. a linha montada em `painel.js` pode citar uma opcao que a linha de
     comando do agente nao aceita mais -- os dois lados nao se falam;
  2. o agente pode nao achar o proprio pacote, e ai o Python responde antes
     de o programa existir (foi o que aconteceu com o dono em 29/08/2026:
     `No module named 'agente'`, rodando de `C:\\WINDOWS\\system32`);
  3. o codigo de saida pode mentir -- programa que falha e devolve 0 faz a
     CI passar por cima de uma falha real.

Aqui o caminho inteiro roda: servidor de verdade numa porta livre, sessao de
verdade, `/api/maquinas/parear` de verdade, e entao o comando como PROCESSO
NOVO, com `cwd` na raiz do repositorio.

ISOLAMENTO, e ele nao e detalhe. O processo filho herda o ambiente, e
`coletar.medir()` varre `Path.home()`. Sem cercar isso, este teste leria as
pastas reais do dono e -- pior -- `guardar_token` escreveria no
`~/.dervs/agente.json` DE VERDADE, derrubando o pareamento que ele fez com o
servidor. `HOME`, `USERPROFILE` e `DERVS_AGENTE_ARQUIVO` apontam todos para
um diretorio temporario.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import banco     # noqa: E402
import cortina   # noqa: E402
import servir    # noqa: E402

PAINEL_JS = AQUI / "assets" / "painel.js"

# O prazo do processo filho. Ele mede a maquina antes de mandar; com `HOME`
# apontando para um diretorio vazio isso e rapido, mas a CI e mais lenta que
# esta maquina e um prazo curto vira falha intermitente.
PRAZO = 180


def comando_do_painel(alvo: str, codigo: str) -> list[str]:
    """A linha EXATA que a tela monta, lida de `painel.js`.

    Nao se escreve a linha aqui. Copia-la seria criar a segunda versao do
    comando, e as duas divergiriam no dia em que alguem trocasse uma opcao --
    o teste continuaria verde provando a copia, que e o modo de falha que o
    `contraste.py` deste repositorio ja teve uma vez.
    """
    fonte = PAINEL_JS.read_text(encoding="utf-8")
    m = re.search(r'"(python -m [^"]*?)"\s*\+\s*location\.origin\s*\+\s*'
                  r'"([^"]*?)"\s*\+\s*d\.codigo', fonte)
    if m is None:
        raise AssertionError(
            "nao achei a linha do pareamento em painel.js. Se ela mudou de "
            "forma, este teste tem de acompanhar -- e nunca ser apagado.")
    linha = m.group(1) + alvo + m.group(2) + codigo
    return linha.split()


class OComandoQueOPainelEntrega(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.casa = tempfile.TemporaryDirectory()
        cls._banco_antigo = banco.BANCO
        banco.BANCO = Path(cls.dir.name) / "hub.db"
        con = banco.conectar()
        cortina.garantir_combinacao(con)
        cls.uid = banco.criar_usuario("dono@teste.local", con=con)
        con.close()

        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), servir.Hub)
        cls.porta = cls.srv.server_address[1]
        cls.alvo = "http://127.0.0.1:%d" % cls.porta
        cls._antigos = (servir.PORTA, servir.ORIGENS_OK, servir.HOSTS_OK)
        servir.PORTA = cls.porta
        servir.ORIGENS_OK = {cls.alvo}
        servir.HOSTS_OK = {"127.0.0.1:%d" % cls.porta}
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        servir.PORTA, servir.ORIGENS_OK, servir.HOSTS_OK = cls._antigos
        banco.BANCO = cls._banco_antigo
        cls.dir.cleanup()
        cls.casa.cleanup()

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
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=15)
        try:
            c.request(metodo, caminho, body=dados, headers=cab)
            r = c.getresponse()
            corpo_txt = (r.read() or b"").decode("utf-8", "replace")
            return r.status, corpo_txt
        finally:
            c.close()

    def com_sessao(self):
        cookie = banco.novo_token()
        con = banco.conectar()
        try:
            banco.abrir_sessao(self.uid, cookie, banco.prazo(3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
        finally:
            con.close()
        return {"sessao": final or cookie}

    def csrf(self, cookies):
        """O nome do cabecalho e `X-Token`, e ele e DERIVADO da sessao pelo
        proprio servidor -- nao e uma coluna do banco. Escrevi `s["csrf"]` de
        primeira e levei um `KeyError`."""
        s = banco.sessao_valida(cookies["sessao"])
        return {"Origin": self.alvo,
                "X-Token": servir.Hub._csrf_da_sessao(s)}

    def numero_do_painel(self):
        """Exatamente o que o botao `Gerar o numero` faz."""
        cookies = self.com_sessao()
        st, corpo = self.pedir("/api/maquinas/parear", "POST", {},
                               cookies=cookies, cabecalhos=self.csrf(cookies))
        self.assertEqual(st, 200, corpo)
        return cookies, json.loads(corpo)["codigo"]

    def rodar(self, argumentos):
        """O comando como PROCESSO NOVO, com a casa cercada."""
        ambiente = dict(os.environ)
        ambiente["HOME"] = self.casa.name
        ambiente["USERPROFILE"] = self.casa.name
        ambiente["DERVS_AGENTE_ARQUIVO"] = str(
            Path(self.casa.name) / "agente.json")
        return subprocess.run([sys.executable] + argumentos[1:], cwd=AQUI,
                              capture_output=True, text=True, timeout=PRAZO,
                              env=ambiente)

    # ---------------------------------------------------------------- casos
    def test_a_linha_do_painel_e_a_que_o_agente_aceita(self):
        """As duas pontas nao se falam: uma esta num `.js`, a outra num
        `argparse`. Uma opcao renomeada de um lado so aparece quando alguem
        cola o comando -- ou aqui."""
        argv = comando_do_painel("https://exemplo.invalido", "123456")
        self.assertEqual(argv[:3], ["python", "-m", "agente.enviar"])
        self.assertIn("--alvo", argv)
        self.assertIn("--codigo", argv)
        r = self.rodar(argv[:3] + ["--help"])
        self.assertEqual(r.returncode, 0, r.stderr)
        for opcao in [a for a in argv if a.startswith("--")]:
            with self.subTest(opcao=opcao):
                self.assertIn(opcao, r.stdout,
                              "o painel manda `%s` e o agente nao conhece "
                              "essa opcao" % opcao)

    def test_o_comando_do_painel_conecta_o_computador(self):
        """A prova que o dono pediu: gerar o numero, colar a linha, funcionar.

        Confere o codigo de saida E o efeito no painel. So o codigo de saida
        nao basta -- um programa que erra e devolve 0 passaria.
        """
        cookies, codigo = self.numero_do_painel()
        # ANTES e DEPOIS, e nao um total fixo: o banco vive a classe inteira e
        # os outros casos tambem pareiam. `assertEqual(len, 1)` passou a ser
        # `3 != 1` assim que o segundo caso rodou -- o comando estava certo, a
        # conta e que era minha.
        _, antes = self.pedir("/api/maquinas", cookies=cookies)
        n_antes = len(json.loads(antes)["maquinas"])

        argv = comando_do_painel(self.alvo, codigo)
        r = self.rodar(argv)
        self.assertEqual(r.returncode, 0,
                         "o comando do painel falhou.\nsaida: %s\nerro: %s"
                         % (r.stdout, r.stderr))
        self.assertIn("pareado com", r.stdout.lower(), r.stdout)
        self.assertIn("enviado", r.stdout.lower(),
                      "pareou e nao mandou medicao: a maquina apareceria na "
                      "tela dizendo `nunca deu noticia`")

        st, corpo = self.pedir("/api/maquinas", cookies=cookies)
        self.assertEqual(st, 200, corpo)
        maquinas = json.loads(corpo)["maquinas"]
        self.assertEqual(len(maquinas), n_antes + 1, maquinas)
        nova = max(maquinas, key=lambda m: m["id"])
        self.assertTrue(nova["visto_em"],
                        "a maquina entrou sem carimbo de vida: o relatorio nao "
                        "chegou, e a tela diria `nunca deu noticia`")
        self.assertGreaterEqual(nova["projetos"], 1,
                                "conectou e nao trouxe projeto nenhum: a tela "
                                "mostraria `0 projetos` com cara de normal")

    def test_a_maquina_nasce_sem_direito_de_rodar_codigo(self):
        """Parear NUNCA autorizou executar. A coluna nasce desligada, e a tela
        mostra isso na etiqueta `SO MEDE`. Se algum dia nascer ligada, o
        segundo sim do dono vira enfeite."""
        cookies, codigo = self.numero_do_painel()
        self.assertEqual(self.rodar(comando_do_painel(self.alvo, codigo))
                         .returncode, 0)
        _, corpo = self.pedir("/api/maquinas", cookies=cookies)
        for m in json.loads(corpo)["maquinas"]:
            self.assertFalse(m["executa"], m)

    def test_a_segunda_vez_dispensa_o_numero(self):
        """O numero e de uso unico; o token fica no arquivo. Se a segunda
        chamada exigisse codigo, `--intervalo` nao existiria."""
        _, codigo = self.numero_do_painel()
        self.assertEqual(self.rodar(comando_do_painel(self.alvo, codigo))
                         .returncode, 0)
        r = self.rodar(["python", "-m", "agente.enviar", "--alvo", self.alvo])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("enviado", r.stdout.lower(), r.stdout)

    def test_numero_de_outro_dervs_falha_dizendo_o_motivo_certo(self):
        """O erro que o dono levou em 29/08/2026. O codigo de saida tem de ser
        diferente de zero E a frase tem de citar a causa real, senao ele
        depura a hipotese errada -- foi o que aconteceu."""
        r = self.rodar(comando_do_painel(self.alvo, "000000"))
        self.assertNotEqual(r.returncode, 0,
                            "codigo recusado e o programa devolveu sucesso")
        junto = (r.stdout + r.stderr)
        self.assertIn("outro DERVS", junto, junto)
        self.assertEqual([c for c in junto if ord(c) > 127], [],
                         "a frase saiu com caractere que o console do Windows "
                         "nao mostra: " + repr(junto))

    def test_rodar_de_fora_da_pasta_e_o_erro_do_python_e_nao_do_numero(self):
        """A confusao de 29/08/2026, fixada. Rodando de outra pasta o Python
        responde ANTES de o programa existir, e a frase e em ingles: quem le
        acha que o numero de seis digitos quebrou. O roteiro em
        `docs/operacao/conectar-uma-maquina.md` cita esta mensagem; se ela
        mudar, o roteiro passa a mentir."""
        cookies, codigo = self.numero_do_painel()
        ambiente = dict(os.environ)
        ambiente["HOME"] = self.casa.name
        ambiente["USERPROFILE"] = self.casa.name
        ambiente.pop("PYTHONPATH", None)
        argv = comando_do_painel(self.alvo, codigo)
        r = subprocess.run([sys.executable] + argv[1:], cwd=self.casa.name,
                           capture_output=True, text=True, timeout=PRAZO,
                           env=ambiente)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("No module named 'agente'", r.stderr, r.stderr)
        # E o numero continua valendo: o erro foi do lugar, nao do codigo.
        self.assertEqual(self.rodar(argv).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
