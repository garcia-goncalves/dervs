"""A fila que conserta.

O painel deixa de so apontar. As decisoes aqui sao PURAS — entra dicionario,
sai veredito — como em `regras.py`, e por isso custam pouco para testar.

O cerco tem quatro travas, todas verificadas em codigo:
teto diario, anti-laco, teste apagado e segredo no arquivo de exemplo de
ambiente. Nenhuma delas e uma instrucao no texto do pedido: instrucao em texto
e sugestao, nao trava.
"""
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
