// Hub de Projetos — servidor local, zero dependencias (so Node nativo).
// Bind em 127.0.0.1. Acoes recebem apenas o ID do projeto (nunca um caminho
// vindo do cliente) e um enum fixo de comandos => sem command injection.

const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFile, spawn } = require("child_process");
const WebSocket = require("ws");
const ptySessions = require("./pty-sessions");

const ROOT = __dirname;
const PORT = Number(process.env.HUB_PORT || 4321);
const CONFIG_PATH = path.join(ROOT, "projects.json");

// REDE DE SEGURANCA: o Hub gerencia muitos PTYs e sockets. Um erro solto (ex.: o
// node-pty faz fork de um helper SEM tratar 'error' — se o fork falha por excesso
// de processos/handles, vira "Unhandled 'error' event" e mataria o processo todo).
// Aqui logamos com stack em _crash.log e SEGUIMOS VIVOS, em vez de derrubar o Hub.
function logCrash(kind, err) {
  const line = `[${new Date().toISOString()}] ${kind}: ${(err && err.stack) || err}\n`;
  try { fs.appendFileSync(path.join(ROOT, "_crash.log"), line); } catch {}
  console.error("\n[Hub] " + kind + " (continuando):\n", err);
}
process.on("uncaughtException", (e) => logCrash("uncaughtException", e));
process.on("unhandledRejection", (e) => logCrash("unhandledRejection", e));

// separador de campos do git log (byte 0x1f = unit separator, nunca aparece em texto)
const SEP = "\x1f";

// ---------- helpers ----------

const READINESS_PATH = path.join(ROOT, "readiness.json");
function loadReadiness() {
  try {
    return JSON.parse(fs.readFileSync(READINESS_PATH, "utf8"));
  } catch {
    return {};
  }
}
function saveReadiness(map) {
  fs.writeFileSync(READINESS_PATH, JSON.stringify(map, null, 2));
}

function loadProjects() {
  const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
  const readiness = loadReadiness();
  // valida que cada path existe; ignora os que sumiram
  return raw.projects
    .map((p, i) => ({ id: p.id || String(i), ...p, readiness: Number(readiness[p.id || String(i)]) || 0 }))
    .filter((p) => {
      try {
        return fs.existsSync(path.join(p.path, ".git"));
      } catch {
        return false;
      }
    });
}

function findProject(id) {
  return loadProjects().find((p) => p.id === id) || null;
}

// roda um comando e devolve stdout (Promise). Nunca usa shell => args sao seguros.
function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    execFile(cmd, args, { windowsHide: true, timeout: 15000, ...opts }, (err, stdout, stderr) => {
      resolve({ ok: !err, out: (stdout || "").trim(), err: (stderr || "").trim() });
    });
  });
}

function git(p, args) {
  return run("git", ["-C", p, ...args]);
}

// owner/repo a partir do remote origin (suporta https e ssh)
function parseRepo(url) {
  if (!url) return null;
  const m = url.match(/github\.com[/:]([^/]+)\/(.+?)(?:\.git)?$/i);
  return m ? `${m[1]}/${m[2]}` : null;
}

async function gitStatus(p) {
  const [branchR, porcelainR, logR, remoteR] = await Promise.all([
    git(p, ["rev-parse", "--abbrev-ref", "HEAD"]),
    git(p, ["status", "--porcelain"]),
    git(p, ["log", "-1", `--format=%s%x1f%cr%x1f%an%x1f%cI`]),
    git(p, ["remote", "get-url", "origin"]),
  ]);

  const branch = branchR.out || "?";
  const changes = porcelainR.out ? porcelainR.out.split("\n").filter(Boolean).length : 0;
  const [subject = "", relative = "", author = "", iso = ""] = (logR.out || "").split(SEP);
  const repo = parseRepo(remoteR.out);

  // ahead/behind vs upstream (se existir)
  let ahead = 0,
    behind = 0,
    hasUpstream = false;
  const up = await git(p, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]);
  if (up.ok && up.out) {
    hasUpstream = true;
    const counts = await git(p, ["rev-list", "--left-right", "--count", `${up.out}...HEAD`]);
    if (counts.ok && counts.out) {
      const [b, a] = counts.out.split(/\s+/).map(Number);
      behind = b || 0;
      ahead = a || 0;
    }
  }

  return {
    branch,
    changes,
    ahead,
    behind,
    hasUpstream,
    lastCommit: subject,
    lastRelative: relative,
    lastAuthor: author,
    lastIso: iso,
    repo,
    githubUrl: repo ? `https://github.com/${repo}` : null,
  };
}

// GitHub via gh CLI (opcional, mais lento) — PRs e issues abertas
async function githubStatus(p) {
  const remote = await git(p, ["remote", "get-url", "origin"]);
  const repo = parseRepo(remote.out);
  if (!repo) return { repo: null, prs: null, issues: null };
  const [pr, is] = await Promise.all([
    run("gh", ["pr", "list", "-R", repo, "--state", "open", "--limit", "100", "--json", "number"]),
    run("gh", ["issue", "list", "-R", repo, "--state", "open", "--limit", "100", "--json", "number"]),
  ]);
  const count = (r) => {
    try {
      return r.ok ? JSON.parse(r.out).length : null;
    } catch {
      return null;
    }
  };
  return { repo, prs: count(pr), issues: count(is) };
}

// ---------- tasks (issues do GitHub) ----------

async function projectIssues(p) {
  const remote = await git(p, ["remote", "get-url", "origin"]);
  const repo = parseRepo(remote.out);
  if (!repo) return { repo: null, issues: [] };
  const r = await run("gh", [
    "issue", "list", "-R", repo, "--state", "open", "--limit", "30",
    "--json", "number,title,url,labels,updatedAt",
  ]);
  let issues = [];
  try {
    issues = r.ok ? JSON.parse(r.out) : [];
  } catch {
    issues = [];
  }
  return { repo, issues };
}

// ---------- insights (post-its) ----------

const INSIGHTS_PATH = path.join(ROOT, "insights.json");

function loadInsights() {
  try {
    return JSON.parse(fs.readFileSync(INSIGHTS_PATH, "utf8"));
  } catch {
    return [];
  }
}
function saveInsights(list) {
  fs.writeFileSync(INSIGHTS_PATH, JSON.stringify(list, null, 2));
}

// ---------- canvas (lousa por projeto) ----------
// Layout das lousas: nodes (posicao/tamanho/role/sessionId), edges (ligacoes) e
// notas. Persistido em canvas.json. boardId = id do projeto ou "portfolio".
// As SESSOES de terminal vivem em memoria (pty-sessions); aqui guardamos so o
// LAYOUT. Apos um restart do servidor, os nodes ficam orfaos de sessao e a UI
// oferece reabrir — mas reload do navegador reconecta normalmente.

const CANVAS_PATH = path.join(ROOT, "canvas.json");
const LOUSA_CLI = path.join(ROOT, "lousa.js");

// O SERVIDOR e a fonte da verdade da lousa. Mutacoes estruturais sao operacoes
// granulares que transmitem eventos por SSE -> o navegador (e qualquer aba) aplica
// na hora. Assim o AGENTE (via CLI) e o USUARIO (via UI) mexem pelos MESMOS caminhos,
// sem divergir. Posicoes/zoom continuam por um PUT que so faz MERGE (nunca apaga).

const boardClients = new Map(); // boardId -> Set(res)  (assinantes SSE)
let canvasSeq = 0;
function genId(p) { return p + (++canvasSeq).toString(36) + Math.random().toString(36).slice(2, 6); }

function loadCanvas() {
  try { return JSON.parse(fs.readFileSync(CANVAS_PATH, "utf8")); } catch { return { boards: {} }; }
}
function saveCanvas(data) { fs.writeFileSync(CANVAS_PATH, JSON.stringify(data, null, 2)); }
function rawBoard(boardId) {
  const data = loadCanvas();
  return data.boards[boardId] || { nodes: [], edges: [], notes: [], viewport: { x: 120, y: 80, scale: 1 } };
}
function writeBoard(boardId, board) {
  const data = loadCanvas();
  data.boards[boardId] = board;
  saveCanvas(data);
}
function broadcastBoard(boardId, ev) {
  const set = boardClients.get(boardId);
  if (!set) return;
  const data = "data: " + JSON.stringify(ev) + "\n\n";
  for (const res of set) { try { res.write(data); } catch {} }
}

function boardAddNode(boardId, node) {
  const b = rawBoard(boardId);
  if (b.nodes.length >= 200) return null;
  b.nodes.push(node); writeBoard(boardId, b);
  broadcastBoard(boardId, { type: "node_added", node });
  return node;
}
function boardRemoveNode(boardId, nodeId) {
  const b = rawBoard(boardId);
  b.nodes = b.nodes.filter((n) => n.id !== nodeId);
  b.edges = b.edges.filter((e) => e.from !== nodeId && e.to !== nodeId);
  writeBoard(boardId, b);
  broadcastBoard(boardId, { type: "node_removed", nodeId });
}
function boardAddEdge(boardId, from, to) {
  const b = rawBoard(boardId);
  if (from === to) return null;
  if (!b.nodes.some((n) => n.id === from) || !b.nodes.some((n) => n.id === to)) return null;
  if (b.edges.some((e) => (e.from === from && e.to === to) || (e.from === to && e.to === from))) return null;
  const edge = { id: genId("e"), from, to };
  b.edges.push(edge); writeBoard(boardId, b);
  broadcastBoard(boardId, { type: "edge_added", edge });
  return edge;
}
function boardRemoveEdge(boardId, edgeId) {
  const b = rawBoard(boardId);
  b.edges = b.edges.filter((e) => e.id !== edgeId);
  writeBoard(boardId, b);
  broadcastBoard(boardId, { type: "edge_removed", edgeId });
}
function boardAddNote(boardId, text, x, y) {
  const b = rawBoard(boardId);
  const note = { id: genId("note"), text: String(text || "").slice(0, 2000), x: Number(x) || 80, y: Number(y) || 80 };
  b.notes.push(note); writeBoard(boardId, b);
  broadcastBoard(boardId, { type: "note_added", note });
  return note;
}
function boardRemoveNote(boardId, noteId) {
  const b = rawBoard(boardId);
  b.notes = b.notes.filter((n) => n.id !== noteId);
  writeBoard(boardId, b);
  broadcastBoard(boardId, { type: "note_removed", noteId });
}
function boardUpdateNode(boardId, nodeId, patch) {
  const b = rawBoard(boardId);
  const n = b.nodes.find((x) => x.id === nodeId);
  if (!n) return null;
  const clean = {};
  for (const k of ["label", "status", "x", "y", "w", "h"]) if (patch[k] !== undefined) clean[k] = patch[k];
  Object.assign(n, clean);
  writeBoard(boardId, b);
  broadcastBoard(boardId, { type: "node_updated", nodeId, patch: clean });
  return n;
}
// PUT de layout: faz MERGE de posicoes/zoom/texto de notas em itens existentes.
// NUNCA cria nem apaga nada (estrutura e so pelas ops granulares) -> nao some o
// que o agente acabou de criar mesmo que a UI mande um PUT logo depois.
function boardPatchLayout(boardId, payload) {
  const b = rawBoard(boardId);
  if (Array.isArray(payload.nodes)) {
    for (const p of payload.nodes) {
      const n = b.nodes.find((x) => x.id === p.id);
      if (n) for (const k of ["x", "y", "w", "h"]) if (p[k] !== undefined) n[k] = p[k];
    }
  }
  if (Array.isArray(payload.notes)) {
    for (const p of payload.notes) {
      const note = b.notes.find((x) => x.id === p.id);
      if (note) { if (p.x !== undefined) note.x = p.x; if (p.y !== undefined) note.y = p.y; if (p.text !== undefined) note.text = String(p.text).slice(0, 2000); }
    }
  }
  if (payload.viewport && typeof payload.viewport === "object") b.viewport = payload.viewport;
  writeBoard(boardId, b);
  return b;
}
// posiciona um filho perto do pai (ou espalha se nao houver pai)
function placeNode(b, parentNodeId) {
  const parent = parentNodeId && b.nodes.find((n) => n.id === parentNodeId);
  if (parent) {
    const kids = b.edges.filter((e) => e.from === parentNodeId).length;
    return { x: Math.round((parent.x || 0) + (parent.w || 460) + 90), y: Math.round((parent.y || 0) + kids * 200) };
  }
  const i = b.nodes.length;
  return { x: 120 + (i % 4) * 510, y: 100 + Math.floor(i / 4) * 380 };
}

// ---------- chat com o Claude (headless, SOMENTE-LEITURA) ----------
// Roda `claude -p` com allowedTools de leitura (Read/Grep/Glob): o Claude le o
// repo pra responder, mas NAO executa comandos nem escreve arquivos. Sem
// --dangerously-skip-permissions => nao e uma superficie de execucao arbitraria.
// O acesso e protegido pela guarda de Host/Origin (so a UI do hub chama a API).

// ferramentas de leitura, passadas como args SEPARADOS no fim (a flag e variadica:
// `<tools...>` — se houver algo depois, ela engole). O prompt vai pelo STDIN, nao
// como argumento, evitando que a variadica coma a mensagem e qualquer mangling.
const READONLY_TOOLS = ["Read", "Grep", "Glob"];
const chatStarted = new Set(); // projectId que ja tem sessao p/ --continue

function claudeChat(project, message) {
  return new Promise((resolve) => {
    const args = ["-p"];
    if (chatStarted.has(project.id)) args.push("--continue");
    args.push("--allowedTools", ...READONLY_TOOLS); // variadica => sempre por ultimo
    const child = spawn("claude", args, { cwd: project.path, windowsHide: true });
    let out = "",
      err = "";
    const timer = setTimeout(() => {
      try {
        child.kill();
      } catch {}
      resolve({ ok: false, reply: "Tempo esgotado (o Claude demorou demais)." });
    }, 240000);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", (e) => {
      clearTimeout(timer);
      resolve({ ok: false, reply: e.message || "Falha ao iniciar o Claude." });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const text = out.trim();
      if (!text && code !== 0) {
        resolve({ ok: false, reply: err.trim() || "Falha ao chamar o Claude." });
        return;
      }
      chatStarted.add(project.id);
      resolve({ ok: true, reply: text });
    });
    child.stdin.write(message);
    child.stdin.end();
  });
}

// ---------- estimativa automatica de % (Claude read-only) ----------
// O Claude le o repo e estima o quao pronto p/ iniciar vendas (0-100). Mesmo
// modo somente-leitura do chat. Prompt via stdin; numero parseado da resposta.

function estimateReadiness(project) {
  return new Promise((resolve) => {
    const prompt = [
      "Voce e um avaliador de prontidao de produto. Analise ESTE repositorio e estime, de 0 a 100, o quao pronto o produto esta para INICIAR VENDAS (lancamento comercial real).",
      "Considere: funcionalidades core completas e funcionando, estabilidade, autenticacao e pagamentos (se aplicavel), deploy/producao configurado, ausencia de TODOs/FIXME criticos, testes, e maturidade geral pelos commits.",
      "Baseie-se em evidencias reais do repo (README, codigo, configs, package.json/.csproj, commits). Seja realista e conservador.",
      "Responda EXATAMENTE em UMA linha, neste formato e nada mais:",
      "PERCENT: <numero 0-100> | <justificativa curta em pt-BR>",
    ].join("\n");
    const child = spawn("claude", ["-p", "--allowedTools", "Read", "Grep", "Glob"], {
      cwd: project.path,
      windowsHide: true,
    });
    let out = "", err = "";
    const timer = setTimeout(() => {
      try { child.kill(); } catch {}
      resolve({ ok: false, error: "tempo esgotado" });
    }, 420000);
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (err += d));
    child.on("error", (e) => { clearTimeout(timer); resolve({ ok: false, error: e.message }); });
    child.on("close", () => {
      clearTimeout(timer);
      const m = out.match(/PERCENT:\s*(\d{1,3})/i) || out.match(/(\d{1,3})\s*%/) || out.match(/\b(\d{1,3})\b/);
      if (!m) {
        resolve({ ok: false, error: (err.trim() || "Claude nao retornou um numero.").slice(0, 200) });
        return;
      }
      const v = Math.max(0, Math.min(100, parseInt(m[1], 10)));
      const rm = out.match(/PERCENT:\s*\d{1,3}\s*[|\-–]\s*(.+)/i);
      const reason = (rm ? rm[1] : "").trim().replace(/\s+/g, " ").slice(0, 300);
      const map = loadReadiness();
      map[project.id] = v;
      saveReadiness(map);
      resolve({ ok: true, readiness: v, reason });
    });
    child.stdin.write(prompt);
    child.stdin.end();
  });
}

// ---------- Neguin: runtime de agente em STREAMING (dentro do hub) ----------
// O servidor roda o Claude em modo stream-json (entrada e saida), num git worktree
// isolado, e transmite os eventos para a UI via SSE. A interacao acontece no hub.
// Travas: worktree isolado, branch neguin/*, NUNCA push, main intocado.

const NEGUIN_PERSONA = [
  'Voce e o NEGUIN: dev lead senior e braco-direito do Andre (andgoncs) — o "Andre robo". Trabalha autonomo e ENTREGA RAPIDO.',
  "CONTEXTO: voce esta num git worktree ISOLADO, num branch neguin/*, criado so pra esta tarefa.",
  "REGRAS INVIOLAVEIS: (1) mexa SO neste worktree; (2) NUNCA rode git push/remote nem nada que saia da maquina — o main fica intocado; (3) commits pequenos conforme avanca; (4) sem segredos hardcoded.",
  "COMO AGIR (rapido e direto): planeje NA SUA CABECA em poucos segundos, SEM cerimonia e SEM despachar subagentes a toa — implemente voce mesmo com suas ferramentas. Va ao menor caminho que entrega valor real. Leia so o necessario. Rode testes quando fizer sentido. Commite ao concluir cada parte. Nao reescreva o que funciona.",
  "Ao terminar, escreva um RESUMO CURTO: o que fez, arquivos, como testar. Tudo em pt-BR e conciso (o usuario acompanha por um painel ao vivo).",
].join("\n");
const NEGUIN_MAX_CONCURRENT = 3;
const NEGUIN_START_STAGGER_MS = 20000; // gap entre inicios de agentes (anti-corrida de token/config)

// Conjunto FIXO de ferramentas seguras do Neguin (sem skip-permissions).
// Pode ler/editar/escrever/criar arquivos, rodar testes/build e git local (add/commit).
// O que NAO esta aqui (git push, rm, curl, etc.) e negado automaticamente.
const NEGUIN_TOOLS = [
  "Read", "Grep", "Glob", "Edit", "Write", "MultiEdit", "Task", "TodoWrite",
  "Bash(git status:*)", "Bash(git add:*)", "Bash(git commit:*)", "Bash(git diff:*)",
  "Bash(git log:*)", "Bash(git branch:*)", "Bash(git checkout:*)", "Bash(git restore:*)", "Bash(git stash:*)",
  "Bash(npm test:*)", "Bash(npm run:*)", "Bash(npm ci:*)", "Bash(npm install:*)",
  "Bash(pnpm test:*)", "Bash(pnpm run:*)", "Bash(pnpm install:*)", "Bash(pnpm i:*)",
  "Bash(npx vitest:*)", "Bash(npx tsc:*)", "Bash(npx eslint:*)", "Bash(node:*)",
  "Bash(dotnet build:*)", "Bash(dotnet test:*)", "Bash(dotnet restore:*)",
  "Bash(ls:*)", "Bash(cat:*)", "Bash(echo:*)", "Bash(mkdir:*)",
];

const neguinRuns = new Map(); // runId -> run
const neguinQueue = []; // runs aguardando slot
let neguinSeq = 0;

function gitP(args) {
  return new Promise((resolve) =>
    execFile("git", args, { windowsHide: true, maxBuffer: 16 * 1024 * 1024 }, (e, o, r) =>
      resolve({ ok: !e, out: (o || "").trim(), err: (r || "").trim() })
    )
  );
}

// Detecta o branch base do repo (main vs master vs HEAD do origin).
async function getBaseBranch(repoPath) {
  const sym = await gitP(["-C", repoPath, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"]);
  if (sym.ok && sym.out) return sym.out.replace(/^origin\//, "");
  for (const b of ["main", "master"]) {
    const r = await gitP(["-C", repoPath, "rev-parse", "--verify", "--quiet", b]);
    if (r.ok && r.out) return b;
  }
  const cur = await gitP(["-C", repoPath, "rev-parse", "--abbrev-ref", "HEAD"]);
  return cur.ok && cur.out ? cur.out : "main";
}

// NOTA sobre credenciais/concorrencia (corrigido apos incidente de 401):
// NAO copiamos a credencial para dirs isolados — copias ficam stale quando o token
// OAuth e rotacionado (refresh one-time-use), causando "401 Invalid credentials" em
// agentes paralelos. Em vez disso, todos usam o ~/.claude REAL (credencial sempre viva)
// e os STARTS sao escalonados (NEGUIN_START_STAGGER_MS) para que o primeiro agente
// refresque/estabilize o token antes do proximo iniciar — evitando a corrida de
// rotacao no startup e a escrita concorrente no ~/.claude.json.

function pushNeguin(run, ev) {
  ev.t = Date.now();
  run.log.push(ev);
  if (run.log.length > 2000) run.log.shift();
  if (ev.kind === "text") run.lastLine = ev.text.replace(/\s+/g, " ").slice(0, 110);
  else if (ev.kind === "tool") run.lastLine = (ev.name === "Task" ? "🤖 " : "🔧 ") + ev.name + (ev.info ? " " + ev.info : "");
  else if (ev.kind === "started") run.lastLine = "iniciando…";
  else if (ev.kind === "exit") run.lastLine = "✅ concluído";
  else if (ev.kind === "error") run.lastLine = "⚠ erro";
  else if (ev.kind === "stopped") run.lastLine = "parado";
  const data = "data: " + JSON.stringify(ev) + "\n\n";
  for (const res of run.clients) {
    try {
      res.write(data);
    } catch {}
  }
}

function neguinSay(run, message) {
  if (!run.child || (run.status !== "running" && run.status !== "done")) return false;
  const line = JSON.stringify({ type: "user", message: { role: "user", content: [{ type: "text", text: String(message) }] } }) + "\n";
  try {
    run.child.stdin.write(line);
    if (run.status === "done") run.status = "running"; // follow-up reativa
    pushNeguin(run, { kind: "you", text: String(message) });
    return true;
  } catch {
    return false;
  }
}

function briefInput(c) {
  try {
    const i = c.input || {};
    if (c.name === "Task") return i.subagent_type ? `subagente ${i.subagent_type}` : i.description || "subagente";
    if (i.file_path) return i.file_path;
    if (i.path) return i.path;
    if (i.command) return String(i.command).slice(0, 90);
    if (i.pattern) return i.pattern;
    return "";
  } catch {
    return "";
  }
}

function handleNeguinLine(run, line) {
  let ev;
  try {
    ev = JSON.parse(line);
  } catch {
    return;
  }
  if (ev.type === "system") {
    pushNeguin(run, { kind: "system", subtype: ev.subtype || "" });
  } else if (ev.type === "assistant" && ev.message && Array.isArray(ev.message.content)) {
    for (const c of ev.message.content) {
      if (c.type === "text" && c.text && c.text.trim()) pushNeguin(run, { kind: "text", text: c.text });
      else if (c.type === "tool_use") pushNeguin(run, { kind: "tool", name: c.name, info: briefInput(c) });
    }
  } else if (ev.type === "result") {
    // fim de turno: o processo segue vivo (pode receber follow-up), mas liberamos o
    // slot de concorrencia e marcamos como concluido para o proximo da fila iniciar.
    if (run.status === "running") run.status = "done";
    pushNeguin(run, { kind: "turn_done", isError: !!ev.is_error });
    pumpNeguin();
  }
}

// cria o run em estado "fila" e tenta iniciar (respeitando o limite de concorrencia)
function neguinEnqueue(project, goal) {
  const runId = "run" + ++neguinSeq;
  const run = {
    runId,
    projectId: project.id,
    projectName: project.name,
    projectPath: project.path,
    goal,
    status: "queued",
    branch: null,
    worktree: null,
    child: null,
    lastLine: "na fila",
    log: [{ kind: "queued", t: Date.now() }],
    clients: new Set(),
  };
  neguinRuns.set(runId, run);
  neguinQueue.push(run);
  pumpNeguin();
  return runId;
}

function neguinRunningCount() {
  let n = 0;
  for (const r of neguinRuns.values()) if (r.status === "running" || r.status === "starting") n++;
  return n;
}

// Inicia no maximo 1 run por vez (lock), com um gap entre starts. Isso serializa
// SO o startup (onde mora a corrida de rotacao de token e a escrita do .claude.json);
// a execucao continua paralela ate NEGUIN_MAX_CONCURRENT.
let neguinStartLock = false;
async function pumpNeguin() {
  if (neguinStartLock) return;
  if (neguinRunningCount() >= NEGUIN_MAX_CONCURRENT) return;
  const run = neguinQueue.find((r) => r.status === "queued");
  if (!run) return;
  neguinStartLock = true;
  run.status = "starting";
  try {
    await startNeguinRun(run);
  } catch (e) {
    run.status = "error";
    pushNeguin(run, { kind: "error", text: String(e && e.message) });
  }
  setTimeout(() => {
    neguinStartLock = false;
    pumpNeguin();
  }, NEGUIN_START_STAGGER_MS);
}

async function startNeguinRun(run) {
  const ts = new Date();
  const slug =
    ts.getFullYear().toString() +
    String(ts.getMonth() + 1).padStart(2, "0") +
    String(ts.getDate()).padStart(2, "0") +
    "-" +
    String(ts.getHours()).padStart(2, "0") +
    String(ts.getMinutes()).padStart(2, "0") +
    String(ts.getSeconds()).padStart(2, "0");
  const wtRoot = path.join(os.tmpdir(), "neguin");
  fs.mkdirSync(wtRoot, { recursive: true });
  const worktree = path.join(wtRoot, `${path.basename(run.projectPath)}-${run.runId}-${slug}`);
  const branch = `neguin/${run.runId}-${slug}`;
  const add = await gitP(["-C", run.projectPath, "worktree", "add", worktree, "-b", branch]);
  if (!add.ok) {
    run.status = "error";
    pushNeguin(run, { kind: "error", text: "worktree falhou: " + add.err });
    pumpNeguin();
    return;
  }
  run.worktree = worktree;
  run.branch = branch;
  run.baseBranch = await getBaseBranch(run.projectPath);
  run.status = "running";

  // usa o ~/.claude REAL (credencial sempre viva) — sem copiar config.
  const child = spawn(
    "claude",
    [
      "--print",
      "--input-format", "stream-json",
      "--output-format", "stream-json",
      "--verbose",
      "--append-system-prompt", NEGUIN_PERSONA,
      "--allowedTools", ...NEGUIN_TOOLS, // variadica => sempre por ultimo
    ],
    { cwd: worktree, windowsHide: true }
  );
  run.child = child;

  let buf = "";
  child.stdout.on("data", (d) => {
    buf += d.toString();
    let idx;
    while ((idx = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, idx);
      buf = buf.slice(idx + 1);
      if (line.trim()) handleNeguinLine(run, line);
    }
  });
  child.stderr.on("data", (d) => pushNeguin(run, { kind: "stderr", text: d.toString().slice(0, 500) }));
  child.on("error", (e) => {
    run.status = "error";
    pushNeguin(run, { kind: "error", text: e.message });
    pumpNeguin();
  });
  child.on("close", (code) => {
    if (run.status === "running") run.status = "done";
    pushNeguin(run, { kind: "exit", code, branch, worktree, repo: run.projectPath, base: run.baseBranch || "main" });
    pumpNeguin();
  });

  pushNeguin(run, { kind: "started", branch, worktree, project: run.projectName });
  neguinSay(run, run.goal);
}

// ---------- sync hook (post-commit opt-in) ----------

function hookPath(p) {
  return path.join(p, ".git", "hooks", "post-commit");
}
function hookStatus(project) {
  try {
    const c = fs.readFileSync(hookPath(project.path), "utf8");
    return c.includes("HUB-DE-PROJETOS");
  } catch {
    return false;
  }
}
function setHook(project, enable) {
  const file = hookPath(project.path);
  if (enable) {
    const body = `#!/bin/sh\n# HUB-DE-PROJETOS sync\ncurl -s -m 2 "http://127.0.0.1:${PORT}/api/touch?id=${project.id}" >/dev/null 2>&1 || true\n`;
    fs.writeFileSync(file, body);
    try {
      fs.chmodSync(file, 0o755);
    } catch {}
    return true;
  }
  try {
    if (fs.existsSync(file) && hookStatus(project)) fs.unlinkSync(file);
  } catch {}
  return false;
}

// timestamps de commit recebidos via hook (sinal de "algo mudou")
const touched = {};

// ---------- acoes (enum fixo) ----------

// Lanca processo destacado via "cmd /c start" — necessario porque wt.exe e um
// app execution alias do WindowsApps (CreateProcess direto nao executa o alias).
// Cada item de `args` vai como argumento separado (shell:false) => sem injection.
function startDetached(args) {
  const child = spawn("cmd.exe", ["/c", "start", "", ...args], {
    detached: true,
    stdio: "ignore",
    windowsHide: true,
    shell: false,
  });
  child.unref();
}

// abre o Claude Code num terminal novo na pasta do projeto. Sem prompt, abre o
// claude direto. Com prompt, gera um .cmd temporario (conteudo 100% controlado
// por nos) e o executa — evita o mangling de aspas/`;` atraves de start->wt->cmd.
function openClaude(dir, prompt) {
  if (!prompt || !prompt.trim()) {
    startDetached(["wt", "-d", dir, "cmd", "/k", "claude"]);
    return;
  }
  const safe = prompt.replace(/%/g, "%%").replace(/\r?\n/g, " ").trim();
  const file = path.join(os.tmpdir(), `hub-task-${Date.now()}.cmd`);
  const body = `@echo off\r\ncd /d "${dir}"\r\nclaude "${safe.replace(/"/g, '\\"')}"\r\n`;
  fs.writeFileSync(file, body, "utf8");
  startDetached(["wt", "-d", dir, "cmd", "/k", file]);
}

async function doAction(project, action, payload) {
  const dir = project.path;
  switch (action) {
    case "claude":
      openClaude(dir, null);
      return { ok: true, msg: "Sessao do Claude aberta." };
    case "task": {
      const prompt = String(payload?.prompt || "").slice(0, 4000);
      if (!prompt.trim()) return { ok: false, msg: "Tarefa vazia." };
      openClaude(dir, prompt);
      return { ok: true, msg: "Claude iniciado com a tarefa." };
    }
    case "code":
      startDetached(["code", dir]);
      return { ok: true, msg: "VS Code aberto." };
    case "terminal":
      startDetached(["wt", "-d", dir]);
      return { ok: true, msg: "Terminal aberto." };
    case "explorer":
      startDetached(["explorer", dir]);
      return { ok: true, msg: "Pasta aberta." };
    case "pull": {
      const r = await git(dir, ["pull", "--ff-only"]);
      return { ok: r.ok, msg: r.ok ? r.out || "Atualizado." : r.err || "Falha no pull." };
    }
    case "fetch": {
      const r = await git(dir, ["fetch", "--all", "--quiet"]);
      return { ok: r.ok, msg: r.ok ? "Fetch concluido." : r.err || "Falha no fetch." };
    }
    default:
      return { ok: false, msg: "Acao desconhecida." };
  }
}

// ---------- http ----------

function sendJson(res, code, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" });
  res.end(body);
}

function sendFile(res, file) {
  const ext = path.extname(file).toLowerCase();
  const type =
    { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".svg": "image/svg+xml" }[ext] ||
    "application/octet-stream";
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end("not found");
      return;
    }
    res.writeHead(200, { "Content-Type": `${type}; charset=utf-8` });
    res.end(data);
  });
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => {
      data += c;
      if (data.length > 1e6) req.destroy();
    });
    req.on("end", () => {
      try {
        resolve(data ? JSON.parse(data) : {});
      } catch {
        resolve({});
      }
    });
  });
}

// so aceita requisicoes cujo Host seja o proprio hub (bloqueia DNS-rebinding) e,
// se houver Origin/Referer, que seja a propria origem (bloqueia CSRF de sites).
const ALLOWED_HOSTS = new Set([`127.0.0.1:${PORT}`, `localhost:${PORT}`]);
function sameOrigin(req) {
  const host = String(req.headers.host || "").toLowerCase();
  if (!ALLOWED_HOSTS.has(host)) return false;
  const o = req.headers.origin || req.headers.referer;
  if (o) {
    try {
      const h = new URL(o).host.toLowerCase();
      if (!ALLOWED_HOSTS.has(h)) return false;
    } catch {
      return false;
    }
  }
  return true;
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathname = url.pathname;

  // a guarda nao se aplica ao hook local /api/touch (chamado pelo git, sem Host de browser)
  if (!sameOrigin(req) && pathname !== "/api/touch") {
    res.writeHead(403, { "Content-Type": "text/plain" });
    res.end("forbidden");
    return;
  }

  try {
    // API
    if (pathname === "/api/projects") {
      return sendJson(res, 200, { projects: loadProjects() });
    }

    let m;
    if ((m = pathname.match(/^\/api\/projects\/([^/]+)\/status$/))) {
      const p = findProject(decodeURIComponent(m[1]));
      if (!p) return sendJson(res, 404, { error: "projeto nao encontrado" });
      return sendJson(res, 200, await gitStatus(p.path));
    }
    if ((m = pathname.match(/^\/api\/projects\/([^/]+)\/github$/))) {
      const p = findProject(decodeURIComponent(m[1]));
      if (!p) return sendJson(res, 404, { error: "projeto nao encontrado" });
      return sendJson(res, 200, await githubStatus(p.path));
    }
    if (pathname === "/api/action" && req.method === "POST") {
      const body = await readBody(req);
      const p = findProject(String(body.id || ""));
      if (!p) return sendJson(res, 404, { ok: false, msg: "projeto nao encontrado" });
      const result = await doAction(p, String(body.action || ""), body);
      return sendJson(res, 200, result);
    }

    // tasks (issues do GitHub)
    if ((m = pathname.match(/^\/api\/projects\/([^/]+)\/issues$/))) {
      const p = findProject(decodeURIComponent(m[1]));
      if (!p) return sendJson(res, 404, { error: "projeto nao encontrado" });
      return sendJson(res, 200, await projectIssues(p.path));
    }

    // chat com o Claude (headless, isolado)
    if (pathname === "/api/chat" && req.method === "POST") {
      const body = await readBody(req);
      const p = findProject(String(body.id || ""));
      if (!p) return sendJson(res, 404, { ok: false, reply: "projeto nao encontrado" });
      const msg = String(body.message || "").slice(0, 8000);
      if (!msg.trim()) return sendJson(res, 200, { ok: false, reply: "Mensagem vazia." });
      return sendJson(res, 200, await claudeChat(p, msg));
    }
    if (pathname === "/api/chat/reset" && req.method === "POST") {
      const body = await readBody(req);
      chatStarted.delete(String(body.id || ""));
      return sendJson(res, 200, { ok: true });
    }

    // readiness (% pronto p/ vendas) — define o valor de um projeto
    if (pathname === "/api/readiness" && req.method === "POST") {
      const body = await readBody(req);
      const p = findProject(String(body.id || ""));
      if (!p) return sendJson(res, 404, { ok: false });
      let v = Math.round(Number(body.value));
      if (!Number.isFinite(v)) v = 0;
      v = Math.max(0, Math.min(100, v));
      const map = loadReadiness();
      map[p.id] = v;
      saveReadiness(map);
      return sendJson(res, 200, { ok: true, id: p.id, readiness: v });
    }

    // readiness automatica (IA le o repo e estima)
    if ((m = pathname.match(/^\/api\/projects\/([^/]+)\/estimate$/)) && req.method === "POST") {
      const p = findProject(decodeURIComponent(m[1]));
      if (!p) return sendJson(res, 404, { ok: false, error: "projeto nao encontrado" });
      return sendJson(res, 200, await estimateReadiness(p));
    }

    // Neguin: enfileira o agente para um projeto (worktree isolado) e devolve runId
    if ((m = pathname.match(/^\/api\/projects\/([^/]+)\/neguin$/)) && req.method === "POST") {
      const p = findProject(decodeURIComponent(m[1]));
      if (!p) return sendJson(res, 404, { ok: false, msg: "projeto nao encontrado" });
      const body = await readBody(req);
      const goal = String(body.goal || "").trim().slice(0, 6000);
      if (!goal) return sendJson(res, 200, { ok: false, msg: "Descreva o objetivo." });
      const runId = neguinEnqueue(p, goal);
      return sendJson(res, 200, { ok: true, runId });
    }

    // Neguin no PORTFOLIO: dispara o agente em varios projetos (3 em paralelo, fila)
    if (pathname === "/api/neguin/portfolio" && req.method === "POST") {
      const body = await readBody(req);
      const directive = String(body.goal || "").trim().slice(0, 6000);
      if (!directive) return sendJson(res, 200, { ok: false, msg: "Descreva a diretiva." });
      const all = loadProjects();
      const ids = Array.isArray(body.projectIds) && body.projectIds.length ? body.projectIds : all.map((p) => p.id);
      const runs = [];
      for (const id of ids) {
        const p = all.find((x) => x.id === id);
        if (!p) continue;
        const goal = `DIRETIVA DO PORTFOLIO: ${directive}\n\nVoce esta no projeto "${p.name}". Avalie o que faz sentido AQUI para cumprir a diretiva e execute. Se a diretiva nao se aplicar a este projeto, diga isso em uma linha e pare.`;
        runs.push({ projectId: id, projectName: p.name, runId: neguinEnqueue(p, goal) });
      }
      return sendJson(res, 200, { ok: true, runs });
    }

    // painel do portfolio: estado de todos os runs
    if (pathname === "/api/neguin/board" && req.method === "GET") {
      const runs = [...neguinRuns.values()].map((r) => ({
        runId: r.runId,
        projectId: r.projectId,
        projectName: r.projectName,
        status: r.status,
        lastLine: r.lastLine || "",
        branch: r.branch,
      }));
      return sendJson(res, 200, { runs, running: neguinRunningCount(), queued: neguinQueue.length, max: NEGUIN_MAX_CONCURRENT });
    }

    // SSE: transmite os eventos do Neguin ao vivo para o hub
    if ((m = pathname.match(/^\/api\/neguin\/([^/]+)\/stream$/)) && req.method === "GET") {
      const run = neguinRuns.get(m[1]);
      if (!run) {
        res.writeHead(404, { "Content-Type": "text/plain" });
        res.end("run nao encontrado");
        return;
      }
      res.writeHead(200, {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      });
      res.write(":ok\n\n");
      for (const ev of run.log) res.write("data: " + JSON.stringify(ev) + "\n\n");
      run.clients.add(res);
      req.on("close", () => run.clients.delete(res));
      return; // mantem aberto
    }

    // envia uma mensagem sua para o Neguin
    if ((m = pathname.match(/^\/api\/neguin\/([^/]+)\/say$/)) && req.method === "POST") {
      const run = neguinRuns.get(m[1]);
      if (!run) return sendJson(res, 404, { ok: false });
      const body = await readBody(req);
      const ok = neguinSay(run, String(body.message || "").slice(0, 6000));
      return sendJson(res, 200, { ok });
    }

    // para o Neguin
    if ((m = pathname.match(/^\/api\/neguin\/([^/]+)\/stop$/)) && req.method === "POST") {
      const run = neguinRuns.get(m[1]);
      if (run) {
        try {
          run.child.kill();
        } catch {}
        run.status = "stopped";
        pushNeguin(run, { kind: "stopped" });
      }
      return sendJson(res, 200, { ok: true });
    }

    // insights (post-its)
    if (pathname === "/api/insights" && req.method === "GET") {
      return sendJson(res, 200, { insights: loadInsights() });
    }
    if (pathname === "/api/insights" && req.method === "POST") {
      const body = await readBody(req);
      const list = loadInsights();
      const note = {
        id: "n" + Date.now().toString(36) + Math.floor(Math.random() * 1000),
        text: String(body.text || "").slice(0, 4000),
        color: String(body.color || "amber"),
        projectId: body.projectId || null,
        createdAt: new Date().toISOString(),
      };
      list.unshift(note);
      saveInsights(list);
      return sendJson(res, 200, note);
    }
    if ((m = pathname.match(/^\/api\/insights\/([^/]+)$/)) && req.method === "PUT") {
      const body = await readBody(req);
      const list = loadInsights();
      const note = list.find((n) => n.id === m[1]);
      if (!note) return sendJson(res, 404, { error: "nao encontrado" });
      if (body.text != null) note.text = String(body.text).slice(0, 4000);
      if (body.color != null) note.color = String(body.color);
      if (body.projectId !== undefined) note.projectId = body.projectId;
      saveInsights(list);
      return sendJson(res, 200, note);
    }
    if ((m = pathname.match(/^\/api\/insights\/([^/]+)$/)) && req.method === "DELETE") {
      const list = loadInsights().filter((n) => n.id !== m[1]);
      saveInsights(list);
      return sendJson(res, 200, { ok: true });
    }

    // ---------- terminais embutidos (canvas) ----------
    // lista sessoes vivas + os roles disponiveis
    if (pathname === "/api/term" && req.method === "GET") {
      const roles = Object.entries(ptySessions.ROLES).map(([id, r]) => ({ id, label: r.label }));
      return sendJson(res, 200, { sessions: ptySessions.list(), roles });
    }
    // cria uma sessao nova (role = enum; cwd/binario saem da config do servidor)
    if (pathname === "/api/term" && req.method === "POST") {
      const body = await readBody(req);
      const role = String(body.role || "claude");
      if (!ptySessions.ROLES[role]) return sendJson(res, 400, { ok: false, msg: "role invalido" });
      let proj = null;
      if (body.projectId) {
        proj = findProject(String(body.projectId));
        if (!proj) return sendJson(res, 404, { ok: false, msg: "projeto nao encontrado" });
      }
      const r = ptySessions.create({
        projectId: proj ? proj.id : null,
        projectName: proj ? proj.name : null,
        projectPath: proj ? proj.path : null,
        role,
        task: String(body.task || "").slice(0, 4000),
        label: body.label ? String(body.label).slice(0, 60) : null,
      });
      if (r.error) return sendJson(res, 500, { ok: false, msg: r.error });
      return sendJson(res, 200, { ok: true, session: ptySessions.meta(r.session) });
    }
    if ((m = pathname.match(/^\/api\/term\/([^/]+)\/kill$/)) && req.method === "POST") {
      return sendJson(res, 200, { ok: ptySessions.kill(m[1]) });
    }
    if ((m = pathname.match(/^\/api\/term\/([^/]+)$/)) && req.method === "DELETE") {
      return sendJson(res, 200, { ok: ptySessions.remove(m[1]) });
    }

    // ---------- canvas (lousas: estrutura no servidor, eventos por SSE) ----------

    // stream de eventos ao vivo da lousa (node/edge/note add/remove/update)
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)\/stream$/)) && req.method === "GET") {
      const boardId = decodeURIComponent(m[1]);
      res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache", Connection: "keep-alive", "X-Accel-Buffering": "no" });
      res.write(":ok\n\n");
      let set = boardClients.get(boardId);
      if (!set) { set = new Set(); boardClients.set(boardId, set); }
      set.add(res);
      req.on("close", () => set.delete(res));
      return;
    }

    // criar um agente (node-terminal) na lousa — usado pela UI E pelo CLI do agente
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)\/spawn$/)) && req.method === "POST") {
      const boardId = decodeURIComponent(m[1]);
      const body = await readBody(req);
      const role = String(body.role || "claude");
      if (!ptySessions.ROLES[role]) return sendJson(res, 400, { ok: false, msg: "role invalido" });
      let proj = null;
      if (body.projectId) {
        proj = findProject(String(body.projectId));
        if (!proj) return sendJson(res, 404, { ok: false, msg: "projeto nao encontrado" });
      }
      const b = rawBoard(boardId);
      const parentNodeId = body.parentNodeId && b.nodes.some((n) => n.id === body.parentNodeId) ? body.parentNodeId : null;
      const pos = body.x != null && body.y != null ? { x: Math.round(body.x), y: Math.round(body.y) } : placeNode(b, parentNodeId);
      const nodeId = genId("n");
      const env = { HUB_PORT: String(PORT), HUB_BOARD: boardId, HUB_NODE: nodeId, HUB_LOUSA: LOUSA_CLI };
      const r = ptySessions.create({
        projectId: proj ? proj.id : null, projectName: proj ? proj.name : null, projectPath: proj ? proj.path : null,
        role, task: String(body.task || "").slice(0, 4000), label: body.label ? String(body.label).slice(0, 60) : null,
        boardId, nodeId, env,
      });
      if (r.error) return sendJson(res, 500, { ok: false, msg: r.error });
      const node = { id: nodeId, sessionId: r.session.id, role, projectId: proj ? proj.id : null, projectName: proj ? proj.name : null, label: r.session.label, x: pos.x, y: pos.y, w: 460, h: 320 };
      boardAddNode(boardId, node);
      if (parentNodeId) boardAddEdge(boardId, parentNodeId, nodeId);
      return sendJson(res, 200, { ok: true, node, nodeId, sessionId: r.session.id });
    }

    // conectar dois nodes
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)\/connect$/)) && req.method === "POST") {
      const boardId = decodeURIComponent(m[1]);
      const body = await readBody(req);
      const edge = boardAddEdge(boardId, String(body.from || ""), String(body.to || ""));
      return sendJson(res, 200, { ok: !!edge, edge });
    }

    // remover node (encerra a sessao tambem)
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)\/remove-node$/)) && req.method === "POST") {
      const boardId = decodeURIComponent(m[1]);
      const body = await readBody(req);
      const b = rawBoard(boardId);
      const node = b.nodes.find((n) => n.id === String(body.nodeId || ""));
      if (node && node.sessionId) ptySessions.remove(node.sessionId);
      boardRemoveNode(boardId, String(body.nodeId || ""));
      return sendJson(res, 200, { ok: true });
    }

    // remover conexao
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)\/remove-edge$/)) && req.method === "POST") {
      const boardId = decodeURIComponent(m[1]);
      const body = await readBody(req);
      boardRemoveEdge(boardId, String(body.edgeId || ""));
      return sendJson(res, 200, { ok: true });
    }

    // post-it
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)\/note$/)) && req.method === "POST") {
      const boardId = decodeURIComponent(m[1]);
      const body = await readBody(req);
      const note = boardAddNote(boardId, body.text, body.x, body.y);
      return sendJson(res, 200, { ok: true, note });
    }
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)\/remove-note$/)) && req.method === "POST") {
      const boardId = decodeURIComponent(m[1]);
      const body = await readBody(req);
      boardRemoveNote(boardId, String(body.noteId || ""));
      return sendJson(res, 200, { ok: true });
    }

    // atualizar node (label/status/posicao)
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)\/update-node$/)) && req.method === "POST") {
      const boardId = decodeURIComponent(m[1]);
      const body = await readBody(req);
      const n = boardUpdateNode(boardId, String(body.nodeId || ""), body);
      return sendJson(res, 200, { ok: !!n, node: n });
    }

    // listar nodes da lousa (o CLI usa pra o agente se situar) — com status vivo
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)\/list$/)) && req.method === "GET") {
      const b = rawBoard(decodeURIComponent(m[1]));
      const nodes = b.nodes.map((n) => {
        const s = ptySessions.get(n.sessionId);
        return { id: n.id, role: n.role, label: n.label, projectName: n.projectName, sessionId: n.sessionId, status: s ? s.status : "gone" };
      });
      return sendJson(res, 200, { nodes, edges: b.edges });
    }

    // board completo (boot da UI) + PUT de layout (merge, nunca apaga estrutura)
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)$/)) && req.method === "GET") {
      return sendJson(res, 200, rawBoard(decodeURIComponent(m[1])));
    }
    if ((m = pathname.match(/^\/api\/canvas\/([^/]+)$/)) && req.method === "PUT") {
      const body = await readBody(req);
      return sendJson(res, 200, boardPatchLayout(decodeURIComponent(m[1]), body));
    }

    // sync hook (post-commit) — status, ativar/desativar, e ping do hook
    if ((m = pathname.match(/^\/api\/projects\/([^/]+)\/hook$/))) {
      const p = findProject(decodeURIComponent(m[1]));
      if (!p) return sendJson(res, 404, { error: "projeto nao encontrado" });
      if (req.method === "POST") {
        const body = await readBody(req);
        const enabled = setHook(p, !!body.enable);
        return sendJson(res, 200, { enabled });
      }
      return sendJson(res, 200, { enabled: hookStatus(p) });
    }
    if (pathname === "/api/touch") {
      const id = url.searchParams.get("id");
      if (id) touched[id] = Date.now();
      return sendJson(res, 200, { ok: true });
    }

    // estaticos
    if (pathname === "/" || pathname === "/index.html") {
      return sendFile(res, path.join(ROOT, "public", "index.html"));
    }
    const safe = path.normalize(pathname).replace(/^(\.\.[/\\])+/, "");
    const filePath = path.join(ROOT, "public", safe);
    if (filePath.startsWith(path.join(ROOT, "public"))) {
      return sendFile(res, filePath);
    }
    res.writeHead(404);
    res.end("not found");
  } catch (e) {
    sendJson(res, 500, { error: String(e && e.message) });
  }
});

// ---------- WebSocket: terminais embutidos persistentes ----------
// Liga o xterm.js do navegador ao PTY que vive no servidor. A MESMA guarda de
// Host/Origin do HTTP vale aqui (senao um site malicioso abriria um WS pro hub).
const wss = new WebSocket.Server({ noServer: true });

server.on("upgrade", (req, socket, head) => {
  let url;
  try {
    url = new URL(req.url, `http://localhost:${PORT}`);
  } catch {
    socket.destroy();
    return;
  }
  if (url.pathname !== "/ws/term" || !sameOrigin(req)) {
    socket.destroy();
    return;
  }
  const session = ptySessions.get(url.searchParams.get("id") || "");
  if (!session) {
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => {
    ptySessions.attach(session, ws);
    ws.on("message", (raw) => {
      let msg;
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        return;
      }
      if (msg.type === "input" && typeof msg.data === "string") ptySessions.write(session, msg.data);
      else if (msg.type === "resize") ptySessions.resize(session, msg.cols, msg.rows);
    });
    ws.on("close", () => ptySessions.detach(session, ws));
    ws.on("error", () => ptySessions.detach(session, ws));
  });
});

server.listen(PORT, "127.0.0.1", () => {
  const url = `http://127.0.0.1:${PORT}`;
  console.log(`\n  Hub de Projetos rodando em ${url}\n`);
  // abre o navegador automaticamente
  spawn("cmd.exe", ["/c", "start", "", url], { detached: true, stdio: "ignore", shell: false }).unref();
});
