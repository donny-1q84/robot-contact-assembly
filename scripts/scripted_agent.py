"""Run a simple scripted peg-in-hole baseline for the robot_contact_assembly Isaac Lab task."""

from __future__ import annotations

import argparse
import atexit
from contextlib import contextmanager
import faulthandler
import json
import os
import signal
import sys

import gymnasium as gym
import torch
import warp as wp

from socket_insertion_servo_logic import SocketInsertionServoConfig, compute_socket_insertion_servo_offset

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


def _close_ignoring_system_exit(close_fn, label: str) -> None:
    try:
        close_fn()
    except SystemExit as exc:
        print(f"[WARN]: Ignoring SystemExit while closing {label}: {exc!r}", file=sys.stderr, flush=True)


def _write_json_atomic(path: str, payload: object) -> None:
    abs_path = os.path.abspath(path)
    parent = os.path.dirname(abs_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = f"{abs_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
    os.replace(tmp_path, abs_path)


def _write_rollout_artifacts(
    *,
    summary_json: str | None,
    trace_json: str | None,
    summary: dict,
    trace_rows: list[dict],
    label: str,
) -> None:
    if summary_json:
        summary_path = os.path.abspath(summary_json)
        _write_json_atomic(summary_path, summary)
        print(f"[SCRIPTED] wrote {label} summary to {summary_path}", flush=True)
    if trace_json:
        trace_path = os.path.abspath(trace_json)
        _write_json_atomic(trace_path, {"summary": summary, "steps": trace_rows})
        print(f"[SCRIPTED] wrote {label} trace to {trace_path}", flush=True)


def _should_autoflush_trace(step: int, interval: int) -> bool:
    if interval <= 0:
        return False
    return step < 5 or step % interval == 0


def _append_jsonl(path: str | None, payload: dict) -> None:
    if not path:
        return
    abs_path = os.path.abspath(path)
    parent = os.path.dirname(abs_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(abs_path, "a", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())


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
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)


def _clamp_actions(values: torch.Tensor, limit: torch.Tensor | float) -> torch.Tensor:
    return torch.clamp(values, min=-limit, max=limit)


def _limit_position_step(error: torch.Tensor, limit: torch.Tensor | float, mode: str) -> torch.Tensor:
    if mode == "component":
        return _clamp_actions(error, limit)
    if mode != "norm":
        raise ValueError(f"unsupported position step mode: {mode}")
    if isinstance(limit, torch.Tensor):
        step_limit = torch.amin(torch.abs(limit), dim=-1, keepdim=True)
    else:
        step_limit = torch.full(
            error.shape[:-1] + (1,),
            abs(float(limit)),
            dtype=error.dtype,
            device=error.device,
        )
    error_norm = torch.linalg.norm(error, dim=-1, keepdim=True)
    scale = torch.clamp(step_limit / torch.clamp(error_norm, min=1.0e-8), max=1.0)
    return error * scale


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


def _parse_joint_pos_overrides(value: str) -> dict[str, float]:
    overrides: dict[str, float] = {}
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise argparse.ArgumentTypeError("expected comma-separated joint=value entries")
        name, raw_value = (item.strip() for item in part.split("=", 1))
        if not name:
            raise argparse.ArgumentTypeError("joint name cannot be empty")
        try:
            overrides[name] = float(raw_value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"joint override for {name} must be numeric") from exc
    if not overrides:
        raise argparse.ArgumentTypeError("at least one joint override is required")
    return overrides


def _quat_multiply(lhs: torch.Tensor, rhs: torch.Tensor) -> torch.Tensor:
    """Hamilton product for Isaac Lab WXYZ quaternions."""

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


def _normalize_quat(quat: torch.Tensor) -> torch.Tensor:
    return quat / torch.clamp(torch.linalg.norm(quat, dim=-1, keepdim=True), min=1.0e-8)


def _quat_conjugate(quat: torch.Tensor) -> torch.Tensor:
    return torch.cat((quat[..., :1], -quat[..., 1:]), dim=-1)


def _quat_rotate(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    zeros = torch.zeros(vec.shape[:-1] + (1,), device=vec.device, dtype=vec.dtype)
    vec_quat = torch.cat((zeros, vec), dim=-1)
    rotated = _quat_multiply(_quat_multiply(quat, vec_quat), _quat_conjugate(quat))
    return rotated[..., 1:]


def _quat_multiply_xyzw(lhs: torch.Tensor, rhs: torch.Tensor) -> torch.Tensor:
    """Hamilton product for Isaac Lab transform outputs observed as XYZW."""

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


def _quat_conjugate_xyzw(quat: torch.Tensor) -> torch.Tensor:
    return torch.cat((-quat[..., :3], quat[..., 3:]), dim=-1)


def _quat_rotate_xyzw(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    zeros = torch.zeros(vec.shape[:-1] + (1,), device=vec.device, dtype=vec.dtype)
    vec_quat = torch.cat((vec, zeros), dim=-1)
    rotated = _quat_multiply_xyzw(_quat_multiply_xyzw(quat, vec_quat), _quat_conjugate_xyzw(quat))
    return rotated[..., :3]


def _quat_multiply_wxyz(lhs: torch.Tensor, rhs: torch.Tensor) -> torch.Tensor:
    """Hamilton product for Isaac Lab WXYZ quaternions."""

    return _quat_multiply(lhs, rhs)


def _quat_conjugate_wxyz(quat: torch.Tensor) -> torch.Tensor:
    return _quat_conjugate(quat)


def _quat_rotate_wxyz(quat: torch.Tensor, vec: torch.Tensor) -> torch.Tensor:
    """Rotate local-frame vectors into world frame using Isaac Lab WXYZ quaternions."""

    return _quat_rotate(quat, vec)


def _normalize_vectors(vec: torch.Tensor) -> torch.Tensor:
    return vec / torch.clamp(torch.linalg.norm(vec, dim=-1, keepdim=True), min=1.0e-8)


def _orthogonal_unit_vector(vec: torch.Tensor) -> torch.Tensor:
    x_basis = torch.zeros_like(vec)
    x_basis[..., 0] = 1.0
    y_basis = torch.zeros_like(vec)
    y_basis[..., 1] = 1.0
    basis = torch.where(torch.abs(vec[..., :1]) < 0.9, x_basis, y_basis)
    return _normalize_vectors(torch.cross(vec, basis, dim=-1))


def _quat_from_two_vectors(source: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    source = _normalize_vectors(source)
    target = _normalize_vectors(target)
    dot = torch.sum(source * target, dim=-1, keepdim=True).clamp(min=-1.0, max=1.0)
    axis = torch.cross(source, target, dim=-1)
    quat = torch.cat((1.0 + dot, axis), dim=-1)
    opposite_mask = dot.squeeze(-1) < -0.999999
    if opposite_mask.any():
        quat[opposite_mask, 0] = 0.0
        quat[opposite_mask, 1:] = _orthogonal_unit_vector(source[opposite_mask])
    return _normalize_quat(quat)


def _axis_align_quat(
    current_quat_w: torch.Tensor,
    socket_quat_w: torch.Tensor,
    axis_local: torch.Tensor,
    *,
    sign_invariant: bool,
) -> torch.Tensor:
    current_axis_w = _normalize_vectors(_quat_rotate(current_quat_w, axis_local))
    socket_axis_w = _normalize_vectors(_quat_rotate(socket_quat_w, axis_local))
    if sign_invariant:
        same_direction = torch.sum(current_axis_w * socket_axis_w, dim=-1, keepdim=True) >= 0.0
        socket_axis_w = torch.where(same_direction, socket_axis_w, -socket_axis_w)
    delta_quat_w = _quat_from_two_vectors(current_axis_w, socket_axis_w)
    return _normalize_quat(_quat_multiply(delta_quat_w, current_quat_w))


def _child_pose_to_parent_pose_xyzw(
    child_pos_w: torch.Tensor,
    child_quat_w: torch.Tensor,
    offset_pos: torch.Tensor,
    offset_quat: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Invert `child = parent * offset` for IsaacLab transform quats stored as XYZW.

    This helper remains only for the diagnosed action-frame path where
    ``combine_frame_transforms(hand, offset)`` behaved like XYZW when fed the
    existing stored four-tuples. Remote action-response evidence still showed
    large off-axis motion after this inverse, so passing through this helper is
    not a semantic-control proof by itself.
    """

    inv_offset_quat = _quat_conjugate_xyzw(offset_quat)
    inv_offset_pos = _quat_rotate_xyzw(inv_offset_quat, -offset_pos)
    parent_pos_w = child_pos_w + _quat_rotate_xyzw(child_quat_w, inv_offset_pos)
    parent_quat_w = _normalize_quat(_quat_multiply_xyzw(child_quat_w, inv_offset_quat))
    return parent_pos_w, parent_quat_w


def _axis_angle_to_quat(axis_angle: torch.Tensor) -> torch.Tensor:
    angle = torch.linalg.norm(axis_angle, dim=-1, keepdim=True)
    axis = axis_angle / torch.clamp(angle, min=1.0e-8)
    half_angle = 0.5 * angle
    quat = torch.cat((torch.cos(half_angle), axis * torch.sin(half_angle)), dim=-1)
    small_angle = angle.squeeze(-1) < 1.0e-8
    if small_angle.any():
        quat[small_angle] = axis_angle.new_tensor((1.0, 0.0, 0.0, 0.0))
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


def _load_joint_response_matrix(path: str) -> list[list[float]]:
    with open(path, "r", encoding="utf-8") as f:
        summary = json.load(f)
    matrix = summary.get("response_matrix_world_delta_per_joint_rad")
    if not isinstance(matrix, list) or len(matrix) != 3:
        raise ValueError(f"joint-response JSON missing 3-row response matrix: {path}")
    width = None
    rows: list[list[float]] = []
    for row_idx, row in enumerate(matrix):
        if not isinstance(row, list):
            raise ValueError(f"joint-response matrix row {row_idx} is not a list: {path}")
        numeric_row = [float(part) for part in row]
        if width is None:
            width = len(numeric_row)
        if len(numeric_row) != width:
            raise ValueError(f"joint-response matrix row {row_idx} has inconsistent width: {path}")
        rows.append(numeric_row)
    if width != 7:
        raise ValueError(f"joint-response matrix must have 7 joint columns, got {width}: {path}")
    return rows


parser = argparse.ArgumentParser(description="Scripted baseline for robot_contact_assembly Isaac Lab tasks.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=None, help="Override number of environments.")
parser.add_argument("--steps", type=int, default=200, help="Number of env steps to run before exit in headless mode.")
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-IK-Rel-Play-v0", help="Task name.")
parser.add_argument("--seed", type=int, default=42, help="Deterministic seed for the scripted baseline.")
parser.add_argument(
    "--disable-insertion-success-termination",
    dest="disable_insertion_success_termination",
    action="store_true",
    default=True,
    help=(
        "Disable the environment's geometry-only insertion_success termination during scripted validation. "
        "The trace validators apply the stricter contact-aware success gate."
    ),
)
parser.add_argument(
    "--keep-insertion-success-termination",
    dest="disable_insertion_success_termination",
    action="store_false",
    help="Keep the task's built-in insertion_success termination/reset behavior.",
)
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
parser.add_argument(
    "--approach-axis",
    choices=("world-z", "socket"),
    default="world-z",
    help=(
        "Axis used for the pre-insertion approach offset. 'world-z' preserves legacy behavior; "
        "'socket' offsets along the socket-frame insertion axis."
    ),
)
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
    "--success-hold-steps",
    type=int,
    default=1,
    help=(
        "Consecutive success steps to observe before exiting. Values above 1 hold the current action after the "
        "first success so sustained-contact validators can prove the insertion is stable."
    ),
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
    "--rotate-descent-mode",
    choices=("hold", "approach"),
    default="hold",
    help=(
        "In staged rotate-before-descend mode, choose the position target while orientation is still aligning. "
        "'hold' preserves the original behavior by holding the XY-aligned high pose; 'approach' keeps aiming "
        "at the approach-height pose so rotation and controlled descent can happen together."
    ),
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
    "--action-semantics-probe-delta",
    type=_parse_vec3,
    default=None,
    help=(
        "Bypass the staged insertion policy and command this small action-frame position delta every step. "
        "Use with trace-only runs plus scripts/check_scripted_action_response_trace.py to validate a "
        "control interface before spending on a full insertion/video attempt."
    ),
)
parser.add_argument(
    "--action-semantics-probe-frame",
    choices=("world", "socket"),
    default="world",
    help="Coordinate frame for --action-semantics-probe-delta.",
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
    "--joint-response-json",
    type=str,
    default=None,
    help=(
        "Calibration JSON from scripts/calibrate_joint_position_action.py. Required for "
        "--scripted-control-mode joint-response."
    ),
)
parser.add_argument(
    "--joint-response-damping",
    type=float,
    default=1.0e-4,
    help="Damping used by the empirical joint-response minimum-norm inverse.",
)
parser.add_argument(
    "--joint-response-max-delta",
    type=float,
    default=0.040,
    help="Maximum absolute per-joint delta produced by --scripted-control-mode joint-response.",
)
parser.add_argument(
    "--debug-action-steps",
    type=int,
    default=0,
    help="Print detailed action-frame diagnostics for the first N control steps.",
)
parser.add_argument(
    "--watchdog_seconds",
    type=int,
    default=int(os.environ.get("RCA_SCRIPTED_WATCHDOG_SECONDS", "0")),
    help="Dump Python tracebacks every N seconds while the scripted rollout is running; 0 disables.",
)
parser.add_argument(
    "--trace-phase-steps",
    type=int,
    default=int(os.environ.get("RCA_TRACE_PHASE_STEPS", "0")),
    help="Write fine-grained JSONL phase markers for the first N control steps; 0 disables.",
)
parser.add_argument(
    "--warmup-steps",
    type=int,
    default=30,
    help="Zero-action settling steps after reset before measuring and applying the scripted controller.",
)
parser.add_argument(
    "--episode-buffer-steps",
    type=int,
    default=20,
    help="Extra environment steps added to the scripted episode horizon after warmup and evaluation steps.",
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
    "--demo-reanchor-socket",
    action="store_true",
    default=False,
    help=(
        "After reset/warmup, move the kinematic socket guide under the current action-frame tip for a "
        "reachable deterministic insertion demo. This is explicit demo instrumentation; default tasks are unchanged."
    ),
)
parser.add_argument(
    "--demo-reanchor-initial-axial",
    type=float,
    default=0.080,
    help="Initial world-Z distance from the current action-frame tip down to the reanchored socket center.",
)
parser.add_argument(
    "--demo-reanchor-orientation",
    choices=("task", "current"),
    default="task",
    help=(
        "Socket-frame orientation for --demo-reanchor-socket. 'task' uses the task's calibrated socket "
        "orientation; 'current' aligns the success frame to the current action-frame orientation."
    ),
)
parser.add_argument(
    "--demo-reanchor-settle-steps",
    type=int,
    default=5,
    help="Zero-action steps after runtime socket reanchor so Isaac scene buffers settle before the rollout.",
)
parser.add_argument(
    "--target-action-pos-offset",
    type=_parse_vec3,
    default=None,
    help=(
        "Add an x,y,z offset to the scripted action-frame target while keeping success metrics measured "
        "against the physical socket. The coordinate frame is selected with --target-action-pos-offset-frame."
    ),
)
parser.add_argument(
    "--target-action-pos-offset-frame",
    choices=("world", "socket"),
    default="world",
    help=(
        "Coordinate frame for --target-action-pos-offset. 'world' preserves legacy diagnostics; 'socket' "
        "applies the offset in the socket frame so compensation follows tilted sockets."
    ),
)
parser.add_argument(
    "--reachable-approach",
    action="store_true",
    default=False,
    help=(
        "Use a stateful pre-insertion XY target that starts outside the socket target and shrinks toward it "
        "only after the current offset target is reached with enough joint-limit margin."
    ),
)
parser.add_argument(
    "--reachable-approach-start-radius",
    type=float,
    default=0.060,
    help="Initial world-XY offset radius in meters for --reachable-approach.",
)
parser.add_argument(
    "--reachable-approach-min-radius",
    type=float,
    default=0.0,
    help="Minimum world-XY offset radius in meters for --reachable-approach.",
)
parser.add_argument(
    "--reachable-approach-shrink-step",
    type=float,
    default=0.002,
    help="Meters by which --reachable-approach shrinks the XY radius after a safe offset target is reached.",
)
parser.add_argument(
    "--reachable-approach-shrink-xy-tol",
    type=float,
    default=0.015,
    help="World-XY tolerance for considering the current reachable-approach offset target reached.",
)
parser.add_argument(
    "--reachable-approach-joint-margin-min",
    type=float,
    default=0.080,
    help=(
        "Minimum previous-step arm joint-limit margin required before reachable-approach shrinks its "
        "offset radius. Use <=0 to ignore joint margin for shrinking."
    ),
)
parser.add_argument(
    "--disable-socket-wall-collisions",
    action="store_true",
    default=False,
    help="Disable guide-wall collision shapes while keeping the socket frame target for contact-blocker diagnostics.",
)
parser.add_argument(
    "--initial-joint-pos",
    type=_parse_joint_pos_overrides,
    default=None,
    help=(
        "Comma-separated joint=value overrides applied to the robot init_state before reset, "
        "for deterministic IK-branch diagnostics, e.g. panda_joint4=-2.6."
    ),
)
parser.add_argument(
    "--abs-control-mode",
    choices=("target", "waypoint"),
    default="target",
    help="For 7D absolute IK actions, command the full target pose or a small absolute waypoint toward it.",
)
parser.add_argument(
    "--mdp-abs-action-frame",
    choices=("root", "world"),
    default="root",
    help=(
        "Frame used when writing native 7D absolute IK MDP actions. Isaac Lab's "
        "DifferentialInverseKinematicsAction expects absolute pose targets in the robot root frame; "
        "'world' keeps the legacy raw world-pose behavior for diagnostics only."
    ),
)
parser.add_argument(
    "--mdp-abs-ik-method",
    choices=("dls", "pinv", "svd", "trans"),
    default=None,
    help=(
        "Override Isaac Lab's native DifferentialInverseKinematicsAction IK method before env creation. "
        "Intended for Abs IK branch diagnostics; omit to keep the task config default."
    ),
)
parser.add_argument(
    "--mdp-abs-orientation-command-mode",
    choices=("target", "current"),
    default="target",
    help=(
        "Orientation command policy for native 7D absolute IK MDP actions. "
        "'target' uses the scripted orientation target; 'current' sends the measured current orientation, "
        "creating a position-only diagnostic while keeping the 7D action interface valid."
    ),
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
    "--orientation-target-mode",
    choices=("socket", "axis-align-current"),
    default="socket",
    help=(
        "Orientation target for the scripted action frame. 'socket' tracks the full socket quaternion; "
        "'axis-align-current' aligns the cylindrical insertion axis while preserving the current twist."
    ),
)
parser.add_argument(
    "--hold-orientation-during-descend",
    action="store_true",
    default=False,
    help=(
        "After staged rotation reaches tolerance, hold the measured orientation while descending to the "
        "approach height. This prioritizes Cartesian descent and avoids over-constraining JointIK."
    ),
)
parser.add_argument(
    "--rotate-xy-retention",
    action="store_true",
    default=False,
    help=(
        "During staged rotate-only alignment, pause rotation and recover XY if the current lateral error "
        "exceeds --rotate-xy-retention-tol."
    ),
)
parser.add_argument(
    "--rotate-xy-retention-tol",
    type=float,
    default=0.012,
    help="Lateral-error threshold that pauses rotate-only alignment for XY recovery.",
)
parser.add_argument(
    "--descend-xy-retention",
    action="store_true",
    default=False,
    help=(
        "During staged descent, hold the current Z/orientation and recover XY if lateral error exceeds "
        "--descend-xy-retention-tol."
    ),
)
parser.add_argument(
    "--descend-xy-retention-tol",
    type=float,
    default=0.012,
    help="Lateral-error threshold that pauses descent for XY recovery.",
)
parser.add_argument(
    "--hold-orientation-during-insert",
    action="store_true",
    default=False,
    help=(
        "Freeze the action-frame orientation at insertion entry instead of continuing to rotate toward the socket "
        "during final descent."
    ),
)
parser.add_argument(
    "--insert-rotation-gated-descent",
    action="store_true",
    default=False,
    help=(
        "During insertion, hold the current Z target whenever orientation error is above "
        "--insert-descent-rot-tol. XY/orientation targets remain active, so the controller can repair rotation "
        "before spending more insertion depth."
    ),
)
parser.add_argument(
    "--insert-descent-rot-tol",
    type=float,
    default=None,
    help=(
        "Orientation-error threshold for --insert-rotation-gated-descent. Defaults to --insert-rot-tol, "
        "or --approach-rot-tol when --insert-rot-tol is unset."
    ),
)
parser.add_argument(
    "--insert-rotation-gate-descent-scale",
    type=float,
    default=0.0,
    help=(
        "When --insert-rotation-gated-descent is active, allow this fraction of the requested Z descent "
        "instead of a full Z hold. The default 0.0 preserves the original hard gate."
    ),
)
parser.add_argument(
    "--insert-rotation-gate-min-descent-step",
    type=float,
    default=0.0,
    help=(
        "Minimum world-Z descent allowed on gated insertion steps when a lower target exists. "
        "Useful for testing a soft rotation gate that keeps making axial progress."
    ),
)
parser.add_argument(
    "--insert-rotation-gate-near-depth-z-tol",
    type=float,
    default=None,
    help=(
        "If set, use the near-depth rotation-gate overrides once axial error is below this threshold. "
        "This keeps early insertion permissive while making redescend stricter near the success Z gate."
    ),
)
parser.add_argument(
    "--insert-rotation-gate-near-depth-rot-tol",
    type=float,
    default=None,
    help="Near-depth override for --insert-descent-rot-tol. Omit to keep the base rotation threshold.",
)
parser.add_argument(
    "--insert-rotation-gate-near-depth-descent-scale",
    type=float,
    default=None,
    help="Near-depth override for --insert-rotation-gate-descent-scale.",
)
parser.add_argument(
    "--insert-rotation-gate-near-depth-min-descent-step",
    type=float,
    default=None,
    help="Near-depth override for --insert-rotation-gate-min-descent-step.",
)
parser.add_argument(
    "--insert-after-alignment",
    action="store_true",
    default=False,
    help=(
        "In staged rotate-before-descend mode, latch insertion as soon as lateral and orientation errors "
        "are within insertion tolerances instead of waiting to reach the approach-height waypoint."
    ),
)
parser.add_argument(
    "--insert-descent-mode",
    choices=("pose-target", "vertical", "joint-cache"),
    default="pose-target",
    help=(
        "Final insertion target strategy. 'pose-target' sends the socket pose as before; 'vertical' commands a "
        "bounded world-Z descent while keeping XY aimed at the socket; 'joint-cache' seeds one local IK "
        "joint-space insertion direction at insertion entry and replays it with joint-space bounds."
    ),
)
parser.add_argument(
    "--insert-vertical-step",
    type=float,
    default=None,
    help="World-Z step for --insert-descent-mode vertical or joint-cache seeding. Defaults to insert-pos-step, then abs-pos-step.",
)
parser.add_argument(
    "--insert-contact-force-aware-xy",
    action="store_true",
    default=False,
    help=(
        "During insertion, add a bounded socket-frame XY correction from measured peg-wall contact force. "
        "This targets the lip-contact failure mode where descent stalls with contact before true centering."
    ),
)
parser.add_argument(
    "--insert-contact-force-min",
    type=float,
    default=0.5,
    help="Minimum peg contact-force magnitude required before insertion force-aware XY correction is active.",
)
parser.add_argument(
    "--insert-contact-force-scale",
    type=float,
    default=10.0,
    help="Force scale passed to peg_contact_force_socket for insertion force-aware XY correction.",
)
parser.add_argument(
    "--insert-contact-force-xy-gain",
    type=float,
    default=0.0015,
    help="Meters of socket-frame XY target offset per scaled contact-force unit during insertion.",
)
parser.add_argument(
    "--insert-contact-force-xy-clamp",
    type=float,
    default=0.0015,
    help="Maximum absolute insertion force-aware XY target offset in meters per socket-frame axis.",
)
parser.add_argument(
    "--insert-contact-force-xy-sign",
    type=float,
    default=1.0,
    help="Sign multiplier for insertion force-aware XY correction. Use -1.0 if trace evidence shows inverted force sign.",
)
parser.add_argument(
    "--final-contact-servo",
    action="store_true",
    default=False,
    help=(
        "Enable a post-smoke final-contact controller that uses the measured physical tip error in the "
        "socket frame for bounded XY centering, then continues a guarded Z descent. This is a semantic "
        "insertion attempt, not a video-only presentation mode."
    ),
)
parser.add_argument(
    "--final-contact-servo-entry-xy-tol",
    type=float,
    default=0.008,
    help="Lateral-error threshold that can enter the final-contact servo state.",
)
parser.add_argument(
    "--final-contact-servo-entry-z-tol",
    type=float,
    default=0.050,
    help="Axial-error threshold that can enter the final-contact servo state.",
)
parser.add_argument(
    "--final-contact-servo-entry-rot-tol",
    type=float,
    default=None,
    help="Orientation-error threshold that can enter final-contact servo. Defaults to active success rot tolerance.",
)
parser.add_argument(
    "--final-contact-servo-exit-xy-tol",
    type=float,
    default=0.012,
    help="Lateral-error threshold that exits final-contact servo before continuing descent.",
)
parser.add_argument(
    "--final-contact-servo-exit-rot-tol",
    type=float,
    default=None,
    help="Orientation-error threshold that exits final-contact servo. Defaults to insert abort rot tolerance.",
)
parser.add_argument(
    "--final-contact-servo-xy-gain",
    type=float,
    default=0.75,
    help="Gain applied to measured physical-tip socket-frame XY error during final-contact servo.",
)
parser.add_argument(
    "--final-contact-servo-xy-clamp",
    type=float,
    default=0.002,
    help="Maximum absolute socket-frame XY correction in meters during final-contact servo.",
)
parser.add_argument(
    "--final-contact-servo-metric-error",
    action="store_true",
    default=False,
    help=(
        "Drive final-contact XYZ corrections from mdp.tip_to_socket_position(), the same signed "
        "socket-frame metric used by the insertion success checker. When disabled, the legacy "
        "controller uses the debug physical-tip transform for XY and a world-Z descent."
    ),
)
parser.add_argument(
    "--final-contact-servo-metric-xy",
    action="store_true",
    default=False,
    help=(
        "Use mdp.tip_to_socket_position() only for final-contact XY centering while leaving axial "
        "motion under the legacy world-Z descent, metric-z, or hold-Z policy. This targets traces "
        "where the legacy physical-tip XY source is nearly zero but the task success metric still "
        "reports a lateral miss."
    ),
)
parser.add_argument(
    "--final-contact-servo-metric-z",
    action="store_true",
    default=False,
    help=(
        "Use mdp.tip_to_socket_position() only for the final-contact axial correction while keeping "
        "legacy physical-tip XY centering. This targets traces where XY converges but world-Z descent "
        "moves past the checker's signed axial metric."
    ),
)
parser.add_argument(
    "--final-contact-servo-z-gain",
    type=float,
    default=1.0,
    help=(
        "Gain applied to signed socket-frame axial error when --final-contact-servo-metric-error or "
        "--final-contact-servo-metric-z is active."
    ),
)
parser.add_argument(
    "--final-contact-servo-z-step",
    type=float,
    default=0.002,
    help=(
        "Maximum axial correction per final-contact servo command in meters. This is a world-Z descent "
        "in legacy mode and a socket-frame signed Z correction in metric-error or metric-z mode."
    ),
)
parser.add_argument(
    "--final-contact-servo-hold-z-when-axial-ready",
    action="store_true",
    default=False,
    help=(
        "In legacy final-contact servo mode, stop the guarded world-Z descent while the task axial "
        "metric is already inside the success window but XY is not yet ready. This targets traces "
        "where axial and XY success windows occur at different times."
    ),
)
parser.add_argument(
    "--final-contact-servo-orientation-mode",
    choices=("current", "target", "insert-hold"),
    default="current",
    help=(
        "Orientation target during final-contact servo. 'current' freezes the measured orientation, "
        "'target' tracks the socket target, and 'insert-hold' reuses the insertion-entry hold quaternion."
    ),
)
parser.add_argument(
    "--socket-insertion-servo",
    action="store_true",
    default=False,
    help=(
        "Enable a stateful socket-frame insertion controller after the contact-smoke gate. It uses "
        "the task tip-to-socket metric for XY, gates axial descent on XY+rotation readiness, and "
        "steps orientation toward the socket target instead of freezing it."
    ),
)
parser.add_argument(
    "--socket-insertion-servo-entry-xy-tol",
    type=float,
    default=0.014,
    help="Lateral-error threshold that can enter the socket insertion servo state.",
)
parser.add_argument(
    "--socket-insertion-servo-entry-z-tol",
    type=float,
    default=0.055,
    help="Axial-error threshold that can enter the socket insertion servo state.",
)
parser.add_argument(
    "--socket-insertion-servo-entry-rot-tol",
    type=float,
    default=0.300,
    help="Orientation-error threshold that can enter the socket insertion servo state.",
)
parser.add_argument(
    "--socket-insertion-servo-exit-xy-tol",
    type=float,
    default=0.020,
    help="Lateral-error threshold that exits the socket insertion servo state.",
)
parser.add_argument(
    "--socket-insertion-servo-exit-z-tol",
    type=float,
    default=0.070,
    help="Axial-error threshold that exits the socket insertion servo state.",
)
parser.add_argument(
    "--socket-insertion-servo-exit-rot-tol",
    type=float,
    default=0.500,
    help="Orientation-error threshold that exits the socket insertion servo state.",
)
parser.add_argument(
    "--socket-insertion-servo-strict-exit",
    action="store_true",
    default=False,
    help=(
        "Exit socket insertion servo immediately on the soft exit thresholds. By default soft exits enter "
        "a recovery hold so the controller can re-center instead of falling back to legacy polish."
    ),
)
parser.add_argument(
    "--socket-insertion-servo-hard-exit-xy-tol",
    type=float,
    default=0.080,
    help="Catastrophic lateral-error threshold that exits socket insertion servo even when recovery is enabled.",
)
parser.add_argument(
    "--socket-insertion-servo-hard-exit-z-tol",
    type=float,
    default=0.090,
    help="Catastrophic axial-error threshold that exits socket insertion servo even when recovery is enabled.",
)
parser.add_argument(
    "--socket-insertion-servo-hard-exit-rot-tol",
    type=float,
    default=0.800,
    help="Catastrophic orientation-error threshold that exits socket insertion servo even when recovery is enabled.",
)
parser.add_argument(
    "--socket-insertion-servo-descend-xy-tol",
    type=float,
    default=None,
    help="XY tolerance required before socket-axis descent. Defaults to active success XY tolerance.",
)
parser.add_argument(
    "--socket-insertion-servo-descend-rot-tol",
    type=float,
    default=None,
    help="Rotation tolerance required before socket-axis descent. Defaults to active success rotation tolerance.",
)
parser.add_argument(
    "--socket-insertion-servo-xy-gain",
    type=float,
    default=0.85,
    help="Gain applied to task-metric socket-frame XY error in socket insertion servo.",
)
parser.add_argument(
    "--socket-insertion-servo-xy-clamp",
    type=float,
    default=0.0025,
    help="Maximum absolute socket-frame XY correction per servo step.",
)
parser.add_argument(
    "--socket-insertion-servo-z-gain",
    type=float,
    default=1.0,
    help="Gain applied to signed socket-frame axial error once XY and rotation are ready.",
)
parser.add_argument(
    "--socket-insertion-servo-z-step",
    type=float,
    default=0.0015,
    help="Maximum socket-frame insertion-axis correction per servo step.",
)
parser.add_argument(
    "--socket-insertion-servo-contact-preload-step",
    type=float,
    default=0.0010,
    help="Small socket-frame preload used only when axial is ready but contact evidence is missing.",
)
parser.add_argument(
    "--socket-insertion-servo-maintain-contact-preload",
    action="store_true",
    help=(
        "Continue applying the small socket-frame preload inside the axial success window even when "
        "contact is currently above the success threshold. This is intended for short success-hold "
        "validation windows where pure joint freezing lets the contact force decay."
    ),
)
parser.add_argument(
    "--socket-insertion-servo-contact-boundary-min-force",
    type=float,
    default=0.25,
    help=(
        "Lower decision-time contact-force threshold used only inside the near-axial contact-boundary band. "
        "The task success contact threshold remains --success-min-contact-force."
    ),
)
parser.add_argument(
    "--socket-insertion-servo-contact-boundary-tol",
    type=float,
    default=0.0010,
    help=(
        "Extra axial band above the success threshold where real contact forces make socket insertion "
        "switch from normal descent to a tiny boundary micro-step."
    ),
)
parser.add_argument(
    "--socket-insertion-servo-contact-boundary-step",
    type=float,
    default=0.00015,
    help="Maximum socket-frame Z micro-step while contact is already present near the axial success boundary.",
)
parser.add_argument(
    "--socket-insertion-servo-contact-boundary-xy-gain",
    type=float,
    default=0.0,
    help=(
        "XY gain used while applying contact-boundary micro-steps. Defaults to zero so the controller "
        "does not scrub laterally after guide contact when XY is already inside the descent gate."
    ),
)
parser.add_argument(
    "--socket-insertion-servo-contact-boundary-xy-clamp",
    type=float,
    default=0.0,
    help="XY clamp used with --socket-insertion-servo-contact-boundary-xy-gain.",
)
parser.add_argument(
    "--socket-insertion-servo-rot-step",
    type=float,
    default=0.030,
    help="Maximum stateful quaternion step while socket insertion servo is active.",
)
parser.add_argument(
    "--socket-insertion-servo-rotate-only-when-rot-misaligned",
    action="store_true",
    default=False,
    help=(
        "Hold the current socket-servo orientation once it is already inside the descent rotation tolerance. "
        "This avoids adding contact torque while the peg is already aligned enough to insert."
    ),
)
parser.add_argument(
    "--socket-insertion-servo-rotate-while-xy-misaligned",
    action="store_true",
    default=False,
    help=(
        "Continue stepping orientation while socket-servo XY is outside the descent tolerance. "
        "By default XY recovery holds current orientation to avoid coupling rotation into lateral drift."
    ),
)
parser.add_argument(
    "--joint-cache-step",
    type=float,
    default=None,
    help="Maximum absolute per-joint cached insertion delta. Defaults to --joint-ik-step.",
)
parser.add_argument(
    "--joint-cache-step-scale",
    type=float,
    default=1.0,
    help="Scale applied to the seed IK joint delta before replaying the cached insertion direction.",
)
parser.add_argument(
    "--joint-cache-total-limit",
    type=float,
    default=0.75,
    help="Maximum absolute per-joint deviation from the cached insertion-entry joint posture.",
)
parser.add_argument(
    "--joint-cache-live-polish",
    action="store_true",
    help=(
        "For joint-cache insertion, switch back to live IK once near-contact polish starts. "
        "This lets the controller correct XY/orientation drift instead of replaying the same cached descent."
    ),
)
parser.add_argument(
    "--stop-on-branch-jump",
    action="store_true",
    default=False,
    help="Stop the scripted rollout when an aligned state is followed by a large lateral or orientation jump.",
)
parser.add_argument(
    "--branch-jump-aligned-xy-tol",
    type=float,
    default=0.015,
    help="Lateral threshold used to mark that the rollout has reached a post-alignment state.",
)
parser.add_argument(
    "--branch-jump-aligned-rot-tol",
    type=float,
    default=0.25,
    help="Orientation threshold used to mark that the rollout has reached a post-alignment state.",
)
parser.add_argument(
    "--branch-jump-xy-tol",
    type=float,
    default=0.05,
    help="Post-alignment lateral error threshold that indicates an IK branch jump.",
)
parser.add_argument(
    "--branch-jump-rot-tol",
    type=float,
    default=0.75,
    help="Post-alignment orientation error threshold that indicates an IK branch jump.",
)
parser.add_argument(
    "--scripted-control-mode",
    choices=("auto", "mdp", "joint-ik", "joint-response"),
    default="auto",
    help=(
        "Controller used by the scripted agent. 'mdp' sends actions to the task action term; "
        "'joint-ik' computes joint-position targets with a standalone Jacobian IK pre-controller; "
        "'joint-response' uses an empirically measured JointPositionAction response matrix."
    ),
)
parser.add_argument(
    "--abs-pos-step",
    type=float,
    default=0.025,
    help="Maximum per-axis position step for --abs-control-mode waypoint.",
)
parser.add_argument(
    "--abs-pos-step-mode",
    choices=("component", "norm"),
    default="component",
    help=(
        "How waypoint position steps are limited. 'component' preserves legacy per-axis clamps; "
        "'norm' scales the full Cartesian error vector to preserve its direction."
    ),
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
    "--joint-step-limit-mode",
    choices=("component", "global", "after-xy-global"),
    default="component",
    help=(
        "How --joint-ik-step is applied. 'component' clips each joint independently; "
        "'global' scales the full IK delta to preserve its joint-space direction; "
        "'after-xy-global' uses component clipping for the first XY reach, then global scaling after XY is latched."
    ),
)
parser.add_argument(
    "--joint-limit-margin",
    type=float,
    default=0.02,
    help="Margin in radians kept inside reported joint position limits for joint-IK commands.",
)
parser.add_argument(
    "--insert-joint-limit-margin",
    type=float,
    default=None,
    help=(
        "Optional joint-limit margin used only while insertion/polish/settle/contact-retention is active. "
        "This can keep late descent from spending all remaining elbow margin without constraining the initial reach."
    ),
)
parser.add_argument(
    "--joint-limit-nullspace-gain",
    type=float,
    default=0.0,
    help=(
        "Joint-limit centering gain for the standalone joint-IK controller. Values >0 add a nullspace "
        "joint delta that pushes active joints back toward the middle of their limits without changing the "
        "Cartesian task to first order."
    ),
)
parser.add_argument(
    "--joint-limit-nullspace-activation-margin",
    type=float,
    default=0.20,
    help=(
        "Activate the joint-limit nullspace bias only when a joint is within this many radians of a limit. "
        "Use <=0 to keep the centering bias active everywhere."
    ),
)
parser.add_argument(
    "--joint-limit-nullspace-step",
    type=float,
    default=0.030,
    help="Maximum absolute per-joint nullspace correction added to each standalone joint-IK target step.",
)
parser.add_argument(
    "--joint-limit-nullspace-damping",
    type=float,
    default=0.050,
    help="Damping used when projecting joint-limit centering into the standalone IK Jacobian nullspace.",
)
parser.add_argument(
    "--joint-limit-guard-gain",
    type=float,
    default=0.0,
    help=(
        "Default-off hard joint-limit guard for the standalone IK controller. Values >0 add an unprojected "
        "centering delta before target clamping, useful when the projected nullspace term is too weak near limits."
    ),
)
parser.add_argument(
    "--joint-limit-guard-activation-margin",
    type=float,
    default=0.20,
    help="Activate --joint-limit-guard-gain when a selected joint is within this many radians of a limit.",
)
parser.add_argument(
    "--joint-limit-guard-step",
    type=float,
    default=0.050,
    help="Maximum absolute per-joint hard guard correction added to each standalone joint-IK target step.",
)
parser.add_argument(
    "--trace-json",
    type=str,
    default=None,
    help="Optional path to write per-step controller trace JSON for the first environment.",
)
parser.add_argument(
    "--trace-autoflush-every",
    type=int,
    default=25,
    help=(
        "Write partial summary/trace artifacts during the rollout. The first five control steps always flush; "
        "set <=0 to disable."
    ),
)
parser.add_argument("--polish-xy-tol", type=float, default=0.008, help="Lateral tolerance to enter the near-contact polish phase.")
parser.add_argument("--polish-z-tol", type=float, default=0.012, help="Axial tolerance to enter the near-contact polish phase.")
parser.add_argument(
    "--polish-rot-tol",
    type=float,
    default=None,
    help="Optional orientation tolerance required before entering the near-contact polish phase.",
)
parser.add_argument(
    "--polish-rotation-mode",
    choices=("target", "current", "insert-hold"),
    default="target",
    help=(
        "Orientation target during polish. 'target' rotates toward the socket, 'current' freezes the current "
        "orientation, and 'insert-hold' reuses the insertion-entry orientation when available."
    ),
)
parser.add_argument("--polish-pos-gain", type=float, default=1.2, help="Lateral position gain during the near-contact polish phase.")
parser.add_argument("--polish-pos-clamp", type=float, default=0.008, help="Lateral position clamp during the near-contact polish phase.")
parser.add_argument("--polish-rot-gain", type=float, default=5.0, help="Orientation gain during the near-contact polish phase.")
parser.add_argument("--polish-rot-clamp", type=float, default=0.35, help="Orientation clamp during the near-contact polish phase.")
parser.add_argument(
    "--depth-rotation-polish",
    action="store_true",
    default=False,
    help=(
        "Latch a target-orientation repair phase once insertion depth/contact are ready but rotation is still outside "
        "the success gate. This keeps XY/Z bounded instead of letting the regular insert phase drift laterally."
    ),
)
parser.add_argument(
    "--depth-rotation-polish-xy-tol",
    type=float,
    default=None,
    help="Lateral tolerance to enter depth-rotation polish. Defaults to --success-xy-tol.",
)
parser.add_argument(
    "--depth-rotation-polish-z-tol",
    type=float,
    default=None,
    help="Axial tolerance to enter depth-rotation polish. Defaults to --success-z-tol.",
)
parser.add_argument(
    "--depth-rotation-polish-contact-min-force",
    type=float,
    default=None,
    help="Contact-force threshold to enter depth-rotation polish. Defaults to --success-min-contact-force.",
)
parser.add_argument(
    "--depth-rotation-polish-exit-contact-min-force",
    type=float,
    default=None,
    help=(
        "Exit depth-rotation polish if contact force falls below this value. Omit to keep contact as an entry-only "
        "condition."
    ),
)
parser.add_argument(
    "--depth-rotation-polish-orientation-mode",
    choices=("target", "stateful-waypoint"),
    default="target",
    help=(
        "Quaternion target policy while depth-rotation polish is active. 'target' keeps the legacy per-step target; "
        "'stateful-waypoint' advances a persistent quaternion command toward the target by "
        "--depth-rotation-polish-rot-step."
    ),
)
parser.add_argument(
    "--depth-rotation-polish-exit-xy-tol",
    type=float,
    default=0.012,
    help="Exit depth-rotation polish when lateral error exceeds this value.",
)
parser.add_argument(
    "--depth-rotation-polish-exit-z-tol",
    type=float,
    default=0.060,
    help="Exit depth-rotation polish when axial error exceeds this value.",
)
parser.add_argument(
    "--depth-rotation-polish-preload-step",
    type=float,
    default=0.001,
    help="World-Z preload below the current action-frame position while depth-rotation polish is active.",
)
parser.add_argument(
    "--depth-rotation-polish-rot-step",
    type=float,
    default=None,
    help="Optional maximum axis-angle rotation step while depth-rotation polish is active.",
)
parser.add_argument(
    "--depth-rotation-polish-pos-gain",
    type=float,
    default=1.0,
    help="Lateral/axial position gain for 6D relative actions while depth-rotation polish is active.",
)
parser.add_argument(
    "--depth-rotation-polish-pos-clamp",
    type=float,
    default=0.004,
    help="Lateral/axial position clamp for 6D relative actions while depth-rotation polish is active.",
)
parser.add_argument(
    "--depth-rotation-polish-rot-gain",
    type=float,
    default=3.0,
    help="Orientation gain for 6D relative actions while depth-rotation polish is active.",
)
parser.add_argument(
    "--depth-rotation-polish-rot-clamp",
    type=float,
    default=0.16,
    help="Orientation clamp for 6D relative actions while depth-rotation polish is active.",
)
parser.add_argument("--settle-xy-tol", type=float, default=0.004, help="Lateral tolerance required before final seating.")
parser.add_argument("--settle-rot-tol", type=float, default=0.24, help="Orientation error threshold to enter the final seating phase.")
parser.add_argument("--settle-pos-gain", type=float, default=0.8, help="Lateral position gain during the final seating phase.")
parser.add_argument("--settle-pos-clamp", type=float, default=0.004, help="Lateral position clamp during the final seating phase.")
parser.add_argument("--settle-z-gain", type=float, default=0.8, help="Axial position gain during the final seating phase.")
parser.add_argument("--settle-z-clamp", type=float, default=0.004, help="Axial position clamp during the final seating phase.")
parser.add_argument("--settle-rot-gain", type=float, default=1.5, help="Orientation gain during the final seating phase.")
parser.add_argument("--settle-rot-clamp", type=float, default=0.12, help="Orientation clamp during the final seating phase.")
parser.add_argument(
    "--settle-contact-retention",
    action="store_true",
    default=False,
    help=(
        "Latch a near-seat contact-retention mode when geometry is inside the active success gate but contact force "
        "is below threshold. This keeps a small downward preload instead of bouncing back to Z-hold polish."
    ),
)
parser.add_argument(
    "--settle-contact-min-force",
    type=float,
    default=None,
    help="Contact-force threshold used to enter retention. Defaults to --success-min-contact-force.",
)
parser.add_argument(
    "--settle-contact-preload-step",
    type=float,
    default=0.020,
    help="World-Z preload target below the current action-frame position while contact-retention is active.",
)
parser.add_argument(
    "--settle-contact-hold-xy",
    action="store_true",
    default=False,
    help="Hold the action-frame XY position captured on retention entry while applying contact preload.",
)
parser.add_argument(
    "--settle-contact-force-aware-xy",
    action="store_true",
    default=False,
    help=(
        "During contact-retention, add a bounded socket-frame XY correction from the measured peg contact force. "
        "This is intended to keep the peg centered while the preload maintains contact."
    ),
)
parser.add_argument(
    "--settle-contact-force-scale",
    type=float,
    default=1.0,
    help="Force scale passed to peg_contact_force_socket before computing force-aware XY correction.",
)
parser.add_argument(
    "--settle-contact-force-xy-gain",
    type=float,
    default=0.003,
    help="Meters of socket-frame XY target offset per scaled contact-force unit during force-aware retention.",
)
parser.add_argument(
    "--settle-contact-force-xy-clamp",
    type=float,
    default=0.002,
    help="Maximum absolute force-aware XY target offset in meters per socket-frame axis.",
)
parser.add_argument(
    "--settle-contact-force-xy-sign",
    type=float,
    default=1.0,
    help="Sign multiplier for force-aware XY correction. Use -1.0 if trace analysis shows the force sign is inverted.",
)
parser.add_argument(
    "--settle-contact-xy-tol",
    type=float,
    default=None,
    help="Lateral entry tolerance for contact-retention. Defaults to the active success XY tolerance.",
)
parser.add_argument(
    "--settle-contact-z-tol",
    type=float,
    default=None,
    help="Axial entry tolerance for contact-retention. Defaults to the active success Z tolerance.",
)
parser.add_argument(
    "--settle-contact-rot-tol",
    type=float,
    default=None,
    help="Rotation entry tolerance for contact-retention. Defaults to the active success rotation tolerance.",
)
parser.add_argument(
    "--settle-contact-exit-xy-tol",
    type=float,
    default=0.008,
    help="Exit contact-retention if lateral error exceeds this value.",
)
parser.add_argument(
    "--settle-contact-exit-z-tol",
    type=float,
    default=0.055,
    help="Exit contact-retention if axial error exceeds this value.",
)
parser.add_argument(
    "--settle-contact-exit-rot-tol",
    type=float,
    default=0.24,
    help="Exit contact-retention if rotation error exceeds this value.",
)
parser.add_argument(
    "--success-xy-tol",
    type=float,
    default=None,
    help="Override scripted success lateral tolerance. Defaults to the task constant.",
)
parser.add_argument(
    "--success-z-tol",
    type=float,
    default=None,
    help="Override scripted success axial tolerance. Defaults to the task constant.",
)
parser.add_argument(
    "--success-rot-tol",
    type=float,
    default=None,
    help="Override scripted success orientation tolerance. Defaults to the task constant.",
)
parser.add_argument(
    "--success-min-contact-force",
    type=float,
    default=0.0,
    help="Require at least this peg contact-force magnitude for scripted success.",
)
add_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
skip_auto_enable_cameras = os.environ.get("RCA_SKIP_AUTO_ENABLE_CAMERAS", "0") == "1"
if args_cli.video and args_cli.video_backend == "viewport" and not skip_auto_enable_cameras:
    args_cli.enable_cameras = True
hydra_args.extend(
    [
        f"hydra.run.dir={_HYDRA_ROOT}/${{now:%Y-%m-%d}}/${{now:%H-%M-%S}}",
        "hydra.output_subdir=null",
    ]
)
sys.argv = [sys.argv[0]] + hydra_args


def _tool_tip_pose_w(env_unwrapped, body_idx: int) -> tuple[torch.Tensor, torch.Tensor]:
    hand_pos_w, hand_quat_w = _hand_pose_w(env_unwrapped, body_idx)
    offset_pos = hand_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    offset_quat = hand_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(hand_pos_w.shape[0], 1)
    return combine_frame_transforms(hand_pos_w, hand_quat_w, offset_pos, offset_quat)


def _socket_pose_w(env_unwrapped) -> tuple[torch.Tensor, torch.Tensor]:
    socket = env_unwrapped.scene["socket_frame"]
    return _as_torch(socket.data.root_pos_w).detach().clone(), _as_torch(socket.data.root_quat_w).detach().clone()


def _target_action_frame_pose_w(
    socket_pos_w: torch.Tensor,
    socket_quat_w: torch.Tensor,
    action_quat_w: torch.Tensor,
    *,
    orientation_target_mode: str,
    insertion_axis_local: tuple[float, float, float],
    axis_sign_invariant: bool,
) -> tuple[torch.Tensor, torch.Tensor]:
    target_quat_w = socket_quat_w.clone()
    if orientation_target_mode == "axis-align-current":
        axis_local = socket_pos_w.new_tensor(insertion_axis_local).unsqueeze(0).repeat(socket_pos_w.shape[0], 1)
        target_quat_w = _axis_align_quat(
            action_quat_w,
            socket_quat_w,
            axis_local,
            sign_invariant=axis_sign_invariant,
        )
    return socket_pos_w.clone(), target_quat_w


def _physical_peg_tip_pose_w(env_unwrapped) -> tuple[torch.Tensor, torch.Tensor]:
    if SceneEntityCfg is not None:
        try:
            from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.mdp.observations import (
                _peg_tip_pose_w as _metric_peg_tip_pose_w,
            )

            peg_tip_pos_w, peg_tip_quat_w = _metric_peg_tip_pose_w(env_unwrapped, SceneEntityCfg("peg"))
            return peg_tip_pos_w.detach().clone(), peg_tip_quat_w.detach().clone()
        except (AttributeError, ImportError, KeyError, ModuleNotFoundError, RuntimeError, ValueError):
            pass

    robot = env_unwrapped.scene["robot"]
    for body_name in ("Peg", "peg"):
        if body_name in robot.body_names:
            body_idx = robot.body_names.index(body_name)
            peg_pos_w = _as_torch(robot.data.body_pos_w)[:, body_idx]
            peg_quat_w = _as_torch(robot.data.body_quat_w)[:, body_idx]
            tip_offset_pos = peg_pos_w.new_tensor(PEG_TIP_FROM_CENTER_POS).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
            tip_offset_quat = peg_pos_w.new_tensor(IDENTITY_QUAT).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
            tip_pos_w, tip_quat_w = combine_frame_transforms(peg_pos_w, peg_quat_w, tip_offset_pos, tip_offset_quat)
            return tip_pos_w.detach().clone(), tip_quat_w.detach().clone()

    try:
        peg = env_unwrapped.scene["peg"]
        peg_data = getattr(peg, "data", None)
        if peg_data is None or not hasattr(peg_data, "root_pos_w"):
            raise AttributeError("scene peg has no RigidObject root pose data")
        peg_pos_w = _as_torch(peg_data.root_pos_w)
        peg_quat_w = _as_torch(peg_data.root_quat_w)
    except (AttributeError, KeyError, RuntimeError, ValueError):
        # Last-resort fallback for partial local imports. The Launchable task
        # should use the MDP helper above so trace evidence and task metrics
        # share the same peg-tip definition.
        return _action_frame_pose_w(env_unwrapped, robot.body_names.index("panda_hand"))
    tip_offset_pos = peg_pos_w.new_tensor(PEG_TIP_FROM_CENTER_POS).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    tip_offset_quat = peg_pos_w.new_tensor(IDENTITY_QUAT).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    tip_pos_w, tip_quat_w = combine_frame_transforms(peg_pos_w, peg_quat_w, tip_offset_pos, tip_offset_quat)
    return tip_pos_w.detach().clone(), tip_quat_w.detach().clone()


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


def _set_socket_wall_collisions_enabled(env_cfg, enabled: bool) -> None:
    import isaaclab.sim as sim_utils

    wall_names = (
        "socket_wall_left",
        "socket_wall_right",
        "socket_wall_front",
        "socket_wall_back",
    )
    disabled_positions = {
        "socket_wall_left": (-10.0, 0.0, -10.0),
        "socket_wall_right": (10.0, 0.0, -10.0),
        "socket_wall_front": (0.0, -10.0, -10.0),
        "socket_wall_back": (0.0, 10.0, -10.0),
    }
    for wall_name in wall_names:
        wall = getattr(env_cfg.scene, wall_name)
        wall.spawn.collision_props = sim_utils.CollisionPropertiesCfg(collision_enabled=enabled)
        if not enabled:
            # Some Isaac Sim primitive collision settings can be authored late; park the walls away too.
            wall.init_state.pos = disabled_positions[wall_name]


def _write_kinematic_root_pose(env_unwrapped, name: str, pos_w: torch.Tensor, quat_w: torch.Tensor) -> None:
    asset = env_unwrapped.scene[name]
    pos_w = pos_w.detach().clone()
    quat_w = quat_w.detach().clone()
    with torch.inference_mode():
        asset.write_root_pose_to_sim(torch.cat((pos_w, quat_w), dim=-1))
        if hasattr(asset, "write_root_velocity_to_sim"):
            asset.write_root_velocity_to_sim(torch.zeros((pos_w.shape[0], 6), device=pos_w.device, dtype=pos_w.dtype))


def _write_socket_guide_at_pose(
    env_unwrapped,
    socket_pos_w: torch.Tensor,
    socket_quat_w: torch.Tensor,
    *,
    wall_center_offset: float,
) -> None:
    wall_quat_w = socket_pos_w.new_tensor(IDENTITY_QUAT).unsqueeze(0).repeat(socket_pos_w.shape[0], 1)
    x_offset = socket_pos_w.new_tensor((wall_center_offset, 0.0, 0.0)).unsqueeze(0)
    y_offset = socket_pos_w.new_tensor((0.0, wall_center_offset, 0.0)).unsqueeze(0)
    _write_kinematic_root_pose(env_unwrapped, "socket_frame", socket_pos_w, socket_quat_w)
    _write_kinematic_root_pose(env_unwrapped, "socket_wall_left", socket_pos_w - x_offset, wall_quat_w)
    _write_kinematic_root_pose(env_unwrapped, "socket_wall_right", socket_pos_w + x_offset, wall_quat_w)
    _write_kinematic_root_pose(env_unwrapped, "socket_wall_front", socket_pos_w - y_offset, wall_quat_w)
    _write_kinematic_root_pose(env_unwrapped, "socket_wall_back", socket_pos_w + y_offset, wall_quat_w)


def _clamp_joint_targets(
    robot,
    joint_ids: torch.Tensor,
    joint_pos: torch.Tensor,
    joint_pos_des: torch.Tensor,
    max_step: float,
    limit_margin: float,
    step_limit_mode: str = "component",
) -> torch.Tensor:
    """Bound IK joint targets so a far Cartesian target cannot command unstable joint jumps."""

    max_step = max(0.0, max_step)
    joint_delta = joint_pos_des - joint_pos
    if step_limit_mode == "global":
        max_abs_delta = torch.max(torch.abs(joint_delta), dim=-1, keepdim=True).values
        scale = torch.clamp(max_step / torch.clamp(max_abs_delta, min=1.0e-8), max=1.0)
        joint_pos_des = joint_pos + joint_delta * scale
    else:
        joint_pos_des = joint_pos + torch.clamp(joint_delta, min=-max_step, max=max_step)

    lower, upper = _selected_joint_limits(robot, joint_ids, margin=limit_margin)
    if lower is None or upper is None:
        return joint_pos_des

    return torch.minimum(torch.maximum(joint_pos_des, lower), upper)


def _selected_joint_limits(
    robot,
    joint_ids: torch.Tensor,
    margin: float = 0.0,
) -> tuple[torch.Tensor | None, torch.Tensor | None]:
    """Return selected joint lower/upper limits with an optional safety margin."""

    limits = getattr(robot.data, "soft_joint_pos_limits", None)
    if limits is None:
        limits = getattr(robot.data, "joint_pos_limits", None)
    if limits is None:
        return None, None

    limits = _as_torch(limits).index_select(1, joint_ids)
    lower = limits[..., 0] + margin
    upper = limits[..., 1] - margin
    return lower, upper


def _joint_limit_margin(joint_pos: torch.Tensor, lower: torch.Tensor | None, upper: torch.Tensor | None) -> torch.Tensor | None:
    if lower is None or upper is None:
        return None
    return torch.minimum(joint_pos - lower, upper - joint_pos)


def _joint_limit_centering_delta(
    joint_pos: torch.Tensor,
    lower: torch.Tensor | None,
    upper: torch.Tensor | None,
    *,
    gain: float,
    activation_margin: float,
    max_step: float,
) -> torch.Tensor | None:
    if lower is None or upper is None or gain <= 0.0 or max_step <= 0.0:
        return None

    center = 0.5 * (lower + upper)
    half_range = torch.clamp(0.5 * (upper - lower), min=1.0e-6)
    center_direction = (center - joint_pos) / half_range

    if activation_margin > 0.0:
        margin = _joint_limit_margin(joint_pos, lower, upper)
        assert margin is not None
        proximity = torch.clamp((activation_margin - margin) / activation_margin, min=0.0, max=1.0)
        center_direction = center_direction * proximity

    return torch.clamp(gain * center_direction, min=-max_step, max=max_step)


def _project_joint_delta_to_nullspace(
    jacobian: torch.Tensor,
    joint_delta: torch.Tensor,
    *,
    damping: float,
) -> torch.Tensor:
    task_dim = jacobian.shape[-2]
    joint_dim = jacobian.shape[-1]
    damping = max(0.0, damping)
    eye_task = torch.eye(task_dim, dtype=jacobian.dtype, device=jacobian.device).expand(
        jacobian.shape[0],
        task_dim,
        task_dim,
    )
    eye_joint = torch.eye(joint_dim, dtype=jacobian.dtype, device=jacobian.device).expand(
        jacobian.shape[0],
        joint_dim,
        joint_dim,
    )
    jacobian_t = jacobian.transpose(-1, -2)
    task_matrix = jacobian @ jacobian_t
    if damping > 0.0:
        task_matrix = task_matrix + (damping * damping) * eye_task
    jacobian_pinv = jacobian_t @ torch.linalg.solve(task_matrix, eye_task)
    nullspace_projector = eye_joint - jacobian_pinv @ jacobian
    return (nullspace_projector @ joint_delta.unsqueeze(-1)).squeeze(-1)


def main():
    global RigidObject, SceneEntityCfg, combine_frame_transforms, compute_pose_error, subtract_frame_transforms
    global DifferentialIKController, DifferentialIKControllerCfg
    global IDENTITY_QUAT, PEG_TIP_BODY_OFFSET_POS, PEG_TIP_BODY_OFFSET_ROT, PEG_TIP_FROM_CENTER_POS, mdp, BODY_OFFSET

    os.makedirs(_HYDRA_ROOT, exist_ok=True)
    torch.manual_seed(args_cli.seed)
    if args_cli.watchdog_seconds > 0:
        faulthandler.enable()
        faulthandler.dump_traceback_later(args_cli.watchdog_seconds, repeat=True, file=sys.stderr)

    with _launched_env_cfg(args_cli.task, args_cli) as env_cfg:
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
            SOCKET_GUIDE_INNER_HALF_WIDTH_M,
            SOCKET_GUIDE_WALL_THICKNESS_M,
            SOCKET_INSERTION_AXIS_LOCAL,
            SOCKET_INSERTION_AXIS_SIGN_INVARIANT,
            SOCKET_FRAME_ROT,
            SOCKET_SUCCESS_ROT_TOLERANCE_RAD,
            SOCKET_SUCCESS_XY_TOLERANCE_M,
            SOCKET_SUCCESS_Z_TOLERANCE_M,
        )

        BODY_OFFSET = PEG_TIP_BODY_OFFSET_POS
        env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
        env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
        if args_cli.disable_fabric:
            env_cfg.sim.use_fabric = False
        mdp_abs_ik_method = None
        mdp_abs_ik_params = None
        if args_cli.mdp_abs_ik_method is not None:
            arm_action_cfg = getattr(env_cfg.actions, "arm_action", None)
            controller_cfg = getattr(arm_action_cfg, "controller", None)
            if controller_cfg is None or not hasattr(controller_cfg, "ik_method"):
                raise RuntimeError(
                    "--mdp-abs-ik-method requires an action config with controller.ik_method"
                )
            default_ik_params = {
                "pinv": {"k_val": 1.0},
                "svd": {"k_val": 1.0, "min_singular_value": 1.0e-5},
                "trans": {"k_val": 1.0},
                "dls": {"lambda_val": 0.01},
            }
            controller_cfg.ik_method = args_cli.mdp_abs_ik_method
            controller_cfg.ik_params = default_ik_params[args_cli.mdp_abs_ik_method].copy()
            mdp_abs_ik_method = args_cli.mdp_abs_ik_method
            mdp_abs_ik_params = dict(controller_cfg.ik_params)
            print(
                f"[SCRIPTED] overriding native IK method to {mdp_abs_ik_method} "
                f"params={mdp_abs_ik_params}",
                flush=True,
            )
        else:
            arm_action_cfg = getattr(env_cfg.actions, "arm_action", None)
            controller_cfg = getattr(arm_action_cfg, "controller", None)
            mdp_abs_ik_method = getattr(controller_cfg, "ik_method", None)
            controller_ik_params = getattr(controller_cfg, "ik_params", None)
            mdp_abs_ik_params = dict(controller_ik_params) if isinstance(controller_ik_params, dict) else None
        step_dt = env_cfg.sim.dt * env_cfg.decimation
        scripted_required_steps = args_cli.warmup_steps + args_cli.steps + args_cli.episode_buffer_steps
        scripted_episode_length_s = scripted_required_steps * step_dt
        env_cfg.episode_length_s = max(env_cfg.episode_length_s, scripted_episode_length_s)
        insertion_success_termination_disabled = False
        if args_cli.disable_insertion_success_termination:
            terminations_cfg = getattr(env_cfg, "terminations", None)
            if terminations_cfg is not None and hasattr(terminations_cfg, "insertion_success"):
                terminations_cfg.insertion_success = None
                insertion_success_termination_disabled = True
                print(
                    "[SCRIPTED] disabled geometry-only insertion_success termination; "
                    "contact-aware trace validators remain authoritative",
                    flush=True,
                )
            else:
                print(
                    "[SCRIPTED] insertion_success termination not found; nothing to disable",
                    flush=True,
                )
        # Keep a fixed target for the scripted baseline so convergence is measured against one command.
        env_cfg.commands.socket_pose.resampling_time_range = (1.0e6, 1.0e6)
        if args_cli.deterministic_reset:
            env_cfg.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
        initial_joint_pos_overrides = dict(args_cli.initial_joint_pos or {})
        if initial_joint_pos_overrides:
            init_joint_pos = dict(getattr(env_cfg.scene.robot.init_state, "joint_pos", {}) or {})
            init_joint_pos.update(initial_joint_pos_overrides)
            env_cfg.scene.robot.init_state.joint_pos = init_joint_pos
            print(
                "[SCRIPTED] overriding initial joint positions "
                + ", ".join(f"{name}={value:.4f}" for name, value in sorted(initial_joint_pos_overrides.items())),
                flush=True,
            )
        if args_cli.socket_pos is not None:
            _override_socket_pose(env_cfg, args_cli.socket_pos)
            print(f"[SCRIPTED] overriding socket world position to {args_cli.socket_pos}", flush=True)
        target_action_pos_offset = tuple(args_cli.target_action_pos_offset or (0.0, 0.0, 0.0))
        if any(abs(component) > 0.0 for component in target_action_pos_offset):
            print(
                "[SCRIPTED] offsetting scripted action-frame target by "
                + ",".join(f"{component:.4f}" for component in target_action_pos_offset)
                + f" m in {args_cli.target_action_pos_offset_frame} frame",
                flush=True,
            )
        reachable_approach_start_radius = max(0.0, args_cli.reachable_approach_start_radius)
        reachable_approach_min_radius = max(0.0, args_cli.reachable_approach_min_radius)
        if reachable_approach_start_radius < reachable_approach_min_radius:
            reachable_approach_start_radius = reachable_approach_min_radius
        reachable_approach_shrink_step = max(0.0, args_cli.reachable_approach_shrink_step)
        reachable_approach_shrink_xy_tol = max(0.0, args_cli.reachable_approach_shrink_xy_tol)
        if args_cli.reachable_approach:
            print(
                "[SCRIPTED] reachable approach enabled "
                f"start_radius={reachable_approach_start_radius:.4f} "
                f"min_radius={reachable_approach_min_radius:.4f} "
                f"shrink_step={reachable_approach_shrink_step:.4f} "
                f"shrink_xy_tol={reachable_approach_shrink_xy_tol:.4f} "
                f"joint_margin_min={args_cli.reachable_approach_joint_margin_min:.4f}",
                flush=True,
            )
        if args_cli.disable_socket_wall_collisions:
            _set_socket_wall_collisions_enabled(env_cfg, enabled=False)
            print("[SCRIPTED] disabled socket guide-wall collisions for diagnostic run", flush=True)
        success_xy_tolerance = (
            args_cli.success_xy_tol if args_cli.success_xy_tol is not None else SOCKET_SUCCESS_XY_TOLERANCE_M
        )
        success_z_tolerance = (
            args_cli.success_z_tol if args_cli.success_z_tol is not None else SOCKET_SUCCESS_Z_TOLERANCE_M
        )
        success_rot_tolerance = (
            args_cli.success_rot_tol if args_cli.success_rot_tol is not None else SOCKET_SUCCESS_ROT_TOLERANCE_RAD
        )
        success_min_contact_force = max(0.0, args_cli.success_min_contact_force)
        print(
            "[SCRIPTED] success gate "
            f"xy<{success_xy_tolerance:.4f} z<{success_z_tolerance:.4f} "
            f"rot<{success_rot_tolerance:.4f} min_contact>={success_min_contact_force:.3f}",
            flush=True,
        )

        render_mode = "rgb_array" if args_cli.video and args_cli.video_backend == "viewport" else None
        env = gym.make(args_cli.task, cfg=env_cfg, render_mode=render_mode)
        video_folder = None
        if args_cli.video:
            video_folder = (
                os.path.abspath(args_cli.video_folder)
                if args_cli.video_folder
                else os.path.join(_ARTIFACT_ROOT, "videos", "scripted", f"seed_{args_cli.seed}")
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

        robot = env_unwrapped.scene["robot"]
        body_ids, _ = robot.find_bodies("panda_hand")
        body_idx = body_ids[0]
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
        arm_joint_ids = torch.as_tensor(arm_joint_ids_raw, device=env_unwrapped.device, dtype=torch.long)
        arm_joint_limit_lower, arm_joint_limit_upper = _selected_joint_limits(robot, arm_joint_ids)
        action_dim = env.action_space.shape[-1]
        print(f"[SCRIPTED] tracing arm joints names={arm_joint_names} ids={arm_joint_ids_raw}", flush=True)

        def _hold_current_or_zero_actions() -> torch.Tensor:
            actions = torch.zeros(env.action_space.shape, device=env_unwrapped.device)
            if action_dim == 7:
                arm_joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, arm_joint_ids)
                actions[:, :7] = arm_joint_pos
            return actions

        if args_cli.warmup_steps > 0:
            for _ in range(args_cli.warmup_steps):
                env.step(_hold_current_or_zero_actions())
            warmup_mode = "hold-current-joints" if action_dim == 7 else "zero-relative-action"
            print(
                f"[SCRIPTED] completed {warmup_mode} warmup steps={args_cli.warmup_steps}",
                flush=True,
            )
        demo_reanchor_socket_pos_w = None
        demo_reanchor_socket_quat_w = None
        if args_cli.demo_reanchor_socket:
            from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.mdp.observations import (
                _peg_tip_pose_w as _metric_peg_tip_pose_w,
                _rotate_vector as _metric_rotate_vector,
            )

            action_pos_w, action_quat_w = _action_frame_pose_w(env_unwrapped, body_idx)
            demo_metric_peg_cfg = SceneEntityCfg("peg")
            demo_metric_socket_cfg = SceneEntityCfg("socket_frame")
            physical_tip_pos_w, physical_tip_quat_w = _metric_peg_tip_pose_w(env_unwrapped, demo_metric_peg_cfg)
            if args_cli.demo_reanchor_orientation == "current":
                demo_reanchor_socket_quat_w = physical_tip_quat_w.detach().clone()
            else:
                demo_reanchor_socket_quat_w = action_pos_w.new_tensor(SOCKET_FRAME_ROT).unsqueeze(0).repeat(
                    action_pos_w.shape[0], 1
                )
            local_tip_offset = action_pos_w.new_tensor(
                (0.0, 0.0, max(0.0, args_cli.demo_reanchor_initial_axial))
            ).unsqueeze(0).repeat(action_pos_w.shape[0], 1)
            tip_offset_w = _metric_rotate_vector(demo_reanchor_socket_quat_w, local_tip_offset)
            demo_reanchor_socket_pos_w = physical_tip_pos_w.detach().clone() - tip_offset_w
            _write_socket_guide_at_pose(
                env_unwrapped,
                demo_reanchor_socket_pos_w,
                demo_reanchor_socket_quat_w,
                wall_center_offset=SOCKET_GUIDE_INNER_HALF_WIDTH_M + 0.5 * SOCKET_GUIDE_WALL_THICKNESS_M,
            )
            settle_steps = max(0, int(args_cli.demo_reanchor_settle_steps))
            if settle_steps > 0:
                for _ in range(settle_steps):
                    env.step(_hold_current_or_zero_actions())
            demo_lateral, demo_axial, demo_rot = mdp.insertion_metrics(
                env_unwrapped,
                peg_cfg=demo_metric_peg_cfg,
                socket_cfg=demo_metric_socket_cfg,
            )
            print(
                "[SCRIPTED] demo reanchored socket guide "
                f"pos={demo_reanchor_socket_pos_w[0].detach().cpu().tolist()} "
                f"quat={demo_reanchor_socket_quat_w[0].detach().cpu().tolist()} "
                f"initial_axial={max(0.0, args_cli.demo_reanchor_initial_axial):.4f} "
                f"orientation={args_cli.demo_reanchor_orientation} settle_steps={settle_steps} "
                f"post_reanchor_lateral={demo_lateral[0].item():.6f} "
                f"post_reanchor_axial={demo_axial[0].item():.6f} "
                f"post_reanchor_rot={demo_rot[0].item():.6f}",
                flush=True,
            )
        peg_cfg = SceneEntityCfg("peg")
        socket_cfg = SceneEntityCfg("socket_frame")
        contact_sensor_cfg = None
        try:
            env_unwrapped.scene["peg_contact"]
            contact_sensor_cfg = SceneEntityCfg("peg_contact")
        except KeyError:
            contact_sensor_cfg = None
        scripted_control_mode = args_cli.scripted_control_mode
        if scripted_control_mode == "auto":
            scripted_control_mode = "joint-ik" if "JointPos" in args_cli.task else "mdp"
        if action_dim not in (6, 7):
            raise ValueError(f"unsupported scripted action dimension: {action_dim}")
        if scripted_control_mode == "joint-ik" and action_dim != 7:
            raise ValueError(f"joint-ik scripted control requires a 7D joint-position action, got {action_dim}")
        if scripted_control_mode == "joint-response" and action_dim != 7:
            raise ValueError(f"joint-response scripted control requires a 7D joint-position action, got {action_dim}")

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
        success_hold_count = 0
        success_hold_exit_step = None
        post_success_hold_step_count = 0
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
        min_arm_joint_limit_margin = float("inf")
        min_arm_joint_limit_margin_step = None
        min_arm_joint_limit_margin_joint_index = None
        min_arm_joint_limit_margin_joint_name = None
        max_joint_limit_nullspace_delta_norm = 0.0
        max_joint_limit_nullspace_delta_norm_step = None
        max_joint_limit_guard_delta_norm = 0.0
        max_joint_limit_guard_delta_norm_step = None
        max_contact_force_magnitude = 0.0
        max_contact_force_magnitude_step = None
        rotate_xy_recovery_step_count = 0
        rotate_xy_recovery_first_step = None
        rotate_xy_recovery_last_step = None
        rotate_xy_recovery_max_lateral = None
        rotate_descent_step_count = 0
        rotate_descent_first_step = None
        rotate_descent_last_step = None
        insert_rotation_gate_step_count = 0
        insert_rotation_gate_first_step = None
        insert_rotation_gate_last_step = None
        insert_rotation_gate_max_rot = None
        insert_rotation_gate_allowed_descent_max = 0.0
        depth_rotation_polish_step_count = 0
        depth_rotation_polish_first_step = None
        depth_rotation_polish_last_step = None
        depth_rotation_polish_max_rot = None
        depth_rotation_polish_max_lateral = None
        depth_rotation_polish_min_axial = None
        final_contact_servo_step_count = 0
        final_contact_servo_first_step = None
        final_contact_servo_last_step = None
        final_contact_servo_entry_count = 0
        final_contact_servo_exit_count = 0
        final_contact_servo_max_lateral = None
        final_contact_servo_min_axial = None
        final_contact_servo_max_xy_offset = 0.0
        final_contact_servo_z_hold_count = 0
        socket_insertion_servo_step_count = 0
        socket_insertion_servo_first_step = None
        socket_insertion_servo_last_step = None
        socket_insertion_servo_entry_count = 0
        socket_insertion_servo_exit_count = 0
        socket_insertion_servo_descend_count = 0
        socket_insertion_servo_z_hold_count = 0
        socket_insertion_servo_contact_preload_count = 0
        socket_insertion_servo_contact_boundary_count = 0
        socket_insertion_servo_recovery_count = 0
        socket_insertion_servo_orientation_hold_count = 0
        socket_insertion_servo_max_lateral = None
        socket_insertion_servo_min_axial = None
        socket_insertion_servo_max_xy_offset = 0.0
        descend_xy_recovery_step_count = 0
        descend_xy_recovery_first_step = None
        descend_xy_recovery_last_step = None
        descend_xy_recovery_max_lateral = None
        trace_rows = []
        trace_events_jsonl = (
            os.path.join(os.path.dirname(os.path.abspath(args_cli.trace_json)), "trace_events.jsonl")
            if args_cli.trace_json
            else None
        )
        trace_artifacts_finalized = {"value": False}
        last_partial_summary: dict = {}
        trace_execution_state = {
            "last_step_started": None,
            "last_trace_phase": "control_loop_setup",
        }

        def _write_unexpected_exit_trace_artifacts() -> None:
            if trace_artifacts_finalized["value"]:
                return
            if not (args_cli.summary_json or args_cli.trace_json):
                return
            summary = dict(last_partial_summary)
            if not summary:
                summary = {
                    "artifact_status": "partial",
                    "artifact_label": "atexit-without-summary",
                    "task": args_cli.task,
                    "seed": args_cli.seed,
                    "steps_requested": args_cli.steps,
                    "steps_recorded": len(trace_rows),
                    "trace_json": os.path.abspath(args_cli.trace_json) if args_cli.trace_json else None,
                }
            else:
                summary["artifact_status"] = "partial"
                summary["artifact_label"] = f"atexit-after-{summary.get('artifact_label', 'partial')}"
                summary["steps_recorded"] = len(trace_rows)
            summary["last_step_started"] = trace_execution_state["last_step_started"]
            summary["last_trace_phase"] = trace_execution_state["last_trace_phase"]
            summary["trace_events_jsonl"] = (
                os.path.abspath(trace_events_jsonl) if trace_events_jsonl else None
            )
            if not trace_rows:
                summary["failure_note"] = (
                    "interpreter exited before the first trace row; inspect "
                    "trace_events.jsonl for the last completed phase"
                )
            _write_rollout_artifacts(
                summary_json=args_cli.summary_json,
                trace_json=args_cli.trace_json,
                summary=summary,
                trace_rows=trace_rows,
                label="atexit-partial",
            )
            trace_artifacts_finalized["value"] = True
            print("[SCRIPTED] atexit wrote partial trace artifacts before interpreter shutdown", flush=True)

        def _handle_termination_signal(signum, _frame) -> None:
            trace_execution_state["last_trace_phase"] = (
                f"signal-{signal.Signals(signum).name}-after-"
                f"{trace_execution_state.get('last_trace_phase')}"
            )
            _write_unexpected_exit_trace_artifacts()
            raise SystemExit(128 + int(signum))

        atexit.register(_write_unexpected_exit_trace_artifacts)
        signal.signal(signal.SIGTERM, _handle_termination_signal)
        signal.signal(signal.SIGINT, _handle_termination_signal)
        _append_jsonl(
            trace_events_jsonl,
            {
                "event": "control_loop_setup",
                "task": args_cli.task,
                "seed": args_cli.seed,
                "steps_requested": args_cli.steps,
                "headless": bool(args_cli.headless),
                "trace_json": os.path.abspath(args_cli.trace_json) if args_cli.trace_json else None,
            },
        )
        xy_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        rotate_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        insert_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        aligned_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        contact_retention_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        contact_retention_anchor_pos_w = torch.zeros(
            (env_unwrapped.num_envs, 3), dtype=torch.float32, device=env_unwrapped.device
        )
        insert_abort_counts = torch.zeros(env_unwrapped.num_envs, dtype=torch.long, device=env_unwrapped.device)
        rotate_hold_pos_w = torch.zeros((env_unwrapped.num_envs, 3), dtype=torch.float32, device=env_unwrapped.device)
        rotate_hold_valid = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        rotate_command_quat_w = torch.zeros((env_unwrapped.num_envs, 4), dtype=torch.float32, device=env_unwrapped.device)
        rotate_command_valid = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        insert_hold_quat_w = torch.zeros((env_unwrapped.num_envs, 4), dtype=torch.float32, device=env_unwrapped.device)
        insert_hold_valid = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        insert_joint_cache_valid = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        insert_joint_cache_anchor = torch.zeros((env_unwrapped.num_envs, 7), dtype=torch.float32, device=env_unwrapped.device)
        insert_joint_cache_direction = torch.zeros((env_unwrapped.num_envs, 7), dtype=torch.float32, device=env_unwrapped.device)
        insert_joint_cache_step_counts = torch.zeros(env_unwrapped.num_envs, dtype=torch.long, device=env_unwrapped.device)
        reachable_approach_radius = torch.full(
            (env_unwrapped.num_envs,),
            reachable_approach_start_radius,
            dtype=torch.float32,
            device=env_unwrapped.device,
        )
        reachable_approach_offset_dir_w = torch.zeros(
            (env_unwrapped.num_envs, 3),
            dtype=torch.float32,
            device=env_unwrapped.device,
        )
        reachable_approach_offset_dir_w[:, 0] = 1.0
        reachable_approach_offset_dir_valid = torch.zeros(
            env_unwrapped.num_envs,
            dtype=torch.bool,
            device=env_unwrapped.device,
        )
        reachable_approach_last_post_margin = torch.full(
            (env_unwrapped.num_envs,),
            0.0,
            dtype=torch.float32,
            device=env_unwrapped.device,
        )
        reachable_approach_shrink_count = 0
        reachable_approach_margin_block_count = 0
        reachable_approach_min_observed_radius = reachable_approach_start_radius
        polish_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        depth_rotation_polish_state = torch.zeros(
            env_unwrapped.num_envs,
            dtype=torch.bool,
            device=env_unwrapped.device,
        )
        depth_rotation_polish_command_quat_w = torch.zeros(
            (env_unwrapped.num_envs, 4),
            dtype=torch.float32,
            device=env_unwrapped.device,
        )
        depth_rotation_polish_command_valid = torch.zeros(
            env_unwrapped.num_envs,
            dtype=torch.bool,
            device=env_unwrapped.device,
        )
        settle_state = torch.zeros(env_unwrapped.num_envs, dtype=torch.bool, device=env_unwrapped.device)
        final_contact_servo_state = torch.zeros(
            env_unwrapped.num_envs,
            dtype=torch.bool,
            device=env_unwrapped.device,
        )
        socket_insertion_servo_state = torch.zeros(
            env_unwrapped.num_envs,
            dtype=torch.bool,
            device=env_unwrapped.device,
        )
        socket_insertion_servo_command_quat_w = torch.zeros(
            (env_unwrapped.num_envs, 4),
            dtype=torch.float32,
            device=env_unwrapped.device,
        )
        socket_insertion_servo_command_valid = torch.zeros(
            env_unwrapped.num_envs,
            dtype=torch.bool,
            device=env_unwrapped.device,
        )
        branch_jump_step = None
        branch_jump_reason = None
        branch_jump_contact_force_magnitude = None
        branch_jump_joint_limit_margin_min = None
        action_axis_signs = torch.tensor(args_cli.action_axis_signs, device=env_unwrapped.device).unsqueeze(0)
        calibrated_candidate_names: list[str] = []
        calibrated_candidate_actions = None
        calibrated_candidate_deltas = None
        joint_response_matrix = None
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
        if scripted_control_mode == "joint-response":
            if not args_cli.joint_response_json:
                raise ValueError("--joint-response-json is required when --scripted-control-mode joint-response")
            joint_response_matrix = torch.tensor(
                _load_joint_response_matrix(args_cli.joint_response_json),
                dtype=torch.float32,
                device=env_unwrapped.device,
            )
            print(
                "[SCRIPTED] loaded empirical joint response matrix "
                f"path={args_cli.joint_response_json} shape={tuple(joint_response_matrix.shape)}",
                flush=True,
            )

        def _debug_step(label: str, step_idx: int) -> None:
            if step_idx < args_cli.debug_action_steps:
                print(f"[SCRIPTED-STEP] step={step_idx:04d} {label}", flush=True)

        def _trace_phase(label: str, step_idx: int) -> None:
            trace_execution_state["last_step_started"] = int(step_idx)
            trace_execution_state["last_trace_phase"] = label
            if step_idx < args_cli.trace_phase_steps:
                _append_jsonl(trace_events_jsonl, {"event": "step_phase", "step": step_idx, "phase": label})

        sim = env_unwrapped.sim
        print(f"[SCRIPTED] entering control loop steps={args_cli.steps}", flush=True)
        _append_jsonl(trace_events_jsonl, {"event": "control_loop_enter", "steps_requested": args_cli.steps})
        for step in range(args_cli.steps):
            _debug_step("begin", step)
            trace_execution_state["last_step_started"] = int(step)
            trace_execution_state["last_trace_phase"] = "step_begin"
            _append_jsonl(trace_events_jsonl, {"event": "step_begin", "step": step})
            _trace_phase("begin", step)
            if not args_cli.headless and sim.visualizers and not any(
                v.is_running() and not v.is_closed for v in sim.visualizers
            ):
                _append_jsonl(trace_events_jsonl, {"event": "visualizer_closed_break", "step": step})
                break

            _trace_phase("before_pose_sampling", step)
            action_pos_w, action_quat_w = _action_frame_pose_w(env_unwrapped, body_idx)
            hand_pos_w, hand_quat_w = _hand_pose_w(env_unwrapped, body_idx)
            physical_tip_pos_w, physical_tip_quat_w = _physical_peg_tip_pose_w(env_unwrapped)
            socket_pos_w, socket_quat_w = _socket_pose_w(env_unwrapped)
            _trace_phase("after_pose_sampling", step)
            _trace_phase("before_target_pose", step)
            target_action_pos_w, target_action_quat_w = _target_action_frame_pose_w(
                socket_pos_w,
                socket_quat_w,
                action_quat_w,
                orientation_target_mode=args_cli.orientation_target_mode,
                insertion_axis_local=SOCKET_INSERTION_AXIS_LOCAL,
                axis_sign_invariant=SOCKET_INSERTION_AXIS_SIGN_INVARIANT,
            )
            unbiased_target_action_pos_w = target_action_pos_w.clone()
            target_action_pos_offset_tensor = target_action_pos_w.new_tensor(target_action_pos_offset).unsqueeze(0).repeat(
                target_action_pos_w.shape[0], 1
            )
            if args_cli.target_action_pos_offset_frame == "socket":
                target_action_pos_offset_w = _quat_rotate_wxyz(socket_quat_w, target_action_pos_offset_tensor)
            else:
                target_action_pos_offset_w = target_action_pos_offset_tensor
            target_action_pos_w = target_action_pos_w + target_action_pos_offset_w
            reachable_approach_offset_w = torch.zeros_like(target_action_pos_w)
            reachable_approach_target_xy_error = torch.zeros(
                target_action_pos_w.shape[0],
                dtype=target_action_pos_w.dtype,
                device=target_action_pos_w.device,
            )
            reachable_approach_margin_ok = torch.ones(
                target_action_pos_w.shape[0],
                dtype=torch.bool,
                device=target_action_pos_w.device,
            )
            reachable_approach_shrink_mask = torch.zeros_like(reachable_approach_margin_ok)
            reachable_approach_margin_block_mask = torch.zeros_like(reachable_approach_margin_ok)
            if args_cli.reachable_approach and reachable_approach_start_radius > 0.0:
                init_dir_mask = ~reachable_approach_offset_dir_valid
                if init_dir_mask.any():
                    target_to_action_xy = action_pos_w[:, :2] - target_action_pos_w[:, :2]
                    target_to_action_norm = torch.linalg.norm(target_to_action_xy, dim=-1, keepdim=True)
                    fallback_dir_xy = torch.zeros_like(target_to_action_xy)
                    fallback_dir_xy[:, 0] = 1.0
                    initial_dir_xy = torch.where(
                        target_to_action_norm > 1.0e-6,
                        target_to_action_xy / torch.clamp(target_to_action_norm, min=1.0e-6),
                        fallback_dir_xy,
                    )
                    reachable_approach_offset_dir_w[init_dir_mask, :2] = initial_dir_xy[init_dir_mask]
                    reachable_approach_offset_dir_w[init_dir_mask, 2] = 0.0
                    reachable_approach_offset_dir_valid[init_dir_mask] = True

                candidate_target_action_pos_w = (
                    target_action_pos_w + reachable_approach_offset_dir_w * reachable_approach_radius[:, None]
                )
                reachable_approach_target_xy_error = torch.linalg.norm(
                    (candidate_target_action_pos_w - action_pos_w)[:, :2],
                    dim=1,
                )
                if args_cli.reachable_approach_joint_margin_min > 0.0:
                    reachable_approach_margin_ok = (
                        reachable_approach_last_post_margin >= args_cli.reachable_approach_joint_margin_min
                    )
                radius_can_shrink = reachable_approach_radius > (reachable_approach_min_radius + 1.0e-6)
                target_reached = reachable_approach_target_xy_error < reachable_approach_shrink_xy_tol
                reachable_approach_shrink_mask = radius_can_shrink & target_reached & reachable_approach_margin_ok
                reachable_approach_margin_block_mask = radius_can_shrink & target_reached & ~reachable_approach_margin_ok
                if reachable_approach_shrink_mask.any() and reachable_approach_shrink_step > 0.0:
                    next_radius = torch.clamp(
                        reachable_approach_radius - reachable_approach_shrink_step,
                        min=reachable_approach_min_radius,
                    )
                    reachable_approach_radius = torch.where(
                        reachable_approach_shrink_mask,
                        next_radius,
                        reachable_approach_radius,
                    )
                    reachable_approach_shrink_count += int(reachable_approach_shrink_mask.sum().item())
                    reachable_approach_min_observed_radius = min(
                        reachable_approach_min_observed_radius,
                        float(torch.min(reachable_approach_radius).item()),
                    )
                if reachable_approach_margin_block_mask.any():
                    reachable_approach_margin_block_count += int(reachable_approach_margin_block_mask.sum().item())

                reachable_approach_offset_w = reachable_approach_offset_dir_w * reachable_approach_radius[:, None]
                target_action_pos_w = target_action_pos_w + reachable_approach_offset_w
            physical_tip_rel_socket_pos, _ = subtract_frame_transforms(
                socket_pos_w,
                socket_quat_w,
                physical_tip_pos_w,
                physical_tip_quat_w,
            )
            action_tip_alignment = torch.linalg.norm(physical_tip_pos_w - action_pos_w, dim=1)

            _trace_phase("before_insertion_metrics", step)
            lateral_error, axial_error, orientation_error = mdp.insertion_metrics(
                env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg
            )
            _trace_phase("after_insertion_metrics", step)
            _trace_phase("before_tip_to_socket_position", step)
            metric_tip_rel_socket_pos = mdp.tip_to_socket_position(
                env_unwrapped,
                peg_cfg=peg_cfg,
                socket_cfg=socket_cfg,
            )
            _trace_phase("after_tip_to_socket_position", step)
            pre_contact_force_magnitude = None
            pre_contact_force_socket = None
            pre_insert_contact_force_socket = None
            if contact_sensor_cfg is not None:
                _trace_phase("before_pre_contact_force", step)
                pre_contact_force_magnitude = mdp.peg_contact_force_magnitude(
                    env_unwrapped,
                    sensor_cfg=contact_sensor_cfg,
                )
                pre_contact_force_socket = mdp.peg_contact_force_socket(
                    env_unwrapped,
                    sensor_cfg=contact_sensor_cfg,
                    socket_cfg=socket_cfg,
                    force_scale=max(1.0e-6, args_cli.settle_contact_force_scale),
                )
                if args_cli.insert_contact_force_aware_xy:
                    pre_insert_contact_force_socket = mdp.peg_contact_force_socket(
                        env_unwrapped,
                        sensor_cfg=contact_sensor_cfg,
                        socket_cfg=socket_cfg,
                        force_scale=max(1.0e-6, args_cli.insert_contact_force_scale),
                    )
                _trace_phase("after_pre_contact_force", step)
            _debug_step("metrics_ready", step)
            _trace_phase("metrics_ready", step)
            _trace_phase("before_ready_masks", step)
            orientation_ready = orientation_error < args_cli.approach_rot_tol
            insert_xy_tolerance = args_cli.insert_xy_tol if args_cli.insert_xy_tol is not None else args_cli.approach_xy_tol
            insert_rot_tolerance = (
                args_cli.insert_rot_tol if args_cli.insert_rot_tol is not None else args_cli.approach_rot_tol
            )
            insert_descent_rot_tolerance = (
                args_cli.insert_descent_rot_tol
                if args_cli.insert_descent_rot_tol is not None
                else insert_rot_tolerance
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
            _trace_phase("after_ready_masks", step)

            _trace_phase("before_approach_insert_state", step)
            approach_pos_w = target_action_pos_w.clone()
            if args_cli.approach_axis == "socket":
                approach_axis_local = socket_pos_w.new_tensor(SOCKET_INSERTION_AXIS_LOCAL).unsqueeze(0).repeat(
                    socket_pos_w.shape[0], 1
                )
                approach_offset_local = approach_axis_local * args_cli.approach_height
                approach_offset_w = _quat_rotate_wxyz(socket_quat_w, approach_offset_local)
                approach_pos_w = target_action_pos_w + approach_offset_w
                approach_z_error = torch.linalg.norm(action_pos_w - approach_pos_w, dim=1)
            else:
                approach_pos_w[:, 2] += args_cli.approach_height
                approach_z_error = torch.abs(action_pos_w[:, 2] - approach_pos_w[:, 2])
            target_pos_w = approach_pos_w.clone()
            target_quat_w = target_action_quat_w.clone()
            controller_lateral_error = torch.linalg.norm((target_action_pos_w - action_pos_w)[:, :2], dim=1)
            descend_mask = torch.zeros_like(xy_state)
            rotate_descent_mask = torch.zeros_like(xy_state)

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
                        if args_cli.rotate_descent_mode == "approach":
                            rotate_descent_mask = rotate_hold_mask
                        else:
                            target_pos_w[rotate_hold_mask] = torch.where(
                                rotate_hold_valid[rotate_hold_mask, None],
                                rotate_hold_pos_w[rotate_hold_mask],
                                xy_target_pos_w[rotate_hold_mask],
                            )
                    target_quat_w[rotate_state] = target_action_quat_w[rotate_state]
                    position_ready = rotation_ready & (approach_z_error < args_cli.approach_z_tol)
                    aligned_insert_ready = rotation_ready & insert_xy_ready & insert_orientation_ready
                    if args_cli.insert_after_alignment:
                        insert_mask = aligned_insert_ready
                    else:
                        insert_mask = position_ready & insert_xy_ready & insert_orientation_ready
                    descend_mask = rotation_ready & ~position_ready & ~insert_mask & ~insert_state
                    if args_cli.hold_orientation_during_descend:
                        target_quat_w[descend_mask] = action_quat_w[descend_mask]
                else:
                    position_ready = xy_state & (approach_z_error < args_cli.approach_z_tol)
                    rotate_state |= position_ready
                    target_quat_w[rotate_state] = target_action_quat_w[rotate_state]
                    insert_mask = position_ready & insert_xy_ready & insert_orientation_ready
                    descend_mask = xy_state & ~position_ready & ~insert_mask & ~insert_state
            else:
                # Decouple gross translation from large orientation changes. With a rigid tip offset, rotating
                # while still far from the socket can move the tip away from the approach corridor.
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
            insert_new_entry_mask = insert_entry_mask & ~insert_state
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
            insert_hold_valid[insert_abort_mask] = False
            insert_joint_cache_valid[insert_abort_mask] = False
            insert_joint_cache_step_counts[insert_abort_mask] = 0
            insert_hold_valid &= insert_state
            insert_joint_cache_valid &= insert_state
            insert_new_active_mask = insert_new_entry_mask & insert_state
            if insert_new_active_mask.any():
                insert_hold_quat_w[insert_new_active_mask] = action_quat_w[insert_new_active_mask]
                insert_hold_valid[insert_new_active_mask] = True
                insert_joint_cache_valid[insert_new_active_mask] = False
                insert_joint_cache_step_counts[insert_new_active_mask] = 0
            insert_mask = insert_state
            _trace_phase("after_approach_insert_state", step)
            insert_rotation_gate_mask = torch.zeros_like(insert_mask)
            insert_rotation_gate_allowed_descent = torch.zeros_like(action_pos_w[:, 2])
            depth_rotation_polish_mask = torch.zeros_like(insert_mask)
            final_contact_servo_mask = torch.zeros_like(insert_mask)
            final_contact_servo_entry_mask = torch.zeros_like(insert_mask)
            final_contact_servo_exit_mask = torch.zeros_like(insert_mask)
            final_contact_servo_xy_offset_socket = torch.zeros_like(target_pos_w)
            final_contact_servo_xy_offset_w = torch.zeros_like(target_pos_w)
            final_contact_servo_xy_target_w = target_action_pos_w
            final_contact_servo_requested_descent = torch.zeros_like(action_pos_w[:, 2])
            final_contact_servo_metric_error_socket = torch.zeros_like(target_pos_w)
            final_contact_servo_z_hold_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_entry_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_exit_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_offset_socket = torch.zeros_like(target_pos_w)
            socket_insertion_servo_offset_w = torch.zeros_like(target_pos_w)
            socket_insertion_servo_target_w = target_action_pos_w
            socket_insertion_servo_xy_ready_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_rot_ready_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_axial_ready_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_contact_ready_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_boundary_contact_ready_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_descend_ready_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_contact_boundary_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_contact_preload_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_maintained_contact_preload_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_contact_boundary_preload_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_z_hold_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_soft_exit_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_hard_exit_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_recovery_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_rotate_mask = torch.zeros_like(insert_mask)
            socket_insertion_servo_orientation_hold_mask = torch.zeros_like(insert_mask)
            action_semantics_probe_active = args_cli.action_semantics_probe_delta is not None
            action_semantics_probe_delta_w = torch.zeros_like(target_pos_w)
            _trace_phase("after_action_mask_init", step)

            _trace_phase("before_action_semantics_probe", step)
            if action_semantics_probe_active:
                probe_delta = target_pos_w.new_tensor(args_cli.action_semantics_probe_delta).unsqueeze(0).repeat(
                    target_pos_w.shape[0],
                    1,
                )
                if args_cli.action_semantics_probe_frame == "socket":
                    action_semantics_probe_delta_w = _quat_rotate_wxyz(socket_quat_w, probe_delta)
                else:
                    action_semantics_probe_delta_w = probe_delta
                target_pos_w = action_pos_w + action_semantics_probe_delta_w
                target_quat_w = action_quat_w.clone()
                xy_state &= torch.zeros_like(xy_state)
                rotate_state &= torch.zeros_like(rotate_state)
                insert_state &= torch.zeros_like(insert_state)
                polish_state &= torch.zeros_like(polish_state)
                settle_state &= torch.zeros_like(settle_state)
                contact_retention_state &= torch.zeros_like(contact_retention_state)
                insert_mask &= torch.zeros_like(insert_mask)
                descend_mask &= torch.zeros_like(descend_mask)
                rotate_descent_mask &= torch.zeros_like(rotate_descent_mask)
            _trace_phase("after_action_semantics_probe", step)

            _trace_phase("before_depth_rotation_polish_state", step)
            if (not action_semantics_probe_active) and args_cli.depth_rotation_polish:
                depth_rotation_polish_xy_tolerance = (
                    success_xy_tolerance
                    if args_cli.depth_rotation_polish_xy_tol is None
                    else max(0.0, args_cli.depth_rotation_polish_xy_tol)
                )
                depth_rotation_polish_z_tolerance = (
                    success_z_tolerance
                    if args_cli.depth_rotation_polish_z_tol is None
                    else max(0.0, args_cli.depth_rotation_polish_z_tol)
                )
                depth_rotation_polish_contact_min_force = (
                    success_min_contact_force
                    if args_cli.depth_rotation_polish_contact_min_force is None
                    else max(0.0, args_cli.depth_rotation_polish_contact_min_force)
                )
                if depth_rotation_polish_contact_min_force > 0.0:
                    if pre_contact_force_magnitude is None:
                        depth_rotation_polish_contact_ready = torch.zeros_like(insert_mask)
                    else:
                        depth_rotation_polish_contact_ready = (
                            pre_contact_force_magnitude.squeeze(-1) >= depth_rotation_polish_contact_min_force
                        )
                else:
                    depth_rotation_polish_contact_ready = torch.ones_like(insert_mask)
                depth_rotation_polish_ready = (
                    insert_mask
                    & (lateral_error < depth_rotation_polish_xy_tolerance)
                    & (axial_error < depth_rotation_polish_z_tolerance)
                    & depth_rotation_polish_contact_ready
                )
                depth_rotation_polish_entry = depth_rotation_polish_ready & ~depth_rotation_polish_state
                depth_rotation_polish_state |= depth_rotation_polish_ready
                depth_rotation_polish_exit_contact_min_force = (
                    None
                    if args_cli.depth_rotation_polish_exit_contact_min_force is None
                    else max(0.0, args_cli.depth_rotation_polish_exit_contact_min_force)
                )
                if depth_rotation_polish_exit_contact_min_force is not None:
                    if pre_contact_force_magnitude is None:
                        depth_rotation_polish_contact_exit = depth_rotation_polish_state
                    else:
                        depth_rotation_polish_contact_exit = (
                            pre_contact_force_magnitude.squeeze(-1) < depth_rotation_polish_exit_contact_min_force
                        )
                else:
                    depth_rotation_polish_contact_exit = torch.zeros_like(depth_rotation_polish_state)
                depth_rotation_polish_exit = (
                    (lateral_error > max(0.0, args_cli.depth_rotation_polish_exit_xy_tol))
                    | (axial_error > max(0.0, args_cli.depth_rotation_polish_exit_z_tol))
                    | depth_rotation_polish_contact_exit
                )
                depth_rotation_polish_state &= ~depth_rotation_polish_exit
                if depth_rotation_polish_entry.any():
                    depth_rotation_polish_command_quat_w[depth_rotation_polish_entry] = action_quat_w[
                        depth_rotation_polish_entry
                    ]
                    depth_rotation_polish_command_valid[depth_rotation_polish_entry] = True
                depth_rotation_polish_command_valid &= depth_rotation_polish_state
                depth_rotation_polish_mask = depth_rotation_polish_state & insert_mask
            else:
                depth_rotation_polish_xy_tolerance = (
                    success_xy_tolerance
                    if args_cli.depth_rotation_polish_xy_tol is None
                    else max(0.0, args_cli.depth_rotation_polish_xy_tol)
                )
                depth_rotation_polish_z_tolerance = (
                    success_z_tolerance
                    if args_cli.depth_rotation_polish_z_tol is None
                    else max(0.0, args_cli.depth_rotation_polish_z_tol)
                )
                depth_rotation_polish_contact_min_force = (
                    success_min_contact_force
                    if args_cli.depth_rotation_polish_contact_min_force is None
                    else max(0.0, args_cli.depth_rotation_polish_contact_min_force)
                )
                depth_rotation_polish_exit_contact_min_force = (
                    None
                    if args_cli.depth_rotation_polish_exit_contact_min_force is None
                    else max(0.0, args_cli.depth_rotation_polish_exit_contact_min_force)
                )
                depth_rotation_polish_command_valid &= torch.zeros_like(depth_rotation_polish_command_valid)
            _trace_phase("after_depth_rotation_polish_state", step)

            depth_rotation_polish_target_quat_w = target_action_quat_w
            _trace_phase("before_depth_rotation_polish_command", step)
            if depth_rotation_polish_mask.any() and args_cli.depth_rotation_polish_orientation_mode == "stateful-waypoint":
                depth_rotation_polish_command_seed_mask = (
                    depth_rotation_polish_mask & ~depth_rotation_polish_command_valid
                )
                if depth_rotation_polish_command_seed_mask.any():
                    depth_rotation_polish_command_quat_w[depth_rotation_polish_command_seed_mask] = action_quat_w[
                        depth_rotation_polish_command_seed_mask
                    ]
                    depth_rotation_polish_command_valid[depth_rotation_polish_command_seed_mask] = True
                depth_rotation_step = (
                    args_cli.abs_rot_step
                    if args_cli.depth_rotation_polish_rot_step is None
                    else max(0.0, args_cli.depth_rotation_polish_rot_step)
                )
                depth_rotation_polish_command_quat_w[depth_rotation_polish_mask] = _quat_step_towards(
                    depth_rotation_polish_command_quat_w[depth_rotation_polish_mask],
                    target_action_quat_w[depth_rotation_polish_mask],
                    depth_rotation_step,
                )
                depth_rotation_polish_target_quat_w = target_action_quat_w.clone()
                depth_rotation_polish_target_quat_w[depth_rotation_polish_mask] = depth_rotation_polish_command_quat_w[
                    depth_rotation_polish_mask
                ]
            _trace_phase("after_depth_rotation_polish_command", step)

            insert_contact_force_xy_offset_w = torch.zeros_like(target_pos_w)
            insert_contact_force_xy_offset_socket = torch.zeros_like(target_pos_w)
            insert_contact_force_xy_target_w = target_action_pos_w
            insert_contact_force_active_mask = torch.zeros_like(insert_mask)
            _trace_phase("before_insert_target_update", step)
            if insert_mask.any():
                if args_cli.insert_descent_mode in ("vertical", "joint-cache"):
                    insert_vertical_step = (
                        args_cli.insert_vertical_step
                        if args_cli.insert_vertical_step is not None
                        else args_cli.insert_pos_step
                        if args_cli.insert_pos_step is not None
                        else args_cli.abs_pos_step
                    )
                    vertical_insert_pos_w = target_action_pos_w.clone()
                    vertical_insert_pos_w[:, 2] = torch.maximum(
                        target_action_pos_w[:, 2],
                        action_pos_w[:, 2] - insert_vertical_step,
                    )
                    target_pos_w[insert_mask] = vertical_insert_pos_w[insert_mask]
                else:
                    target_pos_w[insert_mask] = target_action_pos_w[insert_mask]
                if args_cli.hold_orientation_during_insert:
                    target_quat_w[insert_mask] = torch.where(
                        insert_hold_valid[insert_mask, None],
                        insert_hold_quat_w[insert_mask],
                        action_quat_w[insert_mask],
                    )
                else:
                    target_quat_w[insert_mask] = target_action_quat_w[insert_mask]
                if (
                    args_cli.insert_contact_force_aware_xy
                    and pre_contact_force_magnitude is not None
                    and pre_insert_contact_force_socket is not None
                ):
                    insert_contact_force_active_mask = insert_mask & (
                        pre_contact_force_magnitude.squeeze(-1) >= max(0.0, args_cli.insert_contact_force_min)
                    )
                    if insert_contact_force_active_mask.any():
                        insert_contact_force_xy_socket = (
                            args_cli.insert_contact_force_xy_sign
                            * max(0.0, args_cli.insert_contact_force_xy_gain)
                            * pre_insert_contact_force_socket[:, :2]
                        )
                        insert_contact_force_xy_socket = _clamp_actions(
                            insert_contact_force_xy_socket,
                            max(0.0, args_cli.insert_contact_force_xy_clamp),
                        )
                        insert_contact_force_xy_offset_socket[:, :2] = insert_contact_force_xy_socket
                        zero_pos_w = torch.zeros_like(socket_pos_w)
                        identity_quat_w = socket_pos_w.new_tensor(IDENTITY_QUAT).unsqueeze(0).repeat(
                            socket_pos_w.shape[0], 1
                        )
                        insert_contact_force_xy_offset_w, _ = combine_frame_transforms(
                            zero_pos_w,
                            socket_quat_w,
                            insert_contact_force_xy_offset_socket,
                            identity_quat_w,
                        )
                        insert_contact_force_xy_target_w = target_action_pos_w + insert_contact_force_xy_offset_w
                        target_pos_w[insert_contact_force_active_mask, :2] = insert_contact_force_xy_target_w[
                            insert_contact_force_active_mask, :2
                        ]
                if args_cli.insert_rotation_gated_descent:
                    gate_rot_tolerance = torch.full_like(
                        orientation_error,
                        max(0.0, insert_descent_rot_tolerance),
                    )
                    gate_descent_scale = torch.full_like(
                        action_pos_w[:, 2],
                        max(0.0, min(1.0, args_cli.insert_rotation_gate_descent_scale)),
                    )
                    gate_min_descent_step = torch.full_like(
                        action_pos_w[:, 2],
                        max(0.0, args_cli.insert_rotation_gate_min_descent_step),
                    )
                    near_depth_gate_mask = torch.zeros_like(insert_mask)
                    if args_cli.insert_rotation_gate_near_depth_z_tol is not None:
                        near_depth_gate_mask = insert_mask & (
                            axial_error < max(0.0, args_cli.insert_rotation_gate_near_depth_z_tol)
                        )
                        if args_cli.insert_rotation_gate_near_depth_rot_tol is not None:
                            gate_rot_tolerance[near_depth_gate_mask] = max(
                                0.0,
                                args_cli.insert_rotation_gate_near_depth_rot_tol,
                            )
                        if args_cli.insert_rotation_gate_near_depth_descent_scale is not None:
                            gate_descent_scale[near_depth_gate_mask] = max(
                                0.0,
                                min(1.0, args_cli.insert_rotation_gate_near_depth_descent_scale),
                            )
                        if args_cli.insert_rotation_gate_near_depth_min_descent_step is not None:
                            gate_min_descent_step[near_depth_gate_mask] = max(
                                0.0,
                                args_cli.insert_rotation_gate_near_depth_min_descent_step,
                            )
                    insert_rotation_gate_mask = (
                        insert_mask & ~depth_rotation_polish_mask & (orientation_error > gate_rot_tolerance)
                    )
                    if insert_rotation_gate_mask.any():
                        requested_descent = torch.clamp(
                            action_pos_w[:, 2] - target_pos_w[:, 2],
                            min=0.0,
                        )
                        scaled_descent = requested_descent * gate_descent_scale
                        if gate_min_descent_step.max().item() > 0.0:
                            scaled_descent = torch.where(
                                requested_descent > 0.0,
                                torch.maximum(scaled_descent, gate_min_descent_step),
                                scaled_descent,
                            )
                        insert_rotation_gate_allowed_descent = torch.minimum(requested_descent, scaled_descent)
                        target_pos_w[insert_rotation_gate_mask, 2] = (
                            action_pos_w[insert_rotation_gate_mask, 2]
                            - insert_rotation_gate_allowed_descent[insert_rotation_gate_mask]
                        )
                        insert_rotation_gate_step_count += 1
                        insert_rotation_gate_first_step = (
                            step if insert_rotation_gate_first_step is None else insert_rotation_gate_first_step
                        )
                        insert_rotation_gate_last_step = step
                        current_max_rot = orientation_error[insert_rotation_gate_mask].max().item()
                        insert_rotation_gate_max_rot = (
                            current_max_rot
                            if insert_rotation_gate_max_rot is None
                            else max(insert_rotation_gate_max_rot, current_max_rot)
                        )
                        current_allowed_descent = insert_rotation_gate_allowed_descent[
                            insert_rotation_gate_mask
                        ].max().item()
                        insert_rotation_gate_allowed_descent_max = max(
                            insert_rotation_gate_allowed_descent_max,
                            current_allowed_descent,
                        )
            _trace_phase("after_insert_target_update", step)
            if depth_rotation_polish_mask.any():
                target_pos_w[depth_rotation_polish_mask, :2] = target_action_pos_w[
                    depth_rotation_polish_mask, :2
                ]
                preload_step = max(0.0, args_cli.depth_rotation_polish_preload_step)
                if preload_step > 0.0:
                    depth_rotation_polish_z = torch.maximum(
                        target_action_pos_w[:, 2],
                        action_pos_w[:, 2] - preload_step,
                    )
                else:
                    depth_rotation_polish_z = action_pos_w[:, 2]
                target_pos_w[depth_rotation_polish_mask, 2] = depth_rotation_polish_z[
                    depth_rotation_polish_mask
                ]
                target_quat_w[depth_rotation_polish_mask] = depth_rotation_polish_target_quat_w[
                    depth_rotation_polish_mask
                ]
                depth_rotation_polish_step_count += 1
                depth_rotation_polish_first_step = (
                    step if depth_rotation_polish_first_step is None else depth_rotation_polish_first_step
                )
                depth_rotation_polish_last_step = step
                current_depth_polish_max_rot = orientation_error[depth_rotation_polish_mask].max().item()
                current_depth_polish_max_lateral = lateral_error[depth_rotation_polish_mask].max().item()
                current_depth_polish_min_axial = axial_error[depth_rotation_polish_mask].min().item()
                depth_rotation_polish_max_rot = (
                    current_depth_polish_max_rot
                    if depth_rotation_polish_max_rot is None
                    else max(depth_rotation_polish_max_rot, current_depth_polish_max_rot)
                )
                depth_rotation_polish_max_lateral = (
                    current_depth_polish_max_lateral
                    if depth_rotation_polish_max_lateral is None
                    else max(depth_rotation_polish_max_lateral, current_depth_polish_max_lateral)
                )
                depth_rotation_polish_min_axial = (
                    current_depth_polish_min_axial
                    if depth_rotation_polish_min_axial is None
                    else min(depth_rotation_polish_min_axial, current_depth_polish_min_axial)
                )
            _trace_phase("before_polish_settle_state", step)
            polish_mask = (lateral_error < args_cli.polish_xy_tol) & (axial_error < args_cli.polish_z_tol)
            if args_cli.polish_rot_tol is not None:
                polish_mask &= orientation_error < args_cli.polish_rot_tol
            polish_state |= polish_mask
            settle_mask = polish_state & (lateral_error < args_cli.settle_xy_tol) & (orientation_error < args_cli.settle_rot_tol)
            settle_state = settle_mask

            if args_cli.settle_contact_retention:
                retention_min_force = (
                    success_min_contact_force
                    if args_cli.settle_contact_min_force is None
                    else max(0.0, args_cli.settle_contact_min_force)
                )
                retention_xy_tol = (
                    success_xy_tolerance if args_cli.settle_contact_xy_tol is None else args_cli.settle_contact_xy_tol
                )
                retention_z_tol = (
                    success_z_tolerance if args_cli.settle_contact_z_tol is None else args_cli.settle_contact_z_tol
                )
                retention_rot_tol = (
                    success_rot_tolerance if args_cli.settle_contact_rot_tol is None else args_cli.settle_contact_rot_tol
                )
                contact_retention_ready = (
                    polish_state
                    & (lateral_error < retention_xy_tol)
                    & (axial_error < retention_z_tol)
                    & (orientation_error < retention_rot_tol)
                )
                if retention_min_force > 0.0 and pre_contact_force_magnitude is not None:
                    contact_retention_ready &= pre_contact_force_magnitude.squeeze(-1) < retention_min_force
                elif retention_min_force > 0.0:
                    contact_retention_ready &= torch.zeros_like(contact_retention_ready)
                contact_retention_entry = contact_retention_ready & ~contact_retention_state
                if args_cli.settle_contact_hold_xy and contact_retention_entry.any():
                    contact_retention_anchor_pos_w[contact_retention_entry] = action_pos_w[contact_retention_entry]
                contact_retention_state |= contact_retention_ready
                contact_retention_exit = (
                    (lateral_error > args_cli.settle_contact_exit_xy_tol)
                    | (axial_error > args_cli.settle_contact_exit_z_tol)
                    | (orientation_error > args_cli.settle_contact_exit_rot_tol)
                )
                contact_retention_state &= ~contact_retention_exit
            else:
                contact_retention_state &= torch.zeros_like(contact_retention_state)

            seating_state = settle_state | contact_retention_state
            polish_only = polish_state & ~seating_state & ~depth_rotation_polish_mask
            target_pos_w[polish_only, 2] = action_pos_w[polish_only, 2]
            standard_polish_state = polish_state & ~depth_rotation_polish_mask
            if standard_polish_state.any():
                if args_cli.polish_rotation_mode == "current":
                    target_quat_w[standard_polish_state] = action_quat_w[standard_polish_state]
                elif args_cli.polish_rotation_mode == "insert-hold":
                    target_quat_w[standard_polish_state] = torch.where(
                        insert_hold_valid[standard_polish_state, None],
                        insert_hold_quat_w[standard_polish_state],
                        action_quat_w[standard_polish_state],
                    )
                else:
                    target_quat_w[standard_polish_state] = target_action_quat_w[standard_polish_state]
            if contact_retention_state.any():
                if args_cli.settle_contact_hold_xy:
                    target_pos_w[contact_retention_state, :2] = contact_retention_anchor_pos_w[
                        contact_retention_state, :2
                    ]
                contact_force_xy_offset_w = torch.zeros_like(target_pos_w)
                contact_force_xy_target_w = target_action_pos_w
                if args_cli.settle_contact_force_aware_xy and pre_contact_force_socket is not None:
                    contact_force_xy_socket = (
                        args_cli.settle_contact_force_xy_sign
                        * args_cli.settle_contact_force_xy_gain
                        * pre_contact_force_socket[:, :2]
                    )
                    contact_force_xy_socket = _clamp_actions(
                        contact_force_xy_socket,
                        max(0.0, args_cli.settle_contact_force_xy_clamp),
                    )
                    contact_force_offset_socket = torch.zeros_like(target_pos_w)
                    contact_force_offset_socket[:, :2] = contact_force_xy_socket
                    contact_force_xy_offset_w = _quat_rotate_wxyz(socket_quat_w, contact_force_offset_socket)
                    contact_force_xy_target_w = target_action_pos_w + contact_force_xy_offset_w
                    target_pos_w[contact_retention_state, :2] = contact_force_xy_target_w[
                        contact_retention_state, :2
                    ]
                preload_step = max(0.0, args_cli.settle_contact_preload_step)
                if preload_step > 0.0:
                    preload_z = action_pos_w[:, 2] - preload_step
                    target_pos_w[contact_retention_state, 2] = torch.minimum(
                        target_pos_w[contact_retention_state, 2],
                        preload_z[contact_retention_state],
                    )
            else:
                contact_force_xy_offset_w = torch.zeros_like(target_pos_w)
                contact_force_xy_target_w = target_action_pos_w
            if depth_rotation_polish_mask.any():
                target_pos_w[depth_rotation_polish_mask, :2] = target_action_pos_w[
                    depth_rotation_polish_mask, :2
                ]
                preload_step = max(0.0, args_cli.depth_rotation_polish_preload_step)
                if preload_step > 0.0:
                    depth_rotation_polish_z = torch.maximum(
                        target_action_pos_w[:, 2],
                        action_pos_w[:, 2] - preload_step,
                    )
                else:
                    depth_rotation_polish_z = action_pos_w[:, 2]
                target_pos_w[depth_rotation_polish_mask, 2] = depth_rotation_polish_z[
                    depth_rotation_polish_mask
                ]
                target_quat_w[depth_rotation_polish_mask] = depth_rotation_polish_target_quat_w[
                    depth_rotation_polish_mask
                ]
            _trace_phase("after_polish_settle_state", step)

            _trace_phase("before_final_contact_servo_state", step)
            if args_cli.final_contact_servo:
                final_contact_servo_entry_xy_tolerance = max(0.0, args_cli.final_contact_servo_entry_xy_tol)
                final_contact_servo_entry_z_tolerance = max(0.0, args_cli.final_contact_servo_entry_z_tol)
                final_contact_servo_entry_rot_tolerance = (
                    success_rot_tolerance
                    if args_cli.final_contact_servo_entry_rot_tol is None
                    else max(0.0, args_cli.final_contact_servo_entry_rot_tol)
                )
                final_contact_servo_exit_xy_tolerance = max(0.0, args_cli.final_contact_servo_exit_xy_tol)
                final_contact_servo_exit_rot_tolerance = (
                    insert_abort_rot_tolerance
                    if args_cli.final_contact_servo_exit_rot_tol is None
                    else max(0.0, args_cli.final_contact_servo_exit_rot_tol)
                )
                final_contact_servo_phase_mask = insert_mask | polish_state
                final_contact_servo_ready = (
                    final_contact_servo_phase_mask
                    & polish_state
                    & (lateral_error < final_contact_servo_entry_xy_tolerance)
                    & (axial_error < final_contact_servo_entry_z_tolerance)
                    & (orientation_error < final_contact_servo_entry_rot_tolerance)
                )
                final_contact_servo_entry_mask = final_contact_servo_ready & ~final_contact_servo_state
                final_contact_servo_state |= final_contact_servo_ready
                final_contact_servo_exit_mask = final_contact_servo_state & (
                    ~final_contact_servo_phase_mask
                    | (lateral_error > final_contact_servo_exit_xy_tolerance)
                    | (orientation_error > final_contact_servo_exit_rot_tolerance)
                )
                final_contact_servo_state &= ~final_contact_servo_exit_mask
                final_contact_servo_mask = final_contact_servo_state & final_contact_servo_phase_mask
                if final_contact_servo_entry_mask.any():
                    final_contact_servo_entry_count += int(final_contact_servo_entry_mask.sum().item())
                if final_contact_servo_exit_mask.any():
                    final_contact_servo_exit_count += int(final_contact_servo_exit_mask.sum().item())
            else:
                final_contact_servo_entry_xy_tolerance = max(0.0, args_cli.final_contact_servo_entry_xy_tol)
                final_contact_servo_entry_z_tolerance = max(0.0, args_cli.final_contact_servo_entry_z_tol)
                final_contact_servo_entry_rot_tolerance = (
                    success_rot_tolerance
                    if args_cli.final_contact_servo_entry_rot_tol is None
                    else max(0.0, args_cli.final_contact_servo_entry_rot_tol)
                )
                final_contact_servo_exit_xy_tolerance = max(0.0, args_cli.final_contact_servo_exit_xy_tol)
                final_contact_servo_exit_rot_tolerance = (
                    insert_abort_rot_tolerance
                    if args_cli.final_contact_servo_exit_rot_tol is None
                    else max(0.0, args_cli.final_contact_servo_exit_rot_tol)
                )
                final_contact_servo_state &= torch.zeros_like(final_contact_servo_state)
            _trace_phase("after_final_contact_servo_state", step)

            _trace_phase("before_final_contact_servo_command", step)
            if final_contact_servo_mask.any():
                final_contact_servo_use_metric_z = (
                    args_cli.final_contact_servo_metric_error or args_cli.final_contact_servo_metric_z
                )
                final_contact_servo_use_metric_xy = (
                    args_cli.final_contact_servo_metric_error or args_cli.final_contact_servo_metric_xy
                )
                final_contact_servo_metric_error_socket = (
                    metric_tip_rel_socket_pos if final_contact_servo_use_metric_xy else physical_tip_rel_socket_pos
                )
                final_contact_servo_xy_offset_socket[:, :2] = _clamp_actions(
                    -max(0.0, args_cli.final_contact_servo_xy_gain) * final_contact_servo_metric_error_socket[:, :2],
                    max(0.0, args_cli.final_contact_servo_xy_clamp),
                )
                if final_contact_servo_use_metric_z:
                    final_contact_servo_xy_offset_socket[:, 2] = _clamp_actions(
                        -max(0.0, args_cli.final_contact_servo_z_gain) * metric_tip_rel_socket_pos[:, 2],
                        max(0.0, args_cli.final_contact_servo_z_step),
                    )
                    final_contact_servo_xy_offset_w = _quat_rotate_wxyz(
                        socket_quat_w,
                        final_contact_servo_xy_offset_socket,
                    )
                    final_contact_servo_xy_target_w = action_pos_w + final_contact_servo_xy_offset_w
                    if args_cli.final_contact_servo_metric_error:
                        target_pos_w[final_contact_servo_mask] = final_contact_servo_xy_target_w[
                            final_contact_servo_mask
                        ]
                    else:
                        target_pos_w[final_contact_servo_mask, :2] = final_contact_servo_xy_target_w[
                            final_contact_servo_mask, :2
                        ]
                        target_pos_w[final_contact_servo_mask, 2] = final_contact_servo_xy_target_w[
                            final_contact_servo_mask, 2
                        ]
                    final_contact_servo_requested_descent = torch.abs(metric_tip_rel_socket_pos[:, 2])
                else:
                    final_contact_servo_xy_offset_w = _quat_rotate_wxyz(
                        socket_quat_w,
                        final_contact_servo_xy_offset_socket,
                    )
                    final_contact_servo_xy_target_w = action_pos_w + final_contact_servo_xy_offset_w
                    target_pos_w[final_contact_servo_mask, :2] = final_contact_servo_xy_target_w[
                        final_contact_servo_mask, :2
                    ]
                    final_contact_servo_requested_descent = torch.clamp(
                        action_pos_w[:, 2] - target_action_pos_w[:, 2],
                        min=0.0,
                    )
                    final_contact_servo_descent_step = torch.minimum(
                        final_contact_servo_requested_descent,
                        torch.full_like(
                            final_contact_servo_requested_descent,
                            max(0.0, args_cli.final_contact_servo_z_step),
                        ),
                    )
                    final_contact_servo_z_target = action_pos_w[:, 2] - final_contact_servo_descent_step
                    final_contact_servo_z_target = torch.maximum(final_contact_servo_z_target, target_action_pos_w[:, 2])
                    if args_cli.final_contact_servo_hold_z_when_axial_ready:
                        final_contact_servo_z_hold_mask = (
                            final_contact_servo_mask
                            & (axial_error < success_z_tolerance)
                            & (lateral_error >= success_xy_tolerance)
                        )
                        final_contact_servo_z_target = torch.where(
                            final_contact_servo_z_hold_mask,
                            action_pos_w[:, 2],
                            final_contact_servo_z_target,
                        )
                    target_pos_w[final_contact_servo_mask, 2] = final_contact_servo_z_target[
                        final_contact_servo_mask
                    ]
                    if final_contact_servo_z_hold_mask.any():
                        final_contact_servo_z_hold_count += int(final_contact_servo_z_hold_mask.sum().item())
                if args_cli.final_contact_servo_orientation_mode == "current":
                    target_quat_w[final_contact_servo_mask] = action_quat_w[final_contact_servo_mask]
                elif args_cli.final_contact_servo_orientation_mode == "insert-hold":
                    target_quat_w[final_contact_servo_mask] = torch.where(
                        insert_hold_valid[final_contact_servo_mask, None],
                        insert_hold_quat_w[final_contact_servo_mask],
                        action_quat_w[final_contact_servo_mask],
                    )
                else:
                    target_quat_w[final_contact_servo_mask] = target_action_quat_w[
                        final_contact_servo_mask
                    ]
                final_contact_servo_step_count += 1
                final_contact_servo_first_step = (
                    step if final_contact_servo_first_step is None else final_contact_servo_first_step
                )
                final_contact_servo_last_step = step
                current_final_contact_max_lateral = lateral_error[final_contact_servo_mask].max().item()
                current_final_contact_min_axial = axial_error[final_contact_servo_mask].min().item()
                current_final_contact_xy_offset = torch.linalg.norm(
                    final_contact_servo_xy_offset_socket[final_contact_servo_mask, :2],
                    dim=-1,
                ).max().item()
                final_contact_servo_max_lateral = (
                    current_final_contact_max_lateral
                    if final_contact_servo_max_lateral is None
                    else max(final_contact_servo_max_lateral, current_final_contact_max_lateral)
                )
                final_contact_servo_min_axial = (
                    current_final_contact_min_axial
                    if final_contact_servo_min_axial is None
                    else min(final_contact_servo_min_axial, current_final_contact_min_axial)
                )
                final_contact_servo_max_xy_offset = max(
                    final_contact_servo_max_xy_offset,
                    current_final_contact_xy_offset,
                )
            _trace_phase("after_final_contact_servo_command", step)

            _trace_phase("before_socket_insertion_servo_state", step)
            if args_cli.socket_insertion_servo:
                socket_insertion_servo_entry_xy_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_entry_xy_tol,
                )
                socket_insertion_servo_entry_z_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_entry_z_tol,
                )
                socket_insertion_servo_entry_rot_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_entry_rot_tol,
                )
                socket_insertion_servo_exit_xy_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_exit_xy_tol,
                )
                socket_insertion_servo_exit_z_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_exit_z_tol,
                )
                socket_insertion_servo_exit_rot_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_exit_rot_tol,
                )
                socket_insertion_servo_phase_mask = insert_mask | polish_state | settle_state
                socket_insertion_servo_ready = (
                    socket_insertion_servo_phase_mask
                    & (lateral_error < socket_insertion_servo_entry_xy_tolerance)
                    & (axial_error < socket_insertion_servo_entry_z_tolerance)
                    & (orientation_error < socket_insertion_servo_entry_rot_tolerance)
                )
                socket_insertion_servo_entry_mask = (
                    socket_insertion_servo_ready & ~socket_insertion_servo_state
                )
                socket_insertion_servo_state |= socket_insertion_servo_ready
                socket_insertion_servo_soft_exit_mask = socket_insertion_servo_state & (
                    (lateral_error > socket_insertion_servo_exit_xy_tolerance)
                    | (axial_error > socket_insertion_servo_exit_z_tolerance)
                    | (orientation_error > socket_insertion_servo_exit_rot_tolerance)
                )
                if args_cli.socket_insertion_servo_strict_exit:
                    socket_insertion_servo_hard_exit_mask = socket_insertion_servo_soft_exit_mask
                else:
                    socket_insertion_servo_hard_exit_mask = socket_insertion_servo_state & (
                        (lateral_error > max(0.0, args_cli.socket_insertion_servo_hard_exit_xy_tol))
                        | (axial_error > max(0.0, args_cli.socket_insertion_servo_hard_exit_z_tol))
                        | (orientation_error > max(0.0, args_cli.socket_insertion_servo_hard_exit_rot_tol))
                    )
                    socket_insertion_servo_recovery_mask = (
                        socket_insertion_servo_soft_exit_mask
                        & ~socket_insertion_servo_hard_exit_mask
                        & socket_insertion_servo_phase_mask
                    )
                socket_insertion_servo_exit_mask = socket_insertion_servo_state & (
                    ~socket_insertion_servo_phase_mask | socket_insertion_servo_hard_exit_mask
                )
                socket_insertion_servo_state &= ~socket_insertion_servo_exit_mask
                socket_insertion_servo_mask = socket_insertion_servo_state & socket_insertion_servo_phase_mask
                if socket_insertion_servo_entry_mask.any():
                    socket_insertion_servo_entry_count += int(socket_insertion_servo_entry_mask.sum().item())
                    socket_insertion_servo_command_quat_w[socket_insertion_servo_entry_mask] = action_quat_w[
                        socket_insertion_servo_entry_mask
                    ]
                    socket_insertion_servo_command_valid[socket_insertion_servo_entry_mask] = True
                if socket_insertion_servo_exit_mask.any():
                    socket_insertion_servo_exit_count += int(socket_insertion_servo_exit_mask.sum().item())
                    socket_insertion_servo_command_valid[socket_insertion_servo_exit_mask] = False
                socket_insertion_servo_command_valid &= socket_insertion_servo_state
            else:
                socket_insertion_servo_entry_xy_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_entry_xy_tol,
                )
                socket_insertion_servo_entry_z_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_entry_z_tol,
                )
                socket_insertion_servo_entry_rot_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_entry_rot_tol,
                )
                socket_insertion_servo_exit_xy_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_exit_xy_tol,
                )
                socket_insertion_servo_exit_z_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_exit_z_tol,
                )
                socket_insertion_servo_exit_rot_tolerance = max(
                    0.0,
                    args_cli.socket_insertion_servo_exit_rot_tol,
                )
                socket_insertion_servo_state &= torch.zeros_like(socket_insertion_servo_state)
                socket_insertion_servo_command_valid &= torch.zeros_like(socket_insertion_servo_command_valid)
            _trace_phase("after_socket_insertion_servo_state", step)

            _trace_phase("before_socket_insertion_servo_command", step)
            if socket_insertion_servo_mask.any():
                _trace_phase("before_socket_insertion_servo_config", step)
                socket_insertion_servo_descend_xy_tolerance = (
                    success_xy_tolerance
                    if args_cli.socket_insertion_servo_descend_xy_tol is None
                    else max(0.0, args_cli.socket_insertion_servo_descend_xy_tol)
                )
                socket_insertion_servo_descend_rot_tolerance = (
                    success_rot_tolerance
                    if args_cli.socket_insertion_servo_descend_rot_tol is None
                    else max(0.0, args_cli.socket_insertion_servo_descend_rot_tol)
                )
                socket_insertion_servo_config = SocketInsertionServoConfig(
                    xy_gain=max(0.0, args_cli.socket_insertion_servo_xy_gain),
                    xy_clamp=max(0.0, args_cli.socket_insertion_servo_xy_clamp),
                    z_gain=max(0.0, args_cli.socket_insertion_servo_z_gain),
                    z_step=max(0.0, args_cli.socket_insertion_servo_z_step),
                    descend_xy_tolerance=socket_insertion_servo_descend_xy_tolerance,
                    descend_rot_tolerance=socket_insertion_servo_descend_rot_tolerance,
                    success_z_tolerance=success_z_tolerance,
                    contact_preload_step=max(0.0, args_cli.socket_insertion_servo_contact_preload_step),
                    maintain_contact_preload=args_cli.socket_insertion_servo_maintain_contact_preload,
                    success_min_contact_force=success_min_contact_force,
                    contact_boundary_min_force=max(
                        0.0,
                        args_cli.socket_insertion_servo_contact_boundary_min_force,
                    ),
                    contact_boundary_tolerance=max(
                        0.0,
                        args_cli.socket_insertion_servo_contact_boundary_tol,
                    ),
                    contact_boundary_step=max(
                        0.0,
                        args_cli.socket_insertion_servo_contact_boundary_step,
                    ),
                    contact_boundary_xy_gain=max(
                        0.0,
                        args_cli.socket_insertion_servo_contact_boundary_xy_gain,
                    ),
                    contact_boundary_xy_clamp=max(
                        0.0,
                        args_cli.socket_insertion_servo_contact_boundary_xy_clamp,
                    ),
                )
                _trace_phase("after_socket_insertion_servo_config", step)
                _trace_phase("before_socket_insertion_servo_offset", step)
                socket_insertion_servo_offset_socket, socket_insertion_servo_masks = (
                    compute_socket_insertion_servo_offset(
                        metric_tip_rel_socket_pos,
                        lateral_error,
                        axial_error,
                        orientation_error,
                        pre_contact_force_magnitude,
                        socket_insertion_servo_mask,
                        socket_insertion_servo_config,
                    )
                )
                _trace_phase("after_socket_insertion_servo_offset", step)
                socket_insertion_servo_xy_ready_mask = socket_insertion_servo_masks["xy_ready"]
                socket_insertion_servo_rot_ready_mask = socket_insertion_servo_masks["rot_ready"]
                socket_insertion_servo_axial_ready_mask = socket_insertion_servo_masks["axial_ready"]
                socket_insertion_servo_contact_ready_mask = socket_insertion_servo_masks["contact_ready"]
                socket_insertion_servo_boundary_contact_ready_mask = socket_insertion_servo_masks[
                    "boundary_contact_ready"
                ]
                socket_insertion_servo_descend_ready_mask = socket_insertion_servo_masks["descend_ready"]
                socket_insertion_servo_contact_boundary_mask = socket_insertion_servo_masks["contact_boundary"]
                socket_insertion_servo_contact_preload_mask = socket_insertion_servo_masks["contact_preload"]
                socket_insertion_servo_maintained_contact_preload_mask = socket_insertion_servo_masks[
                    "maintained_contact_preload"
                ]
                socket_insertion_servo_contact_boundary_preload_mask = socket_insertion_servo_masks[
                    "contact_boundary_preload"
                ]
                socket_insertion_servo_z_hold_mask = socket_insertion_servo_masks["hold_z"]
                _trace_phase("before_socket_insertion_servo_offset_rotate", step)
                socket_insertion_servo_offset_w = _quat_rotate_wxyz(
                    socket_quat_w,
                    socket_insertion_servo_offset_socket,
                )
                _trace_phase("after_socket_insertion_servo_offset_rotate", step)
                socket_insertion_servo_target_w = action_pos_w + socket_insertion_servo_offset_w
                _trace_phase("before_socket_insertion_servo_target_update", step)
                target_pos_w[socket_insertion_servo_mask] = socket_insertion_servo_target_w[
                    socket_insertion_servo_mask
                ]
                _trace_phase("after_socket_insertion_servo_target_update", step)
                socket_insertion_servo_command_seed_mask = (
                    socket_insertion_servo_mask & ~socket_insertion_servo_command_valid
                )
                if socket_insertion_servo_command_seed_mask.any():
                    socket_insertion_servo_command_quat_w[socket_insertion_servo_command_seed_mask] = action_quat_w[
                        socket_insertion_servo_command_seed_mask
                    ]
                    socket_insertion_servo_command_valid[socket_insertion_servo_command_seed_mask] = True
                socket_insertion_servo_rotate_mask = socket_insertion_servo_mask.clone()
                if args_cli.socket_insertion_servo_rotate_only_when_rot_misaligned:
                    socket_insertion_servo_rotate_mask &= ~socket_insertion_servo_rot_ready_mask
                if not args_cli.socket_insertion_servo_rotate_while_xy_misaligned:
                    socket_insertion_servo_rotate_mask &= socket_insertion_servo_xy_ready_mask
                socket_insertion_servo_orientation_hold_mask = (
                    socket_insertion_servo_mask & ~socket_insertion_servo_rotate_mask
                )
                _trace_phase("before_socket_insertion_servo_quat_update", step)
                if socket_insertion_servo_rotate_mask.any():
                    socket_insertion_servo_command_quat_w[socket_insertion_servo_rotate_mask] = _quat_step_towards(
                        socket_insertion_servo_command_quat_w[socket_insertion_servo_rotate_mask],
                        target_action_quat_w[socket_insertion_servo_rotate_mask],
                        max(0.0, args_cli.socket_insertion_servo_rot_step),
                    )
                if socket_insertion_servo_orientation_hold_mask.any():
                    socket_insertion_servo_command_quat_w[socket_insertion_servo_orientation_hold_mask] = action_quat_w[
                        socket_insertion_servo_orientation_hold_mask
                    ]
                target_quat_w[socket_insertion_servo_mask] = socket_insertion_servo_command_quat_w[
                    socket_insertion_servo_mask
                ]
                _trace_phase("after_socket_insertion_servo_quat_update", step)
                socket_insertion_servo_step_count += 1
                socket_insertion_servo_first_step = (
                    step if socket_insertion_servo_first_step is None else socket_insertion_servo_first_step
                )
                socket_insertion_servo_last_step = step
                socket_insertion_servo_descend_count += int(socket_insertion_servo_descend_ready_mask.sum().item())
                socket_insertion_servo_z_hold_count += int(socket_insertion_servo_z_hold_mask.sum().item())
                socket_insertion_servo_contact_preload_count += int(
                    socket_insertion_servo_contact_preload_mask.sum().item()
                )
                socket_insertion_servo_contact_boundary_count += int(
                    socket_insertion_servo_contact_boundary_mask.sum().item()
                )
                socket_insertion_servo_recovery_count += int(socket_insertion_servo_recovery_mask.sum().item())
                socket_insertion_servo_orientation_hold_count += int(
                    socket_insertion_servo_orientation_hold_mask.sum().item()
                )
                # Avoid extra CUDA scalar reductions here. A remote diagnostic showed
                # the rollout can die before the first env.step on these summary-only
                # stats; detailed metrics are still preserved in trace rows.
                _trace_phase("skipped_socket_insertion_servo_metric_reductions", step)
            else:
                socket_insertion_servo_descend_xy_tolerance = (
                    success_xy_tolerance
                    if args_cli.socket_insertion_servo_descend_xy_tol is None
                    else max(0.0, args_cli.socket_insertion_servo_descend_xy_tol)
                )
                socket_insertion_servo_descend_rot_tolerance = (
                    success_rot_tolerance
                    if args_cli.socket_insertion_servo_descend_rot_tol is None
                    else max(0.0, args_cli.socket_insertion_servo_descend_rot_tol)
                )
            _trace_phase("after_socket_insertion_servo_command", step)

            _trace_phase("before_pose_error_action_setup", step)
            rotate_only_mask = rotate_state & ~orientation_ready & ~insert_mask & ~polish_state
            rotate_xy_recovery_mask = torch.zeros_like(rotate_only_mask)
            if args_cli.rotate_xy_retention:
                rotate_xy_recovery_mask = rotate_only_mask & (
                    lateral_error > max(0.0, args_cli.rotate_xy_retention_tol)
                )
                if rotate_xy_recovery_mask.any():
                    target_pos_w[rotate_xy_recovery_mask, 2] = action_pos_w[rotate_xy_recovery_mask, 2]
                    target_quat_w[rotate_xy_recovery_mask] = action_quat_w[rotate_xy_recovery_mask]
                    rotate_command_valid[rotate_xy_recovery_mask] = False
                    rotate_xy_recovery_step_count += 1
                    rotate_xy_recovery_first_step = (
                        step if rotate_xy_recovery_first_step is None else rotate_xy_recovery_first_step
                    )
                    rotate_xy_recovery_last_step = step
                    current_max_lateral = lateral_error[rotate_xy_recovery_mask].max().item()
                    rotate_xy_recovery_max_lateral = (
                        current_max_lateral
                        if rotate_xy_recovery_max_lateral is None
                        else max(rotate_xy_recovery_max_lateral, current_max_lateral)
                    )
            rotate_descent_mask = rotate_descent_mask & ~rotate_xy_recovery_mask
            if rotate_descent_mask.any():
                rotate_descent_step_count += 1
                rotate_descent_first_step = step if rotate_descent_first_step is None else rotate_descent_first_step
                rotate_descent_last_step = step

            descend_xy_recovery_mask = torch.zeros_like(descend_mask)
            if args_cli.descend_xy_retention:
                descend_xy_recovery_mask = descend_mask & (
                    lateral_error > max(0.0, args_cli.descend_xy_retention_tol)
                )
                if descend_xy_recovery_mask.any():
                    target_pos_w[descend_xy_recovery_mask, 2] = action_pos_w[descend_xy_recovery_mask, 2]
                    target_quat_w[descend_xy_recovery_mask] = action_quat_w[descend_xy_recovery_mask]
                    descend_xy_recovery_step_count += 1
                    descend_xy_recovery_first_step = (
                        step if descend_xy_recovery_first_step is None else descend_xy_recovery_first_step
                    )
                    descend_xy_recovery_last_step = step
                    current_max_lateral = lateral_error[descend_xy_recovery_mask].max().item()
                    descend_xy_recovery_max_lateral = (
                        current_max_lateral
                        if descend_xy_recovery_max_lateral is None
                        else max(descend_xy_recovery_max_lateral, current_max_lateral)
                    )

            pos_error, axis_angle_error = compute_pose_error(
                action_pos_w, action_quat_w, target_pos_w, target_quat_w, rot_error_type="axis_angle"
            )
            rotate_command_mask = rotate_only_mask & ~rotate_xy_recovery_mask
            rotate_quat_hold_mask = rotate_state & ~insert_mask & ~polish_state & ~rotate_xy_recovery_mask
            # Isaac Lab's relative IK action applies translational deltas directly in the robot root frame.
            # Do not rotate the Cartesian error into the end-effector frame here.
            action_pos_error = pos_error
            signed_action_pos_error = action_pos_error * action_axis_signs

            actions = torch.zeros(env.action_space.shape, device=env_unwrapped.device)
            command_pos_w = target_pos_w
            command_quat_w = target_quat_w
            rot_gain = torch.full_like(axis_angle_error, args_cli.rot_gain)
            rot_gain[polish_state] = args_cli.polish_rot_gain
            rot_gain[depth_rotation_polish_mask] = args_cli.depth_rotation_polish_rot_gain
            rot_gain[settle_state] = args_cli.settle_rot_gain
            rot_clamp = torch.full_like(axis_angle_error, args_cli.rot_clamp)
            rot_clamp[polish_state] = args_cli.polish_rot_clamp
            rot_clamp[depth_rotation_polish_mask] = args_cli.depth_rotation_polish_rot_clamp
            rot_clamp[settle_state] = args_cli.settle_rot_clamp
            hand_target_pos_w = None
            hand_target_quat_w = None
            joint_pos_des = None
            joint_pos_des_raw = None
            joint_limit_centering_delta = None
            joint_limit_nullspace_delta = None
            joint_limit_guard_delta = None
            joint_response_delta = None
            joint_response_predicted_delta = None
            joint_response_cosine = None
            joint_response_residual_norm = None
            joint_response_clamped = False
            joint_pos = None
            joint_vel = None
            joint_limit_lower = None
            joint_limit_upper = None
            joint_limit_margin = None
            post_joint_pos = None
            post_joint_vel = None
            post_joint_limit_margin = None
            arm_joint_pos = None
            arm_joint_vel = None
            arm_joint_limit_margin = None
            post_arm_joint_pos = None
            post_arm_joint_vel = None
            post_arm_joint_limit_margin = None
            mdp_abs_command_pos_b = None
            mdp_abs_command_quat_b = None
            joint_cache_active_mask = torch.zeros_like(insert_mask)
            joint_cache_seed_mask = torch.zeros_like(insert_mask)
            joint_cache_step = args_cli.joint_cache_step if args_cli.joint_cache_step is not None else args_cli.joint_ik_step
            joint_cache_step = max(0.0, joint_cache_step)
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
            if args_cli.depth_rotation_polish_rot_step is not None and depth_rotation_polish_mask.any():
                abs_rot_step_limit[depth_rotation_polish_mask] = max(
                    0.0,
                    args_cli.depth_rotation_polish_rot_step,
                )
            if socket_insertion_servo_mask.any():
                abs_rot_step_limit[socket_insertion_servo_mask] = max(
                    0.0,
                    args_cli.socket_insertion_servo_rot_step,
                )
            _trace_phase("after_pose_error_action_setup", step)

            _trace_phase("before_control_action_solve", step)
            if scripted_control_mode == "joint-response":
                if args_cli.position_control_mode != "direct":
                    raise ValueError("calibrated position control is not supported for joint-response scripted control")
                if joint_response_matrix is None:
                    raise ValueError("joint-response matrix was not loaded")
                joint_ids = arm_joint_ids
                joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, joint_ids)
                joint_vel = _as_torch(robot.data.joint_vel).index_select(-1, joint_ids)
                joint_limit_lower, joint_limit_upper = arm_joint_limit_lower, arm_joint_limit_upper
                joint_limit_margin = _joint_limit_margin(joint_pos, joint_limit_lower, joint_limit_upper)

                desired_delta_w = command_pos_w - action_pos_w
                gram = joint_response_matrix @ joint_response_matrix.transpose(0, 1)
                damping = max(1.0e-8, float(args_cli.joint_response_damping))
                gram = gram + torch.eye(3, device=env_unwrapped.device, dtype=joint_response_matrix.dtype) * (
                    damping * damping
                )
                dual = torch.linalg.solve(gram, desired_delta_w.transpose(0, 1)).transpose(0, 1)
                joint_response_delta = dual @ joint_response_matrix
                max_abs_joint_response = torch.amax(torch.abs(joint_response_delta), dim=-1, keepdim=True)
                max_delta = max(0.0, float(args_cli.joint_response_max_delta))
                if max_delta > 0.0:
                    response_scale = torch.clamp(max_delta / torch.clamp(max_abs_joint_response, min=1.0e-12), max=1.0)
                    joint_response_clamped = bool(torch.any(response_scale < 0.999).item())
                    joint_response_delta = joint_response_delta * response_scale
                joint_response_predicted_delta = joint_response_delta @ joint_response_matrix.transpose(0, 1)
                desired_norm = torch.linalg.norm(desired_delta_w, dim=-1)
                predicted_norm = torch.linalg.norm(joint_response_predicted_delta, dim=-1)
                joint_response_cosine = torch.sum(
                    desired_delta_w * joint_response_predicted_delta,
                    dim=-1,
                ) / torch.clamp(desired_norm * predicted_norm, min=1.0e-12)
                joint_response_residual_norm = torch.linalg.norm(
                    desired_delta_w - joint_response_predicted_delta,
                    dim=-1,
                )
                joint_pos_des_raw = joint_pos + joint_response_delta
                joint_pos_des = _clamp_joint_targets(
                    robot,
                    joint_ids,
                    joint_pos,
                    joint_pos_des_raw,
                    args_cli.joint_ik_step,
                    args_cli.joint_limit_margin,
                    args_cli.joint_step_limit_mode,
                )
                actions[:, :7] = joint_pos_des
                selected_candidate_idxs = None
            elif scripted_control_mode == "joint-ik":
                if args_cli.position_control_mode != "direct":
                    raise ValueError("calibrated position control is not supported for joint-ik scripted control")
                assert diff_ik_controller is not None
                assert robot_entity_cfg is not None
                assert ee_jacobi_idx is not None
                if args_cli.abs_control_mode == "waypoint":
                    command_pos_w = action_pos_w + _limit_position_step(
                        pos_error,
                        abs_pos_step_limit,
                        args_cli.abs_pos_step_mode,
                    )
                    axis_angle_norm = torch.linalg.norm(axis_angle_error, dim=-1, keepdim=True)
                    axis_angle_scale = torch.clamp(
                        abs_rot_step_limit / torch.clamp(axis_angle_norm, min=1.0e-8),
                        max=1.0,
                    )
                    command_quat_w = _normalize_quat(
                        _quat_multiply(action_quat_w, _axis_angle_to_quat(axis_angle_error * axis_angle_scale))
                    )
                if args_cli.rotate_control_mode == "stateful-waypoint" and rotate_command_mask.any():
                    rotate_command_valid &= rotate_command_mask
                    rotate_command_seed_mask = rotate_command_mask & ~rotate_command_valid
                    if rotate_command_seed_mask.any():
                        rotate_command_quat_w[rotate_command_seed_mask] = action_quat_w[rotate_command_seed_mask]
                    rotate_command_valid[rotate_command_mask] = True
                    rotate_command_quat_w[rotate_command_mask] = _quat_step_towards(
                        rotate_command_quat_w[rotate_command_mask],
                        target_quat_w[rotate_command_mask],
                        args_cli.abs_rot_step,
                    )
                    command_quat_w[rotate_command_mask] = rotate_command_quat_w[rotate_command_mask]
                elif args_cli.rotate_control_mode == "target" and rotate_quat_hold_mask.any():
                    command_quat_w[rotate_quat_hold_mask] = target_quat_w[rotate_quat_hold_mask]
                elif args_cli.rotate_control_mode == "waypoint" and rotate_command_mask.any():
                    axis_angle_norm = torch.linalg.norm(axis_angle_error, dim=-1, keepdim=True)
                    axis_angle_scale = torch.clamp(
                        args_cli.abs_rot_step / torch.clamp(axis_angle_norm, min=1.0e-8),
                        max=1.0,
                    )
                    command_quat_w[rotate_command_mask] = _normalize_quat(
                        _quat_multiply(
                            action_quat_w,
                            _axis_angle_to_quat(axis_angle_error * axis_angle_scale),
                        )
                    )[rotate_command_mask]

                offset_pos = action_pos_w.new_tensor(BODY_OFFSET).unsqueeze(0).repeat(action_pos_w.shape[0], 1)
                offset_quat = action_pos_w.new_tensor(PEG_TIP_BODY_OFFSET_ROT).unsqueeze(0).repeat(action_pos_w.shape[0], 1)
                hand_target_pos_w, hand_target_quat_w = _child_pose_to_parent_pose_xyzw(
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
                _debug_step("before_get_jacobians", step)
                jacobians = _as_torch(robot.root_physx_view.get_jacobians())
                _debug_step("after_get_jacobians", step)
                jacobian = jacobians[:, ee_jacobi_idx, :, :].index_select(-1, joint_ids)
                joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, joint_ids)
                joint_vel = _as_torch(robot.data.joint_vel).index_select(-1, joint_ids)
                joint_limit_lower, joint_limit_upper = _selected_joint_limits(robot, joint_ids)
                joint_limit_margin = _joint_limit_margin(joint_pos, joint_limit_lower, joint_limit_upper)
                joint_pos_des_raw = diff_ik_controller.compute(hand_pos_b, hand_quat_b, jacobian, joint_pos)
                joint_limit_centering_delta = _joint_limit_centering_delta(
                    joint_pos,
                    joint_limit_lower,
                    joint_limit_upper,
                    gain=max(0.0, args_cli.joint_limit_nullspace_gain),
                    activation_margin=args_cli.joint_limit_nullspace_activation_margin,
                    max_step=max(0.0, args_cli.joint_limit_nullspace_step),
                )
                if joint_limit_centering_delta is not None:
                    joint_limit_nullspace_delta = _project_joint_delta_to_nullspace(
                        jacobian,
                        joint_limit_centering_delta,
                        damping=args_cli.joint_limit_nullspace_damping,
                    )
                    joint_limit_nullspace_delta = torch.clamp(
                        joint_limit_nullspace_delta,
                        min=-max(0.0, args_cli.joint_limit_nullspace_step),
                        max=max(0.0, args_cli.joint_limit_nullspace_step),
                    )
                    joint_pos_des_raw = joint_pos_des_raw + joint_limit_nullspace_delta
                    current_nullspace_norm = torch.linalg.norm(joint_limit_nullspace_delta[0]).item()
                    if current_nullspace_norm > max_joint_limit_nullspace_delta_norm:
                        max_joint_limit_nullspace_delta_norm = current_nullspace_norm
                        max_joint_limit_nullspace_delta_norm_step = step
                joint_limit_guard_delta = _joint_limit_centering_delta(
                    joint_pos,
                    joint_limit_lower,
                    joint_limit_upper,
                    gain=max(0.0, args_cli.joint_limit_guard_gain),
                    activation_margin=args_cli.joint_limit_guard_activation_margin,
                    max_step=max(0.0, args_cli.joint_limit_guard_step),
                )
                if joint_limit_guard_delta is not None:
                    joint_pos_des_raw = joint_pos_des_raw + joint_limit_guard_delta
                    current_guard_norm = torch.linalg.norm(joint_limit_guard_delta[0]).item()
                    if current_guard_norm > max_joint_limit_guard_delta_norm:
                        max_joint_limit_guard_delta_norm = current_guard_norm
                        max_joint_limit_guard_delta_norm_step = step
                _debug_step("after_ik_compute", step)

                def _limit_joint_targets(
                    joint_pos_raw: torch.Tensor,
                    phase_global_mask: torch.Tensor,
                    guarded_limit_margin_mask: torch.Tensor | None = None,
                ) -> torch.Tensor:
                    def _limit_with_margin(limit_margin: float) -> torch.Tensor:
                        if args_cli.joint_step_limit_mode != "after-xy-global":
                            return _clamp_joint_targets(
                                robot,
                                joint_ids,
                                joint_pos,
                                joint_pos_raw,
                                args_cli.joint_ik_step,
                                limit_margin,
                                args_cli.joint_step_limit_mode,
                            )
                        component_targets = _clamp_joint_targets(
                            robot,
                            joint_ids,
                            joint_pos,
                            joint_pos_raw,
                            args_cli.joint_ik_step,
                            limit_margin,
                            "component",
                        )
                        global_targets = _clamp_joint_targets(
                            robot,
                            joint_ids,
                            joint_pos,
                            joint_pos_raw,
                            args_cli.joint_ik_step,
                            limit_margin,
                            "global",
                        )
                        return torch.where(phase_global_mask[:, None], global_targets, component_targets)

                    limited_targets = _limit_with_margin(args_cli.joint_limit_margin)
                    if (
                        args_cli.insert_joint_limit_margin is None
                        or guarded_limit_margin_mask is None
                        or not bool(guarded_limit_margin_mask.any().item())
                    ):
                        return limited_targets

                    guarded_targets = _limit_with_margin(args_cli.insert_joint_limit_margin)
                    return torch.where(guarded_limit_margin_mask[:, None], guarded_targets, limited_targets)

                after_xy_limit_mask = xy_state | rotate_state | insert_mask | polish_state | settle_state | contact_retention_state
                insert_guarded_limit_margin_mask = insert_mask | polish_state | settle_state | contact_retention_state
                joint_pos_des = _limit_joint_targets(
                    joint_pos_des_raw,
                    after_xy_limit_mask,
                    insert_guarded_limit_margin_mask,
                )
                if args_cli.insert_descent_mode == "joint-cache" and insert_mask.any():
                    joint_cache_active_mask = insert_mask
                    if args_cli.joint_cache_live_polish:
                        joint_cache_active_mask &= ~polish_state
                    joint_cache_seed_mask = joint_cache_active_mask & ~insert_joint_cache_valid
                    if joint_cache_seed_mask.any():
                        seed_target = _limit_joint_targets(
                            joint_pos_des_raw,
                            joint_cache_seed_mask,
                            joint_cache_seed_mask,
                        )
                        seed_direction = (seed_target - joint_pos) * args_cli.joint_cache_step_scale
                        seed_direction = torch.clamp(seed_direction, min=-joint_cache_step, max=joint_cache_step)
                        insert_joint_cache_anchor[joint_cache_seed_mask] = joint_pos[joint_cache_seed_mask]
                        insert_joint_cache_direction[joint_cache_seed_mask] = seed_direction[joint_cache_seed_mask]
                        insert_joint_cache_step_counts[joint_cache_seed_mask] = 0
                        insert_joint_cache_valid[joint_cache_seed_mask] = True

                    joint_cache_valid_mask = joint_cache_active_mask & insert_joint_cache_valid
                    if joint_cache_valid_mask.any():
                        cached_joint_pos_des_raw = joint_pos + insert_joint_cache_direction
                        total_limit = max(0.0, args_cli.joint_cache_total_limit)
                        cached_joint_pos_des_raw = torch.minimum(
                            torch.maximum(
                                cached_joint_pos_des_raw,
                                insert_joint_cache_anchor - total_limit,
                            ),
                            insert_joint_cache_anchor + total_limit,
                        )
                        cached_joint_pos_des = _limit_joint_targets(
                            cached_joint_pos_des_raw,
                            joint_cache_valid_mask,
                            joint_cache_valid_mask,
                        )
                        joint_pos_des[joint_cache_valid_mask] = cached_joint_pos_des[joint_cache_valid_mask]
                        insert_joint_cache_step_counts[joint_cache_valid_mask] += 1
                actions[:, :7] = joint_pos_des
                selected_candidate_idxs = None
            elif action_dim == 7:
                if args_cli.position_control_mode != "direct":
                    raise ValueError("calibrated position control is only supported for 6D relative IK actions")
                selected_candidate_idxs = None
                if args_cli.abs_control_mode == "waypoint":
                    command_pos_w = action_pos_w + _limit_position_step(
                        pos_error,
                        abs_pos_step_limit,
                        args_cli.abs_pos_step_mode,
                    )
                    axis_angle_norm = torch.linalg.norm(axis_angle_error, dim=-1, keepdim=True)
                    axis_angle_scale = torch.clamp(
                        abs_rot_step_limit / torch.clamp(axis_angle_norm, min=1.0e-8),
                        max=1.0,
                    )
                    command_quat_w = _normalize_quat(
                        _quat_multiply(action_quat_w, _axis_angle_to_quat(axis_angle_error * axis_angle_scale))
                    )
                if args_cli.rotate_control_mode == "stateful-waypoint" and rotate_command_mask.any():
                    rotate_command_valid &= rotate_command_mask
                    rotate_command_seed_mask = rotate_command_mask & ~rotate_command_valid
                    if rotate_command_seed_mask.any():
                        rotate_command_quat_w[rotate_command_seed_mask] = action_quat_w[rotate_command_seed_mask]
                    rotate_command_valid[rotate_command_mask] = True
                    rotate_command_quat_w[rotate_command_mask] = _quat_step_towards(
                        rotate_command_quat_w[rotate_command_mask],
                        target_quat_w[rotate_command_mask],
                        args_cli.abs_rot_step,
                    )
                    command_quat_w[rotate_command_mask] = rotate_command_quat_w[rotate_command_mask]
                elif args_cli.rotate_control_mode == "target" and rotate_quat_hold_mask.any():
                    command_quat_w[rotate_quat_hold_mask] = target_quat_w[rotate_quat_hold_mask]
                elif args_cli.rotate_control_mode == "waypoint" and rotate_command_mask.any():
                    axis_angle_norm = torch.linalg.norm(axis_angle_error, dim=-1, keepdim=True)
                    axis_angle_scale = torch.clamp(
                        args_cli.abs_rot_step / torch.clamp(axis_angle_norm, min=1.0e-8),
                        max=1.0,
                    )
                    command_quat_w[rotate_command_mask] = _normalize_quat(
                        _quat_multiply(
                            action_quat_w,
                            _axis_angle_to_quat(axis_angle_error * axis_angle_scale),
                        )
                    )[rotate_command_mask]
                if args_cli.mdp_abs_orientation_command_mode == "current":
                    command_quat_w = action_quat_w.clone()
                if args_cli.mdp_abs_action_frame == "root":
                    root_pose_w = _as_torch(robot.data.root_pose_w)
                    mdp_abs_command_pos_b, mdp_abs_command_quat_b = subtract_frame_transforms(
                        root_pose_w[:, 0:3],
                        root_pose_w[:, 3:7],
                        command_pos_w,
                        command_quat_w,
                    )
                    actions[:, :3] = mdp_abs_command_pos_b
                    actions[:, 3:7] = mdp_abs_command_quat_b
                else:
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

            if action_dim == 6 and depth_rotation_polish_mask.any():
                actions[depth_rotation_polish_mask, :3] = _clamp_actions(
                    args_cli.depth_rotation_polish_pos_gain
                    * signed_action_pos_error[depth_rotation_polish_mask, :3],
                    args_cli.depth_rotation_polish_pos_clamp,
                )
                actions[depth_rotation_polish_mask, 3:6] = _clamp_actions(
                    args_cli.depth_rotation_polish_rot_gain * axis_angle_error[depth_rotation_polish_mask],
                    args_cli.depth_rotation_polish_rot_clamp,
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

            post_success_hold_mode = None
            if success_step is not None and max(1, args_cli.success_hold_steps) > 1:
                if args_cli.socket_insertion_servo and args_cli.socket_insertion_servo_maintain_contact_preload:
                    post_success_hold_mode = "socket-servo-maintain-contact-preload"
                else:
                    actions = _hold_current_or_zero_actions()
                    post_success_hold_mode = "freeze-current-action"
                post_success_hold_step_count += 1
                _append_jsonl(
                    trace_events_jsonl,
                    {
                        "event": "post_success_hold_action",
                        "step": step,
                        "success_step": success_step,
                        "success_hold_count": success_hold_count,
                        "mode": post_success_hold_mode,
                    },
                )

            _trace_phase("after_control_action_solve", step)
            arm_joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, arm_joint_ids)
            arm_joint_vel = _as_torch(robot.data.joint_vel).index_select(-1, arm_joint_ids)
            arm_joint_limit_margin = _joint_limit_margin(
                arm_joint_pos,
                arm_joint_limit_lower,
                arm_joint_limit_upper,
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
                    f"mdp_abs_action_frame={args_cli.mdp_abs_action_frame} "
                    f"mdp_abs_orientation_command_mode={args_cli.mdp_abs_orientation_command_mode} "
                    f"staged_approach={args_cli.staged_approach} "
                    f"selected_calibrated_action="
                    f"{calibrated_candidate_names[int(selected_candidate_idxs[0].item())] if selected_candidate_idxs is not None else None} "
                    f"raw_action={actions[0].tolist()} "
                    f"mdp_abs_command_pos_b={mdp_abs_command_pos_b[0].tolist() if mdp_abs_command_pos_b is not None else None} "
                    f"hand_target_pos={hand_target_pos_w[0].tolist() if hand_target_pos_w is not None else None} "
                    f"joint_response_delta={joint_response_delta[0].tolist() if joint_response_delta is not None else None} "
                    f"joint_response_predicted_delta={joint_response_predicted_delta[0].tolist() if joint_response_predicted_delta is not None else None} "
                    f"joint_response_cosine={joint_response_cosine[0].item() if joint_response_cosine is not None else None} "
                    f"joint_response_residual_norm={joint_response_residual_norm[0].item() if joint_response_residual_norm is not None else None} "
                    f"joint_response_clamped={joint_response_clamped} "
                    f"joint_pos_des_raw={joint_pos_des_raw[0].tolist() if joint_pos_des_raw is not None else None} "
                    f"joint_limit_centering_delta={joint_limit_centering_delta[0].tolist() if joint_limit_centering_delta is not None else None} "
                    f"joint_limit_nullspace_delta={joint_limit_nullspace_delta[0].tolist() if joint_limit_nullspace_delta is not None else None} "
                    f"joint_limit_guard_delta={joint_limit_guard_delta[0].tolist() if joint_limit_guard_delta is not None else None} "
                    f"joint_pos_des={joint_pos_des[0].tolist() if joint_pos_des is not None else None} "
                    f"joint_cache_active={bool(joint_cache_active_mask[0].item())} "
                    f"joint_cache_valid={bool(insert_joint_cache_valid[0].item())} "
                    f"joint_cache_direction={insert_joint_cache_direction[0].tolist()} "
                    f"joint_cache_steps={int(insert_joint_cache_step_counts[0].item())}",
                    flush=True,
                )

            _debug_step("before_env_step", step)
            _append_jsonl(trace_events_jsonl, {"event": "before_env_step", "step": step})
            env.step(actions)
            _debug_step("after_env_step", step)
            _append_jsonl(trace_events_jsonl, {"event": "after_env_step", "step": step})

            lateral, axial, rot = mdp.insertion_metrics(env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)
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
            post_metric_tip_rel_socket_pos = mdp.tip_to_socket_position(
                env_unwrapped,
                peg_cfg=peg_cfg,
                socket_cfg=socket_cfg,
            )
            post_action_tip_alignment = torch.linalg.norm(post_physical_tip_pos_w - post_action_pos_w, dim=1)
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
            success_xy_ready = lateral < success_xy_tolerance
            success_axial_ready = axial < success_z_tolerance
            success_rot_ready = rot < success_rot_tolerance
            if success_min_contact_force > 0.0:
                if contact_force_magnitude is None:
                    success_contact_ready = torch.zeros_like(success_xy_ready)
                else:
                    success_contact_ready = contact_force_magnitude.squeeze(-1) >= success_min_contact_force
            else:
                success_contact_ready = torch.ones_like(success_xy_ready)
            success = success_xy_ready & success_axial_ready & success_rot_ready & success_contact_ready
            post_arm_joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, arm_joint_ids)
            post_arm_joint_vel = _as_torch(robot.data.joint_vel).index_select(-1, arm_joint_ids)
            post_arm_joint_limit_margin = _joint_limit_margin(
                post_arm_joint_pos,
                arm_joint_limit_lower,
                arm_joint_limit_upper,
            )
            if scripted_control_mode == "joint-ik":
                assert robot_entity_cfg is not None
                joint_ids = torch.as_tensor(
                    robot_entity_cfg.joint_ids,
                    device=env_unwrapped.device,
                    dtype=torch.long,
                )
                post_joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, joint_ids)
                post_joint_vel = _as_torch(robot.data.joint_vel).index_select(-1, joint_ids)
                post_joint_limit_margin = _joint_limit_margin(post_joint_pos, joint_limit_lower, joint_limit_upper)

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
            current_arm_joint_limit_margin_argmin = int(torch.argmin(post_arm_joint_limit_margin[0]).item())
            current_arm_joint_limit_margin_min = post_arm_joint_limit_margin[
                0, current_arm_joint_limit_margin_argmin
            ].item()
            if args_cli.reachable_approach:
                reachable_approach_last_post_margin = torch.min(post_arm_joint_limit_margin, dim=-1).values
            if current_arm_joint_limit_margin_min < min_arm_joint_limit_margin:
                min_arm_joint_limit_margin = current_arm_joint_limit_margin_min
                min_arm_joint_limit_margin_step = step
                min_arm_joint_limit_margin_joint_index = current_arm_joint_limit_margin_argmin
                min_arm_joint_limit_margin_joint_name = (
                    arm_joint_names[current_arm_joint_limit_margin_argmin]
                    if current_arm_joint_limit_margin_argmin < len(arm_joint_names)
                    else None
                )
            if contact_force_magnitude is not None:
                current_contact_force = contact_force_magnitude.mean().item()
                if current_contact_force > max_contact_force_magnitude:
                    max_contact_force_magnitude = current_contact_force
                    max_contact_force_magnitude_step = step

            post_aligned_mask = (lateral < args_cli.branch_jump_aligned_xy_tol) & (
                rot < args_cli.branch_jump_aligned_rot_tol
            )
            aligned_state |= post_aligned_mask
            branch_jump_mask = aligned_state & (
                (lateral > args_cli.branch_jump_xy_tol) | (rot > args_cli.branch_jump_rot_tol)
            )
            if branch_jump_step is None and branch_jump_mask.any():
                branch_jump_step = step
                if contact_force_magnitude is not None:
                    branch_jump_contact_force_magnitude = contact_force_magnitude[0].item()
                if post_joint_limit_margin is not None:
                    branch_jump_joint_limit_margin_min = torch.min(post_joint_limit_margin[0]).item()
                branch_jump_reason = (
                    f"lateral={lateral[0].item():.4f} rot={rot[0].item():.4f} "
                    f"after_aligned={bool(aligned_state[0].item())} "
                    f"joint_margin_min={branch_jump_joint_limit_margin_min} "
                    f"contact_force={branch_jump_contact_force_magnitude}"
                )
                print(f"[SCRIPTED] branch jump detected at step={step:04d} {branch_jump_reason}", flush=True)

            if step % 25 == 0 or step == args_cli.steps - 1:
                print(
                    f"[SCRIPTED] step={step:04d} lateral={final_lateral:.4f} axial={final_axial:.4f} "
                    f"rot={final_rot:.4f} success_rate={final_success:.3f} "
                    f"success_xyzr={success_xy_ready.float().mean().item():.0f}/"
                    f"{success_axial_ready.float().mean().item():.0f}/"
                    f"{success_rot_ready.float().mean().item():.0f} "
                    f"contact_ready={success_contact_ready.float().mean().item():.0f} "
                    f"contact_force="
                    f"{contact_force_magnitude.mean().item() if contact_force_magnitude is not None else 0.0:.3f} "
                    f"action_tip_alignment={final_action_tip_alignment:.4f} "
                    f"position_ready={position_ready.float().mean().item():.3f} "
                    f"xy_ready={xy_state.float().mean().item():.3f} "
                    f"rotate_ready={rotate_state.float().mean().item():.3f} "
                    f"insert_ready={insert_mask.float().mean().item():.3f} "
                    f"depth_rot_polish={depth_rotation_polish_mask.float().mean().item():.3f} "
                    f"final_contact_servo={final_contact_servo_mask.float().mean().item():.3f} "
                    f"socket_insert_servo={socket_insertion_servo_mask.float().mean().item():.3f} "
                    f"polish_ready={polish_only.float().mean().item():.3f} "
                    f"settle_ready={settle_state.float().mean().item():.3f} "
                    f"contact_retention={contact_retention_state.float().mean().item():.3f} "
                    f"rotate_xy_recovery={rotate_xy_recovery_mask.float().mean().item():.3f} "
                    f"descend_xy_recovery={descend_xy_recovery_mask.float().mean().item():.3f}",
                    flush=True,
                )

            if args_cli.trace_json:
                if action_semantics_probe_active:
                    phase = "action-semantics-probe"
                elif socket_insertion_servo_recovery_mask[0].item():
                    phase = "socket-insertion-servo-recover"
                elif socket_insertion_servo_mask[0].item():
                    phase = "socket-insertion-servo"
                elif settle_state[0].item():
                    phase = "settle"
                elif contact_retention_state[0].item():
                    phase = "contact-retention"
                elif final_contact_servo_mask[0].item():
                    phase = "final-contact-servo"
                elif depth_rotation_polish_mask[0].item():
                    phase = "depth-rot-polish"
                elif polish_only[0].item():
                    phase = "polish"
                elif insert_rotation_gate_mask[0].item():
                    phase = "insert-rot-recover"
                elif insert_mask[0].item():
                    phase = "insert"
                elif descend_xy_recovery_mask[0].item():
                    phase = "descend-xy-recover"
                elif descend_mask[0].item():
                    phase = "descend"
                elif rotate_xy_recovery_mask[0].item():
                    phase = "rotate-xy-recover"
                elif rotate_descent_mask[0].item():
                    phase = "rotate-descend"
                elif rotate_only_mask[0].item():
                    phase = "align"
                elif rotate_state[0].item():
                    phase = "rotate"
                elif xy_state[0].item():
                    phase = "xy-align"
                elif (
                    args_cli.reachable_approach
                    and reachable_approach_radius[0].item() > reachable_approach_min_radius + 1.0e-6
                ):
                    phase = "reachable-reach"
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
                        "unbiased_target_action_pos_w": unbiased_target_action_pos_w[0].detach().cpu().tolist(),
                        "target_action_pos_w": target_action_pos_w[0].detach().cpu().tolist(),
                        "target_action_pos_offset_frame": args_cli.target_action_pos_offset_frame,
                        "target_action_pos_offset_w": target_action_pos_offset_w[0].detach().cpu().tolist(),
                        "reachable_approach": args_cli.reachable_approach,
                        "reachable_approach_radius": reachable_approach_radius[0].item(),
                        "reachable_approach_min_radius": reachable_approach_min_radius,
                        "reachable_approach_offset_dir_w": (
                            reachable_approach_offset_dir_w[0].detach().cpu().tolist()
                        ),
                        "reachable_approach_offset_w": reachable_approach_offset_w[0].detach().cpu().tolist(),
                        "reachable_approach_target_xy_error": reachable_approach_target_xy_error[0].item(),
                        "reachable_approach_last_post_margin": reachable_approach_last_post_margin[0].item(),
                        "reachable_approach_margin_ok": bool(reachable_approach_margin_ok[0].item()),
                        "reachable_approach_shrink": bool(reachable_approach_shrink_mask[0].item()),
                        "reachable_approach_margin_block": bool(
                            reachable_approach_margin_block_mask[0].item()
                        ),
                        "target_action_quat_w": target_action_quat_w[0].detach().cpu().tolist(),
                        "approach_pos_w": approach_pos_w[0].detach().cpu().tolist(),
                        "approach_axis": args_cli.approach_axis,
                        "rotate_hold_pos_w": rotate_hold_pos_w[0].detach().cpu().tolist(),
                        "rotate_hold_valid": bool(rotate_hold_valid[0].item()),
                        "rotate_command_quat_w": rotate_command_quat_w[0].detach().cpu().tolist(),
                        "rotate_command_valid": bool(rotate_command_valid[0].item()),
                        "target_pos_w": target_pos_w[0].detach().cpu().tolist(),
                        "target_quat_w": target_quat_w[0].detach().cpu().tolist(),
                        "command_pos_w": command_pos_w[0].detach().cpu().tolist(),
                        "command_quat_w": command_quat_w[0].detach().cpu().tolist(),
                        "abs_pos_step_mode": args_cli.abs_pos_step_mode,
                        "mdp_abs_action_frame": args_cli.mdp_abs_action_frame,
                        "mdp_abs_ik_method": mdp_abs_ik_method,
                        "mdp_abs_ik_params": mdp_abs_ik_params,
                        "mdp_abs_orientation_command_mode": args_cli.mdp_abs_orientation_command_mode,
                        "disable_socket_wall_collisions": args_cli.disable_socket_wall_collisions,
                        "mdp_abs_command_pos_b": (
                            mdp_abs_command_pos_b[0].detach().cpu().tolist()
                            if mdp_abs_command_pos_b is not None
                            else None
                        ),
                        "mdp_abs_command_quat_b": (
                            mdp_abs_command_quat_b[0].detach().cpu().tolist()
                            if mdp_abs_command_quat_b is not None
                            else None
                        ),
                        "hand_target_pos_w": (
                            hand_target_pos_w[0].detach().cpu().tolist() if hand_target_pos_w is not None else None
                        ),
                        "hand_target_quat_w": (
                            hand_target_quat_w[0].detach().cpu().tolist() if hand_target_quat_w is not None else None
                        ),
                        "joint_response_delta": (
                            joint_response_delta[0].detach().cpu().tolist()
                            if joint_response_delta is not None
                            else None
                        ),
                        "joint_response_predicted_delta": (
                            joint_response_predicted_delta[0].detach().cpu().tolist()
                            if joint_response_predicted_delta is not None
                            else None
                        ),
                        "joint_response_cosine": (
                            joint_response_cosine[0].item() if joint_response_cosine is not None else None
                        ),
                        "joint_response_residual_norm": (
                            joint_response_residual_norm[0].item()
                            if joint_response_residual_norm is not None
                            else None
                        ),
                        "joint_response_clamped": joint_response_clamped,
                        "joint_pos_des": joint_pos_des[0].detach().cpu().tolist() if joint_pos_des is not None else None,
                        "joint_pos_des_raw": (
                            joint_pos_des_raw[0].detach().cpu().tolist() if joint_pos_des_raw is not None else None
                        ),
                        "joint_limit_margin": args_cli.joint_limit_margin,
                        "insert_joint_limit_margin": args_cli.insert_joint_limit_margin,
                        "joint_limit_nullspace_gain": args_cli.joint_limit_nullspace_gain,
                        "joint_limit_nullspace_activation_margin": args_cli.joint_limit_nullspace_activation_margin,
                        "joint_limit_nullspace_step": args_cli.joint_limit_nullspace_step,
                        "joint_limit_nullspace_damping": args_cli.joint_limit_nullspace_damping,
                        "joint_limit_guard_gain": args_cli.joint_limit_guard_gain,
                        "joint_limit_guard_activation_margin": args_cli.joint_limit_guard_activation_margin,
                        "joint_limit_guard_step": args_cli.joint_limit_guard_step,
                        "joint_limit_centering_delta": (
                            joint_limit_centering_delta[0].detach().cpu().tolist()
                            if joint_limit_centering_delta is not None
                            else None
                        ),
                        "joint_limit_nullspace_delta": (
                            joint_limit_nullspace_delta[0].detach().cpu().tolist()
                            if joint_limit_nullspace_delta is not None
                            else None
                        ),
                        "joint_limit_nullspace_delta_norm": (
                            torch.linalg.norm(joint_limit_nullspace_delta[0]).item()
                            if joint_limit_nullspace_delta is not None
                            else None
                        ),
                        "joint_limit_guard_delta": (
                            joint_limit_guard_delta[0].detach().cpu().tolist()
                            if joint_limit_guard_delta is not None
                            else None
                        ),
                        "joint_limit_guard_delta_norm": (
                            torch.linalg.norm(joint_limit_guard_delta[0]).item()
                            if joint_limit_guard_delta is not None
                            else None
                        ),
                        "joint_pos": joint_pos[0].detach().cpu().tolist() if joint_pos is not None else None,
                        "joint_vel": joint_vel[0].detach().cpu().tolist() if joint_vel is not None else None,
                        "joint_limit_lower": (
                            joint_limit_lower[0].detach().cpu().tolist() if joint_limit_lower is not None else None
                        ),
                        "joint_limit_upper": (
                            joint_limit_upper[0].detach().cpu().tolist() if joint_limit_upper is not None else None
                        ),
                        "joint_limit_margin": (
                            joint_limit_margin[0].detach().cpu().tolist() if joint_limit_margin is not None else None
                        ),
                        "joint_limit_margin_min": (
                            torch.min(joint_limit_margin[0]).item() if joint_limit_margin is not None else None
                        ),
                        "post_joint_pos": (
                            post_joint_pos[0].detach().cpu().tolist() if post_joint_pos is not None else None
                        ),
                        "post_joint_vel": (
                            post_joint_vel[0].detach().cpu().tolist() if post_joint_vel is not None else None
                        ),
                        "post_joint_limit_margin": (
                            post_joint_limit_margin[0].detach().cpu().tolist()
                            if post_joint_limit_margin is not None
                            else None
                        ),
                        "post_joint_limit_margin_min": (
                            torch.min(post_joint_limit_margin[0]).item()
                            if post_joint_limit_margin is not None
                            else None
                        ),
                        "arm_joint_pos": arm_joint_pos[0].detach().cpu().tolist(),
                        "arm_joint_vel": arm_joint_vel[0].detach().cpu().tolist(),
                        "arm_joint_limit_margin": arm_joint_limit_margin[0].detach().cpu().tolist(),
                        "arm_joint_limit_margin_min": torch.min(arm_joint_limit_margin[0]).item(),
                        "post_arm_joint_pos": post_arm_joint_pos[0].detach().cpu().tolist(),
                        "post_arm_joint_vel": post_arm_joint_vel[0].detach().cpu().tolist(),
                        "post_arm_joint_limit_margin": post_arm_joint_limit_margin[0].detach().cpu().tolist(),
                        "post_arm_joint_limit_margin_min": torch.min(post_arm_joint_limit_margin[0]).item(),
                        "pos_error": pos_error[0].detach().cpu().tolist(),
                        "axis_angle_error": axis_angle_error[0].detach().cpu().tolist(),
                        "axis_angle_error_norm": torch.linalg.norm(axis_angle_error[0]).item(),
                        "rotate_only": bool(rotate_only_mask[0].item()),
                        "rotate_descent": bool(rotate_descent_mask[0].item()),
                        "rotate_descent_mode": args_cli.rotate_descent_mode,
                        "rotate_xy_recovery": bool(rotate_xy_recovery_mask[0].item()),
                        "descend_xy_recovery": bool(descend_xy_recovery_mask[0].item()),
                        "rotate_quat_hold": bool(rotate_quat_hold_mask[0].item()),
                        "descend_mask": bool(descend_mask[0].item()),
                        "rotate_control_mode": args_cli.rotate_control_mode,
                        "orientation_target_mode": args_cli.orientation_target_mode,
                        "hold_orientation_during_descend": args_cli.hold_orientation_during_descend,
                        "rotate_xy_retention": args_cli.rotate_xy_retention,
                        "rotate_xy_retention_tolerance": args_cli.rotate_xy_retention_tol,
                        "descend_xy_retention": args_cli.descend_xy_retention,
                        "descend_xy_retention_tolerance": args_cli.descend_xy_retention_tol,
                        "insert_after_alignment": args_cli.insert_after_alignment,
                        "insert_descent_mode": args_cli.insert_descent_mode,
                        "insert_rotation_gated_descent": args_cli.insert_rotation_gated_descent,
                        "insert_descent_rot_tolerance": insert_descent_rot_tolerance,
                        "insert_rotation_gate_descent_scale": args_cli.insert_rotation_gate_descent_scale,
                        "insert_rotation_gate_min_descent_step": args_cli.insert_rotation_gate_min_descent_step,
                        "insert_rotation_gate_near_depth_z_tolerance": (
                            args_cli.insert_rotation_gate_near_depth_z_tol
                        ),
                        "insert_rotation_gate_near_depth_rot_tolerance": (
                            args_cli.insert_rotation_gate_near_depth_rot_tol
                        ),
                        "insert_rotation_gate_near_depth_descent_scale": (
                            args_cli.insert_rotation_gate_near_depth_descent_scale
                        ),
                        "insert_rotation_gate_near_depth_min_descent_step": (
                            args_cli.insert_rotation_gate_near_depth_min_descent_step
                        ),
                        "insert_rotation_gate": bool(insert_rotation_gate_mask[0].item()),
                        "insert_rotation_gate_allowed_descent": insert_rotation_gate_allowed_descent[0].item(),
                        "insert_contact_force_aware_xy": args_cli.insert_contact_force_aware_xy,
                        "insert_contact_force_active": bool(insert_contact_force_active_mask[0].item()),
                        "insert_contact_force_min": args_cli.insert_contact_force_min,
                        "insert_contact_force_scale": args_cli.insert_contact_force_scale,
                        "insert_contact_force_xy_gain": args_cli.insert_contact_force_xy_gain,
                        "insert_contact_force_xy_clamp": args_cli.insert_contact_force_xy_clamp,
                        "insert_contact_force_xy_sign": args_cli.insert_contact_force_xy_sign,
                        "insert_contact_force_socket": (
                            pre_insert_contact_force_socket[0].detach().cpu().tolist()
                            if pre_insert_contact_force_socket is not None
                            else None
                        ),
                        "insert_contact_force_xy_offset_socket": insert_contact_force_xy_offset_socket[
                            0
                        ].detach().cpu().tolist(),
                        "insert_contact_force_xy_offset_w": insert_contact_force_xy_offset_w[
                            0
                        ].detach().cpu().tolist(),
                        "insert_contact_force_xy_target_w": insert_contact_force_xy_target_w[
                            0
                        ].detach().cpu().tolist(),
                        "final_contact_servo": args_cli.final_contact_servo,
                        "final_contact_servo_state": bool(final_contact_servo_state[0].item()),
                        "final_contact_servo_active": bool(final_contact_servo_mask[0].item()),
                        "final_contact_servo_entry": bool(final_contact_servo_entry_mask[0].item()),
                        "final_contact_servo_exit": bool(final_contact_servo_exit_mask[0].item()),
                        "final_contact_servo_entry_xy_tolerance": final_contact_servo_entry_xy_tolerance,
                        "final_contact_servo_entry_z_tolerance": final_contact_servo_entry_z_tolerance,
                        "final_contact_servo_entry_rot_tolerance": final_contact_servo_entry_rot_tolerance,
                        "final_contact_servo_exit_xy_tolerance": final_contact_servo_exit_xy_tolerance,
                        "final_contact_servo_exit_rot_tolerance": final_contact_servo_exit_rot_tolerance,
                        "final_contact_servo_xy_gain": args_cli.final_contact_servo_xy_gain,
                        "final_contact_servo_xy_clamp": args_cli.final_contact_servo_xy_clamp,
                        "final_contact_servo_metric_error": args_cli.final_contact_servo_metric_error,
                        "final_contact_servo_metric_xy": args_cli.final_contact_servo_metric_xy,
                        "final_contact_servo_metric_z": args_cli.final_contact_servo_metric_z,
                        "final_contact_servo_z_gain": args_cli.final_contact_servo_z_gain,
                        "final_contact_servo_z_step": args_cli.final_contact_servo_z_step,
                        "final_contact_servo_hold_z_when_axial_ready": (
                            args_cli.final_contact_servo_hold_z_when_axial_ready
                        ),
                        "final_contact_servo_z_hold": bool(final_contact_servo_z_hold_mask[0].item()),
                        "final_contact_servo_orientation_mode": args_cli.final_contact_servo_orientation_mode,
                        "metric_tip_rel_socket_pos": metric_tip_rel_socket_pos[
                            0
                        ].detach().cpu().tolist(),
                        "post_metric_tip_rel_socket_pos": post_metric_tip_rel_socket_pos[
                            0
                        ].detach().cpu().tolist(),
                        "final_contact_servo_metric_error_socket": final_contact_servo_metric_error_socket[
                            0
                        ].detach().cpu().tolist(),
                        "final_contact_servo_xy_offset_socket": final_contact_servo_xy_offset_socket[
                            0
                        ].detach().cpu().tolist(),
                        "final_contact_servo_xy_offset_w": final_contact_servo_xy_offset_w[
                            0
                        ].detach().cpu().tolist(),
                        "final_contact_servo_xy_target_w": final_contact_servo_xy_target_w[
                            0
                        ].detach().cpu().tolist(),
                        "final_contact_servo_requested_descent": final_contact_servo_requested_descent[0].item(),
                        "action_semantics_probe": action_semantics_probe_active,
                        "action_semantics_probe_delta": (
                            list(args_cli.action_semantics_probe_delta)
                            if args_cli.action_semantics_probe_delta is not None
                            else None
                        ),
                        "action_semantics_probe_frame": args_cli.action_semantics_probe_frame,
                        "action_semantics_probe_delta_w": action_semantics_probe_delta_w[
                            0
                        ].detach().cpu().tolist(),
                        "socket_insertion_servo": args_cli.socket_insertion_servo,
                        "insertion_success_termination_disabled": insertion_success_termination_disabled,
                        "socket_insertion_servo_state": bool(socket_insertion_servo_state[0].item()),
                        "socket_insertion_servo_active": bool(socket_insertion_servo_mask[0].item()),
                        "socket_insertion_servo_entry": bool(socket_insertion_servo_entry_mask[0].item()),
                        "socket_insertion_servo_exit": bool(socket_insertion_servo_exit_mask[0].item()),
                        "socket_insertion_servo_entry_xy_tolerance": socket_insertion_servo_entry_xy_tolerance,
                        "socket_insertion_servo_entry_z_tolerance": socket_insertion_servo_entry_z_tolerance,
                        "socket_insertion_servo_entry_rot_tolerance": socket_insertion_servo_entry_rot_tolerance,
                        "socket_insertion_servo_exit_xy_tolerance": socket_insertion_servo_exit_xy_tolerance,
                        "socket_insertion_servo_exit_z_tolerance": socket_insertion_servo_exit_z_tolerance,
                        "socket_insertion_servo_exit_rot_tolerance": socket_insertion_servo_exit_rot_tolerance,
                        "socket_insertion_servo_strict_exit": args_cli.socket_insertion_servo_strict_exit,
                        "socket_insertion_servo_hard_exit_xy_tolerance": max(
                            0.0,
                            args_cli.socket_insertion_servo_hard_exit_xy_tol,
                        ),
                        "socket_insertion_servo_hard_exit_z_tolerance": max(
                            0.0,
                            args_cli.socket_insertion_servo_hard_exit_z_tol,
                        ),
                        "socket_insertion_servo_hard_exit_rot_tolerance": max(
                            0.0,
                            args_cli.socket_insertion_servo_hard_exit_rot_tol,
                        ),
                        "socket_insertion_servo_descend_xy_tolerance": socket_insertion_servo_descend_xy_tolerance,
                        "socket_insertion_servo_descend_rot_tolerance": socket_insertion_servo_descend_rot_tolerance,
                        "socket_insertion_servo_xy_gain": args_cli.socket_insertion_servo_xy_gain,
                        "socket_insertion_servo_xy_clamp": args_cli.socket_insertion_servo_xy_clamp,
                        "socket_insertion_servo_z_gain": args_cli.socket_insertion_servo_z_gain,
                        "socket_insertion_servo_z_step": args_cli.socket_insertion_servo_z_step,
                        "socket_insertion_servo_contact_preload_step": (
                            args_cli.socket_insertion_servo_contact_preload_step
                        ),
                        "socket_insertion_servo_maintain_contact_preload": (
                            args_cli.socket_insertion_servo_maintain_contact_preload
                        ),
                        "socket_insertion_servo_contact_boundary_min_force": (
                            args_cli.socket_insertion_servo_contact_boundary_min_force
                        ),
                        "socket_insertion_servo_contact_boundary_tolerance": (
                            args_cli.socket_insertion_servo_contact_boundary_tol
                        ),
                        "socket_insertion_servo_contact_boundary_step": (
                            args_cli.socket_insertion_servo_contact_boundary_step
                        ),
                        "socket_insertion_servo_contact_boundary_xy_gain": (
                            args_cli.socket_insertion_servo_contact_boundary_xy_gain
                        ),
                        "socket_insertion_servo_contact_boundary_xy_clamp": (
                            args_cli.socket_insertion_servo_contact_boundary_xy_clamp
                        ),
                        "socket_insertion_servo_rot_step": args_cli.socket_insertion_servo_rot_step,
                        "socket_insertion_servo_rotate_only_when_rot_misaligned": (
                            args_cli.socket_insertion_servo_rotate_only_when_rot_misaligned
                        ),
                        "socket_insertion_servo_rotate_while_xy_misaligned": (
                            args_cli.socket_insertion_servo_rotate_while_xy_misaligned
                        ),
                        "socket_insertion_servo_xy_ready": bool(socket_insertion_servo_xy_ready_mask[0].item()),
                        "socket_insertion_servo_rot_ready": bool(socket_insertion_servo_rot_ready_mask[0].item()),
                        "socket_insertion_servo_axial_ready": bool(socket_insertion_servo_axial_ready_mask[0].item()),
                        "socket_insertion_servo_contact_ready": bool(
                            socket_insertion_servo_contact_ready_mask[0].item()
                        ),
                        "socket_insertion_servo_boundary_contact_ready": bool(
                            socket_insertion_servo_boundary_contact_ready_mask[0].item()
                        ),
                        "socket_insertion_servo_descend_ready": bool(
                            socket_insertion_servo_descend_ready_mask[0].item()
                        ),
                        "socket_insertion_servo_contact_boundary": bool(
                            socket_insertion_servo_contact_boundary_mask[0].item()
                        ),
                        "socket_insertion_servo_contact_preload": bool(
                            socket_insertion_servo_contact_preload_mask[0].item()
                        ),
                        "socket_insertion_servo_maintained_contact_preload": bool(
                            socket_insertion_servo_maintained_contact_preload_mask[0].item()
                        ),
                        "socket_insertion_servo_contact_boundary_preload": bool(
                            socket_insertion_servo_contact_boundary_preload_mask[0].item()
                        ),
                        "socket_insertion_servo_z_hold": bool(socket_insertion_servo_z_hold_mask[0].item()),
                        "socket_insertion_servo_soft_exit": bool(
                            socket_insertion_servo_soft_exit_mask[0].item()
                        ),
                        "socket_insertion_servo_hard_exit": bool(
                            socket_insertion_servo_hard_exit_mask[0].item()
                        ),
                        "socket_insertion_servo_recovery": bool(
                            socket_insertion_servo_recovery_mask[0].item()
                        ),
                        "socket_insertion_servo_rotate": bool(
                            socket_insertion_servo_rotate_mask[0].item()
                        ),
                        "socket_insertion_servo_orientation_hold": bool(
                            socket_insertion_servo_orientation_hold_mask[0].item()
                        ),
                        "socket_insertion_servo_command_valid": bool(
                            socket_insertion_servo_command_valid[0].item()
                        ),
                        "socket_insertion_servo_offset_socket": socket_insertion_servo_offset_socket[
                            0
                        ].detach().cpu().tolist(),
                        "socket_insertion_servo_offset_w": socket_insertion_servo_offset_w[
                            0
                        ].detach().cpu().tolist(),
                        "socket_insertion_servo_target_w": socket_insertion_servo_target_w[
                            0
                        ].detach().cpu().tolist(),
                        "socket_insertion_servo_command_quat_w": socket_insertion_servo_command_quat_w[
                            0
                        ].detach().cpu().tolist(),
                        "depth_rotation_polish": args_cli.depth_rotation_polish,
                        "depth_rotation_polish_state": bool(depth_rotation_polish_state[0].item()),
                        "depth_rotation_polish_active": bool(depth_rotation_polish_mask[0].item()),
                        "depth_rotation_polish_xy_tolerance": depth_rotation_polish_xy_tolerance,
                        "depth_rotation_polish_z_tolerance": depth_rotation_polish_z_tolerance,
                        "depth_rotation_polish_contact_min_force": depth_rotation_polish_contact_min_force,
                        "depth_rotation_polish_exit_contact_min_force": depth_rotation_polish_exit_contact_min_force,
                        "depth_rotation_polish_orientation_mode": args_cli.depth_rotation_polish_orientation_mode,
                        "depth_rotation_polish_command_valid": bool(
                            depth_rotation_polish_command_valid[0].item()
                        ),
                        "depth_rotation_polish_exit_xy_tolerance": args_cli.depth_rotation_polish_exit_xy_tol,
                        "depth_rotation_polish_exit_z_tolerance": args_cli.depth_rotation_polish_exit_z_tol,
                        "depth_rotation_polish_preload_step": args_cli.depth_rotation_polish_preload_step,
                        "depth_rotation_polish_rot_step": args_cli.depth_rotation_polish_rot_step,
                        "insert_vertical_step": (
                            args_cli.insert_vertical_step
                            if args_cli.insert_vertical_step is not None
                            else args_cli.insert_pos_step
                            if args_cli.insert_pos_step is not None
                            else args_cli.abs_pos_step
                        ),
                        "polish_xy_tolerance": args_cli.polish_xy_tol,
                        "polish_z_tolerance": args_cli.polish_z_tol,
                        "polish_rot_tolerance": args_cli.polish_rot_tol,
                        "polish_rotation_mode": args_cli.polish_rotation_mode,
                        "settle_xy_tolerance": args_cli.settle_xy_tol,
                        "settle_rot_tolerance": args_cli.settle_rot_tol,
                        "settle_contact_retention": args_cli.settle_contact_retention,
                        "settle_contact_retention_state": bool(contact_retention_state[0].item()),
                        "settle_contact_hold_xy": args_cli.settle_contact_hold_xy,
                        "settle_contact_force_aware_xy": args_cli.settle_contact_force_aware_xy,
                        "settle_contact_anchor_pos_w": (
                            contact_retention_anchor_pos_w[0].detach().cpu().tolist()
                            if args_cli.settle_contact_hold_xy
                            else None
                        ),
                        "settle_contact_force_xy_offset_w": contact_force_xy_offset_w[0].detach().cpu().tolist(),
                        "settle_contact_force_xy_target_w": contact_force_xy_target_w[0].detach().cpu().tolist(),
                        "settle_contact_force_scale": args_cli.settle_contact_force_scale,
                        "settle_contact_force_xy_gain": args_cli.settle_contact_force_xy_gain,
                        "settle_contact_force_xy_clamp": args_cli.settle_contact_force_xy_clamp,
                        "settle_contact_force_xy_sign": args_cli.settle_contact_force_xy_sign,
                        "settle_contact_preload_step": args_cli.settle_contact_preload_step,
                        "settle_contact_min_force": (
                            success_min_contact_force
                            if args_cli.settle_contact_min_force is None
                            else max(0.0, args_cli.settle_contact_min_force)
                        ),
                        "pre_contact_force_magnitude": (
                            pre_contact_force_magnitude[0].item() if pre_contact_force_magnitude is not None else None
                        ),
                        "pre_contact_force_socket": (
                            pre_contact_force_socket[0].detach().cpu().tolist()
                            if pre_contact_force_socket is not None
                            else None
                        ),
                        "joint_cache_active": bool(joint_cache_active_mask[0].item()),
                        "joint_cache_seed": bool(joint_cache_seed_mask[0].item()),
                        "joint_cache_valid": bool(insert_joint_cache_valid[0].item()),
                        "joint_ik_step": args_cli.joint_ik_step,
                        "joint_step_limit_mode": args_cli.joint_step_limit_mode,
                        "joint_cache_step": joint_cache_step,
                        "joint_cache_step_scale": args_cli.joint_cache_step_scale,
                        "joint_cache_total_limit": args_cli.joint_cache_total_limit,
                        "joint_cache_live_polish": args_cli.joint_cache_live_polish,
                        "joint_cache_step_count": int(insert_joint_cache_step_counts[0].item()),
                        "joint_cache_anchor": insert_joint_cache_anchor[0].detach().cpu().tolist(),
                        "joint_cache_direction": insert_joint_cache_direction[0].detach().cpu().tolist(),
                        "hold_orientation_during_insert": args_cli.hold_orientation_during_insert,
                        "insert_hold_valid": bool(insert_hold_valid[0].item()),
                        "insert_hold_quat_w": insert_hold_quat_w[0].detach().cpu().tolist(),
                        "insert_xy_tolerance": insert_xy_tolerance,
                        "insert_rot_tolerance": insert_rot_tolerance,
                        "insert_descent_rot_tolerance": insert_descent_rot_tolerance,
                        "insert_abort_xy_tolerance": insert_abort_xy_tolerance,
                        "insert_abort_rot_tolerance": insert_abort_rot_tolerance,
                        "insert_xy_ready": bool(insert_xy_ready[0].item()),
                        "insert_orientation_ready": bool(insert_orientation_ready[0].item()),
                        "insert_entry": bool(insert_entry_mask[0].item()),
                        "insert_new_entry": bool(insert_new_entry_mask[0].item()),
                        "insert_abort_violation": bool(insert_abort_violation_mask[0].item()),
                        "insert_abort_count": int(insert_abort_counts[0].item()),
                        "insert_abort_grace_steps": insert_abort_grace_steps,
                        "insert_aborted": bool(insert_abort_mask[0].item()),
                        "insert_state": bool(insert_state[0].item()),
                        "demo_reanchor_socket": args_cli.demo_reanchor_socket,
                        "demo_reanchor_initial_axial": max(0.0, args_cli.demo_reanchor_initial_axial),
                        "demo_reanchor_orientation": args_cli.demo_reanchor_orientation,
                        "demo_reanchor_socket_pos_w": (
                            demo_reanchor_socket_pos_w[0].detach().cpu().tolist()
                            if demo_reanchor_socket_pos_w is not None
                            else None
                        ),
                        "demo_reanchor_socket_quat_w": (
                            demo_reanchor_socket_quat_w[0].detach().cpu().tolist()
                            if demo_reanchor_socket_quat_w is not None
                            else None
                        ),
                        "socket_guide_clearance": SOCKET_GUIDE_CLEARANCE_M,
                        "success_xy_tolerance": SOCKET_SUCCESS_XY_TOLERANCE_M,
                        "success_z_tolerance": SOCKET_SUCCESS_Z_TOLERANCE_M,
                        "success_rot_tolerance": SOCKET_SUCCESS_ROT_TOLERANCE_RAD,
                        "active_success_xy_tolerance": success_xy_tolerance,
                        "active_success_z_tolerance": success_z_tolerance,
                        "active_success_rot_tolerance": success_rot_tolerance,
                        "success_min_contact_force": success_min_contact_force,
                        "success_xy_ready": bool(success_xy_ready[0].item()),
                        "success_axial_ready": bool(success_axial_ready[0].item()),
                        "success_rot_ready": bool(success_rot_ready[0].item()),
                        "success_contact_ready": bool(success_contact_ready[0].item()),
                        "success_xy_margin": lateral[0].item() - success_xy_tolerance,
                        "success_axial_margin": axial[0].item() - success_z_tolerance,
                        "success_rot_margin": rot[0].item() - success_rot_tolerance,
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
                        "success_hold_count": success_hold_count,
                        "success_hold_steps": max(1, args_cli.success_hold_steps),
                        "post_success_hold": bool(
                            success_step is not None and max(1, args_cli.success_hold_steps) > 1
                        ),
                        "post_success_hold_mode": post_success_hold_mode,
                        "position_ready": bool(position_ready[0].item()),
                        "orientation_ready": bool(orientation_ready[0].item()),
                        "aligned_state": bool(aligned_state[0].item()),
                        "branch_jump": bool(branch_jump_mask[0].item()),
                        "branch_jump_step": branch_jump_step,
                        "branch_jump_reason": branch_jump_reason,
                        "xy_state": bool(xy_state[0].item()),
                        "rotate_state": bool(rotate_state[0].item()),
                        "insert_mask": bool(insert_mask[0].item()),
                        "polish_state": bool(polish_state[0].item()),
                        "settle_state": bool(settle_state[0].item()),
                    }
                )
                partial_summary = {
                    "artifact_status": "partial",
                    "artifact_label": "trace-autoflush",
                    "task": args_cli.task,
                    "seed": args_cli.seed,
                    "steps_requested": args_cli.steps,
                    "steps_recorded": len(trace_rows),
                    "last_step": step,
                    "last_phase": phase,
                    "success_step": success_step,
                    "success_hold_exit_step": success_hold_exit_step,
                    "success_hold_count": success_hold_count,
                    "success_hold_steps": max(1, args_cli.success_hold_steps),
                    "post_success_hold_step_count": post_success_hold_step_count,
                    "initial_lateral": initial_lateral,
                    "initial_axial": initial_axial,
                    "initial_rot": initial_rot,
                    "final_lateral": final_lateral,
                    "final_axial": final_axial,
                    "final_rot": final_rot,
                    "final_success_rate": final_success,
                    "best_lateral": best_lateral,
                    "best_lateral_step": best_lateral_step,
                    "best_axial": best_axial,
                    "best_axial_step": best_axial_step,
                    "best_rot": best_rot,
                    "best_rot_step": best_rot_step,
                    "max_contact_force_magnitude": max_contact_force_magnitude,
                    "max_contact_force_magnitude_step": max_contact_force_magnitude_step,
                    "trace_json": os.path.abspath(args_cli.trace_json) if args_cli.trace_json else None,
                }
                last_partial_summary.clear()
                last_partial_summary.update(partial_summary)
                _append_jsonl(
                    trace_events_jsonl,
                    {
                        "event": "trace_row_appended",
                        "step": step,
                        "phase": phase,
                        "rows": len(trace_rows),
                        "lateral": final_lateral,
                        "axial": final_axial,
                        "rot": final_rot,
                        "success_rate": final_success,
                    },
                )
                if _should_autoflush_trace(step, args_cli.trace_autoflush_every):
                    _write_rollout_artifacts(
                        summary_json=args_cli.summary_json,
                        trace_json=args_cli.trace_json,
                        summary=partial_summary,
                        trace_rows=trace_rows,
                        label="partial",
                    )

            if success.any():
                if success_step is None:
                    success_step = step
                    print(f"[SCRIPTED] success reached at step={step:04d}", flush=True)
                    _append_jsonl(trace_events_jsonl, {"event": "success_first_seen", "step": step})
                success_hold_count += 1
                if success_hold_count >= max(1, args_cli.success_hold_steps):
                    success_hold_exit_step = step
                    print(
                        "[SCRIPTED] success hold satisfied "
                        f"first_step={success_step:04d} exit_step={step:04d} "
                        f"hold_steps={success_hold_count}",
                        flush=True,
                    )
                    _append_jsonl(
                        trace_events_jsonl,
                        {
                            "event": "success_hold_break",
                            "step": step,
                            "success_step": success_step,
                            "success_hold_count": success_hold_count,
                        },
                    )
                    break
            else:
                if success_hold_count > 0 and success_hold_count < max(1, args_cli.success_hold_steps):
                    _append_jsonl(
                        trace_events_jsonl,
                        {
                            "event": "success_hold_reset",
                            "step": step,
                            "success_step": success_step,
                            "success_hold_count": success_hold_count,
                        },
                    )
                success_hold_count = 0
            if args_cli.stop_on_branch_jump and branch_jump_step == step:
                print(f"[SCRIPTED] stopping after branch jump at step={step:04d}", flush=True)
                _append_jsonl(
                    trace_events_jsonl,
                    {"event": "branch_jump_break", "step": step, "reason": branch_jump_reason},
                )
                break
            _append_jsonl(trace_events_jsonl, {"event": "step_end", "step": step})

        _append_jsonl(
            trace_events_jsonl,
            {
                "event": "control_loop_exit",
                "steps_recorded": len(trace_rows),
                "success_step": success_step,
                "success_hold_exit_step": success_hold_exit_step,
                "success_hold_count": success_hold_count,
                "success_hold_steps": max(1, args_cli.success_hold_steps),
                "post_success_hold_step_count": post_success_hold_step_count,
                "branch_jump_step": branch_jump_step,
            },
        )
        summary = {
            "artifact_status": "complete",
            "task": args_cli.task,
            "seed": args_cli.seed,
            "steps_requested": args_cli.steps,
            "warmup_steps": args_cli.warmup_steps,
            "episode_buffer_steps": args_cli.episode_buffer_steps,
            "scripted_required_steps": scripted_required_steps,
            "scripted_episode_length_s": scripted_episode_length_s,
            "effective_episode_length_s": env_cfg.episode_length_s,
            "mdp_abs_ik_method": mdp_abs_ik_method,
            "mdp_abs_ik_params": mdp_abs_ik_params,
            "initial_joint_pos_overrides": initial_joint_pos_overrides,
            "demo_reanchor_socket": args_cli.demo_reanchor_socket,
            "demo_reanchor_initial_axial": max(0.0, args_cli.demo_reanchor_initial_axial),
            "demo_reanchor_orientation": args_cli.demo_reanchor_orientation,
            "demo_reanchor_settle_steps": max(0, int(args_cli.demo_reanchor_settle_steps)),
            "demo_reanchor_socket_pos_w": (
                demo_reanchor_socket_pos_w[0].detach().cpu().tolist()
                if demo_reanchor_socket_pos_w is not None
                else None
            ),
            "demo_reanchor_socket_quat_w": (
                demo_reanchor_socket_quat_w[0].detach().cpu().tolist()
                if demo_reanchor_socket_quat_w is not None
                else None
            ),
            "target_action_pos_offset": list(target_action_pos_offset),
            "target_action_pos_offset_frame": args_cli.target_action_pos_offset_frame,
            "approach_axis": args_cli.approach_axis,
            "abs_pos_step_mode": args_cli.abs_pos_step_mode,
            "reachable_approach": args_cli.reachable_approach,
            "reachable_approach_start_radius": reachable_approach_start_radius,
            "reachable_approach_min_radius": reachable_approach_min_radius,
            "reachable_approach_final_radius": reachable_approach_radius[0].item(),
            "reachable_approach_min_observed_radius": reachable_approach_min_observed_radius,
            "reachable_approach_shrink_step": reachable_approach_shrink_step,
            "reachable_approach_shrink_xy_tolerance": reachable_approach_shrink_xy_tol,
            "reachable_approach_joint_margin_min": args_cli.reachable_approach_joint_margin_min,
            "reachable_approach_shrink_count": reachable_approach_shrink_count,
            "reachable_approach_margin_block_count": reachable_approach_margin_block_count,
            "reachable_approach_offset_dir_w": reachable_approach_offset_dir_w[0].detach().cpu().tolist(),
            "disable_socket_wall_collisions": args_cli.disable_socket_wall_collisions,
            "success_step": success_step,
            "success_hold_exit_step": success_hold_exit_step,
            "success_hold_count": success_hold_count,
            "success_hold_steps": max(1, args_cli.success_hold_steps),
            "post_success_hold_step_count": post_success_hold_step_count,
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
            "arm_joint_names": list(arm_joint_names),
            "min_arm_joint_limit_margin": min_arm_joint_limit_margin,
            "min_arm_joint_limit_margin_step": min_arm_joint_limit_margin_step,
            "min_arm_joint_limit_margin_joint_index": min_arm_joint_limit_margin_joint_index,
            "min_arm_joint_limit_margin_joint_name": min_arm_joint_limit_margin_joint_name,
            "insert_joint_limit_margin": args_cli.insert_joint_limit_margin,
            "joint_limit_nullspace_gain": args_cli.joint_limit_nullspace_gain,
            "joint_limit_nullspace_activation_margin": args_cli.joint_limit_nullspace_activation_margin,
            "joint_limit_nullspace_step": args_cli.joint_limit_nullspace_step,
            "joint_limit_nullspace_damping": args_cli.joint_limit_nullspace_damping,
            "max_joint_limit_nullspace_delta_norm": max_joint_limit_nullspace_delta_norm,
            "max_joint_limit_nullspace_delta_norm_step": max_joint_limit_nullspace_delta_norm_step,
            "joint_limit_guard_gain": args_cli.joint_limit_guard_gain,
            "joint_limit_guard_activation_margin": args_cli.joint_limit_guard_activation_margin,
            "joint_limit_guard_step": args_cli.joint_limit_guard_step,
            "max_joint_limit_guard_delta_norm": max_joint_limit_guard_delta_norm,
            "max_joint_limit_guard_delta_norm_step": max_joint_limit_guard_delta_norm_step,
            "video_backend": args_cli.video_backend if args_cli.video else None,
            "video_folder": video_folder,
            "coupled_approach": args_cli.coupled_approach,
            "staged_approach": args_cli.staged_approach,
            "rotate_before_descend": args_cli.rotate_before_descend,
            "rotate_descent_mode": args_cli.rotate_descent_mode,
            "action_axis_signs": list(args_cli.action_axis_signs),
            "action_dim": action_dim,
            "scripted_control_mode": scripted_control_mode,
            "position_control_mode": args_cli.position_control_mode,
            "abs_control_mode": args_cli.abs_control_mode,
            "mdp_abs_action_frame": args_cli.mdp_abs_action_frame,
            "mdp_abs_orientation_command_mode": args_cli.mdp_abs_orientation_command_mode,
            "rotate_control_mode": args_cli.rotate_control_mode,
            "orientation_target_mode": args_cli.orientation_target_mode,
            "hold_orientation_during_descend": args_cli.hold_orientation_during_descend,
            "rotate_xy_retention": args_cli.rotate_xy_retention,
            "rotate_xy_retention_tolerance": args_cli.rotate_xy_retention_tol,
            "rotate_xy_recovery_step_count": rotate_xy_recovery_step_count,
            "rotate_xy_recovery_first_step": rotate_xy_recovery_first_step,
            "rotate_xy_recovery_last_step": rotate_xy_recovery_last_step,
            "rotate_xy_recovery_max_lateral": rotate_xy_recovery_max_lateral,
            "rotate_descent_step_count": rotate_descent_step_count,
            "rotate_descent_first_step": rotate_descent_first_step,
            "rotate_descent_last_step": rotate_descent_last_step,
            "descend_xy_retention": args_cli.descend_xy_retention,
            "descend_xy_retention_tolerance": args_cli.descend_xy_retention_tol,
            "descend_xy_recovery_step_count": descend_xy_recovery_step_count,
            "descend_xy_recovery_first_step": descend_xy_recovery_first_step,
            "descend_xy_recovery_last_step": descend_xy_recovery_last_step,
            "descend_xy_recovery_max_lateral": descend_xy_recovery_max_lateral,
            "hold_orientation_during_insert": args_cli.hold_orientation_during_insert,
            "disable_insertion_success_termination": args_cli.disable_insertion_success_termination,
            "insertion_success_termination_disabled": insertion_success_termination_disabled,
            "insert_after_alignment": args_cli.insert_after_alignment,
            "insert_descent_mode": args_cli.insert_descent_mode,
            "insert_rotation_gated_descent": args_cli.insert_rotation_gated_descent,
            "insert_descent_rot_tolerance": (
                args_cli.insert_descent_rot_tol
                if args_cli.insert_descent_rot_tol is not None
                else args_cli.insert_rot_tol
                if args_cli.insert_rot_tol is not None
                else args_cli.approach_rot_tol
            ),
            "insert_rotation_gate_step_count": insert_rotation_gate_step_count,
            "insert_rotation_gate_first_step": insert_rotation_gate_first_step,
            "insert_rotation_gate_last_step": insert_rotation_gate_last_step,
            "insert_rotation_gate_max_rot": insert_rotation_gate_max_rot,
            "insert_rotation_gate_descent_scale": args_cli.insert_rotation_gate_descent_scale,
            "insert_rotation_gate_min_descent_step": args_cli.insert_rotation_gate_min_descent_step,
            "insert_rotation_gate_near_depth_z_tolerance": args_cli.insert_rotation_gate_near_depth_z_tol,
            "insert_rotation_gate_near_depth_rot_tolerance": args_cli.insert_rotation_gate_near_depth_rot_tol,
            "insert_rotation_gate_near_depth_descent_scale": (
                args_cli.insert_rotation_gate_near_depth_descent_scale
            ),
            "insert_rotation_gate_near_depth_min_descent_step": (
                args_cli.insert_rotation_gate_near_depth_min_descent_step
            ),
            "insert_rotation_gate_allowed_descent_max": insert_rotation_gate_allowed_descent_max,
            "insert_contact_force_aware_xy": args_cli.insert_contact_force_aware_xy,
            "insert_contact_force_min": args_cli.insert_contact_force_min,
            "insert_contact_force_scale": args_cli.insert_contact_force_scale,
            "insert_contact_force_xy_gain": args_cli.insert_contact_force_xy_gain,
            "insert_contact_force_xy_clamp": args_cli.insert_contact_force_xy_clamp,
            "insert_contact_force_xy_sign": args_cli.insert_contact_force_xy_sign,
            "final_contact_servo": args_cli.final_contact_servo,
            "final_contact_servo_entry_xy_tolerance": args_cli.final_contact_servo_entry_xy_tol,
            "final_contact_servo_entry_z_tolerance": args_cli.final_contact_servo_entry_z_tol,
            "final_contact_servo_entry_rot_tolerance": (
                success_rot_tolerance
                if args_cli.final_contact_servo_entry_rot_tol is None
                else max(0.0, args_cli.final_contact_servo_entry_rot_tol)
            ),
            "final_contact_servo_exit_xy_tolerance": args_cli.final_contact_servo_exit_xy_tol,
            "final_contact_servo_exit_rot_tolerance": (
                args_cli.insert_abort_rot_tol
                if args_cli.final_contact_servo_exit_rot_tol is None and args_cli.insert_abort_rot_tol is not None
                else args_cli.approach_rot_tol
                if args_cli.final_contact_servo_exit_rot_tol is None
                else max(0.0, args_cli.final_contact_servo_exit_rot_tol)
            ),
            "final_contact_servo_xy_gain": args_cli.final_contact_servo_xy_gain,
            "final_contact_servo_xy_clamp": args_cli.final_contact_servo_xy_clamp,
            "final_contact_servo_metric_error": args_cli.final_contact_servo_metric_error,
            "final_contact_servo_metric_xy": args_cli.final_contact_servo_metric_xy,
            "final_contact_servo_metric_z": args_cli.final_contact_servo_metric_z,
            "final_contact_servo_z_gain": args_cli.final_contact_servo_z_gain,
            "final_contact_servo_z_step": args_cli.final_contact_servo_z_step,
            "final_contact_servo_hold_z_when_axial_ready": args_cli.final_contact_servo_hold_z_when_axial_ready,
            "final_contact_servo_orientation_mode": args_cli.final_contact_servo_orientation_mode,
            "final_contact_servo_step_count": final_contact_servo_step_count,
            "final_contact_servo_first_step": final_contact_servo_first_step,
            "final_contact_servo_last_step": final_contact_servo_last_step,
            "final_contact_servo_entry_count": final_contact_servo_entry_count,
            "final_contact_servo_exit_count": final_contact_servo_exit_count,
            "final_contact_servo_max_lateral": final_contact_servo_max_lateral,
            "final_contact_servo_min_axial": final_contact_servo_min_axial,
            "final_contact_servo_max_xy_offset": final_contact_servo_max_xy_offset,
            "final_contact_servo_z_hold_count": final_contact_servo_z_hold_count,
            "socket_insertion_servo": args_cli.socket_insertion_servo,
            "socket_insertion_servo_entry_xy_tolerance": args_cli.socket_insertion_servo_entry_xy_tol,
            "socket_insertion_servo_entry_z_tolerance": args_cli.socket_insertion_servo_entry_z_tol,
            "socket_insertion_servo_entry_rot_tolerance": args_cli.socket_insertion_servo_entry_rot_tol,
            "socket_insertion_servo_exit_xy_tolerance": args_cli.socket_insertion_servo_exit_xy_tol,
            "socket_insertion_servo_exit_z_tolerance": args_cli.socket_insertion_servo_exit_z_tol,
            "socket_insertion_servo_exit_rot_tolerance": args_cli.socket_insertion_servo_exit_rot_tol,
            "socket_insertion_servo_strict_exit": args_cli.socket_insertion_servo_strict_exit,
            "socket_insertion_servo_hard_exit_xy_tolerance": args_cli.socket_insertion_servo_hard_exit_xy_tol,
            "socket_insertion_servo_hard_exit_z_tolerance": args_cli.socket_insertion_servo_hard_exit_z_tol,
            "socket_insertion_servo_hard_exit_rot_tolerance": args_cli.socket_insertion_servo_hard_exit_rot_tol,
            "socket_insertion_servo_descend_xy_tolerance": (
                success_xy_tolerance
                if args_cli.socket_insertion_servo_descend_xy_tol is None
                else max(0.0, args_cli.socket_insertion_servo_descend_xy_tol)
            ),
            "socket_insertion_servo_descend_rot_tolerance": (
                success_rot_tolerance
                if args_cli.socket_insertion_servo_descend_rot_tol is None
                else max(0.0, args_cli.socket_insertion_servo_descend_rot_tol)
            ),
            "socket_insertion_servo_xy_gain": args_cli.socket_insertion_servo_xy_gain,
            "socket_insertion_servo_xy_clamp": args_cli.socket_insertion_servo_xy_clamp,
            "socket_insertion_servo_z_gain": args_cli.socket_insertion_servo_z_gain,
            "socket_insertion_servo_z_step": args_cli.socket_insertion_servo_z_step,
            "socket_insertion_servo_contact_preload_step": args_cli.socket_insertion_servo_contact_preload_step,
            "socket_insertion_servo_maintain_contact_preload": (
                args_cli.socket_insertion_servo_maintain_contact_preload
            ),
            "socket_insertion_servo_contact_boundary_min_force": (
                args_cli.socket_insertion_servo_contact_boundary_min_force
            ),
            "socket_insertion_servo_contact_boundary_tolerance": (
                args_cli.socket_insertion_servo_contact_boundary_tol
            ),
            "socket_insertion_servo_contact_boundary_step": args_cli.socket_insertion_servo_contact_boundary_step,
            "socket_insertion_servo_contact_boundary_xy_gain": (
                args_cli.socket_insertion_servo_contact_boundary_xy_gain
            ),
            "socket_insertion_servo_contact_boundary_xy_clamp": (
                args_cli.socket_insertion_servo_contact_boundary_xy_clamp
            ),
            "socket_insertion_servo_rot_step": args_cli.socket_insertion_servo_rot_step,
            "socket_insertion_servo_rotate_only_when_rot_misaligned": (
                args_cli.socket_insertion_servo_rotate_only_when_rot_misaligned
            ),
            "socket_insertion_servo_rotate_while_xy_misaligned": (
                args_cli.socket_insertion_servo_rotate_while_xy_misaligned
            ),
            "socket_insertion_servo_step_count": socket_insertion_servo_step_count,
            "socket_insertion_servo_first_step": socket_insertion_servo_first_step,
            "socket_insertion_servo_last_step": socket_insertion_servo_last_step,
            "socket_insertion_servo_entry_count": socket_insertion_servo_entry_count,
            "socket_insertion_servo_exit_count": socket_insertion_servo_exit_count,
            "socket_insertion_servo_descend_count": socket_insertion_servo_descend_count,
            "socket_insertion_servo_z_hold_count": socket_insertion_servo_z_hold_count,
            "socket_insertion_servo_contact_preload_count": socket_insertion_servo_contact_preload_count,
            "socket_insertion_servo_contact_boundary_count": socket_insertion_servo_contact_boundary_count,
            "socket_insertion_servo_recovery_count": socket_insertion_servo_recovery_count,
            "socket_insertion_servo_orientation_hold_count": socket_insertion_servo_orientation_hold_count,
            "socket_insertion_servo_max_lateral": socket_insertion_servo_max_lateral,
            "socket_insertion_servo_min_axial": socket_insertion_servo_min_axial,
            "socket_insertion_servo_max_xy_offset": socket_insertion_servo_max_xy_offset,
            "depth_rotation_polish": args_cli.depth_rotation_polish,
            "depth_rotation_polish_xy_tolerance": depth_rotation_polish_xy_tolerance,
            "depth_rotation_polish_z_tolerance": depth_rotation_polish_z_tolerance,
            "depth_rotation_polish_contact_min_force": depth_rotation_polish_contact_min_force,
            "depth_rotation_polish_exit_contact_min_force": depth_rotation_polish_exit_contact_min_force,
            "depth_rotation_polish_orientation_mode": args_cli.depth_rotation_polish_orientation_mode,
            "depth_rotation_polish_exit_xy_tolerance": args_cli.depth_rotation_polish_exit_xy_tol,
            "depth_rotation_polish_exit_z_tolerance": args_cli.depth_rotation_polish_exit_z_tol,
            "depth_rotation_polish_preload_step": args_cli.depth_rotation_polish_preload_step,
            "depth_rotation_polish_rot_step": args_cli.depth_rotation_polish_rot_step,
            "depth_rotation_polish_pos_gain": args_cli.depth_rotation_polish_pos_gain,
            "depth_rotation_polish_pos_clamp": args_cli.depth_rotation_polish_pos_clamp,
            "depth_rotation_polish_rot_gain": args_cli.depth_rotation_polish_rot_gain,
            "depth_rotation_polish_rot_clamp": args_cli.depth_rotation_polish_rot_clamp,
            "depth_rotation_polish_step_count": depth_rotation_polish_step_count,
            "depth_rotation_polish_first_step": depth_rotation_polish_first_step,
            "depth_rotation_polish_last_step": depth_rotation_polish_last_step,
            "depth_rotation_polish_max_rot": depth_rotation_polish_max_rot,
            "depth_rotation_polish_max_lateral": depth_rotation_polish_max_lateral,
            "depth_rotation_polish_min_axial": depth_rotation_polish_min_axial,
            "insert_vertical_step": (
                args_cli.insert_vertical_step
                if args_cli.insert_vertical_step is not None
                else args_cli.insert_pos_step
                if args_cli.insert_pos_step is not None
                else args_cli.abs_pos_step
            ),
            "joint_cache_step": args_cli.joint_cache_step if args_cli.joint_cache_step is not None else args_cli.joint_ik_step,
            "joint_cache_step_scale": args_cli.joint_cache_step_scale,
            "joint_cache_total_limit": args_cli.joint_cache_total_limit,
            "joint_cache_live_polish": args_cli.joint_cache_live_polish,
            "polish_xy_tolerance": args_cli.polish_xy_tol,
            "polish_z_tolerance": args_cli.polish_z_tol,
            "polish_rot_tolerance": args_cli.polish_rot_tol,
            "polish_rotation_mode": args_cli.polish_rotation_mode,
            "settle_xy_tolerance": args_cli.settle_xy_tol,
            "settle_rot_tolerance": args_cli.settle_rot_tol,
            "settle_contact_retention": args_cli.settle_contact_retention,
            "settle_contact_hold_xy": args_cli.settle_contact_hold_xy,
            "settle_contact_force_aware_xy": args_cli.settle_contact_force_aware_xy,
            "settle_contact_force_scale": args_cli.settle_contact_force_scale,
            "settle_contact_force_xy_gain": args_cli.settle_contact_force_xy_gain,
            "settle_contact_force_xy_clamp": args_cli.settle_contact_force_xy_clamp,
            "settle_contact_force_xy_sign": args_cli.settle_contact_force_xy_sign,
            "settle_contact_preload_step": args_cli.settle_contact_preload_step,
            "settle_contact_min_force": (
                success_min_contact_force
                if args_cli.settle_contact_min_force is None
                else max(0.0, args_cli.settle_contact_min_force)
            ),
            "settle_contact_xy_tolerance": (
                success_xy_tolerance if args_cli.settle_contact_xy_tol is None else args_cli.settle_contact_xy_tol
            ),
            "settle_contact_z_tolerance": (
                success_z_tolerance if args_cli.settle_contact_z_tol is None else args_cli.settle_contact_z_tol
            ),
            "settle_contact_rot_tolerance": (
                success_rot_tolerance if args_cli.settle_contact_rot_tol is None else args_cli.settle_contact_rot_tol
            ),
            "settle_contact_exit_xy_tolerance": args_cli.settle_contact_exit_xy_tol,
            "settle_contact_exit_z_tolerance": args_cli.settle_contact_exit_z_tol,
            "settle_contact_exit_rot_tolerance": args_cli.settle_contact_exit_rot_tol,
            "stop_on_branch_jump": args_cli.stop_on_branch_jump,
            "branch_jump_step": branch_jump_step,
            "branch_jump_reason": branch_jump_reason,
            "branch_jump_aligned_xy_tolerance": args_cli.branch_jump_aligned_xy_tol,
            "branch_jump_aligned_rot_tolerance": args_cli.branch_jump_aligned_rot_tol,
            "branch_jump_xy_tolerance": args_cli.branch_jump_xy_tol,
            "branch_jump_rot_tolerance": args_cli.branch_jump_rot_tol,
            "branch_jump_contact_force_magnitude": branch_jump_contact_force_magnitude,
            "branch_jump_joint_limit_margin_min": branch_jump_joint_limit_margin_min,
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
            "active_success_xy_tolerance": success_xy_tolerance,
            "active_success_z_tolerance": success_z_tolerance,
            "active_success_rot_tolerance": success_rot_tolerance,
            "success_min_contact_force": success_min_contact_force,
            "socket_guide_clearance": SOCKET_GUIDE_CLEARANCE_M,
            "max_contact_force_magnitude": max_contact_force_magnitude,
            "max_contact_force_magnitude_step": max_contact_force_magnitude_step,
            "position_response_json": args_cli.position_response_json,
            "joint_ik_step": args_cli.joint_ik_step,
            "joint_step_limit_mode": args_cli.joint_step_limit_mode,
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
            f"success_step={summary['success_step']} "
            f"success_hold={summary['success_hold_count']}/{summary['success_hold_steps']} "
            f"success_hold_exit_step={summary['success_hold_exit_step']}",
            flush=True,
        )
        _write_rollout_artifacts(
            summary_json=args_cli.summary_json,
            trace_json=args_cli.trace_json,
            summary=summary,
            trace_rows=trace_rows,
            label="final",
        )
        _append_jsonl(trace_events_jsonl, {"event": "final_artifacts_written", "steps_recorded": len(trace_rows)})
        trace_artifacts_finalized["value"] = True
        _close_ignoring_system_exit(env.close, "environment")


if __name__ == "__main__":
    main()
