"""Application-layer RBAC and high-risk operation policy for QRICS API.

The module does not implement identity proofing, token parsing or external
user directories.  It defines stable authorization semantics shared by the
facade and HTTP adapter so that all routes use the same default-deny policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from qrics.api.schemas import OverrideType, RequestContext


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


_PERMISSION_GROUPS: Final[dict[str, frozenset[str]]] = {
    "operator": frozenset(
        {
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
            "task.submit",
            "task.confirm",
            "task.handoff",
            "control.read",
            "replay.read",
            "events.read",
            "training.submit",
            "policy.register",
            "policy.gate_report",
            "policy.release",
            "policy.promote_baseline",
        }
    ),
    "test_engineer": frozenset(
        {
            "task.submit",
            "task.confirm",
            "task.handoff",
            "control.read",
            "control.emergency_stop",
            "control.safe_stand",
            "replay.read",
            "events.read",
        }
    ),
    "auditor": frozenset(
        {
            "audit.read",
            "events.read",
            "replay.read",
        }
    ),
    "admin": frozenset({"*"}),
}

HIGH_RISK_OPERATIONS: Final[dict[str, HighRiskOperation]] = {
    "task.cancel": HighRiskOperation(
        action="task.cancel",
        permission="task.cancel",
        reason_required=True,
    ),
    "control.emergency_stop": HighRiskOperation(
        action="control.emergency_stop",
        permission="control.emergency_stop",
        reason_required=False,
    ),
    "control.safe_stand": HighRiskOperation(
        action="control.safe_stand",
        permission="control.safe_stand",
        reason_required=False,
    ),
    "control.manual_control": HighRiskOperation(
        action="control.manual_control",
        permission="control.manual_control",
        reason_required=True,
    ),
    "control.pause": HighRiskOperation(
        action="control.pause",
        permission="control.pause",
        reason_required=True,
    ),
    "control.resume": HighRiskOperation(
        action="control.resume",
        permission="control.resume",
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
}

_OVERRIDE_ACTIONS: Final[dict[OverrideType, str]] = {
    "emergency_stop": "control.emergency_stop",
    "manual_control": "control.manual_control",
    "safe_stand": "control.safe_stand",
    "pause": "control.pause",
    "resume": "control.resume",
}


def permissions_for_role(role: str) -> frozenset[str]:
    return _PERMISSION_GROUPS.get(role, frozenset())


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
