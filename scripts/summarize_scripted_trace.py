#!/usr/bin/env python3
"""Summarize scripted rollout trace geometry around selected steps."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _normalize_quat(quat: list[float] | None) -> list[float] | None:
    if quat is None:
        return None
    norm = math.sqrt(sum(value * value for value in quat))
    if norm <= 0.0:
        return None
    return [value / norm for value in quat]


def _quat_angle(a: list[float] | None, b: list[float] | None) -> float | None:
    qa = _normalize_quat(a)
    qb = _normalize_quat(b)
    if qa is None or qb is None:
        return None
    dot = abs(sum(x * y for x, y in zip(qa, qb, strict=True)))
    dot = min(1.0, max(-1.0, dot))
    return 2.0 * math.acos(dot)


def _vec_dist(a: list[float] | None, b: list[float] | None) -> float | None:
    if a is None or b is None:
        return None
    return math.sqrt(sum((x - y) * (x - y) for x, y in zip(a, b, strict=True)))


def _fmt(value: Any, precision: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.{precision}f}"
    return str(value)


def _step_indices(num_steps: int, requested: list[int] | None) -> list[int]:
    if requested:
        return [idx for idx in requested if 0 <= idx < num_steps]
    candidates = [0, 25, 50, 75, 100, 125, 150, 175, 200, num_steps - 1]
    return sorted({idx for idx in candidates if 0 <= idx < num_steps})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_json", type=Path)
    parser.add_argument("--steps", type=int, nargs="*", help="Specific trace step indices to print.")
    args = parser.parse_args()

    data = json.loads(args.trace_json.read_text(encoding="utf-8"))
    steps = data["steps"]
    rows = []
    for idx in _step_indices(len(steps), args.steps):
        step = steps[idx]
        action_quat = step.get("post_action_quat_w") or step.get("action_quat_w")
        command_quat = step.get("command_quat_w")
        target_quat = step.get("target_quat_w") or step.get("target_action_quat_w")
        socket_quat = step.get("post_socket_quat_w") or step.get("socket_quat_w")
        physical_quat = step.get("post_physical_tip_quat_w") or step.get("physical_tip_quat_w")
        raw_action = step.get("raw_action") or []
        if command_quat is None and len(raw_action) >= 7:
            command_quat = raw_action[3:7]
        action_pos = step.get("post_action_pos_w") or step.get("action_pos_w")
        command_pos = step.get("command_pos_w")
        target_action_pos = step.get("target_action_pos_w")
        rotate_hold_pos = step.get("rotate_hold_pos_w")

        rows.append(
            {
                "step": step.get("step", idx),
                "phase": step.get("phase"),
                "lat": step.get("lateral"),
                "ax": step.get("axial"),
                "rot": step.get("rot"),
                "axis_norm": step.get("axis_angle_error_norm"),
                "act_cmd": _quat_angle(action_quat, command_quat),
                "act_target": _quat_angle(action_quat, target_quat),
                "cmd_target": _quat_angle(command_quat, target_quat),
                "tip_socket": _quat_angle(physical_quat, socket_quat),
                "action_target_pos": _vec_dist(action_pos, target_action_pos),
                "cmd_target_pos": _vec_dist(command_pos, target_action_pos),
                "cmd_hold_pos": _vec_dist(command_pos, rotate_hold_pos),
                "insert_xy_ready": step.get("insert_xy_ready"),
                "insert_state": step.get("insert_state"),
                "insert_entry": step.get("insert_entry"),
                "insert_new": step.get("insert_new_entry"),
                "insert_abort_violation": step.get("insert_abort_violation"),
                "insert_abort_count": step.get("insert_abort_count"),
                "insert_abort_grace_steps": step.get("insert_abort_grace_steps"),
                "insert_aborted": step.get("insert_aborted"),
                "insert_mode": step.get("insert_descent_mode"),
                "jcache": step.get("joint_cache_active"),
                "jcache_seed": step.get("joint_cache_seed"),
                "jcache_steps": step.get("joint_cache_step_count"),
                "hold_insert": step.get("hold_orientation_during_insert"),
                "insert_hold": step.get("insert_hold_valid"),
                "succ_xy": step.get("success_xy_ready"),
                "succ_z": step.get("success_axial_ready"),
                "succ_rot": step.get("success_rot_ready"),
                "succ_xy_m": step.get("success_xy_margin"),
                "succ_z_m": step.get("success_axial_margin"),
                "succ_rot_m": step.get("success_rot_margin"),
                "contact": step.get("contact_force_magnitude"),
                "jlim": step.get("post_joint_limit_margin_min") or step.get("joint_limit_margin_min"),
                "xy": step.get("xy_state"),
                "ori": step.get("orientation_ready"),
                "pos": step.get("position_ready"),
                "desc": step.get("descend_mask"),
                "insert": step.get("insert_mask"),
                "aligned": step.get("aligned_state"),
                "branch": step.get("branch_jump"),
            }
        )

    headers = [
        "step",
        "phase",
        "lat",
        "ax",
        "rot",
        "axis_norm",
        "act_cmd",
        "act_target",
        "cmd_target",
        "tip_socket",
        "action_target_pos",
        "cmd_target_pos",
        "cmd_hold_pos",
        "insert_xy_ready",
        "insert_state",
        "insert_entry",
        "insert_new",
        "insert_abort_violation",
        "insert_abort_count",
        "insert_abort_grace_steps",
        "insert_aborted",
        "insert_mode",
        "jcache",
        "jcache_seed",
        "jcache_steps",
        "hold_insert",
        "insert_hold",
        "succ_xy",
        "succ_z",
        "succ_rot",
        "succ_xy_m",
        "succ_z_m",
        "succ_rot_m",
        "contact",
        "jlim",
        "xy",
        "ori",
        "pos",
        "desc",
        "insert",
        "aligned",
        "branch",
    ]
    print("\t".join(headers))
    for row in rows:
        print("\t".join(_fmt(row[header]) for header in headers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
