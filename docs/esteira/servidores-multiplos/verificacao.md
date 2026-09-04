# Verificação — Servidores múltiplos

Fase 6 (parte 1: evidência de comando) da esteira. Executado em 04/09/2026, sobre `main`
depois de mesclar E1 a E9.

## O que os comandos provam

Suíte inteira, 26 arquivos `test_*.py`, todos `OK`:

| arquivo | casos | arquivo | casos |
|---|---|---|---|
| `test_banco.py` | 274 | `test_execucao.py` | 98 |
| `test_regras.py` | 113 | `test_executor.py` | 19 |
| `test_coletar.py` | 201 | `test_github_app.py` | 37 |
| `test_servir.py` | 267 | `test_imagem.py` | 13 |
| `test_rotas.py` | 34 | `test_memoria.py` | 46 |
| `test_design.py` | 53 | `test_p256.py` | 34 |
| `test_servidores.py` | 15 (**novo**) | `test_passkey.py` | 86 |
| `test_fila.py` | 107 | `test_publicar.py` | 29 |
| `test_sse.py` | 16 | `test_tarefas.py` | 42 |
| `test_agente.py` | 63 (1 skip) | `test_tarefas_nao_publicam.py` | 18 |
| `test_auditoria.py` | 65 | `test_barreira.py` | 36 |
| `test_autenticacao.py` | 36 | `test_coletar_pesado.py` | 12 |
| `test_conectador.py` | 29 | `test_conectar_ponta_a_ponta.py` | 6 |
| `test_cortina.py` | 27 | | |

Linha de base antes desta entrega (medida pelo planner, HEAD `b3342fc`): `test_banco`
241 · `test_servir` 227 · `test_coletar` 201 · `test_regras` 105 · `test_rotas` 34 ·
`test_design` 33. Todos os seis subiram ou se mantiveram; nenhum baixou.

Isso prova, com comando: as regras de negócio (banco, migração, pendências, rotas,
autodetecção) e o casamento de texto/classe entre `assets/painel.js` e
`assets/painel.css`.

## O que os comandos NÃO provam

- **Que o selo lista os dois nomes de servidor na tela, de verdade.** Não há runtime de
  JS neste repositório (`test_design.py` lê `painel.js` como texto). Exige abrir
  `dervs.com.br` → Conectar projeto, cadastrar dois servidores, gravar o mesmo projeto
  nos dois, e olhar o card.
- **Que a migração roda no `hub.db` de produção sem perder linha.** O teste da E1
  (`ServidorNoBancoVelho`) prova isso contra um banco montado à mão com `sqlite3` cru,
  simulando o pior caso (múltiplos donos, múltiplas linhas). O `hub.db` real só se
  confirma publicando (ou copiando o banco de lá para conferir antes).
- **Que o padrão de subdomínio real do dono casa os projetos certos.** `fnmatch` está
  testado com casos sintéticos; o padrão de verdade (`*.tinehost.com.br` ou o que ele
  cadastrar) só se confirma cadastrando e vendo a sugestão aparecer.
- **O comportamento em 360px.** O CSS foi escrito seguindo o padrão que a etapa 14 já
  fechou (menu em faixa que rola), mas ninguém abriu num navegador de verdade em tela
  estreita.
- **O clique dos botões "Usar este endereço" e "Ignorar".** `test_design.py` prova que o
  texto e as classes existem no fonte; não prova que o clique de verdade grava ou
  esconde a sugestão.
- **`MAX_SUGESTOES = 3`** foi escolhido por aritmética de pior caso (~68s de thread por
  chamada), não por medição real do parque do dono. Pode precisar subir.

## Revisão especializada — pendente

Nenhum revisor (`python-reviewer`, `security-reviewer`, `database-reviewer`,
`design-reviewer`) rodou ainda sobre o diff final. É o próximo passo desta mesma fase 6,
antes de considerar a entrega pronta para publicação.

## Publicação — não é decisão desta etapa

Igual a todo o resto do repositório: o deploy roda no GitHub, só por `workflow_dispatch`
com `PUBLICAR`, e só quando o dono der o sinal. Esta entrega **entra no mesmo lote** que
já espera publicação (as quatro portas da fila, `2b7b2eb..84c3f64`) — não muda essa
regra.
