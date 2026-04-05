import builtins
import importlib
import sys

import omni.timeline
import omni.usd
import torch

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

for prefix in ("robot_contact_assembly_tasks",):
    for module_name in list(sys.modules):
        if module_name == prefix or module_name.startswith(prefix + "."):
            del sys.modules[module_name]

importlib.invalidate_caches()

from isaaclab.envs import ManagerBasedRLEnv
from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.config.franka.ik_rel_env_cfg import (  # noqa: E402
    FrankaPegInHoleEnvCfg_PLAY,
)


STATE_KEY = "_rca_live_demo_state"
TASK_NAME = "RCA-PegInHole-Franka-IK-Rel-Play-v0"


def close_previous_env():
    previous_state = getattr(builtins, STATE_KEY, None)
    if not previous_state:
        return
    previous_env = previous_state.get("env")
    if previous_env is None:
        return
    try:
        previous_env.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[live-demo] previous env close warning: {exc}")


def main():
    close_previous_env()

    usd_context = omni.usd.get_context()
    usd_context.new_stage()

    env_cfg = FrankaPegInHoleEnvCfg_PLAY()
    env_cfg.scene.num_envs = 1
    env_cfg.scene.env_spacing = 2.5
    env_cfg.sim.device = "cpu"
    env_cfg.sim.use_fabric = False
    env_cfg.observations.policy.enable_corruption = False
    env_cfg.commands.socket_pose.debug_vis = True
    env_cfg.viewer.eye = (2.2, 1.6, 1.4)

    env = ManagerBasedRLEnv(cfg=env_cfg)
    env.reset()

    zero_action = torch.zeros(env.action_space.shape, device=env.unwrapped.device)
    for _ in range(4):
        env.step(zero_action)

    builtins._rca_live_demo_state = {
        "env": env,
        "task_name": TASK_NAME,
    }

    stage = usd_context.get_stage()
    important_paths = [
        "/World/envs/env_0/Robot",
        "/World/envs/env_0/Table",
        "/World/envs/env_0/Visuals/Command",
    ]
    for path in important_paths:
        print(f"[live-demo] {path}: {stage.GetPrimAtPath(path).IsValid()}")

    timeline = omni.timeline.get_timeline_interface()
    timeline.pause()
    print(f"[live-demo] loaded {TASK_NAME} into the current Isaac Sim app")


main()
