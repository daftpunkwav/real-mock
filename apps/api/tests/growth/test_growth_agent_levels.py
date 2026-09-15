"""Agent-level tests for realmock.domains.growth.agents.growth.

Covers: string-list coercion and growth-level aggregation branches.
Conventions: in-memory GrowthRecord dicts/rows; no DB or network.
"""

from __future__ import annotations

import json

from realmock.domains.growth.agents.growth import GrowthAgent, _as_str_list
from realmock.domains.growth.models.growth import GrowthRecord


def _rec(weak, plans):
    return GrowthRecord(
        session_id=1,
        weak_skills=json.dumps(weak),
        training_plan=json.dumps(plans),
    )


class TestAsStrList:
    def test_none(self) -> None:
        assert _as_str_list(None) == []

    def test_list_filters_blank(self) -> None:
        assert _as_str_list(["a", None, "  ", "b", 3]) == ["a", "b", "3"]

    def test_str_json_list(self) -> None:
        assert _as_str_list('["x", " y "]') == ["x", " y "]

    def test_str_invalid_json(self) -> None:
        assert _as_str_list("not-json{{{") == []

    def test_str_json_non_list(self) -> None:
        assert _as_str_list('{"a": 1}') == []

    def test_str_json_list_with_blanks(self) -> None:
        assert _as_str_list('[null, "  ", "ok"]') == ["ok"]

    def test_other_type(self) -> None:
        assert _as_str_list(123) == []
        assert _as_str_list({"a": 1}) == []


class TestGrowthAgentLevels:
    def test_empty(self) -> None:
        out = GrowthAgent().analyze([])
        assert out["total_interviews"] == 0
        assert out["growth_level"] == "To be started"
        assert out["growth_pct"] == 0
        assert out["top_weaknesses"] == []
        assert out["total_plans"] == 0
        assert out["total_weak_skills"] == 0

    def test_starting_stage(self) -> None:
        out = GrowthAgent().analyze([_rec(["a"], ["p1"])])
        assert out["growth_level"] == "Starting stage"
        assert out["total_interviews"] == 1
        assert out["total_plans"] == 1
        assert out["growth_pct"] == 25 + 5

    def test_continuous_growth(self) -> None:
        recs = [_rec([f"w{i % 2}"], []) for i in range(4)]
        out = GrowthAgent().analyze(recs)
        assert out["growth_level"] == "Continuous growth"
        assert out["total_interviews"] == 4

    def test_advanced_promotion(self) -> None:
        recs = [_rec(["w"], ["p1", "p2", "p3", "p4", "p5"]) for _ in range(7)]
        out = GrowthAgent().analyze(recs)
        assert out["growth_level"] == "Advanced promotion"
        # capped at 100
        assert out["growth_pct"] == 100
        assert out["total_weak_skills"] == 1

    def test_top_weaknesses_sorted_and_capped(self) -> None:
        recs = [_rec([f"skill{i}"], []) for i in range(7)]
        recs.append(_rec(["skill0"], []))
        recs.append(_rec(["skill0"], []))
        out = GrowthAgent().analyze(recs)
        assert out["top_weaknesses"][0] == ["skill0", 3]
        assert len(out["top_weaknesses"]) <= 5

    def test_dict_records(self) -> None:
        out = GrowthAgent().analyze(
            [
                {"weak_skills": '["a", "b"]', "training_plan": '["p"]'},
                {"weak_skills": ["a"], "training_plan": []},
                {"weak_skills": None, "training_plan": None},
            ]
        )
        assert out["total_interviews"] == 3
        assert out["total_plans"] == 1
        assert out["growth_level"] == "Continuous growth"

    def test_dict_invalid_json(self) -> None:
        out = GrowthAgent().analyze([{"weak_skills": "junk", "training_plan": "junk"}])
        assert out["total_weak_skills"] == 0
        assert out["total_plans"] == 0

    def test_growth_pct_plan_cap(self) -> None:
        out = GrowthAgent().analyze([_rec([], ["a", "b", "c", "d", "e", "f"])])
        # min(plans,4)*5 = 20
        assert out["growth_pct"] == 25 + 20
