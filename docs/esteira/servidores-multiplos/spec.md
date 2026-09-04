## problema

Hoje "O seu servidor" (a porta 3 das três conexões, `docs/A-APLICACAO.md`
§5.1c) grava **um** endereço por projeto, solto, sem nome de servidor
(`endereco_producao`, `UNIQUE (usuario_id, projeto)` — `banco.py:384-393`).
O dono e o André operam vários provedores ao mesmo tempo (OVH e os cinco da
TineHost, ver `CLAUDE.md` "As três portas"), e um projeto pode responder em
mais de um ao mesmo tempo (ex. um protótipo e a versão de cliente). O
esquema atual não tem como representar isso: não há como dizer *onde* um
endereço mora, nem gravar dois endereços para o mesmo projeto. O selo "no
servidor" fica genérico — "conectado/desconectado" — quando a pergunta real
é "conectado **em qual**".

## solucao

**Uma tabela nova, `servidor`, nomeando o que hoje é implícito**, e a tabela
existente `endereco_producao` passa a apontar para um `servidor_id` em vez
de valer sozinha — o mesmo endereço-por-projeto de hoje, com o dono a mais.

```sql
CREATE TABLE IF NOT EXISTS servidor (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id         INTEGER NOT NULL REFERENCES usuario(id) ON DELETE CASCADE,
    nome               TEXT NOT NULL CHECK (length(trim(nome)) > 0),
    padrao_subdominio  TEXT,                 -- ex. "*.tinehost.com.br"; NULL = sem autodeteccao
    criado_em          TEXT NOT NULL,
    UNIQUE (usuario_id, nome)
);
CREATE INDEX IF NOT EXISTS ix_servidor_dono ON servidor (usuario_id);
```

`endereco_producao` ganha `servidor_id INTEGER NOT NULL REFERENCES
servidor(id) ON DELETE CASCADE`, e o `UNIQUE` muda de `(usuario_id,
projeto)` para `(usuario_id, servidor_id, projeto)` — o mesmo projeto grava
um endereço por servidor, nunca dois no mesmo servidor. `usuario_id`
continua na linha (não vira redundante com `servidor.usuario_id`): é o mesmo
motivo já escrito em `banco.py:369-374` para o esquema atual — a leitura por
dono não pode depender de um `JOIN` para não vazar entre contas por um
`JOIN` esquecido, e o precedente de IDOR consertado duas vezes
(`CLAUDE.md`, etapas 8 e 11) pesa contra simplificar aqui.

**Migração da tabela existente, e ela precisa preservar o dado que já está
no ar.** `endereco_producao` já tem linhas reais (as três portas estão
publicadas desde 01/09/2026 — `A-APLICACAO.md` §11). A migração cria, **por
conta que já tiver ao menos uma linha em `endereco_producao`**, um servidor
chamado `"Servidor"` (nome fixo, sem padrão de subdomínio), e aponta as
linhas existentes para ele antes de aplicar o novo `UNIQUE`. Nenhum endereço
gravado hoje pode sumir da migração — é o mesmo cuidado que
`_migrar_endereco_producao` (`banco.py:980-1018`) já toma ao nascer a
tabela atual num banco velho, aplicado uma casa acima.

**A rota de gravar (`Hub._endereco_guardar`, `servir.py:1596-1650`) ganha um
parâmetro `servidor_id`** no corpo, e repete, sem alterar, a sequência já
existente: sessão → `Origin`/CSRF → corpo limitado → peneira pura
(`coletar_github.url_segura`, qualificada) → teto de balcão **próprio**
(nunca reusar `TETO_DE_ENDERECOS` para o CRUD de servidor — balcão
compartilhado já travou o dono legítimo duas vezes, `servir.py:1583-1585`)
→ `coletar_github.host_publico` → grava → `coletar_github.mede_site` na
hora. Duas rotas novas, no mesmo padrão de sessão+CSRF+peneira: `POST
/api/servidores` (criar/apagar servidor — nome + padrão opcional) e `GET
/api/servidores` (listar os já cadastrados daquela conta).

**A coleta periódica de 20 minutos (`coletar_github.py:1032-1044`) passa a
medir por servidor, não por projeto.** Hoje `enderecos_de_producao(dono)`
devolve `{projeto: url}` e `novo["site"]` é um `dict` singular. Vira
`enderecos_por_servidor(dono)` devolvendo `{projeto: {servidor_nome: url}}`
(ou estrutura equivalente lida por servidor), e `novo["sites"]` vira uma
**lista** de `{servidor, url, ok, codigo, erro, medido_em}` — um item por
servidor onde aquele projeto tem endereço gravado. O mesmo cuidado que já
existe para `vulns` e para o `site` singular de hoje continua valendo por
item da lista: `ok=None` preserva a medição anterior daquele servidor
específico (nunca apaga um "fora do ar" real por uma rodada que não mediu),
e cada item carrega o próprio `medido_em`.

**`regras.py:193-213` (item 15, "o site de produção não respondeu") passa a
iterar a lista de `sites` em vez de ler um `site` só**, emitindo uma
pendência por servidor que estiver fora do ar — o nome do servidor entra na
frase ("O site de produção do X no servidor OVH não respondeu"), porque sem
ele duas pendências do mesmo projeto ficam indistinguíveis na fila.
`montar_estado` (`banco.py:1490-1543`) não muda: ele já copia a camada
`github` inteira (`banco.py:1511`), então a chave nova (`sites`, no lugar de
`site`) chega ao painel sem tocar essa função.

**Autodetecção por padrão de subdomínio, construída por cima das duas
peças acima (Diretor: mesma entrega, segunda metade da execução).** Quando o
dono cadastra um servidor com `padrao_subdominio` preenchido, uma rotina
testa esse padrão (`fnmatch.fnmatch`, biblioteca padrão) contra os nomes de
projeto já conhecidos (local + GitHub, os mesmos nomes que já povoam
`montar_estado`), monta a URL candidata (`https://` + nome do projeto no
lugar do `*`), passa pela mesma peneira (`url_segura` + `host_publico`) e,
só se responder, **propõe** o preenchimento — nunca grava sem o dono
confirmar. Isso não é uma trava nova: é o mesmo princípio de "o Claude
analisa, propõe, e para" (`A-APLICACAO.md` §5.2), adaptado a "o DERVS testa,
propõe, e o dono confirma com um clique", porque um subdomínio pode casar
por acidente um projeto que não é aquele (achado da lente Analista).

**Na tela ("Conectar projeto", `assets/painel.js:1215-1319`):** o cartão "O
seu servidor" vira uma lista de servidores cadastrados (nome + botão
apagar), cada um com seu próprio bloco de endereços por projeto — reusando
as classes CSS já existentes (`.enderecos`, `.endereco`,
`.endereco__dizeres`, `.endereco__url`) para não destoar da convenção da
casa. O formulário de endereço (`formularioDeEndereco`) ganha um seletor do
servidor de destino. O card do projeto no painel principal passa a listar o
nome de cada servidor onde ele responde (ou "não está em nenhum servidor
cadastrado") em vez do selo genérico único de hoje — o desenho exato fica
para a fase 3 (design leve), que reaproveita a direção "Torre de Controle" já
aprovada, sem reabrir escolha visual.

## o_que_ja_existe

- `banco.py:384-393` — tabela `endereco_producao` atual, `UNIQUE (usuario_id,
  projeto)`, o esquema que este trabalho estende.
- `banco.py:980-1018` — `_migrar_endereco_producao`, precedente direto de
  como nascer uma tabela nova num banco de produção já existente.
- `banco.py:2989-3059` — `endereco_de_producao`, `enderecos_de_producao`,
  `guardar_endereco_de_producao`: as três funções de acesso que ganham
  `servidor_id`, sem confiar a URL — a peneira continua fora do banco.
- `servir.py:1596-1650` — `Hub._endereco_guardar`, a sequência de defesa
  completa (sessão → Origin/CSRF → corpo limitado → peneira pura → teto de
  balcão `"endereco"` → resolução real → grava → mede na hora) que toda rota
  nova repete sem reescrever.
- `servir.py:1588-1594` — `Hub._enderecos`, a rota de leitura, só sessão.
- `servir.py:78-87` — o comentário e a trava (`test_rotas.EXECUTA`) que
  exigem `coletar_github.X` sempre qualificado, nunca `from ... import`.
- `coletar_github.py:110-165` — `url_segura`, `enderecos_publicos`,
  `host_publico`: a peneira anti-SSRF a ser reusada, nunca copiada.
- `coletar_github.py:265-299` — `mede_site`: resolve uma vez, conecta no IP
  fixado, duas tentativas antes de acusar fora do ar.
- `coletar_github.py:966-1057` — o laço da coleta de 20 minutos que lê
  `enderecos_de_producao(dono)` e grava `novo["site"]` por projeto; é onde a
  mudança para `sites` (lista) acontece.
- `coletar.py:989-1021` — a camada `local`/`casos.json`, com o mesmo campo
  `url_prod` em formato de fallback singular; precisa da mesma mudança de
  forma se `url_prod` deixar de ser um único endereço.
- `regras.py:193-213` — item 15 da lista de pendências, `site =
  (gh or {}).get("site") or {}`, o ponto que emite "site fora do ar";
  passa a iterar uma lista.
- `banco.py:1490-1543` — `montar_estado`, que copia a camada `github`
  inteira sem soletrar cada chave; não precisa mudar.
- `assets/painel.js:1215-1319` — o cartão "O seu servidor" e
  `formularioDeEndereco()`, a tela que ganha o seletor de servidor.
- `.github/workflows/ci.yml:83-243` — a lista à mão de `test_*.py`; arquivo
  de teste novo entra aqui no mesmo commit.
- `test_banco.py` (`EnderecoDeProducaoTemDono`,
  `EnderecoDeProducaoNoBancoVelho`), `test_servir.py`
  (`AContaDoGithubNoServidorDeVerdade`, `AAuditoriaNoServidorDeVerdade` como
  vizinhos de estilo), `test_regras.py` (`SiteDeProducao`) — os testes
  existentes que servem de molde para os novos.

## fontes_externas

nenhuma

## fora_de_escopo

- Varrer o servidor por SSH, API do provedor ou qualquer credencial —
  decisão do briefing, não reaberta.
- Qualquer correção automática ou escrita no servidor pelo DERVS ou pelo
  Claude Code — decisão do briefing, não reaberta. O caminho de correção
  continua sendo a fila de tarefas existente.
- Medir a saúde do servidor (CPU, disco, memória, containers) — decisão do
  briefing, não reaberta. Fica registrado como ideia futura, como já estava.
- "Zero pendência, tudo perfeito" como critério — decisão do briefing, não
  reaberta.
- **Corte adicional desta síntese:** nenhum. A única mudança em relação ao
  briefing é de **ordem de construção** (autodetecção por padrão de
  subdomínio nasce depois do CRUD de servidor e do endereço por servidor,
  dentro da mesma entrega), não de escopo. Ver `contradicoes_resolvidas`.

## contradicoes_resolvidas

- **Diretor sugeriu tratar a autodetecção por padrão de subdomínio como uma
  segunda rodada dentro da mesma etapa; o briefing lista as três coisas
  (cadastro de servidor, endereço por servidor, autodetecção) juntas no
  `criterio_de_aceitacao`, sem ordenar.** Decisão: as três continuam na
  mesma entrega — nada sai do escopo aprovado pelo dono — mas a
  **construção** segue a ordem do Diretor (CRUD de servidor → endereço por
  servidor → autodetecção por cima), porque o Arquiteto mostrou que a
  autodetecção depende da tabela `servidor` já existir e da rota de endereço
  já aceitar `servidor_id`: construí-la antes seria escrever contra uma
  tabela que ainda muda de forma. Isso é ordenação de plano, não corte —
  registrado aqui para a fase 5 (plano) herdar a sequência pronta.
- **A Analista apontou um risco não nomeado no briefing** (um padrão de
  subdomínio pode casar, por acidente, o endereço de um projeto que não é
  aquele) **e o Diretor não tratou como motivo de cortar a autodetecção,
  só como motivo de nunca gravar sem confirmação.** Decisão: a Analista e o
  Diretor concordam no resultado — o risco vira comportamento obrigatório
  ("propõe e para", nunca grava sozinho), não vira corte de escopo, porque o
  dono pediu explicitamente a autodetecção e discordar do pedido dele exigiria
  levar isso a `duvidas_para_o_dono`, o que não é o caso aqui: mostrar antes
  de gravar não contraria o pedido, só o entrega com a mesma trava que o
  produto já usa em todo outro lugar (§5.2 de `A-APLICACAO.md`).
- **Nenhuma outra contradição real entre as lentes.** O Pesquisador confirma
  que a peneira do Arquiteto é reusável sem segunda cópia para o caso de
  autodetecção; a Analista não pediu nada que o Diretor cortasse.

## duvidas_para_o_dono

nenhuma
