from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from api.runtime import supabase_artifact_storage as storage


class FakeBucket:
    def __init__(self, bucket_name: str) -> None:
        self.bucket_name = bucket_name
        self.upload_calls: list[dict[str, object]] = []

    def upload(self, path: str, file: bytes, file_options: dict[str, str]):
        self.upload_calls.append(
            {
                "path": path,
                "file": file,
                "file_options": file_options,
            }
        )
        return {"Key": path}

    def get_public_url(self, path: str) -> str:
        return f"https://cdn.example/storage/v1/object/public/{self.bucket_name}/{path}"


class FakeStorage:
    def __init__(self) -> None:
        self.bucket = FakeBucket("ax-public-artifacts")

    def from_(self, bucket_name: str) -> FakeBucket:
        assert bucket_name == "ax-public-artifacts"
        return self.bucket


class FakeSupabase:
    def __init__(self) -> None:
        self.storage = FakeStorage()


def test_upload_public_artifact_bytes_uses_random_public_object_path(monkeypatch):
    fake_supabase = FakeSupabase()
    monkeypatch.setenv("AX_SUPABASE_ARTIFACT_BUCKET", "ax-public-artifacts")
    monkeypatch.setattr(
        storage.uuid,
        "uuid4",
        lambda: UUID("12345678-1234-4234-8234-123456789abc"),
    )

    uploaded = storage.upload_public_artifact_bytes(
        image_bytes=b"image-bytes",
        media_type="image/png",
        owner_user_id="user-1",
        run_id="run-1",
        object_suffix=".png",
        supabase_client=fake_supabase,
    )

    assert uploaded.bucket == "ax-public-artifacts"
    assert uploaded.object_path == "artifacts/run-1/12345678123442348234123456789abc.png"
    assert uploaded.public_url == (
        "https://cdn.example/storage/v1/object/public/"
        "ax-public-artifacts/artifacts/run-1/12345678123442348234123456789abc.png"
    )
    assert fake_supabase.storage.bucket.upload_calls == [
        {
            "path": "artifacts/run-1/12345678123442348234123456789abc.png",
            "file": b"image-bytes",
            "file_options": {
                "content-type": "image/png",
                "cache-control": "3600",
                "upsert": "false",
            },
        }
    ]


def test_upload_public_artifact_bytes_requires_configured_bucket(monkeypatch):
    monkeypatch.delenv("AX_SUPABASE_ARTIFACT_BUCKET", raising=False)

    with pytest.raises(ValueError, match="AX_SUPABASE_ARTIFACT_BUCKET is required"):
        storage.upload_public_artifact_bytes(
            image_bytes=b"image-bytes",
            media_type="image/png",
            owner_user_id="user-1",
            run_id="run-1",
            object_suffix=".png",
            supabase_client=FakeSupabase(),
        )


def test_upload_public_artifact_bytes_rejects_unsupported_media_type(monkeypatch):
    monkeypatch.setenv("AX_SUPABASE_ARTIFACT_BUCKET", "ax-public-artifacts")

    with pytest.raises(ValueError, match="Unsupported image media type"):
        storage.upload_public_artifact_bytes(
            image_bytes=b"document-bytes",
            media_type="application/pdf",
            owner_user_id="user-1",
            run_id="run-1",
            object_suffix=".pdf",
            supabase_client=FakeSupabase(),
        )


@pytest.mark.parametrize("object_suffix", ["/evil.png", "..png", ".png?download=true"])
def test_upload_public_artifact_bytes_rejects_unsafe_object_suffixes(
    monkeypatch, object_suffix
):
    monkeypatch.setenv("AX_SUPABASE_ARTIFACT_BUCKET", "ax-public-artifacts")

    with pytest.raises(ValueError, match="object_suffix must be a supported image extension"):
        storage.upload_public_artifact_bytes(
            image_bytes=b"image-bytes",
            media_type="image/png",
            owner_user_id="user-1",
            run_id="run-1",
            object_suffix=object_suffix,
            supabase_client=FakeSupabase(),
        )


def test_upload_public_artifact_file_reads_local_file(monkeypatch, tmp_path):
    fake_supabase = FakeSupabase()
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"local-image")
    monkeypatch.setenv("AX_SUPABASE_ARTIFACT_BUCKET", "ax-public-artifacts")
    monkeypatch.setattr(
        storage.uuid,
        "uuid4",
        lambda: UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    )

    uploaded = storage.upload_public_artifact_file(
        path=image_path,
        media_type="image/png",
        owner_user_id="user-1",
        run_id="run-1",
        supabase_client=fake_supabase,
    )

    assert uploaded.object_path == "artifacts/run-1/aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa.png"
    assert fake_supabase.storage.bucket.upload_calls[0]["file"] == b"local-image"


def test_upload_public_artifact_file_rejects_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv("AX_SUPABASE_ARTIFACT_BUCKET", "ax-public-artifacts")

    with pytest.raises(ValueError, match="Artifact file content is unavailable"):
        storage.upload_public_artifact_file(
            path=Path(tmp_path / "missing.png"),
            media_type="image/png",
            owner_user_id="user-1",
            run_id="run-1",
            supabase_client=FakeSupabase(),
        )
