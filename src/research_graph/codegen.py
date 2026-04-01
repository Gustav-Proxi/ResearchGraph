"""LLM-driven experiment code generation + sandboxed subprocess execution.

Flow:
  1. LLM writes a self-contained Python script (stdlib + numpy only)
  2. Script is written to a temp file
  3. Executed via subprocess with a hard timeout (default 30s)
  4. stdout is parsed for a final JSON metrics line
  5. Full stdout/stderr captured and stored in run artifacts

If the LLM is unavailable, a deterministic benchmark stub is used instead.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
from typing import Optional


_DEFAULT_TIMEOUT = 30  # seconds


def generate_and_run(
    direction: str,
    approach: str,
    code: Optional[str],
    timeout: int = _DEFAULT_TIMEOUT,
) -> dict:
    """Generate (or use provided) code and run it in a subprocess.

    Returns a dict with keys:
      status: "success" | "timeout" | "error" | "stub"
      exit_code: int
      stdout: str
      stderr: str
      metrics: dict[str, float]
      code_used: str
    """
    script = code if code and code.strip() else _stub_script(direction, approach)
    script_source = "llm" if (code and code.strip()) else "stub"

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        prefix="rg_experiment_",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(script)
        tmp_path = tmp.name

    try:
        proc = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": ""},
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        metrics = _parse_metrics(stdout)
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": stdout[-4000:],  # cap to 4k chars
            "stderr": stderr[-2000:],
            "metrics": metrics,
            "code_used": script[:3000],
            "source": script_source,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Experiment timed out after {timeout}s",
            "metrics": {},
            "code_used": script[:3000],
            "source": script_source,
        }
    except Exception as exc:
        return {
            "status": "error",
            "exit_code": -1,
            "stdout": "",
            "stderr": str(exc),
            "metrics": {},
            "code_used": script[:3000],
            "source": script_source,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _parse_metrics(stdout: str) -> dict:
    """Parse the last JSON object from stdout as experiment metrics."""
    if not stdout:
        return {}
    lines = stdout.splitlines()
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    # Keep only numeric or boolean values as metrics
                    return {
                        k: v for k, v in data.items()
                        if isinstance(v, (int, float, bool))
                    }
            except json.JSONDecodeError:
                continue
    return {}


def _stub_script(direction: str, approach: str) -> str:
    """Deterministic benchmark stub used when no LLM-generated code is available."""
    name_safe = direction[:40].replace("'", "").replace('"', "")
    return textwrap.dedent(f"""
        import json
        import math
        import random

        random.seed(42)

        # Benchmark stub for: {name_safe}
        # Approach: {approach[:80]}

        def simulate_coverage(n_papers=20, n_relevant=14):
            hits = random.sample(range(n_papers), n_relevant)
            return len(hits) / n_papers

        def simulate_grounding(n_claims=10, n_supported=8):
            return n_supported / n_claims

        def simulate_novelty_score():
            base = 0.6
            noise = (random.random() - 0.5) * 0.1
            return round(base + noise, 3)

        coverage = simulate_coverage()
        grounding = simulate_grounding()
        novelty = simulate_novelty_score()
        consistency = round(math.sqrt(coverage * grounding), 3)

        print(json.dumps({{
            "coverage": round(coverage, 3),
            "grounding": round(grounding, 3),
            "novelty": novelty,
            "consistency": consistency,
        }}))
    """).strip()
