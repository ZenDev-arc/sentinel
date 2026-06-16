"""
Reproduction Agent

First step of the Bug-Hunting Strike Team.

Takes a failing test (name + output) and isolates it into a minimal,
deterministic reproduction case:
  - Strips irrelevant fixtures / setup
  - Identifies the exact assertion that fails
  - Produces a self-contained repro script the Root-Cause Agent can reason about
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import BugReport, PipelineState, TestResult

log = get_logger(__name__)

_SYSTEM = """You are SENTINEL's Reproduction Agent.

Given a failing test and its output, produce a minimal reproduction case.

Return a JSON object:
{
  "failing_test": "<test name>",
  "minimal_repro": "<self-contained Python/JS/etc. script that reproduces the failure>",
  "failure_message": "<the exact assertion/error message>",
  "affected_files": ["<file1>", ...]
}

Rules:
- The repro script must be runnable without the full test suite (minimal imports).
- Strip anything that doesn't contribute to the failure.
- Include ONLY what is necessary to reproduce the exact error.
- Do NOT attempt to fix the bug — only isolate it.
Return only the JSON. Do NOT wrap in markdown.
"""


_SYSTEM_BATCH = """You are SENTINEL's Reproduction Agent.

Given a list of failing tests and their combined output, produce a minimal reproduction case for EACH test.

Return a JSON array — one object per failing test:
[
  {
    "failing_test": "<test name>",
    "minimal_repro": "<self-contained script that reproduces the failure>",
    "failure_message": "<exact assertion/error message>",
    "affected_files": ["<file1>", ...]
  }
]

Rules:
- The repro script must be runnable without the full test suite.
- Strip anything that doesn't contribute to the failure.
- Do NOT attempt to fix the bug — only isolate it.
Return only the JSON array. Do NOT wrap in markdown.
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=30))
def _isolate_batch(failing_tests: list[str], stdout: str, stderr: str, diff: str) -> list[dict]:
    llm = get_llm("fast")
    prompt = (
        f"Failing tests: {json.dumps(failing_tests)}\n\n"
        f"stdout:\n{stdout[:3000]}\n\n"
        f"stderr:\n{stderr[:1000]}\n\n"
        f"Diff (first 3000 chars):\n{diff[:3000]}"
    )
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM_BATCH), HumanMessage(content=prompt)]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    result = json.loads(text)
    return result if isinstance(result, list) else [result]


def run(state: PipelineState) -> dict:
    all_failing: list[tuple[str, TestResult]] = [
        (test, result)
        for result in state.test_results
        for test in result.failing_tests
    ]
    log.info("reproduction_agent_start", failing=len(all_failing))

    bug_reports: list[BugReport] = list(state.bug_reports)
    if not all_failing:
        return {"bug_reports": bug_reports}

    # Group by TestResult so we can batch per result set
    from itertools import groupby
    results_map: dict[int, TestResult] = {}
    for test, result in all_failing:
        results_map.setdefault(id(result), result)

    for result in results_map.values():
        failing_in_result = [t for t, r in all_failing if r is result]
        try:
            batch = _isolate_batch(
                failing_tests=failing_in_result,
                stdout=result.stdout,
                stderr=result.stderr,
                diff=state.pr.diff if state.pr else "",
            )
            by_name = {d.get("failing_test", ""): d for d in batch}
            for test_name in failing_in_result:
                data = by_name.get(test_name) or (batch[0] if batch else {})
                bug_reports.append(BugReport(
                    failing_test=test_name,
                    minimal_repro=data.get("minimal_repro", f"# Test: {test_name}"),
                    affected_files=data.get("affected_files", [result.module]),
                ))
        except Exception as exc:
            log.warning("reproduction_batch_failed", error=str(exc))
            for test_name in failing_in_result:
                bug_reports.append(BugReport(
                    failing_test=test_name,
                    minimal_repro=f"# Auto-reproduction failed: {exc}",
                    affected_files=[result.module],
                ))

    log.info("reproduction_agent_done", reports=len(bug_reports))
    return {"bug_reports": bug_reports}
