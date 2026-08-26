# -*- coding: utf-8 -*-
"""Servidor do HUB do dev.

Serve a pagina e o /api/dados (que le o SQLite e roda as regras). O despacho
inteiro mora numa tabela: `ROTAS`, no fim deste arquivo.

    python servir.py            # http://localhost:4777
    python servir.py 4780 30    # outra porta, outro intervalo da camada local

TRES CADENCIAS, e e de proposito:
    local   a cada 60 s     git, Docker, portas, memoria           (so disco)
    github  a cada 20 min   CI, PRs, alertas                       (rede, cota)
    pesado  a cada 24 h     cota do Actions, npm audit             (caro)
A tela nunca espera nenhuma delas: le sempre o ultimo valor do banco e mostra o
carimbo de quando aquele numero foi medido.

SEGURANCA — este servidor NAO EXECUTA COMANDO (etapa 7 do DERVS)

Ele ja executou. Havia `/api/acao`, que rodava `git push`, `docker compose up`,
abria o VS Code e disparava uma sessao do Claude; havia `/api/execucao`, que
transmitia o log dessa sessao; e havia um proxy que embutia a tela do grafo de
codigo. Tudo isso foi amputado aqui, e a razao e simples: o HUB vai deixar de
ser um programa que so o dono roda na propria maquina. Codigo que executa
comando nao sobrevive a essa mudanca — nao se endurece, se remove.

`execucao.py` e `fila.py` continuam no repositorio, com seus testes verdes e
SEM NENHUMA ROTA APONTANDO PARA ELES. Isso e proposital: a trava de diff de
`fila.py:229` e uma das defesas do produto para a fatia seguinte, e apaga-la
por "esta sem uso" custaria 183 testes herdados.

Sobrou UMA rota de escrita, `/api/silenciar`, que grava uma linha no banco.
Ela mantem o par que protege contra o vizinho de aba do dono:

  1. um token sorteado a cada inicializacao, injetado so na pagina que servimos;
  2. cabecalho Origin da propria origem;
  3. cabecalho Host de localhost — barra o truque de apontar um dominio para
     127.0.0.1 (DNS rebinding).
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import banco
import memoria
import regras


# A TELINHA PISCANDO NA TELA DO DONO (24/08/2026). O painel roda sob pythonw.exe,
# que nao tem console proprio — entao cada programa de console que ele chama
# (git, aqui ~20 vezes por coleta, de minuto em minuto) ganha um console NOVO,
# que aparece por cima do que o dono estiver fazendo. CREATE_NO_WINDOW resolve
# na origem: o filho roda sem janela, e continuamos lendo o stdout normalmente.
# Mesma correcao ja aplicada em .claude/scripts/vigia-vscode.py em 13/08/2026.
def _sem_console():
    if not sys.platform.startswith("win"):
        return False
    if os.path.basename(sys.executable or "").lower() == "pythonw.exe":
        return True
    return sys.stdout is None


SEM_JANELA = 0x08000000 if _sem_console() else 0

AQUI = Path(__file__).resolve().parent
PAGINA = AQUI / "index.html"

# Os UNICOS arquivos servidos alem da pagina. Delegar ao handler estatico
# publicava a pasta toda — inclusive o hub.db e o .git/config.
ESTATICOS_OK = {"/painel-projetos.svg", "/painel-projetos.png",
                "/painel-projetos.ico", "/favicon.ico"}

COLETORES = {
    "local": (AQUI / "coletar.py", None),          # intervalo vem da linha de comando
    "github": (AQUI / "coletar_github.py", 20 * 60),
    "pesado": (AQUI / "coletar_pesado.py", 24 * 60 * 60),
}

def _numero_de(args, i, padrao, minimo, maximo):
    """Le um numero da linha de comando SEM derrubar o import.

    Antes era int(sys.argv[1]) direto no modulo. Consequencia: `python -m pytest
    test_servir.py` estourava ValueError antes do primeiro teste, porque o
    argumento era o nome do arquivo. Achado na revisao de 24/08/2026.
    """
    if len(args) <= i:
        return padrao
    try:
        n = int(args[i])
    except (TypeError, ValueError):
        return padrao
    return n if minimo <= n <= maximo else padrao


def porta_de(args, padrao=4777):
    return _numero_de(args, 1, padrao, 1, 65535)


PORTA = porta_de(sys.argv)
INTERVALO = _numero_de(sys.argv, 2, 60, 1, 86400)

TOKEN = secrets.token_urlsafe(24)
ORIGENS_OK = {"http://localhost:%d" % PORTA, "http://127.0.0.1:%d" % PORTA}
HOSTS_OK = {"localhost:%d" % PORTA, "127.0.0.1:%d" % PORTA}

_travas = {c: threading.Lock() for c in COLETORES}
_ultima_falha: dict = {}


def coletar(camada: str, motivo: str) -> None:
    """Roda um coletor. Serializado por camada: duas coletas nao se atropelam."""
    script = COLETORES[camada][0]
    if not script.is_file():
        return
    with _travas[camada]:
        inicio = time.time()
        # PRAZO. Sem ele, um coletor travado segura a trava desta camada para
        # sempre: o numero na tela congela e nada avisa. Num painel cuja regra
        # numero um e "nao mentir", medicao parada em silencio e o pior defeito
        # possivel. 10 min e folgado — a camada pesada leva ~40 s no pior dia.
        try:
            r = subprocess.run([sys.executable, str(script)], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               creationflags=SEM_JANELA, timeout=600)
        except subprocess.TimeoutExpired:
            _ultima_falha[camada] = ("o coletor passou de 10 min e foi "
                                     "interrompido.")
            print("[%s] PRAZO estourado em %s (%s)"
                  % (time.strftime("%H:%M:%S"), camada, motivo))
            return
        marca = time.strftime("%H:%M:%S")
        if r.returncode == 0:
            _ultima_falha.pop(camada, None)
            print("[%s] %s (%s) em %.1fs — %s"
                  % (marca, camada, motivo, time.time() - inicio, r.stdout.strip()))
            _anotar_a_vida(camada)
        else:
            _ultima_falha[camada] = (r.stderr or "").strip()[:400]
            print("[%s] FALHA em %s (%s):\n%s" % (marca, camada, motivo,
                                                  _ultima_falha[camada]))


def _anotar_a_vida(camada: str) -> None:
    """Depois de cada coleta LOCAL boa, guarda quem nasceu e quem morreu.

    Aqui, e nao no /api/dados, porque aquela rota e disparada pelo navegador de
    15 em 15 s: com a aba fechada o dia inteiro, o historico do dia nao existiria
    — e o dia em que ele nao olha o painel e exatamente o dia em que a memoria
    precisa ter funcionado sozinha.

    So a camada `local` dispara: ela e a unica que roda a cada 60 s e a unica que
    define quais projetos existem. Um erro aqui NUNCA pode derrubar a coleta: o
    numero na tela vale mais que o registro historico dele.
    """
    if camada != "local":
        return
    try:
        con = banco.conectar()
        try:
            e = banco.montar_estado(con)
            pend = regras.avaliar(e["projetos"], quota=e["quota"],
                                  silenciadas=banco.silenciadas(con))
            # Coleta que terminou bem mas nao enxergou projeto nenhum NAO e "o
            # dono resolveu tudo": e a pasta de repositorios indisponivel por um
            # instante. Sem esta guarda, o painel fecharia as 27 pendencias de
            # uma vez — inclusive as de seguranca — e no minuto seguinte se
            # gabaria de ter fechado 27. Achado da revisao de seguranca.
            memoria.registrar(pend, con, medicao_valida=bool(e["projetos"]))
        finally:
            con.close()
    except Exception as erro:                       # noqa: BLE001 — ver acima
        print("[%s] aviso: nao consegui anotar a memoria do tempo (%s)"
              % (time.strftime("%H:%M:%S"), erro))


def laco(camada: str, intervalo: int):
    while True:
        time.sleep(intervalo)
        coletar(camada, "automática")


# --------------------------------------------------------------------- servidor
class Hub(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(AQUI), **kw)

    def log_message(self, *a):
        pass

    # -------------------------------------------------------------- utilidades
    def _json(self, codigo, objeto):
        corpo = json.dumps(objeto, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _host_confiavel(self) -> bool:
        return (self.headers.get("Host") or "").lower() in HOSTS_OK

    # ---------------------------------------------------------- despacho
    def _caminho(self) -> str:
        """So o caminho, sem a query. A tabela de rotas casa EXATO."""
        return self.path.split("?", 1)[0]

    def _despachar(self, metodo: str):
        if not self._host_confiavel():
            return self._json(403, {"erro": "host nao permitido"})
        rota = ROTAS.get(self._caminho())
        if rota is None or rota.metodo != metodo:
            return self._json(404, {"erro": "nao existe"})
        return rota.funcao(self)

    def do_GET(self):
        return self._despachar("GET")

    def do_POST(self):
        return self._despachar("POST")

    # ------------------------------------------------------------- as rotas
    def _dados(self):
        return self._json(200, self._estado())

    def _estatico(self):
        """Os quatro arquivos de ESTATICOS_OK, e mais nenhum."""
        return super().do_GET()

    def _estado(self):
        con = banco.conectar()
        try:
            e = banco.montar_estado(con)
            pend = regras.avaliar(e["projetos"], quota=e["quota"],
                                  silenciadas=banco.silenciadas(con))
            # So LEITURA aqui: quem escreve a vida e o laco de coleta. Ver
            # _anotar_a_vida() para o motivo.
            agora_iso = banco.agora()
            pend = memoria.decorar(pend, memoria.vidas(con), agora_iso,
                                   desde=memoria.desde(con))
            tend = memoria.tendencia(con, agora_iso)
        finally:
            con.close()
        return {
            "agora": agora_iso,
            "pendencias": pend,
            # A lista achatada acima continua sendo o contrato (o "x" acha a
            # pendencia pelo id). `grupos` e so o desenho da tela.
            "grupos": regras.agrupar(pend),
            "tendencia": tend,
            "briefing": memoria.briefing(pend, tend),
            "projetos": e["projetos"],
            "infra": e["infra"],
            "infra_medido_em": e["infra_medido_em"],
            "quota": e["quota"],
            "falhas_de_coleta": dict(_ultima_falha),   # copia: o vivo muda em outra thread
        }

    def _pagina(self):
        """Serve a pagina com o token da sessao dentro.

        E aqui, e so aqui, que o token sai do processo: quem carrega a pagina
        pelo servidor recebe; quem tenta ler de outra origem nao consegue.
        """
        try:
            html = PAGINA.read_text(encoding="utf-8")
        except OSError:
            return self._json(500, {"erro": "index.html não encontrado"})
        corpo = html.replace("__TOKEN__", TOKEN).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _silenciar(self):
        """Esconde uma pendencia por N horas. SO escreve no banco.

        E a unica rota de escrita que sobrou depois da amputacao da etapa 7.
        Nao roda programa nenhum: o pior que um pedido forjado consegue aqui e
        esconder um alerta da tela do dono por ate 30 dias, e isso se desfaz
        sozinho. Mesmo assim o par Origin + token continua exigido, porque o
        alerta escondido pode ser um alerta de seguranca.
        """
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not secrets.compare_digest(self.headers.get("X-Token") or "", TOKEN):
            return self._json(403, {"erro": "recarregue a pagina (token vencido)"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(min(n, 16_384)) or b"{}")
        except (ValueError, OSError):
            return self._json(400, {"erro": "pedido invalido"})
        if not isinstance(corpo, dict):
            return self._json(400, {"erro": "pedido invalido"})
        pid = corpo.get("id")
        if not pid or not isinstance(pid, str):
            return self._json(400, {"erro": "faltou o id da pendencia"})
        # O id e sempre `regra:projeto` — dezenas de caracteres. Sem teto, quem
        # tem o token grava ids de 16 KiB, um por pedido, e cada um vira linha
        # que nenhuma coleta jamais colhe. Nao vaza nada; incha o banco.
        if len(pid) > 200:
            return self._json(400, {"erro": "id longo demais"})
        try:
            horas = max(1, min(24 * 30, int(corpo.get("horas") or 24)))
        except (TypeError, ValueError):
            return self._json(400, {"erro": "prazo invalido"})
        ate = (datetime.now(timezone.utc)
               + timedelta(hours=horas)).isoformat(timespec="seconds")
        banco.silenciar(pid, ate)
        return self._json(200, {"ok": True,
                                "saida": "silenciada por %d h." % horas})

    def do_HEAD(self):
        """Recusado.

        Sem isto o HEAD caia no SimpleHTTPRequestHandler e servia a PASTA
        INTEIRA sem passar nem pela checagem de Host. Nao vazava conteudo (HEAD
        nao tem corpo), mas vazava existencia, tamanho e data do banco, do
        arquivo de variaveis e do .git/config. Revisao de 24/08/2026.
        """
        # Cabecalho e ponto: HEAD com corpo dessincroniza a fila de respostas
        # assim que ligarmos HTTP/1.1 com keep-alive atras do nginx (etapa 16).
        # Hoje seria inofensivo, e e por isso que se conserta hoje.
        self.send_response(405)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


# ---------------------------------------------------------------- as rotas
#
# A TABELA E O CONTRATO, e ela e o objetivo desta etapa.
#
# Ate aqui o despacho era uma cadeia de `if self.path...` espalhada por dois
# metodos. Ninguem conseguia responder "quais rotas este servidor tem?" sem ler
# o arquivo inteiro e torcer para nao ter pulado um `if` — e foi assim que o
# painel passou meses com rotas que rodavam `git push`, `docker compose` e uma
# sessao do Claude na maquina do dono.
#
# Agora a resposta e uma linha: `sorted(servir.ROTAS)`. E `test_rotas.py` itera
# ESTA estrutura, em memoria, e reprova qualquer caminho que cheire a execucao
# de comando. Em memoria de proposito: um grep no texto do arquivo nao veria
# uma rota montada por concatenacao.
#
# So LEITURA aqui, com uma excecao: /api/silenciar, que escreve uma linha no
# banco e nao roda programa nenhum.
Rota = namedtuple("Rota", "metodo funcao")

ROTAS = {
    "/":               Rota("GET",  Hub._pagina),
    "/index.html":     Rota("GET",  Hub._pagina),
    "/api/dados":      Rota("GET",  Hub._dados),
    "/api/silenciar":  Rota("POST", Hub._silenciar),
}
ROTAS.update({caminho: Rota("GET", Hub._estatico) for caminho in ESTATICOS_OK})


def main():
    con = banco.conectar()
    vazio = not banco.montar_estado(con)["projetos"]
    con.close()
    if vazio:
        coletar("local", "primeira")

    threading.Thread(target=laco, args=("local", INTERVALO), daemon=True).start()
    for camada, (_, intervalo) in COLETORES.items():
        if intervalo:
            threading.Thread(target=laco, args=(camada, intervalo), daemon=True).start()

    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Hub)
    print("HUB do dev no ar: http://localhost:%d" % PORTA)
    print("Camadas: local %ds · github 20min · pesado 24h. Ctrl+C encerra." % INTERVALO)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
