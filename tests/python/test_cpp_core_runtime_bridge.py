from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qrics.api.core_runtime import (
    CoreRuntimeForbiddenZone,
    CoreRuntimeRunRequest,
    CoreRuntimeSceneObstacle,
    CoreRuntimeTaskTarget,
    probe_core_runtime,
    run_core_runtime_task,
)
from qrics.api.http_app import create_http_app


def test_probe_core_runtime_uses_json_binary(tmp_path: Path) -> None:
    binary = tmp_path / "qrics_core_runtime"
    payload = {
        "run_id": "fake_cpp",
        "state": "succeeded",
        "executed_step_count": 3,
    }
    binary.write_text(
        "#!/bin/sh\n" f"printf '%s\\n' '{json.dumps(payload)}'\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | 0o111)

    result = probe_core_runtime(binary, timeout_s=5.0)

    assert result.available is True
    assert result.summary is not None
    assert result.summary["run_id"] == "fake_cpp"
    assert result.summary["state"] == "succeeded"
    assert result.command[0] == str(binary)


def test_probe_core_runtime_reports_missing_binary(tmp_path: Path) -> None:
    missing = tmp_path / "missing_runtime"

    result = probe_core_runtime(missing, timeout_s=1.0)

    assert result.available is False
    assert "failed to execute" in result.error or "No such file" in result.error


def test_http_core_runtime_probe_endpoint_returns_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    # Avoid depending on whether the C++ build artifact exists before Python tests run.
    monkeypatch.setenv("QRICS_CPP_CORE_RUNTIME_BIN", os.devnull)
    client = TestClient(create_http_app())

    response = client.get("/api/v1/sim/core-runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "available" in payload["data"]
    assert "binary_path" in payload["data"]
    assert "summary" in payload["data"]
    assert "error" in payload["data"]


def test_run_core_runtime_task_passes_custom_scene_geometry(tmp_path: Path) -> None:
    binary = tmp_path / "qrics_core_runtime"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "print(json.dumps({'state':'succeeded','argv':sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | 0o111)

    result = run_core_runtime_task(
        CoreRuntimeRunRequest(
            run_id="custom_cpp_scene",
            backend="mujoco",
            runtime_profile="balanced_visual",
            scene_id="web_scene",
            scene_version="0.2.0",
            terrain_pack="mixed_terrain_pack",
            step_count=42,
            task_path=(CoreRuntimeTaskTarget("A", 0.9, 0.2, 0.35, 0.4),),
            obstacles=(
                CoreRuntimeSceneObstacle(
                    obstacle_id="box_1",
                    geometry_type="box",
                    x=0.5,
                    y=0.1,
                    z=0.2,
                    size_x=0.2,
                    size_y=0.3,
                    size_z=0.4,
                ),
            ),
            forbidden_zones=(
                CoreRuntimeForbiddenZone(
                    zone_id="low_friction",
                    polygon=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0)),
                ),
            ),
        ),
        binary_path=binary,
    )

    assert result.available is True
    assert result.summary is not None
    argv_value = result.summary["argv"]
    assert isinstance(argv_value, list)
    argv = [str(item) for item in argv_value]
    assert "--clear-default-assets" in argv
    assert "--task-path" in argv
    assert "A:0.9:0.2:0.35:0.4" in argv
    assert "--obstacle" in argv
    assert "box_1:box:0.5:0.1:0.2:0.2:0.3:0.4:0.12:0.35" in argv
    assert "--forbidden-zone" in argv
    assert any(item.startswith("low_friction:") for item in argv)


def test_one_click_task_run_includes_cpp_core_runtime_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "qrics_core_runtime"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "print(json.dumps({"
        "'run_id':'run_task_1','state':'succeeded','scene_obstacle_count':1,"
        "'scene_forbidden_zone_count':1,'task_target_count':2,'argv':sys.argv[1:]"
        "}))\n",
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | 0o111)
    monkeypatch.setenv("QRICS_CPP_CORE_RUNTIME_BIN", str(binary))

    client = TestClient(create_http_app())
    response = client.post(
        "/api/v1/tasks/run",
        headers={"x-request-id": "req-cpp-run", "x-actor-id": "tester", "x-actor-role": "operator"},
        json={
            "source_text": "先巡检A，再回到平台待命",
            "run_options": {
                "backend": "minimal",
                "runtime_profile": "headless_fast",
                "step_count": 6,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["run_started"] is True
    assert data["status"]["core_runtime_available"] is True
    assert data["status"]["core_runtime_summary"]["summary"]["state"] == "succeeded"
    assert data["core_runtime"]["available"] is True
