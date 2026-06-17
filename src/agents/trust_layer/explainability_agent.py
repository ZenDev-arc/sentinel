"""
Explainability Agent

Attaches plain-English rationale to every:
  - Review finding
  - Generated test
  - Proposed fix

The rationale answers three questions for a human reviewer:
  1. What is the issue / change?
  2. Why does it matter?
  3. What specifically was changed / what should be done?

This makes SENTINEL's output actionable without reading agent logs.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import PipelineState, ProposedFix, ReviewFinding

log = get_logger(__name__)

_FINDING_SYSTEM = """You are SENTINEL's Explainability Agent.

Given a code review finding (JSON), write a concise rationale that a developer
can understand without reading any logs.

Return a JSON object:
{
  "rationale": "<2-3 sentences: what the issue is, why it matters, and what to do>"
}

Be specific, not generic. Reference the actual code concern. No filler phrases.
Return only the JSON object. Do NOT wrap in markdown.
"""

_FIX_SYSTEM = """You are SENTINEL's Explainability Agent.

Given a proposed code fix (patch + description), write a human-readable explanation.

Return a JSON object:
{
  "rationale": "<2-3 sentences: what was broken, why this fix resolves it, what changed>"
}

Be specific. Reference the actual root cause and the patch approach.
Return only the JSON object. Do NOT wrap in markdown.
"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
def _explain_finding(finding: ReviewFinding) -> str:
    llm = get_llm("fast")
    payload = {
        "title": finding.title,
        "category": finding.category,
        "severity": finding.severity,
        "description": finding.description,
        "suggestion": finding.suggestion,
    }
    response = llm.invoke(
        [
            SystemMessage(content=_FINDING_SYSTEM),
            HumanMessage(content=json.dumps(payload)),
        ]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    data = json.loads(text)
    return data.get("rationale", "")


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
def _explain_fix(fix: ProposedFix) -> str:
    llm = get_llm("fast")
    payload = {
        "description": fix.description,
        "patch_preview": fix.patch[:500],
        "affected_files": fix.affected_files,
    }
    response = llm.invoke(
        [SystemMessage(content=_FIX_SYSTEM), HumanMessage(content=json.dumps(payload))]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    data = json.loads(text)
    return data.get("rationale", "")


def run(state: PipelineState) -> dict:
    log.info(
        "explainability_agent_start",
        findings=len(state.consolidated_findings),
        fixes=len(state.proposed_fixes),
    )

    annotated_findings: list[ReviewFinding] = []
    for finding in state.consolidated_findings:
        if finding.rationale:
            annotated_findings.append(finding)
            continue
        try:
            rationale = _explain_finding(finding)
            annotated_findings.append(
                finding.model_copy(update={"rationale": rationale})
            )
        except Exception as exc:
            log.warning("explain_finding_failed", finding_id=finding.id, error=str(exc))
            annotated_findings.append(finding)

    annotated_fixes: list[ProposedFix] = []
    for fix in state.proposed_fixes:
        if fix.rationale:
            annotated_fixes.append(fix)
            continue
        try:
            rationale = _explain_fix(fix)
            annotated_fixes.append(fix.model_copy(update={"rationale": rationale}))
        except Exception as exc:
            log.warning("explain_fix_failed", fix_id=fix.id, error=str(exc))
            annotated_fixes.append(fix)

    log.info(
        "explainability_agent_done",
        annotated_findings=len(annotated_findings),
        annotated_fixes=len(annotated_fixes),
    )
    return {
        "consolidated_findings": annotated_findings,
        "proposed_fixes": annotated_fixes,
    }
