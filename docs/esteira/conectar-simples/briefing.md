# Briefing — Conectar simples: computador, GitHub e servidor em um clique cada

Esteira aberta em 09/10/2026. Fase 1, aguardando o portão 1 (aprovação do dono).

## pedido_original

> sim, conserte e corrija tudo e qualquer coisa que precise ser feito. Quero o melhor. Quero
> que a parte de CONEXÔES (projetos no PC/LOCAL, GITHUB E SERVIDOR) sejam facilitados e fácil
> de entender. Está muito confuso e dificil. Quero algo mais simples e fácil de usar. A conexão
> local/pc dos projetos por exemplo, queria que tivesse por exemplo apenas um botão que eu
> clique, abra o pop-up para eu escolher a pasta do projeto... e então, abrir a pasta dos
> projetos no DERVS com todos os projetos locais... algo assim... quero suas melhores ideias.
> Critique minhas ideias e proponha o melhor... para conectar ao github (conta pessoal,
> organização, etc) tbm precisa ser facilitado e para conectar ao servidor tbm... bem
> facilitado e preciso.

Mais o conserto pedido na mensagem anterior: a frase "não consegui procurar agora" esconde o
motivo real quando a página está velha (403 "token vencido").

## decisoes_do_portao_1 (09/10/2026, conversa com o dono)

Estas decisões **vencem** o resto deste briefing onde houver conflito.

1. **Três entregas.** A = tela nova + página desatualizada + computador + GitHub com contas
   e repositórios à escolha. B = ajudante (agente) no SERVIDOR, modo "só olhar", tempo real,
   ligado aos projetos e ao GitHub (commit no ar por projeto). C = ações no servidor por
   lista fechada (reiniciar, publicar, voltar versão), sempre com "Pode fazer", "só olhar"
   como padrão por servidor. Esta esteira cobre a **A**; B e C abrem briefing próprio.
2. **Servidor: ajudante, nunca chave guardada no site.** O dono perguntou se ajudante + chave
   SSH seria mais preciso: não é (a chave vê o mesmo que o ajudante) e transforma o site em
   chave mestra de todos os servidores (a VPS tem o Ajudei, dado de paciente). A chave fica
   só no PC do dono, pelo DERVS-VOZ (terminal de emergência). Revenda (TineHost) fica só
   com medição por endereço.
3. **Computador: ARQUIVO BAIXADO é o caminho principal** (dono preferiu a colar comando).
   Dois cliques, sem exigir Python (o ajudante traz o que precisa), janela do Windows para
   escolher a pasta, "Autorizar" no navegador (sem código de 6 dígitos dentro do arquivo),
   e a tela acompanha ao vivo ("instalado → pasta escolhida → N projetos"). Linha de comando
   fica escondida em "Prefiro colar um comando". Nada pode assustar: imagem por passo,
   português claro, "o que isso faz?" aberto a quem quiser conferir.
4. **Aviso do Windows (SmartScreen) é medido antes de construir**, no PC do dono, com arquivo
   marcado como baixado (ZoneId=3). Se aparecer a tela azul, a tela do DERVS avisa antes com
   imagem, e o certificado de assinatura (R$ 1-2 mil/ano) vira decisão de custo do dono.
   **MEDIDO em 09/10/2026 no PC do dono** (Windows 11 Pro, Smart App Control desligado,
   arquivos com ZoneId=3): NENHUM deu a tela azul. `.cmd` → "Abrir Arquivo - Aviso de
   Segurança", escudo VERMELHO, "O fornecedor não pôde ser verificado... [Executar]".
   `.vbs` → mesmo diálogo, escudo AMARELO, "Deseja abrir este arquivo? [Abrir]" (mais
   suave). **Escolha: `.cmd`** — o VBScript está sendo removido do Windows pela Microsoft
   (recurso sob demanda, desligado por padrão nas próximas versões); o arquivo pararia de
   abrir sozinho. A tela do DERVS mostra a imagem do aviso do `.cmd` antes do download
   ("o Windows vai perguntar; clique em Executar"). **Não medido ainda:** o aviso do
   PRÓPRIO Chrome no download de `.cmd` (só com arquivo servido pelo dervs.com.br de
   verdade) — conferir na entrega A antes de dizer pronto.
5. **GitHub:** quantas contas quiser (pessoal e organização) e, em cada uma, "Escolher
   repositórios" abre a página certa do GitHub; chave "acompanhar" por repositório no DERVS.

## entendimento

A tela Conectar vira três cartões, um por ligação (Este computador, GitHub, Seus sites), cada
um com **um** botão principal, uma frase do que está ligado e o que falta, e nada de jargão.
O computador se liga baixando um arquivo que já traz tudo dentro: dois cliques, a janela do
Windows para escolher a pasta, e a tela do DERVS se atualiza sozinha mostrando a lista de
projetos achados. O GitHub e o servidor seguem a mesma regra de um botão, e toda recusa da
página velha diz "recarregue" com um botão para isso.

## usuario_alvo

O dono (não-desenvolvedor no terminal, decide o produto) e, em seguida, outros usuários do
DERVS. Usa a tela uma vez por computador, por conta do GitHub e por servidor, e volta a ela
quando algo some do painel. É desenvolvedor de produto, mas **não** opera terminal: a lente DX
do Analista vale para o conectador, não para a tela.

## criterio_de_aceitacao

1. **Computador em um botão.** A tela tem um único botão "Conectar este computador". Ele baixa
   um arquivo que já traz o endereço, o código de pareamento **e o programa que mede** (sem
   exigir o repositório do DERVS clonado nem a linha com `<CAMINHO DO DERVS>`). Prova:
   `test_conectador.py` roda o arquivo baixado numa pasta vazia, sem o repositório, e ele
   pareia e agenda a medição.
2. **A tela percebe sozinha.** Com a tela Conectar aberta, depois do pareamento o cartão muda
   para "Conectado — achei N projetos" em até 15 segundos, sem recarregar, e lista os projetos
   achados (nome e pasta). Prova: clicando, no localhost, com um computador pareado de teste.
3. **Escolher o que aparece.** Cada projeto achado tem uma chave "mostrar no painel"; desligar
   esconde o projeto do painel daquela conta e sobrevive a uma nova medição. Prova: teste de
   rota + clique.
4. **GitHub em um botão.** Um botão "Conectar conta do GitHub" serve para conta pessoal e para
   organização; ao voltar do GitHub (ou ao abrir a tela) a procura de contas roda sozinha, e
   o botão "Procurar minhas contas" deixa de existir. Cada conta aparece com o nome, se é
   pessoal ou organização, quantos repositórios mede e quando mediu. Prova: teste da rota de
   volta + clique.
5. **Servidor em um campo.** "Adicionar site": cola-se o endereço, o DERVS mede na hora e diz
   "respondeu" ou o motivo de não responder, antes de gravar. Endereços que os projetos já
   declaram aparecem como sugestão de um clique. O padrão de subdomínio sai da frente e fica
   num "opções avançadas" fechado. Prova: teste de rota + clique.
6. **Página velha diz o que fazer.** Toda recusa 403 por token vencido, em **qualquer** botão
   do painel, mostra "Esta página ficou desatualizada" com um botão "Recarregar". Prova:
   `test_*_tela` executando a função em node com resposta 403 falsa.
7. **Sem duplicata e sem jargão.** A tela Conectar não repete "Conectar um computador" em dois
   lugares, não mostra "agente", "Git", "token", "linha de comando" nem "instalação" ao dono
   (o caminho da linha de comando fica dentro de "opções avançadas"), e o histórico de recados
   do DERVS-VOZ não ocupa a tela Conectar. Prova: teste que lê o texto da tela + revisor de
   conteúdo.
8. **Nada do que funciona hoje quebra.** As 26+ suítes verdes na CI, o computador já pareado
   continua medindo, as duas contas do GitHub continuam ligadas, o servidor cadastrado
   continua medido. Prova: CI verde + conferência no ar depois de publicar.

## fora_de_escopo

- Ler a pasta do computador **pelo navegador** (a ideia literal do dono; o motivo está na
  crítica, na mensagem do portão).
- Instalador `.exe` ou programa sem Python (precisaria de ferramenta de empacotamento e de
  assinatura digital; vira pergunta própria se o Python for barreira para outros usuários).
- Desconectar o GitHub pela nossa tela (decisão antiga: revogar mora do lado de quem dá).
- Revalidar periodicamente a posse de organização (dívida nomeada de 06/10, segue aberta).
- Pedir chave de acesso ao servidor (SSH). O servidor continua medido só pelo endereço público.
- Mudar o menu de quatro itens.

## riscos

- **Código que roda no computador do dono.** O arquivo baixado passa a levar o programa de
  medição e agenda a execução dele a cada login: tem de ser montado pelo próprio servidor a
  partir do código publicado, nunca de fora. Revisão de segurança obrigatória.
- **Produção.** A mudança só vale depois de publicar pela tarefa do VS Code, que é mão do dono.
- **Migration leve** se a chave "mostrar no painel" virar coluna nova (tabela de projetos).
- Nenhum dado de paciente, nenhum pagamento.

## plano_de_voo

Modo **enxuto** (domínio conhecido, tela que já existe). Fases e despachos previstos:

| Fase | Quem | Modelo | Despachos |
|---|---|---|---|
| 2 Descoberta | 4 lentes num despacho só + síntese minha | opus | 1 |
| 3 Design | redator + diretor de arte num despacho, sobre os tokens já aprovados (Torre de Controle) | sonnet | 1 |
| 4 Plano | neguin-planner | opus | 1 |
| 5 Execução | neguin-executor: computador/conectador, GitHub, sites + tela | sonnet | 3 |
| 6 Revisão | security, python, design, conteudo em paralelo | sonnet/opus | 4 |
| 7 Cronista | eu | — | 0 |

**Total previsto: ~10 despachos.** Portão 3 (visual) não abre: a direção visual já foi
aprovada em `docs/esteira/dervs/design.md`. Portão 4 (risco) abre uma vez, antes de publicar.
