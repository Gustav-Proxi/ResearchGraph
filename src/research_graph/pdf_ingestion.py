"""PDF ingestion pipeline for research papers.

Flow:
  1. Download PDF from a URL (arXiv or Semantic Scholar link)
  2. Extract text using pypdf (pure Python, no system deps)
  3. Segment into sections: Abstract, Introduction, Method, Results, Conclusion
  4. Return PaperSection list for downstream LLM context

Falls back gracefully if pypdf is not installed or the download fails.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.request import Request, urlopen


@dataclass
class PaperSection:
    title: str
    text: str
    char_count: int

    def to_dict(self) -> dict:
        return {"title": self.title, "text": self.text, "char_count": self.char_count}


_SECTION_HEADERS = [
    "abstract", "introduction", "related work", "background",
    "method", "methodology", "approach", "model", "architecture",
    "experiment", "evaluation", "results", "discussion",
    "conclusion", "future work", "references",
]

_SECTION_RE = re.compile(
    r"^\s*(\d+\.?\s+)?(" + "|".join(re.escape(h) for h in _SECTION_HEADERS) + r")\b",
    re.IGNORECASE | re.MULTILINE,
)


def ingest_pdf(url: str, max_chars: int = 20_000) -> List[PaperSection]:
    """Download and parse a PDF. Returns [] on any failure."""
    raw = _download(url)
    if not raw:
        return []
    text = _extract_text(raw)
    if not text:
        return []
    return _segment(text[:max_chars])


def ingest_arxiv_pdf(arxiv_id: str, max_chars: int = 20_000) -> List[PaperSection]:
    """Convenience wrapper: ingest from arXiv ID (e.g. '2301.07543')."""
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    return ingest_pdf(url, max_chars=max_chars)


def _download(url: str) -> Optional[bytes]:
    headers = {
        "User-Agent": "ResearchGraph/1.0 (PDF ingestion; mailto:research@example.com)",
        "Accept": "application/pdf,*/*",
    }
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not url.endswith(".pdf"):
                # Try to follow redirect to PDF
                pass
            return resp.read()
    except Exception:
        return None


def _extract_text(pdf_bytes: bytes) -> Optional[str]:
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages[:40]:  # cap at 40 pages
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue
        return "\n".join(pages)
    except ImportError:
        return _extract_text_fallback(pdf_bytes)
    except Exception:
        return None


def _extract_text_fallback(pdf_bytes: bytes) -> Optional[str]:
    """Very basic fallback: decode visible ASCII from PDF stream."""
    try:
        text = pdf_bytes.decode("latin-1", errors="ignore")
        # Extract text between BT (begin text) and ET (end text) markers
        chunks = re.findall(r"BT\s*(.*?)\s*ET", text, re.DOTALL)
        visible = []
        for chunk in chunks:
            tokens = re.findall(r"\(([^)]{1,200})\)", chunk)
            visible.extend(tokens)
        return " ".join(visible) if visible else None
    except Exception:
        return None


def _segment(text: str) -> List[PaperSection]:
    """Split text into named sections based on header patterns."""
    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        # No headers found — return as a single abstract block
        return [PaperSection(title="Full Text", text=text.strip(), char_count=len(text))]

    sections: List[PaperSection] = []

    # Text before first match = preamble / title / authors
    preamble = text[: matches[0].start()].strip()
    if len(preamble) > 100:
        sections.append(PaperSection(title="Preamble", text=preamble[:2000], char_count=len(preamble)))

    for i, match in enumerate(matches):
        header = match.group(0).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if len(body) < 50:
            continue
        sections.append(PaperSection(title=header, text=body[:4000], char_count=len(body)))

    return sections
