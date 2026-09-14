"""Interview option static catalogs (interview domain).

Voice-related catalogs live in ``realmock.platform.capabilities.voice.tts.options``.
This module depends on interview workflows and the platform company catalog.
"""

from __future__ import annotations

from realmock.domains.interview.schemas import WorkflowTypeOption
from realmock.platform.catalogs.company import get_all_companies
from realmock.domains.interview.agents.workflows import WORKFLOWS, phase_label_map
from realmock.platform.capabilities.voice.tts.options import AVATARS, TTS_VOICES

# Stable role / level ids — UI labels come from frontend i18n.
ROLES = [
    "backend_engineer",
    "frontend_engineer",
    "fullstack_engineer",
    "ai_engineer",
    "algorithm_engineer",
    "game_client_engineer",
    "game_server_engineer",
    "mobile_engineer",
    "devops_engineer",
    "product_manager",
    "engineering_manager",
]

LEVELS = [
    "intern",
    "junior_engineer",
    "mid_engineer",
    "senior_engineer",
    "expert",
    "architect",
]

EXPERIENCE_YEARS = [
    "0-1 years",
    "1-3 years",
    "3-5 years",
    "5-10 years",
    "10+ years",
]

PERSONALITIES = [
    {"id": "gentle", "name": "Gentle", "description": "Warm and supportive, with light guidance"},
    {"id": "professional", "name": "Professional", "description": "Precise and rigorous, depth-focused"},
    {"id": "pressure", "name": "Pressure", "description": "High-pressure probing, stress-interview style"},
    {"id": "hr", "name": "HR", "description": "Soft skills and culture fit"},
    {"id": "expert", "name": "Technical expert", "description": "Deep technical focus on fundamentals"},
]

INTERVIEW_STYLES = [
    {"id": "guided", "name": "Guided", "description": "Light hints to help expand answers"},
    {"id": "deep_dive", "name": "Deep dive", "description": "Layered follow-ups to the core"},
    {"id": "continuous", "name": "Continuous probing", "description": "Stay on one point without switching"},
    {"id": "challenging", "name": "Challenging", "description": "Challenge proposals and demand justification"},
]

# phases are phase ids; UI maps them via resolvePhaseLabels / i18n
WORKFLOW_TYPES = [
    WorkflowTypeOption(id=wf.id, name=wf.name, phases=[p.id for p in wf.phases])
    for wf in WORKFLOWS.values()
]

SCENES = [
    {"id": "meeting_room", "name": "Corporate meeting room"},
    {"id": "glass_office", "name": "Glass-partition office"},
    {"id": "online_interview", "name": "Online interview room"},
    {"id": "boardroom", "name": "Boardroom"},
    {"id": "startup_loft", "name": "Startup open loft"},
    {"id": "library_corner", "name": "Quiet meeting corner"},
]


def build_options_payload() -> dict:
    """Assemble the options API response payload."""
    from realmock.platform.config import get_settings

    return {
        "roles": ROLES,
        "levels": LEVELS,
        "experience_years": EXPERIENCE_YEARS,
        "companies": get_all_companies(),
        "personalities": PERSONALITIES,
        "interview_styles": INTERVIEW_STYLES,
        "workflow_types": WORKFLOW_TYPES,
        "phase_labels": phase_label_map(),
        "avatars": AVATARS,
        "scenes": SCENES,
        "tts_voices": TTS_VOICES,
        # Frontend silence-nudge timer must match backend settings
        "silence_nudge_seconds": get_settings().silence_nudge_seconds,
    }
