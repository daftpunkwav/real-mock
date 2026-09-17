"""Planning agents: flow-plan and HR round-program generation.

Both planners are one-shot background LLM calls that persist their JSON
documents on session/process rows and degrade to static chains on failure —
planning problems must never block an interview. The stored plan protocols
they write live on the process side (:mod:`realmock.domains.interview.process.plan_schema`
and ``round_plan_schema``); web-research grounding comes from
:mod:`realmock.domains.interview.agents.research`.
"""
