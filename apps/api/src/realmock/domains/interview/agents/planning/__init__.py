"""Planning agents: flow-plan and HR round-program generation.

Both planners are one-shot background LLM calls that persist their JSON
documents on session/process rows and degrade to static chains on failure —
planning problems must never block an interview. The stored plan documents
they write live in the neutral shared package
(:mod:`realmock.domains.interview.protocols.plan_schema` and
``round_plan_schema``); web-research grounding comes from
:mod:`realmock.domains.interview.agents.research`.
"""
