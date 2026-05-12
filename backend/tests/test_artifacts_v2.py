from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from api.db.models import Asset, AssetVersion, FlowRun, RunArtifact
from api.main import app
from api.runtime.artifacts import (
    create_artifact_metadata,
    get_artifact_metadata,
    get_staging_artifact,
    list_artifact_metadata,
    list_staging_artifacts,
    retention_days_for_plan_tier,
    storage_outcome_for_artifact,
    staging_artifact_metadata,
)


def _create_flow_run(db, *, owner_user_id: str, run_id: str) -> FlowRun:
    asset = Asset(
        asset_type="flow",
        workspace_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        owner_user_id=owner_user_id,
        name=f"Flow {run_id}",
    )
    db.add(asset)
    db.flush()
    asset_version = AssetVersion(
        asset_id=asset.id,
        version_number=1,
        status="published",
        created_by=owner_user_id,
        payload_json={"type": "flow"},
        metadata_json={"type": "flow"},
    )
    db.add(asset_version)
    db.flush()
    flow_run = FlowRun(
        id=run_id,
        flow_version_id=asset_version.id,
        status="running",
        input_json={},
    )
    db.add(flow_run)
    db.flush()
    return flow_run


def test_ax_managed_artifact_defaults_to_seven_day_retention(db):
    before_create = datetime.now(UTC)
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    artifact = create_artifact_metadata(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
        source_tool="nano_banana",
        source_capability="image_generation",
    )

    assert artifact.retention_expires_at is not None
    assert before_create + timedelta(days=7) <= artifact.retention_expires_at
    assert artifact.retention_expires_at <= datetime.now(UTC) + timedelta(days=7, minutes=1)
    assert artifact.retention_mode == "ax_managed"
    assert artifact.status == "available"


def test_artifact_defaults_to_temporary_storage_outcome(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    artifact = create_artifact_metadata(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
        source_tool="nano_banana",
        source_capability="image_generation",
    )

    assert artifact.storage_backend == "temporary"
    assert artifact.retention_mode == "temporary"
    assert storage_outcome_for_artifact(artifact)["storage_outcome"] == "temporary_only"


def test_create_artifact_requires_real_owner_and_run_scope(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    with pytest.raises(ValueError, match="owner_user_id must not be the zero UUID"):
        create_artifact_metadata(
            db,
            owner_user_id="00000000-0000-0000-0000-000000000000",
            run_id="22222222-2222-2222-2222-222222222222",
            node_id="generate-image",
            artifact_type="image",
            media_type="image/png",
            storage_backend="ax_managed",
            storage_reference="runs/owner/image.png",
            source_tool="nano_banana",
            source_capability="image_generation",
        )

    with pytest.raises(ValueError, match="run_id must not be empty"):
        create_artifact_metadata(
            db,
            owner_user_id="11111111-1111-1111-1111-111111111111",
            run_id=None,
            node_id="generate-image",
            artifact_type="image",
            media_type="image/png",
            storage_backend="ax_managed",
            storage_reference="runs/owner/image.png",
            source_tool="nano_banana",
            source_capability="image_generation",
        )

    assert db.query(RunArtifact).count() == 0


def test_run_artifact_model_defines_enum_check_constraints():
    check_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in RunArtifact.__table__.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    }

    assert check_constraints == {
        "ck_run_artifacts_artifact_type": "artifact_type IN ('image', 'file')",
        "ck_run_artifacts_storage_backend": (
            "storage_backend IN ('ax_managed', 'temporary', 'google_drive')"
        ),
        "ck_run_artifacts_retention_mode": "retention_mode IN ('temporary', 'ax_managed')",
        "ck_run_artifacts_status": "status IN ('available', 'expired', 'failed')",
        "ck_run_artifacts_size_bytes_non_negative": "size_bytes >= 0",
        "ck_run_artifacts_storage_retention_mode": (
            "(storage_backend = 'temporary' AND retention_mode = 'temporary') "
            "OR (storage_backend = 'ax_managed' AND retention_mode = 'ax_managed') "
            "OR (storage_backend = 'google_drive' AND retention_mode = 'temporary')"
        ),
    }


def test_run_artifact_model_rejects_invalid_storage_retention_combination(db):
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference="runs/run/image.png",
        retention_mode="ax_managed",
        status="available",
        metadata_json={},
    )

    db.add(artifact)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_run_artifact_model_rejects_negative_size_bytes(db):
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        size_bytes=-1,
        storage_backend="temporary",
        storage_reference="runs/run/image.png",
        retention_mode="temporary",
        status="available",
        metadata_json={},
    )

    db.add(artifact)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_create_artifact_succeeds_for_owned_run(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    artifact = create_artifact_metadata(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="runs/owner/image.png",
        source_tool="nano_banana",
        source_capability="image_generation",
    )

    assert artifact.run_id == "22222222-2222-2222-2222-222222222222"
    assert artifact.owner_user_id == "11111111-1111-1111-1111-111111111111"


def test_create_artifact_rejects_run_owned_by_another_user(db):
    _create_flow_run(
        db,
        owner_user_id="33333333-3333-3333-3333-333333333333",
        run_id="44444444-4444-4444-4444-444444444444",
    )

    with pytest.raises(LookupError, match="Flow run not found"):
        create_artifact_metadata(
            db,
            owner_user_id="11111111-1111-1111-1111-111111111111",
            run_id="44444444-4444-4444-4444-444444444444",
            node_id="generate-image",
            artifact_type="image",
            media_type="image/png",
            storage_backend="ax_managed",
            storage_reference="runs/other/image.png",
            source_tool="nano_banana",
            source_capability="image_generation",
        )

    assert db.query(RunArtifact).count() == 0


def test_create_artifact_rejects_missing_run(db):
    with pytest.raises(LookupError, match="Flow run not found"):
        create_artifact_metadata(
            db,
            owner_user_id="11111111-1111-1111-1111-111111111111",
            run_id="99999999-9999-9999-9999-999999999999",
            node_id="generate-image",
            artifact_type="image",
            media_type="image/png",
            storage_backend="ax_managed",
            storage_reference="runs/missing/image.png",
            source_tool="nano_banana",
            source_capability="image_generation",
        )

    assert db.query(RunArtifact).count() == 0


def test_list_and_get_artifacts_are_scoped_to_owner(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )
    _create_flow_run(
        db,
        owner_user_id="33333333-3333-3333-3333-333333333333",
        run_id="44444444-4444-4444-4444-444444444444",
    )
    owner_artifact = create_artifact_metadata(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="runs/owner/image.png",
        source_tool="nano_banana",
        source_capability="image_generation",
    )
    create_artifact_metadata(
        db,
        owner_user_id="33333333-3333-3333-3333-333333333333",
        run_id="44444444-4444-4444-4444-444444444444",
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="runs/other/image.png",
        source_tool="nano_banana",
        source_capability="image_generation",
    )

    artifacts = list_artifact_metadata(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
    )

    assert [artifact.id for artifact in artifacts] == [owner_artifact.id]
    assert (
        get_artifact_metadata(
            db,
            artifact_id=str(owner_artifact.id),
            owner_user_id="11111111-1111-1111-1111-111111111111",
        ).id
        == owner_artifact.id
    )
    with pytest.raises(LookupError):
        get_artifact_metadata(
            db,
            artifact_id=str(owner_artifact.id),
            owner_user_id="33333333-3333-3333-3333-333333333333",
        )


def test_public_artifact_metadata_hides_storage_reference_and_secret_metadata(db):
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
        source_tool="nano_banana",
        source_capability="image_generation",
        retention_expires_at=datetime.now(UTC) + timedelta(days=7),
        metadata_json={
            "prompt": "A quiet workspace",
            "seed": 42,
            "access_token": "secret-token",
            "preview_url": "https://cdn.example/preview.png",
            "download_url": "https://cdn.example/download.png",
            "nested": {"api_key": "secret-key", "model": "nano-banana"},
            "notes": ["visible", "contains refresh_token value"],
        },
    )

    payload = staging_artifact_metadata(artifact)

    assert payload["id"] == str(artifact.id)
    assert payload["storage_backend"] == "ax_managed"
    assert payload["mime_type"] == "image/png"
    assert payload["expires_at"] == artifact.retention_expires_at.isoformat()
    assert payload["preview_url"] == "https://cdn.example/preview.png"
    assert payload["download_url"] == "https://cdn.example/download.png"
    assert payload["retention_expires_at"] == artifact.retention_expires_at.isoformat()
    assert payload["self_delete_supported"] is False
    assert "owner_user_id" not in payload
    assert "storage_reference" not in payload
    assert payload["metadata_json"] == {
        "prompt": "A quiet workspace",
        "seed": 42,
        "preview_url": "https://cdn.example/preview.png",
        "download_url": "https://cdn.example/download.png",
        "nested": {"model": "nano-banana"},
        "notes": ["visible", None],
    }


def test_run_artifact_content_route_serves_owned_temporary_image(client, db, tmp_path):
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id="test-user", run_id=run_id)
    image_path = tmp_path / "generated.png"
    image_bytes = b"\x89PNG\r\n\x1a\nimage-bytes"
    image_path.write_bytes(image_bytes)

    artifact = create_artifact_metadata(
        db,
        owner_user_id="test-user",
        run_id=run_id,
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference=str(image_path),
        storage_path=str(image_path),
        source_tool="nano_banana",
        source_capability="image_generation",
    )

    response = client.get(f"/api/run-artifacts/{artifact.id}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == image_bytes


def test_run_artifact_content_route_redirects_owned_ax_managed_public_url(client, db):
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id="test-user", run_id=run_id)
    public_url = "https://cdn.example/storage/v1/object/public/ax-public-artifacts/generated.png"

    artifact = create_artifact_metadata(
        db,
        owner_user_id="test-user",
        run_id=run_id,
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="artifacts/run-1/generated.png",
        storage_path="artifacts/run-1/generated.png",
        source_tool="nano_banana",
        source_capability="image_generation",
        metadata_json={"provider_media_url": public_url},
    )

    response = client.get(f"/api/run-artifacts/{artifact.id}/content", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == public_url


def test_public_run_artifact_content_route_does_not_redirect_provider_url_without_public_metadata(
    client,
    db,
):
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id="test-user", run_id=run_id)

    artifact = create_artifact_metadata(
        db,
        owner_user_id="test-user",
        run_id=run_id,
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="artifacts/run-1/generated.png",
        storage_path="artifacts/run-1/generated.png",
        source_tool="nano_banana",
        source_capability="image_generation",
        metadata_json={
            "provider_media_url": "https://cdn.example/storage/v1/object/public/ax-public-artifacts/generated.png",
        },
    )

    response = client.get(f"/api/public/run-artifacts/{artifact.id}/content", follow_redirects=False)

    assert response.status_code == 404


def test_public_run_artifact_content_route_serves_available_temporary_image(client, db, tmp_path):
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id="test-user", run_id=run_id)
    image_path = tmp_path / "generated.png"
    image_bytes = b"\x89PNG\r\n\x1a\nimage-bytes"
    image_path.write_bytes(image_bytes)

    artifact = create_artifact_metadata(
        db,
        owner_user_id="test-user",
        run_id=run_id,
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference=str(image_path),
        storage_path=str(image_path),
        source_tool="nano_banana",
        source_capability="image_generation",
    )
    artifact.metadata_json = {
        "preview_url": f"/api/run-artifacts/{artifact.id}/content",
        "download_url": f"/api/run-artifacts/{artifact.id}/content",
    }
    db.add(artifact)
    db.flush()

    response = client.get(f"/api/public/run-artifacts/{artifact.id}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == image_bytes


def test_public_run_artifact_content_route_requires_public_artifact_metadata(client, db, tmp_path):
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id="test-user", run_id=run_id)
    image_path = tmp_path / "generated.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\nimage-bytes")

    artifact = create_artifact_metadata(
        db,
        owner_user_id="test-user",
        run_id=run_id,
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference=str(image_path),
        storage_path=str(image_path),
        source_tool="nano_banana",
        source_capability="image_generation",
    )

    response = client.get(f"/api/public/run-artifacts/{artifact.id}/content")

    assert response.status_code == 404


def test_run_artifact_content_route_hides_other_users_artifact(client, db, tmp_path):
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id=run_id,
    )
    image_path = tmp_path / "other.png"
    image_path.write_bytes(b"other-user-image")

    artifact = create_artifact_metadata(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id=run_id,
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference=str(image_path),
        storage_path=str(image_path),
        source_tool="nano_banana",
        source_capability="image_generation",
    )

    response = client.get(f"/api/run-artifacts/{artifact.id}/content")

    assert response.status_code == 404


def test_flow_run_detail_returns_owned_artifacts(client, db, auth_headers, tmp_path):
    run_id = "22222222-2222-2222-2222-222222222222"
    _create_flow_run(db, owner_user_id="test-user", run_id=run_id)
    image_path = tmp_path / "generated.png"
    image_path.write_bytes(b"image-bytes")

    artifact = create_artifact_metadata(
        db,
        owner_user_id="test-user",
        run_id=run_id,
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference=str(image_path),
        storage_path=str(image_path),
        source_tool="nano_banana",
        source_capability="image_generation",
    )
    artifact.metadata_json = {
        "preview_url": f"/api/run-artifacts/{artifact.id}/content",
        "download_url": f"/api/run-artifacts/{artifact.id}/content",
    }
    db.add(artifact)
    db.commit()

    response = client.get(f"/api/flow-runs/{run_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["artifacts"][0]["id"] == str(artifact.id)
    assert body["artifacts"][0]["artifact_type"] == "image"
    assert body["artifacts"][0]["preview_url"] == f"/api/run-artifacts/{artifact.id}/content"


@pytest.mark.parametrize(
    ("field_name", "overrides", "match"),
    [
        ("artifact_type", {"artifact_type": "video"}, "artifact_type must be one of"),
        ("storage_backend", {"storage_backend": "s3"}, "storage_backend must be one of"),
        ("storage_backend", {"storage_backend": ""}, "storage_backend must not be empty"),
        ("storage_backend", {"storage_backend": "   "}, "storage_backend must not be empty"),
        ("status", {"status": "externalized"}, "status must be one of"),
        ("status", {"status": "uploaded"}, "status must be one of"),
        ("retention_mode", {"retention_mode": "forever"}, "retention_mode must be one of"),
    ],
)
def test_create_artifact_rejects_unknown_enum_values(db, field_name, overrides, match):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    payload = {
        "owner_user_id": "11111111-1111-1111-1111-111111111111",
        "run_id": "22222222-2222-2222-2222-222222222222",
        "node_id": "generate-image",
        "artifact_type": "image",
        "media_type": "image/png",
        "storage_backend": "ax_managed",
        "storage_reference": "runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
        "source_tool": "nano_banana",
        "source_capability": "image_generation",
    }
    payload.update(overrides)

    with pytest.raises(ValueError, match=match):
        create_artifact_metadata(db, **payload)

    assert db.query(RunArtifact).count() == 0


@pytest.mark.parametrize(
    ("storage_backend", "retention_mode", "match"),
    [
        ("temporary", "ax_managed", 'storage_backend "temporary" requires retention_mode "temporary"'),
        ("ax_managed", "temporary", 'storage_backend "ax_managed" requires retention_mode "ax_managed"'),
        ("google_drive", "ax_managed", 'storage_backend "google_drive" requires retention_mode "temporary"'),
    ],
)
def test_create_artifact_rejects_invalid_storage_retention_combinations(
    db,
    storage_backend,
    retention_mode,
    match,
):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    with pytest.raises(ValueError, match=match):
        create_artifact_metadata(
            db,
            owner_user_id="11111111-1111-1111-1111-111111111111",
            run_id="22222222-2222-2222-2222-222222222222",
            node_id="generate-image",
            artifact_type="image",
            media_type="image/png",
            storage_backend=storage_backend,
            storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
            retention_mode=retention_mode,
            source_tool="nano_banana",
            source_capability="image_generation",
        )

    assert db.query(RunArtifact).count() == 0


def test_create_artifact_rejects_secret_metadata_before_persistence(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    with pytest.raises(ValueError, match="metadata_json must not include secret-like key: refresh_token"):
        create_artifact_metadata(
            db,
            owner_user_id="11111111-1111-1111-1111-111111111111",
            run_id="22222222-2222-2222-2222-222222222222",
            node_id="generate-image",
            artifact_type="image",
            media_type="image/png",
            storage_backend="ax_managed",
            storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
            source_tool="nano_banana",
            source_capability="image_generation",
            metadata_json={"prompt": "A quiet workspace", "refresh_token": "secret-token"},
        )

    assert db.query(RunArtifact).count() == 0


def test_create_artifact_rejects_encoded_secret_metadata_key_before_persistence(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    with pytest.raises(ValueError, match="metadata_json must not include secret-like key"):
        create_artifact_metadata(
            db,
            owner_user_id="11111111-1111-1111-1111-111111111111",
            run_id="22222222-2222-2222-2222-222222222222",
            node_id="generate-image",
            artifact_type="image",
            media_type="image/png",
            storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
            source_tool="nano_banana",
            source_capability="image_generation",
            metadata_json={
                "nested": {"access%2525255Ftok%25252565n": "abc123"},
            },
        )

    assert db.query(RunArtifact).count() == 0


def test_create_artifact_rejects_negative_size_bytes(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    with pytest.raises(ValueError, match="size_bytes must be non-negative"):
        create_artifact_metadata(
            db,
            owner_user_id="11111111-1111-1111-1111-111111111111",
            run_id="22222222-2222-2222-2222-222222222222",
            node_id="generate-image",
            artifact_type="image",
            media_type="image/png",
            size_bytes=-1,
            storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
            source_tool="nano_banana",
            source_capability="image_generation",
        )

    assert db.query(RunArtifact).count() == 0


def test_public_list_and_get_services_return_non_secret_metadata(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    artifact = create_artifact_metadata(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
        source_tool="nano_banana",
        source_capability="image_generation",
        metadata_json={"prompt": "A quiet workspace"},
    )

    listed = list_staging_artifacts(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
    )
    fetched = get_staging_artifact(
        db,
        artifact_id=str(artifact.id),
        owner_user_id="11111111-1111-1111-1111-111111111111",
    )

    assert listed == [fetched]
    assert fetched["id"] == str(artifact.id)
    assert fetched["retention_expires_at"] == artifact.retention_expires_at.isoformat()
    assert fetched["metadata_json"] == {"prompt": "A quiet workspace"}
    assert "storage_reference" not in fetched
    assert db.get(RunArtifact, artifact.id).metadata_json == {"prompt": "A quiet workspace"}


def test_public_response_contract_includes_runtime_fields(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    artifact = create_artifact_metadata(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        node_id="generate-image",
        artifact_type="image",
        mime_type="image/png",
        storage_backend="temporary",
        storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
        source_tool="nano_banana",
        source_capability="image_generation",
        metadata_json={
            "preview_url": "https://cdn.example/preview.png",
            "download_url": "https://cdn.example/download.png",
        },
    )

    payload = get_staging_artifact(
        db,
        artifact_id=str(artifact.id),
        owner_user_id="11111111-1111-1111-1111-111111111111",
    )

    assert payload["mime_type"] == "image/png"
    assert payload["media_type"] == "image/png"
    assert payload["expires_at"] == artifact.retention_expires_at.isoformat()
    assert payload["retention_expires_at"] == artifact.retention_expires_at.isoformat()
    assert payload["preview_url"] == "https://cdn.example/preview.png"
    assert payload["download_url"] == "https://cdn.example/download.png"
    assert "owner_user_id" not in payload


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "https://access_token:secret@cdn.example/preview.png",
        "https://cdn.example/secret/preview.png",
        "https://cdn.example/assets/access_token/preview.png",
        "https://cdn.example/assets/access%5Ftok%65n/preview.png",
        "https://cdn.example/preview.png#refresh_token=secret",
        "https://cdn.example/preview.png#refresh%5Ftok%65n=secret",
        "https://cdn.example/preview.png?access_token=secret",
        "https://cdn.example/preview.png?access%255Ftok%2565n=abc123",
        "https://cdn.example/preview.png?x=refresh%255Ftok%2565n%3Dabc123",
    ],
)
def test_public_response_omits_unsafe_preview_and_download_urls(unsafe_url):
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference="runs/run/image.png",
        retention_mode="temporary",
        metadata_json={
            "preview_url": unsafe_url,
            "download_url": unsafe_url,
        },
    )

    payload = staging_artifact_metadata(artifact)

    assert payload["preview_url"] is None
    assert payload["download_url"] is None


def test_public_metadata_json_omits_unsafe_url_values_but_keeps_safe_urls():
    deeply_encoded_secret = "access%2525255Ftok%25252565n%25253Dabc123"
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference="runs/run/image.png",
        retention_mode="temporary",
        metadata_json={
            "preview_url": "https://cdn.example/preview.png?access%255Ftok%2565n=abc123",
            "download_url": "https://cdn.example/assets/access%5Ftok%65n/download.png",
            "external_resource_url": "https://drive.example/file/image-1#refresh%5Ftok%65n=secret",
            "safe_url": "https://cdn.example/public.png",
            "encoded_secret_text": "access%255Ftok%2565n=abc123",
            "deep_encoded_secret_text": deeply_encoded_secret,
            "access%2525255Ftok%25252565n": "abc123",
            "arbitrary_url": "https://cdn.example/file.png?access%255Ftok%2565n=abc123",
            "unsafe_host_url": "https://access_token.example.com/public.png",
            "unsafe_encoded_host_url": "https://access%5Ftoken.example.com/public.png",
            "nested": {
                "preview_url": "https://cdn.example/secret/nested.png",
                "safe_url": "https://cdn.example/nested-public.png",
                "refresh%2525255Ftok%25252565n": "abc123",
                "encoded_secret_text": "refresh%255Ftok%2565n%3Dabc123",
                "other_url": "https://cdn.example/nested.png?x=refresh%255Ftok%2565n%3Dabc123",
                "notes": ["safe note", "api%255Fkey%3Dabc123", deeply_encoded_secret],
            },
        },
    )

    payload = staging_artifact_metadata(artifact)

    assert payload["preview_url"] is None
    assert payload["download_url"] is None
    assert payload["metadata_json"] == {
        "safe_url": "https://cdn.example/public.png",
        "nested": {"safe_url": "https://cdn.example/nested-public.png", "notes": ["safe note", None, None]},
    }


def test_public_artifact_metadata_rejects_legacy_negative_size_bytes():
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        size_bytes=-1,
        storage_backend="temporary",
        storage_reference="runs/run/image.png",
        retention_mode="temporary",
        status="available",
        metadata_json={},
    )

    with pytest.raises(ValueError, match="size_bytes must be non-negative"):
        staging_artifact_metadata(artifact)


def test_explicit_retention_beyond_mvp_cap_is_rejected(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    with pytest.raises(ValueError, match="retention_expires_at cannot exceed the 7 day MVP retention cap"):
        create_artifact_metadata(
            db,
            owner_user_id="11111111-1111-1111-1111-111111111111",
            run_id="22222222-2222-2222-2222-222222222222",
            node_id="generate-image",
            artifact_type="image",
            media_type="image/png",
            storage_backend="ax_managed",
            storage_reference="runs/22222222-2222-2222-2222-222222222222/generate-image/image.png",
            source_tool="nano_banana",
            source_capability="image_generation",
            retention_expires_at=datetime.now(UTC) + timedelta(days=90),
        )

    assert db.query(RunArtifact).count() == 0


@pytest.mark.parametrize(
    "public_reader",
    [staging_artifact_metadata, storage_outcome_for_artifact],
)
def test_public_artifact_outputs_reject_legacy_over_cap_retention(public_reader):
    created_at = datetime(2026, 5, 1, tzinfo=UTC)
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference="runs/run/image.png",
        retention_mode="temporary",
        retention_expires_at=created_at + timedelta(days=90),
        status="available",
        metadata_json={},
        created_at=created_at,
    )

    with pytest.raises(ValueError, match="retention_expires_at cannot exceed the 7 day MVP retention cap"):
        public_reader(artifact)


def test_storage_outcome_values_are_limited_to_plan_contract():
    temporary_artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference="runs/run/image.png",
        retention_mode="temporary",
        status="available",
        metadata_json={},
    )
    ax_managed_artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="runs/run/image.png",
        retention_mode="ax_managed",
        status="available",
        metadata_json={},
    )
    google_drive_artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="google_drive",
        storage_reference="drive://file/image-1",
        retention_mode="temporary",
        status="available",
        metadata_json={"external_resource_url": "https://drive.example/file/image-1"},
    )

    outcomes = {
        storage_outcome_for_artifact(temporary_artifact)["storage_outcome"],
        storage_outcome_for_artifact(ax_managed_artifact)["storage_outcome"],
        storage_outcome_for_artifact(google_drive_artifact)["storage_outcome"],
    }

    assert outcomes == {"temporary_only", "ax_managed", "uploaded_to_google_drive"}
    assert "user_managed" not in outcomes


def test_storage_outcome_rejects_unknown_backend_or_retention_mode():
    unknown_backend = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="s3",
        storage_reference="s3://bucket/image.png",
        retention_mode="temporary",
        status="available",
        metadata_json={},
    )
    unknown_retention = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="runs/run/image.png",
        retention_mode="forever",
        status="available",
        metadata_json={},
    )

    with pytest.raises(ValueError, match="storage_backend must be one of"):
        storage_outcome_for_artifact(unknown_backend)
    with pytest.raises(ValueError, match="retention_mode must be one of"):
        storage_outcome_for_artifact(unknown_retention)


def test_storage_outcome_marks_google_drive_upload_as_uploaded_to_google_drive(db):
    _create_flow_run(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
    )

    artifact = create_artifact_metadata(
        db,
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        node_id="upload-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="google_drive",
        storage_reference="drive://file/image-1",
        source_tool="google_drive_upload",
        source_capability="drive_upload",
        retention_expires_at=None,
        status="available",
        metadata_json={
            "external_resource_label": "image-1.png",
            "external_resource_url": "https://drive.example/file/image-1",
        },
    )

    outcome = storage_outcome_for_artifact(artifact)

    assert outcome == {
        "storage_outcome": "uploaded_to_google_drive",
        "external_resource_url": "https://drive.example/file/image-1",
        "external_resource_label": "image-1.png",
        "retention_expires_at": None,
        "expires_at": None,
        "self_delete_supported": False,
    }


@pytest.mark.parametrize(
    "status",
    ["expired", "failed"],
)
def test_storage_outcome_rejects_non_available_status(status):
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="temporary",
        storage_reference="runs/run/image.png",
        retention_mode="temporary",
        status=status,
        metadata_json={},
    )

    with pytest.raises(ValueError, match="storage_outcome requires artifact status available"):
        storage_outcome_for_artifact(artifact)


@pytest.mark.parametrize(
    ("storage_backend", "retention_mode", "match"),
    [
        ("temporary", "ax_managed", 'storage_backend "temporary" requires retention_mode "temporary"'),
        ("ax_managed", "temporary", 'storage_backend "ax_managed" requires retention_mode "ax_managed"'),
        ("google_drive", "ax_managed", 'storage_backend "google_drive" requires retention_mode "temporary"'),
    ],
)
def test_storage_outcome_rejects_invalid_storage_retention_combinations(
    storage_backend,
    retention_mode,
    match,
):
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend=storage_backend,
        storage_reference="runs/run/image.png",
        retention_mode=retention_mode,
        status="available",
        metadata_json={"external_resource_url": "https://drive.example/file/image-1"},
    )

    with pytest.raises(ValueError, match=match):
        storage_outcome_for_artifact(artifact)


def test_storage_outcome_rejects_google_drive_without_safe_external_url():
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="google_drive",
        storage_reference="drive://file/image-1",
        retention_mode="temporary",
        status="available",
        metadata_json={
            "external_resource_url": "https://drive.example/file/image-1?access_token=secret",
            "external_resource_label": "image-1.png",
        },
    )

    with pytest.raises(ValueError, match="google_drive storage_outcome requires a safe external_resource_url"):
        storage_outcome_for_artifact(artifact)


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "https://access_token:secret@drive.example/file/image-1",
        "https://drive.example/secret/image-1",
        "https://drive.example/files/access_token/image-1",
        "https://drive.example/files/access%5Ftok%65n/image-1",
        "https://drive.example/file/image-1#refresh_token=secret",
        "https://drive.example/file/image-1#refresh%5Ftok%65n=secret",
        "https://drive.example/file/image-1?access_token=secret",
        "https://drive.example/file/image-1?access%255Ftok%2565n=abc123",
        "https://drive.example/file/image-1?x=refresh%255Ftok%2565n%3Dabc123",
        "https://access_token.example.com/file/image-1",
        "https://access%5Ftoken.example.com/file/image-1",
    ],
)
def test_storage_outcome_omits_unsafe_external_url_variants(unsafe_url):
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="google_drive",
        storage_reference="drive://file/image-1",
        retention_mode="temporary",
        status="available",
        metadata_json={
            "external_resource_url": unsafe_url,
            "external_resource_label": "image-1.png",
        },
    )

    with pytest.raises(ValueError, match="google_drive storage_outcome requires a safe external_resource_url"):
        storage_outcome_for_artifact(artifact)


def test_storage_outcome_omits_secret_like_external_label():
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="google_drive",
        storage_reference="drive://file/image-1",
        retention_mode="temporary",
        status="available",
        metadata_json={
            "external_resource_url": "https://drive.example/file/image-1",
            "external_resource_label": "refresh_token=secret",
        },
    )

    outcome = storage_outcome_for_artifact(artifact)

    assert outcome["external_resource_url"] == "https://drive.example/file/image-1"
    assert outcome["external_resource_label"] is None


@pytest.mark.parametrize(
    "label",
    [
        {"name": "image-1.png"},
        ["image-1.png"],
        123,
    ],
)
def test_storage_outcome_omits_non_string_external_label(label):
    artifact = RunArtifact(
        owner_user_id="11111111-1111-1111-1111-111111111111",
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_type="image",
        media_type="image/png",
        storage_backend="google_drive",
        storage_reference="drive://file/image-1",
        retention_mode="temporary",
        status="available",
        metadata_json={
            "external_resource_url": "https://drive.example/file/image-1",
            "external_resource_label": label,
        },
    )

    outcome = storage_outcome_for_artifact(artifact)

    assert outcome["external_resource_label"] is None


def test_retention_plan_tier_placeholders_keep_mvp_to_free_seven_days():
    assert retention_days_for_plan_tier("free") == 7
    with pytest.raises(NotImplementedError):
        retention_days_for_plan_tier("pro_30")
    with pytest.raises(NotImplementedError):
        retention_days_for_plan_tier("team_90")


def test_no_user_self_delete_endpoint_is_registered():
    artifact_delete_routes = [
        route
        for route in app.routes
        if "DELETE" in getattr(route, "methods", set())
        and "artifact" in getattr(route, "path", "").lower()
    ]

    assert artifact_delete_routes == []
