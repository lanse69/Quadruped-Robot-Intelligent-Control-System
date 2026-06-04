"""Application-layer RBAC and high-risk operation policy for QRICS API.

This module intentionally does not implement production identity proofing,
JWT/OIDC parsing or an external user directory. It is the single source of
truth for the local API facade and HTTP adapter authorization semantics.

Transport-provided roles are normalized to a non-elevated ``operator`` role
when absent or unknown. That keeps demos resilient without granting training,
policy-release or audit-query privileges by mistake.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from qrics.api.schemas import ApiRole, GateDecision, OverrideType, RequestContext


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    permission: str
    message: str = ""


@dataclass(frozen=True)
class HighRiskOperation:
    action: str
    permission: str
    reason_required: bool = False
    audit_denied: bool = True


VALID_ROLES: Final[frozenset[ApiRole]] = frozenset(
    {"operator", "algorithm_engineer", "test_engineer", "admin", "auditor"}
)

_ROLE_BY_NAME: Final[dict[str, ApiRole]] = {
    "operator": "operator",
    "algorithm_engineer": "algorithm_engineer",
    "test_engineer": "test_engineer",
    "admin": "admin",
    "auditor": "auditor",
}

_PERMISSION_GROUPS: Final[dict[ApiRole, frozenset[str]]] = {
    "operator": frozenset(
        {
            "scene.read",
            "task.submit",
            "task.confirm",
            "task.handoff",
            "task.cancel",
            "control.read",
            "control.emergency_stop",
            "control.safe_stand",
            "control.manual_control",
            "control.pause",
            "control.resume",
            "replay.read",
            "events.read",
        }
    ),
    "algorithm_engineer": frozenset(
        {
            "scene.read",
            "task.submit",
            "task.confirm",
            "task.handoff",
            "control.read",
            "replay.read",
            "events.read",
            "training.submit",
            "training.read",
            "training.start",
            "training.checkpoint",
            "training.complete",
            "training.fail",
            "training.cancel",
            "evaluation.run",
            "evaluation.read",
            "policy.register",
            "policy.gate_report",
            "policy.release",
            "policy.promote_baseline",
        }
    ),
    "test_engineer": frozenset(
        {
            "scene.read",
            "scene.write",
            "scene.publish_baseline",
            "scene.archive",
            "task.submit",
            "task.confirm",
            "task.handoff",
            "task.cancel",
            "control.read",
            "control.emergency_stop",
            "control.safe_stand",
            "control.manual_control",
            "control.pause",
            "control.resume",
            "replay.read",
            "events.read",
            "training.read",
            "evaluation.run",
            "evaluation.read",
        }
    ),
    "auditor": frozenset(
        {
            "scene.read",
            "audit.read",
            "events.read",
            "replay.read",
            "control.read",
            "training.read",
            "evaluation.read",
        }
    ),
    "admin": frozenset({"*"}),
}

HIGH_RISK_OPERATIONS: Final[dict[str, HighRiskOperation]] = {
    "scene.publish_baseline": HighRiskOperation(
        action="scene.publish_baseline",
        permission="scene.publish_baseline",
        reason_required=True,
    ),
    "scene.archive": HighRiskOperation(
        action="scene.archive",
        permission="scene.archive",
        reason_required=True,
    ),
    "task.cancel": HighRiskOperation(
        action="task.cancel",
        permission="task.cancel",
        reason_required=True,
    ),
    "control.emergency_stop": HighRiskOperation(
        action="control.emergency_stop",
        permission="control.emergency_stop",
    ),
    "control.safe_stand": HighRiskOperation(
        action="control.safe_stand",
        permission="control.safe_stand",
    ),
    "control.manual_control": HighRiskOperation(
        action="control.manual_control",
        permission="control.manual_control",
        reason_required=True,
    ),
    "control.pause": HighRiskOperation(
        action="control.pause",
        permission="control.pause",
    ),
    "control.resume": HighRiskOperation(
        action="control.resume",
        permission="control.resume",
    ),
    "policy.gate_report": HighRiskOperation(
        action="policy.gate_report",
        permission="policy.gate_report",
        reason_required=True,
    ),
    "policy.release": HighRiskOperation(
        action="policy.release",
        permission="policy.release",
        reason_required=True,
    ),
    "policy.promote_baseline": HighRiskOperation(
        action="policy.promote_baseline",
        permission="policy.promote_baseline",
        reason_required=True,
    ),
    "training.fail": HighRiskOperation(
        action="training.fail",
        permission="training.fail",
        reason_required=True,
    ),
    "training.cancel": HighRiskOperation(
        action="training.cancel",
        permission="training.cancel",
        reason_required=True,
    ),
}

_OVERRIDE_ACTIONS: Final[dict[OverrideType, str]] = {
    "emergency_stop": "control.emergency_stop",
    "manual_control": "control.manual_control",
    "safe_stand": "control.safe_stand",
    "pause": "control.pause",
    "resume": "control.resume",
}

_OVERRIDE_BY_NAME: Final[dict[str, OverrideType]] = {
    "emergency_stop": "emergency_stop",
    "manual_control": "manual_control",
    "safe_stand": "safe_stand",
    "pause": "pause",
    "resume": "resume",
}

_GATE_DECISION_BY_NAME: Final[dict[str, GateDecision]] = {
    "passed": "passed",
    "failed": "failed",
}


def normalize_role(raw_role: str) -> ApiRole:
    """Normalize a transport-provided role without implicit privilege elevation."""

    role = raw_role.strip()
    if not role:
        return "operator"
    return _ROLE_BY_NAME.get(role, "operator")


def permissions_for_role(role: ApiRole) -> frozenset[str]:
    return _PERMISSION_GROUPS[role]


def authorize(context: RequestContext, permission: str) -> AuthorizationDecision:
    permissions = permissions_for_role(context.role)
    if "*" in permissions or permission in permissions:
        return AuthorizationDecision(allowed=True, permission=permission)
    return AuthorizationDecision(
        allowed=False,
        permission=permission,
        message=f"role={context.role} lacks permission={permission}",
    )


def high_risk_operation(action: str) -> HighRiskOperation | None:
    return HIGH_RISK_OPERATIONS.get(action)


def action_for_override(command_type: OverrideType) -> str:
    return _OVERRIDE_ACTIONS[command_type]


def override_type_from_string(value: str) -> OverrideType:
    normalized = value.strip()
    command = _OVERRIDE_BY_NAME.get(normalized)
    if command is None:
        raise ValueError(
            "command_type must be one of: "
            "emergency_stop, manual_control, pause, resume, safe_stand"
        )
    return command


def gate_decision_from_string(value: str) -> GateDecision:
    normalized = value.strip()
    decision = _GATE_DECISION_BY_NAME.get(normalized)
    if decision is None:
        raise ValueError("decision must be one of: failed, passed")
    return decision
