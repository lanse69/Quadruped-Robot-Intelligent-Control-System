import pytest

from qrics.api.schemas import RequestContext
from qrics.api.security import (
    action_for_override,
    authorize,
    gate_decision_from_string,
    high_risk_operation,
    normalize_role,
    override_type_from_string,
    permissions_for_role,
)


def test_normalize_role_defaults_to_operator_without_elevation() -> None:
    assert normalize_role("") == "operator"
    assert normalize_role("unknown") == "operator"
    assert normalize_role("admin") == "admin"


def test_operator_permissions_do_not_include_training_or_audit_query() -> None:
    permissions = permissions_for_role("operator")
    assert "task.submit" in permissions
    assert "control.emergency_stop" in permissions
    assert "training.submit" not in permissions
    assert "audit.read" not in permissions


def test_admin_wildcard_authorizes_every_known_application_permission() -> None:
    context = RequestContext(request_id="req-admin", actor_id="admin-1", role="admin")
    assert authorize(context, "training.submit").allowed
    assert authorize(context, "audit.read").allowed
    assert authorize(context, "policy.release").allowed


def test_operator_training_authorization_is_denied() -> None:
    context = RequestContext(request_id="req-op", actor_id="operator-1", role="operator")
    decision = authorize(context, "training.submit")
    assert not decision.allowed
    assert decision.permission == "training.submit"
    assert "operator" in decision.message


def test_high_risk_reason_policy_matches_safety_and_governance_rules() -> None:
    emergency = high_risk_operation("control.emergency_stop")
    manual = high_risk_operation("control.manual_control")
    pause = high_risk_operation("control.pause")
    resume = high_risk_operation("control.resume")
    release = high_risk_operation("policy.release")

    assert emergency is not None
    assert not emergency.reason_required
    assert manual is not None
    assert manual.reason_required
    assert pause is not None
    assert not pause.reason_required
    assert resume is not None
    assert not resume.reason_required
    assert release is not None
    assert release.reason_required


def test_override_action_mapping_and_runtime_validation() -> None:
    assert override_type_from_string("emergency_stop") == "emergency_stop"
    assert action_for_override("emergency_stop") == "control.emergency_stop"
    assert action_for_override("manual_control") == "control.manual_control"

    with pytest.raises(ValueError):
        override_type_from_string("shutdown")


def test_gate_decision_runtime_validation() -> None:
    assert gate_decision_from_string("passed") == "passed"
    assert gate_decision_from_string("failed") == "failed"

    with pytest.raises(ValueError):
        gate_decision_from_string("approved")
