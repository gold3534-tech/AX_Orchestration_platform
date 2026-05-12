from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

from sqlalchemy.orm import Session

from api.integrations.google_oauth import GoogleWorkspaceOAuthClient
from api.runtime.credential_resolver import CredentialResolutionError
from api.runtime.oauth_clients import (
    RefreshedOAuthToken,
    RuntimeOAuthToken,
    resolve_oauth_token_payload,
)


GOOGLE_DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
GOOGLE_SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
GOOGLE_WORKSPACE_PROVIDER = "google_workspace"


@dataclass(frozen=True)
class GoogleWorkspaceRuntimeContext:
    db: Session
    owner_user_id: str
    sheets_token: RuntimeOAuthToken | None = None
    drive_token: RuntimeOAuthToken | None = None


_runtime_context: ContextVar[GoogleWorkspaceRuntimeContext | None] = ContextVar(
    "google_workspace_runtime_context",
    default=None,
)


class GoogleSheetsClient:
    def __init__(self, service: Any) -> None:
        self._service = service

    def read_range(self, spreadsheet_id: str, range_name: str) -> list[list[Any]]:
        result = (
            self._service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        return values if isinstance(values, list) else []

    def append_rows(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        return (
            self._service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": values},
            )
            .execute()
        )

    def update_values(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        return (
            self._service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                body={"values": values},
            )
            .execute()
        )


class GoogleDriveClient:
    def __init__(self, service: Any) -> None:
        self._service = service

    def upload_file(
        self,
        *,
        filename: str,
        mime_type: str,
        content_bytes: bytes,
        target_folder_id: str | None,
    ) -> dict[str, Any]:
        from googleapiclient.http import MediaInMemoryUpload

        metadata: dict[str, Any] = {"name": filename}
        if target_folder_id:
            metadata["parents"] = [target_folder_id]
        media = MediaInMemoryUpload(content_bytes, mimetype=mime_type, resumable=False)
        result = (
            self._service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id,webViewLink,webContentLink,mimeType",
            )
            .execute()
        )
        return {
            "drive_file_id": result.get("id"),
            "web_view_link": result.get("webViewLink"),
            "web_content_link": result.get("webContentLink"),
            "mime_type": result.get("mimeType") or mime_type,
        }


@contextmanager
def google_workspace_runtime_context(
    *,
    db: Session,
    owner_user_id: str,
    sheets_token: RuntimeOAuthToken | None = None,
    drive_token: RuntimeOAuthToken | None = None,
) -> Iterator[None]:
    token = _runtime_context.set(
        GoogleWorkspaceRuntimeContext(
            db=db,
            owner_user_id=owner_user_id,
            sheets_token=sheets_token,
            drive_token=drive_token,
        )
    )
    try:
        yield
    finally:
        _runtime_context.reset(token)


def build_sheets_client_from_access_token(access_token: str) -> GoogleSheetsClient:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(token=access_token, scopes=[GOOGLE_SHEETS_SCOPE])
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    return GoogleSheetsClient(service)


def build_drive_client_from_access_token(access_token: str) -> GoogleDriveClient:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(token=access_token, scopes=[GOOGLE_DRIVE_FILE_SCOPE])
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return GoogleDriveClient(service)


def build_sheets_client_from_runtime(
    *,
    db: Session | None = None,
    owner_user_id: str | None = None,
) -> GoogleSheetsClient:
    context = _runtime_context.get()
    if context is not None:
        if context.sheets_token is None:
            raise CredentialResolutionError(
                "Google Sheets OAuth token was not prepared for runtime execution."
            )
        return build_sheets_client_from_access_token(context.sheets_token.access_token)

    runtime_db = db if db is not None else (context.db if context is not None else None)
    runtime_owner_user_id = owner_user_id if owner_user_id is not None else (
        context.owner_user_id if context is not None else None
    )
    if runtime_db is None or not runtime_owner_user_id:
        raise CredentialResolutionError("Google Workspace runtime context is unavailable.")

    token_payload = resolve_google_sheets_runtime_token(
        runtime_db,
        owner_user_id=runtime_owner_user_id,
    )
    return build_sheets_client_from_access_token(token_payload.access_token)


def build_drive_client_from_runtime(
    *,
    db: Session | None = None,
    owner_user_id: str | None = None,
) -> GoogleDriveClient:
    context = _runtime_context.get()
    if context is not None and context.drive_token is not None:
        return build_drive_client_from_access_token(context.drive_token.access_token)

    runtime_db = db if db is not None else (context.db if context is not None else None)
    runtime_owner_user_id = owner_user_id if owner_user_id is not None else (
        context.owner_user_id if context is not None else None
    )
    if runtime_db is None or not runtime_owner_user_id:
        raise CredentialResolutionError("Google Workspace runtime context is unavailable.")

    token_payload = resolve_google_drive_runtime_token(
        runtime_db,
        owner_user_id=runtime_owner_user_id,
    )
    return build_drive_client_from_access_token(token_payload.access_token)


def _refresh_google_workspace_token(
    refresh_token: str,
    scopes: list[str],
) -> RefreshedOAuthToken:
    refreshed = GoogleWorkspaceOAuthClient().refresh_access_token(
        refresh_token=refresh_token,
        scopes=scopes,
    )
    return RefreshedOAuthToken(
        access_token=refreshed.access_token,
        refresh_token=refreshed.refresh_token,
        expires_at=refreshed.expires_at,
        scopes=refreshed.scopes,
        token_type=refreshed.token_type,
    )


def resolve_google_sheets_runtime_token(
    db: Session,
    *,
    owner_user_id: str,
) -> RuntimeOAuthToken:
    return resolve_oauth_token_payload(
        db,
        owner_user_id=owner_user_id,
        provider=GOOGLE_WORKSPACE_PROVIDER,
        required_scopes=[GOOGLE_SHEETS_SCOPE],
        refresh_handler=_refresh_google_workspace_token,
    )


def resolve_google_drive_runtime_token(
    db: Session,
    *,
    owner_user_id: str,
) -> RuntimeOAuthToken:
    return resolve_oauth_token_payload(
        db,
        owner_user_id=owner_user_id,
        provider=GOOGLE_WORKSPACE_PROVIDER,
        required_scopes=[GOOGLE_DRIVE_FILE_SCOPE],
        refresh_handler=_refresh_google_workspace_token,
    )


def resolve_google_sheets_runtime_token_for_crew(
    db: Session,
    *,
    owner_user_id: str,
    crew_snapshot: Mapping[str, Any],
) -> RuntimeOAuthToken | None:
    if not crew_snapshot_uses_google_sheets(crew_snapshot):
        return None
    return resolve_google_sheets_runtime_token(db, owner_user_id=owner_user_id)


def runtime_oauth_redaction_values(*tokens: RuntimeOAuthToken | None) -> set[str]:
    return {
        token.access_token
        for token in tokens
        if token is not None and isinstance(token.access_token, str) and token.access_token
    }


def crew_snapshot_uses_google_sheets(crew_snapshot: Mapping[str, Any]) -> bool:
    return any(
        _tool_payload_uses_google_sheets(tool_key, tool_payload)
        for tool_key, tool_payload in _reachable_tool_payloads(crew_snapshot)
    )


def _reachable_tool_payloads(crew_snapshot: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    runtime_crew = crew_snapshot.get("runtime_crew")
    runtime_crew = runtime_crew if isinstance(runtime_crew, Mapping) else {}
    agent_ids = _string_set(runtime_crew.get("agent_version_ids"))
    manager_agent_id = runtime_crew.get("manager_agent_version_id")
    if isinstance(manager_agent_id, str) and manager_agent_id.strip():
        agent_ids.add(manager_agent_id.strip())
    task_ids = _string_set(runtime_crew.get("task_version_ids"))
    task_agent_links = crew_snapshot.get("task_agent_links")
    if isinstance(task_agent_links, Mapping):
        for task_id in task_ids:
            agent_id = task_agent_links.get(task_id)
            if isinstance(agent_id, str) and agent_id.strip():
                agent_ids.add(agent_id.strip())

    tool_keys: set[str] = set()
    agent_tool_links = crew_snapshot.get("agent_tool_links") or crew_snapshot.get("tool_links")
    if isinstance(agent_tool_links, Mapping):
        for agent_id in agent_ids:
            tool_keys.update(_string_set(agent_tool_links.get(agent_id)))

    task_tool_links = crew_snapshot.get("task_tool_links")
    if isinstance(task_tool_links, Mapping):
        for task_id in task_ids:
            tool_keys.update(_string_set(task_tool_links.get(task_id)))

    runtime_tools = crew_snapshot.get("runtime_tools")
    runtime_tools = runtime_tools if isinstance(runtime_tools, Mapping) else {}
    payloads: list[tuple[str, Mapping[str, Any]]] = []
    for tool_key in tool_keys:
        tool_payload = runtime_tools.get(tool_key)
        if isinstance(tool_payload, Mapping):
            payloads.append((tool_key, tool_payload))
        else:
            payloads.append((tool_key, {}))
    return payloads


def _tool_payload_uses_google_sheets(tool_key: str, tool_payload: Mapping[str, Any]) -> bool:
    if tool_key == "ax.google_sheets":
        return True
    if (
        tool_payload.get("module_path") == "api.tools.google_sheets_tool"
        and tool_payload.get("class_name") == "AXGoogleSheetsTool"
    ):
        return True
    credential_requirements = tool_payload.get("credential_requirements")
    if isinstance(credential_requirements, Sequence) and not isinstance(
        credential_requirements, bytes | bytearray | str
    ):
        for requirement in credential_requirements:
            if not isinstance(requirement, Mapping):
                continue
            if (
                requirement.get("provider") == GOOGLE_WORKSPACE_PROVIDER
                and requirement.get("injection") == "runtime_context"
            ):
                return True
    return False


def _string_set(value: object) -> set[str]:
    if isinstance(value, str) and value.strip():
        return {value.strip()}
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return {item.strip() for item in value if isinstance(item, str) and item.strip()}
    return set()
