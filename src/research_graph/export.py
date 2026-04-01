"""Report export — Markdown and LaTeX generation from completed runs.

Pulls from run artifacts (paper_draft, final_report, judged_decision)
and assembles a publication-ready document.
"""
from __future__ import annotations

import re
from typing import Dict, Optional


def export_markdown(run_dict: dict, project_dict: Optional[dict] = None) -> str:
    """Export a completed run's report as Markdown."""
    artifacts = run_dict.get("artifacts", {})
    draft = artifacts.get("paper_draft", {})
    report = artifacts.get("final_report", {})
    decision = artifacts.get("judged_decision", {})
    project_name = run_dict.get("project_name", "Research Project")

    lines = []
    lines.append(f"# {project_name}")
    lines.append("")

    if project_dict:
        lines.append(f"**Domain:** {project_dict.get('domain', '')}")
        lines.append(f"**Problem:** {project_dict.get('problem', '')}")
        lines.append("")

    # Decision summary
    if decision.get("decision_title"):
        lines.append("## Research Direction")
        lines.append("")
        lines.append(f"**Selected:** {decision['decision_title']}")
        lines.append("")
        if decision.get("rationale"):
            lines.append(f"> {decision['rationale']}")
            lines.append("")
        if decision.get("supported_by"):
            lines.append("**Evidence:** " + ", ".join(decision["supported_by"]))
            lines.append("")

    # Draft sections
    section_order = [
        "report-problem", "report-related-work", "report-method",
        "report-results", "report-discussion", "report-conclusion",
    ]
    for key in section_order:
        if key in draft:
            title = _section_title(key)
            lines.append(f"## {title}")
            lines.append("")
            lines.append(draft[key])
            lines.append("")

    # Any remaining draft sections not in the standard order
    for key, value in draft.items():
        if key not in section_order and isinstance(value, str) and value.strip():
            title = _section_title(key)
            lines.append(f"## {title}")
            lines.append("")
            lines.append(value)
            lines.append("")

    # Report metadata
    if report.get("status"):
        lines.append("---")
        lines.append("")
        lines.append(f"*Status: {report['status']}*")
        if report.get("revision_count"):
            lines.append(f"*Revisions: {report['revision_count']}*")
        if report.get("llm_generated"):
            lines.append("*Generated with LLM assistance*")
        lines.append("")

    return "\n".join(lines)


def export_latex(run_dict: dict, project_dict: Optional[dict] = None) -> str:
    """Export a completed run's report as LaTeX."""
    artifacts = run_dict.get("artifacts", {})
    draft = artifacts.get("paper_draft", {})
    report = artifacts.get("final_report", {})
    decision = artifacts.get("judged_decision", {})
    project_name = run_dict.get("project_name", "Research Project")

    lines = []
    lines.append(r"\documentclass[11pt]{article}")
    lines.append(r"\usepackage[utf8]{inputenc}")
    lines.append(r"\usepackage[margin=1in]{geometry}")
    lines.append(r"\usepackage{hyperref}")
    lines.append(r"\usepackage{booktabs}")
    lines.append("")
    lines.append(rf"\title{{{_tex_escape(project_name)}}}")
    lines.append(r"\author{ResearchGraph Autonomous Research Suite}")
    lines.append(r"\date{\today}")
    lines.append("")
    lines.append(r"\begin{document}")
    lines.append(r"\maketitle")
    lines.append("")

    if project_dict and project_dict.get("abstract"):
        lines.append(r"\begin{abstract}")
        lines.append(_tex_escape(project_dict["abstract"]))
        lines.append(r"\end{abstract}")
        lines.append("")

    # Decision summary
    if decision.get("decision_title"):
        lines.append(r"\section{Research Direction}")
        lines.append(rf"\textbf{{Selected:}} {_tex_escape(decision['decision_title'])}")
        lines.append("")
        if decision.get("rationale"):
            lines.append(_tex_escape(decision["rationale"]))
            lines.append("")

    # Draft sections
    section_order = [
        "report-problem", "report-related-work", "report-method",
        "report-results", "report-discussion", "report-conclusion",
    ]
    for key in section_order:
        if key in draft:
            title = _section_title(key)
            lines.append(rf"\section{{{_tex_escape(title)}}}")
            lines.append(_tex_escape(draft[key]))
            lines.append("")

    for key, value in draft.items():
        if key not in section_order and isinstance(value, str) and value.strip():
            title = _section_title(key)
            lines.append(rf"\section{{{_tex_escape(title)}}}")
            lines.append(_tex_escape(value))
            lines.append("")

    lines.append(r"\end{document}")
    return "\n".join(lines)


def _section_title(key: str) -> str:
    return key.replace("report-", "").replace("-", " ").title()


def _tex_escape(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text
