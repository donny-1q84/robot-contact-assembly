#!/usr/bin/env python3
"""Diagnose whether a near-insertion contact boundary trace is safe to continue.

This is a pre-video diagnostic. It does not declare a peg-in-hole video
successful. It catches the failure mode where the controller reaches the axial
success boundary with good XY/rotation/contact evidence and then keeps applying
a normal descent step, causing the peg to pop out of the guide.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
CONSTANTS_PATH = (
    REPO_ROOT
    / "source"
    / "robot_contact_assembly_tasks"
    / "robot_contact_assembly_tasks"
    / "tasks"
    / "manager_based"
    / "manipulation"
    / "peg_in_hole"
    / "constants.py"
)


def _load_constants() -> dict[str, float]:
    spec = importlib.util.spec_from_file_location("rca_peg_constants", CONSTANTS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load constants from {CONSTANTS_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        "success_xy_tolerance": float(module.SOCKET_SUCCESS_XY_TOLERANCE_M),
        "success_z_tolerance": float(module.SOCKET_SUCCESS_Z_TOLERANCE_M),
        "success_rot_tolerance": float(module.SOCKET_SUCCESS_ROT_TOLERANCE_RAD),
    }


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "pass"}
    return False


def _contact_force(step: dict[str, Any]) -> float | None:
    return _float_or_none(step.get("contact_force_magnitude") or step.get("pre_contact_force_magnitude"))


def _decision_contact_force(step: dict[str, Any]) -> float | None:
    pre_contact = _float_or_none(step.get("pre_contact_force_magnitude"))
    if pre_contact is not None:
        return pre_contact
    return _contact_force(step)


def _offset_z(step: dict[str, Any]) -> float | None:
    offset = step.get("socket_insertion_servo_offset_socket")
    if isinstance(offset, list) and len(offset) >= 3:
        return _float_or_none(offset[2])
    return None


def _step_number(step: dict[str, Any], fallback: int) -> int:
    value = step.get("step")
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _ready(
    step: dict[str, Any],
    *,
    xy_tol: float,
    axial_tol: float,
    rot_tol: float,
    contact_min_force: float,
) -> tuple[bool, bool, bool, bool]:
    lateral = _float_or_none(step.get("lateral"))
    axial = _float_or_none(step.get("axial"))
    rot = _float_or_none(step.get("rot"))
    contact = _contact_force(step)
    return (
        lateral is not None and lateral <= xy_tol,
        axial is not None and axial <= axial_tol,
        rot is not None and rot <= rot_tol,
        contact is not None and contact >= contact_min_force,
    )


def _sustained_success(
    steps: list[dict[str, Any]],
    *,
    xy_tol: float,
    axial_tol: float,
    rot_tol: float,
    contact_min_force: float,
    sustained_steps: int,
) -> int | None:
    streak = 0
    for idx, step in enumerate(steps):
        xy_ready, axial_ready, rot_ready, contact_ready = _ready(
            step,
            xy_tol=xy_tol,
            axial_tol=axial_tol,
            rot_tol=rot_tol,
            contact_min_force=contact_min_force,
        )
        if _boolish(step.get("success")) or (xy_ready and axial_ready and rot_ready and contact_ready):
            streak += 1
            if streak >= sustained_steps:
                return _step_number(step, idx) - sustained_steps + 1
        else:
            streak = 0
    return None


def evaluate_trace(
    trace: dict[str, Any],
    *,
    xy_tol: float,
    axial_tol: float,
    rot_tol: float,
    contact_min_force: float,
    boundary_contact_min_force: float,
    boundary_axial_band: float,
    max_boundary_step: float,
    pop_lateral_jump: float,
    pop_lateral_abs: float,
    pop_axial_regress: float,
    sustained_steps: int,
) -> dict[str, Any]:
    raw_steps = trace.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("trace must contain a non-empty 'steps' list")
    steps = [step for step in raw_steps if isinstance(step, dict)]
    if not steps:
        raise ValueError("trace does not contain dictionary step rows")

    boundary_rows: list[dict[str, Any]] = []
    unsafe_boundary_descents: list[dict[str, Any]] = []
    contact_boundary_micro_steps: list[dict[str, Any]] = []
    pop_events: list[dict[str, Any]] = []

    boundary_axial_tol = axial_tol + max(0.0, boundary_axial_band)
    max_boundary_step = max(0.0, max_boundary_step)

    for idx, step in enumerate(steps):
        xy_ready, axial_ready, rot_ready, contact_ready = _ready(
            step,
            xy_tol=xy_tol,
            axial_tol=axial_tol,
            rot_tol=rot_tol,
            contact_min_force=contact_min_force,
        )
        axial = _float_or_none(step.get("axial"))
        lateral = _float_or_none(step.get("lateral"))
        rot = _float_or_none(step.get("rot"))
        if axial is None or lateral is None or rot is None:
            continue

        decision_contact = _decision_contact_force(step)
        boundary_contact_ready = (
            decision_contact is not None
            and decision_contact >= max(0.0, boundary_contact_min_force)
        )
        near_boundary = xy_ready and rot_ready and boundary_contact_ready and axial <= boundary_axial_tol
        if not near_boundary:
            continue

        row = {
            "step": _step_number(step, idx),
            "lateral": lateral,
            "axial": axial,
            "rot": rot,
            "contact_force": _contact_force(step),
            "decision_contact_force": decision_contact,
            "offset_z": _offset_z(step),
            "success_axial_ready": axial_ready,
            "contact_boundary": _boolish(step.get("socket_insertion_servo_contact_boundary")),
        }
        boundary_rows.append(row)

        offset_z = row["offset_z"]
        if (
            not axial_ready
            and offset_z is not None
            and offset_z < -(max_boundary_step + 1.0e-9)
            and not row["contact_boundary"]
        ):
            unsafe_boundary_descents.append(row)
        if row["contact_boundary"]:
            contact_boundary_micro_steps.append(row)

        if idx + 1 >= len(steps):
            continue
        next_step = steps[idx + 1]
        next_lateral = _float_or_none(next_step.get("lateral"))
        next_axial = _float_or_none(next_step.get("axial"))
        next_rot = _float_or_none(next_step.get("rot"))
        lateral_jump = None if next_lateral is None else next_lateral - lateral
        axial_regress = None if next_axial is None else next_axial - axial
        if (
            (lateral_jump is not None and lateral_jump >= pop_lateral_jump)
            or (next_lateral is not None and next_lateral >= pop_lateral_abs)
            or (axial_regress is not None and axial_regress >= pop_axial_regress)
        ):
            pop_events.append(
                {
                    "from_step": row["step"],
                    "to_step": _step_number(next_step, idx + 1),
                    "lateral": lateral,
                    "next_lateral": next_lateral,
                    "lateral_jump": lateral_jump,
                    "axial": axial,
                    "next_axial": next_axial,
                    "axial_regress": axial_regress,
                    "rot": rot,
                    "next_rot": next_rot,
                    "offset_z": offset_z,
                }
            )

    first_success_step = _sustained_success(
        steps,
        xy_tol=xy_tol,
        axial_tol=axial_tol,
        rot_tol=rot_tol,
        contact_min_force=contact_min_force,
        sustained_steps=max(1, sustained_steps),
    )
    pass_gate = bool(first_success_step is not None and not unsafe_boundary_descents and not pop_events)
    return {
        "pass_gate": pass_gate,
        "first_sustained_success_step": first_success_step,
        "boundary_row_count": len(boundary_rows),
        "unsafe_boundary_descent_count": len(unsafe_boundary_descents),
        "contact_boundary_micro_step_count": len(contact_boundary_micro_steps),
        "pop_event_count": len(pop_events),
        "first_boundary_row": boundary_rows[0] if boundary_rows else None,
        "first_unsafe_boundary_descent": unsafe_boundary_descents[0] if unsafe_boundary_descents else None,
        "first_contact_boundary_micro_step": contact_boundary_micro_steps[0] if contact_boundary_micro_steps else None,
        "first_pop_event": pop_events[0] if pop_events else None,
        "thresholds": {
            "xy_tol": xy_tol,
            "axial_tol": axial_tol,
            "rot_tol": rot_tol,
            "contact_min_force": contact_min_force,
            "boundary_contact_min_force": boundary_contact_min_force,
            "boundary_axial_band": boundary_axial_band,
            "max_boundary_step": max_boundary_step,
            "pop_lateral_jump": pop_lateral_jump,
            "pop_lateral_abs": pop_lateral_abs,
            "pop_axial_regress": pop_axial_regress,
            "sustained_steps": sustained_steps,
        },
        "failure_reasons": [
            reason
            for reason, failed in (
                ("no sustained task-success window at the contact boundary", first_success_step is None),
                ("no near-boundary contact row was observed", not boundary_rows),
                ("controller used a normal descent step after contact near the axial boundary", bool(unsafe_boundary_descents)),
                ("trace popped laterally or axially after reaching the contact boundary", bool(pop_events)),
            )
            if failed
        ],
    }


def _evaluate_path(path: Path, args: argparse.Namespace) -> dict[str, Any]:
    trace = json.loads(path.read_text(encoding="utf-8"))
    events_path = path.with_name("trace_events.jsonl")
    if events_path.exists():
        steps = trace.get("steps")
        if isinstance(steps, list):
            seen_steps = {
                _step_number(step, idx)
                for idx, step in enumerate(steps)
                if isinstance(step, dict)
            }
            event_rows: list[dict[str, Any]] = []
            for line in events_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict) or event.get("event") != "trace_row_appended":
                    continue
                step = _float_or_none(event.get("step"))
                if step is None or int(step) in seen_steps:
                    continue
                event_rows.append(
                    {
                        "step": int(step),
                        "phase": event.get("phase"),
                        "lateral": event.get("lateral"),
                        "axial": event.get("axial"),
                        "rot": event.get("rot"),
                        "success": event.get("success_rate", 0.0) == 1.0,
                        "source": "trace_events_jsonl",
                    }
                )
            if event_rows:
                trace = dict(trace)
                trace["steps"] = sorted(
                    [step for step in steps if isinstance(step, dict)] + event_rows,
                    key=lambda item: _step_number(item, 0),
                )
    return evaluate_trace(
        trace,
        xy_tol=args.xy_tol,
        axial_tol=args.axial_tol,
        rot_tol=args.rot_tol,
        contact_min_force=args.contact_min_force,
        boundary_contact_min_force=args.boundary_contact_min_force,
        boundary_axial_band=args.boundary_axial_band,
        max_boundary_step=args.max_boundary_step,
        pop_lateral_jump=args.pop_lateral_jump,
        pop_lateral_abs=args.pop_lateral_abs,
        pop_axial_regress=args.pop_axial_regress,
        sustained_steps=args.sustained_steps,
    )


def main() -> int:
    constants = _load_constants()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_json", type=Path)
    parser.add_argument("--negative-trace-json", type=Path)
    parser.add_argument("--xy-tol", type=float, default=constants["success_xy_tolerance"])
    parser.add_argument("--axial-tol", type=float, default=constants["success_z_tolerance"])
    parser.add_argument("--rot-tol", type=float, default=constants["success_rot_tolerance"])
    parser.add_argument("--contact-min-force", type=float, default=0.5)
    parser.add_argument("--boundary-contact-min-force", type=float, default=0.25)
    parser.add_argument("--boundary-axial-band", type=float, default=0.001)
    parser.add_argument("--max-boundary-step", type=float, default=0.00015)
    parser.add_argument("--pop-lateral-jump", type=float, default=0.010)
    parser.add_argument("--pop-lateral-abs", type=float, default=0.020)
    parser.add_argument("--pop-axial-regress", type=float, default=0.004)
    parser.add_argument("--sustained-steps", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = _evaluate_path(args.trace_json, args)
    if args.negative_trace_json is not None:
        negative = _evaluate_path(args.negative_trace_json, args)
        result["negative_control"] = negative
        if negative["pass_gate"]:
            result["pass_gate"] = False
            result["failure_reasons"].append("negative control unexpectedly passed final-contact boundary gate")

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        status = "PASS" if result["pass_gate"] else "FAIL"
        print(f"[final-contact-boundary] {status}: {args.trace_json}")
        print(f"  first_sustained_success_step={result['first_sustained_success_step']}")
        print(f"  boundary_row_count={result['boundary_row_count']}")
        print(f"  unsafe_boundary_descent_count={result['unsafe_boundary_descent_count']}")
        print(f"  contact_boundary_micro_step_count={result['contact_boundary_micro_step_count']}")
        print(f"  pop_event_count={result['pop_event_count']}")
        if result["first_unsafe_boundary_descent"]:
            print(f"  first_unsafe_boundary_descent={result['first_unsafe_boundary_descent']}")
        if result["first_pop_event"]:
            print(f"  first_pop_event={result['first_pop_event']}")
        for reason in result["failure_reasons"]:
            print(f"  fail: {reason}")
    return 0 if result["pass_gate"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
