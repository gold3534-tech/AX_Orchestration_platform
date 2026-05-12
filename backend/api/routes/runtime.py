from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.dependencies import get_current_user
from api.schemas.runtime import (
    AuthenticatedUser,
    CredentialCreate,
    CredentialProviderUpsert,
    CredentialResponse,
    ExecutionBindingCreate,
    ExecutionBindingResponse,
)
from api.services.runtime import (
    RuntimeConflictError,
    create_credential,
    create_execution_binding,
    list_credentials,
    revoke_provider_credential,
    upsert_provider_credential,
)

router = APIRouter(prefix="/api", tags=["runtime"])


@router.get("/credentials", response_model=list[CredentialResponse])
def list_credentials_route(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return [
        CredentialResponse(
            id=credential.id,
            label=credential.label,
            provider=credential.provider,
            enabled=credential.enabled,
            created_at=credential.created_at,
            updated_at=credential.updated_at,
        )
        for credential in list_credentials(db, owner_user_id=current_user["id"])
    ]


@router.post("/credentials", response_model=CredentialResponse, status_code=status.HTTP_201_CREATED)
def create_credential_route(
    payload: CredentialCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        credential = create_credential(db, payload, owner_user_id=current_user["id"])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return CredentialResponse(
        id=credential.id,
        label=credential.label,
        provider=credential.provider,
        enabled=credential.enabled,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.put("/credentials/{provider}", response_model=CredentialResponse)
def upsert_provider_credential_route(
    provider: str,
    payload: CredentialProviderUpsert,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        credential = upsert_provider_credential(
            db,
            provider=provider,
            payload=payload,
            owner_user_id=current_user["id"],
        )
    except RuntimeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return CredentialResponse(
        id=credential.id,
        label=credential.label,
        provider=credential.provider,
        enabled=credential.enabled,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


@router.delete("/credentials/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider_credential_route(
    provider: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        revoke_provider_credential(db, provider=provider, owner_user_id=current_user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/versions/{version_id}/bindings",
    response_model=ExecutionBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_execution_binding_route(
    version_id: str,
    payload: ExecutionBindingCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        created = create_execution_binding(
            db,
            version_id=version_id,
            payload=payload,
            owner_user_id=current_user["id"],
        )
    except RuntimeConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return ExecutionBindingResponse(
        id=created.binding.id,
        subject_version_id=created.binding.subject_version_id,
        binding_type=created.binding.binding_type,
        binding_key=created.binding.binding_key,
        credential_id=created.credential.id,
        metadata_json=created.metadata_json,
        created_at=created.binding.created_at,
    )
