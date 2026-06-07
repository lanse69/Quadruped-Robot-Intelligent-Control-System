"""Local demonstration readiness checks for QRICS.

The checks are deliberately side-effect light: they do not launch MuJoCo,
Webots, Uvicorn, or the C++ runtime.  They report whether the local machine is
ready to run the defense/demo path and return concrete remediation commands for
missing pieces.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import resources
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Literal, TypeAlias

from qrics.webui.launcher import default_state_dir

ReadinessStatus: TypeAlias = Literal["ready", "degraded", "blocked"]
ReadinessSeverity: TypeAlias = Literal["required", "optional"]


@dataclass(frozen=True)
class CoreRuntimeProbe:
    """Minimal C++ runtime probe result used without importing qrics.api."""

    available: bool
    binary_path: str = ""
    command: tuple[str, ...] = ()
    summary: dict[str, object] | None = None
    error: str = ""


@dataclass(frozen=True)
class ReadinessItem:
    """One readiness gate in the local demonstration environment."""

    item_id: str
    name: str
    status: ReadinessStatus
    severity: ReadinessSeverity
    detail: str
    command: str = ""
    path: str = ""

    def to_json(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "status": self.status,
            "severity": self.severity,
            "detail": self.detail,
            "command": self.command,
            "path": self.path,
        }


@dataclass(frozen=True)
class DemoReadinessReport:
    """Aggregated local demo readiness result."""

    status: ReadinessStatus
    items: tuple[ReadinessItem, ...]
    commands: tuple[str, ...]
    summary: str

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "summary": self.summary,
            "commands": list(self.commands),
            "items": [item.to_json() for item in self.items],
        }


@dataclass(frozen=True)
class DemoReadinessConfig:
    """Inputs used by readiness checks; injectable for tests."""

    root_dir: Path | None = None
    state_dir: Path | None = None
    webots_executable: str = "webots"


def _find_module_spec(module_name: str) -> ModuleSpec | None:
    """Return an import spec for a Python module.

    Kept as a wrapper so tests can monkeypatch capability discovery without
    reaching into implementation-only imported modules.
    """

    return importlib.util.find_spec(module_name)


def _which(executable: str) -> str | None:
    """Return the executable path if it is discoverable on PATH."""

    return shutil.which(executable)


def collect_demo_readiness(config: DemoReadinessConfig | None = None) -> DemoReadinessReport:
    """Collect local readiness for Web Console + MuJoCo/Webots + C++ runtime."""

    config = config or DemoReadinessConfig()
    root_dir = (config.root_dir or _project_root()).resolve()
    state_dir = (config.state_dir or default_state_dir()).expanduser()
    items = (
        _python_runtime_item(),
        _web_console_static_item(),
        _fastapi_item(),
        _mujoco_item(),
        _webots_item(config.webots_executable),
        _cpp_runtime_item(root_dir),
        _desktop_launcher_item(root_dir),
        _state_dir_item(state_dir),
    )
    status = _aggregate_status(items)
    commands = _deduplicate_commands(item.command for item in items if item.command)
    return DemoReadinessReport(
        status=status,
        items=items,
        commands=commands,
        summary=_summary_text(status, items),
    )


def render_readiness_markdown(report: DemoReadinessReport) -> str:
    """Render a readiness report for CLI output and issue attachments."""

    lines = ["# QRICS 本机演示就绪检查", "", f"总体状态：`{report.status}`", "", report.summary, ""]
    lines.append("| 项 | 状态 | 级别 | 说明 | 路径 |")
    lines.append("|---|---|---|---|---|")
    for item in report.items:
        lines.append(
            "| "
            + " | ".join(
                [
                    item.name,
                    item.status,
                    item.severity,
                    item.detail.replace("|", "/"),
                    item.path or "-",
                ]
            )
            + " |"
        )
    if report.commands:
        lines.extend(["", "## 建议执行命令", ""])
        lines.extend(f"```bash\n{command}\n```" for command in report.commands)
    return "\n".join(lines) + "\n"


def _python_runtime_item() -> ReadinessItem:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return ReadinessItem(
        item_id="python_runtime",
        name="Python 运行时",
        status="ready",
        severity="required",
        detail=f"当前 Python {version} 满足项目 >=3.11 要求。",
        path=sys.executable,
    )


def _web_console_static_item() -> ReadinessItem:
    try:
        static_files = resources.files("qrics.webui.static")
        index = static_files.joinpath("index.html")
        app_js = static_files.joinpath("app.js")
        if index.is_file() and app_js.is_file():
            return ReadinessItem(
                item_id="web_console_static",
                name="Web Console 静态资源",
                status="ready",
                severity="required",
                detail="控制台页面、脚本和样式已随 Python 包可发现。",
                path=str(index),
            )
    except Exception as exc:
        return ReadinessItem(
            item_id="web_console_static",
            name="Web Console 静态资源",
            status="blocked",
            severity="required",
            detail=f"静态资源不可读取：{exc}",
            command="python -m pip install -e .",
        )
    return ReadinessItem(
        item_id="web_console_static",
        name="Web Console 静态资源",
        status="blocked",
        severity="required",
        detail="缺少 index.html 或 app.js。",
        command="python -m pip install -e .",
    )


def _fastapi_item() -> ReadinessItem:
    has_fastapi = _find_module_spec("fastapi") is not None
    has_uvicorn = _find_module_spec("uvicorn") is not None
    if has_fastapi and has_uvicorn:
        return ReadinessItem(
            item_id="api_server_dependencies",
            name="FastAPI/Uvicorn 服务依赖",
            status="ready",
            severity="required",
            detail="API 服务和 Web Console 启动依赖可导入。",
        )
    return ReadinessItem(
        item_id="api_server_dependencies",
        name="FastAPI/Uvicorn 服务依赖",
        status="blocked",
        severity="required",
        detail="缺少 FastAPI 或 Uvicorn，Web Console 应用无法启动。",
        command='python -m pip install -e ".[api,local-sim,dev]"',
    )


def _mujoco_item() -> ReadinessItem:
    if _find_module_spec("mujoco") is not None:
        return ReadinessItem(
            item_id="mujoco_backend",
            name="MuJoCo 后端",
            status="ready",
            severity="required",
            detail="MuJoCo Python 包可导入，可运行本机物理演示。",
        )
    return ReadinessItem(
        item_id="mujoco_backend",
        name="MuJoCo 后端",
        status="blocked",
        severity="required",
        detail="缺少 mujoco Python 包，MuJoCo 预览/运行会失败。",
        command='python -m pip install -e ".[api,local-sim,dev]"',
    )


def _webots_item(executable: str) -> ReadinessItem:
    path = _which(executable) or ("/snap/bin/webots" if Path("/snap/bin/webots").exists() else "")
    if path:
        return ReadinessItem(
            item_id="webots_executable",
            name="Webots 可执行程序",
            status="ready",
            severity="optional",
            detail="Webots 可执行程序已发现，可运行 Webots 可视化演示。",
            path=path,
        )
    return ReadinessItem(
        item_id="webots_executable",
        name="Webots 可执行程序",
        status="degraded",
        severity="optional",
        detail="未找到 webots 可执行程序；MuJoCo 仍可演示，Webots 按钮会返回可解释失败信息。",
        command="安装 Webots 后确认 `webots` 在 PATH 中，或使用 MuJoCo 后端完成本机演示。",
    )


def _cpp_runtime_item(root_dir: Path) -> ReadinessItem:
    result = probe_core_runtime(root_dir)
    if result.available:
        return ReadinessItem(
            item_id="cpp_core_runtime",
            name="C++ 核心运行时",
            status="ready",
            severity="required",
            detail="qrics_core_runtime 可执行并返回核心控制闭环证据。",
            path=result.binary_path,
        )
    return ReadinessItem(
        item_id="cpp_core_runtime",
        name="C++ 核心运行时",
        status="blocked",
        severity="required",
        detail=result.error or "未找到或无法执行 qrics_core_runtime。",
        command="\n".join(
            [
                f"cd {root_dir}",
                "cmake --preset dev-gcc-debug",
                "cmake --build --preset dev-gcc-debug --target qrics_core_runtime",
                "export QRICS_CPP_CORE_RUNTIME_BIN=$PWD/build/dev-gcc-debug/qrics_core_runtime",
            ]
        ),
        path=result.binary_path,
    )


def _desktop_launcher_item(root_dir: Path) -> ReadinessItem:
    script = root_dir / "scripts" / "install_web_console_app.py"
    if script.is_file():
        return ReadinessItem(
            item_id="desktop_launcher",
            name="桌面应用安装脚本",
            status="ready",
            severity="optional",
            detail="可安装/卸载 per-user 桌面入口，满足答辩时从应用启动控制台的演示方式。",
            command=f"cd {root_dir}\npython scripts/install_web_console_app.py install --force",
            path=str(script),
        )
    return ReadinessItem(
        item_id="desktop_launcher",
        name="桌面应用安装脚本",
        status="degraded",
        severity="optional",
        detail="缺少桌面入口安装脚本；仍可用 scripts/run_web_console.py 启动。",
        command=f"cd {root_dir}\npython scripts/run_web_console.py --host 127.0.0.1 --port 8000",
    )


def _state_dir_item(state_dir: Path) -> ReadinessItem:
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        probe = state_dir / ".qrics_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return ReadinessItem(
            item_id="state_dir",
            name="本机状态目录",
            status="ready",
            severity="required",
            detail="SQLite 元数据和本地对象存储目录可写。",
            path=str(state_dir),
        )
    except OSError as exc:
        return ReadinessItem(
            item_id="state_dir",
            name="本机状态目录",
            status="blocked",
            severity="required",
            detail=f"状态目录不可写：{exc}",
            command=f"mkdir -p {state_dir} && chmod u+rwx {state_dir}",
            path=str(state_dir),
        )


def probe_core_runtime(root_dir: Path | None = None, timeout_s: float = 5.0) -> CoreRuntimeProbe:
    """Probe qrics_core_runtime without importing qrics.api to keep CLI startup acyclic."""

    binary = _locate_core_runtime_binary(root_dir or _project_root())
    if binary is None:
        return CoreRuntimeProbe(
            available=False,
            error=(
                "qrics_core_runtime binary not found; build it with "
                "`cmake --preset dev-gcc-debug && cmake --build --preset dev-gcc-debug`."
            ),
        )
    command = (
        str(binary),
        "--run-id",
        "py_core_probe",
        "--backend",
        "minimal",
        "--profile",
        "headless_fast",
        "--terrain",
        "flat",
        "--scene-id",
        "api_demo_scene",
        "--scene-version",
        "0.1.0",
        "--steps",
        "8",
        "--task-path",
        "A:0.18:0:0.35:0",
    )
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except Exception as exc:
        return CoreRuntimeProbe(
            available=False,
            binary_path=str(binary),
            command=command,
            error=f"failed to execute C++ core runtime: {exc}",
        )
    if completed.returncode != 0:
        return CoreRuntimeProbe(
            available=False,
            binary_path=str(binary),
            command=command,
            error=(
                completed.stderr or completed.stdout or f"exit code {completed.returncode}"
            ).strip(),
        )
    try:
        summary = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return CoreRuntimeProbe(
            available=False,
            binary_path=str(binary),
            command=command,
            error=f"C++ runtime returned non-JSON output: {exc}",
        )
    if not isinstance(summary, dict):
        return CoreRuntimeProbe(
            available=False,
            binary_path=str(binary),
            command=command,
            error="C++ runtime returned JSON that is not an object.",
        )
    return CoreRuntimeProbe(
        available=True,
        binary_path=str(binary),
        command=command,
        summary=summary,
    )


def _locate_core_runtime_binary(root_dir: Path) -> Path | None:
    env_path = os.environ.get("QRICS_CPP_CORE_RUNTIME_BIN", "").strip()
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    for candidate in (
        root_dir / "build" / "dev-gcc-debug" / "qrics_core_runtime",
        root_dir / "build" / "release-gcc" / "qrics_core_runtime",
        root_dir / "build" / "dev-clang-debug" / "qrics_core_runtime",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    path_binary = _which("qrics_core_runtime")
    return Path(path_binary) if path_binary else None


def _aggregate_status(items: tuple[ReadinessItem, ...]) -> ReadinessStatus:
    if any(item.status == "blocked" and item.severity == "required" for item in items):
        return "blocked"
    if any(item.status != "ready" for item in items):
        return "degraded"
    return "ready"


def _summary_text(status: ReadinessStatus, items: tuple[ReadinessItem, ...]) -> str:
    ready = sum(1 for item in items if item.status == "ready")
    degraded = sum(1 for item in items if item.status == "degraded")
    blocked = sum(1 for item in items if item.status == "blocked")
    if status == "ready":
        prefix = "本机演示链路已就绪。"
    elif status == "degraded":
        prefix = "本机演示链路可运行，但存在非必需能力缺失。"
    else:
        prefix = "本机演示链路仍有必需能力未就绪。"
    return f"{prefix} ready={ready}, degraded={degraded}, blocked={blocked}."


def _deduplicate_commands(commands: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for command in commands:
        stripped = command.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        result.append(stripped)
    return tuple(result)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]
