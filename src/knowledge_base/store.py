"""
Chroma-backed Knowledge Base store.

Every KB entry is stored as a Chroma document with:
  - id: KBEntry.id
  - embedding: SBERT vector of (title + description + payload summary)
  - document: JSON-serialised KBEntry
  - metadata: flat fields for fast filtering (repo, type, archived, confidence, …)
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.core.config import settings as app_settings
from src.core.logging import get_logger
from src.knowledge_base.embedder import Embedder
from src.knowledge_base.models import (
    KBEntry,
    KBEntryType,
    KBSearchResult,
    ReviewOutcome,
)

log = get_logger(__name__)

_MIN_SIMILARITY = 0.5


class KnowledgeBaseStore:
    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        self._persist_dir = persist_dir or app_settings.CHROMA_PERSIST_DIR
        self._collection_name = collection_name or app_settings.CHROMA_COLLECTION
        self._embedder = Embedder()
        self._client: chromadb.ClientAPI | None = None
        self._collection = None

    _unavailable: bool = (
        False  # class-level flag so all instances skip after first failure
    )

    def _ensure_connected(self) -> None:
        if self._client is not None and self._collection is not None:
            return
        if KnowledgeBaseStore._unavailable:
            raise RuntimeError("ChromaDB unavailable (disabled after prior failure)")
        try:
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            log.info("kb_store_connected", collection=self._collection_name)
        except Exception as exc:
            self._client = (
                None  # reset so next call retries rather than returning early
            )
            self._collection = None
            KnowledgeBaseStore._unavailable = True
            log.warning("kb_store_unavailable", error=str(exc))
            raise

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert(self, entry: KBEntry) -> None:
        try:
            self._ensure_connected()
        except Exception:
            return
        text = self._embedder.build_kb_text(
            entry.title, entry.description, entry.payload
        )
        embedding = self._embedder.embed(text)
        self._collection.upsert(
            ids=[entry.id],
            embeddings=[embedding],
            documents=[entry.model_dump_json()],
            metadatas=[self._meta(entry)],
        )
        log.info("kb_upserted", id=entry.id, type=entry.type, title=entry.title)

    def upsert_batch(self, entries: list[KBEntry]) -> None:
        if not entries:
            return
        try:
            self._ensure_connected()
        except Exception:
            return
        texts = [
            self._embedder.build_kb_text(e.title, e.description, e.payload)
            for e in entries
        ]
        embeddings = self._embedder.embed_batch(texts)
        self._collection.upsert(
            ids=[e.id for e in entries],
            embeddings=embeddings,
            documents=[e.model_dump_json() for e in entries],
            metadatas=[self._meta(e) for e in entries],
        )

    def delete(self, entry_id: str) -> None:
        try:
            self._ensure_connected()
        except Exception:
            return
        self._collection.delete(ids=[entry_id])

    # ── Read ──────────────────────────────────────────────────────────────────

    def get(self, entry_id: str) -> Optional[KBEntry]:
        try:
            self._ensure_connected()
        except Exception:
            return None
        result = self._collection.get(ids=[entry_id], include=["documents"])
        if not result["documents"]:
            return None
        return KBEntry.model_validate_json(result["documents"][0])

    def search(
        self,
        query: str,
        repo: str,
        n_results: int = 5,
        entry_type: Optional[KBEntryType] = None,
    ) -> list[KBSearchResult]:
        try:
            self._ensure_connected()
            embedding = self._embedder.embed(query)
        except Exception as exc:
            log.warning("kb_search_skipped", error=str(exc))
            return []

        where: dict = {"$and": [{"archived": False}, {"invalidated": False}]}
        if entry_type:
            where["$and"].append({"type": entry_type.value})

        try:
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=min(n_results * 2, max(1, self._collection.count())),
                where=where,
                include=["documents", "distances", "metadatas"],
            )
        except Exception:
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=min(n_results, max(1, self._collection.count())),
                include=["documents", "distances"],
            )

        hits: list[KBSearchResult] = []
        docs = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc_json, dist in zip(docs, distances):
            similarity = 1.0 - dist
            if similarity < _MIN_SIMILARITY:
                continue
            entry = KBEntry.model_validate_json(doc_json)
            if entry.repo != repo and repo != "*":
                continue
            hits.append(
                KBSearchResult(entry=entry, similarity=similarity, distance=dist)
            )

        hits.sort(key=lambda h: h.similarity, reverse=True)
        return hits[:n_results]

    def list_all(
        self,
        repo: Optional[str] = None,
        include_archived: bool = False,
    ) -> list[KBEntry]:
        self._ensure_connected()
        count = self._collection.count()
        if count == 0:
            return []
        result = self._collection.get(
            include=["documents"],
            limit=count,
        )
        entries = [KBEntry.model_validate_json(d) for d in result["documents"]]
        if not include_archived:
            entries = [e for e in entries if not e.archived and not e.invalidated]
        if repo:
            entries = [e for e in entries if e.repo == repo]
        return entries

    # ── Mutation helpers for self-healing agents ──────────────────────────────

    def mark_archived(self, entry_id: str, reason: str = "") -> None:
        entry = self.get(entry_id)
        if entry is None:
            return
        entry.archived = True
        entry.invalidation_reason = reason
        entry.updated_at = datetime.utcnow()
        self.upsert(entry)

    def mark_invalidated(self, entry_id: str, reason: str) -> None:
        entry = self.get(entry_id)
        if entry is None:
            return
        entry.invalidated = True
        entry.invalidation_reason = reason
        entry.updated_at = datetime.utcnow()
        self.upsert(entry)

    def record_use(self, entry_id: str) -> None:
        entry = self.get(entry_id)
        if entry is None:
            return
        entry.use_count += 1
        entry.last_used_at = datetime.utcnow()
        entry.updated_at = datetime.utcnow()
        self.upsert(entry)

    def record_outcome(self, entry_id: str, outcome: ReviewOutcome) -> None:
        entry = self.get(entry_id)
        if entry is None:
            return
        entry.outcome = outcome
        if outcome == ReviewOutcome.REJECTED:
            entry.rejection_count += 1
        entry.updated_at = datetime.utcnow()
        self.upsert(entry)

    def update_confidence(self, entry_id: str, confidence: float) -> None:
        entry = self.get(entry_id)
        if entry is None:
            return
        entry.confidence = max(0.0, min(1.0, confidence))
        entry.updated_at = datetime.utcnow()
        self.upsert(entry)

    def count(self) -> int:
        self._ensure_connected()
        return self._collection.count()

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _meta(entry: KBEntry) -> dict:
        return {
            "repo": entry.repo,
            "type": entry.type.value,
            "archived": entry.archived,
            "invalidated": entry.invalidated,
            "confidence": entry.confidence,
            "rejection_count": entry.rejection_count,
            "use_count": entry.use_count,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
        }
