"""Cookie tests for realmock.platform.core.session_auth.cookies.

Covers: cookie naming, secure-flag resolution (explicit/auto/proxy),
  peer trust delegation, and set/clear helpers.
Conventions: synthetic Starlette requests; no network or real cookies.
"""

from __future__ import annotations

from types import SimpleNamespace


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


class TestCookies:
    def test_cookie_name(self) -> None:
        from realmock.platform.core.session_auth.cookies import cookie_name

        assert cookie_name("iv", 7) == "iv_7"
        assert cookie_name("prep", 3) == "prep_3"

    def test_secure_explicit(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import cookies as ck

        monkeypatch.setattr(ck, "get_settings", lambda: SimpleNamespace(cookie_secure=True))
        assert ck.cookie_should_be_secure(_http_req()) is True
        monkeypatch.setattr(ck, "get_settings", lambda: SimpleNamespace(cookie_secure=False))
        assert ck.cookie_should_be_secure(_http_req()) is False

    def test_secure_auto(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import cookies as ck

        monkeypatch.setattr(ck, "get_settings", lambda: SimpleNamespace(cookie_secure=None, trusted_proxy_cidr_list=[]))

        def _https_req():
            from starlette.requests import Request

            scope = {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                "scheme": "https", "path": "/", "raw_path": b"/", "query_string": b"",
                "headers": [], "client": ("127.0.0.1", 1), "server": ("t", 80),
            }
            return Request(scope)

        assert ck.cookie_should_be_secure(_https_req()) is True
        # trusted proxy + forwarded proto
        assert ck.cookie_should_be_secure(_http_req(headers={"x-forwarded-proto": "https"})) is True
        assert ck.cookie_should_be_secure(_http_req()) is False
        # untrusted peer ignores header
        def _untrusted():
            from starlette.requests import Request

            scope = {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
                "scheme": "http", "path": "/", "raw_path": b"/", "query_string": b"",
                "headers": [(b"x-forwarded-proto", b"https")], "client": ("8.8.8.8", 1), "server": ("t", 80),
            }
            return Request(scope)

        assert ck.cookie_should_be_secure(_untrusted()) is False

    def test_peer_trusted_delegates(self, monkeypatch) -> None:
        from realmock.platform.core.session_auth import cookies as ck

        monkeypatch.setattr("realmock.platform.core.ratelimit.get_settings", lambda: SimpleNamespace(trusted_proxy_cidr_list=[]))
        assert ck._peer_is_trusted_proxy("127.0.0.1") is True

    def test_set_and_clear_cookie(self) -> None:
        from fastapi import Response

        from realmock.platform.core.session_auth.cookies import COOKIE_MAX_AGE, clear_session_cookie, set_session_cookie

        resp = Response()
        set_session_cookie(resp, scope="iv", session_id=5, token="tok", secure=False)
        assert "iv_5" in resp.headers.get("set-cookie", "")
        assert COOKIE_MAX_AGE == 90 * 24 * 3600
        resp2 = Response()
        clear_session_cookie(resp2, scope="prep", session_id=9)
        assert "prep_9" in resp2.headers.get("set-cookie", "")
