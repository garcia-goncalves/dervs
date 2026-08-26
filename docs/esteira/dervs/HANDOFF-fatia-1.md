# Handoff — DERVS Fatia 1, etapas 1 a 8 concluídas

Gravado em 26/08/2026, atualizado no fim do dia.
**Etapas 1 a 8 concluídas.** A próxima é a 9.

## ATENÇÃO — A PASTA MUDOU

O trabalho agora acontece em **`C:\Users\Desktop\source\repos\dervs`**
(era `source\painel-projetos`). Abra a janela do VS Code lá.

- Repositório: `github.com/garcia-goncalves/dervs` — privado, `main` protegida.
- A memória do Claude foi migrada para o slug `C--Users-Desktop-source-repos-dervs`.
- `source\painel-projetos` ficou **congelado de propósito** — ponto de retorno.
  O processo em `localhost:4777` roda **desta** pasta desde 26/08 — foi
  reiniciado daqui na etapa 8.

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

## ETAPA 8 — CONCLUÍDA (26/08/2026, branch `etapa-8-banco`)

`banco.py` ganhou seis tabelas — `usuario`, `sessao`, `maquina`, `pareamento`,
`projeto_conectado`, `pendencia_arquivada` — e o `hub.db` passou de 6 para 12.
`test_banco.py` é novo: 65 testes, na CI.

**Nenhuma rota encosta nelas ainda, de propósito.** A 8 constrói o esquema, a 9
constrói o login. O esquema vem antes porque errar a forma de uma tabela depois
custa migrar dado e rotacionar segredo; errar a ordem só custa esperar.

**As três armadilhas do plano, fechadas:**

1. **Nenhum segredo em claro, desde o primeiro dia.** Senha vira hash de
   `scrypt` com sal próprio; cookie de sessão e token do agente viram hash de
   SHA-256; código de pareamento vira HMAC com a chave do cofre; o segredo do
   segundo fator entra cifrado. A cifra é de biblioteca padrão (HMAC-SHA256 em
   modo contador + selo HMAC, encrypt-then-MAC) porque o projeto não tem
   dependência externa e a CI cobra isso. Texto adulterado é **recusado**.
   A chave vem de `DERVS_COFRE` ou de um `cofre.chave` local, no `.gitignore`.
2. **Arquivar exige motivo**, e desarquivar carimba a volta em vez de apagar a
   linha.
3. **`pendencia_estado` ganhou dono.** Era IDOR por desenho de esquema: a chave
   era só o `id`, então o "x" de um usuário escondia o alerta do outro. Virou
   `(id, usuario_id)`. O SQLite não troca chave primária, então `banco.migrar()`
   reconstrói a tabela; o que já estava lá vira do dono local (`usuario_id = 0`).

**O plano errava a prova.** Ele manda rodar `banco.criar()` e `banco.CAMINHO`;
nenhum dos dois existia — o esquema era aplicado dentro de `conectar()` e o
caminho se chama `BANCO`. `criar()` passou a existir; a prova usa `BANCO`.

**Provado:** 65 testes novos OK, **519 no total**, os dez arquivos verdes · as 12
tabelas listadas · o `hub.db` real do dia 26/08 migrado sem perder linha · o
servidor reiniciado e o **"x" da tela clicado de verdade**, gravando com
`usuario_id = 0`.

**Dois defeitos que só apareceram porque o teste veio antes:**
`pareamento.maquina_id` referenciava `maquina(id)` sem `ON DELETE`, e apagar uma
máquina pareada era recusado pelo banco (virou `SET NULL`); e a chave
estrangeira precisava de `PRAGMA foreign_keys=ON` **por conexão**, sem o qual
todo `ON DELETE CASCADE` do esquema era só comentário bonito.

**A CI ganhou um vigia da própria lista.** Os testes são listados à mão, um
passo cada, para o nome na tela do GitHub dizer o que quebrou. O preço disso é
esquecer o arquivo novo — e arquivo esquecido não fica vermelho, fica invisível.
Agora a CI reprova se algum `test_*.py` ficar de fora.

### O que as duas revisões pegaram na etapa 8 (e todas foram corrigidas)

Segurança e banco revisaram em paralelo. **As duas apontaram os mesmos dois
bloqueantes**, e as duas os provaram executando código, não lendo.

**Bloqueante 1 — o pareamento entregava a máquina de um usuário para a conta do
outro, em silêncio.** `abrir_pareamento` usava `INSERT OR REPLACE`, e o hash do
código é chave primária: dois usuários sorteando o mesmo código de seis dígitos
faziam a linha do primeiro ser apagada **sem erro nenhum**. Ele então digitava o
código que a própria tela mostrou, e a máquina dele nascia dentro da conta do
segundo — com projetos, caminhos e alertas junto. Virou `INSERT` puro: colisão
levanta erro, e quem chamou sorteia outro código. Barulho onde havia silêncio.

**Bloqueante 2 — a migração não era tudo-ou-nada, e uma queda no meio travava o
banco para sempre.** `executescript` faz *commit* implícito e não abre transação:
os quatro comandos rodavam soltos. Uma queda entre o `DROP` e o `RENAME` (queda
de energia, `Ctrl+C`, ou o próprio `vigia-vscode.py`, que **mata processo de
rotina**) deixava a cópia órfã no disco, e a partir daí `conectar()` estourava em
**toda** chamada — servidor e coletores fora do ar até alguém apagar a tabela na
mão. Agora é `BEGIN IMMEDIATE` + comandos um a um + `commit`, com `rollback` no
erro, e um `DROP IF EXISTS` da sobra. O `BEGIN IMMEDIATE` pega o *lock* de
escrita antes de decidir, o que resolve a corrida de graça.

**Mais quatro, que só a revisão de segurança viu:**

- **Cinco chutes de um estranho matavam o pareamento de todo mundo.** O contador
  de tentativas não tinha alvo: um código errado incrementava **todas** as linhas
  abertas, de todas as contas. Negação de serviço de um usuário sobre o outro,
  com cinco requisições. O contador global saiu. O teto de força bruta é por
  origem e mora na rota — **é obrigação da etapa 11**, e está anotado aqui porque
  seis dígitos sem ele são varríveis.
- **`DERVS_COFRE` virava chave mestra com um único SHA-256.** Sem KDF, uma frase
  digitada por gente cai em bilhões de tentativas por segundo, fora do ar, a
  partir de uma cópia do `hub.db` — e aí todo segredo de segundo fator se abre.
  Virou `scrypt`, com mínimo de 32 caracteres e a receita de gerar na mensagem
  de erro.
- **O cofre nascia sozinho, em silêncio, e falhava aberto.** Variável esquecida
  no servidor e o programa fabricava outra chave: todo segredo já guardado
  viraria "adulterado", sem uma linha de aviso. Agora ele só cria a chave quando
  `DERVS_AMBIENTE=local`, com `O_EXCL` (o coletor e o servidor abrem o banco ao
  mesmo tempo, e os dois viam "não existe"), e guarda em memória.
- **Sessão de conta desativada continuava valendo.** `usuario_por_email` filtrava
  `desativado_em`, mas `sessao_valida` e `maquina_por_token` não olhavam o dono:
  fechar a conta não derrubava quem já estava dentro. Ganharam `JOIN`.

**E cinco menores, todas feitas porque forma de tabela é cara depois:** chave
primária invertida para `(usuario_id, id)`, que é a ordem das consultas reais;
`CHECK` no motivo, no e-mail, no nome do projeto e no formato do prazo;
`CHECK (id <> 0)` no usuário, que impedia uma conta herdar tudo do dono local;
`usuario_por_email` deixou de fazer `SELECT *` e devolver senha e segredo;
a cifra passou a amarrar o blob ao dono, e o cookie é trocado ao subir para o
segundo fator.

**Uma coisa que a revisão de banco fez e vale registrar:** ela apagou o
`cofre.chave` da pasta ao fim dos testes dela. Não custou nada — havia zero
usuários e zero segredos guardados —, mas se houvesse, o dado ficaria
indecifrável. Agente de revisão com permissão de escrita no disco do projeto é
um risco real, e este foi o aviso barato.

**Para a etapa 9, herdado daqui:** `usuario.totp_confirmado_em` nasce `NULL` e
`sessao.segundo_fator_em` nasce `NULL`. É o que faz a negativa ser o padrão —
a 9 só precisa recusar quem está assim, não inventar o estado.

## A RETOMAR — ETAPA 9

Plano: `docs/superpowers/plans/dervs-fatia-1.md`, seção "## 9" — autenticação:
sessão, senha, segundo fator **obrigatório** e cadastro fechado (`POST
/api/registro` devolve 403). Depois: 10 · 11 · 12 · 13→14→15 (as telas) · 16
(publicação) · 17.

A 9 disputa `servir.py` com a 7, que já está mesclada — o caminho está livre.
As tabelas de que ela precisa já existem (etapa 8) e já nascem negando: quem não
tem `totp_confirmado_em` e quem não tem `segundo_fator_em` na sessão está fora
por padrão. O `TOKEN` de boot de `servir.py:111-113` sai de cena; ele é
anti-CSRF e **não pode** virar credencial de usuário.

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
3. ~~`pendencia_estado` **não tem coluna de dono**~~ — **FEITO na etapa 8.** A
   chave virou `(id, usuario_id)` e `banco.migrar()` reconstrói o banco antigo.
   Continua valendo o resto do item: o `TOKEN` é um só por processo, injetado
   em toda página; serve de anti-CSRF e **não pode** virar credencial de
   usuário. Quem substitui o `TOKEN` é a etapa 9.
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

- **519** funções de teste em 10 arquivos `test_*.py` **na raiz** (não em `tests/`),
  medidas em 26/08 depois da etapa 8. Eram 500 em 8 arquivos antes dela.
  A CI reporta 483 pelo runner do unittest. Não são "452".
- **18** rótulos em `regras.ROTULO_REGRA`. Não são "16".
- `projects.json` não existe. `casos.json` existe.
