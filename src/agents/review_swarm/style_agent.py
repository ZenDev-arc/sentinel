"""
Style Reviewer Agent

Checks:
  - PEP 8 / language-specific naming conventions
  - Function / class complexity (too many args, deeply nested logic)
  - Dead code, unreachable branches, unused imports/variables
  - Missing docstrings on public APIs
  - Magic numbers without named constants
  - Inconsistency with project-specific conventions (derived from KB patterns)
  - Overly long functions (> ~50 lines of logic)
  - Boolean parameter flags that should be separate functions
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import FindingCategory, FindingSeverity, PipelineState, ReviewFinding
from src.knowledge_base.models import KBEntryType
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_SYSTEM = """You are SENTINEL's Style & Conventions Review Agent.

Analyse the diff for code quality, style, and maintainability issues.
Focus on added or modified lines. Be opinionated but practical.

Return a JSON array of findings:
{
  "title": "<issue>",
  "severity": "medium" | "low" | "info",
  "file_path": "<file>",
  "line_start": <int or null>,
  "line_end": <int or null>,
  "description": "<what and why>",
  "suggestion": "<concrete fix>"
}

Return [] if no issues. Do NOT wrap in markdown.

Style checklist:
- Naming: snake_case functions/vars, PascalCase classes, SCREAMING_SNAKE constants
- No bare `except:` — always catch specific exceptions
- No mutable default arguments (def f(x=[]) is a Python footgun)
- No `import *`
- Boolean flag parameters (def f(is_fast=True)) → split into two functions
- Overly long function > 60 lines of logic
- Missing type annotations on public function signatures
- Repeated logic that should be extracted into a helper
- Magic numbers (use named constants)
- Commented-out code blocks (delete or explain)
- TODO/FIXME without a ticket reference
- Docstring missing on public classes/functions
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _llm_review(diff: str, kb_context: str) -> list[dict]:
    llm = get_llm("fast")
    prompt = ""
    if kb_context:
        prompt += f"Project-specific style patterns:\n{kb_context}\n\n"
    prompt += f"Diff:\n{diff[:6000]}"
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def run(state: PipelineState, kb: KnowledgeBaseStore) -> dict:
    pr = state.pr
    log.info("style_agent_start", repo=pr.repo_full_name, pr=pr.pr_number)

    kb_hits = kb.search(
        query=f"naming convention style code quality {pr.repo_full_name}",
        repo=pr.repo_full_name,
        n_results=3,
        entry_type=KBEntryType.CODEBASE_PATTERN,
    )
    kb_context = "\n".join(
        f"- {h.entry.title}: {h.entry.payload.get('pattern', '')[:120]}"
        for h in kb_hits
    )

    try:
        raw = _llm_review(pr.diff, kb_context)
    except Exception as exc:
        log.warning("style_agent_llm_failed", error=str(exc))
        raw = []

    findings: list[ReviewFinding] = []
    for item in raw:
        try:
            sev_str = item.get("severity", "low").lower()
            sev = FindingSeverity(sev_str) if sev_str in FindingSeverity._value2member_map_ else FindingSeverity.LOW
            findings.append(
                ReviewFinding(
                    category=FindingCategory.STYLE,
                    severity=sev,
                    file_path=item.get("file_path", ""),
                    line_start=item.get("line_start"),
                    line_end=item.get("line_end"),
                    title=item.get("title", "Style finding"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", ""),
                    kb_hit_ids=[h.entry.id for h in kb_hits],
                )
            )
        except Exception as exc:
            log.warning("style_finding_parse_error", error=str(exc))

    for hit in kb_hits:
        kb.record_use(hit.entry.id)

    log.info("style_agent_done", count=len(findings))
    return {"style_findings": findings}
