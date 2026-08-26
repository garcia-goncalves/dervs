/* canvas.js — a Lousa de agentes do Hub.
   Cada node e um terminal (xterm) ligado por WebSocket a um PTY que vive no
   servidor. Fechar/recarregar o navegador NAO mata a sessao: ao reabrir, o
   terminal se reanexa e recebe o scrollback. Pan/zoom, drag, conexoes e notas
   sao persistidos por lousa em canvas.json. */

(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const viewport = $("#viewport");
  const world = $("#world");
  const edgesSvg = $("#edges");

  // ---- estado ----
  const params = new URLSearchParams(location.search);
  const boardId = params.get("board"); // null => mostra o seletor de lousas
  let state = { nodes: [], edges: [], notes: [], viewport: { x: 120, y: 80, scale: 1 } };
  let projects = [];
  let roles = [];
  let liveSessions = new Set();

  const els = {};   // nodeId -> elemento DOM do node
  const terms = {}; // nodeId -> { term, fit, ws, fitFn, reconnectTimer }
  const noteEls = {}; // noteId -> elemento

  let connectFrom = null; // modo conectar: id do node de origem

  // ---- util ----
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg; t.classList.add("show");
    clearTimeout(t._tm); t._tm = setTimeout(() => t.classList.remove("show"), 2200);
  }
  async function api(method, path, body) {
    const opt = { method, headers: {} };
    if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    const r = await fetch(path, opt);
    return r.json();
  }

  // ---- persistencia (debounced) ----
  let saveTimer = null;
  function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      api("PUT", "/api/canvas/" + encodeURIComponent(boardId), {
        nodes: state.nodes, edges: state.edges, notes: state.notes, viewport: state.viewport,
      });
    }, 500);
  }

  // ---- transform / coordenadas ----
  function applyTransform() {
    const v = state.viewport;
    world.style.transform = `translate(${v.x}px, ${v.y}px) scale(${v.scale})`;
  }
  // ponto na tela (relativo ao viewport) -> mundo
  function screenToWorld(sx, sy) {
    const v = state.viewport;
    return { x: (sx - v.x) / v.scale, y: (sy - v.y) / v.scale };
  }

  // ---- transicoes de camera (igual Maestri: aproxima/afasta com suavidade) ----
  let camAnim = null;
  function animateCamera(tx, ty, ts, dur = 520) {
    const v = state.viewport;
    const sx = v.x, sy = v.y, ss = v.scale;
    if (camAnim) cancelAnimationFrame(camAnim);
    const start = performance.now();
    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2); // easeInOutCubic
    function step(now) {
      const p = Math.min(1, (now - start) / dur), e = ease(p);
      v.x = sx + (tx - sx) * e; v.y = sy + (ty - sy) * e; v.scale = ss + (ts - ss) * e;
      applyTransform();
      if (p < 1) camAnim = requestAnimationFrame(step);
      else { camAnim = null; save(); }
    }
    camAnim = requestAnimationFrame(step);
  }
  // enquadra todos os nodes (visao de cima)
  function fitAll() {
    if (!state.nodes.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of state.nodes) {
      const w = n.w || 460, h = n.h || 320;
      minX = Math.min(minX, n.x); minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x + w); maxY = Math.max(maxY, n.y + h);
    }
    const pad = 90, rect = viewport.getBoundingClientRect();
    const scale = Math.max(0.25, Math.min(1.3, Math.min(rect.width / (maxX - minX + pad * 2), rect.height / (maxY - minY + pad * 2))));
    const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    animateCamera(rect.width / 2 - cx * scale, rect.height / 2 - cy * scale, scale);
  }
  // voa e aproxima de um node
  function focusNode(id) {
    const n = state.nodes.find((x) => x.id === id); if (!n) return;
    const rect = viewport.getBoundingClientRect();
    const w = n.w || 460, h = n.h || 320;
    const scale = Math.max(0.5, Math.min(1.6, Math.min((rect.width - 120) / w, (rect.height - 120) / h)));
    const cx = n.x + w / 2, cy = n.y + h / 2;
    animateCamera(rect.width / 2 - cx * scale, rect.height / 2 - cy * scale, scale);
  }

  // ====================================================================
  //  NODES + TERMINAIS
  // ====================================================================

  function roleLabel(role) {
    const r = roles.find((x) => x.id === role);
    return r ? r.label : role;
  }

  function renderNode(node) {
    let el = els[node.id];
    if (!el) {
      el = document.createElement("div");
      el.className = "node";
      el.dataset.role = node.role;
      el.dataset.id = node.id;
      el.innerHTML = `
        <div class="head">
          <span class="dot"></span>
          <span class="role"></span>
          <span class="proj"></span>
          <span class="grow"></span>
          <span class="pill"></span>
          <button class="paste" title="Colar texto da área de transferência neste agente (ou botão direito no terminal)">📋</button>
          <button class="link" title="Conectar a outro node">⛓</button>
          <button class="kill" title="Encerrar processo">■</button>
          <button class="del" title="Remover da lousa">✕</button>
        </div>
        <div class="body"></div>
        <div class="resize"></div>`;
      world.appendChild(el);
      els[node.id] = el;

      // arrastar pelo cabecalho (ou completar conexao no modo conectar)
      const head = $(".head", el);
      head.addEventListener("mousedown", (e) => {
        if (e.target.closest("button")) return;
        if (connectFrom && connectFrom !== node.id) { completeConnect(node.id); return; }
        if (connectFrom === node.id) return;
        startDragNode(e, node);
      });
      head.addEventListener("dblclick", (e) => { if (!e.target.closest("button")) focusNode(node.id); });
      $(".paste", el).addEventListener("click", () => pasteInto(node));
      $(".link", el).addEventListener("click", () => beginConnect(node.id));
      $(".kill", el).addEventListener("click", () => killNode(node));
      $(".del", el).addEventListener("click", () => removeNode(node));
      $(".resize", el).addEventListener("mousedown", (e) => startResizeNode(e, node));
      el.addEventListener("mousedown", () => selectNode(node.id), true);
    }
    el.dataset.role = node.role;
    el.style.left = node.x + "px";
    el.style.top = node.y + "px";
    el.style.width = (node.w || 460) + "px";
    el.style.height = (node.h || 320) + "px";
    $(".role", el).textContent = node.label || roleLabel(node.role);
    $(".proj", el).textContent = node.projectName ? "[" + node.projectName + "]" : "";
    $(".pill", el).textContent = roleLabel(node.role);
    return el;
  }

  function selectNode(id) {
    Object.values(els).forEach((e) => e.classList.remove("sel"));
    if (els[id]) els[id].classList.add("sel");
  }

  function setDot(node, status) {
    const el = els[node.id]; if (!el) return;
    const dot = $(".dot", el);
    dot.className = "dot " + (status || "");
  }

  // monta o xterm e conecta ao PTY via WebSocket
  function mountTerminal(node) {
    const el = els[node.id];
    const body = $(".body", el);
    body.className = "term"; body.innerHTML = "";

    const term = new Terminal({
      fontSize: 12, fontFamily: 'ui-monospace, "Cascadia Code", Consolas, monospace',
      cursorBlink: true, scrollback: 5000, allowProposedApi: true,
      theme: { background: "#000000", foreground: "#cdd6e0", cursor: "#58a6ff",
        selectionBackground: "#264f78", black: "#0d1117", brightBlack: "#6e7681" },
    });
    const fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    try { term.loadAddon(new WebLinksAddon.WebLinksAddon()); } catch {}
    term.open(body);
    try { fit.fit(); } catch {}

    // botao direito do mouse cola o conteudo da area de transferencia (estilo terminal)
    body.addEventListener("contextmenu", (e) => { e.preventDefault(); pasteInto(node); });

    const rec = { term, fit, ws: null, fitFn: null, reconnectTimer: null };
    terms[node.id] = rec;

    const sendResize = () => {
      try { fit.fit(); } catch {}
      if (rec.ws && rec.ws.readyState === 1) rec.ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
    };
    rec.fitFn = sendResize;

    term.onData((d) => { if (rec.ws && rec.ws.readyState === 1) rec.ws.send(JSON.stringify({ type: "input", data: d })); });

    function connect() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws/term?id=${encodeURIComponent(node.sessionId)}`);
      rec.ws = ws;
      ws.onopen = () => { setDot(node, "running"); sendResize(); };
      ws.onmessage = (ev) => {
        let m; try { m = JSON.parse(ev.data); } catch { return; }
        if (m.type === "data") term.write(m.data);
        else if (m.type === "meta") setDot(node, m.status === "running" ? "running" : "exited");
        else if (m.type === "exit") setDot(node, "exited");
      };
      ws.onclose = () => {
        // reconecta automaticamente enquanto o node existir e a sessao estiver viva
        if (!els[node.id]) return;
        rec.reconnectTimer = setTimeout(connect, 1200);
      };
      ws.onerror = () => { try { ws.close(); } catch {} };
    }
    connect();
  }

  // placeholder "na fila": o node ja aparece na lousa antes do processo subir
  // (criacao escalonada). Vira terminal quando o sessionId chega (node_updated).
  function showQueued(node) {
    const el = els[node.id];
    const body = $(".body", el);
    body.className = "reopen";
    body.innerHTML = `<div>Na fila — abrindo em instantes…</div>`;
    setDot(node, "queued");
  }

  // mostra overlay "reabrir" quando a sessao nao existe mais (ex.: servidor reiniciou)
  function showReopen(node) {
    const el = els[node.id];
    const body = $(".body", el);
    body.className = "reopen";
    body.innerHTML = `<div>Sessão encerrada</div>`;
    const b = document.createElement("button");
    b.textContent = "Reabrir terminal";
    b.onclick = () => reopenNode(node);
    body.appendChild(b);
    setDot(node, "exited");
  }

  async function reopenNode(node) {
    const r = await api("POST", "/api/term", { role: node.role, projectId: node.projectId || undefined, label: node.label });
    if (!r.ok) { toast(r.msg || "Falha ao reabrir"); return; }
    node.sessionId = r.session.id;
    liveSessions.add(r.session.id);
    save();
    mountTerminal(node);
  }

  function killNode(node) {
    if (node.sessionId) api("POST", "/api/term/" + node.sessionId + "/kill");
    setDot(node, "exited");
    toast("Processo encerrado.");
  }

  // cola o texto da area de transferencia DENTRO do terminal deste node.
  // usa term.paste() => bracketed paste (texto multilinha entra como UM bloco,
  // sem submeter linha a linha) e segue pelo onData -> WS -> PTY.
  async function pasteInto(node) {
    const rec = terms[node.id];
    if (!rec || !rec.ws || rec.ws.readyState !== 1) { toast("Terminal não conectado."); return; }
    let text = "";
    try { text = await navigator.clipboard.readText(); }
    catch { toast("Sem acesso à área de transferência (permita no navegador)."); return; }
    if (!text) { toast("Área de transferência vazia."); return; }
    rec.term.focus();
    rec.term.paste(text);
    toast("Colado (" + text.length + " caracteres).");
  }

  function removeNode(node) {
    if (!confirm("Remover este node da lousa? (encerra o processo)")) return;
    api("POST", `/api/canvas/${encodeURIComponent(boardId)}/remove-node`, { nodeId: node.id });
    applyNodeRemoved(node.id); // teardown imediato (echo do SSE e idempotente)
  }

  // ---- aplicadores de eventos (SSE) — caminho unico p/ UI e agente ----
  function applyNodeAdded(node) {
    if (els[node.id]) return;
    if (!state.nodes.some((n) => n.id === node.id)) state.nodes.push(node);
    renderNode(node);
    if (node.sessionId) { liveSessions.add(node.sessionId); mountTerminal(node); }
    else if (node.status === "queued") showQueued(node);
    else showReopen(node);
    redrawEdges();
  }
  function applyNodeRemoved(nodeId) {
    const rec = terms[nodeId];
    if (rec) { clearTimeout(rec.reconnectTimer); try { rec.ws && rec.ws.close(); } catch {} try { rec.term.dispose(); } catch {} delete terms[nodeId]; }
    if (els[nodeId]) { els[nodeId].remove(); delete els[nodeId]; }
    state.nodes = state.nodes.filter((n) => n.id !== nodeId);
    state.edges = state.edges.filter((e) => e.from !== nodeId && e.to !== nodeId);
    redrawEdges();
  }
  function applyEdgeAdded(edge) {
    if (state.edges.some((e) => e.id === edge.id || (e.from === edge.from && e.to === edge.to) || (e.from === edge.to && e.to === edge.from))) return;
    state.edges.push(edge); redrawEdges();
  }
  function applyEdgeRemoved(edgeId) { state.edges = state.edges.filter((e) => e.id !== edgeId); redrawEdges(); }
  function applyNoteAdded(note) {
    if (noteEls[note.id]) return;
    if (!state.notes.some((n) => n.id === note.id)) state.notes.push(note);
    renderNote(note);
  }
  function applyNoteRemoved(noteId) {
    if (noteEls[noteId]) { noteEls[noteId].remove(); delete noteEls[noteId]; }
    state.notes = state.notes.filter((n) => n.id !== noteId);
  }
  function applyNodeUpdated(nodeId, patch) {
    const n = state.nodes.find((x) => x.id === nodeId); if (!n) return;
    Object.assign(n, patch);
    const el = els[nodeId]; if (!el) return;
    // saiu da fila: o processo subiu e ganhou sessionId -> monta o terminal de fato
    if (patch.sessionId && !terms[nodeId]) { liveSessions.add(patch.sessionId); mountTerminal(n); }
    if (patch.label !== undefined) $(".role", el).textContent = n.label || roleLabel(n.role);
    if (patch.status !== undefined) setDot(n, patch.status);
    if (patch.x !== undefined) el.style.left = n.x + "px";
    if (patch.y !== undefined) el.style.top = n.y + "px";
    if (patch.w !== undefined) el.style.width = (n.w || 460) + "px";
    if (patch.h !== undefined) el.style.height = (n.h || 320) + "px";
    redrawEdges();
  }

  function subscribeStream() {
    const es = new EventSource(`/api/canvas/${encodeURIComponent(boardId)}/stream`);
    es.onmessage = (e) => {
      let ev; try { ev = JSON.parse(e.data); } catch { return; }
      if (ev.type === "node_added") applyNodeAdded(ev.node);
      else if (ev.type === "node_removed") applyNodeRemoved(ev.nodeId);
      else if (ev.type === "edge_added") applyEdgeAdded(ev.edge);
      else if (ev.type === "edge_removed") applyEdgeRemoved(ev.edgeId);
      else if (ev.type === "note_added") applyNoteAdded(ev.note);
      else if (ev.type === "note_removed") applyNoteRemoved(ev.noteId);
      else if (ev.type === "node_updated") applyNodeUpdated(ev.nodeId, ev.patch);
    };
  }

  // ---- drag / resize de node ----
  function startDragNode(e, node) {
    e.preventDefault();
    selectNode(node.id);
    const scale = state.viewport.scale;
    const sx = e.clientX, sy = e.clientY, ox = node.x, oy = node.y;
    function move(ev) {
      node.x = ox + (ev.clientX - sx) / scale;
      node.y = oy + (ev.clientY - sy) / scale;
      const el = els[node.id]; el.style.left = node.x + "px"; el.style.top = node.y + "px";
      redrawEdges();
    }
    function up() { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); save(); }
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  }

  function startResizeNode(e, node) {
    e.preventDefault(); e.stopPropagation();
    const scale = state.viewport.scale;
    const sx = e.clientX, sy = e.clientY, ow = node.w || 460, oh = node.h || 320;
    function move(ev) {
      node.w = Math.max(260, ow + (ev.clientX - sx) / scale);
      node.h = Math.max(180, oh + (ev.clientY - sy) / scale);
      const el = els[node.id]; el.style.width = node.w + "px"; el.style.height = node.h + "px";
      const rec = terms[node.id]; if (rec && rec.fitFn) rec.fitFn();
      redrawEdges();
    }
    function up() { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up);
      const rec = terms[node.id]; if (rec && rec.fitFn) rec.fitFn(); save(); }
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  }

  // ====================================================================
  //  CONEXOES (edges)
  // ====================================================================
  function beginConnect(fromId) {
    connectFrom = fromId;
    $("#connHint").style.display = "";
    Object.values(els).forEach((e) => e.querySelector(".link").classList.remove("active"));
    els[fromId].querySelector(".link").classList.add("active");
  }
  function cancelConnect() {
    connectFrom = null;
    $("#connHint").style.display = "none";
    Object.values(els).forEach((e) => e.querySelector(".link").classList.remove("active"));
  }
  function completeConnect(toId) {
    if (connectFrom && toId && connectFrom !== toId) {
      api("POST", `/api/canvas/${encodeURIComponent(boardId)}/connect`, { from: connectFrom, to: toId });
      // a aresta chega pelo SSE (edge_added) e e desenhada
    }
    cancelConnect();
  }

  function nodeCenter(id) {
    const n = state.nodes.find((x) => x.id === id);
    if (!n) return null;
    return { x: n.x + (n.w || 460) / 2, y: n.y + (n.h || 320) / 2, w: n.w || 460, h: n.h || 320, nx: n.x, ny: n.y };
  }
  function redrawEdges() {
    // limpa SO as arestas (preserva o <defs> com o marcador de seta)
    edgesSvg.querySelectorAll("path.edge").forEach((p) => p.remove());
    for (const e of state.edges) {
      const a = nodeCenter(e.from), b = nodeCenter(e.to);
      if (!a || !b) continue;
      // ancora nas bordas horizontais mais proximas pra curva ficar como na imagem
      const ax = a.x < b.x ? a.nx + a.w : a.nx;
      const bx = a.x < b.x ? b.nx : b.nx + b.w;
      const ay = a.y, by = b.y;
      const dx = Math.max(40, Math.abs(bx - ax) * 0.5);
      const c1x = ax + (a.x < b.x ? dx : -dx), c2x = bx + (a.x < b.x ? -dx : dx);
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("class", "edge");
      path.setAttribute("d", `M ${ax} ${ay} C ${c1x} ${ay}, ${c2x} ${by}, ${bx} ${by}`);
      path.setAttribute("marker-end", "url(#arrow)"); // seta indica direcao pai -> filho
      edgesSvg.appendChild(path);
    }
  }

  // ====================================================================
  //  NOTAS (post-its)
  // ====================================================================
  function renderNote(note) {
    let el = noteEls[note.id];
    if (!el) {
      el = document.createElement("div");
      el.className = "note";
      el.innerHTML = `<span class="x">✕</span><textarea></textarea>`;
      world.appendChild(el);
      noteEls[note.id] = el;
      const ta = $("textarea", el);
      ta.addEventListener("input", () => { note.text = ta.value; save(); });
      ta.addEventListener("mousedown", (e) => e.stopPropagation());
      $(".x", el).addEventListener("click", () => {
        api("POST", `/api/canvas/${encodeURIComponent(boardId)}/remove-note`, { noteId: note.id });
        applyNoteRemoved(note.id);
      });
      el.addEventListener("mousedown", (e) => { if (e.target.tagName === "TEXTAREA" || e.target.classList.contains("x")) return; startDragNote(e, note); });
    }
    el.style.left = note.x + "px"; el.style.top = note.y + "px";
    $("textarea", el).value = note.text || "";
    return el;
  }
  function startDragNote(e, note) {
    e.preventDefault();
    const scale = state.viewport.scale, sx = e.clientX, sy = e.clientY, ox = note.x, oy = note.y;
    function move(ev) { note.x = ox + (ev.clientX - sx) / scale; note.y = oy + (ev.clientY - sy) / scale;
      const el = noteEls[note.id]; el.style.left = note.x + "px"; el.style.top = note.y + "px"; }
    function up() { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); save(); }
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  }

  // ====================================================================
  //  PAN / ZOOM
  // ====================================================================
  viewport.addEventListener("mousedown", (e) => {
    if (e.target !== viewport && e.target !== world && e.target !== edgesSvg) return;
    if (connectFrom) { cancelConnect(); return; }
    viewport.classList.add("panning");
    const sx = e.clientX, sy = e.clientY, ox = state.viewport.x, oy = state.viewport.y;
    function move(ev) { state.viewport.x = ox + (ev.clientX - sx); state.viewport.y = oy + (ev.clientY - sy); applyTransform(); }
    function up() { viewport.classList.remove("panning"); document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); save(); }
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  });

  viewport.addEventListener("wheel", (e) => {
    // scroll sobre um terminal rola o terminal; zoom só sobre o fundo da lousa
    if (e.target.closest(".node")) return;
    e.preventDefault();
    const v = state.viewport;
    const rect = viewport.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    // zoom suave proporcional ao delta; normaliza linhas->px e limita salto por evento
    let dy = e.deltaY;
    if (e.deltaMode === 1) dy *= 16;
    dy = Math.max(-120, Math.min(120, dy));
    const factor = Math.exp(-dy * 0.0009);
    const ns = Math.max(0.25, Math.min(2.2, v.scale * factor));
    const wx = (mx - v.x) / v.scale, wy = (my - v.y) / v.scale;
    v.scale = ns; v.x = mx - wx * ns; v.y = my - wy * ns;
    applyTransform();
    clearTimeout(viewport._zt); viewport._zt = setTimeout(save, 400);
  }, { passive: false });

  // ====================================================================
  //  MODAL criar agente
  // ====================================================================
  function openModal() {
    const mRole = $("#mRole"), mProject = $("#mProject");
    mRole.innerHTML = roles.map((r) => `<option value="${r.id}">${r.label}</option>`).join("");
    mProject.innerHTML = `<option value="">(nenhum — roda no seu HOME)</option>` +
      projects.map((p) => `<option value="${p.id}">${p.name}</option>`).join("");
    // pre-seleciona o projeto da lousa, se for uma lousa de projeto
    if (boardId !== "portfolio") mProject.value = boardId;
    $("#mTask").value = "";
    $("#modal").classList.add("show");
  }
  function closeModal() { $("#modal").classList.remove("show"); }

  async function createAgent() {
    const role = $("#mRole").value;
    const projectId = $("#mProject").value || undefined;
    const task = $("#mTask").value.trim();
    closeModal();
    const rect = viewport.getBoundingClientRect();
    const c = screenToWorld(rect.width / 2 - 230, rect.height / 2 - 160);
    const r = await api("POST", `/api/canvas/${encodeURIComponent(boardId)}/spawn`,
      { role, projectId, task, x: Math.round(c.x), y: Math.round(c.y) });
    if (!r.ok) { toast(r.msg || "Falha ao criar"); return; }
    // criacao e escalonada (fila anti-corrupcao do .claude.json): o node aparece
    // pelo SSE (node_added) quando for realmente criado.
    if (r.node) { applyNodeAdded(r.node); selectNode(r.node.id); }
    else toast("Agente na fila — abrindo em instantes…");
  }

  // ---- painel GLOBAL de agentes (todas as lousas) ----
  // lista toda sessao viva do Hub, com a funcao do papel + o que ela esta fazendo.
  // clicar leva ate o agente (foca o node; troca de lousa se for de outra).
  async function openAgents() {
    $("#agents").classList.add("show");
    const list = $("#agList");
    list.innerHTML = `<div class="empty">Carregando…</div>`;
    let agents = [];
    try { const r = await api("GET", "/api/agents"); agents = r.agents || []; }
    catch { list.innerHTML = `<div class="empty">Falha ao carregar.</div>`; return; }
    $("#agCount").textContent = agents.length ? `· ${agents.length} rodando` : "";
    if (!agents.length) { list.innerHTML = `<div class="empty">Nenhum agente rodando agora.</div>`; return; }
    list.innerHTML = "";
    for (const a of agents) list.appendChild(agentRow(a));
  }
  function closeAgents() { $("#agents").classList.remove("show"); }

  // monta a linha via DOM (textContent) — o task/label vem do agente (texto livre),
  // entao NUNCA via innerHTML, pra nao abrir XSS.
  function agentRow(a) {
    const row = document.createElement("div"); row.className = "ag";
    const dot = document.createElement("div"); dot.className = "dot"; row.appendChild(dot);
    const info = document.createElement("div"); info.className = "info";
    const top = document.createElement("div"); top.className = "top";
    const role = document.createElement("span"); role.className = "role"; role.textContent = a.roleLabel || a.role; top.appendChild(role);
    if (a.projectName) { const p = document.createElement("span"); p.className = "proj"; p.textContent = a.projectName; top.appendChild(p); }
    if (a.board === boardId) { const h = document.createElement("span"); h.className = "here"; h.textContent = "nesta lousa"; top.appendChild(h); }
    info.appendChild(top);
    if (a.roleDesc) { const d = document.createElement("div"); d.className = "desc"; d.textContent = a.roleDesc; info.appendChild(d); }
    if (a.task) { const t = document.createElement("div"); t.className = "task"; t.textContent = "▸ " + a.task; info.appendChild(t); }
    row.appendChild(info);
    row.addEventListener("click", () => gotoAgent(a));
    return row;
  }

  function gotoAgent(a) {
    if (!a.board || !a.nodeId) { toast("Agente sem node numa lousa."); return; }
    if (a.board === boardId) { closeAgents(); selectNode(a.nodeId); focusNode(a.nodeId); return; }
    location.search = "?board=" + encodeURIComponent(a.board) + "&focus=" + encodeURIComponent(a.nodeId);
  }

  // ====================================================================
  //  BOOT
  // ====================================================================
  // ---- seletor de lousas (tela inicial, sem ?board=) ----
  function renderPicker() {
    const grid = document.getElementById("pkGrid");
    const card = (id, name, meta, tags, cls) =>
      `<div class="pk ${cls || ""}" data-board="${id}">
        <div class="nm">${name}</div>
        <div class="meta">${meta}</div>
        ${tags && tags.length ? `<div class="tags">${tags.map((t) => `<span class="tag">${t}</span>`).join("")}</div>` : ""}
      </div>`;
    grid.innerHTML =
      card("portfolio", "🗂 Portfolio", "Todos os projetos numa lousa só", [], "portfolio") +
      projects.map((p) => card(p.id, p.name, "Lousa do projeto", p.tags || [])).join("");
    grid.querySelectorAll(".pk").forEach((el) =>
      el.addEventListener("click", () => { location.search = "?board=" + encodeURIComponent(el.dataset.board); })
    );
    document.getElementById("picker").classList.add("show");
  }

  async function boot() {
    const pj = await api("GET", "/api/projects");
    projects = pj.projects || [];

    // sem board na URL => tela de selecao
    if (!boardId) { renderPicker(); return; }

    // roles + sessoes vivas
    const tm = await api("GET", "/api/term");
    roles = tm.roles || [];
    liveSessions = new Set((tm.sessions || []).map((s) => s.id));

    // nome da lousa + seletor
    const boardName = boardId === "portfolio" ? "· Portfolio" : "· " + ((projects.find((p) => p.id === boardId) || {}).name || boardId);
    $("#boardName").textContent = boardName;
    const sel = $("#boardSel");
    sel.innerHTML = `<option value="portfolio">Portfolio</option>` +
      projects.map((p) => `<option value="${p.id}">${p.name}</option>`).join("");
    sel.value = boardId;
    sel.addEventListener("change", () => { location.search = "?board=" + encodeURIComponent(sel.value); });

    // carrega a lousa
    const board = await api("GET", "/api/canvas/" + encodeURIComponent(boardId));
    state.nodes = board.nodes || [];
    state.edges = board.edges || [];
    state.notes = board.notes || [];
    const savedVp = board.viewport || { x: 120, y: 80, scale: 1 };
    state.viewport = { ...savedVp };
    applyTransform();

    for (const node of state.nodes) {
      renderNode(node);
      if (node.sessionId && liveSessions.has(node.sessionId)) mountTerminal(node);
      else if (node.status === "queued" && !node.sessionId) showQueued(node);
      else showReopen(node);
    }
    for (const note of state.notes) renderNote(note);
    redrawEdges();

    subscribeStream(); // eventos ao vivo (agente criando agentes/conexoes, etc.)

    // veio do painel de agentes (?focus=nodeId): foca direto nesse node em vez da entrada
    const focusId = params.get("focus");
    if (focusId && state.nodes.some((n) => n.id === focusId)) {
      selectNode(focusId);
      requestAnimationFrame(() => focusNode(focusId));
      return;
    }

    // transicao de entrada (igual Maestri): surge um tico afastado e aproxima ate o zoom salvo
    if (state.nodes.length) {
      const rect = viewport.getBoundingClientRect();
      const cxs = rect.width / 2, cys = rect.height / 2;
      const wx = (cxs - savedVp.x) / savedVp.scale, wy = (cys - savedVp.y) / savedVp.scale;
      const startScale = savedVp.scale * 0.9;
      state.viewport = { x: cxs - wx * startScale, y: cys - wy * startScale, scale: startScale };
      applyTransform();
      requestAnimationFrame(() => animateCamera(savedVp.x, savedVp.y, savedVp.scale, 600));
    }
  }

  // ---- eventos globais ----
  $("#addAgent").addEventListener("click", openModal);
  $("#mCancel").addEventListener("click", closeModal);
  $("#mCreate").addEventListener("click", createAgent);
  $("#addNote").addEventListener("click", async () => {
    const rect = viewport.getBoundingClientRect();
    const c = screenToWorld(rect.width / 2, rect.height / 2);
    const r = await api("POST", `/api/canvas/${encodeURIComponent(boardId)}/note`, { text: "", x: Math.round(c.x), y: Math.round(c.y) });
    if (r.note) applyNoteAdded(r.note);
  });
  $("#fitAll").addEventListener("click", fitAll);
  $("#showAgents").addEventListener("click", openAgents);
  $("#agClose").addEventListener("click", closeAgents);
  $("#agents").addEventListener("click", (e) => { if (e.target.id === "agents") closeAgents(); });
  viewport.addEventListener("dblclick", (e) => { if (e.target === viewport || e.target === world || e.target === edgesSvg) fitAll(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { cancelConnect(); closeModal(); closeAgents(); }
    else if ((e.key === "0" || e.key === "1") && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) fitAll();
  });
  window.addEventListener("resize", () => { Object.values(terms).forEach((r) => r.fitFn && r.fitFn()); });

  boot();
})();
