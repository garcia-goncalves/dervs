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

import json
import os
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import banco
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

PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 4777
INTERVALO = int(sys.argv[2]) if len(sys.argv) > 2 else 60

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

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        if not self._host_confiavel():
            return self._json(403, {"erro": "host não permitido"})
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
