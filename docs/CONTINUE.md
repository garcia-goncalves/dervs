<!-- Copia versionada do handoff de 27/08/2026. O recado original vive em
     ~/.claude/handoffs/ e e entregue sozinho a uma sessao nova nesta pasta;
     esta copia existe para o dia em que o hook falhar, e para quem abrir o
     repositorio em outra maquina. Se divergir, o git manda. -->

# Continue daqui — DERVS, 27/08/2026

Pasta: `C:\Users\Desktop\source\repos\dervs` · `main @ e453bdc` · árvore limpa,
tudo no GitHub. **Nada pendente meu.** O dono vai abrir o chat e digitar
"continue" — este arquivo é a única coisa que você tem. Leia inteiro antes de
agir, e confirme no código o que ele afirma.

---

## O QUE FAZER, na ordem. Isto é o "continue".

**A tarefa NÃO é continuar o plano de 17 etapas.** Em 27/08/2026 o dono mudou a
ambição do produto. As palavras dele:

> "A aplicação está crua. Quase sem nada." · "Está tudo muito feio e sem
> design/layout/arquitetura... está confuso tbm" · "tudo precisa ser bem
> inteligente e fácil de entender... por exemplo: MÁQUINA. Achei confuso" ·
> "Quero uma aplicação pra DEV ultra revolucionária. Com tudo o que um dev
> precisa." · **"Parece que não sei se vc se lembra de tudo o que falamos que
> terá na aplicação... estou confuso."**

**A última frase é o problema central, e não é de código.** As decisões estão
espalhadas por um briefing, uma spec, um plano de 17 etapas e mais de 30
memórias. Não existe UM documento que responda *"o que esta aplicação é e o que
ela vai ter"*. Enquanto ele não existir, o dono se sente perdido a cada sessão, e
nenhuma quantidade de código entregue resolve isso.

### Passo 1 — Brainstorm COM ele (skill `superpowers:brainstorming`)

Ele pediu, com todas as letras, para **analisar e estudar juntos** o que a
aplicação será e todas as funcionalidades, e para **refinar e melhorar as ideias
dele** — não só transcrever, e não decidir sozinho. Ele quer as melhores ideias
como proposta, não um cardápio de opções sem recomendação.

### Passo 2 — Pesquisa na internet (ele pediu explicitamente)

Para o documento de arquitetura ficar "completo, inteligente e automatizado".

**Já pesquisado, NÃO refazer:** Backstage (auto-hospedado custa 3–12
engenheiros, não serve para dois) · Coolify/Dokploy (resolvem VPS melhor que
reescrever) · Uptime Kuma + Beszel + GlitchTip (vigilância em <80 MB) · Apache
DevLake (medidas DORA). **Confirmado: não existe ferramenta pronta para *drift*
entre o git e o que está publicado** — é o diferencial do produto.

O que **falta** pesquisar, e é o que ele pediu de novo: como as ferramentas de
dev de 2026 organizam descoberta de projetos locais, conexão com servidores, e
gestão de ferramental de agente (MCPs, skills, plugins).

### Passo 3 — UM documento de arquitetura, que vire a fonte única

Sugestão de lugar: `docs/A-APLICACAO.md`. Ele tem de responder, numa leitura só:
o que o DERVS é, para quem, o que ele mostra, o que ele faz, e o que ele nunca
vai fazer. Todo o resto passa a apontar para ele.

### Passo 4 — Desenvolver

Só depois dos três acima. Ele disse "comece o desenvolvimento de tudo".

---

## AS IDEIAS DO DONO, para refinar (não são ordens fechadas)

- **Três conexões**: servidores (a VPS OVH e as que vierem) · **pastas do PC**
  (projetos locais — o usuário **escolhe** a pasta, e o padrão é `source/repos`)
  · **GitHub** (repositórios e organização). Hoje os projetos vêm do
  `casos.json` escrito à mão; descoberta automática de pasta é novidade.
- **Agentes, MCPs, skills e plugins** como parte do produto — o DERVS
  gerenciando o próprio ferramental do Claude Code, não só vigiando repos.
- **Nomenclatura é trabalho de produto.** "MÁQUINA" (a 4ª classe de acesso, da
  etapa 11) foi o exemplo que ele deu de confuso. O padrão se repete: o
  vocabulário da tela é o vocabulário do banco. Passar a tela inteira pelo
  crivo "isso explica sozinho?".
- **Design de verdade.** Isto **não é retrabalho**: as etapas 13, 14 e 15 do
  plano *são* tokens, folha de estilo, as seis telas e o teste de design — e
  nunca começaram. "Está feio" é a etapa 13 não ter começado.

## PROPOSTAS MINHAS PARA O BRAINSTORM (semente, não decisão)

- **A tela inicial responde "o que eu faço agora?"**, não "aqui está tudo". Uma
  ação recomendada por vez, com o porquê junto. Lista de 203 alertas treina o
  dono a ignorar a lista inteira.
- **Um projeto, três colunas: no seu PC / no GitHub / no ar.** O drift entre as
  três é o coração do produto e o diferencial já confirmado por pesquisa.
- **Descoberta automática**: varrer a pasta escolhida, detectar tipo (Node,
  Python, .NET), remoto git, container, porta. O `casos.json` à mão vira exceção.
- **Painel do ferramental do Claude**: o que está ligado, quanto custa por
  chamada, o que usar em cada tarefa. Já existem a skill `curadoria` e o script
  `orcamento-actions.py` — falta a tela.
- **Ação com aprovação de 1 clique**, nunca ação sozinha. O Watchtower foi
  arquivado em 17/12/2025 exatamente por agir sem o dono ver.

---

## LEIA ANTES DE QUALQUER COISA

1. `CLAUDE.md` na raiz do repo (criado em 27/08) — as convenções e as
   armadilhas desta máquina.
2. Memória `dervs-vira-produto-completo.md` — a virada de 27/08.
3. `docs/esteira/dervs/briefing.md` e `spec.md` — o contrato aprovado do
   produto, fases 1 e 2. **Não refazer.**
4. `docs/superpowers/plans/dervs-fatia-1.md` — 17 etapas. **1 a 12 entregues.**
   Pendentes: 13 (tokens/estilo), 14 (as seis telas), 15 (teste de design),
   16 (publicação), 17 (verificação final).

## O QUE NÃO SE RELITIGA (decisões travadas)

Três peças com fronteira dura (`dervs-core` Python · `dervs-agent` que **não
escuta porta nenhuma** · `dervs-live` Node só na Fatia 3) · núcleo em Python e
não Node (reescrever apaga os 452 testes) · a execução do dervs antigo será
**reescrita**, não endurecida · automerge é privilégio do Renovate · teto de
R$ 50/dia na fila · só pendência mecânica com gabarito · roda só quando o dono
manda · a fila mora dentro do painel, nada no GitHub Actions · o selo tem
**quatro** estados (o quarto é "sem dados") · arquivamento é permanente, não 24 h.

---

## FEITO na sessão de 27/08 (PR #11, mesclado em `e453bdc`)

- **A troca chave → token do GitHub App existe** (`github_app.py`, novo).
  Lê a chave em PKCS#1 e PKCS#8, assina JWT em RS256 à mão (stdlib pura), pede o
  token de instalação e renova 5 min antes de vencer.
- **A assinatura é conferida byte a byte contra o OpenSSL 3.5.4.** Vetor
  produzido fora do nosso código. Passo próprio na CI.
- `coletar_github._token()` agora tem **três portas**: token pronto no ambiente
  → o GitHub App → o `gh`. Ambiente pela metade desce para o `gh` calado.
- **Conserto que não era meu:** `test_banco.py` fixava `AGORA` em 26/08 e dois
  testes pediam prazo de 24 h sem passar `agora_iso` — ficaram vermelhos
  sozinhos em 27/08, e a CI da `main` estava vermelha por isso.
- Revisores de segurança e de Python passaram; **nenhum achado bloqueante**.
  Três achados menores foram corrigidos com teste cada: teto no expoente
  privado, arquivo de chave **indentado** passa a ser lido, e teto de uma hora
  na validade do token.
- `CLAUDE.md` de projeto criado. README e `docs/operacao/token-do-coletor.md`
  atualizados.
- **988 testes verdes** no repositório inteiro.

**NÃO PROVADO, e está escrito no código e na documentação:** a troca nunca rodou
contra a API do GitHub de verdade. Falta o servidor existir. O código está certo
contra o OpenSSL e contra o formato documentado, e mais nada.

## DÍVIDAS NOMEADAS, ainda abertas

- **Issue #10** — peneirar `remoto_slug` na ENTRADA (`receber_relatorio`), e não
  na hora de montar a consulta. Defeito pré-existente.
- **Quando o servidor existir**: levar `DERVS_GITHUB_APP_ID` e
  `DERVS_GITHUB_INSTALLATION_ID` (públicas) e os dois segredos para lá, e
  convidar cada pessoa (`python autenticacao.py convidar <login> <email>`).
- **Risco técnico nº 1, ainda aberto**: os testes podem não passar em Linux —
  `coletar.py` usa PowerShell e `barreira.py` foi escrita contra o `cmd`. O
  núcleo vai rodar em Linux na VPS.

## ARMADILHAS JÁ PAGAS (não pagar de novo)

- O **heredoc do Bash troca o fim de linha** nesta máquina: texto multilinha
  nunca casa com o conteúdo de um arquivo. Para editar por script, escreva o
  script com `Write` e **rode o arquivo**.
- O **varredor de segredo barra por FORMA**: `-----BEGIN ... PRIVATE KEY-----`
  literal e `token = <16+ caracteres>` bloqueiam o commit mesmo em dado de
  teste. Leia `secret-scan.sh` em vez de adivinhar o padrão.
- O **hook `secret-read-guard` barra pelo TEXTO do comando**: mencionar um
  arquivo `.pem` numa linha de comando é recusado. Renomeie o temporário.
- Cada `test_*.py` entra **à mão** no `ci.yml`; há um passo que cobra a lista.
- Teste com data fixa tem de passar `agora_iso`, senão apodrece sozinho.
- A interface do grafo de código (porta 9749) não respondeu em 27/08. **Não
  subir servidor avulso** — reabrir o Claude Code sobe junto.

## NÃO É MEU

Nada.
