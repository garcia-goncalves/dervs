# Links e comandos deste projeto

O HUB do dev é um painel local: uma página só, servida pelo seu próprio
computador, que mostra o estado dos seus projetos (git, Docker, CI, alertas de
segurança, gasto do Claude) e deixa você agir sobre as pendências por botão.

## Links

```
DESTE PROJETO
  Painel ........... http://localhost:4777
  Banco de dados ... hub.db (arquivo SQLite na raiz do projeto)

DEPENDÊNCIA EXTERNA (não é deste projeto, mas o painel usa)
  Grafo do código .. http://localhost:9749   (codebase-memory-mcp)
```

**O que não existe, e por quê:**

- **Não tem `/api/health`.** O painel é uma página só; a prova de que subiu é a
  raiz responder HTTP 200.
- **Não tem tela de login.** O servidor escuta apenas em `127.0.0.1`, ou seja,
  só o seu próprio computador alcança. Contra o risco real — outro site aberto
  no seu navegador disparando um comando aqui — a proteção é um **token
  sorteado a cada vez que o painel sobe**, injetado só na página que o servidor
  entrega.
- **Não tem Postgres nem Docker próprio.** O painel guarda tudo num arquivo
  SQLite (`hub.db`). Ele *observa* os containers dos outros projetos, mas não
  sobe nenhum.

## Como subir

Na janela do VS Code deste projeto, terminal na pasta do projeto:

```
pythonw servir.py
```

Depois abra http://localhost:4777. Se der certo, a página do painel aparece.

Para escolher outra porta e outro intervalo de atualização:

```
python servir.py 4780 30
```

## Como derrubar

```
Get-Process pythonw | Where-Object { $_.Id -eq <NUMERO_DO_PROCESSO> } | Stop-Process -Force
```

Para descobrir o número do processo que está na porta 4777:

```
Get-NetTCPConnection -LocalPort 4777 -State Listen | Select-Object OwningProcess
```

## Se a porta 4777 já estiver ocupada

O sintoma é o painel não subir e o log acusar endereço em uso. Duas saídas:

1. **É o próprio painel, já no ar.** Confira abrindo http://localhost:4777. Se a
   página aparecer, não há nada a fazer — já está de pé.
2. **É outra coisa.** Descubra quem é com o comando `Get-NetTCPConnection` acima
   e decida: derrubar aquilo, ou subir o painel noutra porta com
   `python servir.py 4780 30`.

## Depois de reiniciar o painel, recarregue a aba

O token é sorteado a cada inicialização. Uma aba aberta desde antes do reinício
fica com o token antigo e os botões de ação param de funcionar. **Aperte F5 na
página** e volta ao normal.

## Credenciais

Não há nenhuma. Este painel não tem usuário nem senha — ver "Não tem tela de
login" acima. Nada aqui deve ser exposto à internet.
