from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .graphs import build_agentic_graph, build_paper_graph, build_unified_graph
from .models import NoveltyHypothesis, Paper, ResearchProject


@dataclass
class RankedPaper:
    id: str
    title: str
    score: float
    overlap: int
    connectivity: int
    citations: int
    year: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "score": self.score,
            "overlap": self.overlap,
            "connectivity": self.connectivity,
            "citations": self.citations,
            "year": self.year,
        }


class TurboQuant:
    """Graph-native scorer for papers. Uses semantic embeddings when available, keyword overlap otherwise."""

    def __init__(self, embedder=None) -> None:
        self._embedder = embedder  # Optional[EmbeddingClient]

    def rank_papers(self, project: ResearchProject, limit: int = 5) -> List[RankedPaper]:
        graph = build_paper_graph(project)
        connectivity = _node_degree(graph)

        # Try semantic scoring if embedder is available
        semantic_scores = self._semantic_scores(project) if self._embedder else {}

        scored: List[RankedPaper] = []
        for paper in project.papers:
            overlap = _request_overlap(project, paper)
            centrality = connectivity.get(paper.id, 0)
            citation_signal = min(paper.citations / 500.0, 5.0)
            recency_signal = max(0.0, (paper.year - 2018) * 0.2)
            semantic = semantic_scores.get(paper.id, 0.0)
            # Semantic similarity (0-1) scaled to 0-4 range, replaces overlap when available
            if semantic > 0:
                score = round((semantic * 4.0) + (centrality * 0.75) + citation_signal + recency_signal, 2)
            else:
                score = round((overlap * 1.8) + (centrality * 0.75) + citation_signal + recency_signal, 2)
            scored.append(
                RankedPaper(
                    id=paper.id,
                    title=paper.title,
                    score=score,
                    overlap=overlap,
                    connectivity=centrality,
                    citations=paper.citations,
                    year=paper.year,
                )
            )
        return sorted(scored, key=lambda item: item.score, reverse=True)[:limit]

    def _semantic_scores(self, project: ResearchProject) -> Dict[str, float]:
        """Embed query and all papers, return cosine similarity per paper id."""
        from .embeddings import cosine_similarity
        query_text = f"{project.domain} {project.problem} {project.abstract}"
        query_vec = self._embedder.embed(query_text)
        if query_vec is None:
            return {}
        scores: Dict[str, float] = {}
        for paper in project.papers:
            paper_text = f"{paper.title} {paper.abstract[:300]}"
            paper_vec = self._embedder.embed(paper_text)
            if paper_vec is not None:
                scores[paper.id] = round(cosine_similarity(query_vec, paper_vec), 4)
        return scores

    def graph_signal(self, project: ResearchProject) -> Dict[str, float]:
        graph = build_unified_graph(project)
        degree = _node_degree(graph)
        return {node_id: round(1.0 + degree_value * 0.35, 2) for node_id, degree_value in degree.items()}

    def rank_novelty(self, project: ResearchProject) -> List[NoveltyHypothesis]:
        graph = build_agentic_graph(project)
        degree = _node_degree(graph)
        updated: List[NoveltyHypothesis] = []
        for hypothesis in project.novelty_hypotheses:
            support = sum(degree.get(facet_id, 0) for facet_id in hypothesis.supporting_facets)
            differentiator_signal = len(hypothesis.differentiators) * 1.3
            score = round(3.5 + support * 0.4 + differentiator_signal, 2)
            updated.append(
                NoveltyHypothesis(
                    id=hypothesis.id,
                    title=hypothesis.title,
                    summary=hypothesis.summary,
                    differentiators=hypothesis.differentiators,
                    supporting_facets=hypothesis.supporting_facets,
                    score=score,
                )
            )
        return sorted(updated, key=lambda item: item.score, reverse=True)


def _request_overlap(project: ResearchProject, paper: Paper) -> int:
    request_terms = _keywords_from_text(f"{project.domain} {project.problem} {project.abstract}")
    paper_terms = set(_keywords_from_text(f"{paper.title} {paper.abstract} {' '.join(paper.keywords)}"))
    return len(request_terms.intersection(paper_terms))


def _keywords_from_text(text: str) -> set:
    stopwords = {
        "about",
        "across",
        "agent",
        "agents",
        "build",
        "end",
        "from",
        "into",
        "paper",
        "project",
        "queryable",
        "research",
        "suite",
        "system",
        "that",
        "this",
        "through",
        "with",
    }
    terms = set()
    for token in text.lower().replace("-", " ").split():
        normalized = "".join(character for character in token if character.isalpha())
        if len(normalized) >= 4 and normalized not in stopwords:
            terms.add(normalized)
    return terms


def _node_degree(graph) -> Dict[str, int]:
    degree: Dict[str, int] = {}
    for node in graph.nodes:
        degree[node.id] = 0
    for edge in graph.edges:
        degree[edge.source] = degree.get(edge.source, 0) + 1
        degree[edge.target] = degree.get(edge.target, 0) + 1
    return degree
