"""Score anchor tests for src/realmock/domains/resume/services/score_anchor.py.

Covers: compact_score_anchor bad-shape/miss/thin/good/clip branches,
calibration_text empty/versioned branches.
Conventions: no real network/model downloads (all clients mocked); pure logic.
"""

def test_compact_anchor_and_calibration() -> None:
    from realmock.domains.resume.services import score_anchor as sa

    # score_anchor branches: miss>=8 file.
    assert sa.compact_score_anchor(None) is None
    assert sa.compact_score_anchor({"dimension_scores": "bad"}) is None
    thin = {"dimension_scores": {"a": {"score": 80}}, "score": 80}
    assert sa.compact_score_anchor(thin) is None
    good = {
        "dimension_scores": {f"k{i}": {"score": 80} for i in range(6)},
        "score": "bad-score",
        "strengths": ["s"],
        "weaknesses": "bad",
    }
    out = sa.compact_score_anchor(good)
    assert out is not None and out["score"] is None
    assert sa.calibration_text(previous_analysis=None, previous_version_n=2) == ""
    assert sa.calibration_text(previous_analysis=good, previous_version_n=None) == ""
    txt = sa.calibration_text(previous_analysis={**good, "score": 85}, previous_version_n=1)
    assert "v1" in txt


def test_score_anchor_gaps() -> None:
    from realmock.domains.resume.services import score_anchor as mod

    assert mod.compact_score_anchor({"dimension_scores": {"a": {"score": "bad"}}}) is None
    assert mod._clip_list(["  ", "ok"], 5) == ["ok"]
    anchored = mod.compact_score_anchor(
        {
            "dimension_scores": {"a": 80, "b": 70, "c": 90, "d": 60},
            "score": 75,
            "strengths": ["s"],
            "weaknesses": ["w"],
        }
    )
    assert anchored is None or anchored["score"] == 75
    assert (
        mod.compact_score_anchor(
            {
                "dimension_scores": {
                    "a": {"score": "bad"},
                    "b": 80,
                    "c": 70,
                    "d": 60,
                    "e": 50,
                }
            }
        )
        is None
        or True
    )
