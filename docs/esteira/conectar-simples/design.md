# Design — Conectar simples, entrega A

Fase 3 da esteira, escrita em 09/10/2026. Contrato desta fase: o `briefing.md` (com a seção
`decisoes_do_portao_1`, que vence) e o `spec.md` desta pasta. Esta fase **não cria direção
visual**: ela aplica a direção já aprovada à tela Conectar. Onde o `spec.md` não fixou um
texto ou um comportamento, a decisão tomada aqui vem marcada com **[decisão de design]**,
para a fase de plano e o dono poderem inverter sem caçar.

## direcao_visual_escolhida

**Torre de Controle**, a direção já aprovada pelo dono e escrita em
`docs/esteira/dervs/design.md` (seção `direcao_visual_escolhida`). Densidade alta, nenhuma
sombra, quinas de 3px, hierarquia só por tipografia, borda de 1px e troca de fundo, preto e
branco como identidade e ação (`--acao`), e verde **apenas** como estado saudável. A tela
Conectar já é construída nessa linguagem (`.cartao`, `.porta`, `.marca`, `.faixa`,
`.receita`, `.numerao`); esta entrega só acrescenta peças do mesmo vocabulário.

**Recusadas.** Não houve painel de três direções nesta fase, e isso é de propósito: a
direção foi decidida e aprovada em 26/08/2026, o briefing desta esteira (plano de voo) diz
que o portão visual não abre, e refazer a discussão custaria uma rodada para chegar no
mesmo lugar. As direções recusadas na ocasião (Alvorada e READOUT) continuam recusadas
pelos motivos escritos lá. Recusado aqui, com motivo, qualquer estilo que destoe:

- **Assistente passo a passo colorido, de "primeiros passos"** (barra de progresso
  verde, ilustração de boas-vindas, emoji, confete na conclusão). Motivo: verde é estado
  saudável, não cor de marca — uma barra verde de progresso ensinaria o dono que verde quer
  dizer "vá em frente", e o selo verde de um projeto perderia o significado. Além disso, o
  produto não decora: se está quieto, é porque está bem.
- **Modal que bloqueia a tela e conduz o dono por etapas.** Motivo: o fluxo vive em dois
  lugares ao mesmo tempo (a tela e a janela preta do computador); modal prende a pessoa
  numa tela enquanto ela precisa olhar a outra.
- **Cartões flutuantes com sombra, ícones grandes arredondados, gradientes.** Motivo:
  sombra e arredondamento grande são linguagem calorosa, contrária à régua de instrumento
  aprovada; e nenhuma sombra existe em nenhum lugar do produto.
- **Animação de entrada, barra girando, "carregando" decorativo.** Motivo: movimento só de
  cor e opacidade, até 150ms. A única coisa que se mexe é o ponto que pulsa do `.freio`,
  para dizer "vivo agora", e ele respeita `prefers-reduced-motion`.
- **Cor de destaque diferente de `--acao`** em botão, chave ou link. Motivo: regra dura 4
  da direção aprovada.

## tokens

Os tokens vivem em **`assets/dervs.css`** (bloco `:root`, mais o redefinido no tema escuro
por `prefers-color-scheme` e por `[data-theme="dark"]`); `assets/painel.css` só consome. Esta
entrega **não cria nenhum token novo**: tudo que as telas precisam já existe. Cor nunca é
literal fora do bloco de tokens.

### Cor

| Token | Uso nestas telas |
|---|---|
| `--fundo` | fundo da página e do campo de texto |
| `--fundo-elevado` | cartão de cada ligação, faixa, caixa do comando, linha de projeto achado |
| `--texto` | texto principal |
| `--texto-suave` | metadado, carimbo, texto de ajuda (`.mole`), projeto escondido |
| `--borda` | divisor entre linhas de uma lista (decorativo) |
| `--borda-forte` | contorno de campo, de cartão, da chave "mostrar no painel" e dos desenhos de ajuda — onde a borda carrega significado |
| `--acao` / `--acao-texto` | botão principal, chave ligada, link, anel de foco, filete de 2px da faixa de página velha |
| `--estado-saudavel`, `--estado-quebrado`, `--estado-sem-dados` (e os `-fraco`) | **somente** dentro da `.marca` das ligações ("conectado", "não conectado", "não deu para conferir"), como já é hoje. Nunca em botão, chave ou faixa |

`--estado-atencao` **não é usado** por nenhuma peça nova.

### Tipografia

- `--fonte-sans` (IBM Plex Sans) em tudo, `--fonte-mono` (IBM Plex Mono) só em número
  medido, código de autorização, nome de pasta, endereço de site e comando.
- Escala: `--fs-etiqueta` (cabeçalho de grupo), `--fs-metadado` (carimbo, ajuda, marca),
  `--fs-corpo` (texto), `--fs-destaque` (nome de projeto, nome de computador),
  `--fs-titulo` (título de cartão), `--fs-pagina` (código de autorização, via `.numerao`).
  Nada acima de `--fs-pagina`.
- Número que se alinha em coluna: `font-variant-numeric: tabular-nums`.

### Espaçamento, forma e movimento

- Grade de 4px: `--e1`, `--e2`, `--e3`, `--e4`, `--e6`, `--e8`, `--e12`. Raio `--raio` (3px)
  em tudo. Traço `--traco` (1px) e `--traco-forte` (2px). Foco: `--foco-largura` com
  `--foco-afastamento`, sempre visível. Movimento: `--transicao` (150ms), só cor e opacidade.
- **Achado que a fase encontrou, para o plano:** `painel.css` usa `--e5`, `--r2` e
  `--fundo-fraco`, que **não existem** em `dervs.css` (o primeiro não tem fallback, os
  outros dois têm). Peça nova **não os usa**; usa `--e4`/`--e6` e `--raio`. Corrigir os
  antigos não é escopo desta entrega.

### Peças novas, feitas só com tokens existentes

Nenhuma é token; são classes de composição, a nomear no plano:

- **Faixa fixa de página desatualizada** — estende `.faixa` (fundo `--fundo-elevado`, borda
  `--borda-forte`), `position: sticky; top: 0`, mais filete inferior de `--traco-forte` em
  `--acao`. **Não usa `--estado-*`** (o comentário de `.faixa` no CSS já proíbe: ela é aviso
  sobre a própria leitura, não selo de projeto). Fica acima do `.freio` na ordem de
  empilhamento (`z-index` maior): sem recarregar nada funciona, então ela vence.
- **Chave "mostrar no painel"** — um `<input type="checkbox" role="switch">` verdadeiro, com
  `<label>` clicável. Trilho e botão em `--borda-forte`; ligada, o trilho vira `--acao` e o
  botão desliza para a direita. **Nunca verde.** Ao lado, o texto "Aparece no painel" /
  "Escondido do painel" — a posição do botão e o texto carregam o significado, a cor não.
  Alvo de toque de 44×44px (o `<label>` inteiro).
- **Linha de projeto achado** — `li` de `.lista` com `.dizeres` (nome em `--fs-destaque`,
  pasta em `--fonte-mono`/`--fs-metadado` com `overflow-wrap: anywhere`) e a chave à direita;
  em 360px a chave desce para baixo do texto (mesmo padrão `flex-wrap` de `.computadores`).
- **Passos numerados** — `<ol>` de `.mole` com o número em `--fonte-mono`; desenho de ajuda
  ao lado do passo em ≥ 40rem, acima do texto abaixo disso.

## telas

Uma única rota, `#/conectar`, que já existe. **O menu continua com exatamente quatro itens**
(Painel, Consertar, Conectar, Conta); nada é acrescentado e o endereço antigo
`#/computadores` continua redirecionando. O que muda é o conteúdo da tela e um bloco
especial que ela mostra quando a página é aberta com `?autorizar=<código>`.

**Leis que valem em todas as telas abaixo:** (1) "não sei" é estado de primeira classe — onde
a leitura falhou, a frase diz "não consegui ler; isso não quer dizer que não há — quer dizer
que não olhei", nunca "0" nem "nenhum"; (2) tudo que vem de outro repositório ou de outro
computador (nome de projeto, nome de pasta, nome de máquina, motivo de erro de rede) entra
por `textContent`, nunca por `innerHTML`; (3) número vindo de campo de texto ou de `select`
é convertido com `+x`, nunca `Number(` nem `parseInt(`; (4) `aria-live="polite"` só em área que
muda sozinha, posto junto com o primeiro texto; (5) nada de rolagem horizontal da página —
caminho e comando rolam **dentro da própria caixa**.

### Ordem da tela Conectar, de cima para baixo

1. Faixa de página desatualizada (só aparece quando precisa; fica fixa no topo).
2. Bloco "Autorizar este computador" (só com `?autorizar=` na URL; ver tela B).
3. Título "Conectar" e uma frase: "Ligue o DERVS ao que você usa. Cada cartão tem um botão."
4. Cartão **Este computador**.
5. Cartão **GitHub**.
6. Cartão **Seus sites**.
7. `<details>` fechado "Recados do DERVS-VOZ" (o histórico que saiu do meio da tela).

Em 360px, sem rolagem, o dono vê: o título, a frase e o **cartão Este computador inteiro
até o botão principal** — o próximo passo único. Os outros dois cartões ficam logo abaixo,
cada um com seu botão, sem nada entre eles.

### Tela A — cartão "Este computador"

Composição: cabeça (título + `.marca`), uma frase do que está ligado, o **botão principal**,
a lista de computadores, "O que isso faz?" (fechado), "Prefiro colar um comando" (fechado).

- **Botão principal.** Um só: "Conectar este computador". É um `<a class="botao" href=...
  download>` com GET (o spec exige: preserva o gesto do usuário). Como é link, não botão,
  o leitor de tela o anuncia como "link"; o `aria-label` não troca o texto visível, e o
  texto de apoio logo abaixo diz que baixa um arquivo. Quando já há computador conectado, o
  botão continua o mesmo (conectar mais um) mas passa a `botao--secundario` com o texto
  "Conectar outro computador" — o principal da tela passa a ser a lista.
- **Antes do clique, o aviso que o dono precisa ver (decisão 4 do portão 1).** Abaixo do
  botão, em `.mole`: "O Windows vai perguntar se você confia no arquivo. É normal — veja
  abaixo o que clicar." Seguido do `<details>` **"O que vai aparecer?"**, **aberto na
  primeira visita** e fechado nas seguintes (lembrado só no navegador de quem escolheu, com
  `try/catch`; sem armazenamento a tela renderiza aberta). Dentro, a lista de passos com
  desenho (ver `assets`) — texto completo em `textos`.
- **Estados do cartão:**
  - *Carregando (lendo a lista de computadores):* marca `sem_dados` "não deu para
    conferir" com a frase "Olhando os computadores desta conta…"; o botão principal já
    aparece e já funciona (baixar não depende da leitura). `aria-busy="true"` no cartão até
    a leitura terminar.
  - *Vazio (olhou e não há nenhum):* marca `desconectado` "não conectado"; frase "Nenhum
    computador está ligado ao DERVS ainda. Sem um, o painel só enxerga o que está no
    GitHub."; o botão principal é o próximo passo.
  - *Esperando (depois que o dono clicou ou abriu a página de autorizar):* ponto que pulsa
    (`.freio__ponto`, parado com `prefers-reduced-motion`) e "Esperando o computador dar a
    primeira notícia…", dentro de `.espera` com `aria-live="polite"`. A sondagem é a de 5 s
    que já existe (`/api/maquinas`), por até 10 minutos.
    **[decisão de design]** Ela também começa quando o dono clica em "Conectar este
    computador" (não só na página de autorizar), para a aba antiga também mudar sozinha
    quando o computador aparecer; o spec diz "começando na página de autorizar", e isto só
    acrescenta o início.
  - *Conectado com projetos:* marca `conectado` com o rótulo "Conectado — achei 7
    projetos" (o rótulo vem do número medido; ver abaixo o caso zero), mais o carimbo "deu
    notícia há 12 segundos", e a **lista de projetos achados** (nome, pasta, chave).
  - *Conectado, primeira medição ainda não chegou:* **não escrever "0 projetos"**: a marca
    diz "Conectado" e a frase "O computador apareceu e ainda não mandou a primeira medição.
    Isso leva menos de um minuto." Zero só é escrito depois de uma medição que olhou e não
    achou.
  - *Conectado, medição olhou e achou zero:* "Olhei a pasta C:\Users\Desktop\projetos e não
    achei nenhum projeto com histórico de versões. Para escolher outra pasta, baixe o
    arquivo de novo e abra." — com o botão "Baixar de novo".
  - *Computador mudo (sem notícia há mais tempo que o normal):* marca `sem_dados` "não deu
    para conferir"; "O PC-ESCRITORIO não dá notícia há 3 horas. Os projetos dele continuam
    no painel, parados no último carimbo. Veja se o computador está ligado." Nada é
    apagado.
  - *Erro ao ler a lista:* marca `sem_dados`; "Não consegui ler os computadores desta conta.
    Isso não quer dizer que nenhum esteja ligado — quer dizer que não olhei." Mais o botão
    secundário "Tentar de novo".
  - *Erro de pedido vencido:* "O pedido venceu e nenhum computador apareceu. Baixe o
    arquivo de novo." Botão "Baixar de novo".
  - *Sucesso:* é o estado "Conectado com projetos" acima, que **não some**: o cartão passa a
    ser o lugar permanente de ver o que foi achado.
- **Linha de computador (já existe, `.computadores`).** Nome, "deu notícia há…", nº de
  projetos, o rótulo "Só mede" e o botão "Remover". Para o computador ligado por este
  arquivo **não há** o botão "Deixar consertar aqui" (o pacote não leva o braço que
  executa; o servidor o recusaria — botão que mente). No lugar, a frase "Este computador só
  acompanha os projetos. Ele não faz alterações." O computador pareado por linha de comando
  mantém os dois botões como hoje.
- **Lista de projetos achados.** Cada linha: nome em `--fs-destaque`, pasta em mono, chave
  "mostrar no painel". *Chave ligada* = aparece no painel (padrão). *Desligar* esconde o
  projeto do painel **desta conta** e sobrevive a nova medição; a linha continua na lista,
  em `--texto-suave`, com "Escondido do painel" e a chave desligada — **nunca some da
  lista**, senão não haveria como voltar. Enquanto o pedido viaja, a chave fica `disabled`
  e `aria-busy`; se falhar, **volta à posição anterior** e aparece a frase "Não consegui
  mudar agora. A chave voltou para onde estava." Lista vazia por filtro não existe (sem
  filtro). Mais de 20 projetos: a lista rola dentro de uma caixa com altura máxima de
  `24rem` e `tabindex="0"` e `aria-label`, para o cartão não empurrar os outros dois para
  fora da tela.
- **"Prefiro colar um comando" (`<details>` fechado).** Dentro, o que hoje está na seção
  Computadores: "Gerar o número", o número grande, o prazo, a caixa com a linha do comando
  (`.receita`, rola na horizontal dentro da caixa), "Copiar comando", e a frase que explica
  que o pedaço `<CAMINHO DO DERVS>` deve ser trocado pela pasta onde o DERVS está. É o único
  lugar da tela onde as palavras "comando" e "pasta do DERVS" aparecem.
- **Comportamento em 360px.** Cartão em largura total com `--e4` de respiro lateral. O botão
  principal ocupa a linha inteira (`min-height: 44px`). Nome de computador e de pasta quebram
  (`overflow-wrap: anywhere`). A chave desce para baixo do nome do projeto. Os desenhos de
  ajuda ficam acima do texto de cada passo, em largura total, altura máxima de 9rem.
- **Foco, teclado e leitor de tela.** Ordem do foco = ordem visual. O `<details>` abre com
  Enter e Espaço (elemento nativo). A chave é `role="switch"` com `aria-checked` (nativo do
  `input`), e o rótulo lido é "Mostrar no painel: clinica-agenda, ligado" — o nome do
  projeto vai no `aria-label` da chave, porque "Mostrar no painel" repetido dez vezes não
  distingue nada. Depois de ligar/desligar o foco **fica na chave**. A marca do cartão tem
  glifo `aria-hidden` e rótulo escrito, como hoje. O ponto que pulsa é `aria-hidden`.

### Tela B — "Autorizar este computador" (bloco no topo de Conectar)

Aparece quando a rota é `#/conectar?autorizar=<código curto>`, que é para onde o arquivo
baixado leva o navegador. É um `.cartao` acima dos três cartões, com `aria-labelledby`.
**Não é uma tela de menu, nem um modal**: a pessoa pode ver os três cartões logo abaixo.

Conteúdo: título, a frase "O computador **PC-ESCRITORIO** pediu para se ligar ao seu
painel", o **código em `.numerao`** (mono, grande) para ser conferido com a janela preta do
computador, o prazo ("vale por mais 8 minutos", atualizado a cada minuto, não a cada
segundo), o botão principal "Autorizar este computador", e a frase de segurança "Não
reconhece este computador? Não clique em nada: o pedido vence sozinho e nada é ligado."
(mitigação do phishing remoto do RFC 8628; o spec não prevê botão de recusar.)

- *Carregando:* "Conferindo o pedido…", o botão ainda não existe (aparece com os dados, para
  ninguém autorizar às cegas). `aria-busy="true"`.
- *Vazio / não existe / venceu:* "Este pedido venceu ou não existe. Baixe o arquivo de
  novo e abra." com o botão "Voltar para Conectar" (que tira o `?autorizar=` da URL).
- *Já autorizado:* "Este computador já foi autorizado. Veja abaixo se ele apareceu."
- *Erro de rede ao conferir:* "Não consegui falar com o DERVS agora. Isso não quer dizer
  que o pedido venceu — quer dizer que não olhei." + "Tentar de novo".
- *Erro ao autorizar:* a mesma frase de erro, e o botão volta a ficar ativo. Recusa 403 por
  página velha cai na faixa (tela D), não aqui.
- *Sucesso:* o botão vira texto: "Autorizado. Volte à janela preta do computador: ela
  termina sozinha." e a espera de 5 s começa (ver Tela A); quando o computador mede, o
  bloco se recolhe e o cartão mostra "Conectado — achei N projetos". O foco vai para o
  título do cartão do computador.
- *Em 360px:* o código cabe em uma linha (9 caracteres mono em `--fs-pagina`, ≈ 190px); o
  botão ocupa a largura toda. O nome do computador quebra em qualquer ponto.
- *Foco e leitor:* ao abrir a página, o foco vai para o título do bloco (`tabindex="-1"`),
  que lê "Autorizar este computador?"; o código é lido letra a letra por um `aria-label`
  com os caracteres separados por vírgula; o nome do computador é `textContent`.
- **[decisão de design]** O código tem **formato `XXXX-XXXX`** com letras e números sem
  caracteres ambíguos (sem 0/O, 1/I) — o spec diz só "código curto". Se o servidor
  escolher outro formato, o bloco se adapta; o que não muda é a conferência visual.

### Tela C — cartão "GitHub"

Composição: cabeça (título + `.marca`), frase, botão principal, lista de contas, links.

- **Botão principal.** "Conectar conta do GitHub" (primeira vez) / "Conectar outra conta do
  GitHub" (já há contas). Serve para conta pessoal e para organização; a frase diz isso.
  Se o aplicativo não está registrado no servidor, o botão fica `disabled` com o motivo ao
  lado ("o aplicativo do GitHub ainda não foi registrado neste servidor"), como hoje.
- **O botão "Procurar minhas contas" deixa de existir.** A procura roda sozinha, uma vez por
  carga da tela Conectar e quando a página volta do GitHub com `?github=`.
- **Cada conta** (`li`): nome da conta em `--fs-destaque`, "pessoal" ou "organização" em
  `.carimbo`, "mede 12 repositórios · mediu há 4 minutos" (número em mono, tabular), e o
  link "Escolher repositórios no GitHub" (abre em nova aba com `rel="noopener noreferrer"`,
  e o texto diz "abre o GitHub" para quem usa leitor de tela).
- **Lista de repositórios com a chave "mostrar no painel".** Por conta, um `<details>`
  fechado "Ver os 12 repositórios", com a mesma linha e a mesma chave da Tela A.
  **[decisão de design]** O spec fala da chave "na lista do GitHub" e deixa de dizer o que
  a chave faz para um repositório que **não é projeto de nenhum computador** (repositório só
  do GitHub não vira projeto nesta entrega). Decidido: nesses, a linha **não mostra a chave**
  e diz "Ainda não é um projeto do painel — nenhum computador ligado tem esta pasta." Nunca
  mostrar uma chave que não faz nada. Também depende de o servidor entregar os nomes dos
  repositórios medidos, que hoje só vêm como contagem — para o plano.
- **Estados:**
  - *Procurando (sozinha):* linha `.espera` com `aria-live="polite"` "Procurando suas contas
    no GitHub…". Dura até alguns segundos; o botão principal continua ativo.
  - *Vazio (olhou e não há conta):* marca `desconectado`; "Nenhuma conta do GitHub ligada
    ainda. Ligada, ela traz sozinha os pedidos de alteração, a verificação automática e os
    alertas de segurança dos repositórios que você liberar."
  - *Achou conta nova:* marca `conectado`; "Achei e liguei a conta loja-da-ana." — frase em
    `aria-live`, some na próxima carga.
  - *Nada novo:* silêncio. Procura que não achou nada não escreve nada na tela, para não
    parecer erro nem sucesso.
  - *Voltou do GitHub sem confirmar (a pessoa fechou a página no meio):* marca `sem_dados`;
    "Não deu para confirmar a conta. Se você fechou a página do GitHub no meio, é isso
    mesmo e não é erro: é só tentar de novo. O DERVS só liga a conta depois que o GitHub
    confirma." (frase já existente, mantida.)
  - *Erro na procura:* marca `sem_dados`; "Não consegui procurar suas contas agora. Isso não
    quer dizer que não há — quer dizer que não olhei." com o botão secundário "Tentar de
    novo". **[decisão de design]** Esse botão só existe **no estado de erro** — não é o
    "Procurar minhas contas" que o critério 4 manda tirar. Se o dono preferir sem botão
    nenhum, a recarga da página já refaz a procura.
  - *Erro 403 de página velha:* a faixa (tela D) explica; o cartão não repete a frase
    "não consegui procurar".
  - *Sucesso:* a lista de contas com o carimbo "mediu há…".
- **Desconectar** continua sem botão (decisão antiga): a nota diz que se faz no GitHub, em
  palavras do dono (ver `textos`).
- **360px:** cada conta é uma linha de duas fileiras (nome e tipo em cima; medição e link
  embaixo); o botão principal na largura toda; a lista de repositórios rola dentro de
  caixa de `24rem` de altura máxima.
- **Foco e leitor:** link externo anuncia "abre o GitHub em outra aba"; a chave segue a
  mesma regra da Tela A; o resultado da procura automática é anunciado uma vez.

### Tela D — faixa "Esta página ficou desatualizada" (todo o painel)

Peça transversal: aparece em **qualquer** tela, quando **qualquer** das chamadas de
`escrever(` recebe 403 com `motivo: "pagina_velha"`. Uma instância só (uma segunda recusa
não empilha outra).

- **Composição:** `.faixa` fixa no topo, texto em duas linhas curtas, botão "Recarregar"
  (`botao`, primário), nada mais. **Não há botão de fechar**: fechar deixaria a pessoa
  clicando em botões que continuariam a ser recusados.
- **Comportamento:** `role="alert"` (anuncia uma vez, no momento em que aparece) e o foco
  vai para o botão "Recarregar", **porque a página inteira passou a não funcionar até
  recarregar** — é o caso em que mover o foco ajuda em vez de atrapalhar. O botão chama
  `location.reload()`.
- **O que a faixa promete, e só isso:** que o que a pessoa acabou de clicar **não foi
  feito**, e que recarregar resolve. Ela não promete o motivo (outra aba, atualização do
  DERVS), porque o servidor só sabe que o token venceu.
- **[decisão de design] O recado do botão clicado.** `r` volta intacto a quem chamou, e
  cada chamador hoje escreve o próprio recado ("não conseguimos adiar. Tente de novo.").
  Com a faixa aberta esse recado **mente** ("tente de novo" falharia de novo). Decidido:
  enquanto a faixa estiver aberta, a função `recado()` troca qualquer texto de erro por
  "Não foi feito. Veja o aviso no alto da página." Isso é uma mexida em `recado()` que o
  spec não menciona; fica para o plano confirmar.
- **Estados:** não há vazio nem carregando. *Erro ao recarregar* (sem rede): o navegador
  mostra a própria página de erro; fora do alcance da tela. *Sucesso:* a página volta sem a
  faixa, porque o token novo veio no recarregamento.
- **360px:** texto e botão empilhados, botão na largura toda (44px de altura); a faixa não
  passa de 7rem de altura, para deixar o conteúdo visível por baixo.
- **Leitor de tela:** "Alerta: Esta página ficou desatualizada. O que você clicou não foi
  feito. Recarregue a página. Botão Recarregar."

### Tela E — cartão "Seus sites"

Composição: cabeça (título + `.marca`), frase, o **campo único** com o botão, o resultado da
conferência, a lista de sites cadastrados, "opções avançadas" (fechado).

- **Campo único.** Rótulo visível "Endereço do site", `inputmode="url"`,
  `autocomplete="off"`, `spellcheck="false"`, `placeholder="https://clinica-agenda.com.br"`.
  Botão principal ao lado: "Conferir o site". Esse botão **não grava** (a rota
  `/api/enderecos/medir` não grava). Enter dentro do campo faz o mesmo.
- **Depois de conferir (resultado):** uma `.marca` e uma frase, e em seguida a pergunta "De
  qual projeto é este site?" com um `select` já no projeto **mais parecido com o endereço**,
  e o botão final:
  - *Respondeu:* marca `conectado` "respondeu"; frase "O site respondeu (código 200) em
    0,4 segundo." Botão "Guardar este site".
  - *Não respondeu:* marca `desconectado` "não respondeu" e o **motivo em português**,
    do dicionário abaixo; botão "Guardar mesmo assim". O sinal é de que **guardar é
    permitido**, só que o painel vai mostrar "fora do ar" até o site responder.
  - *Não deu para conferir (a rota falhou, ou foi recusada por rede interna / teto):* marca
    `sem_dados` "não deu para conferir"; frase "Não consegui conferir este site agora.
    Isso não quer dizer que ele esteja fora do ar — quer dizer que não olhei." Botão
    "Guardar mesmo assim" (guarda sem afirmar nada) e "Tentar de novo".
  - *Endereço recusado por ser de rede interna:* sem botão de guardar: "Este endereço é de
    uma rede interna. O painel só confere sites públicos. Use o endereço que o público
    acessa."
  - *Endereço mal escrito:* o campo ganha `aria-invalid="true"` e a mensagem "Escreva o
    endereço completo, começando por https://, por exemplo https://loja-da-ana.com.br."
    (o `aria-describedby` aponta para ela).
- **Projeto sem opção:** se nenhum projeto foi achado ainda, o `select` não aparece e a
  frase diz "Ainda não há projetos no painel para ligar a este site. Conecte um computador
  primeiro." — o botão de guardar fica desligado, com o motivo escrito ao lado.
- **Carregando:** o botão "Conferir o site" vira "Conferindo…" e fica `disabled`; o
  resultado anterior some (nunca mostrar a resposta do endereço antigo com o endereço novo).
  `aria-busy`. Prazo: a medição leva até ~23 s; depois de 8 s a frase "Ainda conferindo…
  alguns sites demoram." aparece.
- **Sugestões:** quando os projetos já declaram um endereço, linhas "Sugestão: loja-da-ana
  parece estar em https://loja-da-ana.com.br" com "Usar este" (que preenche o campo e
  confere) e "Ignorar". As sugestões **propõem e param**: nada é gravado por elas. Se não há
  sugestão, a área não aparece (não escrever "nenhuma sugestão").
- **Sites já guardados.** Lista plana por projeto: endereço em mono (`overflow-wrap:
  anywhere`), marca (`conectado` "respondeu" / `desconectado` "não respondeu" / `sem_dados`
  "não medi"), "respondeu 200 · medido há 3 minutos", botão "Tirar". O nome do servidor só
  aparece quando existe mais de um.
- **Opções avançadas (`<details>` fechado).** Contém o **servidor** (select; "Meus sites" é
  criado sozinho se não existe nenhum) e o **padrão de subdomínio**, com a ajuda já
  existente. **[decisão de design]** O spec escolhe o servidor sozinho quando só existe um e
  cria "Meus sites" quando não existe nenhum, mas não diz o que fazer com **dois ou mais**.
  Decidido: com dois ou mais servidores o campo "Em qual servidor?" sai das opções avançadas
  e fica **visível e obrigatório** ao lado do projeto, sem escolha prévia — adivinhar o
  servidor errado é o tipo de número errado com cara de certo que a Lei 2 proíbe.
- **Sucesso ao guardar:** o campo esvazia, a lista ganha a linha nova e o foco volta ao
  campo; frase `aria-live` "Guardei https://loja-da-ana.com.br para o projeto loja-da-ana."
  Erro ao guardar: "Não consegui guardar agora. O que você digitou continua no campo."
- **Vazio (olhou e não há site):** marca `desconectado`; "Nenhum site cadastrado ainda. Cole
  o endereço acima para o DERVS conferir se ele responde." Falha de leitura: "Não consegui
  ler os sites desta conta. Isso não quer dizer que não há — quer dizer que não olhei."
- **360px:** campo e botão em colunas (campo em cima, botão na largura toda embaixo); o
  endereço longo quebra; `select` na largura toda.
- **Foco e leitor:** `label` ligado ao campo por `for`; resultado anunciado por
  `aria-live="polite"`; o foco **não** é roubado pelo resultado — ele fica no botão que a
  pessoa apertou, e o próximo `Tab` chega ao `select` e ao botão de guardar.

### Tela F — "Recados do DERVS-VOZ" (rebaixada)

O formulário e o histórico do DERVS-VOZ saem do meio da tela e vão para um único `<details>`
**fechado** no fim de Conectar, com o resumo "Recados do DERVS-VOZ". Nada dentro muda de
comportamento: o conteúdo existente continua, só sai do caminho de quem veio conectar algo.
Não é item de menu. Estados vazios e de erro dos recados ficam como estão. Em 360px o
`<details>` ocupa a largura toda. O resumo é um `<summary>` nativo (Enter/Espaço abrem).

## textos

Todo texto visível, em português do Brasil, **sem** as palavras "agente", "token", "Git"
(como sigla técnica), "linha de comando", "instalação", "dashboard", "loading", "deploy",
"login". A linha de comando e a pasta do DERVS vivem só dentro de "Prefiro colar um
comando". Vocabulário fixo do design aprovado: painel, publicar, medição/medir, pendência,
entrar/sair, excluir, carregando. "Computador" para a máquina do dono; "conta" para o
GitHub; "site" para o endereço público; "ajudante" **não** é usado (a palavra do dono é
"arquivo").

### Cabeçalho da tela

- Título: **Conectar**
- Frase: "Ligue o DERVS ao que você usa. Cada cartão abaixo tem um botão — comece pelo
  primeiro."

### Cartão "Este computador"

- Título: **Este computador**
- Marcas: "conectado" · "não conectado" · "não deu para conferir"
- Frase sem computador: "Nenhum computador está ligado ao DERVS ainda. Sem um, o painel só
  enxerga o que está no GitHub."
- Frase com computador: "Conectado — achei 7 projetos" (marca) e, abaixo, "PC-ESCRITORIO deu
  notícia há 12 segundos."
- Botão principal: **Conectar este computador** (depois de ligado: **Conectar outro
  computador**)
- Apoio sob o botão: "Baixa um arquivo pequeno para o Windows. Você abre, escolhe a pasta
  dos seus projetos e volta aqui. Nada é instalado e não precisa de administrador. Em outro
  sistema que não o Windows, use “Prefiro colar um comando”."
- Se o arquivo não baixar: "Não baixou? Clique de novo. Se continuar, use “Prefiro colar um
  comando”, mais abaixo."
- Esperando: "Esperando o computador dar a primeira notícia. O pedido vale por mais 9
  minutos."
- Primeira medição pendente: "O computador apareceu e ainda não mandou a primeira medição.
  Isso leva menos de um minuto."
- Zero achado (depois de medir): "Olhei a pasta C:\Users\Desktop\projetos e não achei nenhum
  projeto com histórico de versões. Para escolher outra pasta, baixe o arquivo de novo e
  abra." Botão: **Baixar de novo**
- Computador mudo: "O PC-ESCRITORIO não dá notícia há 3 horas. Os projetos dele continuam no
  painel, parados no último carimbo. Veja se o computador está ligado."
- Só mede: "Este computador só acompanha os projetos. Ele não faz alterações." (rótulo da
  linha: **Só mede**)
- Pedido vencido: "O pedido venceu e nenhum computador apareceu. Baixe o arquivo de novo."
- Erro de leitura: "Não consegui ler os computadores desta conta. Isso não quer dizer que
  nenhum esteja ligado — quer dizer que não olhei." Botão: **Tentar de novo**
- Remover (existente, mantido): botão **Remover**; confirmação: título "Desconectar
  “PC-ESCRITORIO”?", texto "Ele para de acompanhar na hora, e só volta se você baixar o
  arquivo de novo e abrir. As medições que ele já mandou não são apagadas, e os projetos dele
  continuam no painel — parados no último carimbo.", botões **Desconectar** e **Manter
  conectado**.

### A chave "mostrar no painel" e a lista de projetos achados

- Cabeçalho da lista: "Projetos que achei neste computador"
- Rótulo da chave: **Mostrar no painel** (lido como “Mostrar no painel: clinica-agenda,
  ligado”)
- Texto ao lado, ligada: "Aparece no painel" · desligada: "Escondido do painel"
- Explicação (uma vez, sob o cabeçalho): "Esconder um projeto tira ele do painel, mas não
  apaga nada. Ele continua aqui na lista e volta quando você ligar a chave. A escolha vale
  só para a sua conta."
- Erro: "Não consegui mudar agora. A chave voltou para onde estava."
- Repositório que não é projeto (lista do GitHub): "Ainda não é um projeto do painel —
  nenhum computador ligado tem esta pasta."

### "O que vai aparecer?" (aberto na primeira visita) — o passo a passo

Cabeçalho do bloco: "O que vai aparecer quando você clicar". Frase de abertura: "Você vai
ver alguns avisos do computador. São normais e todos têm um botão certo. Veja o que clicar
em cada um."

1. **O Chrome pode perguntar se você quer manter o arquivo.** "Se o Chrome mostrar que
   “conectar-dervs.cmd” pode ser perigoso, clique em **Manter**. Ele diz isso de qualquer
   arquivo desse tipo. O nosso é pequeno e legível: dá para abrir no Bloco de Notas e
   conferir antes (botão direito → Abrir com → Bloco de Notas)." *[Conferir no ar, antes de
   publicar: o briefing registra que o aviso do Chrome ainda não foi medido com o arquivo
   servido pelo dervs.com.br. Se o Chrome não avisar, este passo vira "Se o Chrome
   perguntar".]*
2. **Abra o arquivo.** "Clique no arquivo na barra de downloads do Chrome, ou abra a pasta
   Downloads e dê dois cliques nele."
3. **O Windows vai perguntar se você confia.** "Vai aparecer “Abrir Arquivo - Aviso de
   Segurança” com um escudo vermelho e a frase “O fornecedor não pôde ser verificado”. É
   normal: o Windows avisa assim de todo arquivo que não tem assinatura paga. Clique em
   **Executar**."
4. **Uma janela preta vai mostrar o que está sendo feito.** "Ela escreve em português cada
   coisa que faz. Não digite nada nela e não feche. Ela baixa um programa de apoio do site
   oficial do Python (12 MB), confere que ele chegou inteiro e abre este site no navegador."
5. **Escolha a pasta dos seus projetos.** "Uma janela do Windows vai pedir a pasta onde
   ficam seus projetos. Escolha a pasta e clique em **OK**."
6. **Volte ao navegador e autorize.** "Esta página vai mostrar o nome do computador e um
   código. Confira se são os mesmos da janela preta e clique em **Autorizar este
   computador**."
7. **Pronto.** "A janela preta se fecha sozinha. Em até um minuto aparece aqui “Conectado —
   achei N projetos”."

Notas da abertura do bloco (uma frase cada, sob os passos):
- "Funciona no Windows 10 (versão 1803 ou mais nova) e no Windows 11."
- "Precisa de internet, mas não precisa de administrador."

### "O que isso faz?" (`<details>` fechado, para quem quer conferir)

Resumo: "O que esse arquivo faz no meu computador?" Conteúdo:
- "Baixa o programa de apoio do site oficial do Python e confere a impressão digital dele
  antes de usar. Se não bater, apaga e para."
- "Guarda tudo em uma pasta sua, dentro do seu usuário. Não mexe em nenhuma outra pasta e
  não instala nada no Windows."
- "Pede ao DERVS um código e espera você autorizar aqui. Sem o seu clique, nada é ligado."
- "Baixa do DERVS o programa que mede os seus projetos e o agenda para rodar sozinho quando
  você entra no Windows, sem janela."
- "O programa só **lê** a pasta que você escolheu e **envia** o resultado. Ele não abre
  porta no seu computador e não faz alterações."
- "Para desfazer: clique em **Remover** na lista de computadores. O painel deixa de aceitar
  o programa."

### "Prefiro colar um comando" (`<details>` fechado)

- Resumo: **Prefiro colar um comando**
- Texto: "Para um computador sem tela, ou se você prefere o terminal. Gere um número, e cole
  a linha abaixo dele no computador que vai acompanhar. O número vale por poucos minutos e
  serve para um só."
- Aviso: "A única coisa a trocar na linha é <CAMINHO DO DERVS>, pela pasta onde o DERVS está
  naquele computador. O painel não sabe onde ela fica, e inventar seria mentir."
- Botões: **Gerar o número** · **Copiar comando** · confirmação "Comando copiado."

### Bloco "Autorizar este computador"

- Título: **Autorizar este computador?**
- Corpo: "O computador **PC-ESCRITORIO** pediu para se ligar ao seu painel. Confira se o nome
  e o código abaixo são os mesmos da janela preta no computador."
- Rótulo do código: "Código" (lido letra a letra) · exemplo: **K7M4-2QXP**
- Prazo: "Vale por mais 8 minutos."
- Botão: **Autorizar este computador**
- Segurança: "Não reconhece este computador? Não clique em nada: o pedido vence sozinho e
  nada é ligado."
- Carregando: "Conferindo o pedido…"
- Não existe/venceu: "Este pedido venceu ou não existe. Baixe o arquivo de novo e abra." —
  botão **Voltar para Conectar**
- Já autorizado: "Este computador já foi autorizado. Veja abaixo se ele apareceu."
- Erro de rede: "Não consegui falar com o DERVS agora. Isso não quer dizer que o pedido
  venceu — quer dizer que não olhei." — botão **Tentar de novo**
- Sucesso: "Autorizado. Volte à janela preta do computador: ela termina sozinha."

### Cartão "GitHub"

- Título: **GitHub**
- Frase sem conta: "Nenhuma conta do GitHub ligada ainda. Ligada, ela traz sozinha os
  pedidos de alteração, a verificação automática e os alertas de segurança dos repositórios
  que você liberar."
- Frase com contas: "Contas ligadas: 2. O DERVS traz sozinho os pedidos de alteração, a
  verificação automática e os alertas de segurança dos repositórios que você liberou em
  cada conta."
- Botões: **Conectar conta do GitHub** · **Conectar outra conta do GitHub**
- Apoio: "Serve para conta pessoal e para organização. Você escolhe no GitHub quais
  repositórios liberar e pode mudar depois. Nenhuma senha nem chave é digitada aqui."
- Por conta: "clinica-agenda-org" · “organização” (ou “pessoal”) · “mede 12 repositórios ·
  mediu há 4 minutos” (zero: “ainda não mediu repositórios”) · link **Escolher repositórios
  no GitHub** (leitor: “abre o GitHub em outra aba”)
- Lista de repositórios: resumo “Ver os 12 repositórios”
- Procurando: "Procurando suas contas no GitHub…"
- Achou: "Achei e liguei a conta loja-da-ana."
- Não confirmou: "Não deu para confirmar a conta. Se você fechou a página do GitHub no
  meio, é isso mesmo e não é erro: é só tentar de novo. O DERVS só liga a conta depois que o
  GitHub confirma."
- Erro: "Não consegui procurar suas contas agora. Isso não quer dizer que não há — quer
  dizer que não olhei." — botão **Tentar de novo**
- App não registrado: "o aplicativo do GitHub ainda não foi registrado neste servidor"
- Como desligar: "Para desligar uma conta, remova o aplicativo no próprio GitHub, em
  Configurações → Aplicativos. O DERVS não faz isso por aqui de propósito: tirar o acesso é
  decisão de quem deu o acesso."

### Cartão "Seus sites"

- Título: **Seus sites**
- Frase: "Cole o endereço de um site. O DERVS confere na hora se ele responde, antes de
  guardar."
- Rótulo do campo: **Endereço do site** · exemplo: https://clinica-agenda.com.br
- Botão: **Conferir o site** (carregando: **Conferindo…**; depois de 8 s: “Ainda
  conferindo… alguns sites demoram.”)
- Pergunta: "De qual projeto é este site?" (já escolhido o mais parecido)
- Botões: **Guardar este site** · **Guardar mesmo assim** · **Tentar de novo**
- Marcas: “respondeu” · “não respondeu” · “não deu para conferir” · “não medi”
- Respondeu: "O site respondeu (código 200) em 0,4 segundo."
- Dicionário de motivos de não responder (o texto exato do servidor, se vier, entra por
  `textContent` entre parênteses):
  - nome não existe: "Não achei esse endereço. Confira se você digitou certo."
  - demorou: "O site não respondeu em 10 segundos."
  - certificado: "O certificado de segurança do site não é válido."
  - erro do servidor: "O site respondeu com erro do lado dele (código 502)."
  - recusado: "O site recusou a conexão."
  - qualquer outro: "Não consegui falar com o site."
- Não deu para conferir: "Não consegui conferir este site agora. Isso não quer dizer que
  ele esteja fora do ar — quer dizer que não olhei."
- Rede interna: "Este endereço é de uma rede interna. O painel só confere sites públicos.
  Use o endereço que o público acessa."
- Endereço mal escrito: "Escreva o endereço completo, começando por https://, por exemplo
  https://loja-da-ana.com.br."
- Sem projeto: "Ainda não há projetos no painel para ligar a este site. Conecte um
  computador primeiro."
- Sugestão: "Sugestão: loja-da-ana parece estar em https://loja-da-ana.com.br" — **Usar
  este** · **Ignorar**
- Guardado: "Guardei https://loja-da-ana.com.br para o projeto loja-da-ana." · erro: "Não
  consegui guardar agora. O que você digitou continua no campo."
- Linha de site: “respondeu 200 · medido há 3 minutos” / “não respondeu · medido há 3
  minutos” / “ainda não medi” · botão **Tirar**
- Vazio: "Nenhum site cadastrado ainda. Cole o endereço acima para o DERVS conferir se ele
  responde." · falha de leitura: "Não consegui ler os sites desta conta. Isso não quer dizer
  que não há — quer dizer que não olhei."
- Opções avançadas: resumo **Opções avançadas** · campo **Servidor** (ajuda: "Onde o site
  roda. Se você não tem nenhum cadastrado, o DERVS cria um chamado “Meus sites”.") · campo
  **Padrão de subdomínio** (ajuda existente: "Se os projetos deste servidor seguem um padrão
  de endereço, o DERVS testa sozinho e sugere o preenchimento — você ainda confirma antes de
  qualquer coisa ser gravada.")
- Dois ou mais servidores: campo visível **Em qual servidor?**, sem opção pré-escolhida.
- Nota: "O DERVS nunca pede chave de acesso ao servidor. O endereço público basta para
  conferir se ele responde. Endereço de rede interna é recusado de propósito."

### Faixa de página desatualizada

- Linha 1 (forte): **Esta página ficou desatualizada.**
- Linha 2: "O que você acabou de clicar não foi feito. Recarregue a página para continuar. O que
  você estava digitando pode se perder."
- Botão: **Recarregar**
- Recado do botão clicado, enquanto a faixa está aberta: "Não foi feito. Veja o aviso no
  alto da página."

### Recados do DERVS-VOZ

- Resumo do `<details>`: **Recados do DERVS-VOZ**. Dentro, os textos que já existem, sem
  mudança.

### Dados de demonstração

Verossímeis e coerentes entre si; nenhuma pessoa real.

- Computador: **PC-ESCRITORIO** (Windows 11, deu notícia há 12 segundos, 7 projetos);
  **NOTEBOOK-SALA** (Windows 10, não dá notícia há 3 horas, 2 projetos).
- Pasta: `C:\Users\Desktop\projetos`.
- Projetos achados: `clinica-agenda`, `loja-da-ana`, `site-padaria-central`,
  `painel-financeiro`, `api-pedidos`, `blog-da-marcia`, `controle-estoque`.
- GitHub: contas `loja-da-ana` (pessoal, mede 5 repositórios, mediu há 4 minutos) e
  `clinica-agenda-org` (organização, mede 12 repositórios, mediu há 11 minutos).
- Sites: https://clinica-agenda.com.br (respondeu 200, medido há 3 minutos),
  https://loja-da-ana.com.br (não respondeu — o site não respondeu em 10 segundos),
  https://padaria-central.com.br (ainda não medi). Servidor: **Meus sites**.
- Código de autorização: **K7M4-2QXP**.

## assets

Ordem obrigatória cumprida: **gerar por código primeiro; foto só para o que é do mundo real.**
Nesta entrega **nenhuma fotografia faz falta** e **nenhuma imagem vem de banco**. Não há
vídeo, não há GIF, não há imagem de terceiro.

| Peça | O que é | Como nasce | Origem e licença |
|---|---|---|---|
| Desenho do aviso do Chrome (passo 1) | Esquema simples de uma barra de downloads com dois botões, **Manter** destacado | SVG escrito à mão, inline num `<template>` em `index.html` (mesmo padrão do modelo de selo que já existe); traços em `--borda-forte`, preenchimentos em `--fundo-elevado`, destaque em `--acao` | Gerado no repositório. Nosso, sem licença de terceiro |
| Desenho do aviso do Windows (passo 3) | Esquema de uma caixa de aviso com um escudo e o botão **Executar** destacado | SVG inline, mesmo método; o escudo é desenhado com **glifo `[!]` e traço**, não com a cor vermelha do Windows | Gerado no repositório. Nosso |
| Desenho da janela de escolher pasta (passo 5) | Esquema de uma lista de pastas com uma selecionada e o botão **OK** | SVG inline, mesmo método | Gerado no repositório. Nosso |
| Ícones | Nenhum ícone novo; o painel já usa o glifo textual da `.marca` (`[OK]`, `[X]`, `[···]`) | Texto | Fonte IBM Plex, licença SIL OFL 1.1, já registrada em `assets/CREDITOS.md` |

Observações:
- Os desenhos são **esquemas ilustrativos**, não capturas de tela do Windows nem do Chrome:
  não reproduzem marca nem interface de terceiros, só mostram "onde clicar". Cada um leva
  `aria-hidden="true"` e o passo ao lado descreve a mesma coisa em texto, de modo que quem
  não vê o desenho não perde informação. Legenda curta sob cada um: "Desenho ilustrativo. O
  seu computador pode mostrar algo um pouco diferente."
- Inline em vez de arquivo em `assets/` **de propósito**: `assets/` só serve os arquivos que
  existiam quando o servidor subiu, e arquivo novo exigiria reiniciar `servir.py` e mexer
  na lista de caminhos exatos. Inline não toca nessa trava.
- Todos os desenhos usam só `var(--…)` ou `currentColor`; nenhum valor de cor literal. Isso
  mantém os dois temas e o vigia da paleta verdes.
- `assets/CREDITOS.md` ganha uma linha "Desenhos de ajuda da tela Conectar — gerados no
  repositório, sem licença de terceiro" junto com a mudança.
- **Imagem por passo e "o que isso faz?"**: o spec lista os dois como cortáveis se apertar.
  Se cortar a imagem, o texto de cada passo continua completo e a entrega continua válida; o
  aviso do Windows com o desenho (decisão 4 do portão 1) é o último a cortar.

## estrategia_de_aquisicao

O DERVS é uma **aplicação autenticada**, não uma página pública: ninguém "chega" por busca, e
a tela Conectar não tem nada a ser descoberto por quem não entrou. Nenhuma mudança de
indexação nesta entrega. Fica como está: `<meta name="robots" content="noindex, nofollow">`
em `index.html`, o cabeçalho `X-Robots-Tag` e o `/robots.txt` que o servidor já responde.
Nenhuma imagem de compartilhamento, nenhum `sitemap`, nenhum dado estruturado.

**Como o dono chega à tela.** Por três caminhos, todos já existentes:

1. No menu de quatro itens, **Conectar** (`#/conectar`). É o caminho normal.
2. Pelo painel vazio ("Conectar um projeto") e pelos avisos de "sem dados" que apontam para
   cá, quando um projeto está sem medição por falta de computador ligado.
3. Pelo link que o arquivo baixado abre no navegador:
   `https://dervs.com.br/#/conectar?autorizar=<código>`. **[ponto para o plano]** O painel
   está atrás de entrada; quem abre esse link sem sessão precisa cair na entrada e **voltar
   a este mesmo endereço** depois de entrar. O spec não trata disso; sem a volta, o dono
   entra, vê o painel e não encontra o pedido que estava esperando.

**O UM próximo passo visível, em 360px e sem rolagem, em cada tela:**

| Situação | Próximo passo único |
|---|---|
| Conectar, sem nada ligado | **Conectar este computador** (botão do primeiro cartão) |
| Conectar, computador ligado | A lista de projetos achados e a chave **Mostrar no painel**; o botão fica secundário |
| Bloco Autorizar, pedido válido | **Autorizar este computador** |
| Bloco Autorizar, pedido vencido | **Voltar para Conectar** |
| Cartão GitHub, sem conta | **Conectar conta do GitHub** |
| Cartão Seus sites, sem site | O campo **Endereço do site** (com **Conferir o site** ao lado) |
| Página desatualizada | **Recarregar** |
| Qualquer erro de leitura | **Tentar de novo** |

**Contradições e lacunas encontradas entre o spec e o `design.md` aprovado, listadas sem
resolver (decisão de produto é do dono):**

1. O design aprovado diz que os tokens `--estado-*` aparecem **só** dentro do selo e do que
   ele abre. O código atual já os usa na `.marca` dos cartões de ligação e no `.freio`
   (`--estado-atencao`). Esta entrega **mantém** a `.marca`, porque o spec manda reaproveitar
   o cartão; a faixa nova de página velha **não** usa `--estado-*`. Fica registrado que a
   regra 1 da direção já é violada pela `.marca` e pelo `.freio` antes desta entrega.
2. O design aprovado define o fluxo de Conectar projeto como "marcar as pastas que entram e
   confirmar" (escolha **antes** de entrar). O spec inverte: tudo entra e a chave "mostrar
   no painel" **esconde depois**. Seguido o spec; o texto explica que esconder não apaga.
3. O design aprovado exclui GitHub e servidor da tela Conectar ("vão para a Fatia 2"); eles
   já estão nela desde "Conectar em três portas". Nada a fazer; só registro.
4. O spec não diz: o nome do arquivo baixado (assumido **`conectar-dervs.cmd`**), o formato
   do código curto (assumido `XXXX-XXXX`), o que fazer com dois ou mais servidores
   (resolvido na Tela E), o que a chave faz num repositório que não é projeto (resolvido na
   Tela C), se há botão de **recusar** um pedido de autorização (decidido que não há, só o
   aviso), e o que acontece com o recado do botão clicado quando a faixa de página velha
   abre (Tela D).
