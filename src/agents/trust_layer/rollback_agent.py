"""
Rollback Agent

Monitors CI check runs after SENTINEL auto-commits a fix. If any check fails,
it reverses the patch and posts a comment explaining what happened.

Flow:
  auto_applied_fix committed → background task starts
  → polls check-runs every 30 s for up to 15 minutes
  → all checks pass  → done, no action
  → any check fails  → create reverse-patch commit + post PR comment
  → timeout (15 min) → log warning, no action (human can review)
"""

from __future__ import annotations

import asyncio

from src.core.logging import get_logger
from src.core.state import FixClassification, ProposedFix

log = get_logger(__name__)

_POLL_INTERVAL_S = 30
_MAX_POLLS = 30   # 30 × 30 s = 15 minutes


def _reverse_patch(patch: str) -> str:
    """
    Produce the inverse of a unified diff: swap + and - lines so applying it
    undoes the original change. @@ headers and context lines are kept as-is.
    """
    reversed_lines: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+++"):
            reversed_lines.append("---" + line[3:])
        elif line.startswith("---"):
            reversed_lines.append("+++" + line[3:])
        elif line.startswith("+") and not line.startswith("+++"):
            reversed_lines.append("-" + line[1:])
        elif line.startswith("-") and not line.startswith("---"):
            reversed_lines.append("+" + line[1:])
        else:
            reversed_lines.append(line)
    return "\n".join(reversed_lines)


async def watch_and_rollback(
    *,
    repo: str,
    pr_number: int,
    fix_id: str,
    commit_sha: str,
    fix_description: str,
    patch: str,
    affected_files: list[str],
    branch: str,
    installation_id: int | None = None,
) -> str:
    """
    Poll GitHub check runs and rollback the fix if CI fails.

    Returns one of: 'passed', 'reverted', 'timed_out', 'no_checks'.
    """
    from src.integrations.github_client import GitHubClient

    gh = GitHubClient(installation_id=installation_id)
    log.info(
        "rollback_watch_start",
        repo=repo,
        pr=pr_number,
        sha=commit_sha[:8],
        fix=fix_description[:60],
    )

    for attempt in range(_MAX_POLLS):
        await asyncio.sleep(_POLL_INTERVAL_S)

        try:
            runs = gh.get_check_runs(repo, commit_sha)
        except Exception as exc:
            log.warning("rollback_check_runs_error", error=str(exc), attempt=attempt)
            continue

        if not runs:
            if attempt >= 3:
                log.info("rollback_no_checks_found", repo=repo, sha=commit_sha[:8])
                return "no_checks"
            continue

        pending = [r for r in runs if r.get("status") != "completed"]
        if pending:
            continue   # some checks still running

        failed = [
            r for r in runs
            if r.get("conclusion") in ("failure", "timed_out", "cancelled", "action_required")
        ]

        if not failed:
            log.info(
                "rollback_ci_passed",
                repo=repo,
                pr=pr_number,
                sha=commit_sha[:8],
                checks=len(runs),
            )
            return "passed"

        # ── CI failed — revert ────────────────────────────────────────────────
        failed_names = ", ".join(r.get("name", "?") for r in failed[:3])
        log.warning(
            "rollback_ci_failed",
            repo=repo,
            pr=pr_number,
            sha=commit_sha[:8],
            failed_checks=failed_names,
        )

        reversed_patch = _reverse_patch(patch)
        if reversed_patch.strip():
            revert_fix = ProposedFix(
                description=f"[ROLLBACK] {fix_description}",
                patch=reversed_patch,
                affected_files=affected_files,
                classification=FixClassification.AUTO_MERGE,
                rationale=f"CI failed after auto-applied fix. Reverting. Failed: {failed_names}",
            )
            try:
                revert_sha = gh.commit_fix(
                    repo,
                    revert_fix,
                    branch,
                    f"[SENTINEL ROLLBACK] Revert auto-fix: {fix_description}\n\n"
                    f"CI checks failed after auto-applied fix.\n"
                    f"Failed checks: {failed_names}\n\n"
                    f"Original fix ID: {fix_id}",
                )
                log.info("rollback_revert_committed", sha=(revert_sha or "")[:8])
            except Exception as exc:
                log.error("rollback_revert_failed", error=str(exc))
                revert_sha = None
        else:
            revert_sha = None

        comment = (
            f"⚠️ **SENTINEL Rollback**\n\n"
            f"The auto-applied fix **\"{fix_description}\"** was automatically reverted "
            f"because CI checks failed.\n\n"
            f"**Failed checks:** {failed_names}\n\n"
            f"The fix has been moved to the **Pending Approvals** queue so a human can "
            f"review it before re-applying.\n\n"
            f"<sub>SENTINEL rollback · commit `{commit_sha[:8]}`</sub>"
        )
        try:
            gh.post_pr_comment(repo, pr_number, comment)
        except Exception as exc:
            log.warning("rollback_comment_failed", error=str(exc))

        return "reverted"

    log.warning(
        "rollback_timed_out",
        repo=repo,
        pr=pr_number,
        sha=commit_sha[:8],
        polls=_MAX_POLLS,
    )
    return "timed_out"
