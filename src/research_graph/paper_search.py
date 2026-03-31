"""Paper search: Semantic Scholar (primary) + arXiv (supplement). No API keys required."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Dict, List
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import Paper

_SS_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "paperId,title,abstract,authors,year,venue,citationCount,fieldsOfStudy,externalIds"

# In-process cache: query → papers (avoids re-hitting SS on repeat runs)
_CACHE: Dict[str, List[Paper]] = {}


def search_papers(query: str, limit: int = 20) -> List[Paper]:
    """Search Semantic Scholar + arXiv. Returns merged, deduplicated results."""
    ss_papers = _search_semantic_scholar(query, limit=limit)

    # Supplement with arXiv — lazy import to avoid circular imports at module load
    try:
        from .arxiv_search import search_arxiv
        ax_papers = search_arxiv(query, limit=10)
    except Exception:
        ax_papers = []

    # Deduplicate by normalised title
    seen: set = {_norm_title(p.title) for p in ss_papers}
    merged = list(ss_papers)
    for p in ax_papers:
        key = _norm_title(p.title)
        if key not in seen:
            seen.add(key)
            merged.append(p)
    return merged[:limit]


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())[:60]


def _search_semantic_scholar(query: str, limit: int = 20) -> List[Paper]:
    """Search Semantic Scholar. Returns [] on any failure or rate limit."""
    clean_query = re.sub(
        r"\b(how|what|why|when|where|which|can|we|do|is|are|the|a|an|to|for|and|or|in|of|on|at|by)\b",
        " ", query, flags=re.I,
    )
    clean_query = " ".join(clean_query.split())[:100]

    cache_key = clean_query.lower()
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    url = f"{_SS_BASE}/paper/search?query={quote(clean_query)}&limit={limit}&fields={_FIELDS}"
    headers = {"User-Agent": "ResearchGraph/1.0"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if api_key:
        headers["x-api-key"] = api_key

    backoffs = [5, 15]
    for attempt in range(3):
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
            papers = [_to_paper(item) for item in data.get("data", []) if item.get("title")]
            if papers:
                _CACHE[cache_key] = papers
            return papers
        except HTTPError as e:
            if e.code == 429 and attempt < len(backoffs):
                time.sleep(backoffs[attempt])
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
