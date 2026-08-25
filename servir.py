# -*- coding: utf-8 -*-
"""Servidor do HUB do dev.

Serve a pagina, o endpoint /api/dados (que le o SQLite e roda as 14 regras) e o
/api/acao, que executa a acao de uma pendencia.

    python servir.py            # http://localhost:4777
    python servir.py 4780 30    # outra porta, outro intervalo da camada local

TRES CADENCIAS, e e de proposito:
    local   a cada 60 s     git, Docker, portas, grafo, memoria  (so disco)
    github  a cada 20 min   CI, PRs, alertas                     (rede, cota)
    pesado  a cada 24 h     cota do Actions, npm audit           (caro)
A tela nunca espera nenhuma delas: le sempre o ultimo valor do banco e mostra o
carimbo de quando aquele numero foi medido.

SEGURANCA — por que ha um token aqui

Ate hoje este servidor so LIA. Agora ele executa `git push`, `docker compose up`
e abre o VS Code. Escutar so em 127.0.0.1 protege contra a rede, mas NAO protege
contra o navegador do proprio dono: qualquer site aberto numa outra aba pode
disparar um POST para http://localhost:4777. Por isso toda acao exige:

  1. um token sorteado a cada inicializacao, injetado so na pagina que servimos;
  2. cabecalho Origin da propria origem, quando o navegador manda;
  3. cabecalho Host de localhost — barra o truque de apontar um dominio para
     127.0.0.1 (DNS rebinding).

E o cliente nunca manda caminho: manda o NOME do projeto, e o caminho vem do
banco. Assim nao existe "acao" que rode em pasta escolhida por quem chamou.
"""
from __future__ import annotations

import http.client
import json
import os
import posixpath
import re
import shutil
import socket
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import banco
import execucao
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
        r = subprocess.run([sys.executable, str(script)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           creationflags=SEM_JANELA)
        marca = time.strftime("%H:%M:%S")
        if r.returncode == 0:
            _ultima_falha.pop(camada, None)
            print("[%s] %s (%s) em %.1fs — %s"
                  % (marca, camada, motivo, time.time() - inicio, r.stdout.strip()))
        else:
            _ultima_falha[camada] = (r.stderr or "").strip()[:400]
            print("[%s] FALHA em %s (%s):\n%s" % (marca, camada, motivo,
                                                  _ultima_falha[camada]))


def laco(camada: str, intervalo: int):
    while True:
        time.sleep(intervalo)
        coletar(camada, "automática")


# --------------------------------------------------------------------- acoes
def _projetos_por_nome() -> dict:
    return {p["nome"]: p for p in banco.montar_estado()["projetos"]}


def _resumo_da_execucao() -> dict:
    """So o cabecalho da execucao, para o /api/dados nao carregar o log inteiro."""
    e = execucao.estado(10 ** 9)          # `desde` alto de proposito: log vazio
    return {"estado": e["estado"], "projeto": e["projeto"],
            "pendencia_id": e["pendencia_id"]}


def _pendencia_por_id(pid: str):
    """A pendencia RECALCULADA aqui dentro, nunca a que veio do navegador.

    O cliente manda so o id. Se o servidor confiasse no resto do corpo, o texto
    da pendencia — que vai dentro do prompt da sessao do Claude — passaria a ser
    escolhido por quem faz o POST. Recalcular e o que mantem o prompt fechado.
    """
    con = banco.conectar()
    try:
        e = banco.montar_estado(con)
        pend = regras.avaliar(e["projetos"], quota=e["quota"],
                              silenciadas=banco.silenciadas(con))
    finally:
        con.close()
    for p in pend:
        if p.get("id") == pid:
            return p
    return None


def _rodar(args, cwd=None, shell=False, limite=180):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=limite,
                       shell=shell, creationflags=SEM_JANELA)
    saida = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    return r.returncode == 0, saida[-1200:]


def acao_git_push(p):
    return _rodar(["git", "-C", p["caminho"], "push"])


def acao_docker_up(p):
    return _rodar(["docker", "compose", "up", "-d"], cwd=p["caminho"], limite=300)


def acao_vscode(p):
    # `code` no Windows e um .cmd: o CreateProcess nao acha sozinho. "cmd /c"
    # resolve SEM shell=True, entao o caminho vai como argumento, nunca como
    # texto de linha de comando — nada nele pode virar comando.
    ok, saida = _rodar(["cmd", "/c", "code", p["caminho"]], limite=30)
    return ok, saida or "VS Code aberto."


def acao_crlf_para_lf(p):
    """Reescreve os arquivos de memoria trocando CRLF por LF.

    Toca SO os .md listados na medida — nao varre pasta, nao adivinha caminho.
    """
    convertidos = []
    slug = p["caminho"].replace("\\", "-").replace("/", "-").replace(":", "-")
    pasta = Path.home() / ".claude" / "projects" / slug / "memory"
    for nome in p.get("memoria_crlf") or []:
        alvo = pasta / nome
        if not alvo.is_file() or alvo.parent != pasta:
            continue
        bruto = alvo.read_bytes()
        if b"\r\n" in bruto:
            alvo.write_bytes(bruto.replace(b"\r\n", b"\n"))
            convertidos.append(nome)
    if not convertidos:
        return False, "nenhum arquivo para converter (talvez já tenha sido feito)."
    return True, "convertidos: " + ", ".join(convertidos)


ACOES = {
    "git_push": acao_git_push,
    "docker_up": acao_docker_up,
    "vscode": acao_vscode,
    "crlf_para_lf": acao_crlf_para_lf,
}


def executar_acao(corpo: dict):
    comando = corpo.get("comando")

    if comando == "recoletar":
        camada = corpo.get("camada", "local")
        if camada not in COLETORES:
            return False, "camada desconhecida."
        coletar(camada, "pedido da tela")
        return True, "recoletado."

    if comando == "silenciar":
        pid = corpo.get("id")
        if not pid:
            return False, "faltou o id da pendência."
        try:
            horas = max(1, min(24 * 30, int(corpo.get("horas") or 24)))
        except (TypeError, ValueError):
            return False, "prazo inválido."
        ate = (datetime.now(timezone.utc) + timedelta(hours=horas)).isoformat(timespec="seconds")
        banco.silenciar(pid, ate)
        return True, "silenciada por %d h." % horas

    if comando == "grafo_ligar":
        return acao_grafo_ligar()

    if comando == "resolver":
        pid = corpo.get("id")
        if not pid:
            return False, "faltou o id da pendência."
        pend = _pendencia_por_id(pid)
        if not pend:
            return False, "pendência desconhecida."
        # Barreira DURA do lado do servidor. A tela tambem esconde o botao, mas
        # esconder e conveniencia; quem recusa de verdade e esta linha.
        if not execucao.pode_resolver(pend):
            return False, "esta pendência não pode ser resolvida automaticamente."
        p = _projetos_por_nome().get(pend.get("projeto") or "")
        if not p or not p.get("caminho"):
            return False, "projeto desconhecido."
        try:
            decisao = execucao.iniciar(pend, p["caminho"])
        except Exception as e:                   # nunca derrubar o servidor
            return False, "falhou ao iniciar: %s" % e
        if decisao == "recusada":
            return False, "já há uma execução em andamento."
        return True, decisao

    if comando == "parar":
        try:
            confirmou = execucao.parar()
        except Exception as e:
            return False, "falhou ao parar: %s" % e
        if confirmou:
            return True, "parada."
        return False, "não consegui confirmar que parou."

    if comando not in ACOES:
        return False, "comando não permitido."

    p = _projetos_por_nome().get(corpo.get("projeto") or "")
    if not p:
        return False, "projeto desconhecido."
    try:
        ok, saida = ACOES[comando](p)
    except subprocess.TimeoutExpired:
        return False, "o comando demorou demais e foi interrompido."
    except Exception as e:                       # nunca derrubar o servidor por uma acao
        return False, "falhou: %s" % e
    if ok:
        coletar("local", "depois da ação")       # o numero na tela vira verdade na hora
    return ok, saida



# ------------------------------------------------------------------- o grafo
"""O grafo de codigo (codebase-memory-mcp) embutido no HUB.

TRES FATOS MEDIDOS EM 24/08/2026, nao supostos:

1. A porta 9749 nao e um servidor independente: e a UI de um servidor MCP de
   stdio. Com o stdin fechado, o processo registra `ui.serving` e em seguida
   `server.shutdown` NO MESMO SEGUNDO — a porta abre e fecha, e a tela fica em
   branco sem nenhum erro. O que o mantem de pe e o cano de entrada ABERTO,
   guardado em _grafo_proc. Consequencia aceita de proposito: o grafo vive
   enquanto o HUB viver e morre junto. E melhor que a alternativa — este binario
   ja congelou a maquina duas vezes por consumo de memoria, e processo orfao
   ninguem lembra de matar.

2. A tela do grafo pede caminho ABSOLUTO: /api/..., /assets/... e /rpc. Servida
   sob /grafo/ ela pediria /api/index-status na raiz do HUB, onde mora o
   /api/dados do painel. Por isso o proxy reescreve o corpo de texto.

3. Ela expoe /api/process-kill. Matar processo pela tela nao e funcao do HUB, e
   o proxy recusa esse caminho — lista de bloqueio, nao de permissao, para nao
   quebrar a tela a cada versao nova do grafo.

SEGURANCA — o que a mesma origem custa, dito por escrito

Embutir na mesma origem resolve X-Frame-Options, SameSite e CORS de uma vez, mas
tem preco: um quadro de mesma origem le o DOM da pagina que o contem, inclusive o
TOKEN de acao do HUB. Isso e ACEITO conscientemente — o binario do grafo ja roda
como MCP com acesso total ao codigo e ao disco desta maquina; o token so agrega
`git push`, `docker compose up` e abrir o VS Code, que qualquer processo local ja
faz. O que NAO e aceito, e por isso e barrado aqui:

  - falsificacao de pedido vinda de outro site (o vizinho de aba do dono
    disparando uma reindexacao pesada): o POST do proxy exige
    `Sec-Fetch-Site: same-origin` quando o cabecalho existe. Navegador nenhum
    deixa JS forjar esse cabecalho. Ausente = cliente que nao e navegador, que
    nao tem credencial de ambiente para roubar.
  - vazamento do token PARA o grafo: o proxy sobe um conjunto minimo de
    cabecalhos. X-Token, Cookie, Authorization e Origin ficam aqui.
"""
GRAFO_HOST = "127.0.0.1"
GRAFO_PORTA = 9749
GRAFO_PREFIXO = "/grafo"
GRAFO_ESPERA = 45                       # s ate desistir do estado "subindo"
GRAFO_BLOQUEADOS = {"/api/process-kill"}


def _achar_grafo_exe():
    """Caminho fixo primeiro, PATH depois.

    No Windows o shutil.which poe o DIRETORIO ATUAL na frente do PATH. Se o HUB
    fosse lancado de uma pasta com um codebase-memory-mcp.exe plantado, era ele
    que subiria. Cenario fraco, correcao gratuita.
    """
    for c in (Path.home() / ".local" / "bin" / "codebase-memory-mcp.exe",
              Path.home() / ".local" / "bin" / "codebase-memory-mcp"):
        if c.is_file():
            return str(c)
    return shutil.which("codebase-memory-mcp")


GRAFO_EXE = _achar_grafo_exe()

_grafo_proc = None
_grafo_ligado_em = 0.0
_grafo_trava = threading.Lock()


def caminho_do_grafo(caminho: str):
    """/grafo/x -> /x. Devolve None quando o pedido nao e do grafo.

    Recusa `..` em vez de normalizar: normalizar significaria decidir por conta
    propria o que o dono quis dizer, e aqui do outro lado ha um servidor de
    terceiro. Recusar e mais curto de ler e nao tem caso de canto.
    """
    if caminho != GRAFO_PREFIXO and not caminho.startswith(GRAFO_PREFIXO + "/"):
        return None
    resto = caminho[len(GRAFO_PREFIXO):] or "/"
    if not resto.startswith("/"):
        return None
    if ".." in resto.split("?", 1)[0].split("#", 1)[0].split("/"):
        return None
    return resto


def grafo_bloqueado(caminho: str) -> bool:
    """Recusa /api/process-kill, inclusive disfarcado.

    Comparar a string crua nao servia: o http.server nao decodifica self.path, e
    quem decide o que "/api/./x" ou "/api/proc%65ss-kill" significa e o servidor
    de DESTINO. Na versao medida em 24/08/2026 o grafo devolvia 404 para todos
    os disfarces — ou seja, a barreira estava furada e so nao doia porque o
    outro lado nao cooperava. Como a API dele muda de versao em versao, a
    normalizacao acontece AQUI: decodifica ate estabilizar, corta fragmento e
    query, colapsa barras e resolve "." e "..".
    """
    c = caminho.split("#", 1)[0].split("?", 1)[0]
    for _ in range(3):                      # %2565 -> %65 -> e
        d = unquote(c)
        if d == c:
            break
        c = d
    # normpath do POSIX PRESERVA barra dupla no inicio ("//api" fica "//api"),
    # entao as barras sao colapsadas antes.
    c = re.sub(r"/+", "/", "/" + c.replace(chr(92), "/"))
    c = posixpath.normpath(c).rstrip("/").lower()
    return (c or "/") in GRAFO_BLOQUEADOS


# O delimitador na frente e o que separa caminho de verdade de coincidencia:
# sem ele, "/apiario" e "https://x/api/y" tambem seriam reescritos. As TRES
# aspas do JavaScript entram — a crase custou um 404 em 24/08/2026, porque a
# tela monta `/api/layout?...` e `/api/browse${X}` assim, e so isso escapou.
_ALVO = re.compile(rb"""(["'`])/(api/|assets/|rpc(?=["'`?]))""")


def reescrever_para_o_hub(corpo: bytes) -> bytes:
    """Faz a tela do grafo pedir /grafo/... em vez de /...

    E idempotente: depois da troca, o que vem apos o delimitador e /grafo/, que
    padrao nenhum casa. Vale porque o proxy nao pede compressao — corpo
    comprimido passaria intacto por aqui e a tela quebraria calada.

    NAO casa `/${e}`, que no mesmo pacote monta caminho de PASTA e nao URL.
    """
    return _ALVO.sub(lambda m: m.group(1) + b"/grafo/" + m.group(2), corpo)


_TIPOS_TEXTO = {"application/javascript", "text/javascript", "application/json",
                "application/xml", "image/svg+xml", "application/manifest+json"}


def e_texto(content_type: str) -> bool:
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    return ct.startswith("text/") or ct in _TIPOS_TEXTO


def pode_repassar(content_type: str, content_encoding) -> bool:
    """Falso quando o corpo e texto E veio comprimido.

    O proxy nao pede compressao, mas isso e suposicao sobre binario de TERCEIRO.
    Sem esta checagem, gzip sairia daqui rotulado como JavaScript e SEM
    Content-Encoding: o navegador leria bytes comprimidos como codigo, e a tela
    ficaria em branco sem log, sem erro, sem nada — a falha muda que este proxy
    existe para evitar. Binario (fonte, imagem) nao e reescrito, entao comprimido
    passa intacto.
    """
    ce = (content_encoding or "").strip().lower()
    if not ce or ce == "identity":
        return True
    return not e_texto(content_type)


def cabecalhos_para_o_grafo(entrada) -> dict:
    """O conjunto MINIMO que sobe. Tudo o mais fica no HUB.

    X-Token, Cookie, Authorization e Origin nao atravessam: o grafo e software
    de terceiro e nao tem nada que ver com eles. Accept-Encoding tambem nao vai,
    e e por isso que o corpo volta sem compressao e pode ser reescrito.
    """
    fora = {"Accept": _um_valor(entrada.get("Accept") or "*/*")}
    ct = entrada.get("Content-Type")
    if ct:
        fora["Content-Type"] = _um_valor(ct)
    return fora


def _um_valor(v: str) -> str:
    """Achata cabecalho dobrado (obs-fold) num valor de linha unica.

    O http.client aceita LF nu no valor e o emite. O destino de hoje une como
    continuacao; o de amanha pode ler como cabecalho novo.
    """
    return " ".join(str(v).replace(chr(13), " ").replace(chr(10), " ").split())


def origem_aceita(sec_fetch_site) -> bool:
    """A defesa contra pedido vindo de OUTRO SITE — para GET e para POST.

    Sec-Fetch-Site nao e forjavel por JavaScript. Ausente = cliente que nao e
    navegador (ou navegador anterior ao Safari 16.4), e ai nao ha credencial de
    ambiente para abusar.

    Estava so no POST ate a revisao de 24/08/2026, enquanto o README ja dizia
    que cobria "pedido vindo de outro site". Cobria metade: por GET, qualquer
    aba do dono varria a API do grafo, inclusive /api/browse, que lista pasta do
    disco. O atacante nao LIA a resposta (nao emitimos CORS), mas a proxima
    versao do grafo pode ganhar um GET com efeito, e nada aqui avisaria.
    """
    return not sec_fetch_site or sec_fetch_site == "same-origin"


def csp_para_o_hub(do_grafo):
    """Repassa a politica do fornecedor, menos a recusa de ser enquadrado.

    O grafo manda Content-Security-Policy com script-src 'self' e object-src
    'none'. O proxy descartava tudo — e o codigo de terceiro passava a rodar SEM
    politica na origem que guarda o token do HUB. Isso importa menos pelo
    binario (que ja tem o disco inteiro) e mais pelo que ele INDEXA: nome de
    funcao e caminho de arquivo vindos de um repositorio hostil sao desenhados
    por essa tela.

    frame-ancestors sai porque e justamente o que impediria o quadro. E uma
    recusa do fornecedor que este desenho contorna de propria conta — fica
    registrado aqui e no README.
    """
    if not do_grafo:
        return None
    partes = [d.strip() for d in do_grafo.split(";")
              if d.strip() and not d.strip().lower().startswith("frame-ancestors")]
    return "; ".join(partes) or None


def classificar_grafo(no_ar: bool, tem_exe: bool, subindo: bool) -> str:
    if no_ar:
        return "no_ar"
    if not tem_exe:
        return "sem_exe"
    return "subindo" if subindo else "fora"


def _grafo_no_ar() -> bool:
    try:
        with socket.create_connection((GRAFO_HOST, GRAFO_PORTA), 0.35):
            return True
    except OSError:
        return False


def grafo_estado() -> dict:
    espera = time.time() - _grafo_ligado_em
    subindo = (_grafo_proc is not None and _grafo_proc.poll() is None
               and espera < GRAFO_ESPERA)
    return {"estado": classificar_grafo(_grafo_no_ar(), GRAFO_EXE is not None, subindo),
            "porta": GRAFO_PORTA,
            "ha": int(espera) if subindo else None}


def acao_grafo_ligar():
    """Sobe o grafo mantendo o stdin aberto — ver o fato 1 la em cima."""
    global _grafo_proc, _grafo_ligado_em
    with _grafo_trava:
        if _grafo_no_ar():
            return True, "o grafo já estava no ar."
        if GRAFO_EXE is None:
            return False, "não achei o codebase-memory-mcp nesta máquina."
        if _grafo_proc is not None and _grafo_proc.poll() is None:
            return True, "o grafo já está subindo."
        extra = ({"creationflags": 0x00000008 | 0x00000200}   # DETACHED | NEW_GROUP
                 if sys.platform.startswith("win") else {"start_new_session": True})
        _grafo_proc = subprocess.Popen(
            [GRAFO_EXE, "--ui=true", "--port=%d" % GRAFO_PORTA],
            stdin=subprocess.PIPE,                 # NAO fechar: e o que o segura vivo
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)
        _grafo_ligado_em = time.time()
    return True, "ligando o grafo…"


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

    # ------------------------------------------------------------------- GET
    def do_GET(self):
        if not self._host_confiavel():
            return self._json(403, {"erro": "host não permitido"})

        if self.path.startswith("/api/dados"):
            return self._json(200, self._estado())

        if self.path in ("/", "/index.html"):
            return self._pagina()

        if self.path in ESTATICOS_OK:
            return super().do_GET()

        # Rota leve: enquanto o grafo sobe, a tela pergunta so isto de 2 em 2 s,
        # em vez de puxar o /api/dados inteiro (que roda as 14 regras).
        if self.path == "/api/grafo":
            return self._json(200, grafo_estado())

        # Consulta do painel de execucao, de 1 em 1 segundo enquanto roda.
        #
        # NAO exija Origin aqui. O navegador nao manda Origin em GET de mesma
        # origem — a rota responderia 403 sempre, e o log ficaria parado para
        # sempre na cara do dono. O par certo para GET e Sec-Fetch-Site, que e
        # o mesmo que o proxy do grafo usa, exatamente por este motivo. O token
        # continua obrigatorio: e ele que separa esta pagina de outra aba.
        if self.path.startswith("/api/execucao"):
            if not origem_aceita(self.headers.get("Sec-Fetch-Site")):
                return self._json(403, {"erro": "origem não permitida"})
            if not secrets.compare_digest(self.headers.get("X-Token") or "", TOKEN):
                return self._json(403, {"erro": "recarregue a página (token vencido)"})
            desde = 0
            if "?" in self.path:
                for par in self.path.split("?", 1)[1].split("&"):
                    if par.startswith("desde="):
                        try:
                            desde = max(0, int(par[len("desde="):]))
                        except ValueError:
                            desde = 0
            return self._json(200, execucao.estado(desde))

        alvo = caminho_do_grafo(self.path)
        if alvo is not None:
            return self._proxy_grafo("GET", alvo)

        return self._json(404, {"erro": "não existe"})

    def _estado(self):
        con = banco.conectar()
        try:
            e = banco.montar_estado(con)
            pend = regras.avaliar(e["projetos"], quota=e["quota"],
                                  silenciadas=banco.silenciadas(con))
        finally:
            con.close()
        return {
            "agora": banco.agora(),
            "pendencias": pend,
            "projetos": e["projetos"],
            "infra": e["infra"],
            "infra_medido_em": e["infra_medido_em"],
            "quota": e["quota"],
            "grafo_ui": grafo_estado(),
            "falhas_de_coleta": dict(_ultima_falha),   # copia: o vivo muda em outra thread
            # Resumo leve da execucao: e o que faz o botao virar "Ver execução"
            # sem a tela precisar de uma segunda consulta. O log NAO vem aqui.
            "execucao": _resumo_da_execucao(),
            # A regra de quem pode ser resolvido mora no servidor; a tela so a
            # repete para esconder o botao. Duas copias da regra divergem.
            "resolver_bloqueado": sorted(execucao.PROJETOS_BLOQUEADOS),
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

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        if not self._host_confiavel():
            return self._json(403, {"erro": "host não permitido"})
        alvo = caminho_do_grafo(self.path)
        if alvo is not None:
            return self._proxy_grafo("POST", alvo)

        if self.path != "/api/acao":
            return self._json(404, {"erro": "não existe"})

        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem não permitida"})
        if not secrets.compare_digest(self.headers.get("X-Token") or "", TOKEN):
            return self._json(403, {"erro": "recarregue a página (token vencido)"})

        try:
            n = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(min(n, 16_384)) or b"{}")
        except (ValueError, OSError):
            return self._json(400, {"erro": "pedido inválido"})

        ok, saida = executar_acao(corpo)
        return self._json(200 if ok else 500, {"ok": ok, "saida": saida})

    # ----------------------------------------------------------- proxy /grafo
    def _proxy_grafo(self, metodo: str, alvo: str):
        # Vale para GET E para POST. Ate 24/08/2026 valia so para POST, e por
        # GET qualquer aba do dono varria a API do grafo — inclusive a rota que
        # lista pasta do disco.
        if not origem_aceita(self.headers.get("Sec-Fetch-Site")):
            return self._json(403, {"erro": "origem não permitida"})
        if grafo_bloqueado(alvo):
            return self._json(403, {"erro": "esta ação do grafo não passa pelo HUB"})

        corpo = b""
        if metodo == "POST":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(max(0, min(n, 4 * 1024 * 1024)))
            except (ValueError, OSError):
                return self._json(400, {"erro": "pedido inválido"})

        # So estes sobem. Repassar tudo levaria o X-Token do HUB junto — e sem
        # Accept-Encoding o grafo responde sem compressao, que e o que permite
        # reescrever o corpo.
        cabecalhos = cabecalhos_para_o_grafo(self.headers)

        con = None
        try:
            con = http.client.HTTPConnection(GRAFO_HOST, GRAFO_PORTA, timeout=20)
            con.request(metodo, alvo, body=corpo or None, headers=cabecalhos)
            r = con.getresponse()
            bruto = r.read()
            tipo = r.getheader("Content-Type") or "application/octet-stream"
            comprimido = r.getheader("Content-Encoding")
            politica = csp_para_o_hub(r.getheader("Content-Security-Policy"))
            codigo = r.status
        except (OSError, http.client.HTTPException):
            return self._json(502, {"erro": "o grafo não está respondendo"})
        finally:
            if con is not None:
                con.close()

        if not pode_repassar(tipo, comprimido):
            # Falhar alto: servir gzip rotulado como JavaScript daria tela em
            # branco sem log nenhum, que e a falha muda que este proxy evita.
            return self._json(502, {"erro": "o grafo respondeu comprimido e o "
                                            "painel não consegue reescrever"})
        if e_texto(tipo):
            bruto = reescrever_para_o_hub(bruto)

        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        if comprimido:                          # so chega aqui se for binario
            self.send_header("Content-Encoding", comprimido)
        if politica:
            self.send_header("Content-Security-Policy", politica)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(bruto)))
        self.end_headers()
        self.wfile.write(bruto)

    def do_HEAD(self):
        """Recusado.

        Sem isto o HEAD caia no SimpleHTTPRequestHandler e servia a PASTA
        INTEIRA sem passar nem pela checagem de Host. Nao vazava conteudo (HEAD
        nao tem corpo), mas vazava existencia, tamanho e data do banco, do
        arquivo de variaveis e do .git/config. Revisao de 24/08/2026.
        """
        return self._json(405, {"erro": "método não permitido"})

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


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
