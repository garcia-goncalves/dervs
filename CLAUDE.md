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
