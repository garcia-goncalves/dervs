# DERVS

O posto de comando de quem programa. Uma pergunta só: **"posso confiar no que
está no ar?"** — respondida em menos de um segundo, sem clicar em nada, com um
botão para agir em cada item.

Não é um painel de "como estão meus projetos". Essa pergunta produz uma tela
bonita que se olha uma vez por semana. Esta produz uma tela que se abre todo dia.

> **Novo por aqui? Leia [`docs/A-APLICACAO.md`](docs/A-APLICACAO.md).** É a fonte
> única: o que o DERVS é, para quem, o que mostra, o que faz e o que nunca vai
> fazer. Todo o resto deste repositório aponta para ele.

## Rodar

```
set DERVS_AMBIENTE=local
python servir.py
```

Abre em **http://localhost:4777**. `Ctrl+C` encerra.

**A primeira tela não é o painel.** Desde a etapa 9 o `/` é uma capa — um
teclado de seis dígitos e nada que diga o que este sistema é. Na sua máquina a
combinação é **`000000`**, fixa e escrita aqui de propósito: local é ambiente de
mentira, e dado de teste não é segredo. Digite, e aparece o **menu de portas**.

**As quatro portas**, na ordem em que a tela as oferece:

| Porta | O que é | Quando aparece |
|---|---|---|
| **Chave de acesso** | passkey: o aparelho assina, o PIN do Windows (ou a digital) destranca | sempre |
| **Entrar com GitHub** | a conta do GitHub, com o 2FA que ela já tem | só com o OAuth App registrado |
| **Código do papel** | um dos dez códigos de uso único, anotados antes | sempre |
| **Entrar · ambiente local** | sessão para `dono@teste.local`, sem senha | só com `DERVS_AMBIENTE=local` |

**Chave de acesso não é digital.** Digital e rosto são só a maneira de
destrancar a chave *dentro* do aparelho — num PC sem câmera e sem leitor, quem
destranca é o **PIN do Windows Hello**, e a chave mora no chip TPM da placa.
Sem TPM, o navegador mostra um QR, o celular confirma com a digital, e a chave
mora no celular. A chave privada nunca sai do aparelho: é por isso que passkey
é imune a site falso — num endereço parecido o navegador simplesmente não
encontra chave nenhuma para oferecer.

Cadastrar, apelidar e remover chaves é dentro do painel, no botão
**Conta → Formas de entrar**. É lá também que se geram os dez códigos de papel — eles
aparecem **uma vez só**. Detalhes e a razão de cada escolha em
[`docs/operacao/formas-de-entrar.md`](docs/operacao/formas-de-entrar.md).

`DERVS_AMBIENTE=local` é obrigatório: sem ela o cofre se recusa a criar a
`cofre.chave` e a porta local some. As duas coisas falham fechadas de propósito
— uma variável esquecida no servidor não pode ser tudo o que separa o mundo de
uma conta pronta.

No servidor é outra história: a combinação é **sorteada na primeira subida e
impressa uma única vez no log**, a porta local **não existe na tabela de rotas**,
e o que resta são chave de acesso, GitHub e código do papel — todos contra a
lista de contas da tabela `credencial`. Ver
[`docs/operacao/registrar-app-github.md`](docs/operacao/registrar-app-github.md).

| Variável | Para quê | Onde vive |
|---|---|---|
| `DERVS_AMBIENTE` | `local` libera a porta local e deixa o cofre nascer | linha de comando |
| `DERVS_COFRE` | a chave do cofre, 32+ caracteres | ambiente do servidor |
| `DERVS_COFRE_ARQUIVO` | tira a `cofre.chave` da pasta servida (etapa 16) | ambiente do servidor |
| `DERVS_GITHUB_ID` | Client ID do OAuth App — **é público** | pode ser versionado |
| `DERVS_GITHUB_SECRET` | Client Secret — **segredo** | só dentro do servidor |
| `DERVS_GITHUB_TOKEN` | token de leitura do **coletor** — **segredo** | só dentro do servidor |
| `DERVS_PROXIES_CONFIAVEIS` | IPs autorizados a dizer de quem é o pedido (etapa 16) | ambiente do servidor |

Sem `DERVS_GITHUB_ID`/`DERVS_GITHUB_SECRET`, `/entrar/github` responde **404** e
o botão nem aparece. Botão que leva a erro é pior que botão que não existe.

`DERVS_GITHUB_TOKEN` é de outra coisa: é como o **coletor** lê o GitHub. Nesta
máquina ele não é necessário — sem a variável, o coletor usa o `gh` que o dono
já logou aqui. No servidor o `gh` não existe e não pode existir (guardaria a
identidade pessoal do dono numa máquina sozinha na internet), então lá a
variável é obrigatória. Como criá-la:
[`docs/operacao/token-do-coletor.md`](docs/operacao/token-do-coletor.md).

Conta nova só por comando, nunca pela web:

```
python autenticacao.py convidar <login-do-github> <email>
python autenticacao.py remover <email> APAGAR
```

O `remover` é o desfazer do convite: `email` é UNIQUE na tabela `usuario`, então
sem ele um endereço digitado errado ficava queimado para sempre. A palavra
`APAGAR` é obrigatória, e a última conta do sistema não pode ser apagada — não
há cadastro pela web, e apagá-la trancaria o DERVS.
`python servir.py 4780 30` troca a porta e o intervalo da camada local.

Só escuta em `127.0.0.1`: o HUB lê git, Docker e o GitHub autenticado, então
exposto na rede vira porta de entrada.

Sem build, sem `npm install`, sem dependência externa. Precisa de Python 3.12,
`git`, `docker` e o `gh` já autenticado (`gh auth status`).

## As peças

| Arquivo | Papel |
|---|---|
| `index.html` | A tela. Recarrega sozinha a cada 15 s. |
| `servir.py` | Serve a página e o `/api/dados`. Agenda as três coletas. **Não executa comando** — ver a seção abaixo. |
| `banco.py` | O SQLite (`hub.db`): 12 tabelas — as 6 da medição, mais as 6 de quem usa o painel (etapa 8). Também é onde mora o cofre que cifra segredo. |
| `test_banco.py` | 65 testes das tabelas novas e do cofre. `python test_banco.py`. |
| `regras.py` | O motor das 18 pendências, mais o agrupamento das repetidas. Puro: entra dicionário, sai lista. |
| `memoria.py` | A memória do tempo: idade de cada pendência, tendência da semana e o briefing. |
| `test_memoria.py` | 46 testes da memória. `python test_memoria.py`. |
| `execucao.py` | O antigo botão **Resolver**. **Sem rota apontando para ele** desde a etapa 7 — fica no repositório de propósito. |
| `test_execucao.py` | 90 testes das decisões do Resolver e das barreiras, todos verdes. `python test_execucao.py`. |
| `barreira.py` | O porteiro do `Bash` da sessão desacompanhada: roda como hook do `claude` e barra o comando **antes** dele rodar. |
| `test_barreira.py` | 36 testes da barreira — cada um é um ataque concreto ou um comando honesto. `python test_barreira.py`. |
| `test_regras.py` | 67 testes do motor. `python test_regras.py`. |
| `test_servir.py` | 6 testes: a linha de comando, e o amarre entre o que a tela busca e o que o servidor serve. `python test_servir.py`. |
| `test_rotas.py` | 11 testes — **o vigia**: importa `servir` e prova que nenhuma rota executa comando. `python test_rotas.py`. |
| `coletar.py` | Camada **local**: git, Docker, portas, idade do grafo, memória, variáveis. |
| `coletar_github.py` | Camada **github**: CI, PRs, **issues abertas**, alertas, o site no ar e o último deploy. Uma consulta GraphQL em lote, para todos os repositórios. |
| `test_coletar.py` | 165 testes dos pedaços dos coletores que já erraram, inclusive a escolha entre token pronto, GitHub App e `gh`. `python test_coletar.py`. |
| `github_app.py` | Troca a **chave privada** do GitHub App por um token de uma hora, e renova antes de vencer. Assinatura RS256 escrita à mão — o projeto não usa biblioteca de fora. |
| `test_github_app.py` | 19 testes. O principal exige que a assinatura seja **igual byte a byte à do OpenSSL**: conta de criptografia testada só com o que ela mesma produziu não está testada. `python test_github_app.py`. |
| `coletar_pesado.py` | Camada **pesado**: cota do Actions e `npm audit`. |
| `test_coletar_pesado.py` | 12 testes da auditoria de dependência. `python test_coletar_pesado.py`. |
| `fila.py` | A fila desacompanhada. **Sem rota apontando para ela** desde a etapa 7 — fica no repositório de propósito. |
| `test_fila.py` | 92 testes da fila. `python test_fila.py`. |
| `casos.json` | Camada **curada**, escrita à mão. Nenhum coletor toca aqui — e desde 01/09/2026 o `url_prod` dele **perde** para o endereço que você digita na tela. |
| `conectador.py` | O programa que roda **na máquina de quem baixa**, e não aqui: escolhe a pasta, pede ao painel (sem número digitado: o navegador abre e o dono clica em Autorizar), recebe o programa que mede e registra a tarefa que mantém o relato ligado. Um arquivo, biblioteca padrão pura, ASCII puro, e nenhum `import` deste repositório — ele roda onde o DERVS pode nem existir. O servidor o **lê** do disco e injeta o endereço; nunca o importa. |
| `conectador.cmd` | O molde do arquivo que o botão **Conectar este computador** baixa (`GET /api/conectar.cmd`). Baixa o Python oficial uma vez (SHA-256 conferido) e roda o `conectador.py` colado no fim. No repositório fica com LF; o servidor monta a saída com CRLF. |
| `test_conectador.py` | 29 testes, todos por dublê: a CI não tem Windows, nem agendador, nem janela gráfica. O que eles cobram são as três leis do arquivo — um arquivo só de biblioteca padrão, fechar sem escolher não deixa lixo, e a pausa do fim não pendura a tarefa agendada. `python test_conectador.py`. |
| `test_conectar_servidor.py`, `test_conectar_tela.py`, `test_conectar_fio.py` | O Conectar simples em três camadas: as rotas do servidor (pedido do computador, pacote, arquivo, esconder projeto, medir site), a tela executada em node com respostas falsas, e o fio que baixa o `.cmd` de verdade, roda a parte Python numa pasta sem o repositório e confere que cada campo que o `painel.js` lê existe na resposta. `python test_conectar_fio.py`. |

`hub.db` é descartável e não é versionado: apagar só custa uma coleta — e, desde
25/08/2026, também zera a memória do tempo, que se reconstrói sozinha a partir da
coleta seguinte.

**1.449 testes no total** (01/09/2026), todos em `unittest` da biblioteca padrão,
e os **25** arquivos rodam na CI — que **falha se um `test_*.py` novo ficar de
fora da lista**, porque arquivo esquecido não fica vermelho, fica invisível.

*As contagens por arquivo da tabela acima são de quando cada linha foi escrita e
envelheceram sem avisar — este parágrafo é o número que vale. Contagem escrita à
mão em dois lugares diverge, e a que diverge é sempre a que ninguém lê.*

Passam em Windows e em Linux — verificado num contêiner
`python:3.12-slim`, porque o núcleo vai rodar em Linux na VPS.

## O servidor deixou de executar comando (etapa 7 do DERVS)

Até 26/08/2026 este servidor executava. Havia `/api/acao`, que rodava
`git push`, `docker compose up`, abria o VS Code e disparava uma sessão do
Claude Code; havia `/api/execucao`, que transmitia o log dessa sessão; e havia
um proxy que embutia a tela do grafo de código dentro da mesma origem.

Nada disso foi endurecido. **Foi removido.** A razão é que o HUB vai deixar de
ser um programa que só o dono roda na própria máquina, e código que executa
comando não sobrevive a essa mudança.

### O que ficou no lugar

Uma tabela, `servir.ROTAS`, no fim do `servir.py`. Antes o despacho era uma
cadeia de `if self.path…` espalhada por dois métodos, e ninguém conseguia
responder "quais rotas este servidor tem?" sem ler o arquivo inteiro e torcer
para não ter pulado um `if`. Agora a resposta cabe numa linha:

```bash
python -c "import servir; print(sorted(servir.ROTAS))"
```

```
['/', '/api/dados', '/api/silenciar', '/favicon.ico', '/index.html',
 '/painel-projetos.ico', '/painel-projetos.png', '/painel-projetos.svg']
```

### O vigia, e por que ele lê a memória e não o arquivo

`test_rotas.py` **importa `servir` e itera a tabela em memória**. Um `grep` por
`"/api/acao"` no texto do arquivo não veria uma rota montada por concatenação —
`"/api/" + "exec" + "ucao"` — e essa rota executaria exatamente igual a uma
escrita à mão. O vigia também reprova se `ROTAS` **não existir**, para que
ninguém "conserte" o teste apagando a tabela.

E ele olha o **comportamento**, não só o nome: uma rota `/api/diagnostico`
apontando para `Hub._diagnostico` — dois nomes limpos — com `subprocess.run`
no corpo passaria por um vigia que só lesse rótulos. Ele segue o grafo de
chamadas a partir de cada rota. E confere que ninguém acrescentou um `do_PUT`
à classe, que despacharia por fora da tabela inteira.

Provado pelos dois lados em 26/08/2026: no código são ele passa; e reprova as
**cinco** sabotagens testadas — rota escrita à mão, rota montada por
concatenação, caminho inocente apontando para função de nome suspeito, nomes
limpos com `subprocess` no corpo, e um `do_PUT` novo por fora da tabela.

### `execucao.py` e `fila.py` continuam aqui, sem rota

De propósito. Os dois somam 182 testes verdes, e a trava de diff de
`fila.py:229` é uma das defesas do produto para a fatia seguinte. Apagá-los
"já que estão sem uso" custaria as duas coisas. Eles não são importados pelo
`servir.py`, e o vigia prova isso.

### O que sumiu da sua tela

O botão **Resolver**, a faixa da **fila**, a aba do **grafo de código**, os
botões **"Medir agora"** e **"Atualizar GitHub"**, e as entradas da paleta que
abriam o VS Code, subiam contêiner ou davam `git push`.

O que ficou: o briefing, a caixa de pendências, o **x** que esconde um alerta
por 24 h, a tabela dos 17 projetos, a paleta (só com o que abre link) e o tema.
As três coletas seguem rodando sozinhas — 60 s, 20 min e 24 h —, então a tela
continua se atualizando sem nenhum botão.

## As três cadências

| Camada | De quanto em quanto | O que mede | Por quê |
|---|---|---|---|
| local | 60 s | git, Docker, portas, idade do grafo, memória, variáveis | só disco, é barato |
| github | 20 min | CI, pedidos de alteração, alertas de segurança, **o site no ar e o que já foi publicado** | rede e cota — nada disso muda em um minuto |
| pesado | 24 h | cota de minutos do Actions, `npm audit` | caro: várias chamadas e rede por repositório |

**A tela nunca espera coleta.** Lê o último valor do banco, mostra na hora e
troca o número quando o novo chegar. Cada camada exibe há quanto tempo foi
medida e esmaece quando envelhece — se o painel mentir uma vez, o hábito morre.

## As 18 pendências

| # | Regra | Gravidade | Ação |
|---|---|---|---|
| 1 | CI vermelha | alta | abrir o que falhou |
| 2 | Container que devia estar no ar e caiu | alta | subir |
| 3 | Alerta de segurança aberto (Dependabot) | alta se houver crítico ou alto, senão média | ver os alertas |
| 4 | Trabalho não commitado há mais de 1 dia | alta | abrir no VS Code |
| 5 | Commit só no disco | alta | enviar ao GitHub |
| 6 | Memória do projeto em CRLF | alta | converter |
| 7 | Cota do Actions acima de 80% | alta | ver o consumo |
| 8 | Grafo de código ausente ou com mais de 7 dias | média | copiar o pedido |
| 9 | Pedido de alteração parado há 7 dias | média | abrir |
| 10 | Dependência com correção de segurança | média | copiar o comando |
| 11 | Exemplo de variáveis divergente do real | média | copiar as diferenças |
| 12 | Sem commit há mais de 30 dias | baixa | abrir e decidir |
| 13 | Sem cópia no GitHub | baixa | copiar o comando |
| 14 | Sem descrição no `casos.json` | baixa | escrever |
| 15 | Site de produção fora do ar | alta | abrir o site |
| 16 | Trabalho pronto no GitHub e não publicado | média | ver as publicações |
| 17 | A auditoria de dependência tentou rodar e falhou | baixa | copiar o comando |
| 18 | O git não respondeu por este projeto | média | copiar o comando |

**A coluna "Ação" descreve a intenção, não um botão.** Desde a etapa 7, só
viram botão as ações que o navegador faz sozinho — abrir um link e copiar um
texto. "Subir", "abrir no VS Code" e "enviar ao GitHub" continuam sendo o que a
pendência pede de você; a diferença é que agora quem faz é você, fora do painel.

Três invariantes, cobertos por teste:

1. **Toda pendência tem uma ação.** Sem o que fazer, não é pendência: é
   estatística, e estatística vai para a tabela de baixo.
2. **Ausência não é falha.** Camada não coletada deixa o motor calado sobre ela.
   Inventar "CI vermelha" porque o número não chegou queima a confiança.
3. **O id é estável** (`regra:projeto`) — é o que faz "esconder por 24 h" durar.

O **×** de cada item esconde a pendência por 24 horas. A decisão fica no banco e
sobrevive à recoleta.

### Duas regras merecem explicação

**Regra 2 só dispara com o projeto aberto no VS Code.** É o critério pelo qual o
`vigia-vscode` sobe e derruba o Docker desta máquina. Sem esse filtro a caixa
nasce com seis alarmes de projeto fechado — nenhum deles pendência, todos
ensinando o dono a ignorar a lista inteira.

**Regra 6 existe porque o erro é calado.** Arquivo de memória em CRLF faz o
harness ignorar o frontmatter, e a memória nunca carrega. Nada na tela avisa.

## A paleta de comandos (`Ctrl+K`)

Uma porta de entrada só. `Ctrl+K` (ou `Cmd+K`) abre uma caixa de busca; digitar
`dents` acha o projeto e os endereços dele. Com 17 repositórios, menu em árvore
vira caça ao tesouro.

**A etapa 7 esvaziou boa parte dela**, e de propósito: "abrir no VS Code",
"subir os contêineres" e "enviar ao GitHub" rodavam programa na sua máquina e
saíram junto com as rotas. O que sobrou abre link — e link o navegador abre
sozinho.

O botão **"Buscar projeto ou ação  `Ctrl K`"** fica visível no cabeçalho de
propósito: atalho que só existe no teclado é atalho que ninguém descobre.

### O que entra na lista

Hoje são ~76 comandos, montados a cada abertura a partir do que a tela já sabe:

1. **As pendências da caixa cuja ação o navegador faz sozinho** — abrir um link
   ou copiar um texto. As demais não entram: a paleta não pode oferecer o que o
   botão não oferece mais.
2. **Cada projeto**, com as portas de entrada que **existem** para ele: abrir no
   GitHub, abrir o site no ar (só se tem `url_prod`), abrir o endereço local (só
   se a porta está viva de fato).
3. **Comandos da máquina**: trocar o tema.

Item que abre nada é pior que item ausente, então nada entra "por via das
dúvidas".

### Como a busca ordena

Quatro níveis, do melhor para o pior: nome igual → começa com → contém →
**letras na ordem** (`wsmed` acha `workspace-medconsultoria`). Acento e hífen
são ignorados dos dois lados — `ajudei saude` acha `Ajudei-Saúde`, que é como
uma pessoa digita.

Uma regra de desempate merece explicação. Digitar o **nome inteiro** de um
projeto põe as entradas daquele projeto em primeiro, mesmo havendo pendência
dele — quem digita `dents` quer o dents. Mas digitar **letras soltas** deixa a
pendência urgente ganhar: ali o dono não sabe o nome, está procurando o que
precisa dele. É o `BONUS_NOME` no `index.html`.

### O que ela deliberadamente não faz

**A paleta não tem ação própria nenhuma.** Ela encontra e dispara o que já
existe: mesma função `agir()`, e a mesma decisão de `temAcaoNaTela()` que a
caixa usa para desenhar o botão. Se pudesse fazer algo que a tela não faz,
viraria uma segunda superfície de risco para revisar a cada mudança.

Dois testes amarram isso: `ATelaSoChamaRotaQueExiste` (em `test_servir.py`)
cruza cada `fetch()` do `index.html` com a tabela `servir.ROTAS`, e o vigia do
`test_rotas.py` prova que essa tabela não tem nada que execute comando.

### Detalhes de implementação

Escrita à mão em ~200 linhas, sem `cmdk` nem `kbar`, porque as duas custariam
build e dependência — as duas virtudes que este projeto tem.

Usa `<dialog closedby="any">` com `showModal()`: o navegador dá de graça o foco
preso dentro, `Esc` fechando, clique fora fechando e camada acima de tudo sem
guerra de `z-index`. Safari ainda não tem `closedby`, então há um fallback de 8
linhas para o clique fora. Navegação é `↑` `↓` `Home` `End` `Enter`, com o
padrão ARIA de `combobox` + `listbox` e `aria-activedescendant` para leitor de
tela.

**Não há teste automatizado da busca em si** — o projeto não tem executor de
teste JavaScript, e instalar um quebraria "zero dependência, zero build". Foi
verificada no navegador em 24/08/2026 com estes casos: `dents`, `wsmed`,
`ajudei saude`, `subir`, `grafo`, `tema`, termo sem resultado, e navegação por
seta com volta ao fim da lista.

## A coluna "A fazer", e o alerta que se anuncia velho (etapa 12)

O painel passou a trazer as **issues abertas** de cada repositório, na mesma
consulta que já ia buscar CI e pedidos de alteração — não numa consulta a mais.
Isso não é economia de estilo: a cota de minutos desta conta já estourou uma
vez, e uma pergunta por repositório multiplicaria a conta por 15.

**Issue aberta não virou pendência, e isso é decisão.** Todo repositório vivo
tem issue aberta o tempo todo; 15 alertas iguais na caixa de entrada ensinam o
dono a ignorar a caixa inteira, inclusive o alerta que importava. Issue é um
*fato do projeto*, então mora na tabela, na coluna **A fazer**, com três
estados que não se confundem:

| O que aparece | O que quer dizer |
|---|---|
| um número | tantas issues abertas; clicar abre a lista no GitHub |
| `—` | conferi, não há nenhuma |
| `?` | **não consegui ler** — falta permissão, ou a consulta veio pela metade |

### O alerta de segurança que não pode ser apagado nem mentir

Quando o coletor não consegue reler os alertas de um repositório (o token
perdeu a permissão, o campo veio nulo), ele **mantém o último número
conhecido**. Zerar apagaria da tela um alerta real — e "93 alertas abertos"
virando silêncio por um piscar de rede é o pior defeito possível aqui.

Mas manter calado é pior que zerar: o painel republicaria uma medição de
semanas atrás como se fosse de agora, para sempre. Por isso o número
preservado carrega a própria idade (`lido_em`, o carimbo da medição — nunca o
carimbo da linha do banco, que é reescrito a cada rodada) e a pendência passa a
dizer:

> 93 alerta(s) de segurança aberto(s) em medconsultoria. Não consigo reler esse
> número há 26 dia(s), então ele pode estar velho.

E a coleta imprime, no meio de uma rodada bem-sucedida, `aviso: nao consegui
reler os alertas de segurança de N projeto(s)`.

## A nota de prontidão, e por que ela mentia

A coluna **Prontidão** dá a cada projeto uma nota de 0 a 100. Ela é a soma dos
pesos dos critérios cumpridos, dividida pela soma dos pesos que **se aplicam
àquele projeto** — e essa segunda metade da frase é nova.

### O defeito (medido em 24/08/2026)

A régua era uma só para os 17 projetos: dez critérios, 14 pontos, cobrados de
todo mundo. O resultado era uma nota que descontava de cada projeto aquilo que
ele não tinha motivo nenhum para ter.

O caso mais claro era o próprio painel: **64%**, descontado por não ter
contêiner, não ter arquivo de variáveis e não ter workflow de publicação. As
três coisas são decisões declaradas deste projeto — "zero dependência e zero
build" está na especificação, e ele nunca vai para servidor nenhum. A nota não
media dívida técnica; media distância de um projeto imaginário.

Pior: o critério de maior peso da régua (2 pontos, junto com CI e testes) era
*"sem arquivo de variáveis na raiz"* — ou seja, reprovava a **existência** do
arquivo. Mas local é de mentira e servidor é de verdade: ter esse arquivo com
senha de teste é exatamente o certo. O item derrubava 6 dos 17 projetos por
fazerem a coisa certa. O risco real nunca foi o arquivo existir; é ele estar
dentro do histórico do git — e é isso que passou a ser medido.

### Como ficou

Todo critério agora tem duas perguntas, não uma: **cabe cobrar isto deste
projeto?** e só então **ele cumpre?**. O que não se aplica **sai do
denominador** — não vira ponto de graça (isso inflaria a nota) nem falta (isso
era o defeito), simplesmente some da conta.

| Critério | Peso | Cobrado de quem |
|---|---|---|
| README | 1 | todos |
| Árvore limpa e enviada | 1 | quem tem git |
| CI configurada | 2 | quem tem git **e** cópia no GitHub |
| Testes automatizados | 2 | quem tem ≥ 500 linhas em linguagem com lógica |
| Docker / compose | 1 | quem declara contêiner no `casos.json`, ou já tem Dockerfile |
| Exemplo de variáveis | 1 | quem usa variáveis de ambiente |
| Workflow de deploy | 2 | quem tem `url_prod` no `casos.json`, ou já tem o workflow |
| Pasta `docs/` | 1 | projetos com ≥ 100 arquivos |
| `.gitignore` | 1 | quem tem git |
| Segredo fora do histórico | 2 | quem tem arquivo de variáveis, versionado |

Os dois limiares (`LIMIAR_DOCS`, `LIMIAR_TESTES`) e a lista
`LINGUAGENS_TESTAVEIS` ficam no topo do `coletar.py`, num lugar só.

O critério de testes fica calado em site de HTML e CSS: a regra da casa isenta
CSS, layout e texto de tela de TDD, e cobrar suíte de teste de uma página
estática é a mesma acusação vazia de antes, com outro nome.

### A palavra final é do dono

A detecção automática erra para os dois lados. Qualquer projeto pode ligar ou
desligar qualquer critério pelo `casos.json`:

```json
"meu-projeto": {
  "titulo": "...",
  "prontidao": { "deploy": false, "docker": true }
}
```

`false` tira o critério da conta; `true` força a cobrança mesmo sem evidência no
disco. A tela marca esses itens como *"desligado por você"* / *"exigido por
você"*, para a nota nunca parecer automática quando não é.

### A tela passou a mostrar a conta

O número aparecia sozinho, em vermelho, sem dizer de que era feito. Número sem
conta não é medida, é acusação. Clicar na porcentagem abre os dez critérios em
três estados — **✓ feito**, **✗ falta**, **— não se aplica** — com o peso de
cada um e o total aplicável.

A tabela inteira é redesenhada de 15 em 15 segundos. A lista `CONTAS_ABERTAS`
(no `index.html`) guarda o que está aberto **por nome de projeto**, não por
elemento, porque os elementos morrem a cada redesenho — sem isso a gaveta
fechava sozinha no meio da leitura.

### O efeito nos 17 projetos

Doze subiram, um caiu, dois ficaram iguais. Os movimentos maiores:
`medconsultoria-crm` 50 → 83, `odontologia-pericia` 29 → 60, `investrix` 71 →
100, o próprio painel 64 → 86.

Dois casos merecem leitura, porque **não** são inflação:

- **`Ajudei-Saude` caiu 93 → 92.** Antes ele ganhava 2 pontos de graça por *não*
  ter arquivo de variáveis. Agora o critério não se aplica a ele e sai da conta,
  em vez de virar brinde. Nota menor, medida mais honesta.
- **`museu-particular-bkp` caiu 14 → 0.** É uma pasta de backup, sem git e com
  12 arquivos: o único critério que cabe cobrar dela é o README, e ela não tem.
  0% aqui não é "projeto péssimo", é "quase nada a medir". Se incomodar, o
  caminho é tirar a pasta de `source/`, não afrouxar a régua.

## Segurança

**Este servidor não executa comando.** Ele já executou, e a seção acima conta o
que saiu e por quê.

Sobrou uma rota de escrita, `/api/silenciar`, que grava uma linha no banco.
Escutar só em `127.0.0.1` protege contra a rede, mas não contra o navegador do
próprio dono: qualquer site aberto em outra aba pode disparar um POST para
`localhost:4777`. Por isso ela ainda exige as três coisas:

1. um **token** sorteado a cada inicialização, injetado apenas na página servida;
2. cabeçalho `Origin` da própria origem;
3. cabeçalho `Host` de `localhost` (barra DNS rebinding).

O pior que um pedido forjado consegue ali é esconder um alerta da sua tela por
até 30 dias — e isso se desfaz sozinho. O par continua exigido mesmo assim,
porque o alerta escondido pode ser um alerta de segurança.

O servidor publica **só** a página e os três arquivos de ícone. Todo o resto
responde 404, e `HEAD` responde 405 — sem isso ele caía no handler de arquivos
padrão e revelava existência, tamanho e data de qualquer arquivo da pasta — o banco, o `casos.json` e o `.git/` não ficam acessíveis.

**Segredo nenhum entra no banco ou na tela.** O coletor abre o arquivo de
variáveis só para extrair **nomes** de variável. Quem autentica no GitHub é o
`gh` que o dono já logou.

### O que a revisão de segurança pegou (24/08/2026, antes de ir para a `main`)

- **Vazamento de segredo, corrigido.** Ler o arquivo de variáveis linha a linha
  não bastava: num valor multilinha entre aspas — chave RSA, certificado,
  credencial — a última linha de um bloco PEM termina em `=` e casava como se
  fosse nome de variável. O pedaço da chave ia para o banco, para a tela e para
  o botão "Copiar as diferenças". Agora o leitor pula tudo que está dentro de um
  valor com aspas ainda abertas, e nome de variável tem limite de 64 caracteres.
  `test_coletar.py` tranca isso.
- **Pasta publicada, fechada.** Ver acima.
- **`Origin` ausente deixou de passar.**
- **Abrir o VS Code** não usa mais `shell=True`.
- **O coletor não executa mais código de fora do repositório.** A detecção de
  "projeto aberto no editor" lia e *executava* `~/.claude/scripts/vigia-vscode.py`
  a cada 60 s — uma pasta que sessões de agente escrevem com frequência, dentro
  de um processo que escuta em rede e roda comandos. Agora lê as marcas que o
  próprio vigia grava em `~/.claude/state/vigia`: mesma verdade, zero execução.
- **Nome de repositório remoto** é validado contra o alfabeto do GitHub antes de
  entrar na consulta GraphQL.

## O painel deixa de ser de uma máquina só (etapa 8 do DERVS)

Seis tabelas novas em `banco.py`, e nenhuma rota ainda encosta nelas. É de
propósito: a etapa 8 constrói o **esquema**, a etapa 9 constrói o **login**. O
esquema vem antes porque errar a forma de uma tabela depois custa migrar dado e
rotacionar segredo; errar a ordem só custa esperar.

| Tabela | Para quê |
|---|---|
| `usuario` | Conta: e-mail, senha (hash de scrypt) e o segredo do segundo fator, **cifrado**. |
| `sessao` | Quem está logado agora. Guarda o **hash** do cookie, nunca o cookie. |
| `maquina` | Cada computador que reporta ao painel. Guarda o **hash** do token do agente. |
| `pareamento` | O código de seis dígitos que casa uma máquina com uma conta. Guarda o HMAC do código, com prazo e teto de tentativas. |
| `projeto_conectado` | Que projetos cada máquina enxerga. Ver de novo não duplica. |
| `pendencia_arquivada` | O sumiço definitivo de um alerta — **com motivo e data obrigatórios**. |

### Três decisões que valem ser ditas

**Nenhum segredo entra em claro, desde o primeiro dia.** Senha vira hash de
`scrypt` com sal próprio; cookie e token de agente viram hash de SHA-256; código
de pareamento vira HMAC com a chave do cofre; o segredo do segundo fator entra
cifrado. A tentação era deixar isso "para a etapa 9, quando o login existir" — e
o preço dessa espera seria migrar dado e rotacionar segredo depois, com conta de
gente já dentro. A cifra é de biblioteca padrão (HMAC-SHA256 em modo contador,
mais um selo HMAC), porque este projeto não tem dependência externa e a CI cobra
isso. Texto adulterado é **recusado**, nunca devolvido como lixo.

**A chave do cofre não é versionada, e não nasce sozinha em qualquer lugar.**
`cofre.chave` está no `.gitignore` — versionar a chave é o mesmo que não ter
chave — e o programa só o cria quando o ambiente é explicitamente local. As três
variáveis que mandam nisso estão logo abaixo.

**Arquivar exige motivo**, e a regra mora **no banco**, não só no Python:
`pendencia_arquivada` tem um `CHECK` que recusa motivo em branco, e desarquivar
carimba a volta em vez de apagar a linha. Invariante de negócio que vive fora do
banco é uma promessa, não uma regra — hoje há um escritor, daqui a duas etapas
há três. Alerta que some para sempre
sem rastro é pior que o "esconder por 24 h" que ele substitui: daqui a três meses
ninguém consegue responder por que aquilo parou de aparecer.

### A chave do cofre, e por que ela se recusa a nascer sozinha no servidor

Duas variáveis de ambiente mandam nisso:

| Variável | Para quê |
|---|---|
| `DERVS_COFRE` | A chave, em texto. **Mínimo de 32 caracteres** — abaixo disso uma frase se quebra fora do ar, a partir de uma cópia do `hub.db`. Gere com `python -c "import secrets;print(secrets.token_urlsafe(32))"`. |
| `DERVS_AMBIENTE` | `local` autoriza o programa a criar um `cofre.chave` sozinho nesta máquina. Em qualquer outro valor — inclusive vazio — ele **recusa subir** em vez de inventar uma chave. |
| `DERVS_COFRE_ARQUIVO` | Tira o `cofre.chave` da pasta servida. Importa na etapa 16: um `root /app` no nginx entregaria a chave mestra por HTTP. |
| `DERVS_PROXIES_CONFIAVEIS` | Lista de IPs, separados por vírgula, autorizados a mandar `X-Forwarded-For`. **Vazia por padrão, e tem de continuar vazia sem proxy na frente**: se qualquer um pudesse dizer de onde veio o pedido, o teto de tentativas sumiria — bastaria variar o cabeçalho a cada chute. Importa na etapa 16: atrás do nginx, **toda** chamada chega como `127.0.0.1`, e sem esta variável o teto de cinco tentativas por quinze minutos vira um balde único para o mundo inteiro. Um estranho gastaria o teto de graça, e o dono nunca mais parearia máquina nenhuma. |

O motivo da recusa: se a variável for esquecida no servidor e o programa
fabricar outra chave, **todo segredo de segundo fator já guardado vira
"adulterado" e todo código de pareamento para de casar — sem uma linha de
aviso**. Falhar na subida é barulhento e reversível; falhar assim é silencioso
e caro. A chave também é derivada com `scrypt`, não com um SHA-256 solto: SHA-256
custa nada por palpite, e o selo do próprio texto cifrado confirma o acerto.

### Voltar atrás da etapa 8 exige apagar o `hub.db` — e isso custa

O código anterior a esta etapa **quebra** num banco já migrado: o `silenciar`
antigo usa `ON CONFLICT(id)`, que não casa mais com a chave. E quebra do pior
jeito: a leitura continua funcionando, então o painel abre normalmente e só o
"x" estoura — parece que voltar deu certo.

O `hub.db` é descartável para `medida` e `pendencia_vida`, que a próxima coleta
refaz. **Não é** para `historico` e `gasto`: são séries no tempo, e valor de
ontem não se recoleta. Apagar o banco para voltar atrás custa o histórico
inteiro e a conta de gasto do Actions — justamente o que o painel usa para
mostrar tendência.

### O `x` de 24 h ganhou dono — e isso era um defeito de segurança

`pendencia_estado` tinha `id` como chave primária e mais nada. Com um usuário
isso funciona. Com dois, o "x" de um **esconde o alerta do outro**, e não há
rota que conserte: o defeito está na forma da tabela. A revisão de segurança da
etapa 7 anotou isso como IDOR por desenho de esquema e mandou consertar aqui, na
migração — que é o único momento barato.

A chave passou a ser `(id, usuario_id)`. O SQLite não sabe trocar chave primária,
então `banco.migrar()` reconstrói a tabela; o que já estava lá vira do **dono
local** (`usuario_id = 0`), que é exatamente o que era — a decisão do dono desta
máquina. A migração roda em toda conexão, é barata (um `PRAGMA table_info`) e
inofensiva na segunda vez. Provado num `hub.db` do dia 26/08: a linha sobreviveu,
e o `x` da tela continua gravando.

## A memória do tempo — o painel passa a lembrar de ontem

Até 25/08/2026 o HUB respondia bem "o que precisa de mim agora?" e não respondia
nada sobre ontem. A tabela `historico` do banco tinha **uma linha**. Faltavam
três coisas que decidem se uma lista é usada ou ignorada:

1. **Idade.** Uma pendência nascida há uma hora e outra aberta há 23 dias
   apareciam iguais — mesmo tamanho, mesma cor, mesma linha.
2. **Progresso.** Lista que só cresce e nunca reconhece o que foi feito é lista
   que se aprende a fechar.
3. **Direção.** "Isto está piorando" é informação. "Existem 27 pendências" não é.

### Como funciona

Tabela `pendencia_vida` (`id`, `regra`, `projeto`, `gravidade`, `visto_em`,
`ultimo_em`, `fechada_em`). A cada coleta **local** bem-sucedida, o servidor
avalia as regras e atualiza a vida de cada pendência: quem apareceu ganha
`visto_em`, quem continua tem o `ultimo_em` renovado (**não** rejuvenesce), quem
sumiu ganha `fechada_em`. No mesmo instante um retrato numérico vai para o
`historico`.

Fica em tabela separada da `pendencia_estado` de propósito: aquela guarda
**decisão do dono** (silenciar por 24 h), esta guarda **observação do coletor**.
Misturar as duas faria uma faxina no banco apagar a escolha dele junto com a
medição.

**Por que o registro roda no laço de coleta e não no `/api/dados`.** Aquela rota
é disparada pelo navegador de 15 em 15 segundos. Gravar ali faria a aba dirigir o
banco — e, pior, com o painel fechado o dia inteiro o histórico ficaria vazio
justamente no dia em que ele não olhou. Painel que só lembra do que aconteceu
enquanto estava sendo olhado não tem memória: tem espelho.

Um erro no registro **nunca** derruba a coleta. O número na tela vale mais que o
registro histórico dele.

### A armadilha da estreia, e como ela foi fechada

Na primeira coleta depois desta mudança, **todas** as pendências abertas ganham
`visto_em = agora` — inclusive um grafo de código velho há 23 dias. Sem trava, a
tela estrearia com 27 selos de "nova" mentindo em uníssono, e o dono aprenderia
na primeira olhada que o selo mente.

Duas travas, uma em cada ponta:

- **`desde_o_inicio`**: quem já estava ali quando a memória começou tem a idade
  exata *desconhecida*. O campo `dias` vem `None`, nunca zero — zero é um número,
  e número errado num painel custa mais caro que número ausente.
- **`novas_24h` só conta quem nasceu depois do início da memória.** Sem isso, o
  briefing anunciaria "27 apareceram nas últimas 24 h" no primeiro minuto de
  vida. Nenhuma era nova: elas já estavam lá, só não havia quem lembrasse.

Mas não saber a idade exata não é não saber nada. A memória sabe há quanto tempo
**ela** existe, e a pendência que já estava aqui na estreia tem no mínimo essa
idade — daí o campo `dias_min` e o texto "aberta há mais de 9 dias". Enquanto a
memória tiver menos de um dia, a linha fica calada.

### O briefing matinal

Uma frase no topo, escrita por função pura a partir dos números. Duas regras a
separam de enfeite:

- **Com pendência alta aberta, ela nunca diz que está tudo certo.**
- **Nunca é genérica**: sempre cita número e nome de projeto.

Frase que não muda quando o dado muda é decoração, e decoração no topo de um
painel operacional é pior que espaço vazio — ensina a não ler o topo. Três
estados de dado produzem três textos diferentes, e isso é coberto por teste.

Ao lado dela, o placar: urgentes, novas hoje, fechadas nos últimos 7 dias, e um
sparkline em SVG puro da semana. **O placar de "fechadas" só aparece quando há o
que comemorar** — um "0 fechadas" permanente no topo da tela é uma repreensão
diária, não uma informação.

## O fim do ruído: dez linhas iguais viram uma

Em 25/08/2026, **10 das 27 pendências abertas eram a mesma regra** — grafo de
código velho — em dez projetos, cada uma com a mesma ação manual. São 37% da
caixa de entrada dizendo a mesma coisa: exatamente o mecanismo que o filtro da
regra 2 existe para evitar. Caixa que nasce com muitos alarmes iguais ensina o
dono a ignorar a caixa inteira, inclusive o alarme que importava.

`regras.agrupar()` dobra qualquer regra com **3 ou mais** ocorrências numa linha
só, com a contagem, a idade da mais velha e os projetos dentro. Com os dados
daquele dia, 27 pendências viraram **10 linhas**.

**Com uma exceção, em `NAO_AGRUPAR`: alerta de segurança nunca se dobra.** Dez
"grafo velho" são dez linhas dizendo a mesma coisa, com a mesma ação. Quatro
projetos com alerta de segurança não são: em 25/08/2026 iam de 6 críticos em 19
alertas a 93 alertas com 11 baixos. *"4 projetos com alertas de segurança
abertos"* é verdade e não ajuda — apaga justamente o número que diz por onde
começar. Medido no painel: o agrupamento entrega **14 linhas** em vez de 11, e
vale a troca.

**É uma visão, não um substituto.** O `/api/dados` continua mandando a lista
achatada em `pendencias`, e o agrupamento vai à parte, em `grupos`. O motivo é
concreto: o "×" de esconder por 24 h acha a pendência pelo `id`. Trocar o
formato de `pendencias` o quebraria. Aqui muda o desenho; a identidade não muda.

O grupo é um `<details>` de verdade, não um painel escrito à mão: o **Ctrl+F do
navegador acha o que está lá dentro** sem o dono precisar abrir.

## O site está no ar? E o que está lá é o que você escreveu?

O HUB media git, Docker, CI, alertas, cota e grafo — e não media a única coisa
que **o cliente percebe antes do dono**. Cinco projetos declaram `url_prod` no
`casos.json`, um deles marcado `criticidade: critica`. Site fora do ar não
produzia pendência nenhuma nesta tela.

### Regra 15 — o site não respondeu (alta)

`GET` na raiz, sem credencial e sem cookie, na cadência de 20 minutos da camada
`github`. **5xx ou ausência de resposta = fora do ar**; 3xx e 4xx contam como
servidor **vivo**, porque um 301 já é prova de que ele respondeu.

**Redirecionamento não é seguido.** Seguir o pulo levaria a requisição para um
domínio que este painel não escolheu.

> **O que esta regra NÃO garante.** Responder 200 na raiz não é o mesmo que
> estar funcionando. Banco caído atrás de uma home estática continua devolvendo
> 200. Isto pega o apagão, não a doença.

### Regra 16 — trabalho pronto e não publicado (média)

Commits na branch padrão do GitHub mais novos que o último deploy bem-sucedido.
Repositório sem workflow de publicação identificável fica **calado** — não saber
não é o mesmo que estar atrasado (invariante 2).

### O cuidado com produção

Esta é a única parte do HUB que toca em produção, e por isso ela tem interruptor:
`MEDIR_SITE` no topo de `coletar_github.py`. Desligar apaga a regra 15 e não muda
mais nada.

`url_segura()` barra `localhost`, rede interna, `.local` e qualquer esquema que
não seja web, **sem tocar em DNS** — a resolução de nome fica em `host_publico()`.
Estão separadas para o teste rodar offline: teste que consulta DNS é teste que
quebra a CI numa terça-feira qualquer.

Hoje o `casos.json` é escrito só pelo dono e nada disso é necessário. Entra assim
mesmo, pelo mesmo motivo que o `detalhe` do pedido de alteração virou número em
25/08: no dia em que essa lista vier de outro lugar, um endereço apontando para
`127.0.0.1` transformaria este coletor numa ferramenta de varredura de dentro da
máquina dele.

**Falha de medição não apaga medição boa.** `ok=None` é "não medi"; `ok=False` é
"caiu". Um blip de rede às 20h não pode fazer "site no ar" virar "site fora" —
mesmo cuidado que os alertas de segurança já tinham.

### Comando que falhou não vira zero medido

Até 26/08/2026 o `sh()` do coletor devolvia a mesma string vazia para dois fatos
opostos: "rodou e não havia nada" e "não rodou". Git ausente do PATH, repositório
corrompido ou permissão negada viravam, na tela, **"árvore limpa, 0 commits,
nunca publicado"** — e o painel oferecia um `git init` que estragaria um repo que
já tem GitHub.

O conserto tem quatro degraus, e o par `(deu_certo, saída)` é o de baixo:

| Peça | Antes | Agora |
|---|---|---|
| `coletar.executa()` | não existia; só `sh()`, que perdia o código de saída | devolve `(ok, saída)` |
| `coleta_git()` | seguia inventando zeros | sentinela no `rev-parse`; se falhou, devolve `{"versionado": true, "medido": false}` |
| `coleta_docker()` | `[]` para Docker mudo **e** para máquina sem contêiner | `None` quando o Docker não respondeu, `[]` quando respondeu vazio |
| Nota de prontidão | `"segredo"` lia chave ausente, `not None` dava `True` e **concedia o ponto de segurança sem olhar** | os critérios de `CRITERIOS_QUE_PEDEM_GIT` ficam sem veredito e aparecem como `?` |

Na tela: `?` em itálico na cor de alerta (nunca `—`, que parece "não tem", nunca
`0`, que parece medido), nota com `*` de parcial, e a regra 18 dizendo em
português que não deu para medir. Mesma lição de `portas_escutando()`, que já
separava `None` de vazio: **tela limpa por cegueira é indistinguível de boa
notícia, e é a pior mentira que um painel pode contar.**

## 203 alertas eram 32 pacotes: contagem não é risco

Até 25/08/2026 a linha de segurança dizia uma coisa só: *"93 alerta(s) de
segurança aberto(s) em medconsultoria."* Verdade, e mesmo assim enganava. Os 203
alertas dos quatro projetos foram baixados um a um com `gh api` naquele dia, e o
que apareceu foi isto:

| Projeto | Alertas | Críticos | Altos | Pacotes | Defeitos distintos |
|---|---|---|---|---|---|
| medconsultoria | 93 | 2 | 44 | 24 | 85 |
| odontologia-pericia | 71 | 1 | 40 | 13 | 62 |
| investrix | 20 | 0 | 12 | 9 | 17 |
| workspace-medconsultoria | 19 | **6** | 7 | 7 | 12 |

O projeto com **mais** alertas não é o mais perigoso, e o mais perigoso era o que
a tela mostrava como menor. Três leituras erradas saíam de um número certo:

1. **Contagem não é tamanho do trabalho.** 203 alertas, 32 pacotes distintos no
   total. Boa parte é dependência transitiva que sai num `npm update`.
2. **Contagem não é gravidade.** Os 11 alertas *baixos* do `medconsultoria`
   pesavam na tela igual aos 6 *críticos* do `workspace-medconsultoria`.
3. **O mesmo defeito era contado várias vezes.** Os 6 críticos do
   `workspace-medconsultoria` são **dois CVEs de `vitest`** (CVE-2025-24964 e
   CVE-2026-47429) repetidos por três manifestos. Três tarefas onde havia uma.

Hoje a mesma consulta GraphQL — **sem uma ida a mais na rede** — traz
`severity`, `package`, `ghsaId` e `dependencyScope` de até 100 alertas, e
`_resume_alertas()` devolve severidade, pacotes distintos, defeitos distintos e
escopo. A frase virou *"6 crítico(s) e 7 alto(s) entre 19 alerta(s) de segurança
em workspace-medconsultoria, em 7 pacote(s)"*, e o detalhe embaixo abre o resto.

### A tentação que foi medida e recusada

O GitHub diz, por alerta, se a dependência é `RUNTIME` ou `DEVELOPMENT`. A
tentação óbvia é rebaixar tudo que é `DEVELOPMENT` — *"vitest é ferramenta de
teste, não vai para produção"*. **Não dá, e isso foi medido, não suposto:** no
próprio `workspace-medconsultoria` o **mesmo `vitest`** volta `DEVELOPMENT` num
manifesto e **`RUNTIME` noutro**, porque num `package.json` ele está declarado
fora de `devDependencies`.

Rebaixar por escopo esconderia um crítico real de produção. O escopo entra na
tela como **fato**, na linha de detalhe, e `gravidade_alerta()` não olha para ele.

### Não saber não é o mesmo que estar seguro

A gravidade caiu para **média** quando não há nenhum crítico nem alto. Duas
situações sobem de volta para **alta**, de propósito:

- **Sem severidade medida** — coleta antiga no banco, ou permissão que concedeu
  o `totalCount` e recusou o detalhe.
- **Amostra** — o GraphQL lê 100 alertas por consulta. Repositório com mais que
  isso devolve amostra, o crítico pode estar justamente entre os que não vieram,
  e a frase passa a dizer *"pelo menos"* em vez de afirmar a distribuição.

Rebaixar por falta de medição seria mais uma forma de o painel mentir com número
certo — a mesma família dos quatro casos da seção de segurança.

### A ordem da lista também mentia

Consertar a frase resolveu metade. Com a severidade já no texto, as quatro linhas
ainda saíam `investrix` (12 altos, zero crítico) **antes** de
`workspace-medconsultoria` (6 críticos) — porque `i` vem antes de `w` no alfabeto.

`risco_alerta()` dá **100 por crítico e 1 por alto**, e esse peso desempata dentro
da gravidade. Um crítico ganha de qualquer número plausível de altos: são coisas
diferentes, não a mesma moeda. Moderado e baixo valem **zero** — são 47 dos 203
alertas reais e, se contassem, seriam eles a decidir o desempate.

O peso nunca atravessa gravidades: uma pendência média com risco alto continua
atrás de qualquer alta. Regra que não mede risco fica em zero e ordena pelo nome,
como sempre.

## O painel deixa de ser de uma máquina só, de verdade (etapa 11 do DERVS)

A etapa 8 abriu as tabelas para várias máquinas; a 11 é quem finalmente põe dado
de outra máquina lá dentro. O pacote `agente/` mede um computador e **manda** o
resultado para um DERVS remoto.

Conectar é um número de seis dígitos, gerado em **Conectar → Computadores**, no painel, e
digitado na outra máquina, **num terminal aberto dentro da pasta do DERVS** — a
que tem a pasta `agente`:

```
python -m agente.enviar --alvo https://SEU-DERVS --codigo 123456
```

Rodar de outra pasta responde `No module named 'agente'`. Esse erro é do Python,
não do número: ele acontece antes de o programa começar, por isso vem em inglês
e parece grave. Num PowerShell dá para fazer as duas coisas numa linha só:
`cd C:\caminho\do\dervs; python -m agente.enviar ...`

**Cada DERVS tem o banco dele.** Um número gerado no painel do servidor não vale
no DERVS da sua própria máquina, e o contrário também não — o segundo recusa, e
está certo. Confira se o `--alvo` é o mesmo endereço que você abriu no navegador
para gerar o número.

O roteiro completo — o que aparece quando dá certo, o que fazer em cada erro, e
como deixar reportando sozinho — está em
[`docs/operacao/conectar-uma-maquina.md`](docs/operacao/conectar-uma-maquina.md).

### Conectado não é autorizado (Fatia 2)

**Parear um computador nunca deu a ele o direito de rodar código.** A coluna
`maquina.executa` nasce `0`, e ligar é um segundo sim, explícito, no botão
**Deixar consertar aqui** da seção **Computadores** da tela **Conectar**. Enquanto ele estiver
desligado, o agente daquela máquina continua medindo e reportando — e a
resposta que ele recebe do painel vem sempre com `"tarefa": null`.

O roteiro de ponta a ponta — autorizar, decidir o que anda sozinho, o que
aparece na tela, e a verdade sobre o botão Parar — está em
[`docs/operacao/segundo-braco.md`](docs/operacao/segundo-braco.md).

### Quatro decisões que valem ser ditas

**O agente não escuta porta nenhuma.** Só sai conexão dele. Um agente que
aceitasse conexão seria uma porta nova numa máquina de casa, atrás do roteador,
sem ninguém olhando — e o que ele executaria do outro lado é justamente o que a
etapa 7 amputou do servidor. `test_agente.py` cobra isso lendo os arquivos do
pacote: `HTTPServer`, `bind(` e `listen(` reprovam a suíte.

**O envio de dado é o sinal de vida.** Não há rota de "estou vivo", e a ausência
dela é testada nominalmente. Com um sinal próprio, uma máquina com a coleta
travada continuaria reportando saúde, e o painel ficaria verde exatamente quando
parou de olhar — a pior mentira possível neste produto.

**O que segura seis dígitos são três travas**, e a terceira era dívida nomeada da
etapa 8: dez minutos de validade, uso único, e **cinco tentativas por origem**
(vinte no ambiente local). Por origem, e não um contador global: global deixava
um estranho trancar o pareamento de todo mundo com cinco chutes. Balcão próprio,
também, para gastar o teto do pareamento não trancar a entrada do dono pela capa.

**Nasceu a quarta classificação de acesso.** Além de `aberta`, `cortina` e
`dado`, a tabela `ROTAS` passou a ter `maquina`: quem prova ser máquina, e não
pessoa. Ela não exige cookie nem `Origin` — o agente não é navegador, e exigir
isso seria uma defesa que só atrapalha quem tem o token. Em troca, `test_rotas.py`
cobra que nenhuma rota de `/api/` aceite token de máquina: relatório roubado não
pode virar acesso ao painel.

### O que mede saiu de dentro do que grava

`coletar.main()` media e gravava na mesma função. Agora `coletar.medir()` mede e
devolve, e dois destinos consomem o mesmo resultado: o `hub.db` desta máquina e
um DERVS remoto. Sem isso, o agente teria de copiar as ~600 linhas que medem
projeto — e cópia vira duas versões no dia em que uma for corrigida, com a errada
passando calada.

Junto veio uma correção honesta: os avisos ("a raiz não existe nesta máquina",
"o Docker está mudo") deixaram de ser `print` e passaram a voltar na estrutura.
Quem recebe por HTTP não tem stdout para ler, e uma medição que não mediu nada
chegaria do outro lado com a mesma cara de uma que não achou nada.

### O que a etapa 11 **não** resolveu

A tabela `medida` continua com chave `(projeto, camada)`, sem dono. Duas contas
diferentes com um projeto de mesmo nome ainda escrevem uma por cima da outra —
como já acontecia com a coleta local. Não é regressão desta etapa, é o
multi-inquilino que falta; o `projeto_conectado`, esse sim, é por máquina.

## O que ainda não existe

Fases 3 e 4 da especificação (a **fase 2 está entregue**, seção acima) (`~/.claude/docs/superpowers/plans/2026-08-24-hub-do-dev.md`):

- **Fase 3 — entregue.** O briefing matinal e a divergência entre local e
  servidor estão nas seções acima, junto com a memória do tempo e o fim do
  ruído, que não estavam na especificação original e nasceram de medir a lista
  de verdade. Já eram: a **nota de saúde por projeto** e a **paleta de comandos
  (`Ctrl+K`)**.
- **Fase 4** — o `radar.py` do `~/.claude` passa a ler este banco em vez de
  coletar por conta própria, acabando com os dois coletores.

E, desde 26/08/2026, o roteiro do **DERVS** (`docs/superpowers/plans/dervs-fatia-1.md`):
banco multiusuário, login com segundo fator, e as telas refeitas. As etapas 13 a
15 são as telas — é lá que se decide o que volta a existir como botão, e por
qual caminho, agora que o servidor não executa mais nada.
