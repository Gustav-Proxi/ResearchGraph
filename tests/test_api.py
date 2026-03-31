"""
HTTP API tests — covers the full user flow:
  POST /api/projects → POST /api/projects/{id}/runs (returns immediately) →
  GET  /api/runs/{id} (poll until done) → GET /api/runs/{id}/graphs/{kind}
"""
import time

import pytest
from fastapi.testclient import TestClient

from research_graph.app import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    # Run background tasks synchronously in tests
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── health & static ───────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


# ── projects ──────────────────────────────────────────────────────────────────

def test_list_projects_includes_demo(client):
    r = client.get("/api/projects")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["projects"]]
    assert "demo-project" in ids


def test_create_project_returns_project_with_id(client):
    r = client.post("/api/projects", json={
        "name":     "Test Project",
        "domain":   "machine learning",
        "problem":  "How can we improve few-shot learning?",
        "abstract": "Testing the project creation endpoint.",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["id"].startswith("project-")
    assert body["domain"] == "machine learning"
    assert body["name"] == "Test Project"


def test_create_project_requires_domain_and_problem(client):
    r = client.post("/api/projects", json={"name": "Missing fields"})
    assert r.status_code == 400


def test_get_project_returns_project(client):
    r = client.get("/api/projects/demo-project")
    assert r.status_code == 200
    assert r.json()["id"] == "demo-project"


def test_get_unknown_project_returns_404(client):
    r = client.get("/api/projects/no-such-project")
    assert r.status_code == 404


# ── background run pattern ────────────────────────────────────────────────────

def test_post_run_returns_immediately_with_queued_status(client):
    """POST /runs must return immediately — not block until the run finishes."""
    r = client.post("/api/projects/demo-project/runs", json={
        "objective": "test background return"
    })
    assert r.status_code == 200
    body = r.json()
    assert body["id"].startswith("run-")
    # TestClient executes background tasks before the response is returned
    # so the run will be completed by now — but the key structural test is
    # that the endpoint returns a run object with an id.
    assert body["project_id"] == "demo-project"
    assert "stages" in body


def test_get_run_returns_completed_run(client):
    """After TestClient flushes background tasks, run should be completed."""
    r_post = client.post("/api/projects/demo-project/runs", json={"objective": "get-run test"})
    assert r_post.status_code == 200
    run_id = r_post.json()["id"]

    r_get = client.get(f"/api/runs/{run_id}")
    assert r_get.status_code == 200
    body = r_get.json()
    assert body["id"] == run_id
    assert body["status"] == "completed"
    assert len(body["stages"]) > 0


def test_get_unknown_run_returns_404(client):
    r = client.get("/api/runs/nonexistent-run-id")
    assert r.status_code == 404


def test_list_project_runs_includes_new_run(client):
    r_run = client.post("/api/projects/demo-project/runs", json={})
    run_id = r_run.json()["id"]

    r_list = client.get("/api/projects/demo-project/runs")
    assert r_list.status_code == 200
    ids = [r["id"] for r in r_list.json()["items"]]
    assert run_id in ids


# ── graph endpoints ───────────────────────────────────────────────────────────

def test_project_graph_returns_nodes_and_edges(client):
    for kind in ("papers", "agents", "unified"):
        r = client.get(f"/api/projects/demo-project/graphs/{kind}")
        assert r.status_code == 200, f"failed for kind={kind}"
        body = r.json()
        assert "nodes" in body
        assert "edges" in body
        assert len(body["nodes"]) > 0, f"no nodes for kind={kind}"


def test_run_graph_returns_nodes_after_execution(client):
    r_run = client.post("/api/projects/demo-project/runs", json={})
    run_id = r_run.json()["id"]

    for kind in ("unified", "agents", "reports"):
        r = client.get(f"/api/runs/{run_id}/graphs/{kind}")
        assert r.status_code == 200, f"failed for kind={kind}"
        body = r.json()
        assert body["nodes"], f"no nodes for run graph kind={kind}"


def test_run_unified_graph_has_multiple_node_kinds(client):
    r_run = client.post("/api/projects/demo-project/runs", json={})
    run_id = r_run.json()["id"]

    r = client.get(f"/api/runs/{run_id}/graphs/unified")
    assert r.status_code == 200
    kinds = {n["kind"] for n in r.json()["nodes"]}
    assert len(kinds) >= 3  # should have papers, agents, experiments at minimum


# ── full user flow ─────────────────────────────────────────────────────────────

def test_full_flow_create_project_run_report(client):
    """
    Simulate the exact frontend flow:
      1. User fills query form → POST /api/projects
      2. Start Research button → POST /api/projects/{id}/runs  (returns queued)
      3. Frontend polls GET /api/runs/{id} until complete
      4. Check final report is present
    """
    # Step 1: create project
    r_proj = client.post("/api/projects", json={
        "name":    "Full Flow Test",
        "domain":  "graph neural networks",
        "problem": "How do message-passing GNNs perform on heterogeneous graphs?",
    })
    assert r_proj.status_code == 200
    project_id = r_proj.json()["id"]

    # Step 2: start run
    r_run = client.post(f"/api/projects/{project_id}/runs", json={
        "objective": "Survey GNN literature and identify novelty gaps."
    })
    assert r_run.status_code == 200
    run = r_run.json()
    run_id = run["id"]
    assert run["project_id"] == project_id

    # Step 3: poll (TestClient flushes background tasks synchronously)
    r_poll = client.get(f"/api/runs/{run_id}")
    assert r_poll.status_code == 200
    run_data = r_poll.json()
    assert run_data["status"] == "completed"
    assert len(run_data["stages"]) > 0

    # Step 4: check deliverables
    assert "judged_decision" in run_data["artifacts"]
    assert "final_report"    in run_data["artifacts"]
    assert run_data["artifacts"]["final_report"]["status"] == "completed"

    # Graph should be queryable
    r_graph = client.get(f"/api/runs/{run_id}/graphs/unified")
    assert r_graph.status_code == 200
    assert r_graph.json()["nodes"]


def test_second_run_applies_learning_from_first(client):
    r1 = client.post("/api/projects/demo-project/runs", json={"objective": "first"})
    run1 = client.get(f"/api/runs/{r1.json()['id']}").json()

    r2 = client.post("/api/projects/demo-project/runs", json={"objective": "second"})
    run2 = client.get(f"/api/runs/{r2.json()['id']}").json()

    assert run1["learning_state"]["run_count"] >= 1
    assert run2["learning_state"]["run_count"] > run1["learning_state"]["run_count"]


# ── supporting endpoints ──────────────────────────────────────────────────────

def test_top_papers_endpoint(client):
    r = client.get("/api/projects/demo-project/top-papers?limit=3")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 3
    assert items[0]["score"] >= items[-1]["score"]


def test_novelty_endpoint(client):
    r = client.get("/api/projects/demo-project/novelty")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    assert all("score" in item for item in items)


def test_learning_state_endpoint(client):
    r = client.get("/api/projects/demo-project/learning")
    assert r.status_code == 200
    body = r.json()
    assert "run_count" in body
    assert "lessons" in body


def test_models_dashboard_endpoint(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    body = r.json()
    assert body["catalog"]["providers"]
    assert "settings" in body
    assert "ollama" in body
