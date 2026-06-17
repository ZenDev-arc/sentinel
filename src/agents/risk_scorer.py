"""
Risk-Scoring Agent

Computes a risk score (0.0–1.0) and a Low/Medium/High label for every PR.
Score factors:
  1. Diff volume  — lines changed, number of files
  2. Sensitive areas — auth, payment, migration, secrets patterns in file paths
  3. Historical bug density — derived from git blame/log data passed in the diff
  4. Coverage exposure — how much of the touched code is currently untested

The Orchestrator uses the level to decide how deep the pipeline runs.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import settings
from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import PipelineState, RiskLevel, RiskScore

log = get_logger(__name__)

_SYSTEM_PROMPT = """You are SENTINEL's Risk-Scoring Agent.

Given a pull request diff and metadata, assess the risk of the change.
Reply ONLY with a JSON object in this exact schema (no markdown fences):

{{
  "score": <float 0.0-1.0>,
  "level": "low" | "medium" | "high",
  "reasons": ["<reason 1>", "<reason 2>", ...],
  "sensitive_areas": ["<area 1>", ...]
}}

Risk scoring guidelines:
- Typos, docs, comments → score 0.0–0.15
- Test-only changes → 0.1–0.25
- Minor refactors (no logic change) → 0.2–0.35
- New feature in isolated module → 0.35–0.55
- Auth, payment, billing, data access changes → 0.65–0.85
- Database schema migrations → 0.70–0.90
- Public API contract changes → 0.65–0.85
- Any change touching secrets/credential handling → 0.85–1.0
- Large diffs (>500 lines) in core modules → add 0.1

Calibrate: LOW < {medium_threshold}, MEDIUM < {high_threshold}, HIGH >= {high_threshold}
""".format(
    medium_threshold=settings.RISK_MEDIUM_THRESHOLD,
    high_threshold=settings.RISK_HIGH_THRESHOLD,
)


def _heuristic_score(state: PipelineState) -> tuple[float, list[str], list[str]]:
    """Fast, deterministic pre-score before sending to LLM.
    Returns (raw_score, reasons, sensitive_areas).
    Used to short-circuit tiny/trivial PRs without an LLM call.
    """
    pr = state.pr
    score = 0.0
    reasons: list[str] = []
    sensitive: list[str] = []

    # Volume
    total_lines = pr.additions + pr.deletions
    if total_lines > 500:
        score += 0.15
        reasons.append(f"Large diff ({total_lines} lines)")
    elif total_lines > 100:
        score += 0.07
    if len(pr.files_changed) > 15:
        score += 0.10
        reasons.append(f"Many files touched ({len(pr.files_changed)})")

    # Sensitive path detection
    patterns = settings.sensitive_patterns
    for fpath in pr.files_changed:
        low = fpath.lower()
        for pat in patterns:
            if pat in low:
                score += 0.20
                if fpath not in sensitive:
                    sensitive.append(fpath)
                reasons.append(f"Sensitive path matched '{pat}': {fpath}")
                break

    return min(score, 1.0), reasons, sensitive


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _llm_score(diff: str, files: list[str], title: str) -> dict[str, Any]:
    llm = get_llm("fast")
    prompt = (
        f"PR title: {title}\n"
        f"Files changed: {', '.join(files[:30])}\n\n"
        f"Diff (first 4000 chars):\n{diff[:4000]}"
    )
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=prompt)]
    )
    import json

    text = response.content.strip()
    # Strip any accidental markdown fences
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def run(state: PipelineState) -> dict:
    """LangGraph node — returns a dict of state fields to update."""
    pr = state.pr
    log.info("risk_scoring_start", repo=pr.repo_full_name, pr=pr.pr_number)

    heuristic_score, h_reasons, h_sensitive = _heuristic_score(state)

    # For very small, non-sensitive PRs skip the LLM to save tokens.
    # But never shortcut if the diff content contains security red-flags.
    _CONTENT_RED_FLAGS = (
        "shell=true",
        "shell = true",
        "password",
        "secret",
        "api_key",
        "apikey",
        "token",
        "execute(",
        "cursor.execute",
        "subprocess",
        "eval(",
        "exec(",
    )
    diff_lower = (pr.diff or "").lower()
    content_is_sensitive = any(flag in diff_lower for flag in _CONTENT_RED_FLAGS)
    if (
        heuristic_score == 0.0
        and pr.additions + pr.deletions < 30
        and not content_is_sensitive
    ):
        level = RiskLevel.LOW
        risk = RiskScore(
            level=level,
            score=0.05,
            reasons=["Tiny diff with no sensitive paths"],
            sensitive_areas=[],
        )
        log.info("risk_score_heuristic_shortcut", level=level)
        return {"risk": risk}

    try:
        data = _llm_score(pr.diff, pr.files_changed, pr.pr_title)
        llm_score = float(data.get("score", heuristic_score))
        llm_reasons = data.get("reasons", [])
        llm_sensitive = data.get("sensitive_areas", [])

        # Blend: take max of heuristic and LLM score to avoid under-scoring
        final_score = max(heuristic_score, llm_score)
        all_reasons = list(dict.fromkeys(h_reasons + llm_reasons))
        all_sensitive = list(dict.fromkeys(h_sensitive + llm_sensitive))

        if final_score >= settings.RISK_HIGH_THRESHOLD:
            level = RiskLevel.HIGH
        elif final_score >= settings.RISK_MEDIUM_THRESHOLD:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        risk = RiskScore(
            level=level,
            score=final_score,
            reasons=all_reasons,
            sensitive_areas=all_sensitive,
        )
    except Exception as exc:
        log.warning("risk_score_llm_failed", error=str(exc))
        # Fall back to heuristic only
        if heuristic_score >= settings.RISK_HIGH_THRESHOLD:
            level = RiskLevel.HIGH
        elif heuristic_score >= settings.RISK_MEDIUM_THRESHOLD:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW
        risk = RiskScore(
            level=level,
            score=heuristic_score,
            reasons=h_reasons + ["LLM scoring unavailable — heuristic only"],
            sensitive_areas=h_sensitive,
        )

    log.info(
        "risk_score_complete",
        level=risk.level,
        score=risk.score,
        reasons=risk.reasons,
    )
    return {"risk": risk}
