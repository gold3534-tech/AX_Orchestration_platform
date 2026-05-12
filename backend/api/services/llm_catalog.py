from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import LLMModel, LLMProvider
from api.schemas.llm_catalog import LLMCatalogResponse, LLMModelResponse, LLMProviderResponse

DEFAULT_LLM_PROVIDER = "openai"
DEFAULT_LLM_MODEL = "openai/gpt-4o-mini"

DEFAULT_PROVIDERS = [
    {
        "provider_key": "openai",
        "display_name": "OpenAI",
        "provider_type": "hosted",
        "credential_provider": "openai",
        "enabled": True,
        "sort_order": 1,
        "metadata_json": {"docs_url": "https://platform.openai.com/docs/models"},
    },
    {
        "provider_key": "anthropic",
        "display_name": "Anthropic",
        "provider_type": "hosted",
        "credential_provider": "anthropic",
        "enabled": True,
        "sort_order": 2,
        "metadata_json": {"docs_url": "https://docs.anthropic.com/en/docs/about-claude/models"},
    },
    {
        "provider_key": "google_gemini",
        "display_name": "Google Gemini",
        "provider_type": "hosted",
        "credential_provider": "google_gemini",
        "enabled": True,
        "sort_order": 3,
        "metadata_json": {"docs_url": "https://ai.google.dev/gemini-api/docs/models"},
    },
    {
        "provider_key": "ollama",
        "display_name": "Ollama",
        "provider_type": "local",
        "credential_provider": None,
        "enabled": True,
        "sort_order": 4,
        "metadata_json": {"base_url_env": "OLLAMA_BASE_URL"},
    },
    {
        "provider_key": "llama_cpp",
        "display_name": "llama.cpp",
        "provider_type": "local",
        "credential_provider": None,
        "enabled": True,
        "sort_order": 5,
        "metadata_json": {"base_url_env": "LLAMA_CPP_BASE_URL"},
    },
]

DEFAULT_MODELS = [
    {
        "provider_key": "openai",
        "model_key": "openai/gpt-4o-mini",
        "display_name": "GPT-4o mini",
        "enabled": True,
        "sort_order": 1,
        "llm_metadata_json": {
            "schema_version": 1,
            "capabilities": {"streaming": True, "tool_calling": True, "json_mode": True},
            "parameters": {
                "temperature": {"supported": True, "default": 0.7, "min": 0, "max": 2},
                "max_tokens": {"supported": True, "default": 4096, "min": 1, "max": 16384},
            },
            "pricing": {
                "currency": "USD",
                "input_per_1m_tokens": 0.15,
                "output_per_1m_tokens": 0.60,
            },
        },
    },
    {
        "provider_key": "openai",
        "model_key": "openai/gpt-4o",
        "display_name": "GPT-4o",
        "enabled": True,
        "sort_order": 2,
        "llm_metadata_json": {
            "schema_version": 1,
            "capabilities": {"streaming": True, "tool_calling": True, "json_mode": True},
            "parameters": {
                "temperature": {"supported": True, "default": 0.7, "min": 0, "max": 2},
                "max_tokens": {"supported": True, "default": 4096, "min": 1, "max": 16384},
            },
            "pricing": {
                "currency": "USD",
                "input_per_1m_tokens": 2.50,
                "output_per_1m_tokens": 10.00,
            },
        },
    },
    {
        "provider_key": "openai",
        "model_key": "openai/gpt-5",
        "display_name": "GPT-5",
        "enabled": True,
        "sort_order": 3,
        "llm_metadata_json": {
            "schema_version": 1,
            "capabilities": {"streaming": True, "tool_calling": True, "json_mode": True},
            "parameters": {
                "temperature": {"supported": False, "default": None, "min": None, "max": None},
                "max_tokens": {"supported": True, "default": 4096, "min": 1, "max": 128000},
            },
            "pricing": {
                "currency": "USD",
                "input_per_1m_tokens": 1.25,
                "output_per_1m_tokens": 10.00,
            },
        },
    },
    {
        "provider_key": "anthropic",
        "model_key": "anthropic/claude-3-5-sonnet-20241022",
        "display_name": "Claude 3.5 Sonnet",
        "enabled": True,
        "sort_order": 10,
        "llm_metadata_json": {
            "schema_version": 1,
            "capabilities": {"streaming": True, "tool_calling": True, "json_mode": True},
            "parameters": {
                "temperature": {"supported": True, "default": 0.7, "min": 0, "max": 1},
                "max_tokens": {"supported": True, "default": 4096, "min": 1, "max": 8192},
            },
            "pricing": {
                "currency": "USD",
                "input_per_1m_tokens": 3.00,
                "output_per_1m_tokens": 15.00,
            },
        },
    },
    {
        "provider_key": "google_gemini",
        "model_key": "gemini/gemini-2.5-flash",
        "display_name": "Gemini 2.5 Flash",
        "enabled": True,
        "sort_order": 20,
        "llm_metadata_json": {
            "schema_version": 1,
            "capabilities": {"streaming": True, "tool_calling": True, "json_mode": True},
            "parameters": {
                "temperature": {"supported": True, "default": 0.7, "min": 0, "max": 2},
                "max_tokens": {"supported": True, "default": 4096, "min": 1, "max": 65536},
            },
            "pricing": {
                "currency": "USD",
                "input_per_1m_tokens": 0.30,
                "output_per_1m_tokens": 2.50,
            },
        },
    },
    {
        "provider_key": "ollama",
        "model_key": "ollama/llama3.1",
        "display_name": "Llama 3.1",
        "enabled": True,
        "sort_order": 30,
        "llm_metadata_json": {
            "schema_version": 1,
            "capabilities": {"streaming": True, "tool_calling": False, "json_mode": False},
            "parameters": {
                "temperature": {"supported": True, "default": 0.7, "min": 0, "max": 2},
                "max_tokens": {"supported": True, "default": 4096, "min": 1, "max": 32768},
            },
            "pricing": {
                "currency": "USD",
                "input_per_1m_tokens": 0,
                "output_per_1m_tokens": 0,
            },
        },
    },
]


@dataclass(frozen=True)
class CatalogModel:
    provider_key: str
    provider_display_name: str
    provider_type: str
    credential_provider: str | None
    model_key: str
    model_display_name: str
    llm_metadata_json: dict
    provider_metadata_json: dict


def seed_default_llm_catalog(db: Session) -> None:
    provider_keys = [provider["provider_key"] for provider in DEFAULT_PROVIDERS]
    providers_by_key = {
        row.provider_key: row
        for row in db.query(LLMProvider).filter(LLMProvider.provider_key.in_(provider_keys)).all()
    }
    for provider in DEFAULT_PROVIDERS:
        row = providers_by_key.get(provider["provider_key"])
        if row is None:
            db.add(LLMProvider(**provider))
            continue
        row.display_name = provider["display_name"]
        row.provider_type = provider["provider_type"]
        row.credential_provider = provider["credential_provider"]
        row.enabled = provider["enabled"]
        row.sort_order = provider["sort_order"]
        row.metadata_json = provider["metadata_json"]
        db.add(row)
    db.flush()

    model_keys = [model["model_key"] for model in DEFAULT_MODELS]
    models_by_key = {
        row.model_key: row
        for row in db.query(LLMModel).filter(LLMModel.model_key.in_(model_keys)).all()
    }
    for model in DEFAULT_MODELS:
        row = models_by_key.get(model["model_key"])
        if row is None:
            db.add(LLMModel(**model))
            continue
        row.provider_key = model["provider_key"]
        row.display_name = model["display_name"]
        row.enabled = model["enabled"]
        row.sort_order = model["sort_order"]
        row.llm_metadata_json = model["llm_metadata_json"]
        db.add(row)
    db.flush()


def _insert_missing_default_llm_catalog(db: Session) -> None:
    def add_missing_row(row) -> bool:
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError:
            return False
        return True

    inserted_any = False
    provider_keys = [provider["provider_key"] for provider in DEFAULT_PROVIDERS]
    existing_provider_keys = {
        row.provider_key
        for row in db.query(LLMProvider.provider_key).filter(LLMProvider.provider_key.in_(provider_keys)).all()
    }
    for provider in DEFAULT_PROVIDERS:
        if provider["provider_key"] not in existing_provider_keys:
            inserted_any = add_missing_row(LLMProvider(**provider)) or inserted_any

    model_keys = [model["model_key"] for model in DEFAULT_MODELS]
    existing_model_keys = {
        row.model_key
        for row in db.query(LLMModel.model_key).filter(LLMModel.model_key.in_(model_keys)).all()
    }
    for model in DEFAULT_MODELS:
        if model["model_key"] not in existing_model_keys:
            inserted_any = add_missing_row(LLMModel(**model)) or inserted_any

    if inserted_any:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()


def get_enabled_llm_catalog(db: Session) -> LLMCatalogResponse:
    _insert_missing_default_llm_catalog(db)

    providers = (
        db.query(LLMProvider)
        .filter(LLMProvider.enabled.is_(True))
        .order_by(LLMProvider.sort_order.asc(), LLMProvider.provider_key.asc())
        .all()
    )
    provider_keys = [provider.provider_key for provider in providers]
    models_by_provider = {provider_key: [] for provider_key in provider_keys}
    if provider_keys:
        models = (
            db.query(LLMModel)
            .filter(
                LLMModel.enabled.is_(True),
                LLMModel.provider_key.in_(provider_keys),
            )
            .order_by(LLMModel.sort_order.asc(), LLMModel.model_key.asc())
            .all()
        )
        for model in models:
            models_by_provider.setdefault(model.provider_key, []).append(
                LLMModelResponse.model_validate(model)
            )

    return LLMCatalogResponse(
        providers=[
            LLMProviderResponse(
                provider_key=provider.provider_key,
                display_name=provider.display_name,
                provider_type=provider.provider_type,
                credential_provider=provider.credential_provider,
                enabled=provider.enabled,
                sort_order=provider.sort_order,
                metadata_json=provider.metadata_json or {},
                models=models_by_provider.get(provider.provider_key, []),
            )
            for provider in providers
        ]
    )


def load_llm_catalog_map(db: Session) -> dict[str, CatalogModel]:
    catalog = get_enabled_llm_catalog(db)
    catalog_map: dict[str, CatalogModel] = {}
    for provider in catalog.providers:
        for model in provider.models:
            catalog_map[model.model_key] = CatalogModel(
                provider_key=provider.provider_key,
                provider_display_name=provider.display_name,
                provider_type=provider.provider_type,
                credential_provider=provider.credential_provider,
                model_key=model.model_key,
                model_display_name=model.display_name,
                llm_metadata_json=model.llm_metadata_json,
                provider_metadata_json=provider.metadata_json,
            )
    return catalog_map
