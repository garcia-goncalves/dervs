# Etapa 9 — Cortina, entrar com GitHub e a tabela `credencial`

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nenhuma rota de dado do DERVS responde sem sessão autenticada; a identidade vem do GitHub; e `GET /` não parece um sistema.

**Architecture:** Três camadas independentes e testáveis em separado. `cortina.py` guarda a combinação de seis dígitos e o teto de tentativas por origem. `autenticacao.py` fala com o GitHub por OAuth e abre a sessão. `banco.py` ganha `credencial` e `instalacao`, e perde as colunas de segredo da `usuario`. `servir.py` deixa de ter um token global e passa a classificar cada rota da tabela `ROTAS`.

**Tech Stack:** Python 3, **só biblioteca padrão** (`hmac`, `hashlib`, `secrets`, `sqlite3`, `urllib.request`, `unittest`). SQLite. HTML/CSS/JS sem framework.

**Spec:** `docs/superpowers/specs/2026-08-26-login-cortina-github-design.md` — leia antes da Tarefa 1. O plano argumenta a partir dela.

## Global Constraints

- **Zero dependências de fora.** A CI reprova a existência de qualquer `requirements.txt`, `pyproject.toml` ou `setup.py`. Se uma tarefa parecer exigir biblioteca externa, **pare e devolva** — não instale.
- **Testes com `unittest`, não `pytest`.** Rodam por `python test_arquivo.py`, terminam com `unittest.main(verbosity=2)` e imprimem `OK`.
- **Todo `test_*.py` novo entra na lista da CI** em `.github/workflows/ci.yml`. Existe um vigia lá que reprova se ficar de fora.
- **Nenhum teste toca a rede.** Chamadas ao GitHub recebem a função de abrir URL por parâmetro (`abrir=urllib.request.urlopen`), e o teste passa um dublê.
- **`DERVS_COFRE` tem de valer 32+ caracteres** e ser definida **antes** de `import banco`. Copie o cabeçalho de `test_banco.py:31-36`.
- **`DERVS_AMBIENTE=local`** é obrigatório nesta máquina: o cofre se recusa a criar `cofre.chave` fora do ambiente local, e falha fechada de propósito.
- **Comentário e nome de função em português.** Mensagem de commit `tipo(escopo):` em português, corpo com o **porquê**. Acento em mensagem de commit: `Write` num arquivo + `git commit -F`, nunca heredoc.
- **`executescript` não abre transação** e dá `COMMIT` implícito. Migração é `BEGIN IMMEDIATE` + `execute` um a um + `commit`, com `rollback` no `except`.
- **A migração roda antes de `executescript(ESQUEMA)`** — a ordem já está certa em `banco.conectar()` (`banco.py:246-262`). Não inverta.
- **`ThreadingHTTPServer`:** todo estado em memória compartilhado entre requisições precisa de `threading.Lock`.
- **Segredo nunca em log, commit, memória ou resposta HTTP.**

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `banco.py` *(modificar)* | Esquema, migração e acesso. Ganha `credencial` e `instalacao`; `usuario` perde `senha_hash`, `totp_segredo`, `totp_confirmado_em`. |
| `cortina.py` *(criar)* | A combinação de seis dígitos, o selo do cookie e o teto por origem. Não sabe o que é GitHub nem o que é sessão. |
| `autenticacao.py` *(criar)* | OAuth do GitHub, abertura de sessão e o comando `convidar`. Não sabe desenhar HTML. |
| `servir.py` *(modificar)* | Classificação das rotas, leitura de cookie, anti-CSRF por sessão. Não conhece `scrypt` nem OAuth. |
| `index-cortina.html` *(criar)* | A tela do museu. Sem nenhum segredo dentro. |
| `test_cortina.py`, `test_autenticacao.py` *(criar)* | Um por módulo. |
| `test_banco.py`, `test_rotas.py`, `test_servir.py` *(modificar)* | Acréscimos. |

Se `autenticacao.py` passar de mil linhas, quebre em `autenticacao.py` + `oauth_github.py` **durante** a implementação, não depois.

---

### Tarefa 1: Esquema `credencial` e `instalacao`, e a migração tudo-ou-nada

**Files:**
- Modify: `banco.py` (bloco `ESQUEMA`, `banco.py:44-240`; função `migrar`, `banco.py:269-330`)
- Test: `test_banco.py` (classe nova no fim, antes do `if __name__`)

**Interfaces:**
- Consumes: `banco.conectar()`, `banco.agora()`, `banco.migrar(con)`, `banco.DONO_LOCAL`
- Produces: tabelas `credencial` e `instalacao`; `usuario` sem `senha_hash`, `totp_segredo`, `totp_confirmado_em`

- [ ] **Step 1: Escrever o teste que falha — o banco velho sobe sem perder linha**

Acrescente em `test_banco.py`:

```python
class MigracaoParaCredencial(unittest.TestCase):
    """Um hub.db da etapa 8 abre no esquema da 9 sem perder usuario nem segredo."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.caminho = str(Path(self.dir.name) / "hub.db")
        self.addCleanup(self.dir.cleanup)

    def _banco_da_etapa_8(self):
        """Recria a forma ANTIGA na mao. Nao importe o esquema de hoje aqui:
        o teste tem de descrever o passado, senao ele para de testar migracao
        no dia em que o esquema mudar de novo."""
        c = sqlite3.connect(self.caminho)
        c.executescript("""
            CREATE TABLE usuario (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT CHECK (id <> 0),
                email              TEXT NOT NULL UNIQUE,
                nome               TEXT NOT NULL DEFAULT '',
                senha_hash         TEXT NOT NULL,
                totp_segredo       TEXT,
                totp_confirmado_em TEXT,
                criado_em          TEXT NOT NULL,
                desativado_em      TEXT);
        """)
        c.execute("INSERT INTO usuario (email, nome, senha_hash, totp_segredo,"
                  " totp_confirmado_em, criado_em) VALUES (?,?,?,?,?,?)",
                  ("thiago@teste.local", "Thiago", "scrypt$aaa", "cifrado$bbb",
                   iso(AGORA), iso(AGORA)))
        c.commit()
        c.close()

    def test_usuario_sobrevive_e_segredos_viram_credencial(self):
        self._banco_da_etapa_8()
        con = banco.conectar(self.caminho)
        try:
            u = con.execute("SELECT id, email FROM usuario").fetchall()
            self.assertEqual(len(u), 1)
            self.assertEqual(u[0]["email"], "thiago@teste.local")
            # As colunas de segredo SAIRAM da usuario.
            colunas = {l[1] for l in con.execute("PRAGMA table_info(usuario)")}
            self.assertNotIn("senha_hash", colunas)
            self.assertNotIn("totp_segredo", colunas)
            self.assertNotIn("totp_confirmado_em", colunas)
            # E viraram linhas na credencial, com o valor intacto.
            cred = {l["tipo"]: l["segredo_hash"] for l in
                    con.execute("SELECT tipo, segredo_hash FROM credencial"
                                " WHERE usuario_id = ?", (u[0]["id"],))}
            self.assertEqual(cred["senha"], "scrypt$aaa")
            self.assertEqual(cred["totp"], "cifrado$bbb")
        finally:
            con.close()

    def test_migracao_e_idempotente(self):
        self._banco_da_etapa_8()
        banco.conectar(self.caminho).close()
        banco.conectar(self.caminho).close()      # segunda vez nao pode duplicar
        con = banco.conectar(self.caminho)
        try:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM credencial").fetchone()[0], 2)
        finally:
            con.close()

    def test_dois_usuarios_nao_reivindicam_o_mesmo_github(self):
        con = banco.conectar(self.caminho)
        try:
            a = con.execute("INSERT INTO usuario (email, criado_em) VALUES (?,?)",
                            ("a@teste.local", iso(AGORA))).lastrowid
            b = con.execute("INSERT INTO usuario (email, criado_em) VALUES (?,?)",
                            ("b@teste.local", iso(AGORA))).lastrowid
            con.execute("INSERT INTO credencial (usuario_id, tipo, identificador,"
                        " criado_em) VALUES (?,'github','4242',?)", (a, iso(AGORA)))
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO credencial (usuario_id, tipo, identificador,"
                            " criado_em) VALUES (?,'github','4242',?)", (b, iso(AGORA)))
        finally:
            con.close()

    def test_instalacao_admite_uma_linha_so(self):
        con = banco.conectar(self.caminho)
        try:
            con.execute("INSERT OR IGNORE INTO instalacao (id, criada_em)"
                        " VALUES (1, ?)", (iso(AGORA),))
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("INSERT INTO instalacao (id, criada_em) VALUES (2, ?)",
                            (iso(AGORA),))
        finally:
            con.close()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python test_banco.py MigracaoParaCredencial -v`
Expected: FAIL — `no such table: credencial`.

- [ ] **Step 3: Acrescentar as duas tabelas ao `ESQUEMA`**

No fim do bloco `ESQUEMA` de `banco.py`, e **remova `senha_hash`, `totp_segredo` e `totp_confirmado_em` do `CREATE TABLE usuario`** (a `usuario` do esquema passa a nascer sem elas):

```sql
CREATE TABLE IF NOT EXISTS credencial (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    tipo          TEXT NOT NULL CHECK (tipo IN ('github','senha','totp','passkey')),
    -- Chave externa da identidade. github: o id NUMERICO, em texto — nunca o
    -- login, que pode ser trocado e liberado para outra pessoa registrar.
    -- senha/totp: o proprio usuario_id em texto, o que faz o UNIQUE abaixo
    -- garantir "uma senha por pessoa" de graca.
    identificador TEXT NOT NULL,
    -- github: NULL, nao ha segredo a guardar. senha: scrypt. totp: CIFRADO.
    segredo_hash  TEXT,
    criado_em     TEXT NOT NULL,
    -- NULL = nunca usada. Para 'totp' este campo faz o papel do antigo
    -- `totp_confirmado_em`: a negativa continua sendo o padrao.
    usado_em      TEXT,
    revogada_em   TEXT,
    UNIQUE (tipo, identificador)
);
CREATE INDEX IF NOT EXISTS ix_credencial_dono ON credencial (usuario_id, tipo);

CREATE TABLE IF NOT EXISTS instalacao (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    combinacao_hash TEXT,     -- scrypt dos seis digitos. NULL = ainda nao gerada.
    combinacao_em   TEXT,
    criada_em       TEXT NOT NULL
);
```

- [ ] **Step 4: Escrever a migração**

Em `banco.py`, dentro de `migrar(con)`, **depois** da migração de `pendencia_estado` que já existe, acrescente:

```python
    _migrar_credencial(con)


def _migrar_credencial(con: sqlite3.Connection) -> None:
    """Tira senha e TOTP de dentro da `usuario` (etapa 9).

    Roda em toda conexao: a checagem barata e um PRAGMA, que nao toca o disco.
    """
    forma = list(con.execute("PRAGMA table_info(usuario)"))
    if not forma:
        return                                   # banco novo: o ESQUEMA ja faz certo
    colunas = {l[1] for l in forma}
    if "senha_hash" not in colunas:
        return                                   # ja migrado
    tinha_totp = "totp_segredo" in colunas
    con.execute("PRAGMA foreign_keys=OFF")
    try:
        # TUDO OU NADA — `executescript` daria COMMIT implicito entre os passos
        # e uma queda entre o DROP e o RENAME deixaria as cinco tabelas filhas
        # apontando para uma `usuario` que nao existe mais.
        con.execute("BEGIN IMMEDIATE")
        con.execute("DROP TABLE IF EXISTS usuario_nova")
        con.execute("""CREATE TABLE usuario_nova (
                id            INTEGER PRIMARY KEY AUTOINCREMENT CHECK (id <> 0),
                email         TEXT NOT NULL UNIQUE CHECK (length(trim(email)) > 0),
                nome          TEXT NOT NULL DEFAULT '',
                criado_em     TEXT NOT NULL,
                desativado_em TEXT)""")
        con.execute("INSERT INTO usuario_nova (id, email, nome, criado_em,"
                    " desativado_em) SELECT id, email, nome, criado_em,"
                    " desativado_em FROM usuario")
        con.execute("""CREATE TABLE IF NOT EXISTS credencial (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
                tipo          TEXT NOT NULL CHECK (tipo IN ('github','senha','totp','passkey')),
                identificador TEXT NOT NULL,
                segredo_hash  TEXT,
                criado_em     TEXT NOT NULL,
                usado_em      TEXT,
                revogada_em   TEXT,
                UNIQUE (tipo, identificador))""")
        con.execute("INSERT OR IGNORE INTO credencial"
                    " (usuario_id, tipo, identificador, segredo_hash, criado_em)"
                    " SELECT id, 'senha', CAST(id AS TEXT), senha_hash, criado_em"
                    "   FROM usuario WHERE senha_hash IS NOT NULL AND senha_hash <> ''")
        if tinha_totp:
            con.execute("INSERT OR IGNORE INTO credencial"
                        " (usuario_id, tipo, identificador, segredo_hash,"
                        "  criado_em, usado_em)"
                        " SELECT id, 'totp', CAST(id AS TEXT), totp_segredo,"
                        "        criado_em, totp_confirmado_em"
                        "   FROM usuario WHERE totp_segredo IS NOT NULL")
        con.execute("DROP TABLE usuario")
        con.execute("ALTER TABLE usuario_nova RENAME TO usuario")
        # Conferencia ANTES do commit: se uma filha ficou orfa, e agora que se
        # descobre, com rollback ainda possivel.
        sobra = list(con.execute("PRAGMA foreign_key_check"))
        if sobra:
            raise sqlite3.IntegrityError("migracao deixaria orfao: %r" % (sobra[:3],))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.execute("PRAGMA foreign_keys=ON")
```

- [ ] **Step 5: Rodar e ver passar**

Run: `python test_banco.py -v`
Expected: PASS, e os 65 testes anteriores continuam verdes. Se algum dos antigos quebrar por causa de `senha_hash`, **não conserte o teste antigo agora** — anote e conserte na Tarefa 2, que é onde as funções de acesso mudam.

- [ ] **Step 6: Commit**

```bash
git add banco.py test_banco.py
git commit -F <arquivo com a mensagem>
```

Mensagem: `feat(banco): senha e TOTP saem da usuario e viram tabela credencial` — no corpo, o porquê: uma conta que entra só por GitHub não tem senha, e amarrar a pessoa a um jeito de entrar é o que faria chave de acesso virar reescrita na Fatia 2.

---

### Tarefa 2: As funções de acesso à `credencial`

**Files:**
- Modify: `banco.py:764-851` (`criar_usuario`, `credencial_por_email`, `guardar_totp`, `ler_totp`, `confirmar_totp`)
- Test: `test_banco.py`

**Interfaces:**
- Consumes: tabelas da Tarefa 1
- Produces:
  - `criar_usuario(email, senha=None, nome="", con=None) -> int` — `senha=None` cria conta **sem** credencial de senha
  - `ligar_github(usuario_id: int, github_id: str, con=None) -> None`
  - `usuario_por_github(github_id: str, con=None) -> dict | None` — só conta ativa; devolve `COLUNAS_USUARIO`
  - `credencial_por_email(email, con=None) -> tuple[int, str] | None` — assinatura preservada
  - `guardar_totp`, `ler_totp`, `confirmar_totp` — assinaturas preservadas, leem da `credencial`

- [ ] **Step 1: Escrever os testes que falham**

```python
class AcessoPorGithub(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.caminho = str(Path(self.dir.name) / "hub.db")
        self.addCleanup(self.dir.cleanup)
        self.con = banco.conectar(self.caminho)
        self.addCleanup(self.con.close)

    def test_conta_sem_senha_e_valida(self):
        uid = banco.criar_usuario("thiago@teste.local", con=self.con)
        self.assertIsNone(banco.credencial_por_email("thiago@teste.local", con=self.con))
        self.assertIsNotNone(banco.usuario_por_email("thiago@teste.local", con=self.con))
        banco.ligar_github(uid, "4242", con=self.con)
        self.assertEqual(
            banco.usuario_por_github("4242", con=self.con)["id"], uid)

    def test_github_desconhecido_devolve_none(self):
        self.assertIsNone(banco.usuario_por_github("999999", con=self.con))

    def test_conta_desativada_nao_entra_por_github(self):
        uid = banco.criar_usuario("andre@teste.local", con=self.con)
        banco.ligar_github(uid, "777", con=self.con)
        self.con.execute("UPDATE usuario SET desativado_em = ? WHERE id = ?",
                         (iso(AGORA), uid))
        self.con.commit()
        self.assertIsNone(banco.usuario_por_github("777", con=self.con))

    def test_credencial_revogada_nao_entra(self):
        uid = banco.criar_usuario("rafael@teste.local", con=self.con)
        banco.ligar_github(uid, "888", con=self.con)
        self.con.execute("UPDATE credencial SET revogada_em = ?"
                         " WHERE tipo='github' AND identificador='888'", (iso(AGORA),))
        self.con.commit()
        self.assertIsNone(banco.usuario_por_github("888", con=self.con))

    def test_totp_continua_cifrado_na_tabela_nova(self):
        uid = banco.criar_usuario("t@teste.local", "senha-de-teste-1234", con=self.con)
        banco.guardar_totp(uid, "JBSWY3DPEHPK3PXP", con=self.con)
        cru = self.con.execute("SELECT segredo_hash FROM credencial"
                               " WHERE usuario_id=? AND tipo='totp'",
                               (uid,)).fetchone()[0]
        self.assertNotIn("JBSWY3DPEHPK3PXP", cru)
        self.assertEqual(banco.ler_totp(uid, con=self.con), "JBSWY3DPEHPK3PXP")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python test_banco.py AcessoPorGithub -v`
Expected: FAIL — `module 'banco' has no attribute 'ligar_github'`.

- [ ] **Step 3: Implementar**

```python
def criar_usuario(email: str, senha: str = None, nome: str = "", con=None) -> int:
    """Devolve o id. E-mail repetido levanta IntegrityError — nao vira silencio.

    `senha=None` e o caminho normal da etapa 9: quem entra por GitHub nao tem
    senha nenhuma, e obrigar uma seria inventar segredo sem dono.
    """
    fechar = con is None
    con = con or conectar()
    try:
        cur = con.execute(
            "INSERT INTO usuario (email, nome, criado_em) VALUES (?,?,?)",
            (_normalizar_email(email), nome or "", agora()))
        uid = int(cur.lastrowid)
        if senha:
            con.execute("INSERT INTO credencial (usuario_id, tipo, identificador,"
                        " segredo_hash, criado_em) VALUES (?,'senha',?,?,?)",
                        (uid, str(uid), hash_senha(senha), agora()))
        con.commit()
        return uid
    finally:
        if fechar:
            con.close()


COLUNAS_USUARIO = ("id", "email", "nome", "criado_em", "desativado_em")


def ligar_github(usuario_id: int, github_id: str, con=None) -> None:
    """Amarra uma conta a um id NUMERICO do GitHub. Nunca ao login em texto."""
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("INSERT INTO credencial (usuario_id, tipo, identificador,"
                    " criado_em) VALUES (?,'github',?,?)",
                    (int(usuario_id), str(github_id).strip(), agora()))
        con.commit()
    finally:
        if fechar:
            con.close()


def usuario_por_github(github_id: str, con=None):
    """Conta ATIVA com credencial ATIVA, ou None. Nao diz qual das duas faltou."""
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute(
            "SELECT %s FROM usuario u JOIN credencial c ON c.usuario_id = u.id"
            " WHERE c.tipo = 'github' AND c.identificador = ?"
            "   AND c.revogada_em IS NULL AND u.desativado_em IS NULL"
            % ", ".join("u." + c for c in COLUNAS_USUARIO),
            (str(github_id).strip(),)).fetchone()
        return dict(l) if l else None
    finally:
        if fechar:
            con.close()
```

`credencial_por_email`, `guardar_totp`, `ler_totp` e `confirmar_totp` passam a ler e escrever em `credencial` com `tipo` `'senha'` / `'totp'` e `identificador = str(usuario_id)`. `confirmar_totp` grava `usado_em`.

- [ ] **Step 4: Rodar a suíte inteira**

Run: `python test_banco.py -v`
Expected: PASS. Conserte aqui os testes da etapa 8 que dependiam das colunas antigas.

- [ ] **Step 5: Commit**

`feat(banco): ligar_github e usuario_por_github, casando pelo id numerico`

---

### Tarefa 3: `cortina.py` — a combinação, o selo e o teto por origem

**Files:**
- Create: `cortina.py`, `test_cortina.py`
- Modify: `.github/workflows/ci.yml` (acrescentar `python test_cortina.py`)

**Interfaces:**
- Consumes: `banco.conectar`, `banco.agora`, `banco.hash_senha`, `banco.conferir_senha`, `banco.chave_do_cofre`, `banco.novo_codigo`
- Produces:
  - `combinacao_atual(con) -> str | None` (a impressão digital, nunca o número)
  - `garantir_combinacao(con) -> str | None` — gera e **devolve o número em claro uma única vez**; devolve `None` se já existia
  - `conferir(combinacao: str, con) -> bool`
  - `trocar(combinacao: str, con) -> None`
  - `selar(agora_s: float, chave: bytes, minutos: int = 10) -> str`
  - `selo_valido(selo: str, agora_s: float, chave: bytes) -> bool`
  - `pode_tentar(origem: str, agora_s: float) -> bool`
  - `anotar_tentativa(origem: str, agora_s: float) -> None`
  - Constantes `TETO = 5`, `JANELA = 900`

- [ ] **Step 1: Escrever `test_cortina.py`**

```python
# -*- coding: utf-8 -*-
"""Testes da cortina (etapa 9).

A cortina NAO e a fechadura — seis digitos sao um milhao de combinacoes. O que
este arquivo cobra e que ela nao seja PIOR do que isso:

  1. O NUMERO NUNCA FICA GUARDADO. So a impressao digital, por scrypt.
  2. ERRAR E ACERTAR SE PARECEM. A diferenca esta no selo, nao na resposta.
  3. O SELO NAO SE FALSIFICA nem sobrevive ao prazo.
  4. O TETO POR ORIGEM SEGURA, e uma origem nao derruba a outra.

    python test_cortina.py
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import banco    # noqa: E402
import cortina  # noqa: E402


class Combinacao(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.con = banco.conectar(str(Path(self.dir.name) / "hub.db"))
        self.addCleanup(self.con.close)

    def test_gera_seis_digitos_e_so_na_primeira_vez(self):
        numero = cortina.garantir_combinacao(self.con)
        self.assertRegex(numero, r"^\d{6}$")
        self.assertIsNone(cortina.garantir_combinacao(self.con))

    def test_o_numero_nao_fica_no_banco(self):
        numero = cortina.garantir_combinacao(self.con)
        guardado = cortina.combinacao_atual(self.con)
        self.assertNotIn(numero, guardado)
        self.assertTrue(cortina.conferir(numero, self.con))
        self.assertFalse(cortina.conferir("000000", self.con))

    def test_sem_combinacao_gravada_ninguem_entra(self):
        # Falha FECHADA: banco novo, cortina nao gerada, nada passa.
        self.assertFalse(cortina.conferir("000000", self.con))

    def test_trocar_invalida_a_anterior(self):
        antigo = cortina.garantir_combinacao(self.con)
        cortina.trocar("314159", self.con)
        self.assertFalse(cortina.conferir(antigo, self.con))
        self.assertTrue(cortina.conferir("314159", self.con))


class Selo(unittest.TestCase):
    CHAVE = b"x" * 32

    def test_selo_vale_dentro_do_prazo(self):
        s = cortina.selar(1000.0, self.CHAVE, minutos=10)
        self.assertTrue(cortina.selo_valido(s, 1000.0, self.CHAVE))
        self.assertTrue(cortina.selo_valido(s, 1000.0 + 599, self.CHAVE))

    def test_selo_vence(self):
        s = cortina.selar(1000.0, self.CHAVE, minutos=10)
        self.assertFalse(cortina.selo_valido(s, 1000.0 + 601, self.CHAVE))

    def test_selo_de_outra_chave_nao_vale(self):
        s = cortina.selar(1000.0, self.CHAVE)
        self.assertFalse(cortina.selo_valido(s, 1000.0, b"y" * 32))

    def test_lixo_nao_derruba(self):
        for ruim in ("", ".", "abc", "9999999999.deadbeef", "x" * 5000):
            self.assertFalse(cortina.selo_valido(ruim, 1000.0, self.CHAVE))


class Teto(unittest.TestCase):
    def setUp(self):
        cortina.zerar_tentativas()

    def test_a_sexta_tentativa_nao_passa(self):
        for i in range(cortina.TETO):
            self.assertTrue(cortina.pode_tentar("10.0.0.1", 100.0))
            cortina.anotar_tentativa("10.0.0.1", 100.0)
        self.assertFalse(cortina.pode_tentar("10.0.0.1", 100.0))

    def test_uma_origem_nao_derruba_a_outra(self):
        for i in range(cortina.TETO):
            cortina.anotar_tentativa("10.0.0.1", 100.0)
        self.assertFalse(cortina.pode_tentar("10.0.0.1", 100.0))
        self.assertTrue(cortina.pode_tentar("10.0.0.2", 100.0))

    def test_a_janela_vira(self):
        for i in range(cortina.TETO):
            cortina.anotar_tentativa("10.0.0.1", 100.0)
        self.assertTrue(cortina.pode_tentar("10.0.0.1", 100.0 + cortina.JANELA + 1))

    def test_origem_antiga_e_esquecida(self):
        """Sem poda, o dicionario cresce por IP ate o processo morrer."""
        cortina.anotar_tentativa("10.0.0.1", 100.0)
        cortina.anotar_tentativa("10.0.0.2", 100.0 + cortina.JANELA * 3)
        self.assertNotIn("10.0.0.1", cortina.origens_lembradas())


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python test_cortina.py -v`
Expected: FAIL — `No module named 'cortina'`.

- [ ] **Step 3: Escrever `cortina.py`**

```python
# -*- coding: utf-8 -*-
"""A cortina: o que `dervs.com.br` mostra antes de admitir que e um sistema.

ISTO NAO E A FECHADURA. Seis digitos sao um milhao de combinacoes, e o codigo
que confere esta aqui justamente para que o formulario de login NAO viaje ate o
navegador antes da hora — quem der Ctrl+U na primeira visita nao acha nada,
porque nao ha nada. Quem protege o dado e o login do GitHub, em
`autenticacao.py`, mais a lista de contas em `credencial`.
"""
from __future__ import annotations

import hashlib
import hmac
import threading

import banco

TETO = 5             # tentativas por origem
JANELA = 900         # segundos (15 minutos)
MINUTOS_DO_SELO = 10

_tentativas: dict = {}
_trava = threading.Lock()     # ThreadingHTTPServer: duas requisicoes ao mesmo tempo


def combinacao_atual(con) -> str:
    l = con.execute("SELECT combinacao_hash FROM instalacao WHERE id = 1").fetchone()
    return (l["combinacao_hash"] if l else None) or ""


def garantir_combinacao(con):
    """Gera na primeira subida e devolve o numero EM CLARO, uma unica vez.

    Devolve None se ja existia. Quem chama imprime uma vez e esquece: o numero
    nao volta a existir em lugar nenhum depois desta linha.
    """
    con.execute("INSERT OR IGNORE INTO instalacao (id, criada_em) VALUES (1, ?)",
                (banco.agora(),))
    if combinacao_atual(con):
        con.commit()
        return None
    numero = banco.novo_codigo(6)
    con.execute("UPDATE instalacao SET combinacao_hash = ?, combinacao_em = ?"
                " WHERE id = 1", (banco.hash_senha(numero), banco.agora()))
    con.commit()
    return numero


def trocar(combinacao: str, con) -> None:
    con.execute("INSERT OR IGNORE INTO instalacao (id, criada_em) VALUES (1, ?)",
                (banco.agora(),))
    con.execute("UPDATE instalacao SET combinacao_hash = ?, combinacao_em = ?"
                " WHERE id = 1", (banco.hash_senha(combinacao), banco.agora()))
    con.commit()


def conferir(combinacao: str, con) -> bool:
    """Falha FECHADA: sem combinacao gravada, ninguem entra."""
    guardado = combinacao_atual(con)
    if not guardado:
        return False
    return banco.conferir_senha(combinacao or "", guardado)


# ------------------------------------------------------------------ o selo

def selar(agora_s: float, chave: bytes, minutos: int = MINUTOS_DO_SELO) -> str:
    ate = "%d" % int(agora_s + minutos * 60)
    return ate + "." + _assinar(ate, chave)


def selo_valido(selo: str, agora_s: float, chave: bytes) -> bool:
    ate, _, assinatura = (selo or "").partition(".")
    if not ate.isdigit() or not assinatura:
        return False
    if not hmac.compare_digest(_assinar(ate, chave), assinatura):
        return False
    return agora_s <= int(ate)


def _assinar(ate: str, chave: bytes) -> str:
    return hmac.new(chave, ("cortina|" + ate).encode("utf-8"),
                    hashlib.sha256).hexdigest()


# ------------------------------------------------------- o teto por origem
#
# Por ORIGEM e na ROTA, nao no recurso. A etapa 8 removeu um contador que vivia
# na tabela de pareamento justamente porque contar no recurso deixa um estranho
# matar o acesso de todo mundo com cinco chutes. A etapa 11 reusa isto.

def pode_tentar(origem: str, agora_s: float) -> bool:
    with _trava:
        _podar(agora_s)
        return len(_tentativas.get(origem, ())) < TETO


def anotar_tentativa(origem: str, agora_s: float) -> None:
    with _trava:
        _podar(agora_s)
        _tentativas.setdefault(origem, []).append(agora_s)


def origens_lembradas() -> set:
    with _trava:
        return set(_tentativas)


def zerar_tentativas() -> None:
    with _trava:
        _tentativas.clear()


def _podar(agora_s: float) -> None:
    """Sem isto o dicionario cresce por IP ate o processo morrer."""
    for origem in list(_tentativas):
        recentes = [t for t in _tentativas[origem] if agora_s - t < JANELA]
        if recentes:
            _tentativas[origem] = recentes
        else:
            del _tentativas[origem]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `python test_cortina.py -v`
Expected: PASS, `OK`.

**Conferido antes de escrever este plano:** `banco.conferir_senha` (`banco.py:484-495`) já termina em `hmac.compare_digest`, e `banco.hash_senha` usa `scrypt` com `n=16384` e sal próprio. Nada a fazer aqui.

**Por que `hash_senha` (scrypt) e não `hash_codigo` (HMAC), que existe e é mais rápido:** `hash_codigo` depende da chave do cofre, e quem consegue copiar o `hub.db` da máquina normalmente consegue o `cofre.chave` junto — aí um milhão de combinações caem em segundos. Com `scrypt` a mesma varredura custa cerca de um dia de processador. **Um dia não é "seguro" — é "caro o bastante para uma cortina"**, e é exatamente por isso que a fechadura é a camada do GitHub. Está escrito aqui para o próximo leitor não "otimizar" isto de volta para HMAC.

- [ ] **Step 5: Acrescentar à CI**

Em `.github/workflows/ci.yml`, ao lado dos outros, no mesmo formato:

```yaml
      - name: Testes da cortina
        run: python test_cortina.py
```

- [ ] **Step 6: Commit**

`feat(cortina): seis digitos conferidos no servidor, com teto por origem`

---

### Tarefa 4: `autenticacao.py` — o caminho do GitHub

**Files:**
- Create: `autenticacao.py`, `test_autenticacao.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `banco.*`, `cortina.selar/selo_valido`
- Produces:
  - `url_de_autorizacao(client_id: str, redirect_uri: str, state: str) -> str`
  - `trocar_code(code, client_id, client_secret, abrir=None) -> str` — devolve o token; levanta `ErroDoGithub` em qualquer resposta que não traga `access_token`
  - `identidade(token: str, abrir=None) -> dict` — `{"id": "4242", "login": "thiago", "2fa": True|None}`
  - `entrar_por_github(code, state, state_esperado, con, ...) -> str | None` — devolve o cookie de sessão ou `None`
  - `ErroDoGithub(Exception)`
  - Constantes `AUTORIZAR`, `TROCAR`, `EU` (as três URLs do GitHub)

- [ ] **Step 1: Escrever `test_autenticacao.py`**

```python
# -*- coding: utf-8 -*-
"""Testes do login por GitHub (etapa 9).

NENHUM TESTE TOCA A REDE: as funcoes que falam com o GitHub recebem a funcao de
abrir URL por parametro, e aqui entra um duble.

  1. `state` ausente, trocado ou reusado e recusado.
  2. Id fora da tabela, conta desativada e credencial revogada devolvem a MESMA
     coisa: None. Resposta diferente diria quem existe.
  3. O casamento e pelo id NUMERICO. Login trocado nao entrega a conta.
  4. O token do GitHub nao sobra em lugar nenhum.
  5. Login por GitHub grava `segundo_fator_em`.

    python test_autenticacao.py
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DERVS_AMBIENTE", "local")
os.environ.setdefault("DERVS_COFRE",
                      "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")

import autenticacao  # noqa: E402
import banco         # noqa: E402

# Valores obviamente falsos. Nao ha segredo de verdade em teste nenhum
# deste repositorio, e o varredor de segredo do hook depende disso.
ID_FALSO = "id-de-aplicativo-inventado"
SEGREDO_FALSO = "nao-e-segredo-e-so-um-texto"
VALOR_FALSO = "resposta-inventada-do-duble"


class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def duble(mapa):
    """Devolve uma funcao no lugar de urllib.request.urlopen.

    `mapa` vai de pedaco-da-URL para o dicionario a devolver. URL nao prevista
    levanta AssertionError — teste que sai para a rede tem de estourar, nao
    tentar.
    """
    def abrir(req, timeout=None):
        url = req if isinstance(req, str) else req.full_url
        for pedaco, corpo in mapa.items():
            if pedaco in url:
                return RespostaFalsa(json.dumps(corpo).encode("utf-8"))
        raise AssertionError("URL nao prevista no teste: %s" % url)
    return abrir


class Fluxo(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.con = banco.conectar(str(Path(self.dir.name) / "hub.db"))
        self.addCleanup(self.con.close)
        self.uid = banco.criar_usuario("thiago@teste.local", con=self.con)
        banco.ligar_github(self.uid, "4242", con=self.con)
        self.rede = duble({
            "login/oauth/access_token": {"access_token": VALOR_FALSO},
            "api.github.com/user": {"id": 4242, "login": "thiago",
                                    "two_factor_authentication": True},
        })

    def _entrar(self, state="s1", esperado="s1", rede=None):
        return autenticacao.entrar_por_github(
            code="c1", state=state, state_esperado=esperado, con=self.con,
            client_id=ID_FALSO, client_secret=SEGREDO_FALSO,
            abrir=rede or self.rede)

    def test_entra_e_grava_segundo_fator(self):
        cookie = self._entrar()
        self.assertTrue(cookie)
        s = banco.sessao_valida(cookie, con=self.con)
        self.assertIsNotNone(s)
        self.assertIsNotNone(s["segundo_fator_em"])

    def test_state_trocado_nao_entra(self):
        self.assertIsNone(self._entrar(state="outro", esperado="s1"))

    def test_state_vazio_nao_entra(self):
        self.assertIsNone(self._entrar(state="", esperado=""))

    def test_id_desconhecido_nao_entra(self):
        rede = duble({
            "login/oauth/access_token": {"access_token": VALOR_FALSO},
            "api.github.com/user": {"id": 999999, "login": "estranho"},
        })
        self.assertIsNone(self._entrar(rede=rede))

    def test_login_igual_com_id_diferente_nao_entra(self):
        """O sequestro classico: o login foi trocado e outra pessoa registrou."""
        rede = duble({
            "login/oauth/access_token": {"access_token": VALOR_FALSO},
            "api.github.com/user": {"id": 1, "login": "thiago"},
        })
        self.assertIsNone(self._entrar(rede=rede))

    def test_conta_desativada_nao_entra(self):
        self.con.execute("UPDATE usuario SET desativado_em = ? WHERE id = ?",
                         (banco.agora(), self.uid))
        self.con.commit()
        self.assertIsNone(self._entrar())

    def test_token_do_github_nao_sobra_no_banco(self):
        self._entrar()
        despejo = "\n".join(self.con.iterdump())
        self.assertNotIn(VALOR_FALSO, despejo)

    def test_resposta_do_github_sem_token_estoura(self):
        rede = duble({"login/oauth/access_token": {"error": "bad_verification_code"}})
        with self.assertRaises(autenticacao.ErroDoGithub):
            autenticacao.trocar_code("c1", ID_FALSO, SEGREDO_FALSO, abrir=rede)

    def test_url_de_autorizacao_leva_o_state(self):
        u = autenticacao.url_de_autorizacao(ID_FALSO,
                                            "https://dervs.com.br/volta", "s1")
        self.assertIn("state=s1", u)
        self.assertIn("client_id=" + ID_FALSO, u)
        self.assertTrue(u.startswith("https://github.com/login/oauth/authorize?"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python test_autenticacao.py -v`
Expected: FAIL — `No module named 'autenticacao'`.

- [ ] **Step 3: Escrever `autenticacao.py`**

```python
# -*- coding: utf-8 -*-
"""Quem e voce: o caminho do GitHub, e a sessao que sai dele.

O DERVS nao guarda senha no caminho normal. Quem confere identidade e o GitHub,
que ja obriga segundo fator na conta. O que sobra aqui e conferir se aquela
identidade esta na tabela `credencial` — e nao esta e nunca esteve na mao de
quem chega.
"""
from __future__ import annotations

import json
import secrets
import urllib.parse
import urllib.request

import banco

AUTORIZAR = "https://github.com/login/oauth/authorize"
TROCAR = "https://github.com/login/oauth/access_token"
EU = "https://api.github.com/user"
ESPERA = 10          # segundos. GitHub fora do ar nao pode travar o servidor.
HORAS_DE_SESSAO = 12


class ErroDoGithub(Exception):
    pass


def novo_state() -> str:
    return secrets.token_urlsafe(24)


def url_de_autorizacao(client_id: str, redirect_uri: str, state: str) -> str:
    # `scope` vazio de proposito: o DERVS quer saber QUEM e, e mais nada.
    return AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri,
        "state": state, "scope": "", "allow_signup": "false"})


def trocar_code(code: str, client_id: str, client_secret: str, abrir=None) -> str:
    abrir = abrir or urllib.request.urlopen
    corpo = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": client_secret,
        "code": code}).encode("utf-8")
    req = urllib.request.Request(TROCAR, data=corpo, headers={
        "Accept": "application/json", "User-Agent": "dervs"})
    with abrir(req, timeout=ESPERA) as r:
        resposta = json.loads(r.read().decode("utf-8"))
    token = resposta.get("access_token")
    if not token:
        # NAO ponha `resposta` na mensagem: ela pode trazer o client_secret de
        # volta em alguns erros, e mensagem de excecao vai para log.
        raise ErroDoGithub("o GitHub nao devolveu token: %s"
                           % resposta.get("error", "sem motivo"))
    return token


def identidade(token: str, abrir=None) -> dict:
    abrir = abrir or urllib.request.urlopen
    req = urllib.request.Request(EU, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "User-Agent": "dervs"})
    with abrir(req, timeout=ESPERA) as r:
        u = json.loads(r.read().decode("utf-8"))
    return {"id": str(u.get("id") or ""), "login": u.get("login") or "",
            "2fa": u.get("two_factor_authentication")}


def entrar_por_github(code, state, state_esperado, con, client_id,
                      client_secret, abrir=None):
    """Devolve o cookie da sessao, ou None. NUNCA diz por que falhou.

    Motivo diferente por causa diferente e o que transforma uma tela de login em
    uma lista de quem existe.
    """
    if not state or not state_esperado or state != state_esperado:
        return None
    try:
        token = trocar_code(code, client_id, client_secret, abrir=abrir)
        quem = identidade(token, abrir=abrir)
    except (ErroDoGithub, OSError, ValueError):
        return None
    finally:
        token = None          # o token do GitHub morre aqui. Nao vai ao banco.
    if not quem["id"]:
        return None
    if quem["2fa"] is False:
        # So barra quando o GitHub AFIRMA que nao ha segundo fator. Campo ausente
        # cai na decisao declarada na spec: confiar na conta do GitHub.
        return None
    usuario = banco.usuario_por_github(quem["id"], con=con)
    if not usuario:
        return None
    cookie = banco.novo_token()
    banco.abrir_sessao(usuario["id"], cookie,
                       banco.prazo(HORAS_DE_SESSAO * 3600), con=con)
    # Identidade e segundo fator acontecem no MESMO passo quando quem confere e
    # o GitHub. Decisao declarada na spec, nao um descuido.
    #
    # `cookie_novo` NAO e opcional fora de teste: `confirmar_segundo_fator`
    # documenta em `banco.py:887` que passar vazio mantem o identificador, e
    # identificador igual antes e depois de autenticar e o que faz fixacao de
    # sessao funcionar. Aqui o cookie nasce nesta funcao e nao houve "antes",
    # entao a fixacao nao se aplica — mas rotacionar custa uma linha e mantem o
    # contrato do modulo valendo para quem ler depois.
    return banco.confirmar_segundo_fator(cookie, banco.novo_token(), con=con)
```

`banco.confirmar_segundo_fator(cookie, cookie_novo, con)` devolve `cookie_novo`. Conferido em `banco.py:887-909`.

- [ ] **Step 4: Rodar e ver passar**

Run: `python test_autenticacao.py -v`
Expected: PASS.

- [ ] **Step 5: Acrescentar à CI e commitar**

```yaml
      - name: Testes de autenticacao
        run: python test_autenticacao.py
```

`feat(auth): entrar com GitHub, casando pelo id numerico e sem guardar token`

---

### Tarefa 5: O comando `convidar` — a única porta para criar conta

**Files:**
- Modify: `autenticacao.py` (bloco `main()` no fim)
- Test: `test_autenticacao.py`

**Interfaces:**
- Produces: `convidar(login: str, email: str, con, abrir=None) -> int`; `main(argv)` para `python autenticacao.py convidar <login> <email>`

- [ ] **Step 1: Teste**

```python
class Convite(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.con = banco.conectar(str(Path(self.dir.name) / "hub.db"))
        self.addCleanup(self.con.close)
        self.rede = duble({"api.github.com/users/thiago": {"id": 4242,
                                                           "login": "thiago"}})

    def test_convidar_cria_conta_e_credencial(self):
        uid = autenticacao.convidar("thiago", "thiago@teste.local",
                                    con=self.con, abrir=self.rede)
        self.assertEqual(banco.usuario_por_github("4242", con=self.con)["id"], uid)
        # Conta criada por convite nao tem senha nenhuma.
        self.assertIsNone(banco.credencial_por_email("thiago@teste.local",
                                                     con=self.con))

    def test_convidar_duas_vezes_estoura_em_vez_de_duplicar(self):
        autenticacao.convidar("thiago", "thiago@teste.local",
                              con=self.con, abrir=self.rede)
        with self.assertRaises(Exception):
            autenticacao.convidar("thiago", "outro@teste.local",
                                  con=self.con, abrir=self.rede)
```

- [ ] **Step 2: Rodar e ver falhar.** Run: `python test_autenticacao.py Convite -v`

- [ ] **Step 3: Implementar**

```python
def convidar(login: str, email: str, con=None, abrir=None) -> int:
    """Cria conta e amarra ao id numerico do GitHub. Nao ha caminho pela web.

    Roda DENTRO do servidor. E de proposito que criar conta custe um comando de
    quem tem acesso a maquina: e isso que mantem o cadastro fechado sem precisar
    de uma lista de convidados em lugar nenhum.
    """
    abrir = abrir or urllib.request.urlopen
    req = urllib.request.Request(
        "https://api.github.com/users/" + urllib.parse.quote(login.strip()),
        headers={"Accept": "application/vnd.github+json", "User-Agent": "dervs"})
    with abrir(req, timeout=ESPERA) as r:
        u = json.loads(r.read().decode("utf-8"))
    if not u.get("id"):
        raise ErroDoGithub("login do GitHub nao encontrado: %s" % login)
    fechar = con is None
    con = con or banco.conectar()
    try:
        uid = banco.criar_usuario(email, nome=u.get("name") or login, con=con)
        banco.ligar_github(uid, str(u["id"]), con=con)
        return uid
    finally:
        if fechar:
            con.close()
```

E um `main(argv)` que aceita `convidar <login> <email>` e imprime `conta criada: <email> -> github #<id>`. Comando desconhecido imprime o uso e devolve 2.

- [ ] **Step 4: Rodar e ver passar.** Run: `python test_autenticacao.py -v`

- [ ] **Step 5: Commit.** `feat(auth): comando convidar, a unica porta para criar conta`

---

### Tarefa 6: `servir.py` — classificar toda rota e negar por padrão

**Files:**
- Modify: `servir.py` (`TOKEN` em `:111`; `Hub._despachar` em `:216-222`; `Hub._pagina` em `:267`; `ROTAS` em `:362-368`)
- Test: `test_rotas.py`, `test_servir.py`

**Interfaces:**
- Consumes: `cortina.*`, `autenticacao.*`, `banco.sessao_valida`
- Produces: `Rota = namedtuple("Rota", "metodo funcao acesso")` com `acesso` em `{"aberta", "cortina", "dado"}`; `Hub._sessao() -> dict | None`; rotas `/entrada`, `/entrar/github`, `/entrar/github/retorno`, `/sair`

- [ ] **Step 1: Escrever os testes**

Em `test_rotas.py`:

```python
    def test_toda_rota_declara_acesso(self):
        """Nega por padrao INCLUSIVE no teste: rota sem classificacao reprova."""
        validos = {"aberta", "cortina", "dado"}
        for caminho, rota in servir.ROTAS.items():
            self.assertIn(getattr(rota, "acesso", None), validos,
                          "rota sem classificacao declarada: %s" % caminho)

    def test_registro_nao_existe(self):
        self.assertNotIn("/api/registro", servir.ROTAS)
```

Em `test_servir.py`, com o servidor de verdade num porta livre:

```python
    def test_rota_de_dado_sem_sessao_nao_vaza_nome_de_projeto(self):
        for caminho, rota in servir.ROTAS.items():
            if rota.acesso != "dado":
                continue
            r = self._pedir(caminho)
            self.assertIn(r.status, (401, 302), caminho)
            self.assertNotIn("dervs", r.corpo.lower(), caminho)

    def test_a_capa_nao_entrega_o_formulario_de_login(self):
        corpo = self._pedir("/").corpo.lower()
        for proibido in ("oauth", "github", "client_id", "entrar com"):
            self.assertNotIn(proibido, corpo)

    def test_errar_e_acertar_a_combinacao_devolvem_o_mesmo(self):
        errado = self._postar("/entrada", {"combinacao": "111111"})
        certo = self._postar("/entrada", {"combinacao": self.combinacao})
        self.assertEqual(errado.status, certo.status)
        self.assertEqual(errado.corpo, certo.corpo)
        self.assertNotIn("cortina=", errado.cabecalhos.get("Set-Cookie", ""))
        self.assertIn("cortina=", certo.cabecalhos.get("Set-Cookie", ""))

    def test_nenhuma_resposta_traz_segredo(self):
        """Varre o JSON inteiro atras dos valores gravados."""
        for caminho, rota in servir.ROTAS.items():
            corpo = self._pedir(caminho).corpo
            for segredo in (self.combinacao, self.client_secret, self.totp_cru):
                self.assertNotIn(segredo, corpo, caminho)
```

- [ ] **Step 2: Rodar e ver falhar.** Run: `python test_rotas.py -v` — falha por `acesso` inexistente.

- [ ] **Step 3: Implementar**

1. `Rota = namedtuple("Rota", "metodo funcao acesso")` e **toda** entrada de `ROTAS` ganha o terceiro campo. `/` e `/entrada` são `"aberta"`; `/entrar/github*` são `"cortina"`; `/api/dados` e `/api/silenciar` são `"dado"`; os estáticos são `"aberta"`.
2. `_despachar` passa a, nesta ordem: conferir Host → achar a rota → **se `acesso == "cortina"`, exigir selo válido; se `acesso == "dado"`, exigir sessão com `segundo_fator_em` preenchido** → só então chamar a função. Rota não encontrada e rota negada devolvem o mesmo 404/401 sem detalhe.
3. `TOKEN = secrets.token_urlsafe(24)` global **sai**. O anti-CSRF passa a ser derivado da sessão: `hmac.new(chave_do_cofre(), ("csrf|" + id_da_sessao).encode(), sha256).hexdigest()`, injetado na página autenticada no lugar de `__TOKEN__`. `_silenciar` confere contra o da sessão de quem pediu.
4. `_pagina` passa a servir `index-cortina.html` quando não há selo, e `index.html` quando há sessão.
5. Cookies: `HttpOnly`, `SameSite=Lax`, `Path=/`, e `Secure` quando `os.environ.get("DERVS_AMBIENTE") != "local"`.
6. `main()` chama `cortina.garantir_combinacao(con)` e, se voltar um número, imprime **uma vez**: `COMBINACAO DE ACESSO (anote agora, nao aparece de novo): 123456`.

- [ ] **Step 4: Rodar tudo.** Run: `python test_rotas.py -v && python test_servir.py -v && python test_cortina.py -v && python test_autenticacao.py -v && python test_banco.py -v`
Expected: `OK` em todos.

- [ ] **Step 5: Commit.** `feat(servir): toda rota declara acesso, e o TOKEN global vira anti-CSRF por sessao`

---

### Tarefa 7: A tela da cortina

**Files:**
- Create: `index-cortina.html`
- Modify: `servir.py` (`ESTATICOS_OK`), `docs/esteira/dervs/design.md`

**Antes de escrever uma linha de HTML/CSS/JS:** invoque `modern-web-guidance` e `frontend-design`. É regra da casa, e o gatilho da primeira quase nunca dispara sozinho em pedido escrito em português.

- [ ] **Step 1: Direção estética.** Referência dada pelo dono: `museuparticular.com.br` — fundo quase preto, serifada de peso alto, um traço vermelho, teclado numérico de 3×4 com dígitos, um apagador e um confirmar. Nenhum logo, nenhum menu, nenhuma palavra que diga o que o sistema é.
- [ ] **Step 2: Escrever a tela.** Seis marcadores de dígito no topo. `POST /entrada` com `{"combinacao": "######"}`. Resposta sem cookie: **nada acontece** — sem mensagem, sem tremida, sem cor. Com cookie: revela um botão só, `Entrar com GitHub`, que é um link para `/entrar/github`.
- [ ] **Step 3: Conferir o que a página entrega.** Run: `python -c "print(open('index-cortina.html',encoding='utf-8').read().lower().count('github'))"` — Expected: `0`. O botão é montado pela resposta do servidor, não está no arquivo.
- [ ] **Step 4: Acessibilidade mínima.** Teclado físico funciona (dígitos, Backspace, Enter); os botões são `<button>` de verdade com `aria-label`; `prefers-reduced-motion` respeitado.
- [ ] **Step 5: Rodar `python test_servir.py -v`.** `test_a_capa_nao_entrega_o_formulario_de_login` tem de passar.
- [ ] **Step 6: Commit.** `feat(cortina): a tela que nao diz o que este sistema e`

---

### Tarefa 8: README, roteiro do OAuth e verificação final

**Files:**
- Modify: `README.md`, `docs/esteira/dervs/HANDOFF-fatia-1.md`
- Create: `docs/operacao/registrar-app-github.md`

- [ ] **Step 1: Escrever o roteiro do registro do OAuth App**, em `docs/operacao/registrar-app-github.md`, **para leigo**: cada campo do formulário do GitHub com o valor exato a digitar (`Application name: DERVS`, `Homepage URL: https://dervs.com.br`, `Authorization callback URL: https://dervs.com.br/entrar/github/retorno`), onde clicar para gerar o Client Secret, e onde ele vai parar (variável `DERVS_GITHUB_SECRET` **dentro do servidor**, nunca em `.env` de máquina de trabalho, nunca em commit, nunca em conversa). Inclua o equivalente local: `http://localhost:4777/entrar/github/retorno`.
- [ ] **Step 2: README** — documentar `DERVS_AMBIENTE`, `DERVS_COFRE`, `DERVS_GITHUB_ID`, `DERVS_GITHUB_SECRET`, a combinação local fixa `000000` (dado de teste, não segredo) e o comando `python autenticacao.py convidar <login> <email>`.
- [ ] **Step 3: Rodar a suíte inteira.** Run: `for t in test_*.py; do echo "== $t"; python "$t" || break; done`
Expected: `OK` em todos os 12 arquivos.
- [ ] **Step 4: Provar na tela, clicando.** Subir `python servir.py`, abrir `http://localhost:4777`, ver a capa, digitar `000000`, ver o botão aparecer. **Ver a faixa aparecer não é prova — o botão tem de disparar.** Reinicie `servir.py` depois de qualquer edição em `.py`: ele importa os módulos na subida e a tela mostraria a versão velha.
- [ ] **Step 5: Revisores especialistas.** Despache `security-reviewer` (obrigatório: auth), `python-reviewer` e `database-reviewer` (migração), em paralelo. **Commite antes de despachar** — revisor com Bash escreve no disco.
- [ ] **Step 6: Atualizar o handoff, abrir o PR, mesclar com CI verde.**

---

## Auto-revisão deste plano

- **Cobertura da spec:** cortina → Tarefas 3, 6, 7. Teto por origem → Tarefa 3. `credencial` e migração → Tarefas 1, 2. OAuth → Tarefa 4. Casamento por id numérico → Tarefas 2, 4. Rejeição idêntica → Tarefas 4, 6. Cadastro fechado → Tarefas 5, 6. Porta de emergência → Tarefas 1, 2 (as credenciais `senha`/`totp` sobrevivem; nenhuma rota as oferece). `instalacao` → Tarefas 1, 3. Client Secret → Tarefas 4, 8. Provas 1–15 da spec → Tarefas 3, 4, 6.
- **Nomes conferidos entre tarefas:** `usuario_por_github`, `ligar_github`, `criar_usuario(senha=None)`, `garantir_combinacao`, `selar`/`selo_valido`, `pode_tentar`/`anotar_tentativa`, `entrar_por_github`, `convidar`, `Rota.acesso` — todos definidos antes do primeiro uso.
- **Ponto que exige conferência no código, e está marcado como tal:** o retorno de `banco.confirmar_segundo_fator` (Tarefa 4, Step 3). Não é placeholder: o teste decide, e a instrução diz o que fazer nos dois casos.
