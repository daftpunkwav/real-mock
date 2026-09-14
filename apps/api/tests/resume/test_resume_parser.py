"""Parser / file-lookup helpers that do not need an LLM."""

from __future__ import annotations

from pathlib import Path

from realmock.domains.resume.schemas.limits import MAX_EXTRACTED_CHARS
from realmock.domains.resume.services.parser import parse_resume_with_llm
from realmock.domains.resume.services.text_extract import extract_text_from_file
from realmock.domains.resume.services.repo_evidence import _pick_key_files, extract_github_repos


def test_extract_text_from_txt_and_md(tmp_path: Path) -> None:
    txt = tmp_path / "a.txt"
    txt.write_text("hello resume", encoding="utf-8")
    assert extract_text_from_file(txt, "txt") == "hello resume"

    md = tmp_path / "a.md"
    md.write_text("# Title\nbody", encoding="utf-8")
    assert "Title" in extract_text_from_file(md, "md")


def test_extract_text_truncates_to_catalog_limit(tmp_path: Path) -> None:
    blob = "x" * (MAX_EXTRACTED_CHARS + 50)
    path = tmp_path / "big.txt"
    path.write_text(blob, encoding="utf-8")
    out = extract_text_from_file(path, "txt")
    assert len(out) == MAX_EXTRACTED_CHARS


def test_pick_key_files_prefers_manifests() -> None:
    paths = [
        "src/util.py",
        "package.json",
        "README.md",
        "main.py",
        "lib/foo.ts",
    ]
    picked = _pick_key_files(paths, limit=2)
    assert "package.json" in picked
    assert "main.py" in picked


def test_extract_github_repos_ignores_empty() -> None:
    assert extract_github_repos("") == []
    assert extract_github_repos("no links here") == []


async def test_parse_resume_with_llm_success_clears_degraded_flag() -> None:
    class _Ok:
        async def chat_json(self, messages, **kwargs):
            return {"name": "Ada", "skills": ["Python"], "parse_degraded": True}

    profile = await parse_resume_with_llm("Ada is a backend engineer.", _Ok())  # type: ignore[arg-type]
    assert profile.parse_degraded is False
    assert profile.name == "Ada"
    assert profile.skills == ["Python"]


async def test_parse_resume_with_llm_marks_fallback() -> None:
    class _Boom:
        async def chat_json(self, messages, **kwargs):
            raise RuntimeError("no json")

    raw = "hello resume text that should become the summary"
    profile = await parse_resume_with_llm(raw, _Boom())  # type: ignore[arg-type]
    assert profile.parse_degraded is True
    assert profile.summary.startswith("hello resume")
