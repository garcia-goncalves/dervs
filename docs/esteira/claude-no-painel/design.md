# Design — o painel de execução do botão "Resolver"

> Fase 3 da esteira (design), a partir da spec aprovada em
> `docs/esteira/claude-no-painel/spec.md` e do briefing em
> `docs/esteira/claude-no-painel/briefing.md`. Papéis fundidos: Diretor de
> arte + Redator de interface + Estrategista, num despacho só — escopo
> pequeno, sistema visual já existente.

## direcao_visual_escolhida

**A direção é obedecer o sistema que já existe em `index.html`.** Não há
paleta nova, não há fonte nova, não há componente visual de tipo novo. O
painel de execução nasce como um `<dialog>` no mesmo molde da paleta Ctrl+K
(`#paleta`, `index.html:718-812`): `showModal()`, foco preso nativamente,
`Esc` fecha nativamente, fallback de "clique fora fecha" para navegador sem
`closedBy`, `margin:12vh auto auto` para abrir onde o olho já está. Reusar
esse padrão em vez de inventar um segundo tipo de modal é a decisão de maior
alavancagem deste documento: zero CSS novo de estrutura de diálogo, zero
comportamento de teclado novo para testar.

Três direções foram consideradas e recusadas, com o motivo:

- **Paleta própria para a área de execução** (ex.: um verde/azul "de
  produto" diferente do `--acento` atual, para dar "identidade" ao recurso
  novo). Recusada porque o painel já resolveu identidade visual — cor nova
  numa tela nova ensina o dono a ler duas linguagens visuais no mesmo
  produto, e o briefing não pediu rebranding, pediu um botão que funciona.
- **Visual de terminal preto** (fundo `#000`, texto verde/âmbar tipo
  console retrô), cotado por parecer "mais Claude Code". Recusada por dois
  motivos: quebra o `color-scheme:light dark` que o resto do painel já
  respeita (o dono usa tema claro de dia), e o usuário-dono não é
  desenvolvedor — um terminal preto comunica "isto é para o sócio", exatamente
  o erro que o briefing avisa para não cometer (`usuario_alvo`, duas pessoas
  opostas, nenhuma pode atravessar a experiência da outra).
- **Cores de marca do Claude** (laranja característico da Anthropic).
  Recusada porque o painel não é material de marketing do Claude — é a
  ferramenta interna do dono, e importar a cor de um produto de terceiro
  dentro do próprio sistema de tokens quebraria justamente a promessa da
  seção `--acento` já existente: um azul só, para toda ação primária do
  painel, projeto ou execução.

A régua de aceite: qualquer pessoa que já usa o HUB hoje (a caixa de
pendências, a paleta, a tabela) tem de reconhecer o painel de execução como
"a mesma casa", não como uma tela emprestada de outro produto.

## tokens

Nenhum token novo. Todos os usados abaixo já existem em `index.html:26-40`
(claro e escuro):

| Token | Uso no painel de execução |
|---|---|
| `--painel` | fundo do `<dialog>` e das faixas internas |
| `--bg` | fundo do log cru (reaproveita o papel de "camada abaixo" que já tem em `.caixa.dentro`) |
| `--borda` | bordas do diálogo, divisórias entre cabeçalho/corpo/rodapé, borda do log |
| `--texto` | todo o texto de leitura corrida: título, linha de status, mensagens, resumo, diff |
| `--fraco` | rótulos secundários: "estimativa", nome do projeto no cabeçalho, timestamp de cada linha do log |
| `--fraquinho` | texto terciário: contador de linhas do log, placeholder |
| `--acento` | botão "Resolver" (herda de `button.agir`), aba ativa "resumo"/"diff" (herda de `nav.abas button[aria-selected]`), foco visível |
| `--ok` | **só como indicador não-textual** (ponto de status, borda esquerda do cabeçalho) no estado `ok` — nunca como cor de texto corrido, ver ressalva abaixo |
| `--alerta` | **só como indicador não-textual** no estado `parada_pelo_dono` |
| `--erro` | cor de texto **permitida** na mensagem de falha (ver ressalva) e indicador não-textual nos demais lugares |
| `--grade` | fundo do log cru e dos blocos de "diff" (mesmo papel que já tem em `.chip` e em `tr.conta>td`: "isto é dado bruto/código") |
| `--sombra` | sombra do `<dialog>`, herdada do padrão de `#paleta` |
| `--mono` | log cru, diff, custo em reais, nome de arquivo no resumo |
| `--sans` | todo o resto |

**Ressalva de contraste — um token existente não alcança em uso de texto
corrido, e a solução é de uso, não de valor.** Medi as combinações contra
`--painel` no tema claro (fórmula WCAG, fundo `#fff`):

| Combinação (tema claro, sobre `--painel`) | Contraste | Passa 4,5:1? |
|---|---|---|
| `--texto` | 18,3:1 | sim |
| `--fraco` | 5,8:1 | sim |
| `--erro` | 5,2:1 | sim |
| `--acento` | 4,44:1 | **não** (por 0,06) |
| `--ok` | 4,37:1 | **não** |
| `--alerta` | 3,85:1 | **não** |
| `--fraquinho` | 3,09:1 | não (mas nunca carrega texto essencial hoje) |

`--erro` passa como texto nos dois temas e por isso a mensagem de falha pode
usar `--erro` diretamente na palavra "Falhou". `--acento`, `--ok` e
`--alerta` **não** viram cor de texto em nenhum lugar novo deste painel —
viram cor de **indicador não textual**: o ponto (`●`) antes da linha de
status e a borda esquerda do cabeçalho do diálogo (mesmo papel que
`.item.alta{border-left-color:var(--erro)}` já cumpre na caixa). Um
indicador decorativo pareado com uma palavra em `--texto` só precisa de
3:1 (WCAG 1.4.11, "componente de interface"), e todos os três passam nisso
com folga (4,44 / 4,37 / 3,85, todos acima de 3). A palavra que importa —
"rodando", "concluído", "parado por você" — está sempre em `--texto`, cor
que nunca falha. Isto não é ajuste de valor de token; é a regra de uso que
falta no sistema hoje e que este documento propõe: **cor de estado é
indicador, nunca é o único portador da palavra**.

### Correções do juiz (24/08/2026)

Duas, aplicadas neste documento e obrigatórias na fase de execução.

**1. O link do pedido de alteração contradizia a própria regra acima.**
O documento afirma que `--acento` "nunca vira cor de texto em nenhum lugar
novo deste painel", mas o link do PR no estado `ok` usa exatamente
`--acento` como texto, herdando o `a{color:var(--acento)}` global — e esse
é o elemento mais importante da entrega inteira, o único que o dono
precisa clicar. A 4,44:1, ele falha 4,5:1 por 0,06.

*Decidido:* o link do PR **não depende de cor para ser reconhecível como
link**. Ganha `font-weight:600` e `text-decoration:underline` permanente
(não só no hover), mais o `↗`. A cor continua `--acento`, herdada.

*Dívida registrada, não paga nesta entrega:* `--acento` a 4,44:1 no tema
claro afeta **todo link do painel**, não só este — corrigir exige retunar o
acento do sistema inteiro e revalidar cada tela existente. Isso é mexer no
vizinho, fora do escopo desta entrega. Fica escrito aqui para não se
perder, e é candidato natural à primeira faxina visual do painel.

**2. `.aviso` com borda `--erro` para um recado neutro é remendo.**
Reaproveitar a classe de erro e compensar com um ícone `ℹ` e com escolha de
palavras resolve para quem lê, não para quem só bate o olho — e o aviso do
`painel-projetos` não é erro nenhum, é informação.

*Decidido:* nasce uma variante `.aviso.neutro` que troca só a cor da borda
para `--acento`, mantendo todo o resto da classe. Duas linhas de CSS,
nenhum token novo, e a classe original fica intocada para quem já a usa.

## telas

Todas as seis vivem dentro do mesmo `<dialog id="execucao">`, aberto por
`showModal()`. A moldura (cabeçalho com nome do projeto + botão fechar,
rodapé com custo) é fixa; muda o miolo. Largura: `min(640px,92vw)` — um
tico mais larga que a paleta (620px) porque o log e o diff precisam de
respiro; em 360px isso dá 331px de diálogo.

### `parada` (o painel ainda não abriu, ou abriu para um projeto que nunca rodou)

Não é uma tela do diálogo — é o estado do botão na caixa de pendências
antes do primeiro clique. Fica registrada aqui porque é o ponto de partida
de toda a jornada.

```
┌──────────────────────────────────────────────────────────┐
│ A verificação automática do GitHub falhou em              │
│ medconsultoria-crm.                                        │
│ medconsultoria-crm · 12 min                                │
│                                        [ Resolver ] [ × ]  │
└──────────────────────────────────────────────────────────┘
```

`button.agir` de sempre, rótulo "Resolver" — mesma classe, mesmo lugar do
botão que hoje existe para outras ações. Nenhuma mudança de layout na
caixa.

### `rodando`

```
┌─ Resolvendo: medconsultoria-crm ──────────────────── [×] ─┐
│ ● Rodando os testes                          [ Parar ]    │
│                                                             │
│ ≈ R$ 1,20 · estimativa, ainda rodando                      │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ 14:02:03  clonando medconsultoria-crm em cópia        │▲ │
│ │           isolada                                     │  │
│ │ 14:02:07  lendo o repositório                          │  │
│ │ 14:02:19  rodando os testes                            │  │
│ │ 14:02:19  FAIL testes/test_agendamento.py::            │  │
│ │           test_horario_duplo — AssertionError          │▼ │
│ └─────────────────────────────────────────────────────┘   │
│ (log continua crescendo; rolagem própria, não fecha)       │
└─────────────────────────────────────────────────────────┘
```

- Linha de status em destaque: ponto `●` em `--acento` (indicador, não
  texto) + frase em `--texto`, peso 600, tamanho maior que o resto
  (`font-size:15px` contra os `13px` do corpo). Região `aria-live="polite"`,
  então cada troca é anunciada sozinha pelo leitor de tela.
- Botão **"Parar"** (`button.calar` visualmente, borda `--erro` para
  diferenciar de um cancelamento neutro) sempre visível nesta tela, ao lado
  da linha de status.
- Custo: `--mono`, cor `--fraco`, atualiza a cada consulta de 1s junto do
  log; a palavra "estimativa" nunca some da tela.
- Log: `<pre>` dentro de contêiner com `overflow-y:auto; max-height:38vh`
  e **rolagem própria** — o diálogo inteiro não cresce sem limite. Fundo
  `--grade`, texto `--mono` 12px, sem `word-break` forçado nas linhas
  longas de stack trace (uso `overflow-x:auto` só dentro do log, igual ao
  padrão já usado em `.rolagem` para a tabela).
- **Os outros botões do painel continuam clicáveis** durante este estado —
  é a mudança de arquitetura da contradição 2 da spec (trava foi para o
  servidor). O `<dialog>` cobre a tela com o backdrop nativo, mas fechar o
  diálogo (Esc) não para a execução; ela continua rodando no servidor e o
  botão "Resolver" daquele projeto na caixa vira, enquanto isso, um botão
  "Ver execução" para reabrir o mesmo diálogo.

**Em 360px:** o cabeçalho quebra em duas linhas (nome do projeto embaixo do
botão fechar); a linha de status e o botão "Parar" empilham verticalmente
(`flex-wrap:wrap`, "Parar" vira largura 100%); o log mantém
`max-height:38vh` e ganha `overflow-x:auto` próprio para as linhas de stack
trace, para a página nunca rolar na horizontal.

### `ok`

```
┌─ Resolvendo: medconsultoria-crm ──────────────────── [×] ─┐
│ ✓ Pedido de alteração aberto                               │
│                                                             │
│ R$ 1,84 · estimativa                                        │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ (log completo, mesmo painel de antes, agora parado)   │▲ │
│ └─────────────────────────────────────────────────────┘   │
│ [ Resumo ] [ Diff ]                                        │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ testes/test_agendamento.py — corrigida a checagem de  │   │
│ │ horário duplo, que comparava string em vez de data.   │   │
│ └─────────────────────────────────────────────────────┘   │
│ Ver o pedido de alteração: github.com/.../pull/312 ↗       │
└─────────────────────────────────────────────────────────┘
```

- Ponto vira `✓` em `--ok` (ainda indicador, não é a palavra — a palavra
  "Pedido de alteração aberto" está em `--texto`).
- Log continua ali, colapsável só por rolagem, nunca por timeout — é o
  log que hoje some em 9 segundos (`index.html:306`) e que esta entrega
  corrige.
- Abaixo do log: duas abas, mesmo padrão visual de `nav.abas` já existente
  (`border-bottom:2px solid var(--acento)` na ativa) — "Resumo" (padrão) e
  "Diff". Trocar não refaz requisição nenhuma: os dois textos já chegaram
  no evento final.
- Link do PR: `<a>` com `--acento` (herdado, `a{color:var(--acento)}` já
  definido globalmente), `target="_blank" rel="noopener"`, símbolo `↗` de
  abre-em-nova-aba.
- **Se o projeto resolvido é `painel-projetos`**, uma faixa de aviso
  aparece entre a linha de status e o custo, usando a mesma classe
  `.aviso` que já existe (`index.html:190`), na variante **`.aviso.neutro`**
  criada pela correção 1 do juiz: mesma caixa, borda em `--acento` em vez de
  `--erro`, porque este recado é informação e não erro.

**Em 360px:** as abas "Resumo"/"Diff" ficam lado a lado (cabem, são só
duas palavras) mas o conteúdo abaixo delas — principalmente o "Diff" —
ganha `overflow-x:auto` num contêiner próprio; o link do PR quebra linha
livremente (`word-break:break-word`) em vez de estourar a largura do
diálogo.

### `falha`

```
┌─ Resolvendo: zacareli ────────────────────────────── [×] ─┐
│ ✕ Falhou: atingiu o teto de gasto                          │
│                                                             │
│ R$ 5,00 · estimativa, execução interrompida pelo teto       │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ (log completo até o ponto da falha, com o motivo)     │▲ │
│ └─────────────────────────────────────────────────────┘   │
│ Parou porque atingiu o teto de R$ 5,00 por execução, sem   │
│ terminar a correção. A cópia isolada continua em disco     │
│ para inspeção; nada foi enviado ao GitHub.                  │
└─────────────────────────────────────────────────────────┘
```

- `✕` em `--erro` como indicador; a **palavra** "Falhou" pode ficar em
  `--erro` também, porque este é o único dos três tokens de estado que
  passa 4,5:1 como texto nos dois temas (ver `tokens`).
  "Falhou: atingiu o teto de gasto" é a manchete curta; o parágrafo abaixo
  do log é o motivo real por extenso — nunca "algo deu errado".
- Sem abas resumo/diff aqui — não há "o que foi feito" para resumir. O log
  cru é a única fonte, e por isso ele fica **sempre visível nesta tela**,
  não atrás de um clique.
- Sem botão "Tentar de novo": não pedido no briefing, e cada tentativa
  nova é um clique em "Resolver" de novo — não inventar funcionalidade
  fora do que os 12 critérios pedem.

**Em 360px:** igual a `ok`, sem as abas.

### `parada_pelo_dono`

```
┌─ Resolvendo: dents ───────────────────────────────── [×] ─┐
│ ⏸ Parada por você                                          │
│                                                             │
│ R$ 0,63 · estimativa até o momento em que parou             │
│ ┌─────────────────────────────────────────────────────┐   │
│ │ (log até a última linha antes do Parar)               │▲ │
│ └─────────────────────────────────────────────────────┘   │
│ Você clicou em "Parar". Nada foi salvo e nenhum pedido de  │
│ alteração foi aberto. A cópia isolada foi descartada.       │
└─────────────────────────────────────────────────────────┘
```

- `⏸` em `--alerta` como indicador (nunca como cor de texto, mesma
  ressalva de `tokens`).
- Diferença central para `falha`: o tom não é de problema, é de confirmação
  — "você pediu, e funcionou". Sem `--erro` em lugar nenhum desta tela.
- Caso especial dito no texto: se o "Parar" não conseguiu matar o processo
  em 5 segundos (`taskkill` não respondeu), a linha de status muda para
  "Não consegui confirmar que parou" (ver `textos`) — o painel nunca
  finge sucesso que não verificou, regra dura da spec (peça 5).

### `recusada_por_ja_haver_outra_execucao`

Esta tela aparece quando o dono clica "Resolver" numa pendência **B**
enquanto a execução da pendência **A** ainda está `rodando` em outro
projeto — a trava é global na máquina inteira (spec, contradição 2). O
diálogo abre normalmente (mesmo `showModal()`), mas nasce direto neste
estado, sem log próprio nenhum, porque nada rodou para este projeto:

```
┌─ Resolver: zacareli ──────────────────────────────── [×] ─┐
│ ⊘ Já há uma execução em andamento                          │
│                                                             │
│ Só é possível rodar uma correção por vez nesta máquina.    │
│ Agora mesmo o Claude está trabalhando em                   │
│ medconsultoria-crm.                                         │
│                                                             │
│              [ Ver essa execução ]  [ Fechar ]              │
└─────────────────────────────────────────────────────────┘
```

- `⊘` em `--fraquinho` como indicador (é um estado neutro de "não agora",
  não é erro nem sucesso — não empresta cor de nenhum dos três outros
  estados).
- Botão **"Ver essa execução"** troca o conteúdo do mesmo diálogo para o
  estado `rodando` do projeto que está de fato executando (o servidor já
  sabe qual é — é o mesmo recurso de execução único que o painel consulta
  para o próprio andamento). Isto transforma um bloqueio em navegação:
  ninguém fica batendo num "não pode" sem saída.
- Se o dono clicar "Resolver" na **mesma** pendência que já está rodando
  (reabrindo depois de fechar com Esc, por exemplo), não é esta tela — é
  `rodando` direto, reconectado ao estado do servidor.

**Em 360px:** os dois botões empilham, "Ver essa execução" primeiro
(é a ação recomendada, vem antes na ordem de tabulação).

## textos

Tudo literal, pronto para copiar para o HTML/JS.

**Botão na caixa de pendências**
- Rótulo do botão: `Resolver`
- Rótulo quando desabilitado por já ter aquele projeto rodando: mesmo
  rótulo, o clique é quem decide o estado (não desabilitar botão nenhum —
  contradição 2 da spec).

**Cabeçalho do diálogo**
- Título com projeto rodando: `Resolvendo: {{projeto}}`
- Título antes de rodar (estado recusado): `Resolver: {{projeto}}`
- Botão fechar: `×`, com `aria-label="Fechar o painel de execução"`

**Linha de status — sequência real da CI vermelha, na ordem em que aparece**
1. `Preparando uma cópia isolada de {{projeto}}`
2. `Lendo o repositório`
3. `Rodando os testes`
4. `Escrevendo a correção`
5. `Rodando os testes de novo`
6. `Abrindo o pedido de alteração`
7. `Pedido de alteração aberto` (estado final `ok`)

**Estado `falha` — manchetes por causa real (nunca "algo deu errado")**
- Teto de gasto: `Falhou: atingiu o teto de gasto`
  — corpo: `Parou porque atingiu o teto de R$ 5,00 por execução, sem
  terminar a correção. A cópia isolada continua em disco para inspeção;
  nada foi enviado ao GitHub.`
- PR já existe para o branch: `Falhou: já existe um pedido de alteração
  aberto`
  — corpo: `O GitHub recusou abrir outro pedido de alteração porque já
  existe um aberto para esta correção: pull/128. Feche ou atualize aquele
  antes de tentar de novo.`
- Testes continuam vermelhos depois da tentativa: `Falhou: os testes
  continuam falhando`
  — corpo: `A sessão tentou corrigir e rodou os testes de novo, mas
  testes/test_agendamento.py::test_horario_duplo continua falhando. Veja o
  log abaixo para o erro exato.`
- Limite de turnos atingido: `Falhou: não terminou a tempo`
  — corpo: `A sessão chegou ao limite de tentativas sem terminar a
  correção. Isto costuma acontecer quando o problema é maior do que uma CI
  vermelha simples — vale olhar manualmente desta vez.`

**Estado `parada_pelo_dono`**
- Manchete: `Parada por você`
- Corpo: `Você clicou em "Parar". Nada foi salvo e nenhum pedido de
  alteração foi aberto. A cópia isolada foi descartada.`
- Se o processo não confirmou a morte em 5 segundos: manchete
  `Não consegui confirmar que parou` — corpo: `Pedi para parar, mas o
  processo não respondeu em 5 segundos. Ele pode ainda estar rodando —
  confira antes de tentar de novo.`

**Estado `recusada_por_ja_haver_outra_execucao`**
- Manchete: `Já há uma execução em andamento`
- Corpo: `Só é possível rodar uma correção por vez nesta máquina. Agora
  mesmo o Claude está trabalhando em {{projeto_em_andamento}}.`
- Botão: `Ver essa execução`
- Botão secundário: `Fechar`

**Botão "Parar" e confirmação**
- Rótulo: `Parar`
- Enquanto processa o pedido: `Parando…`

**Custo**
- Ao vivo: `≈ R$ {{valor}} · estimativa, ainda rodando`
- Final: `R$ {{valor}} · estimativa`
- Nota fixa, sempre visível perto do valor: `Estimativa calculada pelo
  próprio Claude Code, não é a fatura.`

**Abas do resultado**
- `Resumo` (padrão) / `Diff`
- Estado vazio do resumo (não deveria acontecer, mas se a sessão terminar
  sem tocar arquivo): `A sessão terminou sem alterar nenhum arquivo.`

**Link do pedido de alteração**
- `Ver o pedido de alteração ↗` (texto do link, `href` é a URL real vinda
  de `gh pr create --json url`)

**Resumo — exemplo de demonstração (uma frase por arquivo, geradas pelo
próprio gabarito de prompt, não escritas à mão pelo painel)**
```
testes/test_agendamento.py — corrigida a checagem de horário duplo, que
comparava string em vez de data.
src/agendamento/regras.py — ajustado o cálculo que gerava o horário
duplicado quando o fuso horário cruzava a meia-noite.
```

**Diff — exemplo de demonstração**
```diff
--- a/src/agendamento/regras.py
+++ b/src/agendamento/regras.py
@@ -41,7 +41,7 @@ def horario_ocupado(agenda, inicio, fim):
-    return any(a.inicio == inicio for a in agenda)
+    return any(a.inicio.astimezone(UTC) == inicio.astimezone(UTC)
+               for a in agenda)
```

**Log cru — linhas de demonstração, com carimbo de hora, formato real**
```
14:02:03  preparando uma cópia isolada de medconsultoria-crm em
          ~/.cache/hub-worktrees/medconsultoria-crm/a1b2c3d4
14:02:07  lendo o repositório
14:02:19  rodando os testes
14:02:19  FAIL testes/test_agendamento.py::test_horario_duplo —
          AssertionError: esperado 1 agendamento, recebido 2
14:02:41  escrevendo a correção
14:03:02  rodando os testes de novo
14:03:04  3 testes passaram, 0 falharam
14:03:05  abrindo o pedido de alteração
14:03:07  pedido de alteração aberto: pull/312
```

**Estado vazio do log (antes da primeira linha chegar)**
- `Iniciando…` (única linha, `--fraquinho`, substituída pela primeira
  linha real assim que chega)

**Aviso do próprio `painel-projetos`** (classe `.aviso.neutro` — borda em
`--acento`, decidida pela correção 2 do juiz; o ícone à frente do texto é
`ℹ`, não `✕`)
- `ℹ Você está resolvendo o próprio painel. A mudança só aparece na tela
  depois que o painel for reiniciado — o servidor que está te mostrando
  esta execução é o mesmo que ela está tentando alterar.`

**`aria-live` — o que o leitor de tela anuncia**
- A região da linha de status tem `aria-live="polite"` `role="status"`
  (mesmo padrão de `#recado`, `index.html:274`): cada uma das 7 frases da
  sequência acima é anunciada sozinha, na hora em que troca.
- O log **não** é `aria-live` — anunciar cada linha de stack trace seria
  ruído; é uma região navegável (`role="log"`, `aria-label="Saída bruta da
  execução"`) que o leitor de tela lê sob demanda.
- O custo **não** é `aria-live` (evita repetir "estimativa" a cada
  segundo); o valor final de custo entra dentro da própria frase da última
  atualização de status, uma vez: `Pedido de alteração aberto. Custo
  estimado: R$ 1,84.`

**Foco e fechamento pelo teclado**
- Ao abrir (`showModal()`), o foco vai para o `<h2>` do cabeçalho
  (`tabindex="-1"`, mesmo truque que dá contexto sem roubar o usuário do
  fluxo de leitura do `aria-live` que vem em seguida) — não para o botão
  "Parar", para não convidar a interromper por engano assim que a tela
  abre.
- `Esc` fecha nativamente (herdado do `<dialog>`, mesmo comportamento de
  `#paleta`); fechar **não** para a execução no servidor — só fecha a
  janela. Reabrir (novo clique em "Resolver" no mesmo projeto, ou Ctrl+K)
  reconecta ao estado atual.
- Ao fechar, o foco volta para o botão "Resolver" que abriu o diálogo (o
  JS guarda uma referência a ele antes de chamar `showModal()`), mesmo
  princípio que falta hoje em `#paleta` e que este painel introduz como
  prática nova a valer para os dois.

## assets

Nenhum asset de imagem. Todo indicador visual é caractere Unicode comum
(`●`, `✓`, `✕`, `⏸`, `⊘`, `ℹ`, `↗`), exatamente como o resto do
`index.html` já faz hoje (`▾`/`▴` no `<summary>` da tabela, `×` no botão de
silenciar, `▲`/`▼` nunca são imagem em lugar nenhum do arquivo). Não é SVG
inline porque nenhum dos seis estados precisa de forma geométrica — são
pontos de status e um link externo, e caractere tem uma vantagem que SVG
não tem aqui: herda `currentColor`/`font-size` de graça, sem `viewBox` para
ajustar em 360px. Origem: glifos padrão da fonte do sistema
(`--sans`/`--mono`, já carregadas), sem licença a declarar porque não são
arquivo — são texto.

## estrategia_de_aquisicao

Não é produto público; "aquisição" aqui é **descoberta dentro da própria
ferramenta que o dono já abre todo dia**, e "retenção" é confiança para
clicar de novo depois da primeira vez.

**Por onde o botão é alcançável.** Dois caminhos, e os dois já existem no
painel — nenhum atalho novo de teclado é criado:
1. **O cartão da pendência**, ao lado da ação atual — é onde o dono já
   olha primeiro (a "caixa no topo" é a arquitetura central do painel,
   comentário em `index.html:8-17`). "Resolver" fica ao lado, não substitui
   "Ver o que falhou": os dois continuam coexistindo, porque o sócio às
   vezes só quer olhar o log do GitHub direto, sem abrir sessão nenhuma.
2. **A paleta Ctrl+K**, reusando o mesmo caminho de ação que
   `agir()` já executa (`index.html:327-328`, e o teste de
   `test_servir.py:263-290` que garante que a paleta nunca inventa comando
   que o servidor não conheça). Digitar "resolver" ou o nome do projeto na
   paleta encontra a mesma ação — é o caminho do sócio, que já usa Ctrl+K
   para tudo e não quer tirar a mão do teclado.

**O que a pessoa vê na primeira vez, sem saber o que é aquilo.** O botão
se chama "Resolver" — verbo, não jargão ("Executar sessão", "Disparar
agente" ficam de fora). No instante em que clica, a primeira coisa que
aparece não é o log: é a linha de status ("Preparando uma cópia isolada de
{{projeto}}"), que já ensina, sem explicar em texto à parte, que nada
está sendo tocado direto — está sendo copiado primeiro. O dono não precisa
saber a palavra "worktree" para entender essa frase.

**O que faz confiar o suficiente para clicar uma segunda vez.** Três
coisas, na ordem em que a spec resolveu como intocáveis (peças 2, 5 e 6 da
solução) e que este design torna visíveis:
- **Nunca termina em "pronto, mudei"** — termina em "abri um pedido de
  alteração", com link clicável para o dono ver por fora do painel, no
  GitHub, que a promessa "nada muda sem eu aprovar" foi cumprida de
  verdade. Isso é o que separa este botão de "IA que mexe sozinha no meu
  código", medo razoável de quem não é dev.
- **O log nunca some.** Da primeira vez que o dono fecha o painel achando
  que perdeu a explicação e reabre para conferir, encontrar o log intacto
  (em vez do aviso de 9 segundos que o painel tem hoje para erro) é o
  momento que converte ceticismo em confiança — é por isso que a spec
  chama isso, com todas as letras, de mudança obrigatória.
- **O custo nunca é surpresa.** Aparecer ao vivo, rotulado "estimativa", e
  crescer devagar durante os primeiros segundos, ensina o dono a olhar
  aquele número antes de fechar a aba — não depois de levar um susto na
  fatura no fim do mês. É o mesmo princípio de "carimbo em todo número"
  que já rege o resto do painel (`index.html:12-13`), aplicado a dinheiro.

Para o sócio, a segunda visita se ganha diferente: o "Diff" cru, sem
enfeite, é a prova de que a ferramenta não está tentando ser "mais
amigável" às custas de esconder o que de fato mudou — ele lê exatamente o
que leria num `git diff` de terminal, dentro do painel que o dono também
usa, o que é o pedido original ("quero desenvolver diretamente dentro do
Painel DEV").
