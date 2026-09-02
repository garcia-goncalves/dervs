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

import auditoria
import banco
import execucao
import tarefas

# Regra -> trilho. Lista BRANCA: regra fora daqui nao chega ao motor.
#
# `memoria_crlf` e deterministico — existe um comando que faz, sempre igual.
# Gastar um modelo de linguagem nisso e pagar advogado para carimbar.
#
# `grafo_velho` parecia caber e NAO cabe: a acao dele hoje e copiar um texto
# para o dono colar (regras.py:145). Reindexar acontece pelo MCP do grafo, que
# o painel nao dirige — ele so serve a tela do grafo por procuracao.
#
# `auditoria_vencida` entra: e a decisao de RODAR a auditoria de novo, e o
# executor que a atende (`auditoria.EXECUTOR`) e' carimbado por `elegiveis`,
# nao por este mapa. As CINCO `auditoria_<categoria>` (o que a auditoria
# ACHOU) ficam DE FORA de proposito — sao pendencia de CONSERTO, e so entram
# aqui quando o dono autorizar consertar automaticamente o que a auditoria
# aponta. Na duvida, fora e o estado seguro.
REGRAS_MECANICAS = {
    "memoria_crlf":         "mecanico",
    "env_drift":            "claude",
    "dependencia_insegura": "claude",
    "auditoria_vencida":    "claude",
}

# Mesma ordem de `regras.ORDEM`. Nao importamos de la para a fila nao depender
# do motor de deteccao: sao dois assuntos, e o acoplamento so custaria.
ORDEM = {"alta": 0, "media": 1, "baixa": 2}


# MUDARAM DE CASA (Fatia 2, etapa 2) para `tarefas.py`: o teto do dia, as tres
# contas de fuso e as tres contas de dinheiro. O motivo e concreto: o SERVIDOR
# precisa recusar ENTREGAR a tarefa quando o teto do dia estourou, e ele nao
# pode importar `fila` (`test_rotas.AMPUTADOS`). Os nomes continuam aqui, e sao
# os MESMOS objetos — nao ha um segundo valor no repositorio.
TETO_DIARIO_BRL = tarefas.TETO_DIARIO_BRL
hoje_local = tarefas.hoje_local
janela_local_em_utc = tarefas.janela_local_em_utc
dia_local_de = tarefas.dia_local_de
cabe_no_teto = tarefas.cabe_no_teto
quanto_falta = tarefas.quanto_falta
teto_da_sessao = tarefas.teto_da_sessao


def trilho_de(pendencia: dict) -> str:
    """"mecanico" | "claude" | "" (nao elegivel)."""
    projeto = (pendencia.get("projeto") or "").strip()
    if not projeto:
        return ""
    if projeto.lower() in execucao.PROJETOS_BLOQUEADOS:
        return ""
    return REGRAS_MECANICAS.get((pendencia.get("regra") or "").strip(), "")


def elegiveis(pendencias: list) -> list:
    """As pendencias que a fila pode atacar, cada uma com `trilho` E
    `executor` carimbados.

    Devolve COPIAS: quem chamou continua dono da lista dele. O `executor` vem
    de `auditoria.EXECUTOR_DA_REGRA` — regra fora desse mapa recebe "claude",
    o mesmo padrao que `banco.enfileirar` usa no INSERT.
    """
    saida = []
    for p in pendencias or []:
        trilho = trilho_de(p)
        if trilho:
            copia = dict(p)
            copia["trilho"] = trilho
            copia["executor"] = auditoria.EXECUTOR_DA_REGRA.get(
                (p.get("regra") or "").strip(), "claude")
            saida.append(copia)
    return saida
# Duas tentativas, e o numero mora em `tarefas.py` desde a Fatia 2 — o
# servidor tambem precisa dele para nao entregar tarefa que ja se esgotou.
MAX_TENTATIVAS = tarefas.MAX_TENTATIVAS


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


# Os caminhos por onde uma publicacao acontece, a partir da RAIZ do repositorio.
# Casados contra o caminho do cabecalho do diff, nunca por substring solta:
# `infra` dentro de `src/infraestrutura.ts` reprovaria trabalho legitimo, e uma
# trava que reprova trabalho legitimo e desligada em duas semanas.
CAMINHOS_DE_PUBLICACAO = (
    ".github/workflows/",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "infra/",
)

# O que uma linha NOVA nao pode conter. Nao basta proteger os arquivos: um
# script novo em qualquer pasta que chame `gh workflow run` publica igual.
GATILHOS_DE_PUBLICACAO = (
    "workflow run",
    "workflow_dispatch",
    "/dispatches",
    "gh workflow",
)


def _caminho_do_diff(linha: str) -> str:
    """"+++ b/infra/x.conf" -> "infra/x.conf". "" para /dev/null."""
    alvo = linha[4:].strip().split("\t")[0].strip('"')
    if alvo in ("/dev/null", ""):
        return ""
    if alvo[:2] in ("a/", "b/"):
        alvo = alvo[2:]
    return alvo


def _e_caminho_de_publicacao(caminho: str) -> bool:
    if not caminho:
        return False
    for prefixo in CAMINHOS_DE_PUBLICACAO:
        if prefixo.endswith("/"):
            if caminho.startswith(prefixo):
                return True
        elif caminho == prefixo:
            return True
    return False


def diff_toca_publicacao(diff: str) -> str:
    """O diff alteraria o caminho que publica? Devolve o motivo, ou "".

    O criterio 4 da Fatia 2 nao se satisfaz com "nenhuma rota publica": nenhum
    DIFF produzido por uma sessao pode alterar o caminho que publica. Vale para
    TODA regra, verde ou vermelha — nao ha regra que compre esse direito.

    Diff VAZIO nao e reprovado. Parece obvio e nao e: uma trava que reprova
    tudo passa em todo teste de reprovacao e trava o produto inteiro.
    """
    linhas = (diff or "").splitlines()
    for linha in linhas:
        if linha.startswith("--- ") or linha.startswith("+++ "):
            caminho = _caminho_do_diff(linha)
            if _e_caminho_de_publicacao(caminho):
                return "mexeria em %s, que e caminho de publicacao" % caminho
        elif linha.startswith("rename from ") or linha.startswith("rename to "):
            caminho = linha.split(" ", 2)[-1].strip().strip('"')
            if _e_caminho_de_publicacao(caminho):
                return "renomearia %s, que e caminho de publicacao" % caminho
    for linha in linhas:
        if not linha.startswith("+") or linha.startswith("+++"):
            continue
        seco = linha[1:]
        for gatilho in GATILHOS_DE_PUBLICACAO:
            if gatilho in seco:
                return "a linha nova conteria `%s`, que dispara publicacao" % gatilho
    return ""


def reprovar(diff: str, regra: str) -> str:
    """Aplica as travas de diff que valem para esta regra. "" e aprovado."""
    motivo = diff_mexeu_em_teste(diff)
    if motivo:
        return motivo
    # Para TODA regra, sem excecao e antes da parte especifica: publicar nao e
    # um caso particular de uma regra, e um limite do produto inteiro.
    motivo = diff_toca_publicacao(diff)
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

    Cada executor recebe (item, teto_usd) e devolve
    (deu_certo, custo_usd, pr_url, erro). O `teto_usd` e o da SESSAO, ja
    limitado ao que sobra do teto do dia — ver `teto_da_sessao`.
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
            deu_certo, custo, pr_url, erro = executor(item, teto_da_sessao(gasto))
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
