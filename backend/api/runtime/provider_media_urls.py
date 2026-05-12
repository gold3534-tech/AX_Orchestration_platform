from __future__ import annotations

import os
import ipaddress
import re
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from sqlalchemy.orm import Session

from api.db.models import RunArtifact
from api.runtime.supabase_artifact_storage import upload_public_artifact_file

_RUN_ARTIFACT_CONTENT_PATH_RE = re.compile(r"^/api/run-artifacts/([0-9A-Fa-f-]+)/content$")

_SECRET_URL_FRAGMENTS = (
    "api_key",
    "access_token",
    "authorization",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "token",
)


def provider_media_url_for_artifact(
    *,
    artifact_id: str,
    owner_user_id: str,
    run_id: str | None = None,
    db: Session | None = None,
) -> str:
    if db is None:
        raise ValueError("Database session is required to resolve artifact media URL.")
    artifact = _owned_artifact(
        db,
        artifact_id=artifact_id,
        owner_user_id=owner_user_id,
        run_id=run_id,
    )
    if artifact.status != "available":
        raise ValueError("Provider media URL is unavailable for non-available artifacts.")

    metadata_json = artifact.metadata_json if isinstance(artifact.metadata_json, dict) else {}
    for key in (
        "provider_media_url",
        "external_resource_url",
        "download_url",
        "preview_url",
        "web_content_link",
        "web_view_link",
    ):
        value = _optional_string(metadata_json.get(key))
        if value is None:
            continue
        public_url = _public_artifact_content_url(
            value,
            artifact=artifact,
            owner_user_id=owner_user_id,
            run_id=run_id,
            db=db,
        )
        if public_url is not None:
            return public_url
        return absolute_http_provider_media_url(value)
    raise ValueError(f"Provider media URL is unavailable for artifact: {artifact_id}")


def absolute_http_provider_media_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Instagram publish requires an absolute http(s) provider media URL.")
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Instagram publish requires an absolute http(s) provider media URL.")
    if parsed.username or parsed.password:
        raise ValueError("Instagram publish requires a safe provider media URL.")
    if not _is_public_hostname(parsed.hostname):
        raise ValueError("Instagram publish requires a publicly reachable provider media URL.")
    if _contains_secret_fragment(_bounded_unquote(parsed.netloc)):
        raise ValueError("Instagram publish requires a safe provider media URL.")
    if _contains_secret_fragment(_bounded_unquote(parsed.path)):
        raise ValueError("Instagram publish requires a safe provider media URL.")
    if _contains_secret_fragment(_bounded_unquote(parsed.fragment)):
        raise ValueError("Instagram publish requires a safe provider media URL.")
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if _contains_secret_fragment(_bounded_unquote(key)) or _contains_secret_fragment(
            _bounded_unquote(item)
        ):
            raise ValueError("Instagram publish requires a safe provider media URL.")
    return value


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _public_artifact_content_url(
    value: str,
    *,
    artifact: RunArtifact,
    owner_user_id: str,
    run_id: str | None,
    db: Session,
) -> str | None:
    match = _RUN_ARTIFACT_CONTENT_PATH_RE.fullmatch(value)
    if match is None:
        return None
    if match.group(1).lower() != str(artifact.id).lower():
        raise ValueError("Artifact content URL does not match the requested artifact.")

    public_base_url = os.getenv("AX_PUBLIC_BASE_URL")
    if isinstance(public_base_url, str) and public_base_url.strip():
        public_base_url = public_base_url.strip().rstrip("/")
        absolute_http_provider_media_url(public_base_url)
        return absolute_http_provider_media_url(
            f"{public_base_url}/api/public/run-artifacts/{artifact.id}/content"
        )

    return _promote_ax_hosted_artifact_to_supabase(
        artifact=artifact,
        owner_user_id=owner_user_id,
        run_id=run_id,
        db=db,
    )


def _promote_ax_hosted_artifact_to_supabase(
    *,
    artifact: RunArtifact,
    owner_user_id: str,
    run_id: str | None,
    db: Session,
) -> str:
    path_value = artifact.storage_path or artifact.storage_reference
    uploaded = upload_public_artifact_file(
        path=Path(path_value),
        media_type=artifact.media_type,
        owner_user_id=owner_user_id,
        run_id=run_id or str(artifact.run_id),
    )
    public_url = absolute_http_provider_media_url(uploaded.public_url)
    metadata_json = dict(artifact.metadata_json or {})
    metadata_json.update(
        {
            "provider_media_url": public_url,
            "external_resource_url": public_url,
            "supabase_bucket": uploaded.bucket,
            "supabase_object_path": uploaded.object_path,
        }
    )
    artifact.metadata_json = metadata_json
    db.add(artifact)
    db.flush()
    return public_url


def _bounded_unquote(value: str, *, max_rounds: int = 8) -> str:
    decoded = value
    for _ in range(max_rounds):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    return decoded


def _contains_secret_fragment(value: str) -> bool:
    normalized = value.lower()
    return any(fragment in normalized for fragment in _SECRET_URL_FRAGMENTS)


def _is_public_hostname(hostname: str | None) -> bool:
    if not isinstance(hostname, str) or not hostname.strip():
        return False
    hostname = hostname.strip().rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False
    if hostname == "local" or hostname.endswith(".local"):
        return False
    if _is_legacy_numeric_ipv4_hostname(hostname):
        return False
    try:
        return ipaddress.ip_address(hostname).is_global
    except ValueError:
        return True


def _is_legacy_numeric_ipv4_hostname(hostname: str) -> bool:
    labels = hostname.split(".")
    if not 1 <= len(labels) <= 4:
        return False

    parts: list[tuple[int, bool]] = []
    for label in labels:
        if not label:
            return False
        parsed = _parse_ipv4_numeric_label(label)
        if parsed is None:
            return False
        part, uses_legacy_base = parsed
        if part < 0:
            return False
        parts.append((part, uses_legacy_base))

    max_last_part = 1 << (8 * (5 - len(parts)))
    nonfinal_parts = [part for part, _uses_legacy_base in parts[:-1]]
    last_part = parts[-1][0]
    if any(part > 255 for part in nonfinal_parts) or last_part >= max_last_part:
        return True

    is_canonical_dotted_decimal = len(parts) == 4 and not any(
        uses_legacy_base for _part, uses_legacy_base in parts
    )
    return not is_canonical_dotted_decimal


def _parse_ipv4_numeric_label(label: str) -> tuple[int, bool] | None:
    lower_label = label.lower()
    if lower_label.startswith("0x"):
        try:
            return int(lower_label, 16), True
        except ValueError:
            return None
    if len(label) > 1 and label.startswith("0"):
        try:
            return int(label, 8), True
        except ValueError:
            return None
    if not label.isdigit():
        return None
    return int(label, 10), False


def _owned_artifact(
    db: Session,
    *,
    artifact_id: str,
    owner_user_id: str,
    run_id: str | None,
) -> RunArtifact:
    query = db.query(RunArtifact).filter(
        RunArtifact.id == artifact_id,
        RunArtifact.owner_user_id == owner_user_id,
    )
    if run_id:
        query = query.filter(RunArtifact.run_id == run_id)
    artifact = query.one_or_none()
    if artifact is None:
        raise LookupError(f"Artifact not found: {artifact_id}")
    return artifact
