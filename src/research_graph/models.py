from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass
class Paper:
    id: str
    title: str
    abstract: str
    authors: List[str]
    year: int
    venue: str
    citations: int
    keywords: List[str]
    references: List[str] = field(default_factory=list)
    url: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class AgentStage:
    id: str
    name: str
    role: str
    description: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class Artifact:
    id: str
    name: str
    artifact_type: str
    description: str
    produced_by: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class Technology:
    id: str
    name: str
    category: str
    role: str
    maturity: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ExperimentRun:
    id: str
    name: str
    objective: str
    status: str
    metrics: Dict[str, float] = field(default_factory=dict)
    based_on: List[str] = field(default_factory=list)
    generated_by: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ReportSection:
    id: str
    title: str
    purpose: str
    depends_on: List[str] = field(default_factory=list)
    generated_by: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class TaxonomyFacet:
    id: str
    name: str
    category: str
    description: str
    graph_role: str
    opportunities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class NoveltyHypothesis:
    id: str
    title: str
    summary: str
    differentiators: List[str]
    supporting_facets: List[str]
    score: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class ResearchProject:
    id: str
    name: str
    domain: str
    problem: str
    abstract: str
    papers: List[Paper] = field(default_factory=list)
    agents: List[AgentStage] = field(default_factory=list)
    artifacts: List[Artifact] = field(default_factory=list)
    technologies: List[Technology] = field(default_factory=list)
    experiments: List[ExperimentRun] = field(default_factory=list)
    report_sections: List[ReportSection] = field(default_factory=list)
    taxonomy: List[TaxonomyFacet] = field(default_factory=list)
    novelty_hypotheses: List[NoveltyHypothesis] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "problem": self.problem,
            "abstract": self.abstract,
            "papers": [paper.to_dict() for paper in self.papers],
            "agents": [agent.to_dict() for agent in self.agents],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "technologies": [technology.to_dict() for technology in self.technologies],
            "experiments": [experiment.to_dict() for experiment in self.experiments],
            "report_sections": [section.to_dict() for section in self.report_sections],
            "taxonomy": [facet.to_dict() for facet in self.taxonomy],
            "novelty_hypotheses": [hypothesis.to_dict() for hypothesis in self.novelty_hypotheses],
        }


@dataclass
class GraphNode:
    id: str
    label: str
    kind: str
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class GraphEdge:
    source: str
    target: str
    kind: str
    weight: float = 1.0
    metadata: Dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class GraphData:
    name: str
    kind: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }
