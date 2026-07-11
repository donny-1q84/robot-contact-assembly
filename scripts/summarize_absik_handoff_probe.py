#!/usr/bin/env python3
"""Summarize an Abs IK scripted handoff probe into compact JSON."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_XY_TOLERANCE = 0.005
DEFAULT_Z_TOLERANCE = 0.045
DEFAULT_ROT_TOLERANCE = 0.18
DEFAULT_MIN_CONTACT_FORCE = 0.5


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object in {path}")
    return data


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _step_number(step: dict[str, Any], fallback: int) -> int:
    parsed = _int_or_none(step.get("step"))
    return fallback if parsed is None else parsed


def _metric(step: dict[str, Any], key: str) -> float | None:
    return _float_or_none(step.get(key))


def _strict_miss_score(
    step: dict[str, Any],
    *,
    xy_tol: float,
    z_tol: float,
    rot_tol: float,
    min_contact: float,
) -> float:
    lateral = _metric(step, "lateral") or 0.0
    axial = _metric(step, "axial") or 0.0
    rot = _metric(step, "rot") or 0.0
    contact = _metric(step, "contact_force_magnitude") or 0.0
    return (
        max(0.0, lateral - xy_tol) * 100.0
        + max(0.0, axial - z_tol) * 100.0
        + max(0.0, rot - rot_tol) * 10.0
        + max(0.0, min_contact - contact)
    )


def _strict_miss_components(
    step: dict[str, Any],
    *,
    xy_tol: float,
    z_tol: float,
    rot_tol: float,
    min_contact: float,
) -> dict[str, float]:
    lateral = _metric(step, "lateral") or 0.0
    axial = _metric(step, "axial") or 0.0
    rot = _metric(step, "rot") or 0.0
    contact = _metric(step, "contact_force_magnitude") or 0.0
    return {
        "lateral": max(0.0, lateral - xy_tol) * 100.0,
        "axial": max(0.0, axial - z_tol) * 100.0,
        "rot": max(0.0, rot - rot_tol) * 10.0,
        "contact": max(0.0, min_contact - contact),
    }


def _selected_from_step(step: dict[str, Any], index: int, score: float) -> dict[str, Any]:
    return {
        "index": index,
        "step": _step_number(step, index),
        "phase": step.get("phase"),
        "strict_miss_score": score,
        "lateral": _metric(step, "lateral"),
        "axial": _metric(step, "axial"),
        "rot": _metric(step, "rot"),
        "contact_force_magnitude": _metric(step, "contact_force_magnitude"),
        "rotate_xy_recovery": step.get("rotate_xy_recovery"),
        "descend_xy_recovery": step.get("descend_xy_recovery"),
        "depth_rotation_polish_active": step.get("depth_rotation_polish_active"),
        "depth_rotation_polish_command_valid": step.get("depth_rotation_polish_command_valid"),
        "success": step.get("success"),
    }


def _best_step(
    steps: list[dict[str, Any]],
    key: str,
    *,
    maximize: bool = False,
) -> dict[str, Any] | None:
    scored = [(value, index, step) for index, step in enumerate(steps) if (value := _metric(step, key)) is not None]
    if not scored:
        return None
    value, index, step = (max if maximize else min)(scored, key=lambda item: item[0])
    return {
        "step": _step_number(step, index),
        "phase": step.get("phase"),
        key: value,
    }


def _first_ready_step(
    steps: list[dict[str, Any]],
    predicate,
) -> dict[str, Any] | None:
    for index, step in enumerate(steps):
        if predicate(step):
            return {
                "step": _step_number(step, index),
                "phase": step.get("phase"),
                "lateral": _metric(step, "lateral"),
                "axial": _metric(step, "axial"),
                "rot": _metric(step, "rot"),
                "contact_force_magnitude": _metric(step, "contact_force_magnitude"),
            }
    return None


def _extract_steps(trace: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = trace.get("steps")
    if not isinstance(raw_steps, list):
        return []
    return [step for step in raw_steps if isinstance(step, dict)]


def _count_if(steps: list[dict[str, Any]], predicate) -> int:
    return sum(1 for step in steps if predicate(step))


def _phase_counts(steps: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        phase = str(step.get("phase") or "unknown")
        counts[phase] = counts.get(phase, 0) + 1
    return dict(sorted(counts.items()))


def _summary_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": summary.get("task"),
        "scripted_control_mode": summary.get("scripted_control_mode"),
        "abs_control_mode": summary.get("abs_control_mode"),
        "mdp_abs_action_frame": summary.get("mdp_abs_action_frame"),
        "mdp_abs_ik_method": summary.get("mdp_abs_ik_method"),
        "mdp_abs_ik_params": summary.get("mdp_abs_ik_params"),
        "mdp_abs_orientation_command_mode": summary.get("mdp_abs_orientation_command_mode"),
        "joint_ik_step": _float_or_none(summary.get("joint_ik_step")),
        "joint_step_limit_mode": summary.get("joint_step_limit_mode"),
        "joint_limit_margin": _float_or_none(summary.get("joint_limit_margin")),
        "joint_limit_nullspace_gain": _float_or_none(summary.get("joint_limit_nullspace_gain")),
        "joint_limit_nullspace_activation_margin": _float_or_none(
            summary.get("joint_limit_nullspace_activation_margin")
        ),
        "joint_limit_nullspace_step": _float_or_none(summary.get("joint_limit_nullspace_step")),
        "joint_limit_nullspace_damping": _float_or_none(summary.get("joint_limit_nullspace_damping")),
        "max_joint_limit_nullspace_delta_norm": _float_or_none(
            summary.get("max_joint_limit_nullspace_delta_norm")
        ),
        "max_joint_limit_nullspace_delta_norm_step": summary.get("max_joint_limit_nullspace_delta_norm_step"),
        "disable_socket_wall_collisions": summary.get("disable_socket_wall_collisions"),
        "target_action_pos_offset": summary.get("target_action_pos_offset"),
        "rotate_descent_mode": summary.get("rotate_descent_mode"),
        "insert_rotation_gated_descent": summary.get("insert_rotation_gated_descent"),
        "insert_descent_rot_tolerance": _float_or_none(summary.get("insert_descent_rot_tolerance")),
        "insert_rotation_gate_descent_scale": _float_or_none(
            summary.get("insert_rotation_gate_descent_scale")
        ),
        "insert_rotation_gate_min_descent_step": _float_or_none(
            summary.get("insert_rotation_gate_min_descent_step")
        ),
        "insert_rotation_gate_allowed_descent_max": _float_or_none(
            summary.get("insert_rotation_gate_allowed_descent_max")
        ),
        "depth_rotation_polish": summary.get("depth_rotation_polish"),
        "depth_rotation_polish_xy_tolerance": _float_or_none(
            summary.get("depth_rotation_polish_xy_tolerance")
        ),
        "depth_rotation_polish_z_tolerance": _float_or_none(
            summary.get("depth_rotation_polish_z_tolerance")
        ),
        "depth_rotation_polish_contact_min_force": _float_or_none(
            summary.get("depth_rotation_polish_contact_min_force")
        ),
        "depth_rotation_polish_exit_contact_min_force": _float_or_none(
            summary.get("depth_rotation_polish_exit_contact_min_force")
        ),
        "depth_rotation_polish_orientation_mode": summary.get("depth_rotation_polish_orientation_mode"),
        "depth_rotation_polish_exit_xy_tolerance": _float_or_none(
            summary.get("depth_rotation_polish_exit_xy_tolerance")
        ),
        "depth_rotation_polish_exit_z_tolerance": _float_or_none(
            summary.get("depth_rotation_polish_exit_z_tolerance")
        ),
        "depth_rotation_polish_preload_step": _float_or_none(
            summary.get("depth_rotation_polish_preload_step")
        ),
        "depth_rotation_polish_rot_step": _float_or_none(summary.get("depth_rotation_polish_rot_step")),
        "seed": summary.get("seed"),
        "steps_requested": summary.get("steps_requested"),
        "initial_joint_pos_overrides": summary.get("initial_joint_pos_overrides"),
        "success_step": summary.get("success_step"),
        "final_success_rate": summary.get("final_success_rate"),
        "initial_lateral": _float_or_none(summary.get("initial_lateral")),
        "initial_axial": _float_or_none(summary.get("initial_axial")),
        "initial_rot": _float_or_none(summary.get("initial_rot")),
        "final_lateral": _float_or_none(summary.get("final_lateral")),
        "final_axial": _float_or_none(summary.get("final_axial")),
        "final_rot": _float_or_none(summary.get("final_rot")),
        "best_lateral": _float_or_none(summary.get("best_lateral")),
        "best_lateral_step": summary.get("best_lateral_step"),
        "best_axial": _float_or_none(summary.get("best_axial")),
        "best_axial_step": summary.get("best_axial_step"),
        "best_rot": _float_or_none(summary.get("best_rot")),
        "best_rot_step": summary.get("best_rot_step"),
        "arm_joint_names": summary.get("arm_joint_names"),
        "min_arm_joint_limit_margin": _float_or_none(summary.get("min_arm_joint_limit_margin")),
        "min_arm_joint_limit_margin_step": summary.get("min_arm_joint_limit_margin_step"),
        "min_arm_joint_limit_margin_joint_index": summary.get("min_arm_joint_limit_margin_joint_index"),
        "min_arm_joint_limit_margin_joint_name": summary.get("min_arm_joint_limit_margin_joint_name"),
        "rotate_xy_recovery_step_count": summary.get("rotate_xy_recovery_step_count"),
        "rotate_xy_recovery_first_step": summary.get("rotate_xy_recovery_first_step"),
        "rotate_xy_recovery_last_step": summary.get("rotate_xy_recovery_last_step"),
        "rotate_xy_recovery_max_lateral": _float_or_none(summary.get("rotate_xy_recovery_max_lateral")),
        "rotate_descent_step_count": summary.get("rotate_descent_step_count"),
        "rotate_descent_first_step": summary.get("rotate_descent_first_step"),
        "rotate_descent_last_step": summary.get("rotate_descent_last_step"),
        "insert_rotation_gate_step_count": summary.get("insert_rotation_gate_step_count"),
        "insert_rotation_gate_first_step": summary.get("insert_rotation_gate_first_step"),
        "insert_rotation_gate_last_step": summary.get("insert_rotation_gate_last_step"),
        "insert_rotation_gate_max_rot": _float_or_none(summary.get("insert_rotation_gate_max_rot")),
        "depth_rotation_polish_step_count": summary.get("depth_rotation_polish_step_count"),
        "depth_rotation_polish_first_step": summary.get("depth_rotation_polish_first_step"),
        "depth_rotation_polish_last_step": summary.get("depth_rotation_polish_last_step"),
        "depth_rotation_polish_max_rot": _float_or_none(summary.get("depth_rotation_polish_max_rot")),
        "depth_rotation_polish_max_lateral": _float_or_none(
            summary.get("depth_rotation_polish_max_lateral")
        ),
        "depth_rotation_polish_min_axial": _float_or_none(summary.get("depth_rotation_polish_min_axial")),
        "descend_xy_recovery_step_count": summary.get("descend_xy_recovery_step_count"),
        "descend_xy_recovery_first_step": summary.get("descend_xy_recovery_first_step"),
        "descend_xy_recovery_last_step": summary.get("descend_xy_recovery_last_step"),
        "descend_xy_recovery_max_lateral": _float_or_none(summary.get("descend_xy_recovery_max_lateral")),
    }


def build_probe_summary(args: argparse.Namespace) -> dict[str, Any]:
    trace = _load_json(args.trace_json)
    summary = _load_json(args.summary_json)
    handoff = _load_json(args.handoff_json)
    steps = _extract_steps(trace)
    candidate_steps = [
        (index, step)
        for index, step in enumerate(steps)
        if isinstance(step.get("raw_action"), list) and len(step["raw_action"]) == args.action_dim
    ]

    best_scored: list[tuple[float, int, dict[str, Any]]] = [
        (
            _strict_miss_score(
                step,
                xy_tol=args.success_xy_tol,
                z_tol=args.success_z_tol,
                rot_tol=args.success_rot_tol,
                min_contact=args.success_min_contact_force,
            ),
            index,
            step,
        )
        for index, step in candidate_steps
    ]
    closest_candidate = None
    if best_scored:
        score, index, step = min(best_scored, key=lambda item: item[0])
        closest_candidate = _selected_from_step(step, index, score)

    selected_miss = _float_or_none(handoff.get("strict_miss_score"))
    selected_passes_guard = selected_miss is not None and selected_miss <= args.max_strict_miss

    xy_ready = lambda step: (_metric(step, "lateral") or float("inf")) <= args.success_xy_tol
    z_ready = lambda step: (_metric(step, "axial") or float("inf")) <= args.success_z_tol
    rot_ready = lambda step: (_metric(step, "rot") or float("inf")) <= args.success_rot_tol
    contact_ready = lambda step: (_metric(step, "contact_force_magnitude") or 0.0) >= args.success_min_contact_force
    strict_ready = lambda step: xy_ready(step) and z_ready(step) and rot_ready(step) and contact_ready(step)

    return {
        "trace_json": str(args.trace_json),
        "summary_json": str(args.summary_json) if args.summary_json else None,
        "handoff_json": str(args.handoff_json),
        "thresholds": {
            "success_xy_tol": args.success_xy_tol,
            "success_z_tol": args.success_z_tol,
            "success_rot_tol": args.success_rot_tol,
            "success_min_contact_force": args.success_min_contact_force,
            "handoff_max_strict_miss": args.max_strict_miss,
        },
        "scripted_summary": _summary_metrics(summary),
        "trace": {
            "step_count": len(steps),
            "candidate_step_count": len(candidate_steps),
            "phase_counts": _phase_counts(steps),
            "xy_ready_step_count": _count_if(steps, xy_ready),
            "z_ready_step_count": _count_if(steps, z_ready),
            "rot_ready_step_count": _count_if(steps, rot_ready),
            "contact_ready_step_count": _count_if(steps, contact_ready),
            "xy_z_rot_ready_step_count": _count_if(steps, lambda step: xy_ready(step) and z_ready(step) and rot_ready(step)),
            "strict_ready_step_count": _count_if(steps, strict_ready),
            "first_xy_ready_step": _first_ready_step(steps, xy_ready),
            "first_z_ready_step": _first_ready_step(steps, z_ready),
            "first_rot_ready_step": _first_ready_step(steps, rot_ready),
            "first_contact_ready_step": _first_ready_step(steps, contact_ready),
            "first_strict_ready_step": _first_ready_step(steps, strict_ready),
            "best_lateral_step": _best_step(steps, "lateral"),
            "best_axial_step": _best_step(steps, "axial"),
            "best_rot_step": _best_step(steps, "rot"),
            "max_contact_step": _best_step(steps, "contact_force_magnitude", maximize=True),
        },
        "selected_handoff": {
            "index": handoff.get("index"),
            "step": handoff.get("step"),
            "phase": handoff.get("phase"),
            "strict_miss_score": selected_miss,
            "strict_miss_components": _strict_miss_components(
                handoff,
                xy_tol=args.success_xy_tol,
                z_tol=args.success_z_tol,
                rot_tol=args.success_rot_tol,
                min_contact=args.success_min_contact_force,
            ),
            "passes_handoff_guard": selected_passes_guard,
            "lateral": _float_or_none(handoff.get("lateral")),
            "axial": _float_or_none(handoff.get("axial")),
            "rot": _float_or_none(handoff.get("rot")),
            "contact_force_magnitude": _float_or_none(handoff.get("contact_force_magnitude")),
            "rotate_xy_recovery": handoff.get("rotate_xy_recovery"),
            "descend_xy_recovery": handoff.get("descend_xy_recovery"),
            "success": handoff.get("success"),
        },
        "closest_candidate_recomputed": closest_candidate,
        "decision": {
            "status": "pass" if selected_passes_guard else "fail_closed",
            "reason": (
                "selected handoff is inside strict-miss guard"
                if selected_passes_guard
                else "selected handoff exceeds strict-miss guard"
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-json", type=Path, required=True)
    parser.add_argument("--handoff-json", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--action-dim", type=int, default=7)
    parser.add_argument("--success-xy-tol", type=float, default=DEFAULT_XY_TOLERANCE)
    parser.add_argument("--success-z-tol", type=float, default=DEFAULT_Z_TOLERANCE)
    parser.add_argument("--success-rot-tol", type=float, default=DEFAULT_ROT_TOLERANCE)
    parser.add_argument("--success-min-contact-force", type=float, default=DEFAULT_MIN_CONTACT_FORCE)
    parser.add_argument("--max-strict-miss", type=float, default=1.0)
    args = parser.parse_args()

    print(json.dumps(build_probe_summary(args), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
