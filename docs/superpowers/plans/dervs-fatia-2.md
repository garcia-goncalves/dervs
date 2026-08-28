# Plano de execução — DERVS, Fatia 2 (o painel ganha braços)

Fase 4 da esteira, escrito em 28/08/2026. Contrato: `docs/esteira/dervs-fatia-2/spec.md`
e `docs/esteira/dervs-fatia-2/briefing.md`. Direção visual: `docs/esteira/dervs/design.md`,
aprovada e não reaberta. Onde este plano diverge do contrato, a divergência está escrita
com todas as letras na última seção.

Linha de base medida no HEAD `4988e21`, em 28/08/2026: **1095 testes em 19 arquivos, todos
verdes, exit 0** (test_agente 43 · autenticacao 36 · banco 133 · barreira 36 · coletar 165 ·
coletar_pesado 12 · cortina 27 · design 23 · execucao 91 · fila 92 · github_app 22 ·
imagem 12 · memoria 46 · p256 34 · passkey 86 · publicar 15 · regras 88 · rotas 25 ·
servir 109). Toda etapa abaixo mantém esse número subindo e nunca descendo.

## Objetivo

O agente que hoje só mede passa a executar: recebe uma tarefa na resposta do relatório que
ele já manda, dispara o binário `claude` sobre uma cópia isolada do repositório, empurra o
que está acontecendo de volta, e devolve um ramo com o diff. Na frente disso, um semáforo
onde **toda regra nasce vermelha** e o dono repinta; publicar é vermelho para sempre. Ao
fim da fatia, o dono abre o painel, clica em "resolver", vê o trabalho acontecendo ao vivo,
lê o diff em português, e sabe quanto o painel consumiu esta semana — sem digitar comando.

**A trava que não se toca:** o servidor continua sem importar `execucao` e sem alcançar
`subprocess`. `test_rotas.py` não é afrouxado em nenhum ponto. Se alguma etapa parecer
exigir isso, ela saiu do trilho — pare e releia a spec, seção `fora_de_escopo`.

## O que está FORA desta fatia

Do briefing, com destino nomeado: terminal no navegador (Fatia 3) · o Codex ligado — a
interface nasce com duas implementações previstas, só o Claude é ligado (Fatia 3) · a lousa
(Fatia 3) · o canivete de 15 ferramentas avulsas (Fatia 3) · editor de código no navegador
(Fatia 4) · o ferramental do Claude, §10 da fonte única (Fatia 4) · integrações novas ·
cadastro público.

Acrescentado por este plano, com motivo:

- **Execução paralela.** Um braço, uma sessão por vez (`decidir_pedido`, `execucao.py:409`).
  Duas sessões simultâneas não enxergam o gasto uma da outra.
- **Freio de horário.** Decisão do dono em 28/08/2026: sem janela de silêncio, observar sete
  dias. Não se relitiga; o que ela obriga a construir está nas etapas 1, 7 e 13.
- **Reescrever `test_rotas.py`.** Este plano só ACRESCENTA testes lá. Nada sai de
  `PROIBIDO`, `AMPUTADOS`, `EXECUTA` ou `VERBOS_PERMITIDOS`.
- **Migrar o `hub.db` de produção.** As colunas novas nascem com valor padrão; nenhuma linha
  existente é reescrita.

---

## Grafo de dependências

```
GRUPO A — a base. Três trilhas de arquivos disjuntos, rodam juntas.
  1 banco: colunas do semáforo, linhas da tarefa, coluna `executa`   (banco.py)
  2 tarefas.py: o semáforo puro + os tetos que mudam de casa         (tarefas.py, fila.py, execucao.py)
  3 o vigia de vocabulário passa a ler o painel.js                   (test_design.py)
  4 a trava de diff que barra tocar em publicação                    (fila.py)  <- depende da 2
        |
        +----------------------------+----------------------------+
        |                            |                            |
GRUPO B — o servidor (SEQUENCIAL: os três disputam servir.py)
  5 o fio de volta + as rotas de tarefa      (servir.py, Dockerfile)
        |
  6 SSE + o nginx que deixa o fluxo passar   (servir.py, infra/nginx-dervs.conf)
        |
  7 o contador de consumo                    (servir.py, banco.py)
                                     |
GRUPO C — o agente (paralelo com B a partir da 5)
  8 agente/executor.py: a interface Executor, com o Codex previsto e desligado
        |
  9 agente/enviar.py: pega a tarefa, roda, empurra progresso, obedece "pare"
        |
 10 o vigia irmão: nenhuma tarefa, de nenhuma cor, dispara a publicação
                                     |
GRUPO D — a tela (SEQUENCIAL: as três disputam painel.js e index.html)
 11 o semáforo na tela + o ao vivo + o botão Parar em toda tela com sessão viva
        |
 12 a tela do diff em português
        |
 13 a tela "quanto o painel consumiu esta semana"
                                     |
GRUPO E — fechar
 14 documentação: a fonte única, o roteiro do segundo braço
        |
 15 [ PORTÃO DO DONO: sim ou não ] a caixa efêmera na VPS      <- risco ALTO, isolada
        |
 16 verificação final da fatia, com a saída colada
```

**Nota sobre a etapa 4:** ela toca `fila.py`, que a etapa 2 também toca. **São a mesma
trilha**: ou a 4 espera a 2, ou as duas viram uma. Este plano as mantém separadas e
sequenciais (2 → 4) porque provam coisas diferentes.

**O único arquivo que TODAS as etapas com teste novo disputam é `.github/workflows/ci.yml`**
(um passo por `test_*.py`, listado à mão, cobrado pelo passo `:74`). O conflito é de linhas
adjacentes e resolve-se na mesclagem, mas ele existe — está declarado na seção de
paralelização, no fim.

**Ordenação por risco:** 1 e 2 primeiro porque tudo depende do esquema e do semáforo, e
porque uma coluna esquecida obriga migração em cima de dado real. A 3 vem cedo de propósito:
o vigia de vocabulário nasce antes do texto que ele vai cobrar. A 15 é a última e tem portão
próprio: ela é a única etapa que encosta numa máquina com 26 containers de terceiros.

---

## 1. O banco aprende semáforo, histórico e dois braços

- **objetivo** — tirar a execução da memória. Hoje `_execucao` é um dicionário
  (`execucao.py:802`): um recurso por máquina, sem histórico, sem retomada, e a Fatia 2 tem
  dois braços. Depois desta etapa a tarefa é uma linha de banco que sobrevive a reinício.
- **arquivos** — `banco.py`, `test_banco.py`.
- **depende_de** — nenhuma.
- **paralelizavel_com** — 2, 3.
- **risco** — médio. Migração em banco que já roda em produção.
- **fazer** —
  1. `ALTER TABLE fila ADD COLUMN` para: `cor TEXT NOT NULL DEFAULT 'vermelho'`,
     `aprovado_por INTEGER`, `aprovado_em TEXT`, `maquina_id INTEGER`, `ramo TEXT`,
     `executor TEXT NOT NULL DEFAULT 'claude'`, `rodadas INTEGER NOT NULL DEFAULT 0`,
     `parada_pedida_em TEXT`, `visto_em TEXT`, `frase TEXT`, `resumo TEXT`, `diff TEXT`.
     **O padrão de `cor` é `'vermelho'`** — é o que faz "toda regra nasce vermelha" ser
     propriedade do esquema e não promessa do Python.
  2. Estado novo `aguardando_aprovacao`, entre `esperando` e `rodando`.
  3. Tabela nova `tarefa_linha (tarefa_id TEXT, n INTEGER, texto TEXT, quando TEXT,
     PRIMARY KEY (tarefa_id, n))` — a numeração vem do agente (`execucao.estado` já devolve
     `total_de_linhas`), e a chave composta faz reenvio ser idempotente de graça.
  4. Tabela nova `cor_da_regra (regra TEXT PRIMARY KEY, cor TEXT NOT NULL, por INTEGER,
     quando TEXT NOT NULL)` — a repintura do dono. Regra ausente daqui é vermelha.
  5. `ALTER TABLE maquina ADD COLUMN executa INTEGER NOT NULL DEFAULT 0` — a máquina só
     recebe tarefa se alguém ligou isso. Padrão 0, e isso é a lei 3 do repositório.
  6. Funções: `tarefa_para_maquina`, `registrar_progresso`, `registrar_desfecho`,
     `aprovar_tarefa`, `pedir_parada`, `repintar_regra`, `cores_das_regras`,
     `linhas_da_tarefa(tarefa_id, desde)`, `tarefas_sem_noticia(limite_min, agora_iso)`.
  7. `_migrar_fila_semaforo(con)` no molde de `banco.py:416-660`: `PRAGMA table_info` +
     `BEGIN IMMEDIATE` + releitura DENTRO da transação + `_religar_fk`. Chamada a partir de
     `migrar()`, uma função por migração — **nunca `executescript`, que dá COMMIT implícito**
     (lição de 26/08/2026).
- **como_provar** —
  - `python test_banco.py` → `OK`, e `Ran N` com N ≥ 148 (hoje são 133).
  - Um teste dedicado que constrói um `hub.db` no esquema ANTIGO (sem as colunas), grava uma
    linha na `fila`, roda `banco.migrar` **duas vezes**, e prova: as colunas existem, a linha
    antiga sobreviveu, e a `cor` dela é `'vermelho'`.
  - Um teste que prova `maquina.executa` nascendo `0` para máquina criada por pareamento.
  - Um teste que prova que a fonte de `migrar()` não contém `executescript`.
- **armadilha** — passar `agora_iso` a `tarefas_sem_noticia` e a tudo que compara prazo. Teste
  com data fixa que não recebe `agora_iso` passa hoje e fica vermelho sozinho amanhã, sem
  ninguém tocar em nada.

## 2. `tarefas.py` — o semáforo, e os tetos mudando de casa

- **objetivo** — a decisão "esta tarefa pode rodar agora?" existir em UM lugar, puro,
  testável sem processo e sem rede, e alcançável **tanto pelo servidor quanto pelo agente**.
- **arquivos** — `tarefas.py` (novo), `test_tarefas.py` (novo), `fila.py`, `execucao.py`,
  `test_fila.py`, `test_execucao.py`, `.github/workflows/ci.yml` (passo novo).
- **depende_de** — nenhuma.
- **paralelizavel_com** — 1, 3.
- **risco** — médio. Mexe em dois arquivos com 183 testes somados.
- **fazer** —
  1. `tarefas.py`, biblioteca padrão pura, **sem importar `execucao` nem `fila`** (se
     importasse `execucao`, o `Dockerfile` teria de levar `execucao.py`, e
     `test_imagem.PROIBIDOS` reprova).
  2. **Mudam de casa para `tarefas.py`**, com uma cópia só no repositório inteiro:
     `USD_BRL`, `TETO_USD`, `TETO_DIARIO_BRL`, `MAX_TURNOS`, `MAX_TENTATIVAS`,
     `cabe_no_teto`, `quanto_falta`, `teto_da_sessao`, `em_reais`, `hoje_local`,
     `janela_local_em_utc`, `dia_local_de`. `fila.py` e `execucao.py` passam a importar de
     `tarefas`. **Por que mover e não copiar:** o servidor precisa recusar a entrega da
     tarefa quando o teto do dia estourou (critério 5), e ele não pode importar `fila`
     (`test_rotas.AMPUTADOS`). Duas cópias do teto divergem, e a que diverge é sempre a que
     ninguém lê — é a lição de 27/08 do `contraste.py`.
  3. `NUNCA_VERDE = frozenset({"publicar"})` e `cor_da_regra(regra, repinturas)` devolvendo
     `"vermelho"` por padrão e recusando repintar o que está em `NUNCA_VERDE`.
  4. `pode_rodar(tarefa, gasto_usd, agora_iso) -> (bool, motivo)`: recusa se a cor é vermelha
     sem `aprovado_em`, se a regra não está no catálogo, se o teto do dia não cabe, se
     `tentativas >= MAX_TENTATIVAS`, se a máquina não tem `executa`.
  5. **O contrato JSON do fio de volta** escrito como constantes e docstring neste arquivo
     (campos da tarefa que desce, campos do progresso e do desfecho que sobem). É o que
     permite as etapas 5 e 8/9 andarem em paralelo sem se adivinharem.
- **como_provar** —
  - `python test_tarefas.py` → `OK`. Cobre, nominalmente: regra desconhecida nasce vermelha ·
    `publicar` recusa repintura para verde · verde sem aprovação roda · vermelha sem
    aprovação **não** roda · vermelha com aprovação roda · teto estourado recusa antes de
    qualquer outra coisa.
  - **A prova nos dois sentidos, que o critério 3 exige:** um teste `guarda_da_guarda` que
    lê `inspect.getsource(tarefas.pode_rodar)` e cobra que a palavra `aprovado_em` apareça —
    remover a guarda deixa o arquivo vermelho, não só a asserção.
  - `python test_fila.py` → `OK`, `Ran 92` ou mais · `python test_execucao.py` → `OK`,
    `Ran 91` ou mais. As duas suítes continuam verdes depois da mudança de casa.
  - Um teste que prova que importar `tarefas` **não** arrasta `execucao` nem `fila`.
  - `grep -c "python test_tarefas.py" .github/workflows/ci.yml` → `1`.
- **armadilha** — deixar `TETO_DIARIO_BRL` nos dois arquivos "por compatibilidade". Se
  ficarem dois nomes, o dia em que um mudar o outro mente com autoridade.

## 3. O vigia de vocabulário passa a ler o `painel.js`

- **objetivo** — o critério 10 do briefing ("todo texto de tela em português, conferido pelo
  vigia que já existe") ser verdade **antes** de a Fatia 2 escrever texto. Hoje ele não é:
  `test_design.ATelaFalaPortugues.texto_visivel()` lê só o `index.html` e extrai o
  `<script>` inline — que não existe mais desde 28/08, porque a CSP o expulsou para
  `assets/painel.js`. Todo texto novo da Fatia 2 nasceria fora do alcance do vigia.
- **arquivos** — `test_design.py`.
- **depende_de** — nenhuma.
- **paralelizavel_com** — 1, 2.
- **risco** — baixo. Medido em 28/08/2026: a extração aplicada ao `painel.js` de hoje acha
  56 pedaços de texto e **zero** palavras proibidas. Estender não deixa nada vermelho agora.
- **fazer** — `texto_visivel()` passa a concatenar o `index.html` e o `assets/painel.js`
  (o `PAINEL_JS` já está declarado em `test_design.py:45`, usado por outro teste). O piso do
  `test_6b` sobe de 60 para o número medido depois da mudança, menos folga — um vigia que
  passa vazio não vigia nada, e esse teste é a guarda disso.
- **como_provar** —
  - `python test_design.py` → `OK`, `Ran N` com N ≥ 23.
  - O `test_6b` reprova se apontado só para o HTML.
  - Guarda da guarda: `test_6c` continua provando que a comparação reprova mesmo.
- **armadilha** — estender a extração para o arquivo inteiro em vez de para os padrões de
  texto de tela (`textContent`, `title`, `placeholder`, `aria-label`). Nome de rota, chave de
  dado e comentário **não** são texto de tela; reprovar por causa deles treina a gente a
  ignorar o teste.

## 4. A trava de diff que barra tocar em publicação

- **objetivo** — dar dentes ao critério 4. Não basta "nenhuma rota publica": nenhum **diff**
  produzido por uma sessão pode alterar o caminho que publica.
- **arquivos** — `fila.py`, `test_fila.py`.
- **depende_de** — 2 (mesmo arquivo).
- **paralelizavel_com** — 5, 6, 8 (arquivos disjuntos).
- **risco** — baixo.
- **fazer** — `diff_toca_publicacao(diff) -> str` no molde de `diff_mexeu_em_teste`
  (`fila.py:176`): devolve o motivo se alguma linha `+++ b/` ou `--- a/` casar
  `.github/workflows/**`, `Dockerfile`, `docker-compose.yml`, `infra/**`, ou se alguma linha
  nova contiver `workflow run`, `workflow_dispatch`, `/dispatches` ou `gh workflow`.
  Entra em `reprovar(diff, regra)` para **toda** regra, não só para uma.
- **como_provar** —
  - `python test_fila.py` → `OK`, com casos: diff que acrescenta gatilho no `publicar.yml`
    é reprovado · diff que só mexe em `README.md` passa · renomeação de workflow é reprovada ·
    e a guarda: um diff vazio **não** é reprovado (senão a trava viraria "reprova tudo", que
    passa no teste e trava o produto).
- **armadilha** — casar por substring solta. `infra` dentro de `src/infraestrutura.ts`
  reprovaria trabalho legítimo; case o caminho a partir da raiz do diff.

## 5. O fio de volta e as rotas de tarefa

- **objetivo** — o painel passa a ter o que dizer quando o agente pergunta. Nenhuma conexão
  nova, nenhuma porta aberta, nenhuma inversão de sentido: o agente continua sendo quem
  pergunta, e a resposta 200 de `/agente/relatorio` — que já é um dicionário
  (`servir.py:1318-1320`) — passa a carregar a tarefa pendente daquela máquina.
- **arquivos** — `servir.py`, `Dockerfile`, `test_servir.py`, `test_rotas.py` (só
  acréscimo).
- **depende_de** — 1, 2.
- **paralelizavel_com** — 8 (arquivos disjuntos). **Não** com 6 e 7: os três disputam
  `servir.py`.
- **risco** — alto. É o arquivo mais vigiado do repositório.
- **fazer** —
  1. `_relatorio` passa a acrescentar `"tarefa": {...}` ou `"tarefa": None` na resposta,
     lendo `banco.tarefa_para_maquina` + `tarefas.pode_rodar`. O corpo da tarefa segue o
     contrato escrito na etapa 2.
  2. Rota nova `POST /agente/resultado`, acesso `maquina`, função `Hub._resultado`. Aceita
     **progresso** (frase, linhas novas, rodadas, custo parcial) e **desfecho** (estado,
     ramo, resumo, diff, `pr_url`). A resposta dela carrega `{"pare": true|false}` — é assim
     que o botão Parar chega ao agente sem conexão nova.
  3. Balcão próprio no teto: `cortina.registrar_tentativa` com balcão `resultado` e teto
     maior. O balcão de `relatorio` tem teto 60/15 min = um a cada 15 s, e o progresso
     precisa ser mais frequente que isso — misturar os dois trancaria a máquina legítima.
  4. Rotas do dono, todas acesso `dado`, todas com a guarda comum das escritas (anti-CSRF da
     sessão + `Origin`, como `/api/silenciar`): `GET /api/tarefas` (`Hub._tarefas`),
     `POST /api/tarefas/aprovar` (`Hub._tarefa_aprovar`), `POST /api/tarefas/parar`
     (`Hub._tarefa_parar`), `POST /api/tarefas/cor` (`Hub._tarefa_cor`).
  5. `Dockerfile`: `COPY tarefas.py /app/`. Sem isso, `test_imagem.py:99` fica vermelho — ele
     cobra que todo módulo importado por `servir.py` entre na imagem.
  6. Tarefa `rodando` sem `visto_em` há 15 minutos vira `falha` com o motivo *"o computador
     parou de dar notícia"*. Não é enfeite: sem isso, agente morto deixa a tarefa `rodando`
     para sempre e o painel mente (lei 2).
- **como_provar** —
  - `python test_rotas.py` → `OK`, `Ran N` com N ≥ 29. **Nada removido** de `PROIBIDO`,
    `AMPUTADOS`, `EXECUTA` ou `VERBOS_PERMITIDOS`; acréscimos nominais: `/agente/resultado`
    é `maquina`, as quatro `/api/tarefas*` são `dado`.
  - `python test_servir.py` → `OK`, `Ran N` com N ≥ 125, incluindo, no servidor de verdade:
    `POST /agente/resultado` sem token → `401` · com token de outra máquina não alcança a
    tarefa desta · `POST /api/tarefas/aprovar` sem sessão → `401` · com sessão e sem
    anti-CSRF → `403` · relatório de máquina com `executa=0` volta com `"tarefa": null`.
  - `python test_imagem.py` → `OK`. E, nominalmente, que `execucao.py`, `fila.py` e
    `barreira.py` continuam **fora** da imagem.
  - Um teste que prova que `servir` não tem atributo `execucao` nem `fila`.
- **armadilha** — a que vai morder primeiro: **`import execucao` no topo de `servir.py`
  deixa a CI vermelha, e a mensagem fala de rota, não de import** (`test_rotas.py:47`,
  `AMPUTADOS`). A segunda: nomear qualquer rota ou função de rota com `acao`, `execucao`,
  `exec`, `terminal`, `pty`, `shell`, `comando` ou `grafo` — o regex casa contra o caminho
  **e** o nome da função. `_tarefa_aprovar` passa; `_executar_tarefa` não.

## 6. SSE no lugar do relógio de 60 segundos

- **objetivo** — o critério 8 ("o dono vê o trabalho acontecendo") não sobrevive a um
  `setInterval(…, 60000)` (`assets/painel.js:1107`). O `ThreadingHTTPServer` (`servir.py:1633`)
  aguenta; a CSP de produção (`default-src 'self'`) **não** bloqueia `EventSource`
  same-origin. O que falta é o fluxo passar pelo nginx.
- **arquivos** — `servir.py`, `infra/nginx-dervs.conf`, `test_sse.py` (novo),
  `.github/workflows/ci.yml` (passo novo).
- **depende_de** — 5.
- **paralelizavel_com** — 8, 9 (arquivos disjuntos).
- **risco** — médio-alto. É a primeira resposta deste servidor que não é uma string inteira.
- **fazer** —
  1. `GET /api/eventos` (`Hub._eventos`), acesso `dado`. Cabeçalhos:
     `Content-Type: text/event-stream`, `Cache-Control: no-cache`,
     **`X-Accel-Buffering: no`**, `Connection: close`. Sem `Content-Length`.
  2. O laço lê `banco.linhas_da_tarefa(tarefa_id, desde)` a cada 1 s, manda `id:`/`data:`,
     **manda um comentário `: ping` a cada 20 s** (o `proxy_read_timeout` do nginx é 60 s;
     silêncio de um minuto derruba a conexão) e **encerra sozinho em 300 s** — o `EventSource`
     reconecta sozinho, e conexão eterna em `ThreadingHTTPServer` é thread eterna.
  3. Teto de conexões: no máximo 4 por sessão e 16 no total, senão `503`. Sem teto, dez abas
     abertas são dez threads paradas, e o servidor tem duas pessoas de público.
  4. `BrokenPipeError` e `ConnectionAbortedError` tratados **dentro** da rota. Sem isso, cada
     aba fechada cai no `except Exception` de `_despachar` e cospe um traceback no log.
  5. `infra/nginx-dervs.conf`: `location = /api/eventos` com `proxy_buffering off;`,
     `proxy_read_timeout 3600s;`, `proxy_http_version 1.1;` e os mesmos `proxy_set_header` do
     `location /`. **NENHUM `add_header` nesse bloco** — a regra está escrita no próprio
     arquivo (linha ~137): um `add_header` dentro de um `location` anula os seis cabeçalhos
     de segurança do `server`.
- **como_provar** —
  - `python test_sse.py` → `OK`. No molde de `test_servir.ServidorDeVerdade`
    (`test_servir.py:127`), com **timeout em toda leitura** — teste de fluxo sem timeout
    pendura a suíte inteira. Cobre: sem sessão → `401` · com sessão → `200` e
    `Content-Type: text/event-stream` · o cabeçalho `X-Accel-Buffering: no` está presente ·
    uma linha gravada no banco chega ao leitor em menos de 3 s · a conexão fecha sozinha ·
    a quinta conexão da mesma sessão leva `503`.
  - Um teste no mesmo arquivo que **lê `infra/nginx-dervs.conf` como texto** e cobra:
    o bloco `location = /api/eventos` existe · ele tem `proxy_buffering off` · ele **não**
    tem nenhum `add_header` · o `location /` continua com `proxy_buffering on`.
  - `python test_servir.py` → `OK`. E, porque `ATelaSoChamaRotaQueExiste` só enxerga
    `fetch("/…")`, **acrescente lá** a extração de `new EventSource("/…")` — senão a rota do
    fluxo é a única da tela que ninguém cobra existir.
- **armadilha** — testar o SSE só no localhost. Cinco defeitos da primeira publicação só
  existiam fora dele (`docs/esteira/dervs/verificacao.md`). O bloco do nginx é conferido por
  leitura aqui e **por curl contra `dervs.com.br` na etapa 16**, não antes.

## 7. O contador de consumo

- **objetivo** — o dono decidiu observar sete dias antes de limitar. Sem contador, "observar"
  é uma intenção. Esta etapa é o que torna a decisão dele executável.
- **arquivos** — `servir.py`, `banco.py`, `test_servir.py`, `test_banco.py`.
- **depende_de** — 1, 5.
- **paralelizavel_com** — 9, 10.
- **risco** — baixo.
- **fazer** — `banco.consumo(desde_iso, ate_iso)` agregando a `fila` por dia local, por
  projeto e por regra: sessões, rodadas (`rodadas`), duração (`iniciado_em`→`terminado_em`),
  resultado e custo. Rota `GET /api/consumo` (`Hub._consumo`), acesso `dado`. **Sete dias é o
  padrão**, e a resposta carrega o carimbo de quando foi medido (§4.3 da fonte única).
- **como_provar** —
  - `python test_banco.py` → `OK`, com um teste que grava tarefas em três dias locais
    diferentes (passando `agora_iso`) e prova que a agregação separa por **dia local**, não
    por UTC — em UTC-3, as 21h de terça já é quarta em UTC.
  - `python test_servir.py` → `OK`: `/api/consumo` sem sessão → `401`; com sessão → `200` e
    um corpo com `dias`, `projetos`, `regras` e `medido_em`.
  - Um teste que prova que semana **sem nenhuma sessão** devolve zeros **e** o carimbo — e
    não um corpo vazio. "Não sei" e "zero" são estados diferentes (lei 2).
- **armadilha** — somar `custo_usd` e chamar de "quanto o painel consumiu". Com assinatura, o
  recurso escasso é **cota**, não dinheiro (§13 da fonte única). O número que manda é
  sessões e rodadas; o custo em reais aparece como referência, rotulado como tal.

## 8. `agente/executor.py` — a interface, com o Codex previsto e desligado

- **objetivo** — o critério 1 do briefing e a tomada pronta para a Fatia 3. Ligar o Codex
  depois é acrescentar uma implementação, não refazer nada.
- **arquivos** — `agente/executor.py` (novo), `test_executor.py` (novo),
  `.github/workflows/ci.yml` (passo novo).
- **depende_de** — 2 (o contrato).
- **paralelizavel_com** — 5, 6 (arquivos disjuntos).
- **risco** — médio.
- **fazer** —
  1. `class Executor` com `nome`, `disponivel() -> bool` e
     `rodar(tarefa, teto_usd, ao_progredir) -> dict`.
  2. `ExecutorClaude` embrulha o que já existe e está testado: `execucao.iniciar` (`:833`),
     `execucao.estado(desde)` (`:1198`), `execucao.parar` (`:1145`),
     `execucao.esperar_terminar` (`:1130`). **Não reescreva `execucao.py`** — ele tem 91
     testes e a medição de campo colada no topo.
  3. `ExecutorCodex` existe, `disponivel()` devolve `False`, `rodar` levanta
     `NotImplementedError` com a frase que diz que ele é da Fatia 3.
  4. **Antes de disparar**, `Executor.rodar` chama `tarefas.pode_rodar`. É a segunda camada
     do critério 5: o servidor já recusou entregar, e o agente recusa de novo.
- **como_provar** —
  - `python test_executor.py` → `OK`. O critério 1, ao pé da letra: um repositório de mentira
    criado em `tempfile` com `git init` · `execucao.montar_comando` trocado por um argv que
    roda um script Python de mentira cuspindo `stream-json` linha a linha (inclusive um
    evento `assistant` com ferramenta e um `result` com `total_cost_usd` e `num_turns`) ·
    asserções de que as linhas foram lidas **uma a uma** (o `ao_progredir` foi chamado mais de
    uma vez, antes do fim) e de que o desfecho carrega ramo, resumo e diff.
  - No mesmo arquivo, o critério 5: com o teto do dia já consumido, `rodar` devolve recusa
    **e o argv nunca foi montado** — prove com um duble que estoura se for chamado.
  - E o Codex: `ExecutorCodex().disponivel()` é `False`, e `rodar` levanta.
  - `grep -c "python test_executor.py" .github/workflows/ci.yml` → `1`.
- **armadilha** — deixar o teste chamar o `claude` de verdade. Ele gastaria cota da conta do
  André a cada corrida da CI, e a CI roda em máquina sem login nenhum: o teste ficaria
  vermelho por motivo errado.

## 9. O agente pega a tarefa, empurra progresso e obedece "pare"

- **objetivo** — fechar o fio. O mesmo binário, dois lugares.
- **arquivos** — `agente/enviar.py`, `test_agente.py`.
- **depende_de** — 8, e o contrato da 5.
- **paralelizavel_com** — 7, 11.
- **risco** — médio.
- **fazer** —
  1. `enviar_uma_vez` passa a ler `resposta["tarefa"]`. Se houver, chama o executor.
  2. **Enquanto roda, o agente fala a cada 5 s** por `POST /agente/resultado` com o progresso
     (frase, linhas novas desde a última, rodadas, custo parcial) — é isso que alimenta o SSE
     e o que torna o botão Parar utilizável. A resposta traz `{"pare": true}`, e o agente
     chama `execucao.parar()`.
  3. Erro de rede no meio não pode matar a sessão nem o laço: o agente já trata isso
     (`agente/enviar.py:299`), e o mesmo cuidado vale para o progresso.
  4. Uma sessão por vez por máquina, como já é (`decidir_pedido`, `execucao.py:409`).
- **como_provar** —
  - `python test_agente.py` → `OK`, `Ran N` com N ≥ 55, incluindo: resposta sem `tarefa` não
    dispara nada · resposta com tarefa dispara o executor **uma** vez · o progresso é enviado
    mais de uma vez durante uma sessão longa (duble de relógio) · a resposta `{"pare": true}`
    chama `parar()` · falha de rede no progresso não interrompe a sessão · o token continua
    indo só em cabeçalho e o agente continua **sem seguir redirect**
    (`_SemRedirecionar`, `agente/enviar.py:153`).
  - **Latência do Parar, medida e escrita:** um teste que prova que o intervalo de progresso é
    ≤ 5 s. O botão não é instantâneo, e a tela tem de dizer isso (etapa 11).
- **armadilha** — reaproveitar o balcão `relatorio` para o progresso. Teto de 60 por 15 min é
  um a cada 15 s; a cada 5 s a máquina legítima leva `429` e o dono vê a tela congelar sem
  explicação.

## 10. O vigia irmão: nenhuma tarefa, de nenhuma cor, publica

- **objetivo** — o critério 4. O `test_rotas.py` varre as rotas; falta quem varra as tarefas.
- **arquivos** — `test_tarefas_nao_publicam.py` (novo), `.github/workflows/ci.yml`.
- **depende_de** — 2, 4, 8.
- **paralelizavel_com** — 7, 11, 12.
- **risco** — baixo.
- **fazer** — um vigia que prova, lendo as estruturas em memória e o fonte:
  1. `"publicar"` está em `tarefas.NUNCA_VERDE`, e `repintar_regra("publicar","verde")` é
     recusada — nos dois lados, banco e Python.
  2. Nenhuma regra do catálogo tem trilho que alcance `execucao.publicar` sem passar por
     `fila.reprovar`.
  3. `barreira.SAEM_DA_MAQUINA` continua contendo `gh`, `curl`, `wget`, `ssh` e `docker`, e
     `git` continua com lista **branca** de subcomando (`GIT_SUBCOMANDO_OK`) sem `push`.
  4. Nenhum arquivo de `agente/` contém `workflow run`, `/dispatches` nem `workflow_dispatch`.
  5. `fila.reprovar` cita `diff_toca_publicacao` — a trava da etapa 4 está ligada, e não só
     escrita.
  6. **A guarda da guarda:** um diff de mentira que acrescenta `on: push` ao `publicar.yml` é
     reprovado por `fila.reprovar`. Vigia que passa vazio não vigia nada.
- **como_provar** — `python test_tarefas_nao_publicam.py` → `OK`, `Ran N` com N ≥ 8. E
  `grep -c "python test_tarefas_nao_publicam.py" .github/workflows/ci.yml` → `1`.
- **armadilha** — escrever o vigia contra uma cópia da lista de regras. Ele tem de importar
  os módulos e ler as estruturas de verdade, como `test_rotas.py` faz com `servir.ROTAS`.

## 11. A tela: o semáforo, o ao vivo, e o botão Parar em toda tela

- **objetivo** — critérios 8 e 9 na parte que se vê. O botão Parar deixa de ser conveniência
  e vira o freio principal, porque o dono decidiu não ter freio de horário.
- **arquivos** — `index.html`, `assets/painel.js`, `assets/painel.css`, `test_design.py`.
- **depende_de** — 3, 5, 6.
- **paralelizavel_com** — 10. **Não** com 12 e 13 (mesmos arquivos).
- **risco** — médio.
- **fazer** —
  1. O `setInterval(…, 60000)` de `assets/painel.js:1107` é substituído por
     `new EventSource("/api/eventos")`, com volta ao relógio de 60 s se o fluxo cair — a tela
     nunca fica muda.
  2. A cor da tarefa aparece com **os quatro sinais** que o design exige do selo: cor, forma,
     glifo e rótulo escrito. Cor sozinha não é informação.
  3. Botão **Parar** presente em **toda** tela enquanto houver sessão viva, não só na tela da
     tarefa — barra fixa no topo. Ele diz *"pedido de parada enviado"* e só troca para
     *"parada confirmada"* quando o agente confirmar. **Não afirme que parou antes de o
     agente dizer que parou** — `parar()` devolve `False` quando não confirmou a morte
     (`execucao.py:1195`), e essa é exatamente a informação que o dono precisa.
  4. Repintar a cor de uma regra, com a recusa visível para `publicar`.
  5. **Nenhum arquivo novo em `assets/`.** A lista de estáticos nasce de uma leitura da pasta
     **na subida** (`servir.py:132`): arquivo novo só passa a ser servido depois de reiniciar,
     e um `.js` novo do painel precisaria entrar em `ESTATICOS_COM_SESSAO` **por caminho
     exato** e nos dois testes que cobram os nomes. Acrescente ao `painel.js`/`painel.css`.
- **como_provar** —
  - `python test_design.py` → `OK` — e agora o vocabulário cobre o `painel.js` (etapa 3):
    nada de "deploy", "task", "issue", "worker", "loading" no texto novo.
  - `python test_servir.py` → `OK`: `ATelaSoChamaRotaQueExiste` acha as rotas novas, e agora
    também o `EventSource`.
  - `python test_rotas.py` → `OK`: `/assets/painel.js` e `/assets/painel.css` continuam
    `dado`, e continuam existindo com esses nomes exatos.
  - **Verificado clicando, não lendo**: com o servidor local de pé e uma tarefa de mentira,
    o log aparece na tela sem recarregar; o botão Parar dispara e a frase muda nas duas
    etapas. Evidência para a etapa 16.
- **armadilha** — dar a tarefa por parada porque a faixa apareceu. Já aconteceu nesta casa:
  afirmou-se que a fila funcionava tendo só visto a faixa aparecer, e o botão nunca disparava.

## 12. A tela do diff, em português

- **objetivo** — critério 9. O Thiago não lê código; o André lê. Mesma tela, profundidade
  diferente.
- **arquivos** — `index.html`, `assets/painel.js`, `assets/painel.css`.
- **depende_de** — 11.
- **paralelizavel_com** — nenhuma (mesmos arquivos da 11 e da 13).
- **risco** — baixo no código, médio no produto: é aqui que o dono decide aprovar.
- **fazer** — o diff que `execucao.diff_da_copia` (`:690`) já produz, apresentado em duas
  camadas: **em cima**, uma frase por arquivo em português (*"3 linhas trocadas em
  `banco.py`"*, *"o arquivo `X` foi criado"*), o ramo, e o que as travas conferiram; **embaixo,
  fechado**, o diff cru para quem quiser a prova. Toda tarefa termina num ramo, nunca na
  `main` — `nome_do_ramo` (`execucao.py:454`) já garante isso.
- **como_provar** —
  - `python test_design.py` → `OK`, com o vocabulário cobrindo o texto novo.
  - Um teste da tradução do diff em `test_tarefas.py` (função pura: entra diff, sai lista de
    frases), incluindo: arquivo criado · arquivo apagado · renomeação · diff vazio ("nada
    mudou", e não uma lista vazia sem explicação).
  - Clicando: uma tarefa terminada mostra o resumo em português **e** o diff cru abre.
- **armadilha** — resumir o diff com um modelo de linguagem. Medir e apurar é código
  determinístico; um LLM que "acha" que o diff é inofensivo é exatamente o número errado com
  cara de certo que a lei 2 proíbe. Aqui a IA já trabalhou — a apresentação é conta nossa.

## 13. A tela "quanto o painel consumiu esta semana"

- **objetivo** — a semana de observação virar decisão em vez de impressão. Está escrito na
  spec como consequência obrigatória da escolha do dono, não como escopo extra.
- **arquivos** — `index.html`, `assets/painel.js`, `assets/painel.css`,
  `docs/A-APLICACAO.md` (§8).
- **depende_de** — 7, 12.
- **paralelizavel_com** — nenhuma.
- **risco** — baixo.
- **fazer** — por dia, por projeto e por regra: sessões, rodadas, duração e resultado, com o
  carimbo de quando foi medido. **Decisão de produto pendente, ver a última seção:** o §8 da
  fonte única diz "seis telas, e só seis". Este plano assume a **sétima**, e obriga esta etapa
  a atualizar o §8 no mesmo commit. Se o dono preferir, isto vira um bloco da tela Painel — e
  aí a etapa não toca a fonte única.
- **como_provar** —
  - `python test_design.py` → `OK`.
  - `python test_servir.py` → `OK`: a tela busca `/api/consumo`, e a rota existe.
  - Clicando, em 360×640: a tela responde "quanto consumimos esta semana" sem rolagem
    horizontal, e sem nenhuma palavra em inglês.
- **armadilha** — mostrar zero onde o dado não existe. Semana sem medição diz *sem dados*, o
  quarto estado do selo. Zerar o que não deu para reler apaga um problema real.

## 14. A documentação anda junto

- **objetivo** — nenhum documento descrevendo o software de ontem. Documentação que mente
  mente com autoridade.
- **arquivos** — `docs/A-APLICACAO.md` (§7 já reescrito; atualizar §8, §11, §12 e a lista de
  dívidas), `docs/operacao/segundo-braco.md` (novo), `CLAUDE.md` (a seção de travas ganha
  `tarefas.py` e o SSE), `README.md`.
- **depende_de** — 1 a 13.
- **paralelizavel_com** — nenhuma (é a costura).
- **risco** — baixo.
- **fazer** — o que mudou de porta, comando, variável, fluxo e tela. O roteiro do segundo
  braço é escrito **para quem não opera terminal**, com o comando exato, onde colar, o que
  aparece se der certo e o que fazer se der errado.
- **como_provar** —
  - `grep -c "tarefas.py" CLAUDE.md` ≥ 1 · `grep -c "api/eventos" docs/A-APLICACAO.md` ≥ 1.
  - A lista de mudanças da fatia conferida contra os documentos, item a item, colada na
    etapa 16.
- **armadilha** — deixar a documentação para depois do PR. Ela entra no mesmo commit da
  mudança, e isso é regra do repositório.

## 15. [ PORTÃO DO DONO ] A caixa efêmera na VPS

- **objetivo** — o segundo braço. O mesmo agente instalado na VPS, com a sessão rodando
  dentro de um container descartável, sem segredo do painel no ambiente e com saída de rede
  em lista branca.
- **arquivos** — `agente/caixa.py` (novo), `infra/caixa-dervs.Dockerfile` (novo),
  `test_caixa.py` (novo), `docs/operacao/segundo-braco.md`, `.github/workflows/ci.yml`.
- **depende_de** — 9, 14.
- **paralelizavel_com** — nenhuma. **Isolada de propósito.**
- **precisa_da_mao_de_alguem** — **sim, o dono, ANTES de começar.** Uma pergunta de sim ou
  não, com todas as letras: *"posso instalar o agente na VPS que roda os seus 26 containers
  e 8 sistemas, sabendo que ele vai criar e destruir containers lá dentro?"*. É o portão 4 do
  plano de voo do briefing. Sem o sim, esta etapa não começa e a fatia fecha sem ela.
- **risco** — **ALTO, e é o mais alto da fatia.** Erro aqui derruba o negócio do dono, não o
  DERVS. **Se der errado:** o agente da VPS é um processo isolado — pare-o e remova-o; o
  painel volta ao braço único sem nenhuma mudança de código, porque `maquina.executa` é uma
  coluna com padrão `0`. Nunca toque em `/etc/nginx/sites-enabled/`, nunca reutilize porta
  existente, e **o deploy continua rodando no GitHub, nunca daqui**.
- **fazer** —
  1. `agente/caixa.py` monta o argv do `docker run` — **é código nosso, não a IA**, e por isso
     `docker` continua barrado em `barreira.SAEM_DA_MAQUINA` para a sessão filha. As duas
     barreiras são configurações distintas e não se misturam.
  2. O argv: `--rm`, rede própria em lista branca (nunca `--network host`, nunca o socket do
     Docker montado), `--read-only` com `tmpfs` para a cópia, limites de memória e CPU,
     usuário sem privilégio, e **o ambiente peneirado por `execucao.ambiente_da_filha`**.
  3. A lista branca de saída: só o que a sessão precisa alcançar. Nada de GitHub — a cópia
     não tem `origin`.
- **como_provar** —
  - **Sem Docker, na CI:** `python test_caixa.py` → `OK`, cobrando o argv montado: `--rm`
    presente · rede não é `host` · o socket do Docker **não** é montado · nenhuma variável de
    ambiente com nome que case `SEGREDO_NO_NOME` · nenhum segredo do painel (token da máquina,
    chave do cofre) no ambiente · `--read-only` presente.
  - **Com Docker, na VPS, colado em `verificacao.md`** (critério 6 do briefing): de dentro do
    container, uma chamada a um endereço fora da lista branca **falha**, e a chamada ao
    endereço da lista branca **responde**. As duas saídas coladas.
  - `docker ps` na VPS antes e depois: **26 containers antes, 26 depois** da tarefa terminar.
    O container da tarefa não sobrevive.
  - `python test_imagem.py` → `OK`: nada disso entrou na imagem do painel.
- **armadilha** — a tensão que este plano não esconde: **a sessão precisa da credencial do
  Claude para rodar**, e ela é segredo. Ela não é segredo *do painel* — o critério 6 fala do
  painel —, mas ela entra no container assim mesmo, e isso tem de estar escrito no roteiro,
  não descoberto por acidente depois (é o mesmo espírito de
  `SEGREDO_QUE_A_SESSAO_PRECISA`, `execucao.py:565`).

## 16. Verificação final da fatia

- **objetivo** — rodar o critério de aceitação inteiro, de uma vez, e só então dizer pronto.
- **arquivos** — `docs/esteira/dervs-fatia-2/verificacao.md` (novo).
- **depende_de** — 15 (ou 14, se o portão da 15 for "não").
- **paralelizavel_com** — nenhuma.
- **risco** — baixo.
- **como_provar** — os dez critérios do briefing, em ordem, com a saída **colada**:
  1. `python test_executor.py` → `OK` (critério 1)
  2. `ls requirements*.txt pyproject.toml 2>/dev/null | wc -l` → `0`, e o passo da CI verde
     (critério 2)
  3. `python test_tarefas.py` → `OK`, com o teste da guarda-da-guarda nomeado (critério 3)
  4. `python test_tarefas_nao_publicam.py` → `OK` (critério 4)
  5. o teste do teto em `test_executor.py`, nomeado, provando que o argv nunca foi montado
     (critério 5)
  6. as duas saídas de dentro do container da VPS, e o `docker ps` antes/depois (critério 6)
  7. `python test_imagem.py` → `OK` (critério 7)
  8. **conferido clicando**, com o que foi clicado descrito: o log ao vivo e o botão Parar
     (critério 8)
  9. `git branch -r` mostrando o ramo da tarefa, e a tela do diff conferida clicando
     (critério 9)
  10. `python test_design.py` → `OK`, agora cobrindo o `painel.js` (critério 10)
  - E, além dos dez: duas corridas seguidas da suíte inteira, ambas verdes (duas corridas
    pegam o teste que passa por sorte lendo banco real) · a última corrida da verificação
    automática no GitHub com conclusão `success` · e uma requisição ao fluxo de eventos
    contra `dervs.com.br` **com sessão**, provando que o nginx deixa o fluxo passar.
- **armadilha** — escrever "tudo verificado" com a saída de metade. E escrever no arquivo
  **o que os comandos NÃO provam** — foi o que salvou a etapa 17 da Fatia 1.

---

## Paralelização, dito de uma vez

**Rodam juntas, sem cruzar arquivo:** `1` · `2` · `3` (grupo A) · depois `5`+`8` · depois
`6`+`9` · depois `7`+`10`+`11`.

**Sequencial obrigatório, e por quê:**
- `5 → 6 → 7`: os três editam `servir.py`.
- `11 → 12 → 13`: os três editam `index.html` e `assets/painel.js`.
- `2 → 4`: os dois editam `fila.py`.
- `8 → 9`: a interface antes de quem a usa.
- `15` depois de tudo, e só depois do sim do dono.

**O atrito conhecido:** `.github/workflows/ci.yml` é editado pelas etapas 2, 6, 8, 10 e 15
(um passo por arquivo de teste novo, cobrado pelo passo `:74`). São linhas adjacentes num
arquivo pequeno; se as etapas rodarem em worktrees separadas, o conflito aparece na
mesclagem e é trivial de resolver. **Não o resolva criando uma etapa "de CI" no fim** — uma
etapa que entrega teste sem o passo correspondente fica invisível, e arquivo de teste
esquecido não fica vermelho, fica mudo.

---

## O QUE ESTE PLANO NÃO RESOLVE

- **O botão Parar não é instantâneo, e nenhuma etapa o torna.** Ele viaja no próximo pedido
  de progresso do agente: até 5 segundos, mais o tempo de matar a árvore de processos, mais os
  5 segundos que `parar()` espera pela confirmação. Com o freio de horário fora, ele é o freio
  principal — e o freio principal tem uma janela de até ~10 s. A alternativa (conexão aberta
  do painel para o agente) contraria "o agente não escuta porta nenhuma", que é linha travada
  do §12. **Fica assim, e a tela tem de dizer a verdade sobre isso.**
- **Durante a sessão, o gasto continua desconhecido.** Só o evento `result` traz custo
  (`execucao.py`), e `--max-budget-usd` foi medido estourando 4,5×. O contador da etapa 7 conta
  o que **terminou**. Uma sessão de 40 rodadas que trava consumindo cota não aparece em número
  nenhum enquanto roda — só a duração cresce na tela.
- **"Uma sessão por vez" continua sendo por máquina, não por conta.** Com dois braços, o
  painel pode ter duas sessões vivas ao mesmo tempo (uma no computador, uma na VPS) **e elas
  não enxergam o gasto uma da outra dentro da própria janela** — o teto do dia é conferido
  antes de cada uma começar, lendo o mesmo banco, mas duas que começam no mesmo minuto passam
  as duas. Com a cota da assinatura como recurso escasso, isso é o dobro do consumo no pior
  caso. Não há etapa que resolva; declarado para não ser descoberto na semana de observação.
- **O `_execucao` em memória não desaparece — ele muda de dono.** A etapa 1 põe a tarefa no
  banco **do painel**; no agente, o estado do processo vivo continua sendo um dicionário em
  memória, porque o processo é local e o banco está na VPS. Se o agente morrer no meio, a
  tarefa não retoma: ela é marcada `falha` por falta de notícia (etapa 5). **Retomada de
  verdade — reconectar a um processo `claude` que sobreviveu ao agente — não está nesta
  fatia.** Há duas leituras do item 4 da spec, e esta é a que foi escolhida; a outra seria
  persistir em SQLite local no agente, o que criaria um segundo banco e uma segunda fonte de
  verdade.
- **A sétima tela contraria o §8 da fonte única, que diz "seis, e só seis".** A etapa 13
  assume a sétima e atualiza o documento. **Se o dono ler o §8 como travado**, o consumo vira
  um bloco da tela Painel e a etapa não toca a fonte única — o trabalho é o mesmo, a
  navegação não. **Recomendação: a sétima tela** — "quanto consumimos esta semana" é uma
  pergunta própria, e enfiá-la no Painel disputa espaço com a promessa de "eu sei o que houve
  sem clicar", que é o que a Fatia 1 mediu e ajustou.
- **A credencial do Claude dentro do container da VPS não tem resposta boa.** O critério 6
  exige "sem nenhum segredo do painel no ambiente", e isso o plano cumpre. Mas a sessão só
  roda com o login da assinatura, que é um segredo do fornecedor, do André, e ele entra no
  container. **Ninguém verificou o caso "binário da assinatura rodando num servidor"** — a
  pesquisa achou a regra que proíbe assinatura **com o Agent SDK**, e o DERVS não usa o SDK.
  É a pergunta que vai ao portão da etapa 15, junto com o sim/não da VPS.
- **Nada aqui prova que o dono vai confiar no verde.** O plano prova que o vermelho espera
  clique e que o diff aparece em português. Se ele abrir a tela, vir uma tarefa verde que já
  rodou sozinha e sentir que perdeu o controle do próprio código, todos os dezesseis
  `como_provar` continuam verdes e a fatia falhou assim mesmo. A revisão marcada de sete dias
  (spec, `duvidas_para_o_dono`) é onde isso aparece — e ela **não é uma etapa deste plano**,
  é um compromisso de calendário que depende de alguém lembrar.
- **A estimativa de esforço não existe.** Nenhuma etapa tem prazo, e três (5, 9, 11) são
  visivelmente maiores que as outras. Se alguma precisar quebrar em duas durante a execução, o
  grafo aguenta — as trilhas são disjuntas por arquivo, e é por isso que estão desenhadas
  assim.
