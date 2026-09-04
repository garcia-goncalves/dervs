# Design — Servidores múltiplos

Fase 3 da esteira, modo leve. Contrato desta fase: `briefing.md` e `spec.md`, ambos
aprovados. Onde os três documentos divergem, vale `spec.md` (ele já registrou as
divergências em `contradicoes_resolvidas`).

---

## direcao_visual_escolhida

**Não há painel adversarial nesta fase, e a ausência é deliberada.** A direção visual
"Torre de Controle" já foi escolhida e aprovada em `docs/esteira/dervs/design.md`
(26/08/2026) para o produto inteiro — cor, tipografia, espaçamento, forma (raio de 3px,
zero sombra), e o vocabulário de selo com quatro sinais independentes (cor + forma +
glifo + rótulo). Este trabalho é a mesma tela ("Conectar projeto") ganhando mais um
cartão do mesmo tipo que os três que já existem ali (computador, GitHub, servidor),
mais um selo a mais no card do projeto. Não há decisão visual nova a tomar:

- **Mesmo produto** — é a tela `#/conectar` do DERVS, não uma aplicação nova.
- **Mesmo dono** — os dois usuários (o dono e o André) já convivem com o vocabulário de
  selo todo dia; introduzir uma segunda linguagem visual para "servidor" quebraria a
  promessa central do produto ("a diferença entre as três é o produto",
  `docs/A-APLICACAO.md` §4.2) em vez de reforçá-la.
- **Mesmo vocabulário de selo** — a spec já decidiu (`spec.md`, seção `solucao`) que os
  três selos do card do projeto continuam sendo computador/GitHub/servidor(es), só que
  o terceiro deixa de ser um selo genérico "conectado/desconectado" e passa a listar
  nomes de servidor. Isso é extensão de um padrão existente, não desenho de um padrão
  novo.

Rodar um painel de três direções aqui produziria três respostas para uma pergunta que
já tem resposta — é o desperdício que a regra "não reabrir escolha visual" (citada no
briefing e no `plano_de_voo`) existe para evitar.

**Referência obrigatória para quem construir esta fase:** `assets/painel.js:738-761`
(`ESTADO_DA_PORTA`, `marcaDaPorta`) e `assets/painel.js:763-1240` (`porta`,
`formularioDeEndereco`) — é o código que esta fase estende, não substitui.

---

## tokens

**Nenhum token novo de cor, tipografia, espaçamento ou raio.** Todos os tokens que esta
tela precisa já existem em `docs/esteira/dervs/design.md`, seção `tokens`, e em
`assets/painel.css`:

| Token/classe existente | Uso nesta tela |
|---|---|
| `--estado-saudavel` / `--estado-quebrado` / `--estado-atencao` / `--estado-sem-dados` (+ os `-fraco`) | cor de cada selo de servidor, herdada do componente `marcaDaPorta` já existente |
| `--borda`, `--borda-forte` | separador entre servidores cadastrados na lista; contorno do campo "padrão de subdomínio" |
| `--fs-corpo`, `--fs-metadado`, `--fs-destaque` | nome do servidor, endereço, carimbo de medição — os mesmos papéis já usados em `.endereco__dizeres` |
| `--e1`–`--e4` (grade de 4px) | espaçamento entre servidores da lista e dentro de cada bloco de endereço |
| `--raio: 3px` | cartão de servidor, campo de formulário, botão — igual a todo o resto |
| classes `.enderecos`, `.endereco`, `.endereco__dizeres`, `.endereco__url`, `.endereco--novo` | reusadas sem alteração para o bloco de endereço-por-servidor dentro de cada servidor cadastrado |
| `marcaDaPorta()` / `ESTADO_DA_PORTA` (`assets/painel.js:738-761`) | o selo de cada servidor cadastrado (responde / não responde / não deu para conferir) |
| `selo()` / `ESTADOS` (usados na lista de projetos, `assets/painel.js:27-32,86`) | o selo "servidor(es)" dentro do card do projeto no painel principal |

**Uma lacuna real, e a extensão mínima que ela pede:** não existe hoje um jeito de um
selo dizer "estou em N coisas ao mesmo tempo" — `marcaDaPorta` e `selo()` foram
desenhados para um estado só por selo. O card do projeto agora precisa dizer "está em 2
servidores" (ou "não está em nenhum"), o que é uma **contagem**, não um dos quatro
estados existentes.

- **Extensão proposta, mínima:** o selo "servidor(es)" do card do projeto usa o mesmo
  glifo/forma que já existe (`[OK]` verde se está em pelo menos um; `[X]` vermelho se
  não está em nenhum apesar de haver servidor cadastrado; `[···]` neutro se não há
  como conferir), e o **rótulo escrito** — não um token novo — carrega a contagem:
  "em 2 servidores" em vez de só "conectado". Isso é texto (campo `textos` abaixo), não
  cor nem forma nova. Nenhum quinto estado de selo é criado — os quatro continuam
  sendo os únicos possíveis, e "está em 2 servidores mas 1 deles não responde" resolve
  pelo mesmo princípio de "o pior estado vence" que `piorDe()` já usa hoje para
  compor o motivo do card (`assets/painel.js:263,278`).
- Dentro da tela de detalhe do servidor (a lista de endereços por servidor), cada
  endereço individual continua com um selo de um estado só — a contagem só aparece na
  camada de resumo (card do painel principal e cabeçalho de "Conectar projeto"), nunca
  dentro do detalhe, onde a pergunta já é "este endereço específico responde?".

---

## telas

Três blocos mudam. Nenhum é uma tela nova — os três já existem e ganham forma nova para
o mesmo dado.

### 1. "Conectar projeto" — o cartão "O seu servidor" vira lista de servidores

Hoje (`assets/painel.js:1215-1319`) é um cartão único, título fixo "O seu servidor",
com um selo geral e um formulário de endereço sem escolha de servidor. Passa a ser:

- **Cabeçalho da seção:** "Seus servidores", com o selo geral igual ao que já existe
  hoje (sem_dados / conectado / desconectado, conforme leu ou não a lista) — mesma
  função `porta()`, mesmos três estados de porta.
- **Lista de servidores cadastrados**, um bloco por servidor, cada um com:
  - nome do servidor (ex. "OVH"), em `--fs-destaque`;
  - padrão de subdomínio, se houver, em `--fs-metadado` monoespaçado (é dado técnico,
    igual a um endereço);
  - botão "Apagar" (`botao--secundario`, mesmo padrão de `formularioDeEndereco`);
  - dentro do bloco, a lista de endereços gravados **naquele** servidor — reusa
    `formularioDeEndereco()` quase sem alteração, só que passa a receber o
    `servidor_id` daquele bloco e filtrar por ele.
- **Formulário de servidor novo**, acima da lista: campo "nome do servidor" (texto,
  obrigatório) e campo "padrão de subdomínio" (texto, opcional, com o placeholder
  `*.tinehost.com.br`), botão "Cadastrar servidor".
- **Formulário de endereço**, dentro de cada bloco de servidor: os mesmos dois campos
  de hoje (nome do projeto, URL), sem campo de escolha de servidor porque o servidor
  já está implícito no bloco em que o formulário vive — isso evita repetir um seletor
  em cada linha e é mais barato de ler que um `<select>` genérico solto no topo.

**Estado vazio (nenhum servidor cadastrado ainda):** o cartão mostra a mensagem "Nenhum
servidor cadastrado ainda." (ver `textos`) e só o formulário de cadastrar servidor —
sem lista, sem formulário de endereço, porque não há bloco para ele viver dentro.

**Carregando:** mesmo padrão que o resto da tela: o selo do cabeçalho vai para
`sem_dados` ("não deu para conferir") até a leitura de `/api/servidores` responder —
nunca um spinner, nunca a lista aparece vazia por instante antes de ter certeza que
está vazia mesmo.

**Erro (a leitura de `/api/servidores` falha):** o cabeçalho mostra o selo `sem_dados`
com o resumo "Não consegui ler os servidores desta conta. Isso não quer dizer que
nenhum está cadastrado — quer dizer que não olhei." — o mesmo padrão de frase que já
existe para GitHub e para o endereço singular hoje (`assets/painel.js:1189-1191,
1221-1223`). Nunca "Nenhum servidor cadastrado" quando a verdade é "não consegui ler".

**Sugestão de autodetecção:** quando o dono cadastra (ou já tem) um servidor com padrão
de subdomínio, e o DERVS encontra um projeto que casa e responde, aparece **dentro do
bloco daquele servidor**, acima do formulário manual, uma linha destacada com
`--borda-forte` (não uma cor de estado — é uma proposta, não um veredito) mostrando o
nome do projeto e o endereço candidato, com dois botões: "Usar este endereço" e
"Ignorar". Nunca grava sozinho — ver `textos` para a frase exata.

**360px:** o cartão de servidor ocupa a largura total; nome do servidor e botão
"Apagar" ficam na mesma linha até não caberem, então o botão desce (mesmo padrão que
`.endereco` já usa hoje). O menu de telas continua sendo a faixa que rola horizontal
(correção de 04/09/2026, não reaberta aqui). O bloco de endereços dentro de cada
servidor reusa a mesma quebra de `.endereco` — nome/URL numa linha, selo e carimbo na
linha de baixo quando não couberem juntos.

### 2. O card do projeto no painel principal

Hoje o motivo do card (`assets/painel.js:274-278`) já pode citar o servidor dentro da
frase de "pior estado" (ex. "O site de produção do X não respondeu"), mas o selo em si
é um selo só, fundindo os três (computador, GitHub, servidor). Passa a ter — no
cabeçalho da linha do projeto, ao lado do selo principal — um segundo elemento visual
menor: o selo de servidores, usando `marcaDaPorta`, com o rótulo carregando a
contagem (ver a extensão mínima em `tokens`). Se o projeto responde em mais de um
servidor e um deles está fora do ar, o selo geral do card continua obedecendo
`piorDe()` (o pior estado vence, já existente), e a frase do motivo nomeia qual
servidor está fora do ar — o mesmo padrão que `regras.py` já vai produzir por servidor
(`spec.md`, seção `solucao`).

**Vazio/carregando/erro:** herdados do card do projeto como um todo — não há um estado
vazio/carregando/erro **próprio** do selo de servidor dentro do card; ele segue o
mesmo carregando/erro que todo o card já tem hoje (`assets/painel.js:958,
"pintarEspera"`).

**360px:** o selo de servidores fica na mesma linha do nome quando cabe; se não couber,
desce para a linha do carimbo — nunca força rolagem horizontal.

### 3. A tela de detalhe do projeto — os três selos separados

Hoje a tela de detalhe (a partir de `assets/painel.js:394` em diante) já lista
critérios por camada (código, GitHub, servidor, máquina local — ver
`docs/esteira/dervs/design.md`, tela 3). O que muda: a camada "servidor", que hoje
mostra um critério só ("o site de produção respondeu"), passa a mostrar **um critério
por servidor cadastrado** em que aquele projeto tem endereço — cada linha com seu
próprio selo de quatro estados, o endereço, o código de resposta (ou o motivo de não
ter respondido) e o carimbo de quando foi medido. Um projeto sem endereço em nenhum
servidor mostra uma linha só: "Não está em nenhum servidor cadastrado" com o selo
`sem_dados` (ver `textos`) — não é erro, é ausência.

**Vazio (nenhum endereço gravado para este projeto em nenhum servidor):** a mensagem
acima, com um link/botão para "Conectar projeto" (mesma convenção que a tela 3 já usa
para "Primeira medição em andamento" — ausência tem texto, nunca uma seção que some).

**Carregando:** só a linha do servidor que está sendo remedido pisca — mesmo padrão já
descrito em `docs/esteira/dervs/design.md`, tela 3 ("só o critério que está sendo
remedido pisca; o resto da tela fica parada").

**Erro (um servidor específico não respondeu à medição):** a linha daquele servidor
mostra `quebrado` com o motivo em uma frase; os outros servidores do mesmo projeto
não são afetados — mesmo princípio "um critério que falha não derruba os outros" já
registrado na tela 3 do design aprovado.

**360px:** cada linha de servidor vira bloco vertical (selo em cima, endereço e
carimbo embaixo) — mesma quebra que as outras camadas de critério já usam.

---

## textos

Todo texto novo em português do Brasil, no mesmo tom que o resto do painel: frase
curta, explica o porquê em meia linha, nunca inventa um estado que não mediu.

### Cadastrar servidor

- Rótulo do formulário: **"Cadastrar servidor"**
- Campo 1: rótulo "Nome do servidor" (`aria-label`), placeholder `"OVH"`
- Campo 2 (opcional): rótulo "Padrão de subdomínio (opcional)" (`aria-label`),
  placeholder `"*.tinehost.com.br"`
- Texto de ajuda abaixo do campo 2: **"Se os projetos deste servidor seguem um
  padrão de endereço, o DERVS testa sozinho e sugere o preenchimento — você ainda
  confirma antes de qualquer coisa ser gravada."**
- Botão: **"Cadastrar servidor"**
- Texto do cabeçalho da seção (substitui "O seu servidor"): **"Seus servidores"**
- Estado vazio: **"Nenhum servidor cadastrado ainda. Cadastre o nome de um provedor
  (por exemplo OVH ou TineHost) para começar a gravar endereços nele."**
- Resumo do selo geral, lido: **"Há N servidor(es) cadastrado(s)."** (N = 1: "Há 1
  servidor cadastrado.")
- Resumo do selo geral, não lido: **"Não consegui ler os servidores desta conta. Isso
  não quer dizer que nenhum está cadastrado — quer dizer que não olhei."**
- Nota fixa do cartão (reaproveita a nota que já existe hoje, sem reescrever):
  **"Nunca pedimos chave de acesso ao servidor, e não vamos pedir: o endereço público
  basta para conferir se ele responde. Endereço de rede interna é recusado de
  propósito — o painel roda num servidor, e um endereço interno faria dele uma
  ferramenta de varredura."**

### Apagar servidor

- Botão: **"Apagar"**
- Confirmação (nomeia o que morre, como a spec já exige em outros lugares):
  **"Apagar o servidor OVH? Os endereços gravados nele saem do DERVS. O site em si não
  é tocado — só paramos de medir por aqui."** → botões **"Apagar"** · **"Manter"**

### Endereço por servidor (dentro de cada bloco)

Reusa, sem reescrever, o texto de erro que já existe hoje para endereço recusado
(`servir.py:1657-1659`, `ENDERECO_RECUSADO`):

> **"esse endereço aponta para dentro de uma rede privada, ou não é um endereço
> http(s) público. O DERVS só mede endereço que qualquer um alcança pela internet."**

- Campo "nome do projeto": mesmo rótulo/placeholder de hoje (`"nome do projeto"`)
- Campo "URL": mesmo rótulo/placeholder de hoje (`"https://o-seu-site.com.br"`)
- Botão: **"Guardar o endereço"** (mantido, já existe)
- Botão de remover: **"Apagar"** (mantido, já existe)

### O selo "servidor(es)" no card do projeto e na tela de detalhe

- Está em servidor(es): **"em 1 servidor"** / **"em 2 servidores"** (plural correto
  a partir de 2)
- Não está em nenhum, apesar de haver servidor(es) cadastrado(s): **"não está em
  nenhum servidor cadastrado"**
- Não deu para conferir: **"não deu para conferir"** (reusa `ESTADO_DA_PORTA.sem_dados`
  sem alteração)
- Na tela de detalhe, linha "ausência" (projeto sem endereço em nenhum servidor):
  **"Não está em nenhum servidor cadastrado."** — nunca "não se aplica".
- Frase de motivo no card, quando um dos servidores está fora do ar (segue o padrão já
  existente de nomear o servidor): **"O site de produção do X no servidor OVH não
  respondeu."** (reusa a construção que a spec já decidiu para `regras.py`, item 15)

### Autodetecção por padrão de subdomínio — sempre proposta, nunca automática

- Texto da linha de sugestão, dentro do bloco do servidor: **"O endereço
  `https://ajudei-saude.tinehost.com.br` respondeu e parece ser deste projeto. Quer
  usar este endereço para o ajudei-saude?"**
- Botão: **"Usar este endereço"** · **"Ignorar"**
- Se o dono ignorar, o DERVS não pergunta de novo sozinho na mesma sessão — evita
  a mesma sugestão reaparecer a cada atualização da tela (comportamento de
  implementação, não é um texto novo, mas fica registrado aqui para a fase de plano
  não perder o critério).

### Dados de demonstração (verossímeis, do parque real do dono, sem segredo)

| Servidor | Padrão de subdomínio | Projetos com endereço | Selo do servidor |
|---|---|---|---|
| `OVH` | — (sem padrão, cadastro manual) | `dervs-hub`, `grimoire` | conectado |
| `TineHost` | `*.tinehost.com.br` | `medconsultoria`, `ccvp-painel`, `zacareli` | conectado |

| Projeto | Selo "servidor(es)" | Motivo (se houver pendência) |
|---|---|---|
| `ajudei-saude` | não está em nenhum servidor cadastrado | — |
| `ccvp-painel` | em 1 servidor (TineHost) | — |
| `medconsultoria` | em 1 servidor (TineHost) | — |
| `dervs-hub` | em 2 servidores (OVH, TineHost) | "O site de produção do dervs-hub no servidor TineHost não respondeu." |

Nomes coerentes com os já usados em `docs/esteira/dervs/design.md` (mesma tabela de
dados de demonstração) e com o parque real citado no `CLAUDE.md` do repositório (OVH e
os cinco da TineHost). Nenhum segredo, nenhum endereço real de produção é citado.

---

## assets

**Nenhum.** Os ícones/estados desta tela reusam por inteiro o vocabulário ASCII/texto
que o painel já usa em todo lugar — `[OK]`, `[X]`, `[!]`, `[···]`, via `marcaDaPorta()`
e `selo()` (`assets/painel.js:747-761` e a função `selo` da lista principal). Não há
imagem, ícone de biblioteca externa ou SVG novo: a extensão de token descrita em
`tokens` é só o rótulo escrito de um selo existente carregando uma contagem, não uma
forma visual nova.

---

## estrategia_de_aquisicao

**Nenhuma.** "Conectar projeto", o card do painel e a tela de detalhe do projeto são
telas internas, atrás de login, sem página pública correspondente — o mesmo motivo já
registrado em `docs/esteira/dervs/design.md` para as seis telas da Fatia 1
("`robots.txt` bloqueando `/painel`, `/projeto`, `/maquinas`, `/api`", "toda tela
autenticada leva `noindex, nofollow`"). Aquisição e SEO não se aplicam a mudança dentro
de uma tela já bloqueada de indexação.
