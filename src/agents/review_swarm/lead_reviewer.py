"""
Lead Reviewer Agent

Aggregates findings from all four specialist agents:
  - Deduplicates overlapping findings
  - Resolves conflicts (e.g. two agents flagging the same line for different reasons)
  - Re-prioritises by severity and business impact
  - Produces one coherent, human-readable review comment for the PR
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import FindingSeverity, PipelineState, ReviewFinding

log = get_logger(__name__)

_SEVERITY_RANK = {
    FindingSeverity.CRITICAL: 5,
    FindingSeverity.HIGH: 4,
    FindingSeverity.MEDIUM: 3,
    FindingSeverity.LOW: 2,
    FindingSeverity.INFO: 1,
}

_SYSTEM = """You are SENTINEL's Lead Reviewer.

You receive a JSON list of findings from four specialist sub-agents (security,
performance, style, architecture). Your job:

1. Remove exact or near-duplicate findings (same file, same line, same issue).
2. If two agents flagged the same line with different concerns, merge them into one richer finding.
3. Re-rank everything by severity + business impact.
4. Return the deduplicated, merged, re-ranked list as a JSON array with the same schema.

Schema:
{
  "id": "<keep original id>",
  "category": "<keep original>",
  "severity": "critical" | "high" | "medium" | "low" | "info",
  "file_path": "<file>",
  "line_start": <int or null>,
  "line_end": <int or null>,
  "title": "<title>",
  "description": "<merged description>",
  "suggestion": "<merged suggestion>",
  "rationale": "<one sentence on why this matters>",
  "kb_hit_ids": [<keep or merge>]
}

Return ONLY the JSON array. Do NOT wrap in markdown.
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _consolidate(raw_findings_json: str) -> list[dict]:
    llm = get_llm("fast")
    response = llm.invoke(
        [
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=raw_findings_json),
        ]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def run(state: PipelineState) -> dict:
    log.info("lead_reviewer_start", pr=state.pr.pr_number if state.pr else None)

    all_findings = state.all_findings()

    if not all_findings:
        return {"consolidated_findings": []}

    # Sort by severity before sending to LLM to help it prioritise
    all_findings.sort(key=lambda f: _SEVERITY_RANK.get(f.severity, 0), reverse=True)

    # Trim each finding to keep the payload under Groq's token limit
    def _trim(f: ReviewFinding) -> dict:
        d = f.model_dump()
        d["description"] = (d.get("description") or "")[:300]
        d["suggestion"] = (d.get("suggestion") or "")[:200]
        return d

    raw_json = json.dumps([_trim(f) for f in all_findings], default=str)
    # Hard cap at 12 000 chars (~3 000 tokens) so we never hit a 413
    if len(raw_json) > 12_000:
        raw_json = raw_json[:12_000] + "]"

    try:
        consolidated_raw = _consolidate(raw_json)
    except Exception as exc:
        log.warning("lead_reviewer_llm_failed", error=str(exc))
        # Fallback: just deduplicate by (file_path, line_start, title)
        seen: set[tuple] = set()
        consolidated_raw = []
        for f in all_findings:
            key = (f.file_path, f.line_start, f.title)
            if key not in seen:
                seen.add(key)
                consolidated_raw.append(f.model_dump())

    consolidated: list[ReviewFinding] = []
    for item in consolidated_raw:
        try:
            # Re-parse from dict — fields like severity are already valid enums
            consolidated.append(ReviewFinding.model_validate(item))
        except Exception as exc:
            log.warning("lead_reviewer_parse_error", error=str(exc))

    log.info(
        "lead_reviewer_done",
        original=len(all_findings),
        consolidated=len(consolidated),
    )
    return {"consolidated_findings": consolidated}
