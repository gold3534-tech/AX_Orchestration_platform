from dataclasses import dataclass

from api.routes import auth as auth_routes


@dataclass
class FakeSession:
    access_token: str = "email-access-token"
    refresh_token: str = "email-refresh-token"
    expires_at: int = 1_772_848_800
    token_type: str = "bearer"


class FakeAuthResponse:
    def __init__(self, session=None):
        self.session = session


class FakePasswordAuth:
    def __init__(self, response=None, exc: Exception | None = None):
        self.response = response
        self.exc = exc
        self.calls = []

    def sign_in_with_password(self, credentials):
        self.calls.append(credentials)
        if self.exc is not None:
            raise self.exc
        return self.response


class FakeSupabaseClient:
    def __init__(self, auth):
        self.auth = auth


def test_password_login_returns_supabase_session(client, monkeypatch):
    fake_auth = FakePasswordAuth(response=FakeAuthResponse(FakeSession()))
    monkeypatch.setattr(auth_routes, "_get_auth_client", lambda: FakeSupabaseClient(fake_auth))

    response = client.post(
        "/api/auth/password",
        json={"email": "user@example.com", "password": "correct-password"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "email-access-token",
        "refresh_token": "email-refresh-token",
        "expires_at": 1_772_848_800,
        "token_type": "bearer",
    }
    assert fake_auth.calls == [
        {"email": "user@example.com", "password": "correct-password"}
    ]


def test_password_login_rejects_invalid_credentials(client, monkeypatch):
    fake_auth = FakePasswordAuth(exc=RuntimeError("invalid login credentials"))
    monkeypatch.setattr(auth_routes, "_get_auth_client", lambda: FakeSupabaseClient(fake_auth))

    response = client.post(
        "/api/auth/password",
        json={"email": "user@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "이메일 또는 비밀번호가 올바르지 않습니다."
    }


def test_password_login_rejects_missing_session(client, monkeypatch):
    fake_auth = FakePasswordAuth(response=FakeAuthResponse(session=None))
    monkeypatch.setattr(auth_routes, "_get_auth_client", lambda: FakeSupabaseClient(fake_auth))

    response = client.post(
        "/api/auth/password",
        json={"email": "user@example.com", "password": "correct-password"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "이메일 또는 비밀번호가 올바르지 않습니다."
    }


def test_password_login_returns_503_when_auth_is_not_configured(client, monkeypatch):
    monkeypatch.setattr(auth_routes, "_get_auth_client", lambda: None)

    response = client.post(
        "/api/auth/password",
        json={"email": "user@example.com", "password": "correct-password"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Auth not configured"}


def test_password_login_validates_required_fields(client):
    response = client.post("/api/auth/password", json={"email": ""})

    assert response.status_code == 422
