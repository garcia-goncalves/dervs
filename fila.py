"""A fila que conserta.

O painel deixa de so apontar. As decisoes aqui sao PURAS — entra dicionario,
sai veredito — como em `regras.py`, e por isso custam pouco para testar.

O cerco tem quatro travas, todas verificadas em codigo:
teto diario, anti-laco, teste apagado e segredo no arquivo de exemplo de
ambiente. Nenhuma delas e uma instrucao no texto do pedido: instrucao em texto
e sugestao, nao trava.
"""
import re
from datetime import datetime, timedelta, timezone

import banco
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



def janela_local_em_utc(dia_local: str):
    """O dia LOCAL `dia_local` (AAAA-MM-DD) como janela [inicio, fim) em UTC.

    E o que permite somar o gasto do dia do DONO num banco que carimba em UTC.
    """
    fuso = datetime.now().astimezone().tzinfo
    inicio = datetime.strptime(dia_local, "%Y-%m-%d").replace(tzinfo=fuso)
    fim = inicio + timedelta(days=1)
    return (inicio.astimezone(timezone.utc).isoformat(timespec="seconds"),
            fim.astimezone(timezone.utc).isoformat(timespec="seconds"))


def dia_local_de(carimbo_utc: str) -> str:
    """A data LOCAL de um carimbo gravado em UTC. "" se nao der para ler.

    Comparar `terminado_em[:10]` (UTC) com `hoje_local()` era errado: das 21h a
    meia-noite as duas datas divergem, e o "falha de hoje nao volta hoje"
    deixava o item voltar no mesmo laco.
    """
    if not carimbo_utc:
        return ""
    try:
        return datetime.fromisoformat(carimbo_utc).astimezone().strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


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
        terminou = dia_local_de(item.get("terminado_em"))
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
    # Renomear `test_x.py` para `x.bak` apaga o teste na pratica e nao produz
    # `+++ /dev/null` nenhum. O diff da trava vem com --no-renames, mas um
    # `rename from` ainda pode chegar por outro caminho: barramos os dois.
    for linha in linhas:
        if linha.startswith("rename from "):
            caminho = linha[len("rename from "):].strip().strip('"')
            if NOME_DE_TESTE.search(caminho):
                return "renomeou o arquivo de teste %s" % caminho
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
def trabalhar(pendencias: list, executores: dict, parar_agora=None) -> dict:
    """Enfileira o que e elegivel e trabalha ate acabar servico, dinheiro ou paciencia.

    `executores` chega por parametro, nao por import: assim fila.py nao importa
    servir.py (que importaria fila.py de volta) e o teste roda sem servidor,
    sem rede e sem gastar um centavo.

    Cada executor recebe o item e devolve (deu_certo, custo_usd, pr_url, erro).
    """
    hoje = hoje_local()
    janela = janela_local_em_utc(hoje)
    banco.enfileirar(elegiveis(pendencias))
    relatorio = {"feitos": 0, "falhas": 0, "gasto_usd": 0.0, "motivo_da_parada": ""}

    while True:
        if parar_agora and parar_agora():
            relatorio["motivo_da_parada"] = "voce parou a fila"
            break

        gasto = banco.gasto_entre(*janela)
        relatorio["gasto_usd"] = gasto
        item = proximo(banco.fila_aberta(), gasto, hoje)

        if item is None:
            if not cabe_no_teto(gasto):
                relatorio["motivo_da_parada"] = (
                    "teto de %s do dia atingido" % execucao.em_reais(
                        TETO_DIARIO_BRL / execucao.USD_BRL))
            elif relatorio["feitos"] or relatorio["falhas"]:
                relatorio["motivo_da_parada"] = "acabou o servico"
            else:
                relatorio["motivo_da_parada"] = "nada na fila"
            break

        banco.marcar_fila(item["id"], estado="rodando", iniciado_em=banco.agora(),
                          tentativas=int(item.get("tentativas") or 0) + 1)

        executor = executores.get(item.get("trilho") or "")
        if executor is None:
            banco.marcar_fila(item["id"], estado="falha", terminado_em=banco.agora(),
                              erro="sem executor para o trilho %r" % item.get("trilho"))
            relatorio["falhas"] += 1
            continue

        try:
            deu_certo, custo, pr_url, erro = executor(item)
        except Exception as e:                      # noqa: BLE001 — o laco nao morre por um item
            deu_certo, custo, pr_url, erro = False, 0.0, "", "%s: %s" % (type(e).__name__, e)

        banco.marcar_fila(
            item["id"],
            estado="ok" if deu_certo else "falha",
            terminado_em=banco.agora(),
            custo_usd=float(custo or 0.0),
            pr_url=pr_url or None,
            erro=None if deu_certo else (erro or "falhou sem dizer por que"))

        if deu_certo:
            relatorio["feitos"] += 1
        else:
            relatorio["falhas"] += 1

    relatorio["gasto_usd"] = banco.gasto_entre(*janela)
    return relatorio
