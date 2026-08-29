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

## Testes

- Cada `test_*.py` é um passo próprio na CI, listado **à mão** em
  `.github/workflows/ci.yml`. Há um passo que cobra a lista: arquivo de teste
  novo que não estiver lá deixa a verificação vermelha. Acrescente junto.
- `if __name__ == "__main__"` fica no **fim** do arquivo, sempre. Já houve teste
  que nunca rodou porque essa linha estava no meio.
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
- **A Fatia 2 ainda nao comecou.** O pedido do dono em 28/08 a noite ("a fusao
  das aplicacoes... tudo que um DEV precisa") esta transcrito no §11 da fonte
  unica. **Cuidado com a palavra "fusao":** a dos REPOSITORIOS esta entregue
  desde a etapa 1 (o `dervs-hub` vive em `vivo/`); o que ele pede agora e a das
  CAPACIDADES, reescritas em Python. Isso entra pela esteira, comecando pelo
  briefing — "tudo que um DEV precisa" e intencao, nao escopo.
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
