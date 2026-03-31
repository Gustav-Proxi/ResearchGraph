# ResearchGraph

`ResearchGraph` is a new standalone project for the system you described: an end-to-end research suite that treats papers, agents, experiments, reports, artifacts, and technologies as connected graphs instead of isolated steps.

This is intentionally a separate project from `Arc`, `AgentScope`, `vectorlens`, or `RAG`, even though it is designed to reuse ideas from them later.

## What exists now

- A standalone Python package under `src/research_graph`.
- Graph-native domain models for:
  - papers
  - agents
  - experiments
  - report sections
  - artifacts
  - technologies
- A runnable runtime/orchestrator with:
  - executable agent stages
  - swarm-style agent messaging
  - tool wiring
  - run memory
  - cross-run self-learning and reflection
  - optional AgentScope tracing
- A model hub with:
  - major provider registry plus custom provider slots
  - primary-model and embedding-model settings
  - Ollama connectivity checks
  - one-click local small-model installs
  - visible install job status in the dashboard
- Graph builders for:
  - paper connectivity graph
  - agent workflow graph
  - experiment graph
  - report graph
  - technology graph
  - agentic taxonomy graph
  - unified research graph
- `TurboQuant`, a scoring engine for ranking papers and graph nodes by overlap, recency, citations, and connectivity.
- Novelty hypotheses that make the system more than a document lookup wrapper.
- FastAPI endpoints.
- GraphQL schema for exploring the project and graph data.
- A frontend dashboard served directly from the backend.
- Seed data for a demo research program centered on autonomous research systems.

## Why a separate project

This project is the integration layer:

- `AgentScope` can become the run-trace layer.
- `vectorlens` concepts can become evidence-grounding and attribution modules.
- your `RAG` repo can contribute evidence ingestion, workspace corpora, and confidence checks as one subsystem only.
- `Arc` can remain an experimentation sandbox instead of carrying the entire product.

## Project layout

- `src/research_graph/models.py`: graph-native domain objects.
- `src/research_graph/seed.py`: demo project seeding and default pipeline.
- `src/research_graph/graphs.py`: graph builders for papers, agents, experiments, reports, technology, and unified views.
- `src/research_graph/runtime.py`: executable runtime and swarm orchestration.
- `src/research_graph/tools.py`: stage toolchain and artifact-producing tools.
- `src/research_graph/tracing.py`: optional AgentScope bridge.
- `src/research_graph/runtime_models.py`: run, stage, message, timeline, and memory models.
- `src/research_graph/turboquant.py`: ranking/scoring engine.
- `src/research_graph/model_hub.py`: model/provider catalog, settings persistence, Ollama integration, and local install jobs.
- `src/research_graph/learning.py`: persisted self-learning engine, lesson extraction, and run-to-run adaptation state.
- `src/research_graph/service.py`: in-memory repository and orchestration service.
- `src/research_graph/schema.py`: GraphQL schema.
- `src/research_graph/app.py`: FastAPI application and REST endpoints.
- `docs/agentic_blueprint.md`: paper-grounded rationale for the agentic taxonomy and novelty direction.
- `src/research_graph/static/`: frontend dashboard assets.

## Quick start

```bash
cd ResearchGraph
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
research-graph-api
```

Then open:

- `http://127.0.0.1:8080/`
- `http://127.0.0.1:8080/docs`
- `http://127.0.0.1:8080/graphql`

## REST endpoints

- `GET /health`
- `GET /api/projects`
- `GET /api/projects/demo`
- `GET /api/projects/{project_id}`
- `GET /api/projects/{project_id}/graphs/{graph_kind}`
- `GET /api/projects/{project_id}/top-papers?limit=5`
- `GET /api/projects/{project_id}/runs`
- `POST /api/projects/{project_id}/runs`
- `GET /api/projects/{project_id}/novelty`
- `GET /api/projects/{project_id}/learning`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/graphs/{graph_kind}`
- `GET /api/models`
- `GET /api/models/settings`
- `POST /api/models/settings`
- `POST /api/models/custom`
- `GET /api/models/ollama`
- `POST /api/models/ollama/connect`
- `POST /api/models/ollama/install`
- `GET /api/models/install-jobs`

Supported graph kinds:

- `papers`
- `agents`
- `experiments`
- `reports`
- `learning`
- `technology`
- `agentic`
- `unified`

## Example GraphQL queries

```graphql
query DemoProject {
  demoProject {
    id
    name
    domain
    problem
    topPapers(limit: 3) {
      id
      title
      score
    }
  }
}
```

```graphql
mutation ExecuteDemo {
  executeProject(projectId: "demo-project", objective: "Run the full research suite") {
    id
    status
    summary
  }
}
```

```graphql
query UnifiedGraph {
  unifiedGraph(projectId: "demo-project") {
    kind
    nodes {
      id
      label
      kind
    }
    edges {
      source
      target
      kind
      weight
    }
  }
}
```

## Reuse plan

This codebase is clean and independent, but it is set up to absorb parts of your other work:

- from your `RAG` repo: evidence ingestion, corpus management, and confidence estimation
- from `vectorlens`: groundedness and evidence attribution
- from `agentreplay` or `AgentScope`: agent execution tracing and replay

## Runtime

The system is now executable, not just structural.

It currently includes:

- topological orchestration over the agent dependency graph
- executable stage handlers for intake, evidence discovery, planning, survey, experiments, memory, coordination, novelty, and writing
- swarm-style messages passed between specialist agents
- run memory populated during execution
- learned policies persisted across runs and fed back into later stages
- optional AgentScope tracing when a compatible backend is available

## Model Dashboard

The frontend now exposes:

- major model providers plus local/self-hosted endpoints
- separate primary-model and embedding-model controls
- Ollama status and installed-model visibility
- one-click download buttons for curated small local chat models and embedding models
- custom model registration for any provider or OpenAI-compatible endpoint
- visible self-learning panels for learned policies, stage guidance, model reliability, and adaptation history

If AgentScope is importable but no backend is running, tracing fails open and the run still completes locally.

## Agentic architecture

The current design is explicitly influenced by the taxonomy from the 2025 survey “Graphs Meet AI Agents: Taxonomy, Progress, and Future Opportunities”:

- planning
- execution
- memory
- multi-agent coordination

It also adopts the paper’s future-looking directions:

- graph foundation models
- MCP-style structured context exchange
- open agent networks

ResearchGraph turns those into concrete system objects:

- taxonomy facets
- agent stages
- protocol/network technologies
- experiments
- report sections
- novelty hypotheses
- an `agentic` graph that binds them together

## What makes this different

This project is intentionally not just “RAG with a graph UI”.

The novel direction here is a graph-native research operating system:

- `Reflexive Graph Memory`: failures, weak evidence chains, and reusable reasoning motifs are stored as first-class memory graph edges.
- `Self-Learning Swarm`: each run reflects on model reliability, routing outcomes, and grounded reporting, then pushes those lessons back into later runs.
- `Topology-Adaptive Agent Router`: agent communication is optimized as a graph problem, not hardcoded as a fixed chain.
- `MCP-Native Context Graph`: literature, tools, data sources, and artifacts live in one structured context plane.
- `Experiment Graph`: baselines, ablations, metrics, and run lineage are first-class graph objects instead of spreadsheet afterthoughts.
- `Report Graph`: writing is grounded section by section against evidence, plans, experiments, and novelty claims.

## Next steps

1. Add real scholarly ingestion and citation expansion.
2. Swap the in-memory store for SQLite or Postgres.
3. Add GraphQL mutations for project ingestion, experiment creation, and report assembly.
4. Connect run-time tracing to `AgentScope`.
5. Add real literature-grounded novelty detection beyond heuristic scoring.
