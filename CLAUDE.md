# CLAUDE.md — o DERVS

Convenções deste repositório. Combina com o `CLAUDE.md` global; **em conflito,
este vence**. Curto de propósito: só o que faria a próxima sessão errar se não
soubesse.

## As três leis deste código

1. **Biblioteca padrão pura. Nenhuma dependência externa.** Decisão antiga,
   registrada em `banco.py`, e a CI cobra: um `requirements.txt` ou um
   `pyproject.toml` no repositório deixa a verificação vermelha. Quando o Python
   não traz a peça (ECDSA em `p256.py`, RSA em `github_app.py`), ela é escrita à
   mão — nunca instalada.
2. **O painel não pode mentir.** Um número errado com cara de certo é pior que
   número nenhum. "Não sei" é um estado de primeira classe: por isso o selo tem
   **quatro** estados, e o quarto é *sem dados*. Zerar um alerta que não deu para
   reler apaga um problema real.
3. **Falha fechada em caminho de autenticação.** Devolve `None` ou `False`,
   nunca levanta para quem chamou tratar. Um `except` esquecido em caminho de
   login vira porta aberta.

## Criptografia escrita à mão: a regra do vetor de fora

`p256.py` e `github_app.py` são conta de criptografia transcrita à mão. Vale uma
regra sem exceção:

> Código de criptografia testado **só com dado que ele mesmo produziu não está
> testado** — prova que concorda consigo, não que está certo.

Todo vetor vem de fora: `p256.py` é conferido contra a RFC 6979 A.2.5;
`github_app.py` é conferido **byte a byte contra o OpenSSL**. Peça nova de
criptografia sem testemunha externa não entra.

## Segredo

- Nada de segredo em código, log, commit, memória ou documentação. Registre
  **onde** o segredo mora, nunca o valor.
- O varredor `secret-scan.sh` barra o commit por **forma**, não por conteúdo:
  um bloco `-----BEGIN ... PRIVATE KEY-----` literal e qualquer
  `token = <16+ caracteres>` são bloqueados mesmo sendo dado de teste. Em
  `test_github_app.py` a chave de teste é guardada **sem a armadura**, remontada
  em tempo de execução — e os tokens de mentira têm menos de 16 caracteres.
- O hook `secret-read-guard.sh` barra pelo **texto do comando**: mencionar um
  arquivo `.pem` numa linha de comando é recusado, mesmo que a leitura seja
  inofensiva. Renomeie o arquivo temporário.

## Os arquivos de `assets/` sao permissao por caminho EXATO

A lista nasce de uma leitura da pasta **na subida** — arquivo novo so passa a
ser servido depois de reiniciar `servir.py`. E `assets/painel.js` e
`assets/painel.css` **exigem sessao** (classe de acesso `dado`), porque juntos
eles sao a tela inteira do painel; o resto de `assets/` e aberto, porque a
cortina precisa carregar antes de qualquer login.

A trava casa por caminho exato: **renomear um dos dois a desliga em silencio.**
`test_rotas.py` cobra que os dois nomes existam na tabela, e `test_servir.py`
sobe o servidor de verdade para conferir 401 sem sessao e 200 com ela — ler a
tabela nao basta, as duas ja divergiram aqui.

## As duas travas da Fatia 2

**`tarefas.py` é o único lugar onde mora "esta tarefa pode rodar agora?"** A
pergunta é feita duas vezes — pelo servidor antes de entregar, pelo agente
antes de disparar — e as duas respostas vêm do mesmo código. Ele **não importa
`execucao`, `fila` nem `banco`**, e há um teste que roda num processo novo para
provar. Se importasse `execucao`, o `Dockerfile` teria de levar `execucao.py`, e
`test_imagem.PROIBIDOS` reprova.

**Mesmo código não basta: as duas chamadas precisam dos mesmos FATOS.** Medido
em produção em 03/09/2026, com as 26 suítes verdes. `servir._tarefa_pendente`
avaliava a **linha do banco** (que tem `aprovado_em`) e entregava ao agente um
dicionário **montado à mão, sem esse campo**. O agente refazia a mesma pergunta,
no mesmo `tarefas.pode_rodar`, e recusava: *"esta tarefa esta vermelha e espera
o seu clique"* — para uma tarefa aprovada 93 segundos antes. Como **toda regra
nasce vermelha**, nenhuma tarefa aprovada pelo dono jamais rodou: o braço
executor estava morto desde que existe. `tentativas` tinha o mesmo defeito, e
por isso o teto de tentativas só valia do lado do servidor.

Nenhum teste pegou porque **não havia nenhum sobre `_tarefa_pendente`**, e o
caso ponta a ponta de `test_agente.py` monta o dicionário da tarefa **à mão**,
em vez de pedi-lo ao servidor — provava o executor, nunca a entrega. O guarda
que fecha isso é `test_servir.OQueOServidorEntregaSatisfazAChecagemDoAgente`:
ele pega o que `_tarefa_pendente` devolve e passa em `pode_rodar`. **Campo novo
que `pode_rodar` consulte tem de entrar naquele dicionário, e esse teste é quem
cobra.**

Os tetos (`TETO_USD`, `USD_BRL`, `TETO_DIARIO_BRL`, `MAX_TURNOS`,
`MAX_TENTATIVAS`) **mudaram de casa para lá**. `fila.py` e `execucao.py`
reexportam os mesmos objetos, e um teste cobra a identidade — não há um segundo
valor no repositório.

**`GET /api/eventos` é a única resposta deste servidor que não é uma string
inteira.** É um `text/event-stream`. Três coisas quebram em silêncio se
mexidas: o cabeçalho `X-Accel-Buffering: no` (sem ele o nginx segura a
resposta), o bloco `location = /api/eventos` do `infra/nginx-dervs.conf` (que
não pode ter **nenhum** `add_header` — um `add_header` dentro de um `location`
anula os seis do `server`), e a sonda de um segundo dentro do laço, que é o que
faz o servidor perceber que a aba fechou e devolver a vaga.

Teste de fluxo **sempre com prazo em toda leitura**: sem prazo ele não falha,
ele pendura, e suíte pendurada é pior que suíte vermelha.

## As três portas (01/09/2026) — o que não se afrouxa

**A peneira anti-SSRF é reusada, nunca copiada.** `coletar_github.url_segura`,
`enderecos_publicos`, `host_publico` e `mede_site` são chamadas **qualificadas** a
partir de `servir.py`, e nunca `from coletar_github import`: `test_rotas.EXECUTA`
guarda a palavra `coletar`, e `servir.coletar` existe como função de módulo. Uma
segunda cópia dessa peneira já matou o *drift* em silêncio com 926 testes verdes.

**O IP é FIXADO entre a peneira e a conexão.** `mede_site` resolve o nome **uma
vez** e conecta naquele endereço, com `Host` e SNI no nome original. Antes eram
três resoluções, e só a última decidia o destino: um nome com TTL zero
alternando entre um IP público e `172.17.0.x` passava pela peneira e conectava
dentro da rede — e a VPS tem 26 contêineres sem outra porta de entrada. Um nome
que resolva para **qualquer** endereço interno é recusado inteiro.

**Provar que a instalação do GitHub existe não é provar que ela é sua.** O
`installation_id` é público e sequencial. `_instalacao_e_dele` confere o
`account.id` contra o id do GitHub amarrado àquela conta, e a tabela tem
`UNIQUE (installation_id)`. As duas travas são independentes de propósito.

**Instalação em ORGANIZAÇÃO: só ADMIN confere, nunca "é membro" (04/09/2026,
PR #25).** `github_app.usuario_administra_a_organizacao` pergunta ao próprio
app (token da instalação, `?role=admin`) se o dono da sessão administra a
org. Achado de revisão de segurança, antes de mesclar: aceitar qualquer
membro deixaria alguém sem direito de instalar nada pedir o próprio selo e
amarrar a instalação da organização inteira à própria conta — travando o
dono legítimo para sempre. Nunca afrouxe para `?role=` vazio ou para a lista
de membros pura; o teste `test_nao_confere_quando_o_id_nao_e_admin` existe
para isso.

**Todo código de seis dígitos ocupa uma vaga num espaço COMPARTILHADO.**
`codigo_hash` é chave primária global; sem `limpar_pareamentos_vencidos` e sem o
teto de criação por origem (balcão `codigos`), quem gerasse códigos em laço
trancava o dono junto. Vale para as duas rotas que criam código.

**O conectador não importa nada deste repositório, e o servidor não importa o
conectador.** Ele é **lido** do disco e injetado; importar arrastaria `tkinter`
para dentro da imagem. Por ser lido e não importado, ele é invisível para o
teste que cobra os módulos — o nome entra à mão no `Dockerfile` e em
`test_imagem`.

**A linha que a tela entrega carrega `<CAMINHO DO DERVS>`, e isso é de
propósito.** O painel não pode saber onde o repositório está na máquina de quem
lê. `test_conectar_ponta_a_ponta` reprova se o espaço reservado sumir.

## As duas travas de 02/09/2026

**Chegar ao servidor não põe a variável dentro do container.** São dois
arquivos, mantidos por mãos diferentes: o `/opt/dervs/.env` do servidor
(gravado à mão pelo administrador desde 25/09/2026; antes, pelo `publicar.yml`),
e o bloco `environment:` do `docker-compose.yml` é que passa aquilo
para dentro do processo. As três variáveis do GitHub App tinham a primeira
metade e não a segunda — a porta 2 estava morta em produção **por
construção**, e a tela dizia "o aplicativo não está registrado", que é a mesma
frase do estado legítimo. `test_publicar.OContainerRecebeOQueOCodigoLe` compara
as **duas listas** — toda leitura de ambiente de `servir.py` e `banco.py`
contra o compose. Variável nova sem entrada reprova; deixar de fora exige
motivo escrito em `FORA_DO_COMPOSE_DE_PROPOSITO`.

**Resposta escrita não é resposta entregue.** `protocol_version` é HTTP/1.0:
o soquete fecha depois de toda resposta. Quem **recusa** um POST (401, 403,
404, 500) responde em `_despachar` antes de qualquer rota rodar, e as rotas são
os únicos lugares que leem `rfile` — recusa deixava o corpo intocado. Fechar
com bytes por ler gera RST em vez de FIN, e o RST **descarta a resposta já
entregue ao buffer do outro lado**. Por isso o dreno vive em
`handle_one_request`, e não no despacho: ali passa **todo verbo**, inclusive o
`405` do `HEAD` e o `501` de `PUT`/`DELETE`/`PATCH`, que não passam por rota
nenhuma. Uma primeira versão morava em `_despachar` e cobria só `GET` e `POST`
— "rota nova já nasce coberta" era verdade para rota, não para verbo.

`test_rotas` lê o código-fonte de `_despachar` para cobrar a conferência de
acesso, **e um segundo caso cobra que `do_GET`/`do_POST` chamem justamente
essa função**. Sem essa ponte, o guarda fica verde lendo código que ninguém
executa — foi o que quase aconteceu quando o dreno mudou de casa.

*Medido antes do conserto:* 189 de 405 pedidos com corpo deixavam bytes por
ler, e a suíte caía em 2 de 24 corridas, em caso diferente a cada vez. **Não
era o Windows, e não era o teste.**

## As travas da Auditoria Profunda (02/09/2026)

**O fio só existe se alguém provar o fio inteiro.** A auditoria foi construída em
sete etapas, cada uma com teste próprio, e as **26 suítes ficaram verdes com a
funcionalidade morta**: nada em lugar nenhum produzia a chave `achados` no
desfecho, e o bloco que grava em `servir._resultado` era inalcançável. A
auditoria rodaria, gastaria o teto do dia e não gravaria nada. Cada etapa provou
a sua metade contra dublê; ninguém tinha escrito o caso que sobe um desfecho de
verdade pelo fio do agente e termina com achado no banco. **Esse caso agora
existe em `test_agente.py`, e é ele que não pode ser apagado.**

**O JSON dos achados NÃO vai no `resumo`.** `servir._resultado` corta `resumo`
em 4.000 caracteres, e um JSON cortado não é um JSON menor — é lixo. Ele sobe num
campo próprio, com `auditoria.TETO_DOS_ACHADOS`, que é **derivado do esquema**
(`MAX_ACHADOS * 4096`), nunca digitado.

**A identidade de um achado inclui o dono.** `achado` tem `PRIMARY KEY
(usuario_id, id)`, e o `ON CONFLICT` **nunca** escreve `usuario_id` no `SET`.
Antes, o id era `regra:projeto:sha256(...)` — determinístico e sem o dono: duas
contas auditando o mesmo repositório da mesma org geravam o mesmo id, e a segunda
gravação **transferia a linha**, sumindo o achado do painel da primeira. Há um
guarda de código-fonte cobrando a ausência daquela linha no `SET`, porque a chave
composta tornou o defeito **código morto** — e teste de comportamento não acusa
código que não roda.

**`PROJETOS_BLOQUEADOS` mora em `tarefas.py`.** Mudou de casa porque
`_auditoria_pedir` precisa dela e `servir.py` não pode importar `execucao`.
`execucao.py` **reexporta o mesmo objeto**, e um teste cobra a identidade (`is`).
A comparação é insensível a caixa — havia um teste provando que `Ajudei-Saude`
escapava.

**Quem pede auditoria só pede dos projetos da própria conta**, e "não existe" e
"não é seu" devolvem **a mesma resposta**. A tabela `fila` não tem `usuario_id`:
sem essa conferência, uma conta enfileirava trabalho na máquina da outra e
queimava o teto de R$ 50, que é compartilhado.

**`achados` sem id estoura, não é pulado.** `banco.gravar_auditoria` já contou o
achado em `achados_n` antes do laço; pular em silêncio gravaria uma corrida
dizendo "3 achados" com zero linhas na tabela — um contador que não abre nada.

**A poda dos achados em `/api/dados` é DEPOIS do motor, nunca na origem.** É de
`banco.montar_estado` que `regras.avaliar` lê os achados para virar pendência.
Podar lá em cima deixa as rotas verdes e mata a entrega em silêncio; por isso há
um terceiro teste que lê `montar_estado` direto e exige os achados lá.

**Trabalho de executor paralelo mora em worktree — e worktree se apaga.** Duas
perdas de trabalho em 02/09: um executor usou `git checkout -- <arquivo>` para
desfazer uma sabotagem e apagou junto o trabalho não commitado do mesmo arquivo;
e o coordenador removeu uma worktree já mesclada em que **outro** executor estava
trabalhando. **Desfaça sabotagem editando de volta, e commite cedo.**

## Servidores múltiplos (04/09/2026)

`novo["sites"]` é **lista**, nunca `site` (singular). Um item por servidor, cada
um com o próprio `medido_em` — quando um servidor não é medido numa rodada
(`ok=None`), só **aquele** item preserva a medição anterior, nunca a lista
inteira. Uma ponte em `regras.py` ainda lê o formato antigo `site` para um
`hub.db` cuja última coleta seja de antes desta mudança; ela morre sozinha na
primeira coleta boa daquele projeto.

O sufixo do id de pendência `site_fora` é o **`servidor_id`**, nunca o nome do
servidor: nome se renomeia, id não, e nome + projeto pode estourar o teto de 200
caracteres de `_id_de_pendencia`.

`padrao_subdominio` tem um jeito só de dizer "nenhum": `NULL` no banco. A
conversão para `""` acontece **só** na borda da rota (`servir.py`), nunca em dois
lugares.

`banco.um_endereco_por_projeto` (a antiga `enderecos_de_producao`) é a régua de
prontidão do `casos.json` (`coletar.py`) — **não responde** "o projeto está no
ar". Quem responde isso é `banco.enderecos_por_servidor`. Confundir as duas é o
jeito mais fácil de reintroduzir a mentira que a Lei 2 proíbe.

Os balcões `"servidor"` e `"sugestao"` em `servir.py` são **próprios**;
`TETO_DE_ENDERECOS` nunca é emprestado por uma rota nova — cada rota paga o
próprio teto, pelo mesmo motivo de sempre (`servir.py`, comentário perto de
`TETO_DE_ENDERECOS`).

A sugestão de autodetecção por padrão de subdomínio **propõe e para**: a rota
`/api/servidores/sugerir` nunca grava uma linha, e a tela só pede sugestão uma
vez por servidor por sessão (nunca a cada repintura — cada medição pode levar até
~23s, e um servidor com padrão pode ter até 3 candidatos por chamada).

## O botão "Consertar com IA" e o menu de quatro (29/09/2026)

`POST /api/consertar` só **enfileira**; quem roda é o braço executor, depois do
"Pode fazer". Quatro coisas que quebram em silêncio se mexidas:

- **A lista de regras mora em `tarefas.REGRAS_CONSERTAVEIS_PELA_TELA`**, não em
  `fila.py`: `servir.py` não pode importar `fila`. `fila.py` reexporta o mesmo
  objeto (teste de identidade). Fica **fora** dela `dependencia_insegura`,
  `auditoria_vencida` e todo achado de segurança — IA em segurança só com revisão.
- **`consertavel` em `/api/dados` é posto DEPOIS do motor** e sai falso em projeto
  de `PROJETOS_BLOQUEADOS`. Botão que o servidor sempre recusaria é botão que mente.
- **O id da fila leva o dono** (`regra:usuario:id_da_pendência`), pelo mesmo
  motivo da auditoria. `INSERT OR IGNORE` devolve 0 para linha existente em
  QUALQUER estado; por isso o pedido repetido lê a linha (com `usuario_id` no
  `WHERE`) e diz o estado real. Antes dizia "já estava na fila" para conserto
  que falhou ou terminou — achado de dois revisores, independentes.
- **Balcão próprio** (`consertar`, teto 10): um teste esgota o dele e exige que a
  auditoria ainda responda.

O menu tem **exatamente quatro** itens e `test_menu.py` cobra isso, mais que cada
endereço antigo (`#/consumo`, `#/entrada`, `#/computadores`) redirecione. Item
novo no menu exige mexer no teste — de propósito.

**Pendente de propósito:** `memoria_crlf` vai ao braço `claude`, embora
`fila.REGRAS_MECANICAS` a mapeie para `mecanico` (Haiku, mais barato); e
`fila.trabalhar` usa o id `regra:projeto`, sem o dono — hoje ninguém o chama em
produção, mas quem o ligar duplica a tarefa.

## A ponte com o DERVS-VOZ (30/09/2026)

O DERVS-VOZ é outro repositório (`repos\dervs-voz`, programa de voz no PC do dono).
Ele fala com este servidor por **três rotas de máquina**, sempre **de saída** (o VOZ
nunca escuta porta): `POST /agente/voz/estado`, `GET /agente/voz/recados`,
`POST /agente/voz/resultado`, mais `POST /agente/voz/pedido` (o VOZ pede conserto de um
alerta; o miolo é `Hub._enfileirar_conserto`, o MESMO do botão da tela, e a tarefa nasce
esperando o "Pode fazer" do dono); e o dono usa `GET /api/voz` e `POST /api/voz/recado`.
Mesmo token de máquina pareada do agente. Quatro coisas quebram em silêncio:

- **`/estado` NÃO é sinal de vida.** `test_nao_existe_rota_de_sinal_de_vida_separada`
  proíbe, e a razão vale: "estou vivo" separado deixa a máquina parecer saudável
  com a medição parada. A vigília é julgada só por `maquina.visto_em`, carimbado
  pelo `/agente/relatorio`; `voz_estado` não o toca (há guarda de código-fonte).
- **A tela manda `maquina_id` como número com `+$(...)`, nunca `Number(`.** Um
  `<select>` entrega texto e o servidor exige `int`: sem a conversão todo recado
  voltava 400, e `test_voz.py` (corpo montado à mão) ficou verde com a função
  morta. O `+` é de propósito: `test_design` toma `Number(`/`parseInt(` por
  "número na tela sem carimbo". O guarda é `test_voz_tela.OPedidoQueATelaMonta...`.
- **Entrada válida em JSON que o SQLite recusa tem de dar 400, não 500**: inteiro
  fora de 64 bits (`10**30`), `10**400` em float, e surrogate solto (`"\ud800"`)
  em texto. `_texto_gravavel` e `_numero_finito` existem por isso.
- **Estado que nunca expira tranca o dono.** O teto de 20 recados pendentes só
  conta computador vivo e vence em 24 h (`criar_voz_recado`).
- **`avisar` é só do painel e só `leitura`** (aviso de alerta começa com `[alerta:<id>] `, id só com caracteres seguros, total <=500) (`_varrer_vigilia`, chamada por
  `_varrer_mudas`, no máximo 1x/min). Um aviso por ocorrência (`voz_aviso`), teto 5 por
  varredura, nada para conta sem VOZ fresco, e a chave e o recado entram na MESMA
  transação (`avisar_uma_vez`). `test_voz_avisos.py` cobra; a varredura nunca levanta.

**O terminal SSH mora no DERVS-VOZ e NUNCA no painel web** (o `vivo/` tinha um
terminal sem autenticação e foi removido de propósito). O recado `nivel=muda_estado`
só anda com clique do dono **no VOZ**; aprovar no painel não basta.

**JEV (typesafe.ai) não é cérebro de conversa**: é um classificador rápido
(`POST https://api.typesafe.ai/v1/systemone`, `TYPESAFE_API_KEY`, perguntas
`noul`/`choice`/`score`). Serve para triagem; Claude Code e Hermes são os que trabalham.

## Progresso pela documentação e "Desenvolver isto" (30/09/2026)

Formato do documento: `docs/A-DOCUMENTACAO-QUE-O-DERVS-LE.md`; plano e contrato
servidor↔tela: `docs/superpowers/plans/dervs-progresso-por-documentacao.md`. O que
a próxima sessão erraria:

- **Percentual só em `estado === "medido"`.** `nao_verificado`, `sem_documentacao`
  e `sem_dados` têm `percentual: null`, e a tela nunca escreve `%` nem `0` ali.
  `declarados` (`[x]` sem prova rodada) nunca entra em `comprovados`: o servidor
  **recalcula** dos critérios crus e ignora qualquer percentual que o agente mande.
- **O selo de saúde não lê `progresso`.** A conta entra em `_estado` DEPOIS do motor
  e do selo; `regras.py` não lê a chave `documentacao`.
- **Texto de critério é dado de outro repositório:** só `textContent`; a prova nunca
  vai a um terminal (só a lista fechada, sem shell) e nesta entrega nem roda.
- **`desenvolver` não entra em `NUNCA_VERDE`** (seria recusado antes da aprovação e
  nunca rodaria): mora em `tarefas.SEMPRE_VERMELHA`. O botão só existe atrás de
  `c.desenvolvivel === true`, o corpo do POST é só `{criterio: c.id}`, e o servidor
  acha o critério no estado DA CONTA.
- **O leitor não sai do repositório nem abre tudo.** `documentos.ler_projeto`
  resolve `docs/esteira` (e cada pasta e arquivo) com `resolve()` e recusa, com erro
  visível, o que cair fora do repo (link simbólico **e** junction, que
  `is_symlink()` não vê); para no 31º documento e abre no máximo `MAX_VARRIDOS`
  (120) briefings. Sem o `break` ou sem o `resolve`, os testes reprovam.
- **`desenvolver` mostra o pedido antes do clique.** `banco.tarefas_do_painel` traz
  `detalhe` (cortado em 300 no SQL) e `linhaDeTarefa` o escreve por `textContent`,
  com o rótulo "O que foi pedido:". `banco.enfileirar` corta o `detalhe` em 4096.
  `tarefas.so_dado` neutraliza a etiqueta do bloco por regex (caixa, espaço,
  `< /...>`), e `projeto_pode_desenvolver` normaliza `_`/espaço/`.` para `-` e
  bloqueia por prefixo na fronteira do `-`. `test_progresso_fio.py` prova o fio
  inteiro (briefing real -> `/agente/relatorio` -> `/api/dados` e `/api/progresso`
  -> campos que o `painel.js` lê): renomear um campo de um lado só reprova.
- **Quem pergunta "projeto bloqueado?" chama `tarefas.projeto_bloqueado`
  (01/10/2026).** Cinco pontos comparavam `.lower() in PROJETOS_BLOQUEADOS` e
  `Ajudei_Saude` escapava de auditoria, consertar, fila e execução. Comparação
  nova só pelo helper (normaliza e bloqueia por prefixo na fronteira do `-`);
  `test_desenvolver` lê o fonte e reprova a forma antiga. `so_dado` também
  normaliza NFKC e tira caracteres Cf (`＜`, zero-width) e não tem mais
  backtracking quadrático (`\s{0,16}`, não `\s*`).
- **O corte do leitor nunca é mudo.** Passar de `MAX_VARRIDOS` abertos ou de
  `MAX_PASTAS` listadas vira erro visível ("há mais briefings que o limite"),
  senão o painel diria "sem documentação". O teto do JSON da chave subiu para
  32 KiB: com os 11 briefings do próprio DERVS convertidos (115 critérios,
  ~28 KiB) o último ficava sem critério nenhum. Os briefings antigos estão em
  `- [ ]` (nada marcado `[x]`: marcar é julgamento por critério).
- **Em Consertar, o comando da prova sai à parte** (`prova` em
  `banco.tarefas_do_painel`): ele fica no fim do pedido e o corte em 300 o
  esconderia — o dono aprovaria um comando que não leu.
- **Não nomeie rota nem função `documentacao`:** `test_rotas.PROIBIDO` casa
  `acao|exec|comando|shell`, e "documentACAO" casa.
- **Projeto acima de 64 KiB é descartado INTEIRO** em `banco.receber_relatorio`: o
  agente limita o tamanho da chave (32 KiB) e marca `cortado`.
- **`test_progresso_tela.py` executa as funções de montagem em node** com um DOM de
  mentira (como `test_voz_tela.py`); sem node ele pula só esses casos. Mais o
  `test_design`: `Number(`/`parseInt(` são proibidos (use `+x`).

## Fase 2: as provas (01/10/2026)

**O risco, com todas as letras:** rodar o teste de um repositório é **rodar
código de terceiro com os poderes do dono**. Esse código alcança, entre outras
coisas, o token da máquina em `~/.dervs/agente.json`. A barreira (comando da
lista fechada, sem shell, ambiente limpo, numa cópia) **reduz o dano, não
isola**. O clique "Pode fazer" é a aceitação desse risco; nada roda sem ele
(`provar` está em `tarefas.SEMPRE_VERMELHA`).

- **Resultado só vale com a MESMA prova.** O id do critério não inclui o texto
  da prova: trocar o comando no documento não pode herdar o verde do comando
  antigo. Quem lê o veredito confere a prova gravada contra a atual.
- **`None` nunca é falha (Lei 2).** Prova que não rodou (módulo ausente,
  nenhum teste coletado, prazo estourado) é critério sem resposta, não
  reprovado.
- **O que roda é a interseção** do pedido aprovado com o que existe na cópia: o
  texto do pedido é dado e é revalidado linha a linha. `npm test` **fica fora**
  desta fase (`argv_da_prova` só roda `python`).
- **Nada com "exec" em nome de rota ou função** (`test_rotas.PROIBIDO`): a rota é
  `POST /api/provar`, só `{projeto}`, e o servidor acha os comandos na
  documentação DA CONTA, nunca no corpo.
- **Balcão próprio `provar`** (`TETO_DE_PROVAS`), como o `consertar`.
- **Na tela:** o botão "Rodar as provas" só existe com `provavel === true`
  (`/api/progresso`); 403/404/409/429 viram frase nossa; "provado há …" só em
  `estado === "medido"` e com o carimbo `haQuanto`.

## Testes

- Cada `test_*.py` é um passo próprio na CI, listado **à mão** em
  `.github/workflows/ci.yml`. Há um passo que cobra a lista: arquivo de teste
  novo que não estiver lá deixa a verificação vermelha. Acrescente junto.
- `if __name__ == "__main__"` fica no **fim** do arquivo, sempre. Já houve teste
  que nunca rodou porque essa linha estava no meio.
- **Teste que sobe servidor declara a chave de teste ANTES de importar `banco`:**

  ```python
  os.environ.setdefault("DERVS_AMBIENTE", "local")
  os.environ.setdefault("DERVS_COFRE", "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")
  ```

  Sem isso ele passa aqui e **fica vermelho só na CI** — `chave_do_cofre()`
  recusa inventar chave fora do ambiente local, e o `cofre.chave` existe nesta
  máquina e não no runner. Aconteceu em 29/08/2026 (`45963da`).
- **Guarda de acoplamento se prova sabotando.** Teste que casa texto com texto
  (CSS↔JS, doc↔tela) quase sempre tem um caminho em que a asserção é
  tautológica: verde não distingue "está certo" de "não podia dar errado". Em
  29/08/2026, dois de cinco casos novos eram incapazes de reprovar —
  `id="lista-computadores"` já contém a palavra `computadores`, e uma busca de
  string atravessava aspas. Quebre cada coisa de propósito e exija que o caso
  correspondente acuse.
- Teste com data fixa (`AGORA = datetime(...)`) tem de passar `agora_iso` para
  toda função que compara prazo. Sem isso o teste passa hoje e fica vermelho
  sozinho amanhã, sem ninguém tocar em nada.
- **Falha probabilística não vira teste pelo soquete.** Medido em 02/09: pelo
  soquete de verdade, corpo de 2 KB nunca falhou em 200 tentativas e corpo de
  256 KB falhou 5% das vezes — um teste assim ficaria verde quase sempre com o
  defeito de pé. `OCorpoDoPedidoEDrenado` dirige o handler por um soquete de
  mentira e pergunta pelo **mecanismo**, que é determinístico.
- **Sabote com tamanho, não só com presença.** A sabotagem que fez o dreno
  parar depois do primeiro pedaço deixou a suíte verde: todo corpo dos casos
  cabia num `read(65536)`, e o teste media "leu alguma coisa" em vez de "leu
  tudo". Foi preciso um caso de 200 KiB. Guarda de laço precisa de entrada que
  obrigue mais de uma volta.
- **Rodar dois arquivos não é rodar a suíte.** Em 02/09 a CI ficou vermelha num
  guarda que lê código-fonte, porque um rename mudou a função de lugar e eu só
  havia rodado os dois arquivos que estava mexendo.

## Armadilhas desta máquina

- O terminal do dono é **PowerShell**. `comando < arquivo` não existe lá.
- O heredoc do Bash (`<<'FIM'`) **troca o fim de linha** nesta máquina: texto
  multilinha comparado com o conteúdo de um arquivo nunca casa. Para editar
  arquivo por script, escreva o script com a ferramenta `Write` e rode o
  arquivo — não passe o texto por heredoc.
- O Python é o do Windows: caminho `/c/Users/...` não existe para ele.
- `hub.db` é descartável e não versionado. Apagar custa uma coleta.

## Onde estão as decisões já tomadas

- **`docs/A-APLICACAO.md` — a fonte única. Leia este primeiro; em conflito com
  qualquer outro documento, ele vence.** Responde numa leitura só o que o DERVS
  é, para quem, o que mostra, o que faz e o que nunca vai fazer.
- `docs/esteira/dervs/design.md` — a direção visual (Torre de Controle), os
  tokens, as seis telas e o vocabulário. **Aprovado, não refazer.**
- `docs/esteira/dervs/briefing.md` e `spec.md` — o contrato do produto, fase 1
  e 2, aprovados. **Não refazer.**
- `docs/superpowers/plans/dervs-fatia-1.md` — as 17 etapas, **todas entregues**
  em 28/08/2026, e **o site esta no ar** em `https://dervs.com.br`. A saida dos
  oito comandos da etapa 17 esta colada em `docs/esteira/dervs/verificacao.md`,
  junto com o que eles NAO provam e foi conferido clicando. Das quatro
  pendencias nomeadas la, **duas foram fechadas** no mesmo dia (o `painel.js`
  aberto e a conta que nao dava para apagar) e **duas continuam abertas — as
  duas dependem so da mao do dono**, nao de codigo.
- `docs/superpowers/plans/dervs-fatia-2.md` — **14 das 16 etapas entregues** em
  28/08/2026 (PR #18). O DERVS deixou de so medir: recebe tarefa, abre copia
  isolada, trabalha e devolve um ramo. As duas que faltam **nao sao codigo** —
  a 15 e o portao do dono ("posso instalar o braco na VPS dos 26 containers?"),
  e junto dela a pergunta que **ninguem respondeu**: rodar a assinatura Max num
  servidor e aceitavel nos termos da Anthropic? A pesquisa achou a regra que
  proibe assinatura COM O AGENT SDK, e o DERVS nao usa o SDK — isso nao e a
  mesma coisa que uma resposta.
  A verificacao, com o que ela NAO prova, esta em
  `docs/esteira/dervs-fatia-2/verificacao.md`.
- `docs/superpowers/plans/dervs-conectar-tres-portas.md` — as 15 etapas de
  "Conectar em tres portas", **todas entregues** em 01/09/2026. A verificacao,
  com os doze itens que os comandos NAO provam, esta em
  `docs/esteira/conectar-tres-portas/verificacao.md`. **Duas revisoes
  (seguranca e Python) acharam cinco buracos reais, todos corrigidos ali
  mesmo** — o pior deles era a peneira medir um endereco e conectar em outro.
- **Cuidado com a palavra "fusao"** no §11 da fonte unica: a dos REPOSITORIOS
  esta entregue desde a etapa 1 (o `dervs-hub` vive em `vivo/`); o que o dono
  pediu em 28/08 a noite e a das CAPACIDADES, reescritas em Python. Isso entra
  pela esteira, comecando pelo briefing — "tudo que um DEV precisa" e intencao,
  nao escopo, **e continua sem comecar**.
- **O que esta no ar pode ser mais velho que a `main`.** Em 29/09/2026 as
  15:15 subiu o commit `96eb3fc` (menu de quatro e botao Consertar), pelo
  VS Code, e a rota nova `/api/consertar` responde 401 sem sessao (uma rota
  inventada responde 404). Depois disso, confira qual commit esta no ar antes
  de dizer ao dono que a tela mudou (`ssh vps-ovh sudo deploy --lista`; as
  etiquetas `publicado-*` so cobrem ate 04/09/2026, quando o GitHub ainda
  publicava).
- `docs/operacao/` — os roteiros que exigem a mão do dono (GitHub App, entrar,
  conectar computador, **publicar no servidor**).

## Publicação

- **Deploy pelo VS Code (desde 25/09/2026).** Commit + push para a `main`, e a
  tarefa **"Deploy para a VPS"** (`.deploy-vps`, `scripts/deploy-vps.*`). O
  servidor faz backup do volume `dervs-dados`, monta a imagem ali mesmo
  (`build: .`, imagem `dervs:vps`), confere `https://dervs.com.br/robots.txt` e
  volta sozinho se falhar. Padrão: https://github.com/garcia-goncalves/deploy-padrao .
  O GitHub **não publica mais nada** — o `publicar.yml` foi removido.
- O que o `publicar.yml` fazia de administração (gravar OAuth/GitHub App no
  `.env`, trocar a cortina, convidar donos) agora é **manual no servidor**, com
  o administrador: `docs/operacao/publicar-no-servidor.md`, passo 6.
- **A VPS não é terreno limpo:** vários sistemas na mesma máquina. Porta alta
  nova, conferida antes; arquivo de nginx novo; nenhum script escreve em
  `/etc/nginx/sites-enabled/`.
- **A imagem é conferida subindo, não lendo.** `test_imagem.py` cobra a lista de
  cópia do `Dockerfile` contra o que `servir.py` importa de verdade; o deploy
  sobe o container e bate no domínio. A CI sozinha não pega isso: ela roda os
  testes, não a imagem.
