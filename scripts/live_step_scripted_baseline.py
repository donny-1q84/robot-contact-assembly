import builtins
import importlib
import sys

import torch
import warp as wp

for path in (
    "/isaac-sim",
    "/isaac-sim/python_packages",
    "/workspace/IsaacLab/source/isaaclab",
    "/workspace/IsaacLab/source/isaaclab_assets",
    "/workspace/IsaacLab/source/isaaclab_physx",
    "/workspace/IsaacLab/source/isaaclab_tasks",
    "/workspace/robot-contact-assembly/source/robot_contact_assembly_tasks",
):
    if path not in sys.path:
        sys.path.insert(0, path)

importlib.invalidate_caches()

from isaaclab.utils.math import combine_frame_transforms, compute_pose_error

from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
    PEG_TIP_BODY_OFFSET_POS,
    PEG_TIP_BODY_OFFSET_ROT,
)
from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole import mdp


STATE_KEY = "_rca_live_demo_state"
BODY_OFFSET = PEG_TIP_BODY_OFFSET_POS

APPROACH_HEIGHT = 0.05
APPROACH_XY_TOL = 0.015
APPROACH_Z_TOL = 0.02
APPROACH_ROT_TOL = 0.25
POS_GAIN = 2.0
ROT_GAIN = 2.0
POS_CLAMP = 0.12
ROT_CLAMP = 0.4

POLISH_XY_TOL = 0.002
POLISH_Z_TOL = 0.002
POLISH_POS_GAIN = 0.4
POLISH_POS_CLAMP = 0.02
POLISH_ROT_GAIN = 4.0
POLISH_ROT_CLAMP = 0.8

SETTLE_ROT_TOL = 0.25
SETTLE_POS_GAIN = 0.5
SETTLE_POS_CLAMP = 0.012
SETTLE_ROT_GAIN = 3.0
SETTLE_ROT_CLAMP = 0.24


def _hand_pose_w(env, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    robot = env.scene["robot"]
    hand_pos_w = wp.to_torch(robot.data.body_pos_w)[:, body_idx]
    hand_quat_w = wp.to_torch(robot.data.body_quat_w)[:, body_idx]
    return hand_pos_w, hand_quat_w


def _action_frame_pose_w(env, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    offset_quat = hand_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)


def _tool_tip_pose_w(env, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    offset_quat = hand_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)


def _socket_pose_w(env) -> tuple[torch.Tensor, torch.Tensor]:
    socket = env.scene["socket_frame"]
    return wp.to_torch(socket.data.root_pos_w), wp.to_torch(socket.data.root_quat_w)


def _target_action_frame_pose_w(socket_pos_w: torch.Tensor, socket_quat_w: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    return socket_pos_w.clone(), socket_quat_w.clone()


def _quat_conjugate(quat: torch.Tensor) -> torch.Tensor:
    return torch.cat((quat[..., :1], -quat[..., 1:]), dim=-1)


def _quat_multiply(lhs: torch.Tensor, rhs: torch.Tensor) -> torch.Tensor:
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
    zeros = torch.zeros_like(vec[..., :1])
    vec_quat = torch.cat((zeros, vec), dim=-1)
    return _quat_multiply(_quat_multiply(quat, vec_quat), _quat_conjugate(quat))[..., 1:]


def main():
    state = getattr(builtins, STATE_KEY, None)
    if not state or "env" not in state:
        raise RuntimeError("Live peg-in-hole environment is not loaded. Run show_live_play_env.sh first.")

    env = state["env"]
    if "polish_state" not in state:
        state["polish_state"] = torch.zeros(env.unwrapped.num_envs, dtype=torch.bool, device=env.unwrapped.device)
    if "settle_state" not in state:
        state["settle_state"] = torch.zeros(env.unwrapped.num_envs, dtype=torch.bool, device=env.unwrapped.device)
    if "rotate_state" not in state:
        state["rotate_state"] = torch.zeros(env.unwrapped.num_envs, dtype=torch.bool, device=env.unwrapped.device)

    robot = env.scene["robot"]
    body_ids, _ = robot.find_bodies("panda_hand")
    body_idx = body_ids[0]

    polish_state = state["polish_state"]
    settle_state = state["settle_state"]
    rotate_state = state["rotate_state"]

    action_pos_w, action_quat_w = _action_frame_pose_w(env, body_idx)
    socket_pos_w, socket_quat_w = _socket_pose_w(env)
    target_action_pos_w, target_action_quat_w = _target_action_frame_pose_w(socket_pos_w, socket_quat_w)

    from isaaclab.managers import SceneEntityCfg

    peg_cfg = SceneEntityCfg("peg")
    socket_cfg = SceneEntityCfg("socket_frame")
    lateral_error, axial_error, orientation_error = mdp.insertion_metrics(
        env.unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg
    )

    approach_pos_w = target_action_pos_w.clone()
    approach_pos_w[:, 2] += APPROACH_HEIGHT
    target_pos_w = approach_pos_w.clone()
    target_quat_w = action_quat_w.clone()

    approach_z_error = torch.abs(action_pos_w[:, 2] - approach_pos_w[:, 2])
    position_ready = (lateral_error < APPROACH_XY_TOL) & (approach_z_error < APPROACH_Z_TOL)
    rotate_state |= position_ready
    target_quat_w[rotate_state] = target_action_quat_w[rotate_state]
    insert_mask = rotate_state & (lateral_error < APPROACH_XY_TOL) & (orientation_error < APPROACH_ROT_TOL)
    target_pos_w[insert_mask] = target_action_pos_w[insert_mask]

    polish_mask = (lateral_error < POLISH_XY_TOL) & (axial_error < POLISH_Z_TOL)
    polish_state |= polish_mask
    settle_state |= polish_state & (orientation_error < SETTLE_ROT_TOL)

    pos_error, axis_angle_error = compute_pose_error(
        action_pos_w, action_quat_w, target_pos_w, target_quat_w, rot_error_type="axis_angle"
    )
    action_pos_error = _rotate_vector(action_quat_w, pos_error)

    action = torch.zeros(env.action_space.shape, device=env.unwrapped.device)
    pos_gain = torch.full_like(pos_error, POS_GAIN)
    pos_gain[polish_state] = POLISH_POS_GAIN
    pos_gain[settle_state] = SETTLE_POS_GAIN
    rot_gain = torch.full_like(axis_angle_error, ROT_GAIN)
    rot_gain[polish_state] = POLISH_ROT_GAIN
    rot_gain[settle_state] = SETTLE_ROT_GAIN
    pos_clamp = torch.full_like(pos_error, POS_CLAMP)
    pos_clamp[polish_state] = POLISH_POS_CLAMP
    pos_clamp[settle_state] = SETTLE_POS_CLAMP
    rot_clamp = torch.full_like(axis_angle_error, ROT_CLAMP)
    rot_clamp[polish_state] = POLISH_ROT_CLAMP
    rot_clamp[settle_state] = SETTLE_ROT_CLAMP

    action[:, :3] = torch.maximum(torch.minimum(pos_gain * action_pos_error, pos_clamp), -pos_clamp)
    action[:, 3:6] = torch.maximum(torch.minimum(rot_gain * axis_angle_error, rot_clamp), -rot_clamp)

    env.step(action)

    lateral, axial, rot = mdp.insertion_metrics(env.unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)
    success = mdp.insertion_success(env.unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)

    print(
        "live-step "
        f"lateral={lateral.mean().item():.4f} "
        f"axial={axial.mean().item():.4f} "
        f"rot={rot.mean().item():.4f} "
        f"success={success.float().mean().item():.3f} "
        f"position={position_ready.float().mean().item():.3f} "
        f"rotate={rotate_state.float().mean().item():.3f} "
        f"insert={insert_mask.float().mean().item():.3f} "
        f"polish={polish_state.float().mean().item():.3f} "
        f"settle={settle_state.float().mean().item():.3f}"
    )


main()
