"""
Token usage tracker — collects LLM token counts across all agents in a pipeline run.

Uses a module-level variable (not ContextVar) so the tracker is visible across
all threads including LangGraph's parallel-node thread pool.

Usage:
    # Pipeline sets up a tracker at the start of each run (node_load_policy)
    set_tracker(RunTokenTracker())

    # node_finalise reads totals (still in the pipeline thread) and stores in state
    tracker = get_tracker()
    total = tracker.total_tokens  # across all agents
"""

from __future__ import annotations

import threading

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# Blended cost estimate (Groq llama-3.3-70b-versatile ≈ $0.59/1M input + $0.79/1M output,
# fast model ≈ $0.05/1M — we use a conservative midpoint of ~$0.09/1M tokens)
_COST_PER_TOKEN = 9e-8


class RunTokenTracker:
    """Thread-safe accumulator for one pipeline run's LLM token usage."""

    def __init__(self) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self._lock = threading.Lock()

    def add(self, prompt: int, completion: int) -> None:
        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def est_cost_usd(self) -> float:
        return round(self.total_tokens * _COST_PER_TOKEN, 6)


# Module-level tracker — set once per pipeline run, readable from all threads.
# Pipelines run one at a time per process (via asyncio.to_thread), so a single
# global is sufficient. Protected by a lock for safety.
_lock = threading.Lock()
_current: RunTokenTracker | None = None


def set_tracker(tracker: RunTokenTracker) -> None:
    global _current
    with _lock:
        _current = tracker


def get_tracker() -> RunTokenTracker | None:
    return _current


class SentinelTokenCallback(BaseCallbackHandler):
    """
    LangChain callback that records token usage into the active RunTokenTracker.
    Reads the module-level tracker so it works across all threads in the pipeline.
    """

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        tracker = _current
        if tracker is None:
            return

        for gen_list in response.generations:
            for gen in gen_list:
                meta: dict = {}
                if hasattr(gen, "message"):
                    meta = getattr(gen.message, "response_metadata", {}) or {}
                usage = meta.get("usage") or meta.get("token_usage") or {}
                if usage:
                    tracker.add(
                        int(usage.get("prompt_tokens", 0)),
                        int(usage.get("completion_tokens", 0)),
                    )
                    return
