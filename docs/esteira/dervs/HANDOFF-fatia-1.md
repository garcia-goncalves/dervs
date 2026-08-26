# Handoff — DERVS Fatia 1, etapas 1 a 6 concluídas

Gravado em 26/08/2026. Estado: `main@9dc9135`, árvore limpa, tudo no GitHub, CI verde.

## ATENÇÃO — A PASTA MUDOU

O trabalho agora acontece em **`C:\Users\Desktop\source\repos\dervs`**
(era `source\painel-projetos`). Abra a janela do VS Code lá.

- Repositório: `github.com/garcia-goncalves/dervs` — privado, `main` protegida.
- A memória do Claude foi migrada para o slug `C--Users-Desktop-source-repos-dervs`.
- `source\painel-projetos` ficou **congelado de propósito** — ponto de retorno.
  O processo em `localhost:4777` ainda roda de lá.

## FEITO (etapas 1 a 6, todas com prova rodada)

1. **Rename** `dervs` → `dervs-hub`, pelo site, pelo dono. Provado.
2. **André reaponta o remoto** — ele diz que fez; **a saída do `git remote -v` NUNCA
   FOI COLADA.** Não é verificável daqui (é operação local, sem rastro no GitHub).
   Mitigado, não provado: ver "risco aceito" abaixo.
3. **`hub` mesclada na `main`** do dervs-hub, sem squash. Autoria preservada:
   `andgoncs: 13` commits, confirmado pela API do GitHub.
4. **Repositório `dervs` criado**, privado, 81 commits herdados, `.gitattributes`
   no mesmo commit da normalização. Zero CRLF no índice e no disco. 500 testes passam.
5. **`vivo/` como subárvore**, com `.dockerignore` + `Dockerfile` + `LEIA-ANTES.md`
   **no mesmo commit**. Provado construindo a imagem: `vivo/` = 0, `.js` = 0,
   `dangerously-skip-permissions` = 0. A imagem tem 15 arquivos, conferidos.
6. **CI verde** — 483 testes, 8 arquivos, um job só. Vigia novo da barreira do `vivo/`,
   testado pelos DOIS lados (passa no código são, reprova nos três tipos de sabotagem).

**Extra (fora do plano, pedido pelo dono):** o projeto saiu de `source\` e foi para
`source\repos\dervs`, junto com os outros 16. `coletar.py:47` (`RAIZ`) só mede o que
está lá — antes o hub não se media. `pastas_de_projeto()` agora devolve 17 projetos,
`dervs` presente, sem duplicar. O comentário de `coletar.py:51` foi atualizado.

## RISCO ACEITO, CONSCIENTEMENTE

A etapa 2 não tem a prova que o plano exige. Em vez de travar, o silêncio foi removido:

- O `dervs` novo tem histórico **sem parentesco** com o clone do André → um `git push`
  dele apontando para o nome antigo é **recusado com erro na tela**.
- `main` protegida: `allow_force_pushes: false`, `allow_deletions: false` → o único
  caminho que passaria por cima da recusa está fechado.

**Ainda assim, peça a saída do `git remote -v` ao André.** É a última confirmação.

## A RETOMAR — ETAPA 7

Plano: `docs/superpowers/plans/dervs-fatia-1.md`, seção "## 7". **Não refazer o plano.**

Amputar de `servir.py` toda rota que executa comando, e trocar a cadeia de
`if self.path...` por `servir.ROTAS` enumerável.

- **Sai:** `/api/acao`, `/api/execucao`, o proxy do grafo (`servir.py:537-748`),
  `ACOES`, `ACOES_SEM_PROJETO`, `caminho_do_grafo`, e os testes do proxy em
  `test_servir.py`.
- **NÃO sai:** `execucao.py` e `fila.py` — ficam no repositório, com os 183 testes
  verdes, sem nenhuma rota apontando para eles. Apagá-los destrói a trava de diff de
  `fila.py:229`, uma das duas defesas do produto para a Fatia 2.
- **Novo:** `test_rotas.py`, o teste-vigia. Ele **importa `servir` e itera
  `servir.ROTAS` em memória** — não faz grep no texto do arquivo. Uma rota montada
  por concatenação (`"/api/" + nome`) escaparia do grep. E ele falha de propósito se
  `ROTAS` não existir, para ninguém "resolver" o teste apagando a tabela.

Prova: `python test_rotas.py` OK · `grep -c 'ACOES' servir.py` = 0 ·
`test_servir.py`, `test_execucao.py` e `test_fila.py` os três OK.

Depois: 8 (banco multiusuário) · 9 (login + 2FA, depende de 7 e 8, disputa `servir.py`
com a 7) · 10 · 11 · 12 · 13→14→15 (telas) · 16 (publicação) · 17.

## ARMADILHAS JÁ PAGAS — NÃO REPETIR

- `servir.py` **importa** `regras`/`banco`/`coletar` na subida. Editar `.py` e conferir
  na tela sem reiniciar mostra a versão antiga.
- **Heredoc corrompe acento no Windows.** Mensagem de commit com acento: escreva o
  arquivo com a ferramenta Write e use `git commit -F <arquivo>`.
- **Push junto com outros comandos na mesma linha é barrado** por um classificador.
  Rode `git push` sozinho, numa chamada só dele.
- `git ls-files --eol | grep 'w/crlf'` mede o **disco**; `i/crlf` mede o **índice**.
  São coisas diferentes e o plano cobra a primeira.
- **A cota de Actions está em 88%** (2.626 de 3.000 min). Nada de job paralelo:
  a cobrança é por tarefa arredondada.
- **Pendência conhecida para a etapa 16:** `servir.py:982` escuta em `127.0.0.1`.
  Dentro de um container isso **não aceita conexão nenhuma de fora**. Precisa virar
  `0.0.0.0` (atrás do nginx) quando a publicação for montada.

## NÚMEROS REAIS (os documentos da esteira erravam)

- **500** funções de teste em 8 arquivos `test_*.py` **na raiz** (não em `tests/`).
  A CI reporta 483 pelo runner do unittest. Não são "452".
- **18** rótulos em `regras.ROTULO_REGRA`. Não são "16".
- `projects.json` não existe. `casos.json` existe.
