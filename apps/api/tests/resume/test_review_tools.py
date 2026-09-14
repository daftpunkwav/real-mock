"""Resume-only process/plan tool and hierarchical profile/resume tools."""

from __future__ import annotations

import asyncio
import json

import pytest

from realmock.domains.resume.agents.process import ReviewProcess, process_tool_specs
from realmock.domains.resume.schemas.limits import REVIEW_MAX_PLAN_STEPS, REVIEW_MIN_PLAN_STEPS
from realmock.platform.capabilities.ai.agent.tools.profile import (
    ProfileSnapshot,
    profile_tool_specs,
)
from realmock.platform.capabilities.ai.agent.tools.resume import (
    ResumeSnapshot,
    resume_tool_specs,
)


def _steps(n: int, finale: str = "Generate evaluation JSON") -> list[str]:
    return [f"evidence step {i}" for i in range(1, n)] + [finale]


def test_review_set_plan_rejects_fewer_than_min_steps() -> None:
    process = ReviewProcess()
    specs = {spec.name: spec for spec in process_tool_specs(process)}

    async def run() -> str:
        return await specs["review_set_plan"].handler(
            {"steps": _steps(REVIEW_MIN_PLAN_STEPS - 1)}
        )

    payload = json.loads(asyncio.run(run()))
    assert payload["error"] == "invalid_plan"
    assert process.steps == []


def test_review_set_plan_accepts_min_to_max_steps() -> None:
    for n in (REVIEW_MIN_PLAN_STEPS, REVIEW_MAX_PLAN_STEPS):
        process = ReviewProcess()
        specs = {spec.name: spec for spec in process_tool_specs(process)}

        async def run() -> str:
            return await specs["review_set_plan"].handler({"steps": _steps(n)})

        payload = json.loads(asyncio.run(run()))
        assert payload["ok"] is True
        assert len(payload["steps"]) == n
        assert all(step["mode"] == "serial" for step in payload["steps"])


def test_review_set_plan_rejects_more_than_max_steps() -> None:
    process = ReviewProcess()
    specs = {spec.name: spec for spec in process_tool_specs(process)}

    async def run() -> str:
        return await specs["review_set_plan"].handler(
            {"steps": _steps(REVIEW_MAX_PLAN_STEPS + 1)}
        )

    payload = json.loads(asyncio.run(run()))
    assert payload["error"] == "invalid_plan"
    assert process.steps == []


def test_review_set_plan_decodes_escaped_unicode_titles() -> None:
    process = ReviewProcess()
    specs = {spec.name: spec for spec in process_tool_specs(process)}

    async def run() -> str:
        return await specs["review_set_plan"].handler(
            {
                "steps": [f"\\u5355\\u680f evidence {i}" for i in range(1, REVIEW_MIN_PLAN_STEPS)]
                + ["Generate evaluation JSON"]
            }
        )

    payload = json.loads(asyncio.run(run()))
    assert payload["ok"] is True
    assert payload["steps"][0]["title"].startswith("单栏")
    assert "\\u" not in payload["steps"][0]["title"]


def test_review_update_step_parallel_mode() -> None:
    process = ReviewProcess()
    specs = {spec.name: spec for spec in process_tool_specs(process)}

    async def run() -> dict:
        await specs["review_set_plan"].handler({"steps": _steps(REVIEW_MIN_PLAN_STEPS)})
        return json.loads(
            await specs["review_update_step"].handler(
                {"id": "2", "status": "in_progress", "mode": "parallel"}
            )
        )

    payload = asyncio.run(run())
    assert payload["ok"] is True
    assert process.steps[1].status == "in_progress"
    assert process.steps[1].mode == "parallel"


def test_review_update_step_rejects_bad_mode() -> None:
    process = ReviewProcess()
    specs = {spec.name: spec for spec in process_tool_specs(process)}

    async def run() -> dict:
        await specs["review_set_plan"].handler({"steps": _steps(REVIEW_MIN_PLAN_STEPS)})
        return json.loads(
            await specs["review_update_step"].handler(
                {"id": "1", "status": "done", "mode": "warp"}
            )
        )

    payload = asyncio.run(run())
    assert payload["error"] == "invalid_mode"
    assert process.steps[0].mode == "serial"


def test_review_set_plan_requires_evaluation_last_step() -> None:
    process = ReviewProcess()
    specs = {spec.name: spec for spec in process_tool_specs(process)}

    async def run() -> str:
        return await specs["review_set_plan"].handler(
            {"steps": ["Read resume"] + _steps(REVIEW_MIN_PLAN_STEPS - 1, finale="Search market")}
        )

    payload = json.loads(asyncio.run(run()))
    assert payload["error"] == "invalid_plan"


def test_review_set_plan_accepts_evaluation_finale() -> None:
    process = ReviewProcess()
    specs = {spec.name: spec for spec in process_tool_specs(process)}

    async def run() -> str:
        return await specs["review_set_plan"].handler(
            {"steps": ["Read resume"] + _steps(REVIEW_MIN_PLAN_STEPS - 1)}
        )

    payload = json.loads(asyncio.run(run()))
    assert payload["ok"] is True
    assert len(payload["steps"]) == REVIEW_MIN_PLAN_STEPS
    assert payload["steps"][-1]["title"] == "Generate evaluation JSON"


def test_review_set_plan_rejects_package_json_as_finale() -> None:
    process = ReviewProcess()
    specs = {spec.name: spec for spec in process_tool_specs(process)}

    async def run() -> str:
        return await specs["review_set_plan"].handler(
            {
                "steps": ["Read resume"]
                + _steps(REVIEW_MIN_PLAN_STEPS - 1, finale="Parse package.json")
            }
        )

    payload = json.loads(asyncio.run(run()))
    assert payload["error"] == "invalid_plan"
    assert process.steps == []


def test_review_update_rejects_skipping_last_step() -> None:
    process = ReviewProcess()
    specs = {spec.name: spec for spec in process_tool_specs(process)}

    async def run() -> dict:
        await specs["review_set_plan"].handler({"steps": _steps(REVIEW_MIN_PLAN_STEPS)})
        return json.loads(
            await specs["review_update_step"].handler(
                {"id": str(REVIEW_MIN_PLAN_STEPS), "status": "skipped"}
            )
        )

    payload = asyncio.run(run())
    assert payload["error"] == "last_step_cannot_skip"
    assert process.steps[-1].status == "pending"


def test_plan_titles_from_tools_ends_with_evaluation() -> None:
    from realmock.domains.resume.agents.process import plan_titles_from_tool_names

    titles = plan_titles_from_tool_names(
        ["review_set_plan", "web_search", "web_search", "github_get_file"],
    )
    assert titles[0] == "web search"
    assert titles[1] == "github get file"
    assert titles[-1] == "Generate evaluation JSON"
    assert "review_set_plan" not in " ".join(titles)


def test_plan_titles_do_not_embed_locale_catalogs() -> None:
    from realmock.domains.resume.agents.process import plan_titles_from_tool_names

    titles = plan_titles_from_tool_names(["web_search"])
    assert titles[0] == "web search"
    assert titles[-1] == "Generate evaluation JSON"


def test_profile_two_level_disclosure() -> None:
    snapshot = ProfileSnapshot(
        fields={"name": "Ada", "school": "MIT", "major": "CS", "github_username": "ada"}
    )
    specs = {spec.name: spec for spec in profile_tool_specs(snapshot)}

    async def run() -> tuple[dict, dict]:
        listed = json.loads(await specs["profile_list_sections"].handler({}))
        education = json.loads(
            await specs["profile_get_section"].handler({"section": "education"})
        )
        return listed, education

    listed, education = asyncio.run(run())
    assert listed["available"] is True
    ids = {row["id"] for row in listed["sections"]}
    assert ids == {"basics", "education", "career", "skills", "links"}
    assert "school" in education["fields"]
    assert "github_username" not in education["fields"]


def test_resume_overview_does_not_dump_raw() -> None:
    snapshot = ResumeSnapshot(
        resume_id=1,
        filename="cv.pdf",
        file_type="pdf",
        raw_text="x" * 5000,
        parsed={"name": "Ada", "skills": ["Python"], "projects": [{"name": "real-mock"}]},
    )
    specs = {spec.name: spec for spec in resume_tool_specs(snapshot)}

    async def run() -> dict:
        return json.loads(await specs["resume_overview"].handler({}))

    overview = asyncio.run(run())
    dumped = json.dumps(overview)
    assert "xxxxx" not in dumped
    assert overview["project_names"] == ["real-mock"]
    assert "Python" in overview["skills"]


def test_invoke_review_tool_returns_error_json_on_failure() -> None:
    from realmock.domains.resume.agents.review import _invoke_review_tool

    class _Bundle:
        async def execute(self, name: str, args: dict) -> str:
            del name, args
            raise RuntimeError("boom")

    raw, status = asyncio.run(_invoke_review_tool(_Bundle(), "web_search", {}))  # type: ignore[arg-type]
    assert status == "error"
    payload = json.loads(raw)
    assert payload["error"] == "tool_failed"


def test_invoke_review_tool_reraises_business_error() -> None:
    from realmock.domains.resume.agents.review import _invoke_review_tool
    from realmock.platform.core.errors import ApiBusinessError, raise_error

    class _Bundle:
        async def execute(self, name: str, args: dict) -> str:
            del name, args
            raise_error("A0006")

    with pytest.raises(ApiBusinessError) as exc_info:
        asyncio.run(_invoke_review_tool(_Bundle(), "web_search", {}))  # type: ignore[arg-type]
    assert exc_info.value.error_code == "A0006"


def test_tool_timeout_emits_error_event_and_observation() -> None:
    """Timeouts reach the LLM as error JSON and the live UI as status=error."""
    from realmock.domains.resume.agents.review import _build_tool_executor

    class _TimeoutBundle:
        async def execute(self, name: str, args: dict) -> str:
            del name, args
            raise asyncio.TimeoutError

    events: list[dict] = []
    used: list[str] = []
    execute = _build_tool_executor(_TimeoutBundle(), used, events.append)  # type: ignore[arg-type]

    async def run() -> str:
        return await execute("web_search", {"query": "q"})

    returned = asyncio.run(run())
    payload = json.loads(returned)
    assert payload["error"] == "timeout"
    done = [e for e in events if e.get("status") == "error"]
    assert len(done) == 1
    assert json.loads(done[0]["result"])["error"] == "timeout"


def test_plan_reminder_bounded_until_plan_exists() -> None:
    from realmock.domains.resume.agents.review import (
        _PLAN_REMINDER_MAX,
        _needs_plan_reminder,
        _plan_reminder_text,
    )

    assert _needs_plan_reminder(has_plan=False, round_index=0, reminders_used=0) is False
    assert _needs_plan_reminder(has_plan=False, round_index=1, reminders_used=0) is True
    assert _needs_plan_reminder(has_plan=True, round_index=1, reminders_used=0) is False
    assert (
        _needs_plan_reminder(
            has_plan=False, round_index=9, reminders_used=_PLAN_REMINDER_MAX
        )
        is False
    )
    text = _plan_reminder_text()
    assert "review_set_plan" in text
    assert f"{REVIEW_MIN_PLAN_STEPS}-{REVIEW_MAX_PLAN_STEPS}" in text


def test_review_primer_orders_plan_first() -> None:
    from realmock.domains.resume.agents.payload import _overview_text
    from realmock.platform.capabilities.ai.agent.tools.resume import ResumeSnapshot

    snapshot = ResumeSnapshot(
        resume_id=1, filename="r.pdf", file_type="pdf", raw_text="",
        parsed={}, layout_notes="", has_visual_pages=False,
    )
    intro = _overview_text(snapshot)
    assert "review_set_plan" in intro
    assert intro.index("Plan first") < intro.index("Compact parsed map")


def test_tool_circuit_breaker_blocks_repeated_failures() -> None:
    from realmock.domains.resume.agents.review import (
        _TOOL_CIRCUIT_BREAKER_STREAK,
        _build_tool_executor,
    )

    calls: list[str] = []

    class _AlwaysFails:
        async def execute(self, name: str, args: dict) -> str:
            calls.append(name)
            raise RuntimeError("boom")

    execute = _build_tool_executor(_AlwaysFails(), [], None)  # type: ignore[arg-type]

    async def run() -> list[str]:
        return [await execute("web_search", {"query": "q"}) for _ in range(4)]

    results = asyncio.run(run())
    assert len(calls) == _TOOL_CIRCUIT_BREAKER_STREAK
    assert json.loads(results[0])["error"] == "tool_failed"
    opened = json.loads(results[-1])
    assert opened["error"] == "circuit_open"
    assert opened["tool"] == "web_search"
