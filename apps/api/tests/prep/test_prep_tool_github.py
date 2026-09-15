"""GitHub tool tests for realmock.domains.prep.agents.tools.repo.github.

Covers: github_tool_spec handler passthrough/missing and _build_github_specs skip
Conventions: github_tool_specs faked; no network; rate limits reset per test
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
async def test_github_spec_handler_and_missing(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.repo.github as github_mod

    class _Shared:
        name = "github_get_file"
        description = "desc"
        parameters = {"type": "object"}

        async def handler(self, args):
            return f"SHARED:{args.get('repo')}"

    monkeypatch.setattr(
        github_mod, "github_tool_specs", lambda names=None: iter([_Shared()])
    )
    spec = github_mod.github_tool_spec("github_get_file")
    text, hits = await spec.handler({"repo": "a/b"}, _memory())
    assert text == "SHARED:a/b"
    assert hits == []

    monkeypatch.setattr(github_mod, "github_tool_specs", lambda names=None: iter([]))
    with pytest.raises(RuntimeError, match="Platform github tool missing"):
        github_mod.github_tool_spec("github_get_file")

def test_build_github_specs_skips_missing(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.repo.github as github_mod

    real = github_mod.github_tool_spec
    calls = {"n": 0}

    def _flaky(name):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Platform github tool missing: x")
        return real(name)

    monkeypatch.setattr(github_mod, "github_tool_spec", _flaky)
    warnings: list[str] = []
    monkeypatch.setattr(github_mod.logger, "warning", lambda *a, **k: warnings.append(str(a[0])))
    specs = github_mod._build_github_specs()
    assert len(specs) >= 1
    assert any("skipping" in w for w in warnings)
