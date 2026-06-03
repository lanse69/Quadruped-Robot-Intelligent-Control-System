#!/usr/bin/env python3
"""Check local simulation dependencies for QRICS.

The check is intentionally strict for MuJoCo because the current local
simulation stage depends on it as the real-physics backend.  Webots and Isaac
Lab/Isaac Sim are reported as optional backends and do not fail this script when
missing.
"""

from __future__ import annotations

import importlib
import importlib.util
import platform
import shutil
import sys
from pathlib import Path
from types import ModuleType

ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT_DIR / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))


def _status_line(name: str, ok: bool, detail: str = "") -> str:
    marker = "OK" if ok else "MISSING"
    suffix = f" - {detail}" if detail else ""
    return f"{name}: {marker}{suffix}"


def _find_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _import_module(name: str) -> ModuleType | None:
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _check_mujoco_step() -> tuple[bool, str]:
    mujoco = _import_module("mujoco")
    if mujoco is None:
        return False, "mujoco is not importable. Install project dependencies in .venv first."

    try:
        xml = """
<mujoco model="qrics_mj_step_check">
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="floor" type="plane" size="1 1 0.1"/>
    <body name="box" pos="0 0 0.3">
      <freejoint/>
      <geom name="box_geom" type="box" size="0.05 0.05 0.05" mass="0.1"/>
    </body>
  </worldbody>
</mujoco>
"""
        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        for _ in range(10):
            mujoco.mj_step(model, data)
    except Exception as exc:
        return False, f"MuJoCo import succeeded, but mj_step failed: {exc!r}"

    version = getattr(mujoco, "__version__", "installed")
    return True, f"mujoco {version}; mj_step OK; simulated_time_s={float(data.time):.4f}"


def _check_optional_python_module(name: str) -> str:
    module = _import_module(name)
    if module is None:
        return _status_line(name, False, "optional backend not installed")
    version = getattr(module, "__version__", "installed")
    return _status_line(name, True, str(version))


def main() -> int:
    print("QRICS local simulation environment check")
    print(f"repository_root: {ROOT_DIR}")
    print(f"python: {sys.version.split()[0]}")
    print(f"platform: {platform.platform()}")
    print(f"python_package_dir: {PYTHON_DIR}")
    print()

    mujoco_ok, mujoco_detail = _check_mujoco_step()
    print(_status_line("mujoco", mujoco_ok, mujoco_detail))

    webots_path = shutil.which("webots")
    print(_status_line("webots_command", webots_path is not None, webots_path or "optional"))

    snap_webots = Path("/snap/bin/webots")
    print(_status_line("webots_snap", snap_webots.exists(), str(snap_webots) if snap_webots.exists() else "optional"))

    for module_name in ("isaaclab", "isaacsim", "omni", "carb"):
        print(_check_optional_python_module(module_name))

    print()
    if mujoco_ok and webots_path is not None:
        recommended_profile = "balanced_visual"
    elif mujoco_ok:
        recommended_profile = "balanced_visual"
    else:
        recommended_profile = "minimal_contract_only"
    print(f"recommended_profile: {recommended_profile}")
    print("note: Isaac Lab/Isaac Sim absence is informational here; MuJoCo is the required local backend.")

    return 0 if mujoco_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())