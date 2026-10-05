# Plano — GitHub por conta (fase 4 da esteira)

Briefing e spec: `docs/esteira/github-por-conta/`. Escrito em 05/10/2026 a partir da
descoberta do `neguin-planner`. TDD onde há contrato: teste primeiro, vê vermelho, depois código.

## Decisões que travam o plano

1. **Sem coluna nem tabela nova.** O motivo por conta é a linha de sistema
   `projeto="_github"` (constante `banco.GITHUB_DA_CONTA`), camada `"github"`, na tabela
   `medida`, molde de `_quota`. Entra em `RESERVADOS`, senão um agente a sequestraria.
2. `falhas_de_coleta` continua global (falha da rodada inteira). O motivo por conta chega à tela
   pela chave nova `github_da_conta`. No modo por conta, `stdout` e `stderr` levam **só
   contagens e frases genéricas** (sem nome de projeto, id ou e-mail): `falhas_de_coleta`
   aparece no JSON de TODAS as contas.
3. **Modo por conta liga quando** `DERVS_AMBIENTE != "local"` **e** (`DERVS_GITHUB_APP_ID` ou
   `DERVS_GITHUB_APP_KEY` presente). Os testes atuais de `main()` rodam sem isso e seguem no
   caminho antigo. Servidor com App pela metade: grava em cada conta o motivo "o servidor está
   sem o aplicativo do GitHub configurado".
4. No modo por conta, `DERVS_GITHUB_TOKEN` e `DERVS_GITHUB_INSTALLATION_ID` são **ignorados**
   (aviso genérico, sem o valor). A instalação vem só de `banco.instalacao_do_github(uid, con=con)`.
   Cada conta ganha um `Coletor` em **variável local**, nunca em `_APP_GUARDADO`. O caminho por
   conta **não chama** `_token`, `_app`, `_gh_graphql`, `_gh_json` nem `subprocess`.
5. **Armadilhas de forma (valem para todas as etapas):**
   - `secret-scan.sh` barra `token` + (`:` ou `=`) + 16 ou mais caracteres, até em nome de
     variável. Parâmetro novo se chama `credencial`. Tokens de teste com menos de 16
     caracteres (`"ghs-conta-a"`). Nada de PEM literal: `from test_github_app import PEM_PKCS1`.
   - `test_rotas.PROIBIDO` casa `acao|exec|comando…` ("inst**acao**" casa): nenhuma rota/função
     de rota em `servir.py` com "instalacao" no nome. `EXECUTA` proíbe `coletar` alcançável de
     rota: sempre `coletar_github.x` qualificado.
   - Teste com banco declara `os.environ.setdefault("DERVS_AMBIENTE","local")` e `DERVS_COFRE`
     **antes** de `import banco`. O teste de troca de modo muda `os.environ["DERVS_AMBIENTE"]`
     dentro do caso e restaura com `addCleanup`.
   - Windows: nada de heredoc para escrever arquivo (troca o fim de linha); escreva com a
     ferramenta Write. Python é o do Windows.
   - Cada guarda nova se prova **sabotando de propósito** (veja o vermelho, depois restaure
     EDITANDO DE VOLTA, nunca `git checkout -- arquivo`). Registre no commit.
   - `test_coletar.py` troca `_gh_graphql` por `lambda q:` e `mede_deploy` por `lambda *a, **k`,
     e `banco.conta_local` por função que devolve 1: o caminho antigo mantém essas assinaturas.

## Etapa 1 — banco: linha de sistema e lista de contas

Arquivos: `banco.py`, `test_banco.py`. Contexto: `RESERVADOS` (~82), `montar_estado`
(~1701-1754), `receber_relatorio` (~3515).
- `GITHUB_DA_CONTA = "_github"` ao lado de `QUOTA`; acrescentar a `RESERVADOS`.
- `contas_com_projeto(con=None) -> list[int]`: contas ativas (`usuario.desativado_em IS NULL`)
  com camada `local` e projeto fora de `RESERVADOS`, `ORDER BY 1`.
- `montar_estado`: tirar `GITHUB_DA_CONTA` de `tudo` (como `INFRA`) e devolver
  `"github_da_conta": {"tentado_em": medido_em, **dados}` ou `None`.
Testes: (i) duas contas, só A com a linha: `montar_estado(A)` traz o motivo, `(B)` traz `None`;
(ii) `_github` não aparece em `projetos`; (iii) conta desativada fora de `contas_com_projeto`;
(iv) `receber_relatorio` com projeto `"_github"` conta como inválido.
Verifica: `python test_banco.py` e `python test_agente.py` com 0.

## Etapa 2 — `coletar_github`: núcleo HTTP com credencial explícita

Arquivos: `coletar_github.py`, `test_coletar.py`. Refatoração SEM mudar comportamento.
- `_http_com(credencial, caminho, corpo=None, teto=90)`: miolo de `_http_github` (~604-624);
  credencial vazia => `raise ValueError` antes de montar o pedido. `_http_github` vira
  `_http_com(_token(), ...)` com a mesma assinatura.
- `_ler_graphql(resposta)`: extrair as linhas ~665-712, usada por `_gh_graphql` e pela nova
  `_graphql_com(credencial, consulta)` (nunca chama `gh` nem `_token`).
- `_json_com(credencial, caminho, teto=30)`: `None` em falha.
- `mede_deploy(slug, branch, buscar=None)`: `buscar = buscar or _gh_json`.
- Extrair o corpo de gravação de `main` (~1025-1135) para
  `_gravar_medicao(con, dono, tudo, por_alias, dados, com_vulns, buscar)` -> `(gravados, reusados)`,
  sem commit. `main()` antigo a chama com `dono = banco.conta_local(con)` e `buscar=None`.
Teste novo em `test_coletar.py`: `_http_com("", "repos/a/b")` levanta sem chamar
`OpenerDirector.open`.
Verifica: `python test_coletar.py`, `python test_servidores.py`, `python test_github_app.py` com 0,
**sem editar teste existente** além do caso novo.

## Etapa 3 — a rodada por conta (critérios 2, 3, 4, 5)

Arquivos: `coletar_github.py`, `test_coletar_por_conta.py` (novo), `.github/workflows/ci.yml`
(passo `python test_coletar_por_conta.py`, perto do passo do `Coletor`, ~linha 163).
- `_modo_por_conta()` (decisão 3). `main()` desvia para `coletar_por_conta()`; resto intacto.
- `coletar_por_conta()` abre uma conexão e, para cada `uid` de `banco.contas_com_projeto(con)`:
  1. slugs de `ler_tudo(con, usuario_id=uid)` pulando `RESERVADOS`; sem slug, próxima conta.
  2. sem App no ambiente: motivo "o servidor está sem o aplicativo do GitHub configurado".
  3. `inst = banco.instalacao_do_github(uid, con=con)`; sem instalação: "esta conta não
     conectou o GitHub".
  4. `Coletor(app_id, inst, chave)` LOCAL; `cred = coletor.token()`; falhou: "o GitHub não
     entregou a chave de leitura desta conta (aplicativo desinstalado?)".
  5. `_graphql_com` com alertas; se falhar, de novo sem alertas (como ~1003-1023); falhou de novo:
     motivo = texto de `_ler_graphql` (nosso, lista branca).
  6. `_gravar_medicao(..., buscar=lambda c: _json_com(cred, c))`.
  7. `banco.gravar(GITHUB_DA_CONTA, "github", {"motivo": str|None, "medidos": n,
     "repositorios": m, "sem_alcance": [até 5 nomes + "e mais N"]}, con, usuario_id=uid)` e
     `con.commit()` **por conta**.
  8. Conta inteira em `try/except Exception`; motivo fixo "erro interno ao medir esta conta",
     SEM o texto da exceção; o laço continua.
- Retorno: 0 se mediu ao menos uma conta ou não havia conta (então imprime "NAO MEDI" genérico em
  stderr); 1 se tentou e não mediu nenhuma.
- Reescrever os comentários de dívida nomeada (~459-483, ~527-530, ~1036-1039).
Dublê de rede: troca `urllib.request.OpenerDirector.open`, registra `(url, método, Authorization,
corpo)`. `.../installations/111/access_tokens` => `{"token":"ghs-conta-a","expires_at":"2099-..."}`;
`/222` => `"ghs-conta-b"`; `graphql` monta `data` pelos apelidos e slugs do corpo;
`actions/workflows` => `{"workflows":[]}`. Ambiente do teste: `DERVS_GITHUB_APP_ID`,
`DERVS_GITHUB_APP_KEY=PEM_PKCS1`, `DERVS_GITHUB_TOKEN="env-proibido"`,
`DERVS_GITHUB_INSTALLATION_ID="999"`, `coletar_github._APP_GUARDADO` = falso cujo `token()` devolve
`"app-global"`, `coletar_github.subprocess.run` explode. Banco temporário
(`banco.BANCO = Path(tmp)/"hub.db"`, molde `test_agente.py:78-79`): conta A com `org-a/um` e
`org-a/dois`, conta B com `org-b/tres`.
Casos: **(c2)** cada GraphQL com slugs de A leva `Bearer ghs-conta-a` e só slugs de A; igual para B;
`ler_tudo(A)` tem camada `github` só nos projetos de A. **(c3)** B sem instalação, e depois B com
`access_tokens` 404: linha `_github` de B com motivo não vazio, B sem camada `github` nova, A medida
mesmo assim. **(c4)** com o token de B falhando, nenhuma chamada leva `env-proibido`, `app-global`
nem `ghs-conta-a` junto de slug de B; nada vai a `installations/999`; `subprocess` não roda.
**(c5)** capturar stdout/stderr (`contextlib.redirect_*`) e ler todas as linhas de `medida`: nenhum
token (nem o JWT das chamadas `access_tokens`) aparece; stderr sem nome de projeto de conta nenhuma.
**Guarda de código-fonte:** `inspect.getsource` de `coletar_por_conta`, `_graphql_com`, `_json_com`
não contém `_token(`, `_app(`, `_gh_graphql(`, `_gh_json(` nem `subprocess`. **Troca de modo:** com
ambiente local, `main()` não chama `coletar_por_conta` (espião); sem local e com App, chama.
Sabotagens obrigatórias: `Coletor` compartilhado entre as contas deixa (c2) vermelho; trocar
`_json_com(cred,...)` por `_gh_json` deixa (c4) vermelho.
Verifica: `python test_coletar_por_conta.py`, `test_coletar.py`, `test_servidores.py` com 0.
Depende de 1 e 2.

## Etapa 4 — teto de chamadas e prazo (critério 6)

Arquivos: `coletar_github.py`, `test_coletar_por_conta.py`. Constantes DERIVADAS, nunca digitadas:
`TETO_REPOS_POR_CONTA = 50`; `TETO_CHAMADAS_POR_CONTA = 1 + 2 + 3 * TETO_REPOS_POR_CONTA`;
`TETO_CHAMADAS_POR_RODADA = 5 * TETO_CHAMADAS_POR_CONTA`; `PRAZO_DA_RODADA = 480` s (abaixo do
`timeout=600` de `servir.py`). Contador LOCAL da rodada (nunca global do módulo) consultado por
`_graphql_com`, `_json_com` e pela obtenção do token. Repositórios além do teto: "medi N de M; o
resto passou do teto". Orçamento esgotado no meio: `mede_deploy` recebe `None` e o motivo registra
"a publicação de K projetos não foi relida". Sem saldo/prazo antes de uma conta começar: "sem
dados" com "passou do teto/tempo desta rodada".
Testes (tetos reduzidos por `setattr` + `addCleanup`, duas contas): chamadas registradas dentro do
teto; segunda conta com motivo contendo "teto"; prazo zerado => contas seguintes com motivo de
"tempo"; sabotagem (remover a checagem) deixa vermelho. Depende de 3.

## Etapa 5 — o motivo chega à tela

Arquivos: `servir.py`, `assets/painel.js`, `test_servir.py`.
- `_estado` (~910-926) acrescenta `"github_da_conta": e["github_da_conta"]`. NENHUMA rota nova.
- `painel.js` (~547-549): se `ESTADO.github_da_conta && ESTADO.github_da_conta.motivo`, esse texto
  vira o `porque` de `nada(...)`; senão o texto atual. Só `textContent`; nada de `Number(` nem
  `parseInt(` (`test_design`).
Testes em `test_servir.py` com banco de verdade e a linha `_github` só na conta A: `GET /api/dados`
com sessão de A traz o motivo; com sessão de B traz `None`. Guarda de acoplamento: `painel.js` lê
`github_da_conta` no bloco "No GitHub"; sabotagem renomeando de um lado só deixa vermelho.
Verifica: `test_servir.py`, `test_rotas.py`, `test_design.py`, `test_progresso_tela.py` com 0.
Depende de 1. Se algum teste confere o conjunto exato de chaves de `/api/dados`, ajuste-o.

## Etapa 6 — documentação (feita pelo coordenador, não pelo executor)

`CLAUDE.md` da raiz (seção "O GitHub por conta"), `docs/operacao/token-do-coletor.md:149-178`.

## Etapa 7 — fechamento

Suíte inteira (`for t in test_*.py; do python "$t" >/dev/null 2>&1 || echo "FALHOU $t"; done`),
`security-reviewer` + `python-reviewer`, `verificacao.md`. O critério 1 (ver na tela de produção)
depende da publicação pelo dono e de esperar 20+ min (a camada `github` dorme antes da 1ª rodada).

Dívida anotada: a ordem fixa por `usuario_id` faz as últimas contas passarem fome quando o teto da
rodada aperta; rodízio fica para depois.
