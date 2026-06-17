"""
LangGraph Pipeline

Defines the full SENTINEL execution graph.

Graph topology:
  [START]
    │
    ▼
  triage (risk_scorer)
    │
    ├─ LOW risk ──────────────────────┐
    │                                  │
    ▼                                  │
  [PARALLEL]                          │
  review_security  review_perf         │
  review_style     review_arch         │
    │                                  │
    ▼                                  │
  lead_review                          │
    │                                  │
    ▼                                  │
  generate_tests ◄─────────────────────┘
    │
    ▼
  run_tests (sandbox)
    │
    ├─ no failures ─────────────────┐
    │                                │
    ▼                                │
  coverage_analysis                  │
    │                                │
    ▼                                │
  [if medium/high] integration_tests │
    │                                │
    ▼                                │
  [if failures] ──────────────────── ▼
  reproduce_bugs                  explain_findings
  root_cause_analysis                │
  propose_fixes                      ▼
  verify_fixes ──────────────────► approval_gate
                                     │
                                     ▼
                                   finalise (orchestrator)
                                     │
                                    [END]
"""

from __future__ import annotations

from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from src.agents import (
    orchestrator,
    risk_scorer,
)
from src.agents.bug_squad import (
    fix_proposer_agent,
    reproduction_agent,
    root_cause_agent,
    verification_agent,
)
from src.agents.review_swarm import (
    architecture_agent,
    lead_reviewer,
    performance_agent,
    security_agent,
    style_agent,
)
from src.agents.self_healing import (
    consolidation,
    consistency,
    curator,
    drift_checker,
)
from src.agents.test_swarm import (
    coverage_agent,
    integration_test_agent,
    module_test_agent,
)
from src.agents.trust_layer import approval_gate, explainability_agent
from src.core.logging import get_logger
from src.core.project_utils import detect_project_type
from src.core.sandbox import Sandbox
from src.core.state import PipelineState, PipelineStatus, RiskLevel
from src.knowledge_base.store import KnowledgeBaseStore

log = get_logger(__name__)

# Shared instances — created once per process
_kb: KnowledgeBaseStore | None = None
_sandbox: Sandbox | None = None


def get_kb() -> KnowledgeBaseStore:
    global _kb
    if _kb is None:
        _kb = KnowledgeBaseStore()
    return _kb


def get_sandbox() -> Sandbox:
    global _sandbox
    if _sandbox is None:
        _sandbox = Sandbox()
    return _sandbox


# ── Node wrappers ─────────────────────────────────────────────────────────────
# Each node receives the full PipelineState and returns a partial dict.

def node_load_policy(state: PipelineState) -> dict:
    """Fetch sentinel.yaml from the PR's repo and store it in state before any agent runs."""
    from src.core.policy import load_policy, SentinelPolicy
    from src.core.token_tracker import RunTokenTracker, set_tracker

    # Activate a fresh token tracker for this run
    set_tracker(RunTokenTracker())

    if state.pr is None:
        return {"policy": SentinelPolicy()}

    try:
        policy = load_policy(state.pr.repo_full_name, state.pr.head_sha)
    except Exception as exc:
        log.warning("policy_load_error", error=str(exc))
        policy = SentinelPolicy()

    return {"policy": policy}


def node_triage(state: PipelineState) -> dict:
    return {**risk_scorer.run(state), "status": PipelineStatus.TRIAGING}


def _run_with_timeout(fn, *args, timeout: int = 60) -> dict:
    """Run a review agent with a hard timeout so one hung LLM call can't block the pipeline."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(fn, *args)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            log.warning("agent_timeout", agent=fn.__module__, timeout=timeout)
            return {}


def node_security(state: PipelineState) -> dict:
    return _run_with_timeout(security_agent.run, state, get_kb())


def node_performance(state: PipelineState) -> dict:
    return _run_with_timeout(performance_agent.run, state, get_kb())


def node_style(state: PipelineState) -> dict:
    return _run_with_timeout(style_agent.run, state, get_kb())


def node_architecture(state: PipelineState) -> dict:
    return _run_with_timeout(architecture_agent.run, state, get_kb())


def node_lead_review(state: PipelineState) -> dict:
    return {**lead_reviewer.run(state), "status": PipelineStatus.REVIEWING}


def node_generate_tests(state: PipelineState) -> dict:
    return module_test_agent.run(state, get_kb())


def node_run_tests(state: PipelineState) -> dict:
    """Write generated tests to sandbox and run the full suite."""
    from src.integrations.git_utils import archive_pr_branch

    pr = state.pr
    if pr is None:
        return {"test_results": []}

    from src.core.state import TestResult

    project_type = detect_project_type(pr.files_changed)

    extra_files: dict[str, str] = {}
    for gt in state.generated_tests:
        extra_files[gt.file_path] = gt.content

    # For local scans the archive is pre-populated in state; skip the GitHub fetch.
    if state.repo_archive:
        repo_archive = state.repo_archive
    else:
        try:
            repo_archive = archive_pr_branch(
                repo_full_name=pr.repo_full_name,
                ref=pr.head_sha,
            )
        except Exception as exc:
            log.warning("archive_failed", error=str(exc))
            return {"test_results": [], "errors": state.errors + [f"Sandbox archive failed: {exc}"]}

    # Skip sandbox when Docker is unavailable (e.g. Render free tier)
    import os
    if os.environ.get("DISABLE_SANDBOX", "").lower() in ("1", "true", "yes"):
        log.info("sandbox_skipped", reason="DISABLE_SANDBOX=true")
        return {"test_results": []}

    try:
        sandbox = get_sandbox()
    except Exception as _docker_err:
        log.warning("sandbox_docker_unavailable", error=str(_docker_err))
        return {"test_results": [], "errors": state.errors + ["Docker unavailable — sandbox skipped"]}

    if project_type == "javascript":
        log.info("sandbox_running_jest", files=len(pr.files_changed))
        result = sandbox.run_js_tests(repo_archive, extra_files=extra_files)
        # If jest found no tests at all (no test files in project), report gracefully
        if result.exit_code != 0 and result.passed == 0 and result.failed == 0:
            log.info("sandbox_jest_no_tests_found")
            test_result = TestResult(
                module="all",
                passed=0, failed=0, errors=0,
                coverage_percent=None,
                failing_tests=[],
                stdout=(
                    "No test files found in this JavaScript/TypeScript project.\n"
                    "Add test files matching *.test.ts / *.spec.ts to enable sandbox testing.\n\n"
                    + result.stdout[:2000]
                ),
                stderr=result.stderr[:1000],
            )
        else:
            test_result = TestResult(
                module="all",
                passed=result.passed,
                failed=result.failed,
                errors=result.errors,
                coverage_percent=None,
                failing_tests=_extract_failing_tests(result.stdout + result.stderr),
                stdout=result.stdout[:8000],
                stderr=result.stderr[:2000],
            )
    else:
        result = sandbox.run_tests(repo_archive, extra_files=extra_files)
        test_result = TestResult(
            module="all",
            passed=result.passed,
            failed=result.failed,
            errors=result.errors,
            coverage_percent=result.coverage_percent,
            failing_tests=_extract_failing_tests(result.stdout),
            stdout=result.stdout[:8000],
            stderr=result.stderr[:2000],
        )

    # Store the archive so verification_agent can apply patches without re-fetching.
    return {
        "test_results": [test_result],
        "repo_archive": repo_archive,
        "status": PipelineStatus.TESTING,
    }


def node_coverage(state: PipelineState) -> dict:
    return coverage_agent.run(state)


def node_integration_tests(state: PipelineState) -> dict:
    return integration_test_agent.run(state)


def node_reproduce_bugs(state: PipelineState) -> dict:
    return {**reproduction_agent.run(state), "status": PipelineStatus.BUG_HUNTING}


def node_root_cause(state: PipelineState) -> dict:
    return root_cause_agent.run(state, get_kb())


def node_propose_fixes(state: PipelineState) -> dict:
    return fix_proposer_agent.run(state, get_kb())


def node_verify_fixes(state: PipelineState) -> dict:
    return verification_agent.run(state, get_sandbox())


def node_explain(state: PipelineState) -> dict:
    return {**explainability_agent.run(state), "status": PipelineStatus.ANNOTATING}


def node_approval_gate(state: PipelineState) -> dict:
    return {**approval_gate.run(state, get_kb()), "status": PipelineStatus.GATING}


def node_finalise(state: PipelineState) -> dict:
    from src.core.token_tracker import get_tracker
    tracker = get_tracker()
    result = {**orchestrator.run(state, get_kb()), "status": PipelineStatus.DONE}
    if tracker:
        result["token_total"] = tracker.total_tokens
        result["est_cost_usd"] = tracker.est_cost_usd
    return result


# ── Conditional routing ───────────────────────────────────────────────────────

def route_after_triage(
    state: PipelineState,
) -> Literal["start_review", "generate_tests"]:
    """LOW-risk PRs skip the full review swarm and go straight to test generation.
    --force-review overrides this and always runs the full swarm."""
    if state.force_review:
        return "start_review"
    if state.risk and state.risk.level == RiskLevel.LOW:
        return "generate_tests"
    return "start_review"


def route_after_tests(state: PipelineState) -> Literal["coverage", "reproduce_bugs"]:
    if state.has_test_failures():
        return "reproduce_bugs"
    return "coverage"


def route_integration_tests(state: PipelineState) -> Literal["integration_tests", "explain"]:
    if state.risk and state.risk.level != RiskLevel.LOW:
        return "integration_tests"
    return "explain"


def route_after_integration(state: PipelineState) -> Literal["explain"]:
    return "explain"


# ── Graph construction ────────────────────────────────────────────────────────

def node_start_review(_state: PipelineState) -> dict:
    """No-op fan-out gate — allows conditional routing before the parallel swarm."""
    return {}


def build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    # Register all nodes
    graph.add_node("load_policy", node_load_policy)
    graph.add_node("triage", node_triage)
    graph.add_node("start_review", node_start_review)
    graph.add_node("review_security", node_security)
    graph.add_node("review_performance", node_performance)
    graph.add_node("review_style", node_style)
    graph.add_node("review_architecture", node_architecture)
    graph.add_node("lead_review", node_lead_review)
    graph.add_node("generate_tests", node_generate_tests)
    graph.add_node("run_tests", node_run_tests)
    graph.add_node("coverage", node_coverage)
    graph.add_node("integration_tests", node_integration_tests)
    graph.add_node("reproduce_bugs", node_reproduce_bugs)
    graph.add_node("root_cause", node_root_cause)
    graph.add_node("propose_fixes", node_propose_fixes)
    graph.add_node("verify_fixes", node_verify_fixes)
    graph.add_node("explain", node_explain)
    graph.add_node("approval_gate", node_approval_gate)
    graph.add_node("finalise", node_finalise)

    # Entry: load per-repo policy first, then triage
    graph.add_edge(START, "load_policy")
    graph.add_edge("load_policy", "triage")

    # LOW risk → skip review swarm, go straight to test generation.
    # MEDIUM/HIGH → fan-out to all four specialist reviewers in parallel.
    graph.add_conditional_edges("triage", route_after_triage)

    # Parallel review swarm — fan-out from the gate node
    graph.add_edge("start_review", "review_security")
    graph.add_edge("start_review", "review_performance")
    graph.add_edge("start_review", "review_style")
    graph.add_edge("start_review", "review_architecture")

    # Lead reviewer waits for all four
    graph.add_edge("review_security", "lead_review")
    graph.add_edge("review_performance", "lead_review")
    graph.add_edge("review_style", "lead_review")
    graph.add_edge("review_architecture", "lead_review")

    # Test generation
    graph.add_edge("lead_review", "generate_tests")
    graph.add_edge("generate_tests", "run_tests")

    # Conditional: failures → bug squad, else → coverage
    graph.add_conditional_edges("run_tests", route_after_tests)

    # Bug squad (sequential chain)
    graph.add_edge("reproduce_bugs", "root_cause")
    graph.add_edge("root_cause", "propose_fixes")
    graph.add_edge("propose_fixes", "verify_fixes")
    graph.add_edge("verify_fixes", "explain")

    # Coverage → integration tests only for MEDIUM/HIGH risk, else skip to explain
    graph.add_conditional_edges("coverage", route_integration_tests)
    graph.add_edge("integration_tests", "explain")

    # Trust layer
    graph.add_edge("explain", "approval_gate")
    graph.add_edge("approval_gate", "finalise")
    graph.add_edge("finalise", END)

    return graph


def compile_pipeline():
    graph = build_graph()
    return graph.compile()


# ── Utility ───────────────────────────────────────────────────────────────────

def _extract_failing_tests(stdout: str) -> list[str]:
    import re
    failing = []

    # pytest: "FAILED tests/test_foo.py::test_bar - AssertionError"
    for m in re.finditer(r"FAILED\s+([\w/\.]+::[\w\[\]]+)", stdout):
        failing.append(m.group(1))

    # jest: "  ● DescribeName › test name"
    for m in re.finditer(r"^\s+●\s+(.+)$", stdout, re.MULTILINE):
        name = m.group(1).strip()
        if name and not name.startswith("●"):
            failing.append(name)

    return list(dict.fromkeys(failing))  # deduplicate, preserve order
