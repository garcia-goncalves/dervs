# Spec — DERVS

Fase 2 da esteira, escrita em 26/08/2026. Síntese de três despachos: Arquiteto (opus),
Pesquisador (sonnet) e Analista+Diretor (sonnet). O contrato desta fase é o
`briefing.md`, aprovado pelo dono; nada aqui o contradiz sem dizer que contradiz.

## problema

Quem mantém dez projetos sozinho descobre tarde. Descobre que a verificação automática
está vermelha há uma semana quando vai publicar; que o container caiu quando o cliente
liga; que o servidor roda uma versão diferente do GitHub quando o defeito "já corrigido"
reaparece. A informação existe — está espalhada por Docker, git, GitHub, servidor e
grafo de código — mas cada pedaço mora numa tela diferente, e nenhuma delas responde a
pergunta que se faz de manhã: **posso confiar no que está no ar?**

Consertar tem o problema espelhado: saber o que está errado não conserta. O dono deste
projeto não opera terminal. Hoje, entre ver o alerta e o defeito sumir, existe uma
sequência de comandos que só um programador executa.

E há uma armadilha que mata este tipo de ferramenta. A pesquisa de mercado achou o
padrão repetido: o que faz abandonar não é falta de função, é **o custo de manter o
próprio painel** — Backstage auto-hospedado é citado como exigindo de 3 a 12 engenheiros
dedicados, e a equipe de experiência do desenvolvedor da PagerDuty desistiu por isso.
A frase mais dura veio de um fórum de programadores: *"nenhum dev em sã consciência quer
um portal de desenvolvedor"*. Um segundo padrão: o Watchtower, que atualizava containers
sozinho, foi arquivado em 17/12/2025 e a comunidade migrou para uma ferramenta que **só
avisa** — o motivo citado foi "mudança silenciosa é fácil de não perceber".

Ou seja: o produto tem de ser leve de manter, e nunca agir sem o dono ver.

## solucao

DERVS é um posto de comando em `dervs.com.br` com **três peças e uma fronteira dura
entre elas**. A fronteira é o desenho principal, não um detalhe de organização: é ela
que garante que a parte perigosa nunca alcance banco nem segredo.

| Peça | Linguagem | Responsabilidade | De onde vem |
|---|---|---|---|
| **`dervs-core`** | Python | HTTP, autenticação com segundo fator, SQLite, as 16 regras, fila, custo, barreira de comando, coleta do GitHub, a tela | 100% do `painel-projetos` |
| **`dervs-agent`** | Python | Roda na máquina do usuário: git, Docker, portas, editor aberto, chaves de `.env`. **Não escuta porta nenhuma** — só faz saídas HTTPS | ~600 das 793 linhas de `coletar.py` |
| **`dervs-live`** | Node | Só a partir da Fatia 3: terminais, lousa de agentes, eventos ao vivo, bots. Processo separado, **sem acesso ao banco**, fala com o núcleo por API autenticada | `pty-sessions.js`, `public/canvas.js`, `telegram/` — **reescritos**, não portados |

**Por que Python no núcleo e não Node:** o critério de aceitação exige que os 452 testes
herdados continuem passando. Reescrever em Node os apaga, e junto vão `barreira.py` (439
linhas que já sobreviveram a um contorno real, o `git -c alias`) e a trava de diff de
`fila.py:229` — que são as duas defesas do produto contra o agente "consertar" fraudando
o próprio teste. Descartado pelo contrato, não por gosto.

**Por que o Node sobrevive numa peça só:** a Fatia 1 não tem nenhuma linha de Node. A
decisão sobre terminal (reescrever em Python com `pywinpty`/`ptyprocess`, ou manter Node)
custa zero se for adiada para a Fatia 3, e a fronteira já garante o isolamento. Se o
`pywinpty` se mostrar sólido, o `dervs-live` deixa de existir e tudo vira Python.

**As quatro regras duras da fronteira:** o `dervs-live` nunca abre o banco; nunca recebe
credencial de usuário, só um token efêmero por sessão; toda regra de negócio é Python, o
Node só transporta bytes de terminal; e na Fatia 1 ele **não entra no `docker-compose` de
produção**.

**O agente local, e o que acontece quando ele some.** O próprio envio de dados é o sinal
de vida — não há endpoint separado. Pareamento por código de 6 dígitos mostrado na tela,
válido 10 minutos, trocado por um token escopado a um usuário e uma máquina. E a regra
que impede a mentira mais provável:

| Tempo sem notícia | O que a tela faz |
|---|---|
| menos de 3 min | nada |
| 3 a 15 min | faixa amarela; dados locais acinzentados **com o carimbo da última medição** |
| mais de 15 min | as regras que dependem da máquina **calam**; as de GitHub seguem, porque o servidor as mede sozinho |
| mais de 24 h | a máquina vai para "desconectadas". Nenhum dado é apagado |

Nunca inventar "container caído" porque o agente sumiu. Ausência de agente produz
**ausência de camada**, nunca camada vazia.

**Guarda de segredo — a regra é preferir não guardar.** GitHub por App com token de vida
curta (1 hora): o que fica no banco é o número da instalação, que não é segredo. Servidor
**sem chave SSH**: o DERVS observa por HTTPS e publica por `gh workflow run`, que é o
padrão da casa. O que sobrar é cifrado em envelope de duas camadas, com a chave mestra
fora do banco e o identificador do usuário como dado associado — assim um registro
copiado de uma linha para outra falha ao abrir. A API **nunca** devolve segredo, nem para
reexibir: a tela mostra "configurado em DD/MM" e um botão "substituir".

**O selo por projeto tem quatro estados, não três.** Verde, amarelo, vermelho e
**neutro/sem dados**. O quarto é obrigatório: sem ele, um projeto sem camada coletada
apareceria verde — verde por ausência de pendência, não por saúde. É a mentira por
omissão já catalogada na memória do projeto.

## o_que_ja_existe

Caminhos reais, verificados pelo Arquiteto nos dois repositórios.

**Aproveita como está — o núcleo do produto:**

| Capacidade | Caminho |
|---|---|
| Motor puro das 16 regras | `regras.py:59-266`, `regras.py:358` `avaliar()` |
| Banco com carimbo por camada (6 tabelas) | `banco.py:32-110` |
| Vida da pendência ("aberta há 23 dias", "você fechou 6 esta semana") | `memoria.py:57,143,216,306` |
| Prontidão e projeção — a promessa "sei o que falta" | `coletar.py:529,569,637` |
| Drift de `.env` que compara **só as chaves**, nunca o valor | `coletar.py:258` `_chaves_env()`, `:294` |
| Guarda contra requisição a IP privado, no medidor de site | `coletar_github.py:65,75,99,109` |
| Motor de fila com teto diário em reais | `fila.py:78,109,148,237` |
| Trava que reprova o que o Claude fez (mexeu em teste, pôs valor no `.env.example`) | `fila.py:176,210,229` |
| Contabilidade de custo (o teto do dia enxerga fila e botão) | `execucao.py:387`, `banco.py:293,320` |
| Barreira de comando, que já sobreviveu a um contorno real | `barreira.py:131,266,345,390` |
| Padrão "o cliente manda o NOME da ação, o servidor resolve o caminho" | `servir.py:389-394` |

**Aproveita reescrevendo:** `coletar.py:303,691,709,90` (vira o agente local),
`coletar_github.py:244` (na VPS não há `gh` logado — vira GitHub App),
`execucao.py:592,737,833` (sai da máquina do dono), `servir.py:111-113` (token por boot
vira sessão com segundo fator), `index.html` (a hierarquia fica; o markup precisa de
tokens, tema claro/escuro e 360px).

**Descarta, com motivo:** `servir.py:537-748` — o proxy do grafo embutido não sobrevive à
VPS, porque o grafo é um serviço de entrada e saída locais (já registrado na memória
"o grafo morre sem stdin"); vira um dado que o agente reporta. `casos.json` e
`projects.json` — amarram o produto aos projetos dos donos. `server.js:433`
`estimateReadiness()` — pede a um modelo que estime quanto falta, enquanto
`coletar.py:529` mede; palpite com cara de dado é o pecado nº 1 da memória deste projeto.

**Do `dervs`, o que é único e não tem concorrente no painel:** terminal que sobrevive ao
recarregamento do navegador (`pty-sessions.js:157,167,218,225`); lousa de agentes
(`server.js:182-355`, `public/canvas.js`); eventos ao vivo em vez de consulta repetida
(`server.js:535,998,1137`); fila de criação escalonada que resolve a corrida de rotação
de token (`server.js:356-380`); as personas de papel, que são o melhor texto dos dois
repositórios (`pty-sessions.js:54-95`); e o aviso a cada commit por gancho de git
(`server.js:724-747`). Tudo isso é Fatia 3 ou 4.

## fontes_externas

Peças com licença que permite uso comercial, e que substituem código que íamos escrever
(consultadas em 26/08/2026):

| Peça | URL | Estrelas | Licença | Para quê |
|---|---|---|---|---|
| Beszel | github.com/henrygd/beszel | 24,7 mil | MIT | Padrão de distribuição e pareamento de agente leve |
| Uptime Kuma | github.com/louislam/uptime-kuma | 90,6 mil | MIT | Motor de checagem de disponibilidade e aviso de certificado |
| Trivy | github.com/aquasecurity/trivy | 37,6 mil | Apache-2.0 | Vulnerabilidade, segredo vazado, container |
| OSV-Scanner | github.com/google/osv-scanner | 10,9 mil | Apache-2.0 | Alternativa com menos falso positivo |
| SimpleWebAuthn | github.com/MasterKale/SimpleWebAuthn | 2,3 mil | MIT | Chave de acesso (passkey) — **porém é Node**, ver dúvidas |
| ttyd | github.com/tsl0922/ttyd | 12,3 mil | MIT | Terminal no navegador (Fatia 3); o próprio projeto avisa que autenticação básica não basta na internet |

**Não existe peça pronta para o drift entre git e o que está publicado.** O Pesquisador
procurou e só achou ferramentas de infraestrutura declarativa. **É o diferencial real do
DERVS**, e é código nosso.

Incidentes reais que fundamentam o corte da Fatia 3 (consultados em 26/08/2026):
CVE-2025-59532 no Codex CLI — o agente tratava como fronteira do isolamento um caminho
**gerado pelo próprio modelo**; CVE-2025-6514 no `mcp-remote`, nota 9,6 de 10, execução
remota por endereço forjado, 437 mil downloads afetados; levantamento da Trend Micro que
achou 492 servidores desse tipo expostos sem autenticação em julho/2025, subindo para
1.467 em abril/2026; e um contorno do isolamento do próprio Claude Code por byte nulo em
nome de máquina, corrigido em maio/2026. Fontes: sentinelone.com, thehackernews.com,
trendmicro.com, theregister.com.

Cobrança dos concorrentes: Port US$ 40/assento/mês; Cortex com mediana de US$ 75 mil/ano;
OpsLevel mediana de US$ 28,8 mil/ano — todos desenhados para dezenas ou centenas de
desenvolvedores. As ferramentas do público real do DERVS (Coolify, Uptime Kuma, Beszel)
não cobram pela versão auto-hospedada; o Coolify monetiza só a conveniência gerenciada,
a US$ 5/mês. Fonte: vendr.com, platformengineeringcost.com, temps.sh (26/08/2026).

## fora_de_escopo

Mantido o corte do briefing (lousa, Neguin, bots, botão consertar, cadastro público,
cobrança, corrigir os três `deploy.yml` alheios), **com três mudanças decididas nesta
fase**:

1. **Sai da Fatia 1 a tela de conectar conta do GitHub e servidor.** Fica só conectar
   pasta local. Motivo: essa tela coleta **segredo de terceiro**, e a decisão de
   arquitetura de segredo é portão de risco da fase 6 — construir a gaveta antes do cofre.
   Vai para a Fatia 2, junto do botão "consertar", que é quem precisa dessas credenciais.
2. **Entra na Fatia 1 a coleta de issues abertas do GitHub.** O dono pediu saber "o que
   falta" em cada projeto. O painel hoje só mede saúde operacional, não funcionalidade
   pendente. Issues reaproveita a credencial que já temos — não guarda segredo novo — e
   sem isso "o que falta" seria invenção. Estava faltando no briefing.
3. **Entra na Fatia 1 o estado neutro do selo** e o **arquivamento permanente de alerta**
   (ver contradições).

**Descartado do produto, não adiado:** o bot de WhatsApp. A biblioteca usada
(`whatsapp/bot.js:10`, `whatsapp-web.js`) é um navegador sem tela com sessão não oficial —
frágil numa VPS e contra os termos de uso do WhatsApp. Telegram continua na Fatia 4.

## contradicoes_resolvidas

**1. Analista quer mais coleta; Diretor quer menos credencial. Vence o Diretor, com
recorte.** Issues do GitHub usa a **mesma** credencial que já dá verificação, PRs e
alertas — entra. A tela que coleta credencial de servidor ou conta alheia não entra. Regra
de desempate registrada: *nenhuma coleta nova que exija guardar segredo de terceiro entra
antes da decisão de arquitetura de segredo.*

**2. Pesquisador indica o Beszel para o agente local; Arquiteto desenha um agente
próprio. Vence o Arquiteto.** O Beszel mede **infraestrutura** — processador, memória,
disco, containers. O DERVS precisa medir **projeto**: branch, trabalho não commitado,
commits não enviados, chaves de `.env`, editor aberto, quebra de linha da memória. O
Beszel não faz nada disso, e ~600 linhas do nosso agente já existem e estão testadas em
`coletar.py`. Aproveitamos dele o **padrão** de pareamento e distribuição, não o código.

**3. Pesquisador indica o Uptime Kuma; o painel já tem a regra `site_fora`. Vence o
painel, por enquanto.** O nosso já existe (`coletar_github.py:65-109`) e já nasce com
guarda contra requisição a endereço interno — que é a falha clássica de quem deixa o
usuário digitar a URL. Adotar o Uptime Kuma significaria manter um segundo serviço, e o
problema nº 1 do mercado é justamente custo de manutenção. Reavaliar na Fatia 4, quando
"avisar para fora" virar tema.

**4. Reescrever ou endurecer a camada de execução do `dervs`? Reescrever do zero.** Não
é preferência de estilo. O Arquiteto contou **12 pontos que executam comando e 11 que
escrevem em disco**, todos protegidos por uma única checagem de origem e pelo fato de o
servidor escutar só em `127.0.0.1`. Não há autenticação de usuário em lugar nenhum do
repositório. A execução arbitrária não está numa rota que dê para trancar — está no canal
de tempo real (`pty-sessions.js:238` escreve bytes crus na entrada de um `cmd.exe`). E
`server.js:772-782` **escreve um arquivo executável e o roda com texto vindo do corpo da
requisição**. Com zero testes, qualquer endurecimento seria sem rede.
**O que se copia, não se joga fora:** a fila escalonada, a lista branca de ferramentas do
chat e do Neguin, a decisão de não copiar credencial para a cópia isolada, a escrita
atômica, o `xterm.js` guardado localmente em vez de vindo de fora, e o `.gitignore`.

**5. As 16 regras: quatro treinam o dono a ignorar a lista.** `abandonado` e `caso_vazio`
não têm ação — são constatação; `grafo_velho` só sabe pedir para copiar um texto e volta a
cada 7 dias para sempre; `memoria_crlf` é convenção interna do Claude Code e não existe
para "qualquer usuário". **O defeito de fundo não é a regra, é o silenciar:** `agrupar()`
esconde por **24 horas, sempre**. Projeto que o dono arquivou de propósito volta a cutucar
todo dia, para sempre. Correção decidida: **arquivamento permanente** — "isto está certo
assim" — por regra e por projeto, e as quatro regras acima nascem fora do cálculo do selo.

**6. O `dervs` e o painel duplicam a leitura de git e GitHub. Vence o painel, sempre.**
O `dervs` chama `git` a cada visita de página e não guarda nada — a tela dele não sabe
dizer se o número é de agora ou de ontem. O painel mede em cadência e carimba a hora. No
GitHub, o painel faz **uma** consulta para todos os repositórios; o `dervs` faz duas por
repositório.

## duvidas_para_o_dono

Quatro, cada uma com recomendação marcada. As duas primeiras bloqueiam trabalho.

**1. O que roda hoje na VPS da OVH?** BLOQUEIA A PUBLICAÇÃO. Não há infraestrutura
versionada em nenhum dos dois repositórios, e ninguém acessou o servidor. Preciso saber:
qual sistema, se tem Docker, se tem porteiro de site (nginx, Caddy ou Traefik), se
`dervs.com.br` já aponta para lá, e o que mais está hospedado ali — lembrando que o
domínio é usado hoje por um projeto anterior de vocês dois.
→ **Recomendação: o dono responde na próxima janela.** Não dá para chutar.

**2. Os 452 testes passam em Linux?** BLOQUEIA A FUSÃO, e é o risco técnico número um.
`coletar.py:709` usa PowerShell; `execucao.py:805` tem ramo de Windows; `barreira.py` foi
escrita contra o `cmd`. O núcleo vai rodar em Linux na VPS. O Arquiteto foi explícito:
*"pode ser a surpresa cara desta fusão"*.
→ **Recomendação: primeira tarefa técnica da Fatia 1 — rodar os 452 testes num container
Linux, antes de qualquer código novo.** É barato e responde de vez.

**3. Qual mecanismo de login forte?** O critério exige segundo fator obrigatório, mas não
diz qual. Complicação achada nesta fase: a melhor biblioteca de chave de acesso
(SimpleWebAuthn) é de Node, e o núcleo é Python.
→ **Recomendação: chave de acesso (o desbloqueio por digital ou rosto) com código de seis
dígitos como reserva, usando biblioteca Python.** Confirmar que existe biblioteca madura é
tarefa da Fatia 1, não pergunta ao dono.

**4. Onde vivem hoje os segredos do servidor?** Preciso saber para desenhar a migração
sem duplicar segredo em dois lugares. Não li nenhum — um gancho desta máquina bloqueia, e
está certo.
→ **Recomendação: o dono diz apenas ONDE moram, nunca o valor.**

**Dois buracos menores, que não são pergunta ao dono:** varrer `public/` e `telegram/`
atrás de `dangerously-skip-permissions` antes da migração (30 segundos de busca); e
confirmar em qual máquina vive o repositório do Ajudei-Saúde, porque isso decide se aquele
drift é visto pelo agente local ou pelo servidor.

## plano_de_migracao

Preserva 100% da autoria: 69 commits de Thiago Garcia no painel, 13 de `andgoncs` na
branch `hub` do `dervs`. Técnica: subárvore de git com dois remotos — sem reescrita de
histórico, sem submódulo.

**A ordem é obrigatória.** Renomear `dervs` para `dervs-hub` cria um redirecionamento no
GitHub que **morre** quando o nome `dervs` for retomado por um repositório novo; a máquina
do André continuaria apontando para o nome antigo e passaria a enviar commits para o
repositório errado, em silêncio. Logo: (1) renomear pelo site do GitHub; (2) **o André
confirma que reapontou**; (3) só então criar o `dervs` novo. O dono avisou em 26/08 que
fala com o André e que só ele está mexendo agora.

Depois: mesclar `hub` na `main` do `dervs-hub`; clonar o painel como base do repo novo,
preservando os 69 commits; trazer o `dervs-hub` como subárvore na pasta `vivo/`; e provar
com `git shortlog -sne --all` que as duas autorias sobreviveram.

**Quatro coisas que não podem ser esquecidas:** `.gitattributes` fixando `* text=auto
eol=lf` **antes** do primeiro envio — o painel é repositório misto de quebra de linha, e a
fusão é a única chance barata de resolver; o banco no `.gitignore`; a pasta
`docs/esteira/dervs/` migra junto; e os caminhos da verificação automática ajustados no
mesmo commit da mudança de estrutura.

**Uma ordem de segurança, acima de todas:** a pasta `vivo/` traz para dentro do repositório
novo o código que abre terminal sem autenticação. Ela tem de nascer **excluída do build de
produção**, no mesmo commit em que entra. Código perigoso que chega "para organizar depois"
foi exatamente como três `deploy.yml` foram parar publicando sozinhos nesta casa.
