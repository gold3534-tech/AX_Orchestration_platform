import os
import threading

import pytest
from cryptography.fernet import Fernet

from api.db import models
from api.runtime.credential_resolver import (
    CredentialResolutionError,
    collect_required_credential_providers,
    resolve_credential_env,
)
from api.runtime.credential_store import encrypt_secret_payload
from api.runtime.env_overlay import runtime_env_overlay
from api.services.llm_catalog import CatalogModel


def _llm_metadata(*, temperature_supported=True, max_tokens_max=4096):
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
            llm_metadata_json=_llm_metadata(max_tokens_max=4096),
            provider_metadata_json={"docs_url": "https://platform.openai.com/docs/models"},
        ),
        CatalogModel(
            provider_key="anthropic",
            provider_display_name="Anthropic",
            provider_type="hosted",
            credential_provider="anthropic",
            model_key="anthropic/claude-3-5-sonnet-20241022",
            model_display_name="Claude 3.5 Sonnet",
            llm_metadata_json=_llm_metadata(max_tokens_max=8192),
            provider_metadata_json={"docs_url": "https://docs.anthropic.com/en/docs/about-claude/models"},
        ),
        CatalogModel(
            provider_key="ollama",
            provider_display_name="Ollama",
            provider_type="local",
            credential_provider=None,
            model_key="ollama/llama3.1",
            model_display_name="Llama 3.1",
            llm_metadata_json=_llm_metadata(max_tokens_max=32768),
            provider_metadata_json={"base_url_env": "OLLAMA_BASE_URL"},
        ),
    ]


def _add_credential(db, provider: str, api_key: str, owner_user_id: str = "test-user"):
    credential = models.Credential(
        owner_type="user",
        owner_user_id=owner_user_id,
        workspace_id=None,
        provider=provider,
        label=f"{provider} key",
        secret_ref="",
        scopes_json=[],
        status="active",
    )
    db.add(credential)
    db.flush()
    credential.secret_ref = f"secret://db/credential/{credential.id}"
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload({"api_key": api_key}),
            encryption_key_version="v1",
        )
    )
    db.commit()
    return credential


def test_default_agent_llm_requires_default_openai_credential(llm_catalog):
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": ["agent-default"],
                "task_version_ids": [],
            },
            "runtime_agents": {
                "agent-default": {
                    "version_id": "agent-default",
                    "role": "Researcher",
                    "goal": "Research",
                    "backstory": "Finds facts.",
                }
            },
            "runtime_tools": {},
            "agent_tool_links": {},
            "task_tool_links": {},
        },
        llm_catalog=llm_catalog,
    )

    assert providers == ["openai"]


def test_structured_anthropic_llm_requires_anthropic_credential(llm_catalog):
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": ["agent-anthropic"],
                "task_version_ids": [],
            },
            "runtime_agents": {
                "agent-anthropic": {
                    "llm": {
                        "provider": "anthropic",
                        "model": "anthropic/claude-3-5-sonnet-20241022",
                    }
                }
            },
            "runtime_tools": {},
            "agent_tool_links": {},
            "task_tool_links": {},
        },
        llm_catalog=llm_catalog,
    )

    assert providers == ["anthropic"]


def test_local_llm_does_not_require_api_key_credential(llm_catalog):
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": ["agent-local"],
                "task_version_ids": [],
            },
            "runtime_agents": {
                "agent-local": {"llm": {"provider": "ollama", "model": "ollama/llama3.1"}}
            },
            "runtime_tools": {},
            "agent_tool_links": {},
            "task_tool_links": {},
        },
        llm_catalog=llm_catalog,
    )

    assert providers == []


def test_collect_required_credential_providers_from_llms_and_tools():
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_agents": {
                "agent-openai": {"llm": {"provider": "openai", "model": "gpt-4o-mini"}},
                "agent-anthropic": {"llm": {"provider": "anthropic", "model": "claude-3-5-sonnet"}},
            },
            "runtime_crew": {
                "agent_version_ids": ["agent-openai", "agent-anthropic"],
                "manager_llm": {
                    "provider": "google_gemini",
                    "model": "gemini-1.5-pro",
                }
            },
            "runtime_tools": {
                "crewai.serper_dev": {
                    "credential_requirements": [
                        {
                            "provider": "serper",
                            "env_var": "SERPER_API_KEY",
                            "required": True,
                            "injection": "env",
                        }
                    ]
                },
                "crewai.file_read": {"credential_requirements": []},
            },
            "agent_tool_links": {"agent-openai": ["crewai.serper_dev"]},
            "task_tool_links": {},
        }
    )

    assert providers == ["anthropic", "google_gemini", "openai", "serper"]


def test_collect_required_credential_providers_infers_provider_from_model_names():
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": ["agent-openai", "agent-anthropic"],
                "task_version_ids": [],
                "manager_llm": "gemini-1.5-pro",
            },
            "runtime_agents": {
                "agent-openai": {"llm": "gpt-4o-mini"},
                "agent-anthropic": {"llm": {"model": "claude-3-5-sonnet"}},
            },
            "runtime_tools": {},
            "agent_tool_links": {},
            "task_tool_links": {},
        }
    )

    assert providers == ["anthropic", "google_gemini", "openai"]


def test_collect_required_credential_providers_infers_provider_from_prefixed_model_names():
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": ["agent-openai", "agent-anthropic"],
                "task_version_ids": [],
                "manager_llm": "google/gemini-1.5-pro",
                "planning_llm": "gemini/gemini-1.5-pro",
            },
            "runtime_agents": {
                "agent-openai": {"llm": "openai/gpt-4o-mini"},
                "agent-anthropic": {"llm": {"model": "anthropic/claude-3-5-sonnet"}},
            },
            "runtime_tools": {},
            "agent_tool_links": {},
            "task_tool_links": {},
        }
    )

    assert providers == ["anthropic", "google_gemini", "openai"]


def test_collect_required_credential_providers_infers_provider_from_explicit_prefix_without_family_suffix():
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": ["agent-openai", "agent-anthropic"],
                "task_version_ids": [],
                "manager_llm": "google/flash-lite",
                "planning_llm": "gemini/pro-preview",
            },
            "runtime_agents": {
                "agent-openai": {"llm": "openai/chatgpt-4o-latest"},
                "agent-anthropic": {"llm": {"model": "anthropic/sonnet-latest"}},
            },
            "runtime_tools": {},
            "agent_tool_links": {},
            "task_tool_links": {},
        }
    )

    assert providers == ["anthropic", "google_gemini", "openai"]


def test_collect_required_credential_providers_from_crew_planning_and_chat_llms():
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": [],
                "task_version_ids": [],
                "planning_llm": {
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet",
                },
                "chat_llm": {"provider": "openai", "model": "gpt-4o-mini"},
            },
            "runtime_agents": {},
            "runtime_tools": {},
            "agent_tool_links": {},
            "task_tool_links": {},
        }
    )

    assert providers == ["anthropic", "openai"]


def test_collect_required_credential_providers_from_manager_agent_reference():
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": [],
                "task_version_ids": [],
                "manager_agent_version_id": "agent-manager",
            },
            "runtime_agents": {
                "agent-manager": {
                    "role": "Manager",
                    "llm": {"provider": "anthropic", "model": "claude-3-5-sonnet"},
                }
            },
            "agent_tool_links": {"agent-manager": ["crewai.serper_dev"]},
            "task_tool_links": {},
            "runtime_tools": {
                "crewai.serper_dev": {
                    "credential_requirements": [
                        {
                            "provider": "serper",
                            "env_var": "SERPER_API_KEY",
                            "required": True,
                            "injection": "env",
                        }
                    ]
                }
            },
        }
    )

    assert providers == ["anthropic", "serper"]


def test_collect_required_credential_providers_skips_runtime_context_oauth_tools():
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": ["agent-openai"],
                "task_version_ids": [],
            },
            "runtime_agents": {
                "agent-openai": {"llm": {"provider": "openai"}},
            },
            "agent_tool_links": {"agent-openai": ["ax.google_sheets"]},
            "task_tool_links": {},
            "runtime_tools": {
                "ax.google_sheets": {
                    "credential_requirements": [
                        {
                            "provider": "google_workspace",
                            "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
                            "required": True,
                            "injection": "runtime_context",
                        }
                    ]
                }
            },
        }
    )

    assert providers == ["openai"]


def test_collect_required_credential_providers_ignores_unreachable_agents_and_tools():
    providers = collect_required_credential_providers(
        crew_snapshot={
            "runtime_crew": {
                "agent_version_ids": ["agent-openai"],
                "task_version_ids": ["task-research"],
                "manager_llm": {"provider": "google_gemini"},
            },
            "runtime_agents": {
                "agent-openai": {"llm": {"provider": "openai"}},
                "agent-anthropic-unused": {"llm": {"provider": "anthropic"}},
            },
            "runtime_tasks": {
                "task-research": {"description": "Use search."},
                "task-unused": {"description": "Unused scrape."},
            },
            "task_agent_links": {
                "task-research": "agent-openai",
                "task-unused": "agent-anthropic-unused",
            },
            "agent_tool_links": {
                "agent-openai": ["crewai.serper_dev"],
                "agent-anthropic-unused": ["crewai.firecrawl_scrape_website"],
            },
            "task_tool_links": {
                "task-unused": ["crewai.firecrawl_scrape_website"],
            },
            "runtime_tools": {
                "crewai.serper_dev": {
                    "credential_requirements": [
                        {
                            "provider": "serper",
                            "env_var": "SERPER_API_KEY",
                            "required": True,
                            "injection": "env",
                        }
                    ]
                },
                "crewai.firecrawl_scrape_website": {
                    "credential_requirements": [
                        {
                            "provider": "firecrawl",
                            "env_var": "FIRECRAWL_API_KEY",
                            "required": True,
                            "injection": "env",
                        }
                    ]
                },
            },
        }
    )

    assert providers == ["google_gemini", "openai", "serper"]


def test_resolve_credential_env_decrypts_current_user_credentials(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    _add_credential(db, "openai", "sk-openai")
    _add_credential(db, "serper", "serper-key")
    _add_credential(db, "openai", "other-openai", owner_user_id="other-user")

    env = resolve_credential_env(
        db,
        owner_user_id="test-user",
        providers=["openai", "serper"],
    )

    assert env == {"OPENAI_API_KEY": "sk-openai", "SERPER_API_KEY": "serper-key"}


def test_resolve_credential_env_reports_missing_provider(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))

    with pytest.raises(CredentialResolutionError, match="OpenAI API key is not connected"):
        resolve_credential_env(db, owner_user_id="test-user", providers=["openai"])


def test_resolve_credential_env_reports_missing_encryption_key(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    _add_credential(db, "openai", "sk-openai")
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)

    with pytest.raises(CredentialResolutionError) as exc_info:
        resolve_credential_env(db, owner_user_id="test-user", providers=["openai"])

    assert str(exc_info.value) == "Credential encryption is not configured."


def test_runtime_env_overlay_restores_previous_values(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "previous")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    with runtime_env_overlay({"OPENAI_API_KEY": "temporary", "SERPER_API_KEY": "serper"}):
        assert os.environ["OPENAI_API_KEY"] == "temporary"
        assert os.environ["SERPER_API_KEY"] == "serper"

    assert os.environ["OPENAI_API_KEY"] == "previous"
    assert "SERPER_API_KEY" not in os.environ


def test_runtime_env_overlay_restores_values_on_exception(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "previous")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="boom"):
        with runtime_env_overlay({"OPENAI_API_KEY": "temporary", "SERPER_API_KEY": "serper"}):
            assert os.environ["OPENAI_API_KEY"] == "temporary"
            assert os.environ["SERPER_API_KEY"] == "serper"
            raise RuntimeError("boom")

    assert os.environ["OPENAI_API_KEY"] == "previous"
    assert "SERPER_API_KEY" not in os.environ


def test_runtime_env_overlay_serializes_overlapping_contexts(monkeypatch):
    env_key = "RUNTIME_ENV_OVERLAY_LOCK_TEST"
    monkeypatch.delenv(env_key, raising=False)
    first_entered = threading.Event()
    allow_first_exit = threading.Event()
    second_entered = threading.Event()
    second_finished = threading.Event()
    observations = []

    def first_overlay():
        with runtime_env_overlay({env_key: "first"}):
            observations.append(("first", os.environ.get(env_key)))
            first_entered.set()
            assert allow_first_exit.wait(timeout=2)

    def second_overlay():
        assert first_entered.wait(timeout=2)
        with runtime_env_overlay({env_key: "second"}):
            observations.append(("second", os.environ.get(env_key)))
            second_entered.set()
        second_finished.set()

    first = threading.Thread(target=first_overlay)
    second = threading.Thread(target=second_overlay)
    first.start()
    second.start()

    assert first_entered.wait(timeout=2)
    second_was_blocked = not second_entered.wait(timeout=0.05)
    assert os.environ[env_key] == "first"

    allow_first_exit.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert second_was_blocked
    assert second_finished.is_set()
    assert observations == [("first", "first"), ("second", "second")]
    assert env_key not in os.environ
