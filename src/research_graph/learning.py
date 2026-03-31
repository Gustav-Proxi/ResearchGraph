from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Dict, List

from .runtime_models import RuntimeRun, utc_now


class SelfLearningEngine:
    def __init__(self) -> None:
        root = Path(__file__).resolve().parents[2]
        self._data_dir = root / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._data_dir / "self_learning.json"
        self._lock = threading.Lock()
        self._state = self._load_state()

    def get_project_state(self, project_id: str) -> Dict[str, object]:
        with self._lock:
            project = self._ensure_project(project_id)
            return self._public_state(project_id, project)

    def runtime_context(self, project_id: str) -> Dict[str, object]:
        state = self.get_project_state(project_id)
        return {
            "project_id": project_id,
            "prior_run_count": state["run_count"],
            "active_policies": [item["title"] for item in state["lessons"][:5]],
            "policy_details": [
                {
                    "title": item["title"],
                    "content": item["content"],
                    "stage_ids": item["stage_ids"],
                    "strength": item["strength"],
                }
                for item in state["lessons"][:5]
            ],
            "stage_guidance": {
                item["stage_id"]: item["instructions"]
                for item in state["stage_guidance"]
            },
            "model_preferences": state["model_profiles"][:5],
            "recent_adaptations": state["adaptation_history"][:3],
        }

    def learn(self, project_id: str, run: RuntimeRun) -> Dict[str, object]:
        with self._lock:
            project = self._ensure_project(project_id)
            previous_runs = project["run_count"]
            project["run_count"] = previous_runs + 1

            stage_map = {stage.stage_id: stage.stage_name for stage in run.stages}
            fallbacks = [stage for stage in run.stages if stage.model_mode == "fallback"]
            live_stages = [stage for stage in run.stages if stage.model_mode == "live"]
            lesson_specs = _derive_lessons(run, stage_map, previous_runs, fallbacks, live_stages)
            applied_ids = [
                self._merge_lesson(project, lesson)
                for lesson in lesson_specs
            ]
            self._update_model_profiles(project, run)
            reflection = {
                "run_id": run.id,
                "created_at": utc_now(),
                "summary": _reflection_summary(previous_runs, lesson_specs, fallbacks, live_stages),
                "applied_lessons": applied_ids,
                "fallback_stages": [stage.stage_name for stage in fallbacks],
                "live_stages": [stage.stage_name for stage in live_stages],
                "artifact_count": len(run.artifacts),
                "message_count": len(run.messages),
            }
            history = project.setdefault("adaptation_history", [])
            history.insert(0, reflection)
            del history[15:]
            self._persist_state()
            return self._public_state(project_id, project)

    def _merge_lesson(self, project: Dict[str, object], lesson: Dict[str, object]) -> str:
        lessons = project.setdefault("lessons", {})
        lesson_id = lesson["id"]
        stored = lessons.get(lesson_id)
        if stored:
            stored["occurrences"] += 1
            stored["last_run_id"] = lesson["last_run_id"]
            stored["stage_ids"] = sorted(set(stored.get("stage_ids", [])).union(lesson["stage_ids"]))
            stored["content"] = lesson["content"]
            stored["strength"] = round(1.0 + stored["occurrences"] * 0.35, 2)
        else:
            stored = {
                **lesson,
                "occurrences": 1,
                "strength": 1.0,
            }
            lessons[lesson_id] = stored
        stage_guidance = project.setdefault("stage_guidance", {})
        for stage_id in lesson["stage_ids"]:
            guidance = stage_guidance.setdefault(
                stage_id,
                {
                    "stage_id": stage_id,
                    "stage_name": lesson["stage_names"].get(stage_id, stage_id),
                    "instructions": [],
                    "lesson_ids": [],
                    "score": 0.0,
                },
            )
            guidance["stage_name"] = lesson["stage_names"].get(stage_id, guidance["stage_name"])
            if lesson["instruction"] not in guidance["instructions"]:
                guidance["instructions"].append(lesson["instruction"])
            if lesson_id not in guidance["lesson_ids"]:
                guidance["lesson_ids"].append(lesson_id)
            guidance["score"] = round(guidance["score"] + 0.45, 2)
        return lesson_id

    def _update_model_profiles(self, project: Dict[str, object], run: RuntimeRun) -> None:
        profiles = project.setdefault("model_profiles", {})
        for stage in run.stages:
            provider = stage.model_provider or "heuristic"
            model = stage.model_name or "local-fallback"
            key = f"{provider}::{model}"
            profile = profiles.setdefault(
                key,
                {
                    "provider": provider,
                    "model": model,
                    "total_calls": 0,
                    "live_calls": 0,
                    "fallback_calls": 0,
                    "last_error": "",
                },
            )
            profile["total_calls"] += 1
            if stage.model_mode == "live":
                profile["live_calls"] += 1
            if stage.model_mode == "fallback":
                profile["fallback_calls"] += 1
            if stage.model_error:
                profile["last_error"] = stage.model_error

    def _ensure_project(self, project_id: str) -> Dict[str, object]:
        projects = self._state.setdefault("projects", {})
        return projects.setdefault(
            project_id,
            {
                "run_count": 0,
                "lessons": {},
                "stage_guidance": {},
                "model_profiles": {},
                "adaptation_history": [],
            },
        )

    def _public_state(self, project_id: str, project: Dict[str, object]) -> Dict[str, object]:
        lessons = sorted(
            project.get("lessons", {}).values(),
            key=lambda item: (-item["strength"], item["title"]),
        )
        stage_guidance = sorted(
            project.get("stage_guidance", {}).values(),
            key=lambda item: (-item["score"], item["stage_name"]),
        )
        model_profiles = []
        for item in project.get("model_profiles", {}).values():
            total = max(1, item["total_calls"])
            model_profiles.append(
                {
                    **item,
                    "reliability": round(item["live_calls"] / total, 2),
                }
            )
        model_profiles.sort(
            key=lambda item: (-item["reliability"], -item["total_calls"], item["provider"], item["model"])
        )
        return {
            "project_id": project_id,
            "run_count": project.get("run_count", 0),
            "lessons": lessons,
            "stage_guidance": stage_guidance,
            "model_profiles": model_profiles,
            "adaptation_history": list(project.get("adaptation_history", [])),
            "latest_reflection": (project.get("adaptation_history") or [{}])[0] if project.get("adaptation_history") else {},
        }

    def _load_state(self) -> Dict[str, object]:
        if self._path.exists():
            return json.loads(self._path.read_text(encoding="utf-8"))
        state = {"projects": {}}
        self._path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state

    def _persist_state(self) -> None:
        self._path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")


def _derive_lessons(
    run: RuntimeRun,
    stage_map: Dict[str, str],
    previous_runs: int,
    fallbacks: List[object],
    live_stages: List[object],
) -> List[Dict[str, object]]:
    lessons: List[Dict[str, object]] = []
    if fallbacks:
        lessons.append(
            {
                "id": "lesson-resilient-fallback",
                "title": "Resilient model fallback",
                "category": "model-routing",
                "content": "Keep heuristic fallback active and route critical stages through the most reliable reachable provider.",
                "instruction": "Prefer resilient fallback paths and log provider failures into memory.",
                "stage_ids": [stage.stage_id for stage in fallbacks],
                "stage_names": stage_map,
                "last_run_id": run.id,
            }
        )
    if run.artifacts.get("paper_graph") and run.artifacts.get("literature_survey"):
        lessons.append(
            {
                "id": "lesson-evidence-first",
                "title": "Evidence before planning",
                "category": "research-flow",
                "content": "Preserve intake, evidence discovery, and survey before committing to implementation decisions.",
                "instruction": "Anchor planning choices in evidence coverage before expanding the task graph.",
                "stage_ids": ["agent-evidence", "agent-survey", "agent-planner"],
                "stage_names": stage_map,
                "last_run_id": run.id,
            }
        )
    if run.artifacts.get("experiment_summary") and run.artifacts.get("final_report"):
        lessons.append(
            {
                "id": "lesson-experiment-grounding",
                "title": "Experiments ground the report",
                "category": "reporting",
                "content": "Keep experiment outputs in the writer loop so the final report reflects actual evidence and ablations.",
                "instruction": "Route experiment summaries and failure motifs into the report graph before drafting.",
                "stage_ids": ["agent-executor", "agent-memory", "agent-writer"],
                "stage_names": stage_map,
                "last_run_id": run.id,
            }
        )
    if run.messages:
        lessons.append(
            {
                "id": "lesson-topology-adaptation",
                "title": "Sparse mesh swarm coordination",
                "category": "swarm-topology",
                "content": "Coordination works better when planner, memory, and coordinator remain the routing hubs instead of a flat broadcast pattern.",
                "instruction": "Keep high-value swarm traffic sparse and route novelty or failures through hub agents.",
                "stage_ids": ["agent-planning-graph", "agent-planner", "agent-coordinator"],
                "stage_names": stage_map,
                "last_run_id": run.id,
            }
        )
    if previous_runs > 0:
        lessons.append(
            {
                "id": "lesson-cross-run-reflection",
                "title": "Cross-run reflection loop",
                "category": "self-learning",
                "content": "Each run should reuse prior lessons, not restart from a blank slate.",
                "instruction": "Load prior lessons at stage start and record any new adaptation back into the learning graph.",
                "stage_ids": ["agent-intake", "agent-memory", "agent-writer"],
                "stage_names": stage_map,
                "last_run_id": run.id,
            }
        )
    if live_stages:
        lessons.append(
            {
                "id": "lesson-live-provider-available",
                "title": "Reachable model path",
                "category": "model-routing",
                "content": "A reachable model endpoint should be reused for synthesis-heavy stages before falling back.",
                "instruction": "Bias synthesis and writing stages toward the reachable provider path while keeping fallback enabled.",
                "stage_ids": [stage.stage_id for stage in live_stages],
                "stage_names": stage_map,
                "last_run_id": run.id,
            }
        )
    return lessons


def _reflection_summary(previous_runs: int, lessons: List[Dict[str, object]], fallbacks: List[object], live_stages: List[object]) -> str:
    parts = [
        f"run_index={previous_runs + 1}",
        f"lessons={len(lessons)}",
        f"fallbacks={len(fallbacks)}",
        f"live_stages={len(live_stages)}",
    ]
    if lessons:
        parts.append("top_policy=" + lessons[0]["title"])
    return " | ".join(parts)
