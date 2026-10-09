# Briefing — Conectar simples, entrega B: o ajudante no servidor, só olhando

Esteira aberta em 09/10/2026, no ramo `feat/conectar-servidor` (parte de
`feat/conectar-simples`, a entrega A, ainda no PR #38).

## pedido_original

Do portão 1 da entrega A (09/10/2026), `docs/esteira/conectar-simples/briefing.md`:

> B = ajudante (agente) no SERVIDOR, modo "só olhar", tempo real, ligado aos projetos e ao
> GitHub (commit no ar por projeto).

E, nesta sessão:

> continue e faça tudo o que vc sugerir de melhor. Faça tudo sem parar! Seja autonomo.

## decisoes_do_portao_1 (09/10/2026)

**Aprovação delegada.** O dono pediu autonomia total nesta sessão; as decisões abaixo são
minhas, tomadas pelo que ele já decidiu na entrega A, e ele pode inverter qualquer uma.

- [ ] **Nunca chave SSH guardada no DERVS** (decisão dele, entrega A). O ajudante entra no
   servidor por **uma linha colada uma vez** no terminal do servidor, e pareia pelo mesmo
   "Autorizar" no navegador da entrega A. Quem cola é o dono (PuTTY ou o terminal do
   DERVS-VOZ); o DERVS nunca alcança o servidor por conta própria.
- [ ] **Só olhar, de verdade.** O ajudante do servidor é uma máquina `so_mede`: o pacote não
   leva o executor e o servidor recusa ligar execução nela (as duas trancas que já existem).
   Ele não pergunta por tarefa, não recebe recado, não abre porta. Ações (reiniciar,
   publicar, voltar versão) são a entrega C.
- [ ] **Não se atualiza sozinho.** O programa fica fixo no que foi instalado; versão nova
   exige colar a linha de novo. Senão quem tomasse o dervs.com.br tomaria todo servidor
   ligado a ele na atualização seguinte.
- [ ] **Lê só campos escolhidos, nunca o ambiente dos contêineres.** `docker inspect` traz
   as variáveis de ambiente, que são os segredos de cada sistema (a VPS roda o Ajudei, com
   dado de paciente). O ajudante pede ao Docker uma lista fechada de campos, e o servidor
   do DERVS recusa campo fora dela.
- [ ] **"Tempo real" = a cada 30 segundos**, empurrado para a tela aberta pelo fluxo que já
   existe (`/api/eventos`). Não é instantâneo, e a tela diz "medido há N s".

## entendimento

Uma linha colada uma vez no terminal do servidor instala um ajudante que só olha. A cada 30
segundos ele conta ao DERVS o que está rodando ali — cada sistema, se está de pé, desde
quando, e qual versão (commit) está no ar. O DERVS cruza isso com o GitHub e mostra, no
cartão de cada projeto, "no ar: versão de ontem, 3 mudanças atrás do GitHub" ou "no ar está
igual ao GitHub".

## usuario_alvo

O dono (decide o produto, não opera terminal) e depois outros usuários do DERVS. Usa a tela
Conectar uma vez por servidor, para pegar a linha e autorizar; depois olha o painel todo
dia. Colar a linha no servidor é o único passo de terminal, e por isso o roteiro tem de ser
completo (onde colar, o que aparece, o que fazer se der errado). A lente DX do Analista
vale para o instalador, não para a tela.

## criterio_de_aceitacao

- [ ] **Uma linha, um clique.** A tela Conectar tem "Ligar um servidor", que mostra uma
   linha para colar; colada num Linux com `python3`, ela baixa o ajudante do próprio
   dervs.com.br (conferindo o resumo do arquivo), abre o "Autorizar" e, autorizado, deixa o
   ajudante rodando a cada 30 s e voltando sozinho depois de reiniciar o servidor. Prova:
   teste que roda o instalador numa pasta vazia contra o servidor de teste, sem o
   repositório, e ele pareia e envia uma medição.
- [ ] **O que ele conta é lista fechada.** Por contêiner: nome, projeto (rótulo do compose),
   estado, saúde, desde quando, número de reinícios, imagem e commit (rótulo da imagem). Do
   servidor: nome, tempo ligado, disco, memória e carga. Nada mais. Prova: teste que manda
   um campo a mais (por exemplo `Env`) e o servidor recusa ou descarta; e teste que lê o
   fonte do ajudante e reprova `docker inspect` sem `--format` fixo.
- [ ] **Commit no ar por projeto.** O cartão do projeto mostra a versão no ar daquele
   servidor e a compara com o GitHub ("igual", "N mudanças atrás", ou "não sei" quando
   falta um dos lados). Nunca inventa: sem rótulo de commit na imagem, diz que não sabe.
   Prova: teste de regra com os três casos + teste de tela em node.
- [ ] **Tempo real com carimbo.** Com o painel aberto, um contêiner que cai aparece caído em
   até 45 s, sem recarregar, com "medido há N s". Servidor que parou de contar há mais de
   3 minutos vira "sem dados", nunca "tudo bem". Prova: teste do fluxo `/api/eventos` +
   teste de regra da validade.
- [ ] **Só olhar, provado.** A máquina do servidor nasce `so_mede`; o pacote dela não tem
   `executor.py`; ela leva 403 em `/agente/voz/*` e na rota de tarefa. Prova: os testes de
   tranca que já existem, estendidos ao novo tipo de máquina.
- [ ] **Sem jargão na tela.** Nada de "agente", "token", "SSH", "systemd", "contêiner" ao
   dono; "sistemas rodando neste servidor". Prova: teste que lê o texto + revisor de
   conteúdo.
- [ ] **Nada do que funciona quebra.** Todas as suítes verdes, o computador pareado e os
   sites medidos por endereço seguem iguais. Prova: suíte inteira + CI.

## fora_de_escopo

- Qualquer ação no servidor (reiniciar, publicar, voltar versão, ver log): entrega C.
- Ler log de contêiner, variável de ambiente, arquivo `.env` ou conteúdo de volume.
- Servidor de revenda (TineHost): continua só por endereço; lá não há terminal.
- Windows Server e macOS como servidor: só Linux com `python3` e `systemd`.
- Atualização automática do ajudante.
- Guardar chave SSH ou senha de servidor no DERVS, em qualquer forma.
- Instalar na VPS de verdade: é mão do dono, depois de publicar (portão 4).

## riscos

- **Produção e dado de paciente por vizinhança.** O ajudante roda na VPS que hospeda o
  Ajudei. Ler o Docker exige poder de administrador naquela máquina: um defeito no ajudante
  que vazasse o ambiente dos contêineres vazaria segredo de sistema de saúde. Por isso a
  lista fechada dos dois lados e revisão de segurança obrigatória.
- **O DERVS vira um ponto de ataque.** Quem tomasse o dervs.com.br não ganha comando nos
  servidores (não há canal de ordem nem atualização automática), mas veria o inventário.
- **Migration leve:** a medição do servidor provavelmente precisa de tabela própria.
- **Config de deploy:** nenhuma no DERVS; a instalação na VPS é passo manual do dono.
- Nenhum pagamento.

## plano_de_voo

Modo **enxuto** (domínio conhecido, reusa o pareamento da entrega A). Portão 1 aprovado por
delegação; portão 3 não abre (direção visual já aprovada); portão 4 abre só na instalação
na VPS, que é do dono.

| Fase | Quem | Modelo | Despachos |
|---|---|---|---|
| 2 Descoberta | 4 lentes num despacho só + síntese minha | opus | 1 |
| 3 Design | textos e estados da tela, sobre os tokens já aprovados | sonnet | 1 |
| 4 Plano | neguin-planner | opus | 1 |
| 5 Execução | neguin-executor por arquivo: ajudante+instalador, servidor+banco, tela | sonnet | 3 |
| 6 Revisão | security, python, conteudo+design em paralelo | sonnet/opus | 3 |
| 7 Cronista | eu | — | 0 |

**Total previsto: ~9 despachos.**
