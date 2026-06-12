# Hub de Projetos

Painel local, leve e 100% seu para administrar e acompanhar todos os seus projetos —
conectado ao **GitHub** (via `gh`) e ao **Claude Code**. Sem Docker, sem nuvem.
Roda na sua máquina, só em `127.0.0.1`.

> Dependências: o painel em si é Node puro. A **Lousa** (terminais embutidos) usa
> `node-pty` + `ws` no servidor e o `xterm.js` (vendorizado em `public/vendor`, offline)
> no navegador. O `Iniciar Hub.bat` roda `npm install` sozinho na primeira vez.

## Como usar

**Duplo clique no atalho "Hub de Projetos"** na área de trabalho (ou em `Iniciar Hub.bat`).
Ele sobe o servidor e abre o navegador em `http://127.0.0.1:4321`. Deixe a janela preta
aberta enquanto usar; feche-a para encerrar.

Pelo terminal: `cd C:\Users\andre\hub ; node server.js`

## Visão de Projetos

Cada projeto mostra status **ao vivo**:
- **Branch** atual e **alterações** não commitadas
- **Ahead/behind** vs remoto (↑ por enviar, ↓ por baixar)
- **Último commit** (mensagem, quando, autor)
- **GitHub**: PRs e issues abertas (em segundo plano)
- Ordenar por atividade / alterações / nome · busca instantânea (`/`) · **↻ Sincronizar**

**Ações por card:**
- **💬 Chat** — abre o painel lateral pra conversar com o Claude (veja abaixo)
- **✦ Terminal** — abre o Claude Code num terminal na pasta
- **▶ Tarefa** — escreve uma tarefa e o Claude já inicia com ela, num terminal
- **VS Code**, **Pull** (`git pull --ff-only`), **GitHub ↗**

## Painel do projeto (clique em 💬 Chat)

Abre um drawer lateral com três abas:

- **💬 Chat** — converse com o Claude **dentro do hub**, prompt e resposta ali mesmo.
  O Claude roda na pasta do repositório em modo **somente-leitura** (`Read`, `Grep`,
  `Glob`): ele lê o código pra responder, mas **não executa comandos nem altera
  arquivos**. Ctrl+Enter envia. O contexto da conversa continua entre mensagens.
- **✓ Tasks** — as **issues abertas do GitHub** daquele repo, com labels e link.
- **↻ Sync** — liga o **sync automático**: instala um hook `post-commit` no repositório
  que avisa o Hub a cada commit. (O Hub também sincroniza sozinho a cada 60s.)

## Lousa (canvas de agentes)

Botão **🪧 Lousa** no topo (lousa do **Portfolio**) ou no card de cada projeto
(lousa **daquele projeto**). É a canvas estilo Cursor: cada agente vira um **node
arrastável com um terminal Claude embutido**, e você liga os nodes com linhas.

- **+ Agente** — escolhe um **papel** (Orchestrator · Code Reviewer · Tester · Dev ·
  Claude puro · Shell) e o **projeto** (pasta onde roda). Cada papel entra com um
  system-prompt próprio. Opcionalmente já começa com uma tarefa.
- **Terminal de verdade, persistente** — a sessão vive **no servidor** (via `node-pty`),
  não numa janela externa. Fechar a aba ou recarregar o navegador **não derruba a
  sessão**: ao reabrir, o terminal se reanexa e mostra todo o histórico (scrollback).
  É o que resolve o "desconectar a sessão" das janelas `wt`.
- **Conectar** (⛓) — clique no ⛓ de um node e depois no node de destino pra desenhar a
  ligação (linha tracejada). `Esc` cancela.
- **Notas** (post-its), **pan** (arraste o fundo), **zoom** (scroll). Tudo — posições,
  ligações, notas, zoom — é salvo por lousa em `canvas.json`.
- **■** encerra o processo do node · **✕** remove o node · o **⟳ Reabrir** aparece se a
  sessão tiver morrido (ex.: o servidor foi reiniciado).

O comando de cada node é o `claude` por padrão, mas a infra é agnóstica: dá pra apontar
pra qualquer CLI (OpenHands, hermes-agent, etc.) editando os papéis em `pty-sessions.js`.

### Orquestração: o agente controla a lousa (ao vivo)

Os agentes-de-papel nascem sabendo **controlar a própria lousa** por um CLI (`lousa.js`),
e o que eles fazem **aparece na hora** na tela (o servidor é a fonte da verdade e transmite
por SSE). No Bash do agente:

- `node "$HUB_LOUSA" spawn --role tester --task "..."` — cria outro agente, já **ligado** a ele
- `node "$HUB_LOUSA" connect <nodeId>` — desenha uma conexão
- `node "$HUB_LOUSA" list` — lista os nodes da lousa
- `node "$HUB_LOUSA" note "..."` / `status "..."` — post-it / muda o próprio título

O contexto (board/node/porta) vem por **env** (`HUB_BOARD`, `HUB_NODE`, `HUB_PORT`, `HUB_LOUSA`),
injetado quando o agente é criado. Ex.: peça ao Orchestrator *"divida o trabalho: crie um
reviewer e um tester e diga a cada um o que fazer"*.

> ⚠️ **Autonomia total:** os agentes abrem com `--dangerously-skip-permissions` — rodam
> **qualquer** ferramenta (editar/apagar arquivos, bash, git) **sem pedir confirmação**, na
> **pasta real do projeto**. Atenção a prompt-injection via conteúdo do repo. Para desligar,
> ponha `SKIP_PERMISSIONS = false` em `pty-sessions.js` (aí cada ação volta a pedir confirmação).

### Transições de câmera (estilo Maestri)

Câmera com animação suave: **duplo-clique num node** aproxima nele; **duplo-clique no fundo**
(ou botão **⊡ Tudo**, ou tecla `0`) afasta e enquadra tudo; abrir uma lousa faz um **zoom-in
de entrada**. "Aproxime no agente que precisa de atenção, afaste pra ver o quadro todo."

> Nota: as sessões vivem **em memória** enquanto o servidor está de pé. Reiniciar o
> `node server.js` encerra os processos; o **layout** da lousa permanece e cada node
> oferece **Reabrir**. Recarregar só o **navegador** reconecta sem perder nada.

## Insights (post-its)

Aba **Insights** no topo: um quadro de notas coloridas pra ideias, lembretes e
descobertas. Adicione com cor, opcionalmente fixe a um projeto, edite clicando no texto,
apague no ×. Tudo persistido em `insights.json`.

## Adicionar / remover projetos

Edite `projects.json`:

```json
{ "id": "meu-app", "name": "Meu App", "path": "C:\\caminho\\do\\repo", "tags": ["api"] }
```

O `path` precisa ter `.git`. Projetos cuja pasta sumiu são ignorados. Salve e clique em
**↻ Sincronizar**.

## Segurança

- O servidor escuta **apenas** em `127.0.0.1`.
- **Guarda de Host/Origin**: requisições com `Host` diferente do hub ou vindas de outra
  origem (`Origin`/`Referer`) são bloqueadas — protege contra CSRF e DNS-rebinding de
  sites maliciosos abertos no seu navegador.
- O **chat é somente-leitura** (sem `--dangerously-skip-permissions`): não é uma
  superfície de execução de comandos arbitrários.
- As ações recebem só o **id** do projeto (o caminho vem da config do servidor, nunca do
  navegador) e um enum fixo de comandos. Texto de tarefa vai como argumento, nunca
  interpolado em shell.

> ⚠️ **Concorrência do Claude:** o chat do hub usa o seu config padrão do Claude Code.
> Evite usá-lo **ao mesmo tempo** que outra sessão `claude` está iniciando — dois
> processos escrevendo o `~/.claude.json` juntos podem corrompê-lo (limitação do próprio
> Claude Code no Windows). Na prática: use o chat do hub quando não estiver subindo outra
> sessão Claude no mesmo instante.

## Config

- Porta: `HUB_PORT` (padrão `4321`).
- No PATH: `node`, `git`, `gh` (autenticado: `gh auth status`), `wt`, `code`, `claude`.
