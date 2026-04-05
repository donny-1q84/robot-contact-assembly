from __future__ import annotations

from typing import TYPE_CHECKING

import torch
import warp as wp

from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import combine_frame_transforms, subtract_frame_transforms

from ..constants import PEG_TIP_BODY_OFFSET_POS, PEG_TIP_BODY_OFFSET_ROT

if TYPE_CHECKING:
    from isaaclab.assets import RigidObject
    from isaaclab.envs import ManagerBasedRLEnv


def _body_offset_tensors(
    reference: torch.Tensor,
    body_offset: tuple[float, float, float],
    body_rot_offset: tuple[float, float, float, float],
) -> tuple[torch.Tensor, torch.Tensor]:
    """Create batched offset tensors for a peg tip rigidly attached to the tool frame."""

    offset_pos = reference.new_tensor(body_offset).unsqueeze(0).repeat(reference.shape[0], 1)
    offset_quat = reference.new_tensor(body_rot_offset).unsqueeze(0).repeat(reference.shape[0], 1)
    return offset_pos, offset_quat


def _tool_tip_pose_w(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
    body_rot_offset: tuple[float, float, float, float] = PEG_TIP_BODY_OFFSET_ROT,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Tool-tip world pose computed from the selected robot body and a fixed peg-tip offset."""

    asset: RigidObject = env.scene[asset_cfg.name]
    body_pos_w = wp.to_torch(asset.data.body_pos_w)[:, asset_cfg.body_ids[0]]  # type: ignore[index]
    body_quat_w = wp.to_torch(asset.data.body_quat_w)[:, asset_cfg.body_ids[0]]  # type: ignore[index]
    offset_pos, offset_quat = _body_offset_tensors(body_pos_w, body_offset, body_rot_offset)
    return combine_frame_transforms(body_pos_w, body_quat_w, offset_pos, offset_quat)


def _socket_pose_w(
    env: ManagerBasedRLEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Desired socket pose in world coordinates, expressed relative to the robot root frame."""

    asset: RigidObject = env.scene[asset_cfg.name]
    command = env.command_manager.get_command(command_name)
    root_pos_w = wp.to_torch(asset.data.root_pos_w)
    root_quat_w = wp.to_torch(asset.data.root_quat_w)
    return combine_frame_transforms(root_pos_w, root_quat_w, command[:, :3], command[:, 3:7])


def tip_to_socket_position(
    env: ManagerBasedRLEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Tool-tip position error in the socket frame."""

    tip_pos_w, tip_quat_w = _tool_tip_pose_w(env, asset_cfg, body_offset=body_offset)
    socket_pos_w, socket_quat_w = _socket_pose_w(env, command_name, asset_cfg)
    rel_pos, _ = subtract_frame_transforms(socket_pos_w, socket_quat_w, tip_pos_w, tip_quat_w)
    return rel_pos


def tip_to_socket_orientation(
    env: ManagerBasedRLEnv,
    command_name: str,
    asset_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float] = PEG_TIP_BODY_OFFSET_POS,
) -> torch.Tensor:
    """Tool-tip orientation error represented as a relative quaternion in the socket frame."""

    tip_pos_w, tip_quat_w = _tool_tip_pose_w(env, asset_cfg, body_offset=body_offset)
    socket_pos_w, socket_quat_w = _socket_pose_w(env, command_name, asset_cfg)
    _, rel_quat = subtract_frame_transforms(socket_pos_w, socket_quat_w, tip_pos_w, tip_quat_w)
    return rel_quat
