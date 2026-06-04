#!/usr/bin/env python3
"""Run the QRICS FastAPI service for local demonstration."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from qrics.api.app import QricsApiApp, create_demo_app
from qrics.api.http_app import create_http_app
from qrics.api.sqlite_repository import SQLiteQricsRepository
from qrics.storage.object_store import FileObjectStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Run QRICS API service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--state-dir",
        default="runtime/qrics-api",
        help="Directory for SQLite metadata and immutable local object store.",
    )
    args = parser.parse_args()

    state_dir = Path(args.state_dir)
    object_store = FileObjectStore(state_dir / "object_store")
    repository = SQLiteQricsRepository(state_dir / "qrics.sqlite3", object_store=object_store)
    qrics_app = create_demo_app(repository=repository)
    http_app = create_http_app(qrics_app)
    uvicorn.run(http_app, host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
