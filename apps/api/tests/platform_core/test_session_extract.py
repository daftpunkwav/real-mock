"""Extract tests for realmock.platform.core.session_auth.extract.

Covers: header-vs-cookie-vs-query precedence, CSRF enforcement on
  cookie/query paths, prod query stripping, and websocket token parsing.
Conventions: synthetic HTTP/WS requests; settings stubbed via monkeypatch.
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


class TestExtract:
    def test_header_wins(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import extract as ex

        monkeypatch.setattr(ex, "get_settings", lambda: SimpleNamespace(is_prod=False))
        req = _http_req(cookies={"iv_1": "cookie-tok"})
        assert ex._extract_from_request(req, scope="iv", session_id=1, x_interview_token="header-tok", token="q") == "header-tok"

    def test_cookie_requires_csrf(self, monkeypatch) -> None:
        from realmock.platform.core.errors import ApiBusinessError
        from realmock.platform.core.session_auth import extract as ex

        monkeypatch.setattr(ex, "get_settings", lambda: SimpleNamespace(is_prod=False, cors_origin_list=[]))
        req = _http_req(cookies={"iv_1": "c"})
        with pytest.raises(ApiBusinessError):
            ex._extract_from_request(req, scope="iv", session_id=1, x_interview_token=None, token=None)

    def test_query_only_requires_csrf(self, monkeypatch) -> None:
        from realmock.platform.core.errors import ApiBusinessError
        from realmock.platform.core.session_auth import extract as ex

        monkeypatch.setattr(ex, "get_settings", lambda: SimpleNamespace(is_prod=False, cors_origin_list=[]))
        req = _http_req()
        with pytest.raises(ApiBusinessError):
            ex._extract_from_request(req, scope="iv", session_id=1, x_interview_token=None, token="q")

    def test_prod_strips_query(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import extract as ex

        monkeypatch.setattr(ex, "get_settings", lambda: SimpleNamespace(is_prod=True))
        req = _http_req()
        assert ex._extract_from_request(req, scope="iv", session_id=1, x_interview_token=None, token="q") is None

    def test_wrappers(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import extract as ex

        monkeypatch.setattr(ex, "get_settings", lambda: SimpleNamespace(is_prod=False))
        req = _http_req(cookies={"iv_2": "c2"})
        # cookie path triggers csrf (empty allowlist) -> patch csrf to pass
        monkeypatch.setattr(ex, "assert_csrf_if_cookie_only", lambda *a, **k: None)
        assert ex.extract_token(2, req, x_interview_token=None, token=None) == "c2"
        req2 = _http_req(cookies={"prep_3": "p3"})
        assert ex.extract_prep_token(3, req2, x_interview_token=None, token=None) == "p3"

    def test_ws_subprotocol(self) -> None:
        from realmock.platform.core.session_auth.extract import ws_token_subprotocol

        assert ws_token_subprotocol("abc") == "mock.abc"

    def test_extract_ws_token(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import extract as ex

        class _WS:
            def __init__(self, cookies=None, proto=""):
                self.cookies = cookies or {}
                self.headers = {"sec-websocket-protocol": proto} if proto else {}

        tok, sub = ex.extract_ws_token(_WS(cookies={"iv_1": "ck"}), session_id=1)
        assert (tok, sub) == ("ck", None)
        tok2, sub2 = ex.extract_ws_token(_WS(proto="mock.abc123, other"), session_id=None)
        assert (tok2, sub2) == ("abc123", "mock.abc123")
        # blank subprotocol parts skipped
        tok3, _ = ex.extract_ws_token(_WS(proto=" , mock.xyz "), session_id=None)
        assert tok3 == "xyz"
        # empty subprotocol token skipped -> falls to query
        monkeypatch.setattr(ex, "get_settings", lambda: SimpleNamespace(is_prod=False))
        tok4, _ = ex.extract_ws_token(_WS(proto="mock.  "), session_id=None, query_token="q1")
        assert tok4 == "q1"
        # prod rejects query
        monkeypatch.setattr(ex, "get_settings", lambda: SimpleNamespace(is_prod=True))
        tok5, sub5 = ex.extract_ws_token(_WS(), session_id=None, query_token="q1")
        assert (tok5, sub5) == ("", None)
