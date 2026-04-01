# ResearchGraph

An end-to-end autonomous research operating system. Submit a domain and research problem — ResearchGraph surveys the literature, identifies gaps, synthesises novel ideas, runs experiments, and writes a full research report without further input.

## What it does

1. **Literature survey** — searches Semantic Scholar + arXiv, ranks papers by semantic similarity via embeddings
2. **Gap analysis** — LLM-driven identification of open problems in the field
3. **Proposal generation** — multiple research directions with feasibility and novelty scores
4. **Critique & grounding** — adversarial agent challenges each proposal against evidence
5. **Novelty hypotheses** — concrete novel architectures or methods grounded in papers
6. **Experiment design & execution** — auto-generates and runs experiment stubs
7. **Research report** — full paper draft (problem, related work, methodology, results, conclusions)
8. **Self-learning** — lessons from each run are persisted and fed back into future runs

## Quick start

```bash
cd ResearchGraph
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
research-graph-api
# → http://127.0.0.1:8080
```

Set your OpenRouter key for real LLM calls:
```bash
export OPENROUTER_API_KEY=sk-or-...
```

Optionally add a Semantic Scholar key for higher rate limits:
```bash
export SEMANTIC_SCHOLAR_API_KEY=...
```

## Architecture

| Layer | What it does |
|-------|-------------|
| **Frontend** | Vanilla JS, sidebar navigation, live 2D force graph (ring nodes, curved arrows), pipeline progress |
| **FastAPI backend** | `POST /api/projects/{id}/runs` starts background run, frontend polls `GET /api/runs/{id}` every 1.8s |
| **AgentRuntime** | Topological stage execution over a dependency graph of 13+ specialist agents |
| **ResearchToolbox** | Per-stage LLM calls via OpenRouter; falls back gracefully if key missing |
| **EmbeddingClient** | Ollama-first, falls back to OpenRouter `text-embedding-3-small` |
| **TurboQuant** | Semantic similarity ranking of papers using cosine distance on embeddings |
| **SelfLearningEngine** | Persists lessons, model profiles, and policies across runs in `data/self_learning.json` |
| **ModelHub** | Provider registry, Ollama integration, one-click local model installs |

## Pipeline stages

```
Intake → Evidence Scout → Planning Graph → Survey →
Planner → Critic → Grounding → Novelty → Coordinator →
Judge → Executor → Memory → Writer
```

Each stage writes artifacts to the run object, which the live graph endpoint reads incrementally.

## Graph views

The Knowledge Graph view shows 8 different projections of the same research run:

| Kind | What it shows |
|------|--------------|
| `unified` | All nodes and relationships together |
| `papers` | Citation and evidence network |
| `agents` | Pipeline agent flow |
| `experiments` | Experiment design and results |
| `reports` | Report section structure |
| `learning` | Cross-run lessons and model reliability |
| `technology` | Methods, tools, and technology landscape |
| `agentic` | Taxonomy of agentic capabilities |

Graphs build live during a run — nodes animate in as each stage completes.

## Key files

| File | Purpose |
|------|---------|
| `src/research_graph/app.py` | FastAPI routes |
| `src/research_graph/service.py` | Orchestration service, run lifecycle |
| `src/research_graph/runtime.py` | AgentRuntime — topological stage execution |
| `src/research_graph/tools.py` | Stage artifact generators with LLM calls |
| `src/research_graph/graphs.py` | 8 graph builders + live incremental graph |
| `src/research_graph/paper_search.py` | Semantic Scholar + arXiv search with caching |
| `src/research_graph/arxiv_search.py` | arXiv Atom feed search (no key required) |
| `src/research_graph/embeddings.py` | Embedding client (Ollama → OpenRouter fallback) |
| `src/research_graph/llm_router.py` | LLM routing across providers |
| `src/research_graph/model_hub.py` | Provider registry, Ollama, local model installs |
| `src/research_graph/learning.py` | Self-learning engine, cross-run reflection |
| `src/research_graph/turboquant.py` | Semantic paper ranking |
| `src/research_graph/seed.py` | Demo project and pipeline definition |
| `src/research_graph/static/` | Frontend (index.html, app.js, styles.css) |

## REST API

```
GET  /health
GET  /api/projects
POST /api/projects
GET  /api/projects/{id}
GET  /api/projects/{id}/graphs/{kind}
POST /api/projects/{id}/runs
GET  /api/projects/{id}/runs
GET  /api/runs/{id}
GET  /api/runs/{id}/graphs/{kind}
GET  /api/runs/{id}/stream          SSE live updates
GET  /api/runs/{id}/export?format=md|latex
POST /api/runs/{id}/approve         human-in-the-loop approval
DELETE /api/runs                    clear run history
GET  /api/models/settings
POST /api/models/settings
GET  /api/models/ollama
POST /api/models/ollama/connect
POST /api/models/ollama/install
GET  /api/models/install-jobs
POST /api/models/custom
```

## Model support

- **OpenRouter** — any model via `openrouter` provider (default: `openai/gpt-4.1`)
- **Ollama** — local models, auto-detected at `http://127.0.0.1:11434`
- **LM Studio** — OpenAI-compatible endpoint at `http://127.0.0.1:1234/v1`
- **Custom** — any OpenAI-compatible endpoint

Configure in Settings tab or via `data/model_hub.json`.

## Development notes

- State is in-memory only — restarts lose runs (by design for now)
- Self-learning state persists to `data/self_learning.json`
- Paper search results are cached in-process per query to avoid rate limits
- Each pipeline run makes ~13 LLM calls (one per stage); typical duration 2–4 min on OpenRouter
- The frontend polls `/api/runs/{id}` every 1.8s during active runs
