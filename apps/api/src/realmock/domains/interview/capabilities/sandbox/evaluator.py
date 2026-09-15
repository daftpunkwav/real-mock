"""Live coding sandbox test evaluator and execution bridge.

Responsibilities:
- Validate test cases against candidate code outputs.
- Support safe local evaluation and score aggregation.
- Format standardized test results for the WebSocket protocol.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SingleTestCaseResult:
    input_str: str
    expected_str: str
    actual_str: str
    passed: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodeExecutionOutcome:
    passed_all: bool
    total_cases: int
    passed_cases: int
    results: list[SingleTestCaseResult]
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed_all,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "test_results": [r.to_dict() for r in self.results],
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def evaluate_test_cases(
    *,
    test_cases: list[dict[str, Any]],
    candidate_code: str,
    raw_output: str,
) -> CodeExecutionOutcome:
    """Evaluate candidate output against structured test cases."""
    results: list[SingleTestCaseResult] = []
    passed_count = 0

    valid_cases = [tc for tc in test_cases if isinstance(tc, dict)]

    for tc in valid_cases:
        expected = str(tc.get("expected", "")).strip()
        inp = str(tc.get("input", "")).strip()
        # Evaluate match in raw_output
        is_match = expected in raw_output if expected else True
        if is_match:
            passed_count += 1
        results.append(
            SingleTestCaseResult(
                input_str=inp,
                expected_str=expected,
                actual_str="Passed" if is_match else "Mismatch / Not Found",
                passed=is_match,
            )
        )

    all_passed = len(valid_cases) > 0 and passed_count == len(valid_cases)
    return CodeExecutionOutcome(
        passed_all=all_passed,
        total_cases=len(valid_cases),
        passed_cases=passed_count,
        results=results,
        stdout=raw_output,
    )
