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
- `docs/superpowers/plans/dervs-fatia-1.md` — as 17 etapas. Etapas 1 a 14
  entregues.
- `docs/operacao/` — os roteiros que exigem a mão do dono (GitHub App, entrar,
  conectar computador).
