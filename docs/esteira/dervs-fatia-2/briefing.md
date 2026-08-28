# Briefing — DERVS, Fatia 2: o painel ganha braços

Fase 1 da esteira. Escrito em 28/08/2026 pelo Interrogador, a partir de uma rodada de
perguntas ao dono e de três pesquisas externas rodadas em paralelo com a entrevista.

**Este arquivo não substitui `docs/esteira/dervs/briefing.md`** — aquele é o da Fatia 1,
aprovado e entregue. Este abre a Fatia 2.

## pedido_original

Primeira mensagem, 28/08/2026 à noite (já transcrita no §11 da fonte única):

> "Quero a fusão das aplicações conforme combinado (dervs-hub + painel-projetos) e muito
> mais. Quero tudo que um DEV precisa."

Segunda mensagem, 28/08/2026, ao abrir esta esteira:

> "Lembre-se que preciso que vc faça buscas avançadas na internet e em vários repositórios
> do github pra analisar as melhores ferramentas e plataformas para devs e me ajude com as
> suas melhores ideias. Podemos implementar partes/pedaços de aplicaçoes/ferramentas
> open-source (as melhores e que fizerem sentido). Quero realmente que o Dervs seja o
> arsenal perfeito para DEV. Um canivete suiço de primeira linha. Com integração pra um
> monte de coisas. E com o Claude Code rodando 100% nele. Quero talvez o Codex também.
> Juntos. Para dividir tarefas. Tenho a API da openai com crédito. Quero suas ideias e
> criticas e sugestões. Sempre me recomende O MELHOR. Sempre que me perguntar algo, me dê
> alternativas e sempre me mostre a sua RECOMENDAÇÃO."

Resposta à primeira pergunta (onde o trabalho executa), literal:

> "gostaria de entender como seria colocar nos 2 (PC e servidor. Eu teria que instalar o
> Claude Code no meu servidor VPS? É isso? Pq eu gostaria sim que o DERVS conseguisse
> acessar tudo (meu PC / Github / Servidor) para RESOLVER QUALQUER PROBLEMA. O que eu quero
> é isso: Que o Claude Code cuide de TUDO. RESOLVA QUALQUER PROBLEMA. Sem eu precisar
> colocar a mão. TUDO! A única coisa que quero fazer é clicar em botões e somente aprovar o
> Deploy/Publicar."

Resposta à segunda pergunta (quanta autonomia), literal:

> "Bom... se vc está dizendo que esse é o melhor, vou acreditar. Quero sim que o DERVS seja
> independente e podemos arrumar o documento (analisa, executa, programa, desenvolve,
> monitora, resolve problemas, tudo). Ouvi dizer que a melhor coisa é colocar o claude pra
> monitorar e codex pra executar. Não sei se é verdade."

## entendimento

O DERVS deixa de ser só um mirante e passa a ser uma oficina: além de medir o estado dos
projetos, ele **executa trabalho de programação por conta própria**, dirigido pelo Claude
Code, tanto no computador do dono quanto na VPS.

A peça nova é **o trabalhador**: o agente que já existe hoje (instalado no computador,
não escuta porta nenhuma, só pergunta ao painel se há tarefa) ganha a capacidade de rodar
o binário `claude` sobre um repositório e devolver o resultado. O mesmo trabalhador
instalado na VPS dá ao DERVS o braço do servidor — um binário só, dois lugares.

A autonomia é graduada por um **semáforo**: cada tipo de tarefa nasce verde (roda sozinha
e avisa depois) ou vermelha (para e espera um clique). Publicar é sempre vermelho.

## usuario_alvo

**Sim, é desenvolvedor — a lente DX do Analista está ligada.**

Dois perfis, os mesmos da Fatia 1, em momentos diferentes:

1. **Thiago (dono, não opera terminal)** — abre o painel de manhã, vê o que quebrou, clica
   em "resolver" e vai fazer outra coisa. Volta e vê o que foi feito, em português, com o
   diff explicado. Nunca digita comando. É ele quem aprova o vermelho.
2. **André (dev)** — quer ver a prova por baixo: qual comando rodou, qual foi a saída crua,
   qual o diff exato, quanto custou em tokens. Mesma tela, profundidade maior.
3. **Depois: o dev solo ou a dupla** com muitos projetos parados. Chega porque quer que o
   agente resolva o acúmulo. **Desinstala se a ferramenta pedir manutenção** — evidência
   de mercado na fase 2.

## criterio_de_aceitacao

Cada item abaixo tem de ser provável por comando, teste ou olhada na tela. Nenhum vale por
leitura de código.

1. **O trabalhador executa.** Um teste sobe um repositório de mentira, enfileira uma tarefa
   e prova que o processo `claude` foi disparado, que a saída em `stream-json` foi lida
   linha a linha, e que o resultado chegou ao banco. Comando: `python test_executor.py`.
2. **Zero dependência externa continua valendo.** A verificação automática segue verde: não
   existe `requirements.txt` nem `pyproject.toml`, e nenhum `import` fora da biblioteca
   padrão. O SDK oficial em Python está **proibido** (traz 4 dependências para embrulhar um
   subprocesso). Comando: o passo de CI que já existe.
3. **O semáforo obedece.** Um teste prova que tarefa marcada vermelha **não** executa sem
   registro de aprovação no banco, e que tarefa verde executa sem ele. Prova nos dois
   sentidos: o teste tem de ficar vermelho se a guarda for removida.
4. **Publicar continua sendo só do dono.** Nenhuma tarefa, de nenhuma cor, dispara o
   workflow de publicação. O teste que hoje varre as rotas ganha um irmão que varre as
   tarefas.
5. **O teto trava antes, não depois.** Um teste prova que, com o teto do dia já consumido,
   a tarefa é recusada **sem** o processo `claude` chegar a ser disparado.
6. **A caixa é isolada.** A tarefa que roda na VPS acontece dentro de um container
   descartável, sem nenhum segredo do painel no ambiente, com saída de rede permitida só
   para uma lista curta. Prova: um teste tenta alcançar um endereço fora da lista de dentro
   do container e falha.
7. **Nada de `vivo/` entra na imagem.** A trava atual (`.dockerignore` + `Dockerfile` que
   nunca usa `COPY . .`) continua provada pelo `test_imagem.py`.
8. **O dono vê o trabalho acontecendo.** Na tela, uma tarefa em andamento mostra o que está
   sendo feito, ao vivo, em português. Verificado clicando, não lendo código — e a evidência
   colada em `verificacao.md`.
9. **O diff é apresentado antes de virar commit.** Toda tarefa termina num branch, nunca na
   `main`, e a tela mostra o que mudou em linguagem que o Thiago entende.
10. **Todo texto de tela em português do Brasil**, conferido pelo vigia de vocabulário que
    já existe.

## fora_de_escopo

Cortado da Fatia 2 **de propósito**, com destino nomeado. Nada aqui é "não vai ter" — é
"não agora", e a ordem é por risco ÷ valor.

- **Terminal interativo no navegador** (xterm.js + PTY). É a peça mais perigosa do
  protótipo e a menos necessária depois que o agente executa sozinho. **Fatia 3.**
- **Codex como segundo executor.** A interface nasce pronta para ele nesta fatia (uma
  classe `Executor` com duas implementações previstas), mas só o Claude é ligado agora.
  Evidência: só compensa orquestrar dois fornecedores com 3+ tarefas independentes de 15+
  minutos; a fila do DERVS é de correções de 2 minutos. **Fatia 3.**
- **A lousa** (canvas de desenho e notas) do protótipo. **Fatia 3.**
- **O canivete suíço de ferramentas avulsas** (formatador de JSON, base64, JWT, hash,
  regex, cron...). São 15 funções baratas e independentes, todas em biblioteca padrão —
  boas para uma fatia própria, ruins para atrasar esta. **Fatia 3.**
- **Editor de código no navegador** (CodeMirror). **Fatia 4 ou nunca**, se o agente tornar
  desnecessário.
- **Gerenciar skills, MCPs e plugins do Claude** — continua sendo a **Fatia 4**, como já
  decidido no §10 da fonte única.
- **Integrações novas** (Sentry, Linear, Slack, Grafana, Cloudflare, Vercel). O ranking
  está na pesquisa; entram por demanda real, uma a uma, nunca em lote.
- **Cadastro público.** Continua fechado.

## riscos

**Alto, e em quatro frentes. Esta fatia é a mais perigosa já construída no DERVS.**

1. **Execução de comando por IA em máquina exposta à internet.** Quatro ataques públicos
   documentados em 2026 (claude-code-action em janeiro; "Comment and Control" em abril;
   Black Hat em agosto, atingindo Claude, Gemini e Codex; RoguePilot em fevereiro). O
   vetor comum: **texto envenenado numa issue ou comentário de PR vira ordem executada**,
   com exfiltração de segredo pelo próprio GitHub. Um dos furos teve nota 10,0.
2. **Configuração de deploy e produção.** O trabalhador na VPS convive com 26 containers e
   8 sistemas de terceiros do dono. Erro aqui derruba o negócio dele, não só o DERVS.
3. **Dinheiro.** O alerta de gasto do fornecedor atrasa cerca de um dia. Casos públicos de
   2026: US$ 1,3 milhão em 30 dias com ~100 agentes; US$ 437 numa noite num laço recursivo.
   O teto do DERVS **tem** de contar antes de disparar.
4. **Chave de API nova no servidor.** A assinatura Max do dono **não pode** ser usada para
   uso programático (regra da Anthropic). É um segredo novo a guardar, e ele nunca passa
   por chat, commit, memória ou documentação — só pelo caminho que já leva credenciais ao
   `/opt/dervs/.env`.

Não há dado de paciente nem pagamento nesta fatia. **Migration: sim** — a tabela de tarefas
ganha colunas (cor do semáforo, executor, custo, aprovação).

## plano_de_voo

**Modo: completo.** O escopo é grande, o domínio é novo (execução de agente com
isolamento) e o risco é alto — não é caso de modo enxuto.

| Fase | Papéis | Modelo | Despachos |
|---|---|---|---|
| 2 · Descoberta | Pesquisador **já rodou** (3 despachos, entregues) | sonnet ×2, opus ×1 | 3 ✔ feitos |
| 2 · Descoberta | Analista (DX) + Arquiteto (o que já existe no repo) | opus, em lote único | 1 |
| 2 · Síntese | Sintetizador → `spec.md` | opus (eu, sem despacho) | 0 |
| 3 · Design | **não roda direção nova** — a Torre de Controle está aprovada; só telas novas dentro dela | opus (eu) | 0 |
| 4 · Plano | neguin-planner → etapas verificáveis | opus | 1 |
| 5 · Execução | neguin-executor em worktrees isoladas | sonnet | 4 a 6 |
| 6 · Revisão | python-reviewer + security-reviewer, em paralelo | opus | 2 |
| 7 · Cronista | doc, memória, CI, PR, handoff | opus (eu) | 0 |

**Total previsto: 11 a 13 despachos**, dos quais 3 já foram gastos.

**Portões previstos:** o 1 (este briefing) agora. O 2 (decisão de produto) já foi
consumido em duas perguntas — onde executa, e quanta autonomia. O 3 (escolha visual) **não
abre**: a direção está aprovada. O 4 (risco) abre uma vez, antes de ligar o executor na
VPS: uma pergunta de sim ou não.
