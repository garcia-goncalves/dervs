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

QUEM AUTENTICA

Tres caminhos, nesta ordem. Com `DERVS_GITHUB_TOKEN` no ambiente, este arquivo
fala com a API do GitHub direto — e a saida de emergencia. Sem ele, mas com o
GitHub App configurado (`DERVS_GITHUB_APP_ID`, `DERVS_GITHUB_INSTALLATION_ID` e
`DERVS_GITHUB_APP_KEY`), o `github_app.py` troca a chave privada por um token
de instalacao e renova de hora em hora — e o caminho do SERVIDOR, onde nao ha
`gh` logado nem pode haver. Sem nada disso, cai no `gh` que o dono ja logou na
maquina dele, e nada muda para ele.

Nem o token nem a chave sao gravados, impressos ou postos em mensagem de erro —
todas as mensagens que saem daqui sao escritas por nos, nunca repassadas da
excecao. Como os tres valores nascem, onde moram e como se trocam:
`docs/operacao/token-do-coletor.md`.

    python coletar_github.py
"""
from __future__ import annotations

import ipaddress
import json
import re
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit

import github_app

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
TENTATIVAS_SITE = 2          # uma falha nao vira alarme: ver mede_site()
PAUSA_ENTRE_TENTATIVAS = 1.5
# Sem endereco no User-Agent: ele e lido por todo servidor medido e por todo
# intermediario no caminho. Anunciar "ha um painel local na 4777" e informacao
# de graca para quem registrar um dominio que o dono deixou expirar.
AGENTE = "HUB-do-dev/1.0 (monitor)"

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


def _uma_batida(url: str) -> dict:
    """Uma tentativa. codigo=0 e erro preenchido significam 'nem respondeu'."""
    r = {"codigo": 0, "erro": "", "ms": 0}
    pedido = urllib.request.Request(url, method="GET",
                                    headers={"User-Agent": AGENTE})
    abridor = urllib.request.build_opener(_SemRedirecionar)
    inicio = time.time()
    try:
        with abridor.open(pedido, timeout=TETO_SITE) as resp:
            r["codigo"] = resp.status
    except urllib.error.HTTPError as e:
        r["codigo"] = e.code                # 3xx/4xx/5xx chegam aqui
    except Exception as e:                  # noqa: BLE001 — timeout, DNS, TLS, socket
        r["erro"] = type(e).__name__
    r["ms"] = int((time.time() - inicio) * 1000)
    return r


def mede_site(url: str) -> dict:
    """GET na raiz. 5xx e ausencia de resposta = fora do ar; o resto = vivo.

    DUAS TENTATIVAS antes de acusar. Uma unica falha nao vira alarme de gravidade
    alta: um piscar da internet DELE — nao do servidor — bastaria para a tela
    dizer "site de producao fora do ar" com toda a cara de certo, que e o pior
    defeito possivel neste painel. A segunda batida so acontece quando a
    primeira foi mal, entao o caminho normal continua sendo uma requisicao so.

    Confirmar aqui, e nao esperando a proxima coleta, e deliberado: em 20 minutos
    de espera um apagao de verdade fica invisivel: o dobro do tempo em que o
    cliente ja ligou.
    """
    fora = {"url": url, "ok": None, "codigo": 0, "erro": "", "ms": 0,
            "tentativas": 0}
    if not MEDIR_SITE or not url_segura(url):
        return fora
    if not host_publico(urlsplit(url).hostname):
        # Nome que nao resolve, ou que resolve para dentro da rede. Nao da para
        # medir — e "nao da para medir" NAO e "esta fora do ar" (invariante 2).
        fora["erro"] = "nao_resolveu"
        return fora

    for tentativa in range(1, TENTATIVAS_SITE + 1):
        r = _uma_batida(url)
        fora.update(r, tentativas=tentativa)
        vivo = bool(r["codigo"]) and r["codigo"] < 500
        if vivo:
            fora["ok"] = True
            return fora
        if tentativa < TENTATIVAS_SITE:
            time.sleep(PAUSA_ENTRE_TENTATIVAS)
    fora["ok"] = False
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
    issues(states: OPEN, first: 10, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes { number title url updatedAt }
    }
    %(vulns)s
  }
"""
# `first: 100` e o teto util do GraphQL, e vem na MESMA ida a rede que ja
# existia — o detalhe nao custa consulta a mais. Repositorio com mais alertas que
# isso devolve AMOSTRA, e `_resume_alertas` marca isso: medido em 25/08/2026,
# medconsultoria tem 93 e odontologia-pericia 71, os dois cabem.
CAMPO_VULNS = """vulnerabilityAlerts(states: OPEN, first: 100) {
      totalCount
      nodes {
        dependencyScope
        securityAdvisory { ghsaId }
        securityVulnerability {
          severity
          package { name ecosystem }
        }
      }
    }"""


def _consulta(slugs: dict, com_vulns: bool) -> str:
    partes = []
    for alias, slug in slugs.items():
        dono, repo = slug.split("/", 1)
        partes.append(PEDACO % {"alias": alias, "dono": dono, "repo": repo,
                                "vulns": CAMPO_VULNS if com_vulns else ""})
    return "query {\n" + "\n".join(partes) + "\n}"


# ------------------------------------------------------- quem autentica aqui
#
# TRES CAMINHOS, e a ordem importa.
#
# 1. TOKEN PRONTO NO AMBIENTE (`DERVS_GITHUB_TOKEN`) — a saida de emergencia.
#    Serve para o servidor rodar hoje a noite com um token pessoal, sem
#    desconfigurar nada. Vem primeiro justamente para isso: quem o define esta
#    depurando, e quer que ele valha.
# 2. O GITHUB APP (`DERVS_GITHUB_APP_ID` + `DERVS_GITHUB_INSTALLATION_ID` +
#    `DERVS_GITHUB_APP_KEY`) — o caminho do SERVIDOR, e o normal. O app tem
#    identidade propria, so de leitura, revogavel num clique, e nao gasta a
#    cota pessoal do dono. A chave privada nao E um token: com ela pedimos um
#    token novo de hora em hora, e quem faz essa troca e o `github_app.py`.
# 3. O `gh` — o caminho da MAQUINA DO DONO, que continua funcionando sem
#    configurar nada. Sem nada no ambiente, nada muda para ele.
#
# No servidor nao existe `gh` logado, nem pode existir: o `gh` e a ferramenta
# que o dono autenticou na maquina DELE, e amarrar a coleta a isso e amarrar o
# produto a uma pessoa estar sentada aqui. O roteiro dos tres valores esta em
# docs/operacao/token-do-coletor.md.
#
# NEM O TOKEN NEM A CHAVE SAO IMPRESSOS OU GRAVADOS por este arquivo alem do
# cabecalho da requisicao. Toda mensagem de erro que sai daqui e escrita por
# nos, nunca repassada da excecao: `URLError` carrega a URL, e URL de API pode
# carregar o que o chamador pos nela.
VAR_TOKEN_NO_AMBIENTE = "DERVS_GITHUB_TOKEN"
VAR_APP_ID = "DERVS_GITHUB_APP_ID"
VAR_INSTALACAO = "DERVS_GITHUB_INSTALLATION_ID"
VAR_CHAVE_DO_APP = "DERVS_GITHUB_APP_KEY"
API = "https://api.github.com/"
# So o que a API do GitHub usa em caminho de recurso. Barra inicial some antes
# desta peneira; `//`, `..` e esquema completo caem aqui.
CAMINHO_API = re.compile(r"[A-Za-z0-9._~/-]+(\?[A-Za-z0-9._~=&%-]*)?$")


# O app fica guardado entre chamadas porque `_token()` e chamado varias vezes
# por coleta e o token de instalacao vale uma hora — pedir um por consulta
# queimaria cota sem entregar nada. E o `Coletor` que decide quando renovar.
_APP_GUARDADO = None


def esquecer_o_app() -> None:
    """Descarta o app guardado, para que o ambiente seja lido de novo.

    Existe para o teste e para o dia em que alguem trocar a chave sem reiniciar
    o processo. Nao e usado no caminho normal.
    """
    global _APP_GUARDADO
    _APP_GUARDADO = None


def _app():
    """O GitHub App montado do ambiente, ou `None` se ele nao esta configurado.

    Ambiente pela metade — o caso comum no primeiro deploy — devolve `None` sem
    reclamar e sem guardar nada: quem chama cai no `gh`, e o unico jeito de
    saber que faltou uma variavel e a coleta nao trazer os numeros. Reclamar
    aqui encheria o log da maquina do dono, onde a ausencia e o normal.
    """
    global _APP_GUARDADO
    if _APP_GUARDADO is None:
        ident = (os.environ.get(VAR_APP_ID) or "").strip()
        instalacao = (os.environ.get(VAR_INSTALACAO) or "").strip()
        chave = os.environ.get(VAR_CHAVE_DO_APP) or ""
        if not (ident and instalacao and chave.strip()):
            return None
        _APP_GUARDADO = github_app.Coletor(ident, instalacao, chave)
    return _APP_GUARDADO


def _token() -> str:
    """O token do ambiente, ou "" se ele nao serve para ir num cabecalho.

    O `.strip()` limpa as PONTAS. Um token colado com quebra de linha no MEIO
    passa por ele e faz o `http.client` levantar `ValueError` com o valor do
    cabecalho dentro — isto e, com o token.

    Hoje essa excecao NAO chega a lugar nenhum: as duas chamadas de
    `_http_github` a engolem sem repassar. Isto e defesa em profundidade, para
    o dia em que alguem acrescentar um `raise` ou um log ali. Nenhum formato de
    token do GitHub e afetado: `ghp_`, `ghs_`, `github_pat_` e o JWT do App sao
    todos ASCII imprimiveis.

    Recusar aqui derruba para o `gh`, que no SERVIDOR nao existe — entao a
    recusa fala, senao o operador so ve "gh nao respondeu" e procura no lugar
    errado.
    """
    t = (os.environ.get(VAR_TOKEN_NO_AMBIENTE) or "").strip()
    if t and not (t.isascii() and t.isprintable()):
        # O token NAO entra na mensagem, obviamente. Nem o tamanho dele.
        _diga("o valor de %s tem caractere que nao vai em cabecalho HTTP; "
              "ignorei" % VAR_TOKEN_NO_AMBIENTE)
        return ""
    if t:
        return t
    # Sem token pronto, o GitHub App. A troca chave -> token acontece la, e
    # falha fechada: `None` vira "" e a coleta cai no `gh` como sempre caiu.
    app = _app()
    return (app.token() or "") if app is not None else ""


def _url_da_api(caminho: str):
    """`repos/a/b` -> URL da API do GitHub. `None` se o caminho nao serve.

    A checagem existe porque o caminho e montado com `slug`, que vem do
    `casos.json` e da propria API. Sem ela, um slug com `..` ou com `//host`
    apontaria esta funcao para outro servidor levando o `Authorization` junto —
    e entregar o token e pior que falhar a coleta.
    """
    # UMA barra inicial e conveniencia; duas sao `//host`, que e outro endereco.
    # Comer as duas com `lstrip` transformava um caminho malformado em caminho
    # bom calado — e calado e como um defeito destes chega em producao.
    c = (caminho or "")[1:] if (caminho or "").startswith("/") else (caminho or "")
    if not c or c.startswith("/") or not CAMINHO_API.fullmatch(c):
        return None
    # `..` como PEDACO do caminho e subir de pasta. `..` no meio de um pedaco
    # nao e: `compare/abc123...main` — a comparacao que mede o drift inteiro —
    # tem tres pontos, e recusar por texto deixava a regra 16 muda em silencio.
    if ".." in c.split("?", 1)[0].split("/"):
        return None
    return API + c


def _http_github(caminho: str, corpo=None, teto=90):
    """GET (ou POST com `corpo`) na API do GitHub, com o token do ambiente.

    Devolve o JSON decodificado. Levanta em qualquer falha — quem chama traduz.
    """
    url = _url_da_api(caminho)
    if not url:
        raise ValueError("caminho de API recusado")
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    pedido = urllib.request.Request(
        url, data=dados, method="POST" if dados else "GET",
        headers={"Authorization": "Bearer " + _token(),
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": AGENTE,
                 **({"Content-Type": "application/json"} if dados else {})})
    # Sem seguir desvio: um 302 levaria o cabecalho `Authorization` — o token —
    # para o host que o outro lado escolher. E a mesma licao do agente.
    abridor = urllib.request.build_opener(_SemRedirecionar)
    with abridor.open(pedido, timeout=teto) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


# O `type` do erro do GraphQL e enum FECHADO do GitHub, e cada um destes pede
# uma acao diferente de quem opera: arrumar o nome no casos.json, pedir
# permissao no App, ou simplesmente esperar. Chegarem todos como a mesma frase
# deixa o operador sem saber qual das tres fazer.
#
# LISTA BRANCA, e nao repasse: o que nao esta aqui e texto de fora, e texto de
# fora nao entra em mensagem que vai para a tela do painel. O `message` do erro
# — que e frase livre — nunca passa.
TIPOS_DE_ERRO = ("NOT_FOUND", "FORBIDDEN", "RATE_LIMITED", "SERVICE_UNAVAILABLE",
                 "INTERNAL", "MAX_NODE_LIMIT_EXCEEDED", "TIMEOUT")


def _tipos_do_erro(erros) -> str:
    vistos = []
    for e in erros or []:
        t = (e or {}).get("type")
        if t in TIPOS_DE_ERRO and t not in vistos:
            vistos.append(t)
    return ", ".join(vistos) if vistos else "motivo que nao reconheco"


def _gh_graphql(consulta: str):
    if _token():
        try:
            resposta = _http_github("graphql", {"query": consulta})
        except Exception as e:       # noqa: BLE001 — rede, HTTP, TLS, JSON
            # A EXCECAO NAO ENTRA NA MENSAGEM: ela carrega a URL, e a URL pode
            # carregar o token de quem montou a requisicao errado um dia.
            #
            # Mas so "nao respondeu" nao serve no SERVIDOR, onde nao ha ninguem
            # olhando o terminal: nao separa token vencido (401) de GitHub fora
            # do ar (5xx) nem de rede caida (sem codigo). O CODIGO da resposta e
            # um numero de tres digitos que o GitHub devolveu — nao e segredo, e
            # e o que torna o erro diagnosticavel de longe.
            codigo = getattr(e, "code", None)
            return None, ("a API do GitHub respondeu HTTP %s" % codigo
                          if isinstance(codigo, int)
                          else "a API do GitHub nao respondeu")
        if not isinstance(resposta, dict):
            return None, "resposta da API do GitHub nao era JSON de objeto"
        # O GRAPHQL FALHA COM CODIGO 200. O motivo vem aqui dentro, e nao no
        # codigo HTTP: consulta recusada, repositorio inexistente, limite de uso
        # estourado, permissao negada para UM campo — tudo isso chega como 200
        # com `errors` preenchido, muitas vezes junto de dado parcial.
        #
        # O caminho do `gh` fechava isto de graca (ele sai com codigo != 0).
        # Sem esta linha, o caminho HTTP aceitava a falha como sucesso, e a
        # revisao de seguranca mediu as duas consequencias: uma coleta
        # inteiramente falhada imprimia "ok: 0 repositorios atualizados" e saia
        # com 0; e uma falha PARCIAL — token sem permissao de ler alertas —
        # gravava `vulns: {}` por cima de alertas reais, sem acionar a segunda
        # consulta que existe exatamente para esse caso.
        #
        # MAS ERRO NAO E O MESMO QUE FRACASSO. O caso mais banal desta consulta
        # e um repositorio renomeado, transferido ou arquivado: o GitHub devolve
        # os outros 16 COMPLETOS e um `NOT_FOUND` do lado. A primeira versao
        # desta correcao descartava tudo, e isso congelava CI, PR, issues,
        # alertas, site e publicacao de TODOS os projetos por causa de um nome
        # trocado — a cada 20 minutos, para sempre. Trocar um defeito por outro
        # do mesmo tamanho, na direcao contraria.
        #
        # Regra: sobrou repositorio util, seguimos com ele. Nao sobrou nenhum,
        # e falha de verdade. Quem cuida do campo que veio pela metade (alertas
        # sem permissao) e `main`, repositorio a repositorio.
        dados = resposta.get("data") or {}
        if resposta.get("errors"):
            if any(v for v in dados.values()):
                # SOBROU DADO, mas alguma coisa faltou — e o caso tipico e o
                # pior: o token perdeu a permissao de ler alertas, o
                # repositorio vem inteiro so com `vulnerabilityAlerts: null`, e
                # a rodada parece um sucesso. Aceitar CALADO era o defeito da
                # correcao anterior: o painel republicava uma medicao de
                # seguranca velha como se fosse fresca, e o operador perdia o
                # unico aviso que existia. Fica com o dado, mas diz o que
                # faltou.
                # NA SAIDA NORMAL, e nao em `_diga`. Resposta parcial e, por
                # definicao, uma rodada que termina em 0 — e no caminho de
                # SUCESSO o `servir.py` registra o `stdout` e joga o `stderr`
                # fora. Escrito em `_diga`, este aviso so existiria para quem
                # rodasse o coletor a mao no terminal.
                print("aviso: segui com o que veio, mas o GitHub recusou parte "
                      "da consulta (%s)" % _tipos_do_erro(resposta["errors"]))
                return dados, None
            return None, "a API do GitHub recusou a consulta (%s)" % _tipos_do_erro(
                resposta["errors"])
        return dados, None

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
    """GET na API REST do GitHub. None quando falha — ver `_gh_graphql`."""
    if _token():
        try:
            return _http_github(caminho, teto=teto)
        except Exception:            # noqa: BLE001 — 404 aqui e resposta valida
            return None

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

    # Defesa em profundidade: o sha vem da API do GitHub e vai para o `detalhe`
    # da pendencia, campo que entra no prompt do botao "Resolver". Doze
    # caracteres nao injetam nada e a etiqueta de dado nao-confiavel cobre — mas
    # conferir que e mesmo hexadecimal custa uma linha.
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
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
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return 0
    # Carimbo sem fuso subtraido de um com fuso levanta TypeError. Tratar como
    # UTC e o mesmo criterio de `regras._idade`.
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return max(0, (AGORA - t).days)


# O GitHub responde CRITICAL/HIGH/MODERATE/LOW; a tela fala minusculo.
SEVERIDADES = {"CRITICAL": "critical", "HIGH": "high",
               "MODERATE": "moderate", "LOW": "low"}
ESCOPOS = {"RUNTIME": "runtime", "DEVELOPMENT": "development"}


def _resume_alertas(bloco: dict) -> dict:
    """Transforma o bloco de alertas em numeros que a tela pode usar.

    Tres verdades diferentes, e confundi-las e uma das formas de o painel mentir:

      `totalCount` diz QUANTOS alertas ha. E a unica contagem completa.
      `nodes` diz O QUE eles sao, e vem no maximo 100. Quando sao menos que o
        total, tudo que sai deles e amostra — marcada em `amostra`.
      `pacotes`/`defeitos` dizem o TAMANHO DO TRABALHO. Medido em 25/08/2026: os
        203 alertas dos quatro projetos eram 32 pacotes, e os 6 "criticos" do
        workspace-medconsultoria eram DOIS CVEs de vitest repetidos por tres
        manifestos. Contagem bruta faz 3 tarefas de 1.

    `dependencyScope` entra como fato e NADA MAIS. A tentacao e rebaixar tudo que
    e DEVELOPMENT ("vitest e ferramenta de teste, nao vai para producao"), mas foi
    medido no proprio workspace-medconsultoria que o MESMO vitest volta
    DEVELOPMENT num manifesto e RUNTIME noutro — porque num package.json ele esta
    declarado fora de devDependencies. Rebaixar por escopo esconderia um critico
    real. Quem decide gravidade e regras.py, e ele nao olha para este campo.
    """
    total = bloco.get("totalCount")
    if total is None:
        return {}
    saida = {"total": total}
    nos = bloco.get("nodes")
    if nos is None:
        # A permissao pode conceder a contagem e recusar o detalhe. O total
        # sozinho ja e a tela de hoje: devolver so ele e degradar, nao quebrar.
        return saida

    sev = dict.fromkeys(SEVERIDADES.values(), 0)
    escopo = dict.fromkeys(ESCOPOS.values(), 0)
    pacotes, defeitos = set(), set()
    for no in nos:
        vuln = (no or {}).get("securityVulnerability") or {}
        chave = SEVERIDADES.get(vuln.get("severity") or "")
        if chave:
            sev[chave] += 1
        # Severidade que o GitHub nao mandou fica FORA da soma. Jogar em
        # "moderate" por omissao inventaria um numero que ninguem mediu.
        nome = (vuln.get("package") or {}).get("name") or ""
        if nome:
            pacotes.add(nome)
            aviso = ((no or {}).get("securityAdvisory") or {}).get("ghsaId") or ""
            defeitos.add((nome, aviso))
        alvo = ESCOPOS.get((no or {}).get("dependencyScope") or "")
        if alvo:
            escopo[alvo] += 1

    saida.update(sev=sev, escopo=escopo,
                 pacotes=len(pacotes), defeitos=len(defeitos))
    if len(nos) < total:
        saida["amostra"] = True
    return saida


def traduz(no: dict, com_vulns: bool) -> dict:
    """Um repositorio do GraphQL -> o que as regras consomem."""
    # `or ""` e nao `.get(url, "")`: o default do `.get` so vale para chave
    # AUSENTE. Chave presente com valor nulo devolve None, e `None + "/actions"`
    # estoura. Hoje o esquema do GitHub declara estes campos como nao-nulos,
    # entao nao e alcancavel — mas a aceitacao de resposta PARCIAL, logo acima,
    # e a primeira via que entrega no incompleto a esta funcao.
    url = no.get("url") or ""
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

    alertas = (_resume_alertas(no.get("vulnerabilityAlerts") or {})
               if com_vulns else {})

    # AS ISSUES ABERTAS — o "eu sei o que falta" do painel.
    #
    # Vem no MESMO campo da mesma consulta que ja ia buscar CI e PRs: nao ha
    # uma ida a rede a mais por causa disto, e nao pode haver (a cota desta
    # conta ja estourou uma vez).
    #
    # DUAS VERDADES DIFERENTES, e trocar uma pela outra e o painel mentindo:
    #   `issues_total` diz QUANTAS ha — e a contagem completa, vinda do GitHub.
    #   `issues` diz QUAIS sao, e traz no maximo 10. Contar esta lista para
    #     dizer "faltam N" daria 10 num repositorio com 40 abertas.
    # Sem o campo na resposta (permissao negada, consulta degradada), o total e
    # None: NAO MEDI e uma coisa, "nao ha nenhuma" e outra.
    #
    # `titulo` E TEXTO CRU DE TERCEIRO — quem abre uma issue num repositorio do
    # dono escolhe o que vai escrito ali. Ele pode ficar gravado, mas NAO pode
    # chegar ao campo `detalhe` de uma pendencia: esse campo entra no prompt da
    # sessao do botao "Resolver", que roda com Bash auto-aprovado. Foi assim que
    # o titulo de PR virou injecao de prompt uma vez (ver regras.py, regra 9).
    # Hoje nenhuma regra le `issues` e a tela usa so `issues_total`/`issues_url`.
    # O aviso fica AQUI, onde o campo nasce, e nao so onde ele e consumido.
    bloco_issues = no.get("issues")
    issues = []
    for it in ((bloco_issues or {}).get("nodes") or []):
        issues.append({"numero": it.get("number"), "titulo": it.get("title", "")[:120],
                       "url": it.get("url", ""), "dias": _dias(it.get("updatedAt", ""))})
    total_issues = (bloco_issues or {}).get("totalCount")

    return {
        "slug": no.get("nameWithOwner") or "",
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
        "issues": issues,
        "issues_total": total_issues if isinstance(total_issues, int) else None,
        "issues_url": url + "/issues",
        # `lido_em` e o carimbo DESTA leitura, e viaja dentro do proprio
        # `vulns`. E ele que sobrevive quando o valor e preservado numa rodada
        # em que os alertas nao vieram — e por isso e o unico relogio confiavel
        # para dizer ha quanto tempo este numero nao e relido.
        "vulns": (dict(alertas, url=url + "/security/dependabot",
                       lido_em=AGORA.isoformat(timespec="seconds"))
                  if alertas else {}),
    }


def _diga(motivo: str) -> None:
    """Fala na SAIDA DE ERRO, se houver uma. Sob pythonw nao ha, e tudo bem.

    Saida de erro e nao saida normal porque e dali que o `servir.py` tira o
    motivo quando o coletor falha — o `stdout` ele descarta.
    """
    if sys.stderr is not None:
        print("coletar_github: %s" % motivo, file=sys.stderr)


def issues_abertas(slug: str):
    """As issues abertas de UM repositorio. `None` quando nao deu para saber.

    Ferramenta de conferencia, para a linha de comando — a coleta de verdade
    passa por `main()`, que pega os 17 de uma vez. Reusa a mesma consulta e o
    mesmo tradutor de proposito: se um dia o formato mudar, muda nos dois.

    A distincao que importa: `[]` quer dizer "conferi, nao ha nada aberto", e
    `None` quer dizer "nao consegui conferir". Devolver `[]` na falha faria a
    tela comemorar um repositorio que ela nao conseguiu ler.
    """
    if not slug or "/" not in slug:
        _diga("slug invalido: falta o dono antes da barra")
        return None
    dados, erro = _gh_graphql(_consulta({"r0": slug}, com_vulns=False))
    if erro:
        # O MOTIVO VAI PARA A TELA, o retorno continua `None`. Quem roda isto
        # esta investigando por que um repositorio nao aparece; devolver `None`
        # calado esconde justamente a resposta que ele veio buscar.
        _diga(erro)
        return None
    no = (dados or {}).get("r0")
    if not no:
        _diga("o GitHub nao devolveu esse repositorio: nome errado, "
              "ou o token nao alcanca ele")
        return None
    return traduz(no, com_vulns=False)["issues"]


def main():
    tudo = banco.ler_tudo(usuario_id=banco.conta_local())
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
        # A primeira consulta pode falhar por falta de permissao para ler
        # alertas — e ai a segunda, sem esse campo, salva a rodada: CI e PR
        # valem por si.
        #
        # VALE TENTAR ATE CONTRA LIMITE DE COTA. O limite do GraphQL e por
        # PONTOS calculados por consulta, e o custo aqui e dominado pelo campo
        # de alertas — 100 alertas em cada um dos 17 apelidos —, que e
        # justamente o que a segunda consulta NAO pede. Ela e a barata: cabe no
        # saldo em boa parte das vezes em que a primeira nao coube. Desistir
        # congelaria CI, PR, issues, site e publicacao dos 17 durante toda a
        # janela do limite, a cada 20 minutos.
        dados, erro2 = _gh_graphql(_consulta(slugs, com_vulns=False))
        com_vulns = False
        if dados is None:
            print("FALHA ao consultar o GitHub: %s / %s" % (erro, erro2),
                  file=sys.stderr)
            return 1
        print("aviso: vim sem os alertas de segurança nesta rodada (%s)" % erro)

    con = banco.conectar()
    gravados = 0
    reusados = []          # projetos cujo numero de alertas nao deu para reler
    try:
        # FORA DO LACO: dentro, era um SELECT por repositorio, e no primeiro
        # giro de um banco novo o `criar_usuario` de dentro commitava a
        # transacao do coletor pela metade.
        dono = banco.conta_local(con)
        for alias, nome in por_alias.items():
            no = dados.get(alias)
            if not no:
                continue                   # repo sumiu ou sem acesso: fica sem camada
            novo = traduz(no, com_vulns)
            # NAO MEDIMOS OS ALERTAS DESTE REPOSITORIO. Gravar {} aqui apagaria
            # do painel um alerta de seguranca REAL que ja estava no banco — um
            # blip de rede as 20h faria "93 alertas abertos" virar silencio ate
            # a proxima coleta boa. Carregamos o valor anterior e dizemos de
            # quando ele e, para a tela poder mostrar que esta velho.
            #
            # A checagem e POR REPOSITORIO, e nao por rodada. Por rodada
            # (`if not com_vulns`) so cobria a consulta inteira ter caido para a
            # versao sem alertas. O caso que escapava: o token perde a permissao
            # de ler alertas e o GitHub devolve o repositorio COMPLETO, so com
            # `vulnerabilityAlerts: null` — rodada bem-sucedida, campo vazio,
            # 93 alertas apagados em silencio.
            #
            # `vulns` vazio quer dizer NAO MEDI, sempre: um repositorio com zero
            # alertas devolve `{"total": 0}`, que e dicionario cheio. As duas
            # coisas nunca se confundem aqui.
            if not novo.get("vulns"):
                antes = ((tudo.get(nome) or {}).get("github") or {})
                anterior = (antes.get("dados") or {}).get("vulns") or {}
                if anterior:
                    # A IDADE VAI DENTRO DO PROPRIO `vulns`, porque e ali que
                    # `regras.py` le. A versao anterior guardava num campo
                    # `vulns_medido_em` que NINGUEM lia — o comentario prometia
                    # "para a tela poder mostrar que esta velho" e a tela nunca
                    # mostrava. Numero preservado sem carimbo visivel e o
                    # painel republicando medida de semanas atras como se fosse
                    # de agora, para sempre, enquanto a permissao nao voltar.
                    # A ANCORA E `lido_em`, O CARIMBO DA PROPRIA MEDICAO — nao
                    # o `medido_em` da linha. O banco reescreve `medido_em` em
                    # TODA rodada bem-sucedida, e estas rodadas SAO
                    # bem-sucedidas: CI, PRs, issues e publicacao continuam
                    # sendo gravados; so os alertas e que nao vieram. Ancorado
                    # nele, `dias_sem_reler` dava zero para sempre, desde a
                    # primeira rodada — o aviso existia, tinha teste, e nunca
                    # disparava. O teste era verde porque simulava um estado que
                    # a operacao real nunca produz.
                    #
                    # Linha antiga, gravada antes deste campo existir, ganha o
                    # carimbo AGORA e passa a envelhecer a partir daqui: e o
                    # mais velho que da para afirmar sem inventar.
                    lido = anterior.get("lido_em") or antes.get("medido_em")
                    novo["vulns"] = dict(anterior, lido_em=lido,
                                         dias_sem_reler=_dias(lido))
                    reusados.append(nome)
            local = ((tudo.get(nome) or {}).get("local") or {}).get("dados") or {}
            antes_gh = ((tudo.get(nome) or {}).get("github") or {}).get("dados") or {}

            # O SITE: so para quem declarou endereco no casos.json. Projeto sem
            # endereco nao tem site para estar fora do ar.
            url_prod = local.get("url_prod") or ""
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

            # A PUBLICACAO: para TODO repositorio, nao so os com endereco de site.
            # Amarrar as duas coisas foi erro meu, achado rodando: o `dents` tem
            # workflow de deploy, tinha 4 commits publicados a menos que a main —
            # e ficava invisivel por nao ter `url_prod` escrito no casos.json.
            # A primeira chamada e barata e a maioria dos repositorios para nela
            # (sem workflow de publicacao, `mede_deploy` devolve {} e sai).
            dep = mede_deploy(novo["slug"], novo["branch_padrao"] or "main")
            novo["deploy"] = dep or antes_gh.get("deploy") or {}

            banco.gravar(nome, "github", novo, con, usuario_id=dono)
            gravados += 1
        con.commit()          # ver coletar.py: quem abriu a conexao commita
    finally:
        con.close()

    if not gravados:
        # HAVIA repositorios na lista (`if not slugs` ja saiu la em cima) e
        # nenhum foi gravado. Isso nao e uma coleta vazia, e uma coleta que
        # falhou: repositorio sumiu, token sem alcance, apelido que nao voltou.
        # Imprimir "ok: 0" e sair com 0 declara sucesso sobre nada — e no
        # servidor quem le nao e a linha, e o codigo de saida.
        # NA SAIDA DE ERRO, e nao na saida normal: `servir.py` guarda
        # `r.stderr` quando o coletor sai != 0 e joga fora o `stdout`. Escrito
        # em `print()` comum, este motivo existia e ia para o cano que ninguem
        # le — o painel dizia "a coleta falhou. Motivo:" e nada depois.
        print("FALHA: consultei o GitHub e nao consegui atualizar nenhum dos "
              "%d repositorios." % len(slugs), file=sys.stderr)
        return 1

    if reusados:
        # NA SAIDA NORMAL de proposito: a rodada deu certo, e `servir.py`
        # registra o `stdout` justamente no caminho de sucesso. E o sinal de
        # que alguma coisa esta errada com a permissao do token, num dia em que
        # nada mais grita.
        nomes = sorted(reusados)
        # A lista e cortada, e o corte se ANUNCIA: "(a, b, c, d, e)" com 17
        # projetos parece a lista inteira, e quem le acha que sabe quais sao.
        lista = ", ".join(nomes[:5])
        if len(nomes) > 5:
            lista += " e mais %d" % (len(nomes) - 5)
        print("aviso: nao consegui reler os alertas de segurança de %d "
              "projeto(s) (%s) — mantive o último número conhecido, marcado "
              "como velho." % (len(nomes), lista))

    print("ok: %d repositorios do GitHub atualizados%s"
          % (gravados, "" if com_vulns else " (sem alertas de segurança)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
