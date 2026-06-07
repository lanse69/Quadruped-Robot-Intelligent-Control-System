"""Desktop integration helpers for the QRICS Web Console.

The installer uses only standard-library file operations.  On Linux it writes a
per-user ``.desktop`` entry.  On Windows it writes a Start Menu ``.cmd`` entry.
On macOS it writes a runnable ``.command`` launcher under ``~/Applications``.
The generated launchers all start the same local Web Console package entry point
and keep MuJoCo/Webots selection inside the application UI.
"""

from __future__ import annotations

import os
import platform as platform_module
import shlex
import stat
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, TypeAlias

from qrics.webui.launcher import default_state_dir

APP_ID = "qrics-web-console"
LAUNCHER_NAME = "qrics-web-console"
DESKTOP_FILENAME = "qrics-web-console.desktop"
WINDOWS_APP_FILENAME = "QRICS Web Console.cmd"
MACOS_APP_FILENAME = "QRICS Web Console.command"

DesktopPlatform: TypeAlias = Literal["auto", "linux", "windows", "macos"]
ResolvedDesktopPlatform: TypeAlias = Literal["linux", "windows", "macos"]


def _default_python_executable() -> Path:
    return Path(sys.executable)


@dataclass(frozen=True)
class DesktopInstallConfig:
    """Configuration used to install a local desktop launcher."""

    host: str = "127.0.0.1"
    port: int = 8000
    state_dir: Path = field(default_factory=default_state_dir)
    python_executable: Path = field(default_factory=_default_python_executable)
    launcher_dir: Path | None = None
    applications_dir: Path | None = None
    force: bool = False
    platform: DesktopPlatform = "auto"


@dataclass(frozen=True)
class DesktopInstallResult:
    """Files touched by a desktop install or uninstall operation."""

    launcher_path: Path
    desktop_entry_path: Path
    state_dir: Path
    platform: ResolvedDesktopPlatform = "linux"


def install_desktop_app(
    config: DesktopInstallConfig | None = None,
) -> DesktopInstallResult:
    """Install a per-user launcher for the QRICS Web Console."""

    config = _coerce_config(config)
    resolved = _resolve_platform(config.platform)
    launcher_path = _launcher_path(config, resolved)
    desktop_entry_path = _desktop_entry_path(config, resolved)
    state_dir = config.state_dir.expanduser()

    _guard_existing(launcher_path, config.force)
    if desktop_entry_path != launcher_path:
        _guard_existing(desktop_entry_path, config.force)

    launcher_path.parent.mkdir(parents=True, exist_ok=True)
    desktop_entry_path.parent.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    launcher_content = _launcher_script_content(config, resolved)
    launcher_path.write_text(launcher_content, encoding="utf-8")
    if resolved in {"linux", "macos"}:
        launcher_path.chmod(
            launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )

    desktop_content = _desktop_entry_content(launcher_path, resolved)
    desktop_entry_path.write_text(desktop_content, encoding="utf-8")
    if resolved == "macos":
        desktop_entry_path.chmod(
            desktop_entry_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        )

    return DesktopInstallResult(
        launcher_path=launcher_path,
        desktop_entry_path=desktop_entry_path,
        state_dir=state_dir,
        platform=resolved,
    )


def uninstall_desktop_app(
    config: DesktopInstallConfig | None = None,
) -> DesktopInstallResult:
    """Remove the per-user QRICS launcher and application entry."""

    config = _coerce_config(config)
    resolved = _resolve_platform(config.platform)
    launcher_path = _launcher_path(config, resolved)
    desktop_entry_path = _desktop_entry_path(config, resolved)
    for path in (desktop_entry_path, launcher_path):
        with suppress(FileNotFoundError):
            path.unlink()
    return DesktopInstallResult(
        launcher_path=launcher_path,
        desktop_entry_path=desktop_entry_path,
        state_dir=config.state_dir.expanduser(),
        platform=resolved,
    )


def launcher_preview(config: DesktopInstallConfig | None = None) -> str:
    """Return the launcher script content without writing files."""

    config = _coerce_config(config)
    return _launcher_script_content(config, _resolve_platform(config.platform))


def desktop_entry_preview(config: DesktopInstallConfig | None = None) -> str:
    """Return the application entry content without writing files."""

    config = _coerce_config(config)
    resolved = _resolve_platform(config.platform)
    return _desktop_entry_content(_launcher_path(config, resolved), resolved)


def _coerce_config(config: DesktopInstallConfig | None) -> DesktopInstallConfig:
    return config if config is not None else DesktopInstallConfig()


def _resolve_platform(platform: DesktopPlatform) -> ResolvedDesktopPlatform:
    if platform == "linux":
        return "linux"
    if platform == "windows":
        return "windows"
    if platform == "macos":
        return "macos"
    system = platform_module.system().lower()
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "macos"
    return "linux"


def _guard_existing(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass force=True to overwrite")


def _launcher_path(config: DesktopInstallConfig, resolved: ResolvedDesktopPlatform) -> Path:
    if config.launcher_dir is not None:
        root = config.launcher_dir
    elif resolved == "windows":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "QRICS"
    else:
        root = Path(os.environ.get("XDG_BIN_HOME") or Path.home() / ".local" / "bin")

    suffix = ".cmd" if resolved == "windows" else ""
    return root.expanduser() / f"{LAUNCHER_NAME}{suffix}"


def _desktop_entry_path(config: DesktopInstallConfig, resolved: ResolvedDesktopPlatform) -> Path:
    if config.applications_dir is not None:
        root = config.applications_dir
    elif resolved == "windows":
        root = (
            Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )
    elif resolved == "macos":
        root = Path.home() / "Applications"
    else:
        root = (
            Path(
                os.environ.get(
                    "XDG_DATA_HOME",
                    Path.home() / ".local" / "share",
                )
            )
            / "applications"
        )

    filename = {
        "linux": DESKTOP_FILENAME,
        "windows": WINDOWS_APP_FILENAME,
        "macos": MACOS_APP_FILENAME,
    }[resolved]
    return root.expanduser() / filename


def _launcher_script_content(
    config: DesktopInstallConfig,
    resolved: ResolvedDesktopPlatform,
) -> str:
    if resolved == "windows":
        python = _windows_quote(str(config.python_executable.expanduser()))
        state_dir = _windows_quote(str(config.state_dir.expanduser()))
        host = _windows_quote(config.host)
        port = _windows_quote(str(config.port))
        launch_command = (
            f"{python} -m qrics.webui.launcher "
            f"--host {host} --port {port} --state-dir {state_dir} %*"
        )
        return "\r\n".join(
            [
                "@echo off",
                "setlocal",
                launch_command,
                "exit /b %ERRORLEVEL%",
                "",
            ]
        )

    python = shlex.quote(str(config.python_executable.expanduser()))
    state_dir = shlex.quote(str(config.state_dir.expanduser()))
    host = shlex.quote(config.host)
    port = shlex.quote(str(config.port))
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            " ".join(
                [
                    f"exec {python} -m qrics.webui.launcher",
                    f"--host {host}",
                    f"--port {port}",
                    f"--state-dir {state_dir}",
                    '"$@"',
                ]
            ),
            "",
        ]
    )


def _desktop_entry_content(
    launcher_path: Path,
    resolved: ResolvedDesktopPlatform,
) -> str:
    exec_path = str(launcher_path.expanduser())
    if resolved == "windows":
        return "\r\n".join(
            [
                "@echo off",
                f"call {_windows_quote(exec_path)} %*",
                "exit /b %ERRORLEVEL%",
                "",
            ]
        )
    if resolved == "macos":
        return "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f'exec {shlex.quote(exec_path)} "$@"',
                "",
            ]
        )
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            "Name=QRICS Web Console",
            "Name[zh_CN]=QRICS 四足智控演示控制台",
            "Comment=MuJoCo/Webots local quadruped simulation console",
            "Comment[zh_CN]=MuJoCo/Webots 本机四足机器人仿真演示控制台",
            f"Exec={exec_path}",
            "Terminal=true",
            "Categories=Development;Science;Education;Robotics;",
            "StartupNotify=true",
            "",
        ]
    )


def _windows_quote(value: str) -> str:
    escaped = value.replace('"', '""')
    return f'"{escaped}"'
