"""Settings API pre-save validation: URL format and stage provider matching.

Security policy: save-time checks protocol format only — no DNS resolve or
private-net checks (local proxies / fake-ip may map public hostnames into
198.18.0.0/15 and falsely reject valid URLs; bad hostnames should surface via
the Test button's real connectivity request). Runtime egress is still gated by
``realmock.platform.core.security`` SSRF checks.
"""

from __future__ import annotations

from urllib.parse import urlparse

from realmock.platform.config import get_settings
from realmock.platform.core.constants import PipelineStage
from realmock.platform.core.errors import ApiBusinessError, get_spec, raise_error
from realmock.platform.capabilities.voice.config.catalog import find_provider, non_reasoning_provider_ids
from realmock.platform.schemas import StageConfigUpdate


def safe_base(url: str, *, label: str) -> None:
    """Validate URL protocol format only (no DNS / private-net checks).

    Base URL is typed by the user: local proxies (fake-ip) may resolve public
    domains into 198.18.0.0/15, so net-range checks would reject valid addresses;
    typos should surface via the Test button's real request, not an "unsafe URL"
    error at save time. Runtime egress remains under SSRF checks in
    ``realmock.platform.core.security``.
    """
    if not (url or "").strip():
        return
    parsed = urlparse(url.strip())
    require_https = bool(get_settings().is_prod)
    scheme_ok = parsed.scheme == "https" if require_https else parsed.scheme in ("http", "https")
    if not scheme_ok or not parsed.hostname:
        raise ApiBusinessError(
            get_spec("A0007"),
            message=(
                f"Invalid {label}: only http(s) URLs are allowed"
                + (" (production requires https)" if require_https else "")
                + "; check and retry, or use Test to verify connectivity"
            ),
        )


def validate_stage_config(stage: str, data: StageConfigUpdate) -> None:
    """Validate that the chosen provider matches the stage mode."""
    if stage == PipelineStage.RECOGNIZE:
        meta = find_provider("recognize", data.provider)
        if meta and meta.get("status") == "coming_soon":
            raise ApiBusinessError(get_spec("A4003"), message="Recognition processor is not wired yet")
    elif stage == PipelineStage.REASON:
        # Blacklist derived from catalog (single source of truth)
        if data.provider in non_reasoning_provider_ids():
            raise ApiBusinessError(
                get_spec("A4001"),
                message="Interview reasoning must use a text LLM, not ASR/TTS-only providers",
            )
        meta = find_provider("reasoning", data.provider)
        if meta and not meta.get("can_interview_reason") and meta.get("status") != "coming_soon":
            raise_error("A4001")
    elif stage == PipelineStage.SPEAK:
        meta = find_provider("speak", data.provider)
        if meta and meta.get("status") == "coming_soon":
            raise ApiBusinessError(get_spec("A4003"), message="Speech processor is not wired yet")
