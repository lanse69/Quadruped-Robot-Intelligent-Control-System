from __future__ import annotations

from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from qrics.api.http_app import create_http_app
from qrics.demo import readiness
from qrics.demo.readiness import (
    DemoReadinessConfig,
    collect_demo_readiness,
    render_readiness_markdown,
)


@dataclass(frozen=True)
class _FakeProbeResult:
    available: bool
    binary_path: str = ""
    error: str = ""


def test_collect_demo_readiness_reports_ready_when_required_dependencies_exist(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    def fake_find_module_spec(module_name: str) -> ModuleSpec | None:
        if module_name in {"fastapi", "uvicorn", "mujoco"}:
            return ModuleSpec(module_name, loader=None)
        return None

    def fake_which(_executable: str) -> str | None:
        return "/usr/bin/webots"

    monkeypatch.setattr(readiness, "_find_module_spec", fake_find_module_spec)
    monkeypatch.setattr(readiness, "_which", fake_which)
    launcher_dir = tmp_path / "scripts"
    launcher_dir.mkdir()
    (launcher_dir / "install_web_console_app.py").write_text("# launcher", encoding="utf-8")
    monkeypatch.setattr(
        readiness,
        "probe_core_runtime",
        lambda _root=None: _FakeProbeResult(available=True, binary_path="/tmp/qrics_core_runtime"),
    )

    report = collect_demo_readiness(
        DemoReadinessConfig(root_dir=tmp_path, state_dir=tmp_path / "state")
    )

    assert report.status == "ready"
    assert all(item.status == "ready" for item in report.items)
    assert report.commands
    assert "install_web_console_app.py install" in "\n".join(report.commands)


def test_collect_demo_readiness_blocks_on_missing_required_runtime(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    def fake_find_module_spec(_module_name: str) -> ModuleSpec | None:
        return None

    def fake_which(_executable: str) -> str | None:
        return None

    monkeypatch.setattr(readiness, "_find_module_spec", fake_find_module_spec)
    monkeypatch.setattr(readiness, "_which", fake_which)
    monkeypatch.setattr(
        readiness,
        "probe_core_runtime",
        lambda _root=None: _FakeProbeResult(available=False, error="binary missing"),
    )

    report = collect_demo_readiness(
        DemoReadinessConfig(root_dir=tmp_path, state_dir=tmp_path / "state")
    )

    assert report.status == "blocked"
    blocked_items = {item.item_id for item in report.items if item.status == "blocked"}
    assert "api_server_dependencies" in blocked_items
    assert "mujoco_backend" in blocked_items
    assert "cpp_core_runtime" in blocked_items
    assert any("cmake --build" in command for command in report.commands)


def test_render_readiness_markdown_contains_commands(monkeypatch: Any, tmp_path: Path) -> None:
    def fake_find_module_spec(_module_name: str) -> ModuleSpec | None:
        return None

    def fake_which(_executable: str) -> str | None:
        return None

    monkeypatch.setattr(readiness, "_find_module_spec", fake_find_module_spec)
    monkeypatch.setattr(readiness, "_which", fake_which)
    monkeypatch.setattr(
        readiness,
        "probe_core_runtime",
        lambda _root=None: _FakeProbeResult(available=False, error="binary missing"),
    )
    report = collect_demo_readiness(
        DemoReadinessConfig(root_dir=tmp_path, state_dir=tmp_path / "state")
    )

    markdown = render_readiness_markdown(report)

    assert "# QRICS 本机演示就绪检查" in markdown
    assert "总体状态：`blocked`" in markdown
    assert "建议执行命令" in markdown


def test_http_demo_readiness_endpoint_returns_check_items() -> None:
    client = TestClient(create_http_app())

    response = client.get(
        "/api/v1/sim/readiness",
        headers={
            "x-request-id": "req-readiness-http",
            "x-actor-id": "tester",
            "x-actor-role": "operator",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["status"] in {"ready", "degraded", "blocked"}
    assert isinstance(data["items"], list)
    assert {item["item_id"] for item in data["items"]} >= {
        "python_runtime",
        "web_console_static",
        "mujoco_backend",
        "cpp_core_runtime",
        "state_dir",
    }
