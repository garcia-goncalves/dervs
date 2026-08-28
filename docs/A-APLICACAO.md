# O DERVS — o que é, e tudo o que vai ter

**Este é o documento único.** Se algum outro arquivo deste repositório contradizer
este, este vence. Ele existe por um motivo declarado pelo dono em 27/08/2026:

> *"Parece que não sei se vc se lembra de tudo o que falamos que terá na aplicação...
> estou confuso."*

A confusão era real e não era culpa dele: as decisões estavam espalhadas por um
briefing, uma especificação, um documento de design, um plano de 17 etapas e mais de
trinta anotações de memória. Nenhum deles respondia, sozinho, *o que esta aplicação é*.

Última revisão: 28/08/2026.

---

## 1. Em uma frase

**O DERVS é o posto de comando de quem programa: uma tela em `dervs.com.br` onde você
bate o olho e sabe, de cada projeto seu, se dá para confiar no que está no ar, o que
falta fazer, e o que quebrou — e aperta um botão para o Claude consertar.**

**A partir da Fatia 2, aberta em 28/08/2026, ele também tem braços.** Pedido do dono, com
as palavras dele: *"quero sim que o DERVS seja independente — analisa, executa, programa,
desenvolve, monitora, resolve problemas, tudo"*. O que executa é o **agente**, o programa
instalado no computador dele e na VPS, dirigindo o Claude Code. O painel manda, o agente
faz, e o semáforo do §7 decide o que anda sozinho e o que espera um clique.

A ordem importa e não se inverte: **ele mede primeiro e age depois.** Um braço que conserta
em cima de uma leitura errada estraga mais rápido do que uma pessoa distraída.

A pergunta que ele responde, todo dia de manhã, em cinco minutos:

> **Posso confiar no que está no ar?**

Nenhuma outra ferramenta responde essa pergunta hoje. Elas respondem "o container está
de pé?" ou "a verificação automática passou?". Nenhuma responde se o código que está
publicado é o mesmo código que está no GitHub — e essa diferença é a causa mais comum
do defeito "já corrigido" que reaparece.

## 2. Para quem

**Dois perfis, nesta ordem de prioridade.**

**1. O Thiago e o André, hoje, diariamente.** O Thiago decide o produto e não opera
terminal: a tela tem de responder "está tudo ok?" sem que ele leia um log. O André
programa e vai querer ver a prova por baixo. A mesma tela serve os dois em profundidades
diferentes — **selo na frente, prova atrás**.

**2. O desenvolvedor sozinho ou a dupla, com muitos projetos parados — depois.** Chega
porque perdeu tempo descobrindo tarde. Não tem equipe de plataforma: **se a ferramenta
pedir manutenção, ele desinstala.**

Nada é amarrado aos projetos do dono. Qualquer pessoa conecta as próprias pastas, a
própria conta do GitHub e o próprio servidor pela tela de configuração — nunca editando
arquivo.

**A armadilha que mata este tipo de produto, e que a pesquisa de mercado confirmou:** não
é falta de função, é **custo de manter o próprio painel**. Um portal auto-hospedado
concorrente exige de 3 a 12 engenheiros dedicados. O DERVS tem de ser leve de manter, ou
não existe.

## 3. As três promessas, nesta ordem

1. **Eu confio no que está no ar.**
2. **Eu sei o que falta.**
3. **Eu aperto um botão e o Claude conserta.**

A ordem é obrigatória. Consertar antes de confiar na leitura é automatizar em cima de um
número que pode estar errado.

## 4. O que o DERVS mostra

### 4.1. O selo — quatro estados, nunca três

Cada projeto tem um selo. Ele tem **quatro** estados, e o quarto é o mais importante:

| Estado | O que quer dizer |
|---|---|
| **saudável** | "Tudo o que dá para medir passou." |
| **atenção** | "Funciona, mas alguma coisa vai piorar." |
| **quebrado** | "Alguma coisa reprovou agora." |
| **sem dados** | "Não consegui medir." — nunca "não se aplica", nunca "OK" |

**Por que quatro e não três:** sem o quarto, um projeto que ninguém conseguiu medir
apareceria verde. Verde por ausência de problema, não por saúde. É a mentira por omissão,
e é o pecado capital deste produto.

Cada selo mostra **cor, forma, símbolo e a palavra escrita** — os quatro juntos. Quem não
distingue verde de vermelho tem de conseguir usar a tela.

**Clicar no selo abre a conta que o gerou.** Sempre. Um selo que não se abre é um palpite
com cara de dado.

### 4.2. As três colunas — o coração do produto

De cada projeto, três lugares, lado a lado:

| No seu computador | No GitHub | No ar |
|---|---|---|
| branch, trabalho não salvo, commits não enviados, chaves do `.env`, containers, portas, editor aberto | verificação automática, pedidos de alteração abertos, pendências abertas, alertas de segurança | versão publicada, site respondendo, certificado, cota gasta |

**A diferença entre as três é o produto.** É o que se chama *drift*: o servidor rodando
uma versão diferente do GitHub, ou o seu computador com dez commits que nunca subiram.

**Isto é o diferencial confirmado por pesquisa: não existe ferramenta pronta que meça
essa diferença.** É código nosso, e é o motivo de o DERVS ter razão de existir.

### 4.3. O carimbo — todo número diz quando foi medido

Nenhum número aparece na tela sem a hora em que foi medido. Três cadências, de propósito:

| Camada | De quanto em quanto | O que custa |
|---|---|---|
| do seu computador | 60 segundos | nada — só lê disco |
| do GitHub | 20 minutos | rede e cota |
| pesado (cota de execução, auditoria de dependência) | 24 horas | caro |

**A tela nunca espera nenhuma delas.** Ela lê sempre o último valor guardado e mostra o
carimbo.

### 4.4. Quando o agente do seu computador para de responder

Este é o caso em que a maioria das ferramentas mente. O DERVS não:

| Tempo em silêncio | O que a tela faz |
|---|---|
| menos de 3 min | nada |
| 3 a 15 min | faixa amarela; os dados do computador ficam acinzentados, **com o carimbo da última medição** |
| mais de 15 min | as medições que dependem do computador **calam**; as do GitHub seguem, porque o servidor mede sozinho |
| mais de 24 h | o computador vai para "desconectados". **Nenhum dado é apagado.** |

**Ausência de agente produz ausência de camada, nunca camada vazia.**

## 5. O que o DERVS faz

### 5.1. As três conexões

Tudo pela tela, nunca editando arquivo.

**a) A pasta do seu computador.** Você escolhe a pasta; o DERVS varre e descobre sozinho
os projetos que estão lá — tipo (Node, Python, .NET), endereço do git, containers, portas.
O padrão sugerido é `source/repos`, mas a escolha é sua. *Hoje isso é um arquivo escrito à
mão. Deixa de ser.*

**b) A sua conta do GitHub.** Já construído: aplicativo do GitHub com token de vida curta
(uma hora). O que fica guardado no banco é o número da instalação, que **não é segredo**.

**c) O seu servidor.** **Sem chave SSH.** O DERVS observa por HTTPS e publica acionando o
próprio GitHub. Nunca guarda a chave da sua casa.

### 5.2. O botão consertar — com aprovação de um clique, nunca sozinho

O Claude analisa, propõe, **e para**. Você vê o que ele quer mudar e aprova com um clique.
Ele abre um pedido de alteração; ninguém mescla nada sem você ver.

**Por que nunca automático:** a ferramenta que atualizava containers sozinha foi
arquivada em 17/12/2025, e o motivo escrito pela própria comunidade foi *"mudança
silenciosa é fácil de não perceber"*. Repetir esse erro é conhecido e evitável.

**Três travas que já existem e são inegociáveis:**
- **Teto de R$ 50 por dia.** Conta o que a fila gasta e o que o botão gasta, juntos.
- **O Claude não pode mexer nos próprios testes.** Se o remendo tocar um arquivo de
  teste ou escrever valor num `.env.example`, é reprovado automaticamente.
- **Só pendência mecânica, com gabarito.** Nada de "conserta o que achar".

### 5.3. Arquivamento permanente

"Isto está certo assim" some **para sempre**, por regra e por projeto. Hoje o painel
silencia por 24 horas e volta a cutucar todo dia, para sempre — e é assim que se treina
alguém a ignorar a lista inteira.

### 5.4. A tela inicial responde "o que eu faço agora?"

**Decisão de produto, tomada aqui.** A tela inicial não é uma lista de tudo. É **uma ação
recomendada por vez, com o porquê junto**, e a lista completa atrás de um clique.

Uma lista de 203 alertas não é informação: é ruído que ensina o dono a fechar a aba.

## 6. Como é feito por dentro

**Três peças, com fronteira dura entre elas.** A fronteira é o desenho principal, não
organização: é ela que garante que a parte perigosa nunca alcance banco nem segredo.

| Peça | Linguagem | O que faz |
|---|---|---|
| **`dervs-core`** | Python | A tela, o login, o banco, as 16 regras, a fila, o custo, a barreira de comando, a leitura do GitHub |
| **`dervs-agent`** | Python | Roda no seu computador. Lê git, containers, portas, editor aberto. **Não abre porta nenhuma** — só faz saídas |
| **`dervs-live`** | Node | Só na Fatia 3: terminais e a lousa de agentes. Processo separado, **sem acesso ao banco** |

**Por que o núcleo é Python e não Node:** reescrever apaga 988 testes que já passam, e
junto vão as duas defesas do produto — a barreira de comando (que já sobreviveu a um
contorno real) e a trava que reprova o remendo do Claude. Decidido pelo contrato, não por
gosto.

**As quatro regras da fronteira:** o `dervs-live` nunca abre o banco; nunca recebe
credencial, só um passe temporário por sessão; toda regra de negócio é Python, o Node só
transporta bytes; e ele não entra no servidor de produção na Fatia 1.

**Guarda de segredo — a regra é preferir não guardar.** O que sobrar é cifrado em duas
camadas, com a chave-mestra fora do banco. **A tela nunca mostra um segredo de volta**,
nem para conferir: mostra "configurado em 27/08" e um botão "substituir".

## 7. O que o DERVS nunca vai fazer

Isto é tão parte do produto quanto o que ele faz.

- **Nunca agir sozinho no que é vermelho.** *Reescrito em 28/08/2026, por decisão do dono
  ao abrir a Fatia 2.* A regra antiga dizia "toda ação passa por um clique seu", e ela
  impedia o que ele pediu com todas as letras: *"que o Claude Code cuide de TUDO, resolva
  qualquer problema, sem eu precisar colocar a mão"*. A regra nova é um **semáforo**: cada
  tipo de tarefa nasce verde ou vermelha, a cor é visível na tela, e o dono repinta quando
  quiser. **Verde** roda sozinho e avisa depois — formatação, dependência, link quebrado,
  teste que faltava. **Vermelho** para e espera o clique — login, pagamento, banco de
  dados, exclusão, e **publicar, que é vermelho para sempre e não pode ser repintado**.
  Todo verde é reversível por construção: vira commit num branch, nunca vai direto ao ar.
  O que **não** mudou: nada acontece sem ficar registrado, e o dono vê o diff em português.
- **Nunca mostrar número sem dizer quando foi medido.**
- **Nunca inventar estado.** Não mediu, diz "sem dados".
- **Nunca pôr um modelo de linguagem no caminho da medição.** Medir é código comum e
  determinístico: lê o commit que está no ar, lê o commit do GitHub, compara. Um LLM que
  "acha" que está tudo bem é exatamente o número errado com cara de certo que a segunda lei
  deste repositório proíbe. A IA entra depois de medir — para explicar, decidir e consertar,
  nunca para apurar.
- **Nunca abrir um terminal na internet aberta.** Continua valendo na Fatia 2, e é por isso
  que o trabalho executa no **agente** — o programa instalado no computador e na VPS, que
  não escuta porta nenhuma e só pergunta ao painel se há tarefa. Nenhuma rota do servidor
  executa comando, e o teste que varre as rotas continua de pé. O terminal interativo no
  navegador está adiado para a Fatia 3, e não entra sem uma decisão nova e escrita.
- **Nunca guardar chave SSH do seu servidor.**
- **Nunca mostrar texto em inglês na interface.**
- **Nunca ter cadastro público** enquanto for de vocês dois. A estrutura de vários
  usuários nasce pronta; a porta nasce fechada.
- **Nunca virar bot de WhatsApp.** A biblioteca disponível é uma sessão não oficial,
  frágil e contra os termos de uso. Descartado do produto, não adiado. Telegram fica.

## 8. As telas — seis, e só seis

Direção visual escolhida: **Torre de Controle**. Preto, branco e verde.

1. **Entrar** — a cortina. Login forte, cadastro fechado.
2. **Painel** — a ação recomendada, a frase de resumo, e um selo por projeto.
3. **Projeto** — as três colunas, e a prova de cada selo.
4. **Conectar projeto** — escolher a pasta, a conta do GitHub, o servidor.
5. **Computadores** — quais estão conectados, quando cada um deu notícia.
6. **Alerta** — o que houve, o que fazer, e "isto está certo assim".

**A regra dura da cor:** verde é **estado saudável**, nunca cor de marca. Botão, link e
cabeçalho são quase-preto no tema claro e quase-branco no escuro. Se o verde virar cor de
enfeite, o selo verde para de significar alguma coisa no dia em que mais importa.

## 9. O vocabulário — a mesma coisa tem sempre o mesmo nome

Nomear é trabalho de produto, não detalhe. O critério: **isso explica sozinho?**

| Diga | Nunca |
|---|---|
| painel | dashboard |
| publicar / publicação | deploy, deployar |
| verificação automática | CI, pipeline |
| medição / medir | scan, coleta, sync |
| **computador** | máquina, host, node, runner |
| agente | daemon, worker |
| pendência | issue, task, débito |
| entrar / sair | login, logout |
| excluir | deletar |
| carregando | loading |
| commit | *(mantém — é o nome que o dev usa)* |

**Mudança decidida em 27/08/2026: "máquina" vira "computador".** O dono apontou "MÁQUINA"
como o exemplo do que estava confuso, e ele tinha razão — "máquina" é jargão de
infraestrutura herdado do banco de dados. Toda pessoa sabe o que é um computador. A
palavra aparece na tela de "Computadores", no pareamento e na quarta classe de acesso.

## 10. O ferramental do Claude — decisão de 27/08/2026

O dono pediu que o DERVS também cuidasse dos agentes, MCPs, skills e plugins do Claude
Code. **Entra no produto, com um recorte importante.**

**O que o DERVS faz:** mostra o que está ligado, **quanto cada peça custa por chamada**,
e o que usar em cada tipo de tarefa. Liga e desliga com um clique. Esse número — o custo
fixo do ferramental — é invisível hoje e é o item de maior impacto na conta.

**O que o DERVS não faz: não inventa formato próprio.** Em 06/08/2026, Amazon, Anysphere,
Microsoft, OpenAI e Vercel publicaram juntos o **Agent Plugins 1.0.0** — padrão aberto
para empacotar skills e MCPs. Já existem gerenciadores prontos. Construir o nosso formato
três semanas depois desse lançamento seria remar contra o mercado inteiro e virar
manutenção eterna — exatamente o que mata este tipo de produto.

**Fatia 4.** Depende de o login e a fronteira de segurança estarem provados: um painel que
liga e desliga ferramenta do agente é uma superfície de ataque de primeira ordem.

## 11. O caminho — o que está pronto, o que falta

> **Estado em 28/08/2026, fim do dia: a Fatia 1 está FECHADA e NO AR.** As 17 etapas
> entregues, 1095 testes em 19 arquivos, e `https://dervs.com.br` publicado e conferido
> (etiqueta `publicado-20260828-203019`). O que segue abaixo descreve como se chegou até
> aqui; o que **falta** começa em "Depois disso, Fatia 2".

**Entregue (as 17 etapas, 1095 testes passando):** a fusão dos dois repositórios com
as duas autorias preservadas · a verificação automática escalonada · a amputação de toda
rota que executava comando · o banco de vários usuários · o login com cortina e entrada
pelo GitHub · o motor do selo de quatro estados · o agente do computador e o pareamento
por código de seis dígitos · as pendências do GitHub e o drift · a troca de chave por
token do aplicativo do GitHub, conferida byte a byte contra o OpenSSL · a paleta e a
tipografia em tokens, servidas do próprio domínio · **e as telas, em português, com o
selo de quatro estados ligado ao motor e "isto está certo assim" gravando no banco.**

**A etapa 16 fechou o caminho até o ar, e em 28/08/2026 ele foi percorrido.** Existem a
imagem de produção, o arquivo que descreve o container no servidor, a configuração do
nginx e o workflow de publicação — que só dispara por botão, com a palavra `PUBLICAR`
digitada, e que sobe a imagem e bate na porta dela antes de trocar o que está no ar. Os
segredos foram gravados, o dono deu o sinal, e o site está publicado com duas contas e uma
máquina reportando. O roteiro está em `docs/operacao/publicar-no-servidor.md`.

**A primeira subida ensinou cinco coisas que só existem fora do localhost**, e elas estão
em `docs/esteira/dervs/verificacao.md`. A pior: `test_design.py` reprovava e devolvia
código de saída zero, e uma publicação inteira foi ao ar com quatro falhas dentro, com o
passo marcado como sucesso. **A verificação automática decide pelo código de saída — teste
que não o repassa não é teste, é decoração.**

**O que a etapa 16 achou, e vale registrar porque é o tipo de erro que volta:** o
`Dockerfile` não era aberto desde a etapa 7. Entre uma coisa e outra nasceram sete
arquivos de runtime — `autenticacao.py`, `cortina.py`, `passkey.py`, `p256.py`,
`index-cortina.html`, `portas.html` e a pasta `assets/` — e nenhum entrava na imagem. Ela
morria no primeiro `import autenticacao`, e a verificação automática ficava verde o tempo
todo, **porque ela roda os testes, não a imagem**. Agora `test_imagem.py` compara a lista
de cópia com o que `servir.py` de fato importa, seguindo import por import, e o workflow
de publicação sobe o container antes de publicar. Rodado contra o `Dockerfile` antigo, o
teste acusa os oito arquivos.

**Uma contradição achada na etapa 14, decidida pelo dono em 28/08/2026.** O desenho pedia
duas coisas que não cabem juntas: "10 projetos visíveis sem rolagem em 360×640" e uma
linha de projeto com *selo · nome · o motivo em uma frase · o carimbo*. Medido no
navegador, a linha com esse conteúdo ocupa cerca de 90 a 113 px — sete linhas enchem os
640 px, e isso sem contar a frase de resumo, a régua de quatro contadores e a ação
recomendada, que somam mais 350 px.

**O que a medição prova, dito com precisão:** não cabe *com o motivo em duas linhas e com o
topo atual*. Cortar o motivo para uma linha só abaixo de 400 px encolheria a linha em uns
20 a 25 px e levaria de 5-7 para 8-9; enxugar a régua de contadores ou a ação recomendada
ganharia mais. Nenhum dos dois chega a 10 — dez linhas em 640 px pediriam 64 px por linha
*com zero de topo*. Registrado porque a frase fácil ("chegar a 10 exige tirar o motivo") é
mais categórica do que a régua permite, e uma frase categórica errada num documento
aprovado encerra uma discussão que ainda podia render.

**A meta mudou: são 5 a 7 projetos por tela, com o motivo visível.** O número 10 estava
medindo a coisa errada. A promessa do DERVS é "eu sei o que houve sem clicar" — dez nomes
com um selo colorido ao lado obrigam a abrir cada um para descobrir o que aconteceu, e
trocam um clique economizado na rolagem por dez cliques gastos na investigação. Rolar não
é um defeito; abrir dez telas é. **A meta verificável passa a ser:** em 360×640, as
primeiras linhas visíveis mostram *selo, nome, motivo e carimbo* juntos, e o selo é
legível a um braço de distância. A contagem deixa de ser critério.

**As etapas 16 e 17 foram entregues em 28/08/2026.** A conferência final está colada em
`docs/esteira/dervs/verificacao.md`, com a saída dos oito comandos, com o que eles **não**
provam (conferido clicando), e com as pendências nomeadas. Duas delas foram fechadas no
mesmo dia — o `painel.js` que saía sem sessão, e a conta criada errada que não dava para
apagar. **Duas continuam abertas e as duas dependem só da mão do dono:** cadastrar uma
chave de acesso e gerar os códigos de papel (hoje o GitHub é a única porta da conta), e o
MX nulo do domínio, que só importa no dia em que o DERVS precisar enviar e-mail.

**A etapa 15 entregou o teste que reprova design errado**, e vale saber o que ele *não*
faz: seis dos oito itens da lista do desenho são verificados contra os arquivos de
verdade; **dois exigem olho humano** — a linha de projeto em 360×640, e cada botão fazer o
que promete. O teste imprime esses dois na própria saída, em vez de se calar. Uma lista de
oito com seis verificados e dois calados se lê como oito verificados, e essa impressão é
pior que a lacuna.

**Depois disso, Fatia 2:** descoberta automática de pasta, conectar servidor e conta pela
tela, e o botão consertar. **Fatia 3:** terminais e lousa de agentes. **Fatia 4:** o painel
do ferramental do Claude, e o Telegram.

### O pedido do dono em 28/08/2026, à noite — o que abre a Fatia 2

Palavras dele, transcritas para não virarem lembrança minha:

> "Quero a fusão das aplicações conforme combinado (dervs-hub + painel-projetos) e muito
> mais. Quero tudo que um DEV precisa."

**Cuidado com a palavra "fusão" aqui, porque ela já foi usada para outra coisa.** A fusão
dos **repositórios** está entregue desde a etapa 1: o `dervs-hub` do André vive em
`vivo/`, como subárvore, com os 13 commits dele preservados. O que ele está pedindo agora
é a fusão das **capacidades** — trazer para o DERVS o que aquele código faz (terminais,
lousa, os agentes) **reescrito em Python sob as regras deste repositório**, que é
exatamente o que a linha travada do §12 manda: *"a camada de execução do `dervs` antigo é
reescrita, não endurecida"*.

**Nada de `vivo/` vai para o ar como está.** Aquele código abre um terminal de verdade sem
pedir autenticação — no `127.0.0.1` é ferramenta, publicado é execução remota aberta. Duas
barreiras independentes impedem, e `vivo/LEIA-ANTES.md` explica as duas.

**"Tudo que um DEV precisa" deixou de ser intenção e virou escopo em 28/08/2026.** A
esteira rodou na mesma noite: três pesquisas externas em paralelo com a entrevista, duas
decisões de produto tomadas pelo dono, e **o briefing aprovado por ele no portão 1**.

> **O contrato da Fatia 2 mora em `docs/esteira/dervs-fatia-2/briefing.md`.** Ele é quem
> diz o que entra, o que fica de fora com destino nomeado, e como cada coisa se prova.

O recorte, em uma linha: **a Fatia 2 constrói o trabalhador** — o agente ganha a capacidade
de disparar o binário `claude` sobre um repositório e devolver o resultado; o mesmo agente
instalado na VPS vira o segundo braço. Junto vêm o semáforo, a caixa efêmera, o freio de
gasto que trava antes de disparar, e a tela onde o dono acompanha e aprova.

**Adiado com destino escrito, não descartado:** terminal no navegador, a lousa, o canivete
de 15 ferramentas avulsas e o **Codex** vão para a Fatia 3; editor de código e o
ferramental do Claude (§10) para a Fatia 4. O Codex sai desta fatia com a tomada pronta —
a interface do executor nasce com duas implementações previstas, e ligá-lo depois é
acrescentar uma, não refazer nada.

**Por que o Codex não entra agora, com o número:** só compensa orquestrar dois fornecedores
quando há 3 ou mais tarefas independentes de 15+ minutos cada; a fila do DERVS é de
correções de 2 minutos. O que a medição sustenta é **roteamento por tipo de tarefa** —
Claude escreve melhor código que atravessa vários arquivos (87,6% × 85,0% no SWE-bench
Verified), Codex opera melhor terminal e infraestrutura (81,8% no Terminal-Bench 2.0). Isso
é uma coluna a mais na tabela `fila`, não uma arquitetura a mais.

## 12. O que não se relitiga

Decisões travadas. Mudar qualquer uma exige um motivo novo, escrito.

- Três peças com fronteira dura; o agente **não escuta porta nenhuma**.
- Núcleo em Python, não Node.
- A camada de execução do `dervs` antigo é **reescrita**, não endurecida.
- Mesclagem automática é privilégio do robô de dependências.
- Teto de R$ 50 por dia na fila.
- Só pendência mecânica, com gabarito.
- A fila mora dentro do painel — **nada no GitHub Actions** (a cota já estourou uma vez).
  *A parte "só quando o dono manda" foi substituída em 28/08/2026 pelo semáforo do §7:
  vermelho espera o clique, verde anda sozinho dentro do teto de gasto. O motivo novo e
  escrito é o pedido do dono ao abrir a Fatia 2. Publicar continua exigindo a mão dele.*
- O selo tem **quatro** estados.
- Arquivamento é permanente, não 24 horas.
- Publicação nunca é automática: só por botão, depois do sinal do dono.

## 13. Dívidas conhecidas, ainda abertas

- **Pendência #10** — peneirar o nome do repositório na entrada, e não na hora de montar a
  consulta. Defeito que já existia.
- ~~**Quando o servidor existir** — levar as identificações e os segredos para lá, e
  convidar cada pessoa.~~ **Pago em 28/08/2026:** as credenciais do OAuth chegam ao
  `/opt/dervs/.env` pelo workflow (`f2adc52`), e o workflow convida os donos a partir de
  `vars.DERVS_DONOS`, uma linha por pessoa, idempotente **por pessoa** e não por contagem
  — o DERVS tem dois donos (`feed0e0`).
- **A troca de chave por token continua sem ter rodado contra o GitHub de verdade.** Está
  certa contra o OpenSSL e contra o formato documentado, e mais nada. O servidor agora
  existe, então a dívida deixou de estar bloqueada — falta exercitá-la.
- **Só uma forma de entrar.** As rotas de chave de acesso e de código de papel existem e
  são testadas desde a etapa 12; ninguém cadastrou nem gerou nada em produção. Perder a
  conta do GitHub hoje é perder o DERVS. Exige a mão do dono: o Windows só abre a janela
  do PIN para uma pessoa.
- **`dervs.com.br` publica um MX nulo** — o domínio declara que não recebe e-mail. Os
  endereços das contas são identificadores, não caixas.
- **A energia do painel é a assinatura Max 20x, não chave de API.** *Decisão do dono,
  28/08/2026: "usamos o Claude Code Max 20x pela conta do André e usamos muito. Quero usar
  o Max 20x que já pagamos. Não vamos usar API da Anthropic (isso seria um absurdo de
  caro)."* Isso já é o que acontece: `execucao.py:20` registra a medição de 24/08 — *"o
  login é por assinatura (OAuth)"*. **A regra da Anthropic que proíbe assinatura em uso
  programático vale para o Agent SDK**, e o DERVS não usa o SDK (ele traria 5 dependências
  e deixaria a CI vermelha) — ele chama o binário `claude`, o mesmo programa que o dono usa.
  Consequência de desenho: `--bare` continua indisponível (só aceita chave de API), e o
  isolamento segue por `--setting-sources ""` + `--strict-mcp-config`.
- **Com assinatura, o recurso escasso deixa de ser dinheiro e passa a ser COTA.** O Max 20x
  limita por janela de 5 horas e por semana, e as duas pessoas usam a mesma conta o dia
  inteiro. O jeito de falhar não é fatura alta: é **o painel comer a cota e o Claude parar
  para os dois no meio de uma terça-feira.** Por isso o freio da Fatia 2 conta **sessões e
  rodadas**, não reais, e reserva cota para o trabalho humano. O teto em reais continua no
  código como rede de segurança para o dia em que uma chave de API entrar — não como o
  limite que manda.
- **O teto do fornecedor não é cerca, e isso está medido aqui.** `--max-budget-usd` com teto
  US$ 0,10 terminou em US$ 0,4455 — estouro de 4,5× (`execucao.py:22`). E só o evento final
  traz custo, então durante a sessão o gasto é desconhecido. A única garantia real é matar o
  processo. Casos públicos de 2026 que definem o tamanho do perigo em quem usa API: US$ 1,3
  milhão em 30 dias com ~100 agentes soltos, e US$ 437 numa única noite num laço recursivo.
