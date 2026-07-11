"""Run a robot_contact_assembly Isaac Lab task with zero actions."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import faulthandler
import os
import sys
import traceback

import gymnasium as gym
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
        print(f"[WARN]: Ignoring SystemExit while closing {label}: {exc!r}", file=sys.stderr, flush=True)


parser = argparse.ArgumentParser(description="Zero agent for robot_contact_assembly Isaac Lab tasks.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=None, help="Override number of environments.")
parser.add_argument("--steps", type=int, default=200, help="Number of env steps to run before exit in headless mode.")
parser.add_argument("--progress_every", type=int, default=0, help="Print rollout progress every N steps; 0 disables per-step progress.")
parser.add_argument(
    "--disable_peg_sync_interval",
    action="store_true",
    default=False,
    help="Diagnostic mode: keep reset sync but prevent per-step peg sync interval events.",
)
parser.add_argument(
    "--peg_sync_interval_seconds",
    type=float,
    default=None,
    help="Override the per-step peg sync interval, if the task defines sync_peg_each_step.",
)
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-IK-Rel-Play-v0", help="Task name.")
parser.add_argument("--seed", type=int, default=42, help="Deterministic seed for smoke-test reproducibility.")
parser.add_argument(
    "--watchdog_seconds",
    type=int,
    default=int(os.environ.get("RCA_ZERO_AGENT_WATCHDOG_SECONDS", "0")),
    help="Dump Python traceback and exit if the smoke exceeds this many seconds; 0 disables.",
)
add_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
hydra_args.extend(
    [
        f"hydra.run.dir={_HYDRA_ROOT}/${{now:%Y-%m-%d}}/${{now:%H-%M-%S}}",
        "hydra.output_subdir=null",
    ]
)
sys.argv = [sys.argv[0]] + hydra_args


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


def main():
    os.makedirs(_HYDRA_ROOT, exist_ok=True)
    torch.manual_seed(args_cli.seed)

    if args_cli.watchdog_seconds > 0:
        faulthandler.enable()
        faulthandler.dump_traceback_later(args_cli.watchdog_seconds, file=sys.stderr, exit=True)

    rollout_completed = False
    try:
        with _launched_env_cfg(args_cli.task, args_cli) as env_cfg:
            env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
            env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
            if args_cli.disable_fabric:
                env_cfg.sim.use_fabric = False
            sync_event = getattr(getattr(env_cfg, "events", None), "sync_peg_each_step", None)
            if sync_event is not None:
                if args_cli.disable_peg_sync_interval:
                    sync_event.interval_range_s = (1.0e6, 1.0e6)
                    print("[INFO]: Peg sync interval disabled for diagnostics.", flush=True)
                elif args_cli.peg_sync_interval_seconds is not None:
                    sync_event.interval_range_s = (
                        args_cli.peg_sync_interval_seconds,
                        args_cli.peg_sync_interval_seconds,
                    )
                    print(
                        f"[INFO]: Peg sync interval overridden to {args_cli.peg_sync_interval_seconds:.6f}s.",
                        flush=True,
                    )
                print(f"[INFO]: Peg sync interval_range_s={sync_event.interval_range_s}.", flush=True)

            env = gym.make(args_cli.task, cfg=env_cfg)
            try:
                print(f"[INFO]: Gym observation space: {env.observation_space}", flush=True)
                print(f"[INFO]: Gym action space: {env.action_space}", flush=True)
                print("[INFO]: Resetting environment...", flush=True)
                env.reset()
                print("[INFO]: Environment reset completed.", flush=True)

                sim = env.unwrapped.sim
                visualizers = getattr(sim, "visualizers", None)
                actions = torch.zeros(env.action_space.shape, device=env.unwrapped.device)
                for step_idx in range(args_cli.steps):
                    step_number = step_idx + 1
                    if visualizers and not any(v.is_running() and not v.is_closed for v in visualizers):
                        print("[INFO]: Visualizer closed; ending zero-agent rollout.", flush=True)
                        break
                    if args_cli.progress_every > 0 and step_number % args_cli.progress_every == 0:
                        print(f"[INFO]: Zero-agent step {step_number}/{args_cli.steps} begin.", flush=True)
                    with torch.inference_mode():
                        env.step(actions)
                    if args_cli.progress_every > 0 and step_number % args_cli.progress_every == 0:
                        print(f"[INFO]: Zero-agent step {step_number}/{args_cli.steps} completed.", flush=True)
                rollout_completed = True
            except BaseException as exc:
                print(
                    f"[ERROR]: Zero-agent rollout aborted before completion: {type(exc).__name__}: {exc!r}",
                    file=sys.stderr,
                    flush=True,
                )
                traceback.print_exc(file=sys.stderr)
                raise RuntimeError("zero-agent rollout aborted before completion") from exc
            finally:
                _close_ignoring_system_exit(env.close, "environment")
            print(f"[INFO]: Zero agent smoke test completed with seed={args_cli.seed}.", flush=True)
    finally:
        if args_cli.watchdog_seconds > 0:
            faulthandler.cancel_dump_traceback_later()

    if not rollout_completed:
        raise RuntimeError("zero-agent rollout did not reach completion marker")


if __name__ == "__main__":
    main()
