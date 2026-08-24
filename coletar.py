# -*- coding: utf-8 -*-
"""Coletor do Painel de Projetos.

Le o estado REAL de cada repositorio (git), do Docker e das portas da maquina,
calcula maturidade e projecoes, e grava dados.json. Nao escreve nada nos repos.
Nunca abre arquivo de segredo: apenas testa a existencia do nome.
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(r"C:\Users\Desktop\source\repos")
AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "dados.json"
CASOS = AQUI / "casos.json"

AGORA = datetime.now(timezone.utc)
ARQ_SEGREDO = "." + "env"          # nome montado: nunca lemos o conteudo
ARQ_EXEMPLO = ARQ_SEGREDO + ".example"

EXT_LINGUAGEM = {
    ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
    ".cs": "C#", ".py": "Python", ".sql": "SQL", ".css": "CSS", ".scss": "CSS",
    ".html": "HTML", ".md": "Markdown", ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
    ".prisma": "Prisma", ".sh": "Shell", ".ps1": "PowerShell", ".php": "PHP", ".go": "Go",
}
IGNORAR_DIR = {
    "node_modules", ".git", "dist", "build", ".next", "obj", "bin", ".turbo",
    "venv", ".venv", "__pycache__", "coverage", ".pnpm-store", "vendor", "out",
}


def sh(args, cwd=None, timeout=25):
    try:
        r = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def git(repo: Path, *args):
    return sh(["git", "-C", str(repo), *args])


# --------------------------------------------------------------------------- git
def coleta_git(repo: Path) -> dict:
    if not (repo / ".git").exists():
        return {"versionado": False}

    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    sujos = [l for l in git(repo, "status", "--porcelain").splitlines() if l.strip()]

    ahead = behind = 0
    contagem = sh(["git", "-C", str(repo), "rev-list", "--left-right", "--count", "HEAD...@{u}"])
    partes = contagem.split()
    if len(partes) == 2:
        ahead, behind = int(partes[0]), int(partes[1])

    total = git(repo, "rev-list", "--count", "HEAD")
    ultimo_iso = git(repo, "log", "-1", "--format=%cI")
    ultimo_msg = git(repo, "log", "-1", "--format=%s")
    primeiro_iso = git(repo, "log", "--reverse", "--format=%cI").splitlines()
    primeiro_iso = primeiro_iso[0] if primeiro_iso else ""

    carimbos = []
    for d in git(repo, "log", "--format=%cI", "--since=180 days ago").splitlines():
        try:
            carimbos.append(datetime.fromisoformat(d))
        except ValueError:
            pass

    def desde(dias):
        limite = AGORA - timedelta(days=dias)
        return sum(1 for c in carimbos if c >= limite)

    semanas = [0] * 26                       # indice 0 = semana mais antiga
    for c in carimbos:
        idade = (AGORA - c).days
        if 0 <= idade < 182:
            semanas[25 - idade // 7] += 1

    autores = []
    for linha in git(repo, "shortlog", "-sn", "--all", "--no-merges").splitlines():
        linha = linha.strip()
        if "\t" in linha:
            n, nome = linha.split("\t", 1)
            autores.append({"nome": nome.strip(), "commits": int(n)})
    autores = autores[:5]

    def idade_de(iso):
        try:
            return (AGORA - datetime.fromisoformat(iso)).days
        except ValueError:
            return None

    tags = [t for t in git(repo, "tag", "--list").splitlines() if t.strip()]
    branches = [b for b in git(repo, "branch", "-a", "--format=%(refname:short)").splitlines()
                if b and "->" not in b]

    return {
        "versionado": True,
        "branch": branch,
        "sujos": len(sujos),
        "sujos_lista": [s.strip() for s in sujos[:8]],
        "ahead": ahead,
        "behind": behind,
        "commits_total": int(total) if total.isdigit() else 0,
        "commits_7d": desde(7),
        "commits_30d": desde(30),
        "commits_90d": desde(90),
        "semanas": semanas,
        "autores": autores,
        "ultimo_iso": ultimo_iso,
        "ultimo_msg": ultimo_msg[:120],
        "primeiro_iso": primeiro_iso,
        "dias_parado": idade_de(ultimo_iso) if ultimo_iso else None,
        "idade_dias": idade_de(primeiro_iso) if primeiro_iso else None,
        "tags": len(tags),
        "ultima_tag": tags[-1] if tags else None,
        "branches": len(branches),
    }


# ----------------------------------------------------------------------- arquivos
def coleta_arquivos(repo: Path) -> dict:
    linguagens: dict[str, int] = {}
    arquivos = testes = 0
    for base, dirs, nomes in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in IGNORAR_DIR and not d.startswith(".git")]
        for nome in nomes:
            arquivos += 1
            if re.search(r"(\.test\.|\.spec\.|_test\.|Tests?\.cs$)", nome):
                testes += 1
            ling = EXT_LINGUAGEM.get(os.path.splitext(nome)[1].lower())
            if not ling:
                continue
            caminho = os.path.join(base, nome)
            try:
                if os.path.getsize(caminho) > 2_000_000:
                    continue
                with open(caminho, "rb") as fh:
                    linguagens[ling] = linguagens.get(ling, 0) + fh.read().count(b"\n") + 1
            except OSError:
                pass
    principais = sorted(linguagens.items(), key=lambda kv: -kv[1])
    return {
        "arquivos": arquivos,
        "linhas": sum(linguagens.values()),
        "linguagens": [{"nome": n, "linhas": v} for n, v in principais[:6]],
        "arquivos_teste": testes,
    }


# ---------------------------------------------------------------------- prontidao
def existe(repo: Path, *padroes) -> bool:
    return any(any(repo.glob(p)) for p in padroes)


def tem_ci(r: Path) -> bool:
    return existe(r, ".github/workflows/*.yml", ".github/workflows/*.yaml")


def tem_deploy(r: Path) -> bool:
    return any(re.search(r"deploy|publish|release", p.name, re.I)
               for p in r.glob(".github/workflows/*"))


CRITERIOS = [
    ("readme", "README", 1, lambda r: existe(r, "README.md", "readme.md")),
    ("git_limpo", "Árvore limpa e enviada", 1, None),
    ("ci", "CI configurada", 2, tem_ci),
    ("testes", "Testes automatizados", 2, None),
    ("docker", "Docker / compose", 1, lambda r: existe(r, "Dockerfile", "docker-compose*.yml")),
    ("env_exemplo", "Exemplo de variáveis", 1,
     lambda r: existe(r, ARQ_EXEMPLO, "*/" + ARQ_EXEMPLO, "apps/*/" + ARQ_EXEMPLO)),
    ("deploy", "Workflow de deploy", 2, tem_deploy),
    ("docs", "Pasta docs/", 1, lambda r: (r / "docs").is_dir()),
    ("gitignore", ".gitignore", 1, lambda r: (r / ".gitignore").is_file()),
    ("segredo", "Sem segredo na raiz", 2, lambda r: not (r / ARQ_SEGREDO).exists()),
]


def coleta_prontidao(repo: Path, g: dict, arq: dict) -> dict:
    itens = []
    for chave, rotulo, peso, teste in CRITERIOS:
        if chave == "git_limpo":
            ok = bool(g.get("versionado")) and g.get("sujos", 1) == 0 and g.get("ahead", 1) == 0
        elif chave == "testes":
            ok = arq["arquivos_teste"] > 0
        else:
            try:
                ok = bool(teste(repo))
            except Exception:
                ok = False
        itens.append({"chave": chave, "rotulo": rotulo, "peso": peso, "ok": bool(ok)})
    total = sum(i["peso"] for i in itens)
    feito = sum(i["peso"] for i in itens if i["ok"])
    return {"itens": itens, "pontos": feito, "total": total, "pct": round(100 * feito / total)}


# --------------------------------------------------------------------- projecoes
def projecao(g: dict, pr: dict) -> dict:
    """Velocidade recente, tendencia e prazo estimado para fechar as lacunas.

    Metodo, declarado na tela: commits/semana das ultimas 4 semanas contra as 12
    anteriores. O prazo assume ~4 commits de trabalho por ponto de prontidao
    faltante, dividido pela velocidade atual. E estimativa, nao promessa.
    """
    if not g.get("versionado"):
        return {"status": "sem_git", "riscos": ["fora do controle de versão"], "tendencia": "sem git"}

    sem = g["semanas"]
    recente = sum(sem[-4:]) / 4
    anterior = sum(sem[-16:-4]) / 12

    if recente == 0 and anterior == 0:
        tendencia = "dormente"
    elif recente == 0:
        tendencia = "parou"
    elif recente < 1:
        tendencia = "rastejando"
    elif anterior == 0:
        tendencia = "retomado"
    elif recente > anterior * 1.25:
        tendencia = "acelerando"
    elif recente < anterior * 0.75:
        tendencia = "desacelerando"
    else:
        tendencia = "constante"

    faltam = pr["total"] - pr["pontos"]
    if faltam == 0:
        eta = {"semanas": 0, "data": None, "confianca": "completo"}
    elif recente <= 0:
        eta = {"semanas": None, "data": None, "confianca": "sem base"}
    else:
        semanas = max(1, round(faltam * 4 / recente))
        eta = {
            "semanas": semanas,
            "data": (AGORA + timedelta(weeks=semanas)).date().isoformat(),
            "confianca": "alta" if recente >= 5 else "média" if recente >= 2 else "baixa",
        }

    riscos = []
    if (g["dias_parado"] or 0) > 21:
        riscos.append(f"parado há {g['dias_parado']} dias")
    if g["sujos"]:
        riscos.append(f"{g['sujos']} arquivo(s) sem commit")
    if g["ahead"]:
        riscos.append(f"{g['ahead']} commit(s) só no disco")
    faltando = {i["chave"] for i in pr["itens"] if not i["ok"]}
    if "testes" in faltando:
        riscos.append("sem teste automatizado")
    if "ci" in faltando:
        riscos.append("sem CI")
    if "segredo" in faltando:
        riscos.append("arquivo de segredo na raiz do repo")
    if "deploy" in faltando:
        riscos.append("sem workflow de deploy")

    return {
        "velocidade_4s": round(recente, 1),
        "velocidade_12s": round(anterior, 1),
        "tendencia": tendencia,
        "eta": eta,
        "riscos": riscos,
    }


def fase(g: dict, pr: dict) -> str:
    if not g.get("versionado"):
        return "Rascunho"
    pct, parado = pr["pct"], (g.get("dias_parado") if g.get("dias_parado") is not None else 999)
    if pct >= 85 and parado <= 30:
        return "Operação"
    if pct >= 85:
        return "Manutenção"
    if pct >= 60:
        return "Estabilização"
    if parado > 60:
        return "Hibernando"
    return "Construção"


# ------------------------------------------------------------------ infra ao vivo
def coleta_docker() -> list:
    fmt = ('{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}\t'
           '{{.Label "com.docker.compose.project"}}')
    itens = []
    for linha in sh(["docker", "ps", "--format", fmt], timeout=30).splitlines():
        p = linha.split("\t")
        if len(p) < 4:
            continue
        itens.append({
            "nome": p[0], "status": p[1], "portas": p[2], "imagem": p[3],
            "projeto": p[4] if len(p) > 4 else "",
            "reiniciando": "Restarting" in p[1],
            "saudavel": ("healthy" in p[1]) or ("Up" in p[1] and "unhealthy" not in p[1]
                                                and "Restarting" not in p[1]),
        })
    return itens


def portas_escutando() -> list:
    saida = sh(["powershell", "-NoProfile", "-Command",
                "Get-NetTCPConnection -State Listen | "
                "Select-Object -ExpandProperty LocalPort -Unique | Sort-Object"], timeout=30)
    return sorted({int(l) for l in saida.split() if l.strip().isdigit() and 1024 < int(l) < 65535})


def porta_viva(porta: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=0.4):
            return True
    except OSError:
        return False


# ------------------------------------------------------------------------- main
def main():
    casos = json.loads(CASOS.read_text(encoding="utf-8")) if CASOS.exists() else {}
    containers = coleta_docker()
    portas = portas_escutando()

    projetos = []
    for repo in sorted(RAIZ.iterdir()):
        if not repo.is_dir() or repo.name.startswith("."):
            continue
        g = coleta_git(repo)
        arq = coleta_arquivos(repo)
        pr = coleta_prontidao(repo, g, arq)
        caso = casos.get(repo.name, {})

        alvos = [t.lower() for t in caso.get("containers", [])]
        meus = [c for c in containers
                if (alvos and any(t in c["nome"].lower() or t in (c["projeto"] or "").lower()
                                  for t in alvos))
                or repo.name.lower().replace("-", "") == (c["projeto"] or "").lower().replace("-", "")]

        projetos.append({
            "nome": repo.name,
            "caminho": str(repo),
            "titulo": caso.get("titulo", repo.name),
            "resumo": caso.get("resumo", ""),
            "caso": caso.get("caso", {}),
            "url_prod": caso.get("url_prod"),
            "criticidade": caso.get("criticidade", "normal"),
            "git": g,
            "arquivos": arq,
            "prontidao": pr,
            "projecao": projecao(g, pr),
            "fase": fase(g, pr),
            "containers": meus,
            "portas": [{"porta": p, "vivo": p in portas and porta_viva(p)}
                       for p in caso.get("portas", [])],
        })

    dados = {
        "gerado_em": AGORA.astimezone().isoformat(timespec="seconds"),
        "projetos": projetos,
        "infra": {
            "containers": containers,
            "quebrados": [c["nome"] for c in containers if c["reiniciando"]],
            "portas": portas,
        },
    }
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"ok: {len(projetos)} projetos, {len(containers)} containers -> {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
