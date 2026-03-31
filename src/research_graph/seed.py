from __future__ import annotations

from typing import List

from .models import (
    AgentStage,
    Artifact,
    ExperimentRun,
    NoveltyHypothesis,
    Paper,
    ResearchProject,
    ReportSection,
    TaxonomyFacet,
    Technology,
)


def build_demo_project() -> ResearchProject:
    papers = _demo_papers()
    agents = _default_agents()
    artifacts = _default_artifacts()
    technologies = _default_technologies()
    experiments = _default_experiments()
    report_sections = _default_report_sections()
    taxonomy = _agentic_taxonomy()
    novelty = _default_novelty_hypotheses()
    return ResearchProject(
        id="demo-project",
        name="ResearchGraph Demo",
        domain="autonomous research systems",
        problem="Build an end-to-end research suite that spans problem framing, literature analysis, implementation planning, experimentation, and report generation.",
        abstract="A graph-native research operating system where papers, agents, experiments, reports, and technologies are connected and queryable through GraphQL.",
        papers=papers,
        agents=agents,
        artifacts=artifacts,
        technologies=technologies,
        experiments=experiments,
        report_sections=report_sections,
        taxonomy=taxonomy,
        novelty_hypotheses=novelty,
    )


def build_project_from_prompt(project_id: str, name: str, domain: str, problem: str, abstract: str) -> ResearchProject:
    papers = _bootstrap_papers(domain, problem)
    return ResearchProject(
        id=project_id,
        name=name,
        domain=domain,
        problem=problem,
        abstract=abstract,
        papers=papers,
        agents=_default_agents(),
        artifacts=_default_artifacts(),
        technologies=_default_technologies(),
        experiments=_bootstrap_experiments(domain, papers),
        report_sections=_default_report_sections(),
        taxonomy=_agentic_taxonomy(),
        novelty_hypotheses=_bootstrap_novelty_hypotheses(domain),
    )


def _demo_papers() -> List[Paper]:
    return [
        Paper(
            id="paper-graphs-meet-agents",
            title="Graphs Meet AI Agents: Taxonomy, Progress, and Future Opportunities",
            abstract="A survey that organizes graph-empowered agents around planning, execution, memory, and multi-agent coordination, and highlights future directions including graph foundation models, privacy, multimodal agents, MCP, and open agent networks.",
            authors=["Yuanchen Bei", "Weizhi Zhang", "Siwen Wang", "Philip S. Yu"],
            year=2025,
            venue="arXiv",
            citations=40,
            keywords=["graphs", "agents", "planning", "execution", "memory", "coordination", "mcp"],
            references=["paper-rag", "paper-graphrag", "paper-self-refine"],
        ),
        Paper(
            id="paper-autonomous-agents-survey",
            title="Autonomous Agents Modelling Other Agents: A Comprehensive Survey and Open Problems",
            abstract="A survey of techniques for agents reasoning about other agents, including planning, beliefs, and open problems in multi-agent systems.",
            authors=["Frans Oliehoek", "Christopher Amato"],
            year=2017,
            venue="arXiv",
            citations=210,
            keywords=["autonomous agents", "survey", "reasoning", "multi-agent"],
            references=["paper-rag", "paper-self-refine", "paper-graphs-meet-agents"],
        ),
        Paper(
            id="paper-rag",
            title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            abstract="A retrieval-augmented architecture for improving factuality by conditioning generation on external knowledge sources.",
            authors=["Patrick Lewis", "Ethan Perez"],
            year=2020,
            venue="NeurIPS",
            citations=4200,
            keywords=["retrieval", "generation", "knowledge", "nlp"],
            references=[],
        ),
        Paper(
            id="paper-self-refine",
            title="Self-Refine: Iterative Refinement with Self-Feedback",
            abstract="A framework in which language models critique and improve their own responses in multiple refinement rounds.",
            authors=["Aman Madaan", "Shashank Tandon"],
            year=2023,
            venue="NeurIPS Workshop",
            citations=630,
            keywords=["self-refinement", "feedback", "llm agents", "iteration"],
            references=["paper-rag"],
        ),
        Paper(
            id="paper-llm-planning",
            title="Chasing Progress, Not Perfection: Revisiting Strategies for End-to-End LLM Plan Generation",
            abstract="An evaluation of planning-focused strategies for large language models, with an emphasis on end-to-end planning quality and task metrics.",
            authors=["Anonymous"],
            year=2024,
            venue="arXiv",
            citations=95,
            keywords=["planning", "llm", "evaluation", "end-to-end"],
            references=["paper-self-refine", "paper-graphs-meet-agents"],
        ),
        Paper(
            id="paper-graphrag",
            title="GraphRAG: Unlocking LLM Discovery on Narrative Private Data",
            abstract="A graph-driven retrieval method that uses structured entity and relation graphs to improve retrieval and synthesis quality.",
            authors=["Microsoft Research"],
            year=2024,
            venue="arXiv",
            citations=180,
            keywords=["graph", "retrieval", "knowledge graph", "llm"],
            references=["paper-rag"],
        ),
    ]


def _bootstrap_papers(domain: str, problem: str) -> List[Paper]:
    domain_terms = [term.strip() for term in (domain + " " + problem).lower().split() if len(term.strip()) >= 5]
    keywords = list(dict.fromkeys(domain_terms[:6])) or ["research", "agents", "graphs"]
    return [
        Paper(
            id="bootstrap-survey",
            title=f"{domain.title()} Survey Seed",
            abstract=f"Bootstrap survey seed for {problem}.",
            authors=["ResearchGraph"],
            year=2026,
            venue="Seeded",
            citations=0,
            keywords=keywords,
            references=[],
        ),
        Paper(
            id="bootstrap-graph",
            title=f"{domain.title()} Graph Methods Seed",
            abstract=f"Bootstrap graph methods seed for {problem}.",
            authors=["ResearchGraph"],
            year=2026,
            venue="Seeded",
            citations=0,
            keywords=keywords + ["graph", "connectivity"],
            references=["bootstrap-survey"],
        ),
    ]


def _bootstrap_experiments(domain: str, papers: List[Paper]) -> List[ExperimentRun]:
    paper_ids = [paper.id for paper in papers]
    title = domain.title()
    return [
        ExperimentRun(
            id="experiment-grounded-survey-loop",
            name=f"{title} Grounded Survey Loop",
            objective="Measure whether the suite can build a grounded survey and judged decision for the user query.",
            status="designed",
            metrics={"coverage": 0.68, "evidence_grounding": 0.74},
            based_on=paper_ids[:2],
            generated_by="agent-planner",
        ),
        ExperimentRun(
            id="experiment-decision-gate",
            name=f"{title} Decision Gate",
            objective="Test whether critique, grounding, and voting improve final plan quality before execution.",
            status="planned",
            metrics={"expected_decision_quality": 0.18, "expected_hallucination_reduction": 0.21},
            based_on=paper_ids[:2],
            generated_by="agent-judge",
        ),
        ExperimentRun(
            id="experiment-memory-reuse",
            name=f"{title} Memory Reuse",
            objective="Test whether self-learning from prior runs improves future planning and judged decision quality.",
            status="planned",
            metrics={"expected_retry_reduction": 0.16, "expected_planning_gain": 0.12},
            based_on=paper_ids[:2],
            generated_by="agent-memory",
        ),
    ]


def _bootstrap_novelty_hypotheses(domain: str) -> List[NoveltyHypothesis]:
    prefix = domain.title()
    return [
        NoveltyHypothesis(
            id="novelty-domain-router",
            title=f"{prefix} Topology Router",
            summary=f"A topology-adaptive router specialized for {domain} research workflows.",
            differentiators=["weighted voting", "grounding gate", "run-specific decision graph"],
            supporting_facets=["facet-planning", "facet-coordination"],
        ),
        NoveltyHypothesis(
            id="novelty-domain-memory",
            title=f"{prefix} Reflexive Memory",
            summary=f"A self-learning graph memory tuned for {domain} experiments and failure motifs.",
            differentiators=["cross-run reflection", "decision memory", "stage guidance"],
            supporting_facets=["facet-memory", "facet-coordination"],
        ),
        NoveltyHypothesis(
            id="novelty-domain-context",
            title=f"{prefix} Context Graph",
            summary=f"A context graph that binds evidence, tools, datasets, and judged decisions for {domain}.",
            differentiators=["protocol-aware retrieval", "decision-conditioned writing", "artifact lineage"],
            supporting_facets=["facet-execution", "facet-mcp"],
        ),
    ]


def _default_agents() -> List[AgentStage]:
    return [
        AgentStage(
            id="agent-intake",
            name="Intake Agent",
            role="problem-framing",
            description="Normalizes the domain, problem statement, abstract, constraints, and desired outputs.",
            outputs=["research_brief"],
        ),
        AgentStage(
            id="agent-evidence",
            name="Evidence Scout Agent",
            role="evidence-discovery",
            description="Searches scholarly sources, expands citations, and assembles the evidence graph.",
            inputs=["research_brief"],
            outputs=["paper_graph"],
            depends_on=["agent-intake"],
        ),
        AgentStage(
            id="agent-planning-graph",
            name="Planning Graph Agent",
            role="planning",
            description="Builds graph-of-tasks and graph-of-thought structures for decomposition, routing, and decision search.",
            inputs=["research_brief", "paper_graph"],
            outputs=["task_graph", "decision_graph"],
            depends_on=["agent-intake", "agent-evidence"],
        ),
        AgentStage(
            id="agent-survey",
            name="Survey Agent",
            role="literature-synthesis",
            description="Produces the survey, clusters papers, and extracts gaps plus adjacent methods.",
            inputs=["paper_graph"],
            outputs=["literature_survey", "gap_analysis"],
            depends_on=["agent-evidence", "agent-planning-graph"],
        ),
        AgentStage(
            id="agent-planner",
            name="Planner Agent",
            role="proposal-planning",
            description="Proposes multiple research directions and implementation options grounded in the survey.",
            inputs=["gap_analysis"],
            outputs=["proposal_options", "implementation_plan", "experiment_graph"],
            depends_on=["agent-survey", "agent-planning-graph"],
        ),
        AgentStage(
            id="agent-critic",
            name="Critic Agent",
            role="critique",
            description="Attacks proposed options, identifies weak assumptions, and records failure risks.",
            inputs=["proposal_options", "gap_analysis"],
            outputs=["critique_report"],
            depends_on=["agent-planner"],
        ),
        AgentStage(
            id="agent-grounding",
            name="Grounding Agent",
            role="evidence-grounding",
            description="Checks each proposed option against the evidence graph and assigns groundedness scores.",
            inputs=["proposal_options", "paper_graph"],
            outputs=["grounding_report"],
            depends_on=["agent-evidence", "agent-planner"],
        ),
        AgentStage(
            id="agent-coordinator",
            name="Coordination Router Agent",
            role="coordination-voting",
            description="Runs weighted scoring across options using critique, grounding, novelty, and execution cost.",
            inputs=["proposal_options", "critique_report", "grounding_report", "novelty_hypotheses"],
            outputs=["coordination_topology", "agent_routes", "vote_board"],
            depends_on=["agent-planner", "agent-critic", "agent-grounding", "agent-novelty"],
        ),
        AgentStage(
            id="agent-novelty",
            name="Novelty Critic Agent",
            role="novelty-discovery",
            description="Scores novelty against prior work and proposes differentiators grounded in the unified graph.",
            inputs=["paper_graph", "proposal_options"],
            outputs=["novelty_hypotheses"],
            depends_on=["agent-survey", "agent-planner"],
        ),
        AgentStage(
            id="agent-judge",
            name="Judge Agent",
            role="decision-judging",
            description="Finalizes the chosen direction after reviewing the vote board, critique, and evidence grounding.",
            inputs=["vote_board", "grounding_report", "critique_report"],
            outputs=["judged_decision", "decision_summary"],
            depends_on=["agent-coordinator", "agent-grounding", "agent-critic"],
        ),
        AgentStage(
            id="agent-executor",
            name="Experiment Operator Agent",
            role="experiment-execution",
            description="Implements experiments for the judged direction, runs evaluations, and collects results with traceability.",
            inputs=["judged_decision", "implementation_plan"],
            outputs=["experiment_results"],
            depends_on=["agent-judge"],
        ),
        AgentStage(
            id="agent-memory",
            name="Memory Steward Agent",
            role="memory",
            description="Maintains a temporal memory graph of papers, experiments, decisions, failures, and reusable insights.",
            inputs=["paper_graph", "experiment_results", "judged_decision"],
            outputs=["memory_graph", "evidence_context"],
            depends_on=["agent-evidence", "agent-executor", "agent-judge"],
        ),
        AgentStage(
            id="agent-writer",
            name="Writer Agent",
            role="report-generation",
            description="Writes the report and paper draft only from judged outputs, evidence, and experiment results.",
            inputs=["literature_survey", "judged_decision", "experiment_results", "memory_graph"],
            outputs=["report_graph", "paper_draft", "final_report"],
            depends_on=["agent-survey", "agent-judge", "agent-executor", "agent-memory"],
        ),
    ]


def _default_artifacts() -> List[Artifact]:
    return [
        Artifact(
            id="artifact-brief",
            name="Research Brief",
            artifact_type="brief",
            description="Normalized problem statement and success criteria.",
            produced_by="agent-intake",
        ),
        Artifact(
            id="artifact-survey",
            name="Literature Survey",
            artifact_type="survey",
            description="Survey of the evidence corpus with clustered themes and cited anchors.",
            produced_by="agent-survey",
        ),
        Artifact(
            id="artifact-plan",
            name="Implementation Plan",
            artifact_type="plan",
            description="Prioritized implementation roadmap with baselines and experiments.",
            produced_by="agent-planner",
        ),
        Artifact(
            id="artifact-options",
            name="Research Options",
            artifact_type="decision",
            description="Competing research directions proposed by the planner.",
            produced_by="agent-planner",
        ),
        Artifact(
            id="artifact-critique",
            name="Critique Board",
            artifact_type="decision",
            description="Risks and objections against each proposed option.",
            produced_by="agent-critic",
        ),
        Artifact(
            id="artifact-grounding",
            name="Grounding Ledger",
            artifact_type="evidence",
            description="Evidence-backed groundedness checks for each option.",
            produced_by="agent-grounding",
        ),
        Artifact(
            id="artifact-memory",
            name="Memory Graph",
            artifact_type="memory",
            description="Temporal graph of prior searches, experiment outcomes, and reusable research cues.",
            produced_by="agent-memory",
        ),
        Artifact(
            id="artifact-topology",
            name="Vote Board",
            artifact_type="coordination",
            description="Weighted decision board over proposed options, critiques, grounding, and novelty.",
            produced_by="agent-coordinator",
        ),
        Artifact(
            id="artifact-decision",
            name="Judged Decision",
            artifact_type="decision",
            description="Final direction chosen by the judge after weighted scoring and evidence review.",
            produced_by="agent-judge",
        ),
        Artifact(
            id="artifact-novelty",
            name="Novelty Brief",
            artifact_type="novelty",
            description="Ranked novelty opportunities and differentiators against connected prior work.",
            produced_by="agent-novelty",
        ),
        Artifact(
            id="artifact-report",
            name="Paper Draft",
            artifact_type="paper",
            description="Structured draft of the report or paper.",
            produced_by="agent-writer",
        ),
    ]


def _default_experiments() -> List[ExperimentRun]:
    return [
        ExperimentRun(
            id="experiment-baseline-survey-loop",
            name="Baseline Survey Loop",
            objective="Measure whether the suite can convert a problem statement into a grounded literature survey and plan.",
            status="designed",
            metrics={"coverage": 0.72, "evidence_grounding": 0.81},
            based_on=["paper-graphs-meet-agents", "paper-rag", "paper-self-refine"],
            generated_by="agent-planner",
        ),
        ExperimentRun(
            id="experiment-topology-router",
            name="Topology Router Ablation",
            objective="Compare fixed-chain orchestration against topology-adaptive coordination for research task completion.",
            status="planned",
            metrics={"expected_latency_reduction": 0.18, "expected_quality_gain": 0.11},
            based_on=["paper-graphs-meet-agents", "paper-autonomous-agents-survey"],
            generated_by="agent-coordinator",
        ),
        ExperimentRun(
            id="experiment-memory-reuse",
            name="Reflexive Memory Reuse",
            objective="Test whether graph memory of failures improves future planning and novelty scoring.",
            status="planned",
            metrics={"expected_retry_reduction": 0.22, "expected_novelty_precision": 0.15},
            based_on=["paper-self-refine", "paper-graphs-meet-agents"],
            generated_by="agent-memory",
        ),
    ]


def _default_report_sections() -> List[ReportSection]:
    return [
        ReportSection(
            id="report-problem",
            title="Problem Framing",
            purpose="Define the task, stakes, and research objective.",
            depends_on=["artifact-brief"],
            generated_by="agent-intake",
        ),
        ReportSection(
            id="report-related-work",
            title="Related Work",
            purpose="Position the work against prior literature and adjacent methods.",
            depends_on=["artifact-survey", "artifact-novelty"],
            generated_by="agent-survey",
        ),
        ReportSection(
            id="report-method",
            title="Method",
            purpose="Describe the graph-native research operating system and its agent topology.",
            depends_on=["artifact-plan", "artifact-topology", "artifact-memory"],
            generated_by="agent-planner",
        ),
        ReportSection(
            id="report-experiments",
            title="Experiments",
            purpose="Describe evaluation design, baselines, ablations, and metrics.",
            depends_on=["artifact-plan"],
            generated_by="agent-executor",
        ),
        ReportSection(
            id="report-results",
            title="Results And Analysis",
            purpose="Summarize experiment outcomes, failures, and implications.",
            depends_on=["artifact-memory", "artifact-report"],
            generated_by="agent-writer",
        ),
    ]


def _default_technologies() -> List[Technology]:
    return [
        Technology(
            id="tech-fastapi",
            name="FastAPI",
            category="api",
            role="REST service layer",
            maturity="stable",
        ),
        Technology(
            id="tech-graphql",
            name="GraphQL",
            category="query",
            role="Query surface for graphs, projects, and connected artifacts.",
            maturity="stable",
        ),
        Technology(
            id="tech-agentscope",
            name="AgentScope",
            category="observability",
            role="Execution tracing, replay, and debugging for research agents.",
            maturity="prototype",
        ),
        Technology(
            id="tech-vectorlens",
            name="VectorLens-style Attribution",
            category="grounding",
            role="Grounding diagnostics and evidence attribution across literature, notes, and tool outputs.",
            maturity="prototype",
        ),
        Technology(
            id="tech-turboquant",
            name="TurboQuant",
            category="scoring",
            role="Ranks papers, graph nodes, and hypotheses using graph and relevance signals.",
            maturity="new",
        ),
        Technology(
            id="tech-mcp",
            name="Model Context Protocol",
            category="protocol",
            role="Structured boundary for tool, memory, and data-source interaction.",
            maturity="emerging",
        ),
        Technology(
            id="tech-oan",
            name="Open Agent Network",
            category="network",
            role="Graph-native registry of specialist agents, tools, trust, and invocation paths.",
            maturity="speculative",
        ),
        Technology(
            id="tech-gfm",
            name="Graph Foundation Model",
            category="graph-model",
            role="Shared graph operator layer for planning, memory, and coordination reasoning.",
            maturity="emerging",
        ),
    ]


def _agentic_taxonomy() -> List[TaxonomyFacet]:
    return [
        TaxonomyFacet(
            id="facet-planning",
            name="Graphs for Agent Planning",
            category="core-agent-function",
            description="Use graphs to organize task reasoning, task decomposition, and decision search.",
            graph_role="task_graph",
            opportunities=[
                "graph-of-thought planning",
                "task decomposition DAGs",
                "decision-search over explicit state graphs",
            ],
        ),
        TaxonomyFacet(
            id="facet-execution",
            name="Graphs for Agent Execution",
            category="core-agent-function",
            description="Use graphs to structure tool usage and environment interaction instead of flat tool lists.",
            graph_role="tool_graph",
            opportunities=[
                "tool relationship graphs",
                "environment-state transition graphs",
                "routing over operator dependencies",
            ],
        ),
        TaxonomyFacet(
            id="facet-memory",
            name="Graphs for Agent Memory",
            category="core-agent-function",
            description="Use graph memory to organize episodic traces, grounded evidence, and long-horizon context.",
            graph_role="memory_graph",
            opportunities=[
                "knowledge graph memory",
                "temporal memory maintenance",
                "graph-based recall of prior experience",
            ],
        ),
        TaxonomyFacet(
            id="facet-coordination",
            name="Graphs for Multi-Agent Coordination",
            category="core-agent-function",
            description="Use graph topologies to design who communicates with whom, how often, and at what cost.",
            graph_role="coordination_graph",
            opportunities=[
                "adaptive communication topology",
                "sparse agent routing",
                "trust and dependency analysis",
            ],
        ),
        TaxonomyFacet(
            id="facet-mcp",
            name="Graphs for MCP Integration",
            category="future-opportunity",
            description="Use graphs to unify tools, data sources, and protocol endpoints into a structured agent context layer.",
            graph_role="protocol_graph",
            opportunities=[
                "tool recommendation",
                "unified context graphs",
                "protocol-aware context routing",
            ],
        ),
        TaxonomyFacet(
            id="facet-oan",
            name="Graphs for Open Agent Networks",
            category="future-opportunity",
            description="Model agents, tools, policies, trust, and invocation paths as a public but analyzable network.",
            graph_role="network_graph",
            opportunities=[
                "agent discovery",
                "cost-aware routing",
                "reputation and risk propagation",
            ],
        ),
    ]


def _default_novelty_hypotheses() -> List[NoveltyHypothesis]:
    return [
        NoveltyHypothesis(
            id="novelty-reflexive-memory",
            title="Reflexive Graph Memory",
            summary="A temporal memory graph that stores not only facts and papers, but also failed plans, weak evidence chains, and reusable coordination motifs.",
            differentiators=[
                "tracks failure edges, not only success edges",
                "retrieves prior experiments as graph neighborhoods instead of flat chunks",
                "feeds memory back into routing and novelty scoring",
            ],
            supporting_facets=["facet-memory", "facet-coordination"],
        ),
        NoveltyHypothesis(
            id="novelty-topology-router",
            title="Topology-Adaptive Agent Router",
            summary="A coordination layer that changes agent communication topology based on task shape, evidence confidence, and tool cost.",
            differentiators=[
                "agent topology is a first-class object",
                "coordination shifts from static chain to adaptive sparse graph",
                "routing is scored jointly by confidence, latency, and novelty gain",
            ],
            supporting_facets=["facet-coordination", "facet-execution", "facet-oan"],
        ),
        NoveltyHypothesis(
            id="novelty-mcp-graph",
            title="MCP-Native Context Graph",
            summary="An MCP-integrated graph that binds tools, datasets, memories, and papers into one protocol-queryable context plane.",
            differentiators=[
                "unifies literature, tools, and artifacts behind one graph boundary",
                "uses protocol edges to recommend the next best tool or source",
                "treats context delivery as graph routing rather than prompt stuffing",
            ],
            supporting_facets=["facet-mcp", "facet-execution", "facet-memory"],
        ),
    ]
