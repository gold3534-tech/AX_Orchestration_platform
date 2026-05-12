from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CredentialProvider:
    provider: str
    label: str
    env_var: str
    capabilities: tuple[str, ...]
    auth_type: str = "api_key"


SUPPORTED_CREDENTIAL_PROVIDERS: dict[str, CredentialProvider] = {
    "openai": CredentialProvider(
        provider="openai",
        label="OpenAI",
        env_var="OPENAI_API_KEY",
        capabilities=("llm", "vision", "image_generation"),
    ),
    "anthropic": CredentialProvider(
        provider="anthropic",
        label="Anthropic",
        env_var="ANTHROPIC_API_KEY",
        capabilities=("llm",),
    ),
    "google_gemini": CredentialProvider(
        provider="google_gemini",
        label="Google Gemini",
        env_var="GOOGLE_API_KEY",
        capabilities=("llm", "image_generation"),
    ),
    "serper": CredentialProvider(
        provider="serper",
        label="Serper",
        env_var="SERPER_API_KEY",
        capabilities=("web_search",),
    ),
    "firecrawl": CredentialProvider(
        provider="firecrawl",
        label="Firecrawl",
        env_var="FIRECRAWL_API_KEY",
        capabilities=("web_scrape",),
    ),
    "google_workspace": CredentialProvider(
        provider="google_workspace",
        label="Google Workspace",
        env_var="AX_GOOGLE_WORKSPACE_OAUTH",
        capabilities=("sheets", "drive", "oauth2"),
        auth_type="oauth2",
    ),
    "meta_instagram": CredentialProvider(
        provider="meta_instagram",
        label="Instagram",
        env_var="AX_META_INSTAGRAM_OAUTH",
        capabilities=("instagram_publish", "oauth2"),
        auth_type="oauth2",
    ),
}


API_KEY_CREDENTIAL_PROVIDERS: dict[str, CredentialProvider] = {
    provider: metadata
    for provider, metadata in SUPPORTED_CREDENTIAL_PROVIDERS.items()
    if metadata.auth_type == "api_key"
}


_TOOL_CREDENTIAL_REQUIREMENTS: dict[str, list[dict[str, Any]]] = {
    "crewai.serper_dev": [
        {
            "provider": "serper",
            "env_var": "SERPER_API_KEY",
            "required": True,
            "injection": "env",
        }
    ],
    "crewai.firecrawl_scrape_website": [
        {
            "provider": "firecrawl",
            "env_var": "FIRECRAWL_API_KEY",
            "required": True,
            "injection": "env",
        }
    ],
    "ax.coupang_product_scraper": [
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
    ],
    "crewai.dalle": [
        {
            "provider": "openai",
            "env_var": "OPENAI_API_KEY",
            "required": True,
            "injection": "env",
        }
    ],
    "crewai.vision": [
        {
            "provider": "openai",
            "env_var": "OPENAI_API_KEY",
            "required": True,
            "injection": "env",
        }
    ],
    "ax.google_sheets": [
        {
            "provider": "google_workspace",
            "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
            "required": True,
            "injection": "runtime_context",
        }
    ],
    "ax.nano_banana_image": [
        {
            "provider": "google_gemini",
            "env_var": "GOOGLE_API_KEY",
            "required": True,
            "injection": "env",
        }
    ],
    "ax.instagram_publish_tool": [
        {
            "provider": "meta_instagram",
            "env_var": "AX_META_INSTAGRAM_OAUTH",
            "required": True,
            "injection": "runtime_context",
        }
    ],
}


def require_supported_provider(provider: str) -> CredentialProvider:
    try:
        return SUPPORTED_CREDENTIAL_PROVIDERS[provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported credential provider: {provider}") from exc


def require_api_key_provider(provider: str) -> CredentialProvider:
    try:
        return API_KEY_CREDENTIAL_PROVIDERS[provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported API key credential provider: {provider}") from exc


def provider_label(provider: str) -> str:
    return require_supported_provider(provider).label


def provider_env_var(provider: str) -> str:
    return require_supported_provider(provider).env_var


def provider_response_payload(provider: str) -> dict[str, Any]:
    metadata = require_supported_provider(provider)
    return {
        "provider": metadata.provider,
        "label": metadata.label,
        "env_var": metadata.env_var,
        "capabilities": list(metadata.capabilities),
        "auth_type": metadata.auth_type,
    }


def tool_credential_requirements(tool_key: str) -> list[dict[str, Any]]:
    return [dict(requirement) for requirement in _TOOL_CREDENTIAL_REQUIREMENTS.get(tool_key, [])]
