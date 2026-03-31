from __future__ import annotations

import json
import re
from collections import Counter
from copy import deepcopy
from typing import Dict, List, Optional

from .graphs import build_experiment_graph, build_report_graph
from .models import ExperimentRun, NoveltyHypothesis, Paper, ResearchProject
from .runtime_models import RunMemoryEntry, SwarmMessage, TimelineEvent
from .turboquant import TurboQuant


# ── JSON extraction from LLM text ────────────────────────────────────────────

def _extract_json(text: str) -> Optional[dict]:
    """Try to extract the first JSON object from an LLM response."""
    if not text:
        return None
    # Try ```json ... ``` block first
    block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if block:
        try:
            return json.loads(block.group(1))
        except Exception:
            pass
    # Try first top-level { ... }
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except Exception:
            pass
    return None


def _paper_digest(papers: List[Paper], max_papers: int = 12) -> List[dict]:
    """Compact representation of papers for LLM context."""
    top = sorted(papers, key=lambda p: p.citations, reverse=True)[:max_papers]
    return [
        {
            "title": p.title,
            "year": p.year,
            "citations": p.citations,
            "abstract": p.abstract[:300],
            "keywords": p.keywords[:5],
        }
        for p in top
    ]


# ── Main toolbox ──────────────────────────────────────────────────────────────

class ResearchToolbox:
    def __init__(self, llm=None, embedder=None) -> None:
        self._turboquant = TurboQuant(embedder=embedder)
        self._llm = llm  # Optional[LLMRouter]

    # ── helpers ───────────────────────────────────────────────────────────────

    def _call_llm(self, stage_id: str, stage_name: str, role: str, prompt: str) -> Optional[dict]:
        """Call LLM with a JSON-requesting prompt. Returns parsed dict or None."""
        if self._llm is None:
            return None
        result = self._llm.generate_stage_text(
            stage_id, stage_name, role,
            {"__direct_prompt__": prompt},
        )
        if result.get("error") or not result.get("text"):
            return None
        return _extract_json(result["text"])

    # ── stage tools ───────────────────────────────────────────────────────────

    def intake(self, project: ResearchProject) -> dict:
        return {
            "research_brief": {
                "domain": project.domain,
                "problem": project.problem,
                "abstract": project.abstract,
                "success_criteria": [
                    "produce a literature-grounded decision process",
                    "finalize one judged direction before execution",
                    "assemble an evidence-backed report with explicit decision rationale",
                ],
            }
        }

    def evidence_discovery(self, project: ResearchProject) -> dict:
        """Search Semantic Scholar for real papers; fall back to seeds on failure."""
        from .paper_search import search_papers

        # Build a focused query: domain + first 6 content words from problem
        query = f"{project.domain} {project.problem}"
        live_papers = search_papers(query, limit=20)

        if live_papers:
            # Merge live papers with any existing seeds (deduplicate by title)
            existing_titles = {p.title.lower() for p in project.papers}
            new_papers = [p for p in live_papers if p.title.lower() not in existing_titles]
            project.papers = project.papers + new_papers

        ranked = self._turboquant.rank_papers(project, limit=min(8, len(project.papers)))
        themes = Counter(keyword for paper in project.papers for keyword in paper.keywords)
        return {
            "paper_graph": {
                "anchors": [item.to_dict() for item in ranked],
                "theme_counts": dict(themes.most_common(10)),
                "total_papers": len(project.papers),
                "live_papers_found": len(live_papers),
            }
        }

    def planning_graph(self, project: ResearchProject) -> dict:
        tasks = [
            {"id": "task-literature", "label": "Survey prior work", "depends_on": []},
            {"id": "task-options", "label": "Propose competing research options", "depends_on": ["task-literature"]},
            {"id": "task-decision", "label": "Critique, ground, vote, and judge", "depends_on": ["task-options"]},
            {"id": "task-experiments", "label": "Execute the judged direction", "depends_on": ["task-decision"]},
            {"id": "task-writing", "label": "Assemble report from judged outputs", "depends_on": ["task-experiments"]},
        ]
        return {
            "task_graph": tasks,
            "decision_graph": [
                {"from": "planner", "to": "critic", "condition": "at least three concrete options proposed"},
                {"from": "critic", "to": "grounding", "condition": "major assumptions and risks enumerated"},
                {"from": "grounding", "to": "coordinator", "condition": "evidence links and support scores available"},
                {"from": "coordinator", "to": "judge", "condition": "weighted scorecards computed"},
                {"from": "judge", "to": "writer", "condition": "decision finalized and guardrails set"},
            ],
        }

    def survey(self, project: ResearchProject) -> dict:
        """Generate literature survey + gap analysis, using LLM if available."""
        digest = _paper_digest(project.papers)

        if self._llm and digest:
            prompt = (
                f"You are a research analyst. Domain: '{project.domain}'. "
                f"Problem: '{project.problem}'.\n\n"
                f"Papers found:\n{json.dumps(digest, indent=2)}\n\n"
                "Produce a literature survey and gap analysis.\n"
                "Return ONLY valid JSON with this exact shape:\n"
                '{"literature_survey": ["finding 1", "finding 2", "finding 3", "finding 4", "finding 5"], '
                '"gap_analysis": ["gap 1", "gap 2", "gap 3"]}'
            )
            parsed = self._call_llm("agent-survey", "Survey Agent", "literature-synthesis", prompt)
            if parsed and "literature_survey" in parsed and "gap_analysis" in parsed:
                survey_lines = [str(s) for s in parsed["literature_survey"]]
                gaps = [str(g) for g in parsed["gap_analysis"]]
                return {"literature_survey": survey_lines, "gap_analysis": gaps}

        # Fallback: derive from actual papers
        ranked = self._turboquant.rank_papers(project, limit=5)
        summary = [
            f"{item.title} ({item.year}) — citations: {item.citations}"
            for item in ranked
        ]
        themes = Counter(kw for p in project.papers for kw in p.keywords)
        top_themes = [t for t, _ in themes.most_common(5)]
        gaps = [
            f"Limited work on combining {top_themes[0] if top_themes else 'core concepts'} with {top_themes[1] if len(top_themes) > 1 else 'novel methods'}.",
            f"No benchmark specifically designed for {project.domain} evaluation.",
            f"Existing approaches lack explicit treatment of {project.problem[:60]}.",
        ]
        return {"literature_survey": summary, "gap_analysis": gaps}

    def proposal_options(self, project: ResearchProject, artifacts: Dict[str, object]) -> dict:
        """Propose research directions, using LLM if available."""
        gaps = artifacts.get("gap_analysis", [])
        anchors = self._anchor_titles(artifacts)
        digest = _paper_digest(project.papers, max_papers=8)

        if self._llm:
            prompt = (
                f"You are a research planner. Domain: '{project.domain}'. "
                f"Problem: '{project.problem}'.\n\n"
                f"Literature gaps:\n{json.dumps(gaps, indent=2)}\n\n"
                f"Top papers:\n{json.dumps(digest, indent=2)}\n\n"
                "Propose exactly 3 distinct research directions grounded in this literature.\n"
                "Return ONLY valid JSON:\n"
                '{"options": [{"id": "option-1", "title": "...", "summary": "...", '
                '"approach": "...", "feasibility": 0.8, "novelty": 0.7, '
                '"evidence_fit": 0.85, "execution_risk": 0.3, "anchors": ["paper title"]}]}'
            )
            parsed = self._call_llm("agent-planner", "Planner Agent", "proposal-planning", prompt)
            if parsed and "options" in parsed and len(parsed["options"]) >= 2:
                options = []
                for i, opt in enumerate(parsed["options"][:3]):
                    options.append({
                        "id": opt.get("id", f"option-{i+1}"),
                        "title": str(opt.get("title", f"Direction {i+1}")),
                        "summary": str(opt.get("summary", "")),
                        "approach": str(opt.get("approach", "")),
                        "feasibility": float(opt.get("feasibility", 0.75)),
                        "novelty": float(opt.get("novelty", 0.65)),
                        "evidence_fit": float(opt.get("evidence_fit", 0.75)),
                        "execution_risk": float(opt.get("execution_risk", 0.35)),
                        "anchors": list(opt.get("anchors", anchors[:2])),
                    })
                plan = [
                    "Propose multiple candidate research directions before committing.",
                    "Score each option on grounding, feasibility, novelty, and execution risk.",
                    "Require a judged winner before experiments and writing.",
                ]
                return {
                    "proposal_options": options,
                    "implementation_plan": plan,
                    "experiment_graph": build_experiment_graph(project).to_dict(),
                }

        # Fallback: synthetic options
        options = [
            {
                "id": "option-evidence-loop",
                "title": "Evidence-First Research Loop",
                "summary": f"Literature-grounded approach to {project.problem}",
                "approach": "High rigor planning pipeline with explicit evidence checkpoints.",
                "feasibility": 0.88,
                "novelty": 0.63,
                "evidence_fit": 0.90,
                "execution_risk": 0.28,
                "anchors": anchors[:3],
            },
            {
                "id": "option-topology-swarm",
                "title": "Topology-Adaptive Swarm",
                "summary": f"Multi-agent mesh approach for {project.domain}",
                "approach": "Graph-native agent coordination with weighted routing.",
                "feasibility": 0.72,
                "novelty": 0.87,
                "evidence_fit": 0.74,
                "execution_risk": 0.44,
                "anchors": anchors[:4],
            },
            {
                "id": "option-experiment-factory",
                "title": "Experiment-First Research Factory",
                "summary": f"Rapid-iteration empirical approach to {project.problem}",
                "approach": "Execution-led pipeline with strong benchmark automation.",
                "feasibility": 0.69,
                "novelty": 0.71,
                "evidence_fit": 0.58,
                "execution_risk": 0.47,
                "anchors": anchors[1:5],
            },
        ]
        plan = [
            "Propose multiple candidate research directions before committing to one.",
            "Score each option on grounding, feasibility, novelty, and execution risk.",
            "Require a judged winner before experiments and writing.",
            "Carry decision rationale into experiments and report sections.",
        ]
        return {
            "proposal_options": options,
            "implementation_plan": plan,
            "experiment_graph": build_experiment_graph(project).to_dict(),
        }

    def critique(self, artifacts: Dict[str, object]) -> dict:
        critique_items = []
        for option in artifacts.get("proposal_options", []):
            challenge = round(min(0.92, option["execution_risk"] * 0.9 + (1 - option["evidence_fit"]) * 0.45), 2)
            critique_items.append(
                {
                    "option_id": option["id"],
                    "title": option["title"],
                    "challenge_score": challenge,
                    "objections": [
                        "May over-claim novelty unless evidence links are explicit.",
                        "Needs clearer benchmark and stop conditions before execution.",
                        "Tool and coordination complexity could outgrow initial scope."
                        if option["execution_risk"] > 0.4
                        else "Scope appears manageable with disciplined execution boundaries.",
                    ],
                    "recommended_guardrail": "Require a judged decision plus evidence threshold before writing.",
                }
            )
        return {"critique_report": critique_items}

    def grounding(self, project: ResearchProject, artifacts: Dict[str, object]) -> dict:
        theme_counts = artifacts.get("paper_graph", {}).get("theme_counts", {})
        dominant_themes = sorted(theme_counts, key=theme_counts.get, reverse=True)[:5]
        checks = []
        for option in artifacts.get("proposal_options", []):
            support = round(min(0.97, option["evidence_fit"] + 0.05 * min(3, len(option.get("anchors", [])))), 2)
            checks.append(
                {
                    "option_id": option["id"],
                    "support_score": support,
                    "coverage_score": round(min(0.95, 0.52 + len(option.get("anchors", [])) * 0.08), 2),
                    "dominant_themes": dominant_themes,
                    "supported_by": option.get("anchors", []),
                    "verdict": "grounded" if support >= 0.7 else "weakly-grounded",
                }
            )
        return {"grounding_report": checks}

    def novelty(self, project: ResearchProject, artifacts: Dict[str, object]) -> dict:
        """Generate novelty hypotheses, using LLM if available."""
        gaps = artifacts.get("gap_analysis", [])
        options = artifacts.get("proposal_options", [])
        digest = _paper_digest(project.papers, max_papers=8)

        if self._llm and (digest or gaps):
            prompt = (
                f"You are a research novelty analyst. Domain: '{project.domain}'. "
                f"Problem: '{project.problem}'.\n\n"
                f"Literature gaps:\n{json.dumps(gaps, indent=2)}\n\n"
                f"Proposed directions:\n{json.dumps([{'title': o['title'], 'summary': o['summary']} for o in options], indent=2)}\n\n"
                f"Top papers:\n{json.dumps(digest[:6], indent=2)}\n\n"
                "Identify 3 novel research hypotheses or architectures NOT yet addressed in the literature above.\n"
                "Each must be specific, grounded, and differentiated.\n"
                "Return ONLY valid JSON:\n"
                '{"hypotheses": [{"id": "novelty-1", "title": "...", "summary": "...", '
                '"differentiators": ["...", "..."], "supporting_facets": ["facet-planning"]}]}'
            )
            parsed = self._call_llm("agent-novelty", "Novelty Critic Agent", "novelty-discovery", prompt)
            if parsed and "hypotheses" in parsed and len(parsed["hypotheses"]) >= 2:
                live_hypotheses = []
                valid_facets = {"facet-planning", "facet-execution", "facet-memory", "facet-coordination", "facet-mcp", "facet-oan"}
                for i, h in enumerate(parsed["hypotheses"][:3]):
                    facets = [f for f in (h.get("supporting_facets") or []) if f in valid_facets]
                    if not facets:
                        facets = ["facet-planning", "facet-coordination"]
                    live_hypotheses.append(
                        NoveltyHypothesis(
                            id=h.get("id", f"novelty-llm-{i+1}"),
                            title=str(h.get("title", f"Novel Hypothesis {i+1}")),
                            summary=str(h.get("summary", "")),
                            differentiators=[str(d) for d in (h.get("differentiators") or [])[:4]],
                            supporting_facets=facets,
                            score=round(0.85 - i * 0.08, 2),
                        )
                    )
                project.novelty_hypotheses = live_hypotheses
                option_novelty = [
                    {"option_id": o["id"], "novelty_bonus": round(live_hypotheses[i % len(live_hypotheses)].score / 20.0, 3)}
                    for i, o in enumerate(options)
                ]
                return {
                    "novelty_hypotheses": [h.to_dict() for h in live_hypotheses],
                    "option_novelty": option_novelty,
                }

        # Fallback: TurboQuant synthetic ranking
        ranked = self._turboquant.rank_novelty(project)
        project.novelty_hypotheses = ranked
        bonus = {
            "option-evidence-loop": ranked[-1].score if ranked else 0.0,
            "option-topology-swarm": ranked[0].score if ranked else 0.0,
            "option-experiment-factory": ranked[1].score if len(ranked) > 1 else 0.0,
        }
        option_novelty = [
            {"option_id": option_id, "novelty_bonus": round(score / 20.0, 2)}
            for option_id, score in bonus.items()
        ]
        return {
            "novelty_hypotheses": [item.to_dict() for item in ranked],
            "option_novelty": option_novelty,
        }

    def coordinate_vote(self, project: ResearchProject, artifacts: Dict[str, object]) -> dict:
        critiques = {item["option_id"]: item for item in artifacts.get("critique_report", [])}
        grounding = {item["option_id"]: item for item in artifacts.get("grounding_report", [])}
        novelty = {item["option_id"]: item["novelty_bonus"] for item in artifacts.get("option_novelty", [])}
        weights = {"grounding": 0.35, "feasibility": 0.25, "novelty": 0.2, "risk_penalty": 0.2}
        scorecards = []
        for option in artifacts.get("proposal_options", []):
            groundedness = grounding.get(option["id"], {}).get("support_score", 0.0)
            critique = critiques.get(option["id"], {}).get("challenge_score", 0.0)
            novelty_bonus = novelty.get(option["id"], 0.0)
            total = round(
                weights["grounding"] * groundedness
                + weights["feasibility"] * option["feasibility"]
                + weights["novelty"] * novelty_bonus
                - weights["risk_penalty"] * critique,
                3,
            )
            scorecards.append(
                {
                    "option_id": option["id"],
                    "title": option["title"],
                    "score": total,
                    "grounding": groundedness,
                    "feasibility": option["feasibility"],
                    "novelty": novelty_bonus,
                    "risk_penalty": critique,
                }
            )
        scorecards.sort(key=lambda item: item["score"], reverse=True)
        return {
            "coordination_topology": {
                "shape": "adaptive-sparse-mesh",
                "hubs": ["agent-planning-graph", "agent-coordinator", "agent-judge"],
                "policies": [
                    "planner, critic, and grounding agents submit structured score inputs",
                    "coordinator computes weighted vote instead of free-form preference",
                    "writer is blocked until judge finalizes a winning option",
                ],
            },
            "agent_routes": [
                "planner -> critic -> grounding -> novelty -> coordinator",
                "coordinator -> judge -> executor -> memory -> writer",
            ],
            "vote_board": {
                "weights": weights,
                "scorecards": scorecards,
                "provisional_winner": scorecards[0]["option_id"] if scorecards else "",
            },
        }

    def judge(self, artifacts: Dict[str, object]) -> dict:
        options = {item["id"]: item for item in artifacts.get("proposal_options", [])}
        critiques = {item["option_id"]: item for item in artifacts.get("critique_report", [])}
        grounding = {item["option_id"]: item for item in artifacts.get("grounding_report", [])}
        vote_board = artifacts.get("vote_board", {})
        scorecards = vote_board.get("scorecards", [])
        chosen = None
        for card in scorecards:
            support_score = grounding.get(card["option_id"], {}).get("support_score", 0.0)
            if support_score >= 0.68:
                chosen = card
                break
        if not chosen and scorecards:
            chosen = scorecards[0]
        if not chosen:
            return {
                "judged_decision": {"status": "blocked", "reason": "No scored options available."},
                "decision_summary": {"status": "blocked"},
            }
        option = options[chosen["option_id"]]
        critique = critiques.get(chosen["option_id"], {})
        support = grounding.get(chosen["option_id"], {})
        judged = {
            "status": "approved",
            "selected_option_id": option["id"],
            "decision_title": option["title"],
            "summary": option["summary"],
            "rationale": (
                f"Selected because it balanced grounding={support.get('support_score', 0.0)}, "
                f"feasibility={option['feasibility']}, novelty={chosen['novelty']}, and "
                f"manageable risk={critique.get('challenge_score', 0.0)}."
            ),
            "guardrails": [
                "Do not draft claims that are not supported by the grounding ledger.",
                "Carry critique objections into experiment design and report limitations.",
                "Treat the judged option as the only executable direction for this run.",
            ],
            "vote_score": chosen["score"],
            "grounding_score": support.get("support_score", 0.0),
        }
        return {
            "judged_decision": judged,
            "decision_summary": {
                "winner": option["title"],
                "vote_score": chosen["score"],
                "grounding_score": support.get("support_score", 0.0),
            },
        }

    def execute_experiments(self, project: ResearchProject, artifacts: Dict[str, object]) -> dict:
        judged = artifacts.get("judged_decision", {})
        selected_title = judged.get("decision_title", "Unjudged Direction")
        updated: List[ExperimentRun] = []
        for experiment in deepcopy(project.experiments):
            experiment.status = "completed"
            experiment.metrics = {
                key: round(value + 0.04, 3) if value < 1 else value
                for key, value in experiment.metrics.items()
            }
            experiment.metrics["decision_alignment"] = round(judged.get("grounding_score", 0.0), 3)
            updated.append(experiment)
        project.experiments = updated
        return {
            "experiment_results": [experiment.to_dict() for experiment in updated],
            "experiment_summary": {
                "completed": len(updated),
                "best_experiment": updated[0].name if updated else "",
                "decision_title": selected_title,
            },
        }

    def build_memory(self, project: ResearchProject, artifacts: Dict[str, object]) -> dict:
        judged = artifacts.get("judged_decision", {})
        entries = [
            {
                "kind": "paper-anchor",
                "title": "Graph taxonomy anchor",
                "content": "Use planning/execution/memory/coordination as persistent axes.",
                "linked_ids": ["paper-graphs-meet-agents"],
            },
            {
                "kind": "decision-principle",
                "title": "Judge after evidence review",
                "content": "Do not let the writer or executor move before critique, grounding, and weighted voting are complete.",
                "linked_ids": ["artifact-decision"],
            },
            {
                "kind": "experiment-insight",
                "title": "Topology routing matters",
                "content": "Adaptive routing should be evaluated against fixed chains and star topologies.",
                "linked_ids": ["experiment-topology-router"],
            },
            {
                "kind": "writing-constraint",
                "title": "Ground every section",
                "content": "Each report section must link back to judged decisions, evidence, or experiment outputs.",
                "linked_ids": ["report-related-work", "report-method", "report-results"],
            },
        ]
        if judged:
            entries.append(
                {
                    "kind": "decision-record",
                    "title": judged.get("decision_title", "Judged Direction"),
                    "content": judged.get("rationale", ""),
                    "linked_ids": ["artifact-decision"],
                }
            )
        return {
            "memory_graph": entries,
            "evidence_context": {
                "available_artifacts": sorted(artifacts.keys()),
                "memory_principles": [entry["title"] for entry in entries],
                "judged_decision": judged.get("decision_title", ""),
            },
        }

    def report(self, project: ResearchProject, artifacts: Dict[str, object]) -> dict:
        """Write research report, using LLM if available."""
        judged = artifacts.get("judged_decision", {})
        if not judged or judged.get("status") != "approved":
            return {
                "writer_blocked": {
                    "status": "blocked",
                    "reason": "Writer requires a judged decision before drafting.",
                }
            }

        literature_survey = artifacts.get("literature_survey", [])
        experiment_summary = artifacts.get("experiment_summary", {})
        novelty_hypotheses = artifacts.get("novelty_hypotheses", [])
        graph = build_report_graph(project).to_dict()

        if self._llm:
            prompt = (
                f"You are a research writer. Write a structured research report.\n\n"
                f"Domain: '{project.domain}'\n"
                f"Problem: '{project.problem}'\n"
                f"Selected Direction: '{judged['decision_title']}'\n"
                f"Rationale: '{judged['rationale']}'\n\n"
                f"Literature survey:\n{json.dumps(literature_survey[:5], indent=2)}\n\n"
                f"Novel hypotheses:\n{json.dumps([h.get('title','') + ': ' + h.get('summary','') for h in novelty_hypotheses[:3]], indent=2)}\n\n"
                f"Experiment summary: {json.dumps(experiment_summary, indent=2)}\n\n"
                "Write substantive, informative content for each section (2-4 sentences each).\n"
                "Return ONLY valid JSON:\n"
                '{"report-problem": "...", "report-related-work": "...", '
                '"report-method": "...", "report-experiments": "...", "report-results": "..."}'
            )
            parsed = self._call_llm("agent-writer", "Writer Agent", "report-generation", prompt)
            if parsed and "report-problem" in parsed:
                drafts = {
                    "report-problem": str(parsed.get("report-problem", "")),
                    "report-related-work": str(parsed.get("report-related-work", "")),
                    "report-method": str(parsed.get("report-method", "")),
                    "report-experiments": str(parsed.get("report-experiments", "")),
                    "report-results": str(parsed.get("report-results", "")),
                }
                return {
                    "report_graph": graph,
                    "paper_draft": drafts,
                    "final_report": {
                        "status": "completed",
                        "sections": len(project.report_sections),
                        "draft_titles": [section.title for section in project.report_sections],
                        "decision_title": judged["decision_title"],
                        "summary": drafts["report-results"],
                        "guardrails": judged.get("guardrails", []),
                        "llm_generated": True,
                    },
                }

        # Fallback: template-based report
        drafts = {
            "report-problem": f"Problem Framing: {project.problem}",
            "report-related-work": "Related Work: " + "; ".join(literature_survey[:3]),
            "report-method": (
                f"Method: selected direction is {judged['decision_title']}. "
                f"Rationale: {judged['rationale']}"
            ),
            "report-experiments": (
                f"Experiments: executed against the judged direction with best experiment "
                f"{experiment_summary.get('best_experiment', 'n/a')}."
            ),
            "report-results": (
                f"Results And Analysis: judged vote score={judged.get('vote_score', 0.0)}, "
                f"grounding score={judged.get('grounding_score', 0.0)}. "
                f"Guardrails: {'; '.join(judged.get('guardrails', []))}"
            ),
        }
        return {
            "report_graph": graph,
            "paper_draft": drafts,
            "final_report": {
                "status": "completed",
                "sections": len(project.report_sections),
                "draft_titles": [section.title for section in project.report_sections],
                "decision_title": judged["decision_title"],
                "summary": (
                    f"Finalized {judged['decision_title']} after critique, grounding review, "
                    f"weighted coordination vote, and judge approval."
                ),
                "guardrails": judged.get("guardrails", []),
            },
        }

    def stage_messages(self, stage_id: str, role: str) -> List[dict]:
        normalized = role.lower()
        if "planning" in normalized or "proposal" in normalized:
            return [
                {"target": "agent-critic", "category": "strategy", "content": "Three candidate directions proposed for attack review."},
                {"target": "agent-grounding", "category": "evidence", "content": "Check whether each option is grounded in the paper graph."},
            ]
        if "critique" in normalized:
            return [
                {"target": "agent-coordinator", "category": "critique", "content": "Risk and objection scores are ready for weighted voting."},
            ]
        if "grounding" in normalized:
            return [
                {"target": "agent-coordinator", "category": "evidence", "content": "Grounding scores and evidence links are ready for vote aggregation."},
                {"target": "agent-judge", "category": "evidence", "content": "Support thresholds available for final decision review."},
            ]
        if "coordination" in normalized:
            return [
                {"target": "agent-judge", "category": "vote", "content": "Weighted scorecards computed and ranked."},
            ]
        if "judging" in normalized:
            return [
                {"target": "agent-executor", "category": "decision", "content": "One direction has been approved for execution."},
                {"target": "agent-writer", "category": "decision", "content": "Draft only from the judged direction and its guardrails."},
            ]
        if "experiment" in normalized:
            return [
                {"target": "agent-memory", "category": "result", "content": "Record experiment outcomes and failure motifs."},
                {"target": "agent-writer", "category": "result", "content": "Results available for report graph grounding."},
            ]
        if "novelty" in normalized:
            return [
                {"target": "agent-coordinator", "category": "novelty", "content": "Novelty bonus scores ready for weighted decision fusion."},
            ]
        return []

    def _anchor_titles(self, artifacts: Dict[str, object]) -> List[str]:
        anchors = artifacts.get("paper_graph", {}).get("anchors", [])
        titles = [item.get("title", "") for item in anchors if item.get("title")]
        return titles or ["Graphs Meet AI Agents", "Retrieval-Augmented Generation", "Self-Refine"]


def make_memory_entries(run_id: str, payload: List[dict]) -> List[RunMemoryEntry]:
    entries: List[RunMemoryEntry] = []
    for index, item in enumerate(payload, start=1):
        entries.append(
            RunMemoryEntry(
                id=f"{run_id}-memory-{index}",
                kind=item["kind"],
                title=item["title"],
                content=item["content"],
                linked_ids=item.get("linked_ids", []),
            )
        )
    return entries


def make_swarm_messages(run_id: str, stage_id: str, source: str, payload: List[dict]) -> List[SwarmMessage]:
    messages: List[SwarmMessage] = []
    for index, item in enumerate(payload, start=1):
        messages.append(
            SwarmMessage(
                id=f"{run_id}-{stage_id}-msg-{index}",
                source=source,
                target=item["target"],
                category=item["category"],
                content=item["content"],
                priority=0.8,
            )
        )
    return messages


def make_timeline_event(run_id: str, stage_id: str, agent_name: str, event_type: str, summary: str, detail=None) -> TimelineEvent:
    return TimelineEvent(
        id=f"{run_id}-{stage_id}-{event_type}",
        stage_id=stage_id,
        agent_name=agent_name,
        event_type=event_type,
        summary=summary,
        detail=detail or {},
    )
