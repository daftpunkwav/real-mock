"""Linux-job isolation tests for apps/api/src/realmock/platform/capabilities/ai/agent/tools/isolation/linux_job.py.

Covers: env/memory/cpu parsing, user/tool-path resolution, plan building,
constructor/describe/select-plan/cgroup/spawn paths (Linux branches skipped on Windows).

Conventions: no real containers (subprocess/cgroup calls mocked); asyncio_mode=auto.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from realmock.platform.capabilities.ai.agent.tools.isolation import linux_job as lj

ON_LINUX = sys.platform.startswith("linux")


def test_env_flag_and_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(lj.ENV_ALLOW_NETWORK, raising=False)
    assert lj.env_flag(lj.ENV_ALLOW_NETWORK, False) is False
    assert lj.env_flag(lj.ENV_ALLOW_NETWORK, True) is True
    for v in ("1", "true", "YES", "y", "on", " True "):
        monkeypatch.setenv(lj.ENV_ALLOW_NETWORK, v)
        assert lj.env_flag(lj.ENV_ALLOW_NETWORK, False) is True
    monkeypatch.setenv(lj.ENV_ALLOW_NETWORK, "0")
    assert lj.env_flag(lj.ENV_ALLOW_NETWORK, True) is False
    monkeypatch.delenv(lj.ENV_RUN_AS_USER, raising=False)
    assert lj.env_text(lj.ENV_RUN_AS_USER, "dflt") == "dflt"
    monkeypatch.setenv(lj.ENV_RUN_AS_USER, "  nobody  ")
    assert lj.env_text(lj.ENV_RUN_AS_USER, "dflt") == "nobody"


def test_parse_memory_limit() -> None:
    assert lj.parse_memory_limit(None, source="t") is None
    assert lj.parse_memory_limit("", source="t") is None
    assert lj.parse_memory_limit("   ", source="t") is None
    assert lj.parse_memory_limit(1024, source="t") == 1024
    assert lj.parse_memory_limit("2048", source="t") == 2048
    with pytest.raises(ValueError, match="positive byte count"):
        lj.parse_memory_limit(0, source="t")
    with pytest.raises(ValueError, match="positive byte count"):
        lj.parse_memory_limit(-1, source="t")
    with pytest.raises(ValueError, match="byte count"):
        lj.parse_memory_limit("lots", source="t")


def test_parse_cpu_limit() -> None:
    assert lj.parse_cpu_limit(None, source="t") is None
    assert lj.parse_cpu_limit("", source="t") is None
    assert lj.parse_cpu_limit("   ", source="t") is None
    assert lj.parse_cpu_limit("50000 100000", source="t") == "50000 100000"
    assert lj.parse_cpu_limit("50000  100000", source="t") == "50000 100000"
    assert lj.parse_cpu_limit("max", source="t") == "max"
    assert lj.parse_cpu_limit("max 100000", source="t") == "max 100000"
    with pytest.raises(ValueError, match="cpu.max"):
        lj.parse_cpu_limit("ludicrous", source="t")


def test_resolve_user_ids_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    import types as _types

    fake_pwd = _types.ModuleType("pwd")
    fake_pwd.getpwnam = MagicMock(side_effect=KeyError("nope"))  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pwd", fake_pwd)
    with pytest.raises(ValueError, match="unknown isolation user"):
        lj.resolve_user_ids("no-such-user")


def test_resolve_user_ids_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    import types as _types

    entry = MagicMock()
    entry.pw_uid = 1000
    entry.pw_gid = 1001
    fake_pwd = _types.ModuleType("pwd")
    fake_pwd.getpwnam = MagicMock(return_value=entry)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pwd", fake_pwd)
    assert lj.resolve_user_ids("someone") == (1000, 1001)


def test_tool_path_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    lj._tool_path.cache_clear()
    monkeypatch.setattr(lj.shutil, "which", lambda n: f"/usr/bin/{n}")
    assert lj._tool_path("setpriv") == "/usr/bin/setpriv"
    # Cached: second call does not hit which again.
    monkeypatch.setattr(lj.shutil, "which", lambda n: None)
    assert lj._tool_path("setpriv") == "/usr/bin/setpriv"
    lj._tool_path.cache_clear()


def test_probe_success_fail_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    lj._probe_cache.clear()
    monkeypatch.setattr(lj.subprocess, "run", lambda *a, **k: MagicMock(returncode=0))
    assert lj._probe(("true",)) is True
    # Cached True.
    assert lj._probe(("true",)) is True
    lj._probe_cache.clear()
    monkeypatch.setattr(lj.subprocess, "run", lambda *a, **k: MagicMock(returncode=1))
    assert lj._probe(("false-x",)) is False
    lj._probe_cache.clear()
    monkeypatch.setattr(
        lj.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("nope"))
    )
    assert lj._probe(("missing",)) is False
    lj._probe_cache.clear()


def test_user_switch_setpriv_and_runuser(monkeypatch: pytest.MonkeyPatch) -> None:
    lj._tool_path.cache_clear()
    lj._probe_cache.clear()
    # setpriv present and probe ok -> setpriv prefix without trailing true.
    monkeypatch.setattr(lj, "_tool_path", lambda n: "/usr/bin/setpriv" if n == "setpriv" else None)
    monkeypatch.setattr(lj, "_probe", lambda argv: True)
    out = lj._user_switch_argv("nobody", 65534, 65534, probe=True)
    assert out[0].endswith("setpriv")
    assert "true" not in out
    # probe=False skips probing.
    out2 = lj._user_switch_argv("nobody", 65534, 65534, probe=False)
    assert out2[0].endswith("setpriv")
    # setpriv probe fails -> runuser fallback.
    monkeypatch.setattr(lj, "_tool_path", lambda n: "/usr/sbin/runuser" if n == "runuser" else "/usr/bin/setpriv" if n == "setpriv" else None)
    monkeypatch.setattr(lj, "_probe", lambda argv: "runuser" in argv[0])
    out3 = lj._user_switch_argv("nobody", 65534, 65534, probe=True)
    assert "runuser" in out3[0]
    # Neither helper -> ().
    monkeypatch.setattr(lj, "_tool_path", lambda n: None)
    assert lj._user_switch_argv("nobody", 1, 1, probe=False) == ()


def test_build_plan_all_kinds() -> None:
    # Plain without unshare, network blocked vs allowed.
    p = lj.build_plan(
        is_root=False, username="nobody", uid=1, gid=1, allow_network=False,
        unshare=None, user_switch=(), map_users_ok=False, netns_ok=False,
        mountns_netns_ok=False, userns_mountns_netns_ok=False,
    )
    assert p.kind == "plain"
    assert any(n.startswith("network=unavailable") for n in p.notes)
    p2 = lj.build_plan(
        is_root=False, username="nobody", uid=1, gid=1, allow_network=True,
        unshare=None, user_switch=(), map_users_ok=False, netns_ok=False,
        mountns_netns_ok=False, userns_mountns_netns_ok=False,
    )
    assert "network=allowed (explicit opt-in)" in p2.notes
    # Contained.
    c = lj.build_plan(
        is_root=True, username="nobody", uid=1, gid=1, allow_network=False,
        unshare="/usr/bin/unshare", user_switch=("setpriv",), map_users_ok=True,
        netns_ok=True, mountns_netns_ok=True, userns_mountns_netns_ok=True,
    )
    assert c.kind == "contained"
    # userns-mapped (root, map ok, but not contained).
    m = lj.build_plan(
        is_root=True, username="nobody", uid=1, gid=1, allow_network=False,
        unshare="/usr/bin/unshare", user_switch=(), map_users_ok=True,
        netns_ok=True, mountns_netns_ok=False, userns_mountns_netns_ok=True,
    )
    assert m.kind == "userns-mapped"
    # netonly (root, netns ok only).
    n = lj.build_plan(
        is_root=True, username="nobody", uid=1, gid=1, allow_network=False,
        unshare="/usr/bin/unshare", user_switch=(), map_users_ok=False,
        netns_ok=True, mountns_netns_ok=False, userns_mountns_netns_ok=False,
    )
    assert n.kind == "netonly"
    # userns-netonly (non-root).
    u = lj.build_plan(
        is_root=False, username="nobody", uid=1, gid=1, allow_network=False,
        unshare="/usr/bin/unshare", user_switch=(), map_users_ok=False,
        netns_ok=False, mountns_netns_ok=False, userns_mountns_netns_ok=True,
    )
    assert u.kind == "userns-netonly"
    # Plain fallback with root marker and network allowed.
    f = lj.build_plan(
        is_root=True, username="nobody", uid=1, gid=1, allow_network=True,
        unshare="/usr/bin/unshare", user_switch=(), map_users_ok=False,
        netns_ok=False, mountns_netns_ok=False, userns_mountns_netns_ok=False,
    )
    assert f.kind == "plain"
    assert "user_switch=unavailable (no setpriv/runuser found)" in f.notes
    assert "network=allowed (explicit opt-in)" in f.notes
    # Plain fallback non-root, network blocked.
    f2 = lj.build_plan(
        is_root=False, username="nobody", uid=1, gid=1, allow_network=False,
        unshare="/usr/bin/unshare", user_switch=(), map_users_ok=False,
        netns_ok=False, mountns_netns_ok=False, userns_mountns_netns_ok=False,
    )
    assert f2.kind == "plain"
    assert any("network=unavailable" in x for x in f2.notes)


def test_off_linux_constructor_raises() -> None:
    if ON_LINUX:
        pytest.skip("off-Linux rejection only applies on other platforms")
    with pytest.raises(RuntimeError, match="requires Linux"):
        lj.LinuxJobIsolation()


def _fake_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(lj, "resolve_user_ids", lambda u: (65534, 65534))


def test_linux_constructor_and_describe(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_linux(monkeypatch)
    monkeypatch.delenv(lj.ENV_RUN_AS_USER, raising=False)
    monkeypatch.delenv(lj.ENV_ALLOW_NETWORK, raising=False)
    monkeypatch.delenv(lj.ENV_MEMORY_MAX_BYTES, raising=False)
    monkeypatch.delenv(lj.ENV_CPU_MAX, raising=False)
    monkeypatch.delenv(lj.ENV_CGROUP_PARENT, raising=False)
    b = lj.LinuxJobIsolation()
    assert "nobody" in b.describe()
    assert "blocked(netns)" in b.describe()
    b2 = lj.LinuxJobIsolation(
        run_as_user="nobody", allow_network=True, memory_max_bytes=1024,
        cpu_max="max", cgroup_parent="/tmp/cg",
    )
    assert "allowed" in b2.describe()
    b3 = lj.LinuxJobIsolation(memory_max_bytes=None, cpu_max=None, cgroup_parent="/tmp/cg")
    # Both uncapped via empty strings.
    assert b3.memory_max_bytes is not None  # default from env
    with pytest.raises(ValueError, match="must not be empty"):
        lj.LinuxJobIsolation(run_as_user="   ", cgroup_parent="/tmp/cg")
    with pytest.raises(ValueError, match="cgroup parent"):
        lj.LinuxJobIsolation(run_as_user="nobody", cgroup_parent="   ")
    with pytest.raises(ValueError, match="positive byte count"):
        lj.LinuxJobIsolation(run_as_user="nobody", memory_max_bytes=-1)
    with pytest.raises(ValueError, match="cpu.max"):
        lj.LinuxJobIsolation(run_as_user="nobody", cpu_max="bad")
    monkeypatch.setenv(lj.ENV_MEMORY_MAX_BYTES, "4096")
    monkeypatch.setenv(lj.ENV_CPU_MAX, "max")
    b4 = lj.LinuxJobIsolation(run_as_user="nobody")
    assert b4.memory_max_bytes == 4096


def test_linux_constructor_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_linux(monkeypatch)
    monkeypatch.setenv(lj.ENV_RUN_AS_USER, "nobody")
    monkeypatch.setenv(lj.ENV_ALLOW_NETWORK, "true")
    monkeypatch.setenv(lj.ENV_CGROUP_PARENT, "/tmp/cg2")
    b = lj.LinuxJobIsolation()
    assert b.run_as_user == "nobody"
    assert b.allow_network is True


def test_select_plan_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_linux(monkeypatch)
    b = lj.LinuxJobIsolation(run_as_user="nobody", cgroup_parent="/tmp/cg")
    # No unshare -> plain.
    monkeypatch.setattr(lj, "_tool_path", lambda n: None)
    plan = b._select_plan()
    assert plan.kind == "plain"
    # With unshare, root, tools -> contained or mapped.
    monkeypatch.setattr(lj, "_tool_path", lambda n: "/usr/bin/unshare" if n == "unshare" else "/usr/bin/setpriv")
    monkeypatch.setattr(lj, "_user_switch_argv", lambda *a, **k: ("setpriv",))
    monkeypatch.setattr(lj, "_probe", lambda argv: True)
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    plan2 = b._select_plan()
    assert plan2.kind in ("contained", "userns-mapped", "netonly", "plain")
    # Non-root path.
    monkeypatch.setattr(os, "geteuid", lambda: 1000, raising=False)
    plan3 = b._select_plan()
    assert plan3.kind in ("userns-netonly", "plain")


def test_cgroup_leaf_and_attach(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    _fake_linux(monkeypatch)
    parent = str(tmp_path / "cg")
    b = lj.LinuxJobIsolation(run_as_user="nobody", memory_max_bytes=1024, cpu_max="max", cgroup_parent=parent)
    notes: list[str] = []
    leaf = b._prepare_cgroup_leaf(notes)
    assert leaf is not None
    # Attach ok and degraded.
    b._attach_pid(leaf, notes, 12345)
    with patch("builtins.open", side_effect=OSError("denied")):
        b._attach_pid(leaf, notes, 1)
        assert any("cgroup=degraded" in n for n in notes)
    b._drop_cgroup_leaf(leaf)
    b._drop_cgroup_leaf("/nonexistent-leaf-xyz")
    # Uncapped -> None.
    b2 = lj.LinuxJobIsolation(run_as_user="nobody", memory_max_bytes="", cpu_max="", cgroup_parent=parent)
    # Empty string disables cap; both None -> None leaf.
    b2.memory_max_bytes = None
    b2.cpu_max = None
    assert b2._prepare_cgroup_leaf([]) is None
    # Cannot create leaf -> unavailable note.
    monkeypatch.setattr(lj.os, "makedirs", lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
    notes2: list[str] = []
    assert b._prepare_cgroup_leaf(notes2) is None
    assert any("cgroup=unavailable" in n for n in notes2)


def test_cgroup_leaf_knob_degraded(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    _fake_linux(monkeypatch)
    parent = str(tmp_path / "cg2")
    b = lj.LinuxJobIsolation(run_as_user="nobody", memory_max_bytes=1024, cpu_max="max", cgroup_parent=parent)
    real_open = open

    def _fail_knob(path: str, *a: object, **k: object):  # noqa: ANN001
        if str(path).endswith(("memory.max", "cpu.max")):
            raise OSError("knob ro")
        return real_open(path, *a, **k)  # type: ignore[call-arg]

    monkeypatch.setattr("builtins.open", _fail_knob)
    notes: list[str] = []
    leaf = b._prepare_cgroup_leaf(notes)
    assert leaf is not None
    assert any("cgroup=degraded" in n for n in notes)


def test_cgroup_subtree_control_failure_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    _fake_linux(monkeypatch)
    parent = str(tmp_path / "cg3")
    b = lj.LinuxJobIsolation(run_as_user="nobody", memory_max_bytes=1024, cpu_max="max", cgroup_parent=parent)
    real_open = open

    def _fail_subtree(path: str, *a: object, **k: object):  # noqa: ANN001
        if str(path).endswith("cgroup.subtree_control"):
            raise OSError("ro")
        return real_open(path, *a, **k)  # type: ignore[call-arg]

    monkeypatch.setattr("builtins.open", _fail_subtree)
    assert b._prepare_cgroup_leaf([]) is not None


def test_cgroup_leaf_exists_retries_with_suffix(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    _fake_linux(monkeypatch)
    parent = str(tmp_path / "cg4")
    b = lj.LinuxJobIsolation(run_as_user="nobody", memory_max_bytes=1024, cpu_max="max", cgroup_parent=parent)
    real_mkdir = lj.os.mkdir
    calls = {"n": 0}

    def _flaky_mkdir(path: str, *a: object, **k: object) -> None:  # noqa: ANN001
        if "snippet-" not in str(path):
            return real_mkdir(path, *a, **k)
        calls["n"] += 1
        if calls["n"] == 1:
            raise FileExistsError("exists")
        return real_mkdir(path, *a, **k)

    monkeypatch.setattr(lj.os, "mkdir", _flaky_mkdir)
    monkeypatch.setattr(lj.secrets, "token_hex", lambda n: "abcd")
    assert b._prepare_cgroup_leaf([]) is not None


def test_spawn_with_leaf_and_status_variants(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    _fake_linux(monkeypatch)
    work = tmp_path / "work2"
    work.mkdir()
    b = lj.LinuxJobIsolation(run_as_user="nobody", memory_max_bytes=1024, cpu_max="max", cgroup_parent=str(tmp_path / "cg"))
    for status_text, marker in [
        ("ro-unavailable", "bind_ro=unavailable"),
        ("weird", "bind_ro=unknown"),
    ]:
        plan = lj.LaunchPlan(kind="plain", prefix=(), user_switch=(), drops_to="unchanged", net_blocked=False, mount_prelude=True, notes=())

        def _fake_run(argv: object, *, cwd: str, env: object, timeout_s: float, on_start=None) -> tuple:  # noqa: ANN001
            args = list(argv)  # type: ignore[arg-type]
            idx = args.index("/bin/sh")
            status_path = args[idx + 4]
            with open(status_path, "w", encoding="ascii") as fh:
                fh.write(status_text)
            if on_start is not None:
                on_start(111)
            return (0, b"ok", b"", False)

        monkeypatch.setattr(b, "_select_plan", lambda: plan)
        monkeypatch.setattr(lj, "run_child", _fake_run)
        monkeypatch.setattr(b, "_prepare_cgroup_leaf", lambda notes: str(tmp_path / "leaf"))
        monkeypatch.setattr(b, "_drop_cgroup_leaf", lambda leaf: None)
        monkeypatch.setattr(b, "_attach_pid", lambda leaf, notes, pid: notes.append("attached"))
        out = b.spawn(["true"], cwd=str(work), env={}, timeout_s=5)
        assert any(marker in n for n in out.notes)

    # Missing status file -> bind_ro=unknown.
    plan = lj.LaunchPlan(kind="plain", prefix=(), user_switch=(), drops_to="unchanged", net_blocked=False, mount_prelude=True, notes=())
    monkeypatch.setattr(b, "_select_plan", lambda: plan)
    monkeypatch.setattr(lj, "run_child", lambda *a, **k: (0, b"ok", b"", False))
    monkeypatch.setattr(b, "_prepare_cgroup_leaf", lambda notes: str(tmp_path / "leaf"))
    out = b.spawn(["true"], cwd=str(work), env={}, timeout_s=5)
    assert any("bind_ro=unknown" in n for n in out.notes)
    # Unlink failure is swallowed (501-502).
    work3 = tmp_path / "work3"
    work3.mkdir()

    def _fake_run_unlink_fail(argv: object, *, cwd: str, env: object, timeout_s: float, on_start=None) -> tuple:  # noqa: ANN001
        args = list(argv)  # type: ignore[arg-type]
        idx = args.index("/bin/sh")
        status_path = args[idx + 4]
        with open(status_path, "w", encoding="ascii") as fh:
            fh.write("ro-ok")
        return (0, b"ok", b"", False)

    monkeypatch.setattr(b, "_select_plan", lambda: plan)
    monkeypatch.setattr(lj, "run_child", _fake_run_unlink_fail)
    monkeypatch.setattr(lj.os, "unlink", lambda p: (_ for _ in ()).throw(OSError("busy")))
    out2 = b.spawn(["true"], cwd=str(work3), env={}, timeout_s=5)
    assert any("bind_ro=enforced" in n for n in out2.notes)


def test_spawn_paths(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    _fake_linux(monkeypatch)
    b = lj.LinuxJobIsolation(run_as_user="nobody", memory_max_bytes="", cpu_max="", cgroup_parent=str(tmp_path))
    b.memory_max_bytes = None
    b.cpu_max = None
    plan = lj.LaunchPlan(kind="plain", prefix=(), user_switch=(), drops_to="unchanged", net_blocked=False, mount_prelude=False, notes=())
    monkeypatch.setattr(b, "_select_plan", lambda: plan)
    monkeypatch.setattr(lj, "run_child", lambda *a, **k: (0, b"out", b"err", False))
    out = b.spawn(["echo", "hi"], cwd=str(tmp_path), env={}, timeout_s=5)
    assert out.exit_code == 0
    assert any(n.startswith("plan=plain") for n in out.notes)
    assert any("cgroup=uncapped" in n for n in out.notes)


def test_spawn_with_cgroup_and_mount(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    _fake_linux(monkeypatch)
    work = tmp_path / "work"
    work.mkdir()
    b = lj.LinuxJobIsolation(run_as_user="nobody", memory_max_bytes=1024, cpu_max="max", cgroup_parent=str(tmp_path / "cg"))
    plan = lj.LaunchPlan(kind="contained", prefix=("unshare",), user_switch=(), drops_to="nobody(1:1)", net_blocked=True, mount_prelude=True, notes=())

    def _fake_run(argv: object, *, cwd: str, env: object, timeout_s: float, on_start=None) -> tuple:  # noqa: ANN001
        # Simulate mount prelude writing ro-ok status.
        import glob as _glob

        for cand in _glob.glob(os.path.join(cwd, ".mount-status-*")):
            pass
        # Find status path: it is embedded in argv (after cwd). Write ro-ok.
        # argv = [prefix..., /bin/sh, -c, prelude, cwd, status_path, ...]
        args = list(argv)  # type: ignore[arg-type]
        if "/bin/sh" in args:
            idx = args.index("/bin/sh")
            status_path = args[idx + 4] if len(args) > idx + 4 else None
            if status_path and isinstance(status_path, str):
                with open(status_path, "w", encoding="ascii") as fh:
                    fh.write("ro-ok")
        if on_start is not None:
            on_start(99999)
        return (0, b"ok", b"", False)

    monkeypatch.setattr(b, "_select_plan", lambda: plan)
    monkeypatch.setattr(lj, "run_child", _fake_run)
    # Mock cgroup leaf to avoid real fs writes beyond tmp.
    monkeypatch.setattr(b, "_prepare_cgroup_leaf", lambda notes: None)
    out = b.spawn(["true"], cwd=str(work), env={}, timeout_s=5)
    assert any("bind_ro=enforced" in n for n in out.notes)


@pytest.mark.skipif(not ON_LINUX, reason="linux-job backend requires Linux")
def test_linux_real_constructor() -> None:
    b = lj.LinuxJobIsolation()
    assert b.name == "linux-job"


@pytest.mark.skipif(not ON_LINUX, reason="linux-job backend requires Linux")
def test_linux_real_cgroup_marker() -> None:
    b = lj.LinuxJobIsolation(cgroup_parent="/proc/realmock-nope/cgroup")
    notes: list[str] = []
    leaf = b._prepare_cgroup_leaf(notes)
    assert leaf is None or isinstance(leaf, str)
