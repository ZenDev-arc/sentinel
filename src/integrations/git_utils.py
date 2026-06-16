"""
Git utilities

Provides:
  - Fetching PR diffs via GitHub API
  - Archiving a specific ref as a tar.gz for the sandbox
  - Historical bug-density computation from git log
"""

from __future__ import annotations

import hashlib
import io
import re
import tarfile
from pathlib import Path
from typing import Optional

import httpx

from src.core.config import settings
from src.core.logging import get_logger

log = get_logger(__name__)


def fetch_pr_diff(
    repo_full_name: str,
    pr_number: int,
    token: Optional[str] = None,
) -> str:
    """Download the unified diff for a PR from the GitHub API."""
    tok = token or settings.GITHUB_TOKEN
    if not tok:
        raise ValueError("GITHUB_TOKEN is not set")

    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}"
    headers = {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github.v3.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_pr_files(
    repo_full_name: str,
    pr_number: int,
    token: Optional[str] = None,
) -> list[str]:
    """Return list of file paths changed in a PR."""
    tok = token or settings.GITHUB_TOKEN
    if not tok:
        raise ValueError("GITHUB_TOKEN is not set")

    url = f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/files"
    headers = {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    files: list[str] = []
    page = 1
    while True:
        resp = httpx.get(
            url,
            headers=headers,
            params={"per_page": 100, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        files.extend(f["filename"] for f in data)
        if len(data) < 100:
            break
        page += 1
    return files


def archive_pr_branch(
    repo_full_name: str,
    ref: str,
    token: Optional[str] = None,
) -> bytes:
    """
    Download a GitHub repo archive (tarball) at a specific ref.
    Returns raw tar.gz bytes for injection into the Docker sandbox.
    """
    tok = token or settings.GITHUB_TOKEN
    if not tok:
        raise ValueError("GITHUB_TOKEN is not set")

    url = f"https://api.github.com/repos/{repo_full_name}/tarball/{ref}"
    headers = {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    return resp.content


def compute_bug_density(
    repo_path: str,
    files: list[str],
    lookback_commits: int = 200,
) -> dict[str, float]:
    """
    Compute a 0–1 bug-density score for each file based on how often it appeared
    in bug-fix commits (commits whose message matches 'fix|bug|patch|issue|error').

    Returns {file_path: density_score}.
    """
    try:
        import git as gitpython

        repo = gitpython.Repo(repo_path)
    except Exception as exc:
        log.warning("git_repo_open_failed", error=str(exc))
        return {}

    fix_pattern = re.compile(r"\b(fix|bug|patch|issue|error|crash|revert|hotfix)\b", re.I)
    file_fix_counts: dict[str, int] = {f: 0 for f in files}
    total_fix_commits = 0

    for commit in list(repo.iter_commits("HEAD", max_count=lookback_commits)):
        if fix_pattern.search(commit.message):
            total_fix_commits += 1
            changed = {item.a_path for item in commit.diff(commit.parents[0]) if commit.parents} \
                if commit.parents else set()
            for f in files:
                if f in changed:
                    file_fix_counts[f] += 1

    if total_fix_commits == 0:
        return {f: 0.0 for f in files}

    return {f: count / total_fix_commits for f, count in file_fix_counts.items()}
