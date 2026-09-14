"""Multi-round interview processes: memory document, eligibility, round creation, finish folding."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.interview.constants import ProcessStatus
from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.domains.interview.process.process_memory import (
    append_round,
    dump_memory,
    empty_memory,
    load_memory,
    mark_final,
    render_for_prompt,
)
from realmock.domains.interview.process.process_service import (
    create_next_round,
    create_process_with_first_round,
    is_next_round_eligible,
    record_round_finished,
)
from realmock.domains.interview.process.round_digest import build_round_digest
from realmock.domains.interview.schemas.process import ProcessCreateRequest


# ---- process memory document --------------------------------------------------


def test_memory_roundtrip_and_idempotent_append():
    memory = empty_memory()
    append_round(memory, round_no=1, session_id=11, result="passed", digest={"summary": "ok"})
    append_round(memory, round_no=1, session_id=11, result="passed", digest={"summary": "better"})
    append_round(memory, round_no=2, session_id=12, result=None, digest=None)
    loaded = load_memory(dump_memory(memory))
    assert [r["round_no"] for r in loaded["rounds"]] == [1, 2]
    assert loaded["rounds"][0]["digest"]["summary"] == "better"
    assert loaded["rounds"][1]["result"] is None


def test_memory_corrupt_payload_degrades_to_empty():
    assert load_memory("not json")["rounds"] == []
    assert load_memory(None)["schema"] == "realmock.process_memory.v1"
    assert load_memory('{"rounds": 3}')["rounds"] == []


def test_memory_mark_final_and_render():
    memory = empty_memory()
    assert render_for_prompt(memory) == ""
    assert render_for_prompt(None) == ""
    append_round(
        memory,
        round_no=1,
        session_id=1,
        result="passed",
        digest={
            "summary": "基础扎实",
            "topics_covered": ["Redis 持久化", "索引"],
            "weak_points": ["事务隔离级别"],
            "strengths": ["项目表述清晰"],
        },
    )
    mark_final(memory, result="passed", rounds_completed=1)
    text = render_for_prompt(memory)
    assert "Round 1" in text
    assert "基础扎实" in text
    assert "Redis 持久化" in text
    assert "事务隔离级别" in text
    assert "passed" in text


# ---- round digest -------------------------------------------------------------


def test_round_digest_from_session_state(db):
    session = InterviewSession(
        role="Backend",
        level="junior",
        company="acme",
        status="completed",
        agent_state='{"asked_questions": ["讲讲 Redis 持久化"], "weak_points": ["模糊回答"], '
        '"last_turn_score": {"brief": "项目讲得清楚", "rating": 4, "weak_points": []}}',
        round_no=1,
        result="passed",
    )
    db.add(session)
    db.commit()
    digest = build_round_digest(
        session,
        {"turns": [{"phase": "self_intro"}, {"phase": "project_deep_dive"}, {"phase": "self_intro"}]},
    )
    assert "passed" in digest["summary"]
    assert digest["topics_covered"] == ["讲讲 Redis 持久化"]
    assert digest["weak_points"] == ["模糊回答"]
    assert digest["strengths"] == ["项目讲得清楚"]
    assert digest["phases_covered"] == ["self_intro", "project_deep_dive"]


# ---- eligibility + service ----------------------------------------------------


def _make_process(db, *, max_rounds: int = 3) -> InterviewProcess:
    process = InterviewProcess(
        role="Backend",
        level="junior",
        company="acme",
        max_rounds=max_rounds,
        status=ProcessStatus.IN_PROGRESS.value,
        current_round=1,
    )
    db.add(process)
    db.commit()
    db.refresh(process)
    return process


def _add_round(db, process: InterviewProcess, round_no: int, *, status: str, result: str | None):
    session = InterviewSession(
        role=process.role,
        level=process.level,
        company=process.company,
        status=status,
        process_id=process.id,
        round_no=round_no,
        result=result,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def test_eligibility_requires_completed_passed_latest_round(db):
    process = _make_process(db, max_rounds=2)
    assert is_next_round_eligible(process, []) == (False, None)

    first = _add_round(db, process, 1, status="completed", result=None)
    assert is_next_round_eligible(process, [first]) == (False, None)

    first.result = "failed"
    db.commit()
    assert is_next_round_eligible(process, [first]) == (False, None)

    first.result = "passed"
    db.commit()
    assert is_next_round_eligible(process, [first]) == (True, 2)

    second = _add_round(db, process, 2, status="completed", result="passed")
    # cap reached: round 3 > max_rounds=2
    assert is_next_round_eligible(process, [first, second]) == (False, None)


def test_create_process_with_first_round(db):
    req = ProcessCreateRequest(role="Backend", level="junior", company="acme", max_rounds=3)
    process, session = create_process_with_first_round(db, req)
    assert process.current_round == 1
    assert process.status == ProcessStatus.IN_PROGRESS.value
    assert load_memory(process.memory)["rounds"] == []
    assert session.process_id == process.id
    assert session.round_no == 1
    assert session.status == "pending"


def test_create_next_round_validations(db):
    process = _make_process(db, max_rounds=2)
    with pytest.raises(Exception) as exc:
        create_next_round(db, process.id + 999)
    assert getattr(exc.value, "code", "") == "A2001"

    # latest round not finished yet
    _add_round(db, process, 1, status="active", result=None)
    with pytest.raises(Exception) as exc:
        create_next_round(db, process.id)
    assert getattr(exc.value, "code", "") == "A2006"

    process.status = ProcessStatus.COMPLETED.value
    db.commit()
    with pytest.raises(Exception) as exc:
        create_next_round(db, process.id)
    assert getattr(exc.value, "code", "") == "A2006"


def test_create_next_round_after_pass_and_cap(db):
    process = _make_process(db, max_rounds=2)
    _add_round(db, process, 1, status="completed", result="passed")

    second = create_next_round(db, process.id)
    assert second.round_no == 2
    assert process.current_round == 2

    # round 2 passes → next would exceed max_rounds=2
    second.status = "completed"
    second.result = "passed"
    db.commit()
    with pytest.raises(Exception) as exc:
        create_next_round(db, process.id)
    assert getattr(exc.value, "code", "") == "A2006"


def test_record_round_finished_folds_memory_and_completes_on_fail(db):
    process = _make_process(db, max_rounds=3)
    session = _add_round(db, process, 1, status="completed", result="failed")
    session.agent_state = '{"asked_questions": ["q1"], "weak_points": ["w1"]}'
    db.commit()

    record_round_finished(db, session)

    db.refresh(process)
    memory = load_memory(process.memory)
    assert memory["rounds"][0]["result"] == "failed"
    assert memory["rounds"][0]["digest"]["topics_covered"] == ["q1"]
    assert process.status == ProcessStatus.COMPLETED.value
    assert memory["final"]["result"] == "failed"


def test_record_round_finished_cap_pass_completes_process(db):
    process = _make_process(db, max_rounds=1)
    session = _add_round(db, process, 1, status="completed", result="passed")

    record_round_finished(db, session)

    db.refresh(process)
    memory = load_memory(process.memory)
    assert process.status == ProcessStatus.COMPLETED.value
    assert memory["final"]["result"] == "passed"


def test_record_round_finished_pass_keeps_process_open(db):
    process = _make_process(db, max_rounds=3)
    session = _add_round(db, process, 1, status="completed", result="passed")

    record_round_finished(db, session)

    db.refresh(process)
    assert process.status == ProcessStatus.IN_PROGRESS.value
    assert load_memory(process.memory)["final"] is None


# ---- HTTP routes --------------------------------------------------------------


def _client() -> TestClient:
    return TestClient(app)


def test_process_routes_create_list_and_next_round(db):
    client = _client()
    resp = client.post(
        "/api/v1/interview/processes",
        json={"role": "Backend", "level": "junior", "company": "acme", "max_rounds": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    process_id = body["process"]["id"]
    session_id = body["session_id"]
    assert body["process"]["current_round"] == 1
    assert body["process"]["next_round_eligible"] is False
    assert body["process"]["rounds"][0]["round_no"] == 1

    listed = client.get("/api/v1/interview/processes").json()
    assert any(p["id"] == process_id for p in listed)

    detail = client.get(f"/api/v1/interview/processes/{process_id}").json()
    assert detail["id"] == process_id

    # next round blocked while round 1 is pending
    blocked = client.post(f"/api/v1/interview/processes/{process_id}/rounds")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "A2006"

    # pass round 1 → next round unlocked
    session = db.get(InterviewSession, session_id)
    session.status = "completed"
    session.result = "passed"
    db.commit()

    nxt = client.post(f"/api/v1/interview/processes/{process_id}/rounds")
    assert nxt.status_code == 200
    assert nxt.json()["round_no"] == 2
    assert f"iv_{nxt.json()['id']}" in client.cookies


def test_process_round_response_carries_lineage(db):
    client = _client()
    body = client.post(
        "/api/v1/interview/processes",
        json={"role": "Backend", "level": "junior", "company": "acme"},
    ).json()
    sessions = client.get("/api/v1/interview/sessions").json()
    row = next(s for s in sessions if s["id"] == body["session_id"])
    assert row["process_id"] == body["process"]["id"]
    assert row["round_no"] == 1
    assert row["result"] is None
