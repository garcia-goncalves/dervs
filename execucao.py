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
