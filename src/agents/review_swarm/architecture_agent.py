"""
Architecture Reviewer Agent

Looks for structural and design-level issues:
  - Layering violations (e.g. a model importing from a view/controller)
  - Circular dependencies between modules
  - Single Responsibility Principle violations (classes doing too much)
  - Tight coupling / missing abstractions (direct instantiation of concrete classes)
  - Feature envy (a class that constantly accesses another's internals)
  - Premature abstractions (over-engineered for current requirements)
  - Missing error boundaries / exception propagation design
  - Breaking changes to public interfaces without versioning
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import (
    FindingCategory,
    FindingSeverity,
    PipelineState,
    ReviewFinding,
)
from src.knowledge_base.models import KBEntryType
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_SYSTEM = """You are SENTINEL's Architecture Review Agent — a principal engineer focused on
system design, module boundaries, and long-term maintainability.

Analyse the diff for architectural and design-level issues.

Return a JSON array of findings:
{
  "title": "<architectural issue>",
  "severity": "high" | "medium" | "low",
  "file_path": "<file>",
  "line_start": <int or null>,
  "line_end": <int or null>,
  "description": "<what the issue is and why it matters at scale>",
  "suggestion": "<recommended design change>"
}

Return [] if no issues. Do NOT wrap in markdown.

Architecture checklist:
- Layering: models should not import from views; services should not import from HTTP handlers
- Circular imports between modules
- God classes / god functions (one unit doing 5+ distinct things)
- Tight coupling: new code directly instantiating concrete dependencies that should be injected
- Feature envy: class A accessing B.x.y.z chains
- Missing abstraction: repeated ad-hoc logic that should be a shared interface
- Public API changes without deprecation path or version bump
- Direct database access from presentation layer
- Business logic leaking into data access layer
- State mutation through global variables or singletons
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _llm_review(diff: str, kb_context: str) -> list[dict]:
    llm = get_llm("fast")
    prompt = ""
    if kb_context:
        prompt += f"Known architectural patterns for this repo:\n{kb_context}\n\n"
    prompt += f"Diff:\n{diff[:7000]}"
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def run(state: PipelineState, kb: KnowledgeBaseStore) -> dict:
    pr = state.pr
    log.info("architecture_agent_start", repo=pr.repo_full_name, pr=pr.pr_number)

    # Skip only for trivially small diffs — architecture issues can appear at any risk level
    if state.pr and state.pr.additions < 10:
        log.info("architecture_agent_skipped", reason="trivially small diff")
        return {"architecture_findings": []}

    kb_hits = kb.search(
        query=f"architecture layer violation circular dependency {pr.pr_title}",
        repo=pr.repo_full_name,
        n_results=3,
        entry_type=KBEntryType.CODEBASE_PATTERN,
    )
    kb_context = "\n".join(
        f"- {h.entry.title}: {h.entry.description[:120]}" for h in kb_hits
    )

    try:
        raw = _llm_review(pr.diff, kb_context)
    except Exception as exc:
        log.warning("architecture_agent_llm_failed", error=str(exc))
        raw = []

    findings: list[ReviewFinding] = []
    for item in raw:
        try:
            sev_str = item.get("severity", "medium").lower()
            sev = (
                FindingSeverity(sev_str)
                if sev_str in FindingSeverity._value2member_map_
                else FindingSeverity.MEDIUM
            )
            findings.append(
                ReviewFinding(
                    category=FindingCategory.ARCHITECTURE,
                    severity=sev,
                    file_path=item.get("file_path", ""),
                    line_start=item.get("line_start"),
                    line_end=item.get("line_end"),
                    title=item.get("title", "Architecture finding"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", ""),
                    kb_hit_ids=[h.entry.id for h in kb_hits],
                )
            )
        except Exception as exc:
            log.warning("architecture_finding_parse_error", error=str(exc))

    for hit in kb_hits:
        kb.record_use(hit.entry.id)

    log.info("architecture_agent_done", count=len(findings))
    return {"architecture_findings": findings}
