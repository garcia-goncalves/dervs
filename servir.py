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

  1. um anti-CSRF derivado da SESSAO de quem pede, injetado so na pagina que
     servimos (era um token global ate a etapa 9 — com multiusuario, um token
     so para o servidor inteiro seria a chave de todo mundo);
  2. cabecalho Origin da propria origem;
  3. cabecalho Host de localhost — barra o truque de apontar um dominio para
     127.0.0.1 (DNS rebinding).

QUEM ENTRA, E COMO (etapa 9)

`GET /` nao mostra login. Mostra uma cortina: um teclado de seis digitos, e
nada que diga o que este sistema e. A combinacao e conferida NO SERVIDOR, entao
o botao de entrar nem chega ao navegador antes da hora.

A CORTINA NAO E A FECHADURA. Seis digitos sao um milhao de combinacoes; ela
para robo de varredura, e e para isso que serve. A fechadura e o login por
GitHub, em `autenticacao.py`, contra a lista de contas em `credencial`.

Toda rota declara `acesso` na tabela `ROTAS`, e `test_rotas.py` reprova a suite
se alguma nascer sem classificacao. Nega por padrao, inclusive no teste.
"""
from __future__ import annotations

import hashlib
import hmac
import http.cookies
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import autenticacao
import banco
import cortina
import memoria
import passkey
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
# A capa. Quem chega sem sessao ve ESTA pagina, e ela nao contem formulario de
# login nenhum — o botao de entrar so e enviado depois da combinacao certa.
PAGINA_CORTINA = AQUI / "index-cortina.html"
# O menu de portas, injetado DENTRO da capa e so depois da combinacao certa.
# Arquivo separado pelo mesmo motivo que a capa nao traz o botao de entrar: o
# que nao e enviado nao aparece no Ctrl+U de quem ainda nao passou pela cortina.
PAGINA_PORTAS = AQUI / "portas.html"

AMBIENTE = (os.environ.get("DERVS_AMBIENTE") or "").strip().lower()
E_LOCAL = AMBIENTE == "local"
# O Client ID e publico. O Client Secret vive DENTRO do servidor, em variavel de
# ambiente, e nunca em arquivo versionado, commit, log ou conversa. Sem os dois,
# a rota de entrar responde como se nao existisse — falha fechada.
GITHUB_ID = (os.environ.get("DERVS_GITHUB_ID") or "").strip()
GITHUB_SECRET = (os.environ.get("DERVS_GITHUB_SECRET") or "").strip()

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

ORIGENS_OK = {"http://localhost:%d" % PORTA, "http://127.0.0.1:%d" % PORTA}
HOSTS_OK = {"localhost:%d" % PORTA, "127.0.0.1:%d" % PORTA}

# O TOKEN GLOBAL SAIU DE CENA (etapa 9). Ele era sorteado a cada inicializacao e
# injetado na pagina: servia de defesa contra pedido forjado de outro site, e so
# isso. Com sessao de verdade ele nao pode virar credencial de usuario — quem
# tem o token teria a chave de todo mundo. O anti-CSRF passa a ser derivado da
# SESSAO de quem pede, em `_csrf_da_sessao`.
ONDE_VOLTAR = "/entrar/github/retorno"
# Folego da ida ao GitHub. Dez minutos nao bastam: no meio dela cabe uma tela de
# login e um segundo fator digitado do celular.
MINUTOS_DA_IDA = 30

# Os desafios de uso unico das chaves de acesso. Um por processo, em memoria:
# reiniciar o servidor faz quem estava no meio do login apertar o botao de novo,
# e so. Ver a classe em passkey.py para por que nao e um cookie assinado.
DESAFIOS = passkey.Desafios()

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
                                  silenciadas=banco.silenciadas(con),
                                  arquivadas=banco.arquivadas(con=con))
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
        # ANTES de super(): em BaseHTTPRequestHandler o pedido e atendido dentro
        # do proprio __init__, entao atributo criado depois nasce tarde demais.
        self._cookies_pendentes = []
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

    # ------------------------------------------------------------- cookies
    def _ler_cookie(self, nome: str) -> str:
        cru = self.headers.get("Cookie") or ""
        try:
            pote = http.cookies.SimpleCookie()
            pote.load(cru)
        except http.cookies.CookieError:
            return ""
        item = pote.get(nome)
        return item.value if item else ""

    def _por_cookie(self, nome: str, valor: str, segundos: int) -> None:
        """Enfileira um cookie. `end_headers` e quem escreve.

        `HttpOnly` tira o cookie do alcance de qualquer JavaScript da pagina;
        `SameSite=Lax` impede que outro site o mande junto num pedido forjado;
        `Secure` so fora do ambiente local, porque em http://localhost o
        navegador descartaria o cookie e ninguem conseguiria entrar na propria
        maquina.
        """
        pedacos = ["%s=%s" % (nome, valor), "Path=/", "HttpOnly",
                   "SameSite=Lax", "Max-Age=%d" % max(0, segundos)]
        if not E_LOCAL:
            pedacos.append("Secure")
        self._cookies_pendentes.append("; ".join(pedacos))

    def _apagar_cookie(self, nome: str) -> None:
        self._por_cookie(nome, "", 0)

    # ------------------------------------------------------------- sessao
    def _sessao(self):
        """A sessao COMPLETA de quem pediu, ou None.

        Completa quer dizer com segundo fator conferido. Sessao que passou so
        pela primeira metade nao vale para rota de dado — e a negativa e o
        padrao, porque `segundo_fator_em` nasce NULL.
        """
        cookie = self._ler_cookie("sessao")
        if not cookie:
            return None
        s = banco.sessao_valida(cookie)
        if not s or not s.get("segundo_fator_em"):
            return None
        return s

    @staticmethod
    def _csrf_da_sessao(sessao) -> str:
        """O sucessor do TOKEN global.

        Derivado da sessao, entao vale so para quem esta dentro daquela sessao.
        O TOKEN antigo era um so para o servidor inteiro: com multiusuario, ele
        viraria a chave de todo mundo.
        """
        return hmac.new(banco.chave_do_cofre(),
                        ("csrf|" + str(sessao["id"])).encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def _cortina_aberta(self) -> bool:
        return cortina.selo_valido(self._ler_cookie("cortina"), time.time(),
                                   banco.chave_do_cofre())

    def _origem_do_pedido(self) -> str:
        return self.client_address[0] if self.client_address else "?"

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
        # NEGA POR PADRAO. `acesso` e obrigatorio em toda rota, e `test_rotas.py`
        # reprova a suite se alguma nascer sem ele — nao ha valor "sem
        # classificacao" que passe por aqui por descuido.
        if rota.acesso == "dado" and self._sessao() is None:
            # Sem detalhe e sem nome de projeto nenhum no corpo.
            return self._json(401, {"erro": "entre para ver"})
        if rota.acesso == "cortina" and not self._cortina_aberta():
            # A MESMA resposta de rota inexistente: quem nao passou pela cortina
            # nao pode nem descobrir que esta rota existe.
            return self._json(404, {"erro": "nao existe"})
        try:
            return rota.funcao(self)
        except Exception:
            # Sem esta rede, uma excecao dentro da rota faz o `socketserver`
            # imprimir o traceback e FECHAR O SOQUETE: o navegador leva
            # "connection reset", sem status nenhum, e a tela nao sabe o que
            # aconteceu. A mensagem e generica de proposito; o traceback vai
            # para o stderr do servidor, nao para quem pediu.
            traceback.print_exc()
            return self._json(500, {"erro": "falhou"})

    def do_GET(self):
        return self._despachar("GET")

    def do_POST(self):
        return self._despachar("POST")

    # ------------------------------------------------------------- as rotas
    def _dados(self):
        # O dono da sessao, e nao o dono da MAQUINA. Ver `_estado`.
        return self._json(200, self._estado(self._sessao()["usuario_id"]))

    def _estatico(self):
        """Os quatro arquivos de ESTATICOS_OK, e mais nenhum."""
        return super().do_GET()

    def _estado(self, usuario_id: int):
        """O estado COMO AQUELA CONTA o ve.

        `usuario_id` nao era passado, e `banco.silenciadas` caia no padrao
        `DONO_LOCAL = 0`: com uma segunda conta entrando pela web — que e
        exatamente o que esta etapa passou a permitir —, o "x" de um usuario
        escondia o alerta do outro. E o mesmo IDOR que a etapa 8 consertou no
        esquema; faltava consertar na rota. Achado da revisao de seguranca.
        """
        con = banco.conectar()
        try:
            e = banco.montar_estado(con)
            pend = regras.avaliar(e["projetos"], quota=e["quota"],
                                  silenciadas=banco.silenciadas(
                                      con, usuario_id=usuario_id),
                                  arquivadas=banco.arquivadas(
                                      usuario_id=usuario_id, con=con))
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

    # A chave de acesso vem PRIMEIRO, e e a unica sem `secundaria`: e a porta
    # recomendada do desenho. As outras existem para o dia em que ela nao serve.
    BOTAO_CHAVE = ('<button class="entrar" type="button" data-porta="chave">'
                   "Entrar com chave de acesso</button>")
    BOTAO_ENTRAR = ('<a class="entrar secundaria" href="/entrar/github"'
                    ' rel="nofollow">Entrar com GitHub</a>')
    BOTAO_CODIGO = ('<button class="entrar secundaria" type="button"'
                    ' data-porta="codigo">Usar um c&#243;digo do papel</button>')
    # A faixa e o aviso: quem ve isto esta olhando dado de mentira.
    BOTAO_LOCAL = ('<a class="entrar secundaria" href="/entrar/local"'
                   ' rel="nofollow">Entrar &#183; ambiente local</a>')
    FAIXA_LOCAL = ('<div class="faixa-local">Ambiente local &#183; entrada sem '
                   "senha</div>")

    def _pagina(self):
        """Tres estados, e a diferenca entre eles e o que protege a entrada.

        1. sessao completa  -> o painel, com o anti-CSRF daquela sessao dentro;
        2. cortina aberta   -> a capa, MAIS o botao de entrar;
        3. nada             -> a capa, e so a capa.

        O caso 3 e o ponto: o botao de entrar nao esta no arquivo servido. Quem
        der Ctrl+U na primeira visita nao acha o formulario de login, porque ele
        nunca foi enviado.
        """
        sessao = self._sessao()
        if sessao is not None:
            return self._html_de(PAGINA, {
                "__TOKEN__": self._csrf_da_sessao(sessao),
                "__FAIXA__": self.FAIXA_LOCAL if E_LOCAL else ""})
        if not self._cortina_aberta():
            return self._html_de(PAGINA_CORTINA, {"__PORTA_ABERTA__": ""})
        return self._html_de(PAGINA_CORTINA,
                             {"__PORTA_ABERTA__": self._menu_de_portas()})

    def _menu_de_portas(self) -> str:
        """O menu que so existe depois da cortina. Vazio se faltar o arquivo.

        A chave de acesso e o codigo do papel aparecem SEMPRE: os dois vivem
        neste banco, sem depender de nada registrado fora. Quem nao tiver chave
        cadastrada descobre ao clicar — e nao antes, porque dizer "voce nao tem
        chave" a quem so passou pela cortina ja e contar algo sobre a conta.

        O GitHub aparece so com aplicativo registrado: botao que responde 404 e
        pior que botao ausente. E a porta local, so no ambiente local.
        """
        botoes = [self.BOTAO_CHAVE]
        if GITHUB_ID and GITHUB_SECRET:
            botoes.append(self.BOTAO_ENTRAR)
        botoes.append(self.BOTAO_CODIGO)
        if E_LOCAL:
            botoes.append(self.BOTAO_LOCAL)
        try:
            molde = PAGINA_PORTAS.read_text(encoding="utf-8")
        except OSError:
            # Falha FECHADA na tela: sem o molde, a capa aparece sem porta
            # nenhuma em vez de aparecer quebrada.
            return ""
        return molde.replace("__BOTOES__", "\n    ".join(botoes))

    def _html_de(self, caminho, trocas):
        try:
            html = caminho.read_text(encoding="utf-8")
        except OSError:
            return self._json(500, {"erro": "página não encontrada"})
        for marca, valor in trocas.items():
            html = html.replace(marca, valor)
        corpo = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        # Tela autenticada e capa nao entram em buscador. Defesa, nao divulgacao.
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.end_headers()
        self.wfile.write(corpo)

    # ------------------------------------------------------------- a entrada
    def _sem_conteudo(self):
        """A resposta da cortina, IGUAL para acerto, erro e excesso de chute.

        Quem sabe se acertou e o cookie, nao o corpo nem o codigo de status.
        Codigo diferente por causa diferente e um oraculo: da para varrer o
        milhao de combinacoes lendo so o status.
        """
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _entrada(self):
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._sem_conteudo()
        origem, agora_s = self._origem_do_pedido(), time.time()
        if not cortina.registrar_tentativa(origem, agora_s):
            return self._sem_conteudo()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(min(n, 1024)) or b"{}")
        except (ValueError, OSError):
            return self._sem_conteudo()
        if not isinstance(corpo, dict):
            return self._sem_conteudo()
        con = banco.conectar()
        try:
            certo = cortina.conferir(corpo.get("combinacao"), con)
        finally:
            con.close()
        if certo:
            self._por_cookie("cortina",
                             cortina.selar(agora_s, banco.chave_do_cofre()),
                             cortina.MINUTOS_DO_SELO * 60)
        return self._sem_conteudo()

    def _entrar_github(self):
        # Falha FECHADA: sem aplicativo registrado, a rota responde como se nao
        # existisse. Melhor nao ter porta do que ter porta que nao tranca.
        if not GITHUB_ID or not GITHUB_SECRET:
            return self._json(404, {"erro": "nao existe"})
        state = autenticacao.novo_state()
        self._por_cookie("state", state, MINUTOS_DA_IDA * 60)
        # O selo da cortina vale dez minutos, e a ida ao GitHub inclui login e
        # segundo fator. Sem renovar, quem demorasse voltaria para um 404 seco na
        # rota de retorno, sem pista do que aconteceu. Renova-se para o mesmo
        # folego do `state`, e nao mais: a cortina nao vira sessao.
        self._por_cookie("cortina",
                         cortina.selar(time.time(), banco.chave_do_cofre(),
                                       minutos=MINUTOS_DA_IDA),
                         MINUTOS_DA_IDA * 60)
        # O esquema segue o ambiente. Hoje o Host ja passou pelo conjunto fechado
        # de `HOSTS_OK`, entao nao ha o que forjar — mas no dia em que a etapa 16
        # acrescentar `dervs.com.br` ali, um "http://" fixo faria o `code` do
        # OAuth viajar em claro.
        esquema = "http://" if E_LOCAL else "https://"
        origem = esquema + (self.headers.get("Host") or "localhost:%d" % PORTA)
        self.send_response(302)
        self.send_header("Location", autenticacao.url_de_autorizacao(
            GITHUB_ID, origem + ONDE_VOLTAR, state))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _retorno_github(self):
        if not GITHUB_ID or not GITHUB_SECRET:
            return self._json(404, {"erro": "nao existe"})
        pedido = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        con = banco.conectar()
        try:
            cookie = autenticacao.entrar_por_github(
                code=(pedido.get("code") or [""])[0],
                state=(pedido.get("state") or [""])[0],
                state_esperado=self._ler_cookie("state"),
                con=con, client_id=GITHUB_ID, client_secret=GITHUB_SECRET)
        finally:
            con.close()
        # O `state` e de uso unico: some assim que a volta acontece, deu certo
        # ou nao. Reusar um `state` e um dos caminhos classicos de sequestro.
        self._apagar_cookie("state")
        if cookie:
            self._por_cookie("sessao", cookie,
                             autenticacao.HORAS_DE_SESSAO * 3600)
        # Mesma resposta nos dois casos: volta para a capa. Quem falhou ve a
        # capa de novo e nao descobre o motivo.
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    CONTA_LOCAL = "dono@teste.local"

    def _entrar_local(self):
        """A porta do AMBIENTE LOCAL, e so dele.

        Sem ela, esta etapa trancaria o dono do lado de fora da propria maquina:
        o aplicativo do GitHub ainda nao existe, entao `/entrar/github` responde
        404 e nao ha outra porta. Local e de mentira por regra da casa — dado de
        teste, conta de teste, e nada disso e segredo.

        UMA CHAVE, E ELA E `E_LOCAL`. Uma versao anterior deste texto prometia
        "duas travas independentes", e a revisao de Python de 26/08/2026 mostrou
        que a segunda nao podia disparar: `_despachar` ja rejeita todo `Host`
        fora de `HOSTS_OK`, entao a checagem daqui era sempre verdadeira. Prometer
        defesa que nao existe e pior que nao ter a defesa, porque encerra a
        pergunta.

        O que existe de verdade, e nesta ordem:

          1. a rota **nao entra na tabela `ROTAS`** quando `E_LOCAL` e falso, ou
             seja, no servidor ela nao existe — nem como 403, nem como caminho;
          2. a checagem de `E_LOCAL` aqui dentro, para o caso de alguem montar a
             tabela de outro jeito;
          3. a checagem de `Host`, que hoje e redundante e passa a valer no dia
             em que a etapa 16 acrescentar `dervs.com.br` a `HOSTS_OK`.

        As tres falham FECHADAS: fora do ambiente local a rota responde como se
        nao existisse.
        """
        anfitriao = (self.headers.get("Host") or "").split(":", 1)[0].lower()
        if not E_LOCAL or anfitriao not in ("localhost", "127.0.0.1"):
            return self._json(404, {"erro": "nao existe"})
        con = banco.conectar()
        try:
            # `usuario_por_email` filtra `desativado_em IS NULL`: se a conta
            # local estiver desativada ele devolve None, e um `criar_usuario`
            # aqui estouraria no UNIQUE do e-mail e derrubaria o pedido inteiro.
            # Procura-se pela linha, nao pela conta ativa.
            l = con.execute("SELECT id, desativado_em FROM usuario WHERE email = ?",
                            (self.CONTA_LOCAL,)).fetchone()
            if l is None:
                uid = banco.criar_usuario(self.CONTA_LOCAL,
                                          nome="Dono (ambiente local)", con=con)
            elif l["desativado_em"]:
                # Desativada de proposito: a porta local nao reativa conta.
                return self._json(404, {"erro": "nao existe"})
            else:
                uid = l["id"]
            cookie = banco.novo_token()
            banco.abrir_sessao(uid, cookie, banco.prazo(12 * 3600), con=con)
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
        finally:
            con.close()
        self._por_cookie("sessao", final, 12 * 3600)
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ------------------------------------------------- as portas de entrada
    #
    # Quatro caminhos para a mesma sessao, e a cortina continua antes de todos.
    # O desenho esta em docs/superpowers/specs/2026-08-26-portas-de-entrada-design.md.
    #
    # A REGRA QUE VALE PARA AS TRES ROTAS DE ENTRAR: a resposta e a MESMA para
    # todo tipo de fracasso. Credencial que nao existe, assinatura errada,
    # desafio vencido, conta desativada — tudo devolve o mesmo 401 com o mesmo
    # texto. Motivo diferente por causa diferente transforma a tela de login
    # numa lista de quem existe, e "essa credencial nao esta cadastrada" ja
    # confirma que as outras estao.

    RECUSA = {"erro": "nao deu"}

    def _rp_id(self) -> str:
        """O dominio a que a chave fica amarrada — sem a porta.

        Sai do `Host`, que `_despachar` ja conferiu contra `HOSTS_OK`. Fixar
        "localhost" aqui faria toda chave cadastrada parar de funcionar no dia
        em que a etapa 16 puser o sistema em dervs.com.br.
        """
        return (self.headers.get("Host") or "").split(":", 1)[0].lower()

    def _corpo_json(self, teto: int = 64 * 1024):
        """O corpo do pedido como dicionario, ou None. Nunca levanta."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(min(n, teto)) or b"{}")
        except (ValueError, OSError):
            return None
        return corpo if isinstance(corpo, dict) else None

    def _texto_do_corpo(self, corpo, campo: str, teto: int = 4096) -> str:
        """Um campo de texto do corpo, com teto. String vazia se torto."""
        valor = (corpo or {}).get(campo)
        if not isinstance(valor, str) or len(valor) > teto:
            return ""
        return valor

    def _bytes_do_corpo(self, corpo, campo: str):
        """Um campo base64url do corpo, ja decodificado. None se torto."""
        return passkey.de_b64url(self._texto_do_corpo(corpo, campo,
                                                      teto=passkey.TETO_DO_B64))

    def _csrf_ok(self, sessao) -> bool:
        return secrets.compare_digest(self.headers.get("X-Token") or "",
                                      self._csrf_da_sessao(sessao))

    def _handle_do_usuario(self, usuario_id: int) -> str:
        """O identificador que vai para DENTRO do autenticador, e la fica.

        Nao e o id do banco: o autenticador guarda este valor e alguns o
        mostram na tela de escolha de conta. Derivado com a chave do cofre,
        entao e estavel (a mesma conta gera sempre o mesmo) sem carregar o
        numero da linha para fora do servidor.
        """
        return passkey.b64url(hmac.new(
            banco.chave_do_cofre(), ("passkey|%d" % usuario_id).encode("utf-8"),
            hashlib.sha256).digest())

    def _dar_sessao(self, usuario_id: int):
        """Abre a sessao completa e poe o cookie. O fim feliz das tres portas."""
        con = banco.conectar()
        try:
            cookie = banco.novo_token()
            banco.abrir_sessao(usuario_id, cookie,
                               banco.prazo(autenticacao.HORAS_DE_SESSAO * 3600),
                               con=con)
            # Rotaciona o identificador ao autenticar: e o que impede fixacao de
            # sessao, onde quem plantou o cookie antes continua dentro depois.
            final = banco.confirmar_segundo_fator(cookie, banco.novo_token(),
                                                  con=con)
        finally:
            con.close()
        self._por_cookie("sessao", final, autenticacao.HORAS_DE_SESSAO * 3600)

    # --------------------------------------------------- porta 1: a chave
    #
    # Sem `allowCredentials` de proposito. Mandar a lista de credenciais de uma
    # conta ANTES de a pessoa provar quem e entrega quantas chaves ela tem e os
    # ids delas a quem so digitou a cortina. A chave e descobrivel: o proprio
    # autenticador sabe qual oferecer.

    def _chave_desafio(self):
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        origem, agora_s = self._origem_do_pedido(), time.time()
        if not cortina.registrar_tentativa(origem, agora_s, balcao="passkey"):
            return self._json(429, self.RECUSA)
        bilhete, desafio = DESAFIOS.abrir(agora_s)
        self._por_cookie("desafio", bilhete, passkey.PRAZO_DO_DESAFIO)
        return self._json(200, {"desafio": passkey.b64url(desafio),
                                "rp_id": self._rp_id(),
                                "segundos": passkey.PRAZO_DO_DESAFIO})

    def _entrar_chave(self):
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        agora_s = time.time()
        if not cortina.registrar_tentativa(self._origem_do_pedido(), agora_s,
                                           balcao="passkey"):
            return self._json(429, self.RECUSA)
        corpo = self._corpo_json(teto=passkey.TETO_DO_CORPO * 4)
        # O bilhete morre aqui, deu certo ou nao: um desafio que sobrevive ao
        # fracasso e um desafio que pode ser tentado de novo.
        desafio = DESAFIOS.resgatar(self._ler_cookie("desafio"), agora_s)
        self._apagar_cookie("desafio")
        if corpo is None or desafio is None:
            return self._json(401, self.RECUSA)

        cred_id = self._texto_do_corpo(corpo, "cred_id", teto=2048)
        cliente = self._bytes_do_corpo(corpo, "cliente")
        autenticador = self._bytes_do_corpo(corpo, "autenticador")
        assinatura = self._bytes_do_corpo(corpo, "assinatura")
        if not cred_id or cliente is None or autenticador is None \
                or assinatura is None:
            return self._json(401, self.RECUSA)

        guardada = banco.chave_de_acesso(cred_id)
        if guardada is None:
            return self._json(401, self.RECUSA)
        lido = passkey.conferir_entrada(cliente, autenticador, assinatura,
                                        guardada["chave"], desafio,
                                        self._rp_id(), ORIGENS_OK)
        if lido is None:
            return self._json(401, self.RECUSA)
        # O contador so vale se for o BANCO a decidir: conferir aqui e gravar
        # depois deixa duas copias da mesma chave passarem juntas.
        if not banco.usar_chave_de_acesso(guardada["id"], lido["contador"]):
            return self._json(401, self.RECUSA)
        self._dar_sessao(guardada["usuario_id"])
        return self._json(200, {"ok": True})

    # ------------------------------------------ porta 3: codigo do papel
    #
    # A rota se chama /entrar/codigo, e nao /entrar/recuperacao, porque
    # "recuperaCAO" casa com a lista de bloqueio de `test_rotas.py` — a lista
    # que impede uma rota de executar comando na maquina do dono. O vigia
    # reprovou o nome e o nome mudou; afrouxar a lista para caber um nome
    # bonito seria afrouxar a unica coisa que impede a etapa 7 de voltar atras.

    def _entrar_codigo(self):
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="codigo"):
            return self._json(429, self.RECUSA)
        corpo = self._corpo_json(teto=4096)
        if corpo is None:
            return self._json(401, self.RECUSA)
        uid = banco.usar_codigo_de_recuperacao(
            self._texto_do_corpo(corpo, "codigo", teto=200))
        if uid is None:
            return self._json(401, self.RECUSA)
        self._dar_sessao(uid)
        # `restantes` volta so para quem ACERTOU, e ai nao ha o que vazar: quem
        # esta dentro ja pode ver isso na tela de chaves.
        return self._json(200, {"ok": True,
                                "restantes": banco.codigos_restantes(uid)})

    # ------------------------------------------- as chaves, ja la dentro

    def _chaves(self):
        sessao = self._sessao()
        uid = sessao["usuario_id"]
        con = banco.conectar()
        try:
            chaves = banco.chaves_de_acesso(uid, con=con)
            restantes = banco.codigos_restantes(uid, con=con)
        finally:
            con.close()
        return self._json(200, {
            "chaves": chaves, "restantes": restantes,
            # A regra dura do desenho: ninguem fica com UMA so. Uma chave e um
            # aparelho de distancia do bloqueio total, e quem decide o texto da
            # cobranca e a tela — aqui so vai o fato.
            "cobrar_a_segunda": len(chaves) < 2,
            "tem_codigos": restantes > 0})

    def _chave_cadastro_desafio(self):
        sessao = self._sessao()
        if not self._csrf_ok(sessao):
            return self._json(403, {"erro": "recarregue a pagina (token vencido)"})
        bilhete, desafio = DESAFIOS.abrir(time.time())
        self._por_cookie("desafio", bilhete, passkey.PRAZO_DO_DESAFIO)
        con = banco.conectar()
        try:
            l = con.execute("SELECT email, nome FROM usuario WHERE id = ?",
                            (sessao["usuario_id"],)).fetchone()
        finally:
            con.close()
        if l is None:
            return self._json(403, {"erro": "entre de novo"})
        return self._json(200, {
            "desafio": passkey.b64url(desafio), "rp_id": self._rp_id(),
            "usuario": {"id": self._handle_do_usuario(sessao["usuario_id"]),
                        "nome": l["email"], "mostrar": l["nome"] or l["email"]},
            # Os ids que o navegador deve RECUSAR cadastrar de novo. Sem isto, o
            # mesmo aparelho vira duas linhas na lista e o dono nao sabe qual
            # remover.
            "ja_tenho": [c["cred_id"] for c in
                         banco.chaves_de_acesso(sessao["usuario_id"])]})

    def _chave_cadastrar(self):
        sessao = self._sessao()
        if not self._csrf_ok(sessao):
            return self._json(403, {"erro": "recarregue a pagina (token vencido)"})
        corpo = self._corpo_json(teto=passkey.TETO_DO_CORPO * 4)
        desafio = DESAFIOS.resgatar(self._ler_cookie("desafio"), time.time())
        self._apagar_cookie("desafio")
        if corpo is None or desafio is None:
            return self._json(400, {"erro": "tente de novo"})
        cliente = self._bytes_do_corpo(corpo, "cliente")
        atestado = self._bytes_do_corpo(corpo, "atestado")
        if cliente is None or atestado is None:
            return self._json(400, {"erro": "tente de novo"})
        novo = passkey.conferir_cadastro(cliente, atestado, desafio,
                                         self._rp_id(), ORIGENS_OK)
        if novo is None:
            return self._json(400, {"erro": "o aparelho nao completou o cadastro"})
        apelido = self._texto_do_corpo(corpo, "apelido", teto=60).strip()
        try:
            banco.guardar_chave_de_acesso(
                sessao["usuario_id"], passkey.b64url(novo["cred_id"]),
                novo["chave"], apelido=apelido or "sem apelido",
                contador=novo["contador"])
        except sqlite3.IntegrityError:
            # Ja cadastrada. Nao e erro do dono, e a resposta diz isso — aqui
            # ele JA esta autenticado, entao nao ha oraculo a proteger.
            return self._json(409, {"erro": "este aparelho ja esta cadastrado"})
        return self._json(200, {"ok": True})

    def _chave_remover(self):
        sessao = self._sessao()
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._json(403, {"erro": "recarregue a pagina (token vencido)"})
        corpo = self._corpo_json(teto=4096)
        if corpo is None:
            return self._json(400, {"erro": "pedido invalido"})
        try:
            alvo = int(corpo.get("id"))
        except (TypeError, ValueError):
            return self._json(400, {"erro": "faltou o id da chave"})
        # O dono vai na clausula do UPDATE, dentro de `banco`: sem ele, mandar
        # um id vizinho apaga a chave da outra pessoa.
        if not banco.revogar_chave_de_acesso(alvo, sessao["usuario_id"]):
            return self._json(404, {"erro": "essa chave nao e sua"})
        return self._json(200, {"ok": True,
                                "restam": len(banco.chaves_de_acesso(
                                    sessao["usuario_id"]))})

    def _codigos_gerar(self):
        sessao = self._sessao()
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._json(403, {"erro": "recarregue a pagina (token vencido)"})
        # A UNICA vez que estes codigos existem em claro fora do papel do dono.
        # Nao vao para log, nao voltam numa segunda chamada, nao ficam no banco.
        return self._json(200, {
            "codigos": banco.gerar_codigos_de_recuperacao(sessao["usuario_id"]),
            "aviso": "anote agora; eles nao aparecem de novo"})

    def _sair(self):
        # `SameSite=Lax` ja impede o cookie de acompanhar um POST de outro site,
        # entao um pedido forjado chegaria sem sessao e nao encerraria nada. O
        # `Origin` entra assim mesmo: e a unica rota de escrita que estava sem o
        # par que `/api/silenciar` mantem, e defesa em camada nao se dispensa
        # por "a outra ja resolve".
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        cookie = self._ler_cookie("sessao")
        if cookie:
            banco.encerrar_sessao(cookie)
        self._apagar_cookie("sessao")
        self._apagar_cookie("cortina")
        return self._json(200, {"ok": True})

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
        # A rota e de `acesso="dado"`, entao o despacho ja garantiu que ha
        # sessao completa. Aqui so falta o anti-CSRF DAQUELA sessao.
        sessao = self._sessao()
        if sessao is None:
            # A sessao pode ter vencido entre o despacho e esta linha. Sem esta
            # guarda, `_csrf_da_sessao(None)` levantaria TypeError e devolveria
            # 500 onde o certo e 403.
            return self._json(403, {"erro": "entre de novo"})
        if not secrets.compare_digest(self.headers.get("X-Token") or "",
                                      self._csrf_da_sessao(sessao)):
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
        banco.silenciar(pid, ate, usuario_id=sessao["usuario_id"])
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
        for cookie in self._cookies_pendentes:
            self.send_header("Set-Cookie", cookie)
        self._cookies_pendentes = []
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
# `acesso` e o terceiro campo, e ele e OBRIGATORIO (etapa 9). Tres valores:
#
#   "aberta"   qualquer um alcanca. A capa e os quatro estaticos.
#   "cortina"  exige o selo da combinacao de seis digitos.
#   "dado"     exige sessao COMPLETA — senha ou GitHub, mais segundo fator.
#
# Rota sem classificacao declarada REPROVA a suite em `test_rotas.py`. A negativa
# e o padrao inclusive no teste: esquecer de classificar nao pode dar acesso.
Rota = namedtuple("Rota", "metodo funcao acesso")

ROTAS = {
    "/":                        Rota("GET",  Hub._pagina,         "aberta"),
    "/index.html":              Rota("GET",  Hub._pagina,         "aberta"),
    "/entrada":                 Rota("POST", Hub._entrada,        "aberta"),
    "/entrar/github":           Rota("GET",  Hub._entrar_github,  "cortina"),
    "/entrar/github/retorno":   Rota("GET",  Hub._retorno_github, "cortina"),
    "/sair":                    Rota("POST", Hub._sair,           "aberta"),
    "/api/dados":               Rota("GET",  Hub._dados,          "dado"),
    "/api/silenciar":           Rota("POST", Hub._silenciar,      "dado"),

    # As portas de entrada. As tres primeiras sao "cortina" — quem chega ainda
    # nao tem sessao, e e para isso que elas existem. As quatro de baixo sao
    # "dado": so mexe nas proprias chaves quem ja provou ser dono da conta.
    "/entrar/chave/desafio":    Rota("POST", Hub._chave_desafio,   "cortina"),
    "/entrar/chave":            Rota("POST", Hub._entrar_chave,    "cortina"),
    "/entrar/codigo":           Rota("POST", Hub._entrar_codigo,     "cortina"),
    "/api/chaves":              Rota("GET",  Hub._chaves,          "dado"),
    "/api/chaves/desafio":      Rota("POST", Hub._chave_cadastro_desafio, "dado"),
    "/api/chaves/cadastrar":    Rota("POST", Hub._chave_cadastrar, "dado"),
    "/api/chaves/remover":      Rota("POST", Hub._chave_remover,   "dado"),
    "/api/codigos/gerar":       Rota("POST", Hub._codigos_gerar,    "dado"),
}
ROTAS.update({caminho: Rota("GET", Hub._estatico, "aberta")
              for caminho in ESTATICOS_OK})

# A porta do ambiente local NAO EXISTE no servidor — nem como 403, nem como
# caminho reconhecido. Nao ha `if` dentro da rota que segure tanto quanto a rota
# nao estar na tabela: `test_rotas.py` le esta estrutura em memoria, entao a
# ausencia dela e verificavel sem subir servidor nenhum.
if E_LOCAL:
    ROTAS["/entrar/local"] = Rota("GET", Hub._entrar_local, "cortina")


def main():
    con = banco.conectar()
    # A combinacao nasce aqui e aparece UMA vez. Depois desta linha ela nao
    # existe mais em lugar nenhum deste sistema — so a impressao digital, que
    # nao volta a ser numero.
    combinacao = cortina.garantir_combinacao(con)
    vazio = not banco.montar_estado(con)["projetos"]
    con.close()
    if combinacao:
        print("=" * 62)
        print("COMBINACAO DE ACESSO: %s" % combinacao)
        print("Anote agora. Ela NAO aparece de novo.")
        print("=" * 62)
    if not GITHUB_ID or not GITHUB_SECRET:
        print("AVISO: sem DERVS_GITHUB_ID/DERVS_GITHUB_SECRET, a entrada por"
              " GitHub responde 404. Ver docs/operacao/registrar-app-github.md.")
    if E_LOCAL:
        print("AMBIENTE LOCAL: dado de mentira, e a porta /entrar/local esta"
              " aberta atras da cortina. Combinacao: %s"
              % cortina.COMBINACAO_LOCAL)
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
