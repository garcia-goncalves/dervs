# Plano de execução: Conectar simples, entrega A

Ramo `feat/conectar-simples` @ `b119fd4`. Para gravar em `docs/superpowers/plans/dervs-conectar-simples-a.md`.

**Índice e ADR:** não usei o grafo, que está fora do ar. Toda a análise saiu de Grep e Read no disco, com o HEAD conferido por `git log` (`b119fd4`, árvore limpa). Também não consultei o ADR: o equivalente dele aqui é o `CLAUDE.md` do repositório, que li inteiro.

---

## Contexto verificado

- **CSRF vencido.** A frase `"recarregue a pagina (token vencido)"` aparece em 13 pontos de `servir.py`: 12 escritos à mão (linhas 1372, 1401, 1437, 1463, 1500, 1578, 1666, 1695, 1726, 1824, 2039, 2174) e um em `_guarda_de_escrita` (3581). O spec falava em 14.
- **`escrever()`** fica em `assets/painel.js:1263-1269`. Não lê status nenhum. Todo POST do painel passa por ela; a única exceção é `/sair` (painel.js:3542).
- **`rota()`** (`painel.js:111-114`) parte o hash em `/`. Por isso `#/conectar?autorizar=X` vira a tela `"conectar?autorizar=X"` e cai no painel. É preciso consertar.
- **`usar_pareamento`** (`banco.py:3159-3162`) já cria a máquina com `visto_em` preenchido. Assim `visto_em` não separa "pareou" de "mandou a primeira medição", e o design exige essa diferença. Falta uma coluna nova (`relatado_em`).
- **`ver_projeto`** (`banco.py:3652-3657`) zera `arquivado_em` a cada relatório. Não serve para esconder, o que confirma o spec.
- **`maquinas_do_usuario`** (`banco.py:3210-3230`) devolve só a contagem; `projetos_da_maquina` (`banco.py:3665`) tem nome e pasta.
- **Repositórios do GitHub.** O coletor mede só projetos que o relatório traz com `git.remoto_slug` (`coletar_github._slugs`, 1207-1224). Logo, todo repositório medido já é um projeto. O dono do repositório (a parte antes de `/` no slug) é exatamente a conta da instalação que o alcança.
- **Medição de site.** `mede_site` (`coletar_github.py:306-347`) devolve `{url, ok, codigo, erro, ms, tentativas}`, com `erro` igual ao nome da exceção ou `"nao_resolveu"`. A peneira `enderecos_publicos` (153-172) não distingue "não resolve" de "resolve para dentro". Isso é de propósito (falha fechada por conjunto).
- **`test_rotas.py`.** `PROIBIDO = acao|execucao|exec|terminal|pty|shell|comando|grafo` vale para o caminho e para `funcao.__name__`. O andarilho `_alcancaveis` reprova qualquer rota cujo grafo alcance os nomes `subprocess, system, popen, eval, exec, compile, __import__, coletar`, entre outros. Consequência: `re.compile` ou `platform.system()` dentro de um método alcançável por rota reprova.
- **`test_servir.py:2018`.** `PALAVRAS_PROIBIDAS = senha, chave, token, ssh, secret, credencial, key` vale para os nomes de campo lidos por `_texto_do_corpo` e `_numero_do_corpo`. Daí o campo se chamar `pedido`, nunca `token` ou `device_code`.
- **Linha de comando presa por teste.** `test_conectar_ponta_a_ponta.py:122-139` lê de `painel.js:2401-2402` a linha exata `"python \"<CAMINHO DO DERVS>/agente/enviar.py\" --alvo " + location.origin + " --codigo " + d.codigo`. `test_servir` lê `VALIDADE_GITHUB_S` (`painel.js:478`).
- **Dockerfile.** Copia `conectador.py` por nome (`Dockerfile:123`) e não copia `agente/`. `test_imagem.PROIBIDOS` (43) não lista `agente/executor.py`, que importa `execucao`.
- **Fim de linha.** `.gitattributes` tem `* text=auto eol=lf`. Um `.cmd` guardado no repositório fica com LF, e lote do Windows com LF quebra rótulos.
- **Login perde o endereço.** Entrar pelo GitHub ou pela porta local devolve 302 para `/` (`servir.py:1093`, `:1153`) e perde o fragmento. Chave e código fazem `location.reload()` (`cortina.js:50`, `portas.js:87,120`) e preservam.
- **CI e Python.** A CI roda Python 3.12 (`ci.yml:29`) e lista cada `test_*.py` à mão, com um passo que reprova arquivo esquecido (`ci.yml:70-80`).
- **CSP.** É `default-src 'self'` (`infra/nginx-dervs.conf:130`). Atributo `style=` inline é descartado.
- **Pacote do computador.** As dependências reais de `agente/enviar.py` são `coletar`, `tarefas`, `banco` (→ `tarefas`) e `documentos`. O único import preguiçoso é `from agente import executor` (`enviar.py:307`), que fica fora do pacote. Lista fechada: `agente/__init__.py`, `agente/enviar.py`, `coletar.py`, `banco.py`, `documentos.py`, `tarefas.py`.

### Premissas do spec e do design que não se confirmaram ou foram ajustadas (cada uma vira decisão neste plano)

1. **"O relatório diz que só mede."** Trocado por uma coluna `maquina.so_mede`, gravada pelo servidor no momento em que o computador pareia pelo arquivo. O servidor é a fonte de verdade; o relatório não muda.
2. **"Olhei a pasta C:\… e não achei".** O servidor não conhece a pasta escolhida (as raízes não sobem no relatório). O texto passa a ser "Olhei a pasta que você escolheu e não achei nenhum projeto com histórico de versões…".
3. **"Nome não existe" e "rede interna"** viram um estado só, `nao_publico`, sem botão de guardar. A peneira não distingue os dois de propósito, e `/api/enderecos/guardar` recusaria os dois de qualquer jeito.
4. **Ordem dos passos no computador:** pasta primeiro, navegador depois (no design, o passo 4 abre o navegador antes da pasta). Assim continua valendo a lei "fechar sem escolher não deixa lixo nem pedido aberto". Os textos dos passos 4 a 6 mudam (ver E3-2).
5. **Cortados, como o spec permite:** a sugestão por `homepageUrl` e o aviso de "ajudante desatualizado". Ficam, por último, "O que isso faz?" e as imagens por passo.

---

## Contratos (destravam o paralelo; ninguém muda sem mudar aqui)

### C0. Nomes conferidos contra `test_rotas.PROIBIDO`

| Rota | Método | Função | Acesso | PROIBIDO |
|---|---|---|---|---|
| `/agente/pedir` | POST | `Hub._agente_pedir` | aberta | limpo |
| `/agente/esperar` | POST | `Hub._agente_esperar` | aberta | limpo |
| `/agente/pacote` | GET | `Hub._agente_pacote` | maquina | limpo |
| `/api/pedido` | GET | `Hub._pedido_ver` | dado | limpo |
| `/api/pedido/autorizar` | POST | `Hub._pedido_autorizar` | dado | limpo ("autorizar" não tem `acao`; **"autorizacao" teria, proibido**) |
| `/api/conectar.cmd` | GET | `Hub._arquivo_de_conectar` | dado | limpo ("cmd" não casa; **"comando" casaria**) |
| `/api/projetos/mostrar` | POST | `Hub._projeto_mostrar` | dado | limpo |
| `/api/enderecos/medir` | POST | `Hub._endereco_medir` | dado | limpo ("medir" e "medicao" não contêm `acao`) |
| ~~`/api/conectador`~~ | POST | ~~`Hub._conectador`~~ | — | **REMOVIDA** (o botão novo é GET; o código de 6 dígitos sai do arquivo) |

- **Ajudantes novos de `servir.py`:** `_recusa_pagina_velha`, `_endereco_publico`, `_ler_pacote`. Nenhum nome contém `instalacao`, `autorizacao` ou `verificacao`.
- **`re.compile` só em constante de módulo**, como `_CODIGO_CURTO = re.compile(...)`, nunca dentro de método.
- **Variáveis de ambiente:** nenhuma nova é lida em `servir.py` ou `banco.py`. Por isso `docker-compose.yml` e `test_publicar` **não mudam**.

### C1. 403 de página velha

```python
Hub.PAGINA_VELHA = {"erro": "recarregue a pagina (token vencido)", "motivo": "pagina_velha"}
def _recusa_pagina_velha(self): return self._json(403, dict(self.PAGINA_VELHA))
```

- Substitui os 13 pontos. Depois da remoção de `_conectador` restam 12: 11 escritos à mão e mais `_guarda_de_escrita`.
- Os outros 403 não ganham `motivo`: `{"erro":"origem nao permitida"}`, `{"erro":"entre de novo"}`, `{"erro":"host nao permitido"}`.
- A frase continua igual, porque `test_servir` a cobra.
- A tela abre a faixa **só** com `status === 403 && corpo.motivo === "pagina_velha"`.

### C2. `POST /agente/pedir` (aberta)

- **Corpo:** `{"maquina": "PC-ESCRITORIO"}`. É opcional, passa por `Hub._limpo(v, 120)`; vazio vira `"computador"`.
- **200:** `{"pedido": "<opaco, ≥43 car., segredo do computador>", "codigo": "K7M4-2QXP", "minutos": 10, "intervalo": 5}`
- **400:** `{"erro": "pedido invalido"}` (corpo não-JSON ou não-dict).
- **429:** `{"erro": "nao deu"}`, balcão `"pedir"`, `TETO_DE_PEDIDOS = 10` por origem e janela (900 s).
- **503:** `{"erro": "tente de novo em um minuto"}` depois de 5 colisões do código.
- **Antes de criar:** `banco.limpar_pedidos_vencidos()`.

### C3. `POST /agente/esperar` (aberta; é o "token endpoint" do RFC 8628)

- **Corpo:** `{"pedido": "<o de C2>"}`, string de 16 a 128 caracteres.
- **202:** `{"estado": "esperando", "intervalo": 5}`
- **200:** `{"token": "<token da máquina>"}`, **uma vez só**. Cria `maquina` com `so_mede=1`, `executa=0`, `usuario_id` de quem autorizou, `nome` vindo do pedido e `visto_em = agora` (mesmo comportamento de `usar_pareamento`).
- **400:** `{"erro": "pedido invalido"}`
- **404:** `{"erro": "nao existe"}`. Resposta igual para desconhecido, vencido ou já resgatado.
- **429:** `{"erro": "nao deu"}`, balcão `"esperar"`, `TETO_DE_ESPERAS = 300` por origem. O computador dobra o intervalo.

### C4. `GET /api/pedido?codigo=K7M4-2QXP` (dado)

- **Normalização:** maiúsculas, sem espaço nem hífen, exatamente 8 caracteres de `banco.ALFABETO_DE_RECUPERACAO` (`23456789ABCDEFGHJKMNPQRSTUVWXYZ`), recomposto como `XXXX-XXXX`.
- **200:** `{"codigo": "K7M4-2QXP", "maquina": "PC-ESCRITORIO", "minutos": 8, "expira_em": "<iso>", "estado": "esperando"|"autorizado"|"conectado"}`
  - `minutos` é o que falta, arredondado para cima, nunca menos que 0.
  - `conectado` quer dizer já resgatado, e aparece só para a conta que autorizou.
- **400:** `{"erro": "codigo invalido"}`, antes do balcão e sem tocar o banco.
- **401:** recusado no despacho.
- **404:** `{"erro": "nao existe"}`. Vale para não existe, vencido ou autorizado por **outra** conta.
- **429:** `{"erro": "nao deu"}`, balcão `"codigo_curto"`, `TETO_DE_CODIGOS_CURTOS = 20`.

### C5. `POST /api/pedido/autorizar` (dado)

- **Corpo:** `{"codigo": "K7M4-2QXP"}`.
- **Antes de tudo, `_guarda_de_escrita`:** 403 `origem nao permitida`, 403 de C1 ou 400 `pedido invalido`.
- **400:** `{"erro": "codigo invalido"}`.
- **429:** o mesmo balcão `"codigo_curto"` de C4.
- **404:** `{"erro": "nao existe"}`.
- **200:** `{"ok": true, "maquina": "PC-ESCRITORIO", "ja_estava": false}`. Se a mesma conta clicar de novo, `"ja_estava": true`.
- **Efeito:** grava `usuario_id`, `autorizado_em = agora` e `expira_em = max(expira_em, agora + 120 s)`.

### C6. `GET /agente/pacote` (maquina, `Authorization: Token <t>`)

- **200:** `{"versao": "<sha256 hex>", "so_mede": true|false, "arquivos": [{"caminho": "agente/__init__.py", "conteudo": "<utf-8>"}, …]}`
  - Os arquivos vêm na ordem de `Hub.PACOTE = ("agente/__init__.py", "agente/enviar.py", "coletar.py", "banco.py", "documentos.py", "tarefas.py")`.
  - `versao = sha256(Σ caminho + "\n" + conteudo + "\n")`.
- **401:** recusado no despacho.
- **429:** `{"erro": "nao deu"}`, balcão `"pacote"`, chave `"maquina:<id>"`, `TETO_DE_PACOTES = 10`.
- **503:** `{"erro": "o pacote nao esta nesta copia"}` se faltar qualquer arquivo. Nunca entrega pacote parcial.

### C7. `GET /api/conectar.cmd` (dado) e o acordo E1↔E2 sobre arquivos

- **200**, com os cabeçalhos:
  - `Content-Type: application/octet-stream`
  - `Content-Disposition: attachment; filename="conectar-dervs.cmd"`
- **Corpo, montado pelo servidor:** `conectador.cmd` lido do disco, depois a linha `#:DERVS-PYTHON`, depois `conectador.py` com a linha `ALVO = "<alvo>"   # DERVS:ALVO` trocada por `_injetar(fonte, alvo)` (assinatura nova, só ALVO). **Toda linha termina em `\r\n`** (`"\r\n".join(texto.splitlines()) + "\r\n"`). O corpo é ASCII puro.
- **`alvo`** vem de `_endereco_publico()`: `"https://" + DOMINIO`; se `DOMINIO` estiver vazio, `"http://" + Host`, com o `Host` já conferido contra `HOSTS_OK` no despacho.
- **401:** recusado no despacho. **503:** `{"erro": "o arquivo de conectar nao esta nesta copia"}`.
- **A rota não cria pareamento nenhum.**
- **O que E1 garante:**
  - `conectador.cmd` é ASCII.
  - O último comando executável dele é `exit /b %ERRORLEVEL%`.
  - Ele **não** contém nenhuma linha que comece com `#:DERVS-PYTHON`.
  - Ele extrai o Python procurando os bytes `\n#:DERVS-PYTHON`.
  - `conectador.py` tem exatamente uma linha terminada em `# DERVS:ALVO`, nenhuma em `# DERVS:CODIGO` e nenhuma que comece com `#:DERVS-PYTHON`.

### C8. `POST /api/projetos/mostrar` (dado)

- **Corpo:** `{"projeto": "clinica-agenda", "mostrar": false}`.
- **200:** `{"projeto": "clinica-agenda", "mostrar": false, "ocultos_n": 1}`
- **400:** `{"erro": "diga o projeto e se ele aparece"}` quando o projeto está vazio ou passa de 200 caracteres, ou quando `mostrar` não é `bool` (exatamente `true` ou `false`).
- **401 e 403:** como em C1.
- **404:** `{"erro": "nao existe"}` quando o projeto não é desta conta.
- **429:** balcão `"mostrar"`, `TETO_DE_MOSTRAR = 60`.

### C9. `GET /api/dados` (acréscimo)

- Ganha `"ocultos": ["nome", …]`, sempre presente e ordenado.
- `projetos` e `pendencias` saem **sem** os escondidos, e `grupos` e `briefing` são recalculados sobre a lista podada (`regras.agrupar` e `memoria.briefing`, as duas puras).
- **A poda é em `_dados`, depois de `_estado`.** `montar_estado` continua devolvendo tudo.

### C10. `GET /api/maquinas` (acréscimo)

- Cada máquina passa a ser `{id, nome, criado_em, visto_em, executa, projetos, so_mede: bool, relatado_em: iso|null, projetos_vistos: [{projeto, caminho, visto_em, oculto: bool}]}`.
- `projetos_vistos` leva só os não arquivados, ordenados por projeto, com teto de 300.
- **Mudança relacionada:** `POST /api/maquinas/autorizar` com `ligado: true` numa máquina `so_mede` devolve **409** `{"erro": "este computador so mede"}`.

### C11. `GET /api/github` (acréscimo, decisão 4 do design)

- Cada `instalacoes[i]` ganha `"repositorios": [{"projeto": "loja-da-ana", "slug": "loja-da-ana/site", "medido": true, "oculto": false}]`, ordenado por projeto.
- **Fonte:** o relatório da conta. Entra o projeto cujo `local.dados.git.remoto_slug` tem dono (a parte antes de `/`) igual, sem diferença de caixa, a `conta_login`.
- `medido` diz se já existe a camada `github` daquele projeto.
- Com `conta_login` nulo, a lista vem `[]`.

### C12. `POST /api/enderecos/medir` (dado; **nunca grava**)

- **Corpo:** `{"url": "https://loja-da-ana.com.br"}`.
- **200:** `{"url", "ok": true|false|null, "codigo": int, "erro": str, "ms": int, "medido_em": iso}`. Os campos vêm de `coletar_github.mede_site`, chamada qualificada.
- **400 com `motivo: "forma"`:** `{"erro": "escreva o endereco completo, comecando por https://", "motivo": "forma"}`. Vale para URL vazia, com mais de 2048 caracteres, que não se lê, com esquema que não é http(s) ou sem nome de máquina.
- **400 com `motivo: "nao_publico"`:** `{"erro": Hub.ENDERECO_RECUSADO, "motivo": "nao_publico"}`. Sai quando `url_segura` dá falso **ou** `host_publico` dá falso.
- **429:** balcão `"medir"`, `TETO_DE_MEDICOES = 20`. O teto vem depois de `url_segura` e antes de qualquer rede.
- **401 e 403:** como em C1.
- **`POST /api/enderecos/guardar`** passa a aceitar `"medir": false`, que pula `mede_site` e devolve `{"projeto", "url", "guardado": true, "ok": null, "codigo": null, "erro": "", "medido_em": null}`. Sem o campo, nada muda.

### C13. Nomes no `painel.js` que o teste de fio lê (E3 tem de usar estes nomes **e** estes parâmetros)

| Função | Lê |
|---|---|
| `escrever(url, corpo)` | literal `motivo === "pagina_velha"`; chama `abrirFaixaPaginaVelha()` |
| `pintarAutorizar(p)` | `p.codigo`, `p.maquina`, `p.minutos`, `p.estado` |
| `linhaDeComputador(m)` | `m.id`, `m.nome`, `m.visto_em`, `m.relatado_em`, `m.projetos`, `m.executa`, `m.so_mede`, `m.projetos_vistos` |
| `linhaDeProjetoVisto(a)` | `a.projeto`, `a.caminho`, `a.oculto` |
| `linhaDeContaDoGithub(c)` | `c.conta_login`, `c.conta_tipo`, `c.medidos`, `c.medido_em`, `c.gerenciar_url`, `c.repositorios` |
| `linhaDeRepositorio(r)` | `r.projeto`, `r.slug`, `r.medido`, `r.oculto` |
| `pintarResultadoDaMedicao(r)` | `r.ok`, `r.codigo`, `r.erro`, `r.ms`, `r.url`, `r.motivo` |

Chamadas literais: `escrever("/api/pedido/autorizar"`, `escrever("/api/projetos/mostrar"`, `escrever("/api/enderecos/medir"`, `fetch("/api/pedido?codigo="`, e o link `href="/api/conectar.cmd"` com `download="conectar-dervs.cmd"`.

### C14. Banco (E2): esquema e funções

**Tabela `pedido_de_computador`:**
```sql
CREATE TABLE IF NOT EXISTS pedido_de_computador (
  pedido_hash   TEXT PRIMARY KEY,               -- hash_token(pedido)
  codigo_hash   TEXT NOT NULL UNIQUE,           -- hash_codigo("XXXX-XXXX")
  maquina_nome  TEXT NOT NULL DEFAULT '',
  criado_em     TEXT NOT NULL,
  expira_em     TEXT NOT NULL CHECK (expira_em LIKE '____-__-__T__:__:__+00:00'),
  usuario_id    INTEGER REFERENCES usuario(id) ON DELETE CASCADE,  -- NULL ate autorizar
  autorizado_em TEXT,
  usado_em      TEXT,
  maquina_id    INTEGER REFERENCES maquina(id) ON DELETE SET NULL);
```

**Tabela `projeto_oculto`:**
```sql
CREATE TABLE IF NOT EXISTS projeto_oculto (
  usuario_id   INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
  projeto      TEXT NOT NULL CHECK (length(trim(projeto)) > 0),
  escondido_em TEXT NOT NULL,
  PRIMARY KEY (usuario_id, projeto));
```

**Colunas novas em `maquina`:** `so_mede INTEGER NOT NULL DEFAULT 0` e `relatado_em TEXT`.
- Entram no `ESQUEMA` e na migração nova `_migrar_maquina_conectar_simples(con)`, chamada em `migrar()`.
- A migração faz um `ALTER` por coluna, cada um com a própria checagem de "já rodou". Se a tabela ainda não existe, ela sai sem fazer nada.
- Depois preenche o histórico: `UPDATE maquina SET relatado_em = visto_em WHERE relatado_em IS NULL AND EXISTS (SELECT 1 FROM projeto_conectado p WHERE p.maquina_id = maquina.id)`.

**`FILHAS_DE_USUARIO`** ganha `"pedido_de_computador"` e `"projeto_oculto"`.

**Funções:**
- `novo_codigo_de_pedido() -> str` e `normalizar_codigo_de_pedido(texto) -> str` (devolve `""` quando inválido).
- `limpar_pedidos_vencidos(con=None) -> int`
- `abrir_pedido_de_computador(nome_maquina, minutos, con=None) -> (pedido, codigo)`. Usa `INSERT` puro e levanta `IntegrityError` em colisão.
- `ver_pedido_de_computador(codigo, usuario_id, agora_iso="", con=None) -> dict|None`
- `autorizar_pedido_de_computador(codigo, usuario_id, agora_iso="", con=None) -> "ok"|"ja_estava"|"nao_existe"`. O `UPDATE … WHERE usuario_id IS NULL AND usado_em IS NULL AND expira_em > ?` é a própria guarda.
- `resgatar_pedido_de_computador(pedido, agora_iso="", con=None) -> ("esperando", None) | ("token", token) | ("nao_existe", None)`. O `UPDATE … SET usado_em` é atômico, e o `INSERT` da máquina vai na mesma transação.
- `maquina_so_mede(maquina_id, usuario_id, con=None) -> bool`
- `ligar_execucao(...)`: acrescentar `AND (so_mede = 0 OR ? = 0)`, passando `ligado` como esse parâmetro. É a segunda tranca.
- `receber_relatorio`: a linha 3622 passa a gravar também `relatado_em = agora`.
- `projeto_da_conta(usuario_id, projeto, con=None) -> bool`: medida `local` da conta **ou** `projeto_conectado` de máquina da conta.
- `mostrar_projeto(usuario_id, projeto, mostrar: bool, con=None) -> None`: `INSERT OR IGNORE` ou `DELETE`.
- `projetos_ocultos(usuario_id, con=None) -> set`
- `maquinas_do_usuario`: devolve também `so_mede`, `relatado_em` e `projetos_vistos`.
- `repositorios_do_github_por_dono(usuario_id, con=None) -> dict[str(casefold), list]`. O slug é validado sem regex compilada: string, um único `/`, até 200 caracteres.

---

## Lacunas e decisões do `design.md`: tratamento

| # | Item do design | Tratamento |
|---|---|---|
| 1 | [decisão] Sondagem começa também no clique de baixar | **Aceita.** E3-2. Sucesso = id novo de máquina **ou** `relatado_em` de qualquer máquina mais novo que o início da espera (cobre quem roda de novo num PC já ligado). |
| 2 | [decisão] Código `XXXX-XXXX` sem ambíguos | **Aceita.** `ALFABETO_DE_RECUPERACAO` (31 símbolos, sem 0/O/1/I/L). C4 e C14. |
| 3 | [decisão] Repositório que não é projeto: a linha não mostra chave | **Resolvida por construção.** C11 só lista repositórios que já são projetos, então esse ramo nunca acontece. E3 **não** implementa a frase "Ainda não é um projeto…". |
| 4 | [decisão] "Tentar de novo" só no erro da procura | **Aceita.** E3-4. Um 429 da procura automática fica **calado**: é o nosso automatismo batendo no próprio teto. |
| 5 | [decisão] `recado()` troca o texto de erro com a faixa aberta | **Aceita.** E3-1. Variável `PAGINA_VELHA`; `recado(t, true)` passa a escrever "Não foi feito. Veja o aviso no alto da página." |
| 6 | [decisão] Dois ou mais servidores: campo visível e obrigatório | **Aceita, só na tela.** E3-5. Com 0 servidores, a tela chama `POST /api/servidores/guardar {"nome":"Meus sites"}`; com 1, usa ele. |
| 7 | [ponto para o plano] Voltar a `?autorizar=` depois de entrar | **Resolvido.** `assets/cortina.js` guarda o código (validado por regex) em `sessionStorage["dervs-autorizar"]`. O `inicio()` do painel o devolve para `#/conectar?autorizar=` e apaga a chave. Cobre a volta do GitHub e a local, que perdem o fragmento. |
| 8 | [para o plano] Nomes de repositório do GitHub | **C11.** |
| 9 | Achado: `--e5`, `--r2`, `--fundo-fraco` | Fora de escopo, mencionado no fim. Peça nova só usa tokens que existem. |
| 10 | Lacuna 1 (`.marca` usa `--estado-*`) | Mantida como está. A faixa nova não usa `--estado-*`. |
| 11 | Lacuna 2 (esconder depois, em vez de escolher antes) | Segue o spec. |
| 12 | Lacuna 3 (GitHub e servidor dentro de Conectar) | Nada a fazer. |
| 13 | Lacuna 4: nome do arquivo | `conectar-dervs.cmd` (C7). |
| 14 | Lacuna 4: formato do código | `XXXX-XXXX` (item 2). |
| 15 | Lacuna 4: botão de recusar o pedido | **Não existe.** Só o aviso; o pedido vence sozinho. |
| 16 | [Conferir no ar] aviso do Chrome | Item F-2, manual. O texto do passo 1 fica condicional. |

---

## Riscos e o que nenhum teste prova

1. **Aviso do Chrome ao baixar `.cmd` de dervs.com.br.** Só dá para medir no ar, com o arquivo servido de verdade. Se o Chrome não avisar, o passo 1 vira "Se o Chrome perguntar".
2. **Diálogo do Windows e antivírus.** O escudo vermelho foi medido no PC do dono com ZoneId=3 feito à mão. A marca que o Chrome grava (ZoneId=3 + HostUrl) pode mudar o diálogo. A combinação `curl.exe` + `certutil` + `powershell -Command` pode acender a heurística do Defender. Se acender: trocar `certutil -hashfile` por `powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 …).Hash"` e medir de novo. Nenhum teste de CI roda o lote.
3. **Python embutível não traz tkinter.** A pasta é escolhida por PowerShell 5.1 com `FolderBrowserDialog` (`-STA`). Em máquina corporativa com Constrained Language Mode, o `Add-Type` falha e o programa cai para digitar a pasta (`pasta_pelo_teclado`). Isso só é provado por dublê.
4. **Esconder é por nome de projeto, e por conta.** Por isso a tabela `projeto_oculto` (`arquivado_em` zera a cada relatório, `banco.py:3656`). Consequências aceitas:
   - dois computadores com o mesmo nome de projeto escondem juntos;
   - renomear a pasta faz o projeto reaparecer;
   - projeto escondido continua gerando aviso para o DERVS-VOZ, porque a vigília lê `montar_estado` e não `_dados`.
5. **Python 3.14.8 no PC contra 3.12 na CI.** O pacote nunca roda em 3.14 na CI. Mitigação em F-2: rodar `python.exe agente\enviar.py --help` com o embutível. **O SHA-256 do spec não foi conferido por mim:** E1 baixa o zip e confere antes de gravar a constante.
6. **Os 15 s do critério 2 dependem do tempo da primeira medição.** O estado "apareceu, ainda não mandou a primeira medição" é o honesto (Lei 2) enquanto ela não chega.
7. **Agendamento.** ONLOGON exige administrador e cai no plano B (a cada 10 min). Ninguém vai reiniciar o Windows para ver a tarefa rodar.
8. **Phishing remoto (RFC 8628 §5.4).** Quem mandar ao dono um link com o próprio código e conseguir o clique liga uma máquina estranha à conta dele. Essa máquina só mede: consegue injetar projetos falsos no painel, mas não executa nada (`so_mede` com duas trancas) e não lê nada (`/api/*` não aceita token de máquina). Mitigação: frase de aviso, mais nome e código conferidos dos dois lados. **Revisão de segurança obrigatória.**
9. **`/agente/pedir` é aberta e cria linha.** O teto é por origem, com limpeza do vencido. Não há teto global, de propósito: teto compartilhado tranca o dono. Um site de terceiros pode gastar o balcão `pedir` do IP do dono (10 por 15 min).
10. **O pacote entrega código-fonte do servidor** (`banco.py`, `coletar.py`) a toda máquina pareada de qualquer conta convidada. Não há segredo no código (lei do repositório), mas o repositório é privado. Decisão para a revisão de segurança.
11. **Sessão vencida (401) não abre a faixa.** Ela cobre só o 403 `pagina_velha`. Se a sessão venceu, o link `<a download>` baixa um JSON de erro com nome `.cmd`. Caso de borda, aceito.
12. **Armadilhas do vigia:**
   - `re.compile`, `platform.system` ou `exec` em código alcançável por rota reprova `test_rotas`;
   - campo de corpo com `token` ou `chave` reprova `test_servir.PALAVRAS_PROIBIDAS`;
   - CRLF: o repositório força LF, então o servidor converte. Lote com LF quebra no Windows.
13. **DERVS-VOZ.** Parear pelo arquivo grava um token novo em `~/.dervs/agente.json` para o alvo, e o VOZ lê esse arquivo. O coordenador avisa a janela do `dervs-voz` (regra "Avisar o DERVS-VOZ sempre").
14. **Publicação.** Exige a mão do dono (tarefa do VS Code). `servir.py` guarda o código em memória: reinicie antes de conferir clicando. O nginx não muda.
15. **Rodar o `.cmd` num PC já ligado pela linha de comando com `executa = 1`.** O programa reaproveita o token, vê `so_mede: false` no pacote, **não** troca a tarefa agendada e só acrescenta a pasta. Se trocasse, o braço executor morreria.

---

## Divisão por executor (por arquivo, sem sobreposição)

- **E1 (ajudante):**
  - `conectador.py`
  - `conectador.cmd` (novo)
  - `agente/enviar.py`
  - `Dockerfile`
  - `test_imagem.py`
  - `test_conectador.py`
  - `docs/operacao/conectar-uma-maquina.md`
- **E2 (servidor):**
  - `servir.py`
  - `banco.py`
  - `test_servir.py`
  - `test_banco.py`
  - `test_rotas.py`
  - `test_conectar_servidor.py` (novo)
- **E3 (tela):**
  - `assets/painel.js`
  - `index.html`
  - `assets/painel.css`
  - `assets/cortina.js`
  - `assets/CREDITOS.md`
  - `test_conectar_tela.py` (novo)
  - `test_github_tela.py`
  - `test_design.py`
  - `test_menu.py`
  - `test_voz_tela.py`
  - `docs/A-APLICACAO.md` (~150-157 e ~650)
- **F (sequencial, depois dos três):**
  - `test_conectar_fio.py` (novo)
  - `.github/workflows/ci.yml`
  - `CLAUDE.md`
  - `README.md`
  - `docs/LINKS.md`
  - `docs/operacao/parear-o-voz.md`
- **Ninguém edita:** `test_conectar_ponta_a_ponta.py`, `test_agente.py`, `test_voz.py`, `test_publicar.py`, `coletar_github.py`, `docker-compose.yml`, `assets/dervs.css`. E2 e E1 **rodam** esses testes como regressão.
- **`ci.yml` tem um dono só (F).** Até F, o passo "Nenhum arquivo de teste ficou de fora" fica vermelho com os arquivos novos. **Não abrir PR antes de F.**

**Ordem de mesclagem no ramo:** E2, depois E1, depois E3, depois F, com a suíte inteira depois de cada uma. Motivo: o E1 tira o marcador `CODIGO` do `conectador.py`, e a rota antiga `/api/conectador` (que o E2 remove) quebraria se o E1 entrasse primeiro.

---

## Etapas

Comando de regressão usado abaixo (Bash):
```bash
cd /c/Users/Desktop/source/repos/dervs && for t in test_*.py; do python "$t" >/dev/null 2>&1 || echo "FALHOU $t"; done
```
Esperado: nenhuma linha `FALHOU`. Os testes de tela pulam os casos de node se não houver node.

### E2-1. 403 central de página velha
**Objetivo:** todo botão recusado por página velha pode ser reconhecido pela tela.

**Arquivos:** `servir.py`, `test_conectar_servidor.py` (criar).

**Teste antes (`test_conectar_servidor.py`, classe `APaginaVelhaTemMotivo(BaseServidorDeVerdade)`):**
- Para **toda** rota de `servir.ROTAS` com `metodo == "POST"` e `acesso == "dado"`: sessão válida, `Origin` certa e `X-Token` errado devem dar 403, com `motivo == "pagina_velha"` e a frase igual à de hoje.
- Guarda de código-fonte: `inspect.getsource(servir).count("token vencido") == 1`.
- O cabeçalho do arquivo declara `DERVS_AMBIENTE` e `DERVS_COFRE` antes de importar `banco` (`CLAUDE.md`, seção Testes). `if __name__` fica no fim.

**Fazer:** criar o contrato C1 e trocar os 13 pontos.

**Verificação:** `python test_conectar_servidor.py` (verde); `python test_servir.py` e `python test_rotas.py` (verdes).

**Pronto quando:** sabotar um ponto de volta para o dicionário escrito à mão deixa o caso vermelho, e desfazer a sabotagem é feito editando de volta.

**Depende de:** nenhuma.

### E2-2. Pedido de computador, pacote, arquivo `.cmd` e colunas da máquina
**Objetivo:** o arquivo baixado consegue parear sem código de 6 dígitos e baixar o programa que mede.

**Arquivos:** `servir.py`, `banco.py`, `test_conectar_servidor.py`, `test_servir.py`, `test_rotas.py`, `test_banco.py`.

**Teste antes:**
- **Classe `OPedidoDeComputador`:**
  - `pedir` devolve 200 com os campos de C2, e o código casa `^[2-9A-HJKMNP-Z]{4}-[2-9A-HJKMNP-Z]{4}$`.
  - `esperar` antes de autorizar dá 202.
  - `GET /api/pedido` entende minúscula e código sem hífen; código desconhecido dá 404; código torto dá 400.
  - `autorizar` dá 200; depois `esperar` dá 200 com token **uma vez**, e repetir dá 404.
  - A linha da máquina nasce com `so_mede=1`, `executa=0` e `usuario_id=uid`.
  - Outra conta recebe 404 com o mesmo corpo de "não existe", tanto no GET quanto no autorizar.
  - Pedido vencido dá 404, usando `agora_iso` nas funções de `banco`.
  - Tetos: 11 `pedir` dão 429; 21 no balcão `codigo_curto` dão 429; e `/entrada` continua respondendo 204.
  - `/api/maquinas/autorizar` com `ligado:true` numa máquina `so_mede` dá 409 e `executa` continua 0.
- **Classe `OPacote`:**
  - Sem token, 401.
  - Com token, 200 e a ordem é `Hub.PACOTE`; os conteúdos são iguais aos do disco; `so_mede` vem certo.
  - O 11º pedido dá 429.
  - Com `Hub.PACOTE` remendado para incluir um arquivo inexistente, 503.
  - O passeio pelos imports de `agente/enviar.py` (só no nível do módulo, ignorando o import dentro de função) fica contido em `Hub.PACOTE`, e nada de `execucao.py`, `fila.py`, `barreira.py` nem `agente/executor.py` entra.
- **Classe `OArquivoDeConectar`:**
  - Usa `Hub.CONECTADOR_CMD` e `Hub.CONECTADOR` remendados para arquivos temporários (fixture própria; não depende do E1).
  - Sem sessão, 401.
  - Com sessão: os dois cabeçalhos de C7; nenhum `\n` sem `\r` antes; exatamente uma linha `#:DERVS-PYTHON`, depois de uma linha `exit /b`; `ALVO = "http://127.0.0.1:<porta>"`; ASCII.
  - A tabela `pareamento` não muda de tamanho.
  - Com um dos arquivos ausente, 503.
- **`test_rotas.py`:**
  - Nova classe `AsRotasDoConectarSimples`, que nomeia o acesso e o método das 8 rotas de C0.
  - `"/api/conectador" not in servir.ROTAS`.
- **`test_banco.py`:**
  - Migração: banco antigo com `maquina` sem as duas colunas → depois de `conectar()` as colunas existem, e `relatado_em` só é preenchido em máquina que tem linha em `projeto_conectado`.
  - `FILHAS_DE_USUARIO` contém as duas tabelas novas.
  - `normalizar_codigo_de_pedido` com `"k7m4 2qxp"` dá `"K7M4-2QXP"`, e com `"K7M0-2QXP"` dá `""`.

**Fazer:**
- C2 a C7, C10 (`so_mede` e `relatado_em`) e C14.
- Remover `Hub._conectador`, a rota `/api/conectador` e a classe `OConectadorNoServidorDeVerdade` (`test_servir.py:1759-1836`). Levar `test_o_servidor_nao_ganhou_atributo_conectador` para a classe nova.
- Remover `test_servir.py:3054-3055`.
- Criar `Hub.CONECTADOR_CMD = AQUI / "conectador.cmd"` e `Hub.PACOTE`.

**Verificação:** `python test_conectar_servidor.py`, `python test_servir.py`, `python test_rotas.py`, `python test_banco.py`, `python test_agente.py`, `python test_voz.py` e `python test_publicar.py`, todos verdes.

**Pronto quando:** os comandos acima estão verdes e uma busca por `Number(` não traz nada novo (não se aplica a Python, só registro).

**Depende de:** E2-1.

### E2-3. Mostrar no painel e projetos vistos
**Objetivo:** a chave esconde um projeto do painel daquela conta, e o esconderijo sobrevive a uma medição nova.

**Arquivos:** `servir.py`, `banco.py`, `test_conectar_servidor.py`, `test_banco.py`.

**Teste antes (classe `OProjetoOculto`):**
- Relatório com dois projetos e uma pendência em cada. `mostrar:false` tira o projeto de `projetos` e de `pendencias`, `ocultos == ["x"]`, e `grupos` não o cita.
- Um relatório novo **não** traz o projeto de volta. `mostrar:true` traz.
- `banco.montar_estado` continua contendo o projeto escondido (poda depois do motor).
- Projeto desconhecido ou de outra conta dá 404; corpo torto (`mostrar:"nao"`) dá 400; `X-Token` errado dá 403 `pagina_velha`; 61 pedidos dão 429.
- `/api/maquinas`:
  - antes do relatório: `relatado_em` nulo e `projetos_vistos` vazio;
  - depois: `relatado_em` preenchido, e `projetos_vistos[i]` com `{projeto, caminho, visto_em, oculto}`;
  - `oculto` acompanha a chave.

**Fazer:** C8, C9 e C10 (`projetos_vistos`).

**Verificação:** `python test_conectar_servidor.py`, `python test_banco.py`, `python test_servir.py` e `python test_desenvolver.py`, todos verdes.

**Pronto quando:** mover a poda para `_estado` deixa o caso do `montar_estado` vermelho (sabotar e voltar).

**Depende de:** E2-2.

### E2-4. Repositórios por conta do GitHub
**Objetivo:** cada conta do GitHub lista os repositórios e a chave dela.

**Arquivos:** `servir.py`, `banco.py`, `test_conectar_servidor.py`.

**Teste antes (classe `OGithubComRepositorios`):**
- Montagem: uma linha em `instalacao_github` com `conta_login="loja-da-ana"`, e um relatório com projeto de `remoto_slug="Loja-Da-Ana/site"` e outro de `"outra/x"`.
- `/api/github` traz em `instalacoes[0].repositorios` só o primeiro, com `medido` falso.
- `banco.gravar(..., "github", ...)` deixa `medido` verdadeiro.
- Esconder deixa `oculto` verdadeiro.
- O projeto de outra conta nunca aparece.
- Slug torto (`"a/b/c"`, número, `None`) é ignorado sem levantar.

**Fazer:** C11.

**Verificação:** `python test_conectar_servidor.py` e `python test_servir.py`, verdes.

**Pronto quando:** os dois comandos estão verdes.

**Depende de:** E2-3.

### E2-5. Medir o site sem gravar
**Objetivo:** conferir o site antes de guardar.

**Arquivos:** `servir.py`, `test_conectar_servidor.py`.

**Teste antes (classe `OMedirSemGravar`):**
- Com `coletar_github.mede_site` substituído por `mock`, a resposta é 200 com os campos de C12, e `endereco_producao` continua com a mesma contagem.
- URL `"loja"` dá 400 `forma`.
- `"http://10.0.0.1"` dá 400 `nao_publico`.
- Com `host_publico` substituído para devolver `False`, sai 400 `nao_publico` e `mede_site` não é chamado.
- Esgotar o balcão `medir` dá 429, e `/api/enderecos/guardar` continua sem 429 (balcões separados).
- `guardar` com `"medir": false` não chama `mede_site` e devolve `ok: null`.

**Fazer:** C12. A chamada é qualificada (`coletar_github.x`), nunca `from coletar_github import`.

**Verificação:** `python test_conectar_servidor.py`, `python test_servir.py`, `python test_servidores.py` e `python test_rotas.py`, verdes; depois o comando de regressão inteiro.

**Pronto quando:** a suíte inteira passa sem `FALHOU`.

**Depende de:** E2-4.

### E1-1. Arquivo `.cmd` e pareamento pelo navegador
**Objetivo:** dois cliques num arquivo que baixa o Python oficial, pede a pasta e pareia pelo navegador.

**Arquivos:** `conectador.cmd` (criar), `conectador.py`, `test_conectador.py`.

**Teste antes (reescrever `test_conectador.py`, mantendo as três leis do arquivo):**
- **Marcadores e texto:**
  - só biblioteca padrão e nenhum import do repositório; ASCII;
  - existe `# DERVS:ALVO`; não existe `# DERVS:CODIGO`; nenhuma linha começa com `#:DERVS-PYTHON`.
- **`escolher_pasta` em Windows** (com `os.name` substituído por `"nt"` e `subprocess.run` por dublê):
  - argv em lista, começando por `powershell.exe`, com `-NoProfile` e `-STA`;
  - a sugestão **não** aparece no argv e vai em `env["DERVS_SUGESTAO"]`;
  - devolve o stdout limpo;
  - `OSError` cai para tkinter e depois para o teclado.
- **Fechar sem escolher:** nenhuma rede, nenhum arquivo, nenhum `schtasks`, saída `SEM_PASTA`.
- **Fluxo com servidor dublê** (`http.server` numa thread, implementando C2, C3 e C6):
  - `webbrowser.open` (dublê) recebe `alvo + "/#/conectar?autorizar=" + codigo`;
  - 202 seguido de 200 grava o token;
  - 404 dá `SEM_PAREAMENTO` sem gravar nada;
  - 429 dobra o intervalo.
- **Molde `conectador.cmd`:**
  - ASCII;
  - contém `curl.exe`, `certutil -hashfile`, `tar.exe`, `%LOCALAPPDATA%\DERVS`, a URL `https://www.python.org/ftp/python/3.14.8/python-3.14.8-embed-amd64.zip` e um SHA-256 de 64 hexadecimais;
  - o zip é apagado no ramo de hash diferente;
  - tem `exit /b`;
  - não contém `-EncodedCommand`, `-enc`, `bitsadmin`, `Invoke-Expression` nem `iex`.
- **Extração:** o teste pega a linha `-c` do molde por regex, monta molde + `\r\n#:DERVS-PYTHON\r\n` + `conectador.py` em CRLF, roda a extração com `sys.executable` em arquivos temporários, e o resultado tem de passar em `ast.parse`.

**Fazer:**
- **Molde:** baixar o embutível uma vez, conferir com `certutil`, extrair com `tar` para `%CASA%\python`; sempre reextrair o Python para `%CASA%\conectador.py`; rodar `"%CASA%\python\python.exe" -I "%CASA%\conectador.py"`. Nenhum `%` dentro do código do `-c`.
- **`conectador.py`, nesta ordem:** alvo → pasta (PowerShell no Windows) → `POST /agente/pedir` → mostrar código e nome → abrir o navegador → `POST /agente/esperar` em laço até o prazo → `gravar()`.
- **Antes de commitar:** baixar o zip e conferir o SHA-256 de verdade.

**Verificação:** `python test_conectador.py` (verde).

**Pronto quando:** está verde, e trocar um byte do hash no molde faz o teste de formato continuar verde mas o caso de extração falhar não se aplica. **A prova real do hash é manual (F-2).**

**Depende de:** contratos C2, C3 e C7 (não do código do E2).

### E1-2. Pacote, `pythonw`, primeiro relato e reaproveitar o token
**Objetivo:** o PC passa a medir sozinho sem o repositório clonado, e rodar de novo não duplica.

**Arquivos:** `conectador.py`, `agente/enviar.py`, `test_conectador.py`.

**Teste antes:**
- **Pacote:** `GET /agente/pacote` (dublê) grava os arquivos em `DERVS_CASA` (variável de ambiente; o padrão é `%LOCALAPPDATA%\DERVS\programa`) e aceita só `caminho` que casa `^(agente/)?[a-z_]{1,40}\.py$`. `"../x.py"` ou `"agente/../../x.py"` recusa o pacote **inteiro**, não grava nada e sai `SEM_PACOTE = 5`.
- **Interpretador:** `pythonw.exe` ao lado de `sys.executable`, quando existe, é o escolhido para a tarefa; o plano B e as aspas continuam valendo.
- **Primeiro relato:** depois de agendar, `subprocess.run` (dublê) recebe `[<python do console>, <casa>/agente/enviar.py, "--alvo", alvo]` com timeout.
- **Reaproveitar:** com `agente.json` já tendo token para o alvo, o pacote dá 200 e `/agente/pedir` não é chamado. Com 401, pareia de novo. Com `so_mede: false`, não instala nem agenda e só acrescenta a raiz.
- **Pacote sem o braço:** copiar os 6 arquivos do pacote do disco para uma pasta temporária, sem `executor.py`. `python <tmp>/agente/enviar.py --help` sai com 0. Com `sys.modules["agente.executor"] = None` (`mock.patch.dict`), `fazer_a_tarefa` devolve `estado: "falha"` e sobe o desfecho por `_falar` (dublê).

**Fazer:**
- O que os testes acima pedem.
- Em `enviar.py`: `try: from agente import executor as _executor except ImportError:` vira um desfecho de falha "este computador so mede".
- No sucesso, a janela imprime "Pronto. Esta janela fecha em 10 segundos." e fecha; na falha, `pausa()`.

**Verificação:** `python test_conectador.py`, `python test_agente.py`, `python test_progresso_fio.py` e `python test_conectar_ponta_a_ponta.py`, todos verdes.

**Pronto quando:** os quatro passam.

**Depende de:** E1-1.

### E1-3. Imagem e roteiro de operação
**Objetivo:** produção leva o molde e o pacote, e nada do braço executor.

**Arquivos:** `Dockerfile`, `test_imagem.py`, `docs/operacao/conectar-uma-maquina.md`.

**Teste antes (`test_imagem.py`):**
- `PROIBIDOS` ganha `"agente/executor.py"`.
- Constante `PACOTE_DO_COMPUTADOR` igual a C6, com um caso que cobra cada item em `copiados()`.
- `"conectador.cmd"` entra em `test_as_paginas_e_os_assets_entram`.
- `"agente"` não pertence a `modulos_de_runtime()`.

**Fazer:**
- `COPY conectador.cmd /app/`, `COPY agente/__init__.py /app/agente/` e `COPY agente/enviar.py /app/agente/`, com comentário do motivo (lidos e servidos, nunca importados).
- Reescrever o roteiro de operação para o caminho do arquivo `.cmd`; a linha de comando fica como alternativa.

**Verificação:** `python test_imagem.py` (verde); o passo "barreira do vivo/" continua valendo (sem `COPY . .` e sem curinga).

**Pronto quando:** está verde.

**Depende de:** E1-2.

### E3-1. Faixa "Esta página ficou desatualizada"
**Objetivo:** qualquer botão recusado por página velha diz o que fazer.

**Arquivos:** `assets/painel.js`, `index.html`, `assets/painel.css`, `test_conectar_tela.py` (criar).

**Teste antes (`test_conectar_tela.py`, node com DOM de mentira, no molde de `test_voz_tela.py`; sem node, pula só esses casos):**
- `escrever()` com um `fetch` falso que devolve 403 `{"motivo":"pagina_velha"}`: a faixa aparece com `role="alert"`, o foco vai para "Recarregar", e um segundo 403 não cria outra faixa.
- 403 sem `motivo` não abre faixa.
- O `r` volta intacto: `r.status === 403` e `r.json()` ainda pode ser lido.
- Com a faixa aberta, `recado("x", true)` escreve "Não foi feito. Veja o aviso no alto da página."
- Sem node: a regex confirma que o literal `motivo === "pagina_velha"` está dentro de `escrever`.

**Fazer:**
- `escrever` vira `async`, com `r.clone().json()` só quando o status é 403.
- Criar `abrirFaixaPaginaVelha()`.
- Contêiner fixo no topo do `<main>` em `index.html`, sem `style=`.
- Classe `.faixa--pagina-velha` em `painel.css`: `position: sticky; top: 0`, `z-index` acima do `.freio` (50), filete de `--traco-forte` em `--acao`, nenhum `--estado-*`; em 360px, o botão ocupa a largura inteira e a faixa não passa de 7rem.
- Textos exatos da seção "Faixa de página desatualizada" do design.

**Verificação:** `python test_conectar_tela.py`, `python test_design.py` e `python test_menu.py`, verdes.

**Pronto quando:** sabotar o literal faz o teste ficar vermelho.

**Depende de:** C1.

### E3-2. Cartão "Este computador", bloco "Autorizar" e rota com parâmetros
**Objetivo:** um botão baixa o arquivo; a página de autorizar confere nome e código; a tela percebe sozinha.

**Arquivos:** `assets/painel.js`, `index.html`, `assets/painel.css`, `assets/cortina.js`, `test_conectar_tela.py`, `test_design.py`, `test_menu.py`, `test_voz_tela.py`.

**Teste antes:**
- `rota()` em `"#/conectar?autorizar=K7M4-2QXP"` dá a tela `conectar` e o parâmetro `autorizar = "K7M4-2QXP"`; `"#/projeto/x"` continua igual.
- `pintarAutorizar(p)` pinta cada estado de C4 ("esperando", 404, "conectado", erro de rede). O nome do computador entra por `textContent`. O botão só aparece com os dados.
- O link tem `href="/api/conectar.cmd"` e `download="conectar-dervs.cmd"`.
- `linhaDeComputador(m)` com `so_mede: true` **não** tem "Deixar consertar aqui" e tem a frase "Este computador só acompanha os projetos…".
- A espera dá sucesso quando um `relatado_em` passa a ser mais novo que o início da espera.
- `cortina.js` guarda em `sessionStorage` só código que casa o regex de C4.
- Continuam valendo: `test_menu` (`case "conectar"` com `tambem: ["computadores"]`, `carregarComputadores()` e `carregarVoz()`), a linha do comando de `painel.js:2401-2402` (presa por `test_conectar_ponta_a_ponta`) e `VALIDADE_GITHUB_S`.

**Fazer:**
- Seções "Tela A" e "Tela B" do design, com estes ajustes:
  - os passos 4 a 6 viram janela preta → pasta → navegador abre e você autoriza;
  - a frase de zero projetos sem caminho de pasta.
- Retirar `baixarConectador`.
- `porta()` passa a aceitar um caminho do tipo link (`{rotulo, href, download}`).
- "Prefiro colar um comando" vira um `<details>` fechado com o bloco atual: `#btn-gerar-numero`, `#comando-pareamento`, `#espera-pareamento`.
- Desenhos SVG inline em `<template>`, só com classes do `painel.css`. **Nada de `style=` nem `fill="var(…)"`**: a CSP descarta.
- "O que vai aparecer?" vem aberto na primeira visita, lembrado por `localStorage["dervs-conectar-visto"]` com `try/catch`.

**Verificação:** `python test_conectar_tela.py`, `python test_design.py`, `python test_menu.py`, `python test_voz_tela.py` e `python test_conectar_ponta_a_ponta.py`, verdes.

**Pronto quando:** os cinco passam.

**Depende de:** E3-1, C4, C5, C7 e C10.

### E3-3. Lista de projetos achados e a chave "Mostrar no painel"
**Objetivo:** esconder e mostrar um projeto por computador.

**Arquivos:** `assets/painel.js`, `assets/painel.css`, `test_conectar_tela.py`.

**Teste antes:**
- `linhaDeProjetoVisto(a)`: `input[type=checkbox][role=switch]` com `aria-label` "Mostrar no painel: <projeto>".
- Durante o pedido, a chave fica `disabled` e `aria-busy`.
- Na falha, a chave volta para onde estava e aparece a frase do design.
- O foco fica na chave.
- `oculto: true` pinta a linha em `--texto-suave` com "Escondido do painel".
- O nome da classe da chave existe dos dois lados, CSS e JS.

**Fazer:**
- Tela A, seção "A chave…", com caixa rolável a partir de 20 itens.
- **Decisão do plano (Lei 2):** no painel, quando `ESTADO.ocultos.length > 0`, uma linha `.mole` "N projeto(s) escondido(s) do painel. Ver em Conectar." com link. Sem ela, um projeto escondido e quebrado sumiria calado do resumo. O dono pode cortar.

**Verificação:** `python test_conectar_tela.py` e `python test_design.py`, verdes.

**Pronto quando:** os dois passam.

**Depende de:** E3-2 e C8.

### E3-4. Cartão GitHub sem botão de procurar
**Objetivo:** contas aparecem sozinhas, cada uma com os repositórios e a chave.

**Arquivos:** `assets/painel.js`, `test_github_tela.py`, `test_conectar_tela.py`.

**Teste antes:**
- **Reescrever `test_github_tela.py`:**
  - o texto "Procurar minhas contas" **não** existe;
  - `procurarContasDoGithub` é chamada uma vez por carga (flag) e quando há `?github=`;
  - um 429 da procura automática fica calado;
  - `linhaDeContaDoGithub(c)` mostra "pessoal" ou "organização", e "mede N repositórios · mediu há…" com `haQuanto`;
  - o link externo tem `rel="noopener noreferrer"`;
  - `linhaDeRepositorio(r)` reusa a chave de E3-3;
  - nenhum `innerHTML`, `Number(` nem `parseInt(`.

**Fazer:** Tela C do design. "Tentar de novo" só existe no estado de erro.

**Verificação:** `python test_github_tela.py` e `python test_conectar_tela.py`, verdes.

**Pronto quando:** os dois passam.

**Depende de:** E3-3 e C11.

### E3-5. Cartão "Seus sites"
**Objetivo:** colar o endereço, ver se responde e só então guardar.

**Arquivos:** `assets/painel.js`, `assets/painel.css`, `test_design.py`, `test_conectar_tela.py`.

**Teste antes:**
- `pintarResultadoDaMedicao(r)` pinta os quatro desfechos (ok true, ok false, ok null, 400 `nao_publico`) e o 400 `forma` liga `aria-invalid`.
- `erro` é traduzido assim:
  - `TimeoutError`/`timeout` → "não respondeu em 10 segundos";
  - nome com `SSL`/`Certificate` → certificado;
  - `codigo >= 500` → erro do lado dele;
  - `ConnectionRefusedError` → recusou;
  - resto → genérico.
- "Guardar" manda `medir:false`.
- Com 0 servidores, cria "Meus sites"; com 2 ou mais, exige escolha visível.
- Sugestões vêm de `p.github.sites` com `servidor_id === 0` e das sugestões por padrão já existentes, e nunca gravam.
- Atualizar `test_design.OCartaoDeConectarListaOsServidores` e `ASugestaoNaTelaPropoeEPara` para o desenho novo, mantendo as travas: nada pinta antes da leitura, sugestão "propõe e para", "Cadastrar servidor" fica nas opções avançadas.

**Fazer:** Tela E do design.

**Verificação:** `python test_conectar_tela.py`, `python test_design.py` e `python test_servidores.py`, verdes.

**Pronto quando:** os três passam.

**Depende de:** E3-4 e C12.

### E3-6. DERVS-VOZ num `<details>`, guarda de jargão e documentação
**Objetivo:** tela limpa, sem jargão, e documentação que não mente.

**Arquivos:** `index.html`, `assets/painel.js`, `test_voz_tela.py`, `test_conectar_tela.py`, `docs/A-APLICACAO.md`, `assets/CREDITOS.md`, `test_design.py`.

**Teste antes:**
- **Guarda de jargão em `test_conectar_tela.py`:** no texto visível da tela Conectar, que é o HTML de `#tela-conectar` e `#tela-computadores` menos o `<details>` "Prefiro colar um comando" e menos `#voz`, mais os textos entre os marcadores `/* === CONECTAR: início === */` e `/* === CONECTAR: fim === */` do `painel.js`, nenhuma destas palavras: `\bagente\b`, `\btoken\b`, `\bgit\b`, `linha de comando`, `instala[cç][aã]o`, `dashboard`, `loading`, `deploy`, `login`.
  - Prova por sabotagem: inserir "agente" num `textContent` tem de deixar o teste vermelho.
- **`test_voz_tela`:** o VOZ continua dentro de `#tela-computadores`, agora dentro de `<details>` com `<summary>` "Recados do DERVS-VOZ".
- **`test_design`:** `>Computadores<` continua existindo (título da seção), ou o teste é atualizado com motivo escrito. Continua valendo que nenhum arquivo novo entra em `assets/`.

**Fazer:**
- Tirar o parágrafo com "agente" (`index.html:220-224`).
- Atualizar `docs/A-APLICACAO.md` (~150-157 e o item de ~650 "A máquina sem o repositório clonado…").
- Uma linha nova em `CREDITOS.md`.

**Verificação:** `python test_conectar_tela.py`, `python test_voz_tela.py` e `python test_design.py`, verdes; depois o comando de regressão inteiro.

**Pronto quando:** a suíte inteira passa sem `FALHOU`.

**Depende de:** E3-5.

### F-1. O fio ponta a ponta, a CI e a documentação do repositório
**Objetivo:** provar o critério 1 e o casamento servidor↔tela; CI completa.

**Arquivos:** `test_conectar_fio.py` (criar), `.github/workflows/ci.yml`, `CLAUDE.md`, `README.md`, `docs/LINKS.md`, `docs/operacao/parear-o-voz.md`.

**Teste antes (`test_conectar_fio.py`, no espírito de `test_progresso_fio.py`, com `BaseServidorDeVerdade`):**

- **Classe `OArquivoBaixadoConectaNumaPastaVazia`:**
  1. `GET /api/conectar.cmd` com os arquivos **reais**; separar a parte Python em `#:DERVS-PYTHON` e gravá-la numa pasta temporária **sem** o repositório.
  2. Importá-la por `importlib` a partir do caminho.
  3. Dublês: `escolher_pasta` devolve uma pasta temporária com um projeto `git init`; a abertura do navegador captura a URL e, numa thread, chama `GET /api/pedido` e `POST /api/pedido/autorizar` com a sessão; `agendar` captura o argv e devolve `True`.
  4. Isolar `HOME`, `USERPROFILE`, `DERVS_AGENTE_ARQUIVO` e `DERVS_CASA`.
  5. O primeiro relato roda **de verdade** (`sys.executable` + o `enviar.py` do pacote).
  6. Esperado:
     - `main()` devolve 0;
     - `/api/maquinas` traz a máquina com `so_mede: true`, `relatado_em` preenchido e o projeto em `projetos_vistos`;
     - o `/TR` capturado aponta para dentro de `DERVS_CASA`, nunca para o repositório.
- **Classe `OQueATelaLeOServidorEntrega`:**
  - Para cada função de C13, `campos(var, funcao)` (o mesmo regex de `test_progresso_fio`, menos os nomes do DOM) tem de estar contido nas chaves reais de `/api/maquinas`, `/api/pedido`, `/api/github` (instalação gravada à mão mais relatório) e `/api/enderecos/medir` (com `mede_site` dublê).
  - O literal `pagina_velha` de `escrever` é igual a `servir.Hub.PAGINA_VELHA["motivo"]`, e um 403 real de `/api/projetos/mostrar` traz esse valor.
  - Toda rota citada no `painel.js` (C13) existe em `servir.ROTAS` com o método certo.
  - `servir.Hub.PACOTE == test_imagem.PACOTE_DO_COMPUTADOR`.
  - **Sabotar** cada lado (renomear `projetos_vistos` só no JS; renomear `motivo` só no servidor) tem de deixar vermelho. Desfazer editando de volta e commitar cedo.

**Fazer:**
- `ci.yml`: um passo por arquivo novo — `python test_conectar_servidor.py` ("O servidor do Conectar simples"), `python test_conectar_tela.py` ("A tela do Conectar simples") e `python test_conectar_fio.py` ("O fio do Conectar simples").
- `CLAUDE.md`: seção "Conectar simples (09/10/2026)" com as travas:
  - `PAGINA_VELHA` central;
  - `so_mede` com duas trancas;
  - `projeto_oculto` podado em `_dados` e nunca em `montar_estado`;
  - pedido de computador por hash, código e balcão `codigo_curto`;
  - `conectador.cmd` com LF no repositório e CRLF na saída, mais o marcador;
  - `Hub.PACOTE` espelhado em `test_imagem`;
  - repositórios do GitHub derivados do relatório;
  - nomes proibidos (`autorizacao`, `comando`).
- `README.md`: linhas de `conectador.py`, `conectador.cmd` e os testes novos.
- `docs/LINKS.md:115` e `docs/operacao/parear-o-voz.md:14`.
- **Coordenador:** avisar a janela do `dervs-voz` (token novo em `agente.json`) e pedir revisão de segurança, Python, design e conteúdo antes de mesclar.

**Verificação:** `python test_conectar_fio.py` (verde); o comando de regressão inteiro (sem `FALHOU`); o passo "Nenhum arquivo de teste ficou de fora", rodado no Bash (`for t in test_*.py; do grep -q "python $t" .github/workflows/ci.yml || echo FALTOU $t; done`), não imprime nada.

**Pronto quando:** tudo isso verde, e só então abrir o PR.

**Depende de:** E1-3, E2-5 e E3-6, já mesclados nessa ordem.

### F-2. Conferência clicando e no ar (manual; não é código)
**Objetivo:** fechar o que nenhum teste prova.

**Arquivos:** nenhum além de `docs/esteira/conectar-simples/verificacao.md`, escrito na fase do cronista.

**Fazer:**
- **No localhost (porta 4790, `DERVS_AMBIENTE=local`, servidor reiniciado):**
  - baixar o `.cmd` e rodar num Windows;
  - conferir o hash do embutível;
  - pasta pelo PowerShell; bloco Autorizar; cartão "Conectado — achei N" em menos de 15 s depois do primeiro relato;
  - chave esconde e sobrevive a um relatório;
  - conta do GitHub aparece sem botão;
  - site conferido antes de guardar;
  - faixa com duas abas abertas e um login novo.
- **Depois de publicar (mão do dono):**
  - aviso do Chrome no download de dervs.com.br;
  - diálogo do Windows;
  - Defender;
  - o computador já pareado continua medindo, as duas contas do GitHub continuam ligadas, o site cadastrado continua medido;
  - `python.exe agente\enviar.py --help` com o Python 3.14.8 embutível.

**Verificação:** cada item anotado com o que se viu.

**Depende de:** F-1, mesclado e publicado.

---

- **Paralelizável:** E1 (E1-1 → E1-3), E2 (E2-1 → E2-5) e E3 (E3-1 → E3-6) rodam ao mesmo tempo, sem nenhum arquivo em comum. Os contratos C0 a C14 são a única dependência entre eles. Dentro de cada executor as etapas são sequenciais, na ordem que destrava valor: 403 → arquivo → mostrar → GitHub → site.
- **Sequencial obrigatório:**
  - mesclagem E2 → E1 → E3, porque o E1 tira o marcador `CODIGO` de que a rota antiga dependia, e o E2 remove essa rota;
  - F-1 depois dos três (dono único de `ci.yml`, `CLAUDE.md` e do fio, que precisa dos dois lados);
  - F-2 depois de publicar.
- **O que eu não consegui confirmar:**
  - o SHA-256 e a versão 3.14.8 do embutível (vêm do spec, sem acesso à web aqui);
  - se `coletar.medir()` roda em Python 3.14 (a CI é 3.12);
  - o aviso do Chrome e a reação do Defender ao `.cmd` servido de verdade;
  - se `certutil -hashfile` imprime o hash sem espaços em toda build do Windows 10 a partir da 1803;
  - se algum teste existente faz `assertEqual` do dicionário inteiro de `/api/maquinas` ou `/api/dados` (vi só quem lê: `test_agente.py`, `test_voz.py`, `test_rotas.py`, `test_conectar_ponta_a_ponta.py`; o E2 roda todos);
  - o conteúdo exato de `test_design` de 725 a 845 (classes de `.computadores`) e de 1052 a 1280 (cartão de servidores), que o E3 vai ter de ajustar.

**Visto fora de escopo:** `painel.css` usa `--e5` (sem fallback), `--r2` e `--fundo-fraco`, que não existem em `dervs.css`. Há também `style=` inline em `index.html` (por exemplo `:196`, `:235`), que a CSP descarta.
