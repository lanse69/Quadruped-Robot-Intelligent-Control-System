from typing import cast

from qrics.api.app import create_demo_app
from qrics.api.routes_audit import query_audit
from qrics.api.routes_control import override_control
from qrics.api.routes_policies import (
    attach_gate_report,
    promote_policy_baseline,
    register_policy,
    release_policy,
)
from qrics.api.routes_tasks import confirm_task, handoff_task, submit_task
from qrics.api.routes_training import submit_training_plan
from qrics.api.schemas import (
    AuditQuery,
    GateReportPayload,
    MetricSummaryPayload,
    OverridePayload,
    PolicyRegistrationPayload,
    RequestContext,
    ResourceRef,
    TaskSubmissionPayload,
    TrainingPlanPayload,
)


def _ctx(role: str, actor_id: str = "actor-1") -> RequestContext:
    return RequestContext(
        request_id=f"req-{role}",
        actor_id=actor_id,
        role=role,  # type: ignore[arg-type]
    )


def test_training_plan_requires_algorithm_engineer_or_admin() -> None:
    app = create_demo_app()
    payload = TrainingPlanPayload(
        training_id="train-sec",
        scene_ref=ResourceRef("minimal_scene", "0.1.0"),
    )

    denied = submit_training_plan(app, payload, _ctx("operator"))
    assert not denied.ok
    assert denied.errors[0].code == "FORBIDDEN"

    allowed = submit_training_plan(app, payload, _ctx("algorithm_engineer", "algo-1"))
    assert allowed.ok
    assert allowed.data["state"] == "queued"


def test_audit_query_requires_auditor_or_admin() -> None:
    app = create_demo_app()

    denied = query_audit(app, AuditQuery(), _ctx("operator"))
    assert not denied.ok
    assert denied.errors[0].code == "FORBIDDEN"

    allowed = query_audit(app, AuditQuery(), _ctx("auditor", "audit-1"))
    assert allowed.ok
    assert allowed.data["count"] == 1


def test_policy_release_denial_and_gate_conflict_are_audited() -> None:
    app = create_demo_app()
    engineer = _ctx("algorithm_engineer", "algo-1")
    operator = _ctx("operator", "operator-1")
    auditor = _ctx("auditor", "audit-1")
    policy_ref = ResourceRef("flat_nav", "1.0.0")

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

    denied_by_role = release_policy(app, policy_ref, operator, reason="operator release attempt")
    assert not denied_by_role.ok
    assert denied_by_role.errors[0].code == "FORBIDDEN"

    denied_by_reason = release_policy(app, policy_ref, engineer, reason="")
    assert not denied_by_reason.ok
    assert denied_by_reason.errors[0].code == "INVALID_REQUEST"

    denied_by_gate = release_policy(app, policy_ref, engineer, reason="release before gate")
    assert not denied_by_gate.ok
    assert denied_by_gate.errors[0].code == "STATE_CONFLICT"

    audit = query_audit(app, AuditQuery(action="policy.release"), auditor)
    assert audit.ok
    assert audit.data["count"] == 3
    records = cast(list[dict[str, str]], audit.data["records"])
    assert {record["result"] for record in records} == {"denied", "rejected"}


def test_policy_lifecycle_success_writes_gate_release_and_baseline_audit() -> None:
    app = create_demo_app()
    engineer = _ctx("algorithm_engineer", "algo-1")
    auditor = _ctx("auditor", "audit-1")
    policy_ref = ResourceRef("flat_nav", "1.0.1")

    assert register_policy(
        app,
        PolicyRegistrationPayload(
            policy_ref=policy_ref,
            artifact_uri="artifact://policies/flat_nav/1.0.1/model.pt",
            metrics=MetricSummaryPayload(
                success_rate=0.97,
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
        GateReportPayload(policy_ref=policy_ref, decision="passed", reason="meets gate"),
        engineer,
    ).ok
    assert release_policy(app, policy_ref, engineer, reason="release approved").ok
    assert promote_policy_baseline(app, policy_ref, engineer, reason="baseline approved").ok

    audit = query_audit(app, AuditQuery(actor_id="algo-1"), auditor)
    assert audit.ok
    records = cast(list[dict[str, str]], audit.data["records"])
    assert {record["action"] for record in records} >= {
        "policy.gate_report",
        "policy.release",
        "policy.promote_baseline",
    }


def test_manual_control_requires_reason_but_emergency_stop_does_not() -> None:
    app = create_demo_app()
    operator = _ctx("operator", "operator-1")
    auditor = _ctx("auditor", "audit-1")

    task = submit_task(app, TaskSubmissionPayload(source_text="巡检A"), operator)
    task_id = str(task.data["task_id"])
    assert confirm_task(app, task_id, operator).ok
    handoff = handoff_task(app, task_id, operator)
    run_id = str(handoff.data["run_id"])

    manual_without_reason = override_control(
        app,
        run_id,
        OverridePayload(command_type="manual_control", reason=""),
        operator,
    )
    assert not manual_without_reason.ok
    assert manual_without_reason.errors[0].code == "INVALID_REQUEST"

    emergency_without_reason = override_control(
        app,
        run_id,
        OverridePayload(command_type="emergency_stop", reason=""),
        operator,
    )
    assert emergency_without_reason.ok

    audit = query_audit(app, AuditQuery(actor_id="operator-1"), auditor)
    assert audit.ok
    records = cast(list[dict[str, str]], audit.data["records"])
    assert {record["action"] for record in records} >= {
        "control.manual_control",
        "control.emergency_stop",
    }
