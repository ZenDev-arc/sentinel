"""
Text embedder for the knowledge base.

When HUGGINGFACE_API_KEY is set, uses the HF Inference API so PyTorch
never loads on the host. Falls back to local sentence-transformers when
no API key is present.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Union

import numpy as np

from src.core.logging import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_MODEL_SHORT = "all-MiniLM-L6-v2"


def _use_api() -> bool:
    from src.core.config import settings
    return bool(settings.HUGGINGFACE_API_KEY)


@lru_cache(maxsize=1)
def _get_local_model(model_name: str = _DEFAULT_MODEL_SHORT):
    from sentence_transformers import SentenceTransformer
    log.info("loading_embedding_model", model=model_name)
    return SentenceTransformer(model_name)


# Cached flag: once HF API is confirmed unreachable, skip it for the process lifetime
_api_unreachable: bool = False


def _embed_via_api(texts: list[str]) -> list[list[float]]:
    import httpx
    from src.core.config import settings

    resp = httpx.post(
        f"https://api-inference.huggingface.co/pipeline/feature-extraction/{_DEFAULT_MODEL}",
        headers={"Authorization": f"Bearer {settings.HUGGINGFACE_API_KEY}"},
        json={"inputs": texts, "options": {"wait_for_model": True}},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    # HF returns list[list[float]] for batch or list[float] for single
    if isinstance(data[0], float):
        data = [data]
    # Normalize each vector
    result = []
    for vec in data:
        arr = np.array(vec, dtype=float)
        norm = np.linalg.norm(arr)
        result.append((arr / norm if norm > 0 else arr).tolist())
    return result


class Embedder:
    def __init__(self, model_name: str = _DEFAULT_MODEL_SHORT) -> None:
        self.model_name = model_name

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        global _api_unreachable
        if _use_api() and not _api_unreachable:
            try:
                results = []
                for i in range(0, len(texts), 32):
                    results.extend(_embed_via_api(texts[i:i + 32]))
                return results
            except Exception as exc:
                _api_unreachable = True
                log.warning("hf_api_unreachable_falling_back_to_local", error=str(exc))
        # Fall back to local sentence-transformers
        try:
            model = _get_local_model(self.model_name)
            vecs: np.ndarray = model.encode(texts, normalize_embeddings=True, batch_size=32)
            return vecs.tolist()
        except Exception:
            # No embedding backend available — return zero vectors
            dim = 384  # all-MiniLM-L6-v2 dimension
            return [[0.0] * dim for _ in texts]

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
