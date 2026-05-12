import pytest

from api.db import models
from api.runtime.artifacts import create_artifact_metadata
from api.runtime.execution_actions import (
    ExecutionActionRequest,
    MAX_PROVIDER_ARTIFACT_BYTES,
    execute_execution_action,
    load_artifact_bytes,
    register_execution_action,
)
from api.runtime.flow_snapshot_executor import FlowSnapshotExecutor, HumanFeedbackConflictError
from api.runtime.loaders import FlowGraphLoader
from api.runtime.oauth_clients import RuntimeOAuthToken
from api.schemas.flow_graph import FlowGraphDocument


class FakeStreamContext:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self.response

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeStreamResponse:
    def __init__(self, chunks, *, status_error=None):
        self._chunks = chunks
        self._status_error = status_error
        self.chunks_consumed = 0

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def iter_bytes(self):
        for chunk in self._chunks:
            self.chunks_consumed += 1
            yield chunk


def test_execution_action_idempotency_returns_existing_success(db):
    calls = []

    def fake_executor(request):
        calls.append(request.node_id)
        return {"ok": True}

    register_execution_action("test.echo", fake_executor)
    request = ExecutionActionRequest(
        run_id="run-1",
        node_id="execution_action:echo",
        action_key="test.echo",
        owner_user_id="test-user",
        inputs={"value": "AX"},
        config={},
        approval_mode="never",
        artifact_ids=[],
    )

    first = execute_execution_action(db, request)
    second = execute_execution_action(db, request)

    assert first.output_json == {"ok": True}
    assert second.output_json == {"ok": True}
    assert calls == ["execution_action:echo"]


def test_execution_action_every_run_creates_pending_approval(db):
    request = ExecutionActionRequest(
        run_id="run-1",
        node_id="execution_action:echo",
        action_key="test.echo",
        owner_user_id="test-user",
        inputs={"value": "AX"},
        config={},
        approval_mode="every_run",
        artifact_ids=[],
    )

    result = execute_execution_action(db, request)
    repeated = execute_execution_action(db, request)

    assert result.status == "pending_approval"
    assert repeated.id == result.id
    assert result.output_json == {}
    approval = db.query(models.HumanFeedbackRequest).filter_by(run_id="run-1", node_id="execution_action:echo").one()
    assert approval.prompt_json["approval_type"] == "execution_action"
    assert approval.prompt_json["action_key"] == "test.echo"


def test_flow_graph_accepts_execution_action_node():
    graph = _action_flow_graph()

    document = FlowGraphDocument.model_validate(graph)
    snapshot = FlowGraphLoader().validate(graph, published_crew_lookup=_unused_crew_lookup)

    assert [node.type for node in document.nodes] == ["input", "start", "execution_action", "output"]
    assert snapshot["graph"]["nodes"][2]["data"]["action_key"] == "test.echo"


def test_flow_snapshot_executor_runs_execution_action_and_stores_output(db):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=_action_runtime_snapshot())
    calls = []

    def fake_executor(request):
        calls.append(request.inputs)
        return {"echoed": request.inputs["message"], "source": request.inputs["prior"]}

    register_execution_action("test.echo", fake_executor)

    result = FlowSnapshotExecutor(db)._execute_run_path(
        run=run,
        snapshot=_action_runtime_snapshot(),
        state={
            "inputs": {"message": "AX"},
            "state": {"message": "AX"},
            "node_outputs": {"crew:previous": {"summary": "upstream"}},
            "node_output_refs": {},
            "node_output_versions": {},
            "transfer_values": {},
            "human_feedback": {},
            "human_feedback_history": [],
            "run_options": {"capture_agent_execution_logs": False},
        },
        owner_user_id=owner_user_id,
        capture_agent_execution_logs=False,
    )

    assert result.status == "completed"
    assert result.output_json == {"Result": "AX", "Source": "upstream"}
    assert calls == [{"message": "AX", "literal": "fixed", "prior": "upstream"}]
    stored = db.query(models.FlowRunNodeOutput).filter_by(run_id=run.id, node_id="execution_action:echo").one()
    assert stored.output_json == {"echoed": "AX", "source": "upstream"}


def test_flow_snapshot_executor_passes_db_context_to_google_drive_action(db, monkeypatch):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=_action_runtime_snapshot())
    seen = {}

    class FakeDriveClient:
        def upload_file(self, *, filename, mime_type, content_bytes, target_folder_id):
            return {
                "drive_file_id": "drive-file-1",
                "web_view_link": "https://drive.example/view",
                "web_content_link": "https://drive.example/content",
                "mime_type": mime_type,
            }

    def fake_build_drive_client_from_runtime(*, db, owner_user_id):
        seen["db"] = db
        seen["owner_user_id"] = owner_user_id
        return FakeDriveClient()

    monkeypatch.setattr("api.runtime.execution_actions.load_artifact_bytes", lambda *_args, **_kwargs: b"image")
    monkeypatch.setattr(
        "api.runtime.execution_actions.build_drive_client_from_runtime",
        fake_build_drive_client_from_runtime,
    )

    result = FlowSnapshotExecutor(db)._execute_execution_action_node(
        run=run,
        node={
            "id": "execution_action:drive",
            "type": "execution_action",
            "data": {
                "action_key": "ax.google_drive_upload",
                "input_bindings": {
                    "artifact_id": {"source": "literal", "value": "artifact-1"},
                },
                "config_json": {"filename_template": "image.png", "mime_type": "image/png"},
                "approval_mode": "never",
            },
        },
        state={
            "inputs": {},
            "state": {},
            "node_outputs": {},
            "node_output_refs": {},
            "node_output_versions": {},
            "transfer_values": {},
            "human_feedback": {},
            "human_feedback_history": [],
            "run_options": {"capture_agent_execution_logs": False},
        },
        owner_user_id=owner_user_id,
    )

    assert result.status == "succeeded"
    assert seen == {"db": db, "owner_user_id": owner_user_id}


def test_load_artifact_bytes_fetches_ax_managed_artifact_from_safe_provider_url(
    db,
    monkeypatch,
):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=_drive_action_runtime_snapshot())
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="artifacts/run-1/generated.png",
        storage_path="artifacts/run-1/generated.png",
        source_tool="nano_banana",
        source_capability="image_generation",
        metadata_json={
            "provider_media_url": "https://cdn.example/storage/v1/object/public/ax-public-artifacts/artifacts/run-1/generated.png",
        },
    )
    calls = []

    response = FakeStreamResponse([b"supabase-", b"image-bytes"])

    def fake_stream(method, url, *, timeout, follow_redirects):
        calls.append(
            {
                "method": method,
                "url": url,
                "timeout": timeout,
                "follow_redirects": follow_redirects,
            }
        )
        return FakeStreamContext(response)

    monkeypatch.setattr("api.runtime.execution_actions.httpx.stream", fake_stream)

    assert load_artifact_bytes(
        artifact_id=str(artifact.id),
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        db=db,
    ) == b"supabase-image-bytes"
    assert calls == [
        {
            "method": "GET",
            "url": "https://cdn.example/storage/v1/object/public/ax-public-artifacts/artifacts/run-1/generated.png",
            "timeout": 10.0,
            "follow_redirects": False,
        }
    ]


def test_load_artifact_bytes_rejects_redirecting_provider_url(
    db,
    monkeypatch,
):
    import httpx

    owner_user_id = "11111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=_drive_action_runtime_snapshot())
    provider_url = "https://cdn.example/storage/v1/object/public/ax-public-artifacts/redirect.png"
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="artifacts/run-1/redirect.png",
        storage_path="artifacts/run-1/redirect.png",
        source_tool="nano_banana",
        source_capability="image_generation",
        metadata_json={"provider_media_url": provider_url},
    )
    calls = []

    request = httpx.Request("GET", provider_url)
    redirect_response = httpx.Response(
        302,
        headers={"location": "http://127.0.0.1/latest/meta-data"},
        request=request,
    )
    response = FakeStreamResponse(
        [],
        status_error=httpx.HTTPStatusError("redirect", request=request, response=redirect_response),
    )

    def fake_stream(method, url, *, timeout, follow_redirects):
        calls.append({"method": method, "url": url, "timeout": timeout, "follow_redirects": follow_redirects})
        return FakeStreamContext(response)

    monkeypatch.setattr("api.runtime.execution_actions.httpx.stream", fake_stream)

    with pytest.raises(ValueError, match="Artifact file could not be fetched."):
        load_artifact_bytes(
            artifact_id=str(artifact.id),
            owner_user_id=owner_user_id,
            run_id=str(run.id),
            db=db,
        )

    assert calls == [{"method": "GET", "url": provider_url, "timeout": 10.0, "follow_redirects": False}]
    assert response.chunks_consumed == 0


def test_load_artifact_bytes_rejects_oversized_provider_response(
    db,
    monkeypatch,
):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=_drive_action_runtime_snapshot())
    provider_url = "https://cdn.example/storage/v1/object/public/ax-public-artifacts/huge.png"
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="artifacts/run-1/huge.png",
        storage_path="artifacts/run-1/huge.png",
        source_tool="nano_banana",
        source_capability="image_generation",
        metadata_json={"provider_media_url": provider_url},
    )

    response = FakeStreamResponse(
        [
            b"x" * MAX_PROVIDER_ARTIFACT_BYTES,
            b"y",
            b"this chunk must not be consumed",
        ]
    )
    calls = []

    def fake_stream(method, url, *, timeout, follow_redirects):
        calls.append({"method": method, "url": url, "timeout": timeout, "follow_redirects": follow_redirects})
        return FakeStreamContext(response)

    monkeypatch.setattr("api.runtime.execution_actions.httpx.stream", fake_stream)

    with pytest.raises(ValueError, match="Artifact file is too large to fetch."):
        load_artifact_bytes(
            artifact_id=str(artifact.id),
            owner_user_id=owner_user_id,
            run_id=str(run.id),
            db=db,
        )
    assert calls == [{"method": "GET", "url": provider_url, "timeout": 10.0, "follow_redirects": False}]
    assert response.chunks_consumed == 2


def test_load_artifact_bytes_sanitizes_provider_url_fetch_failures(
    db,
    monkeypatch,
):
    import httpx

    owner_user_id = "11111111-1111-4111-8111-111111111111"
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=_drive_action_runtime_snapshot())
    provider_url = "https://cdn.example/storage/v1/object/public/ax-public-artifacts/private-image.png"
    artifact = create_artifact_metadata(
        db,
        owner_user_id=owner_user_id,
        run_id=str(run.id),
        node_id="generate-image",
        artifact_type="image",
        media_type="image/png",
        storage_backend="ax_managed",
        storage_reference="artifacts/run-1/generated.png",
        storage_path="artifacts/run-1/generated.png",
        source_tool="nano_banana",
        source_capability="image_generation",
        metadata_json={"provider_media_url": provider_url},
    )

    def fake_stream(method, url, *, timeout, follow_redirects):
        raise httpx.ConnectError(f"connection failed for {url}")

    monkeypatch.setattr("api.runtime.execution_actions.httpx.stream", fake_stream)

    with pytest.raises(ValueError) as exc_info:
        load_artifact_bytes(
            artifact_id=str(artifact.id),
            owner_user_id=owner_user_id,
            run_id=str(run.id),
            db=db,
        )

    message = str(exc_info.value)
    assert "Artifact file could not be fetched." in message
    assert provider_url not in message
    assert "cdn.example" not in message


def test_flow_snapshot_executor_redacts_google_drive_token_from_action_failure(db, monkeypatch):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    access_token = "drive-access-token-secret"
    drive_token = RuntimeOAuthToken(
        credential_id="credential-1",
        provider="google_workspace",
        access_token=access_token,
        expires_at=None,
        scopes=["https://www.googleapis.com/auth/drive.file"],
        provider_account_id=None,
        provider_account_label=None,
    )
    snapshot = _drive_action_runtime_snapshot()
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=snapshot)

    def fake_resolve_drive_token(*_args, **_kwargs):
        return drive_token

    def failing_drive_client_builder(resolved_access_token):
        raise RuntimeError(f"drive builder failed with {resolved_access_token}")

    monkeypatch.setattr("api.runtime.execution_actions.load_artifact_bytes", lambda *_args, **_kwargs: b"image")
    monkeypatch.setattr(
        "api.integrations.google_workspace.resolve_google_drive_runtime_token",
        fake_resolve_drive_token,
    )
    monkeypatch.setattr(
        "api.runtime.flow_snapshot_executor.resolve_google_drive_runtime_token",
        fake_resolve_drive_token,
        raising=False,
    )
    monkeypatch.setattr(
        "api.integrations.google_workspace.build_drive_client_from_access_token",
        failing_drive_client_builder,
    )

    result = FlowSnapshotExecutor(db)._execute_run_path(
        run=run,
        snapshot=snapshot,
        state={
            "inputs": {},
            "state": {},
            "node_outputs": {},
            "node_output_refs": {},
            "node_output_versions": {},
            "transfer_values": {},
            "human_feedback": {},
            "human_feedback_history": [],
            "run_options": {"capture_agent_execution_logs": False},
        },
        owner_user_id=owner_user_id,
        capture_agent_execution_logs=False,
    )

    assert result.status == "failed"
    assert result.error_message is not None
    assert access_token not in result.error_message
    assert "[redacted]" in result.error_message
    failed_event = (
        db.query(models.FlowRunEvent)
        .filter_by(run_id=run.id, event_type="run_failed")
        .one()
    )
    serialized_payload = str(failed_event.event_payload_json)
    assert access_token not in serialized_payload
    assert "[redacted]" in serialized_payload


def test_flow_snapshot_executor_rolls_back_pending_action_run_after_action_exception(db):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    snapshot = _action_runtime_snapshot()
    snapshot["graph"]["nodes"][2]["data"]["action_key"] = "test.failing_action"
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=snapshot)
    db.commit()

    def failing_executor(request):
        raise RuntimeError("publish failed after pending action row")

    register_execution_action("test.failing_action", failing_executor)

    result = FlowSnapshotExecutor(db)._execute_run_path(
        run=run,
        snapshot=snapshot,
        state={
            "inputs": {"message": "AX"},
            "state": {"message": "AX"},
            "node_outputs": {"crew:previous": {"summary": "upstream"}},
            "node_output_refs": {},
            "node_output_versions": {},
            "transfer_values": {},
            "human_feedback": {},
            "human_feedback_history": [],
            "run_options": {"capture_agent_execution_logs": False},
        },
        owner_user_id=owner_user_id,
        capture_agent_execution_logs=False,
    )

    assert result.status == "failed"
    assert "publish failed after pending action row" in (result.error_message or "")
    assert (
        db.query(models.ExecutionActionRun)
        .filter_by(
            run_id=str(run.id),
            node_id="execution_action:echo",
            action_key="test.failing_action",
        )
        .one_or_none()
        is None
    )


def test_flow_snapshot_executor_pauses_for_execution_action_approval(db):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    snapshot = _action_runtime_snapshot(approval_mode="every_run")
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=snapshot)

    result = FlowSnapshotExecutor(db)._execute_run_path(
        run=run,
        snapshot=snapshot,
        state={
            "inputs": {"message": "AX"},
            "state": {"message": "AX"},
            "node_outputs": {},
            "node_output_refs": {},
            "node_output_versions": {},
            "transfer_values": {},
            "human_feedback": {},
            "human_feedback_history": [],
            "run_options": {"capture_agent_execution_logs": False},
        },
        owner_user_id=owner_user_id,
        capture_agent_execution_logs=False,
    )

    assert result.status == "paused"
    approval = db.query(models.HumanFeedbackRequest).filter_by(run_id=run.id, node_id="execution_action:echo").one()
    assert approval.prompt_json["approval_type"] == "execution_action"


def test_approved_execution_action_runs_once_and_continues_downstream(db):
    owner_user_id = "11111111-1111-4111-8111-111111111111"
    snapshot = _action_runtime_snapshot(approval_mode="every_run")
    run = _create_flow_run(db, owner_user_id=owner_user_id, snapshot=snapshot)
    calls = []

    def fake_executor(request):
        calls.append(request.inputs)
        return {"echoed": request.inputs["message"], "source": request.inputs["prior"]}

    register_execution_action("test.echo", fake_executor)
    executor = FlowSnapshotExecutor(db)

    paused = executor._execute_run_path(
        run=run,
        snapshot=snapshot,
        state={
            "inputs": {"message": "AX"},
            "state": {"message": "AX"},
            "node_outputs": {"crew:previous": {"summary": "upstream"}},
            "node_output_refs": {},
            "node_output_versions": {},
            "transfer_values": {},
            "human_feedback": {},
            "human_feedback_history": [],
            "run_options": {"capture_agent_execution_logs": False},
        },
        owner_user_id=owner_user_id,
        capture_agent_execution_logs=False,
    )

    assert paused.status == "paused"
    assert calls == []

    approval = db.query(models.HumanFeedbackRequest).filter_by(run_id=run.id, node_id="execution_action:echo").one()
    completed = executor.resume_run(
        run_id=str(run.id),
        owner_user_id=owner_user_id,
        request_id=str(approval.id),
        outcome="approved",
        feedback="",
        idempotency_key="approve-action-once",
    )

    assert completed.status == "completed"
    assert completed.output_json == {"Result": "AX", "Source": "upstream"}
    assert calls == [{"message": "AX", "literal": "fixed", "prior": "upstream"}]
    action_run = db.query(models.ExecutionActionRun).filter_by(run_id=run.id, node_id="execution_action:echo").one()
    assert action_run.status == "succeeded"
    stored = db.query(models.FlowRunNodeOutput).filter_by(run_id=run.id, node_id="execution_action:echo").one()
    assert stored.output_json == {"echoed": "AX", "source": "upstream"}

    with pytest.raises(HumanFeedbackConflictError):
        executor.resume_run(
            run_id=str(run.id),
            owner_user_id=owner_user_id,
            request_id=str(approval.id),
            outcome="approved",
            feedback="",
            idempotency_key="approve-action-once-duplicate",
        )
    assert calls == [{"message": "AX", "literal": "fixed", "prior": "upstream"}]


def _unused_crew_lookup(*, asset_id: str, version_id: str) -> dict | None:
    raise AssertionError("execution action graph should not require crew lookup")


def _action_flow_graph() -> dict:
    return {
        "schemaVersion": 1,
        "nodes": [
            {
                "id": "input:main",
                "type": "input",
                "position": {"x": 0, "y": 0},
                "data": {"fields": [{"name": "message", "type": "string", "required": True}]},
            },
            {
                "id": "start:main",
                "type": "start",
                "position": {"x": 100, "y": 0},
                "data": {"triggerType": "manual"},
            },
            {
                "id": "execution_action:echo",
                "type": "execution_action",
                "position": {"x": 200, "y": 0},
                "data": {
                    "action_key": "test.echo",
                    "input_bindings": {"message": {"source": "state", "path": "message"}},
                    "config_json": {"dry_run": True},
                    "approval_mode": "never",
                },
            },
            {
                "id": "output:main",
                "type": "output",
                "position": {"x": 300, "y": 0},
                "data": {
                    "fields": [
                        {
                            "label": "Result",
                            "source": "node",
                            "nodeId": "execution_action:echo",
                            "path": "output.echoed",
                        }
                    ]
                },
            },
        ],
        "edges": [
            {"id": "edge:start:action", "source": "start:main", "target": "execution_action:echo", "type": "flow"},
            {"id": "edge:action:output", "source": "execution_action:echo", "target": "output:main", "type": "flow"},
        ],
    }


def _action_runtime_snapshot(*, approval_mode: str = "never") -> dict:
    graph = _action_flow_graph()
    graph["nodes"][2]["data"]["approval_mode"] = approval_mode
    graph["nodes"][2]["data"]["input_bindings"] = {
        "message": {"source": "state", "path": "message"},
        "literal": {"source": "literal", "value": "fixed"},
        "prior": {"source": "node", "nodeId": "crew:previous", "path": "output.summary"},
    }
    return {
        "schemaVersion": 1,
        "graph": graph,
        "state_schema": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
        "crew_refs": [],
        "crew_input_mappings": {},
        "router_conditions": {},
        "hitl_contracts": {},
        "output_fields": [
            {"label": "Result", "source": "node", "nodeId": "execution_action:echo", "path": "output.echoed"},
            {"label": "Source", "source": "node", "nodeId": "execution_action:echo", "path": "output.source"},
        ],
    }


def _drive_action_runtime_snapshot() -> dict:
    graph = _action_flow_graph()
    graph["nodes"][2]["id"] = "execution_action:drive"
    graph["nodes"][2]["data"] = {
        "action_key": "ax.google_drive_upload",
        "input_bindings": {
            "artifact_id": {"source": "literal", "value": "artifact-1"},
        },
        "config_json": {"filename_template": "image.png", "mime_type": "image/png"},
        "approval_mode": "never",
    }
    graph["nodes"][3]["data"]["fields"] = [
        {
            "label": "Drive File",
            "source": "node",
            "nodeId": "execution_action:drive",
            "path": "output.drive_file_id",
        }
    ]
    graph["edges"][0]["target"] = "execution_action:drive"
    graph["edges"][1]["source"] = "execution_action:drive"
    return {
        "schemaVersion": 1,
        "graph": graph,
        "state_schema": {"type": "object", "properties": {}},
        "crew_refs": [],
        "crew_input_mappings": {},
        "router_conditions": {},
        "hitl_contracts": {},
        "output_fields": [
            {
                "label": "Drive File",
                "source": "node",
                "nodeId": "execution_action:drive",
                "path": "output.drive_file_id",
            }
        ],
    }


def _create_flow_run(db, *, owner_user_id: str, snapshot: dict) -> models.FlowRun:
    asset = models.Asset(
        id="22222222-2222-4222-8222-222222222222",
        asset_type="flow",
        workspace_id="33333333-3333-4333-8333-333333333333",
        owner_user_id=owner_user_id,
        name="Action Flow",
    )
    version = models.AssetVersion(
        id="44444444-4444-4444-8444-444444444444",
        asset_id=asset.id,
        version_number=1,
        status="published",
        created_by=owner_user_id,
        payload_json={},
    )
    runtime_snapshot = models.AssetRuntimeSnapshot(version_id=version.id, runtime_snapshot_json=snapshot)
    run = models.FlowRun(
        id="55555555-5555-4555-8555-555555555555",
        flow_version_id=version.id,
        status="running",
        input_json={"message": "AX"},
    )
    db.add_all([asset, version, runtime_snapshot, run])
    db.flush()
    return run
