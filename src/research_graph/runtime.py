from __future__ import annotations

from copy import deepcopy
from graphlib import TopologicalSorter
from typing import Callable, Dict, List, Optional
from uuid import uuid4

from .embeddings import EmbeddingClient
from .llm_router import LLMRouter
from .models import AgentStage, ResearchProject
from .runtime_models import RuntimeRun, StageExecution, utc_now
from .tools import ResearchToolbox, make_memory_entries, make_swarm_messages, make_timeline_event
from .tracing import TraceBridge


class AgentRuntime:
    def __init__(
        self,
        *,
        trace_base_url: Optional[str] = None,
        model_settings_resolver: Optional[Callable[[], Dict[str, object]]] = None,
        checkpoint_fn: Optional[Callable[[RuntimeRun], None]] = None,
    ) -> None:
        self._toolbox = ResearchToolbox(llm=None)
        self._trace = TraceBridge(base_url=trace_base_url)
        self._model_settings_resolver = model_settings_resolver or (lambda: {})
        # Called after each stage completes — used by persistence layer for checkpointing
        self._checkpoint_fn = checkpoint_fn

    def execute(
        self,
        project: ResearchProject,
        *,
        objective: str = "",
        learning_context: Optional[Dict[str, object]] = None,
        run_ref: Optional[RuntimeRun] = None,
        resume_from: Optional[str] = None,
    ) -> tuple[RuntimeRun, ResearchProject]:
        snapshot = deepcopy(project)
        settings = self._model_settings_resolver()
        llm = LLMRouter(settings)
        embedder = EmbeddingClient(settings)
        self._toolbox = ResearchToolbox(llm=llm, embedder=embedder)
        if run_ref is not None:
            run = run_ref
            run.project_id = snapshot.id
            run.project_name = snapshot.name
            run.status = "running"
            run.objective = objective or run.objective or snapshot.problem
            run.learning_context = deepcopy(learning_context or {})
        else:
            run = RuntimeRun(
                id="run-" + uuid4().hex[:12],
                project_id=snapshot.id,
                project_name=snapshot.name,
                status="running",
                objective=objective or snapshot.problem,
                learning_context=deepcopy(learning_context or {}),
            )

        # Determine which stages have already completed (for resume)
        completed_stage_ids = {s.stage_id for s in run.stages if s.status == "completed"}

        with self._trace.run_scope(
            f"{snapshot.name} runtime",
            metadata={"project_id": snapshot.id, "objective": run.objective},
        ):
            run.trace_run_id = self._trace.current_run_id()
            run.timeline.append(
                make_timeline_event(run.id, "system", "Runtime", "run_started", "ResearchGraph runtime started.")
            )
            for stage in self._ordered_stages(snapshot.agents):
                if stage.id in completed_stage_ids:
                    # Skip already-completed stages on resume
                    continue
                self._execute_stage(snapshot, stage, run, llm)
                if self._checkpoint_fn is not None:
                    try:
                        self._checkpoint_fn(run)
                    except Exception:
                        pass  # checkpoint failures must not abort the run

            # Attach LLM generation log to artifacts
            log_payload = self._toolbox.llm_generation_log()
            run.artifacts.update(log_payload)

            run.status = "completed"
            run.finished_at = utc_now()
            judged = run.artifacts.get("judged_decision", {}) if isinstance(run.artifacts.get("judged_decision", {}), dict) else {}
            run.summary = {
                "completed_stages": len(run.stages),
                "artifacts": sorted(run.artifacts.keys()),
                "messages": len(run.messages),
                "memory_entries": len(run.memory),
                "prior_runs": run.learning_context.get("prior_run_count", 0),
                "active_policies": run.learning_context.get("active_policies", []),
                "applied_learning_lessons": sum(len(stage.learning_applied) for stage in run.stages),
                "selected_decision": judged.get("decision_title", ""),
                "trace_run_id": run.trace_run_id,
                "llm_success_rate": log_payload.get("llm_generation_summary", {}).get("success_rate", 0.0),
            }
            run.timeline.append(
                make_timeline_event(run.id, "system", "Runtime", "run_finished", "ResearchGraph runtime completed.", run.summary)
            )
        return run, snapshot

    def _execute_stage(self, project: ResearchProject, stage: AgentStage, run: RuntimeRun, llm: LLMRouter = None) -> None:
        execution = StageExecution(
            stage_id=stage.id,
            stage_name=stage.name,
            role=stage.role,
            status="running",
            summary=f"Executing {stage.name}.",
            inputs=stage.inputs,
            outputs=stage.outputs,
        )
        stage_guidance = self._stage_guidance(stage, run.learning_context)
        execution.learning_applied = list(stage_guidance)
        run.stages.append(execution)
        run.timeline.append(
            make_timeline_event(
                run.id,
                stage.id,
                stage.name,
                "stage_started",
                execution.summary,
                {"inputs": stage.inputs, "learning_applied": execution.learning_applied},
            )
        )

        with self._trace.step_scope(
            stage.name,
            kind="AGENT",
            input_payload={"inputs": stage.inputs, "outputs": stage.outputs},
            metadata={"stage_id": stage.id, "role": stage.role},
        ):
            stage_messages = make_swarm_messages(
                run.id,
                stage.id,
                stage.id,
                self._toolbox.stage_messages(stage.id, stage.role),
            )
            run.messages.extend(stage_messages)
            for message in stage_messages:
                run.timeline.append(
                    make_timeline_event(
                        run.id,
                        stage.id,
                        stage.name,
                        "swarm_message",
                        f"{stage.name} -> {message.target}: {message.content}",
                        message.to_dict(),
                    )
                )

            payload = self._run_stage_tool(project, stage, run, stage_guidance)
            # Record which model/provider the toolbox used (from the log, not a second LLM call)
            last_log = self._toolbox.last_llm_log_entry()
            if last_log:
                execution.model_provider = last_log.get("provider", "")
                execution.model_name     = last_log.get("model", "")
                execution.model_mode     = last_log.get("mode", "")
                execution.model_error    = last_log.get("error", "")
            for artifact_name, artifact_value in payload.items():
                if artifact_name == "memory_graph":
                    run.memory.extend(make_memory_entries(run.id, artifact_value))
                else:
                    run.artifacts[artifact_name] = artifact_value
            adaptations = run.artifacts.setdefault("learning_adaptations", [])
            if isinstance(adaptations, list):
                adaptations.append(
                    {
                        "stage_id": stage.id,
                        "stage_name": stage.name,
                        "applied_lessons": execution.learning_applied,
                        "model_provider": execution.model_provider,
                        "model_mode": execution.model_mode,
                    }
                )

        execution.status = "completed"
        execution.summary = f"{stage.name} completed."
        execution.finished_at = utc_now()
        execution.artifacts_created = list(payload.keys())
        run.timeline.append(
            make_timeline_event(
                run.id,
                stage.id,
                stage.name,
                "stage_finished",
                execution.summary,
                {"artifacts_created": execution.artifacts_created},
            )
        )

    def _run_stage_tool(self, project: ResearchProject, stage: AgentStage, run: RuntimeRun, stage_guidance: List[str]) -> dict:
        role = stage.role.lower()
        with self._trace.step_scope(
            f"{stage.name} toolchain",
            kind="TOOL",
            input_payload={"role": stage.role},
            metadata={"stage_id": stage.id},
        ):
            if stage.id == "agent-intake":
                return self._apply_learning_to_payload(self._toolbox.intake(project), stage, run, stage_guidance)
            if stage.id == "agent-evidence":
                return self._apply_learning_to_payload(self._toolbox.evidence_discovery(project), stage, run, stage_guidance)
            if stage.id == "agent-planning-graph":
                return self._apply_learning_to_payload(
                    self._toolbox.planning_graph(project, learning_context=run.learning_context),
                    stage, run, stage_guidance,
                )
            if stage.id == "agent-survey":
                return self._apply_learning_to_payload(self._toolbox.survey(project), stage, run, stage_guidance)
            if stage.id == "agent-planner":
                return self._apply_learning_to_payload(self._toolbox.proposal_options(project, run.artifacts), stage, run, stage_guidance)
            if stage.id == "agent-critic":
                return self._apply_learning_to_payload(self._toolbox.critique(project, run.artifacts), stage, run, stage_guidance)
            if stage.id == "agent-grounding":
                return self._apply_learning_to_payload(self._toolbox.grounding(project, run.artifacts), stage, run, stage_guidance)
            if stage.id == "agent-judge":
                return self._apply_learning_to_payload(self._toolbox.judge(run.artifacts), stage, run, stage_guidance)
            if stage.id == "agent-codegen":
                return self._apply_learning_to_payload(self._toolbox.generate_experiment_code(project, run.artifacts), stage, run, stage_guidance)
            if stage.id == "agent-executor":
                return self._apply_learning_to_payload(self._toolbox.execute_experiments(project, run.artifacts), stage, run, stage_guidance)
            if stage.id == "agent-memory":
                payload = self._toolbox.build_memory(project, run.artifacts)
                # Also validate hypotheses against experiments
                validation = self._toolbox.update_hypotheses_from_experiments(run.artifacts)
                payload.update(validation)
                return self._apply_learning_to_payload(payload, stage, run, stage_guidance)
            if stage.id == "agent-coordinator":
                return self._apply_learning_to_payload(self._toolbox.coordinate_vote(project, run.artifacts), stage, run, stage_guidance)
            if stage.id == "agent-novelty":
                return self._apply_learning_to_payload(self._toolbox.novelty(project, run.artifacts), stage, run, stage_guidance)
            if stage.id == "agent-writer":
                return self._apply_learning_to_payload(self._toolbox.report(project, run.artifacts), stage, run, stage_guidance)
            if "planning" in role:
                return self._apply_learning_to_payload(
                    self._toolbox.planning_graph(project, learning_context=run.learning_context),
                    stage, run, stage_guidance,
                )
            return self._apply_learning_to_payload({}, stage, run, stage_guidance)

    def _apply_learning_to_payload(self, payload: dict, stage: AgentStage, run: RuntimeRun, stage_guidance: List[str]) -> dict:
        updated = deepcopy(payload)
        prior_runs = run.learning_context.get("prior_run_count", 0)
        if stage_guidance:
            updated[f"{stage.id}_adaptation"] = {
                "stage": stage.name,
                "prior_runs": prior_runs,
                "applied_lessons": stage_guidance,
            }
        if "research_brief" in updated:
            updated["research_brief"]["historical_context"] = {
                "prior_runs": prior_runs,
                "active_policies": run.learning_context.get("active_policies", []),
            }
        if "task_graph" in updated:
            updated["adaptive_task_policies"] = stage_guidance
        if "implementation_plan" in updated and stage_guidance:
            updated["implementation_plan"] = [
                f"Adaptive policy: {item}" for item in stage_guidance[:2]
            ] + list(updated["implementation_plan"])
        if "experiment_summary" in updated:
            updated["experiment_summary"]["adaptive_policies"] = stage_guidance
            updated["experiment_summary"]["prior_runs"] = prior_runs
        if "evidence_context" in updated:
            updated["evidence_context"]["active_policies"] = run.learning_context.get("active_policies", [])
        if "coordination_topology" in updated:
            updated["coordination_topology"]["learned_bias"] = stage_guidance
        if "novelty_hypotheses" in updated and stage_guidance:
            updated["novelty_learning_bias"] = stage_guidance
        if "paper_draft" in updated and stage_guidance:
            section = updated["paper_draft"].get("report-results", "")
            updated["paper_draft"]["report-results"] = (
                f"{section} Adaptive note: {'; '.join(stage_guidance[:2])}."
            ).strip()
        if "final_report" in updated:
            updated["final_report"]["prior_runs"] = prior_runs
            updated["final_report"]["learning_applied"] = stage_guidance
        if "judged_decision" in updated:
            updated["judged_decision"]["prior_runs"] = prior_runs
            updated["judged_decision"]["learning_applied"] = stage_guidance
        return updated

    def _stage_guidance(self, stage: AgentStage, learning_context: Dict[str, object]) -> List[str]:
        stage_guidance = learning_context.get("stage_guidance", {})
        return list(stage_guidance.get(stage.id, []))

    def _ordered_stages(self, stages: List[AgentStage]) -> List[AgentStage]:
        sorter = TopologicalSorter()
        by_id = {stage.id: stage for stage in stages}
        for stage in stages:
            sorter.add(stage.id, *stage.depends_on)
        ordered_ids = tuple(sorter.static_order())
        return [by_id[stage_id] for stage_id in ordered_ids if stage_id in by_id]


def _preview(value):
    if isinstance(value, list):
        return value[:3]
    if isinstance(value, dict):
        return {key: value[key] for key in list(value.keys())[:5]}
    return value
