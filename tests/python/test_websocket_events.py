from fastapi.testclient import TestClient

from qrics.api.http_app import create_http_app


def test_websocket_event_snapshot_after_handoff() -> None:
    client = TestClient(create_http_app())
    headers = {"x-request-id": "req-ws-1", "x-actor-id": "operator-1", "x-actor-role": "operator"}

    submitted = client.post("/api/v1/tasks", headers=headers, json={"source_text": "巡检A"})
    task_id = submitted.json()["data"]["task_id"]
    client.post(f"/api/v1/tasks/{task_id}/confirm", headers=headers)
    handoff = client.post(f"/api/v1/tasks/{task_id}/handoff", headers=headers)
    run_id = handoff.json()["data"]["run_id"]

    with client.websocket_connect(
        f"/api/v1/ws/events?run_id={run_id}"
        "&request_id=req-ws-1&actor_id=operator-1&actor_role=operator"
    ) as websocket:
        first = websocket.receive_json()
        assert first["run_id"] == run_id
        assert first["topic"] == "control.status"
        snapshot = websocket.receive_json()
        assert snapshot["event_id"] == "snapshot_complete"
        assert snapshot["request_id"] == "req-ws-1"
        assert snapshot["payload"]["count"] >= 1
        websocket.send_json({"op": "close"})


def test_websocket_event_snapshot_uses_non_elevated_default_context() -> None:
    client = TestClient(create_http_app())
    headers = {
        "x-request-id": "req-ws-default",
        "x-actor-id": "operator-1",
        "x-actor-role": "operator",
    }

    submitted = client.post("/api/v1/tasks", headers=headers, json={"source_text": "巡检A"})
    task_id = submitted.json()["data"]["task_id"]
    client.post(f"/api/v1/tasks/{task_id}/confirm", headers=headers)
    client.post(f"/api/v1/tasks/{task_id}/handoff", headers=headers)

    with client.websocket_connect("/api/v1/ws/events") as websocket:
        snapshot_seen = False
        for _ in range(10):
            event = websocket.receive_json()
            assert "event_id" in event
            if event["event_id"] == "snapshot_complete":
                snapshot_seen = True
                break
        assert snapshot_seen
        websocket.send_json({"op": "close"})
