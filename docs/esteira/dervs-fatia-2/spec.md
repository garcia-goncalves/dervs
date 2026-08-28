# Spec — DERVS, Fatia 2: o painel ganha braços

Fase 2 da esteira, escrita em 28/08/2026 pelo Sintetizador, a partir de três pesquisas
externas e um levantamento do terreno. Briefing aprovado pelo dono no portão 1 e commitado
em `f73772f`.

## problema

O DERVS mede bem e não age. Ele diz ao dono que o código no ar divergiu, que a verificação
quebrou, que há 203 pendências — e então para. O dono, que não opera terminal, fica com um
diagnóstico preciso e nenhuma forma de agir sobre ele sem chamar alguém.

A dor não é "falta uma funcionalidade". É que **um painel que só aponta problema transfere
o trabalho inteiro para quem menos pode fazê-lo**. E há um segundo problema, invisível até
o levantamento: **a peça que resolve isso já foi construída e está desligada** — o executor
de sessões do Claude Code existe em `execucao.py`, com 805 linhas de teste, e nenhuma rota
o alcança. O DERVS tem um braço na gaveta.

## solucao

**Religar o braço, com um semáforo na frente e dois lugares onde ele pode trabalhar.**

Quatro peças, nesta ordem de dependência:

**1. O fio de volta (painel → agente).** Hoje o agente só empurra medição: `POST
/agente/relatorio` (`agente/enviar.py:227` → `servir.py:1289`). A resposta 200 já é um
dicionário (`servir.py:1318-1320`). Ela passa a carregar a tarefa pendente daquela máquina.
**Nenhuma conexão nova, nenhuma porta aberta, nenhuma inversão de sentido** — o agente
continua sendo quem pergunta. Uma rota nova, `POST /agente/resultado`, de classe `maquina`,
recebe o que voltou.

**2. O semáforo.** A tabela `fila` (`banco.py:164`) ganha `cor`, `aprovado_por`,
`aprovado_em`, `maquina_id`, `ramo` e `executor`; a máquina de estados ganha um estado novo
entre `esperando` e `rodando`. Verde vai direto; vermelho para e espera clique.
**Toda regra nasce vermelha** e o dono repinta na tela — o inverso erra caro. `publicar`
não é repintável.

**3. O segundo braço.** O mesmo `agente/enviar.py` instalado na VPS, com uma coluna nova em
`maquina` dizendo se aquela máquina executa. Na VPS a sessão roda dentro de um container
descartável, sem segredo no ambiente e com saída de rede em lista branca.

**4. A tela ao vivo.** SSE (`text/event-stream`) sobre o `ThreadingHTTPServer` que já
existe, alimentado por `execucao.estado(desde)` (`execucao.py:1198`), que já foi desenhado
para entrega incremental. Substitui o `setInterval(…, 60000)` de `assets/painel.js:1109`.

**Por que o agente executa, e não o servidor.** Isso não é cautela decorativa: **preserva o
vigia `test_rotas.py` intacto.** O servidor continua sem importar `execucao` e sem alcançar
`subprocess` — ele conversa só com `banco`. A trava que proíbe rota que executa comando
**não precisa ser enfraquecida em nenhum ponto da Fatia 2.** Uma arquitetura que exigisse
afrouxar aquele teste seria a arquitetura errada.

## o_que_ja_existe

Com caminhos reais. Sem caminho, não conta.

| Peça | Onde | Estado |
|---|---|---|
| **Executor de sessão do Claude Code** | `execucao.py` (1215 linhas), `test_execucao.py` (805) | **Pronto e testado.** `montar_comando` (`:163`), `iniciar` (`:833`), `parar` (`:1145`), `estado(desde)` (`:1198`), `publicar` (`:737`) |
| Prompt com dado hostil isolado | `execucao.py:130` (`GABARITO`), `so_dado` (`:256`), `montar_prompt` (`:264`) | Pronto. Bloco `<dados-coletados-nao-confiaveis>`, etiqueta de fechamento neutralizada |
| Cópia isolada do repositório | `criar_copia` (`execucao.py:592`) | Pronto. `git clone` local **com `origin` removido** — a filha não alcança o GitHub |
| Ambiente peneirado de segredo | `ambiente_da_filha` (`:570`), `SEGREDO_NO_NOME` (`:558`) | Pronto |
| **Barreira de ferramenta** (hook `PreToolUse`) | `barreira.py` (439), `test_barreira.py` | **Pronto.** Lista branca de programa (`:43`) e de subcomando de `git` (`:86`) — lista negra perdia para `git -c alias.pwn='!curl …'` |
| Fila, prioridade, tentativas | `fila.py` (302), `test_fila.py` | Pronto. `esperando → rodando → ok\|falha`, `MAX_TENTATIVAS = 2` |
| **Freio de gasto de dois níveis** | `cabe_no_teto` (`fila.py:78`), `teto_da_sessao` (`:96`), tabela `gasto` (`banco.py:186`) | Pronto. Dia **local**, não UTC (`hoje_local`, `:41`) |
| Canal autenticado painel↔agente | classe de acesso `maquina`, `Hub._relatorio` (`servir.py:1289`), teto 60/máquina (`:1287`) | Pronto. Token só em cabeçalho, nunca em query; sem redirect (`agente/enviar.py:153`) |
| Padrão de migration | `banco.migrar` (`banco.py:416-660`) | Pronto. `PRAGMA table_info` + `BEGIN IMMEDIATE` + releitura dentro da transação |
| Diff da cópia | `diff_da_copia` (`execucao.py:690`) | Pronto — falta a tela que o traduz |
| Travas de diff pós-execução | `diff_mexeu_em_teste` (`fila.py:206`), `env_example_tem_valor` (`:246`) | Pronto |

**Nasce do zero:** o fio de volta; o semáforo inteiro (coluna, estado, aprovação, tela); a
coluna `executa` em `maquina`; o container efêmero na VPS; **a persistência da execução**
(hoje `_execucao` é um dicionário em memória, `execucao.py:790` — um recurso por máquina,
sem histórico nem retomada, e a Fatia 2 tem dois braços); o SSE; a interface `Executor` com
duas implementações previstas; o vigia irmão do `test_rotas.py` que varre as tarefas; a
tela do diff em português; e a chave de API no servidor.

## fontes_externas

Consultadas em 28/08/2026.

- Modo headless do Claude Code — https://code.claude.com/docs/en/headless
- Ambientes de sandbox, recomendação oficial — https://code.claude.com/docs/en/sandbox-environments
- SDK Python (lido o `pyproject.toml`: `anyio`, `sniffio`, `mcp`, `jsonschema`, `typing_extensions`) — https://github.com/anthropics/claude-agent-sdk-python
- Uso do Agent SDK com plano de assinatura — https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
- Preços — https://platform.claude.com/docs/en/about-claude/pricing
- Codex, modo não interativo — https://learn.chatgpt.com/docs/non-interactive-mode
- Codex, sandbox (Landlock/seccomp) — https://developers.openai.com/codex/concepts/sandboxing
- Codex CLI, Apache-2.0 — https://github.com/openai/codex
- Ataque à claude-code-action (jan/2026), Microsoft Security — https://www.microsoft.com/en-us/security/blog/2026/06/05/securing-ci-cd-in-agentic-world-claude-code-github-action-case/
- "Comment and Control" (15/04/2026) — https://oddguan.com/blog/comment-and-control-prompt-injection-credential-theft-claude-code-gemini-cli-github-copilot/
- Black Hat USA (05/08/2026), CVE-2026-54316 e CVE-2026-12537 — https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-coding-agent-cicd-secrets-20260808-csa/
- Agente rodando à noite, US$ 437 — https://earezki.com/ai-news/2026-04-29-i-let-my-ai-agent-run-overnight-it-cost-437/
- Guardrails de cobrança, InfoQ (07/2026) — https://www.infoq.com/news/2026/07/ai-agents-billing-guardrails/
- Custo de manter portal de desenvolvedor; US$ 4,2 mi e 64% contornando — https://hackernoon.com/internal-developer-platforms-are-booming-but-adoption-is-failing
- "Backstage is dead" (Port) — https://newsletter.port.io/p/backstage-is-dead
- xterm.js (MIT) — https://github.com/xtermjs/xterm.js · ttyd (MIT) — https://tsl0922.github.io/ttyd/
- perfect-freehand (MIT) — https://github.com/steveruizok/perfect-freehand
- **Armadilha de licença:** tldraw ≥ 2.0 deixou de ser MIT — https://tldraw.dev/blog/license-update-for-the-tldraw-sdk

## fora_de_escopo

O corte do briefing, já aprovado pelo dono: terminal no navegador, o Codex ligado, a lousa,
o canivete de 15 ferramentas avulsas, editor de código no navegador, o ferramental do
Claude (§10, Fatia 4), integrações novas, cadastro público.

Acrescentado nesta fase, com motivo:

- **Reescrever `test_rotas.py`.** O levantamento mostrou que a arquitetura escolhida não
  exige afrouxá-lo. Se alguém precisar mexer naquele arquivo, é sinal de que o desenho
  saiu do trilho — trate como alarme, não como tarefa.
- **Relaxar `barreira.py` para a sessão filha.** `docker` está em `SAEM_DA_MAQUINA`
  (`barreira.py:57`) e continua barrado **para a sessão filha**. Quem cria o container é o
  agente, que é código nosso — não a IA. As duas barreiras são configurações distintas e
  não se misturam.
- **Execução paralela.** Um braço, uma sessão por vez, como já é (`decidir_pedido`,
  `execucao.py:409`). Duas sessões simultâneas não enxergam o gasto uma da outra.

## contradicoes_resolvidas

1. **"Claude monitora, Codex executa" (o dono) × a medição.** Venceu a medição, e é quase o
   inverso: Claude escreve melhor código multiarquivo (87,6% × 85,0%, SWE-bench Verified),
   Codex opera melhor terminal e infra (81,8%, Terminal-Bench 2.0). E **monitorar não é
   trabalho de IA nenhuma** — medir é código determinístico, sob pena de quebrar a segunda
   lei do repositório. O dono foi informado e concordou.
2. **"Claude Code rodando 100% nele" × zero dependências.** Venceu `subprocess` sobre o
   binário `claude`, que é o que `execucao.py:163` já faz. O SDK oficial em Python traz 5
   dependências para embrulhar o mesmo subprocesso — e deixaria a CI vermelha de propósito.

2b. **"A assinatura não serve, precisa de chave de API" (a pesquisa) × a medição local e a
   decisão do dono.** *Contradição levantada e resolvida no mesmo dia — o Sintetizador
   errou primeiro.* A pesquisa achou a regra da Anthropic que proíbe token de assinatura
   **com o Agent SDK**, e eu a generalizei para o binário. Errado: o DERVS não usa o SDK, e
   `execucao.py:20` registra que o executor **já roda com login por assinatura (OAuth)**
   desde 24/08. O dono decidiu em 28/08 usar a Max 20x que as duas pessoas já pagam, e
   recusou a chave de API por custo. Venceu a assinatura, com duas consequências escritas:
   `--bare` continua fora (só aceita chave de API), e **o recurso escasso passa a ser cota,
   não dinheiro**. Ver `contradicoes` do freio, abaixo.
3. **O teto como cerca × a medição de campo.** `--max-budget-usd` **não** é cerca: medido
   estourando 4,5× (teto US$ 0,10, gasto US$ 0,4455 — `execucao.py:63-66`). A garantia real
   é matar o processo (`parar()` → `_matar_arvore`, `:933`). Pior: **só o evento `result`
   traz custo**, então durante a sessão o gasto acumulado é desconhecido. Consequência
   escrita no critério de aceitação: *travar antes de disparar* protege contra o gasto já
   encerrado, e o que limita a sessão em curso é `--max-turns` mais um teto de sessão
   pequeno mais o dedo no gatilho de `parar()`.
4. **Executar na VPS × "nunca abrir terminal na internet aberta" (§7).** Venceu o §7 sem
   emenda: quem executa é o agente, que não escuta porta. A VPS ganha um agente, não uma
   rota.
5. **`--bare` recomendado pela pesquisa × a medição local.** A pesquisa recomendou `--bare`
   (evita executar hooks e MCPs de repositório não confiável). A medição colada em
   `execucao.py` diz que **`--bare` não funciona com login de assinatura**. Venceu a
   medição, e a proteção equivalente já está em uso: `--setting-sources ""` derruba o
   `.claude/settings.json` do repositório sendo consertado, e `--strict-mcp-config` com
   `mcpServers` vazio derruba os MCPs. **Reavaliar quando a chave de API entrar** — pode ser
   que `--bare` volte a funcionar, e aí ele soma.

## duvidas_para_o_dono

**A dúvida do teto em reais foi respondida em 28/08 e virou outra dúvida.** O dono decidiu
usar a assinatura Max 20x — ver contradição 2b. Com isso o freio muda de natureza, e a
pergunta que sobra é esta:

**Quanta cota o painel pode consumir sem pedir licença?** O Max 20x limita por janela de 5
horas e por semana; as duas pessoas usam a mesma conta o dia inteiro, em muitos projetos.
O modo de falhar deixou de ser financeiro e virou operacional: **o painel esgota a janela e
o Claude para para os dois no meio do expediente.** Um teto em reais não protege disso —
ele conta a moeda errada.

O freio precisa de três números, e o dono decide o perfil:

1. **Sessões automáticas por dia** (só o verde; o vermelho ele aprovou olhando).
2. **Rodadas por sessão** — hoje `MAX_TURNOS = 40` (`execucao.py`), dimensionado para "o
   laço que der errado não rodar a noite inteira". Para trabalho desassistido é folgado.
3. **A janela de silêncio** — as horas em que o painel não encosta na cota, porque são as
   horas em que eles trabalham.

**RESPONDIDA pelo dono em 28/08/2026: sem freio de horário. Observar por uma semana.**

A recomendação do Sintetizador era outra (janela de silêncio das 22h às 7h, 6 sessões por
noite, 15 rodadas). O dono ouviu o alerta — *o painel disputa cota com o trabalho dele, e o
dia ruim custa horas de duas pessoas* — e decidiu observar antes de limitar. **Decisão
tomada, não se relitiga.** O alerta não se repete a cada sessão.

**O que essa escolha obriga a construir, e não é escopo extra — é o que a torna executável:**

1. **O contador de consumo.** Cada sessão registra início, fim, duração, rodadas gastas,
   resultado e projeto. Sem isso, "observar" é uma intenção. A tabela `fila` já guarda
   parte (`iniciado_em`, `terminado_em`, `custo_usd`); faltam rodadas e um lugar de leitura.
2. **A tela que responde "quanto o painel consumiu esta semana"** — por dia, por projeto e
   por regra, para a semana de observação virar decisão em vez de impressão.
3. **O botão Parar em toda tela onde há sessão viva**, não só na tela da tarefa. Ele é a
   única garantia dura que existe (`parar()` → `_matar_arvore`, `execucao.py:933,1145`), e
   com o freio de horário fora ele deixa de ser conveniência e vira o freio principal.
4. **Revisão marcada.** Ao fim de sete dias de uso real, o número volta ao dono com os
   dados na mão. Fica escrito aqui para não depender de alguém lembrar.

**Continua valendo:** `MAX_TURNOS = 40` como está, o teto em reais no código como rede para
o dia em que uma chave de API entrar, e uma sessão por vez por máquina (`decidir_pedido`,
`execucao.py:409`) — que, sem janela de silêncio, passa a ser a trava que mais segura o
consumo.
