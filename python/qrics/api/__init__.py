"""QRICS dependency-free API facade."""

from qrics.api.app import QricsApiApp, create_demo_app
from qrics.api.repository import InMemoryRepository, QricsRepository
from qrics.api.schemas import (
    RequestContext,
    SceneAssetPayload,
    SceneCopyPayload,
    SceneCreatePayload,
    SceneProfilePayload,
)
from qrics.api.simulation_runner import (
    LocalSimulationRunner,
    SimulationRunRequest,
    SimulationRunSummary,
)

__all__ = [
    "QricsApiApp",
    "RequestContext",
    "SceneAssetPayload",
    "SceneCopyPayload",
    "SceneCreatePayload",
    "SceneProfilePayload",
    "create_demo_app",
    "LocalSimulationRunner",
    "SimulationRunRequest",
    "SimulationRunSummary",
    "InMemoryRepository",
    "QricsRepository",
]
