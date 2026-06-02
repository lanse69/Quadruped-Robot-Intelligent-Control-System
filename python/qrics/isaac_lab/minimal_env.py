"""Backward-compatible MinimalQuadrupedEnv import.

New code should import qrics.sim.backends.minimal_env.MinimalQuadrupedEnv.
"""

from qrics.sim.backends.minimal_env import MinimalQuadrupedEnv

__all__ = ["MinimalQuadrupedEnv"]
