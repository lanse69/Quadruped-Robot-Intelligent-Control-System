"""FastAPI HTTP/WebSocket adapter for the QRICS application facade.

This module is a transport adapter. Domain state stays in ``QricsApiApp``;
HTTP concerns are limited to request context extraction, JSON payload
conversion, error mapping, and event streaming.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any, cast

from fastapi import FastAPI, Header, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from qrics.api.app import QricsApiApp, create_demo_app
from qrics.api.schemas import (
    ApiResponse,
    AuditQuery,
    EvaluationReportExportPayload,
    EvaluationRunPayload,
    EventEnvelope,
    GateDecision,
    GateReportPayload,
    JsonDict,
    JsonValue,
    MetricSummaryPayload,
    OverridePayload,
    OverrideType,
    PolicyApprovalPayload,
    PolicyRegistrationPayload,
    RandomizationProfilePayload,
    ReplayQuery,
    ReportExportFormat,
    RequestContext,
    ResourceRef,
    SceneAssetPayload,
    SceneAssetType,
    SceneCopyPayload,
    SceneCreatePayload,
    SceneGeometryType,
    SensorProfilePayload,
    TaskSubmissionPayload,
    TrainingCheckpointPayload,
    TrainingCompletionPayload,
    TrainingPlanPayload,
    TrainingResourceQuotaPayload,
)
from qrics.api.security import (
    approval_decision_from_string,
    gate_decision_from_string,
    normalize_role,
    override_type_from_string,
)

JsonMapping = Mapping[str, Any]


def create_http_app(qrics_app: QricsApiApp | None = None) -> FastAPI:
    """Create the HTTP/WebSocket service around an application facade."""

    app = FastAPI(title="QRICS API", version="0.1.0")
    app.state.qrics = qrics_app or create_demo_app()

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: object, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "errors": [{"code": "INVALID_REQUEST", "message": str(exc), "field": ""}],
                "request_id": "",
            },
        )

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        return {"ok": True, "service": "qrics-api", "version": "0.1.0"}

    @app.post("/api/v1/scenes")
    def create_scene(
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).create_scene(_scene_create_payload(payload), context))

    @app.get("/api/v1/scenes")
    def list_scenes(
        scene_id: str = Query(default=""),
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).list_scenes(context, scene_id=scene_id))

    @app.get("/api/v1/scenes/{scene_id}/{scene_version}")
    def get_scene(
        scene_id: str,
        scene_version: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(
            _state(app).get_scene(ResourceRef(scene_id, scene_version), context)
        )

    @app.post("/api/v1/scenes/{scene_id}/{scene_version}/copy")
    def copy_scene(
        scene_id: str,
        scene_version: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        response = _state(app).copy_scene(
            ResourceRef(scene_id, scene_version),
            SceneCopyPayload(
                target_version=_required_str(payload, "target_version"),
                change_summary=str(payload.get("change_summary", "")),
            ),
            context,
        )
        return _to_json_response(response)

    @app.post("/api/v1/scenes/{scene_id}/{scene_version}/baseline")
    def publish_scene_baseline(
        scene_id: str,
        scene_version: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        response = _state(app).publish_scene_baseline(
            ResourceRef(scene_id, scene_version),
            context,
            str(payload.get("reason", "")),
        )
        return _to_json_response(response)

    @app.post("/api/v1/scenes/{scene_id}/{scene_version}/archive")
    def archive_scene(
        scene_id: str,
        scene_version: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        response = _state(app).archive_scene(
            ResourceRef(scene_id, scene_version),
            context,
            str(payload.get("reason", "")),
        )
        return _to_json_response(response)

    @app.post("/api/v1/tasks")
    def submit_task(
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        scene_ref = _resource_ref(
            payload.get("scene_ref"),
            default_id="minimal_scene",
            default_version="0.1.0",
        )
        response = _state(app).submit_task(
            TaskSubmissionPayload(
                source_text=_required_str(payload, "source_text"),
                scene_ref=scene_ref,
                require_confirmation=bool(payload.get("require_confirmation", True)),
            ),
            context,
        )
        return _to_json_response(response)

    @app.post("/api/v1/tasks/{task_id}/confirm")
    def confirm_task(
        task_id: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).confirm_task(task_id, context))

    @app.post("/api/v1/tasks/{task_id}/handoff")
    def handoff_task(
        task_id: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).handoff_task(task_id, context))

    @app.post("/api/v1/tasks/{task_id}/cancel")
    def cancel_task(
        task_id: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        reason = str(payload.get("reason", ""))
        return _to_json_response(_state(app).cancel_task(task_id, context, reason))

    @app.get("/api/v1/control/{run_id}")
    def get_control_status(
        run_id: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).get_control_status(run_id, context))

    @app.post("/api/v1/control/{run_id}/override")
    def override_control(
        run_id: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        response = _state(app).override_control(
            run_id,
            OverridePayload(
                command_type=_required_override_type(payload, "command_type"),
                reason=str(payload.get("reason", "")),
            ),
            context,
        )
        return _to_json_response(response)

    @app.post("/api/v1/training/plans")
    def submit_training_plan(
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        scene_ref = _resource_ref(
            payload.get("scene_ref"),
            default_id="minimal_scene",
            default_version="0.1.0",
        )
        response = _state(app).submit_training_plan(
            TrainingPlanPayload(
                training_id=_required_str(payload, "training_id"),
                scene_ref=scene_ref,
                algorithm=str(payload.get("algorithm", "ppo_placeholder")),
                max_iterations=_optional_int(payload, "max_iterations", 100),
                num_envs=_optional_int(payload, "num_envs", 1),
                seed=_optional_int(payload, "seed", 42),
                reward_config_version=str(
                    payload.get("reward_config_version", "reward.default.v1")
                ),
                randomization_profile_id=str(
                    payload.get("randomization_profile_id", "no_randomization")
                ),
                checkpoint_interval=_optional_int(payload, "checkpoint_interval", 10),
                resource_quota=_resource_quota(payload.get("resource_quota", {})),
                notes=str(payload.get("notes", "")),
            ),
            context,
        )
        return _to_json_response(response)

    @app.get("/api/v1/training/jobs")
    def list_training_jobs(
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).list_training_jobs(context))

    @app.get("/api/v1/training/jobs/{job_id}")
    def get_training_job(
        job_id: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).get_training_job(job_id, context))

    @app.post("/api/v1/training/jobs/{job_id}/start")
    def start_training_job(
        job_id: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).start_training_job(job_id, context))

    @app.post("/api/v1/training/jobs/{job_id}/checkpoint")
    def record_training_checkpoint(
        job_id: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        response = _state(app).record_training_checkpoint(
            job_id,
            TrainingCheckpointPayload(
                iteration=_optional_int(payload, "iteration", 0),
                checkpoint_uri=_required_str(payload, "checkpoint_uri"),
                reason=str(payload.get("reason", "")),
            ),
            context,
        )
        return _to_json_response(response)

    @app.post("/api/v1/training/jobs/{job_id}/complete")
    def complete_training_job(
        job_id: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(
            _state(app).complete_training_job(
                job_id,
                _training_completion_payload(payload),
                context,
            )
        )

    @app.post("/api/v1/training/jobs/{job_id}/fail")
    def fail_training_job(
        job_id: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(
            _state(app).fail_training_job(job_id, context, str(payload.get("reason", "")))
        )

    @app.post("/api/v1/training/jobs/{job_id}/cancel")
    def cancel_training_job(
        job_id: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(
            _state(app).cancel_training_job(job_id, context, str(payload.get("reason", "")))
        )

    @app.post("/api/v1/evaluations")
    def run_standard_evaluation(
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(
            _state(app).run_standard_evaluation(_evaluation_run_payload(payload), context)
        )

    @app.get("/api/v1/evaluations")
    def list_evaluation_reports(
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).list_evaluation_reports(context))

    @app.get("/api/v1/evaluations/{evaluation_id}")
    def get_evaluation_report(
        evaluation_id: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).get_evaluation_report(evaluation_id, context))

    @app.post("/api/v1/evaluations/{evaluation_id}/exports")
    def export_evaluation_report(
        evaluation_id: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        response = _state(app).export_evaluation_report(
            EvaluationReportExportPayload(
                evaluation_id=evaluation_id,
                report_format=_report_export_format(str(payload.get("format", "json"))),
                reason=str(payload.get("reason", "")),
            ),
            context,
        )
        return _to_json_response(response)

    @app.get("/api/v1/evaluations/{evaluation_id}/exports")
    def list_evaluation_report_exports(
        evaluation_id: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(
            _state(app).list_evaluation_report_exports(context, evaluation_id=evaluation_id)
        )

    @app.get("/api/v1/evaluation-exports/{export_id}")
    def get_evaluation_report_export(
        export_id: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).get_evaluation_report_export(export_id, context))

    @app.post("/api/v1/policies/{policy_id}/{policy_version}/approval")
    def approve_policy(
        policy_id: str,
        policy_version: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        response = _state(app).approve_policy(
            PolicyApprovalPayload(
                policy_ref=ResourceRef(policy_id, policy_version),
                evaluation_id=_required_str(payload, "evaluation_id"),
                decision=approval_decision_from_string(_required_str(payload, "decision")),
                reason=_required_str(payload, "reason"),
            ),
            context,
        )
        return _to_json_response(response)

    @app.get("/api/v1/policies/{policy_id}/{policy_version}/approvals")
    def list_policy_approvals(
        policy_id: str,
        policy_version: str,
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(
            _state(app).list_policy_approvals(context, ResourceRef(policy_id, policy_version))
        )

    @app.post("/api/v1/policies")
    def register_policy(
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        metrics_raw = _required_mapping(payload, "metrics")
        response = _state(app).register_policy(
            PolicyRegistrationPayload(
                policy_ref=_required_resource_ref(payload, "policy_ref"),
                artifact_uri=_required_str(payload, "artifact_uri"),
                metrics=_metric_payload(metrics_raw),
                checksum=str(payload.get("checksum", "")),
            ),
            context,
        )
        return _to_json_response(response)

    @app.post("/api/v1/policies/gate-report")
    def attach_gate_report(
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        response = _state(app).attach_gate_report(
            GateReportPayload(
                policy_ref=_required_resource_ref(payload, "policy_ref"),
                decision=_required_gate_decision(payload, "decision"),
                reason=_required_str(payload, "reason"),
            ),
            context,
        )
        return _to_json_response(response)

    @app.post("/api/v1/policies/{policy_id}/{policy_version}/release")
    def release_policy(
        policy_id: str,
        policy_version: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        policy_ref = ResourceRef(policy_id, policy_version)
        response = _state(app).release_policy(
            policy_ref,
            context,
            str(payload.get("reason", "")),
        )
        return _to_json_response(response)

    @app.post("/api/v1/policies/{policy_id}/{policy_version}/baseline")
    def promote_policy_baseline(
        policy_id: str,
        policy_version: str,
        payload: dict[str, object],
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        policy_ref = ResourceRef(policy_id, policy_version)
        response = _state(app).promote_policy_baseline(
            policy_ref,
            context,
            str(payload.get("reason", "")),
        )
        return _to_json_response(response)

    @app.get("/api/v1/replay/{run_id}")
    def query_replay(
        run_id: str,
        event_type: str = Query(default=""),
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).query_replay(ReplayQuery(run_id, event_type), context))

    @app.get("/api/v1/audit")
    def query_audit(
        actor_id: str = Query(default=""),
        object_id: str = Query(default=""),
        action: str = Query(default=""),
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(
            _state(app).query_audit(AuditQuery(actor_id, object_id, action), context)
        )

    @app.get("/api/v1/events")
    def list_events(
        run_id: str = Query(default=""),
        x_request_id: str = Header(default=""),
        x_actor_id: str = Header(default="operator"),
        x_actor_role: str = Header(default="operator"),
    ) -> JSONResponse:
        context = _context(x_request_id, x_actor_id, x_actor_role)
        return _to_json_response(_state(app).query_events(context, run_id=run_id))

    @app.websocket("/api/v1/ws/events")
    async def websocket_events(
        websocket: WebSocket,
        run_id: str = "",
        request_id: str = Query(default=""),
        actor_id: str = Query(default=""),
        actor_role: str = Query(default=""),
    ) -> None:
        await websocket.accept()
        qrics = _state(app)
        context = _websocket_context(websocket, request_id, actor_id, actor_role)

        try:
            response = qrics.query_events(context, run_id=run_id)
            events = _event_records(response.data) if response.ok else []
            for event in events:
                await websocket.send_json(event)
            await websocket.send_json(
                {
                    "event_id": "snapshot_complete",
                    "topic": "control.status",
                    "run_id": run_id,
                    "message": "event snapshot complete",
                    "payload": {"count": len(events)},
                    "request_id": context.request_id,
                    "timestamp_ns": time.time_ns(),
                }
            )
            while True:
                message = await websocket.receive_json()
                if message.get("op") == "close":
                    await websocket.close()
                    return
        except WebSocketDisconnect:
            return

    return app


def _state(app: FastAPI) -> QricsApiApp:
    return cast(QricsApiApp, app.state.qrics)


def _context(request_id: str, actor_id: str, role: str) -> RequestContext:
    return RequestContext(
        request_id=request_id or "req-http",
        actor_id=actor_id or "operator",
        role=normalize_role(role),
    )


def _websocket_context(
    websocket: WebSocket,
    request_id: str,
    actor_id: str,
    actor_role: str,
) -> RequestContext:
    return _context(
        request_id or websocket.headers.get("x-request-id", "req-ws"),
        actor_id or websocket.headers.get("x-actor-id", "ws"),
        actor_role or websocket.headers.get("x-actor-role", "operator"),
    )


def _to_json_response(response: ApiResponse) -> JSONResponse:
    if response.ok:
        return JSONResponse(
            status_code=200,
            content={"ok": True, "data": response.data, "request_id": response.request_id},
        )

    error = response.errors[0] if response.errors else None
    code = error.code if error is not None else "INTERNAL_ERROR"
    return JSONResponse(
        status_code=_status_code(code),
        content={
            "ok": False,
            "errors": [
                {"code": item.code, "message": item.message, "field": item.field}
                for item in response.errors
            ],
            "request_id": response.request_id,
        },
    )


def _status_code(code: str) -> int:
    if code == "NOT_FOUND":
        return 404
    if code == "FORBIDDEN":
        return 403
    if code in {"CONFLICT", "STATE_CONFLICT"}:
        return 409
    if code == "INVALID_REQUEST":
        return 422
    return 500


def _event_records(data: JsonDict) -> list[dict[str, JsonValue]]:
    raw_events = data.get("events", [])
    if not isinstance(raw_events, list):
        return []
    events: list[dict[str, JsonValue]] = []
    for item in raw_events:
        if isinstance(item, dict):
            events.append(item)
    return events


def _metric_payload(raw: JsonMapping) -> MetricSummaryPayload:
    return MetricSummaryPayload(
        success_rate=float(raw.get("success_rate", 0.0)),
        collision_rate=float(raw.get("collision_rate", 1.0)),
        tracking_error_m=float(raw.get("tracking_error_m", 999.0)),
        recovery_rate=float(raw.get("recovery_rate", 0.0)),
        energy_proxy=float(raw.get("energy_proxy", 0.0)),
        hard_constraint_violation_count=int(raw.get("hard_constraint_violation_count", 0)),
    )


def _resource_quota(raw: object) -> TrainingResourceQuotaPayload:
    if raw is None:
        return TrainingResourceQuotaPayload()
    if not isinstance(raw, Mapping):
        raise ValueError("resource_quota must be an object")
    return TrainingResourceQuotaPayload(
        gpu_count=_optional_int(raw, "gpu_count", 0),
        cpu_threads=_optional_int(raw, "cpu_threads", 2),
        memory_gb=float(raw.get("memory_gb", 4.0)),
        max_runtime_s=_optional_int(raw, "max_runtime_s", 3600),
    )


def _training_completion_payload(payload: JsonMapping) -> TrainingCompletionPayload:
    metrics_raw = _required_mapping(payload, "metrics")
    return TrainingCompletionPayload(
        policy_ref=_required_resource_ref(payload, "policy_ref"),
        artifact_uri=_required_str(payload, "artifact_uri"),
        metrics=_metric_payload(metrics_raw),
        checksum=str(payload.get("checksum", "")),
        final_iteration=_optional_int(payload, "final_iteration", 0),
        reason=str(payload.get("reason", "training completed")),
    )


def _evaluation_run_payload(payload: JsonMapping) -> EvaluationRunPayload:
    metrics_raw = _required_mapping(payload, "metrics")
    scene_ref = _resource_ref(
        payload.get("scene_ref"),
        default_id="minimal_scene",
        default_version="0.1.0",
    )
    baseline_ref = _resource_ref(
        payload.get("baseline_policy_ref"),
        default_id="",
        default_version="",
    )
    return EvaluationRunPayload(
        evaluation_id=_required_str(payload, "evaluation_id"),
        policy_ref=_required_resource_ref(payload, "policy_ref"),
        scene_ref=scene_ref,
        metrics=_metric_payload(metrics_raw),
        suite_id=str(payload.get("suite_id", "standard_v1")),
        baseline_policy_ref=baseline_ref,
        replay_run_id=str(payload.get("replay_run_id", "")),
        reason=str(payload.get("reason", "")),
    )


def _event_json(event: EventEnvelope) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "topic": event.topic,
        "run_id": event.run_id,
        "message": event.message,
        "payload": event.payload,
        "request_id": event.request_id,
        "timestamp_ns": event.timestamp_ns,
    }


def _required_str(payload: JsonMapping, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_override_type(payload: JsonMapping, key: str) -> OverrideType:
    return override_type_from_string(_required_str(payload, key))


def _required_gate_decision(payload: JsonMapping, key: str) -> GateDecision:
    return gate_decision_from_string(_required_str(payload, key))


def _report_export_format(value: str) -> ReportExportFormat:
    normalized = value.strip() or "json"
    if normalized not in {"json", "markdown"}:
        raise ValueError("format must be one of: json, markdown")
    return cast(ReportExportFormat, normalized)


def _required_mapping(payload: JsonMapping, key: str) -> JsonMapping:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be an object")
    return value


def _optional_int(payload: JsonMapping, key: str, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{key} must be an integer") from exc
    raise ValueError(f"{key} must be an integer")


def _resource_ref(raw: object, *, default_id: str, default_version: str) -> ResourceRef:
    if not isinstance(raw, Mapping):
        return ResourceRef(default_id, default_version)
    value_id = str(raw.get("id", default_id))
    version = str(raw.get("version", default_version))
    return ResourceRef(value_id, version)


def _required_resource_ref(payload: JsonMapping, key: str) -> ResourceRef:
    raw = _required_mapping(payload, key)
    value_id = _required_str(raw, "id")
    version = str(raw.get("version", ""))
    return ResourceRef(value_id, version)


def _scene_create_payload(payload: JsonMapping) -> SceneCreatePayload:
    return SceneCreatePayload(
        scene_id=_required_str(payload, "scene_id"),
        version=_required_str(payload, "version"),
        name=str(payload.get("name", "")),
        terrain_pack=str(payload.get("terrain_pack", "flat")),
        assets=_scene_assets(payload.get("assets", [])),
        sensor_profile=_sensor_profile(payload.get("sensor_profile", {})),
        randomization_profile=_randomization_profile(payload.get("randomization_profile", {})),
        change_summary=str(payload.get("change_summary", "")),
    )


def _scene_assets(raw: object) -> tuple[SceneAssetPayload, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("assets must be a list")
    return tuple(_scene_asset(item) for item in raw)


def _scene_asset(raw: object) -> SceneAssetPayload:
    if not isinstance(raw, Mapping):
        raise ValueError("scene asset must be an object")
    return SceneAssetPayload(
        asset_id=_required_str(raw, "asset_id"),
        asset_type=_scene_asset_type(str(raw.get("asset_type", "terrain"))),
        uri=str(raw.get("uri", "")),
        checksum=str(raw.get("checksum", "")),
        frame_id=str(raw.get("frame_id", "world")),
        required=bool(raw.get("required", True)),
        geometry_type=_scene_geometry_type(str(raw.get("geometry_type", "none"))),
        position=_float_triplet(raw.get("position", (0.0, 0.0, 0.0)), "position"),
        size=_float_triplet(raw.get("size", (0.0, 0.0, 0.0)), "size"),
        radius_m=float(raw.get("radius_m", 0.0)),
        height_m=float(raw.get("height_m", 0.0)),
    )


def _sensor_profile(raw: object) -> SensorProfilePayload:
    if raw is None:
        return SensorProfilePayload()
    if not isinstance(raw, Mapping):
        raise ValueError("sensor_profile must be an object")
    return SensorProfilePayload(
        profile_id=str(raw.get("profile_id", "default_sensors")),
        camera_enabled=bool(raw.get("camera_enabled", False)),
        depth_camera_enabled=bool(raw.get("depth_camera_enabled", False)),
        lidar_enabled=bool(raw.get("lidar_enabled", False)),
        imu_enabled=bool(raw.get("imu_enabled", True)),
        foot_contact_enabled=bool(raw.get("foot_contact_enabled", True)),
        sample_rate_hz=_optional_int(raw, "sample_rate_hz", 100),
        noise_std=float(raw.get("noise_std", 0.0)),
        source_quality=str(raw.get("source_quality", "direct")),
    )


def _randomization_profile(raw: object) -> RandomizationProfilePayload:
    if raw is None:
        return RandomizationProfilePayload()
    if not isinstance(raw, Mapping):
        raise ValueError("randomization_profile must be an object")
    return RandomizationProfilePayload(
        profile_id=str(raw.get("profile_id", "no_randomization")),
        enabled=bool(raw.get("enabled", False)),
        friction_range=_float_pair(raw.get("friction_range"), (1.0, 1.0)),
        mass_scale_range=_float_pair(raw.get("mass_scale_range"), (1.0, 1.0)),
        sensor_noise_std=float(raw.get("sensor_noise_std", 0.0)),
        seed=_optional_int(raw, "seed", 42),
    )


def _float_pair(raw: object, default: tuple[float, float]) -> tuple[float, float]:
    if raw is None:
        return default
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("range values must be two-number arrays")
    if len(raw) != 2:
        raise ValueError("range values must be two-number arrays")
    return (float(raw[0]), float(raw[1]))


def _scene_asset_type(value: str) -> SceneAssetType:
    if value in {"terrain", "obstacle", "checkpoint", "no_go_zone", "sensor_mount"}:
        return cast(SceneAssetType, value)
    raise ValueError(
        "asset_type must be one of: checkpoint, no_go_zone, obstacle, sensor_mount, terrain"
    )


def _scene_geometry_type(value: str) -> SceneGeometryType:
    if value in {"none", "sphere", "box", "cylinder"}:
        return cast(SceneGeometryType, value)
    raise ValueError("geometry_type must be one of: none, sphere, box, cylinder")


def _float_triplet(raw: object, field_name: str) -> tuple[float, float, float]:
    if raw is None:
        return (0.0, 0.0, 0.0)
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        values = list(raw)
        if len(values) != 3:
            raise ValueError(f"{field_name} must contain exactly 3 numbers")
        return (float(values[0]), float(values[1]), float(values[2]))
    raise ValueError(f"{field_name} must be a 3-number array")


app = create_http_app()
