from fastapi.testclient import TestClient

from qrics.api.http_app import create_http_app
from qrics.api.schemas import ApiRole


def _headers(role: ApiRole = "operator") -> dict[str, str]:
    return {"x-request-id": "req-web-console", "x-actor-id": "tester", "x-actor-role": role}


def _create_typed_scene(client: TestClient) -> None:
    response = client.post(
        "/api/v1/scenes",
        headers=_headers("test_engineer"),
        json={
            "scene_id": "web_console_scene",
            "version": "0.1.0",
            "name": "Web Console scene",
            "terrain_pack": "mixed_terrain_pack",
            "assets": [
                {
                    "asset_id": "mixed_terrain",
                    "asset_type": "terrain",
                    "uri": "builtin://qrics/terrain/mixed_terrain_pack",
                    "checksum": "builtin-mixed",
                },
                {
                    "asset_id": "near_box",
                    "asset_type": "obstacle",
                    "geometry_type": "box",
                    "position": [0.12, 0.0, 0.12],
                    "size": [0.16, 0.16, 0.24],
                },
            ],
            "sensor_profile": {"profile_id": "web_console_sensors", "sample_rate_hz": 100},
            "change_summary": "web console test scene",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["asset_count"] == 2


def test_web_console_static_files_and_backend_catalog() -> None:
    client = TestClient(create_http_app())

    root = client.get("/", follow_redirects=False)
    assert root.status_code in {307, 308}
    assert root.headers["location"] == "/console/"

    console = client.get("/console/")
    assert console.status_code == 200
    assert "QRICS 本机演示控制台" in console.text
    assert "加载已保存场景" in console.text
    assert "添加检查点" in console.text
    assert "添加禁行区" in console.text
    assert "导出场景 JSON" in console.text
    assert "导入场景 JSON" in console.text

    catalog = client.get("/api/v1/sim/backends", headers=_headers())
    assert catalog.status_code == 200
    data = catalog.json()["data"]
    assert "mujoco" in data["backends"]
    assert "webots" in data["backends"]
    assert "balanced_visual" in data["runtime_profiles"]


def test_simulation_preview_uses_selected_scene_and_run_options() -> None:
    client = TestClient(create_http_app())
    _create_typed_scene(client)

    preview = client.post(
        "/api/v1/sim/preview",
        headers=_headers(),
        json={
            "scene_ref": {"id": "web_console_scene", "version": "0.1.0"},
            "run_options": {
                "backend": "minimal",
                "runtime_profile": "headless_fast",
                "step_count": 4,
                "forward_velocity_mps": 0.3,
                "obstacle_replan_distance_m": 0.25,
            },
        },
    )

    assert preview.status_code == 200
    data = preview.json()["data"]
    assert data["state"] == "succeeded"
    assert data["backend"] == "minimal"
    assert data["runtime_profile"] == "headless_fast"
    assert data["control_step_count"] == 4
    assert data["obstacle_detected"] is True
    assert data["safety_event_count"] > 0


def test_task_handoff_accepts_web_console_run_options() -> None:
    client = TestClient(create_http_app())
    _create_typed_scene(client)

    task = client.post(
        "/api/v1/tasks",
        headers=_headers(),
        json={
            "source_text": "巡检A后回到平台待命",
            "scene_ref": {"id": "web_console_scene", "version": "0.1.0"},
        },
    )
    assert task.status_code == 200
    task_id = task.json()["data"]["task_id"]
    assert client.post(f"/api/v1/tasks/{task_id}/confirm", headers=_headers()).status_code == 200

    handoff = client.post(
        f"/api/v1/tasks/{task_id}/handoff",
        headers=_headers(),
        json={
            "run_options": {
                "backend": "minimal",
                "runtime_profile": "headless_fast",
                "step_count": 6,
            }
        },
    )

    assert handoff.status_code == 200
    data = handoff.json()["data"]
    assert data["state"] == "running"
    assert data["backend"] == "minimal"
    assert data["control_step_count"] == 6
    assert data["latest_action"] == "replan"
    assert data["gait_name"] in {"stand", "crawl", "trot", "cautious_trot"}
    assert "joint_command_count" in data


def test_task_targets_use_scene_checkpoint_positions() -> None:
    from qrics.api.app import QricsApiApp, _parse_demo_waypoints
    from qrics.api.schemas import RequestContext, ResourceRef, SceneAssetPayload, SceneCreatePayload

    app = QricsApiApp(simulation_runner=None)
    scene_ref = ResourceRef("checkpoint_scene", "0.1.0")
    created = app.create_scene(
        SceneCreatePayload(
            scene_id=scene_ref.id,
            version=scene_ref.version,
            terrain_pack="flat",
            assets=(
                SceneAssetPayload(
                    asset_id="巡检点A",
                    asset_type="checkpoint",
                    position=(0.42, 0.58, 0.02),
                ),
                SceneAssetPayload(
                    asset_id="平台",
                    asset_type="checkpoint",
                    position=(-0.12, 0.04, 0.02),
                ),
            ),
        ),
        RequestContext(request_id="req-checkpoint", actor_id="tester", role="test_engineer"),
    )
    assert created.ok

    targets = app._simulation_task_path(scene_ref, _parse_demo_waypoints("先巡检A，再回到平台"))

    assert [(target.target_id, round(target.x, 2), round(target.y, 2)) for target in targets] == [
        ("A", 0.42, 0.58),
        ("platform", -0.12, 0.04),
    ]
