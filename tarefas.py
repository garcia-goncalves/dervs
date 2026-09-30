"""O semaforo, e os tetos que valem para o painel INTEIRO.

Este arquivo existe para responder UMA pergunta, num lugar so:

    "esta tarefa pode rodar agora?"

Ela e feita duas vezes, por dois programas diferentes. O servidor pergunta
antes de ENTREGAR a tarefa ao agente; o agente pergunta de novo antes de
DISPARAR a sessao. As duas respostas tem de vir do mesmo codigo, senao a que
diverge e sempre a que ninguem le — foi a licao do `contraste.py`, em
27/08/2026.

**Nada e importado daqui alem da biblioteca padrao.** Em particular, nunca
`execucao` nem `fila`:

- `servir.py` importa este arquivo, e `test_rotas.AMPUTADOS` reprova o
  servidor que alcance `execucao` ou `fila`, mesmo por tabela;
- `test_imagem.py` cobra que todo modulo importado por `servir.py` entre na
  imagem, E proibe `execucao.py`, `fila.py` e `barreira.py` de entrarem. Um
  `import execucao` aqui tornaria as duas exigencias impossiveis ao mesmo
  tempo.

As constantes de dinheiro e de tempo MUDARAM DE CASA para ca (Fatia 2). Nao
ficaram copias em `fila.py` nem em `execucao.py`: os dois passaram a importar
daqui. Duas copias de um teto divergem, e a que diverge mente com autoridade.
"""
import re
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Dinheiro e tempo. Vinham de `execucao.py` e de `fila.py`.
# ---------------------------------------------------------------------------

# Teto por execucao, em dolar. US$ 1 nao daria: medido em 24/08/2026, so LIGAR a
# sessao custa US$ 0,2256 num turno trivial sem MCP, e US$ 0,4455 herdando os
# MCPs da maquina. NAO E LIMITE DURO — `--max-budget-usd` foi medido estourando
# 4,5x. A unica garantia dura e `parar()`.
TETO_USD = 3.0

# Cotacao fixa no codigo, num lugar so (decisao do dono, 24/08/2026). Valor do
# fechamento de 21/08/2026: R$ 5,1417. Envelhece — atualize quando incomodar.
USD_BRL = 5.14

# Limite de turnos da sessao filha. Uma CI vermelha simples se resolve em muito
# menos; o numero existe para o laco que der errado nao rodar a noite inteira.
MAX_TURNOS = 40

# O freio da fila desacompanhada. Decisao do dono em 25/08/2026: comecar
# apertado e afrouxar depois e mais facil que o contrario.
TETO_DIARIO_BRL = 50.00

# Duas tentativas. A terceira nunca consertou nada que a segunda nao tenha
# consertado — e uma correcao que nao pega vira torneira aberta.
MAX_TENTATIVAS = 2

# Teto por auditoria, em dolar (Auditoria Profunda, 02/09/2026). Recomendado
# pela spec: US$ 1,50 (~R$ 7,71) da para tres a quatro auditorias por dia sem
# impedir a fila de consertar. Comeca apertado de proposito — afrouxar depois
# e mais facil que o contrario (a mesma logica de TETO_DIARIO_BRL, acima).
TETO_AUDITORIA_USD = 1.50

# Decisao do dono no portao de risco: prontuario sob LGPD fica fora da entrega
# 1. Comparacao sempre em minusculas. MUDOU DE CASA (revisao de seguranca de
# 02/09/2026): `servir._auditoria_pedir` precisa desta lista para nao
# enfileirar auditoria de um projeto bloqueado, e o servidor nao pode importar
# `execucao` (`test_rotas.AMPUTADOS`). `execucao.py` reexporta o MESMO
# objeto — nao ha uma segunda lista no repositorio.
PROJETOS_BLOQUEADOS = {"ajudei-saude"}

# As regras que o botao "Consertar com IA" do painel pode enfileirar. So as
# MECANICAS e seguras: `dependencia_insegura`, `auditoria_vencida` e os achados
# de seguranca ficam de fora (a IA nao mexe em seguranca sem revisao humana).
# Mora aqui, e nao em `fila.py`, pelo mesmo motivo de PROJETOS_BLOQUEADOS:
# `servir.py` aplica o filtro e nao pode importar `fila` (`test_rotas.AMPUTADOS`,
# e o Dockerfile nao leva `fila.py`). `fila.py` reexporta o MESMO objeto, e
# `test_fila` cobra que e subconjunto de `REGRAS_MECANICAS`.
REGRAS_CONSERTAVEIS_PELA_TELA = frozenset({"memoria_crlf", "env_drift"})

# Palpite, nao decisao: a spec nao fixa numero de turnos para auditoria. 60 e
# o dobro de MAX_TURNOS porque ler um repositorio inteiro com Read/Grep/Glob
# gasta turno rapido, e nenhum deles escreve nada — a primeira auditoria real
# vira medicao, e o numero volta com dado em vez de chute.
MAX_TURNOS_AUDITORIA = 60


def em_reais(usd) -> str:
    """0.2256 -> "R$ 1,16". Virgula decimal, duas casas, sempre."""
    try:
        valor = float(usd) * USD_BRL
    except (TypeError, ValueError):
        valor = 0.0
    return "R$ " + ("%.2f" % valor).replace(".", ",")


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


def cabe_no_teto(gasto_usd) -> bool:
    """Ha espaco para comecar mais um item hoje? No ponto exato, ja nao ha."""
    try:
        gasto_brl = float(gasto_usd) * USD_BRL
    except (TypeError, ValueError):
        gasto_brl = 0.0
    return gasto_brl < TETO_DIARIO_BRL


def quanto_falta(gasto_usd) -> float:
    """Quantos reais ainda cabem hoje. Nunca negativo — a tela nao mostra divida."""
    try:
        gasto_brl = float(gasto_usd) * USD_BRL
    except (TypeError, ValueError):
        gasto_brl = 0.0
    return max(0.0, TETO_DIARIO_BRL - gasto_brl)


def teto_da_sessao(gasto_usd) -> float:
    """Quanto ESTA sessao pode gastar, em dolar. Nunca mais do que sobra hoje.

    Achado do revisor em 25/08/2026: o teto do dia era conferido ANTES do item
    e a sessao saia sempre com TETO_USD (US$ 3, ~R$ 15,42). Com R$ 49 gastos, a
    fila via "cabe" e iniciava um item que podia levar o dia a R$ 64 — sem que
    `cabe_no_teto` jamais tivesse dito que estourou. O teto do dia so vale se o
    teto da sessao souber quanto falta.
    """
    falta_usd = quanto_falta(gasto_usd) / USD_BRL
    return max(0.0, min(float(TETO_USD), falta_usd))


def teto_da_auditoria(gasto_usd) -> float:
    """Quanto UMA auditoria pode gastar, em dolar. Nunca mais do que sobra hoje.

    Mora aqui, e nao em `execucao.py`, porque o SERVIDOR precisa dele para
    calcular o `teto_usd` que desce na tarefa (`servir.py:1918`), e o servidor
    nao pode importar `execucao` nem `fila`. O molde e `teto_da_sessao`, acima
    — o mesmo achado do revisor de 25/08/2026 vale aqui: o teto da auditoria
    tem de ser limitado ao que sobra do dia, senao R$ 49 gastos ainda liberam
    uma auditoria de R$ 7,71 inteira.
    """
    falta_usd = quanto_falta(gasto_usd) / USD_BRL
    return max(0.0, min(float(TETO_AUDITORIA_USD), falta_usd))


# ---------------------------------------------------------------------------
# A peneira de texto para prompt. MUDOU DE CASA de `execucao.py` (Auditoria
# Profunda, 02/09/2026): `execucao.py` NAO entra na imagem
# (`test_imagem.PROIBIDOS`), mas `auditoria.py` entra — e `auditoria.py` usa
# a MESMA peneira que `execucao.montar_prompt` ja usa. Uma segunda copia do
# sanitizador e exatamente o defeito que o CLAUDE.md registra em "As tres
# portas": "uma segunda copia dessa peneira ja matou o drift em silencio com
# 926 testes verdes". `execucao.py` reexporta os MESMOS objetos, no molde de
# `execucao.em_reais = tarefas.em_reais`.
# ---------------------------------------------------------------------------

# A etiqueta que separa dado de instrucao dentro do prompt. Se o proprio dado
# trouxer essa etiqueta escrita, ele fecha o bloco antes da hora e o resto vira
# instrucao — e exatamente o buraco que o bloco existe para tapar.
FIM_DO_BLOCO = "</dados-coletados-nao-confiaveis>"


# Qualquer forma de abrir ou fechar o bloco: caixa diferente, espaco (ou quebra de
# linha) dentro da tag, `< /dados...>`. Compilado AQUI, no topo: `test_rotas`
# reprova `compile` dentro de funcao alcancavel de rota.
_ETIQUETA_DO_BLOCO = re.compile(
    r"<\s*/?\s*dados-coletados-nao-confiaveis\s*>", re.IGNORECASE)


def so_dado(texto) -> str:
    """Tira do campo qualquer tentativa de abrir ou fechar o bloco de dados na
    marra. O resto do texto fica como esta: legivel."""
    limpo = str(texto or "")
    return _ETIQUETA_DO_BLOCO.sub("[etiqueta removida]", limpo)


# ---------------------------------------------------------------------------
# O semaforo
# ---------------------------------------------------------------------------

# As unicas duas cores. Nao ha amarelo: "talvez" nao e uma decisao, e uma
# desculpa para nao ter decidido.
VERMELHO = "vermelho"
VERDE = "verde"
CORES = (VERMELHO, VERDE)

# As regras que NAO PODEM ficar verdes, nunca, por decisao do dono em
# 28/08/2026. Repintar uma delas e recusado nos dois lados — aqui e no banco.
# Nao ha caminho de configuracao, de rota ou de tela que atravesse isto: a
# unica forma de abrir seria editar este arquivo, e ai o vigia
# `test_tarefas_nao_publicam.py` fica vermelho.
NUNCA_VERDE = frozenset({"publicar"})

# Duas familias DIFERENTES, e misturar as duas e o erro que este conjunto
# existe para evitar. `NUNCA_VERDE` e recusado em `pode_rodar` ANTES da
# aprovacao: a regra nunca anda, nem com o clique do dono. `desenvolver` tem de
# andar COM o clique — so nao pode andar sem ele, e nao pode ser repintada de
# verde. Por isso ela NAO entra em `NUNCA_VERDE` (nunca rodaria): entra aqui.
SEMPRE_VERMELHA = frozenset({"desenvolver"})

# Projetos em que o DERVS nao desenvolve nada (mais todo nome com "nexa", que e
# do Andre). Somam-se a `PROJETOS_BLOQUEADOS`: dado de paciente, os cinco da
# TineHost (revenda, sem runner) e o `aninha-site`. Comparacao em minusculas.
PROJETOS_SEM_DESENVOLVIMENTO = frozenset({
    "ajudei-saude", "medconsultoria", "ccvp", "zacareli", "sophia",
    "camargo-e-soares", "aninha-site"})

# Toda regra nasce vermelha. Nao ha lista de regras verdes escrita aqui: o
# padrao e a recusa, e o que existe e o registro do que o dono REPINTOU.
# Apagar a linha da repintura volta ao seguro, em vez de abrir o caminho.


def _nome_normalizado(nome: str) -> str:
    """Minusculas, e `_`, espaco e `.` viram `-`: "Ajudei_Saude" e "ajudei.saude"
    sao o mesmo projeto que "ajudei-saude" para quem quer contornar a lista."""
    return re.sub(r"[_\s.]+", "-", nome.strip().lower())


def projeto_pode_desenvolver(nome) -> bool:
    """O DERVS pode desenvolver neste projeto? Falha fechada: duvida e NAO.

    Nome que nao e texto, vazio, bloqueado, da TineHost, do Andre (qualquer
    nome com "nexa") ou o `aninha-site` dao `False` — igual ao nome da lista OU
    comecando por ele na fronteira do `-` (`ajudei-saude-web`, `aninha-site-v2`).
    A comparacao e sempre normalizada: houve um teste provando que
    `Ajudei-Saude` escapava de outra lista igual a esta. A fronteira do `-`
    poupa os parecidos legitimos (`ccvpx`, `sophiana`).
    """
    if not isinstance(nome, str):
        return False
    n = _nome_normalizado(nome)
    if not n or "nexa" in n:
        return False
    for bloqueado in PROJETOS_BLOQUEADOS | PROJETOS_SEM_DESENVOLVIMENTO:
        if n == bloqueado or n.startswith(bloqueado + "-"):
            return False
    return True


def cor_da_regra(regra: str, repinturas=None) -> str:
    """A cor de uma regra hoje. `vermelho` quando em duvida, sempre.

    `repinturas` e o que veio de `banco.cores_das_regras()`: {regra: cor}.
    Regra ausente, cor desconhecida, dicionario vazio, `None` — tudo vermelho.
    """
    nome = (regra or "").strip()
    if not nome or nome in NUNCA_VERDE or nome in SEMPRE_VERMELHA:
        return VERMELHO
    cor = (repinturas or {}).get(nome)
    return VERDE if cor == VERDE else VERMELHO


def pode_repintar(regra: str, cor: str) -> bool:
    """O dono pode pintar esta regra desta cor?

    Voltar para vermelho e SEMPRE permitido, inclusive em `NUNCA_VERDE`: fechar
    nunca precisa de licenca. Abrir, sim.
    """
    nome = (regra or "").strip()
    if not nome or cor not in CORES:
        return False
    if cor == VERDE and (nome in NUNCA_VERDE or nome in SEMPRE_VERMELHA):
        return False
    return True


# ---------------------------------------------------------------------------
# O contrato do fio de volta
#
# O agente nunca escuta porta nenhuma. Ele PERGUNTA, e o painel responde. Sao
# dois formatos, e eles estao escritos aqui — e nao em `servir.py` nem em
# `agente/enviar.py` — porque as duas pontas precisam concordar sem se ler.
#
# DESCE (dentro da resposta 200 de POST /agente/relatorio, na chave "tarefa";
# `null` quando nao ha nada a fazer):
#
#     {"id": "...",            # o id da linha na fila
#      "projeto": "...",       # a pasta que a sessao vai copiar
#      "regra": "...",         # a regra que originou a tarefa
#      "trilho": "claude",     # qual braco: "claude" | "mecanico"
#      "executor": "claude",   # qual implementacao de Executor
#      "detalhe": "...",       # o texto do pedido
#      "cor": "verde",         # ja resolvida pelo painel
#      "teto_usd": 3.0,        # o que SOBRA hoje, nao o teto cheio
#      "rodadas": 0,           # quantas ja foram, para retomada de contagem
#      "aprovado_em": "...",   # o carimbo do clique do dono, "" se nao houve
#      "tentativas": 1,        # quantas ANTES desta; nunca inclui a atual
#      "parada_pedida_em": ""} # o freio; "" quando ninguem pediu para parar
#
# OS TRES ULTIMOS SAO OS FATOS QUE `pode_rodar` CONSULTA, e por isso descem.
# Ate 03/09/2026 nao desciam, o agente recusava toda tarefa aprovada, e o braco
# executor nunca rodou nada. Campo novo que `pode_rodar` passe a ler entra aqui
# E na montagem de `servir._tarefa_pendente` — as duas pontas so concordam sem
# se ler se este bloco for a verdade.
#
# SOBE (POST /agente/resultado). Dois tipos no mesmo balcao, distinguidos pela
# chave "tipo" — um balcao so porque o teto de chamadas e por balcao, e o
# progresso e frequente:
#
#     {"tipo": "progresso", "id": "...", "frase": "...",
#      "linhas": [[n, "texto"], ...],   # so as novas, desde a ultima vez
#      "rodadas": 3, "custo_usd": 0.41}
#
#     {"tipo": "desfecho", "id": "...", "estado": "ok" | "falha",
#      "ramo": "hub/...", "resumo": "...", "diff": "...", "pr_url": "...",
#      "rodadas": 7, "custo_usd": 1.02, "erro": ""}
#
# A RESPOSTA de /agente/resultado carrega sempre `{"pare": true|false}`. E
# assim, e so assim, que o botao Parar chega ao agente: sem conexao nova, sem
# porta aberta, e com a latencia declarada de ate ~10 s.
# ---------------------------------------------------------------------------

CAMPOS_DA_TAREFA = ("id", "projeto", "regra", "trilho", "executor", "detalhe",
                    "cor", "teto_usd", "rodadas", "aprovado_em", "tentativas",
                    "parada_pedida_em")
CAMPOS_DO_PROGRESSO = ("tipo", "id", "frase", "linhas", "rodadas", "custo_usd")
CAMPOS_DO_DESFECHO = ("tipo", "id", "estado", "ramo", "resumo", "diff",
                      "pr_url", "rodadas", "custo_usd", "erro")

# De quanto em quanto tempo o agente fala enquanto a sessao roda. E o que
# alimenta o fluxo ao vivo E o que torna o botao Parar utilizavel: o pedido de
# parada viaja na RESPOSTA deste pedido. Mexer aqui muda a latencia do freio.
SEGUNDOS_ENTRE_PROGRESSOS = 5

# Depois disto sem noticia, a tarefa `rodando` vira `falha`. Sem este prazo,
# agente morto deixa a tarefa rodando para sempre e o painel mente (lei 2).
MINUTOS_SEM_NOTICIA = 15


def pode_rodar(tarefa: dict, gasto_usd=0.0, agora_iso: str = "",
               repinturas=None, maquina=None):
    """A pergunta unica. Devolve `(pode, motivo)`.

    `motivo` e uma frase em portugues, para a tela — nunca um codigo. Quando
    `pode` e True o motivo e "".

    A ordem das recusas nao e estetica: o teto do dia vem PRIMEIRO, porque uma
    tarefa que nao cabe no dia nao deve nem ser avaliada pelo resto. Depois vem
    a maquina, depois a cor, depois as tentativas.

    Nada aqui levanta excecao. Este e caminho de autorizacao, e a lei 3 do
    repositorio manda falhar fechado: entrada estranha vira recusa, nunca um
    traceback que alguem trata como "deu erro, deixa passar".
    """
    try:
        t = dict(tarefa or {})
    except (TypeError, ValueError):
        return (False, "a tarefa veio num formato que nao da para ler")
    if not (t.get("id") or "").strip():
        return (False, "a tarefa nao tem identificacao")

    if not cabe_no_teto(gasto_usd):
        return (False, "o teto de %s do dia ja foi alcancado"
                       % em_reais(TETO_DIARIO_BRL / USD_BRL))

    if maquina is not None and not int((maquina or {}).get("executa") or 0):
        return (False, "este computador nao esta autorizado a executar tarefas")

    regra = (t.get("regra") or "").strip()
    if not regra:
        return (False, "a tarefa nao diz de que regra veio")
    # ANTES da aprovacao, e nao depois. Escrito assim porque o contrario ja
    # esteve aqui e era um buraco: com a checagem dentro do `if`, uma tarefa
    # `publicar` que tivesse `aprovado_em` passava — o clique do dono numa
    # tarefa aprovava a PUBLICACAO. O clique aprova UMA tarefa; ele nunca
    # levanta o NUNCA_VERDE. Achado pelo vigia irmao em 29/08/2026.
    if regra in NUNCA_VERDE:
        return (False, "a regra \"%s\" nunca anda sozinha" % regra)
    # A segunda barreira de `desenvolver`: o servidor ja recusou o projeto ao
    # receber o pedido, mas o AGENTE pergunta de novo aqui, e nao abre sessao em
    # projeto que nao se desenvolve mesmo que a linha da fila diga o contrario.
    if regra in SEMPRE_VERMELHA and not projeto_pode_desenvolver(
            t.get("projeto")):
        return (False, "o DERVS nao desenvolve neste projeto")
    cor = cor_da_regra(regra, repinturas)
    if cor != VERDE and not (t.get("aprovado_em") or "").strip():
        return (False, "esta tarefa esta vermelha e espera o seu clique")

    if int(t.get("tentativas") or 0) >= MAX_TENTATIVAS:
        return (False, "ja foram %d tentativas; a proxima nao consertaria"
                       % MAX_TENTATIVAS)

    if (t.get("parada_pedida_em") or "").strip():
        return (False, "voce pediu para parar esta tarefa")

    return (True, "")


# ---------------------------------------------------------------------------
# O diff em portugues (etapa 12). Funcao PURA, deterministica, sem modelo de
# linguagem: um LLM que "acha" que o diff e inofensivo e exatamente o numero
# errado com cara de certo que a lei 2 proibe. Aqui a IA ja trabalhou — a
# apresentacao e conta nossa.
# ---------------------------------------------------------------------------

def _caminho_do_cabecalho(linha: str) -> str:
    """"+++ b/banco.py\t" -> "banco.py". "" para /dev/null."""
    alvo = linha[4:].strip().split("\t")[0]
    if alvo in ("/dev/null", ""):
        return ""
    if alvo[:2] in ("a/", "b/"):
        alvo = alvo[2:]
    return alvo


def frases_do_diff(diff: str) -> list:
    """Uma frase em portugues por arquivo tocado.

    Diff vazio devolve UMA frase dizendo que nada mudou — nunca uma lista
    vazia. Lista vazia na tela e indistinguivel de "nao consegui ler", e essa
    e a diferenca que a lei 2 exige que apareca.
    """
    texto = diff or ""
    if not texto.strip():
        return ["Nada mudou: a sessão terminou sem tocar em nenhum arquivo."]

    arquivos = []
    atual = None
    for linha in texto.splitlines():
        if linha.startswith("--- "):
            antigo = _caminho_do_cabecalho(linha)
            atual = {"antigo": antigo, "novo": "", "mais": 0, "menos": 0}
            arquivos.append(atual)
        elif linha.startswith("+++ ") and atual is not None and not atual["novo"]:
            atual["novo"] = _caminho_do_cabecalho(linha)
        elif atual is None:
            continue
        elif linha.startswith("+++") or linha.startswith("---"):
            continue
        elif linha.startswith("+"):
            atual["mais"] += 1
        elif linha.startswith("-"):
            atual["menos"] += 1

    if not arquivos:
        return ["Nada mudou: a sessão terminou sem tocar em nenhum arquivo."]

    frases = []
    for a in arquivos:
        antigo, novo = a["antigo"], a["novo"]
        nome = novo or antigo
        if not antigo and novo:
            frases.append("o arquivo `%s` foi criado (%d linhas)"
                          % (novo, a["mais"]))
        elif antigo and not novo:
            frases.append("o arquivo `%s` foi apagado" % antigo)
        elif antigo and novo and antigo != novo:
            frases.append("o arquivo `%s` virou `%s`" % (antigo, novo))
        else:
            frases.append("%s em `%s`" % (_contar(a["mais"], a["menos"]), nome))
    return frases


def _contar(mais: int, menos: int) -> str:
    """"3 linhas trocadas" | "2 linhas a mais" | "1 linha a menos"."""
    trocadas = min(mais, menos)
    pedacos = []
    if trocadas:
        pedacos.append("%d linha%s trocada%s"
                       % (trocadas, "" if trocadas == 1 else "s",
                          "" if trocadas == 1 else "s"))
    a_mais, a_menos = mais - trocadas, menos - trocadas
    if a_mais:
        pedacos.append("%d linha%s a mais"
                       % (a_mais, "" if a_mais == 1 else "s"))
    if a_menos:
        pedacos.append("%d linha%s a menos"
                       % (a_menos, "" if a_menos == 1 else "s"))
    if not pedacos:
        return "nenhuma linha mudou"
    return ", ".join(pedacos)
