# Design — Auditoria Profunda

Fase 3 da esteira, escrita em 02/09/2026. Contrato desta fase:
`docs/esteira/auditoria-profunda/spec.md`. Onde este documento e a `spec.md`
divergirem, vale a `spec.md`.

## direcao_visual_escolhida

**Torre de Controle** — a mesma, sem alteração. Está aprovada e travada em
`docs/esteira/dervs/design.md` (26/08/2026, com a correção de densidade de
28/08/2026) e registrada como decisão fechada em
`docs/A-APLICACAO.md` §8 e §12 ("O que não se relitiga"). Esta fase **não
propõe direção nova, não abre painel adversarial e não reexamina paleta,
tipografia ou raio** — o pedido desta esteira é uma tela a mais dentro de um
sistema que já existe, não um produto novo. Reabrir a escolha custaria três
diretores de arte outra vez para reafirmar o que já foi decidido, e é
precisamente o tipo de cerimônia que o `CLAUDE.md` deste repositório pede para
evitar.

A regra dura que atravessa tudo continua valendo sem exceção: **o verde é o
estado saudável, nunca cor de marca ou de destaque.** A tela de Auditoria
herda isso sem ajuste — ela não introduz nenhum uso de cor que a Torre de
Controle não já preveja, porque o vocabulário de gravidade de achado é
resolvido reaproveitando o vocabulário de estado que o selo já tem (ver
`## tokens`).

## tokens

A tela usa só tokens que já existem em `assets/dervs.css`. Nenhum é criado.

**Cor:** `--fundo`, `--fundo-elevado` (linha de achado, cartão do carimbo),
`--texto`, `--texto-suave` (metadado, carimbo), `--borda` (traço entre linhas
de achado — decorativo), `--borda-forte` (contorno de cartão, do seletor de
projeto e do selo — carrega significado), `--acao`/`--acao-texto` (botão
"Auditar agora", link "Abrir o arquivo", foco de teclado — nunca um
`--estado-*`).

**Gravidade do achado — não é token novo, é reuso do vocabulário do selo.** A
spec fecha três gravidades (`alta`, `media`, `baixa`) e cinco categorias
(`seguranca`, `bug`, `teste`, `doc`, `estilo`). Nenhuma delas ganha cor
própria: a tabela de gravidade usa exatamente os quatro tokens de estado que
o selo já define, porque o significado é o mesmo — "isto quer minha atenção
com que urgência":

| Gravidade do achado | Token reusado |
|---|---|
| alta | `--estado-quebrado` / `--estado-quebrado-fraco` |
| media | `--estado-atencao` / `--estado-atencao-fraco` |
| baixa | `--estado-sem-dados` (traço, sem preenchimento — é o tom mais discreto que já existe, e "baixa" é literalmente a gravidade que menos precisa gritar) |

Isto não é um token proposto — é a decisão de **não** propor um: criar
`--achado-alta`/`--achado-media`/`--achado-baixa` novos duplicaria um
significado que `--estado-quebrado`/`--estado-atencao`/`--estado-sem-dados`
já carregam, e é exatamente o tipo de segunda cópia que o `CLAUDE.md` deste
repositório registra como o defeito recorrente desta base ("uma segunda cópia
já matou o *drift* em silêncio"). A única diferença visual entre "gravidade
alta de um achado" e "selo quebrado de um projeto" é o rótulo escrito ao
lado, que muda porque o vocabulário muda (ver `## textos`) — a cor, a forma
de traço e o peso continuam sendo o mesmo objeto CSS.

**O quarto estado da tela — "não deu para auditar" — usa o próprio selo
`sem_dados`,** com a classe `.selo` e `data-selo="sem_dados"` que
`assets/dervs.css:388-401` já define (losango vazado, traço tracejado de
`--traco-forte`). Não é um estado novo do componente selo; é o mesmo selo,
aplicado à camada `auditoria` de um projeto, exatamente como a spec descreve
`banco.montar_estado` anexando `p["auditoria"] = None`.

**Espaço, forma, tipografia:** `--e1` a `--e6` (respiro de lista e de
cartão), `--raio` (3px, em todo cartão/botão/campo — nada muda aqui),
`--traco`/`--traco-forte`, `--foco-largura`/`--foco-afastamento` (anel de
foco, sempre visível). `--fs-etiqueta` (rótulo de categoria, cabeçalho de
grupo), `--fs-metadado` (carimbo, caminho de arquivo, linha), `--fs-corpo`
(a frase do achado), `--fs-destaque` (nome do projeto no topo da tela),
`--fs-pagina` (título "Auditoria"). Número (contagem de achados por
categoria) usa `font-variant-numeric: tabular-nums`, herdado do corpo global
— nenhuma regra nova de tipografia.

## telas

### 7. Auditoria — a nona tela

Onde ela entra na navegação: um link a mais em `nav.mapa` de `index.html`,
`<a href="#/auditoria" data-tela="auditoria">Auditoria</a>`, entre "Trabalho"
e "Consumo" — ela é consequência de o DERVS ter *entendido* um projeto por
dentro, a mesma família de "o que o DERVS já fez/está fazendo" que Trabalho
representa para o conserto. Uma seção nova `<section id="tela-auditoria"
hidden>` dentro do `<main>`, seguindo o padrão de toda tela existente
(`rota()`/`navegar()`/`mostrar()` de `assets/painel.js:111-127`). A tela
também é alcançável **sem passar pela navegação**: o botão "Ver auditoria" que
a tela Projeto ganha ao lado da prova de cada critério leva direto para
`#/auditoria?projeto=<nome>`, no mesmo padrão de parâmetro de rota que
`#/conectar` já usa hoje para o alvo.

**Regra de layout, herdada sem ajuste:** uma coluna até 720px, largura máxima
de leitura em 1100px, nenhum painel lateral fixo.

**Composição, de cima para baixo:**

1. **Seletor de projeto** — lista dos projetos que têm a auditoria ligada
   (opt-in, por decisão da spec). Trocar o projeto troca a tela inteira; a
   URL carrega o projeto escolhido, então recarregar a página ou colar o link
   mantém o contexto.
2. **O carimbo, sempre no topo, sempre visível** — "Última auditoria: há 41
   minutos" ou, no estado nunca-auditado, a ausência dele é o próprio sinal
   (ver estado vazio abaixo). É a lei do produto: nenhum número aparece sem
   dizer quando foi medido, e aqui o número é a lista inteira de achados.
3. **A régua de contagem por categoria** — cinco contadores (segurança, bug,
   teste, documentação, estilo), cada um com a contagem de achados abertos
   naquela categoria. Tocar em um filtra a lista abaixo, no mesmo padrão da
   régua de estado do Painel (`.regua .selo` de `assets/painel.css:120-126`).
4. **A lista de achados**, agrupada por gravidade (alta primeiro, depois
   média, depois baixa — mesma lógica de "o que precisa de atenção primeiro"
   que ordena o Painel), linha cheia de borda a borda, com `--borda` entre
   elas. Cada linha: o par cor+traço de gravidade · a frase do achado ·
   arquivo e linha · categoria · a ação ("Abrir o arquivo" quando há
   `arquivo`, "Já virou pendência" com link para o Painel quando é gravidade
   alta e já gerou tarefa na fila, com a cor do semáforo daquela regra
   `auditoria_<categoria>` ao lado — verde anda sozinho, vermelho espera
   clique, exatamente o vocabulário que `tarefas.cor_da_regra` já define).
5. **Botão "Auditar agora"**, sempre visível no topo da tela (não escondido
   atrás de rolagem) — o mesmo verbo e posição do botão "Medir agora" que já
   existe no Painel.

**Os quatro estados:**

- **Vazio / nunca auditado.** Projeto com auditoria ligada mas sem nenhuma
  corrida em `auditoria_do_projeto`. Sem carimbo, sem régua, sem lista.
  Mensagem central com o próximo passo único: *Auditar agora*. Este estado
  **não é o mesmo** que "sem dados" — é "ainda não pedimos", e o texto diz
  isso com todas as letras (ver `## textos`).
- **Carregando.** Só depois de clicar "Auditar agora": o botão vira
  "Pedindo…" e desabilita; a régua e a lista da corrida anterior (se
  houver) continuam na tela, acinzentadas, com uma faixa no topo — o mesmo
  padrão do Painel quando o servidor não responde
  (`docs/esteira/dervs/design.md`, tela 2, estado Erro). Nunca uma tela em
  branco enquanto a auditoria roda: ela pode levar minutos, e uma tela vazia
  nesse intervalo seria indistinguível de "projeto sem achado".
- **Erro / sem dados.** A corrida terminou com `estado='falha'` ou
  `'recusada'` (saída truncada, vazia, JSON quebrado, ou o teto do dia
  estourou antes de começar). A lista e o carimbo **da última corrida boa**
  continuam na tela — nunca são apagados por uma corrida que falhou — com uma
  faixa acima dizendo que a tentativa mais recente não deu para completar, e
  o motivo em português. Projeto que **nunca** teve uma corrida boa cai no
  estado vazio acima, não neste. Este é o estado que a lei 2 do repositório
  proíbe de parecer "zero achados": a régua nunca mostra "0" quando o motivo
  é "não consegui", ela some ou vira o próprio losango `sem_dados`.
- **Preenchido.** Corrida `estado='ok'`, com carimbo, régua e lista. Zero
  achados é um estado válido **só aqui**, e o texto diz "0 achados — a
  auditoria rodou e não achou nada a apontar", nunca um "0" pelado, para não
  se confundir visualmente com o estado de erro acima.

**Em 360px:** o seletor de projeto vira um `<select>` de largura total; a
régua de cinco categorias quebra em duas linhas de 44px de alvo de toque
cada; cada linha de achado empilha verticalmente — gravidade e categoria na
primeira linha, a frase na segunda (quebra em até duas linhas, reticências na
terceira, igual à regra já escrita para o motivo do Painel), arquivo:linha na
terceira. Nenhuma rolagem horizontal na página: um trecho de código longo
dentro do achado expandido rola dentro do próprio contêiner, com
`overflow-x: auto` — o mesmo padrão que a tela Projeto já usa para a saída de
comando.

## textos

Todo texto em português do Brasil, seguindo o vocabulário fixo de
`docs/A-APLICACAO.md` §9 e de `docs/esteira/dervs/design.md` (nada de
*finding*, *severity*, *scan*).

**Título e navegação:** `Auditoria` (link e `<h1>` da tela).

**Botão principal:** `Auditar agora` — mesmo verbo de `Medir agora`, porque é
a mesma ação de fundo (pedir uma medição), só que mais profunda.

**As cinco categorias, rotuladas:**

| Categoria (interna) | Rótulo na tela |
|---|---|
| `seguranca` | Segurança |
| `bug` | Bug |
| `teste` | Teste |
| `doc` | Documentação |
| `estilo` | Estilo |

**As três gravidades, rotuladas:**

- `alta` — "grave" (o adjetivo, não o substantivo — "achado grave", casando
  com o vocabulário de gravidade que a régua de estado usa)
- `media` — "atenção"
- `baixa` — "menor"

**Estado vazio (nunca auditado):**

> "Este projeto ainda não foi auditado. A auditoria lê o código por dentro —
> não só o que está em volta dele — e aponta o que merece atenção, agrupado
> por gravidade."
> → *Auditar agora*

**Estado carregando:**

> Faixa: "Pedindo a auditoria de **ccvp-painel**… Ela só começa depois do seu “Pode fazer”."
> Botão: "Pedindo…" (desabilitado)

**Estado erro/sem dados (a corrida mais recente falhou, mas há uma anterior
boa):**

> Faixa: "A última tentativa de auditar não terminou. Mostrando o resultado
> de há 3 dias, de 30/08."
> Motivo (uma linha, embaixo da faixa): "A saída do agente veio incompleta."

**Estado erro/sem dados (nunca houve corrida boa e a mais recente falhou):**

> "Não deu para auditar este projeto ainda. A saída do agente veio vazia."
> → *Tentar de novo*

Nunca "Erro 500", nunca "Algo deu errado" — mesma regra do vocabulário geral.

**Estado preenchido, zero achados:**

> "0 achados. A auditoria rodou até o fim e não encontrou nada que
> merecesse atenção."

**Estado preenchido, com achados — rótulo da régua:**

> "Segurança: 2 · Bug: 1 · Teste: 0 · Documentação: 3 · Estilo: 5"

**Ação de cada achado, conforme o estado da pendência:**

- Achado grave que virou tarefa, cor verde (`cor_da_regra` == verde): "Já
  entrou na fila. O DERVS conserta sozinho." → link para a tarefa em
  Trabalho.
- Achado grave que virou tarefa, cor vermelha: "Na fila, esperando você
  liberar." → link para o Painel/Alerta correspondente.
- Achado grave, mas sem `arquivo` válido (não vira pendência, por regra da
  spec — pendência sem ação é proibida): "Não abriu tarefa: não achamos o
  arquivo exato para apontar."
- Qualquer achado, gravidade média ou baixa: "Abrir o arquivo" (leva ao
  VS Code local, mesma ação `{"tipo": "vscode", ...}` que a tela Projeto já
  usa).

**Carimbo:**

> "Última auditoria: há 41 minutos, 5 arquivos lidos, custou R$ 0,62."

**Dados de demonstração** — achados de mentira, verossímeis, no mesmo
universo dos projetos que `docs/esteira/dervs/design.md` já usa
(`ajudei-saude`, `ccvp-painel`, `medconsultoria`):

| Projeto | Gravidade | Categoria | Frase | Arquivo:linha |
|---|---|---|---|---|
| `ccvp-painel` | grave | Segurança | "A função de login devolve `True` quando a senha vem vazia, em vez de recusar." | `auth.py:88` |
| `ccvp-painel` | grave | Bug | "Um `except Exception: pass` engole qualquer erro dentro da rotina de cobrança." | `cobranca.py:204` |
| `medconsultoria` | atenção | Teste | "O teste de agendamento sempre passa porque a asserção compara a lista consigo mesma." | `test_agenda.py:41` |
| `medconsultoria` | menor | Documentação | "O README ainda descreve a porta 8000; o serviço sobe na 8080 desde a última publicação." | `README.md:12` |
| `zacareli` | menor | Estilo | "Função com 340 linhas mistura three responsabilidades: validar, calcular e enviar e-mail." | `pedidos.py:15` |

## assets

**Nenhuma imagem nova.** A tela não introduz nenhum arquivo em `assets/` —
condição dura da spec (§8, "Nenhum arquivo novo em `assets/`") e do
`CLAUDE.md` deste repositório: a lista de estáticos nasce de uma leitura da
pasta na subida, e a proteção de sessão em `servir.ESTATICOS_COM_SESSAO`
casa por caminho exato contra só dois nomes (`painel.js`, `painel.css`). Um
arquivo novo nasceria servido **sem** exigir sessão, e só depois de reiniciar
o servidor — os dois defeitos que este repositório já aprendeu a evitar.

Toda peça visual da tela é resolvida com o que já existe:

- **O selo de cada gravidade** reusa o componente `.selo`/`.selo__forma`/
  `.selo__glifo` de `assets/dervs.css`, com `data-selo` mapeado das três
  gravidades para os três estados que já têm forma e traço definidos
  (`quebrado` → grave, `atencao` → atenção, `sem_dados` → menor, sem
  preenchimento). Nenhum SVG, nenhum ícone literal novo — a lição já
  registrada neste repositório é que ícone literal não se lê em 16px, e a
  Torre de Controle resolveu isso com forma geométrica + glifo textual
  monoespaçado (`[OK]`, `[!]`, `[X]`, `[···]`) em vez de pictograma. O selo
  de auditoria herda exatamente esse mecanismo.
- **Os ícones de categoria** (segurança, bug, teste, doc, estilo) **não
  existem como ícone** — são só o rótulo textual em `--fs-etiqueta`, caixa
  alta, na régua de contagem, no mesmo molde da régua de estado do Painel.
  Cinco pictogramas novos custariam mais do que valem numa tela que já tem
  cor, forma e texto fazendo esse trabalho.
- **A ação "Abrir o arquivo"** reusa o mesmo botão de texto (sem ícone) que a
  tela Projeto já usa para a mesma ação `vscode`.

## estrategia_de_aquisicao

A tela de Auditoria é interna, atrás de login, de acesso `dado` (a classe
mais restrita que existe hoje — a spec justifica isso porque um achado
carrega trecho de código-fonte privado). Não há nada a otimizar para busca ou
compartilhamento: `robots.txt` já bloqueia `/painel` e tudo abaixo de
`/api`, e a regra de `noindex, nofollow` em toda tela autenticada
(`docs/esteira/dervs/design.md`, "Achabilidade") cobre esta tela nova sem
precisar de uma linha extra — ela nasce dentro do mesmo domínio de telas
autenticadas.

**Como a pessoa chega:** três caminhos, nenhum deles busca externa.

1. **Pela navegação principal**, o link "Auditoria" ao lado de "Trabalho" e
   "Consumo" — sempre visível para quem está logado.
2. **Pela tela Projeto**, com o botão "Ver auditoria" ao lado de cada
   critério medido — o caminho mais natural, porque quem está olhando "por
   que este projeto está quebrado" é exatamente quem quer a leitura mais
   funda.
3. **Pela tela Alerta**, quando o alerta em questão é um achado grave de
   auditoria (regra `auditoria_<categoria>`): o link "Ver o que gerou este
   selo" que já existe leva à mesma prova, mas para um achado de auditoria
   ele aponta para a tela Auditoria filtrada naquele achado, em vez de para
   a tela Projeto — mesma ação, destino mais preciso.

**O próximo passo que a tela sempre oferece** — ela nunca termina no ar:

- Estado vazio → *Auditar agora* (a auditoria em si).
- Estado carregando → nada a clicar; a única ação disponível é esperar ou
  sair da tela, e a corrida continua em segundo plano (o mesmo padrão que
  o Painel já usa para tarefas em andamento).
- Estado erro/sem dados → *Tentar de novo* quando nunca houve corrida boa;
  quando há uma corrida anterior boa, o próximo passo é a própria lista
  (que continua interativa) mais o botão *Auditar agora* para tentar de
  novo.
- Estado preenchido, zero achados → *Auditar agora* continua disponível
  (repetir mais tarde), sem outro próximo passo forçado — "nada achado" é
  destino final legítimo desta tela.
- Estado preenchido, com achados → cada achado grave que virou pendência diz
  para onde ir (Trabalho, se verde; Painel/Alerta, se vermelho); achados
  médios e baixos oferecem só "Abrir o arquivo", porque não geram pendência
  nesta fase (fora de escopo da spec) — o próximo passo aí é o dono decidir
  fora do DERVS, e a tela não finge que há um botão que não existe.
