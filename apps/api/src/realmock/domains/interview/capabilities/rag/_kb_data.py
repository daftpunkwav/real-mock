"""Pure data layer for the company knowledge base: no business dependencies; shared by company_rag / local_backend / tests.

Includes:
- :data:`COLLECTION_NAME` — Chroma collection name
- :func:`_build_documents` — expand BUILTIN_COMPANIES into Chroma triples
- :func:`_data_dir` — Chroma persistence directory
- :func:`format_context` — format retrieval results
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from realmock.platform.catalogs.company import BUILTIN_COMPANIES

logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    """Chroma persistence directory (the same directory as DB, unified in shared/data)."""
    from realmock.platform.config import PLATFORM_ROOT, get_settings

    settings = get_settings()
    db_path = settings.database_url.replace("sqlite:///", "")
    if db_path and not db_path.startswith(":"):
        chroma_dir = Path(db_path).parent / "chroma"
    else:
        # Scenarios such as memory libraries fall back to the shared data root
        chroma_dir = PLATFORM_ROOT / "data" / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return chroma_dir


COLLECTION_NAME = "company_interview_kb"


def _build_documents() -> tuple[list[str], list[dict[str, Any]], list[str]]:
    """Expand BUILTIN_COMPANIES into Chroma triples (texts, metadatas, ids)."""
    texts: list[str] = []
    metadatas: list[dict[str, Any]] = []
    ids: list[str] = []

    for company in BUILTIN_COMPANIES:
        cid = company["id"]
        # Slice 1: Overall style
        texts.append(
            f"{company['name']} ({cid}) Interview style: {company['style']}. "
            f"Pressure level: {company['pressure_level']}."
        )
        metadatas.append({
            "company_id": cid,
            "company_name": company["name"],
            "section": "style",
        })
        ids.append(f"{cid}::style")

        # Slice 2: Focus Areas
        texts.append(
            f"{company['name']} Key areas to inspect: {', '.join(company['focus_areas'])}."
        )
        metadatas.append({
            "company_id": cid,
            "company_name": company["name"],
            "section": "focus_areas",
        })
        ids.append(f"{cid}::focus_areas")

        # Slice 3: Typical questions (one slice for each question)
        for idx, q in enumerate(company["sample_questions"]):
            texts.append(
                f"{company['name']}Examples of typical interview questions:{q}"
            )
            metadatas.append({
                "company_id": cid,
                "company_name": company["name"],
                "section": "sample_question",
                "question_index": idx,
            })
            ids.append(f"{cid}::q::{idx}")

        # Slice 4: Interview Process
        texts.append(
            f"{company['name']}Typical interview process:{company['interview_flow']}"
        )
        metadatas.append({
            "company_id": cid,
            "company_name": company["name"],
            "section": "interview_flow",
        })
        ids.append(f"{cid}::flow")

    return texts, metadatas, ids


def format_context(hits: list[dict[str, Any]]) -> str:
    """Format the search results into Chinese context fragments that can be injected into the LLM prompt."""
    if not hits:
        return ""
    lines = ["## Enterprise knowledge base search supplement"]
    for i, hit in enumerate(hits, 1):
        meta = hit.get("metadata", {})
        section = meta.get("section", "")
        text = hit.get("text", "")
        lines.append(f"{i}. [{section}] {text}")
    return "\n".join(lines)


__all__ = [
    "COLLECTION_NAME",
    "_build_documents",
    "_data_dir",
    "format_context",
]
