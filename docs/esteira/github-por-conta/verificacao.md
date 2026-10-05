# Verificação — O GitHub por conta

> Fase 6 da esteira, 05/10/2026. Branch `feat/github-por-conta`.

## O que foi provado (comandos rodados, saída lida)

| Critério do briefing | Prova |
|---|---|
| 2. Uma conta, uma instalação | `test_coletar_por_conta.py`: dublê de rede registra o `Authorization` por chamada; cada conta só vê slugs e token dela. Sabotagem (`Coletor` compartilhado) reprovou. |
| 3. Conta sem instalação/quebrada = "sem dados" com motivo; as outras seguem | idem, casos de B sem instalação e com `access_tokens` 404 |
| 4. Falha fechada de token | idem: nenhuma chamada leva `DERVS_GITHUB_TOKEN`, `_APP_GUARDADO` nem token de outra conta; `subprocess` explode se chamado; guarda de código-fonte |
| 5. Segredo não vaza | idem: stdout/stderr e todas as linhas de `medida` lidos, sem token nem JWT |
| 6. Teto de custo | tetos e prazo derivados; testes com dois contas e prazo vencendo no meio |
| 7. Nada quebra | os 38 arquivos `test_*.py` (37 antigos + o novo) rodados à mão, zero falhas; CI do GitHub |
| 8. Revisão | `python-reviewer` (2 importantes, corrigidos), `security-reviewer` (3 importantes, corrigidos; segunda passada: "pode mergear") |

O que as revisões acharam e foi corrigido: prazo que não cobria sites; repositório ruim derrubando a
conta; relatório malformado de agente derrubando a rodada de todas as contas; slug cru na consulta
GraphQL (injeção, dentro da própria conta); mensagem de falha global revelando contagem de contas.

## O que os comandos NÃO provam

- **Critério 1 (ver na tela de produção) está PENDENTE.** Depende da publicação pelo dono (tarefa
  "Deploy para a VPS") e de esperar 20 minutos ou mais (a camada `github` dorme antes da 1ª rodada).
  Antes disso, ninguém viu o bloco "No GitHub" medido no site de verdade.
- Os testes usam dublê de rede: a troca real chave -> token contra o GitHub, com a instalação real do
  dono, só é provada em produção. Se a instalação não cobrir um repositório, ele aparece em
  `sem_alcance` com motivo (não como zero).
- Os testes de JS rodam em `node` e são pulados se ele não existir.

## Dívidas nomeadas

- **Sem rodízio:** ordem fixa por conta e por site; com teto apertado, os últimos envelhecem
  (`TETO_REPOS_POR_CONTA`, `TETO_SITES_POR_CONTA`, teto de 5 contas por rodada). O motivo aparece
  na tela, então não é silêncio.
- `SLUG_VALIDO` aceita `.` como dono ou repo (`./x`); só rende um 404 do GitHub com o token da própria
  conta. Fechar com `not any(p in (".", "..") ...)` quando alguém mexer ali.
- Site `ok=None` sem item anterior (`adiado`/`prazo`) é gravado com `medido_em` de agora e o painel
  mostra "não medido, há agora": carimbo enganoso, não alarme. Gravar `medido_em` vazio é o conserto.
- Um site que já começou pode passar do prazo da rodada em até 20 s; a thread que estourou fica viva
  até o processo acabar (o coletor é subprocesso, morre com ele).
- A rota `/api/servidores/sugerir` chama `mede_site` sem o prazo por thread (pré-existente).
