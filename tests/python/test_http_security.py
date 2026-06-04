from fastapi.testclient import TestClient

from qrics.api.http_app import create_http_app
from qrics.api.schemas import ApiRole


def _headers(role: ApiRole = "operator", request_id: str = "req-http-sec") -> dict[str, str]:
    return {"x-request-id": request_id, "x-actor-id": "tester", "x-actor-role": role}


def _policy_payload(version: str = "1.0.0") -> dict[str, object]:
    return {
        "policy_ref": {"id": "flat_nav", "version": version},
        "artifact_uri": f"artifact://policies/flat_nav/{version}/model.pt",
        "metrics": {
            "success_rate": 0.95,
            "collision_rate": 0.01,
            "tracking_error_m": 0.08,
            "recovery_rate": 0.90,
            "energy_proxy": 30.0,
        },
    }


def test_http_training_defaults_to_operator_and_is_forbidden() -> None:
    client = TestClient(create_http_app())

    denied = client.post(
        "/api/v1/training/plans",
        json={
            "training_id": "train-http",
            "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
        },
    )
    assert denied.status_code == 403
    assert denied.json()["errors"][0]["code"] == "FORBIDDEN"

    allowed = client.post(
        "/api/v1/training/plans",
        headers=_headers("algorithm_engineer"),
        json={
            "training_id": "train-http",
            "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["state"] == "queued"


def test_http_audit_defaults_to_operator_and_is_forbidden() -> None:
    client = TestClient(create_http_app())

    denied = client.get("/api/v1/audit")
    assert denied.status_code == 403
    assert denied.json()["errors"][0]["code"] == "FORBIDDEN"

    allowed = client.get("/api/v1/audit", headers=_headers("auditor"))
    assert allowed.status_code == 200
    assert allowed.json()["data"]["count"] == 1


def test_http_state_conflict_maps_to_409() -> None:
    client = TestClient(create_http_app())

    submitted = client.post("/api/v1/tasks", headers=_headers(), json={"source_text": "巡检A"})
    assert submitted.status_code == 200
    task_id = submitted.json()["data"]["task_id"]

    assert client.post(f"/api/v1/tasks/{task_id}/confirm", headers=_headers()).status_code == 200
    conflicted = client.post(f"/api/v1/tasks/{task_id}/confirm", headers=_headers())
    assert conflicted.status_code == 409
    assert conflicted.json()["errors"][0]["code"] == "STATE_CONFLICT"


def test_http_policy_release_requires_reason_and_writes_denied_audit() -> None:
    client = TestClient(create_http_app())
    policy_ref = {"id": "flat_nav", "version": "1.0.0"}

    assert (
        client.post(
            "/api/v1/policies",
            headers=_headers("algorithm_engineer"),
            json=_policy_payload("1.0.0"),
        ).status_code
        == 200
    )

    denied = client.post(
        "/api/v1/policies/flat_nav/1.0.0/release",
        headers=_headers("algorithm_engineer"),
        json={"reason": ""},
    )
    assert denied.status_code == 422
    assert denied.json()["errors"][0]["code"] == "INVALID_REQUEST"

    gate = client.post(
        "/api/v1/policies/gate-report",
        headers=_headers("algorithm_engineer"),
        json={"policy_ref": policy_ref, "decision": "passed", "reason": "meets gate"},
    )
    assert gate.status_code == 200

    released = client.post(
        "/api/v1/policies/flat_nav/1.0.0/release",
        headers=_headers("algorithm_engineer"),
        json={"reason": "release approved"},
    )
    assert released.status_code == 200

    audit = client.get(
        "/api/v1/audit",
        headers=_headers("auditor"),
        params={"action": "policy.release"},
    )
    assert audit.status_code == 200
    assert audit.json()["data"]["count"] == 2


def test_http_events_use_unified_response_shape() -> None:
    client = TestClient(create_http_app())

    submitted = client.post("/api/v1/tasks", headers=_headers(), json={"source_text": "巡检A"})
    assert submitted.status_code == 200

    denied = client.get("/api/v1/events")
    assert denied.status_code == 200
    assert denied.json()["ok"] is True
    assert "count" in denied.json()["data"]

    auditor = client.get("/api/v1/events", headers=_headers("auditor"))
    assert auditor.status_code == 200
    assert auditor.json()["ok"] is True
    assert auditor.json()["data"]["count"] >= 1


def test_unknown_http_role_is_normalized_to_operator_without_elevation() -> None:
    client = TestClient(create_http_app())

    response = client.post(
        "/api/v1/training/plans",
        headers={"x-request-id": "req-bad-role", "x-actor-id": "tester", "x-actor-role": "root"},
        json={
            "training_id": "train-unknown-role",
            "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
        },
    )

    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "FORBIDDEN"


def test_http_override_rejects_unknown_command_type() -> None:
    client = TestClient(create_http_app())
    submitted = client.post("/api/v1/tasks", headers=_headers(), json={"source_text": "巡检A"})
    task_id = submitted.json()["data"]["task_id"]
    assert client.post(f"/api/v1/tasks/{task_id}/confirm", headers=_headers()).status_code == 200
    handoff = client.post(f"/api/v1/tasks/{task_id}/handoff", headers=_headers())
    run_id = handoff.json()["data"]["run_id"]

    response = client.post(
        f"/api/v1/control/{run_id}/override",
        headers=_headers(),
        json={"command_type": "fly", "reason": "invalid command test"},
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "INVALID_REQUEST"
    assert "command_type" in response.json()["errors"][0]["message"]


def test_http_gate_report_rejects_unknown_decision() -> None:
    client = TestClient(create_http_app())
    assert (
        client.post(
            "/api/v1/policies",
            headers=_headers("algorithm_engineer"),
            json=_policy_payload("1.0.2"),
        ).status_code
        == 200
    )

    response = client.post(
        "/api/v1/policies/gate-report",
        headers=_headers("algorithm_engineer"),
        json={
            "policy_ref": {"id": "flat_nav", "version": "1.0.2"},
            "decision": "maybe",
            "reason": "invalid gate decision test",
        },
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "INVALID_REQUEST"
    assert "decision" in response.json()["errors"][0]["message"]
