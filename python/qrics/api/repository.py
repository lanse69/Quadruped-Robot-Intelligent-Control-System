"""Repository contracts and in-memory implementation for QRICS API state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from qrics.api.schemas import (
    AuditQuery,
    AuditRecordResponse,
    ControlStatusResponse,
    EventEnvelope,
    EventTopic,
    PolicyStateResponse,
    ReplayResponse,
    TaskPreviewResponse,
    TrainingJobResponse,
)


class QricsRepository(Protocol):
    """Persistence boundary for API-facing QRICS state and evidence."""

    def count_tasks(self) -> int: ...

    def count_audit_records(self) -> int: ...

    def count_events(self) -> int: ...

    def save_task(self, task: TaskPreviewResponse) -> None: ...

    def get_task(self, task_id: str) -> TaskPreviewResponse | None: ...

    def append_task_event(self, task_id: str, event_name: str) -> None: ...

    def list_task_events(self, task_id: str) -> tuple[str, ...]: ...

    def save_control(self, status: ControlStatusResponse) -> None: ...

    def get_control(self, run_id: str) -> ControlStatusResponse | None: ...

    def save_training_job(self, job: TrainingJobResponse) -> None: ...

    def get_training_job(self, job_id: str) -> TrainingJobResponse | None: ...

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
    task_events: dict[str, list[str]] = field(default_factory=dict)
    controls: dict[str, ControlStatusResponse] = field(default_factory=dict)
    training_jobs: dict[str, TrainingJobResponse] = field(default_factory=dict)
    policies: dict[str, PolicyStateResponse] = field(default_factory=dict)
    gate_passed: set[str] = field(default_factory=set)
    replays: dict[str, ReplayResponse] = field(default_factory=dict)
    audit_records: list[AuditRecordResponse] = field(default_factory=list)
    events: list[EventEnvelope] = field(default_factory=list)

    def count_tasks(self) -> int:
        return len(self.tasks)

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

    def save_control(self, status: ControlStatusResponse) -> None:
        self.controls[status.run_id] = status

    def get_control(self, run_id: str) -> ControlStatusResponse | None:
        return self.controls.get(run_id)

    def save_training_job(self, job: TrainingJobResponse) -> None:
        self.training_jobs[job.job_id] = job

    def get_training_job(self, job_id: str) -> TrainingJobResponse | None:
        return self.training_jobs.get(job_id)

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
