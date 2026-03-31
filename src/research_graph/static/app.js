/* ═══════════════════════════════════════════════════════
   ResearchGraph — app.js
   Query hero · Background runs · Live polling · 3D graph
═══════════════════════════════════════════════════════ */

const GRAPH_KINDS = ["papers","agents","experiments","reports","learning","technology","agentic","unified"];
const STORAGE_KEY = "researchgraph-project-id";
const POLL_MS     = 1800;  // poll interval while run is active

const NODE_COLORS = {
  // Papers — warm amber
  paper:               "#f0a050",
  // Pipeline agents — sky blue
  agent:               "#4db8ff",
  run_stage:           "#4db8ff",
  applied_lesson:      "#4db8ff",
  // Experiments — soft indigo
  experiment:          "#8b7cf8",
  experiment_result:   "#8b7cf8",
  run_summary:         "#8b7cf8",
  // Reports/output — rose
  report_section:      "#e8709a",
  final_report:        "#e8709a",
  draft_section:       "#e8709a",
  // Technology/methods — emerald teal
  technology:          "#34c9a0",
  model:               "#34c9a0",
  model_profile:       "#34c9a0",
  // Learning — coral
  taxonomy_facet:      "#f08060",
  learning_lesson:     "#f08060",
  learning_reflection: "#f08060",
  // Novelty/ideas — lavender
  novelty:             "#b794f4",
  memory_entry:        "#b794f4",
  // Artifacts — steel
  artifact:            "#6b8599",
  run_artifact:        "#6b8599",
  project:             "#6b8599",
  runtime_run:         "#6b8599",
};

const KIND_LABELS = {
  paper:"Paper", agent:"Agent", run_stage:"Stage", experiment:"Experiment",
  report_section:"Report", technology:"Tech", taxonomy_facet:"Agentic",
  novelty:"Novelty", memory_entry:"Memory", artifact:"Artifact",
  run_artifact:"Artifact", runtime_run:"Run", final_report:"Report",
  draft_section:"Section", learning_lesson:"Lesson", learning_reflection:"Reflection",
  applied_lesson:"Lesson", experiment_result:"Result", run_summary:"Summary",
};

/* ── state ── */
const state = {
  projects: [],
  projectId: localStorage.getItem(STORAGE_KEY) || "demo-project",
  project:   null,
  run:       null,
  learning:  null,
  models:    null,
  activeGraphKind: "unified",
  pollTimer: null,
  graphSim:  null,
  lastStageCount: 0,
};

/* ── DOM shortcuts ── */
const $ = id => document.getElementById(id);

/* ── event wiring ── */
$("run-project-button").addEventListener("click", startResearch);
$("create-project-button").addEventListener("click", saveProject);
$("refresh-button").addEventListener("click", () => boot());
$("use-demo-button").addEventListener("click", () => loadDemoAndRun());
$("node-detail-close").addEventListener("click", () => $("node-detail").classList.remove("open"));
$("error-dismiss").addEventListener("click", clearError);
$("project-selector").addEventListener("change", e => switchProject(e.target.value));
$("save-model-settings").addEventListener("click", saveModelSettings);
$("connect-ollama").addEventListener("click", connectOllama);
$("add-custom-model").addEventListener("click", addCustomModel);

document.querySelectorAll(".tab").forEach(t => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    $(`tab-${t.dataset.tab}`)?.classList.add("active");
  });
});

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
    state.project  = await fetchJson(`/api/projects/${state.projectId}`);
    state.learning = await fetchJson(`/api/projects/${state.projectId}/learning`);
    const runs     = await fetchJson(`/api/projects/${state.projectId}/runs`);
    state.run      = runs.items[0] || null;
    const [papersP, noveltyP] = await Promise.all([
      fetchJson(`/api/projects/${state.projectId}/top-papers?limit=5`),
      fetchJson(`/api/projects/${state.projectId}/novelty`),
    ]);
    renderProjectSummary();
    renderPapers(papersP.items || []);
    renderNovelty(noveltyP.items || []);
    if (state.run) {
      showWorkspace();
      renderRun();
      renderLearning();
      await loadAndDrawGraph();
      if (state.run.status === "running" || state.run.status === "queued") {
        startPolling(state.run.id);
      }
    }
  } catch(e) {
    showError(e.message);
  }
}

/* ═══════════════════════════════════════════
   QUERY & RUN
═══════════════════════════════════════════ */

/** Main entry point — create project (if needed) then start run */
async function startResearch() {
  const domain  = $("project-domain").value.trim();
  const problem = $("project-problem").value.trim();
  if (!domain || !problem) {
    showError("Please enter a domain and research problem.");
    return;
  }
  clearError();

  const btn = $("run-project-button");
  btn.disabled = true;
  btn.classList.add("is-running");
  $("run-btn-text").textContent = "Starting…";

  try {
    // Create a new project from the form
    const project = await fetchJson("/api/projects", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        name:     $("project-name").value.trim() || "Research Project",
        domain,
        problem,
        abstract: $("project-abstract").value.trim(),
      }),
    });

    state.projectId = project.id;
    localStorage.setItem(STORAGE_KEY, project.id);
    await loadProjects(project.id);
    state.project = project;
    renderProjectSummary();

    // Fire the run (returns immediately with status=queued)
    const run = await fetchJson(`/api/projects/${state.projectId}/runs`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ objective: problem }),
    });

    state.run = run;
    state.lastStageCount = 0;
    setStatus("running");
    showWorkspace();
    $("run-btn-text").textContent = "Running…";

    // Show graph overlay
    setOverlay(true, "Queued — starting pipeline…");
    renderStageProgress([], run.status);

    // Start polling
    startPolling(run.id);

  } catch (err) {
    showError(err.message || "Failed to start. Check the server logs.");
    setStatus("error");
    btn.disabled = false;
    btn.classList.remove("is-running");
    $("run-btn-text").textContent = "Start Research ▶";
  }
}

/** Save project without running */
async function saveProject() {
  const domain  = $("project-domain").value.trim();
  const problem = $("project-problem").value.trim();
  if (!domain || !problem) { showError("Domain and problem are required."); return; }
  const project = await fetchJson("/api/projects", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      name:     $("project-name").value.trim() || "Research Project",
      domain, problem, abstract: $("project-abstract").value.trim(),
    }),
  });
  await loadProjects(project.id);
  await loadWorkspace();
}

async function loadDemoAndRun() {
  // Fill the query form with the demo project's details
  const res = await fetch("/api/projects/demo-project");
  if (res.ok) {
    const p = await res.json();
    $("project-name").value    = p.name    || "";
    $("project-domain").value  = p.domain  || "";
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
  stopPolling();
  await loadWorkspace();
}

/* ═══════════════════════════════════════════
   POLLING (live graph building)
═══════════════════════════════════════════ */
function startPolling(runId) {
  stopPolling();
  state.pollTimer = setInterval(() => pollRun(runId), POLL_MS);
}

function stopPolling() {
  if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
}

async function pollRun(runId) {
  try {
    const run = await fetchJson(`/api/runs/${runId}`);
    state.run = run;

    // Show stage progress
    renderStageProgress(run.stages, run.status);

    // Update graph whenever new stages have completed
    if (run.stages.length !== state.lastStageCount) {
      state.lastStageCount = run.stages.length;
      await loadAndDrawGraph();
    }

    // Update overlay stage label
    const runningStage = run.stages.find(s => s.status === "running");
    if (runningStage) {
      setOverlay(true, `Running pipeline…`, runningStage.stage_name);
    }

    // Run finished
    if (run.status !== "running" && run.status !== "queued") {
      stopPolling();
      setOverlay(false);
      setStatus(run.status === "completed" ? "completed" : "error");
      state.learning = run.learning_state || state.learning;
      renderRun();
      renderLearning();
      await loadAndDrawGraph();

      const btn = $("run-project-button");
      btn.disabled = false;
      btn.classList.remove("is-running");
      $("run-btn-text").textContent = "Start Research ▶";

      if (run.status === "error") {
        showError(run.summary?.error || "Run ended with an error.");
      }
    }
  } catch (err) {
    stopPolling();
    setStatus("error");
    showError("Lost connection to server: " + err.message);
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
      _resetGraph();  // clear 3D graph when switching kinds
      await loadAndDrawGraph();
    });
  });
}

async function loadAndDrawGraph() {
  if (!state.projectId) return;
  const url = state.run
    ? `/api/runs/${state.run.id}/graphs/${state.activeGraphKind}`
    : `/api/projects/${state.projectId}/graphs/${state.activeGraphKind}`;
  try {
    const graph = await fetchJson(url);
    drawGraph(graph);
  } catch (_) { /* non-fatal */ }
}

/* ── Force Graph (2D canvas — clean, flat, minimal) ─────────────────────── */

let _graph    = null;
let _graphNodeIds = new Set();
let _graphAutoFit = false;
let _hoveredNode  = null;

function _resetGraph() {
  if (_graph) { try { _graph._destructor && _graph._destructor(); } catch(_) {} }
  _graph = null;
  _graphNodeIds = new Set();
  _graphAutoFit = false;
  _hoveredNode  = null;
  const el = $("graph-canvas");
  if (el) el.innerHTML = "";
}

/* Node radius in graph-space units */
function _nodeSize(node) {
  return 4.5 + Math.min((node._deg || 0) * 0.7, 5.5);
}

/* Draw a single node onto the canvas context */
function _drawNode(node, ctx, gs) {
  const x = node.x, y = node.y;
  const c    = NODE_COLORS[node.kind] || "#6b8599";
  const r    = _nodeSize(node);
  const hot  = node === _hoveredNode;

  // ── outer halo ──────────────────────────────────────────────────────────
  const haloR = r * (hot ? 3.8 : 2.8);
  const halo  = ctx.createRadialGradient(x, y, r * 0.4, x, y, haloR);
  halo.addColorStop(0, c + (hot ? "30" : "18"));
  halo.addColorStop(1, c + "00");
  ctx.fillStyle = halo;
  ctx.beginPath();
  ctx.arc(x, y, haloR, 0, Math.PI * 2);
  ctx.fill();

  // ── filled disc (translucent) ────────────────────────────────────────────
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = c + (hot ? "28" : "16");
  ctx.fill();

  // ── ring ─────────────────────────────────────────────────────────────────
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.strokeStyle = c + (hot ? "ff" : "bb");
  ctx.lineWidth   = Math.max(0.6, (hot ? 2.0 : 1.4) / gs);
  ctx.stroke();

  // ── centre dot ──────────────────────────────────────────────────────────
  ctx.beginPath();
  ctx.arc(x, y, Math.max(0.8, r * 0.22), 0, Math.PI * 2);
  ctx.fillStyle = c + (hot ? "ff" : "dd");
  ctx.fill();

  // ── label ────────────────────────────────────────────────────────────────
  const lbl = (node.label || "").slice(0, 22) + (node.label?.length > 22 ? "…" : "");
  // Show label always but fade at very low zoom
  const alpha = Math.min(0.85, Math.max(0.25, gs * 0.55));
  const fontSize = Math.max(2.5, Math.min(11, 10 / gs));
  ctx.font         = `500 ${fontSize}px Inter, system-ui, sans-serif`;
  ctx.textAlign    = "center";
  ctx.textBaseline = "top";
  ctx.shadowColor  = "rgba(0,0,0,0.9)";
  ctx.shadowBlur   = Math.max(1.5, 4 / gs);
  ctx.fillStyle    = `rgba(203,213,225,${alpha})`;
  ctx.fillText(lbl, x, y + r + 1.8 / gs);
  ctx.shadowBlur   = 0;
}

/* Hit-area paint (invisible — used for click/hover detection) */
function _paintHitArea(node, color, ctx) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(node.x, node.y, _nodeSize(node) + 4, 0, Math.PI * 2);
  ctx.fill();
}

function _initGraph() {
  const el = $("graph-canvas");
  if (!el) return;
  el.innerHTML = "";
  _graphAutoFit = false;
  _hoveredNode  = null;
  const W = el.clientWidth  || 900;
  const H = el.clientHeight || 530;

  _graph = ForceGraph()(el)
    .width(W).height(H)
    .backgroundColor("#00000000")
    // ── nodes ───────────────────────────────────────────────────────────────
    .nodeCanvasObject(_drawNode)
    .nodeCanvasObjectMode(() => "replace")
    .nodePointerAreaPaint(_paintHitArea)
    // ── tooltip ─────────────────────────────────────────────────────────────
    .nodeLabel(n => {
      const c   = NODE_COLORS[n.kind] || "#6b8599";
      const lbl = KIND_LABELS[n.kind] || prettify(n.kind);
      return `<div style="background:rgba(6,10,20,0.93);border:1px solid ${c}44;padding:6px 10px;border-radius:8px;font-size:12px;color:#e2e8f0;max-width:260px;line-height:1.5;box-shadow:0 8px 24px rgba(0,0,0,0.7)"><span style="color:${c};font-size:10px;font-weight:700;letter-spacing:0.07em;text-transform:uppercase;display:block;margin-bottom:2px">${lbl}</span>${esc(n.label)}</div>`;
    })
    // ── links ───────────────────────────────────────────────────────────────
    .linkColor(l => {
      const src = typeof l.source === "object" ? l.source : {};
      return (NODE_COLORS[src.kind] || "#334155") + "40";
    })
    .linkWidth(l => (l.weight || 1) * 0.6)
    .linkCurvature(0.18)
    .linkDirectionalArrowLength(4)
    .linkDirectionalArrowRelPos(0.82)
    .linkDirectionalArrowColor(l => {
      const src = typeof l.source === "object" ? l.source : {};
      return (NODE_COLORS[src.kind] || "#4db8ff") + "88";
    })
    .linkDirectionalParticles(2)
    .linkDirectionalParticleWidth(1.8)
    .linkDirectionalParticleSpeed(0.0045)
    .linkDirectionalParticleColor(l => {
      const src = typeof l.source === "object" ? l.source : {};
      return NODE_COLORS[src.kind] || "#4db8ff";
    })
    // ── interaction ─────────────────────────────────────────────────────────
    .onNodeClick(node => showNodeDetail(node))
    .onNodeHover(node => {
      _hoveredNode = node;
      el.style.cursor = node ? "pointer" : "grab";
      if (_graph) _graph.nodeCanvasObject(_drawNode); // force repaint
    })
    .graphData({ nodes: [], links: [] });

  // Physics: good separation, not too tight
  _graph.d3Force("charge").strength(-220);
  _graph.d3Force("link").distance(70);

  _graphNodeIds = new Set();
}

function drawGraph(graph) {
  if (!graph?.nodes?.length) return;
  const el = $("graph-canvas");
  if (!el) return;

  if (!_graph) _initGraph();

  const existingIds  = _graphNodeIds;
  const newNodes     = graph.nodes.filter(n => !existingIds.has(n.id));
  const newEdges     = graph.edges || [];

  if (newNodes.length === 0 && existingIds.size > 0) return;

  // Degree map for node sizing
  const deg = {};
  (graph.edges || []).forEach(e => {
    deg[e.source] = (deg[e.source] || 0) + 1;
    deg[e.target] = (deg[e.target] || 0) + 1;
  });
  graph.nodes.forEach(n => { n._deg = deg[n.id] || 0; });

  // Legend
  const kinds  = [...new Set(graph.nodes.map(n => n.kind))];
  const legend = $("graph-legend");
  if (legend) legend.innerHTML = kinds.map(k => {
    const c = NODE_COLORS[k] || "#6b8599";
    return `<span class="legend-item"><span class="legend-dot" style="background:${c}"></span>${KIND_LABELS[k] || prettify(k)}</span>`;
  }).join("");

  // Merge into existing graph data
  const existing      = _graph.graphData();
  const allNodeIds    = new Set([...existing.nodes.map(n => n.id), ...newNodes.map(n => n.id)]);
  const existingLinks = new Set(existing.links.map(l => {
    const s = typeof l.source === "object" ? l.source.id : l.source;
    const t = typeof l.target === "object" ? l.target.id : l.target;
    return `${s}||${t}`;
  }));

  const mergedNodes = [...existing.nodes, ...newNodes];
  const mergedLinks = [
    ...existing.links,
    ...newEdges
      .filter(e => allNodeIds.has(e.source) && allNodeIds.has(e.target) && !existingLinks.has(`${e.source}||${e.target}`))
      .map(e => ({ source: e.source, target: e.target, kind: e.kind, weight: e.weight || 1 })),
  ];

  _graph.graphData({ nodes: mergedNodes, links: mergedLinks });
  newNodes.forEach(n => existingIds.add(n.id));

  // Auto-fit after first batch
  if (!_graphAutoFit && mergedNodes.length >= 3) {
    _graphAutoFit = true;
    setTimeout(() => _graph.zoomToFit(700, 60), 1000);
  }
}

function showNodeDetail(d) {
  const c = NODE_COLORS[d.kind]||"#64748b";
  const lbl = KIND_LABELS[d.kind]||prettify(d.kind);
  $("nd-kind").innerHTML = `<span class="neon-dot" style="background:${c};box-shadow:0 0 8px ${c};width:7px;height:7px;border-radius:50%;display:inline-block;"></span> ${lbl}`;
  Object.assign($("nd-kind").style,{background:`${c}18`,color:c,borderColor:`${c}33`});
  $("nd-title").textContent = d.label;
  $("nd-meta").textContent  = `${d._deg||0} connection${(d._deg||0)!==1?"s":""}`;
  const meta  = d.metadata||{};
  const pairs = Object.entries(meta).filter(([,v])=>v!=null&&v!=="").slice(0,8);
  $("nd-props").innerHTML = pairs.length
    ? pairs.map(([k,v])=>`<div><div class="nd-prop-key">${esc(prettify(k))}</div><div class="nd-prop-val">${esc(trunc(String(v),120))}</div></div>`).join("")
    : `<div class="empty">No metadata.</div>`;
  $("node-detail").classList.add("open");
}

/* ═══════════════════════════════════════════
   STAGE PROGRESS (live sidebar)
═══════════════════════════════════════════ */
// Known pipeline stages in topological order — must match actual agent IDs from seed.py
const PIPELINE_STAGES = [
  "agent-intake", "agent-evidence", "agent-planning-graph", "agent-survey",
  "agent-planner", "agent-critic", "agent-grounding", "agent-novelty",
  "agent-coordinator", "agent-judge", "agent-executor", "agent-memory", "agent-writer"
];

function renderStageProgress(stages=[], runStatus="queued") {
  // Build lookup by stage_id
  const byId = {};
  stages.forEach(s => { if (s.stage_id) byId[s.stage_id] = s; });

  // All known IDs: pipeline order first, then any extra stages not in the list
  const extraIds = stages.map(s => s.stage_id).filter(id => id && !PIPELINE_STAGES.includes(id));
  const knownIds = [...PIPELINE_STAGES, ...extraIds];

  const rows = knownIds.map(sid => {
    const s = byId[sid];
    if (!s) {
      return `<div class="sp-item pending">
        <span class="sp-dot"></span>
        <span class="sp-name">${prettify(sid)}</span>
      </div>`;
    }
    const st = s.status;
    const meta = s.model_provider && s.model_name ? `${s.model_provider}/${s.model_name}` : "";
    return `<div class="sp-item ${st}">
      <span class="sp-dot"></span>
      <span class="sp-name">${esc(s.stage_name)}</span>
      ${meta ? `<span class="sp-meta">${esc(meta)}</span>` : ""}
    </div>`;
  });

  const prog = $("stage-progress");
  if (prog) prog.innerHTML = rows.join("") || `<div class="empty">Waiting to start…</div>`;
}

/* ═══════════════════════════════════════════
   RUN RENDERING
═══════════════════════════════════════════ */
function renderRun() {
  if (!state.run) return;
  const r = state.run;

  $("run-stats").innerHTML = [
    stat("Stages",   r.stages.length,   "cyan"),
    stat("Messages", r.messages.length, "purple"),
    stat("Memory",   r.memory.length,   "amber"),
    stat("Decision", r.summary?.selected_decision||"—", "green"),
  ].join("");

  $("run-summary").innerHTML = Object.entries(r.summary||{})
    .map(([k,v]) => item(prettify(k),"run summary",strVal(v)))
    .join("") || empty("No summary yet.");

  renderDecisionCenter();
  renderFinalReport();

  $("stages").innerHTML = r.stages.map(s =>
    item(s.stage_name,
      `${prettify(s.role)} · ${s.model_provider||"heuristic"}/${s.model_name||"—"}`,
      [s.summary,
       s.learning_applied?.length?`✓ ${s.learning_applied.join("; ")}` : "",
       s.model_error?`⚠ ${s.model_error}` : "",
      ].filter(Boolean).join("  |  "), "agent")
  ).join("") || empty("No stages.");

  $("timeline").innerHTML = r.timeline.map(e =>
    `<div class="tl-item">
       <div class="tl-title">${esc(e.agent_name)} · ${esc(prettify(e.event_type))}</div>
       <div class="tl-time">${esc(e.summary)}</div>
     </div>`
  ).join("") || empty("No events.");

  $("messages").innerHTML = r.messages.map(m =>
    item(`${m.source} → ${m.target}`, m.category, m.content,"model")
  ).join("") || empty("No messages.");

  $("artifacts").innerHTML = Object.entries(r.artifacts).map(([k,v]) =>
    item(prettify(k), artifactMeta(v), trunc(JSON.stringify(v,null,2),200),"report")
  ).join("") || empty("No artifacts.");

  $("memory").innerHTML = r.memory.map(e =>
    item(e.title, e.kind, e.content,"learn")
  ).join("") || empty("No memory.");
}

function renderDecisionCenter() {
  const r = state.run;
  const proposals = r.artifacts.proposal_options||[];
  const critiques  = r.artifacts.critique_report ||[];
  const grounding  = r.artifacts.grounding_report||[];
  const votes      = r.artifacts.vote_board      ||{};
  const decision   = r.artifacts.judged_decision ||{};

  $("proposal-options").innerHTML = proposals.map(o =>
    item(o.title,`feasibility ${o.feasibility} · novelty ${o.novelty} · evidence ${o.evidence_fit}`,
      `${o.summary}  Anchors: ${(o.anchors||[]).join(", ")}`,"decision")
  ).join("")||empty("No proposals yet.");

  $("critique-board").innerHTML = critiques.map(c =>
    item(c.title,`challenge ${c.challenge_score}`,
      `${(c.objections||[]).join(" | ")}  Guardrail: ${c.recommended_guardrail}`,"error")
  ).join("")||empty("No critique.");

  $("grounding-ledger").innerHTML = grounding.map(g =>
    item(prettify(g.option_id),
      `support ${g.support_score} · coverage ${g.coverage_score} · ${g.verdict}`,
      `Supported by: ${(g.supported_by||[]).join(", ")}`,"exp")
  ).join("")||empty("No grounding.");

  $("vote-board").innerHTML = (votes.scorecards||[]).map(c =>
    item(c.title,`score ${c.score}`,
      `grounding ${c.grounding} | feasibility ${c.feasibility} | novelty ${c.novelty} | risk −${c.risk_penalty}`,"model")
  ).join("")||empty("No votes.");

  $("judged-decision").innerHTML = decision.decision_title
    ? [item(decision.decision_title,`vote ${decision.vote_score} · grounding ${decision.grounding_score}`,decision.rationale,"decision"),
       item("Guardrails","judge constraints",(decision.guardrails||[]).join("  |  "),"decision")].join("")
    : empty("No decision yet.");
}

function renderFinalReport() {
  const r = state.run;
  const report = r.artifacts.final_report||{};
  const draft  = r.artifacts.paper_draft ||{};
  const parts  = [
    report.summary ? item("Executive Summary",report.decision_title||"final report",report.summary,"report") : "",
    ...Object.entries(draft).map(([k,v]) => item(prettifySectionKey(k),"draft section",v,"report")),
    Object.keys(report).length ? item("Report Metadata",report.status||"report",strVal(report),"report") : "",
  ].filter(Boolean);
  $("final-report").innerHTML = parts.join("")||empty("Report will appear here after the run completes.");
}

/* ═══════════════════════════════════════════
   LEARNING / PAPERS / NOVELTY
═══════════════════════════════════════════ */
function renderLearning() {
  if (!state.learning) return;
  const L = state.learning;
  $("learning-policies").innerHTML  = (L.lessons||[]).map(l=>item(l.title,`${prettify(l.category)} · strength ${l.strength}`,l.content,"learn")).join("")||empty("—");
  $("stage-guidance").innerHTML     = (L.stage_guidance||[]).map(g=>item(g.stage_name,`score ${g.score}`,(g.instructions||[]).join("  |  "),"agent")).join("")||empty("—");
  $("model-reliability").innerHTML  = (L.model_profiles||[]).map(m=>item(`${m.provider}/${m.model}`,`reliability ${m.reliability} · calls ${m.total_calls}`,`live ${m.live_calls} | fallback ${m.fallback_calls}${m.last_error?` | ⚠ ${m.last_error}`:""}` ,"model")).join("")||empty("—");
  $("adaptation-history").innerHTML = (L.adaptation_history||[]).map(h=>item(h.run_id,h.created_at,h.summary,"exp")).join("")||empty("—");
}

function renderPapers(items) {
  $("papers").innerHTML = items.map(p=>item(p.title,`score ${p.score}`,`Overlap ${p.overlap} | Connectivity ${p.connectivity} | Citations ${p.citations}`,"paper")).join("")||empty("—");
}

function renderNovelty(items) {
  $("novelty").innerHTML = items.map(n=>item(n.title,`score ${n.score}`,n.summary,"novelty")).join("")||empty("—");
}

/* ═══════════════════════════════════════════
   PROJECT SUMMARY
═══════════════════════════════════════════ */
function renderProjectSelector() {
  $("project-selector").innerHTML = state.projects.map(p =>
    `<option value="${esc(p.id)}" ${p.id===state.projectId?"selected":""}>${esc(p.name)}</option>`
  ).join("");
}

function renderProjectSummary() {
  const pill = $("current-project-pill");
  if (pill && state.project) pill.textContent = trunc(state.project.name, 24);
  const el = $("project-summary");
  if (!el || !state.project) return;
  el.innerHTML = [
    item("Domain","research domain",state.project.domain),
    item("Problem","query",state.project.problem),
  ].join("");
}

/* ═══════════════════════════════════════════
   MODEL HUB
═══════════════════════════════════════════ */
async function loadModelHub() {
  state.models = await fetchJson("/api/models");
  renderProviders();
  renderModelSettings();
  renderOllama();
  renderLocalPresets();
  renderInstallJobs();
}

function renderProviders() {
  const ps = state.models.catalog.providers;
  $("providers").innerHTML = ps.map(p=>`
    <div class="provider-card">
      <div class="provider-name">${esc(p.name)}</div>
      <div class="provider-meta">${esc(p.category)} · ${esc(p.api_style)}</div>
      <div class="provider-desc">${esc(p.description)}</div>
      <div class="provider-chips">${p.supports.map(s=>`<span class="chip">${esc(s)}</span>`).join("")}</div>
    </div>`).join("");
  fillSelect($("primary-provider"),  ps, state.models.settings.primary_provider);
  fillSelect($("embedding-provider"),ps.filter(p=>p.supports.includes("embeddings")),state.models.settings.embedding_provider);
  fillSelect($("custom-model-provider"),ps,"custom-openai-compatible");
}

function renderModelSettings() {
  const s = state.models.settings;
  $("primary-model").value    = s.primary_model||"";
  $("embedding-model").value  = s.embedding_model||"";
  $("ollama-url").value       = s.ollama_base_url||"";
  $("lmstudio-url").value     = s.lm_studio_base_url||"";
  $("custom-openai-url").value= s.custom_openai_base_url||"";
  const routes = s.stage_model_routing?.routes||{};
  $("routing-overview").innerHTML = Object.entries(routes).map(([k,v])=>item(prettify(k),v.provider||"provider",v.model||"","model")).join("")||empty("Single-model mode.");
  $("custom-models").innerHTML = (s.custom_models||[]).map(m=>item(m.name,`${m.provider} · ${m.model_type}`,m.model,"model")).join("")||empty("None.");
}

function renderOllama() {
  const ol = state.models.ollama;
  const ok = ol.reachable;
  $("ollama-pill").className  = "status-pill "+(ok?"completed":"idle");
  $("ollama-pill").innerHTML  = `<span class="neon-dot ${ok?"green":"amber"}"></span>${ok?"connected":"offline"}`;
  $("ollama-status").innerHTML= [
    item("Endpoint",ok?"reachable":"offline",ol.base_url||"—",ok?"agent":"error"),
    ...(ol.installed_models||[]).slice(0,6).map(m=>item(m.name,fmtBytes(m.size),m.modified_at||"installed","model")),
  ].join("")||empty("No local models.");
}

function renderLocalPresets() {
  $("local-models").innerHTML     = state.models.catalog.local_model_presets.map(m=>installCard(m)).join("");
  $("embedding-presets").innerHTML= state.models.catalog.embedding_presets.map(m=>installCard(m)).join("");
  document.querySelectorAll("[data-install]").forEach(btn=>{
    btn.addEventListener("click", async ()=>{
      btn.disabled=true; btn.textContent="Installing…";
      await fetchJson("/api/models/ollama/install",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({model:btn.dataset.install})});
      await refreshInstall(); btn.disabled=false; btn.textContent=`Install ${btn.dataset.install}`;
    });
  });
}

function renderInstallJobs() {
  $("install-jobs").innerHTML=(state.models.install_jobs||[]).map(j=>item(j.model,`${j.provider}·${j.status}`,trunc(j.log||"queued",160),"model")).join("")||empty("None.");
}

function installCard(m) {
  return `<div class="item model">
    <div class="item-title">${esc(m.name)}</div>
    <div class="item-meta">${esc(m.provider)} · ${esc(m.model_type)} · ${esc(m.size_hint)}</div>
    <div class="item-body">${esc(m.description)}</div>
    <button class="mini-btn" data-install="${esc(m.model)}">Install ${esc(m.model)}</button>
  </div>`;
}

async function saveModelSettings() {
  await fetchJson("/api/models/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
    primary_provider:$("primary-provider").value,primary_model:$("primary-model").value,
    embedding_provider:$("embedding-provider").value,embedding_model:$("embedding-model").value,
    ollama_base_url:$("ollama-url").value,lm_studio_base_url:$("lmstudio-url").value,
    custom_openai_base_url:$("custom-openai-url").value,
  })});
  await loadModelHub();
}

async function connectOllama() {
  await fetchJson("/api/models/ollama/connect",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({base_url:$("ollama-url").value||"http://127.0.0.1:11434"})});
  await loadModelHub();
}

async function addCustomModel() {
  await fetchJson("/api/models/custom",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
    provider:$("custom-model-provider").value,name:$("custom-model-name").value,
    model:$("custom-model-id").value,model_type:$("custom-model-type").value,notes:$("custom-model-notes").value,
  })});
  $("custom-model-name").value=$("custom-model-id").value=$("custom-model-notes").value="";
  await loadModelHub();
}

async function refreshInstall() {
  const [jobs,ol]=await Promise.all([fetchJson("/api/models/install-jobs"),fetchJson("/api/models/ollama")]);
  state.models.install_jobs=jobs.items; state.models.ollama=ol;
  renderOllama(); renderInstallJobs();
}

/* ═══════════════════════════════════════════
   UI HELPERS
═══════════════════════════════════════════ */
function showWorkspace() {
  $("workspace").classList.remove("hidden");
  $("results-section").classList.remove("hidden");
}

function setStatus(status) {
  const pill = $("run-status-pill");
  const dots  = {idle:"idle",running:"amber",queued:"amber",completed:"green",error:"red"};
  const labels= {idle:"idle",running:"running…",queued:"queued…",completed:"completed",error:"error"};
  pill.className = `status-pill ${status}`;
  pill.innerHTML = `<span class="neon-dot ${dots[status]||"idle"}"></span>${labels[status]||status}`;
}

function setOverlay(visible, label="Building knowledge graph…", stage="") {
  const ov = $("graph-overlay");
  if (visible) {
    ov.classList.add("visible");
    $("overlay-label").textContent = label;
    $("overlay-stage").textContent = stage ? `▸ ${stage}` : "";
  } else {
    ov.classList.remove("visible");
  }
}

function showError(msg) {
  $("error-text").textContent = msg;
  $("error-banner").classList.add("visible");
}

function clearError() {
  $("error-banner").classList.remove("visible");
}

/* ═══════════════════════════════════════════
   MICRO HELPERS
═══════════════════════════════════════════ */
function item(title, meta, body, cls="") {
  return `<div class="item ${cls}">
    <div class="item-title">${esc(String(title))}</div>
    ${meta!=null?`<div class="item-meta">${esc(String(meta))}</div>`:""}
    ${body!=null?`<div class="item-body">${esc(String(body))}</div>`:""}
  </div>`;
}

function stat(label, value, cls="") {
  return `<div class="stat-box">
    <div class="stat-lbl">${esc(label)}</div>
    <div class="stat-val ${cls}">${esc(String(value))}</div>
  </div>`;
}

function empty(msg) { return `<div class="empty">${esc(msg)}</div>`; }

function fillSelect(el, items, selected) {
  el.innerHTML = items.map(p=>`<option value="${esc(p.id)}" ${p.id===selected?"selected":""}>${esc(p.name)}</option>`).join("");
}

function artifactMeta(v) {
  if (Array.isArray(v)) return `${v.length} items`;
  if (v&&typeof v==="object") return `${Object.keys(v).length} keys`;
  return typeof v;
}

function strVal(v) {
  if (Array.isArray(v)) return v.join(", ");
  if (v&&typeof v==="object") return JSON.stringify(v,null,2);
  return String(v);
}

function trunc(v, n) { const s=String(v); return s.length>n?s.slice(0,n-1)+"…":s; }

function esc(v) {
  return String(v)
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;").replaceAll("'","&#39;");
}

function prettify(v) {
  return String(v).replace(/^agent-/,"").replaceAll("_"," ").replaceAll("-"," ").replace(/\b\w/g,l=>l.toUpperCase());
}

function prettifySectionKey(k) {
  return k.replace("report-","").replaceAll("-"," ").replace(/\b\w/g,l=>l.toUpperCase());
}

function fmtBytes(v) {
  const n=Number(v||0); if(!n)return"unknown";
  const u=["B","KB","MB","GB"]; let i=0,c=n;
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
