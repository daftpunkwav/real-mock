"""CSRF tests for realmock.platform.core.session_auth.csrf.

Covers: origin/referer allow-list matching, malformed referer handling,
  and cookie-only POST enforcement branches.
Conventions: synthetic Starlette requests; settings stubbed via monkeypatch.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _http_req(headers=None, method="POST", cookies=None, path="/x"):
    from starlette.requests import Request

    raw = []
    if cookies:
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw.append((b"cookie", cookie_header.encode()))
    for k, v in (headers or {}).items():
        raw.append((k.lower().encode(), v.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": raw,
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
    }
    return Request(scope)


class TestCsrf:
    def test_origin_allowed_empty(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import csrf as m

        monkeypatch.setattr(m, "get_settings", lambda: SimpleNamespace(cors_origin_list=[]))
        assert m._origin_allowed(_http_req(headers={"origin": "http://x"})) is False

    def test_origin_hit(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import csrf as m

        monkeypatch.setattr(m, "get_settings", lambda: SimpleNamespace(cors_origin_list=["http://localhost:8080"]))
        assert m._origin_allowed(_http_req(headers={"origin": "http://localhost:8080"})) is True
        assert m._origin_allowed(_http_req(headers={"referer": "http://localhost:8080/some/page"})) is True

    def test_referer_parse_fail(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import csrf as m

        monkeypatch.setattr(m, "get_settings", lambda: SimpleNamespace(cors_origin_list=["http://localhost:8080"]))
        assert m._origin_allowed(_http_req(headers={"referer": "http://%zz"})) is False
        assert m._origin_allowed(_http_req()) is False

    def test_assert_branches(self, monkeypatch) -> None:
        from realmock.platform.core.errors import ApiBusinessError
        from realmock.platform.core.session_auth.csrf import assert_csrf_if_cookie_only

        assert_csrf_if_cookie_only(_http_req(), used_header=True)
        assert_csrf_if_cookie_only(_http_req(method="GET"), used_header=False)
        monkeypatch.setattr("realmock.platform.core.session_auth.csrf.get_settings", lambda: SimpleNamespace(cors_origin_list=[]))
        with pytest.raises(ApiBusinessError):
            assert_csrf_if_cookie_only(_http_req(method="POST"), used_header=False)
