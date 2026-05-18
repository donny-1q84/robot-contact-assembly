#!/usr/bin/env python3
"""Evaluate a small BC contact policy checkpoint inside Isaac Lab."""

from __future__ import annotations

import argparse
import json
import os
import sys

import gymnasium as gym
import torch
import warp as wp

from isaaclab_tasks.utils import add_launcher_args, launch_simulation, resolve_task_config

from extract_contact_demo_dataset import OBS_FIELDS


SceneEntityCfg = None
combine_frame_transforms = None
compute_pose_error = None
subtract_frame_transforms = None
IDENTITY_QUAT = None
PEG_TIP_BODY_OFFSET_POS = None
PEG_TIP_BODY_OFFSET_ROT = None
PEG_TIP_FROM_CENTER_POS = None
mdp = None
BODY_OFFSET = None


def _as_torch(value) -> torch.Tensor:
    return value if isinstance(value, torch.Tensor) else wp.to_torch(value)


def _parse_vec3(value: str) -> tuple[float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("expected three comma-separated values, e.g. 0.22,0.04,0.22")
    try:
        return tuple(float(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("vector values must be numeric") from exc


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


def _socket_pose_w(env_unwrapped) -> tuple[torch.Tensor, torch.Tensor]:
    socket = env_unwrapped.scene["socket_frame"]
    return _as_torch(socket.data.root_pos_w), _as_torch(socket.data.root_quat_w)


def _physical_peg_tip_pose_w(env_unwrapped) -> tuple[torch.Tensor, torch.Tensor]:
    peg = env_unwrapped.scene["peg"]
    peg_pos_w = _as_torch(peg.data.root_pos_w)
    peg_quat_w = _as_torch(peg.data.root_quat_w)
    tip_offset_pos = peg_pos_w.new_tensor(PEG_TIP_FROM_CENTER_POS).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    tip_offset_quat = peg_pos_w.new_tensor(IDENTITY_QUAT).unsqueeze(0).repeat(peg_pos_w.shape[0], 1)
    return combine_frame_transforms(peg_pos_w, peg_quat_w, tip_offset_pos, tip_offset_quat)


def _selected_joint_limits(robot, joint_ids: torch.Tensor, margin: float = 0.0) -> tuple[torch.Tensor | None, torch.Tensor | None]:
    limits = getattr(robot.data, "soft_joint_pos_limits", None)
    if limits is None:
        limits = getattr(robot.data, "joint_pos_limits", None)
    if limits is None:
        return None, None
    limits = _as_torch(limits).index_select(1, joint_ids)
    lower = limits[..., 0] + margin
    upper = limits[..., 1] - margin
    return lower, upper


def _joint_limit_margin(joint_pos: torch.Tensor, lower: torch.Tensor | None, upper: torch.Tensor | None) -> torch.Tensor:
    if lower is None or upper is None:
        return torch.zeros_like(joint_pos)
    return torch.minimum(joint_pos - lower, upper - joint_pos)


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


def _build_model(obs_dim: int, action_dim: int, hidden_dim: int, layers: int):
    from torch import nn

    modules: list[nn.Module] = []
    in_dim = obs_dim
    for _ in range(max(1, layers)):
        modules.append(nn.Linear(in_dim, hidden_dim))
        modules.append(nn.SiLU())
        in_dim = hidden_dim
    modules.append(nn.Linear(in_dim, action_dim))
    return nn.Sequential(*modules)


def _tensor_list(tensor: torch.Tensor) -> list[float]:
    return [float(x) for x in tensor.detach().cpu().tolist()]


def _make_observation(
    env_unwrapped,
    body_idx: int,
    peg_cfg,
    socket_cfg,
    contact_sensor_cfg,
    joint_ids: torch.Tensor,
    joint_limit_lower: torch.Tensor | None,
    joint_limit_upper: torch.Tensor | None,
) -> tuple[torch.Tensor, dict[str, torch.Tensor]]:
    robot = env_unwrapped.scene["robot"]
    action_pos_w, action_quat_w = _action_frame_pose_w(env_unwrapped, body_idx)
    physical_tip_pos_w, physical_tip_quat_w = _physical_peg_tip_pose_w(env_unwrapped)
    socket_pos_w, socket_quat_w = _socket_pose_w(env_unwrapped)
    physical_tip_rel_socket_pos, _ = subtract_frame_transforms(
        socket_pos_w,
        socket_quat_w,
        physical_tip_pos_w,
        physical_tip_quat_w,
    )
    pos_error = socket_pos_w - action_pos_w
    _, axis_angle_error = compute_pose_error(action_pos_w, action_quat_w, socket_pos_w, socket_quat_w, rot_error_type="axis_angle")
    lateral, axial, rot = mdp.insertion_metrics(env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)
    if contact_sensor_cfg is not None:
        contact_force_socket = mdp.peg_contact_force_socket(env_unwrapped, sensor_cfg=contact_sensor_cfg, socket_cfg=socket_cfg)
        contact_force_magnitude = mdp.peg_contact_force_magnitude(env_unwrapped, sensor_cfg=contact_sensor_cfg)
    else:
        contact_force_socket = torch.zeros_like(pos_error)
        contact_force_magnitude = torch.zeros((pos_error.shape[0], 1), device=pos_error.device, dtype=pos_error.dtype)

    joint_pos = _as_torch(robot.data.joint_pos).index_select(-1, joint_ids)
    joint_vel = _as_torch(robot.data.joint_vel).index_select(-1, joint_ids)
    joint_margin = _joint_limit_margin(joint_pos, joint_limit_lower, joint_limit_upper)

    fields = {
        "physical_tip_rel_socket_pos": physical_tip_rel_socket_pos,
        "pos_error": pos_error,
        "axis_angle_error": axis_angle_error,
        "contact_force_socket": contact_force_socket,
        "contact_force_magnitude": contact_force_magnitude,
        "lateral": lateral.unsqueeze(-1),
        "axial": axial.unsqueeze(-1),
        "rot": rot.unsqueeze(-1),
        "joint_pos": joint_pos,
        "joint_vel": joint_vel,
        "joint_limit_margin": joint_margin,
    }
    obs_parts = [fields[name] for name, _ in OBS_FIELDS]
    return torch.cat(obs_parts, dim=-1), fields


parser = argparse.ArgumentParser(description="Evaluate a BC contact policy on the contact peg-in-hole task.")
parser.add_argument("--disable_fabric", action="store_true", default=False, help="Disable fabric.")
parser.add_argument("--num_envs", type=int, default=1, help="Number of environments.")
parser.add_argument("--steps", type=int, default=400, help="Number of evaluation steps.")
parser.add_argument("--task", type=str, default="RCA-PegInHole-Franka-JointPos-Contact-Play-v0", help="Task name.")
parser.add_argument("--checkpoint", type=str, required=True, help="BC checkpoint from scripts/train_contact_bc_policy.py.")
parser.add_argument("--seed", type=int, default=42, help="Environment seed.")
parser.add_argument("--warmup-steps", type=int, default=30)
parser.add_argument("--deterministic-reset", action="store_true", default=False)
parser.add_argument("--socket-pos", type=_parse_vec3, default=None)
parser.add_argument("--success-xy-tol", type=float, default=0.005)
parser.add_argument("--success-z-tol", type=float, default=0.045)
parser.add_argument("--success-rot-tol", type=float, default=0.18)
parser.add_argument("--success-min-contact-force", type=float, default=0.5)
parser.add_argument("--max-action-delta", type=float, default=0.05, help="Clamp 7D joint-position actions around current joints.")
parser.add_argument("--joint-limit-margin", type=float, default=0.005)
parser.add_argument("--summary-json", type=str, default=None)
parser.add_argument("--trace-json", type=str, default=None)
add_launcher_args(parser)
args_cli, hydra_args = parser.parse_known_args()
hydra_args.extend(
    [
        r"hydra.run.dir=/workspace/artifacts/hydra/${now:%Y-%m-%d}/${now:%H-%M-%S}",
        "hydra.output_subdir=null",
    ]
)
sys.argv = [sys.argv[0]] + hydra_args

import robot_contact_assembly_tasks.tasks  # noqa: E402,F401


def main() -> None:
    global SceneEntityCfg, combine_frame_transforms, compute_pose_error, subtract_frame_transforms
    global IDENTITY_QUAT, PEG_TIP_BODY_OFFSET_POS, PEG_TIP_BODY_OFFSET_ROT, PEG_TIP_FROM_CENTER_POS, mdp, BODY_OFFSET

    torch.manual_seed(args_cli.seed)
    os.makedirs("/workspace/artifacts/hydra", exist_ok=True)
    env_cfg, _ = resolve_task_config(args_cli.task, "")
    env_cfg.seed = args_cli.seed

    with launch_simulation(env_cfg, args_cli):
        from isaaclab.managers import SceneEntityCfg
        from isaaclab.utils.math import combine_frame_transforms, compute_pose_error, subtract_frame_transforms
        from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole import mdp
        from robot_contact_assembly_tasks.tasks.manager_based.manipulation.peg_in_hole.constants import (
            IDENTITY_QUAT,
            PEG_TIP_BODY_OFFSET_POS,
            PEG_TIP_BODY_OFFSET_ROT,
            PEG_TIP_FROM_CENTER_POS,
        )

        BODY_OFFSET = PEG_TIP_BODY_OFFSET_POS
        env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs
        env_cfg.sim.device = args_cli.device if args_cli.device is not None else env_cfg.sim.device
        if args_cli.disable_fabric:
            env_cfg.sim.use_fabric = False
        env_cfg.commands.socket_pose.resampling_time_range = (1.0e6, 1.0e6)
        step_dt = env_cfg.sim.dt * env_cfg.decimation
        env_cfg.episode_length_s = max(env_cfg.episode_length_s, (args_cli.warmup_steps + args_cli.steps + 20) * step_dt)
        if args_cli.deterministic_reset:
            env_cfg.events.reset_robot_joints.params["position_range"] = (1.0, 1.0)
        if args_cli.socket_pos is not None:
            _override_socket_pose(env_cfg, args_cli.socket_pos)

        checkpoint = torch.load(args_cli.checkpoint, map_location="cpu")
        obs_dim = int(checkpoint["obs_dim"])
        action_dim = int(checkpoint["action_dim"])
        model = _build_model(obs_dim, action_dim, int(checkpoint["hidden_dim"]), int(checkpoint["layers"]))
        model.load_state_dict(checkpoint["model_state_dict"])
        device = torch.device(args_cli.device if args_cli.device is not None else env_cfg.sim.device)
        model.to(device).eval()
        obs_mean = checkpoint["obs_mean"].to(device)
        obs_std = checkpoint["obs_std"].to(device)
        action_mean = checkpoint["action_mean"].to(device)
        action_std = checkpoint["action_std"].to(device)

        env = gym.make(args_cli.task, cfg=env_cfg, render_mode=None)
        env_unwrapped = env.unwrapped
        env.reset()

        if args_cli.warmup_steps > 0:
            zero_actions = torch.zeros(env.action_space.shape, device=env_unwrapped.device)
            for _ in range(args_cli.warmup_steps):
                env.step(zero_actions)

        robot = env_unwrapped.scene["robot"]
        body_ids, _ = robot.find_bodies("panda_hand")
        body_idx = body_ids[0]
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
        joint_ids_t = torch.as_tensor(robot_entity_cfg.joint_ids, device=env_unwrapped.device, dtype=torch.long)
        joint_limit_lower, joint_limit_upper = _selected_joint_limits(robot, joint_ids_t, margin=args_cli.joint_limit_margin)
        peg_cfg = SceneEntityCfg("peg")
        socket_cfg = SceneEntityCfg("socket_frame")
        try:
            env_unwrapped.scene["peg_contact"]
            contact_sensor_cfg = SceneEntityCfg("peg_contact")
        except KeyError:
            contact_sensor_cfg = None

        trace_rows: list[dict] = []
        success_step = None
        initial_lateral = initial_axial = initial_rot = None
        final_lateral = final_axial = final_rot = final_success_rate = None
        best_lateral = best_axial = best_rot = float("inf")
        best_lateral_step = best_axial_step = best_rot_step = None
        max_contact_force = 0.0
        max_contact_force_step = None

        for step in range(args_cli.steps):
            obs, fields = _make_observation(
                env_unwrapped,
                body_idx,
                peg_cfg,
                socket_cfg,
                contact_sensor_cfg,
                joint_ids_t,
                joint_limit_lower,
                joint_limit_upper,
            )
            with torch.inference_mode():
                obs = obs.to(device)
                pred_norm = model((obs - obs_mean) / obs_std)
                actions = pred_norm * action_std + action_mean
                actions = actions.to(env_unwrapped.device)

            if actions.shape[-1] != env.action_space.shape[-1]:
                raise RuntimeError(f"policy action_dim={actions.shape[-1]} does not match env action_dim={env.action_space.shape[-1]}")
            if actions.shape[-1] == 7 and args_cli.max_action_delta > 0.0:
                joint_pos = fields["joint_pos"]
                actions = joint_pos + torch.clamp(actions - joint_pos, -args_cli.max_action_delta, args_cli.max_action_delta)
                if joint_limit_lower is not None and joint_limit_upper is not None:
                    actions = torch.minimum(torch.maximum(actions, joint_limit_lower), joint_limit_upper)

            env.step(actions)

            lateral, axial, rot = mdp.insertion_metrics(env_unwrapped, peg_cfg=peg_cfg, socket_cfg=socket_cfg)
            if contact_sensor_cfg is not None:
                contact_force = mdp.peg_contact_force_magnitude(env_unwrapped, sensor_cfg=contact_sensor_cfg).squeeze(-1)
            else:
                contact_force = torch.zeros_like(lateral)
            success = (
                (lateral < args_cli.success_xy_tol)
                & (axial < args_cli.success_z_tol)
                & (rot < args_cli.success_rot_tol)
                & (contact_force >= args_cli.success_min_contact_force)
            )
            lateral_mean = lateral.mean().item()
            axial_mean = axial.mean().item()
            rot_mean = rot.mean().item()
            success_rate = success.float().mean().item()
            contact_mean = contact_force.mean().item()

            if step == 0:
                initial_lateral = lateral_mean
                initial_axial = axial_mean
                initial_rot = rot_mean
            final_lateral = lateral_mean
            final_axial = axial_mean
            final_rot = rot_mean
            final_success_rate = success_rate
            if lateral_mean < best_lateral:
                best_lateral = lateral_mean
                best_lateral_step = step
            if axial_mean < best_axial:
                best_axial = axial_mean
                best_axial_step = step
            if rot_mean < best_rot:
                best_rot = rot_mean
                best_rot_step = step
            if contact_mean > max_contact_force:
                max_contact_force = contact_mean
                max_contact_force_step = step
            if success_step is None and success.any():
                success_step = step

            if step % 25 == 0 or step == args_cli.steps - 1 or success_step == step:
                print(
                    f"[BC-EVAL] step={step:04d} lateral={lateral_mean:.4f} axial={axial_mean:.4f} "
                    f"rot={rot_mean:.4f} contact={contact_mean:.3f} success_rate={success_rate:.3f}",
                    flush=True,
                )

            if args_cli.trace_json:
                trace_rows.append(
                    {
                        "step": step,
                        "lateral": lateral[0].item(),
                        "axial": axial[0].item(),
                        "rot": rot[0].item(),
                        "contact_force_magnitude": contact_force[0].item(),
                        "success": bool(success[0].item()),
                        "raw_action": _tensor_list(actions[0]),
                        "observation": _tensor_list(obs[0]),
                        "physical_tip_rel_socket_pos": _tensor_list(fields["physical_tip_rel_socket_pos"][0]),
                        "pos_error": _tensor_list(fields["pos_error"][0]),
                        "axis_angle_error": _tensor_list(fields["axis_angle_error"][0]),
                        "contact_force_socket": _tensor_list(fields["contact_force_socket"][0]),
                        "joint_pos": _tensor_list(fields["joint_pos"][0]),
                        "joint_vel": _tensor_list(fields["joint_vel"][0]),
                        "joint_limit_margin": _tensor_list(fields["joint_limit_margin"][0]),
                    }
                )
            if success_step == step:
                break

        env.close()
        summary = {
            "task": args_cli.task,
            "checkpoint": os.path.abspath(args_cli.checkpoint),
            "seed": args_cli.seed,
            "steps_requested": args_cli.steps,
            "success_step": success_step,
            "initial_lateral": initial_lateral,
            "initial_axial": initial_axial,
            "initial_rot": initial_rot,
            "final_lateral": final_lateral,
            "final_axial": final_axial,
            "final_rot": final_rot,
            "final_success_rate": final_success_rate,
            "best_lateral": best_lateral,
            "best_lateral_step": best_lateral_step,
            "best_axial": best_axial,
            "best_axial_step": best_axial_step,
            "best_rot": best_rot,
            "best_rot_step": best_rot_step,
            "max_contact_force_magnitude": max_contact_force,
            "max_contact_force_magnitude_step": max_contact_force_step,
            "active_success_xy_tolerance": args_cli.success_xy_tol,
            "active_success_z_tolerance": args_cli.success_z_tol,
            "active_success_rot_tolerance": args_cli.success_rot_tol,
            "success_min_contact_force": args_cli.success_min_contact_force,
            "obs_dim": obs_dim,
            "action_dim": action_dim,
            "max_action_delta": args_cli.max_action_delta,
            "deterministic_reset": args_cli.deterministic_reset,
            "socket_pos_override": list(args_cli.socket_pos) if args_cli.socket_pos is not None else None,
            "trace_json": os.path.abspath(args_cli.trace_json) if args_cli.trace_json else None,
        }
        print(
            "[BC-EVAL] summary "
            f"final_lateral={summary['final_lateral']:.4f} final_axial={summary['final_axial']:.4f} "
            f"final_rot={summary['final_rot']:.4f} max_contact={summary['max_contact_force_magnitude']:.3f} "
            f"success_step={summary['success_step']}",
            flush=True,
        )
        if args_cli.summary_json:
            summary_path = os.path.abspath(args_cli.summary_json)
            os.makedirs(os.path.dirname(summary_path), exist_ok=True)
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, sort_keys=True)
        if args_cli.trace_json:
            trace_path = os.path.abspath(args_cli.trace_json)
            os.makedirs(os.path.dirname(trace_path), exist_ok=True)
            with open(trace_path, "w", encoding="utf-8") as f:
                json.dump({"summary": summary, "steps": trace_rows}, f, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
