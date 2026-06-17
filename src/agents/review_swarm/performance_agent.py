"""
Performance Reviewer Agent

Detects:
  - N+1 query patterns (ORM loops)
  - Unnecessary allocations / copies in hot paths
  - Blocking calls in async code (sync I/O inside async def)
  - Missing pagination / unbounded queries
  - Inefficient data structures (list.index() in loop, repeated set membership)
  - Memory leaks (unclosed resources, circular references with __del__)
  - Redundant DB hits (same query called multiple times without caching)
  - Expensive operations inside loop bodies that could be hoisted
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.core.state import (FindingCategory, FindingSeverity, PipelineState,
                            ReviewFinding)
from src.knowledge_base.models import KBEntryType
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_SYSTEM = """You are SENTINEL's Performance Review Agent — a senior engineer specialising in
application performance, database efficiency, and async programming.

Analyse the git diff for performance issues in ADDED or MODIFIED lines only.
Be aggressive — flag potential issues even if they only matter at moderate scale.

Return a JSON array of findings:
{
  "title": "<concise issue title>",
  "severity": "critical" | "high" | "medium" | "low" | "info",
  "file_path": "<file>",
  "line_start": <int or null>,
  "line_end": <int or null>,
  "description": "<what the problem is, quantify impact where possible>",
  "suggestion": "<specific fix with before/after code>"
}

Return [] only if the diff has zero performance concerns. Do NOT wrap in markdown.

Python/backend checklist:
- N+1 queries: any ORM call inside a loop (use select_related/prefetch_related/bulk ops)
- Unbounded queries: .all() or .filter() without .limit() — will break at scale
- Blocking sync I/O inside async def (requests.get, open(), time.sleep)
- Repeated identical DB/API calls — lift above loop or cache
- O(n²) nested loops over collections
- List comprehension where a generator suffices (large datasets)
- String concatenation in loops (use ''.join())
- Missing index on new filter/order_by fields
- Loading entire large file into memory (use streaming/chunking)
- Redundant serialisation/deserialisation in hot paths
- Sorting inside a loop (sort once outside)
- Re-compiling regex inside a loop (compile once at module level)

JavaScript/TypeScript checklist:
- Expensive computation in render (missing useMemo/useCallback)
- setState in a loop causing multiple re-renders
- Large arrays passed as props without memoization
- Missing key prop on list items (causes full re-render)
- Fetching data without caching/deduplication (use SWR/React Query)
- Synchronous operations blocking the event loop
- Large bundle imports (import entire lodash vs import { X } from 'lodash/X')
"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _llm_review(diff: str, kb_context: str) -> list[dict]:
    llm = get_llm("fast")
    prompt = ""
    if kb_context:
        prompt += f"Past performance findings for this repo:\n{kb_context}\n\n"
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
    log.info("performance_agent_start", repo=pr.repo_full_name, pr=pr.pr_number)

    kb_hits = kb.search(
        query=f"performance N+1 slow query {pr.pr_title}",
        repo=pr.repo_full_name,
        n_results=3,
        entry_type=KBEntryType.REVIEW_OUTCOME,
    )
    kb_context = "\n".join(
        f"- {h.entry.title}: {h.entry.description[:120]}" for h in kb_hits
    )

    try:
        raw = _llm_review(pr.diff, kb_context)
    except Exception as exc:
        log.warning("performance_agent_llm_failed", error=str(exc))
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
                    category=FindingCategory.PERFORMANCE,
                    severity=sev,
                    file_path=item.get("file_path", ""),
                    line_start=item.get("line_start"),
                    line_end=item.get("line_end"),
                    title=item.get("title", "Performance finding"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", ""),
                    kb_hit_ids=[h.entry.id for h in kb_hits],
                )
            )
        except Exception as exc:
            log.warning("performance_finding_parse_error", error=str(exc))

    for hit in kb_hits:
        kb.record_use(hit.entry.id)

    log.info("performance_agent_done", count=len(findings))
    return {"performance_findings": findings}
