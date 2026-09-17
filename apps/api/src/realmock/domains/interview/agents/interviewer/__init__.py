"""Lead interviewer agent: the opening / turn / closing streaming chain.

:mod:`runner` is the InterviewRunner facade construction; the three stream
modules own one interview phase each and delegate to the shared kernel at the
``agents`` package root (state, prompts, tool rounds, protocol). Auxiliary
interview roles live in sibling subpackages (``topology``, ``hint``).
"""
