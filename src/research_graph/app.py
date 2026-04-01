from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Body, File, UploadFile
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from strawberry.fastapi import GraphQLRouter
import uvicorn

from .schema import create_schema, graphql_context
from .service import ResearchGraphService


def create_app() -> FastAPI:
    service = ResearchGraphService()
    schema = create_schema(service)
    static_dir = Path(__file__).resolve().parent / "static"
    demo_id = "demo-project"
    app = FastAPI(
        title="ResearchGraph",
        version="0.2.0",
        summary="Graph-native research operating system for papers, agents, experiments, reports, and technologies.",
    )

    graphql_app = GraphQLRouter(
        schema,
        context_getter=lambda: graphql_context(service),
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "research-graph"}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/projects")
    def list_projects() -> dict:
        projects = [project.to_dict() for project in service.list_projects()]
        return {"projects": jsonable_encoder(projects)}

    @app.post("/api/projects")
    def create_project(payload: Optional[dict] = Body(default=None)) -> dict:
        body = payload or {}
        name = str(body.get("name", "")).strip() or "Untitled Research Project"
        domain = str(body.get("domain", "")).strip()
        problem = str(body.get("problem", "")).strip()
        abstract = str(body.get("abstract", "")).strip()
        if not domain or not problem:
            raise HTTPException(status_code=400, detail="domain and problem are required")
        project = service.create_project(name=name, domain=domain, problem=problem, abstract=abstract)
        return jsonable_encoder(project.to_dict())

    @app.get("/api/models")
    def models_dashboard() -> dict:
        return jsonable_encoder(service.model_dashboard())

    @app.get("/api/models/settings")
    def model_settings() -> dict:
        return jsonable_encoder(service.model_settings())

    @app.post("/api/models/settings")
    def update_model_settings(payload: Optional[dict] = Body(default=None)) -> dict:
        return jsonable_encoder(service.update_model_settings(payload or {}))

    @app.post("/api/models/custom")
    def add_custom_model(payload: Optional[dict] = Body(default=None)) -> dict:
        try:
            model = service.add_custom_model(payload or {})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return jsonable_encoder(model)

    @app.get("/api/models/ollama")
    def ollama_status() -> dict:
        return jsonable_encoder(service.ollama_status())

    @app.post("/api/models/ollama/connect")
    def connect_ollama(payload: Optional[dict] = Body(default=None)) -> dict:
        base_url = (payload or {}).get("base_url", "http://127.0.0.1:11434")
        return jsonable_encoder(service.connect_ollama(base_url))

    @app.post("/api/models/ollama/install")
    def install_ollama_model(payload: Optional[dict] = Body(default=None)) -> dict:
        model = (payload or {}).get("model", "").strip()
        if not model:
            raise HTTPException(status_code=400, detail="model is required")
        return jsonable_encoder(service.install_local_model(model))

    @app.get("/api/models/install-jobs")
    def install_jobs() -> dict:
        return {"items": jsonable_encoder(service.install_jobs())}

    @app.get("/api/projects/demo")
    def demo_project() -> dict:
        return jsonable_encoder(service.demo_project().to_dict())

    @app.get("/api/projects/demo/graphs/{graph_kind}")
    def demo_graph(graph_kind: str) -> dict:
        graph = service.build_graph(demo_id, graph_kind)
        return jsonable_encoder(graph.to_dict())

    @app.delete("/api/projects/{project_id}")
    def delete_project(project_id: str) -> dict:
        try:
            service.delete_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"deleted": project_id}

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict:
        try:
            project = service.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return jsonable_encoder(project.to_dict())

    @app.get("/api/projects/{project_id}/graphs/{graph_kind}")
    def get_graph(project_id: str, graph_kind: str) -> dict:
        try:
            graph = service.build_graph(project_id, graph_kind)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return jsonable_encoder(graph.to_dict())

    @app.post("/api/projects/{project_id}/papers")
    def add_paper(project_id: str, payload: Optional[dict] = Body(default=None)) -> dict:
        try:
            paper = service.add_paper(project_id, payload or {})
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return jsonable_encoder(paper)

    @app.post("/api/projects/{project_id}/papers/arxiv")
    def add_paper_arxiv(project_id: str, payload: Optional[dict] = Body(default=None)) -> dict:
        """Fetch a paper from an arXiv URL or ID and add it to the project."""
        raw = str((payload or {}).get("url", "")).strip()
        if not raw:
            raise HTTPException(status_code=400, detail="url is required")
        import re as _re
        # Accept full URL or bare ID like 2301.07543
        m = _re.search(r"(\d{4}\.\d{4,5}(?:v\d+)?)", raw)
        arxiv_id = m.group(1) if m else None
        if not arxiv_id:
            raise HTTPException(status_code=400, detail="Could not parse arXiv ID from input")
        try:
            from .pdf_ingestion import ingest_arxiv_pdf
            from .arxiv_search import search_arxiv
            # Try metadata from arXiv search first
            results = search_arxiv(arxiv_id, limit=1)
            base: dict = {}
            if results:
                p = results[0]
                base = {"title": p.title, "abstract": p.abstract, "authors": ", ".join(p.authors),
                        "year": p.year, "url": p.url, "venue": "arXiv"}
            else:
                # Minimal fallback — ingest PDF for text
                sections = ingest_arxiv_pdf(arxiv_id, max_chars=4000)
                abstract = " ".join(s.text[:500] for s in sections[:3]) if sections else ""
                base = {"title": f"arXiv:{arxiv_id}", "abstract": abstract,
                        "url": f"https://arxiv.org/abs/{arxiv_id}", "year": 2024}
            paper = service.add_paper(project_id, base)
            return jsonable_encoder(paper)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/projects/{project_id}/papers/upload")
    async def upload_paper_pdf(project_id: str, file: UploadFile = File(...)) -> dict:
        """Upload a PDF file, extract text, and add as a paper."""
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are accepted")
        try:
            pdf_bytes = await file.read()
            from .pdf_ingestion import _extract_text, _segment
            text = _extract_text(pdf_bytes)
            if not text:
                raise HTTPException(status_code=422, detail="Could not extract text from PDF")
            sections = _segment(text[:20000])
            abstract = " ".join(s.text[:600] for s in sections[:4] if s.title.lower() not in ("references",))
            # Use filename (minus .pdf) as title fallback
            import re as _re
            title_guess = _re.sub(r"[-_]", " ", file.filename[:-4]).strip() or "Uploaded Paper"
            paper_data = {
                "title": title_guess,
                "abstract": abstract[:2000],
                "url": "",
                "year": 2024,
            }
            paper = service.add_paper(project_id, paper_data)
            return jsonable_encoder(paper)
        except HTTPException:
            raise
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}/top-papers")
    def top_papers(project_id: str, limit: int = 5) -> dict:
        try:
            papers = service.top_papers(project_id, limit=max(1, limit))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"items": jsonable_encoder([paper.to_dict() for paper in papers])}

    @app.get("/api/projects/demo/top-papers")
    def demo_top_papers(limit: int = 5) -> dict:
        papers = service.top_papers(demo_id, limit=max(1, limit))
        return {"items": jsonable_encoder([paper.to_dict() for paper in papers])}

    @app.get("/api/projects/{project_id}/learning")
    def learning(project_id: str) -> dict:
        try:
            payload = service.learning_state(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return jsonable_encoder(payload)

    @app.get("/api/projects/demo/learning")
    def demo_learning() -> dict:
        return jsonable_encoder(service.learning_state(demo_id))

    @app.get("/api/projects/{project_id}/runs")
    def list_project_runs(project_id: str) -> dict:
        runs = [run.to_dict() for run in service.list_runs(project_id=project_id)]
        return {"items": jsonable_encoder(runs)}

    @app.delete("/api/runs")
    def clear_all_runs() -> dict:
        n = service.clear_runs()
        return {"deleted": n}

    @app.get("/api/projects/demo/runs")
    def list_demo_runs() -> dict:
        runs = [run.to_dict() for run in service.list_runs(project_id=demo_id)]
        return {"items": jsonable_encoder(runs)}

    @app.post("/api/projects/{project_id}/runs")
    def run_project(project_id: str, background_tasks: BackgroundTasks, payload: Optional[dict] = Body(default=None)) -> dict:
        try:
            body = payload or {}
            human_approval = body.get("human_approval", False)
            run = service.create_run_placeholder(project_id, objective=body.get("objective", ""), human_approval=human_approval)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        background_tasks.add_task(service.execute_run_background, run.id)
        return jsonable_encoder(run.to_dict())

    @app.post("/api/projects/demo/runs")
    def run_demo_project(background_tasks: BackgroundTasks, payload: Optional[dict] = Body(default=None)) -> dict:
        body = payload or {}
        run = service.create_run_placeholder(demo_id, objective=body.get("objective", ""), human_approval=body.get("human_approval", False))
        background_tasks.add_task(service.execute_run_background, run.id)
        return jsonable_encoder(run.to_dict())

    @app.get("/api/projects/{project_id}/novelty")
    def novelty(project_id: str) -> dict:
        try:
            items = service.novelty_hypotheses(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"items": jsonable_encoder([item.to_dict() for item in items])}

    @app.get("/api/projects/demo/novelty")
    def demo_novelty() -> dict:
        items = service.novelty_hypotheses(demo_id)
        return {"items": jsonable_encoder([item.to_dict() for item in items])}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        try:
            run = service.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return jsonable_encoder(run.to_dict())

    @app.post("/api/runs/{run_id}/resume")
    def resume_run(run_id: str, background_tasks: BackgroundTasks) -> dict:
        try:
            run = service.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if run.status == "completed":
            raise HTTPException(status_code=409, detail="Run is already completed.")
        background_tasks.add_task(service.resume_run_background, run_id)
        return jsonable_encoder({"run_id": run_id, "status": "resuming"})

    @app.get("/api/runs/{run_id}/graphs/{graph_kind}")
    def get_run_graph(run_id: str, graph_kind: str) -> dict:
        try:
            graph = service.build_run_graph(run_id, graph_kind)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return jsonable_encoder(graph.to_dict())

    # ── SSE streaming endpoint ────────────────────────────────────────────────

    @app.get("/api/runs/{run_id}/stream")
    async def stream_run(run_id: str):
        """Server-Sent Events stream for live run updates."""
        try:
            service.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        async def event_generator():
            last_stage_count = 0
            while True:
                try:
                    run = service.get_run(run_id)
                except KeyError:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Run not found'})}\n\n"
                    break

                run_dict = run.to_dict()
                current_stages = len(run_dict.get("stages", []))

                if current_stages != last_stage_count or run_dict["status"] in ("completed", "error", "awaiting_approval"):
                    last_stage_count = current_stages
                    yield f"data: {json.dumps({'type': 'update', 'run': jsonable_encoder(run_dict)})}\n\n"

                if run_dict["status"] in ("completed", "error"):
                    yield f"data: {json.dumps({'type': 'done', 'status': run_dict['status']})}\n\n"
                    break
                if run_dict["status"] == "awaiting_approval":
                    yield f"data: {json.dumps({'type': 'approval_needed', 'run': jsonable_encoder(run_dict)})}\n\n"
                    # Keep streaming but check less frequently
                    await asyncio.sleep(2)
                    continue

                await asyncio.sleep(1.5)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # ── Human-in-the-loop approval ────────────────────────────────────────────

    @app.post("/api/runs/{run_id}/approve")
    def approve_run(run_id: str, background_tasks: BackgroundTasks, payload: Optional[dict] = Body(default=None)) -> dict:
        """Approve a run paused at the judge stage. Set approved=false to reject."""
        try:
            run = service.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if run.status != "awaiting_approval":
            raise HTTPException(status_code=409, detail=f"Run is not awaiting approval (status: {run.status})")
        approved = (payload or {}).get("approved", True)
        if approved:
            background_tasks.add_task(service.resume_run_background, run_id)
            return {"run_id": run_id, "status": "approved", "message": "Run will resume."}
        else:
            run.status = "rejected"
            run.summary["rejection_reason"] = (payload or {}).get("reason", "User rejected the decision.")
            return jsonable_encoder({"run_id": run_id, "status": "rejected"})

    # ── Report export ─────────────────────────────────────────────────────────

    @app.get("/api/runs/{run_id}/export")
    def export_run(run_id: str, format: str = "md") -> PlainTextResponse:
        """Export a run's report as Markdown or LaTeX."""
        from .export import export_markdown, export_latex
        try:
            run = service.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        run_dict = run.to_dict()
        project_dict = None
        try:
            project_dict = service.get_project(run.project_id).to_dict()
        except KeyError:
            pass

        if format == "latex":
            content = export_latex(run_dict, project_dict)
            return PlainTextResponse(content, media_type="application/x-latex",
                                     headers={"Content-Disposition": f"attachment; filename={run_id}.tex"})
        else:
            content = export_markdown(run_dict, project_dict)
            return PlainTextResponse(content, media_type="text/markdown",
                                     headers={"Content-Disposition": f"attachment; filename={run_id}.md"})

    # ── Global cross-project learning ─────────────────────────────────────────

    @app.get("/api/learning/global")
    def global_learning() -> dict:
        return jsonable_encoder(service.global_learning_state())

    @app.post("/api/learning/transfer")
    def transfer_learning(payload: Optional[dict] = Body(default=None)) -> dict:
        body = payload or {}
        source = body.get("source_project_id", "")
        target = body.get("target_project_id", "")
        if not source or not target:
            raise HTTPException(status_code=400, detail="source_project_id and target_project_id required")
        count = service.transfer_lessons(source, target)
        return {"transferred": count, "source": source, "target": target}

    # ── Citation expansion ────────────────────────────────────────────────────

    @app.post("/api/projects/{project_id}/expand-citations")
    def expand_citations(project_id: str, background_tasks: BackgroundTasks, payload: Optional[dict] = Body(default=None)) -> dict:
        """Expand the paper corpus by crawling citations of top papers."""
        try:
            service.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        depth = (payload or {}).get("depth", 1)
        background_tasks.add_task(service.expand_citations_background, project_id, depth=depth)
        return {"status": "expanding", "project_id": project_id, "depth": depth}

    app.include_router(graphql_app, prefix="/graphql")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app


def run() -> None:
    uvicorn.run("research_graph.app:create_app", factory=True, host="127.0.0.1", port=8080, reload=False)

