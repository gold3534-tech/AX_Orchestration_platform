import pytest
from sqlalchemy.orm import sessionmaker

from api.db.models import LLMModel, LLMProvider
from api.services.llm_catalog import get_enabled_llm_catalog, seed_default_llm_catalog


@pytest.fixture
def db_session(db):
    return db


def test_seed_default_llm_catalog_inserts_enabled_models(db_session):
    seed_default_llm_catalog(db_session)

    providers = db_session.query(LLMProvider).order_by(LLMProvider.sort_order.asc()).all()
    models = db_session.query(LLMModel).order_by(LLMModel.sort_order.asc()).all()

    assert [provider.provider_key for provider in providers][:3] == [
        "openai",
        "anthropic",
        "google_gemini",
    ]
    assert all(provider.enabled is True for provider in providers)
    assert all(model.enabled is True for model in models)
    assert [model.model_key for model in models[:3]] == [
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "openai/gpt-5",
    ]
    assert any(model.model_key == "openai/gpt-4o-mini" for model in models)
    assert any(model.model_key == "anthropic/claude-3-5-sonnet-20241022" for model in models)
    assert any(model.model_key == "gemini/gemini-2.5-flash" for model in models)


def test_seed_default_llm_catalog_updates_existing_rows(db_session):
    db_session.add(
        LLMProvider(
            provider_key="openai",
            display_name="Changed",
            provider_type="local",
            credential_provider=None,
            enabled=False,
            sort_order=99,
            metadata_json={"changed": True},
        )
    )
    db_session.add(
        LLMModel(
            provider_key="openai",
            model_key="openai/gpt-4o-mini",
            display_name="Changed",
            enabled=False,
            sort_order=99,
            llm_metadata_json={"changed": True},
        )
    )
    db_session.flush()

    seed_default_llm_catalog(db_session)

    provider = db_session.get(LLMProvider, "openai")
    model = db_session.query(LLMModel).filter(LLMModel.model_key == "openai/gpt-4o-mini").one()

    assert provider.display_name == "OpenAI"
    assert provider.provider_type == "hosted"
    assert provider.credential_provider == "openai"
    assert provider.enabled is True
    assert provider.sort_order == 1
    assert provider.metadata_json["docs_url"] == "https://platform.openai.com/docs/models"
    assert model.display_name == "GPT-4o mini"
    assert model.enabled is True
    assert model.sort_order == 1
    assert model.llm_metadata_json["schema_version"] == 1


def test_get_enabled_llm_catalog_returns_pricing_and_parameters(db_session):
    seed_default_llm_catalog(db_session)

    catalog = get_enabled_llm_catalog(db_session)

    openai_provider = next(provider for provider in catalog.providers if provider.provider_key == "openai")
    gpt4o_mini = next(model for model in openai_provider.models if model.model_key == "openai/gpt-4o-mini")
    gpt5 = next(model for model in openai_provider.models if model.model_key == "openai/gpt-5")

    for provider in catalog.providers:
        for model in provider.models:
            metadata = model.llm_metadata_json
            assert metadata["schema_version"] == 1
            assert isinstance(metadata["capabilities"], dict)
            assert "temperature" in metadata["parameters"]
            assert "max_tokens" in metadata["parameters"]
            assert "currency" in metadata["pricing"]
            assert "input_per_1m_tokens" in metadata["pricing"]
            assert "output_per_1m_tokens" in metadata["pricing"]

    assert gpt4o_mini.llm_metadata_json["parameters"]["temperature"]["supported"] is True
    assert gpt4o_mini.llm_metadata_json["parameters"]["max_tokens"]["default"] == 4096
    assert gpt4o_mini.llm_metadata_json["parameters"]["max_tokens"]["min"] == 1
    assert gpt4o_mini.llm_metadata_json["parameters"]["max_tokens"]["max"] == 16384
    assert "minimum" not in gpt4o_mini.llm_metadata_json["parameters"]["max_tokens"]
    assert "maximum" not in gpt4o_mini.llm_metadata_json["parameters"]["max_tokens"]
    assert gpt4o_mini.llm_metadata_json["schema_version"] == 1
    assert gpt4o_mini.llm_metadata_json["capabilities"]["streaming"] is True
    assert gpt4o_mini.llm_metadata_json["pricing"]["currency"] == "USD"
    assert gpt5.llm_metadata_json["parameters"]["temperature"]["supported"] is False
    assert gpt5.llm_metadata_json["pricing"]["input_per_1m_tokens"] is not None
    assert gpt5.llm_metadata_json["pricing"]["output_per_1m_tokens"] is not None


def test_get_enabled_llm_catalog_lazy_inserts_are_durable_across_sessions(db_session):
    catalog = get_enabled_llm_catalog(db_session)

    assert catalog.providers
    db_session.rollback()

    TestingSessionLocal = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    fresh_session = TestingSessionLocal()
    try:
        assert fresh_session.query(LLMProvider).count() == 5
        assert fresh_session.query(LLMModel).filter(LLMModel.model_key == "openai/gpt-4o-mini").count() == 1
    finally:
        fresh_session.close()


def test_get_enabled_llm_catalog_preserves_disabled_default_provider(db_session):
    seed_default_llm_catalog(db_session)
    provider = db_session.get(LLMProvider, "anthropic")
    provider.enabled = False
    db_session.flush()

    catalog = get_enabled_llm_catalog(db_session)

    assert all(provider.provider_key != "anthropic" for provider in catalog.providers)
    assert db_session.get(LLMProvider, "anthropic").enabled is False


def test_get_enabled_llm_catalog_preserves_disabled_default_model(db_session):
    seed_default_llm_catalog(db_session)
    model = db_session.query(LLMModel).filter(LLMModel.model_key == "openai/gpt-4o-mini").one()
    model.enabled = False
    db_session.flush()

    catalog = get_enabled_llm_catalog(db_session)

    openai_provider = next(provider for provider in catalog.providers if provider.provider_key == "openai")
    assert all(model.model_key != "openai/gpt-4o-mini" for model in openai_provider.models)
    assert db_session.query(LLMModel).filter(LLMModel.model_key == "openai/gpt-4o-mini").one().enabled is False


def test_llm_catalog_route_returns_enabled_models(client, auth_headers):
    response = client.get("/api/llm-catalog", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"][0]["provider_key"] == "openai"
    assert payload["providers"][0]["models"][0]["model_key"] == "openai/gpt-4o-mini"
    assert "pricing" in payload["providers"][0]["models"][0]["llm_metadata_json"]
