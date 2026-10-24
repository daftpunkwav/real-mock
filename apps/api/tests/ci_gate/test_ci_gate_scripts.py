"""Tests for the repo-level CI gate scripts under ``scripts/ci/``.

The gates were only exercised by the pipeline they guard, so their behaviour
was known only through failure output. They run inside the backend suite now:
each script is loaded by file path (they live outside the backend package),
the pass paths run against the real repository, and the failure paths stub
the script's IO seam (the git index, the installed distributions, the repo
root) with synthetic fixtures.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _load_script(name: str):
    """Load one gate script as a module (they are plain scripts, not packages)."""
    path = _REPO_ROOT / "scripts" / "ci" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --- check_docs_pairs.py ---


def test_docs_pairs_pass_on_the_real_repo() -> None:
    assert _load_script("check_docs_pairs.py").main() == 0


def test_docs_pairs_flags_and_clears_an_unpaired_file(tmp_path: Path, monkeypatch) -> None:
    mod = _load_script("check_docs_pairs.py")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("english", encoding="utf-8")
    assert mod.main() == 1
    (docs / "guide.zh.md").write_text("chinese", encoding="utf-8")
    assert mod.main() == 0


# --- check_case_collisions.py ---


def test_case_collisions_pass_on_the_real_repo() -> None:
    assert _load_script("check_case_collisions.py").main() == 0


def test_case_collisions_flags_a_colliding_pair(monkeypatch) -> None:
    mod = _load_script("check_case_collisions.py")
    monkeypatch.setattr(mod, "tracked_paths", lambda: ["src/Mod.py", "src/mod.py", "src/other.py"])
    assert mod.main() == 1


def test_case_collisions_accept_distinct_paths(monkeypatch) -> None:
    mod = _load_script("check_case_collisions.py")
    monkeypatch.setattr(mod, "tracked_paths", lambda: ["src/a.py", "src/b.py"])
    assert mod.main() == 0


# --- check_editorconfig.py ---


def test_editorconfig_passes_on_the_real_repo() -> None:
    assert _load_script("check_editorconfig.py").main() == 0


def test_editorconfig_flags_contract_violations(monkeypatch) -> None:
    mod = _load_script("check_editorconfig.py")
    clean_sha = "a" * 40
    dirty_sha = "b" * 40
    monkeypatch.setattr(
        mod,
        "index_blobs",
        lambda: [(clean_sha, "src/clean.py"), (dirty_sha, "src/dirty.py")],
    )
    monkeypatch.setattr(
        mod,
        "read_blobs",
        lambda shas: {
            clean_sha: b"def main() -> None:\n    return None\n",
            # CRLF, tab indentation, trailing whitespace, no final newline.
            dirty_sha: b"def f():\r\n\tx = 1  ",
        },
    )
    assert mod.main() == 1


def test_editorconfig_accepts_clean_blobs(monkeypatch) -> None:
    mod = _load_script("check_editorconfig.py")
    sha = "a" * 40
    monkeypatch.setattr(mod, "index_blobs", lambda: [(sha, "src/clean.py")])
    monkeypatch.setattr(mod, "read_blobs", lambda shas: {sha: b"x = 1\n"})
    assert mod.main() == 0


# --- check_python_deps_policy.py ---


def test_canonical_normalizes_pep503_names() -> None:
    mod = _load_script("check_python_deps_policy.py")
    assert mod.canonical("Foo._-Bar") == "foo-bar"


def test_deps_policy_flags_a_banned_distribution(monkeypatch) -> None:
    mod = _load_script("check_python_deps_policy.py")
    policy = json.loads(
        (_REPO_ROOT / "scripts" / "ci" / "dependency-policy.json").read_text(encoding="utf-8")
    )
    banned_name = next(iter(policy.get("pip", {})))
    fake = [SimpleNamespace(metadata={"Name": banned_name.upper()}, version="9.9.9")]
    monkeypatch.setattr(mod.metadata, "distributions", lambda: iter(fake))
    assert mod.main() == 1


def test_deps_policy_passes_a_clean_environment(monkeypatch) -> None:
    mod = _load_script("check_python_deps_policy.py")
    fake = [SimpleNamespace(metadata={"Name": "safe-pkg"}, version="1.0.0")]
    monkeypatch.setattr(mod.metadata, "distributions", lambda: iter(fake))
    assert mod.main() == 0
