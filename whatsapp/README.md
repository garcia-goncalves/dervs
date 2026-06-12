# Ponte WhatsApp → Hub de Projetos

Fala com o seu Hub pelo WhatsApp: pergunta o estado de um projeto, ou conversa com o
Claude sobre o código — tudo do celular.

⚠️ **Usa o seu número pessoal via `whatsapp-web.js` (não-oficial).** Isso viola o ToS do
WhatsApp e **pode levar a banimento do número**, além de quebrar quando o WhatsApp
atualiza. Você optou por esse caminho consciente do risco. Prefira um **número
secundário** se possível.

## Pré-requisitos

1. O **Hub** precisa estar rodando (`Iniciar Hub.bat` — em `127.0.0.1:4321`).
2. Node instalado (já tem).

## Primeira vez

1. Duplo clique em **`Iniciar WhatsApp.bat`**.
2. Vai aparecer um **QR code** na janela preta.
3. No celular: **WhatsApp → Configurações → Aparelhos conectados → Conectar um aparelho**
   e escaneie o QR.
4. Quando aparecer `[wa] PRONTO`, está conectado. A sessão fica salva (não precisa
   escanear de novo).

## Como usar

Abra no WhatsApp a sua **"Conversa com você mesmo"** (Mensagens para mim / Notes to
Self) — **é o único lugar que o bot escuta**. Mande:

| Você manda | O bot faz |
|---|---|
| `ajuda` | mostra os comandos |
| `projetos` | lista seus projetos |
| `projeto nukleoa` | define o projeto ativo |
| `status` | estado do projeto (git + GitHub) |
| _qualquer pergunta_ | o Claude responde (somente-leitura) sobre o projeto ativo |

Exemplo: `projeto dents` → `qual o estado pra iniciar as vendas?`

As respostas do bot vêm com o prefixo 🤖.

## Segurança

- **Allowlist absoluta**: só processa mensagens da sua conversa consigo mesmo. Nenhum
  contato consegue acionar o bot.
- **Somente-leitura**: o bot só chama a API local do Hub (status + chat read-only). Não
  executa comandos nem altera arquivos pelo WhatsApp.
- O Hub continua trancado em `127.0.0.1`; a ponte roda na mesma máquina.

## Encerrar / desconectar

- Feche a janela preta para parar a ponte.
- Para desvincular de vez: no celular, **Aparelhos conectados** → remova o aparelho, e
  apague a pasta `.wwebjs_auth`.
