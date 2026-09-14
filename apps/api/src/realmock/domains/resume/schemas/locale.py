"""Analysis-output locale normalization and resume-text language inference.

Responsibilities:
- Map missing / blank / unknown locale values to the default ``zh-CN``
- Infer ``zh-CN`` vs ``en`` from resume body text (market search language)
- Keep the allowed set in one place (``limits.ANALYSIS_LOCALES``)

Must not import FastAPI, ORM, or Pydantic models.
"""

from __future__ import annotations

import re

from realmock.domains.resume.schemas.limits import (
    ANALYSIS_LOCALES,
    DEFAULT_ANALYSIS_LOCALE,
)

# Enough CJK to outrank a Chinese personal name (2–3 chars) on an otherwise
# English resume; a short Chinese title plus body still clears this.
_MIN_CJK_CHARS = 8
_MIN_LATIN_CHARS = 20
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LOCALE_SAMPLE_CHARS = 8_000


def normalize_analysis_locale(locale: str | None) -> str:
    """Return a supported analysis locale; unknown values fall back to zh-CN."""
    if not locale or not str(locale).strip():
        return DEFAULT_ANALYSIS_LOCALE
    text = str(locale).strip()
    return text if text in ANALYSIS_LOCALES else DEFAULT_ANALYSIS_LOCALE


def infer_resume_text_locale(*parts: str | None) -> str:
    """Infer market-search language from resume text, not the UI locale.

    CJK-heavy samples map to ``zh-CN``; Latin-heavy samples with little CJK
    map to ``en``. Empty / tiny input keeps ``DEFAULT_ANALYSIS_LOCALE``.
    """
    text = "\n".join(p for p in parts if p)
    if not text.strip():
        return DEFAULT_ANALYSIS_LOCALE
    sample = text[:_LOCALE_SAMPLE_CHARS]
    cjk = len(_CJK_RE.findall(sample))
    latin = sum(1 for ch in sample if ch.isascii() and ch.isalpha())
    if cjk >= _MIN_CJK_CHARS:
        return "zh-CN"
    if latin >= _MIN_LATIN_CHARS:
        return "en"
    return DEFAULT_ANALYSIS_LOCALE
