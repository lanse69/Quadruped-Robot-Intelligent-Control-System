from __future__ import annotations

from typing import Any

from pytest import MonkeyPatch

from qrics.api.app import QricsApiApp
from qrics.api.schemas import (
    OverridePayload,
    RequestContext,
    ResourceRef,
    SimulationRunOptionsPayload,
    TaskSubmissionPayload,
)
from qrics.api.simulation_runner import LocalSimulationRunner
from qrics.sim.presentation_channel import read_presentation_command


def test_api_override_writes_safe_stand_to_open_presentation_window(
    monkeypatch: MonkeyPatch,
) -> None:
    class DummyProcess:
        pid = 90123

        def poll(self) -> None:
            return None

    def fake_popen(command: list[str], **kwargs: Any) -> DummyProcess:
        return DummyProcess()

    monkeypatch.setattr("qrics.api.simulation_runner.subprocess.Popen", fake_popen)

    context = RequestContext(
        request_id="req-presentation-override", actor_id="operator", role="operator"
    )
    runner = LocalSimulationRunner(webots_execute=False, presentation_hold_seconds=12.0)
    app = QricsApiApp(simulation_runner=runner)

    task_response = app.submit_task(
        TaskSubmissionPayload(
            source_text="先巡检A，再回到平台待命",
            scene_ref=ResourceRef("minimal_scene", "0.1.0"),
        ),
        context,
    )
    assert task_response.ok
    task_id = str(task_response.data["task_id"])
    assert app.confirm_task(task_id, context).ok

    handoff = app.handoff_task(
        task_id,
        context,
        run_options=SimulationRunOptionsPayload(
            backend="webots",
            runtime_profile="webots_fast",
            step_count=4,
        ),
    )
    assert handoff.ok
    run_id = str(handoff.data["run_id"])
    assert handoff.data["presentation_pid"] == 90123

    override = app.override_control(
        run_id,
        OverridePayload(command_type="safe_stand", reason="演示安全站立命令下发到可视化窗口"),
        context,
    )

    assert override.ok
    assert override.data["latest_action"] == "safe_stand"
    assert override.data["presentation_pid"] == 90123
    command_path = str(override.data["presentation_command_path"])
    assert command_path
    command = read_presentation_command(command_path)
    assert command.command_type == "safe_stand"
    assert command.run_id == run_id
