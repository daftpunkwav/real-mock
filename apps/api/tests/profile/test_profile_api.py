"""Profile API tests: GET/PUT contract, length 422, get_or_create, and tech_domains coerce.

HTTP layer only (TestClient against the ASGI app). Pure schema/validator units
live in test_profile_schemas.py; contract-guard drift alarms live in
test_profile_contract_guard.py.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from realmock.asgi import app
from realmock.domains.profile.schemas.field_meta import (
    FIELD_MAX_LENGTH,
    TECH_DOMAIN_ITEM_MAX,
    TECH_DOMAINS_MAX_COUNT,
)


@pytest.fixture(autouse=True)
def _clean_profile_table(api_engine):
    """Clear the profile table before each case so order does not matter."""
    import realmock.platform.models  # noqa: F401  # register ORM
    from realmock.platform.database import ApiBase
    from realmock.platform.models import UserProfile

    ApiBase.metadata.create_all(bind=api_engine)
    with api_engine.begin() as conn:
        conn.execute(delete(UserProfile))
    yield


def test_get_profile_creates_default() -> None:
    """First GET on an empty table inserts a blank profile (required fields empty)."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/profile")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == ""
    assert body["identity"] == ""
    assert body["tech_domains"] == []


def _put(client: TestClient, **overrides) -> object:
    payload: dict = {
        "name": "Test user",
        "identity": "Employed",
        "job_direction": "Backend development",
        "target_role": "Backend engineer",
        "self_intro": "introduce",
        "tech_domains": ["Python"],
    }
    payload.update(overrides)
    return client.put("/api/v1/profile", json=payload)


def test_put_roundtrip_persists() -> None:
    payload = {
        "name": "Test user",
        "identity": "Employed",
        "job_direction": "Backend development",
        "target_role": "Backend engineer",
        "self_intro": "Five years of backend experience",
        "tech_domains": ["Python", "Go"],
    }
    with TestClient(app) as client:
        resp = client.put("/api/v1/profile", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Test user"
        assert body["tech_domains"] == ["Python", "Go"]
        # Re-read after persist must match
        assert client.get("/api/v1/profile").json()["name"] == "Test user"


@pytest.mark.parametrize(
    "field,limit",
    [
        ("name", FIELD_MAX_LENGTH["name"]),
        ("gender", FIELD_MAX_LENGTH["gender"]),
        ("school", FIELD_MAX_LENGTH["school"]),
        ("self_intro", FIELD_MAX_LENGTH["self_intro"]),
        ("portfolio_url", FIELD_MAX_LENGTH["portfolio_url"]),
    ],
)
def test_put_over_limit_returns_422(field: str, limit: int) -> None:
    """Fields over contract max_length are rejected with 422, not silently stored."""
    with TestClient(app) as client:
        resp = _put(client, **{field: "x" * (limit + 1)})
    assert resp.status_code == 422


def test_put_domain_constraints() -> None:
    """Domain list count/item max from field_meta; boundary values pass (distinct items so dedupe cannot hide count checks)."""
    with TestClient(app) as client:
        assert _put(client, tech_domains=[f"d{i}" for i in range(TECH_DOMAINS_MAX_COUNT + 1)]).status_code == 422
        assert _put(client, tech_domains=["x" * (TECH_DOMAIN_ITEM_MAX + 1)]).status_code == 422
        item_prefix = TECH_DOMAIN_ITEM_MAX - 2
        resp = _put(
            client,
            tech_domains=[f"{'x' * item_prefix}{i:02d}" for i in range(TECH_DOMAINS_MAX_COUNT)],
        )
    assert resp.status_code == 200
    assert len(resp.json()["tech_domains"]) == TECH_DOMAINS_MAX_COUNT


def test_put_at_limit_accepted() -> None:
    with TestClient(app) as client:
        resp = _put(
            client,
            name="x" * FIELD_MAX_LENGTH["name"],
            self_intro="y" * FIELD_MAX_LENGTH["self_intro"],
        )
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", ""),
        ("name", "   "),
        ("identity", ""),
        ("job_direction", ""),
        ("target_role", ""),
        ("self_intro", ""),
        ("tech_domains", []),
        ("tech_domains", ["  ", ""]),
    ],
)
def test_put_missing_required_returns_422(field: str, value: object) -> None:
    """Blank required fields or empty tech_domains are rejected with 422."""
    with TestClient(app) as client:
        resp = _put(client, **{field: value})
    assert resp.status_code == 422


def test_put_normalizes_tech_domains() -> None:
    """Tech domains are stripped and deduped before persist."""
    with TestClient(app) as client:
        resp = _put(client, tech_domains=[" Python ", "", "Go", "Python", "  "])
    assert resp.status_code == 200
    assert resp.json()["tech_domains"] == ["Python", "Go"]


def test_clear_profile_blanks_fields_and_keeps_id() -> None:
    """POST /clear empties required and optional fields without deleting the row."""
    with TestClient(app) as client:
        put_resp = _put(
            client,
            name="Ada",
            identity="Employed",
            job_direction="Backend",
            target_role="Engineer",
            self_intro="Intro",
            tech_domains=["Python"],
            city="Shanghai",
            portfolio_url="https://example.com",
        )
        assert put_resp.status_code == 200
        profile_id = put_resp.json()["id"]

        clear_resp = client.post("/api/v1/profile/clear")
        assert clear_resp.status_code == 200
        body = clear_resp.json()
        assert body["id"] == profile_id
        assert body["name"] == ""
        assert body["identity"] == ""
        assert body["job_direction"] == ""
        assert body["target_role"] == ""
        assert body["self_intro"] == ""
        assert body["city"] == ""
        assert body["portfolio_url"] == ""
        assert body["tech_domains"] == []

        reread = client.get("/api/v1/profile").json()
        assert reread["id"] == profile_id
        assert reread["name"] == ""
        assert reread["tech_domains"] == []


def test_clear_profile_is_idempotent() -> None:
    """Clearing an already blank profile still returns 200 and empty fields."""
    with TestClient(app) as client:
        first = client.post("/api/v1/profile/clear")
        second = client.post("/api/v1/profile/clear")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["name"] == ""
    assert second.json()["tech_domains"] == []


def test_coerce_domains_from_orm_corrupt_json_returns_empty_and_logs(caplog) -> None:
    """Invalid JSON becomes [] and logs length only (no payload)."""
    import logging

    from realmock.domains.profile.schemas.tech_domains import coerce_domains_from_orm

    with caplog.at_level(logging.WARNING, logger="realmock.domains.profile.schemas.tech_domains"):
        assert coerce_domains_from_orm("{not-json") == []
        assert coerce_domains_from_orm("{}") == []
        assert coerce_domains_from_orm(["Python"]) == ["Python"]
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "tech_domains" in messages
    assert "{not-json" not in messages


def test_orm_tech_domains_list_logs_on_corrupt_json(caplog) -> None:
    """Interview/Prep read path fail-closes to [] and logs."""
    import logging

    from realmock.platform.models import UserProfile

    row = UserProfile(tech_domains="{not-json")
    with caplog.at_level(logging.WARNING, logger="realmock.platform.models"):
        assert row.tech_domains_list == []
    assert caplog.records
    assert "{not-json" not in caplog.text


def test_get_coerces_corrupt_tech_domains_to_empty_list(api_engine) -> None:
    """GET still 200s when the stored JSON is corrupt; the UI sees an empty list."""
    from sqlalchemy.orm import Session

    from realmock.platform.models import UserProfile

    with Session(api_engine) as db:
        db.add(UserProfile(tech_domains="{not-json"))
        db.commit()

    with TestClient(app) as client:
        resp = client.get("/api/v1/profile")
    assert resp.status_code == 200
    assert resp.json()["tech_domains"] == []


# --- tech_domains coercion through the HTTP layer ---

@pytest.mark.parametrize(
    "raw",
    [
        "{not-json",  # invalid JSON -> []
        '{"a": 1}',  # valid JSON but not a list -> []
        '["Python"] trailing',  # truncated JSON -> []
        "42",  # JSON scalar -> []
    ],
)
def test_put_tech_domains_bad_string_becomes_empty_and_422(raw: str) -> None:
    """A JSON-string input that does not decode to a list normalizes to [] (min_length=1 -> 422)."""
    with TestClient(app) as client:
        resp = _put(client, tech_domains=raw)
    assert resp.status_code == 422


def test_put_accepts_tech_domains_as_json_string() -> None:
    """A JSON-encoded domain list is accepted; the response stays a clean list."""
    with TestClient(app) as client:
        resp = _put(client, tech_domains='[" Python ", "Go", "Go"]')
    assert resp.status_code == 200
    assert resp.json()["tech_domains"] == ["Python", "Go"]


def test_put_tech_domains_non_list_scalar_returns_422() -> None:
    """Non-string, non-list scalars pass the validator untouched and fail list validation."""
    with TestClient(app) as client:
        resp = _put(client, tech_domains=42)
    assert resp.status_code == 422


def test_put_tech_domains_skips_non_string_items() -> None:
    """Non-string list items are dropped, not coerced; strings still trim and dedupe."""
    with TestClient(app) as client:
        resp = _put(client, tech_domains=["Python", 42, None, "Go", "Python", "  "])
    assert resp.status_code == 200
    assert resp.json()["tech_domains"] == ["Python", "Go"]
