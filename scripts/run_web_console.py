#!/usr/bin/env python3
"""Run the QRICS API service and open the local Web Console."""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from qrics.api.app import create_demo_app
from qrics.api.http_app import create_http_app
from qrics.api.sqlite_repository import SQLiteQricsRepository
from qrics.storage.object_store import FileObjectStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QRICS local Web Console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--state-dir",
        default="runtime/qrics-console",
        help="Directory for SQLite metadata and immutable local object store.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the service without opening the browser automatically.",
    )
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    object_store = FileObjectStore(state_dir / "object_store")
    repository = SQLiteQricsRepository(state_dir / "qrics.sqlite3", object_store=object_store)
    http_app = create_http_app(create_demo_app(repository=repository))
    url = f"http://{args.host}:{args.port}/console/"

    if not args.no_browser:
        threading.Thread(target=_open_browser_later, args=(url,), daemon=True).start()

    print(f"QRICS Web Console: {url}")
    print("Use MuJoCo/Webots from the UI. Use --no-browser on headless hosts.")
    uvicorn.run(http_app, host=args.host, port=args.port)


def _open_browser_later(url: str) -> None:
    time.sleep(1.0)
    webbrowser.open(url)


if __name__ == "__main__":
    main()