# Conectar uma máquina ao DERVS

*Escrito em 27/08/2026, na etapa 11 da fatia 1. Reescrito em 29/08/2026,
na etapa A4 de “Conectar em três portas”. Reescrito em 09/10/2026, na entrega A
do “Conectar simples”: o caminho principal passou a ser o arquivo `.cmd` que
autoriza pelo navegador, sem número para digitar e sem o DERVS clonado.*

O DERVS mostra o estado dos seus projetos. Até aqui ele só sabia dos projetos da
máquina **onde ele mesmo roda**. O agente muda isso: qualquer computador seu pode
medir a si mesmo e mandar o resultado para o painel.

## O que o agente faz, em uma frase

Ele olha os repositórios daquela máquina (git, Docker, portas em uso, nomes de
variável em `.env`), monta um relatório e **manda** para o endereço do DERVS.

## O que ele **não** faz — e isso é o desenho, não uma falta

- **Não escuta porta nenhuma.** Só sai conexão dali. Um agente que aceitasse
  conexão seria uma porta nova na sua máquina de casa, sem ninguém olhando.
- **Não recebe comando do painel.** O sentido é sempre da máquina para o painel.
  Foi exatamente isso que a etapa 7 amputou do servidor, e não volta.
- **Não manda o valor de segredo nenhum.** Do `.env` sai só o *nome* da
  variável — a leitura para no sinal de igual.
- **Não executa tarefa nenhuma quando conectado pelo arquivo `.cmd`.** O
  programa que o painel entrega **só mede**: ele não leva o braço executor.

## Dois caminhos, e eles valem o mesmo

A tela **Conectar projeto** oferece dois jeitos de conectar uma máquina, lado a
lado. Nenhum dos dois é o plano B do outro:

- **O arquivo `conectar-dervs.cmd`** — você baixa e abre com dois cliques. Ele
  instala o Python oficial **dentro da sua pasta de usuário** (sem
  administrador), abre a janela do Windows para você escolher a pasta dos
  projetos, abre o navegador para você clicar em **Autorizar** e deixa a máquina
  reportando a cada login. **Não pede terminal nenhum**, e é o caminho
  recomendado para o seu computador de trabalho. Funciona **sem o DERVS clonado**
  na máquina: o programa vem do painel.
- **A linha de comando** — uma linha para colar no terminal. É o caminho para
  um servidor sem tela, para quem prefere terminal e para quem quer que a máquina
  também **execute** tarefas. Esta precisa do DERVS clonado na máquina.

## O arquivo `.cmd`, passo a passo

1. No painel, vá em **Conectar projeto** e clique para baixar o arquivo.
2. Abra o arquivo baixado (dois cliques). O Windows pode mostrar um aviso de
   “arquivo baixado da internet” ou de editor desconhecido: o arquivo é texto
   puro, e você pode abri-lo no Bloco de Notas antes para conferir o que ele faz.
3. Na primeira vez ele baixa o Python oficial (cerca de 12 MB, de
   `python.org`), **confere a impressão digital SHA-256** e só então o usa. Se a
   conferência não bater, apaga o que baixou e para: nada é instalado.
4. Escolha a pasta onde ficam os seus projetos na janela que abrir.
5. O navegador abre no painel com um código curto (por exemplo `K7M4-2QXP`).
   **Confira que o nome do computador e o código na tela são os mesmos que
   estão na janela preta** e clique em **Autorizar**. Se você não reconhece o
   pedido, feche a janela e não clique: quem consegue fazer você clicar num
   pedido dele liga o computador dele à sua conta.
6. Pronto. Ele baixa o programa do painel, agenda a tarefa, manda a primeira
   medição e diz “Pronto. Esta janela fecha em 10 segundos.”

O pedido vale 10 minutos. Passou disso, rode o arquivo de novo.

**Onde as coisas ficam:** o Python em `%LOCALAPPDATA%\DERVS\python`, o programa
do painel em `%LOCALAPPDATA%\DERVS\programa`, o token e as pastas em
`C:\Users\<você>\.dervs\agente.json`. Para desinstalar: apague a pasta
`%LOCALAPPDATA%\DERVS`, remova a tarefa **DERVS - reportar** no Agendador de
Tarefas e remova o computador no painel.

**Rodar o arquivo de novo** (para acrescentar outra pasta, por exemplo) **não
pede autorização outra vez**: ele reaproveita o token que já está no
`agente.json`. Se o painel recusar esse token (computador removido), ele pede
autorização de novo. Se o computador **executa tarefas** (foi ligado pela linha
de comando com o braço executor), o arquivo **só acrescenta a pasta** e não troca
a tarefa agendada, para não desligar o braço.

**Se a janela de escolher pasta não abrir** (algumas máquinas de empresa
bloqueiam o PowerShell), ele pergunta o caminho pelo teclado e segue. Digite o
caminho e aperte Enter.

**Se você fechar sem escolher pasta**, nada acontece na sua máquina: nenhum
token gravado, nenhuma tarefa criada. Ele diz isso e sai.

**Se o programa do painel vier fora do formato esperado**, ele recusa o pacote
inteiro, não grava nada e sai dizendo “Nao consegui receber o programa do
painel” (código de saída 5).

**Fora do Windows** use a linha de comando: o `.cmd` é do Windows.

## A linha de comando, passo a passo

1. No painel, clique em **Conectar**, abra **Prefiro colar um comando** e
   clique em **Gerar o número**.
   Aparece um número de seis dígitos e a linha pronta para copiar.
2. Na outra máquina, abra o terminal **em qualquer pasta** e cole a linha,
   trocando `<CAMINHO DO DERVS>` pela pasta onde o DERVS está:

   ```
   python "<CAMINHO DO DERVS>\agente\enviar.py" --alvo https://SEU-DERVS --codigo 123456
   ```

   **`<CAMINHO DO DERVS>` é o único pedaço que você troca.** O painel não tem
   como saber onde o repositório está na sua máquina, e inventar um caminho
   seria ele mentindo. Quem não quer trocar nada usa o arquivo `.cmd`.

   **Não importa mais de que pasta você roda.** Até 29/08/2026 a linha só
   funcionava de dentro da pasta do DERVS, e de qualquer outra o Python
   respondia `No module named` — em inglês, antes de o programa começar, o que
   fazia parecer que o número de seis dígitos tinha quebrado. A linha agora
   carrega o caminho do arquivo, e o programa se acha sozinho.

   **Se der certo**, ela imprime duas linhas:

   ```
   pareado com https://SEU-DERVS. O token ficou em C:\Users\voce\.dervs\agente.json
   enviado: 17 projetos -> https://SEU-DERVS
   ```

   **Se der errado**, o motivo vem escrito em português. Os três comuns:

   | O que aparece | O que houve | O que fazer |
   |---|---|---|
   | `o codigo de seis digitos nao serve` | digitado errado, passou dos dez minutos, já foi usado — **ou o número saiu do painel de outro DERVS** | gerar outro **no painel do mesmo endereço que está no `--alvo`** |
   | `o alvo recusou por excesso de tentativas` | cinco erros seguidos daquele endereço | esperar quinze minutos |
   | `nao consegui falar com …` | endereço errado, ou sem internet | conferir o endereço |
   | `recusei falar com … por http://` | o endereço veio sem o **s** de `https` | trocar para `https://` |
   | `relatorios demais` | mais de 60 envios em quinze minutos daquela máquina | usar `--intervalo` de 60 s ou mais |

   **Dois DERVS, dois bancos.** Se você tem o do servidor e o da sua própria
   máquina, cada um guarda os códigos dele. Um número gerado em
   `https://dervs.com.br` **não** vale em `http://localhost:4777`, e o
   contrário também não — o segundo responde que o número não serve, e está
   certo. Confira sempre se o endereço do `--alvo` é o mesmo que você abriu no
   navegador para gerar o número.

   **O `https://` não é frescura.** O token da máquina viaja num cabeçalho do
   pedido. Por `http://` ele vai legível para qualquer um que esteja no caminho
   — o wi-fi do café, o provedor, o roteador da empresa. O agente recusa em vez
   de deixar acontecer. A única exceção é o DERVS da sua própria máquina
   (`http://localhost:4777`), onde não há caminho nenhum entre os dois.

3. De volta ao painel, a máquina aparece na lista com o carimbo de quando
   reportou pela última vez.

## Deixar reportando sozinho

O arquivo `.cmd` já faz isso: ele registra uma tarefa que roda a cada login do
Windows (com `pythonw.exe`, sem abrir janela). Sem permissão de administrador o
Windows nega essa tarefa; então ele cai no plano B, uma tarefa que acorda de 10
em 10 minutos e reporta uma vez. Se você conectou pela linha de comando, ou quer
outro intervalo:

```
python "<CAMINHO DO DERVS>\agente\enviar.py" --alvo https://SEU-DERVS --intervalo 600
```

Ele mede e manda de dez em dez minutos, e não morre se a internet cair — volta
sozinho quando ela voltar.

**Não desça de 15 segundos.** O servidor aceita 60 envios por máquina a cada
quinze minutos e responde `relatorios demais` a partir daí. O teto existe para
um token roubado não encher o disco do servidor num laço; dez minutos, ou um
minuto, passam com folga de sobra.

## O que o alvo pode recusar do seu relatório

Duas contagens voltam no fim de cada envio, e as duas viram aviso na tela:

| Aviso | O que quer dizer |
|---|---|
| `o alvo cortou N projeto(s)` | você tem mais de 300 projetos, ou mais de mil na conta — o excedente não entrou |
| `o alvo RECUSOU N entrada(s)` | nome vazio, nome reservado (`_infra`, `_quota`) ou formato errado |

Elas aparecem separadas de propósito. “Cortado” é limite seu; “recusado” é
formato errado, e provavelmente um defeito a investigar.

## Onde mora o token, e por que ali

Pelo arquivo `.cmd`, o computador recebe o token direto do painel, no momento em
que você clica em **Autorizar** (o número de seis dígitos só existe na linha de
comando). Pela linha de comando, o número vale uma vez e vence em dez minutos, e
trocado vira um **token** que não vence — é ele que autoriza os envios seguintes.

O token fica em `~/.dervs/agente.json` (no Windows,
`C:\Users\<você>\.dervs\agente.json`), com permissão de leitura só para a sua
conta. **Fora da pasta do projeto, de propósito:** token dentro do repositório é
token commitado no dia em que alguém rodar `git add -A` com pressa.

Ele também **nunca entra na linha de comando**. Argumento de processo aparece na
lista de processos da máquina inteira. Por isso não existe `--token`: o código de
pareamento entra por ali porque é descartável; o token, não. O arquivo `.cmd`
nunca imprime o token, nem o pedido que o originou.

Para apontar o arquivo para outro lugar: `DERVS_AGENTE_ARQUIVO=/caminho/x.json`.
Para mudar onde o programa do painel é gravado: `DERVS_CASA=/caminho`.

## Desconectar uma máquina

No painel, **Computadores → Remover**. O token daquela máquina deixa de valer no
mesmo instante, e ela só volta com uma nova autorização. Os projetos que ela
reportava continuam no painel com o último dado medido — some a fonte, não o
histórico.

## O que segura o código curto e o número de seis dígitos

Um espaço pequeno de possibilidades é pouco se o chute for de graça. São três
travas, iguais nos dois caminhos:

1. **dez minutos** de validade;
2. **uso único** — código gasto não liga uma segunda máquina;
3. **teto de tentativas por origem** a cada quinze minutos, contado na rota
   (no seu computador o teto é maior — ali o dado é de mentira e apertar só
   atrapalha quem trabalha).

A terceira tem uma sutileza que já custou caro aqui: a conta é **por origem**, e
não um contador global. Contador global deixaria um estranho trancar a conexão
de todo mundo com poucos chutes. E a fila é própria: gastar o teto tentando
conectar **não** tranca a sua entrada pela capa.

## O sinal de vida é o dado

Não existe rota de “estou vivo” separada, e isso é decisão, não esquecimento.
Com um sinal próprio, uma máquina com a coleta travada continuaria dizendo que
está viva — e o painel ficaria verde exatamente quando parou de olhar. Aqui o
carimbo de `visto_em` só anda quando medição de verdade chega.

Ver também: [`formas-de-entrar.md`](formas-de-entrar.md), sobre as portas de
entrada de **pessoas** (que é outra coisa: máquina tem token, pessoa tem sessão).
