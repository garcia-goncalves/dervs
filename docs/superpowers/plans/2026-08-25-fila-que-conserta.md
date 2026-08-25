# A fila que conserta — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o botão Resolver — uma execução por vez, disparada a dedo — numa fila que trabalha desacompanhada dentro de um cerco de quatro travas verificadas em código.

**Architecture:** Três trilhos. O Renovate cuida das dependências npm fora do painel, de graça. Uma tabela `fila` no `hub.db` guarda os itens; `fila.py` concentra as decisões puras (elegibilidade, ordem, teto, anti-laço, travas do diff) e o laço; `execucao.py` continua sendo o único que dispara o Claude. O laço recebe os executores por parâmetro — `fila.py` não importa `servir.py`, e por isso os testes rodam sem servidor no ar.

**Tech Stack:** Python 3.12 da biblioteca padrão. `unittest`. SQLite via `banco.py`. Zero dependência externa, zero build — é a virtude declarada deste projeto e nenhuma tarefa pode quebrá-la.

**Spec:** `docs/superpowers/specs/2026-08-25-fila-que-conserta-design.md`

## Global Constraints

- **Zero dependência nova e zero build.** Nenhuma tarefa instala pacote. Testes em `unittest` da biblioteca padrão.
- **Este repositório é MISTO de fim de linha.** `servir.py`, `banco.py`, `execucao.py`, `README.md`, `test_regras.py`, `test_coletar.py` são CRLF; `regras.py`, `coletar.py`, `coletar_github.py`, `memoria.py`, `index.html`, `test_memoria.py` são LF. **Preserve o de cada arquivo.** Arquivo novo (`fila.py`, `test_fila.py`) nasce LF.
- **Nunca escrever conteúdo com acento por `sys.stdin.read()` dentro de script Python no Windows** — corrompe (o bash manda UTF-8, o Python decodifica cp1252). Conteúdo acentuado vai por arquivo e se lê com `read_bytes().decode('utf-8')`.
- **Limpe `__pycache__` antes de investigar qualquer suspeita de codificação** — cache velho mente sobre encoding.
- Textos visíveis ao dono em **português do Brasil**. Mensagens de commit em `tipo(escopo):`.
- Dinheiro sempre em reais na tela, com vírgula decimal, via `execucao.em_reais()`.
- Toda função de decisão é **pura**: entra dicionário, sai veredito. É o padrão de `regras.py` e é o que torna o teste barato.
- Motivo de recusa é **string em português, vazia quando aprovado** — mesmo padrão de `execucao.classificar_falha`. Nunca `bool` nu, porque a tela precisa dizer *por quê*.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Ação |
|---|---|---|
| `fila.py` | As decisões puras da fila e o laço que as aplica. Não importa `servir.py`. | **Criar** (~260 linhas) |
| `test_fila.py` | A suíte da fila. `python test_fila.py`. | **Criar** (~420 linhas) |
| `banco.py` | Ganha a tabela `fila` e as funções de persistência dela. Toda persistência mora aqui — é o padrão da casa. | Modificar (`ESQUEMA`, linha 31; funções ao fim) |
| `servir.py` | Dois endpoints novos e os dados da fila na resposta de `/api/dados`. Passa os executores para `fila.trabalhar`. | Modificar |
| `execucao.py` | As duas travas de diff entram antes de publicar. | Modificar (`_fechar_com_pedido_de_alteracao`, linha 791) |
| `index.html` | A faixa da fila acima da caixa de pendências. | Modificar |
| `renovate.json` | Um por repositório-alvo. Fora deste repositório. | **Criar** (4×) |
| `README.md` | Seção nova. Entra no mesmo commit da mudança que descreve. | Modificar |

---

## Task 1: A tabela `fila` e a persistência

**Files:**
- Modify: `banco.py:31` (constante `ESQUEMA`) e fim do arquivo
- Test: `test_fila.py` (criar)

**Interfaces:**
- Consumes: `banco.conectar()`, `banco.agora()` — já existem.
- Produces:
  - `banco.enfileirar(pendencias: list, con=None) -> int` — insere as que faltam, devolve quantas entraram. Não duplica: `id` é chave primária.
  - `banco.fila_aberta(con=None) -> list[dict]` — todos os itens que não terminaram em `ok`.
  - `banco.marcar_fila(id_: str, con=None, **campos) -> None` — atualiza colunas nomeadas de um item.
  - `banco.gasto_do_dia(dia: str, con=None) -> float` — soma `custo_usd` dos itens terminados naquele dia. `dia` no formato `AAAA-MM-DD`.

**Decisão de fuso, e ela importa:** o resto do banco carimba em UTC (`banco.agora()`). O teto diário **usa a data local**, não a UTC. Motivo concreto: em UTC−3, às 21h de terça já é quarta em UTC — o teto zeraria três horas cedo, sem ninguém entender por quê. A coluna `terminado_em` continua em UTC; quem converte é `fila.hoje_local()`.

**Risco aceito e documentado:** `hub.db` é descartável. Apagar o banco no meio do dia zera o gasto acumulado e devolve os R$ 50 inteiros. É ato deliberado do dono, não acidente — fica registrado no README, não vira código.

- [ ] **Step 1: Escrever o teste que falha**

Criar `test_fila.py` (fim de linha LF):

```python
"""Testes da fila que conserta. `python test_fila.py`."""
import os
import tempfile
import unittest
from pathlib import Path

import banco


class BancoTemporario(unittest.TestCase):
    """Cada teste com seu proprio hub.db, jogado fora no fim."""

    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.antigo = banco.BANCO
        banco.BANCO = Path(self.pasta.name) / "hub.db"

    def tearDown(self):
        banco.BANCO = self.antigo
        self.pasta.cleanup()


class Enfileirar(BancoTemporario):

    def _pendencia(self, id_="memoria_crlf:dents", projeto="dents",
                   regra="memoria_crlf", gravidade="alta"):
        return {"id": id_, "projeto": projeto, "regra": regra,
                "gravidade": gravidade, "risco": 0}

    def test_insere_o_que_nao_existe(self):
        entraram = banco.enfileirar([self._pendencia()])
        self.assertEqual(entraram, 1)
        self.assertEqual(len(banco.fila_aberta()), 1)

    def test_nao_duplica_o_mesmo_id(self):
        banco.enfileirar([self._pendencia()])
        entraram = banco.enfileirar([self._pendencia()])
        self.assertEqual(entraram, 0)
        self.assertEqual(len(banco.fila_aberta()), 1)

    def test_item_nasce_esperando_com_zero_tentativas(self):
        banco.enfileirar([self._pendencia()])
        item = banco.fila_aberta()[0]
        self.assertEqual(item["estado"], "esperando")
        self.assertEqual(item["tentativas"], 0)
        self.assertEqual(item["custo_usd"], 0.0)

    def test_terminado_em_ok_sai_da_fila_aberta(self):
        banco.enfileirar([self._pendencia()])
        banco.marcar_fila("memoria_crlf:dents", estado="ok",
                          terminado_em="2026-08-25T12:00:00+00:00")
        self.assertEqual(banco.fila_aberta(), [])

    def test_falha_continua_na_fila_aberta(self):
        banco.enfileirar([self._pendencia()])
        banco.marcar_fila("memoria_crlf:dents", estado="falha",
                          terminado_em="2026-08-25T12:00:00+00:00")
        self.assertEqual(len(banco.fila_aberta()), 1)


class GastoDoDia(BancoTemporario):

    def _terminar(self, id_, custo, quando):
        banco.enfileirar([{"id": id_, "projeto": "x", "regra": "env_drift",
                           "gravidade": "media", "risco": 0}])
        banco.marcar_fila(id_, estado="ok", custo_usd=custo, terminado_em=quando)

    def test_dia_sem_nada_e_zero(self):
        self.assertEqual(banco.gasto_do_dia("2026-08-25"), 0.0)

    def test_soma_so_o_dia_pedido(self):
        self._terminar("a:1", 1.50, "2026-08-25T10:00:00+00:00")
        self._terminar("b:1", 0.50, "2026-08-25T18:00:00+00:00")
        self._terminar("c:1", 9.99, "2026-08-24T10:00:00+00:00")
        self.assertAlmostEqual(banco.gasto_do_dia("2026-08-25"), 2.00, places=6)

    def test_item_nao_terminado_nao_conta(self):
        banco.enfileirar([{"id": "d:1", "projeto": "x", "regra": "env_drift",
                           "gravidade": "media", "risco": 0}])
        banco.marcar_fila("d:1", estado="rodando", custo_usd=3.0)
        self.assertEqual(banco.gasto_do_dia("2026-08-25"), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py
```

Esperado: `AttributeError: module 'banco' has no attribute 'enfileirar'`. Se falhar por outro motivo, pare e leia — o teste está errado, não o código.

- [ ] **Step 3: A tabela**

Em `banco.py`, ao fim da constante `ESQUEMA` (antes das aspas triplas de fechamento, hoje na linha 71). **Preserve o CRLF do arquivo.**

```sql
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
```

- [ ] **Step 4: As quatro funções**

Ao fim de `banco.py`:

```python
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
```

- [ ] **Step 5: Rodar e confirmar que passa**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py
```

Esperado: `OK`, 11 testes.

- [ ] **Step 6: Confirmar que nada mais quebrou**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && for s in regras coletar execucao servir memoria; do echo "--- $s"; python test_$s.py 2>&1 | tail -2; done
```

Esperado: `OK` em todas as cinco.

- [ ] **Step 7: Commit**

```bash
git add banco.py test_fila.py
git commit -m "feat(fila): a tabela e a persistencia da fila

O id e o mesmo id estavel da pendencia (regra:projeto): reentra sem duplicar e
continua valendo o esconder por 24 h.

terminado_em fica em UTC como o resto do banco. O teto diario NAO: usa data
local. Em UTC-3, as 21h de terca ja e quarta em UTC e o teto zeraria tres horas
cedo, sem ninguem entender.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Elegibilidade, trilho e ordem

**Files:**
- Create: `fila.py`
- Test: `test_fila.py` (acrescentar)

**Interfaces:**
- Consumes: `execucao.PROJETOS_BLOQUEADOS` — **reaproveitar, nunca redigitar a lista**. Duas listas de projeto bloqueado divergem no primeiro dia.
- Produces:
  - `fila.REGRAS_MECANICAS: dict[str, str]` — regra → trilho.
  - `fila.trilho_de(pendencia: dict) -> str` — `"mecanico"` | `"claude"` | `""` (não elegível).
  - `fila.elegiveis(pendencias: list) -> list[dict]` — as elegíveis, cada uma com a chave `trilho` preenchida.
  - `fila.ORDEM: dict[str, int]` — gravidade → posição.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `test_fila.py`, antes do `if __name__`:

```python
import fila


class Elegibilidade(unittest.TestCase):

    def _p(self, regra, projeto="dents"):
        return {"id": "%s:%s" % (regra, projeto), "regra": regra,
                "projeto": projeto, "gravidade": "media", "risco": 0}

    def test_memoria_crlf_vai_pelo_trilho_mecanico(self):
        self.assertEqual(fila.trilho_de(self._p("memoria_crlf")), "mecanico")

    def test_env_drift_vai_pelo_claude(self):
        self.assertEqual(fila.trilho_de(self._p("env_drift")), "claude")

    def test_dependencia_insegura_vai_pelo_claude(self):
        self.assertEqual(fila.trilho_de(self._p("dependencia_insegura")), "claude")

    def test_ci_vermelha_fica_de_fora(self):
        self.assertEqual(fila.trilho_de(self._p("ci_vermelha")), "")

    def test_grafo_velho_fica_de_fora(self):
        self.assertEqual(fila.trilho_de(self._p("grafo_velho")), "")

    def test_sem_remoto_fica_de_fora(self):
        self.assertEqual(fila.trilho_de(self._p("sem_remoto")), "")

    def test_projeto_bloqueado_nao_entra_nem_com_regra_aceita(self):
        bloqueado = sorted(fila.execucao.PROJETOS_BLOQUEADOS)[0]
        self.assertEqual(fila.trilho_de(self._p("memoria_crlf", bloqueado)), "")

    def test_bloqueio_ignora_caixa_alta(self):
        bloqueado = sorted(fila.execucao.PROJETOS_BLOQUEADOS)[0].upper()
        self.assertEqual(fila.trilho_de(self._p("memoria_crlf", bloqueado)), "")

    def test_pendencia_sem_projeto_nao_tem_onde_agir(self):
        self.assertEqual(fila.trilho_de(self._p("memoria_crlf", "")), "")

    def test_elegiveis_carimba_o_trilho(self):
        saida = fila.elegiveis([self._p("memoria_crlf"), self._p("ci_vermelha")])
        self.assertEqual(len(saida), 1)
        self.assertEqual(saida[0]["trilho"], "mecanico")

    def test_elegiveis_nao_altera_a_lista_recebida(self):
        entrada = [self._p("memoria_crlf")]
        fila.elegiveis(entrada)
        self.assertNotIn("trilho", entrada[0])
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `ModuleNotFoundError: No module named 'fila'`.

- [ ] **Step 3: Criar `fila.py`**

Arquivo novo, fim de linha **LF**:

```python
"""A fila que conserta.

O painel deixa de so apontar. As decisoes aqui sao PURAS — entra dicionario,
sai veredito — como em `regras.py`, e por isso custam pouco para testar.

O cerco tem quatro travas, todas verificadas em codigo:
teto diario, anti-laco, teste apagado e segredo no .env.example. Nenhuma delas
e uma instrucao no texto do pedido: instrucao em texto e sugestao, nao trava.
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
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `OK`, 22 testes.

- [ ] **Step 5: Commit**

```bash
git add fila.py test_fila.py
git commit -m "feat(fila): lista branca de regras e o trilho de cada uma

Tres regras entram, treze ficam de fora — cada uma com o motivo escrito no
codigo, porque em seis meses ninguem lembra por que grafo_velho nao esta la.

PROJETOS_BLOQUEADOS vem de execucao.py, nao redigitada: duas listas de projeto
bloqueado divergem no primeiro dia.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: O teto diário

**Files:**
- Modify: `fila.py`
- Test: `test_fila.py`

**Interfaces:**
- Consumes: `execucao.USD_BRL`, `execucao.em_reais()`, `banco.gasto_do_dia()`.
- Produces:
  - `fila.TETO_DIARIO_BRL: float` = `50.00`
  - `fila.hoje_local() -> str` — data local em `AAAA-MM-DD`.
  - `fila.cabe_no_teto(gasto_usd: float) -> bool`
  - `fila.quanto_falta(gasto_usd: float) -> float` — em reais, nunca negativo.

- [ ] **Step 1: Escrever o teste que falha**

```python
class TetoDiario(unittest.TestCase):

    def test_sem_gasto_cabe(self):
        self.assertTrue(fila.cabe_no_teto(0.0))

    def test_vespera_do_teto_ainda_cabe(self):
        quase = (fila.TETO_DIARIO_BRL - 0.01) / execucao.USD_BRL
        self.assertTrue(fila.cabe_no_teto(quase))

    def test_exatamente_no_teto_nao_cabe(self):
        no_ponto = fila.TETO_DIARIO_BRL / execucao.USD_BRL
        self.assertFalse(fila.cabe_no_teto(no_ponto))

    def test_passou_do_teto_nao_cabe(self):
        self.assertFalse(fila.cabe_no_teto(fila.TETO_DIARIO_BRL))

    def test_quanto_falta_nunca_e_negativo(self):
        self.assertEqual(fila.quanto_falta(999.0), 0.0)

    def test_quanto_falta_sem_gasto_e_o_teto_inteiro(self):
        self.assertAlmostEqual(fila.quanto_falta(0.0), fila.TETO_DIARIO_BRL, places=2)

    def test_hoje_local_tem_formato_de_data(self):
        hoje = fila.hoje_local()
        self.assertEqual(len(hoje), 10)
        self.assertEqual(hoje[4], "-")
        self.assertEqual(hoje[7], "-")
```

Acrescentar `import execucao` ao topo de `test_fila.py`.

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `AttributeError: module 'fila' has no attribute 'cabe_no_teto'`.

- [ ] **Step 3: Implementar**

Em `fila.py`, depois de `ORDEM`:

```python
from datetime import datetime

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
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `OK`, 29 testes.

- [ ] **Step 5: Commit**

```bash
git add fila.py test_fila.py
git commit -m "feat(fila): teto de R\$ 50 por dia, na data LOCAL

Fila desacompanhada gasta sem ninguem olhando. No ponto exato do teto ja nao
cabe mais um: 'so mais um' e como conta de R\$ 300 acontece.

A data e a local de proposito. Em UTC-3, as 21h de terca ja e quarta em UTC — o
teto zeraria tres horas cedo e a surpresa seria de madrugada.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: O anti-laço

**Files:**
- Modify: `fila.py`
- Test: `test_fila.py`

**Interfaces:**
- Produces:
  - `fila.MAX_TENTATIVAS: int` = `2`
  - `fila.pode_tentar(item: dict, hoje: str) -> bool`
  - `fila.proximo(itens: list, gasto_usd: float, hoje: str) -> dict | None`

- [ ] **Step 1: Escrever o teste que falha**

```python
class AntiLaco(unittest.TestCase):

    def _item(self, **campos):
        base = {"id": "env_drift:dents", "projeto": "dents", "regra": "env_drift",
                "gravidade": "media", "risco": 0, "trilho": "claude",
                "estado": "esperando", "tentativas": 0, "terminado_em": None}
        base.update(campos)
        return base

    def test_primeira_tentativa_pode(self):
        self.assertTrue(fila.pode_tentar(self._item(tentativas=0), "2026-08-25"))

    def test_segunda_tentativa_pode(self):
        self.assertTrue(fila.pode_tentar(self._item(tentativas=1), "2026-08-25"))

    def test_terceira_tentativa_nao_pode(self):
        self.assertFalse(fila.pode_tentar(self._item(tentativas=2), "2026-08-25"))

    def test_falha_de_hoje_nao_volta_hoje(self):
        item = self._item(estado="falha", tentativas=1,
                          terminado_em="2026-08-25T14:00:00+00:00")
        self.assertFalse(fila.pode_tentar(item, "2026-08-25"))

    def test_falha_de_ontem_volta_hoje(self):
        item = self._item(estado="falha", tentativas=1,
                          terminado_em="2026-08-24T14:00:00+00:00")
        self.assertTrue(fila.pode_tentar(item, "2026-08-25"))


class Proximo(unittest.TestCase):

    def _item(self, id_, gravidade="media", risco=0, **campos):
        base = {"id": id_, "projeto": id_.split(":")[-1], "regra": "env_drift",
                "gravidade": gravidade, "risco": risco, "trilho": "claude",
                "estado": "esperando", "tentativas": 0, "terminado_em": None}
        base.update(campos)
        return base

    def test_fila_vazia_devolve_nada(self):
        self.assertIsNone(fila.proximo([], 0.0, "2026-08-25"))

    def test_grave_vem_antes(self):
        itens = [self._item("a:zz", "baixa"), self._item("b:aa", "alta")]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["id"], "b:aa")

    def test_dentro_da_gravidade_o_risco_desempata(self):
        itens = [self._item("a:aa", "alta", risco=0),
                 self._item("b:zz", "alta", risco=100)]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["id"], "b:zz")

    def test_risco_nao_atravessa_gravidade(self):
        itens = [self._item("a:aa", "media", risco=100),
                 self._item("b:zz", "alta", risco=0)]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["id"], "b:zz")

    def test_empate_total_ordena_pelo_projeto(self):
        itens = [self._item("a:zz", "alta"), self._item("b:aa", "alta")]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["projeto"], "aa")

    def test_teto_estourado_devolve_nada_mesmo_com_fila_cheia(self):
        itens = [self._item("a:aa", "alta")]
        self.assertIsNone(fila.proximo(itens, 999.0, "2026-08-25"))

    def test_item_rodando_nao_e_escolhido_de_novo(self):
        itens = [self._item("a:aa", "alta", estado="rodando")]
        self.assertIsNone(fila.proximo(itens, 0.0, "2026-08-25"))

    def test_item_esgotado_e_pulado_e_o_seguinte_entra(self):
        itens = [self._item("a:aa", "alta", tentativas=2),
                 self._item("b:bb", "baixa")]
        self.assertEqual(fila.proximo(itens, 0.0, "2026-08-25")["id"], "b:bb")
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `AttributeError: module 'fila' has no attribute 'pode_tentar'`.

- [ ] **Step 3: Implementar**

```python
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
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `OK`, 42 testes.

- [ ] **Step 5: Commit**

```bash
git add fila.py test_fila.py
git commit -m "feat(fila): anti-laco e a ordem de atendimento

Duas tentativas por item, e falha de hoje nao volta hoje. Sem isso, uma
correcao que nao pega vira torneira aberta de madrugada.

proximo() escolhe e nao faz. Separar as duas coisas e o que torna a ordem
testavel sem processo, sem rede e sem gastar um centavo.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: A trava do teste apagado

**Files:**
- Modify: `fila.py`
- Test: `test_fila.py`

**Interfaces:**
- Produces: `fila.diff_mexeu_em_teste(diff: str) -> str` — `""` se limpo, senão o motivo em português.

**Por que esta trava existe:** "consertar a CI vermelha" é o caso mais valioso da fila e o único em que apagar o teste *parece* uma correção. Enquanto esta trava não tiver histórico, `ci_vermelha` fica fora da lista branca.

- [ ] **Step 1: Escrever o teste que falha**

```python
class TesteApagado(unittest.TestCase):

    def test_diff_limpo_passa(self):
        diff = ("diff --git a/regras.py b/regras.py\n"
                "--- a/regras.py\n+++ b/regras.py\n"
                "@@ -1,2 +1,2 @@\n-antigo\n+novo\n")
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_apagar_test_py_reprova(self):
        diff = ("diff --git a/test_regras.py b/test_regras.py\n"
                "deleted file mode 100644\n"
                "--- a/test_regras.py\n+++ /dev/null\n")
        self.assertIn("test_regras.py", fila.diff_mexeu_em_teste(diff))

    def test_apagar_spec_ts_reprova(self):
        diff = ("--- a/src/login.spec.ts\n+++ /dev/null\n")
        self.assertIn("login.spec.ts", fila.diff_mexeu_em_teste(diff))

    def test_apagar_dot_test_js_reprova(self):
        diff = ("--- a/src/soma.test.js\n+++ /dev/null\n")
        self.assertIn("soma.test.js", fila.diff_mexeu_em_teste(diff))

    def test_apagar_arquivo_comum_passa(self):
        diff = ("--- a/README.md\n+++ /dev/null\n")
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_adicionar_arquivo_de_teste_passa(self):
        diff = ("--- /dev/null\n+++ b/test_novo.py\n+def test_x(): pass\n")
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_unittest_skip_reprova(self):
        diff = "+    @unittest.skip('quebrado')\n"
        self.assertIn("unittest.skip", fila.diff_mexeu_em_teste(diff))

    def test_pytest_mark_skip_reprova(self):
        diff = "+@pytest.mark.skip\n"
        self.assertIn("pytest.mark.skip", fila.diff_mexeu_em_teste(diff))

    def test_it_skip_reprova(self):
        diff = "+  it.skip('faz coisa', () => {})\n"
        self.assertIn("it.skip(", fila.diff_mexeu_em_teste(diff))

    def test_xit_reprova(self):
        diff = "+  xit('faz coisa', () => {})\n"
        self.assertIn("xit(", fila.diff_mexeu_em_teste(diff))

    def test_skip_em_linha_REMOVIDA_passa(self):
        """Tirar um skip e o oposto de burlar: e religar o teste."""
        diff = "-    @unittest.skip('quebrado')\n"
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_cabecalho_mais_mais_mais_nao_e_linha_adicionada(self):
        diff = "+++ b/it.skip(coisa).py\n"
        self.assertEqual(fila.diff_mexeu_em_teste(diff), "")

    def test_diff_vazio_passa(self):
        self.assertEqual(fila.diff_mexeu_em_teste(""), "")
        self.assertEqual(fila.diff_mexeu_em_teste(None), "")
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `AttributeError: module 'fila' has no attribute 'diff_mexeu_em_teste'`.

- [ ] **Step 3: Implementar**

Acrescentar `import re` ao topo de `fila.py`.

```python
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
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `OK`, 55 testes.

- [ ] **Step 5: Commit**

```bash
git add fila.py test_fila.py
git commit -m "feat(fila): trava do teste apagado, verificada no diff

E a unica coisa entre 'consertar o teste' e 'apagar o teste'. Por isso vive em
codigo e nao no texto do pedido: instrucao em texto e sugestao, nao trava.

Tirar um skip PASSA de proposito — religar um teste e o oposto de burlar.

Enquanto esta trava nao tiver historico, ci_vermelha fica fora da lista branca.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: A trava do segredo, e ligar as duas no `execucao.py`

**Files:**
- Modify: `fila.py`, `execucao.py:791` (`_fechar_com_pedido_de_alteracao`)
- Test: `test_fila.py`

**Interfaces:**
- Produces:
  - `fila.env_example_tem_valor(diff: str) -> str`
  - `fila.reprovar(diff: str, regra: str) -> str` — aplica as travas que valem para aquela regra; `""` se aprovado.

**A regra dura:** linha nova no `.env.example` só pode ser `CHAVE=`. Com qualquer coisa depois do `=`, o item é reprovado — inclusive um espaço reservado que pareça inofensivo. É estrito de propósito: o custo de errar para o lado frouxo é um segredo no histórico do git, e rotacionar segredo é varredura no repositório inteiro, não a edição de uma linha.

- [ ] **Step 1: Escrever o teste que falha**

```python
class SegredoNoEnvExample(unittest.TestCase):

    def test_chave_vazia_passa(self):
        self.assertEqual(fila.env_example_tem_valor("+DATABASE_URL=\n"), "")

    def test_chave_com_valor_reprova(self):
        motivo = fila.env_example_tem_valor("+DATABASE_URL=postgres://a:b@c/d\n")
        self.assertIn("DATABASE_URL", motivo)

    def test_espaco_reservado_tambem_reprova(self):
        self.assertIn("API_KEY", fila.env_example_tem_valor("+API_KEY=troque-aqui\n"))

    def test_comentario_passa(self):
        self.assertEqual(fila.env_example_tem_valor("+# banco de dados\n"), "")

    def test_linha_em_branco_passa(self):
        self.assertEqual(fila.env_example_tem_valor("+\n"), "")

    def test_linha_removida_nao_e_avaliada(self):
        self.assertEqual(fila.env_example_tem_valor("-SENHA=abc123\n"), "")

    def test_cabecalho_do_diff_nao_e_avaliado(self):
        self.assertEqual(fila.env_example_tem_valor("+++ b/.env.example\n"), "")

    def test_linha_sem_igual_passa(self):
        self.assertEqual(fila.env_example_tem_valor("+apenas texto\n"), "")


class Reprovar(unittest.TestCase):

    def test_env_drift_checa_as_duas_travas(self):
        self.assertIn("DATABASE_URL",
                      fila.reprovar("+DATABASE_URL=segredo\n", "env_drift"))

    def test_dependencia_nao_checa_a_trava_do_env(self):
        """So o env_drift toca .env.example. Cobrar dos outros seria ruido."""
        self.assertEqual(fila.reprovar("+DATABASE_URL=segredo\n",
                                       "dependencia_insegura"), "")

    def test_trava_do_teste_vale_para_toda_regra(self):
        diff = "--- a/test_x.py\n+++ /dev/null\n"
        self.assertIn("test_x.py", fila.reprovar(diff, "dependencia_insegura"))
        self.assertIn("test_x.py", fila.reprovar(diff, "env_drift"))

    def test_diff_limpo_aprova(self):
        self.assertEqual(fila.reprovar("+print('oi')\n", "env_drift"), "")
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `AttributeError: module 'fila' has no attribute 'env_example_tem_valor'`.

- [ ] **Step 3: Implementar em `fila.py`**

```python
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
```

- [ ] **Step 4: Ligar no `execucao.py`**

Em `execucao.py`, dentro de `_fechar_com_pedido_de_alteracao` (linha 791), **antes** da chamada a `publicar(...)`. **Preserve o CRLF do arquivo.** Acrescente `import fila` ao topo — `fila` importa `execucao`, então a importação aqui tem de ser **dentro da função**, não no topo, senão os dois módulos se importam em círculo:

```python
    # As travas de diff. Ficam AQUI, no ultimo instante antes de publicar,
    # porque e o unico ponto por onde todo caminho passa — botao, paleta e fila.
    #
    # `import` dentro da funcao de proposito: fila.py importa execucao.py, e no
    # topo isto seria importacao circular.
    import fila
    motivo = fila.reprovar(_execucao.get("diff") or "", _execucao.get("regra") or "")
    if motivo:
        _anotar("Reprovado antes de publicar: " + motivo)
        _execucao["estado"] = "falha"
        _execucao["frase"] = "Reprovado: " + motivo
        remover_copia(_execucao.get("projeto_caminho"), _execucao.get("copia"))
        return
```

**Atenção:** confira que `_execucao` guarda a chave `regra`. O `_zerado()` de hoje (linha 566) **não tem** essa chave — acrescente `"regra": "",` a ele e preencha em `iniciar()` a partir de `pendencia.get("regra")`. Sem isso a trava do `.env.example` nunca dispara e o teste da Task 6 passa mentindo.

- [ ] **Step 5: Rodar tudo**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3 && python test_execucao.py 2>&1 | tail -3
```

Esperado: `OK` nas duas. `test_fila.py` com 67 testes.

- [ ] **Step 6: Commit**

```bash
git add fila.py execucao.py test_fila.py
git commit -m "feat(fila): trava do segredo no .env.example, e as duas ligadas antes de publicar

Linha nova so pode ser CHAVE=. Espaco reservado que parece inofensivo tambem
reprova: o custo de errar para o lado frouxo e um segredo no historico do git,
e rotacionar e varredura no repositorio inteiro.

As travas ficam no ultimo instante antes de publicar, porque e o unico ponto
por onde TODO caminho passa — botao, paleta e fila.

_zerado() ganhou a chave `regra`. Sem ela a trava do env nunca dispararia.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: O laço

**Files:**
- Modify: `fila.py`
- Test: `test_fila.py`

**Interfaces:**
- Consumes: `banco.enfileirar`, `banco.fila_aberta`, `banco.marcar_fila`, `banco.gasto_do_dia`, `banco.agora`.
- Produces:
  - `fila.trabalhar(pendencias: list, executores: dict, parar_agora=None) -> dict` — devolve o relatório: `{"feitos": int, "falhas": int, "gasto_usd": float, "motivo_da_parada": str}`.
  - `fila.ESTADO: dict` — o retrato para a tela.

**Injeção de dependência, e por quê:** `trabalhar` recebe `executores` — `{"mecanico": fn, "claude": fn}`. Cada função recebe o item e devolve `(deu_certo: bool, custo_usd: float, pr_url: str, erro: str)`. Assim `fila.py` **não importa `servir.py`** (evita o círculo) e o teste roda sem servidor, sem rede e sem gastar um centavo.

- [ ] **Step 1: Escrever o teste que falha**

```python
class Lacar(BancoTemporario):

    def _pendencia(self, regra="memoria_crlf", projeto="dents", gravidade="alta"):
        return {"id": "%s:%s" % (regra, projeto), "regra": regra,
                "projeto": projeto, "gravidade": gravidade, "risco": 0}

    def _executores(self, resultado=(True, 0.0, "", "")):
        self.chamadas = []

        def fingir(item):
            self.chamadas.append(item["id"])
            return resultado

        return {"mecanico": fingir, "claude": fingir}

    def test_fila_vazia_relata_zero(self):
        rel = fila.trabalhar([], self._executores())
        self.assertEqual(rel["feitos"], 0)
        self.assertEqual(rel["motivo_da_parada"], "nada na fila")

    def test_um_item_mecanico_e_feito(self):
        rel = fila.trabalhar([self._pendencia()], self._executores())
        self.assertEqual(rel["feitos"], 1)
        self.assertEqual(self.chamadas, ["memoria_crlf:dents"])

    def test_pendencia_nao_elegivel_nao_entra(self):
        rel = fila.trabalhar([self._pendencia("ci_vermelha")], self._executores())
        self.assertEqual(rel["feitos"], 0)
        self.assertEqual(self.chamadas, [])

    def test_item_feito_fica_ok_e_sai_da_fila_aberta(self):
        fila.trabalhar([self._pendencia()], self._executores())
        self.assertEqual(banco.fila_aberta(), [])

    def test_falha_conta_tentativa_e_guarda_o_erro(self):
        exec_ = self._executores((False, 0.10, "", "o teste continuou vermelho"))
        rel = fila.trabalhar([self._pendencia()], exec_)
        self.assertEqual(rel["falhas"], 1)
        item = banco.fila_aberta()[0]
        self.assertEqual(item["estado"], "falha")
        self.assertEqual(item["tentativas"], 1)
        self.assertIn("vermelho", item["erro"])

    def test_falha_nao_e_retentada_no_mesmo_laco(self):
        exec_ = self._executores((False, 0.0, "", "quebrou"))
        fila.trabalhar([self._pendencia()], exec_)
        self.assertEqual(len(self.chamadas), 1)

    def test_teto_estourado_para_o_laco_com_motivo(self):
        exec_ = self._executores((True, 999.0, "", ""))
        rel = fila.trabalhar(
            [self._pendencia(projeto="a"), self._pendencia(projeto="b")], exec_)
        self.assertEqual(rel["feitos"], 1)
        self.assertIn("teto", rel["motivo_da_parada"])

    def test_o_dono_mandando_parar_interrompe(self):
        exec_ = self._executores()
        rel = fila.trabalhar(
            [self._pendencia(projeto="a"), self._pendencia(projeto="b")],
            exec_, parar_agora=lambda: True)
        self.assertEqual(rel["feitos"], 0)
        self.assertIn("parou", rel["motivo_da_parada"])

    def test_o_grave_e_atendido_primeiro(self):
        exec_ = self._executores()
        fila.trabalhar([self._pendencia("env_drift", "zz", "media"),
                        self._pendencia("memoria_crlf", "aa", "alta")], exec_)
        self.assertEqual(self.chamadas[0], "memoria_crlf:aa")

    def test_pr_url_e_guardado(self):
        exec_ = self._executores((True, 1.0, "https://github.com/x/y/pull/9", ""))
        fila.trabalhar([self._pendencia("env_drift")], exec_)
        con = banco.conectar()
        linha = con.execute("SELECT pr_url FROM fila WHERE id = 'env_drift:dents'").fetchone()
        con.close()
        self.assertEqual(linha["pr_url"], "https://github.com/x/y/pull/9")

    def test_trilho_errado_no_executor_e_erro_visivel(self):
        rel = fila.trabalhar([self._pendencia()], {"claude": lambda i: (True, 0, "", "")})
        self.assertEqual(rel["falhas"], 1)
        self.assertIn("sem executor", banco.fila_aberta()[0]["erro"])
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `AttributeError: module 'fila' has no attribute 'trabalhar'`.

- [ ] **Step 3: Implementar**

Acrescentar `import banco` ao topo de `fila.py`.

```python
def trabalhar(pendencias: list, executores: dict, parar_agora=None) -> dict:
    """Enfileira o que e elegivel e trabalha ate acabar servico, dinheiro ou paciencia.

    `executores` chega por parametro, nao por import: assim fila.py nao importa
    servir.py (que importaria fila.py de volta) e o teste roda sem servidor,
    sem rede e sem gastar um centavo.

    Cada executor recebe o item e devolve (deu_certo, custo_usd, pr_url, erro).
    """
    hoje = hoje_local()
    banco.enfileirar(elegiveis(pendencias))
    relatorio = {"feitos": 0, "falhas": 0, "gasto_usd": 0.0, "motivo_da_parada": ""}

    while True:
        if parar_agora and parar_agora():
            relatorio["motivo_da_parada"] = "voce parou a fila"
            break

        gasto = banco.gasto_do_dia(hoje)
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

    relatorio["gasto_usd"] = banco.gasto_do_dia(hoje)
    return relatorio
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_fila.py 2>&1 | tail -3
```

Esperado: `OK`, 79 testes.

- [ ] **Step 5: Commit**

```bash
git add fila.py test_fila.py
git commit -m "feat(fila): o laco que trabalha desacompanhado

Os executores chegam por parametro, nao por import: fila.py nao importa
servir.py (que importaria fila.py de volta), e o teste roda sem servidor, sem
rede e sem gastar um centavo.

Um item que explode nao mata o laco — vira falha com o motivo, e o proximo
segue. Toda parada tem motivo em portugues, porque a tela precisa dizer por que
parou, nao so que parou.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Os executores de verdade, o servidor e a tela

**Files:**
- Modify: `servir.py`, `index.html`
- Test: `test_servir.py` (acrescentar)

**Interfaces:**
- Consumes: `fila.trabalhar`, `servir.acao_crlf_para_lf` (linha 235), `execucao.iniciar`, `execucao.parar`.
- Produces:
  - `servir.executor_mecanico(item) -> tuple`
  - `servir.executor_claude(item) -> tuple`
  - Comandos novos: `fila_comecar`, `fila_parar`.
  - `/api/dados` ganha a chave `fila`.

**Atenção à lista branca da paleta:** o `test_servir.py` tem o teste `PaletaNaoInventaComando`, que exige que todo comando disparado pelo `index.html` exista no servidor. Os dois comandos novos precisam entrar em `ACOES` (ou na tabela equivalente) ou esse teste quebra — e ele quebrando é o teste fazendo o trabalho dele.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `test_servir.py` (**preserve o CRLF do arquivo**):

```python
class ExecutoresDaFila(unittest.TestCase):

    def test_mecanico_devolve_a_tupla_de_quatro(self):
        saida = servir.executor_mecanico(
            {"id": "memoria_crlf:inexistente", "projeto": "inexistente",
             "regra": "memoria_crlf"})
        self.assertEqual(len(saida), 4)
        deu_certo, custo, pr_url, erro = saida
        self.assertIsInstance(deu_certo, bool)
        self.assertEqual(custo, 0.0)

    def test_mecanico_nunca_cobra(self):
        _, custo, _, _ = servir.executor_mecanico(
            {"id": "memoria_crlf:x", "projeto": "x", "regra": "memoria_crlf"})
        self.assertEqual(custo, 0.0)

    def test_os_dois_comandos_da_fila_existem(self):
        self.assertIn("fila_comecar", servir.ACOES)
        self.assertIn("fila_parar", servir.ACOES)
```

- [ ] **Step 2: Rodar para confirmar que falha**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python test_servir.py 2>&1 | tail -3
```

Esperado: `AttributeError: module 'servir' has no attribute 'executor_mecanico'`.

- [ ] **Step 3: Os dois executores em `servir.py`**

```python
def executor_mecanico(item):
    """O trilho sem IA: custo zero, sem pedido de alteracao.

    Hoje so `memoria_crlf`, e a correcao ja existia — `acao_crlf_para_lf`, que
    toca SO os .md listados na medida e nao varre pasta.
    """
    if item.get("regra") != "memoria_crlf":
        return False, 0.0, "", "trilho mecanico nao sabe fazer %r" % item.get("regra")
    # `_projetos_por_nome` (servir.py:180) e a funcao de MODULO. O `_estado` que
    # monta /api/dados e metodo do manipulador de requisicao — de dentro de um
    # executor ele nao existe.
    medida = _projetos_por_nome().get(item.get("projeto")) or {}
    if not medida.get("caminho"):
        return False, 0.0, "", "nao sei onde fica o projeto %s" % item.get("projeto")
    try:
        deu_certo, mensagem = acao_crlf_para_lf(medida)
    except Exception as e:                          # noqa: BLE001
        return False, 0.0, "", "%s: %s" % (type(e).__name__, e)
    return bool(deu_certo), 0.0, "", "" if deu_certo else mensagem


def executor_claude(item):
    """O trilho com IA: copia isolada, teto de US$ 3, pedido de alteracao no fim.

    Reaproveita `execucao.iniciar` inteiro. A fila nao ganha um segundo caminho
    para disparar o Claude — um caminho so e uma superficie de risco so.
    """
    caminho = (_projetos_por_nome().get(item.get("projeto")) or {}).get("caminho")
    if not caminho:
        return False, 0.0, "", "nao sei onde fica o projeto %s" % item.get("projeto")
    execucao.iniciar(item, caminho)
    final = execucao.esperar_terminar()
    custo = float(final.get("custo_usd") or 0.0)
    if final.get("estado") == "ok":
        return True, custo, final.get("pr_url") or "", ""
    return False, custo, "", final.get("frase") or "falhou sem dizer por que"
```

**`execucao.esperar_terminar()` não existe ainda.** Acrescente-a a `execucao.py`, junto de `parar()`:

```python
def esperar_terminar(limite_s=1800):
    """Bloqueia ate a execucao atual chegar a um estado terminal. Devolve o retrato.

    O laco da fila e sincrono de proposito: um item por vez, e dois worktrees do
    mesmo repositorio e como quebra.
    """
    import time
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        if _execucao.get("estado") in ESTADOS_TERMINAIS:
            return dict(_execucao)
        time.sleep(0.5)
    parar()
    return dict(_execucao)
```

- [ ] **Step 4: Os dois comandos e os dados da tela**

Em `servir.py`, junto das outras ações. `fila_comecar` roda em thread para não travar a resposta HTTP:

```python
_fila_parar = threading.Event()
_fila_relatorio = {}
_fila_thread = None


def _fila_thread_viva() -> bool:
    """A fila esta trabalhando neste instante?"""
    return bool(_fila_thread and _fila_thread.is_alive())


def acao_fila_comecar(p):
    """Comeca a fila. Volta na hora; o trabalho segue em thread."""
    if _fila_thread_viva():
        return False, "a fila já está trabalhando."
    _fila_parar.clear()
    # Mesmo caminho que /api/dados usa (servir.py:672) — nao ha uma segunda
    # forma de calcular pendencia, e nao pode haver.
    con = banco.conectar()
    try:
        e = banco.montar_estado(con)
        pendencias = regras.avaliar(e["projetos"], quota=e["quota"],
                                    silenciadas=banco.silenciadas(con))
    finally:
        con.close()
    global _fila_thread
    _fila_thread = threading.Thread(target=_rodar_fila, args=(pendencias,), daemon=True)
    _fila_thread.start()
    return True, "fila iniciada."


def acao_fila_parar(p):
    _fila_parar.set()
    execucao.parar()
    return True, "pedido de parada enviado."


def _rodar_fila(pendencias):
    global _fila_relatorio
    _fila_relatorio = fila.trabalhar(
        pendencias,
        {"mecanico": executor_mecanico, "claude": executor_claude},
        parar_agora=_fila_parar.is_set)
```

Registre em `ACOES`:

```python
    "fila_comecar": acao_fila_comecar,
    "fila_parar": acao_fila_parar,
```

E acrescente ao dicionário devolvido por `/api/dados`:

```python
    "fila": {
        "itens": banco.fila_aberta(),
        "gasto_hoje_brl": execucao.em_reais(banco.gasto_do_dia(fila.hoje_local())),
        "falta_brl": "R$ " + ("%.2f" % fila.quanto_falta(
            banco.gasto_do_dia(fila.hoje_local()))).replace(".", ","),
        "teto_brl": "R$ " + ("%.2f" % fila.TETO_DIARIO_BRL).replace(".", ","),
        "trabalhando": _fila_thread_viva(),
        "relatorio": _fila_relatorio,
    },
```

- [ ] **Step 5: A faixa no `index.html`**

Acima da caixa de pendências. **Preserve o LF do arquivo.** Sem `innerHTML` com dado vindo do servidor — o projeto já mantém essa disciplina e os dois `innerHTML` existentes são literais fixos.

```html
<section id="faixa-fila" class="faixa-fila" hidden>
  <button id="fila-comecar" type="button">Trabalhar na fila</button>
  <span id="fila-resumo"></span>
  <button id="fila-parar" type="button" hidden>Parar</button>
  <ul id="fila-itens"></ul>
</section>
```

```js
function desenharFila(f) {
  const faixa = document.getElementById('faixa-fila');
  if (!f) { faixa.hidden = true; return; }
  faixa.hidden = false;
  const espera = f.itens.filter(i => i.estado === 'esperando').length;
  document.getElementById('fila-resumo').textContent =
    `${espera} ${espera === 1 ? 'item' : 'itens'} · ${f.gasto_hoje_brl} de ${f.teto_brl} hoje`;
  document.getElementById('fila-comecar').hidden = f.trabalhando;
  document.getElementById('fila-parar').hidden = !f.trabalhando;

  const lista = document.getElementById('fila-itens');
  lista.textContent = '';
  for (const i of f.itens) {
    const li = document.createElement('li');
    li.dataset.estado = i.estado;
    li.textContent = `${i.projeto} — ${i.regra} — ${i.estado}` +
      (i.trilho === 'mecanico' ? ' — R$ 0,00' : '') +
      (i.erro ? ` — ${i.erro}` : '');
    if (i.pr_url) {
      const a = document.createElement('a');
      a.href = i.pr_url; a.rel = 'noopener'; a.target = '_blank';
      a.textContent = ' ver o pedido';
      li.appendChild(a);
    }
    lista.appendChild(li);
  }
}

document.getElementById('fila-comecar')
  .addEventListener('click', () => agir({ comando: 'fila_comecar' }));
document.getElementById('fila-parar')
  .addEventListener('click', () => agir({ comando: 'fila_parar' }));
```

Chame `desenharFila(dados.fila)` de dentro da função que já redesenha a tela a cada 15 s.

- [ ] **Step 6: Rodar tudo**

```bash
cd "C:/Users/Desktop/source/painel-projetos" && for s in fila regras coletar execucao servir memoria; do echo "--- $s"; python test_$s.py 2>&1 | tail -2; done
```

Esperado: `OK` nas seis.

- [ ] **Step 7: Ver no navegador**

Suba o painel e confira a faixa com os próprios olhos — não há executor de teste de JavaScript neste projeto, e o README já registra isso.

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python servir.py
```

Abra http://localhost:4777. Esperado: a faixa aparece dizendo `N itens · R$ 0,00 de R$ 50,00 hoje`, com o botão **Trabalhar na fila**. `Ctrl+C` encerra.

- [ ] **Step 8: Commit**

```bash
git add servir.py execucao.py index.html test_servir.py
git commit -m "feat(fila): os executores de verdade, os dois comandos e a faixa

O executor mecanico reaproveita acao_crlf_para_lf, que ja existia e ja e
cuidadosa: toca SO os .md listados na medida, nao varre pasta.

O executor do Claude reaproveita execucao.iniciar inteiro. A fila NAO ganha um
segundo caminho para disparar o Claude — um caminho so e uma superficie de
risco so, e e o que o PaletaNaoInventaComando ja cobra da paleta.

Item mecanico mostra R\$ 0,00 explicito: metade do trabalho nao custa nada e a
tela tem de dizer isso.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: O Renovate nos repositórios, o Dependabot, e o fecho

**Files:**
- Create: `renovate.json` em `workspace-medconsultoria`, `medconsultoria`, `odontologia-pericia`, `investrix`
- Modify: `README.md` (neste repositório)

**Esta tarefa sai deste repositório.** Cada `renovate.json` é um commit no repositório dele, em branch própria e com pedido de alteração — a regra da casa vale igual.

- [ ] **Step 1: Resolver a dúvida em aberto do CRLF, antes de automatizar**

A memória `regra-crlf-acusa-o-indice` diz que o `MEMORY.md`, por especificação, não tem cabeçalho — então o motivo alegado pela regra 6 ("o harness ignora o frontmatter") não se aplica a ele. O coletor varre `*.md` (`coletar.py:236`) e inclui esse arquivo. Antes de a fila converter arquivos sozinha, **prove**:

```bash
cd "C:/Users/Desktop/source/painel-projetos" && python - <<'FIM'
from pathlib import Path
alvo = Path.home() / ".claude" / "projects" / "_teste-crlf"
alvo.mkdir(parents=True, exist_ok=True)
(alvo / "memory").mkdir(exist_ok=True)
p = alvo / "memory" / "prova.md"
p.write_bytes(b"---\r\nname: prova\r\ndescription: teste de CRLF\r\n---\r\n\r\ncorpo\r\n")
print("gravado em CRLF:", p)
print("tem CRLF?", b"\r\n" in p.read_bytes())
FIM
```

Registre no `README.md` o que a experiência mostrou. Se o `MEMORY.md` de fato não sofre com CRLF, **exclua-o do varredor** em `coletar.py:236` (`if md.name == "MEMORY.md": continue`) com o motivo em comentário, e acrescente o caso a `test_coletar.py`. Se sofre, registre isso e siga.

Apague a pasta de teste ao fim:

```bash
python -c "import shutil,pathlib;shutil.rmtree(pathlib.Path.home()/'.claude'/'projects'/'_teste-crlf')"
```

- [ ] **Step 2: O `renovate.json`**

Mesmo conteúdo nos quatro repositórios:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended"],
  "timezone": "America/Sao_Paulo",
  "schedule": ["after 9pm every weekday", "every weekend"],
  "prConcurrentLimit": 3,
  "prHourlyLimit": 2,
  "minimumReleaseAge": "24 hours",
  "vulnerabilityAlerts": {
    "enabled": true,
    "minimumReleaseAge": "24 hours"
  },
  "packageRules": [
    {
      "description": "Correcao de seguranca sem troca de versao maior, com CI verde: entra sozinha.",
      "matchUpdateTypes": ["patch", "minor"],
      "isVulnerabilityAlert": true,
      "automerge": true,
      "automergeType": "pr",
      "platformAutomerge": true
    },
    {
      "description": "Versao maior SEMPRE espera gente. Muda comportamento, nao so numero.",
      "matchUpdateTypes": ["major"],
      "automerge": false,
      "addLabels": ["versao-maior"]
    },
    {
      "description": "Agrupa o resto por gerenciador: um pedido, nao dezoito.",
      "groupName": "dependencias de {{manager}}",
      "matchUpdateTypes": ["patch", "minor"],
      "automerge": false
    }
  ]
}
```

**`platformAutomerge` só funciona com a mesclagem automática ligada no repositório.** Ligue em *Settings → General → Pull Requests → Allow auto-merge* em cada um dos quatro, senão o Renovate abre o pedido e ele fica parado sem ninguém entender por quê.

- [ ] **Step 3: Instalar o Renovate e desligar o Dependabot que abre PR**

```bash
gh api /repos/garcia-goncalves/workspace-medconsultoria/vulnerability-alerts
```

Esperado: `204` (alertas ligados — **mantenha assim**, é o que alimenta a regra `vulnerabilidade` do painel).

Desligar apenas os *security updates* automáticos, em cada um dos quatro:

```bash
gh api -X DELETE /repos/garcia-goncalves/workspace-medconsultoria/automated-security-fixes
```

Esperado: `204`. Dependabot e Renovate abrindo pedido no mesmo repositório produzem pedidos concorrentes — a literatura é unânime.

O aplicativo Renovate se instala pelo site (https://github.com/apps/renovate), marcando os quatro repositórios. **Isso exige a mão do dono** — é aprovação no navegador.

- [ ] **Step 4: Provar que funcionou**

```bash
gh pr list --repo garcia-goncalves/workspace-medconsultoria --author app/renovate
```

Esperado: ao menos um pedido agrupado. Guarde a URL — é o critério 3 da verificação.

- [ ] **Step 5: O README**

Seção nova, entre "As 16 pendências" e "A paleta de comandos". **Preserve o CRLF do `README.md`.** Cubra: os três trilhos; as quatro travas com o número de cada uma; por que `ci_vermelha` e `grafo_velho` ficam de fora; o teto de R$ 50 na data local e por que não em UTC; e o risco aceito de apagar o `hub.db` no meio do dia zerar o teto.

- [ ] **Step 6: A verificação, com a prova de cada critério**

Crie `docs/esteira/fila-que-conserta/verificacao.md` respondendo aos 8 critérios da especificação, **cada um com a saída real do comando** — é o padrão que `docs/esteira/alertas-por-risco/verificacao.md` já estabeleceu neste projeto.

Os critérios 6 e 7 pedem demonstração deliberada:

- **6 — trava do teste apagado:** enfileire um item, deixe o Claude apagar um teste de propósito num repositório de rascunho, e registre a mensagem que a tela mostrou.
- **7 — teto diário:** baixe `fila.TETO_DIARIO_BRL` para `0.01` numa execução, rode a fila e registre o motivo da parada. **Devolva para `50.00` depois** e confirme no `git diff` antes do commit.

- [ ] **Step 7: Commit e pedido de alteração**

```bash
git add README.md docs/esteira/fila-que-conserta/verificacao.md coletar.py test_coletar.py
git commit -m "docs(fila): o README e a verificacao com a prova de cada criterio

Inclui o que a experiencia do CRLF mostrou sobre o MEMORY.md — a duvida estava
aberta desde 24/08 com a instrucao 'provar antes de mexer', e automatizar a
conversao sem responder seria automatizar em cima de duvida.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
git push -u origin hub/fila-que-conserta
gh pr create --fill
```

- [ ] **Step 8: Revisores especialistas antes de mesclar**

A regra da casa: `.py` → `python-reviewer`; e esta mudança toca segredo, execução autônoma e superfície de ação → `security-reviewer`. O pedido de alteração anterior (PR #5) foi mesclado sem revisor porque a sessão proibia despachar subagente — **esta não pode repetir isso**. Commite antes de despachar: o revisor troca a branch.

---

## Verificação final

```bash
cd "C:/Users/Desktop/source/painel-projetos" && for s in fila regras coletar execucao servir memoria; do printf "%-10s " $s; python test_$s.py 2>&1 | tail -1; done
```

Esperado: `OK` nas seis, com o total do projeto acima de 370 testes (305 de hoje + ~79 da fila).
