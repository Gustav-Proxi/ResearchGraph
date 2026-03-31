from research_graph.runtime import AgentRuntime
from research_graph.seed import build_demo_project
from research_graph.service import ResearchGraphService


def test_agent_runtime_executes_all_stages_and_artifacts():
    runtime = AgentRuntime()
    project = build_demo_project()

    run, snapshot = runtime.execute(project)

    assert run.status == "completed"
    assert len(run.stages) == len(project.agents)
    assert "report_graph" in run.artifacts
    assert "experiment_results" in run.artifacts
    assert "judged_decision" in run.artifacts
    assert run.artifacts["judged_decision"]["status"] == "approved"
    assert any(stage.model_provider for stage in run.stages)
    assert all(stage.model_mode for stage in run.stages)
    assert run.messages
    assert run.memory
    assert all(experiment.status == "completed" for experiment in snapshot.experiments)
    assert run.summary["selected_decision"]


def test_service_persists_runs_and_run_graphs():
    service = ResearchGraphService()

    run = service.run_project("demo-project")
    graph = service.build_run_graph(run.id, "reports")

    assert service.get_run(run.id).id == run.id
    assert graph.kind == "reports"
    assert graph.nodes
    assert run.artifacts["final_report"]["decision_title"] == run.artifacts["judged_decision"]["decision_title"]


def test_each_run_gets_runtime_specific_graph_nodes():
    service = ResearchGraphService()

    run_a = service.run_project("demo-project", objective="A")
    run_b = service.run_project("demo-project", objective="B")
    graph_a = service.build_run_graph(run_a.id, "unified")
    graph_b = service.build_run_graph(run_b.id, "unified")

    ids_a = {node.id for node in graph_a.nodes if run_a.id in node.id}
    ids_b = {node.id for node in graph_b.nodes if run_b.id in node.id}

    assert ids_a
    assert ids_b
    assert ids_a.isdisjoint(ids_b)


def test_self_learning_persists_and_guides_later_runs():
    service = ResearchGraphService()

    first = service.run_project("demo-project", objective="first")
    second = service.run_project("demo-project", objective="second")
    learning = service.learning_state("demo-project")
    learning_graph = service.build_run_graph(second.id, "learning")

    assert first.learning_state["run_count"] >= 1
    assert second.learning_state["run_count"] >= 2
    assert learning["run_count"] >= 2
    assert any(stage.learning_applied for stage in second.stages)
    assert learning_graph.kind == "learning"
    assert any(node.kind == "learning_reflection" for node in learning_graph.nodes)


def test_writer_depends_on_judged_outputs():
    service = ResearchGraphService()
    run = service.run_project("demo-project", objective="judge-before-write")

    report = run.artifacts["final_report"]
    decision = run.artifacts["judged_decision"]

    assert report["status"] == "completed"
    assert report["decision_title"] == decision["decision_title"]
    assert "judge approval" in report["summary"].lower()
