"""Embedding client — supports OpenRouter (openai-compatible) and Ollama."""
from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional
from urllib.request import Request, urlopen


class EmbeddingClient:
    """
    Produces float embeddings for text.
    Provider resolution order:
      1. settings["embedding_provider"] / settings["embedding_model"]
      2. Falls back to OpenRouter text-embedding-3-small if API key present
      3. Returns None on any failure (callers must handle gracefully)
    """

    def __init__(self, settings: Dict[str, object]) -> None:
        self._settings = settings

    def embed(self, text: str) -> Optional[List[float]]:
        provider = str(self._settings.get("embedding_provider", "ollama"))
        model = str(self._settings.get("embedding_model", "nomic-embed-text"))

        if provider == "ollama":
            result = self._ollama_embed(model, text)
            if result is not None:
                return result
            # Ollama unavailable — fall through to OpenRouter if key present

        if provider in {"openrouter", "openai"} or self._openrouter_key():
            or_model = model if provider in {"openrouter", "openai"} else "openai/text-embedding-3-small"
            return self._openai_compatible_embed(
                base_url="https://openrouter.ai/api/v1",
                api_key=self._openrouter_key(),
                model=or_model,
                text=text,
            )
        return None

    def embed_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        return [self.embed(t) for t in texts]

    # ── providers ─────────────────────────────────────────────────────────────

    def _ollama_embed(self, model: str, text: str) -> Optional[List[float]]:
        base_url = str(self._settings.get("ollama_base_url", "http://127.0.0.1:11434")).rstrip("/")
        payload = {"model": model, "prompt": text}
        req = Request(
            f"{base_url}/api/embeddings",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return data.get("embedding")
        except Exception:
            return None

    def _openai_compatible_embed(self, base_url: str, api_key: str, model: str, text: str) -> Optional[List[float]]:
        if not api_key:
            return None
        payload = {"model": model, "input": text}
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        req = Request(
            f"{base_url.rstrip('/')}/embeddings",
            data=json.dumps(payload).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            return data["data"][0]["embedding"]
        except Exception:
            return None

    def _openrouter_key(self) -> str:
        providers_config = self._settings.get("providers_config", {}) or {}
        entry = providers_config.get("openrouter", {})
        if isinstance(entry, dict) and entry.get("api_key"):
            return str(entry["api_key"])
        return os.getenv("OPENROUTER_API_KEY", "")


# ── cosine similarity ─────────────────────────────────────────────────────────

def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
