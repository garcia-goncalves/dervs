# A linha com pedidos só sai depois de um toque (16/10/2026)

Achado da 2ª revisão de segurança da entrega C, conferido no código: cadastrar
chave de acesso pede só sessão + CSRF, e `GET /api/ajudante/linha` punha na
`linha_com_ordens` as 5 chaves vivas mais novas da conta. Quem roubasse a sessão
(GitHub tomado, cookie, código do papel) cadastrava a própria chave e esperava o
dono colar a linha: a partir daí reiniciava e voltava versões na VPS **sem toque
do dono**, 6 por hora. Quebrava A-APLICACAO §5.8 ("sem um toque do dono, nada
acontece"). Nada estava instalado na VPS: o portão das duas revisões existe para isto.

## Decisão (o dono, 16/10: "seguro, mas facilitado; uma chave só")

**Toque antes de mostrar a linha, e a linha leva só a chave tocada.**

| Opção | Fecha? | Custo para o dono |
|---|---|---|
| **A. Toque para ver a linha com pedidos; só a chave tocada vai nela** | Sim | Um PIN do Windows ao colar a linha (raro) |
| B. Toque de chave existente para cadastrar chave nova | Sim | Trava a recuperação de quem perdeu o aparelho |
| C. Mostrar as datas das chaves ao lado da linha | Não (só avisa) | Nenhum, mas depende de o dono ler |

Por que A fecha: a chave do intruso mora no aparelho do intruso. O toque do dono
no computador dele só pode sair da chave dele, e a linha que ele cola leva
**aquela** chave e nenhuma outra. O intruso consegue uma linha com a chave dele,
mas quem cola linha na VPS é o dono.

Uma chave só: o dono assina os pedidos com a mesma chave que pôs na linha (o PIN
do Windows). Não há chave de pedidos separada nem senha nova.

## Contrato

- `GET /api/ajudante/linha` deixa de devolver `linha_com_ordens`/`chaves_na_linha`.
  Devolve `{linha, sha256, endereco, tem_chave}` (`tem_chave`: a conta tem chave viva).
- `POST /api/ajudante/linha/desafio` (sessão + CSRF, balcão próprio): abre desafio
  em `DESAFIOS` (cookie `desafio`, uso único, 300 s) e devolve `{desafio, rp_id,
  chaves: [cred_id vivos da conta], segundos}`.
- `POST /api/ajudante/linha/pedidos` (sessão + CSRF, balcão próprio): corpo
  `{cred_id, cliente, autenticador, assinatura}`. Resgata o desafio, acha a chave
  (`banco.chave_de_acesso`: viva, conta ativa) **da própria sessão**, confere por
  `passkey.conferir_entrada` (UP e UV obrigatórios, origem, rp_id), avança o
  contador (`banco.usar_chave_de_acesso`). Devolve `{linha_com_ordens, chave:
  {apelido, criado_em}}` com **só** essa chave. Qualquer falha: 401 `RECUSA`.
- Tela: "Ligar um servidor" mostra a linha *Só olhar* na hora; abaixo, "Quero
  poder pedir coisas por aqui" → PIN → a linha com pedidos e a frase "Esta linha
  confia só na chave «apelido», cadastrada em data". Sem chave: o caminho para
  Conta → Entrada.
- A frase de revogar: "Tirou uma chave? Cole a linha de novo para tirá-la também
  do servidor."

## Revisões (16/10/2026): segurança e Python, as duas "pode mergear"

Aplicado: o arquivo do ajudante é lido ANTES do toque (503 não gasta o
contador); o caso do uso único passou a distinguir bilhete gasto de contador
parado (sabotado com `get` no lugar de `pop` e reprovou); corpo torto e teto de
toques testados; e a frase contra engenharia social na tela ("O DERVS nunca
manda esta linha por recado, e-mail ou mensagem"), porque quem roubar a sessão
ainda tira uma linha com a chave DELE e só lhe resta convencer o dono a colá-la.

Dívida nomeada: o bilhete do desafio não é amarrado ao fluxo nem à conta
(`DESAFIOS` e o cookie `desafio` servem login, cadastro e esta rota). Um
desafio do login entra em `/linha/pedidos` e pula o balcão `linha_desafio`;
não dá nada além da linha com a chave que a pessoa mesma tocou. Abrir o
cadastro de chave em outra aba no meio do toque troca o bilhete e o toque
volta 401 (incômodo, não falha).

## Fora desta entrega (proposta)

- Aviso de chave nova: faixa "Uma chave nova entrou na sua conta: «X», em data.
  Foi você?", para pegar sessão roubada também no login.
- Revogação chegar sozinha ao ajudante (hoje só a entrega no DERVS barra).
