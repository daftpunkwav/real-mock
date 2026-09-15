"""Score contract tests for realmock.platform.contracts.session_score.

Covers: noop projection defaults and register/apply delegation.
Conventions: in-memory fakes only; global projection restored after test.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestSessionScoreContract:
    def test_score_noop_and_wrapper(self) -> None:
        from realmock.platform.contracts.session_score import (
            _NoopScoreProjection,
            apply_session_overall_score,
            get_session_score_projection,
            register_session_score_projection,
        )

        _NoopScoreProjection().apply_overall_score(MagicMock(), 1, 90)
        prev = get_session_score_projection()
        seen = []

        class _P:
            def apply_overall_score(self, db, sid, score):
                seen.append((sid, score))

        register_session_score_projection(_P())
        apply_session_overall_score(MagicMock(), 7, 88)
        assert seen == [(7, 88)]
        register_session_score_projection(prev)
