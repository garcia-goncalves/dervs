# Registrar o app do GitHub — o roteiro completo

Isto exige a sua mão: só você pode aprovar coisas na sua conta do GitHub. São
cinco minutos, uma vez. **Você não digita nenhum segredo numa conversa de chat.**

O que isso faz: liga o botão "Entrar com GitHub" do DERVS. É grátis, para sempre
e sem limite de usuários — é o mesmo mecanismo que o Vercel, o Netlify e o
Sentry usam.

---

## Antes de começar

Você vai precisar de **dois endereços**, e eles dependem de onde o DERVS vai
rodar. Registre **um app para cada lugar** — não tente usar o mesmo nos dois, o
GitHub aceita só um endereço de volta por app.

| Onde | Homepage URL | Authorization callback URL |
|---|---|---|
| Sua máquina | `http://localhost:4777` | `http://localhost:4777/entrar/github/retorno` |
| O servidor | `https://dervs.com.br` | `https://dervs.com.br/entrar/github/retorno` |

O de casa é opcional: na sua máquina já existe a porta **Entrar · ambiente
local**, que não precisa de app nenhum.

---

## O que ja existe (feito em 27/08/2026)

O OAuth App **do servidor** ja foi registrado:

| Valor | Conteudo |
|---|---|
| Nome | `DERVS` |
| **Client ID** (`DERVS_GITHUB_ID`) | `Ov23litdc9CRv44T2KTM` |
| Homepage | `https://dervs.com.br` |
| Callback | `https://dervs.com.br/entrar/github/retorno` |
| Device Flow | desligado |
| Onde administrar | <https://github.com/settings/applications/3820865> |

O **Client Secret** foi gerado e gravado no cofre do repositorio como
`DERVS_GITHUB_SECRET` (Settings -> Secrets and variables -> Actions). Ele nunca
passou por conversa nem por arquivo do repositorio.

O Client ID tambem esta gravado como *variable* `DERVS_GITHUB_ID` no mesmo lugar.

**Falta**: as duas variaveis chegarem ao ambiente do servidor, e convidar cada
pessoa pela tabela `credencial` (secao "Depois: liberar quem entra").

**Nao existe** app para `localhost`: na maquina do dono a porta
**Entrar - ambiente local** ja resolve, e app de teste seria superficie a toa.

---

## Passo a passo

**1.** Abra <https://github.com/settings/developers> e clique em
**OAuth Apps** → **New OAuth App**.

**2.** Preencha os quatro campos, exatamente assim:

| Campo | O que digitar |
|---|---|
| **Application name** | `DERVS` |
| **Homepage URL** | o da tabela acima |
| **Application description** | pode deixar em branco |
| **Authorization callback URL** | o da tabela acima, **com o `/entrar/github/retorno` no fim** |

O campo que erra com mais frequência é o último. Se ele não bater **letra por
letra** com o endereço que o DERVS usa, o GitHub recusa a volta e você vê a capa
de novo, sem explicação — o DERVS não explica por que recusou, de propósito.

**3.** Clique em **Register application**.

**4.** A tela seguinte mostra o **Client ID**. Ele é público: pode ser copiado,
colado e versionado sem preocupação.

**5.** Clique em **Generate a new client secret**. O GitHub mostra o segredo
**uma única vez**. Não feche a aba antes de guardá-lo.

**6.** Marque **Enable Device Flow?** como **desmarcado**. O DERVS não usa esse
caminho, e caminho de entrada que ninguém usa é superfície de ataque de graça.

---

## Onde cada valor vai parar

**O Client ID** (público) vira a variável `DERVS_GITHUB_ID`.

**O Client Secret** (segredo) vira `DERVS_GITHUB_SECRET`, e vale a regra da
casa, sem exceção:

- **Não** entra em commit, em arquivo do repositório nem em `.env` da sua
  máquina de trabalho.
- **Não** passa por conversa de chat, por e-mail nem por mensagem.
- Mora **dentro do servidor**, no ambiente do processo, e no cofre de segredos do
  GitHub Actions se o deploy precisar dele.

Se ele vazar: volte na mesma tela, clique em **Generate a new client secret**, e
o antigo morre na hora. Depois troque a variável no servidor e reinicie. Rodar
isso leva um minuto — é por isso que o desenho prefere um segredo trocável a um
segredo escondido.

---

## Depois: liberar quem entra

Registrar o app não deixa ninguém entrar. Ele só ensina o GitHub a dizer "esta
pessoa é o fulano". Quem decide se o fulano pode entrar é o DERVS, contra a
tabela `credencial`.

Para cada pessoa, **dentro do servidor**:

```
python autenticacao.py convidar <login-do-github> <email>
```

O comando busca o **id numérico** daquele login no GitHub e guarda o número, não
o nome. É de propósito: login do GitHub pode ser trocado, e o nome antigo fica
livre para outra pessoa registrar. Casar por texto seria entregar a conta a quem
pegasse o nome abandonado.

Não existe caminho pela web para criar conta. `POST /api/registro` não existe, e
há teste cobrando que ele continue não existindo.

---

## Como saber que deu certo

Na subida, o servidor deixa de imprimir o aviso:

```
AVISO: sem DERVS_GITHUB_ID/DERVS_GITHUB_SECRET, a entrada por GitHub responde 404.
```

E na capa, depois da combinação de seis dígitos, aparece o botão **Entrar com
GitHub**. Antes de o app existir, esse botão não aparece — não é falha, é a
mesma decisão de sempre: botão que leva a erro é pior que botão que não existe.

## Se der errado

| O que você vê | O que quase sempre é |
|---|---|
| Volta para a capa sem explicação | o **callback URL** não bate letra por letra |
| `404` ao clicar no botão | falta `DERVS_GITHUB_ID` ou `DERVS_GITHUB_SECRET` no ambiente do servidor |
| O botão nem aparece | o mesmo motivo acima — o DERVS esconde o botão em vez de mostrar um que quebra |
| Entra e cai fora na hora | a conta do GitHub não foi convidada, ou foi convidada com outro login |
