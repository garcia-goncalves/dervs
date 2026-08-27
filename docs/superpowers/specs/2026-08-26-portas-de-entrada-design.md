# As portas de entrada — desenho

Escrito em 26/08/2026, a pedido do dono, depois de a etapa 10 fechar.

## O pedido, nas palavras dele

> "Quero todas as opções possíveis. Quero que possamos escolher. Igual pra entrar
> na Binance (por exemplo)... no celular, obviamente que queremos que tenha tbm a
> opção mais fácil do mundo (digital/rosto)... mas para PC/Notebook, não tenho
> certeza se o Notebook do André tem digital... o meu é PC e não tem digital...
> nem tenho cam... Quero entrada/login com os números que estão atualmente e
> quero o que vc achar que faça sentido."

Restrição de hardware, declarada por ele: **o PC dele não tem leitor de digital
nem câmera.** O notebook do André é desconhecido.

## O mal-entendido que este documento desfaz primeiro

**Passkey não é digital.** Digital e rosto são só a *maneira de destrancar* a
chave — e não são a única. Uma passkey funciona igual em três situações:

| Aparelho | Como ele confirma que é você | Onde a chave mora |
|---|---|---|
| PC sem câmera e sem digital | **PIN do Windows Hello** (os mesmos 4-6 dígitos que destrancam o computador) | no chip TPM da placa-mãe |
| Notebook com digital ou câmera | digital ou rosto | no chip do notebook |
| Qualquer PC + celular | **QR code na tela, digital no celular** | no celular |

A terceira linha é a que resolve o caso dele hoje, sem comprar nada: o navegador
mostra um QR, ele aponta o celular, confirma com a digital, e entra no PC. A
chave privada **nunca sai do aparelho** — nem para o nosso servidor, nem para
lugar nenhum. É por isso que passkey é imune a site falso: não há o que copiar.

## O desenho: um menu de portas, e a cortina antes de todas

```
   [ cortina: 6 dígitos ]   <- continua, e continua sendo só anti-robô
              |
   +----------+-----------+------------------+
   |          |           |                  |
 passkey    GitHub    código do        senha + TOTP
 (padrão)             celular         (emergência, desligada)
```

**A cortina de seis dígitos fica.** Ele pediu para ficar, e ela nunca foi a
fechadura: existe para que um robô de varredura não descubra que há um sistema
aqui. O que muda nela está na seção "Os ajustes da cortina".

### Porta 1 — passkey (a recomendada, e a primeira da lista)

- **Cadastrar:** dentro do painel, "Adicionar uma forma de entrar". Cada pessoa
  cadastra **quantas quiser** — PC, notebook, celular, chave física USB. A lista
  mostra apelido, aparelho e data, com botão de remover.
- **Entrar:** um botão. O navegador cuida do resto.
- **Regra dura:** ninguém fica com **uma só**. Uma passkey só é um aparelho de
  distância do bloqueio total. A tela cobra a segunda.

### Porta 2 — GitHub

Já construída na etapa 9 e testada. Falta só o registro do aplicativo em
github.com — 5 minutos da mão do dono, roteiro em
`docs/operacao/registrar-app-github.md`. Aproveita o 2FA que a conta do GitHub
dele já tem.

### Porta 3 — código do celular (a saída de emergência que não trava ninguém)

Dez códigos de uso único, mostrados **uma vez** no cadastro, guardados só como
impressão digital (hash). Serve para o dia em que o celular quebrar e o PC
morrer no mesmo mês. Sem isto, "login sem senha" com duas pessoas é uma conta a
uma pane de distância de ficar trancada para sempre.

### Porta 4 — senha + TOTP

Já existe no banco (tabela `credencial`), **desligada**. Fica desligada. É a
porta de emergência da emergência, e só se ele mandar ligar.

## O que garante a segurança, item por item

| Ataque | O que barra |
|---|---|
| Site falso copiando o login | a passkey é amarrada ao endereço (`dervs.com.br`); num site falso o navegador **não oferece** a chave |
| Vazamento do nosso banco | não guardamos segredo nenhum: só a chave **pública**, que não abre nada |
| Repetir um pedido capturado | desafio de uso único, guardado na sessão, com prazo |
| Passkey clonada | contador de assinaturas: se voltar atrás, a credencial é derrubada |
| Chute na cortina | teto de 5 por 15 min, por origem, já em pé desde a etapa 9 |

## A decisão técnica que preciso declarar

Este projeto não usa biblioteca externa — é decisão registrada em `banco.py`.
Passkey exige conferir uma assinatura ECDSA na curva P-256, e o Python não traz
isso pronto. **Vou escrever a conferência à mão** (~150 linhas de aritmética
modular), provada contra os vetores de teste oficiais do NIST. É a alternativa a
adotar uma dependência; escolhi manter a promessa de zero dependência porque o
código é pequeno, fechado, e testável contra vetor conhecido — não é criptografia
inventada, é a aritmética publicada.

**O que isso NÃO é:** não vou escrever cifra nova. A parte secreta acontece
dentro do aparelho do usuário; do nosso lado só se **confere** uma assinatura
pública.

## Os ajustes da cortina

O que travou o dono em 26/08: chave certa, tela muda, nada aconteceu — era o
teto de tentativas. Já corrigido com a linha "recusado" na capa. Além disso:

- o selo da cortina passa de **10 minutos para 12 horas no ambiente local**;
  no servidor continua curto. Local não é onde a segurança mora.
- o teto continua 5 por 15 min **no servidor**; no local sobe para 20.

## Fora deste desenho, de propósito

- Cadastro público, convite, recuperação por e-mail — a porta nasce fechada e
  são só duas pessoas.
- SMS como fator. É o mais fraco dos fatores que existem e ele não pediu.
- Biometria "nossa" (foto do rosto conferida por nós). Nunca. A biometria fica
  dentro do aparelho, com o fabricante, e é assim que tem de ser.
