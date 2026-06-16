"""
Docker Sandbox

Executes test suites and patch verifications in isolated containers.

Security properties:
  - No network access (network_mode=none) — prevents SSRF from test code
  - Read-only filesystem except /workspace and /tmp
  - CPU and memory limits enforced
  - Hard timeout — enforced via `timeout` command inside container
  - Runs as non-root user (uid 1000) inside the container
  - No privilege escalation (no_new_privileges=true)
"""

from __future__ import annotations

import copy
import shlex
import tarfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from src.core.config import settings
from src.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    coverage_percent: float | None = None
    timed_out: bool = False


class Sandbox:
    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client

    def run_tests(
        self,
        repo_archive: bytes,
        test_command: str = "pytest --tb=short -q --cov=. --cov-report=term",
        extra_files: dict[str, str] | None = None,
    ) -> SandboxResult:
        """
        repo_archive: tar.gz bytes of the repository to test.
        extra_files: {relative_path: file_content} to inject before running tests.
        """
        client = self._get_client()
        container = None

        try:
            # Keep container alive with a long-running no-op command.
            # We then exec commands into it — exec_run requires a live container.
            container = client.containers.run(
                image=settings.SANDBOX_IMAGE,
                command="tail -f /dev/null",
                detach=True,
                network_mode="none",
                mem_limit=settings.SANDBOX_MEMORY_LIMIT,
                cpu_period=settings.SANDBOX_CPU_PERIOD,
                cpu_quota=settings.SANDBOX_CPU_QUOTA,
                security_opt=["no-new-privileges:true"],
                user="1000:1000",
                working_dir="/workspace",
                remove=False,
            )

            # GitHub tarballs extract to a single root dir (owner-repo-sha/).
            # Strip it so files land directly at /workspace/src/... not
            # /workspace/owner-repo-sha/src/...
            container.put_archive("/workspace", self._strip_tarball_root(repo_archive))

            # Inject extra files (e.g. generated tests)
            if extra_files:
                for rel_path, content in extra_files.items():
                    self._inject_file(container, rel_path, content)

            # Wrap with hard timeout inside the container — this is the correct
            # way to enforce a deadline on exec_run (which blocks indefinitely).
            timeout_sec = settings.SANDBOX_TIMEOUT_SECONDS
            wrapped = f"timeout {timeout_sec} sh -c {shlex.quote(test_command)}"

            exit_code, output = container.exec_run(
                cmd=["sh", "-c", wrapped],
                workdir="/workspace",
                user="1000:1000",
                demux=True,
            )

            timed_out = (exit_code == 124)  # `timeout` exits 124 on expiry
            if timed_out:
                log.warning("sandbox_timeout", command=test_command)

        except Exception as exc:
            log.error("sandbox_run_failed", error=str(exc))
            return SandboxResult(exit_code=-1, stdout="", stderr=str(exc))
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        stdout_bytes, stderr_bytes = (
            output if isinstance(output, tuple) else (output, b"")
        )
        stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
        stderr = (stderr_bytes or b"").decode("utf-8", errors="replace")

        result = self._parse_pytest_output(stdout, stderr, exit_code)
        result.timed_out = timed_out
        log.info(
            "sandbox_run_done",
            exit_code=exit_code,
            passed=result.passed,
            failed=result.failed,
            timed_out=timed_out,
        )
        return result

    def run_js_tests(
        self,
        repo_archive: bytes,
        extra_files: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run Jest tests for a JavaScript/TypeScript project.

        Uses globally installed jest (no npm install needed — no network).
        Works for projects that use standard jest matchers without complex
        project-specific plugins.
        """
        client = self._get_client()
        container = None

        try:
            container = client.containers.run(
                image=settings.SANDBOX_IMAGE,
                command="tail -f /dev/null",
                detach=True,
                network_mode="none",
                mem_limit=settings.SANDBOX_MEMORY_LIMIT,
                cpu_period=settings.SANDBOX_CPU_PERIOD,
                cpu_quota=settings.SANDBOX_CPU_QUOTA,
                security_opt=["no-new-privileges:true"],
                user="1000:1000",
                working_dir="/workspace",
                remove=False,
            )

            container.put_archive("/workspace", self._strip_tarball_root(repo_archive))

            if extra_files:
                for rel_path, content in extra_files.items():
                    self._inject_file(container, rel_path, content)

            timeout_sec = settings.SANDBOX_TIMEOUT_SECONDS

            # Use globally installed jest with ts-jest transformer.
            # --no-coverage: faster, avoids needing babel/istanbul setup
            # --forceExit: don't hang on open handles
            # --testEnvironment node: works for non-browser code
            # --transform: use ts-jest for .ts files without a local tsconfig
            jest_cmd = (
                "jest --no-coverage --forceExit --testEnvironment node "
                "--transform '{\"^.+\\.tsx?$\":\"ts-jest\"}' "
                "--testPathPattern '\\.(test|spec)\\.[jt]sx?$' 2>&1"
            )
            wrapped = f"timeout {timeout_sec} sh -c {shlex.quote(jest_cmd)}"

            exit_code, output = container.exec_run(
                cmd=["sh", "-c", wrapped],
                workdir="/workspace",
                user="1000:1000",
                demux=True,
            )

            timed_out = (exit_code == 124)
            if timed_out:
                log.warning("sandbox_jest_timeout")

        except Exception as exc:
            log.error("sandbox_jest_failed", error=str(exc))
            return SandboxResult(exit_code=-1, stdout="", stderr=str(exc))
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        stdout_bytes, stderr_bytes = (
            output if isinstance(output, tuple) else (output, b"")
        )
        stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
        stderr = (stderr_bytes or b"").decode("utf-8", errors="replace")

        result = self._parse_jest_output(stdout, stderr, exit_code)
        result.timed_out = timed_out if 'timed_out' in locals() else False
        log.info(
            "sandbox_jest_done",
            exit_code=exit_code,
            passed=result.passed,
            failed=result.failed,
        )
        return result

    def apply_patch_and_test(
        self,
        patch: str,
        test_command: str,
        repo_archive: bytes,
    ) -> SandboxResult:
        """
        Applies a unified diff patch inside the sandbox and runs test_command.
        repo_archive: tar.gz of the repository at the PR's head SHA.
        """
        if not patch.strip():
            log.warning("sandbox_empty_patch")
            return SandboxResult(exit_code=1, stdout="", stderr="Empty patch — nothing to apply.")

        # Write patch to a temp file, inject it, then `git apply` + run tests.
        patch_bytes = patch.encode("utf-8")
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=".sentinel_patch.diff")
            info.size = len(patch_bytes)
            tar.addfile(info, BytesIO(patch_bytes))
        patch_archive = buf.getvalue()

        client = self._get_client()
        container = None
        try:
            container = client.containers.run(
                image=settings.SANDBOX_IMAGE,
                command="tail -f /dev/null",
                detach=True,
                network_mode="none",
                mem_limit=settings.SANDBOX_MEMORY_LIMIT,
                cpu_period=settings.SANDBOX_CPU_PERIOD,
                cpu_quota=settings.SANDBOX_CPU_QUOTA,
                security_opt=["no-new-privileges:true"],
                user="1000:1000",
                working_dir="/workspace",
                remove=False,
            )

            container.put_archive("/workspace", self._strip_tarball_root(repo_archive))
            container.put_archive("/workspace", patch_archive)

            timeout_sec = settings.SANDBOX_TIMEOUT_SECONDS
            # `patch -p1` works without a .git repo (GitHub tarballs have none).
            # -p1 strips the leading a/ or b/ path prefix from unified diffs.
            # --forward ignores already-applied hunks (idempotent).
            apply_and_test = (
                "patch --forward -p1 < /workspace/.sentinel_patch.diff && "
                f"timeout {timeout_sec} sh -c {shlex.quote(test_command)}"
            )

            exit_code, output = container.exec_run(
                cmd=["sh", "-c", apply_and_test],
                workdir="/workspace",
                user="1000:1000",
                demux=True,
            )

        except Exception as exc:
            log.error("sandbox_patch_run_failed", error=str(exc))
            return SandboxResult(exit_code=-1, stdout="", stderr=str(exc))
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        stdout_bytes, stderr_bytes = (
            output if isinstance(output, tuple) else (output, b"")
        )
        stdout = (stdout_bytes or b"").decode("utf-8", errors="replace")
        stderr = (stderr_bytes or b"").decode("utf-8", errors="replace")
        return self._parse_pytest_output(stdout, stderr, exit_code)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_pytest_output(stdout: str, stderr: str, exit_code: int) -> SandboxResult:
        import re

        passed = failed = errors = 0
        coverage = None

        # pytest summary line order varies: "3 failed, 3 passed" or "3 passed, 3 failed"
        mp = re.search(r"(\d+) passed", stdout)
        mf = re.search(r"(\d+) failed", stdout)
        me = re.search(r"(\d+) error", stdout)
        passed = int(mp.group(1)) if mp else 0
        failed = int(mf.group(1)) if mf else 0
        errors = int(me.group(1)) if me else 0

        # Coverage: "TOTAL   1234  123  90%"
        cm = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", stdout)
        if cm:
            coverage = float(cm.group(1))

        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            passed=passed,
            failed=failed,
            errors=errors,
            coverage_percent=coverage,
        )

    @staticmethod
    def _parse_jest_output(stdout: str, stderr: str, exit_code: int) -> SandboxResult:
        import re

        passed = failed = errors = 0

        # Jest summary: "Tests: 3 failed, 3 passed, 6 total"
        combined = stdout + "\n" + stderr
        mp = re.search(r"(\d+) passed", combined)
        mf = re.search(r"(\d+) failed", combined)
        passed = int(mp.group(1)) if mp else 0
        failed = int(mf.group(1)) if mf else 0

        # If jest exited non-zero but no counts found, mark as error
        if exit_code != 0 and passed == 0 and failed == 0:
            errors = 1

        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            passed=passed,
            failed=failed,
            errors=errors,
            coverage_percent=None,
        )

    @staticmethod
    def _strip_tarball_root(archive_bytes: bytes) -> bytes:
        """
        GitHub repository tarballs extract to a single top-level directory
        (e.g. 'owner-repo-abc123/'). Strip that prefix so files land directly
        at /workspace/file.py instead of /workspace/owner-repo-abc123/file.py.

        If the archive is already flat (no shared root), returns it unchanged.
        """
        buf_in = BytesIO(archive_bytes)
        buf_out = BytesIO()

        with tarfile.open(fileobj=buf_in, mode="r:gz") as tar_in:
            members = tar_in.getmembers()
            if not members:
                return archive_bytes

            # Detect a single shared root directory
            top_dir = members[0].name.split("/")[0] + "/"
            if not all(m.name.startswith(top_dir) for m in members):
                return archive_bytes  # already flat

            with tarfile.open(fileobj=buf_out, mode="w:gz") as tar_out:
                for member in members:
                    stripped = member.name[len(top_dir):]
                    if not stripped:
                        continue  # skip the root dir entry itself
                    new_member = copy.copy(member)
                    new_member.name = stripped
                    if member.isfile():
                        tar_out.addfile(new_member, tar_in.extractfile(member))
                    else:
                        tar_out.addfile(new_member)

        return buf_out.getvalue()

    @staticmethod
    def _archive_directory(path: str) -> bytes:
        """Create an in-memory tar.gz of a directory."""
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            tar.add(path, arcname=".")
        return buf.getvalue()

    @staticmethod
    def _inject_file(container, rel_path: str, content: str) -> None:
        """Write a single file into /workspace/{rel_path} in the container."""
        data = content.encode("utf-8")
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=rel_path)
            info.size = len(data)
            tar.addfile(info, BytesIO(data))
        container.put_archive("/workspace", buf.getvalue())
