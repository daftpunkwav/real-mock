"""Usage accounting tests for apps/api/src/realmock/platform/capabilities/ai/llm/usage.py.

Covers: UsageAccumulator record_response/record_stream_event/merge/to_dict/cache_hit_rate
across OPENAI_CHAT, ANTHROPIC_MESSAGES and OPENAI_RESPONSES shapes.

Conventions: pure functions, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator, _as_int
from realmock.platform.core.constants import LLMProtocol

CHAT = LLMProtocol.OPENAI_CHAT
ANTH = LLMProtocol.ANTHROPIC_MESSAGES
RESP = LLMProtocol.OPENAI_RESPONSES


def test_as_int_variants() -> None:
    assert _as_int("5") == 5
    assert _as_int(3) == 3
    assert _as_int("0") == 0
    assert _as_int(-2) == 0
    assert _as_int(None) == 0
    assert _as_int("bad") == 0
    assert _as_int(4.9) == 4


def test_cache_hit_rate_none_without_prompt() -> None:
    acc = UsageAccumulator()
    assert acc.cache_hit_rate is None
    acc.prompt_tokens = 100
    acc.cached_tokens = 30
    assert acc.cache_hit_rate == 0.3


def test_cache_hit_rate_capped_at_one() -> None:
    acc = UsageAccumulator(prompt_tokens=10, cached_tokens=99)
    assert acc.cache_hit_rate == 1.0


def test_to_dict_and_merge() -> None:
    acc = UsageAccumulator(prompt_tokens=1, completion_tokens=2, cached_tokens=3)
    assert acc.to_dict() == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "cached_tokens": 3,
        "reasoning_tokens": 0,
    }
    other = UsageAccumulator(prompt_tokens=10, completion_tokens=20, cached_tokens=30, requests=2)
    acc.merge(other)
    assert acc.prompt_tokens == 11
    assert acc.requests == 2
    acc.merge(None)
    assert acc.prompt_tokens == 11


def test_record_response_openai() -> None:
    acc = UsageAccumulator()
    ok = acc.record_response({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}, CHAT)
    assert ok is True
    assert acc.prompt_tokens == 10
    assert acc.requests == 1


def test_record_response_openai_cached_details() -> None:
    acc = UsageAccumulator()
    data = {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "prompt_tokens_details": {"cached_tokens": 4}}}
    assert acc.record_response(data, CHAT) is True
    assert acc.cached_tokens == 4


def test_record_response_openai_deepseek_fallback() -> None:
    acc = UsageAccumulator()
    data = {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "prompt_cache_hit_tokens": 7}}
    assert acc.record_response(data, CHAT) is True
    assert acc.cached_tokens == 7


def test_record_response_openai_non_dict_details() -> None:
    acc = UsageAccumulator()
    data = {"usage": {"prompt_tokens": 2, "completion_tokens": 1, "prompt_tokens_details": "x"}}
    assert acc.record_response(data, CHAT) is True
    assert acc.cached_tokens == 0


def test_record_response_empty_or_missing() -> None:
    acc = UsageAccumulator()
    assert acc.record_response({}, CHAT) is False
    assert acc.record_response({"usage": "x"}, CHAT) is False
    assert acc.record_response({"usage": {}}, CHAT) is False
    assert acc.record_response("not-a-dict", CHAT) is False  # type: ignore[arg-type]


def test_record_response_anthropic() -> None:
    acc = UsageAccumulator()
    data = {"usage": {"input_tokens": 8, "output_tokens": 3, "cache_read_input_tokens": 2}}
    assert acc.record_response(data, ANTH) is True
    assert acc.prompt_tokens == 8
    assert acc.cached_tokens == 2
    assert acc.requests == 1


def test_record_response_responses() -> None:
    acc = UsageAccumulator()
    data = {"usage": {"input_tokens": 6, "output_tokens": 2, "input_tokens_details": {"cached_tokens": 1}}}
    assert acc.record_response(data, RESP) is True
    assert acc.cached_tokens == 1


def test_record_stream_event_non_dict() -> None:
    acc = UsageAccumulator()
    assert acc.record_stream_event("x", CHAT) is False  # type: ignore[arg-type]


def test_record_stream_anthropic_message_start() -> None:
    acc = UsageAccumulator()
    ev = {"type": "message_start", "message": {"usage": {"input_tokens": 5, "output_tokens": 1}}}
    assert acc.record_stream_event(ev, ANTH) is True
    assert acc.prompt_tokens == 5
    assert acc.requests == 1


def test_record_stream_anthropic_message_delta_folds_cumulative() -> None:
    acc = UsageAccumulator()
    start = {"type": "message_start", "message": {"usage": {"input_tokens": 5, "output_tokens": 1}}}
    assert acc.record_stream_event(start, ANTH) is True
    assert acc.record_stream_event({"type": "message_delta", "usage": {"output_tokens": 10}}, ANTH) is True
    assert acc.completion_tokens == 10
    # Smaller cumulative value does not move backwards.
    assert acc.record_stream_event({"type": "message_delta", "usage": {"output_tokens": 3}}, ANTH) is True
    assert acc.completion_tokens == 10
    # No output_tokens key still returns True.
    assert acc.record_stream_event({"type": "message_delta", "usage": {}}, ANTH) is True


def test_record_stream_anthropic_usage_across_rounds() -> None:
    """One accumulator spans every round of an agent run.

    message_delta is cumulative per message, so the second round must add to
    the first instead of comparing against the running total.
    """
    acc = UsageAccumulator()

    def round_(input_tokens: int, final_output: int) -> None:
        acc.record_stream_event(
            {
                "type": "message_start",
                "message": {"usage": {"input_tokens": input_tokens, "output_tokens": 4}},
            },
            ANTH,
        )
        acc.record_stream_event(
            {"type": "message_delta", "usage": {"output_tokens": final_output}}, ANTH
        )

    round_(1000, 800)
    round_(1200, 600)
    assert acc.completion_tokens == 1400
    assert acc.prompt_tokens == 2200
    assert acc.requests == 2


def test_record_stream_anthropic_other_returns_false() -> None:
    acc = UsageAccumulator()
    assert acc.record_stream_event({"type": "content_block_delta"}, ANTH) is False


def test_record_stream_responses_completed() -> None:
    acc = UsageAccumulator()
    ev = {"type": "response.completed", "response": {"usage": {"input_tokens": 4, "output_tokens": 4}}}
    assert acc.record_stream_event(ev, RESP) is True
    assert acc.prompt_tokens == 4
    assert acc.record_stream_event({"type": "other"}, RESP) is False


def test_record_stream_openai_chat_usage() -> None:
    acc = UsageAccumulator()
    ev = {"usage": {"prompt_tokens": 7, "completion_tokens": 2}}
    assert acc.record_stream_event(ev, CHAT) is True
    assert acc.record_stream_event({"choices": []}, CHAT) is False


def test_absorb_anthropic_empty_returns_false() -> None:
    acc = UsageAccumulator()
    assert acc.record_response({"usage": {}}, ANTH) is False
    assert acc.requests == 0


def test_record_response_openai_reasoning_tokens() -> None:
    acc = UsageAccumulator()
    data = {
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "completion_tokens_details": {"reasoning_tokens": 3},
        }
    }
    assert acc.record_response(data, CHAT) is True
    assert acc.reasoning_tokens == 3


def test_record_response_openai_reasoning_flat_fallback() -> None:
    acc = UsageAccumulator()
    data = {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "reasoning_tokens": 2}}
    assert acc.record_response(data, CHAT) is True
    assert acc.reasoning_tokens == 2


def test_record_response_responses_reasoning_tokens() -> None:
    acc = UsageAccumulator()
    data = {
        "usage": {
            "input_tokens": 6,
            "output_tokens": 4,
            "output_tokens_details": {"reasoning_tokens": 3},
        }
    }
    assert acc.record_response(data, RESP) is True
    assert acc.reasoning_tokens == 3


def test_note_response_meta_captures_headers_and_latency() -> None:
    import time

    acc = UsageAccumulator()
    acc.note_request_start()
    time.sleep(0.01)

    class _Headers(dict):
        def get(self, key, default=None):
            return super().get(key.lower(), default)

    acc.note_response_meta(_Headers({"x-request-id": "req-123"}))
    assert acc.last_request_id == "req-123"
    assert acc.last_latency_ms >= 10.0


def test_note_request_error_truncates() -> None:
    acc = UsageAccumulator()
    acc.note_request_error(RuntimeError("boom " * 100))
    assert acc.last_error.startswith("RuntimeError: boom")
    assert len(acc.last_error) <= 300
    assert acc.last_error.endswith("...")
