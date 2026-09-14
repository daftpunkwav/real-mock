"""API Key desensitization (covering mainstream forms)."""

from __future__ import annotations


def _looks_like_api_key(v: str) -> bool:
    lowered = v.lower()
    if lowered.startswith("aiza"):
        return True
    if v.startswith("sk-ant-"):
        return True
    return v.startswith("sk-") or v.startswith("sk_")


def _looks_like_secret(v: str) -> bool:
    """Heuristic: determine whether a string looks like a secret (API Key, token, UUID, etc.).

    Heuristic rules:

    - Length must be ``>= 20`` (typical API Keys are much longer);
    - Must contain at least one ASCII letter / digit;
    - Must contain both letters and digits (to avoid misclassifying ordinary short phrases);
    - Must not contain spaces (to avoid truncation mistakes).
    """
    if len(v) < 20 or " " in v:
        return False
    has_letter = any(c.isalpha() for c in v)
    has_digit = any(c.isdigit() for c in v)
    return has_letter and has_digit


def redact_api_key(value: str | None) -> str:
    """Redact API Keys for log output.

    Covers all of the following:
    - Provider Keys (OpenAI/Anthropic/Google/StepFun);
    - ``Authorization: Bearer xxxx`` / ``authorization=xxxx`` header forms;
    - PEM private-key blocks (including newlines);
    - tokens heuristically identified as "long enough + mixed alphanumeric + no spaces".

    Ordinary short phrases and log templates (``HTTP/%s ...``) are not misclassified.
    """
    if not value:
        return ""
    v = value.strip()
    if len(v) <= 8:
        # Short strings are not desensitized by default to avoid accidentally damaging Chinese phrases/paths/short tokens themselves.
        return v

    # PEM/certificate block: contains newlines, which the heuristic misses
    if "-----BEGIN" in v.upper():
        return "***PEM_REDACTED***"

    # For Authorization / authorization=xxx forms: keep only the scheme, then redact the entire token
    lowered = v.lower()
    if lowered.startswith("authorization"):
        scheme_idx = v.find(":") if ":" in v else v.find("=")
        if scheme_idx >= 0:
            head = v[: scheme_idx + 1]
            return f"{head} ***"
        return "Authorization ***"

    # Explicit Bearer / Token prefix
    for prefix in ("bearer ", "token ", "basic "):
        if lowered.startswith(prefix):
            return f"{prefix[:1].upper()}{prefix[1:]}***"

    if _looks_like_api_key(v):
        return f"{v[:4]}***{v[-4:]}"

    # Heuristic secrets (such as irregular tokens/UUIDs) can only use "first and last 4 characters" desensitization
    if _looks_like_secret(v):
        return f"{v[:4]}***{v[-4:]}"

    return v
