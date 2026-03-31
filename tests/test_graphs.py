from research_graph.graphs import (
    build_agent_graph,
    build_agentic_graph,
    build_experiment_graph,
    build_learning_graph,
    build_paper_graph,
    build_report_graph,
    build_unified_graph,
)
from research_graph.seed import build_demo_project
from research_graph.turboquant import TurboQuant


def test_paper_graph_contains_reference_and_overlap_edges():
    project = build_demo_project()
    graph = build_paper_graph(project)

    edge_kinds = {edge.kind for edge in graph.edges}
    assert "references" in edge_kinds
    assert "keyword_overlap" in edge_kinds


def test_unified_graph_contains_multiple_node_kinds():
    project = build_demo_project()
    graph = build_unified_graph(project)

    node_kinds = {node.kind for node in graph.nodes}
    assert "paper" in node_kinds
    assert "agent" in node_kinds
    assert "artifact" in node_kinds
    assert "experiment" in node_kinds
    assert "report_section" in node_kinds
    assert "technology" in node_kinds


def test_agent_graph_links_artifacts_to_agents():
    project = build_demo_project()
    graph = build_agent_graph(project)

    assert any(edge.kind == "produces" for edge in graph.edges)


def test_agentic_graph_contains_taxonomy_and_novelty_nodes():
    project = build_demo_project()
    graph = build_agentic_graph(project)

    node_kinds = {node.kind for node in graph.nodes}
    assert "taxonomy_facet" in node_kinds
    assert "novelty" in node_kinds
    assert any(edge.kind == "empowers" for edge in graph.edges)


def test_experiment_and_report_graphs_exist_as_first_class_views():
    project = build_demo_project()
    experiment_graph = build_experiment_graph(project)
    report_graph = build_report_graph(project)

    assert all(node.kind == "experiment" for node in experiment_graph.nodes)
    assert any(edge.kind == "informs" for edge in experiment_graph.edges)
    assert all(node.kind == "report_section" for node in report_graph.nodes)
    assert any(edge.kind == "grounds" for edge in report_graph.edges)


def test_learning_graph_contains_lessons_and_model_profiles():
    project = build_demo_project()
    learning_state = {
        "run_count": 2,
        "lessons": [
            {
                "id": "lesson-a",
                "title": "Evidence before planning",
                "category": "research-flow",
                "content": "Survey first.",
                "strength": 1.7,
                "occurrences": 2,
                "stage_ids": ["agent-evidence", "agent-planner"],
            }
        ],
        "stage_guidance": [],
        "model_profiles": [
            {
                "provider": "ollama",
                "model": "llama3.2:1b",
                "total_calls": 2,
                "live_calls": 0,
                "fallback_calls": 2,
                "last_error": "offline",
                "reliability": 0.0,
            }
        ],
        "adaptation_history": [],
    }

    graph = build_learning_graph(project, learning_state)

    node_kinds = {node.kind for node in graph.nodes}
    assert "learning_lesson" in node_kinds
    assert "model_profile" in node_kinds
    assert any(edge.kind == "guides" for edge in graph.edges)


def test_turboquant_ranks_recent_connected_papers():
    project = build_demo_project()
    engine = TurboQuant()
    ranked = engine.rank_papers(project, limit=3)

    assert len(ranked) == 3
    assert ranked[0].score >= ranked[-1].score


def test_turboquant_ranks_novelty_hypotheses():
    project = build_demo_project()
    engine = TurboQuant()
    ranked = engine.rank_novelty(project)

    assert ranked
    assert ranked[0].score >= ranked[-1].score
