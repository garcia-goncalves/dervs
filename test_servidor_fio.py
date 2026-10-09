# -*- coding: utf-8 -*-
"""O FIO INTEIRO do servidor ligado: do arquivo baixado ate o campo da tela.

MOTIVO: as tres metades da entrega B foram provadas cada uma contra duble.
`test_ajudante_servidor` roda o ajudante contra um painel de mentira,
`test_servidor_ligado` conversa com o servidor com corpos escritos a mao, e
`test_servidor_tela` executa o `painel.js` em node com respostas inventadas.
Ninguem provava que o que o servidor ENTREGA e o que a tela LE sao a mesma
coisa -- o buraco que ja deixou 26 suites verdes com a Auditoria morta.

Aqui o arquivo e baixado de `/ajudante/servidor.py` de verdade, conferido pelo
SHA-256 que a linha da tela mostra, gravado numa pasta SEM o repositorio e
carregado pelo caminho. Ele pede (como servidor), o "navegador" autoriza pela
sessao do dono, ele instala numa raiz temporaria e mede com um Docker falso.
So entao se pergunta `/api/dados`, `/api/ajudante/linha` e `/api/pedido`, e se
confere que cada campo que o `assets/painel.js` le (extraido do proprio arquivo
por regex) existe -- a tela le um SUBCONJUNTO do que o servidor entrega.

    python test_servidor_fio.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
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
from test_servir import BaseServidorDeVerdade  # noqa: E402

AQUI = Path(__file__).resolve().parent
JS = (AQUI / "assets" / "painel.js").read_text(encoding="utf-8")
SHA = "96eb3fc"
PONTA = "a" * 40
ID_FALSO = "b" * 64


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


def docker_falso(argv, prazo):
    """O Docker de mentira: dois comandos de leitura, e o resto da certo."""
    if argv[:1] == ["id"]:
        return False, ""                       # o usuario ainda nao existe
    if tuple(argv[:4]) == ("docker", "ps", "-aq", "--no-trunc"):
        return True, ID_FALSO + "\n"
    if tuple(argv[:3]) == ("docker", "inspect", "--format"):
        return True, "\t".join([
            "/loja-fio-web", "running", "healthy", "2026-10-08T12:00:00.5Z",
            "2", "loja:vps", "lojafio", ""]) + "\n"
    return True, ""


class _ComOAjudanteBaixado(BaseServidorDeVerdade):
    """Roda o arquivo que o painel entrega. Sem testes proprios."""

    PROJETO = "loja-fio"
    ESTADO = ("cookies", "csrf", "pedido_visto", "erros_da_linha", "saida",
              "baixado", "linha", "token", "raiz", "codigo_medir")

    def rodar_o_ajudante(self):
        """Roda o fluxo UMA vez por classe (cada classe tem o proprio banco)."""
        cls = type(self)
        if "_rodou" not in cls.__dict__:
            codigo = self._rodar()
            cls._rodou = (codigo, {k: getattr(self, k) for k in self.ESTADO})
        codigo, estado = cls._rodou
        self.__dict__.update(estado)
        return codigo

    def _rodar(self):
        cookies, csrf = self.sessao_e_token()
        self.cookies, self.csrf = cookies, csrf
        banco.gravar(self.PROJETO, "local", {"nome": self.PROJETO},
                     usuario_id=self.uid)
        banco.gravar(self.PROJETO, "github",
                     {"head_sha": PONTA, "no_ar": [{"sha": SHA, "atras": 3}]},
                     usuario_id=self.uid)

        # O arquivo baixado SEM sessao, e a linha que a tela mostra COM ela.
        r = self.pedir("/ajudante/servidor.py", com_origem=False)
        self.assertEqual(r.status, 200, r.corpo[:300])
        bruto = r.corpo.encode("ascii")
        self.baixado = bruto
        l = self.pedir("/api/ajudante/linha", cookies=cookies)
        self.assertEqual(l.status, 200, l.corpo)
        self.linha = json.loads(l.corpo)
        self.assertEqual(hashlib.sha256(bruto).hexdigest(),
                         self.linha["sha256"])

        # Vive ate o fim da CLASSE: o fluxo roda uma vez e todo teste le dele.
        tmp = tempfile.TemporaryDirectory()
        type(self).addClassCleanup(tmp.cleanup)
        base = Path(tmp.name)
        solto = base / "baixado"
        solto.mkdir()
        (solto / "dervs-ajudante.py").write_bytes(bruto)
        raiz = base / "raiz"
        for pasta in ("run/systemd/system", "var/log/deploy", "proc"):
            (raiz / pasta).mkdir(parents=True)
        (raiz / "var/log/deploy/historico.log").write_text(
            "2026-10-08 12:00:00 %s ana 20261008-120000-%s OK\n"
            % (self.PROJETO, SHA), encoding="ascii")
        (raiz / "proc/uptime").write_text("123456.78 99.0\n", encoding="ascii")
        (raiz / "proc/loadavg").write_text("0.12 0.30 0.25 1/100 5\n",
                                           encoding="ascii")
        (raiz / "proc/meminfo").write_text(
            "MemTotal:        4000000 kB\nMemAvailable:    1200000 kB\n",
            encoding="ascii")
        self.raiz = raiz

        espec = importlib.util.spec_from_file_location(
            "ajudante_baixado", str(solto / "dervs-ajudante.py"))
        aj = importlib.util.module_from_spec(espec)
        espec.loader.exec_module(aj)

        self.pedido_visto = {}
        self.erros_da_linha = []
        self.saida = []
        linhas = []

        def abrir(metodo, url, corpo, token, prazo):
            """O `abrir` de verdade; quando o pedido sai, o "navegador" age."""
            codigo, dados = aj.abrir(metodo, url, corpo, token, prazo)
            if url.endswith("/agente/pedir") and codigo == 200:
                linha = threading.Thread(
                    target=navegador, args=(dados["codigo"],), daemon=True)
                linhas.append(linha)
                linha.start()
            return codigo, dados

        def navegador(codigo):
            try:
                v = self.pedir("/api/pedido?codigo=" + codigo, cookies=cookies)
                self.assertEqual(v.status, 200, v.corpo)
                self.pedido_visto = json.loads(v.corpo)
                a = self.pedir("/api/pedido/autorizar", "POST",
                               {"codigo": codigo}, cookies=cookies,
                               cabecalhos={"X-Token": csrf})
                self.assertEqual(a.status, 200, a.corpo)
            except BaseException as e:          # a linha nao propaga sozinha
                self.erros_da_linha.append(e)

        def que_docker_existe(nome):
            return "/usr/bin/docker" if nome == "docker" else None

        with mock.patch.object(shutil, "which", que_docker_existe):
            instalado = aj.instalar(
                alvo=aj.ALVO, raiz=str(raiz), rodar=docker_falso, abrir=abrir,
                dormir=lambda s: time.sleep(0.2), eh_root=lambda: True,
                dono=lambda caminho, usuario: None, nome="vps-fio",
                saida=self.saida.append)
            for linha in linhas:
                linha.join(timeout=10)
            self.assertEqual(self.erros_da_linha, [])
            self.assertEqual(instalado, 0, "\n".join(self.saida))
            self.codigo_medir = aj.medir(
                alvo=aj.ALVO, raiz=str(raiz), rodar=docker_falso, abrir=abrir)
        guardado = json.loads(
            (raiz / "var/lib/dervs-ajudante/agente.json").read_text("ascii"))
        self.token = guardado["token"]
        return instalado

    def dados(self):
        r = self.pedir("/api/dados", cookies=self.cookies)
        self.assertEqual(r.status, 200, r.corpo)
        return json.loads(r.corpo)

    def projeto(self, estado):
        return next(p for p in estado["projetos"]
                    if p["nome"] == self.PROJETO)


class OAjudanteBaixadoLigaNumaPastaVazia(_ComOAjudanteBaixado):
    def test_do_arquivo_baixado_ao_servidor_no_painel(self):
        self.assertEqual(self.rodar_o_ajudante(), 0)
        self.assertEqual(self.codigo_medir, 0)
        servidores = self.dados()["servidores_ligados"]
        self.assertEqual(len(servidores), 1, servidores)
        s = servidores[0]
        self.assertEqual((s["nome"], s["estado"], s["docker_mudo"]),
                         ("vps-fio", "medido", False))
        self.assertEqual(
            [("loja-fio-web", "lojafio", "running", "healthy", 2)],
            [(x["nome"], x["projeto"], x["estado"], x["saude"], x["reinicios"])
             for x in s["sistemas"]])
        self.assertEqual("2026-10-08T12:00:00+00:00", s["sistemas"][0]["desde"])

    def test_o_pedido_que_o_dono_viu_era_de_servidor(self):
        self.rodar_o_ajudante()
        self.assertEqual(self.pedido_visto.get("tipo"), "servidor")
        self.assertEqual(self.pedido_visto.get("maquina"), "vps-fio")

    def test_o_projeto_ganha_o_veredito_certo(self):
        self.rodar_o_ajudante()
        n = self.projeto(self.dados())["no_ar"]
        self.assertEqual(1, len(n), n)
        self.assertEqual(("vps-fio", "medido", SHA, "atras", 3),
                         (n[0]["servidor"], n[0]["estado"], n[0]["sha"],
                          n[0]["veredito"], n[0]["atras"]))

    def test_o_token_so_vai_para_o_arquivo_de_pareamento(self):
        self.rodar_o_ajudante()
        self.assertTrue(self.token)
        self.assertNotIn(self.token, "\n".join(self.saida))
        self.assertNotIn(self.token, self.baixado.decode("ascii"))

    def test_o_token_do_servidor_nao_baixa_o_pacote_do_computador(self):
        self.rodar_o_ajudante()
        r = self.pedir("/agente/pacote", com_origem=False,
                       cabecalhos={"Authorization": "Token " + self.token})
        self.assertEqual(r.status, 403, r.corpo[:200])
        self.assertEqual(json.loads(r.corpo), servir.Hub.SO_OLHA)

    def test_o_ajudante_instalado_e_a_copia_do_que_foi_baixado(self):
        self.rodar_o_ajudante()
        copia = self.raiz / "opt/dervs-ajudante/dervs-ajudante.py"
        self.assertEqual(self.baixado, copia.read_bytes())


class OQueATelaLeOServidorEntrega(_ComOAjudanteBaixado):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.rodar_o_ajudante(), 0)

    def contido(self, lidos: set, reais: set, onde: str):
        self.assertTrue(lidos, "nenhum campo lido para " + onde)
        faltam = lidos - reais
        self.assertFalse(faltam, "a tela le %s que %s nao entrega (entrega: %s)"
                         % (sorted(faltam), onde, sorted(reais)))

    def test_o_servidor_ligado_e_seus_sistemas(self):
        estado = self.dados()
        s = estado["servidores_ligados"][0]
        self.contido(campos("s", "linhaDeServidorLigado"), set(s),
                     "/api/dados (servidores_ligados)")
        self.contido(campos("x", "linhaDeSistema"), set(s["sistemas"][0]),
                     "/api/dados (servidores_ligados[].sistemas)")
        self.contido(campos("ESTADO", "cartaoDosServidores"), set(estado),
                     "/api/dados")

    def test_o_no_ar_do_projeto(self):
        estado = self.dados()
        p = self.projeto(estado)
        self.contido(campos("p", "linhasDoNoAr"), set(p), "/api/dados (projeto)")
        self.contido(campos("n", "linhaDoNoAr"), set(p["no_ar"][0]),
                     "/api/dados (projeto.no_ar)")

    def test_a_linha_para_colar(self):
        self.contido(campos("d", "blocoDaLinhaDoAjudante"), set(self.linha),
                     "/api/ajudante/linha")

    def test_o_pedido_de_autorizar_de_servidor(self):
        self.contido(campos("p", "pintarAutorizar"), set(self.pedido_visto),
                     "/api/pedido")
        self.assertIn("tipo", campos("p", "pintarAutorizar"))

    def test_toda_rota_citada_na_tela_existe_com_o_metodo_certo(self):
        self.assertIn('fetch("/api/ajudante/linha"', JS)
        self.assertIn("/api/ajudante/linha", servir.ROTAS)
        self.assertEqual(servir.ROTAS["/api/ajudante/linha"].metodo, "GET")
        for rota, metodo in {"/ajudante/servidor.py": "GET",
                             "/agente/servidor": "POST",
                             "/api/eventos": "GET"}.items():
            self.assertIn(rota, servir.ROTAS, rota)
            self.assertEqual(servir.ROTAS[rota].metodo, metodo, rota)

    def test_o_fluxo_da_tela_abre_sem_id_e_ouve_a_palavra_do_servidor(self):
        fluxo = sem_comentarios(funcao("ligarFluxoDosServidores"))
        self.assertIn('new EventSource("/api/eventos")', fluxo)
        self.assertNotIn("?id", fluxo)
        self.assertIn('addEventListener("servidor"', fluxo)
        # A mesma palavra tem de sair do servidor.
        fonte = (AQUI / "servir.py").read_text(encoding="utf-8")
        self.assertIn('event: servidor', fonte)


if __name__ == "__main__":
    unittest.main()
