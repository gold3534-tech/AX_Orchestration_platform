import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import jwt as pyjwt
from jwt import InvalidTokenError, PyJWKClient

from .supabase_client import get_supabase

_bearer = HTTPBearer(auto_error=False)
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client

    supabase_url = os.environ.get("SUPABASE_URL")
    if not supabase_url:
        return None

    _jwks_client = PyJWKClient(f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json")
    return _jwks_client


def _decode_user_from_hs256_jwt(token: str) -> dict | None:
    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not jwt_secret:
        return None

    try:
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except JWTError:
        return None

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id.strip():
        return None

    email = payload.get("email")
    return {
        "id": user_id,
        "email": email if isinstance(email, str) else None,
    }


def _decode_user_from_jwks(token: str) -> dict | None:
    jwks_client = _get_jwks_client()
    if jwks_client is None:
        return None

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            options={"verify_aud": False},
        )
    except InvalidTokenError:
        return None
    except Exception:
        return None

    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id.strip():
        return None

    email = payload.get("email")
    return {
        "id": user_id,
        "email": email if isinstance(email, str) else None,
    }


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authenticated",
        )
    return await authenticate_access_token(credentials.credentials)


async def authenticate_access_token(token: str) -> dict:
    token = token.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authenticated",
        )

    supabase = get_supabase()
    if supabase is not None:
        try:
            response = supabase.auth.get_user(token)
            if response.user is not None:
                return {"id": response.user.id, "email": response.user.email}
        except Exception:
            pass

    fallback_user = _decode_user_from_jwks(token) or _decode_user_from_hs256_jwt(token)
    if fallback_user is not None:
        return fallback_user

    if supabase is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth not configured",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
    )
