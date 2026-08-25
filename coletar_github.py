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

import ipaddress
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit

import banco

AGORA = datetime.now(timezone.utc)

# ------------------------------------------------------ o site esta no ar?
#
# INTERRUPTOR. Esta e a unica parte do HUB que toca em PRODUCAO. E uma leitura
# — GET sem credencial, sem cookie, sem seguir redirecionamento — uma vez a cada
# 20 minutos, nos enderecos que o dono escreveu a mao no casos.json. Desligar
# aqui apaga a regra 15 da tela e nao muda mais nada.
MEDIR_SITE = True
TETO_SITE = 8                # segundos ate desistir de um site
AGENTE = "HUB-do-dev/1.0 (monitor local; +http://localhost:4777)"

# Nomes de workflow que contam como "publicar". Repositorio sem nenhum deles
# fica CALADO na regra 16 — nao saber nao e o mesmo que estar atrasado.
NOMES_DE_DEPLOY = ("deploy", "publicar", "publish", "release")


NOMES_LOCAIS = ("localhost", "localhost.localdomain")


def _ip_privado(texto: str):
    """True/False se `texto` e um IP interno; None se nao e IP nenhum."""
    try:
        ip = ipaddress.ip_address(texto)
    except ValueError:
        return None
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def url_segura(url: str) -> bool:
    """Checagem de FORMA, sem rede: so http(s), e nada apontando para dentro.

    Hoje o casos.json e escrito so pelo dono e isto e desnecessario. Entra assim
    mesmo: no dia em que essa lista vier de qualquer outro lugar, um endereco
    apontando para 127.0.0.1 ou para a rede interna transformaria este coletor
    numa ferramenta de varredura de dentro da maquina dele.

    Sem DNS aqui, de proposito: funcao pura e testavel offline. A resolucao de
    nome — que tambem pode apontar para dentro — e conferida em `host_publico`,
    ja com a rede na mao.
    """
    try:
        u = urlsplit((url or "").strip())
    except ValueError:
        return False
    if u.scheme not in ("http", "https") or not u.hostname:
        return False
    h = u.hostname.lower().rstrip(".")
    if h in NOMES_LOCAIS or h.endswith(".localhost") or h.endswith(".local"):
        return False
    return _ip_privado(h) is not True


def host_publico(host: str) -> bool:
    """O nome resolve, e resolve para fora? Nome que nao resolve vira silencio."""
    try:
        enderecos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return False
    return bool(enderecos) and not any(
        _ip_privado(sa[0]) for _, _, _, _, sa in enderecos)


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """Redirecionamento e resposta do servidor: ele esta VIVO, e isso basta.

    Seguir o pulo levaria a requisicao para um dominio que este painel nao
    escolheu — e um 301 para outro lugar ja e prova de que o servidor respondeu.
    """

    def redirect_request(self, *a, **kw):
        return None


def mede_site(url: str) -> dict:
    """GET na raiz. 5xx e ausencia de resposta = fora do ar; o resto = vivo."""
    fora = {"url": url, "ok": None, "codigo": 0, "erro": "", "ms": 0}
    if not MEDIR_SITE or not url_segura(url):
        return fora
    if not host_publico(urlsplit(url).hostname):
        # Nome que nao resolve, ou que resolve para dentro da rede. Nao da para
        # medir — e "nao da para medir" NAO e "esta fora do ar" (invariante 2).
        fora["erro"] = "nao_resolveu"
        return fora
    pedido = urllib.request.Request(url, method="GET",
                                    headers={"User-Agent": AGENTE})
    abridor = urllib.request.build_opener(_SemRedirecionar)
    inicio = time.time()
    try:
        with abridor.open(pedido, timeout=TETO_SITE) as r:
            fora["codigo"] = r.status
    except urllib.error.HTTPError as e:
        fora["codigo"] = e.code             # 3xx/4xx/5xx chegam aqui
    except Exception as e:                  # noqa: BLE001 — timeout, DNS, TLS, socket
        fora["erro"] = type(e).__name__
    fora["ms"] = int((time.time() - inicio) * 1000)
    fora["ok"] = bool(fora["codigo"]) and fora["codigo"] < 500
    return fora


def escolher_workflow(workflows) -> dict:
    """O workflow que publica, entre os do repositorio. {} quando nao da para saber."""
    for w in workflows or []:
        alvo = ((w.get("path") or "") + " " + (w.get("name") or "")).lower()
        if any(n in alvo for n in NOMES_DE_DEPLOY):
            return w
    return {}


def atras_de(comparacao) -> int | None:
    """Quantos commits a branch padrao esta na frente do ultimo deploy."""
    if not isinstance(comparacao, dict):
        return None
    n = comparacao.get("ahead_by")
    return n if isinstance(n, int) else None


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


def _gh_json(caminho: str, teto=30):
    """GET na API REST do GitHub pelo `gh` ja autenticado. None quando falha."""
    try:
        r = subprocess.run(["gh", "api", caminho], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=teto,
                           creationflags=SEM_JANELA)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def mede_deploy(slug: str, branch: str) -> dict:
    """Ultimo deploy bem-sucedido vs. a ponta da branch padrao.

    Tres chamadas REST por projeto, e so para os que declaram endereco de
    producao — hoje 5 dos 17. Sao ~45 chamadas por hora contra um limite de
    5.000: cabe. Fazer isto para os 17 nao caberia no proposito, porque projeto
    sem endereco de producao nao tem o que estar atrasado em relacao a que.

    Devolve {} quando NAO DA PARA SABER (sem workflow de publicacao, sem
    execucao bem-sucedida, comparacao que falhou). {} deixa a regra 16 calada,
    que e o certo: ignorancia nao e alarme.
    """
    ws = _gh_json("repos/%s/actions/workflows" % slug)
    escolhido = escolher_workflow((ws or {}).get("workflows"))
    if not escolhido:
        return {}

    runs = _gh_json("repos/%s/actions/workflows/%s/runs?status=success&per_page=1"
                    % (slug, escolhido.get("id")))
    corridas = (runs or {}).get("workflow_runs") or []
    if not corridas:
        return {}
    sha = corridas[0].get("head_sha") or ""
    if not sha:
        return {}

    comp = _gh_json("repos/%s/compare/%s...%s" % (slug, sha, branch))
    atras = atras_de(comp)
    if atras is None:
        return {}
    return {"sha": sha, "quando": corridas[0].get("updated_at") or "",
            "atras": atras, "workflow": escolhido.get("name") or "",
            "url": "https://github.com/%s/actions" % slug}


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
            # Producao: so para quem declarou endereco no casos.json.
            local = ((tudo.get(nome) or {}).get("local") or {}).get("dados") or {}
            url_prod = local.get("url_prod") or ""
            antes_gh = ((tudo.get(nome) or {}).get("github") or {}).get("dados") or {}
            if url_prod:
                site = mede_site(url_prod)
                if site.get("ok") is None:
                    # NAO medimos (interruptor desligado, ou URL que nao passou na
                    # checagem). Gravar isso apagaria do painel um "fora do ar"
                    # real que ja estava no banco — o mesmo cuidado que os alertas
                    # de seguranca ganharam logo abaixo, pelo mesmo motivo.
                    anterior = antes_gh.get("site")
                    if anterior:
                        novo["site"] = anterior
                else:
                    novo["site"] = site
                dep = mede_deploy(novo["slug"], novo["branch_padrao"] or "main")
                novo["deploy"] = dep or antes_gh.get("deploy") or {}

            banco.gravar(nome, "github", novo, con)
            gravados += 1
    finally:
        con.close()

    print("ok: %d repositorios do GitHub atualizados%s"
          % (gravados, "" if com_vulns else " (sem alertas de segurança)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
