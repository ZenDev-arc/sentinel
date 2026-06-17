"""
GitHub Client

Wraps the GitHub API for:
  - Posting PR review comments
  - Committing auto-applied fixes (via the Git Data API)
  - Fetching PR metadata
  - Webhook signature verification (HMAC-SHA256)

Security: webhook payloads are verified against the HMAC-SHA256 signature
from the X-Hub-Signature-256 header before any processing occurs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Optional

import httpx
from github import Auth, Github, GithubIntegration
from github.Repository import Repository

from src.core.config import settings
from src.core.logging import get_logger
from src.core.state import PRMetadata, ProposedFix

log = get_logger(__name__)

_GH_API = "https://api.github.com"
_GH_VERSION = "2022-11-28"


def verify_webhook_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """
    Verify GitHub webhook HMAC-SHA256 signature.
    Must be called before processing any webhook payload.
    Returns True only if the signature is valid.
    """
    if not settings.GITHUB_WEBHOOK_SECRET:
        log.warning("webhook_secret_not_configured")
        return False

    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    received = signature_header[len("sha256=") :]
    return hmac.compare_digest(expected, received)


class GitHubClient:
    def __init__(
        self,
        token: Optional[str] = None,
        installation_id: Optional[int] = None,
    ) -> None:
        self._token = token or settings.GITHUB_TOKEN
        self._installation_id = installation_id
        self._gh: Optional[Github] = None

    def _get_gh(self) -> Github:
        if self._gh is not None:
            return self._gh

        # GitHub App authentication (preferred for production)
        if (
            settings.GITHUB_APP_ID
            and settings.github_app_private_key
            and self._installation_id
        ):
            app_auth = Auth.AppInstallationAuth(
                Auth.AppAuth(
                    app_id=int(settings.GITHUB_APP_ID),
                    private_key=settings.github_app_private_key,
                ),
                self._installation_id,
            )
            self._gh = Github(auth=app_auth)
            return self._gh

        # PAT fallback (simpler, for single-repo setups)
        if self._token:
            self._gh = Github(auth=Auth.Token(self._token))
            return self._gh

        raise ValueError(
            "No GitHub authentication configured. "
            "Set GITHUB_TOKEN or GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY_PATH."
        )

    def _get_installation_token(self) -> Optional[str]:
        """
        Return a raw bearer token usable in httpx calls.

        For PAT auth this is just the token string.
        For GitHub App auth this exchanges App credentials for a short-lived
        installation access token via the GitHub API.
        """
        if self._token:
            return self._token

        if (
            settings.GITHUB_APP_ID
            and settings.github_app_private_key
            and self._installation_id
        ):
            integration = GithubIntegration(
                auth=Auth.AppAuth(
                    app_id=int(settings.GITHUB_APP_ID),
                    private_key=settings.github_app_private_key,
                )
            )
            token_obj = integration.get_access_token(self._installation_id)
            return token_obj.token

        # Last resort — global PAT
        return settings.GITHUB_TOKEN

    def get_repo(self, repo_full_name: str) -> Repository:
        return self._get_gh().get_repo(repo_full_name)

    def fetch_pr_metadata(self, repo_full_name: str, pr_number: int) -> PRMetadata:
        repo = self.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        files = [f.filename for f in pr.get_files()]

        return PRMetadata(
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            pr_title=pr.title,
            pr_body=pr.body or "",
            base_branch=pr.base.ref,
            head_branch=pr.head.ref,
            head_sha=pr.head.sha,
            author=pr.user.login,
            files_changed=files,
            additions=pr.additions,
            deletions=pr.deletions,
            installation_id=self._installation_id,
        )

    def post_pr_comment(self, repo_full_name: str, pr_number: int, body: str) -> str:
        """Post a general comment on a PR. Returns the comment URL."""
        repo = self.get_repo(repo_full_name)
        pr = repo.get_pull(pr_number)
        comment = pr.create_issue_comment(body)
        log.info("pr_comment_posted", pr=pr_number, url=comment.html_url)
        return comment.html_url

    def commit_fix(
        self,
        repo_full_name: str,
        fix: ProposedFix,
        branch: str,
        commit_message: str,
    ) -> Optional[str]:
        """
        Apply a unified diff patch and commit it to the given branch.
        Uses the Git Data API to avoid needing a local checkout.
        Returns the new commit SHA or None on failure.
        """
        if not fix.patch.strip():
            return None

        tok = self._get_installation_token()
        if not tok:
            log.warning("commit_fix_no_token")
            return None

        headers = {
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": _GH_VERSION,
        }

        # Fetch current tree SHA
        ref_url = f"{_GH_API}/repos/{repo_full_name}/git/ref/heads/{branch}"
        resp = httpx.get(ref_url, headers=headers, timeout=30)
        if resp.status_code != 200:
            log.warning("commit_fix_ref_fetch_failed", status=resp.status_code)
            return None

        current_sha = resp.json()["object"]["sha"]

        # Parse the patch to extract file changes.
        # We pass headers + repo so the parser can fetch current file content
        # from GitHub before applying hunk offsets — necessary to reconstruct
        # complete file content rather than just the diff lines.
        file_changes = _parse_unified_diff_for_git_api(
            fix.patch, headers, repo_full_name
        )
        if not file_changes:
            log.warning("commit_fix_no_parseable_changes")
            return None

        # Create blobs for changed files
        new_tree: list[dict] = []
        for file_path, new_content in file_changes.items():
            blob_resp = httpx.post(
                f"{_GH_API}/repos/{repo_full_name}/git/blobs",
                headers=headers,
                json={"content": new_content, "encoding": "utf-8"},
                timeout=30,
            )
            if blob_resp.status_code != 201:
                log.warning("blob_creation_failed", file=file_path)
                continue
            new_tree.append(
                {
                    "path": file_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": blob_resp.json()["sha"],
                }
            )

        if not new_tree:
            return None

        # Create tree
        tree_resp = httpx.post(
            f"{_GH_API}/repos/{repo_full_name}/git/trees",
            headers=headers,
            json={"base_tree": current_sha, "tree": new_tree},
            timeout=30,
        )
        if tree_resp.status_code != 201:
            return None
        tree_sha = tree_resp.json()["sha"]

        # Create commit
        commit_resp = httpx.post(
            f"{_GH_API}/repos/{repo_full_name}/git/commits",
            headers=headers,
            json={
                "message": commit_message,
                "tree": tree_sha,
                "parents": [current_sha],
            },
            timeout=30,
        )
        if commit_resp.status_code != 201:
            return None
        new_commit_sha = commit_resp.json()["sha"]

        # Update branch ref
        httpx.patch(
            ref_url,
            headers=headers,
            json={"sha": new_commit_sha},
            timeout=30,
        )

        log.info("fix_committed", sha=new_commit_sha[:8], branch=branch)
        return new_commit_sha

    def get_check_runs(self, repo_full_name: str, commit_sha: str) -> list[dict]:
        """
        Return GitHub Actions check runs for a specific commit.
        Each item has keys: name, status, conclusion.
        """
        tok = self._get_installation_token()
        if not tok:
            return []
        headers = {
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": _GH_VERSION,
        }
        resp = httpx.get(
            f"{_GH_API}/repos/{repo_full_name}/commits/{commit_sha}/check-runs",
            headers=headers,
            timeout=30,
        )
        if resp.status_code != 200:
            log.warning("check_runs_fetch_failed", status=resp.status_code)
            return []
        return resp.json().get("check_runs", [])

    def create_pr_suggestion(
        self,
        repo_full_name: str,
        pr_number: int,
        fix: ProposedFix,
        commit_id: str,
    ) -> None:
        """Post a fix as a review suggestion comment on the specific file/line."""
        if not fix.affected_files:
            return
        body = (
            f"**SENTINEL suggested fix:** {fix.description}\n\n"
            f"> {fix.rationale}\n\n"
            "```suggestion\n"
            f"{fix.patch[:1000]}\n"
            "```\n"
            f"*Classification: {fix.classification.value}*"
        )
        self.post_pr_comment(repo_full_name, pr_number, body)


def build_from_webhook(
    payload: dict, installation_id: Optional[int] = None
) -> "GitHubClient":
    """Factory for creating a client scoped to a webhook event's installation."""
    inst_id = installation_id or payload.get("installation", {}).get("id")
    return GitHubClient(installation_id=inst_id)


def _parse_unified_diff_for_git_api(
    patch: str,
    headers: dict,
    repo_full_name: str,
) -> dict[str, str]:
    """
    Parse a unified diff and return {file_path: complete_new_file_content}.

    For each file in the patch:
      1. Fetches the current content from the GitHub Contents API.
      2. Applies the hunk offsets to reconstruct the full new content.

    This is necessary because the Git Data API requires complete file blobs,
    not just the diff lines — the previous approach that only accumulated `+`
    and context lines would truncate files to just the patched region.
    """
    import base64
    import re

    result: dict[str, str] = {}

    # Split into per-file sections on "diff --git" boundaries
    file_sections = re.split(r"(?=^diff --git )", patch, flags=re.MULTILINE)

    for section in file_sections:
        if not section.strip():
            continue

        # Extract file path from "+++ b/<path>" line
        path_match = re.search(r"^\+\+\+ b/(.+)$", section, re.MULTILINE)
        if not path_match:
            continue
        file_path = path_match.group(1).strip()

        # Fetch the current file content from GitHub
        content_resp = httpx.get(
            f"{_GH_API}/repos/{repo_full_name}/contents/{file_path}",
            headers=headers,
            timeout=30,
        )

        if content_resp.status_code == 200:
            raw = content_resp.json().get("content", "").replace("\n", "")
            original = base64.b64decode(raw).decode("utf-8", errors="replace")
            original_lines = original.splitlines()
            trailing_newline = original.endswith("\n")
        elif content_resp.status_code == 404:
            # New file introduced by this patch
            original_lines = []
            trailing_newline = True
        else:
            log.warning(
                "patch_fetch_file_failed",
                file=file_path,
                status=content_resp.status_code,
            )
            continue

        new_lines = _apply_diff_hunks(original_lines, section)
        new_content = "\n".join(new_lines)
        if trailing_newline and not new_content.endswith("\n"):
            new_content += "\n"
        result[file_path] = new_content

    return result


def _apply_diff_hunks(original_lines: list[str], diff_section: str) -> list[str]:
    """
    Apply unified diff hunks from one file's section to original_lines.
    Returns the list of lines for the complete new file.
    """
    import re

    result: list[str] = []
    orig_pos = 0  # current position in original_lines (0-indexed)

    for line in diff_section.splitlines():
        if line.startswith("@@"):
            # Hunk header: @@ -orig_start[,count] +new_start[,count] @@
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@", line)
            if m:
                hunk_start = int(m.group(1)) - 1  # convert to 0-indexed
                # Emit original lines that precede this hunk
                result.extend(original_lines[orig_pos:hunk_start])
                orig_pos = hunk_start
        elif (
            line.startswith("---") or line.startswith("+++") or line.startswith("diff ")
        ):
            continue
        elif line.startswith("+"):
            result.append(line[1:])
        elif line.startswith("-"):
            orig_pos += 1  # consume from original without emitting
        elif line.startswith(" "):
            if orig_pos < len(original_lines):
                result.append(original_lines[orig_pos])
            orig_pos += 1

    # Emit any remaining original lines after the last hunk
    result.extend(original_lines[orig_pos:])
    return result
