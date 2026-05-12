import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from api.db.models import AssetVersion, Credential, CredentialSecret, ExecutionBinding
from api.db.models.asset import utcnow
from api.runtime.credential_providers import require_api_key_provider
from api.runtime.credential_store import encrypt_secret_payload
from api.schemas.runtime import CredentialCreate, CredentialProviderUpsert, ExecutionBindingCreate


class RuntimeConflictError(ValueError):
    pass


@dataclass(frozen=True)
class CreatedExecutionBinding:
    binding: ExecutionBinding
    credential: Credential
    metadata_json: dict


def list_credentials(db: Session, *, owner_user_id: str) -> list[Credential]:
    return (
        db.query(Credential)
        .filter(
            Credential.owner_type == "user",
            Credential.owner_user_id == owner_user_id,
            Credential.workspace_id.is_(None),
            Credential.status == "active",
        )
        .order_by(Credential.created_at.asc())
        .all()
    )


def upsert_provider_credential(
    db: Session,
    *,
    provider: str,
    payload: CredentialProviderUpsert,
    owner_user_id: str,
) -> Credential:
    definition = require_api_key_provider(provider)
    encrypted_secret_json = encrypt_secret_payload({"api_key": payload.api_key})
    label = payload.label or f"{definition.label} API Key"
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
    is_new_credential = credential is None
    if is_new_credential:
        credential = Credential(
            id=str(uuid.uuid4()),
            owner_type="user",
            owner_user_id=owner_user_id,
            workspace_id=None,
            provider=definition.provider,
            label=label,
            secret_ref="",
            scopes_json=[],
            status="active",
        )
        credential.secret_ref = f"secret://db/credential/{credential.id}"
        db.add(credential)
    else:
        credential.label = label
        credential.secret_ref = f"secret://db/credential/{credential.id}"
        credential.updated_at = utcnow()

    if is_new_credential:
        db.add(
            CredentialSecret(
                credential_id=credential.id,
                encrypted_secret_json=encrypted_secret_json,
                encryption_key_version="v1",
            )
        )
    else:
        existing_secret = (
            db.query(CredentialSecret)
            .filter(CredentialSecret.credential_id == credential.id)
            .one_or_none()
        )
        if existing_secret is None:
            db.add(
                CredentialSecret(
                    credential_id=credential.id,
                    encrypted_secret_json=encrypted_secret_json,
                    encryption_key_version="v1",
                )
            )
        else:
            existing_secret.encrypted_secret_json = encrypted_secret_json
            existing_secret.encryption_key_version = "v1"

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise RuntimeConflictError("Credential already exists for this provider.") from exc
    db.refresh(credential)
    return credential


def revoke_provider_credential(db: Session, *, provider: str, owner_user_id: str) -> None:
    definition = require_api_key_provider(provider)
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
        raise LookupError(f"Credential not found for provider: {definition.provider}")
    db.query(CredentialSecret).filter(CredentialSecret.credential_id == credential.id).delete()
    credential.status = "revoked"
    db.commit()


def create_credential(db: Session, payload: CredentialCreate, *, owner_user_id: str) -> Credential:
    api_key = payload.secret_json.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("secret_json.api_key is required")
    if not payload.enabled:
        definition = require_api_key_provider(payload.provider)
        encrypted_secret_json = encrypt_secret_payload({"api_key": api_key.strip()})
        credential = Credential(
            id=str(uuid.uuid4()),
            owner_type="user",
            owner_user_id=owner_user_id,
            workspace_id=None,
            provider=definition.provider,
            label=payload.label,
            secret_ref="",
            scopes_json=[],
            status="inactive",
        )
        credential.secret_ref = f"secret://db/credential/{credential.id}"
        db.add(credential)
        db.add(
            CredentialSecret(
                credential_id=credential.id,
                encrypted_secret_json=encrypted_secret_json,
                encryption_key_version="v1",
            )
        )
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError("Credential could not be created.") from exc
        db.refresh(credential)
        return credential
    return upsert_provider_credential(
        db,
        provider=payload.provider,
        payload=CredentialProviderUpsert(api_key=api_key, label=payload.label),
        owner_user_id=owner_user_id,
    )


def create_execution_binding(
    db: Session,
    *,
    version_id: str,
    payload: ExecutionBindingCreate,
    owner_user_id: str,
) -> CreatedExecutionBinding:
    asset_version = db.get(AssetVersion, version_id)
    if asset_version is None:
        raise LookupError(f"Version not found: {version_id}")

    credential = (
        db.query(Credential)
        .filter(
            Credential.id == payload.credential_id,
            Credential.owner_type == "user",
            Credential.owner_user_id == owner_user_id,
            Credential.workspace_id.is_(None),
            Credential.status == "active",
        )
        .one_or_none()
    )
    if credential is None or not credential.enabled:
        raise LookupError(f"Credential not found: {payload.credential_id}")

    reserved_keys = {"binding_key", "credential_id"}
    conflicting_keys = reserved_keys.intersection(payload.metadata_json)
    if conflicting_keys:
        reserved_key_list = ", ".join(sorted(conflicting_keys))
        raise ValueError(f"metadata_json must not include reserved keys: {reserved_key_list}.")

    compatibility_metadata = {
        "binding_key": payload.binding_key,
        "credential_id": credential.id,
        **payload.metadata_json,
    }

    existing_binding = (
        db.query(ExecutionBinding)
        .filter(
            ExecutionBinding.subject_version_id == asset_version.id,
            ExecutionBinding.binding_type == payload.binding_type,
            ExecutionBinding.binding_key == payload.binding_key,
        )
        .first()
    )
    if existing_binding is not None:
        raise RuntimeConflictError("Execution binding already exists.")

    binding = ExecutionBinding(
        workspace_id=asset_version.asset.workspace_id,
        subject_version_id=asset_version.id,
        binding_type=payload.binding_type,
        binding_key=payload.binding_key,
        credential_id=credential.id,
        created_by=owner_user_id,
    )
    db.add(binding)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise RuntimeConflictError("Execution binding already exists.") from exc
    db.refresh(binding)

    return CreatedExecutionBinding(
        binding=binding,
        credential=credential,
        metadata_json=compatibility_metadata,
    )
