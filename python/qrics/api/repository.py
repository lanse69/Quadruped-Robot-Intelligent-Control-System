"""Repository contracts and in-memory implementation for QRICS API state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from qrics.api.schemas import (
    AuditQuery,
    AuditRecordResponse,
    ControlStatusResponse,
    EvaluationReportExportResponse,
    EvaluationReportResponse,
    EventEnvelope,
    EventTopic,
    PolicyApprovalResponse,
    PolicyStateResponse,
    ReplayResponse,
    ResourceRef,
    SceneProfilePayload,
    TaskPreviewResponse,
    TrainingJobResponse,
)


class QricsRepository(Protocol):
    """Persistence boundary for API-facing QRICS state and evidence."""

    def count_tasks(self) -> int: ...

    def count_scenes(self) -> int: ...

    def count_audit_records(self) -> int: ...

    def count_events(self) -> int: ...

    def save_task(self, task: TaskPreviewResponse) -> None: ...

    def get_task(self, task_id: str) -> TaskPreviewResponse | None: ...

    def append_task_event(self, task_id: str, event_name: str) -> None: ...

    def list_task_events(self, task_id: str) -> tuple[str, ...]: ...

    def save_scene(self, scene: SceneProfilePayload) -> None: ...

    def get_scene(self, scene_key: str) -> SceneProfilePayload | None: ...

    def list_scenes(self, scene_id: str = "") -> tuple[SceneProfilePayload, ...]: ...

    def save_control(self, status: ControlStatusResponse) -> None: ...

    def get_control(self, run_id: str) -> ControlStatusResponse | None: ...

    def save_training_job(self, job: TrainingJobResponse) -> None: ...

    def get_training_job(self, job_id: str) -> TrainingJobResponse | None: ...

    def list_training_jobs(self) -> tuple[TrainingJobResponse, ...]: ...

    def save_evaluation_report(self, report: EvaluationReportResponse) -> None: ...

    def get_evaluation_report(self, evaluation_id: str) -> EvaluationReportResponse | None: ...

    def list_evaluation_reports(self) -> tuple[EvaluationReportResponse, ...]: ...

    def save_evaluation_report_export(
        self, export: EvaluationReportExportResponse, content: str
    ) -> EvaluationReportExportResponse: ...

    def get_evaluation_report_export(
        self, export_id: str
    ) -> EvaluationReportExportResponse | None: ...

    def list_evaluation_report_exports(
        self, evaluation_id: str = ""
    ) -> tuple[EvaluationReportExportResponse, ...]: ...

    def save_policy_approval(self, approval: PolicyApprovalResponse) -> None: ...

    def latest_policy_approval(self, policy_key: str) -> PolicyApprovalResponse | None: ...

    def list_policy_approvals(self, policy_key: str = "") -> tuple[PolicyApprovalResponse, ...]: ...

    def save_policy(self, policy: PolicyStateResponse) -> None: ...

    def get_policy(self, policy_key: str) -> PolicyStateResponse | None: ...

    def list_policies(self) -> tuple[PolicyStateResponse, ...]: ...

    def set_gate_passed(self, policy_key: str, passed: bool) -> None: ...

    def has_gate_passed(self, policy_key: str) -> bool: ...

    def save_replay(self, replay: ReplayResponse) -> ReplayResponse: ...

    def get_replay(self, run_id: str) -> ReplayResponse | None: ...

    def append_audit(self, record: AuditRecordResponse) -> None: ...

    def query_audit(self, query: AuditQuery) -> tuple[AuditRecordResponse, ...]: ...

    def append_event(self, event: EventEnvelope) -> None: ...

    def query_events(
        self,
        *,
        topic: EventTopic | None = None,
        run_id: str = "",
        request_id: str = "",
    ) -> tuple[EventEnvelope, ...]: ...

    def close(self) -> None: ...


@dataclass
class InMemoryRepository:
    """Repository implementation for tests and single-process demo runs."""

    tasks: dict[str, TaskPreviewResponse] = field(default_factory=dict)
    scenes: dict[str, SceneProfilePayload] = field(default_factory=dict)
    task_events: dict[str, list[str]] = field(default_factory=dict)
    controls: dict[str, ControlStatusResponse] = field(default_factory=dict)
    training_jobs: dict[str, TrainingJobResponse] = field(default_factory=dict)
    evaluation_reports: dict[str, EvaluationReportResponse] = field(default_factory=dict)
    evaluation_report_exports: dict[str, EvaluationReportExportResponse] = field(
        default_factory=dict
    )
    evaluation_report_export_content: dict[str, str] = field(default_factory=dict)
    policy_approvals: list[PolicyApprovalResponse] = field(default_factory=list)
    policies: dict[str, PolicyStateResponse] = field(default_factory=dict)
    gate_passed: set[str] = field(default_factory=set)
    replays: dict[str, ReplayResponse] = field(default_factory=dict)
    audit_records: list[AuditRecordResponse] = field(default_factory=list)
    events: list[EventEnvelope] = field(default_factory=list)

    def count_tasks(self) -> int:
        return len(self.tasks)

    def count_scenes(self) -> int:
        return len(self.scenes)

    def count_audit_records(self) -> int:
        return len(self.audit_records)

    def count_events(self) -> int:
        return len(self.events)

    def save_task(self, task: TaskPreviewResponse) -> None:
        self.tasks[task.task_id] = task

    def get_task(self, task_id: str) -> TaskPreviewResponse | None:
        return self.tasks.get(task_id)

    def append_task_event(self, task_id: str, event_name: str) -> None:
        self.task_events.setdefault(task_id, []).append(event_name)

    def list_task_events(self, task_id: str) -> tuple[str, ...]:
        return tuple(self.task_events.get(task_id, ()))

    def save_scene(self, scene: SceneProfilePayload) -> None:
        self.scenes[_scene_key(scene.scene_ref.id, scene.scene_ref.version)] = scene

    def get_scene(self, scene_key: str) -> SceneProfilePayload | None:
        return self.scenes.get(scene_key)

    def list_scenes(self, scene_id: str = "") -> tuple[SceneProfilePayload, ...]:
        rows = list(self.scenes.values())
        if scene_id:
            rows = [scene for scene in rows if scene.scene_ref.id == scene_id]
        return tuple(sorted(rows, key=lambda item: (item.scene_ref.id, item.scene_ref.version)))

    def save_control(self, status: ControlStatusResponse) -> None:
        self.controls[status.run_id] = status

    def get_control(self, run_id: str) -> ControlStatusResponse | None:
        return self.controls.get(run_id)

    def save_training_job(self, job: TrainingJobResponse) -> None:
        self.training_jobs[job.job_id] = job

    def get_training_job(self, job_id: str) -> TrainingJobResponse | None:
        return self.training_jobs.get(job_id)

    def list_training_jobs(self) -> tuple[TrainingJobResponse, ...]:
        return tuple(sorted(self.training_jobs.values(), key=lambda item: item.job_id))

    def save_evaluation_report(self, report: EvaluationReportResponse) -> None:
        self.evaluation_reports[report.evaluation_id] = report

    def get_evaluation_report(self, evaluation_id: str) -> EvaluationReportResponse | None:
        return self.evaluation_reports.get(evaluation_id)

    def list_evaluation_reports(self) -> tuple[EvaluationReportResponse, ...]:
        return tuple(sorted(self.evaluation_reports.values(), key=lambda item: item.evaluation_id))

    def save_evaluation_report_export(
        self, export: EvaluationReportExportResponse, content: str
    ) -> EvaluationReportExportResponse:
        import hashlib

        blob = content.encode("utf-8")
        checksum = f"sha256:{hashlib.sha256(blob).hexdigest()}"
        stored = EvaluationReportExportResponse(
            export_id=export.export_id,
            evaluation_id=export.evaluation_id,
            report_format=export.report_format,
            uri=export.uri or f"memory://evaluation_report/{export.export_id}",
            checksum=checksum,
            size_bytes=len(blob),
            generated_by=export.generated_by,
            request_id=export.request_id,
            timestamp_ns=export.timestamp_ns,
            summary=export.summary,
        )
        self.evaluation_report_exports[stored.export_id] = stored
        self.evaluation_report_export_content[stored.export_id] = content
        return stored

    def get_evaluation_report_export(self, export_id: str) -> EvaluationReportExportResponse | None:
        return self.evaluation_report_exports.get(export_id)

    def list_evaluation_report_exports(
        self, evaluation_id: str = ""
    ) -> tuple[EvaluationReportExportResponse, ...]:
        rows = list(self.evaluation_report_exports.values())
        if evaluation_id:
            rows = [row for row in rows if row.evaluation_id == evaluation_id]
        return tuple(sorted(rows, key=lambda item: item.export_id))

    def save_policy_approval(self, approval: PolicyApprovalResponse) -> None:
        self.policy_approvals.append(approval)

    def latest_policy_approval(self, policy_key: str) -> PolicyApprovalResponse | None:
        rows = [
            row for row in self.policy_approvals if _policy_ref_key(row.policy_ref) == policy_key
        ]
        if not rows:
            return None
        return max(rows, key=lambda item: (item.timestamp_ns, item.approval_id))

    def list_policy_approvals(self, policy_key: str = "") -> tuple[PolicyApprovalResponse, ...]:
        rows = list(self.policy_approvals)
        if policy_key:
            rows = [row for row in rows if _policy_ref_key(row.policy_ref) == policy_key]
        return tuple(sorted(rows, key=lambda item: (item.timestamp_ns, item.approval_id)))

    def save_policy(self, policy: PolicyStateResponse) -> None:
        self.policies[_policy_key(policy)] = policy

    def get_policy(self, policy_key: str) -> PolicyStateResponse | None:
        return self.policies.get(policy_key)

    def list_policies(self) -> tuple[PolicyStateResponse, ...]:
        return tuple(self.policies.values())

    def set_gate_passed(self, policy_key: str, passed: bool) -> None:
        if passed:
            self.gate_passed.add(policy_key)
        else:
            self.gate_passed.discard(policy_key)

    def has_gate_passed(self, policy_key: str) -> bool:
        return policy_key in self.gate_passed

    def save_replay(self, replay: ReplayResponse) -> ReplayResponse:
        self.replays[replay.run_id] = replay
        return replay

    def get_replay(self, run_id: str) -> ReplayResponse | None:
        return self.replays.get(run_id)

    def append_audit(self, record: AuditRecordResponse) -> None:
        self.audit_records.append(record)

    def query_audit(self, query: AuditQuery) -> tuple[AuditRecordResponse, ...]:
        rows = self.audit_records
        if query.actor_id:
            rows = [row for row in rows if row.actor_id == query.actor_id]
        if query.object_id:
            rows = [row for row in rows if row.object_ref.id == query.object_id]
        if query.action:
            rows = [row for row in rows if row.action == query.action]
        return tuple(rows)

    def append_event(self, event: EventEnvelope) -> None:
        self.events.append(event)

    def query_events(
        self,
        *,
        topic: EventTopic | None = None,
        run_id: str = "",
        request_id: str = "",
    ) -> tuple[EventEnvelope, ...]:
        rows = self.events
        if topic is not None:
            rows = [event for event in rows if event.topic == topic]
        if run_id:
            rows = [event for event in rows if event.run_id == run_id]
        if request_id:
            rows = [event for event in rows if event.request_id == request_id]
        return tuple(rows)

    def close(self) -> None:
        return None


def _policy_key(policy: PolicyStateResponse) -> str:
    return f"{policy.policy_ref.id}:{policy.policy_ref.version}"


def _scene_key(scene_id: str, version: str) -> str:
    return f"{scene_id}:{version}"


def _policy_ref_key(policy_ref: ResourceRef) -> str:
    return f"{policy_ref.id}:{policy_ref.version}"
