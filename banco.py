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
