from fastapi.testclient import TestClient

from qrics.api.http_app import create_http_app


def _headers(role: str = "operator") -> dict[str, str]:
    return {"x-request-id": "req-http-1", "x-actor-id": "tester", "x-actor-role": role}


def test_http_task_handoff_replay_and_events_flow() -> None:
    client = TestClient(create_http_app())

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    submitted = client.post(
        "/api/v1/tasks",
        headers=_headers(),
        json={"source_text": "避开低摩擦区，先巡检A，再巡检B，最后回到平台待命"},
    )
    assert submitted.status_code == 200
    task_id = submitted.json()["data"]["task_id"]

    confirmed = client.post(f"/api/v1/tasks/{task_id}/confirm", headers=_headers())
    assert confirmed.status_code == 200
    assert confirmed.json()["data"]["state"] == "confirmed"

    handoff = client.post(f"/api/v1/tasks/{task_id}/handoff", headers=_headers())
    assert handoff.status_code == 200
    handoff_data = handoff.json()["data"]
    run_id = handoff_data["run_id"]
    assert handoff_data["backend"] == "minimal"
    assert handoff_data["control_step_count"] > 0
    assert handoff_data["sim_time_ns"] > 0

    status = client.get(f"/api/v1/control/{run_id}", headers=_headers())
    assert status.status_code == 200
    assert status.json()["data"]["sim_time_ns"] == handoff_data["sim_time_ns"]

    replay = client.get(f"/api/v1/replay/{run_id}", headers=_headers())
    assert replay.status_code == 200
    assert replay.json()["data"]["last_timestamp_ns"] == handoff_data["sim_time_ns"]

    events = client.get("/api/v1/events", headers=_headers("auditor"), params={"run_id": run_id})
    assert events.status_code == 200
    assert events.json()["count"] >= 1


def test_http_policy_release_requires_engineer_role() -> None:
    client = TestClient(create_http_app())
    policy_ref = {"id": "flat_nav", "version": "1.0.0"}

    registered = client.post(
        "/api/v1/policies",
        headers=_headers("algorithm_engineer"),
        json={
            "policy_ref": policy_ref,
            "artifact_uri": "artifact://policies/flat_nav/1.0.0/model.pt",
            "metrics": {
                "success_rate": 0.95,
                "collision_rate": 0.01,
                "tracking_error_m": 0.08,
                "recovery_rate": 0.90,
                "energy_proxy": 30.0,
            },
        },
    )
    assert registered.status_code == 200

    gate = client.post(
        "/api/v1/policies/gate-report",
        headers=_headers("algorithm_engineer"),
        json={"policy_ref": policy_ref, "decision": "passed", "reason": "meets gate"},
    )
    assert gate.status_code == 200

    forbidden = client.post(
        "/api/v1/policies/flat_nav/1.0.0/release",
        headers=_headers("operator"),
        json={"reason": "operator cannot release"},
    )
    assert forbidden.status_code == 403

    released = client.post(
        "/api/v1/policies/flat_nav/1.0.0/release",
        headers=_headers("algorithm_engineer"),
        json={"reason": "release after gate"},
    )
    assert released.status_code == 200
    assert released.json()["data"]["stage"] == "released"
