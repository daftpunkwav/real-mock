"""Text extract tests for src/realmock/domains/resume/services/text_extract.py.

Covers: truncate_text/_truncate limits, _heading_prefix variants,
_assert_docx_zip_safe entry-count/decompression branches,
_extract_docx_structured headings/tables/error branches, extract_text_from_file
pdf/docx/md/txt/page-cap/truncate branches.
Conventions: no real network/model downloads (all clients mocked); Document/PdfReader faked.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def test_truncate_helpers() -> None:
    from realmock.domains.resume.services import text_extract as te
    from realmock.domains.resume.schemas.limits import MAX_EXTRACTED_CHARS

    assert te.truncate_text("abc") == "abc"
    long_text = "x" * (MAX_EXTRACTED_CHARS + 10)
    assert len(te.truncate_text(long_text)) == MAX_EXTRACTED_CHARS
    assert te._truncate("ab") == "ab"


def test_heading_prefix_variants() -> None:
    from realmock.domains.resume.services.text_extract import _heading_prefix

    assert _heading_prefix("Heading 1") == "# "
    assert _heading_prefix("Title") == "# "
    assert _heading_prefix("HEADING 2 custom") == "## "
    assert _heading_prefix("Heading 3 deep") == "### "
    assert _heading_prefix("Normal") == ""
    assert _heading_prefix("") == ""


def test_assert_docx_zip_safe_guards(tmp_path: Path, monkeypatch) -> None:
    from realmock.domains.resume.services import text_extract as te
    from realmock.domains.resume.schemas.limits import MAX_DOCX_ZIP_ENTRIES

    real_zip = tmp_path / "ok.docx"
    with zipfile.ZipFile(real_zip, "w") as zf:
        zf.writestr("a.xml", "hello")
    te._assert_docx_zip_safe(real_zip)

    class _BigInfo:
        file_size = 10

    class _FakeZip:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def infolist(self):
            return [_BigInfo() for _ in range(MAX_DOCX_ZIP_ENTRIES + 1)]

    monkeypatch.setattr(te.zipfile, "ZipFile", _FakeZip)
    with pytest.raises(ValueError, match="Too many DOCX entries"):
        te._assert_docx_zip_safe(real_zip)

    class _HugeInfo:
        file_size = 40 * 1024 * 1024

    class _FakeZip2(_FakeZip):
        def infolist(self):
            return [_HugeInfo()]

    monkeypatch.setattr(te.zipfile, "ZipFile", _FakeZip2)
    with pytest.raises(ValueError, match="decompression"):
        te._assert_docx_zip_safe(real_zip)


def test_extract_docx_structured_headings_tables_and_errors(monkeypatch) -> None:
    from realmock.domains.resume.services import text_extract as te

    class _Style:
        def __init__(self, name: str):
            self.name = name

    class _Para:
        def __init__(self, text: str, style: str = ""):
            self.text = text
            self.style = _Style(style)

    class _BadStylePara:
        text = "oops"

        @property
        def style(self):
            raise RuntimeError("no style")

    class _Cell:
        def __init__(self, text: str):
            self.text = text

    class _Row:
        def __init__(self, cells):
            self._cells = [_Cell(c) for c in cells]

        @property
        def cells(self):
            return self._cells

    class _BadRow:
        @property
        def cells(self):
            raise RuntimeError("bad cells")

    class _Table:
        def __init__(self, rows):
            self._rows = rows

        @property
        def rows(self):
            return self._rows

    class _BadTable:
        @property
        def rows(self):
            raise RuntimeError("bad rows")

    class _Doc:
        paragraphs = [
            _Para("Title text", "Title"),
            _Para("Section", "Heading 2"),
            _Para("   ", "Normal"),
            _BadStylePara(),
        ]
        tables = [
            _Table([_Row(["a", "b"]), _Row(["", ""]), _BadRow()]),
            _BadTable(),
        ]

    monkeypatch.setattr(te, "Document", lambda path: _Doc())
    out = te._extract_docx_structured(Path("/tmp/f.docx"))
    assert "# Title text" in out
    assert "## Section" in out
    assert "[table]" in out
    assert "a | b" in out


def test_extract_text_from_file_branches(tmp_path: Path, monkeypatch) -> None:
    from realmock.domains.resume.services import text_extract as te

    # pdf normal + page cap
    class _Page:
        def __init__(self, text: str):
            self._text = text

        def extract_text(self):
            return self._text

    class _Reader:
        def __init__(self, pages):
            self.pages = pages

    monkeypatch.setattr(te, "PdfReader", lambda path: _Reader([_Page("a"), _Page(None)]))
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF")
    assert te.extract_text_from_file(p, "pdf") == "a\n"

    from realmock.domains.resume.schemas.limits import MAX_PDF_PAGES

    monkeypatch.setattr(te, "PdfReader", lambda path: _Reader([_Page("x")] * (MAX_PDF_PAGES + 1)))
    with pytest.raises(ValueError, match="too many pages"):
        te.extract_text_from_file(p, "PDF")

    # docx + doc both go through zip guard
    monkeypatch.setattr(te, "_assert_docx_zip_safe", lambda path: None)
    monkeypatch.setattr(te, "_extract_docx_structured", lambda path: "docx-text")
    assert te.extract_text_from_file(p, "docx") == "docx-text"
    assert te.extract_text_from_file(p, "doc") == "docx-text"

    # md/txt truncate path
    md = tmp_path / "r.md"
    md.write_text("hello-md", encoding="utf-8")
    assert te.extract_text_from_file(md, "md") == "hello-md"
    txt = tmp_path / "r.txt"
    txt.write_text("y" * 200000, encoding="utf-8")
    from realmock.domains.resume.schemas.limits import MAX_EXTRACTED_CHARS

    assert len(te.extract_text_from_file(txt, "txt")) == MAX_EXTRACTED_CHARS
