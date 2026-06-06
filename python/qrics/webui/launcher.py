"""Runnable entry point for the local QRICS Web Console.

The module is intentionally kept inside the installable Python package so a
Linux desktop launcher can start the same console without depending on the
repository checkout path.  FastAPI and Uvicorn are imported only when the
launcher is executed; importing :mod:`qrics.webui` remains lightweight.
"""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def default_state_dir() -> Path:
    """Return the default persistent state directory for the console."""

    return Path.home() / ".local" / "share" / "qrics" / "console"


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the Web Console launcher argument parser."""

    parser = argparse.ArgumentParser(description="Run QRICS local Web Console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--state-dir",
        default=str(default_state_dir()),
        help="Directory for SQLite metadata and immutable local object store.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the service without opening the browser automatically.",
    )
    parser.add_argument(
        "--browser-delay-s",
        type=float,
        default=1.0,
        help="Seconds to wait before opening the browser.",
    )
    return parser


def create_console_http_app(state_dir: Path) -> Any:
    """Create the FastAPI application backed by local persistent storage."""

    from qrics.api.app import create_demo_app
    from qrics.api.http_app import create_http_app
    from qrics.api.sqlite_repository import SQLiteQricsRepository
    from qrics.storage.object_store import FileObjectStore

    object_store = FileObjectStore(state_dir / "object_store")
    repository = SQLiteQricsRepository(state_dir / "qrics.sqlite3", object_store=object_store)
    return create_http_app(create_demo_app(repository=repository))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local Web Console service."""

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    import uvicorn

    state_dir = Path(args.state_dir).expanduser().resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    http_app = create_console_http_app(state_dir)
    url = f"http://{args.host}:{args.port}/console/"

    if not args.no_browser:
        threading.Thread(
            target=_open_browser_later,
            args=(url, args.browser_delay_s),
            daemon=True,
        ).start()

    print(f"QRICS Web Console: {url}")
    print(f"State directory: {state_dir}")
    print("Use MuJoCo/Webots from the UI. Use --no-browser on headless hosts.")
    uvicorn.run(http_app, host=args.host, port=args.port)
    return 0


def _open_browser_later(url: str, delay_s: float) -> None:
    time.sleep(max(0.0, delay_s))
    webbrowser.open(url)


if __name__ == "__main__":
    raise SystemExit(main())
