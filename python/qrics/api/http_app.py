"""FastAPI HTTP/WebSocket adapter for the QRICS application facade.

This module is a transport adapter. Domain state stays in ``QricsApiApp``;
HTTP concerns are limited to request context extraction, JSON payload
conversion, error mapping, and event streaming.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, cast

from fastapi import FastAPI, Header, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from qrics.api.app import QricsApiApp, create_demo_app
from qrics.api.schemas import (
    ApiResponse,
    AuditQuery,
    EventEnvelope,
    GateReportPayload,
    MetricSummaryPayload,
    OverridePayload,
    PolicyRegistrationPayload,
    ReplayQuery,
    RequestContext,
    ResourceRef,
    TaskSubmissionPayload,
    TrainingPlanPayload,
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
                command_type=_required_str(payload, "command_type"),  # type: ignore[arg-type]
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
            ),
            context,
        )
        return _to_json_response(response)

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
                decision=_required_str(payload, "decision"),  # type: ignore[arg-type]
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
    async def websocket_events(websocket: WebSocket, run_id: str = "") -> None:
        await websocket.accept()
        qrics = _state(app)
        context = RequestContext(request_id="ws", actor_id="ws", role="auditor")
        try:
            response = qrics.query_events(context, run_id=run_id)
            events = (
                cast(list[dict[str, object]], response.data.get("events", []))
                if response.ok
                else []
            )
            for event in events:
                await websocket.send_json(event)
            await websocket.send_json(
                {
                    "event_id": "snapshot_complete",
                    "topic": "control.status",
                    "run_id": run_id,
                    "message": "event snapshot complete",
                    "payload": {"count": len(events)},
                    "request_id": "ws",
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
        role=(role or "operator"),  # type: ignore[arg-type]
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


def _metric_payload(raw: JsonMapping) -> MetricSummaryPayload:
    return MetricSummaryPayload(
        success_rate=float(raw.get("success_rate", 0.0)),
        collision_rate=float(raw.get("collision_rate", 1.0)),
        tracking_error_m=float(raw.get("tracking_error_m", 999.0)),
        recovery_rate=float(raw.get("recovery_rate", 0.0)),
        energy_proxy=float(raw.get("energy_proxy", 0.0)),
        hard_constraint_violation_count=int(raw.get("hard_constraint_violation_count", 0)),
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


app = create_http_app()
