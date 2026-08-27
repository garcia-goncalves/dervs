# As formas de entrar no DERVS

Escrito em 26/08/2026, quando as portas de entrada foram construídas. O desenho
que originou tudo isto está em
[`../superpowers/specs/2026-08-26-portas-de-entrada-design.md`](../superpowers/specs/2026-08-26-portas-de-entrada-design.md).

Este documento é para **você**, dono, e para quem for mexer no código depois.
A primeira metade não tem jargão nenhum.

---

## Em uma frase

Você entra apertando um botão e digitando o **PIN do Windows** — o mesmo que
destranca o computador. Não há senha para lembrar, não há senha para vazar, e
não existe site falso capaz de copiar o que você digita.

## Por que isso funciona sem câmera e sem leitor de digital

Havia um mal-entendido a desfazer, e ele é o motivo de este documento existir:
**chave de acesso não é digital.** A digital e o rosto são só *a maneira de
destrancar* uma chave que já está guardada dentro do aparelho. Sem eles, o
aparelho pede outra coisa.

| Seu aparelho | O que ele pede | Onde a chave fica guardada |
|---|---|---|
| Seu PC (sem câmera, sem leitor) | o **PIN do Windows Hello** | no chip TPM da placa-mãe |
| Notebook com leitor ou câmera | a digital ou o rosto | no chip do notebook |
| Qualquer PC + seu celular | um **QR na tela**, e a digital no celular | no celular |

A terceira linha resolve o caso do seu PC **sem comprar nada**, caso ele não
tenha TPM: o navegador desenha um QR, você aponta o celular, confirma com a
digital, e entra no PC.

A parte secreta nunca sai do aparelho. O DERVS guarda só a **metade pública** da
chave, que serve para conferir uma assinatura e não abre nada. Se alguém copiar
o banco inteiro, não entra na sua conta com o que está lá dentro.

E é por isso que site falso não funciona aqui: a chave é amarrada ao endereço
`dervs.com.br`. Num endereço parecido, o navegador **não encontra chave nenhuma
para oferecer** — não há o que você possa digitar errado, porque não há nada a
digitar.

---

## O que você faz, na prática

### Cadastrar o primeiro aparelho

1. Entre no painel (hoje, pela porta do ambiente local).
2. Botão **Formas de entrar**, no alto à direita.
3. Escreva um apelido — "PC da sala", "celular" — e clique
   **Cadastrar este aparelho**.
4. O Windows abre uma janelinha pedindo o PIN. Digite.
5. Pronto: o aparelho aparece na lista.

**O que aparece se der certo:** o aparelho na lista, e a frase
*"cadastrado. Este aparelho já abre a conta."*
**Se der errado:** a mensagem mais comum é *"este aparelho já está cadastrado"* —
significa que ele já está na lista, e não há nada a fazer.

### Cadastrar o segundo — e por que a tela insiste nisso

Com **uma só** chave, você está a um aparelho de distância do bloqueio total:
PC formatado, PC roubado, PC morto, e ninguém abre a conta. Nunca mais.

Por isso a tela cobra a segunda em vermelho enquanto você tiver uma. Cadastre o
celular (o mesmo botão, no celular) ou gere os códigos de papel abaixo. Um dos
dois basta para o aviso sumir.

### Gerar os códigos de papel

Mesma tela, botão **Gerar dez códigos novos**. Eles aparecem **uma vez só** —
imprima, ou anote no papel e guarde longe do computador.

Cada código serve **uma vez**. Gerar uma lista nova **apaga a anterior**: o papel
velho deixa de valer no mesmo instante, e é por isso que o botão pergunta antes.

### Remover um aparelho

Botão **Remover** ao lado dele. Use quando vender, perder ou formatar o aparelho.
Ele deixa de abrir a conta imediatamente.

### Entrar

Na capa, digite os seis dígitos e escolha **Entrar com chave de acesso**. O
Windows pede o PIN. Acabou.

Se você clicar e nada acontecer, a tela diz o motivo em uma linha logo abaixo
dos botões. Se disser *"não deu"*, use o código do papel — a resposta do
servidor é propositalmente igual para todo tipo de recusa, e a explicação disso
está mais abaixo.

---

## Para quem for mexer no código

### As peças, e o que cada uma faz

| Arquivo | Responsabilidade |
|---|---|
| `p256.py` | conferir uma assinatura ECDSA na curva P-256. **Só conferir.** |
| `passkey.py` | abrir os embrulhos do navegador (CBOR, COSE, clientData) e decidir se a resposta vale |
| `banco.py` | as tabelas `chave_de_acesso` e `codigo_recuperacao` |
| `servir.py` | as sete rotas, o teto de tentativas e a sessão |
| `portas.html` | o menu da capa — injetado **depois** da cortina |
| `index.html` | o diálogo **Formas de entrar**, dentro do painel |

### A decisão que precisa de defesa: criptografia escrita à mão

Este projeto **não tem dependência externa** — decisão antiga, registrada em
`banco.py`. Conferir uma assinatura ECDSA é a única coisa que o Python não traz
pronta, e a alternativa era adotar uma biblioteca só por isso.

Escolhemos transcrever a aritmética publicada da curva (FIPS 186-4), cerca de
150 linhas, e prová-la contra os vetores da **RFC 6979 A.2.5** — os mesmos que o
NIST publica. Isso é defensável por três razões, e não por uma:

1. **Este código só confere.** Gerar chave, guardar chave e assinar acontecem
   inteiros dentro do aparelho de quem entra. Do lado do servidor só chega
   material público.
2. **Um erro aqui é barulhento.** Ele recusa quem devia entrar — aparece na
   hora — em vez de vazar segredo em silêncio.
3. **O teste vem de fora.** Código de criptografia testado só com dado que ele
   mesmo produziu não está testado: prova que concorda consigo, não que está
   certo.

Há ainda uma trava contra o erro mais provável do arquivo, que é digitar um
número errado ao transcrever o vetor: `test_a_chave_publica_nasce_da_privada`
confere o par de chaves por um caminho independente da assinatura. Se ele passa,
X e Y estão certos, e uma falha na assinatura acusa `r`/`s` ou a conta — nunca
"algum dos seis números".

### O que NÃO é conferido, de propósito

O **atestado do fabricante** (`attStmt`). Ele serve para uma empresa exigir "só
chave da marca X". Aqui são duas pessoas e qualquer aparelho serve, então
aceitamos `fmt: none`. Isto está escrito para que ninguém leia a ausência como
esquecimento.

### O anti-oráculo, e o preço que ele cobra

As três rotas de entrar devolvem **a mesma resposta para todo tipo de fracasso**:
credencial que não existe, assinatura errada, desafio vencido, conta desativada —
tudo é o mesmo `401` com o mesmo texto. Motivo diferente por causa diferente
transforma a tela de login numa lista de quem existe.

**O preço:** a orientação de web moderna recomenda devolver `404` quando a
credencial não é encontrada, para que o navegador possa limpar sozinho uma
passkey que o servidor já apagou (`signalUnknownCredential`). Trocamos essa
limpeza automática pelo silêncio. Com duas pessoas, remover a passkey órfã à mão
no gerenciador do navegador é barato; entregar a lista de quem existe, não.

### Onde estão as defesas, item por item

| Ataque | O que barra, e onde |
|---|---|
| Site falso copiando o login | a chave é amarrada ao endereço; e `passkey._client_data` confere a origem de novo, sem depender do navegador |
| Vazamento do banco | não há segredo nas tabelas: chave pública e impressão digital |
| Repetir uma resposta capturada | desafio de uso único em `passkey.Desafios` — `resgatar` **apaga** |
| Passkey copiada | contador de assinaturas, decidido pelo **próprio UPDATE** em `banco.usar_chave_de_acesso` |
| Chute no código de papel | 20 letras sorteadas (~99 bits) + teto por origem |
| Chute derrubando outra porta | cada porta tem a própria fila (`cortina.registrar_tentativa(balcao=…)`) |
| Pedido forjado de outro site | `Origin` em toda rota de escrita, e `X-Token` da sessão nas do painel |
| Apagar a chave do vizinho | o dono vai na cláusula do `UPDATE`, não só na checagem da rota |

### A pegadinha do nome da rota

A rota do código de papel chama-se `/entrar/codigo`, e **não**
`/entrar/recuperacao`. Motivo: "recupera**cao**" casa com a lista de bloqueio de
`test_rotas.py` — a lista que impede uma rota deste servidor de executar comando
na máquina do dono. O vigia reprovou o nome, e o nome mudou. Afrouxar a lista
para caber um nome bonito seria afrouxar a única coisa que impede a etapa 7 de
voltar atrás.

---

## O que ainda depende da sua mão

Registrar o OAuth App em github.com, cinco minutos, roteiro em
[`registrar-app-github.md`](registrar-app-github.md). Sem isso o botão
**Entrar com GitHub** não aparece — de propósito: botão que leva a erro é pior
que botão que não existe.
