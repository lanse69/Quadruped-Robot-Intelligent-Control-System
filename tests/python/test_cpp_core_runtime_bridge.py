from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qrics.api.core_runtime import probe_core_runtime
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
