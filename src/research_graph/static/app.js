/* ═══════════════════════════════════════════════════════
   ResearchGraph — app.js (v2)
   Sidebar navigation · SSE streaming · Human-in-the-loop
   Export · Citation expansion · Collapsible sections
═══════════════════════════════════════════════════════ */

const GRAPH_KINDS = ["unified","papers","agents","experiments","reports","learning","technology","agentic"];
const STORAGE_KEY = "rg-project-id";

const NODE_COLORS = {
  paper:"#fbbf24", agent:"#60a5fa", run_stage:"#60a5fa", applied_lesson:"#60a5fa",
  experiment:"#818cf8", experiment_result:"#818cf8", run_summary:"#818cf8",
  report_section:"#f472b6", final_report:"#f472b6", draft_section:"#f472b6",
  technology:"#34d399", model:"#34d399", model_profile:"#34d399",
  taxonomy_facet:"#fb923c", learning_lesson:"#fb923c", learning_reflection:"#fb923c",
  novelty:"#a78bfa", memory_entry:"#a78bfa", artifact:"#64748b",
  run_artifact:"#64748b", project:"#64748b", runtime_run:"#64748b",
};

const KIND_LABELS = {
  paper:"Paper", agent:"Agent", run_stage:"Stage", experiment:"Experiment",
  report_section:"Report", technology:"Tech", taxonomy_facet:"Agentic",
  novelty:"Novelty", memory_entry:"Memory", artifact:"Artifact",
  run_artifact:"Artifact", runtime_run:"Run", final_report:"Report",
  draft_section:"Section", learning_lesson:"Lesson", learning_reflection:"Reflection",
  applied_lesson:"Lesson", experiment_result:"Result", run_summary:"Summary",
};

const PIPELINE_STAGES = [
  "agent-intake","agent-evidence","agent-planning-graph","agent-survey",
  "agent-planner","agent-critic","agent-grounding","agent-novelty",
  "agent-coordinator","agent-judge","agent-executor","agent-memory","agent-writer"
];

/* ── state ── */
const state = {
  projects: [],
  projectId: localStorage.getItem(STORAGE_KEY) || "demo-project",
  project: null,
  run: null,
  learning: null,
  models: null,
  activeGraphKind: "unified",
  sseSource: null,
  graphSim: null,
  currentView: "home",
};

/* ── DOM shortcuts ── */
const $ = id => document.getElementById(id);

/* ═══════════════════════════════════════════
   SIDEBAR NAVIGATION
═══════════════════════════════════════════ */
document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

function switchView(view) {
  state.currentView = view;
  document.querySelectorAll(".nav-item").forEach(b => b.classList.toggle("active", b.dataset.view === view));
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  $(`view-${view}`)?.classList.add("active");

  const titles = { home:"Home", pipeline:"Pipeline", graph:"Knowledge Graph", papers:"Papers & Memory", report:"Research Report", settings:"Settings" };
  $("view-title").textContent = titles[view] || view;

  if (view === "graph") loadAndDrawGraph();
}

/* ═══════════════════════════════════════════
   COLLAPSIBLE SECTIONS
═══════════════════════════════════════════ */
document.querySelectorAll(".collapsible").forEach(el => {
  const header = el.querySelector(".collapsible-header");
  if (header) {
    header.addEventListener("click", () => {
      const collapsed = el.dataset.collapsed === "true";
      el.dataset.collapsed = collapsed ? "false" : "true";
    });
  }
});

/* ═══════════════════════════════════════════
   EVENT WIRING
═══════════════════════════════════════════ */
$("start-btn").addEventListener("click", startResearch);
$("save-project-btn").addEventListener("click", saveProject);
$("demo-btn").addEventListener("click", loadDemo);
$("refresh-btn").addEventListener("click", () => boot());
$("error-dismiss").addEventListener("click", clearError);
$("project-selector").addEventListener("change", e => switchProject(e.target.value));
$("node-detail-close").addEventListener("click", () => $("node-detail").classList.remove("open"));
$("save-model-settings").addEventListener("click", saveModelSettings);
$("connect-ollama").addEventListener("click", connectOllama);
$("add-custom-model").addEventListener("click", addCustomModel);
$("export-md-btn").addEventListener("click", () => exportReport("md"));
$("export-latex-btn").addEventListener("click", () => exportReport("latex"));
$("expand-citations-btn").addEventListener("click", expandCitations);
$("approve-btn").addEventListener("click", () => approveRun(true));
$("reject-btn").addEventListener("click", () => approveRun(false));

boot();

/* ═══════════════════════════════════════════
   BOOT
═══════════════════════════════════════════ */
async function boot() {
  await loadProjects();
  await loadModelHub();
  renderGraphTabs();
  await loadWorkspace();
}

async function loadProjects(preferredId) {
  const data = await fetchJson("/api/projects");
  state.projects = data.projects || [];
  if (!state.projects.length) {
    state.projectId = "";
  } else {
    const id = preferredId || state.projectId;
    const match = state.projects.find(p => p.id === id);
    state.projectId = match ? match.id : state.projects[0].id;
  }
  localStorage.setItem(STORAGE_KEY, state.projectId || "");
  renderProjectSelector();
}

async function loadWorkspace() {
  if (!state.projectId) return;
  try {
    state.project = await fetchJson(`/api/projects/${state.projectId}`);
    state.learning = await fetchJson(`/api/projects/${state.projectId}/learning`);
    const runs = await fetchJson(`/api/projects/${state.projectId}/runs`);
    state.run = runs.items[0] || null;
    const [papersP, noveltyP] = await Promise.all([
      fetchJson(`/api/projects/${state.projectId}/top-papers?limit=10`),
      fetchJson(`/api/projects/${state.projectId}/novelty`),
    ]);
    renderHomeStats();
    renderPapers(papersP.items || []);
    renderNovelty(noveltyP.items || []);
    if (state.run) {
      renderRun();
      renderLearning();
      if (state.run.status === "running" || state.run.status === "queued") {
        startSSE(state.run.id);
      }
      if (state.run.status === "awaiting_approval") {
        showApproval();
      }
    }
  } catch(e) {
    showError(e.message);
  }
}

/* ═══════════════════════════════════════════
   QUERY & RUN
═══════════════════════════════════════════ */
async function startResearch() {
  const domain = $("project-domain").value.trim();
  const problem = $("project-problem").value.trim();
  if (!domain || !problem) { showError("Domain and research problem are required."); return; }
  clearError();
  const btn = $("start-btn");
  btn.disabled = true;
  btn.classList.add("running");
  $("start-btn-text").textContent = "Starting…";

  try {
    const project = await fetchJson("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: $("project-name").value.trim() || "Research Project",
        domain, problem, abstract: $("project-abstract").value.trim(),
      }),
    });
    state.projectId = project.id;
    localStorage.setItem(STORAGE_KEY, project.id);
    await loadProjects(project.id);
    state.project = project;

    const humanApproval = $("human-approval-check").checked;
    const run = await fetchJson(`/api/projects/${state.projectId}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ objective: problem, human_approval: humanApproval }),
    });
    state.run = run;
    setStatus("running");
    $("start-btn-text").textContent = "Running…";
    switchView("pipeline");
    renderStageProgress([], "queued");
    startSSE(run.id);
  } catch (err) {
    showError(err.message || "Failed to start.");
    setStatus("error");
    btn.disabled = false;
    btn.classList.remove("running");
    $("start-btn-text").textContent = "Start Research";
  }
}

async function saveProject() {
  const domain = $("project-domain").value.trim();
  const problem = $("project-problem").value.trim();
  if (!domain || !problem) { showError("Domain and problem are required."); return; }
  await fetchJson("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: $("project-name").value.trim() || "Research Project",
      domain, problem, abstract: $("project-abstract").value.trim(),
    }),
  });
  await boot();
}

async function loadDemo() {
  const res = await fetch("/api/projects/demo-project");
  if (res.ok) {
    const p = await res.json();
    $("project-name").value = p.name || "";
    $("project-domain").value = p.domain || "";
    $("project-problem").value = p.problem || "";
    $("project-abstract").value = p.abstract || "";
  }
  state.projectId = "demo-project";
  localStorage.setItem(STORAGE_KEY, "demo-project");
  await loadProjects("demo-project");
  await loadWorkspace();
}

async function switchProject(id) {
  state.projectId = id;
  localStorage.setItem(STORAGE_KEY, id);
  stopSSE();
  await loadWorkspace();
}

/* ═══════════════════════════════════════════
   SSE STREAMING (replaces polling)
═══════════════════════════════════════════ */
function startSSE(runId) {
  stopSSE();
  const source = new EventSource(`/api/runs/${runId}/stream`);
  state.sseSource = source;

  source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "update" || data.type === "approval_needed") {
        state.run = data.run;
        renderStageProgress(data.run.stages, data.run.status);
        renderRun();
        if (data.type === "approval_needed") {
          showApproval();
          setStatus("awaiting_approval");
        }
      }
      if (data.type === "done") {
        stopSSE();
        setStatus(data.status === "completed" ? "completed" : "error");
        hideApproval();
        loadWorkspace();
        const btn = $("start-btn");
        btn.disabled = false;
        btn.classList.remove("running");
        $("start-btn-text").textContent = "Start Research";
      }
    } catch (_) {}
  };

  source.onerror = () => {
    // SSE disconnected — fall back to polling
    stopSSE();
    startPolling(runId);
  };
}

function stopSSE() {
  if (state.sseSource) {
    state.sseSource.close();
    state.sseSource = null;
  }
}

// Fallback polling for when SSE isn't available
let _pollTimer = null;
function startPolling(runId) {
  stopPolling();
  _pollTimer = setInterval(async () => {
    try {
      const run = await fetchJson(`/api/runs/${runId}`);
      state.run = run;
      renderStageProgress(run.stages, run.status);
      renderRun();
      if (run.status === "awaiting_approval") {
        showApproval();
        setStatus("awaiting_approval");
      }
      if (run.status !== "running" && run.status !== "queued") {
        stopPolling();
        setStatus(run.status === "completed" ? "completed" : "error");
        hideApproval();
        loadWorkspace();
        const btn = $("start-btn");
        btn.disabled = false;
        btn.classList.remove("running");
        $("start-btn-text").textContent = "Start Research";
      }
    } catch (e) {
      stopPolling();
      showError("Lost connection: " + e.message);
    }
  }, 2000);
}
function stopPolling() { if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; } }

/* ═══════════════════════════════════════════
   HUMAN-IN-THE-LOOP APPROVAL
═══════════════════════════════════════════ */
function showApproval() {
  const decision = state.run?.artifacts?.judged_decision;
  if (decision?.decision_title) {
    $("approval-details").textContent = `Decision: "${decision.decision_title}" — Score: ${decision.vote_score?.toFixed(2) || "N/A"}. Review and approve to continue.`;
  }
  $("approval-banner").classList.add("visible");
}

function hideApproval() {
  $("approval-banner").classList.remove("visible");
}

async function approveRun(approved) {
  if (!state.run) return;
  try {
    await fetchJson(`/api/runs/${state.run.id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved }),
    });
    hideApproval();
    if (approved) {
      setStatus("running");
      startSSE(state.run.id);
    } else {
      setStatus("error");
      $("start-btn").disabled = false;
      $("start-btn").classList.remove("running");
      $("start-btn-text").textContent = "Start Research";
    }
  } catch (e) {
    showError(e.message);
  }
}

/* ═══════════════════════════════════════════
   EXPORT
═══════════════════════════════════════════ */
async function exportReport(format) {
  if (!state.run) { showError("No run to export."); return; }
  window.open(`/api/runs/${state.run.id}/export?format=${format}`);
}

/* ═══════════════════════════════════════════
   CITATION EXPANSION
═══════════════════════════════════════════ */
async function expandCitations() {
  if (!state.projectId) return;
  const btn = $("expand-citations-btn");
  btn.disabled = true;
  btn.textContent = "Expanding…";
  try {
    await fetchJson(`/api/projects/${state.projectId}/expand-citations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ depth: 1 }),
    });
    // Wait a moment then reload
    setTimeout(async () => {
      await loadWorkspace();
      btn.disabled = false;
      btn.textContent = "Expand Citations";
    }, 3000);
  } catch(e) {
    showError(e.message);
    btn.disabled = false;
    btn.textContent = "Expand Citations";
  }
}

/* ═══════════════════════════════════════════
   GRAPH
═══════════════════════════════════════════ */
function renderGraphTabs() {
  const tabs = $("graph-tabs");
  tabs.innerHTML = GRAPH_KINDS.map(k =>
    `<button class="graph-tab${state.activeGraphKind===k?" active":""}" data-kind="${k}">${prettify(k)}</button>`
  ).join("");
  tabs.querySelectorAll(".graph-tab").forEach(btn => {
    btn.addEventListener("click", async () => {
      state.activeGraphKind = btn.dataset.kind;
      renderGraphTabs();
      _resetGraph();
      await loadAndDrawGraph();
    });
  });
}

let _graph    = null;
let _graphNodeIds = new Set();
let _graphAutoFit = false;
let _hoveredNode  = null;

function _resetGraph() {
  if (_graph) { try { _graph._destructor?.(); } catch(_) {} }
  _graph = null;
  _graphNodeIds = new Set();
  _graphAutoFit = false;
  _hoveredNode  = null;
  const el = $("graph-canvas");
  if (el) el.innerHTML = "";
}

async function loadAndDrawGraph() {
  if (!state.projectId) return;
  const url = state.run
    ? `/api/runs/${state.run.id}/graphs/${state.activeGraphKind}`
    : `/api/projects/${state.projectId}/graphs/${state.activeGraphKind}`;
  try {
    const graph = await fetchJson(url);
    drawGraph(graph);
  } catch (_) {}
}

function _nodeSize(node) {
  return 4.5 + Math.min((node._deg || 0) * 0.7, 5.5);
}

function _drawNode(node, ctx, gs) {
  const x = node.x, y = node.y;
  const c   = NODE_COLORS[node.kind] || "#6b8599";
  const r   = _nodeSize(node);
  const hot = node === _hoveredNode;

  // outer halo
  const halo = ctx.createRadialGradient(x, y, r * 0.4, x, y, r * (hot ? 3.8 : 2.8));
  halo.addColorStop(0, c + (hot ? "30" : "18"));
  halo.addColorStop(1, c + "00");
  ctx.fillStyle = halo;
  ctx.beginPath(); ctx.arc(x, y, r * (hot ? 3.8 : 2.8), 0, Math.PI*2); ctx.fill();

  // translucent fill
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI*2);
  ctx.fillStyle = c + (hot ? "28" : "16"); ctx.fill();

  // ring
  ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI*2);
  ctx.strokeStyle = c + (hot ? "ff" : "bb");
  ctx.lineWidth = Math.max(0.6, (hot ? 2.0 : 1.4) / gs);
  ctx.stroke();

  // centre dot
  ctx.beginPath(); ctx.arc(x, y, Math.max(0.8, r * 0.22), 0, Math.PI*2);
  ctx.fillStyle = c + (hot ? "ff" : "dd"); ctx.fill();

  // label
  const lbl = (node.label || "").slice(0, 22) + (node.label?.length > 22 ? "…" : "");
  const alpha    = Math.min(0.85, Math.max(0.25, gs * 0.55));
  const fontSize = Math.max(2.5, Math.min(11, 10 / gs));
  ctx.font = `500 ${fontSize}px Inter, system-ui, sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  ctx.shadowColor = "rgba(0,0,0,0.9)"; ctx.shadowBlur = Math.max(1.5, 4 / gs);
  ctx.fillStyle = `rgba(203,213,225,${alpha})`;
  ctx.fillText(lbl, x, y + r + 1.8 / gs);
  ctx.shadowBlur = 0;
}

function _initGraph() {
  const el = $("graph-canvas");
  if (!el) return;
  el.innerHTML = "";
  _graphAutoFit = false; _hoveredNode = null;
  const W = el.clientWidth || 900;
  const H = el.clientHeight || 520;

  _graph = ForceGraph()(el)
    .width(W).height(H)
    .backgroundColor("#00000000")
    .nodeCanvasObject(_drawNode)
    .nodeCanvasObjectMode(() => "replace")
    .nodePointerAreaPaint((node, color, ctx) => {
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(node.x, node.y, _nodeSize(node) + 4, 0, Math.PI*2); ctx.fill();
    })
    .nodeLabel(n => {
      const c = NODE_COLORS[n.kind] || "#6b8599";
      const lbl = KIND_LABELS[n.kind] || prettify(n.kind);
      return `<div style="background:rgba(6,10,20,0.93);border:1px solid ${c}44;padding:6px 10px;border-radius:8px;font-size:12px;color:#e2e8f0;max-width:260px;line-height:1.5;box-shadow:0 8px 24px rgba(0,0,0,0.7)"><span style="color:${c};font-size:10px;font-weight:700;letter-spacing:0.07em;text-transform:uppercase;display:block;margin-bottom:2px">${lbl}</span>${esc(n.label)}</div>`;
    })
    .linkColor(l => { const s = typeof l.source==="object"?l.source:{}; return (NODE_COLORS[s.kind]||"#334155")+"40"; })
    .linkWidth(l => (l.weight||1) * 0.6)
    .linkCurvature(0.18)
    .linkDirectionalArrowLength(4)
    .linkDirectionalArrowRelPos(0.82)
    .linkDirectionalArrowColor(l => { const s = typeof l.source==="object"?l.source:{}; return (NODE_COLORS[s.kind]||"#4db8ff")+"88"; })
    .linkDirectionalParticles(2)
    .linkDirectionalParticleWidth(1.8)
    .linkDirectionalParticleSpeed(0.0045)
    .linkDirectionalParticleColor(l => { const s = typeof l.source==="object"?l.source:{}; return NODE_COLORS[s.kind]||"#4db8ff"; })
    .onNodeClick(n => showNodeDetail(n))
    .onNodeHover(n => { _hoveredNode = n; el.style.cursor = n ? "pointer" : "grab"; if (_graph) _graph.nodeCanvasObject(_drawNode); })
    .graphData({ nodes: [], links: [] });

  _graph.d3Force("charge").strength(-220);
  _graph.d3Force("link").distance(70);
  _graphNodeIds = new Set();
}

function drawGraph(graph) {
  if (!graph?.nodes?.length) return;
  if (!_graph) _initGraph();

  const deg = {};
  (graph.edges||[]).forEach(e => { deg[e.source]=(deg[e.source]||0)+1; deg[e.target]=(deg[e.target]||0)+1; });
  graph.nodes.forEach(n => { n._deg = deg[n.id]||0; });

  const newNodes = graph.nodes.filter(n => !_graphNodeIds.has(n.id));
  if (newNodes.length === 0 && _graphNodeIds.size > 0) return;

  // Legend
  const kinds = [...new Set(graph.nodes.map(n=>n.kind))];
  const legend = $("graph-legend");
  if (legend) legend.innerHTML = kinds.map(k => {
    const c = NODE_COLORS[k]||"#6b8599";
    return `<span class="legend-item"><span class="legend-dot" style="background:${c}"></span>${KIND_LABELS[k]||prettify(k)}</span>`;
  }).join("");

  const existing = _graph.graphData();
  const allNodeIds = new Set([...existing.nodes.map(n=>n.id), ...newNodes.map(n=>n.id)]);
  const existingLinks = new Set(existing.links.map(l => {
    const s = typeof l.source==="object"?l.source.id:l.source;
    const t = typeof l.target==="object"?l.target.id:l.target;
    return `${s}||${t}`;
  }));
  const mergedNodes = [...existing.nodes, ...newNodes];
  const mergedLinks = [
    ...existing.links,
    ...(graph.edges||[])
      .filter(e => allNodeIds.has(e.source)&&allNodeIds.has(e.target)&&!existingLinks.has(`${e.source}||${e.target}`))
      .map(e => ({ source:e.source, target:e.target, kind:e.kind, weight:e.weight||1 }))
  ];

  _graph.graphData({ nodes: mergedNodes, links: mergedLinks });
  newNodes.forEach(n => _graphNodeIds.add(n.id));

  if (!_graphAutoFit && mergedNodes.length >= 3) {
    _graphAutoFit = true;
    setTimeout(() => _graph.zoomToFit(700, 60), 1000);
  }
}

function showNodeDetail(d) {
  const c = NODE_COLORS[d.kind]||"#64748b";
  const lbl = KIND_LABELS[d.kind]||prettify(d.kind);
  $("nd-kind").innerHTML = `<span style="background:${c};width:7px;height:7px;border-radius:50%;display:inline-block;"></span> ${lbl}`;
  Object.assign($("nd-kind").style, { background:`${c}18`, color:c });
  $("nd-title").textContent = d.label;
  $("nd-meta").textContent = `${d._deg||0} connection${(d._deg||0)!==1?"s":""}`;
  const meta = d.metadata||{};
  const pairs = Object.entries(meta).filter(([,v])=>v!=null&&v!=="").slice(0,8);
  $("nd-props").innerHTML = pairs.length
    ? pairs.map(([k,v])=>`<div><div class="nd-prop-key">${esc(prettify(k))}</div><div class="nd-prop-val">${esc(trunc(String(v),120))}</div></div>`).join("")
    : `<div class="empty-state">No metadata.</div>`;
  $("node-detail").classList.add("open");
}

/* ═══════════════════════════════════════════
   PIPELINE VIEW (stages)
═══════════════════════════════════════════ */
function renderStageProgress(stages=[], runStatus="queued") {
  const byId = {};
  stages.forEach(s => { if (s.stage_id) byId[s.stage_id] = s; });
  const extraIds = stages.map(s=>s.stage_id).filter(id=>id&&!PIPELINE_STAGES.includes(id));
  const allIds = [...PIPELINE_STAGES, ...extraIds];

  $("pipeline-stages").innerHTML = allIds.map(sid => {
    const s = byId[sid];
    const status = s ? s.status : "pending";
    const name = s ? s.stage_name : prettify(sid);
    const meta = s?.model_provider && s?.model_name ? `${s.model_provider}/${s.model_name}` : "";
    return `<div class="stage-item ${status}">
      <span class="stage-dot"></span>
      <span class="stage-name">${esc(name)}</span>
      ${meta ? `<span class="stage-meta">${esc(meta)}</span>` : ""}
    </div>`;
  }).join("") || `<div class="empty-state">Waiting…</div>`;
}

/* ═══════════════════════════════════════════
   RUN RENDERING
═══════════════════════════════════════════ */
function renderRun() {
  if (!state.run) return;
  const r = state.run;

  // Run summary
  $("run-summary").innerHTML = Object.entries(r.summary||{})
    .map(([k,v]) => listItem(prettify(k),"",strVal(v)))
    .join("") || empty("No summary yet.");

  // Decision center
  renderDecisionCenter();
  renderFinalReport();

  // Swarm messages
  $("swarm-messages").innerHTML = r.messages?.map(m =>
    listItem(`${m.source} → ${m.target}`, m.category, m.content, "model")
  ).join("") || empty("No messages.");

  // Timeline
  $("timeline").innerHTML = r.timeline?.map(e =>
    `<div class="tl-item"><div class="tl-title">${esc(e.agent_name)} · ${esc(prettify(e.event_type))}</div><div class="tl-time">${esc(e.summary)}</div></div>`
  ).join("") || empty("No events.");
}

function renderDecisionCenter() {
  const r = state.run;
  const proposals = r.artifacts?.proposal_options||[];
  const critiques = r.artifacts?.critique_report||[];
  const grounding = r.artifacts?.grounding_report||[];
  const decision = r.artifacts?.judged_decision||{};
  const votes = r.artifacts?.vote_board||{};

  let html = "";
  if (decision.decision_title) {
    html += listItem(decision.decision_title, `vote ${decision.vote_score?.toFixed(2)||"—"} · grounding ${decision.grounding_score?.toFixed(2)||"—"}`, decision.rationale||"", "decision");
  }
  if (proposals.length) {
    html += `<h4 style="margin:12px 0 6px;font-size:12px;color:var(--text-3)">PROPOSALS</h4>`;
    html += proposals.map(o =>
      listItem(o.title, `feasibility ${o.feasibility} · novelty ${o.novelty}`, o.summary||"", "decision")
    ).join("");
  }
  if (critiques.length) {
    html += `<h4 style="margin:12px 0 6px;font-size:12px;color:var(--text-3)">CRITIQUES</h4>`;
    html += critiques.map(c =>
      listItem(c.title, `challenge ${c.challenge_score}`, (c.objections||[]).join(" | "), "error")
    ).join("");
  }
  $("decision-center").innerHTML = html || empty("No decision yet.");
}

function renderFinalReport() {
  const r = state.run;
  const report = r.artifacts?.final_report||{};
  const draft = r.artifacts?.paper_draft||{};

  const sections = [];
  if (report.summary) {
    sections.push({ title: "Executive Summary", content: report.summary });
  }

  const sectionOrder = ["report-problem","report-related-work","report-method","report-results","report-discussion","report-conclusion"];
  for (const key of sectionOrder) {
    if (draft[key]) sections.push({ title: prettifySectionKey(key), content: draft[key] });
  }
  for (const [key, val] of Object.entries(draft)) {
    if (!sectionOrder.includes(key) && typeof val === "string" && val.trim()) {
      sections.push({ title: prettifySectionKey(key), content: val });
    }
  }

  if (sections.length) {
    $("report-content").innerHTML = sections.map(s =>
      `<div class="report-section"><h4>${esc(s.title)}</h4><p>${esc(s.content)}</p></div>`
    ).join("");
  } else {
    $("report-content").innerHTML = empty("Report will appear after a run completes.");
  }
}

/* ═══════════════════════════════════════════
   HOME STATS
═══════════════════════════════════════════ */
function renderHomeStats() {
  const hasData = state.project || state.run;
  $("home-stats").classList.toggle("hidden", !hasData);
  if (!hasData) return;
  $("stat-papers").textContent = state.project?.papers?.length || 0;
  $("stat-runs").textContent = state.learning?.run_count || 0;
  $("stat-lessons").textContent = state.learning?.lessons?.length || 0;
  $("stat-decision").textContent = state.run?.artifacts?.judged_decision?.decision_title?.slice(0,16) || "—";
}

/* ═══════════════════════════════════════════
   PAPERS / NOVELTY / LEARNING
═══════════════════════════════════════════ */
function renderPapers(items) {
  $("papers-list").innerHTML = items.map(p =>
    listItem(p.title, `score ${p.score}`, `Citations: ${p.citations} | Overlap: ${p.overlap}`, "paper")
  ).join("") || empty("No papers.");
}

function renderNovelty(items) {
  $("novelty-list").innerHTML = items.map(n =>
    listItem(n.title, `score ${n.score}`, n.summary, "novelty")
  ).join("") || empty("No novelty data.");
}

function renderLearning() {
  if (!state.learning) return;
  const L = state.learning;
  $("learning-policies").innerHTML = (L.lessons||[]).map(l =>
    listItem(l.title, `${prettify(l.category)} · strength ${l.strength}`, l.content, "learn")
  ).join("") || empty("—");
  $("model-reliability").innerHTML = (L.model_profiles||[]).map(m =>
    listItem(`${m.provider}/${m.model}`, `reliability ${m.reliability} · calls ${m.total_calls}`, `live ${m.live_calls} | fallback ${m.fallback_calls}`, "model")
  ).join("") || empty("—");
}

/* ═══════════════════════════════════════════
   PROJECT SELECTOR
═══════════════════════════════════════════ */
function renderProjectSelector() {
  $("project-selector").innerHTML = state.projects.map(p =>
    `<option value="${esc(p.id)}" ${p.id===state.projectId?"selected":""}>${esc(p.name)}</option>`
  ).join("");
}

/* ═══════════════════════════════════════════
   MODEL HUB / SETTINGS
═══════════════════════════════════════════ */
async function loadModelHub() {
  state.models = await fetchJson("/api/models");
  renderProviders();
  renderModelSettings();
  renderOllama();
  renderLocalPresets();
}

function renderProviders() {
  const ps = state.models.catalog.providers;
  $("providers").innerHTML = ps.map(p => `
    <div class="provider-card">
      <div class="provider-name">${esc(p.name)}</div>
      <div class="provider-meta">${esc(p.category)} · ${esc(p.api_style)}</div>
      <div class="provider-desc">${esc(p.description)}</div>
      <div class="provider-chips">${p.supports.map(s=>`<span class="chip">${esc(s)}</span>`).join("")}</div>
    </div>`).join("");
  fillSelect($("primary-provider"), ps, state.models.settings.primary_provider);
  fillSelect($("embedding-provider"), ps.filter(p=>p.supports.includes("embeddings")), state.models.settings.embedding_provider);
  fillSelect($("custom-model-provider"), ps, "custom-openai-compatible");
}

function renderModelSettings() {
  const s = state.models.settings;
  $("primary-model").value = s.primary_model||"";
  $("embedding-model").value = s.embedding_model||"";
  $("ollama-url").value = s.ollama_base_url||"";
  $("lmstudio-url").value = s.lm_studio_base_url||"";
  $("custom-openai-url").value = s.custom_openai_base_url||"";
  const routes = s.stage_model_routing?.routes||{};
  $("routing-overview").innerHTML = Object.entries(routes).map(([k,v])=>listItem(prettify(k),v.provider||"",v.model||"","model")).join("")||empty("Single-model mode.");
  $("custom-models").innerHTML = (s.custom_models||[]).map(m=>listItem(m.name,`${m.provider} · ${m.model_type}`,m.model,"model")).join("")||empty("None.");
}

function renderOllama() {
  const ol = state.models.ollama;
  const ok = ol.reachable;
  const pill = $("ollama-pill");
  pill.className = "status-badge-sm " + (ok?"connected":"idle");
  pill.innerHTML = `<span class="status-dot-sm"></span>${ok?"connected":"offline"}`;
  $("ollama-status").innerHTML = [
    listItem("Endpoint", ok?"reachable":"offline", ol.base_url||"—", ok?"agent":"error"),
    ...(ol.installed_models||[]).slice(0,6).map(m=>listItem(m.name, fmtBytes(m.size), m.modified_at||"installed", "model")),
  ].join("") || empty("No local models.");
}

function renderLocalPresets() {
  $("local-models").innerHTML = state.models.catalog.local_model_presets.map(m=>installCard(m)).join("");
  $("embedding-presets").innerHTML = state.models.catalog.embedding_presets.map(m=>installCard(m)).join("");
  document.querySelectorAll("[data-install]").forEach(btn => {
    btn.addEventListener("click", async () => {
      btn.disabled = true; btn.textContent = "Installing…";
      await fetchJson("/api/models/ollama/install", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({model:btn.dataset.install}) });
      btn.disabled = false; btn.textContent = `Install ${btn.dataset.install}`;
    });
  });
  $("install-jobs").innerHTML = (state.models.install_jobs||[]).map(j=>listItem(j.model,`${j.provider} · ${j.status}`,trunc(j.log||"queued",160),"model")).join("");
}

function installCard(m) {
  return `<div class="list-item model">
    <div class="item-title">${esc(m.name)}</div>
    <div class="item-meta">${esc(m.provider)} · ${esc(m.model_type)} · ${esc(m.size_hint)}</div>
    <div class="item-body">${esc(m.description)}</div>
    <button class="install-btn" data-install="${esc(m.model)}">Install ${esc(m.model)}</button>
  </div>`;
}

async function saveModelSettings() {
  await fetchJson("/api/models/settings", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
    primary_provider:$("primary-provider").value, primary_model:$("primary-model").value,
    embedding_provider:$("embedding-provider").value, embedding_model:$("embedding-model").value,
    ollama_base_url:$("ollama-url").value, lm_studio_base_url:$("lmstudio-url").value,
    custom_openai_base_url:$("custom-openai-url").value,
  })});
  await loadModelHub();
}

async function connectOllama() {
  await fetchJson("/api/models/ollama/connect", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({base_url:$("ollama-url").value||"http://127.0.0.1:11434"}) });
  await loadModelHub();
}

async function addCustomModel() {
  await fetchJson("/api/models/custom", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({
    provider:$("custom-model-provider").value, name:$("custom-model-name").value,
    model:$("custom-model-id").value, model_type:$("custom-model-type").value, notes:$("custom-model-notes").value,
  })});
  $("custom-model-name").value=$("custom-model-id").value=$("custom-model-notes").value="";
  await loadModelHub();
}

/* ═══════════════════════════════════════════
   UI STATE
═══════════════════════════════════════════ */
function setStatus(status) {
  const badge = $("run-status");
  const labels = { idle:"Idle", running:"Running…", queued:"Queued…", completed:"Done", error:"Error", awaiting_approval:"Awaiting Approval" };
  badge.className = `status-badge ${status}`;
  badge.innerHTML = `<span class="status-dot"></span><span class="status-label">${labels[status]||status}</span>`;
}

function showError(msg) { $("error-text").textContent = msg; $("error-banner").classList.add("visible"); }
function clearError() { $("error-banner").classList.remove("visible"); }

/* ═══════════════════════════════════════════
   MICRO HELPERS
═══════════════════════════════════════════ */
function listItem(title, meta, body, cls="") {
  return `<div class="list-item ${cls}">
    <div class="item-title">${esc(String(title))}</div>
    ${meta!=null&&meta!==""?`<div class="item-meta">${esc(String(meta))}</div>`:""}
    ${body!=null&&body!==""?`<div class="item-body">${esc(String(body))}</div>`:""}
  </div>`;
}

function empty(msg) { return `<div class="empty-state">${esc(msg)}</div>`; }

function fillSelect(el, items, selected) {
  el.innerHTML = items.map(p=>`<option value="${esc(p.id)}" ${p.id===selected?"selected":""}>${esc(p.name)}</option>`).join("");
}

function strVal(v) {
  if (Array.isArray(v)) return v.join(", ");
  if (v && typeof v === "object") return JSON.stringify(v, null, 2);
  return String(v);
}

function trunc(v, n) { const s = String(v); return s.length>n ? s.slice(0,n-1)+"…" : s; }

function esc(v) {
  return String(v).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");
}

function prettify(v) {
  return String(v).replace(/^agent-/,"").replaceAll("_"," ").replaceAll("-"," ").replace(/\b\w/g,l=>l.toUpperCase());
}

function prettifySectionKey(k) {
  return k.replace("report-","").replaceAll("-"," ").replace(/\b\w/g,l=>l.toUpperCase());
}

function fmtBytes(v) {
  const n = Number(v||0); if (!n) return "unknown";
  const u = ["B","KB","MB","GB"]; let i=0, c=n;
  while(c>=1024&&i<u.length-1){c/=1024;i++;}
  return `${c.toFixed(c>=10?0:1)} ${u[i]}`;
}

async function fetchJson(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const detail = await res.text().catch(()=>res.statusText);
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}
