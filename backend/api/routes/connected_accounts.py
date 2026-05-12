from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.core.database import get_db
from api.dependencies import get_current_user
from api.runtime.credential_store import CredentialEncryptionNotConfiguredError
from api.schemas.runtime import (
    AuthenticatedUser,
    ConnectedAccountDisconnectResponse,
    ConnectedAccountProviderResponse,
    ConnectedAccountResponse,
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    OAuthStartPathRequest,
    OAuthStartRequest,
    OAuthStartResponse,
)
from api.services.connected_accounts import (
    OAuthStateError,
    complete_oauth_callback,
    connected_account_response,
    disconnect_connected_account,
    list_connected_accounts,
    list_oauth_providers,
    start_oauth,
)

router = APIRouter(prefix="/api/connected-accounts", tags=["connected-accounts"])


@router.get("/providers", response_model=list[ConnectedAccountProviderResponse])
def list_connected_account_providers_route(
    _current_user: AuthenticatedUser = Depends(get_current_user),
):
    return list_oauth_providers()


@router.get("", response_model=list[ConnectedAccountResponse])
def list_connected_accounts_route(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return list_connected_accounts(db, owner_user_id=current_user["id"])


def _start_oauth_response(
    db: Session,
    *,
    provider: str,
    payload: OAuthStartPathRequest,
    owner_user_id: str,
) -> OAuthStartResponse:
    result = start_oauth(db, provider=provider, payload=payload, owner_user_id=owner_user_id)
    return OAuthStartResponse(
        provider=result.provider,
        authorization_url=result.authorization_url,
        state=result.state,
        expires_at=result.expires_at,
    )


def _complete_oauth_callback_response(
    db: Session,
    *,
    provider: str,
    state: str,
    code: str,
    owner_user_id: str | None,
) -> OAuthCallbackResponse:
    completed = complete_oauth_callback(
        db,
        provider=provider,
        state=state,
        code=code,
        owner_user_id=owner_user_id,
    )
    return OAuthCallbackResponse(
        account=connected_account_response(completed.credential),
        redirect_path=completed.redirect_path,
    )


@router.post("/oauth/start", response_model=OAuthStartResponse)
def start_oauth_canonical_route(
    payload: OAuthStartRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return _start_oauth_response(
            db,
            provider=payload.provider,
            payload=OAuthStartPathRequest(scopes=payload.scopes, redirect_path=payload.redirect_path),
            owner_user_id=current_user["id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{provider}/oauth/start", response_model=OAuthStartResponse)
def start_oauth_path_alias_route(
    provider: str,
    payload: OAuthStartPathRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return _start_oauth_response(
            db,
            provider=provider,
            owner_user_id=current_user["id"],
            payload=payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/oauth/callback", response_model=OAuthCallbackResponse)
def complete_oauth_callback_canonical_route(
    provider: str,
    state: str,
    code: str,
    db: Session = Depends(get_db),
):
    try:
        return _complete_oauth_callback_response(
            db,
            provider=provider,
            state=state,
            code=code,
            owner_user_id=None,
        )
    except (CredentialEncryptionNotConfiguredError, OAuthStateError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{provider}/oauth/callback", response_model=OAuthCallbackResponse)
def complete_oauth_callback_path_get_alias_route(
    provider: str,
    state: str,
    code: str,
    db: Session = Depends(get_db),
):
    try:
        return _complete_oauth_callback_response(
            db,
            provider=provider,
            state=state,
            code=code,
            owner_user_id=None,
        )
    except (CredentialEncryptionNotConfiguredError, OAuthStateError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/{provider}/oauth/callback", response_model=OAuthCallbackResponse)
def complete_oauth_callback_path_alias_route(
    provider: str,
    payload: OAuthCallbackRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        return _complete_oauth_callback_response(
            db,
            provider=provider,
            state=payload.state,
            code=payload.code,
            owner_user_id=current_user["id"],
        )
    except (CredentialEncryptionNotConfiguredError, OAuthStateError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.delete("/{provider}", response_model=ConnectedAccountDisconnectResponse)
def disconnect_connected_account_route(
    provider: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    try:
        disconnect_connected_account(db, provider=provider, owner_user_id=current_user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return ConnectedAccountDisconnectResponse(provider=provider, disconnected=True)
