"""Token tests for realmock.platform.core.session_auth.tokens.

Covers: token generation/matching edge cases and session assertion.
Conventions: pure unit tests; no I/O or network.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


class TestTokens:
    def test_new_and_match(self) -> None:
        from realmock.platform.core.session_auth.tokens import new_access_token, tokens_match

        t = new_access_token()
        assert tokens_match(t, t) is True
        assert tokens_match("", t) is False
        assert tokens_match(t, "") is False
        assert tokens_match("abc", "xyz1") is False
        assert tokens_match("abc", "abc") is True

    def test_assert_token(self) -> None:
        from realmock.platform.core.errors import ApiBusinessError
        from realmock.platform.core.session_auth.tokens import assert_session_token

        assert_session_token(SimpleNamespace(access_token="k"), "k")
        with pytest.raises(ApiBusinessError):
            assert_session_token(SimpleNamespace(access_token="k"), "wrong")
