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
| `servir.py` | Serve a página, o `/api/dados` e o `/api/acao`. Agenda as três coletas. |
| `banco.py` | O SQLite (`hub.db`): uma linha por (projeto, camada), com carimbo de tempo. |
| `regras.py` | O motor das 14 pendências. Puro: entra dicionário, sai lista. |
| `test_regras.py` | 30 testes do motor. `python test_regras.py`. |
| `test_servir.py` | 35 testes do proxy do grafo. `python test_servir.py`. |
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

## O que ainda não existe

Fases 3 e 4 da especificação (a **fase 2 está entregue**, seção acima) (`~/.claude/docs/superpowers/plans/2026-08-24-hub-do-dev.md`):

- **Fase 3** — paleta de comandos (`Ctrl+K`), nota de saúde por projeto,
  briefing matinal, detecção de divergência entre local e servidor.
- **Fase 4** — o `radar.py` do `~/.claude` passa a ler este banco em vez de
  coletar por conta própria, acabando com os dois coletores.
