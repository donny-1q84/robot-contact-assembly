#!/usr/bin/env python3
"""Validate whether a scripted trace is good enough to call a peg-in-hole video successful.

This is intentionally stricter than the task termination gate. The task gate proves
that the physical metrics reached the configured success tolerances. A video
deliverable should also show a visible insertion from above the socket and avoid
the common false positive where the peg only contacts or skims the guide lip.
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
        "socket_guide_clearance": float(module.SOCKET_GUIDE_CLEARANCE_M),
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


def _step_metric(step: dict[str, Any], name: str) -> float | None:
    return _float_or_none(step.get(name))


def _step_contact(step: dict[str, Any]) -> float | None:
    return _float_or_none(step.get("contact_force_magnitude") or step.get("pre_contact_force_magnitude"))


def _step_passes(
    step: dict[str, Any],
    *,
    lateral_tol: float,
    axial_tol: float,
    rot_tol: float,
) -> bool:
    lateral = _step_metric(step, "lateral")
    axial = _step_metric(step, "axial")
    rot = _step_metric(step, "rot")
    if lateral is None or axial is None or rot is None:
        return False
    return lateral <= lateral_tol and axial <= axial_tol and rot <= rot_tol


def _first_sustained_window(
    steps: list[dict[str, Any]],
    *,
    lateral_tol: float,
    axial_tol: float,
    rot_tol: float,
    min_steps: int,
) -> tuple[int | None, int]:
    streak = 0
    first_step = None
    for idx, step in enumerate(steps):
        if _step_passes(step, lateral_tol=lateral_tol, axial_tol=axial_tol, rot_tol=rot_tol):
            streak += 1
            if streak >= min_steps:
                first_step = int(step.get("step", idx)) - min_steps + 1
                break
        else:
            streak = 0
    return first_step, streak if first_step is not None else 0


def _best_metric(steps: list[dict[str, Any]], name: str) -> tuple[float | None, int | None]:
    best_value = None
    best_step = None
    for idx, step in enumerate(steps):
        value = _step_metric(step, name)
        if value is None:
            continue
        if best_value is None or value < best_value:
            best_value = value
            best_step = int(step.get("step", idx))
    return best_value, best_step


def _max_contact(steps: list[dict[str, Any]]) -> tuple[float | None, int | None]:
    best_value = None
    best_step = None
    for idx, step in enumerate(steps):
        value = _step_contact(step)
        if value is None:
            continue
        if best_value is None or value > best_value:
            best_value = value
            best_step = int(step.get("step", idx))
    return best_value, best_step


def evaluate_trace(
    trace: dict[str, Any],
    *,
    strict_lateral_tol: float,
    task_lateral_tol: float,
    axial_tol: float,
    rot_tol: float,
    sustained_steps: int,
    min_visible_descent: float,
    min_start_axial: float,
    min_contact_force: float,
) -> dict[str, Any]:
    steps = trace.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("trace must contain a non-empty 'steps' list")
    typed_steps = [step for step in steps if isinstance(step, dict)]
    summary = trace.get("summary") if isinstance(trace.get("summary"), dict) else {}

    first_task_window, _ = _first_sustained_window(
        typed_steps,
        lateral_tol=task_lateral_tol,
        axial_tol=axial_tol,
        rot_tol=rot_tol,
        min_steps=sustained_steps,
    )
    first_video_window, _ = _first_sustained_window(
        typed_steps,
        lateral_tol=strict_lateral_tol,
        axial_tol=axial_tol,
        rot_tol=rot_tol,
        min_steps=sustained_steps,
    )
    best_lateral, best_lateral_step = _best_metric(typed_steps, "lateral")
    best_axial, best_axial_step = _best_metric(typed_steps, "axial")
    best_rot, best_rot_step = _best_metric(typed_steps, "rot")
    max_contact, max_contact_step = _max_contact(typed_steps)

    initial_axial = _step_metric(typed_steps[0], "axial")
    final_axial = _step_metric(typed_steps[-1], "axial")
    if initial_axial is None:
        initial_axial = _float_or_none(summary.get("initial_axial"))
    if final_axial is None:
        final_axial = _float_or_none(summary.get("final_axial"))
    if best_axial is None:
        best_axial = _float_or_none(summary.get("best_axial"))
    visible_descent = None
    if initial_axial is not None and best_axial is not None:
        visible_descent = max(0.0, initial_axial - best_axial)

    summary_success_step = summary.get("success_step")
    if summary_success_step == "None":
        summary_success_step = None
    step_success_step = None
    for idx, step in enumerate(typed_steps):
        if _boolish(step.get("success")):
            step_success_step = int(step.get("step", idx))
            break

    task_gate_pass = first_task_window is not None or summary_success_step is not None or step_success_step is not None
    strict_pose_pass = first_video_window is not None
    visible_descent_pass = (
        initial_axial is not None
        and visible_descent is not None
        and initial_axial >= min_start_axial
        and visible_descent >= min_visible_descent
    )
    contact_seen = max_contact is not None and max_contact >= min_contact_force
    video_candidate_pass = task_gate_pass and strict_pose_pass and visible_descent_pass and contact_seen

    return {
        "task_gate_pass": task_gate_pass,
        "video_candidate_pass": video_candidate_pass,
        "first_task_sustained_step": first_task_window,
        "first_video_sustained_step": first_video_window,
        "summary_success_step": summary_success_step,
        "step_success_step": step_success_step,
        "thresholds": {
            "task_lateral_tol": task_lateral_tol,
            "strict_lateral_tol": strict_lateral_tol,
            "axial_tol": axial_tol,
            "rot_tol": rot_tol,
            "sustained_steps": sustained_steps,
            "min_start_axial": min_start_axial,
            "min_visible_descent": min_visible_descent,
            "min_contact_force": min_contact_force,
        },
        "metrics": {
            "initial_axial": initial_axial,
            "final_axial": final_axial,
            "visible_descent": visible_descent,
            "best_lateral": best_lateral,
            "best_lateral_step": best_lateral_step,
            "best_axial": best_axial,
            "best_axial_step": best_axial_step,
            "best_rot": best_rot,
            "best_rot_step": best_rot_step,
            "max_contact_force": max_contact,
            "max_contact_force_step": max_contact_step,
        },
        "failure_reasons": [
            reason
            for reason, failed in (
                ("task gate never reached sustained configured success tolerances", not task_gate_pass),
                ("pose never reached stricter guide-clearance lateral tolerance", not strict_pose_pass),
                ("trace does not show enough visible insertion descent from above the socket", not visible_descent_pass),
                ("wall contact was not observed above the required force threshold", not contact_seen),
            )
            if failed
        ],
    }


def main() -> int:
    constants = _load_constants()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_json", type=Path, help="Path to probe_trace.json or a trace JSON with steps+summary.")
    parser.add_argument("--sustained-steps", type=int, default=5)
    parser.add_argument("--min-visible-descent", type=float, default=0.030)
    parser.add_argument("--min-start-axial", type=float, default=0.035)
    parser.add_argument("--min-contact-force", type=float, default=0.5)
    parser.add_argument("--task-lateral-tol", type=float, default=constants["success_xy_tolerance"])
    parser.add_argument("--strict-lateral-tol", type=float, default=constants["socket_guide_clearance"])
    parser.add_argument("--axial-tol", type=float, default=constants["success_z_tolerance"])
    parser.add_argument("--rot-tol", type=float, default=constants["success_rot_tolerance"])
    parser.add_argument("--json", action="store_true", help="Print the full machine-readable evaluation.")
    args = parser.parse_args()

    data = json.loads(args.trace_json.read_text(encoding="utf-8"))
    result = evaluate_trace(
        data,
        strict_lateral_tol=args.strict_lateral_tol,
        task_lateral_tol=args.task_lateral_tol,
        axial_tol=args.axial_tol,
        rot_tol=args.rot_tol,
        sustained_steps=max(1, args.sustained_steps),
        min_visible_descent=max(0.0, args.min_visible_descent),
        min_start_axial=max(0.0, args.min_start_axial),
        min_contact_force=max(0.0, args.min_contact_force),
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        status = "PASS" if result["video_candidate_pass"] else "FAIL"
        print(f"[peg-video-candidate] {status}: {args.trace_json}")
        print(f"  task_gate_pass={result['task_gate_pass']}")
        print(f"  video_candidate_pass={result['video_candidate_pass']}")
        print(f"  first_task_sustained_step={result['first_task_sustained_step']}")
        print(f"  first_video_sustained_step={result['first_video_sustained_step']}")
        metrics = result["metrics"]
        print(
            "  metrics: "
            f"initial_axial={metrics['initial_axial']} "
            f"best_axial={metrics['best_axial']} "
            f"visible_descent={metrics['visible_descent']} "
            f"best_lateral={metrics['best_lateral']} "
            f"best_rot={metrics['best_rot']} "
            f"max_contact_force={metrics['max_contact_force']}"
        )
        for reason in result["failure_reasons"]:
            print(f"  fail: {reason}")
    return 0 if result["video_candidate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
