"""Inspect peg-in-hole end-effector and target pose alignment for one rollout."""

from __future__ import annotations

import argparse
import os
import sys

import gymnasium as gym
import torch
import warp as wp

from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.math import combine_frame_transforms, compute_pose_error, subtract_frame_transforms
from isaaclab_tasks.utils import add_launcher_args, launch_simulation, resolve_task_config

from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
    PEG_TIP_BODY_OFFSET_POS,
    PEG_TIP_BODY_OFFSET_ROT,
)

BODY_OFFSET = PEG_TIP_BODY_OFFSET_POS

parser = argparse.ArgumentParser(description="Debug pose alignment for the peg-in-hole scripted baseline.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments.")
parser.add_argument("--steps", type=int, default=220, help="Number of env steps to run.")
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-IK-Rel-Play-v0", help="Task name.")
parser.add_argument("--approach-height", type=float, default=0.0, help="Approach offset over the target along +Z.")
parser.add_argument("--approach-xy-tol", type=float, default=0.01, help="Lateral tolerance before switching to insertion.")
parser.add_argument("--approach-rot-tol", type=float, default=10.0, help="Orientation tolerance before switching to insertion.")
parser.add_argument("--pos-gain", type=float, default=2.0, help="Proportional gain for position error.")
parser.add_argument("--rot-gain", type=float, default=2.0, help="Proportional gain for axis-angle orientation error.")
parser.add_argument("--pos-clamp", type=float, default=0.12, help="Clamp applied to each translational action dimension.")
parser.add_argument("--rot-clamp", type=float, default=0.4, help="Clamp applied to each rotational action dimension.")
add_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
hydra_args.extend(
    [
        r"hydra.run.dir=/workspace/artifacts/hydra/${now:%Y-%m-%d}/${now:%H-%M-%S}",
        "hydra.output_subdir=null",
    ]
)
sys.argv = [sys.argv[0]] + hydra_args

import robot_contact_assembly_tasks.tasks  # noqa: E402,F401


def _tool_tip_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    robot = env_unwrapped.scene["robot"]
    body_pos_w = wp.to_torch(robot.data.body_pos_w)[:, body_idx]
    body_quat_w = wp.to_torch(robot.data.body_quat_w)[:, body_idx]
    offset_pos = body_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    offset_quat = body_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(body_pos_w.shape[0], 1)
    return combine_frame_transforms(body_pos_w, body_quat_w, offset_pos, offset_quat)


def _socket_pose_w(env_unwrapped) -> tuple[torch.Tensor, torch.Tensor]:
    robot = env_unwrapped.scene["robot"]
    command = env_unwrapped.command_manager.get_command("socket_pose")
    root_pos_w = wp.to_torch(robot.data.root_pos_w)
    root_quat_w = wp.to_torch(robot.data.root_quat_w)
    return combine_frame_transforms(root_pos_w, root_quat_w, command[:, :3], command[:, 3:7])


def _print_pose_debug(label: str, tip_pos_w, tip_quat_w, socket_pos_w, socket_quat_w) -> None:
    rel_pos, rel_quat = subtract_frame_transforms(socket_pos_w, socket_quat_w, tip_pos_w, tip_quat_w)
    _, axis_angle_error = compute_pose_error(
        tip_pos_w, tip_quat_w, socket_pos_w, socket_quat_w, rot_error_type="axis_angle"
    )
    print(f"[{label}] tip_pos={tip_pos_w[0].tolist()}", flush=True)
    print(f"[{label}] socket_pos={socket_pos_w[0].tolist()}", flush=True)
    print(f"[{label}] rel_pos={rel_pos[0].tolist()}", flush=True)
    print(f"[{label}] tip_quat={tip_quat_w[0].tolist()}", flush=True)
    print(f"[{label}] socket_quat={socket_quat_w[0].tolist()}", flush=True)
    print(f"[{label}] rel_quat={rel_quat[0].tolist()}", flush=True)
    print(f"[{label}] axis_angle={axis_angle_error[0].tolist()}", flush=True)
    print(f"[{label}] rot_norm={torch.linalg.norm(axis_angle_error, dim=1)[0].item():.6f}", flush=True)


def main():
    os.makedirs("/workspace/artifacts/hydra", exist_ok=True)
    torch.manual_seed(42)
    env_cfg, _ = resolve_task_config(args_cli.task, "")

    with launch_simulation(env_cfg, args_cli):
        env_cfg.scene.num_envs = args_cli.num_envs
        env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
        if args_cli.disable_fabric:
            env_cfg.sim.use_fabric = False
        env_cfg.commands.socket_pose.resampling_time_range = (1.0e6, 1.0e6)

        env = gym.make(args_cli.task, cfg=env_cfg)
        env_unwrapped = env.unwrapped
        env.reset()

        robot = env_unwrapped.scene["robot"]
        body_ids, _ = robot.find_bodies("panda_hand")
        body_idx = body_ids[0]
        asset_cfg = SceneEntityCfg("robot", body_names=["panda_hand"])
        asset_cfg.body_ids = [body_idx]

        tip_pos_w, tip_quat_w = _tool_tip_pose_w(env_unwrapped, body_idx)
        socket_pos_w, socket_quat_w = _socket_pose_w(env_unwrapped)
        _print_pose_debug("initial", tip_pos_w, tip_quat_w, socket_pos_w, socket_quat_w)

        for _ in range(args_cli.steps):
            target_pos_w = socket_pos_w.clone()
            target_pos_w[:, 2] += args_cli.approach_height

            direct_pos_error, direct_axis_angle_error = compute_pose_error(
                tip_pos_w, tip_quat_w, socket_pos_w, socket_quat_w, rot_error_type="axis_angle"
            )
            lateral_error = torch.linalg.norm(direct_pos_error[:, :2], dim=1)
            orientation_error = torch.linalg.norm(direct_axis_angle_error, dim=1)
            align_mask = (lateral_error < args_cli.approach_xy_tol) & (orientation_error < args_cli.approach_rot_tol)
            target_pos_w[align_mask] = socket_pos_w[align_mask]

            pos_error, axis_angle_error = compute_pose_error(
                tip_pos_w, tip_quat_w, target_pos_w, socket_quat_w, rot_error_type="axis_angle"
            )
            actions = torch.zeros(env.action_space.shape, device=env_unwrapped.device)
            actions[:, :3] = torch.clamp(args_cli.pos_gain * pos_error, -args_cli.pos_clamp, args_cli.pos_clamp)
            actions[:, 3:6] = torch.clamp(args_cli.rot_gain * axis_angle_error, -args_cli.rot_clamp, args_cli.rot_clamp)
            env.step(actions)
            tip_pos_w, tip_quat_w = _tool_tip_pose_w(env_unwrapped, body_idx)
            socket_pos_w, socket_quat_w = _socket_pose_w(env_unwrapped)

        _print_pose_debug("final", tip_pos_w, tip_quat_w, socket_pos_w, socket_quat_w)
        env.close()


if __name__ == "__main__":
    main()
