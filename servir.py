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

import contextlib
import hashlib
import hmac
import http.cookies
import ipaddress
import json
import math
import os
import re
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
# A PENEIRA ANTI-SSRF E REUSADA, NAO REESCRITA. `url_segura`,
# `host_publico`, `_ip_privado` e `mede_site` sao funcoes de modulo, sem
# estado. Quando essa peneira foi escrita, uma segunda copia dela matou o
# drift EM SILENCIO com 926 testes verdes; e a faixa CGNAT que faltava
# nela esteve aberta em producao. Uma copia aqui repetiria os dois erros.
#
# SEMPRE QUALIFICADO (`coletar_github.url_segura`), nunca
# `from coletar_github import ...`: `test_rotas.EXECUTA` guarda a palavra
# `coletar`, e `servir.coletar` existe como funcao de modulo aqui.
import coletar_github
import github_app
import cortina
import tarefas
import memoria
import passkey
import regras
# `auditoria.py` e puro (stdlib + `tarefas`, ver auditoria.py:4-10) e ENTRA NA
# IMAGEM (`Dockerfile:62-74`) por causa desta linha. `servir.py` continua sem
# importar `execucao` nem `fila` — `test_rotas.AMPUTADOS` cobra os dois nomes.
import auditoria
# `documentos.py` e puro (stdlib, ver o topo dele) e ENTRA NA IMAGEM por causa
# desta linha. Conta o progresso a partir dos criterios crus que o agente sobe.
import documentos


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
# O "slug" do GitHub App — o nome que aparece na URL de instalacao. E PUBLICO
# (github.com/apps/<slug>), e por isso mora ao lado do Client ID e nao junto do
# segredo. Sem ele a porta 2 responde 404: melhor nao ter porta do que ter
# porta que leva a um endereco que nao abre.
APP_DO_GITHUB = (os.environ.get("DERVS_GITHUB_APP_SLUG") or "").strip()

# Os UNICOS arquivos servidos alem da pagina. Delegar ao handler estatico
# publicava a pasta toda — inclusive o hub.db e o .git/config.
ESTATICOS_OK = {"/painel-projetos.svg", "/painel-projetos.png",
                "/painel-projetos.ico", "/favicon.ico", "/robots.txt"}

# A pasta `assets/` da etapa 13 — folha de estilo, marca, glifos dos selos e as
# duas famílias tipográficas servidas do próprio domínio.
#
# A lista nasce de UMA LEITURA DA PASTA na subida, e continua sendo permissão
# por caminho exato: cada arquivo vira uma entrada propria em `ROTAS`, entao
# nao ha prefixo permissivo e nao ha travessia de diretorio a defender —
# `/assets/../banco.py` simplesmente nao esta na tabela.
#
# A extensao e filtrada de proposito. Sem o filtro, o `CREDITOS.md` seria
# servido, e um `.py` que caisse ali por engano viraria codigo-fonte publico.
ESTATICOS_OK |= {"/" + arquivo.relative_to(AQUI).as_posix()
                 for arquivo in (AQUI / "assets").rglob("*")
                 if arquivo.is_file()
                 and arquivo.suffix in (".css", ".js", ".svg", ".png",
                                       ".woff2")}

COLETORES = {
    "local": (AQUI / "coletar.py", None),          # intervalo vem da linha de comando
    "github": (AQUI / "coletar_github.py", 20 * 60),
    "pesado": (AQUI / "coletar_pesado.py", 24 * 60 * 60),
}

# As camadas que medem A MAQUINA ONDE ESTE PROCESSO RODA: `local` varre as
# pastas de projeto, `pesado` abre o historico de cada uma. A camada `github`
# nao esta aqui porque ela mede a API do GitHub, que responde igual de qualquer
# lugar — e no servidor ela e justamente o que continua fazendo sentido.
CAMADAS_DESTA_MAQUINA = ("local", "pesado")


def _endereco_de_escuta() -> str:
    """Em que endereco o servidor abre a porta. Padrao: so o loopback.

    O padrao e o certo nesta maquina — a porta 4777 nao deve estar visivel na
    rede de casa. Dentro de um container ele e o errado, e o erro e mudo:
    `127.0.0.1` la dentro e o loopback DO CONTAINER, entao o nginx do host bate
    na porta publicada, o Docker encaminha para o IP do container, e ninguem
    esta escutando ali. O site responde 502 para sempre e o log do servidor nao
    tem uma linha de erro, porque ele subiu — so nao no endereco certo.
    """
    return (os.environ.get("DERVS_ESCUTA") or "").strip() or "127.0.0.1"


def _mede_esta_maquina() -> bool:
    """Se as camadas `local` e `pesado` devem rodar. `DERVS_COLETA_LOCAL=0` nao.

    No servidor a pasta de projetos nao existe, entao a varredura local volta
    com zero projetos. Gravar esse zero por cima do que o agente pareado mandou
    e a lei 2 deste repositorio sendo violada da pior forma: nao e o painel
    dizendo "nao sei", e o painel dizendo "nenhum" com a mesma cara de quem
    sabe. La o dado chega pelo agente, e quem mede a maquina e o agente.
    """
    valor = (os.environ.get("DERVS_COLETA_LOCAL") or "1").strip().lower()
    return valor not in ("0", "nao", "não", "false")

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

def _redes_confiaveis(cru):
    """Quem pode dizer "o cliente de verdade e outro". Vazio = ninguem.

    Le `DERVS_PROXIES_CONFIAVEIS`: uma lista separada por virgula, onde cada
    item e um endereco (`172.17.0.1`) ou uma faixa (`172.16.0.0/12`).

    POR QUE FAIXA. Atras do nginx, todo pedido chega ao container com o endereco
    do gateway do Docker — e esse endereco nao e previsivel: cada rede que o
    compose cria recebe a sub-rede que estiver livre na maquina. Fixar a
    sub-rede no compose foi tentado na etapa 16 e esbarrou em colisao com quem
    ja mora na VPS (26 containers). A faixa privada resolve sem adivinhacao, e
    nao alarga a confianca de verdade: a porta do container so aceita conexao
    vinda de `127.0.0.1` do host, que e o nginx.

    FALHA FECHADA. Item que nao e endereco nem faixa e DESCARTADO, nao vira
    permissao ampla. Um erro de digitacao no `.env` do servidor tem de virar
    "nao confio nisso", nunca "confio em todo mundo".
    """
    redes = []
    for pedaco in (cru or "").split(","):
        pedaco = pedaco.strip()
        if not pedaco:
            continue
        try:
            redes.append(ipaddress.ip_network(pedaco, strict=False))
        except ValueError:
            continue
    return tuple(redes)


def _vem_de_proxy(endereco: str, redes) -> bool:
    """Se `endereco` esta em alguma das redes confiaveis.

    Endereco ilegivel devolve False. `client_address` pode ser "?" quando a
    conexao ja morreu, e nesse caso a resposta e nao — nunca sim.
    """
    if not redes or not endereco:
        return False
    try:
        ip = ipaddress.ip_address(endereco)
    except ValueError:
        return False
    return any(ip in rede for rede in redes)


def _aviso_do_teto(dominio: str, redes):
    """O aviso a gritar quando o teto por origem virou balde unico. Ou None.

    O `except ValueError` de `_redes_confiaveis` descarta item mal escrito em
    silencio, e a lista pode ficar vazia de duas formas: erro de digitacao no
    `.env`, ou uma faixa perfeitamente escrita que nao casa com o gateway real —
    o pool padrao do Docker cai em `192.168.0.0/16` quando as faixas 172
    acabam, e naquela VPS ha 26 containers.

    Nos dois casos `_origem_do_pedido` volta a devolver o MESMO endereco para o
    mundo inteiro, o teto de cinco tentativas vira um balde unico, e o sintoma
    na tela e indistinguivel de um ataque de verdade.

    AVISA, NAO DERRUBA. Cair por causa de um erro de digitacao no `.env` tira o
    site do ar, e isso e pior que o problema que se quer evitar. Quem reprova a
    publicacao e o workflow, que confere o gateway de verdade depois de subir.
    Achado da revisao de seguranca da etapa 16, na conferencia das correcoes.
    """
    if dominio and not redes:
        return ("AVISO GRAVE: DERVS_PROXIES_CONFIAVEIS esta vazia e ha dominio"
                " publico. Atras do nginx TODO pedido chega com o mesmo"
                " endereco, entao o teto de tentativas virou um balde unico"
                " para a internet inteira: cinco chamadas de um estranho"
                " trancam o dono para fora. Ver docker-compose.yml.")
    return None


def _dominio_publico() -> str:
    """O dominio pelo qual o DERVS e acessado de fora. Vazio nesta maquina.

    Aceita o valor colado da barra do navegador — com esquema, com barra no fim,
    com maiuscula, com caminho. Um dominio mal digitado aqui nao da erro: da 403
    no site inteiro, calado, e a causa levaria uma tarde para ser achada.
    """
    bruto = (os.environ.get("DERVS_DOMINIO") or "").strip().lower()
    if not bruto:
        return ""
    return bruto.split("://", 1)[-1].strip("/").split("/", 1)[0]


def _enderecos_permitidos(porta: int, dominio: str):
    """Os conjuntos fechados de `Host` e de `Origin` aceitos. (hosts, origens)

    O loopback NAO sai dos HOSTS quando ha dominio: e por ele que o healthcheck
    do container bate na porta, de dentro. Tira-lo daqui deixaria o container
    eternamente `unhealthy` e a publicacao nunca concluiria.

    Das ORIGENS ele sai, e essa assimetria e de proposito. `Origin` so aparece
    em pedido que escreve, e no servidor nao existe pedido legitimo que se
    apresente como vindo de `http://localhost:4777` — mas existe uma pagina
    assim: o proprio DERVS rodando no computador do dono, na mesma porta e no
    mesmo navegador. Ela nao consegue nada hoje (o cookie de sessao e
    `SameSite=Lax` e nao viaja num POST entre sites, entao o pedido chega sem
    sessao e morre no 401), e continuar aceitando a origem seria confiar numa
    unica defesa. Apontado pela revisao de seguranca da etapa 16.

    A origem do dominio e `https://` e so. O nginx manda a porta 80 para a 443,
    entao um pedido que se apresente como `http://dervs.com.br` ou viajou em
    claro ou foi forjado — nos dois casos nao entra.
    """
    hosts = {"localhost:%d" % porta, "127.0.0.1:%d" % porta}
    if not dominio:
        return hosts, {"http://localhost:%d" % porta,
                       "http://127.0.0.1:%d" % porta}
    hosts.add(dominio)
    return hosts, {"https://" + dominio}


# Vazio nesta maquina, `dervs.com.br` no servidor. Tres comentarios deste
# arquivo — no `_entrar_github`, no `_entrar_local` e no que explica de onde sai
# o anfitriao — prometiam que a etapa 16 acrescentaria o dominio publico aqui.
# E esta linha.
DOMINIO = _dominio_publico()
HOSTS_OK, ORIGENS_OK = _enderecos_permitidos(PORTA, DOMINIO)

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
            # A MESMA conta que os coletores gravam. Fora do ambiente
            # local isto vira DONO_LOCAL e o laco nao ve nada: a memoria ainda
            # e de um inquilino so, e passar a ser de cada conta e trabalho da
            # etapa 16. DIVIDA NOMEADA, nao esquecimento.
            # UM dono so nas tres pontas. A medicao passou a ser lida como
            # `conta_local`, mas o silenciado e o arquivado continuavam no
            # padrao `DONO_LOCAL`: o que o dono escondeu pelo painel nao contava
            # como escondido aqui, e a pendencia entrava na memoria como aberta.
            dono = banco.conta_local(con)
            e = banco.montar_estado(con, usuario_id=dono)
            pend = regras.avaliar(e["projetos"], quota=e["quota"],
                                  silenciadas=banco.silenciadas(con,
                                                                usuario_id=dono),
                                  arquivadas=banco.arquivadas(usuario_id=dono,
                                                              con=con))
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


def _linhas_de_prova(linhas) -> list:
    """Linhas de `banco.provas_da_conta` (`criterio_id`, `medido_em`) no formato
    de `documentos.provas_validas` (`id`, `em`). E o UNICO ponto de conversao:
    sem ele `provas_validas` nao acha o id de ninguem e a conta nunca sai de
    "nao verificado", com todos os testes de cada lado verdes."""
    return [{"id": ln.get("criterio_id"), "prova": ln.get("prova"),
             "ok": ln.get("ok"), "em": ln.get("medido_em")}
            for ln in linhas or []]


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

    def _token_do_agente(self) -> str:
        """`Authorization: Token <token>`, e so nesse formato.

        Nao aceita o token na query nem no corpo de proposito: a query vai para
        o log de todo proxy no caminho, e o corpo faria o token viajar junto com
        um relatorio de megabytes que pode ser truncado no meio pelo teto.
        """
        cru = (self.headers.get("Authorization") or "").strip()
        pedaco = cru.split(None, 1)
        if len(pedaco) != 2 or pedaco[0].lower() != "token":
            return ""
        return pedaco[1].strip()

    # Os IPs de quem tem PERMISSAO de dizer "o cliente de verdade e outro".
    # Vazio por padrao, e de proposito: se qualquer um pudesse mandar
    # `X-Forwarded-For`, o teto por origem sumiria — bastaria variar o cabecalho
    # a cada chute. Na etapa 16 o container fica em 127.0.0.1 atras do nginx do
    # host, e sem esta lista TODA chamada chegaria como 127.0.0.1, dividindo um
    # balde unico de cinco tentativas por 15 min: um estranho gastaria o teto de
    # graca e o dono nunca mais parearia maquina nenhuma. Achado da revisao de
    # seguranca da etapa 11.
    # Aceita endereco solto (`172.17.0.1`) e faixa (`172.16.0.0/12`), porque o
    # gateway do Docker nao e previsivel: cada rede que o compose cria pega a
    # sub-rede que estiver livre. Fixar a sub-rede foi tentado na etapa 16 e
    # colide com quem ja mora na VPS. Ver `_redes_confiaveis`.
    PROXIES_CONFIAVEIS = None      # preenchido logo abaixo da classe

    def _origem_do_pedido(self) -> str:
        de = self.client_address[0] if self.client_address else "?"
        if not _vem_de_proxy(de, self.PROXIES_CONFIAVEIS):
            return de
        # O ULTIMO salto e o unico confiavel: o comeco da lista e escrito pelo
        # cliente e pode ser inventado inteiro.
        cru = (self.headers.get("X-Forwarded-For") or "").split(",")
        return (cru[-1].strip() or de) if cru else de

    # ---------------------------------------------------------- despacho
    def _caminho(self) -> str:
        """So o caminho, sem a query. A tabela de rotas casa EXATO."""
        return self.path.split("?", 1)[0]

    # ------------------------------------------------------- o dreno
    #
    # `protocol_version` e HTTP/1.0: o soquete fecha depois de TODA resposta.
    # E quem recusa um POST (401, 403, 404, 500) responde antes de qualquer
    # rota rodar -- e as rotas sao os unicos lugares que leem `rfile`. Recusa =
    # corpo INTOCADO no buffer de recepcao.
    #
    # Fechar um soquete com bytes por ler faz o sistema mandar um RST em vez do
    # FIN, e o RST DESCARTA a resposta que ja estava no buffer do outro lado. A
    # resposta foi escrita, viajou, e morreu a um passo de ser lida.
    #
    # No teste isso aparecia como `WinError 10053` em caso DIFERENTE a cada
    # corrida -- 2 em 24, medido em 02/09/2026, e havia quem chamasse de ruido
    # do Windows. Nao e: dos 405 pedidos com corpo de uma corrida, 189
    # terminavam com bytes por ler. Fora do teste, e o navegador de quem usa o
    # painel levando "conexao perdida" no lugar do 401 -- e toda tela que
    # trataria `401` mostrando "sua sessao venceu" mostra um erro de rede.
    #
    # AQUI E NAO EM CADA ROTA, pelo mesmo motivo de a classificacao de acesso
    # viver na tabela: `if` escrito dentro da funcao nasce esquecido na rota
    # seguinte. Rota nova ja nasce coberta.

    #: Ate onde vale drenar. Acima do maior corpo aceito (`TETO_DO_RELATORIO`,
    #: 4 MiB) e uma promessa que ninguem precisa cumprir: drenar um gigabyte
    #: que o cliente inventou seria pagar a banda de quem ataca. Corpo maior
    #: que isto continua levando RST, e isso e o certo.
    TETO_A_DRENAR = 8 * 1024 * 1024

    class _Contado:
        """Envelope de `rfile` que so anota quanto a rota leu.

        Sem contar nao da para saber quanto falta: cada rota tem um teto
        proprio, e algumas nao leem nada.
        """

        def __init__(self, arquivo):
            self._arquivo = arquivo
            self.lido = 0

        def read(self, k=-1):
            d = self._arquivo.read(k)
            self.lido += len(d)
            return d

        def readline(self, *a):
            d = self._arquivo.readline(*a)
            self.lido += len(d)
            return d

        #: Formas de LER que este envelope nao sabe contar. Delegar em
        #: silencio deixaria `lido` baixo, e o dreno tentaria ler A MAIS —
        #: num soquete de verdade isso nao estoura, BLOQUEIA, e a thread fica
        #: presa ate o cliente fechar. Melhor quebrar alto, na primeira vez,
        #: do que pendurar o servidor de vez em quando.
        NAO_CONTADAS = ("readinto", "readinto1", "read1", "peek", "readlines")

        def __getattr__(self, nome):
            if nome in self.NAO_CONTADAS:
                raise AttributeError(
                    "%s nao passa pelo contador do dreno. Use read() ou "
                    "readline(), ou ensine _Contado a contar %s."
                    % (nome, nome))
            return getattr(self._arquivo, nome)

    def parse_request(self):
        """Depois de ler a linha de pedido e os cabecalhos, zera a conta.

        O envelope e instalado antes de qualquer leitura, porque e so aqui que
        da para envolve-lo. Mas `parse_request` consome a linha de pedido e os
        cabecalhos pelo mesmo `rfile`, e esses bytes NAO sao corpo: contados,
        eles fariam o dreno achar que a rota ja leu o que nao leu.
        """
        pronto = super().parse_request()
        if isinstance(self.rfile, self._Contado):
            self.rfile.lido = 0
        return pronto

    def handle_one_request(self):
        """Atende um pedido e, ao fim, LE O CORPO QUE NINGUEM LEU.

        AQUI, E NAO NO DESPACHO. A primeira versao disto vivia em
        `_despachar`, e por isso cobria GET e POST e mais nada: `do_HEAD`
        responde 405 por fora, e PUT/DELETE/PATCH caem no 501 do
        `BaseHTTPRequestHandler` sem passar por rota nenhuma. Os tres deixavam
        o corpo inteiro por ler — 16 de 16 bytes, medido — e levavam o mesmo
        RST que este conserto existe para evitar. Achado pela revisao de
        02/09/2026, contra a mensagem de commit que dizia "num lugar so".
        """
        verdadeiro = self.rfile
        contado = self._Contado(verdadeiro)
        self.rfile = contado
        try:
            super().handle_one_request()
        finally:
            self.rfile = verdadeiro
            try:
                self._drenar(contado.lido)
            except Exception:
                # O dreno e cortesia com o cliente, nunca o desfecho do
                # pedido. Deixar uma excepcao daqui subir SUBSTITUIRIA o que
                # de fato aconteceu — inclusive uma excepcao de verdade vinda
                # do atendimento, cujo rastro se perderia.
                pass

    def _drenar(self, ja_lido: int):
        """Le o que sobrou do corpo declarado, para o fecho ser FIN e nao RST."""
        cabecalhos = getattr(self, "headers", None)
        if cabecalhos is None:
            return              # o pedido nem chegou a ser entendido
        # `Transfer-Encoding: chunked` sem `Content-Length` nao e drenado, e
        # isso e deliberado: o corpo em pedacos nao diz de antemao quanto e, e
        # adivinhar seria ler o inicio de outra coisa. Em producao o nginx
        # normaliza chunked em `Content-Length` antes de repassar, entao o
        # caminho nao existe la; um cliente que fale direto com a porta leva o
        # RST, e o preco e dele.
        try:
            n = int(cabecalhos.get("Content-Length") or 0)
        except (TypeError, ValueError):
            # Cabecalho torto: nao da para saber quanto e corpo, e chutar
            # seria ler o inicio de outra coisa. Quem manda `Content-Length`
            # invalido perde a propria resposta, e so a dele.
            return
        falta = min(n, self.TETO_A_DRENAR) - ja_lido
        if falta <= 0:
            return
        # PRAZO, E SO AQUI. Esta e a unica espera que um anonimo alcanca em
        # QUALQUER caminho -- 404 de URL inventada, 403 de Host, 401 sem
        # sessao --, e nenhum desses passa por balcao. Hoje o nginx segura
        # (`proxy_request_buffering` ligado, `client_max_body_size 2m`) e a
        # porta so aceita 127.0.0.1; mas essa defesa mora num arquivo que
        # nenhum workflow aplica. `socket.timeout` e subclasse de `OSError`, e
        # o laco abaixo ja para nele.
        #
        # O prazo e devolvido no fim porque `protocol_version` pode virar
        # HTTP/1.1 um dia -- o comentario de `do_HEAD` ja anuncia a intencao --
        # e ai a conexao seguiria viva com um prazo que ninguem escolheu.
        try:
            antes = self.connection.gettimeout()
            self.connection.settimeout(self.SEGUNDOS_PARA_DRENAR)
        except (OSError, AttributeError):
            antes = None            # soquete de mentira, ou ja fechado
        try:
            self._drenar_ate(falta)
        finally:
            try:
                self.connection.settimeout(antes)
            except (OSError, AttributeError):
                pass

    #: Quanto tempo vale esperar pelo corpo que o cliente prometeu. Curto de
    #: proposito: o corpo ja deveria estar no buffer -- quem manda o
    #: cabecalho e some nao merece uma thread.
    SEGUNDOS_PARA_DRENAR = 5

    def _drenar_ate(self, falta: int):
        while falta > 0:
            try:
                pedaco = self.rfile.read(min(falta, 65536))
            except OSError:
                # O cliente ja foi embora. Nao ha o que drenar e nao ha erro a
                # relatar: a resposta dele ja nao interessa a ninguem.
                break
            if not pedaco:
                break              # fim do fluxo: prometeu mais do que mandou
            falta -= len(pedaco)

    def _despachar(self, metodo: str):
        if not self._host_confiavel():
            return self._json(403, {"erro": "host nao permitido"})
        rota = ROTAS.get(self._caminho())
        if rota is None or rota.metodo != metodo:
            return self._json(404, {"erro": "nao existe"})
        # NEGA POR PADRAO, E AQUI — nao so na CI. O `test_rotas.py` cobra que
        # toda rota declare `acesso`, mas ele e garantia de suite: uma rota com
        # "Dado", "maquinas" ou qualquer string fora do conjunto caia por todos
        # os `if` abaixo e EXECUTAVA sem autenticacao nenhuma. O comentario
        # antigo afirmava aqui uma propriedade que o codigo nao tinha. Achado da
        # revisao de seguranca da etapa 11.
        if rota.acesso not in ACESSOS:
            return self._json(500, {"erro": "rota mal classificada"})
        # Zerado ANTES de qualquer decisao, e nao no meio do guarda: o
        # `http.server` reaproveita a MESMA instancia do handler nos pedidos de
        # uma conexao keep-alive, entao um atributo de pedido anterior
        # sobreviveria ate o seguinte — e e assim que se vaza autenticacao entre
        # requisicoes. Uma saida antecipada acima desta linha deixava o valor
        # velho de pe.
        self._maquina = None
        if rota.acesso == "dado" and self._sessao() is None:
            # Sem detalhe e sem nome de projeto nenhum no corpo.
            return self._json(401, {"erro": "entre para ver"})
        # A quarta classe (etapa 11): quem prova ser MAQUINA, e nao pessoa. O
        # agente nao tem cookie, nao manda Origin e nao tem token anti-CSRF —
        # ele carrega um token proprio, preso a uma maquina e a uma conta. A
        # classificacao vive na tabela pelo mesmo motivo das outras tres: `if`
        # dentro da funcao nasce esquecido na rota seguinte. O `self._maquina`
        # ja foi zerado la em cima.
        if rota.acesso == "maquina":
            self._maquina = banco.maquina_por_token(self._token_do_agente())
            if self._maquina is None:
                return self._json(401, {"erro": "token de maquina invalido"})
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
        estado = self._estado(self._sessao()["usuario_id"])
        # A chave crua `documentacao` (todos os criterios, ate 32 KiB por
        # projeto) NAO vai no poll de 60 s de toda aba: a tela recebe a CONTA
        # (`progresso`) e busca os criterios em `/api/progresso` quando abre o
        # projeto. A poda e aqui, e nao em `_estado`: `_progresso` e
        # `_desenvolver_pedir` leem os criterios crus do estado da conta.
        for p in estado["projetos"]:
            p.pop("documentacao", None)
        return self._json(200, estado)

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
            # `usuario_id` TAMBEM aqui, e nao so nas silenciadas. Sem ele
            # `montar_estado` lia a tabela `medida` inteira e devolvia os
            # projetos de TODAS as contas para qualquer sessao. Era o mesmo
            # IDOR que este docstring diz ter consertado, uma linha acima, na
            # metade que faltou. Achado da revisao de seguranca da etapa 11.
            e = banco.montar_estado(con, usuario_id=usuario_id)
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
            # O botao "Consertar com IA" so aparece atras deste bool. Calculado
            # DEPOIS do motor (`regras.avaliar`), nunca na origem: e do estado
            # cru que o motor le os achados. A regra vem de UMA constante, a
            # mesma que `_consertar_pedir` confere do lado do servidor.
            for x in pend:
                # Projeto bloqueado sai FALSO aqui: a rota o recusaria com 403, e
                # um botao que sempre falha e um botao que mente.
                x["consertavel"] = (
                    x.get("regra") in tarefas.REGRAS_CONSERTAVEIS_PELA_TELA
                    and not tarefas.projeto_bloqueado(x.get("projeto")))
            tend = memoria.tendencia(con, agora_iso)
            guardadas = banco.arquivadas_detalhe(usuario_id=usuario_id, con=con)
            provas_da_conta = banco.provas_da_conta(usuario_id, con=con)
        finally:
            con.close()
        # O SELO E CALCULADO AQUI, e nao no navegador.
        #
        # `regras.selo_do_projeto` existe desde a etapa 10 e ate esta linha
        # nunca era chamado por ninguem: a tela antiga pintava a cor por conta
        # propria. Deixar a tela nova recalcular os quatro estados em
        # JavaScript criaria uma segunda copia da regra mais importante do
        # produto — e, como este repositorio ja aprendeu, a copia que diverge e
        # sempre a que ninguem le.
        #
        # `camadas` viaja junto porque "sem dados" sem dizer QUAL camada
        # envelheceu e um veredito sem explicacao: a mesma mentira, so que
        # educada.
        for p in e["projetos"]:
            p["selo"] = regras.selo_do_projeto(p, pend)
            p["camadas"] = regras.camadas_do_selo(p)
            # A LISTA de achados sai daqui, e o RESUMO fica.
            #
            # Esta rota e o poll de 60 segundos de TODA aba, inclusive as que
            # nao mostram achado nenhum. Cada achado carrega `frase`,
            # `o_que_fazer` e `trecho` — ate 1.200 caracteres. Mandar isso a
            # cada minuto para desenhar tela que nao usa o dado e peso puro, e
            # o dado tem rota propria (`/api/auditoria`), buscada so quando a
            # tela de Auditoria abre.
            #
            # A poda e DEPOIS de `regras.avaliar` e de `selo_do_projeto`, e
            # isso e o ponto inteiro: e de `banco.montar_estado` que o motor le
            # os achados para virar pendencia. Podar la em cima — como a
            # revisao de Python de 02/09/2026 chegou a propor — deixaria os
            # dois testes de rota verdes e mataria a entrega em silencio.
            camada = p.get("auditoria")
            if isinstance(camada, dict):
                p["auditoria"] = {k: v for k, v in camada.items()
                                  if k != "achados"}
            # O PROGRESSO POR DOCUMENTACAO entra DEPOIS do selo, e o selo nunca
            # o le (`test_desenvolver.test_o_selo_nao_muda_com_ou_sem_documentacao`).
            # O servidor RECALCULA a conta dos criterios crus: um percentual que
            # o agente mandasse no meio e ignorado. `medido_em` e o da camada
            # local, a mesma que carimbou a chave `documentacao`.
            nome_do_projeto = p.get("nome") or ""
            veredito, provado_em = documentos.provas_validas(
                p.get("documentacao"), nome_do_projeto,
                _linhas_de_prova(provas_da_conta.get(nome_do_projeto)))
            p["progresso"] = documentos.progresso(
                p.get("documentacao"), nome_do_projeto,
                (p.get("medido_em") or {}).get("local"),
                provas=veredito, provado_em=provado_em)
        return {
            "agora": agora_iso,
            "pendencias": pend,
            # O que o dono mandou sumir para sempre, com motivo e data. Some da
            # lista de pendencias e reaparece aqui — nunca sem deixar rastro.
            "arquivadas": guardadas,
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
            # O motivo por que a coleta do GitHub nao mediu ESTA conta (linha
            # `_github`, lida so com o `usuario_id` da sessao). `None` quando
            # nunca tentou. `falhas_de_coleta` acima e da rodada inteira.
            "github_da_conta": e["github_da_conta"],
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
            corpo = json.loads(self.rfile.read(max(0, min(n, 1024))) or b"{}")
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

    CONTA_LOCAL = banco.CONTA_LOCAL   # uma copia so; ver banco.py

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
            corpo = json.loads(self.rfile.read(max(0, min(n, teto))) or b"{}")
        except (ValueError, OSError):
            return None
        return corpo if isinstance(corpo, dict) else None

    def _texto_do_corpo(self, corpo, campo: str, teto: int = 4096) -> str:
        """Um campo de texto do corpo, com teto. String vazia se torto."""
        valor = (corpo or {}).get(campo)
        if not isinstance(valor, str) or len(valor) > teto:
            return ""
        return valor

    @staticmethod
    def _numero_do_corpo(corpo, campo: str, conversor):
        """Um campo numerico OPCIONAL do corpo, convertido com `conversor`
        (`int` ou `float`). Ausente ou `None` -> `(True, None)`. Presente e
        valido -> `(True, valor)`. Torto (`{}`, `[]`, texto nao numerico)
        -> `(False, None)` — quem chama recusa fechado com 400, em vez de
        deixar `float()`/`int()` estourar `TypeError` fora de um `try` e
        derrubar a rota em 500 (achado da revisao de seguranca de
        02/09/2026: uma maquina pareada mandando `custo_usd: {}`)."""
        valor = (corpo or {}).get(campo)
        if valor is None:
            return True, None
        if isinstance(valor, bool):
            return False, None
        try:
            return True, conversor(valor)
        except (TypeError, ValueError):
            return False, None

    def _bytes_do_corpo(self, corpo, campo: str):
        """Um campo base64url do corpo, ja decodificado. None se torto."""
        return passkey.de_b64url(self._texto_do_corpo(corpo, campo,
                                                      teto=passkey.TETO_DO_B64))

    # O 403 do anti-CSRF vencido tem UM lugar so. O `motivo` e o que deixa a tela
    # distinguir "esta pagina ficou velha" de qualquer outro 403 (origem, host,
    # sessao): ela abre a faixa so com `motivo === "pagina_velha"`. A frase
    # continua igual porque `test_servir` a cobra.
    PAGINA_VELHA = {"erro": "recarregue a pagina (token vencido)",
                    "motivo": "pagina_velha"}

    def _recusa_pagina_velha(self):
        return self._json(403, dict(self.PAGINA_VELHA))

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
        # NAO conta como tentativa, e a diferenca importa. Pedir um desafio nao
        # revela nada e nao chuta nada — quem chuta e `/entrar/chave`, que tem
        # o teto. Se contasse aqui, cinco cliques no botao (com a pessoa
        # desistindo do PIN no meio) trancariam a conta por 15 minutos, que e
        # exatamente o que aconteceu com o dono em 26/08 por outro caminho.
        # O crescimento de memoria ja e barrado pelo teto de `passkey.Desafios`,
        # que descarta o mais velho em vez de recusar o mais novo.
        bilhete, desafio = DESAFIOS.abrir(time.time())
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
        if sessao is None:
            # A sessao pode vencer ENTRE o despacho e esta linha. Sem a guarda,
            # indexar `None` levanta TypeError e devolve 500 onde o certo e 403.
            # Mesmo achado que ja estava anotado em `_silenciar`.
            return self._json(403, {"erro": "entre de novo"})
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
        if sessao is None:
            # A sessao pode vencer ENTRE o despacho e esta linha. Sem a guarda,
            # indexar `None` levanta TypeError e devolve 500 onde o certo e 403.
            # Mesmo achado que ja estava anotado em `_silenciar`.
            return self._json(403, {"erro": "entre de novo"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
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
        if sessao is None:
            # A sessao pode vencer ENTRE o despacho e esta linha. Sem a guarda,
            # indexar `None` levanta TypeError e devolve 500 onde o certo e 403.
            # Mesmo achado que ja estava anotado em `_silenciar`.
            return self._json(403, {"erro": "entre de novo"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
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
        if sessao is None:
            # A sessao pode vencer ENTRE o despacho e esta linha. Sem a guarda,
            # indexar `None` levanta TypeError e devolve 500 onde o certo e 403.
            # Mesmo achado que ja estava anotado em `_silenciar`.
            return self._json(403, {"erro": "entre de novo"})
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
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
        if sessao is None:
            # A sessao pode vencer ENTRE o despacho e esta linha. Sem a guarda,
            # indexar `None` levanta TypeError e devolve 500 onde o certo e 403.
            # Mesmo achado que ja estava anotado em `_silenciar`.
            return self._json(403, {"erro": "entre de novo"})
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
        # A UNICA vez que estes codigos existem em claro fora do papel do dono.
        # Nao vao para log, nao voltam numa segunda chamada, nao ficam no banco.
        return self._json(200, {
            "codigos": banco.gerar_codigos_de_recuperacao(sessao["usuario_id"]),
            "aviso": "anote agora; eles nao aparecem de novo"})

    # ------------------------------------------------- as maquinas (etapa 11)
    #
    # TRES PORTAS DO DONO (sessao completa) e DUAS DO AGENTE (token de maquina).
    # A separacao importa: a do agente nao pode exigir cookie nem Origin, senao
    # o agente nunca reporta; a do dono nao pode aceitar token de maquina, senao
    # um relatorio roubado vira acesso ao painel.

    # Dez minutos. Seis digitos sao um milhao de possibilidades, e o que os
    # segura sao tres coisas: este prazo, o uso unico e o teto de chute por
    # origem la embaixo. Prazo mais longo e um milhao de tentativas de graca.
    MINUTOS_DO_CODIGO = 10
    # O relatorio inteiro de uma maquina com ~20 repositorios. Ha teto porque o
    # corpo e lido para a memoria antes de virar JSON.
    TETO_DO_RELATORIO = 4 * 1024 * 1024

    def _maquinas(self):
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        return self._json(200, {
            "maquinas": banco.maquinas_do_usuario(sessao["usuario_id"])})

    def _maquina_parear(self):
        """O dono gera o codigo que ele vai digitar na outra maquina."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
        codigo = self._novo_pareamento(sessao["usuario_id"])
        if not codigo:
            return self._json(503, {"erro": "tente de novo em um minuto"})
        return self._json(200, {"codigo": codigo,
                                "minutos": self.MINUTOS_DO_CODIGO})

    # Quantos codigos abertos uma origem pode criar por janela. NAO e teto de
    # chute de segredo: e teto de CRIACAO, e existe porque cada codigo ocupa
    # uma vaga num espaco de um milhao COMPARTILHADO por todas as contas. Vinte
    # e folga larga para quem esta conectando maquinas de verdade.
    TETO_DE_CODIGOS = 20

    def _novo_pareamento(self, usuario_id: int) -> str:
        """Um codigo de seis digitos aberto para aquela conta, ou "".

        DUAS COISAS QUE NAO ESTAVAM AQUI, e as duas sao da revisao de seguranca
        de 01/09/2026:

        1. A LIMPEZA. `codigo_hash` e PRIMARY KEY global e nada nunca era
           apagado: quem gerasse codigos em laco enchia o espaco e trancava o
           dono junto. Limpar o vencido antes de sortear e o conserto barato.
        2. O TETO POR ORIGEM, com balcao proprio. Sem ele, esta rota criava
           estado permanente de graca. Balcao SEPARADO do chute de codigo
           (`pareamento`) de proposito: misturar os dois faria quem gera trancar
           quem digita.

        O laco de cinco continua: colisao levanta `IntegrityError`, e silencia-la
        punha a maquina de um dentro da conta do outro.
        """
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="codigos",
                                           teto=self.TETO_DE_CODIGOS):
            return ""
        try:
            banco.limpar_pareamentos_vencidos()
        except sqlite3.Error:
            pass                      # limpar e higiene, nao pre-requisito
        for _ in range(5):
            codigo = banco.novo_codigo(6)
            try:
                banco.abrir_pareamento(usuario_id, codigo,
                                       banco.prazo(self.MINUTOS_DO_CODIGO * 60))
            except sqlite3.IntegrityError:
                continue
            return codigo
        return ""

    # ------------------------------ conectar simples: o pedido do computador (A)
    #
    # O computador PEDE (`/agente/pedir`, aberta), o dono AUTORIZA no navegador
    # conferindo nome e codigo (`/api/pedido*`), e o computador RESGATA o token
    # (`/agente/esperar`, aberta). O codigo de seis digitos antigo e o
    # `/api/conectador` (que CRIAVA estado num POST) deixaram de existir no
    # caminho do arquivo; o caminho do comando colado continua em
    # `/api/maquinas/parear`.
    #
    # Cada rota paga o PROPRIO balcao, por origem: misturar balcoes tranca a
    # maquina legitima, e isso ja aconteceu duas vezes nesta casa. As duas
    # rotas do computador sao "aberta" por necessidade -- quem chega ainda nao
    # tem token. O nome do campo e `pedido`, nunca `token`
    # (`test_servir.PALAVRAS_PROIBIDAS`).
    TETO_DE_PEDIDOS = 10          # `/agente/pedir`, por origem e janela (900 s)
    TETO_DE_ESPERAS = 300         # `/agente/esperar`: um a cada 3 s
    TETO_DE_CODIGOS_CURTOS = 20   # chute no codigo curto: GET e autorizar juntos
    TETO_DE_PACOTES = 10          # `/agente/pacote`, por maquina
    INTERVALO_DE_ESPERA = 5       # segundos entre uma pergunta e outra

    def _agente_pedir(self):
        """O computador abre um pedido e recebe o segredo dele e o codigo curto."""
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="pedir",
                                           teto=self.TETO_DE_PEDIDOS):
            return self._json(429, self.RECUSA)
        corpo = self._corpo_json(teto=4096)
        if corpo is None:
            return self._json(400, {"erro": "pedido invalido"})
        nome = self._limpo(corpo.get("maquina"), 120) \
            if isinstance(corpo.get("maquina"), str) else ""
        try:
            banco.limpar_pedidos_vencidos()
        except sqlite3.Error:
            pass                      # limpar e higiene, nao pre-requisito
        for _ in range(5):
            try:
                pedido, codigo = banco.abrir_pedido_de_computador(
                    nome or "computador", self.MINUTOS_DO_CODIGO)
            except sqlite3.IntegrityError:
                continue              # colisao do codigo: sorteia outro
            return self._json(200, {"pedido": pedido, "codigo": codigo,
                                    "minutos": self.MINUTOS_DO_CODIGO,
                                    "intervalo": self.INTERVALO_DE_ESPERA})
        return self._json(503, {"erro": "tente de novo em um minuto"})

    def _agente_esperar(self):
        """O computador pergunta se o dono ja autorizou. O token sai UMA vez."""
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="esperar",
                                           teto=self.TETO_DE_ESPERAS):
            return self._json(429, self.RECUSA)
        corpo = self._corpo_json(teto=4096)
        pedido = self._texto_do_corpo(corpo, "pedido", teto=128)
        if corpo is None or len(pedido) < 16:
            return self._json(400, {"erro": "pedido invalido"})
        estado, token = banco.resgatar_pedido_de_computador(pedido)
        if estado == "esperando":
            return self._json(202, {"estado": "esperando",
                                    "intervalo": self.INTERVALO_DE_ESPERA})
        if estado == "token":
            # A UNICA vez que este token existe fora da maquina que o pediu.
            return self._json(200, {"token": token})
        # A MESMA resposta para desconhecido, vencido e ja resgatado.
        return self._json(404, {"erro": "nao existe"})

    def _codigo_curto_da_consulta(self, bruto):
        """O codigo normalizado, ou "" com a recusa JA respondida (400 antes do
        balcao e sem tocar o banco; 429 se o balcao estourou)."""
        codigo = banco.normalizar_codigo_de_pedido(bruto)
        if not codigo:
            self._json(400, {"erro": "codigo invalido"})
            return ""
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="codigo_curto",
                                           teto=self.TETO_DE_CODIGOS_CURTOS):
            self._json(429, self.RECUSA)
            return ""
        return codigo

    def _pedido_ver(self):
        """O dono confere nome e codigo do computador que pediu."""
        sessao = self._sessao()
        if sessao is None:            # venceu entre o despacho e esta linha
            return self._json(403, {"erro": "entre de novo"})
        consulta = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        codigo = self._codigo_curto_da_consulta(
            (consulta.get("codigo") or [""])[0])
        if not codigo:
            return
        # "nao existe", vencido e "autorizado por outra conta": a mesma resposta.
        visto = banco.ver_pedido_de_computador(codigo, sessao["usuario_id"])
        if visto is None:
            return self._json(404, {"erro": "nao existe"})
        return self._json(200, visto)

    def _pedido_autorizar(self):
        """O dono diz sim ao computador do codigo. O computador resgata depois."""
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        codigo = self._codigo_curto_da_consulta(corpo.get("codigo"))
        if not codigo:
            return
        usuario = sessao["usuario_id"]
        efeito = banco.autorizar_pedido_de_computador(codigo, usuario)
        visto = (banco.ver_pedido_de_computador(codigo, usuario)
                 if efeito != "nao_existe" else None)
        if visto is None:
            return self._json(404, {"erro": "nao existe"})
        return self._json(200, {"ok": True, "maquina": visto["maquina"],
                                "ja_estava": efeito == "ja_estava"})

    # O programa que o computador baixa, e o ajudante do arquivo. Sao LIDOS do
    # disco e entregues como texto, nunca importados: o servidor nao pode
    # arrastar `execucao.py` nem `tkinter`. `Dockerfile` e `test_imagem` cobram
    # os nomes. A ORDEM da tupla e a do `versao`.
    PACOTE = ("agente/__init__.py", "agente/enviar.py", "coletar.py",
              "banco.py", "documentos.py", "tarefas.py")

    def _ler_pacote(self):
        """[{"caminho","conteudo"}] na ordem de `PACOTE`, ou `None` se faltar
        QUALQUER arquivo: nunca se entrega pacote parcial."""
        arquivos = []
        for caminho in self.PACOTE:
            try:
                texto = (AQUI / caminho).read_bytes().decode("utf-8")
            except (OSError, UnicodeDecodeError):
                return None
            arquivos.append({"caminho": caminho, "conteudo": texto})
        return arquivos

    def _agente_pacote(self):
        """O programa que mede, para o computador que ja tem token."""
        maquina = getattr(self, "_maquina", None)
        if maquina is None:            # cinto, alem do guarda do despacho
            return self._json(401, {"erro": "token de maquina invalido"})
        if not cortina.registrar_tentativa(
                "maquina:%d" % maquina["id"], time.time(), balcao="pacote",
                teto=self.TETO_DE_PACOTES):
            return self._json(429, self.RECUSA)
        arquivos = self._ler_pacote()
        if arquivos is None:
            return self._json(503, {"erro": "o pacote nao esta nesta copia"})
        resumo = hashlib.sha256("".join(
            a["caminho"] + "\n" + a["conteudo"] + "\n" for a in arquivos
        ).encode("utf-8")).hexdigest()
        return self._json(200, {
            "versao": resumo,
            "so_mede": banco.maquina_so_mede(maquina["id"],
                                             maquina["usuario_id"]),
            "arquivos": arquivos})

    # O arquivo que a tela entrega: o molde do lote do Windows, uma linha
    # marcadora e o `conectador.py` com o endereco do painel no lugar de
    # `ALVO`. E `GET` e NAO CRIA NADA (o pareamento nasce depois, quando o
    # computador pede), entao nao ha estado para outro site queimar.
    #
    # NENHUM DOS DOIS MORA EM `assets/`: `ESTATICOS_OK` e servido ANTES da
    # cortina. Sao lidos do disco por nome; o `Dockerfile` os copia por nome e
    # `test_imagem.py` cobra a lista -- a rota responderia 200 aqui e 500 em
    # producao, que e o modo de falha da etapa 16.
    CONECTADOR = AQUI / "conectador.py"
    CONECTADOR_CMD = AQUI / "conectador.cmd"
    MARCA_DO_PYTHON = "#:DERVS-PYTHON"

    def _endereco_publico(self) -> str:
        """O endereco que o computador vai chamar de volta.

        No servidor sai do dominio configurado (`https`); local, do `Host`, que
        o despacho JA conferiu contra `HOSTS_OK`. Nunca do `Origin` (um GET nao
        o manda) nem de cabecalho nao conferido."""
        if DOMINIO:
            return "https://" + DOMINIO
        return "http://" + (self.headers.get("Host") or "")

    @staticmethod
    def _injetar(fonte: str, alvo: str) -> str:
        """Troca a linha marcada `# DERVS:ALVO` no fonte do conectador.

        `json.dumps` monta o literal Python: o valor e nosso, mas escapa-lo e o
        que impede que um dia ele carregue uma aspa e quebre o arquivo na
        maquina do dono. A marca e conferida por `test_conectador.py`."""
        linhas = []
        for linha in fonte.splitlines():
            if linha.endswith("# DERVS:ALVO"):
                linha = "ALVO = %s   # DERVS:ALVO" % json.dumps(alvo)
            linhas.append(linha)
        return "\n".join(linhas) + "\n"

    def _arquivo_de_conectar(self):
        """Entrega o `.cmd` que baixa o Python, pede a pasta e pareia."""
        try:
            molde = self.CONECTADOR_CMD.read_text(encoding="utf-8")
            fonte = self.CONECTADOR.read_text(encoding="utf-8")
            # Falha fechada: sem a marca o arquivo pareia com o endereco errado.
            if sum(1 for l in fonte.splitlines()
                   if l.endswith("# DERVS:ALVO")) != 1:
                raise ValueError("marca do alvo")
            junto = (molde.splitlines() + [self.MARCA_DO_PYTHON]
                     + self._injetar(fonte, self._endereco_publico()).splitlines())
            # Lote do Windows com LF quebra rotulos, e o repositorio forca LF.
            corpo = ("\r\n".join(junto) + "\r\n").encode("ascii")
        except (OSError, ValueError):
            # `UnicodeError` e `ValueError`: arquivo que nao e ASCII nao sai.
            return self._json(503, {"erro":
                                    "o arquivo de conectar nao esta nesta copia"})
        self.send_response(200)
        # NAO e `text/html`: o navegador nao pode renderizar isto.
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition",
                         'attachment; filename="conectar-dervs.cmd"')
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    # ------------------------------------------- o endereco do servidor (B2)
    #
    # AQUI O PAINEL PASSA A BUSCAR UMA URL QUE O USUARIO DIGITOU. E a superficie
    # classica de pedir ao servidor que bata em endereco interno, e a defesa nao
    # e escrita aqui: e a mesma de `coletar_github`, chamada de fora.
    #
    # O TETO TEM BALCAO PROPRIO. `mede_site` bloqueia a thread do pedido por ate
    # 8 segundos por tentativa; sem teto, um punhado de pedidos prende o
    # servidor inteiro. E o balcao NAO e emprestado de outra coisa: misturar
    # balcoes tranca a maquina legitima, e isso ja aconteceu duas vezes nesta
    # casa.
    TETO_DE_ENDERECOS = 20

    # O balcao dos SERVIDORES e PROPRIO — nunca o `TETO_DE_ENDERECOS`. Misturar
    # balcoes tranca a maquina legitima, e isso ja aconteceu duas vezes nesta
    # casa (`servir.py:1581-1585`). Cadastrar servidor nao bate em rede nenhuma,
    # mas o teto continua existindo para limitar a velocidade de criacao.
    TETO_DE_SERVIDORES = 20

    def _servidores(self):
        """Os servidores da conta, so da conta de quem pergunta."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        lista = banco.servidores(sessao["usuario_id"])
        # `padrao_subdominio` tem UM jeito so de dizer "nenhum" em cada lado:
        # `None` no banco, `""` no JSON. A troca mora so aqui, na borda.
        for item in lista:
            item["padrao_subdominio"] = item.get("padrao_subdominio") or ""
        return self._json(200, {"servidores": lista})

    def _servidor_guardar(self):
        """Cadastra um servidor nomeado. Nenhum segredo entra aqui: so nome e
        padrao de subdominio, os dois publicos."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
        corpo = self._corpo_json(teto=4096) or {}
        nome = self._texto_do_corpo(corpo, "nome", teto=60).strip()
        padrao = self._texto_do_corpo(corpo, "padrao_subdominio", teto=200).strip()
        if not nome:
            return self._json(400, {"erro": "diga o nome do servidor"})

        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="servidor",
                                           teto=self.TETO_DE_SERVIDORES):
            return self._json(429, self.RECUSA)

        id_ = banco.guardar_servidor(sessao["usuario_id"], nome, padrao or None)
        if id_ is None:
            return self._json(400, {"erro": "esse nome ja existe nesta conta, "
                                            "ou voce ja tem 20 servidores "
                                            "cadastrados"})
        return self._json(200, {"id": id_, "nome": nome,
                                "padrao_subdominio": padrao})

    def _servidor_remover(self):
        """Apaga um servidor da conta, e os enderecos dele junto (CASCADE).
        Nao e seu responde IGUAL a nao existe."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
        corpo = self._corpo_json(teto=4096) or {}
        ok, id_ = self._numero_do_corpo(corpo, "id", int)
        if not ok or id_ is None:
            return self._json(400, {"erro": "id invalido"})
        if not banco.remover_servidor(sessao["usuario_id"], id_):
            return self._json(404, {"erro": "nao existe"})
        return self._json(200, {"ok": True})

    def _enderecos(self):
        """O que esta gravado, so da conta de quem pergunta — uma linha por
        (projeto, servidor), ordenada por (nome do servidor, projeto)."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        por_projeto = banco.enderecos_por_servidor(sessao["usuario_id"])
        lista = [{"servidor_id": item["servidor_id"], "servidor": item["servidor"],
                 "projeto": projeto, "url": item["url"]}
                for projeto, itens in por_projeto.items() for item in itens]
        lista.sort(key=lambda l: (l["servidor"], l["projeto"]))
        return self._json(200, {"enderecos": lista})

    def _endereco_guardar(self):
        """Grava o endereco de producao de um projeto NUM SERVIDOR, e mede se
        ele responde."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
        corpo = self._corpo_json(teto=4096) or {}
        projeto = self._texto_do_corpo(corpo, "projeto", teto=120).strip()
        url = self._texto_do_corpo(corpo, "url", teto=2048).strip()
        if not projeto:
            return self._json(400, {"erro": "diga de qual projeto e o endereco"})

        # ENTRE A LEITURA DO CORPO E A PENEIRA. Ausente ou torto e 400 mesmo
        # para o caminho de apagar: "sem endereco" continua exigindo saber DE
        # QUAL servidor se esta falando.
        ok, servidor_id = self._numero_do_corpo(corpo, "servidor_id", int)
        if not ok or servidor_id is None:
            return self._json(400, {"erro":
                                    "diga em qual servidor esse endereco mora"})

        # Apagar nao gasta o balcao nem bate em lugar nenhum. Mas "nao e
        # seu" responde IGUAL a "nao existe" nos dois caminhos — achado da
        # revisao (04/09/2026): o de gravar ja devolvia 404 aqui embaixo,
        # e este devolvia 200 mesmo quando `servidor_id` era de outra
        # conta. Nao vazava dado (o banco ja recusava gravar), mas a
        # inconsistencia e exatamente o tipo de fresta que ensina errado.
        if not url:
            if not banco.guardar_endereco_de_producao(
                    sessao["usuario_id"], servidor_id, projeto, None):
                return self._json(404, {"erro": "nao existe"})
            return self._json(200, {"projeto": projeto, "url": "",
                                    "ok": None, "guardado": False})

        # A PENEIRA, ANTES DE QUALQUER COISA. `url_segura` e checagem de forma,
        # sem rede; `host_publico` resolve o nome e recusa o que aponta para
        # dentro. As duas juntas cobrem `localhost`, 127/8, 10/8, 172.16/12,
        # 192.168/16, 169.254/16, o loopback IPv6, a faixa CGNAT 100.64/10 e o
        # IPv4 mapeado em IPv6 — e `mede_site` nunca segue redirecionamento,
        # que e como o endereco publico viraria um interno no meio do caminho.
        if not coletar_github.url_segura(url):
            # PURA E SEM REDE: pode vir antes do teto sem custo nenhum, e barra
            # de graca o caso mais comum.
            return self._json(400, {"erro": self.ENDERECO_RECUSADO})

        # O TETO VEM ANTES DE QUALQUER COISA QUE TOQUE A REDE, e nao so antes de
        # `mede_site`. `host_publico` chama `getaddrinfo` SEM PRAZO: um punhado
        # de POSTs com nomes que nao resolvem segura uma thread cada um pelo
        # tempo do resolvedor, e o teto nunca chegava a ser consultado porque a
        # fila ja estava presa. Achado pela revisao de Python.
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="endereco",
                                           teto=self.TETO_DE_ENDERECOS):
            return self._json(429, self.RECUSA)

        if not coletar_github.host_publico(urllib.parse.urlsplit(url).hostname):
            return self._json(400, {"erro": self.ENDERECO_RECUSADO})

        # `servidor_id` de OUTRA conta: o banco confere o dono e devolve
        # `False` SEM GRAVAR. "nao e seu" responde igual a "nao existe" — e
        # ISSO ACONTECE ANTES DE MEDIR: recusar nao pode custar uma medicao.
        if not banco.guardar_endereco_de_producao(sessao["usuario_id"],
                                                   servidor_id, projeto, url):
            return self._json(404, {"erro": "nao existe"})
        # `mede_site` devolve `ok` como None para NAO DEU PARA MEDIR, e isso nao
        # e fora do ar — a invariante esta escrita no docstring dela. Os tres
        # estados viajam separados para a tela nao poder confundi-los.
        medida = coletar_github.mede_site(url)
        return self._json(200, {"projeto": projeto, "url": url, "guardado": True,
                                "ok": medida.get("ok"),
                                "codigo": medida.get("codigo"),
                                "erro": medida.get("erro"),
                                "medido_em": banco.agora()})

    # A frase que a tela mostra quando a peneira barra. ELA E NOSSA, e nao
    # repassada da excecao: `URLError` carrega a URL, e mensagem de erro que
    # ecoa o que o chamador escreveu e por onde um endereco interno vazaria de
    # volta. Recusar endereco interno e comportamento CERTO, e a tela diz por
    # que em vez de parecer defeito.
    ENDERECO_RECUSADO = ("esse endereco aponta para dentro de uma rede privada, "
                         "ou nao e um endereco http(s) publico. O DERVS so mede "
                         "endereco que qualquer um alcanca pela internet.")

    # O balcao da SUGESTAO e PROPRIO — nunca `TETO_DE_ENDERECOS` nem
    # `TETO_DE_SERVIDORES`. Misturar balcoes tranca a maquina legitima
    # (`servir.py:1581-1585`), e esta rota e a mais cara das tres: cada
    # chamada pode medir ate `MAX_SUGESTOES` sites.
    TETO_DE_SUGESTOES = 5

    # Cada medicao custa ate 5s de DNS + 2 x 8s de tentativa + 1,5s de pausa
    # ~= 22,5s de pior caso (`coletar_github.mede_site`). Tres candidatos por
    # chamada = ate ~68s de thread do servidor; e por isso o numero e 3, e
    # nao "todos os projetos que casam".
    MAX_SUGESTOES = 3

    def _servidor_sugerir(self):
        """Testa o padrao do servidor contra os projetos que o DERVS ja
        conhece e PROPOE. Nunca grava — nem uma linha em `endereco_producao`."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
        corpo = self._corpo_json(teto=4096) or {}
        ok, servidor_id = self._numero_do_corpo(corpo, "servidor_id", int)
        if not ok or servidor_id is None:
            return self._json(400, {"erro":
                                    "diga de qual servidor e a sugestao"})

        # "nao e seu" responde IGUAL a "nao existe" — a mesma convencao das
        # quatro portas da fila (04/09/2026).
        servidor = next((s for s in banco.servidores(sessao["usuario_id"])
                        if s["id"] == servidor_id), None)
        if servidor is None:
            return self._json(404, {"erro": "nao existe"})
        padrao = servidor.get("padrao_subdominio")
        if not padrao:
            return self._json(200, {"sugestoes": []})

        # O TETO VEM ANTES DE QUALQUER COISA QUE TOQUE A REDE — o mesmo
        # motivo de `_endereco_guardar` (`servir.py:1708-1712`).
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="sugestao",
                                           teto=self.TETO_DE_SUGESTOES):
            return self._json(429, self.RECUSA)

        ja_tem = {p for p, itens in
                 banco.enderecos_por_servidor(sessao["usuario_id"]).items()
                 if any(i["servidor_id"] == servidor_id for i in itens)}
        nomes = sorted(p["nome"] for p in
                       banco.montar_estado(usuario_id=sessao["usuario_id"])
                       ["projetos"] if p["nome"] not in ja_tem)

        # O teto e de MEDICOES, nao de acertos (achado da revisao de
        # seguranca, 04/09/2026). Contar so `len(sugestoes)` deixava o laco
        # correr por TODOS os projetos da conta sempre que o candidato nao
        # respondesse "ok" — um dono malicioso podia apontar o padrao para
        # um dominio que nunca responde e usar cada projeto conhecido como
        # uma sondagem contra aquele alvo, virando o DERVS num refletor de
        # rede vestindo o IP do servidor. `medidos` conta toda chamada real
        # a `mede_site`, sucesso ou nao, e o laco para em MAX_SUGESTOES
        # medicoes — nunca mais que isso, seja qual for a resposta.
        sugestoes = []
        medidos = 0
        for nome in nomes:
            if medidos >= self.MAX_SUGESTOES:
                break
            url = coletar_github.url_do_padrao(padrao, nome)
            if not url or not coletar_github.url_segura(url):
                continue
            if not coletar_github.host_publico(
                    urllib.parse.urlsplit(url).hostname):
                continue
            medidos += 1
            medida = coletar_github.mede_site(url)
            if medida.get("ok") is True:
                sugestoes.append({"projeto": nome, "url": url})
        return self._json(200, {"sugestoes": sugestoes})

    # ------------------------------------------- a conta do GitHub (etapa C2)
    #
    # O `state` E ASSINADO COM O COFRE, e nao guardado em cookie. O caminho do
    # OAuth de ENTRAR usa cookie porque quem chega ali ainda nao tem sessao;
    # aqui quem pede a ida JA esta dentro, e o que o `state` precisa carregar e
    # DE QUEM e a instalacao — informacao que nao pode vir do navegador na
    # volta. Assinado, ele carrega o `usuario_id` e um prazo curto sem que o
    # servidor guarde estado nenhum entre as duas pontas.
    #
    # QUEM CANCELA NO MEIO NUNCA CHEGA AQUI, E ISSO E NORMAL. Nao e erro e nao
    # e alarme: e "nao deu para conferir", o quarto estado. O `state` tambem se
    # perde em variacoes legitimas do fluxo — a spec registra isso como risco
    # conhecido, e nao como garantia.
    MINUTOS_DA_INSTALACAO = 30
    ASSUNTO_DA_INSTALACAO = "instalar-github"

    # OS DOIS SAO ESTATICOS de proposito: eles nao leem nada do pedido, e
    # amarra-los a uma instancia so faria a prova depender de subir um servidor.
    # O que assina e a chave do cofre, e ela nao vem daqui.
    @staticmethod
    def _selo_da_instalacao(usuario_id: int, ate: int) -> str:
        """`usuario_id.ate.assinatura`. A assinatura cobre os dois primeiros."""
        corpo = "%d.%d" % (usuario_id, ate)
        marca = hmac.new(banco.chave_do_cofre(),
                         ("%s|%s" % (Hub.ASSUNTO_DA_INSTALACAO, corpo)).encode("utf-8"),
                         hashlib.sha256).hexdigest()
        return corpo + "." + marca

    @staticmethod
    def _dono_do_selo(selo: str, agora=None):
        """O `usuario_id` de dentro do selo, ou `None`. NUNCA levanta.

        Falha fechada em toda porta: selo torto, assinatura errada e prazo
        vencido saem todos como `None`, e nao como excecao para quem chamou
        tratar — a lei 3 deste repositorio.
        """
        partes = (selo or "").split(".")
        if len(partes) != 3:
            return None
        try:
            usuario_id, ate = int(partes[0]), int(partes[1])
        except ValueError:
            return None
        esperado = Hub._selo_da_instalacao(usuario_id, ate)
        # `compare_digest`: comparar com `==` vaza o tamanho do prefixo igual
        # pelo tempo, e e assim que uma assinatura se descobre byte a byte.
        if not hmac.compare_digest(esperado, selo or ""):
            return None
        if (time.time() if agora is None else agora) > ate:
            return None
        return usuario_id

    def _github_estado(self):
        """A instalacao DESTA conta, ou vazio. Nunca a de outra."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        contas = banco.instalacoes_da_conta(sessao["usuario_id"])
        for c in contas:
            c["gerenciar_url"] = self._url_de_gerenciar(c)
        return self._json(200, {
            "instalacao": banco.instalacao_do_github(sessao["usuario_id"]) or "",
            "instalacoes": contas,
            "da_para_instalar": bool(APP_DO_GITHUB),
            "lido_em": banco.agora()})

    @staticmethod
    def _url_de_gerenciar(conta: dict) -> str:
        """Onde, no GitHub, esta instalacao se configura (quais repositorios
        liberar). So monta com login valido; sem nome, vazio — a tela esconde o
        link em vez de apontar para um endereco chutado."""
        login = conta.get("conta_login") or ""
        numero = str(conta.get("installation_id") or "")
        if not (github_app.SO_LOGIN_DO_GITHUB.fullmatch(login)
                and github_app.SO_DIGITOS.fullmatch(numero)):
            return ""
        if conta.get("conta_tipo") == "Organization":
            return ("https://github.com/organizations/%s/settings/"
                    "installations/%s" % (login, numero))
        return "https://github.com/settings/installations/%s" % numero

    TETO_DE_PROCURAS = 10
    MAX_ORGS_CONFERIDAS = 10

    def _github_procurar(self):
        """"Procurar minhas contas": liga sozinho as instalacoes do App que ja
        existem no GitHub e sao DESTA conta, sem refazer o caminho de instalar.

        A prova de posse e a MESMA da volta normal (`_instalacao_e_dele`):
        conta pessoal so se o `account.id` for o do GitHub amarrado a esta
        sessao; organizacao so se esta conta for ADMIN dela. Como o App e
        publico, ha instalacao de estranhos na lista: as ja ligadas a alguem
        sao puladas, e so `MAX_ORGS_CONFERIDAS` organizacoes (as mais novas)
        geram pergunta ao GitHub por pedido. O caminho principal continua
        sendo o botao de conectar, que e deterministico."""
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        if not APP_DO_GITHUB:
            return self._json(404, {"erro": "nao existe"})
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="github_procurar",
                                           teto=self.TETO_DE_PROCURAS):
            return self._json(429, self.RECUSA)
        uid = sessao["usuario_id"]
        lista = github_app.listar_instalacoes(
            (os.environ.get("DERVS_GITHUB_APP_ID") or "").strip(),
            os.environ.get("DERVS_GITHUB_APP_KEY") or "")
        if lista is None:
            return self._json(200, {"ok": False, "ligadas": 0})
        ligadas = orgs = 0
        # A lista veio inteira e sem erro: o que esta ligado a esta conta e NAO
        # aparece nela morreu (App desinstalado e reinstalado gera numero novo).
        # Podar antes de ligar tambem libera vaga no teto de instalacoes.
        podadas = banco.podar_instalacoes_do_github(
            uid, [i["id"] for i in lista])
        for inst in sorted(lista, key=lambda i: i["id"], reverse=True):
            numero = str(inst["id"])
            conta = inst.get("account") or {}
            if inst.get("suspended_at"):
                continue
            if conta.get("type") == "Organization":
                if orgs >= self.MAX_ORGS_CONFERIDAS:
                    continue
            with contextlib.closing(banco.conectar()) as con:
                dono = con.execute("SELECT usuario_id FROM instalacao_github"
                                   " WHERE installation_id = ?",
                                   (numero,)).fetchone()
            if dono is not None:
                if dono["usuario_id"] == uid:
                    # Ja e minha: so completa o nome (linha migrada, sem nome).
                    # O nome vem do GitHub, nunca do corpo do pedido.
                    banco.guardar_instalacao_do_github(
                        uid, numero, conta_login=conta.get("login"),
                        conta_tipo=conta.get("type"))
                continue                 # ja e de alguem: nao e candidata
            if conta.get("type") == "Organization":
                orgs += 1
            if not self._instalacao_e_dele(uid, inst):
                continue
            try:
                banco.guardar_instalacao_do_github(
                    uid, numero, conta_login=conta.get("login"),
                    conta_tipo=conta.get("type"))
                ligadas += 1
            except ValueError:
                break                    # teto de instalacoes da conta
        return self._json(200, {"ok": True, "ligadas": ligadas,
                                "podadas": podadas})

    def _github_instalar(self):
        """Devolve o endereco da instalacao, com o selo dentro."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
        if not APP_DO_GITHUB:
            # Falha FECHADA: sem aplicativo registrado, a porta diz que nao
            # existe em vez de mandar o dono para um endereco que nao abre.
            return self._json(404, {"erro": "nao existe"})
        ate = int(time.time()) + self.MINUTOS_DA_INSTALACAO * 60
        selo = self._selo_da_instalacao(sessao["usuario_id"], ate)
        return self._json(200, {
            "url": "https://github.com/apps/%s/installations/new?state=%s" % (
                urllib.parse.quote(APP_DO_GITHUB, safe=""),
                urllib.parse.quote(selo, safe="")),
            "minutos": self.MINUTOS_DA_INSTALACAO})

    def _github_instalado(self):
        """A volta. Acesso `cortina` de proposito, e a decisao esta escrita.

        Quem chega aqui vem DO GITHUB, num salto de pagina que o nosso
        JavaScript nao fez — a mesma situacao de `/entrar/github/retorno`, que
        e `cortina` pelo mesmo motivo. E a autorizacao NAO sai da sessao: sai do
        selo assinado, que e o unico pedaco desta volta que o visitante nao
        consegue escrever.
        """
        pedido = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        selo = (pedido.get("state") or [""])[0]
        instalacao = (pedido.get("installation_id") or [""])[0]
        usuario_id = self._dono_do_selo(selo)

        # A ORDEM AQUI E A ETAPA INTEIRA. Nada e gravado antes das duas provas:
        # o selo diz de quem e, e o GitHub diz que a instalacao existe. Gravar
        # antes de conferir "porque a conferencia e lenta" e gravar um dado
        # forjado, e o desfazer nunca vem.
        confirmada = None
        if usuario_id is not None and instalacao:
            confirmada = github_app.confirmar_instalacao(
                (os.environ.get("DERVS_GITHUB_APP_ID") or "").strip(),
                os.environ.get("DERVS_GITHUB_APP_KEY") or "",
                instalacao)
        if usuario_id is not None and confirmada is not None \
                and self._instalacao_e_dele(usuario_id, confirmada):
            try:
                conta = confirmada.get("account") or {}
                banco.guardar_instalacao_do_github(
                    usuario_id, instalacao, conta_login=conta.get("login"),
                    conta_tipo=conta.get("type"))
            except ValueError:
                # O numero ja e de outra conta. Mesmo desfecho de todo o resto
                # que nao deu: nao gravou, e nao e um erro vermelho.
                return self._ir_para("/?github=nao-deu#/conectar")
            # A QUERY VAI ANTES DO `#`, e nao depois. `/#/conectar?github=x`
            # poe o parametro DENTRO do fragmento, e `location.search` sai
            # vazio — a tela nunca leria o recado. Achado clicando, nao lendo:
            # o 302 estava certo e a tela ficava muda.
            return self._ir_para("/?github=ligado#/conectar")
        # Cancelou no meio, o selo venceu, ou o GitHub nao confirmou: os tres
        # sao o MESMO estado para quem le a tela — nao deu para conferir. E
        # nenhum deles e um erro vermelho.
        return self._ir_para("/?github=nao-deu#/conectar")

    @staticmethod
    def _instalacao_e_dele(usuario_id: int, confirmada: dict) -> bool:
        """A instalacao confirmada e da conta do GitHub AMARRADA a esta sessao?

        PORQUE ISTO EXISTE, e e o achado das duas revisoes de 01/09/2026:
        `confirmar_instalacao` prova que a instalacao EXISTE e que e deste App.
        Nao prova que ela e SUA. O `installation_id` e publico e sequencial:
        sem esta conferencia, uma conta convidada pedia o proprio selo e
        chamava a volta com o numero de OUTRA pessoa, iterando ate acertar — e
        ficava amarrada a instalacao alheia. Hoje o estrago pararia no estado
        mostrado na tela; no dia em que `banco.instalacoes_do_github` ganhasse
        leitor, viraria token sobre os repositorios do outro.

        A PROVA E O `account.id`: o GitHub diz de quem e a instalacao, e nos
        sabemos a qual id do GitHub esta conta esta amarrada
        (`banco.ligar_github`, que guarda o id NUMERICO justamente porque login
        se troca).

        INSTALACAO EM ORGANIZACAO — a divida foi paga em 04/09/2026. Ali o
        `account.id` e o da organizacao, nunca o da pessoa, e o caminho de
        cima nunca confirma. `github_app.usuario_administra_a_organizacao`
        pergunta ao PROPRIO APP — ja instalado ali — se o dono da sessao
        ADMINISTRA ela (nao so "e membro": um membro raso podia pedir o
        proprio selo e amarrar a instalacao inteira a propria conta, achado
        da revisao de seguranca de 04/09/2026). Exige a permissao de
        organizacao "Members: Read-only" no App, e sem ela devolve `None`,
        que este metodo trata como "nao e dele": falha fechada, nunca uma
        porta que se abre sozinha por falta de configuracao.
        """
        conta = (confirmada or {}).get("account") or {}
        dono = str(conta.get("id") or "").strip()
        if not dono:
            return False
        with contextlib.closing(banco.conectar()) as con:
            linha = con.execute(
                "SELECT usuario_id FROM credencial"
                " WHERE tipo = 'github' AND identificador = ?"
                "   AND revogada_em IS NULL", (dono,)).fetchone()
        if linha is not None and linha["usuario_id"] == usuario_id:
            return True
        if conta.get("type") != "Organization":
            return False
        organizacao = str(conta.get("login") or "").strip()
        if not organizacao:
            return False
        with contextlib.closing(banco.conectar()) as con:
            minha = con.execute(
                "SELECT identificador FROM credencial"
                " WHERE tipo = 'github' AND usuario_id = ?"
                "   AND revogada_em IS NULL", (usuario_id,)).fetchone()
        if minha is None:
            return False
        # ADMIN, nao so membro: instalar um App exige ser admin da
        # organizacao, e aceitar qualquer membro provaria um direito menor
        # que o que a propria instalacao ja exigiu de quem a fez. Achado da
        # revisao de seguranca de 04/09/2026 -- ver a nota completa em
        # `github_app.usuario_administra_a_organizacao`.
        administra = github_app.usuario_administra_a_organizacao(
            (os.environ.get("DERVS_GITHUB_APP_ID") or "").strip(),
            os.environ.get("DERVS_GITHUB_APP_KEY") or "",
            str(confirmada.get("id") or ""), organizacao,
            minha["identificador"])
        return administra is True

    def _ir_para(self, destino: str):
        self.send_response(302)
        self.send_header("Location", destino)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _maquina_remover(self):
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            return self._json(403, {"erro": "origem nao permitida"})
        if not self._csrf_ok(sessao):
            return self._recusa_pagina_velha()
        corpo = self._corpo_json(teto=4096) or {}
        try:
            id_ = int(corpo.get("id"))
        except (TypeError, ValueError):
            return self._json(400, {"erro": "id invalido"})
        # `usuario_id` vai para dentro do UPDATE: o id da linha vem do
        # navegador, e um numero vizinho nao pode revogar a maquina do outro.
        if not banco.revogar_maquina(id_, sessao["usuario_id"]):
            return self._json(404, {"erro": "nao existe"})
        return self._json(200, {"ok": True})

    # ----------------------------------------------------- as duas do agente

    def _parear(self):
        """A maquina troca o codigo de seis digitos pelo token dela. UMA vez.

        O TETO DE CHUTE POR ORIGEM MORA AQUI, e nao no banco. Era um contador na
        tabela `pareamento`, e ele foi removido na etapa 8 porque contava o erro
        contra todos os pareamentos abertos de todas as contas: cinco pedidos de
        um estranho matavam o pareamento de todo mundo. Contando por origem, o
        estranho gasta o proprio teto e ninguem mais e afetado. Balcao proprio
        (`pareamento`) para nao trancar a cortina do dono junto — foi o que
        aconteceu com ele em 26/08/2026, por outro caminho.
        """
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="pareamento"):
            return self._json(429, self.RECUSA)
        corpo = self._corpo_json(teto=4096) or {}
        codigo = self._texto_do_corpo(corpo, "codigo", teto=64)
        nome = self._texto_do_corpo(corpo, "maquina", teto=120)
        token = banco.usar_pareamento(codigo, nome) if codigo else None
        if token is None:
            # A MESMA resposta para codigo errado, vencido e ja usado. Distinguir
            # diria a quem chuta que aquele numero existiu.
            return self._json(401, self.RECUSA)
        # A UNICA vez que este token existe fora da maquina que o pediu.
        return self._json(200, {"token": token})

    # 60 relatorios por janela de 15 min = um a cada 15 s. A coleta roda a
    # cada 60 s, entao sobra folga de quatro vezes para reinicio e ajuste.
    TETO_DE_RELATORIOS = 60

    def _relatorio(self):
        """A medicao de uma maquina entra aqui — e o carimbo de vida junto.

        NAO HA ROTA DE SINAL DE VIDA. O envio de dado E o sinal: com um "estou
        vivo" separado, uma maquina com a coleta travada continuaria reportando
        saude, e o painel ficaria verde exatamente quando parou de olhar.
        """
        maquina = getattr(self, "_maquina", None)
        if maquina is None:            # cinto, alem do guarda do despacho
            return self._json(401, {"erro": "token de maquina invalido"})
        # TETO NA INGESTAO. O teto de 300 e POR RELATORIO; nada limitava quantos
        # relatorios. Com um token vazado, um laco de POST enchia o disco e
        # deixava `montar_estado` carregando lixo a cada `/api/dados` de todo
        # mundo. O balde e por MAQUINA, e nao por origem: a maquina legitima tem
        # IP variavel e o token e o que a identifica.
        if not cortina.registrar_tentativa(
                "maquina:%d" % maquina["id"], time.time(),
                balcao="relatorio", teto=self.TETO_DE_RELATORIOS):
            return self._json(429, {"erro": "relatorios demais"})
        corpo = self._corpo_json(teto=self.TETO_DO_RELATORIO)
        if corpo is None:
            return self._json(400, {"erro": "corpo invalido"})
        projetos = corpo.get("projetos")
        if not isinstance(projetos, list):
            return self._json(400, {"erro": "projetos tem de ser lista"})
        avisos = corpo.get("avisos")
        contas = banco.receber_relatorio(
            maquina["id"], projetos, corpo.get("infra"),
            avisos if isinstance(avisos, list) else None)
        resposta = {"ok": True}
        resposta.update(contas)
        # O FIO DE VOLTA. Nenhuma conexao nova, nenhuma porta aberta, nenhuma
        # inversao de sentido: o agente continua sendo quem pergunta, e a
        # resposta que ele ja recebia passa a carregar a tarefa pendente.
        resposta["tarefa"] = self._tarefa_pendente(maquina)
        return self._json(200, resposta)

    # ------------------------------------------------- a tarefa e o desfecho

    def _varrer_mudas(self):
        """Tarefa `rodando` que parou de dar noticia vira `falha`.

        Nao e enfeite. Sem isto, um agente que morreu no meio deixa a tarefa
        `rodando` para sempre, e a tela mostra "trabalhando" para uma sessao
        que nao existe mais. Painel que mente e pior que painel vazio — e a
        lei 2 deste repositorio.
        """
        agora_iso = banco.agora()
        for muda in banco.tarefas_sem_noticia(tarefas.MINUTOS_SEM_NOTICIA,
                                              agora_iso):
            banco.marcar_fila(muda["id"], estado="falha",
                              terminado_em=agora_iso,
                              erro="o computador parou de dar noticia")
        self._varrer_vigilia()

    # No maximo uma varredura por minuto: `_varrer_mudas` roda a cada relatorio
    # de cada computador, e o motor de regras nao e de graca.
    _VIGILIA_CADA_S = 60
    _vigilia_varrida_em = 0.0
    TETO_DE_AVISOS = 5            # avisos NOVOS por varredura e por conta

    @staticmethod
    def _limpo(valor, teto: int) -> str:
        """Texto que e dado (nome de computador, de projeto): sem caractere de
        controle, cortado."""
        return "".join(c if c.isprintable() else " "
                       for c in str(valor))[:teto].strip()

    def _varrer_vigilia(self, agora_iso: str = None, forcar: bool = False):
        """Gera os avisos do painel para o DERVS-VOZ. NUNCA levanta e nunca
        executa comando: so grava recados `avisar` (nivel `leitura`).

        So avisa conta com VOZ de estado fresco, porque aviso que ninguem ouve
        nao se acumula. Um aviso por ocorrencia (`banco.avisar_uma_vez`), no
        maximo `TETO_DE_AVISOS` novos por conta por varredura.
        """
        agora_t = time.time()
        if not forcar and agora_t - Hub._vigilia_varrida_em < self._VIGILIA_CADA_S:
            return
        Hub._vigilia_varrida_em = agora_t
        try:
            agora_iso = agora_iso or banco.agora()
            for uid, destino in banco.voz_destinos_de_aviso(agora_iso).items():
                try:
                    self._avisos_da_conta(uid, destino, agora_iso)
                except Exception as erro:               # noqa: BLE001
                    print("[%s] aviso: varredura da vigilia falhou (%s)"
                          % (time.strftime("%H:%M:%S"), erro))
        except Exception as erro:                       # noqa: BLE001
            print("[%s] aviso: varredura da vigilia falhou (%s)"
                  % (time.strftime("%H:%M:%S"), erro))

    def _avisos_da_conta(self, uid: int, destino: int, agora_iso: str):
        novos = 0
        # (a) computador que calou: so os OUTROS, o do VOZ esta falando.
        for m in banco.maquinas_que_calaram(uid, agora_iso):
            if m["maquina_id"] == destino:
                continue
            if novos >= self.TETO_DE_AVISOS:
                return
            try:
                dia = datetime.fromisoformat(m["visto_em"]).date().isoformat()
            except ValueError:
                continue
            texto = ("O computador %s parou de medir há %d minutos. "
                     "Não sei como ele está."
                     % (self._limpo(m["nome"], 80), m["atraso_s"] // 60))
            if banco.avisar_uma_vez(
                    uid, destino, "calou:%d:%s" % (m["maquina_id"], dia),
                    "vigilia", texto, agora_iso):
                novos += 1
        # (b) pendencia de gravidade alta, como o motor ja calcula para a conta.
        con = banco.conectar()
        try:
            e = banco.montar_estado(con, usuario_id=uid)
            pend = regras.avaliar(e["projetos"], quota=e["quota"],
                                  silenciadas=banco.silenciadas(
                                      con, usuario_id=uid),
                                  arquivadas=banco.arquivadas(
                                      usuario_id=uid, con=con))
        finally:
            con.close()
        for p in pend:
            if p.get("gravidade") != "alta":
                continue
            if novos >= self.TETO_DE_AVISOS:
                return
            projeto = self._limpo(p.get("projeto") or "", 100)
            alvo = (projeto if self._ALVO_DE_RECADO.fullmatch(projeto)
                    and ".." not in projeto else "vigilia")
            # `[alerta:<id>]` no comeco: e por ele que o VOZ oferece "pedir
            # conserto" ao dono. O id vem de nome de projeto (dado de fora):
            # so entra se tiver caracteres seguros, senao o aviso vai sem ele.
            pid = str(p.get("id") or "")
            prefixo = ("[alerta:%s] " % pid
                       if self._ID_DE_ALERTA.fullmatch(pid) else "")
            texto = prefixo + self._limpo(
                ("%s: %s" % (projeto, p.get("texto") or "")) if projeto
                else (p.get("texto") or ""), min(300, 500 - len(prefixo)))
            if banco.avisar_uma_vez(uid, destino, "pend:%s" % p["id"],
                                    alvo, texto, agora_iso):
                novos += 1

    def _tarefa_pendente(self, maquina):
        """O que ESTA maquina deve fazer agora, ou `None`.

        Tres recusas em serie, e a ordem importa: sem maquina autorizada nao ha
        candidata; sem candidata nao ha o que avaliar; e so entao `pode_rodar`
        decide. Qualquer uma delas devolvendo vazio significa `None` — nunca
        uma tarefa "quase" entregue.
        """
        self._varrer_mudas()
        candidata = banco.tarefa_para_maquina(maquina["id"])
        if not candidata:
            return None
        janela = tarefas.janela_local_em_utc(tarefas.hoje_local())
        pode, _motivo = tarefas.pode_rodar(
            candidata, banco.gasto_entre(*janela), banco.agora(),
            banco.cores_das_regras(), maquina)
        if not pode:
            return None
        if not banco.entregar_tarefa(candidata["id"], maquina["id"]):
            # Outra maquina levou entre a leitura e a reserva. Nao e erro: e a
            # resposta certa para "uma sessao por vez".
            return None
        executor = candidata.get("executor") or "claude"
        gasto = banco.gasto_entre(*janela)
        # O TETO DA AUDITORIA E O DA SESSAO SAO CONTAS DIFERENTES (Etapa 5 da
        # Auditoria Profunda). auditoria.EXECUTOR e a MESMA constante usada em
        # `auditoria.py`, `banco.enfileirar` e `agente/executor.py` — um teste
        # de identidade cobra isso, nao igualdade de string.
        teto_usd = (tarefas.teto_da_auditoria(gasto)
                   if executor == auditoria.EXECUTOR
                   else tarefas.teto_da_sessao(gasto))
        return {
            "id": candidata["id"],
            "projeto": candidata.get("projeto") or "",
            "regra": candidata.get("regra") or "",
            "trilho": candidata.get("trilho") or "",
            "executor": executor,
            # `detalhe` (o pedido da tarefa `desenvolver`) vale mais que `erro`
            # (o que a falha da ultima tentativa escreveu). Sem esta linha a
            # sessao abre sem saber o que desenvolver.
            "detalhe": candidata.get("detalhe") or candidata.get("erro") or "",
            "cor": candidata.get("cor") or tarefas.VERMELHO,
            "teto_usd": teto_usd,
            "rodadas": int(candidata.get("rodadas") or 0),
            # OS TRES CAMPOS ABAIXO SAO A METADE QUE FALTAVA DA MESMA PERGUNTA.
            #
            # `pode_rodar` e chamado duas vezes de proposito: aqui, sobre a
            # LINHA DO BANCO, e do outro lado pelo agente, sobre ESTE
            # dicionario. Compartilhar a funcao nao basta — as duas chamadas
            # precisam dos mesmos FATOS. Ate 03/09/2026 nao estavam aqui, e o
            # efeito foi medido em producao: o dono aprovou uma auditoria
            # (`aprovado_em` gravado), o servidor entregou, e o agente recusou
            # com "esta tarefa esta vermelha e espera o seu clique". Como toda
            # regra nasce vermelha, NENHUMA tarefa aprovada rodava.
            #
            # `tentativas` VAI CRU, sem somar 1. Errei isso na primeira versao
            # e uma revisao de seguranca derrubou em 03/09/2026: `pode_rodar`
            # foi escrita sobre o significado "tentativas ja feitas ANTES
            # desta", e e assim que o servidor a avalia, sobre `candidata`,
            # lida antes de `entregar_tarefa` incrementar a coluna. Somar 1
            # aqui daria ao agente um significado diferente do mesmo nome, e
            # com MAX_TENTATIVAS = 2 a SEGUNDA tentativa morria: o servidor
            # entregava e o agente recusava com "ja foram 2 tentativas".
            # Trocar o sentido de um numero entre as duas pontas e a mesma
            # classe de defeito que este bloco existe para fechar.
            "aprovado_em": candidata.get("aprovado_em") or "",
            "tentativas": int(candidata.get("tentativas") or 0),
            "parada_pedida_em": candidata.get("parada_pedida_em") or "",
        }

    # O progresso chega a cada 5 s (`tarefas.SEGUNDOS_ENTRE_PROGRESSOS`), e o
    # balcao de `relatorio` tem teto de 60 por 15 min — um a cada 15 s. Misturar
    # os dois trancaria a maquina legitima com 429 e a tela do dono congelaria
    # sem explicacao. Balcao proprio, teto proprio: 240 por 15 min = um a cada
    # 3,75 s, com folga de quase o dobro sobre o intervalo de 5 s.
    TETO_DE_RESULTADOS = 240
    # O diff cabe aqui dentro. Um diff de uma sessao de 40 rodadas passa
    # folgado de 256 KiB; 2 MiB e o teto que impede o balde sem fundo.
    TETO_DO_RESULTADO = 2 * 1024 * 1024

    @staticmethod
    def _recorte(valor, teto: int) -> str:
        """Texto cortado no teto, com um aviso VISIVEL de que foi cortado.

        `_texto_do_corpo` devolve "" quando o campo passa do teto, e para o
        diff isso seria mentira por omissao: a tela mostraria "nada mudou" para
        uma sessao que mudou 3 MiB. Cortar e dizer que cortou e a resposta
        honesta.
        """
        if not isinstance(valor, str):
            return ""
        if len(valor) <= teto:
            return valor
        return valor[:teto] + (
            "\n[... o restante foi cortado: passou de %d KiB]"
            % (teto // 1024))

    def _resultado(self):
        """O agente conta o que esta acontecendo, ou como terminou.

        A RESPOSTA carrega `{"pare": ...}`. E assim, e so assim, que o botao
        Parar chega ao agente: sem conexao nova, sem porta aberta, e com a
        latencia declarada de ate ~10 s.
        """
        maquina = getattr(self, "_maquina", None)
        if maquina is None:            # cinto, alem do guarda do despacho
            return self._json(401, {"erro": "token de maquina invalido"})
        if not cortina.registrar_tentativa(
                "maquina:%d" % maquina["id"], time.time(),
                balcao="resultado", teto=self.TETO_DE_RESULTADOS):
            return self._json(429, {"erro": "noticias demais"})
        corpo = self._corpo_json(teto=self.TETO_DO_RESULTADO)
        if not isinstance(corpo, dict):
            return self._json(400, {"erro": "corpo invalido"})
        tarefa_id = self._texto_do_corpo(corpo, "id", teto=200)
        if not tarefa_id:
            return self._json(400, {"erro": "faltou o id da tarefa"})
        tipo = self._texto_do_corpo(corpo, "tipo", teto=20)

        if tipo == "desfecho":
            estado = self._texto_do_corpo(corpo, "estado", teto=20)
            rodadas_ok, rodadas = self._numero_do_corpo(corpo, "rodadas", int)
            custo_ok, custo_usd = self._numero_do_corpo(corpo, "custo_usd",
                                                         float)
            if not (rodadas_ok and custo_ok):
                return self._json(400, {"erro": "numero invalido"})
            ok = banco.registrar_desfecho(
                tarefa_id, maquina["id"], estado,
                ramo=self._texto_do_corpo(corpo, "ramo", teto=200),
                resumo=self._texto_do_corpo(corpo, "resumo", teto=4000),
                diff=self._recorte(corpo.get("diff"), 1024 * 1024),
                pr_url=self._texto_do_corpo(corpo, "pr_url", teto=500),
                rodadas=rodadas,
                custo_usd=custo_usd,
                erro=self._texto_do_corpo(corpo, "erro", teto=2000))
            if not ok:
                # A tarefa nao e desta maquina, ou o estado nao existe. A mesma
                # resposta para os dois: distinguir diria a quem tem um token
                # quais ids existem na conta do vizinho.
                return self._json(404, {"erro": "nao existe"})
            # A FRONTEIRA DA AUDITORIA (Etapa 5). So roda quando o desfecho
            # traz "achados" — a tarefa comum (env_drift, dependencia_insegura,
            # ...) nao tem essa chave, e este bloco fica calado para ela. O
            # texto QUE O AGENTE MANDOU e sempre uma STRING (o JSON cru que o
            # `claude` escreveu): `auditoria.validar` faz o parse, e ele tem
            # de rodar ANTES de qualquer gravacao — regra dura desta entrega.
            #
            # A checagem de `ok` ACIMA e o que garante que `tarefa_id` e desta
            # maquina antes de eu ler o projeto dela: ler `banco.tarefa` ANTES
            # dessa checagem vazaria o nome de um projeto de outra conta para
            # quem so tem o token errado.
            if "achados" in corpo:
                # O teto e' de `auditoria.TETO_DOS_ACHADOS`, e nao do corpo
                # inteiro (`TETO_DO_RESULTADO`, 2 MiB) — e' o proprio
                # `auditoria.py` que documenta "quem cobra o teto e'
                # servir.py, na fronteira". Sem esta linha, um texto acima do
                # teto so' seria pego se tambem quebrasse o parse do JSON —
                # padding em branco (JSON valido antes e depois de qualquer
                # token) bastava para passar batido.
                achados_brutos = self._texto_do_corpo(
                    corpo, "achados", teto=auditoria.TETO_DOS_ACHADOS)
                gravada = banco.tarefa(tarefa_id)
                projeto = (gravada or {}).get("projeto") or ""
                limpos, motivo = auditoria.validar(achados_brutos)
                if limpos is None:
                    # Saida invalida: grava a corrida `falha` com o motivo.
                    # NAO fecha os achados anteriores — o projeto continua
                    # com o carimbo da ultima auditoria boa (lei 2).
                    banco.gravar_auditoria(maquina["usuario_id"], projeto,
                                           "falha", [], tarefa_id=tarefa_id,
                                           motivo=motivo)
                else:
                    prontos = []
                    for item in limpos:
                        regra = auditoria.REGRAS.get(item.get("categoria"), "")
                        pronto = dict(item)
                        pronto["regra"] = regra
                        pronto["id"] = auditoria.id_do_achado(regra, projeto,
                                                              item)
                        prontos.append(pronto)
                    banco.gravar_auditoria(
                        maquina["usuario_id"], projeto, "ok", prontos,
                        tarefa_id=tarefa_id,
                        custo_usd=custo_usd or 0.0,
                        rodadas=rodadas or 0)
            extra = {}
            if "provas" in corpo:
                extra = self._gravar_provas_do_resultado(
                    corpo, tarefa_id, maquina)
            return self._json(200, dict({"ok": True, "pare": False}, **extra))

        if tipo != "progresso":
            return self._json(400, {"erro": "tipo desconhecido"})

        rodadas_ok, rodadas = self._numero_do_corpo(corpo, "rodadas", int)
        custo_ok, custo_usd = self._numero_do_corpo(corpo, "custo_usd", float)
        if not (rodadas_ok and custo_ok):
            return self._json(400, {"erro": "numero invalido"})
        linhas = []
        cru = corpo.get("linhas")
        if isinstance(cru, list):
            # Teto de 200 linhas por pedido. O agente fala a cada 5 s; uma
            # sessao que cospe mais que isso em cinco segundos esta em laco, e
            # o teto e o que impede o laco de virar disco cheio.
            for par in cru[:200]:
                if isinstance(par, (list, tuple)) and len(par) == 2:
                    linhas.append((par[0], str(par[1])[:2000]))
        pare = banco.registrar_progresso(
            tarefa_id, maquina["id"],
            frase=self._texto_do_corpo(corpo, "frase", teto=500),
            linhas=linhas, rodadas=rodadas,
            custo_usd=custo_usd)
        return self._json(200, {"ok": True, "pare": bool(pare)})

    _SHA_DE_PROVA = re.compile(r"[0-9a-f]{0,40}")

    def _gravar_provas_do_resultado(self, corpo, tarefa_id, maquina) -> dict:
        """O fio das provas: o agente conta o que cada comando respondeu.

        So vale para tarefa de regra `provar`; o PROJETO vem da tarefa e o DONO
        da maquina autenticada, nunca do corpo. Cada item e validado pelo TIPO
        (`ok` so `True`/`False`/`None`: o texto `"true"` nao grava) e so grava
        o criterio que existe na documentacao DESTA conta COM A MESMA prova.
        O resto e descartado, e a contagem volta no resumo.
        """
        gravada = banco.tarefa(tarefa_id)
        if not gravada or gravada.get("regra") != tarefas.PROVAR:
            return {"provas_gravadas": 0, "provas_descartadas": 0}
        projeto = gravada.get("projeto") or ""
        itens = corpo.get("provas")
        # Teto DERIVADO do que a documentacao pode ter, nunca digitado.
        teto = documentos.MAX_DOCUMENTOS * documentos.MAX_CRITERIOS
        sha = corpo.get("sha", "")
        if (not isinstance(itens, list) or len(itens) > teto
                or not isinstance(sha, str)
                or not self._SHA_DE_PROVA.fullmatch(sha)):
            return {"provas_gravadas": 0, "provas_descartadas": 0,
                    "erro_das_provas": "provas invalidas"}
        achados = self._criterios_da_conta(maquina["usuario_id"], projeto)
        aceitas = (documentos.provas_aceitas(achados[0][1], projeto)
                   if achados else {})
        a_gravar, descartados = {}, 0
        for it in itens:
            if not isinstance(it, dict):
                descartados += 1
                continue
            prova, ok = it.get("prova"), it.get("ok")
            cids, motivo = it.get("criterios"), it.get("motivo", "")
            # `ok` pelo TIPO: `1 == True` e `"true"` nao pode gravar nada.
            if (not self._texto_gravavel(prova)
                    or not (ok is True or ok is False or ok is None)
                    or not isinstance(cids, list) or len(cids) > teto
                    or not self._texto_gravavel(motivo) or len(motivo) > 300
                    or not all(self._texto_gravavel(c) and len(c) <= 64
                               for c in cids)):
                descartados += 1
                continue
            validos = set(aceitas.get(prova.strip(), []))
            for cid in cids:
                if cid in validos:
                    a_gravar[cid] = {"criterio_id": cid, "prova": prova.strip(),
                                     "ok": ok, "motivo": motivo}
                else:
                    descartados += 1
        if a_gravar:
            banco.gravar_provas(maquina["usuario_id"], projeto,
                                list(a_gravar.values()), tarefa_id, sha)
        return {"provas_gravadas": len(a_gravar),
                "provas_descartadas": descartados}

    # ------------------------------------------------- as quatro rotas do dono

    def _tarefas(self):
        """A lista que a tela desenha. Sem o diff cru: ele e pedido a parte."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        self._varrer_mudas()
        consulta = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query)
        pedido = (consulta.get("id") or [""])[0][:200]
        if pedido:
            uma = banco.tarefa(pedido, usuario_id=sessao["usuario_id"])
            if uma is None:
                return self._json(404, {"erro": "nao existe"})
            uma["frases_do_diff"] = tarefas.frases_do_diff(uma.get("diff") or "")
            return self._json(200, {"tarefa": uma,
                                    "medido_em": banco.agora()})
        return self._json(200, {
            "tarefas": banco.tarefas_do_painel(sessao["usuario_id"]),
            "cores": banco.cores_das_regras(),
            "nunca_verde": sorted(tarefas.NUNCA_VERDE | tarefas.SEMPRE_VERMELHA),
            "medido_em": banco.agora()})

    # ------------------------------------------------------ o fluxo ao vivo
    #
    # O `setInterval(..., 60000)` da tela nao sustenta "o dono ve o trabalho
    # acontecendo": um minuto de silencio numa sessao de dez minutos e uma tela
    # que parece travada. Isto e um `text/event-stream` — a primeira resposta
    # deste servidor que nao e uma string inteira.
    #
    # Quatro numeros, e nenhum deles e arbitrario:
    SEGUNDOS_ENTRE_LEITURAS = 1.0   # de quanto em quanto o banco e relido
    SEGUNDOS_ENTRE_PINGS = 20       # o proxy_read_timeout do nginx e 60 s;
                                    # silencio de um minuto derruba a conexao
    SEGUNDOS_DE_VIDA = 300          # o EventSource reconecta sozinho, e conexao
                                    # eterna em ThreadingHTTPServer e thread
                                    # eterna
    FLUXOS_POR_SESSAO = 4           # dez abas abertas seriam dez threads
    FLUXOS_NO_TOTAL = 16            # paradas, e o publico deste servidor sao
                                    # duas pessoas

    # Contador de conexoes vivas. Mora no modulo, e nao na instancia: cada
    # pedido cria um `Hub` novo.
    _fluxos = {}
    _tranca_dos_fluxos = threading.Lock()

    @classmethod
    def _entrar_no_fluxo(cls, chave) -> bool:
        with cls._tranca_dos_fluxos:
            if sum(cls._fluxos.values()) >= cls.FLUXOS_NO_TOTAL:
                return False
            if cls._fluxos.get(chave, 0) >= cls.FLUXOS_POR_SESSAO:
                return False
            cls._fluxos[chave] = cls._fluxos.get(chave, 0) + 1
            return True

    @classmethod
    def _sair_do_fluxo(cls, chave) -> None:
        with cls._tranca_dos_fluxos:
            restam = cls._fluxos.get(chave, 1) - 1
            if restam > 0:
                cls._fluxos[chave] = restam
            else:
                cls._fluxos.pop(chave, None)

    def _eventos(self):
        """O que esta acontecendo agora, empurrado enquanto acontece.

        `BrokenPipeError` e `ConnectionAbortedError` sao tratados AQUI DENTRO.
        Sem isso, cada aba fechada cai no `except Exception` de `_despachar` e
        cospe um traceback no log — e log cheio de traceback normal e log que
        ninguem le no dia do traceback anormal.
        """
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        consulta = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        alvo = (consulta.get("id") or [""])[0][:200]
        try:
            desde = int((consulta.get("desde") or ["0"])[0])
        except (TypeError, ValueError):
            desde = 0

        chave = sessao["usuario_id"]
        if not self._entrar_no_fluxo(chave):
            return self._json(503, {"erro": "janelas demais abertas ao vivo"})
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            # SEM ESTA LINHA O FLUXO NAO PASSA PELO NGINX. O bloco de
            # `location` tambem desliga o buffer, mas as duas defesas nao se
            # dispensam: a de la vale para este nginx, esta vale para qualquer
            # proxy no caminho.
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Connection", "close")
            # Nenhum Content-Length: o tamanho nao existe ainda.
            self.end_headers()
            self._empurrar(alvo, desde, chave)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError,
                OSError):
            pass                        # a aba fechou. Nao e erro.
        finally:
            self._sair_do_fluxo(chave)

    def _empurrar(self, alvo: str, desde: int, usuario_id: int) -> None:
        """O laco. Le o banco, manda o que ha de novo, respira.

        `usuario_id` entra em CADA leitura de `alvo`, nao so na abertura:
        sem ele, uma sessao passando o id de outra conta acompanhava ao vivo
        as linhas, o custo e o diff de uma tarefa alheia — mesma familia do
        achado da auditoria de 03/09/2026. "Nao existe" e "nao e sua" chegam
        ao mesmo lugar: `banco.tarefa` devolve `None` para os dois, e a busca
        de linhas so roda quando a tarefa E confirmada desta conta.
        """
        fim = time.time() + self.SEGUNDOS_DE_VIDA
        ultimo_ping = time.time()
        # `object()` e nao `None`: `None` e um estado POSSIVEL (tarefa que nao
        # existe), e comecar igual a ele faria o primeiro evento nunca sair.
        # Quem abrisse a tela numa tarefa apagada ficaria sem saber se estava
        # carregando ou se nao havia nada — e "nao sei" e "vazio" sao estados
        # diferentes.
        ultimo_estado = object()
        while time.time() < fim:
            if alvo:
                atual = banco.tarefa(alvo, usuario_id=usuario_id)
                if atual is not None:
                    for linha in banco.linhas_da_tarefa(alvo, desde):
                        desde = max(desde, int(linha["n"]))
                        self._evento("linha", {"n": linha["n"],
                                               "texto": linha["texto"],
                                               "quando": linha["quando"]},
                                     ident=linha["n"])
                        ultimo_ping = time.time()
                marca = None if atual is None else (
                    atual["estado"], atual["frase"], atual["rodadas"])
                if marca != ultimo_estado:
                    ultimo_estado = marca
                    self._evento("estado", {
                        "id": alvo,
                        "estado": None if atual is None else atual["estado"],
                        "frase": None if atual is None else atual["frase"],
                        "rodadas": None if atual is None else atual["rodadas"],
                        "parada_pedida": bool(
                            atual and atual["parada_pedida_em"])})
                    ultimo_ping = time.time()
            if time.time() - ultimo_ping >= self.SEGUNDOS_ENTRE_PINGS:
                # Comentario de SSE: nao vira evento na tela, so mantem a
                # conexao viva. O cliente ignora sozinho.
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
                ultimo_ping = time.time()
            else:
                # A SONDA, e ela nao e enfeite: e o que faz o servidor PERCEBER
                # que a aba fechou. Sem ela, a unica escrita do laco era o ping
                # de 20 em 20 s, e ate la a vaga do dono continuava ocupada por
                # ninguem — com quatro vagas por sessao, quatro recargas de
                # pagina trancavam o dono fora do proprio painel por cinco
                # minutos. Custa tres bytes por segundo, e o publico deste
                # servidor sao duas pessoas.
                self.wfile.write(b":\n\n")
                self.wfile.flush()
            time.sleep(self.SEGUNDOS_ENTRE_LEITURAS)
        # Fim de vida anunciado. O EventSource reconecta sozinho; o aviso
        # existe para a tela nao pintar isso como queda.
        self._evento("fim", {"motivo": "a conexao renova sozinha a cada %s"
                                       % self._quanto_tempo(
                                           self.SEGUNDOS_DE_VIDA)})

    @staticmethod
    def _quanto_tempo(segundos: int) -> str:
        """300 -> "5 minutos"; 3 -> "3 segundos". Nunca "0 minutos"."""
        if segundos < 60:
            return "%d segundo%s" % (segundos, "" if segundos == 1 else "s")
        minutos = segundos // 60
        return "%d minuto%s" % (minutos, "" if minutos == 1 else "s")

    def _evento(self, nome: str, dados: dict, ident=None) -> None:
        pedaco = ""
        if ident is not None:
            pedaco += "id: %s\n" % ident
        pedaco += "event: %s\n" % nome
        pedaco += "data: %s\n\n" % json.dumps(dados, ensure_ascii=False)
        self.wfile.write(pedaco.encode("utf-8"))
        self.wfile.flush()

    def _consumo(self):
        """Quanto o painel consumiu na janela. Sete dias por padrao.

        O dono decidiu, em 28/08/2026, nao ter freio de horario e observar sete
        dias antes de limitar. Sem contador, "observar" e uma intencao — esta
        rota e o que torna a decisao dele executavel.
        """
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        consulta = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        try:
            dias = int((consulta.get("dias") or [""])[0])
        except (TypeError, ValueError):
            dias = banco.DIAS_DE_CONSUMO
        # Teto de 90 dias: a leitura varre a `fila` inteira, e uma janela de
        # dez anos pedida pela barra de endereco seria uma varredura completa a
        # cada recarga.
        dias = max(1, min(dias, 90))
        fora = banco.consumo(dias=dias)
        # O custo em reais vem JUNTO e ROTULADO. Com assinatura, o recurso
        # escasso e cota; o dinheiro e referencia, e a tela precisa do texto
        # pronto para nao inventar a conversao dela.
        fora["custo_em_reais"] = tarefas.em_reais(fora["total"]["custo_usd"])
        fora["o_que_e_escasso"] = "sessoes e rodadas"
        return self._json(200, fora)

    def _tarefa_aprovar(self):
        """O clique do dono numa tarefa vermelha."""
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        alvo = self._texto_do_corpo(corpo, "id", teto=200)
        if not alvo:
            return self._json(400, {"erro": "faltou o id da tarefa"})
        if not banco.aprovar_tarefa(alvo, sessao["usuario_id"]):
            return self._json(409, {"erro": "essa tarefa nao espera aprovacao"})
        return self._json(200, {"ok": True})

    def _tarefa_parar(self):
        """O freio. Escreve o pedido; quem para e o agente, no proximo alo.

        A resposta diz `pedido`, e nao `parado`. Afirmar que parou antes de o
        agente confirmar seria exatamente o numero errado com cara de certo que
        a lei 2 proibe — `parar()` devolve False quando nao confirmou a morte.
        """
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        alvo = self._texto_do_corpo(corpo, "id", teto=200)
        if not alvo:
            return self._json(400, {"erro": "faltou o id da tarefa"})
        if not banco.pedir_parada(alvo, sessao["usuario_id"]):
            return self._json(409, {"erro": "essa tarefa ja nao esta rodando"})
        return self._json(200, {"ok": True, "pedido": True,
                                "segundos": tarefas.SEGUNDOS_ENTRE_PROGRESSOS})

    def _tarefa_cor(self):
        """O dono repinta uma regra. `publicar` e recusada, e a tela mostra."""
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        regra = self._texto_do_corpo(corpo, "regra", teto=100)
        cor = self._texto_do_corpo(corpo, "cor", teto=20)
        if not regra:
            return self._json(400, {"erro": "faltou a regra"})
        if not banco.repintar_regra(regra, cor, sessao["usuario_id"]):
            if regra in tarefas.NUNCA_VERDE:
                return self._json(409, {
                    "erro": "a regra \"%s\" nunca anda sozinha, e isso nao se "
                            "repinta" % regra})
            if regra in tarefas.SEMPRE_VERMELHA:
                return self._json(409, {
                    "erro": "a regra \"%s\" sempre espera o seu clique, e "
                            "isso nao se repinta" % regra})
            return self._json(400, {"erro": "cor invalida"})
        return self._json(200, {"ok": True, "cor": cor})

    # ---------------------------------------------------- a auditoria (Etapa 5)
    #
    # Acesso `dado`, e nao `cortina`: um achado carrega caminho de arquivo,
    # numero de linha e um trecho do codigo-fonte privado do dono — o dado
    # mais sensivel que este painel ja guardou. `assets/painel.js`, que
    # desenha a tela, ja exige sessao por caminho exato (`ESTATICOS_COM_SESSAO`
    # mais abaixo); servir os achados com acesso menor seria abrir a porta ao
    # lado da fechadura.

    def _auditoria(self):
        """A camada de auditoria de cada projeto desta conta.

        Projeto sem corrida entra com `"auditoria": None` — nunca `{}` nem
        `{"achados": []}`, que teriam a mesma cara de "auditei e nao achei
        nada". `banco.montar_estado` ja faz essa distincao (lei 2); esta rota
        so recorta o que a tela de auditoria precisa do estado inteiro.
        """
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        con = banco.conectar()
        try:
            estado = banco.montar_estado(con, usuario_id=sessao["usuario_id"])
        finally:
            con.close()
        projetos = []
        for p in estado["projetos"]:
            camada = p.get("auditoria")
            if camada:
                # A tela (`painel.js`, `pintarAuditoria`) le `corrida` e
                # `achados`. Sem a chave `corrida` ela dizia "nunca foi
                # auditado" para uma auditoria gravada com achados.
                camada = dict(camada)
                camada["corrida"] = {
                    "estado": camada.get("estado"),
                    "motivo": camada.get("motivo") or "",
                    "medido_em": (p.get("medido_em") or {}).get("auditoria"),
                    "arquivos_n": camada.get("arquivos_n") or 0,
                    "custo_usd": camada.get("custo_usd") or 0,
                    "achados_n": camada.get("achados_n") or 0,
                    "rodadas": camada.get("rodadas") or 0,
                }
            projetos.append({"projeto": p.get("nome") or "", "auditoria": camada})
        return self._json(200, {"projetos": projetos})

    # Auditoria e cara: um pedido em laco esvaziaria o teto do dia sozinho.
    # Balcao PROPRIO (`auditoria`), reusando `cortina.registrar_tentativa` —
    # o mesmo molde de `_maquina_parear` (:1438), `_conectador` (:1494 antes
    # desta etapa), `_relatorio` (:1851) e `_resultado` (:1961). Dez por
    # janela de 15 min e folga larga para pedir de verdade e curta o
    # suficiente para nao virar torneira aberta na fila.
    TETO_DE_AUDITORIAS = 10

    def _auditoria_pedir(self):
        """O dono pede uma auditoria avulsa deste projeto.

        So ESCREVE na fila com `banco.enfileirar`, no molde da regra
        `auditoria_vencida`: o `trilho` e `"claude"` (quem escolhe o braco
        pelo `executor` e `agente/enviar.fazer_a_tarefa`) e o `executor` e
        `auditoria.EXECUTOR` — a MESMA constante usada em `auditoria.py` e
        `banco.enfileirar`, nunca a string escrita a mao duas vezes.

        Duas travas antes de escrever, achadas na revisao de seguranca de
        02/09/2026: o projeto tem de ser DESTA conta (`banco.montar_estado`),
        e nao pode estar em `tarefas.PROJETOS_BLOQUEADOS` — a mesma lista que
        `fila.trilho_de` aplica, comparada em minusculas para nao se escapar
        com maiuscula. "Nao existe" e "nao e seu" devolvem a MESMA resposta:
        distinguir diria a quem tem sessao quais projetos existem na conta do
        vizinho.
        """
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="auditoria",
                                           teto=self.TETO_DE_AUDITORIAS):
            return self._json(429, self.RECUSA)
        projeto = self._texto_do_corpo(corpo, "projeto", teto=200)
        if not projeto:
            return self._json(400, {"erro": "faltou o projeto"})
        con = banco.conectar()
        try:
            estado = banco.montar_estado(con, usuario_id=sessao["usuario_id"])
        finally:
            con.close()
        nomes_da_conta = {(p.get("nome") or "").lower()
                          for p in estado["projetos"]}
        if projeto.lower() not in nomes_da_conta:
            return self._json(404, {"erro": "projeto nao encontrado"})
        if tarefas.projeto_bloqueado(projeto):
            return self._json(403, {"erro": "projeto bloqueado"})
        # O DONO entra NO ID, e nao so na coluna. `fila.id` continua sendo
        # TEXT PRIMARY KEY global (nao (usuario_id, id), como `achado`), e
        # sem o dono aqui duas contas com projeto de mesmo nome colidiam no
        # MESMO id: `INSERT OR IGNORE` da segunda nao inseria nada,
        # `entraram` vinha 0, e a rota respondia 200 "pedido" para um pedido
        # que nunca entrou na fila DAQUELA conta — sucesso relatado sem
        # efeito, a mesma classe de mentira que a lei 2 proibe. Achado da
        # revisao de Python de 04/09/2026. `.split(":")[0]` (quem le a regra
        # a partir do id, em `execucao.py`) continua valendo: só o PRIMEIRO
        # pedaço importa.
        entraram = banco.enfileirar([{
            "id": "%s:%s:%s" % (auditoria.REGRA_DE_VENCIMENTO,
                                sessao["usuario_id"], projeto),
            "usuario_id": sessao["usuario_id"],
            "projeto": projeto,
            "regra": auditoria.REGRA_DE_VENCIMENTO,
            "gravidade": "baixa",
            "trilho": "claude",
            "executor": auditoria.EXECUTOR,
        }])
        return self._json(200, {"ok": True, "pedido": bool(entraram)})

    # Consertar gasta dinheiro e escreve em repositorio: balcao PROPRIO, como o
    # da auditoria — nunca emprestado de outra rota.
    TETO_DE_CONSERTOS = 10

    def _aviso_do_conserto(self, usuario_id, coisa="conserto"):
        """Por que o conserto entrou na fila mas NAO roda agora, ou `None`.

        Texto para leigo. Ordem: sem computador, computador sem autorizacao,
        teto do dia. `coisa` e a palavra do trabalho ("conserto", ou
        "desenvolvimento" para o botao Desenvolver isto).
        """
        maquinas = banco.maquinas_do_usuario(usuario_id)
        if not maquinas:
            return ("Nenhum computador está conectado à sua conta. Conecte um "
                    "em Conectar para o %s poder rodar." % coisa)
        if not any(int(m.get("executa") or 0) for m in maquinas):
            return ("Seus computadores ainda não foram autorizados a consertar. "
                    "Em Conectar, ligue \"Deixar consertar aqui\".")
        janela = tarefas.janela_local_em_utc(tarefas.hoje_local())
        if not tarefas.cabe_no_teto(banco.gasto_entre(*janela)):
            return ("O limite de gasto de hoje já foi alcançado. O %s "
                    "fica na fila e só roda quando o limite renovar." % coisa)
        return None

    @staticmethod
    def _aviso_do_pedido_repetido(linha, coisa="conserto"):
        """O que dizer ao dono quando o conserto JA existe, segundo o estado real.

        `coisa` e a palavra do trabalho, como em `_aviso_do_conserto`.
        """
        estado = (linha or {}).get("estado") or ""
        if estado in ("esperando", "aguardando_aprovacao"):
            return "Este %s já está na fila. Aprove em Consertar." % coisa
        if estado == "rodando":
            return ("Este %s está sendo feito agora. Acompanhe em Consertar."
                    % coisa)
        if estado == "ok":
            return ("Este %s já foi feito. Se nada mudou, o pedido "
                    "de alteração pode estar esperando a sua revisão no GitHub "
                    "— veja em Consertar." % coisa)
        if estado == "falha":
            if int(linha.get("tentativas") or 0) >= tarefas.MAX_TENTATIVAS:
                return ("Este %s já foi tentado %d vezes e não deu certo. "
                        "Veja o motivo em Consertar."
                        % (coisa, tarefas.MAX_TENTATIVAS))
            return ("A última tentativa deste %s falhou. A fila tenta de "
                    "novo amanhã, dentro do limite de gasto." % coisa)
        return "Este %s já foi pedido. Veja o estado em Consertar." % coisa

    def _consertar_pedir(self):
        """O botao "Consertar com IA": enfileira o conserto de UMA pendencia.

        O pedido traz so o id. Regra, projeto e dono vem do estado DA CONTA de
        quem pediu (`_estado`), nunca do corpo: o navegador nao escolhe o que
        vai para a fila. "Nao existe" e "nao e seu" dao a MESMA resposta (404).
        """
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="consertar",
                                           teto=self.TETO_DE_CONSERTOS):
            return self._json(429, self.RECUSA)
        pid = self._id_de_pendencia(corpo)
        if pid is None:
            return
        status, resposta = self._enfileirar_conserto(sessao["usuario_id"], pid)
        return self._json(status, resposta)

    def _enfileirar_conserto(self, uid, pid):
        """O miolo do conserto, UM so para a tela e para o DERVS-VOZ.

        Devolve `(status, corpo)`. Quem chama decide de quem e o `uid` (da
        sessao, na tela; do dono da maquina, na ponte) e nunca do corpo.
        """
        alvo = next((x for x in self._estado(uid)["pendencias"]
                     if x.get("id") == pid), None)
        if alvo is None:
            return 404, {"erro": "alerta nao encontrado"}
        regra = alvo.get("regra") or ""
        projeto = alvo.get("projeto") or ""
        if regra not in tarefas.REGRAS_CONSERTAVEIS_PELA_TELA:
            return 403, {"erro": "esta regra nao e consertada por aqui"}
        if tarefas.projeto_bloqueado(projeto):
            return 403, {"erro": "projeto bloqueado"}
        # O dono entra NO ID (fila.id e TEXT PRIMARY KEY global): sem ele, duas
        # contas com projeto de mesmo nome colidem e a segunda "pede" sem entrar.
        id_fila = "%s:%s:%s" % (regra, uid, pid)
        entrou = banco.enfileirar([{
            "id": id_fila,
            "usuario_id": uid,
            "projeto": projeto,
            "regra": regra,
            "gravidade": alvo.get("gravidade") or "media",
            "risco": alvo.get("risco") or 0,
            "trilho": "claude",
            "executor": "claude",
        }])
        if entrou:
            aviso = self._aviso_do_conserto(uid)
        else:
            # `INSERT OR IGNORE` devolve 0 para uma linha que ja existe em
            # QUALQUER estado. Dizer "ja estava na fila" para um conserto que
            # falhou ou terminou seria mentira: a tela le a frase daqui.
            aviso = self._aviso_do_pedido_repetido(banco.tarefa(id_fila, uid))
        return 200, {"ok": True, "pedido": bool(entrou), "tarefa": id_fila,
                     "aviso": aviso}

    # ------------------------------------ o progresso por documentacao (Fatia 3)
    #
    # O agente LE os briefings e sobe os criterios crus (`documentacao`); o
    # servidor recalcula a conta a cada pedido (`documentos.progresso`) e nunca
    # aceita percentual pronto. Nenhuma prova roda nesta entrega: todo criterio
    # sai "nao verificado". Duas rotas, ambas `dado` e ambas recortadas ao
    # estado DA CONTA de quem pediu.

    def _criterios_da_conta(self, uid, projeto=None):
        """`[(nome, documentacao, medido_em)]` dos projetos DESTA conta.

        Com `projeto`, so aquele (lista vazia se nao existir OU nao for seu —
        as duas respostas sao a mesma). O estado e o CRU (`montar_estado`): e
        de la que sai a chave `documentacao`, que `_dados` poda depois.
        """
        con = banco.conectar()
        try:
            e = banco.montar_estado(con, usuario_id=uid)
        finally:
            con.close()
        return [(p.get("nome") or "", p.get("documentacao"),
                 (p.get("medido_em") or {}).get("local"))
                for p in e["projetos"]
                if projeto is None or p.get("nome") == projeto]

    @staticmethod
    def _bloqueio_de_desenvolvimento(nome):
        """"" se o DERVS pode desenvolver neste projeto, senao o motivo."""
        return "" if tarefas.projeto_pode_desenvolver(nome) else "projeto bloqueado"

    def _progresso(self):
        """A conta e os criterios de UM projeto da conta, para a tela abrir."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        consulta = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query)
        nome = (consulta.get("projeto") or [""])[0][:200]
        achados = self._criterios_da_conta(sessao["usuario_id"], nome) \
            if nome else []
        if not achados:
            return self._json(404, {"erro": "projeto nao encontrado"})
        nome, doc, medido_em = achados[0]
        veredito, provado_em = self._veredito_das_provas(
            sessao["usuario_id"], nome, doc)
        pr = documentos.progresso(doc, nome, medido_em, provas=veredito,
                                  provado_em=provado_em)
        return self._json(200, {
            "projeto": nome, "progresso": pr,
            "documentos": documentos.detalhar(
                doc, nome, provas=veredito,
                bloqueio=self._bloqueio_de_desenvolvimento(nome)),
            "provavel": bool(documentos.provas_aceitas(doc, nome))
            and tarefas.projeto_pode_desenvolver(nome),
            "medido_em": pr["medido_em"]})

    @staticmethod
    def _veredito_das_provas(uid, nome, doc):
        """`({criterio: bool}, provado_em)` das provas gravadas DESTA conta, ja
        conferidas contra a prova ATUAL do criterio (`provas_validas`)."""
        return documentos.provas_validas(
            doc, nome,
            _linhas_de_prova(banco.provas_da_conta(uid, nome).get(nome)))

    # Desenvolver gasta dinheiro e escreve em repositorio: balcao PROPRIO, como
    # o do conserto e o da auditoria — nunca emprestado de outra rota.
    TETO_DE_DESENVOLVIMENTOS = 10

    def _desenvolver_pedir(self):
        """O botao "Desenvolver isto": enfileira UM criterio documentado.

        O pedido traz so o id do criterio. Projeto, documento, texto e dono vem
        do estado DA CONTA de quem pediu, nunca do corpo; a regra da tarefa e
        sempre `desenvolver` (vermelha, espera o "Pode fazer"). "Nao existe" e
        "nao e seu" dao a MESMA resposta (404). Quem decide se o criterio pode
        ser desenvolvido e `documentos.detalhar` — a MESMA funcao que diz a
        tela se o botao aparece, para o botao nunca oferecer o que aqui se
        recusa.
        """
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="desenvolver",
                                           teto=self.TETO_DE_DESENVOLVIMENTOS):
            return self._json(429, self.RECUSA)
        cid = corpo.get("criterio")
        if not cid or not isinstance(cid, str):
            return self._json(400, {"erro": "faltou o id do criterio"})
        if len(cid) > 64:
            return self._json(400, {"erro": "id longo demais"})
        uid = sessao["usuario_id"]
        achado = projeto = None
        for nome, doc, _ in self._criterios_da_conta(uid):
            # Com as provas: criterio COMPROVADO deixa de ser desenvolvivel.
            achado = documentos.achar_criterio(
                doc, nome, cid,
                provas=self._veredito_das_provas(uid, nome, doc)[0],
                bloqueio=self._bloqueio_de_desenvolvimento(nome))
            if achado:
                projeto = nome
                break
        if achado is None:
            return self._json(404, {"erro": "criterio nao encontrado"})
        documento, c = achado
        if c["motivo"]:
            return self._json(403, {"erro": c["motivo"]})
        # O dono entra NO ID (fila.id e TEXT PRIMARY KEY global): sem ele, duas
        # contas com projeto de mesmo nome colidem e a segunda "pede" sem entrar.
        id_fila = "desenvolver:%s:%s" % (uid, cid)
        # A marca da prova NAO pode vir do texto do criterio (dado de fora): o
        # banco ancora a coluna `prova` na primeira ocorrencia dela.
        texto = c["texto"].replace(banco.MARCA_DA_PROVA.strip(), "Prova (citada)")
        detalhe = "Critério %d de %s: %s" % (c["n"], documento["arquivo"], texto)
        if c["prova_aceita"]:
            detalhe += "\n%s%s" % (banco.MARCA_DA_PROVA, c["prova"])
        entrou = banco.enfileirar([{
            "id": id_fila, "usuario_id": uid, "projeto": projeto,
            "regra": "desenvolver", "gravidade": "media", "risco": 0,
            "trilho": "claude", "executor": "claude", "detalhe": detalhe,
        }])
        if entrou:
            aviso = self._aviso_do_conserto(uid, "desenvolvimento")
        else:
            aviso = self._aviso_do_pedido_repetido(
                banco.tarefa(id_fila, uid), "desenvolvimento")
        return self._json(200, {"ok": True, "pedido": bool(entrou),
                                "tarefa": id_fila, "aviso": aviso})

    # Provar roda comando da lista fechada na maquina do dono: balcao PROPRIO.
    TETO_DE_PROVAS = 10

    _TRAVA_DE_PROVAS = threading.Lock()

    def _provar_pedir(self):
        """O botao "Provar": enfileira UMA tarefa `provar` para um projeto.

        O corpo traz so o NOME do projeto, e ele so vale se estiver no estado
        DA CONTA de quem pediu: "nao existe" e "nao e seu" dao o MESMO 404. Os
        comandos vem da documentacao da conta (`provas_aceitas`, lista
        fechada), nunca do corpo. A tarefa nasce vermelha e espera o "Pode
        fazer"; quem roda e o braco executor.
        """
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="provar",
                                           teto=self.TETO_DE_PROVAS):
            return self._json(429, self.RECUSA)
        nome = corpo.get("projeto")
        if not nome or not isinstance(nome, str) or len(nome) > 200:
            return self._json(400, {"erro": "faltou o nome do projeto"})
        uid = sessao["usuario_id"]
        achados = self._criterios_da_conta(uid, nome)
        if not achados:
            return self._json(404, {"erro": "projeto nao encontrado"})
        nome, doc, _ = achados[0]
        if not tarefas.projeto_pode_desenvolver(nome):
            return self._json(403, {"erro": "projeto bloqueado"})
        comandos = list(documentos.provas_aceitas(doc, nome))
        if not comandos:
            return self._json(409, {"erro": "nenhuma prova para rodar"})
        # "Ja ha prova aberta?" e "enfileirar" sao UMA decisao so: sem a trava,
        # dois cliques simultaneos liam "nao ha" juntos e enfileiravam duas.
        with self._TRAVA_DE_PROVAS:
            if banco.prova_aberta(uid, nome):
                return self._json(200, {
                    "ok": True, "pedido": False, "tarefa": None,
                    "aviso": "Já há uma prova deste projeto na fila ou rodando."})
            # O dono entra NO ID (fila.id e TEXT PRIMARY KEY global). O carimbo
            # deixa pedir de novo depois que a anterior terminou.
            id_fila = "provar:%s:%s:%d" % (
                uid, hashlib.sha256(nome.encode("utf-8")).hexdigest()[:16],
                time.time_ns() // 1_000_000)
            entrou = banco.enfileirar([{
                "id": id_fila, "usuario_id": uid, "projeto": nome,
                "regra": tarefas.PROVAR, "gravidade": "media", "risco": 0,
                "trilho": "prova", "executor": tarefas.EXECUTOR_DA_PROVA,
                "detalhe": "Rodar as provas de %s.\n%s" % (
                    nome, documentos.pedido_de_provas(comandos,
                                                      banco.MARCA_DA_PROVA)),
            }])
        return self._json(200, {
            "ok": True, "pedido": bool(entrou), "tarefa": id_fila,
            "aviso": self._aviso_do_conserto(uid, "prova")})

    TIPOS_DE_PEDIDO_DO_VOZ = ("enfileirar_conserto",)
    _ID_DE_ALERTA = re.compile(r"[A-Za-z0-9._:-]{1,200}")

    def _voz_pedido(self):
        """O VOZ pede ao painel que enfileire o conserto de UM alerta.

        A tarefa nasce PENDENTE do "Pode fazer" do dono no painel e nunca roda
        sozinha (mesma regra e mesmas travas do botao da tela). O dono e o da
        MAQUINA autenticada, nunca algo que venha no corpo; "nao existe" e "nao e
        seu" dao a mesma resposta (404). `resumo` e so contexto do VOZ: dado, e
        nao vai para lugar nenhum.
        """
        maquina = self._voz_maquina()
        if maquina is None:
            return
        corpo = self._corpo_json(teto=16 * 1024)
        if corpo is None:
            return self._json(400, {"erro": "corpo invalido"})
        resumo = corpo.get("resumo", "")
        if (set(corpo) - {"tipo", "alerta_id", "resumo"}
                or corpo.get("tipo") not in self.TIPOS_DE_PEDIDO_DO_VOZ
                or not self._texto_gravavel(corpo.get("alerta_id"))
                or not 0 < len(corpo["alerta_id"]) <= 200
                or not self._texto_gravavel(resumo) or len(resumo) > 300):
            return self._json(400, {"erro": "pedido invalido"})
        if not cortina.registrar_tentativa(
                "maquina:%d" % maquina["id"], time.time(), balcao="vozpedido",
                teto=self.TETO_DE_PEDIDOS_DO_VOZ):
            return self._json(429, {"erro": "pedidos demais"})
        status, resposta = self._enfileirar_conserto(
            maquina["usuario_id"], corpo["alerta_id"])
        if status != 200:
            return self._json(status, resposta)
        return self._json(200, {"ok": True, "tarefa_id": resposta["tarefa"],
                                "pedido": resposta["pedido"],
                                "aviso": resposta["aviso"]})

    def _maquina_autorizar(self):
        """Liga ou desliga o direito desta maquina de trabalhar sozinha.

        Nao se chama "executar" de proposito: `test_rotas.PROIBIDO` casa `exec`
        contra o nome da funcao E o caminho da rota. O nome ruim doeria aqui
        antes de chegar ao servidor, que e para isso que aquela lista existe.
        """
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        try:
            id_ = int(corpo.get("id"))
        except (TypeError, ValueError):
            return self._json(400, {"erro": "id invalido"})
        ligado = bool(corpo.get("ligado"))
        if ligado and banco.maquina_so_mede(id_, sessao["usuario_id"]):
            # Parear pelo arquivo nao da direito de rodar nada. O banco recusa
            # tambem (`ligar_execucao`); aqui a recusa ganha a frase certa.
            return self._json(409, {"erro": "este computador so mede"})
        # `usuario_id` vai para dentro do UPDATE: o id vem do navegador, e um
        # numero vizinho nao pode ligar a execucao na maquina do outro.
        if not banco.ligar_execucao(id_, sessao["usuario_id"], ligado):
            return self._json(404, {"erro": "nao existe"})
        return self._json(200, {"ok": True, "ligado": ligado})

    # ------------------------------------------------- a ponte com o DERVS-VOZ
    #
    # O servidor SO GUARDA E ENTREGA. Nenhuma das cinco rotas abaixo executa
    # nada, abre shell ou SSH: o VOZ vem buscar o recado (conexao de saida dele)
    # e quem age e ele, no computador do dono. E NENHUMA carimba `visto_em` —
    # sinal de vida e so o relatorio (ver `_relatorio`).
    #
    # Balcao PROPRIO `voz`: nunca `TETO_DE_ENDERECOS` nem o de `relatorio`.
    TETO_DE_RECADOS = 30          # pedidos do dono por origem e janela
    TETO_DA_VOZ = 600             # pedidos da maquina: um a cada 1,5 s
    TETO_DE_PEDIDOS_DO_VOZ = 10   # conserto pedido pelo VOZ: balcao proprio
    TETO_DE_PENDENTES = 20        # recados pendentes por conta
    RECADOS_POR_ENTREGA = 10
    # `avisar` so o painel gera (`_varrer_vigilia`); a tela nao o oferece, e com
    # `muda_estado` a rota e o banco o recusam.
    TIPOS_DE_RECADO = ("analisar", "status", "propor", "avisar")
    NIVEIS_DE_RECADO = ("leitura", "muda_estado")
    CEREBROS_PEDIDOS = ("auto", "claude_code", "hermes")
    # Nome de projeto: sem barra, contrabarra, dois-pontos nem `..`.
    _ALVO_DE_RECADO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")

    @staticmethod
    def _iso_valido(valor) -> bool:
        if not isinstance(valor, str) or len(valor) > 40:
            return False
        try:
            datetime.fromisoformat(valor)
        except ValueError:
            return False
        return True

    @staticmethod
    def _texto_gravavel(valor) -> bool:
        """Texto que o SQLite aceita: um surrogate solto (`"\ud800"`) e JSON
        valido, passa pelo tamanho, e estoura UnicodeEncodeError no INSERT."""
        if not isinstance(valor, str):
            return False
        try:
            valor.encode("utf-8")
        except UnicodeEncodeError:
            return False
        return True

    @staticmethod
    def _numero_finito(valor) -> bool:
        """Numero >= 0, finito, e nao booleano (`True` e int em Python)."""
        if not isinstance(valor, (int, float)) or isinstance(valor, bool):
            return False
        try:
            return math.isfinite(valor) and valor >= 0
        except OverflowError:   # 10**400 e JSON valido e nao cabe em float
            return False

    def _voz_maquina(self):
        """A maquina autenticada, depois do balcao; ou None com 401/429 dado."""
        maquina = getattr(self, "_maquina", None)
        if maquina is None:            # cinto, alem do guarda do despacho
            self._json(401, {"erro": "token de maquina invalido"})
            return None
        if not cortina.registrar_tentativa(
                "maquina:%d" % maquina["id"], time.time(), balcao="voz",
                teto=self.TETO_DA_VOZ):
            self._json(429, {"erro": "pedidos demais"})
            return None
        return maquina

    def _voz_estado(self):
        """O VOZ conta como esta (qual cerebro, o que esta disponivel, gasto)."""
        maquina = self._voz_maquina()
        if maquina is None:
            return
        corpo = self._corpo_json(teto=64 * 1024)
        if corpo is None:
            return self._json(400, {"erro": "corpo invalido"})
        if set(corpo) != {"versao", "enviado_em", "cerebro_ativo", "cerebros",
                          "gasto_dia_usd"}:
            return self._json(400, {"erro": "campos desconhecidos ou faltando"})
        cerebros = corpo["cerebros"]
        if (corpo["versao"] != 1 or isinstance(corpo["versao"], bool)
                or not self._iso_valido(corpo["enviado_em"])
                or corpo["cerebro_ativo"] not in banco.VOZ_CEREBRO_ATIVO
                or not self._numero_finito(corpo["gasto_dia_usd"])
                or not isinstance(cerebros, dict)
                or not set(cerebros) <= set(banco.VOZ_CEREBROS)):
            return self._json(400, {"erro": "estado invalido"})
        limpo = {}
        for nome, c in cerebros.items():
            if (not isinstance(c, dict)
                    or not set(c) <= {"disponivel", "motivo"}
                    or not isinstance(c.get("disponivel"), bool)
                    or not self._texto_gravavel(c.get("motivo", ""))
                    or len(c.get("motivo", "")) > 200):
                return self._json(400, {"erro": "cerebro invalido: %s" % nome})
            limpo[nome] = {"disponivel": c["disponivel"],
                           "motivo": c.get("motivo", "")}
        banco.guardar_voz_estado(maquina["id"], maquina["usuario_id"], {
            "versao": 1, "enviado_em": corpo["enviado_em"],
            "cerebro_ativo": corpo["cerebro_ativo"], "cerebros": limpo,
            "gasto_dia_usd": float(corpo["gasto_dia_usd"])})
        return self._json(200, {"ok": True})

    def _voz_recados(self):
        """Os recados pendentes DESTA maquina; cada um sai uma vez so."""
        maquina = self._voz_maquina()
        if maquina is None:
            return
        return self._json(200, {"recados": banco.entregar_voz_recados(
            maquina["id"], maquina["usuario_id"], self.RECADOS_POR_ENTREGA)})

    def _voz_resultado(self):
        """O que o VOZ fez com um recado. So responde recado DA PROPRIA maquina
        e dono; o resto e 404, igual a inexistente."""
        maquina = self._voz_maquina()
        if maquina is None:
            return
        corpo = self._corpo_json(teto=16 * 1024)
        if corpo is None:
            return self._json(400, {"erro": "corpo invalido"})
        id_, resumo = corpo.get("id"), corpo.get("resumo", "")
        custo, duracao = corpo.get("custo_usd", 0), corpo.get("duracao_s", 0)
        terminado = corpo.get("terminado_em") or banco.agora()
        if (not self._texto_gravavel(id_) or not 0 < len(id_) <= 64
                or corpo.get("cerebro") not in banco.VOZ_CEREBRO_RESULTADO
                or corpo.get("estado") not in banco.VOZ_ESTADOS_DE_RESULTADO
                or not self._texto_gravavel(resumo) or len(resumo) > 1000
                or not self._numero_finito(custo)
                or not self._numero_finito(duracao)
                or not self._iso_valido(terminado)):
            return self._json(400, {"erro": "resultado invalido"})
        if not banco.registrar_voz_resultado(
                id_, maquina["id"], maquina["usuario_id"], corpo["cerebro"],
                corpo["estado"], resumo, float(custo), float(duracao),
                terminado):
            return self._json(404, {"erro": "nao existe"})
        return self._json(200, {"ok": True})

    def _voz(self):
        """A ponte como o dono ve: maquinas (vigilia + estado) e recados."""
        sessao = self._sessao()
        if sessao is None:
            return self._json(403, {"erro": "entre de novo"})
        return self._json(200, banco.voz_do_usuario(sessao["usuario_id"]))

    def _voz_recado(self):
        """O dono deixa um recado para o VOZ de uma das maquinas dele.

        `texto` e DADO: e guardado e entregue, nunca interpretado aqui.
        """
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        if not cortina.registrar_tentativa(self._origem_do_pedido(), time.time(),
                                           balcao="voz",
                                           teto=self.TETO_DE_RECADOS):
            return self._json(429, {"erro": "recados demais; espere alguns minutos"})
        mid, alvo, texto = corpo.get("maquina_id"), corpo.get("alvo"), corpo.get("texto", "")
        # A faixa de INTEGER do SQLite: `10**30` e int valido e estourava no banco.
        if (not isinstance(mid, int) or isinstance(mid, bool)
                or not -2**63 <= mid < 2**63
                or corpo.get("tipo") not in self.TIPOS_DE_RECADO
                or corpo.get("nivel") not in self.NIVEIS_DE_RECADO
                or (corpo["tipo"] == "avisar" and corpo["nivel"] != "leitura")
                or corpo.get("cerebro_pedido") not in self.CEREBROS_PEDIDOS
                or not isinstance(alvo, str)
                or not self._ALVO_DE_RECADO.fullmatch(alvo) or ".." in alvo
                or not self._texto_gravavel(texto) or len(texto) > 500
                or "\x00" in texto):
            return self._json(400, {"erro": "recado invalido"})
        id_, motivo = banco.criar_voz_recado(
            sessao["usuario_id"], mid, corpo["tipo"], alvo, texto,
            corpo["nivel"], corpo["cerebro_pedido"], self.TETO_DE_PENDENTES)
        if motivo == "sem_maquina":
            return self._json(404, {"erro": "nao existe"})
        if motivo == "teto":
            return self._json(429, {"erro": "ha recados demais esperando o VOZ; "
                                            "espere ele responder"})
        return self._json(200, {"id": id_})

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

    # ------------------------------------------- a guarda comum das escritas
    #
    # Tres rotas escrevem no banco (silenciar, arquivar, desarquivar) e as tres
    # precisam exatamente da mesma guarda. Ate a etapa 14 ela existia UMA vez,
    # escrita a mao dentro de `_silenciar`. Copiar essas vinte linhas mais duas
    # vezes seria pedir para a terceira copia esquecer uma delas — e guarda de
    # seguranca esquecida nao aparece na tela, aparece no incidente.
    def _guarda_de_escrita(self):
        """(corpo, sessao) — ou (None, None) com a recusa JA respondida.

        Falha FECHADA: todo caminho que nao chega a ultima linha devolve o par
        vazio, e quem chama sai na hora sem tocar no banco.
        """
        if (self.headers.get("Origin") or "") not in ORIGENS_OK:
            self._json(403, {"erro": "origem nao permitida"})
            return None, None
        # As rotas sao de `acesso="dado"`, entao o despacho ja garantiu que ha
        # sessao completa. Aqui so falta o anti-CSRF DAQUELA sessao.
        sessao = self._sessao()
        if sessao is None:
            # A sessao pode ter vencido entre o despacho e esta linha. Sem esta
            # guarda, `_csrf_da_sessao(None)` levantaria TypeError e devolveria
            # 500 onde o certo e 403.
            self._json(403, {"erro": "entre de novo"})
            return None, None
        if not secrets.compare_digest(self.headers.get("X-Token") or "",
                                      self._csrf_da_sessao(sessao)):
            self._recusa_pagina_velha()
            return None, None
        try:
            n = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(max(0, min(n, 16_384))) or b"{}")
        except (ValueError, OSError):
            self._json(400, {"erro": "pedido invalido"})
            return None, None
        if not isinstance(corpo, dict):
            self._json(400, {"erro": "pedido invalido"})
            return None, None
        return corpo, sessao

    def _id_de_pendencia(self, corpo):
        """O id validado, ou `None` com a recusa ja respondida."""
        pid = corpo.get("id")
        if not pid or not isinstance(pid, str):
            self._json(400, {"erro": "faltou o id da pendencia"})
            return None
        # O id e sempre `regra:projeto` — dezenas de caracteres. Sem teto, quem
        # tem o token grava ids de 16 KiB, um por pedido, e cada um vira linha
        # que nenhuma coleta jamais colhe. Nao vaza nada; incha o banco.
        if len(pid) > 200:
            self._json(400, {"erro": "id longo demais"})
            return None
        return pid

    def _silenciar(self):
        """Esconde uma pendencia por N horas. SO escreve no banco.

        Nao roda programa nenhum: o pior que um pedido forjado consegue aqui e
        esconder um alerta da tela do dono por ate 30 dias, e isso se desfaz
        sozinho. Mesmo assim o par Origin + token continua exigido, porque o
        alerta escondido pode ser um alerta de seguranca.
        """
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        pid = self._id_de_pendencia(corpo)
        if pid is None:
            return
        try:
            horas = max(1, min(24 * 30, int(corpo.get("horas") or 24)))
        except (TypeError, ValueError):
            return self._json(400, {"erro": "prazo invalido"})
        ate = (datetime.now(timezone.utc)
               + timedelta(hours=horas)).isoformat(timespec="seconds")
        banco.silenciar(pid, ate, usuario_id=sessao["usuario_id"])
        return self._json(200, {"ok": True,
                                "saida": "silenciada por %d h." % horas})

    # O limite do motivo. Ele e escrito a mao, numa linha, para o proprio dono
    # se lembrar daqui a tres meses — nao e campo de texto livre para prosa.
    MOTIVO_MAX = 300

    def _arquivar(self):
        """"Isto esta certo assim" — o sumico PERMANENTE, e por isso com motivo.

        A correcao veio da fase 2 do desenho: ate aqui a unica saida era adiar
        24 horas, sempre. Consequencia — projeto que o dono arquivou de
        proposito voltava a cutucar todo dia, para sempre, e isso treina a
        pessoa a ignorar a lista inteira. Uma lista que se aprende a ignorar
        nao protege ninguem.

        O motivo e EXIGIDO na rota, e nao so no banco. `banco.arquivar`
        levanta ValueError sem ele; sem esta guarda o dono veria "nao
        conseguimos arquivar" — mensagem de falha de servidor — para o que e
        so um campo em branco.
        """
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        pid = self._id_de_pendencia(corpo)
        if pid is None:
            return
        motivo = corpo.get("motivo")
        if not isinstance(motivo, str) or not motivo.strip():
            return self._json(400, {"erro": "escreva por que isto está certo assim"})
        motivo = motivo.strip()
        # RECUSAR, nao cortar. Ate a revisao de 28/08/2026 esta linha era
        # `motivo[:self.MOTIVO_MAX]`: o dono escrevia a justificativa inteira, a
        # rota respondia "arquivada." e metade do texto sumia sem aviso. O
        # rastro que o arquivar existe para preservar chegava cortado, e a
        # resposta afirmava sucesso total onde houve perda de dado -- a mentira
        # do painel em miniatura. A recusa carrega o numero: recusa sem limite
        # explicito manda o dono adivinhar onde cortar.
        if len(motivo) > self.MOTIVO_MAX:
            return self._json(400, {
                "erro": "o motivo passou de %d caracteres (você escreveu %d). "
                        "Resuma — isto é um bilhete para você mesmo daqui a "
                        "três meses." % (self.MOTIVO_MAX, len(motivo))})
        banco.arquivar(pid, usuario_id=sessao["usuario_id"], motivo=motivo)
        return self._json(200, {"ok": True, "saida": "arquivada."})

    def _desarquivar(self):
        """A volta. Carimba em vez de apagar: o rastro vale tambem para o desfazer."""
        corpo, sessao = self._guarda_de_escrita()
        if corpo is None:
            return
        pid = self._id_de_pendencia(corpo)
        if pid is None:
            return
        banco.desarquivar(pid, usuario_id=sessao["usuario_id"])
        return self._json(200, {"ok": True, "saida": "de volta a lista."})

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
# AS QUATRO CLASSES DE ACESSO, e a lista de verdade. `_despachar` recusa
# qualquer rota que declare outra coisa, e `test_rotas.py` le DAQUI em vez de
# repetir o conjunto — duas copias divergem, e a que diverge e sempre a que
# ninguem le.
ACESSOS = frozenset(("aberta", "cortina", "dado", "maquina"))

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
    # "Isto esta certo assim" e o desfazer dele. Escrevem uma linha no banco e
    # nao rodam programa nenhum, como o silenciar.
    "/api/arquivar":            Rota("POST", Hub._arquivar,       "dado"),
    "/api/desarquivar":         Rota("POST", Hub._desarquivar,    "dado"),

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

    # As maquinas (etapa 11). As tres de cima sao do dono; as duas de baixo sao
    # do agente, e `maquina` e a quarta classificacao de acesso — token proprio,
    # sem cookie e sem Origin. `/agente/parear` e "aberta" por necessidade: quem
    # chega com o codigo de seis digitos ainda nao tem token nenhum, e e por isso
    # que o teto de chute por origem esta DENTRO dela.
    "/api/maquinas":            Rota("GET",  Hub._maquinas,        "dado"),
    "/api/maquinas/parear":     Rota("POST", Hub._maquina_parear,  "dado"),
    "/api/maquinas/remover":    Rota("POST", Hub._maquina_remover, "dado"),
    "/agente/parear":           Rota("POST", Hub._parear,          "aberta"),
    "/agente/relatorio":        Rota("POST", Hub._relatorio,       "maquina"),
    "/api/maquinas/autorizar":  Rota("POST", Hub._maquina_autorizar, "dado"),
    # Conectar simples (A). Os nomes foram conferidos contra
    # `test_rotas.PROIBIDO` ("autorizar" passa; "autorizacao" casaria `acao`).
    # `/agente/pedir` e `/agente/esperar` sao "aberta": quem chega ainda nao
    # tem token, e por isso o teto por origem mora DENTRO delas. O arquivo
    # `.cmd` e `dado` e `GET`: nao cria pareamento nenhum.
    "/agente/pedir":            Rota("POST", Hub._agente_pedir,     "aberta"),
    "/agente/esperar":          Rota("POST", Hub._agente_esperar,   "aberta"),
    "/agente/pacote":           Rota("GET",  Hub._agente_pacote,    "maquina"),
    "/api/pedido":              Rota("GET",  Hub._pedido_ver,       "dado"),
    "/api/pedido/autorizar":    Rota("POST", Hub._pedido_autorizar, "dado"),
    "/api/conectar.cmd":        Rota("GET",  Hub._arquivo_de_conectar, "dado"),

    # A porta 3 (fatia B). As cinco sao `dado`: servidor e endereco de producao
    # sao dado da conta que gravou, e cada rota le SO o da sessao — o IDOR ja
    # foi consertado duas vezes neste repositorio. `/api/servidores/sugerir`
    # SO PROPOE — nao grava nada em `endereco_producao`.
    "/api/servidores":          Rota("GET",  Hub._servidores,        "dado"),
    "/api/servidores/guardar":  Rota("POST", Hub._servidor_guardar,  "dado"),
    "/api/servidores/remover":  Rota("POST", Hub._servidor_remover,  "dado"),
    "/api/servidores/sugerir":  Rota("POST", Hub._servidor_sugerir,  "dado"),
    "/api/enderecos":           Rota("GET",  Hub._enderecos,        "dado"),
    "/api/enderecos/guardar":   Rota("POST", Hub._endereco_guardar, "dado"),

    # A porta 2 (fatia C). A de ida e `dado` — so quem esta dentro pede a
    # instalacao da PROPRIA conta. A de volta e `cortina` PELA MESMA RAZAO que
    # `/entrar/github/retorno`: quem chega vem do GitHub, num salto de pagina
    # que o nosso JavaScript nao fez. A autorizacao dela nao sai da sessao, sai
    # do selo assinado com o cofre.
    "/api/github/instalar":     Rota("POST", Hub._github_instalar,  "dado"),
    "/api/github/procurar":     Rota("POST", Hub._github_procurar,  "dado"),
    "/api/github":              Rota("GET",  Hub._github_estado,    "dado"),
    "/github/instalado":        Rota("GET",  Hub._github_instalado, "cortina"),

    # As tarefas (Fatia 2). `/agente/resultado` e a UNICA de acesso `maquina`
    # aqui: e por ela que o agente conta o que esta acontecendo, e e na
    # RESPOSTA dela que o pedido de parada desce. As quatro `/api/tarefas*` sao
    # do dono, acesso `dado`, com a guarda comum das escritas.
    #
    # Os nomes foram escolhidos contra `test_rotas.PROIBIDO`, que casa
    # `acao|execucao|exec|terminal|pty|shell|comando|grafo` contra o CAMINHO e
    # contra o NOME DA FUNCAO: `_tarefa_aprovar` passa, `_executar_tarefa` nao.
    # E o servidor continua sem importar `execucao`: quem executa a sessao e o
    # agente, na maquina dele. O `subprocess` que existe aqui e o de sempre, e
    # roda SO os coletores da tabela `COLETORES` — nenhum argv vem de pedido.
    "/agente/resultado":        Rota("POST", Hub._resultado,       "maquina"),
    "/api/tarefas":             Rota("GET",  Hub._tarefas,         "dado"),
    "/api/eventos":             Rota("GET",  Hub._eventos,         "dado"),
    "/api/consumo":             Rota("GET",  Hub._consumo,         "dado"),
    "/api/tarefas/aprovar":     Rota("POST", Hub._tarefa_aprovar,  "dado"),
    "/api/tarefas/parar":       Rota("POST", Hub._tarefa_parar,    "dado"),
    "/api/tarefas/cor":         Rota("POST", Hub._tarefa_cor,      "dado"),

    # A Auditoria Profunda (Etapa 5). As duas sao `dado`, e nao `cortina`: um
    # achado carrega caminho de arquivo, numero de linha e trecho de
    # codigo-fonte privado do dono.
    "/api/auditoria":           Rota("GET",  Hub._auditoria,        "dado"),
    "/api/auditoria/pedir":     Rota("POST", Hub._auditoria_pedir,  "dado"),
    "/api/consertar":           Rota("POST", Hub._consertar_pedir,  "dado"),

    # O progresso por documentacao. `/api/progresso` LE (a conta e os criterios
    # de um projeto da conta); `/api/desenvolver` so ENFILEIRA, e quem roda e o
    # braco executor, depois do "Pode fazer". Nenhuma das duas roda prova.
    "/api/progresso":           Rota("GET",  Hub._progresso,        "dado"),
    "/api/desenvolver":         Rota("POST", Hub._desenvolver_pedir, "dado"),
    "/api/provar":              Rota("POST", Hub._provar_pedir,      "dado"),

    # A ponte com o DERVS-VOZ. As tres `/agente/voz/*` sao `maquina` (token do
    # agente, so conexao de saida); as duas `/api/voz*` sao do dono. O servidor
    # so guarda e entrega — nada daqui executa, e nenhuma carimba `visto_em`.
    "/agente/voz/estado":       Rota("POST", Hub._voz_estado,       "maquina"),
    "/agente/voz/recados":      Rota("GET",  Hub._voz_recados,      "maquina"),
    "/agente/voz/resultado":    Rota("POST", Hub._voz_resultado,    "maquina"),
    "/agente/voz/pedido":       Rota("POST", Hub._voz_pedido,       "maquina"),
    "/api/voz":                 Rota("GET",  Hub._voz,              "dado"),
    "/api/voz/recado":          Rota("POST", Hub._voz_recado,       "dado"),
}
# A capa e servida a qualquer visitante, entao a folha de estilo e o teclado da
# cortina precisam ser abertos. Estes dois nao: quem os carrega e o
# `index.html`, que `_pagina` so devolve com sessao. Servi-los abertos entregava
# a tela inteira do painel — o desenho, os nomes dos campos e a lista das rotas
# de API que ela chama — a quem tivesse so a combinacao da cortina.
#
# A protecao casa por CAMINHO EXATO, entao renomear o arquivo a desliga sem
# aviso. `test_rotas.py` cobra que os dois nomes daqui existam em `ROTAS`.
ESTATICOS_COM_SESSAO = {"/assets/painel.js", "/assets/painel.css"}

ROTAS.update({caminho: Rota("GET", Hub._estatico,
                            "dado" if caminho in ESTATICOS_COM_SESSAO
                            else "aberta")
              for caminho in ESTATICOS_OK})

# Fica FORA da classe porque `_redes_confiaveis` precisa existir antes, e uma
# funcao do modulo nao pode ser chamada de dentro do corpo da classe que ela
# vem depois. O valor e o mesmo de sempre: vazio nesta maquina, a faixa privada
# do Docker no servidor.
Hub.PROXIES_CONFIAVEIS = _redes_confiaveis(
    os.environ.get("DERVS_PROXIES_CONFIAVEIS"))

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
    vazio = not banco.montar_estado(
        con, usuario_id=banco.conta_local(con))["projetos"]
    con.close()
    if combinacao:
        print("=" * 62)
        print("COMBINACAO DE ACESSO: %s" % combinacao)
        print("Anote agora. Ela NAO aparece de novo.")
        print("=" * 62)
    aviso = _aviso_do_teto(DOMINIO, Hub.PROXIES_CONFIAVEIS)
    if aviso:
        print("=" * 62)
        print(aviso)
        print("=" * 62)
    if not GITHUB_ID or not GITHUB_SECRET:
        print("AVISO: sem DERVS_GITHUB_ID/DERVS_GITHUB_SECRET, a entrada por"
              " GitHub responde 404. Ver docs/operacao/registrar-app-github.md.")
    if E_LOCAL:
        print("AMBIENTE LOCAL: dado de mentira, e a porta /entrar/local esta"
              " aberta atras da cortina. Combinacao: %s"
              % cortina.COMBINACAO_LOCAL)
    mede_aqui = _mede_esta_maquina()
    if vazio and mede_aqui:
        coletar("local", "primeira")

    if mede_aqui:
        threading.Thread(target=laco, args=("local", INTERVALO), daemon=True).start()
    for camada, (_, intervalo) in COLETORES.items():
        if not intervalo:
            continue
        if camada in CAMADAS_DESTA_MAQUINA and not mede_aqui:
            continue
        threading.Thread(target=laco, args=(camada, intervalo), daemon=True).start()

    escuta = _endereco_de_escuta()
    srv = ThreadingHTTPServer((escuta, PORTA), Hub)
    print("HUB do dev no ar: http://localhost:%d (escutando em %s)" % (PORTA, escuta))
    if mede_aqui:
        print("Camadas: local %ds · github 20min · pesado 24h. Ctrl+C encerra."
              % INTERVALO)
    else:
        print("Camadas: so github (20min). A medicao desta maquina esta"
              " desligada; quem mede e o agente pareado. Ctrl+C encerra.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
