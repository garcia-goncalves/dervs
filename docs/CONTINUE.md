# O que fazer no próximo chat

Escrito em 27/08/2026, ao fim da etapa 14. Este arquivo é versionado de propósito:
handoff que vive só na conversa some no `/clear` seguinte.

## Onde estamos

- **Branch `etapa-14-as-seis-telas`, PR #14 aberto, verificação automática verde.**
  998 testes passando. **Ainda não mesclado.**
- `main` está em `74c509d` (a etapa 13).

## Leia primeiro

1. `docs/A-APLICACAO.md` — a fonte única. Vence qualquer outro documento em conflito.
2. `CLAUDE.md` na raiz — as três leis do código.
3. `docs/esteira/dervs/design.md` — a direção visual. **Aprovado, não refazer.**
4. `docs/LINKS.md` — como subir, os endereços das telas, e as três armadilhas de
   navegador que custaram meia hora nesta etapa.

## O que a etapa 14 entregou

O `index.html` deixou de ser o HUB do dev. Agora são as telas do DERVS, em português,
na direção Torre de Controle: **Painel** (`#/painel`), **Projeto** (`#/projeto/<nome>`),
**Alerta** (`#/alerta/<id>`), **Conectar projeto** (`#/conectar`), **Computadores**
(`#/computadores`) e **Formas de entrar** (`#/entrada`). A tela **Entrar** continua
sendo outra página (`index-cortina.html` + `portas.html`).

Zero cor literal no `index.html` (eram 32). Os quatro estados do selo estão declarados
no HTML, com cor, forma, glifo e rótulo escrito.

**No servidor, três coisas além do previsto no plano:**

- `ESTATICOS_OK` ganhou a pasta `assets/` e o `/robots.txt`, por caminho exato.
- `_guarda_de_escrita` extraída: Origin + sessão + anti-CSRF + corpo JSON, num lugar só.
- **Rotas novas `/api/arquivar` e `/api/desarquivar`**, porque "isto está certo assim"
  era botão sem rota nenhuma.

E `/api/dados` passou a devolver `selo` e `camadas` por projeto — o motor da etapa 10
nunca era chamado por ninguém.

## O PRÓXIMO PASSO: uma decisão sua, e depois a etapa 15

### 1. Mesclar o PR #14 (decisão sua)

A verificação automática está verde. O `CLAUDE.md` global pede revisor especialista
(`python` e `security`) antes de mesclar, porque isto mexe em rota de escrita e no
anti-falsificação. **Escolha: mesclar direto, ou rodar os dois revisores antes.**

### 2. A meta de 360px que não fecha (decisão sua)

O desenho pede duas coisas que não cabem juntas:

- "10 projetos visíveis sem rolagem em 360×640";
- uma linha de projeto com *selo · nome · o motivo em uma frase · o carimbo*.

**Medido no navegador**, dentro de um quadro de 360×640: a linha mede 90–113px, e a
frase de resumo + a régua de quatro contadores + a ação recomendada somam outros 350px.
Cabem 5 a 7 projetos, não 10. **Chegar a 10 exige tirar o motivo da linha.** A tela foi
entregue com o motivo — é ele que responde "o que houve" sem um clique. A meta está
registrada como não cumprida em `docs/A-APLICACAO.md`.

### 3. Etapa 15 — o teste dos oito itens verificáveis do design

Plano em `docs/superpowers/plans/dervs-fatia-1.md`, seção 15. Cria `test_design.py` e
acrescenta **um passo à mão** em `.github/workflows/ci.yml` (há um teste que cobra essa
lista; arquivo novo que não estiver lá deixa a verificação vermelha).

Os oito itens já foram conferidos à mão nesta etapa e passam; o trabalho é transformá-los
em teste. **A armadilha nomeada no plano:** escrever o item 8 como busca de texto e ele
passar vazio porque não achou número nenhum. O caso tem de começar afirmando que há pelo
menos 20 números na tela, e só então verificar os carimbos.

## Dívidas abertas

- **Issue #12** — POST que recebe 401/403 fecha a conexão sem entregar a resposta.
  ~1 em 8 corridas de `test_servir.py`. Verificação vermelha do nada nesse arquivo é isto.
- **A faixa `AMBIENTE LOCAL` nunca aparece nesta máquina.** `E_LOCAL` exige
  `DERVS_AMBIENTE=local`, e o `docs/LINKS.md` manda subir com `pythonw servir.py` sem a
  variável. A falha é fechada (o certo), mas o `CLAUDE.md` global pede a faixa no
  ambiente local. Conserto: a receita de subida define a variável. **Não foi feito**
  porque muda como o painel sobe, e isso é fora do escopo da etapa 14.
- **"Conectar projeto" não lista pastas.** O agente ainda não tem rota que devolva as
  pastas com Git. É da Fatia 2, e a tela diz isso na cara em vez de fingir.

## Armadilhas desta máquina, confirmadas nesta sessão

- **Mudar só o `#` do endereço não recarrega a página.** Editei o HTML e fiquei olhando
  a versão velha.
- **Dois `servir.py` de pé ao mesmo tempo**: o antigo segura a porta, o navegador fala
  com ele, e as rotas novas respondem 404 com a tela idêntica. A receita para listar os
  dois está em `docs/LINKS.md`.
- O heredoc do Bash troca o fim de linha: para editar arquivo por script, escreva o
  script com a ferramenta `Write` e rode o arquivo.
