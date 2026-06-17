"""
Maintenance Scheduler

Runs the four self-healing agents on a nightly/weekly schedule using APScheduler.
Completely independent of the per-PR pipeline.

Schedule (configurable via KB_MAINTENANCE_CRON env var):
  - Curator Agent          → nightly at 02:00
  - Drift-Checker Agent    → nightly at 02:15
  - Consistency Agent      → weekly (Sunday 03:00)
  - Consolidation Agent    → weekly (Sunday 03:30)
"""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.agents.self_healing import consistency, consolidation, curator, drift_checker
from src.core.config import settings
from src.core.logging import get_logger
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_curator(kb: KnowledgeBaseStore) -> None:
    from src.api.store import consume_reverts

    log.info("scheduled_curator_start")
    try:
        reverted = consume_reverts()
        if reverted:
            log.info("curator_revert_shas", count=len(reverted))
        result = curator.run(kb, reverted_commits=reverted)
        log.info("scheduled_curator_done", **result)
    except Exception as exc:
        log.error("scheduled_curator_failed", error=str(exc))


def _run_drift_checker(kb: KnowledgeBaseStore, repo_root: str) -> None:
    log.info("scheduled_drift_checker_start")
    try:
        result = drift_checker.run(kb, repo_root)
        log.info("scheduled_drift_checker_done", **result)
    except Exception as exc:
        log.error("scheduled_drift_checker_failed", error=str(exc))


def _run_consistency(kb: KnowledgeBaseStore) -> None:
    log.info("scheduled_consistency_start")
    try:
        result = consistency.run(kb)
        log.info("scheduled_consistency_done", **result)
    except Exception as exc:
        log.error("scheduled_consistency_failed", error=str(exc))


def _run_consolidation(kb: KnowledgeBaseStore) -> None:
    log.info("scheduled_consolidation_start")
    try:
        result = consolidation.run(kb)
        log.info("scheduled_consolidation_done", **result)
    except Exception as exc:
        log.error("scheduled_consolidation_failed", error=str(exc))


def start_scheduler(repo_root: str = ".") -> None:
    global _scheduler

    kb = KnowledgeBaseStore()

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Nightly jobs
    _scheduler.add_job(
        _run_curator,
        trigger=CronTrigger(hour=2, minute=0),
        args=[kb],
        id="curator",
        name="Curator Agent",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_drift_checker,
        trigger=CronTrigger(hour=2, minute=15),
        args=[kb, repo_root],
        id="drift_checker",
        name="Drift-Checker Agent",
        replace_existing=True,
    )

    # Weekly jobs (Sunday)
    _scheduler.add_job(
        _run_consistency,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
        args=[kb],
        id="consistency",
        name="Consistency Agent",
        replace_existing=True,
    )
    _scheduler.add_job(
        _run_consolidation,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=30),
        args=[kb],
        id="consolidation",
        name="Consolidation Agent",
        replace_existing=True,
    )

    _scheduler.start()
    log.info(
        "maintenance_scheduler_started",
        jobs=[j.name for j in _scheduler.get_jobs()],
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("maintenance_scheduler_stopped")
