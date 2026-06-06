"""Linux desktop integration helpers for the QRICS Web Console."""

from __future__ import annotations

import os
import shlex
import stat
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

from qrics.webui.launcher import default_state_dir

APP_ID = "qrics-web-console"
LAUNCHER_NAME = "qrics-web-console"
DESKTOP_FILENAME = "qrics-web-console.desktop"


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


@dataclass(frozen=True)
class DesktopInstallResult:
    """Files touched by a desktop install or uninstall operation."""

    launcher_path: Path
    desktop_entry_path: Path
    state_dir: Path


def install_desktop_app(
    config: DesktopInstallConfig | None = None,
) -> DesktopInstallResult:
    """Install a per-user Linux desktop entry for the QRICS Web Console."""

    config = _coerce_config(config)
    launcher_path = _launcher_path(config)
    desktop_entry_path = _desktop_entry_path(config)
    state_dir = config.state_dir.expanduser()

    _guard_existing(launcher_path, config.force)
    _guard_existing(desktop_entry_path, config.force)

    launcher_path.parent.mkdir(parents=True, exist_ok=True)
    desktop_entry_path.parent.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    launcher_path.write_text(_launcher_script_content(config), encoding="utf-8")
    launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    desktop_entry_path.write_text(_desktop_entry_content(launcher_path), encoding="utf-8")

    return DesktopInstallResult(
        launcher_path=launcher_path,
        desktop_entry_path=desktop_entry_path,
        state_dir=state_dir,
    )


def uninstall_desktop_app(
    config: DesktopInstallConfig | None = None,
) -> DesktopInstallResult:
    """Remove the per-user QRICS desktop entry and launcher script."""

    config = _coerce_config(config)
    launcher_path = _launcher_path(config)
    desktop_entry_path = _desktop_entry_path(config)
    for path in (desktop_entry_path, launcher_path):
        with suppress(FileNotFoundError):
            path.unlink()
    return DesktopInstallResult(
        launcher_path=launcher_path,
        desktop_entry_path=desktop_entry_path,
        state_dir=config.state_dir.expanduser(),
    )


def launcher_preview(config: DesktopInstallConfig | None = None) -> str:
    """Return the launcher script content without writing files."""

    return _launcher_script_content(_coerce_config(config))


def desktop_entry_preview(config: DesktopInstallConfig | None = None) -> str:
    """Return the desktop entry content without writing files."""

    config = _coerce_config(config)
    return _desktop_entry_content(_launcher_path(config))


def _coerce_config(config: DesktopInstallConfig | None) -> DesktopInstallConfig:
    return config if config is not None else DesktopInstallConfig()


def _guard_existing(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass force=True to overwrite")


def _launcher_path(config: DesktopInstallConfig) -> Path:
    root = config.launcher_dir or Path(
        os.environ.get("XDG_BIN_HOME") or Path.home() / ".local" / "bin"
    )
    return root.expanduser() / LAUNCHER_NAME


def _desktop_entry_path(config: DesktopInstallConfig) -> Path:
    root = (
        config.applications_dir
        or Path(
            os.environ.get(
                "XDG_DATA_HOME",
                Path.home() / ".local" / "share",
            )
        )
        / "applications"
    )
    return root.expanduser() / DESKTOP_FILENAME


def _launcher_script_content(config: DesktopInstallConfig) -> str:
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


def _desktop_entry_content(launcher_path: Path) -> str:
    exec_path = str(launcher_path.expanduser())
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
