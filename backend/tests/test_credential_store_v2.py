import os

import pytest
from cryptography.fernet import Fernet

from api.runtime.credential_providers import (
    API_KEY_CREDENTIAL_PROVIDERS,
    SUPPORTED_CREDENTIAL_PROVIDERS,
    provider_env_var,
    provider_label,
    require_api_key_provider,
    require_supported_provider,
    tool_credential_requirements,
)
from api.runtime.credential_store import (
    CredentialEncryptionError,
    CredentialEncryptionNotConfiguredError,
    decrypt_secret_payload,
    encrypt_secret_payload,
)


def test_provider_registry_exposes_p0_providers_and_env_vars():
    assert list(SUPPORTED_CREDENTIAL_PROVIDERS) == [
        "openai",
        "anthropic",
        "google_gemini",
        "serper",
        "firecrawl",
        "google_workspace",
        "meta_instagram",
    ]
    assert provider_label("google_gemini") == "Google Gemini"
    assert provider_label("google_workspace") == "Google Workspace"
    assert provider_label("meta_instagram") == "Instagram"
    assert provider_env_var("openai") == "OPENAI_API_KEY"
    assert provider_env_var("anthropic") == "ANTHROPIC_API_KEY"
    assert provider_env_var("google_gemini") == "GOOGLE_API_KEY"
    assert provider_env_var("serper") == "SERPER_API_KEY"
    assert provider_env_var("firecrawl") == "FIRECRAWL_API_KEY"
    assert provider_env_var("google_workspace") == "AX_GOOGLE_WORKSPACE_OAUTH"
    assert provider_env_var("meta_instagram") == "AX_META_INSTAGRAM_OAUTH"
    assert SUPPORTED_CREDENTIAL_PROVIDERS["openai"].auth_type == "api_key"
    assert SUPPORTED_CREDENTIAL_PROVIDERS["google_workspace"].auth_type == "oauth2"
    assert SUPPORTED_CREDENTIAL_PROVIDERS["meta_instagram"].auth_type == "oauth2"


def test_api_key_provider_registry_excludes_oauth_only_providers():
    assert list(API_KEY_CREDENTIAL_PROVIDERS) == [
        "openai",
        "anthropic",
        "google_gemini",
        "serper",
        "firecrawl",
    ]
    assert require_api_key_provider("openai").provider == "openai"
    with pytest.raises(ValueError, match="Unsupported API key credential provider: google_workspace"):
        require_api_key_provider("google_workspace")


def test_provider_registry_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported credential provider: github"):
        require_supported_provider("github")


def test_tool_credential_requirements_cover_p0_external_tools():
    assert tool_credential_requirements("crewai.serper_dev") == [
        {
            "provider": "serper",
            "env_var": "SERPER_API_KEY",
            "required": True,
            "injection": "env",
        }
    ]
    assert tool_credential_requirements("crewai.dalle")[0]["provider"] == "openai"
    assert tool_credential_requirements("crewai.vision")[0]["provider"] == "openai"
    assert tool_credential_requirements("crewai.firecrawl_scrape_website")[0]["provider"] == "firecrawl"
    assert tool_credential_requirements("ax.coupang_product_scraper") == [
        {
            "provider": "firecrawl",
            "env_var": "FIRECRAWL_API_KEY",
            "required": True,
            "injection": "env",
        },
        {
            "provider": "google_gemini",
            "env_var": "GOOGLE_API_KEY",
            "required": True,
            "injection": "env",
        },
    ]
    assert tool_credential_requirements("ax.google_sheets") == [
        {
            "provider": "google_workspace",
            "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
            "required": True,
            "injection": "runtime_context",
        }
    ]
    assert tool_credential_requirements("crewai.file_read") == []


def test_encrypt_secret_payload_requires_configured_key(monkeypatch):
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)

    with pytest.raises(CredentialEncryptionNotConfiguredError, match="Credential encryption is not configured."):
        encrypt_secret_payload({"api_key": "sk-test"})


def test_encrypt_secret_payload_round_trips_without_plaintext(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)

    encrypted = encrypt_secret_payload({"api_key": "sk-test-secret"})

    assert encrypted["cipher"] == "fernet"
    assert encrypted["key_version"] == "v1"
    assert "sk-test-secret" not in str(encrypted)
    assert decrypt_secret_payload(encrypted) == {"api_key": "sk-test-secret"}


def test_decrypt_secret_payload_reports_invalid_payload_without_secret(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)

    with pytest.raises(CredentialEncryptionError, match="Credential could not be decrypted."):
        decrypt_secret_payload({"cipher": "fernet", "token": "not-a-valid-token", "key_version": "v1"})
