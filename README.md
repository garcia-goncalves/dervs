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
| `regras.py` | O motor das 14 pendências. Puro: entra dicionário, sai lista. |
| `execucao.py` | O botão **Resolver**: dispara uma sessão do Claude Code numa cópia isolada e abre o pedido de alteração. Seção própria abaixo. |
| `test_execucao.py` | 72 testes das decisões do Resolver. `python test_execucao.py`. |
| `test_regras.py` | 30 testes do motor. `python test_regras.py`. |
| `test_servir.py` | 43 testes do proxy do grafo e da superfície do Resolver. `python test_servir.py`. |
| `coletar.py` | Camada **local**: git, Docker, portas, grafo, memória, variáveis. |
| `coletar_github.py` | Camada **github**: CI, PRs, alertas. Uma consulta GraphQL em lote. |
| `coletar_pesado.py` | Camada **pesado**: cota do Actions e `npm audit`. |
| `casos.json` | Camada **curada**, escrita à mão. Nenhum coletor toca aqui. |

`hub.db` é descartável e não é versionado: apagar só custa uma coleta.

## As três cadências

| Camada | De quanto em quanto | O que mede | Por quê |
|---|---|---|---|
| local | 60 s | git, Docker, portas, idade do grafo, memória, variáveis | só disco, é barato |
| github | 20 min | CI, pedidos de alteração, alertas de segurança | rede e cota — nada disso muda em um minuto |
| pesado | 24 h | cota de minutos do Actions, `npm audit` | caro: várias chamadas e rede por repositório |

**A tela nunca espera coleta.** Lê o último valor do banco, mostra na hora e
troca o número quando o novo chegar. Cada camada exibe há quanto tempo foi
medida e esmaece quando envelhece — se o painel mentir uma vez, o hábito morre.

## As 14 pendências

| # | Regra | Gravidade | Ação |
|---|---|---|---|
| 1 | CI vermelha | alta | abrir o que falhou |
| 2 | Container que devia estar no ar e caiu | alta | subir |
| 3 | Alerta de segurança aberto (Dependabot) | alta | ver os alertas |
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
2. O painel cria uma **cópia isolada** do repositório com `git worktree`, em
   `~/.cache/hub-worktrees/<projeto>/<8 caracteres>` — de propósito **fora** de
   `source\repos`, porque toda subpasta daquela raiz vira projeto medido e o
   painel passaria a medir as próprias cópias.
3. A sessão roda **dentro da cópia**. A pasta original do projeto não é tocada,
   e `git status` nela continua vazio durante e depois.
4. O painel lê a saída linha a linha e mostra o progresso ao vivo: uma frase em
   português, o log cru com carimbo de hora, e o custo.
5. Terminou bem: commit na cópia, `git push` de um ramo `hub/...` e
   `gh pr create`. **Nunca** `push` na `main`, **nunca** `gh pr merge`.
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
um pedido. O teto adotado é **US$ 3** por execução, e a única garantia real de
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

`Bash` está na lista branca e **não** fica preso à cópia. O shell não conhece
fronteira de pasta, e a cópia é um `git worktree`, que compartilha o `.git` do
projeto de verdade e o remoto já autenticado: um `git push --force` saído de lá
alcança o repositório real. `Bash` fica porque sem ele a sessão não roda teste
nem commita — e aí o recurso não existe. O que protege não é a lista de
ferramentas; é não deixar texto de estranho chegar ao prompt (seção acima).

A sessão filha **roda os hooks** do `~/.claude` do dono e o
`.claude/settings.json` versionado do projeto-alvo. Medido: seis hooks
`SessionStart` dispararam dentro dela. A forma de evitar isso seria `--bare`, que
**não funciona** com o login por assinatura desta máquina (responde
`Not logged in`; `--bare` só aceita chave de API). Isso é **risco declarado, não
resolvido** — se um hook do dono abortar a sessão filha, o sintoma é a sessão
terminar sem tocar em arquivo nenhum, e o log cru da tela mostra o motivo.

## O que ainda não existe

Fases 3 e 4 da especificação (a **fase 2 está entregue**, seção acima) (`~/.claude/docs/superpowers/plans/2026-08-24-hub-do-dev.md`):

- **Fase 3** — falta o briefing matinal e a detecção de divergência entre local
  e servidor. Já entregues: a **nota de saúde por projeto** e a **paleta de
  comandos (`Ctrl+K`)**, ambas com seção própria acima.
- **Fase 4** — o `radar.py` do `~/.claude` passa a ler este banco em vez de
  coletar por conta própria, acabando com os dois coletores.
