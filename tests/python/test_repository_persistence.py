from pathlib import Path

from qrics.api.app import create_demo_app
from qrics.api.routes_audit import query_audit
from qrics.api.routes_control import override_control
from qrics.api.routes_replay import query_replay
from qrics.api.routes_scenes import create_scene, get_scene, publish_scene_baseline
from qrics.api.routes_tasks import confirm_task, handoff_task, submit_task
from qrics.api.schemas import (
    AuditQuery,
    OverridePayload,
    ReplayQuery,
    RequestContext,
    ResourceRef,
    SceneAssetPayload,
    SceneCreatePayload,
    TaskSubmissionPayload,
)
from qrics.api.sqlite_repository import SQLiteQricsRepository
from qrics.storage.object_store import FileObjectStore


def test_sqlite_repository_persists_task_control_replay_audit_and_events(tmp_path: Path) -> None:
    db_path = tmp_path / "metadata.sqlite3"
    object_store = FileObjectStore(tmp_path / "objects")
    repository = SQLiteQricsRepository(db_path, object_store=object_store)
    app = create_demo_app(repository=repository)
    context = RequestContext(request_id="req-persist-1", actor_id="operator-1", role="operator")
    tester = RequestContext(
        request_id="req-persist-scene", actor_id="tester-1", role="test_engineer"
    )

    scene = create_scene(
        app,
        SceneCreatePayload(
            scene_id="persist_scene",
            version="0.1.0",
            terrain_pack="flat",
            assets=(
                SceneAssetPayload(
                    asset_id="persist_flat",
                    asset_type="terrain",
                    uri="builtin://qrics/terrain/flat",
                ),
            ),
        ),
        tester,
    )
    assert scene.ok
    assert publish_scene_baseline(
        app,
        ResourceRef("persist_scene", "0.1.0"),
        tester,
        reason="persistent scene baseline",
    ).ok

    submitted = submit_task(
        app,
        TaskSubmissionPayload(
            source_text="巡检A",
            scene_ref=ResourceRef("persist_scene", "0.1.0"),
        ),
        context,
    )
    task_id = str(submitted.data["task_id"])
    assert confirm_task(app, task_id, context).ok

    handoff = handoff_task(app, task_id, context)
    run_id = str(handoff.data["run_id"])

    override = override_control(
        app,
        run_id,
        OverridePayload(command_type="emergency_stop", reason="persistent audit demo"),
        context,
    )
    assert override.ok
    repository.close()

    reopened = SQLiteQricsRepository(db_path, object_store=object_store)
    reopened_app = create_demo_app(repository=reopened)

    persisted_scene = get_scene(
        reopened_app,
        ResourceRef("persist_scene", "0.1.0"),
        context,
    )
    assert persisted_scene.ok
    assert persisted_scene.data["state"] == "baseline"
    assert persisted_scene.data["is_current_baseline"] is True

    replay = query_replay(reopened_app, ReplayQuery(run_id=run_id), context)
    assert replay.ok

    manifest_uri = replay.data["manifest_uri"]
    manifest_checksum = replay.data["manifest_checksum"]
    assert isinstance(manifest_uri, str)
    assert isinstance(manifest_checksum, str)
    assert manifest_uri
    assert manifest_checksum.startswith("sha256:")
    assert Path(manifest_uri).exists()

    events = reopened_app.list_events(context, run_id=run_id)
    assert len(events) >= 2
    assert {event.topic for event in events} >= {"control.status", "control.alert"}
    assert all(event.timestamp_ns > 0 for event in events)

    auditor = RequestContext(
        request_id="req-persist-audit",
        actor_id="auditor-1",
        role="auditor",
    )
    audit = query_audit(reopened_app, AuditQuery(action="control.emergency_stop"), auditor)
    assert audit.ok
    assert audit.data["count"] == 1

    records = audit.data["records"]
    assert isinstance(records, list)
    assert records
    record = records[0]
    assert isinstance(record, dict)
    assert record["request_id"] == "req-persist-1"
    assert isinstance(record["timestamp_ns"], int)
    assert record["timestamp_ns"] > 0

    reopened.close()
