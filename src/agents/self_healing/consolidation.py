"""
Consolidation Agent (weekly)

Clusters near-duplicate KB entries into generalised patterns:
  - Groups entries by semantic similarity > 0.90
  - For each group, generates one canonical "pattern" entry
  - Marks the individual entries as superseded_by the new canonical entry
  - Keeps the KB compact and prevents index bloat

Only runs when the KB has > 50 active entries to make clustering meaningful.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.llm import get_llm
from src.core.logging import get_logger
from src.knowledge_base.models import KBEntry, KBEntryType
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

_CLUSTER_SIMILARITY = 0.90
_MIN_CLUSTER_SIZE = 3
_MIN_KB_SIZE = 50

_SYSTEM = """You are SENTINEL's Consolidation Agent for a code knowledge base.

Given a cluster of similar KB entries, produce ONE generalised canonical entry
that captures the common pattern across all of them.

Return a JSON object:
{
  "title": "<generalised title>",
  "description": "<generalised description capturing the common pattern>",
  "type": "<keep the most common type from the cluster>",
  "payload": {
    "pattern": "<the generalised pattern>",
    "examples": ["<example 1>", "<example 2>"]
  }
}

The canonical entry should be more general than any individual entry.
Return only the JSON. Do NOT wrap in markdown.
"""


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
def _generalise(cluster: list[KBEntry]) -> dict:
    llm = get_llm("fast")
    payload = [
        {"id": e.id, "title": e.title, "description": e.description[:200]}
        for e in cluster
    ]
    response = llm.invoke(
        [SystemMessage(content=_SYSTEM), HumanMessage(content=json.dumps(payload))]
    )
    text = response.content.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def run(kb: KnowledgeBaseStore, repo: str | None = None) -> dict:
    log.info("consolidation_agent_start")

    entries = kb.list_all(repo=repo, include_archived=False)
    if len(entries) < _MIN_KB_SIZE:
        log.info("consolidation_skipped", reason="KB too small", size=len(entries))
        return {"clusters_found": 0, "entries_consolidated": 0}

    # Build clusters using a greedy single-link approach
    # Each entry queries the KB for near-duplicates
    cluster_map: dict[str, set[str]] = {}  # representative_id -> member ids
    assigned: set[str] = set()

    for entry in entries:
        if entry.id in assigned:
            continue
        hits = kb.search(
            query=entry.title + " " + entry.description[:100],
            repo=repo or entry.repo,
            n_results=10,
        )
        cluster_members = {
            h.entry.id for h in hits
            if h.similarity >= _CLUSTER_SIMILARITY and h.entry.id != entry.id
            and h.entry.id not in assigned
        }
        if len(cluster_members) >= _MIN_CLUSTER_SIZE - 1:
            cluster_members.add(entry.id)
            cluster_map[entry.id] = cluster_members
            assigned.update(cluster_members)

    clusters_found = len(cluster_map)
    consolidated_count = 0

    for rep_id, member_ids in cluster_map.items():
        members = [e for e in entries if e.id in member_ids]
        if not members:
            continue

        try:
            canonical_data = _generalise(members)
        except Exception as exc:
            log.warning("generalise_failed", error=str(exc))
            continue

        # Determine repo from members
        repo_name = members[0].repo

        canonical = KBEntry(
            type=KBEntryType(canonical_data.get("type", KBEntryType.CODEBASE_PATTERN.value)),
            title=canonical_data.get("title", f"Generalised pattern (cluster {rep_id[:8]})"),
            description=canonical_data.get("description", ""),
            payload=canonical_data.get("payload", {}),
            repo=repo_name,
            confidence=1.0,
        )
        kb.upsert(canonical)

        # Mark all cluster members as superseded
        for member in members:
            updated = member.model_copy(update={
                "superseded_by": canonical.id,
                "archived": True,
                "invalidation_reason": f"Consolidated into canonical entry {canonical.id}",
            })
            kb.upsert(updated)
            consolidated_count += 1

        log.info(
            "cluster_consolidated",
            canonical_id=canonical.id,
            members=len(members),
        )

    result = {
        "clusters_found": clusters_found,
        "entries_consolidated": consolidated_count,
    }
    log.info("consolidation_agent_done", **result)
    return result
