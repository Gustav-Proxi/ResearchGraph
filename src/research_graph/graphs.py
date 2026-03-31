from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Set

from .models import GraphData, GraphEdge, GraphNode, ResearchProject
from .runtime_models import RuntimeRun


def build_paper_graph(project: ResearchProject) -> GraphData:
    nodes = [
        GraphNode(
            id=paper.id,
            label=paper.title,
            kind="paper",
            metadata={
                "year": paper.year,
                "venue": paper.venue,
                "citations": paper.citations,
                "keywords": paper.keywords,
            },
        )
        for paper in project.papers
    ]
    edges: List[GraphEdge] = []
    papers_by_id = {paper.id: paper for paper in project.papers}
    for paper in project.papers:
        for ref_id in paper.references:
            if ref_id in papers_by_id:
                edges.append(
                    GraphEdge(
                        source=paper.id,
                        target=ref_id,
                        kind="references",
                        weight=1.0,
                    )
                )
        for other in project.papers:
            if other.id <= paper.id:
                continue
            overlap = sorted(set(paper.keywords).intersection(other.keywords))
            if overlap:
                weight = round(0.35 + 0.15 * len(overlap), 2)
                edges.append(
                    GraphEdge(
                        source=paper.id,
                        target=other.id,
                        kind="keyword_overlap",
                        weight=weight,
                        metadata={"shared_keywords": overlap},
                    )
                )
    return GraphData(name=project.name, kind="papers", nodes=nodes, edges=edges)


def build_agent_graph(project: ResearchProject) -> GraphData:
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []

    for agent in project.agents:
        nodes.append(
            GraphNode(
                id=agent.id,
                label=agent.name,
                kind="agent",
                metadata={
                    "role": agent.role,
                    "inputs": agent.inputs,
                    "outputs": agent.outputs,
                },
            )
        )
        for dependency in agent.depends_on:
            edges.append(
                GraphEdge(
                    source=dependency,
                    target=agent.id,
                    kind="depends_on",
                    weight=1.0,
                )
            )

    for artifact in project.artifacts:
        nodes.append(
            GraphNode(
                id=artifact.id,
                label=artifact.name,
                kind="artifact",
                metadata={
                    "artifact_type": artifact.artifact_type,
                    "description": artifact.description,
                },
            )
        )
        edges.append(
            GraphEdge(
                source=artifact.produced_by,
                target=artifact.id,
                kind="produces",
                weight=1.0,
            )
        )

    return GraphData(name=project.name, kind="agents", nodes=nodes, edges=edges)


def build_experiment_graph(project: ResearchProject) -> GraphData:
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []

    for experiment in project.experiments:
        nodes.append(
            GraphNode(
                id=experiment.id,
                label=experiment.name,
                kind="experiment",
                metadata={
                    "objective": experiment.objective,
                    "status": experiment.status,
                    "metrics": experiment.metrics,
                },
            )
        )
        if experiment.generated_by:
            edges.append(
                GraphEdge(
                    source=experiment.generated_by,
                    target=experiment.id,
                    kind="designs",
                    weight=1.0,
                )
            )
        for paper_id in experiment.based_on:
            edges.append(
                GraphEdge(
                    source=paper_id,
                    target=experiment.id,
                    kind="informs",
                    weight=0.8,
                )
            )

    for artifact in project.artifacts:
        if artifact.artifact_type == "plan":
            edges.extend(
                GraphEdge(
                    source=artifact.id,
                    target=experiment.id,
                    kind="specifies",
                    weight=0.75,
                )
                for experiment in project.experiments
            )

    return GraphData(name=project.name, kind="experiments", nodes=nodes, edges=edges)


def build_report_graph(project: ResearchProject) -> GraphData:
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []

    for section in project.report_sections:
        nodes.append(
            GraphNode(
                id=section.id,
                label=section.title,
                kind="report_section",
                metadata={"purpose": section.purpose},
            )
        )
        if section.generated_by:
            edges.append(
                GraphEdge(
                    source=section.generated_by,
                    target=section.id,
                    kind="drafts",
                    weight=1.0,
                )
            )
        for dependency in section.depends_on:
            edges.append(
                GraphEdge(
                    source=dependency,
                    target=section.id,
                    kind="grounds",
                    weight=0.8,
                )
            )

    return GraphData(name=project.name, kind="reports", nodes=nodes, edges=edges)


def build_learning_graph(project: ResearchProject, learning_state: Dict[str, object]) -> GraphData:
    nodes: List[GraphNode] = [
        GraphNode(
            id=project.id,
            label=project.name,
            kind="project",
            metadata={"domain": project.domain, "run_count": learning_state.get("run_count", 0)},
        )
    ]
    edges: List[GraphEdge] = []

    for lesson in learning_state.get("lessons", []):
        lesson_node_id = f"{project.id}::lesson::{lesson['id']}"
        nodes.append(
            GraphNode(
                id=lesson_node_id,
                label=lesson["title"],
                kind="learning_lesson",
                metadata={
                    "category": lesson["category"],
                    "content": lesson["content"],
                    "strength": lesson["strength"],
                    "occurrences": lesson["occurrences"],
                },
            )
        )
        edges.append(GraphEdge(source=project.id, target=lesson_node_id, kind="learned_policy", weight=lesson["strength"]))
        for stage_id in lesson.get("stage_ids", []):
            agent = _agent_by_id(project, stage_id)
            if not agent:
                continue
            nodes.append(
                GraphNode(
                    id=agent.id,
                    label=agent.name,
                    kind="agent",
                    metadata={"role": agent.role},
                )
            )
            edges.append(
                GraphEdge(
                    source=lesson_node_id,
                    target=agent.id,
                    kind="guides",
                    weight=0.8,
                )
            )

    for profile in learning_state.get("model_profiles", []):
        profile_id = f"{project.id}::model-profile::{profile['provider']}::{profile['model']}"
        nodes.append(
            GraphNode(
                id=profile_id,
                label=f"{profile['provider']}:{profile['model']}",
                kind="model_profile",
                metadata=profile,
            )
        )
        edges.append(
            GraphEdge(
                source=project.id,
                target=profile_id,
                kind="observed_model",
                weight=max(0.2, profile.get("reliability", 0.0)),
            )
        )

    for reflection in learning_state.get("adaptation_history", [])[:5]:
        reflection_id = f"{project.id}::reflection::{reflection['run_id']}"
        nodes.append(
            GraphNode(
                id=reflection_id,
                label=reflection["run_id"],
                kind="learning_reflection",
                metadata=reflection,
            )
        )
        edges.append(
            GraphEdge(
                source=project.id,
                target=reflection_id,
                kind="reflects_on",
                weight=0.7,
            )
        )

    return _dedupe_graph(GraphData(name=project.name, kind="learning", nodes=nodes, edges=edges))


def build_technology_graph(project: ResearchProject) -> GraphData:
    nodes = [
        GraphNode(
            id=technology.id,
            label=technology.name,
            kind="technology",
            metadata={
                "category": technology.category,
                "role": technology.role,
                "maturity": technology.maturity,
            },
        )
        for technology in project.technologies
    ]
    edges: List[GraphEdge] = []
    grouped = _group_technology_ids(project)
    for tech_ids in grouped.values():
        for source_id, target_id in _pairs(tech_ids):
            edges.append(
                GraphEdge(
                    source=source_id,
                    target=target_id,
                    kind="same_category",
                    weight=0.6,
                )
            )
    for agent in project.agents:
        if "evidence" in agent.role or "survey" in agent.role:
            edges.append(
                GraphEdge(
                    source="tech-vectorlens",
                    target=agent.id,
                    kind="supports",
                    weight=0.8,
                )
            )
        if "execution" in agent.role or "experiment" in agent.role:
            edges.append(
                GraphEdge(
                    source="tech-agentscope",
                    target=agent.id,
                    kind="observes",
                    weight=0.8,
                )
            )
        if "planning" in agent.role or "synthesis" in agent.role or "novelty" in agent.role:
            edges.append(
                GraphEdge(
                    source="tech-turboquant",
                    target=agent.id,
                    kind="scores",
                    weight=0.75,
                )
            )
        if "report" in agent.role:
            edges.append(
                GraphEdge(
                    source="tech-graphql",
                    target=agent.id,
                    kind="queries",
                    weight=0.5,
                )
            )
    for agent in project.agents:
        nodes.append(
            GraphNode(
                id=agent.id,
                label=agent.name,
                kind="agent",
                metadata={"role": agent.role},
            )
        )
    return GraphData(name=project.name, kind="technology", nodes=nodes, edges=edges)


def build_agentic_graph(project: ResearchProject) -> GraphData:
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []

    for facet in project.taxonomy:
        nodes.append(
            GraphNode(
                id=facet.id,
                label=facet.name,
                kind="taxonomy_facet",
                metadata={
                    "category": facet.category,
                    "description": facet.description,
                    "graph_role": facet.graph_role,
                    "opportunities": facet.opportunities,
                },
            )
        )

    for agent in project.agents:
        nodes.append(
            GraphNode(
                id=agent.id,
                label=agent.name,
                kind="agent",
                metadata={"role": agent.role, "outputs": agent.outputs},
            )
        )
        for facet_id in _facet_links_for_agent(agent.role):
            edges.append(
                GraphEdge(
                    source=facet_id,
                    target=agent.id,
                    kind="empowers",
                    weight=0.9,
                )
            )

    for technology in project.technologies:
        if technology.category in {"protocol", "network", "graph-model", "scoring"}:
            nodes.append(
                GraphNode(
                    id=technology.id,
                    label=technology.name,
                    kind="technology",
                    metadata={"role": technology.role, "category": technology.category},
                )
            )
            for facet_id in _facet_links_for_technology(technology.id):
                edges.append(
                    GraphEdge(
                        source=technology.id,
                        target=facet_id,
                        kind="supports",
                        weight=0.8,
                    )
                )

    for hypothesis in project.novelty_hypotheses:
        nodes.append(
            GraphNode(
                id=hypothesis.id,
                label=hypothesis.title,
                kind="novelty",
                metadata={
                    "summary": hypothesis.summary,
                    "differentiators": hypothesis.differentiators,
                    "score": hypothesis.score,
                },
            )
        )
        for facet_id in hypothesis.supporting_facets:
            edges.append(
                GraphEdge(
                    source=facet_id,
                    target=hypothesis.id,
                    kind="inspires",
                    weight=0.85,
                )
            )

    return GraphData(name=project.name, kind="agentic", nodes=nodes, edges=edges)


def build_unified_graph(project: ResearchProject) -> GraphData:
    graph_parts = [
        build_paper_graph(project),
        build_agent_graph(project),
        build_experiment_graph(project),
        build_report_graph(project),
        build_technology_graph(project),
        build_agentic_graph(project),
    ]
    nodes_by_id: Dict[str, GraphNode] = {}
    edges: List[GraphEdge] = []

    for graph in graph_parts:
        for node in graph.nodes:
            nodes_by_id[node.id] = node
        edges.extend(graph.edges)

    for artifact in project.artifacts:
        relevant_papers = _papers_for_artifact(project, artifact.id)
        for paper_id in relevant_papers:
            edges.append(
                GraphEdge(
                    source=paper_id,
                    target=artifact.id,
                    kind="informs",
                    weight=0.7,
                )
            )

    return GraphData(
        name=project.name,
        kind="unified",
        nodes=list(nodes_by_id.values()),
        edges=edges,
    )


def build_runtime_agent_graph(project: ResearchProject, run: RuntimeRun) -> GraphData:
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []

    for stage in run.stages:
        stage_node_id = _run_stage_node_id(run.id, stage.stage_id)
        nodes.append(
            GraphNode(
                id=stage_node_id,
                label=stage.stage_name,
                kind="run_stage",
                metadata={
                    "role": stage.role,
                    "status": stage.status,
                    "model_provider": stage.model_provider,
                    "model_name": stage.model_name,
                    "model_mode": stage.model_mode,
                    "model_error": stage.model_error,
                },
            )
        )
        edges.append(
            GraphEdge(
                source=run.id,
                target=stage_node_id,
                kind="contains_stage",
                weight=1.0,
            )
        )
        for artifact_name in stage.artifacts_created:
            artifact_node_id = _artifact_node_id(run.id, artifact_name)
            nodes.append(
                GraphNode(
                    id=artifact_node_id,
                    label=artifact_name,
                    kind="run_artifact",
                    metadata={"artifact_name": artifact_name},
                )
            )
            edges.append(
                GraphEdge(
                    source=stage_node_id,
                    target=artifact_node_id,
                    kind="produced_runtime_artifact",
                    weight=0.9,
                )
            )
        if stage.model_provider or stage.model_name:
            model_node_id = _model_node_id(stage.model_provider or "heuristic", stage.model_name or "local-fallback")
            nodes.append(
                GraphNode(
                    id=model_node_id,
                    label=f"{stage.model_provider or 'heuristic'}:{stage.model_name or 'local-fallback'}",
                    kind="model",
                    metadata={"mode": stage.model_mode, "error": stage.model_error},
                )
            )
            edges.append(
                GraphEdge(
                    source=stage_node_id,
                    target=model_node_id,
                    kind="used_model",
                    weight=0.75,
                )
            )

    for stage in run.stages[:-1]:
        current = _run_stage_node_id(run.id, stage.stage_id)
        next_stage = run.stages[run.stages.index(stage) + 1]
        edges.append(
            GraphEdge(
                source=current,
                target=_run_stage_node_id(run.id, next_stage.stage_id),
                kind="runtime_next",
                weight=0.7,
            )
        )

    for message in run.messages:
        source = _run_stage_node_id(run.id, message.source)
        target = _run_stage_node_id(run.id, message.target)
        edges.append(
            GraphEdge(
                source=source,
                target=target,
                kind=f"message_{message.category}",
                weight=message.priority,
                metadata={"content": message.content},
            )
        )

    nodes.append(
        GraphNode(
            id=run.id,
            label=run.project_name,
            kind="runtime_run",
            metadata={"status": run.status, "objective": run.objective},
        )
    )
    return _dedupe_graph(GraphData(name=project.name, kind="agents", nodes=nodes, edges=edges))


def build_runtime_experiment_graph(project: ResearchProject, run: RuntimeRun) -> GraphData:
    base = build_experiment_graph(project)
    nodes = list(base.nodes)
    edges = list(base.edges)
    for experiment in project.experiments:
        result_node_id = f"{run.id}::result::{experiment.id}"
        nodes.append(
            GraphNode(
                id=result_node_id,
                label=f"{experiment.name} result",
                kind="experiment_result",
                metadata={"status": experiment.status, "metrics": experiment.metrics},
            )
        )
        edges.append(
            GraphEdge(
                source=experiment.id,
                target=result_node_id,
                kind="result_of",
                weight=0.9,
            )
        )
        edges.append(
            GraphEdge(
                source=run.id,
                target=result_node_id,
                kind="captured_in_run",
                weight=0.75,
            )
        )
    nodes.append(GraphNode(id=run.id, label=run.project_name, kind="runtime_run", metadata=run.summary))
    return _dedupe_graph(GraphData(name=project.name, kind="experiments", nodes=nodes, edges=edges))


def build_runtime_report_graph(project: ResearchProject, run: RuntimeRun) -> GraphData:
    base = build_report_graph(project)
    nodes = list(base.nodes)
    edges = list(base.edges)
    final_report = run.artifacts.get("final_report", {})
    paper_draft = run.artifacts.get("paper_draft", {})
    final_node_id = f"{run.id}::final_report"
    nodes.append(
        GraphNode(
            id=final_node_id,
            label="Final Report",
            kind="final_report",
            metadata=final_report if isinstance(final_report, dict) else {"value": final_report},
        )
    )
    edges.append(
        GraphEdge(
            source=run.id,
            target=final_node_id,
            kind="produced_report",
            weight=1.0,
        )
    )
    if isinstance(paper_draft, dict):
        for section_id, text in paper_draft.items():
            section_node_id = f"{run.id}::draft::{section_id}"
            nodes.append(
                GraphNode(
                    id=section_node_id,
                    label=section_id.replace("report-", "").replace("-", " ").title(),
                    kind="draft_section",
                    metadata={"text": text},
                )
            )
            edges.append(
                GraphEdge(
                    source=section_id,
                    target=section_node_id,
                    kind="drafted_as",
                    weight=0.85,
                )
            )
            edges.append(
                GraphEdge(
                    source=section_node_id,
                    target=final_node_id,
                    kind="assembled_into",
                    weight=0.8,
                )
            )
    nodes.append(GraphNode(id=run.id, label=run.project_name, kind="runtime_run", metadata=run.summary))
    return _dedupe_graph(GraphData(name=project.name, kind="reports", nodes=nodes, edges=edges))


def build_runtime_learning_graph(project: ResearchProject, run: RuntimeRun) -> GraphData:
    nodes: List[GraphNode] = [
        GraphNode(
            id=run.id,
            label=run.project_name,
            kind="runtime_run",
            metadata={"objective": run.objective, **run.summary},
        )
    ]
    edges: List[GraphEdge] = []

    for stage in run.stages:
        stage_node_id = _run_stage_node_id(run.id, stage.stage_id)
        nodes.append(
            GraphNode(
                id=stage_node_id,
                label=stage.stage_name,
                kind="run_stage",
                metadata={
                    "role": stage.role,
                    "status": stage.status,
                    "learning_applied": stage.learning_applied,
                },
            )
        )
        edges.append(
            GraphEdge(
                source=run.id,
                target=stage_node_id,
                kind="executed_stage",
                weight=1.0,
            )
        )
        for lesson_title in stage.learning_applied:
            lesson_id = f"{run.id}::applied-lesson::{stage.stage_id}::{_slug(lesson_title)}"
            nodes.append(
                GraphNode(
                    id=lesson_id,
                    label=lesson_title,
                    kind="applied_lesson",
                    metadata={"stage_id": stage.stage_id},
                )
            )
            edges.append(
                GraphEdge(
                    source=lesson_id,
                    target=stage_node_id,
                    kind="shaped_stage",
                    weight=0.8,
                )
            )

    for item in run.learning_state.get("model_profiles", [])[:6]:
        profile_id = f"{run.id}::model::{item['provider']}::{item['model']}"
        nodes.append(
            GraphNode(
                id=profile_id,
                label=f"{item['provider']}:{item['model']}",
                kind="model_profile",
                metadata=item,
            )
        )
        edges.append(
            GraphEdge(
                source=run.id,
                target=profile_id,
                kind="consulted_model_profile",
                weight=max(0.2, item.get("reliability", 0.0)),
            )
        )

    if run.reflection:
        reflection_id = f"{run.id}::reflection"
        nodes.append(
            GraphNode(
                id=reflection_id,
                label="Run Reflection",
                kind="learning_reflection",
                metadata=run.reflection,
            )
        )
        edges.append(GraphEdge(source=run.id, target=reflection_id, kind="self_reflects", weight=1.0))

    return _dedupe_graph(GraphData(name=project.name, kind="learning", nodes=nodes, edges=edges))


def build_runtime_unified_graph(project: ResearchProject, run: RuntimeRun) -> GraphData:
    base = build_unified_graph(project)
    runtime_agents = build_runtime_agent_graph(project, run)
    runtime_experiments = build_runtime_experiment_graph(project, run)
    runtime_reports = build_runtime_report_graph(project, run)
    runtime_learning = build_runtime_learning_graph(project, run)
    nodes = list(base.nodes) + list(runtime_agents.nodes) + list(runtime_experiments.nodes) + list(runtime_reports.nodes) + list(runtime_learning.nodes)
    edges = list(base.edges) + list(runtime_agents.edges) + list(runtime_experiments.edges) + list(runtime_reports.edges) + list(runtime_learning.edges)

    for entry in run.memory:
        memory_node_id = f"{run.id}::memory::{entry.id}"
        nodes.append(
            GraphNode(
                id=memory_node_id,
                label=entry.title,
                kind="memory_entry",
                metadata={"kind": entry.kind, "content": entry.content},
            )
        )
        edges.append(
            GraphEdge(
                source=run.id,
                target=memory_node_id,
                kind="stores_memory",
                weight=0.8,
            )
        )
        for linked_id in entry.linked_ids:
            edges.append(
                GraphEdge(
                    source=memory_node_id,
                    target=linked_id,
                    kind="recalls",
                    weight=0.65,
                )
            )

    summary_node_id = f"{run.id}::summary"
    nodes.append(
        GraphNode(
            id=summary_node_id,
            label="Run Summary",
            kind="run_summary",
            metadata=run.summary,
        )
    )
    edges.append(
        GraphEdge(
            source=run.id,
            target=summary_node_id,
            kind="summarizes",
            weight=1.0,
        )
    )
    return _dedupe_graph(GraphData(name=project.name, kind="unified", nodes=nodes, edges=edges))


def _group_technology_ids(project: ResearchProject) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    for technology in project.technologies:
        grouped[technology.category].append(technology.id)
    return grouped


def _pairs(items: Iterable[str]) -> List[tuple]:
    materialized = list(items)
    pairs: List[tuple] = []
    for index, source in enumerate(materialized):
        for target in materialized[index + 1 :]:
            pairs.append((source, target))
    return pairs


def _papers_for_artifact(project: ResearchProject, artifact_id: str) -> Set[str]:
    if artifact_id == "artifact-survey":
        return {paper.id for paper in project.papers}
    if artifact_id == "artifact-plan":
        return {paper.id for paper in project.papers if "planning" in " ".join(paper.keywords)}
    if artifact_id == "artifact-memory":
        return {paper.id for paper in project.papers if "memory" in " ".join(paper.keywords)}
    if artifact_id == "artifact-report":
        return {paper.id for paper in project.papers if paper.year >= 2023}
    if artifact_id == "artifact-novelty":
        return {
            paper.id
            for paper in project.papers
            if "graph" in " ".join(paper.keywords) or "agents" in " ".join(paper.keywords)
        }
    return set()


def _facet_links_for_agent(role: str) -> List[str]:
    normalized = role.lower()
    links: List[str] = []
    if "planning" in normalized or "problem-framing" in normalized:
        links.append("facet-planning")
    if "execution" in normalized or "evidence" in normalized or "survey" in normalized:
        links.append("facet-execution")
    if "memory" in normalized or "survey" in normalized:
        links.append("facet-memory")
    if "coordination" in normalized or "novelty" in normalized:
        links.append("facet-coordination")
    if "report" in normalized:
        links.extend(["facet-mcp", "facet-oan"])
    return links


def _facet_links_for_technology(technology_id: str) -> List[str]:
    if technology_id == "tech-mcp":
        return ["facet-mcp", "facet-execution", "facet-memory"]
    if technology_id == "tech-oan":
        return ["facet-oan", "facet-coordination"]
    if technology_id == "tech-gfm":
        return ["facet-planning", "facet-memory", "facet-coordination"]
    if technology_id == "tech-turboquant":
        return ["facet-planning", "facet-coordination"]
    return []


def _dedupe_graph(graph: GraphData) -> GraphData:
    nodes_by_id: Dict[str, GraphNode] = {}
    for node in graph.nodes:
        nodes_by_id[node.id] = node
    seen_edges = set()
    deduped_edges: List[GraphEdge] = []
    for edge in graph.edges:
        key = (edge.source, edge.target, edge.kind)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        deduped_edges.append(edge)
    return GraphData(name=graph.name, kind=graph.kind, nodes=list(nodes_by_id.values()), edges=deduped_edges)


def _run_stage_node_id(run_id: str, stage_id: str) -> str:
    return f"{run_id}::stage::{stage_id}"


def _artifact_node_id(run_id: str, artifact_name: str) -> str:
    return f"{run_id}::artifact::{artifact_name}"


def _model_node_id(provider: str, model_name: str) -> str:
    return f"model::{provider}::{model_name}"


def _agent_by_id(project: ResearchProject, agent_id: str):
    for agent in project.agents:
        if agent.id == agent_id:
            return agent
    return None


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
