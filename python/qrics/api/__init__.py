"""QRICS dependency-free API facade."""

from qrics.api.app import QricsApiApp, create_demo_app
from qrics.api.schemas import RequestContext

__all__ = ["QricsApiApp", "RequestContext", "create_demo_app"]
