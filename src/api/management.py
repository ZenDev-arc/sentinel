"""
Management API — powers the SENTINEL dashboard.

Endpoints:
  GET  /api/status              — overall system health
  GET  /api/runs                — recent pipeline runs
  GET  /api/runs/{run_id}       — single run detail
  GET  /api/kb/stats            — knowledge base health metrics
  GET  /api/approvals           — pending human-required fixes
  POST /api/approvals/{id}/approve
  POST /api/approvals/{id}/reject
  GET  /api/agents/status       — last maintenance run per agent
  POST /api/maintenance/trigger — kick off manual maintenance run
  POST /api/pipeline/trigger    — run pipeline on a specific PR
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from src.api.store import (
    get_approval,
    get_last_maintenance,
    get_patterns,
    get_run,
    list_approvals,
    list_maintenance,
    list_runs,
    save_maintenance,
    save_run,
    update_approval,
)
from src.core.config import settings
from src.core.logging import get_logger
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)
router = APIRouter(prefix="/api", tags=["management"])

_kb: Optional[KnowledgeBaseStore] = None


def _get_kb() -> KnowledgeBaseStore:
    global _kb
    if _kb is None:
        _kb = KnowledgeBaseStore()
    return _kb


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_status() -> dict:
    kb = _get_kb()
    try:
        kb_count = kb.count()
        kb_ok = True
    except Exception:
        kb_count = 0
        kb_ok = False

    recent_runs = list_runs(limit=5)
    last_run_status = recent_runs[0].get("status") if recent_runs else None

    return {
        "status": "healthy" if kb_ok else "degraded",
        "version": "0.1.3",
        "kb": {"ok": kb_ok, "entries": kb_count},
        "last_run": {
            "status": last_run_status,
            "ran_at": recent_runs[0].get("completed_at") if recent_runs else None,
        },
        "llm_provider": settings.LLM_PROVIDER,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Pipeline runs ──────────────────────────────────────────────────────────────

@router.get("/runs")
async def get_runs(limit: int = 50, repo: Optional[str] = None) -> dict:
    runs = list_runs(limit=limit, repo=repo)
    return {"runs": runs, "total": len(runs)}


@router.get("/runs/{run_id}")
async def get_run_detail(run_id: str) -> dict:
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ── Knowledge Base stats ───────────────────────────────────────────────────────

@router.get("/kb/stats")
async def get_kb_stats() -> dict:
    kb = _get_kb()
    try:
        all_entries = kb.list_all(include_archived=True)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"KB unavailable: {exc}")

    total = len(all_entries)
    active = sum(1 for e in all_entries if e.is_active())
    archived = sum(1 for e in all_entries if e.archived)
    invalidated = sum(1 for e in all_entries if e.invalidated)
    superseded = sum(1 for e in all_entries if e.superseded_by)

    by_type: dict[str, int] = {}
    for e in all_entries:
        if e.is_active():
            by_type[e.type.value] = by_type.get(e.type.value, 0) + 1

    # Confidence distribution of active entries
    active_entries = [e for e in all_entries if e.is_active()]
    if active_entries:
        avg_confidence = sum(e.confidence for e in active_entries) / len(active_entries)
        high_conf = sum(1 for e in active_entries if e.confidence >= 0.7)
        med_conf = sum(1 for e in active_entries if 0.4 <= e.confidence < 0.7)
        low_conf = sum(1 for e in active_entries if e.confidence < 0.4)
    else:
        avg_confidence = 0.0
        high_conf = med_conf = low_conf = 0

    # Most-used entries
    top_used = sorted(active_entries, key=lambda e: e.use_count, reverse=True)[:5]

    return {
        "total": total,
        "active": active,
        "archived": archived,
        "invalidated": invalidated,
        "superseded": superseded,
        "by_type": by_type,
        "confidence": {
            "average": round(avg_confidence, 3),
            "high": high_conf,
            "medium": med_conf,
            "low": low_conf,
        },
        "top_used": [
            {
                "id": e.id,
                "title": e.title,
                "type": e.type.value,
                "use_count": e.use_count,
                "confidence": round(e.confidence, 3),
            }
            for e in top_used
        ],
    }


# ── Approvals ─────────────────────────────────────────────────────────────────

@router.get("/approvals")
async def get_approvals(status: Optional[str] = "pending") -> dict:
    approvals = list_approvals(status=status)
    return {"approvals": approvals, "total": len(approvals)}


class ApprovalAction(BaseModel):
    reviewer: str = "human"


@router.post("/approvals/{approval_id}/approve")
async def approve_fix(
    approval_id: str, body: ApprovalAction, background_tasks: BackgroundTasks
) -> dict:
    approval = get_approval(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    ok = update_approval(approval_id, "approved", reviewer=body.reviewer)
    if not ok:
        raise HTTPException(status_code=404, detail="Approval not found")

    log.info("fix_approved", approval_id=approval_id, reviewer=body.reviewer)
    background_tasks.add_task(_commit_approved_fix, approval, body.reviewer)
    return {"status": "approved", "id": approval_id}


async def _commit_approved_fix(approval: dict, reviewer: str) -> None:
    """Commit the approved patch to the PR branch via the Git Data API."""
    from src.core.state import FixClassification, ProposedFix
    from src.integrations.github_client import GitHubClient

    repo = approval.get("repo", "")
    pr_number = approval.get("pr", 0)
    if not repo or not pr_number:
        log.warning("commit_approved_fix_missing_pr", approval_id=approval.get("id"))
        return

    try:
        gh = GitHubClient()
        pr = await asyncio.to_thread(lambda: gh.get_repo(repo).get_pull(pr_number))
        branch = pr.head.ref

        fix = ProposedFix(
            id=approval["id"],
            description=approval.get("description", ""),
            patch=approval.get("patch", ""),
            affected_files=approval.get("affected_files", []),
            classification=FixClassification(
                approval.get("classification", FixClassification.HUMAN_REQUIRED.value)
            ),
            rationale=approval.get("rationale", ""),
        )

        commit_sha = await asyncio.to_thread(
            gh.commit_fix,
            repo,
            fix,
            branch,
            f"[SENTINEL] {fix.description}\n\nApproved by: {reviewer}\n\n{fix.rationale}",
        )

        if commit_sha:
            log.info("approved_fix_committed", sha=commit_sha[:8], repo=repo, pr=pr_number)
        else:
            log.warning("approved_fix_commit_failed", repo=repo, pr=pr_number)

    except Exception as exc:
        log.error(
            "approved_fix_commit_error",
            error=str(exc),
            approval_id=approval.get("id"),
        )


@router.get("/patterns")
async def get_cross_pr_patterns() -> dict:
    patterns = get_patterns()
    return {"patterns": patterns, "total": len(patterns)}


@router.post("/approvals/{approval_id}/reject")
async def reject_fix(approval_id: str, body: ApprovalAction) -> dict:
    ok = update_approval(approval_id, "rejected", reviewer=body.reviewer)
    if not ok:
        raise HTTPException(status_code=404, detail="Approval not found")
    log.info("fix_rejected", approval_id=approval_id, reviewer=body.reviewer)
    return {"status": "rejected", "id": approval_id}


# ── Agent / maintenance status ─────────────────────────────────────────────────

@router.get("/agents/status")
async def get_agent_status() -> dict:
    last = get_last_maintenance()
    recent = list_maintenance(limit=10)

    agents = [
        {
            "name": "Curator",
            "id": "curator",
            "role": "Removes stale, reverted, or repeatedly-rejected KB entries",
            "schedule": "Nightly 02:00 UTC",
            "swarm": "self_healing",
            "last_run": last.get("curator", {}).get("ran_at"),
            "last_result": last.get("curator", {}),
        },
        {
            "name": "Drift-Checker",
            "id": "drift_checker",
            "role": "Archives entries whose referenced code has materially changed",
            "schedule": "Nightly 02:15 UTC",
            "swarm": "self_healing",
            "last_run": last.get("drift_checker", {}).get("ran_at"),
            "last_result": last.get("drift_checker", {}),
        },
        {
            "name": "Consistency",
            "id": "consistency",
            "role": "Detects and resolves contradictions between KB entries",
            "schedule": "Weekly Sunday 03:00 UTC",
            "swarm": "self_healing",
            "last_run": last.get("consistency", {}).get("ran_at"),
            "last_result": last.get("consistency", {}),
        },
        {
            "name": "Consolidation",
            "id": "consolidation",
            "role": "Clusters near-duplicate entries into generalised patterns",
            "schedule": "Weekly Sunday 03:30 UTC",
            "swarm": "self_healing",
            "last_run": last.get("consolidation", {}).get("ran_at"),
            "last_result": last.get("consolidation", {}),
        },
        {
            "name": "Pattern Detector",
            "id": "pattern_detector",
            "role": "Surfaces recurring cross-PR issues for team-level attention",
            "schedule": "Weekly Sunday 04:00 UTC",
            "swarm": "self_healing",
            "last_run": last.get("pattern_detector", {}).get("ran_at"),
            "last_result": last.get("pattern_detector", {}),
        },
    ]
    return {
        "agents": agents,
        "recent_maintenance": recent,
    }


# ── Maintenance trigger ────────────────────────────────────────────────────────

class MaintenanceTrigger(BaseModel):
    agent: str = "all"  # "all" | "curator" | "drift_checker" | "consistency" | "consolidation"
    repo_root: str = "."


@router.post("/maintenance/trigger")
async def trigger_maintenance(
    body: MaintenanceTrigger, background_tasks: BackgroundTasks
) -> dict:
    background_tasks.add_task(_run_maintenance, body.agent, body.repo_root)
    return {"status": "triggered", "agent": body.agent}


async def _run_maintenance(agent: str, repo_root: str) -> None:
    from src.agents.self_healing import consolidation, consistency, curator, drift_checker, pattern_detector
    from datetime import datetime

    kb = _get_kb()
    ran_at = datetime.utcnow().isoformat()

    def _record(name: str, result: dict) -> None:
        save_maintenance({"agent": name, "ran_at": ran_at, **result})

    if agent in ("all", "curator"):
        try:
            result = curator.run(kb)
            _record("curator", result)
        except Exception as exc:
            _record("curator", {"error": str(exc)})

    if agent in ("all", "drift_checker"):
        try:
            result = drift_checker.run(kb, repo_root)
            _record("drift_checker", result)
        except Exception as exc:
            _record("drift_checker", {"error": str(exc)})

    if agent in ("all", "consistency"):
        try:
            result = consistency.run(kb)
            _record("consistency", result)
        except Exception as exc:
            _record("consistency", {"error": str(exc)})

    if agent in ("all", "consolidation"):
        try:
            result = consolidation.run(kb)
            _record("consolidation", result)
        except Exception as exc:
            _record("consolidation", {"error": str(exc)})

    if agent in ("all", "pattern_detector"):
        try:
            result = pattern_detector.run(kb)
            _record("pattern_detector", result)
        except Exception as exc:
            _record("pattern_detector", {"error": str(exc)})

    log.info("manual_maintenance_done", agent=agent)


# ── Pipeline manual trigger ────────────────────────────────────────────────────

class PipelineTrigger(BaseModel):
    repo: str
    pr_number: int


@router.post("/pipeline/trigger")
async def trigger_pipeline(body: PipelineTrigger, background_tasks: BackgroundTasks) -> dict:
    background_tasks.add_task(_run_pipeline, body.repo, body.pr_number)
    return {"status": "triggered", "repo": body.repo, "pr": body.pr_number}


async def _run_pipeline(repo: str, pr_number: int) -> None:
    from src.core.pipeline import compile_pipeline
    from src.core.state import PipelineState
    from src.integrations.git_utils import fetch_pr_diff, fetch_pr_files
    from src.integrations.github_client import GitHubClient

    started_at = datetime.utcnow().isoformat()
    run_record: dict = {
        "repo": repo,
        "pr": pr_number,
        "started_at": started_at,
        "status": "running",
    }

    try:
        gh = GitHubClient()
        pr_meta = gh.fetch_pr_metadata(repo, pr_number)
        diff = await asyncio.to_thread(fetch_pr_diff, repo, pr_number)
        files = await asyncio.to_thread(fetch_pr_files, repo, pr_number)
        pr_meta = pr_meta.model_copy(update={"diff": diff, "files_changed": files})

        pipeline = compile_pipeline()
        state = PipelineState(pr=pr_meta)
        final_raw = await asyncio.to_thread(pipeline.invoke, state)
        final: PipelineState = PipelineState.model_validate(final_raw) if isinstance(final_raw, dict) else final_raw

        # Token usage is stored in state by node_finalise (runs in pipeline thread)
        token_total = final.token_total
        est_cost_usd = final.est_cost_usd

        # Per-category finding counts for pattern detection
        finding_categories: dict[str, int] = {}
        for f in final.consolidated_findings:
            cat = f.category.value
            finding_categories[cat] = finding_categories.get(cat, 0) + 1

        run_record.update({
            "run_id": final.run_id,
            "status": final.status.value,
            "completed_at": datetime.utcnow().isoformat(),
            "findings": len(final.consolidated_findings),
            "regressions": sum(1 for f in final.consolidated_findings if f.is_regression),
            "finding_categories": finding_categories,
            "tests_generated": len(final.generated_tests),
            "bugs_found": len(final.bug_reports),
            "auto_fixes": len(final.auto_applied_fixes),
            "pending_fixes": len(final.pending_human_fixes),
            "risk_level": final.risk.level.value if final.risk else None,
            "risk_score": final.risk.score if final.risk else None,
            "token_total": token_total,
            "est_cost_usd": est_cost_usd,
        })

        # Save pending approvals
        for fix in final.pending_human_fixes:
            from src.api.store import save_approval
            save_approval({
                "id": fix.id,
                "repo": repo,
                "pr": pr_number,
                "description": fix.description,
                "rationale": fix.rationale,
                "patch": fix.patch,
                "affected_files": fix.affected_files,
                "classification": fix.classification.value,
                "run_id": final.run_id,
            })

        # Launch CI watcher for each auto-applied fix (fire-and-forget)
        if final.auto_applied_fixes and final.pr:
            from src.agents.trust_layer import rollback_agent
            pr_branch = final.pr.head_branch
            installation_id = final.pr.installation_id
            for fix in final.auto_applied_fixes:
                if fix.commit_sha:
                    asyncio.ensure_future(
                        rollback_agent.watch_and_rollback(
                            repo=repo,
                            pr_number=pr_number,
                            fix_id=fix.id,
                            commit_sha=fix.commit_sha,
                            fix_description=fix.description,
                            patch=fix.patch,
                            affected_files=fix.affected_files,
                            branch=pr_branch,
                            installation_id=installation_id,
                        )
                    )

    except Exception as exc:
        log.error("manual_pipeline_failed", repo=repo, pr=pr_number, error=str(exc))
        run_record.update({
            "status": "failed",
            "error": str(exc),
            "completed_at": datetime.utcnow().isoformat(),
        })

    save_run(run_record)
