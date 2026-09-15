"""Unit tests for sandbox test evaluation."""

from realmock.domains.interview.capabilities.sandbox import (
    CodeExecutionOutcome,
    SingleTestCaseResult,
    evaluate_test_cases,
)


def test_evaluate_test_cases_success():
    cases = [
        {"input": "[1, 2]", "expected": "3"},
        {"input": "[0, 0]", "expected": "0"},
    ]
    raw_output = "Computed sum is 3 for case 1, and 0 for case 2"
    outcome = evaluate_test_cases(
        test_cases=cases,
        candidate_code="def sum_two(a, b): return a + b",
        raw_output=raw_output,
    )

    assert outcome.passed_all is True
    assert outcome.total_cases == 2
    assert outcome.passed_cases == 2


def test_evaluate_test_cases_failure():
    cases = [
        {"input": "[1, 2]", "expected": "3"},
        {"input": "[5, 5]", "expected": "10"},
    ]
    raw_output = "Output: 3. Case 2 failed."
    outcome = evaluate_test_cases(
        test_cases=cases,
        candidate_code="def sum_two(a, b): return 3",
        raw_output=raw_output,
    )

    assert outcome.passed_all is False
    assert outcome.total_cases == 2
    assert outcome.passed_cases == 1


def test_evaluate_test_cases_malformed_input():
    cases = [
        {"input": "[1, 2]", "expected": "3"},
        "not_a_dict_case",  # should be safely filtered out
    ]
    outcome = evaluate_test_cases(
        test_cases=cases,  # type: ignore
        candidate_code="def sum_two(a, b): return 3",
        raw_output="Output: 3",
    )
    assert outcome.total_cases == 1
    assert outcome.passed_all is True
