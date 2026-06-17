"""
Structured logging setup.

- stdout : Rich-formatted, phase-grouped, human-readable.
- file   : JSON lines for machine consumption / Render log drain.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import io

import structlog
from rich.console import Console
from rich.text import Text

from src.core.config import settings

# ── Rich console — force UTF-8 so icons work on Windows (CP1252 by default) ──
_stdout_utf8 = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", line_buffering=True
)
_console = Console(file=_stdout_utf8, highlight=False, markup=True)

# ── Phase tracking (module-level so all log calls share state) ────────────────
_current_phase: str | None = None


# ── Event → (phase, icon, rich_style, message_template) ──────────────────────
# message_template uses {key} placeholders filled from the log event kwargs.
# icon   : visual prefix shown before the message
# style  : Rich style string applied to the whole line
# phase  : if non-None, a section header is printed when the phase changes

_EVENT_CONFIG: dict[str, tuple[str | None, str, str, str]] = {
    # ── Server lifecycle ──────────────────────────────────────────────────────
    "sentinel_api_startup":        (None,            "◈", "bold orange1",  "Sentinel listening on port {port}"),
    "sentinel_api_shutdown":       (None,            "◈", "dim",           "Sentinel server shut down"),

    # ── Webhook ───────────────────────────────────────────────────────────────
    "webhook_received":            (None,            "↓", "bold cyan",     "Webhook received  ({gh_event})  delivery {delivery}"),
    "webhook_pr_action_ignored":   (None,            "·", "dim",           "PR action ignored"),
    "webhook_ping_ok":             (None,            "·", "dim",           "Webhook ping OK"),
    "webhook_secret_not_configured":(None,           "⚠", "yellow",        "Webhook secret not configured — requests are unverified"),
    "webhook_signature_invalid":   (None,            "✗", "bold red",      "Webhook signature invalid — request rejected"),

    # ── Pipeline ──────────────────────────────────────────────────────────────
    "pipeline_start":              (None,            "→", "bold white",    "{repo}  PR #{pr}"),
    "pipeline_failed":             (None,            "✗", "bold red",      "Pipeline failed  PR #{pr}  {error}"),

    # ── Risk scoring ──────────────────────────────────────────────────────────
    "risk_scoring_start":          ("RISK SCORING",  "·", "dim",           "Scoring diff  PR #{pr}  ·  {repo}"),
    "risk_score_heuristic_shortcut":(None,           "✓", "green",         "Risk: {risk_level}  (heuristic shortcut)"),
    "risk_score_llm_failed":       (None,            "⚠", "yellow",        "LLM risk scoring failed — falling back to heuristics"),

    # ── Review swarm ──────────────────────────────────────────────────────────
    "security_agent_start":        ("REVIEW SWARM",  "·", "dim",           "Security agent running..."),
    "performance_agent_start":     (None,            "·", "dim",           "Performance agent running..."),
    "style_agent_start":           (None,            "·", "dim",           "Style agent running..."),
    "architecture_agent_start":    (None,            "·", "dim",           "Architecture agent running..."),
    "security_agent_done":         (None,            "✓", "green",         "Security      {count} findings"),
    "performance_agent_done":      (None,            "✓", "green",         "Performance   {count} findings"),
    "style_agent_done":            (None,            "✓", "green",         "Style         {count} findings"),
    "architecture_agent_done":     (None,            "✓", "green",         "Architecture  {count} findings"),
    "security_agent_llm_failed":   (None,            "⚠", "yellow",        "Security agent LLM call failed"),
    "performance_agent_llm_failed":(None,            "⚠", "yellow",        "Performance agent LLM call failed"),
    "style_agent_llm_failed":      (None,            "⚠", "yellow",        "Style agent LLM call failed"),
    "architecture_agent_llm_failed":(None,           "⚠", "yellow",        "Architecture agent LLM call failed"),
    "lead_reviewer_start":         (None,            "·", "dim",           "Lead reviewer consolidating findings..."),
    "lead_reviewer_llm_failed":    (None,            "⚠", "yellow",        "Lead reviewer LLM call failed"),

    # ── Test generation ───────────────────────────────────────────────────────
    "module_test_agent_start":     ("TEST GENERATION","·","dim",           "Generating tests for {files} changed files..."),
    "test_generated":              (None,            "✓", "green",         "Generated tests for  {module}"),
    "test_generation_failed":      (None,            "⚠", "yellow",        "Test generation failed  {module}  —  {error}"),
    "module_test_agent_done":      (None,            "·", "dim",           "{generated} test file(s) generated"),
    "module_test_agent_no_testable_files": (None,    "·", "dim",           "No testable source files changed"),
    "integration_test_agent_start":(None,            "·", "dim",           "Integration test agent running..."),
    "integration_test_generated":  (None,            "✓", "green",         "Integration test written"),
    "integration_test_agent_skipped":(None,          "·", "dim",           "Integration tests skipped (no api / e2e dir found)"),

    # ── Sandbox ───────────────────────────────────────────────────────────────
    "sandbox_running_jest":        ("SANDBOX",       "·", "dim",           "Running Jest tests..."),
    "sandbox_run_done":            (None,            "·", "cyan",          "Sandbox done  exit {exit_code}  ·  {passed} passed  ·  {failed} failed"),
    "sandbox_skipped":             (None,            "·", "dim",           "Sandbox skipped  ({reason})"),
    "sandbox_run_failed":          (None,            "✗", "bold red",      "Sandbox run failed  —  {error}"),
    "sandbox_timeout":             (None,            "⚠", "yellow",        "Sandbox timed out"),
    "sandbox_docker_unavailable":  (None,            "⚠", "yellow",        "Docker unavailable — sandbox disabled"),
    "sandbox_jest_failed":         (None,            "⚠", "yellow",        "Jest run failed"),
    "sandbox_jest_timeout":        (None,            "⚠", "yellow",        "Jest timed out"),
    "sandbox_jest_no_tests_found": (None,            "·", "dim",           "Jest: no test files found"),
    "sandbox_patch_run_failed":    (None,            "⚠", "yellow",        "Patch verification run failed"),
    "sandbox_empty_patch":         (None,            "·", "dim",           "Skipping sandbox — patch is empty"),

    # ── Bug squad ─────────────────────────────────────────────────────────────
    "reproduction_agent_start":    ("BUG SQUAD",     "·", "dim",           "Reproducing {failing} failing test(s)..."),
    "reproduction_agent_done":     (None,            "✓", "green",         "{reports} bug report(s) created"),
    "root_cause_agent_start":      (None,            "·", "dim",           "Root-cause analysis ({reports} reports)..."),
    "root_cause_agent_done":       (None,            "✓", "green",         "Root-cause analysis complete"),
    "fix_proposer_start":          (None,            "·", "dim",           "Proposing fixes for {reports} report(s)..."),
    "fix_proposer_done":           (None,            "✓", "green",         "Fix proposals complete"),
    "fix_proposed":                (None,            "✓", "green",         "Fix proposed  (confidence {confidence})"),
    "fix_verified":                (None,            "✓", "green",         "Fix verified by sandbox"),
    "fix_rejected":                (None,            "⚠", "yellow",        "Fix rejected — tests still failing"),
    "fix_proposal_failed":         (None,            "⚠", "yellow",        "Fix proposal failed"),

    # ── Approval gate ─────────────────────────────────────────────────────────
    "approval_gate_start":         ("APPROVAL GATE", "·", "dim",           "Evaluating {fixes} proposed fix(es)..."),
    "fix_approved":                (None,            "✓", "green",         "Fix approved  →  awaiting merge"),
    "fix_auto_merge":              (None,            "✓", "green",         "Fix auto-committed  —  {description}"),
    "fix_committed":               (None,            "✓", "bold green",    "Committed  {sha}  on  {branch}"),
    "fix_human_required":          (None,            "⚠", "yellow",        "Human review required  —  {description}"),
    "fix_human_required_regression_block":(None,     "⚠", "yellow",        "Blocked — regression detected"),
    "approved_fix_committed":      (None,            "✓", "bold green",    "Approved fix committed to repo"),
    "approved_fix_commit_failed":  (None,            "✗", "bold red",      "Failed to commit approved fix"),

    # ── Knowledge base ────────────────────────────────────────────────────────
    "kb_store_connected":          (None,            "·", "dim",           "Knowledge base connected  ({collection})"),
    "kb_store_unavailable":        (None,            "⚠", "yellow",        "Knowledge base unavailable"),
    "kb_upserted":                 ("KNOWLEDGE BASE","✓", "green",         "KB updated  [{type}]  {title}"),
    "kb_embed_failed":             (None,            "⚠", "yellow",        "Embedding failed — entry skipped"),
    "loading_embedding_model":     (None,            "·", "dim",           "Loading embedding model  ({model})..."),
    "hf_api_unreachable_falling_back_to_local": (None,"·","dim",           "HF API unreachable — using local embeddings"),

    # ── Self-healing maintenance ───────────────────────────────────────────────
    "curator_agent_start":         ("MAINTENANCE",   "·", "dim",           "Curator running..."),
    "curator_agent_done":          (None,            "✓", "green",         "Curator complete"),
    "drift_checker_start":         (None,            "·", "dim",           "Drift checker running..."),
    "drift_checker_done":          (None,            "✓", "green",         "Drift checker complete"),
    "consistency_agent_start":     (None,            "·", "dim",           "Consistency agent running..."),
    "consistency_agent_done":      (None,            "✓", "green",         "Consistency check complete"),
    "consolidation_agent_start":   (None,            "·", "dim",           "Consolidation agent running..."),
    "consolidation_agent_done":    (None,            "✓", "green",         "Consolidation complete"),
    "manual_maintenance_done":     (None,            "✓", "green",         "Manual maintenance complete"),

    # ── GitHub integration ────────────────────────────────────────────────────
    "pr_comment_posted":           (None,            "✓", "bold green",    "Review comment posted  →  {url}"),

    # ── Misc warnings / errors ────────────────────────────────────────────────
    "agent_timeout":               (None,            "⚠", "yellow",        "Agent timed out  ({agent})  limit={timeout}s"),
    "policy_load_error":           (None,            "⚠", "yellow",        "Policy load error"),
    "policy_using_defaults":       (None,            "·", "dim",           "Using default policy"),
}


def _format_event(event: str, level: str, kw: dict[str, Any]) -> str | None:
    """
    Return a Rich-markup string for the given event, or None to suppress.
    Warnings and errors are never suppressed even if unmapped.
    """
    global _current_phase

    lines: list[str] = []
    config = _EVENT_CONFIG.get(event)

    if config:
        phase, icon, style, template = config

        # Phase header (printed once per phase change)
        if phase and phase != _current_phase:
            _current_phase = phase
            lines.append(f"\n  [bold white]{phase}[/bold white]")

        # Fill template with available kwargs; leave missing placeholders as-is
        try:
            msg = template.format_map({k: v for k, v in kw.items() if v is not None})
        except (KeyError, ValueError):
            msg = template

        # Special rendering for pipeline_start: banner
        if event == "pipeline_start":
            repo = kw.get("repo", "")
            pr = kw.get("pr", "")
            banner = f"  SENTINEL  ·  PR #{pr}  ·  {repo}"
            sep = "─" * (len(banner) + 2)
            lines = [
                f"\n[bold white]{sep}[/bold white]",
                f"[bold white]{banner}[/bold white]",
                f"[bold white]{sep}[/bold white]",
            ]
            return "\n".join(lines)

        # Special rendering for pr_comment_posted: footer banner
        if event == "pr_comment_posted":
            url = kw.get("url", "")
            pr = kw.get("pr", "")
            sep = "─" * 60
            lines = [
                f"\n[bold green]{sep}[/bold green]",
                f"[bold green]  ✓  Review posted  ·  PR #{pr}[/bold green]",
                f"[bold green]  {url}[/bold green]",
                f"[bold green]{sep}[/bold green]\n",
            ]
            return "\n".join(lines)

        # Special rendering for pipeline_failed
        if event == "pipeline_failed":
            error = str(kw.get("error", "unknown error"))[:80]
            sep = "─" * 60
            lines = [
                f"\n[bold red]{sep}[/bold red]",
                f"[bold red]  ✗  Pipeline failed  ·  PR #{kw.get('pr', '')}[/bold red]",
                f"[bold red]  {error}[/bold red]",
                f"[bold red]{sep}[/bold red]\n",
            ]
            return "\n".join(lines)

        lines.append(f"  [{style}]{icon}  {msg}[/{style}]")
        return "\n".join(lines)

    # Unmapped event: only surface warnings/errors so the terminal stays clean
    if level in ("warning", "error", "critical"):
        kw_str = "  ".join(f"{k}={v}" for k, v in kw.items() if k != "event")
        colour = "bold red" if level in ("error", "critical") else "yellow"
        return f"  [{colour}]⚠  {event}  {kw_str}[/{colour}]"

    return None  # suppress unknown info/debug events


class _RichConsoleProcessor:
    """structlog processor that emits formatted Rich output and returns None."""

    def __call__(self, logger: Any, method: str, event_dict: dict) -> dict:
        event = event_dict.pop("event", "")
        level = event_dict.pop("level", "info")

        # Remove structlog internals we don't need for display
        for key in ("logger", "timestamp", "_record"):
            event_dict.pop(key, None)

        line = _format_event(event, level, event_dict)
        if line is not None:
            _console.print(line)

        # Raise DropEvent so structlog doesn't double-print anything
        raise structlog.DropEvent()


def configure_logging(quiet: bool = False) -> None:
    """
    quiet=True  — console output suppressed (used by CLI scan/run so Rich
                  progress bars aren't mixed with log lines).
    quiet=False — pretty console output + JSON file (default, used by server).
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    Path(settings.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)

    # ── Shared stdlib processors (used by the file/JSON formatter) ────────────
    _shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # ── Console renderer (stdout) — wraps the whole chain ────────────────────
    console_processors = _shared + [_RichConsoleProcessor()]

    # ── JSON renderer (file) ──────────────────────────────────────────────────
    json_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    # ── Configure structlog to use the console chain by default ───────────────
    structlog.configure(
        processors=console_processors,  # type: ignore[arg-type]
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── stdlib root logger: file handler only (console is handled above) ──────
    handlers: list[logging.Handler] = []

    try:
        fh = logging.FileHandler(settings.LOG_FILE, encoding="utf-8")
        fh.setFormatter(json_formatter)
        handlers.append(fh)
    except OSError:
        pass

    # Quiet mode: if the caller wants no console, we're done.
    # Non-quiet mode: structlog already prints to console via _RichConsoleProcessor;
    # the stdlib root logger only needs the file handler.
    root = logging.getLogger()
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)
    root.setLevel(log_level)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
