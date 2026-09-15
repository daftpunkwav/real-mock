"""Isolation resolve tests for apps/api/src/realmock/platform/capabilities/ai/agent/tools/isolation/__init__.py.

Covers: resolve_backend type/value errors, instance passthrough, process default,
env-override fallback and root-fallback-to-process branch.

Conventions: no real containers (backends mocked); asyncio_mode=auto.
"""

from __future__ import annotations

import pytest



def test_isolation_root_fallback_to_process(monkeypatch) -> None:
    from realmock.platform.capabilities.ai.agent.tools.isolation import (
        ProcessIsolation,
        resolve_backend,
    )
    import realmock.platform.capabilities.ai.agent.tools.isolation as mod

    monkeypatch.setattr(mod, "_running_as_root", lambda: True)
    monkeypatch.setattr(mod, "_warned_fallback", False)

    def _boom():
        raise RuntimeError("no userns")

    monkeypatch.setattr(mod, "LinuxJobIsolation", _boom)
    backend = resolve_backend("auto")
    assert isinstance(backend, ProcessIsolation)


@pytest.mark.asyncio
async def test_iso_resolve_backend_branches(monkeypatch) -> None:
    from realmock.platform.capabilities.ai.agent.tools import isolation as iso

    with pytest.raises(TypeError):
        iso.resolve_backend(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        iso.resolve_backend("ghost")
    # Explicit instance passes through.
    proc = iso.ProcessIsolation()
    assert iso.resolve_backend(proc) is proc
    assert iso.resolve_backend("process").name == "process"
    # Env override empty string falls back to env default.
    monkeypatch.setenv("CODEEXEC_ISOLATION", "process")
    assert iso.resolve_backend("  ").name == "process"
