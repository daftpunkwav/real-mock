"""Python lock/manifest sync check: fail when the CI lock drifts from the manifest.

The backend job installs `apps/api/requirements-ci.lock` with `--require-hashes`,
so the gate exercises the pinned tree rather than the manifest. A dependency
added, dropped or re-ranged in `apps/api/pyproject.toml` without regenerating
the lock leaves CI installing the old tree, and the manifest and the installed
tree disagree silently. This gate compares the manifest's direct requirements
with the pins in the lock and fails loudly on any drift.

The comparison covers exactly what the lock is compiled from: `project.
dependencies` plus the `dev` extra, for Linux on CPython 3.14. A requirement
from another extra, or one whose environment marker excludes that target, is
legitimately absent from the lock and is not reported.

Both directions are checked: a manifest requirement must be locked at a version
its specifier allows, and a distribution the lock marks as a direct requirement
of the project must still be declared in the manifest, so a dependency that was
dropped is caught as well.

The lock's pin lines do not record which extras a requirement asked for, so the
lock also carries a manifest snapshot — the exact requirement strings the lock
was compiled from, appended by `scripts/ci/regenerate_python_lock.py`. The gate
requires the snapshot to match the live manifest exactly. That is what catches
an extras change (`uvicorn[standard]` to `uvicorn`): it changes no resolved
version, so only the snapshot comparison can see it. A lock without the block
fails the gate, because its provenance is then unknown.

Names are compared PEP 503 normalized (lowercase, runs of -/_/. collapsed to
one dash) so both sides agree on spelling, and the version ranges are matched
with `packaging` rather than a hand-rolled comparison.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# `tomllib` is standard library since 3.11, but ruff's default target for this
# directory is still py310, which classifies it as third-party.
import tomllib
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "apps" / "api" / "pyproject.toml"
LOCK = ROOT / "apps" / "api" / "requirements-ci.lock"

# The extra the lock is compiled from, and the target it is compiled for. Both
# mirror the compile command recorded in the lock header.
LOCKED_EXTRA = "dev"
LOCK_ENVIRONMENT = {
    "sys_platform": "linux",
    "platform_system": "Linux",
    "os_name": "posix",
    "platform_machine": "x86_64",
    "python_version": "3.14",
    "python_full_version": "3.14.0",
}

# A pin line is `name==version`, optionally continued by a trailing backslash
# into its `--hash=` lines. Hash and `# via` lines never start at column 0, so
# anchoring the pattern there keeps them out of the result.
_PIN = re.compile(r"^([A-Za-z0-9._-]+)==([^\s\\]+)")

# The manifest snapshot the lock ends with. `regenerate_python_lock.py` appends
# it after compiling; the entry lines carry one manifest requirement string
# each. Explanations inside the block use a single `# ` comment prefix so they
# can never be mistaken for `#   ` entries.
SNAPSHOT_BEGIN = "# --- manifest snapshot ---"
SNAPSHOT_END = "# --- end manifest snapshot ---"
SNAPSHOT_ENTRY_PREFIX = "#   "


def canonical(name: str) -> str:
    """PEP 503 normalization: lowercase, runs of -/_/. collapsed to one dash."""
    return str(canonicalize_name(name))


def _lock_entries(lock_text: str) -> list[tuple[str, str, list[str]]]:
    """Split the lock into (canonical name, version, continuation lines) entries.

    A `name==version` line opens an entry; the indented lines that follow it
    are its `--hash=` lines and its `# via` block.
    """
    entries: list[tuple[str, str, list[str]]] = []
    for line in lock_text.splitlines():
        match = _PIN.match(line)
        if match is not None:
            entries.append((canonical(match.group(1)), match.group(2), []))
        elif entries and line[:1].isspace():
            entries[-1][2].append(line)
    return entries


def locked_pins(lock_text: str) -> list[tuple[str, str]]:
    """Return every pin in the lock as (canonical name, version), in file order.

    The `--hash=` continuation lines and the `# via` comments are skipped: only
    the `name==version` line of each entry carries the pin.
    """
    return [(name, version) for name, version, _ in _lock_entries(lock_text)]


def locked_versions(lock_text: str) -> dict[str, str]:
    """Map every canonical distribution name in the lock to its pinned version."""
    return dict(locked_pins(lock_text))


def duplicate_pins(lock_text: str) -> dict[str, list[str]]:
    """Return the distributions the lock pins more than once, with their versions.

    The lock must pin each distribution exactly once; a repeated pin means the
    file was edited by hand and pip would resolve it unpredictably.
    """
    grouped: dict[str, list[str]] = {}
    for name, version in locked_pins(lock_text):
        grouped.setdefault(name, []).append(version)
    return {name: versions for name, versions in grouped.items() if len(versions) > 1}


def manifest_requirements(manifest: dict[str, Any]) -> list[Requirement]:
    """Return every requirement declared for the lock's scope.

    Those are `project.dependencies` plus the entries of the extra the lock is
    compiled with; an extra that is not compiled into the lock is not part of
    the comparison. Environment markers are not evaluated here.
    """
    return [Requirement(entry) for entry in expected_snapshot(manifest)]


def expected_snapshot(manifest: dict[str, Any]) -> list[str]:
    """Return the raw manifest requirement strings the lock is compiled from.

    Same enumeration as :func:`manifest_requirements`, but the strings stay
    unparsed and in manifest order — the snapshot must also record the extras
    a requirement asks for, which :class:`Requirement` drops from its repr.
    """
    project = manifest.get("project", {})
    entries: list[str] = list(project.get("dependencies", []))
    entries.extend(project.get("optional-dependencies", {}).get(LOCKED_EXTRA, []))
    return entries


def snapshot_block(entries: list[str]) -> str:
    """Render the manifest-snapshot block for the given requirement strings."""
    lines = [
        SNAPSHOT_BEGIN,
        "# The pins above were compiled from exactly these manifest requirement",
        "# strings (project.dependencies plus the dev extra, in manifest order).",
        "# The lock does not record which extras a requirement asks for, so this",
        "# block is the record of it; refresh it whenever the manifest changes.",
    ]
    lines.extend(f"{SNAPSHOT_ENTRY_PREFIX}{entry}" for entry in entries)
    lines.append(SNAPSHOT_END)
    return "\n".join(lines)


def with_snapshot(lock_text: str, entries: list[str]) -> str:
    """Return lock_text with the manifest-snapshot block replaced or appended.

    The block is written at the end, so replacing drops everything from the
    first begin marker on — that also recovers an unterminated block left by
    an interrupted edit.
    """
    lines = lock_text.splitlines()
    if SNAPSHOT_BEGIN in lines:
        lines = lines[: lines.index(SNAPSHOT_BEGIN)]
    text = "\n".join(lines).rstrip("\n")
    return f"{text}\n\n{snapshot_block(entries)}\n"


def snapshot_entries(lock_text: str) -> list[str] | None:
    """Extract the manifest snapshot recorded in the lock, or None.

    None means the block is missing or unterminated, so the lock's provenance
    is unknown and the caller must fail rather than guess.
    """
    lines = lock_text.splitlines()
    try:
        begin = lines.index(SNAPSHOT_BEGIN)
    except ValueError:
        return None
    entries: list[str] = []
    for line in lines[begin + 1 :]:
        if line == SNAPSHOT_END:
            return entries
        if line.startswith(SNAPSHOT_ENTRY_PREFIX):
            entries.append(line[len(SNAPSHOT_ENTRY_PREFIX) :])
    return None


def snapshot_violations(manifest: dict[str, Any], lock_text: str) -> list[str]:
    """Return one message per mismatch between the manifest and the lock's snapshot."""
    expected = expected_snapshot(manifest)
    recorded = snapshot_entries(lock_text)
    if recorded is None:
        return [
            (
                "the lock does not record which manifest requirements it was compiled "
                "from (missing or malformed manifest-snapshot block); regenerate it "
                "with scripts/ci/regenerate_python_lock.py"
            )
        ]
    violations = [
        f"snapshot: {entry} is declared in the manifest but not recorded in the lock"
        for entry in expected
        if entry not in set(recorded)
    ]
    violations += [
        f"snapshot: {entry} is recorded in the lock but not declared in the manifest"
        for entry in recorded
        if entry not in set(expected)
    ]
    if not violations and recorded != expected:
        violations.append(
            "snapshot: the manifest requirements changed order; regenerate the lock"
        )
    return violations


def _applies(requirement: Requirement) -> bool:
    """Whether the requirement applies to the target the lock is compiled for."""
    return requirement.marker is None or requirement.marker.evaluate(LOCK_ENVIRONMENT)


def locked_requirements(manifest: dict[str, Any]) -> list[Requirement]:
    """Return the declared requirements that apply to the lock target.

    A requirement whose environment marker excludes the target the lock is
    compiled for is legitimately absent from the lock, so it takes no part in
    either direction of the comparison.
    """
    return [
        requirement
        for requirement in manifest_requirements(manifest)
        if _applies(requirement)
    ]


def project_marker(manifest: dict[str, Any], manifest_path: Path, root: Path) -> str:
    """Return the marker uv writes for a direct requirement of the project.

    uv records the project itself in the `# via` block of every distribution
    the project requires directly, as `name (path/to/pyproject.toml)`. An empty
    marker means the project name is unknown, and the caller must then check
    nothing rather than guess.
    """
    project_name = manifest.get("project", {}).get("name", "")
    if not project_name:
        return ""
    try:
        relative = manifest_path.relative_to(root).as_posix()
    except ValueError:
        # The manifest is not under the repository root, so the marker cannot be
        # derived; the caller then checks nothing rather than guess.
        return ""
    return f"{project_name} ({relative})"


def _marks_direct(lines: list[str], marker: str) -> bool:
    """Whether an entry's comment lines carry the direct-requirement marker."""
    return any(line.lstrip().startswith("#") and marker in line for line in lines)


def direct_requirements(lock_text: str, marker: str) -> list[str]:
    """Return the distributions the lock marks as direct requirements.

    A lock that carries no such marker was not produced from this manifest, or
    the format changed; the result is then empty and nothing is guessed.
    """
    if not marker:
        return []
    return [
        name
        for name, _version, lines in _lock_entries(lock_text)
        if _marks_direct(lines, marker)
    ]


def _duplicate_pin_violations(lock_text: str) -> list[str]:
    """Return one message per distribution the lock pins more than once."""
    return [
        f"{name}: pinned more than once in the lock ({', '.join(pinned)})"
        for name, pinned in duplicate_pins(lock_text).items()
    ]


def _orphan_violations(lock_text: str, marker: str, declared: set[str]) -> list[str]:
    """Return one message per direct requirement the manifest no longer declares."""
    return [
        f"{name}: locked as a direct requirement, no longer in the manifest"
        for name in direct_requirements(lock_text, marker)
        if name not in declared
    ]


def _requirement_violations(
    requirements: list[Requirement], versions: dict[str, str]
) -> list[str]:
    """Return one message per requirement the lock does not satisfy."""
    return [
        message
        for message in (
            _requirement_message(requirement, versions) for requirement in requirements
        )
        if message is not None
    ]


def _requirement_message(
    requirement: Requirement, versions: dict[str, str]
) -> str | None:
    """Return the drift of one requirement, or None when the lock satisfies it."""
    name = canonical(requirement.name)
    if name not in versions:
        return f"{name}: declared in the manifest but not locked"
    locked = versions[name]
    specifier = requirement.specifier
    if not specifier:
        # An unpinned requirement accepts any version; presence is enough.
        return None
    try:
        satisfied = specifier.contains(locked)
    except InvalidVersion:
        return f"{name}: locked at {locked}, which is not a valid version"
    if not satisfied:
        return f"{name}: locked at {locked}, the manifest allows {specifier}"
    return None


def sync_violations(manifest: dict[str, Any], lock_text: str, marker: str) -> list[str]:
    """Return one message per drift between the manifest requirements and the lock."""
    requirements = locked_requirements(manifest)
    # Only the requirements that apply to the lock target can justify a pin, so
    # an inactive one must not mask a pin the lock should have dropped.
    declared = {canonical(requirement.name) for requirement in requirements}

    violations = _duplicate_pin_violations(lock_text)
    violations += _orphan_violations(lock_text, marker, declared)
    violations += _requirement_violations(requirements, locked_versions(lock_text))
    violations += snapshot_violations(manifest, lock_text)
    return violations


def main() -> int:
    """Fail when the lock and the manifest disagree; print every drift found."""
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    lock_text = LOCK.read_text(encoding="utf-8")
    marker = project_marker(manifest, MANIFEST, ROOT)

    violations = sync_violations(manifest, lock_text, marker)
    if violations:
        print("python lock is out of sync with the manifest:")
        for violation in violations:
            print(f"  - {violation}")
        print("regenerate the lock with scripts/ci/regenerate_python_lock.py")
        return 1

    requirement_count = len(locked_requirements(manifest))
    locked_count = len(locked_versions(lock_text))
    summary = (
        "python lock in sync with the manifest "
        f"({requirement_count} manifest requirements, "
        f"{locked_count} locked distributions)"
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
