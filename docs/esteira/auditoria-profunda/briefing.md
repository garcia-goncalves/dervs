# Briefing — A Auditoria Profunda

> Fase 1 da esteira. Escrito em 02/09/2026. **Aguardando o portão 1 do dono.**

## pedido_original

> "pode começar por onde achar melhor... ative todos seus melhores agentes e seja
> inteligente e ultra performance... faça tudo o que puder... dê o melhor de si e
> implemente tudo do bom e do melhor... quero que a aplicação ajude a sempre deixar
> meus projetos sempre 100%... quero que a aplicação analise tudo debug linha a linha
> profundamente, faça relatórios, corrija, desenvolva, crie, programe, etc... faça
> tudo... podemos usar aplicações opensource como base pra dentro da minha aplicação...
> como o BOLT DIY que é opensource e cria site e aplicações.... podemos ter algo
> parecido.... ou apenas agentes que criem tudo... quero algo revolucionário... quero
> suas melhores ciritcas e ideias.... faça o que achar melhor pro DERVS!"

## entendimento

O DERVS hoje sabe que algo está errado **por fora** — commit sem enviar, PR parado, CI
vermelha, cota estourada — e sabe **executar** uma tarefa que alguém escreveu. Ele nunca
abre o código. Esta entrega dá a ele o olho que falta: o DERVS lê cada projeto por
dentro, arquivo por arquivo, e devolve um relatório em português dizendo o que está
errado, onde, e o que fazer — e cada achado nasce já como tarefa na fila, com a cor do
semáforo, pronta para ser consertada sozinha (verde) ou aprovada por um clique (vermelho).

É o elo que falta entre "painel que mede" e "meus projetos sempre 100%": hoje quem
escreve a tarefa é o dono; depois desta entrega, quem escreve é o próprio DERVS.

## usuario_alvo

**Desenvolvedor — a lente DX está ligada.** Dois usuários reais: o dono, que decide o
produto e não opera terminal, e o André, que programa. O momento de uso é o começo do
dia: o dono abre o painel e quer ver *"5 coisas foram consertadas de madrugada, 2
esperam você"*, sem ler código. O André abre o mesmo relatório e quer o arquivo e a
linha, para conferir o diagnóstico antes de aprovar.

## criterio_de_aceitacao

Cada item abaixo se prova por um comando, um teste ou uma olhada na tela.

- [ ] **A auditoria existe como tipo de tarefa.** Uma tarefa `auditar` dispara o agente sobre um repositório e devolve achados estruturados (`arquivo`, `linha`, `gravidade`, `frase`, `o_que_fazer`). *Prova:* `python test_auditoria.py` verde: defeitos plantados num repositório de mentira têm de aparecer.
- [ ] **Saída malformada não vira número.** Se o agente devolver algo que não é a lista esperada, o projeto fica em **sem dados** — nunca em "0 achados". *Prova:* caso de teste com saída truncada, saída vazia e saída com JSON quebrado; os três resultam em `sem dados`, nenhum resulta em zero.
- [ ] **Todo achado tem carimbo e ação.** Cada achado exibe quando foi medido, e nenhum achado entra na lista sem uma ação que o dono possa executar. *Prova:* `test_regras.py` estendido, cobrando os dois invariantes já existentes sobre os achados de auditoria.
- [ ] **O id do achado é estável entre duas auditorias.** Silenciar um achado o mantém silenciado na auditoria seguinte, mesmo que a ordem da lista mude. *Prova:* teste que roda a mesma auditoria duas vezes com a ordem embaralhada e exige ids iguais.
- [ ] **A auditoria respeita o teto de gasto.** Auditoria que estouraria os R$ 50 do dia não dispara, e a tela diz por quê. *Prova:* teste que fixa o gasto acumulado acima do teto e exige recusa com motivo.
- [ ] **A tela nova existe, em português, e cabe em 360px.** *Prova:* `test_design.py` estendido + olhada na tela em `http://localhost:4777`.
- [ ] **Nenhuma fronteira foi afrouxada.** `servir.py` continua sem importar `execucao`, `fila` ou `banco` a partir de `tarefas.py`; nenhuma rota executa comando. *Prova:* `python test_rotas.py` e `python test_tarefas_nao_publicam.py` verdes, sem nenhuma linha removida deles.
- [ ] **A suíte inteira verde na CI**, não apenas os arquivos tocados, e `test_imagem.py` verde (a lista de cópia do `Dockerfile` acompanha os módulos novos).
- [ ] **Toda variável de ambiente nova aparece no `docker-compose.yml`.** *Prova:* `test_publicar.py` verde — o guarda que compara as duas listas.

## fora_de_escopo

Nomeados com destino, não descartados:

- **O construtor de aplicações do zero** (o "algo parecido com o Bolt.diy"): criar um
  projeto novo a partir de uma frase. Fica para a fatia seguinte, e o motivo está na
  seção de crítica abaixo — o DERVS já tem um motor mais forte que o do Bolt.diy; o que
  falta é a porta de entrada, e ela é trabalho próprio.
- **Terminal no navegador, a lousa e o editor de código**: continuam nas Fatias 3 e 4,
  como já está escrito em `docs/A-APLICACAO.md` §11. Nada aqui os antecipa.
- **Qualquer dependência externa em Python.** Lei 1 do repositório. A análise pesada é
  feita pelo agente `claude` no computador, que já está instalado; o DERVS só pede,
  recebe e desconfia.
- **Auditoria automática e recorrente sem o dono ligar.** Nesta entrega a auditoria é
  disparada por um botão e por tarefa na fila. O agendamento noturno entra depois de a
  primeira auditoria ter rodado de verdade em pelo menos um projeto.
- **Consertar sozinho o que a auditoria achar de vermelho.** A auditoria escreve a
  tarefa; a cor e a execução seguem o semáforo que já existe, sem exceção nova.

## riscos

**Sim, há riscos, e são três.**

1. **Config de publicação.** Um achado de auditoria vira tarefa, e tarefa vira diff.
   `fila.diff_toca_publicacao` já barra qualquer mudança em `.github/workflows/`,
   `Dockerfile`, `docker-compose.yml` e `infra/` — mas a auditoria é a primeira coisa
   que vai *ler* esses arquivos e *querer* mexer neles. A trava precisa ser reconfirmada
   por teste com um achado plantado exatamente nesse caminho.
2. **Custo.** Ler um repositório inteiro é a operação mais cara que o DERVS já fez. O
   teto de R$ 50/dia existe, mas foi dimensionado para correções de 2 minutos. Precisa
   de um teto próprio por auditoria e de uma medição real antes de ligar em vários
   projetos.
3. **Injeção pelo próprio código auditado.** O agente vai ler arquivos que podem conter
   texto escrito para dar ordem a um modelo de linguagem (um `README` de terceiro, uma
   dependência). A saída do agente é **dado, nunca instrução** — e isso precisa de um
   teste com um arquivo plantado contendo uma ordem, exigindo que ela não seja obedecida.

Não há dado de paciente nem pagamento nesta entrega. Migration: sim, uma tabela nova de
achados — reversível, e sem apagar nada existente.

## plano_de_voo

**Fases 1 a 7, com a fase 3 ligada** (há tela nova).

- Fase 1 — Interrogador, `opus`. Feita. 0 despachos (escrita direta).
- Fase 2 — Descoberta em **modo enxuto**: as quatro lentes (Analista, Arquiteto,
  Pesquisador, Diretor) em **um despacho gordo**, `opus`. O domínio é conhecido e o
  repositório já foi lido nesta sessão. **+1 despacho externo de pesquisa já disparado**
  (bolt.diy, licença do WebContainer, flags reais do `claude` não-interativo, e os termos
  da Anthropic sobre assinatura Max em servidor). **2 despachos.**
- Fase 3 — Design: uma tela nova apenas, dentro da direção "Torre de Controle" já
  aprovada. Um despacho, `sonnet`. **1 despacho.**
- Fase 4 — `neguin-planner`, `opus`. **1 despacho.**
- Fase 5 — `neguin-executor` em worktrees isoladas, `sonnet`, de 4 a 6 etapas
  paralelas. **5 despachos.**
- Fase 6 — Revisão: `python-reviewer`, `security-reviewer` e `design-reviewer` em
  paralelo, mais um verificador que **sabota** cada guarda novo para provar que ele
  consegue reprovar. **4 despachos.**
- Fase 7 — Cronista, `sonnet`: documentação, memória, CI, PR e handoff. **1 despacho.**

**Despachos previstos: 14.**

Portões previstos: o 1 (este), e o 4 (risco: a migration da tabela nova e o teto de
custo). Os portões 2 e 3 devem ficar fechados — não há decisão de produto pendente e a
direção visual já está aprovada e travada.
