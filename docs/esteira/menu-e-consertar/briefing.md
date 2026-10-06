# Briefing — menu enxuto e botão "Consertar com IA"

Aprovado em: 2026-10-06

## pedido_original

"Quero tudo funcionando 100% no local, no GitHub e no servidor, sincronizado e integrado. O fluxo e o menu estão confusos, toda a estrutura está confusa. Você pode refatorar para refinar/melhorar toda a aplicação. Quero que meus desenvolvedores tenham facilidade no dia a dia e com poucos cliques façam todas as aplicações monitoradas ficarem saudáveis e sem erros. O DERVS nasceu pra monitorar e deixar tudo saudável, e também para desenvolver de forma facilitada usando IA. Quero uma aplicação revolucionária." Depois: "ok, pode seguir sem me perguntar" à proposta de começar por menu de 4 lugares e botão Consertar para alertas mecânicos.

## entendimento

O menu de 7 itens vira 4 lugares com nomes que dizem o que fazem: Painel, Consertar, Conectar e Conta. Cada alerta mecânico e seguro ganha um botão "Consertar com IA" que enfileira a tarefa na fila que já existe, com aprovação em um clique e o resultado visível ao fim. Quando algo impede o conserto, a tela diz o motivo em português.

## usuario_alvo

Desenvolvedor (Thiago e André, depois devs de equipes pequenas) que abre o painel de manhã e quer, com poucos cliques, ver o que está quebrado e mandar a IA consertar. É desenvolvedor: a lente DX vale.

## criterio_de_aceitacao

- [ ] O menu superior tem exatamente 4 itens (Painel, Consertar, Conectar, Conta). Prova: olhada na tela e um teste que lê o `index.html`.
- [ ] Todas as rotas antigas (`#/trabalho`, `#/auditoria`, `#/consumo`, `#/computadores`, `#/entrada`) continuam abrindo a tela certa. Prova: teste de rotas e clique no navegador.
- [ ] Na tela de um alerta de regra mecânica (`memoria_crlf`, `env_drift`) existe o botão "Consertar com IA". Um clique cria uma tarefa na fila; um segundo clique, "Pode fazer", aprova. Prova: teste de servidor que percorre o fluxo, e clique real no navegador local.
- [ ] O botão só aceita alerta do próprio dono. Alerta de outra conta e alerta inexistente dão a mesma resposta (mesma regra da auditoria). Prova: teste cruzando duas contas, sabotado de propósito para provar que reprova.
- [ ] Alerta de regra que não é mecânica (ex.: `dependencia_insegura`, achados de segurança) NÃO mostra o botão e o servidor recusa o pedido. Prova: teste.
- [ ] Quando o conserto não pode rodar (computador não pareado, não autorizado, teto do dia estourado) a tela diz qual é o motivo, em português. Prova: teste de cada motivo e olhada na tela.
- [ ] O detalhe da tarefa mostra o link do pedido de alteração (`pr_url`) quando existir. Prova: teste.
- [ ] As suítes existentes continuam verdes e todo `test_*.py` novo está listado no `ci.yml`. Prova: rodar todas.
- [ ] `docs/A-APLICACAO.md`, `docs/LINKS.md` e `CLAUDE.md` refletem o menu novo no mesmo commit. Prova: leitura do diff.

## fora_de_escopo

- Consertar alertas de dependência insegura e achados de segurança (segunda rodada; risco de a IA mexer em segurança sem revisão humana).
- Fundir as telas Trabalho e Auditoria numa só tela; nesta rodada elas apenas passam a viver sob o item "Consertar".
- Login com GitHub no ambiente local.
- Publicar no servidor, mexer em cobrança do GitHub, mexer em `publicar.yml` ou no `Dockerfile`.
- Trocar tokens de design, tema ou tipografia.

## riscos

Toca o caminho que enfileira trabalho para o agente que roda `claude` no computador do dono: gasta dinheiro (teto R$ 50/dia, compartilhado) e escreve em repositório. Mitigação: só regras mecânicas, aprovação humana obrigatória, teto e trava de diff que já existem em `fila.py`/`tarefas.py`, e a conferência de dono da tabela `fila`. Não há migration prevista; se aparecer, volta ao portão de risco. Sem dado de paciente, sem pagamento, sem deploy.

## plano_de_voo

Modo enxuto. Fase 2 (descoberta) já feita por um Explore (sonnet) neste turno e por leitura direta do código; Sintetizador dispensado (escopo pequeno). Fase 3 (design) dispensada: reaproveita os tokens e componentes existentes. Fase 4: planejo eu mesmo, no modelo atual. Fase 5: 2 executores (sonnet) em worktrees isoladas, um para o servidor (rota + testes) e outro para a tela (menu + botão), em paralelo. Fase 6: revisores python e security (sonnet), mais clique real no navegador. Fase 7: documentação e PR. Despachos previstos: 1 (feito) + 2 + 2 = 5.
