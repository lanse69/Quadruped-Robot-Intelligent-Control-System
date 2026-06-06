from __future__ import annotations

import os
import stat
from dataclasses import replace
from pathlib import Path

import pytest

from qrics.webui.desktop import DesktopInstallConfig, install_desktop_app, uninstall_desktop_app


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
