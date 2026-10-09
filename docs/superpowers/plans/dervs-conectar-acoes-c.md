# Plano de execução — Conectar simples, entrega C (o servidor faz, com o "Pode fazer" do dono)

Ramo `feat/conectar-acoes`. Contrato: `docs/esteira/conectar-acoes/{briefing,spec,design}.md`
(as `decisoes_do_portao_2` vencem: **duas** ações, reiniciar e voltar; publicar saiu; promessa
honesta). Escrito em 09/10/2026. **Onde este plano e o spec divergirem, vale o plano** — as
divergências estão nomeadas em "Decisões do plano".

Três executores em paralelo, **divididos por arquivo** (nenhum arquivo tem dois donos), e uma
etapa F sequencial, única dona da CI, do `CLAUDE.md` e do teste de fio. Ninguém precisa ver o
trabalho do outro: a seção "Interface" abaixo é o contrato inteiro entre eles.

## Decisões do plano (o spec deixava em aberto ou faltava)

1. **A cópia do lado do DERVS de `texto_da_ordem` mora em `tarefas.py`** (pura, sem import
   novo, já é a casa de `projeto_bloqueado`), nunca numa constante chamada `ACOES`
   (`test_rotas.AMPUTADOS`). A frase da tela mora em `servir.py` como
   `Hub._frase_do_pedido(tipo, alvo, servidor)` e em `painel.js` como
   `fraseDoPedido(tipo, alvo, servidor)`; o F cobra que dão a mesma string.
2. **Cada item de `sistemas` ganha também `bloqueado: bool`** (acréscimo do design ao C9),
   para a tela dizer "fica de fora: guarda dado de saúde" em vez de só esconder o botão.
3. **O vetor de fora tem campos FIXOS** (abaixo), para que o fio (F) possa reproduzir a mesma
   ordem do lado do DERVS. Por isso o servidor ganha duas costuras, só para teste:
   `Hub._numero_da_ordem()` (padrão `secrets.token_hex(16)`) e `Hub._segundos_agora()`
   (padrão `int(time.time())`); e o ajudante recebe `agora` por parâmetro em `ordens(...)`.
4. **E2 testa as rotas com o assinador de teste de `test_passkey.py`** (vetor de dentro). Não
   é furo da regra do vetor de fora: o que E2 prova é a lógica das rotas, e a conta de
   criptografia do DERVS (`passkey`/`p256`) já é conferida por fora (RFC 6979). O vetor de fora
   novo prova o **ajudante** (E1) e, no F, que o DERVS aceita a mesma assinatura que o
   ajudante aceita.
5. **Ordem com `numero` ilegível não gera desfecho** (não há a quem amarrar): o ajudante sai
   calado, e o DERVS mostra `sem_resposta` passados 30 min. Qualquer outra recusa vira
   desfecho `recusada` com o motivo.
6. **Teste de rota novo em arquivo novo** `test_ordens_servidor.py` (E2), não em
   `test_servidor_ligado.py`, que fica só como regressão. Tela em `test_pedidos_tela.py` (E3).
7. **Chaves na linha: as 5 vivas mais novas** da conta (`ORDER BY criado_em DESC LIMIT 5`).

## Armadilhas que reprovam em silêncio (ler antes de escrever uma linha)

- **Nomes proibidos.** `test_rotas.PROIBIDO` casa como **substring**, sem caixa, em caminho de
  rota e em `funcao.__name__`: `acao|execucao|exec|terminal|pty|shell|comando|grafo`. Por isso
  também caem `instalacao`, `autorizacao`, `documentacao`, `publicacao`, `comparacao`,
  `atualizacao`. Nada de rota ou método do `Hub` com esses pedaços. `AMPUTADOS` proíbe
  `ACOES`, `ACOES_SEM_PROJETO`, `executar_acao` como atributo. Use "ordem", "pedido",
  "preparar", "assinar", "desfecho", "fazer". `EXECUTA` reprova `compile`/`system`/
  `subprocess` alcançável por rota (inclui `re.compile` em método: valide hex com
  `all(c in "0123456789abcdef" for c in s)`).
- **A lista de tabelas é à mão:** `test_banco.Esquema.test_as_vinte_tabelas_existem` ganha
  `"ordem_de_servidor"` na lista literal, em ordem alfabética (depois de `"medida"`, antes
  de `"pareamento"`). E `test_as_filhas_de_usuario_incluem_as_tabelas_novas`
  passa a cobrar `"ordem_de_servidor" in FILHAS_DE_USUARIO`.
- **`secret-scan.sh` barra por FORMA.** (a) `passwd`/`token`/`secret`/`password` seguido de
  `:` ou `=` e 16+ caracteres `[A-Za-z0-9/_+=-]`: a linha do `sudoers` (a palavra NOPASSWD, os
  dois-pontos, espaço e o caminho do comando de publicar do servidor) **nunca** aparece inteira
  num literal — nem no ajudante, nem no teste, nem em documento. Monte em pedaços:
  `"NOPASSWD" + ":" + " " + ARGV_DA_VOLTA[2]`. (b) Armadura de chave privada (cinco hífens +
  BEGIN ... PRIVATE KEY): nunca. (c) Constante com `token`/`senha`/`segredo` no nome e valor
  longo: não. Rode `bash "$HOME/.claude/hooks/secret-scan.sh"` com o índice preparado antes
  de cada commit; ele re-barra até um novo `git add`.
- **`secret-read-guard.sh` barra pelo TEXTO do comando:** nenhum nome terminado em `.pem`,
  `.key`, `.p12`, `.pfx` numa linha de comando. As chaves do vetor se chamam `k1` e `k2`, sem
  extensão.
- **O heredoc do Bash troca o fim de linha nesta máquina.** Nunca gere arquivo, script ou
  texto a comparar por `<<'FIM'`: escreva com a ferramenta `Write` e rode o arquivo.
- **Python do Windows:** caminho `/c/Users/...` não existe para ele; use `C:/Users/...`.
- `if __name__ == "__main__"` no **fim** de todo teste novo. Teste que sobe servidor declara
  `DERVS_AMBIENTE=local` e `DERVS_COFRE` **antes** de importar `banco`.
- Prazo em toda leitura de fluxo (`/api/eventos`): sem prazo pendura.
- `ajudante_servidor.py` é **ASCII puro**, Python 3.8, só biblioteca padrão, **uma** marca
  `# DERVS:ALVO`, e **não pode** conter `logs`, `executor`, `.conf`, `Env`, `.env`,
  `{{json`, `agente/(pacote|relatorio|resultado|voz)` (`test_ajudante_servidor.PROIBIDO`).
- `painel.js`: sem `Number(`/`parseInt(` (use `+x`), sem `innerHTML`, sem `style=`; texto do
  servidor só por `textContent`; código novo do cartão entre `/* === CONECTAR: início === */` e
  `/* === CONECTAR: fim === */` (o guarda de jargão lê esse trecho).
- Commite cedo. Desfaça sabotagem **editando de volta**, nunca `git checkout -- <arquivo>`.
  Commit e push em chamadas separadas.

---

## Interface entre E1, E2 e E3 (ninguém muda isto sem mudar aqui)

### I0. A ordem (C0) e os dados de conferência comuns

Texto canônico, ASCII, sete linhas, `\n` entre elas e **sem** `\n` no fim:

```
dervs-ordem=1
servidor=<32 hex minúsculos>
tipo=<reiniciar|voltar>
alvo=<nome>
numero=<32 hex minúsculos>
criado=<inteiro>
vence=<inteiro>
```

`alvo`: `reiniciar` → `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`; `voltar` →
`^[a-z0-9][a-z0-9-]{0,62}$`. Inteiros: só dígitos, sem zero à esquerda (salvo `"0"`), 1 a 10
dígitos, e `vence - criado == 300`. `texto_da_ordem(campos: dict) -> str | None` recebe
`{"servidor","tipo","alvo","numero","criado","vence"}` (`criado`/`vence` como `int`, nunca
`bool`) e devolve `None` para qualquer campo fora do formato. Desafio =
`hashlib.sha256(texto.encode("ascii")).digest()`; no `clientDataJSON` vai o base64url sem `=`.

**Tabela comum** (E1 e E2 escrevem a mesma tabela nos seus testes, à mão; o F cobra as duas
funções lado a lado):

| Campos | `sha256(texto).hexdigest()` | base64url |
|---|---|---|
| servidor `7f3a9c2e5b8d41f6a0c3e9b2d4f6a8c1`, tipo `reiniciar`, alvo `grimoire-web`, numero `4e1d2c3b5a6978f0e1d2c3b4a5968778`, criado `1791558000`, vence `1791558300` | `2358580c05214c6639569a105fe02350d2cea31d76f4fd6f6ead896445090d84` | `I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ` |
| idem, tipo `voltar`, alvo `grimoire` | `27a594db73c6f445df5d478b3e32da7a34ef5204d64145723c51209efc6268fc` | `J6WU23PG9EXfXUeLPjLaejTvUgTWQUVyPFEgnvxiaPw` |

Casos que dão `None` (os dois lados): alvo com `=`, alvo com `\n`, `voltar` com maiúscula
(`Grimoire`), `voltar` com `_`, `reiniciar` começando por `-`, numero com 31 ou 33 hex ou com
maiúscula, servidor com `g`, `criado` `"01791558000"` ou 11 dígitos, `vence - criado == 299`,
`criado` `True`, tipo `publicar`, campo faltando, campo a mais (`extra`) — **campo a mais
também é `None`**.

`sha256("dervs.com.br") = 4bde283fc80ee1a452ddfe1dfdaa75a58a33b746547bf88c2cd52ee44f70dff7`.

**Impressão de chave:** `impressao(x: int, y: int) -> str` = 16 primeiros hex de
`sha256(x.to_bytes(32,"big") + y.to_bytes(32,"big"))`. Fixture comum: o gerador `G` da P-256
dá `d875db7def232236`. No ajudante é `impressao` (função de módulo); no DERVS,
`banco.impressao_da_chave(x, y)`.

**Chave na linha:** `"%064x.%064x" % (x, y)`; várias separadas por `,`, no máximo 5.

### I1. `GET /api/ajudante/linha` (E2 serve, E3 lê)

Acrescenta, sem tirar nada:

```json
{"linha": "...", "sha256": "...", "endereco": "...",
 "linha_com_ordens": "<a linha> --ordens <x>.<y>,<x>.<y>" | null,
 "chaves_na_linha": ["Celular do Thiago", "PIN do notebook"]}
```

`linha_com_ordens` = `linha + " instalar --ordens " + chaves` (o fim da linha da B é
`sudo python3 -I dervs-ajudante.py`; o ajudante aceita `instalar` explícito). `null` e `[]`
quando a conta não tem chave viva.

### I2. A medição (E1 manda, E2 valida) — `POST /agente/servidor`

Corpo da B + a chave de topo **opcional**:

```json
"ordens": {"versao": 1, "ident": "<32 hex>", "chaves": ["d875db7def232236"],
           "voltaveis": ["dervs", "grimoire"]}
```

Validação no DERVS (lista fechada; o que sobra é descartado e contado em `invalidos`):
`versao == 1`; `ident` 32 hex minúsculos (senão o bloco inteiro cai); `chaves` lista de até 5
strings de 16 hex minúsculos; `voltaveis` lista de até 200 nomes no formato de `voltar`, sem os
bloqueados (`tarefas.projeto_bloqueado`). `CHAVES_DO_TOPO` ganha `"ordens"`. A resposta continua
`{"ok": true, "invalidos": N}` — **nunca** ordem nem `tarefa`.

### I3. As rotas do ajudante (E1 chama, E2 serve)

Ambas `POST`, `Authorization: Token <t>`, classe `maquina`, só `tipo='servidor'` (403
`{"erro":"so servidor"}` antes do balcão), corpo JSON (415 sem JSON).

- `POST /agente/servidor/ordens`, corpo `{}`. 200 `{"ordem": null}` ou
  ```json
  {"ordem": {"servidor": "7f3a...", "tipo": "reiniciar", "alvo": "grimoire-web",
             "numero": "4e1d...", "criado": 1791558000, "vence": 1791558300,
             "cliente": "<b64url>", "autenticador": "<b64url>", "assinatura": "<b64url>"}}
  ```
  429 `{"erro":"nao deu"}` (balcão `servidor_ordens`, 90 por janela, por máquina).
- `POST /agente/servidor/desfecho`, corpo
  `{"numero": "<32 hex>", "desfecho": "feita|falhou|recusada|nao_sei", "codigo": int|null, "motivo": str|null}`.
  Regras: `feita` → `codigo 0`, `motivo null`; `falhou` → `codigo` 1–255, `motivo null`;
  `recusada` → `codigo null`, `motivo` da lista; `nao_sei` → os dois `null`. Outra combinação:
  400 `{"erro":"corpo invalido"}`. 200 `{"ok": true}`; 404 `{"erro":"nao achei"}` se a ordem
  não é desta máquina, não foi entregue ou já tem desfecho; 429 (balcão `servidor_desfecho`, 30).

Motivos (lista fechada, igual nas três pontas): `forma`, `outro_servidor`, `vencida`,
`assinatura`, `desafio`, `origem`, `aparelho`, `bloqueado`, `desconhecido`, `repetida`,
`cheio`, `teto`. No ajudante e no DERVS a tupla se chama `MOTIVOS_DA_RECUSA`.

### I4. As rotas da tela (E2 serve, E3 chama)

Sessão, `Origin` em `ORIGENS_OK`, cabeçalho `X-Token` (o `escrever()` do `painel.js` já manda),
classe `dado`.

- `POST /api/maquinas/ordem/preparar` → `Hub._maquina_ordem_preparar`. Corpo
  `{"maquina_id": 7, "tipo": "reiniciar"|"voltar", "alvo": "grimoire-web"}`.
  - 200 `{"numero": "<32 hex>", "desafio": "<b64url de 32 bytes>", "rp_id": "dervs.com.br",
    "chaves": ["<cred_id b64url>", ...], "segundos": 300, "frase": "<frase>"}`
  - 409 `{"motivo": "so_olha"|"sem_dados"|"ocupado"|"sem_chave"}` · 403 `{"motivo":
    "bloqueado"}` · 404 `{"erro":"nao achei"}` (não existe **e** é de outra conta: a mesma) ·
    400 `{"erro":"pedido invalido"}` (tipo/alvo torto ou alvo não medido/não voltável) · 429.
- `POST /api/maquinas/ordem/assinar` → `Hub._maquina_ordem_assinar`. Corpo
  `{"numero", "cred_id", "cliente", "autenticador", "assinatura"}` (base64url, como o
  `paraTexto` de `portas.js`). 200 `{"ok": true}`; qualquer falha 401 `Hub.RECUSA`
  (`{"erro":"nao deu"}`); 429.

**A frase** (`Hub._frase_do_pedido` e `fraseDoPedido`, letra por letra, com aspas tipográficas
U+201C/U+201D):

- `reiniciar`: `Reiniciar o sistema “<alvo>” no servidor “<servidor>”`
- `voltar`: `Voltar “<alvo>” para a versão anterior no servidor “<servidor>”`

`<servidor>` = `maquina.nome`.

### I5. `GET /api/dados` (E2 monta, E3 lê)

Em cada `servidores_ligados[i]` (montado em `_dados`, depois da poda; `montar_estado` não muda):

```json
"ordens": null | {"chaves_ok": true, "linha_velha": false,
                  "voltaveis": ["dervs", "grimoire"],
                  "pedidos": [{"numero": "4e1d...", "tipo": "reiniciar", "alvo": "grimoire-web",
                               "estado": "enviado|nao_pegou|fazendo|sem_resposta|feito|nao_deu|recusado|nao_sei",
                               "quando": "<iso>", "codigo": 1|null, "motivo": "teto"|null}]}
```

e cada `sistemas[j]` ganha `"reiniciavel": bool` e `"bloqueado": bool`. `ordens` é `null`
quando a medição não traz o bloco **ou** `estado != "medido"`; aí `reiniciavel` é falso em
todos. `pedidos`: as 5 mais novas **assinadas**, por `assinada_em` desc. `quando`: `assinada_em`
para `enviado`/`nao_pegou`, `entregue_em` para `fazendo`/`sem_resposta`, `terminada_em` para os
outros. Limites: `enviado` ≤ 120 s desde `assinada_em`; `fazendo` ≤ 1800 s desde `entregue_em`.

### I6. Nomes no `painel.js` que o fio lê (E3 escreve, F cobra)

| Função | Lê |
|---|---|
| `linhaDeServidorLigado(s)` | os da B + `s.ordens` |
| `linhaDeSistema(x, s)` | os da B + `x.reiniciavel`, `x.bloqueado` |
| `blocoDosPedidos(s)` | `s.ordens.chaves_ok`, `s.ordens.linha_velha`, `s.ordens.voltaveis`, `s.ordens.pedidos` |
| `estadoDoPedido(p)` | `p.numero`, `p.tipo`, `p.alvo`, `p.estado`, `p.quando`, `p.codigo`, `p.motivo` |
| `pedirAoServidor(s, tipo, alvo)` | `r.numero`, `r.desafio`, `r.rp_id`, `r.chaves`, `r.segundos`, `r.frase`, `r.motivo` |
| `blocoDaLinhaDoAjudante(d)` | os da B + `d.linha_com_ordens`, `d.chaves_na_linha` |
| `fraseDoPedido(tipo, alvo, servidor)` | — (devolve a frase de I4) |

Literais: `"/api/maquinas/ordem/preparar"`, `"/api/maquinas/ordem/assinar"`,
`navigator.credentials.get`.

---

## O vetor de fora (E1 gera, uma vez, fora do repositório)

Regra do repositório: criptografia testada só com dado que ela produziu não está testada. O
vetor sai do **OpenSSL 3.5.7** desta máquina. Passos, todos numa pasta nova do scratchpad
(`C:/Users/Desktop/AppData/Local/Temp/claude/.../scratchpad/vetor`), **nunca** dentro do repo:

1. Gerar as duas chaves, sem extensão no nome (o hook barra `.pem`/`.key` na linha):
   ```
   openssl ecparam -name prime256v1 -genkey -noout -outform DER -out k1
   openssl ecparam -name prime256v1 -genkey -noout -outform DER -out k2
   openssl ec -inform DER -in k1 -pubout -outform DER -out k1pub
   openssl ec -inform DER -in k2 -pubout -outform DER -out k2pub
   ```
   `x`, `y` = os últimos 64 bytes de `k1pub`/`k2pub` (o ponto não comprimido `04||x||y` fecha
   o SubjectPublicKeyInfo).
2. Escrever **com a ferramenta `Write`** (nunca heredoc) um script `monta.py` no scratchpad que,
   para cada caso, grava `cliente_<caso>` (o `clientDataJSON`, bytes exatos, sem espaço:
   `{"type":"webauthn.get","challenge":"<b64>","origin":"https://dervs.com.br","crossOrigin":false}`),
   `autenticador_<caso>` (37 bytes: `sha256(rp)` + flags + contador `00000001`) e
   `assinado_<caso>` = `autenticador || sha256(cliente)`. O script **não** assina nada.
3. Assinar cada caso pelo OpenSSL:
   `openssl dgst -sha256 -sign k1 -keyform DER -out sig_<caso> assinado_<caso>`
   (`k2` no caso `outra_chave`).
4. Um segundo script lê os arquivos e imprime as constantes em hex para colar no teste. Depois:
   **apagar `k1` e `k2`** (e conferir que sumiram). Só as públicas entram no repositório.

Casos (todos sobre a ordem `reiniciar` da tabela I0, salvo onde dito; `rp = "dervs.com.br"`,
flags `0x05` = UP+UV):

| Caso | O que muda | Conferência que tem de recusar |
|---|---|---|
| `valido` | nada | — (aceita) |
| `valido_voltar` | a ordem `voltar` da tabela I0 | — (aceita) |
| `outra_chave` | assinado por `k2` | 5 `assinatura` |
| `outro_desafio` | `challenge` da ordem com alvo `dervs-app` | 6 `desafio` |
| `tipo_errado` | `"type":"webauthn.create"` | 6 `desafio` |
| `outra_origem` | `"origin":"https://dervs.com.br.exemplo.net"` | 7 `origem` |
| `cruzado` | `"crossOrigin":true` | 7 `origem` |
| `outro_rp` | `rpIdHash = sha256("exemplo.net")` | 8 `aparelho` |
| `sem_uv` | flags `0x01` | 8 `aparelho` |
| `com_at` | flags `0x45` (37 bytes, AT ligado) | 8 `aparelho` |

"Sem assinatura" = `valido` com `assinatura: ""` (5). "Vencida" = `valido` com
`agora = 1791558301` (4). "Repetida" = `valido` duas vezes; a segunda dá `repetida` (11).
Aceita com `agora = 1791558010`.

No teste fica um dicionário `VETOR_DE_FORA` com: `publica_k1` e `publica_k2` (`x`, `y` em hex),
por caso `cliente` (texto), `autenticador` e `assinatura` (hex do DER), mais um comentário com
`openssl version`, a data e os quatro comandos. Nome sem `token`/`senha`/`segredo`. O F
importa `VETOR_DE_FORA` de `test_ajudante_acoes` (como `test_github_tela` importa de
`test_conectar_tela`).

---

## Divisão por executor

| Etapa | Arquivos (lista fechada) |
|---|---|
| E1 | `ajudante_servidor.py`, `test_ajudante_acoes.py` (novo), `test_ajudante_servidor.py` |
| E2 | `banco.py`, `servir.py`, `tarefas.py`, `test_banco.py`, `test_tarefas.py`, `test_rotas.py`, `test_ordens_servidor.py` (novo) |
| E3 | `assets/painel.js`, `assets/painel.css`, `index.html` (só se preciso), `test_pedidos_tela.py` (novo); `test_servidor_tela.py`/`test_design.py`/`test_conectar_tela.py` só se um caso existente quebrar, com o motivo escrito no commit |
| F | `test_acoes_fio.py` (novo), `.github/workflows/ci.yml`, `CLAUDE.md`, `docs/operacao/ligar-um-servidor.md`, `Dockerfile` e `test_imagem.py` (só se preciso), `README.md`, `docs/A-APLICACAO.md` |

Ninguém edita (só roda como regressão): `p256.py`, `passkey.py`, `test_p256.py`,
`test_passkey.py`, `test_servidor_fio.py`, `test_servidor_ligado.py`, `test_sse.py`,
`test_servir.py`, `test_conectar_*.py`, `test_voz*.py`, `test_agente.py`, `regras.py`,
`coletar*.py`, `docker-compose.yml`, `infra/nginx-dervs.conf`, `assets/portas.js`.

Ordem: (E1, E2, E3 em paralelo) → mesclar E2, E1, E3 → F. **A CI fica vermelha até o F** (o
passo que cobra a lista de testes acusa os três arquivos novos): não abrir PR antes do F.

Regressão (Bash):
```bash
cd /c/Users/Desktop/source/repos/dervs && for t in test_*.py; do python "$t" >/dev/null 2>&1 || echo "FALHOU $t"; done
```

---

## Etapas

### E1 — O ajudante aceita dois pedidos e confere sozinho

Arquivos: `ajudante_servidor.py`, `test_ajudante_acoes.py`, `test_ajudante_servidor.py`.
Contratos: C1, C2, C3, C4, C5, C11, C12 (lado do ajudante); I0, I1 (formato do `--ordens`), I2,
I3. Moldes: o próprio ajudante da B (`rodar`, `abrir`, `_gravar`, `texto_do_servico`,
`instalar`, `ComRaiz`, `Dubles`).

**Interface que E1 entrega (o F usa):**

```python
texto_da_ordem(campos: dict) -> str | None
impressao(x: int, y: int) -> str
conferir_ordem(ordem: dict, config: dict, numeros: dict, feitas: list, agora: float,
               sistemas_agora) -> str | None          # None = passou; senao o motivo
fazer(argv: list, prazo: float) -> int | None
ordens(alvo=ALVO, raiz="/", rodar=None, abrir=None, fazer=None, agora=time.time) -> int
instalar(..., ordens=None)     # ordens: lista de "x.y" (texto), vinda de --ordens
ARGV_DO_REINICIO = ("docker", "restart")
ARGV_DA_VOLTA = ("sudo", "-n", "/usr/local/bin/deploy")
PROJETOS_BLOQUEADOS = frozenset({"ajudei-saude"})
MOTIVOS_DA_RECUSA = ("forma", "outro_servidor", "vencida", "assinatura", "desafio",
                     "origem", "aparelho", "bloqueado", "desconhecido", "repetida",
                     "cheio", "teto")
MAX_NUMEROS = 200 ; TETO_POR_HORA = 6 ; PRAZO_DO_REINICIO = 120 ; PRAZO_DA_VOLTA = 1200
```

`main`: `instalar` (com ou sem `--ordens <lista>`), `medir`, `ordens`, `remover`. Arquivos
(prefixados por `raiz`): `/etc/dervs-ajudante/ordens.json`, `/var/lib/dervs-ajudante/numeros.json`
(`{"numeros": {numero: vence}, "feitas": [instantes]}`), `/etc/sudoers.d/dervs-ajudante`,
`/etc/sudoers.d/.dervs-ajudante.novo`, `/etc/systemd/system/dervs-ajudante-ordens.{service,timer}`.

**Testes a escrever ANTES (TDD), em `test_ajudante_acoes.py`:**

- `OTextoDaOrdem`: a tabela I0 (os dois hashes) e cada caso de `None`.
- `AImpressao`: `impressao(Gx, Gy) == "d875db7def232236"`.
- `AContaP256EAMesmaDoP256`: para cada nome de `{somar, multiplicar, ponto_valido, conferir,
  assinatura_de_der, _inteiro}` (e `ponto_de_bytes` se for copiada), `ast.dump` da função no
  ajudante == `ast.dump` em `p256.py`; para `{P, A, B, N, G, TETO_DO_DER}` (e toda constante
  que essas funções citem), valor igual. **Fecho:** todo nome livre citado pelas funções
  copiadas tem de existir no ajudante e estar no conjunto conferido.
- `ARfc6979`: os vetores de RFC 6979 A.2.5 que `test_p256.py` usa, pela cópia do ajudante.
- `OVetorDeFora`: `valido` e `valido_voltar` aceitos por `conferir_ordem`; cada caso da tabela
  do vetor dá o motivo dela; sem assinatura → `assinatura`; vencida → `vencida`; repetida →
  `repetida`; e, como testemunha cruzada, `passkey.conferir_entrada` (DERVS) aceita `valido`
  com `rp_id="dervs.com.br"` e `{"https://dervs.com.br"}`.
- `AsOnzeConferencias`: um caso por linha de C3, na ordem (falha em 2 não chega a 5:
  conferir com uma chave de verdade e `servidor` errado dá `outro_servidor`, não
  `assinatura`); `cliente` de 4097 bytes, `autenticador` de 36/38 bytes, `assinatura` de 81
  bytes, base64url inválido → `forma`; `criado - 121 > agora` → `vencida`; `voltar` de
  `ajudei-saude`, `Ajudei_Saude`, e `reiniciar` de `grimoire-web` cujo rótulo de projeto é
  `ajudei-saude` → `bloqueado`; `voltar` de projeto fora de `voltaveis` e `reiniciar` de nome
  ausente do `docker ps` feito agora → `desconhecido`.
- `ONumeroUnico`: poda o vencido; 200 vivos → `cheio` (nenhum vivo descartado); gravação que
  falha → `recusada`/`cheio` e `fazer` **não** chamado; o número é gravado antes de `fazer`.
- `OTetoPorHora`: 6 feitas na última hora → a 7ª `teto`; a de 61 min atrás não conta.
- `DesligadoPorPadrao`: sem `ordens.json`, `ordens(...)` devolve 0 e o `abrir` falso **nunca**
  é chamado (lista de chamadas vazia), mesmo com a ordem `valido` pronta no dublê.
- `OFazer`: `fazer` com `subprocess.run` remendado: argv exato `["docker","restart","grimoire-web"]`
  e `["sudo","-n","/usr/local/bin/deploy","grimoire","--voltar"]`; `shell` ausente/False;
  `stdin`/`stdout`/`stderr` = `DEVNULL`; `env == {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
  "LANG": "C"}`; código 0 → `feita`; 1 → `falhou`/1; `TimeoutExpired` e `OSError` → `None` →
  `nao_sei`. Corpo do desfecho igual a I3.
- `OBloqueioEOMesmoDoDervs`: `aj.PROJETOS_BLOQUEADOS == frozenset(tarefas.PROJETOS_BLOQUEADOS)`;
  `aj._bloqueado(n) == tarefas.projeto_bloqueado(n)` para `Ajudei-Saude`, `ajudei_saude`,
  `AJUDEI SAUDE`, `ajudei.saude-web`, `ajudeisaude`, `ajudei-saudex`, `grimoire`.
- `AMedicaoContaOsPedidos` (C2): com `ordens.json` válido o corpo de `medir` traz `ordens`
  exatamente como I2; sem arquivo ou torto, a chave não vai; o resto do corpo igual ao da B.
- `if __name__` no fim.

**Em `test_ajudante_servidor.py` (ajustes):**

- Leis do fonte (C5): o literal `"docker"` só em `ARGV_DO_PS`, `ARGV_DO_INSPECT` e
  `ARGV_DO_REINICIO`; `"sudo"` e `"/usr/local/bin/deploy"` só em `ARGV_DA_VOLTA` (o `sudoers`
  é montado a partir dele); `subprocess` só dentro de `rodar` e `fazer`; nenhum `shell=True`,
  `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `pty`; nenhum argv montado fora das quatro
  tuplas (toda chamada a `rodar`/`fazer` tem como primeiro argumento uma expressão que começa
  por uma dessas tuplas ou é a lista fixa já cobrada da B).
- `AUnidadeDosPedidos`: `.service` diretiva por diretiva (`Type=oneshot`,
  `User=dervs-ajudante`, `ExecStart=<python> /opt/dervs-ajudante/dervs-ajudante.py ordens`,
  `TimeoutStartSec=30min`, `PrivateTmp=yes`) e a **ausência** de `NoNewPrivileges`,
  `CapabilityBoundingSet`, `ProtectSystem`, `UMask`; `.timer` (`OnBootSec=45s`,
  `OnUnitActiveSec=30s`, `AccuracySec=1s`, `WantedBy=timers.target`). A unidade da B
  continua byte a byte igual (comparar com o texto atual, copiado para o teste).
- `OSudoersExato`: uma linha por projeto voltável, igual a `"dervs-ajudante ALL=(root) " +
  "NOPASSWD" + ":" + " " + ARGV_DA_VOLTA[2] + " " + p + " --voltar"`; nenhum `*`; nenhuma
  linha para bloqueado; grava em `.dervs-ajudante.novo`, `visudo -cf` (no `rodar` falso), só
  então `os.replace`; `visudo` que reprova ou ausente → nada de linha, aviso, medição segue;
  nenhum projeto → o arquivo não existe; `useradd` nunca com `deploy` nos grupos.
- `OComandoDePublicarConferido`: `/usr/local/bin/deploy` com dono não-root, modo com escrita de
  grupo/outros, ou `/usr/local/bin` gravável por outros → nenhum voltável, frase do porquê
  (fora do Windows; no Windows `skipUnless`).
- `AsChavesDaLinha`: `--ordens` com chave fora da curva, com 63 hex, com 6 chaves → nada de
  pedidos ligado, medição segue; `ident` novo a cada instalar; `ordens.json` com a forma de
  C1.5 e `origem`/`rp_id` derivados do `ALVO` (`https://dervs.com.br` → `dervs.com.br`).
- `DesligarOsPedidos`: `instalar` sem `--ordens` num servidor com pedidos apaga as duas
  unidades novas, o `sudoers.d/dervs-ajudante` e `/etc/dervs-ajudante`; `remover` também.

**Sabotagens que provam cada guarda** (editar, rodar, ver vermelho, editar de volta):
trocar `"restart"` por `"stop"` → `OFazer` e a lei do fonte; mudar um sinal em `somar` da cópia
→ `AContaP256EAMesmaDoP256` e `ARfc6979`; tirar a conferência 7 → `outra_origem` e `cruzado`
aceitos (vermelho); trocar `if not existe(ordens.json): return 0` por continuar → 
`DesligadoPorPadrao`; gravar o número **depois** de `fazer` → `ONumeroUnico`; acrescentar
`"ajudei"` à cópia de `PROJETOS_BLOQUEADOS` → `OBloqueioEOMesmoDoDervs`; acrescentar
`NoNewPrivileges=yes` à unidade nova → `AUnidadeDosPedidos`; escrever `*` no `sudoers` →
`OSudoersExato`; trocar `-c` do `visudo` por nada → `OSudoersExato`.

Verificação:
```bash
cd /c/Users/Desktop/source/repos/dervs && python test_ajudante_acoes.py && python test_ajudante_servidor.py && python test_servidor_fio.py && python -c "open('ajudante_servidor.py','rb').read().decode('ascii')"
```

### E2 — O DERVS prepara, confere a digital, entrega e mostra

Arquivos: `banco.py`, `servir.py`, `tarefas.py`, `test_banco.py`, `test_tarefas.py`,
`test_rotas.py`, `test_ordens_servidor.py`. Contratos: C1 (linha), C2 (validação), C6, C7, C8,
C9, C11 (lado do DERVS); I0–I5. Moldes: `_entrar_chave` (rota de assinatura, `RECUSA` única),
`_agente_servidor` (balcão por máquina), `_servidor_ligado`, `BaseServidorDeVerdade`
(`test_servir.py`) como em `test_servidor_ligado.py`, assinador de teste de `test_passkey.py`.

**Interface que E2 entrega:**

- `tarefas.texto_da_ordem(campos) -> str | None` (I0) e `tarefas.MOTIVOS_DA_RECUSA`.
- `banco`: tabela `ordem_de_servidor` (C6, `CREATE TABLE IF NOT EXISTS` em `ESQUEMA`, índice
  `(maquina_id, criado)`, em `FILHAS_DE_USUARIO`); `impressao_da_chave(x, y)`;
  `chaves_publicas_da_conta(usuario_id) -> [{"cred_id","apelido","x","y"}]` (vivas, 5 mais
  novas); `criar_ordem_de_servidor(...)` (poda além das 50 mais novas da máquina; 409 `ocupado`
  decidido aqui, na mesma transação `BEGIN IMMEDIATE`); `assinar_ordem_de_servidor(usuario_id,
  numero, cred_id, cliente, autenticador, assinatura, agora)`; `entregar_ordem_de_servidor(maquina_id,
  agora) -> dict|None` (`UPDATE ... WHERE entregue_em IS NULL`, `rowcount == 1`);
  `desfecho_da_ordem_de_servidor(maquina_id, numero, desfecho, codigo, motivo) -> bool`;
  `ordens_do_servidor(usuario_id, maquina_id, limite=5) -> list`. Toda leitura e escrita com
  `usuario_id` **e** `maquina_id` no `WHERE` (a de entregar/desfecho, pela máquina do token).
- `servir`: `Hub._maquina_ordem_preparar`, `Hub._maquina_ordem_assinar`,
  `Hub._agente_servidor_ordens`, `Hub._agente_servidor_desfecho`, `Hub._frase_do_pedido`,
  `Hub._numero_da_ordem`, `Hub._segundos_agora`; tetos `TETO_DE_ORDENS_PREPARADAS = 20`,
  `TETO_DE_ORDENS_ASSINADAS = 20` (por sessão), `TETO_DE_BUSCAS_DE_ORDEM = 90`,
  `TETO_DE_DESFECHOS = 30` (por máquina), cada um com balcão **próprio** (`ordem_preparar`,
  `ordem_assinar`, `servidor_ordens`, `servidor_desfecho`); `CHAVES_DO_TOPO` com `"ordens"`;
  `_ajudante_linha` com I1; `_servidor_ligado`/`_dados` com I5. Entradas em `ROTAS` com
  comentário do motivo.

Preparar, nesta ordem: sessão → balcão → corpo (`maquina_id` int não-bool, `tipo` em
`{reiniciar, voltar}`, `alvo` str) → máquina viva `tipo='servidor'` **da conta** (senão 404, o
mesmo para "não existe") → `tarefas.projeto_bloqueado(alvo)` e, para `reiniciar`, também o
`projeto` do sistema medido → 403 `bloqueado` → medição com bloco `ordens` (senão 409
`so_olha`) → `regras.estado_do_servidor == "medido"` (senão 409 `sem_dados`) → alvo medido
(`reiniciar`: nome em `sistemas`; `voltar`: em `ordens.voltaveis`) senão 400 → chaves vivas
cuja impressão o servidor conhece (senão 409 `sem_chave`) → `texto_da_ordem` (None → 400) →
grava (409 `ocupado` se há outra em andamento) → 200.

Assinar: sessão → balcão → ordem da conta, não vencida, não assinada → `cred_id` em
`chaves_de_acesso` da **mesma conta**, com impressão conhecida pelo servidor →
`autenticador` de 37 bytes com AT/ED desligados → `passkey.conferir_entrada(cliente,
autenticador, assinatura, chave, sha256(C0), self._rp_id(), ORIGENS_OK)` com o C0 **remontado
dos campos da linha** → `banco.usar_chave_de_acesso` → grava. Toda falha: 401 `RECUSA`.

**Testes a escrever ANTES (TDD):**

- `test_tarefas.py`, `OTextoDaOrdem`: a mesma tabela I0 (hashes e `None`), escrita à mão.
- `test_banco.py`: `"ordem_de_servidor"` na lista à mão de `test_as_vinte_tabelas_existem`;
  `"ordem_de_servidor" in FILHAS_DE_USUARIO`; `CHECK`s (numero de 31 chars, tipo `publicar`,
  codigo 256, desfecho `ok`) levantam `IntegrityError`; apagar a conta apaga as ordens;
  `impressao_da_chave(Gx, Gy) == "d875db7def232236"`; `chaves_publicas_da_conta` sem revogada,
  no máximo 5.
- `test_ordens_servidor.py` (chave de teste antes de importar `banco`; servidor de verdade):
  - `ALinhaComPedidos`: conta com 2 chaves → `linha_com_ordens` termina em
    `" instalar --ordens " + "%064x.%064x" % ... + "," + ...`, mesmo `sha256` da linha só olhar,
    `chaves_na_linha` com os apelidos; sem chave → `null` e `[]`; chave revogada fora.
  - `AMedicaoComOBlocoDePedidos`: I2 aceito; `ident` torto derruba o bloco; 6 chaves → 5 e
    `invalidos` sobe; `ajudei-saude` em `voltaveis` descartado; resposta sem `ordem`/`tarefa`.
  - `PrepararOPedido`: 200 com os campos de I4 e `desafio == b64url(sha256(texto_da_ordem(...)))`;
    `frase` exata para os dois tipos; outra conta → 404 com corpo **igual** ao de id
    inexistente; só olha → 409 `so_olha`; medição de 181 s → `sem_dados`; segunda ordem →
    `ocupado`; `ajudei-saude`, `Ajudei_Saude`, `AJUDEI SAUDE` e sistema com rótulo
    `ajudei-saude` → 403 `bloqueado`; alvo não medido → 400; sem chave conhecida → `sem_chave`;
    21º → 429 e `/agente/servidor` ainda responde 200 e `/entrar/chave` ainda não dá 429.
  - `AssinarOPedido` (assinador de teste de `test_passkey`): válido → 200 e `assinada_em`;
    chave de outra conta, chave revogada, desafio de outra ordem, origem fora de `ORIGENS_OK`,
    AT ligado, contador que não sobe, ordem vencida, ordem já assinada → 401 com o **mesmo**
    corpo; balcão próprio.
  - `OAjudanteBusca`: computador → 403 `so servidor` antes do balcão; nada assinado →
    `{"ordem": null}`; assinada → os 10 campos de I3 e `entregue_em` marcado; segunda busca →
    `null`; assinada há 121 s → `null` para sempre; ordem de outra máquina da mesma conta
    nunca sai; 91ª → 429.
  - `ODesfecho`: cada combinação válida de I3 grava; combinação torta → 400; ordem de outra
    máquina, não entregue ou já com desfecho → 404; `terminada_em` carimbado.
  - `OQueOPainelMostra` (I5): `ordens: null` em só olha e em `sem_dados`; `chaves_ok` falso sem
    chave viva conhecida; `linha_velha` verdadeiro com uma chave nova; `reiniciavel` e
    `bloqueado` por sistema; cada um dos 8 estados de `pedidos` com relógio fixo
    (`Hub._segundos_agora` e `agora_iso` passados), **nenhum** `feito` sem `desfecho='feita'`;
    `banco.montar_estado` sem `ordens`.
- `test_rotas.py`, classe `AsRotasDosPedidos` (molde `AsRotasDoServidorLigado`): as quatro
  rotas existem, com a classe certa (`dado` POST para as duas da tela, `maquina` para as do
  ajudante); nomes passam `PROIBIDO`; nenhum atributo `ACOES`; `preparar` chama
  `tarefas.projeto_bloqueado` (guarda de fonte: reprova `.lower() in PROJETOS_BLOQUEADOS`).

**Sabotagens:** tirar `usuario_id` do `WHERE` de preparar → outra conta vê a máquina (vermelho);
devolver 403 em vez de 404 para outra conta → corpo diferente (vermelho); trocar
`WHERE entregue_em IS NULL` por nada → segunda busca devolve a ordem; mudar `120` para `600`
em entregar → o caso de 121 s; tirar o `projeto` do sistema da checagem de bloqueio → sistema
com rótulo `ajudei-saude` passa; marcar `feito` sem olhar `desfecho` → `OQueOPainelMostra`;
mudar a ordem de uma linha em `tarefas.texto_da_ordem` → `OTextoDaOrdem`; remover
`"ordem_de_servidor"` da lista à mão → `test_banco`.

Verificação:
```bash
cd /c/Users/Desktop/source/repos/dervs && for t in test_ordens_servidor test_rotas test_banco test_tarefas test_servidor_ligado test_servir test_passkey test_conectar_servidor test_sse test_voz test_agente test_publicar test_imagem; do python $t.py >/dev/null 2>&1 || echo "FALHOU $t"; done
```
Depois a regressão inteira.

### E3 — A tela: os botões, a confirmação, a digital e os estados

Arquivos: `assets/painel.js`, `assets/painel.css`, `index.html` (só se preciso),
`test_pedidos_tela.py`. Contratos: C10; I1, I4, I5, I6; textos e estados **exatos** de
`docs/esteira/conectar-acoes/design.md`. Molde: `test_servidor_tela.py` (node com DOM de
mentira, importa helpers de `test_conectar_tela`; sem node pula só esses casos).

- `linhaDeSistema(x, s)`: botão **Reiniciar** só com `x.reiniciavel === true`; com
  `x.bloqueado === true` e `s.ordens`, a frase "fica de fora: guarda dado de saúde".
- `linhaDeServidorLigado(s)`: com `s.ordens`, `blocoDosPedidos(s)`; sem, o convite "Este
  servidor só olha." + "Quero poder pedir coisas" (só quando medido).
- `blocoDosPedidos(s)`: avisos `!chaves_ok` e `linha_velha`; "Voltar a versão anterior" com um
  botão por `voltaveis` (vazio: a frase do design); último pedido por alvo
  (`estadoDoPedido(p)`), e "Último pedido" para alvo que sumiu; botões desabilitados
  (`aria-disabled`) com pedido `enviado`/`fazendo`.
- `pedirAoServidor(s, tipo, alvo)`: `confirmar({titulo: fraseDoPedido(...), texto, sim: "Pode
  fazer", nao: "Agora não"})` → `escrever("/api/maquinas/ordem/preparar", {maquina_id:
  +s.maquina_id, tipo, alvo})` → botão "Esperando a sua digital…" + faixa com `r.frase` →
  `navigator.credentials.get({publicKey: {challenge, rpId: r.rp_id, allowCredentials:
  r.chaves.map(id => ({type: "public-key", id})), userVerification: "required", timeout:
  r.segundos * 1000}})` (conversão base64url própria no `painel.js`; `portas.js` não muda) →
  `escrever("/api/maquinas/ordem/assinar", {...})` → "pedido enviado" e `carregar()`.
  `NotAllowedError`/`AbortError`/`null` → "Você cancelou. Nada foi pedido ao servidor.";
  sem `navigator.credentials` → frase de navegador sem suporte; cada resposta de erro de I4 →
  a frase da tabela do design.
- `blocoDaLinhaDoAjudante(d)`: as duas escolhas ("Só olhar", "Olhar e aceitar pedidos"),
  empilhadas; a segunda só com `d.linha_com_ordens`; aparelhos de `d.chaves_na_linha`; sem
  chave, o texto e o link para `#/conta`; o "O que isso faz?" com o limite honesto, inteiro.
- CSS: só tokens existentes (tabela do design); em 360 px botões embaixo, largura cheia, alvo
  ≥ 44 px, `overflow-wrap: anywhere` nos nomes; nada de rolagem horizontal da página.

**Testes a escrever ANTES (`test_pedidos_tela.py`, fixtures do design: `vps-ovh`,
`grimoire-web`, `dervs-app`, `grimoire-db`, `ajudei-db`, voltáveis `grimoire` e `dervs`,
servidor `vps-teste` só olha):**

- Botões: Reiniciar só onde `reiniciavel === true`; nenhum em `ajudei-db`, com a frase de
  bloqueio; `ordens: null` → nenhum botão novo e o convite; `sem_dados` → nenhum botão.
- A frase: `fraseDoPedido("reiniciar","grimoire-web","vps-ovh")` e a de `voltar`, iguais às de
  I4 (texto escrito no teste); o `confirmar` recebe esse título e "Pode fazer"/"Agora não".
- O fio da tela com `fetch` e `navigator.credentials.get` falsos: preparar recebe
  `maquina_id` **número**; o `get` recebe `rpId`, `userVerification: "required"`,
  `allowCredentials` com os ids; assinar recebe os 5 campos; cancelado → nenhum POST a
  assinar; cada 409/403/404/400/401/429 → a frase exata.
- Cada um dos 8 estados de `pedidos` → a frase exata com `haQuanto`; `nao_pegou` nunca contém
  "feito"; cada `motivo` → a frase da tabela.
- Linha com pedidos: com `linha_com_ordens`, as duas escolhas e os apelidos; com `null`, o
  texto de cadastrar chave e o link `#/conta`, e nenhuma linha com `--ordens` no DOM.
- Jargão no texto visível das funções novas (fora de `pre`/`code`), sem caixa:
  `webauthn|assinatura|\btoken\b|cont[eê]iner|docker|deploy|sudo|systemd|\bagente\b|\blogin\b|instala[cç][aã]o`
  ausente; as funções novas entre os marcadores `CONECTAR`; nenhuma usa `innerHTML`,
  `Number(`, `parseInt(`.

**Sabotagens:** escrever "contêiner" num `textContent` novo → jargão vermelho; mostrar o botão
com `x.reiniciavel !== false` → caso `ajudei-db`; trocar "para a versão anterior" por "à versão
anterior" só no JS → o caso da frase (e, no F, o fio); tratar `nao_pegou` como `feito` → o
caso de estados; mandar `maquina_id: s.maquina_id` (texto vindo de `dataset`) → o caso do
número.

Verificação:
```bash
cd /c/Users/Desktop/source/repos/dervs && for t in test_pedidos_tela test_servidor_tela test_conectar_tela test_github_tela test_design test_menu test_voz_tela test_progresso_tela test_conectar_ponta_a_ponta; do python $t.py >/dev/null 2>&1 || echo "FALHOU $t"; done
```

### F — O fio inteiro, a CI e a documentação (sequencial, depois de mesclar E2, E1, E3)

Arquivos: `test_acoes_fio.py`, `.github/workflows/ci.yml`, `CLAUDE.md`,
`docs/operacao/ligar-um-servidor.md`, `README.md`, `docs/A-APLICACAO.md`; `Dockerfile` e
`test_imagem.py` só se `servir.py` passou a importar módulo novo (não deve: `tarefas` e
`passkey` já estão na imagem; `ajudante_servidor.py` já é copiado).

- `test_acoes_fio.py`:
  - `OPedidoAtravessaTudo`: servidor de verdade; conta com a chave `publica_k1` do
    `VETOR_DE_FORA` registrada (`banco.guardar_chave_de_acesso`, contador 0, o `cred_id` do
    teste); `Hub._rp_id` → `"dervs.com.br"`; `Hub._numero_da_ordem` → o `numero` de I0;
    `Hub._segundos_agora` → `1791558000`. O ajudante **baixado** (molde
    `test_servidor_fio`) é instalado com `--ordens` numa raiz temporária com Docker falso
    (`grimoire-web`, rótulo `grimoire`); o `ordens.json` gravado tem `ident`, `origem` e `rp_id`
    trocados para os do vetor (`7f3a...`, `https://dervs.com.br`, `dervs.com.br`) — escrito no
    teste com o motivo: o vetor foi assinado para o domínio de produção. `medir` → preparar pela
    sessão → o `desafio` devolvido é `I1hYDAUhTGY5VpoQX-AjUNLOox129P1vbq2JZEUJDYQ` → assinar
    com `cliente`/`autenticador`/`assinatura` do caso `valido` → 200 → `ordens(agora=1791558010)`
    busca, confere, chama `fazer` com `["docker","restart","grimoire-web"]` (dublê devolve 0) e
    manda o desfecho → `/api/dados` traz o pedido `feito`. Segunda passada: `repetida` nunca
    chega a `fazer`. Mesma coisa com `valido_voltar` e o dublê devolvendo 1 → `nao_deu`,
    `codigo 1`.
  - `AsDuasPontasMontamAMesmaOrdem`: `aj.texto_da_ordem(c) == tarefas.texto_da_ordem(c)` na
    tabela I0 e nos casos `None`; `aj.impressao == banco.impressao_da_chave` em `G` e em
    `publica_k1`; `aj.MOTIVOS_DA_RECUSA == tarefas.MOTIVOS_DA_RECUSA`.
  - `AFraseEAMesma`: em node, `fraseDoPedido(...)` == `Hub._frase_do_pedido(...)` nos dois tipos.
  - `OQueATelaLeOServidorEntrega`: `campos(var, fn)` das funções de I6 ⊂ chaves reais de
    `/api/dados`, `/api/ajudante/linha` e da resposta de preparar; as duas rotas literais do
    `painel.js` existem em `servir.ROTAS`.
  - `DesligadoNasDuasPontas`: ajudante instalado **sem** `--ordens` + ordem assinada válida no
    banco → o ajudante não chama a rede; o DERVS responde preparar com 409 `so_olha` e
    `/api/dados` traz `ordens: null`.
  - **Sabotagens:** mudar uma linha de `texto_da_ordem` só no ajudante, ou só em `tarefas` →
    vermelho; renomear `voltaveis` só no JS → vermelho; trocar a aspa da frase só no servidor
    → vermelho.
- `ci.yml`: um passo por arquivo novo — `test_ajudante_acoes`, `test_ordens_servidor`,
  `test_pedidos_tela`, `test_acoes_fio`.
- `CLAUDE.md`: seção "Os pedidos ao servidor (entrega C)" com as travas que quebram em
  silêncio (desligado por padrão nas duas pontas; C0 remontado dos campos; vetor de fora fixo e
  as duas costuras de teste; `sudoers` em pedaços; unidade própria sem as diretivas da B;
  120 s/30 min; `bloqueado` nas duas pontas; a promessa honesta) e as dívidas.
- `docs/operacao/ligar-um-servidor.md`: a parte "Olhar e aceitar pedidos", completa (os comandos são
  do servidor, não do PowerShell): onde colar, o que aparece ("Pedidos ligados: reiniciar
  sistemas; voltar a versão de: ..."), se der errado (`visudo` reprovou, comando de publicar
  com dono errado), como desligar (colar a linha só olhar), e o limite honesto.
- `README.md` e `docs/A-APLICACAO.md`: o que o DERVS faz agora, e o que continua nunca fazendo.
- Coordenador: avisar a janela do `dervs-voz` (nada muda para ele, mas a tela ganhou poder);
  revisões de segurança (**duas passadas**, obrigatórias: VPS do Ajudei), Python e conteúdo.

Verificação:
```bash
cd /c/Users/Desktop/source/repos/dervs && python test_acoes_fio.py && for t in test_*.py; do python "$t" >/dev/null 2>&1 || echo "FALHOU $t"; done; for t in test_*.py; do grep -q "python $t" .github/workflows/ci.yml || echo FALTOU $t; done
```
Saída esperada: nenhuma linha `FALHOU`, nenhuma `FALTOU`.

### F-2 — Conferência manual (não é código)

Localhost (4790, `DERVS_AMBIENTE=local`, `servir.py` reiniciado): cartão em 360 px, a linha com
pedidos, o diálogo, o PIN do Windows de verdade (o `rp_id` local é `localhost`). VM Linux com
Docker e systemd: `visudo -cf` de verdade, `sudo -n` pela unidade nova, `docker restart`,
`deploy --voltar` com um projeto de teste, a recusa com o site parado. VPS (mão do dono, portão
4, depois de publicar e das duas revisões de segurança): idem.

## Riscos e o que nenhum teste prova

1. `sudo`, `visudo`, systemd e Docker de verdade só a F-2 prova; os testes usam dublês.
2. O aparelho não mostra o pedido: com o dervs.com.br tomado, cada toque vira no máximo uma
   ordem da lista fechada, 6 por hora. Escrito na tela; fechar de vez é outra entrega (VOZ).
3. A unidade dos pedidos não tem `NoNewPrivileges`/`ProtectSystem`: a contenção é a lista
   fechada do código + o `sudoers` exato + a conferência da digital. Vai à revisão diretiva por
   diretiva.
4. Chave nova no painel não chega ao servidor sem colar a linha de novo (`linha_velha`).
5. CI fora até 01/11 (cota): a verificação é a suíte local, Windows; o caso de permissão de
   arquivo do comando de publicar só roda fora do Windows.
