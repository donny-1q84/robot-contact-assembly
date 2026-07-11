from __future__ import annotations

from typing import TYPE_CHECKING

import torch
import warp as wp
from isaaclab.managers import SceneEntityCfg

if TYPE_CHECKING:
    from isaaclab.envs import ManagerBasedRLEnv


def _to_torch(data: torch.Tensor) -> torch.Tensor:
    """Return a torch tensor regardless of whether Isaac Lab stores torch or warp data."""

    return data if isinstance(data, torch.Tensor) else wp.to_torch(data)


def _quat_conjugate(quat: torch.Tensor) -> torch.Tensor:
    """Quaternion conjugate for Isaac Lab WXYZ tensors."""

    return torch.cat((quat[..., :1], -quat[..., 1:]), dim=-1)


def _quat_multiply(lhs: torch.Tensor, rhs: torch.Tensor) -> torch.Tensor:
    """Hamilton product for Isaac Lab WXYZ quaternions."""

    w1, x1, y1, z1 = lhs.unbind(dim=-1)
    w2, x2, y2, z2 = rhs.unbind(dim=-1)
    return torch.stack(
        (
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ),
        dim=-1,
    )


def _rotate_vector(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    """Rotate local-frame vectors into world frame with Isaac Lab WXYZ quaternions."""

    zeros = torch.zeros_like(vec[..., :1])
    vec_quat = torch.cat((zeros, vec), dim=-1)
    return _quat_multiply(_quat_multiply(quat, vec_quat), _quat_conjugate(quat))[..., 1:]


def _combine_frame_transforms_wxyz(
    parent_pos: torch.Tensor,
    parent_quat: torch.Tensor,
    child_pos: torch.Tensor,
    child_quat: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Compose transforms using Isaac Lab's WXYZ quaternion convention."""

    return parent_pos + _rotate_vector(parent_quat, child_pos), _quat_multiply(parent_quat, child_quat)


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
    """Place the physical peg at the controller tip frame. RESET-ONLY.

    `body_offset` and `body_rot_offset` define the same tip frame used by the IK action.
    The physical peg root is then derived from that tip pose, so controller targets,
    rewards, terminations, and trace metrics refer to one consistent tip frame.

    The peg is a dynamic body welded to the hand by a fixed joint (see
    ``assets.spawn_attached_peg_cylinder``). This teleport must only run on
    reset to seed the joint near zero error; running it per step would fight
    the joint solver and erase contact impulses, reintroducing the
    no-contact-physics artifact documented in the 2026-06-11 audit.
    """

    robot = env.scene[robot_cfg.name]
    peg = env.scene[peg_cfg.name]

    if env_ids is None:
        index = slice(None)
        sim_env_ids = None
    elif isinstance(env_ids, slice):
        index = env_ids
        sim_env_ids = None if env_ids == slice(None) else env_ids
    else:
        index = env_ids
        sim_env_ids = env_ids

    body_pos_w = _to_torch(robot.data.body_pos_w)[:, robot_cfg.body_ids[0]][index]  # type: ignore[index]
    body_quat_w = _to_torch(robot.data.body_quat_w)[:, robot_cfg.body_ids[0]][index]  # type: ignore[index]

    tip_offset_pos = body_pos_w.new_tensor(body_offset).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    tip_offset_quat = body_pos_w.new_tensor(body_rot_offset).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    tip_pos_w, tip_quat_w = _combine_frame_transforms_wxyz(
        body_pos_w,
        body_quat_w,
        tip_offset_pos,
        tip_offset_quat,
    )

    root_offset_pos = body_pos_w.new_tensor(peg_root_from_tip_pos).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    root_offset_quat = body_pos_w.new_tensor(peg_root_from_tip_rot).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    peg_pos_w, peg_quat_w = _combine_frame_transforms_wxyz(
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
