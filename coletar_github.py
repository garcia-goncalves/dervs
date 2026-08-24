# -*- coding: utf-8 -*-
"""Camada GitHub do HUB — CI, pedidos de alteracao e alertas de seguranca.

POR QUE EM LOTE, E POR QUE DEVAGAR

Nenhum destes numeros muda de minuto em minuto. Consultar 16 repositorios um a
um, o tempo todo, queima cota sem entregar nada — e a cota desta conta JA
estourou uma vez (2.313 min em 30 dias num repositorio so, 116% do mes inteiro).

Entao: UMA consulta GraphQL com um apelido por repositorio, a cada 20 minutos.
Traz ramo padrao, resultado da ultima verificacao, PRs abertos e contagem de
alertas de vulnerabilidade dos 16 de uma vez, gastando pontos do orcamento de
5.000/hora em vez de dezenas de chamadas REST.

Roda em processo separado do coletar.py de proposito: aquele mede o disco a cada
60 s e nao pode ficar esperando a rede.

O TOKEN nunca aparece aqui: quem autentica e o `gh` que o dono ja logou. Este
arquivo nao le, nao grava e nao imprime segredo nenhum.

    python coletar_github.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import banco

AGORA = datetime.now(timezone.utc)


def _sem_console():
    if not sys.platform.startswith("win"):
        return False
    if os.path.basename(sys.executable or "").lower() == "pythonw.exe":
        return True
    return sys.stdout is None


SEM_JANELA = 0x08000000 if _sem_console() else 0

# vulnerabilityAlerts exige permissao de administracao no repositorio. Quando o
# token nao tem, o GitHub responde erro para ESSE campo e zera a resposta toda —
# por isso a consulta e montada em duas versoes e a segunda e a rede de seguranca.
PEDACO = """
  %(alias)s: repository(owner: "%(dono)s", name: "%(repo)s") {
    nameWithOwner
    url
    defaultBranchRef {
      name
      target { ... on Commit { statusCheckRollup { state } } }
    }
    pullRequests(states: OPEN, first: 5, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes { number title url updatedAt isDraft }
    }
    %(vulns)s
  }
"""
CAMPO_VULNS = 'vulnerabilityAlerts(states: OPEN, first: 1) { totalCount }'


def _consulta(slugs: dict, com_vulns: bool) -> str:
    partes = []
    for alias, slug in slugs.items():
        dono, repo = slug.split("/", 1)
        partes.append(PEDACO % {"alias": alias, "dono": dono, "repo": repo,
                                "vulns": CAMPO_VULNS if com_vulns else ""})
    return "query {\n" + "\n".join(partes) + "\n}"


def _gh_graphql(consulta: str):
    try:
        r = subprocess.run(["gh", "api", "graphql", "-f", "query=" + consulta],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90, creationflags=SEM_JANELA)
    except (subprocess.TimeoutExpired, OSError) as e:
        return None, "gh nao respondeu: %s" % e
    if r.returncode != 0:
        return None, (r.stderr or "").strip()[:300]
    try:
        return json.loads(r.stdout).get("data") or {}, None
    except ValueError:
        return None, "resposta do gh nao era JSON"


def _dias(iso: str):
    try:
        return max(0, (AGORA - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days)
    except (ValueError, AttributeError):
        return 0


def traduz(no: dict, com_vulns: bool) -> dict:
    """Um repositorio do GraphQL -> o que as regras consomem."""
    url = no.get("url", "")
    ramo = no.get("defaultBranchRef") or {}
    alvo = ramo.get("target") or {}
    rollup = alvo.get("statusCheckRollup") or {}
    estado = (rollup.get("state") or "").upper()

    prs = []
    for pr in ((no.get("pullRequests") or {}).get("nodes") or []):
        if pr.get("isDraft"):
            continue                       # rascunho nao esta esperando ninguem
        prs.append({"numero": pr.get("number"), "titulo": pr.get("title", "")[:120],
                    "url": pr.get("url", ""), "dias": _dias(pr.get("updatedAt", ""))})

    total_vulns = ((no.get("vulnerabilityAlerts") or {}).get("totalCount")
                   if com_vulns else None)

    return {
        "slug": no.get("nameWithOwner", ""),
        "url": url,
        "branch_padrao": ramo.get("name", ""),
        # ERROR e FAILURE viram falha; PENDING e EXPECTED nao sao pendencia (ainda
        # esta rodando); ausencia de rollup significa "esse repo nao tem CI", que e
        # outra regra, nao esta.
        "ci": {"conclusao": "failure" if estado in ("FAILURE", "ERROR") else
                            "success" if estado == "SUCCESS" else "",
               "estado_bruto": estado,
               "url": url + "/actions",
               "quando": ""},
        "prs": prs,
        "vulns": ({"total": total_vulns, "url": url + "/security/dependabot"}
                  if total_vulns is not None else {}),
    }


def main():
    tudo = banco.ler_tudo()
    slugs, por_alias = {}, {}
    for nome, camadas in sorted(tudo.items()):
        if nome == banco.INFRA:
            continue
        slug = ((camadas.get("local") or {}).get("dados") or {}).get("git", {}).get("remoto_slug")
        if not slug or "/" not in slug:
            continue                       # sem remoto: regra 13 ja cobre
        alias = "r%d" % len(slugs)
        slugs[alias] = slug
        por_alias[alias] = nome

    if not slugs:
        print("nenhum repositorio com remoto no GitHub.")
        return 0

    dados, erro = _gh_graphql(_consulta(slugs, com_vulns=True))
    com_vulns = True
    if dados is None:
        # A primeira consulta pode falhar por falta de permissao para ler alertas,
        # mas tambem por rede, timeout ou limite de uso — daqui nao da para
        # distinguir. Tentamos sem esse campo, porque CI e PR valem por si.
        dados, erro2 = _gh_graphql(_consulta(slugs, com_vulns=False))
        com_vulns = False
        if dados is None:
            print("FALHA ao consultar o GitHub: %s / %s" % (erro, erro2))
            return 1
        print("aviso: vim sem os alertas de segurança nesta rodada (%s)" % erro)

    con = banco.conectar()
    gravados = 0
    try:
        for alias, nome in por_alias.items():
            no = dados.get(alias)
            if not no:
                continue                   # repo sumiu ou sem acesso: fica sem camada
            novo = traduz(no, com_vulns)
            if not com_vulns:
                # NAO medimos alertas nesta rodada. Gravar {} aqui apagaria do
                # painel um alerta de seguranca REAL que ja estava no banco —
                # um blip de rede as 20h faria "93 alertas abertos" virar silencio
                # ate a proxima coleta boa. Carregamos o valor anterior e dizemos
                # de quando ele e, para a tela poder mostrar que esta velho.
                antes = ((tudo.get(nome) or {}).get("github") or {})
                novo["vulns"] = (antes.get("dados") or {}).get("vulns") or {}
                novo["vulns_medido_em"] = antes.get("medido_em")
            banco.gravar(nome, "github", novo, con)
            gravados += 1
    finally:
        con.close()

    print("ok: %d repositorios do GitHub atualizados%s"
          % (gravados, "" if com_vulns else " (sem alertas de segurança)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
