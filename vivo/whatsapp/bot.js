// Ponte WhatsApp -> Hub de Projetos.
//
// SEGURANCA / ESCOPO:
//  - Usa o SEU numero (whatsapp-web.js, nao-oficial). Risco de ban/ToS — voce aceitou.
//  - Allowlist absoluta: so processa mensagens da sua "Conversa com voce mesmo"
//    (Notes to Self). Nenhum contato consegue acionar nada.
//  - Somente-leitura: so chama a API local do hub (status + chat read-only). Sem
//    acoes destrutivas pelo WhatsApp.

const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");

const HUB = process.env.HUB_URL || "http://127.0.0.1:4321";
const TAG = "\u{1F916}"; // robo — prefixo das respostas (evita loop)

let activeProject = null;
let projects = [];

async function api(path, opts) {
  const r = await fetch(HUB + path, opts);
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

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: __dirname + "/.wwebjs_auth" }),
  puppeteer: { headless: true, args: ["--no-sandbox", "--disable-setuid-sandbox"] },
});

client.on("qr", (qr) => {
  console.log("\n=== Escaneie este QR no WhatsApp ===");
  console.log("WhatsApp > Configuracoes > Aparelhos conectados > Conectar aparelho\n");
  qrcode.generate(qr, { small: true });
});
client.on("auth_failure", (m) => console.error("[wa] falha de auth:", m));
client.on("authenticated", () => console.log("[wa] autenticado."));
client.on("disconnected", (r) => console.log("[wa] desconectado:", r));
client.on("ready", async () => {
  try {
    await loadProjects();
  } catch (e) {
    console.error("[wa] hub offline? ", e.message);
  }
  console.log(`\n[wa] PRONTO. ${projects.length} projetos carregados.`);
  console.log('[wa] No WhatsApp, abra a "Conversa com voce mesmo" e mande: ajuda\n');
});

client.on("message_create", async (msg) => {
  try {
    const me = client.info && client.info.wid && client.info.wid._serialized;
    if (!me) return;
    // allowlist: SOMENTE o chat consigo mesmo
    if (msg.from !== me || msg.to !== me) return;
    const body = (msg.body || "").trim();
    if (!body || body.startsWith(TAG)) return; // ignora as proprias respostas (anti-loop)
    const reply = await handle(body);
    if (reply) await client.sendMessage(me, `${TAG} ${reply}`);
  } catch (e) {
    try {
      const me = client.info.wid._serialized;
      await client.sendMessage(me, `${TAG} erro: ${e.message}`);
    } catch {}
  }
});

async function handle(text) {
  const low = text.toLowerCase();

  if (low === "ajuda" || low === "/help" || low === "help" || low === "menu") return helpText();

  if (low === "projetos" || low === "lista" || low === "/list") {
    await loadProjects();
    return "Projetos:\n" + projects.map((p) => "• " + p.name).join("\n") + '\n\nUse: *projeto <nome>* e depois é só perguntar. *status* mostra o estado.';
  }

  let m;
  if ((m = text.match(/^(?:\/p|projeto|usar)\s+(.+)$/i))) {
    const p = findProject(m[1]);
    if (!p) return `Não achei "${m[1]}". Mande *projetos* pra ver a lista.`;
    activeProject = p;
    return `Projeto ativo: *${p.name}*. Pode perguntar à vontade, ou mande *status*.`;
  }

  if (low === "status" || low.startsWith("status ")) {
    let p = activeProject;
    const rest = text.slice(6).trim();
    if (rest) p = findProject(rest) || p;
    if (!p) return "Escolha um projeto antes: *projeto <nome>*.";
    const st = await api(`/api/projects/${encodeURIComponent(p.id)}/status`);
    const gh = await api(`/api/projects/${encodeURIComponent(p.id)}/github`).catch(() => ({}));
    return statusText(p, st, gh);
  }

  // qualquer outra coisa: pergunta pro Claude (read-only) no projeto ativo
  if (!activeProject) {
    await loadProjects();
    return "Qual projeto? Mande *projeto <nome>*:\n" + projects.map((p) => "• " + p.name).join("\n");
  }
  const r = await api("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: activeProject.id, message: text }),
  });
  return r.reply || "(sem resposta)";
}

function statusText(p, st, gh) {
  const out = [`*${p.name}* — ${st.branch}`];
  out.push(st.changes ? `✏️ ${st.changes} alteração(ões) não commitadas` : "✅ limpo");
  if (st.ahead || st.behind) out.push(`🔄 ↑${st.ahead || 0} ↓${st.behind || 0}`);
  if (st.lastCommit) out.push(`📝 ${st.lastCommit} _(${st.lastRelative})_`);
  if (gh && (gh.prs || gh.issues)) out.push(`🐙 ${gh.prs || 0} PRs · ${gh.issues || 0} issues abertas`);
  return out.join("\n");
}

function helpText() {
  return [
    "*Hub no WhatsApp* 🤖",
    "",
    "• *projetos* — lista seus projetos",
    "• *projeto <nome>* — escolhe o projeto ativo",
    "• *status* — estado do projeto (git + GitHub)",
    "• _qualquer pergunta_ — o Claude responde (somente-leitura) sobre o projeto ativo",
    "",
    "Ex: _projeto nukleoa_ → _qual o estado pra iniciar as vendas?_",
  ].join("\n");
}

console.log(`[wa] iniciando ponte... (hub: ${HUB})`);
client.initialize();
