from collections.abc import Mapping
from pathlib import Path

from fastapi.testclient import TestClient

from qrics.api.app import create_demo_app
from qrics.api.http_app import create_http_app
from qrics.api.schemas import (
    EvaluationReportExportPayload,
    EvaluationRunPayload,
    JsonValue,
    MetricSummaryPayload,
    PolicyApprovalPayload,
    RequestContext,
    ResourceRef,
    TrainingCheckpointPayload,
    TrainingCompletionPayload,
    TrainingPlanPayload,
    TrainingResourceQuotaPayload,
)
from qrics.api.sqlite_repository import SQLiteQricsRepository
from qrics.storage.object_store import FileObjectStore


def _json_object(data: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue]:
    value = data[key]
    assert isinstance(value, dict)
    return value


def _json_float(data: Mapping[str, JsonValue], key: str) -> float:
    value = data[key]
    assert isinstance(value, int | float)
    assert not isinstance(value, bool)
    return float(value)


def _engineer() -> RequestContext:
    return RequestContext(request_id="req-train", actor_id="algo-1", role="algorithm_engineer")


def _metrics() -> MetricSummaryPayload:
    return MetricSummaryPayload(
        success_rate=0.91,
        collision_rate=0.01,
        tracking_error_m=0.12,
        recovery_rate=0.88,
        energy_proxy=24.0,
        hard_constraint_violation_count=0,
    )


def test_training_job_checkpoint_completion_and_evaluation_gate() -> None:
    app = create_demo_app()
    context = _engineer()
    plan = TrainingPlanPayload(
        training_id="batch-001",
        scene_ref=ResourceRef("minimal_scene", "0.1.0"),
        algorithm="ppo_local_smoke",
        max_iterations=40,
        num_envs=4,
        seed=7,
        reward_config_version="reward.walk.v2",
        randomization_profile_id="local_domain_randomization",
        checkpoint_interval=5,
        resource_quota=TrainingResourceQuotaPayload(
            gpu_count=0,
            cpu_threads=4,
            memory_gb=6.0,
            max_runtime_s=900,
        ),
    )

    queued = app.submit_training_plan(plan, context)
    assert queued.ok
    assert queued.data["state"] == "queued"
    assert queued.data["config_hash"]
    assert queued.data["resource_quota"] == {
        "gpu_count": 0,
        "cpu_threads": 4,
        "memory_gb": 6.0,
        "max_runtime_s": 900,
    }

    started = app.start_training_job("job_batch-001", context)
    assert started.ok
    assert started.data["state"] == "running"

    checkpoint = app.record_training_checkpoint(
        "job_batch-001",
        TrainingCheckpointPayload(iteration=10, checkpoint_uri="file://ckpt/batch-001/10.pt"),
        context,
    )
    assert checkpoint.ok
    assert checkpoint.data["current_iteration"] == 10
    assert checkpoint.data["checkpoint_count"] == 1

    completion = app.complete_training_job(
        "job_batch-001",
        TrainingCompletionPayload(
            policy_ref=ResourceRef("rough_nav", "2.0.0"),
            artifact_uri="artifact://policies/rough_nav/2.0.0/model.pt",
            checksum="sha256:rough-nav",
            metrics=_metrics(),
            final_iteration=40,
            reason="候选策略训练完成",
        ),
        context,
    )
    assert completion.ok
    completion_job = _json_object(completion.data, "job")
    completion_policy = _json_object(completion.data, "policy")
    completion_metrics = _json_object(completion_policy, "metrics")
    assert completion_job["state"] == "succeeded"
    assert completion_policy["stage"] == "candidate"
    assert _json_float(completion_metrics, "success_rate") == 0.91

    evaluation = app.run_standard_evaluation(
        EvaluationRunPayload(
            evaluation_id="eval-rough-nav-2",
            policy_ref=ResourceRef("rough_nav", "2.0.0"),
            scene_ref=ResourceRef("minimal_scene", "0.1.0"),
            metrics=_metrics(),
            suite_id="standard_v1",
        ),
        context,
    )
    assert evaluation.ok
    baseline_diff = _json_object(evaluation.data, "baseline_diff")
    assert evaluation.data["decision"] == "passed"
    assert evaluation.data["reason"] == "standard gate thresholds satisfied"
    assert _json_float(baseline_diff, "success_rate_delta") == 0.91

    approval = app.approve_policy(
        PolicyApprovalPayload(
            policy_ref=ResourceRef("rough_nav", "2.0.0"),
            evaluation_id="eval-rough-nav-2",
            decision="approved",
            reason="门禁报告批准",
        ),
        context,
    )
    assert approval.ok
    assert approval.data["decision"] == "approved"

    exported = app.export_evaluation_report(
        EvaluationReportExportPayload(
            evaluation_id="eval-rough-nav-2",
            report_format="markdown",
            reason="导出评测报告",
        ),
        context,
    )
    assert exported.ok
    assert exported.data["report_format"] == "markdown"
    assert exported.data["checksum"]

    release = app.release_policy(ResourceRef("rough_nav", "2.0.0"), context, "门禁通过发布")
    assert release.ok
    assert release.data["stage"] == "released"


def test_training_evaluation_persists_in_sqlite_repository(tmp_path: Path) -> None:
    object_store = FileObjectStore(tmp_path / "objects")
    repository = SQLiteQricsRepository(tmp_path / "qrics.sqlite3", object_store=object_store)
    try:
        app = create_demo_app(repository)
        context = _engineer()

        assert app.submit_training_plan(
            TrainingPlanPayload(
                training_id="persist-001",
                scene_ref=ResourceRef("minimal_scene", "0.1.0"),
            ),
            context,
        ).ok
        assert app.start_training_job("job_persist-001", context).ok
        assert app.complete_training_job(
            "job_persist-001",
            TrainingCompletionPayload(
                policy_ref=ResourceRef("persist_nav", "1.0.0"),
                artifact_uri="artifact://policies/persist_nav/1.0.0/model.pt",
                metrics=_metrics(),
                final_iteration=100,
            ),
            context,
        ).ok
        assert app.run_standard_evaluation(
            EvaluationRunPayload(
                evaluation_id="eval-persist-nav",
                policy_ref=ResourceRef("persist_nav", "1.0.0"),
                scene_ref=ResourceRef("minimal_scene", "0.1.0"),
                metrics=_metrics(),
            ),
            context,
        ).ok
        assert app.approve_policy(
            PolicyApprovalPayload(
                policy_ref=ResourceRef("persist_nav", "1.0.0"),
                evaluation_id="eval-persist-nav",
                decision="approved",
                reason="persistent approval",
            ),
            context,
        ).ok
        exported = app.export_evaluation_report(
            EvaluationReportExportPayload(
                evaluation_id="eval-persist-nav",
                report_format="json",
                reason="persistent export",
            ),
            context,
        )
        assert exported.ok
        uri = exported.data["uri"]
        assert isinstance(uri, str)
        assert Path(uri).exists()
    finally:
        repository.close()

    reopened = SQLiteQricsRepository(tmp_path / "qrics.sqlite3", object_store=object_store)
    try:
        job = reopened.get_training_job("job_persist-001")
        assert job is not None
        assert job.state == "succeeded"
        assert job.config_hash
        report = reopened.get_evaluation_report("eval-persist-nav")
        assert report is not None
        assert report.decision == "passed"
        policy = reopened.get_policy("persist_nav:1.0.0")
        assert policy is not None
        assert policy.stage == "approved"
        assert policy.metrics.success_rate == 0.91
        approval = reopened.latest_policy_approval("persist_nav:1.0.0")
        assert approval is not None
        assert approval.decision == "approved"
        exports = reopened.list_evaluation_report_exports("eval-persist-nav")
        assert len(exports) == 1
        assert exports[0].checksum.startswith("sha256:")
        assert Path(exports[0].uri).exists()
    finally:
        reopened.close()


def test_http_training_and_evaluation_runtime_flow() -> None:
    client = TestClient(create_http_app())
    headers = {
        "x-request-id": "req-http-training",
        "x-actor-id": "algo-http",
        "x-actor-role": "algorithm_engineer",
    }
    policy_ref = {"id": "http_nav", "version": "1.0.0"}
    metrics = {
        "success_rate": 0.9,
        "collision_rate": 0.02,
        "tracking_error_m": 0.2,
        "recovery_rate": 0.8,
        "energy_proxy": 25.0,
        "hard_constraint_violation_count": 0,
    }

    plan = client.post(
        "/api/v1/training/plans",
        headers=headers,
        json={
            "training_id": "http-001",
            "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
            "algorithm": "ppo_http_smoke",
            "max_iterations": 20,
            "num_envs": 2,
            "checkpoint_interval": 5,
            "resource_quota": {"gpu_count": 0, "cpu_threads": 2, "memory_gb": 4.0},
        },
    )
    assert plan.status_code == 200
    assert plan.json()["data"]["config_hash"]

    started = client.post("/api/v1/training/jobs/job_http-001/start", headers=headers)
    assert started.status_code == 200
    checkpoint = client.post(
        "/api/v1/training/jobs/job_http-001/checkpoint",
        headers=headers,
        json={"iteration": 5, "checkpoint_uri": "file://ckpt/http-001/5.pt"},
    )
    assert checkpoint.status_code == 200
    assert checkpoint.json()["data"]["checkpoint_count"] == 1

    completed = client.post(
        "/api/v1/training/jobs/job_http-001/complete",
        headers=headers,
        json={
            "policy_ref": policy_ref,
            "artifact_uri": "artifact://policies/http_nav/1.0.0/model.pt",
            "metrics": metrics,
            "final_iteration": 20,
            "reason": "HTTP training completed",
        },
    )
    assert completed.status_code == 200
    assert completed.json()["data"]["policy"]["stage"] == "candidate"

    evaluation = client.post(
        "/api/v1/evaluations",
        headers=headers,
        json={
            "evaluation_id": "eval-http-nav",
            "policy_ref": policy_ref,
            "scene_ref": {"id": "minimal_scene", "version": "0.1.0"},
            "metrics": metrics,
        },
    )
    assert evaluation.status_code == 200
    assert evaluation.json()["data"]["decision"] == "passed"

    approval = client.post(
        "/api/v1/policies/http_nav/1.0.0/approval",
        headers=headers,
        json={
            "evaluation_id": "eval-http-nav",
            "decision": "approved",
            "reason": "HTTP approval after standardized evaluation",
        },
    )
    assert approval.status_code == 200
    assert approval.json()["data"]["decision"] == "approved"

    exported = client.post(
        "/api/v1/evaluations/eval-http-nav/exports",
        headers=headers,
        json={"format": "json", "reason": "export gate evidence"},
    )
    assert exported.status_code == 200
    assert exported.json()["data"]["checksum"]

    released = client.post(
        "/api/v1/policies/http_nav/1.0.0/release",
        headers=headers,
        json={"reason": "release after standardized evaluation"},
    )
    assert released.status_code == 200
    assert released.json()["data"]["stage"] == "released"
