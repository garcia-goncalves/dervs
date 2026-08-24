# -*- coding: utf-8 -*-
"""Servidor do Painel de Projetos.

Serve index.html e o endpoint /api/dados, e mantem dados.json fresco
executando coletar.py em segundo plano no intervalo configurado.

    python servir.py            # http://localhost:4777, recoleta a cada 60 s
    python servir.py 4780 30    # outra porta, outro intervalo

So escuta em 127.0.0.1: o painel nao fica exposto na rede.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
COLETOR = AQUI / "coletar.py"
DADOS = AQUI / "dados.json"

PORTA = int(sys.argv[1]) if len(sys.argv) > 1 else 4777
INTERVALO = int(sys.argv[2]) if len(sys.argv) > 2 else 60

_trava = threading.Lock()
_ultima = 0.0


def coletar(motivo: str) -> None:
    """Executa o coletor. Serializado: duas coletas nunca se atropelam."""
    global _ultima
    with _trava:
        inicio = time.time()
        r = subprocess.run([sys.executable, str(COLETOR)], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        _ultima = time.time()
        marca = time.strftime("%H:%M:%S")
        if r.returncode == 0:
            print(f"[{marca}] coleta ({motivo}) em {_ultima - inicio:.1f}s — {r.stdout.strip()}")
        else:
            print(f"[{marca}] FALHA na coleta ({motivo}):\n{r.stderr.strip()[:900]}")


def laco():
    while True:
        time.sleep(INTERVALO)
        coletar("automática")


class Painel(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(AQUI), **kw)

    def log_message(self, *a):        # silencia o log de acesso, ruidoso demais
        pass

    def do_GET(self):
        if self.path.startswith("/api/dados"):
            if "recoletar=1" in self.path:
                coletar("pedido da tela")
            try:
                corpo = DADOS.read_bytes()
            except OSError:
                coletar("primeira")
                corpo = DADOS.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
            return
        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    if not DADOS.exists():
        coletar("inicial")
    else:
        try:
            json.loads(DADOS.read_text(encoding="utf-8"))
        except ValueError:
            coletar("dados.json corrompido")

    threading.Thread(target=laco, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Painel)
    print(f"Painel de Projetos no ar: http://localhost:{PORTA}")
    print(f"Recoleta automática a cada {INTERVALO}s. Ctrl+C encerra.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
