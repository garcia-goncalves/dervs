#!/usr/bin/env node
// notifier.js — avisos PROATIVOS (push) do Hub pro Telegram do dono. Processo
// INDEPENDENTE do bot.js: so faz polling da API local do Hub e chamadas de saida
// pro Telegram. Nao abre porta nem endpoint publico.
//
// O que observa e avisa, sem precisar que o dono pergunte:
//  (a) worker (node da lousa) terminou / morreu / foi removido
//  (b) nota nova em qualquer lousa
//  (c) commit novo nos projetos cadastrados (projects.json)
//  (d) resumo periodico curto (agentes rodando agora)
//
// SEGURANCA:
//  - So fala com o Hub em 127.0.0.1 (rotas ja existentes: /api/projects,
//    /api/agents, /api/canvas/:board, /api/canvas/:board/list). Nenhuma rota
//    nova foi inventada.
//  - O TOKEN do Telegram nunca e logado (so usado na URL da chamada, que nunca
//    e impressa).
//  - Dedupe em disco (notifier-state.json): apos restart, nao reenvia o que ja
//    foi mandado, e nao "explode" avisando de tudo que ja existia antes de o
//    notifier existir (primeira observacao de cada lousa so semeia o estado).
//  - Backoff exponencial (2s -> 5min) em erro de rede, tanto pro Hub quanto
//    pro Telegram.

const fs = require("fs");
const path = require("path");

const HUB = `http://127.0.0.1:${process.env.HUB_PORT || 4321}`;
const DIR = __dirname;
const CFG_PATH = path.join(DIR, "config.json");
const TOKEN_PATH = path.join(DIR, "token.txt");
const STATE_PATH = path.join(DIR, "notifier-state.json");

const POLL_MS = Number(process.env.NOTIFIER_POLL_MS) || 20000; // notas + nodes
const COMMIT_POLL_MS = Number(process.env.NOTIFIER_COMMIT_POLL_MS) || 120000; // commits
const SUMMARY_MS = Number(process.env.NOTIFIER_SUMMARY_MS) || 30 * 60 * 1000; // resumo periodico

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
  console.error("[notifier] falta o token. Cole em " + TOKEN_PATH + " (ou defina TELEGRAM_TOKEN).");
  process.exit(1);
}
const TG_API = `https://api.telegram.org/bot${TOKEN}`;

function loadCfg() {
  try {
    return JSON.parse(fs.readFileSync(CFG_PATH, "utf8"));
  } catch {
    return {};
  }
}
function owner() {
  const n = Number(loadCfg().owner);
  return Number.isFinite(n) && n ? n : null;
}

function loadState() {
  try {
    const s = JSON.parse(fs.readFileSync(STATE_PATH, "utf8"));
    return { notes: s.notes || {}, nodes: s.nodes || {}, commits: s.commits || {}, lastSummary: s.lastSummary || 0 };
  } catch {
    return { notes: {}, nodes: {}, commits: {}, lastSummary: 0 };
  }
}
function saveState() {
  try {
    fs.writeFileSync(STATE_PATH, JSON.stringify(state, null, 2));
  } catch (e) {
    console.error("[notifier] nao consegui salvar notifier-state.json:", e.message);
  }
}
const state = loadState();

// ---------- envio pro Telegram (com backoff) ----------
let tgBackoffMs = 0;
async function tgSendOne(chatId, text) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 15000);
  try {
    const r = await fetch(`${TG_API}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text, disable_web_page_preview: true }),
      signal: ctrl.signal,
    });
    const j = await r.json().catch(() => ({}));
    if (!j.ok) {
      console.error("[notifier] telegram recusou o envio (codigo " + (j.error_code || "?") + ")");
      return false;
    }
    tgBackoffMs = 0;
    console.log(`[notifier] enviado (msg id ${j.result && j.result.message_id})`);
    return true;
  } catch (e) {
    tgBackoffMs = Math.min(tgBackoffMs ? tgBackoffMs * 2 : 2000, 5 * 60000);
    console.error(`[notifier] falha ao enviar pro telegram (rede). backoff ${tgBackoffMs}ms. ${e.message}`);
    await new Promise((res) => setTimeout(res, tgBackoffMs));
    return false;
  } finally {
    clearTimeout(t);
  }
}
async function sendTelegram(text) {
  const chatId = owner();
  if (!chatId) {
    console.error("[notifier] sem 'owner' definido ainda em config.json (mande /start no bot.js primeiro).");
    return false;
  }
  const s = String(text || "");
  let ok = true;
  for (let i = 0; i < s.length; i += 4000) {
    ok = (await tgSendOne(chatId, s.slice(i, i + 4000))) && ok;
  }
  return ok;
}

// ---------- API do Hub (127.0.0.1 apenas), com backoff ----------
let hubBackoffMs = 0;
async function hubGet(p) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 10000);
  try {
    const r = await fetch(HUB + p, { signal: ctrl.signal });
    if (!r.ok) throw new Error("hub respondeu " + r.status);
    const j = await r.json();
    hubBackoffMs = 0;
    return j;
  } finally {
    clearTimeout(t);
  }
}
async function safeHubGet(p) {
  try {
    return await hubGet(p);
  } catch (e) {
    hubBackoffMs = Math.min(hubBackoffMs ? hubBackoffMs * 2 : 2000, 5 * 60000);
    console.error(`[notifier] hub indisponivel em ${p}. backoff ${hubBackoffMs}ms. ${e.message}`);
    await new Promise((res) => setTimeout(res, hubBackoffMs));
    return null;
  }
}

function boardIdsFor(projects) {
  return ["portfolio", ...projects.map((p) => p.id)];
}

// ---------- (a) workers encerrados + (b) notas novas ----------
async function checkBoards(projects) {
  for (const bid of boardIdsFor(projects)) {
    const board = await safeHubGet(`/api/canvas/${encodeURIComponent(bid)}`);
    const listResp = await safeHubGet(`/api/canvas/${encodeURIComponent(bid)}/list`);
    if (!board || !listResp) continue;

    // (b) notas — primeira vez que vemos a lousa: so semeia (nao manda o historico todo)
    const firstTimeNotes = !(bid in state.notes);
    const seenNotes = new Set(state.notes[bid] || []);
    const noteIdsNow = [];
    for (const n of board.notes || []) {
      noteIdsNow.push(n.id);
      if (!firstTimeNotes && !seenNotes.has(n.id)) {
        await sendTelegram(`📌 Nota nova na lousa (${bid}):\n${n.text}`);
      }
    }
    state.notes[bid] = noteIdsNow;

    // (a) workers: transicao running -> (exited|gone) ou desaparecimento (removido)
    const firstTimeNodes = !(bid in state.nodes);
    const prevNodes = state.nodes[bid] || {};
    const nowNodes = {};
    for (const n of listResp.nodes || []) {
      nowNodes[n.id] = n.status;
      if (!firstTimeNodes && prevNodes[n.id] === "running" && n.status !== "running") {
        const proj = n.projectName ? ` (${n.projectName})` : "";
        await sendTelegram(`🔴 Worker encerrado — [${n.role}] ${n.label}${proj} · lousa "${bid}" · status: ${n.status}`);
      }
    }
    if (!firstTimeNodes) {
      for (const nid of Object.keys(prevNodes)) {
        if (prevNodes[nid] === "running" && !(nid in nowNodes)) {
          await sendTelegram(`🔴 Worker removido da lousa "${bid}" (node ${nid})`);
        }
      }
    }
    state.nodes[bid] = nowNodes;
  }
  saveState();
}

// ---------- (c) commits novos ----------
async function checkCommits(projects) {
  for (const p of projects) {
    const st = await safeHubGet(`/api/projects/${encodeURIComponent(p.id)}/status`);
    if (!st || !st.lastIso) continue;
    const key = st.lastIso + "|" + st.lastCommit;
    const prev = state.commits[p.id];
    if (prev && prev !== key) {
      await sendTelegram(`📦 Commit novo em ${p.name} (${st.branch}):\n${st.lastCommit}\n${st.lastAuthor} · ${st.lastRelative}`);
    }
    state.commits[p.id] = key;
  }
  saveState();
}

// ---------- (d) resumo periodico ----------
async function sendSummary() {
  const r = await safeHubGet("/api/agents");
  const agents = (r && r.agents) || [];
  const lines = [`🕒 Resumo — ${new Date().toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" })}`];
  if (!agents.length) {
    lines.push("Nenhum agente rodando agora.");
  } else {
    lines.push(`${agents.length} agente(s) rodando:`);
    for (const a of agents) {
      const proj = a.projectName ? ` ${a.projectName}` : "";
      const task = a.task ? ` — ${a.task}` : "";
      lines.push(`• [${a.roleLabel || a.role}]${proj} (lousa ${a.board || "?"})${task}`);
    }
  }
  await sendTelegram(lines.join("\n"));
  state.lastSummary = Date.now();
  saveState();
}

// ---------- loop principal ----------
let lastCommitCheck = 0;
async function tick() {
  const projectsResp = await safeHubGet("/api/projects");
  if (!projectsResp) return;
  const projects = projectsResp.projects || [];

  await checkBoards(projects);

  if (Date.now() - lastCommitCheck >= COMMIT_POLL_MS) {
    await checkCommits(projects);
    lastCommitCheck = Date.now();
  }

  if (Date.now() - (state.lastSummary || 0) >= SUMMARY_MS) {
    await sendSummary();
  }
}

async function main() {
  console.log(`[notifier] no ar. hub: ${HUB}. poll: ${POLL_MS}ms.`);
  while (true) {
    try {
      await tick();
    } catch (e) {
      console.error("[notifier] erro inesperado no ciclo:", e.message);
    }
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
}

main();
