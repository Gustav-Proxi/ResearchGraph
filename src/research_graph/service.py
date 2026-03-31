from __future__ import annotations

from typing import Dict, List, Optional
from uuid import uuid4

from .graphs import (
    build_agent_graph,
    build_agentic_graph,
    build_experiment_graph,
    build_learning_graph,
    build_paper_graph,
    build_report_graph,
    build_runtime_agent_graph,
    build_runtime_experiment_graph,
    build_runtime_learning_graph,
    build_runtime_report_graph,
    build_runtime_unified_graph,
    build_technology_graph,
    build_unified_graph,
)
from .learning import SelfLearningEngine
from .model_hub import ModelHub
from .models import GraphData, ResearchProject
from .runtime import AgentRuntime
from .runtime_models import RuntimeRun, utc_now
from .seed import build_demo_project, build_project_from_prompt
from .turboquant import RankedPaper, TurboQuant


class ResearchGraphService:
    def __init__(self) -> None:
        self._projects: Dict[str, ResearchProject] = {}
        self._runs: Dict[str, RuntimeRun] = {}
        self._run_projects: Dict[str, ResearchProject] = {}
        self._model_hub = ModelHub()
        self._learning = SelfLearningEngine()
        self._turboquant = TurboQuant()
        self._runtime = AgentRuntime(model_settings_resolver=self._model_hub.runtime_settings)
        self._seed_demo()

    def list_projects(self) -> List[ResearchProject]:
        return list(self._projects.values())

    def get_project(self, project_id: str) -> ResearchProject:
        try:
            return self._projects[project_id]
        except KeyError as exc:
            raise KeyError("Unknown project_id: %s" % project_id) from exc

    def create_project(self, name: str, domain: str, problem: str, abstract: str) -> ResearchProject:
        project_id = "project-" + uuid4().hex[:10]
        project = build_project_from_prompt(
            project_id=project_id,
            name=name,
            domain=domain,
            problem=problem,
            abstract=abstract,
        )
        self._projects[project.id] = project
        return project

    def top_papers(self, project_id: str, limit: int = 5) -> List[RankedPaper]:
        project = self.get_project(project_id)
        return self._turboquant.rank_papers(project, limit=limit)

    def graph_signal(self, project_id: str) -> Dict[str, float]:
        project = self.get_project(project_id)
        return self._turboquant.graph_signal(project)

    def novelty_hypotheses(self, project_id: str):
        project = self.get_project(project_id)
        hypotheses = self._turboquant.rank_novelty(project)
        project.novelty_hypotheses = hypotheses
        return hypotheses

    def create_run_placeholder(self, project_id: str, objective: str = "") -> RuntimeRun:
        """Create a run entry immediately (status=queued) so the frontend can poll it."""
        project = self.get_project(project_id)
        run = RuntimeRun(
            id="run-" + __import__("uuid").uuid4().hex[:12],
            project_id=project.id,
            project_name=project.name,
            status="queued",
            objective=objective or project.problem,
        )
        self._runs[run.id] = run
        return run

    def execute_run_background(self, run_id: str) -> None:
        """Execute a run in the background, updating the shared run object live."""
        run = self._runs.get(run_id)
        if run is None:
            return
        try:
            project = self.get_project(run.project_id)
            learning_context = self._learning.runtime_context(run.project_id)
            _, snapshot = self._runtime.execute(
                project,
                objective=run.objective,
                learning_context=learning_context,
                run_ref=run,
            )
            learning_state = self._learning.learn(run.project_id, run)
            run.learning_state = learning_state
            run.reflection = learning_state.get("latest_reflection", {})
            run.artifacts["self_learning_state"] = {
                "run_count": learning_state["run_count"],
                "top_lessons": [item["title"] for item in learning_state["lessons"][:5]],
                "top_model_profiles": learning_state["model_profiles"][:3],
            }
            run.artifacts["self_learning_reflection"] = run.reflection
            run.summary["artifacts"] = sorted(run.artifacts.keys())
            run.summary["learned_policies"] = len(learning_state["lessons"])
            run.summary["learning_runs"] = learning_state["run_count"]
            self._run_projects[run_id] = snapshot
        except Exception as exc:
            run.status = "error"
            run.finished_at = utc_now()
            run.summary = {"error": str(exc)}

    def run_project(self, project_id: str, *, objective: str = "") -> RuntimeRun:
        """Synchronous run (kept for backwards compatibility)."""
        project = self.get_project(project_id)
        learning_context = self._learning.runtime_context(project_id)
        run, snapshot = self._runtime.execute(project, objective=objective, learning_context=learning_context)
        learning_state = self._learning.learn(project_id, run)
        run.learning_state = learning_state
        run.reflection = learning_state.get("latest_reflection", {})
        run.artifacts["self_learning_state"] = {
            "run_count": learning_state["run_count"],
            "top_lessons": [item["title"] for item in learning_state["lessons"][:5]],
            "top_model_profiles": learning_state["model_profiles"][:3],
        }
        run.artifacts["self_learning_reflection"] = run.reflection
        run.summary["artifacts"] = sorted(run.artifacts.keys())
        run.summary["learned_policies"] = len(learning_state["lessons"])
        run.summary["learning_runs"] = learning_state["run_count"]
        self._runs[run.id] = run
        self._run_projects[run.id] = snapshot
        return run

    def list_runs(self, project_id: Optional[str] = None) -> List[RuntimeRun]:
        runs = list(self._runs.values())
        if project_id:
            runs = [run for run in runs if run.project_id == project_id]
        return sorted(runs, key=lambda item: item.started_at, reverse=True)

    def get_run(self, run_id: str) -> RuntimeRun:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise KeyError("Unknown run_id: %s" % run_id) from exc

    def model_dashboard(self) -> Dict[str, object]:
        return self._model_hub.dashboard_state()

    def learning_state(self, project_id: str) -> Dict[str, object]:
        self.get_project(project_id)
        return self._learning.get_project_state(project_id)

    def model_settings(self) -> Dict[str, object]:
        return self._model_hub.settings()

    def update_model_settings(self, payload: Dict[str, object]) -> Dict[str, object]:
        return self._model_hub.update_settings(payload)

    def add_custom_model(self, payload: Dict[str, str]) -> Dict[str, object]:
        return self._model_hub.add_custom_model(payload)

    def ollama_status(self, base_url: Optional[str] = None) -> Dict[str, object]:
        return self._model_hub.ollama_status(base_url=base_url)

    def connect_ollama(self, base_url: str) -> Dict[str, object]:
        return self._model_hub.connect_ollama(base_url)

    def install_local_model(self, model: str) -> Dict[str, object]:
        return self._model_hub.start_ollama_install(model)

    def install_jobs(self) -> List[Dict[str, object]]:
        return self._model_hub.list_install_jobs()

    def build_graph(self, project_id: str, graph_kind: str) -> GraphData:
        project = self.get_project(project_id)
        if graph_kind == "papers":
            return build_paper_graph(project)
        if graph_kind == "agents":
            return build_agent_graph(project)
        if graph_kind == "experiments":
            return build_experiment_graph(project)
        if graph_kind == "reports":
            return build_report_graph(project)
        if graph_kind == "learning":
            return build_learning_graph(project, self._learning.get_project_state(project_id))
        if graph_kind == "agentic":
            project.novelty_hypotheses = self._turboquant.rank_novelty(project)
            return build_agentic_graph(project)
        if graph_kind == "technology":
            return build_technology_graph(project)
        if graph_kind == "unified":
            project.novelty_hypotheses = self._turboquant.rank_novelty(project)
            return build_unified_graph(project)
        raise KeyError("Unsupported graph kind: %s" % graph_kind)

    def build_run_graph(self, run_id: str, graph_kind: str) -> GraphData:
        try:
            project = self._run_projects[run_id]
            run = self._runs[run_id]
        except KeyError as exc:
            raise KeyError("Unknown run_id: %s" % run_id) from exc
        if graph_kind == "papers":
            return build_paper_graph(project)
        if graph_kind == "agents":
            return build_runtime_agent_graph(project, run)
        if graph_kind == "experiments":
            return build_runtime_experiment_graph(project, run)
        if graph_kind == "reports":
            return build_runtime_report_graph(project, run)
        if graph_kind == "learning":
            return build_runtime_learning_graph(project, run)
        if graph_kind == "technology":
            return build_technology_graph(project)
        if graph_kind == "agentic":
            project.novelty_hypotheses = self._turboquant.rank_novelty(project)
            return build_agentic_graph(project)
        if graph_kind == "unified":
            project.novelty_hypotheses = self._turboquant.rank_novelty(project)
            return build_runtime_unified_graph(project, run)
        raise KeyError("Unsupported graph kind: %s" % graph_kind)

    def demo_project(self) -> ResearchProject:
        return self.get_project("demo-project")

    def _seed_demo(self) -> None:
        demo = build_demo_project()
        self._projects[demo.id] = demo
