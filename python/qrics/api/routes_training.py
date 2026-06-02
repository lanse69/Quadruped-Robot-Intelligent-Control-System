"""Training API route facade functions."""

from __future__ import annotations

from qrics.api.app import QricsApiApp
from qrics.api.schemas import ApiResponse, RequestContext, TrainingPlanPayload


def submit_training_plan(
    app: QricsApiApp,
    payload: TrainingPlanPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.submit_training_plan(payload, context)
