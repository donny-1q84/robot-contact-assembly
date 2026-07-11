#!/usr/bin/env python3
"""Select the best handoff step from a scripted trace JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _strict_miss_score(
    step: dict[str, Any],
    *,
    xy_tol: float,
    z_tol: float,
    rot_tol: float,
    min_contact: float,
) -> float:
    lateral = float(step.get("lateral") or 0.0)
    axial = float(step.get("axial") or 0.0)
    rot = float(step.get("rot") or 0.0)
    contact = float(step.get("contact_force_magnitude") or 0.0)
    return (
        max(0.0, lateral - xy_tol) * 100.0
        + max(0.0, axial - z_tol) * 100.0
        + max(0.0, rot - rot_tol) * 10.0
        + max(0.0, min_contact - contact)
    )


def _step_number(step: dict[str, Any], fallback: int) -> int:
    raw_step = step.get("step")
    return int(raw_step if raw_step is not None else fallback)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-json", required=True, help="Scripted trace JSON to scan.")
    parser.add_argument("--action-dim", type=int, default=7, help="Expected action dimension.")
    parser.add_argument("--phase", action="append", default=None, help="Optional phase filter; may be repeated.")
    parser.add_argument("--success-xy-tol", type=float, default=0.005)
    parser.add_argument("--success-z-tol", type=float, default=0.045)
    parser.add_argument("--success-rot-tol", type=float, default=0.18)
    parser.add_argument("--success-min-contact-force", type=float, default=0.5)
    parser.add_argument("--json", action="store_true", default=False, help="Print the selected row as JSON.")
    args = parser.parse_args()

    trace_path = Path(args.trace_json)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    allowed_phases = set(args.phase or [])

    candidates: list[tuple[float, int, dict[str, Any]]] = []
    for index, step in enumerate(trace.get("steps") or []):
        if not isinstance(step, dict):
            continue
        raw_action = step.get("raw_action")
        if not isinstance(raw_action, list) or len(raw_action) != args.action_dim:
            continue
        phase = str(step.get("phase") or "")
        if allowed_phases and phase not in allowed_phases:
            continue
        score = _strict_miss_score(
            step,
            xy_tol=args.success_xy_tol,
            z_tol=args.success_z_tol,
            rot_tol=args.success_rot_tol,
            min_contact=args.success_min_contact_force,
        )
        candidates.append((score, index, step))

    if not candidates:
        raise SystemExit(f"no valid handoff candidates in {trace_path}")

    score, index, step = min(candidates, key=lambda item: item[0])
    selected = {
        "trace_json": str(trace_path),
        "index": index,
        "step": _step_number(step, index),
        "phase": step.get("phase"),
        "strict_miss_score": score,
        "lateral": step.get("lateral"),
        "axial": step.get("axial"),
        "rot": step.get("rot"),
        "contact_force_magnitude": step.get("contact_force_magnitude"),
        "rotate_xy_recovery": step.get("rotate_xy_recovery"),
        "descend_xy_recovery": step.get("descend_xy_recovery"),
        "success": step.get("success"),
    }
    if args.json:
        print(json.dumps(selected, sort_keys=True))
    else:
        print(selected["step"])


if __name__ == "__main__":
    main()
