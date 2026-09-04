# Servidores múltiplos — as quatro lentes (modo enxuto)

Despacho único cobrindo Analista, Arquiteto, Pesquisador e Diretor. As quatro
investigações abaixo foram escritas sem uma ler a saída da outra — a
reconciliação é trabalho do Sintetizador, em `spec.md`.

---

## Analista

**Usuário concreto.** O dono, de manhã, no painel do celular ou do notebook,
com pressa: ele acabou de subir um projeto novo num servidor da TineHost (um
dos cinco: `medconsultoria`, `ccvp`, `zacareli`, `sophia`,
`camargo-e-soares`) e quer que o card daquele projeto mostre, sem abrir
terminal, que ele está respondendo ali. O André, no mesmo painel, olha o
mesmo card em profundidade maior: quer confirmar que o projeto responde nos
**dois** servidores em que ele mora hoje (ex. um protótipo na OVH e a versão
de cliente na TineHost) sem confundir um com o outro.

**Momentos de uso, em ordem de frequência:**
1. **Ler o painel** (diário, várias vezes ao dia) — bater o olho no selo "no
   servidor" de cada projeto e saber, sem clicar, em quantos e quais ele
   responde.
2. **Cadastrar o endereço de um projeto num servidor já conhecido** (toda vez
   que um projeto novo sobe, ou muda de endereço) — hoje já existe para um
   endereço solto; passa a exigir escolher o servidor também.
3. **Cadastrar um servidor novo** (raro — a cada provedor novo que o dono ou
   o André passam a usar. Hoje são OVH e os cinco da TineHost: seis
   servidores nomeáveis já existem na cabeça do dono, zero estão nomeados no
   DERVS).
4. **Apagar um servidor** (mais raro ainda — só quando um provedor sai de
   uso).

O padrão de subdomínio (momento 3, quando o dono o informa) existe para
baratear o momento 2: sem ele, cada projeto novo exige clicar e digitar; com
ele, o DERVS testa sozinho e o momento 2 desaparece para o caso comum.

**O que seria fracasso:** o dono cadastra um servidor, volta ao painel e o
selo de "servidor" continua dizendo a mesma frase genérica de antes —
"conectado / desconectado" sem dizer **qual** servidor. Isso desfaz a
promessa do produto (§4.2 de `A-APLICACAO.md`: "a diferença entre as três é o
produto") transformando uma diferença nova (servidor A responde, servidor B
não) em ruído indistinguível. Fracasso também é o dono cadastrar um padrão de
subdomínio e ele preencher um projeto **errado** — ex. `blog.tinehost.com.br`
resolvendo por acaso e sendo atribuído ao projeto "blog-antigo" que não é
aquele. Isso não está coberto pelo critério de aceitação do briefing além de
"testa o padrão contra nomes de projeto já conhecidos" — é um risco, não uma
funcionalidade sem dono (ver Diretor).

**Funcionalidade sem dono:** nenhuma achada. Todo item do
`criterio_de_aceitacao` do briefing tem um momento de uso correspondente
acima. Não há item "que alguém achou legal" sobrando.

**A lente DX se aplica.** O usuário é desenvolvedor operando o próprio
parque de projetos. Critério DX: o formulário de "Conectar projeto" já usa
rótulos em português com `aria-label` (`assets/painel.js:1294-1303`), erro
explicado em português quando a peneira recusa (`ENDERECO_RECUSADO`,
`servir.py:1657`) — o padrão a manter é o mesmo: mensagem de erro que explica
o "porquê" nunca um código cru.

---

## Arquiteto

**Onde vive "O seu servidor" hoje — um endereço solto por projeto, sem
servidor nomeado.**

- **Tabela:** `endereco_producao` (`banco.py:384-393`). Colunas: `id`,
  `usuario_id` (dono, `REFERENCES usuario(id) ON DELETE CASCADE`), `projeto`,
  `url` (`NOT NULL CHECK` de não-vazio — "sem endereço" é a AUSÊNCIA da
  linha, nunca string vazia), `criado_em`, `atualizado_em`,
  `UNIQUE (usuario_id, projeto)`. Um projeto só pode ter **um** endereço por
  conta hoje — é exatamente essa restrição que o pedido do dono quebra: "o
  mesmo projeto pode ter endereço gravado em mais de um servidor". Índice
  `ix_endereco_dono` em `usuario_id` (`banco.py:393`).
- **Migração:** `_migrar_endereco_producao` (`banco.py:980-1018`) cria a
  tabela em conexão já aberta, e o comentário no schema
  (`banco.py:367-374`) documenta a decisão de dono-por-linha para evitar
  IDOR — precedente direto para a tabela nova.
- **Funções de acesso** (`banco.py`): `endereco_de_producao(usuario_id,
  projeto, con=None)` (linha 2989, lê um), `enderecos_de_producao(usuario_id,
  con=None)` (linha 3010, lê `{projeto: url}` inteiro — "o que o coletor
  consome de uma vez só"), `guardar_endereco_de_producao(usuario_id, projeto,
  url, con=None)` (linha 3023, grava/apaga; `url` vazia apaga a linha).
  **Nenhuma confere a URL** — a peneira mora em `coletar_github`, e é
  aplicada por quem chama, nunca duplicada aqui (comentário explícito na
  linha 3031-3034, citando um SSRF real que passou por peneira duplicada).
- **Rota de gravar:** `Hub._endereco_guardar` em `servir.py:1596-1650`,
  registrada via `/api/enderecos/guardar`. Ordem exata da defesa, que
  qualquer rota nova precisa repetir:
  1. sessão (`self._sessao()`);
  2. `Origin` em `ORIGENS_OK` e CSRF (`self._csrf_ok`);
  3. corpo (`self._corpo_json(teto=4096)`), `projeto` e `url` truncados
     (`self._texto_do_corpo(..., teto=...)`);
  4. se `url` vazia: apaga sem gastar balcão nem rede;
  5. **peneira de forma, sem rede**, `coletar_github.url_segura(url)` —
     pura, antes de qualquer coisa que toque rede;
  6. **teto do balcão `"endereco"`** (`cortina.registrar_tentativa(...,
     balcao="endereco", teto=self.TETO_DE_ENDERECOS)`, `TETO_DE_ENDERECOS =
     20`) — ANTES de `host_publico`, porque `getaddrinfo` não tem prazo e sem
     essa ordem um punhado de nomes que não resolvem prende threads antes do
     teto ser consultado (comentário `servir.py:1628-1632`, achado da revisão
     de Python);
  7. `coletar_github.host_publico(hostname)` — resolve de verdade, recusa
     rede interna;
  8. `banco.guardar_endereco_de_producao(...)`;
  9. `coletar_github.mede_site(url)` para devolver `ok`/`codigo`/`erro` na
     hora, sem esperar a próxima coleta de 20 min.
  Rota de leitura: `Hub._enderecos` (`servir.py:1588-1594`), só sessão, devolve
  `banco.enderecos_de_producao(sessao["usuario_id"])`.
- **A peneira em si**, sempre chamada QUALIFICADA (`coletar_github.X`, nunca
  `from coletar_github import`, guardado por `test_rotas.EXECUTA`, comentário
  `servir.py:78-87`): `url_segura(url)` (`coletar_github.py:110-131`, forma
  pura, sem DNS), `enderecos_publicos(host)` (linha 141-160, resolve e falha
  fechada por conjunto — qualquer IP privado no conjunto recusa o nome
  inteiro), `host_publico(host)` (linha 163-165), `mede_site(url)` (linha
  265+, resolve **uma vez** e conecta no IP fixado, duas tentativas antes de
  acusar fora do ar). **Nenhuma rota nova pode reescrever nada disso** — é
  reusada qualificada, do mesmo jeito.

**Onde a medição de verdade acontece — não é a rota que grava, é a coleta
periódica de 20 minutos.** `coletar_github.py:1032-1044`: dentro do laço que
grava a camada `github` de cada projeto, lê `enderecos =
banco.enderecos_de_producao(dono, con=con)` **uma vez por rodada**
(linha 966), e para cada projeto: `url_prod = enderecos.get(nome) or
local.get("url_prod") or ""` — o banco vence o `casos.json` (comentário
1024-1031: "quem digitou um endereço na tela espera que ele valha"). Se
`url_prod`, chama `mede_site(url_prod)` e grava em `novo["site"]`
(dict único — hoje só cabe **um** site por projeto). O `casos.json` local
tem o mesmo formato de fallback em `coletar.py:989-1021` (a camada `local`,
não `github`) via `caso.get("containers", [])` e `caso["url_prod"]` — dois
lugares que precisam da mesma mudança se `url_prod` deixar de ser singular.

**Onde o selo nasce:** `regras.py:193-213`, item 15 da lista de pendências,
lê `site = (gh or {}).get("site") or {}` — um `dict` **singular**. Isso é o
ponto de maior impacto da mudança: virar `sites` (lista, um por servidor) ou
manter `site` como "pior caso agregado" e adicionar um campo novo por
servidor é decisão do Sintetizador, não fato do repositório. `montar_estado`
(`banco.py:1490-1543`) monta o card de cada projeto juntando `local`,
`github`, `pesado` e `auditoria` — a camada `github` (que carrega `site`) é
copiada inteira em `p["github"] = camadas["github"]["dados"]`
(`banco.py:1511`), então qualquer chave nova dentro de `novo` em
`coletar_github.py` chega ao painel sem mudar `montar_estado`. As outras duas
pernas do selo ("no seu computador", "no GitHub") vivem na mesma função:
`local` cobre containers/portas/git (via `coleta_git`/`coleta_docker` em
`coletar.py`), `github` cobre CI/PRs/deploy (via `coletar_github.py`).

**Padrão de teste do repositório para rota nova, parecida:**
- `test_servir.py` tem casos de rota existentes para `/api/enderecos*` (ver
  `AContaDoGithubNoServidorDeVerdade`, `AAuditoriaNoServidorDeVerdade` como
  vizinhos de estilo — classe por comportamento, `self.com_projeto(...)` como
  helper de fixture).
- `test_banco.py` tem `EnderecoDeProducaoTemDono` e
  `EnderecoDeProducaoNoBancoVelho` — o segundo cobre migração contra banco
  legado, que a tabela `servidor` nova vai precisar repetir (dado existente
  em `endereco_producao` não pode sumir).
- `test_regras.py` tem `SiteDeProducao` (linha ~246: `base["site"] =
  dict({"url": "https://exemplo.com.br"}, **site)`) — cobre o item 15 da
  lista de pendências e precisa de um gêmeo para "mais de um servidor
  respondendo".
- **Nenhum arquivo `test_coletar_github.py` existe** — os testes de
  `coletar_github.py` vivem espalhados em `test_servir.py`/`test_regras.py`.
  Arquivo de teste **novo** (se nascer um) precisa entrar em
  `.github/workflows/ci.yml`, que lista cada `test_*.py` à mão (linhas
  83-243) — há um passo que cobra a lista completa.
- CI já cobra `python test_banco.py`, `test_regras.py`, `test_coletar.py`,
  `test_coletar_pesado.py`, `test_servir.py`, `test_rotas.py` — todos tocados
  por esta mudança.

**Onde fica a tela no frontend:**
- **`assets/painel.js:1215-1319`** — o cartão "O seu servidor" (`cartao3`,
  título fixo "O seu servidor" — **precisa virar plural/lista de
  servidores**), estado (`sem_dados`/`conectado`/`desconectado`) calculado de
  `ENDERECOS`/`ENDERECOS_LIDO_EM` (variáveis de módulo, linhas 883-884,
  lidas de `/api/enderecos` em `olharOsEnderecos()`, linha 1076-1087).
  `formularioDeEndereco()` (linha 1245-1319) é o formulário atual: lista os
  já gravados com `marcaDaPorta` para os três estados do site (conectado /
  desconectado / sem_dados — os mesmos três do quarto estado do produto), e
  um `<form>` com dois campos (projeto, url). **É este arquivo que ganha o
  seletor de servidor** — hoje o formulário não pergunta "em qual servidor",
  porque só existe um endereço por projeto.
- **O card do projeto no painel** (fora do escopo lido nesta busca —
  `regras.py` monta a pendência "site fora do ar" citada acima, e o card
  visual que lista os selos por projeto fica no mesmo `painel.js`, na função
  que desenha a lista principal — não localizada com caminho de linha exato
  nesta busca; a fase de design leve deve procurar `marcaDaPorta` e o
  desenho do selo de "no ar" atual antes de tocar).
- CSS: `assets/painel.css` tem as classes `.enderecos`, `.endereco`,
  `.endereco__dizeres`, `.endereco__url`, `.endereco--novo` (nomeadas em
  `formularioDeEndereco`) — reusar o mesmo prefixo para o card de servidor
  evita destoar da convenção da casa.

**Convenção da casa a seguir:** nome de função em português, com auxiliar de
verbo (`guardar_`, `enderecos_de_`); `usuario_id` **sempre** posicional e
obrigatório, nunca com padrão (o motivo, escrito em `banco.py:2992-2996` e
repetido em `banco.py:3065-3068`, é IDOR — funcionalidade nova que dá um
`usuario_id` opcional reabre o mesmo defeito consertado duas vezes); toda
tabela nova de dado por conta ganha `UNIQUE` que impede vazamento entre
contas e um índice em `usuario_id`; toda rota nova de escrita repete a
sequência sessão → Origin/CSRF → corpo limitado → peneira pura → teto de
balcão **próprio** (nunca reusar `TETO_DE_ENDERECOS` para outra coisa — o
comentário em `servir.py:1583-1585` avisa que misturar balcões "tranca a
máquina legítima, e isso já aconteceu duas vezes nesta casa").

---

## Pesquisador

**Não há biblioteca externa a considerar.** O repositório é biblioteca
padrão pura por decisão registrada (`CLAUDE.md`, "As três leis deste
código", lei 1), e a CI reprova qualquer `requirements.txt` ou
`pyproject.toml` novo. Este pedido não precisa de nada que a stdlib não
tenha: cadastro de servidor é uma tabela e um formulário; teste de padrão de
subdomínio contra nome de projeto é comparação de string.

**Padrão de subdomínio: casamento por `fnmatch`, não por regex nem por
biblioteca de glob.** O módulo `fnmatch` da biblioteca padrão do Python já
resolve `*.tinehost.com.br` contra `meu-projeto.tinehost.com.br` com
`fnmatch.fnmatch(nome_testado, padrao)`, sem introduzir dependência nem
reinventar um parser de glob. Isso não é uma dúvida real — é o jeito óbvio
dentro da própria stdlib, coerente com a lei 1 do `CLAUDE.md`.

**A dúvida genuína que existia — "dá para testar o padrão sem repetir a
peneira anti-SSRF?" — está respondida pelo próprio Arquiteto: não é uma
segunda peneira, é a mesma `coletar_github.url_segura` +
`coletar_github.host_publico` chamada com a URL montada
(`https://` + nome-do-projeto-substituído-no-padrão). A rota que testa
autodetecção monta a URL candidata e a passa pela peneira existente, do
mesmo jeito que a rota manual já faz — nenhum padrão novo de segurança
entra, só um lugar novo que monta a string antes de checar.

`fontes_externas: nenhuma`.

---

## Diretor

**O corte do briefing (`fora_de_escopo`) é vinculante e não é reaberto
aqui:** SSH/varredura por credencial, correção autônoma/escrita no servidor,
saúde do servidor (CPU/disco/memória/containers), e "zero pendência" como
critério. Nenhum desses volta a entrar.

**O que mais deveria esperar, dentro do que sobrou:**

1. **Autodetecção por padrão de subdomínio deveria ser a SEGUNDA entrega
   dentro desta mesma etapa, não a primeira — e continua sendo fase 1 de
   escopo, só não é o primeiro código a nascer.** Motivo: ela depende de dois
   alicerces que ainda não existem — a tabela `servidor` nomeada, e a rota
   que grava endereço por (projeto, servidor). Construí-la antes seria
   escrever contra uma tabela que ainda muda de forma. Ordem correta dentro
   da mesma entrega: (a) CRUD de servidor nomeado, (b) endereço por projeto
   **por servidor** (com todos os testes de dono/peneira/teto que o
   Arquiteto listou), (c) autodetecção por padrão, por cima das duas.
   Nenhuma das três é "fica para depois" — o briefing pediu as três no
   `criterio_de_aceitacao` — a ordem é só a sequência de construção.

2. **Risco real que a Analista apontou e o briefing não cobre explicitamente:
   um padrão de subdomínio pode casar um projeto errado.** Ex.:
   `api.tinehost.com.br` resolvendo por acaso para um projeto de nome
   parecido mas não relacionado. Isso não é motivo para cortar a
   autodetecção — é motivo para a implementação **sempre mostrar o que
   preencheu sozinho antes de gravar**, nunca gravar direto sem o dono ver
   (o mesmo princípio do §5.2 do produto: "o Claude analisa, propõe, e
   para" — aqui adaptado a "o DERVS testa, propõe, e o dono confirma"). Isto
   é uma decisão de comportamento, não um corte de escopo, então vira
   critério na spec, não vira `fora_de_escopo`.

3. **Não é candidato a corte, mas é candidato a atenção redobrada na fase 6:
   a migração de `endereco_producao` para a tabela nova.** Há dado real
   gravado hoje (etapa B2/B3 já publicada e em uso — `A-APLICACAO.md` §11
   confirma "as três portas" no ar desde 01/09). Uma migração que perde o
   endereço já gravado de um projeto quebra a promessa "eu confio no que
   está no ar" bem no dado que essa mesma promessa depende. Não é escopo
   novo — é rigor extra dentro do escopo que já existe (migração de banco já
   é `risco` nomeado no briefing).

**Balde 1 (faz a coisa existir):** tabela `servidor` + CRUD; endereço por
projeto **por servidor**; os três selos separados na tela; peneira e teto
reusados sem segunda cópia; teste com dois servidores e o mesmo projeto
respondendo nos dois.

**Balde 2 (fica boa, pode esperar uma segunda rodada da mesma etapa, não uma
etapa futura):** autodetecção por padrão de subdomínio.

**Balde 3 (nem entra):** nada identificado além do que o briefing já cortou.

**Custo do corte, em uma frase:** nenhum corte novo além dos já decididos no
briefing — a única mudança é de **ordem interna** dentro da execução, e ela
não tira nada do dono, só evita construir a autodetecção em cima de uma
tabela que ainda vai mudar de forma.
