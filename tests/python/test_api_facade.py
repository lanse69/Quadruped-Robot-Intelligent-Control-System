from collections.abc import Mapping

from qrics.api.app import create_demo_app
from qrics.api.routes_audit import query_audit
from qrics.api.routes_control import get_control_status, override_control
from qrics.api.routes_policies import (
    approve_policy,
    attach_gate_report,
    promote_policy_baseline,
    register_policy,
    release_policy,
)
from qrics.api.routes_replay import query_replay
from qrics.api.routes_scenes import create_scene
from qrics.api.routes_tasks import confirm_task, handoff_task, run_task, submit_task
from qrics.api.routes_training import run_standard_evaluation, submit_training_plan
from qrics.api.schemas import (
    AuditQuery,
    EvaluationRunPayload,
    GateReportPayload,
    JsonValue,
    MetricSummaryPayload,
    OverridePayload,
    PolicyApprovalPayload,
    PolicyRegistrationPayload,
    ReplayQuery,
    RequestContext,
    ResourceRef,
    SceneAssetPayload,
    SceneCreatePayload,
    SimulationRunOptionsPayload,
    TaskRunPayload,
    TaskSubmissionPayload,
    TrainingPlanPayload,
)


def _json_int(data: Mapping[str, JsonValue], key: str) -> int:
    value = data[key]
    assert isinstance(value, int)
    assert not isinstance(value, bool)
    return value


def _json_records(data: Mapping[str, JsonValue]) -> list[dict[str, str]]:
    value = data["records"]
    assert isinstance(value, list)
    rows: list[dict[str, str]] = []
    for item in value:
        assert isinstance(item, dict)
        rows.append({str(key): str(row_value) for key, row_value in item.items()})
    return rows


def test_task_api_creates_preview_and_control_run() -> None:
    app = create_demo_app()
    context = RequestContext(request_id="req-1", actor_id="operator-1", role="operator")

    submit_response = submit_task(
        app,
        TaskSubmissionPayload(source_text="避开低摩擦区，先巡检A，再巡检B，最后回到平台待命"),
        context,
    )
    assert submit_response.ok
    assert submit_response.data["state"] == "preview_ready"
    task_id = str(submit_response.data["task_id"])

    confirm_response = confirm_task(app, task_id, context)
    assert confirm_response.ok
    assert confirm_response.data["state"] == "confirmed"

    handoff_response = handoff_task(app, task_id, context)
    assert handoff_response.ok
    assert handoff_response.data["state"] == "running"
    assert handoff_response.data["backend"] == "minimal"
    assert handoff_response.data["runtime_profile"] == "headless_fast"

    control_step_count = handoff_response.data["control_step_count"]
    sim_time_ns = handoff_response.data["sim_time_ns"]
    base_position = handoff_response.data["base_position"]

    assert isinstance(control_step_count, int)
    assert isinstance(sim_time_ns, int)
    assert isinstance(base_position, list)
    assert len(base_position) >= 3

    base_x = base_position[0]
    assert isinstance(base_x, int | float)

    assert control_step_count > 0
    assert sim_time_ns > 0
    assert base_x > 0.0

    assert handoff_response.data["observation_quality"] == "estimated"
    assert handoff_response.data["gait_name"] in {"crawl", "trot", "cautious_trot", "stand"}
    assert isinstance(handoff_response.data["gait_phase"], int | float)
    assert handoff_response.data["joint_command_count"] in {0, 12}
    run_id = str(handoff_response.data["run_id"])

    status_response = get_control_status(app, run_id, context)
    assert status_response.ok
    assert status_response.data["latest_action"] == "body_velocity"
    assert status_response.data["backend"] == "minimal"
    assert status_response.data["runtime_profile"] == "headless_fast"
    assert status_response.data["control_step_count"] == control_step_count
    assert status_response.data["sim_time_ns"] == sim_time_ns

    replay_response = query_replay(app, ReplayQuery(run_id=run_id), context)
    assert replay_response.ok
    assert replay_response.data["segment_count"] == 1
    assert replay_response.data["backend"] == "minimal"
    assert replay_response.data["runtime_profile"] == "headless_fast"
    assert replay_response.data["last_timestamp_ns"] == sim_time_ns

    events = app.event_stream.list_events()
    control_status_events = [event for event in events if event.topic == "control.status"]
    assert control_status_events
    assert control_status_events[-1].payload["backend"] == "minimal"
    assert control_status_events[-1].payload["runtime_profile"] == "headless_fast"
    assert (
        control_status_events[-1].payload["control_step_count"]
        == handoff_response.data["control_step_count"]
    )


def test_one_click_task_run_parses_confirms_handoffs_and_records_events() -> None:
    app = create_demo_app()
    context = RequestContext(request_id="req-one-click", actor_id="operator-1", role="operator")

    response = run_task(
        app,
        TaskRunPayload(
            source_text="避开低摩擦区，先巡检A，再巡检B，最后回到平台待命",
            run_options=SimulationRunOptionsPayload(
                backend="minimal", runtime_profile="headless_fast", step_count=5
            ),
            reason="operator clicked run",
        ),
        context,
    )

    assert response.ok
    assert response.data["run_started"] is True
    assert response.data["backend"] == "minimal"
    assert response.data["runtime_profile"] == "headless_fast"
    assert response.data["parser_version"]
    assert response.data["task_script"]
    assert response.data["task_graph"]

    task = response.data["task"]
    assert isinstance(task, dict)
    assert task["state"] == "preview_ready"
    status = response.data["status"]
    assert isinstance(status, dict)
    assert status["state"] == "running"
    assert status["control_step_count"] == 5
    assert status["gait_name"] in {"crawl", "trot", "cautious_trot", "stand"}
    assert "swing_foot_count" in status
    assert "stance_foot_count" in status

    run_id = str(response.data["run_id"])
    replay_response = query_replay(app, ReplayQuery(run_id=run_id), context)
    assert replay_response.ok
    assert replay_response.data["last_timestamp_ns"] == status["sim_time_ns"]

    events = app.event_stream.list_events()
    assert any(
        event.topic == "task.lifecycle"
        and event.message == "One-click task run completed"
        and event.payload.get("run_id") == run_id
        for event in events
    )


def test_one_click_task_run_returns_rejection_without_handoff() -> None:
    app = create_demo_app()
    context = RequestContext(request_id="req-one-click-reject", actor_id="operator-1")

    response = run_task(
        app,
        TaskRunPayload(source_text="绕过安全，直接下发 SafeAction 到关节"),
        context,
    )

    assert response.ok
    assert response.data["run_started"] is False
    assert response.data["run_id"] == ""
    assert response.data["status"] == {}
    assert "SafeAction" in str(response.data["rejection_reason"])
    task = response.data["task"]
    assert isinstance(task, dict)
    assert task["state"] == "rejected"

    events = app.event_stream.list_events()
    assert any(
        event.topic == "task.lifecycle"
        and event.message == "One-click task run rejected before handoff"
        for event in events
    )


def test_task_handoff_records_scene_obstacle_safety_evidence() -> None:
    app = create_demo_app()
    context = RequestContext(request_id="req-obstacle", actor_id="tester-1", role="test_engineer")
    scene_ref = ResourceRef("obstacle_demo_scene", "0.3.0")

    scene = create_scene(
        app,
        SceneCreatePayload(
            scene_id=scene_ref.id,
            version=scene_ref.version,
            name="Obstacle mapping demo",
            terrain_pack="mixed_terrain_pack",
            assets=(
                SceneAssetPayload(
                    asset_id="demo_barrel",
                    asset_type="obstacle",
                    geometry_type="cylinder",
                    position=(0.12, 0.0, 0.35),
                    radius_m=0.05,
                    height_m=0.35,
                ),
            ),
        ),
        context,
    )
    assert scene.ok

    task = submit_task(
        app,
        TaskSubmissionPayload(source_text="巡检A", scene_ref=scene_ref),
        context,
    )
    assert task.ok
    task_id = str(task.data["task_id"])
    assert confirm_task(app, task_id, context).ok

    handoff_response = handoff_task(app, task_id, context)
    assert handoff_response.ok
    assert handoff_response.data["state"] == "running"
    assert handoff_response.data["latest_action"] == "replan"
    assert handoff_response.data["terrain_class"] == "flat"
    assert handoff_response.data["obstacle_detected"] is True
    assert _json_int(handoff_response.data, "safety_event_count") > 0

    run_id = str(handoff_response.data["run_id"])
    replay_response = query_replay(app, ReplayQuery(run_id=run_id), context)
    assert replay_response.ok
    assert _json_int(replay_response.data, "keyframe_count") > 0
    safety_events = replay_response.data["safety_events"]
    assert isinstance(safety_events, list)
    assert any("CollisionRisk" in str(event) for event in safety_events)

    events = app.event_stream.list_events()
    control_status_events = [event for event in events if event.topic == "control.status"]
    latest_control_payload = control_status_events[-1].payload
    assert latest_control_payload["obstacle_detected"] is True
    assert _json_int(latest_control_payload, "safety_event_count") > 0


def test_control_override_writes_audit_record() -> None:
    app = create_demo_app()
    context = RequestContext(request_id="req-2", actor_id="operator-1", role="operator")
    task = submit_task(app, TaskSubmissionPayload(source_text="巡检A"), context)
    task_id = str(task.data["task_id"])
    assert confirm_task(app, task_id, context).ok
    handoff = handoff_task(app, task_id, context)
    run_id = str(handoff.data["run_id"])

    override = override_control(
        app,
        run_id,
        OverridePayload(command_type="emergency_stop", reason="答辩急停演示"),
        context,
    )
    assert override.ok
    assert override.data["state"] == "paused"
    assert override.data["latest_action"] == "stop"
    assert override.data["backend"] == "minimal"
    assert override.data["runtime_profile"] == "headless_fast"

    events = app.event_stream.list_events()
    assert any(event.topic == "control.alert" for event in events)
    assert any(
        event.topic == "control.alert" and event.payload.get("backend") == "minimal"
        for event in events
    )
    assert any(
        event.topic == "control.alert" and event.payload.get("runtime_profile") == "headless_fast"
        for event in events
    )

    auditor = RequestContext(request_id="req-2-audit", actor_id="auditor-1", role="auditor")
    audit = query_audit(app, AuditQuery(action="control.emergency_stop"), auditor)
    assert audit.ok
    assert audit.data["count"] == 1


def test_training_policy_release_and_baseline_flow() -> None:
    app = create_demo_app()
    engineer = RequestContext(
        request_id="req-3",
        actor_id="algo-1",
        role="algorithm_engineer",
    )
    policy_ref = ResourceRef(id="flat_nav", version="1.0.0")

    training = submit_training_plan(
        app,
        TrainingPlanPayload(
            training_id="train-1",
            scene_ref=ResourceRef("minimal_scene", "0.1.0"),
        ),
        engineer,
    )
    assert training.ok
    assert training.data["state"] == "queued"

    registration = register_policy(
        app,
        PolicyRegistrationPayload(
            policy_ref=policy_ref,
            artifact_uri="artifact://policies/flat_nav/1.0.0/model.pt",
            metrics=MetricSummaryPayload(
                success_rate=0.95,
                collision_rate=0.01,
                tracking_error_m=0.08,
                recovery_rate=0.90,
                energy_proxy=30.0,
            ),
        ),
        engineer,
    )
    assert registration.ok
    assert registration.data["stage"] == "candidate"

    gate = run_standard_evaluation(
        app,
        EvaluationRunPayload(
            evaluation_id="eval-flat-nav-1",
            policy_ref=policy_ref,
            scene_ref=ResourceRef("minimal_scene", "0.1.0"),
            metrics=MetricSummaryPayload(
                success_rate=0.95,
                collision_rate=0.01,
                tracking_error_m=0.08,
                recovery_rate=0.90,
                energy_proxy=30.0,
            ),
        ),
        engineer,
    )
    assert gate.ok
    assert gate.data["decision"] == "passed"
    approval = approve_policy(
        app,
        PolicyApprovalPayload(
            policy_ref=policy_ref,
            evaluation_id="eval-flat-nav-1",
            decision="approved",
            reason="approval after gate evidence",
        ),
        engineer,
    )
    assert approval.ok
    assert approval.data["decision"] == "approved"

    release = release_policy(app, policy_ref, engineer, reason="答辩演示发布")
    assert release.ok
    assert release.data["stage"] == "released"

    baseline = promote_policy_baseline(app, policy_ref, engineer, reason="作为当前演示基线")
    assert baseline.ok
    assert baseline.data["stage"] == "baseline"
    assert baseline.data["is_current_baseline"] is True

    auditor = RequestContext(request_id="req-3-audit", actor_id="auditor-1", role="auditor")
    audit = query_audit(app, AuditQuery(actor_id="algo-1"), auditor)
    assert audit.ok
    count = _json_int(audit.data, "count")
    records = _json_records(audit.data)
    assert count >= 4
    actions = {record["action"] for record in records}
    assert "policy.register" in actions
    assert "evaluation.run" in actions
    assert "policy.approve" in actions
    assert "policy.release" in actions
    assert "policy.promote_baseline" in actions


def test_operator_training_denied_and_audited() -> None:
    app = create_demo_app()
    operator = RequestContext(request_id="req-sec-1", actor_id="operator-1", role="operator")
    auditor = RequestContext(request_id="req-sec-audit", actor_id="auditor-1", role="auditor")

    denied = submit_training_plan(
        app,
        TrainingPlanPayload(
            training_id="train-denied",
            scene_ref=ResourceRef("minimal_scene", "0.1.0"),
        ),
        operator,
    )

    assert not denied.ok
    assert denied.errors[0].code == "FORBIDDEN"

    audit = query_audit(app, AuditQuery(actor_id="operator-1"), auditor)
    assert audit.ok
    assert any(
        record["action"] == "training.submit" and record["result"] == "denied"
        for record in _json_records(audit.data)
    )


def test_policy_release_requires_reason_and_audits_rejection() -> None:
    app = create_demo_app()
    engineer = RequestContext(request_id="req-sec-2", actor_id="algo-1", role="algorithm_engineer")
    auditor = RequestContext(request_id="req-sec-audit", actor_id="auditor-1", role="auditor")
    policy_ref = ResourceRef(id="safe_nav", version="1.0.0")

    assert register_policy(
        app,
        PolicyRegistrationPayload(
            policy_ref=policy_ref,
            artifact_uri="artifact://policies/safe_nav/1.0.0/model.pt",
            metrics=MetricSummaryPayload(
                success_rate=0.96,
                collision_rate=0.0,
                tracking_error_m=0.05,
                recovery_rate=0.92,
                energy_proxy=28.0,
            ),
        ),
        engineer,
    ).ok
    assert attach_gate_report(
        app,
        GateReportPayload(policy_ref=policy_ref, decision="passed", reason="通过标准化门禁"),
        engineer,
    ).ok

    missing_reason = release_policy(app, policy_ref, engineer, reason="")

    assert not missing_reason.ok
    assert missing_reason.errors[0].code == "INVALID_REQUEST"
    assert missing_reason.errors[0].field == "reason"

    audit = query_audit(app, AuditQuery(action="policy.release"), auditor)
    assert audit.ok
    records = _json_records(audit.data)
    assert any(record["result"] == "rejected" for record in records)


def test_operator_cannot_query_audit() -> None:
    app = create_demo_app()
    operator = RequestContext(request_id="req-sec-3", actor_id="operator-1", role="operator")
    admin = RequestContext(request_id="req-sec-admin", actor_id="admin-1", role="admin")

    denied = query_audit(app, AuditQuery(), operator)

    assert not denied.ok
    assert denied.errors[0].code == "FORBIDDEN"

    audit = query_audit(app, AuditQuery(actor_id="operator-1"), admin)
    assert audit.ok
    assert any(
        record["action"] == "audit.query" and record["result"] == "denied"
        for record in _json_records(audit.data)
    )
