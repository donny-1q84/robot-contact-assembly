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
from .terminations import insertion_metrics, insertion_success

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def tip_position_error(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """L2 peg-tip position error in the physical socket frame."""

    rel_pos = tip_to_socket_position(env, peg_cfg, socket_cfg)
    return torch.linalg.norm(rel_pos, dim=1)


def tip_position_error_tanh(
    env: ManagerBasedRLEnv,
    std: float,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Tanh-shaped reward for physical peg-tip position tracking."""

    distance = tip_position_error(env, peg_cfg, socket_cfg)
    return 1.0 - torch.tanh(distance / std)


def tip_orientation_error(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Shortest-path orientation error between the peg tip and the socket frame."""

    _, tip_quat_w = _peg_tip_pose_w(env, peg_cfg)
    _, socket_quat_w = _socket_pose_w(env, socket_cfg)
    return quat_error_magnitude(tip_quat_w, socket_quat_w)


def tip_orientation_error_tanh(
    env: ManagerBasedRLEnv,
    std: float,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Tanh-shaped reward for peg-tip orientation tracking."""

    orientation_error = tip_orientation_error(env, peg_cfg, socket_cfg)
    return 1.0 - torch.tanh(orientation_error / std)


def approach_pose_reward(
    env: ManagerBasedRLEnv,
    lateral_std: float,
    axial_std: float,
    rot_std: float,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
    axial_weight: float = 0.40,
) -> torch.Tensor:
    """Simple coupled pose reward for the contact-guided insertion shell."""

    lateral_error, axial_error, rot_error = insertion_metrics(env, peg_cfg, socket_cfg)
    lateral_term = 1.0 - torch.tanh(lateral_error / lateral_std)
    axial_term = 1.0 - torch.tanh(axial_error / axial_std)
    rot_term = 1.0 - torch.tanh(rot_error / rot_std)
    coupled_alignment = torch.sqrt(torch.clamp(lateral_term * rot_term, min=0.0))
    return coupled_alignment + axial_weight * axial_term * coupled_alignment


def insertion_progress_reward(
    env: ManagerBasedRLEnv,
    std: float,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
    lateral_tolerance: float,
    lateral_std: float,
    rot_tolerance: float,
    rot_std: float,
) -> torch.Tensor:
    """Dense insertion reward once the peg is centered and rotation is nearly correct."""

    lateral_error, axial_error, rot_error = insertion_metrics(env, peg_cfg, socket_cfg)
    shaped = 1.0 - torch.tanh(axial_error / std)
    lateral_margin = torch.clamp(lateral_error - lateral_tolerance, min=0.0)
    rot_margin = torch.clamp(rot_error - rot_tolerance, min=0.0)
    lateral_gate = torch.exp(-torch.square(lateral_margin / lateral_std))
    rot_gate = torch.exp(-torch.square(rot_margin / rot_std))
    return shaped * lateral_gate * rot_gate


def insertion_success_reward(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
    xy_tolerance: float = SOCKET_SUCCESS_XY_TOLERANCE_M,
    z_tolerance: float = SOCKET_SUCCESS_Z_TOLERANCE_M,
    rot_tolerance: float = SOCKET_SUCCESS_ROT_TOLERANCE_RAD,
) -> torch.Tensor:
    """Binary success reward using the physical socket frame."""

    return insertion_success(
        env,
        peg_cfg,
        socket_cfg,
        xy_tolerance=xy_tolerance,
        z_tolerance=z_tolerance,
        rot_tolerance=rot_tolerance,
    ).float()
