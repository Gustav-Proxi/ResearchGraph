"""Semantic Scholar paper search — no API key required for basic queries."""
from __future__ import annotations

import json
import os
import re
import time
from typing import List
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import Paper

_SS_BASE = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "paperId,title,abstract,authors,year,venue,citationCount,fieldsOfStudy"


def search_papers(query: str, limit: int = 20) -> List[Paper]:
    """Search Semantic Scholar. Returns [] on any failure or rate limit."""
    # Strip question words that confuse the search
    clean_query = re.sub(r"\b(how|what|why|when|where|which|can|we|do|is|are|the|a|an|to|for)\b", " ", query, flags=re.I)
    clean_query = " ".join(clean_query.split())[:120]  # max 120 chars

    url = f"{_SS_BASE}/paper/search?query={quote(clean_query)}&limit={limit}&fields={_FIELDS}"
    headers = {"User-Agent": "ResearchGraph/1.0"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if api_key:
        headers["x-api-key"] = api_key

    for attempt in range(2):
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode())
            return [_to_paper(item) for item in data.get("data", []) if item.get("title")]
        except HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(3)
                continue
            return []
        except Exception:
            return []
    return []


def _to_paper(item: dict) -> Paper:
    raw_id = item.get("paperId", "")
    safe_id = "ss-" + re.sub(r"[^a-z0-9]", "", raw_id.lower())[:20] if raw_id else f"ss-{hash(item.get('title',''))}"
    authors = [a.get("name", "") for a in (item.get("authors") or [])]
    return Paper(
        id=safe_id,
        title=item.get("title", "Untitled"),
        abstract=(item.get("abstract") or "")[:800],
        authors=authors[:6],
        year=item.get("year") or 2024,
        venue=item.get("venue") or "Unknown",
        citations=item.get("citationCount") or 0,
        keywords=item.get("fieldsOfStudy") or [],
        references=[],
    )
