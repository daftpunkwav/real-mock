"""Local-only guard tests for realmock.platform.core.local_only.

Covers: loopback enforcement, cross-site fetch rejection, and
  websocket origin guard branches.
Conventions: synthetic requests/sockets; TEST_MODE bypass neutralized.
"""

from __future__ import annotations

import pytest

from realmock.platform.core.errors import ApiBusinessError


def _req(host="127.0.0.1", headers=None):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers or [],
        "client": (host, 1234) if host else None,
        "server": ("test", 80),
    }
    return Request(scope)


class TestLocalOnly:
    def test_none_request_passes(self) -> None:
        from realmock.platform.core.local_only import reject_cross_site_fetch, require_local_peer

        require_local_peer(None)
        reject_cross_site_fetch(None)

    def test_testclient_peer_passes(self) -> None:
        from realmock.platform.core.local_only import require_local_peer

        require_local_peer(_req(host="testclient"))

    def test_empty_peer_rejected(self) -> None:
        from realmock.platform.core.local_only import require_local_peer

        with pytest.raises(ApiBusinessError):
            require_local_peer(_req(host=None))

    def test_invalid_ip_rejected(self, monkeypatch) -> None:
        import os

        from realmock.platform.core.local_only import require_local_peer

        monkeypatch.setenv("TEST_MODE", "0")

        class _C:
            host = "not-an-ip"

        class _R:
            client = _C()
            headers = {}

        with pytest.raises(ApiBusinessError):
            require_local_peer(_R())
        assert os.environ.get("TEST_MODE") == "0"

    def test_non_loopback_rejected(self) -> None:
        import os

        from realmock.platform.core.local_only import require_local_peer

        # ensure TEST_MODE bypass does not hide the check
        old = os.environ.get("TEST_MODE")
        os.environ["TEST_MODE"] = "0"
        try:
            with pytest.raises(ApiBusinessError):
                require_local_peer(_req(host="8.8.8.8"))
        finally:
            if old is None:
                del os.environ["TEST_MODE"]
            else:
                os.environ["TEST_MODE"] = old

    def test_loopback_passes(self) -> None:
        from realmock.platform.core.local_only import require_local_peer

        require_local_peer(_req(host="127.0.0.1"))

    def test_reject_cross_site(self) -> None:
        from realmock.platform.core.local_only import reject_cross_site_fetch

        with pytest.raises(ApiBusinessError):
            reject_cross_site_fetch(_req(host="127.0.0.1", headers=[(b"sec-fetch-site", b"cross-site")]))
        reject_cross_site_fetch(_req(host="127.0.0.1"))

    def test_local_api_deps_registered(self) -> None:
        from realmock.platform.core.local_only import LOCAL_API_DEPENDENCIES

        assert len(LOCAL_API_DEPENDENCIES) == 2

    @pytest.mark.asyncio
    async def test_guard_ws_origin(self) -> None:
        from realmock.platform.core.local_only import _close_ws_forbidden, guard_ws_origin
        from starlette.websockets import WebSocketState

        class _WS:
            def __init__(self, origin="", state=WebSocketState.CONNECTING):
                self.headers = {"origin": origin} if origin else {}
                self.client_state = state
                self.closed = None

            async def close(self, code=None):
                self.closed = code

        assert await guard_ws_origin(_WS(origin="")) is True
        assert await guard_ws_origin(_WS(origin="http://localhost:8080")) is True
        assert await guard_ws_origin(_WS(origin="http://127.0.0.1:8080")) is True
        assert await guard_ws_origin(_WS(origin="http://[::1]:8080")) is True
        ws = _WS(origin="https://evil.example.com")
        assert await guard_ws_origin(ws) is False
        assert ws.closed == 1008
        ws2 = _WS(origin="https://evil.example.com", state=WebSocketState.CONNECTED)
        assert await guard_ws_origin(ws2) is False
        # direct close helper both states
        await _close_ws_forbidden(_WS(origin="", state=WebSocketState.CONNECTING))
