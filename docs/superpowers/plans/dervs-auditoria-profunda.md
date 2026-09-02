# Plano — A Auditoria Profunda

> Fase 4 da esteira, escrita em 02/09/2026 na branch `auditoria-profunda`.
> Autoridade, nesta ordem: `docs/esteira/auditoria-profunda/spec.md` → `briefing.md`
> → `CLAUDE.md` da raiz → `design.md`.
> **A spec já decidiu a arquitetura. Este plano não redecide nada dela** — ele corta o
> trabalho em etapas que cabem num commit, declara o comando que prova cada uma, e
> nomeia a sabotagem que valida cada guarda novo.

---

## Contexto verificado no código (lido, não resumido da spec)

- `tarefas.py:1-27` declara que nada é importado dali além da biblioteca padrão, e
  **nunca `execucao` nem `fila`**. Os tetos estão em `tarefas.py:37-56`
  (`TETO_USD=3.0`, `USD_BRL=5.14`, `MAX_TURNOS=40`, `TETO_DIARIO_BRL=50.00`,
  `MAX_TENTATIVAS=2`). `teto_da_sessao` (`tarefas.py:119`) já limita a sessão ao que
  sobra do dia.
- `FIM_DO_BLOCO` (`execucao.py:252`) e `so_dado` (`execucao.py:255`) moram hoje em
  `execucao.py`, que **não** entra na imagem — `test_imagem.PROIBIDOS =
  ("execucao.py","fila.py","barreira.py","hub.db","cofre.chave")` (`test_imagem.py:45`).
  A reexportação-molde já existe: `execucao.em_reais = tarefas.em_reais`
  (`execucao.py:401`).
- `execucao.montar_comando` (`:162`) monta o argv e manda o prompt por **stdin**;
  `FERRAMENTAS_OK` (`:95`), `FERRAMENTAS_PROIBIDAS` (`:100`),
  `VIGIADAS = ("Bash","Write","Edit","MultiEdit","NotebookEdit")` (`:203`),
  `METACARACTERES_DO_CMD = ("|","&","<",">","^","%")` (`:246`).
- `agente/executor.py`: `Executor` com `_recusar_se_nao_pode` (`:55`),
  `ExecutorClaude`, `ExecutorCodex` (`disponivel()` → `False`), tabela `EXECUTORES` e
  `executor_de()` no fim. `agente/enviar.fazer_a_tarefa` (`agente/enviar.py:294`)
  escolhe o braço por `tarefa["executor"]`.
- `banco.migrar` (`banco.py:525`) chama seis `_migrar_*`; `_migrar_instalacao_github`
  (`banco.py:979`) é o molde exato: checa `sqlite_master`, `BEGIN IMMEDIATE`, **relê a
  condição dentro da transação**, e `con.execute` um comando por vez.
  `FILHAS_DE_USUARIO` em `banco.py:546`. A coluna
  `executor TEXT NOT NULL DEFAULT 'claude'` já existe (`banco.py:560`, `:1355`).
- **Confirmado o defeito que a spec aponta:** `banco.enfileirar` (`banco.py:1368`) faz
  `INSERT OR IGNORE INTO fila (id, projeto, regra, gravidade, risco, trilho,
  criado_em)` — **`executor` não está no INSERT**. Hoje toda tarefa nasce `'claude'`
  pelo DEFAULT.
- `banco.montar_estado` (`banco.py:1267`) anexa camadas com
  `for extra in ("github","pesado")` e faz `p.setdefault(extra, None)`. É esse laço que
  ganha `"auditoria"`.
- `servir._tarefa_pendente` (`servir.py:1890`) já devolve
  `"executor": candidata.get("executor") or "claude"` (`:1917`) e
  `"detalhe": candidata.get("erro") or ""` (`:1918`) — para tarefa nova o `erro` é
  sempre vazio, como a spec descreve.
- `servir.ACESSOS = frozenset(("aberta","cortina","dado","maquina"))` (`servir.py:2483`);
  `ESTATICOS_COM_SESSAO = {"/assets/painel.js","/assets/painel.css"}` (`:2572`).
- **Há balcão genérico reusável:** `cortina.registrar_tentativa(chave, agora,
  balcao="...", teto=N)`, usado em `servir.py:1440` (`TETO_DE_CODIGOS = 20`), `:1594`
  (`TETO_DE_ENDERECOS = 20`), `:1853` (`TETO_DE_RELATORIOS = 60`) e `:1963`
  (`TETO_DE_RESULTADOS = 240`).
- `test_rotas.PROIBIDO = r"acao|execucao|exec|terminal|pty|shell|comando|grafo"`
  (`test_rotas.py:40`) casa contra caminho **e** `funcao.__name__`; `AMPUTADOS`
  (`:46`) inclui `"execucao"` e `"fila"`; `EXECUTA` (`:111`) inclui `"coletar"`,
  `"subprocess"`, `"exec"`, `"eval"`, `"compile"`, `"__import__"`, e `_alcancaveis`
  (`:124`) anda o grafo de chamadas.
- `.github/workflows/ci.yml:71-77` é o passo que cobra a lista
  (`for t in test_*.py; do grep -q "python $t" ... done`). Os testes são listados à
  mão, um passo cada, de `ci.yml:83` a `:235`.
- `Dockerfile:62-74` é o bloco de `COPY` dos módulos de runtime.
  `test_imagem.modulos_de_runtime()` (`test_imagem.py:66`) segue os imports de
  `servir.py` **em profundidade** — `import auditoria` obriga `COPY auditoria.py`.

## Premissas do pedido que NÃO se confirmaram

1. **`docs/esteira/auditoria-profunda/design.md` não existia** no momento em que o
   plano foi escrito. **Passou a existir em 02/09/2026 14:11**, escrito pela fase 3 em
   paralelo, e foi validado. **A Etapa 6 está desbloqueada.** Ela continua obrigada a
   *seguir* o `design.md`, sem inventar desenho.
2. **`regras.py` já tem uma regra chamada `auditoria_nao_rodou`** — `regras.py:241`
   (a pendência), `:479` (`CAMADA_DA_REGRA` → `"pesado"`) e `:587` (`ROTULO_REGRA` →
   *"cujas dependências não consegui auditar"*). É sobre auditoria de **dependências**
   e não tem nada com esta entrega. A spec não previu esse choque. **Conferido no
   código em 02/09/2026.**
   **Consequência dura para todo guarda deste plano: casar nome de regra por igualdade
   exata ou por pertencimento a uma lista, NUNCA por `startswith("auditoria")` nem por
   `"auditoria" in regra`.** Um guarda por prefixo passa verde lendo a regra errada.
3. `regras.py` hoje **não importa nenhum módulo local**. Passar a importar `auditoria`
   é mudança de fronteira — aceitável porque `auditoria.py` é puro e entra na imagem,
   mas `regras.py` tem de continuar sem tocar disco, rede ou processo.

---

## Riscos, e o que fazer se acontecerem

- **O binário `claude` nunca pode ser chamado por teste.** A CI não tem login e cada
  corrida gastaria a assinatura do dono (`ci.yml:78-82`). Todo teste que precise de
  stream usa **script de mentira** que cospe `stream-json`, no molde de
  `test_executor.py`.
- **`--json-schema` é promessa do fornecedor.** A validação que vale é
  `auditoria.validar()`, em Python. Nenhum teste pode depender de o binário respeitar
  o esquema.
- **`/api/auditoria/pedir` sem teto vira torneira na fila.** A Etapa 5 reusa
  `cortina.registrar_tentativa`; **não invente mecanismo novo**.
- **`auditoria.py` entra na imagem.** Se importar `execucao`, `fila` ou `barreira`,
  `test_imagem.test_nada_de_execucao_fila_barreira_banco_ou_cofre` fica vermelho e a
  imagem morre na subida. Ele importa, no máximo, a stdlib e `tarefas`.
- **Sabotagem tautológica.** O CLAUDE.md registra que `id="lista-computadores"` já
  contém a palavra `computadores` e o guarda não podia reprovar. Vale igual aqui:
  `id="tela-auditoria"` contém `auditoria`. Ver sabotagem 6b.
- **Rodar dois arquivos não é rodar a suíte** (lição de 02/09). Guardas que leem
  código-fonte quebram com renomeação feita em outra etapa. Por isso existe a Etapa 7.

---

## O número em aberto: `TETO_AUDITORIA_USD`

A spec recomenda **US$ 1,50 por auditoria (≈ R$ 7,71)**; alternativas US$ 3,00 e
US$ 0,75. **O valor entra na Etapa 1**, como `tarefas.TETO_AUDITORIA_USD`. **Se ainda
não houver decisão do dono quando a Etapa 1 for despachada, use o recomendado da spec:
`1.50`.** A Etapa 7 troca o número numa linha. Nenhuma outra etapa depende do valor —
só do nome da constante.

---

## Regras duras que valem para TODAS as etapas

O executor não vê esta conversa nem as outras etapas. Estão repetidas dentro de cada
etapa de propósito.

1. **TDD.** Teste primeiro, vermelho, depois o código. Vale para validação, cálculo,
   parser, regra de negócio e guarda. Não vale para CSS e texto de tela.
2. **`if __name__ == "__main__"` fica no FIM do arquivo de teste, sempre.**
3. **Teste que sobe servidor ou importa `banco` declara a chave ANTES do import**,
   literalmente assim, no topo:

   ```python
   os.environ.setdefault("DERVS_AMBIENTE", "local")
   os.environ.setdefault("DERVS_COFRE", "chave-de-teste-que-nao-e-segredo-nenhum-0123456789")
   ```

   Sem isso passa nesta máquina e fica vermelho **só na CI** — `chave_do_cofre()`
   recusa inventar chave fora do ambiente local. Aconteceu em 29/08/2026 (`45963da`).
4. **Todo `test_*.py` novo entra à mão em `.github/workflows/ci.yml`**, passo próprio,
   `run: python test_X.py`. O passo `ci.yml:71-77` cobra a lista.
5. **Nenhuma etapa afrouxa `test_rotas.py` nem `test_tarefas_nao_publicam.py`.** Os
   dois são **somente leitura** para todas as etapas. Se ficarem vermelhos, o defeito
   está no código novo.
6. **Teste com data fixa** passa `agora_iso` para toda função que compara prazo.
7. **Sabote com tamanho, não só com presença**, quando o guarda cobre um laço.
8. **Segredo:** `secret-scan.sh` barra por forma — `token = <16+ caracteres>` é
   bloqueado mesmo sendo dado de teste. Tokens de mentira com menos de 16 caracteres.
9. **Nada de heredoc** para escrever arquivo nesta máquina (troca o fim de linha).
10. **Rode os SEUS arquivos, não a suíte inteira.** A Etapa 7 roda tudo.
11. **Casar nome de regra por igualdade exata**, nunca por prefixo — ver premissa 2.

---

## Etapas

### Etapa 1 — A fundação: `tarefas.py` ganha os tetos e o sanitizador; nasce `auditoria.py`

**Porquê:** todo o resto importa daqui. E `so_dado` precisa sair de `execucao.py` (que
não entra na imagem) para `tarefas.py` (que entra), senão haveria uma segunda cópia da
peneira — o defeito que o CLAUDE.md registra como *"uma segunda cópia dessa peneira já
matou o drift em silêncio com 926 testes verdes"*.

**Arquivos que ela toca (nenhum outro):**
`auditoria.py` (**novo**), `test_auditoria.py` (**novo**), `tarefas.py`,
`test_tarefas.py`, `execucao.py` (**apenas** a remoção de `FIM_DO_BLOCO`/`so_dado` das
linhas 252 e 255 e a reexportação no lugar — nada mais), `Dockerfile`,
`.github/workflows/ci.yml`.

**Fazer:**

1. **`tarefas.py`**, no bloco de dinheiro (perto de `tarefas.py:37-56`):
   - `TETO_AUDITORIA_USD = 1.50` (ver *O número em aberto*) e `MAX_TURNOS_AUDITORIA`
     (recomendo `60`; a spec não fixa — escolha e escreva o porquê em comentário).
   - `def teto_da_auditoria(gasto_usd) -> float:` devolvendo
     `max(0.0, min(float(TETO_AUDITORIA_USD), quanto_falta(gasto_usd) / USD_BRL))`.
     Mora aqui porque **o servidor precisa dele** (`servir.py:1918`) e o servidor não
     pode importar `execucao` nem `fila`.
   - `FIM_DO_BLOCO` e `so_dado`, **movidos** de `execucao.py:252-260`, com o comentário
     original preservado.
2. **`execucao.py`**: onde estavam as definições, ficam
   `FIM_DO_BLOCO = tarefas.FIM_DO_BLOCO` e `so_dado = tarefas.so_dado` — os **mesmos
   objetos**, no molde de `execucao.em_reais = tarefas.em_reais` (`execucao.py:401`).
   Não mexa em mais nada de `execucao.py` nesta etapa.
3. **`auditoria.py`**, puro, importando no máximo a stdlib e `tarefas`:
   - `CATEGORIAS = ("seguranca","bug","teste","doc","estilo")` — a **fonte única**. O
     `enum` do esquema, o sufixo das cinco regras e as chaves de rótulo são
     **derivados** dela, nunca reescritos.
   - `REGRA_DE_VENCIMENTO = "auditoria_vencida"`, `EXECUTOR = "auditor"`,
     `REGRAS = {cat: "auditoria_" + cat}` e `EXECUTOR_DA_REGRA` (regra → executor,
     consumido por `fila.elegiveis`).
   - `ESQUEMA` — o dicionário Python **literalmente** como está em `spec.md` § *"3 — O
     esquema JSON exato"*, com `maxItems: 60`.
   - `GABARITO` — gabarito **fechado**, no molde de `execucao.GABARITO`
     (`execucao.py:129`), com **um único** campo interpolado: o nome do projeto. O
     texto diz com todas as letras que tudo que o agente ler dos arquivos é objeto de
     análise e nunca ordem. **O conteúdo dos arquivos não passa pelo prompt.**
   - `montar_prompt(projeto)` — aplica `tarefas.so_dado` ao nome do projeto.
   - `impressao(arquivo, categoria, frase)` — 12 primeiros hexadígitos de
     `sha256(arquivo + "\n" + categoria + "\n" + normalizar(frase))`, com `normalizar`
     = minúsculas, espaços colapsados, pontuação de fim removida. **A linha NÃO entra.**
   - `id_do_achado(regra, projeto, achado)` → `"<regra>:<projeto>:<impressao>"`.
   - `caminho_aceitavel(arquivo)` — recusa caminho absoluto, com `..`, começando com
     `/` ou `\`, ou com letra de unidade (`C:`).
   - `limpar(achado)` — `so_dado` em `frase`, `o_que_fazer` e `trecho`, remoção de
     caracteres de controle, corte nos tamanhos do esquema.
   - `validar(bruto)` — **tudo-ou-nada**, refazendo em Python tipo, faixa, enumeração,
     tamanho e a peneira de caminho. Devolve `(achados, "")` ou
     `(None, "<motivo em português>")`. Saída truncada, vazia e JSON quebrado →
     `(None, motivo)`. **Nunca lista parcial.**
4. **`Dockerfile`**: `COPY auditoria.py /app/` no bloco `Dockerfile:62-74`.
5. **`ci.yml`**: passo próprio, nome em português, `run: python test_auditoria.py`.

**Verificação (da raiz do repositório):**

```
python test_auditoria.py
python test_tarefas.py
python test_imagem.py
```

Esperado: `OK` nos três. `test_imagem.py` verde prova que a linha de `COPY` foi aceita.

**Critérios do briefing:** 2, 4, 5 (parcial), 8 (parcial).

**Sabotagens obrigatórias:**

| # | Quebra deliberada | Caso que TEM de acusar |
|---|---|---|
| 1a | Incluir `linha` no cálculo de `impressao` | "duas auditorias com a linha deslocada dão o mesmo id" |
| 1b | Ordenar por índice dentro de `validar` | "mesma auditoria, ordem embaralhada, ids iguais" |
| 1c | Fazer `validar` descartar o inválido e devolver o resto | "um achado inválido invalida a corrida inteira" |
| 1d | **Por tamanho:** fazer o laço de `validar` parar depois do 1º item. Use **61 achados em que só o último é inválido** — com 2 itens este guarda passa verde | "61 achados, o último inválido, recusa tudo" |
| 1e | Remover a checagem de `..` de `caminho_aceitavel` | `../../.ssh/config` recusado |
| 1f | Acrescentar `"perf"` ao `enum` do `ESQUEMA` sem pôr em `CATEGORIAS` | "as cinco categorias são a mesma lista" |
| 1g | Renomear `auditoria_seguranca` para `auditoria:seguranca` | "nenhuma regra tem dois-pontos" (quem lê é `execucao.py:1058`, `pendencia_id.split(":")[0]`) |
| 1h | Acrescentar ao `ESQUEMA` um `"pattern": "^[^<>]+$"` | "o JSON serializado do esquema não contém `\|`, `&`, `<`, `>`, `^` nem `%`" |
| 1i | Redefinir `so_dado` dentro de `execucao.py` (uma cópia) | **identidade** `tarefas.so_dado is execucao.so_dado` (use `is`, não `==`) |
| 1j | Trocar `max(0.0, ...)` por `min(...)` em `teto_da_auditoria` | "gasto acima do teto do dia → teto da auditoria é 0.0" |

**Depende de:** nenhuma. **É o gargalo: 3, 4 e 5 esperam por ela.**

---

### Etapa 2 — `banco.py`: as duas tabelas, a migração e as quatro funções

**Porquê:** sem a tabela da **corrida**, um projeto com zero linhas em `achado` é
indistinguível de um projeto nunca auditado — e o painel diria "0 achados" para quem
nunca foi medido. É a lei 2 em forma de esquema.

**Arquivos que ela toca (nenhum outro):** `banco.py`, `test_banco.py`.

**Fazer:**

1. O DDL **literal** de `auditoria` e `achado` está em `spec.md` § *"o_que_ja_existe →
   o que muda"*. Copie sem alterar. Vai em **duas cópias, de propósito**, no molde
   declarado em `banco.py:785-789`: dentro de `ESQUEMA` (`banco.py:92`) e nas
   constantes `_CREATE_AUDITORIA` / `_CREATE_ACHADO`.
2. `_migrar_auditoria(con)`, acrescentada a `migrar()` (`banco.py:525`), **no molde
   exato de `_migrar_instalacao_github` (`banco.py:979`)**: sai cedo se `usuario` não
   existe; sai se as tabelas já existem; `BEGIN IMMEDIATE`; **relê a condição dentro da
   transação**; e **`con.execute` um comando por vez, JAMAIS `executescript`** — ele dá
   COMMIT implícito e desmonta a transação (`banco.py:993`, lição de 26/08/2026).
3. `FILHAS_DE_USUARIO` (`banco.py:546`) ganha `"auditoria"` e `"achado"`.
4. Funções novas: `gravar_auditoria(...)` (**uma transação só**, molde de
   `banco.py:664`), `auditoria_do_projeto(...)`, `achados_do_projeto(...)`,
   `fechar_achados_ausentes(...)`.
   - Achado que reaparece: `INSERT OR REPLACE` na **mesma** linha, **mantendo o
     `visto_em` mais antigo**.
   - Achado que não voltou: marca `fechado_em`. **Nunca `DELETE`.**
5. **Cirúrgico em `banco.enfileirar` (`banco.py:1368`):** o `INSERT` passa a levar
   `executor`, lendo `p.get("executor")` com padrão `'claude'`. Verificado: hoje a
   coluna **não está** no INSERT.
6. **Cirúrgico em `banco.montar_estado` (`banco.py:1267`):** camada `auditoria` anexada
   com carimbo em `p["medido_em"]["auditoria"]`, no mesmo laço de `("github","pesado")`.
   Projeto sem corrida recebe `p["auditoria"] = None` — **`None`, nunca `{}`, nunca
   `{"achados": []}`**.
7. **Cirúrgico em `banco.tarefa_para_maquina` (`banco.py:1435`):**
   `LEFT JOIN achado ON achado.id = fila.id`, para o `detalhe` da tarefa sair do achado.
   A função continua **só lendo** e falhando fechada.

**Verificação:**

```
python test_banco.py
```

**Critérios do briefing:** 2, 4, 1 (parcial).

**Sabotagens obrigatórias:**

| # | Quebra deliberada | Caso que TEM de acusar |
|---|---|---|
| 2a | Trocar os `con.execute` de `_migrar_auditoria` por `con.executescript` | o caso que lê o código-fonte de `_migrar_auditoria` e exige `BEGIN IMMEDIATE` **e** a ausência de `executescript` |
| 2b | Fazer o `INSERT OR REPLACE` sobrescrever `visto_em` | "achado que reaparece mantém o `visto_em` mais antigo" |
| 2c | Trocar `fechar_achados_ausentes` por um `DELETE` | "achado que sumiu ganha `fechado_em` e continua na tabela" |
| 2d | Remover `executor` do INSERT de `enfileirar` | "enfileirar com `executor='auditor'` e ler de volta `'auditor'`" |
| 2e | Fazer `montar_estado` devolver `{"achados": []}` para projeto sem corrida | "projeto nunca auditado recebe `None`" — use `assertIsNone`, **não** `assertFalse` (que passa com `{}`) |
| 2f | **Por tamanho:** fazer `gravar_auditoria` dar `commit` a cada achado. Use **60 achados** e derrube a gravação no 40º; a tabela tem de ficar **vazia** | "gravar 60 achados é tudo-ou-nada" |
| 2g | Remover `"achado"` de `FILHAS_DE_USUARIO` | "apagar o usuário leva junto as corridas e os achados" (`ON DELETE CASCADE` só vale com `PRAGMA foreign_keys=ON`, `banco.py:509`) |

**Depende de:** nenhuma. **Roda em paralelo com a Etapa 1.**

---

### Etapa 3 — `regras.py` + `fila.py`: o achado vira pendência e entra na fila

**Porquê:** é onde o achado deixa de ser dado e vira *"o que precisa de mim agora?"*,
com a cor do semáforo por categoria — controle real para o dono, sem mecanismo novo.

**Arquivos que ela toca (nenhum outro):** `regras.py`, `test_regras.py`, `fila.py`,
`test_fila.py`.

**Fazer:**

1. **`regras.py`** importa `auditoria` (só as constantes de nome). O módulo continua
   **puro**: não lê disco, não chama rede, não roda comando.
   - `_p` (`regras.py:42`) ganha `sufixo=""` opcional que, quando presente, faz o id
     virar `"regra:projeto:sufixo"`. Sem sufixo, nada muda.
   - `_do_projeto` (`regras.py:61`) ganha o bloco que lê `p.get("auditoria")`, **no
     molde exato de `gh = p.get("github")` (`regras.py:69`)**: `None` significa "camada
     não coletada" e o motor fica **calado**. Nunca "0 achados".
   - Cada achado de gravidade **`alta`** vira pendência da regra
     `auditoria_<categoria>`, com ação `{"tipo":"vscode","rotulo":"Abrir o
     arquivo","caminho":"<caminho do projeto>/<arquivo>"}` — tipo já existente em
     `regras.ACOES` (`regras.py:30`). **Achado cujo `arquivo` não passa em
     `auditoria.caminho_aceitavel` não vira pendência nenhuma** (invariante 1).
   - `auditoria_vencida` (gravidade **baixa**): projeto marcado para auditar cuja
     última corrida venceu, ou que nunca teve corrida.
   - `VALIDADE` (`regras.py:458`) ganha `"auditoria": 7 * 24 * 3600`.
   - `CAMADA_DA_REGRA` (`regras.py:466`) ganha as **cinco** `auditoria_*` — e **não**
     `auditoria_vencida`: "não medi" é `sem_dados`, nunca `quebrado`.
   - `ROTULO_REGRA` (`regras.py:570`) ganha as **seis**, em português.
   - `NAO_AGRUPAR` (`regras.py:566`) ganha as **cinco** `auditoria_*`, porque `agrupar`
     escreve `"%d projetos %s."` (`regras.py:628`) e doze achados no **mesmo** projeto
     virariam *"12 projetos com achados de segurança"*.
2. **`fila.py`**:
   - `REGRAS_MECANICAS` (`fila.py:26`) ganha `"auditoria_vencida": "claude"`. As cinco
     `auditoria_*` entram **apenas se e quando o dono autorizar** — na dúvida, deixe-as
     **fora** e escreva o comentário dizendo por quê. Fora é o estado seguro.
   - `elegiveis` (`fila.py:61`) passa a carimbar `executor` além de `trilho`, lendo
     `auditoria.EXECUTOR_DA_REGRA`. Regra fora do mapa recebe `"claude"`.
3. **Atenção à premissa 2:** `auditoria_nao_rodou` já existe (`regras.py:241/479/587`)
   e é outra coisa. Case por igualdade exata.

**Verificação:**

```
python test_regras.py
python test_fila.py
```

Os casos dos três invariantes já existentes em `test_regras.py` têm de continuar verdes
**cobrindo também os achados novos**.

**Critérios do briefing:** 3, 1 (parcial), 2.

**Sabotagens obrigatórias:**

| # | Quebra deliberada | Caso que TEM de acusar |
|---|---|---|
| 3a | Emitir a pendência de achado **sem** a chave `acao` | o caso-invariante 1 ("toda pendência tem ação") |
| 3b | Trocar `p.get("auditoria")` por `p.get("auditoria") or {}` e emitir "0 achados" | o caso-invariante 2 ("camada ausente → motor calado") |
| 3c | Acrescentar `"auditoria_vencida": "pesado"` a `CAMADA_DA_REGRA` | "`auditoria_vencida` NÃO pinta o selo" |
| 3d | Escrever o guarda anterior com `startswith("auditoria")` | ele passa a ler `auditoria_nao_rodou`, que **está** em `CAMADA_DA_REGRA` — o caso tem de listar os **seis nomes exatos** e reprovar |
| 3e | **Por tamanho:** remover `auditoria_seguranca` de `NAO_AGRUPAR`. Use **12 achados altos no MESMO projeto** — com 2 o agrupamento nem dispara | "doze achados num projeto não viram '12 projetos'" |
| 3f | Fazer `elegiveis` carimbar `"claude"` fixo | "`auditoria_vencida` sai da fila com `executor='auditor'`" |
| 3g | Remover `.github/workflows/` de `fila.CAMINHOS_DE_PUBLICACAO` (`fila.py:175`) | **risco 1 do briefing**: achado apontando para `.github/workflows/ci.yml` gera diff que `fila.reprovar` (`fila.py:245`) **reprova** |
| 3h | Fazer o achado com `arquivo = "../../.ssh/config"` virar pendência | "achado com caminho recusado não vira pendência nenhuma" |

**Depende de:** Etapa 1.

---

### Etapa 4 — `execucao.auditar()` e `ExecutorAuditor`: o braço só-leitura

**Porquê:** é onde a auditoria vira corrida de verdade — e a única etapa em que "só
leitura" precisa ser **provado**, não prometido.

**Arquivos que ela toca (nenhum outro):** `execucao.py`, `agente/executor.py`,
`test_execucao.py`, `test_executor.py`, e **acrescenta classes ao fim de**
`test_auditoria.py`.

**Fazer:**

1. **`execucao.py`**:
   - `FERRAMENTAS_DE_LEITURA = ["Read","Grep","Glob"]` — constante **própria**.
     `FERRAMENTAS_OK` (`execucao.py:95`) fica **intocada**.
   - `montar_comando_de_auditoria(teto_usd, turnos, settings="")` devolvendo o argv
     exatamente como `spec.md` § *"4 — Como se prova o modo só-leitura"* manda:
     `--allowedTools Read,Grep,Glob`;
     `--disallowedTools Bash,Edit,Write,MultiEdit,NotebookEdit,Task,WebFetch,WebSearch`;
     `--json-schema <json.dumps(auditoria.ESQUEMA, ensure_ascii=True)>`;
     `--output-format stream-json --verbose`;
     `--strict-mcp-config --mcp-config {"mcpServers":{}}`;
     `--setting-sources "" --settings <settings_da_barreira()>`;
     `--max-budget-usd`; `--max-turns`.
     **Nunca `--bare`** (medido falhando com "Not logged in", `execucao.py:166`) e
     nunca modo de permissão frouxo. O prompt vai por **stdin**, como em
     `montar_comando` (`execucao.py:162-176`).
   - `auditar(...)`, irmã de `iniciar()` (`execucao.py:833`): reusa `criar_copia`
     (`:587`), `ambiente_da_filha` (`:565`), `settings_da_barreira` (`:220`),
     `interpretar_linha` (`:281`), `custo_do_evento` (`:386`) e **a mesma trava global
     `_trava`/`_proc`**. **NÃO passa** por `_absorver` (`:1014`) nem por
     `_fechar_com_pedido_de_alteracao` (`:1053`) — auditoria não abre PR.
     **Não toque em `iniciar()`.** Ela tem 91 testes.
2. **`agente/executor.py`**: `ExecutorAuditor(Executor)`, com `nome = auditoria.EXECUTOR`
   (a **constante**, não a string literal), e a entrada na tabela `EXECUTORES`. Herda
   `_recusar_se_nao_pode` (`agente/executor.py:55`), que chama `tarefas.pode_rodar`
   **antes** de montar qualquer comando.
3. **Nenhum teste chama o binário `claude`.** Script de mentira que cospe
   `stream-json`, no molde de `test_executor.py`.

**Verificação:**

```
python test_execucao.py
python test_executor.py
python test_auditoria.py
```

**Critérios do briefing:** 1, 5.

**Sabotagens obrigatórias — `OComandoEhSoLeitura` tem quatro casos, e cada um reprova
sozinho:**

| # | Quebra deliberada | Caso que TEM de acusar |
|---|---|---|
| 4a | Acrescentar `"Bash"` a `FERRAMENTAS_DE_LEITURA` | caso (a): `Bash`/`Edit`/`Write` **não** aparecem em `--allowedTools` |
| 4b | Remover `WebFetch` de `--disallowedTools` | caso (b): os oito nomes de escrita/rede aparecem em `--disallowedTools` |
| 4c | Remover o par `--settings` do argv | caso (c): `--settings` continua trazendo o hook de `barreira.py` |
| 4d | Acrescentar `"Write"` a `FERRAMENTAS_DE_LEITURA` | caso (d): a interseção entre `FERRAMENTAS_DE_LEITURA` e `execucao.VIGIADAS` (`execucao.py:203`) é **vazia** |
| 4e | Acrescentar uma chamada a `_fechar_com_pedido_de_alteracao` dentro de `auditar` | o caso que lê `inspect.getsource(execucao.auditar)` e exige a ausência de `_absorver` e `_fechar_com_pedido_de_alteracao` |
| 4f | Dar a `auditar` uma trava própria | "com uma sessão de conserto rodando, `auditar` é recusada" — a trava É compartilhada, senão o teto de R$ 50 é conferido duas vezes contra o mesmo saldo |
| 4g | Remover a chamada a `_recusar_se_nao_pode` de `ExecutorAuditor.rodar` | "gasto acima do teto do dia → desfecho com `recusada=True`, sem montar comando" (**critério 5**) |
| 4h | Escrever `nome = "auditor"` literal e mudar `auditoria.EXECUTOR` | **identidade**: `auditoria.EXECUTOR` é o mesmo objeto usado por `ExecutorAuditor.nome` e é a chave em `EXECUTORES` |
| 4i | Interpolar o conteúdo de um arquivo no gabarito | `OTextoDoRepoNaoViraOrdem` (a): a ordem plantada num `README.md` de mentira **não aparece em lugar nenhum** do prompt montado |
| 4j | Remover `so_dado` de `auditoria.limpar` | `OTextoDoRepoNaoViraOrdem` (b): um `</dados-coletados-nao-confiaveis>` literal dentro de `frase` é neutralizado |

**Depende de:** Etapa 1 (conflito de arquivo em `execucao.py` e `test_auditoria.py`).

---

### Etapa 5 — `servir.py`: as duas rotas e a validação no `_resultado`

**Porquê:** é a fronteira. É onde o texto que subiu do agente para de ser promessa e
passa por código nosso.

**Arquivos que ela toca (nenhum outro):** `servir.py`, `test_servir.py`.
**`test_rotas.py` é SOMENTE LEITURA nesta etapa.**

**Fazer:**

1. `import auditoria` no topo de `servir.py`.
2. Duas rotas, ambas com acesso **`dado`** (`servir.ACESSOS`, `servir.py:2483`):

   | caminho | método | função | acesso |
   |---|---|---|---|
   | `/api/auditoria` | `GET` | `Hub._auditoria` | `dado` |
   | `/api/auditoria/pedir` | `POST` | `Hub._auditoria_pedir` | `dado` |

   **`dado`, e não `cortina`:** achado carrega caminho de arquivo, número de linha e
   trecho de código-fonte privado. E `assets/painel.js`, que desenha a tela, já exige
   sessão (`servir.py:2572`).
3. `_auditoria_pedir` escreve na fila com `banco.enfileirar` e **ganha balcão próprio**,
   reusando o que já existe: `cortina.registrar_tentativa(chave, time.time(),
   balcao="auditoria", teto=self.TETO_DE_AUDITORIAS)`, no molde de `servir.py:1440`,
   `:1594`, `:1853`, `:1963`. **Não invente mecanismo novo.**
4. Dentro de `_resultado` (`servir.py:1951`): quando o desfecho traz `achados`, chama
   `auditoria.validar` **primeiro**; só com `(achados, "")` é que
   `banco.gravar_auditoria` grava a corrida `ok` e os achados **numa transação**. Saída
   inválida grava a corrida com `estado='falha'` e o `motivo` em português, **não fecha
   os achados anteriores**, e o projeto continua com o carimbo da última auditoria boa.
5. O `teto_usd` de `_tarefa_pendente` (`servir.py:1918`) usa
   `tarefas.teto_da_auditoria(...)` quando o executor é o auditor, e
   `tarefas.teto_da_sessao(...)` no resto.
6. **Nomes:** `test_rotas.PROIBIDO` (`test_rotas.py:40`) casa contra caminho **e** nome
   da função. `_auditoria` e `_auditoria_pedir` passam; `_executar_auditoria` **não**
   passaria, e é bom que não passe. Nada de `montar_comando_*` em `servir.py`.
7. `servir.py` continua **sem** importar `execucao` e `fila` (`test_rotas.AMPUTADOS`).

**Verificação:**

```
python test_servir.py
python test_rotas.py
python test_tarefas_nao_publicam.py
```

Os dois últimos rodam **sem uma linha editada** — é isso que fecha o critério 7.

**Critérios do briefing:** 7, 2, 1.

**Sabotagens obrigatórias:**

| # | Quebra deliberada | Caso que TEM de acusar |
|---|---|---|
| 5a | Trocar o acesso de `/api/auditoria` para `"cortina"` | "as duas rotas de auditoria têm acesso `dado`" |
| 5b | Renomear `Hub._auditoria_pedir` para `Hub._executar_auditoria` | `test_rotas.test_nenhuma_funcao_de_rota_cheira_a_execucao` (não editar `test_rotas.py`: ele já pega) |
| 5c | Gravar sem passar por `auditoria.validar` | "desfecho com `achados` malformado grava corrida `falha` e **nenhum** achado" |
| 5d | Fazer a corrida inválida **fechar** os achados anteriores | "auditoria que falhou não apaga o que a anterior achou" |
| 5e | **Por tamanho:** fazer `_resultado` cortar em 60 e aceitar. Envie **61 achados**, todos válidos | "61 achados são recusados inteiros, não truncados" |
| 5f | Remover o balcão de `_auditoria_pedir` | "N+1 pedidos seguidos da mesma sessão devolvem 429" |
| 5g | Importar `execucao` em `servir.py` para reusar `montar_comando_de_auditoria` | `test_rotas.test_os_nomes_amputados_sumiram` (`AMPUTADOS` inclui `"execucao"`) |

**Depende de:** Etapa 1 **e** Etapa 2.

---

### Etapa 6 — A tela Auditoria, a nona

**Porquê:** o dono não lê código. Sem tela, tudo o que as cinco etapas anteriores
fizeram existe só no banco.

**Arquivos que ela toca (nenhum outro):** `index.html`, `assets/painel.js`,
`assets/painel.css`, `test_design.py`.

**PRÉ-REQUISITO — JÁ SATISFEITO:** `docs/esteira/auditoria-profunda/design.md` existe
desde 02/09/2026 14:11 e passou no validador. **Siga o `design.md`** — desenho, tokens,
vocabulário e frases vêm de lá, aprovados. **Não invente desenho.**

**Fazer:**

1. **Nenhum arquivo novo em `assets/`.** A lista de estáticos nasce de uma leitura da
   pasta **na subida** (`servir.py:150`) e a proteção casa por caminho **exato**: um
   `assets/auditoria.js` novo nasceria **aberto**, porque só `painel.js` e `painel.css`
   estão em `ESTATICOS_COM_SESSAO` (`servir.py:2572`) — e só seria servido depois de
   reiniciar `servir.py`. A tela mora em `painel.js` e `painel.css`.
2. `index.html`: link `data-tela="auditoria"` na navegação (`index.html:63-69`) e uma
   `<section id="tela-auditoria">` dentro do `<main>` (`index.html:139`).
3. `assets/painel.js`: rota `#/auditoria` no `switch` de `navegar()`
   (`assets/painel.js:126`), usando `rota()` (`:111`), `mostrar()` (`:116`), `vazio()`
   (`:334`), `criterio()` (`:360`) e `haQuanto()` (`:52`, o carimbo em português).
4. **Achado é escrito com `textContent`, nunca `innerHTML`** — padrão já usado em
   `assets/painel.js:73` e `:214`. É a quarta barreira contra o texto do repositório
   auditado.
5. **Três estados com palavras diferentes:** *"nunca foi auditado"*, *"a auditoria
   falhou: <motivo>"* e *"auditado, nenhum achado"*. Zero achados só existe quando a
   corrida terminou `ok` com lista vazia. É a lei 2.
6. Tudo em português. Cabe em 360px.

**Verificação:**

```
python test_design.py
```

Esperado: `OK`, e `resumo_do_que_falta()` continua imprimindo o que o teste **não**
cobre (o olho humano em 360×640). Mais uma olhada em `http://localhost:4777` depois da
Etapa 5.

**Critérios do briefing:** 6.

**Sabotagens obrigatórias:**

| # | Quebra deliberada | Caso que TEM de acusar |
|---|---|---|
| 6a | Renomear a seção para `id="tela-audit"` | "existe uma `<section id="tela-auditoria">` **e** um `data-tela="auditoria"` na navegação **e** um `case "auditoria":` em `navegar()` — os três, casados entre si" |
| 6b | **A armadilha tautológica:** escrever o guarda como `assertIn("auditoria", html)`. Com `id="tela-auditoria"` no arquivo, ele **não pode reprovar** | reescreva casando as **três** ocorrências e prove: apague só o `case "auditoria":` do `painel.js` e exija vermelho |
| 6c | Trocar um `textContent` por `innerHTML` no desenho do achado | "nenhum campo de achado é escrito com `innerHTML`" |
| 6d | Fazer a tela escrever "0 achados" quando a corrida foi `falha` | "os três estados têm frases diferentes" (lei 2) |
| 6e | Acrescentar `assets/auditoria.js` e apontar a tela para ele | "`ESTATICOS_COM_SESSAO` continua com exatamente dois nomes: `painel.js` e `painel.css`" |

**Depende de:** nada em código (sem conflito de arquivo com 4 e 5) — **mas a olhada no
navegador só fecha depois da Etapa 5**.

---

### Etapa 7 — Fechamento: o número do teto, a suíte inteira e a CI

**Porquê:** *"rodar dois arquivos não é rodar a suíte"* — em 02/09 a CI ficou vermelha
num guarda que lê código-fonte porque um rename mudou a função de lugar e só dois
arquivos tinham sido rodados. `test_rotas`, `test_tarefas_nao_publicam`, `test_imagem`,
`test_publicar` e `test_design` quebram com mudança feita em **outra** etapa.

**Arquivos que ela toca:** `tarefas.py` (**apenas** o valor de `TETO_AUDITORIA_USD`, se
o dono decidiu diferente) e `.github/workflows/ci.yml` (**apenas** se algum passo
faltar). Nenhum outro `.py`.

**Fazer:**

1. Se o dono decidiu teto diferente de US$ 1,50, troque `tarefas.TETO_AUDITORIA_USD` —
   **uma linha**, com comentário dizendo a data e quem decidiu, no molde de
   `tarefas.py:47-49`.
2. Confira que **todo** `test_*.py` tem passo próprio no `ci.yml` (o passo `ci.yml:71-77`
   cobra a lista).
3. Confira que **nenhuma variável de ambiente nova** foi introduzida. Esta entrega
   **não tem** nenhuma, e é decisão consciente da spec: os tetos são constantes em
   `tarefas.py`. `test_publicar.OContainerRecebeOQueOCodigoLe` tem de continuar verde
   **sem edição** do `docker-compose.yml`. Se ficar vermelho, alguém introduziu leitura
   de ambiente em `servir.py` ou `banco.py` — conserte o código, não o guarda.
4. Rode a suíte inteira.

**Verificação (leva mais de 2 minutos):**

```
python test_auditoria.py
python test_tarefas.py
python test_banco.py
python test_regras.py
python test_fila.py
python test_execucao.py
python test_executor.py
python test_servir.py
python test_rotas.py
python test_tarefas_nao_publicam.py
python test_imagem.py
python test_publicar.py
python test_design.py
python test_sse.py
python test_agente.py
python test_conectar_ponta_a_ponta.py
python test_barreira.py
python test_cortina.py
python test_autenticacao.py
python test_coletar.py
python test_coletar_pesado.py
python test_memoria.py
python test_p256.py
python test_github_app.py
python test_passkey.py
python test_conectador.py
```

Esperado: `OK` em **todos**. Um único `FAILED` reprova a etapa.

**Critérios do briefing:** 8, 9, 7 (reconfirmado).

**Sabotagens obrigatórias:** nenhuma nova. Esta etapa **re-executa** 1i, 2a, 4e e 5g em
árvore limpa, para provar que nenhuma etapa anterior deixou um guarda incapaz de
reprovar.

**Depende de:** todas as anteriores.

---

## Ordem, paralelismo e o gargalo

**Rodada 1 (em paralelo — nenhum arquivo em comum):** Etapa 1 · Etapa 2
**Rodada 2 (em paralelo — nenhum arquivo em comum):** Etapa 3 · Etapa 4 · Etapa 5 · Etapa 6
**Rodada 3 (sozinha):** Etapa 7

### Sequencial obrigatório, e por quê

- **1 → 3, 1 → 4, 1 → 5:** `auditoria.py` e as constantes de `tarefas.py` são
  importadas pelas três. Além disso, **1 e 4 editam o mesmo `execucao.py` e o mesmo
  `test_auditoria.py`** — é conflito de arquivo, não só de dependência. A Etapa 1 mexe
  **só** na mudança de casa de `so_dado`; a Etapa 4 acrescenta
  `FERRAMENTAS_DE_LEITURA`, `montar_comando_de_auditoria` e `auditar`.
- **2 → 5:** `servir._resultado` chama `banco.gravar_auditoria`, e `_tarefa_pendente`
  depende do `LEFT JOIN achado` em `tarefa_para_maquina`.
- **6 depois de 5 para a verificação visual:** o desenho pode ser escrito antes, mas a
  tela só busca dado depois de `/api/auditoria` existir.
- **7 por último, sempre.**

**O gargalo é a Etapa 1** — a única que trava três outras. Se houver executor livre no
começo, despache 1 e 2 juntas: a 2 não espera ninguém.

---

## O que não se conseguiu confirmar na escrita do plano

1. **`design.md` não existia** quando o plano foi escrito; passou a existir às 14:11 do
   mesmo dia e a Etapa 6 foi desbloqueada acima.
2. **O choque de nome com `auditoria_nao_rodou`** (`regras.py:241`, `:479`, `:587`) é
   achado do planejador; a spec não o previu. **Conferido no código.** A mitigação está
   escrita (nome exato, sabotagem 3d), mas quem escrever a Etapa 3 deve reler
   `regras.py:230-250` antes de encostar em `_do_projeto`. Se as duas regras confundirem
   o dono **na tela**, isso é decisão de produto que volta ao portão, não conserto de
   executor.
3. **`MAX_TURNOS_AUDITORIA` não tem valor na spec.** Sugerido 60 na Etapa 1; é palpite,
   não decisão. A primeira auditoria real vira medição.
4. **`TETO_AUDITORIA_USD`** segue com US$ 1,50 como padrão recomendado, aguardando
   confirmação do dono. Trocar é uma linha, na Etapa 7.
5. **O planejador não rodou nenhum teste e não alterou nenhum `.py`** — é somente
   leitura. Tudo que afirma sobre o estado atual vem de leitura de código, com
   arquivo:linha citado.
6. **Se `--json-schema` não existir no binário instalado**, a Etapa 4 continua verde (o
   guarda lê o argv montado, não roda o `claude`) e o defeito só aparece na primeira
   auditoria real. Não é corrigível por teste — registrado aqui de propósito.

---

## Fora deste plano, mencionado e não planejado

- `regras.ROTULO_REGRA` e `CAMADA_DA_REGRA` estão virando mapas longos e paralelos;
  poderiam ser um só. **Não refatore** — não foi pedido, e mexer neles é mexer no que
  `test_regras.py` cobre.
