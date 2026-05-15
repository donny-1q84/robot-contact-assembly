from __future__ import annotations

from typing import TYPE_CHECKING

import torch
import warp as wp
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import combine_frame_transforms

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def sync_peg_to_hand(
    env: ManagerBasedRLEnv,
    env_ids: torch.Tensor | slice | None,
    robot_cfg: SceneEntityCfg,
    peg_cfg: SceneEntityCfg,
    body_offset: tuple[float, float, float],
    body_rot_offset: tuple[float, float, float, float],
    peg_root_from_tip_pos: tuple[float, float, float],
    peg_root_from_tip_rot: tuple[float, float, float, float],
) -> None:
    """Rigidly follow the controller tip frame with the physical peg each environment step.

    `body_offset` and `body_rot_offset` define the same tip frame used by the IK action.
    The physical peg root is then derived from that tip pose, so controller targets,
    rewards, terminations, and trace metrics refer to one consistent tip frame.
    """

    robot = env.scene[robot_cfg.name]
    peg = env.scene[peg_cfg.name]

    index = slice(None) if env_ids is None else env_ids
    sim_env_ids = None if env_ids is None or env_ids == slice(None) else env_ids

    body_pos_w = wp.to_torch(robot.data.body_pos_w)[:, robot_cfg.body_ids[0]][index]  # type: ignore[index]
    body_quat_w = wp.to_torch(robot.data.body_quat_w)[:, robot_cfg.body_ids[0]][index]  # type: ignore[index]

    tip_offset_pos = body_pos_w.new_tensor(body_offset).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    tip_offset_quat = body_pos_w.new_tensor(body_rot_offset).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    tip_pos_w, tip_quat_w = combine_frame_transforms(
        body_pos_w,
        body_quat_w,
        tip_offset_pos,
        tip_offset_quat,
    )

    root_offset_pos = body_pos_w.new_tensor(peg_root_from_tip_pos).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    root_offset_quat = body_pos_w.new_tensor(peg_root_from_tip_rot).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    peg_pos_w, peg_quat_w = combine_frame_transforms(
        tip_pos_w,
        tip_quat_w,
        root_offset_pos,
        root_offset_quat,
    )
    peg.write_root_pose_to_sim(torch.cat((peg_pos_w, peg_quat_w), dim=1), env_ids=sim_env_ids)
    peg.write_root_velocity_to_sim(
        torch.zeros((peg_pos_w.shape[0], 6), device=peg_pos_w.device, dtype=peg_pos_w.dtype),
        env_ids=sim_env_ids,
    )
