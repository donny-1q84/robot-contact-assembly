"""Run a robot_contact_assembly Isaac Lab task with zero actions."""

from __future__ import annotations

import argparse
import os
import sys

import gymnasium as gym
import torch

from isaaclab_tasks.utils import add_launcher_args, launch_simulation, resolve_task_config

parser = argparse.ArgumentParser(description="Zero agent for robot_contact_assembly Isaac Lab tasks.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=None, help="Override number of environments.")
parser.add_argument("--steps", type=int, default=200, help="Number of env steps to run before exit in headless mode.")
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-IK-Rel-Play-v0", help="Task name.")
parser.add_argument("--seed", type=int, default=42, help="Deterministic seed for smoke-test reproducibility.")
add_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
hydra_args.extend(
    [
        r"hydra.run.dir=/workspace/artifacts/hydra/${now:%Y-%m-%d}/${now:%H-%M-%S}",
        "hydra.output_subdir=null",
    ]
)
sys.argv = [sys.argv[0]] + hydra_args

import robot_contact_assembly_tasks.tasks  # noqa: F401


def main():
    os.makedirs("/workspace/artifacts/hydra", exist_ok=True)
    torch.manual_seed(args_cli.seed)
    env_cfg, _ = resolve_task_config(args_cli.task, "")
    env_cfg.seed = args_cli.seed

    with launch_simulation(env_cfg, args_cli):
        env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
        env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
        if args_cli.disable_fabric:
            env_cfg.sim.use_fabric = False

        env = gym.make(args_cli.task, cfg=env_cfg)
        print(f"[INFO]: Gym observation space: {env.observation_space}", flush=True)
        print(f"[INFO]: Gym action space: {env.action_space}", flush=True)
        env.reset()

        sim = env.unwrapped.sim
        actions = torch.zeros(env.action_space.shape, device=env.unwrapped.device)
        for _ in range(args_cli.steps):
            if sim.visualizers and not any(v.is_running() and not v.is_closed for v in sim.visualizers):
                break
            with torch.inference_mode():
                env.step(actions)

        env.close()
        print(f"[INFO]: Zero agent smoke test completed with seed={args_cli.seed}.", flush=True)


if __name__ == "__main__":
    main()
