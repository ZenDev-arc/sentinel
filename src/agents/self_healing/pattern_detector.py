"""
Pattern Detector Agent (weekly)

Analyses recent pipeline runs and the active KB to surface recurring cross-PR
patterns that the team should address at a structural level:
  - Which finding categories recur most often
  - Which file areas accumulate the most issues
  - Regression rate trend
  - Specific high-use KB entries indicating systemic problems

Results are saved to data/patterns.json and served via GET /api/patterns.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.core.logging import get_logger
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_MAX_PATTERNS = 8


def run(kb: KnowledgeBaseStore, max_runs: int = 100) -> dict:
    from src.api.store import list_runs, save_patterns

    runs = list_runs(limit=max_runs)
    if len(runs) < 3:
        log.info("pattern_detector_insufficient_runs", count=len(runs))
        return {"patterns": 0, "skipped": "need at least 3 runs"}

    active_entries = kb.list_all(include_archived=False)
    patterns = _derive_patterns(runs, active_entries)
    save_patterns(patterns)

    log.info("pattern_detector_done", patterns=len(patterns))
    return {"patterns": len(patterns), "ran_at": datetime.now(timezone.utc).isoformat()}


def _derive_patterns(runs: list[dict], kb_entries: list) -> list[dict]:
    """
    Derive patterns purely from aggregated statistics — no LLM call needed.
    Each pattern has: type, title, description, severity, evidence (dict).
    """
    now = datetime.now(timezone.utc).isoformat()
    patterns: list[dict] = []

    total = len(runs)

    # ── Category breakdown from run records ──────────────────────────────────
    category_totals: dict[str, int] = {}
    for run in runs:
        for cat, count in (run.get("finding_categories") or {}).items():
            category_totals[cat] = category_totals.get(cat, 0) + count

    if category_totals:
        top_cat, top_count = max(category_totals.items(), key=lambda x: x[1])
        per_pr = round(top_count / total, 1)
        if per_pr >= 1.0:
            patterns.append(
                {
                    "type": "recurring_category",
                    "title": f"Recurring {top_cat} findings",
                    "description": (
                        f"{top_cat.title()} issues appear in {top_count} findings across "
                        f"{total} runs ({per_pr:.1f} per PR on average). "
                        f"Consider adding a linter rule or architecture guide for this area."
                    ),
                    "severity": "high" if per_pr >= 3 else "medium",
                    "evidence": {
                        "category": top_cat,
                        "total_findings": top_count,
                        "avg_per_pr": per_pr,
                    },
                    "detected_at": now,
                }
            )

    # ── Regression rate ───────────────────────────────────────────────────────
    runs_with_regressions = sum(1 for r in runs if (r.get("regressions") or 0) > 0)
    regression_rate = round(runs_with_regressions / total * 100, 1)
    if regression_rate >= 10:
        patterns.append(
            {
                "type": "high_regression_rate",
                "title": "Repeated bug regressions",
                "description": (
                    f"{regression_rate}% of the last {total} PRs re-introduced a previously-fixed bug. "
                    f"This suggests the fixes aren't being tested at the right level, "
                    f"or the root cause isn't being addressed."
                ),
                "severity": "high" if regression_rate >= 25 else "medium",
                "evidence": {
                    "regression_rate_pct": regression_rate,
                    "affected_runs": runs_with_regressions,
                },
                "detected_at": now,
            }
        )

    # ── High average finding count ────────────────────────────────────────────
    total_findings = sum(r.get("findings") or 0 for r in runs)
    avg_findings = round(total_findings / total, 1)
    if avg_findings >= 5:
        patterns.append(
            {
                "type": "high_finding_volume",
                "title": "High average findings per PR",
                "description": (
                    f"PRs average {avg_findings} findings each. "
                    f"A sustained high volume often indicates a lack of pre-commit linting "
                    f"or missing code-review standards."
                ),
                "severity": "medium",
                "evidence": {
                    "avg_findings_per_pr": avg_findings,
                    "total_findings": total_findings,
                },
                "detected_at": now,
            }
        )

    # ── Most-used KB entries (systemic issues) ────────────────────────────────
    top_entries = sorted(kb_entries, key=lambda e: e.use_count, reverse=True)[:3]
    for entry in top_entries:
        if entry.use_count >= 3:
            patterns.append(
                {
                    "type": "systemic_kb_entry",
                    "title": f"Systemic issue: {entry.title}",
                    "description": (
                        f"This known bug pattern has been detected {entry.use_count} times. "
                        f"It was first fixed in PR #{entry.pr_number} ({entry.repo}). "
                        f"Consider adding a static analysis rule to prevent it."
                    ),
                    "severity": "medium",
                    "evidence": {
                        "kb_entry_id": entry.id,
                        "use_count": entry.use_count,
                        "first_fixed_pr": entry.pr_number,
                        "repo": entry.repo,
                    },
                    "detected_at": now,
                }
            )

    # ── KB file area hot-spots ────────────────────────────────────────────────
    area_counts: dict[str, int] = {}
    for entry in kb_entries:
        for fp in entry.file_paths or []:
            area = fp.split("/")[0] if "/" in fp else "root"
            area_counts[area] = area_counts.get(area, 0) + 1

    if area_counts:
        top_area, top_area_count = max(area_counts.items(), key=lambda x: x[1])
        if top_area_count >= 3:
            patterns.append(
                {
                    "type": "file_area_hotspot",
                    "title": f"Bug hotspot: {top_area}/",
                    "description": (
                        f"The `{top_area}/` directory appears in {top_area_count} KB entries. "
                        f"This area accumulates disproportionate issues — consider a focused "
                        f"refactor or dedicated review checklist."
                    ),
                    "severity": "medium",
                    "evidence": {"area": top_area, "kb_entry_count": top_area_count},
                    "detected_at": now,
                }
            )

    # ── Risk level trend ──────────────────────────────────────────────────────
    recent = [r for r in runs[:20] if r.get("risk_level")]
    if len(recent) >= 5:
        high_rate = sum(1 for r in recent if r.get("risk_level") == "high") / len(
            recent
        )
        if high_rate >= 0.4:
            patterns.append(
                {
                    "type": "elevated_risk_trend",
                    "title": "Elevated PR risk trend",
                    "description": (
                        f"{round(high_rate * 100)}% of recent PRs are classified as HIGH risk. "
                        f"Large, high-impact changes are merging frequently. "
                        f"Consider enforcing smaller PR sizes or mandatory reviewer sign-off."
                    ),
                    "severity": "high" if high_rate >= 0.6 else "medium",
                    "evidence": {
                        "high_risk_rate_pct": round(high_rate * 100),
                        "sample_size": len(recent),
                    },
                    "detected_at": now,
                }
            )

    return patterns[:_MAX_PATTERNS]
