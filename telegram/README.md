# Ponte Telegram → Hub de Projetos

Fala com o seu Hub pelo Telegram: pergunta o estado de um projeto ou conversa com o
Claude sobre o código, do celular. **Oficial, grátis, sem risco de ban, sem endpoint
público, zero dependências.**

## Setup (2 minutos, uma vez)

1. No Telegram, abra **@BotFather** → mande `/newbot` → escolha um nome e um username
   (tem que terminar em `bot`, ex: `andre_hub_bot`).
2. O BotFather te devolve um **token** (tipo `8123456789:AAH...`). Cole esse token no
   arquivo **`token.txt`** nesta pasta (só o token, nada mais).
3. Garanta que o **Hub** está rodando (`Iniciar Hub.bat`).
4. Duplo clique em **`Iniciar Telegram.bat`**.
5. No Telegram, abra **uma conversa com o seu bot** (procure pelo username) e mande
   `/start`. Você vira o **dono** — a partir daí só você é atendido.

A sessão e o "dono" ficam salvos em `config.json` (não precisa repetir).

## Como usar

| Você manda | O bot faz |
|---|---|
| `/start` ou `ajuda` | mostra os comandos |
| `projetos` | lista seus projetos |
| `projeto nukleoa` | define o projeto ativo |
| `status` | estado do projeto (git + GitHub) |
| _qualquer pergunta_ | o Claude responde (somente-leitura) sobre o projeto ativo |

Exemplo: `projeto dents` → `qual o estado pra iniciar as vendas?`

## Segurança

- **Long-polling**: o bot só faz requisições de saída pra API do Telegram. Não abre
  porta, não precisa de túnel/IP público. O Hub continua trancado em `127.0.0.1`.
- **Allowlist por dono**: o primeiro `/start` fixa o seu ID; depois disso, mensagens de
  qualquer outra pessoa são ignoradas. (Dá pra fixar via variável `TELEGRAM_OWNER`.)
- **Somente-leitura**: o bot só usa a API local do Hub (status + chat read-only). Não
  executa comandos nem altera arquivos.
- O `token.txt` é segredo — não comite, não compartilhe.

## Trocar de dono / resetar

Apague `config.json` e mande `/start` de novo.
