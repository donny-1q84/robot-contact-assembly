"""Run a fixed-step evaluation loop for an RSL-RL checkpoint on the peg-in-hole task."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import os
import sys
from pathlib import Path

ISAACLAB_RSL_RL_SCRIPTS_DIR = Path("/workspace/IsaacLab/scripts/reinforcement_learning/rsl_rl")
if str(ISAACLAB_RSL_RL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(ISAACLAB_RSL_RL_SCRIPTS_DIR))

import cli_args  # isort: skip


parser = argparse.ArgumentParser(description="Evaluate an RSL-RL checkpoint on the peg-in-hole task.")
parser.add_argument("--video", action="store_true", default=False, help="Record one evaluation video.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video in steps.")
parser.add_argument(
    "--video_backend",
    type=str,
    default="camera",
    choices=("camera", "viewport"),
    help="Video recording backend. 'camera' records from an explicit RGB sensor and avoids viewport capture.",
)
parser.add_argument("--video_width", type=int, default=640, help="Recorded video width in pixels.")
parser.add_argument("--video_height", type=int, default=480, help="Recorded video height in pixels.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=None, help="Number of environments to simulate.")
parser.add_argument("--task", type=str, default=None, help="Name of the task.")
parser.add_argument(
    "--agent",
    type=str,
    default="rsl_rl_cfg_entry_point",
    help="Name of the RL agent configuration entry point.",
)
parser.add_argument("--seed", type=int, default=42, help="Seed used for the environment.")
parser.add_argument("--steps", type=int, default=400, help="Number of evaluation steps to run.")
parser.add_argument(
    "--summary-json",
    type=str,
    default=None,
    help="Optional path to write a machine-readable evaluation summary.",
)
cli_args.add_rsl_rl_args(parser)
from isaaclab_tasks.utils import add_launcher_args  # noqa: E402

add_launcher_args(parser)

args_cli, hydra_args = parser.parse_known_args()
skip_auto_enable_cameras = os.environ.get("RCA_SKIP_AUTO_ENABLE_CAMERAS", "0") == "1"
if args_cli.video and args_cli.video_backend == "viewport" and not skip_auto_enable_cameras:
    args_cli.enable_cameras = True
sys.argv = [sys.argv[0]] + hydra_args

import robot_contact_assembly_tasks.tasks  # noqa: F401,E402

import gymnasium as gym
import imageio.v2 as imageio
import numpy as np
import torch
from packaging import version
from rsl_rl.runners import DistillationRunner, OnPolicyRunner

from isaaclab.envs import DirectMARLEnvCfg
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils.assets import retrieve_file_path
from isaaclab.utils.dict import print_dict
from isaaclab_rl.rsl_rl import RslRlBaseRunnerCfg, RslRlVecEnvWrapper, handle_deprecated_rsl_rl_cfg
from isaaclab_tasks.utils import get_checkpoint_path, launch_simulation, resolve_task_config

from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole import mdp


DEBUG_CAMERA_POS_WORLD = (2.5, 2.5, 2.5)
DEBUG_CAMERA_QUAT_WORLD = (-0.27984815, -0.1159169, 0.88047623, -0.3647052)
DEBUG_CAMERA_WARMUP_STEPS = 3


def _make_debug_camera(base_env, width: int, height: int):
    import isaaclab.sim as sim_utils
    from isaaclab.sensors.camera import Camera, CameraCfg

    camera_cfg = CameraCfg(
        height=height,
        width=width,
        prim_path="/World/DebugCamera",
        update_latest_camera_pose=False,
        data_types=["rgb"],
        offset=CameraCfg.OffsetCfg(
            pos=DEBUG_CAMERA_POS_WORLD,
            rot=DEBUG_CAMERA_QUAT_WORLD,
            convention="world",
        ),
        spawn=sim_utils.PinholeCameraCfg(
            focal_length=24.0,
            focus_distance=400.0,
            horizontal_aperture=20.955,
            clipping_range=(0.1, 1.0e5),
        ),
    )
    return Camera(camera_cfg)


def _prepare_debug_camera(video_camera) -> None:
    from isaaclab.app.settings_manager import get_settings_manager

    settings = get_settings_manager()
    if not settings.get("/isaaclab/cameras_enabled"):
        settings.set_bool("/isaaclab/cameras_enabled", True)
    if not video_camera.is_initialized:
        video_camera._initialize_callback(None)
    if not video_camera.is_initialized:
        raise RuntimeError("Debug camera failed to initialize after explicit callback.")
    video_camera.reset()


def _frame_to_uint8(frame_tensor: torch.Tensor) -> np.ndarray:
    frame = frame_tensor.detach().cpu().numpy()
    if frame.shape[-1] == 4:
        frame = frame[..., :3]
    if frame.dtype == np.uint8:
        return frame
    if np.issubdtype(frame.dtype, np.floating):
        if float(np.nanmax(frame)) <= 1.0:
            frame = frame * 255.0
    return np.clip(frame, 0, 255).astype(np.uint8)


def main() -> None:
    os.makedirs("/workspace/artifacts/hydra", exist_ok=True)
    env_cfg, agent_cfg = resolve_task_config(args_cli.task, args_cli.agent)
    installed_version = metadata.version("rsl-rl-lib")
    print(
        f"[VIDEO] requested={args_cli.video} backend={args_cli.video_backend} "
        f"enable_cameras={getattr(args_cli, 'enable_cameras', False)}",
        flush=True,
    )
    with launch_simulation(env_cfg, args_cli):
        agent_cfg = cli_args.update_rsl_rl_cfg(agent_cfg, args_cli)
        env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
        env_cfg.seed = agent_cfg.seed
        env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
        agent_cfg = handle_deprecated_rsl_rl_cfg(agent_cfg, installed_version)

        log_root_path = os.path.abspath(os.path.join("logs", "rsl_rl", agent_cfg.experiment_name))
        if args_cli.checkpoint and (
            os.path.isabs(args_cli.checkpoint)
            or Path(args_cli.checkpoint).expanduser().is_file()
            or "://" in args_cli.checkpoint
        ):
            resume_path = retrieve_file_path(args_cli.checkpoint)
        else:
            if args_cli.checkpoint:
                agent_cfg.load_checkpoint = args_cli.checkpoint
            resume_path = get_checkpoint_path(log_root_path, agent_cfg.load_run, agent_cfg.load_checkpoint)
        log_dir = os.path.dirname(resume_path)
        env_cfg.log_dir = log_dir

        print("[VIDEO] creating gym environment", flush=True)
        base_env = gym.make(
            args_cli.task,
            cfg=env_cfg,
            render_mode="rgb_array" if args_cli.video and args_cli.video_backend == "viewport" else None,
        )
        print("[VIDEO] gym environment created", flush=True)
        if isinstance(base_env.unwrapped.cfg, DirectMARLEnvCfg):
            from isaaclab.envs import multi_agent_to_single_agent

            base_env = multi_agent_to_single_agent(base_env)

        video_camera = None
        video_writer = None
        video_frames_written = 0
        if args_cli.video:
            video_dir = os.path.join(log_dir, "videos", "eval")
            os.makedirs(video_dir, exist_ok=True)
            if args_cli.video_backend == "viewport":
                video_kwargs = {
                    "video_folder": video_dir,
                    "step_trigger": lambda step: step == 0,
                    "video_length": min(args_cli.video_length, args_cli.steps),
                    "disable_logger": True,
                }
                print("[INFO] Recording evaluation video with viewport backend.")
                print_dict(video_kwargs, nesting=4)
                base_env = gym.wrappers.RecordVideo(base_env, **video_kwargs)
            else:
                video_path = os.path.join(video_dir, "camera_eval.mp4")
                print("[VIDEO] creating explicit camera sensor", flush=True)
                video_camera = _make_debug_camera(base_env, width=args_cli.video_width, height=args_cli.video_height)
                _prepare_debug_camera(video_camera)
                video_writer = imageio.get_writer(video_path, fps=max(1, round(1.0 / base_env.unwrapped.step_dt)))
                print(
                    f"[INFO] Recording evaluation video with camera backend to {video_path} "
                    f"({args_cli.video_width}x{args_cli.video_height}, warmup={DEBUG_CAMERA_WARMUP_STEPS}).",
                    flush=True,
                )

        env = None
        try:
            env = RslRlVecEnvWrapper(base_env, clip_actions=agent_cfg.clip_actions)

            if agent_cfg.class_name == "OnPolicyRunner":
                runner = OnPolicyRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
            elif agent_cfg.class_name == "DistillationRunner":
                runner = DistillationRunner(env, agent_cfg.to_dict(), log_dir=None, device=agent_cfg.device)
            else:
                raise ValueError(f"Unsupported runner class: {agent_cfg.class_name}")
            runner.load(resume_path)
            policy = runner.get_inference_policy(device=env.unwrapped.device)
            policy_nn = None
            if version.parse(installed_version) < version.parse("4.0.0"):
                if version.parse(installed_version) >= version.parse("2.3.0"):
                    policy_nn = runner.alg.policy
                else:
                    policy_nn = runner.alg.actor_critic

            obs = env.get_observations()
            peg_cfg = SceneEntityCfg("peg")
            socket_cfg = SceneEntityCfg("socket_frame")

            initial_lateral = None
            initial_axial = None
            initial_rot = None
            final_lateral = None
            final_axial = None
            final_rot = None
            final_success_rate = None
            best_success_rate = 0.0
            best_lateral = None
            best_axial = None
            best_rot = None
            first_success_step = None

            for step in range(args_cli.steps):
                with torch.inference_mode():
                    actions = policy(obs)
                    obs, _, dones, _ = env.step(actions)
                    if version.parse(installed_version) >= version.parse("4.0.0"):
                        policy.reset(dones)
                    else:
                        policy_nn.reset(dones)

                if (
                    video_camera is not None
                    and step >= DEBUG_CAMERA_WARMUP_STEPS
                    and video_frames_written < args_cli.video_length
                ):
                    video_camera.update(base_env.unwrapped.step_dt, force_recompute=True)
                    frame = _frame_to_uint8(video_camera.data.output["rgb"][0])
                    video_writer.append_data(frame)
                    video_frames_written += 1

                lateral, axial, rot = mdp.insertion_metrics(env.unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)
                success = mdp.insertion_success(env.unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)
                lateral_mean = lateral.mean().item()
                axial_mean = axial.mean().item()
                rot_mean = rot.mean().item()
                success_rate = success.float().mean().item()

                if step == 0:
                    initial_lateral = lateral_mean
                    initial_axial = axial_mean
                    initial_rot = rot_mean

                if success_rate > best_success_rate:
                    best_success_rate = success_rate
                    best_lateral = lateral_mean
                    best_axial = axial_mean
                    best_rot = rot_mean

                if first_success_step is None and success.any():
                    first_success_step = step

                final_lateral = lateral_mean
                final_axial = axial_mean
                final_rot = rot_mean
                final_success_rate = success_rate

                if step % 25 == 0 or step == args_cli.steps - 1:
                    print(
                        f"[EVAL] step={step:04d} lateral={lateral_mean:.4f} axial={axial_mean:.4f} "
                        f"rot={rot_mean:.4f} success_rate={success_rate:.3f}",
                        flush=True,
                    )

            summary = {
                "task": args_cli.task,
                "seed": args_cli.seed,
                "steps": args_cli.steps,
                "num_envs": env.unwrapped.num_envs,
                "checkpoint_path": resume_path,
                "log_dir": log_dir,
                "initial_lateral": initial_lateral,
                "initial_axial": initial_axial,
                "initial_rot": initial_rot,
                "final_lateral": final_lateral,
                "final_axial": final_axial,
                "final_rot": final_rot,
                "final_success_rate": final_success_rate,
                "best_success_rate": best_success_rate,
                "best_lateral": best_lateral,
                "best_axial": best_axial,
                "best_rot": best_rot,
                "first_success_step": first_success_step,
                "video_backend": args_cli.video_backend if args_cli.video else None,
                "video_frames_written": video_frames_written if args_cli.video else 0,
            }
            print(
                "[EVAL] summary "
                f"best_success_rate={best_success_rate:.3f} "
                f"final_success_rate={final_success_rate:.3f} "
                f"final_lateral={final_lateral:.4f} "
                f"final_axial={final_axial:.4f} "
                f"final_rot={final_rot:.4f}",
                flush=True,
            )

            if args_cli.summary_json:
                summary_path = Path(args_cli.summary_json).expanduser().resolve()
                summary_path.parent.mkdir(parents=True, exist_ok=True)
                summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
                print(f"[EVAL] wrote summary to {summary_path}", flush=True)
        finally:
            if video_writer is not None:
                video_writer.close()
            if env is not None:
                env.close()


if __name__ == "__main__":
    main()
