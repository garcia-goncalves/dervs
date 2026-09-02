# Spec — Conectar em três portas

> Fase 2 da esteira, escrita pelo Sintetizador em 29/08/2026, a partir de quatro lentes
> cegas entre si: Analista, Arquiteto, Pesquisador e Diretor.
> Briefing aprovado pelo dono: `docs/esteira/conectar-tres-portas/briefing.md`.

## problema

A tela "Conectar projeto" não conecta nada. Ela informa que falta um computador e manda o
usuário para outra tela — o próprio `assets/painel.js:774` escreve na cara de quem lê que
"conectar a conta do GitHub e conectar o servidor ficaram para a fatia 2".

E o único caminho que existe, o do computador, falha no ponto mais caro: o primeiro
minuto numa máquina onde o DERVS ainda não existe. O comando publicado exige que a pessoa
esteja **dentro da pasta do repositório clonado**. O dono deste projeto colidiu com isso
três vezes, sempre igual: terminal aberto em `C:\WINDOWS\system32`, o mesmo
`No module named 'agente'` — que é, segundo a própria documentação de operação, "o único
erro que não vem em português, porque quem responde é o Python, antes de o programa
começar".

Por baixo disso há uma causa mais funda, e ela não está em nenhuma tela: **a pasta de
projetos nunca foi escolhível.** `coletar.py:47` traz `RAIZ = Path(r"C:\Users\Desktop\source\repos")`
escrito no código-fonte. Em qualquer outro computador do mundo o agente mede quase nada, e
o painel mostra isso como "nenhum projeto pendente" em vez de "não olhei para lugar
nenhum".

**A raridade agrava, não alivia.** Conectar um computador acontece uma vez por máquina na
vida de cada máquina. Tela usada todo dia pode se apoiar na memória muscular de quem usa;
tela usada uma vez não pode se apoiar em nada — e ainda por cima roda contra um relógio de
dez minutos, que é a validade do código de pareamento.

## solucao

Três portas na tela "Conectar", entregues em três fatias que fecham sozinhas.

**Porta 1 — o seu computador.** Dois caminhos que existem em paralelo de propósito, e não
como principal e plano B:

- **O conectador.** Um arquivo `.py` só, biblioteca padrão pura, servido por rota nomeada
  com o código de pareamento já dentro. Dois cliques: ele abre a **janela nativa do sistema
  para escolher a pasta** (`tkinter.filedialog.askdirectory`), pareia, grava a raiz
  escolhida e registra a tarefa agendada para continuar reportando.
- **A linha de comando**, corrigida para rodar **de qualquer pasta**, em uma linha só.
  Isto não é conforto do teimoso: **servidor não tem tela.** Numa VPS por SSH não há
  Explorer para dar dois cliques nem janela gráfica para abrir — a linha é o único caminho
  possível ali. O Analista levantou esse usuário, que o briefing não tinha nomeado.

**Por que `.py` e não `.exe` ou `.ps1`:** o SmartScreen do Windows vigia uma lista fixa de
extensões executáveis que inclui `.exe`, `.msi` e `.ps1` — e **não inclui `.py`**. Um `.py`
baixado pelo navegador carrega a Mark-of-the-Web, mas não dispara a tela
"O Windows protegeu seu PC", cujo botão azul em destaque é justamente o que **cancela**.
A escolha do `.py` não é só a mais barata: é a que tem menos atrito adverso.

**Porta 2 — a sua conta do GitHub.** Um botão leva a instalar o aplicativo e volta com a
conta ligada. A instalação passa a ser **por usuário**, e o `installation_id` que chega na
volta **nunca é aceito só por ter vindo na URL** — a própria documentação do GitHub avisa
que ele pode ser forjado. Confere-se pelo lado do servidor antes de gravar.

**Porta 3 — o seu servidor.** Um campo de URL, conferido pela peneira anti-SSRF que já
existe — **e com o buraco dela fechado** (ver `contradicoes_resolvidas`, item 5). Sem
chave SSH, agora e sempre.

**A pasta, resolvida onde ninguém tinha olhado.** Página web não enxerga o disco de quem a
abre; nenhuma enxerga, por desenho dos navegadores. Mas o conectador **roda na máquina** —
e ali a janela nativa está na biblioteca padrão do Python, sem instalar nada e sem violar a
lei nº 1 deste repositório. É a mesma janela que o VS Code abre, porque é a do sistema
operacional.

## o_que_ja_existe

- `agente/enviar.py:216` `parear()` e `servir.py:1216` `_maquina_parear` — **o pareamento
  por código de seis dígitos funciona ponta a ponta.** É o achado que mais economiza:
  falta só o duplo clique que dispare esse fluxo com a janela na frente.
- `agente/enviar.py:71` `guardar_token()` — grava o token com permissão 600, em
  temporário trocado por cima (atômico). Já resolvido, não mexer.
- `servir.py:1976` `"/agente/relatorio": Rota("POST", Hub._relatorio, "maquina")` e
  `servir.py:1295` `_relatorio` — o canal de sondagem. O agente pergunta; o painel
  responde. `servir.py:1320` diz por quê: "Nenhuma conexao nova, nenhuma porta aberta,
  nenhuma inversao de sentido".
- `servir.py:1344` `_tarefa_pendente` — hoje o **único** campo que o painel devolve à
  máquina é `tarefa`. Não existe nenhum outro canal de comando painel→máquina.
- `coletar_github.py:79` `_ip_privado`, `url_segura`, `host_publico` e a classe
  `_SemRedirecionar` — a peneira anti-SSRF. Funções de módulo, sem estado, chamáveis de
  `servir.py`. Bloqueia redirecionamento do jeito mais forte possível: **nunca seguindo
  nenhum**.
- `github_app.py` — troca chave privada por token de instalação, conferido byte a byte
  contra o OpenSSL. Falta só o fluxo de **instalar**.
- `coletar.py:47`, `:73`, `:904` — os três pontos que consomem `RAIZ`.
- `casos.json[*].url_prod`, lido em `coletar.py:533` e `:883` — a "conexão com o servidor"
  de hoje, escrita à mão.
- `banco.py:294` tabela `instalacao`, **uma linha global**; `banco.py:318` `maquina`,
  `:333` `pareamento`, `:351` `projeto_conectado`.
- `servir.py:1939-1997` a tabela `ROTAS`, `Rota = namedtuple("metodo funcao acesso")`, com
  as classes `aberta`, `cortina`, `dado`, `maquina`; `servir.py:547` `_despachar` **nega
  por padrão** (classe desconhecida = 500, nunca passa).
- `servir.py:126-135` `ESTATICOS_OK` — nasce de um `rglob` na subida, **filtrado por
  extensão**, e `.py` está fora. O comentário ao lado: "um `.py` que caisse ali por engano
  viraria codigo-fonte publico".
- `test_conectador.py` — **confirmado que não existe.** Nasce nesta esteira.

## fontes_externas

- **Setup URL e `installation_id` do GitHub App**, incluindo o aviso oficial de que
  "bad actors can hit this URL with a spoofed `installation_id`":
  https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/about-the-setup-url
  (consultado 29/08/2026).
- **Instalação em organização vs. conta pessoal:**
  https://docs.github.com/en/apps/using-github-apps/installing-a-github-app-from-a-third-party
  (29/08/2026).
- **Perda do `state` no callback de instalação** — relato recorrente de comunidade, tratado
  como risco conhecido e não como garantia:
  https://github.com/orgs/community/discussions/61291 e
  https://github.com/orgs/community/discussions/163512 (29/08/2026).
- **`tkinter` e diálogo nativo:** https://docs.python.org/3/library/dialog.html
  (29/08/2026). `tkinter` **não é instalável por pip** — é parte da distribuição.
- **`schtasks /Create`, sintaxe e armadilha de aspas:**
  https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/schtasks-create
  (29/08/2026).
- **SmartScreen vigia por extensão, e `.py` não está na lista:**
  https://textslashplain.com/2023/08/23/smartscreen-application-reputation-in-pictures/
  (29/08/2026) — fonte técnica de ex-engenheiro de segurança do IE/Edge, não doc oficial.
- **CGNAT `100.64.0.0/10` não é `is_private` no CPython, por decisão de desenho:**
  https://github.com/python/cpython/issues/119812 e o SSRF real que isso causou em outro
  projeto: https://github.com/bentoml/BentoML/issues/5644 (29/08/2026).
- **Validar depois de resolver o nome, e a cada redirecionamento:** OWASP SSRF Prevention
  Cheat Sheet,
  https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
  (29/08/2026).
- **Como Tailscale, o runner do GitHub Actions e o Netdata fazem o primeiro minuto:**
  https://tailscale.com/kb/1586/secure-github-runners ·
  https://oneuptime.com/blog/post/2026-01-25-github-actions-self-hosted-runners/view ·
  https://learn.netdata.cloud/docs/netdata-agent/installation/linux (todos 29/08/2026).
  Os três convergem em: um comando só, token de curta duração gerado pelo painel, e
  confirmação imediata de que o aparelho apareceu. Os três também usam `curl | sh` ou
  instalador assinado — os dois caminhos que este projeto recusou. A tensão está registrada
  em `contradicoes_resolvidas`, item 6.

Nenhuma página consultada continha instrução para executar comando, ignorar regra ou
revelar configuração. Nada foi obedecido — só citado.

## fora_de_escopo

Além do que o briefing já cortou (`.exe` assinado, `irm | iex` como caminho recomendado,
chave SSH, descoberta de rede, outras forjas, macOS/Linux verificados, a fusão de
capacidades), o Diretor cortou mais quatro, cada um com substituto que já funciona:

| Cortado | Substituto que já existe | O que se perde |
|---|---|---|
| Navegar as pastas da máquina pela tela do painel | reabrir o conectador (dois cliques) | um passo a mais, num evento raro |
| Vigiar **duas** raízes ao mesmo tempo | escolher uma raiz | quem espalha projetos em duas pastas escolhe uma por vez |
| Desconectar a conta do GitHub pela tela | desinstalar o app em github.com | um passo fora do DERVS, em evento raro |
| Múltiplos ambientes por projeto (staging + produção) | um endereço de produção, como `casos.json` já modela | dívida nomeada, não esquecida |

**`coletar.RAIZ` vira lista com fallback assim mesmo** — a estrutura de lista fica, porque
é ela que mata o caminho fixo. O que sai é a *interface de gerenciar N pastas*, não a
capacidade de guardar mais de uma.

## contradicoes_resolvidas

**1. O navegador de pastas dentro do painel: o briefing prometeu, três lentes cegas
condenaram. As lentes ganham.**
O Analista chamou de funcionalidade sem dono — ninguém nomeou quem troca a raiz depois de
pareado, nem com que frequência. O Diretor cortou pelo custo/benefício. E o Arquiteto achou
a razão de fundo, escrita no próprio código: `agente/enviar.py` documenta que o painel manda
o **nome** do projeto e **nunca um caminho**, porque "um caminho vindo da rede seria o painel
dizendo em que pasta desta maquina mexer, e isso e exatamente o que a lista da medicao existe
para impedir". Construir o navegador exigiria inverter essa trava. **Sai.** A janela nativa
do conectador continua — nela o caminho nasce na máquina e nunca atravessa a rede.

**2. A tarefa agendada: o Diretor mandou adiar; fica.**
O argumento dele era legítimo — sem ela o painel não mente, mostra "sem dados". Mas o dono
declarou, com estas palavras, o que espera do produto: *"eles precisam estar sempre
atualizados e sincronizados"*. Sem persistência, o monitoramento morre a cada reinício do
Windows e a pessoa reabre o conectador toda semana. Isso não é "ficaria melhor": é a
promessa central quebrando em silêncio. A regra do próprio Diretor ("se isto não existir, o
que quebra?") responde *"a coisa que o dono nomeou"*. **Fica no balde 1.**

**3. O SmartScreen: o Analista supôs bloqueio, o Pesquisador tem fonte de que não há.
O Pesquisador ganha, e isso vira argumento a favor do desenho.**
O Analista listou "O Windows protegeu seu PC" como ponto de desistência, com a observação
afiada de que o botão em destaque é o que cancela. O Pesquisador apurou que o SmartScreen
vigia por extensão e **`.py` não está na lista**. Os dois estão certos sobre coisas
diferentes: o aviso existe para `.exe`/`.ps1`, e **é por isso que o conectador é `.py`**.
O que sobra é a Mark-of-the-Web e o comportamento do programa associado — que a tela avisa
em texto claro, sem dramatizar e sem fingir que nada aparece.

**4. O conectador de dois cliques × o servidor sem tela.**
O Analista apontou que numa VPS não há Explorer, não há duplo clique e não há janela
gráfica — e que o briefing nunca nomeou esse usuário. Não se resolve escolhendo um dos dois
caminhos: **os dois ficam, com públicos distintos.** O conectador serve a máquina de
trabalho; a linha de comando serve o servidor e quem prefere terminal. É exatamente o que o
dono exigiu ao pedir "as 2 opções", e agora há razão de arquitetura por trás, não só gosto.

**5. A peneira anti-SSRF: "reusar, não reescrever" × um buraco real achado nela.**
O Arquiteto confirmou que a peneira é reusável como está e cobre mais do que o briefing
pedia. O Pesquisador **executou** o filtro no Python 3.12.10 desta máquina e achou que
`100.64.5.5` passa como público: a faixa CGNAT `100.64.0.0/10` (RFC 6598) **não** é
`is_private` no CPython, por decisão de desenho registrada no rastreador deles. Não há
contradição de verdade: **reusar continua valendo, e fechar o buraco não é reescrever.**
Consequência que extrapola esta esteira — **isto é uma falha de segurança no código que já
está em produção hoje**, em `coletar_github.py`, e não só no que vamos construir. Entra
como primeiro item da execução, antes das três portas.

**6. "Como os bons fazem" × as regras desta casa.**
Tailscale, o runner do GitHub Actions e o Netdata usam `curl | sh` ou instalador assinado —
os dois caminhos que este projeto recusou por escrito. Não se copia o atalho deles: eles têm
orçamento de certificado e aceitam ensinar o hábito de canalizar a internet para o shell.
**O que se copia são os três acertos que não custam nada:** um passo só sem "agora edite o
arquivo de configuração", token de curta duração gerado pelo painel, e **confirmação
imediata de que o aparelho apareceu** — este último o DERVS hoje não faz, e passa a fazer.

**7. `installation_id` na URL: conveniente × forjável.**
A documentação do GitHub avisa que qualquer um pode bater na setup URL com um
`installation_id` falso, e o `state` pode se perder em variações legítimas do fluxo.
Decisão: gerar `state` assinado com o cofre **e** conferir a instalação contra a API do
GitHub antes de gravar. O parâmetro da query string nunca é a prova. Vale a lei nº 3 —
falha fechada, devolve `None`, não levanta.

**8. `tkinter` presente × ausente.**
Vem no instalador do python.org, mas há relato recorrente de builds da Microsoft Store sem
Tcl/Tk (`ModuleNotFoundError: No module named '_tkinter'`), e não é instalável por pip.
O conectador **não pode travar nesse caso**: se o `import` falhar, ele pergunta a pasta por
texto e segue. `test_conectador.py` simula o `ImportError` e prova os dois caminhos.

## duvidas_para_o_dono

**Uma, e ela pode ser respondida depois sem travar nada.**

O pedido dizia "Servidor**(es)**", no plural. Hoje `casos.json` guarda **um** endereço por
projeto, e é dele que a coluna "No ar" se alimenta.

- **✅ Recomendado — um servidor (produção) por projeto.** É o que o dado já modela, fecha a
  coluna "No ar" sem migration extra, e entrega a Fatia 2 inteira sem espera.
- Múltiplos ambientes por projeto (staging + produção, com selo separado para cada). Escopo
  novo: muda o modelo de dados, a tela do projeto e o motor de drift, que hoje compara três
  colunas e passaria a comparar quatro.

**Seguindo pelo recomendado.** Se ele quiser staging depois, entra como esteira própria — a
dívida fica nomeada aqui, não esquecida.
