"""
SBERT-based text embedder for the knowledge base.
Uses sentence-transformers (local, free, no API calls).
Model is downloaded once and cached in ~/.cache/huggingface/.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Union

import numpy as np

from src.core.logging import get_logger

log = get_logger(__name__)

# 384-dim, fast, good quality for code + prose similarity
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
        model = _get_model(self.model_name)
        vec: np.ndarray = model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = _get_model(self.model_name)
        vecs: np.ndarray = model.encode(texts, normalize_embeddings=True, batch_size=32)
        return vecs.tolist()

    @staticmethod
    def build_kb_text(title: str, description: str, payload: dict) -> str:
        """Compose the text blob that gets embedded for a KB entry."""
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
