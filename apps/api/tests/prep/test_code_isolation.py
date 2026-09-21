"""Isolation backends for the code_exec tool: selection, fallback, markers (no LLM)."""

from __future__ import annotations

import os
import sys

import pytest

from realmock.platform.capabilities.ai.agent.tools import isolation as isolation_pkg
from realmock.platform.capabilities.ai.agent.tools.codeexec import (
    CodeResult,
    format_observation,
    run_code_snippet,
)
from realmock.platform.capabilities.ai.agent.tools.isolation import (
    SELECTION_ENV_VAR,
    CompletedSnippet,
    LinuxJobIsolation,
    ProcessIsolation,
    resolve_backend,
)
from realmock.platform.capabilities.ai.agent.tools.isolation import (
    linux_job as linux_job_mod,
)

ON_LINUX = sys.platform.startswith("linux")
NEEDS_LINUX = pytest.mark.skipif(not ON_LINUX, reason="linux-job backend requires Linux")


def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def test_process_backend_runs_snippet_with_name_attached() -> None:
    result = run_code_snippet("python", "print('hi', 40 + 2)", isolation="process")
    assert result.exit_code == 0
    assert "hi 42" in result.stdout
    assert result.isolation == "process"
    assert result.notes == ()
    assert "isolation: process" in format_observation(result)


def test_backend_instance_is_used_directly() -> None:
    backend = ProcessIsolation()
    assert resolve_backend(backend) is backend
    result = run_code_snippet("python", "print('ok')", isolation=backend)
    assert result.exit_code == 0
    assert result.isolation == "process"


def test_auto_selection_matches_platform() -> None:
    backend = resolve_backend("auto")
    if ON_LINUX and _is_root():
        assert backend.name == "linux-job"
    else:
        assert backend.name == "process"


def test_auto_logs_fallback_warning_once(caplog: pytest.LogCaptureFixture) -> None:
    if ON_LINUX and _is_root():
        pytest.skip("fallback warning only applies off Linux-root")
    isolation_pkg._warned_fallback = False
    try:
        with caplog.at_level("WARNING", logger=isolation_pkg.__name__):
            resolve_backend("auto")
        assert any("process isolation only" in rec.message for rec in caplog.records)
        caplog.clear()
        with caplog.at_level("WARNING", logger=isolation_pkg.__name__):
            resolve_backend("auto")
        assert caplog.records == []
    finally:
        isolation_pkg._warned_fallback = True


def test_unknown_backend_name_is_a_clear_error_not_a_raise() -> None:
    with pytest.raises(ValueError, match="unknown isolation backend"):
        resolve_backend("no-such-backend")
    result = run_code_snippet("python", "print(1)", isolation="no-such-backend")
    assert result.exit_code == -1
    assert "unknown isolation backend" in result.error


def test_backend_selection_type_error_is_a_clear_error() -> None:
    with pytest.raises(TypeError, match="isolation must be"):
        resolve_backend(123)  # type: ignore[arg-type]
    result = run_code_snippet("python", "print(1)", isolation=123)  # type: ignore[arg-type]
    assert "isolation misconfigured" in result.error


def test_env_override_selects_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SELECTION_ENV_VAR, "process")
    assert isinstance(resolve_backend(None), ProcessIsolation)
    monkeypatch.setenv(SELECTION_ENV_VAR, "bogus-backend")
    with pytest.raises(ValueError, match="unknown isolation backend"):
        resolve_backend(None)


def test_linux_job_request_off_linux_is_a_clear_error() -> None:
    if ON_LINUX:
        pytest.skip("off-Linux rejection only applies on other platforms")
    with pytest.raises(RuntimeError, match="requires Linux"):
        LinuxJobIsolation()
    result = run_code_snippet("python", "print(1)", isolation="linux-job")
    assert "requires Linux" in result.error


def test_code_result_defaults_keep_old_constructors_working() -> None:
    result = CodeResult(language="python", exit_code=0, stdout="a", stderr="", duration_ms=1)
    assert result.isolation == ""
    assert result.notes == ()
    assert CompletedSnippet(exit_code=0, stdout=b"", stderr=b"", timed_out=False).notes == ()


def test_error_observations_keep_exact_legacy_shape() -> None:
    result = run_code_snippet("ruby", "puts 1")
    assert "isolation: " not in format_observation(result)


def test_env_scrub_preserved_under_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REALMOCK_CODEEXEC_SECRET_PROBE", "leak-me")
    code = "import os; print('secret=' + os.environ.get('REALMOCK_CODEEXEC_SECRET_PROBE', 'absent'))"
    result = run_code_snippet("python", code, isolation="process")
    assert result.exit_code == 0
    assert "secret=absent" in result.stdout


def test_timeout_kill_tree_preserved_under_process_backend() -> None:
    result = run_code_snippet(
        "python", "import time\ntime.sleep(30)", timeout=1, isolation="process"
    )
    assert result.timed_out is True
    assert "isolation: process" in format_observation(result)


def test_terminate_tree_posix_and_dead_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.platform.capabilities.ai.agent.tools.isolation import base as base_mod

    class _P:
        pid = 12345
        killed = False

        def kill(self):
            self.killed = True

    # POSIX killpg success path (create attr on Windows).
    monkeypatch.setattr(base_mod.os, "name", "posix")
    monkeypatch.setattr(base_mod.os, "killpg", lambda pid, sig: None, raising=False)
    import signal as _sig

    monkeypatch.setattr(_sig, "SIGKILL", 9, raising=False)
    p = _P()
    base_mod.terminate_tree(p)  # type: ignore[arg-type]
    assert p.killed is False
    # POSIX killpg raises -> falls back to proc.kill.

    def _boom(pid, sig):
        raise ProcessLookupError("gone")

    monkeypatch.setattr(base_mod.os, "killpg", _boom, raising=False)
    base_mod.terminate_tree(p)  # type: ignore[arg-type]
    assert p.killed is True
    # proc.kill raises -> swallowed.
    class _Dead:
        pid = 1

        def kill(self):
            raise ProcessLookupError("gone")

    base_mod.terminate_tree(_Dead())  # type: ignore[arg-type]


def test_run_child_caps_captured_output_and_child_still_exits() -> None:
    # A child printing far beyond the backend capture cap must still exit
    # cleanly (draining keeps the pipe open) with bounded captured output.
    from realmock.platform.capabilities.ai.agent.tools.isolation.base import (
        _CAPTURE_LIMIT_BYTES,
        run_child,
    )

    script = "print('x' * (3 * 1024 * 1024))"
    exit_code, out, err, timed_out = run_child(
        [sys.executable, "-I", "-c", script],
        cwd=os.getcwd(),
        env={"PATH": os.environ.get("PATH", "")},
        timeout_s=30,
    )
    assert exit_code == 0
    assert timed_out is False
    assert len(out) <= _CAPTURE_LIMIT_BYTES
    assert err == b""


def test_output_caps_preserved_with_isolation_param() -> None:
    result = run_code_snippet("python", "print('x' * 20000)", isolation="process")
    assert result.exit_code == 0
    assert result.truncated is True


def test_notes_rendered_in_observation() -> None:
    result = CodeResult(
        language="python", exit_code=0, stdout="a", stderr="",
        duration_ms=1, isolation="linux-job", notes=("cgroup=unavailable (probe)",),
    )
    assert "cgroup=unavailable (probe)" in format_observation(result)


def test_process_backend_describes_its_limits() -> None:
    assert "no user switch" in ProcessIsolation().describe()


def test_build_plan_prefers_contained_for_root_with_tools() -> None:
    plan = linux_job_mod.build_plan(
        is_root=True, username="nobody", uid=65534, gid=65534,
        allow_network=False, unshare="/usr/bin/unshare",
        user_switch=("setpriv", "--reuid=65534"), map_users_ok=True,
        netns_ok=True, mountns_netns_ok=True, userns_mountns_netns_ok=True,
    )
    assert plan.kind == "contained"
    assert plan.drops_to == "nobody(65534:65534)"
    assert plan.net_blocked is True
    assert plan.mount_prelude is True
    assert plan.user_switch[0] == "setpriv"


def test_build_plan_falls_back_without_unshare() -> None:
    plan = linux_job_mod.build_plan(
        is_root=False, username="nobody", uid=65534, gid=65534,
        allow_network=False, unshare=None, user_switch=(),
        map_users_ok=False, netns_ok=False,
        mountns_netns_ok=False, userns_mountns_netns_ok=False,
    )
    assert plan.kind == "plain"
    assert plan.mount_prelude is False
    assert any(n.startswith("user_switch=unavailable") for n in plan.notes)
    assert any(n.startswith("bind_ro=unavailable") for n in plan.notes)


def test_build_plan_userns_netonly_keeps_uid_marker_for_non_root() -> None:
    plan = linux_job_mod.build_plan(
        is_root=False, username="nobody", uid=65534, gid=65534,
        allow_network=False, unshare="/usr/bin/unshare", user_switch=(),
        map_users_ok=False, netns_ok=False,
        mountns_netns_ok=False, userns_mountns_netns_ok=True,
    )
    assert plan.kind == "userns-netonly"
    assert plan.net_blocked is True
    assert plan.drops_to == "unchanged"
    assert any(n.startswith("user_switch=unavailable") for n in plan.notes)


def test_build_plan_explicit_network_opt_in_is_marked() -> None:
    plan = linux_job_mod.build_plan(
        is_root=True, username="nobody", uid=65534, gid=65534,
        allow_network=True, unshare="/usr/bin/unshare",
        user_switch=("setpriv", "--reuid=65534"), map_users_ok=True,
        netns_ok=True, mountns_netns_ok=True, userns_mountns_netns_ok=True,
    )
    assert plan.net_blocked is False
    assert "network=allowed (explicit opt-in)" in plan.notes


def test_limit_parsing_rejects_bad_config() -> None:
    assert linux_job_mod.parse_memory_limit(None, source="t") is None
    assert linux_job_mod.parse_memory_limit("", source="t") is None
    assert linux_job_mod.parse_memory_limit("1024", source="t") == 1024
    with pytest.raises(ValueError, match="positive byte count"):
        linux_job_mod.parse_memory_limit(-5, source="t")
    with pytest.raises(ValueError, match="byte count"):
        linux_job_mod.parse_memory_limit("lots", source="t")
    assert linux_job_mod.parse_cpu_limit(None, source="t") is None
    assert linux_job_mod.parse_cpu_limit("", source="t") is None
    assert linux_job_mod.parse_cpu_limit("50000 100000", source="t") == "50000 100000"
    with pytest.raises(ValueError, match="cpu.max"):
        linux_job_mod.parse_cpu_limit("ludicrous", source="t")


def test_user_switch_argv_only_names_known_helpers() -> None:
    switch = linux_job_mod._user_switch_argv("nobody", 65534, 65534, probe=False)
    assert isinstance(switch, tuple)
    if switch:
        assert os.path.basename(switch[0]) in ("setpriv", "runuser")


@NEEDS_LINUX
def test_linux_job_constructor_validates_config() -> None:
    with pytest.raises(ValueError, match="positive byte count"):
        LinuxJobIsolation(memory_max_bytes=-1)
    with pytest.raises(ValueError, match="cpu.max"):
        LinuxJobIsolation(cpu_max="ludicrous")
    with pytest.raises(ValueError, match="unknown isolation user"):
        LinuxJobIsolation(run_as_user="no-such-user-real-mock")
    backend = LinuxJobIsolation()
    assert backend.name == "linux-job"
    assert "nobody" in backend.describe()


@NEEDS_LINUX
def test_cgroup_failure_degrades_with_marker_not_silently() -> None:
    backend = LinuxJobIsolation(cgroup_parent="/proc/realmock-nope/cgroup")
    result = run_code_snippet("python", "print('ok')", isolation=backend)
    assert result.exit_code == 0
    assert "ok" in result.stdout
    assert result.isolation == "linux-job"
    assert any(n.startswith("cgroup=unavailable") for n in result.notes)
    assert any(n.startswith("plan=") for n in result.notes)
