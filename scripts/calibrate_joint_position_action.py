"""Empirically measure how JointPositionAction targets move the action frame."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import sys

from isaaclab.app import AppLauncher

add_launcher_args = AppLauncher.add_app_launcher_args


gym = None
torch = None
wp = None
combine_frame_transforms = None
PEG_TIP_BODY_OFFSET_POS = None
PEG_TIP_BODY_OFFSET_ROT = None
BODY_OFFSET = None


ARM_JOINT_NAMES = (
    "panda_joint1",
    "panda_joint2",
    "panda_joint3",
    "panda_joint4",
    "panda_joint5",
    "panda_joint6",
    "panda_joint7",
)


def _as_torch(value) -> torch.Tensor:
    return value if isinstance(value, torch.Tensor) else wp.to_torch(value)


def _hand_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    robot = env_unwrapped.scene["robot"]
    hand_pos_w = _as_torch(robot.data.body_pos_w)[:, body_idx]
    hand_quat_w = _as_torch(robot.data.body_quat_w)[:, body_idx]
    return hand_pos_w.detach().clone(), hand_quat_w.detach().clone()


def _action_frame_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env_unwrapped, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    offset_quat = hand_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    action_pos_w, action_quat_w = combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)
    return action_pos_w.detach().clone(), action_quat_w.detach().clone()


def _tensor_list(value: torch.Tensor) -> list[float]:
    return [float(item) for item in value.detach().cpu().flatten().tolist()]


def _step(env, action: torch.Tensor, steps: int) -> None:
    for _ in range(max(0, steps)):
        env.step(action)


def _close_ignoring_system_exit(close_fn, label: str) -> None:
    try:
        close_fn()
    except SystemExit as exc:
        print(f"[WARN]: Ignoring SystemExit while closing {label}: {exc!r}", file=sys.stderr, flush=True)


def _load_runtime_modules() -> None:
    """Import Isaac runtime-dependent modules only after SimulationApp exists."""

    global gym, torch, wp
    if gym is not None:
        return
    import gymnasium as gym_module
    import torch as torch_module
    import warp as wp_module

    gym = gym_module
    torch = torch_module
    wp = wp_module


@contextmanager
def _launched_env_cfg(task_name: str, args):
    app_launcher = AppLauncher(args)
    simulation_app = app_launcher.app
    try:
        _load_runtime_modules()
        import robot_contact_assembly_tasks.tasks  # noqa: F401
        from isaaclab_tasks.utils import parse_env_cfg

        env_cfg = parse_env_cfg(
            task_name,
            device=args.device if args.device is not None else "cuda:0",
            num_envs=args.num_envs,
            use_fabric=False if args.disable_fabric else None,
        )
        env_cfg.seed = args.seed
        yield env_cfg
    finally:
        _close_ignoring_system_exit(simulation_app.close, "simulation app")


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments.")
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-JointPos-Contact-Play-v0")
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--settle-steps", type=int, default=30)
parser.add_argument("--steps-per-probe", type=int, default=8)
parser.add_argument("--joint-delta-magnitude", type=float, default=0.040)
parser.add_argument("--summary-json", type=str, default=None)
add_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
hydra_args.extend(
    [
        r"hydra.run.dir=/workspace/artifacts/hydra/${now:%Y-%m-%d}/${now:%H-%M-%S}",
        "hydra.output_subdir=null",
    ]
)
sys.argv = [sys.argv[0]] + hydra_args


def main() -> None:
    global combine_frame_transforms, PEG_TIP_BODY_OFFSET_POS, PEG_TIP_BODY_OFFSET_ROT, BODY_OFFSET

    os.makedirs("/workspace/artifacts/hydra", exist_ok=True)

    with _launched_env_cfg(args_cli.task, args_cli) as env_cfg:
        torch.manual_seed(args_cli.seed)
        from isaaclab.utils.math import combine_frame_transforms
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
        arm_joint_ids_raw, arm_joint_names = robot.find_joints(list(ARM_JOINT_NAMES))
        arm_joint_ids = torch.as_tensor(arm_joint_ids_raw, device=env_unwrapped.device, dtype=torch.long)

        if len(arm_joint_names) != len(ARM_JOINT_NAMES):
            raise RuntimeError(f"expected 7 arm joints, got {arm_joint_names}")
        if env.action_space.shape[-1] != len(ARM_JOINT_NAMES):
            raise RuntimeError(f"expected 7D JointPositionAction task, got action shape {env.action_space.shape}")

        probes: dict[str, dict[str, object]] = {}
        joint_delta_magnitude = float(args_cli.joint_delta_magnitude)
        if joint_delta_magnitude <= 0.0:
            raise ValueError("--joint-delta-magnitude must be positive")

        def run_probe(name: str, joint_offset: torch.Tensor) -> dict[str, object]:
            torch.manual_seed(args_cli.seed)
            env.reset()

            base_joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, arm_joint_ids).detach().clone()
            hold_action = base_joint_pos.detach().clone()
            _step(env, hold_action, args_cli.settle_steps)
            base_joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, arm_joint_ids).detach().clone()
            hold_action = base_joint_pos.detach().clone()
            start_pos, start_quat = _action_frame_pose_w(env_unwrapped, body_idx)

            probe_action = base_joint_pos + joint_offset
            _step(env, probe_action, args_cli.steps_per_probe)
            end_pos, end_quat = _action_frame_pose_w(env_unwrapped, body_idx)
            end_joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, arm_joint_ids).detach().clone()

            delta_pos = end_pos - start_pos
            result = {
                "joint_offset_target": _tensor_list(joint_offset[0]),
                "base_joint_pos": _tensor_list(base_joint_pos[0]),
                "end_joint_pos": _tensor_list(end_joint_pos[0]),
                "actual_joint_delta": _tensor_list((end_joint_pos - base_joint_pos)[0]),
                "start_action_pos": _tensor_list(start_pos[0]),
                "end_action_pos": _tensor_list(end_pos[0]),
                "delta_action_pos": _tensor_list(delta_pos[0]),
                "start_action_quat": _tensor_list(start_quat[0]),
                "end_action_quat": _tensor_list(end_quat[0]),
            }
            print(
                f"[JOINT-CALIBRATE] {name} target={result['joint_offset_target']} "
                f"actual_joint_delta={result['actual_joint_delta']} delta_pos={result['delta_action_pos']}",
                flush=True,
            )
            return result

        zero_offset = torch.zeros((1, len(ARM_JOINT_NAMES)), device=env_unwrapped.device)
        probes["zero"] = run_probe("zero", zero_offset)
        columns: list[torch.Tensor] = []
        for idx, joint_name in enumerate(arm_joint_names):
            pos_offset = torch.zeros_like(zero_offset)
            neg_offset = torch.zeros_like(zero_offset)
            pos_offset[:, idx] = joint_delta_magnitude
            neg_offset[:, idx] = -joint_delta_magnitude
            probes[f"{joint_name}_pos"] = run_probe(f"{joint_name}_pos", pos_offset)
            probes[f"{joint_name}_neg"] = run_probe(f"{joint_name}_neg", neg_offset)
            pos_delta = torch.tensor(
                probes[f"{joint_name}_pos"]["delta_action_pos"],
                device=env_unwrapped.device,
                dtype=torch.float32,
            )
            neg_delta = torch.tensor(
                probes[f"{joint_name}_neg"]["delta_action_pos"],
                device=env_unwrapped.device,
                dtype=torch.float32,
            )
            columns.append((pos_delta - neg_delta) / (2.0 * joint_delta_magnitude))

        response_matrix = torch.stack(columns, dim=1)
        summary = {
            "task": args_cli.task,
            "seed": args_cli.seed,
            "settle_steps": args_cli.settle_steps,
            "steps_per_probe": args_cli.steps_per_probe,
            "joint_delta_magnitude": joint_delta_magnitude,
            "joint_names": list(arm_joint_names),
            "joint_ids": [int(item) for item in arm_joint_ids_raw],
            "probes": probes,
            "response_matrix_world_delta_per_joint_rad": [
                _tensor_list(response_matrix[row_idx]) for row_idx in range(3)
            ],
        }
        print(
            "[JOINT-CALIBRATE] response_matrix_world_delta_per_joint_rad="
            f"{summary['response_matrix_world_delta_per_joint_rad']}",
            flush=True,
        )
        if args_cli.summary_json:
            summary_path = os.path.abspath(args_cli.summary_json)
            os.makedirs(os.path.dirname(summary_path), exist_ok=True)
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, sort_keys=True)
            print(f"[JOINT-CALIBRATE] wrote summary to {summary_path}", flush=True)
        env.close()


if __name__ == "__main__":
    main()
