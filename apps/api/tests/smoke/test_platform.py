"""Platform platform layer smokes: core modules can be imported independently and the contract is correct."""

from __future__ import annotations


def test_platform_core_importable() -> None:
    import importlib

    for name in (
        "realmock.platform.config",
        "realmock.platform.core.constants",
        "realmock.platform.core.errors",
        "realmock.platform.core.security",
        "realmock.platform.core.secrets",
        "realmock.platform.core.session_auth",
        "realmock.platform.core.logging",
        "realmock.platform.core.migrate",
        "realmock.platform.core.ratelimit",
        "realmock.platform.database",
    ):
        importlib.import_module(name)

    import realmock.platform.core.secrets
    import realmock.platform.database

    assert realmock.platform.core.secrets._MASTER_SALT == b"app-master-v2"
    assert realmock.platform.database.SessionsBase is not None
    assert realmock.platform.database.ApiBase is not None


def test_platform_capabilities_importable() -> None:

    from realmock.platform.catalogs.company import get_all_companies

    assert len(get_all_companies()) >= 6


def test_platform_models_and_schemas() -> None:
    from realmock.platform.models import LLMSettings, Resume, StageConfig, UserProfile

    assert LLMSettings.__tablename__ == "llm_settings"
    assert StageConfig.__tablename__ == "stage_configs"
    assert Resume.__tablename__ == "resumes"
    assert UserProfile.__tablename__ == "user_profiles"
