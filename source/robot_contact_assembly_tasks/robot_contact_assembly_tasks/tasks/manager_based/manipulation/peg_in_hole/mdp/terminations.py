from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import quat_error_magnitude

from ..constants import (
    SOCKET_SUCCESS_ROT_TOLERANCE_RAD,
    SOCKET_SUCCESS_XY_TOLERANCE_M,
    SOCKET_SUCCESS_Z_TOLERANCE_M,
)
from .observations import _peg_tip_pose_w, _socket_pose_w, tip_to_socket_position

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def insertion_metrics(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Return lateral, axial, and rotational insertion errors against the socket frame."""

    rel_pos = tip_to_socket_position(env, peg_cfg, socket_cfg)
    _, tip_quat_w = _peg_tip_pose_w(env, peg_cfg)
    _, socket_quat_w = _socket_pose_w(env, socket_cfg)
    lateral_error = torch.linalg.norm(rel_pos[:, :2], dim=1)
    axial_error = torch.abs(rel_pos[:, 2])
    rot_error = quat_error_magnitude(tip_quat_w, socket_quat_w)
    return lateral_error, axial_error, rot_error


def insertion_success(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
    xy_tolerance: float = SOCKET_SUCCESS_XY_TOLERANCE_M,
    z_tolerance: float = SOCKET_SUCCESS_Z_TOLERANCE_M,
    rot_tolerance: float = SOCKET_SUCCESS_ROT_TOLERANCE_RAD,
) -> torch.Tensor:
    """Terminate when the physical peg tip reaches the socket-frame tolerances."""

    lateral_error, axial_error, rot_error = insertion_metrics(env, peg_cfg, socket_cfg)
    return (lateral_error < xy_tolerance) & (axial_error < z_tolerance) & (rot_error < rot_tolerance)
