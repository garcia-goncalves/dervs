# -*- coding: utf-8 -*-
"""Banco do HUB — SQLite, uma verdade so.

Substitui o dados.json. Tres motivos, na ordem em que importam:

  1. CARIMBO POR CAMADA. Git/Docker sao medidos de minuto em minuto; GitHub a
     cada 20 min; npm audit uma vez por dia. Num JSON unico o numero velho fica
     indistinguivel do novo, e painel que mente uma vez perde o dono para sempre.
  2. HISTORICO. O consumo de minutos do Actions ao longo do tempo so existe se
     alguem guardar. JSON sobrescrito nao guarda nada.
  3. NAO CORROMPE. Duas coletas escrevendo ao mesmo tempo num JSON produzem
     arquivo pela metade. Esta maquina ja congelou duas vezes esta semana.

Uma linha por (projeto, camada). O valor e JSON — o SQLite aqui e o carimbo, a
concorrencia e o historico, nao o esquema.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BANCO = AQUI / "hub.db"

INFRA = "_infra"          # projeto sintetico: containers e portas da maquina
QUOTA = "_quota"          # projeto sintetico: cota de minutos do Actions, da CONTA
CAMADAS = ("local", "github", "pesado")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS medida (
    projeto   TEXT NOT NULL,
    camada    TEXT NOT NULL,
    medido_em TEXT NOT NULL,
    dados     TEXT NOT NULL,
    PRIMARY KEY (projeto, camada)
);

CREATE TABLE IF NOT EXISTS historico (
    medido_em TEXT NOT NULL,
    chave     TEXT NOT NULL,
    valor     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_historico ON historico (chave, medido_em);

-- Silenciar uma pendencia e decisao do dono, nao do coletor: por isso vive no
-- banco e sobrevive a recoleta.
CREATE TABLE IF NOT EXISTS pendencia_estado (
    id             TEXT PRIMARY KEY,
    silenciada_ate TEXT,
    anotado_em     TEXT NOT NULL
);

-- A vida de cada pendencia: quando nasceu, quando foi vista pela ultima vez e
-- quando sumiu. E o que permite a tela dizer "aberta ha 23 dias" e "voce fechou
-- 6 esta semana" — sem isto o painel acorda todo dia sem lembrar de ontem.
--
-- Tabela SEPARADA da pendencia_estado de proposito: aquela guarda decisao do
-- dono (silenciar), esta guarda observacao do coletor. Misturar as duas faria
-- um `DELETE` de faxina apagar a escolha dele junto com a medicao.
CREATE TABLE IF NOT EXISTS pendencia_vida (
    id         TEXT PRIMARY KEY,
    regra      TEXT NOT NULL DEFAULT '',
    projeto    TEXT NOT NULL DEFAULT '',
    gravidade  TEXT NOT NULL DEFAULT 'media',
    visto_em   TEXT NOT NULL,
    ultimo_em  TEXT NOT NULL,
    fechada_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_vida_aberta ON pendencia_vida (fechada_em, visto_em);

-- A fila do que o painel conserta sozinho. O `id` e o mesmo id estavel da
-- pendencia (regra:projeto): e o que faz um item reentrar sem duplicar e o
-- que amarra a fila ao "esconder por 24 h" que ja existe.
--
-- `terminado_em` fica em UTC como todo o resto. O TETO DIARIO, nao: ele usa a
-- data local (fila.hoje_local). Em UTC-3, as 21h de terca ja e quarta em UTC —
-- o teto zeraria tres horas cedo e ninguem entenderia por que.
CREATE TABLE IF NOT EXISTS fila (
    id           TEXT PRIMARY KEY,
    projeto      TEXT NOT NULL DEFAULT '',
    regra        TEXT NOT NULL DEFAULT '',
    gravidade    TEXT NOT NULL DEFAULT 'media',
    risco        REAL NOT NULL DEFAULT 0,
    trilho       TEXT NOT NULL DEFAULT '',
    estado       TEXT NOT NULL DEFAULT 'esperando',
    tentativas   INTEGER NOT NULL DEFAULT 0,
    criado_em    TEXT NOT NULL,
    iniciado_em  TEXT,
    terminado_em TEXT,
    custo_usd    REAL NOT NULL DEFAULT 0.0,
    pr_url       TEXT,
    erro         TEXT
);
CREATE INDEX IF NOT EXISTS ix_fila_dia ON fila (terminado_em);
"""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(BANCO, timeout=15)
    con.row_factory = sqlite3.Row
    # WAL: o servidor le enquanto o coletor escreve, sem um travar o outro.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=15000")
    con.executescript(ESQUEMA)
    return con


def gravar(projeto: str, camada: str, dados: dict, con=None) -> None:
    fechar = con is None
    con = con or conectar()
    try:
        con.execute(
            "INSERT INTO medida (projeto, camada, medido_em, dados) VALUES (?,?,?,?) "
            "ON CONFLICT(projeto, camada) DO UPDATE SET medido_em=excluded.medido_em, "
            "dados=excluded.dados",
            (projeto, camada, agora(), json.dumps(dados, ensure_ascii=False)),
        )
        con.commit()
    finally:
        if fechar:
            con.close()


def ler_tudo(con=None) -> dict:
    """Devolve {projeto: {camada: {"medido_em": iso, "dados": {...}}}}."""
    fechar = con is None
    con = con or conectar()
    try:
        fora: dict = {}
        for l in con.execute("SELECT projeto, camada, medido_em, dados FROM medida"):
            fora.setdefault(l["projeto"], {})[l["camada"]] = {
                "medido_em": l["medido_em"],
                "dados": json.loads(l["dados"]),
            }
        return fora
    finally:
        if fechar:
            con.close()


def montar_estado(con=None) -> dict:
    """As tres camadas remontadas no formato que o motor de regras consome.

    Cada camada carrega o proprio "medido_em". E o que permite a tela dizer
    "medido ha 40 s" no numero do git e "ha 12 min" no numero do GitHub, em vez
    de um carimbo unico que mente sobre metade dos valores.
    """
    fechar = con is None
    con = con or conectar()
    try:
        tudo = ler_tudo(con)
        infra = tudo.pop(INFRA, {}).get("local", {})
        projetos = []
        for nome, camadas in sorted(tudo.items()):
            local = camadas.get("local")
            if not local or "nome" not in local["dados"]:
                continue                    # so a camada local define um projeto
            p = dict(local["dados"])
            p["medido_em"] = {"local": local["medido_em"]}
            for extra in ("github", "pesado"):
                if extra in camadas:
                    p[extra] = camadas[extra]["dados"]
                    p["medido_em"][extra] = camadas[extra]["medido_em"]
                else:
                    p.setdefault(extra, None)
            projetos.append(p)
        return {
            "projetos": projetos,
            "infra": infra.get("dados", {}),
            "infra_medido_em": infra.get("medido_em"),
            "quota": (tudo.get(QUOTA) or {}).get("pesado", {}).get("dados"),
        }
    finally:
        if fechar:
            con.close()


def anotar_historico(chave: str, valor: float, con=None) -> None:
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("INSERT INTO historico (medido_em, chave, valor) VALUES (?,?,?)",
                    (agora(), chave, float(valor)))
        con.commit()
    finally:
        if fechar:
            con.close()


def silenciadas(con=None) -> dict:
    fechar = con is None
    con = con or conectar()
    try:
        agora_iso = agora()
        return {l["id"]: l["silenciada_ate"] for l in
                con.execute("SELECT id, silenciada_ate FROM pendencia_estado "
                            "WHERE silenciada_ate IS NOT NULL AND silenciada_ate > ?",
                            (agora_iso,))}
    finally:
        if fechar:
            con.close()


def silenciar(pid: str, ate_iso: str, con=None) -> None:
    fechar = con is None
    con = con or conectar()
    try:
        con.execute(
            "INSERT INTO pendencia_estado (id, silenciada_ate, anotado_em) VALUES (?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET silenciada_ate=excluded.silenciada_ate, "
            "anotado_em=excluded.anotado_em",
            (pid, ate_iso, agora()))
        con.commit()
    finally:
        if fechar:
            con.close()
COLUNAS_FILA = ("projeto", "regra", "gravidade", "risco", "trilho", "estado",
                "tentativas", "iniciado_em", "terminado_em", "custo_usd",
                "pr_url", "erro")


def enfileirar(pendencias: list, con=None) -> int:
    """Insere as pendencias que ainda nao estao na fila. Devolve quantas entraram."""
    fechar = con is None
    con = con or conectar()
    entraram = 0
    try:
        for p in pendencias or []:
            cur = con.execute(
                "INSERT OR IGNORE INTO fila (id, projeto, regra, gravidade, risco,"
                " trilho, criado_em) VALUES (?,?,?,?,?,?,?)",
                (p.get("id") or "", p.get("projeto") or "", p.get("regra") or "",
                 p.get("gravidade") or "media", float(p.get("risco") or 0),
                 p.get("trilho") or "", agora()))
            entraram += cur.rowcount or 0
        con.commit()
    finally:
        if fechar:
            con.close()
    return entraram


def fila_aberta(con=None) -> list:
    """Tudo que ainda nao terminou em `ok`, do mais grave para o menos."""
    fechar = con is None
    con = con or conectar()
    try:
        linhas = con.execute(
            "SELECT * FROM fila WHERE estado <> 'ok' ORDER BY criado_em").fetchall()
        return [dict(l) for l in linhas]
    finally:
        if fechar:
            con.close()


def marcar_fila(id_: str, con=None, **campos) -> None:
    """Atualiza colunas nomeadas de um item. Coluna desconhecida e erro, nao silencio."""
    desconhecidas = set(campos) - set(COLUNAS_FILA)
    if desconhecidas:
        raise ValueError("coluna de fila desconhecida: %s" % ", ".join(sorted(desconhecidas)))
    if not campos:
        return
    fechar = con is None
    con = con or conectar()
    try:
        pedaco = ", ".join("%s = ?" % c for c in campos)
        con.execute("UPDATE fila SET %s WHERE id = ?" % pedaco,
                    list(campos.values()) + [id_])
        con.commit()
    finally:
        if fechar:
            con.close()


def gasto_entre(inicio_iso: str, fim_iso: str, con=None) -> float:
    """Soma o custo dos itens terminados na JANELA [inicio, fim) — ambos em UTC.

    Existe porque `gasto_do_dia` compara PREFIXO de data, e o dia do dono nao e
    o dia do UTC. Em UTC-3, um item terminado as 22h de terca carimba quarta em
    UTC: o prefixo nao bate, a soma volta zero e o teto NUNCA fecha entre 21h e
    meia-noite. Quem manda a janela e `fila.janela_local_em_utc`.
    """
    fechar = con is None
    con = con or conectar()
    try:
        linha = con.execute(
            "SELECT COALESCE(SUM(custo_usd), 0.0) AS total FROM fila"
            " WHERE terminado_em IS NOT NULL AND terminado_em >= ?"
            " AND terminado_em < ?", (inicio_iso, fim_iso)).fetchone()
        return float(linha["total"] or 0.0)
    finally:
        if fechar:
            con.close()


def gasto_do_dia(dia: str, con=None) -> float:
    """Soma o custo dos itens TERMINADOS no dia (AAAA-MM-DD, comparado em UTC)."""
    fechar = con is None
    con = con or conectar()
    try:
        linha = con.execute(
            "SELECT COALESCE(SUM(custo_usd), 0.0) AS total FROM fila"
            " WHERE terminado_em IS NOT NULL AND substr(terminado_em, 1, 10) = ?",
            (dia,)).fetchone()
        return float(linha["total"] or 0.0)
    finally:
        if fechar:
            con.close()
