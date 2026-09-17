"""Research agents: bounded company web research.

:mod:`company_research` hosts the shared ``run_web_research`` loop (model +
``web_search``/``web_fetch`` under call budgets) used by both the process-level
research digest and :mod:`company_brief` (setup-page brief with cache,
singleflight and failure cooldown). Failure is honest and cheap: any research
problem returns ``None`` and callers proceed with catalog context only.
"""
