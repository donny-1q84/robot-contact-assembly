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

from isaaclab.utils.math import combine_frame_transforms, compute_pose_error, quat_inv, quat_mul

from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
    PEG_TIP_BODY_OFFSET_POS,
    PEG_TIP_BODY_OFFSET_ROT,
)
from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole import mdp


STATE_KEY = "_rca_live_demo_state"
BODY_OFFSET = PEG_TIP_BODY_OFFSET_POS

APPROACH_HEIGHT = 0.0
APPROACH_XY_TOL = 1.0
APPROACH_ROT_TOL = 10.0
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


def _identity_quat(reference: torch.Tensor) -> torch.Tensor:
    quat = reference.new_zeros((reference.shape[0], 4))
    quat[:, 3] = 1.0
    return quat


def _hand_pose_w(env, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    robot = env.scene["robot"]
    hand_pos_w = wp.to_torch(robot.data.body_pos_w)[:, body_idx]
    hand_quat_w = wp.to_torch(robot.data.body_quat_w)[:, body_idx]
    return hand_pos_w, hand_quat_w


def _action_frame_pose_w(env, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, _identity_quat(hand_pos_w))


def _tool_tip_pose_w(env, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    offset_quat = hand_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)


def _socket_pose_w(env) -> tuple[torch.Tensor, torch.Tensor]:
    robot = env.scene["robot"]
    command = env.command_manager.get_command("socket_pose")
    root_pos_w = wp.to_torch(robot.data.root_pos_w)
    root_quat_w = wp.to_torch(robot.data.root_quat_w)
    return combine_frame_transforms(root_pos_w, root_quat_w, command[:, :3], command[:, 3:7])


def _target_action_frame_pose_w(socket_pos_w: torch.Tensor, socket_quat_w: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    offset_quat = socket_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(socket_pos_w.shape[0], 1)
    target_action_quat_w = quat_mul(socket_quat_w, quat_inv(offset_quat))
    return socket_pos_w.clone(), target_action_quat_w


def main():
    state = getattr(builtins, STATE_KEY, None)
    if not state or "env" not in state:
        raise RuntimeError("Live peg-in-hole environment is not loaded. Run show_live_play_env.sh first.")

    env = state["env"]
    if "polish_state" not in state:
        state["polish_state"] = torch.zeros(env.unwrapped.num_envs, dtype=torch.bool, device=env.unwrapped.device)
    if "settle_state" not in state:
        state["settle_state"] = torch.zeros(env.unwrapped.num_envs, dtype=torch.bool, device=env.unwrapped.device)

    robot = env.scene["robot"]
    body_ids, _ = robot.find_bodies("panda_hand")
    body_idx = body_ids[0]
    asset_cfg = state.get("asset_cfg")
    if asset_cfg is None:
        from isaaclab.managers import SceneEntityCfg

        asset_cfg = SceneEntityCfg("robot", body_names=["panda_hand"])
        asset_cfg.body_ids = [body_idx]
        state["asset_cfg"] = asset_cfg

    polish_state = state["polish_state"]
    settle_state = state["settle_state"]

    action_pos_w, action_quat_w = _action_frame_pose_w(env, body_idx)
    tip_pos_w, tip_quat_w = _tool_tip_pose_w(env, body_idx)
    socket_pos_w, socket_quat_w = _socket_pose_w(env)
    target_action_pos_w, target_action_quat_w = _target_action_frame_pose_w(socket_pos_w, socket_quat_w)

    target_pos_w = target_action_pos_w.clone()
    target_pos_w[:, 2] += APPROACH_HEIGHT

    direct_pos_error, direct_axis_angle_error = compute_pose_error(
        tip_pos_w, tip_quat_w, socket_pos_w, socket_quat_w, rot_error_type="axis_angle"
    )
    lateral_error = torch.linalg.norm(direct_pos_error[:, :2], dim=1)
    axial_error = torch.abs(direct_pos_error[:, 2])
    orientation_error = torch.linalg.norm(direct_axis_angle_error, dim=1)

    align_mask = (lateral_error < APPROACH_XY_TOL) & (orientation_error < APPROACH_ROT_TOL)
    target_pos_w[align_mask] = target_action_pos_w[align_mask]

    polish_mask = (lateral_error < POLISH_XY_TOL) & (axial_error < POLISH_Z_TOL)
    polish_state |= polish_mask
    settle_state |= polish_state & (orientation_error < SETTLE_ROT_TOL)

    pos_error, axis_angle_error = compute_pose_error(
        action_pos_w, action_quat_w, target_pos_w, target_action_quat_w, rot_error_type="axis_angle"
    )

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

    action[:, :3] = torch.maximum(torch.minimum(pos_gain * pos_error, pos_clamp), -pos_clamp)
    action[:, 3:6] = torch.maximum(torch.minimum(rot_gain * axis_angle_error, rot_clamp), -rot_clamp)

    env.step(action)

    lateral, axial, rot = mdp.insertion_metrics(
        env.unwrapped, command_name="socket_pose", asset_cfg=asset_cfg, body_offset=BODY_OFFSET
    )
    success = mdp.insertion_success(
        env.unwrapped, command_name="socket_pose", asset_cfg=asset_cfg, body_offset=BODY_OFFSET
    )

    print(
        "live-step "
        f"lateral={lateral.mean().item():.4f} "
        f"axial={axial.mean().item():.4f} "
        f"rot={rot.mean().item():.4f} "
        f"success={success.float().mean().item():.3f} "
        f"polish={polish_state.float().mean().item():.3f} "
        f"settle={settle_state.float().mean().item():.3f}"
    )


main()
