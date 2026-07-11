from __future__ import annotations

from typing import TYPE_CHECKING

import torch
import warp as wp

from isaaclab.managers import SceneEntityCfg

from ..constants import (
    IDENTITY_QUAT,
    PEG_CENTER_BODY_OFFSET_POS,
    PEG_CENTER_BODY_OFFSET_ROT,
    PEG_TIP_FROM_CENTER_POS,
    SOCKET_INSERTION_AXIS_LOCAL,
    SOCKET_INSERTION_AXIS_SIGN_INVARIANT,
)

if TYPE_CHECKING:
    from isaaclab.assets import RigidObject
    from isaaclab.envs import ManagerBasedRLEnv
    from isaaclab.sensors import ContactSensor


def _to_torch(data: torch.Tensor) -> torch.Tensor:
    """Return a torch tensor regardless of whether the backing storage is warp or torch."""

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


def _rotate_vector_inverse(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    """Rotate world-frame vectors into the local frame of `quat`."""

    zeros = torch.zeros_like(vec[..., :1])
    vec_quat = torch.cat((zeros, vec), dim=-1)
    return _quat_multiply(_quat_multiply(_quat_conjugate(quat), vec_quat), quat)[..., 1:]


def _rotate_vector(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    """Rotate local-frame vectors into the world frame of `quat`."""

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


def _subtract_frame_transforms_wxyz(
    parent_pos: torch.Tensor,
    parent_quat: torch.Tensor,
    child_pos: torch.Tensor,
    child_quat: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Express child transform in parent frame using Isaac Lab WXYZ quaternions."""

    return (
        _rotate_vector_inverse(parent_quat, child_pos - parent_pos),
        _quat_multiply(_quat_conjugate(parent_quat), child_quat),
    )


def _normalize_vectors(vec: torch.Tensor) -> torch.Tensor:
    return vec / torch.clamp(torch.linalg.norm(vec, dim=-1, keepdim=True), min=1.0e-8)


def _peg_root_pose_w(env: ManagerBasedRLEnv, peg_cfg: SceneEntityCfg) -> tuple[torch.Tensor, torch.Tensor]:
    """World pose of the physical peg root.

    Prefer the actual peg articulation-link body when Isaac exposes it through
    the robot view. The fallback hand-derived pose only exists for legacy
    diagnostics or partial local imports where the runtime body view is absent.
    """

    robot = env.scene["robot"]
    body_name_candidates = (peg_cfg.name.capitalize(), peg_cfg.name, "Peg", "peg")
    for body_name in body_name_candidates:
        if body_name in robot.body_names:
            body_idx = robot.body_names.index(body_name)
            return _to_torch(robot.data.body_pos_w)[:, body_idx], _to_torch(robot.data.body_quat_w)[:, body_idx]

    hand_idx = robot.body_names.index("panda_hand")
    hand_pos_w = _to_torch(robot.data.body_pos_w)[:, hand_idx]
    hand_quat_w = _to_torch(robot.data.body_quat_w)[:, hand_idx]
    root_offset_pos = hand_pos_w.new_tensor(PEG_CENTER_BODY_OFFSET_POS).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    root_offset_quat = hand_pos_w.new_tensor(PEG_CENTER_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return _combine_frame_transforms_wxyz(hand_pos_w, hand_quat_w, root_offset_pos, root_offset_quat)


def _socket_pose_w(env: ManagerBasedRLEnv, socket_cfg: SceneEntityCfg) -> tuple[torch.Tensor, torch.Tensor]:
    """World pose of the physical socket frame anchor."""

    socket: RigidObject = env.scene[socket_cfg.name]
    return _to_torch(socket.data.root_pos_w), _to_torch(socket.data.root_quat_w)


def _peg_tip_pose_w(env: ManagerBasedRLEnv, peg_cfg: SceneEntityCfg) -> tuple[torch.Tensor, torch.Tensor]:
    """Peg-tip world pose computed from the physical peg body center."""

    peg_pos_w, peg_quat_w = _peg_root_pose_w(env, peg_cfg)
    tip_offset_pos = peg_pos_w.new_tensor(PEG_TIP_FROM_CENTER_POS).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    tip_offset_quat = peg_pos_w.new_tensor(IDENTITY_QUAT).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    return _combine_frame_transforms_wxyz(peg_pos_w, peg_quat_w, tip_offset_pos, tip_offset_quat)


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
    rel_pos, rel_quat = _subtract_frame_transforms_wxyz(root_pos_w, root_quat_w, socket_pos_w, socket_quat_w)
    return torch.cat((rel_pos, rel_quat), dim=1)


def tip_to_socket_position(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Peg-tip position error in the physical socket frame."""

    tip_pos_w, tip_quat_w = _peg_tip_pose_w(env, peg_cfg)
    socket_pos_w, socket_quat_w = _socket_pose_w(env, socket_cfg)
    rel_pos, _ = _subtract_frame_transforms_wxyz(socket_pos_w, socket_quat_w, tip_pos_w, tip_quat_w)
    return rel_pos


def tip_to_socket_orientation(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Peg-tip orientation error represented as a relative quaternion in the socket frame."""

    tip_pos_w, tip_quat_w = _peg_tip_pose_w(env, peg_cfg)
    socket_pos_w, socket_quat_w = _socket_pose_w(env, socket_cfg)
    _, rel_quat = _subtract_frame_transforms_wxyz(socket_pos_w, socket_quat_w, tip_pos_w, tip_quat_w)
    return rel_quat


def tip_to_socket_axis_error(
    env: ManagerBasedRLEnv,
    peg_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
) -> torch.Tensor:
    """Sign-invariant insertion-axis error for the cylindrical peg."""

    _, tip_quat_w = _peg_tip_pose_w(env, peg_cfg)
    socket_pos_w, socket_quat_w = _socket_pose_w(env, socket_cfg)
    axis_local = socket_pos_w.new_tensor(SOCKET_INSERTION_AXIS_LOCAL).unsqueeze(0).repeat(socket_pos_w.shape[0], 1)
    tip_axis_w = _normalize_vectors(_rotate_vector(tip_quat_w, axis_local))
    socket_axis_w = _normalize_vectors(_rotate_vector(socket_quat_w, axis_local))
    dot = torch.sum(tip_axis_w * socket_axis_w, dim=1)
    if SOCKET_INSERTION_AXIS_SIGN_INVARIANT:
        dot = torch.abs(dot)
    return torch.acos(torch.clamp(dot, min=-1.0, max=1.0))


def _peg_wall_contact_forces_w(sensor: ContactSensor) -> torch.Tensor:
    """Socket-wall contact force on the peg, summed over the filtered wall pairs.

    Uses ``force_matrix_w`` (shape ``(num_envs, num_bodies, num_filters, 3)``),
    which only aggregates contacts against ``filter_prim_paths_expr`` — the four
    guide walls. ``net_forces_w`` would also include gripper-finger and other
    incidental contacts, which is exactly the artifact that invalidated the old
    contact gate (2026-06-11 audit). The net-force fallback only exists for
    sensors configured without a filter list.
    """

    force_matrix = getattr(sensor.data, "force_matrix_w", None)
    if force_matrix is not None:
        forces = _to_torch(force_matrix)
        if forces.ndim > 2:
            forces = forces.sum(dim=tuple(range(1, forces.ndim - 1)))
        return forces
    net_forces = _to_torch(sensor.data.net_forces_w)
    if net_forces.ndim == 3:
        net_forces = net_forces.sum(dim=1)
    return net_forces


def peg_contact_force_magnitude(env: ManagerBasedRLEnv, sensor_cfg: SceneEntityCfg) -> torch.Tensor:
    """Socket-wall contact-force magnitude on the peg body."""

    sensor: ContactSensor = env.scene[sensor_cfg.name]
    forces = _peg_wall_contact_forces_w(sensor)
    return torch.linalg.norm(forces, dim=-1, keepdim=True)


def peg_contact_force_socket(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    socket_cfg: SceneEntityCfg,
    force_scale: float = 20.0,
) -> torch.Tensor:
    """Socket-wall contact force on the peg, in the socket frame, squashed with tanh."""

    sensor: ContactSensor = env.scene[sensor_cfg.name]
    forces = _peg_wall_contact_forces_w(sensor)
    _, socket_quat_w = _socket_pose_w(env, socket_cfg)
    local_forces = _rotate_vector_inverse(socket_quat_w, forces)
    return torch.tanh(local_forces / force_scale)


def peg_contact_force_magnitude_scaled(
    env: ManagerBasedRLEnv,
    sensor_cfg: SceneEntityCfg,
    force_scale: float = 20.0,
) -> torch.Tensor:
    """Bounded contact magnitude for force-aware policies."""

    return torch.tanh(peg_contact_force_magnitude(env, sensor_cfg) / force_scale)
