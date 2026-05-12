from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from api.db.models import Credential, CredentialSecret
from api.runtime.llm_config import infer_provider_from_model, normalize_llm_config
from api.runtime.credential_providers import (
    SUPPORTED_CREDENTIAL_PROVIDERS,
    provider_env_var,
    provider_label,
    require_api_key_provider,
    require_supported_provider,
)
from api.runtime.credential_store import (
    CredentialEncryptionError,
    CredentialEncryptionNotConfiguredError,
    decrypt_secret_payload,
)
from api.services.llm_catalog import CatalogModel


class CredentialResolutionError(ValueError):
    pass


def _mapping_payload(payload: object) -> Mapping[str, Any] | None:
    if isinstance(payload, Mapping):
        return payload
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    return None


def _llm_provider(payload: object) -> str | None:
    if isinstance(payload, str) and payload.strip():
        value = payload.strip()
        return value if value in _llm_provider_keys() else _llm_provider_from_model(value)
    mapping = _mapping_payload(payload)
    if mapping is None:
        return None
    provider = mapping.get("provider")
    if isinstance(provider, str) and provider.strip():
        return provider.strip()
    for model_key in ("model", "main_model"):
        model = mapping.get(model_key)
        if isinstance(model, str) and model.strip():
            inferred_provider = _llm_provider_from_model(model.strip())
            if inferred_provider is not None:
                return inferred_provider
    return None


def _llm_provider_keys() -> set[str]:
    return {
        key
        for key, definition in SUPPORTED_CREDENTIAL_PROVIDERS.items()
        if "llm" in definition.capabilities
    }


def _llm_provider_from_model(model: str) -> str | None:
    return infer_provider_from_model(model)


def _credential_requirements(payload: object) -> Sequence[object]:
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return payload
    return ()


def _string_sequence(payload: object) -> set[str]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes, bytearray)):
        return set()
    return {item.strip() for item in payload if isinstance(item, str) and item.strip()}


def _linked_agent_ids(task_agent_links: object, task_ids: set[str]) -> set[str]:
    if not isinstance(task_agent_links, Mapping):
        return set()
    agent_ids: set[str] = set()
    for task_id in task_ids:
        agent_id = task_agent_links.get(task_id)
        if isinstance(agent_id, str) and agent_id.strip():
            agent_ids.add(agent_id.strip())
    return agent_ids


def _linked_tool_keys(tool_links: object, owner_ids: set[str]) -> set[str]:
    if not isinstance(tool_links, Mapping):
        return set()
    tool_keys: set[str] = set()
    for owner_id in owner_ids:
        linked_tools = tool_links.get(owner_id)
        if isinstance(linked_tools, str) and linked_tools.strip():
            tool_keys.add(linked_tools.strip())
            continue
        tool_keys.update(_string_sequence(linked_tools))
    return tool_keys


def _add_normalized_credential_provider(
    providers: set[str],
    payload: object,
    *,
    llm_catalog: Mapping[str, CatalogModel] | None = None,
) -> None:
    normalized = normalize_llm_config(payload, llm_catalog=llm_catalog)
    if normalized.credential_provider is not None:
        providers.add(normalized.credential_provider)


def _add_explicit_llm_provider(providers: set[str], payload: object, llm_providers: set[str]) -> None:
    provider = _llm_provider(payload)
    if provider in llm_providers:
        providers.add(provider)


def collect_required_credential_providers(
    *,
    crew_snapshot: Mapping[str, Any],
    llm_catalog: Mapping[str, CatalogModel] | None = None,
) -> list[str]:
    providers: set[str] = set()
    llm_providers = {
        key
        for key, definition in SUPPORTED_CREDENTIAL_PROVIDERS.items()
        if "llm" in definition.capabilities
    }

    runtime_crew = crew_snapshot.get("runtime_crew")
    runtime_crew_mapping = _mapping_payload(runtime_crew) or {}
    crew_agent_ids = _string_sequence(runtime_crew_mapping.get("agent_version_ids"))
    manager_agent_version_id = runtime_crew_mapping.get("manager_agent_version_id")
    if isinstance(manager_agent_version_id, str) and manager_agent_version_id.strip():
        crew_agent_ids.add(manager_agent_version_id.strip())
    crew_task_ids = _string_sequence(runtime_crew_mapping.get("task_version_ids"))
    task_agent_links = crew_snapshot.get("task_agent_links")
    reachable_agent_ids = crew_agent_ids | _linked_agent_ids(task_agent_links, crew_task_ids)
    agent_tool_links = crew_snapshot.get("agent_tool_links") or crew_snapshot.get("tool_links")
    reachable_tool_keys = _linked_tool_keys(agent_tool_links, reachable_agent_ids)
    reachable_tool_keys.update(
        _linked_tool_keys(crew_snapshot.get("task_tool_links"), crew_task_ids)
    )

    runtime_agents = crew_snapshot.get("runtime_agents")
    if isinstance(runtime_agents, Mapping):
        for agent_id in reachable_agent_ids:
            payload = runtime_agents.get(agent_id)
            mapping = _mapping_payload(payload)
            if mapping is None:
                continue
            primary_payload = mapping.get("llm") or mapping.get("llm_config_json")
            _add_normalized_credential_provider(
                providers,
                primary_payload,
                llm_catalog=llm_catalog,
            )
            for llm_key in ("function_calling_llm", "function_calling_llm_config_json"):
                _add_explicit_llm_provider(providers, mapping.get(llm_key), llm_providers)

    if runtime_crew_mapping:
        for llm_key in (
            "manager_llm",
            "manager_llm_config_json",
            "planning_llm",
            "planning_llm_config_json",
            "chat_llm",
            "chat_llm_config_json",
        ):
            if llm_key in runtime_crew_mapping and runtime_crew_mapping.get(llm_key) is not None:
                _add_normalized_credential_provider(
                    providers,
                    runtime_crew_mapping.get(llm_key),
                    llm_catalog=llm_catalog,
                )
        for llm_key in ("function_calling_llm", "function_calling_llm_config_json"):
            _add_explicit_llm_provider(providers, runtime_crew_mapping.get(llm_key), llm_providers)

    runtime_tools = crew_snapshot.get("runtime_tools")
    if isinstance(runtime_tools, Mapping):
        for tool_key in reachable_tool_keys:
            tool_payload = runtime_tools.get(tool_key)
            tool_mapping = _mapping_payload(tool_payload)
            if tool_mapping is None:
                continue
            requirements = _credential_requirements(
                tool_mapping.get("credential_requirements")
            )
            for requirement in requirements:
                requirement_mapping = _mapping_payload(requirement)
                if requirement_mapping is None:
                    continue
                if requirement_mapping.get("required") is not True:
                    continue
                injection = requirement_mapping.get("injection")
                if isinstance(injection, str) and injection.strip() and injection.strip() != "env":
                    continue
                provider = requirement_mapping.get("provider")
                if isinstance(provider, str) and provider.strip():
                    providers.add(provider.strip())

    return sorted(providers)


def _friendly_decrypt_error(provider: str) -> CredentialResolutionError:
    return CredentialResolutionError(
        f"{provider_label(provider)} credential could not be decrypted. "
        "Replace it on the Credentials page."
    )


def resolve_credential_env(
    db: Session,
    *,
    owner_user_id: str,
    providers: list[str],
) -> dict[str, str]:
    env: dict[str, str] = {}
    for provider in providers:
        try:
            definition = require_api_key_provider(provider)
        except ValueError as exc:
            raise CredentialResolutionError(
                "A required credential provider is not supported. "
                "Update this crew's tools or LLM settings."
            ) from exc

        credential = (
            db.query(Credential)
            .filter(
                Credential.owner_type == "user",
                Credential.owner_user_id == owner_user_id,
                Credential.workspace_id.is_(None),
                Credential.provider == definition.provider,
                Credential.status == "active",
            )
            .one_or_none()
        )
        if credential is None:
            raise CredentialResolutionError(
                f"{provider_label(definition.provider)} API key is not connected. "
                "Add it on the Credentials page."
            )

        secret = (
            db.query(CredentialSecret)
            .filter(CredentialSecret.credential_id == credential.id)
            .one_or_none()
        )
        if secret is None:
            raise _friendly_decrypt_error(definition.provider)

        try:
            decrypted = decrypt_secret_payload(secret.encrypted_secret_json)
        except CredentialEncryptionNotConfiguredError as exc:
            raise CredentialResolutionError(
                "Credential encryption is not configured."
            ) from exc
        except CredentialEncryptionError as exc:
            raise _friendly_decrypt_error(definition.provider) from exc

        api_key = decrypted.get("api_key")
        if not isinstance(api_key, str) or not api_key:
            raise _friendly_decrypt_error(definition.provider)
        env[provider_env_var(definition.provider)] = api_key
    return env
