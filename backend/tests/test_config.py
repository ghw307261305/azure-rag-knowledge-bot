from dataclasses import replace

import pytest

from app.services.config import get_settings, validate_settings


def test_validate_settings_accepts_mock_mode_without_external_services() -> None:
    validate_settings(replace(get_settings(), rag_mode="mock"))


def test_validate_settings_rejects_missing_local_knowledge_directory(tmp_path) -> None:
    settings = replace(
        get_settings(),
        rag_mode="local",
        knowledge_dir=str(tmp_path / "missing"),
    )

    with pytest.raises(ValueError, match="KNOWLEDGE_DIR does not exist"):
        validate_settings(settings)


def test_validate_settings_rejects_empty_local_knowledge_directory(tmp_path) -> None:
    settings = replace(get_settings(), rag_mode="local", knowledge_dir=str(tmp_path))

    with pytest.raises(ValueError, match="contains no Markdown files"):
        validate_settings(settings)


def test_validate_settings_rejects_incomplete_azure_configuration() -> None:
    settings = replace(
        get_settings(),
        rag_mode="azure",
        azure_openai_endpoint="",
        azure_openai_api_key="",
        azure_openai_chat_deployment="",
        azure_openai_embedding_deployment="",
        azure_search_endpoint="",
        azure_search_api_key="",
        azure_search_index_name="",
    )

    with pytest.raises(ValueError, match="Missing required settings") as error:
        validate_settings(settings)

    assert "AZURE_OPENAI_ENDPOINT" in str(error.value)
    assert "AZURE_SEARCH_ENDPOINT" in str(error.value)


def test_validate_settings_rejects_short_local_jwt_secret() -> None:
    settings = replace(
        get_settings(),
        auth_mode="local_jwt",
        local_jwt_secret="too-short",
    )

    with pytest.raises(ValueError, match="at least 32 characters"):
        validate_settings(settings)
