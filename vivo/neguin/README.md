# 🧠 Neguin — seu dev lead autônomo (dentro do hub)

O **Neguin** é um agente Opus que age como o "André robô": recebe um objetivo num
projeto, **planeja** e **executa** sozinho, e você acompanha — e responde — **dentro do
Hub**, num console ao vivo.

```
VOCÊ → objetivo no projeto X (botão 🧠 Neguin)
     │
🧠 NEGUIN (Opus, o lead)  ──streaming──►  Console no Hub (você vê e responde)
     ├─ 📋 neguin-planner  → planeja por etapas (read-only)
     └─ ⚙️ neguin-executor → implementa, roda testes, commita
→ entrega o branch neguin/<data> pra você revisar
```

## Como funciona

1. No card do projeto: **🧠 Neguin** → descreva o objetivo → **Soltar o Neguin**.
2. Abre o **console do Neguin** no hub. Você vê em tempo real: o raciocínio dele, as
   🔧 ferramentas/subagentes que usa, e pode **responder no próprio hub** (caixa embaixo).
3. Ao terminar, o console mostra o branch e os comandos pra revisar/aprovar.

Tecnicamente: o servidor roda `claude` em modo `stream-json` (entrada e saída) num git
worktree isolado, e transmite os eventos pra UI via **SSE**. Endpoints:
`POST /api/projects/:id/neguin` (inicia), `GET /api/neguin/:runId/stream` (SSE),
`POST /api/neguin/:runId/say` (você responde), `POST /api/neguin/:runId/stop`.

## Segurança (travas sempre ativas)

- **Worktree isolado** num branch **`neguin/<data>`** — cópia separada do repo.
- **Nunca dá `git push`** (não está na allowlist) — seu `main` fica intocado.
- **Sem `--dangerously-skip-permissions`.** O Neguin tem um **conjunto fixo de ferramentas
  seguras** (`NEGUIN_TOOLS` em `server.js`): ler, editar, escrever, criar arquivos,
  `git add/commit`, rodar testes/build. Qualquer comando fora da lista (rm, curl, push…)
  é **negado automaticamente**. Em troca, tarefas que precisem de um comando não previsto
  podem ficar bloqueadas — é só adicionar o padrão à allowlist se confiar.
- O servidor só é alcançável de `127.0.0.1` + guarda de Host/Origin.

## Revisar / aprovar / descartar

O console mostra os comandos ao terminar:
- **revisar**: `git -C <worktree> diff main..neguin/<data>`
- **aprovar**: `git -C <repo> merge neguin/<data>`
- **descartar**: `git -C <repo> worktree remove --force <worktree>` + `git branch -D neguin/<data>`

## Subagentes

Em `~/.claude/agents/`: `neguin-planner.md` (read-only, opus) e `neguin-executor.md`
(escrita/testes, sonnet).

## Custo

Vários agentes trabalhando = **mais tokens**. Use para tarefas que valem delegar. Evite
rodar **ao mesmo tempo** que outra sessão Claude esteja iniciando (concorrência no
`~/.claude.json`).
