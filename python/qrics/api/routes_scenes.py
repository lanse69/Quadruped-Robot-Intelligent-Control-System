"""Scene resource management route facade functions."""

from __future__ import annotations

from qrics.api.app import QricsApiApp
from qrics.api.schemas import (
    ApiResponse,
    RequestContext,
    ResourceRef,
    SceneCopyPayload,
    SceneCreatePayload,
)


def create_scene(
    app: QricsApiApp,
    payload: SceneCreatePayload,
    context: RequestContext,
) -> ApiResponse:
    return app.create_scene(payload, context)


def copy_scene(
    app: QricsApiApp,
    scene_ref: ResourceRef,
    payload: SceneCopyPayload,
    context: RequestContext,
) -> ApiResponse:
    return app.copy_scene(scene_ref, payload, context)


def publish_scene_baseline(
    app: QricsApiApp,
    scene_ref: ResourceRef,
    context: RequestContext,
    reason: str,
) -> ApiResponse:
    return app.publish_scene_baseline(scene_ref, context, reason)


def archive_scene(
    app: QricsApiApp,
    scene_ref: ResourceRef,
    context: RequestContext,
    reason: str,
) -> ApiResponse:
    return app.archive_scene(scene_ref, context, reason)


def get_scene(app: QricsApiApp, scene_ref: ResourceRef, context: RequestContext) -> ApiResponse:
    return app.get_scene(scene_ref, context)


def list_scenes(app: QricsApiApp, context: RequestContext, scene_id: str = "") -> ApiResponse:
    return app.list_scenes(context, scene_id)
