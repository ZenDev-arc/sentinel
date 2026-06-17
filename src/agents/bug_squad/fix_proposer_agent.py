"""
Fix-Proposer Agent

Given the root cause from the Root-Cause Agent, drafts one or more candidate
patches. Queries the KB for similar past fixes first.

Each patch is a unified diff that can be applied with `git apply`.
Generates 1–3 candidates ordered by confidence.
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

_SYSTEM = """You are SENTINEL's Fix-Proposer Agent.

Given a root-cause analysis and the PR diff, propose 1–3 candidate patches.

Return a JSON array of patch objects, ordered by your confidence (highest first):
[
  {
    "confidence": <float 0.0-1.0>,
    "description": "<what this patch does and why it fixes the bug>",
    "patch": "<unified diff that can be applied with git apply>",
    "affected_files": ["<file1>"]
  }
]

Rules:
- Patches must be minimal — fix only what is broken.
- Prefer the simplest correct fix over a clever one.
- If a similar past fix exists in the knowledge base, prefer that approach.
- Patch format: standard unified diff (`--- a/file` / `+++ b/file` / `@@ … @@`).
- Do NOT change unrelated code.
Return only the JSON array. Do NOT wrap in markdown.
"""


_SYSTEM = """You are SENTINEL's Fix-Proposer Agent.

Given a root-cause analysis and the PR diff, propose a code fix.

Return a single JSON object:
{
  "confidence": <float 0.0-1.0>,
  "description": "<what this fix does and why it works>",
  "file": "<relative file path, e.g. buggy_calculator.py>",
  "original_code": "<exact code block to replace — copy verbatim from the diff, no + prefix>",
  "fixed_code": "<replacement code block with the bug fixed>",
  "affected_files": ["<file1>"]
}

Rules:
- original_code must match EXACTLY what appears in the source file (same whitespace, no leading + characters).
- fixed_code must be a minimal, drop-in replacement for original_code.
- Fix only the broken lines. Do NOT change anything else.
Return only the JSON object. Do NOT wrap in markdown.
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=10, max=45))
def _propose(root_cause: str, diff: str, kb_context: str) -> dict:
    llm = get_llm("fast")
    prompt = ""
    if kb_context:
        prompt += f"Similar past fixes:\n{kb_context}\n\n"
    prompt += f"Root cause:\n{root_cause}\n\nPR diff (first 4000 chars):\n{diff[:4000]}"
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def run(state: PipelineState, kb: KnowledgeBaseStore) -> dict:
    log.info("fix_proposer_start", reports=len(state.bug_reports))

    updated_reports: list[BugReport] = []

    for report in state.bug_reports:
        if report.candidate_patches:
            updated_reports.append(report)
            continue

        if not report.root_cause or "failed" in report.root_cause.lower():
            updated_reports.append(
                report.model_copy(
                    update={
                        "candidate_patches": [
                            {
                                "confidence": 0.0,
                                "description": "Skipped: no root cause",
                                "file": "",
                                "original_code": "",
                                "fixed_code": "",
                                "affected_files": [],
                            }
                        ]
                    }
                )
            )
            continue

        query = f"fix {report.root_cause[:200]} {' '.join(report.affected_files[:3])}"
        kb_hits = kb.search(
            query=query,
            repo=state.pr.repo_full_name if state.pr else "*",
            n_results=2,
            entry_type=KBEntryType.BUG_FIX,
        )
        kb_context = "\n".join(
            f"- Past fix: {h.entry.payload.get('patch', '')[:200]}" for h in kb_hits
        )

        try:
            patch = _propose(
                root_cause=report.root_cause,
                diff=state.pr.diff if state.pr else "",
                kb_context=kb_context,
            )
            updated_reports.append(
                report.model_copy(update={"candidate_patches": [patch]})
            )
            log.info(
                "fix_proposed",
                test=report.failing_test,
                confidence=patch.get("confidence"),
            )
        except Exception as exc:
            log.warning("fix_proposal_failed", test=report.failing_test, error=str(exc))
            updated_reports.append(
                report.model_copy(
                    update={
                        "candidate_patches": [
                            {
                                "confidence": 0.0,
                                "description": f"Auto-fix failed: {exc}",
                                "file": "",
                                "original_code": "",
                                "fixed_code": "",
                                "affected_files": [],
                            }
                        ]
                    }
                )
            )

        for hit in kb_hits:
            kb.record_use(hit.entry.id)

    log.info("fix_proposer_done", reports=len(updated_reports))
    return {"bug_reports": updated_reports}
