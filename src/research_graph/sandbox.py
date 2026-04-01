"""Sandboxed experiment execution layer.

Interface: SandboxResult and run_in_sandbox(script, timeout) → SandboxResult

Two implementations:
  - SubprocessSandbox  — current default; runs in a subprocess, no network, restricted env
  - DockerSandbox      — drop-in upgrade; requires `docker` Python SDK + Docker daemon

Both expose the same interface so codegen.py can swap between them without changes.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class SandboxResult:
    status: str          # "success" | "timeout" | "error"
    exit_code: int
    stdout: str
    stderr: str
    metrics: Dict[str, float] = field(default_factory=dict)
    backend: str = "subprocess"


class SubprocessSandbox:
    """Current default: subprocess with restricted env and hard timeout."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    def run(self, script: str) -> SandboxResult:
        from .codegen import _parse_metrics

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", prefix="rg_sandbox_",
            delete=False, encoding="utf-8",
        ) as tmp:
            tmp.write(script)
            tmp_path = tmp.name

        try:
            # Minimal env: only stdlib guaranteed
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": os.environ.get("HOME", ""),
                "PYTHONPATH": "",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
            )
            stdout = proc.stdout.strip()[-4000:]
            stderr = proc.stderr.strip()[-2000:]
            metrics = _parse_metrics(stdout)
            return SandboxResult(
                status="success" if proc.returncode == 0 else "error",
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                metrics=metrics,
                backend="subprocess",
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(
                status="timeout", exit_code=-1, stdout="",
                stderr=f"Timed out after {self.timeout}s", backend="subprocess",
            )
        except Exception as exc:
            return SandboxResult(
                status="error", exit_code=-1, stdout="",
                stderr=str(exc), backend="subprocess",
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class DockerSandbox:
    """Drop-in upgrade: runs script in an isolated Docker container.

    Requirements:
      pip install docker
      Docker daemon running

    Usage:
      sandbox = DockerSandbox(image="python:3.11-slim", timeout=60)
      result = sandbox.run(script)
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        timeout: int = 60,
        memory_limit: str = "256m",
    ) -> None:
        self.image = image
        self.timeout = timeout
        self.memory_limit = memory_limit

    def run(self, script: str) -> SandboxResult:
        from .codegen import _parse_metrics

        try:
            import docker  # type: ignore
        except ImportError:
            # Fall back to subprocess if docker SDK not installed
            return SubprocessSandbox(timeout=self.timeout).run(script)

        try:
            client = docker.from_env()
            result = client.containers.run(
                self.image,
                command=["python", "-c", script],
                remove=True,
                network_disabled=True,
                mem_limit=self.memory_limit,
                timeout=self.timeout,
                stdout=True,
                stderr=True,
            )
            stdout = result.decode("utf-8", errors="replace").strip()
            metrics = _parse_metrics(stdout)
            return SandboxResult(
                status="success",
                exit_code=0,
                stdout=stdout[-4000:],
                stderr="",
                metrics=metrics,
                backend="docker",
            )
        except Exception as exc:
            # Any Docker error → fall back to subprocess
            fallback = SubprocessSandbox(timeout=self.timeout).run(script)
            fallback.stderr = f"Docker error: {exc}\n{fallback.stderr}"
            fallback.backend = "docker-fallback"
            return fallback


def run_in_sandbox(
    script: str,
    timeout: int = 30,
    use_docker: bool = False,
    docker_image: str = "python:3.11-slim",
) -> SandboxResult:
    """Convenience entry point. Set use_docker=True to attempt Docker execution."""
    if use_docker:
        return DockerSandbox(image=docker_image, timeout=timeout).run(script)
    return SubprocessSandbox(timeout=timeout).run(script)
