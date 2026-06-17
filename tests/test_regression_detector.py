"""
Tests for the regression detector.

Uses a lightweight stub KB (no SBERT/Chroma) to avoid the Protobuf version
conflict in the test environment.  The stub controls similarity scores
directly so we can test the detector's branching logic precisely.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.core.regression_detector import _REGRESSION_THRESHOLD, detect_regressions
from src.core.state import FindingCategory, FindingSeverity, ReviewFinding
from src.knowledge_base.models import KBEntry, KBEntryType

# ── Stub KB ───────────────────────────────────────────────────────────────────


class _KBSearchResult:
    """Minimal stand-in for KBSearchResult."""

    def __init__(self, entry: KBEntry, similarity: float):
        self.entry = entry
        self.similarity = similarity


class StubKB:
    """
    A KB stub that returns pre-programmed search results.
    Tracks record_use() calls so we can assert on them.
    """

    def __init__(self, results: list[_KBSearchResult] | None = None):
        self._results: list[_KBSearchResult] = results or []
        self.used_ids: list[str] = []

    def search(self, query: str, repo: str, n_results: int, entry_type=None):
        return self._results

    def record_use(self, entry_id: str):
        self.used_ids.append(entry_id)


def _make_entry(
    title: str = "SQL injection in login",
    description: str = "Unsanitised input passed to raw query",
    repo: str = "acme/backend",
    pr_number: int = 10,
) -> KBEntry:
    return KBEntry(
        type=KBEntryType.BUG_FIX,
        title=title,
        description=description,
        payload={
            "root_cause": description,
            "patch": "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1 +1 @@\n-bad\n+good",
            "patch_verified": True,
            "affected_files": ["src/auth.py"],
        },
        repo=repo,
        pr_number=pr_number,
        file_paths=["src/auth.py"],
    )


def _finding(
    title: str = "SQL injection in login",
    description: str = "desc",
    file_path: str = "src/auth.py",
) -> ReviewFinding:
    return ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.HIGH,
        file_path=file_path,
        title=title,
        description=description,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDetectRegressions:
    def test_empty_findings_returns_empty(self):
        kb = StubKB()
        result = detect_regressions([], "acme/backend", kb)
        assert result == []

    def test_no_search_results_no_regression(self):
        kb = StubKB(results=[])
        result = detect_regressions([_finding()], "acme/backend", kb)
        assert result[0].is_regression is False
        assert result[0].regression is None

    def test_high_similarity_flags_regression(self):
        entry = _make_entry()
        kb = StubKB(results=[_KBSearchResult(entry, similarity=0.92)])

        result = detect_regressions([_finding()], "acme/backend", kb)

        assert result[0].is_regression is True
        rm = result[0].regression
        assert rm is not None
        assert rm.kb_entry_id == entry.id
        assert rm.original_pr == 10
        assert rm.similarity == 0.92
        assert rm.original_repo == "acme/backend"

    def test_below_threshold_not_flagged(self):
        entry = _make_entry()
        # similarity just below the default threshold
        kb = StubKB(
            results=[_KBSearchResult(entry, similarity=_REGRESSION_THRESHOLD - 0.01)]
        )

        result = detect_regressions([_finding()], "acme/backend", kb)
        assert result[0].is_regression is False

    def test_exactly_at_threshold_is_flagged(self):
        entry = _make_entry()
        kb = StubKB(results=[_KBSearchResult(entry, similarity=_REGRESSION_THRESHOLD)])

        result = detect_regressions([_finding()], "acme/backend", kb)
        assert result[0].is_regression is True

    def test_archived_entry_not_flagged(self):
        entry = _make_entry()
        entry = entry.model_copy(update={"archived": True})
        kb = StubKB(results=[_KBSearchResult(entry, similarity=0.95)])

        result = detect_regressions([_finding()], "acme/backend", kb)
        assert result[0].is_regression is False

    def test_custom_threshold_overrides_default(self):
        entry = _make_entry()
        # similarity is above the default but below the custom threshold
        similarity = _REGRESSION_THRESHOLD + 0.05
        kb = StubKB(results=[_KBSearchResult(entry, similarity=similarity)])

        result_default = detect_regressions([_finding()], "acme/backend", kb)
        assert result_default[0].is_regression is True

        result_strict = detect_regressions(
            [_finding()], "acme/backend", kb, threshold=1.0
        )
        assert result_strict[0].is_regression is False

    def test_record_use_called_on_match(self):
        entry = _make_entry()
        kb = StubKB(results=[_KBSearchResult(entry, similarity=0.90)])

        detect_regressions([_finding()], "acme/backend", kb)

        assert entry.id in kb.used_ids

    def test_record_use_not_called_when_no_match(self):
        entry = _make_entry()
        kb = StubKB(results=[_KBSearchResult(entry, similarity=0.50)])

        detect_regressions([_finding()], "acme/backend", kb)

        assert kb.used_ids == []

    def test_cross_repo_original_repo_preserved(self):
        entry = _make_entry(repo="other-org/other-repo")
        kb = StubKB(results=[_KBSearchResult(entry, similarity=0.91)])

        result = detect_regressions([_finding()], "acme/backend", kb)

        assert result[0].is_regression is True
        assert result[0].regression.original_repo == "other-org/other-repo"

    def test_multiple_findings_only_matching_flagged(self):
        entry = _make_entry()
        # First finding gets a high-similarity hit; second gets nothing
        call_count = 0

        class SelectiveKB:
            used_ids: list = []

            def search(self, query, repo, n_results, entry_type=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return [_KBSearchResult(entry, similarity=0.90)]
                return []

            def record_use(self, entry_id):
                self.used_ids.append(entry_id)

        kb = SelectiveKB()
        findings = [
            _finding("SQL injection", "desc1"),
            _finding("Missing rate limit", "desc2"),
        ]
        result = detect_regressions(findings, "acme/backend", kb)

        assert result[0].is_regression is True
        assert result[1].is_regression is False

    def test_kb_search_failure_does_not_crash(self):
        """A KB search error is swallowed — finding passes through untagged."""

        class BrokenKB:
            def search(self, *args, **kwargs):
                raise RuntimeError("chroma unavailable")

            def record_use(self, *args):
                pass

        result = detect_regressions([_finding()], "acme/backend", BrokenKB())
        assert len(result) == 1
        assert result[0].is_regression is False

    def test_only_first_hit_above_threshold_used(self):
        """When multiple hits pass the threshold, only the best one is used."""
        entry1 = _make_entry(title="entry 1", pr_number=1)
        entry2 = _make_entry(title="entry 2", pr_number=2)
        kb = StubKB(
            results=[
                _KBSearchResult(entry1, similarity=0.95),
                _KBSearchResult(entry2, similarity=0.90),
            ]
        )

        result = detect_regressions([_finding()], "acme/backend", kb)
        assert result[0].regression.original_pr == 1  # first hit wins
        assert len(kb.used_ids) == 1  # only first hit recorded
