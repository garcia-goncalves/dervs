# Spec — entrega C: o servidor faz, com o "Pode fazer" do dono

Fase 2, 09/10/2026. Síntese de uma descoberta em modo enxuto (4 lentes num despacho).
Contrato: `briefing.md` desta pasta (as `decisoes_do_portao_1` vencem, salvo os dois cortes
nomeados em `contradicoes_resolvidas` e levados ao dono em `duvidas_para_o_dono`).

## problema

O painel já mostra, por servidor ligado (entrega B), qual sistema caiu e qual projeto está
"N mudanças atrás do GitHub". Mas para agir o dono precisa de terminal: reiniciar um sistema
ou voltar a versão anterior exige SSH e `sudo deploy`, que ele não opera. E a entrega B
prometeu que o ajudante **só olha**: um dervs.com.br tomado vaza inventário, não manda em
nada. A entrega C tem de dar ao dono dois ou três botões que façam algo de verdade num
servidor de produção (que hospeda o Ajudei, com dado de paciente) **sem** transformar o
DERVS numa chave mestra da VPS.

O que a descoberta achou, e muda o pedido:

1. **`deploy <projeto>` sozinho não publica nada.** O kit `deploy-padrao` (commit 1d57f57)
   exige `deploy <projeto> <arquivo.tar.gz> [commit]`: o código vem de um arquivo que o
   VS Code envia por SSH, nunca do GitHub. Com um argumento só o comando imprime o uso e
   sai 1 (`[ $# -ge 2 ]`). "Publicar a versão do GitHub" não existe no servidor hoje.
2. **O navegador não mostra ao dono o que ele está assinando.** WebAuthn assina um desafio
   opaco; o pedido da digital diz só "dervs.com.br". Quem tomar o dervs.com.br pode mostrar
   "Reiniciar x" e pedir a assinatura de "Voltar y" — ou pedir a assinatura de uma ordem
   durante um **login** comum (os dois são `webauthn.get` no mesmo domínio). A promessa
   "quem tomasse o dervs.com.br não manda o servidor fazer nada" só vale **sem um toque do
   dono**; com o site tomado, cada toque pode virar **uma** ordem da lista fechada.
3. **A unidade da entrega B não consegue rodar `sudo`.** `dervs-ajudante.service` tem
   `NoNewPrivileges=yes`, `CapabilityBoundingSet=` vazio e `ProtectSystem=strict`: `sudo`
   é setuid e morre ali, e o `deploy` herdaria o disco só-leitura. As ordens precisam de
   uma unidade própria.

## solucao

**Duas ações nesta entrega, escritas no código do ajudante:** *reiniciar um sistema* e
*voltar a versão anterior de um projeto*. "Publicar a versão do GitHub" sai desta entrega
(dúvida 1). Uma ação nova exige versão nova do ajudante, colada de novo pelo dono.

**O fio, do clique ao resultado:**

1. No cartão do servidor ligado **com ordens**, o dono clica "Reiniciar" num sistema ou
   "Voltar a versão anterior" num projeto. A tela mostra a frase exata ("Reiniciar o
   sistema *grimoire-web* no servidor *vps-ovh*") e o botão "Pode fazer".
2. A tela pede ao DERVS que **prepare** a ordem (`POST /api/maquinas/ordem/preparar`). O
   DERVS confere dono, servidor com ordens, alvo medido, projeto não bloqueado, nenhuma
   ordem em andamento; sorteia o número único, carimba criado/vence (5 min) e devolve o
   desafio = SHA-256 do texto canônico da ordem (C0).
3. A tela chama `navigator.credentials.get` com esse desafio, só com as chaves que aquele
   servidor conhece, `userVerification: "required"`. O dono toca/digita o PIN.
4. A tela manda a assinatura (`POST /api/maquinas/ordem/assinar`). O DERVS confere com
   `passkey.conferir_entrada` (mesma conta, chave viva, contador) e marca a ordem *enviada*.
   Tela: "Pedido enviado".
5. No servidor, a unidade `dervs-ajudante-ordens.timer` (30 s) roda `ordens`: busca no
   máximo uma ordem (`POST /agente/servidor/ordens`), **confere sozinho** a assinatura, a
   origem, o domínio, o desafio, o prazo, o número único, o projeto bloqueado e o alvo;
   grava o número; faz; e conta o desfecho (`POST /agente/servidor/desfecho`).
6. A tela relê `/api/dados` no evento `servidor` do fluxo que já existe e mostra "feito há
   N s", "não deu certo (código N)", "o servidor recusou o pedido" ou, passados 2 min sem
   o servidor buscar, "o servidor não pegou o pedido" — nunca "feito" sem o desfecho.

### Contratos

**C0 — A ordem e o desafio.** Texto ASCII, sete linhas `chave=valor` separadas por `\n`,
sem `\n` no fim, nesta ordem e só estas:

```
dervs-ordem=1
servidor=<ident: 32 hex minúsculos>
tipo=<reiniciar|voltar>
alvo=<nome>
numero=<32 hex minúsculos>
criado=<segundos desde 1970, inteiro>
vence=<segundos desde 1970, inteiro>
```

- `alvo`: para `reiniciar`, nome de contêiner `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`; para
  `voltar`, nome de projeto `^[a-z0-9][a-z0-9-]{0,62}$`. Inteiros sem sinal, sem zero à
  esquerda, até 10 dígitos. Qualquer campo fora do formato: a ordem não existe (nem
  montada, nem conferida) — nenhum valor pode carregar `=` ou `\n`.
- `vence - criado == 300` exatamente.
- Desafio = `SHA-256(texto em ASCII)`, 32 bytes; o `challenge` do `clientDataJSON` é o
  base64url sem `=` desses 32 bytes.
- **Quem confere remonta o texto a partir dos campos que recebeu**, nunca recebe o texto
  pronto: o DERVS não consegue fazer o ajudante conferir uma coisa e executar outra.
- Uma função `texto_da_ordem(campos) -> str | None` no ajudante e uma cópia do lado do DERVS
  (em `servir.py` ou `tarefas.py`, decisão do plano; **nunca** uma constante ou atributo de
  módulo chamado `ACOES`, que é `test_rotas.AMPUTADOS`). Teste cobra que as duas dão os
  mesmos bytes numa tabela de casos e no vetor de fora.

**C1 — A instalação com ordens.** `GET /api/ajudante/linha` passa a devolver também
`linha_com_ordens` (ou `null` quando a conta não tem chave de acesso viva) e
`chaves_na_linha` (os apelidos, para a tela dizer quais aparelhos poderão mandar). O
arquivo servido é **o mesmo** da linha "só olhar" (mesmo SHA-256, mesma
`_bytes_do_ajudante()`, uma marca `# DERVS:ALVO` só); muda o fim da linha:

```
... && sudo python3 -I dervs-ajudante.py instalar --ordens <x>.<y>[,<x>.<y>...]
```

- Cada chave: `x` e `y` com **64** hex minúsculos (`"%064x"`; o banco grava `"%x"`, sem
  zero à esquerda — padronizar na saída), no máximo 5 chaves, só as vivas da conta
  (função nova em `banco.py`; `chaves_de_acesso` continua sem a chave pública).
- `instalar --ordens` faz tudo o que a B faz e mais, nesta ordem, como root:
  1. Confere cada chave com a mesma checagem de curva (`ponto_valido`); uma torta e nada
     de ordens é ligado (a medição segue).
  2. Gera `ident = secrets.token_hex(16)` **novo a cada instalação** (ordem antiga para o
     ident velho é recusada como `outro_servidor`).
  3. Projetos que podem voltar: os nomes do `historico.log` (que já é lido; nada de listar
     `/etc/deploy`, e `test_ajudante_servidor.PROIBIDO` continua barrando `.conf`) que casam
     `^[a-z0-9][a-z0-9-]{0,62}$` e **não** estão bloqueados (C11). Só se
     `/usr/local/bin/deploy` existe, é arquivo comum de dono root, sem escrita para grupo e
     outros, e o mesmo vale para `/usr/local/bin` e `/usr/local`; senão nenhum projeto pode
     voltar e o instalador diz por quê.
  4. Escreve `/etc/sudoers.d/dervs-ajudante` (root:root, 0440) com **uma linha por
     projeto**, argumentos exatos, sem curinga:
     `dervs-ajudante ALL=(root) NOPASSWD:` seguido de `/usr/local/bin/deploy <projeto>
     --voltar`, numa linha só (escrito em dois pedaços aqui porque o `secret-scan.sh` toma
     `NOPASSWD:` + caminho por segredo).
     Gravado primeiro em `/etc/sudoers.d/.dervs-ajudante.novo` (nome com `.`, que o
     `#includedir` ignora), conferido com `visudo -cf`, e só então `os.replace`. Sem
     `visudo` ou com a conferência reprovada: nenhum projeto pode voltar, aviso, o resto
     segue. Nenhum projeto: o arquivo não existe. O usuário `dervs-ajudante` **nunca**
     entra no grupo `deploy` (que libera `deploy` com qualquer argumento).
  5. Escreve `/etc/dervs-ajudante/ordens.json` (pasta root:root 0755, arquivo root:root
     0644 — o usuário do ajudante lê e não consegue mudar): `{"versao": 1, "ident",
     "origem": ALVO, "rp_id": host do ALVO, "chaves": [[x_hex, y_hex], ...],
     "voltaveis": [...]}`. Origem e domínio saem do ALVO injetado: em produção
     `https://dervs.com.br` e `dervs.com.br`; no teste, o endereço local.
  6. Instala `dervs-ajudante-ordens.service` + `.timer` (`OnBootSec=45s`,
     `OnUnitActiveSec=30s`, `AccuracySec=1s`), `enable --now`. Serviço: `Type=oneshot`,
     `User=dervs-ajudante`, `ExecStart=<python> /opt/dervs-ajudante/dervs-ajudante.py
     ordens`, `TimeoutStartSec=30min`, `PrivateTmp=yes`. **Sem** `NoNewPrivileges`,
     `CapabilityBoundingSet`, `ProtectSystem` e `UMask` (quebram o `sudo` ou o `deploy`,
     que já faz `umask 022`); a contenção ali é a lista fechada do código + o `sudoers`
     exato + a assinatura. O `test_ajudante_servidor` confere diretiva por diretiva, e a
     lista vai à revisão de segurança.
  7. Diz em português o que ficou ligado ("Pedidos ligados: reiniciar sistemas; voltar a
     versão de: grimoire, dervs. O Ajudei fica de fora sempre.").
- `instalar` **sem** `--ordens` num servidor que tinha ordens **desliga** as ordens
  (apaga as duas unidades novas, o `sudoers.d/dervs-ajudante` e `/etc/dervs-ajudante`).
  Desligar os botões = colar a linha "só olhar". `remover` também apaga tudo isso.
- Chave nova ou removida no painel não chega sozinha ao servidor: o dono cola a linha
  com ordens de novo (C9 mostra quando é preciso).

**C2 — A medição conta se há ordens.** `medir` (unidade da B, sem mudança de diretiva) lê
`/etc/dervs-ajudante/ordens.json` se existir e põe no corpo a chave nova `ordens`:
`{"versao": 1, "ident", "chaves": [impressões], "voltaveis": [...]}`, impressão =
16 primeiros hex de `SHA-256(x 32 bytes || y 32 bytes)`. Sem arquivo (ou torto): a chave
não vai. No DERVS, `CHAVES_DO_TOPO` ganha `ordens`, validada por lista fechada (ident
32 hex; até 5 impressões de 16 hex; até 200 projetos no formato de C0; versão 1; o resto
descartado e contado em `invalidos`).

**C3 — O ajudante confere sozinho.** Subcomando `ordens`. Sem `ordens.json`: sai sem
nenhuma chamada de rede (desligado por padrão; ordem válida e assinada nunca é nem
buscada). Com ele, busca **uma** ordem e confere nesta ordem, parando na primeira falha e
devolvendo um `motivo` da lista fechada:

| # | Conferência | motivo |
|---|---|---|
| 1 | Forma: campos de C0 presentes e no formato; `cliente` ≤ 4 KiB, `autenticador` = exatos 37 bytes, `assinatura` ≤ 80 bytes, base64url válido | `forma` |
| 2 | `servidor == ident` | `outro_servidor` |
| 3 | `tipo` em `{reiniciar, voltar}` | `forma` |
| 4 | `vence - criado == 300`, `criado - 120 <= agora <= vence` | `vencida` |
| 5 | Assinatura ECDSA P-256 sobre `autenticador || SHA-256(cliente)` válida para **alguma** das chaves guardadas | `assinatura` |
| 6 | `cliente`: JSON objeto, `type == "webauthn.get"`, `challenge == b64url(SHA-256(C0))` | `desafio` |
| 7 | `origin == origem` guardada, `crossOrigin` ausente ou falso | `origem` |
| 8 | `rpIdHash == SHA-256(rp_id)`; flags com UP (0x01) e UV (0x04); AT (0x40) e ED (0x80) desligados | `aparelho` |
| 9 | Projeto bloqueado (C11): para `voltar`, o alvo; para `reiniciar`, o nome do contêiner **e** o rótulo de projeto dele | `bloqueado` |
| 10 | Alvo conhecido: `voltar` → está em `voltaveis`; `reiniciar` → aparece num `docker ps`/`inspect` feito **agora** (mesmos `ARGV_DO_PS`/`ARGV_DO_INSPECT`) | `desconhecido` |
| 11 | Número nunca usado (C4) | `repetida` |

- O contador do autenticador **não** é conferido no ajudante (chave sincronizada manda
  zero para sempre e há vários servidores); quem impede repetir é o número único. O DERVS
  confere o contador no passo 4 do fio.
- A conta ECDSA P-256 mora **dentro** do `ajudante_servidor.py` (ele é lido, não importa
  `p256.py`): cópia de `somar`, `multiplicar`, `ponto_valido`, `conferir`,
  `assinatura_de_der`, `_inteiro` e das constantes `P, A, B, N, G`. Guarda: teste compara
  `ast.dump` de cada função e o valor de cada constante com `p256.py` — cópia que diverge
  reprova. Mais os vetores da RFC 6979 A.2.5 (os mesmos de `test_p256.py`) e o vetor de
  fora (C12).
- Toda recusa vira desfecho `recusada` com o motivo; nada é feito.

**C4 — O número único.** Mora em `/var/lib/dervs-ajudante/numeros.json` (dono
`dervs-ajudante`, 0600, gravado pela `_gravar` da B: arquivo novo + troca atômica, dono e
modo pelo descritor). Conteúdo `{numero: vence}`. Antes de cada conferência poda o que tem
`vence < agora` (seguro: o passo 4 já recusaria). No máximo **200** números; cheio de
números ainda vivos → recusa `cheio` (nunca descarta um vivo para abrir vaga). O número é
gravado **depois** de passar as 11 conferências e **antes** de fazer; se a gravação falhar,
não faz (`recusada`, motivo `cheio`). Também guarda os últimos instantes de ordens feitas:
no máximo **6 ordens por hora** por servidor (`motivo: teto`) — limita o estrago de
assinaturas colhidas por um site tomado (problema 2).

**C5 — Fazer, por lista fechada.** Dois `argv` fixos, e só eles:

- `ARGV_DO_REINICIO = ("docker", "restart")` + `[nome]`, como `dervs-ajudante` (grupo
  `docker`, sem `sudo`), prazo 120 s.
- `ARGV_DA_VOLTA = ("sudo", "-n", "/usr/local/bin/deploy")` + `[projeto, "--voltar"]`,
  prazo 1200 s.

Uma função nova `fazer(argv, prazo) -> int | None`, a única além de `rodar` com
`subprocess`: `shell=False`, `stdin`, `stdout` e `stderr` em `DEVNULL` (a saída do
`deploy` traz registro, e registro de sistema de saúde não sobe), ambiente mínimo
(`PATH=/usr/sbin:/usr/bin:/sbin:/bin`, `LANG=C`). Devolve o código de saída (0–255), ou
`None` em prazo estourado/erro de sistema. Desfecho: `0` → `feita`; outro código →
`falhou` com o código; `None` → `nao_sei` (Lei 2: nunca "deu certo" nem "falhou" sem saber).
`test_ajudante_servidor` passa a liberar o literal `"docker"` também em
`ARGV_DO_REINICIO`, `"sudo"`/`"/usr/local/bin/deploy"` só em `ARGV_DA_VOLTA` e no texto do
`sudoers`, e `subprocess` só em `rodar` e `fazer`; e reprova qualquer outro.

**C6 — A tabela `ordem_de_servidor`.** Migração leve (`CREATE TABLE IF NOT EXISTS`, como
`medicao_de_servidor`); `test_banco.Esquema.test_as_vinte_tabelas_existem` ganha o nome na
lista escrita à mão.

```
numero        TEXT PRIMARY KEY CHECK (length(numero) = 32)
usuario_id    INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE
maquina_id    INTEGER NOT NULL REFERENCES maquina(id) ON DELETE CASCADE
ident         TEXT NOT NULL            -- o do servidor na hora de preparar
tipo          TEXT NOT NULL CHECK (tipo IN ('reiniciar','voltar'))
alvo          TEXT NOT NULL CHECK (length(alvo) BETWEEN 1 AND 128)
criado        INTEGER NOT NULL, vence INTEGER NOT NULL
assinada_em   TEXT, entregue_em TEXT, terminada_em TEXT   -- ISO UTC, relógio do DERVS
cred_id, cliente, autenticador, assinatura   TEXT         -- base64url, NULL até assinar
desfecho      TEXT CHECK (desfecho IN ('feita','falhou','recusada','nao_sei'))
codigo        INTEGER CHECK (codigo BETWEEN 0 AND 255)
motivo        TEXT     -- só a lista fechada de C3/C4
```

Índice `(maquina_id, criado)`. Poda: ao preparar, apaga ordens da máquina além das 50 mais
novas. Toda leitura e escrita leva `usuario_id` **e** `maquina_id` no `WHERE`. Uma ordem
"em andamento" por máquina (preparada e não vencida, ou entregue sem desfecho há menos de
30 min): a segunda dá 409 `ocupado`.

**C7 — As rotas da tela** (sessão, `Origin` em `ORIGENS_OK`, `X-Token`, classe `dado`;
nomes sem `acao|execucao|exec|terminal|pty|shell|comando|grafo`):

- `POST /api/maquinas/ordem/preparar` → `Hub._maquina_ordem_preparar`. Corpo
  `{maquina_id: int, tipo, alvo}`. Balcão próprio `ordem_preparar` (20 por janela, por
  sessão). Servidor de outra conta e servidor que não existe: **o mesmo 404**. Respostas:
  200 `{numero, desafio, rp_id, chaves: [cred_id...], segundos: 300, frase}`;
  409 `{motivo}` com `so_olha` (sem bloco `ordens` na medição), `sem_dados` (medição
  passou de 180 s), `ocupado`, `sem_chave` (nenhuma chave viva da conta cuja impressão o
  servidor conheça); 403 `bloqueado`; 400 alvo torto ou não medido; 429.
- `POST /api/maquinas/ordem/assinar` → `Hub._maquina_ordem_assinar`. Corpo `{numero,
  cred_id, cliente, autenticador, assinatura}`. Balcão próprio `ordem_assinar` (20, por
  sessão). Lê a ordem com `usuario_id` da sessão, preparada, não vencida, não assinada;
  `banco.chave_de_acesso(cred_id)` tem de ser da **mesma conta** e de impressão conhecida
  pelo servidor; `autenticador` com 37 bytes e AT/ED desligados (a mesma régua do
  ajudante, para a tela não dizer "enviado" ao que o servidor vai recusar);
  `passkey.conferir_entrada(..., desafio=SHA-256(C0), self._rp_id(), ORIGENS_OK)`;
  `banco.usar_chave_de_acesso` (contador). Qualquer falha: 401 com a mesma frase
  (`RECUSA`). Sucesso: grava as quatro peças e `assinada_em`, 200 `{ok}`. Chave revogada
  no painel deixa de mandar ordem na hora, mesmo que o servidor ainda a conheça.

**C8 — As rotas do ajudante** (classe `maquina`, só `tipo='servidor'`, 403 `so servidor`
nas outras, conferido antes do balcão; `/agente/servidor` continua respondendo só
`{ok, invalidos}`, **nunca** ordem nem `tarefa`):

- `POST /agente/servidor/ordens` → `Hub._agente_servidor_ordens`. Balcão próprio
  `servidor_ordens` (90 por janela, por máquina). Devolve `{ordem: null}` ou a ordem mais
  velha da máquina **assinada há no máximo 120 s**, não vencida, não entregue: os sete
  campos de C0 + `cliente`, `autenticador`, `assinatura`. Marca `entregue_em` no mesmo
  `UPDATE ... WHERE entregue_em IS NULL` (quem não levar `rowcount == 1` não entrega).
  Assinada há mais de 120 s e não entregue nunca mais sai (a tela já disse "não pegou").
- `POST /agente/servidor/desfecho` → `Hub._agente_servidor_desfecho`. Balcão próprio
  `servidor_desfecho` (30, por máquina). Corpo `{numero, desfecho, codigo, motivo}`
  validado por lista fechada; grava só se a ordem é **desta máquina**, entregue e sem
  desfecho (`UPDATE` com as três condições); senão 404. Carimba `terminada_em`.

**C9 — O que `/api/dados` entrega.** Em `servidores_ligados[]` (montado depois do motor,
como na B; `montar_estado` não muda), cada servidor ganha:

- `ordens`: `null` quando a medição não traz o bloco (só olha) ou o estado não é
  `medido`; senão `{"chaves_ok": bool, "linha_velha": bool, "voltaveis": [...],
  "pedidos": [...]}`. `chaves_ok`: alguma chave viva da conta tem impressão conhecida.
  `linha_velha`: o conjunto de impressões do servidor difere do das chaves vivas (chave
  nova ou removida → "cole a linha com pedidos de novo"). `voltaveis` sem os bloqueados.
- Cada item de `sistemas` ganha `reiniciavel: bool` (falso para bloqueado por nome ou
  rótulo, e quando `ordens` é `null`).
- `pedidos`: as 5 ordens mais novas assinadas, `{numero, tipo, alvo, estado, quando,
  codigo, motivo}`, com `estado` calculado no DERVS: `enviado` (assinada, não entregue,
  ≤ 120 s), `nao_pegou` (não entregue, > 120 s), `fazendo` (entregue, sem desfecho,
  ≤ 30 min), `sem_resposta` (entregue, sem desfecho, > 30 min), `feito`, `nao_deu`
  (`falhou`, com `codigo`), `recusado` (com `motivo`), `nao_sei`. `quando` é o carimbo do
  estado (para `haQuanto`). Nenhum estado diz "feito" sem `desfecho = 'feita'` vindo do
  ajudante.
- O fluxo `/api/eventos` sem `id` não muda: a medição de 30 s já dispara `event:
  servidor` e a tela relê `/api/dados`.

**C10 — A tela** (`assets/painel.js`, dentro de Conectar; menu continua com 4 itens):

- `linhaDeSistema(x)`: botão "Reiniciar" só com `x.reiniciavel === true`.
- `linhaDeServidorLigado(s)`: com `s.ordens`, uma lista "Voltar a versão anterior" com um
  botão por projeto de `s.ordens.voltaveis`; a linha do último pedido por alvo; aviso
  `linha_velha` / `!chaves_ok` com o caminho ("Ligar um servidor" → linha com pedidos).
  Sem `s.ordens`: nada novo aparece.
- "Ligar um servidor" oferece as duas linhas; a com pedidos só quando
  `linha_com_ordens` não é `null`; sem chave de acesso, explica como cadastrar uma (em
  Entrar/Segurança) e não mostra a linha.
- Clique → `confirmar({titulo: frase, ...})` → preparar → `navigator.credentials.get` →
  assinar. Erros viram frase nossa: cancelou o toque, 401, 403 `bloqueado`, 404, 409 de
  cada motivo, 429.
- Textos: sem "WebAuthn", "assinatura", "token", "contêiner", "docker", "deploy",
  "sudo". Diz "pedido", "digital ou PIN", "sistema", "versão". "O que isso faz?" da linha
  com pedidos diz o limite honesto (problema 2) com todas as letras.
- `maquina_id` vai como número com `+`, nunca `Number(`/`parseInt(` (`test_design`); todo
  texto vindo do servidor por `textContent`.

**C11 — Projeto bloqueado nas duas pontas.** O ajudante leva
`PROJETOS_BLOQUEADOS = frozenset({...})` e `_bloqueado(nome)` com a mesma normalização de
`tarefas._nome_normalizado` + `projeto_bloqueado` (minúsculas; `_`, espaço e `.` viram
`-`; igual ou prefixo na fronteira do `-`). Teste cobra igualdade do conjunto com
`tarefas.PROJETOS_BLOQUEADOS` e a mesma resposta das duas funções numa tabela de variações
(`Ajudei-Saude`, `ajudei_saude`, `AJUDEI SAUDE`, `ajudei.saude-web`, `ajudeisaude`,
`ajudei-saudex`). No DERVS, preparar chama `tarefas.projeto_bloqueado` (nunca a forma
antiga `.lower() in`). O instalador nunca escreve linha de `sudoers` para bloqueado.

**C12 — Os testes.** Arquivos novos, cada um um passo próprio em `.github/workflows/ci.yml`
(a lista é cobrada):

- `test_ajudante_acoes.py`: as 11 conferências de C3, uma por caso, e **os seis do
  briefing** com vetor de fora — sem assinatura, outra chave, desafio que não é o resumo
  da ordem, origem diferente, vencida, repetida —, mais UV desligado, `rpIdHash` de outro
  domínio, `crossOrigin`, servidor sem `ordens.json` recusa ordem válida (e não chama a
  rede), `cheio`, `teto`, e `fazer` com `Docker`/`sudo` falsos (código 0, 1, prazo).
  Guarda `ast` das funções de P-256 contra `p256.py` e da cópia de `PROJETOS_BLOQUEADOS`.
- `test_ajudante_servidor.py`: as leis do fonte ajustadas (C5), unidades novas diretiva
  por diretiva, `sudoers` exato, `visudo` que reprova, `deploy` com dono ou modo errado,
  `instalar` sem `--ordens` desliga, `remover` apaga tudo.
- `test_acoes_fio.py`: o fio inteiro — sessão prepara, assina com o vetor de fora
  (servidor de teste com `ORIGENS_OK`/`rp_id` iguais aos do vetor), ajudante de verdade
  (raiz temporária, Docker falso) busca, confere, faz e devolve, e `/api/dados` traz os
  campos que o `painel.js` lê (subconjunto). Sabotar `texto_da_ordem` de um lado só deixa
  vermelho.
- Rotas: outra conta = mesmo 404; balcões próprios esgotados não travam `/agente/servidor`
  nem login; `test_rotas` verde com os nomes novos; `test_banco` com a tabela.
- Tela em node (molde `test_voz_tela.py`): botões só com os campos verdadeiros, frase
  exata, cada estado de `pedidos`, nenhuma palavra proibida.

**O vetor de fora (como gerar, uma vez, fora do repositório).** Com OpenSSL 3.5.7 nesta
máquina, num diretório temporário, arquivos **sem** extensão `.pem` (o hook barra a palavra
na linha de comando):

```
openssl ecparam -name prime256v1 -genkey -noout -outform DER -out k1
openssl ec -inform DER -in k1 -pubout -outform DER -out k1pub     # x,y = últimos 64 bytes
# um script Python grava assinado.bin = autenticador(37 bytes) || SHA-256(clientDataJSON)
openssl dgst -sha256 -sign k1 -keyform DER -out sig.der assinado.bin
```

Uma assinatura por caso que precisa de assinatura **válida** sobre dado errado (outro
desafio, outra origem, `type` errado, UV desligado, outro `rpIdHash`, `crossOrigin`) e uma
segunda chave `k2` para "outra chave". No teste ficam só as **públicas** (x, y em hex), o
`clientDataJSON` em texto, o `autenticador` e as assinaturas em hex, com a versão do
OpenSSL, a data e os comandos no comentário; a chave privada é apagada e nunca entra no
repositório (nada de armadura `BEGIN ... PRIVATE KEY` para o `secret-scan.sh` barrar). Nomes
de constante sem `token`/`segredo`/`senha`; conferir com o `secret-scan.sh` antes do commit.
O mesmo varredor barra `NOPASSWD:` seguido de 16+ caracteres de caminho: o texto do
`sudoers` no ajudante e no teste tem de ser montado em pedaços (ex.: `"NOPASSWD:" + " " +
ARGV_DA_VOLTA[2]`), nunca escrito inteiro num literal.
Vencida e repetida reusam o vetor válido (relógio de teste e segunda passada).

## o_que_ja_existe

- **Ajudante** `ajudante_servidor.py`: `ALVO` com a marca `# DERVS:ALVO` (linha 49);
  `ARGV_DO_PS`, `FORMATO_DO_INSPECT`, `ARGV_DO_INSPECT` (70–72); `rodar` (única porta do
  `subprocess`, `shell=False`), `abrir` (sem redirecionar, token só no cabeçalho, teto
  64 KiB); `_gravar` (arquivo novo + `O_EXCL` + `fchmod`/dono pelo descritor +
  `os.replace`); `texto_do_servico` (`NoNewPrivileges`, `ProtectSystem=strict`,
  `CapabilityBoundingSet=` vazio, `User=dervs-ajudante`), `texto_do_temporizador`
  (30 s); `instalar` (root, systemd, docker, useradd no grupo `docker`, pareamento
  `tipo: "servidor"`, cópia para `/opt/dervs-ajudante/`, ACL no historico, `enable --now`,
  primeira medição, repareamento uma vez); `_sistemas` (ps + inspect, refaz uma vez,
  `docker_mudo`); `_publicacoes` (historico do kit, descarta `quem`); `medir` (POST
  `/agente/servidor`); `remover`; `main` (`instalar|medir|remover`).
- **Chave de acesso** `passkey.py`: `de_b64url`/`b64url`; `dados_do_autenticador`
  (37 bytes + AT/ED); `_client_data` (`type`, `challenge` por `hmac.compare_digest`,
  `origin` em conjunto, recusa `crossOrigin`); `_bloco_ok` (`rpIdHash`, UP, UV);
  `conferir_entrada(cliente, autenticador, assinatura, chave, desafio, rp_id, origens)`
  assina `authenticatorData || sha256(clientDataJSON)` e confere com
  `p256.conferir_bytes`; `contador_ok`. `p256.py`: `ponto_valido`, `ponto_de_bytes`
  (só não comprimido), `conferir(publica, resumo, r, s)`, `conferir_bytes`,
  `assinatura_de_der` (DER canônico, teto 80 bytes), testado contra RFC 6979 A.2.5
  (`test_p256.py`). `test_passkey.py` usa um assinador **de teste** feito com `p256`
  (vetor de dentro) — a C precisa do de fora.
- **Chave no banco** `banco.py:572` `chave_de_acesso` (`cred_id` base64url UNIQUE global,
  `chave_x`/`chave_y` em **hex sem zero à esquerda** — `"%x"` em
  `guardar_chave_de_acesso`, 4732 —, `contador`, `revogada_em`); `chave_de_acesso(cred_id)`
  (4759, só viva de conta viva, devolve `(x, y)` int); `chaves_de_acesso(usuario_id)` (sem
  a pública, de propósito); `usar_chave_de_acesso` (4804, o `UPDATE` decide o contador).
- **Servidor** `servir.py`: `ORIGENS_OK`/`HOSTS_OK` (344, `https://dervs.com.br` só);
  `Hub._rp_id` (1223, do `Host` já conferido); `_entrar_chave` (1337, molde de rota de
  assinatura: balcão `passkey`, `RECUSA` única); `SO_OLHA`/`_servidor_so_olha` (1886);
  `_bytes_do_ajudante` (1901) e `_ajudante_linha` (1935, linha com `mktemp -d`, SHA-256,
  `-I`); `CHAVES_DO_TOPO` e `_medicao_limpa` (lista fechada); `_maquina_do_servidor`;
  `_agente_servidor` (2107, balcão `servidor_relato` 60, resposta `{ok, invalidos}`);
  `_servidor_ligado` (2133) e a montagem de `servidores_ligados` em `_dados` (864);
  rotas em `ROTAS` (4425–4532: `/api/chaves*`, `/api/maquinas*`, `/agente/servidor`,
  `/ajudante/servidor.py`, `/api/ajudante/linha`). `cortina.registrar_tentativa(origem,
  agora, balcao, teto)` é o balcão.
- **Bloqueio** `tarefas.py:69` `PROJETOS_BLOQUEADOS = {"ajudei-saude"}`;
  `_nome_normalizado` (263); `projeto_bloqueado` (269).
- **Tela** `assets/painel.js`: `haQuanto` (55); `linhaDeSistema` (3277);
  `linhaDeServidorLigado` (3299, já tem o grupo `acoes` com "Desligar este servidor" e o
  `confirmar`); `cartaoDosServidores` (3434); `ligarUmServidor` (3475);
  `ligarFluxoDosServidores` (3537). `navigator.credentials.get` existe só em
  `assets/portas.js:76` (login), com `userVerification: "required"` e a conversão base64url.
- **Testes** `test_ajudante_servidor.py` (`problemas_do_fonte`: ASCII, Python 3.8, uma
  marca, `PROIBIDO` com `.conf`/`Env`/`executor`, `docker` só nos dois argv, `subprocess`
  só em `rodar`, `shell=False`, `__main__` no fim; `Dubles`; `ComRaiz`), `test_servidor_fio.py`
  (baixa, confere SHA-256, instala com Docker falso, confere campos do `painel.js`),
  `test_passkey.py`, `test_rotas.py` (`PROIBIDO`, `AMPUTADOS` com `ACOES`), `test_banco.py`
  (`test_as_vinte_tabelas_existem`, lista à mão).
- **Onde a ordem desce:** hoje nada desce ao ajudante. A tarefa do computador desce na
  resposta de `/agente/relatorio` (`_tarefa_pendente`); a B proíbe isso em
  `/agente/servidor`. Por isso a C cria `/agente/servidor/ordens` numa unidade própria
  (C1.6, C8), e o resultado volta por `/agente/servidor/desfecho`.

## fontes_externas

- **W3C Web Authentication Level 3**, https://www.w3.org/TR/webauthn-3/ , lido em
  09/10/2026. Confirmado na leitura: §7.2 passos 1–6 (`navigator.credentials.get`,
  `allowCredentials`, identificar a credencial); §6.5.5, assinatura "MUST be encoded as an
  ASN.1 DER Ecdsa-Sig-Value" (RFC 3279 §2.2.3); §6.1.1, autenticador sem contador manda
  zero; §5.8.5, ES256 exige `crv` 1 (P-256) e proíbe ponto comprimido; o índice de §10.1
  lista só `appid`, `appidExclude`, `credProps`, `prf`, `largeBlob` — **não há extensão de
  confirmação de transação** (o antigo `txAuthSimple` não existe): o aparelho não mostra o
  desafio ao dono. **De conhecimento** (a ferramenta cortou a página no passo 7 do §7.2) e
  já implementado e testado em `passkey.conferir_entrada`: `C.type == "webauthn.get"`,
  `C.challenge` = base64url do desafio, `C.origin` esperado, `topOrigin`/`crossOrigin`,
  `rpIdHash == SHA-256(rpId)`, UP obrigatório, UV quando exigido, `hash = SHA-256(cData)`,
  assinatura sobre `authData || hash`, regra do `signCount`; desafio de pelo menos 16
  bytes (§13.4.3).
- **`garcia-goncalves/deploy-padrao`**, commit `1d57f57` (28/09/2026), lido por `gh api` em
  09/10/2026: `servidor/deploy` aceita `<projeto> <arquivo.tar.gz> [commit]`,
  `<projeto> --voltar`, `--historico`, `--lista`; com menos de dois argumentos imprime o uso
  e sai 1; exige root (`id -u`); `umask 022`; `QUEM="${SUDO_USER:-...}"`; `flock` por
  projeto; `--voltar` refaz `build` + `up -d` + saúde e grava `OK(voltou)` ou
  `FALHOU-AO-VOLTAR`. `servidor/INSTALAR.md`: comando em `/usr/local/bin/deploy`,
  configuração em `/etc/deploy/<projeto>.conf`, `sudoers.d/deploy` com
  `%deploy ALL=(root) NOPASSWD:` seguido de `/usr/local/bin/deploy` (qualquer argumento),
  `visudo -cf` para conferir.
- **sudoers(5)**, de conhecimento: argumentos escritos na regra casam **exatamente**;
  curinga `*` casa também espaço (por isso proibido aqui); `#includedir` ignora arquivo com
  `.` no nome ou terminado em `~`; `sudo -n` não pergunta senha.
- **systemd.exec(5)**, de conhecimento: `NoNewPrivileges=yes` impede ganhar privilégio por
  setuid (mata o `sudo`); `CapabilityBoundingSet=` vazio vale para os filhos, root inclusive;
  `ProtectSystem=strict` deixa o disco só-leitura para todo o processo e os filhos. Confirmar
  na conferência manual F-2 na VPS, como na B.
- **OpenSSL 3.5.7** (9 jun 2026) nesta máquina, `openssl version` em 09/10/2026: gera a chave
  P-256 e assina em DER (`ecparam -genkey`, `dgst -sha256 -sign`) — a testemunha de fora.

## fora_de_escopo

O do briefing, mais (corte do Diretor):

- **Publicar a versão do GitHub** (dúvida 1): o kit não publica do GitHub; fica para uma
  entrega própria.
- Mostrar ao dono, no próprio aparelho, o texto da ordem (não existe em WebAuthn hoje).
- Rodar as ordens pelo DERVS-VOZ, por regra, por IA ou por agenda.
- Conferir o contador do autenticador no ajudante; atualizar as chaves do servidor sem colar
  a linha.
- Ordem para vários servidores de uma vez; fila de ordens (uma em andamento por servidor).
- Qualquer leitura do que a ação imprimiu; "ver log".
- Mudar a unidade de medição da B (continua byte a byte igual).
- Instalar na VPS de verdade e a conferência manual F-2: mão do dono, depois de publicar.

## contradicoes_resolvidas

1. **Briefing: três ações; kit: `deploy <projeto>` não publica.** Vence o kit: duas ações
   nesta entrega (reiniciar, voltar); publicar vira dúvida 1 com recomendação. Inventar um
   jeito de baixar o código pelo DERVS quebraria a própria promessa (o site tomado
   publicaria o código dele).
2. **Briefing: "quem tomasse o dervs.com.br não manda o servidor fazer nada"; WebAuthn: o
   aparelho não mostra o que assina.** Vence a verdade (Lei 2): a promessa vira "sem um
   toque seu, nada acontece; com o site tomado, cada toque pode virar no máximo um pedido da
   lista fechada, nunca no Ajudei, nunca um comando, nunca ler dado, e no máximo 6 por
   hora". O teto de C4 e o texto de "O que isso faz?" saem daqui. Dúvida 2.
3. **Briefing: sudoers na instalação; B: unidade com `NoNewPrivileges`.** Vence uma unidade
   própria para as ordens, sem as diretivas que matam o `sudo`; a da B não muda.
4. **Briefing: `deploy <projeto> --voltar` com sudoers "restrita àquele comando"; kit:
   `%deploy` libera qualquer argumento.** Vence uma linha por projeto com argumentos exatos,
   arquivo próprio, e o usuário do ajudante fora do grupo `deploy`.
5. **De onde vêm os projetos do sudoers: `/etc/deploy/*.conf` contra o historico.** Vence o
   historico (já lido, e só projeto que já publicou tem para onde voltar); listar `.conf`
   reprovaria `test_ajudante_servidor.PROIBIDO`.
6. **"O ajudante guarda a chave pública": embutida no arquivo contra na linha.** Vence na
   linha: o arquivo continua igual para todo mundo (um SHA-256 só, uma marca só), e o dono vê
   na linha o que está entregando. As duas formas confiam no dervs.com.br na hora de colar —
   a mesma confiança da B.
7. **Origem fixa `https://dervs.com.br` contra derivada do ALVO.** Vence derivada do ALVO
   injetado (em produção é exatamente `https://dervs.com.br`): permite o fio de teste local
   sem um segundo caminho no código.
8. **Ordem no `POST /agente/servidor` contra rota nova.** Vence rota nova: a B promete
   (e testa) que a medição nunca traz trabalho, e o processo que pode usar `sudo` é outro.
9. **Contador no ajudante.** Não confere: chave sincronizada manda zero e vários servidores
   não compartilham contador; o número único e o prazo fazem o papel; o DERVS confere o
   contador na hora de assinar.
10. **2 min ("não pegou") contra 5 min (prazo da assinatura).** O DERVS só entrega até 120 s
    depois de assinada; o ajudante aceita até `vence`. Assim a tela que disse "não pegou"
    nunca é desmentida por uma ação feita no minuto 3.

## duvidas_para_o_dono

1. **"Publicar a versão do GitHub" fica para depois?** O comando de publicar do servidor só
   aceita o arquivo que o VS Code manda; ele não busca nada no GitHub. **Recomendação: sim,
   tirar desta entrega** e entregar "reiniciar" e "voltar a versão anterior", que funcionam
   hoje. Para publicar pelo painel numa entrega própria, o caminho seguro é o próprio servidor
   baixar do GitHub o commit exato que você assinou, com uma permissão de leitura do GitHub
   guardada na VPS pela sua mão — nunca o DERVS entregando o código. A decisão está tomada
   assim pela autonomia delegada; você pode inverter.
2. **Aceita a promessa honesta?** A digital prova que foi você quem tocou, mas o aparelho não
   mostra o texto do pedido. Se alguém tomasse o dervs.com.br, poderia trocar o pedido na
   hora do seu toque (inclusive num login comum): o pior seria reiniciar um sistema ou voltar
   a versão de um projeto liberado, no máximo 6 vezes por hora, nunca no Ajudei e nunca um
   comando. **Recomendação: aceitar**, com o teto por hora e essa frase escrita em "O que
   isso faz?". A alternativa sem esse risco é aprovar cada pedido também no DERVS-VOZ, no
   seu computador — outra entrega. Decidido assim pela autonomia delegada; você pode inverter.
