"""Reference-answer agent: tool-grounded model replies for the candidate.

The "full" reference mode runs a short agent loop (profile / resume / GitHub
tools, :data:`FULL_HINT_BUDGET_SECONDS` wall-clock budget) and synthesizes a
first-person answer the candidate can adapt. Never raises: any failure yields
``None`` so the caller degrades to the fast outline.
"""
