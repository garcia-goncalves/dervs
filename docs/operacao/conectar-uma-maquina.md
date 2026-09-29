# Conectar uma máquina ao DERVS

*Escrito em 27/08/2026, na etapa 11 da fatia 1. Reescrito em 29/08/2026,
na etapa A4 de “Conectar em três portas”: o conectador entrou, e a linha
de comando deixou de exigir que o terminal estivesse na pasta do DERVS.*

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

## Dois caminhos, e eles valem o mesmo

Desde 29/08/2026 a tela **Conectar projeto** oferece dois jeitos de conectar
uma máquina, lado a lado. Nenhum dos dois é o plano B do outro:

- **O conectador** — um arquivo que você baixa e abre com dois cliques. Ele
  abre a janela do sistema para você escolher a pasta dos projetos, conecta
  sozinho e deixa a máquina reportando a cada login. **Não pede terminal
  nenhum**, e é o caminho recomendado para o seu computador de trabalho.
- **A linha de comando** — uma linha para colar no terminal. É o caminho para
  um servidor sem tela, e para quem prefere terminal.

O conectador é um arquivo `.py`, e isso é escolha: a tela azul de proteção do
Windows (o SmartScreen) vigia por extensão, e `.py` não está na lista dela.
O que **pode** aparecer é o aviso de "arquivo baixado da internet", e o Windows
vai abri-lo com o programa que estiver associado a `.py` na sua máquina.

## O conectador, passo a passo

1. No painel, vá em **Conectar projeto** e clique em **Baixar o conectador**.
   O arquivo já vem com o seu número de seis dígitos dentro — ele vale dez
   minutos.
2. Abra o arquivo baixado (dois cliques).
3. Escolha a pasta onde ficam os seus projetos na janela que abrir.
4. Pronto. Ele mostra na tela o que fez, e a máquina aparece no painel.

**Se a janela de escolher pasta não abrir**, ele pergunta o caminho pelo
teclado e segue — alguns Pythons do Windows vêm sem a peça que desenha janelas,
e ela não é instalável. Digite o caminho e aperte Enter.

**Se você fechar sem escolher pasta**, nada acontece na sua máquina: nenhum
token gravado, nenhuma tarefa criada. Ele diz isso e sai.

**Se ele disser que não achou o DERVS nesta máquina**, o pareamento valeu, mas
o relato contínuo não foi agendado — ele precisa dos arquivos do DERVS ali.
Clone o repositório e rode o conectador de novo.

**Fora do Windows** ele conecta e grava a pasta, mas **não agenda nada** — o
agendador que ele usa é o do Windows. Ele diz isso e mostra a linha para você
deixar rodando.

## A linha de comando, passo a passo

1. No painel, clique em **Computadores** e depois em **Gerar o número**.
   Aparece um número de seis dígitos e a linha pronta para copiar.
2. Na outra máquina, abra o terminal **em qualquer pasta** e cole a linha,
   trocando `<CAMINHO DO DERVS>` pela pasta onde o DERVS está:

   ```
   python "<CAMINHO DO DERVS>\agente\enviar.py" --alvo https://SEU-DERVS --codigo 123456
   ```

   **`<CAMINHO DO DERVS>` é o único pedaço que você troca.** O painel não tem
   como saber onde o repositório está na sua máquina, e inventar um caminho
   seria ele mentindo. Quem não quer trocar nada usa o conectador.

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

O conectador já faz isso: ele registra uma tarefa que roda a cada login do
Windows. Sem permissão de administrador o Windows nega essa tarefa; então ele
cai no plano B, uma tarefa que acorda de 10 em 10 minutos e reporta uma vez.
Se você conectou pela linha de comando, ou quer outro intervalo:

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

Elas aparecem separadas de propósito. "Cortado" é limite seu; "recusado" é
formato errado, e provavelmente um defeito a investigar.

## Onde mora o token, e por que ali

O número de seis dígitos vale uma vez e vence em dez minutos. Trocado, ele vira
um **token** que não vence — e é ele que autoriza os envios seguintes.

O token fica em `~/.dervs/agente.json` (no Windows,
`C:\Users\<você>\.dervs\agente.json`), com permissão de leitura só para a sua
conta. **Fora da pasta do projeto, de propósito:** token dentro do repositório é
token commitado no dia em que alguém rodar `git add -A` com pressa.

Ele também **nunca entra na linha de comando**. Argumento de processo aparece na
lista de processos da máquina inteira. Por isso não existe `--token`: o código de
pareamento entra por ali porque é descartável; o token, não.

Para apontar o arquivo para outro lugar: `DERVS_AGENTE_ARQUIVO=/caminho/x.json`.

## Desconectar uma máquina

No painel, **Computadores → Remover**. O token daquela máquina deixa de valer no
mesmo instante, e ela só volta com um número novo. Os projetos que ela reportava
continuam no painel com o último dado medido — some a fonte, não o histórico.

## O que segura seis dígitos

Um milhão de possibilidades é pouco se o chute for de graça. São três travas:

1. **dez minutos** de validade;
2. **uso único** — código gasto não pareia uma segunda máquina;
3. **cinco tentativas por origem** a cada quinze minutos, contadas na rota
   (no seu computador são vinte — ali o dado é de mentira e apertar só atrapalha
   quem trabalha).

A terceira tem uma sutileza que já custou caro aqui: a conta é **por origem**, e
não um contador global. Contador global deixaria um estranho trancar o
pareamento de todo mundo com cinco chutes. E a fila é própria: gastar o teto
tentando parear **não** tranca a sua entrada pela capa.

## O sinal de vida é o dado

Não existe rota de "estou vivo" separada, e isso é decisão, não esquecimento.
Com um sinal próprio, uma máquina com a coleta travada continuaria dizendo que
está viva — e o painel ficaria verde exatamente quando parou de olhar. Aqui o
carimbo de `visto_em` só anda quando medição de verdade chega.

Ver também: [`formas-de-entrar.md`](formas-de-entrar.md), sobre as portas de
entrada de **pessoas** (que é outra coisa: máquina tem token, pessoa tem sessão).
