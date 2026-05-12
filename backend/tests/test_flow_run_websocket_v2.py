import pytest
from starlette.websockets import WebSocketDisconnect

from tests.test_flow_run_hitl_v2 import _create_hitl_run, fake_crew  # noqa: F401


def test_flow_run_stream_requires_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/flow-runs/run_123/stream") as websocket:
            websocket.receive_json()


def test_flow_run_stream_sends_persisted_hitl_requested_event(
    client,
    db,
    auth_headers,
    fake_crew,
    monkeypatch,
):
    from api.db.models import HumanFeedbackRequest

    token = "local-stream-token"

    async def fake_authenticate_access_token(value: str):
        assert value == token
        return {"id": "test-user", "email": "test@example.com"}

    monkeypatch.setattr("api.routes.runs.authenticate_access_token", fake_authenticate_access_token)

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    request = db.query(HumanFeedbackRequest).filter(HumanFeedbackRequest.run_id == run["id"]).one()

    with client.websocket_connect(f"/api/flow-runs/{run['id']}/stream") as websocket:
        websocket.send_json({"type": "authenticate", "access_token": token})
        event = websocket.receive_json()
        while event["type"] != "hitl_requested":
            event = websocket.receive_json()

    assert event["type"] == "hitl_requested"
    assert event["run_id"] == run["id"]
    assert event["request_id"] == str(request.id)
    assert event["message"] == "HITL이 실행되었습니다. 계속 진행하시겠습니까?"
    assert event["remaining_retries"] == 3


def test_flow_run_stream_pages_persisted_events_beyond_first_batch(
    client,
    db,
    auth_headers,
    fake_crew,
    monkeypatch,
):
    from datetime import datetime, timezone

    from api.db.models import FlowRunEvent

    token = "local-stream-token"

    async def fake_authenticate_access_token(value: str):
        assert value == token
        return {"id": "test-user", "email": "test@example.com"}

    monkeypatch.setattr("api.routes.runs.authenticate_access_token", fake_authenticate_access_token)

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    db.query(FlowRunEvent).filter(FlowRunEvent.run_id == run["id"]).delete(synchronize_session=False)
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(101):
        db.add(
            FlowRunEvent(
                id=f"00000000-0000-4000-8000-{index + 1:012d}",
                run_id=run["id"],
                node_id="node:page",
                event_type=f"page_event_{index + 1}",
                event_payload_json={"type": f"page_event_{index + 1}", "sequence": index + 1},
                created_at=created_at,
            )
        )
    db.commit()

    with client.websocket_connect(f"/api/flow-runs/{run['id']}/stream") as websocket:
        websocket.send_json({"type": "authenticate", "access_token": token})
        first_batch = [websocket.receive_json() for _ in range(100)]
        websocket.send_text("ping")
        next_event = websocket.receive_json()

    assert first_batch[0]["sequence"] == 1
    assert first_batch[-1]["sequence"] == 100
    assert next_event["type"] == "page_event_101"
    assert next_event["sequence"] == 101


def test_flow_run_stream_sends_late_committed_overlap_event(
    client,
    db,
    auth_headers,
    fake_crew,
    monkeypatch,
):
    from datetime import datetime, timezone

    from api.db.models import FlowRunEvent

    token = "local-stream-token"

    async def fake_authenticate_access_token(value: str):
        assert value == token
        return {"id": "test-user", "email": "test@example.com"}

    monkeypatch.setattr("api.routes.runs.authenticate_access_token", fake_authenticate_access_token)

    run = _create_hitl_run(client, db, auth_headers, fake_crew)
    db.query(FlowRunEvent).filter(FlowRunEvent.run_id == run["id"]).delete(synchronize_session=False)
    overlap_created_at = datetime(2026, 1, 1, 0, 0, 4, tzinfo=timezone.utc)
    for index in range(101):
        db.add(
            FlowRunEvent(
                id=f"00000000-0000-4000-8000-{index + 1:012d}",
                run_id=run["id"],
                node_id="node:overlap",
                event_type=f"overlap_event_{index + 1}",
                event_payload_json={"type": f"overlap_event_{index + 1}", "sequence": index + 1},
                created_at=overlap_created_at,
            )
        )
    db.add(
        FlowRunEvent(
            id="00000000-0000-4000-8000-000000000200",
            run_id=run["id"],
            node_id="node:latest",
            event_type="newer_event",
            event_payload_json={"type": "newer_event", "sequence": 200},
            created_at=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        )
    )
    db.commit()

    with client.websocket_connect(f"/api/flow-runs/{run['id']}/stream") as websocket:
        websocket.send_json({"type": "authenticate", "access_token": token})
        initial_events = [websocket.receive_json() for _ in range(102)]
        db.add(
            FlowRunEvent(
                id="00000000-0000-4000-8000-000000000102",
                run_id=run["id"],
                node_id="node:late",
                event_type="late_event",
                event_payload_json={"type": "late_event", "sequence": 102},
                created_at=overlap_created_at,
            )
        )
        db.commit()
        websocket.send_text("ping")
        late_event = websocket.receive_json()

    assert initial_events[0]["sequence"] == 1
    assert initial_events[100]["sequence"] == 101
    assert initial_events[101]["type"] == "newer_event"
    assert late_event["type"] == "late_event"
    assert late_event["sequence"] == 102
