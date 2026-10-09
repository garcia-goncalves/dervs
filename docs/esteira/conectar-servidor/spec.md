# Spec — entrega B: o ajudante no servidor, só olhando

Fase 2, 09/10/2026. Síntese de uma descoberta em modo enxuto (4 lentes num despacho).
Contrato: `briefing.md` desta pasta.

## problema

O DERVS mede o servidor só de fora, pelo endereço público: sabe se o site responde, mas
não sabe quais sistemas rodam lá, se algum caiu sem derrubar o site, nem **qual versão está
no ar**. O dono publica pelo VS Code e não tem onde ver se a versão publicada é a mesma do
GitHub. E a única forma de olhar por dentro hoje é uma chave SSH, que o dono decidiu nunca
guardar no site.

## solucao

Um **arquivo único, `ajudante_servidor.py`** (biblioteca padrão, ASCII puro, lido do disco e
nunca importado pelo servidor, como o `conectador.py`), servido com o endereço injetado e
colado no servidor por uma linha. Ele faz três coisas: se instala, pareia e mede.

**1. A linha** (mostrada na tela, com o resumo SHA-256 calculado sobre os bytes servidos):

```
curl -fsSL https://dervs.com.br/ajudante/servidor.py -o dervs-ajudante.py && echo "<SHA256>  dervs-ajudante.py" | sha256sum -c - && sudo python3 dervs-ajudante.py
```

Sem `curl | sh` (download pela metade executaria pela metade). O resumo prova integridade no
caminho; **não** protege contra um dervs.com.br tomado — a tela não promete isso.
`GET /ajudante/servidor.py` é aberta e não cria estado.

**2. Instalação** (rodando como root, uma vez): confere `python3 >= 3.8`, `systemd` e
`docker`; pede pareamento com `POST /agente/pedir` levando `tipo: "servidor"`; imprime o
endereço `#/conectar?autorizar=XXXX-XXXX` e o código (servidor está noutra rede, então a
tela exige digitar o código); espera em `/agente/esperar` (10 min); grava o token em
`/var/lib/dervs-ajudante/agente.json` (600) **logo após** o resgate; cria o usuário de
sistema `dervs-ajudante` no grupo `docker`; dá a ele **leitura** por ACL em
`/var/log/deploy/historico.log` (se existir e `setfacl` existir; sem mudar dono nem modo);
copia a si mesmo para `/opt/dervs-ajudante/` (root:root, 755); instala `dervs-ajudante.service`
(`oneshot`, `User=dervs-ajudante`, `NoNewPrivileges`, `ProtectSystem=strict`,
`ProtectHome=yes`, `PrivateTmp`, `ReadWritePaths=/var/lib/dervs-ajudante`,
`RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`) e `.timer` (`OnBootSec=30s`,
`OnUnitActiveSec=30s`, `AccuracySec=1s`); `enable --now`. Rodar de novo reaproveita o token.
Subcomando `remover` desfaz tudo.

**3. Medição** (a cada 30 s, processo novo):
- Contêineres: `docker ps -aq --no-trunc` e `docker inspect --format <CONSTANTE>` com
  exatamente: nome, estado, saúde, `StartedAt`, `RestartCount`, imagem, rótulo
  `com.docker.compose.project`, rótulo `org.opencontainers.image.revision`. **Nunca**
  `.Config.Env`, `.Labels` inteiro, `.Command`, log. Sem docker: `docker_mudo: true`.
- Servidor: nome (hostname), tempo ligado (`/proc/uptime`), carga (`/proc/loadavg`),
  memória (`/proc/meminfo`), disco (`os.statvfs("/")`).
- Publicações: última linha por projeto do `historico.log` (formato do kit
  `deploy-padrao`: `data hora projeto quem versao resultado`, versão
  `AAAAMMDD-HHMMSS-<commit>`). O campo `quem` é **descartado** no ajudante. Versão
  `antes-do-primeiro-deploy` ou resultado `FALHOU-AO-VOLTAR` → commit "não sei".
- Envia `POST /agente/servidor`.

**4. No servidor do DERVS:**
- `pedido_de_computador.tipo` e `maquina.tipo` (`'computador'|'servidor'`, padrão
  `computador`), migração no molde das que existem. O tipo vem do `/agente/pedir`, é copiado
  no resgate, aparece na tela de Autorizar ("um servidor chamado X"). Máquina servidor nasce
  `so_mede=1` como toda máquina desse caminho.
- `POST /agente/servidor`: só máquina `tipo='servidor'` (403 nas outras); balcão próprio
  `servidor_relato` (60 por 15 min); corpo validado por **lista fechada** de chaves e tipos
  (chave desconhecida descartada e contada em `invalidos`; `sha` só com `[0-9a-f]{7,40}`;
  textos com teto e sem caractere de controle; no máximo 200 contêineres e 200 publicações);
  resposta só `{ok}` — **nunca** `tarefa`. Grava em `medicao_de_servidor` (uma linha por
  máquina, sobrescrita; `maquina_id` PK com `ON DELETE CASCADE`, `usuario_id`, `medido_em`
  carimbado pelo DERVS na chegada, `dados` até 64 KiB) e carimba `maquina.visto_em` na mesma
  transação.
- Máquina `tipo='servidor'` leva 403 em `/agente/relatorio`, `/agente/resultado`,
  `/agente/pacote` e `/agente/voz/*`.
- `_dados` (depois do motor, como `progresso`) ganha `servidores_ligados`: por máquina
  servidor da conta, nome, `medido_em`, estado (`medido` se dentro de
  `regras.VALIDADE_DO_SERVIDOR = 180` s, senão `sem_dados`), máquina e lista de sistemas.
  E cada projeto ganha `no_ar` por servidor: commit curto, publicado em, e
  `regras.comparar_no_ar(sha, github)` → `igual` | `atras` (com N) | `diferente` | `nao_sei`.
  Projeto casa com contêiner/publicação pelo nome normalizado (mesmo critério de
  `coletar.py:1065`); sem casamento, nada é inventado.
- `coletar_github.PEDACO` passa a pedir `defaultBranchRef.target.oid` (sem ida a mais à
  rede) → `github.head_sha`; quando o commit no ar difere da ponta, o coletor pede
  `compare/{sha}...{branch}` (com o teto de chamadas que já existe) e guarda
  `github.no_ar = {sha, atras}`. `comparar_no_ar` só usa N se o `sha` comparado for o mesmo
  que está no ar agora; senão `diferente`.
- `/api/eventos` aceita ser aberto sem `id`: emite `event: servidor` com `medido_em` quando
  muda o `MAX(medido_em)` dos servidores da conta (só o carimbo; a tela relê `/api/dados`).
  Não mexe em `X-Accel-Buffering`, nginx nem na sonda de 1 s.
- `/api/ajudante/linha` (sessão): devolve a linha pronta com o SHA-256.

**5. Na tela (dentro de Conectar, menu continua com 4 itens):** cartão "Seus servidores"
com "Ligar um servidor" → mostra a linha, "copiar", o roteiro (onde colar, o que aparece,
o que fazer se der errado) e "o que isso faz?". Cada servidor ligado: nome, "medido há N s"
(`haQuanto`), "sem dados" passado o prazo, e a lista "sistemas rodando neste servidor"
(nome, de pé/caído, desde quando, reinícios). No cartão do projeto, linha "No ar em
<servidor>: versão de <data> — igual ao GitHub | N mudanças atrás | diferente do GitHub |
não sei qual versão está no ar".

**Por que essa forma:** reusa o pareamento por "Autorizar" e as trancas `so_mede` da
entrega A; o ajudante sem canal de ordem e sem atualização automática faz do dervs.com.br
tomado um vazamento de inventário, não uma chave mestra; a lista fechada dos dois lados é o
que protege o ambiente dos contêineres do Ajudei.

## o_que_ja_existe

- Pareamento: `servir.py:1650 _agente_pedir`, `servir.py:1688 _agente_esperar`,
  `banco.py:3415 resgatar_pedido_de_computador` (INSERT com `so_mede=1` em `banco.py:3445`),
  tabelas `pedido_de_computador` (`banco.py:385`) e `maquina` (`banco.py:332`).
- Trancas `so_mede`: `banco.py:2732 ligar_execucao`, `servir.py:3678` (409),
  `servir.py:3749 _voz_maquina` (403), `Hub.PACOTE` (`servir.py:1763`).
- Tarefa desce na resposta de `/agente/relatorio` (`servir.py:2550`, `_tarefa_pendente`
  em `servir.py:2659`).
- `_infra` (`banco.py:55`, `RESERVADOS` em `banco.py:85`) e `coletar.coleta_docker`
  (`coletar.py:911`, já com `docker ps --format` fixo) — uma linha por conta; não serve
  para vários servidores.
- Fluxo: `servir.py:2995 _eventos`, `servir.py:3035 _empurrar`, `FLUXOS_POR_SESSAO = 4`
  (`servir.py:2967`), `ligarFluxo` (`assets/painel.js:3963`).
- Servidor por endereço: tabela `servidor` (`banco.py:424`), `banco.enderecos_por_servidor`
  (`banco.py:4153`).
- GitHub: `coletar_github.PEDACO` (`coletar_github.py:455`), `traduz` (`:971`),
  `mede_deploy` (`:851`), `atras_de` (`:434`), regra `nao_publicado` (`regras.py:243`),
  `regras.VALIDADE` (`regras.py:553`), `camadas_do_selo` (`regras.py:603`).
- Teto por projeto `MAX_BYTES_POR_PROJETO` (`banco.py:94`).

## fontes_externas

- `garcia-goncalves/deploy-padrao`, commit 1d57f57 (28/09/2026), lido por `gh api` em
  09/10/2026: `servidor/deploy` grava `/var/log/deploy/historico.log`; versão vem de
  `kit-vscode/scripts/deploy-vps.sh:33` (`git rev-parse --short HEAD`); imagens **sem**
  rótulo OCI de revisão; `INSTALAR.md` põe o log em 750 root.
- https://docs.docker.com/reference/cli/docker/container/ls/ (09/10/2026): campos de
  `docker ps --format`; `RestartCount` e `StartedAt` só por `docker inspect --format`.
- API do GitHub `compare` aceita sha curto (testado em 09/10/2026 contra o próprio
  `deploy-padrao`: `498dafc...main` → `ahead_by: 2`).

## fora_de_escopo

O do briefing, mais (corte do Diretor): amarração manual de máquina a `servidor` ou a
projeto; histórico de quedas; regra/pendência nova (`sistema_caido`) — **o selo não muda
nesta entrega**; aviso ao DERVS-VOZ; portas abertas; rótulo OCI no kit `deploy-padrao`
(outro repositório, sugestão anotada).

## contradicoes_resolvidas

1. Briefing diz "commit = rótulo da imagem", mas o rótulo não existe hoje. Vence: rótulo
   OCI se houver, senão `historico.log`; sem os dois, "não sei".
2. "O pacote não tem `executor.py`" contra "não há pacote". Vence: o arquivo único é o
   pacote; teste prova que ele não cita `executor` e que `/agente/pacote` dá 403.
3. SSE contra sondagem simples. Vence SSE (contrato do briefing), mas só com o carimbo; a
   tela relê `/api/dados` para não haver segundo contrato.
4. Root contra usuário próprio. Vence usuário próprio + ACL de leitura + endurecimento do
   systemd; o grupo `docker` ainda equivale a root, e a tela diz isso em "o que isso faz?".
5. "Teste de regra da validade" contra não mexer no selo. Vence constante própria
   `regras.VALIDADE_DO_SERVIDOR`, fora de `regras.VALIDADE`.
6. Docker pelo soquete contra CLI. Vence CLI com `--format`: o soquete traria `Env` para a
   memória do ajudante.

## duvidas_para_o_dono

nenhuma. A única levantada (dar leitura ao ajudante no `historico.log` do kit) foi decidida
por mim pela autonomia delegada: **sim**, só leitura por ACL, sem mudar dono nem modo.
Sem isso o "commit no ar" seria "não sei" em todo projeto. O dono pode inverter.
