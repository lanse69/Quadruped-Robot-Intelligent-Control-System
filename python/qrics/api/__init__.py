"""QRICS dependency-free API facade."""

from qrics.api.app import QricsApiApp, create_demo_app
from qrics.api.repository import InMemoryRepository, QricsRepository
from qrics.api.schemas import (
    EvaluationReportExportPayload,
    EvaluationReportExportResponse,
    PolicyApprovalPayload,
    PolicyApprovalResponse,
    RequestContext,
    SceneAssetPayload,
    SceneCopyPayload,
    SceneCreatePayload,
    SceneProfilePayload,
    SimulationBackendCatalogResponse,
    SimulationPreviewPayload,
    SimulationRunOptionsPayload,
)
from qrics.api.simulation_runner import (
    LocalSimulationRunner,
    SimulationRunRequest,
    SimulationRunSummary,
)

__all__ = [
    "QricsApiApp",
    "EvaluationReportExportPayload",
    "EvaluationReportExportResponse",
    "PolicyApprovalPayload",
    "PolicyApprovalResponse",
    "RequestContext",
    "SceneAssetPayload",
    "SceneCopyPayload",
    "SceneCreatePayload",
    "SceneProfilePayload",
    "SimulationBackendCatalogResponse",
    "SimulationPreviewPayload",
    "SimulationRunOptionsPayload",
    "create_demo_app",
    "LocalSimulationRunner",
    "SimulationRunRequest",
    "SimulationRunSummary",
    "InMemoryRepository",
    "QricsRepository",
]
