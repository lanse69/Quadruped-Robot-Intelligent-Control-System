from collections.abc import Mapping

from qrics.api.app import create_demo_app
from qrics.api.routes_audit import query_audit
from qrics.api.routes_scenes import (
    archive_scene,
    copy_scene,
    create_scene,
    get_scene,
    list_scenes,
    publish_scene_baseline,
)
from qrics.api.routes_tasks import submit_task
from qrics.api.routes_training import submit_training_plan
from qrics.api.schemas import (
    AuditQuery,
    JsonValue,
    RandomizationProfilePayload,
    RequestContext,
    ResourceRef,
    SceneAssetPayload,
    SceneCopyPayload,
    SceneCreatePayload,
    SensorProfilePayload,
    TaskSubmissionPayload,
    TrainingPlanPayload,
)


def _json_records(data: Mapping[str, JsonValue]) -> list[dict[str, str]]:
    value = data["records"]
    assert isinstance(value, list)
    rows: list[dict[str, str]] = []
    for item in value:
        assert isinstance(item, dict)
        rows.append({str(key): str(row_value) for key, row_value in item.items()})
    return rows


def test_scene_profile_create_copy_publish_archive_and_usage() -> None:
    app = create_demo_app()
    tester = RequestContext(request_id="req-scene-1", actor_id="tester-1", role="test_engineer")
    operator = RequestContext(
        request_id="req-scene-operator", actor_id="operator-1", role="operator"
    )
    auditor = RequestContext(request_id="req-scene-audit", actor_id="auditor-1", role="auditor")

    created = create_scene(
        app,
        SceneCreatePayload(
            scene_id="mixed_eval",
            version="0.1.0",
            name="Mixed terrain evaluation scene",
            terrain_pack="mixed",
            assets=(
                SceneAssetPayload(
                    asset_id="terrain_mixed_v1",
                    asset_type="terrain",
                    uri="builtin://qrics/terrain/mixed",
                    checksum="sha256:mixed",
                ),
                SceneAssetPayload(
                    asset_id="obstacle_box_1",
                    asset_type="obstacle",
                    geometry_type="box",
                    position=(0.80, 0.10, 0.20),
                    size=(0.30, 0.20, 0.40),
                ),
            ),
            sensor_profile=SensorProfilePayload(
                profile_id="imu_contact_lidar",
                lidar_enabled=True,
                imu_enabled=True,
                foot_contact_enabled=True,
                sample_rate_hz=120,
            ),
            randomization_profile=RandomizationProfilePayload(
                profile_id="train_randomization_v1",
                enabled=True,
                friction_range=(0.7, 1.2),
                mass_scale_range=(0.9, 1.1),
                sensor_noise_std=0.01,
            ),
            change_summary="create reusable mixed terrain scene",
        ),
        tester,
    )

    assert created.ok
    assert created.data["state"] == "draft"
    assert created.data["asset_count"] == 2
    assert created.data["terrain_pack"] == "mixed"
    assert created.data["validation_errors"] == []
    assets = created.data["assets"]
    assert isinstance(assets, list)
    obstacle_asset = next(
        item for item in assets if isinstance(item, dict) and item["asset_id"] == "obstacle_box_1"
    )
    assert obstacle_asset["geometry_type"] == "box"
    assert obstacle_asset["position"] == [0.8, 0.1, 0.2]
    assert obstacle_asset["size"] == [0.3, 0.2, 0.4]
    checksum = created.data["checksum"]
    assert isinstance(checksum, str)
    assert len(checksum) == 64

    denied = create_scene(
        app,
        SceneCreatePayload(scene_id="operator_scene", version="0.1.0"),
        operator,
    )
    assert not denied.ok
    assert denied.errors[0].code == "FORBIDDEN"

    publish_without_reason = publish_scene_baseline(
        app,
        ResourceRef("mixed_eval", "0.1.0"),
        tester,
        reason="",
    )
    assert not publish_without_reason.ok
    assert publish_without_reason.errors[0].code == "INVALID_REQUEST"

    published = publish_scene_baseline(
        app,
        ResourceRef("mixed_eval", "0.1.0"),
        tester,
        reason="baseline scene for regression tests",
    )
    assert published.ok
    assert published.data["state"] == "baseline"
    assert published.data["is_current_baseline"] is True

    listed = list_scenes(app, operator, scene_id="mixed_eval")
    assert listed.ok
    assert listed.data["count"] == 1

    task = submit_task(
        app,
        TaskSubmissionPayload(
            source_text="巡检A",
            scene_ref=ResourceRef("mixed_eval", "0.1.0"),
        ),
        operator,
    )
    assert task.ok
    assert task.data["scene_id"] == "mixed_eval"
    assert task.data["scene_version"] == "0.1.0"

    copied = copy_scene(
        app,
        ResourceRef("mixed_eval", "0.1.0"),
        SceneCopyPayload(target_version="0.2.0", change_summary="archive candidate copy"),
        tester,
    )
    assert copied.ok
    assert copied.data["state"] == "draft"
    assert copied.data["is_current_baseline"] is False

    archived = archive_scene(
        app,
        ResourceRef("mixed_eval", "0.2.0"),
        tester,
        reason="not needed for current regression baseline",
    )
    assert archived.ok
    assert archived.data["state"] == "archived"

    training = submit_training_plan(
        app,
        TrainingPlanPayload(
            training_id="train-on-archived-scene",
            scene_ref=ResourceRef("mixed_eval", "0.2.0"),
        ),
        RequestContext(request_id="req-scene-train", actor_id="algo-1", role="algorithm_engineer"),
    )
    assert not training.ok
    assert training.errors[0].code in {"CONFLICT", "STATE_CONFLICT"}

    audit = query_audit(app, AuditQuery(actor_id="tester-1"), auditor)
    assert audit.ok
    actions = {record["action"] for record in _json_records(audit.data)}
    assert "scene.create" in actions
    assert "scene.publish_baseline" in actions
    assert "scene.copy" in actions
    assert "scene.archive" in actions

    fetched = get_scene(app, ResourceRef("mixed_eval", "0.1.0"), operator)
    assert fetched.ok
    assert fetched.data["checksum"] == checksum


def test_scene_validation_blocks_baseline_publish() -> None:
    app = create_demo_app()
    tester = RequestContext(
        request_id="req-scene-invalid", actor_id="tester-1", role="test_engineer"
    )

    created = create_scene(
        app,
        SceneCreatePayload(
            scene_id="invalid_scene",
            version="0.1.0",
            terrain_pack="flat",
            assets=(
                SceneAssetPayload(
                    asset_id="missing_asset",
                    asset_type="obstacle",
                    uri="missing://obstacle.usd",
                    required=True,
                ),
            ),
        ),
        tester,
    )

    assert created.ok
    errors = created.data["validation_errors"]
    assert isinstance(errors, list)
    assert errors

    published = publish_scene_baseline(
        app,
        ResourceRef("invalid_scene", "0.1.0"),
        tester,
        reason="try invalid baseline",
    )

    assert not published.ok
    assert published.errors[0].code in {"CONFLICT", "STATE_CONFLICT"}
