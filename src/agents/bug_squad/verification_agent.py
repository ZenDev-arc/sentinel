"""
Verification Agent

Last step of the Bug-Hunting Strike Team.

For each BugReport with candidate patches:
  1. Extracts the target file from the repo archive
  2. Applies the fix via text replacement (original_code → fixed_code)
  3. Injects the corrected file into the Docker sandbox
  4. Runs the failing test — if it passes, the fix is accepted
  5. Marks the report as verified

Text-replacement approach avoids unified-diff format issues entirely.
Patches are applied in isolation — the original archive is never mutated.
"""

from __future__ import annotations

import difflib
import tarfile
from io import BytesIO

from src.core.logging import get_logger
from src.core.sandbox import Sandbox
from src.core.state import BugReport, FixClassification, PipelineState, ProposedFix

log = get_logger(__name__)


def _extract_file(archive_bytes: bytes, rel_path: str) -> str | None:
    """Extract one file from a tar.gz archive by its relative path."""
    try:
        buf = BytesIO(archive_bytes)
        with tarfile.open(fileobj=buf, mode="r:gz") as tar:
            for member in tar.getmembers():
                name = member.name.lstrip("./")
                if name == rel_path or name.endswith("/" + rel_path):
                    f = tar.extractfile(member)
                    if f:
                        return f.read().decode("utf-8", errors="replace")
    except Exception as exc:
        log.warning("extract_file_failed", path=rel_path, error=str(exc))
    return None


def _apply_text_fix(original: str, fix_original: str, fix_replacement: str) -> str | None:
    """Replace fix_original with fix_replacement inside original. Returns None if not found."""
    if fix_original in original:
        return original.replace(fix_original, fix_replacement, 1)
    # Try normalising line endings
    norm_orig = fix_original.replace("\r\n", "\n").strip()
    for line in original.split("\n"):
        pass  # just normalise
    norm_file = original.replace("\r\n", "\n")
    if norm_orig in norm_file:
        return norm_file.replace(norm_orig, fix_replacement.replace("\r\n", "\n"), 1)
    return None


def _make_unified_diff(original: str, fixed: str, filename: str) -> str:
    """Build a proper unified diff using Python's difflib."""
    orig_lines = original.splitlines(keepends=True)
    fixed_lines = fixed.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines, fixed_lines,
        fromfile=f"a/{filename}", tofile=f"b/{filename}",
        lineterm="",
    )
    return "".join(diff)


def run(state: PipelineState, sandbox: Sandbox) -> dict:
    log.info("verification_agent_start", reports=len(state.bug_reports))

    if not state.repo_archive:
        log.error("verification_no_archive")
        return {
            "bug_reports": state.bug_reports,
            "proposed_fixes": state.proposed_fixes,
            "errors": state.errors + ["Verification skipped: repo_archive missing from state"],
        }

    updated_reports: list[BugReport] = []
    proposed_fixes: list[ProposedFix] = list(state.proposed_fixes)

    for report in state.bug_reports:
        if report.verified or not report.candidate_patches:
            updated_reports.append(report)
            continue

        selected_patch: dict | None = None

        for candidate in sorted(
            report.candidate_patches,
            key=lambda p: p.get("confidence", 0.0),
            reverse=True,
        ):
            file_path = candidate.get("file", "")
            orig_code = candidate.get("original_code", "")
            fixed_code = candidate.get("fixed_code", "")

            if not file_path or not orig_code.strip() or not fixed_code.strip():
                log.info("patch_skipped_missing_fields", test=report.failing_test)
                continue

            # Extract original file from archive
            original_content = _extract_file(state.repo_archive, file_path)
            if original_content is None:
                log.warning("patch_file_not_found", file=file_path)
                continue

            # Apply text replacement
            fixed_content = _apply_text_fix(original_content, orig_code, fixed_code)
            if fixed_content is None:
                log.warning("patch_text_not_found", file=file_path, snippet=orig_code[:80])
                continue

            log.info("testing_fix", test=report.failing_test, file=file_path,
                     confidence=candidate.get("confidence"))

            # Build test_name relative to workspace (strip leading path components)
            test_name = report.failing_test
            result = sandbox.run_tests(
                repo_archive=state.repo_archive,
                test_command=f"pytest {test_name} -x --tb=short -q",
                extra_files={file_path: fixed_content},
            )

            if result.exit_code == 0 and result.failed == 0 and result.passed > 0:
                selected_patch = candidate
                # Build a clean unified diff for storage
                candidate["patch"] = _make_unified_diff(original_content, fixed_content, file_path)
                log.info("fix_verified", test=report.failing_test, file=file_path)
                break
            else:
                log.info("fix_rejected", test=report.failing_test,
                         exit_code=result.exit_code, failed=result.failed,
                         passed=result.passed, stdout=result.stdout[:300])

        updated_report = report.model_copy(
            update={
                "selected_patch": selected_patch,
                "verified": selected_patch is not None,
            }
        )
        updated_reports.append(updated_report)

        if selected_patch:
            affected = selected_patch.get("affected_files", report.affected_files)
            sensitive_keywords = {"auth", "payment", "billing", "password", "secret", "token"}
            is_sensitive = any(
                kw in f.lower() for f in affected for kw in sensitive_keywords
            )
            classification = (
                FixClassification.HUMAN_REQUIRED
                if is_sensitive
                else FixClassification.AUTO_MERGE
            )
            proposed_fixes.append(
                ProposedFix(
                    description=selected_patch.get("description", f"Fix for {report.failing_test}"),
                    patch=selected_patch.get("patch", ""),
                    affected_files=affected,
                    classification=classification,
                )
            )

    log.info(
        "verification_agent_done",
        verified=sum(1 for r in updated_reports if r.verified),
        proposed_fixes=len(proposed_fixes),
    )
    return {
        "bug_reports": updated_reports,
        "proposed_fixes": proposed_fixes,
    }
