# Briefing — o HUB fecha o dia

Aprovado em: 2026-10-06

> Fase 1 da esteira `hub-fecha-o-dia`. Escrito em 25/08/2026 sobre medição do
> painel rodando, não sobre suposição: 27 pendências reais, 17 projetos,
> `/api/dados` inspecionado item a item.

## pedido_original

"Analise tudo profundamente e comece por onde achar melhor. Faça tudo! Elabore o
melhor Painel para DEV do mundo. Eu mereço! Me ajude!"

## entendimento

O HUB hoje responde bem "o que precisa de mim agora?", mas responde isso **como
se todo dia fosse o primeiro**: não lembra de ontem, não sabe o que o dono já
resolveu, e trata dez tarefas idênticas como dez linhas iguais na mesma lista.
Esta entrega dá ao painel **memória do tempo** (o que é novo, o que apodreceu, o
que você fechou), um **briefing matinal** de uma frase escrito a partir dessa
memória, o **fim do ruído** que hoje toma 37% da lista, e a pergunta que nenhum
painel dele responde hoje: **o site está no ar, e o que está lá é o que você
escreveu?**

## usuario_alvo

**Desenvolvedor** — o dono, único usuário. Momento de uso: a primeira janela que
ele abre de manhã, antes de decidir em que projeto vai trabalhar, e de novo ao
longo do dia depois de terminar cada tarefa. A tela é para ser aberta todo dia,
não visitada uma vez por semana; qualquer coisa que a torne ignorável é defeito.
Liga a lente DX.

## criterio_de_aceitacao

- [ ] **A tabela `historico` cresce a cada coleta local.** Prova: `python -c "import sqlite3;print(sqlite3.connect('hub.db').execute('select count(*) from historico').fetchone())"` sobe entre duas coletas separadas por mais de 60 s. Hoje tem **1 linha só**.
- [ ] **Cada pendência sabe a própria idade.** O JSON de `/api/dados` traz `visto_em` e `dias` em toda pendência, e a tela mostra "nova" para quem nasceu nas últimas 24 h. Prova: `curl -s localhost:4777/api/dados | python -c "..."` imprime `dias` para as 27.
- [ ] **O painel diz quantas o dono fechou.** `/api/dados` traz `tendencia: {resolvidas_7d, novas_24h, abertas_por_gravidade, serie}`, e o número de resolvidas é maior que zero depois de resolver uma pendência de mentira e recoletar. Prova: teste automatizado sobre o motor, sem depender do relógio real.
- [ ] **O briefing matinal é uma frase de verdade, nunca genérica.** Aparece no topo da tela, cita número e nome de projeto, e muda quando o dado muda. Prova: três estados (dia limpo, com alta, piorando) dão três textos distintos, e nenhum diz "tudo certo" havendo pendência alta.
- [ ] **Dez linhas de "grafo velho" viram uma.** A lista agrupa pendências da mesma regra em uma linha com contagem e uma ação que serve para todas. Prova: com os dados de hoje, a contagem visível cai de 27 para **18 ou menos**, e nenhuma pendência some da conta (o agrupado diz "10 projetos").
- [ ] **Site fora do ar vira pendência alta.** Regra nova: `url_prod` que não responde em 8 s ou devolve 5xx. Prova: teste com servidor de mentira respondendo 200, 503 e recusando conexão — só os dois últimos geram pendência.
- [ ] **Divergência local × servidor aparece.** Regra nova: commits na `main` do GitHub mais novos que o último deploy bem-sucedido. Prova: teste com dados de deploy sintéticos (mesmo sha = sem pendência; sha atrasado = pendência com o número de commits).
- [ ] **Nada quebrou.** `python test_regras.py`, `python test_coletar.py`, `python test_servir.py` e `python test_execucao.py` passam, e a soma de testes é maior que os 203 de hoje.
- [ ] **A CI fica verde** no GitHub, e as suítes novas estão listadas no `.github/workflows/ci.yml` (o arquivo não descobre suíte sozinho).
- [ ] **A documentação anda junto.** `README.md` ganha seção das quatro entregas no mesmo commit, incluindo o que a regra de servidor **não** garante.

## fora_de_escopo

- **Atacar os 203 alertas de segurança abertos** (93 em medconsultoria, 71 em
  odontologia-pericia, 20 em investrix, 19 em workspace-medconsultoria). É o
  trabalho de maior valor que este painel revelou, e é grande demais para entrar
  de carona: merece esteira própria e provavelmente o botão "Resolver".
- **Fase 4 da spec original** (o `radar.py` do `~/.claude` passar a ler este
  banco). É trabalho da janela `~/.claude`, não desta — Regra zero.
- **Redesenho visual do painel.** A tela atual funciona; mexer no visual inteiro
  gasta a sessão sem responder melhor a pergunta do dono.
- **Medir a versão publicada lendo o próprio site** (procurar sha numa meta tag).
  Nenhum dos 5 sites expõe isso; a comparação honesta é pelo deploy do Actions.
- **Notificação fora da tela** (som, balão do Windows, e-mail). Nada disso foi
  pedido e cada um vira uma fonte nova de ruído.

## riscos

- **A regra 6 faz requisição para os sites de produção do dono.** É `GET` sem
  credencial, sem cookie, sem seguir redirecionamento para outro domínio, com
  8 s de teto e no máximo uma vez a cada 20 minutos (camada `github`). Não é
  deploy, não escreve nada e não manda dado nenhum para fora — mas **é a primeira
  vez que este painel toca em produção**, e por isso está declarado aqui e vira
  portão de risco antes de mesclar.
- **`url_prod` vem do `casos.json`, escrito à mão pelo dono.** Se algum dia esse
  arquivo passar a vir de fora, a URL vira entrada hostil e precisa de validação
  de esquema (`https://` e domínio dele). Já entra com essa validação, mesmo hoje
  sendo desnecessária — a lição do título de PR de estranho custou caro demais
  para ser aprendida duas vezes.
- Migration: `historico` já existe com o esquema certo; nada é apagado nem
  reescrito. `hub.db` é descartável por definição.
- Dado de paciente, pagamento e config de deploy: **nenhum**. Esta entrega lê o
  status de deploy, não o dispara.

## plano_de_voo

**Modo enxuto.** O domínio acabou de ser medido nesta sessão (17 projetos, 27
pendências, esquema do banco, formato da API), então a fase 2 não precisa de
quatro lentes cegas redescobrindo o repositório.

| Fase | Roda? | Quem | Modelo | Despachos |
|---|---|---|---|---|
| 1 Interrogador | sim | coordenador | opus | 0 |
| 2 Descoberta | **enxuta** | coordenador, com o medido acima | opus | 0 |
| 3 Design | **não** | — | — | 0 |
| 4 Plano | sim | coordenador | opus | 0 |
| 5 Execução | sim | coordenador, em ramo próprio | opus | 0 |
| 6 Revisão | **sim, obrigatória** | `python-reviewer`, `security-reviewer`, `design-reviewer` | conforme o agente | **3** |
| 7 Cronista | sim | coordenador | opus | 0 |

**Total previsto: 3 despachos**, todos na fase 6.

A fase 3 não roda porque não há direção visual nova a escolher: as quatro
entregas usam os componentes que já existem na tela. A fase 6 é inegociável —
é regra do `CLAUDE.md` (§6, revisor por extensão de arquivo tocado), e na entrega
anterior foram exatamente esses revisores que acharam dois bloqueantes que 197
testes verdes não tinham pegado.
