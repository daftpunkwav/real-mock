"""Code-exec tool tests for realmock.domains.prep.agents.tools.basic.code_exec.

Covers: missing-code guard and timeout default/clamp branches
Conventions: run_code_snippet faked; no real execution; rate limits reset per test
"""
from __future__ import annotations
import pytest
from realmock.platform.capabilities.ai.agent import WorkingMemory

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def _memory() -> WorkingMemory:
    return WorkingMemory()

@pytest.mark.asyncio
async def test_code_exec_missing_code() -> None:
    from realmock.domains.prep.agents.tools.basic.code_exec import run_code_exec

    text, hits = await run_code_exec({"language": "python", "code": "   "}, _memory())
    assert "missing code" in text
    assert hits == []

@pytest.mark.asyncio
async def test_code_exec_bad_timeout_uses_default(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.basic.code_exec as code_mod

    seen: dict = {}

    def _fake_snippet(language, code, timeout=None):
        seen.update({"language": language, "code": code, "timeout": timeout})
        return {"ok": True}

    monkeypatch.setattr(code_mod, "run_code_snippet", _fake_snippet)
    monkeypatch.setattr(code_mod, "format_observation", lambda result: f"OBS:{result}")
    text, hits = await code_mod.run_code_exec(
        {"language": "python", "code": "print(1)", "timeout": "bad"}, _memory()
    )
    assert text.startswith("OBS:")
    assert hits == []
    assert seen["timeout"] == code_mod._CODE_EXEC_DEFAULT_TIMEOUT

    text2, _ = await code_mod.run_code_exec(
        {"language": "python", "code": "print(1)", "timeout": 99}, _memory()
    )
    assert text2.startswith("OBS:")
    assert seen["timeout"] == code_mod._CODE_EXEC_MAX_TIMEOUT

@pytest.mark.asyncio
async def test_code_exec_overlong_code_refused_not_truncated(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.basic.code_exec as code_mod

    def _must_not_run(*args, **kwargs):
        raise AssertionError("overlong code must not reach the sandbox")

    monkeypatch.setattr(code_mod, "run_code_snippet", _must_not_run)
    text, hits = await code_mod.run_code_exec(
        {"language": "python", "code": "x" * (code_mod._PLATFORM_MAX_CODE_CHARS + 1)},
        _memory(),
    )
    assert "too long" in text
    assert hits == []

@pytest.mark.asyncio
async def test_code_exec_nonfinite_timeout_uses_default(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.basic.code_exec as code_mod

    seen: dict = {}

    def _fake_snippet(language, code, timeout=None):
        seen.update({"timeout": timeout})
        return {"ok": True}

    monkeypatch.setattr(code_mod, "run_code_snippet", _fake_snippet)
    monkeypatch.setattr(code_mod, "format_observation", lambda result: f"OBS:{result}")
    text, _ = await code_mod.run_code_exec(
        {"language": "python", "code": "print(1)", "timeout": float("nan")}, _memory()
    )
    assert text.startswith("OBS:")
    assert seen["timeout"] == code_mod._CODE_EXEC_DEFAULT_TIMEOUT
