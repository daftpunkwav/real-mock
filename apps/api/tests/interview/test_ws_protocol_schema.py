"""WS protocol contract: protocol/interview_ws.schema.json is aligned with backend and frontend types."""

from __future__ import annotations

import json
import re
from pathlib import Path

from realmock.domains.interview.constants import WSClientEvent, WSServerEvent

ROOT = Path(__file__).resolve().parents[4]  # repo root (tests/interview/ -> apps/api -> apps -> repo)
SCHEMA_PATH = ROOT / "protocol" / "interview_ws.schema.json"
FRONTEND_WS_TS = ROOT / "apps" / "web" / "src" / "types" / "domains" / "interview_ws.ts"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _extract_ts_event_types(ts_path: Path) -> tuple[set[str], set[str]]:
    text = ts_path.read_text(encoding="utf-8")
    client_idx = text.find("export type ClientEvent")
    server_part = text[:client_idx] if client_idx > 0 else text
    client_part = text[client_idx:] if client_idx > 0 else ""
    server_types = set(re.findall(r"type:\s*\"([a-z_]+)\"", server_part))
    client_types = set(re.findall(r"type:\s*\"([a-z_]+)\"", client_part))
    return server_types, client_types


def _extract_ts_required_fields(ts_path: Path) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Extract field names other than type for each event from the TS union type (heuristically aligned with the interview_ws.ts structure)."""
    text = ts_path.read_text(encoding="utf-8")
    client_idx = text.find("export type ClientEvent")
    server_part = text[:client_idx] if client_idx > 0 else text
    client_part = text[client_idx:] if client_idx > 0 else ""

    def _scan(part: str) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for block in re.findall(r"\{[^{}]*type:\s*\"([a-z_]+)\"[^{}]*\}", part):
            pass
        # Multi-line block: from type to the next `| {` or `;`
        for m in re.finditer(
            r"type:\s*\"([a-z_]+)\"([^|]*?)(?=\||;)",
            part,
            flags=re.DOTALL,
        ):
            event = m.group(1)
            body = m.group(2)
            fields = set(re.findall(r"([a-z_][a-z0-9_]*)\s*[:?]", body))
            fields.discard("type")
            out[event] = fields
        return out

    return _scan(server_part), _scan(client_part)


def test_ws_schema_matches_backend_enums() -> None:
    schema = _load_schema()
    server_schema = set(schema["serverEventTypes"])
    client_schema = set(schema["clientEventTypes"])

    enum_server = {e.value for e in WSServerEvent}
    enum_client = {e.value for e in WSClientEvent}

    assert enum_server <= server_schema
    assert enum_client <= client_schema


def test_ws_schema_covers_frontend_types() -> None:
    schema = _load_schema()
    ts_server, ts_client = _extract_ts_event_types(FRONTEND_WS_TS)
    ts_server.add("error")

    server_schema = set(schema["serverEventTypes"])
    client_schema = set(schema["clientEventTypes"])

    assert ts_server <= server_schema
    assert ts_client <= client_schema


def test_ws_schema_payload_entries_complete() -> None:
    schema = _load_schema()
    server_payloads = schema.get("serverEventPayloads", {})
    client_payloads = schema.get("clientEventPayloads", {})

    for event in schema["serverEventTypes"]:
        assert event in server_payloads, f"Missing server payload definition: {event}"
        assert "required" in server_payloads[event]
        assert "properties" in server_payloads[event]

    for event in schema["clientEventTypes"]:
        assert event in client_payloads, f"Missing client payload definition: {event}"
        assert "required" in client_payloads[event]
        assert "properties" in client_payloads[event]


def test_ws_schema_payload_required_covers_frontend_fields() -> None:
    schema = _load_schema()
    ts_server, ts_client = _extract_ts_required_fields(FRONTEND_WS_TS)
    ts_server["error"] = {"message"}  # SSEErrorEvent is re-exported from another file

    server_payloads = schema["serverEventPayloads"]
    client_payloads = schema["clientEventPayloads"]

    for event, fields in ts_server.items():
        if event not in server_payloads:
            continue
        required = set(server_payloads[event]["required"])
        props = set(server_payloads[event]["properties"].keys())
        allowed = required | props
        missing = fields - allowed
        assert not missing, f"server {event} schema does not cover the frontend field: {missing}"

    for event, fields in ts_client.items():
        if event not in client_payloads:
            continue
        required = set(client_payloads[event]["required"])
        props = set(client_payloads[event]["properties"].keys())
        allowed = required | props
        missing = fields - allowed
        assert not missing, f"client {event} schema does not cover the frontend field: {missing}"

    # Required frontend fields must be explicitly declared in schema required or properties.
    for event, fields in ts_server.items():
        if event not in server_payloads or not fields:
            continue
        required = set(server_payloads[event]["required"])
        props = set(server_payloads[event]["properties"].keys())
        for f in fields:
            assert f in required or f in props, f"server {event}.{f} Not declared in schema"

    for event, fields in ts_client.items():
        if event not in client_payloads or not fields:
            continue
        required = set(client_payloads[event]["required"])
        props = set(client_payloads[event]["properties"].keys())
        for f in fields:
            assert f in required or f in props, f"client {event}.{f} Not declared in schema"
