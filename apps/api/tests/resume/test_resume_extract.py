"""Resume text-extraction orchestration: empty files and vision fallback."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from realmock.domains.resume.services import extract as extract_mod
from realmock.platform.core.errors import ApiBusinessError


def test_extract_empty_non_pdf_is_a1004(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    async def run() -> None:
        await extract_mod.extract_resume_text(path, "txt", SimpleNamespace(api_key="k"), db=object())

    with pytest.raises(ApiBusinessError) as caught:
        asyncio.run(run())
    assert caught.value.error_code == "A1004"


def test_extract_returns_non_empty_text(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("hello resume", encoding="utf-8")

    async def run() -> str:
        return await extract_mod.extract_resume_text(
            path, "txt", SimpleNamespace(api_key="k"), db=object()
        )

    assert asyncio.run(run()) == "hello resume"


def test_extract_empty_pdf_without_vision_is_a1006(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-")
    monkeypatch.setattr(extract_mod, "extract_text_from_file", lambda *_args, **_kw: "")
    monkeypatch.setattr(extract_mod, "get_stage_config_for_runtime", lambda *_args, **_kw: {})

    async def run() -> None:
        await extract_mod.extract_resume_text(path, "pdf", SimpleNamespace(api_key=""), db=object())

    with pytest.raises(ApiBusinessError) as caught:
        asyncio.run(run())
    assert caught.value.error_code == "A1006"


def test_extract_parser_failure_is_a1004(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        extract_mod,
        "extract_text_from_file",
        lambda *_args, **_kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    async def run() -> None:
        await extract_mod.extract_resume_text(path, "txt", SimpleNamespace(api_key="k"), db=object())

    with pytest.raises(ApiBusinessError) as caught:
        asyncio.run(run())
    assert caught.value.error_code == "A1004"
