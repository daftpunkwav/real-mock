"""Interview WebSocket API."""

from fastapi import APIRouter, Query, WebSocket

from realmock.platform.core.local_only import guard_ws_origin
from realmock.platform.core.session_auth import extract_ws_token
from realmock.domains.interview.realtime.ws_handler import InterviewWSHandler

router = APIRouter()


@router.websocket("/ws/interview/{session_id}")
async def interview_websocket(
    websocket: WebSocket,
    session_id: int,
    token: str = Query(default="", description="Session Capability Token (compatible; preferred subprotocol)"),
):
    """Realtime interview socket: origin-guarded handshake, then room loop.

    FastAPI dependencies cannot run on WS scopes, so origin + capability-token
    checks happen inline before delegating to :class:`InterviewWSHandler`.
    """
    # Dependency guards cannot run on WS scopes: reject browser-driven
    # cross-site handshakes here instead (capability token still applies).
    if not await guard_ws_origin(websocket):
        return
    access, chosen_proto = extract_ws_token(
        websocket, session_id=session_id, query_token=token
    )
    # Echo only the mock.<token> subprotocol declared in the client handshake; never echo tokens extracted from cookies/queries
    # Generate response subprotocol - RFC 6455 requires that the response subprotocol be taken from the client's request list, otherwise the browser
    # Directly reject the handshake (the front end has switched to using cookies to pass tokens, and it is no longer actively constructed here).
    echo_proto = chosen_proto
    handler = InterviewWSHandler(
        websocket,
        session_id,
        access_token=access,
        ws_subprotocol=echo_proto,
    )
    await handler.handle()
