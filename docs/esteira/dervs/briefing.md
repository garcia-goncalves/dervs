# Briefing — DERVS

Fase 1 da esteira. Escrito em 26/08/2026 pelo Interrogador, a partir de duas rodadas de
perguntas ao dono.

## pedido_original

> No começo, pedi somente pra criar o painel pra me ajudar a ter uma visão como um todo de
> todos os meus projetos. Agora, eu gostaria que não fosse apenas um Painel pra me ajudar,
> mas sim uma aplicação. Como se fosse uma aplicação para se tornar um produto no mercado.
> Quero que você faça uma varredura na internet e em todos os repositórios do github pra
> trazer as melhores ideias de como podemos criar a aplicação perfeita para DEVS. Precisa
> ser focada em desenvolvimento/programação/criiação de apps, aplicações, sites, jogos,
> etc... tudo... e também análises, testes e manutenção dos projetos. Quero tudo integrado
> na aplicação (CBM, Docker, Servidor, Github, etc)... podemos usar aplicações opensource
> dos melhores repos do github. Quero que tenha tudo o que um dev precisa. Quero que seja
> bem inteligente e automatizada/automática/autonomo. Quero que tenha dashboard para o
> usuário bater o olho e saber o que está acontecendo em cada projeto. Quero que o Claude
> Code está integrado e cuidando de tudo. Quero um grupo de Agentes especializados cada um
> em uma coisa diferente. Quero tudo bem organizado e inteligente. Quero que entendam meus
> pedidos e me façam todas as perguntas possíveis antes de fazer qualquer coisa. Quero
> assertividade. Quero agilidade. Me diga quais são suas melhores ideias. Me diga o que vc
> acha que podemos criar... aproveite e atualize os documentos com base em como está o
> painel atualmente. Também precisamos criar a identidade visual (pensei em preto, branco e
> verde, pra ficar com cara de DEV/Hacker). Aceito suas sugestões. Quero entrar na aplicação
> diariamente e saber que tudo está ok (local, servidor, github, etc). Quer tb saber quais
> projetos estão funcionando 100% e quais estão em desenvolvimento e o que faltam fazer.
> Quero apertar poucos botões e ver o claude fazendo tudo o que faltar. Quando houver erros
> eu tbm quero apertar poucos botões e ver o claude corrigindo tudoo. 100% tudo.

Respostas das duas rodadas de perguntas, literais:

- Ambição: *"A principio será apenas para eu e meu sócio (mas quero que já tenha cara de
  produto. Não quero que seja engessado. Quero que tenha as configurações que o usuário
  precisa (qualquer usuário). Por exemplo, conectar a pasta do repo local, conectar conta do
  github, conectar servidor, etc. Não quero que faça a aplicação somente para funcionar os
  meus projetos. Quero que qualquer pessoa possa usar com seus próprios projetos."*
- Onde roda: *"A aplicação/painel será hospedado em um domínio meu chamado dervs.com.br e
  será hospedado na minha VPS da OVH. (...) quero ver a possibilidade de fazermos uma fusão
  do que está no https://github.com/garcia-goncalves/dervs junto da nossa aplicaçáo atual
  (painel). Gostaria que vc unisse os dois e transformasse apenas em DERVS (dervs.com.br)."*
- Autonomia: *"Conserta e abre pedido; você aprova com 1 clique."*
- André: *"Já conversamos, pode seguir."*
- Acesso: *"Só você e o André, por login forte."*
- Repositórios: *"o repo atual DERVS poderia chamar dervs-hub pois o nov eu queria que se
  chamasse dervs."*

## entendimento

DERVS é um posto de comando para quem programa: uma aplicação em `dervs.com.br` onde o dono
bate o olho e sabe, de cada projeto, se está saudável, o que falta e o que quebrou — juntando
o que hoje está partido em dois repositórios, o `painel-projetos` (que sabe *o que está
errado*: Docker, git, GitHub, grafo de código, 16 regras, motor de fila, controle de custo) e
o `dervs` (que sabe *consertar e mostrar*: terminais Claude reais no navegador, lousa de
agentes, o Neguin autônomo, avisos por WhatsApp e Telegram).

O produto se sustenta em três promessas, nesta ordem: **eu confio no que está no ar**,
**eu sei o que falta**, e **eu aperto um botão e o Claude conserta**. Nada é amarrado aos
projetos do dono: qualquer pessoa conecta suas próprias pastas, sua conta do GitHub e seu
servidor pela tela de configuração.

Este briefing cobre o produto inteiro, mas o `criterio_de_aceitacao` abaixo é o da **Fatia 1
— a fundação**, porque tudo o que vem depois depende dela estar de pé e segura.

## usuario_alvo

Desenvolvedor — **a lente DX se aplica em cheio**. Dois perfis:

1. **O dono (Thiago) e o sócio (André), diariamente, de manhã.** Thiago decide o produto e
   não opera terminal: a tela precisa responder "está tudo ok?" sem que ele leia um log. André
   programa e vai querer o terminal e a lousa. A mesma tela serve os dois em profundidades
   diferentes: selo na frente, prova atrás.
2. **O dev solo ou a dupla, com muitos projetos parados, que virá depois.** Chega porque
   perdeu tempo descobrindo tarde que um container caiu, que a CI está vermelha há uma semana
   ou que o servidor roda versão diferente do GitHub. Não tem time de plataforma: se a
   ferramenta pedir manutenção, ele desinstala.

Momento de uso dominante: **cinco minutos, de manhã, antes de começar.** Um segundo momento,
menos frequente e mais longo, é o de conserto — quando algo está vermelho e ele quer apertar
poucos botões e ver o Claude resolver.

## criterio_de_aceitacao

Fatia 1 — a fundação. Cada item é verificável por comando, teste ou olhada na tela.

**Segurança (a fatia não entrega sem estes cinco):**
- `curl -si https://dervs.com.br/api/projetos` sem sessão devolve 401 ou 302, nunca dado.
- Conta sem segundo fator configurado não alcança nenhuma rota de dados: teste automatizado
  prova o 403.
- O cadastro público está desligado: `POST /api/registro` devolve 403 e existe teste que
  prova.
- Nenhuma rota expõe terminal, PTY ou execução de comando nesta fatia: teste varre as rotas
  registradas e falha se encontrar qualquer uma.
- O `grep -r "dangerously-skip-permissions"` no código publicado não retorna nada.

**Função:**
- O agente local, rodando na máquina do dono, aparece na tela com "visto por último" abaixo
  de 2 minutos.
- Cada projeto mostra um selo verde, amarelo ou vermelho, e clicar abre a conta que gerou o
  selo (CI, publicação por botão, drift, segredo, teste).
- O drift entre servidor e GitHub aparece corretamente para pelo menos um projeto real —
  o Ajudei-Saúde tem 10 commits não publicados desde 11/08/2026 e precisa aparecer vermelho
  nesse quesito.
- Conectar um projeto novo é feito **pela tela**, não editando arquivo: escolher pasta local,
  conta do GitHub e servidor. Provado abrindo a tela e conectando um repositório qualquer.
- Os 452 testes herdados do `painel-projetos` continuam passando, rodados **duas vezes
  seguidas** (a segunda corrida pega teste que lê banco real e passa por sorte).
- A CI do repositório novo fica verde no GitHub.

**Tela:**
- Nenhum texto em inglês visível.
- Em 360px de largura, o selo de cada projeto é legível sem rolagem horizontal.
- A tela funciona nos dois temas do sistema (claro e escuro) sem cor definida só dentro de
  um deles.

## fora_de_escopo

Não entra na Fatia 1, e ninguém deve "aproveitar e já fazer". Cada item tem a fatia em que
entra:

- **Lousa de agentes e terminais no navegador** — Fatia 3. Depende de o modelo de segurança
  estar provado, e é a parte mais perigosa do produto.
- **Neguin autônomo** — Fatia 3.
- **WhatsApp e Telegram** — Fatia 4.
- **Botão "consertar" ligado ao Claude** — Fatia 2. A Fatia 1 mostra o problema; consertar vem
  depois de confiar na leitura.
- **Cadastro público, cobrança, isolamento entre contas de terceiros, cota por usuário** —
  não tem fatia marcada. A estrutura multiusuário nasce pronta, a porta nasce fechada.
- **Corrigir os três `deploy.yml` que publicam sozinhos** (`medconsultoria`, `ccvp-painel`,
  `zacareli`) — é trabalho da janela de cada projeto, não desta esteira. O DERVS vai
  *apontar* o problema, não consertá-lo.
- **Atualizar a documentação do `painel-projetos` para o estado atual** — pedido do dono, mas
  fica para a fase 7 desta esteira, quando já se souber se o repositório sobrevive.

## riscos

Três dos quatro tipos de risco da esteira estão presentes. Dado de paciente **não** está.

- **Produção e config de deploy.** O DERVS vai morar numa VPS pública com domínio próprio.
  Publicação e configuração de servidor exigem portão de risco na fase 6.
- **Segredo.** A aplicação vai guardar credencial de GitHub e de servidor de quem a usar. É a
  primeira vez que um projeto desta casa guarda segredo de terceiro. Onde o segredo mora e
  como é cifrado é decisão de arquitetura, não de implementação.
- **Execução remota de código.** O `dervs` de hoje abre terminais Claude com
  `--dangerously-skip-permissions` e foi escrito sob a premissa, literal no README dele, de
  rodar só em `127.0.0.1`. Publicá-lo como está em domínio público seria abrir um shell na
  internet. Por isso a Fatia 1 proíbe qualquer rota de execução, e a lousa só volta na Fatia
  3, com modelo de segurança próprio.
- **Trabalho ativo de terceiro.** A branch `hub` do `dervs` tem commits do André até
  22/08/2026 e o repositório recebeu envio em 26/08/2026 às 02:08. O dono confirmou que já
  conversaram, mas o histórico e a autoria dele precisam ser preservados na fusão.
- **Armadilha de renomeação.** Renomear `dervs` para `dervs-hub` cria um redirecionamento no
  GitHub que **é apagado** quando um repositório novo tomar o nome `dervs`. A máquina do André
  continuaria apontando para o nome antigo e passaria a enviar commits para o repositório
  errado, em silêncio. Ordem obrigatória: renomear, o André reapontar o remoto, e só então
  criar o `dervs` novo.

## plano_de_voo

**Fases ligadas:** 1 a 7, com a fase 3 ligada — há interface, e a identidade visual (preto,
branco e verde) é entrega explícita do dono.

**Modo:** completo na fase 2. O escopo é grande, atravessa dois repositórios em duas
linguagens, e três das quatro lentes têm trabalho de verdade a fazer — o Arquiteto precisa
mapear o que se aproveita de 5.500 linhas de Python e ~115 mil caracteres de JavaScript, o
Pesquisador precisa da varredura de mercado que o dono pediu, e o Diretor precisa cortar
escopo com faca. Modo enxuto aqui economizaria pouco e custaria a qualidade do corte.

**Modelos por papel:** Interrogador `opus` (feito). Fase 2: Analista `sonnet`, Arquiteto
`opus` (é o papel que decide a fusão), Pesquisador `sonnet`, Diretor `opus` (corte de
escopo), Sintetizador `opus`. Fase 3: Diretor de arte `sonnet`, Redator `sonnet`,
Estrategista `sonnet`, juiz `opus`. Fase 4: `neguin-planner` em `opus`. Fase 5:
`neguin-executor` em `sonnet`, em worktrees isoladas. Fase 6: revisores `python-reviewer`,
`typescript-reviewer`, `security-reviewer` e `design-reviewer`; o de segurança em `opus`, por
causa do risco de execução remota. Fase 7: Cronista `sonnet`.

**Despachos previstos: 22.** Fase 2: 5. Fase 3: 3. Fase 4: 1. Fase 5: 6. Fase 6: 6. Fase 7: 1.

**Portões previstos:** o 1 (este briefing), o 3 (escolha visual entre direções de preto,
branco e verde) e o 4 (risco: publicação em VPS pública e guarda de segredo). O portão 2 só
abre se a fase 2 devolver decisão de produto pendente.

**Onde o estado mora:** `docs/esteira/dervs/` dentro do `painel-projetos` até o repositório
novo existir; migra junto com o resto na fase 5.
