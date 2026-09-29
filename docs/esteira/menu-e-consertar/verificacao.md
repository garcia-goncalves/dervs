# Verificação — menu enxuto e botão "Consertar com IA" (29/09/2026)

Ramo `feat/menu-e-consertar`. Critérios em `briefing.md`.

| # | Critério | Estado | Prova |
|---|---|---|---|
| 1 | Menu com exatamente 4 itens | ATENDIDO | `test_menu.py` (sabotado com um 5º item: reprova) e menu lido no navegador: Painel, Consertar, Conectar, Conta |
| 2 | Rotas antigas abrem a tela certa | ATENDIDO | `test_menu.py` (sabotado sem o alias `consumo`: reprova) e as 8 rotas percorridas no navegador, com o item do menu certo marcado |
| 3 | Botão enfileira; segundo clique aprova | PARCIAL | Enfileirar: clicado no navegador local (POST 200, tarefa "grimoire — env_drift, na fila, espera o clique"). **Aprovar não foi clicado**, de propósito: rodaria o Claude num repositório real e gastaria dinheiro |
| 4 | Só alerta do próprio dono, mesma resposta | ATENDIDO | `test_servir.OBotaoConsertarComIA`, duas contas, sabotado (busca em todas as contas: reprova) |
| 5 | Regra não mecânica: sem botão e 403 | ATENDIDO | Teste de servidor + `consertavel` conferido nos dados reais: só `memoria_crlf` e `env_drift` |
| 6 | Motivo em português quando não pode rodar | ATENDIDO | Um teste por motivo (sem computador, sem autorização, teto do dia), cada um sabotado |
| 7 | Link do pedido de alteração | ATENDIDO NO SERVIDOR | `/api/tarefas?id=` devolve `pr_url` (teste sobe um desfecho de verdade pelo fio do agente). A tela mostra o link quando existe; **não vi um link real**, porque nenhuma tarefa terminou aqui |
| 8 | Suítes verdes; testes novos na CI | ATENDIDO | Todos os `test_*.py`, um a um, saída 0; `test_menu.py` tem passo próprio no `ci.yml` |
| 9 | Documentação junto | ATENDIDO | `A-APLICACAO.md`, `LINKS.md`, `CLAUDE.md` no mesmo ramo |

## O que dois revisores acharam, e o que foi feito

- **Python** (mesmo achado do de segurança, de forma independente): o pedido
  repetido dizia "já estava na fila" para conserto que falhou ou terminou. Corrigido
  na rota (lê o estado real, com o dono no `WHERE`), com 4 testes sabotados.
- **Segurança:** nenhum bloqueante. Autorização entre contas, CSRF, injeção, XSS e
  CSP conferidos.
- **Achado clicando:** `Ajudei-Saude` (bloqueado) aparecia com botão que o servidor
  sempre recusaria. `consertavel` agora sai falso em projeto bloqueado.
- Testes que não podiam reprovar: o do balcão próprio só provava o 429; ganhou o
  caso que esgota `consertar` e exige que a auditoria responda.

## O que isto NÃO prova

- **Nenhuma tarefa rodou de ponta a ponta.** Não há aqui um computador pareado e
  autorizado a consertar, e aprovar gastaria dinheiro real. O caminho *aprovar →
  agente roda → PR → link na tela* continua provado só por partes (o backend já
  tinha testes; a tela do link, não).
- **Não foi ao servidor.** Publicar depende da cobrança do GitHub, do administrador
  da VPS (`ATIVO=sim`) e do sinal do dono.
- **Sem teste de JavaScript em navegador.** `test_menu.py` lê o texto do
  `painel.js` (com sabotagem); o comportamento foi conferido clicando, uma vez.
- **CI do GitHub não rodou** (cobrança). A prova é local.

## Continua aberto (de propósito)

- `memoria_crlf` vai ao braço `claude`, embora `fila.REGRAS_MECANICAS` a mapeie
  para o mais barato (`mecanico`). Só custo, e o teto diário protege.
- `fila.trabalhar` enfileira com id `regra:projeto` (sem o dono). Ninguém o chama
  em produção hoje; quem ligar duplica a tarefa.
- O título da tarefa ainda mostra o nome técnico da regra (`env_drift`).
- Fundir Trabalho e Auditoria numa tela só; consertar dependências e achados de
  segurança (segunda rodada).
