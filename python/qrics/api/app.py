"""Dependency-free QRICS application API facade.

This facade is deliberately not an HTTP server. It provides the same boundary
objects that HTTP/WebSocket adapters will expose later, while keeping the current
repository runnable without FastAPI, databases, message brokers, or Isaac Lab.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from qrics.api.errors import conflict, forbidden, invalid_request, not_found
from qrics.api.event_stream import InMemoryEventStream
from qrics.api.schemas import (
    ApiResponse,
    AuditQuery,
    AuditRecordResponse,
    ControlStatusResponse,
    EventEnvelope,
    GateReportPayload,
    OverridePayload,
    PolicyRegistrationPayload,
    PolicyStateResponse,
    ReplayQuery,
    ReplayResponse,
    RequestContext,
    ResourceRef,
    TaskLifecycleResponse,
    TaskPreviewResponse,
    TaskSubmissionPayload,
    TrainingJobResponse,
    TrainingPlanPayload,
    WaypointView,
)
from qrics.api.simulation_runner import (
    LocalSimulationRunner,
    SimulationRunner,
    SimulationRunRequest,
)


@dataclass
class QricsApiApp:
    tasks: dict[str, TaskPreviewResponse] = field(default_factory=dict)
    task_events: dict[str, list[str]] = field(default_factory=dict)
    controls: dict[str, ControlStatusResponse] = field(default_factory=dict)
    training_jobs: dict[str, TrainingJobResponse] = field(default_factory=dict)
    policies: dict[str, PolicyStateResponse] = field(default_factory=dict)
    gate_passed: set[str] = field(default_factory=set)
    audit_records: list[AuditRecordResponse] = field(default_factory=list)
    replay_index: dict[str, ReplayResponse] = field(default_factory=dict)
    event_stream: InMemoryEventStream = field(default_factory=InMemoryEventStream)
    simulation_runner: SimulationRunner | None = field(default_factory=LocalSimulationRunner)
    default_sim_backend: str = "minimal"
    default_runtime_profile: str = "headless_fast"

    def submit_task(
        self,
        payload: TaskSubmissionPayload,
        context: RequestContext,
    ) -> ApiResponse:
        if not payload.source_text.strip():
            return invalid_request(context, "source_text must not be empty", "source_text")

        waypoints = _parse_demo_waypoints(payload.source_text)
        task_id = f"task_{len(self.tasks) + 1}"
        if not waypoints:
            self.task_events[task_id] = ["submitted", "rejected"]
            rejected = TaskPreviewResponse(
                task_id=task_id,
                state="rejected",
                goal=payload.source_text,
                waypoints=(),
                selected_policy_reason="no waypoint matched",
                risk_summary="任务缺少可执行路径点",
                operator_action_required=True,
            )
            self.tasks[task_id] = rejected
            return ApiResponse.success(
                data=rejected.to_json(),
                request_id=context.request_id,
            )

        preview = TaskPreviewResponse(
            task_id=task_id,
            state="preview_ready",
            goal=payload.source_text,
            waypoints=waypoints,
            selected_policy_reason="规则策略选择：flat/gravel/platform 占位策略",
            risk_summary="未发现禁行区冲突；执行前仍需 Safety Shield 门控",
            operator_action_required=payload.require_confirmation,
        )
        self.tasks[task_id] = preview
        self.task_events[task_id] = ["submitted", "preview_generated"]
        self.event_stream.append(
            topic="task.lifecycle",
            request_id=context.request_id,
            message="Task preview generated",
            run_id=task_id,
            payload={"task_id": task_id, "state": preview.state},
        )
        return ApiResponse.success(data=preview.to_json(), request_id=context.request_id)

    def confirm_task(self, task_id: str, context: RequestContext) -> ApiResponse:
        task = self.tasks.get(task_id)
        if task is None:
            return not_found(context, "Task", task_id)
        if task.state != "preview_ready":
            return conflict(
                context,
                f"Only preview_ready task can be confirmed, current={task.state}",
            )
        updated = replace(task, state="confirmed")
        self.tasks[task_id] = updated
        self.task_events.setdefault(task_id, []).append("confirmed")
        self.event_stream.append(
            topic="task.lifecycle",
            request_id=context.request_id,
            message="Task confirmed",
            run_id=task_id,
            payload={"task_id": task_id, "state": updated.state},
        )
        return ApiResponse.success(
            data=_task_lifecycle_json(task_id, updated.state, self.task_events),
            request_id=context.request_id,
        )

    def handoff_task(self, task_id: str, context: RequestContext) -> ApiResponse:
        task = self.tasks.get(task_id)
        if task is None:
            return not_found(context, "Task", task_id)
        if task.state != "confirmed":
            return conflict(
                context,
                f"Only confirmed task can be handed off, current={task.state}",
            )

        updated = replace(task, state="handed_off")
        self.tasks[task_id] = updated
        self.task_events.setdefault(task_id, []).append("handed_off")

        run_id = f"run_{task_id}"
        simulation_summary = None

        if self.simulation_runner is not None:
            try:
                simulation_summary = self.simulation_runner.run(
                    SimulationRunRequest(
                        run_id=run_id,
                        backend=self.default_sim_backend,
                        runtime_profile=self.default_runtime_profile,
                        scene_id=task_id,
                        scene_version="0.2.0",
                        step_count=20,
                    )
                )
            except RuntimeError as exc:
                self.controls[run_id] = ControlStatusResponse(
                    run_id=run_id,
                    state="failed",
                    current_node_id="move_0",
                    latest_action="stop",
                    reason=f"Simulation handoff failed: {exc}",
                    backend=self.default_sim_backend,
                    runtime_profile=self.default_runtime_profile,
                )
                self._append_audit(
                    context,
                    "control.handoff_failed",
                    ResourceRef(run_id),
                    "failed",
                    str(exc),
                )
                return ApiResponse.success(
                    data=self.controls[run_id].to_json(),
                    request_id=context.request_id,
                )

        if simulation_summary is None:
            self.controls[run_id] = ControlStatusResponse(
                run_id=run_id,
                state="running",
                current_node_id="move_0",
                latest_action="body_velocity",
                reason="Task handed off to placeholder control service",
                backend=self.default_sim_backend,
                runtime_profile=self.default_runtime_profile,
            )
            replay = ReplayResponse(
                run_id=run_id,
                segment_count=1,
                keyframe_count=0,
            )
        else:
            self.controls[run_id] = ControlStatusResponse(
                run_id=run_id,
                state="running",
                current_node_id="move_0",
                control_step_count=simulation_summary.step_count,
                risk_score=simulation_summary.risk_score,
                latest_action="body_velocity",
                reason=f"Task handed off to {simulation_summary.backend} simulation runner",
                backend=simulation_summary.backend,
                runtime_profile=simulation_summary.runtime_profile,
                sim_time_ns=simulation_summary.sim_time_ns,
                base_position=simulation_summary.base_position,
                observation_quality=simulation_summary.observation_quality,
            )
            replay = ReplayResponse(
                run_id=run_id,
                segment_count=1,
                keyframe_count=len(simulation_summary.keyframes),
                backend=simulation_summary.backend,
                runtime_profile=simulation_summary.runtime_profile,
                first_timestamp_ns=0,
                last_timestamp_ns=simulation_summary.sim_time_ns,
                keyframes=simulation_summary.keyframes,
            )

        self.replay_index[run_id] = replay
        self.event_stream.append(
            topic="control.status",
            request_id=context.request_id,
            message="Control run started",
            run_id=run_id,
            payload={
                "run_id": run_id,
                "state": self.controls[run_id].state,
                "backend": self.controls[run_id].backend,
                "runtime_profile": self.controls[run_id].runtime_profile,
                "control_step_count": self.controls[run_id].control_step_count,
                "base_position": list(self.controls[run_id].base_position),
                "sim_time_ns": self.controls[run_id].sim_time_ns,
            },
        )
        return ApiResponse.success(
            data=self.controls[run_id].to_json(),
            request_id=context.request_id,
        )

    def cancel_task(self, task_id: str, context: RequestContext, reason: str) -> ApiResponse:
        task = self.tasks.get(task_id)
        if task is None:
            return not_found(context, "Task", task_id)
        if task.state in {"handed_off", "cancelled"}:
            return conflict(context, f"Task cannot be cancelled from state={task.state}")
        updated = replace(task, state="cancelled", risk_summary=reason or task.risk_summary)
        self.tasks[task_id] = updated
        self.task_events.setdefault(task_id, []).append("cancelled")
        self._append_audit(context, "task.cancel", ResourceRef(task_id), "success", reason)
        return ApiResponse.success(
            data=_task_lifecycle_json(task_id, updated.state, self.task_events),
            request_id=context.request_id,
        )

    def get_control_status(self, run_id: str, context: RequestContext) -> ApiResponse:
        status = self.controls.get(run_id)
        if status is None:
            return not_found(context, "Control run", run_id)
        return ApiResponse.success(data=status.to_json(), request_id=context.request_id)

    def override_control(
        self,
        run_id: str,
        payload: OverridePayload,
        context: RequestContext,
    ) -> ApiResponse:
        status = self.controls.get(run_id)
        if status is None:
            return not_found(context, "Control run", run_id)

        if payload.command_type == "resume":
            updated = replace(
                status,
                state="running",
                reason=payload.reason or "resume requested",
            )
        elif payload.command_type == "emergency_stop":
            updated = replace(
                status,
                state="paused",
                latest_action="stop",
                reason="emergency stop",
            )
            self._append_audit(
                context,
                "control.emergency_stop",
                ResourceRef(run_id),
                "success",
                payload.reason,
            )
        elif payload.command_type == "safe_stand":
            updated = replace(
                status,
                state="paused",
                latest_action="safe_stand",
                reason="safe stand requested",
            )
        else:
            updated = replace(
                status,
                state="paused",
                latest_action="stop",
                reason=payload.reason or payload.command_type,
            )

        self.controls[run_id] = updated
        self.event_stream.append(
            topic="control.alert",
            request_id=context.request_id,
            message=f"Control override: {payload.command_type}",
            run_id=run_id,
            payload={
                "run_id": run_id,
                "state": updated.state,
                "action": updated.latest_action,
                "backend": updated.backend,
                "runtime_profile": updated.runtime_profile,
            },
        )
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def submit_training_plan(
        self,
        payload: TrainingPlanPayload,
        context: RequestContext,
    ) -> ApiResponse:
        if payload.max_iterations <= 0 or payload.num_envs <= 0:
            return invalid_request(context, "max_iterations and num_envs must be positive")
        job = TrainingJobResponse(
            job_id=f"job_{payload.training_id}",
            state="queued",
            scene_ref=payload.scene_ref,
            algorithm=payload.algorithm,
        )
        self.training_jobs[job.job_id] = job
        self.event_stream.append(
            topic="training.status",
            request_id=context.request_id,
            message="Training job queued",
            run_id=job.job_id,
            payload=job.to_json(),
        )
        return ApiResponse.success(data=job.to_json(), request_id=context.request_id)

    def register_policy(
        self,
        payload: PolicyRegistrationPayload,
        context: RequestContext,
    ) -> ApiResponse:
        key = _policy_key(payload.policy_ref)
        state = PolicyStateResponse(policy_ref=payload.policy_ref, stage="candidate")
        self.policies[key] = state
        self.event_stream.append(
            topic="policy.lifecycle",
            request_id=context.request_id,
            message="Policy registered as candidate",
            payload=state.to_json(),
        )
        return ApiResponse.success(data=state.to_json(), request_id=context.request_id)

    def attach_gate_report(
        self,
        payload: GateReportPayload,
        context: RequestContext,
    ) -> ApiResponse:
        key = _policy_key(payload.policy_ref)
        state = self.policies.get(key)
        if state is None:
            return not_found(context, "Policy", key)

        if payload.decision == "passed":
            self.gate_passed.add(key)
            updated = replace(state, stage="gate_passed", reason=payload.reason)
        else:
            updated = replace(state, stage="gate_failed", reason=payload.reason)

        self.policies[key] = updated
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def release_policy(
        self,
        policy_ref: ResourceRef,
        context: RequestContext,
        reason: str,
    ) -> ApiResponse:
        if context.role not in {"algorithm_engineer", "admin"}:
            return forbidden(context, "Only algorithm_engineer or admin can release policies")

        key = _policy_key(policy_ref)
        state = self.policies.get(key)
        if state is None:
            return not_found(context, "Policy", key)
        if key not in self.gate_passed:
            return conflict(context, "Policy must pass gate before release")

        updated = replace(state, stage="released", reason=reason)
        self.policies[key] = updated
        self._append_audit(context, "policy.release", policy_ref, "success", reason)
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def promote_policy_baseline(
        self,
        policy_ref: ResourceRef,
        context: RequestContext,
        reason: str,
    ) -> ApiResponse:
        if context.role not in {"algorithm_engineer", "admin"}:
            return forbidden(context, "Only algorithm_engineer or admin can promote baselines")

        key = _policy_key(policy_ref)
        state = self.policies.get(key)
        if state is None:
            return not_found(context, "Policy", key)
        if state.stage not in {"released", "baseline"}:
            return conflict(context, "Only released policy can become baseline")

        for existing_key, existing_state in tuple(self.policies.items()):
            if existing_state.is_current_baseline:
                self.policies[existing_key] = replace(
                    existing_state,
                    stage="released",
                    is_current_baseline=False,
                )

        updated = replace(state, stage="baseline", is_current_baseline=True, reason=reason)
        self.policies[key] = updated
        self._append_audit(context, "policy.promote_baseline", policy_ref, "success", reason)
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def query_replay(self, query: ReplayQuery, context: RequestContext) -> ApiResponse:
        replay = self.replay_index.get(query.run_id)
        if replay is None:
            return not_found(context, "Replay", query.run_id)
        return ApiResponse.success(data=replay.to_json(), request_id=context.request_id)

    def query_audit(self, query: AuditQuery, context: RequestContext) -> ApiResponse:
        rows = self.audit_records
        if query.actor_id:
            rows = [row for row in rows if row.actor_id == query.actor_id]
        if query.object_id:
            rows = [row for row in rows if row.object_ref.id == query.object_id]
        if query.action:
            rows = [row for row in rows if row.action == query.action]
        return ApiResponse.success(
            data={"count": len(rows), "audit_ids": [row.audit_id for row in rows]},
            request_id=context.request_id,
        )

    def list_events(self, context: RequestContext, run_id: str = "") -> tuple[EventEnvelope, ...]:
        _ = context
        return self.event_stream.query(run_id=run_id)

    def _append_audit(
        self,
        context: RequestContext,
        action: str,
        object_ref: ResourceRef,
        result: str,
        reason: str,
    ) -> None:
        record = AuditRecordResponse(
            audit_id=f"audit_{len(self.audit_records) + 1}",
            actor_id=context.actor_id,
            action=action,
            object_ref=object_ref,
            result=result,
            reason=reason,
        )
        self.audit_records.append(record)
        self.event_stream.append(
            topic="audit.record",
            request_id=context.request_id,
            message=f"Audit recorded: {action}",
            payload=record.to_json(),
        )


def create_demo_app() -> QricsApiApp:
    return QricsApiApp()


def _parse_demo_waypoints(source_text: str) -> tuple[WaypointView, ...]:
    matches: list[WaypointView] = []
    candidates = (
        ("A", WaypointView("A", name="巡检点 A", terrain_hint="flat")),
        ("B", WaypointView("B", name="巡检点 B", terrain_hint="gravel", dwell_time_s=3.0)),
        ("平台", WaypointView("platform", name="平台", terrain_hint="flat")),
    )
    for token, waypoint in candidates:
        if token in source_text:
            matches.append(waypoint)
    return tuple(matches)


def _task_lifecycle_json(
    task_id: str,
    state: str,
    task_events: dict[str, list[str]],
) -> dict[str, object]:
    events = task_events.get(task_id, [])
    response = TaskLifecycleResponse(
        task_id=task_id,
        state=state,  # type: ignore[arg-type]
        event_count=len(events),
        latest_event=events[-1] if events else "",
    )
    return response.to_json()


def _policy_key(policy_ref: ResourceRef) -> str:
    return f"{policy_ref.id}:{policy_ref.version}"
