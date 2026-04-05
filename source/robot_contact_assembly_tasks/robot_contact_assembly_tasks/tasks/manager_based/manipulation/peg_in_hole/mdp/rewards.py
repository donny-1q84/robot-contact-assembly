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


def approach_pose_reward(
    env: ManagerBasedRLEnv,
    lateral_std: float,
    axial_std: float,
    rot_std: float,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    axial_weight: float = 0.35,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Coupled coarse approach reward before the policy reaches the insertion regime.

    Two failure modes showed up in smoke tests:
    1. strong position shaping with weak rotation caused coarse centering but bad orientation
    2. strong rotation shaping with weak position holding caused the peg to spiral away laterally

    Instead of paying the two dimensions independently, this term rewards their *joint* progress.
    Axial approach is only paid once the peg is simultaneously becoming centered and oriented.
    """

    lateral_error, axial_error, rot_error = insertion_metrics(env, command_name, asset_cfg, body_offset=body_offset)
    lateral_term = 1.0 - torch.tanh(lateral_error / lateral_std)
    axial_term = 1.0 - torch.tanh(axial_error / axial_std)
    rot_term = 1.0 - torch.tanh(rot_error / rot_std)
    coupled_alignment = torch.sqrt(torch.clamp(lateral_term * rot_term, min=0.0))
    return coupled_alignment + axial_weight * axial_term * coupled_alignment


def late_stage_pose_reward(
    env: ManagerBasedRLEnv,
    lateral_std: float,
    axial_std: float,
    rot_std: float,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Joint late-stage pose reward for checkpoint polishing near the socket.

    The base task already learns how to enter the socket neighborhood. During
    polish we care less about broad approach and more about keeping position and
    rotation tight at the same time. Paying the three dimensions independently
    made it too easy to improve rotation while giving back some lateral or axial
    accuracy. This term rewards only their simultaneous convergence.
    """

    lateral_error, axial_error, rot_error = insertion_metrics(env, command_name, asset_cfg, body_offset=body_offset)
    lateral_term = torch.exp(-torch.square(lateral_error / lateral_std))
    axial_term = torch.exp(-torch.square(axial_error / axial_std))
    rot_term = torch.exp(-torch.square(rot_error / rot_std))
    return torch.pow(torch.clamp(lateral_term * axial_term * rot_term, min=0.0), 1.0 / 3.0)


def late_stage_position_hold_reward(
    env: ManagerBasedRLEnv,
    lateral_std: float,
    axial_std: float,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Keep the peg tightly centered near the socket during checkpoint polishing.

    The base run already reaches a good coarse pose neighborhood. In polish mode we
    first need to *hold* that lateral / axial accuracy while a separate gated reward
    sharpens orientation. Coupling rotation into this term made PPO happily improve
    orientation while giving back the near-zero position errors learned by the base
    checkpoint.
    """

    lateral_error, axial_error, _ = insertion_metrics(env, command_name, asset_cfg, body_offset=body_offset)
    lateral_term = torch.exp(-torch.square(lateral_error / lateral_std))
    axial_term = torch.exp(-torch.square(axial_error / axial_std))
    return torch.sqrt(torch.clamp(lateral_term * axial_term, min=0.0))


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
    """Dense insertion-stage reward after coarse alignment.

    This term is intentionally stricter than ``approach_pose_reward``. The policy first gets paid
    for moving near the socket, then this reward takes over and favors axial convergence only while
    the peg tip remains centered and rotationally aligned.
    """

    lateral_error, axial_error, rot_error = insertion_metrics(env, command_name, asset_cfg, body_offset=body_offset)
    shaped = 1.0 - torch.tanh(axial_error / std)
    lateral_margin = torch.clamp(lateral_error - lateral_tolerance, min=0.0)
    rot_margin = torch.clamp(rot_error - rot_tolerance, min=0.0)
    lateral_gate = torch.exp(-torch.square(lateral_margin / lateral_std))
    rot_gate = torch.exp(-torch.square(rot_margin / rot_std))
    return shaped * lateral_gate * rot_gate


def insertion_orientation_fine_reward(
    env: ManagerBasedRLEnv,
    std: float,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    lateral_tolerance: float,
    axial_tolerance: float,
    lateral_std: float,
    axial_std: float,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Late-stage orientation shaping once the peg is already near the socket."""

    lateral_error, axial_error, rot_error = insertion_metrics(env, command_name, asset_cfg, body_offset=body_offset)
    rot_term = 1.0 - torch.tanh(rot_error / std)
    lateral_margin = torch.clamp(lateral_error - lateral_tolerance, min=0.0)
    axial_margin = torch.clamp(axial_error - axial_tolerance, min=0.0)
    lateral_gate = torch.exp(-torch.square(lateral_margin / lateral_std))
    axial_gate = torch.exp(-torch.square(axial_margin / axial_std))
    return rot_term * lateral_gate * axial_gate


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
