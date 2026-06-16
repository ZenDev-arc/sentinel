"""
Integration Test Agent

After unit-level gaps are filled, writes tests that exercise interactions
across the changed modules. Only fires when:
  - Risk level is Medium or High
  - Multiple source files were changed
  - The changes touch module boundaries (imports between changed files)
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import GeneratedTest, PipelineState, RiskLevel

log = get_logger(__name__)

_SYSTEM = """You are SENTINEL's Integration Test Agent.

Write integration tests that exercise the INTERACTIONS between the changed modules —
not internal unit logic (that's covered by unit tests).

Focus on:
- Cross-module data flows (module A calls module B, assert the combined output)
- Boundary conditions between layers (e.g. service → repository → DB)
- Error propagation across module boundaries
- Happy path end-to-end for the new feature/fix

Return a JSON object:
{
  "module": "integration",
  "language": "python",
  "file_path": "<suggested test file path>",
  "description": "<what interactions are tested>",
  "content": "<complete integration test file as a string>"
}

Return only the JSON object. Do NOT wrap in markdown.
Use pytest. Mock external services (HTTP, DB) at the boundary.
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _generate(diff: str, changed_files: list[str]) -> dict:
    llm = get_llm("strong")
    files_summary = "\n".join(f"- {f}" for f in changed_files[:20])
    prompt = (
        f"Changed modules:\n{files_summary}\n\n"
        f"Combined diff (first 6000 chars):\n{diff[:6000]}"
    )
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def _modules_interact(diff: str, files: list[str]) -> bool:
    """Check if any changed file imports another changed file (basic heuristic)."""
    stems = [f.split("/")[-1].replace(".py", "") for f in files]
    for stem in stems:
        if re.search(rf"^[+].*import.*\b{re.escape(stem)}\b", diff, re.MULTILINE):
            return True
    return False


def run(state: PipelineState) -> dict:
    pr = state.pr
    risk = state.risk

    if risk is None or risk.level == RiskLevel.LOW:
        log.info("integration_test_agent_skipped", reason="low risk")
        return {}

    source_files = [
        f for f in pr.files_changed
        if re.search(r"\.(py|js|ts|go|java|rs)$", f)
        and not re.search(r"(test_|_test\.|spec\.)", f)
    ]

    if len(source_files) < 2:
        log.info("integration_test_agent_skipped", reason="single module changed")
        return {}

    if not _modules_interact(pr.diff, source_files):
        log.info("integration_test_agent_skipped", reason="no cross-module imports detected")
        return {}

    log.info("integration_test_agent_start", modules=len(source_files))

    try:
        data = _generate(pr.diff, source_files)
        new_test = GeneratedTest(
            module="integration",
            file_path=data.get("file_path", "tests/test_integration.py"),
            content=data.get("content", ""),
            language=data.get("language", "python"),
            description=data.get("description", ""),
        )
        existing = list(state.generated_tests)
        existing.append(new_test)
        log.info("integration_test_generated")
        return {"generated_tests": existing}
    except Exception as exc:
        log.warning("integration_test_generation_failed", error=str(exc))
        return {}
