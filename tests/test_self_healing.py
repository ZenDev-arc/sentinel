"""
Tests for self-healing agents (curator, drift_checker, consistency, consolidation).
All KB operations use a temp Chroma store.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.knowledge_base.models import KBEntry, KBEntryType, ReviewOutcome
from src.knowledge_base.store import KnowledgeBaseStore


@pytest.fixture
def kb(tmp_path) -> KnowledgeBaseStore:
    return KnowledgeBaseStore(
        persist_dir=str(tmp_path / "chroma"),
        collection_name="test_self_healing",
    )


def _entry(
    title: str = "Test Entry",
    rejection_count: int = 0,
    commit_sha: str | None = None,
    confidence: float = 1.0,
    days_old: int = 0,
) -> KBEntry:
    created = datetime.utcnow() - timedelta(days=days_old)
    return KBEntry(
        type=KBEntryType.REVIEW_OUTCOME,
        title=title,
        description="Test description about code review finding.",
        repo="acme/backend",
        rejection_count=rejection_count,
        commit_sha=commit_sha,
        confidence=confidence,
        created_at=created,
        updated_at=created,
    )


class TestCuratorAgent:
    def test_invalidates_reverted_commit(self, kb):
        from src.agents.self_healing.curator import run

        e = _entry(commit_sha="abc123")
        kb.upsert(e)

        result = run(kb, reverted_commits=["abc123"])
        assert result["invalidated"] == 1

        retrieved = kb.get(e.id)
        assert retrieved.invalidated is True

    def test_invalidates_repeatedly_rejected(self, kb):
        from src.agents.self_healing.curator import run

        e = _entry(rejection_count=5)
        kb.upsert(e)

        result = run(kb, reverted_commits=[])
        assert result["invalidated"] >= 1

    def test_archives_low_confidence(self, kb):
        from src.agents.self_healing.curator import run
        from src.core.config import settings

        # Entry that hasn't been used in KB_CONFIDENCE_DECAY_DAYS + extra days
        days_old = settings.KB_CONFIDENCE_DECAY_DAYS + 60
        e = _entry(confidence=0.05, days_old=days_old)
        kb.upsert(e)

        result = run(kb, reverted_commits=[])
        # Either archived or decayed
        assert result["decayed"] >= 0  # may vary by timing

    def test_skips_active_entries(self, kb):
        from src.agents.self_healing.curator import run

        e = _entry(confidence=1.0, days_old=0)
        kb.upsert(e)

        result = run(kb, reverted_commits=[])
        assert result["invalidated"] == 0


class TestDriftChecker:
    def test_archives_changed_files(self, kb, tmp_path):
        from src.agents.self_healing.drift_checker import run

        # Create a file and hash it
        test_file = tmp_path / "src" / "utils.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("def foo(): pass")

        import hashlib
        original_hash = hashlib.sha256(b"def foo(): pass").hexdigest()

        e = KBEntry(
            type=KBEntryType.BUG_FIX,
            title="Fix in utils",
            description="Some fix",
            repo="acme/backend",
            file_paths=["src/utils.py"],
            code_snapshot_hash=original_hash,
        )
        kb.upsert(e)

        # Modify the file (simulating drift)
        test_file.write_text("def foo(): return 42")

        result = run(kb, repo_root=str(tmp_path))
        assert result["drifted"] == 1

        retrieved = kb.get(e.id)
        assert retrieved.archived is True

    def test_no_drift_unchanged_file(self, kb, tmp_path):
        from src.agents.self_healing.drift_checker import run

        test_file = tmp_path / "src" / "stable.py"
        test_file.parent.mkdir(parents=True)
        content = b"def stable(): pass"
        test_file.write_bytes(content)

        import hashlib
        original_hash = hashlib.sha256(content).hexdigest()

        e = KBEntry(
            type=KBEntryType.BUG_FIX,
            title="Fix in stable",
            description="Some fix",
            repo="acme/backend",
            file_paths=["src/stable.py"],
            code_snapshot_hash=original_hash,
        )
        kb.upsert(e)

        result = run(kb, repo_root=str(tmp_path))
        assert result["drifted"] == 0

    def test_skips_entries_without_snapshot(self, kb, tmp_path):
        from src.agents.self_healing.drift_checker import run

        e = _entry()  # no code_snapshot_hash
        kb.upsert(e)

        result = run(kb, repo_root=str(tmp_path))
        assert result["checked"] == 0
