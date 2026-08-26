# Plano de execução — DERVS, Fatia 1 (a fundação)

Fase 4 da esteira, escrito em 26/08/2026. Contrato: `docs/esteira/dervs/briefing.md`,
`docs/esteira/dervs/spec.md` e `docs/esteira/dervs/design.md`. Onde este plano diverge
deles, a divergência está escrita com todas as letras na última seção.

## Objetivo

Fundir o `painel-projetos` e o `dervs` num repositório novo chamado `dervs`, publicado em
`dervs.com.br`, onde duas pessoas entram por login com segundo fator e veem, de cada
projeto conectado, um selo de quatro estados com a conta que o gerou. A fatia entrega
**leitura confiável e nada mais**: nenhuma rota executa comando, e o código do `dervs`
antigo — que abre terminal sem autenticação — entra no repositório já excluído do que vai
para o ar. Ao fim, `curl` sem sessão devolve 401, a verificação automática fica verde no
GitHub, e a suíte herdada roda duas vezes seguidas sem vermelho.

## O que está FORA desta fatia

- Terminal, PTY, lousa de agentes, eventos ao vivo, o Neguin — Fatia 3. **Nenhuma rota de
  execução de comando nesta fatia**, e isso é critério de aceitação com teste-vigia.
- Botão "consertar" ligado ao Claude — Fatia 2. `execucao.py` e `fila.py` **permanecem no
  repositório como módulos testados, sem nenhuma rota HTTP apontando para eles**.
- Tela de conectar conta do GitHub e conectar servidor — Fatia 2 (coletam segredo de
  terceiro; a arquitetura de segredo é portão de risco da fase 6).
- WhatsApp e Telegram — Fatia 4 (o de WhatsApp foi descartado do produto, não adiado).
- Cadastro público, cobrança, cota por usuário, isolamento entre contas de terceiros — sem
  fatia marcada. A estrutura multiusuário nasce pronta; a porta nasce fechada.
- Corrigir os três `deploy.yml` alheios (`medconsultoria`, `ccvp-painel`, `zacareli`). O
  DERVS **aponta**, não conserta.
- Página pública de marketing, `sitemap.xml`, `og.png`, dados estruturados — a aquisição
  começa na Fatia 2. Nesta fatia só entram o `robots.txt` e o `noindex` das telas
  autenticadas, que são defesa, não divulgação.
- Reescrever qualquer coisa em Node. A Fatia 1 não tem uma linha de Node.

---

## Grafo de dependências

```
 [ mão de gente ]
  1 renomear dervs -> dervs-hub (dono, site do GitHub)
        |
  2 André reaponta o remoto e confirma (André)
        |
  3 mesclar hub -> main no dervs-hub
        |
  4 criar o repo `dervs` + .gitattributes + primeiro envio  <-- portão: nada antes daqui
        |
        +-------------------+-------------------+------------------+
        |                   |                   |                  |
  5 subárvore vivo/   8 banco multiusuário  10 motor do selo  13 tokens + assets
    + exclusão do          (banco.py)          (regras.py)       (assets/)
      build                    |                                     |
        |                      |                              14 as seis telas
  6 CI escalonada              |                                 (index.html)
        |                      |                                     |
  7 tabela de rotas -----------+                              15 teste dos 8 itens
    + amputação da execução    |                                 do design
        |                      |
        +----------+-----------+
                   |
              9 autenticação (sessão + 2FA + registro 403)
                   |
        +----------+-----------+
        |                      |
  11 agente local        12 issues + drift
     + pareamento           (coletar_github.py)
        |                      |
        +----------+-----------+-------------------+
                   |                               |
             16 publicação (Dockerfile, nginx, deploy.yml)   [ mão do dono: "pode subir" ]
                   |
             17 verificação final da fatia inteira
```

**Rodam em paralelo, sem se cruzar:** `5+6` (infraestrutura de repositório) · `7→9`
(servir.py) · `8` (banco.py) · `10` (regras.py) · `12` (coletar_github.py) ·
`13→14→15` (tela). São seis trilhas com arquivos disjuntos.

**Onde há sequência forçada por arquivo compartilhado, está dito na etapa.** Os três
casos: `7` e `9` disputam `servir.py`; `13` e `14` disputam a folha de estilo e o markup;
`5` e `6` disputam a raiz do repositório recém-criado.

**Ordenação por risco:** `1–4` primeiro porque errar a ordem manda commits do André para o
repositório errado, em silêncio, e não há como saber depois. `5` e `7` em seguida porque
são as duas amputações de código perigoso — se qualquer uma escorregar, a fatia inteira
vira exatamente o que ela existe para não ser.

---

## 1. Renomear `dervs` para `dervs-hub` pelo site do GitHub

- **objetivo** — liberar o nome `dervs` sem quebrar em silêncio a máquina do André.
- **arquivos** — nenhum. É operação no GitHub.
- **depende_de** — nenhuma.
- **paralelizavel_com** — nenhuma. É o portão da migração inteira.
- **precisa_da_mao_de_alguem** — **sim, o dono**, em
  `https://github.com/garcia-goncalves/dervs/settings`, campo "Repository name" →
  `dervs-hub` → "Rename". A transferência/renomeação de repositório já foi barrada por
  automação nesta casa antes; é pelo site, e é ele quem clica.
- **como_provar** —
  `gh repo view garcia-goncalves/dervs-hub --json name,pushedAt -q '.name + " " + .pushedAt'`
  imprime `dervs-hub <data>`; e
  `gh api repos/garcia-goncalves/dervs -q .full_name` imprime `garcia-goncalves/dervs-hub`
  (o redirecionamento ainda vivo).
- **armadilha** — dar por concluída a etapa porque o segundo comando respondeu. Ele
  responde **por causa do redirecionamento**, que é justamente o que vai morrer na etapa 4.
  A prova é o primeiro comando, não o segundo.

## 2. O André reaponta o remoto da máquina dele e confirma

- **objetivo** — garantir que nenhum commit do André caia no repositório errado quando o
  nome `dervs` for retomado.
- **arquivos** — nenhum neste repositório.
- **depende_de** — 1.
- **paralelizavel_com** — nenhuma.
- **precisa_da_mao_de_alguem** — **sim, o André**, na máquina dele:
  `git remote set-url origin https://github.com/garcia-goncalves/dervs-hub.git` e depois
  `git remote -v`. Ele responde ao dono com a saída colada.
- **como_provar** — a saída de `git remote -v` do André contendo `dervs-hub.git` nas duas
  linhas (`fetch` e `push`). **Esta é a única etapa do plano cuja prova é um texto colado
  por uma pessoa**, e é assim de propósito: não há como verificar daqui o remoto da máquina
  dele.
- **armadilha** — aceitar "já reapontei" sem a saída. Enquanto o redirecionamento existir,
  o `git push` dele funciona apontando para o nome antigo, então "funcionou" não prova
  nada. O que prova é o texto do `git remote -v`.

## 3. Mesclar `hub` na `main` do `dervs-hub`

- **objetivo** — deixar um histórico só no `dervs-hub` antes de ele virar subárvore.
- **arquivos** — nenhum neste repositório; a operação é no clone do `dervs-hub`.
- **depende_de** — 2.
- **paralelizavel_com** — nenhuma.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** —
  `git -C <clone> log --oneline main..hub` sai **vazio** (nada em `hub` fora de `main`), e
  `git -C <clone> shortlog -sne main | sort -rn` lista as duas autorias, com `andgoncs`
  com no mínimo 13 commits.
- **armadilha** — usar `--squash` ou rebase "para limpar". Isso apaga a autoria do André,
  que é risco declarado no briefing ("trabalho ativo de terceiro"). Mesclagem comum, com
  commit de mesclagem, e nada de reescrita de histórico.

## 4. Criar o repositório `dervs` e fazer o primeiro envio, com `.gitattributes`

- **objetivo** — nascer o repositório novo a partir dos 69 commits do painel, já com a
  quebra de linha fixada.
- **arquivos** — repositório novo `garcia-goncalves/dervs`; `.gitattributes` (novo),
  `.gitignore` (herdado, com `hub.db` dentro), `README.md`, todo o Python e o
  `index.html` herdados, e `docs/esteira/dervs/` migrado junto.
- **depende_de** — 3. (E, transitivamente, 2: **criar o `dervs` novo antes de o André
  confirmar é o erro que este plano existe para evitar.**)
- **paralelizavel_com** — nenhuma. É o portão de todo o resto.
- **precisa_da_mao_de_alguem** — não. `gh repo create garcia-goncalves/dervs --private`
  roda daqui; o dono não precisa clicar.
- **como_provar** —
  `git -C <novo> log --oneline | wc -l` ≥ 69 ·
  `git -C <novo> check-attr text eol -- servir.py` imprime `eol: lf` ·
  `git -C <novo> ls-files --eol | grep -c 'w/crlf'` imprime `0` ·
  `git -C <novo> ls-files | grep -c '^hub.db$'` imprime `0` ·
  `gh repo view garcia-goncalves/dervs --json isPrivate -q .isPrivate` imprime `true`.
- **armadilha** — gravar o `.gitattributes` **depois** do primeiro envio. Aí o índice já
  tem CRLF gravado e a normalização vira um commit gigante que mistura conteúdo com fim de
  linha, e todo `git blame` desta casa fica inútil. O arquivo entra no **primeiro** commit
  do repositório novo, antes do `push`. Segunda armadilha: `gh repo create` sem
  `--private` — o repositório nasceria público com `hub.db` a um `git add` de distância.

## 5. Trazer o `dervs-hub` como subárvore em `vivo/`, já excluído do build

- **objetivo** — preservar o código e a autoria do André dentro do repositório novo, sem
  que uma linha dele possa chegar ao servidor.
- **arquivos** — `vivo/` (subárvore inteira), `.dockerignore` (novo), `Dockerfile` (novo,
  estágio de cópia explícito), `vivo/LEIA-ANTES.md` (novo).
- **depende_de** — 4.
- **paralelizavel_com** — 8, 10, 13. **Não** com 6: as duas mexem na raiz do repositório
  recém-criado e a 6 precisa saber que `vivo/` existe para ignorá-lo.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** — no **mesmo commit**:
  `git -C <novo> show --stat HEAD | grep -c '^ vivo/'` > 0 **e**
  `git -C <novo> show HEAD:.dockerignore | grep -c '^vivo/'` = 1. Depois,
  `docker build -t dervs-teste . && docker run --rm dervs-teste sh -c 'ls /app | grep -c vivo || true'`
  imprime `0`, e
  `docker run --rm dervs-teste sh -c 'grep -r "dangerously-skip-permissions" /app | wc -l'`
  imprime `0`.
- **armadilha** — trazer a subárvore num commit e excluí-la do build no commit seguinte.
  Entre os dois commits existe uma etiqueta possível, e foi exatamente assim que três
  `deploy.yml` desta casa foram parar publicando sozinhos. **Um commit só.** Segunda
  armadilha: confiar no `.dockerignore` sem construir a imagem — `.dockerignore` não vale
  para `COPY --from` nem para contexto remoto, e a prova é o `ls` dentro do container.

## 6. Verificação automática escalonada no repositório novo

- **objetivo** — a CI do `dervs` roda os 8 arquivos de teste herdados e fica verde, sem
  estourar a cota de minutos.
- **arquivos** — `.github/workflows/ci.yml` (adaptado do atual), `.github/dependabot.yml`
  ou `renovate.json` (herdado).
- **depende_de** — 5.
- **paralelizavel_com** — 8, 10, 13.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** —
  `gh run list --repo garcia-goncalves/dervs --limit 1 --json conclusion,event -q '.[0].conclusion + " " + .[0].event'`
  imprime `success push` · `grep -c 'workflow_run' .github/workflows/*.yml` imprime `0` ·
  `grep -c 'paths-ignore' .github/workflows/ci.yml` ≥ 1 ·
  `grep -c 'vivo/' .github/workflows/ci.yml` ≥ 1 (o Node do `vivo/` não é compilado nem
  testado nesta fatia).
- **armadilha** — copiar o `ci.yml` do painel sem tocar nos caminhos, e ele passar verde
  **porque não está rodando nada**. Prove pelo número: a saída do job tem de conter as 8
  linhas de teste. E não caia na tentação de paralelizar os 8 testes em 8 jobs: a cobrança
  é por tarefa arredondada, e isso multiplica a conta por 8 para economizar 40 segundos de
  parede.

## 7. Tabela de rotas em `servir.py`, e a amputação da execução

- **objetivo** — trocar a cadeia de `if self.path…` por um registro de rotas enumerável, e
  remover desse registro toda rota que executa comando.
- **arquivos** — `servir.py` (remove `/api/acao`, `/api/execucao`, o proxy do grafo em
  `servir.py:537-748`, `ACOES`, `ACOES_SEM_PROJETO`, `caminho_do_grafo`), `test_servir.py`
  (os testes do proxy saem junto), `test_rotas.py` (**novo — o teste-vigia**).
  `execucao.py` e `fila.py` **não são tocados**: continuam no repositório, continuam com
  seus 183 testes verdes, e ficam sem nenhuma rota apontando para eles.
- **depende_de** — 4.
- **paralelizavel_com** — 5, 6, 8, 10, 13.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** —
  `python test_rotas.py` imprime `OK` (o teste importa `servir`, lê `servir.ROTAS`, e
  reprova se qualquer padrão casar com `acao|execucao|exec|terminal|pty|shell|comando|grafo`) ·
  `python -c "import servir; print(sorted(servir.ROTAS))"` não imprime nenhuma dessas ·
  `grep -c 'ACOES' servir.py` imprime `0` ·
  `python test_servir.py && python test_execucao.py && python test_fila.py` os três
  imprimem `OK`.
- **armadilha** — o teste-vigia varrer **texto do arquivo** em vez do registro em memória.
  Uma rota registrada por concatenação (`"/api/" + nome`) passaria despercebida por
  `grep`. O vigia importa o módulo e itera a estrutura de verdade — e falha, de propósito,
  se `ROTAS` não existir, para que ninguém "resolva" o teste apagando a tabela. Segunda
  armadilha: apagar `execucao.py` e `fila.py` "já que não têm rota" — isso apaga 183
  testes herdados e a trava de diff de `fila.py:229`, que é uma das duas defesas do
  produto para a Fatia 2.

## 8. Banco multiusuário, pareamento e arquivamento permanente

- **objetivo** — as tabelas que faltam para o produto deixar de ser de uma máquina só.
- **arquivos** — `banco.py` (acrescenta `usuario`, `sessao`, `maquina`, `pareamento`,
  `projeto_conectado`, `pendencia_arquivada`, sem tocar nas 6 tabelas existentes),
  `test_banco.py` (novo).
- **depende_de** — 4.
- **paralelizavel_com** — 5, 6, 7, 10, 13.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** —
  `python test_banco.py` imprime `OK` ·
  `python -c "import banco,sqlite3;banco.criar();print(sorted(r[0] for r in sqlite3.connect(banco.CAMINHO).execute(\"select name from sqlite_master where type='table'\")))"`
  lista as 12 tabelas ·
  `python test_memoria.py && python test_regras.py` continuam `OK` (as 6 tabelas antigas
  não mudaram de forma).
- **armadilha** — guardar o segredo do segundo fator ou o token do agente **em claro** na
  tabela, "porque a cifragem é da etapa 9". A tabela nasce guardando hash do token e
  segredo cifrado; retroencaixar isso depois exige migração de dado e uma rotação de
  segredo. Segunda armadilha: `pendencia_arquivada` sem coluna de motivo e data — o
  arquivamento permanente sem rastro é pior que o silêncio de 24 h que ele substitui.

## 9. Autenticação: cortina, entrar com GitHub, cadastro fechado

> **REESCRITA EM 26/08/2026, ANTES DE COMEÇAR.** O dono pediu entrada disfarçada e login
> sem senha, com a intenção declarada de vender o DERVS um dia. O desenho aprovado está em
> `docs/superpowers/specs/2026-08-26-login-cortina-github-design.md` — **leia aquele
> arquivo, não o texto abaixo**. O que muda: identidade passa a vir do GitHub (OAuth);
> `GET /` vira cortina com combinação de seis dígitos conferida no servidor; senha e TOTP
> saem de colunas da `usuario` e viram linhas numa tabela `credencial` nova, o que deixa
> chave de acesso (*passkey*) entrar na Fatia 2 como acréscimo em vez de reescrita; senha +
> TOTP ficam como porta de emergência desligada. O que **não** muda: cadastro fechado (403),
> negativa por padrão em toda rota de dado, e a mesma resposta para toda rejeição.
>
> O texto original segue abaixo por honestidade de histórico. A etapa ficou maior e pode
> quebrar em 9a (banco + cortina) e 9b (OAuth + sessão) durante a implementação; o grafo de
> dependências aguenta, porque as trilhas são disjuntas por arquivo.

- **objetivo** — nenhuma rota de dado responde sem sessão com segundo fator conferido.
- **arquivos** — `servir.py` (camada de sessão em cima da tabela de rotas da etapa 7;
  substitui o `TOKEN` por boot de `servir.py:111-113`), `autenticacao.py` (novo, TOTP em
  biblioteca padrão: `hmac` + `hashlib` + `base64`, sem dependência externa),
  `test_autenticacao.py` (novo).
- **depende_de** — 7 e 8. **Sequencial com a 7 por disputa de arquivo:** as duas reescrevem
  o despacho de `servir.py`, e resolver o conflito de mesclagem entre "tabela de rotas" e
  "camada de sessão" custa mais que esperar.
- **paralelizavel_com** — 10, 12, 13, 14.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** —
  `python test_autenticacao.py` imprime `OK`, cobrindo os quatro casos do critério:
  (a) requisição sem sessão a cada rota de `servir.ROTAS` marcada como de dado devolve 401
  ou 302 e **corpo sem nenhum nome de projeto**; (b) conta com senha correta e **sem**
  segundo fator configurado recebe 403 em toda rota de dado; (c) `POST /api/registro`
  devolve 403; (d) nenhuma resposta da API contém o segredo TOTP nem o token do agente —
  o teste varre o JSON inteiro atrás dos valores gravados.
- **armadilha** — a lista de rotas protegidas ser escrita à mão e nascer desatualizada na
  primeira rota nova. O teste itera `servir.ROTAS` e **falha em rota sem classificação
  declarada** — nega por padrão, inclusive no teste. Segunda armadilha: mensagem de erro
  que diz qual campo errou; o design exige "E-mail ou senha não conferem", sem dizer qual,
  porque o contrário entrega quais e-mails existem.

## 10. Motor do selo: quatro estados, e o que acontece quando o agente cala

- **objetivo** — o selo passa a ter o estado "sem dados", e ausência de medição nunca vira
  verde nem vermelho.
- **arquivos** — `regras.py` (nova função `selo_do_projeto()`; `abandonado`, `caso_vazio`,
  `grafo_velho` e `memoria_crlf` saem do cálculo do selo; `agrupar()` passa a respeitar
  arquivamento permanente), `test_regras.py`.
- **depende_de** — 8 (a tabela `pendencia_arquivada`).
- **paralelizavel_com** — 5, 6, 7, 9, 12, 13.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** —
  `python test_regras.py` imprime `OK` com casos novos que provam, um a um:
  projeto sem nenhuma camada medida → `sem_dados` (**nunca** `saudavel`); camada local com
  carimbo de 20 minutos atrás → os critérios de máquina viram `sem_dados` e os de GitHub
  seguem; pendência arquivada permanentemente não reaparece na coleta seguinte; e
  `abandonado`/`caso_vazio`/`grafo_velho`/`memoria_crlf` não alteram o selo. Mais:
  `python -c "import regras;print(regras.selo_do_projeto({}))"` imprime `sem_dados`.
- **armadilha** — a mentira por omissão já catalogada: calcular o selo como "não há
  pendência aberta ⇒ verde". Sem camada medida não há pendência **e** não há saúde. A
  pergunta de revisão desta etapa é a mesma que salvou o porte para Linux: *este valor de
  retorno é distinguível de uma medição real?* Se não for, é `None`, e o `None` sobrevive
  até a tela.

## 11. Agente local `dervs-agent` e o pareamento por código de seis dígitos

- **objetivo** — a máquina do dono reporta git, Docker, portas e chaves de `.env` para a
  VPS, sem escutar porta nenhuma.
- **arquivos** — `agente/` (novo pacote, extraído de `coletar.py` — as ~600 linhas que
  medem projeto), `agente/enviar.py`, `servir.py` (uma rota nova de ingestão, autenticada
  por token de máquina, declarada na tabela da etapa 7), `test_agente.py` (novo).
  `coletar.py` continua no repositório enquanto o agente não substituir a coleta local.
- **depende_de** — 9.
- **paralelizavel_com** — 12, 13, 14, 15.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** —
  `python test_agente.py` imprime `OK`, provando: código de 6 dígitos vence em 10 minutos;
  código usado não serve duas vezes; token escapado a um usuário **e** uma máquina;
  relatório com token de outra máquina recebe 403. E, de ponta a ponta,
  `python -m agente.enviar --alvo http://127.0.0.1:4777 --codigo <seis dígitos>` seguido de
  `curl -s -b sessao.txt http://127.0.0.1:4777/api/maquinas | python -m json.tool | grep visto_em`
  mostrando carimbo com menos de 2 minutos.
- **armadilha** — inventar um endpoint separado de "sinal de vida". O envio de dado **é** o
  sinal; um sinal separado permite a máquina parecer viva enquanto a medição está parada,
  que é a pior mentira possível neste produto. Segunda armadilha: o agente devolver lista
  vazia quando o `docker` não está instalado — vazio e `None` dizem coisas opostas, e essa
  é exatamente a família de defeito corrigida em `7b4221c`, `3f5aa40` e `c50fe1d`.

## 12. Issues abertas do GitHub, e o drift entre servidor e GitHub

- **objetivo** — entregar o "eu sei o que falta" e o diferencial defensável do produto, o
  drift, medido pelo servidor e não pela máquina do dono.
- **arquivos** — `coletar_github.py` (issues abertas na mesma consulta única já existente;
  `coletar_github.py:244` deixa de depender do `gh` logado e passa a usar credencial de
  aplicativo do GitHub), `regras.py` **não é tocado** — a regra `nao_publicado` já existe.
- **depende_de** — 9 (a credencial vive na tabela da etapa 8, atrás de sessão).
- **paralelizavel_com** — 11, 13, 14, 15.
- **precisa_da_mao_de_alguem** — não, **se** a credencial de aplicativo já existir. Se não
  existir, **sim: o dono** cria o GitHub App em `github.com/settings/apps` e instala na
  organização — só ele pode.
- **como_provar** —
  `python coletar_github.py --projeto ajudei-saude --so-medir | python -m json.tool | grep -E 'nao_publicado|commits_atras'`
  imprime `10` ou mais, com data `11/08/2026`; e
  `python -c "import coletar_github as c;print(c.issues_abertas('ajudei-saude'))"` devolve
  lista (possivelmente vazia) e **nunca** `[]` por falha — falha devolve `None`.
  `python test_coletar.py && python test_coletar_pesado.py` continuam `OK`.
- **armadilha** — fazer duas consultas por repositório, como o `dervs` antigo fazia. A cota
  da conta já estourou uma vez; o painel faz **uma** consulta para todos os repositórios e
  esse padrão se mantém. Segunda armadilha: contar o drift comparando etiquetas em vez de
  commits — o servidor guarda o código antigo (é a lição do commit `c2ceb35`), e comparar a
  etiqueta faz a conferência mentir.

## 13. Tokens, folha de estilo e assets

- **objetivo** — a paleta preto/branco/verde do design existir como token antes de
  qualquer tela.
- **arquivos** — `assets/dervs.css` (novo: os 15 tokens de cor nos três blocos de tema, a
  escala tipográfica, espaçamento, raio de 3px), `assets/logo.svg`, `assets/favicon.svg`,
  `assets/favicon-180.png`, `assets/selos.svg`, `assets/CREDITOS.md`, `assets/fontes/`
  (IBM Plex Sans e Mono, subconjunto latino, OFL 1.1, servidas do próprio domínio),
  `servir.py` **não é tocado** — o `ESTATICOS_OK` ganha `assets/` na etapa 14.
- **depende_de** — 4.
- **paralelizavel_com** — 5, 6, 7, 8, 9, 10, 11, 12.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** —
  `python docs/esteira/dervs/contraste.py` recalcula a tabela e imprime todos os pares
  ≥ 4,5:1 (texto) e ≥ 3:1 (`--borda-forte`), sem nenhuma linha `REPROVA` ·
  `grep -c 'oklch(\|rgb(' assets/dervs.css` imprime `0` ·
  `python -c "import re;t=open('assets/dervs.css',encoding='utf-8').read();print(len(re.findall(r'--[a-z-]+:',t)))"`
  ≥ 30 · `ls assets/fontes/*.woff2 | wc -l` ≥ 2.
- **armadilha** — usar verde como cor de destaque em qualquer lugar fora do selo. É a regra
  dura deste projeto: `--acao` é quase-preto no tema claro e quase-branco no escuro, e é
  ela que carrega botão, link, foco e cabeçalho. Verde é o estado saudável; se ele virar
  cor de marca, o selo verde para de significar alguma coisa no dia em que mais importa.

## 14. As seis telas, em português

- **objetivo** — Entrar, Painel, Projeto, Conectar projeto, Máquinas e Alerta, na direção
  Torre de Controle, funcionando em 360px e nos dois temas.
- **arquivos** — `index.html` (reescrito: markup, os quatro selos com cor+forma+glifo+
  rótulo, a frase de resumo, a lista de linha cheia; as 26 cores literais de hoje somem em
  favor de `var(--…)`), `servir.py` (só o `ESTATICOS_OK` ganhando `assets/`, uma linha),
  `robots.txt` (novo: bloqueia `/painel`, `/projeto`, `/maquinas`, `/api`).
- **depende_de** — 13. **Sequencial por disputa de arquivo:** as duas escrevem CSS, e uma
  tela escrita antes dos tokens nasce com cor literal — que é o defeito nº 1 da lista de
  verificação do design.
- **paralelizavel_com** — 11, 12.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** —
  `grep -coE '#[0-9a-fA-F]{3,8}|rgb\(|oklch\(' index.html` imprime `0` ·
  `grep -c 'noindex' index.html` ≥ 1 ·
  `python -c "import re;h=open('index.html',encoding='utf-8').read();print(len(re.findall(r'data-selo=\"(saudavel|atencao|quebrado|sem_dados)\"',h)))"`
  ≥ 4 · e a prova visual, que é o item 5 do design: com o servidor de pé,
  `python -m agente.enviar --demonstracao` e a tela em 360×640 mostrando 10 projetos sem
  rolagem — conferida **clicando no selo**, não olhando a faixa: `Ver o que gerou este
  selo` tem de abrir a prova.
- **armadilha** — dar a tela por pronta porque ela **aparece** certa. Já aconteceu nesta
  casa: a faixa da fila apareceu e o botão nunca disparava. Cada botão do design
  (`Medir agora`, `Isto está certo assim`, `Ver todos`) é clicado uma vez antes de a etapa
  fechar. Segunda armadilha: palavra em inglês escapando — `dashboard`, `deploy`,
  `loading`, `deletar`, `login` estão todas no vocabulário proibido do design.

## 15. O teste dos oito itens verificáveis do design

- **objetivo** — transformar a lista "Como esta fase se prova" do `design.md` em teste que
  roda na CI.
- **arquivos** — `test_design.py` (novo), `.github/workflows/ci.yml` (uma linha de job).
- **depende_de** — 14.
- **paralelizavel_com** — 11, 12.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** — `python test_design.py` imprime `OK`, com um caso por item: (1) nenhuma
  cor literal fora do bloco de tokens; (2) nenhum `--estado-*` em regra de botão, link,
  navegação ou cabeçalho; (3) todo par de contraste recalculado, reprovando abaixo de
  4,5:1 / 3:1; (4) nenhuma cor definida só dentro de um bloco de tema; (6) nenhuma palavra
  da lista de vocabulário proibido no texto visível; (7) todo estado de selo com cor, forma,
  glifo e rótulo no HTML; (8) nenhum número em tela sem o carimbo da medição.
  Os itens 5 e o clique do 14 continuam sendo olhada humana — **e o teste diz isso na
  própria saída**, listando "2 itens desta lista não são automatizáveis".
- **armadilha** — escrever o item 8 como busca de texto e ele passar vazio porque não achou
  número nenhum. Teste que não encontra o que deveria examinar **passa por engano**: o caso
  começa afirmando que há pelo menos 20 números na tela, e só então verifica os carimbos.

## 16. Publicação: imagem, porteiro de site e workflow de publicação

- **objetivo** — o DERVS de pé em `dervs.com.br`, publicado por botão e só por botão.
- **arquivos** — `Dockerfile` (finalizado; `vivo/` já fora desde a etapa 5),
  `docker-compose.yml` (novo; **sem** `dervs-live`), `infra/nginx-dervs.conf` (novo, no
  molde do `nukleoa.com.br`: container em porta alta de `127.0.0.1`, proxy reverso do
  host), `.github/workflows/publicar.yml` (novo: `workflow_dispatch` e só ele, palavra
  `PUBLICAR` digitada, `cancel-in-progress: false`, job que cria a etiqueta).
- **depende_de** — 6, 9, 11, 12, 15.
- **paralelizavel_com** — nenhuma.
- **precisa_da_mao_de_alguem** — **sim, o dono**, em dois pontos: (a) gravar os segredos do
  repositório (chave de acesso à VPS usada **pelo workflow**, nunca pelo laptop) — só ele
  os tem; (b) dizer "pode subir" antes do primeiro `gh workflow run`. O sinal vale para o
  lote, não para cada commit.
- **como_provar** —
  `grep -cE '^\s*(push|workflow_run):' .github/workflows/publicar.yml` imprime `0` ·
  `python -c "import yaml,sys;d=yaml.safe_load(open('.github/workflows/publicar.yml'));print(list(d[True]))"`
  imprime `['workflow_dispatch']` ·
  `curl -si https://dervs.com.br/api/projetos | head -1` devolve `401` ou `302` ·
  `curl -s https://dervs.com.br/robots.txt | grep -c '/api'` ≥ 1 ·
  `gh release list --repo garcia-goncalves/dervs --limit 1` mostra a etiqueta criada pelo
  próprio workflow.
- **armadilha** — `ssh`, `scp`, `rsync` ou `docker compose` apontados para o servidor
  saindo desta máquina. O deploy roda no GitHub, sempre. Segunda armadilha, específica
  desta VPS: ela **não é terreno limpo** — 26 containers servindo 8 sistemas. Publicar numa
  porta já ocupada, ou reescrever um arquivo de `/etc/nginx/sites-enabled/` que é de outro
  site, derruba um sistema que não tem nada a ver com esta esteira. Um arquivo novo, porta
  alta nova, e conferir a porta antes.

## 17. Verificação final da fatia

- **objetivo** — rodar o critério de aceitação inteiro, de uma vez, e só então dizer pronto.
- **arquivos** — `docs/esteira/dervs/verificacao.md` (novo: a saída de cada comando, colada).
- **depende_de** — 16.
- **paralelizavel_com** — nenhuma.
- **precisa_da_mao_de_alguem** — não.
- **como_provar** — os oito comandos, nesta ordem, com a saída colada no arquivo:
  1. `curl -si https://dervs.com.br/api/projetos | head -1` → `401` ou `302`
  2. `python test_autenticacao.py` → `OK` (403 sem segundo fator, 403 no registro)
  3. `python test_rotas.py` → `OK`
  4. `grep -rn "dangerously-skip-permissions" $(git ls-files | grep -v '^vivo/') | wc -l` → `0`,
     **e** a mesma busca dentro da imagem publicada → `0`
  5. `for i in 1 2; do for t in test_*.py; do python $t || exit 1; done; done; echo DUAS-CORRIDAS-OK`
     → `DUAS-CORRIDAS-OK` (duas corridas seguidas; a segunda pega o teste que passa por
     sorte lendo banco real)
  6. `gh run list --repo garcia-goncalves/dervs --limit 1 --json conclusion -q '.[0].conclusion'` → `success`
  7. `curl -s -b sessao.txt https://dervs.com.br/api/maquinas | grep visto_em` → carimbo
     com menos de 2 minutos
  8. `python test_design.py` → `OK`
- **armadilha** — escrever "tudo verificado" com a saída de meia dúzia dos oito. Falha se
  relata com a saída junto, e sucesso também. O arquivo de verificação existe para que
  daqui a um mês ninguém precise acreditar em mim.

---

## O que este plano NÃO resolve

- **Não sei ainda qual biblioteca de segundo fator.** A etapa 9 escolhe TOTP em biblioteca
  padrão (`hmac`/`hashlib`/`base64`) porque a CI deste repositório **reprova a existência
  de qualquer arquivo de dependência**, e a recomendação da spec — chave de acesso — depende
  do SimpleWebAuthn, que é Node e não cabe no núcleo Python. Isso é um degrau abaixo do que
  a spec recomendou, e está aqui declarado, não escondido. Chave de acesso volta na Fatia 2.
- **A dúvida 4 continua aberta:** onde vivem hoje os segredos do servidor. A etapa 16 grava
  segredo novo no repositório sem saber se ele já existe em outro lugar — risco de segredo
  duplicado em dois cofres, que é como rotação vira caçada.
- **Nada aqui prova que o produto é bom.** O plano prova que a leitura é confiável e que
  não há shell exposto. Se o dono abrir a tela às 5 da manhã e ela não responder "posso
  confiar no que está no ar" em cinco segundos, todos os 17 `como_provar` continuam verdes
  e o produto falhou assim mesmo.
- **O `vivo/` fica no repositório sem ninguém entender o que tem dentro.** A etapa 5 o
  isola; nenhuma etapa o lê. Quando a Fatia 3 abrir aquela pasta, os 12 pontos que executam
  comando e os 11 que escrevem em disco vão estar exatamente onde estavam, com zero testes.
- **A estimativa de esforço não existe.** Nenhuma etapa tem prazo, e três delas (7, 9, 14)
  são visivelmente maiores que as outras. Se alguma precisar quebrar em duas durante a
  fase 5, o grafo aguenta — as trilhas são disjuntas por arquivo, e é por isso que estão
  desenhadas assim.
- **A migração do dado que já existe não foi planejada.** O `hub.db` de hoje tem histórico,
  vida de pendência e gasto acumulado. O plano cria o esquema novo (etapa 8) e não diz o
  que acontece com o banco antigo. Provavelmente a resposta certa é "nada, começa vazio",
  mas é uma decisão de produto que não é minha.
