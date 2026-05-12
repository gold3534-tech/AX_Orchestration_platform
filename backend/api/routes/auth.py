import base64
import hashlib
import logging
import os
import secrets
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator
from supabase import Client, create_client

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)

_PKCE_COOKIE_NAME = "ai-oh-oauth-code-verifier"
_REDIRECT_COOKIE_NAME = "ai-oh-oauth-redirect-to"
_auth_client: Client | None = None


class PasswordLoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip()
        if "@" not in normalized:
            raise ValueError("A valid email address is required.")
        return normalized


class AuthSessionResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_at: int | None = None
    token_type: str | None = None


def _get_configured_callback_url() -> str:
    return os.environ.get("OAUTH_REDIRECT_URL", "http://localhost:3000/auth/callback")


def _get_frontend_callback_url(request: Request) -> str:
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if referer:
            parsed_referer = urlparse(referer)
            if parsed_referer.scheme and parsed_referer.netloc:
                origin = f"{parsed_referer.scheme}://{parsed_referer.netloc}"

    if origin:
        parsed_origin = urlparse(origin)
        if parsed_origin.scheme in {"http", "https"} and parsed_origin.netloc:
            return f"{parsed_origin.scheme}://{parsed_origin.netloc}/auth/callback"

    return _get_configured_callback_url()


def _create_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def _get_auth_client() -> Client | None:
    global _auth_client
    if _auth_client is not None:
        return _auth_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None

    _auth_client = create_client(url, key)
    return _auth_client


def _serialize_auth_session(session) -> AuthSessionResponse:
    return AuthSessionResponse(
        access_token=session.access_token,
        refresh_token=getattr(session, "refresh_token", None),
        expires_at=getattr(session, "expires_at", None),
        token_type=getattr(session, "token_type", None),
    )


@router.post("/password", response_model=AuthSessionResponse)
async def login_with_password(payload: PasswordLoginRequest):
    """Exchange an existing Supabase email/password account for a session."""
    supabase = _get_auth_client()
    if supabase is None:
        raise HTTPException(status_code=503, detail="Auth not configured")

    try:
        auth_response = supabase.auth.sign_in_with_password(
            {
                "email": payload.email,
                "password": payload.password,
            }
        )
    except Exception as exc:
        logger.exception("Email/password login failed")
        raise HTTPException(
            status_code=401,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        ) from exc

    session = auth_response.session
    if session is None:
        raise HTTPException(
            status_code=401,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    return _serialize_auth_session(session)


@router.get("/google")
async def login_with_google(request: Request):
    """Redirect the user to Supabase Google OAuth flow."""
    supabase_url = os.environ.get("SUPABASE_URL")
    if not supabase_url:
        raise HTTPException(status_code=503, detail="Auth not configured")

    verifier, challenge = _create_pkce_pair()
    redirect_to = _get_frontend_callback_url(request)
    authorize_url = (
        f"{supabase_url.rstrip('/')}/auth/v1/authorize?"
        + urlencode(
            {
                "provider": "google",
                "redirect_to": redirect_to,
                "code_challenge": challenge,
                "code_challenge_method": "s256",
            }
        )
    )

    response = RedirectResponse(url=authorize_url)
    response.set_cookie(
        _PKCE_COOKIE_NAME,
        verifier,
        httponly=True,
        secure=os.environ.get("OAUTH_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
        samesite="lax",
        max_age=600,
        path="/api/auth",
    )
    response.set_cookie(
        _REDIRECT_COOKIE_NAME,
        redirect_to,
        httponly=True,
        secure=os.environ.get("OAUTH_COOKIE_SECURE", "").lower() in {"1", "true", "yes"},
        samesite="lax",
        max_age=600,
        path="/api/auth",
    )
    return response


@router.get("/callback")
async def oauth_callback(request: Request, code: str | None = None):
    """Exchange a Supabase OAuth authorization code for a session."""
    if not code:
        raise HTTPException(status_code=400, detail="Missing OAuth code")

    code_verifier = request.cookies.get(_PKCE_COOKIE_NAME)
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Missing OAuth code verifier")

    redirect_to = request.cookies.get(_REDIRECT_COOKIE_NAME) or _get_frontend_callback_url(request)

    supabase = _get_auth_client()
    if supabase is None:
        raise HTTPException(status_code=503, detail="Auth not configured")

    try:
        auth_response = supabase.auth.exchange_code_for_session(
            {
                "auth_code": code,
                "code_verifier": code_verifier,
                "redirect_to": redirect_to,
            }
        )
    except Exception as exc:
        logger.exception("OAuth code exchange failed")
        raise HTTPException(status_code=401, detail="OAuth code exchange failed") from exc

    session = auth_response.session
    if session is None:
        raise HTTPException(status_code=401, detail="OAuth code exchange failed")

    response = JSONResponse(_serialize_auth_session(session).model_dump())
    response.delete_cookie(_PKCE_COOKIE_NAME, path="/api/auth")
    response.delete_cookie(_REDIRECT_COOKIE_NAME, path="/api/auth")
    return response
