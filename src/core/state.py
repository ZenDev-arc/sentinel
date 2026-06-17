"""
Shared pipeline state — the single source of truth passed between every agent.
All fields are optional so partial updates merge cleanly in LangGraph.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# ── Enumerations ──────────────────────────────────────────────────────────────


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FindingSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingCategory(str, Enum):
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    ARCHITECTURE = "architecture"
    TEST = "test"
    BUG = "bug"


class FixClassification(str, Enum):
    AUTO_MERGE = "auto_merge"
    HUMAN_REQUIRED = "human_required"


class PipelineStatus(str, Enum):
    INITIALIZING = "initializing"
    TRIAGING = "triaging"
    REVIEWING = "reviewing"
    TESTING = "testing"
    BUG_HUNTING = "bug_hunting"
    ANNOTATING = "annotating"
    GATING = "gating"
    REPORTING = "reporting"
    DONE = "done"
    FAILED = "failed"


# ── Sub-models ────────────────────────────────────────────────────────────────


class PRMetadata(BaseModel):
    repo_full_name: str
    pr_number: int
    pr_title: str
    pr_body: str
    base_branch: str
    head_branch: str
    head_sha: str
    author: str
    files_changed: list[str] = Field(default_factory=list)
    diff: str = ""
    additions: int = 0
    deletions: int = 0
    installation_id: int | None = None


class RegressionMatch(BaseModel):
    """Evidence that a finding matches a previously-fixed bug in the KB."""

    kb_entry_id: str
    original_pr: int | None
    original_repo: str
    original_fix_summary: str
    similarity: float
    fixed_at: datetime


class ReviewFinding(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: FindingCategory
    severity: FindingSeverity
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    title: str
    description: str
    suggestion: str = ""
    rationale: str = ""
    kb_hit_ids: list[str] = Field(default_factory=list)
    is_regression: bool = False
    regression: RegressionMatch | None = None


class TestResult(BaseModel):
    module: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    coverage_percent: float | None = None
    failing_tests: list[str] = Field(default_factory=list)
    stdout: str = ""
    stderr: str = ""


class GeneratedTest(BaseModel):
    module: str
    file_path: str
    content: str
    language: str = "python"
    description: str = ""


class BugReport(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    failing_test: str
    minimal_repro: str = ""
    root_cause: str = ""
    affected_files: list[str] = Field(default_factory=list)
    candidate_patches: list[dict[str, Any]] = Field(default_factory=list)
    selected_patch: dict[str, Any] | None = None
    verified: bool = False


class ProposedFix(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    patch: str
    affected_files: list[str]
    classification: FixClassification
    rationale: str = ""
    applied: bool = False
    commit_sha: str | None = None


class RiskScore(BaseModel):
    level: RiskLevel
    score: float
    reasons: list[str] = Field(default_factory=list)
    sensitive_areas: list[str] = Field(default_factory=list)


# ── Main pipeline state ───────────────────────────────────────────────────────


class PipelineState(BaseModel):
    """Complete state flowing through the LangGraph pipeline."""

    # Identity
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = Field(default_factory=datetime.utcnow)
    status: PipelineStatus = PipelineStatus.INITIALIZING

    # Token usage (populated by node_finalise from the in-thread ContextVar tracker)
    token_total: int = 0
    est_cost_usd: float = 0.0

    # Input
    pr: PRMetadata | None = None
    # Raw tar.gz bytes of the repo at PR head — fetched once by node_run_tests,
    # reused by verification_agent to apply/test patches without re-downloading.
    repo_archive: bytes | None = None

    # Triage
    risk: RiskScore | None = None

    # Review swarm outputs
    security_findings: list[ReviewFinding] = Field(default_factory=list)
    performance_findings: list[ReviewFinding] = Field(default_factory=list)
    style_findings: list[ReviewFinding] = Field(default_factory=list)
    architecture_findings: list[ReviewFinding] = Field(default_factory=list)
    consolidated_findings: list[ReviewFinding] = Field(default_factory=list)

    # Test swarm outputs
    generated_tests: list[GeneratedTest] = Field(default_factory=list)
    test_results: list[TestResult] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)

    # Bug squad outputs
    bug_reports: list[BugReport] = Field(default_factory=list)

    # Trust layer outputs
    proposed_fixes: list[ProposedFix] = Field(default_factory=list)
    auto_applied_fixes: list[ProposedFix] = Field(default_factory=list)
    pending_human_fixes: list[ProposedFix] = Field(default_factory=list)

    # Final report
    pr_comment: str = ""

    # Errors / warnings accumulated during run
    errors: list[str] = Field(default_factory=list)

    # When True, always run the full review swarm regardless of risk level
    force_review: bool = False

    # Per-repo policy loaded from sentinel.yaml at the start of each run.
    # Typed as Any to avoid a circular import with src.core.policy.
    # Callers cast: from src.core.policy import SentinelPolicy; policy: SentinelPolicy = state.policy
    policy: Any = None

    def has_test_failures(self) -> bool:
        return any(
            r.failed > 0 or r.errors > 0 or len(r.failing_tests) > 0
            for r in self.test_results
        )

    def all_findings(self) -> list[ReviewFinding]:
        return (
            self.security_findings
            + self.performance_findings
            + self.style_findings
            + self.architecture_findings
        )

    def model_dump_safe(self) -> dict[str, Any]:
        """Serialize for logging — truncates large diff/patch fields."""
        d = self.model_dump(exclude={"repo_archive"})
        if d.get("pr") and d["pr"].get("diff"):
            d["pr"]["diff"] = d["pr"]["diff"][:500] + "…"
        return d
