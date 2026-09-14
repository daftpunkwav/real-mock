"""LLM interview execution chain: turn runner, session state, prompts, and tools.

This is the real agent loop of the interview domain (runner_opening / runner_turn /
runner_closing, tool rounds, follow-ups, verdicts). The turn state machine and media
pipeline live in :mod:`realtime`; silence-nudge templates live in
:mod:`realtime.nudge`; pluggable perception capabilities live in
:mod:`capabilities`.
"""
