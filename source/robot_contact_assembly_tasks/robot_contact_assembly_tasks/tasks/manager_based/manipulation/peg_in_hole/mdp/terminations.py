from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import quat_error_magnitude

from ..constants import PEG_TIP_BODY_OFFSET_POS
from .observations import _socket_pose_w, _tool_tip_pose_w, tip_to_socket_position

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def insertion_metrics(
    env: ManagerBasedRLEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Return lateral, axial and rotational insertion errors."""

    rel_pos = tip_to_socket_position(env, command_name, asset_cfg, body_offset=body_offset)
    _, tip_quat_w = _tool_tip_pose_w(env, asset_cfg, body_offset=body_offset)
    _, socket_quat_w = _socket_pose_w(env, command_name, asset_cfg)
    lateral_error = torch.linalg.norm(rel_pos[:, :2], dim=1)
    axial_error = torch.abs(rel_pos[:, 2])
    rot_error = quat_error_magnitude(tip_quat_w, socket_quat_w)
    return lateral_error, axial_error, rot_error


def insertion_success(
    env: ManagerBasedRLEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
    xy_tolerance: float = 0.003,
    z_tolerance: float = 0.003,
    rot_tolerance: float = 0.15,
) -> torch.Tensor:
    """Terminate when the peg-tip target is reached with insertion-level tolerances."""

    lateral_error, axial_error, rot_error = insertion_metrics(
        env,
        command_name,
        asset_cfg,
        body_offset=body_offset,
    )
    return (lateral_error < xy_tolerance) & (axial_error < z_tolerance) & (rot_error < rot_tolerance)
