"""Deterministic metric aggregation utilities for placeholder evaluation results."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class EpisodeSummary:
    success: bool
    collision: bool
    tracking_error_m: float
    recovered: bool
    energy_proxy: float
    hard_constraint_violation_count: int = 0


@dataclass(frozen=True)
class MetricsDigest:
    success_rate: float
    collision_rate: float
    tracking_error_m: float
    recovery_rate: float
    energy_proxy: float
    hard_constraint_violation_count: int


def calculate_metrics(episodes: Sequence[EpisodeSummary]) -> MetricsDigest:
    """Aggregate episode-level results into the same digest shape as C++ MetricsDigest."""
    if not episodes:
        raise ValueError("episodes must not be empty")

    count = len(episodes)
    success_rate = sum(1 for item in episodes if item.success) / count
    collision_rate = sum(1 for item in episodes if item.collision) / count
    tracking_error_m = sum(item.tracking_error_m for item in episodes) / count
    recovery_rate = sum(1 for item in episodes if item.recovered) / count
    energy_proxy = sum(item.energy_proxy for item in episodes) / count
    hard_constraint_violation_count = sum(item.hard_constraint_violation_count for item in episodes)

    return MetricsDigest(
        success_rate=success_rate,
        collision_rate=collision_rate,
        tracking_error_m=tracking_error_m,
        recovery_rate=recovery_rate,
        energy_proxy=energy_proxy,
        hard_constraint_violation_count=hard_constraint_violation_count,
    )
