"""Preview tests for ledger/preview.py.

Covers: truncate preview None/short/long, non-string passthrough,
dict round-trip/truncate, dumps/loads failure paths.
Conventions: no real network/LLM (all external calls mocked); pure function tests.
"""

import json
from unittest.mock import patch

from realmock.domains.interview.ledger.preview import truncate_preview

# No handler fixture: truncate_preview is a pure function tested directly.

def test_truncate_preview_branches():
    assert truncate_preview(None) is None
    assert truncate_preview("short", max_chars=10) == "short"
    assert truncate_preview("x" * 20, max_chars=10).endswith("…")
    assert truncate_preview(42) == 42
    assert truncate_preview(True) in (True, 1)
    # small dict round-trips
    assert truncate_preview({"a": 1}, max_chars=100) == {"a": 1}
    # large dict truncated to str
    big = {"k": "v" * 200}
    out = truncate_preview(big, max_chars=20)
    assert isinstance(out, str) and out.endswith("…")
    # dumps failure -> repr path
    with patch("realmock.domains.interview.ledger.preview.json.dumps", side_effect=TypeError("no json")):
        v = object()
        out2 = truncate_preview(v, max_chars=1000)
        assert isinstance(out2, str)
    # loads failure -> return text
    with (
        patch("realmock.domains.interview.ledger.preview.json.dumps", return_value="not-json{{{"),
        patch("realmock.domains.interview.ledger.preview.json.loads", side_effect=json.JSONDecodeError("e", "d", 0)),
    ):
        assert truncate_preview({"a": 1}, max_chars=100) == "not-json{{{"
    # truncated path needs no loads
    with patch("realmock.domains.interview.ledger.preview.json.dumps", return_value="z" * 50):
        assert truncate_preview({"a": 1}, max_chars=10).endswith("…")

