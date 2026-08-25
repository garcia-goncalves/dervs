# Spec — o HUB fecha o dia

> Fase 2 (modo enxuto) da esteira `hub-fecha-o-dia`, sobre o `briefing.md`
> aprovado. Escrita em 25/08/2026 com o painel rodando e o banco aberto.

## problema

O painel responde "o que precisa de mim agora?" — e responde bem. Mas ele tem
**amnésia**, e a amnésia produz três dores concretas, todas medidas hoje:

1. **Não sabe distinguir o urgente do apodrecido.** Das 27 pendências abertas,
   nenhuma diz há quanto tempo está ali. Uma pendência que nasceu há uma hora e
   outra que está aberta há 23 dias aparecem exatamente iguais. O grafo do
   `camargo-e-soares` está velho **há 23 dias** e ocupa a mesma linha, do mesmo
   tamanho, que o arquivo que o dono deixou sem commit hoje de manhã.
2. **Não devolve nenhum sinal de progresso.** A tabela `historico` do banco tem
   **uma linha**, gravada ontem às 18:02. O painel nunca conseguiu dizer "você
   fechou seis coisas esta semana" nem "isto está piorando". Lista que só cresce
   e nunca reconhece o que foi feito é lista que se aprende a fechar.
3. **A lista treina o dono a ignorá-la.** Dez das 27 pendências (**37%**) são a
   mesma regra — grafo de código velho — em dez projetos diferentes, cada uma com
   a mesma ação manual de copiar um comando. Isso é exatamente o mecanismo
   descrito no próprio `README.md` para justificar o filtro da regra 2: a caixa
   que nasce com muitos alarmes iguais ensina a ignorar a caixa inteira.

E há uma quarta dor, que não é de amnésia e sim de cegueira: **o painel não sabe
se os sites do dono estão no ar.** Cinco projetos têm endereço de produção no
`casos.json` — incluindo `Ajudei-Saude`, marcado `criticidade: critica`, e
`medconsultoria`. O HUB mede git, Docker, CI, alertas, cota e grafo, e não mede
a única coisa que o usuário final percebe. Um site fora do ar hoje não produz
pendência nenhuma nesta tela.

## solucao

Quatro entregas, cada uma independente e commitável sozinha.

### 1. O painel ganha memória do tempo

Tabela nova `pendencia_vida` (`id`, `visto_em`, `ultimo_em`, `fechada_em`).
A cada coleta **local** bem-sucedida — de 60 em 60 segundos, no processo do
servidor e **não** no navegador — as regras são avaliadas e a vida de cada
pendência é atualizada: quem apareceu ganha `visto_em`; quem continua ali tem o
`ultimo_em` renovado; quem sumiu ganha `fechada_em`. No mesmo instante, um
retrato numérico vai para a tabela `historico` já existente (`abertas_alta`,
`abertas_media`, `abertas_baixa`, `abertas_total`).

**Por que no laço de coleta e não no `/api/dados`:** `regras.avaliar()` roda hoje
a cada requisição da tela (`servir.py:638`), ou seja, de 15 em 15 segundos por
aba aberta. Gravar ali faria o navegador dirigir o banco — e, pior, com o painel
fechado o dia inteiro o histórico ficaria vazio justamente no dia em que ele não
olhou. O laço de coleta é o único relógio honesto que este processo tem.

Com isso, toda pendência passa a sair do `/api/dados` com `visto_em`, `dias` e
`nova` (menos de 24 h), e a tela ganha um selo para as novas e a idade para as
velhas.

### 2. O briefing matinal

Uma frase no topo da tela, escrita por função pura a partir dos números:
quantas altas existem, quantas nasceram desde ontem, quantas o dono fechou nos
últimos 7 dias, e **qual dói mais** (a de maior gravidade e maior idade).

A regra que a torna útil em vez de decorativa: **ela nunca diz "tudo certo"
quando existe pendência alta**, e nunca é genérica — sempre cita número e nome
de projeto. Três estados de dado produzem três textos diferentes, e isso é
provado por teste.

### 3. O fim do ruído: pendências iguais viram uma linha

O `/api/dados` passa a mandar, **ao lado** da lista achatada de sempre, uma
lista `grupos`: pendências da mesma regra com três ou mais ocorrências viram uma
entrada única com contagem, a idade da mais velha, e a lista dos projetos dentro.

**Ao lado, não no lugar** — este é o ponto de projeto que evita quebrar duas
coisas que já funcionam: o botão "Resolver" recalcula a pendência pelo `id` no
servidor (`servir.py:156`, e é isso que mantém o prompt fechado), e o "×" de
esconder por 24 h também é por `id`. Trocar o formato de `pendencias` quebraria
as duas. O agrupamento é uma **visão**; o contrato de identidade não muda.

Com os dados de hoje: 27 linhas viram 18 (os 10 "grafo velho" viram 1, os 4
"vulnerabilidade" viram 1 — as duas únicas regras com 3+ ocorrências), sem que
nenhuma pendência saia da conta.

### 4. O site está no ar? E o que está lá é o que você escreveu?

Duas regras novas, só para os projetos que declaram `url_prod` no `casos.json`:

- **Regra 15 — `site_fora`, gravidade alta.** O endereço de produção não
  respondeu em 8 s, ou devolveu 5xx. `GET` sem credencial, sem cookie, sem seguir
  redirecionamento para outro domínio, na cadência de 20 minutos da camada
  `github`. Ação: abrir o endereço.
- **Regra 16 — `nao_publicado`, gravidade média.** Existem commits na branch
  padrão do GitHub mais novos que o último deploy bem-sucedido. Ação: abrir a
  aba de Actions do repositório. Só dispara quando o repositório tem um workflow
  de deploy identificável; sem isso o painel **fica calado**, que é o invariante
  2 do motor ("ausência não é falha").

**O que a regra 15 NÃO garante, e vai escrito no README:** responder 200 na raiz
não é o mesmo que estar funcionando. Banco caído atrás de uma home estática
continua devolvendo 200. Isto detecta o apagão, não a doença.

## o_que_ja_existe

Caminhos reais, conferidos nesta sessão:

- `banco.py` — `anotar_historico(chave, valor)` (linha 137) **já existe e está
  praticamente sem uso**: 1 linha no banco. A tabela `historico` já tem o
  esquema certo (`medido_em`, `chave`, `valor`) e índice por `(chave, medido_em)`.
  A entrega 1 não cria esquema novo aqui — passa a usar o que está pronto.
- `banco.py` — `pendencia_estado` (id, silenciada_ate, anotado_em) prova que o
  padrão "estado de pendência sobrevive à recoleta" já está estabelecido. A
  `pendencia_vida` segue o mesmo desenho, em tabela separada para não migrar a
  existente.
- `regras.py:40` — `_p(regra, gravidade, projeto, texto, acao, detalhe)` monta a
  pendência com `id = "regra:projeto"`. As regras 15 e 16 entram por aqui, sem
  formato novo.
- `regras.py:223` — `avaliar(projetos, quota, silenciadas)` é **pura**: entra
  lista de dicionários, sai lista. É o que torna as regras novas testáveis sem
  rede. `test_regras.py` tem 30 testes nesse padrão.
- `regras.py:33-37` — os limiares (`DIAS_SUJO`, `DIAS_PR`, `DIAS_GRAFO`,
  `DIAS_ABANDONO`, `PCT_COTA`) já vivem no topo, nomeados. Os novos entram junto.
- `coletar_github.py` — a consulta GraphQL em lote (`PEDACO`, `_consulta`) e o
  `traduz(no, com_vulns)`. É onde a medição do site e do deploy encaixa: mesma
  cadência de 20 min, mesmo lugar onde a rede já é tolerada.
- `coletar_github.py:135` — o padrão de **não apagar dado bom com falha de rede**
  (o bloco `if not com_vulns`) é o precedente a copiar para o estado do site: um
  blip de rede não pode fazer "site no ar" virar "site fora".
- `coletar.py:47` — `RAIZ`, e `casos.json` é a fonte de `url_prod` e
  `criticidade`. Nenhum coletor escreve nesse arquivo.
- `servir.py:117` — `coletar(camada, motivo)`, serializado por camada com trava,
  é o gancho da entrega 1: o registro da vida entra depois do `returncode == 0`
  da camada `local`.
- `servir.py:634` — `_estado()` é onde `pendencias` é montada; `grupos`,
  `tendencia` e `briefing` entram no mesmo dicionário.
- `index.html` — a tela, 60 KB, sem build. Recarrega a cada 15 s.
- Suítes: `test_regras.py` (30), `test_coletar.py`, `test_servir.py` (43),
  `test_execucao.py` (72) — **203 no total**. `.github/workflows/ci.yml` nomeia
  cada suíte num passo próprio e **não descobre suíte nova sozinho**.

## fontes_externas

nenhuma. Toda a análise saiu do repositório e do painel rodando nesta máquina;
as APIs usadas (`gh api graphql`, `gh run list`) já estão em uso no projeto.

## fora_de_escopo

O corte, já decidido:

- **Os 203 alertas de segurança abertos** (93 medconsultoria, 71
  odontologia-pericia, 20 investrix, 19 workspace-medconsultoria). É o achado de
  maior valor desta análise e está fora **de propósito**: entra em esteira
  própria, provavelmente com o botão "Resolver". Entrar de carona aqui
  transformaria uma entrega provável em duas improváveis.
- **Fase 4 da spec original** (`radar.py` lendo este banco) — janela `~/.claude`.
- **Redesenho visual.**
- **Ler a versão publicada do próprio site** (sha em meta tag): nenhum dos cinco
  expõe isso.
- **Notificação fora da tela.**
- **Reindexar o grafo sozinho.** Seria a cura do ruído em vez do curativo, mas
  indexação é cara, demorada e já travou esta máquina duas vezes (23 e 24/08).
  Agrupar é o passo seguro; automatizar fica para depois de medir o custo.

## contradicoes_resolvidas

- **Agrupar vs. manter a lista achatada.** Agrupar melhora a leitura e piora
  duas coisas que já funcionam (o `id` que o "Resolver" recalcula e o "×" de 24
  horas). **Venceu:** mandar as duas listas, `pendencias` achatada como contrato
  estável e `grupos` como visão. Custa alguns bytes no JSON e não custa nenhum
  risco.
- **Gravar a vida no `/api/dados` vs. no laço de coleta.** O `/api/dados` é o
  lugar onde `avaliar()` já roda, e seria menos código. **Venceu o laço de
  coleta:** o `/api/dados` é dirigido pelo navegador, e com a aba fechada o
  histórico do dia não existiria. Um painel que só lembra do que aconteceu
  enquanto estava sendo olhado não tem memória — tem espelho.
- **Regra 15 na camada `local` vs. `github`.** Local é de 60 em 60 s e daria
  detecção mais rápida. **Venceu `github` (20 min):** bater de minuto em minuto
  em cinco sites de produção o dia inteiro é 7.200 requisições por dia contra
  servidor que é dele mas que ele paga. Vinte minutos é o intervalo em que o
  próprio projeto já decidiu que a rede é aceitável.
- **`site_fora` alta vs. crítica.** Não existe gravidade "crítica" no motor
  (`ORDEM` só tem alta/media/baixa, `regras.py:30`). **Venceu usar `alta`** e
  deixar a ordenação interna resolver, em vez de inventar um nível novo e ter de
  reordenar a tela inteira.

## duvidas_para_o_dono

Uma só, e é a de risco (portão 4 da esteira):

1. **A regra 15 pode bater nos seus cinco endereços de produção?** É um `GET` de
   leitura, sem senha, sem cookie, uma vez a cada 20 minutos — o mesmo que abrir
   o site no navegador, três vezes por hora. Não publica nada, não altera nada.
   **Recomendação: sim.** É a única pendência desta lista que o seu cliente
   percebe antes de você. A regra já entra escrita e testada, com um interruptor
   `MEDIR_SITE` no topo do coletor: se a resposta for não, ele fica desligado e
   nada mais muda.
