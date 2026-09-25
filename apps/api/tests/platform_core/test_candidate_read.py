"""Candidate-read tests for realmock.platform.services.candidate_read.

Covers: safe ORM queries, user-profile loading/formatting, and resume
  helpers with invalid-JSON branches.
Conventions: wiped api_db per test; autouse table creation.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError


@pytest.fixture(autouse=True)
def _ensure_tables(api_engine):
    import realmock.platform.models  # noqa: F401

    from realmock.platform.database import ApiBase

    ApiBase.metadata.create_all(bind=api_engine)
    yield


def _wipe(api_db) -> None:
    from realmock.platform.models import LLMSettings, LlmProvider, ModelProfile, StageConfig, TaskBinding

    for m in (TaskBinding, ModelProfile, LlmProvider, StageConfig, LLMSettings):
        api_db.query(m).delete()
    api_db.commit()


class TestCandidateRead:
    def test_safe_query_operational_error(self, api_db) -> None:
        from realmock.platform.services.candidate_read import _safe_orm_query

        def _boom():
            raise OperationalError("x", None, Exception("no table"))

        assert _safe_orm_query(api_db, _boom, table_label="T") is None

    def test_user_profile_branches(self, api_db) -> None:
        from realmock.platform.models import UserProfile
        from realmock.platform.services import candidate_read as cr

        _wipe(api_db)
        assert cr.get_user_profile(api_db, 1) is None
        row = UserProfile(name="Alice", tech_domains='["Python"]', job_direction="Backend")
        api_db.add(row)
        api_db.commit()
        assert cr.get_user_profile(api_db, row.id) is not None
        assert cr.get_default_user_profile(api_db) is not None
        api_db.query(UserProfile).delete()
        api_db.commit()
        assert cr.get_default_user_profile(api_db) is None

    def test_format_profile_summary(self, api_db) -> None:
        from realmock.platform.models import UserProfile
        from realmock.platform.services import candidate_read as cr

        _wipe(api_db)
        assert cr.format_profile_summary(api_db, 999) == ""
        assert cr.format_profile_summary(api_db) == ""
        row = UserProfile(name="Bob", tech_domains='["Go", "Rust"]', school="X", strengths="fast")
        api_db.add(row)
        api_db.commit()
        text = cr.format_profile_summary(api_db, row.id)
        assert "Bob" in text
        assert "Go, Rust" in text
        row2 = UserProfile(name="")
        api_db.add(row2)
        api_db.commit()
        # empty fields -> empty string handled via default loader path
        assert isinstance(cr.format_profile_summary(api_db, row2.id), str)

    def test_resume_helpers(self, api_db) -> None:
        from realmock.platform.models import Resume
        from realmock.platform.services import candidate_read as cr

        _wipe(api_db)
        assert cr.format_resume_summary(api_db, None) == ""
        assert cr.get_candidate_profile(api_db, None) is None
        assert cr.get_resume_agent_payload(api_db, None) is None
        assert cr.format_resume_summary(api_db, 999) == ""
        assert cr.get_candidate_profile(api_db, 999) is None
        assert cr.get_resume_detail(api_db, 999) is None
        assert cr.get_resume_agent_payload(api_db, 999) is None
        row = Resume(filename="r.pdf", file_type="pdf", raw_text="raw", parsed_profile=json.dumps({"name": "Z", "layout_notes": "n"}))
        api_db.add(row)
        api_db.commit()
        assert "r.pdf" in cr.format_resume_summary(api_db, row.id)
        assert cr.get_candidate_profile(api_db, row.id) is not None
        assert cr.get_candidate_profile(api_db, row.id).name == "Z"
        fname, payload = cr.get_resume_detail(api_db, row.id)
        assert fname == "r.pdf"
        agent = cr.get_resume_agent_payload(api_db, row.id)
        assert agent is not None and agent["filename"] == "r.pdf"
        # invalid json branches
        row.parsed_profile = "{bad"
        api_db.commit()
        assert cr.get_candidate_profile(api_db, row.id) is None
        assert cr.get_resume_detail(api_db, row.id)[1] == {}
        assert cr.get_resume_agent_payload(api_db, row.id)["parsed"] == {}
        row.parsed_profile = "[1,2]"
        api_db.commit()
        assert cr.get_candidate_profile(api_db, row.id) is None
        assert cr.get_resume_agent_payload(api_db, row.id)["parsed"] == {}

    def test_latest_scored_resume_id(self, api_db) -> None:
        from realmock.platform.models import Resume
        from realmock.platform.services import candidate_read as cr

        # Shared engine: clear resumes so this test is order-independent.
        api_db.query(Resume).delete()
        api_db.commit()
        assert cr.get_latest_scored_resume_id(api_db) is None
        old = Resume(filename="old.pdf", file_type="pdf", score=60, is_active=False)
        new = Resume(filename="new.pdf", file_type="pdf", score=80, is_active=True)
        unscored = Resume(filename="draft.pdf", file_type="pdf")
        api_db.add_all([old, new, unscored])
        api_db.commit()
        # active scored resume wins over other scored rows
        assert cr.get_latest_scored_resume_id(api_db) == new.id
        new.is_active = False
        api_db.commit()
        # fallback: newest scored row, ignoring newer-but-unscored rows
        assert cr.get_latest_scored_resume_id(api_db) == new.id

    def test_safe_query_rollback_failure(self, api_db, monkeypatch) -> None:
        from realmock.platform.services import candidate_read as cr

        def _boom():
            raise OperationalError("x", None, Exception("t"))

        monkeypatch.setattr(api_db, "rollback", MagicMock(side_effect=RuntimeError("rb fail")))
        assert cr._safe_orm_query(api_db, _boom, table_label="T") is None
