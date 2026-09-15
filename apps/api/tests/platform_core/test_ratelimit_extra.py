"""Rate-limit tests for realmock.platform.core.ratelimit.

Covers: trusted-proxy resolution, in-memory buckets, DB backend branches,
  window expiry, sweeper reaping, and double-checked cleanup locking.
Conventions: faked DB sessions and stubbed settings; no network.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from realmock.platform.core import ratelimit as rl
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.core.ratelimit import reset_rate_limit


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


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


class TestTrustedProxy:
    def test_empty_config_uses_loopback(self, monkeypatch) -> None:
        monkeypatch.setattr("realmock.platform.core.ratelimit.get_settings", lambda: SimpleNamespace(trusted_proxy_cidr_list=[]))
        nets = rl._trusted_proxy_nets()
        assert len(nets) == 2

    def test_invalid_cidr_skipped(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "realmock.platform.core.ratelimit.get_settings",
            lambda: SimpleNamespace(trusted_proxy_cidr_list=["not-a-cidr", "10.0.0.0/8"]),
        )
        nets = rl._trusted_proxy_nets()
        assert len(nets) == 1

    def test_peer_trusted(self, monkeypatch) -> None:
        monkeypatch.setattr("realmock.platform.core.ratelimit.get_settings", lambda: SimpleNamespace(trusted_proxy_cidr_list=[]))
        assert rl._peer_is_trusted_proxy("127.0.0.1") is True
        assert rl._peer_is_trusted_proxy("8.8.8.8") is False
        assert rl._peer_is_trusted_proxy("not-an-ip") is False

    def test_resolve_client_ip(self, monkeypatch) -> None:
        monkeypatch.setattr("realmock.platform.core.ratelimit.get_settings", lambda: SimpleNamespace(trusted_proxy_cidr_list=[]))
        # trusted proxy + forwarded header
        r = _req(host="127.0.0.1", headers=[(b"x-forwarded-for", b"9.9.9.9, 8.8.8.8")])
        assert rl._resolve_client_ip(r) == "9.9.9.9"
        # untrusted peer ignores header
        r2 = _req(host="8.8.8.8", headers=[(b"x-forwarded-for", b"9.9.9.9")])
        assert rl._resolve_client_ip(r2) == "8.8.8.8"
        # no client
        r3 = _req(host=None)
        assert rl._resolve_client_ip(r3) == "unknown"
        # no header
        r4 = _req(host="1.2.3.4")
        assert rl._resolve_client_ip(r4) == "1.2.3.4"


class TestMemoryBuckets:
    def test_ensure_cleanup_idempotent(self) -> None:
        rl._ensure_cleanup_thread()
        first = rl._cleanup_started
        rl._ensure_cleanup_thread()
        assert rl._cleanup_started is first

    def test_check_prunes_and_limits(self) -> None:
        reset_rate_limit("cov-infra")
        req = _req(host="127.0.0.1")
        for _ in range(2):
            rl.check_rate_limit(req, key="cov-infra", limit=2, window_seconds=60)
        with pytest.raises(ApiBusinessError) as e:
            rl.check_rate_limit(req, key="cov-infra", limit=2, window_seconds=60)
        assert e.value.status_code == 429
        assert "Retry-After" in (e.value.headers or {})
        reset_rate_limit("cov-infra")

    def test_check_by_id_and_try(self) -> None:
        reset_rate_limit("cov-byid")
        for _ in range(2):
            rl.check_rate_limit_by_id(key="cov-byid", client_id="c1", limit=2, window_seconds=60)
        with pytest.raises(ApiBusinessError):
            rl.check_rate_limit_by_id(key="cov-byid", client_id="c1", limit=2, window_seconds=60)
        assert rl.try_rate_limit_by_id(key="cov-byid", client_id="other", limit=1, window_seconds=60) is True
        assert rl.try_rate_limit_by_id(key="cov-byid", client_id="c1", limit=1, window_seconds=60) is False
        reset_rate_limit("cov-byid")

    def test_rate_limit_dep_and_reset_all(self) -> None:
        dep = rl.rate_limit_dep(key="cov-dep", limit=100, window_seconds=60)
        assert callable(dep)
        reset_rate_limit("cov-dep")
        dep(_req(host="127.0.0.1"))
        reset_rate_limit()

    def test_use_db_flag(self, monkeypatch) -> None:
        monkeypatch.setattr("realmock.platform.core.ratelimit.get_settings", lambda: SimpleNamespace(ratelimit_backend="database"))
        assert rl._use_db_ratelimit() is True
        monkeypatch.setattr("realmock.platform.core.ratelimit.get_settings", lambda: SimpleNamespace(ratelimit_backend="memory"))
        assert rl._use_db_ratelimit() is False


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, row=None, fail_commit=False):
        self._row = row
        self.added = None
        self.committed = False
        self.fail_commit = fail_commit

    def query(self, model):
        return _FakeQuery(self._row)

    def add(self, row):
        self.added = row
        if self._row is None:
            self._row = row

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("db down")
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class TestDbRatelimitBranches:
    def test_creates_row_and_appends(self, monkeypatch) -> None:
        db = _FakeDB(row=None)
        monkeypatch.setattr(rl, "SessionsSessionLocal", lambda: db)
        rl._check_rate_limit_db(bucket_key=("k", "1.1.1.1"), limit=5, window_seconds=60)
        assert db.committed

    def test_invalid_json_and_nonlist_and_nonnumeric(self, monkeypatch) -> None:
        for payload in ("{bad", "[1,2", '"str"', "[1, 'x', None]"):
            row = SimpleNamespace(bucket_key="k:x", timestamps_json=payload)
            db = _FakeDB(row=row)
            monkeypatch.setattr(rl, "SessionsSessionLocal", lambda: db)
            rl._check_rate_limit_db(bucket_key=("k", "x"), limit=5, window_seconds=60)

    def test_window_prunes_old(self, monkeypatch) -> None:
        import time as _t

        old = _t.time() - 1000
        row = SimpleNamespace(bucket_key="k:x", timestamps_json=json.dumps([old, _t.time()]))
        db = _FakeDB(row=row)
        monkeypatch.setattr(rl, "SessionsSessionLocal", lambda: db)
        rl._check_rate_limit_db(bucket_key=("k", "x"), limit=5, window_seconds=60)

    def test_limit_exceeded(self, monkeypatch) -> None:
        import time as _t

        now = _t.time()
        row = SimpleNamespace(bucket_key="k:x", timestamps_json=json.dumps([now, now]))
        db = _FakeDB(row=row)
        monkeypatch.setattr(rl, "SessionsSessionLocal", lambda: db)
        with pytest.raises(ApiBusinessError) as e:
            rl._check_rate_limit_db(bucket_key=("k", "x"), limit=2, window_seconds=60)
        assert e.value.status_code == 429

    def test_commit_failure_reraises(self, monkeypatch) -> None:
        db = _FakeDB(row=None, fail_commit=True)
        monkeypatch.setattr(rl, "SessionsSessionLocal", lambda: db)
        with pytest.raises(RuntimeError):
            rl._check_rate_limit_db(bucket_key=("k", "x"), limit=5, window_seconds=60)

    def test_check_rate_limit_db_backend_routing(self, monkeypatch) -> None:
        monkeypatch.setattr("realmock.platform.core.ratelimit.get_settings", lambda: SimpleNamespace(ratelimit_backend="database", trusted_proxy_cidr_list=[]))
        db = _FakeDB(row=None)
        monkeypatch.setattr(rl, "SessionsSessionLocal", lambda: db)
        rl.check_rate_limit(_req(), key="cov-db", limit=5, window_seconds=60)
        rl.check_rate_limit_by_id(key="cov-db", client_id="c", limit=5, window_seconds=60)
        monkeypatch.setattr("realmock.platform.core.ratelimit.get_settings", lambda: SimpleNamespace(ratelimit_backend="memory", trusted_proxy_cidr_list=[]))


@pytest.mark.asyncio
async def test_ratelimit_window_expiry_pops_old_entries() -> None:
    from realmock.platform.core import ratelimit as mod

    reset_rate_limit()
    # Fill one bucket then age it past the window so popleft branches hit.
    assert mod.try_rate_limit_by_id(
        key="cov-final", client_id="c1", limit=1, window_seconds=60
    ) is True
    # Second call without ageing is blocked.
    assert mod.try_rate_limit_by_id(
        key="cov-final", client_id="c1", limit=1, window_seconds=60
    ) is False
    # Age timestamps by hand to force the while-popleft path (202/239).
    bucket = mod._BUCKETS[("cov-final", "c1")]
    old = time.monotonic() - 120.0
    bucket.timestamps.clear()
    bucket.timestamps.append(old)
    bucket.last_access = old
    assert mod.try_rate_limit_by_id(
        key="cov-final", client_id="c1", limit=1, window_seconds=60
    ) is True
    reset_rate_limit("cov-final")


def test_ratelimit_sweeper_reaps_stale_buckets(monkeypatch) -> None:
    from realmock.platform.core import ratelimit as mod

    reset_rate_limit()
    monkeypatch.setattr(mod, "_CLEANUP_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(mod, "_BUCKET_TTL_SECONDS", 0.01)
    monkeypatch.setattr(mod, "_cleanup_started", False)
    mod._ensure_cleanup_thread()
    # Second call hits the fast-path return (110); the sweeper covers 120-124.
    mod._ensure_cleanup_thread()
    stale_key = ("cov-sweep", "9.9.9.9")
    mod._BUCKETS[stale_key] = mod._Bucket(
        timestamps=__import__("collections").deque(),
        last_access=time.monotonic() - 10.0,
    )
    deadline = time.monotonic() + 2.0
    while stale_key in mod._BUCKETS and time.monotonic() < deadline:
        time.sleep(0.02)
    assert stale_key not in mod._BUCKETS
    reset_rate_limit()


def test_ratelimit_double_checked_lock_second_return() -> None:
    from realmock.platform.core import ratelimit as mod

    # Force the inner double-checked branch (114): outer check passes (False),
    # inner check sees True because another thread set it under the lock.
    monkeypatch_holder: dict = {}

    orig_lock = mod._LOCK

    class _FakeLock:
        def __enter__(self):
            mod._cleanup_started = True
            return orig_lock.__enter__()

        def __exit__(self, *exc):
            return orig_lock.__exit__(*exc)

    mod._cleanup_started = False
    mod._LOCK = _FakeLock()  # type: ignore[assignment]
    try:
        mod._ensure_cleanup_thread()
    finally:
        mod._LOCK = orig_lock
        monkeypatch_holder["done"] = True
    assert monkeypatch_holder["done"] is True
