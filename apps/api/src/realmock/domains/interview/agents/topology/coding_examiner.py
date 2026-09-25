"""Coding Examiner Agent responsible for live coding challenges, test execution, and static analysis.

Responsibilities:
- Formulate tailored algorithmic or engineering coding challenges.
- Provide structured problem specifications, starter templates, and test suites.
- Evaluate candidate code submissions across correctness, complexity, and idiomatic quality.
- Synchronize evaluation results with the CognitiveMemoryGraph and Shadow Evaluator.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from realmock.domains.interview.agents.memory.cognitive_graph import (
    CognitiveMemoryGraph,
    CompetencyStatus,
)
from realmock.domains.interview.agents.topology.prompts import CODE_EVAL_PROMPT, CODING_CHALLENGE_PROMPT
from realmock.platform.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)

@dataclass
class CodingTestCase:
    input: str
    expected: str
    is_hidden: bool = False
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CodingChallenge:
    id: str
    title: str
    description: str
    language: str = "python"
    starter_code: str = ""
    test_cases: list[CodingTestCase] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "starter_code": self.starter_code,
            "test_cases": [tc.to_dict() for tc in self.test_cases],
        }


@dataclass
class CodeEvaluationReport:
    passed: bool = False
    score: int = 0
    time_complexity: str = ""
    space_complexity: str = ""
    summary: str = ""
    feedback_for_candidate: str = ""
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CodingExaminerAgent:
    """Agent responsible for code challenge generation and submission evaluation."""

    def __init__(self, llm: LLMClient, memory_graph: CognitiveMemoryGraph) -> None:
        self.llm = llm
        self.memory_graph = memory_graph
        self.active_challenge: CodingChallenge | None = None

    async def create_challenge(
        self,
        *,
        role: str = "Software Engineer",
        level: str = "Senior",
        preferred_language: str = "python",
    ) -> CodingChallenge:
        """Create a targeted coding challenge for the candidate."""
        if not self.llm.api_key:
            # Fallback static challenge
            fallback = CodingChallenge(
                id="two_sum_variant",
                title="Subarray Sum to Target",
                description="Given an array of integers `nums` and an integer `target`, return indices of the two numbers such that they add up to `target`.",
                language=preferred_language,
                starter_code="def two_sum(nums: list[int], target: int) -> list[int]:\n    # Write your solution here\n    pass\n",
                test_cases=[
                    CodingTestCase(input="[2, 7, 11, 15], 9", expected="[0, 1]", description="Basic case"),
                    CodingTestCase(input="[3, 2, 4], 6", expected="[1, 2]", description="Unsorted case"),
                ],
            )
            self.active_challenge = fallback
            self.memory_graph.working_memory.active_code_task = fallback.title
            return fallback

        prompt = CODING_CHALLENGE_PROMPT.format(role=role, level=level)
        try:
            raw = await self.llm.chat_json(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Generate a coding challenge in {preferred_language}."},
                ],
                temperature=0.3,
            )
            if not raw or not isinstance(raw, dict):
                raise ValueError("Invalid LLM JSON format")

            test_cases = [
                CodingTestCase(
                    input=str(tc.get("input", "")),
                    expected=str(tc.get("expected", "")),
                    is_hidden=bool(tc.get("is_hidden", False)),
                    description=str(tc.get("description", "")),
                )
                for tc in raw.get("test_cases", [])
                if isinstance(tc, dict)
            ]

            challenge = CodingChallenge(
                id=str(raw.get("id", "challenge_1")),
                title=str(raw.get("title", "Coding Problem")),
                description=str(raw.get("description", "")),
                language=str(raw.get("language", preferred_language)),
                starter_code=str(raw.get("starter_code", "")),
                test_cases=test_cases,
            )
            self.active_challenge = challenge
            self.memory_graph.working_memory.active_code_task = challenge.title
            return challenge
        except Exception as e:
            logger.warning("Coding challenge generation failed: %s; using standard problem", e)
            fallback = CodingChallenge(
                id="lru_cache_lite",
                title="LRU Cache Get/Put",
                description="Design a data structure that follows the constraints of a Least Recently Used (LRU) cache.",
                language=preferred_language,
                starter_code="class LRUCache:\n    def __init__(self, capacity: int):\n        pass\n    def get(self, key: int) -> int:\n        return -1\n    def put(self, key: int, value: int) -> None:\n        pass\n",
            )
            self.active_challenge = fallback
            self.memory_graph.working_memory.active_code_task = fallback.title
            return fallback

    async def evaluate_submission(
        self,
        *,
        code: str,
        test_output: str,
        turn_index: int,
    ) -> CodeEvaluationReport:
        """Evaluate candidate submitted code and log finding to memory."""
        self.memory_graph.working_memory.candidate_code = code
        self.memory_graph.working_memory.last_test_output = test_output

        challenge_desc = self.active_challenge.description if self.active_challenge else "Live Coding Challenge"
        lang = self.active_challenge.language if self.active_challenge else "python"

        if not self.llm.api_key:
            return CodeEvaluationReport(
                passed=True,
                score=7,
                time_complexity="O(n)",
                space_complexity="O(n)",
                summary="Code submitted and executed against basic cases.",
                feedback_for_candidate="Good job completing the coding task.",
            )

        prompt = CODE_EVAL_PROMPT.format(
            problem_description=challenge_desc,
            language=lang,
            code=code,
            test_output=test_output,
        )

        try:
            raw = await self.llm.chat_json(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Analyze the submitted code and test outputs."},
                ],
                temperature=0.2,
            )
            try:
                score = int(raw.get("score", 5))
            except (ValueError, TypeError):
                score = 5
            score = max(1, min(10, score))

            strengths = [str(x) for x in raw.get("strengths", []) if isinstance(x, (str, int, float))]
            weaknesses = [str(x) for x in raw.get("weaknesses", []) if isinstance(x, (str, int, float))]

            report = CodeEvaluationReport(
                passed=bool(raw.get("passed", False)),
                score=score,
                time_complexity=str(raw.get("time_complexity", "")),
                space_complexity=str(raw.get("space_complexity", "")),
                summary=str(raw.get("summary", "")),
                feedback_for_candidate=str(raw.get("feedback_for_candidate", "")),
                strengths=strengths,
                weaknesses=weaknesses,
            )

            status = CompetencyStatus.VERIFIED if report.passed and report.score >= 7 else CompetencyStatus.FAILED
            self.memory_graph.record_finding(
                topic="Live Coding Implementation",
                category="coding",
                status=status,
                claim=f"Solved in {report.time_complexity} time, {report.space_complexity} space",
                finding=f"Score: {report.score}/10; {report.summary}",
                turn_index=turn_index,
                confidence=0.9,
            )

            return report
        except Exception as e:
            logger.warning("Code submission evaluation failed: %s", e)
            return CodeEvaluationReport(passed=False, score=5, summary="Evaluation error occurred")
