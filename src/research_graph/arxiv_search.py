"""arXiv search — no API key required. Uses the arXiv API v1 (Atom feed)."""
from __future__ import annotations

import re
import time
from typing import List
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

from .models import Paper

_ARXIV_API = "https://export.arxiv.org/api/query"
_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def search_arxiv(query: str, limit: int = 10) -> List[Paper]:
    """Search arXiv. Returns [] on any failure or rate limit."""
    clean = re.sub(r"\b(how|what|why|when|where|which|can|we|do|is|are|the|a|an|to|for)\b", " ", query, flags=re.I)
    clean = " ".join(clean.split())[:120]

    url = (
        f"{_ARXIV_API}?search_query=all:{quote(clean)}"
        f"&start=0&max_results={limit}&sortBy=relevance&sortOrder=descending"
    )
    req = Request(url, headers={"User-Agent": "ResearchGraph/1.0"})
    for attempt in range(2):
        try:
            with urlopen(req, timeout=15) as resp:
                xml_bytes = resp.read()
            return _parse_feed(xml_bytes)
        except HTTPError as exc:
            if exc.code == 429 and attempt == 0:
                time.sleep(5)
                continue
            return []
        except Exception:
            return []
    return []


def _parse_feed(xml_bytes: bytes) -> List[Paper]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    papers: List[Paper] = []
    for entry in root.findall("atom:entry", _NS):
        arxiv_id_raw = _text(entry, "atom:id")
        if not arxiv_id_raw:
            continue
        # e.g. http://arxiv.org/abs/2301.07543v2 → 2301.07543
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id_raw.rstrip("/").split("/")[-1])
        safe_id = "ax-" + re.sub(r"[^a-z0-9]", "", arxiv_id.lower())[:20]

        title = (_text(entry, "atom:title") or "Untitled").replace("\n", " ").strip()
        abstract = (_text(entry, "atom:summary") or "").replace("\n", " ").strip()[:2000]

        authors = [
            (a.find("atom:name", _NS).text or "").strip()
            for a in entry.findall("atom:author", _NS)
            if a.find("atom:name", _NS) is not None
        ][:6]

        # published date → year
        published = _text(entry, "atom:published") or ""
        year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else 2024

        # categories
        cats = [
            c.get("term", "")
            for c in entry.findall("atom:category", _NS)
            if c.get("term")
        ][:5]

        url = f"https://arxiv.org/abs/{arxiv_id}"

        papers.append(
            Paper(
                id=safe_id,
                title=title,
                abstract=abstract,
                authors=authors,
                year=year,
                venue="arXiv",
                citations=0,  # arXiv API doesn't expose citation counts
                keywords=cats,
                references=[],
                url=url,
            )
        )
    return papers


def _text(elem: ET.Element, tag: str) -> str:
    found = elem.find(tag, _NS)
    return (found.text or "").strip() if found is not None and found.text else ""
