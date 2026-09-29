# Plano — menu enxuto e botão "Consertar com IA"

Briefing: `docs/esteira/menu-e-consertar/briefing.md`. Critérios 1 a 9 vivem lá.

## O contrato entre as duas fatias (não mudar sem avisar)

**Servidor → tela.** Cada pendência em `/api/dados` ganha `consertavel` (bool). Vem
de UMA constante em `fila.py` (`REGRAS_CONSERTAVEIS_PELA_TELA = {"memoria_crlf", "env_drift"}`),
aplicada DEPOIS do motor (`regras.avaliar`), nunca na origem.

**Tela → servidor.** `POST /api/consertar` com `{"id": "<id da pendência>"}`. Classe
de acesso `dado`, mesma guarda de escrita e mesmo balcão próprio de tentativas que
`_auditoria_pedir` (não emprestar o teto de outra rota).

| Situação | HTTP | Corpo |
|---|---|---|
| entrou na fila | 200 | `{"ok": true, "pedido": true, "tarefa": "<id da fila>", "aviso": <texto em português ou null>}` |
| já estava na fila | 200 | `{"ok": true, "pedido": false, "tarefa": "<id>", "aviso": null}` |
| id não existe OU é de outra conta | 404 | `{"erro": "alerta nao encontrado"}` (a MESMA resposta nos dois casos) |
| regra fora de `REGRAS_CONSERTAVEIS_PELA_TELA` | 403 | `{"erro": "esta regra nao e consertada por aqui"}` |
| projeto em `tarefas.PROJETOS_BLOQUEADOS` (minúsculas) | 403 | `{"erro": "projeto bloqueado"}` |

`aviso` é preenchido quando o conserto entrou na fila mas NÃO vai rodar agora:
nenhum computador da conta pareado; computador pareado mas sem autorização de
conserto; teto diário estourado. Texto pronto para leigo, sem jargão.

`GET /api/tarefas` passa a devolver `pr_url` no detalhe da tarefa quando o
desfecho tiver esse campo.

## Fatia A — servidor (executor 1)

Arquivos: `servir.py`, `fila.py`, `banco.py` (só se faltar consulta), `test_servir.py`,
`test_fila.py`, `test_rotas.py`, `.github/workflows/ci.yml` (só se criar teste novo).

1. `fila.REGRAS_CONSERTAVEIS_PELA_TELA` + teste de que é subconjunto de `REGRAS_MECANICAS`
   e de que NÃO contém `auditoria_vencida` nem `dependencia_insegura`.
2. `consertavel` em cada pendência de `/api/dados`, calculado depois de `regras.avaliar`.
   Teste que lê `montar_estado` direto e exige que os alertas continuem lá (a poda é DEPOIS).
3. Rota `/api/consertar` conforme a tabela. Molde: `Hub._auditoria_pedir` (servir.py:2634).
   O id da fila leva o dono: `"<regra>:<usuario_id>:<id da pendência>"` (só o primeiro pedaço
   é lido como regra). Registrar em `ROTAS` com classe `dado`; `test_rotas` tem de continuar
   verde (não usar `exec`/`executar` em nome de função ou caminho).
4. `pr_url` no detalhe de `/api/tarefas?id=`.
5. Testes, TODOS sabotados de propósito para provar que reprovam: fluxo completo (200 e
   linha na fila com o dono certo); duas contas (404 igual, e a linha da fila não vaza);
   regra proibida (403); projeto bloqueado com maiúscula (403); cada `aviso`.

## Fatia B — tela (executor 2)

Arquivos: `index.html`, `assets/painel.js`, `assets/painel.css`, e um teste novo
`test_menu.py` (listado à mão no `ci.yml`, passo próprio).

1. Menu com 4 itens: **Painel** (`#/painel`), **Consertar** (`#/trabalho`), **Conectar**
   (`#/conectar`), **Conta** (`#/conta`). Tela `#/conta` = abas "Consumo" e "Formas de
   entrar" reaproveitando o HTML das telas atuais; **Consertar** ganha um seletor
   "Tarefas | Auditoria" que reaproveita as telas atuais; **Conectar** ganha a seção
   "Computadores" (o parear e o "Deixar consertar aqui") reaproveitando a tela atual.
2. Rotas antigas (`#/auditoria`, `#/consumo`, `#/computadores`, `#/entrada`) continuam
   abrindo a mesma coisa (alias), e o item de menu correto fica marcado.
3. Na tela do alerta (`#/alerta/<id>`), se `p.consertavel`, botão **"Consertar com IA"**.
   Clique → `POST /api/consertar`. Mostra "Na fila. Aprove em Consertar." com link para
   `#/trabalho`, e o `aviso` do servidor se houver. Erros do servidor em português, nunca
   "nada acontece". Sem `consertavel`, sem botão.
4. Nomes de "ver detalhe" unificados em **"Ver detalhes"**.
5. Detalhe da tarefa mostra `pr_url` como link ("Ver o pedido de alteração") quando existir.
6. `test_menu.py`: exatamente 4 itens no nav; cada alias antigo está no roteador; o botão
   só existe atrás de `consertavel`. Sabotar cada caso para provar que reprova.
7. Nada de `<style>` nem estilo inline novo que quebre a CSP: só classes em `painel.css`.

## Depois (eu, no coordenador)

Mesclar as duas fatias, rodar TODAS as suítes, revisores `python-reviewer` e
`security-reviewer` em paralelo, clicar no navegador local, docs (`A-APLICACAO.md`,
`LINKS.md`, `CLAUDE.md`), PR.
