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
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tarefas

AQUI = Path(__file__).resolve().parent


def _caminho_do_banco() -> Path:
    """Onde mora o `hub.db`. `DERVS_BANCO` tira ele da pasta do codigo.

    Nesta maquina o padrao serve: o banco fica ao lado do codigo, e apagar o
    arquivo custa uma coleta. No servidor nao serve. La o codigo vive dentro de
    uma imagem que e jogada fora e reconstruida a cada publicacao, e um banco
    dentro dela seria apagado junto — toda conta, todo computador pareado e
    toda medicao, em silencio, a cada deploy. A variavel aponta o arquivo para
    um volume, que sobrevive a troca da imagem.

    Variavel definida e vazia vale como nao definida: e o que um
    `docker compose` produz quando a variavel do ambiente nao existe, e
    gravar em `Path("")` seria pior que usar o padrao.
    """
    fora = (os.environ.get("DERVS_BANCO") or "").strip()
    return Path(fora) if fora else AQUI / "hub.db"


BANCO = _caminho_do_banco()

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
    -- O DONO. Zero (`DONO_LOCAL`) e o pedido do laco local, sem sessao web —
    -- o mesmo padrao que `pendencia_estado` e `achado` usam para a mesma
    -- situacao. Toda escrita que nasce de uma sessao (`_auditoria_pedir`) leva
    -- o `usuario_id` daquela sessao, nunca zero.
    usuario_id   INTEGER NOT NULL DEFAULT 0,
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
    erro         TEXT,
    -- Fatia 2: o semaforo. `cor` nasce 'vermelho' AQUI, no esquema, e nao numa
    -- linha de Python que alguem pode esquecer de chamar. "Toda regra nasce
    -- vermelha" e propriedade do banco, nao promessa do codigo.
    cor              TEXT NOT NULL DEFAULT 'vermelho',
    aprovado_por     INTEGER,
    aprovado_em      TEXT,
    maquina_id       INTEGER,
    ramo             TEXT,
    executor         TEXT NOT NULL DEFAULT 'claude',
    rodadas          INTEGER NOT NULL DEFAULT 0,
    parada_pedida_em TEXT,
    visto_em         TEXT,
    frase            TEXT,
    resumo           TEXT,
    diff             TEXT
);
CREATE INDEX IF NOT EXISTS ix_fila_dia ON fila (terminado_em);
CREATE INDEX IF NOT EXISTS ix_fila_maquina ON fila (maquina_id, estado);
CREATE INDEX IF NOT EXISTS ix_fila_dono ON fila (usuario_id, estado);

-- O que a sessao foi dizendo, linha a linha. A numeracao `n` vem do agente
-- (`execucao.estado` ja devolve `total_de_linhas`), e a chave composta faz
-- reenvio ser idempotente de graca: o agente pode repetir um lote inteiro
-- depois de uma falha de rede sem duplicar nada.
CREATE TABLE IF NOT EXISTS tarefa_linha (
    tarefa_id TEXT NOT NULL,
    n         INTEGER NOT NULL,
    texto     TEXT NOT NULL DEFAULT '',
    quando    TEXT NOT NULL,
    PRIMARY KEY (tarefa_id, n)
);

-- A repintura do dono. Regra AUSENTE daqui e vermelha — a tabela guarda o que
-- foi repintado, nunca o padrao. Assim, apagar uma linha volta ao seguro em
-- vez de abrir o caminho.
CREATE TABLE IF NOT EXISTS cor_da_regra (
    regra  TEXT PRIMARY KEY,
    cor    TEXT NOT NULL,
    por    INTEGER,
    quando TEXT NOT NULL
);

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
    revogada_em TEXT,
    -- Fatia 2: a maquina so RECEBE tarefa se alguem ligou isto. Padrao 0, e
    -- isso e a lei 3 do repositorio — falha fechada. Parear um computador nao
    -- da a ele o direito de rodar codigo; e um segundo sim, explicito.
    executa     INTEGER NOT NULL DEFAULT 0
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

-- O cadastro de servidores nomeados de cada conta (Servidores multiplos,
-- E1, 04/09/2026). "O seu servidor" deixou de ser um endereco solto por
-- projeto e virou isto: uma conta pode ter varios servidores, cada um com
-- os proprios enderecos de producao.
--
-- NAO HA SEGREDO AQUI. `nome` e `padrao_subdominio` sao dado publico — o
-- mesmo nome que o dono ve na propria tela e o mesmo padrao de subdominio
-- que qualquer visitante ve na URL. Chave SSH, senha e token de deploy NAO
-- entram nesta tabela, agora nem nunca. O dono esta na linha pelo mesmo
-- motivo de `endereco_producao`, duas linhas abaixo: e dado de CONTA, nao
-- configuracao da maquina.
--
-- `padrao_subdominio` tem UM jeito so de dizer "nenhum": `NULL`. Nunca
-- string vazia. A conversao para `""` acontece so na borda JSON da rota —
-- o banco e o JSON tem, cada um, um jeito so de dizer a mesma coisa, e e a
-- mesma lei que `url` de `endereco_producao` ja segue.
CREATE TABLE IF NOT EXISTS servidor (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id        INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    nome              TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    padrao_subdominio TEXT,
    criado_em         TEXT NOT NULL,
    UNIQUE (usuario_id, nome)
);
CREATE INDEX IF NOT EXISTS ix_servidor_dono ON servidor (usuario_id);

-- O endereco de producao de cada projeto, POR SERVIDOR — a "porta 3" (fatia
-- B, 01/09/2026; servidor_id chegou na E1 de Servidores multiplos).
--
-- POR QUE TEM DONO, e nao e uma coluna solta por projeto: o endereco sai do
-- `casos.json`, que e um arquivo unico da maquina, e vira dado de conta. Duas
-- pessoas podem ter um projeto com o MESMO nome e servidores diferentes, e
-- quem le o endereco de um projeto e a conta que o gravou. Coluna sem dono
-- aqui seria IDOR por desenho de esquema — o mesmo defeito ja consertado duas
-- vezes neste repositorio (etapas 8 e 11), e nao se repete.
--
-- POR QUE TEM `servidor_id`: o mesmo projeto pode responder em mais de um
-- servidor ao mesmo tempo (staging, producao, um servidor por regiao). O
-- `UNIQUE` passa a ser (usuario_id, servidor_id, projeto) — o mesmo projeto
-- no MESMO servidor continua so podendo ter um endereco.
--
-- NAO HA SEGREDO AQUI. E uma URL publica, a mesma que qualquer visitante
-- digita no navegador. Chave SSH, senha de servidor e token de deploy NAO
-- entram nesta tabela, agora nem nunca: o DERVS mede o site de fora, nao
-- entra nele.
--
-- `url` e NOT NULL com CHECK de nao-vazio: "sem endereco" e a AUSENCIA da
-- linha, e nao uma linha com string vazia. Dois jeitos de dizer a mesma coisa
-- dao dois caminhos de leitura, e um deles sempre e esquecido.
CREATE TABLE IF NOT EXISTS endereco_producao (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    servidor_id   INTEGER NOT NULL REFERENCES servidor(id) ON DELETE CASCADE,
    projeto       TEXT NOT NULL CHECK (length(trim(projeto)) > 0),
    url           TEXT NOT NULL CHECK (length(trim(url)) > 0),
    criado_em     TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    UNIQUE (usuario_id, servidor_id, projeto)
);
CREATE INDEX IF NOT EXISTS ix_endereco_dono ON endereco_producao (usuario_id);
CREATE INDEX IF NOT EXISTS ix_endereco_servidor ON endereco_producao (servidor_id);

-- A instalacao do GitHub App DAQUELA conta. NAO confundir com a tabela
-- `instalacao` acima: aquela e a impressao digital da combinacao da cortina,
-- tem `CHECK (id = 1)` e nada tem a ver com o GitHub.
--
-- Ate aqui o `installation_id` era a variavel de ambiente
-- `DERVS_GITHUB_INSTALLATION_ID` — UMA instalacao para o processo inteiro, ou
-- seja, para todas as contas. Esta tabela e o que desfaz isso: o numero passa a
-- ter dono, e o `UNIQUE (usuario_id)` e o que impede uma conta acumular duas
-- instalacoes e ninguem saber qual delas vale.
--
-- NAO HA SEGREDO AQUI. O `installation_id` e um numero publico — ele aparece na
-- propria URL de instalacao, e `docs/operacao/token-do-coletor.md` ja o trata
-- assim. O que E segredo (a chave privada do App) continua fora do banco, no
-- ambiente. Se um dia entrar segredo nesta tabela, ele passa por
-- `cifrar`/`decifrar` com contexto — nao antes.
--
-- `installation_id` e TEXT com CHECK de nao-vazio: "sem instalacao" e a
-- AUSENCIA da linha, e nao uma linha com string vazia. Ver o mesmo motivo em
-- `endereco_producao`.
-- UMA INSTALACAO PERTENCE A UMA CONTA SO, e este `UNIQUE` e a segunda tranca
-- da posse. O `installation_id` e PUBLICO e sequencial, e perguntar ao GitHub
-- so prova que ele EXISTE — para qualquer numero deste App, inclusive o de
-- outra pessoa. Sem esta linha, duas contas gravavam o mesmo numero e a segunda
-- ficava amarrada a instalacao da primeira. Achado pelas duas revisoes de
-- 01/09/2026; a primeira tranca e a conferencia do dono em `servir.py`.
CREATE TABLE IF NOT EXISTS instalacao_github (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    installation_id TEXT NOT NULL CHECK (length(trim(installation_id)) > 0),
    criado_em       TEXT NOT NULL,
    atualizado_em   TEXT NOT NULL,
    UNIQUE (usuario_id),
    UNIQUE (installation_id)
);
CREATE INDEX IF NOT EXISTS ix_instalacao_github_dono
    ON instalacao_github (usuario_id);

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

-- A Auditoria Profunda (fase 4, 02/09/2026). `auditoria` e a CORRIDA;
-- `achado` e o que ela achou. Duas tabelas, e nao uma, de proposito: sem a
-- corrida, um projeto com zero linhas em `achado` e indistinguivel de um
-- projeto nunca auditado, e o painel diria "0 achados" para quem nunca foi
-- medido — a lei 2 deste repositorio.
CREATE TABLE IF NOT EXISTS auditoria (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id   INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    projeto      TEXT    NOT NULL CHECK (length(trim(projeto)) > 0),
    tarefa_id    TEXT,
    estado       TEXT    NOT NULL CHECK (estado IN ('ok','falha','recusada')),
    motivo       TEXT    NOT NULL DEFAULT '',
    achados_n    INTEGER NOT NULL DEFAULT 0,
    arquivos_n   INTEGER NOT NULL DEFAULT 0,
    custo_usd    REAL    NOT NULL DEFAULT 0.0,
    rodadas      INTEGER NOT NULL DEFAULT 0,
    medido_em    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_auditoria_projeto
    ON auditoria (usuario_id, projeto, medido_em);

-- `id` e TEXT (o id ESTAVEL da pendencia), e nao autoincremento: e por ele
-- que um achado que reaparece faz `INSERT ... ON CONFLICT DO UPDATE` na
-- MESMA linha, mantendo o `visto_em` mais antigo. Achado que nao voltou some
-- marcando `fechado_em`, NUNCA com DELETE, para o historico nao mentir.
--
-- A CHAVE E (usuario_id, id), NUNCA `id` sozinho. `id` e
-- `regra:projeto:sha256(arquivo,categoria,frase)[:12]` — deterministico e SEM
-- o dono dentro. Duas contas que auditam o MESMO repositorio geram o MESMO id
-- para o mesmo achado; com `id` como chave global, a segunda gravacao
-- TRANSFERIA a linha de dono e o achado sumia do painel da primeira conta,
-- sem erro e sem aviso. Achado da revisao de seguranca de 02/09/2026.
CREATE TABLE IF NOT EXISTS achado (
    id           TEXT    NOT NULL,
    auditoria_id INTEGER NOT NULL REFERENCES auditoria(id) ON DELETE CASCADE,
    usuario_id   INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    projeto      TEXT    NOT NULL DEFAULT '',
    regra        TEXT    NOT NULL DEFAULT '',
    categoria    TEXT    NOT NULL DEFAULT '',
    arquivo      TEXT    NOT NULL DEFAULT '',
    linha        INTEGER,
    gravidade    TEXT    NOT NULL DEFAULT 'media',
    frase        TEXT    NOT NULL DEFAULT '',
    o_que_fazer  TEXT    NOT NULL DEFAULT '',
    trecho       TEXT    NOT NULL DEFAULT '',
    visto_em     TEXT    NOT NULL,
    fechado_em   TEXT,
    PRIMARY KEY (usuario_id, id)
);
CREATE INDEX IF NOT EXISTS ix_achado_aberto
    ON achado (usuario_id, projeto, fechado_em);

-- A ponte com o DERVS-VOZ. O servidor SO GUARDA E ENTREGA: nenhuma destas
-- linhas vira comando aqui. `voz_estado` e a ultima foto que o VOZ mandou de
-- si mesmo (uma por maquina) e NAO e sinal de vida — `maquina.visto_em` so
-- anda quando chega relatorio. `voz_recado` e o recado que o dono deixou para
-- o VOZ e o que o VOZ respondeu. Toda leitura filtra por `usuario_id`.
CREATE TABLE IF NOT EXISTS voz_estado (
    maquina_id  INTEGER PRIMARY KEY REFERENCES maquina(id) ON DELETE CASCADE,
    usuario_id  INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    recebido_em TEXT    NOT NULL,
    dados       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS voz_recado (
    id            TEXT    PRIMARY KEY,
    usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    maquina_id    INTEGER NOT NULL REFERENCES maquina(id) ON DELETE CASCADE,
    criado_em     TEXT    NOT NULL,
    tipo          TEXT    NOT NULL,
    alvo          TEXT    NOT NULL,
    texto         TEXT    NOT NULL DEFAULT '',
    nivel         TEXT    NOT NULL,
    cerebro_pedido TEXT   NOT NULL,
    estado        TEXT    NOT NULL DEFAULT 'pendente'
                  CHECK (estado IN ('pendente', 'entregue', 'feito', 'recusado',
                                    'falhou', 'aguardando_clique')),
    cerebro       TEXT    NOT NULL DEFAULT '',
    resumo        TEXT    NOT NULL DEFAULT '',
    custo_usd     REAL    NOT NULL DEFAULT 0,
    duracao_s     REAL    NOT NULL DEFAULT 0,
    terminado_em  TEXT
);
CREATE INDEX IF NOT EXISTS ix_voz_recado_maquina
    ON voz_recado (maquina_id, estado, criado_em);
CREATE INDEX IF NOT EXISTS ix_voz_recado_dono
    ON voz_recado (usuario_id, criado_em);

-- Um aviso do painel por OCORRENCIA. `voz_recado.tipo` nao tem CHECK, entao o
-- tipo `avisar` nao exigiu migracao; esta tabela so lembra o que ja foi dito.
CREATE TABLE IF NOT EXISTS voz_aviso (
    usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    chave      TEXT    NOT NULL,
    criado_em  TEXT    NOT NULL,
    PRIMARY KEY (usuario_id, chave)
);
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
    _migrar_fila_semaforo(con)
    _migrar_endereco_producao(con)
    _migrar_servidor_por_endereco(con)
    _migrar_instalacao_github(con)
    _migrar_auditoria(con)
    _migrar_achado_dono(con)


# As tabelas que apontam para `usuario`. A migracao confere so estas: varrer o
# banco inteiro faria um orfao antigo, de outra tabela, travar toda subida.
FILHAS_DE_USUARIO = ("credencial", "sessao", "maquina", "pareamento",
                     "chave_de_acesso", "codigo_recuperacao",
                     "servidor", "endereco_producao", "instalacao_github",
                     "auditoria", "achado")


# Fatia 2. Nome da coluna -> o pedaco de DDL do `ALTER TABLE`. A ordem e a do
# esquema, e o valor padrao de `cor` e o coracao do semaforo: uma linha antiga,
# que nasceu antes de existir semaforo, acorda VERMELHA.
_COLUNAS_SEMAFORO = (
    ("usuario_id",       "INTEGER NOT NULL DEFAULT 0"),
    ("cor",              "TEXT NOT NULL DEFAULT 'vermelho'"),
    ("aprovado_por",     "INTEGER"),
    ("aprovado_em",      "TEXT"),
    ("maquina_id",       "INTEGER"),
    ("ramo",             "TEXT"),
    ("executor",         "TEXT NOT NULL DEFAULT 'claude'"),
    ("rodadas",          "INTEGER NOT NULL DEFAULT 0"),
    ("parada_pedida_em", "TEXT"),
    ("visto_em",         "TEXT"),
    ("frase",            "TEXT"),
    ("resumo",           "TEXT"),
    ("diff",             "TEXT"),
)


def _migrar_fila_semaforo(con: sqlite3.Connection) -> None:
    """A `fila` e a `maquina` ganham as colunas da Fatia 2.

    `ALTER TABLE ... ADD COLUMN` nao reescreve linha nenhuma: o SQLite guarda o
    padrao no cabecalho da tabela e as linhas antigas passam a le-lo. Por isso
    esta migracao roda contra o hub.db de producao sem tocar em dado — o que
    ela NAO pode e rodar duas vezes, e por isso a checagem por `table_info`.

    Nunca `executescript` aqui: ele da COMMIT implicito e desmontaria o
    `BEGIN IMMEDIATE`, deixando duas subidas simultaneas migrarem juntas.
    Licao paga em 26/08/2026.
    """
    forma = list(con.execute("PRAGMA table_info(fila)"))
    if not forma:
        return                                   # banco novo: o ESQUEMA ja faz certo
    tem_fila = {l[1] for l in forma}
    tem_maq = {l[1] for l in con.execute("PRAGMA table_info(maquina)")}
    faltam_fila = [c for c in _COLUNAS_SEMAFORO if c[0] not in tem_fila]
    falta_maq = bool(tem_maq) and "executa" not in tem_maq
    if not faltam_fila and not falta_maq:
        return
    try:
        con.execute("BEGIN IMMEDIATE")
        # RELIDO DENTRO DA TRANSACAO. A leitura la em cima aconteceu antes do
        # lock; dois processos subindo juntos leriam os dois "preciso migrar" e
        # o segundo morreria com "duplicate column name".
        tem_fila = {l[1] for l in con.execute("PRAGMA table_info(fila)")}
        tem_maq = {l[1] for l in con.execute("PRAGMA table_info(maquina)")}
        for nome, ddl in _COLUNAS_SEMAFORO:
            if nome not in tem_fila:
                con.execute("ALTER TABLE fila ADD COLUMN %s %s" % (nome, ddl))
        if tem_maq and "executa" not in tem_maq:
            con.execute("ALTER TABLE maquina ADD COLUMN"
                        " executa INTEGER NOT NULL DEFAULT 0")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        _religar_fk(con)


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


# Duas copias do mesmo CREATE, de proposito — o mesmo arranjo de
# `_CREATE_CREDENCIAL`: a do ESQUEMA e a documentacao do banco de hoje, esta e
# a ferramenta da migracao. Se uma mudar, a outra muda junto, e ha teste que
# cobra as duas terem a mesma forma.
_CREATE_SERVIDOR = """CREATE TABLE IF NOT EXISTS servidor (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id        INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    nome              TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    padrao_subdominio TEXT,
    criado_em         TEXT NOT NULL,
    UNIQUE (usuario_id, nome))"""

_CREATE_ENDERECO_PRODUCAO = """CREATE TABLE IF NOT EXISTS endereco_producao (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    servidor_id   INTEGER NOT NULL REFERENCES servidor(id) ON DELETE CASCADE,
    projeto       TEXT NOT NULL CHECK (length(trim(projeto)) > 0),
    url           TEXT NOT NULL CHECK (length(trim(url)) > 0),
    criado_em     TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    UNIQUE (usuario_id, servidor_id, projeto))"""


def _migrar_endereco_producao(con: sqlite3.Connection) -> None:
    """`servidor` e a tabela do endereco de producao nascem aqui, e nao so no
    ESQUEMA.

    POR QUE NA MIGRACAO, se o `ESQUEMA` roda logo depois e tem
    `CREATE TABLE IF NOT EXISTS`: porque as duas apontam para `usuario` (e
    `endereco_producao` tambem para `servidor`), e o `ESQUEMA` roda DEPOIS de
    toda a migracao. Criar aqui, no fim, deixa as tabelas existirem para o
    `_orfaos` da proxima reconstrucao de `usuario` — que e o motivo de as duas
    estarem em `FILHAS_DE_USUARIO`. O dia em que houver uma migracao nova que
    mexa nelas, o lugar ja esta feito.
    As duas nascem VAZIAS aqui: e vazia, entao nao ha dado antigo a converter,
    um hub.db de producao passa por aqui sem uma linha ser tocada. Um hub.db
    que JA TEM `endereco_producao` (na forma antiga, sem `servidor_id`) nao
    passa por este caminho — a condicao de "ja migrado" e a PRESENCA da
    tabela, e quem cuida de dar `servidor_id` a essas linhas e
    `_migrar_servidor_por_endereco`, logo abaixo.

    Nunca `executescript` aqui: ele da COMMIT implicito e desmontaria o
    `BEGIN IMMEDIATE`, deixando duas subidas simultaneas migrarem juntas.
    Licao paga em 26/08/2026.
    """
    presentes = {l[0] for l in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "usuario" not in presentes:
        return                        # banco novo: o ESQUEMA ja faz certo
    if "endereco_producao" in presentes:
        return                        # ja migrado
    try:
        con.execute("BEGIN IMMEDIATE")
        # RELIDO DENTRO DA TRANSACAO. A leitura la em cima aconteceu antes do
        # lock; dois processos subindo juntos leriam os dois "preciso migrar", e
        # sem o `IF NOT EXISTS` do CREATE o segundo morreria dentro de
        # `conectar()` — que roda em toda requisicao, entao o processo nem
        # subiria. O `IF NOT EXISTS` sozinho ja bastaria; a releitura e o que
        # deixa a intencao no lugar certo se um dia o CREATE virar ALTER.
        ja = con.execute("SELECT 1 FROM sqlite_master"
                         " WHERE type='table' AND name='endereco_producao'"
                         ).fetchone()
        if ja:
            con.rollback()
            return
        con.execute(_CREATE_SERVIDOR)
        con.execute("CREATE INDEX IF NOT EXISTS ix_servidor_dono"
                    " ON servidor (usuario_id)")
        con.execute(_CREATE_ENDERECO_PRODUCAO)
        con.execute("CREATE INDEX IF NOT EXISTS ix_endereco_dono"
                    " ON endereco_producao (usuario_id)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_endereco_servidor"
                    " ON endereco_producao (servidor_id)")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        _religar_fk(con)


def _migrar_servidor_por_endereco(con: sqlite3.Connection) -> None:
    """`endereco_producao` ganhou `servidor_id` (Servidores multiplos, E1,
    04/09/2026). Antes, "o seu servidor" era um endereco solto por projeto;
    agora e um cadastro de servidores nomeados, e todo endereco pertence a um.

    Um hub.db que ja tinha `endereco_producao` na forma ANTIGA (sem
    `servidor_id`) precisa de um servidor para cada dono, e cada linha antiga
    aponta para o servidor daquele dono — nome `"Servidor"`, sem padrao de
    subdominio. Nenhum endereco ja gravado some no caminho.

    O SQLite nao sabe trocar `UNIQUE` nem acrescentar FK `NOT NULL` sem
    reconstruir a tabela — mesmo molde de `_migrar_achado_dono`. Nunca
    `executescript` aqui: ele da COMMIT implicito e desmontaria o
    `BEGIN IMMEDIATE`, deixando duas subidas simultaneas migrarem juntas.
    Licao paga em 26/08/2026.
    """
    forma = list(con.execute("PRAGMA table_info(endereco_producao)"))
    if not forma:
        return                        # sem a tabela: o proximo passo cria certo
    if "servidor_id" in {l[1] for l in forma}:
        return                        # ja migrado
    con.execute("PRAGMA foreign_keys=OFF")
    try:
        # TUDO OU NADA. `executescript` faria COMMIT implicito e rodaria os
        # comandos como transacoes soltas: uma queda entre o DROP e o RENAME
        # apagaria a tabela e deixaria a copia orfa.
        con.execute("BEGIN IMMEDIATE")
        # DE NOVO, E AGORA DENTRO DA TRANSACAO — mesmo motivo do gemeo em
        # `_migrar_pendencia_estado`: a leitura la em cima aconteceu antes do
        # lock, e duas subidas simultaneas leriam as duas "preciso migrar".
        forma = list(con.execute("PRAGMA table_info(endereco_producao)"))
        if not forma:
            con.rollback()
            return
        if "servidor_id" in {l[1] for l in forma}:
            con.rollback()
            return
        con.execute(_CREATE_SERVIDOR)
        con.execute("CREATE INDEX IF NOT EXISTS ix_servidor_dono"
                    " ON servidor (usuario_id)")
        quando = agora()
        # Um servidor "Servidor" por DONO presente em `endereco_producao` —
        # nunca um por linha: dois enderecos do mesmo dono viram o mesmo
        # servidor, exatamente como eram um endereco solto por projeto.
        donos = [l["usuario_id"] for l in con.execute(
            "SELECT DISTINCT usuario_id FROM endereco_producao")]
        servidor_do_dono = {}
        for dono in donos:
            cur = con.execute(
                "INSERT INTO servidor (usuario_id, nome, criado_em)"
                " VALUES (?, 'Servidor', ?)", (dono, quando))
            servidor_do_dono[dono] = cur.lastrowid
        con.execute("DROP TABLE IF EXISTS endereco_producao_nova")
        con.execute("""CREATE TABLE endereco_producao_nova (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id    INTEGER NOT NULL
                              REFERENCES usuario(id) ON DELETE CASCADE,
                servidor_id   INTEGER NOT NULL
                              REFERENCES servidor(id) ON DELETE CASCADE,
                projeto       TEXT NOT NULL CHECK (length(trim(projeto)) > 0),
                url           TEXT NOT NULL CHECK (length(trim(url)) > 0),
                criado_em     TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                UNIQUE (usuario_id, servidor_id, projeto))""")
        for dono, sid in servidor_do_dono.items():
            con.execute(
                "INSERT INTO endereco_producao_nova"
                " (id, usuario_id, servidor_id, projeto, url,"
                "  criado_em, atualizado_em)"
                " SELECT id, usuario_id, ?, projeto, url,"
                "        criado_em, atualizado_em"
                "   FROM endereco_producao WHERE usuario_id = ?",
                (sid, dono))
        con.execute("DROP TABLE endereco_producao")
        con.execute("ALTER TABLE endereco_producao_nova"
                    " RENAME TO endereco_producao")
        con.execute("CREATE INDEX IF NOT EXISTS ix_endereco_dono"
                    " ON endereco_producao (usuario_id)")
        con.execute("CREATE INDEX IF NOT EXISTS ix_endereco_servidor"
                    " ON endereco_producao (servidor_id)")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        _religar_fk(con)


# O mesmo arranjo de `_CREATE_ENDERECO_PRODUCAO`: duas copias do mesmo CREATE de
# proposito — a do ESQUEMA e a documentacao do banco de hoje, esta e a
# ferramenta da migracao. Se uma mudar, a outra muda junto, e ha teste que cobra
# as duas terem a mesma forma.
_CREATE_INSTALACAO_GITHUB = """CREATE TABLE IF NOT EXISTS instalacao_github (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id      INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    installation_id TEXT NOT NULL CHECK (length(trim(installation_id)) > 0),
    criado_em       TEXT NOT NULL,
    atualizado_em   TEXT NOT NULL,
    UNIQUE (usuario_id),
    UNIQUE (installation_id))"""


def _migrar_instalacao_github(con: sqlite3.Connection) -> None:
    """A tabela da instalacao do GitHub nasce aqui, e nao so no ESQUEMA.

    Mesmo motivo de `_migrar_endereco_producao`: a tabela aponta para `usuario`,
    e o `ESQUEMA` roda DEPOIS de toda a migracao. Criar aqui, no fim, deixa a
    tabela existir para o `_orfaos` da proxima reconstrucao de `usuario` — que e
    o motivo de ela estar em `FILHAS_DE_USUARIO`.

    Ela nasce VAZIA, e isso e uma decisao, nao um esquecimento: o
    `installation_id` de hoje mora na variavel de ambiente
    `DERVS_GITHUB_INSTALLATION_ID`, que e do processo e nao de ninguem.
    Escolher uma conta para herda-lo seria o banco inventando um dono — e dono
    inventado em caminho de autorizacao e o IDOR de amanha. Cada conta reconecta.

    Nunca `executescript` aqui: ele da COMMIT implicito e desmontaria o
    `BEGIN IMMEDIATE`, deixando duas subidas simultaneas migrarem juntas.
    Licao paga em 26/08/2026.
    """
    presentes = {l[0] for l in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "usuario" not in presentes:
        return                        # banco novo: o ESQUEMA ja faz certo
    if "instalacao_github" in presentes:
        return                        # ja migrado
    try:
        con.execute("BEGIN IMMEDIATE")
        # RELIDO DENTRO DA TRANSACAO — ver o comentario gemeo em
        # `_migrar_endereco_producao`: a leitura la em cima aconteceu antes do
        # lock, e duas subidas simultaneas leriam as duas "preciso migrar".
        ja = con.execute("SELECT 1 FROM sqlite_master"
                         " WHERE type='table' AND name='instalacao_github'"
                         ).fetchone()
        if ja:
            con.rollback()
            return
        con.execute(_CREATE_INSTALACAO_GITHUB)
        con.execute("CREATE INDEX IF NOT EXISTS ix_instalacao_github_dono"
                    " ON instalacao_github (usuario_id)")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        _religar_fk(con)


# O mesmo arranjo de `_CREATE_INSTALACAO_GITHUB`: duas copias do mesmo CREATE
# de proposito — a do ESQUEMA e a documentacao do banco de hoje, esta e a
# ferramenta da migracao. Ha teste que cobra as duas terem a mesma forma.
_CREATE_AUDITORIA = """CREATE TABLE IF NOT EXISTS auditoria (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id   INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    projeto      TEXT    NOT NULL CHECK (length(trim(projeto)) > 0),
    tarefa_id    TEXT,
    estado       TEXT    NOT NULL CHECK (estado IN ('ok','falha','recusada')),
    motivo       TEXT    NOT NULL DEFAULT '',
    achados_n    INTEGER NOT NULL DEFAULT 0,
    arquivos_n   INTEGER NOT NULL DEFAULT 0,
    custo_usd    REAL    NOT NULL DEFAULT 0.0,
    rodadas      INTEGER NOT NULL DEFAULT 0,
    medido_em    TEXT    NOT NULL
)"""

_CREATE_ACHADO = """CREATE TABLE IF NOT EXISTS achado (
    id           TEXT    NOT NULL,
    auditoria_id INTEGER NOT NULL REFERENCES auditoria(id) ON DELETE CASCADE,
    usuario_id   INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    projeto      TEXT    NOT NULL DEFAULT '',
    regra        TEXT    NOT NULL DEFAULT '',
    categoria    TEXT    NOT NULL DEFAULT '',
    arquivo      TEXT    NOT NULL DEFAULT '',
    linha        INTEGER,
    gravidade    TEXT    NOT NULL DEFAULT 'media',
    frase        TEXT    NOT NULL DEFAULT '',
    o_que_fazer  TEXT    NOT NULL DEFAULT '',
    trecho       TEXT    NOT NULL DEFAULT '',
    visto_em     TEXT    NOT NULL,
    fechado_em   TEXT,
    PRIMARY KEY (usuario_id, id)
)"""


def _migrar_auditoria(con: sqlite3.Connection) -> None:
    """As duas tabelas da Auditoria Profunda nascem aqui, e nao so no ESQUEMA.

    Mesmo motivo de `_migrar_instalacao_github`: as duas apontam para
    `usuario`, e o `ESQUEMA` roda DEPOIS de toda a migracao. Criar aqui, no
    fim, deixa as tabelas existirem para o `_orfaos` da proxima reconstrucao
    de `usuario` — que e o motivo de as duas estarem em `FILHAS_DE_USUARIO`.

    Nascem VAZIAS: nao ha dado antigo a converter, um hub.db de producao passa
    por aqui sem uma linha ser tocada.

    Nunca `executescript` aqui: ele da COMMIT implicito e desmontaria o
    `BEGIN IMMEDIATE`, deixando duas subidas simultaneas migrarem juntas.
    Licao paga em 26/08/2026.
    """
    presentes = {l[0] for l in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "usuario" not in presentes:
        return                        # banco novo: o ESQUEMA ja faz certo
    if "auditoria" in presentes and "achado" in presentes:
        return                        # ja migrado
    try:
        con.execute("BEGIN IMMEDIATE")
        # RELIDO DENTRO DA TRANSACAO — ver o comentario gemeo em
        # `_migrar_instalacao_github`: a leitura la em cima aconteceu antes do
        # lock, e duas subidas simultaneas leriam as duas "preciso migrar".
        ja = {l[0] for l in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name IN ('auditoria','achado')")}
        if "auditoria" in ja and "achado" in ja:
            con.rollback()
            return
        con.execute(_CREATE_AUDITORIA)
        con.execute("CREATE INDEX IF NOT EXISTS ix_auditoria_projeto"
                    " ON auditoria (usuario_id, projeto, medido_em)")
        con.execute(_CREATE_ACHADO)
        con.execute("CREATE INDEX IF NOT EXISTS ix_achado_aberto"
                    " ON achado (usuario_id, projeto, fechado_em)")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        _religar_fk(con)


def _migrar_achado_dono(con: sqlite3.Connection) -> None:
    """`achado.id` nasceu como chave primaria GLOBAL — sem o dono dentro. O id
    e `regra:projeto:sha256(arquivo,categoria,frase)[:12]`, deterministico: o
    MESMO defeito, no MESMO arquivo, com a MESMA frase, gera o MESMO id em
    duas contas que auditam o mesmo repositorio. Com `id` sozinho como chave,
    a segunda gravacao fazia `ON CONFLICT` TRANSFERIR a linha para o segundo
    dono — o achado sumia do painel do primeiro, sem erro e sem aviso. A
    chave passa a ser `(usuario_id, id)`.

    O SQLite nao sabe trocar chave primaria, entao a tabela e reconstruida —
    mesmo molde de `_migrar_pendencia_estado`. O dado existente e preservado
    com o mesmo dono que ja tinha.

    Nunca `executescript` aqui: ele da COMMIT implicito e desmontaria o
    `BEGIN IMMEDIATE`, deixando duas subidas simultaneas migrarem juntas.
    Licao paga em 26/08/2026.
    """
    forma = list(con.execute("PRAGMA table_info(achado)"))
    if not forma:
        return                        # sem a tabela: o proximo passo cria certo
    chave = [l[1] for l in sorted((l for l in forma if l[5]), key=lambda l: l[5])]
    if chave == ["usuario_id", "id"]:
        return                        # ja migrado
    con.execute("PRAGMA foreign_keys=OFF")
    try:
        # TUDO OU NADA. `executescript` faria COMMIT implicito e rodaria os
        # comandos como transacoes soltas: uma queda entre o DROP e o RENAME
        # apagaria a tabela e deixaria a copia orfa.
        con.execute("BEGIN IMMEDIATE")
        # DE NOVO, E AGORA DENTRO DA TRANSACAO — mesmo motivo do gemeo em
        # `_migrar_pendencia_estado`: a leitura la em cima aconteceu antes do
        # lock, e duas subidas simultaneas leriam as duas "preciso migrar".
        forma = list(con.execute("PRAGMA table_info(achado)"))
        if not forma:
            con.rollback()
            return
        chave = [l[1] for l in sorted((l for l in forma if l[5]),
                                      key=lambda l: l[5])]
        if chave == ["usuario_id", "id"]:
            con.rollback()
            return
        con.execute("DROP TABLE IF EXISTS achado_nova")
        con.execute("""CREATE TABLE achado_nova (
                id           TEXT    NOT NULL,
                auditoria_id INTEGER NOT NULL
                             REFERENCES auditoria(id) ON DELETE CASCADE,
                usuario_id   INTEGER NOT NULL
                             REFERENCES usuario(id) ON DELETE CASCADE,
                projeto      TEXT    NOT NULL DEFAULT '',
                regra        TEXT    NOT NULL DEFAULT '',
                categoria    TEXT    NOT NULL DEFAULT '',
                arquivo      TEXT    NOT NULL DEFAULT '',
                linha        INTEGER,
                gravidade    TEXT    NOT NULL DEFAULT 'media',
                frase        TEXT    NOT NULL DEFAULT '',
                o_que_fazer  TEXT    NOT NULL DEFAULT '',
                trecho       TEXT    NOT NULL DEFAULT '',
                visto_em     TEXT    NOT NULL,
                fechado_em   TEXT,
                PRIMARY KEY (usuario_id, id))""")
        con.execute(
            "INSERT INTO achado_nova (id, auditoria_id, usuario_id, projeto,"
            " regra, categoria, arquivo, linha, gravidade, frase,"
            " o_que_fazer, trecho, visto_em, fechado_em)"
            " SELECT id, auditoria_id, usuario_id, projeto, regra, categoria,"
            " arquivo, linha, gravidade, frase, o_que_fazer, trecho,"
            " visto_em, fechado_em FROM achado")
        con.execute("DROP TABLE achado")
        con.execute("ALTER TABLE achado_nova RENAME TO achado")
        con.execute("CREATE INDEX IF NOT EXISTS ix_achado_aberto"
                    " ON achado (usuario_id, projeto, fechado_em)")
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
            # A camada `auditoria` NAO mora em `medida`: vive nas tabelas
            # dedicadas `auditoria`/`achado`, porque a CORRIDA precisa
            # sobreviver mesmo quando ela nao acha nada. Projeto sem corrida
            # recebe `None` — nunca `{}` nem `{"achados": []}`, que teriam a
            # mesma cara de "auditei e nao achei nada". Lei 2 deste repositorio.
            corrida = auditoria_do_projeto(usuario_id, nome, con=con)
            if corrida:
                p["auditoria"] = {
                    "estado": corrida["estado"],
                    "motivo": corrida["motivo"],
                    "achados_n": corrida["achados_n"],
                    "arquivos_n": corrida["arquivos_n"],
                    "custo_usd": corrida["custo_usd"],
                    "rodadas": corrida["rodadas"],
                    "achados": achados_do_projeto(usuario_id, nome, con=con),
                }
                p["medido_em"]["auditoria"] = corrida["medido_em"]
            else:
                p.setdefault("auditoria", None)
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
                "pr_url", "erro",
                # Fatia 2
                "cor", "aprovado_por", "aprovado_em", "maquina_id", "ramo",
                "executor", "rodadas", "parada_pedida_em", "visto_em",
                "frase", "resumo", "diff")

# Os estados por onde uma tarefa passa. `aguardando_aprovacao` entrou na
# Fatia 2 e mora ENTRE `esperando` e `rodando`: e onde a tarefa vermelha para,
# esperando o clique do dono. Sem esse estado, "vermelha" seria so uma coluna
# que ninguem olha.
ESTADOS_FILA = ("esperando", "aguardando_aprovacao", "rodando", "ok", "falha")

VERMELHO = "vermelho"
VERDE = "verde"


def enfileirar(pendencias: list, con=None) -> int:
    """Insere as pendencias que ainda nao estao na fila. Devolve quantas entraram."""
    fechar = con is None
    con = con or conectar()
    entraram = 0
    try:
        for p in pendencias or []:
            cur = con.execute(
                "INSERT OR IGNORE INTO fila (id, usuario_id, projeto, regra,"
                " gravidade, risco, trilho, criado_em, executor)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (p.get("id") or "", int(p.get("usuario_id") or 0),
                 p.get("projeto") or "", p.get("regra") or "",
                 p.get("gravidade") or "media", float(p.get("risco") or 0),
                 p.get("trilho") or "", agora(), p.get("executor") or "claude"))
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




# ---------------------------------------------------------------------------
# Fatia 2 — a tarefa vira linha de banco.
#
# Ate aqui a execucao vivia num dicionario em memoria (`execucao._execucao`):
# um recurso por maquina, sem historico, sem retomada. Com dois bracos isso
# nao fecha. O que segue e o minimo para a tarefa sobreviver a um reinicio.
# ---------------------------------------------------------------------------

# Os estados em que uma tarefa ainda pode ser pega por um agente.
_A_PEGAR = ("esperando", "aguardando_aprovacao")


def tarefa_para_maquina(maquina_id: int, con=None):
    """A proxima tarefa que ESTA maquina poderia pegar, ou `None`.

    So LE. Quem decide se ela pode rodar e `tarefas.pode_rodar`, e quem a
    reserva e `entregar_tarefa` — separar as tres coisas e o que permite ao
    servidor recusar sem deixar rastro no banco.

    Maquina sem `executa`, revogada, ou inexistente devolve `None`. Falha
    fechada: a duvida nunca vira tarefa entregue.
    """
    fechar = con is None
    con = con or conectar()
    try:
        m = con.execute(
            "SELECT id, executa, usuario_id FROM maquina"
            " WHERE id = ? AND revogada_em IS NULL", (maquina_id,)).fetchone()
        if not m or not int(m["executa"] or 0):
            return None
        marcas = ",".join("?" * len(_A_PEGAR))
        # LEFT JOIN achado: o `detalhe` de uma tarefa nascida de um achado de
        # auditoria vem do proprio achado, e nao so de `fila.erro` (que para
        # uma tarefa nova e sempre vazio). So LEITURA — a funcao continua
        # falhando fechada.
        #
        # `achado.usuario_id = ?` (o dono da MAQUINA) entra na condicao do
        # JOIN, e nao no WHERE: um achado.id que colida entre duas contas (o
        # id nao carrega o dono) nao pode entregar `frase`/`o_que_fazer`/
        # `trecho`/`arquivo` — codigo-fonte privado — para a maquina de outra
        # conta. Sem esta condicao, o JOIN casaria com qualquer dono.
        l = con.execute(
            "SELECT fila.*, achado.frase AS achado_frase,"
            " achado.o_que_fazer AS achado_o_que_fazer,"
            " achado.trecho AS achado_trecho,"
            " achado.arquivo AS achado_arquivo,"
            " achado.linha AS achado_linha"
            " FROM fila LEFT JOIN achado"
            "   ON achado.id = fila.id AND achado.usuario_id = ?"
            " WHERE fila.usuario_id = ?"
            "   AND fila.estado IN (%s)"
            "   AND fila.trilho <> ''"
            "   AND fila.parada_pedida_em IS NULL"
            "   AND (fila.maquina_id IS NULL OR fila.maquina_id = ?)"
            " ORDER BY (fila.aprovado_em IS NULL), fila.criado_em"
            " LIMIT 1" % marcas,
            [m["usuario_id"], m["usuario_id"]] + list(_A_PEGAR)
            + [maquina_id]).fetchone()
        return dict(l) if l else None
    finally:
        if fechar:
            con.close()


def entregar_tarefa(tarefa_id: str, maquina_id: int, agora_iso: str = "",
                    con=None) -> bool:
    """Reserva a tarefa para esta maquina. `True` se ESTA chamada a pegou.

    O `WHERE` repete a condicao inteira de proposito: e um UPDATE condicional,
    e e ele — nao o `if` do Python la em cima — que garante que dois agentes
    perguntando no mesmo segundo nao levem a mesma tarefa. `rowcount` diz quem
    ganhou.
    """
    fechar = con is None
    con = con or conectar()
    quando = agora_iso or agora()
    try:
        marcas = ",".join("?" * len(_A_PEGAR))
        cur = con.execute(
            "UPDATE fila SET estado = 'rodando', maquina_id = ?,"
            "   iniciado_em = COALESCE(iniciado_em, ?), visto_em = ?,"
            "   tentativas = tentativas + 1"
            " WHERE id = ? AND estado IN (%s)"
            "   AND parada_pedida_em IS NULL"
            "   AND (maquina_id IS NULL OR maquina_id = ?)" % marcas,
            [maquina_id, quando, quando, tarefa_id] + list(_A_PEGAR)
            + [maquina_id])
        con.commit()
        return cur.rowcount == 1
    finally:
        if fechar:
            con.close()


def registrar_progresso(tarefa_id: str, maquina_id: int, frase: str = "",
                        linhas=None, rodadas=None, custo_usd=None,
                        agora_iso: str = "", con=None) -> bool:
    """Guarda o que a sessao esta dizendo. Devolve `True` se pediram parada.

    O booleano de volta e o freio: e por ele que o botao Parar chega ao agente,
    na RESPOSTA do proprio pedido de progresso. Sem conexao nova.

    `linhas` e uma lista de `(n, texto)`. `INSERT OR IGNORE` com chave composta
    faz o reenvio de um lote inteiro ser inofensivo — o agente pode repetir
    depois de uma falha de rede sem duplicar nada na tela.
    """
    fechar = con is None
    con = con or conectar()
    quando = agora_iso or agora()
    try:
        alvo = con.execute(
            "SELECT id, parada_pedida_em FROM fila"
            " WHERE id = ? AND maquina_id = ?",
            (tarefa_id, maquina_id)).fetchone()
        if not alvo:
            return False
        campos = ["visto_em = ?"]
        valores = [quando]
        if frase:
            campos.append("frase = ?")
            valores.append(frase)
        if rodadas is not None:
            campos.append("rodadas = ?")
            valores.append(int(rodadas))
        if custo_usd is not None:
            campos.append("custo_usd = ?")
            valores.append(float(custo_usd))
        con.execute("UPDATE fila SET %s WHERE id = ?" % ", ".join(campos),
                    valores + [tarefa_id])
        for par in (linhas or []):
            try:
                n, texto = int(par[0]), str(par[1])
            except (TypeError, ValueError, IndexError):
                continue
            con.execute(
                "INSERT OR IGNORE INTO tarefa_linha (tarefa_id, n, texto, quando)"
                " VALUES (?,?,?,?)", (tarefa_id, n, texto, quando))
        con.commit()
        return bool(alvo["parada_pedida_em"])
    finally:
        if fechar:
            con.close()


def registrar_desfecho(tarefa_id: str, maquina_id: int, estado: str,
                       ramo: str = "", resumo: str = "", diff: str = "",
                       pr_url: str = "", rodadas=None, custo_usd=None,
                       erro: str = "", agora_iso: str = "", con=None) -> bool:
    """O fim da sessao. `True` se a tarefa era mesmo desta maquina."""
    if estado not in ("ok", "falha"):
        return False
    fechar = con is None
    con = con or conectar()
    quando = agora_iso or agora()
    try:
        cur = con.execute(
            "UPDATE fila SET estado = ?, terminado_em = ?, visto_em = ?,"
            "   ramo = ?, resumo = ?, diff = ?, pr_url = ?, erro = ?,"
            "   rodadas = COALESCE(?, rodadas),"
            "   custo_usd = COALESCE(?, custo_usd)"
            " WHERE id = ? AND maquina_id = ?",
            (estado, quando, quando, ramo or None, resumo or None,
             diff or None, pr_url or None, erro or None,
             None if rodadas is None else int(rodadas),
             None if custo_usd is None else float(custo_usd),
             tarefa_id, maquina_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        if fechar:
            con.close()


# ---------------------------------------------------------------------------
# Fase 4 — A Auditoria Profunda. A corrida (`auditoria`) e o que ela achou
# (`achado`). `banco.py` so guarda: quem monta o achado pronto (id, regra,
# categoria...) e `servir.py`, depois de `auditoria.validar()` — este modulo
# nao importa `auditoria`, de proposito (ver spec: quem importa e servir.py e
# regras.py, nunca banco.py).
# ---------------------------------------------------------------------------


def gravar_auditoria(usuario_id: int, projeto: str, estado: str, achados: list,
                     *, tarefa_id: str = "", motivo: str = "",
                     custo_usd: float = 0.0, rodadas: int = 0,
                     agora_iso: str = "", con=None) -> int:
    """Grava a corrida e os achados NUMA UNICA TRANSACAO. Devolve o id da
    auditoria.

    Corrida `'ok'`: cada achado da lista e gravado — o que reaparece mantem o
    `visto_em` mais antigo e perde o `fechado_em` se estava fechado — e todo
    achado deste projeto que NAO esta na lista ganha `fechado_em`. NUNCA
    `DELETE`: o historico nao pode mentir.

    Corrida `'falha'` ou `'recusada'`: so a linha da corrida e gravada. Os
    achados da corrida anterior continuam de pe, exatamente como estavam — uma
    auditoria que falhou nao pode apagar o que a anterior encontrou.

    TUDO OU NADA: se a gravacao de qualquer achado falhar no meio do laco, a
    transacao inteira desfaz — nunca 39 de 60 achados na tabela.
    """
    if estado not in ("ok", "falha", "recusada"):
        raise ValueError("estado de auditoria desconhecido: %r" % (estado,))
    achados = achados or []
    fechar = con is None
    con = con or conectar()
    quando = agora_iso or agora()
    propria = not con.in_transaction
    try:
        if propria:
            con.execute("BEGIN IMMEDIATE")
        arquivos = {str(a.get("arquivo") or "") for a in achados}
        cur = con.execute(
            "INSERT INTO auditoria (usuario_id, projeto, tarefa_id, estado,"
            " motivo, achados_n, arquivos_n, custo_usd, rodadas, medido_em)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (usuario_id, projeto, tarefa_id or None, estado, motivo or "",
             len(achados), len(arquivos), float(custo_usd or 0.0),
             int(rodadas or 0), quando))
        auditoria_id = cur.lastrowid
        presentes = []
        for a in achados:
            aid = str(a.get("id") or "")
            if not aid:
                # NAO pular em silencio. `achados_n` acima ja contou este
                # achado; pular aqui gravaria uma corrida dizendo "3 achados"
                # com zero linhas na tabela — o numero errado com cara de
                # certo que a lei 2 deste repositorio proibe, e que na tela
                # vira um contador que nao abre nada.
                #
                # Quem chama (`servir._resultado`) carimba o id com
                # `auditoria.id_do_achado` antes de chegar aqui. Se um dia
                # esquecer, isto tem de estourar dentro da transacao — e o
                # `except` abaixo desfaz a corrida inteira.
                raise ValueError(
                    "achado sem id chegou a gravar_auditoria: %r" % (a,))
            presentes.append(aid)
            con.execute(
                "INSERT INTO achado (id, auditoria_id, usuario_id, projeto,"
                " regra, categoria, arquivo, linha, gravidade, frase,"
                " o_que_fazer, trecho, visto_em, fechado_em)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)"
                " ON CONFLICT(id, usuario_id) DO UPDATE SET"
                "   auditoria_id = excluded.auditoria_id,"
                "   projeto = excluded.projeto,"
                "   regra = excluded.regra,"
                "   categoria = excluded.categoria,"
                "   arquivo = excluded.arquivo,"
                "   linha = excluded.linha,"
                "   gravidade = excluded.gravidade,"
                "   frase = excluded.frase,"
                "   o_que_fazer = excluded.o_que_fazer,"
                "   trecho = excluded.trecho,"
                "   fechado_em = NULL",
                # `visto_em` NAO entra no SET do ON CONFLICT: e o que faz o
                # achado que reaparece manter o carimbo mais antigo.
                # `usuario_id` TAMBEM nao entra: a chave e (id, usuario_id),
                # entao um upsert so casa dentro do MESMO dono — mas mesmo
                # assim o dono nunca deve mudar por upsert, de proposito.
                (aid, auditoria_id, usuario_id, projeto,
                 str(a.get("regra") or ""), str(a.get("categoria") or ""),
                 str(a.get("arquivo") or ""), a.get("linha"),
                 str(a.get("gravidade") or "media"), str(a.get("frase") or ""),
                 str(a.get("o_que_fazer") or ""), str(a.get("trecho") or ""),
                 quando))
        if estado == "ok":
            _fechar_ausentes(con, usuario_id, projeto, presentes, quando)
        if propria:
            con.commit()
        return auditoria_id
    except Exception:
        if propria:
            con.rollback()
        raise
    finally:
        if fechar:
            con.close()


def _fechar_ausentes(con, usuario_id, projeto, presentes, quando) -> int:
    """O miolo de `fechar_achados_ausentes`, reusado por `gravar_auditoria`
    para fechar dentro da MESMA transacao."""
    if presentes:
        marcas = ",".join("?" * len(presentes))
        cur = con.execute(
            "UPDATE achado SET fechado_em = ?"
            " WHERE usuario_id = ? AND projeto = ? AND fechado_em IS NULL"
            "   AND id NOT IN (%s)" % marcas,
            [quando, usuario_id, projeto] + presentes)
    else:
        cur = con.execute(
            "UPDATE achado SET fechado_em = ?"
            " WHERE usuario_id = ? AND projeto = ? AND fechado_em IS NULL",
            (quando, usuario_id, projeto))
    return cur.rowcount or 0


def fechar_achados_ausentes(usuario_id: int, projeto: str, presentes_ids: list,
                            agora_iso: str = "", con=None) -> int:
    """Marca `fechado_em` nos achados abertos deste projeto que NAO estao em
    `presentes_ids`. NUNCA `DELETE` — devolve quantos fechou.

    Funcao publica, para quem precisar fechar fora de `gravar_auditoria` (por
    exemplo, um projeto desligado da auditoria). `gravar_auditoria` usa o
    miolo `_fechar_ausentes` para ficar na MESMA transacao da gravacao.
    """
    fechar = con is None
    con = con or conectar()
    quando = agora_iso or agora()
    try:
        n = _fechar_ausentes(con, usuario_id, projeto, list(presentes_ids or []),
                             quando)
        con.commit()
        return n
    finally:
        if fechar:
            con.close()


def auditoria_do_projeto(usuario_id: int, projeto: str, con=None):
    """A corrida mais recente deste projeto, ou `None` se ele nunca foi
    auditado. `None`, e nunca `{}` — lei 2 deste repositorio."""
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute(
            "SELECT * FROM auditoria WHERE usuario_id = ? AND projeto = ?"
            " ORDER BY medido_em DESC, id DESC LIMIT 1",
            (usuario_id, projeto)).fetchone()
        return dict(l) if l else None
    finally:
        if fechar:
            con.close()


def achados_do_projeto(usuario_id: int, projeto: str, con=None,
                       incluir_fechados: bool = False) -> list:
    """Os achados deste projeto — so os abertos, salvo `incluir_fechados`."""
    fechar = con is None
    con = con or conectar()
    try:
        sql = "SELECT * FROM achado WHERE usuario_id = ? AND projeto = ?"
        if not incluir_fechados:
            sql += " AND fechado_em IS NULL"
        sql += " ORDER BY visto_em DESC"
        return [dict(l) for l in con.execute(sql, (usuario_id, projeto))]
    finally:
        if fechar:
            con.close()


def aprovar_tarefa(tarefa_id: str, usuario_id: int, agora_iso: str = "",
                   con=None) -> bool:
    """O clique do dono numa tarefa vermelha. `True` se ESTE clique aprovou.

    Aprovar duas vezes devolve `False` na segunda — nao e erro, e a resposta
    honesta: nada mudou. E tarefa que ja terminou nao se aprova.

    `usuario_id` entra TAMBEM no WHERE, e nao so no `SET aprovado_por`: sem
    essa condicao, qualquer conta logada que adivinhasse o id (previsivel,
    `regra:projeto`) aprovava a tarefa vermelha de outra conta e disparava
    uma sessao de IA na maquina dela.
    """
    fechar = con is None
    con = con or conectar()
    quando = agora_iso or agora()
    try:
        cur = con.execute(
            "UPDATE fila SET aprovado_por = ?, aprovado_em = ?,"
            "   estado = 'esperando'"
            " WHERE id = ? AND usuario_id = ? AND aprovado_em IS NULL"
            "   AND estado IN ('esperando', 'aguardando_aprovacao')",
            (usuario_id, quando, tarefa_id, usuario_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        if fechar:
            con.close()


def pedir_parada(tarefa_id: str, usuario_id: int, agora_iso: str = "",
                 con=None) -> bool:
    """Marca o pedido de parada. `True` se havia o que parar.

    Isto NAO para nada sozinho: so escreve o pedido. Quem para e o agente,
    quando ler a resposta do proximo progresso — ate 5 segundos depois, mais o
    tempo de matar a arvore de processos. A tela tem de dizer isso.

    `usuario_id` no WHERE: sem ele, `_tarefa_parar` nem recebia o usuario, e
    qualquer conta logada parava a sessao de qualquer outra.
    """
    fechar = con is None
    con = con or conectar()
    quando = agora_iso or agora()
    try:
        cur = con.execute(
            "UPDATE fila SET parada_pedida_em = ?"
            " WHERE id = ? AND usuario_id = ? AND parada_pedida_em IS NULL"
            "   AND estado IN ('esperando', 'aguardando_aprovacao', 'rodando')",
            (quando, tarefa_id, usuario_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        if fechar:
            con.close()


def repintar_regra(regra: str, cor: str, por: int = None, agora_iso: str = "",
                   con=None) -> bool:
    """O dono pinta uma regra de verde ou de vermelho. `True` se pintou.

    A recusa de `tarefas.NUNCA_VERDE` e conferida AQUI TAMBEM, e nao so na
    rota. Duas travas para a mesma coisa e de proposito: a rota e o caminho
    esperado, e esta e a que sobra se alguem inventar um segundo caminho.
    """
    nome = (regra or "").strip()
    if not tarefas.pode_repintar(nome, cor):
        return False
    fechar = con is None
    con = con or conectar()
    try:
        con.execute(
            "INSERT INTO cor_da_regra (regra, cor, por, quando)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(regra) DO UPDATE SET cor = excluded.cor,"
            "   por = excluded.por, quando = excluded.quando",
            (nome, cor, por, agora_iso or agora()))
        con.commit()
        return True
    finally:
        if fechar:
            con.close()


def cores_das_regras(con=None) -> dict:
    """{regra: cor} do que foi REPINTADO. O que nao esta aqui e vermelho.

    Uma cor invalida que tenha entrado no banco por outro caminho e descartada
    na leitura: preferimos perder a repintura a devolver algo que
    `tarefas.cor_da_regra` interpretaria como aberto.
    """
    fechar = con is None
    con = con or conectar()
    try:
        fora = {}
        for l in con.execute("SELECT regra, cor FROM cor_da_regra"):
            if l["cor"] in tarefas.CORES:
                fora[l["regra"]] = l["cor"]
        return fora
    finally:
        if fechar:
            con.close()


def linhas_da_tarefa(tarefa_id: str, desde: int = 0, limite: int = 500,
                     con=None) -> list:
    """As linhas da sessao a partir de `desde` (exclusivo), em ordem.

    O `limite` existe porque isto alimenta o fluxo ao vivo, que le de segundo
    em segundo: sem teto, uma sessao de mil linhas mandaria mil linhas a cada
    volta para quem acabou de abrir a tela.
    """
    fechar = con is None
    con = con or conectar()
    try:
        linhas = con.execute(
            "SELECT n, texto, quando FROM tarefa_linha"
            " WHERE tarefa_id = ? AND n > ? ORDER BY n LIMIT ?",
            (tarefa_id, int(desde or 0), int(limite))).fetchall()
        return [dict(l) for l in linhas]
    finally:
        if fechar:
            con.close()


def tarefas_sem_noticia(limite_min: int, agora_iso: str = "", con=None) -> list:
    """As tarefas `rodando` que pararam de dar noticia. So LE.

    `agora_iso` e obrigatorio na pratica: teste com data fixa que nao o passa
    passa hoje e fica vermelho sozinho amanha, sem ninguem tocar em nada.
    """
    agora_dt = agora_iso or agora()
    try:
        corte = (datetime.fromisoformat(agora_dt)
                 - timedelta(minutes=int(limite_min))).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return []
    fechar = con is None
    con = con or conectar()
    try:
        linhas = con.execute(
            "SELECT * FROM fila"
            " WHERE estado = 'rodando'"
            "   AND COALESCE(visto_em, iniciado_em, criado_em) < ?"
            " ORDER BY criado_em", (corte,)).fetchall()
        return [dict(l) for l in linhas]
    finally:
        if fechar:
            con.close()


def tarefas_do_painel(usuario_id: int, limite: int = 50, con=None) -> list:
    """O que a tela mostra: as tarefas mais recentes DESTA CONTA, novas primeiro.

    Sem o `diff` cru — ele pode ter dezenas de milhares de caracteres e a lista
    e carregada a cada abertura de tela. Quem quer o diff pede a tarefa.

    Sem o filtro por `usuario_id`, a lista do painel mostrava a fila inteira,
    de todas as contas — achado da auditoria de 03/09/2026.
    """
    fechar = con is None
    con = con or conectar()
    try:
        linhas = con.execute(
            "SELECT id, projeto, regra, gravidade, trilho, estado, cor,"
            "       tentativas, criado_em, iniciado_em, terminado_em,"
            "       custo_usd, rodadas, ramo, resumo, frase, visto_em,"
            "       aprovado_em, parada_pedida_em, maquina_id, executor, erro"
            "  FROM fila WHERE usuario_id = ? ORDER BY criado_em DESC LIMIT ?",
            (int(usuario_id), int(limite))).fetchall()
        return [dict(l) for l in linhas]
    finally:
        if fechar:
            con.close()


def tarefa(tarefa_id: str, usuario_id=None, con=None):
    """Uma tarefa inteira, com o diff. `None` se nao existe (ou nao e sua).

    `usuario_id` e OPCIONAL de proposito: as duas pontas internas —
    `_resultado` (ja provou o dono pela maquina, via `registrar_desfecho`) e o
    laco de progresso da propria maquina — nao tem uma sessao para passar.
    Toda rota alcancada por SESSAO (`_tarefas`, `_eventos`) tem de passar o
    `usuario_id` dela: "nao existe" e "nao e sua" devolvem a MESMA resposta,
    para nao revelar qual id pertence a outra conta.
    """
    fechar = con is None
    con = con or conectar()
    try:
        if usuario_id is None:
            l = con.execute("SELECT * FROM fila WHERE id = ?",
                            (tarefa_id,)).fetchone()
        else:
            l = con.execute(
                "SELECT * FROM fila WHERE id = ? AND usuario_id = ?",
                (tarefa_id, int(usuario_id))).fetchone()
        return dict(l) if l else None
    finally:
        if fechar:
            con.close()


def ligar_execucao(maquina_id: int, usuario_id: int, ligado: bool,
                   con=None) -> bool:
    """Autoriza (ou desautoriza) esta maquina a executar tarefas.

    O `usuario_id` no `WHERE` nao e enfeite: sem ele, uma conta ligaria a
    execucao na maquina da outra.
    """
    fechar = con is None
    con = con or conectar()
    try:
        cur = con.execute(
            "UPDATE maquina SET executa = ?"
            " WHERE id = ? AND usuario_id = ? AND revogada_em IS NULL",
            (1 if ligado else 0, maquina_id, usuario_id))
        con.commit()
        return cur.rowcount == 1
    finally:
        if fechar:
            con.close()


# Quantos dias a tela mostra por padrao. Sete porque foi o prazo que o dono
# deu a si mesmo em 28/08/2026 para observar antes de decidir sobre freio de
# horario. O numero e daqui, e nao da rota, para a tela e o teste nao
# discordarem sobre o que e "esta semana".
DIAS_DE_CONSUMO = 7


def consumo(desde_iso: str = "", ate_iso: str = "", dias: int = DIAS_DE_CONSUMO,
            agora_iso: str = "", con=None) -> dict:
    """Quanto o painel trabalhou na janela. Por dia LOCAL, projeto e regra.

    O recurso escasso e COTA, nao dinheiro: com assinatura, o que acaba sao
    sessoes e rodadas. O custo em reais entra como referencia, rotulado como
    tal, e nunca como o numero principal (§13 da fonte unica).

    Semana sem nenhuma sessao devolve ZEROS mais o carimbo — e nao um corpo
    vazio. "Nao sei" e "zero" sao estados diferentes, e o carimbo e o que
    permite a tela distinguir os dois.

    A agregacao e por DIA LOCAL, e nao por UTC. Em UTC-3, as 21h de terca ja e
    quarta em UTC: agrupar pelo carimbo cru jogaria as noites do dono para o
    dia seguinte, e o grafico mentiria em toda madrugada.
    """
    agora_dt = agora_iso or agora()
    if not ate_iso:
        ate_iso = agora_dt
    if not desde_iso:
        try:
            base = datetime.fromisoformat(ate_iso)
        except (TypeError, ValueError):
            base = datetime.now(timezone.utc)
        desde_iso = (base - timedelta(days=int(dias))).isoformat(
            timespec="seconds")

    fechar = con is None
    con = con or conectar()
    try:
        linhas = con.execute(
            "SELECT projeto, regra, estado, iniciado_em, terminado_em,"
            "       custo_usd, rodadas, criado_em"
            "  FROM fila"
            " WHERE COALESCE(terminado_em, iniciado_em, criado_em) >= ?"
            "   AND COALESCE(terminado_em, iniciado_em, criado_em) < ?",
            (desde_iso, ate_iso)).fetchall()
    finally:
        if fechar:
            con.close()

    por_dia, por_projeto, por_regra = {}, {}, {}
    total = _balde()
    for l in linhas:
        carimbo = l["terminado_em"] or l["iniciado_em"] or l["criado_em"]
        dia = tarefas.dia_local_de(carimbo) or "sem data"
        for balde in (por_dia.setdefault(dia, _balde()),
                      por_projeto.setdefault(l["projeto"] or "(sem projeto)",
                                             _balde()),
                      por_regra.setdefault(l["regra"] or "(sem regra)",
                                           _balde()),
                      total):
            _somar(balde, l)

    return {
        "desde": desde_iso, "ate": ate_iso, "dias": dias,
        "por_dia": [dict(dia=d, **por_dia[d]) for d in sorted(por_dia)],
        "por_projeto": [dict(projeto=p, **por_projeto[p])
                        for p in sorted(por_projeto)],
        "por_regra": [dict(regra=r, **por_regra[r]) for r in sorted(por_regra)],
        "total": total,
        # O CARIMBO. Sem ele, uma tela de zeros e indistinguivel de uma tela
        # que nao conseguiu medir — e zerar o que nao deu para reler apaga um
        # problema real.
        "medido_em": agora_dt,
    }


def _balde() -> dict:
    return {"sessoes": 0, "rodadas": 0, "segundos": 0, "custo_usd": 0.0,
            "ok": 0, "falhas": 0}


def _somar(balde: dict, l) -> None:
    balde["sessoes"] += 1
    balde["rodadas"] += int(l["rodadas"] or 0)
    balde["custo_usd"] += float(l["custo_usd"] or 0.0)
    if l["estado"] == "ok":
        balde["ok"] += 1
    elif l["estado"] == "falha":
        balde["falhas"] += 1
    if l["iniciado_em"] and l["terminado_em"]:
        try:
            balde["segundos"] += int(
                (datetime.fromisoformat(l["terminado_em"])
                 - datetime.fromisoformat(l["iniciado_em"])).total_seconds())
        except (TypeError, ValueError):
            pass


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


def usuario_por_email(email: str, con=None, *, incluir_desativados=False):
    """Por padrao SO conta ativa: quem pergunta e caminho de entrada, e conta
    desativada nao entra.

    `incluir_desativados=True` existe para UM caso, e ele e administrativo:
    `autenticacao.remover` precisa achar a conta que quer apagar. Sem isso o
    comando respondia "nao ha conta com este e-mail" para uma conta que existe
    — mentira com cara de verdade, e a conta desativada ficava impossivel de
    apagar. NAO use isto em caminho de login.
    """
    fechar = con is None
    con = con or conectar()
    filtro = "" if incluir_desativados else " AND desativado_em IS NULL"
    try:
        l = con.execute(
            "SELECT %s FROM usuario WHERE email = ?%s"
            % (", ".join(COLUNAS_USUARIO), filtro),
            (_normalizar_email(email),)).fetchone()
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


def limpar_pareamentos_vencidos(con=None) -> int:
    """Apaga os codigos que ja venceram. Devolve quantos sairam.

    POR QUE ISTO PRECISOU EXISTIR: `codigo_hash` e PRIMARY KEY GLOBAL, e ate
    aqui nenhuma linha era apagada nunca. Seis digitos sao um milhao de vagas
    para TODAS as contas juntas; quem gerasse codigos em laco enchia o espaco, e
    o laco de cinco tentativas de todo mundo — inclusive o do dono — passava a
    colidir e devolver "tente de novo em um minuto", para sempre.

    E o "teto compartilhado tranca o dono" pela terceira vez nesta casa, agora
    pelo ESPACO em vez do contador. Achado pela revisao de seguranca de
    01/09/2026.

    Codigo vencido nao serve para nada: `usar_pareamento` ja o recusa pela data.
    """
    fechar = con is None
    con = con or conectar()
    try:
        cursor = con.execute("DELETE FROM pareamento WHERE expira_em < ?",
                             (agora(),))
        if fechar:
            con.commit()
        return cursor.rowcount or 0
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
            "SELECT m.id, m.nome, m.criado_em, m.visto_em, m.executa,"
            "       (SELECT COUNT(*) FROM projeto_conectado p"
            "         WHERE p.maquina_id = m.id AND p.arquivado_em IS NULL)"
            "       AS projetos"
            "  FROM maquina m"
            " WHERE m.usuario_id = ? AND m.revogada_em IS NULL"
            " ORDER BY m.criado_em", (usuario_id,))]
    finally:
        if fechar:
            con.close()


# ---------------------------------------------------------- a ponte com o VOZ
#
# O servidor so guarda e entrega. Nada aqui executa, e nada aqui carimba
# `maquina.visto_em`: a vigilia e o relatorio, nunca o estado do VOZ.

# Acima disto a maquina e "sem dados" — o dobro do intervalo de coleta (600 s).
VIGILIA_LIMITE_S = 1200
VOZ_CEREBROS = ("claude_code", "hermes", "jev")
VOZ_CEREBRO_ATIVO = ("claude_code", "hermes", "jev_triagem")
# `jev` tambem responde como autor de um resultado: e ele que classifica.
VOZ_CEREBRO_RESULTADO = VOZ_CEREBRO_ATIVO + ("jev",)
VOZ_ESTADOS_FINAIS = ("feito", "recusado", "falhou")
VOZ_ESTADOS_DE_RESULTADO = VOZ_ESTADOS_FINAIS + ("aguardando_clique",)


def _segundos_desde(iso, agora_iso: str):
    """Segundos entre `iso` e `agora_iso`, ou None se nao der para saber."""
    try:
        t = datetime.fromisoformat(iso)
        a = datetime.fromisoformat(agora_iso)
        if t.tzinfo is None or a.tzinfo is None:
            return None
        return max(0, int((a - t).total_seconds()))
    except (TypeError, ValueError):
        return None


def guardar_voz_estado(maquina_id: int, usuario_id: int, dados: dict,
                       agora_iso: str = None, con=None) -> None:
    """Guarda o ULTIMO estado do VOZ daquela maquina. Nao toca `visto_em`."""
    fechar = con is None
    con = con or conectar()
    try:
        con.execute(
            "INSERT INTO voz_estado (maquina_id, usuario_id, recebido_em, dados)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(maquina_id) DO UPDATE SET"
            "   recebido_em = excluded.recebido_em, dados = excluded.dados",
            (maquina_id, usuario_id, agora_iso or agora(),
             json.dumps(dados, ensure_ascii=False)))
        con.commit()
    finally:
        if fechar:
            con.close()


def criar_voz_recado(usuario_id: int, maquina_id: int, tipo: str, alvo: str,
                     texto: str, nivel: str, cerebro_pedido: str,
                     teto_pendentes: int, agora_iso: str = None, con=None):
    """Enfileira um recado. `(id, None)` se entrou; `(None, motivo)` se nao.

    Motivos: `"sem_maquina"` (nao existe, e de outra conta ou foi revogada — a
    MESMA resposta para as tres) e `"teto"` (pendentes demais). A conferencia
    de dono e a contagem estao na mesma transacao que o INSERT.
    """
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        id_, motivo = _inserir_voz_recado(
            con, usuario_id, maquina_id, tipo, alvo, texto, nivel,
            cerebro_pedido, teto_pendentes, agora_iso)
        if motivo is not None:
            con.rollback()
        else:
            con.commit()
        return id_, motivo
    finally:
        if fechar:
            con.close()


def _inserir_voz_recado(con, usuario_id, maquina_id, tipo, alvo, texto, nivel,
                        cerebro_pedido, teto_pendentes, agora_iso):
    """O miolo de `criar_voz_recado`, DENTRO de uma transacao que o chamador
    abriu e fecha (commit se `motivo` for None, rollback se nao)."""
    # `avisar` e o painel falando com o dono: nunca muda nada.
    if tipo == "avisar" and nivel != "leitura":
        return None, "nivel"
    if con.execute(
            "SELECT 1 FROM maquina WHERE id = ? AND usuario_id = ?"
            " AND revogada_em IS NULL", (maquina_id, usuario_id)
    ).fetchone() is None:
        return None, "sem_maquina"
    # Recado que ninguem buscou em 24 h nao e pendencia, e estado que nunca
    # expira tranca o dono (PC desligado ou revogado = teto cheio para sempre).
    # Em UTC: `criado_em` e comparado como texto, e so vale com o mesmo fuso.
    limite = (datetime.fromisoformat(agora_iso or agora())
              .astimezone(timezone.utc)
              - timedelta(hours=24)).isoformat(timespec="seconds")
    con.execute(
        "UPDATE voz_recado SET estado = 'falhou', terminado_em = ?,"
        " resumo = 'Venceu: o DERVS-VOZ nao buscou este recado em 24 horas.'"
        " WHERE usuario_id = ? AND estado = 'pendente' AND criado_em < ?",
        (agora_iso or agora(), usuario_id, limite))
    # So conta recado de computador vivo: o de um revogado nunca sera buscado.
    # E os avisos do painel tem o PROPRIO teto: uma fila de avisos nao pode
    # trancar o dono para mandar recado, nem o contrario.
    pendentes = con.execute(
        "SELECT COUNT(*) FROM voz_recado r JOIN maquina m ON m.id = r.maquina_id"
        " WHERE r.usuario_id = ? AND r.estado = 'pendente'"
        " AND m.revogada_em IS NULL AND (r.tipo = 'avisar') = ?",
        (usuario_id, 1 if tipo == "avisar" else 0)).fetchone()[0]
    if pendentes >= teto_pendentes:
        return None, "teto"
    id_ = str(uuid.uuid4())
    con.execute(
        "INSERT INTO voz_recado (id, usuario_id, maquina_id, criado_em,"
        " tipo, alvo, texto, nivel, cerebro_pedido)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (id_, usuario_id, maquina_id, agora_iso or agora(), tipo, alvo,
         texto, nivel, cerebro_pedido))
    return id_, None


def avisar_uma_vez(usuario_id: int, maquina_id_do_voz: int, chave: str,
                   alvo: str, texto: str, agora_iso: str = None, con=None,
                   teto_pendentes: int = 20) -> bool:
    """Um aviso do painel por OCORRENCIA. True se criou, False se ja existia
    (ou se nao coube: maquina de outro dono, teto de pendentes).

    A chave e o recado entram na MESMA transacao: recado que nao coube desfaz
    a chave tambem, e a proxima varredura tenta de novo. `nivel` e sempre
    `leitura` — o painel avisa, nunca pede que o VOZ mude algo.
    """
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        novo = con.execute(
            "INSERT OR IGNORE INTO voz_aviso (usuario_id, chave, criado_em)"
            " VALUES (?,?,?)", (usuario_id, chave, agora_iso or agora())
        ).rowcount == 1
        if not novo:
            con.rollback()
            return False
        _id, motivo = _inserir_voz_recado(
            con, usuario_id, maquina_id_do_voz, "avisar", alvo, texto,
            "leitura", "auto", teto_pendentes, agora_iso)
        if motivo is not None:
            con.rollback()
            return False
        con.commit()
        return True
    finally:
        if fechar:
            con.close()


def voz_destinos_de_aviso(agora_iso: str, con=None) -> dict:
    """`{usuario_id: maquina_id}`: para cada conta, o computador vivo (nao
    revogado) cujo estado do VOZ e FRESCO — o mais recente se houver varios.
    Conta sem VOZ fresco nao aparece: aviso que ninguem ouve nao se acumula."""
    fechar = con is None
    con = con or conectar()
    try:
        destinos, recebido = {}, {}
        for l in con.execute(
                "SELECT e.usuario_id, e.maquina_id, e.recebido_em"
                "  FROM voz_estado e JOIN maquina m ON m.id = e.maquina_id"
                "   AND m.usuario_id = e.usuario_id"
                " WHERE m.revogada_em IS NULL"):
            idade = _segundos_desde(l["recebido_em"], agora_iso)
            if idade is None or idade > VIGILIA_LIMITE_S:
                continue
            uid = l["usuario_id"]
            if uid not in destinos or idade < recebido[uid]:
                destinos[uid], recebido[uid] = l["maquina_id"], idade
        return destinos
    finally:
        if fechar:
            con.close()


def maquinas_que_calaram(usuario_id: int, agora_iso: str, con=None) -> list:
    """Computadores vivos da conta que JA mediram e pararam de medir ha mais de
    `VIGILIA_LIMITE_S`: `[{maquina_id, nome, visto_em, atraso_s}]`. Quem nunca
    mediu (`visto_em` nulo) ou tem carimbo ilegivel nao entra: nao ha "parou"
    sem um "mediu"."""
    fechar = con is None
    con = con or conectar()
    try:
        achadas = []
        for m in con.execute(
                "SELECT id, nome, visto_em FROM maquina"
                " WHERE usuario_id = ? AND revogada_em IS NULL"
                "   AND visto_em IS NOT NULL ORDER BY id", (usuario_id,)):
            atraso = _segundos_desde(m["visto_em"], agora_iso)
            if atraso is not None and atraso > VIGILIA_LIMITE_S:
                achadas.append({"maquina_id": m["id"], "nome": m["nome"],
                                "visto_em": m["visto_em"], "atraso_s": atraso})
        return achadas
    finally:
        if fechar:
            con.close()


def entregar_voz_recados(maquina_id: int, usuario_id: int, limite: int = 10,
                         con=None) -> list:
    """Os recados pendentes DESTA maquina (no maximo `limite`), ja marcados
    `entregue`. Quem chama recebe cada recado uma vez so."""
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        linhas = [dict(l) for l in con.execute(
            "SELECT id, criado_em, tipo, alvo, texto, nivel, cerebro_pedido"
            "  FROM voz_recado WHERE maquina_id = ? AND usuario_id = ?"
            "   AND estado = 'pendente' ORDER BY criado_em, rowid LIMIT ?",
            (maquina_id, usuario_id, limite))]
        for l in linhas:
            con.execute("UPDATE voz_recado SET estado = 'entregue'"
                        " WHERE id = ? AND estado = 'pendente'", (l["id"],))
        con.commit()
        return linhas
    finally:
        if fechar:
            con.close()


def registrar_voz_resultado(id_: str, maquina_id: int, usuario_id: int,
                            cerebro: str, estado: str, resumo: str,
                            custo_usd: float, duracao_s: float,
                            terminado_em: str, con=None) -> bool:
    """Grava a resposta do VOZ. False se o recado nao e desta maquina e dono.

    IDEMPOTENTE: recado em estado final (`feito`, `recusado`, `falhou`) nao e
    sobrescrito — o repetido devolve True sem mudar nada. `aguardando_clique`
    ainda pode virar `feito`.
    """
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        achou = con.execute(
            "SELECT estado FROM voz_recado WHERE id = ? AND maquina_id = ?"
            " AND usuario_id = ?", (id_, maquina_id, usuario_id)).fetchone()
        if achou is None:
            con.rollback()
            return False
        if achou["estado"] not in VOZ_ESTADOS_FINAIS:
            con.execute(
                "UPDATE voz_recado SET estado = ?, cerebro = ?, resumo = ?,"
                " custo_usd = ?, duracao_s = ?, terminado_em = ?"
                " WHERE id = ? AND maquina_id = ? AND usuario_id = ?",
                (estado, cerebro, resumo, custo_usd, duracao_s, terminado_em,
                 id_, maquina_id, usuario_id))
        con.commit()
        return True
    finally:
        if fechar:
            con.close()


def voz_do_usuario(usuario_id: int, agora_iso: str = None, con=None) -> dict:
    """O que o painel mostra da ponte: maquinas vivas da conta e 20 recados.

    LEI 2: `vigilia` so diz `viva` quando ha `visto_em` de ate
    `VIGILIA_LIMITE_S`. Sem carimbo, ou carimbo velho, ou carimbo ilegivel, e
    `sem_dados` — nunca um verde sem dado e nunca um "morta" inventado.
    `fresco` do estado segue a mesma regra sobre `recebido_em`.
    """
    agora_iso = agora_iso or agora()
    fechar = con is None
    con = con or conectar()
    try:
        maquinas = []
        for m in con.execute(
                "SELECT m.id, m.nome, m.visto_em, e.recebido_em, e.dados"
                "  FROM maquina m LEFT JOIN voz_estado e"
                "    ON e.maquina_id = m.id AND e.usuario_id = m.usuario_id"
                " WHERE m.usuario_id = ? AND m.revogada_em IS NULL"
                " ORDER BY m.criado_em, m.id", (usuario_id,)):
            atraso = _segundos_desde(m["visto_em"], agora_iso)
            estado = None
            if m["recebido_em"] is not None:
                try:
                    d = json.loads(m["dados"])
                except ValueError:
                    d = None
                if isinstance(d, dict):
                    idade = _segundos_desde(m["recebido_em"], agora_iso)
                    estado = {
                        "recebido_em": m["recebido_em"],
                        "cerebro_ativo": d.get("cerebro_ativo"),
                        "cerebros": d.get("cerebros"),
                        "gasto_dia_usd": d.get("gasto_dia_usd"),
                        "fresco": idade is not None and idade <= VIGILIA_LIMITE_S,
                    }
            maquinas.append({
                "maquina_id": m["id"], "nome": m["nome"],
                "visto_em": m["visto_em"], "atraso_s": atraso,
                "vigilia": ("viva" if atraso is not None
                            and atraso <= VIGILIA_LIMITE_S else "sem_dados"),
                "estado": estado})
        recados = [dict(l) for l in con.execute(
            "SELECT id, criado_em, maquina_id, tipo, alvo, nivel,"
            "       cerebro_pedido, estado, cerebro, resumo, custo_usd,"
            "       terminado_em"
            "  FROM voz_recado WHERE usuario_id = ?"
            " ORDER BY criado_em DESC, rowid DESC LIMIT 20", (usuario_id,))]
        return {"maquinas": maquinas, "recados": recados}
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


# Sem teto TOTAL de servidores, so o teto de VELOCIDADE do balcao por origem
# (na rota) limitaria a criacao. `_servidor_sugerir` varre `servidores()`
# inteiro e mede ate 3 candidatos por chamada — sem um teto total essa lista
# cresceria sem fim e a rota de sugestao ficaria mais lenta a cada servidor
# cadastrado.
MAX_SERVIDORES_POR_CONTA = 20


def servidores(usuario_id: int, con=None) -> list:
    """[{"id","nome","padrao_subdominio","criado_em"}] de UMA conta, ordenado
    por nome.

    `padrao_subdominio` sai como veio do banco — `None` quando nao ha padrao.
    A conversao para `""` mora na borda do JSON, na rota: o banco tem um jeito
    so de dizer "nenhum", e o JSON tem outro, e a troca acontece num lugar so.
    """
    fechar = con is None
    con = con or conectar()
    try:
        return [dict(l) for l in con.execute(
            "SELECT id, nome, padrao_subdominio, criado_em FROM servidor"
            " WHERE usuario_id = ? ORDER BY nome", (usuario_id,))]
    finally:
        if fechar:
            con.close()


def guardar_servidor(usuario_id: int, nome: str, padrao_subdominio=None,
                     con=None):
    """Cria um servidor nomeado. Devolve o `id`, ou `None` quando o nome
    colide com outro da MESMA conta, fica vazio depois do `strip`, ou a conta
    ja tem `MAX_SERVIDORES_POR_CONTA` servidores.

    `padrao_subdominio` tem UM jeito so de dizer "nenhum": `""` e espacos
    puros viram `None` aqui, antes de chegar ao banco — nunca grava string
    vazia.

    A checagem de nome repetido e feita por `SELECT` antes do `INSERT`, e nao
    por capturar `IntegrityError` do `UNIQUE`: um erro cru levantado no meio
    de um caminho que grava dado de conta seria dificil de distinguir de um
    tropeco de verdade — o mesmo cuidado de `guardar_instalacao_do_github`.
    """
    fechar = con is None
    con = con or conectar()
    try:
        nome_limpo = (nome or "").strip()
        if not nome_limpo:
            return None
        padrao = (padrao_subdominio or "").strip() or None
        total = con.execute("SELECT COUNT(*) FROM servidor WHERE usuario_id = ?",
                            (usuario_id,)).fetchone()[0]
        if total >= MAX_SERVIDORES_POR_CONTA:
            return None
        ja = con.execute("SELECT 1 FROM servidor"
                         " WHERE usuario_id = ? AND nome = ?",
                         (usuario_id, nome_limpo)).fetchone()
        if ja:
            return None
        cur = con.execute(
            "INSERT INTO servidor (usuario_id, nome, padrao_subdominio, criado_em)"
            " VALUES (?,?,?,?)", (usuario_id, nome_limpo, padrao, agora()))
        if fechar:                    # ver `gravar`: nao quebre a transacao alheia
            con.commit()
        return cur.lastrowid
    finally:
        if fechar:
            con.close()


def remover_servidor(usuario_id: int, servidor_id: int, con=None) -> bool:
    """`DELETE ... WHERE id = ? AND usuario_id = ?`; devolve se apagou.

    O DONO NO `WHERE`, NAO NUM `if` ANTES — a licao das quatro portas da fila
    (04/09/2026): a camada que decide tem de ser a mesma que executa. Os
    enderecos daquele servidor vao junto por `ON DELETE CASCADE`.
    """
    fechar = con is None
    con = con or conectar()
    try:
        cur = con.execute("DELETE FROM servidor WHERE id = ? AND usuario_id = ?",
                          (servidor_id, usuario_id))
        if fechar:
            con.commit()
        return cur.rowcount > 0
    finally:
        if fechar:
            con.close()


def enderecos_por_servidor(usuario_id: int, con=None) -> dict:
    """{projeto: [{"servidor_id","servidor","url"}, ...]} de UMA conta, um
    item por servidor onde aquele projeto responde, ordenado pelo nome do
    servidor. E a resposta a "em quais servidores este projeto esta no ar".

    `usuario_id` e POSICIONAL E OBRIGATORIO — mesmo motivo de sempre: um
    padrao aqui seria o caminho pronto para uma rota esquecer o dono e ler o
    endereco de outra pessoa. O `WHERE endereco_producao.usuario_id = ?` e
    quem DECIDE a resposta; o `JOIN servidor` so traz o nome para exibir.
    """
    fechar = con is None
    con = con or conectar()
    try:
        por_projeto: dict = {}
        for l in con.execute(
                "SELECT ep.projeto AS projeto, ep.servidor_id AS servidor_id,"
                "       s.nome AS servidor, ep.url AS url"
                "  FROM endereco_producao ep"
                "  JOIN servidor s ON s.id = ep.servidor_id"
                "                 AND s.usuario_id = ep.usuario_id"
                " WHERE ep.usuario_id = ?"
                " ORDER BY s.nome, ep.projeto", (usuario_id,)):
            por_projeto.setdefault(l["projeto"], []).append({
                "servidor_id": l["servidor_id"],
                "servidor": l["servidor"],
                "url": l["url"],
            })
        return por_projeto
    finally:
        if fechar:
            con.close()


def enderecos_do_projeto(usuario_id: int, projeto: str, con=None) -> list:
    """[{"servidor_id","servidor","url"}, ...] de UM projeto DAQUELA conta,
    ordenado pelo nome do servidor. Substitui `endereco_de_producao`: um
    projeto pode responder em mais de um servidor ao mesmo tempo, e quem le
    precisa dos dois — nunca so o primeiro que um `SELECT` sem `servidor_id`
    trouxesse.
    """
    fechar = con is None
    con = con or conectar()
    try:
        return [{"servidor_id": l["servidor_id"], "servidor": l["servidor"],
                 "url": l["url"]}
                for l in con.execute(
                    "SELECT ep.servidor_id AS servidor_id, s.nome AS servidor,"
                    "       ep.url AS url"
                    "  FROM endereco_producao ep"
                    "  JOIN servidor s ON s.id = ep.servidor_id"
                    "                 AND s.usuario_id = ep.usuario_id"
                    " WHERE ep.usuario_id = ? AND ep.projeto = ?"
                    " ORDER BY s.nome", (usuario_id, projeto))]
    finally:
        if fechar:
            con.close()


def um_endereco_por_projeto(usuario_id: int, con=None) -> dict:
    """{projeto: url} de UMA conta — o endereco do servidor de MENOR NOME, e
    SO para a regua de prontidao do `casos.json` (`coletar.py:669`). Quem
    quer saber se o projeto esta no ar usa `enderecos_por_servidor` — esta
    aqui nao sabe responder isso: ela nao diz QUAL servidor, nem se ha mais de
    um, nem se algum deles esta fora do ar enquanto outro responde.
    """
    fechar = con is None
    con = con or conectar()
    try:
        # ORDER BY ... s.nome DESC: dentro de cada projeto, o dict comprehension
        # guarda o ULTIMO valor lido para a mesma chave — descendente faz o
        # servidor de MENOR nome ser o ultimo, e por isso o que sobrevive.
        return {l["projeto"]: l["url"] for l in con.execute(
            "SELECT ep.projeto AS projeto, ep.url AS url"
            "  FROM endereco_producao ep"
            "  JOIN servidor s ON s.id = ep.servidor_id"
            "                 AND s.usuario_id = ep.usuario_id"
            " WHERE ep.usuario_id = ?"
            " ORDER BY ep.projeto, s.nome DESC", (usuario_id,))}
    finally:
        if fechar:
            con.close()


def guardar_endereco_de_producao(usuario_id: int, servidor_id: int, projeto: str,
                                 url, con=None) -> bool:
    """Grava, troca ou APAGA o endereco de um projeto NAQUELE servidor daquela
    conta. Devolve se gravou.

    CONFERE QUE O SERVIDOR E DA CONTA antes de gravar, e falha fechada: um
    `servidor_id` de outra conta devolve `False` SEM TOCAR o banco — "nao e
    seu" responde igual a "nao existe", a mesma convencao das quatro portas
    da fila (04/09/2026).

    `url` vazia ou `None` apaga a linha, e nao grava string vazia: "sem
    endereco" tem um jeito so de ser dito neste banco — a ausencia da linha.
    Dois jeitos dariam dois caminhos de leitura, e um deles sempre e esquecido.

    NAO confere a URL. A peneira anti-SSRF mora em `coletar_github.url_segura`,
    e quem chama e que a aplica antes de chegar aqui: o banco nao alcanca a
    rede, e duplicar a peneira aqui criaria duas verdades que divergem em
    silencio — foi exatamente assim que um SSRF real passou.
    """
    fechar = con is None
    con = con or conectar()
    try:
        dono = con.execute("SELECT 1 FROM servidor"
                           " WHERE id = ? AND usuario_id = ?",
                           (servidor_id, usuario_id)).fetchone()
        if not dono:
            return False
        limpa = (url or "").strip()
        if not limpa:
            con.execute("DELETE FROM endereco_producao"
                        " WHERE usuario_id = ? AND servidor_id = ? AND projeto = ?",
                        (usuario_id, servidor_id, projeto))
        else:
            quando = agora()
            # O `criado_em` NAO entra no `DO UPDATE`: trocar o endereco nao
            # reescreve a data em que a conta declarou aquele projeto.
            con.execute(
                "INSERT INTO endereco_producao"
                " (usuario_id, servidor_id, projeto, url,"
                "  criado_em, atualizado_em)"
                " VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(usuario_id, servidor_id, projeto) DO UPDATE SET"
                " url=excluded.url, atualizado_em=excluded.atualizado_em",
                (usuario_id, servidor_id, projeto, limpa, quando, quando))
        if fechar:                    # ver `gravar`: nao quebre a transacao alheia
            con.commit()
        return True
    finally:
        if fechar:
            con.close()


def instalacao_do_github(usuario_id: int, con=None):
    """O `installation_id` DAQUELA conta, ou `None` se ela nao conectou.

    `usuario_id` e POSICIONAL E OBRIGATORIO, e nao um argumento com padrao —
    mesmo motivo de `enderecos_do_projeto`: um padrao aqui seria o caminho
    pronto para uma rota esquecer de passar o dono e agir com a instalacao de
    outra pessoa. Sem dono nao ha leitura.

    Devolve TEXT, e nao int: e um identificador, nao um numero de contar. Quem
    precisar dele numa URL ja o quer em texto.
    """
    fechar = con is None
    con = con or conectar()
    try:
        l = con.execute("SELECT installation_id FROM instalacao_github"
                        " WHERE usuario_id = ?", (usuario_id,)).fetchone()
        return l["installation_id"] if l else None
    finally:
        if fechar:
            con.close()


def instalacoes_do_github(con=None) -> dict:
    """{usuario_id: installation_id} de TODAS as contas — o que o coletor le.

    Esta e a unica leitura sem dono deste conjunto, e e de proposito: quem
    coleta roda por conta propria, sem sessao, e precisa saber em nome de quem
    falar com o GitHub. Toda outra leitura passa por `instalacao_do_github`.
    """
    fechar = con is None
    con = con or conectar()
    try:
        return {l["usuario_id"]: l["installation_id"] for l in con.execute(
            "SELECT usuario_id, installation_id FROM instalacao_github"
            " ORDER BY usuario_id")}
    finally:
        if fechar:
            con.close()


def guardar_instalacao_do_github(usuario_id: int, installation_id, con=None) -> None:
    """Grava ou troca a instalacao daquela conta. Vazio aqui e ERRO, nao apagar.

    A diferenca para `guardar_endereco_de_producao`, que apaga com string
    vazia: la o vazio vem de um campo de formulario que o dono limpou; aqui o
    valor vem do GitHub, e um vazio significa que o fluxo de instalar quebrou.
    Gravar silencio nesse caso seria uma conta "conectada" a lugar nenhum.
    Desconectar tem funcao propria, e um `DELETE` explicito.
    """
    limpa = str(installation_id or "").strip()
    if not limpa:
        raise ValueError("instalacao vazia nao e permitida:"
                         " para desconectar use desconectar_do_github")
    fechar = con is None
    con = con or conectar()
    try:
        quando = agora()
        # O `criado_em` NAO entra no `DO UPDATE`: reinstalar o App nao reescreve
        # a data em que aquela conta conectou pela primeira vez.
        # O NUMERO JA E DE OUTRA CONTA? Recusa, e diz. `ON CONFLICT(usuario_id)`
        # so cobre a colisao pelo dono; a colisao pelo NUMERO cai no `UNIQUE`
        # novo e viraria um `IntegrityError` cru no meio de um caminho de
        # autenticacao. Conferir antes deixa a recusa legivel para quem chamou.
        dono = con.execute("SELECT usuario_id FROM instalacao_github"
                           " WHERE installation_id = ?", (limpa,)).fetchone()
        if dono is not None and dono["usuario_id"] != usuario_id:
            raise ValueError("essa instalacao ja pertence a outra conta")
        # O NUMERO JA E DE OUTRA CONTA? Recusa, e diz. `ON CONFLICT(usuario_id)`
        # so cobre a colisao pelo dono; a colisao pelo NUMERO cai no `UNIQUE`
        # novo e viraria um `IntegrityError` cru no meio de um caminho de
        # autenticacao. Conferir antes deixa a recusa legivel para quem chamou.
        dono = con.execute("SELECT usuario_id FROM instalacao_github"
                           " WHERE installation_id = ?", (limpa,)).fetchone()
        if dono is not None and dono["usuario_id"] != usuario_id:
            raise ValueError("essa instalacao ja pertence a outra conta")
        con.execute(
            "INSERT INTO instalacao_github"
            " (usuario_id, installation_id, criado_em, atualizado_em)"
            " VALUES (?,?,?,?)"
            " ON CONFLICT(usuario_id) DO UPDATE SET"
            " installation_id=excluded.installation_id,"
            " atualizado_em=excluded.atualizado_em",
            (usuario_id, limpa, quando, quando))
        if fechar:                    # ver `gravar`: nao quebre a transacao alheia
            con.commit()
    finally:
        if fechar:
            con.close()


def desconectar_do_github(usuario_id: int, con=None) -> None:
    """Apaga a instalacao DAQUELA conta — e so a dela.

    O `usuario_id` no `WHERE` e a peca inteira desta funcao: sem ele um clique
    em "desconectar" derrubaria o GitHub de todo mundo. Inofensiva quando nao ha
    linha: desconectar duas vezes nao e erro.
    """
    fechar = con is None
    con = con or conectar()
    try:
        con.execute("DELETE FROM instalacao_github WHERE usuario_id = ?",
                    (usuario_id,))
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
