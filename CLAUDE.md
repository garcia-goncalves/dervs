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
arquivos, mantidos por mãos diferentes: `publicar.yml` escreve no ambiente do
servidor, e o bloco `environment:` do `docker-compose.yml` é que passa aquilo
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
- **O que esta no ar e MAIS VELHO que a `main`.** A ultima publicacao levou a
  Fatia 2; tudo de 29/08 (a tela de Computadores refeita e as mensagens do
  agente) esta so no GitHub. Antes de dizer ao dono que a tela mudou, confira
  se a etiqueta `publicado-*` mais nova cobre o commit em questao.
- `docs/operacao/` — os roteiros que exigem a mão do dono (GitHub App, entrar,
  conectar computador, **publicar no servidor**).

## Publicação

> ### As quatro portas da fila fecharam (04/09/2026) — falta só o sinal do dono
>
> A tabela `fila` ganhou `usuario_id` (migração em `_migrar_fila_semaforo`,
> preenchida por `enfileirar` e por `servir._auditoria_pedir`), e as quatro
> travas que faltavam agora conferem o dono no `WHERE`: `banco.aprovar_tarefa`,
> `banco.pedir_parada` (chamada por `servir._tarefa_parar`, que passa a receber
> o usuário), `banco.tarefa_para_maquina` e `banco.tarefas_do_painel`. De
> quebra, o mesmo furo existia no `?id=` de `/api/tarefas` e no fluxo ao vivo
> (`/api/eventos`) — os dois também passaram a exigir o dono. Sabotado de
> proposito (removendo a condição em `aprovar_tarefa`) para provar que o
> teste novo pega: pegou. 622 testes de `banco`/`servir`/`fila`/`sse` verdes,
> 6 deles escritos para provar cruzando duas contas.
>
> **O que falta não é código: é o sinal do dono para publicar** — a "porta 2"
> de sempre (`docs/regras/ambientes-e-publicacao.md`), e o lote inclui também
> o conserto do braço executor (`2b7b2eb`..`84c3f64`). Apague este bloco quando
> a publicação sair.


- **O deploy roda no GitHub, nunca daqui.** Nada de `ssh`, `scp`, `rsync` ou
  `docker compose` apontados para o servidor saindo desta máquina.
- `.github/workflows/publicar.yml` dispara **só** por `workflow_dispatch`, com a
  palavra `PUBLICAR` digitada. Um passo dele falha se alguém acrescentar gatilho
  automático — a trava é o próprio arquivo se conferindo.
- **A VPS não é terreno limpo:** 26 containers, 8 sistemas. Porta alta nova,
  conferida antes; arquivo de nginx novo; nenhum script escreve em
  `/etc/nginx/sites-enabled/`.
- **A imagem é conferida subindo, não lendo.** `test_imagem.py` cobra a lista de
  cópia do `Dockerfile` contra o que `servir.py` importa de verdade; o workflow
  sobe o container e bate na porta. A CI sozinha não pega isso: ela roda os
  testes, não a imagem.
