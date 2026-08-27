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
# Mesma lista de pastas do coletor local — importada, nao repetida: duas listas
# divergem, e divergencia de lista e como o HUB deixa de ver um projeto.
from coletar import pastas_de_projeto

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


def argv_npm(windows=None) -> list:
    """O argv do `npm audit --json`, com os argumentos CHEGANDO ao npm.

    Nada de shell=True: em Linux o shell recebe so o primeiro item da lista e
    descarta o resto — rodaria `npm` puro, que imprime a ajuda. No Windows o
    npm e um .cmd que o CreateProcess nao acha sozinho; o `cmd /c` resolve isso
    mantendo cada argumento como argumento, nunca como texto de comando. Mesmo
    desenho do acao_vscode() em servir.py.
    """
    if windows is None:
        windows = sys.platform.startswith("win")
    base = ["npm", "audit", "--json"]
    return ["cmd", "/c", *base] if windows else base


def interpreta_audit(texto: str):
    """A lista de pacotes graves com conserto. None quando nao houve auditoria.

    O npm devolve o relatorio em JSON com a chave `vulnerabilities`. Qualquer
    outra coisa — ajuda, erro de rede, saida vazia — significa que nao medimos,
    e nao que esta limpo.
    """
    try:
        dados = json.loads(texto)
    except (ValueError, TypeError):
        return None
    if not isinstance(dados, dict) or "vulnerabilities" not in dados:
        return None
    fora = []
    for nome, v in (dados.get("vulnerabilities") or {}).items():
        # So o que e grave E tem correcao: pendencia sem conserto e estatistica.
        if isinstance(v, dict) and v.get("severity") in GRAVES and v.get("fixAvailable"):
            fora.append(nome)
    return sorted(fora)[:30]


def audita_npm(repo: Path):
    """Pacotes com correcao de seguranca disponivel. None se NAO deu para medir.

    None e lista vazia dizem coisas opostas, e o painel depende da diferenca:
    vazia e "auditei, esta limpo"; None e "nao auditei". O mesmo cuidado que a
    coleta_quota() ja tinha ("nao conte como zero") faltava aqui.
    """
    if not (repo / "package-lock.json").is_file():
        return []
    try:
        r = subprocess.run(argv_npm(), cwd=str(repo), capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=LIMITE_AUDIT, creationflags=SEM_JANELA)
    except Exception:
        return None
    return interpreta_audit(r.stdout or "")


def main():
    con = banco.conectar()
    try:
        # FORA DO LACO: dentro, era um SELECT por repositorio, e no primeiro
        # giro de um banco novo o `criar_usuario` de dentro commitava a
        # transacao do coletor pela metade.
        dono = banco.conta_local(con)
        quota = coleta_quota()
        if quota:
            banco.gravar(banco.QUOTA, "pesado", quota, con, usuario_id=dono)
            banco.anotar_historico("actions_minutos", quota["minutos"], con)
            print("cota do Actions: %d%% (%d de %d min)"
                  % (quota["pct"], quota["minutos"], quota["cota"]))
        else:
            print("cota do Actions: nao consegui medir (nao conte como zero)")

        auditados = 0
        cegos = []
        for repo in pastas_de_projeto():
            if not (repo / "package-lock.json").is_file():
                continue
            deps = audita_npm(repo)
            # None vai para o banco COMO None de proposito: "nao auditei" tem de
            # sobreviver ate a tela. Gravar [] aqui seria inventar uma medicao.
            #
            # `auditoria_falhou` e o que separa "tentei e nao consegui" de "esta
            # camada nunca rodou". Sem essa marca a regra 17 nao acorda, e o
            # invariante 2 do motor (ausencia nao e falha) continua de pe.
            banco.gravar(repo.name, "pesado",
                         {"deps_inseguras": deps, "auditoria_falhou": deps is None},
                         con, usuario_id=dono)
            if deps is None:
                cegos.append(repo.name)
            else:
                auditados += 1
        print("ok: %d repositorio(s) auditados com npm audit" % auditados)
        if cegos:
            print("npm audit NAO respondeu em %d (nao conte como zero): %s"
                  % (len(cegos), ", ".join(cegos[:8])))
        con.commit()          # ver coletar.py: quem abriu a conexao commita
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
