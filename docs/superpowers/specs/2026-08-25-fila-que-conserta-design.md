# A fila que conserta

**Bloco B do HUB do dev.** Data: 25/08/2026.

O painel deixa de só apontar e passa a consertar — dentro de um cerco escrito,
com teto de dinheiro e sem nunca depender de uma instrução em texto para se
comportar.

## O problema, com número

O painel detecta 16 tipos de pendência e dá um botão para cada uma. O botão
**Resolver** já dispara uma sessão do Claude Code numa cópia isolada, com teto
de US$ 3, 40 rodadas, lista branca de ferramentas e abertura automática do
pedido de alteração.

Ele para num lugar só: `execucao.py` guarda **uma execução por vez**, numa
variável global (`_execucao`, linha 576), disparada a dedo, com o dono olhando.
Não existe fila.

O custo disso é medido: **203 dependências vulneráveis** em 4 projetos, entre
elas 6 críticas em `workspace-medconsultoria`, estão na tela há dias e continuam
lá. O gargalo nunca foi a detecção. É o dono ter de apertar um botão por vez.

## As cinco decisões que definem o escopo

Tomadas pelo dono em 25/08/2026, e todo o resto do documento decorre delas:

| # | Decisão | Consequência |
|---|---|---|
| 1 | Mescla sozinha **só o comprovadamente seguro** | Só PR do Renovate faz automerge. PR escrito pelo Claude sempre espera gente. |
| 2 | Teto de **R$ 50 por dia** | A fila para ao bater o teto e avisa, em vez de seguir. |
| 3 | Só pendências **mecânicas, com gabarito** | Lista branca de 3 regras. `ci_vermelha` fica de fora nesta versão. |
| 4 | Roda **só quando o dono manda começar** | Nenhum gasto acontece sem um clique. Sem agendador, sem laço de fundo. |
| 5 | A fila mora **dentro do painel** | Nada roda no GitHub Actions: a cota da conta já estourou (2.313 min / 116%). |

## A descoberta que muda o desenho

Uma das regras mecânicas é **determinística** — existe um comando que faz a
correção, sempre igual, e o resultado se verifica sem julgamento:

- `memoria_crlf` — converter fim de linha de CRLF para LF num arquivo de memória.

Gastar um modelo de linguagem nisso é pagar advogado para carimbar. Ela ganha um
trilho próprio: **sem IA, custo zero, sem pedido de alteração**. O painel faz e
relata.

`grafo_velho` parecia caber aqui e **não cabe**. A ação dessa regra hoje é copiar
um texto para o dono colar (`regras.py:145`): reindexar acontece pelo MCP do
grafo, que o painel não dirige — ele apenas serve a tela do grafo por procuração
(`servir.py:386`). Automatizar exigiria encanamento novo, fora do orçamento desta
entrega. Fica registrado como candidato ao trilho mecânico na entrega seguinte.

Sobram para o Claude as que exigem julgamento:

- `env_drift` — comparar o arquivo de exemplo de variáveis com o real e
  sincronizar **apenas os nomes**, nunca os valores.
- `dependencia_insegura` — só o que o Renovate não cobre (1 dos 203 alertas não
  é npm).

## Arquitetura

Três trilhos, um banco, uma tela.

```
pendências (regras.py, já existe)
        │
        ├── trilho 0: Renovate  ── fora do painel, no GitHub, custo zero
        │        dependência npm · agrupa · automerge do seguro
        │
        └── fila (tabela nova em hub.db)
                 │
                 ├── trilho 1: mecânica pura ── comando determinístico
                 │        memoria_crlf · custo zero · sem PR
                 │
                 └── trilho 2: com Claude ── execucao.py, cópia isolada
                          env_drift · dependencia_insegura · gera PR
```

### Trilho 0 — Renovate

Um `renovate.json` por repositório, com preset compartilhado. A regra de
automerge é estreita e escrita:

- É correção de segurança **e**
- não troca a versão maior (`patch` ou `minor`) **e**
- a CI está verde **e**
- o pacote tem ao menos 24 h de publicado (`minimumReleaseAge`) — janela contra
  pacote envenenado recém-subido.

Qualquer coisa fora disso vira pedido de alteração normal, esperando gente.

**Ajuste obrigatório no GitHub:** manter os *alertas* do Dependabot ligados — são
eles que alimentam a regra `vulnerabilidade` do painel — e desligar os *security
updates* automáticos dele. Dependabot e Renovate abrindo PR no mesmo repositório
produzem pedidos concorrentes.

### Trilho 1 e 2 — a fila

Tabela nova em `hub.db`:

```sql
CREATE TABLE fila (
  id           TEXT PRIMARY KEY,   -- igual ao id da pendência: regra:projeto
  projeto      TEXT NOT NULL,
  regra        TEXT NOT NULL,
  trilho       TEXT NOT NULL,      -- 'mecanico' | 'claude'
  estado       TEXT NOT NULL,      -- esperando|rodando|ok|falha|pulada
  tentativas   INTEGER NOT NULL DEFAULT 0,
  criado_em    TEXT NOT NULL,
  iniciado_em  TEXT,
  terminado_em TEXT,
  custo_usd    REAL NOT NULL DEFAULT 0.0,
  pr_url       TEXT,
  erro         TEXT
);
```

O `id` é o mesmo id estável da pendência (`regra:projeto`). É o que faz um item
reentrar sem duplicar e o que amarra a fila ao "esconder por 24 h" que já existe.

**Um item por vez.** A trava global de `decidir_pedido()` continua valendo; a
fila apenas deixa de exigir um clique humano entre um item e o seguinte.

## As quatro travas

Todas verificadas em código. Nenhuma delas é uma instrução no texto do pedido —
instrução em texto é sugestão, não trava.

### 1. Teto diário

```python
TETO_DIARIO_BRL = 50.00
```

Antes de iniciar cada item, soma `custo_usd` de todos os itens terminados hoje,
converte pela cotação de `execucao.py`, e compara. Bateu o teto: a fila para no
estado `pausada_por_teto` e a tela diz quanto gastou e quantos itens ficaram.
Não inicia "só mais um".

### 2. Anti-laço

- Máximo **2 tentativas** por item.
- Item que terminou em `falha` **não volta no mesmo dia**.

Sem isso, uma correção que não pega vira torneira aberta de madrugada.

### 3. Proibido apagar teste

Antes de abrir o pedido de alteração, o painel lê o `diff` da cópia — que
`execucao.py:513` já sabe produzir. O item é **reprovado** se:

- sumiu arquivo cujo nome case com `test_*` / `*_test.*` / `*.test.*` / `*.spec.*`; ou
- apareceu marcador de teste desligado (`@skip`, `xit(`, `it.skip(`, `test.skip(`,
  `@unittest.skip`, `pytest.mark.skip`).

Reprovado significa: a cópia é descartada, nada é publicado, e a tela diz por quê.

Esta trava é a razão de `ci_vermelha` ficar fora desta versão. "Consertar o teste
quebrado" é o caso mais valioso e o único em que apagar o teste parece uma
correção. Ele volta quando esta trava tiver rodado sozinha por um tempo.

### 4. Lista branca

```python
REGRAS_MECANICAS = {
    "memoria_crlf":         "mecanico",
    "env_drift":            "claude",
    "dependencia_insegura": "claude",
}
```

Regra fora do dicionário nem chega ao motor. `PROJETOS_BLOQUEADOS` (hoje
`ajudei-saude`) continua valendo por cima.

Ficam **deliberadamente de fora**, e por quê:

| Regra | Por que não |
|---|---|
| `ci_vermelha` | Ver trava 3. Volta depois. |
| `grafo_velho` | O painel não dirige o MCP do grafo. Encanamento novo, fora do orçamento. |
| `sem_remoto` | Criar repositório é ação fora da máquina e decisão do dono. |
| `caso_vazio` | Escrever a descrição do projeto é decisão de produto. |
| `abandonado` | "O que fazer com projeto parado há 30 dias" só o dono sabe. |
| `nao_enviado`, `nao_commitado` | Já são um botão de um clique. Fila não acrescenta nada. |
| `nao_publicado`, `site_fora` | Publicação nunca é automática — regra da casa. |
| `cota_actions` | Não tem projeto. Não há onde agir. |

## Segredo: a regra dura do `env_drift`

O `env_drift` é o único item da fila que toca arquivo de variáveis. A trava:

- Escreve **apenas nomes de variável** no `.env.example`, com valor vazio ou o
  placeholder já existente.
- **Nunca** copia valor do `.env` real.
- Verificação em código antes de publicar: se alguma linha nova do `.env.example`
  tiver conteúdo depois do `=`, o item é reprovado.

## A tela

Nenhuma tela nova. Uma faixa acima da caixa de pendências:

```
[ Trabalhar na fila ]   12 itens · R$ 0,00 de R$ 50 hoje
```

Enquanto roda, a faixa expande e mostra:

- o item em curso, com a frase de status que `execucao.py` já produz;
- quantos esperam;
- os terminados hoje, com resultado e link do pedido de alteração;
- o gasto acumulado em reais.

Um botão **Parar** ao lado. Ele usa o `parar()` que já existe e já mata a árvore
de processos.

Itens do trilho mecânico aparecem com `R$ 0,00` explícito — para ficar claro que
metade do trabalho não custa nada.

## Testes

Suíte nova `test_fila.py`, em `unittest` da biblioteca padrão, escrita **antes**
da implementação. As decisões são funções puras: entra dicionário, sai veredito.

| O que | Casos mínimos |
|---|---|
| `elegivel(pendencia)` | cada uma das 3 regras aceitas; uma recusada; projeto bloqueado; pendência sem projeto |
| `cabe_no_teto(gastos, custo)` | zero gasto; véspera do teto; exatamente no teto; passou |
| `pode_tentar(item, hoje)` | 1ª tentativa; 2ª; 3ª recusada; falha de hoje recusada; falha de ontem aceita |
| `diff_mexeu_em_teste(diff)` | remoção de arquivo de teste; cada marcador de skip; diff limpo; arquivo de teste **adicionado** (deve passar) |
| `env_example_tem_valor(diff)` | linha `CHAVE=`; linha `CHAVE=segredo`; comentário; linha inalterada |
| `proximo(fila, gastos)` | ordem por gravidade; empate; fila vazia; teto estourado devolve `None` |

Alvo: cobertura das quatro travas com caso de fronteira em cada uma. O projeto
está em 305 testes; esta suíte deve somar por volta de 40.

## O que fica fora desta entrega

Dito em voz alta para não virar falsa sensação de completude:

- **Bloco A** (o André abrir o painel na máquina dele) — é a próxima entrega, e é
  a fundação de tudo que vem depois.
- **Blocos C a G** — trabalho combinado, servidor/VPS, vigilância do que está no
  ar, medidas de tempo, negócio.
- `ci_vermelha` na fila — volta quando a trava 3 tiver histórico.
- Execução em paralelo — um item por vez é decisão, não limitação temporária.
- Agendamento — decisão 4 do dono: nada roda sem clique.

## Critérios de verificação

A entrega só está pronta quando, com a prova de cada um:

1. `python test_fila.py` verde, e o total do projeto acima de 340 testes.
2. As 4 suítes existentes seguem verdes (`test_regras`, `test_coletar`,
   `test_execucao`, `test_servir`, `test_memoria`).
3. `renovate.json` presente nos 4 repositórios com alerta aberto, e o Renovate
   tendo aberto ao menos um pedido agrupado — com a URL registrada.
4. Dependabot *security updates* desligado nesses 4, alertas mantidos ligados.
5. Uma corrida real da fila, com o registro do gasto em reais e o que produziu.
6. Um item reprovado de propósito pela trava 3, com a mensagem que a tela mostrou.
7. Teto diário demonstrado: fila parando com o motivo na tela.
8. README atualizado no mesmo commit.
