# -*- coding: utf-8 -*-
"""A barreira da sessao desacompanhada.

O botao "Resolver" tinha uma pessoa olhando a tela. A fila nao tem ninguem, e
por isso precisa de trava em CODIGO, e nao de instrucao no texto do pedido:
instrucao em texto e sugestao, nao trava (mesmo principio de `fila.py`).

Este modulo e o porteiro do Bash da sessao filha. Ele roda como hook PreToolUse
do proprio `claude` (ver `execucao.montar_comando`): recebe o evento por stdin,
sai com 0 para deixar passar e com 2 para BARRAR, escrevendo o motivo no stderr
— e o codigo 2 e o unico que o Claude Code trata como veto.

O QUE ELE E, E O QUE ELE NAO E. Ele e a terceira barreira, nao a primeira:

  1a  a copia nao alcanca o GitHub: e um `git clone` local com o `origin`
      REMOVIDO, e nao mais um `git worktree` que compartilhava o `.git` e o
      remoto ja autenticado do projeto de verdade (execucao.criar_copia).
  2a  a sessao filha nao carrega ajuste de ninguem: `--setting-sources ""`
      derruba tanto os hooks do `~/.claude` do dono quanto — e este era o furo
      grande — o `.claude/settings.json` do repositorio que ela foi consertar,
      que e justamente conteudo de estranho.
  3a  esta lista, que barra o comando antes de ele rodar.

Dito com todas as letras, porque documentacao que promete demais e pior que
nenhuma: rodar teste E rodar codigo arbitrario. A propria suite do projeto e
codigo de terceiro executando com todos os poderes do usuario. Esta lista
encarece e estreita o caminho; ela nao transforma a maquina num cofre. O que de
fato impede o estrago de sair da copia sao as duas primeiras barreiras.
"""
from __future__ import annotations

import json
import re
import sys

# --------------------------------------------------------------- as listas

# Lista BRANCA de programas. Sai daqui quem nao aparece: recusar o
# desconhecido e o unico jeito de a lista nao envelhecer para o lado errado.
#
# `bash`, `sh`, `powershell`, `cmd`, `env`, `xargs` e `npx` NAO estao aqui de
# proposito: todos executam um segundo comando que esta barreira ja nao leria.
PERMITIDOS = {
    "git", "python", "python3", "py", "pytest", "node", "npm", "pnpm", "yarn",
    "dotnet", "go", "cargo", "ruff", "black", "flake8", "mypy", "tsc",
    "jest", "vitest", "eslint", "prettier",
    "ls", "dir", "cat", "type", "head", "tail", "sed", "grep", "rg", "find",
    "wc", "sort", "uniq", "cut", "tr", "diff", "echo", "printf", "pwd", "cd",
    "mkdir", "touch", "cp", "mv", "rm", "true", "false", "which", "basename",
    "dirname", "date",
}

# Programas barrados COM NOME PROPRIO. Sao redundantes com a lista branca — se
# nao estao la, ja nao passariam. Existem para a mensagem de recusa dizer
# "isto sai da maquina" em vez de "programa desconhecido", que e o que o
# proximo humano precisa ler para entender o veto.
SAEM_DA_MAQUINA = {
    "curl", "wget", "ssh", "scp", "sftp", "rsync", "nc", "ncat", "netcat",
    "telnet", "ftp", "gh", "hub", "glab", "aws", "az", "gcloud", "heroku",
    "vercel", "netlify", "docker", "kubectl", "terraform", "ansible",
    "pip", "pip3", "poetry", "pipenv", "conda", "brew", "choco", "winget",
    "apt", "apt-get", "npx", "bunx", "deno", "certutil", "bitsadmin",
    "invoke-webrequest", "iwr",
}

# Subcomando barrado, por programa. `git push` e o caso que originou tudo isto.
# `git config` esta aqui porque um `git config diff.noprefix true` cegaria para
# sempre a trava que le o diff (ver execucao.diff_para_a_trava).
SUBCOMANDO_BARRADO = {
    "git": {"push", "remote", "clone", "fetch", "pull", "submodule", "daemon",
            "filter-branch", "config", "credential", "send-email", "svn",
            "request-pull", "instaweb", "archive"},
    "npm": {"install", "i", "ci", "add", "publish", "exec", "login", "adduser",
            "token", "audit", "update", "link"},
    "pnpm": {"install", "i", "add", "publish", "dlx", "update", "link"},
    "yarn": {"install", "add", "publish", "dlx", "upgrade", "link"},
    "dotnet": {"nuget", "restore", "publish", "tool"},
    "go": {"get", "install", "mod"},
    "cargo": {"publish", "install", "login", "add", "update", "fetch"},
}

# `python -m X`: so estes X. Sem isto, `python -m pip install` e `python -m
# http.server` entrariam pela porta que existe para o `python -m pytest`.
MODULOS_OK = {"pytest", "unittest", "compileall", "json.tool", "venv"}

# Bandeira que faz o programa virar interpretador de texto solto — e ai a
# barreira estaria lendo `python` e deixando passar qualquer coisa.
BANDEIRA_BARRADA = {
    "python": {"-c"}, "python3": {"-c"}, "py": {"-c"},
    "node": {"-e", "--eval", "-p", "--print"},
    "find": {"-exec", "-execdir", "-ok", "-okdir"},
    "sed": {"-i", "--in-place"},
}

# O unico caminho absoluto que passa. `2>/dev/null` aparece em quase todo
# comando honesto; barra-lo seria transformar a barreira em pedra no caminho.
ABSOLUTO_TOLERADO = {"/dev/null", "nul", "NUL"}

# Pasta que a sessao nao escreve nem que esteja dentro da copia. `.git/hooks`
# transforma qualquer `git commit` futuro em execucao de codigo.
PASTAS_PROIBIDAS = (".git/", ".git\\", ".ssh", ".aws", ".claude", "id_rsa",
                    "credentials")


# ------------------------------------------------------- separar o comando

OPERADORES = (";", "&&", "||", "|", "&", "\n")


def _fatias(comando: str) -> list:
    """Quebra o comando em pedacos executaveis, respeitando aspas.

    Inclui o conteudo de `$( )` e de crase como pedacos proprios: substituicao
    de comando e um comando, e um que a leitura ingenua nao veria.
    """
    texto = comando or ""
    fatias, atual = [], []
    aspas = ""
    i = 0
    while i < len(texto):
        c = texto[i]
        if aspas:
            atual.append(c)
            if c == aspas:
                aspas = ""
            i += 1
            continue
        if c in ("'", '"'):
            aspas = c
            atual.append(c)
            i += 1
            continue
        if c == "$" and texto[i + 1:i + 2] == "(":
            fim = _fecha_parentese(texto, i + 1)
            fatias.extend(_fatias(texto[i + 2:fim]))
            i = fim + 1
            continue
        if c == "`":
            fim = texto.find("`", i + 1)
            fim = fim if fim != -1 else len(texto)
            fatias.extend(_fatias(texto[i + 1:fim]))
            i = fim + 1
            continue
        casou = next((op for op in OPERADORES if texto.startswith(op, i)), None)
        if casou:
            fatias.append("".join(atual))
            atual = []
            i += len(casou)
            continue
        atual.append(c)
        i += 1
    fatias.append("".join(atual))
    return [f.strip() for f in fatias if f.strip()]


def _fecha_parentese(texto: str, abre: int) -> int:
    """Indice do `)` que fecha o `(` em `abre`. Fim do texto se nao fechar."""
    nivel = 0
    for i in range(abre, len(texto)):
        if texto[i] == "(":
            nivel += 1
        elif texto[i] == ")":
            nivel -= 1
            if nivel == 0:
                return i
    return len(texto)


def _palavras(fatia: str) -> list:
    """Tokens da fatia, com as aspas de fora retiradas."""
    cru = re.findall(r"""'[^']*'|"[^"]*"|\S+""", fatia)
    saida = []
    for p in cru:
        if len(p) >= 2 and p[0] == p[-1] and p[0] in ("'", '"'):
            p = p[1:-1]
        saida.append(p)
    return saida


def _programa(palavras: list) -> str:
    """O nome do programa, sem caminho, sem extensao, em minusculas.

    Pula atribuicao de variavel (`FOO=1 git status`), que e prefixo e nao
    programa.
    """
    for p in palavras:
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", p):
            continue
        nome = re.split(r"[\\/]", p)[-1].lower()
        return re.sub(r"\.(exe|cmd|bat|ps1)$", "", nome)
    return ""


def _argumentos(palavras: list) -> list:
    """As palavras depois do programa."""
    for i, p in enumerate(palavras):
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", p):
            return palavras[i + 1:]
    return []


# --------------------------------------------------------- regras de caminho

_ABSOLUTO = re.compile(r"^(/|~|[A-Za-z]:[\\/]|\\\\)")

# Trecho entre aspas, para poder apaga-lo antes de procurar operador de shell.
_ASPAS = re.compile(r"'[^']*'" + r'|"[^"]*"')


def caminho_suspeito(token: str) -> str:
    """"" se o caminho pode; senao o motivo. Vale para argumento e redirecao."""
    limpo = (token or "").strip().strip("'\"")
    if not limpo or limpo in ABSOLUTO_TOLERADO:
        return ""
    alvo = limpo.split("=", 1)[1] if re.match(r"^--?[A-Za-z][\w-]*=", limpo) else limpo
    if not alvo or alvo in ABSOLUTO_TOLERADO:
        return ""
    if "$HOME" in alvo or "%USERPROFILE%" in alvo or "%APPDATA%" in alvo:
        return "o caminho `%s` aponta para a pasta pessoal, fora da cópia" % alvo
    if _ABSOLUTO.match(alvo):
        return "o caminho `%s` é absoluto — a sessão só trabalha dentro da cópia" % alvo
    if re.split(r"[\\/]", alvo)[0] == ".." or "/../" in alvo or "\\..\\" in alvo:
        return "o caminho `%s` sai da cópia com `..`" % alvo
    baixo = alvo.lower()
    for proibida in PASTAS_PROIBIDAS:
        if proibida in baixo:
            return "o caminho `%s` toca `%s`, que a sessão não mexe" % (alvo, proibida)
    return ""


def _alvos_de_redirecao(fatia: str) -> list:
    """Os arquivos escritos por `>` e `>>` fora de aspas.

    Redirecao e a porta lateral: `echo x > ../.git/hooks/pre-commit` seria lido
    como um `echo` inocente por quem so olha o programa.
    """
    return re.findall(r">>?\s*([^\s;|&]+)", _ASPAS.sub(" ", fatia))


# ----------------------------------------------------------- a decisao

def vetar_bash(comando: str) -> str:
    """"" se o comando pode rodar; senao a frase que o dono e o Claude leem.

    Funcao PURA — entra texto, sai veredito. E por isso que ela custa quase
    nada para testar, e testada e o unico jeito de eu confiar nela.
    """
    for fatia in _fatias(comando):
        palavras = _palavras(fatia)
        if not palavras:
            continue
        programa = _programa(palavras)
        if not programa:
            continue
        if programa in SAEM_DA_MAQUINA:
            return ("`%s` fala com a rede ou com outra máquina. A sessão da fila "
                    "roda sem ninguém olhando e não faz isso." % programa)
        if programa not in PERMITIDOS:
            return ("`%s` não está na lista do que a sessão da fila pode rodar "
                    "sozinha." % programa)
        argumentos = _argumentos(palavras)
        motivo = _vetar_argumentos(programa, argumentos)
        if motivo:
            return motivo
        for token in argumentos:
            motivo = caminho_suspeito(token)
            if motivo:
                return motivo
        for alvo in _alvos_de_redirecao(fatia):
            motivo = caminho_suspeito(alvo)
            if motivo:
                return motivo
    return ""


def _vetar_argumentos(programa: str, argumentos: list) -> str:
    """Subcomando, bandeira perigosa e `python -m`."""
    barradas = BANDEIRA_BARRADA.get(programa, set())
    for a in argumentos:
        if a.split("=", 1)[0] in barradas:
            return ("`%s %s` faz o programa executar texto solto, e aí esta "
                    "barreira já não estaria lendo nada." % (programa, a))

    if programa in ("python", "python3", "py") and "-m" in argumentos:
        i = argumentos.index("-m")
        modulo = argumentos[i + 1] if i + 1 < len(argumentos) else ""
        if modulo not in MODULOS_OK:
            return ("`python -m %s` não está liberado; só %s."
                    % (modulo or "(vazio)", ", ".join(sorted(MODULOS_OK))))

    # TODA palavra solta e comparada, e nao so a primeira: `git -C pasta push`
    # tem "pasta" como primeiro nao-hifen, e um `next(...)` ingenuo deixaria o
    # `push` passar. O preco e recusar `git commit -m "push"`, e a mensagem de
    # recusa diz qual palavra foi — troca boa para o lado que erra fechando.
    barrados = SUBCOMANDO_BARRADO.get(programa, set())
    for a in argumentos:
        if a.startswith("-") or a.lower() not in barrados:
            continue
        if programa == "git" and a.lower() in ("push", "remote", "fetch",
                                               "pull", "clone"):
            return ("`git %s` alcança o repositório de verdade. Quem publica "
                    "é o painel, depois, com o diff já aprovado pelas travas." % a)
        return "`%s %s` não é permitido na sessão da fila." % (programa, a)
    return ""


def vetar_caminho(caminho: str) -> str:
    """A mesma regra de caminho, para o `file_path` do Write e do Edit."""
    return caminho_suspeito(caminho)


def decidir(evento: dict) -> str:
    """"" libera; qualquer outra coisa e o motivo da recusa."""
    ferramenta = (evento or {}).get("tool_name") or ""
    entrada = (evento or {}).get("tool_input") or {}
    if ferramenta == "Bash":
        return vetar_bash(entrada.get("command") or "")
    if ferramenta in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        return vetar_caminho(entrada.get("file_path") or "")
    return ""


def main(entrada=None, saida_erro=None) -> int:
    """O contrato do hook: 0 deixa passar, 2 barra e o stderr vira a explicacao.

    Erro de leitura BARRA. Porteiro que nao conseguiu ler o cracha nao abre a
    porta — mesmo criterio de `diff_para_a_trava`, que recusa quando nao
    conseguiu ler o diff.
    """
    if entrada is None and saida_erro is None:
        # Medido em 25/08/2026: sem isto o motivo chega na sessao filha como
        # "alcan?a o reposit?rio" — no Windows o stderr nasce em cp1252, e uma
        # recusa que o Claude nao consegue LER e uma recusa que ele nao entende.
        for fluxo in (sys.stdin, sys.stderr):
            if hasattr(fluxo, "reconfigure"):
                fluxo.reconfigure(encoding="utf-8", errors="replace")
    entrada = entrada if entrada is not None else sys.stdin
    saida_erro = saida_erro if saida_erro is not None else sys.stderr
    try:
        evento = json.loads(entrada.read() or "{}")
    except (ValueError, OSError) as e:
        saida_erro.write("barreira: nao consegui ler o evento (%s)\n" % e)
        return 2
    motivo = decidir(evento)
    if motivo:
        saida_erro.write("Barrado pela barreira da fila: %s\n" % motivo)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
