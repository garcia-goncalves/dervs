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
- **Não tem cadastro aberto.** Conta só nasce por convite, rodado por quem tem
  acesso à máquina (`python autenticacao.py convidar …`). Não existe rota de
  registro, e um teste reprova a suíte se alguma aparecer.
- **Não tem recuperação por e-mail.** É decisão, não falta: quem perde todas as
  formas de entrar não abre a conta. Por isso o painel cobra a segunda forma —
  ver `docs/operacao/formas-de-entrar.md`.
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

O `servir.py` importa `regras.py`, `banco.py`, `coletar.py`, `cortina.py` e
`passkey.py` **uma vez, quando sobe**. Editar esses arquivos não muda nada na tela enquanto o processo não
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

O token anti-falsificação é derivado da **sua sessão**, e vai dentro da página
que o servidor entrega. Uma aba aberta desde antes do reinício pode ficar com um
token que não vale mais, e aí os botões que escrevem param de funcionar.
**Aperte F5** e volta ao normal.

## Entrar

Desde a etapa 9 e o desenho das portas de entrada (26/08/2026), o painel tem
cortina e login.

1. **A capa** pede uma combinação de seis dígitos. No seu computador ela é
   `000000`, escrita aqui de propósito: aqui o dado é de mentira, e combinação
   que você tem de decorar na própria máquina só atrapalha. **No servidor ela é
   sorteada e mostrada uma vez só.**
2. **Depois da capa**, três portas: chave de acesso (o PIN do Windows ou a
   digital do celular), GitHub, e código do papel. No ambiente local há uma
   quarta, **Entrar · ambiente local**, que **não existe** no servidor — nem
   como caminho reconhecido.

Detalhes e a razão de cada escolha: `docs/operacao/formas-de-entrar.md`.

## Conectar outra máquina (etapa 11)

O painel recebe medição de outros computadores. No painel, botão **Máquinas** →
**Gerar o número**; na outra máquina, dentro da pasta do DERVS:

```
python -m agente.enviar --alvo http://localhost:4777 --codigo 123456
```

Se der certo, ela imprime `pareado com …` e, logo depois,
`enviado: N projetos`. Para deixar reportando sozinho, acrescente
`--intervalo 600`. O roteiro completo, com os erros comuns:
`docs/operacao/conectar-uma-maquina.md`.

O token daquela máquina fica em `~/.dervs/agente.json`, **fora do repositório**.

## Credenciais

**Deste computador, e não são segredo:** a combinação da capa é `000000` e a
porta "ambiente local" entra sem senha. Dado de teste não é segredo — é dado de
teste.

**Do servidor:** a combinação é sorteada lá dentro e mostrada uma vez; a chave
do cofre (`DERVS_COFRE`) nasce lá e nunca passa por chat, repositório ou commit.
