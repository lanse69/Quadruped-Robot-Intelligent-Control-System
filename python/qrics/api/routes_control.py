"""Control API route facade functions."""

from __future__ import annotations

from qrics.api.app import QricsApiApp
from qrics.api.schemas import ApiResponse, OverridePayload, RequestContext


def get_control_status(app: QricsApiApp, run_id: str, context: RequestContext) -> ApiResponse:
    return app.get_control_status(run_id, context)


def override_control(
    app: QricsApiApp,
    run_id: str,
    payload: OverridePayload,
    context: RequestContext,
) -> ApiResponse:
    return app.override_control(run_id, payload, context)
