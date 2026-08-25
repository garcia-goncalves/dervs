# Spec — o Claude dentro do painel (entrega 1: o botão "Resolver")

> Fase 2 da esteira, escrita pelo Sintetizador em 24/08/2026, a partir de quatro
> lentes cegas entre si: Analista, Arquiteto, Pesquisador e Diretor.

## problema

Hoje o HUB **mostra** 14 tipos de pendência nos 17 projetos e para por aí. Quando
uma CI fica vermelha, a única ação disponível é "abrir o que falhou"
(`README.md`, regra 1) — o que joga o dono num log do GitHub que ele não lê, ou
obriga o sócio a largar o que estava fazendo e abrir o VS Code.

A dor é assimétrica e atinge duas pessoas de formas opostas:

- **o dono** vê um alerta vermelho que ele não tem como resolver sozinho, e cuja
  gravidade ele não consegue julgar. O painel lhe entrega ansiedade sem entregar
  ação;
- **o sócio** vira o gargalo de tudo o que é técnico, inclusive do que é
  repetitivo e chato — corrigir teste quebrado, atualizar dependência, arrumar
  fim de linha.

O painel diagnostica bem e não trata. Falta o verbo.

## solucao

Um botão **"Resolver"** ao lado da pendência, que dispara uma sessão do Claude
Code de verdade — a mesma que roda no terminal — numa **cópia isolada** do
repositório, mostra o que ela está fazendo **enquanto acontece**, e termina
abrindo um **pedido de alteração no GitHub** que o dono aprova com um clique.

Nada é salvo no ramo principal por conta própria, em nenhuma hipótese.

**Por que esta forma, e não outra.** As alternativas foram consideradas e
descartadas com motivo:

- *rodar o código no navegador, como Lovable e bolt.diy* — não serve. Aqueles
  usam um sandbox de Node dentro da aba, e os projetos desta máquina são .NET,
  PHP, Docker e Postgres no disco. Aqui o caminho é o inverso: o painel vira a
  cara do Claude Code, que já enxerga disco, Git e Docker reais;
- *usar o Agent SDK (pacote Python)* — descartado. A CI deste projeto tem um
  passo chamado *"Nada de dependencia externa"* que **falha o build** se aparecer
  `requirements.txt` ou `pyproject.toml`. A rota é o CLI em modo `-p`, chamado
  por `subprocess`, exatamente como o projeto já chama `git`, `gh` e `docker`;
- *editar direto na pasta do projeto* — descartado por integridade. É onde o dono
  e o sócio trabalham; uma sessão autônoma ali destrói trabalho não commitado. A
  regra 4 do próprio painel ("commit só no disco") existe porque isso acontece.

**A forma técnica, em sete peças, na ordem que destrava o resto:**

1. **Um recurso de execução no servidor**, com ciclo de vida fechado:
   `parada · rodando · ok · falha · parada_pelo_dono`. **Uma execução por vez na
   máquina inteira**, com trava global. O estado mora no servidor, não no
   navegador — recarregar a página não perde nada.
2. **Cópia isolada em `git worktree`**, criada em
   `~/.cache/hub-worktrees/<projeto>/<id-curto>`. **Fora de
   `C:\Users\Desktop\source\repos`**, obrigatoriamente — ver contradição 4.
   Removida com `git worktree remove` no sucesso; **preservada na falha**, para
   diagnóstico.
3. **O processo filho**: `claude -p --output-format stream-json --verbose
   --max-budget-usd 3 --strict-mcp-config --mcp-config '{"mcpServers":{}}'
   --allowedTools <lista branca> --max-turns <limite>`, com
   `creationflags=CREATE_NEW_PROCESS_GROUP`, `cwd` no worktree. **Sem
   `--bare`** — ele quebra a autenticação nesta máquina, ver contradição 9. O prompt é
   montado **inteiramente no servidor**, a partir de gabarito fechado — nenhum
   texto vindo do navegador entra nele. O cliente manda só o `id` da pendência,
   como já manda só o nome do projeto hoje (`servir.py:29-30`).
4. **Transmissão ao vivo por consulta de 1 em 1 segundo**:
   `GET /api/execucao?desde=<N>` devolve as linhas novas do log a partir do
   índice N, passando pelas mesmas checagens de Host, Origin e `X-Token` que o
   `/api/acao` já faz. Sem SSE nesta entrega — ver contradição 1.
5. **Botão "Parar"**, com prazo duro de 5 segundos: `taskkill /PID <pid> /T /F`,
   seguido de `proc.wait(timeout=5)`. Se não morrer, o painel **diz que não
   conseguiu**, em vez de fingir sucesso.
6. **Custo ao vivo em reais**: o campo `total_cost_usd` vem no evento `result`
   do próprio fluxo, e os eventos de mensagem trazem `usage` incremental.
   Multiplicado por uma cotação constante no código. O painel escreve na tela
   que é **estimativa**, não fatura.
7. **Fim de linha**: `gh pr create --json url`, e o link clicável na tela.

**A tela**, decidida pela lente de usuário:

- uma **linha de status em destaque** que muda em português ("lendo o
  repositório" → "rodando os testes" → "abrindo o pedido de alteração"), porque
  é isso que os dois usuários realmente precisam ver;
- abaixo, o **log cru**, num painel que **não some sozinho** (o aviso de erro de
  hoje desaparece em 9 segundos — `index.html:306` — o que tornaria o critério 8
  formalmente cumprido e inutilizável na prática);
- ao final, dois modos alternáveis por um clique: **"resumo"** (uma frase em
  português por arquivo tocado, produzida pelo próprio gabarito de prompt, sem
  chamada extra ao modelo) e **"diff"** (`git diff` do worktree, texto puro).

## o_que_ja_existe

Levantado pelo Arquiteto no código, com caminho e linha. **Quatro das sete peças
já têm precedente no repositório** — é a informação que mais barateia esta
entrega.

| Peça | Onde já existe | O que falta |
|---|---|---|
| Processo filho longo, destacado, em grupo próprio | `servir.py:481-498` (`acao_grafo_ligar`), com `CREATE_NEW_PROCESS_GROUP` e handle vivo em `servir.py:306` sob trava em `servir.py:308` | trocar `stdout=DEVNULL` por `PIPE` e ler linha a linha |
| Serialização de execução concorrente | `_travas` em `servir.py:112`, usada em `servir.py:121`; padrão "já está subindo" em `servir.py:481-489` | uma trava global de execução, no mesmo molde |
| Leitura de git | `coleta_git()` em `coletar.py:296-387`, helper `git()` em `coletar.py:173-174` | nada; funciona em worktree, onde `.git` é arquivo e não pasta |
| Detecção de CI vermelha | `coletar_github.py:122-126` (via `gh api graphql`) e `regras.py:62-69`, que gera a pendência `ci_vermelha:<projeto>` (id em `regras.py:42`) | o dado já chega à tela; é esta pendência que ganha o botão |
| `gh` CLI como dependência de fato | `coletar_github.py:77` | nada — `gh pr create` sai de graça |
| Tabela numérica para o custo | `banco.anotar_historico()` em `banco.py:141-150`, tabela `historico` em `banco.py:40-45` | nada |
| Lista branca de comandos | `ACOES` em `servir.py:193-198`, mais os três de fora do dict em `servir.py:204-223` | acrescentar `resolver` |
| Cadeia de segurança do POST | Host `servir.py:518-519`; Origin `servir.py:593`; `X-Token` com `compare_digest` `servir.py:595`; corpo ≤16 KiB `servir.py:600` | nada — a rota nova entra **dentro** desta cadeia |
| Servidor multi-thread | `ThreadingHTTPServer` em `servir.py:692` | nada; aguenta conexão longa sem travar as outras (medido) |

**O que não existe e é construção nova:** qualquer forma de transmissão de
progresso (zero ocorrências de `EventSource`, `WebSocket` ou `text/event-stream`
no repositório), qualquer uso de `git worktree` (zero ocorrências), qualquer
noção de execução com estado, e qualquer cálculo de custo.

**Tabela nova no banco.** `banco.conectar()` roda `executescript(ESQUEMA)` a toda
conexão com `CREATE TABLE IF NOT EXISTS` (`banco.py:67`), então acrescentar uma
tabela é gratuito e retrocompatível. **Mas não há mecanismo de migração nenhum**
— nem coluna de versão, nem `ALTER`. Tabela nova é seguro; alterar coluna
existente não tem caminho. A tabela `execucao` precisa nascer certa.

**A convenção da casa, a ser obedecida:** identificadores e comentários em
português sem acento (arquivos abrem com `# -*- coding: utf-8 -*-`), strings
voltadas ao dono **com** acento; zero dependência externa (cobrado pela CI);
teste em `unittest` puro rodado como script, com docstring contando o caso real
que originou cada classe; funções puras separadas do I/O, porque a CI roda em
`ubuntu-latest` e não pode tocar em `creationflags` nem em caminho do Windows;
erro nunca derruba o servidor (`servir.py:236-237`); ausência de dado é `None` e
significa "não sei", nunca zero.

## fontes_externas

Todas consultadas em **24/08/2026** pelo Pesquisador.

- https://code.claude.com/docs/en/headless — modo `-p`; ao receber SIGTERM o
  Claude Code já mata a árvore de processos das ferramentas Bash em execução.
- https://code.claude.com/docs/en/cli-reference — flags. **`--max-budget-usd`
  existe e é teto de gasto real** (exige Claude Code ≥ v2.1.217); ao atingir, a
  sessão para e novos subagentes falham com "Budget limit reached". `--bare`
  pula a autodescoberta de hooks, skills, MCP e CLAUDE.md do usuário — e vai se
  tornar o padrão de `-p` numa versão futura.
- https://code.claude.com/docs/en/agent-sdk/streaming-output — formato de
  `--output-format stream-json`: um objeto JSON por linha; primeiro evento
  `{"type":"system","subtype":"init"}`; deltas em
  `{"type":"stream_event",...}`; **última linha é o evento `result`**.
- https://code.claude.com/docs/en/agent-sdk/cost-tracking — `total_cost_usd` no
  evento `result`. **É estimativa calculada no cliente**, por tabela de preços
  embutida no binário; pode divergir da fatura. Serve para o teto e para a tela,
  não para cobrança.
- https://docs.python.org/3/library/subprocess.html — `CREATE_NEW_PROCESS_GROUP`;
  `CTRL_BREAK_EVENT` só funciona em processo criado com essa flag. No Windows,
  `terminate()` **não** mata os netos — daí `taskkill /T /F`.
- https://git-scm.com/docs/git-worktree — worktree abandonada deixa metadados que
  só `git worktree prune` remove; worktree suja exige `remove --force`;
  submódulos são experimentais com worktree; **arquivos ignorados pelo git não
  são copiados** para a cópia nova.
- Pesquisa de mercado (sem página oficial única): OpenHands mostra painel de ação
  ao vivo e estado explícito de espera por aprovação; bolt.diy mostra cada
  mudança como diff revisável. O que têm em comum — progresso visível, diff antes
  de aceitar, interrupção a qualquer momento — é exatamente o desenho acima.

*O Pesquisador registra que nenhuma página consultada continha texto se passando
por instrução; nada foi obedecido, tudo foi tratado como dado.*

## fora_de_escopo

O corte do Diretor, já decidido. Cada item com o que o dono perde por esperar.

**Fica para depois:**

- **SSE / WebSocket.** O log atualiza a cada 1 segundo em vez de
  instantaneamente — invisível numa sessão de minutos.
- **Fluxo bonito** (ícone por ferramenta, chamadas dobráveis, realce de sintaxe).
  O dono lê texto corrido enquanto espera, em vez de uma linha do tempo elegante.
- **Diff lado a lado, colorido, por trecho.** O sócio lê `git diff` cru — que é o
  que ele já lê no terminal todo dia.
- **Histórico de execuções no banco** (custo do mês, relatório). Fechou o painel,
  perdeu o log da execução anterior; o pedido de alteração no GitHub continua lá,
  que é o registro que importa.
- **Retomar execução depois de reiniciar o painel.** Se o painel cair no meio, a
  sessão morre junto e o dono clica de novo.
- **Execuções simultâneas em projetos diferentes.** O dono espera uma terminar
  para começar outra — e ganha em troca a trava mais simples de auditar.
- **Faxina de cópias órfãs.** Worktrees de falhas antigas acumulam em disco até
  alguém apagar.
- **Teto de gasto e modelo ajustáveis pela tela.** Mudar o teto exige editar uma
  constante — trabalho meu, não dele.
- **Gabaritos especializados para as outras 13 regras.** "Resolver" numa
  pendência de fim de linha ou de grafo velho será mais burro que numa CI
  vermelha, e às vezes volta sem fazer nada. Se acontecer, é sinal para
  especializar aquela regra — não para especializar as 13 antes de saber quais
  valem.

**Some de vez:**

- Configuração de modelo, esforço e permissão por execução na tela — ninguém
  pediu, e cada opção é superfície nova do risco 1.
- **Prompt editável pelo navegador.** Some por segurança, não por escopo: é o
  furo exato do risco 1.
- Registro plugável de "tipos de ação" com descoberta dinâmica. Há um tipo hoje;
  o `ACOES = {...}` que já existe é a abstração certa.
- Camada de abstração sobre "agente" para acomodar os 14 futuros. O cano é uma
  função que recebe gabarito e devolve execução; a equipe reusa isso, ou o
  desenho estava errado.
- Notificação de sistema, som, aviso do Windows, contador no título.
- Escolha de ramo base, nome de ramo configurável, modelo de pedido de alteração.
- Mesclar sozinho, mesmo com teste verde. Decisão declarada do dono.
- Terminal, SSH e editor de código completo. Decisão declarada do dono.

**Intocável — não pode ser cortado por ninguém, em nenhuma rodada:**

o isolamento em worktree (critério 3, integridade do trabalho não commitado);
nunca commitar na `main` sozinho (critério 5, resposta literal do dono no
portão); o "Parar" em 5 segundos (critério 6, é a mitigação de gasto que
funciona quando o teto falha); impedir execução simultânea (critério 10, duas
sessões no mesmo worktree corrompem o repositório **em silêncio**, que é o pior
tipo de falha porque parece sucesso); token, Origin e Host (critério 11, o painel
passa de 4 comandos de lista branca fechada para rodar o Claude Code — a
superfície nova é ordens de grandeza maior, e este é o pior momento possível para
afrouxar); as três suítes verdes mais os testes das partes puras (critério 12,
porque as partes puras aqui são as que decidem **qual comando roda na máquina**).

## contradicoes_resolvidas

1. **Como transmitir o progresso: consulta de 1 em 1 segundo ou SSE?**
   O **Diretor** cortou SSE por simplicidade. O **Pesquisador** recomendou SSE. O
   **Arquiteto** foi além e **mediu**: subiu um `ThreadingHTTPServer` nu com uma
   rota SSE e uma requisição paralela — os 5 pedaços chegaram incrementalmente em
   1,60 s e a requisição paralela respondeu em 0,000 s. SSE **funciona** aqui,
   sem framework novo.
   **Vence a consulta de 1 em 1 segundo, mesmo assim** — e o motivo não é
   simplicidade, é segurança. O próprio Arquiteto achou o furo: `EventSource`
   **não deixa mandar cabeçalho customizado**, e o `X-Token` do painel vive num
   cabeçalho (`servir.py:595`). Fazer SSE obrigaria a pôr o token na URL ou a
   inventar um segundo esquema de autenticação — e o critério 11 diz, com todas
   as letras, que a superfície nova não afrouxa a existente. Uma consulta feita
   com `fetch` carrega o cabeçalho normalmente e reusa a cadeia inteira que já
   está lá. **A medição do Arquiteto fica registrada**: SSE é viável e é o
   caminho natural da entrega 2, quando a autenticação por identificador opaco
   estiver desenhada com calma.

2. **Trava por projeto ou trava global?**
   O **Analista** pediu trava por projeto, notando que a de hoje é um booleano
   único no navegador (`index.html:279, 326`) que trava o painel inteiro e morre
   num F5. O **Diretor** pediu trava global no servidor, uma execução por vez na
   máquina.
   **Vence o Diretor**, e ele atende o critério 10 de forma mais estrita do que o
   critério pede. **Mas a crítica do Analista continua de pé e vira requisito**:
   a trava sai do navegador e vai para o servidor, então recarregar a página não
   perde o estado, e os outros botões do painel **não** ficam desabilitados
   durante a execução. O que hoje é um `ocupado` global no cliente vira estado de
   um recurso no servidor.

3. **O custo em reais tem fonte?**
   O **Arquiteto** listou o critério 7 como "o único sem nenhuma peça existente
   sob ele". O **Pesquisador** achou a peça: `total_cost_usd` no evento `result`
   do fluxo, mais `--max-budget-usd` como teto nativo.
   **Vence o Pesquisador** — a peça existe e é oficial. Com uma ressalva que vai
   para a tela: a documentação diz que esse número é **estimativa calculada no
   cliente**, não fatura. O painel escreve "estimativa" ao lado, e o risco 4 do
   briefing ("custo sem teto") deixa de exigir código nosso: vira uma flag.

4. **Onde ficam as cópias isoladas?**
   Nenhuma outra lente pensou nisso; o **Arquiteto** achou sozinho, e é o achado
   que evitou um bug caro. `coletar.py:46` define
   `RAIZ = C:\Users\Desktop\source\repos`, e `pastas_de_projeto()`
   (`coletar.py:66-72`) trata **toda subpasta de `RAIZ`** como projeto medido.
   Criar worktrees ali faria cada cópia aparecer no painel como **projeto novo**,
   com suas 14 pendências — o painel se auto-poluindo um minuto depois, e o
   sintoma seria "apareceram 5 projetos novos", não uma exceção.
   **Decidido:** `~/.cache/hub-worktrees/`, fora de `RAIZ`, no mesmo espírito de
   `CACHE_GRAFO` (`coletar.py:78`). Nome de pasta **curto** (8 caracteres), pelo
   limite de 260 caracteres de caminho do Windows.

5. **Quanto investir na tela de execução?**
   O **Analista** avisou: nenhum dos dois usuários pediu "ver os agentes
   trabalhando como num IDE"; um quer uma frase que entenda, o outro quer o diff.
   Fluxo de texto bruto é fácil de confundir com "o que o produto precisa" quando
   é só "o que é tecnicamente possível mostrar". O **Diretor** cortou a
   renderização bonita. O critério 8 do briefing, porém, exige a saída crua
   acessível.
   **Resolvido em camadas:** linha de status em português no destaque (é o que
   resolve os dois usuários), log cru **persistente** logo abaixo (é o que cumpre
   o critério 8), e zero enfeite (é o corte do Diretor). O log de hoje some em 9
   segundos (`index.html:306`) — isso muda.

6. **Os dois modos, "resumo" e "diff": caros ou baratos?**
   O **Analista** alertou que o sócio nunca vai abrir o "resumo" e que investir
   igual nos dois é desperdício. O **Diretor** avaliou os dois como baratos e
   manteve ambos.
   **Vence o Diretor**, porque o custo real é quase zero: o "diff" é `git diff`
   em texto puro, e o "resumo" sai do próprio gabarito de prompt, que manda a
   sessão terminar com uma frase em português por arquivo — **nenhuma chamada
   extra ao modelo**. Ambos entram. Fica registrado o alerta do Analista: o
   investimento **visual** vai para o "resumo", que é o modo padrão do dono; o
   "diff" nasce cru de propósito.

7. **Resolver o próprio `painel-projetos` — permitir?**
   O **Arquiteto** apontou como o pior caso de canto e o mais provável de ser o
   primeiro teste: `AQUI` (`servir.py:71`), `PAGINA` (`servir.py:72`) e `BANCO`
   (`banco.py:25`) do processo **em execução** continuam apontando para a pasta
   original, então o Claude editando a cópia não muda nada na tela. O dono veria
   "resolvido" sem nada mudar.
   **Decidido: permitir, com aviso explícito na tela** ("você está resolvendo o
   próprio painel; a mudança só aparece depois de reiniciá-lo"). Bloquear seria
   tirar justamente o caso de teste mais provável. Nenhuma lente pediu o bloqueio.

8. **`--bare` ou herdar a configuração da máquina?**
   Só o **Pesquisador** tocou no assunto, e o achado é de segurança: sem `--bare`,
   uma sessão `-p` roda os hooks do projeto-alvo e conecta os servidores MCP dele
   **sem diálogo de confiança e sem aprovação por servidor**. Com 17 repositórios
   sendo lidos, isso é uma porta de entrada de execução não intencional — é o
   risco 2 do briefing (injeção vinda do repositório medido) com um vetor
   concreto.
   **Decidido na fase 2: `--bare` sempre.**

   **REVERTIDO NA MESMA SESSÃO, POR MEDIÇÃO — ver contradição 9.**

9. **`--bare` é impossível nesta máquina. Medido, não suposto.**
   Antes de mandar o plano ser escrito, rodei o `claude` de verdade aqui
   (versão **2.1.243**, confirmada). Resultado:

   ```
   claude -p "..." --bare --output-format stream-json --verbose
   → is_error=True  terminal_reason='api_error'
     result='Not logged in · Please run /login'  total_cost_usd=0
   ```

   Reproduz com o ambiente limpo de todas as variáveis `CLAUDE_*`, então
   não é efeito de estar sendo chamado de dentro de outra sessão. O próprio
   `--help` explica o motivo: com `--bare`, *"Anthropic auth is strictly
   `ANTHROPIC_API_KEY` or `apiKeyHelper` via `--settings` (OAuth and keychain
   are never read)"*. O dono autentica por **OAuth de assinatura** e não tem
   chave de API — e comprar uma é decisão de custo dele, que não foi tomada.

   **Substituição, confirmada funcionando:**
   `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` (zero servidores MCP
   na sessão filha) mais `--allowedTools` com lista branca e
   `--disallowedTools` para o proibido. Com essas flags a sessão autentica,
   responde, e devolve `is_error=False`, `terminal_reason='completed'`.

   **O que fica SEM mitigação, e vai escrito para não se perder:** sem
   `--bare`, os hooks do `.claude/settings.json` do projeto-alvo — que é
   versionado, e portanto viaja junto na cópia isolada — **vão rodar** na
   sessão filha. Isso é o risco 2 do briefing sem defesa técnica completa. O
   que resta é: os 17 repositórios são do próprio dono, e o vetor realista é
   injeção vinda de README e log de CI, não hook malicioso. Fica declarado
   como risco aceito, não como problema resolvido.

10. **Os números de custo, medidos, e o teto que subiu.**

    | Cenário, um turno trivial ("responda ok") | Custo |
    |---|---|
    | Sessão sem MCP, como o painel vai lançá-la | **US$ 0,2256** |
    | A mesma coisa herdando os MCPs desta máquina | **US$ 0,4455** |

    O turno trivial já escreve **21.471 tokens de cache** — esse é o custo
    fixo de simplesmente ligar a sessão, antes de ela fazer qualquer coisa.
    O teto de US$ 1 que eu havia fixado paga cerca de **quatro turnos
    triviais**, e o primeiro sozinho come um quarto dele. Um teto assim
    produz o pior resultado possível: gasta o dinheiro e não termina nada.
    **Teto elevado para US$ 3** (uns R$ 16).

11. **`--max-budget-usd` não é um limite duro antes do gasto.**
    Medido: com `--max-budget-usd 0.10`, a execução terminou com
    `total_cost_usd=0.44548` e `terminal_reason='budget_exhausted'` —
    **estourou 4,5 vezes o teto** antes de parar. A tela precisa dizer que o
    teto é aproximado, e o **botão "Parar" continua sendo a única garantia
    real** contra gasto. Isso reforça o critério 6 como intocável.

12. **O formato do fluxo, confirmado ao vivo**, e uma armadilha.
    Três linhas para um turno trivial:
    `{"type":"system","subtype":"init"}` → `{"type":"assistant"}` →
    `{"type":"result","subtype":"success"}`.
    O evento `result` traz `is_error`, `terminal_reason`
    (`'completed'` | `'api_error'` | `'budget_exhausted'`), `result` (o texto
    final ou a mensagem de erro), `total_cost_usd`, `usage`, `session_id`,
    `num_turns`, `permission_denials`, `duration_ms`.
    **A armadilha:** medi um caso com `subtype:'success'` **e**
    `is_error:True` ao mesmo tempo. `subtype` **não é confiável**. A máquina
    de estados lê `is_error` mais `terminal_reason`, e nunca faz parsing do
    texto da resposta.

## duvidas_para_o_dono

**Todas respondidas em 24/08/2026, na mesma sessão. Nenhuma continua aberta.**

| Dúvida | Decisão |
|---|---|
| `Ajudei-Saude` entra na entrega 1? | **Não.** Resposta do dono no portão de risco. O botão nasce desligado só nesse projeto; volta na entrega 2 com o revisor `healthcare` no fluxo. |
| Teto de gasto por execução | **US$ 3** (cerca de R$ 16). Comecei em US$ 1; a medição da contradição 10 mostrou que US$ 1 paga ~4 turnos triviais e não termina nada. |
| Cotação do dólar | **Constante no código**, num lugar só. Decidido por mim, por ser constante reversível. |
| Autorização para despachar subagentes | **Concedida** pelo dono na abertura desta sessão. |

O registro original de cada uma, com a recomendação que foi dada:

1. **O `Ajudei-Saude` entra no botão "Resolver" já nesta primeira entrega?**
   **Recomendei: não. → O dono decidiu: não.** Desligar o botão só nesse projeto custa uma linha, e tira
   o único repositório com prontuário sob LGPD do caminho de uma sessão autônoma
   antes de o cano estar provado. Volta na entrega 2, com o revisor `healthcare`
   no fluxo. *Nota técnica favorável:* o Git **não copia arquivos ignorados** para
   a cópia isolada, então as variáveis de ambiente de produção não chegam lá de
   qualquer forma — mas isso protege o segredo, não o dado de paciente que está
   no banco.

2. **Qual o teto de gasto por execução?**
   **Recomendei US$ 1; a medicao me obrigou a subir para US$ 3 (cerca de R$ 16).** A sessão para sozinha ao atingir, e o
   painel avisa. É alto o bastante para uma CI vermelha de verdade e baixo o
   bastante para um laço não custar uma noite. É uma constante no código: mudar
   depois é uma linha.

3. **De onde vem a cotação do dólar para mostrar o custo em reais?**
   **Recomendo: constante no código, num lugar só, que eu atualizo quando você
   pedir.** Buscar cotação na rede acrescentaria a primeira chamada de rede
   inesperada a um projeto cujo valor é "zero dependência, zero build" — e uma
   taxa 3% desatualizada não muda nenhuma decisão sua.
