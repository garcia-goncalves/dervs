# Spec — O bloco "No GitHub" medindo por conta

> Fase 2 da esteira. Escrito em 05/10/2026, a partir da descoberta do `neguin-planner`
> (HEAD `aaba2ed`). Briefing aprovado pelo dono em 05/10/2026.

## problema

No servidor todo projeto mostra "No GitHub: nunca foi medido". O coletor
(`coletar_github.py`, `main`) lê só `banco.conta_local()`, que no servidor é a conta de teste
(`DONO_LOCAL=0`), sem projeto nenhum. O token também é único para o processo: `_app()` guarda
um `Coletor` global (`_APP_GUARDADO`, `coletar_github.py:497`) escolhido pela conta local ou
por `DERVS_GITHUB_INSTALLATION_ID`. Medir duas contas com isso faria a conta B ler com a
credencial da A.

## solucao

Um **modo por conta** em `coletar_github.py`, que liga só no servidor com o GitHub App
configurado (`DERVS_AMBIENTE != "local"` e `DERVS_GITHUB_APP_ID` ou `DERVS_GITHUB_APP_KEY`
presente). Para cada conta ativa com projeto: lê os slugs dela, obtém **um `Coletor` local**
com a instalação dela (`banco.instalacao_do_github(uid)`), mede e grava na conta dela.

O caminho por conta **nunca chama** `_token`, `_app`, `_gh_graphql`, `_gh_json` nem
`subprocess`: usa funções novas que recebem a credencial como parâmetro explícito
(`_http_com`, `_graphql_com`, `_json_com`). Assim não existe credencial implícita para
vazar entre contas. O motivo de uma conta não ter sido medida vai numa linha de sistema
`_github` na tabela `medida` (mesmo molde de `_quota`; **sem coluna nem tabela nova**, o
portão de risco não dispara) e chega à tela em `ESTADO.github_da_conta`, só para o dono.
Teto de chamadas e prazo por rodada, derivados de constantes.

Por que esta forma: limpar o global entre uma conta e outra deixaria a segurança dependente de
ninguém esquecer de limpar; parâmetro explícito faz a garantia morar na assinatura.

## o_que_ja_existe

- `github_app.py:376-445`: `Coletor` (token só em memória, renovação, falha fechada).
- `banco.py:3835` `instalacao_do_github(usuario_id, con)`; tabela `instalacao_github`
  (`banco.py:459-467`, `UNIQUE(usuario_id)` e `UNIQUE(installation_id)`).
- `banco.py:1678` `ler_tudo(con, usuario_id=)`; `banco.py:55-56,82` `INFRA`, `QUOTA`,
  `RESERVADOS`; `banco.py:1701-1754` `montar_estado`; `banco.py:3515` `receber_relatorio`.
- `coletar_github.py`: `_consulta` (450), `traduz` (866), `_tipos_do_erro` (639), `_monta_sites`
  (339), corpo de gravação de `main` (1025-1135), `_http_github` (604), `_gh_graphql` (648),
  `_gh_json` (728), `mede_deploy` (750).
- `servir.py:165-169` agenda 20 min; `servir.py:365-395` roda o coletor em subprocesso
  (`timeout=600`, herda o ambiente); `servir.py:910-926` `_estado`.
- `assets/painel.js:547-549` e `663-673` (`nada()`): onde "nunca foi medido" é escrito.
- Testes: `test_coletar.py` (`_http_falso`, 1828-1935 molde de dublê de rede com token),
  `test_github_app.py` (`PEM_PKCS1`), `test_banco.py`, `test_servir.py`.

## fontes_externas

nenhuma

## fora_de_escopo

Tudo o que o briefing exclui, mais: rodízio de contas quando o teto aperta (a ordem é fixa
por `usuario_id`; fica anotado como dívida), e mudar o `timeout=600` do `servir.py`.

## contradicoes_resolvidas

- **Quando o modo por conta liga.** (a) servidor + App configurado; (b) bastar não ser local.
  Venceu (a): os testes atuais de `main()` rodam sem App e continuam no caminho antigo, e a
  máquina do dono (ambiente local) não muda de comportamento.
- **Número de suítes.** O briefing diz 38; hoje são 37 `test_*.py`; com o novo, 38. O
  critério 7 passa a dizer "as 37 existentes continuam verdes".

## duvidas_para_o_dono

nenhuma
