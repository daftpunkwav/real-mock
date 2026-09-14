"""Linux job isolation backend: unprivileged user + no network + cgroup caps.

Minimum viable Step 2 sandbox for snippet execution on Linux, built from
stdlib and OS primitives only (``unshare``/``setpriv``/``runuser`` from the
essential util-linux package, cgroup v2 filesystem, ``/bin/sh``):

* user switch: ``setpriv`` (else ``runuser``) to a ``nobody``-style account
  when root; otherwise a user-namespace uid/gid map onto that account, so
  the snippet is never the API uid without an explicit marker saying so.
* network: a fresh network namespace (``unshare -n``) with no interfaces
  brought up, so even loopback stays down.
* cgroup v2: per-run leaf under a configurable subtree with ``memory.max``
  and ``cpu.max`` caps; the leaf is removed after the run.
* filesystem: best-effort read-only remount of ``/`` inside a private mount
  namespace while the temp workdir stays writable; the outcome is recorded
  in a status file and surfaced as a note.

Every control that cannot be enforced (no cgroup fs, no namespaces in the
runtime, missing helper) becomes an explicit ``<control>=unavailable``
entry in ``CompletedSnippet.notes`` — never a silent downgrade. Mount
changes are only ever attempted inside a freshly unshared private mount
namespace, never on the host namespace.

``pwd``/``grp`` are imported lazily so this module stays importable on
Windows (where constructing the backend raises a clear ``RuntimeError``).
"""

from __future__ import annotations

import itertools
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

from .base import CompletedSnippet, run_child

# Neutral environment overrides (all optional; explicit ctor args win).
ENV_CGROUP_PARENT = "CODEEXEC_CGROUP_PARENT"
ENV_RUN_AS_USER = "CODEEXEC_RUN_AS_USER"
ENV_ALLOW_NETWORK = "CODEEXEC_ALLOW_NETWORK"
ENV_MEMORY_MAX_BYTES = "CODEEXEC_MEMORY_MAX_BYTES"
ENV_CPU_MAX = "CODEEXEC_CPU_MAX"

DEFAULT_RUN_AS_USER = "nobody"
DEFAULT_CGROUP_PARENT = "/sys/fs/cgroup/realmock-codeexec"
DEFAULT_MEMORY_MAX_BYTES = 256 * 1024 * 1024  # 256 MiB per snippet.
DEFAULT_CPU_MAX = "50000 100000"  # Half a CPU in cgroup v2 cpu.max terms.
_MOUNT_STATUS_PREFIX = ".mount-status-"

_CPU_MAX_RE = re.compile(r"^(max|\d+)(?:\s+(?:\d+))?$")
_TRUTHY = frozenset({"1", "true", "yes", "y", "on"})

_probe_cache: dict[tuple[str, ...], bool] = {}
_launch_counter = itertools.count(1)


def env_flag(name: str, default: bool) -> bool:
    """Parse an opt-in env toggle; unset means ``default``."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def env_text(name: str, default: str) -> str:
    """Read an env string; unset means ``default``, whitespace is stripped."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip()


@dataclass(frozen=True)
class LaunchPlan:
    """How one snippet argv is wrapped before spawn (pure data, testable)."""

    kind: str  # contained | userns-mapped | userns-netonly | netonly | plain
    prefix: tuple[str, ...]  # Namespace wrapper (unshare ...) or ().
    user_switch: tuple[str, ...]  # setpriv/runuser argv or () when n/a.
    drops_to: str  # Outside identity of the snippet ("nobody"-style or "unchanged").
    net_blocked: bool
    mount_prelude: bool  # Whether the read-only remount prelude is attempted.
    notes: tuple[str, ...] = ()


def parse_memory_limit(raw: str | int | None, *, source: str) -> int | None:
    """Normalize a memory cap to bytes; ``""``/``None`` disables the cap."""
    if raw is None:
        return None
    if isinstance(raw, int):
        value = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        try:
            value = int(text)
        except ValueError:
            raise ValueError(f"{source} must be a byte count, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{source} must be a positive byte count, got {raw!r}")
    return value


def parse_cpu_limit(raw: str | None, *, source: str) -> str | None:
    """Validate a cgroup v2 ``cpu.max`` value; ``""``/``None`` disables it."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if not _CPU_MAX_RE.match(text):
        raise ValueError(
            f"{source} must look like cgroup v2 cpu.max ('<max> <period>' or "
            f"'max <period>'), got {raw!r}"
        )
    return " ".join(text.split())


def resolve_user_ids(username: str) -> tuple[int, int]:
    """Map an account name to ``(uid, gid)``; unknown names are a clear error."""
    import pwd

    try:
        entry = pwd.getpwnam(username)
    except KeyError:
        raise ValueError(f"unknown isolation user {username!r}") from None
    return int(entry.pw_uid), int(entry.pw_gid)


@lru_cache(maxsize=1)
def _tool_path(name: str) -> str | None:
    """Cached ``shutil.which`` so per-snippet overhead stays near zero."""
    return shutil.which(name)


def _probe(argv: Sequence[str]) -> bool:
    """Return True when a helper argv runs cleanly (results are cached)."""
    key = tuple(argv)
    cached = _probe_cache.get(key)
    if cached is not None:
        return cached
    try:
        completed = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        ok = completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    _probe_cache[key] = ok
    return ok


def _user_switch_argv(
    username: str, uid: int, gid: int, *, probe: bool = True
) -> tuple[str, ...]:
    """Best setpriv/runuser argv for dropping to ``username`` (else ``()``).

    The exact argv (flags included) is probe-validated so an unsupported
    helper never reaches the real run.
    """
    setpriv = _tool_path("setpriv")
    if setpriv:
        argv = (
            setpriv,
            f"--reuid={uid}",
            f"--regid={gid}",
            "--clear-groups",
            "--no-new-privs",
            "true",
        )
        # Probe without the trailing payload check: replace payload with true.
        if not probe or _probe(argv):
            return argv[:-1]
    runuser = _tool_path("runuser")
    if runuser:
        argv = (runuser, "-u", username, "--", "true")
        if not probe or _probe(argv):
            return argv[:-1]
    return ()


def build_plan(
    *,
    is_root: bool,
    username: str,
    uid: int,
    gid: int,
    allow_network: bool,
    unshare: str | None,
    user_switch: tuple[str, ...],
    map_users_ok: bool,
    netns_ok: bool,
    mountns_netns_ok: bool,
    userns_mountns_netns_ok: bool,
) -> LaunchPlan:
    """Pick the strongest workable launch strategy (pure; unit-testable).

    Preference order: fully contained (namespaces + user switch) > user
    namespace with uid/gid mapping > user namespace for network only >
    network namespace only > plain spawn with explicit unavailable markers.
    """
    named = f"{username}({uid}:{gid})"
    if allow_network:
        net_note = ("network=allowed (explicit opt-in)",)
    else:
        net_note = ()
    if unshare is None:
        return LaunchPlan(
            kind="plain",
            prefix=(),
            user_switch=(),
            drops_to="unchanged",
            net_blocked=False,
            mount_prelude=False,
            notes=(
                "user_switch=unavailable (no unshare/setpriv/runuser path)",
                *(() if allow_network else ("network=unavailable (no unshare)",)),
                "cgroup=best-effort (see run notes)",
                "bind_ro=unavailable (no mount namespace)",
                *net_note,
            ),
        )
    if is_root and not allow_network and mountns_netns_ok and user_switch:
        return LaunchPlan(
            kind="contained",
            prefix=(unshare, "-m", "--propagation", "private", "-n"),
            user_switch=user_switch,
            drops_to=named,
            net_blocked=True,
            mount_prelude=True,
        )
    if is_root and not allow_network and map_users_ok:
        return LaunchPlan(
            kind="userns-mapped",
            prefix=(
                unshare,
                "-U",
                "-m",
                "-n",
                f"--map-users=0:{uid}:1",
                f"--map-groups=0:{gid}:1",
            ),
            user_switch=(),
            drops_to=named,
            net_blocked=True,
            mount_prelude=True,
        )
    if is_root and not allow_network and netns_ok:
        return LaunchPlan(
            kind="netonly",
            prefix=(unshare, "-n"),
            user_switch=(),
            drops_to="unchanged",
            net_blocked=True,
            mount_prelude=False,
            notes=("user_switch=unavailable (no setpriv/runuser found)",),
        )
    if not allow_network and userns_mountns_netns_ok:
        return LaunchPlan(
            kind="userns-netonly",
            prefix=(unshare, "-U", "-m", "-n", "-r"),
            user_switch=(),
            drops_to="unchanged",
            net_blocked=True,
            mount_prelude=True,
            notes=(
                "user_switch=unavailable (non-root single-id map keeps callers uid)",
            ),
        )
    notes = ["cgroup=best-effort (see run notes)", "bind_ro=unavailable (no mount namespace)"]
    if not allow_network:
        notes.append("network=unavailable (no workable namespace combination)")
    notes.extend(net_note)
    if is_root:
        notes.append("user_switch=unavailable (no setpriv/runuser found)")
    return LaunchPlan(
        kind="plain",
        prefix=(),
        user_switch=(),
        drops_to="unchanged",
        net_blocked=False,
        mount_prelude=False,
        notes=tuple(notes),
    )


# Read-only remount prelude executed as `$0`=workdir, `$1`=status file,
# remaining args = inner command. Only used inside a private mount namespace.
_MOUNT_PRELUDE = (
    "printf 'pending' > \"$1\" 2>/dev/null; "
    "mount --make-rprivate / 2>/dev/null; "
    "mount --bind \"$0\" \"$0\" 2>/dev/null; "
    "if mount -o remount,ro,bind / 2>/dev/null; then "
    "mount -o remount,rw,bind \"$0\" 2>/dev/null; "
    "printf 'ro-ok' > \"$1\" 2>/dev/null; "
    "else printf 'ro-unavailable' > \"$1\" 2>/dev/null; fi; "
    "shift; exec \"$@\""
)


class LinuxJobIsolation:
    """Linux sandbox: dropped user, private net namespace, cgroup caps.

    Constructor validates platform, account and limits eagerly so a
    misconfigured deployment fails with a clear error instead of running
    snippets under weaker isolation than requested.
    """

    name = "linux-job"

    def __init__(
        self,
        *,
        run_as_user: str | None = None,
        allow_network: bool | None = None,
        memory_max_bytes: int | str | None = None,
        cpu_max: str | None = None,
        cgroup_parent: str | None = None,
    ) -> None:
        if os.name != "posix" or not sys.platform.startswith("linux"):
            raise RuntimeError("linux-job isolation requires Linux")
        self.run_as_user = env_text(ENV_RUN_AS_USER, DEFAULT_RUN_AS_USER) if run_as_user is None else run_as_user.strip()
        if not self.run_as_user:
            raise ValueError("isolation user must not be empty")
        self.uid, self.gid = resolve_user_ids(self.run_as_user)
        self.allow_network = env_flag(ENV_ALLOW_NETWORK, False) if allow_network is None else bool(allow_network)
        if memory_max_bytes is None:
            raw_memory: int | str | None = os.environ.get(ENV_MEMORY_MAX_BYTES)
            if raw_memory is None:
                raw_memory = DEFAULT_MEMORY_MAX_BYTES
            self.memory_max_bytes = parse_memory_limit(raw_memory, source=ENV_MEMORY_MAX_BYTES)
        else:
            self.memory_max_bytes = parse_memory_limit(memory_max_bytes, source="memory_max_bytes")
        if cpu_max is None:
            raw_cpu = os.environ.get(ENV_CPU_MAX)
            if raw_cpu is None:
                raw_cpu = DEFAULT_CPU_MAX
            self.cpu_max = parse_cpu_limit(raw_cpu, source=ENV_CPU_MAX)
        else:
            self.cpu_max = parse_cpu_limit(cpu_max, source="cpu_max")
        if cgroup_parent is None:
            self.cgroup_parent = env_text(ENV_CGROUP_PARENT, DEFAULT_CGROUP_PARENT)
        else:
            self.cgroup_parent = cgroup_parent.strip()
        if not self.cgroup_parent:
            raise ValueError("cgroup parent path must not be empty")

    def describe(self) -> str:
        """One-line summary of the enforced controls (logs/observations)."""
        net = "allowed" if self.allow_network else "blocked(netns)"
        mem = str(self.memory_max_bytes) if self.memory_max_bytes else "uncapped"
        cpu = self.cpu_max if self.cpu_max else "uncapped"
        return (
            f"linux-job: user={self.run_as_user}({self.uid}:{self.gid}) "
            f"net={net} cgroup(parent={self.cgroup_parent},mem={mem},cpu={cpu})"
        )

    def _select_plan(self) -> LaunchPlan:
        """Probe OS helpers (cached) and pick the strongest workable plan."""
        unshare = _tool_path("unshare")
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        if unshare is None:
            return build_plan(
                is_root=is_root,
                username=self.run_as_user,
                uid=self.uid,
                gid=self.gid,
                allow_network=self.allow_network,
                unshare=None,
                user_switch=(),
                map_users_ok=False,
                netns_ok=False,
                mountns_netns_ok=False,
                userns_mountns_netns_ok=False,
            )
        switch = _user_switch_argv(self.run_as_user, self.uid, self.gid) if is_root else ()
        return build_plan(
            is_root=is_root,
            username=self.run_as_user,
            uid=self.uid,
            gid=self.gid,
            allow_network=self.allow_network,
            unshare=unshare,
            user_switch=switch,
            map_users_ok=_probe(
                (unshare, "-U", "--map-users=0:0:1", "--map-groups=0:0:1", "true")
            ),
            netns_ok=_probe((unshare, "-n", "true")),
            mountns_netns_ok=_probe((unshare, "-m", "--propagation", "private", "-n", "true")),
            userns_mountns_netns_ok=_probe((unshare, "-U", "-m", "-n", "-r", "true")),
        )

    def _prepare_cgroup_leaf(self, notes: list[str]) -> str | None:
        """Create and cap a per-run cgroup leaf; failures become notes."""
        if self.memory_max_bytes is None and self.cpu_max is None:
            return None
        leaf = os.path.join(
            self.cgroup_parent, f"snippet-{os.getpid()}-{next(_launch_counter)}"
        )
        try:
            os.makedirs(self.cgroup_parent, exist_ok=True)
            try:
                # Control files require a plain write (append mode is rejected).
                with open(os.path.join(self.cgroup_parent, "cgroup.subtree_control"), "w", encoding="ascii") as fh:
                    fh.write("+cpu +memory")
            except OSError:
                pass  # Controllers may already be enabled or read-only; leaf writes decide.
            try:
                os.mkdir(leaf)
            except FileExistsError:
                leaf = f"{leaf}-{secrets.token_hex(4)}"
                os.mkdir(leaf)
        except OSError as exc:
            notes.append(f"cgroup=unavailable (cannot create leaf under {self.cgroup_parent}: {exc.strerror or exc})")
            return None
        knobs = []
        if self.memory_max_bytes is not None:
            knobs.append(("memory.max", str(self.memory_max_bytes)))
        if self.cpu_max is not None:
            knobs.append(("cpu.max", self.cpu_max))
        for knob, value in knobs:
            try:
                with open(os.path.join(leaf, knob), "w", encoding="ascii") as fh:
                    fh.write(value)
            except OSError as exc:
                notes.append(f"cgroup=degraded ({knob} not enforced: {exc.strerror or exc})")
        return leaf

    @staticmethod
    def _attach_pid(leaf: str, notes: list[str], pid: int) -> None:
        try:
            with open(os.path.join(leaf, "cgroup.procs"), "w", encoding="ascii") as fh:
                fh.write(str(pid))
        except OSError as exc:
            notes.append(f"cgroup=degraded (child not moved into leaf: {exc.strerror or exc})")

    @staticmethod
    def _drop_cgroup_leaf(leaf: str) -> None:
        try:
            os.rmdir(leaf)
        except OSError:
            pass

    def spawn(
        self,
        argv: Sequence[str],
        *,
        cwd: str,
        env: Mapping[str, str],
        timeout_s: float,
    ) -> CompletedSnippet:
        """Run ``argv`` under the selected Linux sandbox plan."""
        plan = self._select_plan()
        notes = list(plan.notes)
        notes.append(
            f"plan={plan.kind} user={plan.drops_to} "
            f"net={'blocked' if plan.net_blocked else 'open'}"
        )
        status_name = f"{_MOUNT_STATUS_PREFIX}{secrets.token_hex(8)}"
        status_path = os.path.join(cwd, status_name)
        inner: list[str] = ["/bin/sh", "-c", _MOUNT_PRELUDE, cwd, status_path] if plan.mount_prelude else []
        full_argv = [*plan.prefix, *inner, *plan.user_switch, *argv]
        leaf: str | None = None
        if self.memory_max_bytes is None and self.cpu_max is None:
            notes.append("cgroup=uncapped (no limits configured)")
        else:
            leaf = self._prepare_cgroup_leaf(notes)
        try:
            if leaf is not None:
                exit_code, out, err, timed_out = run_child(
                    full_argv,
                    cwd=cwd,
                    env=env,
                    timeout_s=timeout_s,
                    on_start=lambda pid: self._attach_pid(leaf, notes, pid),
                )
            else:
                exit_code, out, err, timed_out = run_child(
                    full_argv, cwd=cwd, env=env, timeout_s=timeout_s
                )
        finally:
            if leaf is not None:
                self._drop_cgroup_leaf(leaf)
        if plan.mount_prelude:
            try:
                with open(status_path, encoding="ascii") as fh:
                    status = fh.read().strip()
                try:
                    os.unlink(status_path)
                except OSError:
                    pass
            except OSError:
                status = "missing"
            if status == "ro-ok":
                notes.append("bind_ro=enforced (/ read-only, workdir writable)")
            elif status == "ro-unavailable":
                notes.append("bind_ro=unavailable (read-only remount denied)")
            else:
                notes.append("bind_ro=unknown (mount status not recorded)")
        return CompletedSnippet(
            exit_code=exit_code,
            stdout=out,
            stderr=err,
            timed_out=timed_out,
            notes=tuple(notes),
        )
