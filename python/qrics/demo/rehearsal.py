"""End-to-end defence rehearsal runner for local QRICS demonstrations.

The readiness gate answers whether the machine can run the demo.  This module
answers a different question: whether the current QRICS application wiring can
walk through the complete defence path without the Web Console hiding failures.
It exercises the same application facade used by HTTP routes: scene creation,
preview, one-click task parsing/running, override safety commands, replay/audit
queries, and the lightweight training/evaluation/model gate lifecycle.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from qrics.api import create_demo_app
from qrics.api.app import QricsApiApp
from qrics.api.schemas import (
    ApiError,
    ApiResponse,
    AuditQuery,
    EvaluationRunPayload,
    JsonDict,
    JsonValue,
    MetricSummaryPayload,
    OverridePayload,
    PolicyApprovalPayload,
    ReplayQuery,
    RequestContext,
    ResourceRef,
    SceneAssetPayload,
    SceneCreatePayload,
    SimulationBackend,
    SimulationPreviewPayload,
    SimulationRunOptionsPayload,
    TaskRunPayload,
    TrainingCheckpointPayload,
    TrainingCompletionPayload,
    TrainingPlanPayload,
)
from qrics.api.simulation_runner import LocalSimulationRunner

RehearsalStatus = Literal["passed", "failed"]
RehearsalStepStatus = Literal["passed", "failed"]


@dataclass(frozen=True)
class DemoRehearsalConfig:
    """Configuration for a bounded local end-to-end defence rehearsal."""

    backend: SimulationBackend = "minimal"
    runtime_profile: str = "headless_fast"
    step_count: int = 12
    task_text: str = "从平台出发，避开低摩擦区，先巡检A，再巡检B，最后回到平台待命"
    scene_id: str = "defense_rehearsal_scene"
    scene_version: str = "0.5.0"
    unique_scene_version: bool = True
    webots_execute: bool = False
    include_training_gate: bool = True
    include_overrides: bool = True


@dataclass(frozen=True)
class DemoRehearsalStep:
    """One executable checkpoint in the local defence rehearsal."""

    step_id: str
    name: str
    status: RehearsalStepStatus
    detail: str = ""
    data: JsonDict = field(default_factory=dict)

    def to_json(self) -> JsonDict:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "data": self.data,
        }


@dataclass(frozen=True)
class DemoRehearsalReport:
    """Structured result produced by a complete local demonstration rehearsal."""

    status: RehearsalStatus
    backend: SimulationBackend
    runtime_profile: str
    scene_ref: ResourceRef
    run_id: str
    task_text: str
    steps: tuple[DemoRehearsalStep, ...]
    generated_at_ns: int = 0

    @property
    def failed_steps(self) -> tuple[DemoRehearsalStep, ...]:
        return tuple(step for step in self.steps if step.status == "failed")

    def to_json(self) -> JsonDict:
        return {
            "schema": "qrics.demo_rehearsal.v1",
            "status": self.status,
            "backend": self.backend,
            "runtime_profile": self.runtime_profile,
            "scene_ref": {"id": self.scene_ref.id, "version": self.scene_ref.version},
            "run_id": self.run_id,
            "task_text": self.task_text,
            "generated_at_ns": self.generated_at_ns,
            "failed_step_count": len(self.failed_steps),
            "steps": [step.to_json() for step in self.steps],
        }


def run_demo_rehearsal(
    *,
    app: QricsApiApp | None = None,
    config: DemoRehearsalConfig | None = None,
) -> DemoRehearsalReport:
    """Execute the full local demo path through the application facade."""

    if config is None:
        config = DemoRehearsalConfig()

    qrics_app = app or create_demo_app()
    if qrics_app.simulation_runner is None:
        qrics_app.simulation_runner = LocalSimulationRunner(webots_execute=config.webots_execute)
    qrics_app.default_sim_backend = config.backend
    qrics_app.default_runtime_profile = config.runtime_profile

    operator = RequestContext("rehearsal-operator", "defense-operator", "operator")
    test_engineer = RequestContext("rehearsal-scene", "defense-tester", "test_engineer")
    algorithm_engineer = RequestContext(
        "rehearsal-algorithm", "defense-algorithm", "algorithm_engineer"
    )
    auditor = RequestContext("rehearsal-audit", "defense-auditor", "auditor")

    steps: list[DemoRehearsalStep] = []
    run_id = ""
    scene_ref = ResourceRef(config.scene_id, _scene_version(config))
    run_options = SimulationRunOptionsPayload(
        backend=config.backend,
        runtime_profile=config.runtime_profile,
        step_count=max(1, config.step_count),
        forward_velocity_mps=0.32,
        yaw_rate_radps=0.04,
        obstacle_replan_distance_m=0.18,
    )

    created_scene = qrics_app.create_scene(
        _scene_payload(scene_ref),
        test_engineer,
    )
    steps.append(_step_from_response("scene_create", "创建 typed 本机演示场景", created_scene))
    if not created_scene.ok:
        return _report(config, scene_ref, run_id, steps)

    preview = qrics_app.preview_simulation(
        SimulationPreviewPayload(scene_ref=scene_ref, run_options=run_options),
        operator,
    )
    steps.append(_step_from_response("simulation_preview", "预览场景并执行仿真后端 smoke", preview))
    if not preview.ok or preview.data.get("state") == "failed":
        return _report(config, scene_ref, run_id, steps)

    task_run = qrics_app.run_task(
        TaskRunPayload(
            source_text=config.task_text,
            scene_ref=scene_ref,
            run_options=run_options,
            require_confirmation=False,
            reason="答辩端到端演练",
        ),
        operator,
    )
    steps.append(_step_from_response("task_one_click_run", "一键任务解析、确认、handoff", task_run))
    if not task_run.ok or not bool(task_run.data.get("run_started", False)):
        return _report(config, scene_ref, run_id, steps)
    run_id = str(task_run.data.get("run_id", ""))

    status = qrics_app.get_control_status(run_id, operator)
    steps.append(_step_from_response("control_status", "查询控制运行状态", status))

    replay = qrics_app.query_replay(ReplayQuery(run_id=run_id), operator)
    steps.append(_step_from_response("replay_query", "查询回放与关键帧索引", replay))

    if config.include_overrides:
        safe_stand = qrics_app.override_control(
            run_id,
            OverridePayload(command_type="safe_stand", reason="答辩演练安全站立"),
            operator,
        )
        steps.append(
            _step_from_response("override_safe_stand", "下发 Safe-Stand 安全接管", safe_stand)
        )

        emergency_stop = qrics_app.override_control(
            run_id,
            OverridePayload(command_type="emergency_stop", reason="答辩演练急停"),
            operator,
        )
        steps.append(
            _step_from_response("override_emergency_stop", "下发急停并写入审计", emergency_stop)
        )

    audit = qrics_app.query_audit(AuditQuery(object_id=run_id), auditor)
    steps.append(_step_from_response("audit_query", "查询运行审计链路", audit))

    events = qrics_app.query_events(auditor, run_id=run_id)
    steps.append(_step_from_response("events_query", "查询任务/控制事件快照", events))

    if config.include_training_gate:
        steps.extend(_run_training_gate_rehearsal(qrics_app, scene_ref, run_id, algorithm_engineer))

    return _report(config, scene_ref, run_id, steps)


def write_rehearsal_report(
    report: DemoRehearsalReport, output_dir: str | Path
) -> tuple[Path, Path]:
    """Persist JSON and Markdown evidence for a rehearsal run."""

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "qrics_demo_rehearsal.json"
    markdown_path = out / "qrics_demo_rehearsal.md"
    json_path.write_text(
        json.dumps(report.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_path.write_text(render_rehearsal_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def render_rehearsal_markdown(report: DemoRehearsalReport) -> str:
    """Render a concise defence rehearsal checklist for submission or screenshots."""

    lines = [
        "# QRICS 本机答辩端到端演练报告",
        "",
        f"- 总体状态：`{report.status}`",
        f"- 仿真后端：`{report.backend}`",
        f"- 运行模式：`{report.runtime_profile}`",
        f"- 场景：`{report.scene_ref.id}:{report.scene_ref.version}`",
        f"- 运行编号：`{report.run_id or '-'}`",
        f"- 任务输入：{report.task_text}",
        f"- 失败步骤数：{len(report.failed_steps)}",
        "",
        "## 执行检查项",
        "",
        "| 步骤 | 结果 | 说明 |",
        "| --- | --- | --- |",
    ]
    for step in report.steps:
        detail = step.detail.replace("|", "\\|")
        lines.append(f"| {step.name} | `{step.status}` | {detail} |")
    if report.failed_steps:
        lines.extend(["", "## 失败步骤", ""])
        for step in report.failed_steps:
            lines.append(f"- `{step.step_id}`：{step.detail}")
    lines.append("")
    return "\n".join(lines)


def _run_training_gate_rehearsal(
    app: QricsApiApp,
    scene_ref: ResourceRef,
    run_id: str,
    context: RequestContext,
) -> tuple[DemoRehearsalStep, ...]:
    training_id = f"rehearsal_{int(time.time_ns())}"
    job_id = f"job_{training_id}"
    policy_ref = ResourceRef("rehearsal_gait_policy", "0.5.0")
    metrics = MetricSummaryPayload(
        success_rate=0.91,
        collision_rate=0.01,
        tracking_error_m=0.12,
        recovery_rate=0.86,
        energy_proxy=0.68,
        hard_constraint_violation_count=0,
    )

    steps: list[DemoRehearsalStep] = []
    plan = app.submit_training_plan(
        TrainingPlanPayload(
            training_id=training_id,
            scene_ref=scene_ref,
            algorithm="local_rehearsal_gait_controller",
            max_iterations=4,
            num_envs=1,
            reward_config_version="reward.local_rehearsal.v1",
            randomization_profile_id="web_console_randomization",
            checkpoint_interval=2,
            notes="答辩演练：验证训练-评测-模型门禁状态机，不做长时 RL 训练。",
        ),
        context,
    )
    steps.append(_step_from_response("training_plan", "提交轻量训练计划", plan))
    if not plan.ok:
        return tuple(steps)

    started = app.start_training_job(job_id, context)
    steps.append(_step_from_response("training_start", "启动训练任务", started))
    if not started.ok:
        return tuple(steps)

    checkpoint = app.record_training_checkpoint(
        job_id,
        TrainingCheckpointPayload(
            iteration=2,
            checkpoint_uri=f"artifact://qrics/checkpoints/{training_id}/iter_2.ckpt",
            reason="答辩演练检查点",
        ),
        context,
    )
    steps.append(_step_from_response("training_checkpoint", "记录训练检查点", checkpoint))
    if not checkpoint.ok:
        return tuple(steps)

    completed = app.complete_training_job(
        job_id,
        TrainingCompletionPayload(
            policy_ref=policy_ref,
            artifact_uri=f"artifact://qrics/policies/{policy_ref.id}/{policy_ref.version}",
            metrics=metrics,
            checksum="sha256:demo-rehearsal-policy",
            final_iteration=4,
            reason="答辩演练策略工件注册",
        ),
        context,
    )
    steps.append(_step_from_response("training_complete", "完成训练并注册候选策略", completed))
    if not completed.ok:
        return tuple(steps)

    evaluation_id = f"eval_{training_id}"
    evaluated = app.run_standard_evaluation(
        EvaluationRunPayload(
            evaluation_id=evaluation_id,
            policy_ref=policy_ref,
            scene_ref=scene_ref,
            suite_id="defense_rehearsal_suite",
            metrics=metrics,
            replay_run_id=run_id,
            reason="答辩演练标准化评测",
        ),
        context,
    )
    steps.append(_step_from_response("evaluation_gate", "执行标准化评测与门禁", evaluated))
    if not evaluated.ok or evaluated.data.get("decision") != "passed":
        return tuple(steps)

    approved = app.approve_policy(
        PolicyApprovalPayload(
            policy_ref=policy_ref,
            evaluation_id=evaluation_id,
            decision="approved",
            reason="答辩演练门禁通过，允许发布",
        ),
        context,
    )
    steps.append(_step_from_response("policy_approve", "审批候选策略", approved))
    if not approved.ok:
        return tuple(steps)

    released = app.release_policy(policy_ref, context, "答辩演练发布策略")
    steps.append(_step_from_response("policy_release", "发布策略工件", released))
    if not released.ok:
        return tuple(steps)

    baseline = app.promote_policy_baseline(policy_ref, context, "答辩演练提升为仿真基线")
    steps.append(_step_from_response("policy_baseline", "提升策略为当前基线", baseline))
    return tuple(steps)


def _scene_payload(scene_ref: ResourceRef) -> SceneCreatePayload:
    return SceneCreatePayload(
        scene_id=scene_ref.id,
        version=scene_ref.version,
        name="QRICS Defence Rehearsal Scene",
        terrain_pack="mixed_terrain_pack",
        assets=(
            SceneAssetPayload(
                asset_id="mixed_terrain",
                asset_type="terrain",
                uri="builtin://qrics/terrain/mixed_terrain_pack",
                checksum="builtin-mixed-terrain",
            ),
            SceneAssetPayload(
                asset_id="平台",
                asset_type="checkpoint",
                uri="builtin://qrics/checkpoint/platform",
                checksum="builtin-platform",
                position=(0.0, 0.0, 0.02),
            ),
            SceneAssetPayload(
                asset_id="巡检点A",
                asset_type="checkpoint",
                uri="builtin://qrics/checkpoint/A",
                checksum="builtin-checkpoint-A",
                position=(0.9, 0.34, 0.02),
            ),
            SceneAssetPayload(
                asset_id="巡检点B",
                asset_type="checkpoint",
                uri="builtin://qrics/checkpoint/B",
                checksum="builtin-checkpoint-B",
                position=(1.85, -0.3, 0.02),
            ),
            SceneAssetPayload(
                asset_id="低摩擦区",
                asset_type="no_go_zone",
                uri="builtin://qrics/no_go_zone/low_friction",
                checksum="builtin-low-friction-zone",
                position=(2.45, 0.0, 0.01),
                size=(1.15, 1.65, 0.02),
            ),
            SceneAssetPayload(
                asset_id="演练箱体",
                asset_type="obstacle",
                geometry_type="box",
                position=(1.12, 0.68, 0.14),
                size=(0.2, 0.2, 0.22),
                radius_m=0.1,
                height_m=0.22,
            ),
            SceneAssetPayload(
                asset_id="演练圆柱",
                asset_type="obstacle",
                geometry_type="cylinder",
                position=(1.48, -0.62, 0.15),
                radius_m=0.09,
                height_m=0.3,
            ),
            SceneAssetPayload(
                asset_id="演练球体",
                asset_type="obstacle",
                geometry_type="sphere",
                position=(2.2, 0.5, 0.12),
                radius_m=0.12,
                height_m=0.12,
            ),
        ),
        change_summary="local defence rehearsal typed scene",
    )


def _scene_version(config: DemoRehearsalConfig) -> str:
    if not config.unique_scene_version:
        return config.scene_version
    suffix = str(time.time_ns())[-8:]
    return f"{config.scene_version}+rehearsal{suffix}"


def _step_from_response(step_id: str, name: str, response: ApiResponse) -> DemoRehearsalStep:
    if response.ok:
        return DemoRehearsalStep(
            step_id=step_id,
            name=name,
            status="passed",
            detail=_success_detail(response.data),
            data=response.data,
        )
    return DemoRehearsalStep(
        step_id=step_id,
        name=name,
        status="failed",
        detail=_error_detail(response.errors),
        data={
            "errors": [
                {"code": error.code, "message": error.message, "field": error.field}
                for error in response.errors
            ]
        },
    )


def _success_detail(data: JsonDict) -> str:
    if "state" in data:
        return f"state={data['state']}"
    if "decision" in data:
        return f"decision={data['decision']}"
    if "count" in data:
        return f"count={data['count']}"
    if "run_id" in data:
        return f"run_id={data['run_id']}"
    if "job_id" in data:
        return f"job_id={data['job_id']}"
    if "policy_id" in data and "policy_version" in data:
        return f"policy={data['policy_id']}:{data['policy_version']}"
    return "ok"


def _error_detail(errors: tuple[ApiError, ...]) -> str:
    if not errors:
        return "unknown error"
    first = errors[0]
    field = f" field={first.field}" if first.field else ""
    return f"{first.code}: {first.message}{field}"


def _report(
    config: DemoRehearsalConfig,
    scene_ref: ResourceRef,
    run_id: str,
    steps: list[DemoRehearsalStep],
) -> DemoRehearsalReport:
    status: RehearsalStatus = (
        "passed" if all(step.status == "passed" for step in steps) else "failed"
    )
    return DemoRehearsalReport(
        status=status,
        backend=config.backend,
        runtime_profile=config.runtime_profile,
        scene_ref=scene_ref,
        run_id=run_id,
        task_text=config.task_text,
        steps=tuple(steps),
        generated_at_ns=time.time_ns(),
    )


def coerce_json_dict(value: JsonValue) -> JsonDict:
    """Small helper for strict type checkers at call sites that read JSON payloads."""

    if isinstance(value, dict):
        return value
    return {}
