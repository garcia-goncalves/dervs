# Briefing — Conectar simples, entrega C: o servidor faz, com o "Pode fazer" do dono

Esteira aberta em 09/10/2026, no ramo `feat/conectar-acoes` (parte de
`feat/conectar-servidor`, a entrega B, ainda no PR #39, que parte do #38).

## pedido_original

Do portão 1 da entrega A (09/10/2026), `docs/esteira/conectar-simples/briefing.md`:

> C = ações por lista fechada com "Pode fazer".

E, nesta sessão:

> continue de onde vc parou e faça tudo sem parar. Faça tudo vc mesmo. Abra navegadores e
> clique em tudo pra resolver tudo. te dou autorização e autonomia pra fazer tudo.

## decisoes_do_portao_1 (09/10/2026)

**Aprovação delegada**, como na entrega B. As decisões são minhas, tomadas pelo que o dono já
decidiu nas entregas A e B, e ele pode inverter qualquer uma.

- [ ] **Três ações, e só três, escritas no código do ajudante:** *reiniciar um sistema*
   (`docker restart` de um contêiner que o próprio ajudante mediu), *publicar a versão do
   GitHub* (`deploy <projeto>` do kit `deploy-padrao`) e *voltar a versão anterior*
   (`deploy <projeto> --voltar`). Sem shell, sem texto livre, sem "rodar comando". Uma ação
   nova exige versão nova do ajudante, colada de novo pelo dono.
- [ ] **A ordem é assinada pela chave de acesso do dono, e quem confere é o ajudante, no
   servidor.** O "Pode fazer" vira o pedido da digital/rosto (WebAuthn); o desafio assinado é
   o resumo da ordem (servidor, ação, alvo, número único, prazo). O ajudante guarda, na
   instalação, a chave pública do dono e confere a assinatura, a origem
   `https://dervs.com.br`, o prazo e o número único. **Quem tomasse o dervs.com.br não
   manda o servidor fazer nada** — a promessa da entrega B continua de pé para as ações.
- [ ] **Desligado por padrão.** A linha da entrega B continua "só olhar". As ações só existem
   num servidor onde o dono colou a linha **com ações** — e o ajudante, sem ela, recusa
   qualquer ordem, mesmo assinada.
- [ ] **Projeto bloqueado nunca recebe ação.** `PROJETOS_BLOQUEADOS` vale no servidor do
   DERVS **e** no ajudante (cópia conferida por teste, porque o ajudante é lido, não
   importado). O Ajudei, com dado de paciente, fica fora pelas duas pontas.
- [ ] **Sem ler log.** "Ver log" saiu da lista: log de sistema de saúde pode trazer dado de
   paciente. O resultado da ação é só "deu certo", "não deu" e o código de saída.

## entendimento

No cartão de cada sistema de um servidor ligado com ações, o dono vê "Reiniciar", "Publicar
a versão do GitHub" e "Voltar a versão anterior". Ao clicar, a tela mostra exatamente o que
vai acontecer e pede a digital (a chave de acesso); o ajudante do servidor confere essa
assinatura sozinho, faz a ação em até um minuto e conta se deu certo. Sem a digital do dono,
nada acontece no servidor — nem se o próprio site do DERVS for tomado.

## usuario_alvo

O dono (decide o produto, não opera terminal) e depois outros usuários do DERVS com servidor
próprio. Usa no dia a dia, quando o painel mostra um sistema caído ou "3 mudanças atrás do
GitHub". O único passo de terminal é colar a linha **com ações** uma vez por servidor — por
isso o roteiro `docs/operacao/ligar-um-servidor.md` ganha essa parte completa. Não é
desenvolvedor na hora de usar; a lente DX vale só para o instalador.

## criterio_de_aceitacao

- [ ] **Sem a digital, nada roda.** O ajudante recusa ordem sem assinatura, com assinatura de
   outra chave, com o desafio que não é o resumo da ordem, com origem diferente de
   `https://dervs.com.br`, vencida (mais de 5 minutos) e repetida (número único já usado).
   Prova: `test_ajudante_acoes.py` com cada um dos seis casos, e a assinatura conferida
   **contra vetor de fora** (assertion WebAuthn gerada pelo OpenSSL/`cryptography` fora do
   repositório, gravada no teste — a regra do vetor de fora).
- [ ] **Lista fechada, provada lendo o código.** O ajudante só chama três `argv` fixos
   (`docker restart <nome>`, `deploy <projeto>`, `deploy <projeto> --voltar`), com o alvo
   conferido por formato e contra o que ele mesmo mediu/conhece; nenhum `shell=True`, nenhum
   `os.system`. Prova: `test_ajudante_servidor.py`/`test_ajudante_acoes.py` leem o fonte com
   `ast` e reprovam qualquer outro jeito.
- [ ] **Desligado por padrão.** Ajudante instalado pela linha "só olhar" recusa ordem válida
   e assinada; o servidor do DERVS não mostra os botões para ele. Prova: teste nas duas pontas.
- [ ] **Projeto bloqueado fora, nas duas pontas.** Ordem para `Ajudei-Saude` (e variações de
   caixa, `_`, espaço) é recusada pelo servidor do DERVS **e** pelo ajudante, mesmo assinada.
   Prova: teste em cada ponta + teste que cobra que a lista do ajudante é igual a
   `tarefas.PROJETOS_BLOQUEADOS`.
- [ ] **O dono vê antes e depois.** A tela mostra, antes da digital, a frase exata da ação
   ("Reiniciar o sistema *x* no servidor *vps-ovh*"); depois, "pedido enviado", "feito há N
   s" ou "não deu certo (código N)". Ordem que o ajudante não buscou em 2 minutos vira
   "o servidor não pegou o pedido", nunca "feito". Prova: teste de tela em node + teste do
   fio (`test_acoes_fio.py`: pedido na tela → ordem no banco → ajudante busca, confere,
   executa com Docker falso → resultado na tela).
- [ ] **Só a conta dona.** Ordem para servidor de outra conta dá a mesma resposta de "não
   existe"; ordem só pela sessão do dono, com balcão próprio. Prova: teste de rota.
- [ ] **Sem jargão na tela.** Nada de "WebAuthn", "assinatura", "token", "contêiner",
   "docker", "deploy" ao dono. Prova: teste que lê o texto + revisor de conteúdo.
- [ ] **Nada do que funciona quebra.** Todas as suítes verdes no Windows e na CI de bancada
   em Linux (`python:3.12`), e a medição da entrega B segue igual. Prova: suíte inteira.

## fora_de_escopo

- Ver log de sistema, ler `.env`, variável de ambiente ou volume.
- Qualquer ação fora das três (parar, apagar, rodar comando, mudar configuração, mexer no
  nginx).
- Ação em servidor de revenda (TineHost) ou em computador pareado.
- Ação disparada pelo DERVS-VOZ, por regra automática ou por IA: só clique + digital do dono.
- Atualização automática do ajudante (continua proibida).
- Instalar na VPS de verdade e dar ao ajudante a permissão de rodar `deploy`: é mão do dono,
  depois de publicar (portão 4).
- Login por chave de acesso para quem não tem uma: sem chave de acesso cadastrada, a tela
  explica como cadastrar e não mostra os botões.

## riscos

- **Produção, e dado de paciente por vizinhança.** Pela primeira vez o DERVS faz algo num
  servidor de verdade, e a VPS hospeda o Ajudei. Por isso: desligado por padrão, lista
  fechada no código, projeto bloqueado nas duas pontas, assinatura conferida no próprio
  servidor e revisão de segurança obrigatória (duas passadas, como na B).
- **Criptografia escrita à mão no ajudante.** A conferência ECDSA P-256 precisa morar dentro
  do `ajudante_servidor.py` (ele é lido, não importa `p256.py`). Regra do vetor de fora vale
  sem exceção.
- **Poder de root.** `deploy` roda com `sudo`; o ajudante precisa de uma regra de `sudoers`
  restrita àquele comando, escrita na instalação **com ações**. Um erro ali é escalada de
  privilégio — entra na revisão de segurança, diretiva por diretiva.
- **Migration leve:** tabela das ordens (com dono, número único e resultado).
- **Config de deploy:** nenhuma no DERVS; a mudança na VPS é passo manual do dono.
- Nenhum pagamento.

## plano_de_voo

Modo **enxuto** (domínio conhecido, reusa o ajudante da B e a chave de acesso que já existe).
Portão 1 aprovado por delegação; portão 2 só se a descoberta achar que a chave de acesso não
serve; portão 3 não abre (direção visual aprovada); portão 4 abre só na instalação na VPS.

| Fase | Quem | Modelo | Despachos |
|---|---|---|---|
| 2 Descoberta | 4 lentes num despacho só + síntese | opus | 1 |
| 3 Design | textos e estados dos botões, sobre os tokens aprovados | sonnet | 1 |
| 4 Plano | neguin-planner | opus | 1 |
| 5 Execução | neguin-executor por arquivo: ajudante, servidor+banco, tela | sonnet | 3 |
| 6 Revisão | security (2 passadas), python, conteúdo | opus/sonnet | 4 |
| 7 Cronista | eu | — | 0 |

**Total previsto: ~10 despachos.**

## decisoes_do_portao_2 (09/10/2026, depois da descoberta)

Aprovação delegada, como no portão 1. Estas decisões **vencem** as do portão 1 onde divergem.

- **"Publicar a versão do GitHub" sai desta entrega.** O `deploy` do kit `deploy-padrao`
  só publica o pacote `.tar.gz` que o VS Code envia; sem ele, sai 1. Ficam duas ações:
  reiniciar e voltar. Publicar pelo painel vira entrega própria (o servidor baixa o commit do
  GitHub com permissão de leitura guardada na VPS pela mão do dono).
- **A promessa fica honesta.** WebAuthn não mostra no aparelho o que está sendo assinado: quem
  tomasse o dervs.com.br poderia trocar a ordem na hora do toque. O que vale: **sem um toque
  do dono, nada acontece**; com o site tomado, cada toque vira no máximo UMA ordem da lista
  fechada (reiniciar ou voltar um projeto liberado), teto de 6 por hora no ajudante, nunca
  projeto bloqueado, nunca comando. A tela diz isso em "O que isso faz?". Fechar o buraco de
  vez (aprovar também no DERVS-VOZ) é outra entrega.
