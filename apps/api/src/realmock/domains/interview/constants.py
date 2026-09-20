"""Mock-interview domain protocol constants.

Interview-specific enums / defaults moved down from legacy platform constants: phases, workflow types,
interviewer persona styles, follow-up categories, and the WebSocket event contract. Only ``realmock.domains.interview`` consumes these;
after the move, ``realmock.platform.core.constants`` retains only platform constants shared by all services/domains.

The frontend ``src/config/*.ts`` files correspond one-to-one with this module; changing any enum requires updating the frontend as well.
"""

from __future__ import annotations

from enum import StrEnum


# ── Interview Workflows / Stages ────────────────────────────────────────


class WorkflowType(StrEnum):
    TECHNICAL = "technical"
    HR = "hr"
    MANAGEMENT = "management"


class InterviewPhaseId(StrEnum):
    """Phase id used by all workflows (enumeration constraint; see ``workflows.PhaseDef`` for metadata)."""

    IDENTITY_CHECK = "identity_check"
    SELF_INTRO = "self_intro"
    BASIC_KNOWLEDGE = "basic_knowledge"
    PROJECT_DEEP_DIVE = "project_deep_dive"
    TECHNICAL_DEEP = "technical_deep"
    SYSTEM_DESIGN = "system_design"
    SCENARIO = "scenario"
    REVERSE_QA = "reverse_qa"
    SUMMARY = "summary"
    # HR
    CAREER_PLAN = "career_plan"
    TEAMWORK = "teamwork"
    PRESSURE = "pressure"
    SALARY = "salary"
    # management post
    LEADERSHIP = "leadership"
    DECISION_MAKING = "decision_making"
    CONFLICT = "conflict"
    BUSINESS = "business"


class InterviewResult(StrEnum):
    """Round verdict announced by the interviewer agent (turn protocol ``verdict``)."""

    PASSED = "passed"
    FAILED = "failed"


class ProcessStatus(StrEnum):
    """Lifecycle of a multi-round interview process."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# Hard cap on rounds within one interview process (round 1..5).
MAX_INTERVIEW_ROUNDS = 5


# ── Interviewer Persona / Style ────────────────────────────────────────


class Personality(StrEnum):
    GENTLE = "gentle"
    PROFESSIONAL = "professional"
    PRESSURE = "pressure"
    HR = "hr"
    EXPERT = "expert"


DEFAULT_PERSONALITY = Personality.PROFESSIONAL


class InterviewStyle(StrEnum):
    GUIDED = "guided"
    DEEP_DIVE = "deep_dive"
    CONTINUOUS = "continuous"
    CHALLENGING = "challenging"


DEFAULT_INTERVIEW_STYLE = InterviewStyle.DEEP_DIVE


# ── Follow-up Signal Classification ────────────────────────────────────────


class FollowupCategory(StrEnum):
    """Followup signal classification (with ``realmock.domains.interview.agents.followup`` single source of truth)."""

    VAGUE = "vague"
    MISSING_DATA = "missing_data"
    TECH_HOLE = "tech_hole"
    OFF_TOPIC = "off_topic"
    NONE = "none"


# ── WebSocket Event Contract ────────────────────────────────────────


class WSServerEvent(StrEnum):
    """WebSocket server event type (front-end ``ServerEvent`` union type one-to-one correspondence)."""

    TURN_STATE = "turn_state"
    ASSISTANT_TOKEN = "assistant_token"
    ASSISTANT_DONE = "assistant_done"
    STT_PARTIAL = "stt_partial"
    STT_FINAL = "stt_final"
    TTS_AUDIO = "tts_audio"
    TTS_FAILED = "tts_failed"
    TTS_INTERRUPTED = "tts_interrupted"
    SILENCE_NUDGE = "silence_nudge"
    REFERENCE_HINT_LOADING = "reference_hint_loading"
    REFERENCE_HINT = "reference_hint"
    REFERENCE_HINT_ERROR = "reference_hint_error"
    PHASE_CHANGED = "phase_changed"
    INTERVIEW_COMPLETE = "interview_complete"
    SERVER_PING = "server_ping"
    INFO = "info"
    ERROR = "error"
    CODING_CHALLENGE_OPEN = "coding_challenge_open"
    CODING_TEST_RESULT = "coding_test_result"
    CODING_EVAL_REPORT = "coding_eval_report"


class WSClientEvent(StrEnum):
    """WebSocket client event type (front-end ``ClientEvent`` union type one-to-one correspondence)."""

    USER_TEXT = "user_text"
    USER_TURN_END = "user_turn_end"
    STT_TEXT = "stt_text"
    USER_TYPING = "user_typing"
    SILENCE_TIMEOUT = "silence_timeout"
    BARGE_IN = "barge_in"
    REQUEST_HINT = "request_hint"
    REQUEST_FINISH = "request_finish"
    VISION_UPDATE = "vision_update"
    TTS_PLAYBACK_DONE = "tts_playback_done"
    PONG = "pong"
    # Reserved legacy inbound: accepted by the dispatcher but not emitted by
    # the first-party client (voice travels as PCM inside ``user_turn_end``).
    AUDIO_CHUNK = "audio_chunk"
    CODING_CODE_UPDATE = "coding_code_update"
    CODING_RUN_REQUEST = "coding_run_request"
    CODING_SUBMIT_REQUEST = "coding_submit_request"
