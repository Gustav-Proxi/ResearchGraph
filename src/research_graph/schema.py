from __future__ import annotations

from typing import List

import strawberry
from strawberry.types import Info
from strawberry.schema.config import StrawberryConfig

from .models import GraphData, ResearchProject
from .service import ResearchGraphService


@strawberry.type
class GraphNodeType:
    id: str
    label: str
    kind: str
    metadata: strawberry.scalars.JSON


@strawberry.type
class GraphEdgeType:
    source: str
    target: str
    kind: str
    weight: float
    metadata: strawberry.scalars.JSON


@strawberry.type
class GraphType:
    name: str
    kind: str
    nodes: List[GraphNodeType]
    edges: List[GraphEdgeType]


@strawberry.type
class RankedPaperType:
    id: str
    title: str
    score: float
    overlap: int
    connectivity: int
    citations: int
    year: int


@strawberry.type
class NoveltyHypothesisType:
    id: str
    title: str
    summary: str
    differentiators: List[str]
    supporting_facets: List[str]
    score: float


@strawberry.type
class RuntimeRunType:
    id: str
    project_id: str
    project_name: str
    status: str
    objective: str
    started_at: str
    finished_at: str
    trace_run_id: str
    summary: strawberry.scalars.JSON
    artifacts: strawberry.scalars.JSON
    timeline: strawberry.scalars.JSON
    messages: strawberry.scalars.JSON
    memory: strawberry.scalars.JSON
    learning_context: strawberry.scalars.JSON
    learning_state: strawberry.scalars.JSON
    reflection: strawberry.scalars.JSON


@strawberry.type
class ResearchProjectType:
    id: str
    name: str
    domain: str
    problem: str
    abstract: str

    @strawberry.field
    def top_papers(self, info: Info, limit: int = 5) -> List[RankedPaperType]:
        service: ResearchGraphService = info.context["service"]
        ranked = service.top_papers(self.id, limit=limit)
        return [RankedPaperType(**paper.to_dict()) for paper in ranked]

    @strawberry.field
    def graph_signal(self, info: Info) -> strawberry.scalars.JSON:
        service: ResearchGraphService = info.context["service"]
        return service.graph_signal(self.id)

    @strawberry.field
    def novelty_hypotheses(self, info: Info) -> List[NoveltyHypothesisType]:
        service: ResearchGraphService = info.context["service"]
        return [NoveltyHypothesisType(**item.to_dict()) for item in service.novelty_hypotheses(self.id)]


@strawberry.input
class ProjectBootstrapInput:
    name: str
    domain: str
    problem: str
    abstract: str = ""


@strawberry.type
class Query:
    @strawberry.field
    def projects(self, info: Info) -> List[ResearchProjectType]:
        service: ResearchGraphService = info.context["service"]
        return [_project_type(project) for project in service.list_projects()]

    @strawberry.field
    def demo_project(self, info: Info) -> ResearchProjectType:
        service: ResearchGraphService = info.context["service"]
        return _project_type(service.demo_project())

    @strawberry.field
    def project(self, info: Info, project_id: str) -> ResearchProjectType:
        service: ResearchGraphService = info.context["service"]
        return _project_type(service.get_project(project_id))

    @strawberry.field
    def runs(self, info: Info, project_id: str) -> List[RuntimeRunType]:
        service: ResearchGraphService = info.context["service"]
        return [_run_type(item) for item in service.list_runs(project_id=project_id)]

    @strawberry.field
    def run(self, info: Info, run_id: str) -> RuntimeRunType:
        service: ResearchGraphService = info.context["service"]
        return _run_type(service.get_run(run_id))

    @strawberry.field
    def paper_graph(self, info: Info, project_id: str) -> GraphType:
        service: ResearchGraphService = info.context["service"]
        return _graph_type(service.build_graph(project_id, "papers"))

    @strawberry.field
    def agent_graph(self, info: Info, project_id: str) -> GraphType:
        service: ResearchGraphService = info.context["service"]
        return _graph_type(service.build_graph(project_id, "agents"))

    @strawberry.field
    def experiment_graph(self, info: Info, project_id: str) -> GraphType:
        service: ResearchGraphService = info.context["service"]
        return _graph_type(service.build_graph(project_id, "experiments"))

    @strawberry.field
    def report_graph(self, info: Info, project_id: str) -> GraphType:
        service: ResearchGraphService = info.context["service"]
        return _graph_type(service.build_graph(project_id, "reports"))

    @strawberry.field
    def learning_graph(self, info: Info, project_id: str) -> GraphType:
        service: ResearchGraphService = info.context["service"]
        return _graph_type(service.build_graph(project_id, "learning"))

    @strawberry.field
    def technology_graph(self, info: Info, project_id: str) -> GraphType:
        service: ResearchGraphService = info.context["service"]
        return _graph_type(service.build_graph(project_id, "technology"))

    @strawberry.field
    def agentic_graph(self, info: Info, project_id: str) -> GraphType:
        service: ResearchGraphService = info.context["service"]
        return _graph_type(service.build_graph(project_id, "agentic"))

    @strawberry.field
    def unified_graph(self, info: Info, project_id: str) -> GraphType:
        service: ResearchGraphService = info.context["service"]
        return _graph_type(service.build_graph(project_id, "unified"))


@strawberry.type
class Mutation:
    @strawberry.mutation
    def bootstrap_project(self, info: Info, payload: ProjectBootstrapInput) -> ResearchProjectType:
        service: ResearchGraphService = info.context["service"]
        project = service.create_project(
            name=payload.name,
            domain=payload.domain,
            problem=payload.problem,
            abstract=payload.abstract,
        )
        return _project_type(project)

    @strawberry.mutation
    def execute_project(self, info: Info, project_id: str, objective: str = "") -> RuntimeRunType:
        service: ResearchGraphService = info.context["service"]
        return _run_type(service.run_project(project_id, objective=objective))


def create_schema(service: ResearchGraphService) -> strawberry.Schema:
    return strawberry.Schema(
        query=Query,
        mutation=Mutation,
        config=StrawberryConfig(auto_camel_case=True),
        extensions=[],
    )


def graphql_context(service: ResearchGraphService) -> dict:
    return {"service": service}


def _project_type(project: ResearchProject) -> ResearchProjectType:
    return ResearchProjectType(
        id=project.id,
        name=project.name,
        domain=project.domain,
        problem=project.problem,
        abstract=project.abstract,
    )


def _graph_type(graph: GraphData) -> GraphType:
    return GraphType(
        name=graph.name,
        kind=graph.kind,
        nodes=[
            GraphNodeType(
                id=node.id,
                label=node.label,
                kind=node.kind,
                metadata=node.metadata,
            )
            for node in graph.nodes
        ],
        edges=[
            GraphEdgeType(
                source=edge.source,
                target=edge.target,
                kind=edge.kind,
                weight=edge.weight,
                metadata=edge.metadata,
            )
            for edge in graph.edges
        ],
    )


def _run_type(run) -> RuntimeRunType:
    payload = run.to_dict()
    return RuntimeRunType(
        id=payload["id"],
        project_id=payload["project_id"],
        project_name=payload["project_name"],
        status=payload["status"],
        objective=payload["objective"],
        started_at=payload["started_at"],
        finished_at=payload["finished_at"],
        trace_run_id=payload["trace_run_id"],
        summary=payload["summary"],
        artifacts=payload["artifacts"],
        timeline=payload["timeline"],
        messages=payload["messages"],
        memory=payload["memory"],
        learning_context=payload["learning_context"],
        learning_state=payload["learning_state"],
        reflection=payload["reflection"],
    )
