"""Application configuration module (shared platform layer)."""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from realmock.platform.core.constants import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_RAG_BACKEND,
    RAGBackendKind,
)

logger = logging.getLogger(__name__)

# Platform layer root directory (src/realmock/platform/): data, uploads, and.env are concentrated here
PLATFORM_ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    """Global configuration with support for environment variables and .env files.

    All environment variables use unprefixed names (CORS_ORIGINS / ENV / SECRET_KEY / TEST_MODE / …).
    """

    model_config = SettingsConfigDict(
        env_file=PLATFORM_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # LLM BYOK (default model is no longer provided to avoid misuse of public defaults when users are not configured)
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    llm_context_window: int = DEFAULT_CONTEXT_WINDOW

    # LLM embedding (optional): Fallback to above LLM BYOK configuration when None
    llm_embeddings_base: str | None = None
    llm_embeddings_key: str | None = None
    llm_embeddings_model: str | None = None

    # RAG backend selection
    rag_backend: RAGBackendKind = DEFAULT_RAG_BACKEND
    # StepFun backend only: if a StepFun vector_store already exists, reuse its ID; leave this blank to create one automatically at startup.
    stepfun_vector_store_id: str | None = None

    # Databases (two SQLite files; legacy ``database_url`` still maps to the sessions database)
    api_database_url: str = f"sqlite:///{PLATFORM_ROOT / 'data' / 'api.db'}"
    sessions_database_url: str = f"sqlite:///{PLATFORM_ROOT / 'data' / 'sessions.db'}"
    database_url: str = f"sqlite:///{PLATFORM_ROOT / 'data' / 'sessions.db'}"
    upload_dir: str = str(PLATFORM_ROOT / "uploads")
    cors_origins: str = Field(
        # Port planning (configured through.env, the default value is only local):
        #   Default aggregation form: front-end + back-end single-process aggregation (8080 / 8081);
        #   Independent running form: api 8081 / agent 8082 / interview 8083.
        default="http://localhost:8080,http://127.0.0.1:8080",
    )
    # The default is only the local machine; for LAN debugging, please explicitly set HOST=0.0.0.0
    host: str = "127.0.0.1"
    port: int = Field(default=8081, ge=1, le=65535)
    env: str = Field(
        default="dev",
        description="dev/prod, determines allow_local_llm and CORS strictness",
    )

    # Voice: By default, OpenAI is compatible with cloud transcriptions (reusing LLM BYOK);
    # Prefer local faster-whisper when filling in tiny/base/small/....
    whisper_model: str = "whisper-1"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    silence_nudge_seconds: int = Field(default=25, ge=1, le=600)

    # GitHub (interview verification tool; optional PAT, increase API quota)
    github_token: str = ""
    # Whether the interview agent enables function calling tool loop
    interview_tools_enabled: bool = True
    interview_max_tool_rounds: int = Field(default=3, ge=0, le=6)

    # LLM call: Whether to allow local/private network base_url. Production must be False.
    allow_local_llm: bool = Field(default=False)

    # WS lease: memory=in-process dict (default, single worker); database=DB table (visible across multiple workers)
    ws_lease_backend: Literal["memory", "database"] = "memory"

    # Rate limiting: comma-separated list of trusted reverse-proxy CIDRs; empty means only request.client.host.
    trusted_proxy_cidrs: str = Field(default="")

    # Current limiting backend: memory=in-process; database=shared table (consistent for multiple workers)
    ratelimit_backend: Literal["memory", "database"] = "memory"

    # Cookie Secure: None=auto (https or trusted proxy X-Forwarded-Proto=https)
    cookie_secure: bool | None = Field(default=None)

    @field_validator("cors_origins")
    @classmethod
    def _strip_cors(cls, v: str) -> str:
        """Clean up the white space on both sides of each origin to facilitate subsequent splitting."""
        return ",".join(o.strip() for o in v.split(",") if o.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [o for o in self.cors_origins.split(",") if o]

    @property
    def is_prod(self) -> bool:
        return self.env.strip().lower() == "prod"

    @property
    def trusted_proxy_cidr_list(self) -> list[str]:
        return [c.strip() for c in self.trusted_proxy_cidrs.split(",") if c.strip()]

    @property
    def effective_embeddings_base(self) -> str:
        """Parsed embeddings base: independent configuration takes precedence, otherwise it falls back to chat base."""
        return (self.llm_embeddings_base or self.llm_api_base).rstrip("/")

    @property
    def effective_embeddings_key(self) -> str:
        return self.llm_embeddings_key or self.llm_api_key

    @property
    def effective_embeddings_model(self) -> str:
        return self.llm_embeddings_model or self.llm_model

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> "Settings":
        """Cross-field configuration validation."""
        # legacy DATABASE_URL: if explicitly set to a path different from the default sessions path, sync it to the sessions database
        import os

        legacy = os.environ.get("DATABASE_URL")
        if legacy and legacy != self.sessions_database_url:
            object.__setattr__(self, "sessions_database_url", legacy)
            object.__setattr__(self, "database_url", legacy)
        if self.is_prod and self.allow_local_llm:
            raise ValueError("Allow_local_llm=True is not allowed in production environment (env=prod)")
        if self.rag_backend == RAGBackendKind.STEPFUN and not self.stepfun_vector_store_id:
            logger.warning(
                "rag_backend=stepfun but stepfun_vector_store_id is not configured; startup will attempt to create a vector store automatically"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
