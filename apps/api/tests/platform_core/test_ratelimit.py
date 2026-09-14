"""Rate-limit unit tests: per-id in-memory window and DB-backed epoch timestamps."""

from __future__ import annotations

from realmock.platform.core.ratelimit import reset_rate_limit, try_rate_limit_by_id


def test_try_rate_limit_by_id_blocks_after_limit():
    reset_rate_limit("llm_test_ws")
    for _ in range(3):
        assert try_rate_limit_by_id(
            key="llm_test_ws", client_id="s1", limit=3, window_seconds=60
        )
    assert not try_rate_limit_by_id(
        key="llm_test_ws", client_id="s1", limit=3, window_seconds=60
    )
    reset_rate_limit("llm_test_ws")


def test_db_ratelimit_uses_epoch_timestamps() -> None:
    """DB rate-limit timestamps must use wall-clock epoch seconds (readable across restarts), not monotonic time."""
    import time as _time

    from realmock.platform.core import ratelimit
    from realmock.platform.core.errors import ApiBusinessError

    stored: dict[str, str] = {}

    class _Row:
        bucket_key = "k:ip"
        timestamps_json = "[]"

    class _Query:
        def filter(self, *a, **kw):
            return self

        def first(self):
            return None

    class _DB:
        def query(self, model):
            return _Query()

        def add(self, row):
            self._row = row

        def commit(self):
            stored["json"] = self._row.timestamps_json

        def rollback(self):
            pass

        def close(self):
            pass

    db = _DB()
    orig_factory = ratelimit.SessionsSessionLocal
    ratelimit.SessionsSessionLocal = lambda: db
    try:
        before = _time.time()
        try:
            ratelimit._check_rate_limit_db(
                bucket_key=("llm", "1.2.3.4"), limit=5, window_seconds=60
            )
        except ApiBusinessError:
            raise AssertionError("The first request should not trigger rate limiting")
        after = _time.time()
    finally:
        ratelimit.SessionsSessionLocal = orig_factory

    stamps = __import__("json").loads(stored["json"])
    assert len(stamps) == 1
    # epoch semantics: the same order of magnitude as wall-clock time (the monotonic uptime counter is usually far below 1e9).
    assert before - 5 <= stamps[0] <= after + 5, stamps[0]
