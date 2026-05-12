import asyncio

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt

from api import dependencies


def test_get_current_user_falls_back_to_local_jwt_decode(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret")

    class BrokenAuthClient:
        class auth:
            @staticmethod
            def get_user(_token):
                raise RuntimeError("session_not_found")

    monkeypatch.setattr(dependencies, "get_supabase", lambda: BrokenAuthClient())

    token = jwt.encode(
        {
            "sub": "user-123",
            "email": "dev@example.com",
            "role": "authenticated",
        },
        "test-jwt-secret",
        algorithm="HS256",
    )

    result = asyncio.run(
        dependencies.get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
    )

    assert result == {"id": "user-123", "email": "dev@example.com"}


def test_get_current_user_returns_401_for_invalid_token(monkeypatch):
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret")
    monkeypatch.setattr(dependencies, "get_supabase", lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            dependencies.get_current_user(
                HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")
            )
        )

    assert exc_info.value.status_code == 503
