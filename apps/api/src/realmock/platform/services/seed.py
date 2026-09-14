"""Initialize the LLM configuration from environment variables on startup."""

import json
import logging

from sqlalchemy.orm import Session

from realmock.platform.config import get_settings
from realmock.platform.core.constants import PipelineStage
from realmock.platform.core.secrets import encrypt_secret
from realmock.platform.services.pipeline.config import get_or_create_stage_config

logger = logging.getLogger(__name__)


def seed_llm_settings(db: Session) -> None:
    """If the database has no stage configuration and the environment variable has a Key, the reason stage will be automatically written."""
    settings = get_settings()
    if not settings.llm_api_key:
        return

    reason = get_or_create_stage_config(db, PipelineStage.REASON)
    if reason.api_key:
        return

    reason.api_base = settings.llm_api_base
    reason.api_key = encrypt_secret(settings.llm_api_key) or ""
    reason.model = settings.llm_model
    reason.max_tokens = settings.llm_max_tokens
    reason.context_window = settings.llm_context_window
    reason.provider = ""
    reason.extras = json.dumps({"source": "environment"}, ensure_ascii=False)
    db.commit()
    logger.info("Processor configuration has been initialized from environment variables (api_key has been encrypted and stored in the database)")
