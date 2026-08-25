# Briefing — o Claude dentro do painel

> Fase 1 da esteira. Escrito em 24/08/2026, na janela do `painel-projetos`.

## pedido_original

"QUero a versão completa desde o começo, mesmo pq o Claude estará dentro do
Painel. Irei utilizar o Claude dentro do painel para tudo, inclusive para
desenvolvimento. Não quero precisar mais ter que abrir o VSCODE pra desenvolver
com o Claude. Quero desenvolver diretamente dentro do Painel DEV. Podemos fazer
algum tipo de lousa ou um tipo de IDE nossa (tipo o lovable ou o BOLT DIY)...
algo assim... quero que dentro do painel tenha tudo do bom e do melhor. Quero
botões nos projetos do tipo 'analisar' 'desenvolver' 'resolver' etc... quero
suas melhores ideias. Quero tbm ter uma equipe de Agentes dentro do painel. Cada
um com sua função. E muito mais coisas. QUero suas ideias. Mas quero poder
clicar em um botão e o Claude resolver tudo (erros, programação, criação,
desenvolvimento, análises, etc)... quero que o Claude tenha TITAL autonomia
dentro do Painel. Tbm quero que no painel tenha terminal SSH (se fizer sentido)
para facilitar a vida do DEV."

Respostas dadas no portão de decisão, na mesma sessão:

- Primeira entrega: **um botão "Resolver" que funciona ponta a ponta**.
- Terminal: **nenhum por enquanto**.
- Autonomia: **sempre abrir um pedido de alteração**, nunca salvar direto.
- Editor: **os dois** — visualizador de mudanças com aceitar/recusar *e* editor
  de código completo, com o usuário escolhendo o modo a cada momento. Textual:
  *"Quem vai usar a aplicação sou eu e meu sócio (eu sou leigo mas ele é DEV
  experiente). Ele vai mexer bastante. Mas tbm pode escolher que vc tenha total
  autonomia e ele fique só olhando/aprovando."*

## entendimento

O HUB deixa de ser só um painel que **mostra** e passa a ser a cabine de comando
de onde o Claude Code **trabalha**: o dono clica em "Resolver" numa pendência, e
uma sessão do Claude conserta aquilo sozinha, numa cópia isolada do repositório,
terminando num pedido de alteração que ele aprova com um clique.

Não é um clone do Lovable ou do bolt.diy: aqueles rodam o código dentro do
navegador, o que não serve para projetos .NET, PHP, Docker e Postgres que vivem
no disco desta máquina. O caminho é o inverso — o painel vira a interface do
Claude Code de verdade, que já tem acesso ao disco, ao Git e ao Docker reais.

Esta primeira entrega constrói **um** botão ponta a ponta. Ele é o cano que
todas as outras ações ("Analisar", "Desenvolver", "Explicar", a equipe de
agentes, a fila de trabalho) vão reusar depois.

## usuario_alvo

**Duas pessoas, com necessidades opostas, e o produto tem de servir às duas.**
Isto é o fato mais importante deste briefing e foi descoberto só no portão.

1. **O dono.** Decide o produto, não opera terminal, não lê código. Abre o
   painel de manhã. Para ele, o sucesso é clicar num botão e receber um
   resultado em português que ele entende o suficiente para aprovar ou recusar.
   Nunca deve precisar saber o que é branch, worktree ou merge.
2. **O sócio, desenvolvedor experiente.** Vai mexer bastante e vai querer ler o
   diff de verdade, editar arquivo à mão, e às vezes só assistir e aprovar. Para
   ele, uma ferramenta que só mostra resumo em português é uma gaiola.

**A lente DX está ligada** por causa do segundo. O mesmo botão precisa render um
resumo de uma linha para o primeiro e o diff completo para o segundo, sem que
nenhum dos dois tenha de atravessar a experiência do outro.

## criterio_de_aceitacao

Verificáveis um a um, na tela ou por comando:

1. Cada pendência da caixa exibe um botão **"Resolver"** ao lado da ação atual.
2. Clicar em "Resolver" numa CI vermelha faz aparecer, na própria tela, o que a
   sessão está fazendo **enquanto acontece** — não só no fim.
3. A sessão trabalha numa cópia isolada (`git worktree`): `git status` na pasta
   original do projeto continua limpo durante e depois da execução.
4. Ao terminar bem, existe um pedido de alteração aberto no GitHub, e o painel
   mostra o link clicável.
5. O painel **nunca** salva no ramo principal por conta própria: nenhum commit
   novo aparece em `main` sem o dono clicar em aprovar.
6. Existe um botão **"Parar"** visível durante a execução, e clicar nele
   encerra o processo em até 5 segundos (verificável: o processo some da lista
   de processos da máquina).
7. O custo da execução aparece na tela em reais, ao vivo e ao final.
8. Falha é dita com o motivo real e a saída crua acessível — nunca "algo deu
   errado".
9. O resultado tem **dois modos, alternáveis por um clique**: "resumo" (uma
   frase em português por arquivo tocado, para o dono) e "diff" (o antes e o
   depois completo, para o sócio).
10. Duas execuções simultâneas no mesmo projeto são impedidas com uma mensagem
    clara, em vez de corromperem a cópia.
11. `/api/acao` continua exigindo token de sessão, Origin e Host — a superfície
    nova não afrouxa a existente.
12. As três suítes de teste continuam verdes, e a execução do Claude tem teste
    das partes puras (montagem do comando, leitura do fluxo, estados).

## fora_de_escopo

Explicitamente **não** entram nesta primeira entrega, para ninguém "aproveitar e
já fazer":

- **Terminal, SSH ou qualquer acesso ao servidor.** Decisão do dono no portão.
- **Editor de código completo.** Fica para a entrega 2, junto com o
  visualizador de mudanças editável. Nesta entrega o diff é só de leitura.
- Os botões "Analisar", "Desenvolver" e "Explicar" — reusam este mesmo cano
  depois que ele estiver provado.
- A tela da equipe de 14 agentes.
- A fila de trabalho (clicar em várias pendências e sair para almoçar).
- O briefing matinal e a detecção de divergência local × servidor (itens que
  sobraram da Fase 3 do plano original).
- Mesclar sozinho, mesmo com teste verde.

## riscos

**Altos, e três deles pedem revisor de segurança antes de mesclar.**

1. **Execução de código arbitrário a partir do navegador.** O painel hoje roda
   4 comandos de uma lista branca fechada. Passar a rodar o Claude Code é abrir
   a porta para qualquer comando. Mitigação obrigatória: continuar em
   `127.0.0.1`, manter token de sessão + Origin + Host, e o prompt do Claude
   nunca ser montado com texto que veio do navegador sem lista branca.
2. **Prompt injection vinda do próprio repositório medido.** O Claude vai ler
   README, código e log de CI de 17 projetos. Um desses arquivos pode conter
   texto se passando por instrução. Mitigação: conteúdo lido é dado, nunca
   instrução, e a sessão roda com permissão restrita ao worktree.
3. **Dado de paciente.** O `Ajudei-Saude` tem prontuário sob LGPD. Uma sessão
   autônoma nele pode ler dado real. Mitigação: exigir revisor `healthcare`
   antes de mesclar qualquer coisa nesse projeto, e o worktree nunca conter
   `.env` de produção.
4. **Custo em dinheiro real, sem teto.** Sessão que entra em laço custa até o
   dono perceber. Mitigação: teto de gasto por execução, e o botão "Parar".
5. **Migration e deploy** não entram nesta entrega, mas o cano criado aqui vai
   alcançá-los depois — o portão de risco tem de existir desde já.

Nenhum risco de pagamento nesta entrega.

## plano_de_voo

Fases 1 a 7. **Fase 3 (design) ligada**, porque há tela nova com estados
(parada, rodando, sucesso, falha, parada pelo dono) e porque os dois modos
"resumo"/"diff" são decisão visual de verdade, não enfeite.

Modo **completo** na descoberta, não enxuto: o escopo não é pequeno nem
conhecido — envolve rodar processo filho a partir de um servidor web, transmitir
saída ao vivo para o navegador, isolar em worktree e uma superfície de segurança
nova. As quatro lentes precisam rodar separadas.

Modelos por papel: Interrogador `opus` (feito). Descoberta `sonnet`, com o
Arquiteto em `opus` por causa do desenho do processo filho e do isolamento.
Síntese `opus`. Design `sonnet` com juiz `opus`. Plano `opus`. Execução `sonnet`
em worktrees isoladas. Revisão: `security` e `python` obrigatórios, `design`
para a tela — todos `opus`. Cronista `sonnet`.

**Despachos previstos: 18.**

**Impedimento conhecido, a resolver antes da fase 2:** a configuração da sessão
atual proíbe acionar subagentes sem o dono pedir com todas as letras. A esteira
depende de despacho da fase 2 em diante. Ou o dono autoriza os despachos na
abertura da próxima janela, ou as fases 2 a 6 são feitas por mim sozinho, em
sequência — mais lento e sem as lentes independentes, e isso precisa ser dito a
ele, não contornado em silêncio.
