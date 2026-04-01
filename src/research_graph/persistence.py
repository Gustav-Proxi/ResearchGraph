"""SQLite persistence layer for ResearchGraph runs and projects.

Replaces the in-memory dicts in ResearchGraphService so that runs and
projects survive server restarts.

Tables:
  projects  — serialised ResearchProject JSON blobs
  runs      — serialised RuntimeRun JSON blobs (checkpointed after each stage)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List, Optional


def _db_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "researchgraph.db"


class _Store:
    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or _db_path()
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS projects (
                        id TEXT PRIMARY KEY,
                        data TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS runs (
                        id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        data TEXT NOT NULL,
                        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS runs_project_idx ON runs(project_id)")
            conn.close()


class ProjectStore(_Store):
    def save(self, project_dict: dict) -> None:
        with self._lock:
            conn = self._connect()
            with conn:
                conn.execute(
                    """
                    INSERT INTO projects(id, data, updated_at)
                    VALUES(?, ?, datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at
                    """,
                    (project_dict["id"], json.dumps(project_dict)),
                )
            conn.close()

    def load(self, project_id: str) -> Optional[dict]:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT data FROM projects WHERE id=?", (project_id,)).fetchone()
            conn.close()
        return json.loads(row[0]) if row else None

    def load_all(self) -> List[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute("SELECT data FROM projects ORDER BY updated_at DESC").fetchall()
            conn.close()
        return [json.loads(r[0]) for r in rows]

    def exists(self, project_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone()
            conn.close()
        return row is not None


class RunStore(_Store):
    def save(self, run_dict: dict) -> None:
        with self._lock:
            conn = self._connect()
            with conn:
                conn.execute(
                    """
                    INSERT INTO runs(id, project_id, status, data, updated_at)
                    VALUES(?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(id) DO UPDATE SET
                        status=excluded.status,
                        data=excluded.data,
                        updated_at=excluded.updated_at
                    """,
                    (run_dict["id"], run_dict["project_id"], run_dict["status"], json.dumps(run_dict)),
                )
            conn.close()

    def load(self, run_id: str) -> Optional[dict]:
        with self._lock:
            conn = self._connect()
            row = conn.execute("SELECT data FROM runs WHERE id=?", (run_id,)).fetchone()
            conn.close()
        return json.loads(row[0]) if row else None

    def load_for_project(self, project_id: str) -> List[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                "SELECT data FROM runs WHERE project_id=? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
            conn.close()
        return [json.loads(r[0]) for r in rows]

    def load_all(self) -> List[dict]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute("SELECT data FROM runs ORDER BY updated_at DESC").fetchall()
            conn.close()
        return [json.loads(r[0]) for r in rows]
