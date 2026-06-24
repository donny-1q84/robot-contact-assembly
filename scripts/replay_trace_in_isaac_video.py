#!/usr/bin/env python3
"""Render a validated scripted trace inside Isaac Sim.

This is intentionally different from ``render_trace_video.py``: it creates the
real Isaac Lab scene, writes the recorded robot/socket/peg states from a trace,
and captures frames through Isaac rendering. The source trace remains the
semantic proof; this script only turns that proof into an Isaac-rendered video.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys

import gymnasium as gym
import imageio.v2 as imageio
import numpy as np
import torch

_FORCE_APP_LAUNCHER = os.environ.get("RCA_FORCE_APP_LAUNCHER", "0") == "1"
_USE_TASK_UTILS_LAUNCHER = False
_ARTIFACT_ROOT = os.environ.get("RCA_ARTIFACT_ROOT", "/workspace/artifacts")
_HYDRA_ROOT = os.path.join(_ARTIFACT_ROOT, "hydra")

if not _FORCE_APP_LAUNCHER:
    try:
        from isaaclab_tasks.utils import add_launcher_args, launch_simulation, resolve_task_config

        _USE_TASK_UTILS_LAUNCHER = True
    except (ImportError, ModuleNotFoundError):
        pass

if not _USE_TASK_UTILS_LAUNCHER:
    from isaaclab.app import AppLauncher

    add_launcher_args = AppLauncher.add_app_launcher_args
    launch_simulation = None
    resolve_task_config = None
    _USE_TASK_UTILS_LAUNCHER = False


def _close_ignoring_system_exit(close_fn, label: str) -> None:
    try:
        close_fn()
    except SystemExit as exc:
        print(f"[trace-replay] ignoring SystemExit while closing {label}: {exc!r}", file=sys.stderr, flush=True)


@contextmanager
def _launched_env_cfg(task_name: str, args):
    if _USE_TASK_UTILS_LAUNCHER:
        import robot_contact_assembly_tasks.tasks  # noqa: F401

        env_cfg, _ = resolve_task_config(task_name, "")
        env_cfg.seed = args.seed
        with launch_simulation(env_cfg, args):
            yield env_cfg
        return

    app_launcher = AppLauncher(args)
    simulation_app = app_launcher.app
    try:
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


def _load_trace(path: Path) -> tuple[dict, list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object with summary and steps")
    summary = payload.get("summary")
    steps = payload.get("steps")
    if not isinstance(summary, dict) or not isinstance(steps, list):
        raise ValueError(f"{path} must contain summary object and steps list")
    rows = [row for row in steps if isinstance(row, dict)]
    if not rows:
        raise ValueError(f"{path} contains no replayable trace rows")
    return summary, rows


def _vec(row: dict, *keys: str, length: int) -> list[float] | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, list) and len(value) == length:
            return [float(part) for part in value]
    return None


def _tensor(device: torch.device | str, value: list[float]) -> torch.Tensor:
    return torch.tensor(value, device=device, dtype=torch.float32).unsqueeze(0)


def _frame_to_uint8(frame) -> np.ndarray:
    if isinstance(frame, torch.Tensor):
        array = frame.detach().cpu().numpy()
    else:
        array = np.asarray(frame)
    if array.ndim == 4:
        array = array[0]
    if array.shape[-1] == 4:
        array = array[..., :3]
    if array.dtype == np.uint8:
        return array
    if np.issubdtype(array.dtype, np.floating) and float(np.nanmax(array)) <= 1.0:
        array = array * 255.0
    return np.clip(array, 0, 255).astype(np.uint8)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _write_kinematic_root_pose(env_unwrapped, name: str, pos_w: torch.Tensor, quat_w: torch.Tensor) -> None:
    asset = env_unwrapped.scene[name]
    with torch.inference_mode():
        asset.write_root_pose_to_sim(torch.cat((pos_w, quat_w), dim=-1))
        if hasattr(asset, "write_root_velocity_to_sim"):
            asset.write_root_velocity_to_sim(torch.zeros((pos_w.shape[0], 6), device=pos_w.device, dtype=pos_w.dtype))


def _write_socket_guide(env_unwrapped, row: dict, wall_center_offset: float, identity_quat: tuple[float, ...]) -> None:
    socket_pos = _vec(row, "post_socket_pos_w", "socket_pos_w", length=3)
    socket_quat = _vec(row, "post_socket_quat_w", "socket_quat_w", length=4)
    if socket_pos is None or socket_quat is None:
        return
    device = env_unwrapped.device
    socket_pos_w = _tensor(device, socket_pos)
    socket_quat_w = _tensor(device, socket_quat)
    wall_quat_w = _tensor(device, list(identity_quat))
    x_offset = _tensor(device, [wall_center_offset, 0.0, 0.0])
    y_offset = _tensor(device, [0.0, wall_center_offset, 0.0])
    _write_kinematic_root_pose(env_unwrapped, "socket_frame", socket_pos_w, socket_quat_w)
    _write_kinematic_root_pose(env_unwrapped, "socket_wall_left", socket_pos_w - x_offset, wall_quat_w)
    _write_kinematic_root_pose(env_unwrapped, "socket_wall_right", socket_pos_w + x_offset, wall_quat_w)
    _write_kinematic_root_pose(env_unwrapped, "socket_wall_front", socket_pos_w - y_offset, wall_quat_w)
    _write_kinematic_root_pose(env_unwrapped, "socket_wall_back", socket_pos_w + y_offset, wall_quat_w)


def _write_robot_state(env_unwrapped, row: dict, arm_joint_ids: torch.Tensor) -> None:
    joint_pos = _vec(row, "post_arm_joint_pos", "arm_joint_pos", length=7)
    if joint_pos is None:
        return
    robot = env_unwrapped.scene["robot"]
    pos = _tensor(env_unwrapped.device, joint_pos)
    vel = torch.zeros_like(pos)
    with torch.inference_mode():
        try:
            robot.write_joint_state_to_sim(pos, vel, joint_ids=arm_joint_ids)
        except TypeError:
            robot.write_joint_state_to_sim(pos, vel)
        if hasattr(robot, "set_joint_position_target"):
            try:
                robot.set_joint_position_target(pos, joint_ids=arm_joint_ids)
            except TypeError:
                robot.set_joint_position_target(pos)


def _write_peg_from_trace_tip(
    env_unwrapped,
    row: dict,
    peg_root_from_tip_pos: tuple[float, ...],
    peg_root_from_tip_rot: tuple[float, ...],
) -> None:
    _ = (env_unwrapped, row, peg_root_from_tip_pos, peg_root_from_tip_rot)
    # The current task welds the peg into the Franka articulation. There is no
    # separate peg RigidObject pose to write safely; the articulation-link peg is
    # replayed through robot joint states instead.
    return


def _render_frame(env, env_unwrapped):
    if hasattr(env_unwrapped, "sim") and hasattr(env_unwrapped.sim, "render"):
        env_unwrapped.sim.render()
    frame = env.render()
    if frame is None:
        raise RuntimeError("env.render() returned None; ensure render_mode='rgb_array' and rendering is enabled")
    return _frame_to_uint8(frame)


def _select_rows(rows: list[dict], start_step: int, end_step: int | None, stride: int) -> list[dict]:
    selected = []
    for row in rows:
        step = row.get("step")
        if not isinstance(step, int):
            continue
        if step < start_step:
            continue
        if end_step is not None and step > end_step:
            continue
        if (step - start_step) % stride != 0:
            continue
        selected.append(row)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-json", required=True, type=Path)
    parser.add_argument("--task", default="RCA-PegInHole-Franka-JointPos-Contact-Play-v0")
    parser.add_argument("--video-folder", required=True, type=Path)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--start-step", type=int, default=0)
    parser.add_argument("--end-step", type=int)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--num-envs", type=int, default=1)
    parser.add_argument("--disable-fabric", action="store_true")
    parser.add_argument("--require-source-success", action="store_true")
    parser.add_argument("--write-peg-root-from-trace", action="store_true")
    add_launcher_args(parser)
    args_cli, hydra_args = parser.parse_known_args()
    if hasattr(args_cli, "enable_cameras"):
        args_cli.enable_cameras = True
    hydra_args.extend(
        [
            f"hydra.run.dir={_HYDRA_ROOT}/trace_replay_${{now:%Y-%m-%d}}/${{now:%H-%M-%S}}",
            "hydra.output_subdir=null",
        ]
    )
    sys.argv = [sys.argv[0]] + hydra_args

    source_summary, rows = _load_trace(args_cli.trace_json)
    success_step = source_summary.get("success_step")
    if args_cli.require_source_success and success_step is None and not any(row.get("success") is True for row in rows):
        raise RuntimeError(f"source trace has no success step: {args_cli.trace_json}")
    selected_rows = _select_rows(rows, args_cli.start_step, args_cli.end_step, max(1, args_cli.stride))
    if not selected_rows:
        raise RuntimeError("selected replay range contains no trace rows")

    args_cli.video_folder.mkdir(parents=True, exist_ok=True)
    video_path = args_cli.video_folder / "isaac_trace_replay.mp4"

    with _launched_env_cfg(args_cli.task, args_cli) as env_cfg:
        from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
            IDENTITY_QUAT,
            PEG_ROOT_FROM_TIP_POS,
            PEG_ROOT_FROM_TIP_ROT,
            SOCKET_GUIDE_INNER_HALF_WIDTH_M,
            SOCKET_GUIDE_WALL_THICKNESS_M,
        )

        env_cfg.scene.num_envs = 1
        env_cfg.scene.env_spacing = 2.5
        env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
        if args_cli.disable_fabric:
            env_cfg.sim.use_fabric = False
        env_cfg.observations.policy.enable_corruption = False
        env_cfg.commands.socket_pose.resampling_time_range = (1.0e6, 1.0e6)
        env_cfg.viewer.eye = (1.25, 0.85, 0.95)
        env_cfg.viewer.lookat = (0.43, -0.04, 0.37)

        env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array")
        env_unwrapped = env.unwrapped
        env.reset()

        robot = env_unwrapped.scene["robot"]
        arm_joint_ids_raw, arm_joint_names = robot.find_joints(
            [
                "panda_joint1",
                "panda_joint2",
                "panda_joint3",
                "panda_joint4",
                "panda_joint5",
                "panda_joint6",
                "panda_joint7",
            ]
        )
        if len(arm_joint_names) != 7:
            raise RuntimeError(f"expected 7 arm joints, got {arm_joint_names}")
        arm_joint_ids = torch.as_tensor(arm_joint_ids_raw, device=env_unwrapped.device, dtype=torch.long)
        wall_center_offset = SOCKET_GUIDE_INNER_HALF_WIDTH_M + 0.5 * SOCKET_GUIDE_WALL_THICKNESS_M

        frames_written = 0
        first_success_frame = None
        writer = imageio.get_writer(video_path, fps=max(1, int(args_cli.fps)))
        try:
            for row in selected_rows:
                _write_socket_guide(env_unwrapped, row, wall_center_offset, IDENTITY_QUAT)
                _write_robot_state(env_unwrapped, row, arm_joint_ids)
                if args_cli.write_peg_root_from_trace:
                    _write_peg_from_trace_tip(env_unwrapped, row, PEG_ROOT_FROM_TIP_POS, PEG_ROOT_FROM_TIP_ROT)
                frame = _render_frame(env, env_unwrapped)
                writer.append_data(frame)
                if first_success_frame is None and row.get("success") is True:
                    first_success_frame = frames_written
                frames_written += 1
        finally:
            writer.close()
            _close_ignoring_system_exit(env.close, "gym env")

    replay_summary = {
        "artifact_status": "complete",
        "frames_written": frames_written,
        "first_success_frame": first_success_frame,
        "fps": max(1, int(args_cli.fps)),
        "replay_end_step": selected_rows[-1].get("step"),
        "replay_start_step": selected_rows[0].get("step"),
        "replay_stride": max(1, args_cli.stride),
        "source_best_axial": source_summary.get("best_axial"),
        "source_best_lateral": source_summary.get("best_lateral"),
        "source_best_rot": source_summary.get("best_rot"),
        "source_final_success_rate": source_summary.get("final_success_rate"),
        "source_max_contact_force_magnitude": source_summary.get("max_contact_force_magnitude"),
        "source_success_step": success_step,
        "source_trace_json": str(args_cli.trace_json),
        "task": args_cli.task,
        "video_path": str(video_path),
    }
    if args_cli.summary_json:
        _write_json(args_cli.summary_json, replay_summary)
    print(json.dumps(replay_summary, indent=2, sort_keys=True), flush=True)
    print(f"[trace-replay] wrote Isaac-rendered replay video: {video_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
