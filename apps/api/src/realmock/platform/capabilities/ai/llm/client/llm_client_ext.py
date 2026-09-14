"""LLMClient outbound probes and embeddings: ``test_connection`` / ``embed``.

Runtime dependency is one-way: ``llm_client`` imports this module after the class definition; this module references ``LLMClient`` only under TYPE_CHECKING.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from realmock.platform.config import get_settings
from realmock.platform.core.security import UnsafeURLError, is_safe_http_url

from .base import _is_local_allowed, _require_https
from .openai_transport import embed_texts

if TYPE_CHECKING:
    from .llm_client import LLMClient


async def test_connection(client: "LLMClient") -> tuple[bool, str]:
    """Test API connectivity (lightweight probing, no key leakage)."""
    try:
        reply = await client.chat(
            [
                {
                    "role": "system",
                    "content": "Reply with plain text only, no emojis.",
                },
                {"role": "user", "content": "Please reply: Connection successful"},
            ],
            temperature=0,
        )
        return True, reply[:100]
    except httpx.HTTPStatusError as e:
        return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        return False, str(e)


async def embed(
    client: "LLMClient",
    texts: list[str],
    *,
    model: str | None = None,
) -> list[list[float]]:
    """Call the OpenAI compatible /embeddings endpoint to return a vector for each piece of text."""
    base = get_settings().effective_embeddings_base
    if not is_safe_http_url(base, allow_local=_is_local_allowed(), require_https=_require_https()):
        raise UnsafeURLError(f"Embeddings api_base is not safe: {base}")
    return await embed_texts(
        texts=texts,
        model=model,
        api_base=client.api_base,
        api_key=client.api_key,
    )


__all__ = ["embed", "test_connection"]
