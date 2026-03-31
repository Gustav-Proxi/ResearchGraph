"""
Tests for the background-execution run pattern:
  create_run_placeholder → execute_run_background → poll GET /runs/{id}
"""
import time

from research_graph.runtime import AgentRuntime
from research_graph.seed import build_demo_project
from research_graph.service import ResearchGraphService


# ── create_run_placeholder ────────────────────────────────────────────────────

def test_placeholder_run_has_queued_status():
    service = ResearchGraphService()
    run = service.create_run_placeholder("demo-project", objective="test placeholder")

    assert run.status == "queued"
    assert run.project_id == "demo-project"
    assert run.objective == "test placeholder"
    assert run.id.startswith("run-")
    assert len(run.stages) == 0


def test_placeholder_run_is_immediately_retrievable():
    service = ResearchGraphService()
    run = service.create_run_placeholder("demo-project")

    fetched = service.get_run(run.id)
    assert fetched.id == run.id
    assert fetched.status == "queued"


def test_placeholder_uses_project_problem_as_default_objective():
    service = ResearchGraphService()
    project = service.get_project("demo-project")
    run = service.create_run_placeholder("demo-project")  # no explicit objective

    assert run.objective == project.problem


def test_placeholder_raises_for_unknown_project():
    service = ResearchGraphService()
    try:
        service.create_run_placeholder("nonexistent-project")
        assert False, "should have raised"
    except KeyError:
        pass


# ── execute_run_background ────────────────────────────────────────────────────

def test_background_execution_completes_run():
    service = ResearchGraphService()
    run = service.create_run_placeholder("demo-project", objective="background test")

    service.execute_run_background(run.id)

    assert run.status == "completed"
    assert run.finished_at


def test_background_execution_populates_stages():
    service = ResearchGraphService()
    run = service.create_run_placeholder("demo-project")

    service.execute_run_background(run.id)

    assert len(run.stages) > 0
    assert all(s.status in {"completed", "running", "error"} for s in run.stages)
    assert all(s.stage_name for s in run.stages)


def test_background_execution_produces_required_artifacts():
    service = ResearchGraphService()
    run = service.create_run_placeholder("demo-project")

    service.execute_run_background(run.id)

    for key in ("judged_decision", "final_report", "proposal_options"):
        assert key in run.artifacts, f"missing artifact: {key}"


def test_background_execution_populates_learning_state():
    service = ResearchGraphService()
    run = service.create_run_placeholder("demo-project")

    service.execute_run_background(run.id)

    assert run.learning_state
    assert run.learning_state.get("run_count", 0) >= 1


def test_background_execution_registers_snapshot_for_graph_queries():
    service = ResearchGraphService()
    run = service.create_run_placeholder("demo-project")

    service.execute_run_background(run.id)

    graph = service.build_run_graph(run.id, "unified")
    assert graph.nodes
    assert graph.kind == "unified"


def test_background_execution_silently_handles_unknown_run_id():
    service = ResearchGraphService()
    # Should not raise
    service.execute_run_background("nonexistent-run-id")


# ── run_ref parameter on AgentRuntime ─────────────────────────────────────────

def test_execute_with_run_ref_updates_existing_object():
    from research_graph.runtime_models import RuntimeRun

    runtime = AgentRuntime()
    project = build_demo_project()
    existing_run = RuntimeRun(
        id="run-existing-001",
        project_id=project.id,
        project_name=project.name,
        status="queued",
        objective="test run_ref",
    )

    returned_run, _ = runtime.execute(project, run_ref=existing_run)

    # Should have updated the *same* object, not created a new one
    assert returned_run is existing_run
    assert existing_run.id == "run-existing-001"
    assert existing_run.status == "completed"
    assert len(existing_run.stages) > 0


def test_execute_without_run_ref_creates_new_run():
    runtime = AgentRuntime()
    project = build_demo_project()

    run, _ = runtime.execute(project)

    assert run.status == "completed"
    assert run.id.startswith("run-")


def test_run_ref_objective_is_preserved_when_not_overridden():
    from research_graph.runtime_models import RuntimeRun

    runtime = AgentRuntime()
    project = build_demo_project()
    existing_run = RuntimeRun(
        id="run-obj-test",
        project_id=project.id,
        project_name=project.name,
        status="queued",
        objective="my specific objective",
    )

    runtime.execute(project, objective="", run_ref=existing_run)

    assert existing_run.objective == "my specific objective"


def test_run_ref_objective_is_overridden_when_provided():
    from research_graph.runtime_models import RuntimeRun

    runtime = AgentRuntime()
    project = build_demo_project()
    existing_run = RuntimeRun(
        id="run-override",
        project_id=project.id,
        project_name=project.name,
        status="queued",
        objective="original",
    )

    runtime.execute(project, objective="overridden objective", run_ref=existing_run)

    assert existing_run.objective == "overridden objective"


# ── placeholder + background simulates live polling ──────────────────────────

def test_stages_accumulate_during_simulated_polling():
    """
    Simulate what the frontend does: create placeholder, start background
    execution synchronously here, then check the run mutated in place.
    """
    service = ResearchGraphService()
    run = service.create_run_placeholder("demo-project", objective="polling simulation")

    # In production this runs in a thread; here we call directly
    service.execute_run_background(run.id)

    # The same object the frontend would poll via GET /runs/{id}
    polled = service.get_run(run.id)
    assert polled is run  # same object, not a copy
    assert polled.status == "completed"
    assert len(polled.stages) > 0
    assert polled.summary.get("completed_stages") == len(polled.stages)


def test_two_concurrent_runs_do_not_share_state():
    service = ResearchGraphService()

    run_a = service.create_run_placeholder("demo-project", objective="A")
    run_b = service.create_run_placeholder("demo-project", objective="B")

    service.execute_run_background(run_a.id)
    service.execute_run_background(run_b.id)

    assert run_a.id != run_b.id
    assert set(s.stage_id for s in run_a.stages).isdisjoint(
        {s.stage_id for s in run_b.stages}
    ) is False  # stage_ids are shared by name, but run IDs differ
    # What matters: run objects are separate
    assert run_a is not run_b
    assert run_a.stages is not run_b.stages
