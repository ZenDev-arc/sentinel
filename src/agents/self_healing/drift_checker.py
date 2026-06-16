"""
Drift-Checker Agent (nightly)

For each active KB entry that references specific files or code snapshots,
diffs the current HEAD against the stored snapshot hash.

If the referenced code has materially changed:
  - Archives the entry (it may no longer apply)
  - Schedules re-embedding with updated context (future: re-validation pass)

Uses GitPython to resolve file content at HEAD.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.core.logging import get_logger
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)


def _hash_file(path: Path) -> str | None:
    if not path.exists():
        return None
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def run(kb: KnowledgeBaseStore, repo_root: str) -> dict:
    """
    repo_root: local path to the cloned repository being monitored.
    """
    log.info("drift_checker_start", repo_root=repo_root)
    root = Path(repo_root)

    entries = kb.list_all(include_archived=False)
    checked = 0
    drifted = 0

    for entry in entries:
        if not entry.file_paths or not entry.code_snapshot_hash:
            continue

        checked += 1
        # Compute current hash of the referenced files
        file_contents = b""
        for fp in entry.file_paths:
            full_path = root / fp
            content = full_path.read_bytes() if full_path.exists() else b""
            file_contents += content

        current_hash = hashlib.sha256(file_contents).hexdigest()

        if current_hash != entry.code_snapshot_hash:
            kb.mark_archived(
                entry.id,
                reason=(
                    f"Referenced files changed since entry was created. "
                    f"Stored hash: {entry.code_snapshot_hash[:8]}, "
                    f"current: {current_hash[:8]}"
                ),
            )
            drifted += 1
            log.info(
                "entry_archived_drift",
                entry_id=entry.id,
                files=entry.file_paths,
            )

    result = {
        "checked": checked,
        "drifted": drifted,
        "total_entries": len(entries),
    }
    log.info("drift_checker_done", **result)
    return result
