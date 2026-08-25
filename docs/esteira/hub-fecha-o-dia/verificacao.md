# Verificação — o HUB fecha o dia

> Fase 6 da esteira `hub-fecha-o-dia`, 25/08/2026. Cada critério do `briefing.md`
> com a prova ao lado — comando rodado e saída, não afirmação.

## Os 10 critérios de aceitação

| # | Critério | Prova | Estado |
|---|---|---|---|
| 1 | A tabela `historico` cresce a cada coleta | passou de **1 linha para 49** em ~15 min de painel rodando; hoje grava só quando o número muda, com batimento de 1 h | **passou** |
| 2 | Cada pendência sabe a própria idade | `/api/dados` traz `visto_em`, `dias`, `nova`, `desde_o_inicio` e `dias_min` nas 27 | **passou** |
| 3 | O painel diz quantas o dono fechou | `tendencia: {novas_24h, fechadas_24h, resolvidas_7d, abertas, direcao, serie}`, com 8 testes sobre o motor, sem depender do relógio real | **passou** |
| 4 | O briefing é uma frase de verdade | 4 estados produzem 4 textos distintos; teste trava que ele nunca diz "tudo certo" com pendência alta aberta | **passou** |
| 5 | Dez linhas de "grafo velho" viram uma | **27 pendências → 10 linhas** na tela, medido no `/api/dados` real. O critério pedia ≤18 | **passou com folga** |
| 6 | Site fora do ar vira pendência alta | servidor de mentira respondendo 200, 301, 404, 503 e recusando conexão: só 503 e a recusa geram pendência | **passou** |
| 7 | Divergência local × servidor aparece | medido de verdade: `dents` tem **4 commits na `main` publicados a menos**, último deploy em 19/08. `painel-projetos` fica calado (não tem workflow de publicação) | **passou** |
| 8 | Nada quebrou, e há mais teste que antes | **281 testes**, cinco suítes, todas verdes. Eram 203 | **passou** |
| 9 | A CI fica verde e conhece as suítes novas | `test_memoria.py` e `memoria.py` entraram no `ci.yml` à mão | **a confirmar no GitHub** |
| 10 | A documentação anda junto | `README.md` ganhou três seções no mesmo trabalho, incluindo o que a regra 15 **não** garante | **passou** |

## O que os revisores acharam

Três revisores especialistas, despachados em paralelo sobre o ramo commitado.

**Segurança — nenhum bloqueante.** Quatro hipóteses foram escaladas e as quatro
**derrubadas com teste**, não com opinião:

- SSRF em `mede_site`: `::ffff:127.0.0.1`, `[::1]`, IP decimal (`2130706433`),
  hexadecimal, `127.1`, `nip.io`, `localtest.me`, `169.254.169.254`, credencial
  embutida (`http://evil.com@127.0.0.1/`) — **todas barradas**, umas em
  `url_segura`, outras em `host_publico`. Redirecionamento confirmadamente não
  seguido.
- Injeção de caminho no `gh api`: `subprocess.run` com lista de argumentos, sem
  shell; e o git proíbe `..`, `?`, `*`, `~`, `^`, `:` e espaço em nome de ref.
- Reintrodução do caminho de injeção de prompt de 25/08: `site["codigo"]` é
  sempre inteiro; `sha` é hash truncado; a URL vai só na **ação**, nunca no
  texto. `so_dado()` e a etiqueta de dado não-confiável continuam cobrindo.
- SQL por formatação em `memoria.py`/`banco.py`: zero ocorrências, inclusive o
  `LIMIT` é parametrizado.

Sobrou dele o achado mais importante do dia, que nenhum teste pegava e que eu
não tinha previsto — está na seção abaixo.

**Python — nenhum bloqueante**, dois importantes e um menor, todos corrigidos.

**Design — três bloqueantes**, todos de contraste e acessibilidade, todos
corrigidos. Os números foram **remedidos por mim** antes de aceitar, e os do
revisor estavam certos nos três.

## Os quatro defeitos que só apareceram rodando

Nenhum destes estava no plano. Todos vieram de olhar o resultado de verdade.

1. **A armadilha da estreia.** Na primeira coleta, as 27 pendências ganham
   `visto_em = agora` — inclusive um grafo velho há 23 dias. A tela estrearia
   com 27 selos de "nova" mentindo em uníssono, e o briefing anunciaria "27
   apareceram nas últimas 24 h". Fechado nas duas pontas (`desde_o_inicio` e o
   filtro de `novas_24h`), e depois melhorado: em vez de silêncio, a idade vira
   um piso honesto — "aberta há mais de 9 dias".
2. **A coleta vazia que virava comemoração** (achado da revisão de segurança).
   Coleta que termina bem mas não enxerga projeto nenhum fecharia as 27
   pendências de uma vez — inclusive as de segurança — e no minuto seguinte o
   painel se gabaria de ter fechado 27. É o painel mentindo sobre segurança.
3. **A publicação medida só para quem tem site** (erro meu de ligação). O
   `dents` tem workflow de deploy e estava 4 commits atrás, invisível só porque
   não tem `url_prod` escrito no `casos.json`.
4. **O histórico crescendo sem parar**: 4 linhas por minuto, 2 milhões por ano,
   quase todas idênticas — e um gráfico de semana feito de 10 mil pontos iguais
   não mostra forma nenhuma.

## O que ficou de fora, e por quê

- **Os 203 alertas de segurança abertos** (93 `medconsultoria`, 71
  `odontologia-pericia`, 20 `investrix`, 19 `workspace-medconsultoria`). É o
  achado de maior valor desta análise inteira, e está fora **de propósito**:
  entrar de carona aqui transformaria uma entrega provável em duas improváveis.
  Merece esteira própria, provavelmente com o botão "Resolver".
- **Reindexar o grafo sozinho** — seria a cura do ruído em vez do curativo, mas
  indexação já travou esta máquina duas vezes. Agrupar é o passo seguro.
- **Fase 4 da spec original** (`radar.py` lendo este banco) — janela `~/.claude`.
- **A regra 15 medindo produção de verdade** depende do sim do dono. O código
  está escrito e testado; o interruptor `MEDIR_SITE` decide.

## Duas decisões que são do dono

1. **Medir os cinco endereços de produção** (`MEDIR_SITE`). Recomendação: sim.
2. **Tirar o `d.json` do histórico do ramo** antes do push. São 110 KB pareando
   endereço de produção com contagem de falha de segurança. O ramo nunca foi
   enviado, então sai de graça agora; depois do push custaria reescrita de
   história compartilhada.
