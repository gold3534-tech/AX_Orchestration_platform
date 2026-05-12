from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import sessionmaker

from api.db import models
from api.integrations.google_oauth import GoogleWorkspaceOAuthError
from api.integrations.google_workspace import (
    GOOGLE_SHEETS_SCOPE,
    GoogleSheetsClient,
    build_sheets_client_from_runtime,
    crew_snapshot_uses_google_sheets,
    google_workspace_runtime_context,
    resolve_google_sheets_runtime_token,
    runtime_oauth_redaction_values,
)
from api.runtime.credential_resolver import CredentialResolutionError
from api.runtime.credential_store import decrypt_secret_payload, encrypt_secret_payload
from api.runtime.oauth_clients import RuntimeOAuthToken
from api.tools.google_sheets_tool import AXGoogleSheetsTool, GoogleSheetsInput


class FakeSheetsClient:
    def __init__(self):
        self.calls = []

    def read_range(self, spreadsheet_id: str, range_name: str):
        self.calls.append(("read_range", spreadsheet_id, range_name))
        return [["Name"], ["AX"]]

    def append_rows(self, spreadsheet_id: str, range_name: str, values: list[list[str]]):
        self.calls.append(("append_rows", spreadsheet_id, range_name, values))
        return {"updatedRows": len(values)}

    def update_values(self, spreadsheet_id: str, range_name: str, values: list[list[str]]):
        self.calls.append(("update_values", spreadsheet_id, range_name, values))
        return {"updatedCells": sum(len(row) for row in values)}


class FakeValuesResource:
    def __init__(self):
        self.calls = []
        self.response = {}

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        self.response = {"values": [["Name"], ["AX"]]}
        return self

    def append(self, **kwargs):
        self.calls.append(("append", kwargs))
        self.response = {"updatedRows": len(kwargs["body"]["values"])}
        return self

    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        self.response = {"updatedCells": sum(len(row) for row in kwargs["body"]["values"])}
        return self

    def execute(self):
        return self.response


class FakeSheetsService:
    def __init__(self):
        self.values_resource = FakeValuesResource()

    def spreadsheets(self):
        return self

    def values(self):
        return self.values_resource


def test_google_sheets_tool_values_schema_has_typed_cell_items():
    schema = GoogleSheetsInput.model_json_schema()

    values_schema = schema["properties"]["values"]["anyOf"][0]
    cell_schema = values_schema["items"]["items"]

    assert cell_schema["anyOf"] == [
        {"type": "string"},
        {"type": "integer"},
        {"type": "number"},
        {"type": "boolean"},
        {"type": "null"},
    ]


def test_google_sheets_tool_schema_describes_safe_range_and_values_usage():
    schema = GoogleSheetsInput.model_json_schema()

    assert "A1 notation range only" in schema["properties"]["range_name"]["description"]
    assert "Do not include braces" in schema["properties"]["range_name"]["description"]
    assert 'for example [["done"]]' in schema["properties"]["values"]["description"]
    assert "products!A20:C22" in AXGoogleSheetsTool().description
    assert "Do not include braces" in AXGoogleSheetsTool().description


def test_google_sheets_tool_reads_enabled_range(monkeypatch):
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(
        "api.tools.google_sheets_tool.build_sheets_client_from_runtime",
        lambda: fake_client,
    )
    tool = AXGoogleSheetsTool()

    result = tool._run(
        operation="read_range",
        spreadsheet_id="sheet-1",
        range_name="Sheet1!A1:A2",
    )

    assert result == [["Name"], ["AX"]]
    assert fake_client.calls == [("read_range", "sheet-1", "Sheet1!A1:A2")]


def test_google_sheets_tool_rejects_disabled_append(monkeypatch):
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(
        "api.tools.google_sheets_tool.build_sheets_client_from_runtime",
        lambda: fake_client,
    )
    tool = AXGoogleSheetsTool(append_rows_enabled=False)

    with pytest.raises(ValueError, match="append_rows is disabled"):
        tool._run(
            operation="append_rows",
            spreadsheet_id="sheet-1",
            range_name="Sheet1!A1:B2",
            values=[["A", "B"]],
        )

    assert fake_client.calls == []


def test_google_sheets_tool_executes_enabled_append(monkeypatch):
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(
        "api.tools.google_sheets_tool.build_sheets_client_from_runtime",
        lambda: fake_client,
    )
    tool = AXGoogleSheetsTool(append_rows_enabled=True)

    result = tool._run(
        operation="append_rows",
        spreadsheet_id="sheet-1",
        range_name="Sheet1!A1:B1",
        values=[["A", "B"]],
    )

    assert result == {"updatedRows": 1}
    assert fake_client.calls == [("append_rows", "sheet-1", "Sheet1!A1:B1", [["A", "B"]])]


def test_google_sheets_tool_executes_enabled_update(monkeypatch):
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(
        "api.tools.google_sheets_tool.build_sheets_client_from_runtime",
        lambda: fake_client,
    )
    tool = AXGoogleSheetsTool(update_values_enabled=True)

    result = tool._run(
        operation="update_values",
        spreadsheet_id="sheet-1",
        range_name="Sheet1!A1:B1",
        values=[["A", "B"]],
    )

    assert result == {"updatedCells": 2}
    assert fake_client.calls == [("update_values", "sheet-1", "Sheet1!A1:B1", [["A", "B"]])]


def test_google_sheets_tool_rejects_disabled_update(monkeypatch):
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(
        "api.tools.google_sheets_tool.build_sheets_client_from_runtime",
        lambda: fake_client,
    )
    tool = AXGoogleSheetsTool(update_values_enabled=False)

    with pytest.raises(ValueError, match="update_values is disabled"):
        tool._run(
            operation="update_values",
            spreadsheet_id="sheet-1",
            range_name="Sheet1!A1:B1",
            values=[["A", "B"]],
        )

    assert fake_client.calls == []


def test_google_sheets_tool_rejects_values_that_are_not_rows(monkeypatch):
    monkeypatch.setattr(
        "api.tools.google_sheets_tool.build_sheets_client_from_runtime",
        lambda: pytest.fail("client should not be built"),
    )
    tool = AXGoogleSheetsTool()

    with pytest.raises(ValueError, match="values must be a list of rows"):
        tool._run(
            operation="update_values",
            spreadsheet_id="sheet-1",
            range_name="Sheet1!C5",
            values=["done"],
        )


def test_google_sheets_tool_rejects_empty_spreadsheet_id_and_range(monkeypatch):
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(
        "api.tools.google_sheets_tool.build_sheets_client_from_runtime",
        lambda: fake_client,
    )
    tool = AXGoogleSheetsTool()

    with pytest.raises(ValueError, match="spreadsheet_id must not be empty"):
        tool._run(operation="read_range", spreadsheet_id=" ", range_name="Sheet1!A:C")

    with pytest.raises(ValueError, match="range_name must not be empty"):
        tool._run(operation="read_range", spreadsheet_id="sheet-1", range_name=" ")

    assert fake_client.calls == []


def test_google_sheets_tool_trims_spreadsheet_id_and_range(monkeypatch):
    fake_client = FakeSheetsClient()
    monkeypatch.setattr(
        "api.tools.google_sheets_tool.build_sheets_client_from_runtime",
        lambda: fake_client,
    )
    tool = AXGoogleSheetsTool()

    result = tool._run(
        operation="read_range",
        spreadsheet_id=" sheet-1 ",
        range_name=" Sheet1!A:C ",
    )

    assert result == [["Name"], ["AX"]]
    assert fake_client.calls == [("read_range", "sheet-1", "Sheet1!A:C")]


def test_google_sheets_client_wraps_official_values_api():
    service = FakeSheetsService()
    client = GoogleSheetsClient(service)

    assert client.read_range("sheet-1", "Sheet1!A1:A2") == [["Name"], ["AX"]]
    assert client.append_rows("sheet-1", "Sheet1!A1:B1", [["A", "B"]]) == {"updatedRows": 1}
    assert client.update_values("sheet-1", "Sheet1!A1:B1", [["A", "B"]]) == {"updatedCells": 2}

    assert service.values_resource.calls == [
        ("get", {"spreadsheetId": "sheet-1", "range": "Sheet1!A1:A2"}),
        (
            "append",
            {
                "spreadsheetId": "sheet-1",
                "range": "Sheet1!A1:B1",
                "valueInputOption": "USER_ENTERED",
                "insertDataOption": "INSERT_ROWS",
                "body": {"values": [["A", "B"]]},
            },
        ),
        (
            "update",
            {
                "spreadsheetId": "sheet-1",
                "range": "Sheet1!A1:B1",
                "valueInputOption": "USER_ENTERED",
                "body": {"values": [["A", "B"]]},
            },
        ),
    ]


def test_google_sheets_runtime_client_uses_oauth_resolver_not_env(monkeypatch):
    calls = []
    db = object()
    monkeypatch.setenv("AX_GOOGLE_WORKSPACE_OAUTH", "must-not-be-read")

    def fake_resolver(runtime_db, *, owner_user_id, provider, required_scopes, refresh_handler=None):
        assert refresh_handler is not None
        calls.append((runtime_db, owner_user_id, provider, required_scopes))
        return SimpleNamespace(access_token="oauth-access-token")

    def fake_builder(access_token):
        calls.append(("builder", access_token))
        return "sheets-client"

    monkeypatch.setattr(
        "api.integrations.google_workspace.resolve_oauth_token_payload",
        fake_resolver,
    )
    monkeypatch.setattr(
        "api.integrations.google_workspace.build_sheets_client_from_access_token",
        fake_builder,
    )

    client = build_sheets_client_from_runtime(db=db, owner_user_id="user-1")

    assert client == "sheets-client"
    assert calls == [
        (db, "user-1", "google_workspace", [GOOGLE_SHEETS_SCOPE]),
        ("builder", "oauth-access-token"),
    ]
    assert "must-not-be-read" not in str(calls)


def test_google_sheets_runtime_context_requires_preresolved_token(monkeypatch):
    db = object()

    def fail_resolver(*args, **kwargs):
        raise AssertionError("runtime context must not lazily resolve tokens")

    monkeypatch.setattr(
        "api.integrations.google_workspace.resolve_oauth_token_payload",
        fail_resolver,
    )

    with google_workspace_runtime_context(db=db, owner_user_id="user-1"):
        with pytest.raises(
            CredentialResolutionError,
            match="Google Sheets OAuth token was not prepared",
        ):
            build_sheets_client_from_runtime(db=db, owner_user_id="user-1")


def test_google_sheets_runtime_token_refreshes_expired_access_token(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    expired_at = datetime.now(UTC) - timedelta(minutes=5)
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        provider_account_id="google_workspace",
        provider_account_label="Google Workspace",
        scopes_json=[GOOGLE_SHEETS_SCOPE],
        status="active",
        metadata_json={"display_name": "Google Workspace"},
        expires_at=expired_at,
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload(
                {
                    "access_token": "expired-access-token",
                    "refresh_token": "stored-refresh-token",
                    "expires_at": expired_at.isoformat(),
                    "token_type": "Bearer",
                }
            ),
            encryption_key_version="v1",
        )
    )
    db.commit()

    class FakeGoogleOAuthClient:
        def refresh_access_token(self, *, refresh_token: str, scopes: list[str]):
            assert refresh_token == "stored-refresh-token"
            assert scopes == [GOOGLE_SHEETS_SCOPE]
            return SimpleNamespace(
                access_token="fresh-access-token",
                refresh_token="stored-refresh-token",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                scopes=[GOOGLE_SHEETS_SCOPE],
                token_type="Bearer",
            )

    monkeypatch.setattr(
        "api.integrations.google_workspace.GoogleWorkspaceOAuthClient",
        lambda: FakeGoogleOAuthClient(),
    )

    token = resolve_google_sheets_runtime_token(
        db,
        owner_user_id="test-user",
    )

    assert token.access_token == "fresh-access-token"
    stored = db.get(models.Credential, credential.id)
    secret_payload = decrypt_secret_payload(stored.secret.encrypted_secret_json)
    assert secret_payload["access_token"] == "fresh-access-token"
    assert secret_payload["refresh_token"] == "stored-refresh-token"
    assert stored.expires_at > datetime.now(UTC)


def test_google_sheets_runtime_token_requires_refresh_token_for_expired_credentials(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    expired_at = datetime.now(UTC) - timedelta(minutes=5)
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        provider_account_id="google_workspace",
        provider_account_label="Google Workspace",
        scopes_json=[GOOGLE_SHEETS_SCOPE],
        status="active",
        metadata_json={"display_name": "Google Workspace"},
        expires_at=expired_at,
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload(
                {
                    "access_token": "expired-access-token",
                    "expires_at": expired_at.isoformat(),
                    "token_type": "Bearer",
                }
            ),
            encryption_key_version="v1",
        )
    )
    db.commit()

    with pytest.raises(CredentialResolutionError, match="refresh token is unavailable"):
        resolve_google_sheets_runtime_token(
            db,
            owner_user_id="test-user",
        )


def test_google_sheets_runtime_token_refresh_does_not_commit_unrelated_pending_objects(
    db,
    monkeypatch,
):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    expired_at = datetime.now(UTC) - timedelta(minutes=5)
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        provider_account_id="google_workspace",
        provider_account_label="Google Workspace",
        scopes_json=[GOOGLE_SHEETS_SCOPE],
        status="active",
        metadata_json={"display_name": "Google Workspace"},
        expires_at=expired_at,
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload(
                {
                    "access_token": "expired-access-token",
                    "refresh_token": "stored-refresh-token",
                    "expires_at": expired_at.isoformat(),
                    "token_type": "Bearer",
                }
            ),
            encryption_key_version="v1",
        )
    )
    db.commit()

    pending_credential = models.Credential(
        owner_type="user",
        owner_user_id="pending-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Pending Google Workspace",
        provider_account_id="pending-google-workspace",
        provider_account_label="Pending Google Workspace",
        scopes_json=[GOOGLE_SHEETS_SCOPE],
        status="active",
        metadata_json={"display_name": "Pending Google Workspace"},
        secret_ref="secret://db/credential/pending-google",
    )
    db.add(pending_credential)

    class FakeGoogleOAuthClient:
        def refresh_access_token(self, *, refresh_token: str, scopes: list[str]):
            return SimpleNamespace(
                access_token="fresh-access-token",
                refresh_token=refresh_token,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                scopes=scopes,
                token_type="Bearer",
            )

    monkeypatch.setattr(
        "api.integrations.google_workspace.GoogleWorkspaceOAuthClient",
        lambda: FakeGoogleOAuthClient(),
    )

    token = resolve_google_sheets_runtime_token(
        db,
        owner_user_id="test-user",
    )

    assert token.access_token == "fresh-access-token"
    assert pending_credential in db.new

    FreshSession = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
    fresh_db = FreshSession()
    try:
        assert (
            fresh_db.query(models.Credential)
            .filter(models.Credential.owner_user_id == "pending-user")
            .one_or_none()
            is None
        )
        stored = fresh_db.get(models.Credential, credential.id)
        assert stored is not None
        secret_payload = decrypt_secret_payload(stored.secret.encrypted_secret_json)
        assert secret_payload["access_token"] == "fresh-access-token"
    finally:
        fresh_db.close()


def test_google_sheets_runtime_token_wraps_refresh_handler_failures(db, monkeypatch):
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    expired_at = datetime.now(UTC) - timedelta(minutes=5)
    credential = models.Credential(
        owner_type="user",
        owner_user_id="test-user",
        workspace_id=None,
        provider="google_workspace",
        auth_type="oauth2",
        label="Google Workspace",
        provider_account_id="google_workspace",
        provider_account_label="Google Workspace",
        scopes_json=[GOOGLE_SHEETS_SCOPE],
        status="active",
        metadata_json={"display_name": "Google Workspace"},
        expires_at=expired_at,
        secret_ref="secret://db/credential/google",
    )
    db.add(credential)
    db.flush()
    db.add(
        models.CredentialSecret(
            credential_id=credential.id,
            encrypted_secret_json=encrypt_secret_payload(
                {
                    "access_token": "expired-access-token",
                    "refresh_token": "stored-refresh-token",
                    "expires_at": expired_at.isoformat(),
                    "token_type": "Bearer",
                }
            ),
            encryption_key_version="v1",
        )
    )
    db.commit()

    class FakeGoogleOAuthClient:
        def refresh_access_token(self, *, refresh_token: str, scopes: list[str]):
            raise GoogleWorkspaceOAuthError("network unavailable")

    monkeypatch.setattr(
        "api.integrations.google_workspace.GoogleWorkspaceOAuthClient",
        lambda: FakeGoogleOAuthClient(),
    )

    with pytest.raises(CredentialResolutionError, match="token refresh failed"):
        resolve_google_sheets_runtime_token(
            db,
            owner_user_id="test-user",
        )



def test_google_sheets_runtime_context_reuses_preresolved_token(monkeypatch):
    db = object()
    token = RuntimeOAuthToken(
        credential_id="credential-1",
        provider="google_workspace",
        access_token="pre-resolved-token",
        expires_at=None,
        scopes=[GOOGLE_SHEETS_SCOPE],
        provider_account_id="google-account-1",
        provider_account_label="creator@example.com",
    )

    def fail_resolver(*args, **kwargs):
        raise AssertionError("resolver should not run when context has a token")

    monkeypatch.setattr(
        "api.integrations.google_workspace.resolve_oauth_token_payload",
        fail_resolver,
    )
    monkeypatch.setattr(
        "api.integrations.google_workspace.build_sheets_client_from_access_token",
        lambda access_token: ("client", access_token),
    )

    with google_workspace_runtime_context(
        db=db,
        owner_user_id="user-1",
        sheets_token=token,
    ):
        client = build_sheets_client_from_runtime()

    assert client == ("client", "pre-resolved-token")
    assert runtime_oauth_redaction_values(token) == {"pre-resolved-token"}


def test_google_sheets_detection_covers_alias_tool_metadata():
    assert crew_snapshot_uses_google_sheets(
        {
            "runtime_crew": {"agent_version_ids": ["agent-1"], "task_version_ids": []},
            "agent_tool_links": {"agent-1": ["custom.sheets_alias"]},
            "runtime_tools": {
                "custom.sheets_alias": {
                    "module_path": "api.tools.google_sheets_tool",
                    "class_name": "AXGoogleSheetsTool",
                    "credential_requirements": [
                        {
                            "provider": "google_workspace",
                            "env_var": "AX_GOOGLE_WORKSPACE_OAUTH",
                            "required": True,
                            "injection": "runtime_context",
                        }
                    ],
                }
            },
        }
    )
