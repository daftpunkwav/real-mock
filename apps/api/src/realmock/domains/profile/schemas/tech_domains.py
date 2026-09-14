"""Tech-domain list normalization and OpenAPI/ORM coerce helpers.

Responsibilities:
- Strip / dedupe domain names (order-preserving)
- Coerce ORM JSON and PUT input into list[str]
- Apply per-item max length from field_meta

Must not import FastAPI or the Update model.

The frontend ``cleanTechDomains`` helper is the TypeScript counterpart for
``string[]`` input. This module also skips non-strings and parses JSON; keep
those behaviors documented if you change either side.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from pydantic import BeforeValidator, StringConstraints

from realmock.domains.profile.schemas.field_meta import TECH_DOMAIN_ITEM_MAX

logger = logging.getLogger(__name__)

# Per-domain max length; oversized names are usually typos
DomainItem = Annotated[str, StringConstraints(max_length=TECH_DOMAIN_ITEM_MAX)]


def clean_tech_domains(domains: list[object]) -> list[str]:
    """Strip items, drop empties and duplicates (order-preserving). Non-strings are skipped."""
    seen: set[str] = set()
    out: list[str] = []
    for item in domains:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def coerce_domains_from_orm(value: object) -> object:
    """Coerce the ORM JSON string to a list before Response validation.

    Invalid JSON or a non-list value becomes ``[]`` so GET still 200s. PUT
    cannot persist an empty list (min_length=1); only POST /clear writes ``[]``.
    Do not log the payload — it may contain user-authored names.
    """
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        logger.warning(
            "Corrupt user_profiles.tech_domains JSON on profile read; returning []. length=%s",
            len(value),
        )
        return []
    if isinstance(parsed, list):
        return parsed
    logger.warning(
        "user_profiles.tech_domains JSON is not a list on profile read; returning []. json_type=%s",
        type(parsed).__name__,
    )
    return []


def normalize_update_domains(value: object) -> object:
    """PUT input: accept JSON string or list; normalize to stripped, deduped list."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        value = parsed if isinstance(parsed, list) else []
    if not isinstance(value, list):
        return value
    return clean_tech_domains(value)


OrmTechDomains = Annotated[list[str], BeforeValidator(coerce_domains_from_orm)]
UpdateTechDomains = Annotated[list[DomainItem], BeforeValidator(normalize_update_domains)]
