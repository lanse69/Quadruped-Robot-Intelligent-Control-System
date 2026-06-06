"""SQLite-backed QRICS API repository."""

from __future__ import annotations

import functools
import json
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any, TypeVar, cast

from qrics.api.repository import QricsRepository
from qrics.api.schemas import (
    ApiRole,
    ApprovalDecision,
    AuditQuery,
    AuditRecordResponse,
    ControlApiState,
    ControlStatusResponse,
    EvaluationReportExportResponse,
    EvaluationReportResponse,
    EventEnvelope,
    EventTopic,
    GateDecision,
    MetricSummaryPayload,
    PolicyApiStage,
    PolicyApprovalResponse,
    PolicyStateResponse,
    RandomizationProfilePayload,
    ReplayResponse,
    ReportExportFormat,
    ResourceRef,
    SceneApiState,
    SceneAssetPayload,
    SceneAssetType,
    SceneGeometryType,
    SceneProfilePayload,
    SensorProfilePayload,
    TaskApiState,
    TaskPreviewResponse,
    TrainingJobResponse,
    TrainingJobState,
    TrainingResourceQuotaPayload,
    WaypointView,
)
from qrics.storage.object_store import FileObjectStore

JsonPayload = dict[str, Any]

F = TypeVar("F", bound=Callable[..., Any])


def _locked(method: F) -> F:
    """Run repository operations under the SQLite connection lock.

    FastAPI executes synchronous route handlers in a worker-thread pool. A
    repository instance is held on application state, so a single SQLite
    connection can be touched by multiple worker threads during the web-console
    session. The lock serializes access to the shared connection and keeps a
    transaction block, nested helper call, and cursor read on the same guarded
    path.
    """

    @functools.wraps(method)
    def wrapper(self: SQLiteQricsRepository, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return method(self, *args, **kwargs)

    return cast(F, wrapper)


class SQLiteQricsRepository(QricsRepository):
    """Repository that persists metadata in SQLite and replay manifests as files."""

    def __init__(self, db_path: str | Path, object_store: FileObjectStore | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.object_store = object_store
        self._lock = RLock()
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    @_locked
    def count_tasks(self) -> int:
        return self._count("tasks")

    @_locked
    def count_scenes(self) -> int:
        return self._count("scenes")

    @_locked
    def count_audit_records(self) -> int:
        return self._count("audit_log")

    @_locked
    def count_events(self) -> int:
        return self._count("events")

    @_locked
    def save_task(self, task: TaskPreviewResponse) -> None:
        payload = _task_to_payload(task)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO tasks(task_id, state, payload_json)
                VALUES(?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                  state=excluded.state,
                  payload_json=excluded.payload_json
                """,
                (task.task_id, task.state, _dumps(payload)),
            )

    @_locked
    def get_task(self, task_id: str) -> TaskPreviewResponse | None:
        row = self.connection.execute(
            "SELECT payload_json FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return _task_from_payload(_loads(row["payload_json"]))

    @_locked
    def append_task_event(self, task_id: str, event_name: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO task_events(task_id, seq, event_name) VALUES(?, ?, ?)",
                (task_id, len(self.list_task_events(task_id)) + 1, event_name),
            )

    @_locked
    def list_task_events(self, task_id: str) -> tuple[str, ...]:
        rows = self.connection.execute(
            "SELECT event_name FROM task_events WHERE task_id = ? ORDER BY seq",
            (task_id,),
        ).fetchall()
        return tuple(str(row["event_name"]) for row in rows)

    @_locked
    def save_scene(self, scene: SceneProfilePayload) -> None:
        key = _scene_key(scene)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO scenes(scene_key, scene_id, scene_version, state,
                                   is_current_baseline, checksum, payload_json)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scene_key) DO UPDATE SET
                  state=excluded.state,
                  is_current_baseline=excluded.is_current_baseline,
                  checksum=excluded.checksum,
                  payload_json=excluded.payload_json
                """,
                (
                    key,
                    scene.scene_ref.id,
                    scene.scene_ref.version,
                    scene.state,
                    1 if scene.is_current_baseline else 0,
                    scene.checksum,
                    _dumps(_scene_to_payload(scene)),
                ),
            )

    @_locked
    def get_scene(self, scene_key: str) -> SceneProfilePayload | None:
        row = self.connection.execute(
            "SELECT payload_json FROM scenes WHERE scene_key = ?",
            (scene_key,),
        ).fetchone()
        if row is None:
            return None
        return _scene_from_payload(_loads(row["payload_json"]))

    @_locked
    def list_scenes(self, scene_id: str = "") -> tuple[SceneProfilePayload, ...]:
        if scene_id:
            rows = self.connection.execute(
                """
                SELECT payload_json FROM scenes
                WHERE scene_id = ?
                ORDER BY scene_id, scene_version
                """,
                (scene_id,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload_json FROM scenes ORDER BY scene_id, scene_version"
            ).fetchall()
        return tuple(_scene_from_payload(_loads(row["payload_json"])) for row in rows)

    @_locked
    def save_control(self, status: ControlStatusResponse) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO controls(run_id, state, payload_json)
                VALUES(?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  state=excluded.state,
                  payload_json=excluded.payload_json
                """,
                (status.run_id, status.state, _dumps(_control_to_payload(status))),
            )

    @_locked
    def get_control(self, run_id: str) -> ControlStatusResponse | None:
        row = self.connection.execute(
            "SELECT payload_json FROM controls WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return _control_from_payload(_loads(row["payload_json"]))

    @_locked
    def save_training_job(self, job: TrainingJobResponse) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO training_jobs(job_id, state, payload_json)
                VALUES(?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  state=excluded.state,
                  payload_json=excluded.payload_json
                """,
                (job.job_id, job.state, _dumps(_training_job_to_payload(job))),
            )

    @_locked
    def get_training_job(self, job_id: str) -> TrainingJobResponse | None:
        row = self.connection.execute(
            "SELECT payload_json FROM training_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return _training_job_from_payload(_loads(row["payload_json"]))

    @_locked
    def list_training_jobs(self) -> tuple[TrainingJobResponse, ...]:
        rows = self.connection.execute(
            "SELECT payload_json FROM training_jobs ORDER BY job_id"
        ).fetchall()
        return tuple(_training_job_from_payload(_loads(row["payload_json"])) for row in rows)

    @_locked
    def save_evaluation_report(self, report: EvaluationReportResponse) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO evaluation_reports(evaluation_id, policy_key, decision, payload_json)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(evaluation_id) DO UPDATE SET
                  policy_key=excluded.policy_key,
                  decision=excluded.decision,
                  payload_json=excluded.payload_json
                """,
                (
                    report.evaluation_id,
                    f"{report.policy_ref.id}:{report.policy_ref.version}",
                    report.decision,
                    _dumps(_evaluation_report_to_payload(report)),
                ),
            )

    @_locked
    def get_evaluation_report(self, evaluation_id: str) -> EvaluationReportResponse | None:
        row = self.connection.execute(
            "SELECT payload_json FROM evaluation_reports WHERE evaluation_id = ?",
            (evaluation_id,),
        ).fetchone()
        if row is None:
            return None
        return _evaluation_report_from_payload(_loads(row["payload_json"]))

    @_locked
    def list_evaluation_reports(self) -> tuple[EvaluationReportResponse, ...]:
        rows = self.connection.execute(
            "SELECT payload_json FROM evaluation_reports ORDER BY evaluation_id"
        ).fetchall()
        return tuple(_evaluation_report_from_payload(_loads(row["payload_json"])) for row in rows)

    @_locked
    def save_evaluation_report_export(
        self, export: EvaluationReportExportResponse, content: str
    ) -> EvaluationReportExportResponse:
        stored = export
        if self.object_store is not None:
            suffix = ".md" if export.report_format == "markdown" else ".json"
            ref = self.object_store.put_text(
                "evaluation_report", export.export_id, content, suffix=suffix
            )
            stored = replace(
                export,
                uri=ref.uri,
                checksum=ref.checksum,
                size_bytes=ref.size_bytes,
            )
        else:
            import hashlib

            blob = content.encode("utf-8")
            stored = replace(
                export,
                uri=export.uri or f"sqlite://evaluation_report/{export.export_id}",
                checksum=f"sha256:{hashlib.sha256(blob).hexdigest()}",
                size_bytes=len(blob),
            )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO evaluation_report_exports(
                  export_id, evaluation_id, report_format, uri, checksum, size_bytes,
                  timestamp_ns, payload_json, content_text
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(export_id) DO UPDATE SET
                  evaluation_id=excluded.evaluation_id,
                  report_format=excluded.report_format,
                  uri=excluded.uri,
                  checksum=excluded.checksum,
                  size_bytes=excluded.size_bytes,
                  timestamp_ns=excluded.timestamp_ns,
                  payload_json=excluded.payload_json,
                  content_text=excluded.content_text
                """,
                (
                    stored.export_id,
                    stored.evaluation_id,
                    stored.report_format,
                    stored.uri,
                    stored.checksum,
                    stored.size_bytes,
                    stored.timestamp_ns,
                    _dumps(_evaluation_report_export_to_payload(stored)),
                    "" if self.object_store is not None else content,
                ),
            )
        return stored

    @_locked
    def get_evaluation_report_export(self, export_id: str) -> EvaluationReportExportResponse | None:
        row = self.connection.execute(
            "SELECT payload_json FROM evaluation_report_exports WHERE export_id = ?",
            (export_id,),
        ).fetchone()
        if row is None:
            return None
        return _evaluation_report_export_from_payload(_loads(row["payload_json"]))

    @_locked
    def list_evaluation_report_exports(
        self, evaluation_id: str = ""
    ) -> tuple[EvaluationReportExportResponse, ...]:
        if evaluation_id:
            rows = self.connection.execute(
                """
                SELECT payload_json FROM evaluation_report_exports
                WHERE evaluation_id = ?
                ORDER BY timestamp_ns, export_id
                """,
                (evaluation_id,),
            ).fetchall()
        else:
            rows = self.connection.execute("""
                SELECT payload_json FROM evaluation_report_exports
                ORDER BY timestamp_ns, export_id
                """).fetchall()
        return tuple(
            _evaluation_report_export_from_payload(_loads(row["payload_json"])) for row in rows
        )

    @_locked
    def save_policy_approval(self, approval: PolicyApprovalResponse) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO policy_approvals(approval_id, policy_key, evaluation_id, decision,
                                             timestamp_ns, payload_json)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(approval_id) DO UPDATE SET
                  policy_key=excluded.policy_key,
                  evaluation_id=excluded.evaluation_id,
                  decision=excluded.decision,
                  timestamp_ns=excluded.timestamp_ns,
                  payload_json=excluded.payload_json
                """,
                (
                    approval.approval_id,
                    _policy_ref_key(approval.policy_ref),
                    approval.evaluation_id,
                    approval.decision,
                    approval.timestamp_ns,
                    _dumps(_policy_approval_to_payload(approval)),
                ),
            )

    @_locked
    def latest_policy_approval(self, policy_key: str) -> PolicyApprovalResponse | None:
        row = self.connection.execute(
            """
            SELECT payload_json FROM policy_approvals
            WHERE policy_key = ?
            ORDER BY timestamp_ns DESC, approval_id DESC
            LIMIT 1
            """,
            (policy_key,),
        ).fetchone()
        if row is None:
            return None
        return _policy_approval_from_payload(_loads(row["payload_json"]))

    @_locked
    def list_policy_approvals(self, policy_key: str = "") -> tuple[PolicyApprovalResponse, ...]:
        if policy_key:
            rows = self.connection.execute(
                """
                SELECT payload_json FROM policy_approvals
                WHERE policy_key = ?
                ORDER BY timestamp_ns, approval_id
                """,
                (policy_key,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                "SELECT payload_json FROM policy_approvals ORDER BY timestamp_ns, approval_id"
            ).fetchall()
        return tuple(_policy_approval_from_payload(_loads(row["payload_json"])) for row in rows)

    @_locked
    def save_policy(self, policy: PolicyStateResponse) -> None:
        key = _policy_key(policy)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO policies(policy_key, policy_id, policy_version,
                                     stage, is_current_baseline, payload_json)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(policy_key) DO UPDATE SET
                  stage=excluded.stage,
                  is_current_baseline=excluded.is_current_baseline,
                  payload_json=excluded.payload_json
                """,
                (
                    key,
                    policy.policy_ref.id,
                    policy.policy_ref.version,
                    policy.stage,
                    1 if policy.is_current_baseline else 0,
                    _dumps(_policy_to_payload(policy)),
                ),
            )

    @_locked
    def get_policy(self, policy_key: str) -> PolicyStateResponse | None:
        row = self.connection.execute(
            "SELECT payload_json FROM policies WHERE policy_key = ?",
            (policy_key,),
        ).fetchone()
        if row is None:
            return None
        return _policy_from_payload(_loads(row["payload_json"]))

    @_locked
    def list_policies(self) -> tuple[PolicyStateResponse, ...]:
        rows = self.connection.execute(
            "SELECT payload_json FROM policies ORDER BY policy_key"
        ).fetchall()
        return tuple(_policy_from_payload(_loads(row["payload_json"])) for row in rows)

    @_locked
    def set_gate_passed(self, policy_key: str, passed: bool) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO gate_state(policy_key, passed)
                VALUES(?, ?)
                ON CONFLICT(policy_key) DO UPDATE SET passed=excluded.passed
                """,
                (policy_key, 1 if passed else 0),
            )

    @_locked
    def has_gate_passed(self, policy_key: str) -> bool:
        row = self.connection.execute(
            "SELECT passed FROM gate_state WHERE policy_key = ?",
            (policy_key,),
        ).fetchone()
        return row is not None and int(row["passed"]) == 1

    @_locked
    def save_replay(self, replay: ReplayResponse) -> ReplayResponse:
        stored = replay
        if self.object_store is not None:
            ref = self.object_store.put_json("replay_manifest", replay.run_id, replay.to_json())
            stored = replace(replay, manifest_uri=ref.uri, manifest_checksum=ref.checksum)
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO replays(run_id, payload_json, manifest_uri, manifest_checksum)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  payload_json=excluded.payload_json,
                  manifest_uri=excluded.manifest_uri,
                  manifest_checksum=excluded.manifest_checksum
                """,
                (
                    stored.run_id,
                    _dumps(_replay_to_payload(stored)),
                    stored.manifest_uri,
                    stored.manifest_checksum,
                ),
            )
        return stored

    @_locked
    def get_replay(self, run_id: str) -> ReplayResponse | None:
        row = self.connection.execute(
            "SELECT payload_json FROM replays WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return _replay_from_payload(_loads(row["payload_json"]))

    @_locked
    def append_audit(self, record: AuditRecordResponse) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO audit_log(audit_id, actor_id, actor_role, action, object_id,
                                      object_version, result, reason, request_id,
                                      timestamp_ns, payload_json)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.audit_id,
                    record.actor_id,
                    record.actor_role,
                    record.action,
                    record.object_ref.id,
                    record.object_ref.version,
                    record.result,
                    record.reason,
                    record.request_id,
                    record.timestamp_ns,
                    _dumps(_audit_to_payload(record)),
                ),
            )

    @_locked
    def query_audit(self, query: AuditQuery) -> tuple[AuditRecordResponse, ...]:
        clauses: list[str] = []
        params: list[str] = []
        if query.actor_id:
            clauses.append("actor_id = ?")
            params.append(query.actor_id)
        if query.object_id:
            clauses.append("object_id = ?")
            params.append(query.object_id)
        if query.action:
            clauses.append("action = ?")
            params.append(query.action)
        sql = "SELECT payload_json FROM audit_log"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp_ns, audit_id"
        rows = self.connection.execute(sql, tuple(params)).fetchall()
        return tuple(_audit_from_payload(_loads(row["payload_json"])) for row in rows)

    @_locked
    def append_event(self, event: EventEnvelope) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO events(event_id, topic, run_id, request_id, timestamp_ns, payload_json)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.topic,
                    event.run_id,
                    event.request_id,
                    event.timestamp_ns,
                    _dumps(_event_to_payload(event)),
                ),
            )

    @_locked
    def query_events(
        self,
        *,
        topic: EventTopic | None = None,
        run_id: str = "",
        request_id: str = "",
    ) -> tuple[EventEnvelope, ...]:
        clauses: list[str] = []
        params: list[str] = []
        if topic is not None:
            clauses.append("topic = ?")
            params.append(topic)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if request_id:
            clauses.append("request_id = ?")
            params.append(request_id)
        sql = "SELECT payload_json FROM events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY timestamp_ns, event_id"
        rows = self.connection.execute(sql, tuple(params)).fetchall()
        return tuple(_event_from_payload(_loads(row["payload_json"])) for row in rows)

    @_locked
    def close(self) -> None:
        self.connection.close()

    def _count(self, table_name: str) -> int:
        row = self.connection.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
        return int(row["count"])

    def _init_schema(self) -> None:
        with self.connection:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.executescript("""
                CREATE TABLE IF NOT EXISTS tasks(
                  task_id TEXT PRIMARY KEY,
                  state TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_events(
                  task_id TEXT NOT NULL,
                  seq INTEGER NOT NULL,
                  event_name TEXT NOT NULL,
                  PRIMARY KEY(task_id, seq)
                );
                CREATE TABLE IF NOT EXISTS scenes(
                  scene_key TEXT PRIMARY KEY,
                  scene_id TEXT NOT NULL,
                  scene_version TEXT NOT NULL,
                  state TEXT NOT NULL,
                  is_current_baseline INTEGER NOT NULL,
                  checksum TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_scenes_scene_id ON scenes(scene_id);
                CREATE INDEX IF NOT EXISTS idx_scenes_state ON scenes(state);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_scenes_current_baseline
                  ON scenes(scene_id, is_current_baseline)
                  WHERE is_current_baseline = 1;
                CREATE TABLE IF NOT EXISTS controls(
                  run_id TEXT PRIMARY KEY,
                  state TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS training_jobs(
                  job_id TEXT PRIMARY KEY,
                  state TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evaluation_reports(
                  evaluation_id TEXT PRIMARY KEY,
                  policy_key TEXT NOT NULL,
                  decision TEXT NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_evaluation_policy ON evaluation_reports(policy_key);
                CREATE INDEX IF NOT EXISTS idx_evaluation_decision ON evaluation_reports(decision);
                CREATE TABLE IF NOT EXISTS evaluation_report_exports(
                  export_id TEXT PRIMARY KEY,
                  evaluation_id TEXT NOT NULL,
                  report_format TEXT NOT NULL,
                  uri TEXT NOT NULL,
                  checksum TEXT NOT NULL,
                  size_bytes INTEGER NOT NULL,
                  timestamp_ns INTEGER NOT NULL,
                  payload_json TEXT NOT NULL,
                  content_text TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_report_exports_evaluation
                  ON evaluation_report_exports(evaluation_id);
                CREATE TABLE IF NOT EXISTS policy_approvals(
                  approval_id TEXT PRIMARY KEY,
                  policy_key TEXT NOT NULL,
                  evaluation_id TEXT NOT NULL,
                  decision TEXT NOT NULL,
                  timestamp_ns INTEGER NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_policy_approvals_policy
                  ON policy_approvals(policy_key);
                CREATE INDEX IF NOT EXISTS idx_policy_approvals_evaluation
                  ON policy_approvals(evaluation_id);
                CREATE TABLE IF NOT EXISTS policies(
                  policy_key TEXT PRIMARY KEY,
                  policy_id TEXT NOT NULL,
                  policy_version TEXT NOT NULL,
                  stage TEXT NOT NULL,
                  is_current_baseline INTEGER NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_policies_current_baseline
                  ON policies(is_current_baseline)
                  WHERE is_current_baseline = 1;
                CREATE TABLE IF NOT EXISTS gate_state(
                  policy_key TEXT PRIMARY KEY,
                  passed INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS replays(
                  run_id TEXT PRIMARY KEY,
                  payload_json TEXT NOT NULL,
                  manifest_uri TEXT NOT NULL DEFAULT '',
                  manifest_checksum TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS audit_log(
                  audit_id TEXT PRIMARY KEY,
                  actor_id TEXT NOT NULL,
                  actor_role TEXT NOT NULL,
                  action TEXT NOT NULL,
                  object_id TEXT NOT NULL,
                  object_version TEXT NOT NULL,
                  result TEXT NOT NULL,
                  reason TEXT NOT NULL,
                  request_id TEXT NOT NULL,
                  timestamp_ns INTEGER NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id);
                CREATE INDEX IF NOT EXISTS idx_audit_object ON audit_log(object_id);
                CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
                CREATE TABLE IF NOT EXISTS events(
                  event_id TEXT PRIMARY KEY,
                  topic TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  request_id TEXT NOT NULL,
                  timestamp_ns INTEGER NOT NULL,
                  payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id);
                CREATE INDEX IF NOT EXISTS idx_events_topic ON events(topic);
                CREATE INDEX IF NOT EXISTS idx_events_request_id ON events(request_id);
                """)


def _dumps(payload: JsonPayload) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(payload: str) -> JsonPayload:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("repository payload is not an object")
    return data


_TASK_API_STATES = frozenset({"preview_ready", "rejected", "confirmed", "handed_off", "cancelled"})
_CONTROL_API_STATES = frozenset(
    {"created", "running", "paused", "succeeded", "failed", "cancelled"}
)
_TRAINING_JOB_STATES = frozenset({"queued", "running", "succeeded", "failed", "cancelled"})
_POLICY_API_STAGES = frozenset(
    {
        "draft",
        "candidate",
        "gate_passed",
        "gate_failed",
        "approved",
        "released",
        "baseline",
        "archived",
    }
)
_SCENE_API_STATES = frozenset({"draft", "baseline", "archived"})
_SCENE_ASSET_TYPES = frozenset({"terrain", "obstacle", "checkpoint", "no_go_zone", "sensor_mount"})
_SCENE_GEOMETRY_TYPES = frozenset({"none", "sphere", "box", "cylinder"})
_API_ROLES = frozenset({"operator", "algorithm_engineer", "test_engineer", "admin", "auditor"})
_APPROVAL_DECISIONS = frozenset({"approved", "rejected"})
_REPORT_EXPORT_FORMATS = frozenset({"json", "markdown"})
_EVENT_TOPICS = frozenset(
    {
        "scene.lifecycle",
        "task.lifecycle",
        "control.status",
        "control.alert",
        "training.status",
        "policy.lifecycle",
        "replay.index",
        "report.export",
        "audit.record",
    }
)


def _required_literal(value: object, *, allowed: frozenset[str], field_name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"invalid {field_name}: {value!r}")
    return value


def _task_api_state(value: object) -> TaskApiState:
    return cast(
        TaskApiState,
        _required_literal(value, allowed=_TASK_API_STATES, field_name="task state"),
    )


def _control_api_state(value: object) -> ControlApiState:
    return cast(
        ControlApiState,
        _required_literal(value, allowed=_CONTROL_API_STATES, field_name="control state"),
    )


def _training_job_state(value: object) -> TrainingJobState:
    return cast(
        TrainingJobState,
        _required_literal(value, allowed=_TRAINING_JOB_STATES, field_name="training job state"),
    )


def _policy_api_stage(value: object) -> PolicyApiStage:
    return cast(
        PolicyApiStage,
        _required_literal(value, allowed=_POLICY_API_STAGES, field_name="policy stage"),
    )


def _scene_api_state(value: object) -> SceneApiState:
    return cast(
        SceneApiState,
        _required_literal(value, allowed=_SCENE_API_STATES, field_name="scene state"),
    )


def _scene_asset_type(value: object) -> SceneAssetType:
    return cast(
        SceneAssetType,
        _required_literal(value, allowed=_SCENE_ASSET_TYPES, field_name="scene asset type"),
    )


def _scene_geometry_type(value: object) -> SceneGeometryType:
    return cast(
        SceneGeometryType,
        _required_literal(value, allowed=_SCENE_GEOMETRY_TYPES, field_name="scene geometry type"),
    )


def _float_triplet(value: object) -> tuple[float, float, float]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        values = list(value)
        if len(values) == 3:
            return (float(values[0]), float(values[1]), float(values[2]))
    return (0.0, 0.0, 0.0)


def _api_role(value: object) -> ApiRole:
    return cast(
        ApiRole,
        _required_literal(value, allowed=_API_ROLES, field_name="actor role"),
    )


def _approval_decision(value: object) -> ApprovalDecision:
    return cast(
        ApprovalDecision,
        _required_literal(value, allowed=_APPROVAL_DECISIONS, field_name="approval decision"),
    )


def _report_export_format(value: object) -> ReportExportFormat:
    return cast(
        ReportExportFormat,
        _required_literal(value, allowed=_REPORT_EXPORT_FORMATS, field_name="report export format"),
    )


def _event_topic(value: object) -> EventTopic:
    return cast(
        EventTopic,
        _required_literal(value, allowed=_EVENT_TOPICS, field_name="event topic"),
    )


def _base_position(value: object) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"invalid base_position: {value!r}")
    if len(value) != 3:
        raise ValueError(f"base_position must contain exactly 3 values: {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))


def _task_to_payload(task: TaskPreviewResponse) -> JsonPayload:
    return {
        "task_id": task.task_id,
        "state": task.state,
        "goal": task.goal,
        "scene_id": task.scene_ref.id,
        "scene_version": task.scene_ref.version,
        "waypoints": [waypoint.__dict__ for waypoint in task.waypoints],
        "selected_policy_reason": task.selected_policy_reason,
        "risk_summary": task.risk_summary,
        "operator_action_required": task.operator_action_required,
    }


def _task_from_payload(payload: JsonPayload) -> TaskPreviewResponse:
    return TaskPreviewResponse(
        task_id=str(payload["task_id"]),
        state=_task_api_state(payload["state"]),
        goal=str(payload["goal"]),
        waypoints=tuple(WaypointView(**item) for item in payload.get("waypoints", [])),
        selected_policy_reason=str(payload["selected_policy_reason"]),
        risk_summary=str(payload["risk_summary"]),
        operator_action_required=bool(payload["operator_action_required"]),
        scene_ref=ResourceRef(
            str(payload.get("scene_id", "minimal_scene")),
            str(payload.get("scene_version", "0.1.0")),
        ),
    )


def _scene_to_payload(scene: SceneProfilePayload) -> JsonPayload:
    return scene.to_json()


def _scene_from_payload(payload: JsonPayload) -> SceneProfilePayload:
    sensor_raw = payload.get("sensor_profile", {})
    sensor = cast(JsonPayload, sensor_raw) if isinstance(sensor_raw, dict) else {}
    randomization_raw = payload.get("randomization_profile", {})
    randomization = (
        cast(JsonPayload, randomization_raw) if isinstance(randomization_raw, dict) else {}
    )
    return SceneProfilePayload(
        scene_ref=ResourceRef(str(payload["scene_id"]), str(payload.get("scene_version", ""))),
        name=str(payload.get("name", "")),
        terrain_pack=str(payload.get("terrain_pack", "flat")),
        assets=tuple(_scene_asset_from_payload(item) for item in payload.get("assets", [])),
        sensor_profile=_sensor_profile_from_payload(sensor),
        randomization_profile=_randomization_profile_from_payload(randomization),
        state=_scene_api_state(payload.get("state", "draft")),
        is_current_baseline=bool(payload.get("is_current_baseline", False)),
        checksum=str(payload.get("checksum", "")),
        change_summary=str(payload.get("change_summary", "")),
        validation_errors=tuple(str(item) for item in payload.get("validation_errors", [])),
    )


def _scene_asset_from_payload(payload: object) -> SceneAssetPayload:
    if not isinstance(payload, dict):
        raise ValueError("scene asset payload is not an object")
    return SceneAssetPayload(
        asset_id=str(payload.get("asset_id", "")),
        asset_type=_scene_asset_type(payload.get("asset_type", "terrain")),
        uri=str(payload.get("uri", "")),
        checksum=str(payload.get("checksum", "")),
        frame_id=str(payload.get("frame_id", "world")),
        required=bool(payload.get("required", True)),
        geometry_type=_scene_geometry_type(payload.get("geometry_type", "none")),
        position=_float_triplet(payload.get("position", (0.0, 0.0, 0.0))),
        size=_float_triplet(payload.get("size", (0.0, 0.0, 0.0))),
        radius_m=float(payload.get("radius_m", 0.0)),
        height_m=float(payload.get("height_m", 0.0)),
    )


def _sensor_profile_from_payload(payload: JsonPayload) -> SensorProfilePayload:
    return SensorProfilePayload(
        profile_id=str(payload.get("profile_id", "default_sensors")),
        camera_enabled=bool(payload.get("camera_enabled", False)),
        depth_camera_enabled=bool(payload.get("depth_camera_enabled", False)),
        lidar_enabled=bool(payload.get("lidar_enabled", False)),
        imu_enabled=bool(payload.get("imu_enabled", True)),
        foot_contact_enabled=bool(payload.get("foot_contact_enabled", True)),
        sample_rate_hz=int(payload.get("sample_rate_hz", 100)),
        noise_std=float(payload.get("noise_std", 0.0)),
        source_quality=str(payload.get("source_quality", "direct")),
    )


def _float_pair(value: object, default: tuple[float, float]) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return default
    if len(value) != 2:
        return default
    return (float(value[0]), float(value[1]))


def _randomization_profile_from_payload(payload: JsonPayload) -> RandomizationProfilePayload:
    return RandomizationProfilePayload(
        profile_id=str(payload.get("profile_id", "no_randomization")),
        enabled=bool(payload.get("enabled", False)),
        friction_range=_float_pair(payload.get("friction_range"), (1.0, 1.0)),
        mass_scale_range=_float_pair(payload.get("mass_scale_range"), (1.0, 1.0)),
        sensor_noise_std=float(payload.get("sensor_noise_std", 0.0)),
        seed=int(payload.get("seed", 42)),
    )


def _control_to_payload(status: ControlStatusResponse) -> JsonPayload:
    return status.to_json()


def _control_from_payload(payload: JsonPayload) -> ControlStatusResponse:
    return ControlStatusResponse(
        run_id=str(payload["run_id"]),
        state=_control_api_state(payload["state"]),
        current_node_id=str(payload.get("current_node_id", "")),
        completed_node_count=int(payload.get("completed_node_count", 0)),
        control_step_count=int(payload.get("control_step_count", 0)),
        risk_score=float(payload.get("risk_score", 0.0)),
        latest_action=str(payload.get("latest_action", "stop")),
        reason=str(payload.get("reason", "")),
        backend=str(payload.get("backend", "minimal")),
        runtime_profile=str(payload.get("runtime_profile", "headless_fast")),
        sim_time_ns=int(payload.get("sim_time_ns", 0)),
        base_position=_base_position(payload.get("base_position", (0.0, 0.0, 0.0))),
        observation_quality=str(payload.get("observation_quality", "estimated")),
        terrain_class=str(payload.get("terrain_class", "unknown")),
        obstacle_detected=bool(payload.get("obstacle_detected", False)),
        nearest_obstacle_distance_m=float(payload.get("nearest_obstacle_distance_m", 0.0)),
        safety_event_count=int(payload.get("safety_event_count", 0)),
        presentation_pid=int(payload.get("presentation_pid", 0)),
        presentation_log_path=str(payload.get("presentation_log_path", "")),
        presentation_workspace=str(payload.get("presentation_workspace", "")),
        presentation_command_dir=str(payload.get("presentation_command_dir", "")),
        presentation_command_path=str(payload.get("presentation_command_path", "")),
    )


def _training_job_to_payload(job: TrainingJobResponse) -> JsonPayload:
    return job.to_json()


def _training_job_from_payload(payload: JsonPayload) -> TrainingJobResponse:
    quota_raw = payload.get("resource_quota", {})
    quota = cast(JsonPayload, quota_raw) if isinstance(quota_raw, dict) else {}
    return TrainingJobResponse(
        job_id=str(payload["job_id"]),
        state=_training_job_state(payload["state"]),
        scene_ref=ResourceRef(str(payload["scene_id"]), str(payload.get("scene_version", ""))),
        algorithm=str(payload["algorithm"]),
        max_iterations=int(payload.get("max_iterations", 100)),
        num_envs=int(payload.get("num_envs", 1)),
        seed=int(payload.get("seed", 42)),
        reward_config_version=str(payload.get("reward_config_version", "reward.default.v1")),
        randomization_profile_id=str(payload.get("randomization_profile_id", "no_randomization")),
        checkpoint_interval=int(payload.get("checkpoint_interval", 10)),
        resource_quota=_resource_quota_from_payload(quota),
        config_hash=str(payload.get("config_hash", "")),
        current_iteration=int(payload.get("current_iteration", 0)),
        checkpoint_count=int(payload.get("checkpoint_count", 0)),
        latest_checkpoint_uri=str(payload.get("latest_checkpoint_uri", "")),
        failure_reason=str(payload.get("failure_reason", "")),
    )


def _resource_quota_from_payload(payload: JsonPayload) -> TrainingResourceQuotaPayload:
    return TrainingResourceQuotaPayload(
        gpu_count=int(payload.get("gpu_count", 0)),
        cpu_threads=int(payload.get("cpu_threads", 2)),
        memory_gb=float(payload.get("memory_gb", 4.0)),
        max_runtime_s=int(payload.get("max_runtime_s", 3600)),
    )


def _metric_summary_from_payload(payload: object) -> MetricSummaryPayload:
    if not isinstance(payload, dict):
        return MetricSummaryPayload(0.0, 1.0, 999.0, 0.0, 0.0, 999)
    return MetricSummaryPayload(
        success_rate=float(payload.get("success_rate", 0.0)),
        collision_rate=float(payload.get("collision_rate", 1.0)),
        tracking_error_m=float(payload.get("tracking_error_m", 999.0)),
        recovery_rate=float(payload.get("recovery_rate", 0.0)),
        energy_proxy=float(payload.get("energy_proxy", 0.0)),
        hard_constraint_violation_count=int(payload.get("hard_constraint_violation_count", 999)),
    )


def _evaluation_report_export_to_payload(export: EvaluationReportExportResponse) -> JsonPayload:
    return export.to_json()


def _evaluation_report_export_from_payload(payload: JsonPayload) -> EvaluationReportExportResponse:
    return EvaluationReportExportResponse(
        export_id=str(payload["export_id"]),
        evaluation_id=str(payload["evaluation_id"]),
        report_format=_report_export_format(payload.get("report_format", "json")),
        uri=str(payload.get("uri", "")),
        checksum=str(payload.get("checksum", "")),
        size_bytes=int(payload.get("size_bytes", 0)),
        generated_by=str(payload.get("generated_by", "")),
        request_id=str(payload.get("request_id", "")),
        timestamp_ns=int(payload.get("timestamp_ns", 0)),
        summary=str(payload.get("summary", "")),
    )


def _policy_approval_to_payload(approval: PolicyApprovalResponse) -> JsonPayload:
    return approval.to_json()


def _policy_approval_from_payload(payload: JsonPayload) -> PolicyApprovalResponse:
    return PolicyApprovalResponse(
        approval_id=str(payload["approval_id"]),
        policy_ref=ResourceRef(str(payload["policy_id"]), str(payload.get("policy_version", ""))),
        evaluation_id=str(payload.get("evaluation_id", "")),
        decision=_approval_decision(payload.get("decision", "rejected")),
        approver_id=str(payload.get("approver_id", "")),
        approver_role=_api_role(payload.get("approver_role", "operator")),
        reason=str(payload.get("reason", "")),
        request_id=str(payload.get("request_id", "")),
        timestamp_ns=int(payload.get("timestamp_ns", 0)),
    )


def _policy_ref_key(policy_ref: ResourceRef) -> str:
    return f"{policy_ref.id}:{policy_ref.version}"


def _policy_to_payload(policy: PolicyStateResponse) -> JsonPayload:
    return policy.to_json()


def _policy_from_payload(payload: JsonPayload) -> PolicyStateResponse:
    return PolicyStateResponse(
        policy_ref=ResourceRef(str(payload["policy_id"]), str(payload.get("policy_version", ""))),
        stage=_policy_api_stage(payload["stage"]),
        is_current_baseline=bool(payload.get("is_current_baseline", False)),
        reason=str(payload.get("reason", "")),
        artifact_uri=str(payload.get("artifact_uri", "")),
        checksum=str(payload.get("checksum", "")),
        metrics=_metric_summary_from_payload(payload.get("metrics", {})),
    )


def _evaluation_report_to_payload(report: EvaluationReportResponse) -> JsonPayload:
    return report.to_json()


def _evaluation_report_from_payload(payload: JsonPayload) -> EvaluationReportResponse:
    return EvaluationReportResponse(
        evaluation_id=str(payload["evaluation_id"]),
        policy_ref=ResourceRef(str(payload["policy_id"]), str(payload.get("policy_version", ""))),
        scene_ref=ResourceRef(str(payload["scene_id"]), str(payload.get("scene_version", ""))),
        suite_id=str(payload.get("suite_id", "standard_v1")),
        metrics=_metric_summary_from_payload(payload.get("metrics", {})),
        decision=cast(
            GateDecision,
            _required_literal(
                payload.get("decision", "failed"),
                allowed=frozenset({"passed", "failed"}),
                field_name="gate decision",
            ),
        ),
        reason=str(payload.get("reason", "")),
        baseline_policy_ref=ResourceRef(
            str(payload.get("baseline_policy_id", "")),
            str(payload.get("baseline_policy_version", "")),
        ),
        baseline_metrics=_metric_summary_from_payload(payload.get("baseline_metrics", {})),
        baseline_diff=cast(JsonPayload, payload.get("baseline_diff", {})),
        replay_run_id=str(payload.get("replay_run_id", "")),
    )


def _replay_to_payload(replay: ReplayResponse) -> JsonPayload:
    return replay.to_json()


def _replay_from_payload(payload: JsonPayload) -> ReplayResponse:
    return ReplayResponse(
        run_id=str(payload["run_id"]),
        segment_count=int(payload["segment_count"]),
        keyframe_count=int(payload["keyframe_count"]),
        backend=str(payload.get("backend", "minimal")),
        runtime_profile=str(payload.get("runtime_profile", "headless_fast")),
        first_timestamp_ns=int(payload.get("first_timestamp_ns", 0)),
        last_timestamp_ns=int(payload.get("last_timestamp_ns", 0)),
        keyframes=tuple(str(item) for item in payload.get("keyframes", [])),
        safety_events=tuple(str(item) for item in payload.get("safety_events", [])),
        manifest_uri=str(payload.get("manifest_uri", "")),
        manifest_checksum=str(payload.get("manifest_checksum", "")),
    )


def _audit_to_payload(record: AuditRecordResponse) -> JsonPayload:
    return record.to_json()


def _audit_from_payload(payload: JsonPayload) -> AuditRecordResponse:
    return AuditRecordResponse(
        audit_id=str(payload["audit_id"]),
        actor_id=str(payload["actor_id"]),
        actor_role=_api_role(payload.get("actor_role", "operator")),
        action=str(payload["action"]),
        object_ref=ResourceRef(str(payload["object_id"]), str(payload.get("object_version", ""))),
        result=str(payload["result"]),
        reason=str(payload.get("reason", "")),
        request_id=str(payload.get("request_id", "")),
        timestamp_ns=int(payload.get("timestamp_ns", 0)),
    )


def _event_to_payload(event: EventEnvelope) -> JsonPayload:
    return event.to_json()


def _event_from_payload(payload: JsonPayload) -> EventEnvelope:
    return EventEnvelope(
        event_id=str(payload["event_id"]),
        topic=_event_topic(payload["topic"]),
        run_id=str(payload.get("run_id", "")),
        message=str(payload.get("message", "")),
        payload=dict(payload.get("payload", {})),
        request_id=str(payload.get("request_id", "")),
        timestamp_ns=int(payload.get("timestamp_ns", 0)),
    )


def _policy_key(policy: PolicyStateResponse) -> str:
    return f"{policy.policy_ref.id}:{policy.policy_ref.version}"


def _scene_key(scene: SceneProfilePayload) -> str:
    return f"{scene.scene_ref.id}:{scene.scene_ref.version}"
