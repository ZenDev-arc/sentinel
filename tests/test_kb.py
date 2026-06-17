"""
Tests for the Knowledge Base store and embedder.
Uses an in-memory Chroma client (no disk I/O).
"""

from __future__ import annotations

import pytest

from src.knowledge_base.embedder import Embedder
from src.knowledge_base.models import KBEntry, KBEntryType, ReviewOutcome
from src.knowledge_base.store import KnowledgeBaseStore


@pytest.fixture
def kb(tmp_path) -> KnowledgeBaseStore:
    store = KnowledgeBaseStore(
        persist_dir=str(tmp_path / "chroma"),
        collection_name="test_collection",
    )
    return store


@pytest.fixture
def sample_entry() -> KBEntry:
    return KBEntry(
        type=KBEntryType.BUG_FIX,
        title="Fix: null pointer in UserService.getById",
        description="getById returned null without checking if user exists in DB first.",
        payload={
            "failing_test": "test_get_user_by_id_not_found",
            "root_cause": "Missing null check before accessing user.profile",
            "patch": "--- a/src/user_service.py\n+++ b/src/user_service.py\n@@ -10 +10 @@\n- return user.profile\n+ return user.profile if user else None",
            "affected_files": ["src/user_service.py"],
            "patch_verified": True,
        },
        repo="acme/backend",
        pr_number=42,
        commit_sha="abc123",
        file_paths=["src/user_service.py"],
    )


class TestKBStoreUpsertAndGet:
    def test_upsert_and_get(self, kb, sample_entry):
        kb.upsert(sample_entry)
        retrieved = kb.get(sample_entry.id)
        assert retrieved is not None
        assert retrieved.id == sample_entry.id
        assert retrieved.title == sample_entry.title

    def test_get_nonexistent(self, kb):
        assert kb.get("nonexistent-id") is None

    def test_upsert_updates_existing(self, kb, sample_entry):
        kb.upsert(sample_entry)
        updated = sample_entry.model_copy(update={"title": "Updated title"})
        kb.upsert(updated)
        retrieved = kb.get(sample_entry.id)
        assert retrieved.title == "Updated title"

    def test_count(self, kb, sample_entry):
        assert kb.count() == 0
        kb.upsert(sample_entry)
        assert kb.count() == 1


class TestKBStoreSearch:
    def test_search_finds_relevant(self, kb, sample_entry):
        kb.upsert(sample_entry)
        results = kb.search(
            query="null pointer user service get by id",
            repo="acme/backend",
            n_results=5,
        )
        assert len(results) >= 1
        assert any(r.entry.id == sample_entry.id for r in results)

    def test_search_by_type_filter(self, kb, sample_entry):
        kb.upsert(sample_entry)
        results = kb.search(
            query="user service",
            repo="acme/backend",
            n_results=5,
            entry_type=KBEntryType.BUG_FIX,
        )
        assert all(r.entry.type == KBEntryType.BUG_FIX for r in results)

    def test_search_excludes_archived(self, kb, sample_entry):
        kb.upsert(sample_entry)
        kb.mark_archived(sample_entry.id, reason="test")
        results = kb.search(
            query="null pointer",
            repo="acme/backend",
            n_results=5,
        )
        assert not any(r.entry.id == sample_entry.id for r in results)


class TestKBSelfHealingMutations:
    def test_mark_archived(self, kb, sample_entry):
        kb.upsert(sample_entry)
        kb.mark_archived(sample_entry.id, reason="stale")
        entry = kb.get(sample_entry.id)
        assert entry.archived is True
        assert entry.invalidation_reason == "stale"

    def test_mark_invalidated(self, kb, sample_entry):
        kb.upsert(sample_entry)
        kb.mark_invalidated(sample_entry.id, reason="reverted")
        entry = kb.get(sample_entry.id)
        assert entry.invalidated is True

    def test_record_outcome_rejection(self, kb, sample_entry):
        kb.upsert(sample_entry)
        kb.record_outcome(sample_entry.id, ReviewOutcome.REJECTED)
        entry = kb.get(sample_entry.id)
        assert entry.rejection_count == 1
        assert entry.outcome == ReviewOutcome.REJECTED

    def test_record_use_increments(self, kb, sample_entry):
        kb.upsert(sample_entry)
        kb.record_use(sample_entry.id)
        kb.record_use(sample_entry.id)
        entry = kb.get(sample_entry.id)
        assert entry.use_count == 2

    def test_confidence_decay(self):
        entry = KBEntry(
            type=KBEntryType.CODEBASE_PATTERN,
            title="Test",
            description="Test",
            repo="test/repo",
        )
        assert entry.confidence == 1.0
        decayed = entry.decay_confidence(days_since_use=100)
        assert 0.0 < decayed < 1.0

    def test_is_active(self, sample_entry):
        assert sample_entry.is_active() is True
        archived = sample_entry.model_copy(update={"archived": True})
        assert archived.is_active() is False


class TestEmbedder:
    def test_embed_returns_vector(self):
        embedder = Embedder()
        vec = embedder.embed("null pointer exception in user service")
        assert isinstance(vec, list)
        assert len(vec) > 0
        assert all(isinstance(v, float) for v in vec)

    def test_embed_batch(self):
        embedder = Embedder()
        texts = [
            "security vulnerability",
            "performance N+1 query",
            "style naming convention",
        ]
        vecs = embedder.embed_batch(texts)
        assert len(vecs) == 3
        assert all(len(v) == len(vecs[0]) for v in vecs)

    def test_build_kb_text(self):
        text = Embedder.build_kb_text(
            title="Fix null pointer",
            description="User was not checked before access",
            payload={
                "root_cause": "Missing guard",
                "patch": "if user is None: return None",
            },
        )
        assert "Fix null pointer" in text
        assert "Missing guard" in text
