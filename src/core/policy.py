"""
Per-repo policy loader

Teams drop a sentinel.yaml (or .sentinel.yaml) in their repo root to
override global SENTINEL defaults without touching the server config.

Load order when a PR is processed:
  1. Fetch sentinel.yaml from the repo at the PR's head SHA via GitHub API
  2. If not found, try .sentinel.yaml
  3. If neither exists, return SentinelPolicy() with all defaults

The loader never raises — a bad or missing policy file always falls back
to defaults so a mis-typed YAML can't block an entire review run.
"""

from __future__ import annotations

import base64
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from src.core.logging import get_logger

log = get_logger(__name__)

# Severity order for min_severity filtering
_SEV_ORDER: dict[str, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

SeverityLevel = Literal["info", "low", "medium", "high", "critical"]
CategoryName = Literal["security", "performance", "style", "architecture", "test", "bug"]


class ReviewPolicy(BaseModel):
    min_severity: SeverityLevel = "info"
    skip_categories: list[CategoryName] = Field(default_factory=list)


class GatePolicy(BaseModel):
    max_auto_patch_lines: int = Field(default=30, ge=1, le=500)
    always_human_paths: list[str] = Field(default_factory=list)


class RegressionPolicy(BaseModel):
    enabled: bool = True
    threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    block_merge: bool = False


class SentinelPolicy(BaseModel):
    """Validated representation of a repo's sentinel.yaml."""
    version: int = 1
    review: ReviewPolicy = Field(default_factory=ReviewPolicy)
    gate: GatePolicy = Field(default_factory=GatePolicy)
    regressions: RegressionPolicy = Field(default_factory=RegressionPolicy)

    @model_validator(mode="after")
    def _check_version(self) -> "SentinelPolicy":
        if self.version != 1:
            raise ValueError(f"Unsupported sentinel.yaml version: {self.version}. Only version 1 is supported.")
        return self

    def severity_rank(self) -> int:
        return _SEV_ORDER.get(self.review.min_severity, 0)

    def is_below_min_severity(self, severity: str) -> bool:
        return _SEV_ORDER.get(severity, 0) < self.severity_rank()

    def is_always_human(self, file_path: str) -> bool:
        """Return True if this file path matches an always_human_paths pattern."""
        low = file_path.lower()
        return any(pat.lower() in low for pat in self.gate.always_human_paths)


def load_policy(repo_full_name: str, head_sha: str) -> SentinelPolicy:
    """
    Fetch and parse sentinel.yaml from the repo at the given ref.
    Falls back to defaults on any error (missing file, bad YAML, validation failure).
    """
    from src.integrations.github_client import GitHubClient

    client = GitHubClient()
    try:
        gh_repo = client.get_repo(repo_full_name)
    except Exception as exc:
        log.warning("policy_repo_fetch_failed", repo=repo_full_name, error=str(exc))
        return SentinelPolicy()

    for filename in ("sentinel.yaml", ".sentinel.yaml"):
        try:
            content_file = gh_repo.get_contents(filename, ref=head_sha)
            # PyGithub returns a ContentFile with base64-encoded content
            raw = base64.b64decode(content_file.content).decode("utf-8")  # type: ignore[union-attr]
            data = yaml.safe_load(raw) or {}
            policy = SentinelPolicy.model_validate(data)
            log.info("policy_loaded", repo=repo_full_name, file=filename, min_severity=policy.review.min_severity)
            return policy
        except Exception as exc:
            # 404 from GitHub → GithubException with status 404; YAML/validation errors are ValueError
            msg = str(exc)
            if "404" not in msg and "Not Found" not in msg:
                log.warning("policy_parse_failed", repo=repo_full_name, file=filename, error=msg)
            # continue to next filename or fall through to defaults

    log.info("policy_using_defaults", repo=repo_full_name)
    return SentinelPolicy()
