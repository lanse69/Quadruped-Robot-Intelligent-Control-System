from qrics.api.app import create_demo_app
from qrics.api.routes_audit import query_audit
from qrics.api.routes_control import get_control_status, override_control
from qrics.api.routes_policies import (
    attach_gate_report,
    promote_policy_baseline,
    register_policy,
    release_policy,
)
from qrics.api.routes_replay import query_replay
from qrics.api.routes_tasks import confirm_task, handoff_task, submit_task
from qrics.api.routes_training import submit_training_plan
from qrics.api.schemas import (
    AuditQuery,
    GateReportPayload,
    MetricSummaryPayload,
    OverridePayload,
    PolicyRegistrationPayload,
    ReplayQuery,
    RequestContext,
    ResourceRef,
    TaskSubmissionPayload,
    TrainingPlanPayload,
)


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

    audit = query_audit(app, AuditQuery(action="control.emergency_stop"), context)
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

    gate = attach_gate_report(
        app,
        GateReportPayload(
            policy_ref=policy_ref,
            decision="passed",
            reason="meets baseline gate",
        ),
        engineer,
    )
    assert gate.ok
    assert gate.data["stage"] == "gate_passed"

    release = release_policy(app, policy_ref, engineer, reason="答辩演示发布")
    assert release.ok
    assert release.data["stage"] == "released"

    baseline = promote_policy_baseline(app, policy_ref, engineer, reason="作为当前演示基线")
    assert baseline.ok
    assert baseline.data["stage"] == "baseline"
    assert baseline.data["is_current_baseline"] is True

    audit = query_audit(app, AuditQuery(actor_id="algo-1"), engineer)
    assert audit.ok
    assert audit.data["count"] == 2
