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

**Segredo nenhum entra no banco ou na tela.** O coletor abre o arquivo de
variáveis só para extrair **nomes** de variável: a expressão regular para no sinal
de igual. Quem autentica no GitHub é o `gh` que o dono já logou.

## O que ainda não existe

Fases 2 a 4 da especificação (`~/.claude/docs/superpowers/plans/2026-08-24-hub-do-dev.md`):

- **Fase 2** — o grafo de código embutido, por proxy reverso em `/grafo/*`, com
  botão "Ligar o grafo" e montagem preguiçosa.
- **Fase 3** — paleta de comandos (`Ctrl+K`), nota de saúde por projeto,
  briefing matinal, detecção de divergência entre local e servidor.
- **Fase 4** — o `radar.py` do `~/.claude` passa a ler este banco em vez de
  coletar por conta própria, acabando com os dois coletores.
