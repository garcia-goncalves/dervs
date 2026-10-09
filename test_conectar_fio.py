# -*- coding: utf-8 -*-
"""O FIO INTEIRO do Conectar simples: do arquivo baixado ate o campo da tela.

MOTIVO: as tres metades do "Conectar simples" foram provadas cada uma contra
duble. `test_conectar_servidor` conversa com o servidor, `test_conectar_tela`
executa o `painel.js` em node com respostas escritas a mao, e `test_conectador`
roda o programa contra um servidor de mentira. Ninguem provava que o que o
servidor ENTREGA e o que a tela LE sao a mesma coisa -- o mesmo buraco que ja
deixou 26 suites verdes com a Auditoria morta (`test_progresso_fio.py`).

Aqui nada do lado do servidor e montado a mao: o `.cmd` e baixado de verdade,
a parte Python dele e gravada numa pasta SEM o repositorio e executada; ela
pede, o "navegador" autoriza pela sessao do dono, o pacote desce, e o primeiro
relato roda como processo novo. So entao se pergunta `/api/maquinas`,
`/api/github` e `/api/enderecos/medir`, e se confere que cada campo que o
`assets/painel.js` le (extraido do proprio arquivo por regex) existe.

    python test_conectar_fio.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco         # noqa: E402
import servir        # noqa: E402
import test_imagem   # noqa: E402
from test_servir import BaseServidorDeVerdade  # noqa: E402

AQUI = Path(__file__).resolve().parent
JS = (AQUI / "assets" / "painel.js").read_text(encoding="utf-8")
MARCA = "#:DERVS-PYTHON"


def funcao(nome: str) -> str:
    m = re.search(r"(?:async )?function %s\(.*?\n}\n" % re.escape(nome), JS, re.S)
    assert m, "funcao %s nao encontrada em painel.js" % nome
    return m.group(0)


def sem_comentarios(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)//[^\n]*$", "", js)


def campos(variavel: str, *nomes_de_funcao: str) -> set:
    """Os `variavel.campo` que essas funcoes do painel.js leem."""
    achados = set()
    for nome in nomes_de_funcao:
        achados |= set(re.findall(r"\b%s\.([A-Za-z_]\w*)" % variavel,
                                  sem_comentarios(funcao(nome))))
    return achados


def git(pasta, *args):
    subprocess.run(["git", *args], cwd=str(pasta), check=True,
                   capture_output=True, timeout=60)


class _ComOArquivoBaixado(BaseServidorDeVerdade):
    """Roda o arquivo que o painel entrega. Sem testes proprios."""

    DONO = "dono-fio"
    PROJETO = "loja-fio"

    ESTADO = ("cookies", "csrf", "pedido_visto", "erros_da_linha",
              "argv_do_agendador", "casa")

    def rodar_o_arquivo_baixado(self):
        """Roda o fluxo UMA vez por classe (cada classe tem o proprio banco) e
        devolve o codigo de saida. O primeiro relato e um processo novo, e
        repeti-lo em cada teste custaria meio minuto."""
        cls = type(self)
        if "_rodou" not in cls.__dict__:
            saida = self._rodar()
            cls._rodou = (saida, {k: getattr(self, k) for k in self.ESTADO})
        saida, estado = cls._rodou
        self.__dict__.update(estado)
        return saida

    def _rodar(self):
        """Baixa o `.cmd`, executa a parte Python fora do repositorio e devolve
        o que ela fez. Cookies e anti-CSRF vem da sessao do dono."""
        cookies, csrf = self.sessao_e_token()
        self.cookies, self.csrf = cookies, csrf
        r = self.pedir("/api/conectar.cmd", cookies=cookies)
        self.assertEqual(r.status, 200, r.corpo[:300])
        self.assertIn(MARCA, r.corpo)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        # Longe do repositorio: so a parte Python, numa pasta que so tem ela.
        solto = base / "baixado"
        solto.mkdir()
        parte = r.corpo.split(MARCA + "\r\n", 1)[1].replace("\r\n", "\n")
        (solto / "conectar_baixado.py").write_bytes(parte.encode("ascii"))
        projetos = base / "meus-projetos"
        projeto = projetos / self.PROJETO
        projeto.mkdir(parents=True)
        git(projeto, "init", "-q")
        git(projeto, "remote", "add", "origin",
            "https://github.com/%s/%s.git" % (self.DONO, self.PROJETO))
        (projeto / "LEIAME.md").write_text("oi\n", encoding="utf-8")
        git(projeto, "add", "LEIAME.md")
        git(projeto, "-c", "user.name=t", "-c", "user.email=t@t.local",
            "commit", "-q", "-m", "primeiro")
        casa = base / "casa"
        home = base / "home"
        home.mkdir()

        espec = importlib.util.spec_from_file_location(
            "conectar_baixado", str(solto / "conectar_baixado.py"))
        con = importlib.util.module_from_spec(espec)
        espec.loader.exec_module(con)

        self.pedido_visto = {}
        self.erros_da_linha = []
        self.argv_do_agendador = []
        self.casa = casa
        linhas = []

        def abrir(url):
            codigo = url.split("autorizar=", 1)[1]

            def navegador():
                try:
                    v = self.pedir("/api/pedido?codigo=" + codigo,
                                   cookies=cookies)
                    self.assertEqual(v.status, 200, v.corpo)
                    self.pedido_visto = json.loads(v.corpo)
                    a = self.pedir("/api/pedido/autorizar", "POST",
                                   {"codigo": codigo}, cookies=cookies,
                                   cabecalhos={"X-Token": csrf})
                    self.assertEqual(a.status, 200, a.corpo)
                except BaseException as e:      # a linha nao propaga sozinha
                    self.erros_da_linha.append(e)
            linha = threading.Thread(target=navegador, daemon=True)
            linhas.append(linha)
            linha.start()
            return True

        def agendar(agente, alvo, plano_b=False, interprete=""):
            self.argv_do_agendador.extend(con.argumentos_do_schtasks(
                agente, alvo, plano_b, interprete))
            return True

        ambiente = {"HOME": str(home), "USERPROFILE": str(home),
                    "DERVS_AGENTE_ARQUIVO": str(home / "agente.json"),
                    "DERVS_CASA": str(casa)}
        with mock.patch.dict(os.environ, ambiente), \
                mock.patch.object(con, "escolher_pasta",
                                  lambda sugestao="": str(projetos)), \
                mock.patch.object(con.webbrowser, "open", abrir), \
                mock.patch.object(con, "agendar", agendar), \
                mock.patch.object(con, "fala", lambda *_: None), \
                mock.patch.object(con, "pausa", lambda: None), \
                mock.patch.object(con, "dormir", lambda s: time.sleep(0.2)):
            saida = con.main()
        for linha in linhas:
            linha.join(timeout=10)
        self.assertEqual(self.erros_da_linha, [])
        return saida

    def maquinas(self):
        r = self.pedir("/api/maquinas", cookies=self.cookies)
        self.assertEqual(r.status, 200, r.corpo)
        return json.loads(r.corpo)["maquinas"]


class OArquivoBaixadoConectaNumaPastaVazia(_ComOArquivoBaixado):
    def test_do_clique_ao_primeiro_relato(self):
        self.assertEqual(self.rodar_o_arquivo_baixado(), 0)
        maquinas = self.maquinas()
        self.assertEqual(len(maquinas), 1, maquinas)
        m = maquinas[0]
        self.assertIs(m["so_mede"], True)
        self.assertTrue(m["relatado_em"], "o primeiro relato nao subiu")
        self.assertIn(self.PROJETO, [a["projeto"] for a in m["projetos_vistos"]])

    def test_a_tarefa_agendada_aponta_para_a_casa_e_nunca_para_o_repositorio(self):
        self.rodar_o_arquivo_baixado()
        self.assertTrue(self.argv_do_agendador, "nada foi agendado")
        i = self.argv_do_agendador.index("/TR")
        tr = self.argv_do_agendador[i + 1]
        self.assertIn(str(self.casa), tr)
        self.assertNotIn(str(AQUI), tr)

    def test_o_pedido_que_a_tela_confere_veio_do_servidor(self):
        self.rodar_o_arquivo_baixado()
        self.assertEqual(self.pedido_visto.get("estado"), "esperando")
        self.assertTrue(self.pedido_visto.get("codigo"))


class OQueATelaLeOServidorEntrega(_ComOArquivoBaixado):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.rodar_o_arquivo_baixado(), 0)
        self.assertEqual(self.erros_da_linha, [])
        banco.guardar_instalacao_do_github(
            self.uid, "777001", conta_login=self.DONO, conta_tipo="User")

    def contido(self, esperados: set, reais: set, onde: str):
        faltam = esperados - reais
        self.assertFalse(faltam, "a tela le %s que %s nao entrega (entrega: %s)"
                         % (sorted(faltam), onde, sorted(reais)))

    def test_o_computador_e_o_projeto_visto(self):
        m = self.maquinas()[0]
        lidos = campos("m", "linhaDeComputador", "blocoDeProjetosVistos")
        self.assertIn("projetos_vistos", lidos)
        self.assertTrue(lidos)
        self.contido(lidos, set(m), "/api/maquinas")
        vistos = campos("a", "linhaDeProjetoVisto")
        self.assertTrue(vistos)
        self.contido(vistos, set(m["projetos_vistos"][0]),
                     "/api/maquinas (projetos_vistos)")

    def test_o_pedido_de_autorizar(self):
        lidos = campos("p", "pintarAutorizar")
        self.assertTrue(lidos)
        self.contido(lidos, set(self.pedido_visto), "/api/pedido")

    def test_a_conta_do_github_e_seus_repositorios(self):
        r = self.pedir("/api/github", cookies=self.cookies)
        self.assertEqual(r.status, 200, r.corpo)
        conta = json.loads(r.corpo)["instalacoes"][0]
        self.assertTrue(campos("c", "linhaDeContaDoGithub"))
        self.contido(campos("c", "linhaDeContaDoGithub"), set(conta),
                     "/api/github")
        self.assertTrue(conta["repositorios"],
                        "o repositorio do relatorio nao chegou a conta")
        self.contido(campos("r", "linhaDeRepositorio"),
                     set(conta["repositorios"][0]), "/api/github (repositorios)")

    def test_o_resultado_da_medicao(self):
        medida = {"ok": True, "codigo": 200, "erro": "", "ms": 12}
        with mock.patch.object(servir.coletar_github, "mede_site",
                               return_value=medida), \
                mock.patch.object(servir.coletar_github, "host_publico",
                                  return_value=True):
            ok = self.pedir("/api/enderecos/medir", "POST",
                            {"url": "https://loja-da-ana.com.br"},
                            cookies=self.cookies,
                            cabecalhos={"X-Token": self.csrf})
        self.assertEqual(ok.status, 200, ok.corpo)
        ruim = self.pedir("/api/enderecos/medir", "POST", {"url": "oi"},
                          cookies=self.cookies,
                          cabecalhos={"X-Token": self.csrf})
        self.assertEqual(ruim.status, 400, ruim.corpo)
        reais = set(json.loads(ok.corpo)) | set(json.loads(ruim.corpo))
        lidos = campos("r", "pintarResultadoDaMedicao")
        self.assertTrue(lidos)
        self.contido(lidos, reais, "/api/enderecos/medir")

    def test_a_pagina_velha_e_a_mesma_palavra_nos_dois_lados(self):
        m = re.search(r'motivo === "([a-z_]+)"', funcao("escrever"))
        self.assertTrue(m, "escrever() nao confere o motivo")
        self.assertEqual(m.group(1), servir.Hub.PAGINA_VELHA["motivo"])
        r = self.pedir("/api/projetos/mostrar", "POST",
                       {"projeto": self.PROJETO, "mostrar": False},
                       cookies=self.cookies, cabecalhos={"X-Token": "velho"})
        self.assertEqual(r.status, 403, r.corpo)
        self.assertEqual(json.loads(r.corpo).get("motivo"), m.group(1))

    def test_toda_rota_citada_na_tela_existe_com_o_metodo_certo(self):
        citadas = {
            "/api/pedido": "GET", "/api/pedido/autorizar": "POST",
            "/api/projetos/mostrar": "POST", "/api/enderecos/medir": "POST",
            "/api/conectar.cmd": "GET"}
        for rota, metodo in citadas.items():
            self.assertIn('"%s' % rota, JS, rota + " sumiu do painel.js")
            self.assertIn(rota, servir.ROTAS, rota)
            self.assertEqual(servir.ROTAS[rota].metodo, metodo, rota)
        # O link nasce em JS: as duas constantes tem de ser as do servidor.
        self.assertIn('a.href = "/api/conectar.cmd"', JS)
        self.assertIn('a.download = "conectar-dervs.cmd"', JS)
        r = self.pedir("/api/conectar.cmd", cookies=self.cookies)
        self.assertIn('filename="conectar-dervs.cmd"',
                      r.cabecalhos.get("Content-Disposition", ""))

    def test_o_pacote_do_servidor_e_o_que_a_imagem_copia(self):
        self.assertEqual(servir.Hub.PACOTE, test_imagem.PACOTE_DO_COMPUTADOR)


if __name__ == "__main__":
    unittest.main()
