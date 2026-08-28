# Continue daqui — DERVS, 27/08/2026 (fim da tarde)

Pasta: `C:\Users\Desktop\source\repos\dervs` · `main @ 1e30304` · árvore limpa,
tudo no GitHub. **Nada pendente meu.** Leia inteiro antes de agir, e confirme no
código o que ele afirma.

---

## LEIA PRIMEIRO, sempre

**`docs/A-APLICACAO.md` — a fonte única.** Criado nesta sessão. Responde numa
leitura só o que o DERVS é, para quem, o que mostra, o que faz, o que nunca vai
fazer, o caminho e o que não se relitiga. **Em conflito com qualquer outro
documento do repositório, ele vence.** Também publicado como página:
https://claude.ai/code/artifact/804ce5f2-1ae9-4298-8f8c-b38de6ae58b1

Depois dele: `CLAUDE.md` na raiz (as armadilhas desta máquina) e
`docs/esteira/dervs/design.md` (669 linhas de direção visual, **aprovado, não
refazer**).

---

## O QUE FAZER: a etapa 14, e ela é a tarefa inteira

**As seis telas, em português.** É o que resolve o "está tudo feio" do dono.
O plano está em `docs/superpowers/plans/dervs-fatia-1.md`, seção 14 — leia-a
inteira, ela tem as provas e as armadilhas.

Resumo do que a etapa 14 pede:

- `index.html` **reescrito**: hoje tem 1.549 linhas e **32 cores literais**, que
  precisam virar `var(--…)`. As telas são Entrar, Painel, Projeto, Conectar
  projeto, **Computadores** e Alerta.
- `servir.py`: **uma linha** — o `ESTATICOS_OK` ganha `assets/`. Foi deixado de
  fora da etapa 13 de propósito.
- `robots.txt` novo, bloqueando `/painel`, `/projeto`, `/maquinas`, `/api`.

**As três armadilhas da etapa 14, nas palavras do plano:**

1. **Não dê a tela por pronta porque ela *aparece* certa.** Já aconteceu nesta
   casa: a faixa da fila apareceu e o botão nunca disparava. **Cada botão é
   clicado uma vez** antes de a etapa fechar.
2. **Palavra em inglês escapando** — `dashboard`, `deploy`, `loading`,
   `deletar`, `login` estão no vocabulário proibido.
3. **"máquina" agora é "computador".** Decisão de produto de 27/08: foi o
   exemplo que o dono deu de termo confuso. O `design.md` ainda diz "máquina" na
   tabela de vocabulário — `docs/A-APLICACAO.md` corrige, e ele vence.

Depois da 14 vêm a 15 (o teste dos oito itens de design, que roda na CI), a 16
(publicar) e a 17 (conferência final).

---

## FEITO nesta sessão

**1. `docs/A-APLICACAO.md`** (commit `1f5bbb2`). Três decisões de produto tomadas
junto, com motivo escrito:

- **"máquina" vira "computador"** no vocabulário fixo.
- **A tela inicial mostra UMA ação recomendada**, não a lista inteira. Lista de
  203 alertas treina o dono a fechar a aba.
- **O painel de ferramental do Claude adota o Agent Plugins 1.0.0** — padrão
  aberto publicado em 06/08/2026 por Amazon, Anysphere, Microsoft, OpenAI e
  Vercel — em vez de formato próprio. Fica na Fatia 4.

**2. Etapa 13 — a paleta e a tipografia viram código** (PR #13, mesclado em
`1e30304`). CI verde em 33s.

- `assets/dervs.css`: 45 tokens nos três blocos de tema, mais as primitivas
  (selo de quatro estados, botão, campo, cartão, lista, tabela, faixa, vazio).
- Fontes IBM Plex Sans e Mono servidas do próprio domínio, 76 KB, OFL 1.1.
- Marca: três camadas com a do meio fora de alinhamento — é o *drift*.
- `assets/CREDITOS.md` com origem e licença de tudo.

**3. O conserto que era o mais importante do PR:**
`docs/esteira/dervs/contraste.py` tinha a paleta **digitada dentro dele**,
copiada do `design.md`. No instante em que `assets/dervs.css` passou a existir,
essa cópia virou mentira em potencial — bastava mudar uma cor no CSS para o
script seguir aprovando a cor velha, **com cara de verificação**. Agora ele lê o
CSS, sai com código 1, cobra que o escuro do sistema seja igual ao escuro do
botão, e é passo da CI. **Provado ao contrário:** clareei `--texto-suave` e ele
reprovou com 2,08:1.

---

## PESQUISA JÁ FEITA — não refazer

Da sessão anterior: Backstage (auto-hospedado custa 3–12 engenheiros) · Coolify
e Dokploy · Uptime Kuma + Beszel + GlitchTip · Apache DevLake. **Confirmado: não
existe ferramenta pronta para o drift entre o git e o que está publicado** — é o
diferencial do produto.

Desta sessão: **Agent Plugins 1.0.0** (06/08/2026, cinco empresas) e
gerenciadores de skill/MCP prontos como o SkillDock — por isso o DERVS **não**
inventa formato próprio. E o consenso de 2026 para observar máquina sem expor
porta é exatamente o desenho já aprovado aqui (agente só de saída, pareado por
token): a pesquisa **confirmou**, não mudou nada.

---

## DÍVIDAS NOMEADAS, ainda abertas

- **Issue #12 (nova)** — POST que recebe 401/403 **fecha a conexão sem entregar
  a resposta**: o servidor não drena `rfile` antes de responder erro, e no
  Windows isso vira RST. Falha ~1 em 8 corridas de `test_servir.py`. É caminho
  de autenticação, mas a falha é **fechada** (o acesso é negado certo), então
  não é brecha. O conserto certo toca o despacho de **todas** as rotas POST —
  merece etapa própria com revisor de segurança. **Se a CI ficar vermelha do
  nada em `test_servir.py`, é isto.**
- **Issue #10** — peneirar `remoto_slug` na ENTRADA (`receber_relatorio`), e não
  na hora de montar a consulta. Defeito pré-existente.
- **Quando o servidor existir**: levar `DERVS_GITHUB_APP_ID` e
  `DERVS_GITHUB_INSTALLATION_ID` (públicas) e os dois segredos para lá, e
  convidar cada pessoa (`python autenticacao.py convidar <login> <email>`).
- **A troca chave → token nunca rodou contra o GitHub de verdade.** Está certa
  contra o OpenSSL e contra o formato documentado, e mais nada.

## ARMADILHAS JÁ PAGAS (não pagar de novo)

- **Verificador que guarda cópia do que verifica passa por engano.** Foi o
  `contraste.py`. Todo verificador tem de LER o artefato, e **prove ao
  contrário** antes de acreditar nele.
- **Ícone literal não se lê em 16px.** Tentei a torre de controle três vezes:
  virou abajur, depois taça. **Renderize e olhe o PNG** antes de dar por pronto.
- **O IBM Plex Sans do Google é fonte variável** — os três pesos são o mesmo
  binário (mesmo md5). Confira o md5 antes de versionar fonte.
- O **heredoc do Bash troca o fim de linha** nesta máquina. Para editar por
  script, escreva o script com `Write` e **rode o arquivo**.
- O **varredor de segredo barra por FORMA**; o hook `secret-read-guard` barra
  pelo **texto do comando** (mencionar um `.pem` é recusado).
- Cada `test_*.py` entra **à mão** no `ci.yml`; há um passo que cobra a lista.
- Teste com data fixa tem de passar `agora_iso`, senão apodrece sozinho.

## NÃO É MEU

Nada.
