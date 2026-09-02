# Spec — A Auditoria Profunda

> Fase 2 da esteira (Descoberta, modo enxuto: Analista + Arquiteto + Pesquisador
> + Diretor de escopo num despacho só). Escrita em 02/09/2026, depois de ler o
> código. Não contradiz `briefing.md`; em conflito com qualquer documento que
> não seja `docs/A-APLICACAO.md`, esta spec vence.

## problema

O DERVS mede o **entorno** do código e nunca o código. As 18 regras de
`regras.py` olham git (`regras.py:104`), containers (`regras.py:88`), CI e
alertas do GitHub (`regras.py:78` e `regras.py:95`), cota do Actions
(`regras.py:428`) e dependências (`regras.py:221`). Nenhuma delas abre um
arquivo `.py`, `.ts` ou `.cs`. Um projeto pode estar **saudável** pelos quatro
estados do selo (`regras.py:510`) com uma função de autenticação que falha
aberta, um `except` engolindo erro num caminho de pagamento e um teste que não
pode reprovar — porque nada disso produz commit sujo, CI vermelha ou alerta do
Dependabot.

A consequência prática é que o dono não consegue chegar a "meus projetos sempre
100%": ele só é avisado do que **já** quebrou por fora. E a fila que conserta
(`fila.py:26`) só sabe atacar três regras — `memoria_crlf`, `env_drift` e
`dependencia_insegura` —, porque só existem três pendências que alguém soube
descrever mecanicamente. Quem escreve a tarefa hoje é o dono; se ele não
escrever, a fila fica parada com o motor inteiro pronto e sem serviço.

Há uma segunda dor, menor e real: quando o dono **sabe** que algo está errado
num arquivo, não há nenhum lugar no DERVS onde registrar isso. Ele abre o VS
Code e conserta à mão — que é exatamente o trabalho que a Fatia 2 construiu o
braço para fazer.

## solucao

Um tipo novo de trabalho: **auditar um repositório por dentro**, disparando o
binário `claude` em modo só-leitura sobre uma cópia isolada, exigindo a resposta
por contrato (`--json-schema`), guardando os achados com carimbo, mostrando-os
numa tela nova, e transformando os graves em pendência que entra na fila já com
a cor do semáforo que existe.

Seis peças, e a fronteira de cada uma:

**1. `auditoria.py` — módulo NOVO, puro, sem estado.** Segue o molde de
`regras.py:16` ("entra dicionário, sai lista; não lê disco, não chama rede, não
roda comando"). Guarda: o esquema JSON dos achados, o gabarito fechado do prompt
de auditoria, a validação da saída do agente, o cálculo do id estável, a
higienização de cada campo, e as duas constantes de acoplamento
(`auditoria.REGRA_DE_VENCIMENTO`, `auditoria.EXECUTOR`).

*Por que módulo novo e não uma regra dentro de `regras.py`:* `regras.py` decide
"o que precisa de mim agora" a partir de um retrato já medido. A auditoria
**produz** medida. Pôr o gabarito do prompt e a validação do JSON dentro de
`regras.py` misturaria a apuração com a decisão, que é o que o §7 de
`docs/A-APLICACAO.md` proíbe ("nunca pôr um modelo de linguagem no caminho da
medição"). O achado só chega a `regras.py` depois de virar dado no banco — a IA
já trabalhou, a apresentação é conta nossa.

*Por que não dentro de `tarefas.py`:* `tarefas.py` responde uma pergunta só
(`tarefas.py:5`), é importado pelo servidor, e o cabeçalho dele proíbe importar
`execucao` e `fila` (`tarefas.py:15-24`). Encher esse arquivo de gabarito de
prompt destruiria a propriedade que faz `test_tarefas_nao_publicam.py` valer.

*Quem importa `auditoria.py`:* `servir.py` (para validar o que sobe e converter
achado em pendência), `regras.py` (só as constantes de nome de regra),
`execucao.py` (para o esquema e o gabarito) e `fila.py`. Como `servir.py` o
importa, ele **entra na imagem** — e como ele só usa biblioteca padrão, isso é
inofensivo. `auditoria.py` **não importa** `banco`, `execucao`, `fila` nem
`servir`.

**2. `execucao.auditar()` — função irmã de `iniciar()`, em `execucao.py`.**
Reusa `criar_copia` (`execucao.py:587`), `ambiente_da_filha`
(`execucao.py:565`), `settings_da_barreira` (`execucao.py:220`),
`interpretar_linha` (`execucao.py:281`), `custo_do_evento` (`execucao.py:386`) e
a trava global `_trava`/`_proc` (`execucao.py:800`). **Não** passa por
`_absorver` (`execucao.py:1014`) nem por `_fechar_com_pedido_de_alteracao`
(`execucao.py:1053`) — uma auditoria não abre PR, e reusar `iniciar()` faria
exatamente isso no fim.

*Por que uma função nova e não um parâmetro em `iniciar()`:* `iniciar()` tem 91
testes e a medição de campo colada no topo do arquivo. Um `if modo ==` dentro
dela põe todos esses testes em risco por uma funcionalidade que não compartilha
o desfecho. A trava global É compartilhada, e de propósito: auditoria e conserto
disputam o mesmo recurso, e "uma sessão por vez" tem de continuar valendo, senão
o teto de R$ 50 é conferido duas vezes contra o mesmo saldo.

**3. `ExecutorAuditor` — em `agente/executor.py`.** A tomada foi construída para
isto: *"a única coisa que este arquivo precisa garantir é que ligar o segundo
seja ACRESCENTAR uma implementação, não refazer nada"* (`agente/executor.py:5`).
Herda de `Executor` e portanto herda `_recusar_se_nao_pode`
(`agente/executor.py:55`), que chama `tarefas.pode_rodar` **antes** de montar
comando — a segunda camada do teto, que não depende do painel estar certo.

**4. Duas tabelas novas no banco:** `auditoria` (a corrida) e `achado` (o que
ela achou). Duas, e não uma, por causa da lei 2: sem a tabela da corrida, um
projeto com zero linhas em `achado` é indistinguível de um projeto nunca
auditado, e o painel diria "0 achados" para quem nunca foi medido. O DDL está
em `## o_que_ja_existe` → *o que muda*.

**5. Uma regra nova em `regras.py` e uma família de regras de achado.**
`auditoria_vencida` (baixa) diz "este projeto está marcado para auditar e a
última auditoria venceu, ou nunca houve". É ela que entra na fila e vira a
tarefa de auditar. E cada achado **de gravidade alta** vira uma pendência da
regra `auditoria_<categoria>` — cinco categorias fechadas: `auditoria_seguranca`,
`auditoria_bug`, `auditoria_teste`, `auditoria_doc`, `auditoria_estilo`.

*Por que a categoria entra no nome da regra:* porque a cor do semáforo é **por
regra** (`tarefas.cor_da_regra`, `tarefas.py:154`). Com uma regra só, o dono que
pintasse "achado de auditoria" de verde autorizaria a sessão a mexer sozinha
tanto num typo de documentação quanto num caminho de login. Com cinco, ele pinta
`auditoria_estilo` de verde e deixa `auditoria_seguranca` vermelha — e não há
mecanismo novo nenhum para isso: `cor_da_regra` já faz.

*Sem dois-pontos no nome da regra, de propósito:* `execucao.py:1058` faz
`_execucao["pendencia_id"].split(":")[0]` para recuperar a regra. `auditoria:seguranca`
quebraria isso em silêncio; `auditoria_seguranca` não.

**6. A tela `Auditoria`, a nona.** `#/auditoria` em `assets/painel.js`, seção
`#tela-auditoria` em `index.html`, link `data-tela="auditoria"` na navegação, e
estilo em `assets/painel.css`. **Nenhum arquivo novo em `assets/`** — ver
`## contradicoes_resolvidas`.

### O ciclo completo, ponta a ponta

1. O dono liga a auditoria de um projeto (interruptor na tela Projeto) **ou**
   clica em "Auditar agora" na tela Auditoria.
2. `regras._do_projeto` passa a emitir `auditoria_vencida` para projeto ligado
   cuja última corrida venceu. `fila.elegiveis` (`fila.py:61`) carimba trilho
   `claude` e executor `auditor`; `banco.enfileirar` (`banco.py:1368`) grava a
   linha, que **nasce vermelha** pelo `DEFAULT 'vermelho'` do esquema
   (`banco.py:184`).
3. O agente pergunta em `POST /agente/relatorio`; `_tarefa_pendente`
   (`servir.py:1890`) confere `tarefas.pode_rodar` e devolve a tarefa com
   `executor: "auditor"` e `teto_usd` já limitado ao que sobra do dia.
4. `agente/enviar.fazer_a_tarefa` (`agente/enviar.py:294`) escolhe o braço pelo
   campo `executor`; `ExecutorAuditor.rodar` confere de novo, clona a cópia
   isolada e roda `claude` só-leitura com `--json-schema`.
5. O desfecho sobe por `POST /agente/resultado` carregando `achados`.
   `servir._resultado` (`servir.py:1951`) chama `auditoria.validar`, e só então
   `banco.gravar_auditoria` grava a corrida e os achados numa transação.
6. `banco.montar_estado` (`banco.py:1267`) passa a devolver a camada
   `auditoria` de cada projeto; `regras._do_projeto` transforma cada achado alto
   em pendência; o resto aparece só na tela Auditoria.
7. O achado alto entra na fila como qualquer pendência. Verde anda sozinho,
   vermelho espera o clique. As travas de diff (`fila.reprovar`, `fila.py:245`)
   valem sem uma linha nova.

### As respostas diretas às nove perguntas

**1 — Onde a auditoria se encaixa.** Módulo novo `auditoria.py` (puro) + função
irmã `execucao.auditar()` + `ExecutorAuditor` em `agente/executor.py` + uma regra
em `regras.py`. **Nada** é acrescentado a `tarefas.py` além de dois números
(`TETO_AUDITORIA_USD`, `MAX_TURNOS_AUDITORIA`) e da mudança de casa de
`so_dado`/`FIM_DO_BLOCO` (justificada abaixo). `tarefas.py` continua sem importar
`execucao`, `fila` e `banco`; `servir.py` continua sem importar `execucao` e
`fila`; a lista de `test_imagem.PROIBIDOS` (`test_imagem.py:43`) continua com os
mesmos três módulos, e `auditoria.py` entra na lista de `COPY` do `Dockerfile`
porque `servir.py` o importa.

**2 — Como o achado vira pendência sem quebrar os três invariantes.**

- *Toda pendência tem ação* (`regras.py:12`): a ação de um achado é
  `{"tipo": "vscode", "rotulo": "Abrir o arquivo", "caminho": "<caminho do
  projeto>/<arquivo>"}` — tipo já existente em `regras.ACOES`
  (`regras.py:30`). Achado cujo `arquivo` não passa na peneira de caminho **não
  vira pendência nenhuma**: sem arquivo não há onde abrir, e pendência sem ação
  é proibida.
- *Ausência não é falha* (`regras.py:14`): `p.get("auditoria")` valendo `None`
  significa "camada não coletada", e o motor fica **calado** — exatamente como
  faz hoje com `gh = p.get("github")` (`regras.py:69`). Nunca "0 achados".
- *O id é estável* (`regras.py:17`): o formato exato é

  ```
  <regra>:<projeto>:<impressao>
  auditoria_seguranca:dervs:9f3c1a72b0d4
  ```

  onde `impressao` são os **12 primeiros hexadígitos** de
  `sha256(arquivo + "\n" + categoria + "\n" + normalizar(frase))`, com
  `normalizar` = minúsculas, espaços colapsados, pontuação de fim removida.
  **A linha NÃO entra no id, de propósito:** ela é o campo que muda quando
  alguém insere uma linha em cima, e um id que muda desfaz o silenciamento
  (`banco.silenciar`, `banco.py:1336`) e o arquivamento permanente. O critério 4
  do briefing — mesma auditoria duas vezes com a ordem embaralhada dá ids iguais
  — se prova sem rede, porque o id é função pura dos campos.

**3 — O esquema JSON exato**, passado a `--json-schema`:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["achados"],
  "properties": {
    "achados": {
      "type": "array",
      "maxItems": 60,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["arquivo", "linha", "categoria", "gravidade", "frase", "o_que_fazer"],
        "properties": {
          "arquivo":     {"type": "string", "minLength": 1, "maxLength": 400},
          "linha":       {"type": "integer", "minimum": 1, "maximum": 2000000},
          "categoria":   {"type": "string",
                          "enum": ["seguranca", "bug", "teste", "doc", "estilo"]},
          "gravidade":   {"type": "string", "enum": ["alta", "media", "baixa"]},
          "frase":       {"type": "string", "minLength": 10, "maxLength": 300},
          "o_que_fazer": {"type": "string", "minLength": 10, "maxLength": 500},
          "trecho":      {"type": "string", "maxLength": 400}
        }
      }
    }
  }
}
```

Ele mora em `auditoria.ESQUEMA` como **dicionário Python**, serializado com
`json.dumps(..., ensure_ascii=True)` na hora de virar argumento — pelo mesmo
motivo documentado em `execucao.py:203-212`: nesta máquina `claude` é um
`.CMD`, e todo argumento passa pelo interpretador do Windows, que rouba
`|`, `&`, `<`, `>`, `^` e `%` (`execucao.METACARACTERES_DO_CMD`,
`execucao.py:246`). Um teste-guarda confere que o JSON serializado do esquema
não contém nenhum desses seis caracteres.

**O esquema não é a validação.** `--json-schema` é promessa do fornecedor;
`auditoria.validar()` é a nossa, e ela refaz tudo em Python: tipo, faixa,
enumeração, tamanho e a peneira de caminho. O briefing exige que saída truncada,
vazia e JSON quebrado resultem em **sem dados** e nunca em zero — isso só é
verdade se quem decide for código nosso.

**4 — Como se prova o modo só-leitura.** `execucao.montar_comando_de_auditoria()`
devolve o argv com, nesta ordem:

```
--allowedTools     Read,Grep,Glob
--disallowedTools  Bash,Edit,Write,MultiEdit,NotebookEdit,Task,WebFetch,WebSearch
--json-schema      <o esquema acima>
--output-format    stream-json  --verbose
--strict-mcp-config  --mcp-config {"mcpServers":{}}
--setting-sources  ""           --settings <settings_da_barreira()>
--max-budget-usd   <teto da auditoria>
--max-turns        <MAX_TURNOS_AUDITORIA>
```

Nunca `--bare` (medido falhando com "Not logged in", `execucao.py:166`) e nunca
qualquer modo de permissão frouxo — a nota final de `pesquisa.md` registra que
esse nome aparece na documentação da Anthropic e **não** será usado.

`execucao.FERRAMENTAS_DE_LEITURA = ["Read", "Grep", "Glob"]` é constante própria,
e `FERRAMENTAS_OK` (`execucao.py:95`) fica intocada.

*Quem cobra:* `test_auditoria.OComandoEhSoLeitura` afirma quatro coisas, e cada
uma reprova sozinha — (a) `Bash`, `Edit` e `Write` **não** aparecem em
`--allowedTools`; (b) os oito nomes de escrita/rede aparecem em
`--disallowedTools`; (c) `--settings` continua trazendo o hook de `barreira.py`,
como cinto além do suspensório; (d) a interseção entre
`FERRAMENTAS_DE_LEITURA` e `execucao.VIGIADAS` (`execucao.py:203`) é vazia. A
sabotagem que o verificador da fase 6 tem de rodar: acrescentar `"Bash"` a
`FERRAMENTAS_DE_LEITURA` e exigir que o caso (a) fique vermelho.

**5 — As tabelas novas e como a migration é aplicada.** Ver
`## o_que_ja_existe` → *o que muda* para o DDL literal e para o mecanismo, que
segue à risca o molde de `_migrar_instalacao_github` (`banco.py:979`):
`con.execute` um comando por vez, **nunca `executescript`** — porque ele dá
COMMIT implícito e desmonta a transação (`banco.py:993`, e a lição está gravada
na memória desta máquina).

**6 — Como o custo é contado e travado.** Três camadas, e nenhuma delas é nova
de mecanismo:

- *o dia*: `tarefas.TETO_DIARIO_BRL = 50.00` (`tarefas.py:49`). `pode_rodar`
  recusa **antes de tudo** (`tarefas.py:257`), tanto no servidor
  (`servir.py:1901`) quanto no agente (`agente/executor.py:57`).
- *a sessão*: `tarefas.teto_da_sessao` (`tarefas.py:119`) já limita o teto da
  sessão ao que sobra do dia — foi achado de revisor em 25/08/2026 e resolve o
  caso "R$ 49 gastos e a sessão sai com o teto cheio".
- *a auditoria*: **novo**, `tarefas.TETO_AUDITORIA_USD` e
  `tarefas.teto_da_auditoria(gasto_usd) = max(0, min(TETO_AUDITORIA_USD,
  quanto_falta(gasto)/USD_BRL))`. Mora em `tarefas.py` pelo mesmo motivo que os
  outros tetos moram lá: **o servidor precisa dele** para calcular o `teto_usd`
  que desce na tarefa (`servir.py:1918`), e o servidor não pode importar
  `execucao` nem `fila`. `execucao.py` e `fila.py` **reexportam o mesmo objeto**,
  como já fazem com `TETO_USD` (`execucao.py:78`, `fila.py:42`), e um teste
  cobra a identidade (`is`), não a igualdade.

O custo real vem de `custo_do_evento` (`execucao.py:386`), que lê
`total_cost_usd` do evento `result` e **não** converte token em dólar por conta
própria. Ele é anotado em `fila.custo_usd` pelo desfecho, e portanto entra no
`banco.gasto_entre` (`banco.py:1872`) que alimenta o teto do dia — sem dupla
contagem, porque a auditoria vem pela fila e `contabilizar=False` vale para ela
como vale para o conserto (`execucao.py:996`).

O teto duro de verdade continua sendo o relógio: `--max-budget-usd` foi medido
estourando 4,5× (`execucao.py:34`), e o `SEGUNDOS_DE_SESSAO = 1800`
(`agente/executor.py:87`) é o que não estoura.

**7 — Como o texto do repositório auditado é impedido de virar instrução.**
Quatro barreiras, em quatro lugares diferentes:

- *Na entrada:* o gabarito de auditoria é **fechado**, no molde de
  `execucao.GABARITO` (`execucao.py:129`), e o único campo interpolado é o nome
  do projeto. O conteúdo dos arquivos **não passa pelo prompt** — o agente os lê
  com `Read`/`Grep`. O texto do gabarito diz, com todas as letras, que tudo que
  ele ler dos arquivos é objeto de análise e nunca ordem.
- *Na saída:* `auditoria.limpar()` aplica `so_dado` (hoje `execucao.py:255`) a
  `frase`, `o_que_fazer` e `trecho`, remove caracteres de controle, corta nos
  tamanhos do esquema, e **recusa** achado cujo `arquivo` seja absoluto, tenha
  `..`, comece com `/` ou `\`, ou tenha letra de unidade (`C:`).
- *No reuso:* quando um achado vira o `detalhe` de uma tarefa de conserto, ele
  entra no `<dados-coletados-nao-confiaveis>` de `execucao.montar_prompt`
  (`execucao.py:263`) — a barreira que já existe, e que `so_dado` protege contra
  o dado que traz a própria etiqueta de fechamento escrita dentro.
- *Na tela:* achado é escrito com `textContent`, nunca `innerHTML` — o padrão já
  usado em `assets/painel.js:73` e `:214`.

*A mudança de casa que isto exige:* `so_dado` e `FIM_DO_BLOCO` moram hoje em
`execucao.py`, que **não entra na imagem** (`test_imagem.PROIBIDOS`). `auditoria.py`
entra. Uma segunda cópia do sanitizador é exatamente o defeito que o §"As três
portas" do `CLAUDE.md` registra ("uma segunda cópia dessa peneira já matou o
*drift* em silêncio com 926 testes verdes"). Então os dois **mudam de casa para
`tarefas.py`** e `execucao.so_dado = tarefas.so_dado` vira reexportação — o mesmo
padrão de `execucao.em_reais` (`execucao.py:401`), com teste de identidade.

*Como se testa:* `test_auditoria.OTextoDoRepoNaoViraOrdem` monta um repositório
de mentira com um `README.md` contendo uma ordem explícita a um modelo e um
`</dados-coletados-nao-confiaveis>` literal, e afirma (a) que a ordem não aparece
em lugar nenhum do prompt montado, (b) que `so_dado` neutraliza a etiqueta, e (c)
que um achado cujo `arquivo` é `../../.ssh/config` é recusado por `validar`. O
teste é determinístico e não chama modelo nenhum — ele testa o **mecanismo**, no
molde de `OCorpoDoPedidoEDrenado` (a lição de 02/09 sobre falha probabilística).

**8 — A tela nova.** Duas rotas, ambas de acesso **`dado`**:

| caminho | método | função | acesso |
|---|---|---|---|
| `/api/auditoria` | `GET` | `Hub._auditoria` | `dado` |
| `/api/auditoria/pedir` | `POST` | `Hub._auditoria_pedir` | `dado` |

*Por que `dado` e não `cortina`:* um achado carrega caminho de arquivo, número de
linha e um trecho do código-fonte privado do dono. É o dado mais sensível que
este painel já guardou — mais que o nome de um projeto. `cortina` são seis
dígitos, um milhão de combinações, e o próprio `servir.py:47` diz que ela não é a
fechadura. E a tela é desenhada dentro de `assets/painel.js`, que já **exige
sessão por caminho exato** (`servir.ESTATICOS_COM_SESSAO`, `servir.py:2572`):
servir os achados com acesso menor que o do arquivo que os desenha seria
incoerente.

*Nenhum arquivo novo em `assets/`.* A lista de estáticos nasce de uma leitura da
pasta **na subida** (`servir.py:150`) e a proteção casa por caminho exato — um
`assets/auditoria.js` novo nasceria **aberto**, porque só `painel.js` e
`painel.css` estão em `ESTATICOS_COM_SESSAO`, e além disso só passaria a ser
servido depois de reiniciar `servir.py`. A tela mora em `painel.js`/`painel.css`.

*Nomes contra `test_rotas.PROIBIDO`* (`test_rotas.py:42`, casa
`acao|execucao|exec|terminal|pty|shell|comando|grafo` contra o caminho **e** o
nome da função): `auditoria` e `_auditoria_pedir` passam. `_executar_auditoria`
não passaria — e é bom que não passe.

*E `test_rotas.EXECUTA`* (`test_rotas.py:111`): `_auditoria_pedir` escreve no
banco com `banco.enfileirar` e não alcança `subprocess` nem `coletar`. O
andarilho `_alcancaveis` (`test_rotas.py:124`) segue o grafo de chamadas dentro
de `servir`, então isso é verificado, não prometido.

**9 — O que quebra se alguém renomear alguma coisa.** Está listado inteiro no
fim de `## o_que_ja_existe`.

## o_que_ja_existe

### O que NÃO precisa ser construído (com caminho e linha)

**A tomada do segundo braço.** `agente/executor.py:36` define `Executor` com
três métodos, e `agente/executor.py:5-10` diz literalmente que a segunda
implementação é para ser **acrescentada**. `ExecutorCodex` já está lá com
`disponivel()` devolvendo `False`. `agente/enviar.py:309` escolhe o braço pelo
campo `executor` da tarefa. **Ligar o auditor é escrever uma classe, não mexer
no despacho.**

**A coluna `executor` na tabela `fila`** já existe, com
`executor TEXT NOT NULL DEFAULT 'claude'` (`banco.py:189`), já está em
`COLUNAS_FILA` (`banco.py:1355`), já é migrada por `ALTER TABLE`
(`banco.py:560`, entrada `("executor", "TEXT NOT NULL DEFAULT 'claude'")`) e já
desce na tarefa (`servir.py:1917`). **Não é preciso inventar nada para
distinguir uma tarefa de auditoria de uma tarefa de conserto.**

**A guarda dupla do teto.** `tarefas.pode_rodar` (`tarefas.py:234`) é a pergunta
única, feita pelo servidor em `servir.py:1901` e de novo pelo agente em
`agente/executor.py:57`. A ordem das recusas já é a certa: teto do dia primeiro
(`tarefas.py:257`), depois máquina autorizada, depois cor, depois tentativas.
`teto_da_sessao` (`tarefas.py:119`) já limita a sessão ao que sobra do dia.

**O semáforo inteiro.** `cor_da_regra` (`tarefas.py:154`) devolve vermelho em
qualquer dúvida; `pode_repintar` (`tarefas.py:167`) deixa fechar sempre e abrir
só fora de `NUNCA_VERDE` (`tarefas.py:147`); a coluna `cor` nasce `'vermelho'`
no próprio esquema (`banco.py:184`), e o comentário ali diz por quê. **A regra
nova de auditoria nasce vermelha sem uma linha de código.**

**As travas de diff.** `fila.diff_toca_publicacao` (`fila.py:215`) barra
`.github/workflows/`, `Dockerfile`, `docker-compose.yml`, `docker-compose.yaml`,
`infra/` (`fila.py:175`) e qualquer linha nova com `gh workflow`,
`workflow_dispatch`, `/dispatches` (`fila.py:185`).
`fila.diff_mexeu_em_teste` (`fila.py:118`) barra teste apagado, teste renomeado
e teste desligado por marcador. `fila.reprovar` (`fila.py:245`) aplica as duas
para **toda** regra, antes de qualquer parte específica. **Risco 1 do briefing
não precisa de código novo — precisa de um teste que plante um achado apontando
para `.github/workflows/ci.yml` e exija a reprovação.**

**O isolamento da cópia.** `execucao.criar_copia` (`execucao.py:587`) faz clone
local com `--no-hardlinks`, `remote remove origin` e `core.hooksPath` numa pasta
vazia. `ambiente_da_filha` (`execucao.py:565`) peneira segredo do ambiente.
`settings_da_barreira` (`execucao.py:220`) combina `--setting-sources ""` com um
hook `PreToolUse` — e o comentário em `execucao.py:229` registra o furo grande
que isso tapou: o `.claude/settings.json` **do repositório sendo consertado**,
que é conteúdo de estranho.

**A barreira do Bash.** `barreira.py:41` é lista branca de programas;
`barreira.py:58` nomeia os que saem da máquina; `barreira.py:70` explica por que
`git` tem lista branca de subcomando e não lista negra (`git -c alias` anulava
tudo). Na auditoria o `Bash` nem é permitido — a barreira fica como terceira
camada redundante, e redundância aqui é barata.

**O contrato do fio de volta**, escrito em `tarefas.py:186-216`: o que desce em
`/agente/relatorio` (`CAMPOS_DA_TAREFA`, `tarefas.py:218`) e o que sobe em
`/agente/resultado` (`CAMPOS_DO_PROGRESSO` e `CAMPOS_DO_DESFECHO`,
`tarefas.py:220`). **Um balcão só**, e o motivo está escrito ali. A auditoria
usa o mesmo balcão.

**A leitura do stream e o custo.** `interpretar_linha` (`execucao.py:281`) nunca
levanta exceção — o comentário explica que uma exceção ali mata a thread e a
tela congela. `custo_do_evento` (`execucao.py:386`) lê `total_cost_usd` e
recusa-se a converter token em dólar por conta própria.

**A entrega da tarefa e a reserva.** `banco.tarefa_para_maquina`
(`banco.py:1435`) só lê e falha fechada; `banco.entregar_tarefa`
(`banco.py:1469`) reserva; `servir._tarefa_pendente` (`servir.py:1890`) encadeia
as três recusas. `banco.registrar_desfecho` (`banco.py:1549`) grava o fim.
`servir._varrer_mudas` (`servir.py:1875`) mata tarefa muda em 15 minutos —
`tarefas.MINUTOS_SEM_NOTICIA` (`tarefas.py:231`).

**O motor do selo e o quarto estado.** `regras.selo_do_projeto`
(`regras.py:510`), `regras.camadas_do_selo` (`regras.py:499`), `regras.VALIDADE`
(`regras.py:458`) e `regras.CAMADA_DA_REGRA` (`regras.py:466`). O comentário de
`regras.py:461` já explica por que regra fora do mapa **não pinta o selo** — e é
onde `auditoria_vencida` vai ficar.

**O agrupamento e o silenciar/arquivar.** `regras.agrupar` (`regras.py:592`),
`regras.NAO_AGRUPAR` (`regras.py:566`), `regras.ROTULO_REGRA` (`regras.py:570`),
`banco.silenciar` (`banco.py:1336`), as rotas `/api/arquivar` e
`/api/desarquivar` (`servir.py:2498`). **Achado silenciado e achado arquivado
não custam mecanismo novo — custam um id estável, e é por isso que o id é a
decisão mais importante desta spec.**

**O padrão de tela.** `assets/painel.js:111` (`rota()`), `:116` (`mostrar()`),
`:126` (`navegar()`), `:334` (`vazio()`), `:360` (`criterio()`), `:52`
(`haQuanto()` — o carimbo em português). `index.html:64-69` é a navegação;
`index.html:139` é o `<main>` e cada tela é uma `<section id="tela-…">`.

### O que muda (o inventário completo da entrega)

**Arquivos novos: dois.** `auditoria.py` e `test_auditoria.py`.

**`banco.py` — as duas tabelas.** DDL literal, repetido em `ESQUEMA`
(`banco.py:92`) e nas constantes `_CREATE_AUDITORIA` / `_CREATE_ACHADO`, no molde
declarado em `banco.py:785-789` (duas cópias do mesmo `CREATE`, de propósito: a
do `ESQUEMA` é a documentação do banco de hoje, a da constante é a que a
migração roda):

```sql
CREATE TABLE IF NOT EXISTS auditoria (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id   INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    projeto      TEXT    NOT NULL CHECK (length(trim(projeto)) > 0),
    tarefa_id    TEXT,
    estado       TEXT    NOT NULL CHECK (estado IN ('ok','falha','recusada')),
    motivo       TEXT    NOT NULL DEFAULT '',
    achados_n    INTEGER NOT NULL DEFAULT 0,
    arquivos_n   INTEGER NOT NULL DEFAULT 0,
    custo_usd    REAL    NOT NULL DEFAULT 0.0,
    rodadas      INTEGER NOT NULL DEFAULT 0,
    medido_em    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_auditoria_projeto
    ON auditoria (usuario_id, projeto, medido_em);

CREATE TABLE IF NOT EXISTS achado (
    id           TEXT    PRIMARY KEY,
    auditoria_id INTEGER NOT NULL REFERENCES auditoria(id) ON DELETE CASCADE,
    usuario_id   INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    projeto      TEXT    NOT NULL DEFAULT '',
    regra        TEXT    NOT NULL DEFAULT '',
    categoria    TEXT    NOT NULL DEFAULT '',
    arquivo      TEXT    NOT NULL DEFAULT '',
    linha        INTEGER,
    gravidade    TEXT    NOT NULL DEFAULT 'media',
    frase        TEXT    NOT NULL DEFAULT '',
    o_que_fazer  TEXT    NOT NULL DEFAULT '',
    trecho       TEXT    NOT NULL DEFAULT '',
    visto_em     TEXT    NOT NULL,
    fechado_em   TEXT
);
CREATE INDEX IF NOT EXISTS ix_achado_aberto
    ON achado (usuario_id, projeto, fechado_em);
```

*Por que `achado.id` é `TEXT PRIMARY KEY` e não autoincremento:* é o id estável
da pendência, e ele **é** a chave. Um achado que reaparece na auditoria seguinte
faz `INSERT OR REPLACE` na mesma linha e mantém o `visto_em` mais antigo — quem
some é quem não voltou, e some marcando `fechado_em`, nunca com `DELETE`, para o
histórico não mentir.

*A migração:* `_migrar_auditoria(con)`, acrescentada à lista de `migrar()`
(`banco.py:525`), no molde exato de `_migrar_instalacao_github`
(`banco.py:979`) — uma função por migração, condição própria de "já rodou"
(`PRAGMA table_info`), e **`con.execute` um comando por vez, jamais
`executescript`**, porque ele dá COMMIT implícito e desmontaria a transação
(`banco.py:993`). As duas tabelas apontam para `usuario`, e o `ESQUEMA` roda
**depois** da migração (`banco.py:515-516`), então elas nascem na migração e o
`ESQUEMA` só as reafirma. `FILHAS_DE_USUARIO` (`banco.py:546`) ganha
`"auditoria"` e `"achado"`.

*Funções novas em `banco.py`:* `gravar_auditoria(...)` (uma transação só, no
molde de `banco.py:664`), `auditoria_do_projeto(...)`, `achados_do_projeto(...)`,
`fechar_achados_ausentes(...)`.

*Uma mudança cirúrgica em `banco.enfileirar` (`banco.py:1368`):* o `INSERT` passa
a levar a coluna `executor`, lendo `p.get("executor")` com padrão `'claude'` —
sem isso a tarefa de auditoria chegaria ao agente pedindo o braço errado.

*Uma mudança cirúrgica em `banco.montar_estado` (`banco.py:1267`):* a camada
`auditoria` é anexada a cada projeto, com o carimbo em
`p["medido_em"]["auditoria"]`, no mesmo formato das camadas `github` e `pesado`
(`banco.py:1288`). Projeto sem corrida recebe `p["auditoria"] = None`.

*Uma mudança cirúrgica em `banco.tarefa_para_maquina` (`banco.py:1435`):*
`LEFT JOIN achado ON achado.id = fila.id`, para o `detalhe` que desce na tarefa
sair do achado. Hoje `servir.py:1918` manda `candidata.get("erro")` como
`detalhe`, o que para uma tarefa nova sempre é vazio.

**`tarefas.py` —** `TETO_AUDITORIA_USD`, `MAX_TURNOS_AUDITORIA`,
`teto_da_auditoria()`, e a mudança de casa de `FIM_DO_BLOCO` (`execucao.py:252`)
e `so_dado` (`execucao.py:255`), com reexportação em `execucao.py`.

**`regras.py` —** `_p` (`regras.py:42`) ganha um parâmetro opcional `sufixo=""`
que, quando presente, faz o id virar `regra:projeto:sufixo`; `_do_projeto`
(`regras.py:61`) ganha o bloco que lê `p.get("auditoria")`; `VALIDADE`
(`regras.py:458`) ganha `"auditoria": 7 * 24 * 3600`; `CAMADA_DA_REGRA`
(`regras.py:466`) ganha as cinco regras `auditoria_*` (mas **não**
`auditoria_vencida`); `ROTULO_REGRA` (`regras.py:570`) ganha as seis;
`NAO_AGRUPAR` (`regras.py:566`) ganha as cinco `auditoria_*`.

*Por que `NAO_AGRUPAR`:* `agrupar` escreve `"%d projetos %s."` (`regras.py:628`).
Doze achados no **mesmo** projeto virariam a frase "12 projetos com achados de
segurança" — um número errado com cara de certo, que é o pecado capital da lei
2. `vulnerabilidade` já está lá pelo mesmo tipo de motivo (`regras.py:566`).

**`fila.py` —** `REGRAS_MECANICAS` (`fila.py:26`) ganha
`"auditoria_vencida": "claude"` e as cinco `auditoria_*` que o dono autorizar;
`elegiveis` (`fila.py:61`) passa a carimbar `executor` além de `trilho`, lendo
`auditoria.EXECUTOR_DA_REGRA`.

**`execucao.py` —** `FERRAMENTAS_DE_LEITURA`, `montar_comando_de_auditoria()`,
`auditar()`, e a reexportação de `so_dado`. Nada é removido.

**`servir.py` —** duas rotas, duas funções, e a validação dentro de `_resultado`
(`servir.py:1951`) quando o desfecho traz `achados`. `import auditoria` no topo.

**`agente/executor.py` —** `ExecutorAuditor`, e a entrada dele em
`executor_de()`.

**`Dockerfile` —** `COPY auditoria.py /app/` junto dos outros módulos de runtime
(`Dockerfile:63-74`).

**`.github/workflows/ci.yml` —** o passo de `test_auditoria.py`, à mão, porque há
um passo que cobra a lista.

**`docker-compose.yml` — nada.** Não há variável de ambiente nova nesta entrega:
os tetos são constantes em `tarefas.py`, como `TETO_USD` e `TETO_DIARIO_BRL` já
são. `test_publicar.OContainerRecebeOQueOCodigoLe` continua verde sem edição, e
isso é decisão consciente, não esquecimento.

**`index.html`, `assets/painel.js`, `assets/painel.css` —** a nona tela.

### Os acoplamentos por nome que esta entrega cria (cada um vira um teste-guarda)

Cada linha abaixo é uma coisa que **quebra em silêncio** se renomeada, e para
cada uma há um caso em `test_auditoria.py` — mais a sabotagem obrigatória que
prova que o caso consegue reprovar.

1. **`achado.id` = `<regra>:<projeto>:<impressao>`, sem dois-pontos dentro da
   regra.** Quem lê: `execucao.py:1058` (`pendencia_id.split(":")[0]`) e
   `regras._p` (`regras.py:50`). *Sabotagem:* renomear uma regra para
   `auditoria:seguranca` e exigir que o guarda acuse.
2. **`executor = "auditor"`** aparece em quatro lugares: `auditoria.EXECUTOR`,
   `banco.enfileirar`, `servir._tarefa_pendente` (`servir.py:1917`) e
   `agente/executor.executor_de`. O guarda lê a constante e afirma que as
   quatro pontas usam **o mesmo objeto**, no molde do teste de identidade dos
   tetos.
3. **As cinco categorias** do enum do esquema JSON, o sufixo das cinco regras
   `auditoria_*` e as chaves de `ROTULO_REGRA`/`CAMADA_DA_REGRA` são a **mesma
   lista**, derivada de `auditoria.CATEGORIAS`. Três cópias divergem; uma
   constante, não.
4. **`assets/painel.js` e `assets/painel.css`** continuam sendo os dois nomes de
   `servir.ESTATICOS_COM_SESSAO` (`servir.py:2572`) — o guarda que já existe em
   `test_rotas.py` cobra isso, e a tela nova **não** acrescenta um terceiro nome.
5. **`auditoria.py` na lista de `COPY` do `Dockerfile`.** `test_imagem.py:43`
   segue os imports de `servir.py`; um `import auditoria` sem a linha de `COPY`
   deixa a suíte vermelha — e é exatamente o que se quer.
6. **`--allowedTools` sem `Bash`/`Edit`/`Write`** e `--disallowedTools` com os
   oito. O guarda lê o argv montado, não o código-fonte.
7. **O JSON do esquema serializado não contém `|`, `&`, `<`, `>`, `^` nem `%`**
   (`execucao.METACARACTERES_DO_CMD`, `execucao.py:246`).
8. **`tarefas.so_dado` é o mesmo objeto que `execucao.so_dado`**, e
   `FIM_DO_BLOCO` idem — teste de identidade, no molde de `execucao.em_reais`
   (`execucao.py:401`).
9. **`test_auditoria.py` na lista à mão de `.github/workflows/ci.yml`** — já há
   um passo que cobra a lista.
10. **`auditoria_vencida` fora de `CAMADA_DA_REGRA`.** Um guarda afirma que ela
    **não** pinta o selo: "não medi" é `sem_dados`, nunca `quebrado`. É a lei 2
    escrita como teste.

## fontes_externas

Todas consultadas em **02/09/2026** e registradas em
`docs/esteira/auditoria-profunda/pesquisa.md`. Nenhuma pesquisa nova foi feita
nesta fase.

**Claude Code sem interação — as flags que esta entrega usa:**
- https://code.claude.com/docs/en/headless (02/09/2026) — `-p`,
  `--output-format json|stream-json` com `total_cost_usd` dentro.
- https://code.claude.com/docs/en/cli-reference (02/09/2026) — **`--json-schema`**,
  que devolve a saída validada em `structured_output`; `--allowedTools`;
  `--max-turns`. Armadilha confirmada: `--bare` exige chave de API e não lê o
  login por assinatura. Trava numérica achada: **10 MB no stdin** — logo,
  referenciar arquivos por caminho, nunca despejar conteúdo por cano.

**Bolt.diy — descartado, com dois motivos independentes:**
- https://github.com/stackblitz-labs/bolt.diy (02/09/2026) — TypeScript/React +
  Vite + UnoCSS. Não é Python.
- https://github.com/stackblitz-labs/bolt.diy/blob/main/LICENSE (02/09/2026) —
  MIT, o código é livre.
- https://webcontainers.io/enterprise e https://stackblitz.com/pricing
  (02/09/2026) — o WebContainer, que é quem de fato roda o código, **exige
  licença comercial de US$ 25 a US$ 60 por usuário/mês**, com teto de 500
  sessões. Quebra a lei 1 do repositório e cobra mensalidade por um motor mais
  fraco que o que o DERVS já tem.

**Referências de desenho (não instaladas — todas trazem dependência externa):**
- https://github.com/All-Hands-AI/OpenHands (MIT) · 
  https://github.com/swe-agent/swe-agent (MIT) · 
  https://github.com/qodo-ai/pr-agent (Apache-2.0), consultadas em 02/09/2026.
- https://github.com/sweepai/sweep (02/09/2026) — o concorrente mais direto
  **fechou o código** e virou plugin comercial da JetBrains.

**Assinatura Max num servidor — a pergunta que continua sem resposta:**
- https://code.claude.com/docs/en/legal-and-compliance (02/09/2026). O texto
  proíbe rotear pedidos por credencial de plano Free/Pro/Max **em nome de
  terceiros** e no Agent SDK; e permite o próprio usuário logar no **binário sem
  modificação** com a própria assinatura, **inclusive hospedado**. A zona
  cinzenta (painel próprio, na VPS do dono, para os projetos do dono) não é
  resolvida pelo texto. **Não fabricar um "sim".** Esta entrega não muda nada
  desse quadro: ela roda o binário sem modificação, com a conta do dono, sem
  servir terceiros.

## fora_de_escopo

**Do briefing, sem alteração:**

- **O construtor de aplicações do zero** (o "algo parecido com o Bolt.diy").
  → fatia seguinte, pela esteira, começando por briefing próprio.
- **Terminal no navegador, a lousa e o editor de código.**
  → Fatias 3 e 4, como já está em `docs/A-APLICACAO.md` §11. Nada aqui os
  antecipa.
- **Qualquer dependência externa em Python.** → lei 1, para sempre.
- **Auditoria automática e recorrente sem o dono ligar.** → depois de a primeira
  auditoria ter rodado de verdade em pelo menos um projeto.
- **Consertar sozinho o que a auditoria achar de vermelho.** → o semáforo que já
  existe decide, sem exceção nova.

**Cortado nesta fase, com destino nomeado:**

- **Auditar todos os projetos por padrão.** A auditoria é **opt-in por projeto**:
  nasce desligada, e ligar é um segundo sim explícito, no molde travado do §12 da
  fonte única (*"parear um computador não dá a ele o direito de rodar código"*).
  → A conta que obriga: 17 projetos × o teto por auditoria estoura os R$ 50 do
  dia antes do primeiro conserto. → fica para depois da medição real.
- **Achado de gravidade `media` e `baixa` virando pendência no Painel.** Eles
  aparecem **só** na tela Auditoria. → o Painel responde "o que eu faço agora?"
  (§5.4 da fonte única), e 60 achados médios ali dentro é o retorno dos 203
  alertas. → revisar depois da primeira auditoria real.
- **Auditar `vivo/`, `docs/` e qualquer projeto de `execucao.PROJETOS_BLOQUEADOS`**
  (`execucao.py:104`, hoje `ajudei-saude`). → o bloqueio existente vale igual
  para auditar; prontuário sob LGPD continua fora.
- **Editar o achado na tela** (mudar gravidade, reescrever a frase). O dono
  silencia, arquiva ou manda consertar — não edita. → se aparecer necessidade,
  vira pedido próprio.
- **Auditoria incremental (só o que mudou desde o último commit auditado).**
  Seria a economia mais óbvia de custo. → depende de ter a medição real do custo
  de uma auditoria cheia; entra na fatia seguinte com o número na mão.
- **Segundo braço (Codex) auditando.** A tomada fica pronta;
  `ExecutorCodex.disponivel()` continua `False`. → Fatia 3, como já decidido.
- **Arquivo novo em `assets/`.** → a tela mora em `painel.js`/`painel.css`,
  pelo motivo escrito na pergunta 8.
- **Variável de ambiente nova.** → os tetos são constantes em `tarefas.py`.

## contradicoes_resolvidas

**1. "Auditar profundo" × o teto de R$ 50/dia — a tensão principal.**
*Analista:* o valor do produto está em ler o repositório inteiro, arquivo por
arquivo, como o dono pediu ("analise tudo debug linha a linha profundamente").
*Diretor de escopo:* uma leitura assim é a operação mais cara que o DERVS já
fez, e o teto de R$ 50 foi dimensionado para correções de dois minutos
(`tarefas.py:49`). Auditar 17 projetos gastaria o dia inteiro e a fila de
conserto não rodaria nenhuma vez.
**Venceu o Diretor, com três limites e um motivo:** (a) teto próprio por
auditoria (`TETO_AUDITORIA_USD`) além do teto do dia; (b) opt-in por projeto;
(c) `maxItems: 60` no esquema, que é também um freio de custo, porque o modelo
para de escrever. *O motivo:* um recurso que estoura o orçamento no primeiro dia
é desligado na primeira semana, e aí a profundidade vale zero. A profundidade
volta pela auditoria incremental, com número medido — está em `fora_de_escopo`
com destino.

**2. Onde mora a lógica da auditoria.**
*Arquiteto (primeira leitura):* uma regra a mais em `regras.py`, que é onde as
18 já moram. *Arquiteto (segunda leitura, depois de abrir o arquivo):*
`regras.py:16` promete que o módulo é **puro** e que **não roda comando** — e o
§7 da fonte única proíbe pôr um modelo de linguagem no caminho da medição.
**Venceu a segunda leitura:** `auditoria.py` produz a medida, `regras.py` decide
o que fazer com ela depois de gravada. A regra em `regras.py` existe, mas ela lê
uma camada já medida, como `github` e `pesado`.

**3. Uma regra de achado ou cinco?**
*Analista:* uma só (`auditoria_achado`) é mais simples de escrever e de explicar.
*Arquiteto:* a cor do semáforo é por regra (`tarefas.py:154`); com uma só, pintar
de verde autoriza a sessão a mexer sozinha num caminho de login e num typo de
documentação com o mesmo clique.
**Venceu o Arquiteto.** Cinco categorias fechadas, e o dono ganha um controle
real sem mecanismo novo. O custo é uma lista a manter em um lugar
(`auditoria.CATEGORIAS`), e ela vira teste-guarda nº 3.

**4. A linha do arquivo entra no id?**
*Analista:* sim — é a informação mais útil para o André conferir o diagnóstico.
*Arquiteto:* então o id muda quando alguém insere uma linha acima, e o
silenciamento e o arquivamento permanente se desfazem sozinhos — que é o
invariante 3 de `regras.py:17` quebrado.
**Venceu o Arquiteto:** a linha aparece na tela e no `achado.linha`, mas **fora**
do id. O id usa arquivo + categoria + frase normalizada.

**5. Reusar `execucao.iniciar()` ou escrever `auditar()`?**
*Analista:* reusar, porque `iniciar` já sabe clonar, ler o stream e contar
custo. *Arquiteto:* `iniciar` termina em `_fechar_com_pedido_de_alteracao`
(`execucao.py:1053`), que abre PR — uma auditoria que abre PR é um defeito, e um
`if modo ==` dentro de uma função com 91 testes é como se quebram os 91.
**Venceu o Arquiteto**, com a ressalva do Analista aceita: `auditar()` reusa as
peças (`criar_copia`, `ambiente_da_filha`, `interpretar_linha`,
`custo_do_evento`) e **a mesma trava global**, para "uma sessão por vez"
continuar valendo entre auditoria e conserto.

**6. Cópia isolada ou ler o projeto de verdade, já que é só leitura?**
*Diretor:* o clone custa disco e segundos — o maior projeto tem 342 MB de `.git`
(`execucao.py:596`) — e em modo só-leitura seria desperdício.
*Arquiteto:* "só leitura" é uma lista de ferramentas, e lista de ferramentas é
promessa do fornecedor. As duas barreiras que de fato seguram são a cópia sem
`origin` e o corte de `--setting-sources` (`barreira.py:14-22`); ler o projeto
de verdade descarta a primeira.
**Venceu o Arquiteto.** O desperdício é aceito e nomeado; a economia volta como
auditoria incremental, com número medido.

**7. A tela é `dado` ou `cortina`?**
*Não houve discordância real, e fica registrado por quê:* achado carrega trecho
de código-fonte privado. `servir.py:47` diz que a cortina não é a fechadura. E
`painel.js`, que desenha a tela, já exige sessão (`servir.py:2572`) — servir o
conteúdo com acesso menor que o do arquivo que o desenha seria incoerente.

**8. O que fazer quando a saída do agente vem quebrada.**
*Analista:* aproveitar os achados que deram para ler, para não perder a corrida
inteira. *Arquiteto:* aproveitar parte é gravar uma lista incompleta com cara de
completa — o critério 2 do briefing manda os três casos (truncada, vazia, JSON
quebrado) resultarem em **sem dados**.
**Venceu o Arquiteto, sem meio-termo:** validação é tudo-ou-nada. A corrida é
gravada com `estado='falha'` e o `motivo` em português, os achados anteriores
**não** são fechados, e o projeto continua com o carimbo da última auditoria
boa. Zero achados só existe quando a corrida terminou `ok` com lista vazia — e a
tela escreve as duas coisas com palavras diferentes.

## duvidas_para_o_dono

**Uma, e é de dinheiro.**

**Quanto uma auditoria pode custar, no máximo?** Hoje o único teto é o do dia
(R$ 50) e o da sessão (US$ 3 ≈ R$ 15,42). Ler um repositório inteiro é mais caro
que corrigir uma CI vermelha, e não há medição nossa disso ainda — a
documentação da Anthropic não publica número para varredura de repositório
(`pesquisa.md`, §3).

**Minha recomendação: US$ 1,50 por auditoria (≈ R$ 7,71), com três a quatro
auditorias cabendo no dia sem impedir a fila de consertar.** O número é
deliberadamente apertado: começar apertado e afrouxar depois é mais fácil que o
contrário, que foi a decisão dele mesmo em 25/08/2026 ao fixar o teto do dia
(`tarefas.py:47-49`). A primeira auditoria real vira medição, e o número volta
para ele com dado em vez de palpite.

*As alternativas, para ele não decidir no escuro:* US$ 3,00 (o mesmo teto de uma
sessão de conserto, ≈ R$ 15,42) permite auditoria mais profunda e deixa só três
por dia; US$ 0,75 (≈ R$ 3,86) provavelmente não termina a leitura de um
repositório grande e devolveria uma lista rasa com cara de completa — que é o
risco que a lei 2 mais odeia.

*Onde isto é decidido:* esta é a pergunta do **portão 4**, que o briefing já
previu ("risco: a migration da tabela nova e o teto de custo"). Não trava a fase
3 nem a 4; trava a fase 5.

**Nenhuma outra.** As duas decisões que pareciam pedir o dono foram resolvidas
por precedente escrito e estão em `## fora_de_escopo` e `## contradicoes_resolvidas`:
o opt-in por projeto segue o §12 da fonte única (*"parear um computador não dá a
ele o direito de rodar código"*), e a cor de cada categoria de achado já é
respondida pelo semáforo — toda regra nasce vermelha e ele repinta quando
quiser, sem que ninguém precise decidir nada agora.
