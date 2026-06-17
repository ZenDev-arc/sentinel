"""
Orchestrator Agent

Entry point of the pipeline. After all swarms have run, the Orchestrator:
  1. Assembles the final state
  2. Embeds new findings and fixes into the Knowledge Base
  3. Posts the consolidated PR comment via the GitHub client

The actual sequencing/routing is done by the LangGraph graph (core/pipeline.py).
This module provides the post-processing step that fires last.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from src.core.logging import get_logger
from src.core.state import PipelineState, PipelineStatus
from src.knowledge_base.models import (BugFixPayload, KBEntry, KBEntryType,
                                       ReviewOutcome, ReviewOutcomePayload)
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)


def _snapshot_hash(file_paths: list[str]) -> str:
    return hashlib.sha256(",".join(sorted(file_paths)).encode()).hexdigest()


def embed_outcomes(state: PipelineState, kb: KnowledgeBaseStore) -> None:
    """Persist this run's findings and fixes back into the KB."""
    if not state.pr:
        return

    repo = state.pr.repo_full_name

    # Embed consolidated review findings
    for finding in state.consolidated_findings:
        if not finding.description:
            continue
        entry = KBEntry(
            type=KBEntryType.REVIEW_OUTCOME,
            title=finding.title,
            description=finding.description,
            payload=ReviewOutcomePayload(
                category=finding.category.value,
                severity=finding.severity.value,
                suggestion=finding.suggestion,
                outcome=ReviewOutcome.PENDING,
            ).model_dump(),
            repo=repo,
            pr_number=state.pr.pr_number,
            commit_sha=state.pr.head_sha,
            file_paths=([finding.file_path] if finding.file_path else []),
            code_snapshot_hash=_snapshot_hash(state.pr.files_changed),
        )
        kb.upsert(entry)

    # Embed verified bug fixes
    for report in state.bug_reports:
        if not report.verified or not report.selected_patch:
            continue
        entry = KBEntry(
            type=KBEntryType.BUG_FIX,
            title=f"Fix: {report.failing_test}",
            description=report.root_cause,
            payload=BugFixPayload(
                failing_test=report.failing_test,
                root_cause=report.root_cause,
                patch=report.selected_patch.get("patch", ""),
                affected_files=report.affected_files,
                patch_verified=True,
            ).model_dump(),
            repo=repo,
            pr_number=state.pr.pr_number,
            commit_sha=state.pr.head_sha,
            file_paths=report.affected_files,
            code_snapshot_hash=_snapshot_hash(report.affected_files),
        )
        kb.upsert(entry)

    log.info(
        "kb_updated",
        findings=len(state.consolidated_findings),
        bug_fixes=sum(1 for r in state.bug_reports if r.verified),
    )


def run(state: PipelineState, kb: KnowledgeBaseStore) -> dict:
    log.info(
        "orchestrator_finalise",
        run_id=state.run_id,
        pr=state.pr.pr_number if state.pr else None,
    )

    # Persist learnings
    try:
        embed_outcomes(state, kb)
    except Exception as exc:
        log.warning("kb_embed_failed", error=str(exc))

    return {"status": PipelineStatus.DONE}
