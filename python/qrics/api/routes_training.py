"""Training and evaluation API route facade functions."""

from __future__ import annotations

from qrics.api.app import QricsApiApp
from qrics.api.schemas import (
    ApiResponse,
    EvaluationReportExportPayload,
    EvaluationRunPayload,
    RequestContext,
    TrainingCheckpointPayload,
    TrainingCompletionPayload,
    TrainingPlanPayload,
)


def submit_training_plan(
    app: QricsApiApp,
    payload: TrainingPlanPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.submit_training_plan(payload, context)


def get_training_job(app: QricsApiApp, job_id: str, context: RequestContext) -> ApiResponse:
    return app.get_training_job(job_id, context)


def list_training_jobs(app: QricsApiApp, context: RequestContext) -> ApiResponse:
    return app.list_training_jobs(context)


def start_training_job(app: QricsApiApp, job_id: str, context: RequestContext) -> ApiResponse:
    return app.start_training_job(job_id, context)


def record_training_checkpoint(
    app: QricsApiApp,
    job_id: str,
    payload: TrainingCheckpointPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.record_training_checkpoint(job_id, payload, context)


def complete_training_job(
    app: QricsApiApp,
    job_id: str,
    payload: TrainingCompletionPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.complete_training_job(job_id, payload, context)


def fail_training_job(
    app: QricsApiApp,
    job_id: str,
    context: RequestContext,
    reason: str,
) -> ApiResponse:
    return app.fail_training_job(job_id, context, reason)


def cancel_training_job(
    app: QricsApiApp,
    job_id: str,
    context: RequestContext,
    reason: str,
) -> ApiResponse:
    return app.cancel_training_job(job_id, context, reason)


def run_standard_evaluation(
    app: QricsApiApp,
    payload: EvaluationRunPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.run_standard_evaluation(payload, context)


def get_evaluation_report(
    app: QricsApiApp,
    evaluation_id: str,
    context: RequestContext,
) -> ApiResponse:
    return app.get_evaluation_report(evaluation_id, context)


def list_evaluation_reports(app: QricsApiApp, context: RequestContext) -> ApiResponse:
    return app.list_evaluation_reports(context)


def export_evaluation_report(
    app: QricsApiApp,
    payload: EvaluationReportExportPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.export_evaluation_report(payload, context)


def get_evaluation_report_export(
    app: QricsApiApp, export_id: str, context: RequestContext
) -> ApiResponse:
    return app.get_evaluation_report_export(export_id, context)


def list_evaluation_report_exports(
    app: QricsApiApp, context: RequestContext, evaluation_id: str = ""
) -> ApiResponse:
    return app.list_evaluation_report_exports(context, evaluation_id)
