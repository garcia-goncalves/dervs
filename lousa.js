#!/usr/bin/env node
// lousa.js — CLI que o AGENTE usa pra controlar a lousa do Hub (e voce tambem, na mao).
// Le o contexto do ambiente (injetado quando o agente nasce num node):
//   HUB_PORT  porta do Hub (padrao 4321)
//   HUB_BOARD lousa em que o agente esta
//   HUB_NODE  id do node do proprio agente (origem de connect/status)
// As mutacoes aparecem AO VIVO na lousa (o servidor transmite por SSE).
//
// Uso:
//   node lousa.js spawn --role <reviewer|tester|dev|orchestrator> [--task "..."] [--project <id>] [--label "..."]
//   node lousa.js connect <nodeId>            liga VOCE (HUB_NODE) ao node alvo
//   node lousa.js list                        lista os nodes da lousa
//   node lousa.js note "<texto>"              cria um post-it
//   node lousa.js status "<texto>"            muda o titulo do SEU node (atividade atual)
//   node lousa.js move <nodeId> <x> <y>       reposiciona um node
//   node lousa.js remove <nodeId>             remove um node (encerra a sessao)

const http = require("http");
const PORT = process.env.HUB_PORT || 4321;
const BOARD = process.env.HUB_BOARD || "portfolio";
const NODE = process.env.HUB_NODE || "";

function req(method, path, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const headers = { Host: `127.0.0.1:${PORT}` };
    if (data) { headers["Content-Type"] = "application/json"; headers["Content-Length"] = Buffer.byteLength(data); }
    const r = http.request({ host: "127.0.0.1", port: PORT, path, method, headers }, (res) => {
      let o = ""; res.on("data", (c) => (o += c));
      res.on("end", () => { try { resolve({ status: res.statusCode, json: o ? JSON.parse(o) : null }); } catch { resolve({ status: res.statusCode, raw: o }); } });
    });
    r.on("error", reject);
    if (data) r.write(data);
    r.end();
  });
}

function parseFlags(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith("--")) { const k = a.slice(2); const v = i + 1 < argv.length && !argv[i + 1].startsWith("--") ? argv[++i] : "true"; out[k] = v; }
    else out._.push(a);
  }
  return out;
}

function usage() {
  console.log([
    "uso: node lousa.js <comando> ...",
    "  spawn --role <reviewer|tester|dev|orchestrator|claude|shell> [--task \"..\"] [--project <id>] [--label \"..\"]",
    "  connect <nodeId>        liga voce (HUB_NODE) ao node alvo",
    "  list                    lista os nodes da lousa",
    "  note \"<texto>\"          post-it na lousa",
    "  status \"<texto>\"        muda o titulo do seu node",
    "  move <nodeId> <x> <y>   reposiciona",
    "  remove <nodeId>         remove (encerra a sessao)",
  ].join("\n"));
}

(async () => {
  const [cmd, ...rest] = process.argv.slice(2);
  const f = parseFlags(rest);
  const base = `/api/canvas/${encodeURIComponent(BOARD)}`;
  try {
    if (cmd === "spawn") {
      const r = await req("POST", base + "/spawn", {
        role: f.role || "dev", task: f.task && f.task !== "true" ? f.task : "",
        projectId: f.project, label: f.label && f.label !== "true" ? f.label : undefined,
        parentNodeId: NODE || undefined,
      });
      if (r.json && r.json.ok) console.log(`agente enfileirado: node ${r.json.nodeId} (sobe em alguns segundos)`);
      else { console.error("falhou:", (r.json && r.json.msg) || r.status); process.exit(1); }
    } else if (cmd === "connect") {
      const to = f._[0]; const from = f._[1] || NODE;
      if (!to) { console.error("uso: connect <nodeId>"); process.exit(1); }
      const r = await req("POST", base + "/connect", { from, to });
      console.log(r.json && r.json.ok ? `conectado ${from} -> ${to}` : "falhou (node inexistente ou ja conectado)");
    } else if (cmd === "list") {
      const r = await req("GET", base + "/list");
      const nodes = (r.json && r.json.nodes) || [];
      if (!nodes.length) console.log("(lousa vazia)");
      for (const n of nodes) console.log(`${n.id}\t[${n.role}]\t${n.label}${n.projectName ? " (" + n.projectName + ")" : ""}\t${n.status}${n.id === NODE ? "  <- voce" : ""}`);
    } else if (cmd === "note") {
      const text = f._.join(" ") || (f.text !== "true" ? f.text : "") || "";
      await req("POST", base + "/note", { text });
      console.log("nota adicionada");
    } else if (cmd === "status") {
      const text = f._.join(" ") || (f.text !== "true" ? f.text : "") || "";
      if (!NODE) { console.error("sem HUB_NODE no ambiente"); process.exit(1); }
      const r = await req("POST", base + "/update-node", { nodeId: NODE, label: text });
      console.log(r.json && r.json.ok ? "status atualizado" : "falhou");
    } else if (cmd === "move") {
      const [id, x, y] = f._;
      await req("POST", base + "/update-node", { nodeId: id, x: Number(x), y: Number(y) });
      console.log("movido");
    } else if (cmd === "remove") {
      const id = f._[0];
      if (!id) { console.error("uso: remove <nodeId>"); process.exit(1); }
      await req("POST", base + "/remove-node", { nodeId: id });
      console.log("removido " + id);
    } else {
      usage();
    }
  } catch (e) {
    console.error("erro:", e.message);
    process.exit(1);
  }
})();
