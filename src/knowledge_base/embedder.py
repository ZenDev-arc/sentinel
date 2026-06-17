"""
Text embedder for the knowledge base.

Uses sentence-transformers (all-MiniLM-L6-v2) locally — no API key required,
no rate limits, works offline. The model (~80 MB) is downloaded on first use
and cached by sentence-transformers in ~/.cache/torch/sentence_transformers/.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from src.core.logging import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _get_model(model_name: str = _DEFAULT_MODEL):
    from sentence_transformers import SentenceTransformer
    log.info("loading_embedding_model", model=model_name)
    return SentenceTransformer(model_name)


class Embedder:
    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self.model_name = model_name

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            model = _get_model(self.model_name)
            vecs: np.ndarray = model.encode(texts, normalize_embeddings=True, batch_size=32)
            return vecs.tolist()
        except Exception as exc:
            log.warning("embedding_failed_returning_zeros", error=str(exc))
            return [[0.0] * 384 for _ in texts]

    @staticmethod
    def build_kb_text(title: str, description: str, payload: dict) -> str:
        parts = [title, description]
        if root_cause := payload.get("root_cause"):
            parts.append(f"Root cause: {root_cause}")
        if patch := payload.get("patch"):
            parts.append(f"Fix: {patch[:300]}")
        if pattern := payload.get("pattern"):
            parts.append(f"Pattern: {pattern}")
        if suggestion := payload.get("suggestion"):
            parts.append(f"Suggestion: {suggestion}")
        return "\n".join(parts)
