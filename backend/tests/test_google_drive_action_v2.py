import pytest

from api.db import models
from api.runtime.artifacts import create_artifact_metadata
from api.runtime.execution_actions import ExecutionActionRequest
from api.runtime.execution_actions import google_drive_upload_executor


class FakeDriveClient:
    def __init__(self) -> None:
        self.uploads = []

    def upload_file(
        self,
        *,
        filename: str,
        mime_type: str,
        content_bytes: bytes,
        target_folder_id: str | None,
    ):
        self.uploads.append(
            {
                "filename": filename,
                "mime_type": mime_type,
                "content_bytes": content_bytes,
                "target_folder_id": target_folder_id,
            }
        )
        return {
            "drive_file_id": "drive-file-1",
            "web_view_link": "https://drive.example/view",
            "web_content_link": "https://drive.example/content",
            "mime_type": mime_type,
            "ignored_secret": "must-not-return",
        }


class FakeDriveClientWithoutUrl(FakeDriveClient):
    def upload_file(
        self,
        *,
        filename: str,
        mime_type: str,
        content_bytes: bytes,
        target_folder_id: str | None,
    ):
        self.uploads.append(
            {
                "filename": filename,
                "mime_type": mime_type,
                "content_bytes": content_bytes,
                "target_folder_id": target_folder_id,
            }
        )
        return {
            "drive_file_id": "drive-file-without-url",
            "web_view_link": None,
            "web_content_link": None,
            "mime_type": mime_type,
        }


def test_google_drive_upload_executor_returns_drive_metadata(monkeypatch):
    fake_client = FakeDriveClient()
    monkeypatch.setattr("api.runtime.execution_actions.load_artifact_bytes", lambda *_args, **_kwargs: b"image")
    monkeypatch.setattr("api.runtime.execution_actions.build_google_drive_client", lambda *_args, **_kwargs: fake_client)

    output = google_drive_upload_executor(
        ExecutionActionRequest(
            run_id="run-1",
            node_id="execution_action:drive",
            action_key="ax.google_drive_upload",
            owner_user_id="test-user",
            inputs={"artifact_id": "artifact-1"},
            config={"filename_template": "image.png", "mime_type": "image/png", "target_folder_id": "folder-1"},
            approval_mode="never",
            artifact_ids=["artifact-1"],
        )
    )

    assert output == {
        "drive_file_id": "drive-file-1",
        "web_view_link": "https://drive.example/view",
        "web_content_link": "https://drive.example/content",
        "mime_type": "image/png",
    }
    assert fake_client.uploads == [
        {
            "filename": "image.png",
            "mime_type": "image/png",
            "content_bytes": b"image",
            "target_folder_id": "folder-1",
        }
    ]


def test_google_drive_upload_executor_reads_db_backed_temporary_artifact(db, tmp_path, monkeypatch):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id)
    artifact_path = tmp_path / "image.png"
    artifact_path.write_bytes(b"db-image")
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference=str(artifact_path),
        storage_path=str(artifact_path),
        size_bytes=len(b"db-image"),
    )
    fake_client = FakeDriveClient()
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_google_drive_client",
        lambda *_args, **_kwargs: fake_client,
    )

    output = google_drive_upload_executor(
        ExecutionActionRequest(
            run_id=str(run.id),
            node_id="execution_action:drive",
            action_key="ax.google_drive_upload",
            owner_user_id=owner_user_id,
            inputs={"artifact_id": str(artifact.id)},
            config={"filename_template": "image.png", "mime_type": "image/png"},
            approval_mode="never",
            artifact_ids=[str(artifact.id)],
            db=db,
        )
    )

    assert output["drive_file_id"] == "drive-file-1"
    assert fake_client.uploads[0]["content_bytes"] == b"db-image"
    db.refresh(artifact)
    assert artifact.storage_backend == "google_drive"
    assert artifact.storage_reference == "drive://file/drive-file-1"
    assert artifact.metadata_json["provider_media_url"] == "https://drive.example/content"
    assert artifact.metadata_json["external_resource_url"] == "https://drive.example/content"


def test_google_drive_upload_executor_keeps_temporary_artifact_when_drive_url_is_unavailable(
    db,
    tmp_path,
    monkeypatch,
):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id)
    artifact_path = tmp_path / "image.png"
    artifact_path.write_bytes(b"db-image")
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference=str(artifact_path),
        storage_path=str(artifact_path),
        size_bytes=len(b"db-image"),
    )
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_google_drive_client",
        lambda *_args, **_kwargs: FakeDriveClientWithoutUrl(),
    )

    output = google_drive_upload_executor(
        ExecutionActionRequest(
            run_id=str(run.id),
            node_id="execution_action:drive",
            action_key="ax.google_drive_upload",
            owner_user_id=owner_user_id,
            inputs={"artifact_id": str(artifact.id)},
            config={"filename_template": "image.png", "mime_type": "image/png"},
            approval_mode="never",
            artifact_ids=[str(artifact.id)],
            db=db,
        )
    )

    assert output["drive_file_id"] == "drive-file-without-url"
    db.refresh(artifact)
    assert artifact.storage_backend == "temporary"
    assert artifact.storage_reference == str(artifact_path)
    assert artifact.metadata_json == {}


def test_google_drive_upload_executor_requires_artifact_id():
    with pytest.raises(ValueError, match="artifact_id is required"):
        google_drive_upload_executor(
            ExecutionActionRequest(
                run_id="run-1",
                node_id="execution_action:drive",
                action_key="ax.google_drive_upload",
                owner_user_id="test-user",
                inputs={},
                config={},
                approval_mode="never",
                artifact_ids=[],
            )
        )


def test_google_drive_upload_executor_rejects_artifact_owned_by_another_user(db, tmp_path, monkeypatch):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    other_owner_user_id = "22222222-2222-4222-8222-222222222222"
    run = _create_flow_run(db, owner_user_id=other_owner_user_id)
    artifact_path = tmp_path / "other.png"
    artifact_path.write_bytes(b"other-image")
    artifact = create_artifact_metadata(
        db,
        owner_user_id=other_owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference=str(artifact_path),
        storage_path=str(artifact_path),
    )
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_google_drive_client",
        lambda *_args, **_kwargs: FakeDriveClient(),
    )

    with pytest.raises(LookupError, match="Artifact not found"):
        google_drive_upload_executor(
            ExecutionActionRequest(
                run_id=str(run.id),
                node_id="execution_action:drive",
                action_key="ax.google_drive_upload",
                owner_user_id=owner_user_id,
                inputs={"artifact_id": str(artifact.id)},
                config={},
                approval_mode="never",
                artifact_ids=[str(artifact.id)],
                db=db,
            )
        )


def test_google_drive_upload_executor_rejects_relative_path_escape_from_configured_root(
    db,
    tmp_path,
    monkeypatch,
):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id)
    artifact_root = tmp_path / "artifact-root"
    artifact_root.mkdir()
    escaped_path = tmp_path / "outside-configured-root.txt"
    escaped_path.write_bytes(b"escaped")
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="file",
        media_type="text/plain",
        storage_backend="temporary",
        storage_reference="../outside-configured-root.txt",
        storage_path="../outside-configured-root.txt",
    )
    monkeypatch.setenv("AX_ARTIFACT_STORAGE_ROOT", str(artifact_root))
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_google_drive_client",
        lambda *_args, **_kwargs: FakeDriveClient(),
    )

    with pytest.raises(ValueError, match="outside an allowed artifact storage root"):
        google_drive_upload_executor(
            ExecutionActionRequest(
                run_id=str(run.id),
                node_id="execution_action:drive",
                action_key="ax.google_drive_upload",
                owner_user_id=owner_user_id,
                inputs={"artifact_id": str(artifact.id)},
                config={},
                approval_mode="never",
                artifact_ids=[str(artifact.id)],
                db=db,
            )
        )


def _create_flow_run(db, *, owner_user_id: str) -> models.FlowRun:
    asset = models.Asset(
        id="22222222-2222-4222-8222-222222222222",
        asset_type="flow",
        workspace_id="33333333-3333-4333-8333-333333333333",
        owner_user_id=owner_user_id,
        name="Drive Action Flow",
    )
    version = models.AssetVersion(
        id="44444444-4444-4444-8444-444444444444",
        asset_id=asset.id,
        version_number=1,
        status="published",
        created_by=owner_user_id,
        payload_json={},
    )
    run = models.FlowRun(
        id="55555555-5555-4555-8555-555555555555",
        flow_version_id=version.id,
        status="running",
        input_json={},
    )
    db.add_all([asset, version, run])
    db.flush()
    return run
