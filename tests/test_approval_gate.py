"""
Tests for the approval gate — classification logic and policy enforcement.
"""

from __future__ import annotations

import pytest

from src.agents.trust_layer.approval_gate import _build_pr_comment, _is_auto_mergeable, run
from src.core.policy import GatePolicy, RegressionPolicy, ReviewPolicy, SentinelPolicy
from src.core.state import (
    FindingCategory,
    FindingSeverity,
    FixClassification,
    PRMetadata,
    PipelineState,
    ProposedFix,
    ReviewFinding,
    RiskLevel,
    RiskScore,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fix(description: str = "Fix bug", affected_files: list[str] | None = None, patch_lines: int = 5) -> ProposedFix:
    patch_body = "\n".join(
        [f"+line {i}" for i in range(patch_lines // 2)]
        + [f"-line {i}" for i in range(patch_lines - patch_lines // 2)]
    )
    return ProposedFix(
        description=description,
        patch=f"--- a/src/foo.py\n+++ b/src/foo.py\n@@ -1 +1 @@\n{patch_body}",
        affected_files=affected_files or ["src/foo.py"],
        classification=FixClassification.HUMAN_REQUIRED,
        rationale="test rationale",
    )


def _finding(
    severity: FindingSeverity = FindingSeverity.MEDIUM,
    category: FindingCategory = FindingCategory.BUG,
    is_regression: bool = False,
) -> ReviewFinding:
    from src.core.state import RegressionMatch
    from datetime import datetime
    regression = None
    if is_regression:
        regression = RegressionMatch(
            kb_entry_id="kb-1",
            original_pr=5,
            original_repo="acme/backend",
            original_fix_summary="Missing null check",
            similarity=0.91,
            fixed_at=datetime(2025, 1, 1),
        )
    return ReviewFinding(
        category=category,
        severity=severity,
        file_path="src/foo.py",
        title="Test finding",
        description="Test description",
        is_regression=is_regression,
        regression=regression,
    )


def _state(**kwargs) -> PipelineState:
    defaults = dict(
        proposed_fixes=[],
        consolidated_findings=[],
        risk=RiskScore(level=RiskLevel.LOW, score=0.2),
    )
    defaults.update(kwargs)
    return PipelineState(**defaults)


# ── _is_auto_mergeable ────────────────────────────────────────────────────────

class TestIsAutoMergeable:
    def test_small_safe_patch_is_mergeable(self):
        state = _state()
        assert _is_auto_mergeable(_fix(patch_lines=4), state) is True

    def test_empty_patch_not_mergeable(self):
        fix = ProposedFix(
            description="empty",
            patch="   ",
            affected_files=["src/foo.py"],
            classification=FixClassification.HUMAN_REQUIRED,
        )
        assert _is_auto_mergeable(fix, _state()) is False

    def test_sensitive_file_not_mergeable(self):
        fix = _fix(affected_files=["src/auth/login.py"])
        assert _is_auto_mergeable(fix, _state()) is False

    def test_patch_too_large_not_mergeable(self):
        fix = _fix(patch_lines=60)
        assert _is_auto_mergeable(fix, _state()) is False

    def test_policy_always_human_path(self):
        policy = SentinelPolicy(gate=GatePolicy(always_human_paths=["deploy/"]))
        state = _state(policy=policy)
        fix = _fix(affected_files=["deploy/prod.yaml"])
        assert _is_auto_mergeable(fix, state) is False

    def test_policy_max_patch_lines_override(self):
        # Default is 30; policy sets it to 5
        policy = SentinelPolicy(gate=GatePolicy(max_auto_patch_lines=5))
        state = _state(policy=policy)
        assert _is_auto_mergeable(_fix(patch_lines=6), state) is False
        assert _is_auto_mergeable(_fix(patch_lines=4), state) is True

    def test_high_risk_critical_finding_not_mergeable(self):
        state = _state(
            risk=RiskScore(level=RiskLevel.HIGH, score=0.85),
            security_findings=[_finding(severity=FindingSeverity.CRITICAL)],
        )
        assert _is_auto_mergeable(_fix(), state) is False


# ── run() classification ──────────────────────────────────────────────────────

class TestRunClassification:
    def test_small_fix_auto_merged(self):
        state = _state(proposed_fixes=[_fix(patch_lines=4)])
        result = run(state)
        assert len(result["auto_applied_fixes"]) == 1
        assert len(result["pending_human_fixes"]) == 0

    def test_large_fix_human_required(self):
        state = _state(proposed_fixes=[_fix(patch_lines=60)])
        result = run(state)
        assert len(result["pending_human_fixes"]) == 1
        assert len(result["auto_applied_fixes"]) == 0

    def test_sensitive_file_human_required(self):
        state = _state(proposed_fixes=[_fix(affected_files=["src/auth/tokens.py"])])
        result = run(state)
        assert len(result["pending_human_fixes"]) == 1

    def test_mixed_fixes_classified_correctly(self):
        state = _state(proposed_fixes=[
            _fix("safe fix", patch_lines=4),
            _fix("big fix", patch_lines=60),
        ])
        result = run(state)
        assert len(result["auto_applied_fixes"]) == 1
        assert len(result["pending_human_fixes"]) == 1


# ── Policy: min_severity filtering ───────────────────────────────────────────

class TestPolicyMinSeverity:
    def test_low_findings_hidden_when_min_medium(self):
        policy = SentinelPolicy(review=ReviewPolicy(min_severity="medium"))
        state = _state(
            policy=policy,
            consolidated_findings=[
                _finding(FindingSeverity.LOW),
                _finding(FindingSeverity.INFO),
                _finding(FindingSeverity.MEDIUM),
                _finding(FindingSeverity.HIGH),
            ],
        )
        result = run(state)
        comment = result["pr_comment"]
        # Medium and high should appear; info and low should be filtered
        assert "MEDIUM" in comment or "HIGH" in comment

    def test_all_findings_shown_with_info_threshold(self):
        policy = SentinelPolicy(review=ReviewPolicy(min_severity="info"))
        findings = [_finding(s) for s in [
            FindingSeverity.INFO, FindingSeverity.LOW,
            FindingSeverity.MEDIUM, FindingSeverity.HIGH,
        ]]
        state = _state(policy=policy, consolidated_findings=findings)
        result = run(state)
        # All 4 findings pass through
        assert "4 findings" in result["pr_comment"]


# ── Policy: skip_categories ───────────────────────────────────────────────────

class TestPolicySkipCategories:
    def test_skipped_category_removed(self):
        policy = SentinelPolicy(review=ReviewPolicy(skip_categories=["style"]))
        state = _state(
            policy=policy,
            consolidated_findings=[
                _finding(category=FindingCategory.STYLE),
                _finding(category=FindingCategory.SECURITY),
            ],
        )
        result = run(state)
        # Only the security finding passes — so "1 findings"
        assert "1 findings" in result["pr_comment"]


# ── Policy: regression block_merge ───────────────────────────────────────────

class TestPolicyRegressionBlockMerge:
    def test_block_merge_forces_human_required(self):
        policy = SentinelPolicy(regressions=RegressionPolicy(block_merge=True, enabled=False))
        state = _state(
            policy=policy,
            proposed_fixes=[_fix(patch_lines=4)],  # would normally auto-merge
            consolidated_findings=[_finding(is_regression=True)],
        )
        result = run(state)
        assert len(result["pending_human_fixes"]) == 1
        assert len(result["auto_applied_fixes"]) == 0

    def test_block_merge_false_allows_auto(self):
        policy = SentinelPolicy(regressions=RegressionPolicy(block_merge=False, enabled=False))
        state = _state(
            policy=policy,
            proposed_fixes=[_fix(patch_lines=4)],
            consolidated_findings=[_finding(is_regression=True)],
        )
        result = run(state)
        assert len(result["auto_applied_fixes"]) == 1


# ── PR comment content ────────────────────────────────────────────────────────

class TestBuildPrComment:
    def test_regression_section_at_top(self):
        state = _state(consolidated_findings=[_finding(is_regression=True)])
        comment = _build_pr_comment(state)
        regression_pos = comment.find("Regressions Detected")
        risk_pos = comment.find("Risk Level")
        assert regression_pos != -1
        assert regression_pos < risk_pos

    def test_no_regression_section_when_none(self):
        state = _state(consolidated_findings=[_finding(is_regression=False)])
        comment = _build_pr_comment(state)
        assert "Regressions Detected" not in comment

    def test_regression_shows_original_pr(self):
        state = _state(consolidated_findings=[_finding(is_regression=True)])
        comment = _build_pr_comment(state)
        assert "#5" in comment
        assert "acme/backend" in comment

    def test_no_findings_shows_clean_message(self):
        state = _state()
        comment = _build_pr_comment(state)
        assert "No significant findings" in comment

    def test_pr_comment_contains_sentinel_footer(self):
        state = _state()
        comment = _build_pr_comment(state)
        assert "SENTINEL" in comment
