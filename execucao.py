# -*- coding: utf-8 -*-
"""O Claude dentro do painel — as decisoes do botao "Resolver".

Este modulo responde cinco perguntas, e so elas:

    qual comando roda    montar_comando()
    o que ele vai fazer  montar_prompt()
    em que pe esta       frase_de_status() / avancar() / classificar_falha()
    quanto custou        custo_do_evento() / em_reais()
    pode comecar?        pode_resolver() / decidir_pedido()

TUDO AQUI E PURO de proposito. Nada de subprocess, disco ou rede nesta parte —
a suite roda em ubuntu-latest, onde nao existe `claude`, nem `taskkill`, nem
`C:\\`. O I/O mora mais abaixo no arquivo, em funcoes que os testes nao chamam.

TRES MEDICOES FEITAS NESTA MAQUINA EM 24/08/2026 (claude 2.1.243) — nao suponha
o contrario sem medir de novo:

  1. `--bare` NAO funciona com o login do dono: responde "Not logged in". O
     login e por assinatura (OAuth) e --bare so aceita chave de API. O que
     funcionou foi --strict-mcp-config com um mcp-config vazio.
  2. `--max-budget-usd` NAO e cerca. Com teto 0,10 a execucao terminou em
     0,44548 (estouro de 4,5x). O botao "Parar" e a unica garantia real.
  3. O campo `subtype` do evento result NAO e confiavel: foi visto
     subtype:'success' junto de is_error:True. Leia is_error + terminal_reason.
"""
from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
from pathlib import Path

# Teto por execucao, em dolar. US$ 1 nao daria: medido em 24/08/2026, so LIGAR a
# sessao custa US$ 0,2256 num turno trivial sem MCP, e US$ 0,4455 herdando os
# MCPs da maquina. Nao e limite duro (ver medicao 2 no topo) — a tela precisa
# dizer que o teto e aproximado.
TETO_USD = 3.0

# Cotacao fixa no codigo, num lugar so (decisao do dono, 24/08/2026). Valor do
# fechamento de 21/08/2026: R$ 5,1417. Envelhece — atualize quando incomodar.
USD_BRL = 5.14

# Limite de turnos da sessao filha. Uma CI vermelha simples se resolve em muito
# menos; o numero existe para o laco que der errado nao rodar a noite inteira.
MAX_TURNOS = 40

# Lista branca: o que a sessao filha pode fazer sozinha, sem perguntar. Ela roda
# dentro de uma copia isolada, entao editar arquivo ali nao alcanca o projeto.
FERRAMENTAS_OK = ["Read", "Grep", "Glob", "Edit", "Write", "Bash", "TodoWrite"]

# Lista negra: vence a branca no `claude`. Sessao filha nao despacha sessao neta
# (custo sem teto) e nao navega na web (o prompt ja traz o contexto de que
# precisa; buscar na web e superficie de injecao a mais).
FERRAMENTAS_PROIBIDAS = ["Task", "WebFetch", "WebSearch"]

# Decisao do dono no portao de risco: prontuario sob LGPD fica fora da entrega 1.
# Comparacao sempre em minusculas.
PROJETOS_BLOQUEADOS = {"ajudei-saude"}

# As 7 frases da linha de status, literais do design.md. Ficam aqui, e nao no
# HTML, porque quem sabe em que pe a sessao esta e quem le os eventos.
FRASE_COPIA = "Preparando uma cópia isolada de %s"
FRASE_LENDO = "Lendo o repositório"
FRASE_TESTES = "Rodando os testes"
FRASE_CORRIGINDO = "Escrevendo a correção"
FRASE_TESTES_DE_NOVO = "Rodando os testes de novo"
FRASE_ABRINDO_PR = "Abrindo o pedido de alteração"
FRASE_PR_ABERTO = "Pedido de alteração aberto"

# Ciclo de vida, um recurso unico na maquina inteira. Estado em memoria no
# processo do servidor — sem tabela no banco, sem historico, sem retomada.
ESTADOS_TERMINAIS = ("ok", "falha", "parada_pelo_dono")

# Gabarito FECHADO do prompt. Os quatro %s sao, na ordem: projeto, regra, texto,
# detalhe — todos recalculados pelo servidor a partir do banco, NUNCA lidos do
# corpo do POST. E daqui que sai a aba "Resumo": a ultima instrucao manda a
# sessao escrever uma frase por arquivo, o que evita uma segunda chamada ao
# modelo so para resumir.
GABARITO = """Você está no repositório %s, numa cópia isolada e descartável dele.

O painel de projetos detectou esta pendência:

  regra: %s
  o que está acontecendo: %s
  detalhe: %s

Sua tarefa é corrigir a causa dessa pendência neste repositório.

Regras desta sessão, sem exceção:
1. Trabalhe só nesta cópia. Não mude nada fora dela.
2. Rode a suíte de testes do projeto antes e depois da sua correção.
3. Não faça `git push`, não abra pull request e não faça merge — quem publica
   é o painel, depois, com a sua mudança já commitada localmente.
4. Se a causa for maior do que uma correção pontual, pare e explique por quê,
   em vez de reescrever meio projeto.

Termine sua última mensagem com um resumo: **uma frase em português por arquivo
que você tocou**, no formato `caminho/do/arquivo.py — o que mudou e por quê`.
Se você não tocou em arquivo nenhum, diga isso em uma linha."""


# ---------------------------------------------------------------- parte pura


def montar_comando(prompt: str, teto_usd: float = TETO_USD,
                   turnos: int = MAX_TURNOS) -> list:
    """O argv exato da sessao filha. O prompt vai por ultimo, posicional.

    NAO acrescente --bare: foi medido e falha com "Not logged in" (ver topo).
    """
    return [
        "claude", "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--strict-mcp-config",
        "--mcp-config", '{"mcpServers":{}}',
        "--max-budget-usd", "%.2f" % teto_usd,
        "--max-turns", str(int(turnos)),
        "--allowedTools", ",".join(FERRAMENTAS_OK),
        "--disallowedTools", ",".join(FERRAMENTAS_PROIBIDAS),
        prompt,
    ]


def montar_prompt(pendencia: dict) -> str:
    """Gabarito fechado. So quatro campos da pendencia entram — nada mais."""
    return GABARITO % (
        pendencia.get("projeto", ""),
        pendencia.get("regra", ""),
        pendencia.get("texto", ""),
        pendencia.get("detalhe", "") or "(sem detalhe)",
    )


def pode_resolver(pendencia: dict) -> bool:
    """Ha o que resolver? Pendencia sem projeto (cota_actions) nao tem onde."""
    projeto = (pendencia.get("projeto") or "").strip()
    if not projeto:
        return False
    return projeto.lower() not in PROJETOS_BLOQUEADOS


def interpretar_linha(bruto):
    """Uma linha do stream-json -> dict, ou None. NUNCA levanta excecao.

    Uma excecao aqui mata a thread leitora e a tela congela para sempre. A saida
    real tem linha vazia, linha cortada pelo buffer e banner que nao e JSON.
    """
    if not bruto:
        return None
    try:
        valor = json.loads(bruto.strip())
    except (ValueError, TypeError, AttributeError):
        return None
    return valor if isinstance(valor, dict) else None


def _ferramentas_do_evento(evento: dict) -> list:
    """[(nome_da_ferramenta, comando_se_for_bash)] de um evento assistant."""
    conteudo = (evento.get("message") or {}).get("content")
    if not isinstance(conteudo, list):
        return []
    achados = []
    for bloco in conteudo:
        if isinstance(bloco, dict) and bloco.get("type") == "tool_use":
            entrada = bloco.get("input") or {}
            comando = entrada.get("command") if isinstance(entrada, dict) else ""
            achados.append((bloco.get("name") or "", str(comando or "")))
    return achados


def frase_de_status(evento: dict, frase_atual: str) -> str:
    """A frase em portugues que o dono le. Evento sem novidade nao muda nada."""
    tipo = evento.get("type")

    if tipo == "system":
        return FRASE_LENDO

    if tipo == "result":
        return FRASE_PR_ABERTO if not evento.get("is_error") else frase_atual

    for nome, comando in _ferramentas_do_evento(evento):
        baixo = comando.lower()
        if "gh pr create" in baixo:
            return FRASE_ABRINDO_PR
        if "test" in baixo or "pytest" in baixo:
            # "de novo" so depois de ter escrito alguma correcao — e a memoria
            # da sequencia, e ela vem da frase anterior, nao de um contador.
            if frase_atual in (FRASE_CORRIGINDO, FRASE_TESTES_DE_NOVO):
                return FRASE_TESTES_DE_NOVO
            return FRASE_TESTES
        if nome in ("Edit", "Write", "NotebookEdit"):
            return FRASE_CORRIGINDO

    return frase_atual


def avancar(estado: str, evento: dict) -> str:
    """Proximo estado. Le is_error + terminal_reason; IGNORA subtype (medicao 3)."""
    if estado in ESTADOS_TERMINAIS:
        return estado

    if evento.get("type") != "result":
        return "rodando"

    limpo = (not evento.get("is_error")
             and evento.get("terminal_reason") == "completed")
    return "ok" if limpo else "falha"


def classificar_falha(evento: dict):
    """(manchete, corpo) com a causa REAL. "Algo deu errado" e proibido."""
    razao = (evento.get("terminal_reason") or "").lower()
    texto = str(evento.get("result") or "").lower()

    if razao == "budget_exhausted":
        return ("Falhou: atingiu o teto de gasto",
                "Parou porque atingiu o teto de %s por execução, sem terminar a "
                "correção. A cópia isolada continua em disco para inspeção; nada "
                "foi enviado ao GitHub." % em_reais(TETO_USD))

    if "max_turns" in razao or "turn" in razao:
        return ("Falhou: não terminou a tempo",
                "A sessão chegou ao limite de tentativas sem terminar a correção. "
                "Isto costuma acontecer quando o problema é maior do que uma CI "
                "vermelha simples — vale olhar manualmente desta vez.")

    if "already exists" in texto or "pull request for branch" in texto:
        return ("Falhou: já existe um pedido de alteração aberto",
                "O GitHub recusou abrir outro pedido de alteração porque já existe "
                "um aberto para esta correção. Feche ou atualize aquele antes de "
                "tentar de novo.")

    if "fail" in texto or "falhou" in texto or "error" in texto:
        return ("Falhou: os testes continuam falhando",
                "A sessão tentou corrigir e rodou os testes de novo, mas eles "
                "continuam falhando. Veja o log abaixo para o erro exato.")

    # Quinta manchete, fora das quatro do design: `api_error` nao e nenhuma
    # delas, e escolher a mais parecida seria mentir com autoridade. Aqui o
    # motivo cru aparece na tela, feio e verdadeiro.
    return ("Falhou: a sessão terminou com erro",
            "A sessão terminou sem completar a correção. Motivo relatado pelo "
            "Claude Code: %s. O log abaixo tem a saída crua."
            % (evento.get("terminal_reason") or "não informado"))


def custo_do_evento(evento: dict, acumulado: float) -> float:
    """Custo em dolar ate agora. O `result` sobrescreve; o resto so aproveita.

    NAO ha tabela de precos aqui, de proposito: converter token em dolar por
    conta propria daria um numero que se mexe e esta errado. Se o evento nao
    trouxer custo, o valor fica parado — e a tela diz "estimativa".
    """
    bruto = evento.get("total_cost_usd")
    if isinstance(bruto, (int, float)) and not isinstance(bruto, bool):
        return float(bruto)
    return acumulado


def em_reais(usd: float) -> str:
    """0.2256 -> "R$ 1,16". Virgula decimal, duas casas, sempre."""
    try:
        valor = float(usd) * USD_BRL
    except (TypeError, ValueError):
        valor = 0.0
    return "R$ " + ("%.2f" % valor).replace(".", ",")


def decidir_pedido(execucao_atual, projeto_pedido: str) -> str:
    """A trava global, em forma testavel: "iniciar" | "mesma" | "recusada"."""
    if not execucao_atual or execucao_atual.get("estado") != "rodando":
        return "iniciar"
    em_curso = (execucao_atual.get("projeto") or "").lower()
    if em_curso == (projeto_pedido or "").lower():
        return "mesma"
    return "recusada"


def url_do_pr(saida):
    """A URL do pull request no stdout do `gh`. gh 2.78.0 nao tem --json aqui."""
    if not saida:
        return None
    achada = None
    for linha in str(saida).splitlines():
        limpa = linha.strip()
        if limpa.startswith("https://"):
            achada = limpa
    return achada


# ------------------------------------------------- a copia isolada: nomes puros


def id_curto(semente=None) -> str:
    """8 caracteres hexadecimais. Curto porque caminho no Windows morre em 260."""
    sorteio = random.Random(semente) if semente is not None else random.SystemRandom()
    return "%08x" % sorteio.randrange(16 ** 8)


def caminho_da_copia(base, projeto: str, id_: str) -> Path:
    """`base` e parametro para o teste rodar em ubuntu-latest com pasta temporaria."""
    return Path(base) / _so_o_seguro(projeto) / id_


def _so_o_seguro(bruto: str) -> str:
    """Minusculas, so letra/numero/hifen, sem hifen dobrado nem nas pontas."""
    limpo = []
    for c in (bruto or "").lower():
        limpo.append(c if (c.isascii() and (c.isalnum() or c == "-")) else "-")
    texto = re.sub(r"-{2,}", "-", "".join(limpo)).strip("-")
    return texto


def nome_do_ramo(regra: str, id_: str) -> str:
    """`ci_vermelha` + `a1b2c3d4` -> `hub/ci-vermelha-a1b2c3d4`.

    O nome do projeto NAO entra: o ramo ja nasce dentro do repositorio daquele
    projeto, entao repeti-lo so encompridaria o nome. (O plano da etapa 2 previa
    um terceiro parametro `projeto`; ele viraria argumento nunca usado.)
    """
    miolo = _so_o_seguro(regra) or "pendencia"
    return "hub/%s-%s" % (miolo, id_)


def mensagem_de_commit(pendencia: dict) -> str:
    """Primeira linha curta com tipo(escopo), corpo com o porque. Em portugues."""
    regra = pendencia.get("regra", "pendencia")
    projeto = pendencia.get("projeto", "")
    titulo = "fix(%s): resolve pendência apontada pelo painel" % _so_o_seguro(regra)
    return ("%s\n\n"
            "Correção gerada por uma sessão do Claude Code disparada pelo botão\n"
            "\"Resolver\" do painel de projetos, numa cópia isolada de %s.\n\n"
            "Pendência (regra %s): %s\n"
            % (titulo[:72], projeto, regra, pendencia.get("texto", "")))


def titulo_e_corpo_do_pr(pendencia: dict):
    """O que o dono le no GitHub semanas depois, sem lembrar desta pendencia."""
    projeto = pendencia.get("projeto", "")
    regra = pendencia.get("regra", "")
    titulo = "Resolve: %s (%s)" % (pendencia.get("texto", "")[:60], projeto)
    corpo = (
        "Aberto automaticamente pelo **painel de projetos**, a partir da pendência\n"
        "`%s` detectada em `%s`.\n\n"
        "**O que o painel viu:** %s\n\n"
        "**Detalhe:** %s\n\n"
        "A correção foi escrita por uma sessão do Claude Code rodando numa cópia\n"
        "isolada do repositório (`git worktree`), com teto de gasto aproximado de\n"
        "%s. Nenhuma pessoa leu este diff ainda. **Revise antes de mesclar.**\n"
        % (regra, projeto, pendencia.get("texto", ""),
           pendencia.get("detalhe", "") or "(sem detalhe)", em_reais(TETO_USD))
    )
    return titulo, corpo


# -------------------------------------------------- a copia isolada: disco e rede

# Fora de C:\\Users\\Desktop\\source\\repos de proposito: pastas_de_projeto()
# (coletar.py) trata TODA subpasta daquela raiz como projeto medido, e o painel
# passaria a medir as proprias copias. Mesmo espirito de CACHE_GRAFO.
BASE_COPIAS = Path.home() / ".cache" / "hub-worktrees"


def _sem_console() -> bool:
    """Igual a servir.py:60 — sob pythonw.exe cada filho abriria um console."""
    if not sys.platform.startswith("win"):
        return False
    if os.path.basename(sys.executable or "").lower() == "pythonw.exe":
        return True
    return sys.stdout is None


SEM_JANELA = 0x08000000 if _sem_console() else 0


def _rodar(args, cwd=None, limite=180):
    """Molde de servir.py:148 — (ok, saida cortada em 1200 caracteres)."""
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=limite,
                           creationflags=SEM_JANELA)
    except (OSError, subprocess.SubprocessError) as e:
        return False, "não consegui rodar %s: %s" % (args[0], e)
    saida = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    return r.returncode == 0, saida[-1200:]


def criar_copia(caminho_do_projeto, destino, ramo):
    """git worktree add — a pasta original do projeto nao e tocada."""
    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    return _rodar(["git", "-C", str(caminho_do_projeto), "worktree", "add",
                   "-b", ramo, str(destino), "HEAD"])


def remover_copia(caminho_do_projeto, destino):
    """Sucesso remove a copia; falha preserva (a chamada e de quem decide)."""
    ok, saida = _rodar(["git", "-C", str(caminho_do_projeto), "worktree",
                        "remove", "--force", str(destino)])
    _rodar(["git", "-C", str(caminho_do_projeto), "worktree", "prune"])
    return ok, saida


def houve_mudanca(destino) -> bool:
    ok, saida = _rodar(["git", "-C", str(destino), "status", "--porcelain"])
    return bool(ok and saida.strip())


def diff_da_copia(destino) -> str:
    """Texto puro: e exatamente o que a aba "Diff" mostra, sem requisicao nova."""
    ok, saida = _rodar(["git", "-C", str(destino), "diff", "HEAD"], limite=60)
    return saida if ok else ""


def publicar(destino, ramo, titulo, corpo, mensagem):
    """add + commit + push + gh pr create. NUNCA push na main, nunca pr merge.

    Devolve (ok, url_ou_None, log). O log volta inteiro para a tela: se o `gh`
    recusar porque ja existe PR, o dono precisa ver a frase do GitHub, nao um
    "algo deu errado" nosso.
    """
    passos = [
        (["git", "-C", str(destino), "add", "-A"], 60),
        (["git", "-C", str(destino), "commit", "-m", mensagem], 120),
        (["git", "-C", str(destino), "push", "-u", "origin", ramo], 180),
    ]
    log = []
    for args, limite in passos:
        ok, saida = _rodar(args, limite=limite)
        log.append(saida)
        if not ok:
            return False, None, "\n".join(x for x in log if x)

    ok, saida = _rodar(["gh", "pr", "create", "--title", titulo,
                        "--body", corpo, "--head", ramo],
                       cwd=str(destino), limite=180)
    log.append(saida)
    return ok, (url_do_pr(saida) if ok else None), "\n".join(x for x in log if x)
