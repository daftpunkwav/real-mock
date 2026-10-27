"""Tests for the repo-level CI gate scripts under ``scripts/ci/``.

The gates were only exercised by the pipeline they guard, so their behaviour
was known only through failure output. They run inside the backend suite now:
each script is loaded by file path (they live outside the backend package),
the pass paths run against the real repository, and the failure paths stub
the script's IO seam (the git index, the installed distributions, the repo
root, the manifest and the lock) with synthetic fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import tomllib
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


# --- check_python_lock_sync.py ---

# A synthetic manifest/lock pair. The manifest declares `Beta._-Pkg` while the
# lock pins `beta-pkg`, so a clean run also proves both sides are compared
# PEP 503 normalized; `gamma` carries no specifier, so only its presence is
# required of it. The lock marks every pin as a direct requirement through its
# `# via` block, which is how uv records the project itself.
_SYNTHETIC_MANIFEST = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "alpha>=1.0,<2",
    "Beta._-Pkg==3.0.0",
]

[project.optional-dependencies]
dev = ["gamma"]
"""

_SYNTHETIC_LOCK = """\
alpha==1.5.0 \\
    --hash=sha256:1111
    # via
    #   demo (pyproject.toml)
beta-pkg==3.0.0 \\
    --hash=sha256:2222
    # via
    #   demo (pyproject.toml)
gamma==7.7.7 \\
    --hash=sha256:3333
    # via
    #   demo (pyproject.toml)
"""

# The manifest declares a distribution the lock does not pin.
_MANIFEST_WITH_MISSING = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "alpha>=1.0,<2",
    "missing-pkg==1.0.0",
]
"""

# The manifest allows `alpha` below 2.0, the lock pins it above.
_MANIFEST_WITH_RANGE = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = ["alpha>=1.0,<2"]
"""

_LOCK_OUT_OF_RANGE = """\
alpha==2.5.0 \\
    --hash=sha256:1111
    # via demo
"""

# The same distribution pinned twice: the lock must pin each one exactly once.
_LOCK_WITH_DUPLICATE = """\
alpha==1.5.0 \\
    --hash=sha256:1111
alpha==1.6.0 \\
    --hash=sha256:2222
"""

# A distribution the lock marks as a direct requirement of the project, but
# which the manifest no longer declares.
_LOCK_WITH_ORPHAN = """\
alpha==1.5.0 \\
    --hash=sha256:1111
    # via
    #   demo (pyproject.toml)
orphan==9.9.9 \\
    --hash=sha256:4444
    # via
    #   demo (pyproject.toml)
"""

# A lock that carries no marker at all: the reverse check must not guess and
# must report nothing, even for a pin the manifest does not declare.
_LOCK_WITHOUT_MARKER = """\
alpha==1.5.0 \\
    --hash=sha256:1111
    # via
    #   some-other-package
extra==1.2.3 \\
    --hash=sha256:5555
    # via
    #   some-other-package
"""


def _stub_lock_sync(mod, monkeypatch, tmp_path: Path, manifest: str, lock: str) -> None:
    """Point the gate at a synthetic manifest/lock pair instead of the real ones."""
    manifest_path = tmp_path / "pyproject.toml"
    manifest_path.write_text(manifest, encoding="utf-8")
    lock_path = tmp_path / "requirements-ci.lock"
    lock_path.write_text(lock, encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "MANIFEST", manifest_path)
    monkeypatch.setattr(mod, "LOCK", lock_path)


def test_python_lock_sync_passes_on_the_real_repo() -> None:
    assert _load_script("check_python_lock_sync.py").main() == 0


def test_lock_sync_canonical_normalizes_pep503_names() -> None:
    mod = _load_script("check_python_lock_sync.py")
    assert mod.canonical("Foo._-Bar") == "foo-bar"


def test_lock_sync_reads_the_pins_and_skips_the_hash_and_comment_lines() -> None:
    mod = _load_script("check_python_lock_sync.py")
    assert mod.locked_versions(_SYNTHETIC_LOCK) == {
        "alpha": "1.5.0",
        "beta-pkg": "3.0.0",
        "gamma": "7.7.7",
    }


def test_python_lock_sync_accepts_a_clean_synthetic_pair(tmp_path: Path, monkeypatch) -> None:
    mod = _load_script("check_python_lock_sync.py")
    _stub_lock_sync(mod, monkeypatch, tmp_path, _SYNTHETIC_MANIFEST, _SYNTHETIC_LOCK)
    assert mod.main() == 0


def test_python_lock_sync_flags_a_requirement_missing_from_the_lock(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    mod = _load_script("check_python_lock_sync.py")
    _stub_lock_sync(mod, monkeypatch, tmp_path, _MANIFEST_WITH_MISSING, _SYNTHETIC_LOCK)
    assert mod.main() == 1
    assert "missing-pkg" in capsys.readouterr().out


def test_python_lock_sync_flags_a_version_outside_the_manifest_range(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    mod = _load_script("check_python_lock_sync.py")
    _stub_lock_sync(mod, monkeypatch, tmp_path, _MANIFEST_WITH_RANGE, _LOCK_OUT_OF_RANGE)
    assert mod.main() == 1
    assert "locked at 2.5.0" in capsys.readouterr().out


def test_python_lock_sync_flags_a_distribution_pinned_twice(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    mod = _load_script("check_python_lock_sync.py")
    _stub_lock_sync(mod, monkeypatch, tmp_path, _MANIFEST_WITH_RANGE, _LOCK_WITH_DUPLICATE)
    assert mod.main() == 1
    assert "pinned more than once" in capsys.readouterr().out


def test_python_lock_sync_flags_a_direct_requirement_no_longer_declared(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    mod = _load_script("check_python_lock_sync.py")
    _stub_lock_sync(mod, monkeypatch, tmp_path, _MANIFEST_WITH_RANGE, _LOCK_WITH_ORPHAN)
    assert mod.main() == 1
    assert "orphan" in capsys.readouterr().out


def test_python_lock_sync_ignores_a_lock_without_the_direct_marker(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _load_script("check_python_lock_sync.py")
    _stub_lock_sync(mod, monkeypatch, tmp_path, _MANIFEST_WITH_RANGE, _LOCK_WITHOUT_MARKER)
    assert mod.main() == 0


def test_lock_sync_marker_set_matches_the_manifest_requirements() -> None:
    mod = _load_script("check_python_lock_sync.py")
    manifest = tomllib.loads(mod.MANIFEST.read_text(encoding="utf-8"))
    lock_text = mod.LOCK.read_text(encoding="utf-8")
    marker = mod.project_marker(manifest, mod.MANIFEST, mod.ROOT)
    direct = mod.direct_requirements(lock_text, marker)
    # Only the requirements that apply to the lock target can be marked direct
    # in a lock for that target.
    declared = {mod.canonical(r.name) for r in mod.locked_requirements(manifest)}
    assert set(direct) == declared


# A requirement whose environment marker excludes the lock target (Linux) is
# legitimately absent from the lock; one whose marker applies to it is not.
_MANIFEST_WITH_MARKERS = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "windows-only; sys_platform == 'win32'",
    "posix-only; sys_platform == 'linux'",
]
"""

_LOCK_WITH_POSIX_ONLY = """\
posix-only==1.0.0 \\
    --hash=sha256:1111
    # via
    #   demo (pyproject.toml)
"""

# The same requirement, moved off the lock target: the pin is now stale, and
# the inactive requirement must not justify it.
_MANIFEST_WITH_INACTIVE_REQUIREMENT = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = ["posix-only; sys_platform == 'win32'"]
"""


# A non-dev extra is not compiled into the lock, so it is not compared.
_MANIFEST_WITH_OTHER_EXTRA = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = ["alpha>=1.0,<2"]

[project.optional-dependencies]
docs = ["docs-only==1.0.0"]
dev = ["gamma==7.7.7"]
"""

_LOCK_FOR_DEV_EXTRA = """\
alpha==1.5.0 \\
    --hash=sha256:1111
    # via
    #   demo (pyproject.toml)
gamma==7.7.7 \\
    --hash=sha256:3333
    # via
    #   demo (pyproject.toml)
"""


def test_python_lock_sync_skips_a_requirement_whose_marker_excludes_the_lock(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _load_script("check_python_lock_sync.py")
    _stub_lock_sync(mod, monkeypatch, tmp_path, _MANIFEST_WITH_MARKERS, _LOCK_WITH_POSIX_ONLY)
    assert mod.main() == 0


def test_python_lock_sync_flags_a_marker_requirement_the_lock_should_carry(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    mod = _load_script("check_python_lock_sync.py")
    # The lock pins the Windows-only requirement instead of the Linux one, so
    # the applicable requirement is missing and the inapplicable one is orphaned.
    lock = _LOCK_WITH_POSIX_ONLY.replace("posix-only", "windows-only")
    _stub_lock_sync(mod, monkeypatch, tmp_path, _MANIFEST_WITH_MARKERS, lock)
    assert mod.main() == 1
    assert "posix-only" in capsys.readouterr().out


def test_python_lock_sync_flags_a_pin_the_inactive_requirement_no_longer_justifies(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    mod = _load_script("check_python_lock_sync.py")
    # The requirement moved off the lock target but the lock still pins it, so
    # the pin is stale: an inactive requirement must not mask it.
    _stub_lock_sync(
        mod,
        monkeypatch,
        tmp_path,
        _MANIFEST_WITH_INACTIVE_REQUIREMENT,
        _LOCK_WITH_POSIX_ONLY,
    )
    assert mod.main() == 1
    assert "posix-only" in capsys.readouterr().out


def test_python_lock_sync_compares_only_the_dev_extra(tmp_path: Path, monkeypatch) -> None:
    mod = _load_script("check_python_lock_sync.py")
    # `docs-only` is declared but not compiled into the lock, and `gamma` is
    # both: only the requirements the lock covers are compared.
    _stub_lock_sync(mod, monkeypatch, tmp_path, _MANIFEST_WITH_OTHER_EXTRA, _LOCK_FOR_DEV_EXTRA)
    assert mod.main() == 0
