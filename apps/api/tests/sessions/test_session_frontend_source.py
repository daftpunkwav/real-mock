"""Session fix: static assertions on frontend source (retryNow reconnects, and a finish failure does not navigate away)."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]  # Repository root
# After frontend commit 0c14d0c consolidated code by domain, the hook moved from features/media/ to features/interview/hooks/.
_WS_HOOK = _ROOT / "apps" / "web" / "src" / "features" / "interview" / "hooks" / "useInterviewWS.ts"
_ROOM = _ROOT / "apps" / "web" / "src" / "features" / "interview" / "hooks" / "room" / "useInterviewRoom.ts"
_ACTIONS = _ROOT / "apps" / "web" / "src" / "features" / "interview" / "hooks" / "room" / "useInterviewRoomActions.ts"
_EVENTS = _ROOT / "apps" / "web" / "src" / "features" / "interview" / "hooks" / "room" / "useInterviewRoomEvents.ts"


def test_retry_now_uses_reconnect_key() -> None:
    text = _WS_HOOK.read_text(encoding="utf-8")
    assert "reconnectKey" in text
    assert "setReconnectKey" in text
    assert "retryNow" in text
    # effect dependencies must include reconnectKey
    assert "reconnectKey" in text
    assert "sessionId" in text and "maxRetries" in text
    assert "reconnectKey," in text or "reconnectKey]" in text


def test_handle_finish_requests_closing_then_navigates() -> None:
    room = _ROOM.read_text(encoding="utf-8")
    actions = _ACTIONS.read_text(encoding="utf-8")
    events = _EVENTS.read_text(encoding="utf-8")
    assert "handleFinish" in room or "handleFinish" in actions
    assert "request_finish" in actions
    assert "toast.error" in actions
    assert "router.push" in events
    # The report is generated in the WS background; the interview page navigates directly to the report page, which continues by polling (no longer await finishInterview).
    assert "router.push(`/report/${d.sessionId}`)" in events
    assert "is_complete" in events


def test_constants_encryption_version_v2() -> None:
    from realmock.platform.core.constants import API_KEY_ENCRYPTION_VERSION

    assert API_KEY_ENCRYPTION_VERSION == "enc:v2"
