"""
SENTINEL entry point

Usage:
  # Start the webhook server (production mode)
  python main.py serve

  # Run the pipeline manually against a GitHub PR
  python main.py run --repo owner/repo --pr 42

  # Scan local code (no GitHub required)
  python main.py scan --path ./src
  python main.py scan --path . --staged          # staged changes only
  python main.py scan --path . --branch main     # diff vs a branch
  python main.py scan --path . --output report.md

  # Run KB maintenance manually
  python main.py maintain
"""

from __future__ import annotations

import argparse
import sys

# Ensure UTF-8 output on Windows (required for Rich Unicode characters)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from src.api.webhook import app
    from src.core.logging import configure_logging
    from src.scheduler.maintenance import start_scheduler

    configure_logging()
    start_scheduler(repo_root=args.repo_root)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_config=None,  # use structlog
    )


def cmd_run(args: argparse.Namespace) -> None:
    from src.core.logging import configure_logging
    from src.core.pipeline import compile_pipeline
    from src.core.state import PipelineState, PRMetadata
    from src.integrations.git_utils import fetch_pr_diff, fetch_pr_files
    from src.integrations.github_client import GitHubClient

    configure_logging(quiet=True)

    gh = GitHubClient()
    diff = fetch_pr_diff(args.repo, args.pr)
    files = fetch_pr_files(args.repo, args.pr)
    pr_meta = gh.fetch_pr_metadata(args.repo, args.pr)
    pr_meta = pr_meta.model_copy(update={"diff": diff, "files_changed": files})

    initial_state = PipelineState(
        pr=pr_meta, force_review=getattr(args, "force_review", False)
    )
    pipeline = compile_pipeline()

    from rich.console import Console

    Console().print(
        f"\n[bold cyan]SENTINEL[/bold cyan]  [cyan]{args.repo}#{args.pr}[/cyan]\n"
    )
    _run_and_display(pipeline, initial_state, report_title="SENTINEL PR REPORT")


def cmd_scan(args: argparse.Namespace) -> None:
    """Run SENTINEL on local code — no GitHub PR required."""
    import re
    import subprocess
    import tarfile
    from io import BytesIO
    from pathlib import Path

    from src.core.logging import configure_logging
    from src.core.pipeline import compile_pipeline
    from src.core.state import PipelineState, PRMetadata

    configure_logging(quiet=True)

    scan_path = Path(args.path).resolve()
    if not scan_path.exists():
        print(f"Error: path '{scan_path}' does not exist.")
        sys.exit(1)

    _SKIP = (
        ".git",
        "__pycache__",
        ".egg-info",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        "coverage",
        ".turbo",
    )
    _SOURCE_EXTS = (".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs")

    def _collect_source_files(root: "Path") -> "tuple[list[str], str, int]":
        """Collect every source file, build a synthetic diff, return (files, diff, additions)."""
        src_files: list[str] = []
        full_diff = ""
        added = 0
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix not in _SOURCE_EXTS:
                continue
            rel = str(p.relative_to(root)).replace("\\", "/")
            if any(s in rel for s in _SKIP):
                continue
            src_files.append(rel)
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                added += len(lines)
                full_diff += (
                    f"\n--- /dev/null\n+++ b/{rel}\n@@ -0,0 +1,{len(lines)} @@\n"
                )
                full_diff += "\n".join(f"+{l}" for l in lines) + "\n"
            except Exception:
                pass
        return src_files, full_diff, added

    # ── Build diff ────────────────────────────────────────────────────────────
    diff = ""
    files_changed: list[str] = []
    additions = deletions = 0

    if args.all:
        print("--all flag set — scanning every source file in the path.")
        files_changed, diff, additions = _collect_source_files(scan_path)
    elif args.staged:
        diff_cmd = ["git", "diff", "--cached"]
        result = subprocess.run(
            diff_cmd,
            capture_output=True,
            text=True,
            cwd=str(scan_path),
            encoding="utf-8",
            errors="replace",
        )
        diff = result.stdout
    elif args.branch:
        diff_cmd = ["git", "diff", args.branch]
        result = subprocess.run(
            diff_cmd,
            capture_output=True,
            text=True,
            cwd=str(scan_path),
            encoding="utf-8",
            errors="replace",
        )
        diff = result.stdout
    else:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(scan_path),
            encoding="utf-8",
            errors="replace",
        )
        diff = result.stdout
        # If working tree is clean, fall back to last commit's changes
        if not diff.strip():
            result = subprocess.run(
                ["git", "diff", "HEAD~1", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(scan_path),
                encoding="utf-8",
                errors="replace",
            )
            diff = result.stdout

    # ── Parse files + line counts from diff (when not using --all) ────────────
    if not args.all:
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                fp = line[6:]
                if fp and fp not in files_changed:
                    files_changed.append(fp)
            elif line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1

        # No git diff at all — fall back to full scan
        if not files_changed:
            print("No git diff found — falling back to full source file scan.")
            files_changed, diff, additions = _collect_source_files(scan_path)

    if not files_changed:
        print("Nothing to scan — no source files found and no git diff.")
        sys.exit(0)

    # ── Detect repo name from git remote ──────────────────────────────────────
    remote = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        cwd=str(scan_path),
    )
    repo_name = "local/scan"
    if remote.returncode == 0:
        m = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", remote.stdout.strip())
        if m:
            repo_name = m.group(1)

    # ── Package the directory for the Docker sandbox ──────────────────────────
    print(f"Packaging {scan_path.name} for sandbox…")
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in sorted(scan_path.rglob("*")):
            rel = str(p.relative_to(scan_path)).replace("\\", "/")
            if any(s in rel for s in _SKIP):
                continue
            if p.is_file():
                try:
                    tar.add(str(p), arcname=rel)
                except Exception:
                    pass
    repo_archive = buf.getvalue()

    # ── Build synthetic PR metadata ───────────────────────────────────────────
    pr_meta = PRMetadata(
        repo_full_name=repo_name,
        pr_number=0,
        pr_title=f"Local scan: {scan_path.name}",
        pr_body="",
        base_branch="main",
        head_branch="local",
        head_sha="local",
        author="local",
        files_changed=files_changed,
        diff=diff,
        additions=additions,
        deletions=deletions,
    )

    initial_state = PipelineState(
        pr=pr_meta,
        repo_archive=repo_archive,
        force_review=getattr(args, "force_review", False),
    )
    pipeline = compile_pipeline()

    from rich import box as rbox
    from rich.console import Console
    from rich.table import Table

    c = Console()
    c.print()
    c.print(f"[bold cyan]SENTINEL[/bold cyan]  local scan")
    info = Table.grid(padding=(0, 3))
    info.add_column(style="dim")
    info.add_column(style="cyan")
    info.add_row("Path", str(scan_path))
    info.add_row("Repo", repo_name)
    info.add_row("Files", str(len(files_changed)))
    info.add_row("Lines", f"+{additions}  -{deletions}")
    c.print(info)
    c.print()

    from src.cli.display import print_report, run_with_progress

    final_state = run_with_progress(pipeline, initial_state)
    print_report(final_state, title="SENTINEL LOCAL SCAN REPORT")

    if args.output:
        from pathlib import Path as _P

        _P(args.output).write_text(
            final_state.pr_comment or "No findings.", encoding="utf-8"
        )
        c.print(f"[dim]Report saved →[/dim] [cyan]{args.output}[/cyan]")


def _run_and_display(pipeline, initial_state, report_title: str) -> None:
    from src.cli.display import print_report, run_with_progress

    final_state = run_with_progress(pipeline, initial_state)
    print_report(final_state, title=report_title)


def cmd_init(args: argparse.Namespace) -> None:
    """Interactive first-time setup — writes API keys to ~/.sentinel/.env."""
    from pathlib import Path

    from rich.console import Console
    from rich.prompt import Confirm, Prompt

    c = Console()
    c.print("\n[bold orange1]SENTINEL[/bold orange1]  setup wizard\n")

    env_dir = Path.home() / ".sentinel"
    env_file = env_dir / ".env"
    env_dir.mkdir(parents=True, exist_ok=True)

    # Load existing values so re-running doesn't clear them
    existing: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    def ask(key: str, prompt: str, default: str = "", secret: bool = False) -> str:
        cur = existing.get(key, default)
        hint = (
            f"[dim](current: {cur[:8]}…)[/dim]"
            if (cur and secret)
            else f"[dim](current: {cur})[/dim]" if cur else ""
        )
        val = Prompt.ask(f"  {prompt} {hint}", password=secret, default=cur)
        return val or cur

    c.print(
        "[bold]LLM provider[/bold]  (cascade = Groq → HuggingFace fallback, recommended)"
    )
    provider = Prompt.ask(
        "  LLM_PROVIDER",
        choices=["cascade", "groq", "huggingface", "ollama", "anthropic"],
        default=existing.get("LLM_PROVIDER", "cascade"),
    )

    groq_key = hf_key = ollama_url = anthropic_key = ""
    if provider in ("cascade", "groq"):
        c.print("\n[bold]Groq[/bold]  free key at [cyan]console.groq.com[/cyan]")
        groq_key = ask("GROQ_API_KEY", "GROQ_API_KEY", secret=True)
    if provider in ("cascade", "huggingface"):
        c.print(
            "\n[bold]HuggingFace[/bold]  free token at [cyan]huggingface.co/settings/tokens[/cyan]"
        )
        hf_key = ask("HUGGINGFACE_API_KEY", "HUGGINGFACE_API_KEY", secret=True)
    if provider == "ollama":
        ollama_url = ask(
            "OLLAMA_BASE_URL", "OLLAMA_BASE_URL", default="http://localhost:11434"
        )
    if provider == "anthropic":
        anthropic_key = ask("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY", secret=True)

    c.print("\n[bold]GitHub[/bold]")
    webhook_secret = ask("GITHUB_WEBHOOK_SECRET", "GITHUB_WEBHOOK_SECRET", secret=True)
    github_token = ask(
        "GITHUB_TOKEN", "GITHUB_TOKEN (PAT with repo scope)", secret=True
    )
    github_app_id = ask(
        "GITHUB_APP_ID", "GITHUB_APP_ID (leave blank to use PAT)", default=""
    )

    lines = [
        "# SENTINEL configuration — generated by sentinel init",
        f"LLM_PROVIDER={provider}",
    ]
    if groq_key:
        lines.append(f"GROQ_API_KEY={groq_key}")
    if hf_key:
        lines.append(f"HUGGINGFACE_API_KEY={hf_key}")
    if ollama_url:
        lines.append(f"OLLAMA_BASE_URL={ollama_url}")
    if anthropic_key:
        lines.append(f"ANTHROPIC_API_KEY={anthropic_key}")
    if webhook_secret:
        lines.append(f"GITHUB_WEBHOOK_SECRET={webhook_secret}")
    if github_token:
        lines.append(f"GITHUB_TOKEN={github_token}")
    if github_app_id:
        lines.append(f"GITHUB_APP_ID={github_app_id}")

    # Preserve any other keys from the existing file
    skip = {
        "LLM_PROVIDER",
        "GROQ_API_KEY",
        "HUGGINGFACE_API_KEY",
        "OLLAMA_BASE_URL",
        "ANTHROPIC_API_KEY",
        "GITHUB_WEBHOOK_SECRET",
        "GITHUB_TOKEN",
        "GITHUB_APP_ID",
    }
    for k, v in existing.items():
        if k not in skip:
            lines.append(f"{k}={v}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    c.print(f"\n[green]✓[/green]  Saved to [cyan]{env_file}[/cyan]")
    c.print("\nNext steps:")
    c.print(
        "  1. Build the sandbox image:  [cyan]docker build -f docker/Dockerfile.sandbox -t sentinel-sandbox:latest .[/cyan]"
    )
    c.print("  2. Set up your GitHub webhook:  [cyan]sentinel github-setup[/cyan]")
    c.print("  3. Start the server:  [cyan]sentinel serve[/cyan]\n")


def cmd_github_setup(args: argparse.Namespace) -> None:
    """Print step-by-step GitHub webhook setup instructions."""
    from rich.console import Console
    from rich.panel import Panel

    c = Console()
    c.print("\n[bold orange1]SENTINEL[/bold orange1]  GitHub webhook setup\n")
    c.print(
        Panel(
            "[bold]1.[/bold] Go to your GitHub repo → [cyan]Settings → Webhooks → Add webhook[/cyan]\n\n"
            "[bold]2.[/bold] Fill in:\n"
            "   Payload URL:   [cyan]http://<your-machine-ip>:8000/webhook/github[/cyan]\n"
            "                  [dim](use ngrok for internet access — see below)[/dim]\n"
            "   Content type:  [cyan]application/json[/cyan]\n"
            "   Secret:        [cyan]the GITHUB_WEBHOOK_SECRET from your .env[/cyan]\n"
            "   Events:        [cyan]Pull requests[/cyan]\n\n"
            "[bold]3.[/bold] For local dev with a public URL, start an ngrok tunnel:\n"
            "   [cyan]ngrok http 8000[/cyan]\n"
            "   Then use the [cyan]https://xxxx.ngrok-free.app[/cyan] URL as your Payload URL.\n\n"
            "[bold]4.[/bold] Start SENTINEL:\n"
            "   [cyan]sentinel serve[/cyan]\n\n"
            "[bold]5.[/bold] Open a PR on your repo — SENTINEL will post a review comment automatically.",
            title="Setup steps",
            border_style="orange1",
        )
    )
    c.print()


def cmd_maintain(args: argparse.Namespace) -> None:
    from src.agents.self_healing import (
        consistency,
        consolidation,
        curator,
        drift_checker,
    )
    from src.core.logging import configure_logging
    from src.knowledge_base.store import KnowledgeBaseStore

    configure_logging()
    kb = KnowledgeBaseStore()
    print("Running KB maintenance…")
    print("Curator:      ", curator.run(kb))
    print("Drift-Checker:", drift_checker.run(kb, args.repo_root))
    print("Consistency:  ", consistency.run(kb))
    print("Consolidation:", consolidation.run(kb))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SENTINEL — self-healing code quality pipeline"
    )
    sub = parser.add_subparsers(dest="command")

    # serve
    p_serve = sub.add_parser("serve", help="Start the webhook server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument(
        "--repo-root", default=".", help="Local path to the monitored repo"
    )
    p_serve.set_defaults(func=cmd_serve)

    # run
    p_run = sub.add_parser("run", help="Run pipeline manually on a GitHub PR")
    p_run.add_argument("--repo", required=True, help="owner/repo")
    p_run.add_argument("--pr", type=int, required=True, help="PR number")
    p_run.add_argument(
        "--force-review",
        action="store_true",
        dest="force_review",
        help="Always run full review swarm regardless of risk level",
    )
    p_run.set_defaults(func=cmd_run)

    # scan
    p_scan = sub.add_parser("scan", help="Scan local code — no GitHub PR required")
    p_scan.add_argument(
        "--path", default=".", help="Directory to scan (default: current dir)"
    )
    p_scan.add_argument(
        "--all",
        action="store_true",
        help="Scan every source file in the path (.py/.js/.ts/.jsx/.tsx) — ignores git diff",
    )
    p_scan.add_argument(
        "--staged", action="store_true", help="Scan only staged git changes"
    )
    p_scan.add_argument(
        "--branch", default=None, help="Diff against this branch (e.g. main)"
    )
    p_scan.add_argument(
        "--force-review",
        action="store_true",
        dest="force_review",
        help="Always run full review swarm regardless of risk level",
    )
    p_scan.add_argument(
        "--output", default=None, help="Save report to this file (e.g. report.md)"
    )
    p_scan.set_defaults(func=cmd_scan)

    # init
    sub.add_parser(
        "init", help="First-time setup wizard — saves API keys to ~/.sentinel/.env"
    ).set_defaults(func=cmd_init)

    # github-setup
    sub.add_parser(
        "github-setup", help="Step-by-step GitHub webhook setup guide"
    ).set_defaults(func=cmd_github_setup)

    # maintain
    p_maintain = sub.add_parser("maintain", help="Run KB maintenance agents manually")
    p_maintain.add_argument(
        "--repo-root", default=".", help="Local path to the monitored repo"
    )
    p_maintain.set_defaults(func=cmd_maintain)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
