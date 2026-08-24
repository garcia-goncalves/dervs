# -*- coding: utf-8 -*-
"""Camada pesada do HUB — cota do Actions e dependencias inseguras. 1x por dia.

Sao as duas medidas que custam caro: a cota exige varias chamadas ao GitHub, e o
`npm audit` fala com a rede uma vez por repositorio. Nenhuma das duas muda em uma
hora, quanto mais em um minuto. Por isso vivem aqui, em processo proprio, com
cadencia diaria — e por isso a tela nunca espera por elas.

A cota NAO e reimplementada: quem sabe medi-la e o orcamento-actions.py, que ja
existe em ~/.claude/scripts. Este arquivo le a saida dele. Duas contas diferentes
do mesmo numero e exatamente o problema que este HUB veio resolver.

    python coletar_pesado.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import banco

ORCAMENTO = Path.home() / ".claude" / "scripts" / "orcamento-actions.py"
RAIZ = Path(r"C:\Users\Desktop\source\repos")

# "Medido nos 8 maiores: 2313 min — 116% da cota do plano team (2000 min)."
LINHA_COTA = re.compile(
    r"Medido nos \d+ maiores:\s*([\d.]+)\s*min.*?(\d+)%\s*da cota do plano\s*(\S+)\s*"
    r"\(([\d.]+)\s*min\)")

GRAVES = ("high", "critical")
LIMITE_AUDIT = 120          # segundos por repositorio; sem isso um repo trava o dia


def _sem_console():
    if not sys.platform.startswith("win"):
        return False
    if os.path.basename(sys.executable or "").lower() == "pythonw.exe":
        return True
    return sys.stdout is None


SEM_JANELA = 0x08000000 if _sem_console() else 0


def coleta_quota():
    """Cota de minutos do Actions, pela saida do orcamento-actions.py."""
    if not ORCAMENTO.is_file():
        return None
    try:
        r = subprocess.run([sys.executable, str(ORCAMENTO), "--sem-auditoria", "--detalhe", "0"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300, creationflags=SEM_JANELA)
    except Exception:
        return None
    m = LINHA_COTA.search(r.stdout or "")
    if not m:
        return None
    minutos, pct, plano, cota = m.groups()
    return {
        "minutos": int(float(minutos)),
        "pct": int(pct),
        "plano": plano,
        "cota": int(float(cota)),
        "url": "https://github.com/settings/billing",
    }


def audita_npm(repo: Path) -> list:
    """Pacotes com correcao de seguranca disponivel. So onde ha lockfile."""
    if not (repo / "package-lock.json").is_file():
        return []
    try:
        r = subprocess.run(["npm", "audit", "--json"], cwd=str(repo), capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=LIMITE_AUDIT, creationflags=SEM_JANELA, shell=True)
        dados = json.loads(r.stdout or "{}")
    except Exception:
        return []
    fora = []
    for nome, v in (dados.get("vulnerabilities") or {}).items():
        # So o que e grave E tem correcao: pendencia sem conserto e estatistica.
        if v.get("severity") in GRAVES and v.get("fixAvailable"):
            fora.append(nome)
    return sorted(fora)[:30]


def main():
    con = banco.conectar()
    try:
        quota = coleta_quota()
        if quota:
            banco.gravar(banco.QUOTA, "pesado", quota, con)
            banco.anotar_historico("actions_minutos", quota["minutos"], con)
            print("cota do Actions: %d%% (%d de %d min)"
                  % (quota["pct"], quota["minutos"], quota["cota"]))
        else:
            print("cota do Actions: nao consegui medir (nao conte como zero)")

        auditados = 0
        for repo in sorted(RAIZ.iterdir()):
            if not repo.is_dir() or repo.name.startswith("."):
                continue
            if not (repo / "package-lock.json").is_file():
                continue
            banco.gravar(repo.name, "pesado", {"deps_inseguras": audita_npm(repo)}, con)
            auditados += 1
        print("ok: %d repositorio(s) auditados com npm audit" % auditados)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
