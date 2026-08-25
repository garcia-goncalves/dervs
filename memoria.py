# -*- coding: utf-8 -*-
"""A memoria do tempo do HUB — idade da pendencia, tendencia e briefing.

POR QUE ESTE MODULO EXISTE

O painel respondia bem "o que precisa de mim agora?" e nao respondia nada sobre
ontem. Sem isso faltavam tres coisas que decidem se a lista e usada ou ignorada:

  1. IDADE. Uma pendencia nascida ha uma hora e outra aberta ha 23 dias apareciam
     iguais, no mesmo tamanho, na mesma cor. Sao coisas diferentes.
  2. PROGRESSO. Lista que so cresce e nunca reconhece o que foi feito e lista
     que se aprende a fechar. Fechar 6 coisas na semana precisava aparecer.
  3. DIRECAO. "Isto esta piorando" e informacao; "existem 27 pendencias" nao e.

QUEM CHAMA, E QUANDO

`registrar()` roda no laco de coleta do servidor (servir.py), uma vez por coleta
LOCAL bem-sucedida — de 60 em 60 s. Deliberadamente NAO roda no /api/dados:
aquela rota e disparada pelo navegador de 15 em 15 s, e com a aba fechada o dia
inteiro o historico ficaria vazio justamente no dia em que o dono nao olhou.
Painel que so lembra do que aconteceu enquanto era olhado nao tem memoria, tem
espelho.

`decorar()`, `tendencia()` e `briefing()` sao de leitura e rodam no /api/dados.
`decorar()` e `briefing()` sao puras — entra dado, sai dado, sem relogio e sem
banco. E o que as torna testaveis sem esperar um dia passar.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import banco
from regras import ORDEM

JANELA_NOVA_H = 24        # abaixo disso a pendencia recebe o selo "nova"
JANELA_SEMANA_D = 7       # o "voce fechou N" olha para esta janela
PONTOS_SERIE = 60         # retratos devolvidos para o grafico da tela
BATIMENTO_H = 1           # ate sem novidade, um retrato por hora

GRAVIDADES = ("alta", "media", "baixa")


def _dt(iso: str):
    """ISO -> datetime consciente de fuso. None quando o texto nao presta."""
    try:
        d = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _agora(agora_iso=None) -> str:
    return agora_iso or banco.agora()


# ---------------------------------------------------------------- escrita
def registrar(pendencias, con, agora_iso=None, medicao_valida=True) -> dict:
    """Atualiza a vida de cada pendencia e grava o retrato numerico do momento.

    `medicao_valida=False` faz a funcao NAO TOCAR EM NADA. O chamador usa isso
    quando a coleta terminou bem mas nao enxergou projeto nenhum — a pasta de
    repositorios ficou indisponivel por um instante, por exemplo. Sem esta
    guarda, uma lista vazia significaria "o dono resolveu tudo": as 27
    pendencias seriam marcadas como fechadas, renasceriam com selo de "nova" na
    coleta seguinte, e o briefing anunciaria "voce fechou 27 nos ultimos 7 dias".
    Entre elas estariam `vulnerabilidade` e `site_fora`. Nao e um erro de
    contagem: e o painel mentindo sobre seguranca, que e o unico defeito que
    mata este projeto.

    Tres movimentos, nesta ordem:
      - quem apareceu agora e nao tinha linha aberta ganha `visto_em`;
      - quem ja estava aberta tem so o `ultimo_em` renovado (NAO rejuvenesce);
      - quem estava aberta e nao veio nesta rodada ganha `fechada_em`.

    Pendencia que volta depois de fechada e tratada como NOVA, de proposito: o
    grafo que envelheceu de novo tres semanas depois nao e o mesmo problema de
    antes, e mostra-lo com "aberto ha 30 dias" seria mentira.
    """
    if not medicao_valida:
        return {"abertas": {}, "fechadas_agora": 0, "ignorado": True}

    ts = _agora(agora_iso)
    vivos = {p["id"]: p for p in pendencias}

    abertas_antes = {l["id"] for l in con.execute(
        "SELECT id FROM pendencia_vida WHERE fechada_em IS NULL")}

    for pid, p in vivos.items():
        if pid in abertas_antes:
            con.execute("UPDATE pendencia_vida SET ultimo_em=?, gravidade=? WHERE id=?",
                        (ts, p.get("gravidade", "media"), pid))
        else:
            # O ON CONFLICT cobre tanto a estreia quanto a REABERTURA de uma
            # pendencia que estava fechada — nos dois casos o nascimento e agora.
            con.execute(
                "INSERT INTO pendencia_vida (id, regra, projeto, gravidade, visto_em, "
                "ultimo_em, fechada_em) VALUES (?,?,?,?,?,?,NULL) "
                "ON CONFLICT(id) DO UPDATE SET visto_em=excluded.visto_em, "
                "ultimo_em=excluded.ultimo_em, fechada_em=NULL, "
                "gravidade=excluded.gravidade, regra=excluded.regra, "
                "projeto=excluded.projeto",
                (pid, p.get("regra", ""), p.get("projeto", ""),
                 p.get("gravidade", "media"), ts, ts))

    sumiram = abertas_antes - set(vivos)
    for pid in sumiram:
        con.execute("UPDATE pendencia_vida SET fechada_em=? WHERE id=?", (ts, pid))

    conta = {g: sum(1 for p in pendencias if p.get("gravidade") == g)
             for g in GRAVIDADES}
    conta["total"] = len(pendencias)
    gravou = _retrato(con, conta, ts)
    con.commit()
    return {"abertas": conta, "fechadas_agora": len(sumiram), "retrato": gravou}


def _retrato(con, conta, ts) -> bool:
    """Grava o retrato numerico — mas so quando ele diz algo novo.

    A coleta roda de 60 em 60 s. Gravar quatro linhas por minuto para sempre sao
    5.760 linhas por dia, 2 milhoes por ano, quase todas identicas a anterior —
    e um grafico de semana feito de 10 mil pontos iguais nao mostra forma
    nenhuma. Entao: grava quando o numero MUDA, ou quando o ultimo retrato ja
    tem mais de uma hora (o batimento que garante pontos num dia parado).
    """
    ultimo = con.execute(
        "SELECT medido_em, valor FROM historico WHERE chave='abertas_total' "
        "ORDER BY medido_em DESC LIMIT 1").fetchone()
    if ultimo:
        mudou = float(ultimo["valor"]) != float(conta["total"])
        quando = _dt(ultimo["medido_em"])
        agora_dt = _dt(ts)
        velho = (not quando or not agora_dt
                 or (agora_dt - quando) >= timedelta(hours=BATIMENTO_H))
        if not mudou and not velho:
            return False
    for chave, valor in conta.items():
        con.execute("INSERT INTO historico (medido_em, chave, valor) VALUES (?,?,?)",
                    (ts, "abertas_" + chave, float(valor)))
    return True


def vidas(con, so_abertas=True) -> dict:
    """{id: {visto_em, ultimo_em, fechada_em, gravidade}}.

    So as ABERTAS por padrao, e isso importa para o custo: esta funcao roda no
    caminho de leitura do /api/dados, que a tela chama de 15 em 15 s por aba, e
    `pendencia_vida` nunca e podada. Trazer as fechadas junto seria uma varredura
    da tabela inteira, crescendo para sempre, para descartar quase tudo —
    `decorar()` so usa as que estao abertas agora. O indice ix_vida_aberta cobre
    exatamente este filtro.

    `so_abertas=False` existe para quem precisa auditar o historico (e para o
    teste conferir que a pendencia sumida foi mesmo marcada como fechada).
    """
    sql = ("SELECT id, visto_em, ultimo_em, fechada_em, gravidade FROM pendencia_vida"
           + (" WHERE fechada_em IS NULL" if so_abertas else ""))
    return {l["id"]: {"visto_em": l["visto_em"], "ultimo_em": l["ultimo_em"],
                      "fechada_em": l["fechada_em"], "gravidade": l["gravidade"]}
            for l in con.execute(sql)}


# ---------------------------------------------------------------- leitura
def desde(con):
    """O instante em que esta memoria comecou a existir. None se ainda nao ha."""
    return (con.execute("SELECT MIN(visto_em) FROM pendencia_vida").fetchone()
            or [None])[0]


def decorar(pendencias, vida_por_id, agora_iso=None, desde=None):
    """Copia das pendencias com `visto_em`, `dias`, `nova` e `desde_o_inicio`.

    Tres casos, e os tres importam:

      1. SEM registro de vida -> `dias` None, `nova` False. Nunca zero: zero e um
         numero, e numero errado no painel custa mais caro que numero ausente.
      2. Ja estava ali quando a memoria comecou (`visto_em` <= `desde`) -> idade
         real DESCONHECIDA, `desde_o_inicio` True. Esta e a armadilha da estreia:
         na primeira coleta depois desta mudanca, as 27 pendencias abertas ganham
         `visto_em` = agora, inclusive um grafo velho ha 23 dias. Sem esta trava
         a tela estrearia com 27 selos de "nova" mentindo em uniso.
      3. Nasceu depois -> a idade e medida, e abaixo de 24 h ela e "nova".
    """
    ref = _dt(_agora(agora_iso))
    inicio = _dt(desde)
    fora = []
    for p in pendencias:
        v = (vida_por_id or {}).get(p.get("id")) or {}
        nasceu = _dt(v.get("visto_em"))
        if not nasceu or not ref:
            dias, nova, do_inicio = None, False, False
        elif inicio and nasceu <= inicio:
            dias, nova, do_inicio = None, False, True
        else:
            horas = (ref - nasceu).total_seconds() / 3600.0
            dias, nova, do_inicio = (int(max(0.0, horas) // 24),
                                     horas < JANELA_NOVA_H, False)
        # Nao saber a idade exata nao e nao saber nada: a memoria sabe ha quanto
        # tempo ELA existe, e a pendencia que ja estava aqui na estreia tem no
        # minimo essa idade. "Aberta ha mais de 9 dias" prioriza; "ha mais tempo
        # do que eu lembro" so ocupa a linha.
        piso = 0
        if do_inicio and inicio and ref:
            piso = int(max(0.0, (ref - inicio).total_seconds() / 86400.0))
        fora.append(dict(p, visto_em=v.get("visto_em"), dias=dias, nova=nova,
                         desde_o_inicio=do_inicio, dias_min=piso))
    return fora


def _serie(con, chave, desde_iso):
    return [{"medido_em": l["medido_em"], "valor": l["valor"]} for l in con.execute(
        "SELECT medido_em, valor FROM historico WHERE chave=? AND medido_em>=? "
        "ORDER BY medido_em DESC LIMIT ?", (chave, desde_iso, PONTOS_SERIE))][::-1]


def tendencia(con, agora_iso=None) -> dict:
    """Novas, resolvidas, abertas por gravidade e para que lado a coisa anda."""
    ts = _agora(agora_iso)
    ref = _dt(ts) or datetime.now(timezone.utc)
    dia = (ref - timedelta(hours=JANELA_NOVA_H)).isoformat(timespec="seconds")
    semana = (ref - timedelta(days=JANELA_SEMANA_D)).isoformat(timespec="seconds")

    def um(sql, *a):
        return (con.execute(sql, a).fetchone() or [0])[0] or 0

    # `visto_em > inicio` e a trava da estreia: na primeira coleta todas as
    # pendencias nascem com o mesmo carimbo, e nenhuma delas e novidade — elas
    # ja estavam la, so nao havia quem lembrasse. Contar as 27 como "apareceram
    # nas ultimas 24 h" seria a primeira mentira da tela, no primeiro minuto.
    inicio = desde(con) or ""
    novas = um("SELECT COUNT(*) FROM pendencia_vida "
               "WHERE fechada_em IS NULL AND visto_em >= ? AND visto_em > ?",
               dia, inicio)
    fechadas_24h = um("SELECT COUNT(*) FROM pendencia_vida "
                      "WHERE fechada_em IS NOT NULL AND fechada_em >= ?", dia)
    resolvidas_7d = um("SELECT COUNT(*) FROM pendencia_vida "
                       "WHERE fechada_em IS NOT NULL AND fechada_em >= ?", semana)

    abertas = {g: um("SELECT COUNT(*) FROM pendencia_vida "
                     "WHERE fechada_em IS NULL AND gravidade = ?", g)
               for g in GRAVIDADES}
    abertas["total"] = sum(abertas[g] for g in GRAVIDADES)

    if novas > fechadas_24h:
        direcao = "piorando"
    elif fechadas_24h > novas:
        direcao = "melhorando"
    else:
        direcao = "estavel"

    return {"novas_24h": novas, "fechadas_24h": fechadas_24h,
            "resolvidas_7d": resolvidas_7d, "abertas": abertas, "direcao": direcao,
            "serie": _serie(con, "abertas_total", semana)}


# --------------------------------------------------------------- o briefing
def _saudacao(hora: int) -> str:
    if 5 <= hora <= 11:
        return "Bom dia"
    if 12 <= hora <= 17:
        return "Boa tarde"
    return "Boa noite"


def _pior(pendencias):
    """A que mais doi: primeiro a gravidade, so depois a idade.

    A ordem importa e nao e obvia. Uma pendencia media parada ha 30 dias parece
    mais urgente numa planilha; na pratica, CI vermelha de quatro dias bloqueia
    o trabalho de hoje e o grafo velho de trinta nao bloqueia nada.
    """
    if not pendencias:
        return None
    return sorted(pendencias,
                  key=lambda p: (ORDEM.get(p.get("gravidade"), 9),
                                 -(p.get("dias") if p.get("dias") is not None else -1),
                                 p.get("projeto") or ""))[0]


def _idade(p) -> str:
    d = p.get("dias")
    if d is None:
        piso = p.get("dias_min") or 0
        return (" (aberta há mais de %d dia%s)" % (piso, "" if piso == 1 else "s")
                if piso else "")
    if d == 0:
        return " (de hoje)"
    return " (aberta há %d dia%s)" % (d, "" if d == 1 else "s")


def _alvo(p) -> str:
    """O nome do projeto mais o texto — sem dizer o nome duas vezes.

    Quase todo texto de pendencia ja cita o projeto ("A CI do dents falhou"),
    entao prefixar sempre produziria "a pior e dents - A CI do dents falhou".
    """
    proj = p.get("projeto") or ""
    txt = (p.get("texto") or "").strip().rstrip(".")
    if len(txt) > 90:
        txt = txt[:87].rstrip() + "..."
    if proj and proj.lower() not in txt.lower():
        return "%s — %s" % (proj, txt)
    return txt or proj


def briefing(pendencias, tend, hora=None) -> str:
    """Uma frase honesta sobre o dia. Funcao pura: entra dado, sai texto.

    A trava que separa briefing util de enfeite esta em duas regras:
      - com pendencia ALTA aberta, o texto NUNCA diz que esta tudo certo;
      - o texto sempre cita numero e nome de projeto, nunca fica no generico.
    Frase que nao muda quando o dado muda e decoracao, e decoracao no topo de um
    painel operacional e pior que espaco vazio: ensina a nao ler o topo.
    """
    if hora is None:
        hora = datetime.now().hour
    saud = _saudacao(hora)
    ab = (tend or {}).get("abertas") or {}
    resolvidas = (tend or {}).get("resolvidas_7d") or 0
    novas = (tend or {}).get("novas_24h") or 0

    feito = (" Você fechou %d nos últimos %d dias." % (resolvidas, JANELA_SEMANA_D)
             if resolvidas else "")

    if not pendencias:
        return ("%s. Nada pendente nos seus projetos.%s" % (saud, feito)).strip()

    altas = [p for p in pendencias if p.get("gravidade") == "alta"]
    pior = _pior(pendencias)

    if altas:
        cabeca = ("%s. %d coisa%s pede%s você agora."
                  % (saud, len(altas), "" if len(altas) == 1 else "s",
                     "" if len(altas) == 1 else "m"))
        corpo = " A mais grave: %s%s." % (_alvo(pior), _idade(pior))
    else:
        n = ab.get("total") or len(pendencias)
        cabeca = ("%s. Nada urgente — %d coisa%s de menor prioridade esperando."
                  % (saud, n, "" if n == 1 else "s"))
        corpo = " A mais antiga: %s%s." % (_alvo(pior), _idade(pior))

    aviso = ""
    if novas and (tend or {}).get("direcao") == "piorando":
        aviso = (" %s nas últimas 24 h."
                 % ("1 apareceu" if novas == 1 else "%d apareceram" % novas))
    return (cabeca + corpo + aviso + feito).strip()
