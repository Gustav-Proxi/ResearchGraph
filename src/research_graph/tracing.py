from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
from typing import Iterator, Optional


def _load_agentscope():
    workspace_root = Path(__file__).resolve().parents[3]
    sdk_path = workspace_root / "AgentScope" / "sdk" / "src"
    if sdk_path.exists() and str(sdk_path) not in sys.path:
        sys.path.insert(0, str(sdk_path))
    try:
        from agentscope import AgentScopeClient, configure, get_current_run_id, trace_context

        return AgentScopeClient, configure, get_current_run_id, trace_context
    except Exception:
        return None, None, None, None


class TraceBridge:
    def __init__(self, base_url: Optional[str] = None):
        AgentScopeClient, configure, get_current_run_id, trace_context = _load_agentscope()
        self._AgentScopeClient = AgentScopeClient
        self._configure = configure
        self._get_current_run_id = get_current_run_id
        self._trace_context = trace_context
        self.enabled = bool(trace_context)
        self.base_url = base_url
        if self.enabled:
            if base_url:
                self._configure(base_url=base_url)
            else:
                self._configure()

    @contextmanager
    def run_scope(self, name: str, metadata: Optional[dict] = None) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        try:
            with self._trace_context(
                name,
                run_name=name,
                framework="research-graph",
                metadata=metadata or {},
            ):
                yield
                return
        except Exception:
            self.enabled = False
            yield

    @contextmanager
    def step_scope(self, name: str, *, kind: str = "AGENT", input_payload=None, metadata: Optional[dict] = None) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        try:
            with self._trace_context(
                name,
                kind=kind,
                framework="research-graph",
                input_payload=input_payload,
                metadata=metadata or {},
            ):
                yield
                return
        except Exception:
            self.enabled = False
            yield

    def current_run_id(self) -> str:
        if not self.enabled or self._get_current_run_id is None:
            return ""
        return self._get_current_run_id() or ""
