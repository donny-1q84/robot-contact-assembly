"""Run a simple scripted peg-in-hole baseline for the robot_contact_assembly Isaac Lab task."""

from __future__ import annotations

import argparse
import json
import os
import sys

import gymnasium as gym
import torch
import warp as wp

from isaaclab_tasks.utils import add_launcher_args, launch_simulation, resolve_task_config


RigidObject = None
SceneEntityCfg = None
combine_frame_transforms = None
compute_pose_error = None
PEG_TIP_BODY_OFFSET_POS = None
PEG_TIP_BODY_OFFSET_ROT = None
mdp = None
BODY_OFFSET = None


def _hand_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    robot = env_unwrapped.scene["robot"]
    hand_pos_w = wp.to_torch(robot.data.body_pos_w)[:, body_idx]
    hand_quat_w = wp.to_torch(robot.data.body_quat_w)[:, body_idx]
    return hand_pos_w, hand_quat_w


def _action_frame_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env_unwrapped, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    offset_quat = hand_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)


def _clamp_actions(values: torch.Tensor, limit: torch.Tensor | float) -> torch.Tensor:
    return torch.clamp(values, min=-limit, max=limit)

parser = argparse.ArgumentParser(description="Scripted baseline for robot_contact_assembly Isaac Lab tasks.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=None, help="Override number of environments.")
parser.add_argument("--steps", type=int, default=200, help="Number of env steps to run before exit in headless mode.")
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-IK-Rel-Play-v0", help="Task name.")
parser.add_argument("--seed", type=int, default=42, help="Deterministic seed for the scripted baseline.")
parser.add_argument("--video", action="store_true", default=False, help="Record one scripted reference video.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video in steps.")
parser.add_argument(
    "--video_backend",
    type=str,
    default="viewport",
    choices=("viewport",),
    help="Video recording backend for the scripted rollout.",
)
parser.add_argument(
    "--video_folder",
    type=str,
    default=None,
    help="Optional directory for recorded videos. Defaults to a local scripted-video folder under /workspace/artifacts.",
)
parser.add_argument(
    "--summary-json",
    type=str,
    default=None,
    help="Optional path to write a JSON summary for fixed-seed evaluation runs.",
)
parser.add_argument("--approach-height", type=float, default=0.05, help="Approach offset over the target along +Z.")
parser.add_argument("--approach-xy-tol", type=float, default=0.015, help="Lateral tolerance before switching to insertion.")
parser.add_argument("--approach-z-tol", type=float, default=0.02, help="World-Z tolerance for the pre-insertion hold pose.")
parser.add_argument("--approach-rot-tol", type=float, default=0.25, help="Orientation tolerance before switching to insertion.")
parser.add_argument(
    "--coupled-approach",
    action="store_true",
    default=False,
    help="Use the legacy controller that rotates while translating toward the socket.",
)
parser.add_argument("--pos-gain", type=float, default=2.0, help="Proportional gain for position error.")
parser.add_argument("--rot-gain", type=float, default=2.0, help="Proportional gain for axis-angle orientation error.")
parser.add_argument("--pos-clamp", type=float, default=0.12, help="Clamp applied to each translational action dimension.")
parser.add_argument("--rot-clamp", type=float, default=0.4, help="Clamp applied to each rotational action dimension.")
parser.add_argument("--polish-xy-tol", type=float, default=0.008, help="Lateral tolerance to enter the near-contact polish phase.")
parser.add_argument("--polish-z-tol", type=float, default=0.012, help="Axial tolerance to enter the near-contact polish phase.")
parser.add_argument("--polish-pos-gain", type=float, default=1.2, help="Lateral position gain during the near-contact polish phase.")
parser.add_argument("--polish-pos-clamp", type=float, default=0.008, help="Lateral position clamp during the near-contact polish phase.")
parser.add_argument("--polish-rot-gain", type=float, default=5.0, help="Orientation gain during the near-contact polish phase.")
parser.add_argument("--polish-rot-clamp", type=float, default=0.35, help="Orientation clamp during the near-contact polish phase.")
parser.add_argument("--settle-xy-tol", type=float, default=0.004, help="Lateral tolerance required before final seating.")
parser.add_argument("--settle-rot-tol", type=float, default=0.24, help="Orientation error threshold to enter the final seating phase.")
parser.add_argument("--settle-pos-gain", type=float, default=0.8, help="Lateral position gain during the final seating phase.")
parser.add_argument("--settle-pos-clamp", type=float, default=0.004, help="Lateral position clamp during the final seating phase.")
parser.add_argument("--settle-z-gain", type=float, default=0.8, help="Axial position gain during the final seating phase.")
parser.add_argument("--settle-z-clamp", type=float, default=0.004, help="Axial position clamp during the final seating phase.")
parser.add_argument("--settle-rot-gain", type=float, default=1.5, help="Orientation gain during the final seating phase.")
parser.add_argument("--settle-rot-clamp", type=float, default=0.12, help="Orientation clamp during the final seating phase.")
add_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
skip_auto_enable_cameras = os.environ.get("RCA_SKIP_AUTO_ENABLE_CAMERAS", "0") == "1"
if args_cli.video and args_cli.video_backend == "viewport" and not skip_auto_enable_cameras:
    args_cli.enable_cameras = True
hydra_args.extend(
    [
        r"hydra.run.dir=/workspace/artifacts/hydra/${now:%Y-%m-%d}/${now:%H-%M-%S}",
        "hydra.output_subdir=null",
    ]
)
sys.argv = [sys.argv[0]] + hydra_args

import robot_contact_assembly_tasks.tasks  # noqa: F401,E402


def _tool_tip_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env_unwrapped, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    offset_quat = hand_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)


def _socket_pose_w(env_unwrapped) -> tuple[torch.Tensor, torch.Tensor]:
    socket = env_unwrapped.scene["socket_frame"]
    return wp.to_torch(socket.data.root_pos_w), wp.to_torch(socket.data.root_quat_w)


def _target_action_frame_pose_w(socket_pos_w: torch.Tensor, socket_quat_w: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    return socket_pos_w.clone(), socket_quat_w.clone()


def main():
    global RigidObject, SceneEntityCfg, combine_frame_transforms, compute_pose_error
    global PEG_TIP_BODY_OFFSET_POS, PEG_TIP_BODY_OFFSET_ROT, mdp, BODY_OFFSET

    os.makedirs("/workspace/artifacts/hydra", exist_ok=True)
    torch.manual_seed(args_cli.seed)
    env_cfg, _ = resolve_task_config(args_cli.task, "")
    env_cfg.seed = args_cli.seed

    with launch_simulation(env_cfg, args_cli):
        from isaaclab.assets import RigidObject
        from isaaclab.managers import SceneEntityCfg
        from isaaclab.utils.math import combine_frame_transforms, compute_pose_error
        from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole import mdp
        from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
            PEG_TIP_BODY_OFFSET_POS,
            PEG_TIP_BODY_OFFSET_ROT,
        )

        BODY_OFFSET = PEG_TIP_BODY_OFFSET_POS
        env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
        env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
        if args_cli.disable_fabric:
            env_cfg.sim.use_fabric = False
        # Keep a fixed target for the scripted baseline so convergence is measured against one command.
        env_cfg.commands.socket_pose.resampling_time_range = (1.0e6, 1.0e6)

        render_mode = "rgb_array" if args_cli.video and args_cli.video_backend == "viewport" else None
        env = gym.make(args_cli.task, cfg=env_cfg, render_mode=render_mode)
        video_folder = None
        if args_cli.video:
            video_folder = (
                os.path.abspath(args_cli.video_folder)
                if args_cli.video_folder
                else os.path.join("/workspace/artifacts/videos/scripted", f"seed_{args_cli.seed}")
            )
            os.makedirs(video_folder, exist_ok=True)
            env = gym.wrappers.RecordVideo(
                env,
                video_folder=video_folder,
                step_trigger=lambda step: step == 0,
                video_length=min(args_cli.video_length, args_cli.steps),
                disable_logger=True,
            )
            print(
                f"[SCRIPTED] recording video with {args_cli.video_backend} backend to {video_folder} "
                f"(length={min(args_cli.video_length, args_cli.steps)})",
                flush=True,
            )
        env_unwrapped = env.unwrapped
        print(f"[INFO]: Gym observation space: {env.observation_space}", flush=True)
        print(f"[INFO]: Gym action space: {env.action_space}", flush=True)
        env.reset()

        robot = env_unwrapped.scene["robot"]
        body_ids, _ = robot.find_bodies("panda_hand")
        body_idx = body_ids[0]
        peg_cfg = SceneEntityCfg("peg")
        socket_cfg = SceneEntityCfg("socket_frame")

        initial_lateral = None
        initial_axial = None
        initial_rot = None
        final_lateral = None
        final_axial = None
        final_rot = None
        final_success = None
        success_step = None
        rotate_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        polish_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        settle_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)

        sim = env_unwrapped.sim
        for step in range(args_cli.steps):
            if sim.visualizers and not any(v.is_running() and not v.is_closed for v in sim.visualizers):
                break

            action_pos_w, action_quat_w = _action_frame_pose_w(env_unwrapped, body_idx)
            socket_pos_w, socket_quat_w = _socket_pose_w(env_unwrapped)
            target_action_pos_w, target_action_quat_w = _target_action_frame_pose_w(socket_pos_w, socket_quat_w)

            lateral_error, axial_error, orientation_error = mdp.insertion_metrics(
                env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg
            )

            approach_pos_w = target_action_pos_w.clone()
            approach_pos_w[:, 2] += args_cli.approach_height
            target_pos_w = approach_pos_w.clone()
            target_quat_w = target_action_quat_w.clone()

            if args_cli.coupled_approach:
                position_ready = (lateral_error < args_cli.approach_xy_tol) & (
                    orientation_error < args_cli.approach_rot_tol
                )
                rotate_state |= position_ready
                insert_mask = position_ready
            else:
                # Decouple gross translation from large orientation changes. With a rigid tip offset, rotating
                # while still far from the socket can move the tip away from the approach corridor.
                approach_z_error = torch.abs(action_pos_w[:, 2] - approach_pos_w[:, 2])
                position_ready = (lateral_error < args_cli.approach_xy_tol) & (
                    approach_z_error < args_cli.approach_z_tol
                )
                rotate_state |= position_ready
                target_quat_w = action_quat_w.clone()
                target_quat_w[rotate_state] = target_action_quat_w[rotate_state]
                insert_mask = (
                    rotate_state
                    & (lateral_error < args_cli.approach_xy_tol)
                    & (orientation_error < args_cli.approach_rot_tol)
                )

            target_pos_w[insert_mask] = target_action_pos_w[insert_mask]
            polish_mask = (lateral_error < args_cli.polish_xy_tol) & (axial_error < args_cli.polish_z_tol)
            polish_state |= polish_mask
            settle_mask = polish_state & (lateral_error < args_cli.settle_xy_tol) & (orientation_error < args_cli.settle_rot_tol)
            settle_state = settle_mask

            polish_only = polish_state & ~settle_state
            target_pos_w[polish_only, 2] = action_pos_w[polish_only, 2]

            pos_error, axis_angle_error = compute_pose_error(
                action_pos_w, action_quat_w, target_pos_w, target_quat_w, rot_error_type="axis_angle"
            )

            actions = torch.zeros(env.action_space.shape, device=env_unwrapped.device)
            rot_gain = torch.full_like(axis_angle_error, args_cli.rot_gain)
            rot_gain[polish_state] = args_cli.polish_rot_gain
            rot_gain[settle_state] = args_cli.settle_rot_gain
            rot_clamp = torch.full_like(axis_angle_error, args_cli.rot_clamp)
            rot_clamp[polish_state] = args_cli.polish_rot_clamp
            rot_clamp[settle_state] = args_cli.settle_rot_clamp

            actions[:, :3] = _clamp_actions(args_cli.pos_gain * pos_error, args_cli.pos_clamp)
            actions[:, 3:6] = _clamp_actions(rot_gain * axis_angle_error, rot_clamp)

            if polish_only.any():
                actions[polish_only, :2] = _clamp_actions(
                    args_cli.polish_pos_gain * pos_error[polish_only, :2],
                    args_cli.polish_pos_clamp,
                )
                actions[polish_only, 2] = 0.0
                actions[polish_only, 3:6] = _clamp_actions(
                    args_cli.polish_rot_gain * axis_angle_error[polish_only],
                    args_cli.polish_rot_clamp,
                )

            if settle_state.any():
                actions[settle_state, :2] = _clamp_actions(
                    args_cli.settle_pos_gain * pos_error[settle_state, :2],
                    args_cli.settle_pos_clamp,
                )
                actions[settle_state, 2] = _clamp_actions(
                    args_cli.settle_z_gain * pos_error[settle_state, 2],
                    args_cli.settle_z_clamp,
                )
                actions[settle_state, 3:6] = _clamp_actions(
                    args_cli.settle_rot_gain * axis_angle_error[settle_state],
                    args_cli.settle_rot_clamp,
                )

            env.step(actions)

            lateral, axial, rot = mdp.insertion_metrics(env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)
            success = mdp.insertion_success(env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)

            if step == 0:
                initial_lateral = lateral.mean().item()
                initial_axial = axial.mean().item()
                initial_rot = rot.mean().item()

            final_lateral = lateral.mean().item()
            final_axial = axial.mean().item()
            final_rot = rot.mean().item()
            final_success = success.float().mean().item()

            if step % 25 == 0 or step == args_cli.steps - 1:
                print(
                    f"[SCRIPTED] step={step:04d} lateral={final_lateral:.4f} axial={final_axial:.4f} "
                    f"rot={final_rot:.4f} success_rate={final_success:.3f} "
                    f"position_ready={position_ready.float().mean().item():.3f} "
                    f"rotate_ready={rotate_state.float().mean().item():.3f} "
                    f"insert_ready={insert_mask.float().mean().item():.3f} "
                    f"polish_ready={polish_only.float().mean().item():.3f} "
                    f"settle_ready={settle_state.float().mean().item():.3f}",
                    flush=True,
                )

            if success.any():
                success_step = step
                print(f"[SCRIPTED] success reached at step={step:04d}", flush=True)
                break

        env.close()
        summary = {
            "task": args_cli.task,
            "seed": args_cli.seed,
            "steps_requested": args_cli.steps,
            "success_step": success_step,
            "initial_lateral": initial_lateral,
            "final_lateral": final_lateral,
            "initial_axial": initial_axial,
            "final_axial": final_axial,
            "initial_rot": initial_rot,
            "final_rot": final_rot,
            "final_success_rate": final_success,
            "video_backend": args_cli.video_backend if args_cli.video else None,
            "video_folder": video_folder,
            "coupled_approach": args_cli.coupled_approach,
        }
        print(
            "[SCRIPTED] summary "
            f"seed={summary['seed']} "
            f"initial_lateral={summary['initial_lateral']:.4f} final_lateral={summary['final_lateral']:.4f} "
            f"initial_axial={summary['initial_axial']:.4f} final_axial={summary['final_axial']:.4f} "
            f"initial_rot={summary['initial_rot']:.4f} final_rot={summary['final_rot']:.4f} "
            f"final_success_rate={summary['final_success_rate']:.3f} "
            f"success_step={summary['success_step']}",
            flush=True,
        )
        if args_cli.summary_json:
            summary_path = os.path.abspath(args_cli.summary_json)
            os.makedirs(os.path.dirname(summary_path), exist_ok=True)
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, sort_keys=True)
            print(f"[SCRIPTED] wrote summary to {summary_path}", flush=True)


if __name__ == "__main__":
    main()
