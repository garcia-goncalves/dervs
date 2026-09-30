# Plano — progresso pela documentação e desenvolver a partir dela

Briefing aprovado em 30/09/2026 (`docs/esteira/progresso-por-documentacao/briefing.md`).
Plano de 30/09/2026, lido contra o código (HEAD f5c5e59). **Duas frentes paralelas, sem arquivo em comum**:
Executor A (servidor, agente, testes) e Executor B (tela e documentação). Depois, etapa 3 sequencial.

## Fatos verificados no código (não redescubra)

- O agente já lê `docs/esteira/*/` em `coletar.coleta_esteira` (coletar.py:842-870) → `projetos[i]["esteiras"]` (coletar.py:1052); ninguém consome. O próprio DERVS é medido via `AVULSOS=[AQUI]` (coletar.py:184).
- O dicionário do projeto vai inteiro para `medida` como JSON (`banco.receber_relatorio`, banco.py:~3404): chave nova não pede tabela. **Projeto acima de 64 KiB é descartado INTEIRO** (banco.py:91, :3395): o agente limita o tamanho.
- Nenhum briefing tem ainda linha `- [ ]`/`- [x]`, nem marca de aprovado.
- `tarefas.NUNCA_VERDE` (tarefas.py:~215) é recusado em `pode_rodar` ANTES da aprovação: `desenvolver` NÃO entra nele (nunca rodaria); conjunto novo `SEMPRE_VERMELHA`.
- `test_rotas.PROIBIDO` casa `acao|exec|comando|shell` no caminho E no nome da função da rota: "documentACAO" casa; não nomeie rota/função `documentacao`. `_alcancaveis` reprova `compile`/`eval` alcançável de rota (nada de `re.compile` dentro de função de rota).
- `fila.erro` é o `detalhe` que desce ao agente (servir.py:~2268); `banco.enfileirar` não grava detalhe. Colunas da fila são aditivas em `_COLUNAS_SEMAFORO` (banco.py:~696) e no ESQUEMA (banco.py:~167).
- `execucao.GABARITO` (execucao.py:~152); `montar_prompt` (execucao.py:~311) passa tudo por `so_dado`.
- `test_imagem.modulos_de_runtime` segue imports a partir de `servir`: módulo novo importado pelo servidor exige `COPY` no Dockerfile. `test_imagem.PROIBIDOS` barra `execucao/fila/barreira`.
- Tela Projeto: index.html:~170-189, `pintarProjeto` painel.js:~475-614; modelo de botão `consertarComIA` (painel.js:~729-780). `test_design.NenhumNumeroSemCarimbo` exige `haQuanto(`/`hora(` em toda frase com número calculado; barra `Number(`/`parseInt(`. Menu = exatamente 4 itens.

## Desenho

1. Leitura NO AGENTE (`coletar.medir`, chave nova `documentacao` por projeto); falha fechada.
2. Parser e conta num módulo puro novo **`documentos.py`** (stdlib, sem subprocess, sem importar banco/execucao/fila/barreira). Importado por `coletar.py` (lê) e `servir.py` (conta).
3. O servidor RECALCULA a partir dos critérios crus; nunca aceita percentual do agente. A conta entra em `_estado` DEPOIS do motor e do selo; `regras.py` não lê a chave: **o selo de saúde não muda**.
4. Quatro estados: `sem_dados` (agente antigo, chave ausente), `sem_documentacao`, `nao_verificado` (há critérios, nenhuma prova rodou), `medido`. `percentual` só existe em `medido`; nos outros é `null`, nunca 0 nem 100.
5. **Provas NÃO rodam nesta entrega** (fase 2): `npm test` no Windows passa por cmd.exe; rodar suíte a cada coleta prende portas e o hub.db. Entram: o validador de lista fechada (`documentos.prova_permitida`, puro, testado com comandos hostis) e a conta pronta para receber resultado. Todo critério aparece "não verificado"; `declarados` (marcados `[x]` sem prova rodada) nunca entram em `comprovados`.
6. Fase 2 (não agora): `ExecutorProva` em agente/executor.py (registro `EXECUTORES`), regra `provar` pela fila, passa por `pode_rodar` (executa=1), roda o argv de `prova_permitida` sem shell, cwd do projeto, prazo.
7. Tarefa `desenvolver`: `tarefas.SEMPRE_VERMELHA = frozenset({"desenvolver"})`: `cor_da_regra` devolve vermelho, `pode_repintar(verde)` False. `NUNCA_VERDE` segue `{"publicar"}`. `fila.py` não muda.
8. `POST /api/desenvolver {criterio}`: acha o critério no `_estado` DA CONTA (molde de `_enfileirar_conserto`), grava cópia do texto numa coluna nova `fila.detalhe`; `_tarefa_pendente` desce `detalhe or erro`; `execucao.montar_prompt` usa `GABARITO_DESENVOLVER` quando a regra é `desenvolver`.
9. "Documento aprovado" = linha `Aprovado em: AAAA-MM-DD` no briefing (versionada no git). A trava real continua sendo o "Pode fazer".

## Formato do documento (texto IDÊNTICO ao do parser; B escreve `docs/A-DOCUMENTACAO-QUE-O-DERVS-LE.md`)

- Arquivo `docs/esteira/<slug>/briefing.md`, slug `[a-z0-9][a-z0-9-]{0,79}`.
- Seção: linha exata `## criterio_de_aceitacao` até a próxima linha `## `.
- Critério: linha `^- \[( |x|X)\] (.+)$`, sem recuo. Item numerado (`1. `) dentro da seção = erro "critério numerado não conta: use - [ ]".
- Prova (opcional) na linha LOGO ABAIXO: `^\s*Prova:\s*(.+)$`. Prova solta = erro.
- Aprovação: `^Aprovado em:\s*(\d{4}-\d{2}-\d{2})\s*$`, fora da seção.
- Tetos (cortar e marcar `cortado:true`): 30 documentos, 40 critérios por documento, texto ≤300, prova ≤200, arquivo ≤256 KiB, JSON da chave ≤24 KiB.
- Prova permitida (lista fechada): `python test_<[A-Za-z0-9_]+>.py`, `python -m pytest <relativo .py, sem .., sem absoluto>`, `npm test`. Recusa qualquer um destes: `; & | $ \` < > ( ) aspas nova-linha`.

## CONTRATO A ↔ B

**O agente sobe** (por projeto): `"documentacao": {"versao":1, "documentos":[{"slug","arquivo","aprovado_em":"AAAA-MM-DD"|"","erros":[str],"cortado":bool,"criterios":[{"n":int,"texto":str,"marcado":bool,"prova":str}]}]}`

**`GET /api/dados`**: cada projeto ganha `progresso` e perde a chave crua `documentacao`:
`{"estado":"medido"|"nao_verificado"|"sem_documentacao"|"sem_dados","percentual":int|null,"total":int,"comprovados":int,"falhos":int,"nao_verificados":int,"faltam":int,"declarados":int,"medido_em":iso|null,"documentos_n":int,"erros_n":int}`. `percentual = comprovados*100//total`; 100 só se todos comprovados.

**`GET /api/progresso?projeto=<nome>`** (acesso `dado`): 200 `{"projeto","progresso":{...igual...},"documentos":[{"slug","arquivo","aprovado_em","erros":[str],"criterios":[{"id","n","texto","marcado","prova","prova_aceita":bool,"situacao":"comprovado"|"prova_falhou"|"nao_verificado"|"falta","desenvolvivel":bool,"motivo":str}]}],"medido_em"}`; 404 `{"erro":"projeto nao encontrado"}` (mesma resposta para "não é seu"). `id` do critério = `"c"+sha256(projeto\0slug\0n\0texto)[:20]`.

**`POST /api/desenvolver {"criterio":"<id>"}`** (acesso `dado`, `_guarda_de_escrita`, balcão próprio `desenvolver`, `TETO_DE_DESENVOLVIMENTOS=10`): 200 `{"ok":true,"pedido":bool,"tarefa":"desenvolver:<uid>:<id>","aviso":str|null}`; 400 `faltou o id do criterio` / `id longo demais`; 404 `criterio nao encontrado`; 403 `documento nao aprovado` | `projeto bloqueado` | `criterio sensivel` | `criterio ja marcado`; 429 `RECUSA` padrão.

**`GET /api/tarefas`**: `nunca_verde` devolve `sorted(NUNCA_VERDE | SEMPRE_VERMELHA)`. **`POST /api/tarefas/cor`** com desenvolver/verde: 409 `a regra "desenvolver" sempre espera o seu clique, e isso nao se repinta`.

## Executor A (servidor, agente, testes)

Arquivos: `documentos.py` (novo), `coletar.py`, `servir.py`, `banco.py`, `tarefas.py`, `execucao.py`, `Dockerfile`, `.github/workflows/ci.yml` (lista `test_documentos.py`, `test_desenvolver.py` E `test_progresso_tela.py` do B), `test_documentos.py`, `test_desenvolver.py`, ajustes nos `test_*.py` existentes se a suíte pedir.
Funções: `documentos.ler_briefing(texto, slug)`, `ler_projeto(raiz)`, `prova_permitida(texto)->(bool,motivo,argv)`, `criterio_sensivel(texto)` (lista de palavras: senha, token, segredo, chave, pagamento, paciente, prontuario, autentica, login, migration, deploy, producao), `id_do_criterio`, `progresso(documentacao, projeto, medido_em, provas=None)`; `coletar.coleta_documentacao(repo)` chamada em `medir` com try/falha fechada; `tarefas.SEMPRE_VERMELHA`, `PROJETOS_SEM_DESENVOLVIMENTO` (ajudei-saude, medconsultoria, ccvp, zacareli, sophia, camargo-e-soares, aninha-site) e `projeto_pode_desenvolver(nome)` (também recusa se tiver "nexa"); `banco`: coluna `detalhe TEXT` na fila (ESQUEMA + migração aditiva) e `enfileirar` grava `detalhe`; `servir`: `_estado` põe `progresso`, `_dados` poda a chave crua, `Hub._progresso`, `Hub._desenvolver_pedir`, `_criterios_da_conta(uid, projeto)`, `_tarefa_pendente` desce `detalhe`, `_tarefa_cor` responde 409; `execucao.GABARITO_DESENVOLVER`; `Dockerfile`: `COPY documentos.py /app/` (confira o padrão de COPY real).
Testes: `test_documentos` (exemplos válidos e quebrados; 4 estados; `test_nao_verificado_nunca_entra_no_percentual`; `test_sem_documentacao_nunca_e_zero_nem_cem`; `test_comandos_hostis_recusados` com `; rm`, `&&`, `$(...)`, `..\\`, `C:\\`, aspas; `test_tamanho_cabe_no_relatorio` 50 docs × 100 critérios ≤24 KiB com `cortado`; `test_importa_sem_banco_execucao_fila` em processo novo); `test_desenvolver` (duas contas cruzadas com 404 igual; regra no corpo ignorada; não aprovado/bloqueado/"Nexa-x"/sensível = 403; balcão próprio esgota e `/api/consertar` ainda responde; `OQueOServidorEntregaSatisfazPodeRodar` para desenvolver aprovada; não repinta verde; o prompt carrega o detalhe dentro de `so_dado`; o selo não muda com e sem documentação).
Sabotagens obrigatórias (cada uma reprova ao menos um caso): somar `declarados` em `comprovados`; devolver 0 em `sem_documentacao`; tirar `;` da recusa; tirar o uid do id da fila; pôr `desenvolver` em `NUNCA_VERDE`; tirar `detalhe` de `_tarefa_pendente`; fazer o selo ler `progresso`; tirar o teto de tamanho do agente (sabote com TAMANHO); usar o balcão `consertar`.

## Executor B (tela e documentação)

Arquivos: `index.html`, `assets/painel.js`, `assets/painel.css`, `docs/A-DOCUMENTACAO-QUE-O-DERVS-LE.md` (novo), `docs/A-APLICACAO.md`, `docs/LINKS.md`, `CLAUDE.md` (seção nova curta com as armadilhas deste plano), `README.md` só se listar rotas, `test_progresso_tela.py` (novo), e `docs/esteira/progresso-por-documentacao/briefing.md` (converter `criterio_de_aceitacao` para `- [ ]` + linhas `Prova:` (só comandos da lista fechada que existem de verdade no repo; sem prova quando não houver) e acrescentar `Aprovado em: 2026-09-30` fora da seção).
painel.js: `pintarProgresso(p)` chamada de `pintarProjeto` numa `<section id="projeto-progresso">` NOVA (não como coluna do selo); `carregarProgresso(nome)` → `/api/progresso`; `linhaDeCriterio(c)`; `desenvolverCriterio(c, botao)` no molde de `consertarComIA`; `frasePorQueNaoDesenvolveu(status, corpo)` cobrindo as 4 strings 403.
Regras: texto do critério só por `textContent`; número grande só quando `estado==="medido"`; `nao_verificado` mostra "Nenhuma prova rodou ainda" + `declarados` rotulados "marcados no documento, sem prova"; toda frase com número leva `haQuanto(pr.medido_em)`; botão só atrás de `c.desenvolvivel === true`; PROIBIDO `Number(`/`parseInt(` (use `+x`), item novo no menu, e palavras de `test_design.PROIBIDAS`; `sem_documentacao` nunca escreve "%"; 360px sem rolagem horizontal; acessível por teclado. Invoque a skill `modern-web-guidance` antes de HTML/CSS/JS se tiver a ferramenta Skill.
Testes: `test_progresso_tela.py`: 4 estados mapeados; nenhum `innerHTML` em `pintarProgresso`/`linhaDeCriterio`; botão atrás de `desenvolvivel`; corpo do POST é `{criterio: c.id}`; `sem_documentacao` não escreve "%". Sabotagens: trocar para `innerHTML`; mostrar "0%" em `sem_documentacao`; tirar o `if` do `desenvolvivel`; passar `progresso` para `selo(`.

## Etapa 3 (sequencial, depois de mesclar A e B)

`test_progresso_tela.OQueATelaLeOServidorEntrega`: sobe o servidor, manda relatório com documentação por `/agente/relatorio` (nada montado à mão), lê `/api/dados` e `/api/progresso`, exige cada campo `pr.*`/`c.*` que o painel.js lê; mais um caso que lê os `docs/esteira/*` reais do DERVS e confere a conta por extenso. Depois, clique real no navegador.

## Fora desta entrega

Rodar provas (fase 2: `ExecutorProva`); migrar briefings antigos (aparecem "sem documentação"); aprovar pela tela (aprovação é a linha no arquivo).

## Riscos

Agente antigo aparece `sem_dados` até reiniciar; coluna nova da fila pede revisor de database; `TETO_USD` 3,00 e `MAX_TURNOS` 40 podem não bastar para desenvolver um critério (medir na 1ª execução, não afrouxar); `criterio_sensivel` por lista de palavras dá falso negativo (a trava real é a tarefa vermelha); qualquer um com escrita no repo aprova documento (repos são do dono).
