"""Resume-domain Agents.

The review Agent is the deep-evaluation loop. Process/plan tools stay here;
GitHub / search / profile / resume inspection live in platform agent tools.
"""

from realmock.domains.resume.agents.review import run_resume_review

__all__ = ["run_resume_review"]
