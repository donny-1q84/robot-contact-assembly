"""Compatibility helpers for Isaac Lab version drift."""

from __future__ import annotations

try:
    from isaaclab.utils.configclass import configclass
except ImportError:  # Isaac Lab <= 5.2 exported configclass from isaaclab.utils.
    from isaaclab.utils import configclass as _configclass

    configclass = _configclass if callable(_configclass) else _configclass.configclass

