# Notifier — avisos PROATIVOS do Hub pro Telegram

Processo **independente** do `bot.js`. O `bot.js` é *pull* (só responde quando
você pergunta); o `notifier.js` é *push* — fica de olho na API local do Hub e
te avisa sozinho, sem você precisar perguntar nada.

## O que ele avisa

| Evento | Quando dispara |
|---|---|
| 🔴 Worker encerrado/morreu/removido | um node da lousa que estava `running` muda de status ou some |
| 📌 Nota nova | qualquer post-it novo em qualquer lousa (`portfolio` + cada projeto) |
| 📦 Commit novo | o `HEAD` de um projeto cadastrado muda |
| 🕒 Resumo periódico | a cada 30 min (configurável), lista os agentes rodando agora |

## Como roda

- Polling da API do Hub em `http://127.0.0.1:{HUB_PORT ou 4321}` — rotas **já
  existentes**, nenhuma nova foi criada:
  - `GET /api/projects` — projetos cadastrados (e vira a lista de lousas: `portfolio` + cada `id`)
  - `GET /api/agents` — agentes rodando agora (pro resumo)
  - `GET /api/canvas/:board` — notas da lousa
  - `GET /api/canvas/:board/list` — nodes + status vivo (pra detectar término)
  - `GET /api/projects/:id/status` — último commit (mesma rota que o `status` do bot.js já usa)
- Envio pro Telegram: mesmo `token.txt` do `bot.js`, mesmo dono fixado em `config.json` (`owner`).
- **Dedupe em disco** (`notifier-state.json`, ao lado deste arquivo): guarda quais notas/nodes/commits
  já foram vistos. Na *primeira* observação de cada lousa/projeto, ele só **semeia** o estado —
  não manda o histórico inteiro que já existia antes do notifier nascer. Depois disso, só avisa
  transições novas. Sobrevive a restart (não reenvia o que já mandou).
- **Backoff exponencial** (2s → até 5min) tanto pra chamadas ao Hub quanto pro Telegram, em caso
  de erro de rede.
- **Segurança**: só fala com `127.0.0.1` (não abre porta, não usa túnel); é somente leitura
  (só faz `GET` no Hub); o token nunca é logado — só entra na URL da chamada HTTPS pro Telegram,
  que nunca é impressa. O log só mostra o `message_id` retornado pelo Telegram (não o token).

## Rodar

Duplo clique em **`Iniciar Notifier.bat`** (o Hub precisa estar rodando). Fica de olho de novo
mesmo depois de fechar e reabrir — o estado de dedupe está em `notifier-state.json`.

Variáveis de ambiente opcionais:
- `HUB_PORT` — porta do Hub (padrão 4321)
- `TELEGRAM_TOKEN` — sobrepõe o `token.txt`
- `NOTIFIER_POLL_MS` — intervalo do ciclo principal (padrão 20000)
- `NOTIFIER_COMMIT_POLL_MS` — intervalo de checagem de commits (padrão 120000)
- `NOTIFIER_SUMMARY_MS` — intervalo do resumo periódico (padrão 1800000 = 30 min)

## Validação real (feita em 05/08/2026)

1. Notifier iniciado do zero (`notifier-state.json` limpo). Primeiro ciclo **semeou** o estado
   de todas as lousas (`portfolio`, `hragro`, `nexa`, `dents`, `medcrm`, ...) sem mandar nada
   do histórico (ex.: as 17 notas já existentes em `dents` e as 32 em `medcrm` não geraram aviso).
   O resumo periódico inicial foi enviado nesse mesmo ciclo (primeira vez, `lastSummary` era 0).
2. Disparado um post-it de teste de verdade, pelo CLI da lousa:
   ```
   node "C:\Users\andre\hub\lousa.js" note "teste notifier"
   ```
   → `nota adicionada`
3. No ciclo seguinte (poll de 20s), o notifier detectou a nota nova (id `notef87ba`, board
   `portfolio`) e chamou o Telegram. Log real (sem token, só o retorno do Telegram):
   ```
   [notifier] no ar. hub: http://127.0.0.1:4321. poll: 20000ms.
   [notifier] enviado (msg id 14)
   ```
   `msg id 14` é o `message_id` que a API do Telegram devolveu com `ok:true` — confirma que a
   mensagem foi aceita e entregue ao chat do dono.
4. Conferido que o token não aparece em nenhum ponto do log (`grep` do conteúdo de `token.txt`
   contra o log → 0 ocorrências).
5. `notifier-state.json` atualizado com a nota nova (`notef87ba`) na lista de vistas — uma
   reinicialização do processo agora não reenviaria essa mesma nota.

Notifier ficou rodando em background após o teste (é o serviço pedido — fica de olho pra sempre).
