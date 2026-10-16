# Verificação — os pedidos ao servidor (entrega C) e o ajudante (entrega B)

## Ensaio da F-2 num container (16/10/2026)

Receita em `infra/ensaio-f2/LEIA.md`. Ubuntu 24.04 com systemd, sudo, visudo e
Docker 29.1 **de verdade**, o kit `deploy-padrao` **de verdade** em
`/usr/local/bin/deploy` e um projeto `ensaio` publicado duas vezes (v1, v2). O
DERVS era o local (4790, `rp_id` `localhost`), com a chave de acesso do dono.

O que ficou provado, visto e não suposto:

- **A linha com pedidos, colada como usuário comum**, baixou o arquivo, passou
  no `sha256sum -c`, pediu autorização com nome e código certos, e a tela
  mostrou "Autorizar este servidor?". Depois de Autorizar, a saída disse
  "Pedidos ligados: reiniciar sistemas; voltar a versao de: ensaio."
- **As duas unidades rodam de verdade** a cada 30 s, `Result=success`, com as
  diretivas de contenção da B (`ProtectSystem`, `CapabilityBoundingSet=` vazio,
  `UMask=0077`) e a do soquete do Docker.
- **`visudo -cf` aceitou** o `sudoers` montado em pedaços: uma linha só, que
  deixa o usuário `dervs-ajudante` rodar como root, sem senha, exatamente
  `/usr/local/bin/deploy ensaio --voltar`, sem curinga (a linha literal não vai
  para documento: o `secret-scan` a barra). `_comando_de_publicar_ok` aceitou o `deploy` do kit
  (root, 755).
- **A ACL** deu `user:dervs-ajudante:r--` no `historico.log`; `/var/lib/dervs-ajudante`
  ficou `700` do ajudante, `agente.json` `600`.
- **O `--format` do `inspect` com Docker de verdade**: `ensaio-web-1`, `running`,
  projeto `ensaio` pelo rótulo do compose; o rótulo de revisão ausente não
  derrubou a linha. O painel mostrou o servidor "medido", "de pé desde 15:53"
  (hora do Brasil certa, a medição é UTC).
- **Reiniciar** (`ensaio-web-1`) e **Voltar** (`ensaio`), assinados com o PIN do
  Windows do dono: os dois `desfecho = feita` em `ordem_de_servidor`. O voltar
  passou por `sudo -n` (registrado no `journal` com o comando exato), o kit
  gravou `OK(voltou)` e o site respondeu **v1**.

- **Reinício da máquina** (`docker restart` do container, systemd subindo do
  zero): os dois temporizadores voltaram ativos, a primeira medição saiu com
  `Result=success` e o painel a recebeu (13:14 UTC); o site do ensaio subiu sozinho.
- **Painel fora do ar**: com o DERVS local desligado à noite, a unidade dos
  pedidos saiu com código 5 (`SEM_REDE`) e não fez nada; na volta seguinte, normal.
- **`remover`** (o comando que a instalação imprime): saíram as unidades, o
  `sudoers`, `/opt`, `/var/lib` e `/etc` do ajudante, o usuário e a entrada dele
  na ACL; o site do ensaio não foi tocado. Três minutos depois o painel disse
  "Sem dados há 4 minutos — o servidor parou de contar", nunca "zero sistemas";
  "Desligar este servidor" o tirou da lista.

## O que este ensaio NÃO prova

- A VPS: nginx, o Docker e o fuso dela, o Ajudei ao lado, `dervs.com.br` como
  `rp_id`. Continua "na VPS só depois de publicar e de duas revisões de segurança".
- Um `voltar` que FALHA (`FALHOU-AO-VOLTAR` no kit → desfecho `falhou` na
  tela): exige outra assinatura com o PIN do dono.
- O container é `--privileged`: o que a contenção do systemd impede numa máquina
  comum pode passar aqui sem ser notado (o contrário não: o que funcionou com as
  diretivas ligadas funciona com elas).

## Achados do ensaio

1. **A página subia ao topo a cada repintura** (achado do dono): `navegar()`
   terminava sempre em `scrollTo(0, 0)`, e é chamada a cada minuto e a cada
   medição de servidor (30 s). Consertado; `test_rolagem_tela.py` cobra.
2. **A autorização de servidor dizia "Ele só vai olhar"** mesmo quando a linha
   colada liga os pedidos de reiniciar e voltar. Consertado no texto.
3. **Dívida pequena (Lei 2):** servidor que cala não manda evento, então a tela
   só descobre o "sem dados" no relógio de um minuto: por até ~60 s depois dos
   180 s ela ainda mostra `[OK] ligado` e "medido há 3 minutos". O servidor já
   responde `sem_dados` certo. Fechar = a tela julgar o prazo pelo `medido_em`
   (como faz com o GitHub em `motivoDoGithubDaConta`). Não feito.
4. A unidade dos pedidos sai com código 5 (`SEM_REDE`) quando o DERVS está fora
   do ar, e o systemd o rotula `NOTINSTALLED` — só o nome é estranho; a volta
   seguinte segue normal.
