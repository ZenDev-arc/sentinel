"""
Regression Detector

For each consolidated finding, searches the KB for past bug_fix entries that
match semantically. If similarity >= THRESHOLD, the finding is tagged as a
regression — meaning this bug was fixed before and has come back.

This is SENTINEL's institutional memory: no LLM session can do this.
"""

from __future__ import annotations

from datetime import datetime

from src.core.logging import get_logger
from src.core.state import RegressionMatch, ReviewFinding
from src.knowledge_base.models import KBEntryType
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

# Cosine similarity required to call something a regression.
# 0.82 is high enough to avoid false positives while catching real regressions.
_REGRESSION_THRESHOLD = 0.82


def detect_regressions(
    findings: list[ReviewFinding],
    repo: str,
    kb: KnowledgeBaseStore,
    threshold: float | None = None,
) -> list[ReviewFinding]:
    """
    Tag each finding that matches a past verified bug_fix KB entry.

    Searches with repo="*" so regressions are caught even if a bug
    previously appeared in a related repo or was fixed in a fork.

    threshold overrides _REGRESSION_THRESHOLD when provided (e.g. from policy).
    """
    if not findings:
        return findings

    effective_threshold = threshold if threshold is not None else _REGRESSION_THRESHOLD

    updated: list[ReviewFinding] = []
    regression_count = 0

    for finding in findings:
        query = f"{finding.title}\n{finding.description}\nfile: {finding.file_path}"

        try:
            hits = kb.search(
                query=query,
                repo="*",
                n_results=3,
                entry_type=KBEntryType.BUG_FIX,
            )
        except Exception as exc:
            log.warning(
                "regression_search_failed", finding_id=finding.id, error=str(exc)
            )
            updated.append(finding)
            continue

        match: RegressionMatch | None = None
        for hit in hits:
            if hit.similarity < effective_threshold:
                continue
            if not hit.entry.is_active():
                continue

            payload = hit.entry.payload
            patch = payload.get("patch", "")
            root_cause = payload.get("root_cause", "")
            summary = root_cause or patch
            # Keep summary short for PR comment display
            if len(summary) > 300:
                summary = summary[:300] + "…"

            match = RegressionMatch(
                kb_entry_id=hit.entry.id,
                original_pr=hit.entry.pr_number,
                original_repo=hit.entry.repo,
                original_fix_summary=summary,
                similarity=hit.similarity,
                fixed_at=hit.entry.created_at,
            )
            kb.record_use(hit.entry.id)
            log.info(
                "regression_detected",
                finding=finding.title,
                original_pr=hit.entry.pr_number,
                similarity=f"{hit.similarity:.2f}",
            )
            break

        if match:
            regression_count += 1
            updated.append(
                finding.model_copy(
                    update={
                        "is_regression": True,
                        "regression": match,
                    }
                )
            )
        else:
            updated.append(finding)

    if regression_count:
        log.warning("regressions_found", count=regression_count, repo=repo)

    return updated
