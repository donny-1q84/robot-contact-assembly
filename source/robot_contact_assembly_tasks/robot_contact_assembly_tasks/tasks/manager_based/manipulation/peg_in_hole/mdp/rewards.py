from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import quat_error_magnitude

from ..constants import PEG_TIP_BODY_OFFSET_POS
from .observations import _socket_pose_w, _tool_tip_pose_w, tip_to_socket_position
from .terminations import insertion_metrics, insertion_success

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def tip_position_error(
    env: ManagerBasedRLEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """L2 tool-tip position error in the socket frame."""

    rel_pos = tip_to_socket_position(env, command_name, asset_cfg, body_offset=body_offset)
    return torch.linalg.norm(rel_pos, dim=1)


def tip_position_error_tanh(
    env: ManagerBasedRLEnv,
    std: float,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Tanh-shaped reward for tool-tip position tracking."""

    distance = tip_position_error(env, command_name, asset_cfg, body_offset=body_offset)
    return 1.0 - torch.tanh(distance / std)


def tip_orientation_error(
    env: ManagerBasedRLEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Shortest-path orientation error between the tool tip and target socket pose."""

    _, tip_quat_w = _tool_tip_pose_w(env, asset_cfg, body_offset=body_offset)
    _, socket_quat_w = _socket_pose_w(env, command_name, asset_cfg)
    return quat_error_magnitude(tip_quat_w, socket_quat_w)


def tip_orientation_error_tanh(
    env: ManagerBasedRLEnv,
    std: float,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Tanh-shaped reward for tool-tip orientation tracking."""

    orientation_error = tip_orientation_error(env, command_name, asset_cfg, body_offset=body_offset)
    return 1.0 - torch.tanh(orientation_error / std)


def insertion_progress_reward(
    env: ManagerBasedRLEnv,
    std: float,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    lateral_tolerance: float,
    lateral_std: float,
    rot_tolerance: float,
    rot_std: float,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Dense insertion-stage reward with soft gates on lateral and rotational alignment.

    The earlier hard gate (`lateral_error < lateral_tolerance`) made insertion progress almost
    unreachable, so the policy learned coarse alignment and orientation but rarely received any
    useful axial reward. We keep full reward inside a small pre-insertion window and decay
    smoothly outside it so the policy can climb toward the insertion regime.
    """

    lateral_error, axial_error, rot_error = insertion_metrics(env, command_name, asset_cfg, body_offset=body_offset)
    shaped = 1.0 - torch.tanh(axial_error / std)
    lateral_margin = torch.clamp(lateral_error - lateral_tolerance, min=0.0)
    rot_margin = torch.clamp(rot_error - rot_tolerance, min=0.0)
    lateral_gate = torch.exp(-torch.square(lateral_margin / lateral_std))
    rot_gate = torch.exp(-torch.square(rot_margin / rot_std))
    return shaped * lateral_gate * rot_gate


def insertion_success_reward(
    env: ManagerBasedRLEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
    xy_tolerance: float = 0.003,
    z_tolerance: float = 0.003,
    rot_tolerance: float = 0.15,
) -> torch.Tensor:
    """Binary success reward for insertion completion."""

    return insertion_success(
        env,
        command_name,
        asset_cfg,
        body_offset=body_offset,
        xy_tolerance=xy_tolerance,
        z_tolerance=z_tolerance,
        rot_tolerance=rot_tolerance,
    ).float()
