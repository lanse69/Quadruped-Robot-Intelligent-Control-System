"""Policy API route facade functions."""

from __future__ import annotations

from qrics.api.app import QricsApiApp
from qrics.api.schemas import (
    ApiResponse,
    GateReportPayload,
    PolicyRegistrationPayload,
    RequestContext,
    ResourceRef,
)


def register_policy(
    app: QricsApiApp,
    payload: PolicyRegistrationPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.register_policy(payload, context)


def attach_gate_report(
    app: QricsApiApp,
    payload: GateReportPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.attach_gate_report(payload, context)


def release_policy(
    app: QricsApiApp,
    policy_ref: ResourceRef,
    context: RequestContext,
    reason: str,
) -> ApiResponse:
    return app.release_policy(policy_ref, context, reason)


def promote_policy_baseline(
    app: QricsApiApp,
    policy_ref: ResourceRef,
    context: RequestContext,
    reason: str,
) -> ApiResponse:
    return app.promote_policy_baseline(policy_ref, context, reason)
