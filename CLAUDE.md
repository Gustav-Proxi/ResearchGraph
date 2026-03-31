# ResearchGraph — Project Context

## What This Is

End-to-end **autonomous research suite**. User submits a domain + problem, system does everything:

1. Literature survey → builds knowledge graph of relevant papers
2. Gap analysis → finds what hasn't been solved
3. Novelty synthesis → proposes novel ideas/architectures grounded in evidence
4. Experiment design & execution → auto-researcher style validation
5. Full research report → paper draft with executive summary, findings, conclusions

**Core value**: Submit your research problem → get a full paper draft + novelty map in minutes.

## UX Principles

- **Query form is the hero** — must be the first prominent element, not hidden in a tab
- **Graph builds live** — nodes appear as each pipeline stage completes (polling-based)
- **Stage progress visible** during execution so user knows what's happening
- **Report is the deliverable** — make it easy to read and export
- User should need to do NOTHING after submitting the query

## Architecture

- **Backend**: FastAPI on `127.0.0.1:8080` (uvicorn, `research-graph-api` CLI)
- **Execution**: Background task pattern — `POST /runs` returns immediately with run_id, frontend polls `GET /api/runs/{id}` every 1.5s
- **Runtime**: `AgentRuntime` in `runtime.py` — topological stage execution
- **Graph**: 8 graph types (papers, agents, experiments, reports, learning, technology, agentic, unified)
- **Frontend**: Vanilla JS + D3 v7 force graph, dark neon theme

## Stack

- Python 3.11+, FastAPI, Uvicorn, Strawberry GraphQL
- Frontend: Vanilla JS, D3.js v7, Inter font, no framework
- No database — in-memory state only (restarts lose data)

## Run

```bash
cd ResearchGraph
pip install -e .
research-graph-api
# → http://127.0.0.1:8080
```

## Key Files

| File | Purpose |
|------|---------|
| `src/research_graph/app.py` | FastAPI routes |
| `src/research_graph/service.py` | Orchestration service |
| `src/research_graph/runtime.py` | AgentRuntime — stage execution |
| `src/research_graph/graphs.py` | 8 graph builders |
| `src/research_graph/tools.py` | Stage artifact generators |
| `src/research_graph/seed.py` | Demo project + bootstrap |
| `src/research_graph/static/index.html` | Frontend HTML |
| `src/research_graph/static/app.js` | Frontend JS |
| `src/research_graph/static/styles.css` | Dark neon CSS |
