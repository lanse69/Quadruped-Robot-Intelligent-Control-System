"""Shared API error helpers."""

from __future__ import annotations

from qrics.api.schemas import ApiResponse, RequestContext


def invalid_request(context: RequestContext, message: str, field: str = "") -> ApiResponse:
    return ApiResponse.failure(
        code="INVALID_REQUEST",
        message=message,
        request_id=context.request_id,
        field=field,
    )


def not_found(context: RequestContext, object_name: str, object_id: str) -> ApiResponse:
    return ApiResponse.failure(
        code="NOT_FOUND",
        message=f"{object_name} does not exist: {object_id}",
        request_id=context.request_id,
    )


def forbidden(context: RequestContext, message: str) -> ApiResponse:
    return ApiResponse.failure(code="FORBIDDEN", message=message, request_id=context.request_id)


def conflict(context: RequestContext, message: str) -> ApiResponse:
    return ApiResponse.failure(
        code="STATE_CONFLICT",
        message=message,
        request_id=context.request_id,
    )
