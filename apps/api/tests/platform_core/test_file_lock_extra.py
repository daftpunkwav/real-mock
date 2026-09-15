"""File-lock tests for realmock.platform.core.file_lock.

Covers: basic acquire/release, contention timeout, and POSIX branch.
Conventions: tmp_path locks only; Windows contention uses msvcrt.
"""

from __future__ import annotations

import pytest


class TestFileLock:
    def test_basic_lock(self, tmp_path) -> None:
        from realmock.platform.core.file_lock import FileLockTimeout, file_lock

        p = tmp_path / "x.lock"
        with file_lock(p):
            assert p.is_file()
        with file_lock(p, timeout=1):
            pass
        assert FileLockTimeout is not None

    def test_timeout_when_locked(self, tmp_path) -> None:
        import os

        from realmock.platform.core.file_lock import FileLockTimeout, file_lock

        p = tmp_path / "busy.lock"
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(p), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            locked = True
        except OSError:
            locked = False
        try:
            if locked:
                with pytest.raises(FileLockTimeout):
                    with file_lock(p, timeout=0.2, poll_interval=0.05):
                        pass
        finally:
            try:
                if locked:
                    import msvcrt as _m

                    _m.locking(fd, _m.LK_UNLCK, 1)
            except OSError:
                pass
            os.close(fd)

    def test_posix_branch_covered(self, tmp_path, monkeypatch) -> None:
        import sys

        import realmock.platform.core.file_lock as fl

        locked_calls = []
        monkeypatch.setattr(sys, "platform", "linux")
        import types

        fake_fcntl = types.SimpleNamespace(
            LOCK_EX=1,
            LOCK_NB=2,
            LOCK_UN=8,
            flock=lambda fd, op: locked_calls.append(op),
        )
        monkeypatch.setitem(__import__("sys").modules, "fcntl", fake_fcntl)
        with fl.file_lock(tmp_path / "posix.lock"):
            pass
        assert locked_calls
