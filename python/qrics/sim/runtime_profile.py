"""Runtime profiles for local simulation backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

RenderMode: TypeAlias = Literal["none", "viewer", "offscreen"]


@dataclass(frozen=True)
class RuntimeProfile:
    name: str
    render_mode: RenderMode
    width: int = 1280
    height: int = 720
    physics_timestep_s: float = 0.002
    control_decimation: int = 10
    camera_preview_enabled: bool = False
    video_record_enabled: bool = False
    contact_sensor_enabled: bool = True
    imu_enabled: bool = True
    max_demo_seconds: float = 60.0


PROFILES: dict[str, RuntimeProfile] = {
    "headless_fast": RuntimeProfile(
        name="headless_fast",
        render_mode="none",
        width=640,
        height=480,
        physics_timestep_s=0.004,
        control_decimation=10,
        max_demo_seconds=120.0,
    ),
    "balanced_visual": RuntimeProfile(
        name="balanced_visual",
        render_mode="viewer",
        width=1280,
        height=720,
        physics_timestep_s=0.002,
        control_decimation=10,
        max_demo_seconds=60.0,
    ),
    "webots_fast": RuntimeProfile(
        name="webots_fast",
        render_mode="viewer",
        width=1280,
        height=720,
        physics_timestep_s=0.016,
        control_decimation=2,
        camera_preview_enabled=True,
        max_demo_seconds=90.0,
    ),
    "rich_demo": RuntimeProfile(
        name="rich_demo",
        render_mode="viewer",
        width=1280,
        height=720,
        physics_timestep_s=0.002,
        control_decimation=10,
        camera_preview_enabled=True,
        video_record_enabled=True,
        max_demo_seconds=60.0,
    ),
}


def get_runtime_profile(name: str) -> RuntimeProfile:
    try:
        return PROFILES[name]
    except KeyError as exc:
        allowed = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unknown runtime profile: {name}. Allowed profiles: {allowed}") from exc
