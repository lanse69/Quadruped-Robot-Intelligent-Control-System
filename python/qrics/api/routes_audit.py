"""Audit API route facade functions."""

from __future__ import annotations

from qrics.api.app import QricsApiApp
from qrics.api.schemas import ApiResponse, AuditQuery, RequestContext


def query_audit(app: QricsApiApp, query: AuditQuery, context: RequestContext) -> ApiResponse:
    return app.query_audit(query, context)
