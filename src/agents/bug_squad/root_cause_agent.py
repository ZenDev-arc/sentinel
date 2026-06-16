"""
Root-Cause Agent

Given the minimal repro from the Reproduction Agent, traces the failure to its
source by reasoning over:
  - The stack trace
  - Recent commits that touched the affected files
  - The actual diff introduced by this PR
  - Relevant Knowledge Base entries (similar past bugs)

Produces a root-cause description and identifies the likely source file/line.
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import BugReport, PipelineState
from src.knowledge_base.models import KBEntryType
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_SYSTEM = """You are SENTINEL's Root-Cause Agent — a senior debugging engineer.

Given:
- A minimal reproduction case
- The test failure message
- The PR diff
- Relevant past bugs from the knowledge base

Identify the root cause of the failure.

Return a JSON object:
{
  "root_cause": "<precise explanation of what is wrong and why>",
  "source_file": "<file most likely containing the bug>",
  "source_line_hint": <line number or null>,
  "affected_files": ["<file1>", "<file2>"],
  "hypothesis": "<one sentence hypothesis to guide the fix>"
}

Return only the JSON. Do NOT wrap in markdown.
Do NOT suggest a fix here — only identify the cause.
"""


_SYSTEM_BATCH = """You are SENTINEL's Root-Cause Agent — a senior debugging engineer.

Given a list of bug repros and the PR diff, identify the root cause for EACH bug.

Return a JSON array — one object per bug, in the same order:
[
  {
    "failing_test": "<test name>",
    "root_cause": "<precise explanation of what is wrong and why>",
    "source_file": "<file most likely containing the bug>",
    "source_line_hint": <line number or null>,
    "affected_files": ["<file1>", "<file2>"],
    "hypothesis": "<one sentence hypothesis to guide the fix>"
  }
]

Return only the JSON array. Do NOT wrap in markdown.
Do NOT suggest fixes — only identify causes.
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=30))
def _analyse_batch(repros: list[dict], diff: str, kb_context: str) -> list[dict]:
    llm = get_llm("fast")
    prompt = ""
    if kb_context:
        prompt += f"Similar past bugs:\n{kb_context}\n\n"
    repros_text = json.dumps([
        {"failing_test": r["failing_test"], "minimal_repro": r["minimal_repro"][:800]}
        for r in repros
    ], indent=2)
    prompt += f"Bug repros:\n{repros_text}\n\nPR diff (first 4000 chars):\n{diff[:4000]}"
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM_BATCH), HumanMessage(content=prompt)]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    result = json.loads(text)
    return result if isinstance(result, list) else [result]


def run(state: PipelineState, kb: KnowledgeBaseStore) -> dict:
    log.info("root_cause_agent_start", reports=len(state.bug_reports))

    needs_analysis = [r for r in state.bug_reports if not r.root_cause]
    already_done = [r for r in state.bug_reports if r.root_cause]

    if not needs_analysis:
        return {"bug_reports": state.bug_reports}

    # Single KB search covering all bugs
    combined_query = " ".join(
        f"bug {r.failing_test} {' '.join(r.affected_files[:2])}"
        for r in needs_analysis[:3]
    )
    kb_hits = kb.search(
        query=combined_query,
        repo=state.pr.repo_full_name if state.pr else "*",
        n_results=3,
        entry_type=KBEntryType.BUG_FIX,
    )
    kb_context = "\n".join(
        f"- {h.entry.title}: {h.entry.payload.get('root_cause', '')[:200]}"
        for h in kb_hits
    )

    repros_input = [
        {"failing_test": r.failing_test, "minimal_repro": r.minimal_repro}
        for r in needs_analysis
    ]

    try:
        batch = _analyse_batch(
            repros=repros_input,
            diff=state.pr.diff if state.pr else "",
            kb_context=kb_context,
        )
        by_test = {d.get("failing_test", ""): d for d in batch}
        updated = []
        for i, report in enumerate(needs_analysis):
            data = by_test.get(report.failing_test) or (batch[i] if i < len(batch) else {})
            updated.append(report.model_copy(update={
                "root_cause": data.get("root_cause", "Unknown"),
                "affected_files": data.get("affected_files", report.affected_files),
            }))
    except Exception as exc:
        log.warning("root_cause_batch_failed", error=str(exc))
        updated = [
            r.model_copy(update={"root_cause": f"Root-cause analysis failed: {exc}"})
            for r in needs_analysis
        ]

    for hit in kb_hits:
        kb.record_use(hit.entry.id)

    log.info("root_cause_agent_done", reports=len(updated))
    return {"bug_reports": already_done + updated}
