# Design — entrega B: o ajudante no servidor

Fase 3, 09/10/2026. Sem portão visual: tudo cabe na direção já aprovada.

## direcao_visual_escolhida

**Torre de Controle**, a de `docs/esteira/dervs/design.md`, sem mudança. O cartão "Seus
servidores" segue o molde dos cartões da entrega A (`docs/esteira/conectar-simples/design.md`):
um botão principal, uma frase do que está ligado, o detalhe fechado em "o que isso faz?".
Recusadas: (a) tela própria "Servidores" no menu — o menu tem exatamente quatro itens e
`test_menu.py` cobra; (b) terminal embutido mostrando a saída do servidor — o terminal mora
só no DERVS-VOZ, por decisão antiga.

## tokens

Nenhum token novo. Usa os de `assets/painel.css`: superfície de cartão, texto secundário
para o carimbo "medido há", a cor de estado ok/alerta/sem dados já usada no selo, fonte
monoespaçada só no bloco da linha para colar (que rola na horizontal dentro do próprio
bloco, nunca a página).

## telas

**Conectar → cartão "Seus servidores"** (abaixo de "Seus sites"):
- *Vazio:* frase + botão "Ligar um servidor".
- *Ligando:* bloco com a linha (monoespaçada, rolagem própria), botão "Copiar", roteiro em
  quatro passos, "o que isso faz?" fechado. Carregando a linha: "Preparando a linha…".
  Erro ao buscar: frase nossa + "Tentar de novo"; 403 de página velha usa a faixa central
  `PAGINA_VELHA`.
- *Ligado:* por servidor, nome, "medido há N s" ou "Sem dados há N min" (passados 180 s),
  e a lista "Sistemas rodando neste servidor": nome, "de pé" / "parado" / "reiniciando",
  "desde <quando>", "reiniciou N vezes" (só se N > 0). Sem docker: "Não consegui ver os
  sistemas deste servidor."
- *360px:* uma coluna; a linha para colar rola dentro do bloco; o botão Copiar fica acima
  dela, largura cheia.

**Cartão do projeto (painel):** uma linha por servidor onde o projeto foi achado, só
quando há dado: "No ar em <servidor>: versão de <data>" + o veredito. Projeto sem
servidor ligado não ganha linha nenhuma (nada de "não sei" em todo cartão).

## textos

- Título do cartão: **Seus servidores**
- Vazio: "Ligue um servidor para ver, por dentro, o que está rodando nele e qual versão de
  cada projeto está no ar. O DERVS só olha: não muda nada lá."
- Botão: **Ligar um servidor**
- Roteiro:
  1. "Abra o terminal do servidor (o PuTTY ou o terminal do DERVS-VOZ) e entre como de
     costume."
  2. "Cole a linha abaixo e aperte Enter. Ela pode pedir a sua senha do servidor."
  3. "Vai aparecer um código de 8 letras. Abra esta mesma tela no seu computador, clique em
     Autorizar e digite o código."
  4. "Pronto: em até um minuto o servidor aparece aqui."
- Se der errado: "Apareceu `python3: command not found`? O servidor não tem Python. Cole
  `sudo apt install -y python3` e rode a linha de novo." · "Apareceu `FAILED` ou
  `soma de verificação`? O arquivo chegou diferente do esperado. Não rode nada: recarregue
  esta página e copie a linha de novo."
- "O que isso faz?": "A linha baixa um programa pequeno do dervs.com.br, confere que ele
  chegou inteiro e o instala no servidor. A cada 30 segundos ele conta ao DERVS quais
  sistemas estão rodando, desde quando, e qual versão foi publicada por último. Ele nunca
  lê senhas, arquivos de configuração nem os dados dos sistemas, não recebe ordens e não
  se atualiza sozinho. Para ver o Docker ele precisa de poder de administrador no servidor:
  por isso roda separado, num usuário só dele, e só com leitura. Para tirar: cole
  `sudo python3 /opt/dervs-ajudante/dervs-ajudante.py remover`."
- Ligado: "medido há 12 s" · "Sem dados há 4 min — o servidor parou de contar."
- Estados do sistema: "de pé" · "parado" · "reiniciando" · "com problema" (saúde `unhealthy`).
- Veredito no projeto: "igual ao GitHub" · "3 mudanças atrás do GitHub" · "diferente do
  GitHub" · "não sei qual versão está no ar".
- Tela de Autorizar, quando o pedido é de servidor: "Um servidor chamado **<nome>** quer
  se ligar à sua conta. Ele só vai olhar."
- Dados de demonstração (local): servidor `vps-ovh`, sistemas `dervs-app` (de pé, desde
  ontem), `grimoire-web` (de pé), `ajudei-db` (reiniciou 2 vezes), versão `96eb3fc`.

## assets

nenhum — nenhuma imagem nova; o cartão é só texto e os ícones de estado que já existem.
Nenhuma foto realista falta.

## estrategia_de_aquisicao

Tela interna, atrás de login, fora de busca (`robots.txt` já recusa). Sem meta tag nova. O
próximo passo da tela é sempre um só: sem servidor, "Ligar um servidor"; ligado, olhar o
painel, onde cada projeto passa a dizer qual versão está no ar.
