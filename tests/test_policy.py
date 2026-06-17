"""
Tests for the per-repo policy loader and SentinelPolicy model.
"""

from __future__ import annotations

import pytest
import yaml

from src.core.policy import (GatePolicy, RegressionPolicy, ReviewPolicy,
                             SentinelPolicy)

# ── SentinelPolicy model ──────────────────────────────────────────────────────


class TestSentinelPolicyDefaults:
    def test_all_defaults(self):
        p = SentinelPolicy()
        assert p.version == 1
        assert p.review.min_severity == "info"
        assert p.review.skip_categories == []
        assert p.gate.max_auto_patch_lines == 30
        assert p.gate.always_human_paths == []
        assert p.regressions.enabled is True
        assert p.regressions.threshold == 0.82
        assert p.regressions.block_merge is False

    def test_unsupported_version_raises(self):
        with pytest.raises(ValueError, match="Unsupported sentinel.yaml version"):
            SentinelPolicy(version=2)


class TestSentinelPolicySeverityFilter:
    def test_info_is_below_low(self):
        p = SentinelPolicy(review=ReviewPolicy(min_severity="low"))
        assert p.is_below_min_severity("info") is True
        assert p.is_below_min_severity("low") is False
        assert p.is_below_min_severity("medium") is False

    def test_medium_threshold(self):
        p = SentinelPolicy(review=ReviewPolicy(min_severity="medium"))
        assert p.is_below_min_severity("info") is True
        assert p.is_below_min_severity("low") is True
        assert p.is_below_min_severity("medium") is False
        assert p.is_below_min_severity("high") is False
        assert p.is_below_min_severity("critical") is False

    def test_info_threshold_hides_nothing(self):
        p = SentinelPolicy(review=ReviewPolicy(min_severity="info"))
        for sev in ("info", "low", "medium", "high", "critical"):
            assert p.is_below_min_severity(sev) is False

    def test_critical_threshold_hides_most(self):
        p = SentinelPolicy(review=ReviewPolicy(min_severity="critical"))
        for sev in ("info", "low", "medium", "high"):
            assert p.is_below_min_severity(sev) is True
        assert p.is_below_min_severity("critical") is False


class TestSentinelPolicyAlwaysHuman:
    def test_matching_path(self):
        p = SentinelPolicy(
            gate=GatePolicy(always_human_paths=["deploy/", "migrations/"])
        )
        assert p.is_always_human("deploy/prod.yaml") is True
        assert p.is_always_human("migrations/0042_add_index.py") is True

    def test_non_matching_path(self):
        p = SentinelPolicy(gate=GatePolicy(always_human_paths=["deploy/"]))
        assert p.is_always_human("src/utils.py") is False

    def test_case_insensitive(self):
        p = SentinelPolicy(gate=GatePolicy(always_human_paths=["DEPLOY/"]))
        assert p.is_always_human("deploy/prod.yaml") is True

    def test_empty_always_human_paths(self):
        p = SentinelPolicy()
        assert p.is_always_human("anything/file.py") is False


class TestSentinelPolicyValidation:
    def test_threshold_clamped_to_range(self):
        with pytest.raises(Exception):
            SentinelPolicy(regressions=RegressionPolicy(threshold=1.5))
        with pytest.raises(Exception):
            SentinelPolicy(regressions=RegressionPolicy(threshold=-0.1))

    def test_max_patch_lines_positive(self):
        with pytest.raises(Exception):
            SentinelPolicy(gate=GatePolicy(max_auto_patch_lines=0))

    def test_valid_skip_categories(self):
        p = SentinelPolicy(
            review=ReviewPolicy(skip_categories=["style", "performance"])
        )
        assert "style" in p.review.skip_categories

    def test_from_dict_full(self):
        data = {
            "version": 1,
            "review": {"min_severity": "medium", "skip_categories": ["style"]},
            "gate": {"max_auto_patch_lines": 50, "always_human_paths": ["infra/"]},
            "regressions": {"enabled": True, "threshold": 0.9, "block_merge": True},
        }
        p = SentinelPolicy.model_validate(data)
        assert p.review.min_severity == "medium"
        assert "style" in p.review.skip_categories
        assert p.gate.max_auto_patch_lines == 50
        assert p.gate.always_human_paths == ["infra/"]
        assert p.regressions.threshold == 0.9
        assert p.regressions.block_merge is True

    def test_from_dict_partial_uses_defaults(self):
        data = {"version": 1, "review": {"min_severity": "high"}}
        p = SentinelPolicy.model_validate(data)
        assert p.review.min_severity == "high"
        assert p.gate.max_auto_patch_lines == 30  # default
        assert p.regressions.threshold == 0.82  # default

    def test_empty_dict_uses_all_defaults(self):
        p = SentinelPolicy.model_validate({})
        assert p.review.min_severity == "info"
        assert p.regressions.enabled is True


# ── load_policy (unit — mocks GitHub) ────────────────────────────────────────


class TestLoadPolicy:
    # GitHubClient is imported inside load_policy's function body, so we patch
    # it at the source module, not at src.core.policy.
    _PATCH_TARGET = "src.integrations.github_client.GitHubClient"

    def test_returns_defaults_when_github_unavailable(self, monkeypatch):
        """If GitHub client raises, load_policy returns defaults silently."""
        from src.core import policy as policy_mod

        class FakeClient:
            def get_repo(self, name):
                raise RuntimeError("network error")

        monkeypatch.setattr(self._PATCH_TARGET, FakeClient)

        result = policy_mod.load_policy("acme/backend", "abc123")
        assert isinstance(result, SentinelPolicy)
        assert result.review.min_severity == "info"

    def test_returns_defaults_when_file_not_found(self, monkeypatch):
        """A 404 from get_contents silently falls through to defaults."""
        import base64

        from github import GithubException

        from src.core import policy as policy_mod

        class FakeRepo:
            def get_contents(self, path, ref):
                raise GithubException(404, {"message": "Not Found"}, None)

        class FakeClient:
            def get_repo(self, name):
                return FakeRepo()

        monkeypatch.setattr(self._PATCH_TARGET, FakeClient)

        result = policy_mod.load_policy("acme/backend", "abc123")
        assert isinstance(result, SentinelPolicy)

    def test_parses_valid_yaml(self, monkeypatch):
        """A valid sentinel.yaml is parsed and returned as a SentinelPolicy."""
        import base64

        from src.core import policy as policy_mod

        raw_yaml = yaml.dump(
            {
                "version": 1,
                "review": {"min_severity": "medium"},
                "gate": {"max_auto_patch_lines": 10},
            }
        )

        class FakeContentFile:
            content = base64.b64encode(raw_yaml.encode()).decode()

        class FakeRepo:
            def get_contents(self, path, ref):
                if path == "sentinel.yaml":
                    return FakeContentFile()
                raise Exception("not found")

        class FakeClient:
            def get_repo(self, name):
                return FakeRepo()

        monkeypatch.setattr(self._PATCH_TARGET, FakeClient)

        result = policy_mod.load_policy("acme/backend", "abc123")
        assert result.review.min_severity == "medium"
        assert result.gate.max_auto_patch_lines == 10

    def test_invalid_yaml_falls_back_to_defaults(self, monkeypatch):
        """Malformed YAML returns defaults without crashing."""
        import base64

        from src.core import policy as policy_mod

        class FakeContentFile:
            content = base64.b64encode(b"version: 99\n").decode()

        class FakeRepo:
            def get_contents(self, path, ref):
                return FakeContentFile()

        class FakeClient:
            def get_repo(self, name):
                return FakeRepo()

        monkeypatch.setattr(self._PATCH_TARGET, FakeClient)

        result = policy_mod.load_policy("acme/backend", "abc123")
        assert isinstance(result, SentinelPolicy)
        assert result.review.min_severity == "info"
