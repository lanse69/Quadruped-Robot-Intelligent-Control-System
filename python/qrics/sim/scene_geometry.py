"""Canonical local-demo scene geometry.

The Web console, MuJoCo backend and Webots backend all use these dimensions so
that demo scenes keep the same physical meaning across renderers.  The values
are intentionally expressed in meters and the semantic markers are visual-only:
platform/A/B are navigation regions, not collision obstacles.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class XY:
    x: float
    y: float


@dataclass(frozen=True)
class BoxSize:
    x: float
    y: float
    z: float


ROBOT_NOMINAL_BASE_HEIGHT_M = 0.38
ROBOT_BODY_LENGTH_M = 0.56
ROBOT_BODY_WIDTH_M = 0.26
ROBOT_BODY_HEIGHT_M = 0.12

# Semantic regions.  These are intentionally non-colliding in the simulators.
PLATFORM_CENTER = XY(0.0, 0.0)
PLATFORM_SIZE = BoxSize(0.86, 0.62, 0.018)
CHECKPOINT_A = XY(0.90, 0.34)
CHECKPOINT_B = XY(1.85, -0.30)
CHECKPOINT_RADIUS_M = 0.135
CHECKPOINT_MARKER_HEIGHT_M = 0.018

# A visual restricted/low-friction region.  The planner may avoid it, but the
# demo backends must not treat it as a physical obstacle.
NO_GO_CENTER = XY(2.45, 0.0)
NO_GO_SIZE = BoxSize(1.15, 1.65, 0.012)

# Default editable terrain blocks used by the Web console and all local backends.
# x/y are centers in meters; size.x/size.y are visible block dimensions.
TERRAIN_REGION_DEFAULTS: dict[str, tuple[XY, BoxSize]] = {
    "slope": (XY(1.55, 0.54), BoxSize(1.30, 0.60, 0.07)),
    "gravel": (XY(1.50, -0.19), BoxSize(1.40, 0.65, 0.05)),
    "stairs": (XY(1.42, -0.38), BoxSize(1.15, 0.62, 0.20)),
}

DEFAULT_OBSTACLE_RADIUS_M = 0.09
DEFAULT_OBSTACLE_HEIGHT_M = 0.28
DEFAULT_OBSTACLE_Z_M = DEFAULT_OBSTACLE_HEIGHT_M * 0.5

TASK_TARGETS: dict[str, XY] = {
    "A": CHECKPOINT_A,
    "B": CHECKPOINT_B,
    "platform": PLATFORM_CENTER,
}


def clamp_obstacle_radius(radius_m: float) -> float:
    """Keep user-authored obstacles within a stable local-demo range."""

    return max(0.035, min(0.22, float(radius_m)))


def clamp_obstacle_height(height_m: float) -> float:
    """Keep user-authored obstacle height proportional to the small quadruped."""

    return max(0.05, min(0.75, float(height_m)))
