// Ponte Telegram -> Hub de Projetos. Zero dependencias (so fetch nativo).
//
// SEGURANCA / ESCOPO:
//  - Long-polling: o bot PUXA mensagens da API do Telegram (saida da sua maquina).
//    NAO abre porta nem endpoint publico. O hub continua so em 127.0.0.1.
//  - Allowlist por DONO: o primeiro a mandar /start vira o dono (salvo em config.json);
//    depois disso, so o dono e atendido. (Ou fixe TELEGRAM_OWNER no ambiente.)
//  - Somente-leitura: so chama a API local do hub (status + chat read-only).

const fs = require("fs");
const path = require("path");
const { execFile } = require("child_process");

const HUB = process.env.HUB_URL || "http://127.0.0.1:4321";
const CFG_PATH = path.join(__dirname, "config.json");
const TOKEN_PATH = path.join(__dirname, "token.txt");

function readToken() {
  if (process.env.TELEGRAM_TOKEN) return process.env.TELEGRAM_TOKEN.trim();
  try {
    return fs.readFileSync(TOKEN_PATH, "utf8").trim();
  } catch {
    return "";
  }
}
const TOKEN = readToken();
if (!TOKEN) {
  console.error("\n[tg] FALTA O TOKEN.\n  Crie um bot com @BotFather no Telegram e cole o token em:\n  " + TOKEN_PATH + "\n  (ou defina a variavel TELEGRAM_TOKEN)\n");
  process.exit(1);
}
const API = `https://api.telegram.org/bot${TOKEN}`;

// ----- config (dono + projeto ativo) -----
function loadCfg() {
  try {
    return JSON.parse(fs.readFileSync(CFG_PATH, "utf8"));
  } catch {
    return {};
  }
}
function saveCfg(c) {
  fs.writeFileSync(CFG_PATH, JSON.stringify(c, null, 2));
}
let cfg = loadCfg();
if (process.env.TELEGRAM_OWNER) cfg.owner = Number(process.env.TELEGRAM_OWNER);

let projects = [];

// ----- helpers de rede -----
async function tg(method, body, ms = 35000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    const r = await fetch(`${API}/${method}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
      signal: ctrl.signal,
    });
    return await r.json();
  } finally {
    clearTimeout(t);
  }
}
async function api(p, opts) {
  const r = await fetch(HUB + p, opts);
  if (!r.ok) throw new Error("hub respondeu " + r.status);
  return r.json();
}
async function loadProjects() {
  projects = (await api("/api/projects")).projects || [];
  return projects;
}
function findProject(q) {
  q = (q || "").trim().toLowerCase();
  if (!q) return null;
  return (
    projects.find((p) => p.id === q || p.name.toLowerCase() === q) ||
    projects.find((p) => p.name.toLowerCase().includes(q) || p.id.includes(q)) ||
    null
  );
}

// git read-only (log). Nunca usa shell => args seguros mesmo com texto do usuario.
function git(cwd, args) {
  return new Promise((resolve) => {
    execFile("git", args, { cwd, windowsHide: true, timeout: 15000 }, (err, stdout) => {
      resolve({ ok: !err, out: (stdout || "").trim() });
    });
  });
}

// boards da lousa = "portfolio" + o id de cada projeto (mesma convencao do server/lousa.js)
function boardIdsFor() {
  return ["portfolio", ...projects.map((p) => p.id)];
}

async function lousaText(arg) {
  await loadProjects();
  let boardIds;
  if (arg) {
    if (arg.toLowerCase() === "portfolio") boardIds = ["portfolio"];
    else {
      const p = findProject(arg);
      if (!p) return `Não achei "${arg}". Mande: projetos`;
      boardIds = [p.id];
    }
  } else {
    boardIds = boardIdsFor();
  }
  const lines = [];
  for (const bid of boardIds) {
    let data;
    try {
      data = await api(`/api/canvas/${encodeURIComponent(bid)}/list`);
    } catch {
      continue;
    }
    const nodes = data.nodes || [];
    if (!nodes.length) continue;
    lines.push(`🗂 ${bid}`);
    for (const n of nodes) lines.push(`  • [${n.role}] ${n.label}${n.projectName ? " (" + n.projectName + ")" : ""} — ${n.status}`);
  }
  return lines.length ? lines.join("\n") : "(nenhum node ativo na lousa)";
}

async function agentesText() {
  const r = await api("/api/agents");
  const agents = r.agents || [];
  if (!agents.length) return "(nenhum agente rodando agora)";
  return agents
    .map((a) => {
      const proj = a.projectName ? ` ${a.projectName}` : "";
      const task = a.task ? `\n   ↳ ${a.task}` : "";
      return `🤖 [${a.roleLabel || a.role}]${proj} — lousa ${a.board || "?"}${task}`;
    })
    .join("\n\n");
}

async function commitsText(p, n = 5) {
  const r = await git(p.path, ["log", `-${n}`, "--pretty=%h %s (%ar)"]);
  if (!r.ok) return `⚠️ não consegui ler o git de ${p.name}`;
  const lines = r.out.split("\n").filter(Boolean);
  if (!lines.length) return `${p.name}: sem commits`;
  return `📝 ${p.name} — últimos commits:\n` + lines.map((l) => "• " + l).join("\n");
}

// envia texto, quebrando em pedaços de <=4000 chars (limite do Telegram = 4096)
async function send(chatId, text) {
  const s = String(text || "");
  for (let i = 0; i < s.length; i += 4000) {
    await tg("sendMessage", { chat_id: chatId, text: s.slice(i, i + 4000), disable_web_page_preview: true });
  }
}

// ----- logica de comandos -----
async function handle(textRaw) {
  const text = textRaw.replace(/^\//, ""); // aceita "/projetos" e "projetos"
  const low = text.toLowerCase().trim();

  if (["ajuda", "help", "start", "menu"].includes(low)) return helpText();

  if (["projetos", "lista", "list"].includes(low)) {
    await loadProjects();
    return "📁 Projetos:\n" + projects.map((p) => "• " + p.name).join("\n") + "\n\nUse: projeto <nome>  →  depois é só perguntar.  (status mostra o estado)";
  }

  let m;
  if ((m = text.match(/^(?:p|projeto|usar)\s+(.+)$/i))) {
    await loadProjects();
    const p = findProject(m[1]);
    if (!p) return `Não achei "${m[1]}". Mande: projetos`;
    cfg.activeProject = p.id;
    saveCfg(cfg);
    return `✅ Projeto ativo: ${p.name}\nPode perguntar à vontade, ou mande: status`;
  }

  if (low === "lousa" || low.startsWith("lousa ")) {
    return lousaText(text.slice(5).trim());
  }

  if (low === "agentes") {
    return agentesText();
  }

  if ((m = text.match(/^commits\s+(.+)$/i))) {
    await loadProjects();
    const p = findProject(m[1]);
    if (!p) return `Não achei "${m[1]}". Mande: projetos`;
    return commitsText(p);
  }

  if (low === "status" || low.startsWith("status ")) {
    await loadProjects();
    let p = cfg.activeProject ? projects.find((x) => x.id === cfg.activeProject) : null;
    const rest = text.slice(6).trim();
    if (rest) p = findProject(rest) || p;
    if (!p) return "Escolha um projeto antes: projeto <nome>";
    const st = await api(`/api/projects/${encodeURIComponent(p.id)}/status`);
    const gh = await api(`/api/projects/${encodeURIComponent(p.id)}/github`).catch(() => ({}));
    return statusText(p, st, gh);
  }

  // resto: pergunta pro Claude (read-only) no projeto ativo
  await loadProjects();
  const p = cfg.activeProject ? projects.find((x) => x.id === cfg.activeProject) : null;
  if (!p) return "Qual projeto? Mande: projeto <nome>\n\n" + projects.map((x) => "• " + x.name).join("\n");
  const r = await api("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: p.id, message: text }),
  });
  return r.reply || "(sem resposta)";
}

function statusText(p, st, gh) {
  const out = [`${p.name} — ${st.branch}`];
  out.push(`🎯 ${p.readiness || 0}% pronto p/ vendas`);
  out.push(st.changes ? `✏️ ${st.changes} alteração(ões) não commitadas` : "✅ limpo");
  if (st.ahead || st.behind) out.push(`🔄 ↑${st.ahead || 0} ↓${st.behind || 0}`);
  if (st.lastCommit) out.push(`📝 ${st.lastCommit} (${st.lastRelative})`);
  if (gh && (gh.prs || gh.issues)) out.push(`🐙 ${gh.prs || 0} PRs · ${gh.issues || 0} issues abertas`);
  return out.join("\n");
}
function helpText() {
  return [
    "🤖 Hub no Telegram",
    "",
    "• projetos — lista seus projetos",
    "• projeto <nome> — escolhe o projeto ativo",
    "• status — estado do projeto (git + GitHub)",
    "• lousa [projeto] — nodes da lousa (papel + status atual)",
    "• agentes — o que cada agente esta fazendo agora",
    "• commits <projeto> — ultimos commits",
    "• qualquer pergunta — o Claude responde (somente-leitura) sobre o projeto ativo",
    "",
    "Ex: projeto nukleoa → qual o estado pra iniciar as vendas?",
  ].join("\n");
}

// ----- loop de mensagens -----
async function onMessage(msg) {
  const chatId = msg.chat && msg.chat.id;
  const from = msg.from && msg.from.id;
  const text = (msg.text || "").trim();
  if (!chatId || !from || !text) return;

  // trust-on-first-use: primeiro /start vira o dono
  if (!cfg.owner) {
    if (/^\/?start/i.test(text) || /^\/?ajuda/i.test(text)) {
      cfg.owner = from;
      saveCfg(cfg);
      console.log("[tg] dono definido:", from);
      await send(chatId, "✅ Conectado! Você é o dono deste bot.\n\n" + helpText());
    } else {
      await send(chatId, "Mande /start para começar.");
    }
    return;
  }
  if (from !== cfg.owner) return; // allowlist: so o dono

  try {
    const reply = await handle(text);
    if (reply) await send(chatId, reply);
  } catch (e) {
    await send(chatId, "⚠️ erro: " + e.message);
  }
}

async function poll() {
  let offset = 0;
  console.log(`[tg] ponte no ar. hub: ${HUB}. ${cfg.owner ? "dono ja definido." : "aguardando /start do dono..."}`);
  // limpa o backlog (so processa mensagens novas a partir de agora)
  try {
    const r0 = await tg("getUpdates", { offset: -1, timeout: 0 }, 10000);
    if (r0.result && r0.result.length) offset = r0.result[r0.result.length - 1].update_id + 1;
  } catch {}
  while (true) {
    try {
      const r = await tg("getUpdates", { offset, timeout: 30 }, 35000);
      if (!r.ok) {
        console.error("[tg] getUpdates:", r.description || r);
        await new Promise((s) => setTimeout(s, 3000));
        continue;
      }
      for (const u of r.result || []) {
        offset = u.update_id + 1;
        if (u.message) await onMessage(u.message);
      }
    } catch (e) {
      await new Promise((s) => setTimeout(s, 2000));
    }
  }
}

(async () => {
  const me = await tg("getMe", {}, 10000).catch(() => null);
  if (!me || !me.ok) {
    console.error("[tg] token invalido ou sem internet. Verifique o token.txt.");
    process.exit(1);
  }
  console.log(`[tg] bot @${me.result.username} autenticado.`);
  try {
    await loadProjects();
    console.log(`[tg] ${projects.length} projetos carregados do hub.`);
  } catch (e) {
    console.error("[tg] hub offline? inicie o Hub primeiro. " + e.message);
  }
  poll();
})();
