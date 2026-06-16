"""
Coverage Analysis Agent

After the sandbox runs the generated tests, this agent:
  1. Parses the coverage report from the sandbox output
  2. Identifies which branches/lines are still uncovered in the changed modules
  3. Updates state.coverage_gaps with specific targets for re-generation
  4. Triggers re-dispatch (via state flag) if gaps are significant (< 80%)
"""

from __future__ import annotations

import re

from src.core.logging import get_logger
from src.core.state import PipelineState, TestResult

log = get_logger(__name__)

_COVERAGE_THRESHOLD = 80.0


def _parse_coverage_from_output(stdout: str) -> dict[str, float]:
    """
    Parse pytest-cov / coverage.py output:
    e.g. "src/auth/service.py      45     3    93%"
    Returns {file_path: coverage_percent}.
    """
    coverage: dict[str, float] = {}
    # Matches lines like: "src/foo.py    100    12    88%"
    pattern = re.compile(r"^(\S+\.py)\s+\d+\s+\d+\s+(\d+)%", re.MULTILINE)
    for match in pattern.finditer(stdout):
        file_path = match.group(1)
        pct = float(match.group(2))
        coverage[file_path] = pct
    return coverage


def run(state: PipelineState) -> dict:
    log.info("coverage_agent_start", results=len(state.test_results))

    gaps: list[str] = []
    updated_results: list[TestResult] = []

    for result in state.test_results:
        coverage_map = _parse_coverage_from_output(result.stdout)

        if not coverage_map and result.coverage_percent is not None:
            # Coverage already parsed by sandbox
            if result.coverage_percent < _COVERAGE_THRESHOLD:
                gaps.append(
                    f"{result.module}: {result.coverage_percent:.1f}% coverage "
                    f"(target {_COVERAGE_THRESHOLD}%)"
                )
            updated_results.append(result)
            continue

        for file_path, pct in coverage_map.items():
            if pct < _COVERAGE_THRESHOLD:
                gaps.append(
                    f"{file_path}: {pct:.1f}% coverage (target {_COVERAGE_THRESHOLD}%)"
                )

        # Update result with parsed coverage
        if coverage_map:
            avg_coverage = sum(coverage_map.values()) / len(coverage_map)
            updated_result = result.model_copy(update={"coverage_percent": avg_coverage})
            updated_results.append(updated_result)
        else:
            updated_results.append(result)

    log.info("coverage_agent_done", gaps=len(gaps))
    return {
        "coverage_gaps": gaps,
        "test_results": updated_results if updated_results else state.test_results,
    }
