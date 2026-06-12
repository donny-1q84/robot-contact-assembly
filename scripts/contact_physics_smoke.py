"""Contact-physics smoke test: prove peg/socket-wall collision response is real.

This is the gate required by the 2026-06-11 contact physics validity audit.
It must pass before any paid controller/BC/RL run:

1. attach:   after reset+settle, the peg tracks the hand through the fixed
             joint (per-env, so cloned joints are wired to their own robot).
2. free:     hovering above the wall, the wall-filtered contact force is ~0.
3. press:    commanding the peg 20mm below the wall top must produce a
             sustained wall reaction force, and the peg must be BLOCKED near
             the wall-top plane instead of passing through.
4. no-clip:  geometric penetration of the peg into the wall stays small.
5. release:  retreating removes the wall force and the joint still holds.

Any FAIL marker or nonzero exit means contact physics is still invalid.
"""

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


def _close_ignoring_system_exit(close_fn, label: str) -> None:
    try:
        close_fn()
    except SystemExit as exc:
        print(f"[WARN]: Ignoring SystemExit while closing {label}: {exc!r}", file=sys.stderr, flush=True)


parser = argparse.ArgumentParser(description="Contact-physics smoke test for the RCA peg-in-hole task.")
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-IK-Abs-Contact-Play-v0", help="Task name.")
parser.add_argument("--num_envs", type=int, default=2, help="Use >=2 to catch cross-env joint wiring failures.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--settle_steps", type=int, default=50)
parser.add_argument("--press_steps", type=int, default=220)
parser.add_argument("--retreat_steps", type=int, default=80)
parser.add_argument("--free_force_max", type=float, default=0.05, help="Max wall force (N) allowed in free space.")
parser.add_argument("--press_force_min", type=float, default=0.5, help="Min sustained wall force (N) while pressing.")
parser.add_argument("--block_tolerance_m", type=float, default=0.008,
                    help="How far below the wall-top plane the peg end may sink while pressing.")
parser.add_argument("--attach_tolerance_m", type=float, default=0.008,
                    help="Max hand-to-peg transform error for the fixed joint.")
parser.add_argument(
    "--watchdog_seconds",
    type=int,
    default=int(os.environ.get("RCA_CONTACT_SMOKE_WATCHDOG_SECONDS", "0")),
    help="Dump traceback and exit if the smoke exceeds this many seconds; 0 disables.",
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

_FAILURES: list[str] = []


def _check(name: str, passed: bool, detail: str) -> None:
    if passed:
        print(f"[INFO]: CONTACT-SMOKE {name}: PASS ({detail})", flush=True)
    else:
        _FAILURES.append(name)
        print(f"[ERROR]: CONTACT-SMOKE {name}: FAIL ({detail})", flush=True)


# --- calibrated XYZW quaternion helpers (repo convention) ---


def _quat_conjugate(q: torch.Tensor) -> torch.Tensor:
    return torch.cat((-q[..., :3], q[..., 3:]), dim=-1)


def _quat_multiply(lhs: torch.Tensor, rhs: torch.Tensor) -> torch.Tensor:
    x1, y1, z1, w1 = lhs.unbind(dim=-1)
    x2, y2, z2, w2 = rhs.unbind(dim=-1)
    return torch.stack(
        (
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        ),
        dim=-1,
    )


def _rotate_vector(q: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    zeros = torch.zeros_like(v[..., :1])
    vq = torch.cat((v, zeros), dim=-1)
    return _quat_multiply(_quat_multiply(q, vq), _quat_conjugate(q))[..., :3]


def _rotate_vector_inverse(q: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    zeros = torch.zeros_like(v[..., :1])
    vq = torch.cat((v, zeros), dim=-1)
    return _quat_multiply(_quat_multiply(_quat_conjugate(q), vq), q)[..., :3]


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


def _wall_force(scene) -> torch.Tensor:
    """Per-env wall-filtered contact force magnitude on the peg, shape (N,)."""

    sensor = scene["peg_contact"]
    forces = sensor.data.force_matrix_w
    if forces is None:
        raise RuntimeError("peg_contact sensor has no force_matrix_w; filter_prim_paths_expr is not active")
    if not isinstance(forces, torch.Tensor):
        import warp as wp

        forces = wp.to_torch(forces)
    if forces.ndim > 2:
        forces = forces.sum(dim=tuple(range(1, forces.ndim - 1)))
    return torch.linalg.norm(forces, dim=-1)


def _attach_error_m(scene, root_from_hand_pos: torch.Tensor) -> torch.Tensor:
    """Per-env |peg_root - (hand ⊗ offset)|, shape (N,)."""

    robot = scene["robot"]
    peg = scene["peg"]
    hand_idx = robot.body_names.index("panda_hand")
    hand_pos = robot.data.body_pos_w[:, hand_idx]
    hand_quat = robot.data.body_quat_w[:, hand_idx]
    expected = hand_pos + _rotate_vector(hand_quat, root_from_hand_pos.expand_as(hand_pos))
    return torch.linalg.norm(peg.data.root_pos_w - expected, dim=-1)


def main():
    os.makedirs(_HYDRA_ROOT, exist_ok=True)
    torch.manual_seed(args_cli.seed)

    if args_cli.watchdog_seconds > 0:
        faulthandler.enable()
        faulthandler.dump_traceback_later(args_cli.watchdog_seconds, file=sys.stderr, exit=True)

    try:
        with _launched_env_cfg(args_cli.task, args_cli) as env_cfg:
            env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
            env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
            if args_cli.disable_fabric:
                env_cfg.sim.use_fabric = False
            # The play cfg's 8s episode (240 env steps) is shorter than the
            # settle+press+retreat sequence; a mid-smoke timeout reset would
            # teleport the arm and invalidate the phase logic.
            env_cfg.episode_length_s = max(float(getattr(env_cfg, "episode_length_s", 0.0)), 60.0)

            env = gym.make(args_cli.task, cfg=env_cfg)
            try:
                run_smoke(env)
            finally:
                _close_ignoring_system_exit(env.close, "environment")
    finally:
        if args_cli.watchdog_seconds > 0:
            faulthandler.cancel_dump_traceback_later()

    if _FAILURES:
        print(f"[ERROR]: Contact physics smoke FAILED checks: {', '.join(_FAILURES)}", flush=True)
        raise SystemExit(1)
    print("[INFO]: Contact physics smoke completed: all checks passed.", flush=True)


def run_smoke(env) -> None:
    from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
        PEG_CENTER_BODY_OFFSET_POS,
        PEG_LENGTH_M,
        PEG_TIP_BODY_OFFSET_POS,
        PEG_TIP_BODY_OFFSET_ROT,
        SOCKET_GUIDE_DEPTH_M,
        SOCKET_GUIDE_INNER_HALF_WIDTH_M,
        SOCKET_GUIDE_WALL_THICKNESS_M,
    )

    env.reset()
    print("[INFO]: Environment reset completed.", flush=True)

    env_unwrapped = env.unwrapped
    scene = env_unwrapped.scene
    device = env_unwrapped.device
    robot = scene["robot"]
    peg = scene["peg"]
    socket = scene["socket_frame"]
    hand_idx = robot.body_names.index("panda_hand")

    root_from_hand_pos = torch.tensor(PEG_CENTER_BODY_OFFSET_POS, device=device, dtype=torch.float32)
    tip_offset = torch.tensor(PEG_TIP_BODY_OFFSET_POS, device=device, dtype=torch.float32)
    tip_rot_offset = torch.tensor(PEG_TIP_BODY_OFFSET_ROT, device=device, dtype=torch.float32)

    def tip_pose_w():
        hand_pos = robot.data.body_pos_w[:, hand_idx]
        hand_quat = robot.data.body_quat_w[:, hand_idx]
        tip_pos = hand_pos + _rotate_vector(hand_quat, tip_offset.expand_as(hand_pos))
        tip_quat = _quat_multiply(hand_quat, tip_rot_offset.expand_as(hand_quat))
        return tip_pos, tip_quat

    def action_for(tip_target_pos_w: torch.Tensor, tip_quat_w: torch.Tensor) -> torch.Tensor:
        """Convert a world tip pose target into the root-frame 7D abs IK action."""

        root_pos = robot.data.root_pos_w
        root_quat = robot.data.root_quat_w
        rel_pos = _rotate_vector_inverse(root_quat, tip_target_pos_w - root_pos)
        rel_quat = _quat_multiply(_quat_conjugate(root_quat), tip_quat_w)
        return torch.cat((rel_pos, rel_quat), dim=-1)

    def step_hold(tip_target_pos_w, tip_quat_w, steps, collect_last=30):
        forces = []
        for i in range(steps):
            with torch.inference_mode():
                env.step(action_for(tip_target_pos_w, tip_quat_w))
            if i >= steps - collect_last:
                forces.append(_wall_force(scene))
        return torch.stack(forces) if forces else torch.zeros((1, robot.num_instances), device=device)

    # Geometry: press straight down onto the TOP of the right guide wall.
    socket_pos = socket.data.root_pos_w  # (N, 3)
    wall_top_z = socket_pos[:, 2] + 0.5 * SOCKET_GUIDE_DEPTH_M
    wall_center_offset = SOCKET_GUIDE_INNER_HALF_WIDTH_M + 0.5 * SOCKET_GUIDE_WALL_THICKNESS_M
    press_xy = socket_pos[:, :2].clone()
    press_xy[:, 0] += wall_center_offset

    # The logged tip frame is the gripped UPPER end of the peg; the inserting
    # end is one peg length farther along the (downward) peg axis. With the
    # hand vertical, lower_end_z = tip_z - PEG_LENGTH_M.
    hover_clearance = 0.020
    press_depth = 0.020

    _, tip_quat0 = tip_pose_w()
    tip_quat0 = tip_quat0.clone()

    # Phase 1: settle at a free-space hover above the wall top.
    hover_target = torch.zeros_like(socket_pos)
    hover_target[:, :2] = press_xy
    hover_target[:, 2] = wall_top_z + hover_clearance + PEG_LENGTH_M
    forces = step_hold(hover_target, tip_quat0, args_cli.settle_steps, collect_last=10)
    attach_err = _attach_error_m(scene, root_from_hand_pos)
    _check(
        "attach",
        bool((attach_err < args_cli.attach_tolerance_m).all()),
        f"per-env hand-peg error {attach_err.tolist()} m, tolerance {args_cli.attach_tolerance_m}",
    )
    free_force = forces.mean(dim=0)
    _check(
        "free-space",
        bool((free_force < args_cli.free_force_max).all()),
        f"mean wall force {free_force.tolist()} N over last 10 settle steps, max {args_cli.free_force_max}",
    )

    # Phase 2: command the inserting end 20mm BELOW the wall top.
    press_target = hover_target.clone()
    press_target[:, 2] = wall_top_z - press_depth + PEG_LENGTH_M
    forces = step_hold(press_target, tip_quat0, args_cli.press_steps, collect_last=30)
    press_force = forces.mean(dim=0)
    _check(
        "press-force",
        bool((press_force > args_cli.press_force_min).all()),
        f"mean wall force {press_force.tolist()} N over last 30 press steps, min {args_cli.press_force_min}",
    )

    # Blocked: the lower end must stay near the wall-top plane, far above the
    # commanded -20mm. Use the physical peg body, not the commanded frame.
    peg_quat = peg.data.root_quat_w
    axis = _rotate_vector(peg_quat, torch.tensor([0.0, 0.0, 1.0], device=device).expand(peg_quat.shape[0], 3))
    axis = torch.where(axis[:, 2:3] > 0, -axis, axis)  # inserting end points down
    lower_end = peg.data.root_pos_w + 0.5 * PEG_LENGTH_M * axis
    sink = wall_top_z - lower_end[:, 2]
    _check(
        "press-blocked",
        bool((sink < args_cli.block_tolerance_m).all()),
        f"lower end sank {sink.tolist()} m below wall top vs commanded {press_depth} m, "
        f"tolerance {args_cli.block_tolerance_m}",
    )
    lateral_slip = torch.linalg.norm(lower_end[:, :2] - press_xy, dim=-1)
    print(f"[INFO]: CONTACT-SMOKE press lateral slip {lateral_slip.tolist()} m (informational)", flush=True)

    # Phase 3: retreat and confirm release + joint integrity.
    forces = step_hold(hover_target, tip_quat0, args_cli.retreat_steps, collect_last=10)
    release_force = forces.mean(dim=0)
    _check(
        "release",
        bool((release_force < args_cli.free_force_max).all()),
        f"mean wall force {release_force.tolist()} N after retreat, max {args_cli.free_force_max}",
    )
    attach_err = _attach_error_m(scene, root_from_hand_pos)
    _check(
        "joint-integrity",
        bool((attach_err < args_cli.attach_tolerance_m).all()),
        f"per-env hand-peg error {attach_err.tolist()} m after contact, tolerance {args_cli.attach_tolerance_m}",
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc(file=sys.stderr)
        raise
