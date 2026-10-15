# Design — entrega C: o servidor faz, com o "Pode fazer" do dono

Fase 3, 09/10/2026. Sem portão visual (o portão 3 não abre: a direção está aprovada). Só
textos e estados, sobre o cartão "Seus servidores" da entrega B. Contrato técnico:
`spec.md` desta pasta (C0–C12); as `decisoes_do_portao_2` do `briefing.md` vencem: **duas
ações** (reiniciar um sistema, voltar a versão anterior de um projeto), "publicar" saiu, e a
promessa é a honesta.

## direcao_visual_escolhida

**Torre de Controle**, a de `docs/esteira/dervs/design.md`, sem mudança nenhuma. Os pedidos
moram **dentro** do cartão de cada servidor ligado (Conectar → "Seus servidores"), no mesmo
molde da entrega B: um botão por coisa que se pode fazer, uma frase do estado, o detalhe
fechado em "O que isso faz?". A confirmação usa o diálogo único que já existe
(`confirmar()`, `#dlg-confirmar`), o mesmo de "Desligar este servidor".

Recusadas, com o motivo:

- **(a) Um item novo no menu ("Servidores" ou "Pedidos").** O menu tem exatamente quatro
  itens e `test_menu.py` cobra; o lugar de mexer num servidor é onde ele já aparece.
- **(b) Botões no cartão do projeto do Painel** ("Voltar a versão" ao lado de "3 mudanças
  atrás do GitHub"). Seria o lugar mais rápido, mas espalha um poder de produção por todas as
  telas e mistura "olhar" com "fazer". Fica só em Conectar, num lugar só, que o dono procura
  de propósito. O Painel continua só lendo.
- **(c) Pedido sem confirmação (um toque e vai).** A digital já é uma confirmação, mas o
  aparelho não mostra o que está sendo aprovado; a frase exata tem de aparecer na tela **antes**
  do toque, num diálogo, com "Agora não" em evidência igual.
- **(d) Mostrar o que o servidor imprimiu** ("ver o registro"). Fora de escopo: registro de
  sistema de saúde pode trazer dado de paciente. O resultado é só "feito", "não deu certo
  (código N)" ou "não sei".
- **(e) Terminal embutido.** O terminal mora só no DERVS-VOZ, por decisão antiga.

## tokens

**Nenhum token novo.** Usa, por nome, os de `assets/dervs.css` já aplicados em
`assets/painel.css`:

| Uso nesta entrega | Token |
|---|---|
| Fundo do cartão do servidor e da faixa do pedido | `--fundo-elevado` |
| Botão "Pode fazer" (o principal do diálogo) | `--acao`, `--acao-texto` |
| Botões "Reiniciar" e "Voltar a versão anterior" (secundários, contorno) | `--borda-forte`, `--texto`, `--raio`, `--traco` |
| Carimbos ("feito há 12 s", "pedido enviado há 4 s") | `--texto-suave`, `--fs-metadado` |
| Nome do alvo dentro da frase | `--peso-forte` |
| Marca "feito" | `--estado-saudavel`, fundo `--estado-saudavel-fraco` |
| Marca "não deu certo" e "recusado" | `--estado-quebrado`, fundo `--estado-quebrado-fraco` |
| Marca "o servidor não pegou", "sem resposta", aviso de linha velha | `--estado-atencao`, fundo `--estado-atencao-fraco` |
| Marca "não sei" | `--estado-sem-dados` |
| Linha para colar (só ela) | `--fonte-mono` |
| Espaços entre linha de sistema, botão e estado | `--e2`, `--e3`, `--e4` |
| Foco visível nos botões novos | `--foco-largura`, `--foco-afastamento` |
| Separador entre "Sistemas" e "Voltar a versão anterior" | `--borda` |

As marcas de estado reusam `marcaDaPorta()`: **cor nunca sozinha**, sempre com a palavra.
Nenhum `style=` no HTML e nenhum arquivo novo em `assets/` (`test_design`).

## telas

Tudo dentro de **Conectar → "Seus servidores"**, no item de cada servidor ligado
(`linhaDeServidorLigado`). Nada muda num servidor que só olha, a não ser o convite.

**1. Sem chave de acesso cadastrada** (a conta não tem chave de acesso viva;
`/api/ajudante/linha` traz `linha_com_ordens: null`). Em "Ligar um servidor", abaixo da
linha "só olhar", um parágrafo explica que pedir coisas ao servidor exige uma chave de acesso
(digital ou PIN) e um link "Cadastrar uma chave de acesso" para `#/conta`. **Não mostra** a
linha com pedidos. Num servidor que já tem pedidos ligados mas cuja conta perdeu todas as
chaves (`ordens.chaves_ok === false`), os botões somem e fica o mesmo aviso.

**2. Servidor só olha, com convite.** Servidor ligado pela linha da entrega B
(`s.ordens === null` e medido): a lista de sistemas como hoje, **sem** botões, e uma linha
discreta no fim: "Este servidor só olha." + botão secundário "Quero poder pedir coisas" que
abre o mesmo bloco de "Ligar um servidor", já na aba da linha com pedidos.

**3. "Ligar um servidor" com as duas linhas.** Duas escolhas, uma embaixo da outra (nunca
abas lado a lado em 360 px): "Só olhar" (a da B, igual) e "Olhar e aceitar pedidos" (só quando
`linha_com_ordens` não é `null`). Cada uma com seu bloco de linha (monoespaçada, rolagem
própria), "Copiar" acima, largura cheia. A com pedidos lista os aparelhos que poderão mandar
pedidos (`chaves_na_linha`, só os apelidos) e tem o seu "O que isso faz?" com o limite honesto.

**4. Linha velha / chave nova** (`ordens.linha_velha === true`). Faixa de atenção no topo
do servidor: a lista de aparelhos mudou desde que a linha foi colada. Os botões continuam
(as chaves que o servidor conhece ainda valem), e a faixa tem o botão "Ver a linha nova".

**5. Os botões.**
- Em cada sistema com `x.reiniciavel === true`: botão secundário **Reiniciar**, à direita do
  nome em tela larga; embaixo, largura cheia, em 360 px. Sistema bloqueado (`reiniciavel`
  falso num servidor com pedidos): sem botão, com a frase curta "fica de fora: guarda dado
  de saúde" quando o motivo é o bloqueio (o DERVS manda o campo `bloqueado: true` no item,
  acréscimo deste design ao C9 do spec, registrado no plano).
- Bloco **"Voltar a versão anterior"**, depois dos sistemas, separado por `--borda`: uma
  linha por projeto de `s.ordens.voltaveis`, nome + botão secundário **Voltar**. Lista vazia:
  "Nenhum projeto deste servidor pode voltar de versão ainda." (aparece quando nada foi
  publicado pelo VS Code ali, ou o comando de publicar do servidor não passou na conferência).
- Enquanto há um pedido em andamento no servidor (`enviado` ou `fazendo`), todos os botões
  daquele servidor ficam desabilitados com `aria-disabled` e o título "Espere o pedido
  anterior terminar."

**6. Confirmação com a frase exata.** Clique → `confirmar()` com o título = a frase do pedido
(ver `textos`), o texto do que vai acontecer, "Pode fazer" (principal) e "Agora não". Nada
vai ao servidor do DERVS antes do "Pode fazer".

**7. Esperando a digital.** Depois do "Pode fazer": o botão clicado vira "Esperando a sua
digital…" (desabilitado), e uma faixa no topo do servidor repete a frase do pedido devolvida
pelo DERVS (`frase` de `preparar`), para o dono conferir enquanto o aparelho pede o toque.
O pedido vence em 5 minutos.

**8. Digital cancelada.** O dono fechou o pedido do aparelho, ou ele expirou: faixa neutra
"Você cancelou. Nada foi pedido ao servidor." O botão volta ao normal. (Uma ordem preparada e
não aprovada simplesmente vence; nada desce ao servidor.)

**9. Pedido enviado.** O DERVS aceitou a digital: marca neutra "pedido enviado" + carimbo
"há N s", na linha do alvo (sistema ou projeto). O fluxo de eventos já aberto (`event:
servidor`, a cada medição de 30 s) relê o painel; o estado avança sozinho.

**10. Fazendo.** O servidor pegou o pedido e ainda não contou o fim: "o servidor está
fazendo" + "há N s". Voltar uma versão pode levar minutos.

**11. O servidor não pegou em 2 minutos** (`nao_pegou`). Marca de atenção: "o servidor não
pegou o pedido" + o que fazer. **Nunca** "feito". Os botões voltam.

**12. Feito há N s** (`feito`). Marca saudável + "feito há N s".

**13. Não deu certo (código N)** (`nao_deu`). Marca quebrada + "não deu certo (código N)" +
uma frase do que tentar.

**14. Recusado** (`recusado`, com `motivo`). Marca quebrada + a frase do motivo (tabela em
`textos`). Inclui o teto do próprio servidor (`motivo: teto`, 6 pedidos por hora).

**15. Sem resposta / não sei** (`sem_resposta`, `nao_sei`). Marca "não sei": o servidor pegou
e não contou como terminou. Nunca "feito", nunca "falhou".

**16. Teto atingido no DERVS** (429 em preparar/assinar). Faixa de atenção: muitos pedidos em
pouco tempo; tentar daqui a alguns minutos.

**17. Erros de preparar/assinar**, cada um com frase nossa (tabela em `textos`): 409
`so_olha`, `sem_dados`, `ocupado`, `sem_chave`; 403 `bloqueado`; 404; 400; 401; página
velha (403 com `PAGINA_VELHA`) usa a faixa central que já existe.

Só o **último pedido por alvo** aparece na linha daquele alvo (`ordens.pedidos`, os 5 mais
novos do servidor). Pedido de alvo que sumiu da medição aparece numa linha "Último pedido"
abaixo da lista, para o resultado nunca desaparecer calado.

**360 px.** Uma coluna. Em cada sistema: nome (quebra em qualquer ponto, `overflow-wrap:
anywhere`), marca de estado, carimbo, e o botão "Reiniciar" **embaixo**, largura cheia, alvo
de toque de pelo menos 44 px. "Voltar a versão anterior": cada projeto numa linha, botão
"Voltar" embaixo, largura cheia. A faixa do pedido (esperando, enviado, resultado) ocupa a
largura do cartão e quebra linha. O diálogo de confirmação já é largura cheia em 360 px;
"Pode fazer" e "Agora não" empilham, "Pode fazer" em cima. As duas linhas para colar rolam
dentro do próprio bloco; a página nunca rola na horizontal.

## textos

Sem jargão: nada de "WebAuthn", "assinatura", "token", "contêiner", "docker", "deploy",
"sudo", "systemd", "agente", "login", "instalação". Diz "pedido", "digital ou PIN",
"sistema", "versão", "aparelho". O único texto técnico visível é a linha para colar (dentro
do `<pre>`/`<code>`, fora do guarda).

**Ligar um servidor (as duas linhas)**
- Escolha 1, título: **Só olhar** — "O servidor conta o que está rodando nele. O DERVS não
  consegue pedir nada a ele."
- Escolha 2, título: **Olhar e aceitar pedidos** — "Além de contar, o servidor aceita dois
  pedidos seus: reiniciar um sistema e voltar um projeto para a versão anterior. Cada pedido
  só anda com a sua digital ou o seu PIN."
- Aparelhos: "Poderão mandar pedidos: Celular do Thiago, PIN do notebook." (os apelidos de
  `chaves_na_linha`, separados por vírgula).
- Sem chave de acesso: "Para o servidor aceitar pedidos, você precisa de uma chave de acesso
  (a digital do celular ou o PIN do computador). Cadastre uma e volte aqui." + link
  **Cadastrar uma chave de acesso**.
- O roteiro de quatro passos é o da B, sem mudança; o passo 2 da escolha 2 diz: "Cole a linha
  abaixo e aperte Enter. Ela pode pedir a sua senha do servidor. Se o servidor já estava
  ligado, ela troca o jeito dele sem perder o que ele já contou."
- Para desligar os pedidos: "Para voltar a só olhar, cole no servidor a linha **Só olhar**.
  Os pedidos são desligados na hora."

**"O que isso faz?" da linha com pedidos** (fechado por padrão)

> A linha faz tudo o que a de só olhar faz e mais uma coisa: deixa o servidor aceitar dois
> pedidos seus — reiniciar um sistema que ele está vendo e voltar um projeto para a versão
> que estava no ar antes da última. Nenhum outro: ele não apaga, não para, não lê dados nem
> senhas e não aceita nenhuma ordem escrita. Um pedido novo só existe numa versão nova deste
> programa, que você colaria de novo.
>
> Cada pedido sai com a sua digital ou o seu PIN, e é o **próprio servidor** quem confere
> que foi o seu aparelho, que o pedido é recente e que ainda não foi usado. O Ajudei e
> qualquer sistema com dado de saúde ficam de fora sempre, nas duas pontas.
>
> **O limite, com todas as letras:** o seu aparelho não mostra qual pedido você está
> aprovando — ele mostra só "dervs.com.br". Se alguém tomasse o dervs.com.br, poderia trocar
> o pedido na hora do seu toque. Sem um toque seu, nada acontece. Com o site tomado, cada
> toque vira no máximo **um** pedido desta lista — reiniciar um sistema ou voltar um projeto
> liberado —, nunca no Ajudei, nunca um comando, e no máximo 6 por hora em cada servidor.
> Se o seu aparelho pedir a digital sem você ter clicado em "Pode fazer", recuse.
>
> Para isso, a linha dá ao programa do servidor a permissão de voltar a versão só dos
> projetos listados, um por um, e de reiniciar os sistemas que ele vê. Para tirar tudo:
> cole a linha **Só olhar** (desliga os pedidos) ou a linha de remover, que já está acima.

**Cartão do servidor**
- Convite (só olha): "Este servidor só olha." · botão **Quero poder pedir coisas**
- Linha velha: "A lista de aparelhos que podem mandar pedidos mudou desde que você ligou este
  servidor. Os aparelhos antigos continuam valendo; para os novos, cole a linha de novo." ·
  botão **Ver a linha nova**
- Sem chave viva: "Você não tem mais nenhuma chave de acesso, então este servidor não aceita
  pedidos seus. Cadastre uma em Conta e cole a linha de novo." · link **Ir para Conta**
- Botão no sistema: **Reiniciar** · desabilitado: "Espere o pedido anterior terminar."
- Sistema bloqueado: "fica de fora: guarda dado de saúde"
- Bloco: título **Voltar a versão anterior** · botão **Voltar** · vazio: "Nenhum projeto
  deste servidor pode voltar de versão ainda."

**Confirmação** (a frase é montada igual pela tela e pelo DERVS, letra por letra)
- Reiniciar, título: **Reiniciar o sistema “grimoire-web” no servidor “vps-ovh”**
- Reiniciar, texto: "O sistema para e volta sozinho, em alguns segundos. Quem estiver usando
  pode ver a página fora do ar nesse tempo. Depois do clique, o seu aparelho pede a digital
  ou o PIN."
- Voltar, título: **Voltar “grimoire” para a versão anterior no servidor “vps-ovh”**
- Voltar, texto: "O servidor põe no ar de novo a versão que estava antes da última
  publicação. Pode levar alguns minutos, e o sistema fica fora do ar por alguns segundos no
  fim. Depois do clique, o seu aparelho pede a digital ou o PIN."
- Botões: **Pode fazer** · **Agora não**

**Estados do pedido** (na linha do alvo; `N` vem de `haQuanto(quando)`)

| Estado | Marca | Frase |
|---|---|---|
| esperando a digital | neutra | "Esperando a sua digital…" (no botão) e, na faixa: "Confira: Reiniciar o sistema “grimoire-web” no servidor “vps-ovh”. O pedido vence em 5 minutos." |
| digital cancelada | neutra | "Você cancelou. Nada foi pedido ao servidor." |
| `enviado` | neutra | "pedido enviado há 4 s" |
| `fazendo` | neutra | "o servidor está fazendo, há 40 s" |
| `nao_pegou` | atenção | "o servidor não pegou o pedido. Nada foi feito. Confira se ele está medindo (o carimbo acima) e peça de novo." |
| `feito` | saudável | "feito há 12 s" |
| `nao_deu` | quebrada | "não deu certo (código 1). Confira o sistema na lista acima: se ele estiver parado, peça de novo." |
| `recusado` | quebrada | "o servidor recusou o pedido: " + a frase do motivo abaixo |
| `sem_resposta` | não sei | "o servidor pegou o pedido há 31 min e não contou como terminou. Não sei se foi feito." |
| `nao_sei` | não sei | "o servidor não conseguiu saber se terminou. Confira o sistema na lista acima." |

**Motivos da recusa do servidor** (lista fechada de C3/C4)

| `motivo` | Frase |
|---|---|
| `teto` | "já foram 6 pedidos na última hora, o máximo. Tente de novo mais tarde." |
| `vencida` | "o pedido chegou depois dos 5 minutos. Peça de novo." |
| `repetida` | "este pedido já tinha sido usado." |
| `bloqueado` | "este sistema guarda dado de saúde e fica de fora sempre." |
| `desconhecido` | "o servidor não encontrou esse sistema ou projeto agora." |
| `outro_servidor` | "o pedido era para outra ligação deste servidor. Recarregue a página e peça de novo." |
| `cheio` | "o servidor está com pedidos demais guardados. Tente daqui a 5 minutos." |
| `assinatura`, `desafio`, `origem`, `aparelho`, `forma` | "o servidor não reconheceu a sua digital neste pedido. Se a lista de aparelhos mudou, cole a linha de novo." |

**Erros ao pedir** (antes de chegar ao servidor)

| Resposta | Frase |
|---|---|
| 409 `so_olha` | "Este servidor só olha. Para ele aceitar pedidos, cole a linha com pedidos." |
| 409 `sem_dados` | "O servidor não conta nada há mais de 3 minutos. Espere ele voltar a medir." |
| 409 `ocupado` | "Já há um pedido em andamento neste servidor. Espere ele terminar." |
| 409 `sem_chave` | "Nenhum aparelho seu é conhecido por este servidor. Cole a linha com pedidos de novo." |
| 403 `bloqueado` | "Este sistema guarda dado de saúde e fica de fora sempre." |
| 404 | "Não achei este servidor na sua conta. Recarregue a página." |
| 400 | "Esse sistema não está mais na medição. Recarregue a página." |
| 401 (digital não aceita) | "Não deu para conferir a sua digital. Nada foi pedido. Tente de novo." |
| 429 | "Muitos pedidos em pouco tempo. Tente daqui a alguns minutos." |
| rede | "Não consegui falar com o DERVS. Nada foi pedido. Tente de novo." |
| navegador sem suporte | "Este navegador não sabe pedir a digital. Use o Chrome, o Edge ou o Safari atualizados." |

**Dados de demonstração** (só no ambiente local; a faixa `AMBIENTE LOCAL` aparece)
- Servidor `vps-ovh`, medido há 12 s, com pedidos ligados; aparelhos "Celular do Thiago" e
  "PIN do notebook".
- Sistemas: `grimoire-web` (de pé, desde ontem; último pedido "feito há 2 min"), `dervs-app`
  (de pé; sem pedido), `grimoire-db` (de pé; "o servidor não pegou o pedido" de 14:02),
  `ajudei-db` (reiniciou 2 vezes; **sem** botão: "fica de fora: guarda dado de saúde").
- Voltar a versão anterior: `grimoire` ("não deu certo (código 1)" há 9 min) e `dervs` (sem
  pedido). `ajudei-saude` nunca aparece na lista.
- Segundo servidor `vps-teste`, só olha: dois sistemas, o convite "Quero poder pedir coisas".

## assets

nenhum — nenhuma imagem, ícone ou fonte nova. Os estados usam as marcas de texto que já
existem (`marcaDaPorta`) e os tokens acima; nenhuma foto realista falta.

## estrategia_de_aquisicao

Não se aplica: é tela interna, atrás de login, fora de busca (`robots.txt` já recusa); sem
meta tag, página pública ou texto de venda novos. O próximo passo da tela é sempre um só:
servidor que só olha → "Quero poder pedir coisas"; servidor com pedidos → o botão do sistema
caído ou do projeto que precisa voltar; pedido em andamento → esperar o resultado, que chega
sozinho a cada 30 s.
