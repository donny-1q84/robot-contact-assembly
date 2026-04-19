from __future__ import annotations

from typing import TYPE_CHECKING

import torch
import warp as wp

from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import combine_frame_transforms, subtract_frame_transforms

from ..constants import PEG_TIP_FROM_CENTER_POS

if TYPE_CHECKING:
    from isaaclab.assets import RigidObject
    from isaaclab.envs import ManagerBasedRLEnv
    from isaaclab.sensors import ContactSensor


def _to_torch(data: torch.Tensor) -> torch.Tensor:
    """Return a torch tensor regardless of whether the backing storage is warp or torch."""

    return data if isinstance(data, torch.Tensor) else wp.to_torch(data)


def _quat_conjugate(quat: torch.Tensor) -> torch.Tensor:
    """Quaternion conjugate for `(w, x, y, z)` tensors."""

    return torch.cat((quat[..., :1], -quat[..., 1:]), dim=-1)


def _quat_multiply(lhs: torch.Tensor, rhs: torch.Tensor) -> torch.Tensor:
    """Hamilton product for `(w, x, y, z)` quaternions."""

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


def _rotate_vector_inverse(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    """Rotate world-frame vectors into the local frame of `quat`."""

    zeros = torch.zeros_like(vec[..., :1])
    vec_quat = torch.cat((zeros, vec), dim=-1)
    return _quat_multiply(_quat_multiply(_quat_conjugate(quat), vec_quat), quat)[..., 1:]


def _peg_root_pose_w(env: ManagerBasedRLEnv, peg_cfg: SceneEntityCfg) -> tuple[torch.Tensor, torch.Tensor]:
    """World pose of the physical peg body."""

    peg: RigidObject = env.scene[peg_cfg.name]
    return _to_torch(peg.data.root_pos_w), _to_torch(peg.data.root_quat_w)


def _socket_pose_w(env: ManagerBasedRLEnv, socket_cfg: SceneEntityCfg) -> tuple[torch.Tensor, torch.Tensor]:
    """World pose of the physical socket frame anchor."""

    socket: RigidObject = env.scene[socket_cfg.name]
    return _to_torch(socket.data.root_pos_w), _to_torch(socket.data.root_quat_w)


def _peg_tip_pose_w(env: ManagerBasedRLEnv, peg_cfg: SceneEntityCfg) -> tuple[torch.Tensor, torch.Tensor]:
    """Peg-tip world pose computed from the physical peg body center."""

    peg_pos_w, peg_quat_w = _peg_root_pose_w(env, peg_cfg)
    tip_offset_pos = peg_pos_w.new_tensor(PEG_TIP_FROM_CENTER_POS).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    tip_offset_quat = peg_pos_w.new_tensor((1.0, 0.0, 0.0, 0.0)).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    return combine_frame_transforms(peg_pos_w, peg_quat_w, tip_offset_pos, tip_offset_quat)


def socket_pose(
    env: ManagerBasedRLEnv,
    asset_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Socket frame pose expressed in the robot root frame."""

    robot = env.scene[asset_cfg.name]
    root_pos_w = _to_torch(robot.data.root_pos_w)
    root_quat_w = _to_torch(robot.data.root_quat_w)
    socket_pos_w, socket_quat_w = _socket_pose_w(env, socket_cfg)
    rel_pos, rel_quat = subtract_frame_transforms(root_pos_w, root_quat_w, socket_pos_w, socket_quat_w)
    return torch.cat((rel_pos, rel_quat), dim=1)


def tip_to_socket_position(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Peg-tip position error in the physical socket frame."""

    tip_pos_w, tip_quat_w = _peg_tip_pose_w(env, peg_cfg)
    socket_pos_w, socket_quat_w = _socket_pose_w(env, socket_cfg)
    rel_pos, _ = subtract_frame_transforms(socket_pos_w, socket_quat_w, tip_pos_w, tip_quat_w)
    return rel_pos


def tip_to_socket_orientation(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Peg-tip orientation error represented as a relative quaternion in the socket frame."""

    tip_pos_w, tip_quat_w = _peg_tip_pose_w(env, peg_cfg)
    socket_pos_w, socket_quat_w = _socket_pose_w(env, socket_cfg)
    _, rel_quat = subtract_frame_transforms(socket_pos_w, socket_quat_w, tip_pos_w, tip_quat_w)
    return rel_quat


def peg_contact_force_magnitude(env: ManagerBasedRLEnv, sensor_cfg: SceneEntityCfg) -> torch.Tensor:
    """Net contact-force magnitude on the peg body."""

    sensor: ContactSensor = env.scene[sensor_cfg.name]
    net_forces = _to_torch(sensor.data.net_forces_w)
    if net_forces.ndim == 3:
        net_forces = net_forces.sum(dim=1)
    return torch.linalg.norm(net_forces, dim=-1, keepdim=True)


def peg_contact_force_socket(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
    force_scale: float = 20.0,
) -> torch.Tensor:
    """Net contact force on the peg, expressed in the socket frame and squashed with tanh."""

    sensor: ContactSensor = env.scene[sensor_cfg.name]
    net_forces = _to_torch(sensor.data.net_forces_w)
    if net_forces.ndim == 3:
        net_forces = net_forces.sum(dim=1)
    _, socket_quat_w = _socket_pose_w(env, socket_cfg)
    local_forces = _rotate_vector_inverse(socket_quat_w, net_forces)
    return torch.tanh(local_forces / force_scale)


def peg_contact_force_magnitude_scaled(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    force_scale: float = 20.0,
) -> torch.Tensor:
    """Bounded contact magnitude for force-aware policies."""

    return torch.tanh(peg_contact_force_magnitude(env, sensor_cfg) / force_scale)
