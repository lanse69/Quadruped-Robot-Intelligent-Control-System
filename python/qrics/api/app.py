"""Dependency-free QRICS application API facade."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, replace

from qrics.api.errors import conflict, forbidden, invalid_request, not_found
from qrics.api.event_stream import InMemoryEventStream
from qrics.api.repository import InMemoryRepository, QricsRepository
from qrics.api.schemas import (
    ApiResponse,
    AuditQuery,
    AuditRecordResponse,
    ControlStatusResponse,
    EvaluationReportExportPayload,
    EvaluationReportExportResponse,
    EvaluationReportResponse,
    EvaluationRunPayload,
    EventEnvelope,
    EventTopic,
    GateDecision,
    GateReportPayload,
    JsonDict,
    MetricSummaryPayload,
    OverridePayload,
    PolicyApprovalPayload,
    PolicyApprovalResponse,
    PolicyRegistrationPayload,
    PolicyStateResponse,
    RandomizationProfilePayload,
    ReplayQuery,
    ReplayResponse,
    RequestContext,
    ResourceRef,
    SceneAssetPayload,
    SceneCopyPayload,
    SceneCreatePayload,
    SceneProfilePayload,
    SensorProfilePayload,
    TaskApiState,
    TaskLifecycleResponse,
    TaskPreviewResponse,
    TaskSubmissionPayload,
    TrainingCheckpointPayload,
    TrainingCompletionPayload,
    TrainingJobResponse,
    TrainingPlanPayload,
    WaypointView,
)
from qrics.api.security import action_for_override, authorize, high_risk_operation
from qrics.api.simulation_runner import (
    LocalSimulationRunner,
    SimulationRunner,
    SimulationRunRequest,
)
from qrics.sim import SceneObstacle as SimSceneObstacle
from qrics.sim import Vec3 as SimVec3


@dataclass
class QricsApiApp:
    """Application-level QRICS API service.

    The app coordinates domain-facing use cases and delegates persistence to a
    repository. ``event_stream`` remains as a local process snapshot for tests
    and demo clients, while the repository is the durable source of truth when a
    SQLite implementation is supplied.
    """

    repository: QricsRepository = field(default_factory=InMemoryRepository)
    event_stream: InMemoryEventStream = field(default_factory=InMemoryEventStream)
    simulation_runner: SimulationRunner | None = field(default_factory=LocalSimulationRunner)
    default_sim_backend: str = "minimal"
    default_runtime_profile: str = "headless_fast"

    def __post_init__(self) -> None:
        self._ensure_default_scene()

    def create_scene(
        self,
        payload: SceneCreatePayload,
        context: RequestContext,
    ) -> ApiResponse:
        denied = self._require_permission(context, "scene.write", "scene.create")
        if denied is not None:
            return denied

        scene_ref = ResourceRef(payload.scene_id.strip(), payload.version.strip())
        if not scene_ref.id or not scene_ref.version:
            return invalid_request(context, "scene_id and version must not be empty")
        if self.repository.get_scene(_scene_key(scene_ref)) is not None:
            return conflict(context, f"Scene already exists: {_scene_key(scene_ref)}")

        validation_errors = _validate_scene_payload(payload)
        scene = SceneProfilePayload(
            scene_ref=scene_ref,
            name=payload.name or scene_ref.id,
            terrain_pack=payload.terrain_pack,
            assets=payload.assets,
            sensor_profile=payload.sensor_profile,
            randomization_profile=payload.randomization_profile,
            state="draft",
            checksum=_scene_checksum(
                scene_ref,
                payload.name or scene_ref.id,
                payload.terrain_pack,
                payload.assets,
                payload.sensor_profile,
                payload.randomization_profile,
            ),
            change_summary=payload.change_summary,
            validation_errors=validation_errors,
        )
        self.repository.save_scene(scene)
        self._append_audit(
            context,
            "scene.create",
            scene_ref,
            "success" if not validation_errors else "validation_failed",
            payload.change_summary or "; ".join(validation_errors) or "scene draft created",
        )
        self._append_event(
            topic="scene.lifecycle",
            request_id=context.request_id,
            message="Scene draft created",
            run_id=scene_ref.id,
            payload=scene.to_json(),
        )
        return ApiResponse.success(data=scene.to_json(), request_id=context.request_id)

    def copy_scene(
        self,
        scene_ref: ResourceRef,
        payload: SceneCopyPayload,
        context: RequestContext,
    ) -> ApiResponse:
        denied = self._require_permission(context, "scene.write", "scene.copy", scene_ref)
        if denied is not None:
            return denied

        source = self.repository.get_scene(_scene_key(scene_ref))
        if source is None:
            return not_found(context, "Scene", _scene_key(scene_ref))
        target_ref = ResourceRef(scene_ref.id, payload.target_version.strip())
        if not target_ref.version:
            return invalid_request(context, "target_version must not be empty", "target_version")
        if self.repository.get_scene(_scene_key(target_ref)) is not None:
            return conflict(context, f"Scene already exists: {_scene_key(target_ref)}")

        copied = replace(
            source,
            scene_ref=target_ref,
            state="draft",
            is_current_baseline=False,
            change_summary=payload.change_summary or f"copied from {scene_ref.version}",
        )
        self.repository.save_scene(copied)
        self._append_audit(
            context,
            "scene.copy",
            target_ref,
            "success",
            copied.change_summary,
        )
        self._append_event(
            topic="scene.lifecycle",
            request_id=context.request_id,
            message="Scene version copied",
            run_id=target_ref.id,
            payload=copied.to_json(),
        )
        return ApiResponse.success(data=copied.to_json(), request_id=context.request_id)

    def publish_scene_baseline(
        self,
        scene_ref: ResourceRef,
        context: RequestContext,
        reason: str,
    ) -> ApiResponse:
        denied = self._require_high_risk_reason(
            context, "scene.publish_baseline", scene_ref, reason
        )
        if denied is not None:
            return denied

        scene = self.repository.get_scene(_scene_key(scene_ref))
        if scene is None:
            return not_found(context, "Scene", _scene_key(scene_ref))
        if scene.state == "archived":
            self._append_audit(
                context, "scene.publish_baseline", scene_ref, "rejected", "archived scene"
            )
            return conflict(context, "Archived scene cannot be published as baseline")
        if scene.validation_errors:
            self._append_audit(
                context,
                "scene.publish_baseline",
                scene_ref,
                "rejected",
                "; ".join(scene.validation_errors),
            )
            return conflict(
                context, "Scene validation errors must be fixed before baseline publish"
            )

        for existing in self.repository.list_scenes(scene_ref.id):
            if existing.is_current_baseline:
                self.repository.save_scene(
                    replace(existing, state="draft", is_current_baseline=False)
                )
        updated = replace(
            scene,
            state="baseline",
            is_current_baseline=True,
            change_summary=reason,
        )
        self.repository.save_scene(updated)
        self._append_audit(context, "scene.publish_baseline", scene_ref, "success", reason)
        self._append_event(
            topic="scene.lifecycle",
            request_id=context.request_id,
            message="Scene baseline published",
            run_id=scene_ref.id,
            payload=updated.to_json(),
        )
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def archive_scene(
        self,
        scene_ref: ResourceRef,
        context: RequestContext,
        reason: str,
    ) -> ApiResponse:
        denied = self._require_high_risk_reason(context, "scene.archive", scene_ref, reason)
        if denied is not None:
            return denied

        scene = self.repository.get_scene(_scene_key(scene_ref))
        if scene is None:
            return not_found(context, "Scene", _scene_key(scene_ref))
        if scene.is_current_baseline:
            self._append_audit(
                context,
                "scene.archive",
                scene_ref,
                "rejected",
                "current baseline cannot be archived",
            )
            return conflict(context, "Current baseline scene cannot be archived")
        updated = replace(scene, state="archived", change_summary=reason)
        self.repository.save_scene(updated)
        self._append_audit(context, "scene.archive", scene_ref, "success", reason)
        self._append_event(
            topic="scene.lifecycle",
            request_id=context.request_id,
            message="Scene archived",
            run_id=scene_ref.id,
            payload=updated.to_json(),
        )
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def get_scene(self, scene_ref: ResourceRef, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(context, "scene.read", "scene.read", scene_ref)
        if denied is not None:
            return denied
        scene = self.repository.get_scene(_scene_key(scene_ref))
        if scene is None:
            return not_found(context, "Scene", _scene_key(scene_ref))
        return ApiResponse.success(data=scene.to_json(), request_id=context.request_id)

    def list_scenes(self, context: RequestContext, scene_id: str = "") -> ApiResponse:
        denied = self._require_permission(
            context, "scene.read", "scene.list", ResourceRef(scene_id or "*")
        )
        if denied is not None:
            return denied
        scenes = self.repository.list_scenes(scene_id)
        return ApiResponse.success(
            data={"count": len(scenes), "scenes": [scene.to_json() for scene in scenes]},
            request_id=context.request_id,
        )

    def submit_task(
        self,
        payload: TaskSubmissionPayload,
        context: RequestContext,
    ) -> ApiResponse:
        denied = self._require_permission(context, "task.submit", "task.submit")
        if denied is not None:
            return denied

        if not payload.source_text.strip():
            return invalid_request(context, "source_text must not be empty", "source_text")
        scene_error = self._validate_scene_ref(payload.scene_ref, context)
        if scene_error is not None:
            return scene_error

        waypoints = _parse_demo_waypoints(payload.source_text)
        task_id = f"task_{self.repository.count_tasks() + 1}"
        if not waypoints:
            rejected = TaskPreviewResponse(
                task_id=task_id,
                state="rejected",
                goal=payload.source_text,
                waypoints=(),
                selected_policy_reason="no waypoint matched",
                risk_summary="任务缺少可执行路径点",
                operator_action_required=True,
                scene_ref=payload.scene_ref,
            )
            self.repository.save_task(rejected)
            self.repository.append_task_event(task_id, "submitted")
            self.repository.append_task_event(task_id, "rejected")
            self._append_event(
                topic="task.lifecycle",
                request_id=context.request_id,
                message="Task rejected",
                run_id=task_id,
                payload={"task_id": task_id, "state": rejected.state},
            )
            return ApiResponse.success(data=rejected.to_json(), request_id=context.request_id)

        preview = TaskPreviewResponse(
            task_id=task_id,
            state="preview_ready",
            goal=payload.source_text,
            waypoints=waypoints,
            selected_policy_reason="规则策略选择：flat/gravel/platform 占位策略",
            risk_summary="未发现禁行区冲突；执行前仍需 Safety Shield 门控",
            operator_action_required=payload.require_confirmation,
            scene_ref=payload.scene_ref,
        )
        self.repository.save_task(preview)
        self.repository.append_task_event(task_id, "submitted")
        self.repository.append_task_event(task_id, "preview_generated")
        self._append_event(
            topic="task.lifecycle",
            request_id=context.request_id,
            message="Task preview generated",
            run_id=task_id,
            payload={"task_id": task_id, "state": preview.state},
        )
        return ApiResponse.success(data=preview.to_json(), request_id=context.request_id)

    def confirm_task(self, task_id: str, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "task.confirm",
            "task.confirm",
            ResourceRef(task_id),
        )
        if denied is not None:
            return denied

        task = self.repository.get_task(task_id)
        if task is None:
            return not_found(context, "Task", task_id)
        if task.state != "preview_ready":
            return conflict(
                context,
                f"Only preview_ready task can be confirmed, current={task.state}",
            )
        updated = replace(task, state="confirmed")
        self.repository.save_task(updated)
        self.repository.append_task_event(task_id, "confirmed")
        self._append_event(
            topic="task.lifecycle",
            request_id=context.request_id,
            message="Task confirmed",
            run_id=task_id,
            payload={"task_id": task_id, "state": updated.state},
        )
        return ApiResponse.success(
            data=_task_lifecycle_json(task_id, updated.state, self.repository),
            request_id=context.request_id,
        )

    def handoff_task(self, task_id: str, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "task.handoff",
            "task.handoff",
            ResourceRef(task_id),
        )
        if denied is not None:
            return denied

        task = self.repository.get_task(task_id)
        if task is None:
            return not_found(context, "Task", task_id)
        if task.state != "confirmed":
            return conflict(
                context,
                f"Only confirmed task can be handed off, current={task.state}",
            )

        updated = replace(task, state="handed_off")
        self.repository.save_task(updated)
        self.repository.append_task_event(task_id, "handed_off")
        run_id = f"run_{task_id}"
        simulation_summary = None

        if self.simulation_runner is not None:
            try:
                simulation_summary = self.simulation_runner.run(
                    SimulationRunRequest(
                        run_id=run_id,
                        backend=self.default_sim_backend,
                        runtime_profile=self.default_runtime_profile,
                        scene_id=task.scene_ref.id,
                        scene_version=task.scene_ref.version,
                        terrain_pack=self._simulation_terrain_pack(task.scene_ref),
                        obstacles=self._simulation_obstacles(task.scene_ref),
                        step_count=20,
                    )
                )
            except RuntimeError as exc:
                failed = ControlStatusResponse(
                    run_id=run_id,
                    state="failed",
                    current_node_id="move_0",
                    latest_action="stop",
                    reason=f"Simulation handoff failed: {exc}",
                    backend=self.default_sim_backend,
                    runtime_profile=self.default_runtime_profile,
                )
                self.repository.save_control(failed)
                self._append_audit(
                    context,
                    "control.handoff_failed",
                    ResourceRef(run_id),
                    "failed",
                    str(exc),
                )
                return ApiResponse.success(data=failed.to_json(), request_id=context.request_id)

        if simulation_summary is None:
            status = ControlStatusResponse(
                run_id=run_id,
                state="running",
                current_node_id="move_0",
                latest_action="body_velocity",
                reason="Task handed off to placeholder control service",
                backend=self.default_sim_backend,
                runtime_profile=self.default_runtime_profile,
            )
            replay = ReplayResponse(run_id=run_id, segment_count=1, keyframe_count=0)
        else:
            status = ControlStatusResponse(
                run_id=run_id,
                state="running",
                current_node_id="move_0",
                control_step_count=simulation_summary.step_count,
                risk_score=simulation_summary.risk_score,
                latest_action=simulation_summary.latest_action,
                reason=f"Task handed off to {simulation_summary.backend} simulation runner",
                backend=simulation_summary.backend,
                runtime_profile=simulation_summary.runtime_profile,
                sim_time_ns=simulation_summary.sim_time_ns,
                base_position=simulation_summary.base_position,
                observation_quality=simulation_summary.observation_quality,
                terrain_class=simulation_summary.terrain_class,
                obstacle_detected=simulation_summary.obstacle_detected,
                nearest_obstacle_distance_m=simulation_summary.nearest_obstacle_distance_m,
                safety_event_count=len(simulation_summary.safety_events),
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
                safety_events=simulation_summary.safety_events,
            )

        self.repository.save_control(status)
        saved_replay = self.repository.save_replay(replay)
        self._append_event(
            topic="control.status",
            request_id=context.request_id,
            message="Control run started",
            run_id=run_id,
            payload={
                "run_id": run_id,
                "state": status.state,
                "backend": status.backend,
                "runtime_profile": status.runtime_profile,
                "control_step_count": status.control_step_count,
                "base_position": list(status.base_position),
                "sim_time_ns": status.sim_time_ns,
                "terrain_class": status.terrain_class,
                "obstacle_detected": status.obstacle_detected,
                "nearest_obstacle_distance_m": status.nearest_obstacle_distance_m,
                "safety_event_count": status.safety_event_count,
                "replay_manifest_uri": saved_replay.manifest_uri,
            },
        )
        return ApiResponse.success(data=status.to_json(), request_id=context.request_id)

    def cancel_task(self, task_id: str, context: RequestContext, reason: str) -> ApiResponse:
        object_ref = ResourceRef(task_id)
        denied = self._require_high_risk_reason(context, "task.cancel", object_ref, reason)
        if denied is not None:
            return denied

        task = self.repository.get_task(task_id)
        if task is None:
            return not_found(context, "Task", task_id)
        if task.state in {"handed_off", "cancelled"}:
            self._append_audit(
                context,
                "task.cancel",
                object_ref,
                "rejected",
                f"Task cannot be cancelled from state={task.state}",
            )
            return conflict(context, f"Task cannot be cancelled from state={task.state}")
        updated = replace(task, state="cancelled", risk_summary=reason or task.risk_summary)
        self.repository.save_task(updated)
        self.repository.append_task_event(task_id, "cancelled")
        self._append_audit(context, "task.cancel", object_ref, "success", reason)
        return ApiResponse.success(
            data=_task_lifecycle_json(task_id, updated.state, self.repository),
            request_id=context.request_id,
        )

    def get_control_status(self, run_id: str, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "control.read",
            "control.read",
            ResourceRef(run_id),
        )
        if denied is not None:
            return denied

        status = self.repository.get_control(run_id)
        if status is None:
            return not_found(context, "Control run", run_id)
        return ApiResponse.success(data=status.to_json(), request_id=context.request_id)

    def override_control(
        self,
        run_id: str,
        payload: OverridePayload,
        context: RequestContext,
    ) -> ApiResponse:
        action = action_for_override(payload.command_type)
        object_ref = ResourceRef(run_id)
        denied = self._require_high_risk_reason(context, action, object_ref, payload.reason)
        if denied is not None:
            return denied

        status = self.repository.get_control(run_id)
        if status is None:
            return not_found(context, "Control run", run_id)

        if payload.command_type == "resume":
            updated = replace(status, state="running", reason=payload.reason or "resume requested")
        elif payload.command_type == "emergency_stop":
            updated = replace(status, state="paused", latest_action="stop", reason="emergency stop")
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

        self.repository.save_control(updated)
        self._append_audit(context, action, object_ref, "success", payload.reason or action)
        self._append_event(
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
        denied = self._require_permission(
            context,
            "training.submit",
            "training.submit",
            payload.scene_ref,
        )
        if denied is not None:
            return denied

        scene_error = self._validate_scene_ref(payload.scene_ref, context)
        if scene_error is not None:
            return scene_error
        validation_error = _validate_training_plan(payload)
        if validation_error:
            return invalid_request(context, validation_error)

        job = TrainingJobResponse(
            job_id=f"job_{payload.training_id}",
            state="queued",
            scene_ref=payload.scene_ref,
            algorithm=payload.algorithm,
            max_iterations=payload.max_iterations,
            num_envs=payload.num_envs,
            seed=payload.seed,
            reward_config_version=payload.reward_config_version,
            randomization_profile_id=payload.randomization_profile_id,
            checkpoint_interval=payload.checkpoint_interval,
            resource_quota=payload.resource_quota,
            config_hash=_training_config_hash(payload),
        )
        self.repository.save_training_job(job)
        self._append_event(
            topic="training.status",
            request_id=context.request_id,
            message="Training job queued",
            run_id=job.job_id,
            payload=job.to_json(),
        )
        return ApiResponse.success(data=job.to_json(), request_id=context.request_id)

    def get_training_job(self, job_id: str, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "training.read",
            "training.read",
            ResourceRef(job_id),
        )
        if denied is not None:
            return denied
        job = self.repository.get_training_job(job_id)
        if job is None:
            return not_found(context, "Training job", job_id)
        return ApiResponse.success(data=job.to_json(), request_id=context.request_id)

    def list_training_jobs(self, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "training.read",
            "training.list",
            ResourceRef("*"),
        )
        if denied is not None:
            return denied
        jobs = self.repository.list_training_jobs()
        return ApiResponse.success(
            data={"count": len(jobs), "jobs": [job.to_json() for job in jobs]},
            request_id=context.request_id,
        )

    def start_training_job(self, job_id: str, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "training.start",
            "training.start",
            ResourceRef(job_id),
        )
        if denied is not None:
            return denied
        job = self.repository.get_training_job(job_id)
        if job is None:
            return not_found(context, "Training job", job_id)
        if job.state != "queued":
            return conflict(context, f"Only queued training job can start, current={job.state}")
        updated = replace(job, state="running")
        self.repository.save_training_job(updated)
        self._append_audit(context, "training.start", ResourceRef(job_id), "success", "started")
        self._append_event(
            topic="training.status",
            request_id=context.request_id,
            message="Training job running",
            run_id=job_id,
            payload=updated.to_json(),
        )
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def record_training_checkpoint(
        self,
        job_id: str,
        payload: TrainingCheckpointPayload,
        context: RequestContext,
    ) -> ApiResponse:
        denied = self._require_permission(
            context,
            "training.checkpoint",
            "training.checkpoint",
            ResourceRef(job_id),
        )
        if denied is not None:
            return denied
        job = self.repository.get_training_job(job_id)
        if job is None:
            return not_found(context, "Training job", job_id)
        if job.state != "running":
            return conflict(
                context, f"Only running training job can checkpoint, current={job.state}"
            )
        if payload.iteration <= job.current_iteration:
            return invalid_request(context, "checkpoint iteration must increase", "iteration")
        if payload.iteration > job.max_iterations:
            return invalid_request(
                context, "checkpoint iteration exceeds max_iterations", "iteration"
            )
        if not payload.checkpoint_uri.strip():
            return invalid_request(context, "checkpoint_uri must not be empty", "checkpoint_uri")
        updated = replace(
            job,
            current_iteration=payload.iteration,
            checkpoint_count=job.checkpoint_count + 1,
            latest_checkpoint_uri=payload.checkpoint_uri,
        )
        self.repository.save_training_job(updated)
        self._append_event(
            topic="training.status",
            request_id=context.request_id,
            message="Training checkpoint recorded",
            run_id=job_id,
            payload=updated.to_json(),
        )
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def complete_training_job(
        self,
        job_id: str,
        payload: TrainingCompletionPayload,
        context: RequestContext,
    ) -> ApiResponse:
        denied = self._require_permission(
            context,
            "training.complete",
            "training.complete",
            ResourceRef(job_id),
        )
        if denied is not None:
            return denied
        job = self.repository.get_training_job(job_id)
        if job is None:
            return not_found(context, "Training job", job_id)
        if job.state != "running":
            return conflict(context, f"Only running training job can complete, current={job.state}")
        metric_error = _validate_metrics(payload.metrics)
        if metric_error:
            return invalid_request(context, metric_error)
        final_iteration = payload.final_iteration or job.max_iterations
        if final_iteration < job.current_iteration or final_iteration > job.max_iterations:
            return invalid_request(context, "final_iteration must be within job iteration range")
        updated = replace(job, state="succeeded", current_iteration=final_iteration)
        self.repository.save_training_job(updated)

        policy = PolicyStateResponse(
            policy_ref=payload.policy_ref,
            stage="candidate",
            reason=payload.reason,
            artifact_uri=payload.artifact_uri,
            checksum=payload.checksum,
            metrics=payload.metrics,
        )
        self.repository.save_policy(policy)
        self._append_audit(
            context,
            "training.complete",
            ResourceRef(job_id),
            "success",
            payload.reason,
        )
        self._append_audit(
            context,
            "policy.register",
            payload.policy_ref,
            "success",
            f"registered from {job_id}",
        )
        self._append_event(
            topic="training.status",
            request_id=context.request_id,
            message="Training job succeeded",
            run_id=job_id,
            payload=updated.to_json(),
        )
        self._append_event(
            topic="policy.lifecycle",
            request_id=context.request_id,
            message="Policy registered from completed training job",
            payload=policy.to_json(),
        )
        return ApiResponse.success(
            data={"job": updated.to_json(), "policy": policy.to_json()},
            request_id=context.request_id,
        )

    def fail_training_job(self, job_id: str, context: RequestContext, reason: str) -> ApiResponse:
        denied = self._require_high_risk_reason(
            context, "training.fail", ResourceRef(job_id), reason
        )
        if denied is not None:
            return denied
        job = self.repository.get_training_job(job_id)
        if job is None:
            return not_found(context, "Training job", job_id)
        if job.state not in {"queued", "running"}:
            return conflict(context, f"Training job cannot fail from state={job.state}")
        updated = replace(job, state="failed", failure_reason=reason)
        self.repository.save_training_job(updated)
        self._append_audit(context, "training.fail", ResourceRef(job_id), "success", reason)
        self._append_event(
            topic="training.status",
            request_id=context.request_id,
            message="Training job failed",
            run_id=job_id,
            payload=updated.to_json(),
        )
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def cancel_training_job(self, job_id: str, context: RequestContext, reason: str) -> ApiResponse:
        denied = self._require_high_risk_reason(
            context, "training.cancel", ResourceRef(job_id), reason
        )
        if denied is not None:
            return denied
        job = self.repository.get_training_job(job_id)
        if job is None:
            return not_found(context, "Training job", job_id)
        if job.state not in {"queued", "running"}:
            return conflict(context, f"Training job cannot be cancelled from state={job.state}")
        updated = replace(job, state="cancelled", failure_reason=reason)
        self.repository.save_training_job(updated)
        self._append_audit(context, "training.cancel", ResourceRef(job_id), "success", reason)
        self._append_event(
            topic="training.status",
            request_id=context.request_id,
            message="Training job cancelled",
            run_id=job_id,
            payload=updated.to_json(),
        )
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def run_standard_evaluation(
        self,
        payload: EvaluationRunPayload,
        context: RequestContext,
    ) -> ApiResponse:
        denied = self._require_permission(
            context,
            "evaluation.run",
            "evaluation.run",
            payload.policy_ref,
        )
        if denied is not None:
            return denied
        scene_error = self._validate_scene_ref(payload.scene_ref, context)
        if scene_error is not None:
            return scene_error
        metric_error = _validate_metrics(payload.metrics)
        if metric_error:
            return invalid_request(context, metric_error)

        key = _policy_key(payload.policy_ref)
        policy = self.repository.get_policy(key)
        if policy is None:
            return not_found(context, "Policy", key)

        baseline = self.repository.get_policy(_policy_key(payload.baseline_policy_ref))
        if not payload.baseline_policy_ref.id:
            baseline = _current_baseline_policy(self.repository.list_policies())
        baseline_ref = baseline.policy_ref if baseline is not None else ResourceRef("", "")
        baseline_metrics = _policy_metrics_or_default(baseline)
        decision, reason = _evaluate_gate(payload.metrics)
        report = EvaluationReportResponse(
            evaluation_id=payload.evaluation_id,
            policy_ref=payload.policy_ref,
            scene_ref=payload.scene_ref,
            suite_id=payload.suite_id,
            metrics=payload.metrics,
            decision=decision,
            reason=payload.reason or reason,
            baseline_policy_ref=baseline_ref,
            baseline_metrics=baseline_metrics,
            baseline_diff=_baseline_diff(payload.metrics, baseline_metrics),
            replay_run_id=payload.replay_run_id,
        )
        self.repository.save_evaluation_report(report)
        self.repository.set_gate_passed(key, decision == "passed")
        updated_policy = replace(
            policy,
            stage="gate_passed" if decision == "passed" else "gate_failed",
            metrics=payload.metrics,
            reason=reason,
        )
        self.repository.save_policy(updated_policy)
        self._append_audit(
            context,
            "evaluation.run",
            payload.policy_ref,
            "success",
            f"{payload.suite_id}:{decision}",
        )
        self._append_audit(
            context,
            "policy.gate_report",
            payload.policy_ref,
            "success",
            reason,
        )
        self._append_event(
            topic="training.status",
            request_id=context.request_id,
            message="Standard evaluation completed",
            run_id=payload.evaluation_id,
            payload=report.to_json(),
        )
        self._append_event(
            topic="policy.lifecycle",
            request_id=context.request_id,
            message="Policy gate updated from evaluation",
            payload=updated_policy.to_json(),
        )
        return ApiResponse.success(data=report.to_json(), request_id=context.request_id)

    def get_evaluation_report(self, evaluation_id: str, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "evaluation.read",
            "evaluation.read",
            ResourceRef(evaluation_id),
        )
        if denied is not None:
            return denied
        report = self.repository.get_evaluation_report(evaluation_id)
        if report is None:
            return not_found(context, "Evaluation report", evaluation_id)
        return ApiResponse.success(data=report.to_json(), request_id=context.request_id)

    def list_evaluation_reports(self, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "evaluation.read",
            "evaluation.list",
            ResourceRef("*"),
        )
        if denied is not None:
            return denied
        reports = self.repository.list_evaluation_reports()
        return ApiResponse.success(
            data={"count": len(reports), "reports": [report.to_json() for report in reports]},
            request_id=context.request_id,
        )

    def export_evaluation_report(
        self, payload: EvaluationReportExportPayload, context: RequestContext
    ) -> ApiResponse:
        denied = self._require_permission(
            context,
            "evaluation.export",
            "evaluation.export",
            ResourceRef(payload.evaluation_id),
        )
        if denied is not None:
            return denied
        report = self.repository.get_evaluation_report(payload.evaluation_id)
        if report is None:
            return not_found(context, "Evaluation report", payload.evaluation_id)

        approval = self.repository.latest_policy_approval(_policy_key(report.policy_ref))
        content = _render_evaluation_report_export(
            report=report,
            approval=approval,
            report_format=payload.report_format,
            generated_by=context.actor_id,
            request_id=context.request_id,
        )
        export = EvaluationReportExportResponse(
            export_id=f"export_{self.repository.count_events() + 1}_{payload.evaluation_id}",
            evaluation_id=payload.evaluation_id,
            report_format=payload.report_format,
            uri="",
            checksum="",
            size_bytes=0,
            generated_by=context.actor_id,
            request_id=context.request_id,
            timestamp_ns=time.time_ns(),
            summary=(
                f"{report.suite_id}:{report.decision}:"
                f"{report.policy_ref.id}:{report.policy_ref.version}"
            ),
        )
        stored = self.repository.save_evaluation_report_export(export, content)
        self._append_audit(
            context,
            "evaluation.export",
            ResourceRef(payload.evaluation_id),
            "success",
            payload.reason or stored.summary,
        )
        self._append_event(
            topic="report.export",
            request_id=context.request_id,
            message="Evaluation report exported",
            run_id=payload.evaluation_id,
            payload=stored.to_json(),
        )
        return ApiResponse.success(data=stored.to_json(), request_id=context.request_id)

    def get_evaluation_report_export(self, export_id: str, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "evaluation.read",
            "evaluation.export.read",
            ResourceRef(export_id),
        )
        if denied is not None:
            return denied
        export = self.repository.get_evaluation_report_export(export_id)
        if export is None:
            return not_found(context, "Evaluation report export", export_id)
        return ApiResponse.success(data=export.to_json(), request_id=context.request_id)

    def list_evaluation_report_exports(
        self, context: RequestContext, evaluation_id: str = ""
    ) -> ApiResponse:
        denied = self._require_permission(
            context,
            "evaluation.read",
            "evaluation.export.list",
            ResourceRef(evaluation_id or "*"),
        )
        if denied is not None:
            return denied
        exports = self.repository.list_evaluation_report_exports(evaluation_id)
        return ApiResponse.success(
            data={"count": len(exports), "exports": [item.to_json() for item in exports]},
            request_id=context.request_id,
        )

    def register_policy(
        self,
        payload: PolicyRegistrationPayload,
        context: RequestContext,
    ) -> ApiResponse:
        denied = self._require_permission(
            context,
            "policy.register",
            "policy.register",
            payload.policy_ref,
        )
        if denied is not None:
            return denied

        metric_error = _validate_metrics(payload.metrics)
        if metric_error:
            return invalid_request(context, metric_error)
        state = PolicyStateResponse(
            policy_ref=payload.policy_ref,
            stage="candidate",
            artifact_uri=payload.artifact_uri,
            checksum=payload.checksum,
            metrics=payload.metrics,
        )
        self.repository.save_policy(state)
        self._append_audit(
            context,
            "policy.register",
            payload.policy_ref,
            "success",
            payload.checksum or "registered candidate policy",
        )
        self._append_event(
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
        denied = self._require_high_risk_reason(
            context,
            "policy.gate_report",
            payload.policy_ref,
            payload.reason,
        )
        if denied is not None:
            return denied

        key = _policy_key(payload.policy_ref)
        state = self.repository.get_policy(key)
        if state is None:
            return not_found(context, "Policy", key)

        if payload.decision == "passed":
            self.repository.set_gate_passed(key, True)
            updated = replace(state, stage="gate_passed", reason=payload.reason)
        else:
            self.repository.set_gate_passed(key, False)
            updated = replace(state, stage="gate_failed", reason=payload.reason)

        self.repository.save_policy(updated)
        self._append_audit(
            context,
            "policy.gate_report",
            payload.policy_ref,
            "success",
            payload.reason,
        )
        self._append_event(
            topic="policy.lifecycle",
            request_id=context.request_id,
            message="Gate report attached",
            payload=updated.to_json(),
        )
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def approve_policy(
        self, payload: PolicyApprovalPayload, context: RequestContext
    ) -> ApiResponse:
        denied = self._require_high_risk_reason(
            context, "policy.approve", payload.policy_ref, payload.reason
        )
        if denied is not None:
            return denied
        key = _policy_key(payload.policy_ref)
        state = self.repository.get_policy(key)
        if state is None:
            return not_found(context, "Policy", key)
        report = self.repository.get_evaluation_report(payload.evaluation_id)
        if report is None:
            return not_found(context, "Evaluation report", payload.evaluation_id)
        if _policy_key(report.policy_ref) != key:
            self._append_audit(
                context,
                "policy.approve",
                payload.policy_ref,
                "rejected",
                "evaluation report policy mismatch",
            )
            return conflict(context, "Evaluation report does not belong to target policy")
        if payload.decision == "approved" and report.decision != "passed":
            self._append_audit(
                context,
                "policy.approve",
                payload.policy_ref,
                "rejected",
                "failed gate report cannot be approved",
            )
            return conflict(context, "Only passed gate reports can be approved")

        approval = PolicyApprovalResponse(
            approval_id=f"approval_{self.repository.count_audit_records() + 1}",
            policy_ref=payload.policy_ref,
            evaluation_id=payload.evaluation_id,
            decision=payload.decision,
            approver_id=context.actor_id,
            approver_role=context.role,
            reason=payload.reason,
            request_id=context.request_id,
            timestamp_ns=time.time_ns(),
        )
        self.repository.save_policy_approval(approval)
        if payload.decision == "approved":
            updated = replace(state, stage="approved", reason=payload.reason)
        else:
            updated = replace(state, reason=f"approval rejected: {payload.reason}")
        self.repository.save_policy(updated)
        self._append_audit(
            context,
            "policy.approve",
            payload.policy_ref,
            "success",
            f"{payload.evaluation_id}:{payload.decision}:{payload.reason}",
        )
        self._append_event(
            topic="policy.lifecycle",
            request_id=context.request_id,
            message="Policy approval recorded",
            payload={"approval": approval.to_json(), "policy": updated.to_json()},
        )
        return ApiResponse.success(data=approval.to_json(), request_id=context.request_id)

    def list_policy_approvals(
        self, context: RequestContext, policy_ref: ResourceRef | None = None
    ) -> ApiResponse:
        object_ref = policy_ref or ResourceRef("*")
        denied = self._require_permission(
            context, "policy.approval.read", "policy.approval.list", object_ref
        )
        if denied is not None:
            return denied
        key = _policy_key(policy_ref) if policy_ref is not None else ""
        approvals = self.repository.list_policy_approvals(key)
        return ApiResponse.success(
            data={"count": len(approvals), "approvals": [item.to_json() for item in approvals]},
            request_id=context.request_id,
        )

    def release_policy(
        self,
        policy_ref: ResourceRef,
        context: RequestContext,
        reason: str,
    ) -> ApiResponse:
        denied = self._require_high_risk_reason(context, "policy.release", policy_ref, reason)
        if denied is not None:
            return denied

        key = _policy_key(policy_ref)
        state = self.repository.get_policy(key)
        if state is None:
            return not_found(context, "Policy", key)
        if not self.repository.has_gate_passed(key):
            self._append_audit(
                context,
                "policy.release",
                policy_ref,
                "rejected",
                "Policy must pass gate before release",
            )
            return conflict(context, "Policy must pass gate before release")
        approval = self.repository.latest_policy_approval(key)
        if approval is None or approval.decision != "approved":
            self._append_audit(
                context,
                "policy.release",
                policy_ref,
                "rejected",
                "Policy must have approved gate evidence before release",
            )
            return conflict(context, "Policy must have approved gate evidence before release")
        if state.stage not in {"approved", "released", "baseline"}:
            self._append_audit(
                context,
                "policy.release",
                policy_ref,
                "rejected",
                f"Policy stage={state.stage} is not releasable",
            )
            return conflict(context, f"Policy stage={state.stage} is not releasable")

        updated = replace(state, stage="released", reason=reason)
        self.repository.save_policy(updated)
        self._append_audit(context, "policy.release", policy_ref, "success", reason)
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def promote_policy_baseline(
        self,
        policy_ref: ResourceRef,
        context: RequestContext,
        reason: str,
    ) -> ApiResponse:
        denied = self._require_high_risk_reason(
            context,
            "policy.promote_baseline",
            policy_ref,
            reason,
        )
        if denied is not None:
            return denied

        key = _policy_key(policy_ref)
        state = self.repository.get_policy(key)
        if state is None:
            return not_found(context, "Policy", key)
        if state.stage not in {"released", "baseline"}:
            self._append_audit(
                context,
                "policy.promote_baseline",
                policy_ref,
                "rejected",
                "Only released policy can become baseline",
            )
            return conflict(context, "Only released policy can become baseline")

        for existing_state in self.repository.list_policies():
            if existing_state.is_current_baseline:
                self.repository.save_policy(
                    replace(existing_state, stage="released", is_current_baseline=False)
                )

        updated = replace(state, stage="baseline", is_current_baseline=True, reason=reason)
        self.repository.save_policy(updated)
        self._append_audit(context, "policy.promote_baseline", policy_ref, "success", reason)
        return ApiResponse.success(data=updated.to_json(), request_id=context.request_id)

    def query_replay(self, query: ReplayQuery, context: RequestContext) -> ApiResponse:
        denied = self._require_permission(
            context,
            "replay.read",
            "replay.read",
            ResourceRef(query.run_id),
        )
        if denied is not None:
            return denied

        replay = self.repository.get_replay(query.run_id)
        if replay is None:
            return not_found(context, "Replay", query.run_id)
        return ApiResponse.success(data=replay.to_json(), request_id=context.request_id)

    def query_audit(self, query: AuditQuery, context: RequestContext) -> ApiResponse:
        object_ref = ResourceRef(query.object_id or "*")
        denied = self._require_permission(context, "audit.read", "audit.query", object_ref)
        if denied is not None:
            return denied

        rows = self.repository.query_audit(query)
        self._append_audit(
            context,
            "audit.query",
            object_ref,
            "success",
            f"count={len(rows)}",
        )
        return ApiResponse.success(
            data={
                "count": len(rows),
                "audit_ids": [row.audit_id for row in rows],
                "records": [row.to_json() for row in rows],
            },
            request_id=context.request_id,
        )

    def query_events(self, context: RequestContext, run_id: str = "") -> ApiResponse:
        denied = self._require_permission(
            context,
            "events.read",
            "events.query",
            ResourceRef(run_id or "*"),
        )
        if denied is not None:
            return denied

        events = self.repository.query_events(run_id=run_id)
        return ApiResponse.success(
            data={"count": len(events), "events": [event.to_json() for event in events]},
            request_id=context.request_id,
        )

    def list_events(self, context: RequestContext, run_id: str = "") -> tuple[EventEnvelope, ...]:
        denied = self._require_permission(
            context,
            "events.read",
            "events.query",
            ResourceRef(run_id or "*"),
        )
        if denied is not None:
            return ()
        return self.repository.query_events(run_id=run_id)

    def _validate_scene_ref(
        self,
        scene_ref: ResourceRef,
        context: RequestContext,
    ) -> ApiResponse | None:
        scene = self.repository.get_scene(_scene_key(scene_ref))
        if scene is None:
            return invalid_request(
                context,
                f"Unknown scene reference: {_scene_key(scene_ref)}",
                "scene_ref",
            )
        if scene.state == "archived":
            return conflict(context, f"Archived scene cannot be used: {_scene_key(scene_ref)}")
        return None

    def _simulation_terrain_pack(self, scene_ref: ResourceRef) -> str:
        scene = self.repository.get_scene(_scene_key(scene_ref))
        if scene is None:
            return "flat"
        return scene.terrain_pack

    def _simulation_obstacles(self, scene_ref: ResourceRef) -> tuple[SimSceneObstacle, ...]:
        scene = self.repository.get_scene(_scene_key(scene_ref))
        if scene is None:
            return ()
        obstacles: list[SimSceneObstacle] = []
        for index, asset in enumerate(scene.assets):
            if asset.asset_type != "obstacle":
                continue
            if _asset_has_inline_geometry(asset):
                radius_m = asset.radius_m
                if radius_m <= 0.0 and asset.size != (0.0, 0.0, 0.0):
                    radius_m = max(asset.size[0], asset.size[1]) * 0.5
                height_m = asset.height_m
                if height_m <= 0.0 and asset.size != (0.0, 0.0, 0.0):
                    height_m = asset.size[2]
                geometry_type = asset.geometry_type if asset.geometry_type != "none" else "cylinder"
                obstacles.append(
                    SimSceneObstacle(
                        obstacle_id=asset.asset_id,
                        position=SimVec3(
                            x=asset.position[0],
                            y=asset.position[1],
                            z=asset.position[2],
                        ),
                        radius_m=max(0.01, radius_m),
                        height_m=max(0.01, height_m),
                        geometry_type=geometry_type,
                        size=SimVec3(
                            x=asset.size[0],
                            y=asset.size[1],
                            z=asset.size[2],
                        ),
                    )
                )
                continue
            # Compatibility fallback for older scene assets that only carried a
            # URI/checksum.  New scene definitions should use typed geometry so
            # MuJoCo/Webots can bind explicit obstacle objects into their worlds.
            obstacles.append(
                SimSceneObstacle(
                    obstacle_id=asset.asset_id,
                    position=SimVec3(x=0.35 + (0.35 * index), y=0.0, z=0.35),
                    radius_m=0.08,
                    height_m=0.35,
                    geometry_type="cylinder",
                )
            )
        return tuple(obstacles)

    def _ensure_default_scene(self) -> None:
        default_ref = ResourceRef("minimal_scene", "0.1.0")
        if self.repository.get_scene(_scene_key(default_ref)) is not None:
            return
        scene = SceneProfilePayload(
            scene_ref=default_ref,
            name="Minimal local simulation scene",
            terrain_pack="flat",
            assets=(
                SceneAssetPayload(
                    asset_id="flat_ground",
                    asset_type="terrain",
                    uri="builtin://qrics/terrain/flat",
                    checksum="builtin-flat",
                ),
            ),
            sensor_profile=SensorProfilePayload(
                profile_id="minimal_contacts_imu",
                imu_enabled=True,
                foot_contact_enabled=True,
                sample_rate_hz=100,
            ),
            randomization_profile=RandomizationProfilePayload(),
            state="baseline",
            is_current_baseline=True,
            checksum=_scene_checksum(
                default_ref,
                "Minimal local simulation scene",
                "flat",
                (
                    SceneAssetPayload(
                        asset_id="flat_ground",
                        asset_type="terrain",
                        uri="builtin://qrics/terrain/flat",
                        checksum="builtin-flat",
                    ),
                ),
                SensorProfilePayload(
                    profile_id="minimal_contacts_imu",
                    imu_enabled=True,
                    foot_contact_enabled=True,
                    sample_rate_hz=100,
                ),
                RandomizationProfilePayload(),
            ),
            change_summary="seeded default scene",
        )
        self.repository.save_scene(scene)

    def _require_permission(
        self,
        context: RequestContext,
        permission: str,
        audit_action: str,
        object_ref: ResourceRef | None = None,
    ) -> ApiResponse | None:
        decision = authorize(context, permission)
        if decision.allowed:
            return None
        self._append_audit(
            context,
            audit_action,
            object_ref or ResourceRef("*"),
            "denied",
            decision.message,
        )
        return forbidden(context, decision.message)

    def _require_high_risk_reason(
        self,
        context: RequestContext,
        action: str,
        object_ref: ResourceRef,
        reason: str,
    ) -> ApiResponse | None:
        operation = high_risk_operation(action)
        if operation is None:
            return self._require_permission(context, action, action, object_ref)

        denied = self._require_permission(context, operation.permission, action, object_ref)
        if denied is not None:
            return denied

        if operation.reason_required and not reason.strip():
            self._append_audit(
                context,
                action,
                object_ref,
                "rejected",
                "reason is required for high-risk operation",
            )
            return invalid_request(context, f"reason is required for {action}", "reason")
        return None

    def _append_audit(
        self,
        context: RequestContext,
        action: str,
        object_ref: ResourceRef,
        result: str,
        reason: str,
    ) -> None:
        record = AuditRecordResponse(
            audit_id=f"audit_{self.repository.count_audit_records() + 1}",
            actor_id=context.actor_id,
            actor_role=context.role,
            action=action,
            object_ref=object_ref,
            result=result,
            reason=reason,
            request_id=context.request_id,
            timestamp_ns=time.time_ns(),
        )
        self.repository.append_audit(record)
        self._append_event(
            topic="audit.record",
            request_id=context.request_id,
            message=f"Audit recorded: {action}",
            payload=record.to_json(),
        )

    def _append_event(
        self,
        *,
        topic: EventTopic,
        request_id: str,
        message: str,
        run_id: str = "",
        payload: JsonDict | None = None,
    ) -> EventEnvelope:
        event = EventEnvelope(
            event_id=f"event_{self.repository.count_events() + 1}",
            topic=topic,
            run_id=run_id,
            message=message,
            payload=payload or {},
            request_id=request_id,
            timestamp_ns=time.time_ns(),
        )
        self.repository.append_event(event)
        self.event_stream.append_envelope(event)
        return event


def create_demo_app(repository: QricsRepository | None = None) -> QricsApiApp:
    return QricsApiApp(repository=repository or InMemoryRepository())


def _render_evaluation_report_export(
    *,
    report: EvaluationReportResponse,
    approval: PolicyApprovalResponse | None,
    report_format: str,
    generated_by: str,
    request_id: str,
) -> str:
    approval_json = approval.to_json() if approval is not None else {}
    payload = {
        "evaluation": report.to_json(),
        "approval": approval_json,
        "generated_by": generated_by,
        "request_id": request_id,
        "schema": "qrics.evaluation_report_export.v1",
    }
    if report_format == "json":
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    metrics = report.metrics
    approval_line = "none"
    if approval is not None:
        approval_line = f"{approval.decision} by {approval.approver_id} ({approval.approver_role})"
    return (
        f"# QRICS Evaluation Report {report.evaluation_id}\n\n"
        f"- Policy: {report.policy_ref.id}:{report.policy_ref.version}\n"
        f"- Scene: {report.scene_ref.id}:{report.scene_ref.version}\n"
        f"- Suite: {report.suite_id}\n"
        f"- Decision: {report.decision}\n"
        f"- Reason: {report.reason}\n"
        f"- Approval: {approval_line}\n"
        f"- Success rate: {metrics.success_rate:.3f}\n"
        f"- Collision rate: {metrics.collision_rate:.3f}\n"
        f"- Tracking error m: {metrics.tracking_error_m:.3f}\n"
        f"- Recovery rate: {metrics.recovery_rate:.3f}\n"
        f"- Energy proxy: {metrics.energy_proxy:.3f}\n"
        f"- Hard constraint violations: {metrics.hard_constraint_violation_count}\n"
        f"- Baseline policy: {report.baseline_policy_ref.id}:{report.baseline_policy_ref.version}\n"
        f"- Replay run: {report.replay_run_id or 'none'}\n"
        f"- Generated by: {generated_by}\n"
        f"- Request id: {request_id}\n"
    )


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
    state: TaskApiState,
    repository: QricsRepository,
) -> JsonDict:
    events = repository.list_task_events(task_id)
    response = TaskLifecycleResponse(
        task_id=task_id,
        state=state,
        event_count=len(events),
        latest_event=events[-1] if events else "",
    )
    return response.to_json()


def _policy_key(policy_ref: ResourceRef) -> str:
    return f"{policy_ref.id}:{policy_ref.version}"


_ALLOWED_TERRAIN_PACKS = frozenset({"flat", "slope", "gravel", "stairs", "low_friction", "mixed"})


def _scene_key(scene_ref: ResourceRef) -> str:
    return f"{scene_ref.id}:{scene_ref.version}"


def _validate_scene_payload(payload: SceneCreatePayload) -> tuple[str, ...]:
    errors: list[str] = []
    if payload.terrain_pack not in _ALLOWED_TERRAIN_PACKS:
        errors.append(f"terrain_pack must be one of {sorted(_ALLOWED_TERRAIN_PACKS)}")
    asset_ids: set[str] = set()
    for asset in payload.assets:
        if not asset.asset_id.strip():
            errors.append("asset_id must not be empty")
        if asset.asset_id in asset_ids:
            errors.append(f"duplicate asset_id: {asset.asset_id}")
        asset_ids.add(asset.asset_id)
        if (
            asset.required
            and (not asset.uri.strip() or asset.uri.startswith("missing:"))
            and not _asset_has_inline_geometry(asset)
        ):
            errors.append(f"asset dependency missing: {asset.asset_id}")
        if asset.geometry_type not in {"none", "sphere", "box", "cylinder"}:
            errors.append(
                f"unsupported geometry_type for asset {asset.asset_id}: {asset.geometry_type}"
            )
        if any(value < 0.0 for value in asset.size):
            errors.append(f"asset size must be non-negative: {asset.asset_id}")
        if asset.radius_m < 0.0 or asset.height_m < 0.0:
            errors.append(f"asset radius_m/height_m must be non-negative: {asset.asset_id}")
        if asset.asset_type == "obstacle" and asset.geometry_type != "none":
            if asset.radius_m <= 0.0 and asset.size == (0.0, 0.0, 0.0):
                errors.append(f"obstacle geometry requires radius_m or size: {asset.asset_id}")
            if asset.height_m <= 0.0 and asset.size == (0.0, 0.0, 0.0):
                errors.append(f"obstacle geometry requires height_m or size: {asset.asset_id}")
    if payload.sensor_profile.sample_rate_hz <= 0 or payload.sensor_profile.sample_rate_hz > 1000:
        errors.append("sensor sample_rate_hz must be within 1..1000")
    if payload.sensor_profile.noise_std < 0.0:
        errors.append("sensor noise_std must be non-negative")
    friction_min, friction_max = payload.randomization_profile.friction_range
    if friction_min <= 0.0 or friction_max <= 0.0 or friction_min > friction_max:
        errors.append("friction_range must be positive and ordered")
    mass_min, mass_max = payload.randomization_profile.mass_scale_range
    if mass_min <= 0.0 or mass_max <= 0.0 or mass_min > mass_max:
        errors.append("mass_scale_range must be positive and ordered")
    if payload.randomization_profile.sensor_noise_std < 0.0:
        errors.append("randomization sensor_noise_std must be non-negative")
    return tuple(errors)


def _asset_has_inline_geometry(asset: SceneAssetPayload) -> bool:
    return (
        asset.geometry_type != "none"
        or asset.radius_m > 0.0
        or asset.height_m > 0.0
        or asset.size != (0.0, 0.0, 0.0)
        or asset.position != (0.0, 0.0, 0.0)
    )


def _validate_training_plan(payload: TrainingPlanPayload) -> str:
    if not payload.training_id.strip():
        return "training_id must not be empty"
    if not payload.algorithm.strip():
        return "algorithm must not be empty"
    if payload.max_iterations <= 0:
        return "max_iterations must be positive"
    if payload.num_envs <= 0:
        return "num_envs must be positive"
    if payload.checkpoint_interval <= 0:
        return "checkpoint_interval must be positive"
    if payload.resource_quota.gpu_count < 0:
        return "resource_quota.gpu_count must be non-negative"
    if payload.resource_quota.cpu_threads <= 0:
        return "resource_quota.cpu_threads must be positive"
    if payload.resource_quota.memory_gb <= 0.0:
        return "resource_quota.memory_gb must be positive"
    if payload.resource_quota.max_runtime_s <= 0:
        return "resource_quota.max_runtime_s must be positive"
    return ""


def _training_config_hash(payload: TrainingPlanPayload) -> str:
    canonical = json.dumps(
        payload.to_config_json(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_metrics(metrics: MetricSummaryPayload) -> str:
    bounded = {
        "success_rate": metrics.success_rate,
        "collision_rate": metrics.collision_rate,
        "recovery_rate": metrics.recovery_rate,
    }
    for name, value in bounded.items():
        if value < 0.0 or value > 1.0:
            return f"{name} must be within 0..1"
    if metrics.tracking_error_m < 0.0:
        return "tracking_error_m must be non-negative"
    if metrics.energy_proxy < 0.0:
        return "energy_proxy must be non-negative"
    if metrics.hard_constraint_violation_count < 0:
        return "hard_constraint_violation_count must be non-negative"
    return ""


def _evaluate_gate(metrics: MetricSummaryPayload) -> tuple[GateDecision, str]:
    if metrics.hard_constraint_violation_count != 0:
        return "failed", "hard constraint violations must be zero"
    if metrics.success_rate < 0.8:
        return "failed", "success_rate is below 0.80 gate threshold"
    if metrics.collision_rate > 0.05:
        return "failed", "collision_rate exceeds 0.05 gate threshold"
    if metrics.tracking_error_m > 0.30:
        return "failed", "tracking_error_m exceeds 0.30 gate threshold"
    return "passed", "standard gate thresholds satisfied"


def _current_baseline_policy(
    policies: tuple[PolicyStateResponse, ...],
) -> PolicyStateResponse | None:
    for policy in policies:
        if policy.is_current_baseline:
            return policy
    return None


def _policy_metrics_or_default(policy: PolicyStateResponse | None) -> MetricSummaryPayload:
    if policy is None:
        return MetricSummaryPayload(0.0, 1.0, 999.0, 0.0, 0.0, 999)
    return policy.metrics


def _baseline_diff(
    metrics: MetricSummaryPayload,
    baseline_metrics: MetricSummaryPayload,
) -> JsonDict:
    return {
        "success_rate_delta": metrics.success_rate - baseline_metrics.success_rate,
        "collision_rate_delta": metrics.collision_rate - baseline_metrics.collision_rate,
        "tracking_error_m_delta": metrics.tracking_error_m - baseline_metrics.tracking_error_m,
        "recovery_rate_delta": metrics.recovery_rate - baseline_metrics.recovery_rate,
        "energy_proxy_delta": metrics.energy_proxy - baseline_metrics.energy_proxy,
        "hard_constraint_violation_count_delta": (
            metrics.hard_constraint_violation_count
            - baseline_metrics.hard_constraint_violation_count
        ),
    }


def _scene_checksum(
    scene_ref: ResourceRef,
    name: str,
    terrain_pack: str,
    assets: tuple[SceneAssetPayload, ...],
    sensor_profile: SensorProfilePayload,
    randomization_profile: RandomizationProfilePayload,
) -> str:
    payload = {
        "scene_id": scene_ref.id,
        "scene_version": scene_ref.version,
        "name": name,
        "terrain_pack": terrain_pack,
        "assets": [asset.to_json() for asset in assets],
        "sensor_profile": sensor_profile.to_json(),
        "randomization_profile": randomization_profile.to_json(),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
