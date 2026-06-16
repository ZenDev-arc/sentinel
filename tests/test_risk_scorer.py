"""
Tests for the Risk-Scoring Agent.
Mocks the LLM call so these run without an API key.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.agents.risk_scorer import _heuristic_score, run
from src.core.state import PipelineState, PRMetadata, RiskLevel


def _make_state(
    additions: int = 10,
    deletions: int = 5,
    files: list[str] | None = None,
    diff: str = "+ print('hello')\n",
) -> PipelineState:
    return PipelineState(
        pr=PRMetadata(
            repo_full_name="acme/backend",
            pr_number=1,
            pr_title="Test PR",
            pr_body="",
            base_branch="main",
            head_branch="feat/test",
            head_sha="abc123",
            author="devejya",
            files_changed=files or ["src/utils.py"],
            diff=diff,
            additions=additions,
            deletions=deletions,
        )
    )


class TestHeuristicScore:
    def test_tiny_pr_scores_zero(self):
        state = _make_state(additions=5, deletions=2)
        score, reasons, sensitive = _heuristic_score(state)
        assert score == 0.0
        assert sensitive == []

    def test_large_diff_increases_score(self):
        state = _make_state(additions=400, deletions=200)
        score, reasons, _ = _heuristic_score(state)
        assert score > 0.0
        assert any("lines" in r for r in reasons)

    def test_sensitive_file_increases_score(self):
        state = _make_state(files=["src/auth/login.py"])
        score, reasons, sensitive = _heuristic_score(state)
        assert score >= 0.20
        assert "src/auth/login.py" in sensitive

    def test_payment_file_is_sensitive(self):
        state = _make_state(files=["billing/payment_processor.py"])
        score, _, sensitive = _heuristic_score(state)
        assert "billing/payment_processor.py" in sensitive

    def test_score_capped_at_one(self):
        # Many sensitive files should not exceed 1.0
        state = _make_state(
            additions=1000,
            deletions=500,
            files=[f"auth/module_{i}.py" for i in range(20)],
        )
        score, _, _ = _heuristic_score(state)
        assert score <= 1.0


class TestRiskScorerRun:
    def test_shortcut_tiny_pr(self):
        """Tiny non-sensitive PR should not call LLM."""
        state = _make_state(additions=5, deletions=2, files=["README.md"])
        with patch("src.agents.risk_scorer._llm_score") as mock_llm:
            result = run(state)
            mock_llm.assert_not_called()
        assert result["risk"].level == RiskLevel.LOW

    def test_llm_called_for_nontrivial_pr(self):
        state = _make_state(additions=50, deletions=20)
        mock_response = {
            "score": 0.45,
            "level": "medium",
            "reasons": ["New API endpoint"],
            "sensitive_areas": [],
        }
        with patch("src.agents.risk_scorer._llm_score", return_value=mock_response):
            result = run(state)
        assert result["risk"].level == RiskLevel.MEDIUM
        assert result["risk"].score >= 0.40

    def test_high_risk_auth_change(self):
        state = _make_state(
            additions=100,
            files=["src/auth/jwt_handler.py"],
        )
        mock_response = {
            "score": 0.85,
            "level": "high",
            "reasons": ["JWT authentication modified"],
            "sensitive_areas": ["src/auth/jwt_handler.py"],
        }
        with patch("src.agents.risk_scorer._llm_score", return_value=mock_response):
            result = run(state)
        assert result["risk"].level == RiskLevel.HIGH

    def test_llm_failure_falls_back_to_heuristic(self):
        state = _make_state(additions=200, deletions=50)
        with patch("src.agents.risk_scorer._llm_score", side_effect=Exception("LLM down")):
            result = run(state)
        # Should still return a valid risk score
        assert result["risk"] is not None
        assert "heuristic only" in " ".join(result["risk"].reasons)

    def test_blends_heuristic_and_llm_scores(self):
        """Final score must be max(heuristic, llm), never lower than heuristic."""
        state = _make_state(additions=600, deletions=100)
        mock_response = {
            "score": 0.30,
            "level": "low",
            "reasons": ["LLM thinks it's low risk"],
            "sensitive_areas": [],
        }
        with patch("src.agents.risk_scorer._llm_score", return_value=mock_response):
            result = run(state)
        # Heuristic for 700-line diff scores 0.15; LLM says 0.30 → should take max (0.30)
        assert result["risk"].score >= 0.15
