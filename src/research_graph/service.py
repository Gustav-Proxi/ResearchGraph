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
from .persistence import ProjectStore, RunStore
from .runtime import AgentRuntime
from .runtime_models import RuntimeRun, StageExecution, RunMemoryEntry, SwarmMessage, TimelineEvent, utc_now
from .seed import build_demo_project, build_project_from_prompt
from .turboquant import RankedPaper, TurboQuant


def _run_from_dict(data: dict) -> RuntimeRun:
    """Rehydrate a RuntimeRun from its serialised dict form."""
    run = RuntimeRun(
        id=data["id"],
        project_id=data["project_id"],
        project_name=data["project_name"],
        status=data["status"],
        objective=data.get("objective", ""),
        started_at=data.get("started_at", utc_now()),
        finished_at=data.get("finished_at", ""),
        trace_run_id=data.get("trace_run_id", ""),
        artifacts=data.get("artifacts", {}),
        summary=data.get("summary", {}),
        learning_context=data.get("learning_context", {}),
        learning_state=data.get("learning_state", {}),
        reflection=data.get("reflection", {}),
    )
    run.stages = [
        StageExecution(
            stage_id=s["stage_id"],
            stage_name=s["stage_name"],
            role=s["role"],
            status=s["status"],
            summary=s["summary"],
            inputs=s.get("inputs", []),
            outputs=s.get("outputs", []),
            artifacts_created=s.get("artifacts_created", []),
            model_provider=s.get("model_provider", ""),
            model_name=s.get("model_name", ""),
            model_mode=s.get("model_mode", ""),
            model_error=s.get("model_error", ""),
            learning_applied=s.get("learning_applied", []),
            started_at=s.get("started_at", ""),
            finished_at=s.get("finished_at", ""),
        )
        for s in data.get("stages", [])
    ]
    run.messages = [
        SwarmMessage(
            id=m["id"], source=m["source"], target=m["target"],
            category=m["category"], content=m["content"],
            priority=m.get("priority", 0.8),
            created_at=m.get("created_at", ""),
        )
        for m in data.get("messages", [])
    ]
    run.timeline = [
        TimelineEvent(
            id=e["id"], stage_id=e["stage_id"], agent_name=e["agent_name"],
            event_type=e["event_type"], summary=e["summary"],
            detail=e.get("detail", {}),
            created_at=e.get("created_at", ""),
        )
        for e in data.get("timeline", [])
    ]
    run.memory = [
        RunMemoryEntry(
            id=m["id"], kind=m["kind"], title=m["title"],
            content=m["content"], linked_ids=m.get("linked_ids", []),
            created_at=m.get("created_at", ""),
        )
        for m in data.get("memory", [])
    ]
    return run


def _project_from_dict(data: dict) -> ResearchProject:
    """Rehydrate a ResearchProject from its serialised dict form."""
    from .models import (
        AgentStage, Artifact, ExperimentRun, NoveltyHypothesis,
        Paper, ReportSection, TaxonomyFacet, Technology,
    )

    def _paper(p: dict) -> Paper:
        return Paper(
            id=p["id"], title=p["title"], abstract=p["abstract"],
            authors=p["authors"], year=p["year"], venue=p["venue"],
            citations=p["citations"], keywords=p["keywords"],
            references=p.get("references", []),
            url=p.get("url", ""),
        )

    def _agent(a: dict) -> AgentStage:
        return AgentStage(
            id=a["id"], name=a["name"], role=a["role"],
            description=a["description"], inputs=a.get("inputs", []),
            outputs=a.get("outputs", []), depends_on=a.get("depends_on", []),
        )

    def _experiment(e: dict) -> ExperimentRun:
        return ExperimentRun(
            id=e["id"], name=e["name"], objective=e["objective"],
            status=e["status"], metrics=e.get("metrics", {}),
            based_on=e.get("based_on", []), generated_by=e.get("generated_by", ""),
        )

    def _novelty(h: dict) -> NoveltyHypothesis:
        return NoveltyHypothesis(
            id=h["id"], title=h["title"], summary=h["summary"],
            differentiators=h.get("differentiators", []),
            supporting_facets=h.get("supporting_facets", []),
            score=h.get("score", 0.0),
        )

    def _artifact(a: dict) -> Artifact:
        return Artifact(
            id=a["id"], name=a["name"], artifact_type=a["artifact_type"],
            description=a["description"], produced_by=a["produced_by"],
        )

    def _technology(t: dict) -> Technology:
        return Technology(
            id=t["id"], name=t["name"], category=t["category"],
            role=t["role"], maturity=t["maturity"],
        )

    def _section(s: dict) -> ReportSection:
        return ReportSection(
            id=s["id"], title=s["title"], purpose=s["purpose"],
            depends_on=s.get("depends_on", []), generated_by=s.get("generated_by", ""),
        )

    def _facet(f: dict) -> TaxonomyFacet:
        return TaxonomyFacet(
            id=f["id"], name=f["name"], category=f["category"],
            description=f["description"], graph_role=f["graph_role"],
            opportunities=f.get("opportunities", []),
        )

    return ResearchProject(
        id=data["id"],
        name=data["name"],
        domain=data["domain"],
        problem=data["problem"],
        abstract=data["abstract"],
        papers=[_paper(p) for p in data.get("papers", [])],
        agents=[_agent(a) for a in data.get("agents", [])],
        artifacts=[_artifact(a) for a in data.get("artifacts", [])],
        technologies=[_technology(t) for t in data.get("technologies", [])],
        experiments=[_experiment(e) for e in data.get("experiments", [])],
        report_sections=[_section(s) for s in data.get("report_sections", [])],
        taxonomy=[_facet(f) for f in data.get("taxonomy", [])],
        novelty_hypotheses=[_novelty(h) for h in data.get("novelty_hypotheses", [])],
    )


class ResearchGraphService:
    def __init__(self) -> None:
        self._project_store = ProjectStore()
        self._run_store = RunStore()
        self._projects: Dict[str, ResearchProject] = {}
        self._runs: Dict[str, RuntimeRun] = {}
        self._run_projects: Dict[str, ResearchProject] = {}
        self._model_hub = ModelHub()
        self._learning = SelfLearningEngine()
        self._turboquant = TurboQuant()
        self._runtime = AgentRuntime(
            model_settings_resolver=self._model_hub.runtime_settings,
            checkpoint_fn=self._checkpoint_run,
        )
        self._seed_demo()
        self._load_persisted()

    # ── persistence helpers ───────────────────────────────────────────────────

    def _checkpoint_run(self, run: RuntimeRun) -> None:
        self._run_store.save(run.to_dict())

    def _save_project(self, project: ResearchProject) -> None:
        self._project_store.save(project.to_dict())

    def _load_persisted(self) -> None:
        for pdata in self._project_store.load_all():
            pid = pdata.get("id", "")
            if pid and pid not in self._projects:
                try:
                    self._projects[pid] = _project_from_dict(pdata)
                except Exception:
                    pass
        for rdata in self._run_store.load_all():
            rid = rdata.get("id", "")
            if rid and rid not in self._runs:
                try:
                    self._runs[rid] = _run_from_dict(rdata)
                except Exception:
                    pass

    # ── project methods ───────────────────────────────────────────────────────

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
        self._save_project(project)
        return project

    def add_paper(self, project_id: str, paper_data: dict) -> dict:
        """Add a user-supplied paper to the project's corpus."""
        from .models import Paper
        import re

        project = self.get_project(project_id)
        title = str(paper_data.get("title", "")).strip()
        if not title:
            raise ValueError("Paper title is required.")

        safe_id = "user-" + re.sub(r"[^a-z0-9]", "", title.lower())[:24]
        # Avoid duplicates
        existing_ids = {p.id for p in project.papers}
        existing_titles = {p.title.lower() for p in project.papers}
        if safe_id in existing_ids or title.lower() in existing_titles:
            raise ValueError("A paper with this title already exists in the project.")

        # Optionally ingest PDF if url is an arXiv or direct PDF link
        abstract = str(paper_data.get("abstract", "")).strip()
        url = str(paper_data.get("url", "")).strip()
        if url and not abstract:
            try:
                from .pdf_ingestion import ingest_pdf
                sections = ingest_pdf(url, max_chars=4000)
                if sections:
                    abstract = " ".join(s.text[:500] for s in sections[:3])
            except Exception:
                pass

        paper = Paper(
            id=safe_id,
            title=title,
            abstract=abstract[:2000],
            authors=[a.strip() for a in str(paper_data.get("authors", "")).split(",") if a.strip()][:8],
            year=int(paper_data.get("year", 2024)),
            venue=str(paper_data.get("venue", "User-supplied")).strip() or "User-supplied",
            citations=int(paper_data.get("citations", 0)),
            keywords=[k.strip() for k in str(paper_data.get("keywords", "")).split(",") if k.strip()][:10],
            references=[],
            url=url,
        )
        project.papers.append(paper)
        self._save_project(project)
        return paper.to_dict()

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

    # ── run methods ───────────────────────────────────────────────────────────

    def create_run_placeholder(self, project_id: str, objective: str = "") -> RuntimeRun:
        project = self.get_project(project_id)
        run = RuntimeRun(
            id="run-" + __import__("uuid").uuid4().hex[:12],
            project_id=project.id,
            project_name=project.name,
            status="queued",
            objective=objective or project.problem,
        )
        self._runs[run.id] = run
        self._run_store.save(run.to_dict())
        return run

    def execute_run_background(self, run_id: str) -> None:
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
            self._run_store.save(run.to_dict())
        except Exception as exc:
            run.status = "error"
            run.finished_at = utc_now()
            run.summary = {"error": str(exc)}
            self._run_store.save(run.to_dict())

    def resume_run_background(self, run_id: str) -> None:
        """Resume a partial or failed run from where it left off."""
        run = self._runs.get(run_id)
        if run is None:
            return
        if run.status == "completed":
            return
        run.status = "running"
        self.execute_run_background(run_id)

    def run_project(self, project_id: str, *, objective: str = "") -> RuntimeRun:
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
        self._run_store.save(run.to_dict())
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

    # ── model + learning ──────────────────────────────────────────────────────

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

    # ── graphs ────────────────────────────────────────────────────────────────

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
        if not self._project_store.exists("demo-project"):
            demo = build_demo_project()
            self._projects[demo.id] = demo
            self._save_project(demo)
        else:
            pdata = self._project_store.load("demo-project")
            if pdata:
                try:
                    self._projects["demo-project"] = _project_from_dict(pdata)
                except Exception:
                    demo = build_demo_project()
                    self._projects[demo.id] = demo
