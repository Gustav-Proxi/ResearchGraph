from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Body
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
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
        version="0.1.0",
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

    @app.get("/api/projects/demo/runs")
    def list_demo_runs() -> dict:
        runs = [run.to_dict() for run in service.list_runs(project_id=demo_id)]
        return {"items": jsonable_encoder(runs)}

    @app.post("/api/projects/{project_id}/runs")
    def run_project(project_id: str, background_tasks: BackgroundTasks, payload: Optional[dict] = Body(default=None)) -> dict:
        try:
            run = service.create_run_placeholder(project_id, objective=(payload or {}).get("objective", ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        background_tasks.add_task(service.execute_run_background, run.id)
        return jsonable_encoder(run.to_dict())

    @app.post("/api/projects/demo/runs")
    def run_demo_project(background_tasks: BackgroundTasks, payload: Optional[dict] = Body(default=None)) -> dict:
        run = service.create_run_placeholder(demo_id, objective=(payload or {}).get("objective", ""))
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

    @app.get("/api/runs/{run_id}/graphs/{graph_kind}")
    def get_run_graph(run_id: str, graph_kind: str) -> dict:
        try:
            graph = service.build_run_graph(run_id, graph_kind)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return jsonable_encoder(graph.to_dict())

    app.include_router(graphql_app, prefix="/graphql")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app


def run() -> None:
    uvicorn.run("research_graph.app:create_app", factory=True, host="127.0.0.1", port=8080, reload=False)
