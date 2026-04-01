"""Citation graph expansion via Semantic Scholar API.

Given a paper (by Semantic Scholar ID or title), fetch its references and
citing papers to expand the research corpus beyond flat keyword search.

No API key required (rate-limited to ~100 req/min without key).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import List, Optional
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import Paper

_SS_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "paperId,title,abstract,authors,year,venue,citationCount,fieldsOfStudy,externalIds"


def expand_citations(
    paper: Paper,
    depth: int = 1,
    max_refs: int = 10,
    max_cites: int = 10,
) -> List[Paper]:
    """Fetch references and citing papers for the given paper.

    Returns a deduplicated list of new Paper objects (excluding the input).
    Set depth > 1 for recursive expansion (use with caution — grows fast).
    """
    ss_id = _resolve_ss_id(paper)
    if not ss_id:
        return []

    found: dict[str, Paper] = {}  # paperId → Paper
    _expand_one(ss_id, found, max_refs=max_refs, max_cites=max_cites)

    if depth > 1:
        # Second-level expansion on the top-cited papers from level 1
        level1_ids = sorted(found.keys(), key=lambda k: found[k].citations, reverse=True)[:5]
        for pid in level1_ids:
            _expand_one(pid, found, max_refs=min(5, max_refs), max_cites=min(5, max_cites))

    # Remove the original paper if it ended up in the results
    found.pop(ss_id, None)
    return list(found.values())


def _resolve_ss_id(paper: Paper) -> Optional[str]:
    """Try to find a Semantic Scholar paper ID from our Paper object."""
    # If the paper.id starts with "ss-", try to reverse it
    if paper.url and "semanticscholar.org" in paper.url:
        # Extract from URL
        parts = paper.url.rstrip("/").split("/")
        return parts[-1] if parts else None

    # Try searching by title
    clean_title = re.sub(r"[^a-zA-Z0-9 ]", "", paper.title)[:100]
    url = f"{_SS_BASE}/paper/search?query={quote(clean_title)}&limit=1&fields=paperId"
    headers = _headers()
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        results = data.get("data", [])
        if results:
            return results[0].get("paperId")
    except Exception:
        pass
    return None


def _expand_one(
    ss_id: str,
    found: dict[str, Paper],
    max_refs: int = 10,
    max_cites: int = 10,
) -> None:
    """Fetch references and citations for a single paper ID."""
    # References
    refs = _fetch_connected(ss_id, "references", limit=max_refs)
    for p in refs:
        if p.id not in found:
            found[p.id] = p

    # Small delay to respect rate limits
    time.sleep(0.5)

    # Citations
    cites = _fetch_connected(ss_id, "citations", limit=max_cites)
    for p in cites:
        if p.id not in found:
            found[p.id] = p


def _fetch_connected(ss_id: str, direction: str, limit: int = 10) -> List[Paper]:
    """Fetch references or citations for a paper.

    direction: "references" or "citations"
    """
    url = (
        f"{_SS_BASE}/paper/{ss_id}/{direction}"
        f"?fields={_FIELDS}&limit={limit}"
    )
    headers = _headers()
    req = Request(url, headers=headers)

    for attempt in range(2):
        try:
            with urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
            papers = []
            for item in data.get("data", []):
                nested = item.get("citedPaper" if direction == "references" else "citingPaper", {})
                if nested and nested.get("title"):
                    papers.append(_to_paper(nested))
            return papers
        except HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(5)
                continue
            return []
        except Exception:
            return []
    return []


def _to_paper(item: dict) -> Paper:
    raw_id = item.get("paperId", "")
    safe_id = "ss-" + re.sub(r"[^a-z0-9]", "", raw_id.lower())[:20] if raw_id else f"ss-{abs(hash(item.get('title', ''))):x}"
    authors = [a.get("name", "") for a in (item.get("authors") or [])]
    ext = item.get("externalIds") or {}
    arxiv_id = ext.get("ArXiv", "")
    url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""
    return Paper(
        id=safe_id,
        title=item.get("title", "Untitled"),
        abstract=(item.get("abstract") or "")[:2000],
        authors=authors[:6],
        year=item.get("year") or 2024,
        venue=item.get("venue") or "Unknown",
        citations=item.get("citationCount") or 0,
        keywords=item.get("fieldsOfStudy") or [],
        references=[],
        url=url,
    )


def _headers() -> dict:
    headers = {"User-Agent": "ResearchGraph/1.0"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if api_key:
        headers["x-api-key"] = api_key
    return headers
