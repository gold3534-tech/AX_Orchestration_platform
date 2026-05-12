from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from api.services.llm_catalog import DEFAULT_LLM_MODEL, DEFAULT_LLM_PROVIDER


HOSTED_PROVIDER_CREDENTIALS = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google_gemini": "google_gemini",
}

PREFIX_PROVIDER_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google_gemini",
    "gemini": "google_gemini",
    "ollama": "ollama",
    "llama_cpp": "llama_cpp",
}


@dataclass(frozen=True)
class LLMConfigIssue:
    code: str
    message: str
    parameter: str | None = None


@dataclass(frozen=True)
class NormalizedLLMConfig:
    source: str
    provider: str
    provider_type: str
    credential_provider: str | None
    model: str
    runtime_kwargs: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    issues: list[LLMConfigIssue] = field(default_factory=list)


def mapping_payload(payload: object) -> Mapping[str, Any] | None:
    if isinstance(payload, Mapping):
        return payload
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dumped
    return None


def infer_provider_from_model(model: str | None) -> str | None:
    if not isinstance(model, str):
        return None
    normalized = model.strip().lower()
    if not normalized:
        return None
    if "/" in normalized:
        prefix, _model_name = normalized.split("/", 1)
        return PREFIX_PROVIDER_MAP.get(prefix)
    if normalized.startswith("gpt-") or re.match(r"^o\d(?:-|$)", normalized):
        return "openai"
    if normalized.startswith("claude-"):
        return "anthropic"
    if normalized.startswith("gemini-"):
        return "google_gemini"
    return None


def normalize_llm_config(
    payload: object,
    *,
    llm_catalog: object = None,
    default_model: str = DEFAULT_LLM_MODEL,
    default_provider: str = DEFAULT_LLM_PROVIDER,
    strict: bool = False,
) -> NormalizedLLMConfig:
    mapping = mapping_payload(payload)
    raw_model = _payload_model(payload, mapping)
    source = "payload" if raw_model else "default"
    model = raw_model or default_model

    catalog_by_model = _catalog_by_model(llm_catalog)
    payload_provider = _payload_provider(payload, mapping)
    model, catalog_model = _catalog_lookup(catalog_by_model, model, payload_provider)

    provider = (
        _catalog_value(catalog_model, "provider_key")
        or payload_provider
        or infer_provider_from_model(model)
        or default_provider
    )
    provider_type = _catalog_value(catalog_model, "provider_type") or _provider_type(provider)
    credential_provider = _catalog_value(catalog_model, "credential_provider")
    if catalog_model is None:
        credential_provider = _credential_provider(provider, provider_type)
    metadata = dict(_catalog_value(catalog_model, "llm_metadata_json") or {})

    runtime_kwargs: dict[str, Any] = {"model": model}
    issues: list[LLMConfigIssue] = []
    if raw_model is None and payload_provider is not None:
        issues.append(
            LLMConfigIssue(
                code="provider_without_model_ignored",
                message="provider was ignored because no model was provided",
                parameter="provider",
            )
        )
    if catalog_model is not None and mapping is not None:
        _include_supported_parameter(
            runtime_kwargs,
            issues,
            metadata,
            model,
            mapping,
            "temperature",
            strict=strict,
        )
        _include_supported_parameter(
            runtime_kwargs,
            issues,
            metadata,
            model,
            mapping,
            "max_tokens",
            strict=strict,
        )

    return NormalizedLLMConfig(
        source=source,
        provider=provider,
        provider_type=provider_type,
        credential_provider=credential_provider,
        model=model,
        runtime_kwargs=runtime_kwargs,
        metadata=metadata,
        issues=issues,
    )


def _payload_model(payload: object, mapping: Mapping[str, Any] | None) -> str | None:
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    if mapping is None:
        return None
    for key in ("main_model", "model"):
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_provider(payload: object, mapping: Mapping[str, Any] | None) -> str | None:
    if isinstance(payload, str):
        return infer_provider_from_model(payload)
    if mapping is None:
        return None
    provider = mapping.get("provider")
    if isinstance(provider, str) and provider.strip():
        return PREFIX_PROVIDER_MAP.get(provider.strip().lower(), provider.strip())
    return infer_provider_from_model(_payload_model(payload, mapping))


def _catalog_by_model(llm_catalog: object) -> dict[str, object]:
    return {
        str(model_key): entry
        for entry in _catalog_entries(llm_catalog)
        if (model_key := _catalog_value(entry, "model_key"))
    }


def _catalog_lookup(
    catalog_by_model: Mapping[str, object],
    model: str,
    provider: str | None,
) -> tuple[str, object | None]:
    catalog_model = catalog_by_model.get(model)
    if catalog_model is not None:
        return model, catalog_model
    if "/" in model or provider is None:
        return model, None
    for prefix in _provider_model_prefixes(provider):
        candidate = f"{prefix}/{model}"
        catalog_model = catalog_by_model.get(candidate)
        if catalog_model is not None:
            return candidate, catalog_model
    return model, None


def _provider_model_prefixes(provider: str) -> tuple[str, ...]:
    if provider == "google_gemini":
        return ("gemini", "google")
    return (provider,)


def _catalog_entries(llm_catalog: object) -> Iterable[object]:
    if llm_catalog is None:
        return ()
    providers = getattr(llm_catalog, "providers", None)
    if providers is not None:
        entries = []
        for provider in providers:
            provider_payload = mapping_payload(provider) or {}
            for model in getattr(provider, "models", []) or []:
                model_payload = mapping_payload(model) or {}
                entries.append(
                    {
                        **model_payload,
                        "provider_key": model_payload.get("provider_key")
                        or provider_payload.get("provider_key"),
                        "provider_type": provider_payload.get("provider_type"),
                        "credential_provider": provider_payload.get("credential_provider"),
                        "provider_metadata_json": provider_payload.get("metadata_json", {}),
                    }
                )
        return entries
    if isinstance(llm_catalog, Mapping):
        values = llm_catalog.values()
        if all(_catalog_value(value, "model_key") for value in values):
            return llm_catalog.values()
    if isinstance(llm_catalog, Iterable) and not isinstance(llm_catalog, (str, bytes, bytearray)):
        return llm_catalog
    return ()


def _catalog_value(entry: object, name: str) -> Any:
    if entry is None:
        return None
    if isinstance(entry, Mapping):
        return entry.get(name)
    return getattr(entry, name, None)


def _provider_type(provider: str) -> str:
    if provider in HOSTED_PROVIDER_CREDENTIALS:
        return "hosted"
    return "local" if provider in {"ollama", "llama_cpp"} else "hosted"


def _credential_provider(provider: str, provider_type: str) -> str | None:
    if provider_type != "hosted":
        return None
    return HOSTED_PROVIDER_CREDENTIALS.get(provider)


def _include_supported_parameter(
    runtime_kwargs: dict[str, Any],
    issues: list[LLMConfigIssue],
    metadata: Mapping[str, Any],
    model: str,
    payload: Mapping[str, Any],
    parameter: str,
    *,
    strict: bool,
) -> None:
    if parameter not in payload:
        return
    parameter_metadata = _parameter_metadata(metadata, parameter)
    if not parameter_metadata.get("supported"):
        issues.append(
            LLMConfigIssue(
                code="unsupported_parameter_dropped",
                message=f"{parameter} is not supported for {model}",
                parameter=parameter,
            )
        )
        return

    value = payload[parameter]
    if parameter == "temperature":
        if _is_number(value):
            _raise_if_non_finite(parameter, value)
            _validate_range(parameter, value, parameter_metadata)
            runtime_kwargs[parameter] = value
        elif strict:
            raise ValueError("temperature must be a number")
        else:
            _drop_invalid_parameter(issues, parameter)
        return

    if parameter == "max_tokens":
        if _is_number(value) and not math.isfinite(value):
            raise ValueError("max_tokens must be a finite integer")
        if _is_int(value):
            _validate_range(parameter, value, parameter_metadata)
            runtime_kwargs[parameter] = value
        elif strict:
            raise ValueError("max_tokens must be an integer")
        else:
            _drop_invalid_parameter(issues, parameter)


def _parameter_metadata(metadata: Mapping[str, Any], parameter: str) -> Mapping[str, Any]:
    parameters = metadata.get("parameters")
    if not isinstance(parameters, Mapping):
        return {}
    parameter_metadata = parameters.get(parameter)
    return parameter_metadata if isinstance(parameter_metadata, Mapping) else {}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _raise_if_non_finite(parameter: str, value: int | float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{parameter} must be a finite number")


def _validate_range(parameter: str, value: int | float, metadata: Mapping[str, Any]) -> None:
    minimum = metadata.get("min")
    maximum = metadata.get("max")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f"{parameter} must be between {minimum} and {maximum}")


def _drop_invalid_parameter(issues: list[LLMConfigIssue], parameter: str) -> None:
    issues.append(
        LLMConfigIssue(
            code="invalid_parameter_dropped",
            message=f"{parameter} is invalid and was dropped",
            parameter=parameter,
        )
    )
