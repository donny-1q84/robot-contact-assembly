"""Run a simple scripted peg-in-hole baseline for the robot_contact_assembly Isaac Lab task."""

from __future__ import annotations

import argparse
import json
import os
import sys

import gymnasium as gym
import torch
import warp as wp

from isaaclab_tasks.utils import add_launcher_args, launch_simulation, resolve_task_config


RigidObject = None
SceneEntityCfg = None
combine_frame_transforms = None
compute_pose_error = None
subtract_frame_transforms = None
DifferentialIKController = None
DifferentialIKControllerCfg = None
IDENTITY_QUAT = None
PEG_TIP_BODY_OFFSET_POS = None
PEG_TIP_BODY_OFFSET_ROT = None
PEG_TIP_FROM_CENTER_POS = None
mdp = None
BODY_OFFSET = None


def _as_torch(value) -> torch.Tensor:
    return value if isinstance(value, torch.Tensor) else wp.to_torch(value)


def _hand_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    robot = env_unwrapped.scene["robot"]
    hand_pos_w = _as_torch(robot.data.body_pos_w)[:, body_idx]
    hand_quat_w = _as_torch(robot.data.body_quat_w)[:, body_idx]
    return hand_pos_w, hand_quat_w


def _action_frame_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env_unwrapped, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    offset_quat = hand_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)


def _clamp_actions(values: torch.Tensor, limit: torch.Tensor | float) -> torch.Tensor:
    return torch.clamp(values, min=-limit, max=limit)


def _parse_action_axis_signs(value: str) -> tuple[float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("expected three comma-separated values, e.g. 1,-1,-1")
    try:
        signs = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("axis signs must be numeric") from exc
    if any(sign == 0.0 for sign in signs):
        raise argparse.ArgumentTypeError("axis signs must be non-zero")
    return signs


def _parse_vec3(value: str) -> tuple[float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("expected three comma-separated values, e.g. 0.45,0.0,0.19")
    try:
        return tuple(float(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("vector values must be numeric") from exc


def _quat_multiply(lhs: torch.Tensor, rhs: torch.Tensor) -> torch.Tensor:
    """Hamilton product for `(x, y, z, w)` quaternions."""

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


def _normalize_quat(quat: torch.Tensor) -> torch.Tensor:
    return quat / torch.clamp(torch.linalg.norm(quat, dim=-1, keepdim=True), min=1.0e-8)


def _quat_conjugate(quat: torch.Tensor) -> torch.Tensor:
    result = quat.clone()
    result[..., :3] = -result[..., :3]
    return result


def _quat_rotate(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    zeros = torch.zeros(vec.shape[:-1] + (1,), device=vec.device, dtype=vec.dtype)
    vec_quat = torch.cat((vec, zeros), dim=-1)
    rotated = _quat_multiply(_quat_multiply(quat, vec_quat), _quat_conjugate(quat))
    return rotated[..., :3]


def _child_pose_to_parent_pose(
    child_pos_w: torch.Tensor,
    child_quat_w: torch.Tensor,
    offset_pos: torch.Tensor,
    offset_quat: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Invert `child = parent * offset` and return the parent pose."""

    inv_offset_quat = _quat_conjugate(offset_quat)
    inv_offset_pos = _quat_rotate(inv_offset_quat, -offset_pos)
    parent_pos_w = child_pos_w + _quat_rotate(child_quat_w, inv_offset_pos)
    parent_quat_w = _normalize_quat(_quat_multiply(child_quat_w, inv_offset_quat))
    return parent_pos_w, parent_quat_w


def _axis_angle_to_quat(axis_angle: torch.Tensor) -> torch.Tensor:
    angle = torch.linalg.norm(axis_angle, dim=-1, keepdim=True)
    axis = axis_angle / torch.clamp(angle, min=1.0e-8)
    half_angle = 0.5 * angle
    quat = torch.cat((axis * torch.sin(half_angle), torch.cos(half_angle)), dim=-1)
    small_angle = angle.squeeze(-1) < 1.0e-8
    if small_angle.any():
        quat[small_angle] = axis_angle.new_tensor((0.0, 0.0, 0.0, 1.0))
    return _normalize_quat(quat)


def _quat_step_towards(current: torch.Tensor, target: torch.Tensor, max_rotation: float) -> torch.Tensor:
    """Move `current` toward `target` by at most `max_rotation` radians.

    This keeps quaternion sign continuity against the previous command. That matters near 180 deg, where
    recomputing an axis-angle waypoint from the measured pose can alternate between antipodal branches.
    """

    current = _normalize_quat(current)
    target = _normalize_quat(target)
    dot = torch.sum(current * target, dim=-1, keepdim=True)
    target = torch.where(dot < 0.0, -target, target)
    dot = torch.abs(dot).clamp(max=1.0)
    omega = torch.acos(dot)
    angle = 2.0 * omega
    t = torch.clamp(max_rotation / torch.clamp(angle, min=1.0e-8), max=1.0)
    sin_omega = torch.sin(omega)
    linear_mask = sin_omega < 1.0e-6
    slerp = (
        torch.sin((1.0 - t) * omega) / torch.clamp(sin_omega, min=1.0e-8) * current
        + torch.sin(t * omega) / torch.clamp(sin_omega, min=1.0e-8) * target
    )
    lerp = _normalize_quat((1.0 - t) * current + t * target)
    return _normalize_quat(torch.where(linear_mask, lerp, slerp))


def _load_calibrated_position_response(path: str) -> tuple[list[dict[str, list[float]]], int]:
    with open(path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    probes = summary.get("probes")
    if not isinstance(probes, dict):
        raise ValueError(f"calibration JSON missing probes: {path}")

    candidates = []
    for name in ("x_pos", "x_neg", "y_pos", "y_neg", "z_pos", "z_neg"):
        probe = probes.get(name)
        if not isinstance(probe, dict):
            raise ValueError(f"calibration JSON missing probe {name}: {path}")
        action_xyz = probe.get("action_xyz")
        delta_pos = probe.get("delta_action_pos")
        if not (
            isinstance(action_xyz, list)
            and isinstance(delta_pos, list)
            and len(action_xyz) == 3
            and len(delta_pos) == 3
        ):
            raise ValueError(f"calibration probe {name} has invalid action/delta fields: {path}")
        candidates.append({"name": name, "action_xyz": action_xyz, "delta_pos": delta_pos})

    steps_per_probe = int(summary.get("steps_per_probe", 1))
    if steps_per_probe <= 0:
        raise ValueError(f"calibration JSON has invalid steps_per_probe={steps_per_probe}: {path}")
    return candidates, steps_per_probe

parser = argparse.ArgumentParser(description="Scripted baseline for robot_contact_assembly Isaac Lab tasks.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=None, help="Override number of environments.")
parser.add_argument("--steps", type=int, default=200, help="Number of env steps to run before exit in headless mode.")
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-IK-Rel-Play-v0", help="Task name.")
parser.add_argument("--seed", type=int, default=42, help="Deterministic seed for the scripted baseline.")
parser.add_argument("--video", action="store_true", default=False, help="Record one scripted reference video.")
parser.add_argument("--video_length", type=int, default=200, help="Length of the recorded video in steps.")
parser.add_argument(
    "--video_backend",
    type=str,
    default="viewport",
    choices=("viewport",),
    help="Video recording backend for the scripted rollout.",
)
parser.add_argument(
    "--video_folder",
    type=str,
    default=None,
    help="Optional directory for recorded videos. Defaults to a local scripted-video folder under /workspace/artifacts.",
)
parser.add_argument(
    "--summary-json",
    type=str,
    default=None,
    help="Optional path to write a JSON summary for fixed-seed evaluation runs.",
)
parser.add_argument("--approach-height", type=float, default=0.05, help="Approach offset over the target along +Z.")
parser.add_argument("--approach-xy-tol", type=float, default=0.015, help="Lateral tolerance before switching to insertion.")
parser.add_argument("--approach-z-tol", type=float, default=0.02, help="World-Z tolerance for the pre-insertion hold pose.")
parser.add_argument("--approach-rot-tol", type=float, default=0.25, help="Orientation tolerance before switching to insertion.")
parser.add_argument(
    "--insert-xy-tol",
    type=float,
    default=None,
    help="Current socket-frame lateral tolerance required before commanding insertion. Defaults to approach-xy-tol.",
)
parser.add_argument(
    "--insert-rot-tol",
    type=float,
    default=None,
    help="Current orientation tolerance required before commanding insertion. Defaults to approach-rot-tol.",
)
parser.add_argument(
    "--insert-abort-xy-tol",
    type=float,
    default=None,
    help="Exit latched insert mode if current lateral error exceeds this value. Defaults to approach-xy-tol.",
)
parser.add_argument(
    "--insert-abort-rot-tol",
    type=float,
    default=None,
    help="Exit latched insert mode if current orientation error exceeds this value. Defaults to approach-rot-tol.",
)
parser.add_argument(
    "--insert-abort-grace-steps",
    type=int,
    default=1,
    help="Consecutive over-threshold steps required before exiting latched insert mode. 1 preserves immediate abort behavior.",
)
parser.add_argument(
    "--staged-approach",
    action="store_true",
    default=False,
    help="Align XY at the current height before descending to the pre-insertion approach height.",
)
parser.add_argument(
    "--rotate-before-descend",
    action="store_true",
    default=False,
    help="In staged approach mode, rotate to the socket orientation after XY alignment before descending.",
)
parser.add_argument(
    "--coupled-approach",
    action="store_true",
    default=False,
    help="Use the legacy controller that rotates while translating toward the socket.",
)
parser.add_argument("--pos-gain", type=float, default=2.0, help="Proportional gain for position error.")
parser.add_argument("--rot-gain", type=float, default=2.0, help="Proportional gain for axis-angle orientation error.")
parser.add_argument("--pos-clamp", type=float, default=0.12, help="Clamp applied to each translational action dimension.")
parser.add_argument("--rot-clamp", type=float, default=0.4, help="Clamp applied to each rotational action dimension.")
parser.add_argument(
    "--action-axis-signs",
    type=_parse_action_axis_signs,
    default=(1.0, 1.0, 1.0),
    help="Comma-separated root-frame translational action-axis signs. Debug logs show the signed command vector.",
)
parser.add_argument(
    "--position-control-mode",
    choices=("direct", "calibrated-onehot"),
    default="direct",
    help=(
        "Position controller. 'direct' applies proportional root-frame deltas; "
        "'calibrated-onehot' greedily selects the calibrated one-hot raw action predicted to reduce position error."
    ),
)
parser.add_argument(
    "--position-response-json",
    type=str,
    default=None,
    help="Calibration JSON from scripts/calibrate_relative_ik_action.py, required for calibrated-onehot mode.",
)
parser.add_argument(
    "--debug-action-steps",
    type=int,
    default=0,
    help="Print detailed action-frame diagnostics for the first N control steps.",
)
parser.add_argument(
    "--warmup-steps",
    type=int,
    default=30,
    help="Zero-action settling steps after reset before measuring and applying the scripted controller.",
)
parser.add_argument(
    "--deterministic-reset",
    action="store_true",
    default=False,
    help="Disable reset joint randomization for deterministic controller gates.",
)
parser.add_argument(
    "--socket-pos",
    type=_parse_vec3,
    default=None,
    help="Override the fixed socket-frame world position as x,y,z for deterministic debugging gates.",
)
parser.add_argument(
    "--abs-control-mode",
    choices=("target", "waypoint"),
    default="target",
    help="For 7D absolute IK actions, command the full target pose or a small absolute waypoint toward it.",
)
parser.add_argument(
    "--rotate-control-mode",
    choices=("inherit", "target", "waypoint", "stateful-waypoint"),
    default="inherit",
    help=(
        "Override quaternion control only during the rotate-only staged phase. "
        "'target' keeps the position waypoint but sends the full target quaternion; "
        "'stateful-waypoint' advances a persistent quaternion command toward the target."
    ),
)
parser.add_argument(
    "--scripted-control-mode",
    choices=("auto", "mdp", "joint-ik"),
    default="auto",
    help=(
        "Controller used by the scripted agent. 'mdp' sends actions to the task action term; "
        "'joint-ik' computes joint-position targets with a standalone Jacobian IK pre-controller."
    ),
)
parser.add_argument(
    "--abs-pos-step",
    type=float,
    default=0.025,
    help="Maximum per-axis position step for --abs-control-mode waypoint.",
)
parser.add_argument(
    "--insert-pos-step",
    type=float,
    default=None,
    help="Optional maximum per-axis position step while insert_mask is active. Defaults to abs-pos-step.",
)
parser.add_argument(
    "--abs-rot-step",
    type=float,
    default=0.20,
    help="Maximum axis-angle rotation step for --abs-control-mode waypoint.",
)
parser.add_argument(
    "--insert-rot-step",
    type=float,
    default=None,
    help="Optional maximum axis-angle rotation step while insert_mask is active. Defaults to abs-rot-step.",
)
parser.add_argument(
    "--joint-ik-step",
    type=float,
    default=0.05,
    help="Maximum per-step joint delta in radians for the standalone joint-IK scripted controller.",
)
parser.add_argument(
    "--joint-limit-margin",
    type=float,
    default=0.02,
    help="Margin in radians kept inside reported joint position limits for joint-IK commands.",
)
parser.add_argument(
    "--trace-json",
    type=str,
    default=None,
    help="Optional path to write per-step controller trace JSON for the first environment.",
)
parser.add_argument("--polish-xy-tol", type=float, default=0.008, help="Lateral tolerance to enter the near-contact polish phase.")
parser.add_argument("--polish-z-tol", type=float, default=0.012, help="Axial tolerance to enter the near-contact polish phase.")
parser.add_argument("--polish-pos-gain", type=float, default=1.2, help="Lateral position gain during the near-contact polish phase.")
parser.add_argument("--polish-pos-clamp", type=float, default=0.008, help="Lateral position clamp during the near-contact polish phase.")
parser.add_argument("--polish-rot-gain", type=float, default=5.0, help="Orientation gain during the near-contact polish phase.")
parser.add_argument("--polish-rot-clamp", type=float, default=0.35, help="Orientation clamp during the near-contact polish phase.")
parser.add_argument("--settle-xy-tol", type=float, default=0.004, help="Lateral tolerance required before final seating.")
parser.add_argument("--settle-rot-tol", type=float, default=0.24, help="Orientation error threshold to enter the final seating phase.")
parser.add_argument("--settle-pos-gain", type=float, default=0.8, help="Lateral position gain during the final seating phase.")
parser.add_argument("--settle-pos-clamp", type=float, default=0.004, help="Lateral position clamp during the final seating phase.")
parser.add_argument("--settle-z-gain", type=float, default=0.8, help="Axial position gain during the final seating phase.")
parser.add_argument("--settle-z-clamp", type=float, default=0.004, help="Axial position clamp during the final seating phase.")
parser.add_argument("--settle-rot-gain", type=float, default=1.5, help="Orientation gain during the final seating phase.")
parser.add_argument("--settle-rot-clamp", type=float, default=0.12, help="Orientation clamp during the final seating phase.")
add_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
skip_auto_enable_cameras = os.environ.get("RCA_SKIP_AUTO_ENABLE_CAMERAS", "0") == "1"
if args_cli.video and args_cli.video_backend == "viewport" and not skip_auto_enable_cameras:
    args_cli.enable_cameras = True
hydra_args.extend(
    [
        r"hydra.run.dir=/workspace/artifacts/hydra/${now:%Y-%m-%d}/${now:%H-%M-%S}",
        "hydra.output_subdir=null",
    ]
)
sys.argv = [sys.argv[0]] + hydra_args

import robot_contact_assembly_tasks.tasks  # noqa: F401,E402


def _tool_tip_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env_unwrapped, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    offset_quat = hand_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)


def _socket_pose_w(env_unwrapped) -> tuple[torch.Tensor, torch.Tensor]:
    socket = env_unwrapped.scene["socket_frame"]
    return _as_torch(socket.data.root_pos_w), _as_torch(socket.data.root_quat_w)


def _target_action_frame_pose_w(socket_pos_w: torch.Tensor, socket_quat_w: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    return socket_pos_w.clone(), socket_quat_w.clone()


def _physical_peg_tip_pose_w(env_unwrapped) -> tuple[torch.Tensor, torch.Tensor]:
    peg = env_unwrapped.scene["peg"]
    peg_pos_w = _as_torch(peg.data.root_pos_w)
    peg_quat_w = _as_torch(peg.data.root_quat_w)
    tip_offset_pos = peg_pos_w.new_tensor(PEG_TIP_FROM_CENTER_POS).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    tip_offset_quat = peg_pos_w.new_tensor(IDENTITY_QUAT).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    return combine_frame_transforms(peg_pos_w, peg_quat_w, tip_offset_pos, tip_offset_quat)


def _override_socket_pose(env_cfg, socket_pos: tuple[float, float, float]) -> None:
    from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
        SOCKET_GUIDE_INNER_HALF_WIDTH_M,
        SOCKET_GUIDE_WALL_THICKNESS_M,
    )

    x, y, z = socket_pos
    wall_offset = SOCKET_GUIDE_INNER_HALF_WIDTH_M + 0.5 * SOCKET_GUIDE_WALL_THICKNESS_M
    env_cfg.scene.socket_frame.init_state.pos = (x, y, z)
    env_cfg.scene.socket_wall_left.init_state.pos = (x - wall_offset, y, z)
    env_cfg.scene.socket_wall_right.init_state.pos = (x + wall_offset, y, z)
    env_cfg.scene.socket_wall_front.init_state.pos = (x, y - wall_offset, z)
    env_cfg.scene.socket_wall_back.init_state.pos = (x, y + wall_offset, z)
    env_cfg.commands.socket_pose.ranges.pos_x = (x, x)
    env_cfg.commands.socket_pose.ranges.pos_y = (y, y)
    env_cfg.commands.socket_pose.ranges.pos_z = (z, z)


def _clamp_joint_targets(
    robot,
    joint_ids: torch.Tensor,
    joint_pos: torch.Tensor,
    joint_pos_des: torch.Tensor,
    max_step: float,
    limit_margin: float,
) -> torch.Tensor:
    """Bound IK joint targets so a far Cartesian target cannot command unstable joint jumps."""

    max_step = max(0.0, max_step)
    joint_pos_des = joint_pos + torch.clamp(joint_pos_des - joint_pos, min=-max_step, max=max_step)

    limits = getattr(robot.data, "soft_joint_pos_limits", None)
    if limits is None:
        limits = getattr(robot.data, "joint_pos_limits", None)
    if limits is None:
        return joint_pos_des

    limits = _as_torch(limits).index_select(1, joint_ids)
    lower = limits[..., 0] + limit_margin
    upper = limits[..., 1] - limit_margin
    return torch.minimum(torch.maximum(joint_pos_des, lower), upper)


def main():
    global RigidObject, SceneEntityCfg, combine_frame_transforms, compute_pose_error, subtract_frame_transforms
    global DifferentialIKController, DifferentialIKControllerCfg
    global IDENTITY_QUAT, PEG_TIP_BODY_OFFSET_POS, PEG_TIP_BODY_OFFSET_ROT, PEG_TIP_FROM_CENTER_POS, mdp, BODY_OFFSET

    os.makedirs("/workspace/artifacts/hydra", exist_ok=True)
    torch.manual_seed(args_cli.seed)
    env_cfg, _ = resolve_task_config(args_cli.task, "")
    env_cfg.seed = args_cli.seed

    with launch_simulation(env_cfg, args_cli):
        from isaaclab.assets import RigidObject
        from isaaclab.controllers import DifferentialIKController, DifferentialIKControllerCfg
        from isaaclab.managers import SceneEntityCfg
        from isaaclab.utils.math import combine_frame_transforms, compute_pose_error, subtract_frame_transforms
        from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole import mdp
        from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
            IDENTITY_QUAT,
            PEG_TIP_BODY_OFFSET_POS,
            PEG_TIP_BODY_OFFSET_ROT,
            PEG_TIP_FROM_CENTER_POS,
            SOCKET_GUIDE_CLEARANCE_M,
            SOCKET_SUCCESS_ROT_TOLERANCE_RAD,
            SOCKET_SUCCESS_XY_TOLERANCE_M,
            SOCKET_SUCCESS_Z_TOLERANCE_M,
        )

        BODY_OFFSET = PEG_TIP_BODY_OFFSET_POS
        env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
        env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
        if args_cli.disable_fabric:
            env_cfg.sim.use_fabric = False
        step_dt = env_cfg.sim.dt * env_cfg.decimation
        env_cfg.episode_length_s = max(env_cfg.episode_length_s, (args_cli.steps + 2) * step_dt)
        # Keep a fixed target for the scripted baseline so convergence is measured against one command.
        env_cfg.commands.socket_pose.resampling_time_range = (1.0e6, 1.0e6)
        if args_cli.deterministic_reset:
            env_cfg.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
        if args_cli.socket_pos is not None:
            _override_socket_pose(env_cfg, args_cli.socket_pos)
            print(f"[SCRIPTED] overriding socket world position to {args_cli.socket_pos}", flush=True)

        render_mode = "rgb_array" if args_cli.video and args_cli.video_backend == "viewport" else None
        env = gym.make(args_cli.task, cfg=env_cfg, render_mode=render_mode)
        video_folder = None
        if args_cli.video:
            video_folder = (
                os.path.abspath(args_cli.video_folder)
                if args_cli.video_folder
                else os.path.join("/workspace/artifacts/videos/scripted", f"seed_{args_cli.seed}")
            )
            os.makedirs(video_folder, exist_ok=True)
            env = gym.wrappers.RecordVideo(
                env,
                video_folder=video_folder,
                step_trigger=lambda step: step == 0,
                video_length=min(args_cli.video_length, args_cli.steps),
                disable_logger=True,
            )
            print(
                f"[SCRIPTED] recording video with {args_cli.video_backend} backend to {video_folder} "
                f"(length={min(args_cli.video_length, args_cli.steps)})",
                flush=True,
            )
        env_unwrapped = env.unwrapped
        print(f"[INFO]: Gym observation space: {env.observation_space}", flush=True)
        print(f"[INFO]: Gym action space: {env.action_space}", flush=True)
        env.reset()

        if args_cli.warmup_steps > 0:
            zero_actions = torch.zeros(env.action_space.shape, device=env_unwrapped.device)
            for _ in range(args_cli.warmup_steps):
                env.step(zero_actions)
            print(f"[SCRIPTED] completed zero-action warmup steps={args_cli.warmup_steps}", flush=True)

        robot = env_unwrapped.scene["robot"]
        body_ids, _ = robot.find_bodies("panda_hand")
        body_idx = body_ids[0]
        peg_cfg = SceneEntityCfg("peg")
        socket_cfg = SceneEntityCfg("socket_frame")
        contact_sensor_cfg = None
        try:
            env_unwrapped.scene["peg_contact"]
            contact_sensor_cfg = SceneEntityCfg("peg_contact")
        except KeyError:
            contact_sensor_cfg = None
        action_dim = env.action_space.shape[-1]
        scripted_control_mode = args_cli.scripted_control_mode
        if scripted_control_mode == "auto":
            scripted_control_mode = "joint-ik" if "JointPos" in args_cli.task else "mdp"
        if action_dim not in (6, 7):
            raise ValueError(f"unsupported scripted action dimension: {action_dim}")
        if scripted_control_mode == "joint-ik" and action_dim != 7:
            raise ValueError(f"joint-ik scripted control requires a 7D joint-position action, got {action_dim}")

        diff_ik_controller = None
        robot_entity_cfg = None
        ee_jacobi_idx = None
        if scripted_control_mode == "joint-ik":
            assert DifferentialIKController is not None
            assert DifferentialIKControllerCfg is not None
            robot_entity_cfg = SceneEntityCfg(
                "robot",
                joint_names=[
                    "panda_joint1",
                    "panda_joint2",
                    "panda_joint3",
                    "panda_joint4",
                    "panda_joint5",
                    "panda_joint6",
                    "panda_joint7",
                ],
                body_names=["panda_hand"],
            )
            robot_entity_cfg.resolve(env_unwrapped.scene)
            ee_jacobi_idx = robot_entity_cfg.body_ids[0] - 1 if robot.is_fixed_base else robot_entity_cfg.body_ids[0]
            diff_ik_cfg = DifferentialIKControllerCfg(command_type="pose", use_relative_mode=False, ik_method="dls")
            diff_ik_controller = DifferentialIKController(
                diff_ik_cfg,
                num_envs=env_unwrapped.num_envs,
                device=env_unwrapped.device,
            )
            diff_ik_controller.reset()
            print(
                "[SCRIPTED] using standalone joint-IK pre-controller "
                f"body_id={robot_entity_cfg.body_ids[0]} ee_jacobi_idx={ee_jacobi_idx} "
                f"joint_ids={robot_entity_cfg.joint_ids}",
                flush=True,
            )

        initial_lateral = None
        initial_axial = None
        initial_rot = None
        final_lateral = None
        final_axial = None
        final_rot = None
        final_success = None
        success_step = None
        best_lateral = float("inf")
        best_lateral_step = None
        best_axial = float("inf")
        best_axial_step = None
        best_rot = float("inf")
        best_rot_step = None
        initial_action_tip_alignment = None
        final_action_tip_alignment = None
        best_action_tip_alignment = float("inf")
        best_action_tip_alignment_step = None
        max_contact_force_magnitude = 0.0
        max_contact_force_magnitude_step = None
        trace_rows = []
        xy_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        rotate_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        insert_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        insert_abort_counts = torch.zeros(env_unwrapped.num_envs, dtype=torch.long, device=env_unwrapped.device)
        rotate_hold_pos_w = torch.zeros((env_unwrapped.num_envs, 3), dtype=torch.float32, device=env_unwrapped.device)
        rotate_hold_valid = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        rotate_command_quat_w = torch.zeros((env_unwrapped.num_envs, 4), dtype=torch.float32, device=env_unwrapped.device)
        rotate_command_valid = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        polish_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        settle_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        action_axis_signs = torch.tensor(args_cli.action_axis_signs, device=env_unwrapped.device).unsqueeze(0)
        calibrated_candidate_names: list[str] = []
        calibrated_candidate_actions = None
        calibrated_candidate_deltas = None
        if args_cli.position_control_mode == "calibrated-onehot":
            if not args_cli.position_response_json:
                raise ValueError("--position-response-json is required when --position-control-mode=calibrated-onehot")
            candidates, steps_per_probe = _load_calibrated_position_response(args_cli.position_response_json)
            calibrated_candidate_names = [candidate["name"] for candidate in candidates]
            calibrated_candidate_actions = torch.tensor(
                [candidate["action_xyz"] for candidate in candidates],
                dtype=torch.float32,
                device=env_unwrapped.device,
            )
            calibrated_candidate_deltas = torch.tensor(
                [candidate["delta_pos"] for candidate in candidates],
                dtype=torch.float32,
                device=env_unwrapped.device,
            ) / float(steps_per_probe)
            print(
                "[SCRIPTED] loaded calibrated one-hot position response "
                f"path={args_cli.position_response_json} candidates={calibrated_candidate_names} "
                f"steps_per_probe={steps_per_probe}",
                flush=True,
            )

        sim = env_unwrapped.sim
        for step in range(args_cli.steps):
            if sim.visualizers and not any(v.is_running() and not v.is_closed for v in sim.visualizers):
                break

            action_pos_w, action_quat_w = _action_frame_pose_w(env_unwrapped, body_idx)
            hand_pos_w, hand_quat_w = _hand_pose_w(env_unwrapped, body_idx)
            physical_tip_pos_w, physical_tip_quat_w = _physical_peg_tip_pose_w(env_unwrapped)
            socket_pos_w, socket_quat_w = _socket_pose_w(env_unwrapped)
            target_action_pos_w, target_action_quat_w = _target_action_frame_pose_w(socket_pos_w, socket_quat_w)
            physical_tip_rel_socket_pos, _ = subtract_frame_transforms(
                socket_pos_w,
                socket_quat_w,
                physical_tip_pos_w,
                physical_tip_quat_w,
            )
            action_tip_alignment = torch.linalg.norm(physical_tip_pos_w - action_pos_w, dim=1)

            lateral_error, axial_error, orientation_error = mdp.insertion_metrics(
                env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg
            )
            orientation_ready = orientation_error < args_cli.approach_rot_tol
            insert_xy_tolerance = args_cli.insert_xy_tol if args_cli.insert_xy_tol is not None else args_cli.approach_xy_tol
            insert_rot_tolerance = (
                args_cli.insert_rot_tol if args_cli.insert_rot_tol is not None else args_cli.approach_rot_tol
            )
            insert_xy_ready = lateral_error < insert_xy_tolerance
            insert_orientation_ready = orientation_error < insert_rot_tolerance
            insert_abort_xy_tolerance = (
                args_cli.insert_abort_xy_tol
                if args_cli.insert_abort_xy_tol is not None
                else args_cli.approach_xy_tol
            )
            insert_abort_rot_tolerance = (
                args_cli.insert_abort_rot_tol
                if args_cli.insert_abort_rot_tol is not None
                else args_cli.approach_rot_tol
            )

            approach_pos_w = target_action_pos_w.clone()
            approach_pos_w[:, 2] += args_cli.approach_height
            target_pos_w = approach_pos_w.clone()
            target_quat_w = target_action_quat_w.clone()
            controller_lateral_error = torch.linalg.norm((target_action_pos_w - action_pos_w)[:, :2], dim=1)

            if args_cli.coupled_approach:
                position_ready = (lateral_error < args_cli.approach_xy_tol) & (
                    orientation_error < args_cli.approach_rot_tol
                )
                rotate_state |= position_ready
                insert_mask = position_ready & insert_xy_ready & insert_orientation_ready
            elif args_cli.staged_approach:
                xy_state |= lateral_error < args_cli.approach_xy_tol
                xy_target_pos_w = target_action_pos_w.clone()
                xy_target_pos_w[:, 2] = action_pos_w[:, 2]
                target_pos_w[~xy_state] = xy_target_pos_w[~xy_state]

                approach_z_error = torch.abs(action_pos_w[:, 2] - approach_pos_w[:, 2])
                target_quat_w = action_quat_w.clone()
                if args_cli.rotate_before_descend:
                    prev_rotate_state = rotate_state.clone()
                    rotate_state |= xy_state
                    new_rotate_mask = rotate_state & ~prev_rotate_state
                    if new_rotate_mask.any():
                        rotate_hold_pos_w[new_rotate_mask] = xy_target_pos_w[new_rotate_mask]
                        rotate_hold_valid[new_rotate_mask] = True
                    rotation_ready = rotate_state & orientation_ready
                    rotate_hold_mask = rotate_state & ~rotation_ready
                    if rotate_hold_mask.any():
                        target_pos_w[rotate_hold_mask] = torch.where(
                            rotate_hold_valid[rotate_hold_mask, None],
                            rotate_hold_pos_w[rotate_hold_mask],
                            xy_target_pos_w[rotate_hold_mask],
                        )
                    target_quat_w[rotate_state] = target_action_quat_w[rotate_state]
                    position_ready = rotation_ready & (approach_z_error < args_cli.approach_z_tol)
                else:
                    position_ready = xy_state & (approach_z_error < args_cli.approach_z_tol)
                    rotate_state |= position_ready
                    target_quat_w[rotate_state] = target_action_quat_w[rotate_state]
                insert_mask = (
                    position_ready
                    & insert_xy_ready
                    & insert_orientation_ready
                )
            else:
                # Decouple gross translation from large orientation changes. With a rigid tip offset, rotating
                # while still far from the socket can move the tip away from the approach corridor.
                approach_z_error = torch.abs(action_pos_w[:, 2] - approach_pos_w[:, 2])
                position_ready = (lateral_error < args_cli.approach_xy_tol) & (
                    approach_z_error < args_cli.approach_z_tol
                )
                rotate_state |= position_ready
                target_quat_w = action_quat_w.clone()
                target_quat_w[rotate_state] = target_action_quat_w[rotate_state]
                insert_mask = (
                    rotate_state
                    & insert_xy_ready
                    & insert_orientation_ready
                )

            insert_entry_mask = insert_mask
            insert_state |= insert_entry_mask
            insert_abort_counts[insert_entry_mask] = 0
            insert_abort_violation_mask = insert_state & (
                (lateral_error > insert_abort_xy_tolerance) | (orientation_error > insert_abort_rot_tolerance)
            )
            insert_abort_counts[insert_abort_violation_mask] += 1
            insert_abort_counts[~insert_abort_violation_mask] = 0
            insert_abort_grace_steps = max(1, args_cli.insert_abort_grace_steps)
            insert_abort_mask = insert_abort_violation_mask & (insert_abort_counts >= insert_abort_grace_steps)
            insert_state[insert_abort_mask] = False
            insert_abort_counts[insert_abort_mask] = 0
            insert_mask = insert_state

            target_pos_w[insert_mask] = target_action_pos_w[insert_mask]
            polish_mask = (lateral_error < args_cli.polish_xy_tol) & (axial_error < args_cli.polish_z_tol)
            polish_state |= polish_mask
            settle_mask = polish_state & (lateral_error < args_cli.settle_xy_tol) & (orientation_error < args_cli.settle_rot_tol)
            settle_state = settle_mask

            polish_only = polish_state & ~settle_state
            target_pos_w[polish_only, 2] = action_pos_w[polish_only, 2]

            pos_error, axis_angle_error = compute_pose_error(
                action_pos_w, action_quat_w, target_pos_w, target_quat_w, rot_error_type="axis_angle"
            )
            rotate_only_mask = rotate_state & ~orientation_ready & ~insert_mask & ~polish_state
            rotate_quat_hold_mask = rotate_state & ~insert_mask & ~polish_state
            # Isaac Lab's relative IK action applies translational deltas directly in the robot root frame.
            # Do not rotate the Cartesian error into the end-effector frame here.
            action_pos_error = pos_error
            signed_action_pos_error = action_pos_error * action_axis_signs

            actions = torch.zeros(env.action_space.shape, device=env_unwrapped.device)
            command_pos_w = target_pos_w
            command_quat_w = target_quat_w
            rot_gain = torch.full_like(axis_angle_error, args_cli.rot_gain)
            rot_gain[polish_state] = args_cli.polish_rot_gain
            rot_gain[settle_state] = args_cli.settle_rot_gain
            rot_clamp = torch.full_like(axis_angle_error, args_cli.rot_clamp)
            rot_clamp[polish_state] = args_cli.polish_rot_clamp
            rot_clamp[settle_state] = args_cli.settle_rot_clamp
            hand_target_pos_w = None
            hand_target_quat_w = None
            joint_pos_des = None
            joint_pos_des_raw = None
            abs_pos_step_limit = torch.full_like(pos_error, args_cli.abs_pos_step)
            if args_cli.insert_pos_step is not None and insert_mask.any():
                abs_pos_step_limit[insert_mask] = args_cli.insert_pos_step
            abs_rot_step_limit = torch.full(
                (axis_angle_error.shape[0], 1),
                args_cli.abs_rot_step,
                dtype=axis_angle_error.dtype,
                device=axis_angle_error.device,
            )
            if args_cli.insert_rot_step is not None and insert_mask.any():
                abs_rot_step_limit[insert_mask] = args_cli.insert_rot_step

            if scripted_control_mode == "joint-ik":
                if args_cli.position_control_mode != "direct":
                    raise ValueError("calibrated position control is not supported for joint-ik scripted control")
                assert diff_ik_controller is not None
                assert robot_entity_cfg is not None
                assert ee_jacobi_idx is not None
                if args_cli.abs_control_mode == "waypoint":
                    command_pos_w = action_pos_w + _clamp_actions(pos_error, abs_pos_step_limit)
                    axis_angle_norm = torch.linalg.norm(axis_angle_error, dim=-1, keepdim=True)
                    axis_angle_scale = torch.clamp(
                        abs_rot_step_limit / torch.clamp(axis_angle_norm, min=1.0e-8),
                        max=1.0,
                    )
                    command_quat_w = _normalize_quat(
                        _quat_multiply(action_quat_w, _axis_angle_to_quat(axis_angle_error * axis_angle_scale))
                    )
                if args_cli.rotate_control_mode == "stateful-waypoint" and rotate_only_mask.any():
                    rotate_command_valid &= rotate_only_mask
                    rotate_command_seed_mask = rotate_only_mask & ~rotate_command_valid
                    if rotate_command_seed_mask.any():
                        rotate_command_quat_w[rotate_command_seed_mask] = action_quat_w[rotate_command_seed_mask]
                    rotate_command_valid[rotate_only_mask] = True
                    rotate_command_quat_w[rotate_only_mask] = _quat_step_towards(
                        rotate_command_quat_w[rotate_only_mask],
                        target_quat_w[rotate_only_mask],
                        args_cli.abs_rot_step,
                    )
                    command_quat_w[rotate_only_mask] = rotate_command_quat_w[rotate_only_mask]
                elif args_cli.rotate_control_mode == "target" and rotate_quat_hold_mask.any():
                    command_quat_w[rotate_quat_hold_mask] = target_quat_w[rotate_quat_hold_mask]
                elif args_cli.rotate_control_mode == "waypoint" and rotate_only_mask.any():
                    axis_angle_norm = torch.linalg.norm(axis_angle_error, dim=-1, keepdim=True)
                    axis_angle_scale = torch.clamp(
                        args_cli.abs_rot_step / torch.clamp(axis_angle_norm, min=1.0e-8),
                        max=1.0,
                    )
                    command_quat_w[rotate_only_mask] = _normalize_quat(
                        _quat_multiply(
                            action_quat_w,
                            _axis_angle_to_quat(axis_angle_error * axis_angle_scale),
                        )
                    )[rotate_only_mask]

                offset_pos = action_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(action_pos_w.shape[0], 1)
                offset_quat = action_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(action_pos_w.shape[0], 1)
                hand_target_pos_w, hand_target_quat_w = _child_pose_to_parent_pose(
                    command_pos_w,
                    command_quat_w,
                    offset_pos,
                    offset_quat,
                )
                root_pose_w = _as_torch(robot.data.root_pose_w)
                hand_target_pos_b, hand_target_quat_b = subtract_frame_transforms(
                    root_pose_w[:, 0:3],
                    root_pose_w[:, 3:7],
                    hand_target_pos_w,
                    hand_target_quat_w,
                )
                hand_pos_b, hand_quat_b = subtract_frame_transforms(
                    root_pose_w[:, 0:3],
                    root_pose_w[:, 3:7],
                    hand_pos_w,
                    hand_quat_w,
                )
                ik_commands = torch.cat((hand_target_pos_b, hand_target_quat_b), dim=-1)
                diff_ik_controller.set_command(ik_commands)
                joint_ids = torch.as_tensor(
                    robot_entity_cfg.joint_ids,
                    device=env_unwrapped.device,
                    dtype=torch.long,
                )
                jacobians = _as_torch(robot.root_physx_view.get_jacobians())
                jacobian = jacobians[:, ee_jacobi_idx, :, :].index_select(-1, joint_ids)
                joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, joint_ids)
                joint_pos_des_raw = diff_ik_controller.compute(hand_pos_b, hand_quat_b, jacobian, joint_pos)
                joint_pos_des = _clamp_joint_targets(
                    robot,
                    joint_ids,
                    joint_pos,
                    joint_pos_des_raw,
                    args_cli.joint_ik_step,
                    args_cli.joint_limit_margin,
                )
                actions[:, :7] = joint_pos_des
                selected_candidate_idxs = None
            elif action_dim == 7:
                if args_cli.position_control_mode != "direct":
                    raise ValueError("calibrated position control is only supported for 6D relative IK actions")
                selected_candidate_idxs = None
                if args_cli.abs_control_mode == "waypoint":
                    command_pos_w = action_pos_w + _clamp_actions(pos_error, abs_pos_step_limit)
                    axis_angle_norm = torch.linalg.norm(axis_angle_error, dim=-1, keepdim=True)
                    axis_angle_scale = torch.clamp(
                        abs_rot_step_limit / torch.clamp(axis_angle_norm, min=1.0e-8),
                        max=1.0,
                    )
                    command_quat_w = _normalize_quat(
                        _quat_multiply(action_quat_w, _axis_angle_to_quat(axis_angle_error * axis_angle_scale))
                    )
                if args_cli.rotate_control_mode == "stateful-waypoint" and rotate_only_mask.any():
                    rotate_command_valid &= rotate_only_mask
                    rotate_command_seed_mask = rotate_only_mask & ~rotate_command_valid
                    if rotate_command_seed_mask.any():
                        rotate_command_quat_w[rotate_command_seed_mask] = action_quat_w[rotate_command_seed_mask]
                    rotate_command_valid[rotate_only_mask] = True
                    rotate_command_quat_w[rotate_only_mask] = _quat_step_towards(
                        rotate_command_quat_w[rotate_only_mask],
                        target_quat_w[rotate_only_mask],
                        args_cli.abs_rot_step,
                    )
                    command_quat_w[rotate_only_mask] = rotate_command_quat_w[rotate_only_mask]
                elif args_cli.rotate_control_mode == "target" and rotate_quat_hold_mask.any():
                    command_quat_w[rotate_quat_hold_mask] = target_quat_w[rotate_quat_hold_mask]
                elif args_cli.rotate_control_mode == "waypoint" and rotate_only_mask.any():
                    axis_angle_norm = torch.linalg.norm(axis_angle_error, dim=-1, keepdim=True)
                    axis_angle_scale = torch.clamp(
                        args_cli.abs_rot_step / torch.clamp(axis_angle_norm, min=1.0e-8),
                        max=1.0,
                    )
                    command_quat_w[rotate_only_mask] = _normalize_quat(
                        _quat_multiply(
                            action_quat_w,
                            _axis_angle_to_quat(axis_angle_error * axis_angle_scale),
                        )
                    )[rotate_only_mask]
                actions[:, :3] = command_pos_w
                actions[:, 3:7] = command_quat_w
            elif args_cli.position_control_mode == "calibrated-onehot":
                assert calibrated_candidate_actions is not None
                assert calibrated_candidate_deltas is not None
                predicted_next_errors = signed_action_pos_error[:, None, :] - calibrated_candidate_deltas[None, :, :]
                selected_candidate_idxs = torch.argmin(torch.linalg.norm(predicted_next_errors, dim=-1), dim=1)
                actions[:, :3] = calibrated_candidate_actions[selected_candidate_idxs]
                actions[:, 3:6] = _clamp_actions(rot_gain * axis_angle_error, rot_clamp)
            else:
                selected_candidate_idxs = None
                actions[:, :3] = _clamp_actions(args_cli.pos_gain * signed_action_pos_error, args_cli.pos_clamp)
                actions[:, 3:6] = _clamp_actions(rot_gain * axis_angle_error, rot_clamp)

            if action_dim == 6 and polish_only.any():
                actions[polish_only, :2] = _clamp_actions(
                    args_cli.polish_pos_gain * signed_action_pos_error[polish_only, :2],
                    args_cli.polish_pos_clamp,
                )
                actions[polish_only, 2] = 0.0
                actions[polish_only, 3:6] = _clamp_actions(
                    args_cli.polish_rot_gain * axis_angle_error[polish_only],
                    args_cli.polish_rot_clamp,
                )

            if action_dim == 6 and settle_state.any():
                actions[settle_state, :2] = _clamp_actions(
                    args_cli.settle_pos_gain * signed_action_pos_error[settle_state, :2],
                    args_cli.settle_pos_clamp,
                )
                actions[settle_state, 2] = _clamp_actions(
                    args_cli.settle_z_gain * signed_action_pos_error[settle_state, 2],
                    args_cli.settle_z_clamp,
                )
                actions[settle_state, 3:6] = _clamp_actions(
                    args_cli.settle_rot_gain * axis_angle_error[settle_state],
                    args_cli.settle_rot_clamp,
                )

            if step < args_cli.debug_action_steps:
                print(
                    f"[ACTION-DEBUG] step={step:04d} "
                    f"action_pos={action_pos_w[0].tolist()} "
                    f"socket_pos={socket_pos_w[0].tolist()} "
                    f"approach_pos={approach_pos_w[0].tolist()} "
                    f"target_pos={target_pos_w[0].tolist()} "
                    f"command_pos={command_pos_w[0].tolist()} "
                    f"pos_error={pos_error[0].tolist()} "
                    f"controller_lateral_error={controller_lateral_error[0].item():.6f} "
                    f"action_pos_error={action_pos_error[0].tolist()} "
                    f"signed_action_pos_error={signed_action_pos_error[0].tolist()} "
                    f"axis_angle_error={axis_angle_error[0].tolist()} "
                    f"action_dim={action_dim} "
                    f"scripted_control_mode={scripted_control_mode} "
                    f"position_control_mode={args_cli.position_control_mode} "
                    f"abs_control_mode={args_cli.abs_control_mode} "
                    f"staged_approach={args_cli.staged_approach} "
                    f"selected_calibrated_action="
                    f"{calibrated_candidate_names[int(selected_candidate_idxs[0].item())] if selected_candidate_idxs is not None else None} "
                    f"raw_action={actions[0].tolist()} "
                    f"hand_target_pos={hand_target_pos_w[0].tolist() if hand_target_pos_w is not None else None} "
                    f"joint_pos_des_raw={joint_pos_des_raw[0].tolist() if joint_pos_des_raw is not None else None} "
                    f"joint_pos_des={joint_pos_des[0].tolist() if joint_pos_des is not None else None}",
                    flush=True,
                )

            env.step(actions)

            lateral, axial, rot = mdp.insertion_metrics(env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)
            success = mdp.insertion_success(env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)
            post_hand_pos_w, post_hand_quat_w = _hand_pose_w(env_unwrapped, body_idx)
            post_action_pos_w, post_action_quat_w = _action_frame_pose_w(env_unwrapped, body_idx)
            post_physical_tip_pos_w, post_physical_tip_quat_w = _physical_peg_tip_pose_w(env_unwrapped)
            post_socket_pos_w, post_socket_quat_w = _socket_pose_w(env_unwrapped)
            post_physical_tip_rel_socket_pos, _ = subtract_frame_transforms(
                post_socket_pos_w,
                post_socket_quat_w,
                post_physical_tip_pos_w,
                post_physical_tip_quat_w,
            )
            post_action_tip_alignment = torch.linalg.norm(post_physical_tip_pos_w - post_action_pos_w, dim=1)
            success_xy_ready = lateral < SOCKET_SUCCESS_XY_TOLERANCE_M
            success_axial_ready = axial < SOCKET_SUCCESS_Z_TOLERANCE_M
            success_rot_ready = rot < SOCKET_SUCCESS_ROT_TOLERANCE_RAD
            contact_force_magnitude = None
            contact_force_socket = None
            if contact_sensor_cfg is not None:
                contact_force_magnitude = mdp.peg_contact_force_magnitude(env_unwrapped, sensor_cfg=contact_sensor_cfg)
                contact_force_socket = mdp.peg_contact_force_socket(
                    env_unwrapped,
                    sensor_cfg=contact_sensor_cfg,
                    socket_cfg=socket_cfg,
                    force_scale=1.0,
                )

            if step == 0:
                initial_lateral = lateral.mean().item()
                initial_axial = axial.mean().item()
                initial_rot = rot.mean().item()
                initial_action_tip_alignment = post_action_tip_alignment.mean().item()

            final_lateral = lateral.mean().item()
            final_axial = axial.mean().item()
            final_rot = rot.mean().item()
            final_success = success.float().mean().item()
            final_action_tip_alignment = post_action_tip_alignment.mean().item()
            if final_lateral < best_lateral:
                best_lateral = final_lateral
                best_lateral_step = step
            if final_axial < best_axial:
                best_axial = final_axial
                best_axial_step = step
            if final_rot < best_rot:
                best_rot = final_rot
                best_rot_step = step
            if final_action_tip_alignment < best_action_tip_alignment:
                best_action_tip_alignment = final_action_tip_alignment
                best_action_tip_alignment_step = step
            if contact_force_magnitude is not None:
                current_contact_force = contact_force_magnitude.mean().item()
                if current_contact_force > max_contact_force_magnitude:
                    max_contact_force_magnitude = current_contact_force
                    max_contact_force_magnitude_step = step

            if step % 25 == 0 or step == args_cli.steps - 1:
                print(
                    f"[SCRIPTED] step={step:04d} lateral={final_lateral:.4f} axial={final_axial:.4f} "
                    f"rot={final_rot:.4f} success_rate={final_success:.3f} "
                    f"success_xyzr={success_xy_ready.float().mean().item():.0f}/"
                    f"{success_axial_ready.float().mean().item():.0f}/"
                    f"{success_rot_ready.float().mean().item():.0f} "
                    f"contact_force="
                    f"{contact_force_magnitude.mean().item() if contact_force_magnitude is not None else 0.0:.3f} "
                    f"action_tip_alignment={final_action_tip_alignment:.4f} "
                    f"position_ready={position_ready.float().mean().item():.3f} "
                    f"xy_ready={xy_state.float().mean().item():.3f} "
                    f"rotate_ready={rotate_state.float().mean().item():.3f} "
                    f"insert_ready={insert_mask.float().mean().item():.3f} "
                    f"polish_ready={polish_only.float().mean().item():.3f} "
                    f"settle_ready={settle_state.float().mean().item():.3f}",
                    flush=True,
                )

            if args_cli.trace_json:
                if settle_state[0].item():
                    phase = "settle"
                elif polish_only[0].item():
                    phase = "polish"
                elif insert_mask[0].item():
                    phase = "insert"
                elif rotate_state[0].item():
                    phase = "rotate"
                elif xy_state[0].item():
                    phase = "descend"
                else:
                    phase = "reach"
                trace_rows.append(
                    {
                        "step": step,
                        "phase": phase,
                        "hand_pos_w": hand_pos_w[0].detach().cpu().tolist(),
                        "hand_quat_w": hand_quat_w[0].detach().cpu().tolist(),
                        "action_pos_w": action_pos_w[0].detach().cpu().tolist(),
                        "action_quat_w": action_quat_w[0].detach().cpu().tolist(),
                        "physical_tip_pos_w": physical_tip_pos_w[0].detach().cpu().tolist(),
                        "physical_tip_quat_w": physical_tip_quat_w[0].detach().cpu().tolist(),
                        "physical_tip_rel_socket_pos": physical_tip_rel_socket_pos[0].detach().cpu().tolist(),
                        "action_to_physical_tip_delta_w": (
                            physical_tip_pos_w[0] - action_pos_w[0]
                        ).detach().cpu().tolist(),
                        "action_tip_alignment": action_tip_alignment[0].item(),
                        "post_hand_pos_w": post_hand_pos_w[0].detach().cpu().tolist(),
                        "post_hand_quat_w": post_hand_quat_w[0].detach().cpu().tolist(),
                        "post_action_pos_w": post_action_pos_w[0].detach().cpu().tolist(),
                        "post_action_quat_w": post_action_quat_w[0].detach().cpu().tolist(),
                        "post_physical_tip_pos_w": post_physical_tip_pos_w[0].detach().cpu().tolist(),
                        "post_physical_tip_quat_w": post_physical_tip_quat_w[0].detach().cpu().tolist(),
                        "post_physical_tip_rel_socket_pos": post_physical_tip_rel_socket_pos[0].detach().cpu().tolist(),
                        "post_socket_pos_w": post_socket_pos_w[0].detach().cpu().tolist(),
                        "post_socket_quat_w": post_socket_quat_w[0].detach().cpu().tolist(),
                        "post_action_to_physical_tip_delta_w": (
                            post_physical_tip_pos_w[0] - post_action_pos_w[0]
                        ).detach().cpu().tolist(),
                        "post_action_tip_alignment": post_action_tip_alignment[0].item(),
                        "controller_lateral_error": controller_lateral_error[0].item(),
                        "socket_pos_w": socket_pos_w[0].detach().cpu().tolist(),
                        "socket_quat_w": socket_quat_w[0].detach().cpu().tolist(),
                        "target_action_pos_w": target_action_pos_w[0].detach().cpu().tolist(),
                        "target_action_quat_w": target_action_quat_w[0].detach().cpu().tolist(),
                        "approach_pos_w": approach_pos_w[0].detach().cpu().tolist(),
                        "rotate_hold_pos_w": rotate_hold_pos_w[0].detach().cpu().tolist(),
                        "rotate_hold_valid": bool(rotate_hold_valid[0].item()),
                        "rotate_command_quat_w": rotate_command_quat_w[0].detach().cpu().tolist(),
                        "rotate_command_valid": bool(rotate_command_valid[0].item()),
                        "target_pos_w": target_pos_w[0].detach().cpu().tolist(),
                        "target_quat_w": target_quat_w[0].detach().cpu().tolist(),
                        "command_pos_w": command_pos_w[0].detach().cpu().tolist(),
                        "command_quat_w": command_quat_w[0].detach().cpu().tolist(),
                        "hand_target_pos_w": (
                            hand_target_pos_w[0].detach().cpu().tolist() if hand_target_pos_w is not None else None
                        ),
                        "hand_target_quat_w": (
                            hand_target_quat_w[0].detach().cpu().tolist() if hand_target_quat_w is not None else None
                        ),
                        "joint_pos_des": joint_pos_des[0].detach().cpu().tolist() if joint_pos_des is not None else None,
                        "joint_pos_des_raw": (
                            joint_pos_des_raw[0].detach().cpu().tolist() if joint_pos_des_raw is not None else None
                        ),
                        "pos_error": pos_error[0].detach().cpu().tolist(),
                        "axis_angle_error": axis_angle_error[0].detach().cpu().tolist(),
                        "axis_angle_error_norm": torch.linalg.norm(axis_angle_error[0]).item(),
                        "rotate_only": bool(rotate_only_mask[0].item()),
                        "rotate_quat_hold": bool(rotate_quat_hold_mask[0].item()),
                        "rotate_control_mode": args_cli.rotate_control_mode,
                        "insert_xy_tolerance": insert_xy_tolerance,
                        "insert_rot_tolerance": insert_rot_tolerance,
                        "insert_abort_xy_tolerance": insert_abort_xy_tolerance,
                        "insert_abort_rot_tolerance": insert_abort_rot_tolerance,
                        "insert_xy_ready": bool(insert_xy_ready[0].item()),
                        "insert_orientation_ready": bool(insert_orientation_ready[0].item()),
                        "insert_entry": bool(insert_entry_mask[0].item()),
                        "insert_abort_violation": bool(insert_abort_violation_mask[0].item()),
                        "insert_abort_count": int(insert_abort_counts[0].item()),
                        "insert_abort_grace_steps": insert_abort_grace_steps,
                        "insert_aborted": bool(insert_abort_mask[0].item()),
                        "insert_state": bool(insert_state[0].item()),
                        "socket_guide_clearance": SOCKET_GUIDE_CLEARANCE_M,
                        "success_xy_tolerance": SOCKET_SUCCESS_XY_TOLERANCE_M,
                        "success_z_tolerance": SOCKET_SUCCESS_Z_TOLERANCE_M,
                        "success_rot_tolerance": SOCKET_SUCCESS_ROT_TOLERANCE_RAD,
                        "success_xy_ready": bool(success_xy_ready[0].item()),
                        "success_axial_ready": bool(success_axial_ready[0].item()),
                        "success_rot_ready": bool(success_rot_ready[0].item()),
                        "success_xy_margin": lateral[0].item() - SOCKET_SUCCESS_XY_TOLERANCE_M,
                        "success_axial_margin": axial[0].item() - SOCKET_SUCCESS_Z_TOLERANCE_M,
                        "success_rot_margin": rot[0].item() - SOCKET_SUCCESS_ROT_TOLERANCE_RAD,
                        "contact_force_magnitude": (
                            contact_force_magnitude[0].item() if contact_force_magnitude is not None else None
                        ),
                        "contact_force_socket": (
                            contact_force_socket[0].detach().cpu().tolist() if contact_force_socket is not None else None
                        ),
                        "raw_action": actions[0].detach().cpu().tolist(),
                        "lateral": lateral[0].item(),
                        "axial": axial[0].item(),
                        "rot": rot[0].item(),
                        "success": bool(success[0].item()),
                        "position_ready": bool(position_ready[0].item()),
                        "orientation_ready": bool(orientation_ready[0].item()),
                        "xy_state": bool(xy_state[0].item()),
                        "rotate_state": bool(rotate_state[0].item()),
                        "insert_mask": bool(insert_mask[0].item()),
                        "polish_state": bool(polish_state[0].item()),
                        "settle_state": bool(settle_state[0].item()),
                    }
                )

            if success.any():
                success_step = step
                print(f"[SCRIPTED] success reached at step={step:04d}", flush=True)
                break

        env.close()
        summary = {
            "task": args_cli.task,
            "seed": args_cli.seed,
            "steps_requested": args_cli.steps,
            "success_step": success_step,
            "initial_lateral": initial_lateral,
            "final_lateral": final_lateral,
            "initial_axial": initial_axial,
            "final_axial": final_axial,
            "initial_rot": initial_rot,
            "final_rot": final_rot,
            "final_success_rate": final_success,
            "best_lateral": best_lateral,
            "best_lateral_step": best_lateral_step,
            "best_axial": best_axial,
            "best_axial_step": best_axial_step,
            "best_rot": best_rot,
            "best_rot_step": best_rot_step,
            "initial_action_tip_alignment": initial_action_tip_alignment,
            "final_action_tip_alignment": final_action_tip_alignment,
            "best_action_tip_alignment": best_action_tip_alignment,
            "best_action_tip_alignment_step": best_action_tip_alignment_step,
            "video_backend": args_cli.video_backend if args_cli.video else None,
            "video_folder": video_folder,
            "coupled_approach": args_cli.coupled_approach,
            "staged_approach": args_cli.staged_approach,
            "rotate_before_descend": args_cli.rotate_before_descend,
            "action_axis_signs": list(args_cli.action_axis_signs),
            "action_dim": action_dim,
            "scripted_control_mode": scripted_control_mode,
            "position_control_mode": args_cli.position_control_mode,
            "abs_control_mode": args_cli.abs_control_mode,
            "rotate_control_mode": args_cli.rotate_control_mode,
            "insert_xy_tolerance": args_cli.insert_xy_tol if args_cli.insert_xy_tol is not None else args_cli.approach_xy_tol,
            "insert_rot_tolerance": args_cli.insert_rot_tol if args_cli.insert_rot_tol is not None else args_cli.approach_rot_tol,
            "insert_abort_xy_tolerance": (
                args_cli.insert_abort_xy_tol if args_cli.insert_abort_xy_tol is not None else args_cli.approach_xy_tol
            ),
            "insert_abort_rot_tolerance": (
                args_cli.insert_abort_rot_tol if args_cli.insert_abort_rot_tol is not None else args_cli.approach_rot_tol
            ),
            "insert_abort_grace_steps": max(1, args_cli.insert_abort_grace_steps),
            "insert_pos_step": args_cli.insert_pos_step if args_cli.insert_pos_step is not None else args_cli.abs_pos_step,
            "insert_rot_step": args_cli.insert_rot_step if args_cli.insert_rot_step is not None else args_cli.abs_rot_step,
            "success_xy_tolerance": SOCKET_SUCCESS_XY_TOLERANCE_M,
            "success_z_tolerance": SOCKET_SUCCESS_Z_TOLERANCE_M,
            "success_rot_tolerance": SOCKET_SUCCESS_ROT_TOLERANCE_RAD,
            "socket_guide_clearance": SOCKET_GUIDE_CLEARANCE_M,
            "max_contact_force_magnitude": max_contact_force_magnitude,
            "max_contact_force_magnitude_step": max_contact_force_magnitude_step,
            "position_response_json": args_cli.position_response_json,
            "joint_ik_step": args_cli.joint_ik_step,
            "joint_limit_margin": args_cli.joint_limit_margin,
            "deterministic_reset": args_cli.deterministic_reset,
            "socket_pos_override": list(args_cli.socket_pos) if args_cli.socket_pos is not None else None,
            "trace_json": os.path.abspath(args_cli.trace_json) if args_cli.trace_json else None,
        }
        print(
            "[SCRIPTED] summary "
            f"seed={summary['seed']} "
            f"initial_lateral={summary['initial_lateral']:.4f} final_lateral={summary['final_lateral']:.4f} "
            f"initial_axial={summary['initial_axial']:.4f} final_axial={summary['final_axial']:.4f} "
            f"initial_rot={summary['initial_rot']:.4f} final_rot={summary['final_rot']:.4f} "
            f"best_lateral={summary['best_lateral']:.4f}@{summary['best_lateral_step']} "
            f"best_axial={summary['best_axial']:.4f}@{summary['best_axial_step']} "
            f"best_rot={summary['best_rot']:.4f}@{summary['best_rot_step']} "
            f"best_action_tip_alignment={summary['best_action_tip_alignment']:.4f}@"
            f"{summary['best_action_tip_alignment_step']} "
            f"max_contact_force={summary['max_contact_force_magnitude']:.3f}@"
            f"{summary['max_contact_force_magnitude_step']} "
            f"final_success_rate={summary['final_success_rate']:.3f} "
            f"success_step={summary['success_step']}",
            flush=True,
        )
        if args_cli.summary_json:
            summary_path = os.path.abspath(args_cli.summary_json)
            os.makedirs(os.path.dirname(summary_path), exist_ok=True)
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, sort_keys=True)
            print(f"[SCRIPTED] wrote summary to {summary_path}", flush=True)
        if args_cli.trace_json:
            trace_path = os.path.abspath(args_cli.trace_json)
            os.makedirs(os.path.dirname(trace_path), exist_ok=True)
            with open(trace_path, "w", encoding="utf-8") as f:
                json.dump({"summary": summary, "steps": trace_rows}, f, indent=2, sort_keys=True)
            print(f"[SCRIPTED] wrote trace to {trace_path}", flush=True)


if __name__ == "__main__":
    main()
