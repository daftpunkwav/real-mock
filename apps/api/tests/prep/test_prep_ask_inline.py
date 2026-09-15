"""Inline ask-user tests for realmock.domains.prep.agents.ask_user.inline.

Covers: _parse_inline_ask_args forms and extract_inline_ask_user capping/merging rules
Conventions: Pure parsing, no I/O; rate limits reset per test
"""
from __future__ import annotations
import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def test_parse_inline_ask_args_forms() -> None:
    from realmock.domains.prep.agents.ask_user.inline import _parse_inline_ask_args

    # JSON with nested arguments string
    raw = '<tool_call>{"name":"ask_user","arguments":"{\\"question\\":\\"Q?\\",\\"options\\":[\\"A\\",\\"B\\"]}"}</tool_call>'
    assert _parse_inline_ask_args(raw) is not None
    # invalid JSON falls through to None when no params
    assert _parse_inline_ask_args("<tool_call>not json at all</tool_call>") is None
    # JSON without question falls through
    assert _parse_inline_ask_args('<tool_call>{"name":"ask_user","arguments":{}}</tool_call>') is None
    # parameter tags with JSON options
    param = '<tool_call><parameter name="question">Pick?</parameter><parameter name="options">["A","B"]</parameter></tool_call>'
    parsed = _parse_inline_ask_args(param)
    assert parsed is not None and parsed["question"] == "Pick?"
    # parameter tags with line options
    param2 = '<tool_call><parameter name="question">Pick?</parameter><parameter name="options">- A\n- B\n</parameter></tool_call>'
    parsed2 = _parse_inline_ask_args(param2)
    assert parsed2 is not None and parsed2["options"] == ["A", "B"]
    # invalid options JSON falls back to lines
    param3 = '<tool_call><parameter name="question">Pick?</parameter><parameter name="options">not-json[</parameter></tool_call>'
    assert _parse_inline_ask_args(param3) is not None

def test_extract_inline_respects_cap_and_merges() -> None:
    from realmock.domains.prep.agents.ask_user.inline import extract_inline_ask_user

    assert extract_inline_ask_user("plain text") == ("plain text", None)
    # non-ask blocks preserved
    other = 'keep <tool_call>{"name":"web_search","arguments":{}}</tool_call> end'
    cleaned, evt = extract_inline_ask_user(other)
    assert evt is None
    assert "<tool_call>" in cleaned
    # invalid ask blocks stripped with no event
    bad = '<tool_call>{"name":"ask_user","arguments":{"question":"","options":[]}}</tool_call> tail'
    cleaned2, evt2 = extract_inline_ask_user(bad)
    assert "<tool_call>" not in cleaned2
    assert evt2 is None
    # nine blocks capped at eight
    many = "".join(
        f'<tool_call>{{"name":"ask_user","arguments":{{"question":"Q{i}?","options":["A","B"]}}}}</tool_call>'
        for i in range(9)
    )
    cleaned3, evt3 = extract_inline_ask_user("head " + many)
    assert "<tool_call>" not in cleaned3
    assert evt3 is not None
    assert len(evt3["questions"]) == 8
    # single block has no questions key (needs >=2 options)
    one = '<tool_call>{"name":"ask_user","arguments":{"question":"Solo?","options":["A","B"]}}</tool_call>'
    _, evt4 = extract_inline_ask_user(one)
    assert evt4 is not None and "questions" not in evt4
    # single option cannot render a dialog
    solo_one_opt = '<tool_call>{"name":"ask_user","arguments":{"question":"Solo?","options":["A"]}}</tool_call>'
    _, evt5 = extract_inline_ask_user(solo_one_opt)
    assert evt5 is None

def test_extract_inline_param_style_recovers() -> None:
    from realmock.domains.prep.agents.ask_user.inline import extract_inline_ask_user

    body = '<tool_call><invoke name="ask_user"><parameter name="question">Which?</parameter><parameter name="options">["A","B"]</parameter></invoke></tool_call>'
    cleaned, evt = extract_inline_ask_user(body)
    assert evt is not None and evt["question"] == "Which?"
    assert "<tool_call>" not in cleaned
