# O token do coletor — o roteiro completo

Isto exige a sua mão: só você pode criar coisas na sua organização do GitHub.
São **cinco minutos, uma vez**. Você não digita nenhum segredo numa conversa de
chat, e não precisa entender nada de terminal.

---

## O problema que isto resolve

Na sua máquina, o painel lê o GitHub usando o `gh` — um programa que **você já
logou aqui**. Funciona, e vai continuar funcionando: nada do que está escrito
abaixo muda o seu computador.

No servidor esse programa não existe, e não pode existir. Ele guardaria a sua
identidade pessoal dentro de uma máquina que fica sozinha na internet: qualquer
falha lá viraria acesso a **tudo** que a sua conta do GitHub alcança, para
sempre, sem prazo de validade.

O que o servidor precisa é de uma identidade **própria**, com permissão só de
leitura, só nos repositórios da organização, e revogável num clique.

---

## Duas formas de fazer. A recomendada é a primeira

| | **GitHub App** (recomendado) | Token pessoal (PAT) |
|---|---|---|
| De quem é a identidade | do sistema | **sua** |
| Vence? | não | sim, em até 1 ano |
| Se você sair da organização | continua funcionando | **para de funcionar** |
| Revogar | desinstalar o app | apagar o token |
| Trabalho para criar | ~5 min | ~2 min |
| Cota de leitura | 5.000/hora por instalação | 5.000/hora, **compartilhada com você** |

A última linha é a que decide: um token pessoal faz o servidor gastar a **sua**
cota. O painel já tem histórico de cota estourada nesta conta.

O caminho do token pessoal existe aqui como **saída de emergência** — serve para
o servidor rodar hoje à noite se o app der trabalho. Está no fim do documento.

---

## Caminho recomendado: o GitHub App

### 1. Criar

Abra <https://github.com/organizations/garcia-goncalves/settings/apps> e clique
em **New GitHub App**.

Se essa página der erro de permissão, use
<https://github.com/settings/apps> → **New GitHub App** e escolha a organização
no campo de dono.

### 2. Preencher

| Campo | O que digitar |
|---|---|
| **GitHub App name** | `DERVS coletor` |
| **Homepage URL** | `https://dervs.com.br` |
| **Webhook** → *Active* | **desmarque** |

Desmarcar o webhook importa: o painel **pergunta** ao GitHub de vinte em vinte
minutos, ele não recebe avisos. Um endereço de webhook ligado seria uma porta
aberta na internet que ninguém atende.

### 3. As permissões — só leitura, e só estas cinco

Em **Repository permissions**, deixe tudo em `No access` menos:

| Permissão | Nível | Para que serve no painel |
|---|---|---|
| **Metadata** | Read-only | (obrigatória, o GitHub liga sozinha) |
| **Contents** | Read-only | comparar o que foi publicado com a ponta do ramo |
| **Issues** | Read-only | a coluna **A fazer** |
| **Pull requests** | Read-only | o alerta de pedido de alteração parado |
| **Actions** | Read-only | a CI vermelha, e a data do último deploy |
| **Dependabot alerts** | Read-only | os alertas de segurança |

**Não** conceda nada em `Write`. O coletor só lê — e um coletor com permissão de
escrita é uma ferramenta de estrago esperando por um defeito.

Em **Organization permissions** não marque nada.

Em **Where can this GitHub App be installed?** escolha **Only on this account**.

### 4. Criar e guardar os dois valores

Clique em **Create GitHub App**. A tela seguinte mostra:

- **App ID** — um número. É público, pode ser copiado sem preocupação.
- Role a página até **Private keys** → **Generate a private key**. O navegador
  baixa um arquivo `.pem`. **É segredo, e o GitHub não mostra de novo.**

### 5. Instalar na organização

Menu da esquerda → **Install App** → **Install** ao lado de
`garcia-goncalves` → **All repositories**.

Depois de instalar, a barra de endereço termina em um número, assim:

```
https://github.com/settings/installations/12345678
```

Esse `12345678` é o **Installation ID**. Anote — é o terceiro valor.

### 6. O que me mandar

Só isto, e **nunca pelo chat**:

- **App ID** e **Installation ID** — não são segredo, pode dizer aqui.
- O arquivo `.pem` — **não cole o conteúdo aqui**. Ele vai direto para dois
  lugares, por você:
  - **GitHub → o repositório `dervs` → Settings → Secrets and variables →
    Actions → New repository secret**, com o nome `DERVS_GITHUB_APP_KEY`;
  - e para dentro do servidor, quando ele existir.

Se ele vazar algum dia: volte em **Private keys**, apague a chave antiga e gere
outra. A antiga morre na hora. É por isso que o desenho prefere um segredo
trocável a um segredo escondido.

---

## O que ainda falta do meu lado

**O código de hoje aceita um token pronto**, na variável de ambiente
`DERVS_GITHUB_TOKEN`, e já foi provado contra o GitHub de verdade (as issues e a
medida de publicação atrasada vêm iguais pelos dois caminhos).

**O que ainda não existe** é a troca automática: um GitHub App não entrega um
token direto — ele entrega uma chave com a qual o sistema pede, de hora em hora,
um token novo. Essa peça (assinar o pedido com a chave `.pem` e renovar antes de
vencer) é a próxima tarefa, e **só posso terminá-la depois que os três valores
acima existirem** — sem eles não há contra o que provar que funciona, e neste
projeto código sem prova não é código pronto.

Enquanto isso, o painel na sua máquina segue funcionando pelo `gh`, exatamente
como antes.

---

## Saída de emergência: o token pessoal

Use só se precisar do servidor rodando antes de o app estar pronto.

1. <https://github.com/settings/personal-access-tokens/new>
2. **Token name**: `dervs-coletor`. **Resource owner**: `garcia-goncalves`.
3. **Expiration**: 90 dias. Prazo curto é de propósito — segredo que não vence
   é segredo que ninguém troca.
4. **Repository access** → **All repositories**.
5. **Permissions** → as mesmas cinco da tabela acima, todas `Read-only`.
6. **Generate token**. O GitHub mostra o valor **uma vez só**.

Ele vai para o ambiente do servidor como `DERVS_GITHUB_TOKEN` — e vale a regra
da casa, sem exceção: não entra em commit, não entra em `.env` da sua máquina,
não passa por chat nem por e-mail.

---

## Como saber que deu certo

Dentro do servidor, a coleta imprime:

```
ok: 15 repositorios do GitHub atualizados
```

Se o token estiver errado ou sem permissão, ela imprime, sem nunca mostrar o
token:

```
FALHA ao consultar o GitHub: a API do GitHub respondeu HTTP 401 / a API do GitHub respondeu HTTP 401
```

O número no fim é o que separa um problema do outro, e vale decorar:

| O que aparece | O que é |
|---|---|
| `HTTP 401` | o token venceu, foi revogado, ou está errado |
| `HTTP 403` | o token é válido mas não tem a permissão pedida |
| `recusou a consulta (NOT_FOUND)` | um repositório foi renomeado ou saiu da organização |
| `recusou a consulta (FORBIDDEN)` | falta uma das permissões da tabela acima |
| `recusou a consulta (RATE_LIMITED)` | bateu no teto de uso; ele se refaz sozinho em uma hora |
| `nao respondeu` | rede, DNS ou o GitHub fora do ar — não é com você |

E se aparecer, no meio de uma coleta que deu certo:

```
aviso: nao consegui reler os alertas de segurança de 3 projeto(s) (...) — mantive o último número conhecido, marcado como velho.
```

isso quer dizer que falta a permissão **Dependabot alerts**. O painel continua
mostrando o último número que ele conheceu, com a ressalva "não consigo reler
esse número há N dias" junto — de propósito: zerar apagaria um alerta real.

## Se der errado

| O que você vê | O que quase sempre é |
|---|---|
| `FALHA ao consultar o GitHub` | o token venceu, foi revogado, ou o app não foi **instalado** (criar não basta) |
| Coleta funciona mas sem alertas de segurança | falta a permissão **Dependabot alerts** |
| A coluna **A fazer** fica com `?` | falta a permissão **Issues** |
| Um repositório some do painel | o app foi instalado em *Only select repositories* e esse ficou de fora |
