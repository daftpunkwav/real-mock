"""File routes extra tests for src/realmock/domains/resume/routes/file.py.

Covers: get_resume_pages_meta pdf-read-error/business-reraise branches,
get_resume_page_image non-pdf/OOB/generic-error branches.
Conventions: no real network/model downloads (all clients mocked); store/file
helpers mocked; rate limits reset per test.
"""

from __future__ import annotations

import pytest

import realmock.domains.resume.routes.file as file_mod
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.models import Resume


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def _resume_row(**over) -> Resume:
    base = {"filename": "a.pdf", "file_type": "pdf", "raw_text": "x", "parsed_profile": "{}"}
    base.update(over)
    return Resume(**base)


def test_pages_meta_pdf_read_error(monkeypatch) -> None:
    def _boom(path):
        raise RuntimeError("pdf broken")

    monkeypatch.setattr(file_mod, "pdf_page_count", _boom)
    monkeypatch.setattr(file_mod.store, "get_row", lambda db, rid: _resume_row())
    monkeypatch.setattr(file_mod, "find_resume_file", lambda r: __import__("pathlib").Path("/tmp/a.pdf"))
    with pytest.raises(ApiBusinessError) as e:
        file_mod.get_resume_pages_meta(1, db=object())  # type: ignore[arg-type]
    assert e.value.error_code == "A1004"


def test_pages_meta_reraises_business(monkeypatch) -> None:
    from realmock.platform.core.errors import raise_error

    def _boom(path):
        try:
            raise_error("A1004")
        except ApiBusinessError:
            raise

    monkeypatch.setattr(file_mod, "pdf_page_count", _boom)
    monkeypatch.setattr(file_mod.store, "get_row", lambda db, rid: _resume_row())
    monkeypatch.setattr(file_mod, "find_resume_file", lambda r: __import__("pathlib").Path("/tmp/a.pdf"))
    with pytest.raises(ApiBusinessError):
        file_mod.get_resume_pages_meta(1, db=object())  # type: ignore[arg-type]


def test_page_image_non_pdf_and_oob(monkeypatch) -> None:
    monkeypatch.setattr(file_mod.store, "get_row", lambda db, rid: _resume_row(file_type="txt"))
    monkeypatch.setattr(file_mod, "find_resume_file", lambda r: __import__("pathlib").Path("/tmp/a.txt"))
    with pytest.raises(ApiBusinessError) as e:
        file_mod.get_resume_page_image(1, 1, db=object())  # type: ignore[arg-type]
    assert e.value.error_code == "A0404"

    monkeypatch.setattr(file_mod.store, "get_row", lambda db, rid: _resume_row(file_type="pdf"))
    monkeypatch.setattr(file_mod, "find_resume_file", lambda r: __import__("pathlib").Path("/tmp/a.pdf"))
    monkeypatch.setattr(file_mod, "render_pdf_page_png", lambda path, n: (_ for _ in ()).throw(ValueError("oob")))
    with pytest.raises(ApiBusinessError) as e2:
        file_mod.get_resume_page_image(1, 99, db=object())  # type: ignore[arg-type]
    assert e2.value.error_code == "A0404"


def test_page_image_generic_error(monkeypatch) -> None:
    monkeypatch.setattr(file_mod.store, "get_row", lambda db, rid: _resume_row(file_type="pdf"))
    monkeypatch.setattr(file_mod, "find_resume_file", lambda r: __import__("pathlib").Path("/tmp/a.pdf"))
    monkeypatch.setattr(file_mod, "render_pdf_page_png", lambda path, n: (_ for _ in ()).throw(RuntimeError("render down")))
    with pytest.raises(ApiBusinessError) as e:
        file_mod.get_resume_page_image(1, 1, db=object())  # type: ignore[arg-type]
    assert e.value.error_code == "A1004"
