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
if args_cli.video:
    args_cli.enable_cameras = True
sys.argv = [sys.argv[0]] + hydra_args

import robot_contact_assembly_tasks.tasks  # noqa: F401,E402

import gymnasium as gym
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
from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import PEG_TIP_BODY_OFFSET_POS


def main() -> None:
    os.makedirs("/workspace/artifacts/hydra", exist_ok=True)
    env_cfg, agent_cfg = resolve_task_config(args_cli.task, args_cli.agent)
    installed_version = metadata.version("rsl-rl-lib")
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

        env = gym.make(args_cli.task, cfg=env_cfg, render_mode="rgb_array" if args_cli.video else None)
        if isinstance(env.unwrapped.cfg, DirectMARLEnvCfg):
            from isaaclab.envs import multi_agent_to_single_agent

            env = multi_agent_to_single_agent(env)

        if args_cli.video:
            video_kwargs = {
                "video_folder": os.path.join(log_dir, "videos", "eval"),
                "step_trigger": lambda step: step == 0,
                "video_length": min(args_cli.video_length, args_cli.steps),
                "disable_logger": True,
            }
            print("[INFO] Recording evaluation video.")
            print_dict(video_kwargs, nesting=4)
            env = gym.wrappers.RecordVideo(env, **video_kwargs)

        env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)

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
        robot = env.unwrapped.scene["robot"]
        body_ids, _ = robot.find_bodies("panda_hand")
        asset_cfg = SceneEntityCfg("robot", body_names=["panda_hand"])
        asset_cfg.body_ids = [body_ids[0]]

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

            lateral, axial, rot = mdp.insertion_metrics(
                env.unwrapped,
                command_name="socket_pose",
                asset_cfg=asset_cfg,
                body_offset=PEG_TIP_BODY_OFFSET_POS,
            )
            success = mdp.insertion_success(
                env.unwrapped,
                command_name="socket_pose",
                asset_cfg=asset_cfg,
                body_offset=PEG_TIP_BODY_OFFSET_POS,
            )
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

        env.close()


if __name__ == "__main__":
    main()
