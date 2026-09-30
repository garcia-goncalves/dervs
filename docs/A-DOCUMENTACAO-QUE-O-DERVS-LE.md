# A documentação que o DERVS lê

Este é o **único lugar** onde o formato está escrito. O leitor (`documentos.py`)
segue estas regras ao pé da letra; se este texto e o leitor divergirem, o leitor
é o que vale e este texto está errado: conserte-o.

**Para que serve.** Toda coisa nova nasce documentada: uma lista de critérios
("o que precisa estar verdadeiro para eu dizer que está pronto"), escrita e
aprovada antes do código. O DERVS lê essa lista em cada projeto e mostra, na tela
do projeto, **quanto dela já está cumprido** e o que falta. Ele só mede; não
estima prazo nem esforço.

## Onde o arquivo mora

`docs/esteira/<nome>/briefing.md`, dentro do repositório do projeto.

O `<nome>` usa só letras minúsculas sem acento, números e hífen, começa por letra
ou número e tem no máximo 80 caracteres (exemplo: `progresso-por-documentacao`).
Pasta com outro nome de formato é ignorada.

## Como se escreve um critério

Dentro do arquivo, uma seção que começa com esta linha, **exatamente**:

```
## criterio_de_aceitacao
```

Ela vai até a próxima linha que começa com `## `. Cada critério é **uma linha**,
sem recuo, neste formato:

```
- [ ] O botão Salvar grava o cadastro e mostra "Salvo".
- [x] O cadastro recusa e-mail sem arroba.
```

- `- [ ]` (com um espaço dentro dos colchetes) quer dizer **ainda não feito**.
- `- [x]` ou `- [X]` quer dizer **marcado como feito** por quem escreveu.
- Depois do colchete vem **um espaço** e o texto do critério, em uma linha só.

**Item numerado não conta.** Uma linha `1. texto` dentro da seção é um erro do
leitor ("critério numerado não conta: use - [ ]") e fica de fora da conta.

## A prova (opcional)

Logo **na linha de baixo** do critério, você pode dizer como provar que ele está
cumprido:

```
- [ ] O cadastro recusa e-mail sem arroba.
Prova: python test_cadastro.py
```

A linha é `Prova:` (pode ter espaços antes) seguida do comando. Regras:

- Tem de ser a linha **imediatamente** abaixo do critério. Uma linha `Prova:`
  solta, sem critério logo acima, é um erro do leitor.
- Sem `Prova:`, o critério só pode ficar "marcado no documento, sem prova".

### Que comandos são aceitos (lista fechada)

Só estes três formatos:

1. `python test_<nome>.py`, onde `<nome>` tem só letras, números e `_`
   (exemplo: `python test_cadastro.py`).
2. `python -m pytest <arquivo.py>`, com caminho **relativo** ao projeto, sem `..`
   e sem caminho absoluto (exemplo: `python -m pytest tests/test_cadastro.py`).
3. `npm test`.

Qualquer comando com estes caracteres é recusado na hora: `;` `&` `|` `$` crase
`<` `>` `(` `)` aspas (simples ou duplas) ou quebra de linha. O texto da prova é
**dado vindo de fora**: o DERVS nunca o entrega a um terminal. Nesta entrega
**nenhuma prova roda ainda** (ver "O que a tela mostra").

## Quando o documento está aprovado

Uma linha, **fora** da seção de critérios (por exemplo logo abaixo do título):

```
Aprovado em: 2026-09-30
```

O formato é `Aprovado em:` e a data `AAAA-MM-DD`. Enquanto ela não existir, o
botão "Desenvolver isto" não aparece para os critérios daquele documento. A linha
é versionada no git junto com o documento, e quem tem escrita no repositório pode
escrevê-la: a trava de verdade continua sendo o "Pode fazer" do dono na hora de
rodar.

## Limites (o que passa do teto é cortado e marcado)

| O quê | Teto |
|---|---|
| documentos lidos por projeto | 30 |
| critérios por documento | 40 |
| texto de um critério | 300 caracteres |
| texto de uma prova | 200 caracteres |
| tamanho do arquivo | 256 KiB |
| tamanho do que sobe ao painel, por projeto | 24 KiB |

Passou do teto: o leitor corta, marca o documento como **cortado** e segue. Nunca
falha em silêncio por causa do tamanho.

O leitor também **para de abrir arquivo** ao chegar ao 31º documento, e abre no
máximo 120 briefings por leitura (com ou sem critério): um repositório com milhares
de pastas não faz o agente ler milhares de arquivos.

### Só lê o que está dentro do repositório

`docs` e `docs/esteira` (e cada pasta e arquivo dentro) são resolvidos antes de
lidos, e precisam continuar **dentro do repositório**. Um link simbólico (ou
*junction* do Windows) que aponte para fora é **recusado**: o projeto aparece com um
documento `docs/esteira` e o erro "aponta para fora do repositório (link): não foi
lida", em vez de "sem documentação" calado.

## O que a tela mostra

Na tela do projeto, a seção **Quanto já foi desenvolvido** tem quatro faces. O
número grande e a barra só existem na primeira:

| Face | Quando | O que escreve |
|---|---|---|
| **Medido** | há critérios e pelo menos uma prova rodou | o percentual (comprovados ÷ total, arredondado para baixo; 100% só se todos estiverem comprovados), quantos faltam, quantos têm prova falhando e quantos ainda não foram verificados |
| **Não verificado** | há critérios, mas nenhuma prova rodou | "Nenhuma prova rodou ainda", o total de critérios e quantos estão "marcados no documento, sem prova". **Sem percentual.** |
| **Sem documentação** | o projeto não tem nenhum critério em `docs/esteira` | "Sem documentação". **Nunca 0% e nunca 100%**: sem critério não há o que medir. |
| **Sem dados** | o agente do computador não enviou a documentação (versão antiga, ou não mediu) | "Não consegui medir" |

Um critério marcado com `[x]` **não conta** como cumprido: só conta quando a
prova dele rodou e passou. Por isso, nesta entrega, onde nenhuma prova roda ainda,
todo projeto com critérios aparece como "Não verificado". Toda frase com número
diz **quando foi medida**. O progresso **não muda a cor do selo de saúde**: são
perguntas diferentes.

## Um documento inteiro, como exemplo

```
# Briefing — cadastro de clientes

Aprovado em: 2026-09-30

## pedido_original

"Quero cadastrar clientes."

## criterio_de_aceitacao

- [ ] O cadastro grava nome e e-mail.
Prova: python test_cadastro.py
- [ ] O cadastro recusa e-mail sem arroba.
Prova: python -m pytest tests/test_cadastro.py
- [ ] A tela de cadastro cabe em 360 px sem rolagem horizontal.

## fora_de_escopo

- Importar clientes de planilha.
```

Lido assim: um documento aprovado em 30/09/2026, com três critérios, dois com
prova permitida e um sem prova. Como nenhuma prova rodou, a tela mostra
"Nenhuma prova rodou ainda" e "3 critérios documentados".

### Erros comuns (e o que o leitor diz)

```
## criterio_de_aceitacao

1. O cadastro grava o nome.                  <- numerado: não conta
- [ ] O cadastro grava o e-mail.
Prova: python test_cadastro.py; rm -rf /     <- tem ";": prova recusada, nunca roda
Prova: python test_solta.py                  <- prova sem critério logo acima: erro
```

Cada erro aparece na tela, no documento onde está, e o critério com erro fica
**fora da conta** (nunca dentro como se estivesse certo).

## Desenvolver a partir da documentação

Com documento aprovado, o critério ganha o botão **Desenvolver isto**. Ele cria uma
tarefa `desenvolver` que **sempre espera o seu "Pode fazer"** em Consertar e nunca
anda sozinha. O servidor recusa quando:

- o documento ainda não tem `Aprovado em:`;
- o projeto é bloqueado (do André, da TineHost ou com dado de paciente). O nome é
  comparado em minúsculas, com `_`, espaço e `.` tratados como `-`, e vale também
  para o que **começa** com um nome bloqueado seguido de `-` (`ajudei-saude-web`,
  `aninha-site-v2`, `Ajudei_Saude`); qualquer nome com `nexa` também. Nomes
  parecidos que não são o mesmo (`sophiana`, `ccvpx`) não são bloqueados;
- o critério trata de segurança, senha, pagamento ou dado de paciente;
- o critério já está marcado com `[x]`.

Em **Consertar**, a linha da tarefa mostra **"O que foi pedido:"** (o texto do
critério, cortado em 300 caracteres) ao lado do botão **Pode fazer**: você lê o que
vai ser feito antes de aprovar. O texto vem de um documento de outro repositório e
aparece sempre como texto, nunca como HTML. Por dentro, o pedido que desce ao agente
vai dentro de um bloco de dados, e qualquer tentativa de abrir ou fechar esse bloco
(maiúsculas, espaços dentro da etiqueta) é trocada por "[etiqueta removida]".

O resultado de um desenvolvimento é um ramo para você revisar; o DERVS não publica
nada sozinho.

## Migrar um briefing antigo

Briefings escritos antes deste formato têm uma lista numerada. Eles aparecem como
**Sem documentação** até alguém trocar `1. texto` por `- [ ] texto` e, se quiser,
acrescentar as linhas `Prova:` e `Aprovado em:`.
