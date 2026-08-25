"""A fila que conserta.

O painel deixa de so apontar. As decisoes aqui sao PURAS — entra dicionario,
sai veredito — como em `regras.py`, e por isso custam pouco para testar.

O cerco tem quatro travas, todas verificadas em codigo:
teto diario, anti-laco, teste apagado e segredo no arquivo de exemplo de
ambiente. Nenhuma delas e uma instrucao no texto do pedido: instrucao em texto
e sugestao, nao trava.
"""
import re
from datetime import datetime

import execucao

# Regra -> trilho. Lista BRANCA: regra fora daqui nao chega ao motor.
#
# `memoria_crlf` e deterministico — existe um comando que faz, sempre igual.
# Gastar um modelo de linguagem nisso e pagar advogado para carimbar.
#
# `grafo_velho` parecia caber e NAO cabe: a acao dele hoje e copiar um texto
# para o dono colar (regras.py:145). Reindexar acontece pelo MCP do grafo, que
# o painel nao dirige — ele so serve a tela do grafo por procuracao.
REGRAS_MECANICAS = {
    "memoria_crlf":         "mecanico",
    "env_drift":            "claude",
    "dependencia_insegura": "claude",
}

# Mesma ordem de `regras.ORDEM`. Nao importamos de la para a fila nao depender
# do motor de deteccao: sao dois assuntos, e o acoplamento so custaria.
ORDEM = {"alta": 0, "media": 1, "baixa": 2}


# O freio da fila desacompanhada. Decisao do dono em 25/08/2026: comecar
# apertado e afrouxar depois e mais facil que o contrario.
TETO_DIARIO_BRL = 50.00


def hoje_local() -> str:
    """A data de HOJE para o dono, nao para o servidor.

    O resto do banco carimba em UTC. O teto, nao: em UTC-3, as 21h de terca ja
    e quarta em UTC, e o teto zeraria tres horas cedo.
    """
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def cabe_no_teto(gasto_usd: float) -> bool:
    """Ha espaco para comecar mais um item hoje? No ponto exato, ja nao ha."""
    try:
        gasto_brl = float(gasto_usd) * execucao.USD_BRL
    except (TypeError, ValueError):
        gasto_brl = 0.0
    return gasto_brl < TETO_DIARIO_BRL


def quanto_falta(gasto_usd: float) -> float:
    """Quantos reais ainda cabem hoje. Nunca negativo — a tela nao mostra divida."""
    try:
        gasto_brl = float(gasto_usd) * execucao.USD_BRL
    except (TypeError, ValueError):
        gasto_brl = 0.0
    return max(0.0, TETO_DIARIO_BRL - gasto_brl)


def trilho_de(pendencia: dict) -> str:
    """"mecanico" | "claude" | "" (nao elegivel)."""
    projeto = (pendencia.get("projeto") or "").strip()
    if not projeto:
        return ""
    if projeto.lower() in execucao.PROJETOS_BLOQUEADOS:
        return ""
    return REGRAS_MECANICAS.get((pendencia.get("regra") or "").strip(), "")


def elegiveis(pendencias: list) -> list:
    """As pendencias que a fila pode atacar, cada uma com `trilho` carimbado.

    Devolve COPIAS: quem chamou continua dono da lista dele.
    """
    saida = []
    for p in pendencias or []:
        trilho = trilho_de(p)
        if trilho:
            copia = dict(p)
            copia["trilho"] = trilho
            saida.append(copia)
    return saida
# Duas tentativas. A terceira nunca consertou nada que a segunda nao tenha
# consertado — e uma correcao que nao pega vira torneira aberta.
MAX_TENTATIVAS = 2


def pode_tentar(item: dict, hoje: str) -> bool:
    """Este item ainda merece uma chance hoje?"""
    if int(item.get("tentativas") or 0) >= MAX_TENTATIVAS:
        return False
    if item.get("estado") == "falha":
        terminou = (item.get("terminado_em") or "")[:10]
        if terminou == hoje:
            return False
    return True


def proximo(itens: list, gasto_usd: float, hoje: str):
    """O proximo item a trabalhar, ou None. NAO inicia nada: so escolhe.

    Separar escolher de fazer e o que torna a ordem testavel sem processo,
    sem rede e sem gastar um centavo.
    """
    if not cabe_no_teto(gasto_usd):
        return None
    espera = [i for i in (itens or [])
              if i.get("estado") in ("esperando", "falha") and pode_tentar(i, hoje)]
    if not espera:
        return None
    espera.sort(key=lambda i: (ORDEM.get(i.get("gravidade"), 9),
                               -float(i.get("risco") or 0),
                               (i.get("projeto") or "").lower()))
    return espera[0]
# Nome de arquivo de teste nas quatro convencoes que os 17 projetos usam.
NOME_DE_TESTE = re.compile(
    r"(^|/)(test_[^/]+\.py|[^/]+_test\.[A-Za-z0-9]+"
    r"|[^/]+\.test\.[A-Za-z0-9]+|[^/]+\.spec\.[A-Za-z0-9]+)$")

# Marcadores de teste desligado. Cada um ja apareceu em algum destes projetos.
MARCADORES_SKIP = (
    "@unittest.skip", "pytest.mark.skip", "@skip",
    "it.skip(", "xit(", "test.skip(", "describe.skip(", "xdescribe(",
)


def diff_mexeu_em_teste(diff: str) -> str:
    """"" se o diff esta limpo; senao o motivo, pronto para a tela.

    Esta e a unica coisa entre 'consertar o teste' e 'apagar o teste'. Ela vive
    em codigo e nao no texto do pedido: instrucao em texto e sugestao.
    """
    linhas = (diff or "").splitlines()
    for i, linha in enumerate(linhas):
        if not linha.startswith("--- a/"):
            continue
        if i + 1 >= len(linhas) or not linhas[i + 1].startswith("+++ /dev/null"):
            continue
        caminho = linha[len("--- a/"):].strip()
        if NOME_DE_TESTE.search(caminho):
            return "apagou o arquivo de teste %s" % caminho
    for linha in linhas:
        if not linha.startswith("+") or linha.startswith("+++"):
            continue
        seco = linha[1:]
        for marcador in MARCADORES_SKIP:
            if marcador in seco:
                return "desligou um teste com `%s`" % marcador
    return ""
CHAVE_COM_VALOR = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]{0,63})\s*=\s*(\S.*)$")


def env_example_tem_valor(diff: str) -> str:
    """Alguma linha NOVA do .env.example levaria valor? Estrito de proposito.

    Um espaco reservado que parece inofensivo passa a ser recusado junto. O
    custo de errar para o lado frouxo e um segredo no historico do git, e
    rotacionar segredo e varredura no repositorio inteiro.
    """
    for linha in (diff or "").splitlines():
        if not linha.startswith("+") or linha.startswith("+++"):
            continue
        seco = linha[1:].strip()
        if not seco or seco.startswith("#"):
            continue
        achou = CHAVE_COM_VALOR.match(seco)
        if achou:
            return "a linha `%s` do .env.example levaria um valor" % achou.group(1)
    return ""


def reprovar(diff: str, regra: str) -> str:
    """Aplica as travas de diff que valem para esta regra. "" e aprovado."""
    motivo = diff_mexeu_em_teste(diff)
    if motivo:
        return motivo
    if regra == "env_drift":
        return env_example_tem_valor(diff)
    return ""
