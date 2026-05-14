"""Empirically measure how Isaac Lab relative IK actions move the contact task frame."""

from __future__ import annotations

import argparse
import json
import os
import sys

import gymnasium as gym
import torch
import warp as wp

from isaaclab.managers import SceneEntityCfg
from isaaclab_tasks.utils import add_launcher_args, launch_simulation, resolve_task_config


combine_frame_transforms = None
PEG_TIP_BODY_OFFSET_POS = None
PEG_TIP_BODY_OFFSET_ROT = None
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


def _socket_pose_w(env_unwrapped) -> tuple[torch.Tensor, torch.Tensor]:
    socket = env_unwrapped.scene["socket_frame"]
    return wp.to_torch(socket.data.root_pos_w), wp.to_torch(socket.data.root_quat_w)


def _tensor_list(value: torch.Tensor) -> list[float]:
    return [float(item) for item in value.detach().cpu().flatten().tolist()]


parser = argparse.ArgumentParser(description="Calibrate relative IK action response for the peg-in-hole task.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments.")
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0", help="Task name.")
parser.add_argument("--seed", type=int, default=42, help="Seed used for deterministic reset.")
parser.add_argument("--steps-per-probe", type=int, default=4, help="Number of repeated env steps per one-hot action.")
parser.add_argument("--zero-steps-before", type=int, default=1, help="Zero-action settling steps before each probe.")
parser.add_argument("--action-magnitude", type=float, default=0.12, help="One-hot raw action magnitude to probe.")
parser.add_argument("--summary-json", type=str, default=None, help="Optional path to write a JSON summary.")
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


def _probe_action(env, action: torch.Tensor, steps: int) -> None:
    for _ in range(steps):
        env.step(action)


def main():
    global combine_frame_transforms, PEG_TIP_BODY_OFFSET_POS, PEG_TIP_BODY_OFFSET_ROT, BODY_OFFSET

    os.makedirs("/workspace/artifacts/hydra", exist_ok=True)
    torch.manual_seed(args_cli.seed)
    env_cfg, _ = resolve_task_config(args_cli.task, "")
    env_cfg.seed = args_cli.seed

    with launch_simulation(env_cfg, args_cli):
        from isaaclab.utils.math import combine_frame_transforms
        from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole import mdp
        from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
            PEG_TIP_BODY_OFFSET_POS,
            PEG_TIP_BODY_OFFSET_ROT,
        )

        BODY_OFFSET = PEG_TIP_BODY_OFFSET_POS
        env_cfg.scene.num_envs = args_cli.num_envs
        env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
        if args_cli.disable_fabric:
            env_cfg.sim.use_fabric = False
        env_cfg.commands.socket_pose.resampling_time_range = (1.0e6, 1.0e6)
        env_cfg.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
        env_cfg.events.reset_robot_joints.params["velocity_range"] = (0.0, 0.0)

        env = gym.make(args_cli.task, cfg=env_cfg)
        env_unwrapped = env.unwrapped
        robot = env_unwrapped.scene["robot"]
        body_ids, _ = robot.find_bodies("panda_hand")
        body_idx = body_ids[0]
        peg_cfg = SceneEntityCfg("peg")
        socket_cfg = SceneEntityCfg("socket_frame")

        probes: list[tuple[str, tuple[float, float, float]]] = [
            ("zero", (0.0, 0.0, 0.0)),
            ("x_pos", (args_cli.action_magnitude, 0.0, 0.0)),
            ("x_neg", (-args_cli.action_magnitude, 0.0, 0.0)),
            ("y_pos", (0.0, args_cli.action_magnitude, 0.0)),
            ("y_neg", (0.0, -args_cli.action_magnitude, 0.0)),
            ("z_pos", (0.0, 0.0, args_cli.action_magnitude)),
            ("z_neg", (0.0, 0.0, -args_cli.action_magnitude)),
        ]

        results: dict[str, dict[str, object]] = {}
        for name, values in probes:
            torch.manual_seed(args_cli.seed)
            env.reset()

            zero_action = torch.zeros(env.action_space.shape, device=env_unwrapped.device)
            _probe_action(env, zero_action, args_cli.zero_steps_before)

            start_pos, start_quat = _action_frame_pose_w(env_unwrapped, body_idx)
            start_socket_pos, _ = _socket_pose_w(env_unwrapped)
            start_lateral, start_axial, start_rot = mdp.insertion_metrics(
                env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg
            )

            action = torch.zeros(env.action_space.shape, device=env_unwrapped.device)
            action[:, :3] = action.new_tensor(values)
            _probe_action(env, action, args_cli.steps_per_probe)

            end_pos, end_quat = _action_frame_pose_w(env_unwrapped, body_idx)
            end_socket_pos, _ = _socket_pose_w(env_unwrapped)
            end_lateral, end_axial, end_rot = mdp.insertion_metrics(
                env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg
            )

            delta_pos = end_pos - start_pos
            results[name] = {
                "action_xyz": list(values),
                "start_action_pos": _tensor_list(start_pos[0]),
                "end_action_pos": _tensor_list(end_pos[0]),
                "delta_action_pos": _tensor_list(delta_pos[0]),
                "start_socket_pos": _tensor_list(start_socket_pos[0]),
                "end_socket_pos": _tensor_list(end_socket_pos[0]),
                "start_metrics": {
                    "lateral": float(start_lateral[0].item()),
                    "axial": float(start_axial[0].item()),
                    "rot": float(start_rot[0].item()),
                },
                "end_metrics": {
                    "lateral": float(end_lateral[0].item()),
                    "axial": float(end_axial[0].item()),
                    "rot": float(end_rot[0].item()),
                },
                "start_action_quat": _tensor_list(start_quat[0]),
                "end_action_quat": _tensor_list(end_quat[0]),
            }
            print(
                f"[CALIBRATE] {name:>5} action={list(values)} "
                f"delta_pos={results[name]['delta_action_pos']} "
                f"metrics=({results[name]['end_metrics']})",
                flush=True,
            )

        columns = []
        dominant_response = {}
        for axis in ("x", "y", "z"):
            pos_delta = torch.tensor(results[f"{axis}_pos"]["delta_action_pos"], device=env_unwrapped.device)
            neg_delta = torch.tensor(results[f"{axis}_neg"]["delta_action_pos"], device=env_unwrapped.device)
            column = (pos_delta - neg_delta) / (2.0 * args_cli.action_magnitude)
            columns.append(column)
            dominant_axis_idx = int(torch.argmax(torch.abs(column)).item())
            dominant_response[axis] = {
                "world_axis": ("x", "y", "z")[dominant_axis_idx],
                "sign": 1.0 if float(column[dominant_axis_idx].item()) >= 0.0 else -1.0,
                "gain": float(column[dominant_axis_idx].item()),
                "column": _tensor_list(column),
            }

        response_matrix = torch.stack(columns, dim=1)
        summary = {
            "task": args_cli.task,
            "seed": args_cli.seed,
            "steps_per_probe": args_cli.steps_per_probe,
            "zero_steps_before": args_cli.zero_steps_before,
            "action_magnitude": args_cli.action_magnitude,
            "probes": results,
            "response_matrix_world_delta_per_raw_action": [
                _tensor_list(response_matrix[row_idx]) for row_idx in range(3)
            ],
            "dominant_response": dominant_response,
        }
        print(
            "[CALIBRATE] response_matrix_world_delta_per_raw_action="
            f"{summary['response_matrix_world_delta_per_raw_action']}",
            flush=True,
        )
        print(f"[CALIBRATE] dominant_response={dominant_response}", flush=True)

        if args_cli.summary_json:
            summary_path = os.path.abspath(args_cli.summary_json)
            os.makedirs(os.path.dirname(summary_path), exist_ok=True)
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, sort_keys=True)
            print(f"[CALIBRATE] wrote summary to {summary_path}", flush=True)

        env.close()


if __name__ == "__main__":
    main()
