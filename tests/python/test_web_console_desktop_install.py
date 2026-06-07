from __future__ import annotations

import os
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from qrics.webui.desktop import (
    DesktopInstallConfig,
    desktop_entry_preview,
    install_desktop_app,
    launcher_preview,
    uninstall_desktop_app,
)


def test_install_desktop_app_writes_launcher_and_desktop_entry(tmp_path: Path) -> None:
    config = DesktopInstallConfig(
        host="127.0.0.1",
        port=8123,
        state_dir=tmp_path / "state",
        python_executable=Path("/usr/bin/python3"),
        launcher_dir=tmp_path / "bin",
        applications_dir=tmp_path / "applications",
    )

    result = install_desktop_app(config)

    launcher = result.launcher_path.read_text(encoding="utf-8")
    desktop_entry = result.desktop_entry_path.read_text(encoding="utf-8")
    assert "python3 -m qrics.webui.launcher" in launcher
    assert "--port 8123" in launcher
    assert str(config.state_dir) in launcher
    assert os.access(result.launcher_path, os.X_OK)
    assert stat.S_IMODE(result.launcher_path.stat().st_mode) & stat.S_IXUSR
    assert "Name[zh_CN]=QRICS 四足智控演示控制台" in desktop_entry
    assert f"Exec={result.launcher_path}" in desktop_entry
    assert result.state_dir.exists()
    assert result.platform == "linux"


def test_install_desktop_app_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    config = DesktopInstallConfig(
        state_dir=tmp_path / "state",
        python_executable=Path("/usr/bin/python3"),
        launcher_dir=tmp_path / "bin",
        applications_dir=tmp_path / "applications",
    )

    install_desktop_app(config)

    with pytest.raises(FileExistsError):
        install_desktop_app(config)

    forced = install_desktop_app(replace(config, force=True))
    assert forced.launcher_path.exists()
    assert forced.desktop_entry_path.exists()


def test_uninstall_desktop_app_is_idempotent(tmp_path: Path) -> None:
    config = DesktopInstallConfig(
        state_dir=tmp_path / "state",
        python_executable=Path("/usr/bin/python3"),
        launcher_dir=tmp_path / "bin",
        applications_dir=tmp_path / "applications",
    )
    installed = install_desktop_app(config)

    removed = uninstall_desktop_app(config)
    assert removed.launcher_path == installed.launcher_path
    assert not installed.launcher_path.exists()
    assert not installed.desktop_entry_path.exists()

    removed_again = uninstall_desktop_app(config)
    assert removed_again.launcher_path == installed.launcher_path


def test_install_windows_app_writes_start_menu_command(tmp_path: Path) -> None:
    config = DesktopInstallConfig(
        host="127.0.0.1",
        port=8123,
        state_dir=tmp_path / "state",
        python_executable=Path(r"C:\Python311\python.exe"),
        launcher_dir=tmp_path / "bin",
        applications_dir=tmp_path / "start-menu",
        platform="windows",
    )

    result = install_desktop_app(config)

    launcher = result.launcher_path.read_text(encoding="utf-8")
    start_menu_entry = result.desktop_entry_path.read_text(encoding="utf-8")
    assert result.platform == "windows"
    assert result.launcher_path.name == "qrics-web-console.cmd"
    assert result.desktop_entry_path.name == "QRICS Web Console.cmd"
    assert "qrics.webui.launcher" in launcher
    assert '--port "8123"' in launcher
    assert str(config.state_dir) in launcher
    assert "call" in start_menu_entry
    assert str(result.launcher_path) in start_menu_entry


def test_install_macos_app_writes_command_entry(tmp_path: Path) -> None:
    config = DesktopInstallConfig(
        host="127.0.0.1",
        port=8123,
        state_dir=tmp_path / "state",
        python_executable=Path("/usr/bin/python3"),
        launcher_dir=tmp_path / "bin",
        applications_dir=tmp_path / "Applications",
        platform="macos",
    )

    result = install_desktop_app(config)

    launcher = result.launcher_path.read_text(encoding="utf-8")
    command_entry = result.desktop_entry_path.read_text(encoding="utf-8")
    assert result.platform == "macos"
    assert result.desktop_entry_path.name == "QRICS Web Console.command"
    assert "qrics.webui.launcher" in launcher
    assert f"exec {result.launcher_path}" in command_entry
    assert os.access(result.launcher_path, os.X_OK)
    assert os.access(result.desktop_entry_path, os.X_OK)


def test_desktop_previews_use_requested_platform(tmp_path: Path) -> None:
    config = DesktopInstallConfig(
        state_dir=tmp_path / "state",
        python_executable=Path("/usr/bin/python3"),
        launcher_dir=tmp_path / "bin",
        applications_dir=tmp_path / "applications",
        platform="windows",
    )

    assert launcher_preview(config).startswith("@echo off")
    assert desktop_entry_preview(config).startswith("@echo off")
