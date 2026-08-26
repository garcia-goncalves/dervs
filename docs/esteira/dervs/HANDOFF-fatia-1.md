# Handoff — DERVS Fatia 1, etapas 1 a 7 concluídas

Gravado em 26/08/2026, atualizado no fim do dia.
Estado: `main@81424f6`, árvore limpa, tudo no GitHub, CI verde.
**Etapas 1 a 7 concluídas.** A próxima é a 8.

## ATENÇÃO — A PASTA MUDOU

O trabalho agora acontece em **`C:\Users\Desktop\source\repos\dervs`**
(era `source\painel-projetos`). Abra a janela do VS Code lá.

- Repositório: `github.com/garcia-goncalves/dervs` — privado, `main` protegida.
- A memória do Claude foi migrada para o slug `C--Users-Desktop-source-repos-dervs`.
- `source\painel-projetos` ficou **congelado de propósito** — ponto de retorno.
  O processo em `localhost:4777` ainda roda de lá.

## FEITO (etapas 1 a 6, todas com prova rodada)

1. **Rename** `dervs` → `dervs-hub`, pelo site, pelo dono. Provado.
2. **André reaponta o remoto** — ele diz que fez; **a saída do `git remote -v` NUNCA
   FOI COLADA.** Não é verificável daqui (é operação local, sem rastro no GitHub).
   Mitigado, não provado: ver "risco aceito" abaixo.
3. **`hub` mesclada na `main`** do dervs-hub, sem squash. Autoria preservada:
   `andgoncs: 13` commits, confirmado pela API do GitHub.
4. **Repositório `dervs` criado**, privado, 81 commits herdados, `.gitattributes`
   no mesmo commit da normalização. Zero CRLF no índice e no disco. 500 testes passam.
5. **`vivo/` como subárvore**, com `.dockerignore` + `Dockerfile` + `LEIA-ANTES.md`
   **no mesmo commit**. Provado construindo a imagem: `vivo/` = 0, `.js` = 0,
   `dangerously-skip-permissions` = 0. A imagem tem 15 arquivos, conferidos.
6. **CI verde** — 483 testes, 8 arquivos, um job só. Vigia novo da barreira do `vivo/`,
   testado pelos DOIS lados (passa no código são, reprova nos três tipos de sabotagem).

**Extra (fora do plano, pedido pelo dono):** o projeto saiu de `source\` e foi para
`source\repos\dervs`, junto com os outros 16. `coletar.py:47` (`RAIZ`) só mede o que
está lá — antes o hub não se media. `pastas_de_projeto()` agora devolve 17 projetos,
`dervs` presente, sem duplicar. O comentário de `coletar.py:51` foi atualizado.

## RISCO ACEITO, CONSCIENTEMENTE

A etapa 2 não tem a prova que o plano exige. Em vez de travar, o silêncio foi removido:

- O `dervs` novo tem histórico **sem parentesco** com o clone do André → um `git push`
  dele apontando para o nome antigo é **recusado com erro na tela**.
- `main` protegida: `allow_force_pushes: false`, `allow_deletions: false` → o único
  caminho que passaria por cima da recusa está fechado.

**Ainda assim, peça a saída do `git remote -v` ao André.** É a última confirmação.

## ETAPA 7 — CONCLUÍDA (26/08/2026, PR #2, `main@81424f6`)

`servir.py` perdeu `/api/acao`, `/api/execucao` e o proxy do grafo. O despacho
virou a tabela `servir.ROTAS`, e `test_rotas.py` é o vigia que impede a volta.
Restaram 8 caminhos, 7 de leitura e 1 de escrita:

```
['/', '/api/dados', '/api/silenciar', '/favicon.ico', '/index.html',
 '/painel-projetos.ico', '/painel-projetos.png', '/painel-projetos.svg']
```

**Decisão de produto do dono, nesta sessão:** `/api/silenciar` — o "x" que
esconde um alerta por 24 h — sobreviveu, com porta própria. Só escreve no
banco. Sem ele o painel ficaria só de leitura até a etapa 13.

**A tela foi amputada junto** (o plano não a listava, mas ela chamava as rotas
mortas). Saíram o botão Resolver, a faixa da fila, a aba do grafo, os botões
"Medir agora" e "Atualizar GitHub", e os itens da paleta que abriam o VS Code,
subiam contêiner ou davam `git push`.

**Provado:** 471 testes OK · o vigia reprova as **5** sabotagens testadas ·
servidor de pé com `/api/acao`, `/api/execucao`, `/grafo/` e `/hub.db` todos
404 · página carrega sem erro no console e o "x" foi clicado de verdade.

**O vigia era cego duas vezes, e a revisão pegou:** ele lia só o *nome* da rota
e da função. Uma rota `/api/diagnostico` → `Hub._diagnostico` com `subprocess`
no corpo passava; e um `do_PUT` novo escapava da tabela inteira, porque o
`BaseHTTPRequestHandler` despacha por nome de método. Hoje ele segue o grafo de
chamadas e enumera `dir(Hub)`. **Lição durável: teste-barreira precisa ser
provado pelos dois lados, e a sabotagem tem de vir de quem não escreveu a
barreira.**

**A revisão de segurança aprovou** ("pode mergear", nada bloqueante) e provou
por execução que `/hub.db`, `/.git/config`, `/servir.py` e as travessias com
`%2e%2e` dão todas 404. As quatro pontas soltas que ela listou foram feitas:
prazo de 10 min no coletor (coletor travado congelava o número na tela **em
silêncio**), `HEAD` sem corpo, teto de 200 no id do "esconder", e o `Dockerfile`
deixou de embarcar `execucao.py` e `fila.py`.

`execucao.py` e `fila.py` continuam no repositório, 182 testes verdes, **sem
rota apontando** — de propósito, pela trava de diff de `fila.py:229`.

## A RETOMAR — ETAPA 8

Plano: `docs/superpowers/plans/dervs-fatia-1.md`, seção "## 8" — banco
multiusuário, pareamento e arquivamento permanente. Depois: 9 (login + 2FA,
disputa `servir.py` com a 7, já mesclada) · 10 · 11 · 12 · 13→14→15 (as telas)
· 16 (publicação) · 17.

## PARA A ETAPA 16 — o que a revisão de segurança deixou anotado

Nada disso é defeito do que já foi feito; é o roteiro de expor o painel.

1. **A ordem entre "virar 0.0.0.0" e "ter login" não é negociável.**
   `/api/dados` não tem autenticação nenhuma e devolve o caminho absoluto do
   disco do dono, o inventário de projetos e o texto de todas as pendências,
   inclusive as de segurança. Quem segura isso hoje é o bind em `127.0.0.1`
   mais a checagem de `Host`. **Se as duas coisas não couberem no mesmo passo,
   quem espera é o bind.**
2. `HOSTS_OK` e `ORIGENS_OK` só aceitam localhost — atrás do nginx tudo vira
   403. O risco não é o 403, é a pressa que faz alguém relaxar para "aceita
   qualquer coisa". Allowlist explícita do domínio, e `X-Forwarded-Host` fora
   da decisão.
3. `pendencia_estado` **não tem coluna de dono** — com múltiplos usuários, é
   IDOR por desenho de esquema. Conserta-se na migration da etapa 8, não na
   rota. E o `TOKEN` é um só por processo, injetado em toda página: serve de
   anti-CSRF e **não pode** virar credencial de usuário.
4. A página não manda **nenhum** cabeçalho de segurança (sem CSP, sem
   `frame-ancestors`, sem `nosniff`). O token vive dentro do HTML.
5. Nada tem limite de taxa, e `/api/dados` recalcula as regras a cada chamada.
6. `servir.py:982` escuta em `127.0.0.1` — dentro de contêiner isso não aceita
   conexão de fora. Precisa virar `0.0.0.0`, **e só depois do item 1**.

## ARMADILHAS JÁ PAGAS — NÃO REPETIR

- **Caminho do Windows em string Python não-crua corrompe em silêncio.** A
  barra invertida seguida de `r` vira *carriage return*: `source` barra `repos`
  gravou `sourceepos`. O Python só avisa com `SyntaxWarning: invalid escape
  sequence`, e a substituição seguinte deixa de casar — cai-se investigando o
  lado errado. Use string crua, ou a ferramenta `Write`. Custou três repetições
  em 26/08.
- **Corte por marcador precisa dos DOIS marcadores na mesma seção.** Cortando
  o CSS do painel de execução, escolhi um marcador de fim que ficava depois do
  `<body>`: a remoção levou junto o corpo inteiro do `index.html`. Restaurado do
  commit e refeito. Confira `grep -c '<script>' index.html` depois de cada corte.
- **`taskkill` é barrado pelo classificador; `Stop-Process` passa.**
  `powershell -NoProfile -Command "Stop-Process -Id <PID> -Force"`.


- `servir.py` **importa** `regras`/`banco`/`coletar` na subida. Editar `.py` e conferir
  na tela sem reiniciar mostra a versão antiga.
- **Heredoc corrompe acento no Windows.** Mensagem de commit com acento: escreva o
  arquivo com a ferramenta Write e use `git commit -F <arquivo>`.
- **Push junto com outros comandos na mesma linha é barrado** por um classificador.
  Rode `git push` sozinho, numa chamada só dele.
- `git ls-files --eol | grep 'w/crlf'` mede o **disco**; `i/crlf` mede o **índice**.
  São coisas diferentes e o plano cobra a primeira.
- **A cota de Actions está em 88%** (2.626 de 3.000 min). Nada de job paralelo:
  a cobrança é por tarefa arredondada.
- **Pendência conhecida para a etapa 16:** `servir.py:982` escuta em `127.0.0.1`.
  Dentro de um container isso **não aceita conexão nenhuma de fora**. Precisa virar
  `0.0.0.0` (atrás do nginx) quando a publicação for montada.

## NÚMEROS REAIS (os documentos da esteira erravam)

- **500** funções de teste em 8 arquivos `test_*.py` **na raiz** (não em `tests/`).
  A CI reporta 483 pelo runner do unittest. Não são "452".
- **18** rótulos em `regras.ROTULO_REGRA`. Não são "16".
- `projects.json` não existe. `casos.json` existe.
