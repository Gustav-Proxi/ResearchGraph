from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SwarmMessage:
    id: str
    source: str
    target: str
    category: str
    content: str
    priority: float
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class TimelineEvent:
    id: str
    stage_id: str
    agent_name: str
    event_type: str
    summary: str
    detail: Dict[str, object] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class StageExecution:
    stage_id: str
    stage_name: str
    role: str
    status: str
    summary: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    artifacts_created: List[str] = field(default_factory=list)
    model_provider: str = ""
    model_name: str = ""
    model_mode: str = ""
    model_error: str = ""
    learning_applied: List[str] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class RunMemoryEntry:
    id: str
    kind: str
    title: str
    content: str
    linked_ids: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class RuntimeRun:
    id: str
    project_id: str
    project_name: str
    status: str
    objective: str
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""
    trace_run_id: str = ""
    artifacts: Dict[str, object] = field(default_factory=dict)
    stages: List[StageExecution] = field(default_factory=list)
    messages: List[SwarmMessage] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)
    memory: List[RunMemoryEntry] = field(default_factory=list)
    summary: Dict[str, object] = field(default_factory=dict)
    learning_context: Dict[str, object] = field(default_factory=dict)
    learning_state: Dict[str, object] = field(default_factory=dict)
    reflection: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "status": self.status,
            "objective": self.objective,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "trace_run_id": self.trace_run_id,
            "artifacts": self.artifacts,
            "stages": [stage.to_dict() for stage in self.stages],
            "messages": [message.to_dict() for message in self.messages],
            "timeline": [event.to_dict() for event in self.timeline],
            "memory": [entry.to_dict() for entry in self.memory],
            "summary": self.summary,
            "learning_context": self.learning_context,
            "learning_state": self.learning_state,
            "reflection": self.reflection,
        }
