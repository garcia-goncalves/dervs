# Plano de execução — o Claude dentro do painel (entrega 1: o botão "Resolver")

> Fase 4 da esteira `claude-no-painel`. Escrito em 24/08/2026, sobre `briefing.md`,
> `spec.md` e `design.md` aprovados, mais verificação pontual no código e três
> medições feitas na máquina.

## Resumo

São **7 etapas**. Duas frentes correm em paralelo: a trilha Python (etapas 1→2→3→4,
todas em `execucao.py` e depois `servir.py`) e a trilha de tela (etapa 5, só estrutura e
CSS de `index.html`). Só a etapa 5 é genuinamente paralela — as outras seis são
sequenciais, porque `execucao.py`, `servir.py` e `index.html` são cada um tocado por mais
de uma etapa e nenhum par pode ser editado ao mesmo tempo. O **caminho crítico é
1 → 2 → 3 → 4 → 6 → 7**, com a etapa 5 encaixando em qualquer ponto antes da 6. A etapa 4
é a que destrava tudo do lado da tela: até ela existir, `test_servir.py` proíbe o
`index.html` de mandar o comando novo.

## Contexto verificado

- **Índice do grafo está em dia.** `head_sha` do índice = `32933d5`, igual ao `HEAD` no
  momento do planejamento. Árvore limpa. Nenhuma análise aqui está apoiada em índice velho.
- **A CI roda três suítes nomeadas, uma por passo** (`.github/workflows/ci.yml`):
  `python test_regras.py`, `python test_coletar.py`, `python test_servir.py`, mais
  `py_compile` de `banco.py regras.py coletar.py coletar_github.py coletar_pesado.py
  servir.py`. **Suíte nova e módulo novo não entram sozinhos** — os dois passos precisam
  ser editados à mão.
- **O passo "Nada de dependencia externa"** falha o build se existir `requirements*.txt`
  ou `pyproject.toml`. Confirmado no YAML.
- **`claude` na máquina é 2.1.243** e aceita `--bare`, `--allowedTools`,
  `--disallowedTools`, `--max-budget-usd`, `--permission-mode`, `--add-dir`,
  `--output-format`. `gh` 2.78.0, `git` 2.52.0.
- **`gh pr create` NÃO tem `--json`.** A spec (peça 7) diz `gh pr create --json url`;
  o `--help` da versão instalada lista `--base --body --body-file --fill --head --title`
  e nenhum `--json`. A URL sai **no stdout**. Corrigido no plano: função pura
  `url_do_pr(saida)` que pesca a última linha começando por `https://`, com
  `gh pr view --json url` como plano B.
- **`--bare` está fora** (medição do coordenador): sem `ANTHROPIC_API_KEY`
  ele devolve `is_error=True`, `terminal_reason='api_error'`,
  `result='Not logged in · Please run /login'`. Substituído por
  `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` + `--allowedTools` +
  `--disallowedTools`, combinação **medida funcionando** (`is_error=False`,
  `terminal_reason='completed'`). Consequência a registrar sem maquiagem: os hooks do
  `.claude/settings.json` do projeto-alvo (versionado, logo presente na cópia isolada) e
  a configuração do usuário **vão rodar** na sessão filha. Isso enfraquece a mitigação do
  risco 2 do briefing e é risco declarado, não resolvido.
- **Teto sobe para US$ 3.** Medido: um turno trivial sem MCP custa **US$ 0,2256**
  (21.471 tokens de escrita de cache); herdando os MCPs da máquina, **US$ 0,4455**. US$ 1
  pagaria ~4 turnos triviais. E `--max-budget-usd` **não é limite duro**: com teto 0,10 a
  execução terminou em `total_cost_usd=0,44548` com `terminal_reason='budget_exhausted'`
  — estouro de 4,5×. O "Parar" é a única garantia real, e a tela tem de dizer que o teto é
  aproximado.
- **Fluxo confirmado ao vivo:** `{"type":"system","subtype":"init"}` →
  `{"type":"assistant"}` → `{"type":"result","subtype":"success"}`. O `result` traz
  `is_error`, `terminal_reason` (`completed` | `api_error` | `budget_exhausted`),
  `result`, `total_cost_usd`, `usage`, `session_id`, `num_turns`, `permission_denials`,
  `duration_ms`. **`subtype` não é confiável** (visto `success` junto de `is_error:True`):
  a máquina de estados lê `is_error` + `terminal_reason`.
- **A trava de execução no cliente existe e é o que a spec manda matar:**
  `let ESTADO = null, ocupado = false;` (`index.html:279`) e
  `if (ocupado){ recado("Espere a ação anterior terminar."); return; }`
  (`index.html:326`).
- **O log de erro some em 9 s:** `recado._t = setTimeout(... , erro ? 9000 : 4000)`
  (`index.html:306`). O painel de execução não usa `recado()`.
- **A pendência tem UMA ação só** (`regras.py:40-49`, campo `acao`), e o botão é
  desenhado a partir dela em `itensEm()` (`index.html:409-413`). O "Resolver" é botão
  **novo, ao lado**, não substituição — e por isso não passa por `regras.py`.
- **Nem toda pendência tem projeto:** `cota_actions` nasce com `projeto=""`
  (`regras.py:222-230`, comentário "Projeto '' e proposital"). O critério 1 do briefing
  ("cada pendência exibe um botão Resolver") não é literalmente executável.
- **A cadeia de segurança do POST está onde a spec disse:** Host `servir.py:518-519`,
  Origin `servir.py:593`, `compare_digest` `servir.py:595`, corpo ≤16 KiB
  `servir.py:600`. `executar_acao` trata `recoletar`, `silenciar` e `grafo_ligar` fora do
  dict `ACOES` (`servir.py:204-227`) — é esse molde que `resolver` e `parar` seguem.
- **`origem_aceita(Sec-Fetch-Site)` já existe** e é usada no proxy (`servir.py:612`).
  É a peça certa para o GET novo — ver o risco do `Origin` abaixo.
- **`PaletaNaoInventaComando` extrai com regex `comando\s*:\s*["\']([a-z_]+)["\']`**
  do `index.html` e cruza com `set(servir.ACOES) | FORA_DO_DICT`, onde
  `FORA_DO_DICT = {"recoletar", "silenciar", "grafo_ligar"}` (`test_servir.py:274`).
  Confirmado: o HTML mandar `comando:"resolver"` antes do servidor conhecê-lo **quebra a
  CI**.

### Premissas do pedido que NÃO se confirmaram

1. **`gh pr create --json url` não existe** nesta versão do `gh` (spec, peça 7).
2. **`--bare` não é utilizável** com a autenticação do dono (spec, contradição 8).
3. **`--max-budget-usd` não é teto duro** (spec, contradição 3 e risco 4 do briefing
   tratavam-no como "vira uma flag").
4. **US$ 1 de teto é baixo demais** para o custo real de ligar a sessão (spec,
   `duvidas_para_o_dono` nº 2). Vai a US$ 3.

### Duas ambiguidades — as duas leituras, e a recomendação

**A. A tabela `execucao` no banco entra ou não?** A spec diz, em `o_que_ja_existe`, "a
tabela `execucao` precisa nascer certa"; e diz, em `fora_de_escopo`, "Histórico de
execuções no banco … fica para depois" e "Retomar execução depois de reiniciar o painel"
também fica para depois.

- *Leitura 1 (recomendada, e adotada):* **nenhuma tabela nova.** O estado da execução vive
  em memória no processo do servidor, como `_grafo_proc` já vive. Sem histórico, sem
  retomada — exatamente o que o `fora_de_escopo` corta. `banco.py` não é tocado, e a
  frase da spec sobre a tabela lê-se como nota de viabilidade para a entrega 2.
- *Leitura 2:* criar `CREATE TABLE IF NOT EXISTS execucao (...)` em `banco.py:32-54` já
  nesta entrega, mesmo sem ninguém ler, para não pagar migração depois.
- **Adotada a 1**, porque a 2 escreve código que nenhum critério dos 12 exerce, e
  código não exercido nasce errado.

**B. "Cada pendência exibe Resolver" — cada uma mesmo?** `cota_actions` não tem projeto e
`Ajudei-Saude` está desligado por decisão do dono.

- *Leitura 1 (recomendada, e adotada):* o botão aparece **só onde há o que resolver** —
  pendência com `projeto` não vazio e projeto fora da lista de bloqueio. As outras seguem
  com o botão de ação atual apenas.
- *Leitura 2:* o botão aparece sempre e, ao ser clicado no caso impossível, explica por
  que não dá.
- **Adotada a 1**: botão que existe para dizer "não" é o oposto do invariante 1 de
  `regras.py` ("toda pendência tem uma ação"). A barreira dura fica **no servidor** (o
  cliente só esconde).

## Riscos conhecidos antes de começar

1. **Etapa 6 antes da 4 quebra o repositório.** `PaletaNaoInventaComando` falha no
   instante em que `comando:"resolver"` aparece no HTML sem `resolver` na lista branca do
   servidor. Se acontecer: não conserte editando o teste — mescle a etapa 4 primeiro.
2. **Hook do projeto-alvo abortando a sessão filha.** Sem `--bare`, os hooks do
   `~/.claude` e do `.claude/settings.json` do alvo rodam. O `block-no-verify.py` do dono
   já barra formas de `git push`, e o `actions-budget-guard.py` barra escrita de workflow.
   Sintoma: a sessão termina com `permission_denials` não vazio e nenhum arquivo tocado.
   Se der: registre a saída crua no log (o critério 8 cobre isso) e reporte — **não
   desligue hook do dono por conta própria**.
3. **Custo ao vivo pode não ter fonte nos eventos intermediários.** Só foi confirmado
   `usage` no evento `result`. Se os eventos `assistant` não trouxerem `usage`, o número
   ao vivo fica parado até o fim, e o critério 7 ("ao vivo e ao final") cai pela metade. A
   etapa 3 tem uma medição obrigatória para isso, feita **antes** de escrever o acumulador.
4. **`taskkill` não existe na CI.** Todo teste de "Parar" tem de ser sobre a função pura
   que **monta** o comando de morte, nunca sobre executá-lo. Mesma regra para
   `creationflags` e para caminhos `C:\`.
5. **Worktree em `~/.cache` com caminho longo.** O limite de 260 caracteres do Windows já
   quase estoura em projetos .NET aninhados. O id de pasta tem 8 caracteres por isso; se
   `git worktree add` falhar com nome longo, o sintoma é erro do git, não exceção Python —
   trate como falha normal e mostre a saída.
6. **Resolver o próprio `painel-projetos` durante o desenvolvimento.** É o caso de teste
   mais provável (contradição 7 da spec) e é o único em que a cópia isolada é do repo que
   está sendo editado pelas outras etapas. Faça o teste ponta a ponta da etapa 7 **depois**
   de commitar tudo, com árvore limpa.
7. **Duas etapas atrasadas viram uma só.** Se a etapa 2 e a 3 forem executadas por agentes
   diferentes ao mesmo tempo em `execucao.py`, o merge é conflito de arquivo inteiro.
   Elas são sequenciais e isso não é negociável.

---

## Etapas

### Etapa 1 — `execucao.py` nasce puro, com a suíte e o passo de CI

**Objetivo:** existe um módulo novo com todas as decisões testáveis do recurso — qual
comando roda, qual prompt é montado, qual frase aparece, qual estado é o próximo, quanto
custou — e a CI passa a cobrá-las. Nada ainda executa nada.

**Arquivos:** `execucao.py` (novo), `test_execucao.py` (novo), `.github/workflows/ci.yml`.

**Contexto:**

- Convenção da casa, obrigatória: arquivo abre com `# -*- coding: utf-8 -*-`,
  identificadores e comentários **em português sem acento**, strings visíveis ao dono
  **com** acento; zero import fora da biblioteca padrão; funções puras separadas do I/O
  porque a CI é `ubuntu-latest`.
- Molde de teste a copiar: `test_servir.py:1-16` (docstring de módulo dizendo por que a
  suíte existe, `if __name__ == "__main__": unittest.main(verbosity=2)`), e **cada classe
  com docstring contando o caso real que a originou, com data** — veja
  `test_servir.py:52-60` como exemplo do tom.
- Textos literais: **todas as 7 frases de status, as 4 manchetes de falha e os corpos**
  estão em `docs/esteira/claude-no-painel/design.md`, seção `textos`. Copie literalmente,
  com acento. Duas correções sobre o design: (a) o corpo da falha por teto interpola
  `em_reais(TETO_USD)` em vez do literal "R$ 5,00", porque o teto mudou; (b) acrescente à
  nota de custo que **o teto é aproximado** (medido: estouro de 4,5×).

**Fazer:** criar `execucao.py` contendo, nesta ordem, as constantes e as funções puras
abaixo — e nada de I/O (`subprocess`, `Popen`, `Path.home()`, `threading` ficam para as
etapas 2 e 3):

Constantes, cada uma num lugar só:

- `TETO_USD = 3.0` — com comentário citando a medição de 24/08/2026 (turno trivial
  US$ 0,2256 sem MCP, US$ 0,4455 com MCP) e o fato de o teto não ser duro.
- `USD_BRL` — cotação constante, com a data no comentário (decisão do dono: constante no
  código, num lugar só).
- `MAX_TURNOS` — limite de turnos.
- `FERRAMENTAS_OK` / `FERRAMENTAS_PROIBIDAS` — listas brancas/negras de `--allowedTools`
  e `--disallowedTools`.
- `PROJETOS_BLOQUEADOS = {"ajudei-saude"}` — comparação em minúsculas; decisão do dono no
  portão de risco.

Funções puras (cada uma com teste próprio):

- `montar_comando(prompt, teto_usd, turnos)` → lista de argv começando em `"claude"` e
  contendo `-p`, `--output-format stream-json`, `--verbose`,
  `--strict-mcp-config`, `--mcp-config '{"mcpServers":{}}'`, `--max-budget-usd`,
  `--allowedTools`, `--disallowedTools`, `--max-turns`. **Não use `--bare`** — medido:
  falha com `Not logged in`. O prompt entra como argumento posicional, último.
- `montar_prompt(pendencia)` → string, a partir de gabarito **fechado** no módulo,
  interpolando só `regra`, `projeto`, `texto`, `detalhe` da pendência. Nenhum campo vindo
  do corpo do POST entra aqui. O gabarito manda a sessão terminar com **uma frase em
  português por arquivo tocado** (é daí que sai o modo "resumo", sem chamada extra ao
  modelo — spec, contradição 6).
- `pode_resolver(pendencia)` → `False` quando `projeto` é vazio ou está em
  `PROJETOS_BLOQUEADOS` (comparação insensível a caixa); `True` no resto.
- `interpretar_linha(bruto)` → `dict` ou `None`; linha que não é JSON **nunca** levanta
  exceção.
- `frase_de_status(evento, frase_atual)` → uma das 7 frases do design, ou `frase_atual`
  quando o evento não muda de fase.
- `avancar(estado, evento)` → próximo estado no ciclo
  `parada · rodando · ok · falha · parada_pelo_dono`. **Lê `is_error` e `terminal_reason`
  do evento `result`, nunca `subtype`** (medido: `subtype:'success'` com `is_error:True`).
- `classificar_falha(evento_result)` → `(manchete, corpo)` para os quatro casos do design:
  `budget_exhausted`, PR já existente, testes ainda vermelhos, limite de turnos.
- `custo_do_evento(evento, acumulado)` → float. `total_cost_usd` do `result`
  **sobrescreve** o acumulado; eventos intermediários somam a partir de `usage`, se vier.
- `em_reais(usd)` → `"R$ 1,84"`, vírgula decimal, duas casas.
- `decidir_pedido(execucao_atual, projeto_pedido)` → `"iniciar"` | `"mesma"` |
  `"recusada"` — é a decisão da trava global, e é o critério 10 em forma testável.
- `url_do_pr(saida_do_gh)` → última linha começando por `https://`, ou `None`.
  **`gh pr create` não aceita `--json`** nesta versão; a URL vem no stdout.

Criar `test_execucao.py` cobrindo cada função acima, e acrescentar ao `ci.yml`, logo
depois do passo "Proxy do grafo", um passo `- name: Execução` com
`run: python test_execucao.py`; e incluir `execucao.py` na lista do passo "Compila".

**Verificação:**

```
python test_execucao.py && python test_servir.py && python test_regras.py && python test_coletar.py
python -m py_compile execucao.py
```

Espera-se: as quatro suítes com `OK`, `py_compile` silencioso. A saída de
`test_execucao.py` tem de nomear classes como `MontagemDoComando`,
`MaquinaDeEstados`, `AcumuladorDeCusto`, `DecisaoDaTrava` — se algum desses nomes não
aparecer na saída, o critério 12 não está coberto.

**Depende de:** nenhuma.
**Revisores da fase 6:** `python`, `security` (é aqui que se decide qual comando roda na
máquina e como o prompt é montado).

---

### Etapa 2 — a cópia isolada e o fim de linha no GitHub

**Objetivo:** o painel sabe criar uma cópia em `git worktree` fora de
`source\repos`, ler o diff dela, abrir o pedido de alteração e limpar depois — sem que a
pasta original do projeto seja tocada.

**Arquivos:** `execucao.py`, `test_execucao.py`.

**Contexto:**

- **Onde:** `~/.cache/hub-worktrees/<projeto>/<id-de-8-caracteres>`, obrigatoriamente
  fora de `RAIZ = C:\Users\Desktop\source\repos` (`coletar.py:46`), porque
  `pastas_de_projeto()` (`coletar.py:66-72`) trata **toda** subpasta de `RAIZ` como
  projeto medido e o painel se auto-poluiria (spec, contradição 4). O espírito é o de
  `CACHE_GRAFO` (`coletar.py:78`).
- **Helper de subprocesso já existe:** `_rodar(args, cwd, shell, limite)` em
  `servir.py:148-153` — passa `creationflags=SEM_JANELA`, corta a saída em 1200
  caracteres e devolve `(ok, saida)`. Replique o padrão em `execucao.py` (inclusive
  `SEM_JANELA`, cuja razão está em `servir.py:55-69`: sob `pythonw.exe` cada filho abre um
  console que pisca na cara do dono).
- **Sucesso remove a cópia; falha preserva** (spec, peça 2). Worktree suja exige
  `git worktree remove --force`.
- `gh` já é dependência de fato do projeto (`coletar_github.py:77`).
- Nunca `git push` para `main`, nunca `gh pr merge`: critério 5 e item "intocável" da
  spec.

**Fazer:** acrescentar a `execucao.py`, abaixo da parte pura:

- puras (com teste): `id_curto()` determinístico sob semente injetada,
  `caminho_da_copia(base, projeto, id)` — **`base` é parâmetro**, para o teste rodar em
  `ubuntu-latest` com `tmp_path`; `nome_do_ramo(regra, projeto, id)` produzindo algo como
  `hub/ci-vermelha-a1b2c3d4`, sanitizando o que não é válido em nome de ramo;
  `mensagem_de_commit(pendencia)`; `titulo_e_corpo_do_pr(pendencia)`.
- I/O: `criar_copia(caminho_do_projeto, destino, ramo)` via
  `git -C <projeto> worktree add -b <ramo> <destino> HEAD`;
  `remover_copia(caminho_do_projeto, destino)` via `git worktree remove --force` seguido
  de `git worktree prune`; `diff_da_copia(destino)` via `git -C <destino> diff` (texto
  puro, é o modo "diff" da tela); `houve_mudanca(destino)` via `git status --porcelain`;
  `publicar(destino, ramo, titulo, corpo)` encadeando `git add -A`, `git commit`,
  `git push -u origin <ramo>` e `gh pr create --title --body --head`, extraindo a URL com
  `url_do_pr()`.

**Verificação:** com a árvore do `painel-projetos` limpa, criar uma cópia e removê-la; em
seguida `git status --short` **vazio** (é o critério 3 em uma linha) e `git worktree list`
mostrando só a árvore principal ao final; suíte `OK`. Se um ramo de teste sobrar, apague-o
com `git branch -D`.

**Depende de:** Etapa 1 (mesmo arquivo).
**Revisores da fase 6:** `python`, `security` (montagem de comando `git`/`gh` com nome de
projeto e de ramo).

---

### Etapa 3 — o processo filho, o fluxo ao vivo, a trava e o "Parar"

**Objetivo:** o servidor sabe iniciar uma sessão do Claude na cópia isolada, acumular log
e custo enquanto ela roda, recusar uma segunda execução, e matá-la em até 5 segundos.

**Arquivos:** `execucao.py`, `test_execucao.py`.

**Contexto:**

- **Molde existente do processo destacado:** `acao_grafo_ligar()`
  (`servir.py:481-498`) — `subprocess.Popen` com `creationflags = 0x00000008 | 0x00000200`
  (DETACHED | NEW_PROCESS_GROUP) no Windows e `start_new_session=True` fora dele, handle
  global (`_grafo_proc`, `servir.py:306`) e trava (`_grafo_trava`, `servir.py:308`). Aqui
  é o mesmo desenho, trocando `stdout=DEVNULL` por `PIPE` e lendo linha a linha numa
  thread. Serialização por trava: molde em `_travas` (`servir.py:112`, uso em
  `servir.py:121`).
- **Ciclo de vida:** `parada · rodando · ok · falha · parada_pelo_dono`, um recurso único
  na máquina inteira, estado **em memória no servidor** (sem tabela no banco — ver
  ambiguidade A). Recarregar a página não perde nada porque o estado não está no
  navegador.
- **Parar:** Windows `taskkill /PID <pid> /T /F`; fora do Windows, matar o grupo. Depois
  `proc.wait(timeout=5)`. Se não morrer, o estado vira "não confirmado" e a tela diz
  `Não consegui confirmar que parou` — nunca fingir sucesso (design, `textos`).
- **Erro nunca derruba o servidor:** molde em `servir.py:236-237`.
- **Medição obrigatória antes de escrever o acumulador de custo:** rode uma sessão
  trivial de verdade e olhe se os eventos `assistant` trazem `usage`. Se `usage` só vier
  no `result`, o custo ao vivo fica parado e **isso tem de ser dito na tela**
  ("estimativa, ainda rodando" só atualiza ao final) — não invente tabela de preços.

**Fazer:** acrescentar a `execucao.py`:

- estado global `_execucao` (dict) e `_trava` (`threading.Lock`), no molde de
  `servir.py:306-308`;
- `iniciar(pendencia, caminho_do_projeto)` — sob a trava, consulta
  `decidir_pedido()` (etapa 1); cria a cópia (etapa 2); monta prompt e comando
  (etapa 1); abre o `Popen` com `cwd` no worktree, `stdout=PIPE`, `stderr=STDOUT`,
  `text=True`, `encoding="utf-8"`, `errors="replace"`, `bufsize=1`, e
  `creationflags` no molde do grafo somado a `SEM_JANELA`; dispara a thread leitora;
- a thread leitora: para cada linha, `interpretar_linha` → `frase_de_status` →
  `avancar` → `custo_do_evento`, anexando ao log com carimbo de hora no formato do design
  (`14:02:03  texto`); ao ver o `result`, decide `ok`/`falha`, e no caso `ok` chama
  `publicar()` e `diff_da_copia()` e remove a cópia; no caso `falha`, **preserva** a cópia;
- `parar()` — mata, espera 5 s, e devolve se conseguiu confirmar;
- `estado(desde=0)` → dict com `estado`, `projeto`, `pendencia_id`, `frase`, `custo_usd`,
  `custo_brl`, `linhas` a partir de `desde`, `total_de_linhas`, `pr_url`, `resumo`,
  `diff`, `manchete`, `corpo`.

Testes novos: só o que é puro — a montagem do comando de morte
(`comando_para_matar(pid)`), o corte incremental do log (`linhas_desde(log, n)`, inclusive
`n` maior que o tamanho e `n` negativo), a transição de estado ao receber cada um dos
`terminal_reason` medidos, e o acumulador de custo com um `result` real gravado como
literal no teste.

**Verificação:** suíte `OK`; depois, uma execução real de teste: em 8 segundos o estado é
`rodando` com pelo menos uma linha de log e uma frase em português; `parar()` devolve
confirmação; e na mesma janela `Get-Process claude -ErrorAction SilentlyContinue` não
lista nada — **é o critério 6, verificado como o briefing pede**. E `git status --short`
no `painel-projetos` continua vazio.

**Depende de:** Etapa 2 (mesmo arquivo).
**Revisores da fase 6:** `python`, `security` (processo filho a partir de servidor web).

---

### Etapa 4 — a superfície HTTP: `resolver`, `parar` e `/api/execucao`

**Objetivo:** o navegador consegue disparar, acompanhar e interromper uma execução,
passando pela mesma cadeia de segurança que o `/api/acao` já exige — e a lista branca do
servidor volta a estar em dia com o teste da paleta.

**Arquivos:** `servir.py`, `test_servir.py`, `README.md`.

**Contexto:**

- `executar_acao` (`servir.py:201-240`) trata `recoletar`, `silenciar` e `grafo_ligar`
  **antes** do `if comando not in ACOES`. `resolver` e `parar` entram nesse mesmo trecho,
  porque precisam do corpo inteiro (o `id` da pendência), e não da assinatura `f(p)` do
  dict `ACOES`.
- **O cliente manda só o `id`** (spec, peça 3; molde já existente em `silenciar`,
  `servir.py:211-221`). O servidor **recalcula** as pendências — mesmo caminho de
  `_estado()` (`servir.py:546-563`): `banco.montar_estado` + `regras.avaliar` — e procura
  a de `id` igual. Não achou, recusa. É assim que nenhum texto do navegador entra no
  prompt.
- **Ordem das checagens do POST, já pronta:** Host `servir.py:518-519`, Origin
  `servir.py:593`, `compare_digest` `servir.py:595`, corpo ≤16 KiB `servir.py:600`. A
  rota nova entra **dentro** dela; nada é afrouxado (critério 11).
- **Armadilha do GET:** navegador **não** manda `Origin` em requisição GET de mesma
  origem. Se o `/api/execucao` exigir `Origin` como o POST faz, ele responde 403 sempre.
  Use `_host_confiavel()` + `secrets.compare_digest` no `X-Token` +
  `origem_aceita(self.headers.get("Sec-Fetch-Site"))` — a função já existe em
  `servir.py:612` e é o padrão que o proxy do grafo usa exatamente por esse motivo.
- `test_servir.py:274`: `FORA_DO_DICT = {"recoletar", "silenciar", "grafo_ligar"}` precisa
  ganhar `"resolver"` e `"parar"`, **nesta etapa**, senão a etapa 6 quebra a CI.

**Fazer:**

1. `import execucao` no topo de `servir.py`.
2. Em `executar_acao`, antes do `if comando not in ACOES`: bloco `resolver` (acha a
   pendência pelo id recalculado, verifica `execucao.pode_resolver`, resolve o caminho do
   projeto pelo banco via `_projetos_por_nome()` em `servir.py:144-145`, chama
   `execucao.iniciar`) e bloco `parar` (chama `execucao.parar`).
3. Em `do_GET` (`servir.py:522-544`), antes do `caminho_do_grafo`, a rota
   `/api/execucao` com `desde` lido da query (inteiro, com piso 0), devolvendo
   `execucao.estado(desde)`.
4. Em `_estado()` (`servir.py:546-563`), acrescentar duas chaves: `"execucao"` (resumo
   leve: estado, projeto, id da pendência) e `"resolver_bloqueado"` (a lista de
   `execucao.PROJETOS_BLOQUEADOS`), para o cliente não duplicar a regra.
5. `test_servir.py`: atualizar `FORA_DO_DICT`; acrescentar uma classe nova com docstring
   datada garantindo que `resolver` e `parar` são conhecidos por `executar_acao` e que
   `/api/execucao` não é servido pelo handler estático.
6. `README.md`: seção nova descrevendo o cano (o botão, a cópia isolada, a trava única, o
   teto aproximado de US$ 3 com a medição que o justifica, o "Parar" de 5 s) e um
   parágrafo na seção **Segurança** existente sobre a rota nova e sobre o que **não** foi
   mitigado (hooks do projeto-alvo rodam, porque `--bare` não é utilizável com OAuth).
   Ajustar a seção "O que ainda não existe".

**Verificação:** as quatro suítes `OK`; com um servidor de teste no ar, **403** na consulta
sem `X-Token` e **403** no Host forjado; e, no console do navegador, a consulta a
`/api/execucao?desde=0` com o token devolve um objeto com `estado:"parada"`.

**Depende de:** Etapa 3.
**Revisores da fase 6:** `security` (obrigatório — superfície HTTP e montagem de comando),
`python`.

---

### Etapa 5 — o diálogo de execução: estrutura, CSS e os seis estados, sem rede

**Objetivo:** o painel ganha o `<dialog id="execucao">` com os seis estados desenhados,
alternáveis à mão, e a variante `.aviso.neutro` — tudo visível e revisável antes de haver
um byte de JavaScript de rede.

**Arquivos:** `index.html` (só o `<style>` e o markup; **não tocar no `<script>`** além do
mínimo para trocar o estado à mão).

**Contexto:**

- **Molde a copiar:** `#paleta`, markup em `index.html:259-273` e CSS em
  `index.html:137-169` — `<dialog closedby="any">`, `::backdrop`, `showModal()`,
  `@media (prefers-reduced-motion)`. O fallback de "clique fora fecha" para Safari está em
  `index.html:806`.
- **Zero token novo.** Todos os tokens usados já existem em `index.html:26-40`
  (`--painel --bg --borda --texto --fraco --fraquinho --acento --ok --alerta --erro
  --grade --sombra --mono --sans`).
- **As duas correções do juiz são obrigatórias** (design, seção "Correções do juiz"):
  (1) o link do PR ganha `font-weight:600` e `text-decoration:underline` permanente, mais
  o `↗`, porque `--acento` a 4,44:1 não passa 4,5:1; (2) nasce `.aviso.neutro`, que troca
  **só** a cor da borda de `--erro` para `--acento`, mantendo o resto de `.aviso`
  (`index.html:190`) intacto.
- **Regra de uso de cor, do design:** `--acento`, `--ok` e `--alerta` **não** viram cor de
  texto neste painel; viram indicador não textual (`●`, `✓`, `⏸`, borda esquerda). Só
  `--erro` pode ser cor de palavra ("Falhou"). A palavra que importa está sempre em
  `--texto`.
- Largura `min(640px,92vw)`; log em `<pre>` com `overflow-y:auto; max-height:38vh` e
  `overflow-x:auto` próprio; comportamento em 360px descrito estado a estado no design.
- Acessibilidade, literal do design: linha de status com `aria-live="polite"`
  `role="status"` (molde em `#recado`, `index.html:274`); log com `role="log"`
  `aria-label="Saída bruta da execução"` e **sem** `aria-live`; custo sem `aria-live`;
  foco vai para o `<h2>` com `tabindex="-1"` ao abrir; ao fechar, volta ao botão que abriu.
- **O log não some.** Nada de `setTimeout` no molde de `recado._t`
  (`index.html:305-306`).

**Fazer:** acrescentar o `<dialog id="execucao">` com moldura fixa (cabeçalho com
`Resolvendo: {{projeto}}` e `×` com `aria-label="Fechar o painel de execução"`; rodapé com
o custo e a nota fixa) e miolo trocado por um atributo `data-estado` com os valores
`rodando`, `ok`, `falha`, `parada_pelo_dono`, `recusada`. Todos os textos literais saem da
seção `textos` do `design.md` — inclusive o aviso `ℹ` do `painel-projetos` na variante
`.aviso.neutro`, as abas `Resumo`/`Diff` no molde de `nav.abas` (`index.html:59-65`), o
`Iniciando…` de log vazio e a nota de custo. Acrescentar à nota de custo que **o teto é
aproximado** (medição do estouro de 4,5×). Nenhum `fetch`, nenhum `comando:` — se aparecer
a string `comando:"..."` nesta etapa, ela quebra `PaletaNaoInventaComando`.

**Fixe e documente**, num comentário no próprio `index.html`, os `id`s dos elementos que a
etapa 6 vai preencher. Sem isso, a etapa 6 vira uma edição de CSS disfarçada.

**Verificação:** com o painel no ar, abrir o diálogo pelo console e desfilar os cinco
estados via `data-estado`: sem quebra de layout, `Esc` fechando, backdrop correto. Repetir
com `data-theme="dark"` e com a janela em 360px — a página **não** rola na horizontal em
nenhum estado. Confirmar que `python test_servir.py` continua `OK` (a regex do teste não
deve achar comando novo).

**Depende de:** nenhuma. **Roda em paralelo com as etapas 1 a 4.**
**Revisores da fase 6:** `design`.

---

### Etapa 6 — o fio: botão "Resolver", consulta de 1 s, abas e "Parar"

**Objetivo:** clicar em "Resolver" numa pendência abre o diálogo, mostra o progresso ao
vivo, deixa parar, e termina com o link do pedido de alteração — os 12 critérios passam a
ser exercitáveis na tela.

**Arquivos:** `index.html` (só o `<script>`), `README.md`.

**Contexto:**

- **O botão novo entra em `itensEm()`** (`index.html:390-423`), entre o `button.agir` da
  ação atual (linha 409-413) e o `button.calar` (414-419) — **ao lado**, nunca no lugar.
  Só quando `p.projeto` não é vazio e `p.projeto` não está em
  `d.resolver_bloqueado` (chave nova vinda do `/api/dados`, etapa 4). Ver ambiguidade B.
- **`agir()` não serve e não deve ser reusada:** ela é o executor de ação única e o
  caminho onde vive o `ocupado` global (`index.html:326, 329, 340`). O "Resolver" é um
  segundo executor, e **não usa `ocupado`** — a trava foi para o servidor (spec,
  contradição 2). Os outros botões do painel continuam clicáveis durante a execução.
- **`mandar()`** (`index.html:310-316`) já manda `X-Token`; a consulta GET precisa mandar
  o mesmo cabeçalho à mão (`fetch("/api/execucao?desde="+n, {headers:{"X-Token":TOKEN}})`).
- **Paleta:** acrescentar o comando em `comandosDe()` (`index.html:668-716`), no bloco 1
  das pendências, chamando a mesma função do botão — a paleta nunca tem ação própria
  (comentário em `index.html:631-634`).
- **Consulta de 1 em 1 segundo**, com `desde` = total de linhas já recebidas; parar o
  laço quando o estado sai de `rodando`. Fechar o diálogo (Esc) **não** para a execução; o
  botão do projeto vira "Ver execução" enquanto ela roda (o `/api/dados` já traz a chave
  `execucao`).
- **As abas Resumo/Diff não fazem requisição nenhuma** — os dois textos já vieram no
  estado final.
- Guardar a referência do botão que abriu, para devolver o foco ao fechar (design, seção
  "Foco e fechamento pelo teclado").

**Fazer:** o executor `resolver(pend, botao)`, o laço de consulta, a troca de
`data-estado` e o preenchimento dos campos do diálogo da etapa 5, o botão "Parar" (com
`Parando…` enquanto processa), as abas, o link do PR, e o aviso `.aviso.neutro` quando
`pend.projeto === "painel-projetos"`. Atualizar o `README.md` na seção da paleta e na
seção nova criada na etapa 4, descrevendo o comportamento de tela.

**Verificação:** `python test_servir.py` → `OK`. É este teste que prova que o
`comando:"resolver"` e o `comando:"parar"` recém-colocados no HTML existem na lista branca
do servidor (`PaletaNaoInventaComando`, `test_servir.py:263-290`). Depois, com o painel no
ar: clicar "Resolver" numa pendência, ver a linha de status trocar de frase e o log crescer
sem sumir; abrir o Ctrl+K, digitar "resolver" e achar o mesmo comando; fechar com `Esc` e
reabrir, confirmando que o log continua lá.

**Depende de:** Etapa 4 (sem ela a CI quebra) e Etapa 5 (mesmo arquivo).
**Revisores da fase 6:** `design`, `security` (o cliente que carrega o token e dispara a
execução).

---

### Etapa 7 — prova de aceitação: os 12 critérios, um a um

**Objetivo:** o dono tem prova, não promessa, de que a entrega faz o que o briefing pediu
— e as falhas encontradas voltam para a etapa dona do arquivo, não viram remendo.

**Arquivos:** nenhum. Esta etapa não edita nada; ela mede e relata.

**Contexto:** os 12 critérios estão em `docs/esteira/claude-no-painel/briefing.md`,
`criterio_de_aceitacao`. Faça com a árvore **limpa e tudo commitado** — o caso de teste
natural é resolver o próprio `painel-projetos`, e ele é o repositório em que as outras
etapas mexeram.

**Fazer / Verificação — um comando ou uma olhada por critério:**

1. Botão "Resolver" ao lado da ação atual → olhar a caixa; conferir que a pendência
   `cota_actions` (projeto vazio) **não** tem o botão.
2. Progresso ao vivo → a linha de status troca de frase antes do fim.
3. Isolamento → durante e depois: `git status --short` na pasta original **vazio**;
   a cópia aparece em `~/.cache/hub-worktrees` enquanto roda.
4. PR aberto → o link aparece e abre um pull request de verdade no GitHub.
5. `main` intacta → `git log --oneline -1 main` é o mesmo commit de antes.
6. "Parar" em 5 s → clicar e rodar `Get-Process claude -ErrorAction SilentlyContinue`:
   sem saída.
7. Custo em reais na tela, ao vivo e ao final, com a palavra "estimativa" e a nota de
   que o teto é aproximado.
8. Falha com motivo real → force uma (ex.: `--max-turns 1`) e confira que a manchete é
   uma das quatro do design e que o log cru está visível.
9. Dois modos → alternar Resumo/Diff sem requisição nova (aba Network parada).
10. Duas execuções → clicar "Resolver" em outro projeto durante a primeira: a tela
    `recusada_por_ja_haver_outra_execucao`, com "Ver essa execução" funcionando.
11. `curl` sem `X-Token` em `/api/acao` e em `/api/execucao` → **403** nos dois.
12. `python test_regras.py && python test_coletar.py && python test_servir.py &&
    python test_execucao.py` → quatro `OK`.

**Depende de:** Etapa 6.
**Revisores da fase 6:** nenhum — é o portão de entrada da fase 6, não código.

---

## O que roda em paralelo

- **Paralelo de verdade:** a **Etapa 5** (`index.html`, estrutura e CSS) com **qualquer
  uma** das etapas 1, 2, 3 ou 4. Não há interseção de arquivos: a 5 não toca `.py`, e as
  1–4 não tocam `index.html`. Este é o único paralelismo real do plano, e é intencional —
  foi por isso que o CSS e o markup foram separados do JavaScript.
- **Sequencial obrigatório, por conflito de arquivo:**
  - **1 → 2 → 3**, as três em `execucao.py` e `test_execucao.py`. Duas delas ao mesmo
    tempo geram conflito de arquivo inteiro.
  - **5 → 6**, as duas em `index.html`. O arquivo tem 962 linhas e as duas etapas mexem em
    regiões vizinhas.
  - **4 → 6**, por `README.md`: a 4 escreve a seção do cano e da segurança, a 6 escreve a
    da tela. Como a 6 já depende da 4 por outro motivo, o README nunca é alvo de duas
    etapas simultâneas. As etapas 1, 2, 3 e 5 **não tocam** o README de propósito, para
    manter essa propriedade.
- **Sequencial obrigatório, por dependência lógica:**
  - **3 → 4**: `servir.py` importa `execucao` e chama `iniciar`/`parar`/`estado`.
  - **4 → 6**: `PaletaNaoInventaComando` (`test_servir.py:263-290`) quebra a CI no instante
    em que `comando:"resolver"` aparece no `index.html` sem `resolver` na lista branca do
    servidor. Este é o ponto exato em que o repositório pode ficar quebrado no meio, e é
    por isso que a atualização de `FORA_DO_DICT` mora na etapa 4, não na 6.
  - **6 → 7**: não há o que aceitar antes de o fio existir.
- **`.github/workflows/ci.yml` é tocado por uma etapa só** (a 1), justamente para não
  virar um terceiro ponto de colisão.

## Riscos do plano

*(riscos de execução; os riscos do produto estão no briefing)*

1. **A etapa 3 é a maior e a mais provável de estourar.** Processo filho, thread leitora,
   trava, custo e "Parar" num arquivo só. Se ela crescer demais, o corte natural é tirar o
   "Parar" para uma etapa 3b — mesma sequência, mesmo arquivo, um commit a mais. **Não
   corte o "Parar" do escopo**: é item intocável da spec.
2. **O custo ao vivo pode não ter fonte.** A etapa 3 mede antes de escrever. Se `usage` só
   vier no `result`, o critério 7 fica cumprido pela metade e isso precisa ser **dito ao
   dono**, não escondido atrás de um número que não se move.
3. **Hooks do projeto-alvo podem abortar a sessão filha.** Descoberto só na etapa 7,
   quando já se investiu tudo. Mitigação barata: na **etapa 3**, a primeira execução real
   já deve ser num projeto com `.claude/settings.json` versionado, para o sintoma aparecer
   cedo.
4. **`gh pr create` sem `--json` pode mudar de formato de saída.** `url_do_pr()` é pura e
   testada, mas o teste usa uma saída literal. Se o `gh` for atualizado, o sintoma é "PR
   aberto e link ausente" — visível na etapa 7, critério 4.
5. **A etapa 5 pode divergir do que a etapa 6 precisa.** Ela desenha os campos, a 6 os
   preenche. Mitigação já embutida: a etapa 5 fixa e documenta os `id`s num comentário.
6. **Resolver o próprio painel durante o desenvolvimento** cria uma cópia isolada do repo
   que está sendo editado. Faça só na etapa 7, com tudo commitado.
7. **O teto de US$ 3 é aproximado e já foi visto estourar 4,5×.** Um erro de laço durante
   os testes das etapas 3 e 7 pode custar mais do que a conta sugere. Tenha o
   `Get-Process claude | Stop-Process` à mão antes de rodar a primeira sessão real.

## O que não foi possível confirmar

- **Se os eventos `assistant` trazem `usage`.** Só há medição do evento `result`. É a
  diferença entre o critério 7 cumprido e cumprido pela metade; a etapa 3 mede antes de
  decidir.
- **Se algum hook do `~/.claude` ou do `.claude/settings.json` dos projetos-alvo barra
  `git push` ou `git commit` da sessão filha.** O `block-no-verify.py` existe e barra pelo
  menos uma forma de `git push`. A sessão filha não foi testada com hooks ativos.
- **Se `--settings` conseguiria neutralizar os hooks sem `--bare`.** Não testado, e por
  isso não incluído no plano. Se o executor quiser tentar, é medição, não suposição.
- **Se o prompt cabe como argumento de linha de comando** em todos os casos. Estimativa:
  sim (limite ~32 KB no Windows), mas gabaritos futuros com log de CI colado dentro podem
  estourar. Se acontecer, a alternativa é mandar o prompt por stdin.
- **A cotação do dólar a usar em `USD_BRL`.** O dono decidiu "constante no código, num
  lugar só"; o valor de hoje precisa ser escrito com a data no comentário, na etapa 1.
- **Se `git worktree add` funciona nos 17 projetos.** Submódulos com worktree são
  experimentais (fonte da spec), e não se sabe quais projetos têm submódulo.

*Uma observação fora do escopo, dita em uma linha:* o design registra como dívida que
`--acento` a 4,44:1 afeta **todo** link do painel, não só o do PR — candidato à primeira
faxina visual, em outra entrega.
