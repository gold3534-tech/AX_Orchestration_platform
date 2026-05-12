import pytest

from api.runtime.llm_config import LLMConfigIssue, normalize_llm_config
from api.services.llm_catalog import CatalogModel


def _metadata(*, temperature_supported=True, max_tokens_max=4096, pricing=None):
    return {
        "schema_version": 1,
        "capabilities": {"streaming": True, "tool_calling": True, "json_mode": True},
        "parameters": {
            "temperature": {
                "supported": temperature_supported,
                "default": 0.7 if temperature_supported else None,
                "min": 0,
                "max": 2 if temperature_supported else None,
            },
            "max_tokens": {
                "supported": True,
                "default": 4096,
                "min": 1,
                "max": max_tokens_max,
            },
        },
        "pricing": pricing
        or {
            "currency": "USD",
            "input_per_1m_tokens": 0.15,
            "output_per_1m_tokens": 0.60,
        },
    }


@pytest.fixture
def llm_catalog():
    return [
        CatalogModel(
            provider_key="openai",
            provider_display_name="OpenAI",
            provider_type="hosted",
            credential_provider="openai",
            model_key="openai/gpt-4o-mini",
            model_display_name="GPT-4o mini",
            llm_metadata_json=_metadata(max_tokens_max=4096),
            provider_metadata_json={"docs_url": "https://platform.openai.com/docs/models"},
        ),
        CatalogModel(
            provider_key="openai",
            provider_display_name="OpenAI",
            provider_type="hosted",
            credential_provider="openai",
            model_key="openai/gpt-5",
            model_display_name="GPT-5",
            llm_metadata_json=_metadata(
                temperature_supported=False,
                max_tokens_max=4096,
                pricing={
                    "currency": "USD",
                    "input_per_1m_tokens": 1.25,
                    "output_per_1m_tokens": 10.00,
                },
            ),
            provider_metadata_json={"docs_url": "https://platform.openai.com/docs/models"},
        ),
        CatalogModel(
            provider_key="ollama",
            provider_display_name="Ollama",
            provider_type="local",
            credential_provider=None,
            model_key="ollama/llama3.1",
            model_display_name="Llama 3.1",
            llm_metadata_json=_metadata(
                max_tokens_max=32768,
                pricing={
                    "currency": "USD",
                    "input_per_1m_tokens": 0,
                    "output_per_1m_tokens": 0,
                },
            ),
            provider_metadata_json={"base_url_env": "OLLAMA_BASE_URL"},
        ),
    ]


def test_normalize_none_uses_default_catalog_model(llm_catalog):
    normalized = normalize_llm_config(None, llm_catalog=llm_catalog)

    assert normalized.source == "default"
    assert normalized.provider == "openai"
    assert normalized.provider_type == "hosted"
    assert normalized.credential_provider == "openai"
    assert normalized.model == "openai/gpt-4o-mini"
    assert normalized.runtime_kwargs == {"model": "openai/gpt-4o-mini"}
    assert normalized.metadata["pricing"]["input_per_1m_tokens"] == 0.15
    assert normalized.issues == []


def test_structured_llm_keeps_supported_temperature_and_max_tokens(llm_catalog):
    normalized = normalize_llm_config(
        {"provider": "openai", "model": "openai/gpt-4o-mini", "temperature": 0.3, "max_tokens": 1024},
        llm_catalog=llm_catalog,
    )

    assert normalized.source == "payload"
    assert normalized.provider == "openai"
    assert normalized.runtime_kwargs == {
        "model": "openai/gpt-4o-mini",
        "temperature": 0.3,
        "max_tokens": 1024,
    }
    assert normalized.issues == []


def test_structured_unprefixed_model_resolves_catalog_model_with_supported_parameters(llm_catalog):
    normalized = normalize_llm_config(
        {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.2, "max_tokens": 1024},
        llm_catalog=llm_catalog,
    )

    assert normalized.source == "payload"
    assert normalized.provider == "openai"
    assert normalized.model == "openai/gpt-4o-mini"
    assert normalized.runtime_kwargs == {
        "model": "openai/gpt-4o-mini",
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    assert normalized.issues == []


def test_provider_without_model_uses_default_model_and_records_issue(llm_catalog):
    normalized = normalize_llm_config({"provider": "anthropic"}, llm_catalog=llm_catalog)

    assert normalized.source == "default"
    assert normalized.provider == "openai"
    assert normalized.model == "openai/gpt-4o-mini"
    assert normalized.runtime_kwargs == {"model": "openai/gpt-4o-mini"}
    assert normalized.issues == [
        LLMConfigIssue(
            code="provider_without_model_ignored",
            message="provider was ignored because no model was provided",
            parameter="provider",
        )
    ]


def test_unsupported_temperature_is_dropped_with_issue(llm_catalog):
    normalized = normalize_llm_config(
        {"model": "openai/gpt-5", "temperature": 0.3, "max_tokens": 2048},
        llm_catalog=llm_catalog,
    )

    assert normalized.runtime_kwargs == {"model": "openai/gpt-5", "max_tokens": 2048}
    assert normalized.issues == [
        LLMConfigIssue(
            code="unsupported_parameter_dropped",
            message="temperature is not supported for openai/gpt-5",
            parameter="temperature",
        )
    ]


def test_out_of_range_max_tokens_raises_in_strict_mode(llm_catalog):
    with pytest.raises(ValueError, match="max_tokens must be between 1 and 4096"):
        normalize_llm_config(
            {"model": "openai/gpt-4o-mini", "max_tokens": 4097},
            llm_catalog=llm_catalog,
            strict=True,
        )


def test_temperature_nan_raises_value_error(llm_catalog):
    with pytest.raises(ValueError, match="temperature must be a finite number"):
        normalize_llm_config(
            {"model": "openai/gpt-4o-mini", "temperature": float("nan")},
            llm_catalog=llm_catalog,
        )


def test_legacy_anthropic_string_infers_provider_without_catalog_match(llm_catalog):
    normalized = normalize_llm_config(
        "anthropic/claude-3-5-sonnet-20241022",
        llm_catalog=llm_catalog,
    )

    assert normalized.source == "payload"
    assert normalized.provider == "anthropic"
    assert normalized.provider_type == "hosted"
    assert normalized.credential_provider == "anthropic"
    assert normalized.model == "anthropic/claude-3-5-sonnet-20241022"
    assert normalized.runtime_kwargs == {"model": "anthropic/claude-3-5-sonnet-20241022"}


def test_local_ollama_model_has_no_credential_provider(llm_catalog):
    normalized = normalize_llm_config(
        {"model": "ollama/llama3.1", "temperature": 0.8},
        llm_catalog=llm_catalog,
    )

    assert normalized.provider == "ollama"
    assert normalized.provider_type == "local"
    assert normalized.credential_provider is None
    assert normalized.runtime_kwargs == {"model": "ollama/llama3.1", "temperature": 0.8}
