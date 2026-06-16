"""
Simple persistent run-history store (JSON file on disk).
No external DB required — keeps SENTINEL dependency-free for local installs.
Stores the last 500 pipeline runs and maintenance records.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Optional

_RUNS_FILE = Path("./data/runs.json")
_MAINT_FILE = Path("./data/maintenance.json")
_APPROVALS_FILE = Path("./data/approvals.json")

_lock = Lock()


def _read(path: Path) -> list[dict]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def _write(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, default=str, indent=2))


# ── Pipeline runs ──────────────────────────────────────────────────────────────

def save_run(run: dict) -> None:
    with _lock:
        runs = _read(_RUNS_FILE)
        runs.insert(0, run)
        _write(_RUNS_FILE, runs[:500])


def list_runs(limit: int = 50, repo: Optional[str] = None) -> list[dict]:
    runs = _read(_RUNS_FILE)
    if repo:
        runs = [r for r in runs if r.get("repo") == repo]
    return runs[:limit]


def get_run(run_id: str) -> Optional[dict]:
    for run in _read(_RUNS_FILE):
        if run.get("run_id") == run_id:
            return run
    return None


# ── Maintenance records ────────────────────────────────────────────────────────

def save_maintenance(record: dict) -> None:
    with _lock:
        records = _read(_MAINT_FILE)
        records.insert(0, record)
        _write(_MAINT_FILE, records[:200])


def list_maintenance(limit: int = 20) -> list[dict]:
    return _read(_MAINT_FILE)[:limit]


def get_last_maintenance() -> dict[str, Any]:
    records = _read(_MAINT_FILE)
    by_agent: dict[str, dict] = {}
    for r in records:
        agent = r.get("agent", "unknown")
        if agent not in by_agent:
            by_agent[agent] = r
    return by_agent


# ── Revert commit tracking ────────────────────────────────────────────────────
# Accumulated by push-event handler; consumed (and cleared) by the nightly curator.

_REVERTS_FILE = Path("./data/reverted_commits.json")


def record_revert(sha: str) -> None:
    with _lock:
        reverts: list[str] = _read(_REVERTS_FILE)  # type: ignore[assignment]
        if sha not in reverts:
            reverts.append(sha)
        _write(_REVERTS_FILE, reverts[-500:])


def consume_reverts() -> list[str]:
    """Return all pending revert SHAs and clear the file."""
    with _lock:
        reverts: list[str] = _read(_REVERTS_FILE)  # type: ignore[assignment]
        if reverts:
            _write(_REVERTS_FILE, [])
        return reverts


# ── Pending approvals ──────────────────────────────────────────────────────────

def save_approval(approval: dict) -> None:
    approval.setdefault("id", str(uuid.uuid4()))
    approval.setdefault("created_at", datetime.utcnow().isoformat())
    approval.setdefault("status", "pending")
    with _lock:
        approvals = _read(_APPROVALS_FILE)
        approvals.insert(0, approval)
        _write(_APPROVALS_FILE, approvals[:1000])


def get_approval(approval_id: str) -> Optional[dict]:
    for a in _read(_APPROVALS_FILE):
        if a.get("id") == approval_id:
            return a
    return None


def list_approvals(status: Optional[str] = "pending") -> list[dict]:
    approvals = _read(_APPROVALS_FILE)
    if status:
        approvals = [a for a in approvals if a.get("status") == status]
    return approvals


def update_approval(approval_id: str, status: str, reviewer: str = "human") -> bool:
    with _lock:
        approvals = _read(_APPROVALS_FILE)
        for a in approvals:
            if a.get("id") == approval_id:
                a["status"] = status
                a["reviewed_by"] = reviewer
                a["reviewed_at"] = datetime.utcnow().isoformat()
                _write(_APPROVALS_FILE, approvals)
                return True
    return False
