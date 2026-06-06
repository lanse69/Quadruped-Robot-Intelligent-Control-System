"""Simulation presentation route facade functions."""

from __future__ import annotations

from qrics.api.app import QricsApiApp
from qrics.api.schemas import ApiResponse, RequestContext, SimulationPreviewPayload


def list_simulation_backends(app: QricsApiApp, context: RequestContext) -> ApiResponse:
    return app.list_simulation_backends(context)


def probe_cpp_core_runtime(app: QricsApiApp, context: RequestContext) -> ApiResponse:
    return app.probe_cpp_core_runtime(context)


def preview_simulation(
    app: QricsApiApp,
    payload: SimulationPreviewPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.preview_simulation(payload, context)
