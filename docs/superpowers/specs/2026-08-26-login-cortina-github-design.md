# Desenho: a entrada do DERVS — cortina, GitHub e a tabela `credencial`

- **Data:** 26/08/2026
- **Substitui:** a seção `## 9` de `docs/superpowers/plans/dervs-fatia-1.md`
- **Estado:** aprovado pelo dono em conversa, antes de qualquer linha de código

---

## Por que este documento existe

O plano da Fatia 1 desenhou a etapa 9 como **e-mail + senha + TOTP**. O dono pediu outra
coisa: uma entrada que não pareça uma entrada, e um login **sem senha**, com a intenção
declarada de um dia vender o DERVS para outras pessoas.

Isso não é um ajuste de tela. Muda o esquema do banco, muda o despacho de `servir.py` e
muda o que a etapa 9 tem de provar. Por isso virou desenho próprio, e por isso a seção 9
do plano será reescrita para apontar para cá.

## O que fica decidido

1. Quem confere identidade é o **GitHub**. O DERVS não guarda senha de ninguém no caminho
   normal.
2. A página de `dervs.com.br` **não mostra login**. Mostra uma cortina.
3. As maneiras de provar quem se é saem da tabela `usuario` e viram uma tabela própria,
   `credencial`. É o que faz chave de acesso (*passkey*) ser um acréscimo na Fatia 2, e não
   uma reescrita.
4. Senha + TOTP **não são apagados**. Viram porta de emergência, desligada por padrão.
5. Cadastro continua fechado. Conta nova só por comando rodado dentro do servidor.

## O que NÃO está aqui, de propósito

- **Chave de acesso (passkey).** Verificar a assinatura exige aritmética de curva elíptica
  escrita à mão, porque a CI deste repositório reprova qualquer arquivo de dependência. O
  plano já a tinha marcado para a Fatia 2, pelo mesmo motivo. A tabela `credencial` é o
  preparo para ela.
- **Entrar com Google.** Mesmo mecanismo, outro registro. Entra quando houver cliente que
  não seja desenvolvedor.
- **Cadastro público, cobrança, cota por conta.** A estrutura nasce multiusuário; a porta
  nasce fechada.
- **Tela de conectar conta do GitHub e conectar servidor** — Fatia 2, como já estava.
  Coletar segredo de terceiro é outro problema, e merece a arquitetura de segredo pronta
  antes.

---

## Camada 0 — A cortina

### O que a pessoa vê

`GET /` devolve uma página escura, sem logo, sem menu, sem nome de projeto: um texto seco
e um teclado numérico de seis dígitos. Referência estética dada pelo dono:
`museuparticular.com.br`.

- **Combinação errada:** nada acontece. Sem mensagem, sem tremida, sem cor. A resposta é
  a mesma, byte a byte, para "errou" e para "está bloqueado por excesso de tentativas".
- **Combinação certa:** a página passa a mostrar **um único botão**, "Entrar com GitHub".

### A parte que não é encenação

A conferência é **no servidor**. O formulário de login não existe no HTML entregue na
primeira visita — `Ctrl+U` não revela nada porque não há nada a revelar. Só depois de
`POST /entrada` com a combinação certa o servidor devolve o botão.

Isto é o que separa este desenho da versão ingênua, em que a palavra secreta viaja no
JavaScript e qualquer pessoa a lê em dez segundos.

### Contrato

| Rota | Método | Entrada | Saída |
|---|---|---|---|
| `/` | GET | — | página da cortina, `noindex` |
| `/entrada` | POST | `{"combinacao": "######"}` | 204 + cookie `cortina`, **ou** 204 sem cookie |

O 204 é o mesmo nos dois casos. **Quem sabe se acertou é o cookie, não o corpo nem o
código de status.**

### Como a combinação é guardada

- Nunca em claro. Nunca no código. Nunca no `.env`. Nunca no repositório.
- Só a impressão digital, por `scrypt`, na tabela `instalacao` (nova, uma linha só):

```sql
CREATE TABLE IF NOT EXISTS instalacao (
    id                INTEGER PRIMARY KEY CHECK (id = 1),  -- uma linha, e so uma
    combinacao_hash   TEXT,        -- scrypt dos seis digitos. NULL = ainda nao gerada.
    combinacao_em     TEXT,        -- quando foi gerada ou trocada
    criada_em         TEXT NOT NULL
);
```

  O `CHECK (id = 1)` é o que impede uma segunda instalação de aparecer por engano e
  duas cortinas passarem a valer ao mesmo tempo.
- Comparação por `hmac.compare_digest` — comparação de tempo constante, para não vazar
  quantos dígitos bateram pelo tempo de resposta.
- **Primeiro arranque no servidor:** se não houver combinação gravada, o DERVS gera seis
  dígitos aleatórios (`secrets`), grava a impressão digital e **imprime o número uma única
  vez no log**. Nunca mais.
- **Troca:** tela de configuração, com a pessoa já autenticada. Mesma tela que um cliente
  futuro usará.
- **Ambiente local** (`DERVS_AMBIENTE=local`): combinação fixa `000000`, escrita no
  `README.md`. Dado de teste não é segredo — é regra da casa.

### Teto de tentativas

Seis dígitos são um milhão de combinações. Sem teto, um robô as percorre. Com teto, a
cortina cumpre o papel dela.

- Contagem **por origem** (IP), em memória, na rota — não no banco.
- Cinco tentativas por janela de 15 minutos; excedeu, toda tentativa daquela origem
  responde igual até a janela virar.
- **Isto paga a dívida nomeada da etapa 11.** O contador que existia na tabela de
  pareamento foi removido na etapa 8 justamente porque contar no recurso deixa um usuário
  matar o acesso do outro. Contar por origem, na rota, é o desenho certo — e a etapa 11
  reusa este mesmo mecanismo para o código de pareamento.

### Cookie `cortina`

Assinado por HMAC com a chave do cofre, contendo apenas o instante de expiração. Dez
minutos, `HttpOnly`, `SameSite=Lax`, `Secure` quando o ambiente não é local. Não vai ao
banco: é passageiro demais para justificar uma linha.

### O que a cortina NÃO faz — dito aqui para não ser esquecido

**A cortina não é a fechadura.** Ela para robô de varredura e curioso. Não para alguém
determinado, e não deve ser usada como argumento para afrouxar a camada 1. Quem protege o
dado é o login do GitHub e a lista de contas autorizadas.

---

## Camada 1 — A porta: entrar com GitHub

### O caminho, em ordem

1. `GET /entrar/github` — exige o cookie `cortina` válido. Sorteia um `state` (valor
   aleatório de uso único, defesa contra pedido forjado de fora), guarda a impressão
   digital dele num cookie curto, e redireciona para
   `https://github.com/login/oauth/authorize`.
2. A pessoa aprova no github.com. O GitHub redireciona de volta para
   `GET /entrar/github/retorno?code=…&state=…`.
3. O `state` é conferido. Não bateu: rejeição genérica, fim.
4. O servidor troca o `code` por um token, falando **de servidor para servidor** com
   `https://github.com/login/oauth/access_token` (`urllib.request`, biblioteca padrão).
5. Com o token, lê `https://api.github.com/user` e obtém o **id numérico** e o login.
6. Procura uma `credencial` de tipo `github` com aquele id. Achou e a conta está ativa:
   cria sessão. Não achou: rejeição genérica.
7. O token do GitHub é **descartado na hora**. O DERVS não pede escopo nenhum além de
   identidade, e não guarda nada do GitHub além do id.

### Decisões que precisam estar escritas

- **Casamos pelo id numérico, nunca pelo login.** Login do GitHub pode ser trocado e o
  nome antigo fica livre para outra pessoa registrar. Casar por texto é entregar a conta
  a quem pegar o nome abandonado.
- **Rejeição é sempre idêntica.** Conta inexistente, conta desativada, `state` inválido e
  cortina vencida devolvem a mesma coisa. Resposta diferente revela quem existe.
- **`sessao.segundo_fator_em` é preenchido no login por GitHub.** O GitHub obriga segundo
  fator na conta dele; identidade e segundo fator acontecem no mesmo passo. Esta é uma
  decisão de confiança, e está aqui declarada, não escondida.
- **A verificar na implementação:** se `GET /user` devolver o campo
  `two_factor_authentication`, exigir que seja verdadeiro. Se não devolver, seguir com a
  decisão do item acima e registrar isso no código, junto do link da documentação
  consultada. Não inventar o campo.
- **Nenhuma conta é criada no retorno do OAuth.** `POST /api/registro` devolve 403, como o
  plano já exigia.

### O Client Secret

Vive dentro do servidor, fora do repositório, lido de variável de ambiente
(`DERVS_GITHUB_SECRET`). Não entra em `.env` de máquina de trabalho, não entra em commit,
não entra em memória, não passa por conversa. O Client ID é público e pode ficar em
configuração versionada.

**Precisa da mão do dono, uma vez:** registrar o OAuth App em github.com, e colar o
segredo no servidor. Roteiro passo a passo entra no plano de implementação.

---

## Camada 2 — A chave reserva

Senha + TOTP continuam existindo, agora como credenciais na tabela nova.

- **Não aparecem na tela** enquanto houver credencial `github` ativa na instalação.
- Servem para o dia em que o GitHub estiver fora do ar ou o OAuth App quebrar.
- Ligar é decisão consciente, por comando dentro do servidor.

Sem isto, os dois donos ficam trancados do lado de fora do próprio sistema por uma falha
que não é deles. Custa pouco: a etapa 8 já construiu `scrypt`, TOTP cifrado e o cofre.

---

## O banco: a tabela `credencial`

### O problema com o esquema de hoje

`usuario` tem `senha_hash NOT NULL`, `totp_segredo` e `totp_confirmado_em` como colunas
próprias. Isso amarra uma pessoa a um jeito de entrar. Uma conta que só usa GitHub não tem
senha — e não pode ser obrigada a inventar uma.

### O esquema novo

```sql
CREATE TABLE credencial (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    tipo          TEXT NOT NULL CHECK (tipo IN ('github','senha','totp','passkey')),
    -- Chave externa da identidade. github: o id NUMERICO do GitHub, em texto.
    -- passkey: o identificador da credencial. senha/totp: o proprio usuario_id
    -- em texto, o que faz o UNIQUE abaixo garantir "uma senha por pessoa".
    identificador TEXT NOT NULL,
    -- github: NULL (nao ha segredo a guardar). senha: scrypt. totp: CIFRADO.
    segredo_hash  TEXT,
    criado_em     TEXT NOT NULL,
    -- NULL = nunca usada. Para 'totp', tambem e o "confirmado_em" de antes:
    -- a negativa continua sendo o padrao.
    usado_em      TEXT,
    revogada_em   TEXT,
    UNIQUE (tipo, identificador)
);
CREATE INDEX IF NOT EXISTS ix_credencial_dono ON credencial (usuario_id, tipo);
```

`UNIQUE (tipo, identificador)` é a peça central: dois usuários não podem reivindicar o
mesmo id do GitHub, e ninguém tem duas senhas.

### A migração

`usuario` perde `senha_hash`, `totp_segredo` e `totp_confirmado_em`; o conteúdo vira
linhas em `credencial`. Regras já pagas com sangue nas etapas anteriores, repetidas aqui
porque esquecer uma delas custa o banco:

1. A migração roda **antes** de `executescript(ESQUEMA)`. Ao contrário, o
   `CREATE TABLE IF NOT EXISTS` recria a tabela vazia e o dado antigo fica inalcançável
   para sempre.
2. `executescript` **não abre transação** e dá `COMMIT` implícito. Use `BEGIN IMMEDIATE`,
   `execute` um comando por vez, e `commit` no fim. Queda no meio tem de voltar a zero.
3. Hoje há zero usuários gravados, mas a migração é escrita como se houvesse — é ela que
   vai rodar no servidor daqui a um mês.

### Como nasce a primeira conta

Comando rodado dentro do servidor (e localmente, por mim, para testar):

```
python autenticacao.py convidar <login-do-github>
```

Ele resolve o id numérico em `https://api.github.com/users/<login>`, cria o `usuario` e a
`credencial` de tipo `github`. Não existe caminho pela web para criar conta.

---

## O que muda em `servir.py`

- **O `TOKEN` de arranque (`servir.py:111-113`) sai de cena como credencial.** Ele é defesa
  contra pedido forjado de outro site, não prova de identidade. Vira um token anti-CSRF
  **por sessão**, derivado da sessão, não um valor global.
- Toda rota da tabela `ROTAS` ganha classificação declarada. Rota de dado sem sessão com
  segundo fator conferido responde 401 ou 302, e **o corpo não contém nome de projeto
  nenhum**.
- Rota sem classificação declarada **falha o teste**. Nega por padrão, inclusive no teste.
- Cookie de sessão: `HttpOnly`, `SameSite=Lax`, `Secure` fora do ambiente local. No banco
  vai só a impressão digital do cookie, como a etapa 8 já previu.

---

## Como isto será provado

Arquivo novo `test_autenticacao.py`, mais acréscimos em `test_banco.py` e `test_rotas.py`.
**Nenhum teste toca a rede:** as chamadas ao GitHub passam por `urllib.request`, que é
substituído por dublê no teste.

**Cortina**
1. `GET /` não contém nenhuma das palavras da tela autenticada, nem `oauth`, nem o Client ID.
2. Combinação errada e combinação certa devolvem o mesmo status e o mesmo corpo; só o
   cookie difere.
3. Sexta tentativa da mesma origem dentro da janela não confere mais nada, e responde igual.
4. Combinação nunca aparece em claro no banco.

**Porta**
5. `state` ausente, trocado ou reusado: rejeitado.
6. Id do GitHub fora da tabela `credencial`: rejeitado, com resposta idêntica à do id
   inexistente.
7. Conta com `desativado_em` preenchido: rejeitada, mesmo com id correto.
8. Login por GitHub grava `segundo_fator_em`.
9. `POST /api/registro` devolve 403.
10. O token do GitHub não é gravado em lugar nenhum — o teste varre banco e disco.

**Rotas**
11. Para **cada** rota de dado em `servir.ROTAS`, requisição sem sessão devolve 401/302 e
    corpo sem nome de projeto.
12. Rota sem classificação declarada reprova a suíte.

**Segredo**
13. Nenhuma resposta da API contém segredo de TOTP, token de agente ou Client Secret — o
    teste varre o JSON inteiro atrás dos valores gravados.

**Banco**
14. Migração interrompida no meio deixa o banco no estado anterior, íntegro.
15. Dois usuários não conseguem gravar o mesmo id do GitHub.

---

## Riscos declarados

- **A cortina pode dar falsa sensação de segurança.** Mitigação: está escrito em três
  lugares deste documento que ela não é a fechadura, e nenhum teste a trata como tal.
- **Dependência do GitHub estar de pé.** Mitigação: a camada 2.
- **A decisão de confiar no segundo fator do GitHub** é uma decisão, não um fato. Está
  declarada acima e é revisável.
- **Seis dígitos é pouco.** O teto por origem é o que sustenta a escolha. Se um dia a
  cortina precisar ser fechadura, ela muda — mas aí não é mais cortina.
- **`autenticacao.py` vai crescer.** Cortina, OAuth, sessão e credenciais em um arquivo só
  passam de mil linhas. Se passar, quebra em `cortina.py` e `autenticacao.py` durante a
  implementação, não depois.
