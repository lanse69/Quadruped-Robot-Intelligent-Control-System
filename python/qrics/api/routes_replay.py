"""Replay API route facade functions."""

from __future__ import annotations

from qrics.api.app import QricsApiApp
from qrics.api.schemas import ApiResponse, ReplayQuery, RequestContext


def query_replay(app: QricsApiApp, query: ReplayQuery, context: RequestContext) -> ApiResponse:
    return app.query_replay(query, context)
