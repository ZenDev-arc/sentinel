"""
Per-Module Test Generation Agent

For each changed file/module in the PR, generates or extends unit tests:
  - Identifies the testing framework already in use (pytest, unittest, jest, etc.)
  - Generates tests for new/modified functions and classes
  - Covers happy path, edge cases, and expected failures
  - Matches the project's existing test conventions (fixtures, factories, mocking patterns)
  - Never overwrites existing tests — only adds missing ones
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import GeneratedTest, PipelineState
from src.knowledge_base.models import KBEntryType
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_SYSTEM = """You are SENTINEL's Test Generation Agent.

Given a code diff for one module, write unit tests that cover the new and modified code.

Rules:
- Match the testing framework and style already visible in the diff or file.
  Default to pytest with type annotations if framework is unclear.
- Test new/modified functions: happy path + at least 2 edge cases each.
- Use mocks for external dependencies (DB, HTTP, filesystem).
- Do NOT reproduce existing tests — only fill gaps.
- Tests must be immediately runnable (correct imports, fixtures defined).
- Keep each test function focused on one behaviour.

Respond in TWO parts separated by the exact line ---CODE---

Part 1: a JSON object (no markdown fences):
{"module": "<module path>", "language": "python", "file_path": "<test file path>", "description": "<one sentence>"}

---CODE---

Part 2: the complete test file content (raw source, no fences).
"""


def _extract_json(text: str) -> dict:
    """Extract the first JSON object from LLM output robustly."""
    text = text.strip()
    # Strip markdown code fences
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find the outermost {...} block
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("Unterminated JSON object in response")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _generate_tests(module_diff: str, module_path: str, kb_context: str) -> dict:
    llm = get_llm("strong")
    prompt = ""
    if kb_context:
        prompt += f"Testing patterns for this repo:\n{kb_context}\n\n"
    prompt += f"Module: {module_path}\n\nDiff:\n{module_diff[:5000]}"
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
    )
    text = response.content.strip()
    if "---CODE---" in text:
        meta_part, code_part = text.split("---CODE---", 1)
        data = _extract_json(meta_part)
        data["content"] = code_part.strip()
        return data
    # Fallback: whole response as JSON (old format)
    return _extract_json(text)


def _extract_module_diff(full_diff: str, file_path: str) -> str:
    """Pull out the section of the unified diff for one specific file."""
    lines = full_diff.splitlines(keepends=True)
    in_file = False
    chunk: list[str] = []
    for line in lines:
        if line.startswith("diff --git"):
            in_file = file_path in line
        if in_file:
            chunk.append(line)
    return "".join(chunk) or full_diff[:3000]


def run(state: PipelineState, kb: KnowledgeBaseStore) -> dict:
    pr = state.pr
    log.info(
        "module_test_agent_start", repo=pr.repo_full_name, files=len(pr.files_changed)
    )

    # Only generate tests for source files (skip test files, docs, configs)
    testable_files = [
        f
        for f in pr.files_changed
        if not re.search(
            r"(test_|_test\.|spec\.|\.md$|\.yaml$|\.yml$|\.json$|\.lock$)", f
        )
        and re.search(r"\.(py|js|ts|jsx|tsx|mjs|go|java|rs|rb|cs)$", f)
    ]

    if not testable_files:
        log.info("module_test_agent_no_testable_files")
        return {"generated_tests": []}

    kb_hits = kb.search(
        query=f"test pattern fixture mock {pr.repo_full_name}",
        repo=pr.repo_full_name,
        n_results=3,
        entry_type=KBEntryType.TEST_PATTERN,
    )
    kb_context = "\n".join(
        f"- {h.entry.title}: {h.entry.payload.get('pattern', '')[:200]}"
        for h in kb_hits
    )

    generated: list[GeneratedTest] = []
    for file_path in testable_files[:10]:  # cap at 10 modules per PR
        module_diff = _extract_module_diff(pr.diff, file_path)
        if len(module_diff) < 50:
            continue
        try:
            data = _generate_tests(module_diff, file_path, kb_context)
            generated.append(
                GeneratedTest(
                    module=data.get("module", file_path),
                    file_path=data.get(
                        "file_path", f"tests/test_{file_path.split('/')[-1]}"
                    ),
                    content=data.get("content", ""),
                    language=data.get("language", "python"),
                    description=data.get("description", ""),
                )
            )
            log.info("test_generated", module=file_path)
        except Exception as exc:
            log.warning("test_generation_failed", module=file_path, error=str(exc))

    for hit in kb_hits:
        kb.record_use(hit.entry.id)

    log.info("module_test_agent_done", generated=len(generated))
    return {"generated_tests": generated}
