# Links e comandos deste projeto

O HUB do dev é um painel local: uma página só, servida pelo seu próprio
computador, que mostra o estado dos seus projetos (git, Docker, CI, alertas de
segurança, gasto do Claude).

**Desde a etapa 7 do DERVS (26/08/2026), ele só mostra — não age.** As rotas
que rodavam `git push`, `docker compose up`, abriam o VS Code e disparavam uma
sessão do Claude foram removidas, porque este painel vai passar a rodar num
servidor exposto à internet. O que sobrou de botão: esconder um alerta por 24 h
e trocar o tema.

## Links

```
DESTE PROJETO
  Painel ........... http://localhost:4777
  Banco de dados ... hub.db (arquivo SQLite na raiz do projeto)

```

O grafo de código (`codebase-memory-mcp`, porta 9749) **não é mais dependência
deste projeto**. O painel embutia a tela dele por procuração; esse proxy saiu na
etapa 7. Ele continua existindo como ferramenta do Claude Code, à parte.

**O que não existe, e por quê:**

- **Não tem `/api/health`.** O painel é uma página só; a prova de que subiu é a
  raiz responder HTTP 200.
- **Não tem tela de login** — ainda. O servidor escuta apenas em `127.0.0.1`,
  ou seja, só o seu próprio computador alcança. A única rota que escreve
  (`/api/silenciar`, o "x" que esconde um alerta) exige um **token sorteado a
  cada vez que o painel sobe**, injetado só na página que o servidor entrega.

  **Atenção para a etapa 16:** o `/api/dados` não tem autenticação nenhuma e
  devolve o caminho absoluto das suas pastas. Quem segura isso hoje é escutar só
  em `127.0.0.1`. Trocar esse endereço para aceitar a internet **antes** de as
  etapas 8 e 9 (banco multiusuário e login) estarem prontas publicaria o painel
  inteiro para leitura anônima.
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

## Mudou um arquivo `.py`? Reinicie o servidor

O `servir.py` importa `regras.py`, `banco.py` e `coletar.py` **uma vez, quando
sobe**. Editar esses arquivos não muda nada na tela enquanto o processo não
reiniciar — a página continua servindo a versão que estava em memória.

Isso engana de um jeito caro: você conserta um defeito, confere na tela, o
defeito ainda está lá, e você vai investigar código que já estava certo. Foi o
que aconteceu em 26/08/2026.

Derrube (receita acima) e suba de novo. Depois recarregue a página.

Mudança só no `index.html` **não** precisa disso: o arquivo é lido a cada
pedido — basta recarregar a página.

E `python coletar.py` também não basta sozinho: ele grava no `hub.db`, mas quem
calcula as pendências é o processo do servidor.

## Se a porta 4777 já estiver ocupada

O sintoma é o painel não subir e o log acusar endereço em uso. Duas saídas:

1. **É o próprio painel, já no ar.** Confira abrindo http://localhost:4777. Se a
   página aparecer, não há nada a fazer — já está de pé.
2. **É outra coisa.** Descubra quem é com o comando `Get-NetTCPConnection` acima
   e decida: derrubar aquilo, ou subir o painel noutra porta com
   `python servir.py 4780 30`.

## Depois de reiniciar o painel, recarregue a aba

O token é sorteado a cada inicialização. Uma aba aberta desde antes do reinício
fica com o token antigo e o "x" de esconder alerta para de funcionar. **Aperte
F5 na página** e volta ao normal.

## Credenciais

Não há nenhuma. Este painel não tem usuário nem senha — ver "Não tem tela de
login" acima. Nada aqui deve ser exposto à internet.
