"""
Rich CLI display for SENTINEL scan and run commands.

Provides:
  - Live agent-by-agent progress while the pipeline streams
  - Structured final report with color-coded severity tables
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn
from rich.progress import Progress as RichProgress
from rich.progress import SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from src.core.state import PipelineState

import io as _io
import sys as _sys

# On Windows the default console codec often can't handle Unicode box/spinner
# chars. Force UTF-8 so Rich renders correctly.
if _sys.platform == "win32":
    try:
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

console = Console()

# ── Node label mapping ────────────────────────────────────────────────────────

_NODE_LABEL: dict[str, str] = {
    "triage": "Risk assessment",
    "start_review": "Starting review swarm",
    "review_security": "Security review",
    "review_performance": "Performance review",
    "review_style": "Style & quality review",
    "review_architecture": "Architecture review",
    "lead_review": "Lead review synthesis",
    "generate_tests": "Test generation",
    "run_tests": "Running sandbox tests",
    "coverage": "Coverage analysis",
    "integration_tests": "Integration tests",
    "reproduce_bugs": "Bug reproduction",
    "root_cause": "Root cause analysis",
    "propose_fixes": "Proposing fixes",
    "verify_fixes": "Verifying fixes",
    "explain": "Generating explanations",
    "approval_gate": "Approval gate",
    "finalise": "Finalising report",
}

_SEVERITY_COLOR: dict[str, str] = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "cyan",
    "info": "dim white",
}

_RISK_COLOR: dict[str, str] = {
    "high": "bold red",
    "medium": "bold yellow",
    "low": "bold green",
}


# ── Live pipeline runner ───────────────────────────────────────────────────────


def run_with_progress(pipeline, initial_state) -> "PipelineState":
    """
    Stream the pipeline and show a live progress panel.
    Returns the final PipelineState.
    """
    from src.core.state import PipelineState

    completed: list[tuple[str, str]] = []  # (label, extra_info)
    current: list[str] = []  # current node label
    final_state_raw = None

    progress = RichProgress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        transient=False,
    )
    task_id = progress.add_task("Starting…", total=None)

    def _make_panel() -> Panel:
        lines: list[Text] = []
        for label, info in completed:
            t = Text()
            t.append("  ✓ ", style="bold green")
            t.append(label, style="green")
            if info:
                t.append(f"  {info}", style="dim")
            lines.append(t)
        if current:
            t = Text()
            t.append("  ⠸ ", style="bold yellow")
            t.append(current[0], style="bold yellow")
            lines.append(t)
        body = "\n".join(str(l) for l in lines) if lines else "  Initialising…"
        return Panel(
            body,
            title="[bold cyan]SENTINEL[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )

    with Live(_make_panel(), refresh_per_second=8, console=console) as live:
        for event in pipeline.stream(initial_state):
            for node_name, state_update in event.items():
                if node_name == "__end__":
                    final_state_raw = state_update
                    continue

                label = _NODE_LABEL.get(node_name, node_name)
                extra = ""

                # Pull useful summary info out of the node's output dict
                if isinstance(state_update, dict):
                    risk = state_update.get("risk")
                    if risk and hasattr(risk, "level"):
                        col = _RISK_COLOR.get(risk.level.value, "white")
                        extra = f"[{col}]{risk.level.value.upper()}[/{col}]  score {risk.score:.2f}"
                    findings = (
                        state_update.get("security_findings", [])
                        + state_update.get("performance_findings", [])
                        + state_update.get("style_findings", [])
                        + state_update.get("architecture_findings", [])
                        + state_update.get("consolidated_findings", [])
                    )
                    if findings:
                        extra = f"{len(findings)} finding(s)"
                    tests = state_update.get("generated_tests", [])
                    if tests:
                        extra = f"{len(tests)} test file(s) generated"
                    results = state_update.get("test_results", [])
                    if results:
                        r = results[0] if results else None
                        if r:
                            extra = f"passed {r.passed}  failed {r.failed}"

                if current:
                    completed.append((current[0], ""))
                    current.clear()
                current.append(label)
                progress.update(task_id, description=f"[yellow]{label}[/yellow]")
                live.update(_make_panel())

        # Mark last node done
        if current:
            completed.append((current[0], ""))
        live.update(_make_panel())

    # Reconstruct typed state from the final accumulated dict
    # LangGraph streams partial dicts per node; accumulate manually if __end__ missing
    if final_state_raw is None:
        # Fallback: invoke to get final state (stream already ran for display)
        final_state_raw = pipeline.invoke(initial_state)

    if isinstance(final_state_raw, dict):
        return PipelineState.model_validate(final_state_raw)
    return final_state_raw


# ── Structured report ─────────────────────────────────────────────────────────


def print_report(state: "PipelineState", title: str = "SENTINEL REPORT") -> None:
    """Render the full pipeline result as a rich structured report."""

    console.print()
    console.rule(f"[bold cyan]{title}[/bold cyan]", style="cyan")
    console.print()

    # ── Summary bar ───────────────────────────────────────────────────────────
    risk = state.risk
    risk_text = Text("UNKNOWN", style="dim")
    if risk:
        col = _RISK_COLOR.get(risk.level.value, "white")
        risk_text = Text(f"{risk.level.value.upper()}  ({risk.score:.2f})", style=col)

    summary = Table.grid(padding=(0, 3))
    summary.add_column(style="dim")
    summary.add_column()
    summary.add_row("Risk level", risk_text)
    summary.add_row(
        "Files reviewed", str(len(state.pr.files_changed) if state.pr else 0)
    )
    summary.add_row("Findings", str(len(state.consolidated_findings)))
    summary.add_row("Tests generated", str(len(state.generated_tests)))
    summary.add_row("Bugs found", str(len(state.bug_reports)))
    summary.add_row("Auto-fixes", str(len(state.auto_applied_fixes)))
    summary.add_row("Pending fixes", str(len(state.pending_human_fixes)))
    console.print(Panel(summary, title="Summary", border_style="cyan", padding=(0, 2)))

    # ── Findings table ────────────────────────────────────────────────────────
    findings = state.consolidated_findings or state.all_findings()
    if findings:
        console.print()
        console.print(Rule("[bold]Findings[/bold]"))
        t = Table(box=box.SIMPLE_HEAD, show_edge=False, padding=(0, 1))
        t.add_column("Severity", style="bold", width=10)
        t.add_column("Category", width=14)
        t.add_column("File", style="cyan", max_width=40)
        t.add_column("Issue")
        for f in findings:
            sev = f.severity.value
            col = _SEVERITY_COLOR.get(sev, "white")
            loc = f.file_path
            if f.line_start:
                loc += f":{f.line_start}"
            t.add_row(
                Text(sev.upper(), style=col),
                f.category.value,
                loc,
                f.title,
            )
        console.print(t)
    else:
        console.print()
        console.print("  [dim]No findings.[/dim]")

    # ── Generated tests ───────────────────────────────────────────────────────
    if state.generated_tests:
        console.print()
        console.print(Rule("[bold]Generated Tests[/bold]"))
        for gt in state.generated_tests:
            console.print(
                f"  [green]•[/green] [cyan]{gt.file_path}[/cyan]  [dim]{gt.description}[/dim]"
            )

    # ── Sandbox test results ──────────────────────────────────────────────────
    if state.test_results:
        console.print()
        console.print(Rule("[bold]Sandbox Results[/bold]"))
        for r in state.test_results:
            status_col = "green" if r.failed == 0 and r.errors == 0 else "red"
            console.print(
                f"  passed [bold green]{r.passed}[/bold green]  "
                f"failed [{status_col}]{r.failed}[/{status_col}]  "
                f"errors [{status_col}]{r.errors}[/{status_col}]"
                + (
                    f"  coverage [bold]{r.coverage_percent:.0f}%[/bold]"
                    if r.coverage_percent is not None
                    else ""
                )
            )
        for r in state.test_results:
            for ft in r.failing_tests:
                console.print(f"    [red]✗[/red] {ft}")

    # ── Bug reports ───────────────────────────────────────────────────────────
    if state.bug_reports:
        console.print()
        console.print(Rule("[bold]Bug Reports[/bold]"))
        for i, bug in enumerate(state.bug_reports, 1):
            console.print(f"  [red]#{i}[/red]  {bug.failing_test}")
            if bug.root_cause:
                console.print(f"      [dim]Root cause: {bug.root_cause[:120]}[/dim]")

    # ── Proposed fixes ────────────────────────────────────────────────────────
    if state.auto_applied_fixes or state.pending_human_fixes:
        console.print()
        console.print(Rule("[bold]Proposed Fixes[/bold]"))
        for fix in state.auto_applied_fixes:
            console.print(f"  [bold green]✦ AUTO [/bold green] {fix.description}")
            for f in fix.affected_files:
                console.print(f"         [cyan]{f}[/cyan]")
        for fix in state.pending_human_fixes:
            console.print(f"  [bold yellow]⚑ HUMAN[/bold yellow] {fix.description}")
            for f in fix.affected_files:
                console.print(f"         [cyan]{f}[/cyan]")

    # ── Risk reasons ──────────────────────────────────────────────────────────
    if risk and risk.reasons:
        console.print()
        console.print(Rule("[bold]Risk Factors[/bold]"))
        for r in risk.reasons:
            console.print(f"  [dim]•[/dim] {r}")

    # ── Footer ────────────────────────────────────────────────────────────────
    console.print()
    f_count = len(findings)
    b_count = len(state.bug_reports)
    fix_count = len(state.auto_applied_fixes) + len(state.pending_human_fixes)
    console.rule(
        f"[dim]{f_count} finding{'s' if f_count != 1 else ''}  │  "
        f"{b_count} bug{'s' if b_count != 1 else ''}  │  "
        f"{fix_count} fix{'es' if fix_count != 1 else ''}[/dim]",
        style="dim",
    )
    console.print()
