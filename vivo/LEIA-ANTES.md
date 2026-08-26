# Leia antes de tocar em qualquer coisa desta pasta

Esta pasta é o repositório `dervs-hub` inteiro, trazido para cá como subárvore
do Git. Ele continua existindo e vivo em
`https://github.com/garcia-goncalves/dervs-hub` — o André trabalha nele.

## Por que ele está aqui

Para que o código e a **autoria** do André não se percam quando o nome `dervs`
foi reaproveitado por este repositório. Os 13 commits dele estão preservados no
histórico, com o nome dele, sem squash e sem rebase.

## Por que nenhuma linha daqui vai para o ar

O código desta pasta abre um terminal de verdade (PTY) **sem pedir
autenticação**. No computador de alguém, atrás do `127.0.0.1`, isso é uma
ferramenta. Publicado na internet, isso é execução remota de comando aberta
para qualquer pessoa que descubra o endereço.

Duas barreiras independentes impedem isso, e as duas nasceram no mesmo commit
desta pasta:

1. **`.dockerignore`** na raiz tem a linha `vivo/` — a pasta não entra nem no
   contexto de construção da imagem.
2. **`Dockerfile`** na raiz nunca usa `COPY . .`. Cada arquivo que entra na
   imagem está escrito lá por nome.

A segunda existe porque a primeira não basta sozinha: `.dockerignore` não vale
para `COPY --from` nem para contexto de construção remoto.

**A prova de que funcionou não é ler estes dois arquivos.** É construir a
imagem e olhar dentro dela:

```
docker build -t dervs-teste .
docker run --rm dervs-teste sh -c 'ls /app | grep -c vivo || true'
```

O segundo comando tem de imprimir `0`.

## O que é permitido fazer aqui

- **Ler.** É para isso que a pasta existe.
- Aproveitar ideia, desenho ou trecho — reescrevendo no código da raiz, em
  Python, sob as regras deste repositório.

## O que não é permitido

- Importar, chamar ou executar qualquer arquivo desta pasta a partir do código
  da raiz.
- Tirar a linha `vivo/` do `.dockerignore`.
- Trocar a cópia explícita do `Dockerfile` por `COPY . .`.

Se você precisar de algo daqui em produção, a resposta é **reescrever na raiz**,
não abrir a barreira.

## Se quiser atualizar esta pasta com o trabalho novo do André

```
git subtree pull --prefix=vivo https://github.com/garcia-goncalves/dervs-hub.git main
```

Sem `--squash`. Squash apaga a autoria dele, que é justamente o que esta pasta
existe para preservar.
