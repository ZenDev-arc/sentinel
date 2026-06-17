"""
Approval Gate

Classifies each proposed fix as:
  AUTO_MERGE — safe to commit directly (low blast radius, reversible)
  HUMAN_REQUIRED — must be reviewed by a human before applying

Auto-merge criteria (ALL must hold):
  - Fix touches no sensitive areas (auth, payment, migrations, secrets, public API)
  - Patch is small (< 30 lines changed)
  - All existing tests still pass after the patch
  - The fix was verified by the Verification Agent

Anything not satisfying ALL criteria → HUMAN_REQUIRED.

Then separates fixes into auto_applied_fixes and pending_human_fixes lists
and writes a human-readable PR comment body for the Orchestrator to post.
"""

from __future__ import annotations

from src.core.config import settings
from src.core.logging import get_logger
from src.core.regression_detector import detect_regressions
from src.core.state import (FindingSeverity, FixClassification, PipelineState,
                            ProposedFix, RiskLevel)
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_SENSITIVE_KEYWORDS = set(settings.sensitive_patterns)
_MAX_AUTO_PATCH_LINES = 30


def _get_policy(state: PipelineState):
    """Return the active SentinelPolicy, creating defaults if none was loaded."""
    from src.core.policy import SentinelPolicy

    if state.policy is None:
        return SentinelPolicy()
    return state.policy


def _is_auto_mergeable(fix: ProposedFix, state: PipelineState) -> bool:
    if not fix.patch.strip():
        return False

    policy = _get_policy(state)

    # Sensitive file check — global defaults + policy always_human_paths
    for fpath in fix.affected_files:
        low = fpath.lower()
        if any(kw in low for kw in _SENSITIVE_KEYWORDS):
            return False
        if policy.is_always_human(fpath):
            return False

    # Patch size check — policy can override the default limit
    max_lines = policy.gate.max_auto_patch_lines
    changed_lines = sum(
        1
        for line in fix.patch.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )
    if changed_lines > max_lines:
        return False

    # High-risk PR with CRITICAL findings → force human review on all fixes
    critical_count = sum(
        1 for f in state.all_findings() if f.severity == FindingSeverity.CRITICAL
    )
    if state.risk and state.risk.level == RiskLevel.HIGH and critical_count > 0:
        return False

    return True


def _build_pr_comment(state: PipelineState) -> str:
    lines: list[str] = ["## SENTINEL Review Report\n"]

    # Regressions — show at the very top so they're impossible to miss
    regressions = [f for f in state.consolidated_findings if f.is_regression]
    if regressions:
        lines.append(f"\n### ⚠️ Regressions Detected ({len(regressions)})\n")
        lines.append(
            "> These findings match bugs that were **previously fixed** in your codebase. "
            "Merging this PR will reintroduce known issues.\n"
        )
        for f in regressions:
            rm = f.regression
            assert rm is not None
            pr_ref = f"[#{rm.original_pr}]" if rm.original_pr else "unknown PR"
            lines.append(
                f"- **{f.title}** — `{f.file_path}`\n"
                f"  Previously fixed in {rm.original_repo} {pr_ref} "
                f"on {rm.fixed_at.strftime('%Y-%m-%d')} "
                f"(similarity: {rm.similarity:.0%})\n"
                f"  > {rm.original_fix_summary}"
            )
        lines.append("")

    # Risk badge
    risk = state.risk
    if risk:
        emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk.level.value, "⚪")
        lines.append(
            f"**Risk Level:** {emoji} {risk.level.value.upper()} (score: {risk.score:.2f})\n"
        )
        if risk.reasons:
            lines.append("**Risk reasons:** " + "; ".join(risk.reasons[:3]) + "\n")

    # Review findings
    findings = state.consolidated_findings
    if findings:
        lines.append(f"\n### Code Review ({len(findings)} findings)\n")
        by_sev = {}
        for f in findings:
            by_sev.setdefault(f.severity, []).append(f)
        for sev in [
            FindingSeverity.CRITICAL,
            FindingSeverity.HIGH,
            FindingSeverity.MEDIUM,
            FindingSeverity.LOW,
            FindingSeverity.INFO,
        ]:
            group = by_sev.get(sev, [])
            if not group:
                continue
            lines.append(f"\n**{sev.value.upper()}** ({len(group)})\n")
            for finding in group[:5]:  # cap display at 5 per severity
                loc = f"`{finding.file_path}`"
                if finding.line_start:
                    loc += f" line {finding.line_start}"
                lines.append(f"- **{finding.title}** — {loc}")
                if finding.rationale:
                    lines.append(f"  > {finding.rationale}")
                if finding.suggestion:
                    lines.append(f"  *Suggestion:* {finding.suggestion}")
    else:
        lines.append("\n### Code Review\n✅ No significant findings.\n")

    # Test coverage
    results = state.test_results
    if results:
        total_passed = sum(r.passed for r in results)
        total_failed = sum(r.failed + r.errors for r in results)
        lines.append(f"\n### Tests\n")
        lines.append(f"- Passed: {total_passed}  Failed: {total_failed}")
        if state.coverage_gaps:
            lines.append(f"- Coverage gaps: {len(state.coverage_gaps)}")
            for gap in state.coverage_gaps[:3]:
                lines.append(f"  - {gap}")

    # Auto-applied fixes
    if state.auto_applied_fixes:
        lines.append(f"\n### Auto-Applied Fixes ({len(state.auto_applied_fixes)})\n")
        for fix in state.auto_applied_fixes:
            lines.append(f"- ✅ {fix.description}")
            if fix.commit_sha:
                lines.append(f"  Commit: `{fix.commit_sha[:8]}`")
            if fix.rationale:
                lines.append(f"  > {fix.rationale}")

    # Pending human fixes
    if state.pending_human_fixes:
        lines.append(f"\n### Pending Human Review ({len(state.pending_human_fixes)})\n")
        for fix in state.pending_human_fixes:
            lines.append(f"- ⏳ {fix.description}")
            if fix.rationale:
                lines.append(f"  > {fix.rationale}")
            lines.append(f"  *Affected:* {', '.join(fix.affected_files[:3])}")

    lines.append("\n---\n*Generated by [SENTINEL](https://github.com/SENTINEL)*")
    return "\n".join(lines)


def run(state: PipelineState, kb: KnowledgeBaseStore | None = None) -> dict:
    log.info("approval_gate_start", fixes=len(state.proposed_fixes))

    policy = _get_policy(state)

    # Tag any finding that matches a previously-fixed bug in the KB
    if kb is not None and state.consolidated_findings and policy.regressions.enabled:
        repo = state.pr.repo_full_name if state.pr else "*"
        tagged = detect_regressions(
            state.consolidated_findings,
            repo,
            kb,
            threshold=policy.regressions.threshold,
        )
        state = state.model_copy(update={"consolidated_findings": tagged})

    # Apply policy filters: drop findings below min_severity or in skip_categories
    skip_cats = set(policy.review.skip_categories)
    if policy.review.min_severity != "info" or skip_cats:
        filtered = [
            f
            for f in state.consolidated_findings
            if not policy.is_below_min_severity(f.severity.value)
            and f.category.value not in skip_cats
        ]
        if len(filtered) != len(state.consolidated_findings):
            log.info(
                "policy_filtered_findings",
                before=len(state.consolidated_findings),
                after=len(filtered),
                min_severity=policy.review.min_severity,
                skip_categories=list(skip_cats),
            )
        state = state.model_copy(update={"consolidated_findings": filtered})

    # If block_merge is set and any regression was found, force all fixes to HUMAN_REQUIRED
    has_regressions = any(f.is_regression for f in state.consolidated_findings)
    force_human = policy.regressions.block_merge and has_regressions

    auto_fixes: list[ProposedFix] = []
    human_fixes: list[ProposedFix] = []

    for fix in state.proposed_fixes:
        if not force_human and _is_auto_mergeable(fix, state):
            classified = fix.model_copy(
                update={"classification": FixClassification.AUTO_MERGE}
            )
            auto_fixes.append(classified)
            log.info("fix_auto_merge", description=fix.description[:60])
        else:
            classified = fix.model_copy(
                update={"classification": FixClassification.HUMAN_REQUIRED}
            )
            human_fixes.append(classified)
            if force_human:
                log.info(
                    "fix_human_required_regression_block",
                    description=fix.description[:60],
                )
            else:
                log.info("fix_human_required", description=fix.description[:60])

    pr_comment = _build_pr_comment(
        state.model_copy(
            update={
                "auto_applied_fixes": auto_fixes,
                "pending_human_fixes": human_fixes,
            }
        )
    )

    log.info(
        "approval_gate_done",
        auto=len(auto_fixes),
        human=len(human_fixes),
    )
    return {
        "auto_applied_fixes": auto_fixes,
        "pending_human_fixes": human_fixes,
        "pr_comment": pr_comment,
    }
