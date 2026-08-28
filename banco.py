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

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BANCO = AQUI / "hub.db"

INFRA = "_infra"          # projeto sintetico: containers e portas da maquina
QUOTA = "_quota"          # projeto sintetico: cota de minutos do Actions, da CONTA
CAMADAS = ("local", "github", "pesado")

# Dono das linhas que nasceram antes de existir conta. Nao e um usuario de
# verdade — por isso `usuario_id` das tabelas de decisao NAO tem chave
# estrangeira para `usuario`: o zero precisa continuar valendo.
DONO_LOCAL = 0
# A conta que a porta `/entrar/local` abre. Ela e a dona da coleta DESTA
# maquina: os coletores gravam nela, e nao num `DONO_LOCAL` que sessao nenhuma
# consegue ler. E conta de TESTE, e por isso `conta_local()` so a cria em
# ambiente local — no servidor ninguem roda coletor, quem alimenta e o agente.
CONTA_LOCAL = "dono@teste.local"

# Seis digitos sao um milhao de possibilidades. O teto e o que impede chutar.
MAX_TENTATIVAS_PAREAMENTO = 5

# Tetos do que chega de uma maquina pareada. Uma maquina autorizada nao e uma
# maquina confiavel: token vazado, ou agente adulterado, escreve o que quiser
# neste banco. Sem teto, um relatorio de 4 MB repetido enche o disco do servidor
# e deixa o painel ilegivel com dez mil linhas de projeto inventado.
MAX_PROJETOS_POR_RELATORIO = 300
MAX_NOME_DE_PROJETO = 200
MAX_CAMINHO = 500
MAX_AVISOS = 30
# As duas linhas de sistema que moram na mesma tabela `medida`. Relatorio de
# maquina nao pode escrever nelas — ver `receber_relatorio`.
RESERVADOS = (INFRA, QUOTA)
# Quantos projetos DISTINTOS uma conta pode acumular na `medida`. O teto de
# relatorio nao segura disco: 300 nomes NOVOS por envio, mil envios, e o volume
# do servidor acaba. Ver `receber_relatorio`.
MAX_PROJETOS_POR_CONTA = 1000
# E o teto de CADA projeto. Sem ele, o teto de 4 MiB do corpo e o de 60 envios
# por 15 min ainda somavam ~4 GiB numa conta — e `montar_estado` faz `json.loads`
# de tudo aquilo, num processo unico compartilhado por todos os inquilinos: o
# painel do dono legitimo derrubava o servidor. Achado da revisao da correcao.
MAX_BYTES_POR_PROJETO = 64 * 1024

ESQUEMA = """
-- `usuario_id` NA CHAVE. Sem ele a medicao era um balcao unico: duas contas
-- com um projeto de mesmo nome — "site", "api" — se sobrescreviam pelo
-- ON CONFLICT, e `ler_tudo` devolvia a tabela inteira para qualquer sessao. Uma
-- maquina pareada por uma conta escrevia por cima do alerta de outra, e revogar
-- a maquina nao desfazia. Achado BLOQUEANTE das revisoes de banco e de
-- seguranca da etapa 11, com prova rodada. Sem chave estrangeira pelo mesmo
-- motivo das outras tabelas com dono: DONO_LOCAL = 0 nao e conta de verdade.
CREATE TABLE IF NOT EXISTS medida (
    usuario_id INTEGER NOT NULL DEFAULT 0,
    projeto    TEXT NOT NULL,
    camada     TEXT NOT NULL,
    medido_em  TEXT NOT NULL,
    dados      TEXT NOT NULL,
    PRIMARY KEY (usuario_id, projeto, camada)
);

CREATE TABLE IF NOT EXISTS historico (
    medido_em TEXT NOT NULL,
    chave     TEXT NOT NULL,
    valor     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_historico ON historico (chave, medido_em);

-- Silenciar uma pendencia e decisao do dono, nao do coletor: por isso vive no
-- banco e sobrevive a recoleta.
--
-- O dono da linha entrou na etapa 8. Antes a chave era so o `id`: com dois
-- usuarios, o "x" de um escondia o alerta do outro, e isso e IDOR por desenho
-- de esquema — nao ha rota que conserte. Banco velho e reconstruido por
-- `migrar()`, e o que estava la vira do DONO_LOCAL.
--
-- A ordem da chave e (usuario_id, id), nao o contrario: toda consulta comeca
-- por "as deste usuario". O SQLite nao troca chave primaria, entao inverter
-- depois custaria uma segunda reconstrucao de tabela — e reconstrucao e a
-- operacao mais arriscada que existe aqui.
--
-- `usuario_id` NAO tem chave estrangeira: o DONO_LOCAL = 0 nao e um usuario de
-- verdade e precisa continuar valendo. O preco disso e que apagar uma conta NAO
-- limpa esta tabela: quem for atender "apague meus dados" tem de lembrar dela e
-- da `pendencia_arquivada` na mao.
CREATE TABLE IF NOT EXISTS pendencia_estado (
    id             TEXT NOT NULL,
    usuario_id     INTEGER NOT NULL DEFAULT 0,
    silenciada_ate TEXT,
    anotado_em     TEXT NOT NULL,
    PRIMARY KEY (usuario_id, id)
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

-- Gasto que NAO passou pela fila. O botao "Resolver" dispara a mesma sessao,
-- com o mesmo custo, e nao encostava na tabela `fila` — entao o teto do dia
-- nao o enxergava. Duas sessoes em paralelo (uma da fila, uma do botao)
-- gastavam sem nenhuma das duas ver a outra. Achado do revisor em 25/08/2026.
CREATE TABLE IF NOT EXISTS gasto (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    quando       TEXT NOT NULL,
    origem       TEXT NOT NULL DEFAULT '',
    custo_usd    REAL NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS ix_gasto_dia ON gasto (quando);

-- ---------------------------------------------------------------------------
-- Etapa 8: as seis tabelas que tiram o HUB de uma maquina so.
--
-- Regra que vale para todas: SEGREDO NAO ENTRA EM CLARO. Senha vira hash de
-- scrypt, cookie e token de agente viram hash de SHA-256, codigo de pareamento
-- vira HMAC com a chave do cofre, e o segredo do segundo fator entra cifrado.
-- Deixar isso "para a etapa 9" custaria migrar dado e rotacionar segredo.
-- ---------------------------------------------------------------------------

-- O `CHECK (id <> 0)` nao e paranoia: o SQLite aceita id explicito mesmo com
-- AUTOINCREMENT, e uma conta de id 0 herdaria todo silenciamento e todo
-- arquivamento do DONO_LOCAL. Grátis agora, reconstrucao de tabela depois.
-- A `usuario` diz QUEM a pessoa e, e so isso. Como ela prova quem e mora na
-- `credencial`, la embaixo. Ate a etapa 8 a senha e o segredo do TOTP eram
-- colunas daqui, e isso amarrava cada pessoa a UM jeito de entrar — uma conta
-- que so usa GitHub nao tem senha nenhuma para por aqui, e obrigar uma seria
-- inventar segredo sem dono.
CREATE TABLE IF NOT EXISTS usuario (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT CHECK (id <> 0),
    email              TEXT NOT NULL UNIQUE CHECK (length(trim(email)) > 0),
    nome               TEXT NOT NULL DEFAULT '',
    criado_em          TEXT NOT NULL,
    desativado_em      TEXT
);

-- As maneiras que uma pessoa tem de provar quem e. Uma pessoa pode ter varias.
-- E esta separacao que faz chave de acesso (passkey) entrar na Fatia 2 como
-- acrescimo em vez de reescrita.
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
    -- O CHECK e o que tira a garantia "uma senha por pessoa" da convencao e a
    -- poe no banco: sem ele, um chamador que passasse o e-mail criaria uma
    -- SEGUNDA credencial de senha, e `credencial_por_email` devolveria uma das
    -- duas sem criterio. O segundo CHECK e o mesmo raciocinio do id numerico:
    -- nada impedia gravar um login de texto na credencial do GitHub.
    CHECK (tipo NOT IN ('senha','totp') OR identificador = CAST(usuario_id AS TEXT)),
    CHECK (tipo <> 'github' OR identificador GLOB '[0-9]*'),
    -- A peca central: dois usuarios nao reivindicam o mesmo id do GitHub, e
    -- ninguem tem duas senhas.
    UNIQUE (tipo, identificador)
);
CREATE INDEX IF NOT EXISTS ix_credencial_dono ON credencial (usuario_id, tipo);

-- Uma linha, e so uma: a configuracao desta instalacao do DERVS. Hoje guarda
-- so a impressao digital da combinacao da cortina — os seis digitos que a
-- pagina de entrada pede antes de admitir que existe um sistema aqui.
CREATE TABLE IF NOT EXISTS instalacao (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    combinacao_hash TEXT,     -- scrypt dos seis digitos. NULL = ainda nao gerada.
    combinacao_em   TEXT,
    criada_em       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessao (
    id               TEXT PRIMARY KEY,   -- hash do cookie, nunca o cookie
    usuario_id       INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    criado_em        TEXT NOT NULL,
    -- O formato e cobrado no banco porque a comparacao e por TEXTO. Misturar
    -- "…08:00Z" com "…08:00+00:00" inverte o resultado: o mesmo instante, e o
    -- sufixo Z sempre "vence" — uma sessao gravada assim valeria alem do prazo.
    -- Use `banco.prazo()` para produzir este valor.
    expira_em        TEXT NOT NULL
                     CHECK (expira_em LIKE '____-__-__T__:__:__+00:00'),
    -- Senha conferida e segundo fator conferido sao dois momentos. Sessao com
    -- este campo em NULL passou so pela senha.
    segundo_fator_em TEXT,
    encerrada_em     TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessao_dono ON sessao (usuario_id, expira_em);

CREATE TABLE IF NOT EXISTS maquina (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    nome        TEXT NOT NULL DEFAULT '',
    token_hash  TEXT NOT NULL UNIQUE,   -- hash do token do agente
    criado_em   TEXT NOT NULL,
    visto_em    TEXT,                   -- ultimo alo do agente; o selo da 10 le daqui
    revogada_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_maquina_dono ON maquina (usuario_id);

CREATE TABLE IF NOT EXISTS pareamento (
    codigo_hash TEXT PRIMARY KEY,       -- HMAC do codigo de seis digitos
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    criado_em   TEXT NOT NULL,
    expira_em   TEXT NOT NULL
                CHECK (expira_em LIKE '____-__-__T__:__:__+00:00'),
    -- Chute contra ESTE codigo. Nao e o teto de forca bruta da instalacao: esse
    -- e por origem (IP/sessao) e mora na rota, na etapa 11. Contar aqui o chute
    -- que nao casou com codigo nenhum deixava um usuario matar o pareamento do
    -- outro, e isso e negacao de servico entre contas.
    tentativas  INTEGER NOT NULL DEFAULT 0,
    usado_em    TEXT,
    -- SET NULL, nao CASCADE: apagar a maquina nao pode apagar o registro de
    -- que aquele codigo foi usado. Sem isto, `DELETE FROM maquina` era recusado
    -- e a conta ficava com maquina que ninguem conseguia remover.
    maquina_id  INTEGER REFERENCES maquina(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS projeto_conectado (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    maquina_id   INTEGER NOT NULL REFERENCES maquina(id) ON DELETE CASCADE,
    projeto      TEXT NOT NULL CHECK (length(trim(projeto)) > 0),
    caminho      TEXT NOT NULL DEFAULT '',
    visto_em     TEXT NOT NULL,
    arquivado_em TEXT,
    UNIQUE (maquina_id, projeto)
);

-- O irmao definitivo do "esconder por 24 h". MOTIVO E DATA SAO OBRIGATORIOS:
-- arquivamento permanente sem rastro e pior que o silencio temporario que ele
-- substitui — ninguem consegue depois responder "por que isso sumiu?".
--
-- O CHECK existe porque "exige motivo" nao pode morar so no Python: hoje ha um
-- escritor, e daqui a duas etapas ha tres. Invariante de negocio que vive fora
-- do banco e uma promessa, nao uma regra.
--
-- Como em `pendencia_estado`, `usuario_id` nao tem chave estrangeira (o zero
-- precisa valer) — e por isso apagar uma conta nao limpa esta tabela.
CREATE TABLE IF NOT EXISTS pendencia_arquivada (
    id              TEXT NOT NULL,
    usuario_id      INTEGER NOT NULL DEFAULT 0,
    motivo          TEXT NOT NULL CHECK (length(trim(motivo)) > 0),
    arquivado_em    TEXT NOT NULL,
    desarquivado_em TEXT,
    PRIMARY KEY (usuario_id, id)
);

-- ---------------------------------------------------------------------------
-- As portas de entrada (desenho de 26/08/2026).
--
-- POR QUE NAO CABEM NA `credencial`, que ate tem 'passkey' na lista de tipos:
--
--   chave_de_acesso     tem um campo que MUDA a cada uso — o contador de
--                       assinaturas, que e a unica defesa contra passkey
--                       copiada. A `credencial` nao tem coluna para isso, e
--                       enfiar um contador em `segredo_hash` seria mentir
--                       sobre o que a coluna guarda.
--   codigo_recuperacao  sao DEZ linhas por pessoa, e o UNIQUE (tipo,
--                       identificador) da `credencial` a limita a uma.
--
-- E o mais importante: NAO HA SEGREDO EM NENHUMA DAS DUAS. A primeira guarda a
-- chave PUBLICA, que so serve para conferir assinatura e nao abre nada. A
-- segunda guarda impressao digital. Uma copia inteira do hub.db nao entrega a
-- conta de ninguem — e essa e a diferenca entre isto e guardar senha.
CREATE TABLE IF NOT EXISTS chave_de_acesso (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    -- O id que o autenticador deu a esta credencial, em base64url. UNIQUE
    -- global, e nao por usuario: duas contas reivindicando a mesma credencial
    -- e sequestro de conta, nao um detalhe de indice.
    cred_id     TEXT NOT NULL UNIQUE CHECK (length(trim(cred_id)) > 0),
    -- As coordenadas da chave PUBLICA, em hexadecimal. Texto, e nao INTEGER:
    -- sao numeros de 256 bits, e o INTEGER do SQLite tem 64.
    chave_x     TEXT NOT NULL,
    chave_y     TEXT NOT NULL,
    apelido     TEXT NOT NULL DEFAULT '',
    contador    INTEGER NOT NULL DEFAULT 0 CHECK (contador >= 0),
    criado_em   TEXT NOT NULL,
    usado_em    TEXT,
    revogada_em TEXT
);
CREATE INDEX IF NOT EXISTS ix_chave_dono
    ON chave_de_acesso (usuario_id, revogada_em);

-- Dez codigos de uso unico, mostrados UMA vez. A saida de emergencia do dia em
-- que o celular quebra e o PC morre no mesmo mes. Sem eles, "login sem senha"
-- com duas pessoas e uma conta a um aparelho de distancia de ficar trancada
-- para sempre — e aqui nao ha recuperacao por e-mail, de proposito.
CREATE TABLE IF NOT EXISTS codigo_recuperacao (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    codigo_hash TEXT NOT NULL UNIQUE,
    criado_em   TEXT NOT NULL,
    usado_em    TEXT
);
CREATE INDEX IF NOT EXISTS ix_codigo_dono
    ON codigo_recuperacao (usuario_id, usado_em);
"""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar(caminho=None) -> sqlite3.Connection:
    con = sqlite3.connect(BANCO if caminho is None else caminho, timeout=15)
    con.row_factory = sqlite3.Row
    # WAL: o servidor le enquanto o coletor escreve, sem um travar o outro.
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=15000")
    # Sem isto o ON DELETE CASCADE do esquema e so comentario bonito: o SQLite
    # nasce com chave estrangeira DESLIGADA, e por conexao.
    con.execute("PRAGMA foreign_keys=ON")
    # A migracao vem ANTES do esquema, e a ordem nao e estetica. Se viesse
    # depois, um `CREATE TABLE IF NOT EXISTS` recriaria a `pendencia_estado`
    # vazia no formato novo; `migrar()` veria a coluna `usuario_id` presente,
    # devolveria na hora, e o dado antigo ficaria inalcancavel para sempre.
    migrar(con)
    con.executescript(ESQUEMA)
    return con


def criar(caminho=None) -> None:
    """Cria (ou atualiza) o banco e fecha. Serve de comando de conferencia."""
    conectar(caminho).close()


def migrar(con: sqlite3.Connection) -> None:
    """Leva um hub.db antigo para o esquema de hoje.

    Roda em TODA conexao, entao cada passo tem de ser barato e inofensivo na
    segunda vez — a checagem e um `PRAGMA table_info`, que nao toca o disco.

    Uma funcao por migracao, e todas chamadas aqui. Nao junte duas num `if` so:
    cada uma tem a propria condicao de "ja rodou", e uma sair na frente da outra
    com `return` deixaria a seguinte sem rodar nunca — foi exatamente o risco de
    ter posto a segunda no fim do corpo da primeira.
    """
    _migrar_pendencia_estado(con)
    _migrar_credencial(con)
    _migrar_medida(con)


# As tabelas que apontam para `usuario`. A migracao confere so estas: varrer o
# banco inteiro faria um orfao antigo, de outra tabela, travar toda subida.
FILHAS_DE_USUARIO = ("credencial", "sessao", "maquina", "pareamento",
                     "chave_de_acesso", "codigo_recuperacao")


def _orfaos(con: sqlite3.Connection) -> int:
    """Quantas linhas das filhas da `usuario` apontam para lugar nenhum.

    So as filhas, e so as que EXISTEM: o `ESQUEMA` roda DEPOIS da migracao,
    entao num hub.db anterior a etapa 8 varias delas ainda nao nasceram, e
    `PRAGMA foreign_key_check(x)` numa tabela ausente levanta erro.
    """
    presentes = {l[0] for l in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    total = 0
    for filha in FILHAS_DE_USUARIO:
        if filha in presentes:
            total += len(list(con.execute("PRAGMA foreign_key_check(%s)" % filha)))
    return total


def _religar_fk(con: sqlite3.Connection) -> None:
    """`PRAGMA foreign_keys` e NO-OP silencioso com transacao aberta.

    Medido na revisao de 26/08/2026. Se a conexao sair daqui dentro de uma
    transacao, religar falharia calado e ela voltaria ao servidor com a chave
    estrangeira desligada — o `ON DELETE CASCADE` do esquema viraria enfeite.
    Neste caso e melhor nao devolver a conexao nenhuma.
    """
    if con.in_transaction:
        con.rollback()
    con.execute("PRAGMA foreign_keys=ON")


def _migrar_pendencia_estado(con: sqlite3.Connection) -> None:
    """`pendencia_estado` ganhou dono (etapa 8). O SQLite nao
    sabe trocar chave primaria, entao a tabela e reconstruida; o que ja estava
    la vira do DONO_LOCAL, que e exatamente o que era — a decisao do dono desta
    maquina.
    """
    forma = list(con.execute("PRAGMA table_info(pendencia_estado)"))
    if not forma:
        return                                   # banco novo: o ESQUEMA ja faz certo
    colunas = {l[1] for l in forma}
    # A condicao olha a CHAVE, nao a existencia da coluna. Um banco que passou
    # por uma versao intermediaria desta etapa tem `usuario_id` mas com a chave
    # na ordem errada — e essa e a hora de arrumar, porque a proxima chance
    # custaria outra reconstrucao de tabela.
    chave = [l[1] for l in sorted((l for l in forma if l[5]), key=lambda l: l[5])]
    if chave == ["usuario_id", "id"]:
        return
    tinha_dono = "usuario_id" in colunas
    # Reconstrucao com FK desligada: e o procedimento que o proprio SQLite
    # recomenda, e aqui nao ha nada apontando para esta tabela. O pragma e por
    # conexao e nao vaza para os outros processos.
    con.execute("PRAGMA foreign_keys=OFF")
    try:
        # TUDO OU NADA. `executescript` faria COMMIT implicito e rodaria os
        # quatro comandos como quatro transacoes soltas: uma queda entre o DROP
        # e o RENAME apagaria a tabela e deixaria a copia orfa, sem excecao
        # nenhuma e sem nunca tentar de novo.
        con.execute("BEGIN IMMEDIATE")
        # DE NOVO, E AGORA DENTRO DA TRANSACAO. A leitura la em cima aconteceu
        # antes do lock: dois processos subindo juntos leem os dois "preciso
        # migrar", um migra e commita, e o outro chega aqui com a decisao
        # obsoleta. Sem esta releitura ele refaz a reconstrucao com um
        # `tinha_dono` velho e joga o silenciamento de TODAS as contas para o
        # dono local. Achado da revisao de banco de 26/08/2026 — o comentario
        # que estava aqui afirmava que o BEGIN resolvia isso, e nao resolvia:
        # o BEGIN vinha nove linhas depois da decisao.
        forma = list(con.execute("PRAGMA table_info(pendencia_estado)"))
        chave = [l[1] for l in sorted((l for l in forma if l[5]),
                                      key=lambda l: l[5])]
        if chave == ["usuario_id", "id"]:
            con.rollback()
            return
        tinha_dono = "usuario_id" in {l[1] for l in forma}
        con.execute("DROP TABLE IF EXISTS pendencia_estado_nova")
        con.execute("""CREATE TABLE pendencia_estado_nova (
                id             TEXT NOT NULL,
                usuario_id     INTEGER NOT NULL DEFAULT 0,
                silenciada_ate TEXT,
                anotado_em     TEXT NOT NULL,
                PRIMARY KEY (usuario_id, id))""")
        con.execute("INSERT INTO pendencia_estado_nova"
                    " (id, usuario_id, silenciada_ate, anotado_em)"
                    " SELECT id, %s, silenciada_ate, anotado_em FROM pendencia_estado"
                    % ("usuario_id" if tinha_dono else "0"))
        con.execute("DROP TABLE pendencia_estado")
        con.execute("ALTER TABLE pendencia_estado_nova RENAME TO pendencia_estado")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        _religar_fk(con)


def _dono_da_medida_antiga(con: sqlite3.Connection) -> int:
    """A conta local — mas SO se ela for a unica conta deste banco.

    A `medida` antiga nao tem dono: nao da para saber de quem e cada linha. Num
    banco com mais de uma conta, entregar tudo a conta local seria mover o
    inventario alheio — nomes de projeto, caminhos, contagem de alerta — para
    uma conta que `/entrar/local` abre SEM SENHA, apagando o rastro no
    `DROP TABLE`. Foi o que aconteceu, e o revisor da correcao rodou a prova.

    Com mais de uma conta, `DONO_LOCAL`: ninguem le, e o coletor local repoe a
    medicao em 60 s. Fechar por padrao custa um minuto de tela vazia.

    Le direto em vez de chamar `conta_local()`: aqui NAO se cria conta nenhuma —
    a migracao roda em toda conexao, inclusive no servidor.
    """
    try:
        contas = con.execute("SELECT COUNT(*) FROM usuario").fetchone()[0]
        if contas != 1:
            return DONO_LOCAL
        l = con.execute("SELECT id FROM usuario WHERE email = ?"
                        " AND desativado_em IS NULL", (CONTA_LOCAL,)).fetchone()
    except sqlite3.Error:
        return DONO_LOCAL              # banco anterior a `usuario`: nao ha dono
    return l["id"] if l else DONO_LOCAL


def _migrar_medida(con: sqlite3.Connection) -> None:
    """`medida` ganhou dono (etapa 11, correcao). Mesmo procedimento da
    `pendencia_estado`: o SQLite nao troca chave primaria, entao a tabela e
    reconstruida, e o que ja estava la vira do DONO_LOCAL — que e exatamente o
    que era, a medicao desta maquina.
    """
    forma = list(con.execute("PRAGMA table_info(medida)"))
    if not forma:
        return                                   # banco novo: o ESQUEMA ja faz certo
    chave = [l[1] for l in sorted((l for l in forma if l[5]), key=lambda l: l[5])]
    if chave == ["usuario_id", "projeto", "camada"]:
        return
    con.execute("PRAGMA foreign_keys=OFF")
    try:
        con.execute("BEGIN IMMEDIATE")
        # RELIDO DENTRO DA TRANSACAO: a leitura la em cima aconteceu antes do
        # lock, e dois processos subindo juntos leriam os dois "preciso migrar".
        # E a licao ja paga na `pendencia_estado`.
        forma = list(con.execute("PRAGMA table_info(medida)"))
        chave = [l[1] for l in sorted((l for l in forma if l[5]),
                                      key=lambda l: l[5])]
        if chave == ["usuario_id", "projeto", "camada"]:
            con.rollback()
            return
        tinha_dono = "usuario_id" in {l[1] for l in forma}
        # PARA QUEM VAI LER, e nao para o zero. Em ambiente local quem abre o
        # painel e a conta `CONTA_LOCAL`; entregar a ela e o unico jeito de a
        # medicao antiga continuar aparecendo. No servidor essa conta nao
        # existe, e ai o destino e o zero mesmo.
        destino = ("usuario_id" if tinha_dono
                   else str(_dono_da_medida_antiga(con)))
        con.execute("DROP TABLE IF EXISTS medida_nova")
        con.execute("""CREATE TABLE medida_nova (
                usuario_id INTEGER NOT NULL DEFAULT 0,
                projeto    TEXT NOT NULL,
                camada     TEXT NOT NULL,
                medido_em  TEXT NOT NULL,
                dados      TEXT NOT NULL,
                PRIMARY KEY (usuario_id, projeto, camada))""")
        con.execute("INSERT INTO medida_nova"
                    " (usuario_id, projeto, camada, medido_em, dados)"
                    " SELECT %s, projeto, camada, medido_em, dados FROM medida"
                    % destino)
        con.execute("DROP TABLE medida")
        con.execute("ALTER TABLE medida_nova RENAME TO medida")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        _religar_fk(con)


# A `credencial` precisa existir ANTES da reconstrucao da `usuario` la embaixo,
# e o ESQUEMA so roda DEPOIS de toda a migracao. Entao o texto dela mora aqui,
# numa constante, e o ESQUEMA repete a mesma forma — duas copias do mesmo
# CREATE, de proposito: a do ESQUEMA e a documentacao do banco de hoje, esta e
# a ferramenta da migracao. Se uma mudar, a outra muda junto.
_CREATE_CREDENCIAL = """CREATE TABLE IF NOT EXISTS credencial (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    tipo          TEXT NOT NULL CHECK (tipo IN ('github','senha','totp','passkey')),
    identificador TEXT NOT NULL,
    segredo_hash  TEXT,
    criado_em     TEXT NOT NULL,
    usado_em      TEXT,
    revogada_em   TEXT,
    CHECK (tipo NOT IN ('senha','totp') OR identificador = CAST(usuario_id AS TEXT)),
    CHECK (tipo <> 'github' OR identificador GLOB '[0-9]*'),
    UNIQUE (tipo, identificador))"""


def _migrar_credencial(con: sqlite3.Connection) -> None:
    """Tira senha e TOTP de dentro da `usuario` (etapa 9).

    A condicao de "ja rodou" e a ausencia da coluna `senha_hash`. Cinco tabelas
    apontam para a `usuario`, entao a reconstrucao termina com um
    `foreign_key_check` ANTES do commit: se alguma filha ficaria orfa, e agora
    que se descobre, com rollback ainda possivel.
    """
    forma = list(con.execute("PRAGMA table_info(usuario)"))
    if not forma:
        return                                # banco novo: o ESQUEMA ja faz certo
    colunas = {l[1] for l in forma}
    if "senha_hash" not in colunas:
        return                                # ja migrado
    tinha_totp = "totp_segredo" in colunas
    # Reconstrucao com FK desligada: e o procedimento que o proprio SQLite
    # recomenda. O pragma e por conexao e nao vaza para os outros processos.
    con.execute("PRAGMA foreign_keys=OFF")
    try:
        # TUDO OU NADA. `executescript` daria COMMIT implicito entre os passos e
        # rodaria cada comando como uma transacao solta: uma queda entre o DROP
        # e o RENAME apagaria a `usuario` e deixaria as cinco filhas apontando
        # para uma tabela que nao existe mais, sem excecao nenhuma e sem nunca
        # tentar de novo.
        con.execute("BEGIN IMMEDIATE")
        # DE NOVO, DENTRO DA TRANSACAO — ver o comentario gemeo em
        # `_migrar_pendencia_estado`. Aqui o processo perdedor nem chegava a
        # estragar dado: ele estourava com `no such column: senha_hash` dentro
        # de `conectar()`, e como `conectar()` roda em toda requisicao, o
        # processo simplesmente nao subia.
        if "senha_hash" not in {l[1] for l in
                                con.execute("PRAGMA table_info(usuario)")}:
            con.rollback()
            return
        # A sequencia do AUTOINCREMENT nao sobrevive ao DROP: ela voltaria para
        # o maior id copiado, e um id ja usado poderia ser reemitido. Como
        # `pendencia_estado` e `pendencia_arquivada` de proposito NAO tem chave
        # estrangeira para `usuario`, as linhas de uma conta apagada seriam
        # herdadas em silencio pela conta nova que recebesse o id.
        seq = con.execute("SELECT seq FROM sqlite_sequence WHERE name='usuario'"
                          ).fetchone()
        seq = seq[0] if seq else None
        orfaos_antes = _orfaos(con)
        con.execute("DROP TABLE IF EXISTS usuario_nova")
        con.execute("""CREATE TABLE usuario_nova (
                id            INTEGER PRIMARY KEY AUTOINCREMENT CHECK (id <> 0),
                email         TEXT NOT NULL UNIQUE CHECK (length(trim(email)) > 0),
                nome          TEXT NOT NULL DEFAULT '',
                criado_em     TEXT NOT NULL,
                desativado_em TEXT)""")
        con.execute("INSERT INTO usuario_nova"
                    " (id, email, nome, criado_em, desativado_em)"
                    " SELECT id, email, nome, criado_em, desativado_em FROM usuario")
        con.execute(_CREATE_CREDENCIAL)
        # `INSERT` seco, e nao `OR IGNORE`. A justificativa que estava aqui
        # ("se ela ja rodou pela metade") descrevia um cenario impossivel: esta
        # tudo numa transacao so, entao nao existe meia-migracao. O que o
        # `OR IGNORE` fazia de fato era engolir conflito genuino — um hub.db com
        # linha `senha` antiga na `credencial` e `usuario.senha_hash` mais nova
        # teria a senha revertida em silencio.
        con.execute("INSERT INTO credencial"
                    " (usuario_id, tipo, identificador, segredo_hash, criado_em)"
                    " SELECT id, 'senha', CAST(id AS TEXT), senha_hash, criado_em"
                    "   FROM usuario"
                    "  WHERE senha_hash IS NOT NULL AND senha_hash <> ''")
        if tinha_totp:
            con.execute("INSERT INTO credencial"
                        " (usuario_id, tipo, identificador, segredo_hash,"
                        "  criado_em, usado_em)"
                        " SELECT id, 'totp', CAST(id AS TEXT), totp_segredo,"
                        "        criado_em, totp_confirmado_em"
                        "   FROM usuario WHERE totp_segredo IS NOT NULL")
        con.execute("DROP TABLE usuario")
        con.execute("ALTER TABLE usuario_nova RENAME TO usuario")
        if seq is not None:
            con.execute("UPDATE sqlite_sequence SET seq = ? WHERE name='usuario'",
                        (seq,))
        # A PERGUNTA CERTA E "eu PIOREI alguma coisa?", nao "esta tudo limpo?".
        #
        # A primeira versao desta linha era `PRAGMA foreign_key_check` sem
        # argumento, comparado contra zero. Isso varre o banco INTEIRO e aborta
        # por orfao que ja estava la — e como isso acontece dentro de
        # `conectar()`, que roda em toda requisicao, o banco ficaria inacessivel
        # PARA SEMPRE, sem caminho de volta no codigo. Orfao pre-existente e
        # plausivel: qualquer escrita por conexao sem `foreign_keys=ON` deixa um.
        #
        # Comparando antes e depois, um orfao herdado passa (e continua sendo
        # problema de outra pessoa, nao desta migracao) e um orfao CRIADO aqui
        # aborta, que e exatamente o que precisa acontecer.
        piorou = _orfaos(con) - orfaos_antes
        if piorou > 0:
            raise sqlite3.IntegrityError(
                "a migracao criaria %d referencia orfa; nada foi gravado" % piorou)
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        _religar_fk(con)


# --------------------------------------------------------------------------
# O cofre: o que transforma segredo em coisa que pode morar numa tabela.
# --------------------------------------------------------------------------

MIN_COFRE = 32          # caracteres. Abaixo disso da para quebrar offline.
_CHAVE_EM_MEMORIA = None


def _derivar(bruto: bytes) -> bytes:
    """scrypt, nao SHA-256.

    Um SHA-256 puro custa nada por palpite, e o selo do proprio blob confirma o
    acerto: uma frase digitada por gente cai em bilhoes de tentativas por
    segundo, offline, a partir de uma copia do hub.db. O scrypt cobra memoria
    de quem chuta. O sal e fixo de proposito — ele separa este uso de qualquer
    outro, e nao ha nada onde guardar um sal por chave.
    """
    return hashlib.scrypt(bruto, salt=b"dervs/cofre/v1", n=16384, r=8, p=1, dklen=32)


def caminho_do_cofre() -> Path:
    """Onde mora a chave. `DERVS_COFRE_ARQUIVO` tira ela da pasta servida.

    Na etapa 16 isto importa de verdade: um `root /app` no nginx serviria a
    chave mestra por HTTP. Hoje `servir.py` so entrega quatro arquivos por lista
    fechada, entao nao vaza — mas o padrao certo e a chave nascer fora.
    """
    fora = os.environ.get("DERVS_COFRE_ARQUIVO")
    return Path(fora) if fora else AQUI / "cofre.chave"


def chave_do_cofre() -> bytes:
    """32 bytes derivados de `DERVS_COFRE` ou de um arquivo local.

    RECUSA CRIAR A CHAVE SOZINHA fora do ambiente local. Fabricar outra chave
    porque a variavel foi esquecida no servidor e falhar por cima: todo segredo
    de segundo fator ja guardado viraria "adulterado", e todo codigo de
    pareamento pararia de casar, sem uma linha de aviso. Melhor nao subir.
    """
    global _CHAVE_EM_MEMORIA
    if _CHAVE_EM_MEMORIA is not None:
        return _CHAVE_EM_MEMORIA
    bruto = (os.environ.get("DERVS_COFRE") or "").strip()
    if bruto:
        if len(bruto) < MIN_COFRE:
            raise ValueError(
                "DERVS_COFRE tem %d caracteres e precisa de %d. Gere um valor "
                "aleatorio de verdade:\n"
                '  python -c "import secrets;print(secrets.token_urlsafe(32))"'
                % (len(bruto), MIN_COFRE))
        _CHAVE_EM_MEMORIA = _derivar(bruto.encode("utf-8"))
        return _CHAVE_EM_MEMORIA
    arquivo = caminho_do_cofre()
    if not arquivo.exists():
        if os.environ.get("DERVS_AMBIENTE") != "local":
            raise RuntimeError(
                "nao ha chave de cofre e este nao e o ambiente local, entao eu "
                "nao vou inventar uma.\n"
                "  No servidor: defina DERVS_COFRE (>= %d caracteres).\n"
                "  Nesta maquina: defina DERVS_AMBIENTE=local e eu crio %s."
                % (MIN_COFRE, arquivo))
        # O_EXCL, nao `exists()` + `write`: o coletor e o servidor abrem o banco
        # ao mesmo tempo, e os dois veriam "nao existe". O ultimo a escrever
        # venceria, e o que o primeiro cifrasse no intervalo era perdido.
        try:
            fd = os.open(arquivo, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(secrets.token_bytes(32))
        except FileExistsError:
            pass                         # outro processo ganhou; a dele serve
    _CHAVE_EM_MEMORIA = _derivar(arquivo.read_bytes())
    return _CHAVE_EM_MEMORIA


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _fluxo(chave: bytes, nonce: bytes, quantos: int) -> bytes:
    """Sequencia pseudoaleatoria por HMAC, do tamanho pedido (modo contador)."""
    saida = b""
    contador = 0
    while len(saida) < quantos:
        saida += hmac.new(chave, nonce + contador.to_bytes(4, "big"),
                          hashlib.sha256).digest()
        contador += 1
    return saida[:quantos]


def cifrar(claro: str, contexto: str = "") -> str:
    """Devolve 'v1$nonce$cifra$selo'. Sem biblioteca externa, por decisao do projeto.

    Duas chaves derivadas da mesma raiz — uma cifra, outra sela. Cifrar sem
    selar deixaria o texto adulteravel sem ninguem perceber.

    `contexto` entra no selo e AMARRA o blob ao lugar dele. Sem isso, copiar o
    `totp_segredo` da linha de um usuario para a de outro decifra normalmente —
    exige escrita no banco para explorar, mas custa uma linha para fechar.
    """
    raiz = chave_do_cofre()
    k_cifra = hmac.new(raiz, b"cifra", hashlib.sha256).digest()
    k_selo = hmac.new(raiz, b"selo", hashlib.sha256).digest()
    nonce = secrets.token_bytes(16)
    dados = claro.encode("utf-8")
    cifra = bytes(a ^ b for a, b in zip(dados, _fluxo(k_cifra, nonce, len(dados))))
    selo = hmac.new(k_selo, nonce + cifra + (contexto or "").encode("utf-8"),
                    hashlib.sha256).digest()
    return "v1$%s$%s$%s" % (_b64(nonce), _b64(cifra), _b64(selo))


def decifrar(blob: str, contexto: str = "") -> str:
    """Recusa o que foi adulterado ou movido de lugar. Nunca devolve lixo."""
    partes = (blob or "").split("$")
    if len(partes) != 4:
        raise ValueError("texto cifrado ilegivel: esperava 4 partes, veio %d"
                         % len(partes))
    versao, nonce_b, cifra_b, selo_b = partes
    if versao != "v1":
        raise ValueError("versao de cifra desconhecida: %r" % versao)
    try:
        nonce = base64.b64decode(nonce_b, validate=True)
        cifra = base64.b64decode(cifra_b, validate=True)
        selo = base64.b64decode(selo_b, validate=True)
    except Exception as e:
        raise ValueError("texto cifrado ilegivel") from e
    raiz = chave_do_cofre()
    k_selo = hmac.new(raiz, b"selo", hashlib.sha256).digest()
    esperado = hmac.new(k_selo, nonce + cifra + (contexto or "").encode("utf-8"),
                        hashlib.sha256).digest()
    if not hmac.compare_digest(selo, esperado):
        raise ValueError("texto cifrado adulterado, movido de lugar, ou chave errada")
    k_cifra = hmac.new(raiz, b"cifra", hashlib.sha256).digest()
    return bytes(a ^ b for a, b in
                 zip(cifra, _fluxo(k_cifra, nonce, len(cifra)))).decode("utf-8")


def prazo(segundos: int) -> str:
    """O UNICO jeito certo de produzir `expira_em`.

    O banco compara prazo por TEXTO. Quem montar a string a mao e escrever "Z"
    em vez de "+00:00" grava uma sessao que sobrevive ao proprio vencimento —
    o mesmo instante, e o sufixo Z sempre "vence" na comparacao.
    """
    from datetime import timedelta
    return (datetime.now(timezone.utc) + timedelta(seconds=segundos)
            ).isoformat(timespec="seconds")


def novo_codigo(digitos: int = 6) -> str:
    """Codigo de pareamento. Aleatorio de verdade, com zero a esquerda preservado."""
    return str(secrets.randbelow(10 ** digitos)).zfill(digitos)


def hash_senha(senha: str) -> str:
    """scrypt com sal proprio. Sem sal, duas contas com a mesma senha se denunciam."""
    sal = secrets.token_bytes(16)
    bruto = hashlib.scrypt(senha.encode("utf-8"), salt=sal, n=16384, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$%s$%s" % (_b64(sal), _b64(bruto))


def conferir_senha(senha: str, guardado: str) -> bool:
    """Falso para senha errada E para registro torto. Nunca levanta erro."""
    try:
        marca, n, r, p, sal_b, esperado_b = (guardado or "").split("$")
        if marca != "scrypt":
            return False
        bruto = hashlib.scrypt(senha.encode("utf-8"), salt=base64.b64decode(sal_b),
                               n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(bruto, base64.b64decode(esperado_b))
    except Exception:
        return False


def novo_token() -> str:
    """Token de sessao ou de agente: aleatorio de verdade, url-seguro."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 puro: o token ja tem entropia de sobra, nao precisa de hash lento."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def hash_codigo(codigo: str) -> str:
    """HMAC, nao hash puro: seis digitos sao chutaveis a partir de um banco vazado."""
    return hmac.new(chave_do_cofre(), (codigo or "").encode("utf-8"),
                    hashlib.sha256).hexdigest()


def gravar(projeto: str, camada: str, dados: dict, con=None, *,
           usuario_id: int) -> None:
    """`usuario_id` E OBRIGATORIO, e de proposito nao tem padrao.

    Um padrao `DONO_LOCAL` aqui seria a mesma armadilha que `silenciadas` foi na
    etapa 8: quem esquecesse de passar escreveria no balcao do dono local sem
    erro nenhum. Sem padrao, esquecer nao roda.

    SO COMMITA QUEM ABRIU A CONEXAO. Commitar tambem com um `con` vindo de fora
    quebrava a transacao de quem chamou: `receber_relatorio` prometia "numa
    transacao so" e na pratica fazia um commit por projeto.
    """
    fechar = con is None
    con = con or conectar()
    try:
        con.execute(
            "INSERT INTO medida (usuario_id, projeto, camada, medido_em, dados)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(usuario_id, projeto, camada) DO UPDATE SET"
            " medido_em=excluded.medido_em, dados=excluded.dados",
            (usuario_id, projeto, camada, agora(),
             json.dumps(dados, ensure_ascii=False)),
        )
        if fechar:
            con.commit()
    finally:
        if fechar:
            con.close()


def ler_tudo(con=None, *, usuario_id: int) -> dict:
    """{projeto: {camada: {"medido_em": iso, "dados": {...}}}} DAQUELA CONTA.

    Sem o `WHERE` esta funcao era o vazamento: devolvia a tabela inteira, e
    `_estado` mandava tudo para qualquer sessao. `usuario_id` sem padrao pelo
    mesmo motivo de `gravar`.
    """
    fechar = con is None
    con = con or conectar()
    try:
        fora: dict = {}
        for l in con.execute("SELECT projeto, camada, medido_em, dados FROM medida"
                             " WHERE usuario_id = ?", (usuario_id,)):
            fora.setdefault(l["projeto"], {})[l["camada"]] = {
                "medido_em": l["medido_em"],
                "dados": json.loads(l["dados"]),
            }
        return fora
    finally:
        if fechar:
            con.close()


def montar_estado(con=None, *, usuario_id: int) -> dict:
    """As tres camadas remontadas no formato que o motor de regras consome.

    Cada camada carrega o proprio "medido_em". E o que permite a tela dizer
    "medido ha 40 s" no numero do git e "ha 12 min" no numero do GitHub, em vez
    de um carimbo unico que mente sobre metade dos valores.
    """
    fechar = con is None
    con = con or conectar()
    try:
        tudo = ler_tudo(con, usuario_id=usuario_id)
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


def silenciadas(con=None, usuario_id: int = DONO_LOCAL, agora_iso: str = "") -> dict:
    """O que este usuario mandou esconder e ainda esta no prazo.

    `con` continua sendo o primeiro parametro por compatibilidade: `servir.py`
    chama `silenciadas(con)` posicionalmente, e mudar a ordem quebraria a
    unica rota de escrita do painel sem nenhum teste reclamar.
    """
    fechar = con is None
    con = con or conectar()
    try:
        corte = agora_iso or agora()
        return {l["id"]: l["silenciada_ate"] for l in
                con.execute("SELECT id, silenciada_ate FROM pendencia_estado "
                            "WHERE usuario_id = ? AND silenciada_ate IS NOT NULL "
                            "AND silenciada_ate > ?", (usuario_id, corte))}
    finally:
        if fechar:
            con.close()


def silenciar(pid: str, ate_iso: str, con=None, usuario_id: int = DONO_LOCAL) -> None:
    fechar = con is None
    con = con or conectar()
    try:
        con.execute(
            "INSERT INTO pendencia_estado (id, usuario_id, silenciada_ate, anotado_em)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(id, usuario_id) DO UPDATE SET"
            " silenciada_ate=excluded.silenciada_ate, anotado_em=excluded.anotado_em",
            (pid, usuario_id, ate_iso, agora()))
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
        # Mais o que foi gasto FORA da fila, na mesma janela. Sem esta segunda
        # soma, o botao "Resolver" gastava sem o teto do dia jamais ver.
        fora = con.execute(
            "SELECT COALESCE(SUM(custo_usd), 0.0) AS total FROM gasto"
            " WHERE quando >= ? AND quando < ?",
            (inicio_iso, fim_iso)).fetchone()
        return float(linha["total"] or 0.0) + float(fora["total"] or 0.0)
    finally:
        if fechar:
            con.close()


def registrar_gasto(custo_usd, origem: str = "", quando: str = "", con=None):
    """Anota um gasto que nao esta na fila. Zero nao vira linha.

    Quem passa pela fila NAO usa isto: la o custo mora em `fila.custo_usd`, e
    contar duas vezes seria pior do que nao contar.
    """
    try:
        valor = float(custo_usd or 0.0)
    except (TypeError, ValueError):
        return False
    if valor <= 0:
        return False
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("INSERT INTO gasto (quando, origem, custo_usd) VALUES (?,?,?)",
                    (quando or agora(), origem or "", valor))
        con.commit()
        return True
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


# --------------------------------------------------------------------------
# Etapa 8: conta, sessao, maquina, pareamento, projeto e arquivamento.
#
# Sao acessos finos de proposito. A REGRA de quem pode o que e da etapa 9;
# aqui mora so o que a tabela precisa para nao nascer torta.
# --------------------------------------------------------------------------

def _normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def conta_local(con=None) -> int:
    """O id da conta desta maquina, criando-a se ainda nao existir.

    FORA DO AMBIENTE LOCAL DEVOLVE `DONO_LOCAL` e nao cria nada: a conta e de
    teste, e o servidor recusa conta de teste por verificacao de ambiente. La
    ninguem roda coletor — quem escreve na `medida` e o agente, por HTTP, com a
    conta de quem pareou a maquina.
    """
    if (os.environ.get("DERVS_AMBIENTE") or "").strip().lower() != "local":
        return DONO_LOCAL
    fechar = con is None
    con = con or conectar()
    try:
        # PROCURA-SE A LINHA, NAO A CONTA ATIVA. Filtrar `desativado_em IS NULL`
        # aqui devolvia nada para uma conta local desativada, e o `criar_usuario`
        # abaixo estourava no UNIQUE do e-mail — derrubando `servir.main()` e a
        # coleta. `_entrar_local` ja trata esse caso; esta funcao esqueceu.
        l = con.execute("SELECT id, desativado_em FROM usuario WHERE email = ?",
                        (CONTA_LOCAL,)).fetchone()
        if l is not None:
            # Desativada de proposito: nao se reativa por aqui, e nao ha dono.
            return DONO_LOCAL if l["desativado_em"] else l["id"]
        uid = criar_usuario(CONTA_LOCAL, nome="Dono (ambiente local)", con=con)
        if fechar:
            con.commit()
        return uid
    finally:
        if fechar:
            con.close()


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


# As colunas que podem sair daqui. Nenhum segredo mora mais nesta tabela — eles
# foram para a `credencial` na etapa 9 —, mas a lista continua explicita porque
# um `SELECT *` volta a vazar no dia em que alguem acrescentar uma coluna.
COLUNAS_USUARIO = ("id", "email", "nome", "criado_em", "desativado_em")


def usuario_por_email(email: str, con=None):
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute(
            "SELECT %s FROM usuario WHERE email = ? AND desativado_em IS NULL"
            % ", ".join(COLUNAS_USUARIO), (_normalizar_email(email),)).fetchone()
        return dict(l) if l else None
    finally:
        if fechar:
            con.close()


def credencial_por_email(email: str, con=None):
    """A PORTA DE EMERGENCIA, e so ela. Devolve (id, senha_hash) ou None.

    Desde a etapa 9 o caminho normal e o GitHub, e conta criada por convite nao
    tem credencial de senha nenhuma — entao None aqui e o esperado, nao um erro.
    """
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute("SELECT u.id AS id, c.segredo_hash AS senha_hash"
                        "  FROM usuario u"
                        "  JOIN credencial c ON c.usuario_id = u.id"
                        " WHERE u.email = ? AND u.desativado_em IS NULL"
                        "   AND c.tipo = 'senha' AND c.revogada_em IS NULL",
                        (_normalizar_email(email),)).fetchone()
        return (l["id"], l["senha_hash"]) if l else None
    finally:
        if fechar:
            con.close()


def ligar_github(usuario_id: int, github_id: str, con=None) -> None:
    """Amarra uma conta a um id NUMERICO do GitHub. Nunca ao login em texto.

    Login do GitHub pode ser trocado, e o nome antigo fica livre para outra
    pessoa registrar. Casar por texto e entregar a conta a quem pegar o nome
    abandonado.
    """
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
    """Conta ATIVA com credencial ATIVA, ou None. Nao diz qual das duas faltou.

    Motivo diferente por causa diferente e o que transforma uma tela de login
    numa lista de quem existe.
    """
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute(
            "SELECT %s FROM usuario u JOIN credencial c ON c.usuario_id = u.id"
            " WHERE c.tipo = 'github' AND c.identificador = ?"
            "   AND c.revogada_em IS NULL AND u.desativado_em IS NULL"
            % ", ".join("u.%s AS %s" % (c, c) for c in COLUNAS_USUARIO),
            (str(github_id).strip(),)).fetchone()
        return dict(l) if l else None
    finally:
        if fechar:
            con.close()


def guardar_totp(usuario_id: int, segredo: str, con=None) -> None:
    """Guarda CIFRADO e deixa o `usado_em` em branco: guardar nao e conferir."""
    fechar = con is None
    con = con or conectar()
    try:
        # Uma credencial de TOTP por pessoa: o UNIQUE (tipo, identificador) ja
        # garante isso, e o REPLACE e o que deixa trocar o autenticador sem
        # precisar apagar a anterior a mao.
        con.execute("INSERT OR REPLACE INTO credencial"
                    " (usuario_id, tipo, identificador, segredo_hash, criado_em)"
                    " VALUES (?,'totp',?,?,?)",
                    (usuario_id, str(usuario_id),
                     cifrar(segredo, contexto="totp:%d" % usuario_id), agora()))
        con.commit()
    finally:
        if fechar:
            con.close()


def ler_totp(usuario_id: int, con=None):
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute("SELECT segredo_hash FROM credencial"
                        " WHERE tipo = 'totp' AND identificador = ?"
                        "   AND revogada_em IS NULL",
                        (str(usuario_id),)).fetchone()
        return decifrar(l[0], contexto="totp:%d" % usuario_id) if l and l[0] else None
    finally:
        if fechar:
            con.close()


def confirmar_totp(usuario_id: int, con=None) -> None:
    """`usado_em` faz o papel do antigo `totp_confirmado_em`."""
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("UPDATE credencial SET usado_em = ?"
                    " WHERE tipo = 'totp' AND identificador = ?"
                    "   AND revogada_em IS NULL",
                    (agora(), str(usuario_id)))
        con.commit()
    finally:
        if fechar:
            con.close()


def abrir_sessao(usuario_id: int, cookie: str, expira_em: str, con=None) -> None:
    """Grava o HASH do cookie. Vazar o banco nao pode equivaler a vazar as sessoes."""
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("INSERT INTO sessao (id, usuario_id, criado_em, expira_em)"
                    " VALUES (?,?,?,?)",
                    (hash_token(cookie), usuario_id, agora(), expira_em))
        con.commit()
    finally:
        if fechar:
            con.close()


def sessao_valida(cookie: str, agora_iso: str = "", con=None):
    """Sessao viva DE CONTA VIVA.

    O `JOIN` nao e enfeite: sem ele, desativar uma conta nao derruba quem ja
    esta dentro — o cookie no navegador continua valendo ate o prazo, que a
    etapa 9 vai medir em horas. Fechar a conta tem de fechar a porta.
    """
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute(
            "SELECT s.* FROM sessao s JOIN usuario u ON u.id = s.usuario_id"
            " WHERE s.id = ? AND s.encerrada_em IS NULL AND s.expira_em > ?"
            " AND u.desativado_em IS NULL",
            (hash_token(cookie), agora_iso or agora())).fetchone()
        return dict(l) if l else None
    finally:
        if fechar:
            con.close()


def confirmar_segundo_fator(cookie: str, cookie_novo: str = "", con=None) -> str:
    """Sobe a sessao de "so senha" para "senha + segundo fator".

    TROCA O COOKIE ao subir de nivel, e devolve o novo. Manter o mesmo
    identificador de antes e depois de autenticar e o que faz fixacao de sessao
    funcionar: quem plantou o cookie antes do login continua dentro depois dele.
    Passar `cookie_novo` vazio mantem o cookie — use so em teste.
    """
    fechar = con is None
    con = con or conectar()
    try:
        if cookie_novo:
            con.execute("UPDATE sessao SET id = ?, segundo_fator_em = ? WHERE id = ?",
                        (hash_token(cookie_novo), agora(), hash_token(cookie)))
        else:
            con.execute("UPDATE sessao SET segundo_fator_em = ? WHERE id = ?",
                        (agora(), hash_token(cookie)))
        con.commit()
        return cookie_novo or cookie
    finally:
        if fechar:
            con.close()


def encerrar_sessao(cookie: str, con=None) -> None:
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("UPDATE sessao SET encerrada_em = ? WHERE id = ?",
                    (agora(), hash_token(cookie)))
        con.commit()
    finally:
        if fechar:
            con.close()


def abrir_pareamento(usuario_id: int, codigo: str, expira_em: str, con=None) -> None:
    """INSERT puro, NUNCA `INSERT OR REPLACE`.

    Com `REPLACE`, dois usuarios sorteando o mesmo codigo de seis digitos ao
    mesmo tempo faziam a linha do primeiro ser apagada em silencio — e a maquina
    dele nascia dentro da conta do segundo, com os projetos e os alertas junto.
    Colisao agora levanta `IntegrityError`: quem chamou sorteia outro codigo.
    Barulho onde havia silencio.
    """
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("INSERT INTO pareamento"
                    " (codigo_hash, usuario_id, criado_em, expira_em) VALUES (?,?,?,?)",
                    (hash_codigo(codigo), usuario_id, agora(), expira_em))
        con.commit()
    finally:
        if fechar:
            con.close()


def usar_pareamento(codigo: str, nome_maquina: str = "", agora_iso: str = "", con=None):
    """Casa uma maquina com a conta e devolve o token do agente — UMA vez so.

    O token e devolvido aqui e em nenhum outro lugar: a tabela guarda so o hash.

    O PROPRIO UPDATE E A GUARDA. Um `SELECT` que decide e um `INSERT` depois
    correm fora da mesma transacao: dois agentes resgatando o codigo no mesmo
    instante viam os dois `usado_em IS NULL`, e um codigo de uso unico virava
    dois acessos permanentes a conta. Aqui quem nao levar `rowcount == 1` perdeu.

    NAO HA CONTADOR GLOBAL DE CHUTE. Um codigo solto nao diz de quem ele seria,
    entao contar o chute errado contra todos os pareamentos abertos deixava
    qualquer um matar o pareamento de todo mundo com cinco requisicoes. O teto
    de forca bruta e por ORIGEM e mora na rota, na etapa 11 — junto com o prazo
    curto, e o que segura seis digitos.
    """
    fechar = con is None
    con = con or conectar()
    corte = agora_iso or agora()
    try:
        cur = con.execute(
            # NAO HA `AND tentativas < ?` AQUI, e nao e esquecimento: nada
            # neste repositorio incrementa `pareamento.tentativas`, entao a
            # condicao era sempre verdadeira e fingia existir um teto dentro do
            # banco. Quem lesse este SQL podia remover o teto da rota — o unico
            # que existe de verdade — achando que havia dois. Achado da revisao
            # de seguranca da etapa 11.
            "UPDATE pareamento SET usado_em = ? WHERE codigo_hash = ?"
            " AND usado_em IS NULL AND expira_em > ?",
            (corte, hash_codigo(codigo), corte))
        if cur.rowcount != 1:
            con.rollback()
            return None
        dono = con.execute("SELECT usuario_id FROM pareamento WHERE codigo_hash = ?",
                           (hash_codigo(codigo),)).fetchone()["usuario_id"]
        token = novo_token()
        maq = con.execute(
            "INSERT INTO maquina (usuario_id, nome, token_hash, criado_em, visto_em)"
            " VALUES (?,?,?,?,?)",
            (dono, nome_maquina or "", hash_token(token), agora(), corte))
        con.execute("UPDATE pareamento SET maquina_id = ? WHERE codigo_hash = ?",
                    (maq.lastrowid, hash_codigo(codigo)))
        con.commit()
        return token
    finally:
        if fechar:
            con.close()


def maquina_por_token(token: str, con=None):
    """Maquina viva DE CONTA VIVA — mesmo motivo do `JOIN` em `sessao_valida`."""
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute(
            "SELECT m.* FROM maquina m JOIN usuario u ON u.id = m.usuario_id"
            " WHERE m.token_hash = ? AND m.revogada_em IS NULL"
            " AND u.desativado_em IS NULL", (hash_token(token),)).fetchone()
        return dict(l) if l else None
    finally:
        if fechar:
            con.close()


def revogar_maquina(maquina_id: int, usuario_id: int, con=None) -> bool:
    """Tira uma maquina de circulacao. False se ela nao e desta conta.

    `usuario_id` na clausula NAO e redundante com a checagem da rota, e a
    assinatura o exige em vez de aceitar como opcional: e o IDOR classico de
    rota de remocao, onde o id da linha vem do navegador e quem manda um numero
    vizinho revoga a maquina do outro. Opcional com padrao permissivo seria uma
    defesa que some no dia em que alguem esquecer de passar o argumento —
    exatamente o desenho de `revogar_chave_de_acesso`, e pelo mesmo motivo.
    """
    fechar = con is None
    con = con or conectar()
    try:
        cur = con.execute(
            "UPDATE maquina SET revogada_em = ? WHERE id = ? AND usuario_id = ?"
            " AND revogada_em IS NULL", (agora(), maquina_id, usuario_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        if fechar:
            con.close()


def maquinas_do_usuario(usuario_id: int, con=None) -> list:
    """As maquinas vivas da conta, com a contagem de projetos de cada uma.

    NAO DEVOLVE `token_hash`. A lista vai para a tela; hash de token na tela e
    hash de token no cache do navegador, no log do proxy e na captura de tela
    que o dono manda para pedir ajuda.
    """
    fechar = con is None
    con = con or conectar()
    try:
        return [dict(l) for l in con.execute(
            "SELECT m.id, m.nome, m.criado_em, m.visto_em,"
            "       (SELECT COUNT(*) FROM projeto_conectado p"
            "         WHERE p.maquina_id = m.id AND p.arquivado_em IS NULL)"
            "       AS projetos"
            "  FROM maquina m"
            " WHERE m.usuario_id = ? AND m.revogada_em IS NULL"
            " ORDER BY m.criado_em", (usuario_id,))]
    finally:
        if fechar:
            con.close()


def receber_relatorio(maquina_id: int, projetos: list, infra=None,
                      avisos=None, con=None) -> dict:
    """O relatorio de uma maquina, gravado numa transacao so.

    O ENVIO DE DADO E O SINAL DE VIDA, e por isso `visto_em` e carimbado AQUI,
    depois de a medicao entrar — nunca por uma rota de "estou vivo" separada.
    Um sinal proprio permite a maquina parecer viva com a medicao parada, que e
    a pior mentira possivel neste produto: o painel fica verde justamente
    quando parou de olhar.

    PROJETO QUE SUMIU E ARQUIVADO, MAS LISTA VAZIA NAO ARQUIVA NADA. Coleta que
    falhou inteira manda `[]`, e tratar isso como "os projetos acabaram" apagaria
    da tela repositorios que continuam existindo — a mesma familia de defeito de
    confundir vazio com ausencia de medicao.
    """
    fechar = con is None
    con = con or conectar()
    try:
        # O DONO VEM DA MAQUINA, NAO DE QUEM CHAMOU. A rota ja achou a maquina
        # pelo token; reler o dono aqui deixa uma fonte de verdade so, e nao ha
        # parametro `usuario_id` para um chamador futuro preencher errado.
        dono = con.execute("SELECT usuario_id FROM maquina WHERE id = ?",
                           (maquina_id,)).fetchone()
        if dono is None:
            raise ValueError("maquina %r nao existe" % (maquina_id,))
        usuario_id = dono["usuario_id"]
        # UMA transacao, agora de verdade. Antes o docstring prometia e o codigo
        # nao cumpria: `gravar`, `ver_projeto` e `arquivar_projeto` commitavam
        # cada um, entao um relatorio de 300 projetos eram 600 commits e 300
        # estados intermediarios visiveis para quem estivesse com o painel
        # aberto — o painel mostrava "150 projetos" com cara de numero certo.
        # IMMEDIATE, e nao a transacao implicita do modulo, porque a implicita
        # nasce DEFERRED e a promocao para escrita pode voltar BUSY sem esperar
        # o `busy_timeout`.
        propria = not con.in_transaction
        if propria:
            con.execute("BEGIN IMMEDIATE")
        # TETO ACUMULADO, e nao so por relatorio: sem ele um token vazado
        # gravava nomes aleatorios novos a cada envio e o disco crescia sem fim.
        # Nome que JA existe continua atualizando normalmente — o teto so barra
        # a criacao do 1001.
        ja_tem = {l[0] for l in con.execute(
            "SELECT DISTINCT projeto FROM medida WHERE usuario_id = ?",
            (usuario_id,))}
        vistos, cortados, invalidos = set(), 0, 0
        for p in projetos:
            if not isinstance(p, dict):
                invalidos += 1
                continue
            nome = str(p.get("nome") or "").strip()[:MAX_NOME_DE_PROJETO]
            # NOME RESERVADO NAO ENTRA. `INFRA` e `QUOTA` sao linhas de sistema
            # dentro da mesma tabela: um projeto chamado `_infra` sequestrava o
            # bloco de infraestrutura do painel — "Docker OK, nada quebrado" —
            # escrito por quem mandou o relatorio. Achado da revisao de
            # seguranca da etapa 11.
            if not nome or nome in RESERVADOS:
                invalidos += 1
                continue
            if len(vistos) >= MAX_PROJETOS_POR_RELATORIO and nome not in vistos:
                cortados += 1
                continue
            if len(json.dumps(p, ensure_ascii=False).encode("utf-8")) > \
                    MAX_BYTES_POR_PROJETO:
                invalidos += 1
                continue
            if nome not in ja_tem and len(ja_tem) >= MAX_PROJETOS_POR_CONTA:
                cortados += 1
                continue
            ja_tem.add(nome)
            vistos.add(nome)
            gravar(nome, "local", p, con, usuario_id=usuario_id)
            ver_projeto(maquina_id, nome,
                        str(p.get("caminho") or "")[:MAX_CAMINHO], con=con)
        if isinstance(infra, dict):
            infra = dict(infra)
            if avisos:
                infra["avisos"] = [str(a)[:500] for a in avisos[:MAX_AVISOS]]
            gravar(INFRA, "local", infra, con, usuario_id=usuario_id)
        if vistos:
            for antigo in projetos_da_maquina(maquina_id, con=con):
                if antigo["projeto"] not in vistos:
                    arquivar_projeto(maquina_id, antigo["projeto"], con=con)
        con.execute("UPDATE maquina SET visto_em = ? WHERE id = ?",
                    (agora(), maquina_id))
        if propria:                   # so encerra a transacao quem a abriu
            con.commit()
        # `cortados` e `invalidos` VOLTAM na resposta em vez de sumir. Truncagem
        # silenciosa e a mesma mentira por omissao de tudo mais neste projeto: o
        # agente imprimiria "enviado: 300 projetos" achando que mandou os 340.
        # `invalidos` nasceu porque `cortados` contava so o estouro do teto —
        # entrada malformada sumia sem contagem nenhuma, e um bug de
        # serializacao do lado do agente ficaria invisivel dos dois lados.
        return {"projetos": len(vistos), "infra": isinstance(infra, dict),
                "cortados": cortados, "invalidos": invalidos}
    except Exception:
        # `propria` pode nem existir se o estouro veio antes dela: um erro na
        # busca do dono nao desfaz a transacao de quem chamou.
        if locals().get("propria"):
            con.rollback()
        raise
    finally:
        if fechar:
            con.close()


def ver_projeto(maquina_id: int, projeto: str, caminho: str = "",
                visto_em: str = "", con=None) -> None:
    """O agente diz que o projeto existe ali. Ver de novo NAO duplica, e
    desarquiva: projeto que voltou a aparecer voltou a existir."""
    fechar = con is None
    con = con or conectar()
    try:
        con.execute(
            "INSERT INTO projeto_conectado (maquina_id, projeto, caminho, visto_em)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(maquina_id, projeto) DO UPDATE SET"
            " caminho=excluded.caminho, visto_em=excluded.visto_em, arquivado_em=NULL",
            (maquina_id, projeto, caminho or "", visto_em or agora()))
        if fechar:                    # ver `gravar`: nao quebre a transacao alheia
            con.commit()
    finally:
        if fechar:
            con.close()


def projetos_da_maquina(maquina_id: int, con=None) -> list:
    fechar = con is None
    con = con or conectar()
    try:
        return [dict(l) for l in con.execute(
            "SELECT * FROM projeto_conectado WHERE maquina_id = ?"
            " AND arquivado_em IS NULL ORDER BY projeto", (maquina_id,))]
    finally:
        if fechar:
            con.close()


def arquivar_projeto(maquina_id: int, projeto: str, con=None) -> None:
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("UPDATE projeto_conectado SET arquivado_em = ?"
                    " WHERE maquina_id = ? AND projeto = ?",
                    (agora(), maquina_id, projeto))
        if fechar:                    # ver `gravar`: nao quebre a transacao alheia
            con.commit()
    finally:
        if fechar:
            con.close()


def arquivar(pid: str, usuario_id: int = DONO_LOCAL, motivo: str = "", con=None) -> None:
    """Some com a pendencia para sempre — e por isso EXIGE motivo.

    Sumico sem motivo registrado nao tem volta explicavel: daqui a tres meses
    ninguem consegue responder por que aquele alerta parou de aparecer.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValueError("arquivar sem motivo nao e permitido: o rastro e o ponto")
    fechar = con is None
    con = con or conectar()
    try:
        con.execute(
            "INSERT INTO pendencia_arquivada (id, usuario_id, motivo, arquivado_em)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(id, usuario_id) DO UPDATE SET motivo=excluded.motivo,"
            " arquivado_em=excluded.arquivado_em, desarquivado_em=NULL",
            (pid, usuario_id, motivo, agora()))
        con.commit()
    finally:
        if fechar:
            con.close()


def desarquivar(pid: str, usuario_id: int = DONO_LOCAL, con=None) -> None:
    """Carimba a volta em vez de apagar a linha: o rastro vale tambem para o desfazer."""
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("UPDATE pendencia_arquivada SET desarquivado_em = ?"
                    " WHERE id = ? AND usuario_id = ?", (agora(), pid, usuario_id))
        con.commit()
    finally:
        if fechar:
            con.close()


def arquivadas_detalhe(usuario_id: int = DONO_LOCAL, con=None) -> list:
    """O que `arquivadas` esconde, com o rastro junto — para a tela mostrar.

    `arquivadas` devolve so o conjunto de ids, que e o que o motor de regras
    precisa. A secao "Arquivados" da tela do projeto precisa de mais: o motivo
    escrito na hora e a data. Sem os dois, "isto esta certo assim" vira um
    sumico sem explicacao, e daqui a tres meses ninguem responde por que aquele
    alerta parou de aparecer.
    """
    fechar = con is None
    con = con or conectar()
    try:
        return [{"id": l[0], "motivo": l[1], "arquivado_em": l[2]}
                for l in con.execute(
                    "SELECT id, motivo, arquivado_em FROM pendencia_arquivada"
                    " WHERE usuario_id = ? AND desarquivado_em IS NULL"
                    " ORDER BY arquivado_em DESC", (usuario_id,))]
    finally:
        if fechar:
            con.close()


def arquivadas(usuario_id: int = DONO_LOCAL, con=None) -> set:
    fechar = con is None
    con = con or conectar()
    try:
        return {l[0] for l in con.execute(
            "SELECT id FROM pendencia_arquivada WHERE usuario_id = ?"
            " AND desarquivado_em IS NULL", (usuario_id,))}
    finally:
        if fechar:
            con.close()


# ----------------------------------------------------- as chaves de acesso
#
# A chave PUBLICA de uma passkey. Ela nao abre nada: serve so para conferir uma
# assinatura feita pelo aparelho de quem entra. Quem levar este banco inteiro
# nao entra na conta de ninguem com o que esta aqui.

def guardar_chave_de_acesso(usuario_id: int, cred_id: str, chave,
                            apelido: str = "", contador: int = 0,
                            con=None) -> int:
    """Grava uma chave de acesso nova e devolve o id da linha.

    `cred_id` repetido levanta `IntegrityError` de proposito, e o UNIQUE e
    global: se duas contas pudessem reivindicar a mesma credencial, entrar na
    segunda seria entrar na primeira. Mesmo raciocinio do `INSERT` puro de
    `abrir_pareamento` — barulho onde havia silencio.
    """
    fechar = con is None
    con = con or conectar()
    try:
        cur = con.execute(
            "INSERT INTO chave_de_acesso"
            " (usuario_id, cred_id, chave_x, chave_y, apelido, contador,"
            "  criado_em) VALUES (?,?,?,?,?,?,?)",
            (usuario_id, (cred_id or "").strip(), "%x" % chave[0],
             "%x" % chave[1], (apelido or "").strip()[:60], max(0, contador),
             agora()))
        con.commit()
        return cur.lastrowid
    finally:
        if fechar:
            con.close()


def chave_de_acesso(cred_id: str, con=None):
    """A chave viva, de conta viva. None se nao existe, foi revogada ou o dono saiu.

    O `JOIN` com `usuario` e o mesmo de `sessao_valida`: desativar uma conta tem
    de fechar a porta no mesmo instante, e nao no dia em que alguem lembrar de
    revogar chave por chave.
    """
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute(
            "SELECT c.id, c.usuario_id, c.chave_x, c.chave_y, c.apelido,"
            "       c.contador"
            "  FROM chave_de_acesso c JOIN usuario u ON u.id = c.usuario_id"
            " WHERE c.cred_id = ? AND c.revogada_em IS NULL"
            "   AND u.desativado_em IS NULL", ((cred_id or "").strip(),)
        ).fetchone()
        if not l:
            return None
        return {"id": l["id"], "usuario_id": l["usuario_id"],
                "apelido": l["apelido"], "contador": l["contador"],
                "chave": (int(l["chave_x"], 16), int(l["chave_y"], 16))}
    finally:
        if fechar:
            con.close()


def chaves_de_acesso(usuario_id: int, con=None) -> list:
    """A lista para a TELA. Sem a chave publica: o que nao sai nao vaza."""
    fechar = con is None
    con = con or conectar()
    try:
        return [{"id": l["id"], "cred_id": l["cred_id"],
                 "apelido": l["apelido"], "criado_em": l["criado_em"],
                 "usado_em": l["usado_em"]}
                for l in con.execute(
                    "SELECT id, cred_id, apelido, criado_em, usado_em"
                    "  FROM chave_de_acesso"
                    " WHERE usuario_id = ? AND revogada_em IS NULL"
                    " ORDER BY criado_em", (usuario_id,))]
    finally:
        if fechar:
            con.close()


def usar_chave_de_acesso(id_: int, contador: int, con=None) -> bool:
    """Anota o uso e AVANCA o contador. False se o contador nao andou.

    O PROPRIO UPDATE E A GUARDA, e isto nao e estilo. Conferir em Python e
    gravar depois deixa uma janela entre a decisao e a escrita: duas copias da
    mesma passkey entrando no mesmo instante passariam as duas pela checagem
    antes de qualquer uma gravar, que e exatamente o que o contador existe para
    pegar. Mesmo desenho de `usar_pareamento`: quem nao levar `rowcount == 1`
    perdeu.

    A condicao tem duas metades, e a segunda e a excecao prevista na norma:
    autenticador que nao implementa contador manda zero para sempre, e ai nao ha
    o que comparar. Note a assimetria — zero-para-sempre passa, mas quem JA
    contou e volta a zero e regressao, e cai fora. `passkey.contador_ok` decide
    o mesmo em Python, e `test_o_banco_e_o_python_concordam` cobra que as duas
    nao se separem.
    """
    fechar = con is None
    con = con or conectar()
    try:
        cur = con.execute(
            "UPDATE chave_de_acesso SET contador = ?, usado_em = ?"
            " WHERE id = ? AND revogada_em IS NULL"
            "   AND (? > contador OR (contador = 0 AND ? = 0))",
            (max(0, contador), agora(), id_, contador, contador))
        con.commit()
        return cur.rowcount == 1
    finally:
        if fechar:
            con.close()


def revogar_chave_de_acesso(id_: int, usuario_id: int, con=None) -> bool:
    """Tira uma chave de circulacao. False se ela nao e desta conta.

    `usuario_id` na clausula NAO e redundante com a checagem da rota: e o
    IDOR classico de rota de remocao, onde o id da linha vem do navegador e
    quem manda um numero vizinho apaga a chave do outro.
    """
    fechar = con is None
    con = con or conectar()
    try:
        cur = con.execute(
            "UPDATE chave_de_acesso SET revogada_em = ?"
            " WHERE id = ? AND usuario_id = ? AND revogada_em IS NULL",
            (agora(), id_, usuario_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        if fechar:
            con.close()


# ------------------------------------------------- os codigos de recuperacao
#
# Alfabeto sem 0/O e sem 1/I/L: estes codigos sao para ser LIDOS DE UM PAPEL e
# digitados por uma pessoa. Zero confundido com O nao e erro de quem digita, e
# sim de quem escolheu o alfabeto.

ALFABETO_DE_RECUPERACAO = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
GRUPOS_DO_CODIGO = 4
LETRAS_POR_GRUPO = 5
CODIGOS_DE_RECUPERACAO = 10


def novo_codigo_de_recuperacao() -> str:
    """20 letras em quatro grupos: cerca de 99 bits. `secrets`, nunca `random`.

    Entropia alta e o que permite guardar isto como HMAC rapido em vez de
    scrypt: nao ha teto de tentativa por conta neste caminho (contar chute
    errado contra a conta deixaria qualquer um trancar o dono), entao quem
    segura e o tamanho do espaco, nao a lentidao do hash.
    """
    letras = [secrets.choice(ALFABETO_DE_RECUPERACAO)
              for _ in range(GRUPOS_DO_CODIGO * LETRAS_POR_GRUPO)]
    return "-".join("".join(letras[i:i + LETRAS_POR_GRUPO])
                    for i in range(0, len(letras), LETRAS_POR_GRUPO))


def _normalizar_codigo(codigo) -> str:
    """Tira tracinho, espaco e caixa. Quem copia de um papel erra os tres.

    Isto NAO afrouxa nada: o que sobra tem de bater letra a letra com um codigo
    sorteado de 99 bits. Afrouxar seria aceitar prefixo ou parte.
    """
    if not isinstance(codigo, str):
        return ""
    limpo = "".join(c for c in codigo.upper() if c.isalnum())
    return limpo if len(limpo) == GRUPOS_DO_CODIGO * LETRAS_POR_GRUPO else ""


def gerar_codigos_de_recuperacao(usuario_id: int,
                                 quantos: int = CODIGOS_DE_RECUPERACAO,
                                 con=None) -> list:
    """Sorteia a lista nova e devolve os codigos EM CLARO — uma vez so.

    Depois desta linha eles nao existem em lugar nenhum deste sistema: a tabela
    guarda so a impressao digital. Quem chama mostra na tela e esquece.

    Gerar de novo QUEIMA os codigos anteriores que ainda nao foram usados —
    senao o papel velho continua abrindo a conta, e "gerei codigos novos" viraria
    falsa sensacao de ter fechado a porta. Os JA USADOS ficam: codigo gasto e
    evidencia de que alguem entrou por ali, e apagar a linha apaga a evidencia.
    """
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("DELETE FROM codigo_recuperacao"
                    " WHERE usuario_id = ? AND usado_em IS NULL", (usuario_id,))
        claros = []
        for _ in range(max(1, quantos)):
            codigo = novo_codigo_de_recuperacao()
            con.execute("INSERT INTO codigo_recuperacao"
                        " (usuario_id, codigo_hash, criado_em) VALUES (?,?,?)",
                        (usuario_id,
                         hash_codigo(_normalizar_codigo(codigo)), agora()))
            claros.append(codigo)
        con.commit()
        return claros
    finally:
        if fechar:
            con.close()


def usar_codigo_de_recuperacao(codigo, con=None):
    """Gasta um codigo e devolve o dono. None para qualquer outra coisa.

    O UPDATE decide, pelo mesmo motivo de `usar_chave_de_acesso`: dois pedidos
    com o mesmo codigo no mesmo instante veriam ambos `usado_em IS NULL`, e um
    codigo de uso unico viraria duas entradas.

    A conta desativada e conferida DEPOIS de gastar o codigo, e isso e de
    proposito: gastar e a parte irreversivel, e um codigo apresentado a uma
    conta morta ja foi exposto — deixa-lo valido seria guardar um segredo que
    ja andou por ai.
    """
    limpo = _normalizar_codigo(codigo)
    if not limpo:
        return None
    fechar = con is None
    con = con or conectar()
    try:
        alvo = hash_codigo(limpo)
        cur = con.execute(
            "UPDATE codigo_recuperacao SET usado_em = ?"
            " WHERE codigo_hash = ? AND usado_em IS NULL", (agora(), alvo))
        if cur.rowcount != 1:
            con.rollback()
            return None
        l = con.execute(
            "SELECT c.usuario_id FROM codigo_recuperacao c"
            "  JOIN usuario u ON u.id = c.usuario_id"
            " WHERE c.codigo_hash = ? AND u.desativado_em IS NULL",
            (alvo,)).fetchone()
        con.commit()
        return l["usuario_id"] if l else None
    finally:
        if fechar:
            con.close()


def codigos_restantes(usuario_id: int, con=None) -> int:
    """Quantos ainda abrem a conta. A tela avisa quando esta acabando."""
    fechar = con is None
    con = con or conectar()
    try:
        return con.execute(
            "SELECT COUNT(*) c FROM codigo_recuperacao"
            " WHERE usuario_id = ? AND usado_em IS NULL",
            (usuario_id,)).fetchone()["c"]
    finally:
        if fechar:
            con.close()
