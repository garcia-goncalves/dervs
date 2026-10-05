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

## O que ja existe (feito em 27/08/2026)

O app **ja foi criado e instalado**. Os dois valores publicos:

| Valor | Conteudo |
|---|---|
| **App ID** | `4739197` |
| **Installation ID** | `157015815` |
| Nome no GitHub | `DERVS coletor` (`dervs-coletor`) |
| Onde administrar | <https://github.com/organizations/garcia-goncalves/settings/apps/dervs-coletor> |

Permissoes concedidas, todas `Read-only`: Metadata (obrigatoria), Contents,
Issues, Pull requests, Actions e Dependabot alerts. Webhook desligado.
Instalado em `garcia-goncalves`, **All repositories**.

O que **falta**: a chave privada chegar ao servidor — que ainda nao existe. A
troca chave -> token de instalacao **ja esta no codigo** (`github_app.py`), e a
secao "Como saber que deu certo", no fim, diz o que aparece quando ela funciona.

O passo a passo abaixo fica como registro de **como** isso foi feito — e serve
para refazer, se um dia o app precisar ser recriado.

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

## Como o sistema usa isso — as três portas, nesta ordem

O coletor tenta três coisas, e para na primeira que funciona:

| Ordem | O que ele procura | Onde isso vale |
|---|---|---|
| 1º | `DERVS_GITHUB_TOKEN`, um token pronto | saída de emergência |
| 2º | o **GitHub App**: `DERVS_GITHUB_APP_ID` + `DERVS_GITHUB_INSTALLATION_ID` + `DERVS_GITHUB_APP_KEY` | o **servidor** |
| 3º | o `gh` que você já logou | a **sua máquina** |

Faltando uma variável do meio, ele **não reclama e não cai**: desce para o `gh`.
Isso é de propósito — na sua máquina a ausência é o normal, e um aviso a cada
vinte minutos treinaria você a ignorar avisos.

**Desde 01/09/2026 o número da instalação também pode vir do banco**, gravado
pelo botão *Conectar a conta* da tela `Conectar projeto`. A ordem acima **não
muda**: `DERVS_GITHUB_INSTALLATION_ID` continua vencendo, porque quem define uma
variável de ambiente está depurando e quer que ela valha. O banco entra só
quando ela não existe.

Para o botão funcionar, o servidor precisa de mais uma variável:
`DERVS_GITHUB_APP_SLUG` — o nome que aparece na URL de instalação
(`github.com/apps/<slug>`). Ele é **público**, e por isso mora ao lado do Client
ID e não junto dos segredos. Sem ele o botão responde "não existe": melhor não
ter porta do que ter porta que leva a um endereço que não abre.

**A dívida das várias contas foi paga em 05/10/2026.** No **servidor**, com o App
configurado (`DERVS_AMBIENTE` diferente de `local` e `DERVS_GITHUB_APP_ID` ou
`DERVS_GITHUB_APP_KEY` presente), o coletor entra no **modo por conta**: para cada
conta ativa com projeto, usa a instalação **daquela** conta (lida do banco) e
grava o resultado nela. Nesse modo `DERVS_GITHUB_TOKEN` e
`DERVS_GITHUB_INSTALLATION_ID` são **ignorados** (a ordem da tabela acima só vale
fora dele, isto é, na sua máquina), e o `gh` nunca é chamado.

A conta que não deu para medir (sem instalação, aplicativo desinstalado, passou
do teto ou do prazo da rodada) aparece no bloco "No GitHub" com o **motivo em
português**, e não como "nunca foi medido". O motivo mora numa linha de sistema
`_github` da tabela `medida` e só aparece para a conta dona. O código de saída é
1 só quando ele tentou medir alguma conta e não mediu nenhuma. Há teto de
chamadas por conta e por rodada, e um prazo de 480 s (abaixo do limite de 600 s do
servidor). **Dívida nova:** a ordem é fixa por conta, então, se o teto apertar, as
últimas contas ficam sem medir; um rodízio fica para depois.

### A troca chave → token, que agora existe

Um GitHub App não entrega um token: entrega uma chave privada. Com ela, o
sistema **assina um bilhete** que diz "sou o app 4739197", manda para o GitHub, e
recebe de volta um token que vale **uma hora**. Quando falta pouco para vencer,
ele pede outro. Nada disso aparece para você.

Quem faz é o `github_app.py`. Duas coisas dele valem saber:

- **A conta foi escrita à mão**, porque o Python não traz essa matemática pronta
  e o projeto não usa biblioteca de fora. Por isso ela é conferida contra o
  **OpenSSL**: o teste assina uma frase conhecida e exige que o resultado seja
  igual, byte a byte, ao que o OpenSSL produziu. Se um dia divergir num único
  byte, a CI fica vermelha — não o servidor, às três da manhã.
- **A chave nunca é impressa, gravada nem posta em mensagem de erro.** Quando a
  troca falha, a frase que aparece diz o motivo e nada mais.

O que **ainda falta**, e não depende de código: levar as duas variáveis públicas
e os dois segredos para dentro do servidor — que ainda não existe.

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
