# Plano de execução — Conectar simples, entrega B (o ajudante no servidor)

Ramo `feat/conectar-servidor`. Contrato: `docs/esteira/conectar-servidor/{briefing,spec,design}.md`.
Escrito pelo neguin-planner em 09/10/2026 (gravado pelo coordenador). **Este plano corrige o
spec em 7 pontos (seção "Premissas que não se confirmaram"); onde divergirem, vale o plano.**

## Contexto verificado

- Pareamento da A: `servir.py:1650 _agente_pedir` lê só `maquina` do corpo (charset
  `NOME_DE_COMPUTADOR_OK`, ≤40); `:1688 _agente_esperar`; `banco.py:3415
  resgatar_pedido_de_computador` (INSERT com `so_mede=1` em `:3445`); `ver_pedido_de_computador`
  (`:3338`) devolve `{codigo, maquina, minutos, expira_em, estado, mesma_rede}`. Tabelas `maquina`
  (`:332`) e `pedido_de_computador` (`:385`) **não têm `tipo`**.
- Migrações em `banco.migrar()` (`:729-751`); molde `_migrar_maquina_conectar_simples` (`:826`):
  `BEGIN IMMEDIATE`, relê `table_info` dentro da transação, `_religar_fk`. Tabelas novas da A
  entraram só em `ESQUEMA` + `FILHAS_DE_USUARIO` (`:756`).
- Trancas atuais: `_voz_maquina` (`:3741`) já 403 para `so_mede`. `_relatorio` (`:2516`) e
  `_resultado` (`:2756`) não olham tipo; `_agente_pacote` (`:1778`) entrega a qualquer máquina;
  `_relatorio` devolve `tarefa` (`:2550`).
- `_despachar` (`:750`) faz `self._maquina = banco.maquina_por_token(...)` = `SELECT m.*`
  (`:3471`): coluna nova `tipo` chega sozinha.
- `_dados` (`:806`) poda ocultos depois de `_estado` e tira `documentacao` (`:858`): lugar do
  acréscimo, depois do motor.
- `_eventos`/`_empurrar` (`:2995`/`:3035`): sem `id`, hoje só sonda e ping. `test_sse.py` abre sem
  `id` e não cobra ausência de eventos.
- `_injetar(fonte, alvo)` (`:1823`, estático, troca a linha `# DERVS:ALVO`); `_endereco_publico`
  (`:1812`). Reusar.
- `test_rotas.py:42 PROIBIDO = acao|execucao|exec|terminal|pty|shell|comando|grafo` sobre caminho
  e `funcao.__name__`: casam "instal**acao**", "autoriz**acao**", "public**acao**",
  "compar**acao**", "atualiz**acao**". Passam "medicao", "ajudante", "servidor", "linha".
  `EXECUTA` (`:111`) reprova `compile`/`system`/`subprocess` alcançáveis por rota (inclui
  `re.compile` em método).
- `test_servir.py:1937 PALAVRAS_PROIBIDAS`: nenhum campo novo com token/chave/key/ssh.
- Casamento de projeto (`coletar.py:1065`): `nome.lower().replace("-","") ==
  projeto_compose.lower().replace("-","")`.
- GitHub: `PEDACO` (`coletar_github.py:455`) sem `oid`; `traduz` `:971`; `mede_deploy` `:851`
  (`buscar = buscar or _gh_json`); `atras_de` `:434`; `_gravar_medicao` `:1086`;
  `TETO_CHAMADAS_POR_CONTA = 1 + 2 + 3 * TETO_REPOS_POR_CONTA` (`:1246`), cobrado em
  `test_coletar_por_conta.py:413`; guarda de fonte `test_coletar_por_conta.py:765-773`.
  `coletar_github` não importa `regras` hoje.
- Kit `deploy-padrao` (`servidor/deploy`): linha `data hora PROJETO QUEM versao resultado` (6
  campos). Versão `AAAAMMDD-HHMMSS-<commit curto>`. Resultados: `OK`, `OK(voltou)` (versão gravada
  = no ar); `OK(estado-original)` (versão termina em `-antes-do-primeiro-deploy`);
  `FALHOU(backup)` e `FALHOU(<etapa>)-voltou` (gravam a versão que NÃO subiu);
  `FALHOU-AO-VOLTAR` (estado desconhecido). O próprio kit lê "última no ar" com `$6 ~ /^OK/`.
- Tela: `ligarFluxo(id)` (`painel.js:3963`) com um único `FLUXO`; `pintarConectar` (`:2636`);
  cartão "Seus sites" fixo em `index.html:438-484`; marcadores `/* === CONECTAR: início/fim === */`
  (`:1394`/`:3219`) delimitam o guarda de jargão (`test_conectar_tela.py:1723`); `haQuanto` `:55`;
  `campos(var, fn)` em `test_progresso_fio.py:74`.
- Imagem/CI: `Dockerfile` copia por nome (`conectador.py` em `:126`); `test_imagem.py` cobra lista
  e "lido, nunca importado"; `ci.yml` lista testes à mão, passo "ficou de fora" (`:70`).

### Premissas que não se confirmaram (decididas)

1. "Commit no ar" = **última linha com resultado `^OK`** do projeto; `FALHOU-AO-VOLTAR` depois
   dela → "não sei"; versão `...-antes-do-primeiro-deploy` → "não sei".
2. ACL: a pasta `/var/log/deploy` é 750 root. `setfacl -m u:dervs-ajudante:x` na pasta, `r` no
   arquivo e `-d -m u:dervs-ajudante:r` na pasta.
3. Teto de `dados`: **128 KiB** (64 não cabe 200 sistemas + 200 publicações).
4. `github.no_ar` é **lista** `[{sha, atras}]` (vários servidores).
5. `maquinas_do_usuario` e `maquinas_que_calaram` filtram `tipo = 'computador'`: o servidor só
   aparece em `servidores_ligados`; o VOZ não recebe aviso de servidor.
6. O guarda de fonte do ajudante proíbe `agente/pacote|relatorio|resultado|voz` e `executor`
   (não "agente": as rotas `/agente/pedir|esperar|servidor` são usadas).
7. O corpo da medição não leva o nome do servidor: vale `maquina.nome` do pareamento.

---

## Contratos (ninguém muda um destes sem mudar aqui)

### C0. Rotas novas

| Rota | Método | Função | Acesso | Balcão |
|---|---|---|---|---|
| `/agente/servidor` | POST | `Hub._agente_servidor` | maquina | `servidor_relato`, chave `maquina:<id>`, `TETO_DE_RELATOS_DE_SERVIDOR = 60` / 900 s |
| `/ajudante/servidor.py` | GET | `Hub._ajudante_do_servidor` | aberta | `ajudante`, por origem, `TETO_DE_AJUDANTES = 30` |
| `/api/ajudante/linha` | GET | `Hub._ajudante_linha` | dado | nenhum (leitura com sessão, não cria estado) |

Ajudantes: `_bytes_do_ajudante()`, `_maquina_do_servidor()`, `Hub.SO_OLHA`. Nenhum nome com
`acao`/`exec`. Sem `re.compile` alcançável por rota: sha validado por
`7 <= len(s) <= 40 and all(c in "0123456789abcdef" for c in s)`. **Nenhuma variável de ambiente
nova** (compose e `test_publicar` não mudam).

### C1. `tipo` no pedido e na máquina

- `POST /agente/pedir` aceita `{"maquina": "vps-ovh", "tipo": "servidor"}`; sem `tipo` →
  `"computador"`; fora de `{"computador","servidor"}` → 400 `{"erro":"pedido invalido"}`.
- `GET /api/pedido` devolve também `"tipo"`.
- Resgate copia `tipo` para `maquina.tipo`; sempre `so_mede=1`.
- `Hub.SO_OLHA = {"erro": "este servidor so olha"}`. Máquina `tipo='servidor'` leva **403
  `SO_OLHA`**, conferido **antes do balcão**, em `/agente/relatorio`, `/agente/resultado`,
  `/agente/pacote` e `_voz_maquina` (todas as `/agente/voz/*`).

### C2. Banco (E2)

```sql
-- maquina e pedido_de_computador ganham (ESQUEMA + migracao _migrar_tipo_de_maquina):
tipo TEXT NOT NULL DEFAULT 'computador' CHECK (tipo IN ('computador','servidor'))

CREATE TABLE IF NOT EXISTS medicao_de_servidor (
  maquina_id INTEGER PRIMARY KEY REFERENCES maquina(id) ON DELETE CASCADE,
  usuario_id INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  medido_em  TEXT NOT NULL CHECK (medido_em LIKE '____-__-__T__:__:__+00:00'),
  dados      TEXT NOT NULL CHECK (length(dados) <= 131072));
```

- `_migrar_tipo_de_maquina(con)`: um `ALTER` por tabela, cada um com checagem própria de "já
  rodou", relendo `table_info` dentro do `BEGIN IMMEDIATE`; tabela ausente → nada; `_religar_fk`;
  nunca `executescript`. Chamada em `migrar()` depois de `_migrar_pedido_origem`.
- `FILHAS_DE_USUARIO` ganha `"medicao_de_servidor"`. `MAX_BYTES_DA_MEDICAO = 128 * 1024`.
- `abrir_pedido_de_computador(nome, minutos, con=None, origem="", tipo="computador")`;
  `ver_pedido_de_computador` devolve também `tipo`; `resgatar_pedido_de_computador` copia `tipo`.
- `gravar_medicao_de_servidor(maquina_id, usuario_id, dados: dict, con=None) -> str`: devolve
  `medido_em = agora()` do DERVS; UPSERT + `UPDATE maquina SET visto_em` na **mesma transação**;
  `ValueError` se o JSON passar de `MAX_BYTES_DA_MEDICAO`.
- `medicoes_de_servidor(usuario_id, con=None) -> list[dict]`: itens
  `{"maquina_id": int, "nome": str, "medido_em": iso|None, "dados": dict|None}`; **toda** máquina
  viva `tipo='servidor'` da conta (inclusive pareada sem medição); ordem `nome`, `id`.
- `ultima_medicao_de_servidor(usuario_id, con=None) -> str|None`: `MAX(medido_em)` dos servidores
  vivos da conta.
- `maquinas_do_usuario` e `maquinas_que_calaram`: `AND m.tipo = 'computador'`.

### C3. `POST /agente/servidor` (corpo; lista fechada)

```json
{"versao": 1,
 "docker_mudo": false,
 "servidor": {"ligado_s": 123456, "carga_1m": 0.12, "carga_5m": 0.3, "carga_15m": 0.25,
              "memoria_total_kb": 4000000, "memoria_disponivel_kb": 1200000,
              "disco_total_b": 80000000000, "disco_livre_b": 30000000000},
 "sistemas": [{"nome": "dervs-app", "projeto": "dervs", "estado": "running",
               "saude": "healthy", "desde": "2026-10-08T12:00:00+00:00",
               "reinicios": 0, "imagem": "dervs:vps", "sha": ""}],
 "publicacoes": [{"projeto": "dervs", "quando": "2026-09-29T15:15:00+00:00",
                  "sha": "96eb3fc", "resultado": "OK"}]}
```

Ordem das recusas: 401 sem token (despacho) → 403 `{"erro":"so servidor"}` se `tipo !=
'servidor'` → 429 `{"erro":"nao deu"}` balcão → 415 sem JSON (`_veio_como_json`) → 400
`{"erro":"corpo invalido"}` se não for dict (corpo lido com `teto = 512 KiB`) → 400
`{"erro":"medicao grande demais"}` se o resultado limpo passar de `MAX_BYTES_DA_MEDICAO`.

Validação (chave desconhecida em qualquer nível: descartada, +1 em `invalidos`; item com campo
obrigatório torto: descartado inteiro, +1):
- `docker_mudo`: bool, senão `None`.
- `servidor`: cada número finito, `>= 0`, não-bool, int `< 2**63`; torto → `None`.
- `sistemas` (≤200): `nome` obrigatório 1-128, sem controle, gravável (molde
  `_texto_gravavel`/`_limpo`); `projeto` ≤128 (`""` ok); `estado` obrigatório de `{created,
  running, paused, restarting, removing, exited, dead}`; `saude` de `{"", starting, healthy,
  unhealthy}` senão `""`; `desde` exatamente `AAAA-MM-DDTHH:MM:SS+00:00` (25 chars, `fromisoformat`
  aceita) senão `""`; `reinicios` int `>= 0` senão `None`; `imagem` ≤200; `sha` hex minúsculo
  7-40 senão `""`.
- `publicacoes` (≤200): `projeto` obrigatório 1-128; `quando` como `desde`; `sha` como acima;
  `resultado` ≤40, só `[A-Za-z0-9()_-]`, senão `""`.

200: `{"ok": true, "invalidos": N}`. **Nunca `tarefa`.** Grava `dados` limpo + `invalidos`.

### C4. `GET /ajudante/servidor.py` e `GET /api/ajudante/linha`

- `Hub.AJUDANTE = AQUI / "ajudante_servidor.py"`.
- `_bytes_do_ajudante() -> bytes|None`: lê; exige exatamente uma linha terminada em
  `# DERVS:ALVO`; `self._injetar(fonte, self._endereco_publico())`; codifica `ascii` com LF;
  `None` em `OSError`/`UnicodeError`/`ValueError`. **As duas rotas usam esta mesma função.**
- `/ajudante/servidor.py`: 200 `application/octet-stream`, `Content-Disposition: attachment;
  filename="dervs-ajudante.py"`, `Content-Length`; 503 `{"erro":"o ajudante nao esta nesta
  copia"}`; 429 balcão `ajudante`; não cria estado.
- `/api/ajudante/linha`: 200 `{"linha": "cd \"$(mktemp -d)\" && curl -fsSL
  <alvo>/ajudante/servidor.py -o dervs-ajudante.py && echo \"<sha256>  dervs-ajudante.py\" |
  sha256sum -c - && sudo python3 -I dervs-ajudante.py", "sha256": "<64 hex>", "endereco":
  "<alvo>/ajudante/servidor.py"}` (dois espaços entre sha e nome; pasta nova e privada, e `-I`
  isola o caminho de busca do Python — revisão de segurança, 09/10/2026); 503 igual; 403
  `{"erro":"entre de novo"}` se a sessão venceu.

### C5. `GET /api/dados` (em `_dados`, depois da poda dos ocultos)

- `"servidores_ligados"` (lista, sempre presente), um item por `banco.medicoes_de_servidor`:
  ```json
  {"maquina_id": 7, "nome": "vps-ovh", "estado": "medido"|"sem_dados",
   "medido_em": "iso"|null, "docker_mudo": false|true|null,
   "sistemas": [{"nome","projeto","estado","saude","desde","reinicios"}]}
  ```
  `estado` = `regras.estado_do_servidor(medido_em)`; `sistemas` por `nome`, **sem** `imagem`/`sha`;
  sem medição: `sistemas: []`, `docker_mudo: null`.
- Cada `p` em `projetos` ganha `"no_ar"` (lista, sempre presente):
  ```json
  {"maquina_id": 7, "servidor": "vps-ovh", "estado": "medido"|"sem_dados",
   "medido_em": "iso", "sha": "96eb3fc"|null, "publicado_em": "iso"|null,
   "veredito": "igual"|"atras"|"diferente"|"nao_sei", "atras": 3|null}
  ```
  Um por servidor onde `regras.no_ar_do_projeto(p["nome"], dados)` não é `None`. `sem_dados` →
  veredito `nao_sei`, `atras` `null`; senão `regras.comparar_no_ar(sha, p.get("github"))`.
- `banco.montar_estado` **não muda.**

### C6. `/api/eventos` sem `id`

Em `_empurrar`, só com `alvo` vazio: a cada volta lê `banco.ultima_medicao_de_servidor(usuario_id)`;
a primeira leitura é base (não emite); a cada mudança emite `event: servidor` com
`data: {"medido_em": "<iso>"}`, sem `ident`. Com `id`, nada muda. Não mexer em cabeçalho, sonda,
ping, `SEGUNDOS_DE_VIDA`, `FLUXOS_POR_SESSAO` nem nginx.

### C7. Camada `github` (E3)

- `traduz` ganha `"head_sha"` = `defaultBranchRef.target.oid` se hex minúsculo de 40, senão `""`.
  `PEDACO`: `target { ... on Commit { oid statusCheckRollup { state } } }`.
- `_gravar_medicao` grava `novo["no_ar"] = [{"sha": "96eb3fc", "atras": 3}]` (≤
  `MAX_SHAS_NO_AR = 3`): um por sha distinto no ar, de `banco.medicoes_de_servidor(dono, con=con)`
  lido **uma vez fora do laço** em `try/except Exception: []`, filtrado por
  `regras.no_ar_do_projeto`; só sha não vazio, **não** prefixo de `head_sha`, cujo `compare`
  respondeu; `atras` de `atras_de`. Sem servidor ou tudo igual → `[]`.
- `mede_no_ar(slug, branch, head_sha, shas, buscar=None) -> list`: `buscar = buscar or _gh_json`;
  uma chamada `repos/<slug>/compare/<sha>...<branch>` por sha; compare falhou → item ausente.
- `TETO_CHAMADAS_POR_CONTA = 1 + 2 + (3 + MAX_SHAS_NO_AR) * TETO_REPOS_POR_CONTA`.

### C8. `regras.py` (E0)

```python
VALIDADE_DO_SERVIDOR = 180          # FORA de VALIDADE: o selo nao muda nesta entrega

def estado_do_servidor(medido_em, agora=None) -> str:   # "medido" | "sem_dados"
    # sem carimbo legivel -> "sem_dados"; idade > 180 -> "sem_dados" (reusa _idade)

def no_ar_do_projeto(nome: str, dados) -> dict | None:
    # dados = o `dados` de UMA medicao (pode ser None -> None).
    # casa por str(x).lower().replace("-", "") contra sistemas[].projeto e publicacoes[].projeto.
    # nada casou -> None.
    # sha: os `sha` nao-vazios dos sistemas casados em estado "running"; todos iguais -> esse;
    #      divergem -> ""; nenhum -> o `sha` da publicacao casada.
    # devolve {"sha": str ("" = nao sei), "publicado_em": str ("" se nao ha)}

def comparar_no_ar(sha, github) -> dict:   # {"veredito": ..., "atras": int|None}
    # sha invalido/vazio -> nao_sei; github nao-dict ou head_sha invalido -> nao_sei;
    # head_sha.startswith(sha) -> igual;
    # item de github["no_ar"] com item["sha"] == sha e int atras > 0 -> atras, N;
    # senao -> diferente.
```

### C9. Ajudante (E1): interface que o F usa

Arquivo único, ASCII, só biblioteca padrão, Python 3.8. Uma linha `ALVO = ""   # DERVS:ALVO`.
`main(argv=None) -> int`: sem argumento → `instalar`; `medir`; `remover`.

```python
instalar(alvo=ALVO, raiz="/", rodar=None, abrir=None, dormir=time.sleep, eh_root=None,
         dono=None, nome=None, saida=print) -> int
medir(alvo=ALVO, raiz="/", rodar=None, abrir=None) -> int
remover(raiz="/", rodar=None, eh_root=None) -> int
rodar(argv: list, prazo: float) -> (bool, str)   # padrao: subprocess.run(lista, sem shell)
abrir(metodo, url, corpo: dict|None, token: str|None, prazo: float) -> (int, dict|None)
```

`raiz` prefixa: `/var/lib/dervs-ajudante/agente.json` (0600, `{"alvo","token"}`),
`/opt/dervs-ajudante/dervs-ajudante.py`, `/etc/systemd/system/dervs-ajudante.{service,timer}`,
`/var/log/deploy/historico.log`, `/proc/{uptime,loadavg,meminfo}`, `os.statvfs(raiz)`.
`dono(caminho, usuario)` padrão `shutil.chown`. Saídas: `OK=0`, `SEM_ROOT=2`, `SEM_REQUISITO=3`,
`SEM_PAREAMENTO=4`, `SEM_REDE=5`, `RECUSADO=6`. Constantes cobradas por igualdade:

```python
ARGV_DO_PS = ("docker","ps","-aq","--no-trunc")
FORMATO_DO_INSPECT = '{{.Name}}\t{{.State.Status}}\t{{if .State.Health}}{{.State.Health.Status}}{{end}}\t{{.State.StartedAt}}\t{{.RestartCount}}\t{{.Config.Image}}\t{{index .Config.Labels "com.docker.compose.project"}}\t{{index .Config.Labels "org.opencontainers.image.revision"}}'
ARGV_DO_INSPECT = ("docker","inspect","--format", FORMATO_DO_INSPECT)   # + ids, no maximo 200
```

### C10. Nomes no `painel.js` que o fio lê

| Função | Lê |
|---|---|
| `cartaoDosServidores()` | `ESTADO.servidores_ligados` |
| `linhaDeServidorLigado(s)` | `s.maquina_id`, `s.nome`, `s.estado`, `s.medido_em`, `s.docker_mudo`, `s.sistemas` |
| `linhaDeSistema(x)` | `x.nome`, `x.estado`, `x.saude`, `x.desde`, `x.reinicios` |
| `linhaDoNoAr(n)` | `n.servidor`, `n.estado`, `n.medido_em`, `n.sha`, `n.publicado_em`, `n.veredito`, `n.atras` |
| `blocoDaLinhaDoAjudante(d)` | `d.linha`, `d.sha256` |
| `pintarAutorizar(p)` | os campos de hoje + `p.tipo` |

Literais: `fetch("/api/ajudante/linha"`, `new EventSource("/api/eventos")` (sem `?id`),
`addEventListener("servidor"`.

---

## Riscos e o que nenhum teste prova

1. Docker e systemd de verdade não rodam na CI (só dublês). F-2 numa VM/VPS: o `--format` com
   rótulo ausente (`""` ou `<no value>`: o ajudante trata ambos como `""`); `ProtectSystem=strict`
   com o soquete; docker CLI sem `HOME` (se falhar: `Environment=DOCKER_CONFIG=/var/lib/dervs-ajudante/docker`).
2. Grupo `docker` = root: o "só olhar" é do código, não do SO. A tela diz. Revisão de segurança
   obrigatória (VPS hospeda o Ajudei).
3. dervs.com.br tomado vê inventário, não ganha comando. O SHA-256 prova integridade, não origem.
4. Local: `ALVO` vem do `Host`; host diferente na VM → resumo não casa (só local).
5. `remover` não revoga a máquina no DERVS (fica "Sem dados"). **Fechado em 09/10/2026:** cada
   servidor do cartão tem "Desligar este servidor", que chama a mesma `POST /api/maquinas/remover`
   (o `usuario_id` no `UPDATE` recusa máquina de outra conta). Tirar é os dois passos: `remover` no
   servidor e o botão no painel. Colar a linha de novo num servidor desligado pede código novo.
6. Fuso: `historico.log` é hora local; `strptime(...).astimezone(timezone.utc)` assume o TZ do
   processo. TZ diferente erra a hora (não o commit).
7. Segundo fluxo SSE por aba gasta 1 das 4 vagas: só abre com `servidores_ligados.length > 0` e
   nas telas painel/projeto/conectar.
8. "Sem dados" aparece em até 180+60 s (repintura de 1 min). Aceito.
9. CI fora até 01/11: verificação é a suíte local.
10. Armadilhas: `re.compile`/`acao`/`exec` em rota; token de teste >16 chars; `.pem` em linha de
    comando; `if __name__` no fim; chave de teste antes de importar `banco`; prazo em toda leitura
    de fluxo.

---

## Divisão por executor (por arquivo, sem sobreposição)

| Etapa | Arquivos (lista fechada) |
|---|---|
| E0 | `regras.py`, `test_regras.py` |
| E1 | `ajudante_servidor.py` (novo), `test_ajudante_servidor.py` (novo), `docs/operacao/ligar-um-servidor.md` (novo) |
| E2 | `banco.py`, `servir.py`, `test_servidor_ligado.py` (novo), `test_rotas.py` |
| E3 | `coletar_github.py`, `test_coletar.py`, `test_coletar_por_conta.py` |
| E4 | `assets/painel.js`, `assets/painel.css`, `index.html`, `test_servidor_tela.py` (novo); `test_design.py` e `test_conectar_tela.py` só se um caso existente quebrar, com motivo escrito |
| F | `test_servidor_fio.py` (novo), `Dockerfile`, `test_imagem.py`, `.github/workflows/ci.yml`, `CLAUDE.md`, `README.md`, `docs/A-APLICACAO.md`, `docs/LINKS.md` |

Ninguém edita (só roda como regressão): `test_sse.py`, `test_conectar_servidor.py`,
`test_conectar_fio.py`, `test_voz*.py`, `test_agente.py`, `docker-compose.yml`,
`infra/nginx-dervs.conf`, `conectador.*`, `agente/*`. `ci.yml` só no F; não abrir PR antes do F.
Ordem: E0 → (E1, E2, E3, E4 paralelo) → mesclar E2, E1, E3, E4 → F. Commite cedo; desfaça
sabotagem editando de volta, nunca `git checkout --`.

Regressão (Bash):
```bash
cd /c/Users/Desktop/source/repos/dervs && for t in test_*.py; do python "$t" >/dev/null 2>&1 || echo "FALHOU $t"; done
```

---

## Etapas

### E0 — As regras puras do "no ar"
Arquivos: `regras.py`, `test_regras.py`. Implementar C8; reusar `_idade` (`regras.py:587`); **não**
tocar `VALIDADE`, `CAMADA_DA_REGRA`, `camadas_do_selo`. Testes (classes novas antes do
`if __name__`): `ONoArDoProjeto` (casa com `-` e caixa; nada casa → None; rótulo vence publicação;
rótulos divergentes → `""`; só publicação → sha dela; `dados` None/lista/texto → None sem levantar);
`CompararNoAr` (prefixo curto de head de 40 → igual; `no_ar` mesmo sha `atras:3` → atras 3; sha
diferente sem item → diferente; `atras:0` → diferente; sha vazio/maiúsculo/"zz", github None,
head vazio → nao_sei); `AValidadeDoServidor` com `agora` fixo (179 s medido, 181 s sem_dados,
None/torto sem_dados, `VALIDADE_DO_SERVIDOR == 180`, `"servidor" not in VALIDADE`).
Verificação: `python test_regras.py`; sabotar `startswith`→`==` deixa vermelho.

### E1 — O ajudante: instala, pareia e mede, só olhando
Arquivos: `ajudante_servidor.py`, `test_ajudante_servidor.py`, `docs/operacao/ligar-um-servidor.md`.
Contratos C1, C3, C9; moldes `conectador.py` e `test_conectador.py`.

- Instalar: confere root → `python3 >= 3.8` → `<raiz>/run/systemd/system` →
  `shutil.which("docker")`, com código de C9 e frase em português sem jargão; `useradd --system
  --no-create-home --shell /usr/sbin/nologin --groups docker dervs-ajudante` se `id` falhar;
  `/var/lib/dervs-ajudante` 0700 do usuário; reaproveita token se `agente.json.alvo == ALVO`;
  senão `POST /agente/pedir {"maquina": <hostname limpo [A-Za-z0-9 ._-], ≤40>, "tipo": "servidor"}`,
  imprime `ALVO + "/#/conectar?autorizar=" + codigo` e o código ("abra no seu computador e digite
  o código"), espera em `/agente/esperar` respeitando `intervalo` (dobra no 429) até `minutos`;
  grava `agente.json` 0600 logo após o 200 (`dono(...)`); copia a si mesmo para
  `/opt/dervs-ajudante/` (0755 root); ACLs do item 2 das premissas se `/var/log/deploy` e
  `setfacl` existirem; `.service` (`Type=oneshot`, `User=dervs-ajudante`,
  `ExecStart=<sys.executable> /opt/dervs-ajudante/dervs-ajudante.py medir`, `NoNewPrivileges=yes`,
  `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`,
  `ReadWritePaths=/var/lib/dervs-ajudante`, `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`);
  `.timer` (`OnBootSec=30s`, `OnUnitActiveSec=30s`, `AccuracySec=1s`, `WantedBy=timers.target`);
  `systemctl daemon-reload` e `systemctl enable --now dervs-ajudante.timer`; primeira medição.
- Medir: `ARGV_DO_PS` → `ARGV_DO_INSPECT` + ids (≤200); tira `/` do nome; `<no value>` → `""`;
  `StartedAt` → 19 primeiros chars + `+00:00`, `0001-...` → `""`; `docker_mudo: true` se o `ps`
  falhar; `/proc/*` e `statvfs`; publicações: só linha de 6 campos, **descarta o campo 4 (`quem`)
  na leitura**, por projeto a última `^OK` salvo `FALHOU-AO-VOLTAR` depois (sha `""`); sha =
  `versao.split("-", 2)[2]` se hex 7-40 (`antes-do-primeiro-deploy` → `""`); `quando` local→UTC;
  `POST /agente/servidor` com `Authorization: Token <t>`; 200→0, 401→`SEM_PAREAMENTO`,
  403→`RECUSADO`, 429→0 calado, rede→`SEM_REDE`.
- Remover: `systemctl disable --now dervs-ajudante.timer`; apaga units; `daemon-reload`;
  `setfacl -x u:dervs-ajudante` (pasta, arquivo, default); `userdel dervs-ajudante`; apaga
  `/opt/dervs-ajudante` e `/var/lib/dervs-ajudante`; avisa que no DERVS fica "sem dados".
- Testes (raiz temporária, `rodar`/`abrir` falsos, sem rede/processo real): ASCII;
  `ast.parse(fonte, feature_version=(3, 8))`; uma linha `# DERVS:ALVO`; imports só da stdlib
  (`sys.stdlib_module_names`); guarda AST: literal `"docker"` só em `ARGV_DO_PS`/`ARGV_DO_INSPECT`,
  `FORMATO_DO_INSPECT ==` string de C9 escrita no teste, `subprocess` só dentro de `rodar` com lista
  e sem `shell=True`, fonte não casa
  `\bEnv\b|\.env\b|\.conf\b|\{\{\s*json|\.Config\.Env|executor|agente/(pacote|relatorio|resultado|voz)|\blogs\b`;
  sabotagem: `{{json .Config.Env}}` numa cópia em memória reprova; instalar com `abrir` 202→200
  (`agente.json`, 0600 fora do Windows, argv de `useradd`/`setfacl`×3/`systemctl`, diretivas dos
  units; rodar de novo não chama `/agente/pedir`); medir (corpo só com chaves de C3; nenhum valor
  contém o `quem` de mentira, ex. `tiba`; `OK`→`FALHOU(build)-voltou` dá sha da OK;
  `OK`→`FALHOU-AO-VOLTAR` dá `""`; `antes-do-primeiro-deploy` → `""`; `docker ps` falhando →
  `docker_mudo: true`, `sistemas: []`); remover; `if __name__` no fim.
- `docs/operacao/ligar-um-servidor.md`: roteiro completo (onde colar, o que aparece, se der
  errado, como tirar), estilo de `conectar-uma-maquina.md`.
Verificação: `python test_ajudante_servidor.py`; `python -c "open('ajudante_servidor.py','rb').read().decode('ascii')"`.

### E2 — Servidor e banco: o tipo, a medição, a linha e os 403
Arquivos: `banco.py`, `servir.py`, `test_servidor_ligado.py`, `test_rotas.py`. C0-C6; usa C8.
Moldes: `BaseServidorDeVerdade` (`test_servir.py`) como em `test_conectar_servidor.py`;
`test_sse.OFluxoAoVivo`. Reusar `_texto_gravavel`/`_numero_finito` (`servir.py:3720`/`:3732`).
Consumidores de `maquinas_do_usuario`: `servir.py:1544 _maquinas`, `:3318 _aviso_do_conserto`; de
`maquinas_que_calaram`: `:2611`. Entradas em `ROTAS` com comentário do motivo.
Testes (`test_servidor_ligado.py`, chave de teste antes de importar `banco`):
- `OTipoDoPedido`: pedir servidor → `/api/pedido.tipo` → autorizar/resgatar → `tipo='servidor'`,
  `so_mede=1`; `tipo:"x"` → 400; sem tipo → computador.
- `AMigracao`: banco sem `tipo` → colunas existem com `'computador'`; duas vezes não levanta;
  `"medicao_de_servidor" in FILHAS_DE_USUARIO`.
- `OServidorSoOlha`: token de servidor → 403 `SO_OLHA` em relatório, resultado, pacote e as 4
  `/agente/voz/*`; sabotar uma deixa vermelho; token de computador em `/agente/servidor` → 403.
- `AMedicaoDoServidor`: corpo C3 → 200 `{ok, invalidos}` sem `tarefa`; `Env` no topo e no sistema
  descartado (nem banco nem `/api/dados`), `invalidos >= 2`; `sha:"ZZZ"`→`""`; `estado:"hacked"`
  descarta; `10**30` em `reinicios`→None; `"\ud800"` no nome descarta (nunca 500); 201 sistemas →
  200; estouro → 400; 61 medições → 429 e `/agente/esperar` ainda responde; `visto_em` muda;
  `medido_em` do servidor.
- `OsDadosDoPainel`: projeto `clinica-agenda` por computador; camada github com `head_sha` de 40
  e `no_ar:[{"sha":"96eb3fc","atras":3}]`; servidor mede `projeto:"clinicaagenda"`,
  `sha:"96eb3fc"` → `servidores_ligados[0]` com chaves C5 e `no_ar[0].veredito == "atras"`,
  `atras == 3`; `medido_em` velho → `sem_dados`/`nao_sei`; sem casamento → `[]`;
  `montar_estado` sem `no_ar`; outra conta nunca aparece; `/api/maquinas` sem o servidor;
  `maquinas_que_calaram` sem o servidor.
- `ALinhaDoAjudante`: `Hub.AJUDANTE` remendado → GET sem sessão 200 e `sha256(bytes) ==
  /api/ajudante/linha.sha256`; linha casa o molde C4; sem marca ou byte não-ASCII → 503 nas duas;
  linha sem sessão → 401; 31º GET → 429; `pedido_de_computador` não cresce.
- `OFluxoAvisaQueOServidorMediu`: `/api/eventos` sem id + gravação → `event: servidor` em ≤6 s
  com o `medido_em`; com `?id=x` nenhum em 3 s; prazo em toda leitura.
- `test_rotas.py`: classe `AsRotasDoServidorLigado` (molde `AsRotasDoConectarSimples`).
Verificação: `test_servidor_ligado`, `test_rotas`, `test_servir`, `test_conectar_servidor`,
`test_sse`, `test_voz`, `test_voz_avisos`, `test_agente`, `test_banco`, `test_publicar` verdes; depois
a regressão inteira.

### E3 — O GitHub sabe a ponta e compara com o que está no ar
Arquivos: `coletar_github.py`, `test_coletar.py`, `test_coletar_por_conta.py`. C7; usa
`regras.no_ar_do_projeto` e `banco.medicoes_de_servidor` (nos testes,
`mock.patch.object(banco, "medicoes_de_servidor", create=True, return_value=[...])`; no código em
`try/except Exception` → `[]`, como `enderecos_por_servidor` em `:1116`). `import regras` entra.
`mede_no_ar` **entra na lista** do guarda de `test_coletar_por_conta.py:765`, com `buscar = buscar
or _gh_json`. Sha validado hex antes de ir à URL (como `mede_deploy:885`). Testes: `traduz` com oid
válido/inválido; `mede_no_ar` (igual não chama; diferente chama `compare/<sha>...main` →
`{sha, atras}`; compare None → ausente; 4 shas → ≤3 chamadas; sha torto nunca na URL);
`_gravar_medicao` grava `no_ar` e `head_sha`; `medicoes_de_servidor` levantando → `no_ar == []` e
segue; `:413` com a fórmula nova; sabotar `_gh_json(` em `mede_no_ar` reprova o guarda.
Verificação: `test_coletar`, `test_coletar_por_conta`, `test_regras`, `test_imagem`.

### E4 — A tela: "Seus servidores", a linha para colar e o "no ar" no projeto
Arquivos: `assets/painel.js`, `assets/painel.css`, `index.html`, `test_servidor_tela.py`. C4, C5,
C6, C10 e os textos exatos de `design.md`. Molde: `test_github_tela.py` (importa helpers de
`test_conectar_tela.py`, node com DOM de mentira; sem node pula só esses casos). Regras: menu de 4;
sem `Number(`/`parseInt(` (use `+x`); só `textContent`; sem `style=` nem arquivo novo em `assets/`;
nenhum token novo; código do cartão entre os marcadores `CONECTAR: início/fim`.
- `index.html`: depois de `#cartao-sites`, `<div class="cartao porta" id="cartao-servidores"
  aria-labelledby="servidores-titulo">` com `<h2 id="servidores-titulo">Seus servidores</h2>` e corpo
  `aria-live="polite"`; bloco da linha e "Copiar" não são recriados a cada repintura.
- `cartaoDosServidores()`: vazio → texto + "Ligar um servidor"; clique → `fetch("/api/ajudante/linha"`
  com "Preparando a linha…"; 503/rede → frase nossa + "Tentar de novo"; 403 página velha → faixa
  central; ligando (`blocoDaLinhaDoAjudante(d)`): "Copiar" acima, largura cheia em 360px, `<pre>`
  com rolagem própria, roteiro de 4 passos, "Se der errado", `<details>` "O que isso faz?";
  ligado (`linhaDeServidorLigado(s)`): nome, "medido há N s" (`haQuanto`) ou "Sem dados há N min —
  o servidor parou de contar.", "Não consegui ver os sistemas deste servidor." se
  `docker_mudo === true`; `linhaDeSistema(x)`: running+unhealthy → "com problema", running → "de
  pé", restarting → "reiniciando", resto → "parado"; "desde <quando>"; "reiniciou N vezes" só N>0.
- `pintarAutorizar(p)` com `p.tipo === "servidor"`: "Autorizar este servidor?" + "Um servidor
  chamado <nome> quer se ligar à sua conta. Ele só vai olhar."; sucesso: "Autorizado. Em até um
  minuto o servidor aparece em Seus servidores." e `carregar()`.
- `linhaDoNoAr(n)`: "No ar em <servidor>: versão de <data>" + veredito ("igual ao GitHub", "N
  mudanças atrás do GitHub", "diferente do GitHub", "não sei qual versão está no ar"); sem
  `publicado_em` só "No ar em <servidor>:" + veredito; no cartão do projeto em `pintarPainel`
  (`.dizeres`) e em `pintarProjeto`; `no_ar` vazio → nenhuma linha.
- `ligarFluxoDosServidores()`: variável própria `FLUXO_SERVIDORES`; abre
  `new EventSource("/api/eventos")` só com `servidores_ligados.length > 0` e tela
  painel/projeto/conectar; `servidor` → `carregar()` e `navegar()`; `fim` → religa em 500 ms; sai
  da tela → fecha.
- Testes (`test_servidor_tela.py`, fixtures `vps-ovh`, `dervs-app`, `grimoire-web`, `ajudei-db` com
  2 reinícios, `96eb3fc`): cada estado do cartão; os 4 vereditos; "reiniciou" ausente com 0; `no_ar`
  vazio sem linha; Autorizar de servidor; `EventSource` literal e não abre com lista vazia; sem
  `innerHTML`/`Number(`/`parseInt(` nas funções novas; jargão
  `\bagente\b|\btoken\b|\bssh\b|systemd|cont[eê]iner|instala[cç][aã]o|deploy|login|dashboard`
  (sem caixa) ausente do texto visível; sabotar "contêiner" num `textContent` reprova.
Verificação: `test_servidor_tela`, `test_conectar_tela`, `test_github_tela`, `test_design`,
`test_menu`, `test_voz_tela`, `test_progresso_tela`, `test_conectar_ponta_a_ponta`.

### F — O fio inteiro, a imagem, a CI e a documentação
Arquivos: `test_servidor_fio.py`, `Dockerfile`, `test_imagem.py`, `ci.yml`, `CLAUDE.md`,
`README.md`, `docs/A-APLICACAO.md`, `docs/LINKS.md`.
- `test_servidor_fio.py`: `OAjudanteBaixadoLigaNumaPastaVazia` (GET do arquivo real → pasta
  temporária fora do repo → confere sha256 → `importlib` pelo caminho → `instalar(raiz=tmp,
  rodar=dublê, eh_root=lambda: True, dono=noop, dormir=noop)` com thread que lê o código e chama
  `/api/pedido` (espera `tipo:"servidor"`) e autoriza → `medir(...)` com docker falso e
  `historico.log` de mentira → ambos 0; `servidores_ligados[0].sistemas` com os falsos; projeto
  com camada github à mão tem `no_ar[0].veredito` certo; `/agente/pacote` com o token → 403);
  `OQueATelaLeOServidorEntrega` (`campos(var, fn)` das funções C10 ⊂ chaves reais; rotas em
  `servir.ROTAS`; sabotar `veredito` só no JS e `sha256` só no servidor deixa vermelho).
- `Dockerfile`: `COPY ajudante_servidor.py /app/` ("lido e servido, nunca importado").
- `test_imagem.py`: o nome na lista e caso "lido, nunca importado".
- `ci.yml`: um passo por arquivo novo (`test_ajudante_servidor`, `test_servidor_ligado`,
  `test_servidor_tela`, `test_servidor_fio`).
- `CLAUDE.md`: seção "O ajudante no servidor (entrega B)" com as travas e dívidas.
- `README.md`, `docs/A-APLICACAO.md`, `docs/LINKS.md`.
- Coordenador: avisar a janela do `dervs-voz`; revisões de segurança (obrigatória), Python,
  conteúdo e design antes de mesclar.
Verificação: `python test_servidor_fio.py`; regressão sem `FALHOU`;
`for t in test_*.py; do grep -q "python $t" .github/workflows/ci.yml || echo FALTOU $t; done` vazio.

### F-2 — Conferência manual (não é código)
Localhost (4790, `DERVS_AMBIENTE=local`, `servir.py` reiniciado): cartão em 360px, copiar,
Autorizar de servidor, fluxo sem recarregar. VM Linux com Docker+systemd: a linha de verdade, timer
de 30 s, `ProtectSystem` com o soquete, reboot, `remover`. VPS (mão do dono, portão 4, depois de
publicar): idem + `historico.log` com a ACL.

### Não confirmado
Saída de `{{index .Config.Labels "x"}}` para rótulo ausente no Docker da VPS; `ProtectSystem=strict`
com docker CLI sem `HOME`; se o 750 é da pasta ou do arquivo; TZ do `date` do kit; se o nome no
`historico.log` sempre bate com o repositório; se algum caso de `test_design.py` quebra com o cartão.
