# -*- coding: utf-8 -*-
"""Coletor do HUB do dev.

Le o estado REAL de cada repositorio (git), do Docker, das portas da maquina, do
grafo de codigo e da memoria do Claude; calcula maturidade e projecoes; e grava
no SQLite (banco.py, camada "local"). Nao escreve nada nos repositorios.

SEGREDO: o coletor abre o arquivo de variaveis para extrair NOMES de variavel e
so isso — a expressao regular para no sinal de igual, o valor nunca e lido, nunca
entra no banco e nunca chega a tela. E o unico jeito de detectar que o exemplo
versionado divergiu do real, que e onde erro silencioso de deploy costuma nascer.
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

import banco
import documentos


# A TELINHA PISCANDO NA TELA DO DONO (24/08/2026). O painel roda sob pythonw.exe,
# que nao tem console proprio — entao cada programa de console que ele chama
# (git, aqui ~20 vezes por coleta, de minuto em minuto) ganha um console NOVO,
# que aparece por cima do que o dono estiver fazendo. CREATE_NO_WINDOW resolve
# na origem: o filho roda sem janela, e continuamos lendo o stdout normalmente.
# Mesma correcao ja aplicada em .claude/scripts/vigia-vscode.py em 13/08/2026.
#
# So sob pythonw, porque a marca nao e de graca: o Windows aloca um console
# escondido por filho (~11ms cada). Rodando do terminal o filho herda o console
# que ja existe — nada pisca ali.
def _sem_console():
    if not sys.platform.startswith("win"):
        return False
    if os.path.basename(sys.executable or "").lower() == "pythonw.exe":
        return True
    return sys.stdout is None


SEM_JANELA = 0x08000000 if _sem_console() else 0

AQUI = Path(__file__).resolve().parent
CASOS = AQUI / "casos.json"


# --------------------------------------------------- as raizes que sao medidas
#
# Ate 01/09/2026 havia aqui uma linha so, com o caminho DESTA maquina escrito no
# codigo-fonte. Em qualquer outro computador o coletor media zero projeto — e o
# painel nao tinha como saber a diferenca entre "nao ha projeto" e "nao olhei".
# Agora sao varias raizes, e nenhuma delas nasce escrita na mao.
VAR_RAIZES = "DERVS_RAIZES"


def arquivo_do_agente() -> Path:
    """O mesmo arquivo em que `agente/enviar.py` guarda o token da maquina.

    A leitura e reescrita AQUI, pequena e propria, em vez de importar
    `agente.enviar`: aquele modulo faz `import coletar` na subida (enviar.py:36),
    entao importa-lo daqui seria um ciclo.
    """
    bruto = os.environ.get("DERVS_AGENTE_ARQUIVO")
    if bruto:
        return Path(bruto).expanduser()
    return Path.home() / ".dervs" / "agente.json"


def _config_do_agente() -> dict:
    """O conteudo do arquivo do agente, ou {}.

    Arquivo ausente, JSON torto e conteudo que nao e um objeto caem todos no
    mesmo lugar, sem levantar: cada um deles so quer dizer "ninguem disse", e
    quem chama segue para o proximo degrau.
    """
    try:
        dados = json.loads(arquivo_do_agente().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def raiz_de_ultimo_recurso() -> Path:
    """O palpite de quando ninguem disse nada. DERIVADO de `Path.home()`.

    Nunca escrito na mao: um caminho literal aqui e exatamente o defeito que
    esta funcao existe para nao repetir.
    """
    return Path.home() / "source" / "repos"


def raizes_configuradas() -> list:
    """As pastas que este computador mede, do mais explicito ao ultimo recurso.

    1. a variavel de ambiente `DERVS_RAIZES`, separada por `os.pathsep`;
    2. a chave `raizes` do arquivo de configuracao do agente;
    3. `Path.home()` mais `source/repos`.

    Devolve sempre pelo menos uma raiz. Se ela existe de verdade nesta maquina
    e outra pergunta, respondida por `avisos_das_raizes()`.
    """
    bruto = os.environ.get(VAR_RAIZES, "")
    caminhos = [t for t in bruto.split(os.pathsep) if t.strip()]
    if not caminhos:
        do_arquivo = _config_do_agente().get("raizes")
        if isinstance(do_arquivo, list):
            caminhos = [t for t in do_arquivo if isinstance(t, str) and t.strip()]
    if not caminhos:
        return [raiz_de_ultimo_recurso()]
    vistos, saida = set(), []
    for texto in caminhos:
        p = Path(texto.strip()).expanduser()
        if str(p).lower() in vistos:
            continue                       # a mesma raiz duas vezes mede uma vez
        vistos.add(str(p).lower())
        saida.append(p)
    return saida


def escrever_raizes(raizes) -> Path:
    """Grava a chave `raizes` no arquivo do agente PRESERVANDO as outras chaves.

    O token da maquina mora neste mesmo arquivo: reescrever o arquivo inteiro
    com so a nossa chave desconectaria o agente em silencio.

    O JEITO DE GRAVAR E COPIADO de `guardar_token` (agente/enviar.py:72), e as
    razoes sao as de la: o temporario e criado com `O_EXCL` porque o modo do
    `os.open` so vale para arquivo NOVO (e o `chmod` falha em silencio), e o
    `os.replace` por cima e atomico — uma queda no meio da escrita nao leva
    junto o token que ja estava gravado.
    """
    destino = arquivo_do_agente()
    destino.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    dados = _config_do_agente()
    dados["raizes"] = [str(Path(r)) for r in raizes]
    texto = json.dumps(dados, ensure_ascii=False, indent=2)
    passagem = destino.with_name(destino.name + ".novo")
    try:
        passagem.unlink()                  # sobra de uma queda anterior
    except OSError:
        pass
    fd = os.open(passagem, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as arq:
        arq.write(texto)
    os.replace(passagem, destino)
    return destino


def avisos_das_raizes(raizes=None) -> list:
    """Uma frase por raiz que NAO existe, nomeando cada uma delas.

    Raiz que existe e esta vazia e caso DIFERENTE: ali "nenhum projeto" e uma
    resposta verdadeira. Raiz que nao existe nao foi medida, e calar isso e o
    painel mentindo com cara de boa noticia.
    """
    return ["a raiz %s nao existe nesta maquina; os projetos dela NAO foram"
            " medidos — isto nao e 'nenhum projeto pendente'." % raiz
            for raiz in (RAIZES if raizes is None else raizes) if not raiz.is_dir()]


RAIZES = raizes_configuradas()

# Ate 24/08/2026 o PROPRIO HUB morava fora de source\repos, e por isso nao se
# vigiava: sapateiro de pe no chao. Listar a pasta aqui foi a correcao escolhida
# NAQUELA data em vez de mudar o projeto de lugar, porque mover quebraria tres
# coisas batizadas pelo CAMINHO — a pasta de memoria do Claude, o indice do
# grafo e o processo no ar — e a primeira falha CALADA: a memoria nao some, so
# deixa de ser encontrada, e ninguem avisa.
#
# Em 26/08/2026 o projeto virou o `dervs` e nasceu ja dentro de source\repos,
# quando nao havia ainda memoria, indice nem processo amarrados ao caminho novo
# — o custo de mover era quase zero, e so cresceria. Hoje a varredura das
# raizes ja encontra esta pasta sozinha, e a linha abaixo e DEDUPLICADA em
# pastas_de_projeto(): ela nao mede nada duas vezes.
#
# A linha fica como rede: se alguem mover este projeto para fora de repos\ de
# novo, o hub continua se vigiando em vez de voltar a ser sapateiro descalco.
# AQUI, e nao o caminho escrito na mao, para continuar certo se a pasta mudar
# de nome.
def _casas_do_programa():
    """As pastas onde o `conectador` instala o programa (as mesmas regras de
    `conectador.casa_do_programa`, copiadas porque este arquivo nao importa o
    conectador). Rodando de uma delas, AQUI e o pacote, nao um projeto."""
    local = os.environ.get("LOCALAPPDATA")
    casas = []
    for bruto in (os.environ.get("DERVS_CASA"),
                  local and str(Path(local) / "DERVS" / "programa"),
                  str(Path.home() / ".dervs" / "programa")):
        if bruto:
            try:
                casas.append(str(Path(bruto).expanduser().resolve()).lower())
            except OSError:
                pass
    return casas


# Rodando do PACOTE (computador conectado pelo arquivo), a pasta do programa
# nunca e projeto: apareceria no painel como "casa"/"programa". Do repositorio
# clonado, AQUI e o proprio DERVS e continua medido.
AVULSOS = [] if str(AQUI).lower() in _casas_do_programa() else [AQUI]


def pastas_de_projeto():
    """Toda pasta que o HUB mede: as filhas de CADA raiz, mais as avulsas.

    A deduplicacao por caminho em minusculas ja existia para os AVULSOS; agora
    ela vale tambem entre raizes, porque duas raizes podem se sobrepor (ou vir
    repetidas com maiuscula diferente) e ninguem quer medir o mesmo projeto
    duas vezes.
    """
    achadas, vistas = [], set()
    for raiz in RAIZES:
        if not raiz.is_dir():
            continue
        for p in raiz.iterdir():
            if not p.is_dir() or p.name.startswith(".") or str(p).lower() in vistas:
                continue
            vistas.add(str(p).lower())
            achadas.append(p)
    for p in AVULSOS:
        if p.is_dir() and str(p).lower() not in vistas:
            vistas.add(str(p).lower())
            achadas.append(p)
    return sorted(achadas, key=lambda p: p.name.lower())

# Onde o grafo de codigo guarda um .db por projeto. A data de modificacao do
# arquivo E a idade do indice — o codebase-memory-mcp nao expoe isso por API, e
# desde 24/08/2026 ele nao reindexa mais sozinho (a varredura automatica foi
# desligada depois de congelar a maquina duas vezes).
CACHE_GRAFO = Path.home() / ".cache" / "codebase-memory-mcp"

# Onde o Claude Code guarda a memoria de cada projeto, uma pasta por caminho.
PROJETOS_CLAUDE = Path.home() / ".claude" / "projects"

# O vigia-vscode grava uma marca por projeto aberto e atualiza a data dela de
# minuto em minuto. A data do arquivo E a resposta.
MARCAS_VIGIA = Path.home() / ".claude" / "state" / "vigia"
MARCA_FRESCA = 180        # 3 min: o vigia roda a cada minuto, com folga
VIGIA_VIVO = 420          # marca mais nova que isso = o vigia esta rodando


def abertos_no_editor():
    """Nomes de projeto com janela do VS Code aberta AGORA. None se nao der.

    "Devia estar no ar" nesta maquina quer dizer "aberto no VS Code": e o criterio
    do vigia-vscode, que sobe e derruba o Docker por ele. Reimplementar a deteccao
    aqui criaria uma segunda verdade sobre a mesma coisa — o erro que este HUB
    existe para acabar.

    POR QUE LER O DISCO E NAO IMPORTAR O SCRIPT DELE (revisao de 24/08/2026):
    a primeira versao carregava e EXECUTAVA ~/.claude/scripts/vigia-vscode.py a
    cada 60 s. Aquele arquivo mora numa pasta que sessoes de agente escrevem com
    frequencia; e este processo escuta em rede e roda comandos. Uma alteracao
    naquele arquivo viraria execucao aqui dentro no minuto seguinte. Lendo as
    marcas que ele mesmo grava, temos a MESMA verdade sem executar nada.

    Devolve None (= "nao sei") quando as marcas estao todas velhas, porque isso
    quer dizer que o vigia nao esta rodando. A regra de container fica calada:
    alarme falso custa mais caro que silencio.
    """
    if not MARCAS_VIGIA.is_dir():
        return None
    agora = AGORA.timestamp()
    marcas = {}
    for arq in MARCAS_VIGIA.iterdir():
        if arq.name.startswith("_") or arq.suffix == ".json" or not arq.is_file():
            continue                       # "_falhas-*.json" nao e marca de janela
        try:
            marcas[arq.name] = agora - arq.stat().st_mtime
        except OSError:
            pass
    if not marcas or min(marcas.values()) > VIGIA_VIVO:
        return None                        # o vigia nao esta de pe: nao da para saber
    return {nome for nome, idade in marcas.items() if idade <= MARCA_FRESCA}


def nome_da_marca(repo) -> str:
    """O nome de arquivo que o vigia usa para este caminho.

    C:\\dev\\repos\\dents -> c-dev-repos-dents
    Comparamos o CAMINHO INTEIRO. Casar so o fim do nome daria "sophia" para o
    projeto "o-que-e-que-eu-faco-sophia".
    """
    return str(repo).lower().replace("\\", "/").replace("/", "-").replace(":", "")

AGORA = datetime.now(timezone.utc)
ARQ_SEGREDO = "." + "env"          # nome montado: nunca lemos o conteudo
ARQ_EXEMPLO = ARQ_SEGREDO + ".example"

EXT_LINGUAGEM = {
    ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
    ".cs": "C#", ".py": "Python", ".sql": "SQL", ".css": "CSS", ".scss": "CSS",
    ".html": "HTML", ".md": "Markdown", ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
    ".prisma": "Prisma", ".sh": "Shell", ".ps1": "PowerShell", ".php": "PHP", ".go": "Go",
}
# Linguagens onde existe logica testavel. Fora daqui e tela, dado ou config —
# e a regra da casa isenta CSS, layout e texto de tela de TDD.
LINGUAGENS_TESTAVEIS = {"TypeScript", "JavaScript", "C#", "Python", "PHP", "Go"}
IGNORAR_DIR = {
    "node_modules", ".git", "dist", "build", ".next", "obj", "bin", ".turbo",
    "venv", ".venv", "__pycache__", "coverage", ".pnpm-store", "vendor", "out",
}

# Como se chama um arquivo de teste, por linguagem. O prefixo "test_" faltava:
# e a convencao do Python, e por isso o HUB dizia que ELE MESMO nao tinha teste
# automatizado — com 56 deles no disco. Achado em 24/08/2026, na primeira coleta
# depois que o painel passou a se vigiar. Falso negativo em medida de qualidade e
# pior que numero ausente: parece informacao.
EH_TESTE = re.compile(
    r"(\.test\.|\.spec\.|_test\.|^test_.*\.py$|^conftest\.py$|Tests?\.cs$)", re.I)


def executa(args, cwd=None, timeout=25):
    """Roda o comando e devolve (deu_certo, saida).

    A saida vazia sozinha nao diz nada: "git status" de arvore limpa e "git
    ausente do PATH" produzem a MESMA string vazia. Quem so olha a string acaba
    afirmando "arvore limpa, 0 commits" de um repo que nunca foi medido — numero
    errado com cara de certo, o pior defeito possivel num painel. Por isso o
    primeiro item do par: ele separa "medi e nao ha nada" de "nao consegui
    medir". Mesma distincao que portas_escutando() ja fazia com None.
    """
    try:
        r = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=SEM_JANELA,
        )
        return (r.returncode == 0), (r.stdout.strip() if r.returncode == 0 else "")
    except Exception:
        return False, ""


def sh(args, cwd=None, timeout=25):
    """Só a saída, para quem de fato nao precisa distinguir falha de vazio."""
    return executa(args, cwd=cwd, timeout=timeout)[1]


def git(repo: Path, *args):
    return sh(["git", "-C", str(repo), *args])


def idade_do_mais_antigo(repo: Path, sujos: list) -> int | None:
    """Ha quantos dias o trabalho nao commitado esta parado ai.

    O git nao guarda "desde quando o arquivo esta sujo" — quem guarda e o sistema
    de arquivos. Pegamos a modificacao MAIS ANTIGA entre os arquivos alterados:
    e ela que diz ha quanto tempo esse trabalho espera. A mais recente diria so
    que o dono digitou algo agora, que nao e a pergunta.
    """
    mais_antigo = None
    for linha in sujos:
        caminho = linha[3:].strip()
        if " -> " in caminho:                   # renomeado: interessa o destino
            caminho = caminho.split(" -> ")[-1]
        caminho = caminho.strip('"')
        try:
            m = (repo / caminho).stat().st_mtime
        except OSError:
            continue
        mais_antigo = m if mais_antigo is None else min(mais_antigo, m)
    if mais_antigo is None:
        return None
    return max(0, int((AGORA.timestamp() - mais_antigo) // 86400))


def nome_do_db(caminho) -> str:
    """O nome de arquivo que o codebase-memory-mcp usa para este caminho.

    C:\\dev\\repos\\dents  ->  C-dev-repos-dents
    """
    return str(caminho).replace(":", "").replace("\\", "-").replace("/", "-")


def coleta_grafo(repo, cache=None) -> dict:
    """Idade do indice do grafo de codigo, pela data do .db no cache.

    O casamento e pelo CAMINHO INTEIRO, nao pelo nome da pasta. Casar por sufixo
    ("termina em -medconsultoria") pega tambem o workspace-medconsultoria, e a
    ordem em que o glob devolve arquivo e a do sistema de arquivos, nao a
    alfabetica: o painel diria "indexado ha 1 dia" para um repo nunca indexado.
    Medido em 24/08/2026: dois arquivos casavam com "medconsultoria".
    """
    cache = cache or CACHE_GRAFO
    alvo = cache / (nome_do_db(repo) + ".db")
    if not alvo.is_file():
        return {"indexado": False, "dias": None}
    dias = int((AGORA.timestamp() - alvo.stat().st_mtime) // 86400)
    return {"indexado": True, "dias": max(0, dias)}


def coleta_memoria_crlf(repo: Path) -> list:
    """Arquivos de memoria gravados com quebra de linha do Windows.

    Falha calada e cara: em CRLF o harness ignora o frontmatter e a memoria
    NUNCA carrega. Nada na tela avisa. So um varredor externo descobre.
    """
    slug = str(repo).replace("\\", "-").replace("/", "-").replace(":", "-")
    pasta = PROJETOS_CLAUDE / slug / "memory"
    if not pasta.is_dir():
        return []
    fora = []
    for md in sorted(pasta.glob("*.md")):
        # MEMORY.md fica de fora. O motivo da regra e "em CRLF o harness ignora
        # o frontmatter e a memoria nunca carrega" — e este arquivo, por
        # especificacao, NAO TEM frontmatter: e o indice, uma linha por memoria.
        # Nao ha cabecalho para ser ignorado, logo nao ha falha a apontar.
        # Conferido em 25/08/2026: dos 13 .md desta pasta, e o unico sem `---`.
        if md.name == "MEMORY.md":
            continue
        try:
            if b"\r\n" in md.read_bytes()[:4096]:
                fora.append(md.name)
        except OSError:
            pass
    return fora


# Nome de variavel de ambiente de verdade: comeca com letra ou _, no maximo 64
# caracteres. O limite nao e cosmetico — ver o comentario em _chaves_env.
CHAVE_ENV = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]{0,63})\s*=")


def _chaves_env(caminho: Path) -> set:
    """So os NOMES das variaveis. Nenhum pedaco de valor pode sair daqui.

    VAZAMENTO ENCONTRADO NA REVISAO DE 24/08/2026, antes de ir para a main:
    ler linha a linha nao basta. Um valor multilinha entre aspas — chave RSA,
    certificado, credencial de service account — tem linhas base64 no miolo, e
    uma linha base64 sem "+" nem "/" que termine em "=" (o caso NORMAL da ultima
    linha de um bloco PEM) casava com a expressao como se fosse nome de variavel.
    O pedaco da chave ia parar no banco, na tela e no botao "Copiar as
    diferencas" — ou seja, o proprio fluxo desenhado tirava o segredo da maquina.

    Duas travas, e as duas sao necessarias:
      1. enquanto um valor entre aspas nao fechar, TODA linha e pulada;
      2. o nome tem no maximo 64 caracteres (base64 vazado vinha bem maior).
    """
    try:
        texto = caminho.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()

    chaves, aspa_aberta = set(), None
    for linha in texto.splitlines():
        if aspa_aberta:                       # ainda dentro de um valor multilinha
            if aspa_aberta in linha:
                aspa_aberta = None
            continue
        m = CHAVE_ENV.match(linha)
        if not m:
            continue
        chaves.add(m.group(1))
        resto = linha[m.end():].lstrip()
        if resto[:1] in ('"', "'") and resto.count(resto[0]) < 2:
            aspa_aberta = resto[0]            # abriu aspas e nao fechou nesta linha
    return chaves


def coleta_env_drift(repo: Path) -> dict:
    real, exemplo = repo / ARQ_SEGREDO, repo / ARQ_EXEMPLO
    if not (real.is_file() and exemplo.is_file()):
        return {"faltando": [], "sobrando": []}
    a, b = _chaves_env(real), _chaves_env(exemplo)
    return {"faltando": sorted(a - b)[:20], "sobrando": sorted(b - a)[:20]}


# --------------------------------------------------------------------------- git
def coleta_git(repo: Path) -> dict:
    if not (repo / ".git").exists():
        return {"versionado": False}

    # Sentinela. Se ATE ISTO falhou, o git nao respondeu por este repo — e
    # tudo que viesse depois seria zero inventado, nao zero medido. Melhor a
    # tela dizer "nao consegui medir" do que jurar "arvore limpa".
    ok, branch = executa(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"])
    if not ok:
        return {"versionado": True, "medido": False}

    sujos = [l for l in git(repo, "-c", "core.quotepath=false",
                            "status", "--porcelain").splitlines() if l.strip()]

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

    remoto = git(repo, "remote", "get-url", "origin")
    slug = None
    if remoto:
        m = re.search(r"[:/]([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?$", remoto)
        slug = m.group(1) if m else None

    return {
        "versionado": True,
        "medido": True,
        "branch": branch,
        "sujos": len(sujos),
        "sujos_lista": [s.strip() for s in sujos[:8]],
        "sujos_dias": idade_do_mais_antigo(repo, sujos),
        "tem_remoto": bool(remoto),
        "remoto_slug": slug,
        # So o NOME do arquivo entra na conta: o conteudo nunca e lido. Ter o
        # arquivo de variaveis no disco e o certo; te-lo no historico e o erro.
        "env_versionado": bool(git(repo, "ls-files", "--", ARQ_SEGREDO).strip()),
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
            if EH_TESTE.search(nome):
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
        # Quanto do projeto e LOGICA, e nao tela. E o que decide se cobrar
        # teste automatizado faz sentido: site de HTML e CSS e isento.
        "linhas_testaveis": sum(v for n, v in linguagens.items()
                                if n in LINGUAGENS_TESTAVEIS),
    }


# ---------------------------------------------------------------------- prontidao
def existe(repo: Path, *padroes) -> bool:
    return any(any(repo.glob(p)) for p in padroes)


def tem_ci(r: Path) -> bool:
    return existe(r, ".github/workflows/*.yml", ".github/workflows/*.yaml")


def tem_deploy(r: Path) -> bool:
    return any(re.search(r"deploy|publish|release", p.name, re.I)
               for p in r.glob(".github/workflows/*"))


def tem_docker(r: Path) -> bool:
    return existe(r, "Dockerfile", "docker-compose*.yml", "docker-compose*.yaml",
                  "compose.yml", "compose.yaml")


def tem_exemplo(r: Path) -> bool:
    return existe(r, ARQ_EXEMPLO, "*/" + ARQ_EXEMPLO, "apps/*/" + ARQ_EXEMPLO)


# Limiares da regua, num lugar so — sao o que o dono vai querer girar primeiro.
LIMIAR_DOCS = 100        # abaixo de 100 arquivos, um README honesto basta
LIMIAR_TESTES = 500      # linhas em linguagem com logica; abaixo disso e tela


# A REGUA. Cinco colunas: chave, rotulo, peso, TESTE (passou?) e APLICA (cabe
# cobrar deste projeto?). `aplica=None` significa "cabe cobrar de todo mundo".
#
# A quinta coluna e o conserto de um defeito medido em 24/08/2026: a regua era
# uma so para os 17 projetos, e descontava de cada um o que ele nao tinha
# motivo para ter. O proprio HUB tirava 64% por nao ter contêiner, arquivo de
# variaveis nem publicacao — tres coisas que ele nunca vai ter, por decisao.
# Nota que cobra o impossivel nao mede nada: so ensina o dono a ignora-la.
#
# Regra dura: o que NAO se aplica sai do denominador. Nao vira ponto de graca
# (isso inflaria a nota) nem falta (isso e o defeito antigo) — some da conta.
# Criterios cujo veredito depende de uma resposta do git. Se o git nao
# respondeu, eles nao podem ser julgados — e julgar assim mesmo e o pior
# caminho: "segredo" leria uma chave ausente, `not None` daria True e o
# painel CONCEDERIA o ponto de seguranca sem ter olhado o historico.
CRITERIOS_QUE_PEDEM_GIT = {"git_limpo", "ci", "segredo"}

CRITERIOS = [
    ("readme", "README", 1,
     lambda c: existe(c["repo"], "README.md", "readme.md"),
     None),

    ("git_limpo", "Árvore limpa e enviada", 1,
     lambda c: c["g"].get("sujos", 1) == 0 and c["g"].get("ahead", 1) == 0,
     lambda c: bool(c["g"].get("versionado"))),

    # CI so faz sentido onde ha GitHub para roda-la.
    ("ci", "CI configurada", 2,
     lambda c: tem_ci(c["repo"]),
     lambda c: bool(c["g"].get("versionado")) and bool(c["g"].get("tem_remoto"))),

    # Regra da casa: CSS, layout e texto de tela sao isentos de TDD. Site
    # estatico nao devia perder 2 pontos por nao ter suite de teste.
    ("testes", "Testes automatizados", 2,
     lambda c: c["arq"].get("arquivos_teste", 0) > 0,
     lambda c: c["arq"].get("linhas_testaveis", 0) >= LIMIAR_TESTES),

    # "Devia ter contêiner" e o dono quem diz, no casos.json — ou o disco, se o
    # projeto ja tem Dockerfile. Nao e uma virtude universal.
    ("docker", "Docker / compose", 1,
     lambda c: tem_docker(c["repo"]),
     lambda c: bool(c["caso"].get("containers")) or tem_docker(c["repo"])),

    ("env_exemplo", "Exemplo de variáveis", 1,
     lambda c: c["tem_exemplo"],
     lambda c: c["tem_env"] or c["tem_exemplo"]),

    # So cobra publicacao de quem publica: tem endereco de producao declarado,
    # ou ja tem o workflow. Projeto de gaveta nao deve 2 pontos a ninguem.
    #
    # "DECLARADO" passou a incluir o endereco que a tela gravou (etapa B2), e
    # nao so o do `casos.json`. Sem isto, digitar o endereco na tela nao fazia
    # a regra enxergar nada, e a pessoa via o painel ignorar o que ela acabara
    # de dizer — calado, que e a pior forma.
    ("deploy", "Workflow de deploy", 2,
     lambda c: tem_deploy(c["repo"]),
     lambda c: bool(c["caso"].get("url_prod")) or tem_deploy(c["repo"])),

    ("docs", "Pasta docs/", 1,
     lambda c: (c["repo"] / "docs").is_dir(),
     lambda c: c["arq"].get("arquivos", 0) >= LIMIAR_DOCS),

    ("gitignore", ".gitignore", 1,
     lambda c: (c["repo"] / ".gitignore").is_file(),
     lambda c: bool(c["g"].get("versionado"))),

    # O criterio antigo reprovava a EXISTENCIA do arquivo de variaveis, com o
    # peso mais alto da regua — e derrubava 6 dos 17 projetos por fazerem o
    # certo. Local e de mentira: ter o arquivo com senha de teste e o esperado.
    # O risco real e ele estar dentro do historico do git, e e isso que se mede.
    ("segredo", "Segredo fora do histórico", 2,
     lambda c: not c["g"].get("env_versionado"),
     lambda c: c["tem_env"] and bool(c["g"].get("versionado"))),
]


def _seguro(f, ctx) -> bool:
    """Criterio que explode nao pode derrubar a coleta do projeto inteiro."""
    try:
        return bool(f(ctx))
    except Exception:
        return False


def coleta_prontidao(repo: Path, g: dict, arq: dict, caso: dict | None = None) -> dict:
    """Nota de prontidao, cobrando de cada projeto so o que cabe a ele.

    `caso` e a entrada do projeto no casos.json. A palavra final e do dono: a
    chave "prontidao" de la liga (true) ou desliga (false) qualquer criterio,
    passando por cima da deteccao automatica nos dois sentidos.
    """
    caso = caso or {}
    ctx = {
        "repo": repo, "g": g, "arq": arq, "caso": caso,
        "tem_env": _seguro(lambda _: (repo / ARQ_SEGREDO).exists(), None),
        "tem_exemplo": _seguro(lambda _: tem_exemplo(repo), None),
    }
    manual = caso.get("prontidao") or {}

    sem_medida = bool(g.get("versionado")) and not g.get("medido")
    nao_medido = []
    itens = []
    for chave, rotulo, peso, teste, aplica in CRITERIOS:
        if sem_medida and chave in CRITERIOS_QUE_PEDEM_GIT:
            nao_medido.append(chave)
            itens.append({"chave": chave, "rotulo": rotulo, "peso": peso,
                          "aplica": False, "ok": False, "manual": False,
                          "nao_medido": True})
            continue
        if chave in manual:
            vale = bool(manual[chave])
        elif aplica is None:
            vale = True
        else:
            vale = _seguro(aplica, ctx)
        itens.append({
            "chave": chave, "rotulo": rotulo, "peso": peso,
            "aplica": vale, "nao_medido": False,
            "ok": _seguro(teste, ctx) if vale else False,
            "manual": chave in manual,
        })

    total = sum(i["peso"] for i in itens if i["aplica"])
    feito = sum(i["peso"] for i in itens if i["aplica"] and i["ok"])
    return {
        "itens": itens, "pontos": feito, "total": total,
        # Quais criterios ficaram SEM VEREDITO. Lista vazia = a nota e inteira.
        "nao_medido": nao_medido,
        # total 0 = o dono desligou tudo. Nada cobrado, nada devendo.
        "pct": round(100 * feito / total) if total else 100,
    }


# --------------------------------------------------------------------- projecoes
def projecao(g: dict, pr: dict) -> dict:
    """Velocidade recente, tendencia e prazo estimado para fechar as lacunas.

    Metodo, declarado na tela: commits/semana das ultimas 4 semanas contra as 12
    anteriores. O prazo assume ~4 commits de trabalho por ponto de prontidao
    faltante, dividido pela velocidade atual. E estimativa, nao promessa.
    """
    if not g.get("versionado"):
        return {"status": "sem_git", "riscos": ["fora do controle de versão"], "tendencia": "sem git"}
    if not g.get("medido"):
        return {"status": "nao_medido", "tendencia": "não medido",
                "riscos": ["não consegui medir o git deste projeto"]}

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
    if not g.get("medido"):
        return "Não medido"
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


# ----------------------------------------------------------------------- esteira
FASES_ESTEIRA = [
    ("briefing", "Briefing"), ("spec", "Spec"),
    ("design", "Design"), ("verificacao", "Verificação"),
]


def coleta_esteira(repo: Path) -> list:
    """Le docs/esteira/<slug>/ e diz que fases ja produziram artefato.

    Nao valida contrato: so registra o que existe em disco, que e onde o estado
    da esteira mora.
    """
    base = repo / "docs" / "esteira"
    if not base.is_dir():
        return []
    trabalhos = []
    for pasta in sorted(base.iterdir()):
        if not pasta.is_dir():
            continue
        fases = []
        for arquivo, rotulo in FASES_ESTEIRA:
            alvo = pasta / f"{arquivo}.md"
            fases.append({"rotulo": rotulo, "ok": alvo.is_file(),
                          "linhas": alvo.read_text(encoding="utf-8", errors="replace").count("\n")
                                    if alvo.is_file() else 0})
        feitas = sum(1 for f in fases if f["ok"])
        if not feitas:
            continue
        trabalhos.append({
            "slug": pasta.name,
            "fases": fases,
            "feitas": feitas,
            "atual": next((f["rotulo"] for f in fases if not f["ok"]), "concluída"),
        })
    return trabalhos


def coleta_documentacao(repo: Path):
    """Os criterios de aceitacao documentados no repositorio, ou `None`.

    `None` quer dizer "nao consegui ler", e o chamador OMITE a chave: o painel
    mostra "sem dados", que e outra coisa que "sem documentacao" (que e a
    resposta `{"documentos": []}`). Zerar uma leitura que falhou apagaria o
    problema real — a Lei 2 do painel. O formato, os tetos (o JSON da chave
    nunca passa de 40 KiB, porque o servidor descarta o projeto INTEIRO acima
    de 64 KiB) e a lista de provas moram em `documentos.py`.
    """
    try:
        return documentos.ler_projeto(repo)
    except Exception:                      # noqa: BLE001 — medir vale mais
        return None


# ------------------------------------------------------------------ infra ao vivo
def coleta_docker(executor=None) -> list | None:
    """Os conteineres de pe. None quando NAO DEU para perguntar ao Docker.

    Lista vazia e None dizem coisas opostas: vazia e "perguntei, nao ha
    nenhum"; None e "o Docker nao respondeu". Sem essa diferenca, Docker
    desligado virava "nada no ar" na tela — indistinguivel de aplicacao
    realmente derrubada.
    """
    executor = executor or executa
    fmt = ('{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}\t'
           '{{.Label "com.docker.compose.project"}}')
    ok, saida = executor(["docker", "ps", "--format", fmt], timeout=30)
    if not ok:
        return None
    itens = []
    for linha in saida.splitlines():
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


def _uteis(portas) -> list:
    return sorted({p for p in portas if 1024 < p < 65536})


def portas_do_proc(texto: str) -> set:
    """As portas em LISTEN dentro de um /proc/net/tcp (ou tcp6) do Linux.

    Formato de cada linha: `sl local_address:PORTA rem:PORTA st ...`, tudo em
    hexadecimal. `st` 0A e TCP_LISTEN; qualquer outro estado e conexao de
    passagem, nao servico de pe. Linha estragada nao derruba a leitura: uma
    porta a menos e ruim, um coletor morto de minuto em minuto e pior.
    """
    portas = set()
    for linha in texto.splitlines():
        campos = linha.split()
        if len(campos) < 4 or campos[3].upper() != "0A":
            continue
        try:
            portas.add(int(campos[1].rsplit(":", 1)[1], 16))
        except (IndexError, ValueError):
            continue
    return portas


def portas_escutando():
    """Quem esta escutando nesta maquina. None quando NAO DEU para medir.

    None e vazio dizem coisas opostas e o painel depende da diferenca: vazio e
    "medi, nao ha ninguem"; None e "nao consegui medir". Ate 26/08/2026 esta
    funcao so sabia perguntar ao PowerShell e, fora do Windows, devolvia vazio
    em silencio — e o painel jurava que todo projeto estava fora do ar.
    """
    if sys.platform.startswith("win"):
        saida = sh(["powershell", "-NoProfile", "-Command",
                    "Get-NetTCPConnection -State Listen | "
                    "Select-Object -ExpandProperty LocalPort -Unique | Sort-Object"], timeout=30)
        if not saida:
            return None
        return _uteis(int(l) for l in saida.split() if l.strip().isdigit())

    achou = False
    portas = set()
    for arquivo in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            portas |= portas_do_proc(arquivo.read_text(encoding="utf-8", errors="replace"))
            achou = True
        except OSError:
            continue
    return _uteis(portas) if achou else None


def deve_testar(porta: int, portas) -> bool:
    """Vale abrir conexao nesta porta? Sem lista (None), vale sempre.

    Nao saber nao e dizer nao: quando a medicao falhou, quem decide e a conexao
    de verdade, que funciona nos dois sistemas.
    """
    return portas is None or porta in portas


def porta_viva(porta: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=0.4):
            return True
    except OSError:
        return False


# ------------------------------------------------------------------------- main
def medir() -> dict:
    """MEDE A MAQUINA E DEVOLVE O RESULTADO. Nao escreve em lugar nenhum.

    Esta funcao era o comeco do `main()`, e saiu de la na etapa 11 por um
    motivo so: agora ha DOIS destinos para a mesma medicao — o `hub.db`
    desta maquina (o `main()` daqui) e um DERVS remoto (`agente/enviar.py`).
    Medir e gravar eram a mesma funcao, e o agente teria de copiar as ~600
    linhas que medem projeto. Copia divide-se em duas versoes no dia em que
    uma for corrigida, e a errada passa calada.

    OS AVISOS VOLTAM NA ESTRUTURA, e nao em `print`. Quem chama por HTTP nao
    tem stdout para ler: "a raiz nao existe" tem de chegar ao outro lado, ou
    o painel remoto mostra "0 projetos pendentes" com cara de boa noticia.
    Mesma familia de defeito de `7b4221c`/`3f5aa40`/`c50fe1d`: vazio e None
    dizem coisas opostas, e aqui `docker_mudo` e `portas_mudas` guardam a
    diferenca explicitamente.
    """
    casos = json.loads(CASOS.read_text(encoding="utf-8")) if CASOS.exists() else {}
    containers = coleta_docker()
    docker_mudo = containers is None
    containers = containers or []
    portas = portas_escutando()
    abertos = abertos_no_editor()

    # Os enderecos que a tela gravou (etapa B2), lidos UMA vez. Falha fechada:
    # banco sem a tabela, ou sem conta local, cai em vazio e o `casos.json`
    # continua valendo — nunca um erro no meio da medicao.
    try:
        con_end = banco.conectar()
        try:
            enderecos_gravados = banco.um_endereco_por_projeto(
                banco.conta_local(con_end), con=con_end)
        finally:
            con_end.close()
    except Exception:                      # noqa: BLE001 — medir vale mais
        enderecos_gravados = {}

    projetos = []
    for repo in pastas_de_projeto():
        g = coleta_git(repo)
        arq = coleta_arquivos(repo)
        # O caso vem ANTES da nota: e ele que diz se o projeto tem contêiner e
        # se publica, e sem isso a regua volta a cobrar de todos a mesma coisa.
        caso = casos.get(repo.name, {})
        # O endereco gravado pela tela entra no `caso` ANTES das regras, e
        # vence o do arquivo — a mesma ordem de `coletar_github`. Duas ordens
        # diferentes para o mesmo dado sao duas verdades, e a que diverge e
        # sempre a que ninguem le.
        if enderecos_gravados.get(repo.name):
            caso = dict(caso, url_prod=enderecos_gravados[repo.name])
        pr = coleta_prontidao(repo, g, arq, caso)

        alvos = [t.lower() for t in caso.get("containers", [])]
        meus = [c for c in containers
                if (alvos and any(t in c["nome"].lower() or t in (c["projeto"] or "").lower()
                                  for t in alvos))
                or repo.name.lower().replace("-", "") == (c["projeto"] or "").lower().replace("-", "")]

        documentacao = coleta_documentacao(repo)
        projetos.append({
            "nome": repo.name,
            "caminho": str(repo),
            "casos_json": str(CASOS),
            "titulo": caso.get("titulo", repo.name),
            "resumo": caso.get("resumo", ""),
            "caso": caso.get("caso", {}),
            "caso_vazio": not (caso.get("resumo") or caso.get("caso")),
            "url_prod": caso.get("url_prod"),
            "criticidade": caso.get("criticidade", "normal"),
            "grafo": coleta_grafo(repo),
            "memoria_crlf": coleta_memoria_crlf(repo),
            "env_drift": coleta_env_drift(repo),
            "compose": existe(repo, "docker-compose*.yml", "docker-compose*.yaml",
                              "compose.yml", "compose.yaml"),
            "containers_esperados": caso.get("containers", []),
            "aberto_no_editor": None if abertos is None else (nome_da_marca(repo) in abertos),
            "git": g,
            "arquivos": arq,
            "prontidao": pr,
            "projecao": projecao(g, pr),
            "fase": fase(g, pr),
            "esteiras": coleta_esteira(repo),
            "containers": meus,
            "portas": [{"porta": p, "vivo": deve_testar(p, portas) and porta_viva(p)}
                       for p in caso.get("portas", [])],
        })
        # A chave so existe quando a leitura deu certo: ausente e "sem dados".
        if documentacao is not None:
            projetos[-1]["documentacao"] = documentacao

    avisos = avisos_das_raizes()
    if portas is None:
        avisos.append("nao consegui listar as portas em uso; o 'no ar' de cada projeto saiu so da conexao direta.")
    if docker_mudo:
        avisos.append("o docker nao respondeu; a lista de conteineres esta MUDA, e nao vazia.")
    return {
        "projetos": projetos,
        "infra": {
            "containers": containers,
            "docker_mudo": docker_mudo,
            "quebrados": [c["nome"] for c in containers if c["reiniciando"]],
            "portas": portas,
        },
        "portas_mudas": portas is None,
        "avisos": avisos,
    }


def main():
    """A coleta LOCAL: mede e grava no `hub.db` desta maquina."""
    medicao = medir()
    projetos, infra = medicao["projetos"], medicao["infra"]
    docker_mudo, containers = infra["docker_mudo"], infra["containers"]

    # Uma linha por projeto, com carimbo proprio: quando a coleta de um repo
    # falhar, os outros continuam com data honesta em vez de herdar a do lote.
    con = banco.conectar()
    try:
        dono = banco.conta_local(con)
        for pr in projetos:
            banco.gravar(pr["nome"], "local", pr, con, usuario_id=dono)
        banco.gravar(banco.INFRA, "local", infra, con, usuario_id=dono)
        # O commit e daqui: `gravar` so commita quando ABRIU a conexao, para nao
        # quebrar a transacao de quem chamou. Sem esta linha a coleta inteira
        # seria descartada no `close()` — em silencio.
        con.commit()
    finally:
        con.close()

    print(f"ok: {len(projetos)} projetos, "
          f"{'DOCKER MUDO' if docker_mudo else str(len(containers)) + ' containers'}"
          f" -> {banco.BANCO.name}")
    # A raiz sumida nao levanta erro: iterdir() nao roda e a lista fica so com os
    # avulsos. Sem este aviso o coletor imprime "ok: 1 projetos" e parece que deu
    # certo — foi o que aconteceu ao rodar em Linux pela primeira vez, onde o
    # caminho do Windows obviamente nao existe. Os avisos vem de `medir()`: um
    # so lugar decide o que e digno de aviso, e o agente carrega os MESMOS para
    # o painel remoto.
    for aviso in medicao["avisos"]:
        print("AVISO: " + aviso)
    return 0


if __name__ == "__main__":
    sys.exit(main())
