#!/usr/bin/env python3
"""Install or uninstall the QRICS Web Console as a per-user desktop app."""

from __future__ import annotations

import argparse
from pathlib import Path

from qrics.webui.desktop import (
    DesktopInstallConfig,
    desktop_entry_preview,
    install_desktop_app,
    launcher_preview,
    uninstall_desktop_app,
)
from qrics.webui.launcher import default_state_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Install QRICS Web Console desktop launcher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="Install the desktop app")
    _add_common_options(install)
    install.add_argument("--force", action="store_true", help="Overwrite existing launcher files")
    install.add_argument("--dry-run", action="store_true", help="Print files that would be written")

    uninstall = subparsers.add_parser("uninstall", help="Remove the desktop app")
    _add_common_options(uninstall)

    args = parser.parse_args()
    config = DesktopInstallConfig(
        host=args.host,
        port=args.port,
        state_dir=Path(args.state_dir).expanduser(),
        launcher_dir=Path(args.launcher_dir).expanduser() if args.launcher_dir else None,
        applications_dir=(
            Path(args.applications_dir).expanduser() if args.applications_dir else None
        ),
        force=getattr(args, "force", False),
        platform=args.platform,
    )

    if args.command == "install" and args.dry_run:
        print("--- launcher script ---")
        print(launcher_preview(config), end="")
        print("--- desktop entry ---")
        print(desktop_entry_preview(config), end="")
        return 0

    if args.command == "install":
        result = install_desktop_app(config)
        print(f"Installed launcher: {result.launcher_path}")
        print(f"Installed application entry: {result.desktop_entry_path}")
        print(f"Platform: {result.platform}")
        print(f"State directory: {result.state_dir}")
        return 0

    result = uninstall_desktop_app(config)
    print(f"Removed application entry if present: {result.desktop_entry_path}")
    print(f"Removed launcher if present: {result.launcher_path}")
    print(f"Platform: {result.platform}")
    return 0


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--state-dir", default=str(default_state_dir()))
    parser.add_argument("--launcher-dir", default="", help="Override launcher directory")
    parser.add_argument("--applications-dir", default="", help="Override application entry directory")
    parser.add_argument(
        "--platform",
        choices=("auto", "linux", "windows", "macos"),
        default="auto",
        help="Application launcher target platform; auto detects the current OS.",
    )


if __name__ == "__main__":
    raise SystemExit(main())