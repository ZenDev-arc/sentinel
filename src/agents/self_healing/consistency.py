"""
Consistency Agent (on-write + weekly sweep)

Detects contradictions between KB entries:
  - Entry A says "always use library X" while Entry B says "library X is deprecated"
  - Two entries give opposite fix advice for the same pattern
  - A newer entry supersedes an older one on the same topic

Uses the LLM to compare pairs of entries that are semantically close
(cosine similarity > 0.85 from a preliminary vector search).
"""

from __future__ import annotations

import json
import re
from itertools import combinations

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.knowledge_base.models import KBEntry
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_SIMILARITY_THRESHOLD = 0.85
_SYSTEM = """You are SENTINEL's Consistency Agent for a code knowledge base.

Given two KB entries, determine if they contradict each other.

Return a JSON object:
{
  "contradicts": true | false,
  "reason": "<explanation if they contradict, empty string if not>",
  "keep_id": "<id of the entry to keep, or null if both are valid>",
  "deprecate_id": "<id of the entry to deprecate, or null>"
}

Contradiction means: following advice from Entry A would conflict with advice from Entry B
on the SAME code pattern, library choice, or fix approach.
Difference in scope or context is NOT a contradiction.

Return only the JSON. Do NOT wrap in markdown.
"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
def _compare(entry_a: KBEntry, entry_b: KBEntry) -> dict:
    llm = get_llm("fast")
    payload = {
        "entry_a": {
            "id": entry_a.id,
            "title": entry_a.title,
            "description": entry_a.description,
            "created_at": entry_a.created_at.isoformat(),
        },
        "entry_b": {
            "id": entry_b.id,
            "title": entry_b.title,
            "description": entry_b.description,
            "created_at": entry_b.created_at.isoformat(),
        },
    }
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=json.dumps(payload))]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def run(kb: KnowledgeBaseStore, repo: str | None = None) -> dict:
    log.info("consistency_agent_start")

    entries = kb.list_all(repo=repo, include_archived=False)
    if len(entries) < 2:
        return {"checked_pairs": 0, "contradictions_resolved": 0}

    # Find candidate pairs via vector proximity (use each entry's title as query)
    # Limit to avoid O(n²) LLM calls on large KBs
    candidate_pairs: list[tuple[KBEntry, KBEntry]] = []
    seen_pairs: set[frozenset] = set()

    for entry in entries[:100]:  # cap at 100 entries per run
        hits = kb.search(
            query=entry.title + " " + entry.description[:100],
            repo=repo or entry.repo,
            n_results=4,
        )
        for hit in hits:
            if hit.entry.id == entry.id:
                continue
            pair_key = frozenset([entry.id, hit.entry.id])
            if pair_key in seen_pairs:
                continue
            if hit.similarity >= _SIMILARITY_THRESHOLD:
                candidate_pairs.append((entry, hit.entry))
                seen_pairs.add(pair_key)

    checked = 0
    resolved = 0

    for entry_a, entry_b in candidate_pairs[:50]:  # cap LLM calls
        try:
            result = _compare(entry_a, entry_b)
            checked += 1
            if result.get("contradicts"):
                deprecate_id = result.get("deprecate_id")
                if deprecate_id in (entry_a.id, entry_b.id):
                    kb.mark_invalidated(
                        deprecate_id,
                        reason=f"Contradicts entry {result.get('keep_id')}: {result.get('reason', '')[:200]}",
                    )
                    resolved += 1
                    log.info(
                        "contradiction_resolved",
                        deprecated=deprecate_id,
                        kept=result.get("keep_id"),
                    )
        except Exception as exc:
            log.warning("consistency_check_failed", error=str(exc))

    result_summary = {"checked_pairs": checked, "contradictions_resolved": resolved}
    log.info("consistency_agent_done", **result_summary)
    return result_summary
