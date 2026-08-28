# Design — DERVS

Fase 3 da esteira, escrita em 26/08/2026. Contrato desta fase: o `briefing.md` (aprovado
pelo dono) e o `spec.md`. Onde os dois divergem, vale o `spec.md`, que já registrou a
divergência em `contradicoes_resolvidas`.

Método: painel adversarial. Três diretores de arte produziram três direções **sem ver o
trabalho um do outro** — é isso que impede as três de chegarem no mesmo lugar. O juiz
escolheu uma e enxertou o que as outras duas tinham de melhor. As recusadas ficam
registradas com o motivo, para a discussão não recomeçar do zero daqui a um mês.

O dono foi consultado (portão 3) e devolveu a decisão ao juiz, com as palavras *"quero o
melhor que você puder criar"*. A escolha abaixo é minha, e o motivo está escrito.

---

## direcao_visual_escolhida

### Vencedora — **Torre de Controle**

> **A sensação:** olhar para o painel de uma torre de controle. Cada projeto é uma pista,
> cada selo é um instrumento, e nada pisca sem motivo — se está quieto, é porque está tudo
> bem, e você confia nisso porque a tela nunca decora.

Densidade alta, sem sombra em lugar nenhum, quinas quase retas (3px), hierarquia feita só
por tipografia, borda de 1px e troca de fundo. Letra técnica de interface no texto, letra
monoespaçada **só nos números medidos**, com algarismos de largura fixa para que os dados de
projetos diferentes alinhem em coluna.

**Por que ela ganhou, contra os quatro critérios do juiz:**

1. **Serve aos dois usuários do Analista, na mesma tela.** Thiago decide o produto e não
   opera terminal: recebe selo com forma, cor e **rótulo escrito**. André programa: recebe a
   densidade e o dado cru logo abaixo, sem precisar de outra tela. Selo na frente, prova
   atrás — literalmente o que o briefing pediu.
2. **Sustenta a tela mais chata, não só a mais bonita.** A tela que decide o produto não é a
   inicial: é a lista de 23 critérios de um projeto, e a tela de erro do agente. Uma direção
   que só funciona na home é maquiagem.
3. **Sobrevive a 360px** porque foi desenhada densa desde o começo, e não espremida depois.
4. **O contraste fecha em todos os pares** — medido, não estimado (tabela adiante), e o
   único par que reprovou foi corrigido antes de este documento existir.

E ela responde ao pedido literal do dono — *"cara de DEV/Hacker"* — pelo lado do
instrumento, não pelo lado do clichê. O painel parece uma ferramenta de precisão, não um
plano de fundo de filme.

### O problema do verde — a regra dura deste projeto

O dono pediu preto, branco e verde. A trava que atravessa o produto inteiro é esta:

> **O verde é o estado saudável, não a cor da marca.**

Se o verde virar cor genérica de destaque — botão, link, cabeçalho, logotipo —, a tela fica
verde inteira e o selo verde de "projeto saudável" para de significar alguma coisa. O dia em
que o dono mais precisa que o verde grite "está tudo bem" seria o dia em que o verde já
gritou o dia inteiro por outro motivo.

**A solução:** quem carrega identidade e ação é o **preto/branco** — o par de contraste
máximo, invertido entre os temas. `--acao` é quase-preto no tema claro e quase-branco no
escuro. Botão primário, link, foco de teclado, cabeçalho, ícone de navegação: tudo em
`--acao`. Nunca em verde.

**Isto é regra de implementação, não de estilo.** Componente novo que pedir "uma cor de
destaque" recebe preto/branco. Está escrito como critério verificável em `telas`.

**Uma tensão que declaro em vez de esconder:** a spec exige quatro estados de selo, e dois
deles (atenção, quebrado) não cabem dentro de preto/branco/verde. A resolução: **preto,
branco e verde são a paleta de marca e interface; âmbar e vermelho são vocabulário de
alarme.** Aparecem só dentro do selo e do que o selo abre — nunca em botão, nunca em
navegação. Um instrumento de aviação também não é bicolor: a régua é preto e branco, e o
alarme é âmbar e vermelho, sem que ninguém confunda isso com a marca da aeronave.

### Enxertos das direções recusadas

O juiz não escolheu um pacote fechado. Três peças das perdedoras entram na vencedora:

| Enxerto | De onde veio | Por que entra |
|---|---|---|
| **Lista de linha cheia, de borda a borda, com zero vão entre linhas e um traço de 1px separando** — em vez de cartões flutuando com espaço entre eles | Alvorada | Resolve o conflito entre respiro e velocidade de leitura: o espaço generoso vive *dentro* de cada linha, nunca *entre* elas. O olho varre como sumário de jornal. Cabem 10 projetos em 360px sem rolagem |
| **Uma frase de resumo no topo, em linguagem humana** — "8 de 10 projetos estão bem" | Alvorada | Responde a pergunta das cinco da manhã antes de a pessoa ler qualquer número. É a promessa nº 1 do briefing ("eu confio no que está no ar") virando uma linha de texto |
| **O glifo textual dentro do selo** — `[OK]`, `[!]`, `[X]`, `[···]` | READOUT | Sobrevive a impressão em preto e branco, a captura de tela sem cor e a daltonismo total. Cor + forma + glifo + rótulo: quatro sinais, nenhum indispensável sozinho |

### Recusadas, e por quê

**Alvorada** — *"o jornal dobrado na mesa"*. Serifa editorial na manchete, muito respiro,
notícia ruim dada com calma. **Recusada por duas razões.** A primeira é o pedido literal do
dono: ele escreveu "cara de DEV/Hacker", e a serifa de jornal é o ponto mais distante disso
que as três direções alcançaram — escolhê-la seria eu trocando o gosto dele pelo meu sem
avisar. A segunda é de função: a serifa aparece uma vez por tela, o que a torna um enfeite
caro (uma família tipográfica inteira carregada para uma linha) numa aplicação cuja tela
mais importante é uma tabela. **O que ela tinha de melhor foi enxertado** — a linha cheia e
a frase de resumo, que são as duas melhores ideias das três direções.

**READOUT** — *"a régua de instrumento binária"*. Tudo em monoespaçada, alto contraste,
selos escritos. **Recusada por um defeito verificável e um risco.** O defeito: ela afirma
caber 40 caracteres por linha em 360px, e não cabe — monoespaçada de 15px ocupa cerca de
9px por caractere, e 360px menos o respiro lateral dão ~34 caracteres. A conta que sustenta
o layout inteiro dela está errada, e corrigi-la aperta a tela. O risco: monoespaçada em
texto corrido cansa, e o produto tem prosa de verdade — o motivo de cada alerta, a idade de
cada pendência, o que o Claude fez. Isso pesa contra o usuário que não é programador.
**O que ela tinha de melhor foi enxertado:** o glifo textual no selo, e a regra explícita de
que as quatro cores de estado não aparecem em nenhum outro lugar do sistema.

**As três convergiram num ponto, e isso não é falta de ousadia:** nenhuma usou verde como
cor de marca. Três agentes cegos entre si chegando à mesma solução para a trava mais difícil
é a evidência mais forte que esta fase produziu de que a regra está certa.

---

## tokens

Tokens antes de tela, sempre. Sem isto cada tela nasce com um cinza diferente e ninguém
conserta depois sem refazer tudo.

### Cor

Todos os tokens existem nos dois temas — **nenhuma cor é definida só dentro de um deles**,
que é critério de aceitação do briefing. A implementação declara a paleta clara completa em
`:root`, redefine os valores sob `@media (prefers-color-scheme: dark)` guardado por
`:root:not([data-theme="light"])`, e redefine de novo sob `:root[data-theme="dark"]`, para
que o botão de tema vença nos dois sentidos.

| Token | Papel | Tema claro | Tema escuro |
|---|---|---|---|
| `--fundo` | fundo da página | `#FFFFFF` | `#0B0C0B` |
| `--fundo-elevado` | cartão, barra fixa, campo, modal | `#F1F2F0` | `#161816` |
| `--texto` | texto principal | `#101210` | `#F2F3F1` |
| `--texto-suave` | metadado, carimbo de hora, rótulo | `#5B605A` | `#9BA098` |
| `--borda` | divisor entre linhas — **decorativo** | `#D9DBD8` | `#2B2D2A` |
| `--borda-forte` | contorno de campo, de selo e de cartão ativo — **carrega significado** | `#8A8F89` | `#676C65` |
| `--acao` | identidade, botão primário, link, anel de foco | `#111310` | `#F2F3F1` |
| `--acao-texto` | texto sobre `--acao` | `#FFFFFF` | `#101210` |
| `--estado-saudavel` | selo verde: traço e texto | `#146B45` | `#34C77E` |
| `--estado-saudavel-fraco` | preenchimento tênue do selo | `#E7F3EC` | `#12241B` |
| `--estado-atencao` | selo âmbar: traço e texto | `#8A5A00` | `#E8A93D` |
| `--estado-atencao-fraco` | preenchimento tênue | `#FBF1DD` | `#2A2110` |
| `--estado-quebrado` | selo vermelho: traço e texto | `#B3261E` | `#FF6B5E` |
| `--estado-quebrado-fraco` | preenchimento tênue | `#FBEAE9` | `#2B1512` |
| `--estado-sem-dados` | selo neutro: traço e texto | `#666B65` | `#8F948D` |

Não existe `--estado-sem-dados-fraco`: o selo neutro é **vazado**, e a ausência de
preenchimento é justamente o sinal que ele precisa dar.

### Regra dura de uso da cor

Quatro regras, todas verificáveis por busca no código:

1. **Os cinco tokens de estado** (`--estado-*`) aparecem exclusivamente dentro do selo e do
   detalhe que o selo abre. Nunca em botão, link, navegação, cabeçalho ou logotipo.
2. **Nenhum valor de cor literal** (`#`, `rgb(`, `oklch(`) fora do bloco de tokens. Cor no
   componente é sempre `var(--…)`.
3. **`--borda` é decorativa** (contraste 1,4:1) e só pode separar itens de uma lista já
   distinguíveis pelo conteúdo. Onde a borda é o único sinal — contorno de campo de
   formulário, do selo, do cartão selecionado — usa-se `--borda-forte` (≥3:1).
4. **Verde nunca é `--acao`.** Se um componente pedir cor de destaque, a resposta é `--acao`.

### Contraste verificado

Medido com a fórmula de luminância relativa da WCAG 2.2, não estimado. O script está em
`docs/esteira/dervs/contraste.py` — rode-o e a conta se refaz; o mínimo é **4,5:1** para texto e **3:1**
para contorno que carrega significado.

| Par | Claro (sobre fundo / sobre cartão) | Escuro (sobre fundo / sobre cartão) |
|---|---|---|
| `--texto` | 18,82 / 16,76 | 17,60 / 16,04 |
| `--texto-suave` | 6,43 / 5,73 | 7,35 / 6,69 |
| `--estado-saudavel` | 6,52 / 5,81 | 8,97 / 8,17 |
| `--estado-atencao` | 5,93 / 5,28 | 9,49 / 8,65 |
| `--estado-quebrado` | 6,54 / 5,82 | 7,01 / 6,39 |
| `--estado-sem-dados` | 5,45 / 4,85 | 6,33 / 5,77 |
| `--acao-texto` sobre `--acao` | 18,68 | 16,90 |
| `--borda-forte` sobre fundo | 3,30 | 3,65 |

**Duas correções que a medição forçou, e que nenhuma das três direções tinha visto:**

- O cinza de "sem dados" proposto (`#8A8F89` / `#6E736D`) dava **4,31:1** sobre o cartão no
  tema claro — reprovava. Escurecido para `#666B65`, que fecha em 4,85:1. O estado que
  informa "não sei" era o menos legível da tela, o que é exatamente o pior lugar para uma
  falha de contraste.
- A borda única de `#D9DBD8` dá **1,39:1**. As três direções apoiavam toda a hierarquia
  nela, sem sombra nenhuma. Daí a divisão em `--borda` (decorativa) e `--borda-forte`
  (com significado), com valores medidos.

### Tipografia

| Uso | Pilha |
|---|---|
| Interface e texto corrido | `"IBM Plex Sans", "Segoe UI", system-ui, -apple-system, sans-serif` |
| Número medido, carimbo de hora, contagem, identificador de commit | `"IBM Plex Mono", "Cascadia Code", ui-monospace, Consolas, monospace` |

Fora da monoespaçada, todo número usa `font-variant-numeric: tabular-nums` — sem isso,
"10 commits" e "3 commits" desalinham em coluna e a tabela deixa de ser varrível.

| Token | Tamanho | Peso | Altura de linha | Papel |
|---|---|---|---|---|
| `--fs-etiqueta` | 0,6875rem | 600, rastreio +0,04em | 1,2 | rótulo em caixa alta, cabeçalho de coluna |
| `--fs-metadado` | 0,8125rem | 400 | 1,4 | carimbo, metadado, texto suave |
| `--fs-corpo` | 0,9375rem | 400 | 1,5 | corpo padrão |
| `--fs-destaque` | 1,0625rem | 500 | 1,3 | nome do projeto, item ativo |
| `--fs-titulo` | 1,25rem | 600 | 1,25 | título de seção |
| `--fs-pagina` | 1,75rem | 600 | 1,2 | cabeçalho da página |

A escala para em 1,75rem de propósito. Nada de 2,5rem: é painel de instrumento, não página
de venda. Tamanho grande aqui custa projetos visíveis por rolagem.

### Espaçamento, forma e densidade

- **Espaço**, na grade de 4px: `--e1: 4px` · `--e2: 8px` · `--e3: 12px` · `--e4: 16px` ·
  `--e6: 24px` · `--e8: 32px` · `--e12: 48px`.
- **Raio:** `--raio: 3px` em tudo — cartão, botão, campo, selo. Quina quase reta,
  deliberadamente não amigável. Nada no produto passa de 3px.
- **Sombra: nenhuma, em lugar nenhum.** Separação vem de `--borda`/`--borda-forte` e da
  troca de `--fundo` para `--fundo-elevado`. Sombra sugere luz e profundidade física, que é
  linguagem calorosa; e no tema escuro ela simplesmente não se enxerga.
- **Densidade alta:** linha de lista com `--e3` de respiro vertical e `--e4` horizontal.
  Meta verificável: **em 360×640, a linha de projeto mostra selo, nome, motivo e carimbo
  juntos** — o que houve se lê sem abrir nada. Na prática isso dá 5 a 7 projetos por tela.

  > **Correção de 28/08/2026, decidida pelo dono.** Até aqui a meta era "10 projetos
  > visíveis sem rolagem em 360×640", e a etapa 14 provou por medição que ela não cabe
  > junto com o motivo na linha (90 a 113 px por linha, mais ~350 px de frase de resumo,
  > régua e ação recomendada). O número foi trocado, não a densidade: dez nomes com um
  > selo ao lado obrigam a abrir cada projeto para descobrir o que aconteceu — trocam um
  > clique economizado na rolagem por dez gastos na investigação. Rolar não é defeito;
  > abrir dez telas é. A contagem deixou de ser critério.
- **Foco de teclado:** anel de 2px em `--acao` com `--e1` de afastamento, sempre visível,
  nunca removido. É a única "sombra" do sistema, e ela é funcional.
- **Movimento:** só transição de cor e de opacidade, no máximo 150ms. Nenhuma entrada
  animada de conteúdo. Tudo respeita `prefers-reduced-motion: reduce`. A tela é lida com
  pressa; movimento aqui atrapalha em vez de agradar.

### Os quatro estados do selo

Quatro sinais independentes — **cor, forma, glifo e rótulo escrito**. Nenhum é
indispensável: a tela continua legível em preto e branco, para quem não distingue cores, e
para quem usa leitor de tela.

| Estado | Forma | Preenchimento | Glifo | Rótulo | O que quer dizer |
|---|---|---|---|---|---|
| **Saudável** | círculo cheio | `--estado-saudavel-fraco`, traço sólido 1px | `[OK]` | `saudável` | tudo o que dá para medir foi medido e passou |
| **Atenção** | triângulo cheio | `--estado-atencao-fraco`, traço sólido 1px | `[!]` | `atenção` | mede, passa, mas alguma coisa vai piorar |
| **Quebrado** | quadrado cheio | `--estado-quebrado-fraco`, traço sólido **2px** | `[X]` | `quebrado` | mede e reprova. É o único com peso de traço diferente |
| **Sem dados** | losango **vazado** | nenhum, traço **tracejado** 2px | `[···]` | `sem dados` | não foi medido. Não é bom nem ruim: é ausência |

**O quarto estado é obrigatório e é o mais importante do produto.** Sem ele, um projeto sem
camada coletada apareceria verde — verde por ausência de pendência, não por saúde. É a
mentira por omissão já catalogada na memória deste projeto, e é a razão de o selo neutro ser
o único vazado e tracejado: ele *parece* vazio de informação, que é a verdade que precisa
comunicar.

O selo é sempre um botão. Clicar abre a prova que o gerou, com o mesmo par forma+cor+glifo
repetido lá dentro.

---

## telas

Seis telas na Fatia 1, mais três comportamentos que atravessam todas. Cada uma declara os
estados **vazio, carregando e erro** — que é onde as interfaces mentem — e o que acontece
em 360px.

**Regra de layout, das seis:** uma coluna só até 720px; duas colunas acima disso, nunca
três. Largura máxima de leitura em 1100px. Nada de painel lateral fixo: em 360px ele viraria
gaveta, e gaveta escondida é onde informação vai morrer.

### 1. Entrar

A porta. Login com segundo fator obrigatório, cadastro público desligado.

- **Composição:** logotipo, campo de e-mail, campo de senha, botão "Entrar". Nada mais —
  sem "criar conta", sem "entrar com o GitHub", porque nenhum dos dois existe nesta fatia.
- **Segundo fator:** segunda etapa, depois da senha correta, com seis campos de um dígito
  que aceitam colar o código inteiro de uma vez.
- **Carregando:** o botão vira "Entrando…" e fica desabilitado. Sem roda girando.
- **Erro:** mensagem única abaixo do botão, em `--estado-quebrado`, **sem dizer qual dos
  dois campos errou** (isso entregaria quais e-mails existem). O campo de senha esvazia,
  o de e-mail não.
- **Erro de segundo fator:** diz quantas tentativas restam. Esgotadas, a sessão de login
  cai inteira e volta ao primeiro passo.
- **360px:** campos de largura total, `--e6` de respiro lateral. Os seis campos do código
  têm 40px cada, com `--e2` entre eles — cabem em 328px com folga.
- **Verificável:** `curl -si https://dervs.com.br/api/projetos` sem sessão devolve 401 ou
  302, nunca dado.

### 2. Painel

A tela das cinco da manhã. É esta que decide se o produto vale.

**Ordem de leitura, de cima para baixo:**

1. **A frase.** "8 de 10 projetos estão bem." Em `--fs-pagina`. Responde a pergunta antes de
   qualquer número. Se houver quebrado, a frase muda de sujeito: "1 projeto quebrado, 9 bem."
2. **A régua de contagem.** Quatro contadores, um por estado, cada um com forma, glifo e
   rótulo. São filtros: tocar em "quebrado" reduz a lista.
3. **A lista.** Linha cheia de borda a borda, sem vão entre linhas, separadas por 1px de
   `--borda`. Cada linha: selo · nome do projeto · o motivo em uma frase · o carimbo da
   última medição.
4. **Ordem:** quebrado, atenção, sem dados, saudável. Dentro de cada grupo, o mais recente
   primeiro. **O saudável fica por último de propósito** — quem está bem não precisa de
   atenção.

- **Vazio (nenhum projeto conectado):** ocupa a tela inteira, não é uma linha triste. Diz o
  que vai aparecer ali, e o único próximo passo é "Conectar um projeto".
- **Vazio por filtro:** "Nenhum projeto quebrado agora." com "Ver todos".
- **Carregando:** esqueleto com a forma exata das linhas — mesma altura, mesmo número de
  linhas da última visita — para a tela não saltar quando o dado chegar. Nunca uma roda
  girando no meio da tela.
- **Erro (o servidor não respondeu):** a lista anterior **continua na tela, acinzentada**,
  com uma faixa em cima: "Não conseguimos atualizar. Mostrando a medição de 08:14." Nunca
  esvaziar a tela por causa de uma falha de rede — tela vazia é indistinguível de "você não
  tem projetos".
- **360px:** o motivo quebra em até duas linhas e corta com reticências na terceira; o
  carimbo desce para a linha de baixo do selo. **O motivo fica** — é ele que responde "o
  que houve" sem um clique. Ver a correção de 28/08/2026 na seção de densidade.
- **Verificável:** o `ajudei-saude` aparece vermelho no quesito de publicação, com os 10
  commits não publicados desde 11/08/2026.

### 3. Projeto — a prova do selo

O selo é uma afirmação; esta tela é a conta que a sustenta. **Nenhum número aparece aqui sem
o carimbo de quando foi medido.**

- **Topo:** nome, selo grande, e a frase do porquê daquele selo.
- **Corpo:** a lista de critérios, um por linha, cada um com seu próprio veredito nos mesmos
  quatro estados. Agrupados por camada (código, GitHub, servidor, máquina local).
- **Critério sem veredito:** o que depende do git e não pôde ser lido aparece como **sem
  dados**, com o texto "não consegui medir" — nunca "não se aplica". A diferença entre "não
  há" e "não perguntei" é a espinha dorsal deste produto.
- **Cada critério abre** para mostrar o dado cru: a saída do comando, o commit, o arquivo.
  Fechado por padrão. Selo na frente, prova atrás.
- **Vazio:** projeto recém-conectado, ainda não medido. "Primeira medição em andamento.
  Deve levar menos de um minuto."
- **Carregando:** só o critério que está sendo remedido pisca; o resto da tela fica parada.
- **Erro:** o critério que falhou mostra "não consegui medir" e o motivo em uma linha.
  Um critério que falha **não derruba os outros**.
- **360px:** os critérios viram lista vertical; a camada vira um cabeçalho pegajoso que
  acompanha a rolagem.

### 4. Conectar projeto

**A descoberta de desenho desta tela:** o navegador não enxerga o disco do usuário, e o
DERVS roda numa VPS. Quem lista as pastas é o **agente local**. Logo, esta tela não é um
seletor de arquivos — é uma lista que o agente propõe.

- **Fluxo:** escolher a máquina (se houver mais de uma) → o agente devolve as pastas com
  `.git` que encontrou → marcar as que entram → confirmar.
- **Sem máquina pareada:** esta tela não abre. Manda para "Parear máquina" e explica por quê
  em uma frase.
- **Vazio (o agente não achou nada):** "Não encontramos nenhuma pasta com Git em <caminho>."
  com um campo para digitar o caminho manualmente.
- **Carregando:** "Procurando pastas com Git nesta máquina…" com o nome da máquina.
- **Erro:** "O agente desta máquina não respondeu em 30 segundos." com "Tentar de novo".
- **360px:** lista de uma coluna, caixa de marcação de 24px (alvo de toque de 44px com o
  respiro), botão de confirmar fixo no rodapé.
- **Fora desta fatia, por decisão da fase 2:** conectar conta do GitHub e conectar servidor.
  As duas coletam segredo de terceiro, e a arquitetura de segredo é portão de risco da fase
  6. Construir a gaveta antes do cofre. Vão para a Fatia 2.

### 5. Máquinas

Onde se pareia o agente local e se vê se ele está vivo.

- **Parear:** um código de seis dígitos em `--fs-pagina`, monoespaçado, com o tempo restante
  ao lado ("vale por 9:43"). Abaixo, o comando exato para colar na máquina.
- **Lista de máquinas:** nome, sistema, visto por último, e quantos projetos ela reporta.
- **Expirado:** o código fica riscado e um botão "Gerar outro código" toma o lugar.
- **Vazio:** "Nenhuma máquina conectada. O DERVS precisa de um agente rodando no seu
  computador para ver Docker, Git e as portas."
- **Carregando:** o código só aparece pronto; nunca meio código na tela.
- **Erro:** "Não conseguimos gerar o código agora." com "Tentar de novo".
- **360px:** o código cabe folgado; o comando de instalação rola na horizontal **dentro da
  própria caixa**, com botão de copiar — a página nunca rola de lado.

### 6. Alerta, e o arquivamento permanente

Correção decidida na fase 2: hoje silenciar é por 24 horas, sempre — logo, projeto que o
dono arquivou de propósito volta a cutucar todo dia, para sempre. Isso treina a pessoa a
ignorar a lista inteira.

- **Cada alerta tem três ações:** "Resolver", "Adiar 24h" e **"Isto está certo assim"**.
- **A terceira é permanente**, por regra e por projeto. Pede um motivo em uma linha —
  não para auditar, mas para o próprio dono lembrar em três meses por que decidiu aquilo.
- **Onde vão parar:** uma seção "Arquivados" no fim da tela do projeto, com o motivo e a
  data, e um botão para desarquivar. Nunca some sem deixar rastro.
- **Quatro regras nascem fora do cálculo do selo** — `abandonado`, `caso_vazio`,
  `grafo_velho` e `memoria_crlf` —, porque são constatação sem ação, ou convenção interna
  que não existe para "qualquer usuário".
- **Erro ao arquivar:** o alerta volta visualmente para o estado anterior, com "Não
  conseguimos arquivar. Tente de novo." Nada de sumir da tela e reaparecer depois.

### Comportamento transversal A — quando o agente local some

A mentira mais provável do produto, e a regra vem direto da spec. **Ausência de agente
produz ausência de camada, nunca camada vazia.** Nunca escrever "nenhum container rodando"
quando a verdade é "não perguntei".

| Tempo sem notícia | O que a tela faz |
|---|---|
| menos de 3 min | nada |
| 3 a 15 min | faixa âmbar no topo; os dados locais ficam acinzentados **com o carimbo da última medição** |
| mais de 15 min | os critérios que dependem da máquina viram **sem dados**; os de GitHub seguem, porque o servidor os mede sozinho |
| mais de 24 h | a máquina vai para "Desconectadas". **Nenhum dado é apagado** |

### Comportamento transversal B — tema claro e escuro

Três estados: escolha explícita clara, escolha explícita escura, e "seguir o sistema"
(o padrão). O botão de tema percorre os três nesta ordem e diz em qual está. A escolha vive
no navegador de quem escolheu.

**Critério verificável:** nenhuma cor tem sua única definição dentro de um bloco de tema, e
o `body` recebe fundo explícito do token — nunca transparente.

### Comportamento transversal C — 360px

Nada de rolagem horizontal na página, nunca. Conteúdo largo — tabela de critérios, saída de
comando, diff — rola **dentro do próprio contêiner**, com `overflow-x: auto`. Alvo de toque
mínimo de 44×44px. Meta verificável do briefing: em 360px, o selo de cada projeto é legível
sem rolagem lateral.

---

## textos

Todo texto visível, em português do Brasil. **Nada de inglês na interface** — nem
*dashboard*, nem *loading*, nem *deploy*, nem *deletar*.

### Vocabulário fixo — a mesma coisa tem sempre o mesmo nome

| Diga | Nunca |
|---|---|
| painel | dashboard |
| publicar / publicação | deploy, deployar |
| verificação automática | CI, pipeline |
| medição / medir | scan, coleta, sync |
| máquina | host, node, runner |
| agente | daemon, worker |
| pendência | issue, task, débito |
| entrar / sair | login, logout, sign in |
| excluir | deletar |
| carregando | loading |
| commit | (mantém — é o nome que o dev usa; traduzir confundiria) |

### Os quatro estados, escritos

- **saudável** — "Tudo o que dá para medir passou."
- **atenção** — "Funciona, mas alguma coisa vai piorar."
- **quebrado** — "Alguma coisa reprovou agora."
- **sem dados** — "Não consegui medir." *(nunca "não se aplica", nunca "OK")*

### Frase de resumo do painel, em cada caso

| Situação | Texto |
|---|---|
| tudo bem | "Os 10 projetos estão bem." |
| alguns em atenção | "8 de 10 projetos estão bem. 2 pedem atenção." |
| algum quebrado | "1 projeto quebrado, 9 bem." |
| há projeto sem dados | "…e 1 não foi medido." (emendado na frase acima) |
| nenhum projeto | "Você ainda não conectou nenhum projeto." |
| agente mudo | "Mostrando a última medição, de 08:14. O agente desta máquina não reporta há 22 minutos." |

### Botões — cada um diz o que acontece

`Entrar` · `Conectar um projeto` · `Medir agora` · `Ver o que gerou este selo` ·
`Resolver` · `Adiar 24 horas` · `Isto está certo assim` · `Desarquivar` ·
`Gerar outro código` · `Copiar comando` · `Tentar de novo` · `Ver todos` ·
`Parar` · `Sair`

Nada de `OK`, `Enviar`, `Confirmar` ou `Cancelar` solto.

### Telas vazias — dizem o que vai aparecer e como fazer aparecer

- **Painel:** "Nenhum projeto conectado ainda. Quando você conectar, cada projeto vira uma
  linha aqui com um selo dizendo se está saudável, se pede atenção ou se quebrou." →
  *Conectar um projeto*
- **Máquinas:** "Nenhuma máquina conectada. O DERVS precisa de um agente rodando no seu
  computador para enxergar Docker, Git e as portas. Sem ele, só dá para ver o que está no
  GitHub." → *Parear uma máquina*
- **Arquivados:** "Nada arquivado. Quando você disser 'isto está certo assim' para um
  alerta, ele fica guardado aqui, com o motivo e a data."
- **Filtro sem resultado:** "Nenhum projeto quebrado agora." → *Ver todos*

### Erros — dizem o que fazer, não o que houve

| Situação | Texto |
|---|---|
| e-mail ou senha errados | "E-mail ou senha não conferem." *(sem dizer qual dos dois)* |
| código de seis dígitos errado | "Código incorreto. Restam 2 tentativas." |
| tentativas esgotadas | "Tentativas esgotadas. Entre de novo." |
| servidor mudo no painel | "Não conseguimos atualizar. Mostrando a medição de 08:14." |
| agente não respondeu | "O agente desta máquina não respondeu em 30 segundos." → *Tentar de novo* |
| pasta sem Git | "Não encontramos nenhuma pasta com Git em C:\\Users\\Desktop\\source." |
| falhou ao arquivar | "Não conseguimos arquivar. Tente de novo." |
| código de pareamento vencido | "Este código venceu. Gere outro." |
| sem permissão | "Você não tem acesso a este projeto." |

**Nunca:** "Erro 500", "Algo deu errado", "Ops!", "Falha inesperada".

### Confirmação que nomeia o que morre

> **Desconectar o projeto ajudei-saude?**
> O histórico de medições dele sai do DERVS. Sua pasta e seu repositório não são tocados.
> Dá para conectar de novo depois, mas o histórico não volta.
> → *Desconectar* · *Manter conectado*

### Dados de demonstração

Projetos reais deste universo, verossímeis e coerentes entre si. **Nenhum dado de pessoa
real** além dos nomes dos dois donos, que são os próprios usuários.

| Projeto | Selo | Motivo em uma frase | Última medição |
|---|---|---|---|
| `ajudei-saude` | quebrado | "Servidor 10 commits atrás do GitHub desde 11/08." | há 41s |
| `ccvp-painel` | quebrado | "Publica sozinho a cada envio: `deploy.yml` com `on: push`." | há 1min |
| `medconsultoria` | atenção | "Verificação automática vermelha há 3 dias." | há 1min |
| `zacareli` | atenção | "Certificado do site vence em 12 dias." | há 2min |
| `dervs-hub` | sem dados | "Agente não reporta há 22 minutos." | 08:14 |
| `painel-projetos` | saudável | "500 testes passando · publicado há 2 horas." | há 38s |
| `workspace-medconsultoria` | saudável | "Sem pendência aberta." | há 45s |

Máquinas de demonstração: `DESKTOP-THIAGO` (Windows 11, 7 projetos, visto há 41 segundos) e
`vps-ovh-dervs` (Debian 12, 2 projetos, visto há 12 segundos).

### Regras de escrita que valem para todo texto novo

- Frase curta, voz ativa, sem ironia. A pessoa não está admirando o texto: quer sair da tela.
- Número sempre com unidade e referência: "10 commits não publicados desde 11/08", nunca
  "drift: 10".
- Data por extenso curta ("11/08"), hora só quando o minuto importa ("08:14").
- Tempo relativo até 24 horas ("há 41 segundos"), data absoluta depois disso.
- **Nunca afirmar o que não foi medido.** Na dúvida entre "0" e "não sei", escreva "não sei".

---

## assets

Ordem de trabalho obrigatória: gerar por código primeiro, procurar foto só depois, e só para
o que é genuinamente do mundo real. **A Fatia 1 não precisa de nenhuma fotografia** — é uma
aplicação atrás de login, feita de texto e de dado.

| Arquivo | O que é | Como nasce | Origem e licença |
|---|---|---|---|
| `assets/logo.svg` | Marca DERVS: as cinco letras em IBM Plex Sans 600, e o `V` construído como um losango vazado — a mesma forma do selo "sem dados". Preto/branco puro, **nunca verde** | SVG escrito à mão, sem dependência | Nosso, feito neste projeto. Sem licença de terceiro |
| `assets/favicon.svg` | O losango vazado sozinho, sem as letras | SVG, com `prefers-color-scheme` embutido para inverter no tema escuro do navegador | Nosso |
| `assets/favicon-180.png` | Ícone de atalho para iOS | Gerado do SVG | Nosso |
| `assets/selos.svg` | Os quatro glifos — círculo, triângulo, quadrado, losango — num único arquivo de símbolos, usados por referência | SVG, `currentColor` para herdar o token de estado | Nosso |
| `assets/og.png` (1200×630) | Imagem de compartilhamento: fundo `#0B0C0B`, o logotipo, a frase "Saiba se dá para confiar no que está no ar", e os quatro selos em fila | Composta em SVG e convertida para PNG na construção | Nosso |
| `assets/CREDITOS.md` | Registro de origem e licença de cada arquivo acima | Escrito junto com o primeiro asset | — |

**Tipografia é o único ativo de terceiro:** IBM Plex Sans e IBM Plex Mono, licença
SIL Open Font License 1.1, uso comercial permitido. **Servidas do nosso próprio domínio,
não de um serviço de fontes** — a aplicação fica atrás de login e não deve fazer pedido a
terceiro em nenhuma tela autenticada. Subconjunto de caracteres latinos, `font-display:
swap`, e `system-ui` como reserva real caso a fonte não carregue.

**Nenhum ícone de biblioteca externa.** Os poucos ícones necessários (engrenagem, seta,
copiar, fechar) saem em SVG de traço de 1,5px, no mesmo peso do resto — biblioteca de ícones
traria centenas de arquivos para usar seis, e traria estilo alheio junto.

### Qual foto realista falta

**Nenhuma, na Fatia 1.** E vale dizer de onde viria o incômodo, para ninguém tentar
resolver com banco de imagem:

- **A página pública de `dervs.com.br` (Fatia 2) vai precisar de uma imagem do produto
  funcionando** — captura de tela do painel real, no tema escuro, 1600×1000, com dados
  verossímeis e sem nada identificável dos donos. **Ela não existe hoje porque o produto não
  existe hoje.** Sai da própria tela quando a Fatia 1 estiver de pé, e é a melhor imagem
  possível: nenhuma foto de banco vende uma ferramenta melhor do que a ferramenta.
- **Não usar foto de banco de "programador no computador".** É o clichê que qualquer
  desenvolvedor reconhece em meio segundo, e comunicaria o oposto do que o produto é.

**Limite honesto, sem rodeio:** não há geração de foto realista nem de vídeo filmado dentro
do Claude Code. Se em alguma fatia futura for preciso uma fotografia de verdade, as opções
são o dono fornecer, um banco gratuito com licença comercial (Pexels, Pixabay, Unsplash,
Openverse — nunca com ligação direta ao arquivo deles), ou a tela assumir a estética
ilustrada. **Nenhuma fatura nasce por iniciativa de agente.**

---

## estrategia_de_aquisicao

**A honestidade primeiro:** na Fatia 1 o cadastro público está desligado por decisão de
segurança, e só duas pessoas entram. Então a aquisição real começa na Fatia 2. O que se faz
agora é a **fundação**, porque ela custa quase nada hoje e é cara de retroencaixar depois:
endereço definido, página pública de uma dobra, marcação correta e as métricas de velocidade
tratadas como critério de aceitação, não como ajuste posterior.

### Como a pessoa chega

O público real do DERVS não busca "portal de desenvolvedor" — a pesquisa da fase 2 achou a
frase *"nenhum dev em sã consciência quer um portal de desenvolvedor"*. Ele busca o problema:
*"saber se o servidor está atrás do GitHub"*, *"monitorar meus projetos"*, *"painel para
projetos pessoais"*, *"ver se a CI está vermelha"*. O texto persegue o problema, não a
categoria.

O diferencial defensável, achado pelo Pesquisador: **não existe ferramenta pronta que
compare o que está publicado com o que está no Git.** É o que a página deve dizer primeiro.

### Por que fica — a única dobra da página pública

Em 360px, acima da rolagem, três coisas e **um só** próximo passo:

- **Para quem é:** "Para quem cuida de muitos projetos sozinho."
- **O que ganha:** "Saiba, em cinco minutos por dia, se dá para confiar no que está no ar."
- **A prova em uma linha:** "O servidor está 10 commits atrás do GitHub desde 11 de agosto.
  Você descobriria isso quando?"
- **Próximo passo, um só:** `Entrar`. Enquanto o cadastro estiver fechado, abaixo dele uma
  linha discreta: "Ainda em construção, para dois usuários."

Página com cinco chamadas de igual peso não tem nenhuma.

### Marcação

```html
<title>DERVS — saiba se dá para confiar no que está no ar</title>
<meta name="description" content="Painel para quem cuida de muitos projetos sozinho.
  Mostra, num selo por projeto, o que quebrou, o que falta e se o servidor está atrás
  do GitHub.">
<link rel="canonical" href="https://dervs.com.br/">
<meta property="og:type" content="website">
<meta property="og:url" content="https://dervs.com.br/">
<meta property="og:title" content="DERVS — saiba se dá para confiar no que está no ar">
<meta property="og:description" content="Um selo por projeto: saudável, atenção,
  quebrado ou sem dados. E a conta que gerou o selo, sempre com a hora da medição.">
<meta property="og:image" content="https://dervs.com.br/assets/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:locale" content="pt_BR">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0B0C0B">
```

- **A imagem de compartilhamento não é opcional.** No Brasil o tráfego chega por WhatsApp, e
  link sem imagem parece link suspeito.
- **Dados estruturados:** `schema.org/SoftwareApplication`, com
  `applicationCategory: DeveloperApplication`. Sem `AggregateRating` e sem `Offer` — não há
  avaliação nem preço, e inventar qualquer um dos dois é mentira marcada.

### Achabilidade, e a parte que a maioria erra

- `sitemap.xml` com a página pública, e **só ela**.
- `robots.txt` liberando `/` e **bloqueando `/painel`, `/projeto`, `/maquinas`, `/api`**.
- **Toda tela autenticada leva `<meta name="robots" content="noindex, nofollow">`**, cinto
  além da suspensória: bloqueio no `robots.txt` impede a visita, não a indexação de um
  endereço que vazou por outro caminho.
- Redirecionamento permanente de `www.dervs.com.br` para `dervs.com.br`, e de `http` para
  `https` — já está de pé e verificado.

### Velocidade como critério de aceitação, não como ajuste depois

| Métrica | Meta | Como se sustenta |
|---|---|---|
| Maior conteúdo pintado (LCP) | < 1,5s em 4G | A dobra é texto e SVG. Nenhuma imagem de mapa de bits acima da rolagem |
| Salto de layout (CLS) | < 0,05 | Toda imagem com largura e altura declaradas; o esqueleto do painel tem a altura exata das linhas |
| Resposta ao toque (INP) | < 200ms | Nenhuma biblioteca de interface no cliente. Filtro do painel é uma mudança de classe, não uma nova consulta |
| Peso da página pública | < 100 KB, fonte incluída | Uma família tipográfica em subconjunto latino, dois pesos, SVG em vez de imagem |

### O que explicitamente **não** se faz agora

Sem rastreador de terceiro, sem mapa de calor, sem aviso de biscoitos — porque não haverá
biscoito de terceiro para avisar. Uma ferramenta que promete "eu te digo a verdade sobre
seus projetos" não abre a própria porta para três empresas olharem quem entrou. Medição de
audiência, se um dia for preciso, será por registro do próprio servidor.

---

## Como esta fase se prova

Os itens abaixo são verificáveis e viram teste ou olhada na tela na fase 6:

1. `grep -rE '#[0-9a-fA-F]{3,8}|rgb\(|oklch\(' ` fora do bloco de tokens não retorna nada.
2. Nenhum token `--estado-*` aparece em regra de botão, link, navegação ou cabeçalho.
3. Todo par de contraste da tabela é recalculado no teste e reprova abaixo de 4,5:1
   (texto) ou 3:1 (contorno com significado).
4. Nenhuma cor tem definição única dentro de um bloco de tema.
5. Em 360×640, a linha de projeto mostra selo, nome, motivo e carimbo juntos, e a página
   não rola na horizontal. (Corrigido em 28/08/2026; era "10 projetos sem rolagem".)
6. Nenhuma palavra em inglês na interface — busca contra a lista do vocabulário fixo.
7. Todo estado de selo tem, no HTML, cor + forma + glifo + rótulo textual.
8. Nenhum número aparece em tela sem o carimbo da medição que o produziu.
