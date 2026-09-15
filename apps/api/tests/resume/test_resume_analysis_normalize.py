"""Analysis normalize tests for src/realmock/domains/resume/services/analysis_normalize.py.

Covers: normalize_resume_analysis_payload basic/clamp/empty/locale/nested/weights/
scores/dims/rewrite/suggestion blobs plus deep-questions/repo-evidence/suggestion
edges, rewrite-pair loaders, score coerce/pick/weights/percentile branches.
Conventions: no real network/model downloads (all clients mocked); pure logic.
"""

from types import SimpleNamespace

from realmock.domains.resume.services.analysis_normalize import (
    normalize_resume_analysis_payload,
)
from realmock.domains.resume.schemas.resume import ResumeAnalysis


def test_normalize_basic():
    raw = {
        "score": 88,
        "strengths": ["A"],
        "weaknesses": ["B"],
        "dimension_scores": {
            "tech_depth": 90,
            "role_fit": {"score": 80, "comment": "Match"},
        },
        "predicted_questions": ["Q1"],
    }
    data = normalize_resume_analysis_payload(raw)
    analysis = ResumeAnalysis.model_validate(data)
    assert analysis.score == 88
    assert analysis.dimension_scores["tech_depth"].score == 90
    assert analysis.dimension_scores["role_fit"].comment == "Match"


def test_normalize_clamps_score():
    data = normalize_resume_analysis_payload({"score": 150, "strengths": "bad"})
    analysis = ResumeAnalysis.model_validate(data)
    assert analysis.score == 100
    assert analysis.strengths == []


def test_normalize_empty():
    data = normalize_resume_analysis_payload({})
    analysis = ResumeAnalysis.model_validate(data)
    assert analysis.score == 0


def test_normalize_decimal_string_score_and_percentile():
    """Decimal score strings truncate; percentile is derived from the total, not the LLM field."""
    from realmock.domains.resume.services.analysis_normalize import (
        benchmark_percentile_from_score,
    )

    data = normalize_resume_analysis_payload(
        {"score": "88.7", "benchmark_percentile": "72.5"}
    )
    assert data["score"] == 88
    assert data["benchmark_percentile"] == benchmark_percentile_from_score(88)


def test_normalize_invalid_inputs_keep_semantics():
    """Invalid score becomes 0; percentile still follows the fixed conversion."""
    from realmock.domains.resume.services.analysis_normalize import (
        benchmark_percentile_from_score,
    )

    data = normalize_resume_analysis_payload(
        {"score": "abc", "benchmark_percentile": "abc"}
    )
    assert data["score"] == 0
    assert data["benchmark_percentile"] == benchmark_percentile_from_score(0)
    data = normalize_resume_analysis_payload({"benchmark_percentile": None})
    assert data["benchmark_percentile"] == benchmark_percentile_from_score(0)


def test_normalize_zh_cn_applies_fullwidth_punctuation():
    """zh-CN locale converts half-width punctuation adjacent to CJK."""
    data = normalize_resume_analysis_payload(
        {"content_review": "项目不错,但缺少量化.", "score": 70},
        locale="zh-CN",
    )
    assert "，" in data["content_review"]
    assert "。" in data["content_review"]


def test_normalize_en_skips_cn_punctuation():
    """en locale must not rewrite English punctuation to full-width."""
    text = "Strong projects, but missing metrics."
    data = normalize_resume_analysis_payload(
        {"content_review": text, "score": 70},
        locale="en",
    )
    assert data["content_review"] == text


def test_normalize_nested_review_blobs():
    data = normalize_resume_analysis_payload(
        {
            "score": 40,
            "rewrite_examples": [{"before": "old", "after": "new"}],
            "section_reviews": [
                {"section": "Projects", "score": 80, "verdict": "ok", "detail": "d"}
            ],
            "project_cards": [
                {
                    "name": "P",
                    "score": 70,
                    "one_line": "line",
                    "highlights": ["h"],
                    "risks": ["r"],
                    "deep_questions": ["q"],
                }
            ],
            "skill_trust": {"solid": ["Python"], "claimed": [], "missing": ["K8s"]},
            "career_analysis": {"trajectory": "up", "stability_score": 60, "gaps": []},
            "company_fit": [{"tier": "startup", "fit_score": 55, "reason": "match"}],
            "repo_evidence": [
                {
                    "repo": "me/app",
                    "url": "https://github.com/me/app",
                    "stars": 4,
                    "languages": ["Python"],
                    "evidence_notes": ["ok"],
                }
            ],
            "repo_verification": [
                {"repo": "me/app", "verdict": "matches", "details": "commits exist"}
            ],
        }
    )
    analysis = ResumeAnalysis.model_validate(data)
    assert analysis.rewrite_examples[0].after == "new"
    assert analysis.section_reviews[0].section == "Projects"
    assert analysis.project_cards[0].name == "P"
    assert analysis.skill_trust is not None
    assert analysis.skill_trust.solid == ["Python"]
    assert analysis.career_analysis is not None
    assert analysis.company_fit[0].tier == "startup"
    assert analysis.repo_evidence[0].repo == "me/app"
    assert analysis.repo_evidence[0].stars == 4
    assert analysis.repo_verification[0].verdict == "matches"


def test_normalize_skips_dimension_without_numeric_score():
    data = normalize_resume_analysis_payload(
        {
            "dimension_scores": {
                "role_fit": {"comment": "no score yet"},
                "tech_depth": {"score": 80, "comment": "clear"},
            }
        }
    )
    assert "role_fit" not in data["dimension_scores"]
    assert data["dimension_scores"]["tech_depth"]["score"] == 80


def test_compute_score_from_dims_mean():
    from realmock.domains.resume.schemas.analysis import DimensionScore
    from realmock.domains.resume.services.analysis_normalize import compute_score_from_dims

    dims = {
        "a": DimensionScore(score=40, comment=""),
        "b": DimensionScore(score=60, comment=""),
    }
    assert compute_score_from_dims(dims) == 50
    assert compute_score_from_dims({}) is None


def test_compute_score_from_dims_weighted(monkeypatch) -> None:
    from realmock.domains.resume.schemas.analysis import DimensionScore
    from realmock.domains.resume.services import analysis_normalize

    monkeypatch.setattr(analysis_normalize, "DIMENSION_WEIGHTS", {"a": 3.0, "b": 1.0})
    dims = {
        "a": DimensionScore(score=40, comment=""),
        "b": DimensionScore(score=60, comment=""),
    }
    assert analysis_normalize.compute_score_from_dims(dims) == 45


def test_score_band_label_boundaries() -> None:
    from realmock.domains.resume.schemas.limits import score_band_label

    assert score_band_label(85) == "突出"
    assert score_band_label(84) == "扎实"
    assert score_band_label(70) == "扎实"
    assert score_band_label(69) == "参差"
    assert score_band_label(55) == "参差"
    assert score_band_label(54) == "偏弱"
    assert score_band_label(0) == "偏弱"
    assert score_band_label(100) == "突出"
    assert score_band_label(90, locale="en") == "standout"
    assert score_band_label(60, locale="en") == "mixed"


def test_benchmark_percentile_from_score_bounds():
    from realmock.domains.resume.services.analysis_normalize import (
        benchmark_percentile_from_score,
    )

    assert benchmark_percentile_from_score(0) == 8
    assert benchmark_percentile_from_score(100) == 92
    assert benchmark_percentile_from_score(50) == 50
    assert benchmark_percentile_from_score(0) < benchmark_percentile_from_score(50)
    assert benchmark_percentile_from_score(50) < benchmark_percentile_from_score(100)


def test_normalize_non_dict_returns_empty():
    assert normalize_resume_analysis_payload(["nope"]) == {}  # type: ignore[arg-type]


def test_normalize_rewrite_arrow_keeps_latin_before_text():
    """Arrow pairs must not treat ``[before change]`` as a character class."""
    data = normalize_resume_analysis_payload({"rewrite_examples": ["foo -> bar"]})
    assert data["rewrite_examples"] == [{"before": "foo", "after": "bar"}]


def test_normalize_rewrite_strips_before_label_on_arrow():
    data = normalize_resume_analysis_payload(
        {"rewrite_examples": ["before: old -> new"]}
    )
    assert data["rewrite_examples"] == [{"before": "old", "after": "new"}]


def test_normalize_keeps_explicit_zero_score():
    """An explicit 0 must not be overwritten by leftover alias totals."""
    data = normalize_resume_analysis_payload({"score": 0, "overall_score": 72})
    assert data["score"] == 0


def test_normalize_salvages_overall_score_when_score_missing():
    data = normalize_resume_analysis_payload({"overall_score": 72})
    assert data["score"] == 72


def test_normalize_accepts_dimension_score_list():
    data = normalize_resume_analysis_payload(
        {
            "dimension_scores": [
                {"dimension": "tech_depth", "score": 81, "comment": "ok"},
            ]
        }
    )
    assert data["dimension_scores"]["tech_depth"]["score"] == 81


def test_clamp_score_bounds():
    from realmock.domains.resume.services.analysis_normalize import _clamp_score

    assert _clamp_score(-5) == 0
    assert _clamp_score(0) == 0
    assert _clamp_score(72) == 72
    assert _clamp_score(100) == 100
    assert _clamp_score(101) == 100


def test_normalize_rewrite_dict_with_alias_keys():
    data = normalize_resume_analysis_payload(
        {"rewrite_examples": [{"Before the change": "a", "After modification": "b"}]}
    )
    assert data["rewrite_examples"] == [{"before": "a", "after": "b"}]


def test_normalize_rewrite_json_string():
    data = normalize_resume_analysis_payload(
        {"rewrite_examples": ['{"before": "a", "after": "b"}']}
    )
    assert data["rewrite_examples"] == [{"before": "a", "after": "b"}]


def test_normalize_rewrite_keyed_fallback_on_trailing_junk():
    """Unparseable-as-dict but key-shaped text falls back to the key regex."""
    data = normalize_resume_analysis_payload(
        {"rewrite_examples": ['{"before": "a", "after": "b"} trailing junk']}
    )
    assert data["rewrite_examples"] == [{"before": "a", "after": "b"}]


def test_normalize_rewrite_labeled_markers():
    data = normalize_resume_analysis_payload(
        {"rewrite_examples": ["改前：做了X after: did Y"]}
    )
    assert data["rewrite_examples"] == [{"before": "做了X", "after": "did Y"}]


def test_normalize_rewrite_strips_heading_markers():
    data = normalize_resume_analysis_payload(
        {"rewrite_examples": ["### Old -> New"]}
    )
    assert data["rewrite_examples"] == [{"before": "Old", "after": "New"}]


def test_normalize_rewrite_drops_unmatched_text():
    data = normalize_resume_analysis_payload(
        {"rewrite_examples": ["just some text"]}
    )
    assert data["rewrite_examples"] == []


def test_normalize_interviewer_comments_even_count():
    data = normalize_resume_analysis_payload(
        {"interviewer_comments": ["a", "b", "c", "d", "e"]}
    )
    assert data["interviewer_comments"] == ["a", "b", "c", "d"]
    data = normalize_resume_analysis_payload(
        {"interviewer_comments": ["a", "", "b", "c", "d", "e", "f", "g", "h", "i"]}
    )
    assert data["interviewer_comments"] == ["a", "b", "c", "d", "e", "f", "g", "h"]
    # Fewer than 4 are kept as-is: never invent or destroy evidence.
    data = normalize_resume_analysis_payload({"interviewer_comments": ["a", "b", "c"]})
    assert data["interviewer_comments"] == ["a", "b", "c"]
    data = normalize_resume_analysis_payload({"interviewer_comments": "nope"})
    assert data["interviewer_comments"] == []


def test_normalize_improvement_suggestions_dict_shapes():
    data = normalize_resume_analysis_payload(
        {
            "improvement_suggestions": [
                {
                    "location": "顶部个人信息区",
                    "current": "仅有姓名",
                    "suggested": "新增目标岗位",
                    "effect": "让HR第一眼锁定方向",
                },
                "{'location': '技能区', 'current': '三列平铺', 'suggested': '改为两列', 'effect': '降低堆砌感'}",
                "plain readable suggestion",
                42,
            ]
        }
    )
    items = data["improvement_suggestions"]
    assert items[0] == "【顶部个人信息区】仅有姓名 → 新增目标岗位（让HR第一眼锁定方向）"
    assert items[1] == "【技能区】三列平铺 → 改为两列（降低堆砌感）"
    assert items[2] == "plain readable suggestion"
    assert items[3] == "42"
    assert all("{'location'" not in item for item in items)


def test_normalize_improvement_suggestions_non_list():
    assert normalize_resume_analysis_payload({"improvement_suggestions": "nope"})[
        "improvement_suggestions"
    ] == []


def test_normalize_dimension_weights_clamped_to_range():
    from realmock.domains.resume.schemas.limits import (
        DIMENSION_WEIGHTS,
        dimension_weight_range,
    )
    from realmock.domains.resume.services.analysis_normalize import (
        _normalize_dimension_weights,
    )

    low, high = dimension_weight_range("role_fit")
    weights = _normalize_dimension_weights(
        {
            "role_fit": high + 100.0,
            "typography": -5.0,
            "not_a_dimension": 9.0,
            "tech_depth": "11",
            "credibility": float("nan"),
        }
    )
    assert weights["role_fit"] == high
    assert weights["typography"] == dimension_weight_range("typography")[0]
    assert "not_a_dimension" not in weights
    assert weights["tech_depth"] == 11.0
    assert weights["credibility"] == DIMENSION_WEIGHTS["credibility"]
    assert set(weights) == set(DIMENSION_WEIGHTS)


def test_normalize_dimension_weights_missing_block_falls_back_to_base():
    from realmock.domains.resume.schemas.limits import DIMENSION_WEIGHTS
    from realmock.domains.resume.services.analysis_normalize import (
        _normalize_dimension_weights,
    )

    assert _normalize_dimension_weights(None) == DIMENSION_WEIGHTS
    assert _normalize_dimension_weights({}) == DIMENSION_WEIGHTS
    data = normalize_resume_analysis_payload({"dimension_scores": {}})
    assert data["dimension_weights"] == DIMENSION_WEIGHTS


def test_compute_score_uses_validated_weights():
    from realmock.domains.resume.schemas.analysis import DimensionScore
    from realmock.domains.resume.services.analysis_normalize import (
        compute_score_from_dims,
    )

    dims = {
        "role_fit": DimensionScore(score=100, comment=""),
        "typography": DimensionScore(score=0, comment=""),
    }
    assert compute_score_from_dims(dims, {"role_fit": 18.0, "typography": 2.0}) == 90
    assert compute_score_from_dims(dims, {"role_fit": 6.0, "typography": 6.0}) == 50


def test_normalize_deep_questions_and_repo_and_suggestion() -> None:
    from realmock.domains.resume.services import analysis_normalize as mod

    assert mod._normalize_deep_questions("bad") == []
    out = mod._normalize_deep_questions(
        [{"question": "  "}, {"question": "What is cache?", "intent": "probe"}]
    )
    assert len(out) == 1 and out[0]["question"] == "What is cache?"
    assert mod._normalize_repo_evidence([{"repo": "a", "stars": "x"}]) is not None
    assert mod._normalize_repo_evidence(["bad", {"repo": "r"}])[0]["repo"] == "r"
    assert mod._format_structured_suggestion({"current": "old"}) == "old"
    assert mod._format_structured_suggestion({}) is None


def test_normalize_rewrite_variants() -> None:
    from realmock.domains.resume.services.analysis_normalize import (
        _arrow_rewrite_pair,
        _keyed_rewrite_pair,
        _labeled_rewrite_pair,
        _loads_rewrite_dict,
        _normalize_rewrite_examples,
        _strip_heading_markers,
    )

    assert _loads_rewrite_dict('{"before":"a","after":"b"}') == {"before": "a", "after": "b"}
    assert _loads_rewrite_dict("{'before': 'a', 'after': 'b'}") == {"before": "a", "after": "b"}
    assert _loads_rewrite_dict("not-a-dict") is None
    assert _loads_rewrite_dict("[1,2]") is None
    assert _keyed_rewrite_pair("{'before': 'x', 'after': 'y'}") == ("x", "y")
    assert _keyed_rewrite_pair("nothing") == ("", "")
    assert _labeled_rewrite_pair("before: old after: new") == ("old", "new")
    assert _labeled_rewrite_pair("nothing") == ("", "")
    assert _arrow_rewrite_pair("old -> new") == ("old", "new")
    assert _arrow_rewrite_pair("[before] old => [after] new") == ("old", "new")
    assert _arrow_rewrite_pair("no-arrow") == ("", "")
    assert _strip_heading_markers("### title") == "title"

    out = _normalize_rewrite_examples("not-a-list")
    assert out == []
    out2 = _normalize_rewrite_examples([
        {"before": "### a", "after": "b"},
        '{"before": "x", "after": "y"}',
        "{'before': 'p', 'after': 'q'}",
        "before: m after: n",
        "m -> n",
        {"before": "", "after": ""},
        "dangling",
    ])
    assert {"before": "a", "after": "b"} in out2
    assert len(out2) >= 4


def test_normalize_scores_dims_and_weights() -> None:
    from realmock.domains.resume.services.analysis_normalize import (
        _coerce_dimension_map,
        _coerce_int_score,
        _normalize_dimension_weights,
        _norm_score,
        _pick_overall_score,
        benchmark_percentile_from_score,
        compute_score_from_dims,
    )
    from realmock.domains.resume.schemas.limits import DIMENSION_WEIGHTS

    assert _coerce_int_score("88.7") == 88
    assert _coerce_int_score("abc") is None
    assert _norm_score("abc") == 0
    assert _pick_overall_score({"score": 0, "overall_score": 90}) == 0
    assert _pick_overall_score({"overall_score": "77"}) == 77
    assert _pick_overall_score({}) == 0
    assert _pick_overall_score({"score": 150}) == 100
    assert _coerce_dimension_map({"a": 1}) == {"a": 1}
    assert _coerce_dimension_map([{"key": "k", "score": 1}, "bad", {}]) == {"k": {"key": "k", "score": 1}}
    assert _coerce_dimension_map("bad") == {}
    w = _normalize_dimension_weights({"unknown_dim": 9, "tech_depth": "bad", "tech_depth2": 1})
    assert w == DIMENSION_WEIGHTS
    w2 = _normalize_dimension_weights({"tech_depth": float("inf")})
    assert w2["tech_depth"] == DIMENSION_WEIGHTS["tech_depth"]
    w3 = _normalize_dimension_weights({"tech_depth": 999})
    assert w3["tech_depth"] <= max(v for v in w3.values())
    assert _normalize_dimension_weights("bad") == DIMENSION_WEIGHTS
    assert benchmark_percentile_from_score(0) < benchmark_percentile_from_score(100)
    assert compute_score_from_dims({}) is None
    assert compute_score_from_dims({"a": SimpleNamespace(score=None)}) is None
    assert compute_score_from_dims({"a": SimpleNamespace(score=80)}, weights={"a": 0}) is None
    assert compute_score_from_dims({"a": SimpleNamespace(score=80), "b": SimpleNamespace(score=60)}) == 70


def test_normalize_nested_blobs() -> None:
    from realmock.domains.resume.services.analysis_normalize import normalize_resume_analysis_payload

    data = normalize_resume_analysis_payload(
        {
            "score": 80,
            "dimension_scores": {
                "tech_depth": {"comment": "no-score"},
                "role_fit": {"score": "bad"},
                "k2": {"score": 90, "comment": "ok"},
                "k3": 70,
            },
            "section_reviews": [{"section": "exp", "score": "90", "verdict": "v", "detail": "d"}, "bad"],
            "project_cards": [{"name": "p", "score": 80, "deep_questions": ["why?"]}, "bad"],
            "skill_trust": {"solid": ["Python"], "claimed": [], "missing": []},
            "career_analysis": {"trajectory": "up", "stability_score": 80, "gaps": ["g"], "notes": "n"},
            "company_fit": [{"tier": "t", "fit_score": 80, "reason": "r"}, "bad"],
            "repo_evidence": [{"repo": "o/r", "stars": "10", "forks": "x"}],
            "repo_verification": [{"repo": "o/r", "verdict": "ok", "details": "d"}, "bad"],
            "interview_qa": [{"question": "q?", "intent": "i", "answer_points": ["a"], "follow_ups": ["f"]}, {"no": "q"}, "bad"],
            "improvement_suggestions": [{"location": "exp", "current": "a", "suggested": "b", "effect": "e"}, "{'location': 'x', 'current': 'a', 'suggested': 'b', 'effect': 'e'}", "plain", {}, ""],
            "interviewer_comments": ["a", "b", "c", "d", "e"],
            "dimension_weights": {"tech_depth": 1.5},
        },
        locale="en",
    )
    assert data["dimension_scores"]["k2"]["score"] == 90
    assert "tech_depth" not in data["dimension_scores"]
    assert data["skill_trust"]["solid"] == ["Python"]
    assert data["career_analysis"]["trajectory"] == "up"
    assert data["repo_evidence"][0]["stars"] == 10
    assert len(data["interviewer_comments"]) == 4
    assert any("exp" in s for s in data["improvement_suggestions"])

    assert normalize_resume_analysis_payload("bad") == {}
    zh = normalize_resume_analysis_payload({"score": 10, "headline": "，hello"}, locale="zh-CN")
    assert zh["score"] == 10
    empty_trust = normalize_resume_analysis_payload({"score": 1, "skill_trust": {"solid": [], "claimed": [], "missing": []}})
    assert empty_trust["skill_trust"] is None
    empty_career = normalize_resume_analysis_payload({"score": 1, "career_analysis": {"trajectory": "", "gaps": []}})
    assert empty_career["career_analysis"] is None
    assert normalize_resume_analysis_payload({"score": 1, "skill_trust": "bad"})["skill_trust"] is None
    assert normalize_resume_analysis_payload({"score": 1, "career_analysis": "bad"})["career_analysis"] is None
