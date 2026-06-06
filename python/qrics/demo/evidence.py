"""Generate local QRICS demonstration evidence bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qrics.api import create_demo_app
from qrics.api.routes_audit import query_audit
from qrics.api.routes_control import override_control
from qrics.api.routes_replay import query_replay
from qrics.api.routes_scenes import create_scene
from qrics.api.routes_tasks import confirm_task, handoff_task, submit_task
from qrics.api.schemas import (
    AuditQuery,
    OverridePayload,
    ReplayQuery,
    RequestContext,
    ResourceRef,
    SceneAssetPayload,
    SceneCreatePayload,
    SimulationBackend,
    TaskSubmissionPayload,
)
from qrics.api.simulation_runner import LocalSimulationRunner
from qrics.sim.scene_loader import load_scene_profile_from_json


@dataclass(frozen=True)
class EvidenceBundleResult:
    output_dir: Path
    evidence_json: Path
    evidence_markdown: Path

    def to_json(self) -> dict[str, str]:
        return {
            "output_dir": str(self.output_dir),
            "evidence_json": str(self.evidence_json),
            "evidence_markdown": str(self.evidence_markdown),
        }


def generate_evidence_bundle(
    *,
    output_dir: str | Path,
    backend: SimulationBackend = "minimal",
    runtime_profile: str = "headless_fast",
    task_text: str = "避开障碍，巡检A后回到平台待命",
    scene_json: str | Path | None = None,
    webots_execute: bool = False,
    trigger_emergency_stop: bool = True,
) -> EvidenceBundleResult:
    """Run a bounded local demo and persist audit/replay/status evidence."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    app = create_demo_app()
    app.simulation_runner = LocalSimulationRunner(webots_execute=webots_execute)
    app.default_sim_backend = backend
    app.default_runtime_profile = runtime_profile

    operator = RequestContext("demo-operator", "operator-demo", "operator")
    test_engineer = RequestContext("demo-scene", "test-demo", "test_engineer")
    scene_ref = _create_demo_scene(app, test_engineer, scene_json)

    submitted = submit_task(
        app,
        TaskSubmissionPayload(source_text=task_text, scene_ref=scene_ref),
        operator,
    )
    _ensure_ok(submitted.data, submitted.ok, "submit_task")
    task_id = str(submitted.data["task_id"])

    confirmed = confirm_task(app, task_id, operator)
    _ensure_ok(confirmed.data, confirmed.ok, "confirm_task")

    handoff = handoff_task(app, task_id, operator)
    _ensure_ok(handoff.data, handoff.ok, "handoff_task")
    run_id = str(handoff.data["run_id"])

    override_payload: dict[str, Any] = {}
    if trigger_emergency_stop:
        override = override_control(
            app,
            run_id,
            OverridePayload(command_type="emergency_stop", reason="答辩证据包急停演示"),
            operator,
        )
        _ensure_ok(override.data, override.ok, "override_control")
        override_payload = dict(override.data)

    replay = query_replay(app, ReplayQuery(run_id=run_id), operator)
    _ensure_ok(replay.data, replay.ok, "query_replay")
    audit = query_audit(
        app, AuditQuery(object_id=run_id), RequestContext("demo-audit", "auditor-demo", "auditor")
    )
    _ensure_ok(audit.data, audit.ok, "query_audit")

    events = [event.to_json() for event in app.list_events(operator, run_id=run_id)]
    payload: dict[str, Any] = {
        "schema": "qrics.demo_evidence.v1",
        "backend": backend,
        "runtime_profile": runtime_profile,
        "scene_ref": {"id": scene_ref.id, "version": scene_ref.version},
        "task_text": task_text,
        "task": submitted.data,
        "handoff": handoff.data,
        "override": override_payload,
        "replay": replay.data,
        "audit": audit.data,
        "events": events,
    }
    json_path = out / "qrics_demo_evidence.json"
    md_path = out / "qrics_demo_evidence.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return EvidenceBundleResult(out, json_path, md_path)


def _create_demo_scene(
    app: Any,
    context: RequestContext,
    scene_json: str | Path | None,
) -> ResourceRef:
    if scene_json:
        sim_scene = load_scene_profile_from_json(scene_json)
        scene_ref = ResourceRef(sim_scene.scene_id, sim_scene.version)
        assets = tuple(
            SceneAssetPayload(
                asset_id=obstacle.obstacle_id,
                asset_type="obstacle",
                geometry_type=obstacle.geometry_type,
                position=(obstacle.position.x, obstacle.position.y, obstacle.position.z),
                radius_m=obstacle.radius_m,
                height_m=obstacle.height_m,
                size=(obstacle.size.x, obstacle.size.y, obstacle.size.z),
            )
            for obstacle in sim_scene.obstacle_set
        )
        payload = SceneCreatePayload(
            scene_id=scene_ref.id,
            version=scene_ref.version,
            name=sim_scene.name,
            terrain_pack=sim_scene.terrain_pack,
            assets=assets,
            change_summary="demo evidence scene loaded from JSON",
        )
    else:
        scene_ref = ResourceRef("demo_evidence_scene", "0.4.0")
        payload = SceneCreatePayload(
            scene_id=scene_ref.id,
            version=scene_ref.version,
            name="QRICS Demo Evidence Scene",
            terrain_pack="mixed_terrain_pack",
            assets=(
                SceneAssetPayload(
                    asset_id="demo_box",
                    asset_type="obstacle",
                    geometry_type="box",
                    position=(0.18, 0.0, 0.35),
                    size=(0.18, 0.16, 0.28),
                    radius_m=0.09,
                    height_m=0.28,
                ),
                SceneAssetPayload(
                    asset_id="demo_sphere",
                    asset_type="obstacle",
                    geometry_type="sphere",
                    position=(0.70, 0.18, 0.30),
                    radius_m=0.09,
                    height_m=0.18,
                ),
            ),
            change_summary="default demo evidence scene",
        )
    created = create_scene(app, payload, context)
    _ensure_ok(created.data, created.ok, "create_scene")
    return scene_ref


def _ensure_ok(data: object, ok: bool, stage: str) -> None:
    if not ok:
        raise RuntimeError(f"{stage} failed: {data}")


def _render_markdown(payload: dict[str, Any]) -> str:
    handoff = payload["handoff"]
    replay = payload["replay"]
    audit = payload["audit"]
    events = payload["events"]
    return (
        "# QRICS 本机演示证据包\n\n"
        f"- Backend: `{payload['backend']}`\n"
        f"- Runtime profile: `{payload['runtime_profile']}`\n"
        f"- Scene: `{payload['scene_ref']['id']}:{payload['scene_ref']['version']}`\n"
        f"- Task: {payload['task_text']}\n"
        f"- Run ID: `{handoff.get('run_id', '')}`\n"
        f"- State: `{handoff.get('state', '')}`\n"
        f"- Latest action: `{handoff.get('latest_action', '')}`\n"
        f"- Control steps: {handoff.get('control_step_count', 0)}\n"
        f"- Sim time ns: {handoff.get('sim_time_ns', 0)}\n"
        f"- Base position: `{handoff.get('base_position', [])}`\n"
        f"- Terrain: `{handoff.get('terrain_class', '')}`\n"
        f"- Obstacle detected: `{handoff.get('obstacle_detected', False)}`\n"
        f"- Safety event count: {handoff.get('safety_event_count', 0)}\n"
        f"- Replay keyframes: {replay.get('keyframe_count', 0)}\n"
        f"- Replay manifest: `{replay.get('manifest_uri', '')}`\n"
        f"- Audit records: {audit.get('count', 0)}\n"
        f"- Event snapshots: {len(events)}\n\n"
        "## 安全事件\n\n"
        + "\n".join(f"- {event}" for event in replay.get("safety_events", []))
        + "\n"
    )
