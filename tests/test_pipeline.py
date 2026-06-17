"""
Integration tests for the LangGraph pipeline.
Uses mocked agents to verify graph topology (routing, state flow)
without making real LLM or API calls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.pipeline import build_graph
from src.core.state import (FindingCategory, FindingSeverity, PipelineState,
                            PipelineStatus, PRMetadata, ReviewFinding,
                            RiskLevel, RiskScore, TestResult)


def _make_initial_state(
    files: list[str] | None = None,
    additions: int = 50,
) -> PipelineState:
    return PipelineState(
        pr=PRMetadata(
            repo_full_name="acme/backend",
            pr_number=99,
            pr_title="Add user profile endpoint",
            pr_body="",
            base_branch="main",
            head_branch="feat/user-profile",
            head_sha="deadbeef",
            author="devejya",
            files_changed=files or ["src/users/profile.py"],
            diff="+ def get_profile(user_id):\n+     return db.get(user_id)\n",
            additions=additions,
            deletions=10,
        )
    )


def _make_finding(severity: str = "medium") -> ReviewFinding:
    return ReviewFinding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity(severity),
        file_path="src/users/profile.py",
        title="Missing auth check",
        description="Endpoint doesn't verify the caller has permission.",
        suggestion="Add @require_auth decorator.",
    )


class TestGraphTopology:
    """Verify the graph has the required nodes."""

    def test_all_required_nodes_present(self):
        graph = build_graph()
        compiled = graph.compile()
        node_names = set(compiled.get_graph().nodes.keys())
        required = {
            "triage",
            "start_review",
            "review_security",
            "review_performance",
            "review_style",
            "review_architecture",
            "lead_review",
            "generate_tests",
            "run_tests",
            "coverage",
            "integration_tests",
            "reproduce_bugs",
            "root_cause",
            "propose_fixes",
            "verify_fixes",
            "explain",
            "approval_gate",
            "finalise",
        }
        assert required.issubset(node_names), f"Missing nodes: {required - node_names}"


class TestConditionalRouting:
    """Verify routing functions return correct branch names."""

    def test_route_to_coverage_on_no_failures(self):
        from src.core.pipeline import route_after_tests

        state = _make_initial_state()
        state = state.model_copy(
            update={"test_results": [TestResult(module="all", passed=10, failed=0)]}
        )
        assert route_after_tests(state) == "coverage"

    def test_route_to_bug_squad_on_failures(self):
        from src.core.pipeline import route_after_tests

        state = _make_initial_state()
        state = state.model_copy(
            update={
                "test_results": [
                    TestResult(
                        module="all", passed=8, failed=2, failing_tests=["test_foo"]
                    )
                ]
            }
        )
        assert route_after_tests(state) == "reproduce_bugs"

    def test_route_integration_tests_medium_risk(self):
        from src.core.pipeline import route_integration_tests

        state = _make_initial_state()
        state = state.model_copy(
            update={"risk": RiskScore(level=RiskLevel.MEDIUM, score=0.5)}
        )
        assert route_integration_tests(state) == "integration_tests"

    def test_skip_integration_tests_low_risk(self):
        from src.core.pipeline import route_integration_tests

        state = _make_initial_state()
        state = state.model_copy(
            update={"risk": RiskScore(level=RiskLevel.LOW, score=0.1)}
        )
        assert route_integration_tests(state) == "explain"

    def test_low_risk_bypasses_review_swarm(self):
        from src.core.pipeline import route_after_triage

        state = _make_initial_state()
        state = state.model_copy(
            update={"risk": RiskScore(level=RiskLevel.LOW, score=0.1)}
        )
        assert route_after_triage(state) == "generate_tests"

    def test_medium_risk_goes_through_review_swarm(self):
        from src.core.pipeline import route_after_triage

        state = _make_initial_state()
        state = state.model_copy(
            update={"risk": RiskScore(level=RiskLevel.MEDIUM, score=0.5)}
        )
        assert route_after_triage(state) == "start_review"

    def test_high_risk_goes_through_review_swarm(self):
        from src.core.pipeline import route_after_triage

        state = _make_initial_state()
        state = state.model_copy(
            update={"risk": RiskScore(level=RiskLevel.HIGH, score=0.85)}
        )
        assert route_after_triage(state) == "start_review"

    def test_triage_without_risk_goes_to_review(self):
        from src.core.pipeline import route_after_triage

        state = _make_initial_state()
        # No risk set — defaults to going through full review
        assert route_after_triage(state) == "start_review"


class TestApprovalGate:
    def test_auto_merge_small_safe_fix(self):
        from src.agents.trust_layer.approval_gate import _is_auto_mergeable
        from src.core.state import FixClassification, ProposedFix

        state = _make_initial_state()
        state = state.model_copy(
            update={"risk": RiskScore(level=RiskLevel.MEDIUM, score=0.45)}
        )
        fix = ProposedFix(
            description="Add null check",
            patch="--- a/src/utils.py\n+++ b/src/utils.py\n@@ -5 +5 @@\n+    if x is None: return\n",
            affected_files=["src/utils.py"],
            classification=FixClassification.AUTO_MERGE,
        )
        assert _is_auto_mergeable(fix, state) is True

    def test_human_required_for_auth_fix(self):
        from src.agents.trust_layer.approval_gate import _is_auto_mergeable
        from src.core.state import FixClassification, ProposedFix

        state = _make_initial_state()
        state = state.model_copy(
            update={"risk": RiskScore(level=RiskLevel.HIGH, score=0.80)}
        )
        fix = ProposedFix(
            description="Fix JWT validation",
            patch="--- a/src/auth/jwt.py\n+++ b/src/auth/jwt.py\n@@ -10 +10 @@\n+    verify_signature(token)\n",
            affected_files=["src/auth/jwt.py"],
            classification=FixClassification.HUMAN_REQUIRED,
        )
        assert _is_auto_mergeable(fix, state) is False

    def test_human_required_for_high_risk_pr(self):
        from src.agents.trust_layer.approval_gate import _is_auto_mergeable
        from src.core.state import FixClassification, ProposedFix

        state = _make_initial_state()
        state = state.model_copy(
            update={"risk": RiskScore(level=RiskLevel.HIGH, score=0.85)}
        )
        fix = ProposedFix(
            description="Tiny fix",
            patch="--- a/src/utils.py\n+++ b/src/utils.py\n@@ -1 +1 @@\n+x = 1\n",
            affected_files=["src/utils.py"],
            classification=FixClassification.AUTO_MERGE,
        )
        # High risk PR → always human required
        assert _is_auto_mergeable(fix, state) is False


class TestWebhookSignature:
    def test_valid_signature_passes(self):
        import hashlib
        import hmac

        from src.integrations.github_client import verify_webhook_signature

        payload = b'{"action": "opened"}'
        secret = "test-webhook-secret"
        sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        with patch("src.integrations.github_client.settings") as mock_settings:
            mock_settings.GITHUB_WEBHOOK_SECRET = secret
            assert verify_webhook_signature(payload, sig) is True

    def test_invalid_signature_fails(self):
        from src.integrations.github_client import verify_webhook_signature

        with patch("src.integrations.github_client.settings") as mock_settings:
            mock_settings.GITHUB_WEBHOOK_SECRET = "real-secret"
            assert verify_webhook_signature(b"payload", "sha256=fakesig") is False

    def test_missing_prefix_fails(self):
        from src.integrations.github_client import verify_webhook_signature

        with patch("src.integrations.github_client.settings") as mock_settings:
            mock_settings.GITHUB_WEBHOOK_SECRET = "secret"
            assert verify_webhook_signature(b"payload", "badsig") is False
