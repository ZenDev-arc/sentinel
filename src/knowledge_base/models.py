"""
Pydantic models for Knowledge Base entries.
Every entry carries confidence metadata so the self-healing agents can
decay, invalidate, and consolidate without touching unrelated records.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class KBEntryType(str, Enum):
    BUG_FIX = "bug_fix"
    REVIEW_OUTCOME = "review_outcome"
    CODEBASE_PATTERN = "codebase_pattern"
    TEST_PATTERN = "test_pattern"


class ReviewOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IGNORED = "ignored"
    PENDING = "pending"


class KBEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: KBEntryType

    # Human-readable
    title: str
    description: str

    # Payload differs by type
    payload: dict[str, Any] = Field(default_factory=dict)

    # Provenance
    repo: str
    pr_number: int | None = None
    commit_sha: str | None = None
    file_paths: list[str] = Field(default_factory=list)

    # Outcome tracking (updated after human review)
    outcome: ReviewOutcome = ReviewOutcome.PENDING
    rejection_count: int = 0
    use_count: int = 0

    # Confidence / decay
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None

    # Code snapshot for drift detection
    code_snapshot_hash: str | None = None

    # Self-healing flags
    archived: bool = False
    invalidated: bool = False
    invalidation_reason: str | None = None

    # Consolidation — if merged into another entry
    superseded_by: str | None = None

    def is_active(self) -> bool:
        return not self.archived and not self.invalidated and self.superseded_by is None

    def decay_confidence(self, days_since_use: int, decay_rate: float = 0.02) -> float:
        """Exponential confidence decay. Returns new confidence value."""
        new_confidence = self.confidence * ((1 - decay_rate) ** days_since_use)
        return max(0.0, new_confidence)


class KBSearchResult(BaseModel):
    entry: KBEntry
    similarity: float
    distance: float


class BugFixPayload(BaseModel):
    """Payload for KBEntryType.BUG_FIX entries."""

    failing_test: str
    root_cause: str
    patch: str
    affected_files: list[str] = Field(default_factory=list)
    patch_verified: bool = False
    reverted: bool = False


class ReviewOutcomePayload(BaseModel):
    """Payload for KBEntryType.REVIEW_OUTCOME entries."""

    category: str
    severity: str
    suggestion: str
    outcome: ReviewOutcome = ReviewOutcome.PENDING
    human_notes: str = ""


class CodebasePatternPayload(BaseModel):
    """Payload for KBEntryType.CODEBASE_PATTERN entries."""

    pattern: str
    examples: list[str] = Field(default_factory=list)
    anti_examples: list[str] = Field(default_factory=list)
    enforcement: str = ""
