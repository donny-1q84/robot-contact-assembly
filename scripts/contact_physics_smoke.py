"""Contact-physics smoke test: prove peg/socket-wall collision response is real.

This is the gate required by the 2026-06-11 contact physics validity audit.
It must pass before any paid controller/BC/RL run:

1. attach:   after reset+settle, the peg tracks the hand through the fixed
             joint (per-env, so cloned joints are wired to their own robot).
2. free:     hovering above the wall, the wall-filtered contact force is ~0.
3. press:    commanding the peg/wall contact must produce a sustained wall
             reaction force, and the blocked relation must match the chosen
             press mechanism instead of passing through.
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
parser.add_argument("--local_guide_reanchor_steps", type=int, default=10)
parser.add_argument("--free_force_max", type=float, default=0.05, help="Max wall force (N) allowed in free space.")
parser.add_argument("--press_force_min", type=float, default=0.5, help="Min sustained wall force (N) while pressing.")
parser.add_argument(
    "--contact_setup",
    choices=("local-guide", "fixed-socket"),
    default=os.environ.get("RCA_CONTACT_SMOKE_SETUP", "local-guide"),
    help=(
        "local-guide relocates the kinematic socket walls under the current insertion tip so the smoke tests "
        "contact physics, not long-range IK reachability. fixed-socket keeps the authored task socket pose."
    ),
)
parser.add_argument(
    "--press_mechanism",
    choices=("guide-wall-sweep", "arm-servo"),
    default=os.environ.get("RCA_CONTACT_SMOKE_PRESS_MECHANISM", "guide-wall-sweep"),
    help=(
        "guide-wall-sweep keeps the robot at the reanchored pose and moves the local kinematic wall into "
        "the dynamic peg, isolating peg-vs-wall contact physics. arm-servo keeps the older lower-end IK "
        "press path as a controller reachability diagnostic."
    ),
)
parser.add_argument(
    "--press_lateral_tolerance_m",
    type=float,
    default=0.015,
    help="Max lateral error allowed between the physical lower peg end and the commanded wall-contact point.",
)
parser.add_argument(
    "--block_tolerance_m",
    type=float,
    default=0.008,
    help=(
        "Max error allowed in the blocked-contact relation. arm-servo expects the lower peg end near the "
        "wall-top plane; guide-wall-sweep expects the cylindrical lower-end centerline about one peg radius "
        "above the wall top."
    ),
)
parser.add_argument("--clip_tolerance_m", type=float, default=0.008,
                    help="Max geometric wall penetration allowed for the inserting peg end.")
parser.add_argument("--attach_tolerance_m", type=float, default=0.008,
                    help="Max hand-to-peg transform error for the fixed joint.")
parser.add_argument(
    "--reset_joint_position_scale",
    type=float,
    default=float(os.environ.get("RCA_CONTACT_SMOKE_RESET_JOINT_POSITION_SCALE", "1.0")),
    help=(
        "Deterministic reset scale used by the smoke test. The contact smoke "
        "isolates peg-vs-wall physics; random reset posture reachability is a "
        "separate controller diagnostic."
    ),
)
parser.add_argument(
    "--press_tracking_gain",
    type=float,
    default=0.6,
    help="Per-step lower-end tracking feedback gain used during the press phase.",
)
parser.add_argument(
    "--press_tracking_step_limit_m",
    type=float,
    default=0.010,
    help="Max per-step correction applied to the action-frame target during press tracking.",
)
parser.add_argument(
    "--exclude_peg_from_articulation",
    action="store_true",
    default=os.environ.get("RCA_CONTACT_SMOKE_EXCLUDE_PEG_FROM_ARTICULATION", "0") == "1",
    help="Legacy diagnostic only: keep the peg as a maximal-coordinate rigid body outside the Franka articulation.",
)
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
_SUCCESS_MARKER_EMITTED = False


def _check(name: str, passed: bool, detail: str) -> None:
    if passed:
        print(f"[INFO]: CONTACT-SMOKE {name}: PASS ({detail})", flush=True)
    else:
        _FAILURES.append(name)
        print(f"[ERROR]: CONTACT-SMOKE {name}: FAIL ({detail})", flush=True)


def _emit_success_marker_if_ready() -> None:
    """Emit the success marker before Isaac teardown can interrupt process exit."""

    global _SUCCESS_MARKER_EMITTED
    if _FAILURES or _SUCCESS_MARKER_EMITTED:
        return
    print("[INFO]: Contact physics smoke completed: all checks passed.", flush=True)
    _SUCCESS_MARKER_EMITTED = True


# --- Isaac Lab WXYZ quaternion helpers ---


def _quat_conjugate(q: torch.Tensor) -> torch.Tensor:
    return torch.cat((q[..., :1], -q[..., 1:]), dim=-1)


def _quat_multiply(lhs: torch.Tensor, rhs: torch.Tensor) -> torch.Tensor:
    w1, x1, y1, z1 = lhs.unbind(dim=-1)
    w2, x2, y2, z2 = rhs.unbind(dim=-1)
    return torch.stack(
        (
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ),
        dim=-1,
    )


def _rotate_vector(q: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    zeros = torch.zeros_like(v[..., :1])
    vq = torch.cat((zeros, v), dim=-1)
    return _quat_multiply(_quat_multiply(q, vq), _quat_conjugate(q))[..., 1:]


def _rotate_vector_inverse(q: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    zeros = torch.zeros_like(v[..., :1])
    vq = torch.cat((zeros, v), dim=-1)
    return _quat_multiply(_quat_multiply(_quat_conjugate(q), vq), q)[..., 1:]


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


def _expected_peg_root_from_hand(
    scene,
    root_from_hand_pos: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Expected peg root from the calibrated fixed hand offset."""

    robot = scene["robot"]
    hand_idx = robot.body_names.index("panda_hand")
    hand_pos = robot.data.body_pos_w[:, hand_idx]
    hand_quat = robot.data.body_quat_w[:, hand_idx]
    expected = hand_pos + _rotate_vector(hand_quat, root_from_hand_pos.expand_as(hand_pos))
    return expected, hand_pos, hand_quat


def _scene_entity_or_none(scene, name: str):
    try:
        return scene[name]
    except (KeyError, ValueError, RuntimeError):
        return None


def _peg_pose_w_for_smoke(
    scene,
    root_from_hand_pos: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, str]:
    """Best available peg root pose for diagnostics and blocked-motion checks."""

    robot = scene["robot"]
    for body_name in ("Peg", "peg"):
        if body_name in robot.body_names:
            body_idx = robot.body_names.index(body_name)
            return robot.data.body_pos_w[:, body_idx], robot.data.body_quat_w[:, body_idx], f"robot-body:{body_name}"

    peg = _scene_entity_or_none(scene, "peg")
    if peg is not None and hasattr(peg, "data"):
        return peg.data.root_pos_w, peg.data.root_quat_w, "scene-rigidobject:peg"

    expected, _, hand_quat = _expected_peg_root_from_hand(scene, root_from_hand_pos)
    return expected, hand_quat, "derived-hand-offset"


def _attach_expected_delta(
    scene,
    root_from_hand_pos: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, str]:
    """Per-env expected peg root and delta from the fixed hand offset."""

    expected, hand_pos, hand_quat = _expected_peg_root_from_hand(scene, root_from_hand_pos)
    peg_pos, _, source = _peg_pose_w_for_smoke(scene, root_from_hand_pos)
    delta = peg_pos - expected
    actual_local = _rotate_vector_inverse(hand_quat, peg_pos - hand_pos)
    error = torch.linalg.norm(delta, dim=-1)
    return error, delta, actual_local, expected, hand_pos, peg_pos, source


def _attach_error_m(scene, root_from_hand_pos: torch.Tensor) -> torch.Tensor:
    """Per-env |peg_root - (hand ⊗ offset)|, shape (N,)."""

    error, _, _, _, _, _, _ = _attach_expected_delta(scene, root_from_hand_pos)
    return error


def _small_list(tensor: torch.Tensor, max_envs: int = 4) -> list:
    return tensor[:max_envs].detach().cpu().tolist()


def _normal_tensor(tensor: torch.Tensor) -> torch.Tensor:
    """Copy Isaac/PyTorch inference tensors into a normal tensor for mutation/writes."""

    out = torch.empty(tensor.shape, device=tensor.device, dtype=tensor.dtype)
    out.copy_(tensor)
    return out


def _limit_vector_norm(delta: torch.Tensor, max_norm: float) -> torch.Tensor:
    """Limit each per-env vector correction without changing its direction."""

    if max_norm <= 0.0:
        return torch.zeros_like(delta)
    norm = torch.linalg.norm(delta, dim=-1, keepdim=True)
    scale = torch.clamp(max_norm / torch.clamp(norm, min=1e-9), max=1.0)
    return delta * scale


def _limit_scalar(delta: torch.Tensor, max_abs: float) -> torch.Tensor:
    """Clamp a scalar per-env correction while preserving sign."""

    if max_abs <= 0.0:
        return torch.zeros_like(delta)
    return torch.clamp(delta, min=-max_abs, max=max_abs)


def _print_attach_diagnostics(scene, root_from_hand_pos: torch.Tensor, label: str) -> None:
    error, delta, actual_local, expected, hand_pos, peg_pos, source = _attach_expected_delta(
        scene, root_from_hand_pos
    )
    print(
        f"[INFO]: CONTACT-SMOKE attach-diagnostic {label}: "
        f"peg_pose_source={source} "
        f"err_m={_small_list(error)} "
        f"delta_xyz={_small_list(delta)} "
        f"actual_root_from_hand_local={_small_list(actual_local)} "
        f"expected_root_from_hand_local={_small_list(root_from_hand_pos)} "
        f"expected_peg_root={_small_list(expected)} "
        f"hand_pos={_small_list(hand_pos)} "
        f"peg_pos={_small_list(peg_pos)}",
        flush=True,
    )


def _print_usd_joint_diagnostics(scene) -> None:
    """Log fixed-joint authored state without making it part of pass/fail."""

    try:
        import omni.usd
        from pxr import UsdPhysics
    except Exception as exc:  # pragma: no cover - Isaac runtime only
        print(f"[WARN]: CONTACT-SMOKE joint-diagnostic unavailable: {exc}", flush=True)
        return

    stage = omni.usd.get_context().get_stage()
    if stage is None:
        print("[WARN]: CONTACT-SMOKE joint-diagnostic unavailable: no USD stage", flush=True)
        return

    robot = scene["robot"]
    max_envs = min(int(robot.num_instances), 4)

    def _rel_targets(joint, getter_name: str) -> list[str] | str:
        getter = getattr(joint, getter_name, None)
        if getter is None:
            return "<unavailable>"
        rel = getter()
        return [str(path) for path in rel.GetTargets()]

    def _attr_value(joint, getter_name: str):
        getter = getattr(joint, getter_name, None)
        if getter is None:
            return "<unavailable>"
        attr = getter()
        return attr.Get() if attr else None

    for env_idx in range(max_envs):
        joint_path = f"/World/envs/env_{env_idx}/Peg/PegHandFixedJoint"
        prim = stage.GetPrimAtPath(joint_path)
        if not prim.IsValid():
            print(f"[INFO]: CONTACT-SMOKE joint-diagnostic env={env_idx}: missing {joint_path}", flush=True)
            continue
        joint = UsdPhysics.FixedJoint(prim)
        body0 = _rel_targets(joint, "GetBody0Rel")
        body1 = _rel_targets(joint, "GetBody1Rel")
        local_pos0 = _attr_value(joint, "GetLocalPos0Attr")
        local_rot0 = _attr_value(joint, "GetLocalRot0Attr")
        local_pos1 = _attr_value(joint, "GetLocalPos1Attr")
        local_rot1 = _attr_value(joint, "GetLocalRot1Attr")
        exclude = _attr_value(joint, "GetExcludeFromArticulationAttr")
        print(
            f"[INFO]: CONTACT-SMOKE joint-diagnostic env={env_idx}: "
            f"path={joint_path} body0={body0} body1={body1} "
            f"localPos0={local_pos0} localRot0={local_rot0} "
            f"localPos1={local_pos1} localRot1={local_rot1} "
            f"excludeFromArticulation={exclude}",
            flush=True,
        )


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
            reset_event = getattr(getattr(env_cfg, "events", None), "reset_robot_joints", None)
            reset_params = getattr(reset_event, "params", None)
            if isinstance(reset_params, dict):
                old_position_range = reset_params.get("position_range")
                old_velocity_range = reset_params.get("velocity_range")
                reset_scale = float(args_cli.reset_joint_position_scale)
                reset_params["position_range"] = (reset_scale, reset_scale)
                reset_params["velocity_range"] = (0.0, 0.0)
                print(
                    "[INFO]: CONTACT-SMOKE reset-joints: deterministic "
                    f"(old_position_range={old_position_range}, "
                    f"new_position_range={reset_params['position_range']}, "
                    f"old_velocity_range={old_velocity_range}, "
                    f"new_velocity_range={reset_params['velocity_range']})",
                    flush=True,
                )
            else:
                print(
                    "[WARN]: CONTACT-SMOKE reset-joints: deterministic reset unavailable "
                    "(reset_robot_joints params missing)",
                    flush=True,
                )
            # The play cfg's 8s episode (240 env steps) is shorter than the
            # settle+press+retreat sequence; a mid-smoke timeout reset would
            # teleport the arm and invalidate the phase logic.
            env_cfg.episode_length_s = max(float(getattr(env_cfg, "episode_length_s", 0.0)), 60.0)
            peg_cfg = getattr(env_cfg.scene, "peg", None)
            peg_spawn = getattr(peg_cfg, "spawn", None)
            if hasattr(peg_spawn, "exclude_from_articulation"):
                peg_spawn.exclude_from_articulation = bool(args_cli.exclude_peg_from_articulation)
                print(
                    "[INFO]: CONTACT-SMOKE peg-articulation-model "
                    f"exclude_from_articulation={peg_spawn.exclude_from_articulation}",
                    flush=True,
                )
            else:
                print(
                    "[WARN]: CONTACT-SMOKE peg-articulation-model unavailable: "
                    "peg spawn has no exclude_from_articulation field",
                    flush=True,
                )

            env = gym.make(args_cli.task, cfg=env_cfg)
            try:
                run_smoke(env)
                _emit_success_marker_if_ready()
            finally:
                _close_ignoring_system_exit(env.close, "environment")
    finally:
        if args_cli.watchdog_seconds > 0:
            faulthandler.cancel_dump_traceback_later()

    if _FAILURES:
        print(f"[ERROR]: Contact physics smoke FAILED checks: {', '.join(_FAILURES)}", flush=True)
        raise SystemExit(1)
    _emit_success_marker_if_ready()


def run_smoke(env) -> None:
    from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
        IDENTITY_QUAT,
        PEG_CENTER_BODY_OFFSET_POS,
        PEG_LENGTH_M,
        PEG_RADIUS_M,
        PEG_TIP_BODY_OFFSET_POS,
        PEG_TIP_BODY_OFFSET_ROT,
        SOCKET_FRAME_ROT,
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
    socket = scene["socket_frame"]
    hand_idx = robot.body_names.index("panda_hand")
    completed_phases: list[str] = []
    last_phase = "reset"

    root_from_hand_pos = torch.tensor(PEG_CENTER_BODY_OFFSET_POS, device=device, dtype=torch.float32)
    tip_offset = torch.tensor(PEG_TIP_BODY_OFFSET_POS, device=device, dtype=torch.float32)
    tip_rot_offset = torch.tensor(PEG_TIP_BODY_OFFSET_ROT, device=device, dtype=torch.float32)

    _print_usd_joint_diagnostics(scene)
    _print_attach_diagnostics(scene, root_from_hand_pos, "after-reset")

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

    def lower_end_pose_w():
        peg_pos, peg_quat, peg_pose_source = _peg_pose_w_for_smoke(scene, root_from_hand_pos)
        axis = _rotate_vector(peg_quat, torch.tensor([0.0, 0.0, 1.0], device=device).expand(peg_quat.shape[0], 3))
        axis = torch.where(axis[:, 2:3] > 0, -axis, axis)  # inserting end points down
        return peg_pos + 0.5 * PEG_LENGTH_M * axis, peg_pos, peg_quat, peg_pose_source

    def write_kinematic_root_pose(name: str, pos_w: torch.Tensor, quat_w: torch.Tensor) -> None:
        asset = scene[name]
        pos_w = _normal_tensor(pos_w)
        quat_w = _normal_tensor(quat_w)
        with torch.inference_mode():
            asset.write_root_pose_to_sim(torch.cat((pos_w, quat_w), dim=-1))
            if hasattr(asset, "write_root_velocity_to_sim"):
                asset.write_root_velocity_to_sim(torch.zeros((pos_w.shape[0], 6), device=device, dtype=pos_w.dtype))

    def write_socket_guide_at_socket_pos(socket_pos_w: torch.Tensor, wall_center_offset: float) -> torch.Tensor:
        """Move the socket frame and all four kinematic guide walls together."""

        socket_pos_w = _normal_tensor(socket_pos_w)
        socket_quat = torch.tensor(SOCKET_FRAME_ROT, device=device, dtype=torch.float32).repeat(socket_pos_w.shape[0], 1)
        wall_quat = torch.tensor(IDENTITY_QUAT, device=device, dtype=torch.float32).repeat(socket_pos_w.shape[0], 1)
        wall_offset = wall_center_offset

        write_kinematic_root_pose("socket_frame", socket_pos_w, socket_quat)
        write_kinematic_root_pose(
            "socket_wall_left",
            socket_pos_w + torch.tensor([-wall_offset, 0.0, 0.0], device=device, dtype=torch.float32),
            wall_quat,
        )
        write_kinematic_root_pose(
            "socket_wall_right",
            socket_pos_w + torch.tensor([wall_offset, 0.0, 0.0], device=device, dtype=torch.float32),
            wall_quat,
        )
        write_kinematic_root_pose(
            "socket_wall_front",
            socket_pos_w + torch.tensor([0.0, -wall_offset, 0.0], device=device, dtype=torch.float32),
            wall_quat,
        )
        write_kinematic_root_pose(
            "socket_wall_back",
            socket_pos_w + torch.tensor([0.0, wall_offset, 0.0], device=device, dtype=torch.float32),
            wall_quat,
        )
        return socket_pos_w

    def move_socket_guide_for_local_contact(
        lower_end_w: torch.Tensor,
        wall_center_offset: float,
        hover_clearance: float,
    ) -> torch.Tensor:
        """Place the right guide-wall top directly below the current inserting end."""

        socket_pos_w = _normal_tensor(lower_end_w)
        offset = torch.tensor(
            [-wall_center_offset, 0.0, -(hover_clearance + 0.5 * SOCKET_GUIDE_DEPTH_M)],
            device=device,
            dtype=socket_pos_w.dtype,
        )
        socket_pos_w = socket_pos_w + offset
        return write_socket_guide_at_socket_pos(socket_pos_w, wall_center_offset)

    def wall_targets_from_socket(socket_pos_w: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        wall_top_z_w = socket_pos_w[:, 2] + 0.5 * SOCKET_GUIDE_DEPTH_M
        press_x_w = socket_pos_w[:, 0] + wall_center_offset
        press_y_w = socket_pos_w[:, 1]
        press_xy_w = torch.stack((press_x_w, press_y_w), dim=-1)
        hover_target_w = torch.stack(
            (press_x_w, press_y_w, wall_top_z_w + hover_clearance),
            dim=-1,
        )
        return wall_top_z_w, press_xy_w, hover_target_w

    def step_hold(tip_target_pos_w, tip_quat_w, steps, collect_last=30, phase_label: str | None = None):
        nonlocal last_phase
        if phase_label is not None:
            last_phase = phase_label
            print(
                f"[INFO]: CONTACT-SMOKE phase {phase_label}: begin "
                f"(steps={steps}, collect_last={collect_last})",
                flush=True,
            )
        forces = []
        for i in range(steps):
            with torch.inference_mode():
                env.step(action_for(tip_target_pos_w, tip_quat_w))
            if phase_label is not None and (
                i == 0 or i + 1 == steps or (i + 1) % 50 == 0
            ):
                print(
                    f"[INFO]: CONTACT-SMOKE phase {phase_label}: progress {i + 1}/{steps}",
                    flush=True,
                )
            if i >= steps - collect_last:
                forces.append(_wall_force(scene))
        if phase_label is not None:
            completed_phases.append(phase_label)
            print(f"[INFO]: CONTACT-SMOKE phase {phase_label}: end", flush=True)
        return torch.stack(forces) if forces else torch.zeros((1, robot.num_instances), device=device)

    def step_track_lower_end(
        desired_lower_end_w: torch.Tensor,
        tip_quat_w: torch.Tensor,
        steps: int,
        collect_last: int = 30,
        phase_label: str | None = None,
        control_label: str = "press-control",
        axis_mode: str = "z-only-lateral-locked",
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Servo the physical lower peg end with bounded current-tip corrections.

        The smoke is validating peg-vs-wall contact, not one-shot absolute-IK
        tracking. Keep the action-frame lateral anchor fixed by default and
        only correct along world Z; the pass/fail tracking checks still use the
        physical peg lower end, so lateral IK branch drift remains visible
        without feeding that drift back into the command.
        """

        nonlocal last_phase
        if phase_label is not None:
            last_phase = phase_label
            print(
                f"[INFO]: CONTACT-SMOKE phase {phase_label}: begin "
                f"(steps={steps}, collect_last={collect_last})",
                flush=True,
            )

        desired_lower_end_w = _normal_tensor(desired_lower_end_w)
        tip_quat_w = _normal_tensor(tip_quat_w)
        tip_now, _ = tip_pose_w()
        tip_now = _normal_tensor(tip_now)
        lateral_anchor_tip_w = tip_now[:, :2].clone()
        last_tip_target_pos_w = _normal_tensor(tip_now)
        # Retained for the diagnostic arm-servo mode; the default contact
        # physics gate now uses CONTACT-SMOKE press-control: local-wall-sweep.
        print(
            f"[INFO]: CONTACT-SMOKE {control_label}: lower-end closed-loop "
            f"(gain={args_cli.press_tracking_gain}, "
            f"step_limit_m={args_cli.press_tracking_step_limit_m}, "
            f"axis_mode={axis_mode}, "
            f"desired_lower_end={_small_list(desired_lower_end_w)}, "
            f"initial_tip={_small_list(last_tip_target_pos_w)}, "
            f"lateral_anchor_tip={_small_list(lateral_anchor_tip_w)})",
            flush=True,
        )

        forces = []
        last_error = torch.zeros_like(desired_lower_end_w)
        last_correction = torch.zeros_like(desired_lower_end_w)
        for i in range(steps):
            lower_end_now, _, _, _ = lower_end_pose_w()
            tip_now, _ = tip_pose_w()
            lower_end_now = _normal_tensor(lower_end_now)
            tip_now = _normal_tensor(tip_now)
            last_error = desired_lower_end_w - lower_end_now
            if axis_mode == "z-only-lateral-locked":
                last_correction = torch.zeros_like(last_error)
                last_correction[:, 2] = _limit_scalar(
                    last_error[:, 2] * float(args_cli.press_tracking_gain),
                    float(args_cli.press_tracking_step_limit_m),
                )
                last_tip_target_pos_w = tip_now.clone()
                last_tip_target_pos_w[:, :2] = lateral_anchor_tip_w
                last_tip_target_pos_w[:, 2] = tip_now[:, 2] + last_correction[:, 2]
            elif axis_mode == "xyz":
                last_correction = _limit_vector_norm(
                    last_error * float(args_cli.press_tracking_gain),
                    float(args_cli.press_tracking_step_limit_m),
                )
                last_tip_target_pos_w = tip_now + last_correction
            else:
                raise ValueError(f"unsupported axis_mode: {axis_mode}")

            with torch.inference_mode():
                env.step(action_for(last_tip_target_pos_w, tip_quat_w))
            if phase_label is not None and (
                i == 0 or i + 1 == steps or (i + 1) % 50 == 0
            ):
                print(
                    f"[INFO]: CONTACT-SMOKE phase {phase_label}: progress {i + 1}/{steps} "
                    f"(lower_end_error={_small_list(last_error)}, "
                    f"tip_correction={_small_list(last_correction)})",
                    flush=True,
                )
            if i >= steps - collect_last:
                forces.append(_wall_force(scene))
        if phase_label is not None:
            completed_phases.append(phase_label)
            print(f"[INFO]: CONTACT-SMOKE phase {phase_label}: end", flush=True)

        print(
            f"[INFO]: CONTACT-SMOKE {control_label}: final "
            f"(final_tip_target={_small_list(last_tip_target_pos_w)}, "
            f"final_lower_end_error={_small_list(last_error)}, "
            f"final_tip_correction={_small_list(last_correction)})",
            flush=True,
        )
        stacked = torch.stack(forces) if forces else torch.zeros((1, robot.num_instances), device=device)
        return stacked, last_tip_target_pos_w

    def step_sweep_socket_z(
        target_socket_pos_w: torch.Tensor,
        hold_tip_target_pos_w: torch.Tensor,
        tip_quat_w: torch.Tensor,
        steps: int,
        collect_last: int = 30,
        phase_label: str | None = None,
        control_label: str = "press-control",
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """Sweep the local guide vertically while holding the current robot pose.

        This isolates the first semantic gate: dynamic peg vs kinematic socket-wall
        contact. The older arm-servo press path remains available for controller
        reachability, but a failed IK descent should not hide whether contact
        physics and wall-filtered force sensing work at all.
        """

        nonlocal last_phase
        if phase_label is not None:
            last_phase = phase_label
            print(
                f"[INFO]: CONTACT-SMOKE phase {phase_label}: begin "
                f"(steps={steps}, collect_last={collect_last})",
                flush=True,
            )

        start_socket_pos_w = _normal_tensor(socket.data.root_pos_w)
        target_socket_pos_w = _normal_tensor(target_socket_pos_w)
        hold_tip_target_pos_w = _normal_tensor(hold_tip_target_pos_w)
        tip_quat_w = _normal_tensor(tip_quat_w)
        delta_z = target_socket_pos_w[:, 2] - start_socket_pos_w[:, 2]
        print(
            f"[INFO]: CONTACT-SMOKE {control_label}: local-wall-sweep "
            f"(start_socket_pos={_small_list(start_socket_pos_w)}, "
            f"target_socket_pos={_small_list(target_socket_pos_w)}, "
            f"wall_delta_z={_small_list(delta_z)}, "
            f"held_tip_target={_small_list(hold_tip_target_pos_w)})",
            flush=True,
        )

        forces = []
        current_socket_pos_w = start_socket_pos_w
        for i in range(steps):
            alpha = float(i + 1) / float(max(1, steps))
            current_socket_pos_w = start_socket_pos_w + (target_socket_pos_w - start_socket_pos_w) * alpha
            write_socket_guide_at_socket_pos(current_socket_pos_w, wall_center_offset)
            with torch.inference_mode():
                env.step(action_for(hold_tip_target_pos_w, tip_quat_w))
            if phase_label is not None and (
                i == 0 or i + 1 == steps or (i + 1) % 50 == 0
            ):
                lower_end_now, _, _, _ = lower_end_pose_w()
                current_wall_top_z, _, _ = wall_targets_from_socket(current_socket_pos_w)
                print(
                    f"[INFO]: CONTACT-SMOKE phase {phase_label}: progress {i + 1}/{steps} "
                    f"(wall_top_z={_small_list(current_wall_top_z)}, "
                    f"lower_end={_small_list(lower_end_now)})",
                    flush=True,
                )
            if i >= steps - collect_last:
                forces.append(_wall_force(scene))
        if phase_label is not None:
            completed_phases.append(phase_label)
            print(f"[INFO]: CONTACT-SMOKE phase {phase_label}: end", flush=True)

        final_wall_top_z, final_press_xy, final_hover_target = wall_targets_from_socket(current_socket_pos_w)
        lower_end_final, _, _, _ = lower_end_pose_w()
        print(
            f"[INFO]: CONTACT-SMOKE {control_label}: final "
            f"(final_socket_pos={_small_list(current_socket_pos_w)}, "
            f"final_wall_top_z={_small_list(final_wall_top_z)}, "
            f"final_lower_end={_small_list(lower_end_final)})",
            flush=True,
        )
        stacked = torch.stack(forces) if forces else torch.zeros((1, robot.num_instances), device=device)
        return stacked, current_socket_pos_w, final_wall_top_z, final_press_xy

    def require_complete_phase_sequence() -> None:
        required = ["free-space-settle", "press-hold", "retreat-hold"]
        if args_cli.contact_setup == "local-guide":
            required.insert(1, "local-guide-reanchor")
        missing = [name for name in required if name not in completed_phases]
        if missing:
            _FAILURES.append("phase-sequence")
            print(
                "[ERROR]: CONTACT-SMOKE phase-sequence: FAIL "
                f"(last_phase={last_phase}, completed={completed_phases}, missing={missing})",
                flush=True,
            )
        else:
            print(
                "[INFO]: CONTACT-SMOKE phase-sequence: PASS "
                f"(completed={completed_phases})",
                flush=True,
            )

    wall_center_offset = SOCKET_GUIDE_INNER_HALF_WIDTH_M + 0.5 * SOCKET_GUIDE_WALL_THICKNESS_M

    # The action frame is the calibrated controller/insertion tip. Earlier
    # smoke revisions treated it as the gripped upper end and added
    # PEG_LENGTH_M, which commanded the peg to hover above the wall instead of
    # pressing into it.
    hover_clearance = 0.020
    press_depth = 0.020

    _, tip_quat0 = tip_pose_w()
    tip_quat0 = tip_quat0.clone()

    # Geometry: press straight down onto the TOP of the right guide wall. By
    # default, local-guide mode moves the kinematic guide under the current
    # insertion tip so this smoke isolates dynamic peg-vs-wall contact physics.
    # The authored fixed socket position is a separate reachability problem.
    if args_cli.contact_setup == "local-guide":
        lower_end0, _, _, lower_source0 = lower_end_pose_w()
        socket_pos = move_socket_guide_for_local_contact(lower_end0, wall_center_offset, hover_clearance)
        print(
            "[INFO]: CONTACT-SMOKE contact-setup: local-guide "
            f"(peg_pose_source={lower_source0}, socket_pos={_small_list(socket_pos)}, "
            f"initial_lower_end={_small_list(lower_end0)})",
            flush=True,
        )
    else:
        socket_pos = socket.data.root_pos_w  # (N, 3)
        print(
            "[INFO]: CONTACT-SMOKE contact-setup: fixed-socket "
            f"(socket_pos={_small_list(socket_pos)})",
            flush=True,
        )
    wall_top_z, press_xy, hover_target = wall_targets_from_socket(socket_pos)

    try:
        # Phase 1: settle at a free-space hover above the wall top.
        forces = step_hold(
            hover_target,
            tip_quat0,
            args_cli.settle_steps,
            collect_last=10,
            phase_label="free-space-settle",
        )
        attach_err = _attach_error_m(scene, root_from_hand_pos)
        _print_attach_diagnostics(scene, root_from_hand_pos, "after-free-space-settle")
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

        if args_cli.contact_setup == "local-guide":
            # Re-anchor after the hover settle. The absolute IK controller may move
            # laterally while settling; the contact smoke should press vertically
            # from the actual settled inserting-end pose, not from the pre-settle
            # guess used only to establish the free-space negative control.
            lower_end_hover, _, _, lower_source_hover = lower_end_pose_w()
            socket_pos = move_socket_guide_for_local_contact(lower_end_hover, wall_center_offset, hover_clearance)
            wall_top_z, press_xy, hover_target = wall_targets_from_socket(socket_pos)
            tip_hold_target, tip_quat0 = tip_pose_w()
            tip_hold_target = _normal_tensor(tip_hold_target)
            tip_quat0 = tip_quat0.clone()
            reanchor_steps = max(1, int(args_cli.local_guide_reanchor_steps))
            reanchor_forces = step_hold(
                tip_hold_target,
                tip_quat0,
                reanchor_steps,
                collect_last=min(10, reanchor_steps),
                phase_label="local-guide-reanchor",
            )
            reanchor_force = reanchor_forces.mean(dim=0)
            lower_end_reanchored, _, _, lower_source_reanchored = lower_end_pose_w()
            socket_pos = move_socket_guide_for_local_contact(
                lower_end_reanchored,
                wall_center_offset,
                hover_clearance,
            )
            wall_top_z, press_xy, hover_target = wall_targets_from_socket(socket_pos)
            _, tip_quat0 = tip_pose_w()
            tip_quat0 = tip_quat0.clone()
            print(
                "[INFO]: CONTACT-SMOKE contact-setup: local-guide reanchored "
                f"(peg_pose_source={lower_source_reanchored}, socket_pos={_small_list(socket_pos)}, "
                f"pre_hold_lower_end={_small_list(lower_end_hover)}, "
                f"post_hold_lower_end={_small_list(lower_end_reanchored)}, "
                f"hold_tip_target={_small_list(tip_hold_target)})",
                flush=True,
            )
            _check(
                "free-space-reanchored",
                bool((reanchor_force < args_cli.free_force_max).all()),
                f"mean wall force {reanchor_force.tolist()} N after local-guide reanchor, max {args_cli.free_force_max}",
            )

        # Phase 2: prove local peg-vs-wall contact. The default guide-wall sweep
        # moves the kinematic guide into the held dynamic peg, so the first gate
        # tests contact physics instead of Franka IK reachability.
        if args_cli.press_mechanism == "guide-wall-sweep":
            if args_cli.contact_setup != "local-guide":
                raise ValueError("guide-wall-sweep requires --contact_setup local-guide")
            press_socket_pos = socket_pos.clone()
            press_socket_pos[:, 2] = socket_pos[:, 2] + hover_clearance + press_depth
            hold_tip_target, tip_quat0 = tip_pose_w()
            forces, socket_pos, wall_top_z, press_xy = step_sweep_socket_z(
                press_socket_pos,
                hold_tip_target,
                tip_quat0,
                args_cli.press_steps,
                collect_last=30,
                phase_label="press-hold",
                control_label="press-control",
            )
        else:
            press_target = hover_target.clone()
            press_target[:, 2] = wall_top_z - press_depth
            forces, _ = step_track_lower_end(
                press_target,
                tip_quat0,
                args_cli.press_steps,
                collect_last=30,
                phase_label="press-hold",
                control_label="press-control",
            )
        press_force = forces.mean(dim=0)
        _check(
            "press-force",
            bool((press_force > args_cli.press_force_min).all()),
            f"mean wall force {press_force.tolist()} N over last 30 press steps, min {args_cli.press_force_min}",
        )

        # The force and blocked checks only mean anything if the controller actually
        # brought the inserting end to the wall-contact line. Use the physical peg
        # body, not the commanded action frame, so failed IK tracking cannot look
        # like valid contact physics.
        lower_end, _, _, peg_pose_source = lower_end_pose_w()
        sink = wall_top_z - lower_end[:, 2]
        print(f"[INFO]: CONTACT-SMOKE press peg pose source {peg_pose_source}", flush=True)
        lateral_slip = torch.linalg.norm(lower_end[:, :2] - press_xy, dim=-1)
        _check(
            "press-tracking",
            bool((lateral_slip <= args_cli.press_lateral_tolerance_m).all()),
            f"lower-end lateral error {lateral_slip.tolist()} m to wall target, "
            f"tolerance {args_cli.press_lateral_tolerance_m}",
        )
        if args_cli.press_mechanism == "guide-wall-sweep":
            centerline_clearance = lower_end[:, 2] - wall_top_z
            blocked_error = centerline_clearance - float(PEG_RADIUS_M)
            blocked_detail = (
                f"lower_end_z - wall_top_z {centerline_clearance.tolist()} m vs expected "
                f"peg radius {PEG_RADIUS_M} m, error {blocked_error.tolist()} m, "
                f"tolerance {args_cli.block_tolerance_m}"
            )
        else:
            blocked_error = sink
            blocked_detail = (
                f"wall_top_z - lower_end_z {sink.tolist()} m vs expected 0.0 m at the wall-top plane, "
                f"commanded {press_depth} m penetration, tolerance {args_cli.block_tolerance_m}"
            )
        _check(
            "press-blocked",
            bool((torch.abs(blocked_error) <= args_cli.block_tolerance_m).all()),
            blocked_detail,
        )
        penetration = torch.clamp(sink, min=0.0)
        _check(
            "press-no-clip",
            bool((penetration <= args_cli.clip_tolerance_m).all()),
            f"lower-end wall penetration {penetration.tolist()} m, tolerance {args_cli.clip_tolerance_m}",
        )
        print(f"[INFO]: CONTACT-SMOKE press lateral slip {lateral_slip.tolist()} m (informational)", flush=True)

        # Phase 3: retreat and confirm release + joint integrity.
        if args_cli.press_mechanism == "guide-wall-sweep":
            retreat_socket_pos = socket_pos.clone()
            retreat_socket_pos[:, 2] = socket_pos[:, 2] - (hover_clearance + press_depth)
            hold_tip_target, tip_quat0 = tip_pose_w()
            forces, socket_pos, wall_top_z, press_xy = step_sweep_socket_z(
                retreat_socket_pos,
                hold_tip_target,
                tip_quat0,
                args_cli.retreat_steps,
                collect_last=10,
                phase_label="retreat-hold",
                control_label="retreat-control",
            )
        else:
            forces, _ = step_track_lower_end(
                hover_target,
                tip_quat0,
                args_cli.retreat_steps,
                collect_last=10,
                phase_label="retreat-hold",
                control_label="retreat-control",
            )
        release_force = forces.mean(dim=0)
        _check(
            "release",
            bool((release_force < args_cli.free_force_max).all()),
            f"mean wall force {release_force.tolist()} N after retreat, max {args_cli.free_force_max}",
        )
        attach_err = _attach_error_m(scene, root_from_hand_pos)
        _print_attach_diagnostics(scene, root_from_hand_pos, "after-retreat")
        _check(
            "joint-integrity",
            bool((attach_err < args_cli.attach_tolerance_m).all()),
            f"per-env hand-peg error {attach_err.tolist()} m after contact, tolerance {args_cli.attach_tolerance_m}",
        )
    except BaseException as exc:
        _FAILURES.append("phase-exception")
        print(
            "[ERROR]: CONTACT-SMOKE phase-exception: "
            f"type={type(exc).__name__} repr={exc!r} "
            f"last_phase={last_phase} completed={completed_phases}",
            flush=True,
        )
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
        raise
    finally:
        require_complete_phase_sequence()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc(file=sys.stderr)
        raise
