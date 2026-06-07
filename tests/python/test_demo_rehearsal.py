from pathlib import Path

from qrics.demo.rehearsal import (
    DemoRehearsalConfig,
    render_rehearsal_markdown,
    run_demo_rehearsal,
    write_rehearsal_report,
)


def test_demo_rehearsal_runs_complete_minimal_defence_flow(tmp_path: Path) -> None:
    report = run_demo_rehearsal(
        config=DemoRehearsalConfig(
            backend="minimal",
            runtime_profile="headless_fast",
            step_count=6,
            scene_version="0.5.0-test",
            unique_scene_version=False,
        )
    )

    assert report.status == "passed"
    assert report.run_id.startswith("run_task_")
    step_ids = {step.step_id for step in report.steps}
    assert {
        "scene_create",
        "simulation_preview",
        "task_one_click_run",
        "replay_query",
        "override_safe_stand",
        "override_emergency_stop",
        "audit_query",
        "events_query",
        "training_plan",
        "training_start",
        "training_checkpoint",
        "training_complete",
        "evaluation_gate",
        "policy_approve",
        "policy_release",
        "policy_baseline",
    }.issubset(step_ids)

    markdown = render_rehearsal_markdown(report)
    assert "QRICS 本机答辩端到端演练报告" in markdown
    assert "总体状态：`passed`" in markdown
    assert "提升策略为当前基线" in markdown

    json_path, markdown_path = write_rehearsal_report(report, tmp_path)
    assert json_path.exists()
    assert markdown_path.exists()
    assert "qrics.demo_rehearsal.v1" in json_path.read_text(encoding="utf-8")
    assert "执行检查项" in markdown_path.read_text(encoding="utf-8")


def test_demo_rehearsal_can_skip_training_and_overrides() -> None:
    report = run_demo_rehearsal(
        config=DemoRehearsalConfig(
            backend="minimal",
            runtime_profile="headless_fast",
            step_count=3,
            scene_version="0.5.0-skip",
            unique_scene_version=False,
            include_training_gate=False,
            include_overrides=False,
        )
    )

    assert report.status == "passed"
    step_ids = {step.step_id for step in report.steps}
    assert "training_plan" not in step_ids
    assert "override_emergency_stop" not in step_ids
    assert "events_query" in step_ids
