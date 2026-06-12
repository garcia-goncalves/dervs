// pty-sessions.js — gerenciador de sessoes de terminal PERSISTENTES.
//
// Cada sessao e um processo real (Claude, shell, ou qualquer CLI) rodando dentro
// de um PTY (node-pty) que vive NO PROCESSO DO SERVIDOR. O navegador so se anexa
// via WebSocket. Fechar a aba / recarregar o navegador NAO mata a sessao: ao
// reabrir, o cliente se reanexa e recebe o scrollback. E isso que resolve o
// "desconectar a sessao" das janelas wt destacadas.
//
// Seguranca: o COMANDO de cada sessao nunca vem cru do cliente. O cliente escolhe
// um preset (enum) e o id de um projeto; o cwd e o binario saem da config do
// servidor. Texto livre (a tarefa) vai como ARGUMENTO, nunca interpolado em shell
// (PTY = exec direto, sem shell). Igual ao resto do hub.

const pty = require("node-pty");
const os = require("os");
const fs = require("fs");
const path = require("path");

// node-pty NAO resolve o PATH/PATHEXT como o child_process: ele precisa do caminho
// absoluto do executavel. Resolvemos "claude" (e cia.) varrendo o PATH + PATHEXT.
const _cmdCache = new Map();
function resolveCommand(cmd) {
  if (_cmdCache.has(cmd)) return _cmdCache.get(cmd);
  let found = cmd;
  if (path.isAbsolute(cmd) && fs.existsSync(cmd)) {
    found = cmd;
  } else {
    const exts = (process.env.PATHEXT || ".EXE;.CMD;.BAT").split(";").filter(Boolean);
    const dirs = (process.env.PATH || "").split(path.delimiter).filter(Boolean);
    outer: for (const dir of dirs) {
      const base = path.join(dir, cmd);
      if (fs.existsSync(base) && fs.statSync(base).isFile()) { found = base; break; }
      for (const ext of exts) {
        const full = base + ext;
        if (fs.existsSync(full)) { found = full; break outer; }
      }
    }
  }
  _cmdCache.set(cmd, found);
  return found;
}

const SCROLLBACK_BYTES = 256 * 1024; // ~256KB de historico por sessao p/ replay no reconnect
const DEFAULT_COLS = 100;
const DEFAULT_ROWS = 30;

// Presets de papel (roles). Cada um define como o Claude entra. O comando base e
// sempre "claude"; o que muda e o system-prompt (--append-system-prompt) e se ja
// inicia com uma tarefa. shell = terminal cru pra quando voce quer mao na massa.
const ROLES = {
  orchestrator: {
    label: "Orchestrator",
    persona:
      "Voce e o ORCHESTRATOR de uma lousa de agentes. Coordene o trabalho: divida tarefas, acompanhe os outros agentes (Reviewer, Tester, Dev) e consolide resultados. Seja conciso e direto em pt-BR.",
  },
  reviewer: {
    label: "Code Reviewer",
    persona:
      "Voce e o CODE REVIEWER. Revise o codigo deste repositorio com olhar critico: bugs, seguranca, simplificacao, convencoes. Aponte achados objetivos com arquivo:linha. pt-BR, conciso.",
  },
  tester: {
    label: "Tester",
    persona:
      "Voce e o TESTER. Foque em testes: rode a suite, escreva testes faltantes, reproduza bugs com um teste antes de corrigir. Reporte o que passou/falhou com a saida real. pt-BR, conciso.",
  },
  dev: {
    label: "Dev",
    persona:
      "Voce e o DEV deste projeto. Implemente o que for pedido pelo menor caminho que entrega valor, sem cerimonia. Commits pequenos. pt-BR, conciso.",
  },
  claude: { label: "Claude", persona: null }, // claude puro, sem persona
  shell: { label: "Shell", persona: null, shell: true }, // terminal cru
};

// Instrucoes que viram parte do system-prompt dos agentes-de-papel quando eles
// nascem numa lousa: como controlar o canvas pelo CLI (que aparece ao vivo na tela).
const CANVAS_GUIDE = [
  "CONTROLE DA LOUSA (visual, ao vivo para o usuario): voce e um node numa lousa de agentes do Hub.",
  "Voce PODE criar outros agentes e conexoes — eles aparecem na hora na tela. Use o CLI pelo Bash:",
  '- Criar agente ligado a voce: node "$HUB_LOUSA" spawn --role <reviewer|tester|dev|orchestrator> --task "<o que ele faz>" [--project <id>]',
  '- Conectar voce a outro node: node "$HUB_LOUSA" connect <nodeId>',
  '- Listar os nodes da lousa: node "$HUB_LOUSA" list',
  '- Post-it na lousa: node "$HUB_LOUSA" note "<texto>"',
  '- Atualizar seu status (sai no seu cabecalho): node "$HUB_LOUSA" status "<texto curto>"',
  "Crie agentes SO quando dividir o trabalho ajudar de verdade — nao crie a toa.",
  "HUB_NODE (seu id), HUB_BOARD e HUB_PORT ja estao no ambiente; o CLI usa sozinho.",
].join("\n");

// AUTONOMIA TOTAL: abre os agentes com --dangerously-skip-permissions (pedido do
// usuario). ATENCAO: o agente roda QUALQUER ferramenta SEM pedir confirmacao —
// edita/apaga arquivos, roda bash arbitrario, git, etc. Os agentes rodam na pasta
// REAL do projeto (nao em worktree isolado), entao isso vale pro repo de verdade.
// Risco extra: prompt-injection via conteudo de arquivos/README do repo. Para
// desligar, ponha false (ai cada ferramenta volta a pedir confirmacao no terminal).
const SKIP_PERMISSIONS = true;

const sessions = new Map(); // id -> session
let seq = 0;

function genId() {
  return "t" + (++seq).toString(36) + Date.now().toString(36).slice(-4);
}

// Monta argv a partir do role. NUNCA usa shell (node-pty faz exec direto).
// boardId presente => agente nasce numa lousa: ganha o guia de controle do canvas
// e a pre-aprovacao do CLI. A flag --allowedTools e variadica, entao vai por ULTIMO
// (e a tarefa, posicional, vai por PRIMEIRO pra nao ser engolida).
function buildSpawn(role, projectPath, task, boardId) {
  const def = ROLES[role] || ROLES.claude;
  if (def.shell) {
    return { file: resolveCommand(process.env.ComSpec || "cmd.exe"), args: [] };
  }
  const args = [];
  const t = (task || "").replace(/\r?\n/g, " ").trim();
  if (t) args.push(t.slice(0, 4000)); // prompt posicional primeiro
  if (SKIP_PERMISSIONS) args.push("--dangerously-skip-permissions"); // autonomia total
  let persona = def.persona;
  if (persona && boardId) persona += "\n\n" + CANVAS_GUIDE;
  if (persona) args.push("--append-system-prompt", persona);
  return { file: resolveCommand("claude"), args };
}

function create({ projectId, projectName, projectPath, role = "claude", task = "", label, boardId, nodeId, env }) {
  const id = genId();
  const { file, args } = buildSpawn(role, projectPath, task, boardId);
  const cwd = projectPath || os.homedir();

  let term;
  try {
    term = pty.spawn(file, args, {
      name: "xterm-256color",
      cols: DEFAULT_COLS,
      rows: DEFAULT_ROWS,
      cwd,
      env: env ? { ...process.env, ...env } : process.env,
    });
  } catch (e) {
    return { error: "Falha ao abrir o terminal: " + (e && e.message) };
  }

  const session = {
    id,
    projectId: projectId || null,
    projectName: projectName || null,
    role,
    label: label || (ROLES[role] || ROLES.claude).label,
    cwd,
    cmd: file + (args.length ? " " + args.join(" ") : ""),
    cols: DEFAULT_COLS,
    rows: DEFAULT_ROWS,
    status: "running",
    createdAt: Date.now(),
    buffer: "", // scrollback (string, truncado a SCROLLBACK_BYTES)
    term,
    clients: new Set(), // sockets WS anexados
  };
  sessions.set(id, session);

  term.onData((data) => {
    session.buffer += data;
    if (session.buffer.length > SCROLLBACK_BYTES) {
      session.buffer = session.buffer.slice(session.buffer.length - SCROLLBACK_BYTES);
    }
    broadcast(session, data);
  });

  term.onExit(({ exitCode }) => {
    session.status = "exited";
    session.exitCode = exitCode;
    const note = `\r\n\x1b[90m[sessao encerrada — codigo ${exitCode}]\x1b[0m\r\n`;
    session.buffer += note;
    broadcast(session, note);
    for (const ws of session.clients) {
      try { ws.send(JSON.stringify({ type: "exit", exitCode })); } catch {}
    }
  });

  return { session };
}

function broadcast(session, data) {
  const msg = JSON.stringify({ type: "data", data });
  for (const ws of session.clients) {
    try { ws.send(msg); } catch {}
  }
}

function attach(session, ws) {
  session.clients.add(ws);
  // replay do scrollback pro cliente que acabou de chegar
  try {
    ws.send(JSON.stringify({ type: "data", data: session.buffer }));
    ws.send(JSON.stringify({ type: "meta", status: session.status, cols: session.cols, rows: session.rows }));
  } catch {}
}

function detach(session, ws) {
  session.clients.delete(ws);
}

function write(session, data) {
  if (session.status === "running") {
    try { session.term.write(data); } catch {}
  }
}

function resize(session, cols, rows) {
  cols = Math.max(2, Math.min(500, Number(cols) | 0));
  rows = Math.max(1, Math.min(300, Number(rows) | 0));
  if (!cols || !rows) return;
  session.cols = cols;
  session.rows = rows;
  if (session.status === "running") {
    try { session.term.resize(cols, rows); } catch {}
  }
}

function kill(id) {
  const s = sessions.get(id);
  if (!s) return false;
  try { s.term.kill(); } catch {}
  s.status = "exited";
  return true;
}

function remove(id) {
  const s = sessions.get(id);
  if (!s) return false;
  try { s.term.kill(); } catch {}
  for (const ws of s.clients) {
    try { ws.close(); } catch {}
  }
  sessions.delete(id);
  return true;
}

function get(id) {
  return sessions.get(id) || null;
}

// metadados (sem buffer nem handles) p/ a listagem na UI
function meta(s) {
  return {
    id: s.id,
    projectId: s.projectId,
    projectName: s.projectName,
    role: s.role,
    label: s.label,
    cwd: s.cwd,
    status: s.status,
    createdAt: s.createdAt,
    clients: s.clients.size,
  };
}

function list() {
  return [...sessions.values()].map(meta);
}

module.exports = { ROLES, create, attach, detach, write, resize, kill, remove, get, list, meta };
