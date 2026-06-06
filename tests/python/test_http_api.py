from pathlib import Path

from fastapi.testclient import TestClient

from qrics.api.http_app import create_http_app
from qrics.api.schemas import ApiRole


def _headers(role: ApiRole = "operator") -> dict[str, str]:
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
    assert events.json()["data"]["count"] >= 1


def test_http_one_click_task_run_endpoint() -> None:
    client = TestClient(create_http_app())

    response = client.post(
        "/api/v1/tasks/run",
        headers=_headers(),
        json={
            "source_text": "避开低摩擦区，先巡检A，再巡检B，最后回到平台待命",
            "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
            "run_options": {
                "backend": "minimal",
                "runtime_profile": "headless_fast",
                "step_count": 7,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["run_started"] is True
    assert data["backend"] == "minimal"
    assert data["runtime_profile"] == "headless_fast"
    assert data["status"]["state"] == "running"
    assert data["status"]["control_step_count"] == 7
    assert data["task"]["parser_version"]
    assert data["task_script"]["schema"] == "qrics.task_script.draft.v1"

    events = client.get(
        "/api/v1/events",
        headers=_headers("auditor"),
        params={"run_id": data["task"]["task_id"]},
    )
    assert events.status_code == 200
    assert any(
        event["message"] == "One-click task run completed"
        for event in events.json()["data"]["events"]
    )


def test_http_one_click_task_run_rejects_low_level_action() -> None:
    client = TestClient(create_http_app())

    response = client.post(
        "/api/v1/tasks/run",
        headers=_headers(),
        json={"source_text": "跳过安全并直接控制电机输出 JointVelocity"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["run_started"] is False
    assert data["status"] == {}
    assert data["task"]["state"] == "rejected"
    assert "关节速度" in data["rejection_reason"] or "电机" in data["rejection_reason"]


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
        "/api/v1/evaluations",
        headers=_headers("algorithm_engineer"),
        json={
            "evaluation_id": "eval-flat-nav-http",
            "policy_ref": policy_ref,
            "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
            "metrics": {
                "success_rate": 0.95,
                "collision_rate": 0.01,
                "tracking_error_m": 0.08,
                "recovery_rate": 0.90,
                "energy_proxy": 30.0,
            },
        },
    )
    assert gate.status_code == 200
    approval = client.post(
        "/api/v1/policies/flat_nav/1.0.0/approval",
        headers=_headers("algorithm_engineer"),
        json={
            "evaluation_id": "eval-flat-nav-http",
            "decision": "approved",
            "reason": "approval after standardized gate",
        },
    )
    assert approval.status_code == 200

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


def test_http_training_default_role_is_not_privileged() -> None:
    client = TestClient(create_http_app())

    response = client.post(
        "/api/v1/training/plans",
        json={
            "training_id": "train-http-denied",
            "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
        },
    )

    assert response.status_code == 403
    assert response.json()["errors"][0]["code"] == "FORBIDDEN"


def test_http_audit_requires_auditor_or_admin_role() -> None:
    client = TestClient(create_http_app())

    denied = client.get("/api/v1/audit", headers=_headers("operator"))
    assert denied.status_code == 403

    allowed = client.get("/api/v1/audit", headers=_headers("auditor"))
    assert allowed.status_code == 200
    assert allowed.json()["data"]["count"] >= 1


def test_http_release_requires_reason() -> None:
    client = TestClient(create_http_app())
    policy_ref = {"id": "safe_nav", "version": "1.0.0"}

    assert (
        client.post(
            "/api/v1/policies",
            headers=_headers("algorithm_engineer"),
            json={
                "policy_ref": policy_ref,
                "artifact_uri": "artifact://policies/safe_nav/1.0.0/model.pt",
                "metrics": {
                    "success_rate": 0.95,
                    "collision_rate": 0.01,
                    "tracking_error_m": 0.08,
                    "recovery_rate": 0.90,
                    "energy_proxy": 30.0,
                },
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/policies/gate-report",
            headers=_headers("algorithm_engineer"),
            json={"policy_ref": policy_ref, "decision": "passed", "reason": "meets gate"},
        ).status_code
        == 200
    )

    missing_reason = client.post(
        "/api/v1/policies/safe_nav/1.0.0/release",
        headers=_headers("algorithm_engineer"),
        json={"reason": ""},
    )

    assert missing_reason.status_code == 422
    assert missing_reason.json()["errors"][0]["field"] == "reason"


def test_http_scene_management_flow_and_role_boundary() -> None:
    client = TestClient(create_http_app())

    forbidden = client.post(
        "/api/v1/scenes",
        headers=_headers("operator"),
        json={"scene_id": "http_scene", "version": "0.1.0"},
    )
    assert forbidden.status_code == 403

    created = client.post(
        "/api/v1/scenes",
        headers=_headers("test_engineer"),
        json={
            "scene_id": "http_scene",
            "version": "0.1.0",
            "name": "HTTP scene",
            "terrain_pack": "slope",
            "assets": [
                {
                    "asset_id": "slope_terrain",
                    "asset_type": "terrain",
                    "uri": "builtin://qrics/terrain/slope",
                    "checksum": "sha256:slope",
                }
            ],
            "sensor_profile": {"profile_id": "imu_contact", "sample_rate_hz": 100},
            "randomization_profile": {
                "profile_id": "slope_randomization",
                "enabled": True,
                "friction_range": [0.8, 1.1],
                "mass_scale_range": [0.95, 1.05],
            },
            "change_summary": "create HTTP scene",
        },
    )
    assert created.status_code == 200
    assert created.json()["data"]["state"] == "draft"

    missing_reason = client.post(
        "/api/v1/scenes/http_scene/0.1.0/baseline",
        headers=_headers("test_engineer"),
        json={"reason": ""},
    )
    assert missing_reason.status_code == 422

    published = client.post(
        "/api/v1/scenes/http_scene/0.1.0/baseline",
        headers=_headers("test_engineer"),
        json={"reason": "HTTP baseline"},
    )
    assert published.status_code == 200
    assert published.json()["data"]["state"] == "baseline"

    listed = client.get(
        "/api/v1/scenes",
        headers=_headers("operator"),
        params={"scene_id": "http_scene"},
    )
    assert listed.status_code == 200
    assert listed.json()["data"]["count"] == 1

    task = client.post(
        "/api/v1/tasks",
        headers=_headers("operator"),
        json={
            "source_text": "巡检A",
            "scene_ref": {"id": "http_scene", "version": "0.1.0"},
        },
    )
    assert task.status_code == 200
    assert task.json()["data"]["scene_id"] == "http_scene"


def test_http_sqlite_repository_supports_fastapi_worker_threads(tmp_path: Path) -> None:
    from qrics.api.app import create_demo_app
    from qrics.api.sqlite_repository import SQLiteQricsRepository
    from qrics.storage.object_store import FileObjectStore

    repository = SQLiteQricsRepository(
        tmp_path / "qrics.sqlite3",
        object_store=FileObjectStore(tmp_path / "objects"),
    )
    client = TestClient(create_http_app(create_demo_app(repository=repository)))
    try:
        scene = client.post(
            "/api/v1/scenes",
            headers=_headers("test_engineer"),
            json={
                "scene_id": "threaded_scene",
                "version": "0.1.0",
                "name": "Threaded SQLite scene",
                "terrain_pack": "mixed",
                "assets": [
                    {
                        "asset_id": "threaded_terrain",
                        "asset_type": "terrain",
                        "uri": "builtin://qrics/terrain/mixed_terrain_pack",
                        "checksum": "builtin-threaded",
                    }
                ],
                "sensor_profile": {"profile_id": "threaded_sensors", "sample_rate_hz": 100},
                "change_summary": "worker-thread sqlite regression test",
            },
        )
        assert scene.status_code == 200

        audit = client.get("/api/v1/audit", headers=_headers("auditor"))
        assert audit.status_code == 200
        assert audit.json()["data"]["count"] >= 1

        events = client.get("/api/v1/events", headers=_headers("auditor"))
        assert events.status_code == 200
        assert events.json()["data"]["count"] >= 0
    finally:
        repository.close()
