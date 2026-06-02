"""Task API route facade functions."""

from __future__ import annotations

from qrics.api.app import QricsApiApp
from qrics.api.schemas import ApiResponse, RequestContext, TaskSubmissionPayload


def submit_task(
    app: QricsApiApp,
    payload: TaskSubmissionPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.submit_task(payload, context)


def confirm_task(app: QricsApiApp, task_id: str, context: RequestContext) -> ApiResponse:
    return app.confirm_task(task_id, context)


def handoff_task(app: QricsApiApp, task_id: str, context: RequestContext) -> ApiResponse:
    return app.handoff_task(task_id, context)


def cancel_task(
    app: QricsApiApp,
    task_id: str,
    context: RequestContext,
    reason: str,
) -> ApiResponse:
    return app.cancel_task(task_id, context, reason)
