"""code_exec tool: snippet execution, limits, and registry wiring (no LLM)."""

from __future__ import annotations

import shutil

import pytest

from realmock.domains.prep.agents import tools as prep_tools
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.tools.codeexec import (
    MAX_OUTPUT_CHARS,
    format_observation,
    run_code_snippet,
)


def test_registry_contains_code_exec() -> None:
    assert "code_exec" in prep_tools.TOOL_REGISTRY
    names = [d["function"]["name"] for d in prep_tools.PREP_TOOL_DEFINITIONS]
    assert "code_exec" in names


async def test_python_hello_world() -> None:
    obs, hits = await prep_tools.execute_prep_tool(
        "code_exec",
        {"language": "python", "code": "print('hi', 40 + 2)"},
        WorkingMemory(),
    )
    assert hits == []
    assert "exit=0" in obs
    assert "hi 42" in obs


async def test_python_failure_surfaces_stderr_and_exit_code() -> None:
    obs, _ = await prep_tools.execute_prep_tool(
        "code_exec",
        {"language": "python", "code": "raise ValueError('boom')"},
        WorkingMemory(),
    )
    assert "exit=1" in obs
    assert "ValueError" in obs
    assert "boom" in obs


async def test_timeout_kills_snippet() -> None:
    obs, _ = await prep_tools.execute_prep_tool(
        "code_exec",
        {"language": "python", "code": "import time\ntime.sleep(30)", "timeout": 1},
        WorkingMemory(),
    )
    assert "timeout" in obs


def test_output_truncated_with_marker() -> None:
    result = run_code_snippet("python", "print('x' * 20000)")
    assert result.exit_code == 0
    assert result.truncated is True
    assert len(result.stdout) <= MAX_OUTPUT_CHARS + 100
    assert "truncated" in result.stdout
    assert "truncated" in format_observation(result)


def test_unsupported_language_is_an_observation_not_a_raise() -> None:
    result = run_code_snippet("ruby", "puts 1")
    assert result.exit_code == -1
    assert "unsupported language" in result.error
    assert "unsupported language" in format_observation(result)


def test_empty_code_rejected() -> None:
    result = run_code_snippet("python", "   ")
    assert "empty code" in result.error


@pytest.mark.skipif(shutil.which("node") is None, reason="node runtime not installed")
async def test_node_hello_world() -> None:
    obs, _ = await prep_tools.execute_prep_tool(
        "code_exec",
        {"language": "javascript", "code": "console.log('hi', 40 + 2)"},
        WorkingMemory(),
    )
    assert "exit=0" in obs
    assert "hi 42" in obs
