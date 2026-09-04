# Plano de execução — Servidores múltiplos

Fase 4 da esteira, escrito em 04/09/2026. Contrato: `docs/esteira/servidores-multiplos/briefing.md`, `spec.md` e `design.md`, os três aprovados e validados. As contradições já resolvidas na spec **não se reabrem**. Direção visual "Torre de Controle" (`docs/esteira/dervs/design.md`): aprovada, não reaberta.

## Contexto verificado pelo planner

- `endereco_producao` é exatamente como o Arquiteto descreveu: `banco.py:384-393`, `UNIQUE (usuario_id, projeto)`, índice `ix_endereco_dono`, comentário de IDOR em `:367-383`.
- **Só três consumidores** das funções de endereço fora dos testes: `coletar.py:1002`, `coletar_github.py:966`, `servir.py:1593/1613/1641`. `endereco_de_producao` (singular, `banco.py:2989`) **não tem nenhum consumidor de produção** — só `test_banco.py:2081`.
- `regras.py:201` lê `site` singular; `_p()` (`regras.py:49-70`) já tem o parâmetro `sufixo`, e o id é `regra:projeto[:sufixo]`. `test_regras.ADocumentacaoNaoPodeMentir.test_nenhuma_regra_repete_o_nome` exige que `"site_fora"` apareça **uma vez só** no fonte — a emissão por servidor tem de ser um `_p(` dentro de laço.
- `servir.ROTAS` casa **caminho → um verbo só** (`servir.py:2757-2831`). O spec escreveu `GET /api/servidores` e `POST /api/servidores`: **isso não cabe na tabela** — é a única divergência de contrato deste plano, resolvida com caminhos separados no padrão de `/api/maquinas*`.
- `test_rotas.PROIBIDO` (`acao|execucao|exec|terminal|pty|shell|comando|grafo`) e `EXECUTA` (contém `coletar`, casamento exato) **não barram** nenhum dos nomes propostos; `coletar_github` não casa `coletar`.
- **Não existe runtime de JS neste repositório** (nenhum `node`/`npm`/`jsdom` no `ci.yml`): `assets/painel.js` só é verificado como texto (`test_design.PAINEL_JS`). "O selo lista os dois nomes" não é provável por teste automatizado no DOM — a prova automatizada para no dado, e o clique fica para a fase 6.
- Custo real de `mede_site`: `PRAZO_DO_DNS=5` + `TENTATIVAS_SITE=2` × `TETO_SITE=8` + `PAUSA_ENTRE_TENTATIVAS=1.5` ≈ **22,5 s de pior caso por endereço**, numa thread do servidor.
- Linha de base medida, HEAD `b3342fc`, tudo verde: `test_banco` 241 · `test_servir` 227 · `test_coletar` 201 · `test_regras` 105 · `test_rotas` 34 · `test_design` 33.
- **Premissa do spec que não se confirmou:** `coletar.py:989-1021` não precisa da mesma mudança de forma — ali `url_prod` alimenta a régua de prontidão (`coleta_prontidao`, via `coletar.py:669`), não o selo de "no ar". Fica singular, com nome novo e honesto.

## Riscos

- **A migração toca dado real em produção.** `endereco_producao` tem linhas no ar desde 01/09. O SQLite não troca `UNIQUE` nem acrescenta FK `NOT NULL` sem reconstruir a tabela. `hub.db` é descartável **no laptop**, **no servidor não é** — por isso a etapa 1 exige um caso que sabota (roda a migração num banco com N linhas e conta N depois) antes de qualquer publicação.
- **Trocar o id da pendência quebra o silêncio já dado.** `site_fora:X` vira `site_fora:X:<servidor_id>`; um silêncio ativo em `pendencia_estado` fica órfão e a pendência reaparece. Aceitável — silêncio tem prazo máximo de 30 dias — mas tem de estar escrito no commit.
- **`sugerir` pode prender uma thread por ~68 s** (3 × 22,5 s). Teto próprio de balcão e limite de 3 candidatos por chamada; nunca reusar `TETO_DE_ENDERECOS`.
- **Fixture de teste divergindo do produtor real** — a lição de "Suíte verde, funcionalidade morta". A etapa 5 é obrigada a conter o caso que pega o `sites` que o **coletor de verdade** monta e o passa por `regras.avaliar`.
- **Worktree paralela perde trabalho** (`CLAUDE.md`, 02/09). Desfaça sabotagem editando de volta, nunca com `git checkout -- <arquivo>`; não remova worktree alheia.

## Objetivo

"O seu servidor" deixa de ser um endereço solto por projeto e vira um **cadastro de servidores nomeados**, cada um com os próprios endereços por projeto. O mesmo projeto responde em mais de um servidor ao mesmo tempo, e o card diz **em quais** — nunca um selo genérico fundindo computador, GitHub e servidor.

**As travas que não se tocam:**

- **A peneira anti-SSRF é reusada, nunca copiada.** Toda rota nova chama `coletar_github.url_segura`, `coletar_github.enderecos_publicos`, `coletar_github.host_publico` e `coletar_github.mede_site` **qualificadas**. Nenhum `from coletar_github import`. (`servir.py:78-87`, `test_rotas.EXECUTA`.)
- **Biblioteca padrão pura.** Nada de `requirements.txt` nem `pyproject.toml`. O casamento de padrão é `fnmatch` da stdlib.
- **Nenhuma rota nova aceita, grava, loga ou pede senha, chave, token ou segredo de acesso a servidor.** Só endereço público e nome.
- **Falha fechada em caminho de autorização:** servidor que não é da conta devolve `False`/404 com a **mesma resposta** de "não existe". Nunca levanta.
- **Teto de balcão próprio por rota nova.** `TETO_DE_ENDERECOS` não é emprestado (`servir.py:1581-1586`).
- **O painel não pode mentir.** `ok=None` continua sendo "não medi", por servidor, e nunca apaga um "fora do ar" real medido antes.

## O que está FORA

Do briefing, não reaberto: SSH/varredura por credencial · correção automática ou escrita no servidor · saúde do servidor (CPU/disco/memória/containers) · "zero pendência" como critério.

Acrescentado por este plano, com motivo:

- **Renomear servidor pela tela.** Cadastrar e apagar bastam para o critério de aceitação; renomear exigiria reescrever ids de pendência já gravados. Dívida nomeada.
- **Vários ambientes por projeto no mesmo servidor** (staging + produção). O `UNIQUE (usuario_id, servidor_id, projeto)` fecha isso de propósito, e a dívida já estava nomeada no plano das três portas.

## Divergências do contrato, com todas as letras

1. **`spec.md` pediu `POST /api/servidores` e `GET /api/servidores`.** `servir.ROTAS` é um dicionário caminho → `Rota(verbo, função, classe)`: um caminho só admite um verbo. Vira `GET /api/servidores`, `POST /api/servidores/guardar`, `POST /api/servidores/remover` — o mesmo padrão de `/api/maquinas`, `/api/maquinas/parear`, `/api/maquinas/remover`.
2. **`spec.md` disse que `coletar.py:989-1021` precisa da mesma mudança de forma.** Não precisa. Ali `url_prod` é a régua de prontidão (`coletar.py:669`), não o selo de "no ar". Fica singular, com nome que confessa isso (`um_endereco_por_projeto`).
3. **O sufixo do id da pendência é o `servidor_id`, não o nome do servidor.** O nome entra na frase; o id não pode depender dele (renomear trocaria o id, e nome + projeto pode estourar o teto de 200 caracteres de `_id_de_pendencia`).
4. **`design.md` implica que a sugestão de autodetecção aparece sozinha.** Ela aparece sozinha, sim, mas por uma leitura assíncrona **uma vez por servidor por sessão** — não a cada repintura. Medir 3 endereços custa até 68 s de thread; repetir isso a cada repintura da tela seria um coletor disfarçado de tela.

---

## Grafo de dependências

```
onda 0   E1 banco: tabela `servidor` + migracao      ‖   E2 regras: uma pendencia por servidor
              (banco.py, test_banco.py)                    (regras.py, test_regras.py)
                     |                                              |
onda 1   E3 banco: funcoes de acesso por servidor               (pronta)
              (banco.py, coletar.py, coletar_github.py 1 linha, test_banco.py)
                     |
onda 2   E4 servir: as rotas   ‖  E5 coletar_github: `sites`  ‖  E6 painel: card + detalhe
         (servir.py,              (coletar_github.py,            (painel.js, painel.css,
          test_servir.py,          test_servidores.py NOVO,       test_design.py)
          test_rotas.py)           ci.yml)
                     \                    /                              |
onda 3   E7 painel: a tela "Conectar projeto"    ‖   E8 autodeteccao: helper + rota
              (painel.js, painel.css, test_design.py)   (coletar_github.py, servir.py,
                     |                                   test_servidores.py, test_servir.py)
                     \____________________  ____________________/
onda 4                     E9 a sugestao na tela
                        (painel.js, painel.css, test_design.py)
                                    |
onda 5              E10 documentacao e verificacao
```

**Os arquivos que serializam:** `banco.py` (E1→E3) · `assets/painel.js` + `painel.css` + `test_design.py` (E6→E7→E9) · `servir.py` (E4→E8) · `coletar_github.py` (E3→E5→E8).

---

## E1. `banco`: a tabela `servidor` e a migração que não perde endereço

- **objetivo** — o DERVS passa a ter servidores nomeados, e nenhum endereço já gravado some no caminho.
- **arquivos** — `banco.py`, `test_banco.py`. **Nenhum outro.**
- **depende_de** — nenhuma.
- **paralelizavel_com** — E2 (arquivos disjuntos).
- **revisores** — database, security.
- **fazer** —
  1. No `ESQUEMA` (`banco.py`), **antes** do bloco de `endereco_producao` (linha 384), a tabela nova, com comentário no mesmo tom dos vizinhos, dizendo que **não há segredo aqui** (nome e padrão públicos) e por que o dono está na linha:
     ```sql
     CREATE TABLE IF NOT EXISTS servidor (
         id                INTEGER PRIMARY KEY AUTOINCREMENT,
         usuario_id        INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
         nome              TEXT NOT NULL CHECK (length(trim(nome)) > 0),
         padrao_subdominio TEXT,
         criado_em         TEXT NOT NULL,
         UNIQUE (usuario_id, nome)
     );
     CREATE INDEX IF NOT EXISTS ix_servidor_dono ON servidor (usuario_id);
     ```
     **`padrao_subdominio` tem UM jeito só de dizer "nenhum": `NULL`.** Nunca string vazia. A conversão para `""` acontece só na borda JSON (E4). Escreva isso no comentário — é a mesma lei que o `url` de `endereco_producao` já segue.
  2. `endereco_producao`, no `ESQUEMA`, ganha `servidor_id INTEGER NOT NULL REFERENCES servidor(id) ON DELETE CASCADE`, e o `UNIQUE` vira `(usuario_id, servidor_id, projeto)`. `usuario_id` **continua na linha** — o motivo já está escrito em `banco.py:369-374` e não muda.
  3. `_CREATE_SERVIDOR` (constante nova, gêmea do `_CREATE_ENDERECO_PRODUCAO`) e `_CREATE_ENDERECO_PRODUCAO` atualizado para a forma nova.
  4. `_migrar_endereco_producao` (`banco.py:980`) passa a criar **`servidor` antes** de `endereco_producao`, na mesma transação, e a checagem de "já migrado" continua sendo a presença de `endereco_producao`.
  5. **`_migrar_servidor_por_endereco(con)` — a migração nova**, chamada em `migrar()` (`banco.py:583-601`) **depois** de `_migrar_endereco_producao`. Molde: `_migrar_achado_dono` (`banco.py:1169-1245`), que é o único que reconstrói tabela preservando dado.
     - sai cedo se `PRAGMA table_info(endereco_producao)` vier vazio, ou se já houver a coluna `servidor_id`;
     - `PRAGMA foreign_keys=OFF`; `BEGIN IMMEDIATE`; **relê a condição dentro da transação** (o motivo está escrito em `banco.py:1198-1200` e vale igual aqui);
     - cria `servidor` se faltar (`_CREATE_SERVIDOR` + índice);
     - para **cada `usuario_id` distinto** presente em `endereco_producao`, insere um servidor `nome='Servidor'`, `padrao_subdominio=NULL`, `criado_em=agora()`, e guarda o `id`;
     - cria `endereco_producao_nova` na forma nova, `INSERT ... SELECT` mapeando cada linha ao servidor daquele dono, `DROP TABLE endereco_producao`, `ALTER TABLE ... RENAME`, recria `ix_endereco_dono`;
     - `commit()`; `except: rollback(); raise`; `finally: _religar_fk(con)`.
     - **Nunca `executescript`** — o motivo está em `banco.py:1194-1196` e custou uma lição em 26/08.
  6. `FILHAS_DE_USUARIO` (`banco.py:606`) ganha `"servidor"`.
- **como_provar** — `python test_banco.py` → `OK`, `Ran N` com **N ≥ 253** (hoje 241). Casos obrigatórios:
  - **`ServidorNoBancoVelho`** (molde: `EnderecoDeProducaoNoBancoVelho`, `test_banco.py:2038`): monta com `sqlite3` cru um banco com `usuario` + a forma **antiga** de `endereco_producao` e **3 linhas de dois donos diferentes**; abre com `banco.conectar`; exige `SELECT COUNT(*) FROM endereco_producao == 3`, que toda linha tenha `servidor_id` não nulo, que exista exatamente **um** servidor por dono e que o nome dele seja `"Servidor"`, e que `SELECT url` de cada linha seja idêntico ao gravado antes.
  - **abrir duas vezes não quebra** e não cria um segundo `"Servidor"`.
  - `UNIQUE (usuario_id, nome)` reprova dois servidores com o mesmo nome na mesma conta e **aceita** o mesmo nome em contas diferentes.
  - `UNIQUE (usuario_id, servidor_id, projeto)` aceita o **mesmo projeto em dois servidores** e reprova dois endereços do mesmo projeto no mesmo servidor.
  - `DELETE FROM servidor` leva os endereços dele junto (`ON DELETE CASCADE`) e **não toca** nos do outro servidor.
  - **`servidor` está em `FILHAS_DE_USUARIO`** (molde: `test_auditoria_e_achado_estao_em_filhas_de_usuario`).
  - **as duas cópias do CREATE não divergem** — dois casos novos no molde de `test_o_esquema_e_a_constante_da_migracao_nao_divergem` (`test_banco.py:1019`), reusando o `normalizar` de lá, um para `servidor` e um para `endereco_producao`.
  - **guarda de "nada de segredo na tabela"**: `{l[1] for l in PRAGMA table_info(servidor)}` é **exatamente** `{"id","usuario_id","nome","padrao_subdominio","criado_em"}`. Este caso reprova coluna nova em silêncio — e é ele que segura o critério do briefing.
- **sabotar antes de aceitar** — troque o `INSERT ... SELECT` da migração por um `SELECT` que perde uma linha (por exemplo um `LIMIT 1`) e exija que `ServidorNoBancoVelho` **fique vermelho**. Guarda de migração que não sabe reprovar é decoração.
- **armadilha** — deixar `_migrar_servidor_por_endereco` **dentro** do corpo de `_migrar_endereco_producao`. O aviso está escrito em `banco.py:589-592`: uma sair na frente com `return` deixa a seguinte sem rodar nunca. Uma função por migração, todas chamadas em `migrar()`.

## E2. `regras`: uma pendência por servidor, com o nome dele na frase

- **objetivo** — dois servidores fora do ar no mesmo projeto viram **duas** pendências distinguíveis, e não uma frase ambígua.
- **arquivos** — `regras.py`, `test_regras.py`. **Nenhum outro.**
- **depende_de** — nenhuma. (Não toca banco: o formato de `sites` está pinado aqui e a etapa 5 é obrigada a produzi-lo.)
- **paralelizavel_com** — E1.
- **revisores** — python.
- **contrato do dado (pinado, e a etapa 5 produz exatamente isto)** — a camada `github` de cada projeto carrega:
  ```python
  novo["sites"] = [
      {"servidor_id": 3, "servidor": "OVH", "url": "https://…",
       "ok": True, "codigo": 200, "erro": "",
       "medido_em": "2026-09-04T…"},
  ]
  ```
  ordenada por nome de servidor. Lista vazia = projeto sem endereço em nenhum servidor. `ok` pode ser `True`, `False` ou `None` ("não medi").
- **fazer** —
  1. `regras.py:193-213` passa a ler `sites = (gh or {}).get("sites")`. **Um único `_p("site_fora", …)`, dentro do laço** — `test_regras.test_nenhuma_regra_repete_o_nome` exige que o nome apareça uma vez só no fonte, e o único repetido permitido é `grafo_velho`.
  2. Cada item com `ok is False` emite uma pendência com `sufixo=str(item["servidor_id"])`. O texto nomeia o servidor: `"O site de produção do %s no servidor %s %s."` — e o nome do servidor **é escrito pelo dono, não vem do GitHub**, então continua valendo a regra de `regras.py:208-210`: URL só na `acao`, nunca no `texto`.
  3. **Ponte para dado antigo, e ela é obrigatória:** quando `sites` não existir e existir `site` (dict, forma de hoje), trate como lista de um item com `servidor: ""` e emita **sem sufixo** e com a frase de hoje. Sem isso, um `hub.db` cuja última coleta é anterior à publicação fica **calado sobre um site fora do ar de verdade** — é a lei 2 sendo quebrada por uma migração de formato. Escreva no comentário que essa ponte morre na primeira coleta boa.
  4. Atualize a docstring do módulo se o número de regras mudar — não deve mudar, e `test_regras.ADocumentacaoNaoPodeMentir` cobra.
- **como_provar** — `python test_regras.py` → `OK`, `Ran N` com **N ≥ 113** (hoje 105). Em `SiteDeProducao` (`test_regras.py:241`):
  - **dois servidores, ambos no ar** → zero pendência `site_fora`;
  - **dois servidores, um fora** → exatamente **1** pendência, o texto contém o nome daquele servidor e **não** contém o do outro;
  - **dois servidores, os dois fora** → **2** pendências, com **ids diferentes** (é este caso que prova o `sufixo`; sem ele os dois ids colidem e o painel some com um);
  - `sites` vazio → calado (invariante 2);
  - camada `github` ausente → calado;
  - **ponte:** `github` com `site` antigo e sem `sites` → 1 pendência, com a frase de hoje;
  - a URL continua fora do `texto` e dentro de `acao["url"]`.
- **sabotar antes de aceitar** — tire o `sufixo=` e exija que o caso "os dois fora" fique vermelho por ids iguais.

## E3. `banco`: as funções de acesso passam a ter servidor

- **objetivo** — nenhuma função do banco continua capaz de responder "o endereço do projeto X" como se houvesse um só.
- **arquivos** — `banco.py`, `coletar.py` (uma linha), `coletar_github.py` (uma linha), `test_banco.py`.
- **depende_de** — E1.
- **paralelizavel_com** — nenhuma (E2 pode já estar pronta; não conflita).
- **revisores** — database, python, security.
- **fazer** — todas com `usuario_id` **posicional e obrigatório**, pelo motivo já escrito em `banco.py:2992-2996`; nenhuma confere URL (a peneira mora em `coletar_github`, `banco.py:3031-3034`).
  1. `servidores(usuario_id, con=None) -> list[dict]` — `[{"id","nome","padrao_subdominio","criado_em"}]` ordenado por `nome`. `padrao_subdominio` sai como veio do banco (`None` quando não há).
  2. `guardar_servidor(usuario_id, nome, padrao_subdominio=None, con=None) -> int | None` — cria; devolve o `id`, ou `None` quando o nome colide, quando o nome fica vazio depois do `strip`, ou quando a conta já tem `MAX_SERVIDORES_POR_CONTA` servidores. **`MAX_SERVIDORES_POR_CONTA = 20`**, constante de módulo com comentário: sem teto total, o balcão por origem só limita a velocidade, e a rota de sugestão passaria a varrer uma lista sem fim. Normaliza `""`/`"   "` de `padrao_subdominio` para `None` — **um jeito só de dizer "nenhum"**.
  3. `remover_servidor(usuario_id, servidor_id, con=None) -> bool` — `DELETE ... WHERE id = ? AND usuario_id = ?`; devolve se apagou. **O dono no `WHERE`, não num `if` antes** — é a lição das quatro portas da fila (04/09).
  4. `enderecos_por_servidor(usuario_id, con=None) -> dict` — `{projeto: [{"servidor_id","servidor","url"}, …]}`, ordenado por nome de servidor. `JOIN servidor` **e** `WHERE endereco_producao.usuario_id = ?` — o dono na linha existe justamente para a leitura não depender do `JOIN`.
  5. `enderecos_do_projeto(usuario_id, projeto, con=None) -> list` — substitui `endereco_de_producao`, que **sai** (único chamador é um teste).
  6. `guardar_endereco_de_producao(usuario_id, servidor_id, projeto, url, con=None) -> bool` — `servidor_id` posicional logo depois do dono. **Confere que o servidor é da conta antes de gravar** e devolve `False` sem gravar quando não é (falha fechada, lei 3). `url` vazia apaga a linha daquele servidor e devolve `True`. `criado_em` continua fora do `DO UPDATE`. O `ON CONFLICT` passa a ser `(usuario_id, servidor_id, projeto)` e **nunca escreve `usuario_id` no `SET`** — é a mesma trava que o `achado` ganhou.
  7. `enderecos_de_producao` **é renomeada** para `um_endereco_por_projeto(usuario_id, con=None) -> {projeto: url}`, com docstring que confessa o que ela é: *"o endereço do servidor de menor nome, e SÓ para a régua de prontidão do `casos.json` (`coletar.py:669`). Quem quer saber se o projeto está no ar usa `enderecos_por_servidor` — esta aqui não sabe responder isso."* Sem o nome novo, ela vira a segunda verdade que ninguém lê.
  8. Trocar o nome nos dois chamadores: `coletar.py:1002` e `coletar_github.py:966`. **Nada mais nesses dois arquivos nesta etapa.**
- **como_provar** — `python test_banco.py` **e** `python test_coletar.py`, os dois `OK`. `test_banco` ≥ **270**; `test_coletar` continua em **201**.
  - o endereço da conta A não aparece na leitura da conta B (molde: `EnderecoDeProducaoTemDono`, `test_banco.py:2153`);
  - **`guardar_endereco_de_producao` com o `servidor_id` de OUTRA conta devolve `False` e não grava nada** — este caso é o critério de aceitação "não é seu responde igual a não existe", no nível do banco;
  - `remover_servidor` com dono errado devolve `False` e a linha continua lá;
  - `guardar_servidor` recusa nome duplicado na mesma conta, aceita em conta diferente, recusa nome vazio, recusa o 21º;
  - `guardar_servidor("OVH", "")` grava `NULL`, não `""` — lido de volta como `None`;
  - `enderecos_por_servidor` traz **os dois** servidores do projeto que responde nos dois, na ordem alfabética do nome;
  - `um_endereco_por_projeto` devolve o do servidor de menor nome, e a docstring dela contém a palavra `prontidão` (guarda barata contra alguém reusá-la achando que é a verdade).
- **sabotar antes de aceitar** — tire o `AND usuario_id = ?` de `remover_servidor` e exija que o caso do dono errado fique vermelho. Foi exatamente assim que as quatro portas da fila foram provadas em 04/09.
- **armadilha** — deixar `enderecos_de_producao` viva "por compatibilidade". Duas cópias divergem, e a que diverge é sempre a que ninguém lê.

## E4. `servir`: as rotas de servidor, e o endereço por servidor

- **objetivo** — dá para cadastrar, listar e apagar servidor pela tela, e gravar endereço dizendo em qual servidor ele mora — com a mesma sequência de defesa que a porta 3 já tem.
- **arquivos** — `servir.py`, `test_servir.py`, `test_rotas.py` (se precisar de caso novo).
- **depende_de** — E3.
- **paralelizavel_com** — E5, E6.
- **revisores** — security, python.
- **fazer** —
  1. **Quatro entradas em `ROTAS`** (`servir.py:2796`), classe de acesso `"dado"` nas quatro, vizinhas das de endereço:
     ```
     "/api/servidores":          Rota("GET",  Hub._servidores,        "dado")
     "/api/servidores/guardar":  Rota("POST", Hub._servidor_guardar,  "dado")
     "/api/servidores/remover":  Rota("POST", Hub._servidor_remover,  "dado")
     ```
     (A quarta, `/api/servidores/sugerir`, nasce na E8.)
  2. `_servidores` — só sessão, molde de `_enderecos` (`servir.py:1588`). Devolve `{"servidores": [{"id","nome","padrao_subdominio","criado_em"}]}`, com `padrao_subdominio` convertido de `None` para `""` **aqui, na borda** — o JSON tem um jeito só, o banco tem outro, e a conversão mora num lugar só.
  3. `_servidor_guardar` — a sequência **inteira**, na ordem de `_endereco_guardar` (`servir.py:1596-1650`): sessão → `Origin` em `ORIGENS_OK` → `_csrf_ok` → `_corpo_json(teto=4096)` → `_texto_do_corpo(corpo, "nome", teto=60)` e `"padrao_subdominio"` com `teto=200` → nome vazio devolve 400 em português → **teto do balcão próprio** `balcao="servidor"`, `teto=self.TETO_DE_SERVIDORES` (**constante nova, `= 20`**, com comentário dizendo que **não** é o `TETO_DE_ENDERECOS`, pelo motivo de `servir.py:1581-1585`) → `banco.guardar_servidor(...)` → `None` devolve 400 com frase em português explicando o porquê (nome repetido / limite de 20 atingido, frases distintas). O teto de 60 no nome não é enfeite: o nome entra em frase de pendência, e `_id_de_pendencia` recusa id acima de 200 caracteres.
     **Nada de rede aqui** — cadastrar servidor não bate em lugar nenhum.
  4. `_servidor_remover` — sessão → Origin → CSRF → `_numero_do_corpo(corpo, "id", int)` (`servir.py:1146`) → `banco.remover_servidor(sessao["usuario_id"], id)` → `False` devolve **404 com a mesma frase** de "esse servidor não existe" que um id inexistente devolve. **"não existe" e "não é seu" respondem igual** — a convenção já registrada no `CLAUDE.md`.
  5. `_enderecos` passa a devolver a lista chata, não o dicionário:
     ```json
     {"enderecos": [{"servidor_id": 3, "servidor": "OVH",
                     "projeto": "dervs", "url": "https://…"}]}
     ```
     ordenada por (nome do servidor, projeto).
  6. `_endereco_guardar` ganha `servidor_id` no corpo, **entre a leitura do corpo e a peneira**: `_numero_do_corpo(corpo, "servidor_id", int)`; ausente ou torto devolve 400 ("diga em qual servidor esse endereço mora"). O resto da sequência **não muda de ordem**: peneira pura → teto do balcão `"endereco"` → `host_publico` → grava → `mede_site`. O `guardar_endereco_de_producao` devolvendo `False` (servidor de outra conta) vira **404, mesma frase de "não existe"**, e isso acontece **depois** do teto e **antes** de `mede_site` — recusar não pode custar uma medição.
  7. O caminho de apagar (`url` vazia) continua sem gastar balcão nem rede, mas agora exige o `servidor_id`.
- **como_provar** — `python test_servir.py` **e** `python test_rotas.py`, os dois `OK`. `test_servir` ≥ **252** (hoje 227); `test_rotas` ≥ 34.
  - Classe nova `OsServidoresNoServidorDeVerdade`, molde de `OEnderecoDoServidorNoServidorDeVerdade` (`test_servir.py:1838`), **com os mesmos dublês de `mede_site` e `host_publico` do `setUp` de lá** — a CI não tem internet garantida.
  - sem sessão → 401 nas três rotas · com sessão e sem CSRF → 403 · sem `Origin` → 403 (as três).
  - cadastra, lista, apaga; **o servidor da conta A não aparece na lista da conta B**; apagar o servidor da conta A com a sessão da conta B devolve **404** e a linha continua viva.
  - **o critério do briefing, no nível da rota:** cadastra dois servidores, grava o **mesmo projeto** nos dois, e `GET /api/enderecos` traz **duas** entradas com `servidor` diferente.
  - **rede interna continua recusada nas rotas novas:** reuse a lista `INTERNOS` de `OEnderecoDoServidorNoServidorDeVerdade` (`test_servir.py:1906`) contra `/api/enderecos/guardar` **com `servidor_id` válido** — a peneira tem de barrar antes de o servidor importar.
  - `servidor_id` ausente → 400 e **nada é gravado**.
  - **teto de balcão próprio:** estourar o balcão `"servidor"` devolve 429 e **não fecha a cortina** nem gasta o balcão `"endereco"` (molde: `test_servir.py:2037`).
  - **guarda de "nenhum segredo entra"**, e ela precisa poder reprovar: um caso que lê o fonte de `Hub._servidor_guardar` e `Hub._servidor_remover` com `inspect.getsource` e exige que **nenhuma** das palavras `senha`, `chave`, `token`, `ssh`, `secret`, `credencial`, `key` apareça como campo lido do corpo. **Sabote:** acrescente `self._texto_do_corpo(corpo, "senha")` numa cópia da string e exija que o casamento acuse — sem isso o caso pode ser tautológico, que foi o defeito de 29/08.
  - `test_rotas` continua verde sem afrouxar nada: nenhum item sai de `PROIBIDO`, `AMPUTADOS`, `EXECUTA` ou `VERBOS_PERMITIDOS`.
- **armadilha** — conferir o dono do servidor num `if` dentro da rota em vez de no `WHERE` do banco. As duas camadas conferem, mas a que **decide** é o `WHERE`; `if` na rota é o padrão que já vazou duas vezes nesta casa.

## E5. `coletar_github`: `novo["sites"]` vira lista, um item por servidor

- **objetivo** — a coleta de 20 minutos mede **cada** servidor onde o projeto tem endereço, e nunca apaga a medição de um servidor por causa de uma rodada que não mediu o outro.
- **arquivos** — `coletar_github.py`, `test_servidores.py` (**novo**), `.github/workflows/ci.yml`.
- **depende_de** — E3 (as funções) e E2 (o `regras` que o caso de fio inteiro atravessa).
- **paralelizavel_com** — E4, E6.
- **revisores** — python, security.
- **fazer** —
  1. `coletar_github.py:966` passa a ler `banco.enderecos_por_servidor(dono, con=con)` — **mantendo a falha fechada em vazio** de hoje (`try/except` → `{}`), e o comentário de `:960-964` continua valendo palavra por palavra.
  2. `coletar_github.py:1032-1044` vira um laço. Para cada item de `por_servidor.get(nome, [])`, chama `mede_site(url)` e monta `{"servidor_id","servidor","url","ok","codigo","erro","medido_em"}`, com `medido_em` **por item**.
  3. **A preservação continua por servidor.** Monte um índice do que já havia — `{item["servidor_id"]: item for item in (antes_gh.get("sites") or [])}` — e, quando `ok is None` para aquele servidor, use o item anterior **daquele servidor**. Nunca o do vizinho, nunca zere a lista inteira. O comentário de `:1036-1039` explica o porquê e vale igual aqui.
  4. **O `casos.json` continua sendo o último recurso, e continua singular.** Projeto sem endereço em nenhum servidor, mas com `local["url_prod"]`, gera **uma** entrada com `servidor: ""` e `servidor_id: 0`. O banco vence o arquivo, na mesma ordem de hoje (`:1024-1031`).
  5. `novo["sites"]` sempre existe (lista, possivelmente vazia). **`novo["site"]` deixa de ser escrito.** Não deixe os dois: `regras.py` tem a ponte para o dado velho, e escrever os dois criaria duas verdades vivas ao mesmo tempo.
  6. **`test_servidores.py` novo**, e ele **declara a chave de teste antes de importar `banco`**:
     ```python
     os.environ.setdefault("DERVS_AMBIENTE", "local")
     os.environ.setdefault("DERVS_COFRE", "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")
     ```
     Sem isso ele passa aqui e fica vermelho só na CI (`45963da`, 29/08). `if __name__ == "__main__"` **no fim do arquivo**.
  7. `.github/workflows/ci.yml`: passo novo `run: python test_servidores.py`, com nome de passo em português dizendo o que ele guarda. O passo "Nenhum arquivo de teste ficou de fora" (`ci.yml:70-77`) cobra isso.
- **como_provar** — `python test_servidores.py` → `OK`; `python test_regras.py` continua `OK`; `python test_coletar.py` continua `OK`.
  - projeto com endereço em **dois** servidores → `sites` com **2 itens**, na ordem alfabética do nome, cada um com o próprio `medido_em`;
  - o servidor A mede `ok=False` e o B devolve `ok=None` → o item do B **mantém a medição anterior do B** e o do A é o novo; o item do A **não** vira o do B;
  - projeto sem endereço nenhum e sem `url_prod` → `sites == []`, e `"site" not in novo`;
  - projeto só com `url_prod` do `casos.json` → um item com `servidor == ""`;
  - **O CASO DO FIO INTEIRO, e é ele que não pode ser apagado:** monte dois servidores de verdade no banco, com o mesmo projeto, dublê de `mede_site` devolvendo `ok=False` para os dois; rode o trecho de coleta; leia a camada de volta com `banco.montar_estado(usuario_id=...)`; passe em `regras.avaliar` e exija **2 pendências `site_fora` com ids diferentes**, cada uma nomeando o seu servidor. Sem este caso, as duas metades ficam verdes contra dublê e a entrega pode estar morta — foi exatamente o que aconteceu com a Auditoria Profunda em 02/09.
- **sabotar antes de aceitar** — faça a preservação usar `sites[0]` em vez do item do servidor certo, e exija que o caso "A fora, B não medido" fique vermelho. **Sabote com tamanho, não só com presença:** o caso de preservação precisa de **dois** servidores, senão `sites[0]` acerta por acidente.
- **armadilha** — medir dentro do laço de projetos sem contar quanto custa. Um dono com 10 projetos × 2 servidores = 20 `mede_site` por rodada, até 22,5 s cada no pior caso. É a coleta de fundo, não uma requisição, então é aceitável — mas escreva o número no comentário, porque o próximo a mexer vai querer saber.

## E6. Painel: o card do projeto e a tela de detalhe passam a ler `sites`

- **objetivo** — o dono bate o olho no card e sabe **em quantos e quais** servidores o projeto responde; abre o detalhe e vê uma linha por servidor.
- **arquivos** — `assets/painel.js`, `assets/painel.css`, `test_design.py`.
- **depende_de** — E2 (o formato). Não depende de rota nova — e é por isso que ela pode andar em paralelo.
- **paralelizavel_com** — E4, E5.
- **revisores** — design, react/typescript (o revisor de JS da casa).
- **fazer** —
  1. **Tela de detalhe**, `assets/painel.js:487-495`: o critério único "Site respondendo" vira **um `criterio()` por item de `gh.sites`**, com rótulo `"Site respondendo — " + item.servidor`, os quatro estados de hoje (`quebrado` / `saudavel` / `sem_dados`), a URL e o código no detalhe, e `haQuanto(item.medido_em)` na marca. `sites` vazio → **uma linha só**: `"Não está em nenhum servidor cadastrado."` com selo `sem_dados` (é ausência, não erro — texto exato em `design.md`).
     **Ponte para dado velho:** se `sites` não existir e `site` existir, desenhe a linha de hoje. Some na primeira coleta boa.
  2. **Card do projeto**, `assets/painel.js:261-294`: ao lado do selo principal, um segundo elemento com `marcaDaPorta(...)`, cujo **rótulo escrito carrega a contagem** — `"em 1 servidor"` / `"em 2 servidores"` / `"não está em nenhum servidor cadastrado"` / `"não deu para conferir"`. **Nenhum quinto estado de selo nasce**: os quatro continuam sendo os únicos, e "está em 2 mas 1 caiu" resolve pelo `piorDe()` que já existe (`painel.js:156`).
     Como `marcaDaPorta` (`painel.js:747`) tira o rótulo de `ESTADO_DA_PORTA`, ou você passa o rótulo por parâmetro opcional **ou** desenha o rótulo ao lado — escolha uma e não duplique a função; duas montagens divergem, e a que diverge é a que esquece o rótulo escrito (o aviso já está em `painel.js:763-764`).
  3. `assets/painel.css`: as classes novas reusam os tokens existentes. **Nenhuma cor literal fora do bloco de tokens** — `test_design.ACorMoraNumLugarSo` reprova; e cor de estado **não pinta botão, link, navegação nem cabeçalho** (`test_2`).
  4. 360px: o selo de servidores fica na linha do nome quando cabe e desce para a do carimbo quando não — sem rolagem horizontal.
- **como_provar** — `python test_design.py` → `OK`, `Ran N` com **N ≥ 36** (hoje 33). Casos novos, todos no molde de `ATelaDeComputadoresCasaDosDoisLados` (`test_design.py:721`):
  - toda classe CSS nova que o `painel.css` estiliza **é produzida** pelo `painel.js`, e vice-versa;
  - os quatro rótulos de contagem existem no fonte da tela, e o plural só aparece a partir de 2;
  - a função que desenha a lista de servidores **chama `haQuanto`** — `test_8c` reprova tela que mostra dado medido sem dizer de quando ele é, e a lista nova cai exatamente nessa peneira;
  - nenhuma palavra em inglês entra em texto de tela (`test_6` roda sozinho sobre o `painel.js` inteiro).
  - `python test_servir.py` continua `OK`: `ATelaSoChamaRotaQueExiste` (`test_servir.py:73`) vigia todo `fetch("…")` novo — **esta etapa não acrescenta nenhum**, e é isso que a mantém verde antes da E4 mesclar.
- **sabotar antes de aceitar** — o teste de casamento CSS↔JS quase sempre tem um caminho tautológico. Renomeie a classe **só no CSS** e exija vermelho; renomeie **só no JS** e exija vermelho. Em 29/08 dois de cinco casos assim não podiam reprovar.
- **limitação declarada** — **não há runtime de JS neste repositório.** Estes casos leem o `painel.js` como texto. "O selo lista os dois nomes na tela" não fica provado por comando; vai para `verificacao.md` como item que exige clique.

## E7. Painel: "Conectar projeto" vira uma lista de servidores

- **objetivo** — o cartão "O seu servidor" vira "Seus servidores": cadastrar, listar, apagar, e um bloco de endereços dentro de cada um.
- **arquivos** — `assets/painel.js`, `assets/painel.css`, `test_design.py`.
- **depende_de** — E4 (as rotas têm de existir antes, senão `ATelaSoChamaRotaQueExiste` fica vermelho) e E6 (mesmos arquivos).
- **paralelizavel_com** — E8 (arquivos disjuntos).
- **revisores** — design, security.
- **fazer** — seguindo `design.md`, seção `telas`, item 1, com os textos de lá **palavra por palavra**:
  1. Variáveis de módulo `SERVIDORES` / `SERVIDORES_LIDO_EM`, e `olharOsServidores()` no molde exato de `olharOsEnderecos()` (`painel.js:1076-1087`) — inclusive o `catch` que **volta sem carimbo**, porque é o carimbo ausente que faz o selo dizer "não olhei".
  2. `ENDERECOS` passa a ser a **lista** que `/api/enderecos` devolve agora; `formularioDeEndereco(servidorId)` filtra por ele. `guardarEndereco(servidorId, projeto, url)` manda `servidor_id` no corpo.
  3. O cartão 3 (`painel.js:1215-1237`) vira: cabeçalho "Seus servidores" com o selo geral de três estados; formulário de cadastrar servidor (nome + padrão de subdomínio, com o texto de ajuda do design); um bloco por servidor com nome, padrão em `--fs-metadado` monoespaçado, botão "Apagar" e o formulário de endereço dentro.
  4. **Apagar usa o diálogo da casa**, `confirmar({titulo, texto, sim, nao}, aoConfirmar)` (`painel.js:2265`), **nunca o `confirm()` do navegador** — o motivo está escrito em `painel.js:1654-1656`. Texto: o do design, que nomeia o que morre.
  5. **Estado vazio, carregando e erro** exatamente como o design manda — e a frase de erro **nunca** diz "nenhum servidor cadastrado" quando a verdade é "não consegui ler".
  6. A nota fixa sobre chave de acesso é **reaproveitada sem reescrever** de `painel.js:1231-1234`.
  7. CSS: reuse `.enderecos`, `.endereco`, `.endereco__dizeres`, `.endereco__url`, `.endereco--novo` (`painel.css:575-621`). As classes novas do bloco de servidor seguem o mesmo prefixo.
- **como_provar** — `python test_design.py` **e** `python test_servir.py`, os dois `OK`. `test_design` ≥ **40**.
  - `ATelaSoChamaRotaQueExiste` verde com os `fetch("/api/servidores")`, `fetch("/api/servidores/guardar")` e `fetch("/api/servidores/remover")` novos — é este caso que prova que a tela não chama rota que não existe;
  - os textos do `design.md` existem no fonte, **casados um a um** (frase de estado vazio, frase de erro de leitura, texto de ajuda do padrão, confirmação de apagar);
  - toda classe nova casa dos dois lados (CSS↔JS);
  - `test_6` (português) e `test_8c` (carimbo) continuam verdes com o texto novo.
- **armadilha** — pintar "Nenhum servidor cadastrado" enquanto a leitura ainda não voltou. É a lei 2 do produto quebrada na cara do dono, e o design escreveu o caminho certo: selo `sem_dados` até `/api/servidores` responder.

## E8. Autodetecção por padrão de subdomínio: o helper e a rota

- **objetivo** — o DERVS testa o padrão contra os projetos que já conhece e **propõe**; nunca grava.
- **arquivos** — `coletar_github.py`, `servir.py`, `test_servidores.py`, `test_servir.py`.
- **depende_de** — E4 e E5.
- **paralelizavel_com** — E7.
- **revisores** — security, python.
- **fazer** —
  1. Em `coletar_github.py`, ao lado da peneira, `url_do_padrao(padrao, projeto) -> str | ""`:
     - devolve `""` se `padrao` não contiver exatamente um `*`, ou se o projeto tiver caractere que não pode virar rótulo de DNS;
     - monta `host = padrao.replace("*", projeto)`;
     - confere com `fnmatch.fnmatch(host, padrao)` — se não casar, `""`;
     - devolve `"https://" + host`.
     **Fica em `coletar_github` de propósito:** é onde a peneira mora, e assim `servir.py` continua chamando tudo qualificado, sem ganhar lógica de URL própria.
  2. Em `servir.py`, `Hub._servidor_sugerir` e a rota `"/api/servidores/sugerir": Rota("POST", Hub._servidor_sugerir, "dado")`:
     - sessão → Origin → CSRF → `_numero_do_corpo(corpo, "servidor_id", int)`;
     - lê o servidor pelo `banco.servidores(sessao["usuario_id"])` e **confere o dono**; não achou ou não é dele → **404, mesma frase**;
     - servidor sem `padrao_subdominio` → 200 com `{"sugestoes": []}` (não é erro);
     - **teto do balcão próprio**, `balcao="sugestao"`, `teto=self.TETO_DE_SUGESTOES` (**constante nova, `= 5`**), **antes de qualquer coisa que toque a rede** — a mesma ordem e o mesmo motivo de `servir.py:1628-1632`;
     - nomes de projeto: `banco.montar_estado(usuario_id=...)["projetos"]` — são os mesmos nomes que o painel já conhece, do computador e do GitHub;
     - descarta os que já têm endereço **naquele** servidor;
     - **mede no máximo `MAX_SUGESTOES = 3`** por chamada, em ordem alfabética estável. Escreva a conta no comentário: 3 × (5 s de DNS + 2 × 8 s + 1,5 s) ≈ **68 s de pior caso numa thread**, e é por isso que o número é 3 e não "todos";
     - para cada candidato: `coletar_github.url_do_padrao` → `coletar_github.url_segura` → `coletar_github.host_publico` → `coletar_github.mede_site`. **Só entra na resposta quem devolveu `ok is True`.** Tudo qualificado, nenhuma peneira nova;
     - devolve `{"sugestoes": [{"projeto","url"}]}`. **Não escreve nada no banco. Nem uma linha.**
- **como_provar** — `python test_servidores.py`, `python test_servir.py`, `python test_rotas.py`, os três `OK`. `test_servir` ≥ **266**.
  - `url_do_padrao("*.tinehost.com.br", "ccvp-painel")` → `"https://ccvp-painel.tinehost.com.br"`; padrão sem `*` → `""`; padrão com dois `*` → `""`; projeto com `/`, espaço ou `..` → `""`;
  - **a rota não grava:** conte as linhas de `endereco_producao` antes e depois; tem de ser o mesmo número. Este é o caso que sustenta a decisão do Diretor;
  - **rede interna continua recusada aqui também:** dublê de `host_publico` devolvendo `False` → zero sugestões, e `mede_site` **não é chamado**;
  - candidato que responde `ok=False` **não** entra na lista; `ok=None` também não;
  - servidor de outra conta → 404, mesma frase de "não existe";
  - servidor sem padrão → `{"sugestoes": []}` e **nenhuma chamada de rede** (conte as chamadas do dublê);
  - no máximo 3 medições por chamada, mesmo com 10 projetos casando — conte as chamadas do dublê e exija exatamente 3;
  - teto do balcão `"sugestao"` devolve 429 sem gastar o balcão `"endereco"` nem o `"servidor"`;
  - `test_rotas` verde: `/api/servidores/sugerir` não casa `PROIBIDO`, `_servidor_sugerir` não casa `PROIBIDO`, e `_alcancaveis(Hub._servidor_sugerir) & EXECUTA == set()`.
- **sabotar antes de aceitar** — troque o `if medida["ok"] is True` por `if medida["ok"] is not False` e exija que o caso do `ok=None` fique vermelho. "Não medi" virando sugestão é a lei 2 quebrada dentro da funcionalidade nova.
- **armadilha** — chamar `banco.montar_estado` sem `usuario_id`. Ele é keyword-only e obrigatório (`banco.py:1490`); passar a conta errada aqui entrega os nomes de projeto de outra pessoa.

## E9. A sugestão na tela — propõe, e para

- **objetivo** — o dono vê o endereço que o DERVS achou, com o nome do projeto, e decide com um clique.
- **arquivos** — `assets/painel.js`, `assets/painel.css`, `test_design.py`.
- **depende_de** — E7 e E8.
- **paralelizavel_com** — nenhuma.
- **revisores** — design, security.
- **fazer** —
  1. Ao pintar "Conectar projeto", **uma chamada por servidor com padrão, uma vez por sessão** — guarde os `servidor_id` já pedidos num `Set` de módulo. Sem isso a tela dispara até 68 s de medição a cada repintura, e o `pintarConectar()` roda em toda leitura assíncrona que volta.
  2. A resposta pinta, **dentro do bloco daquele servidor, acima do formulário manual**, a linha do design: contorno `--borda-forte` (**não uma cor de estado** — é proposta, não veredito), o texto exato do `design.md`, e dois botões: "Usar este endereço" → chama `guardarEndereco(servidorId, projeto, url)`; "Ignorar" → some da tela e **não volta nesta sessão** (mesmo `Set`).
  3. Nada é gravado sem o clique. Nenhum caminho da tela grava sozinho.
- **como_provar** — `python test_design.py` **e** `python test_servir.py`, os dois `OK`. `test_design` ≥ **43**.
  - o texto exato da sugestão e os dois rótulos de botão existem no fonte;
  - a linha de sugestão **não usa** `--estado-saudavel`/`--estado-quebrado` (caso que lê o CSS e reprova se usar — é a diferença entre proposta e veredito, e é a única forma automatizável de cobrar isso);
  - `ATelaSoChamaRotaQueExiste` verde com `fetch("/api/servidores/sugerir")`;
  - português e carimbo continuam verdes.
- **armadilha** — chamar `sugerir` dentro de `pintarConectar()` sem o `Set`. `pintarConectar` é chamada por `olharOsEnderecos`, `olharOsComputadores` e `olharOsServidores` — três disparos por abertura de tela, e cada um custa até 68 s de thread no servidor.

## E10. Documentação e verificação

- **objetivo** — a documentação descreve o software de hoje, e o que os comandos **não** provam está escrito antes de alguém dizer "pronto".
- **arquivos** — `docs/A-APLICACAO.md`, `CLAUDE.md` (do repositório), `docs/esteira/servidores-multiplos/verificacao.md` (**novo**).
- **depende_de** — E1 a E9.
- **fazer** —
  1. **`docs/A-APLICACAO.md` §5.1c** reescrito: "O seu servidor" vira "Os seus servidores". Diga que são vários, nomeados, que o mesmo projeto pode responder em mais de um, e **repita sem afrouxar** a frase "Sem chave SSH, agora e sempre". §11 ganha uma linha sobre esta entrega. É a fonte única — em conflito, ela vence.
  2. **`CLAUDE.md` do repositório** ganha um bloco curto com as convenções que **nascem aqui**, e só elas:
     - `novo["sites"]` é **lista**, nunca `site`; item por servidor, cada um com o próprio `medido_em`, e `ok=None` preserva a medição **daquele** servidor;
     - o sufixo do id de `site_fora` é o **`servidor_id`**, nunca o nome — nome renomeia, id não, e nome + projeto estoura o teto de 200 de `_id_de_pendencia`;
     - `padrao_subdominio` é `NULL` no banco e `""` no JSON, com **um** ponto de conversão, na borda da rota;
     - `um_endereco_por_projeto` é a régua de prontidão do `casos.json` e **não** responde "o projeto está no ar" — quem responde isso é `enderecos_por_servidor`;
     - os balcões `"servidor"` e `"sugestao"` são **próprios**, e `TETO_DE_ENDERECOS` continua sem ser emprestado.
  3. **`docs/esteira/servidores-multiplos/verificacao.md`** (fase 6): a saída colada de cada comando, **e a lista do que eles não provam** — no mínimo: que o selo desenha os dois nomes na tela (não há runtime de JS aqui), que a migração roda no `hub.db` **de produção** sem perder linha (só se prova publicando ou copiando o banco de lá), que o padrão de subdomínio real do dono casa os projetos certos, e o comportamento em 360px.
- **como_provar** — **a suíte inteira**, não dois arquivos (a lição de 02/09): `for t in test_*.py; do echo "== $t"; python "$t" || break; done` (Git Bash). Os 26+ arquivos `OK`, nenhum vermelho, e o passo "Nenhum arquivo de teste ficou de fora" do `ci.yml` reconhecendo `test_servidores.py`.
- **armadilha** — dizer que a tela mudou antes de conferir a etiqueta `publicado-*`. **O que está no ar é mais velho que a `main`**, e há um lote inteiro esperando o sinal do dono (as quatro portas da fila, `2b7b2eb..84c3f64`). Este trabalho **entra no mesmo lote** e não muda a regra: quem publica é o dono dando o sinal.

---

## Paralelizável

- **Onda 0:** E1 (`banco.py`, `test_banco.py`) ‖ E2 (`regras.py`, `test_regras.py`).
- **Onda 2:** E4 (`servir.py`, `test_servir.py`, `test_rotas.py`) ‖ E5 (`coletar_github.py`, `test_servidores.py`, `ci.yml`) ‖ E6 (`painel.js`, `painel.css`, `test_design.py`).
- **Onda 3:** E7 (`painel.js`, `painel.css`, `test_design.py`) ‖ E8 (`coletar_github.py`, `servir.py`, `test_servidores.py`, `test_servir.py`).

Nenhum par acima toca o mesmo arquivo. `ci.yml` é editado **só** pela E5.

## Sequencial obrigatório

- **E1 → E3**: os dois escrevem `banco.py`; e as funções de acesso não têm onde existir antes da coluna.
- **E3 → E4, E3 → E5**: as duas chamam funções que nascem na E3.
- **E2 → E5**: o caso do fio inteiro da E5 exige `regras.avaliar` já lendo `sites`; rodá-lo antes daria verde por ausência.
- **E4 → E7**: `ATelaSoChamaRotaQueExiste` reprova `fetch` para rota que não existe.
- **E6 → E7 → E9**: os três escrevem `painel.js`, `painel.css` e `test_design.py`.
- **E5 → E8**: os dois escrevem `coletar_github.py`. **E4 → E8**: os dois escrevem `servir.py`.
- **E10 por último**: ela precisa dos números finais para não mentir.

## O que o planner não conseguiu confirmar

- **Se o `hub.db` de produção tem linha em `endereco_producao`.** A migração foi desenhada para o pior caso (tem linhas, de mais de um dono), e o teste da E1 prova esse caso. O número real só se sabe publicando.
- **Se o `test_design.py` novo vai passar de primeira nos guardas de contraste.** Expectativa de que sim (nenhum token de cor novo), mas não rodou — a tela nova não existe ainda.
- **Se `MAX_SUGESTOES = 3` é o número certo.** Escolhido por aritmética de pior caso (~68 s de thread), não por medição. Pode subir depois de medido.
- **A frase exata de `regras.py` quando o servidor vem do `casos.json`** (`servidor == ""`). Sugestão: cair na frase de hoje, sem nomear servidor — decisão de texto que pode ser revista na fase 6.

## Uma linha sobre o que foi visto e não planejado

`endereco_de_producao` (`banco.py:2989`) já é código morto hoje — nenhum consumidor de produção. Ele sai na E3 porque **ficaria errado** depois da mudança, não por faxina.
