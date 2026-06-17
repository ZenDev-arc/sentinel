"""
Curator Agent (nightly)

Scans the KB for entries that should be invalidated:
  1. Linked to reverted commits — if a commit that introduced a fix was later reverted,
     the fix pattern is no longer valid.
  2. Repeatedly rejected — suggestions that humans have dismissed 3+ times.
  3. Entries whose confidence has decayed below the threshold.

Demotes or removes them, logging the reason so the drift checker can audit.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.core.config import settings
from src.core.logging import get_logger
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)


def run(kb: KnowledgeBaseStore, reverted_commits: list[str] | None = None) -> dict:
    """
    reverted_commits: list of commit SHAs that were reverted since last run.
    Returns summary dict of actions taken.
    """
    log.info("curator_agent_start")
    reverted_commits = reverted_commits or []

    entries = kb.list_all(include_archived=False)
    now = datetime.utcnow()
    decay_days = settings.KB_CONFIDENCE_DECAY_DAYS
    rejection_threshold = settings.KB_CURATOR_REJECTION_THRESHOLD
    confidence_threshold = settings.KB_CONFIDENCE_THRESHOLD

    invalidated = 0
    decayed = 0
    archived = 0

    for entry in entries:
        # 1. Reverted commit
        if entry.commit_sha and entry.commit_sha in reverted_commits:
            kb.mark_invalidated(
                entry.id,
                reason=f"Source commit {entry.commit_sha} was reverted",
            )
            invalidated += 1
            log.info(
                "entry_invalidated_revert",
                entry_id=entry.id,
                commit=entry.commit_sha,
            )
            continue

        # 2. Repeatedly rejected
        if entry.rejection_count >= rejection_threshold:
            kb.mark_invalidated(
                entry.id,
                reason=f"Rejected {entry.rejection_count} times by humans",
            )
            invalidated += 1
            log.info(
                "entry_invalidated_rejections",
                entry_id=entry.id,
                count=entry.rejection_count,
            )
            continue

        # 3. Confidence decay
        days_since = (
            (now - entry.last_used_at).days
            if entry.last_used_at
            else (now - entry.created_at).days
        )
        if days_since >= decay_days:
            new_conf = entry.decay_confidence(days_since - decay_days)
            kb.update_confidence(entry.id, new_conf)
            decayed += 1

            if new_conf < confidence_threshold:
                kb.mark_archived(
                    entry.id,
                    reason=f"Confidence decayed to {new_conf:.3f} after {days_since} days without use",
                )
                archived += 1
                log.info("entry_archived_decay", entry_id=entry.id, confidence=new_conf)

    result = {
        "invalidated": invalidated,
        "decayed": decayed,
        "archived": archived,
        "total_scanned": len(entries),
        "ran_at": now.isoformat(),
    }
    log.info("curator_agent_done", **result)
    return result
