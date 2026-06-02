import pytest

pytest.importorskip("mujoco")

from qrics.api import create_demo_app
from qrics.api.routes_tasks import confirm_task, handoff_task, submit_task
from qrics.api.schemas import RequestContext, TaskSubmissionPayload


def test_api_handoff_can_use_mujoco_backend_when_installed() -> None:
    app = create_demo_app()
    app.default_sim_backend = "mujoco"
    app.default_runtime_profile = "headless_fast"
    context = RequestContext(request_id="req-mujoco", actor_id="operator-1", role="operator")

    submitted = submit_task(app, TaskSubmissionPayload(source_text="巡检A"), context)
    assert submitted.ok
    task_id = str(submitted.data["task_id"])
    assert confirm_task(app, task_id, context).ok

    handoff = handoff_task(app, task_id, context)

    assert handoff.ok
    assert handoff.data["backend"] == "mujoco"
    assert handoff.data["runtime_profile"] == "headless_fast"

    control_step_count = handoff.data["control_step_count"]
    sim_time_ns = handoff.data["sim_time_ns"]

    assert isinstance(control_step_count, int)
    assert isinstance(sim_time_ns, int)

    assert control_step_count > 0
    assert sim_time_ns > 0
