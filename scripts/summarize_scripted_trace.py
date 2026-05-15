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
        action_quat = step.get("action_quat_w")
        command_quat = step.get("command_quat_w")
        target_quat = step.get("target_quat_w") or step.get("target_action_quat_w")
        socket_quat = step.get("socket_quat_w")
        physical_quat = step.get("physical_tip_quat_w")
        raw_action = step.get("raw_action") or []
        if command_quat is None and len(raw_action) >= 7:
            command_quat = raw_action[3:7]
        action_pos = step.get("action_pos_w")
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
                "xy": step.get("xy_state"),
                "ori": step.get("orientation_ready"),
                "pos": step.get("position_ready"),
                "insert": step.get("insert_mask"),
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
        "xy",
        "ori",
        "pos",
        "insert",
    ]
    print("\t".join(headers))
    for row in rows:
        print("\t".join(_fmt(row[header]) for header in headers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
