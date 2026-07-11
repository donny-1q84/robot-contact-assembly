#!/usr/bin/env python3
"""Validate that an empirical action calibration is usable for insertion control."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


AXES = ("x", "y", "z")


def _vec3(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must be a 3-vector")
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain numeric values") from exc


def _sub(lhs: tuple[float, float, float], rhs: tuple[float, float, float]) -> tuple[float, float, float]:
    return (lhs[0] - rhs[0], lhs[1] - rhs[1], lhs[2] - rhs[2])


def _add(lhs: tuple[float, float, float], rhs: tuple[float, float, float]) -> tuple[float, float, float]:
    return (lhs[0] + rhs[0], lhs[1] + rhs[1], lhs[2] + rhs[2])


def _scale(value: tuple[float, float, float], factor: float) -> tuple[float, float, float]:
    return (value[0] * factor, value[1] * factor, value[2] * factor)


def _norm(value: tuple[float, float, float]) -> float:
    return math.sqrt(sum(part * part for part in value))


def _probe_delta(probes: dict[str, Any], name: str) -> tuple[float, float, float]:
    probe = probes.get(name)
    if not isinstance(probe, dict):
        raise ValueError(f"missing probe {name}")
    return _vec3(probe.get("delta_action_pos"), f"probe {name} delta_action_pos")


def validate_summary(path: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    probes = payload.get("probes")
    if not isinstance(probes, dict):
        raise ValueError(f"{path} missing probes object")
    action_magnitude = float(payload.get("action_magnitude", 0.0))
    if action_magnitude <= 0.0:
        raise ValueError(f"{path} has invalid action_magnitude={action_magnitude!r}")

    zero_delta = _probe_delta(probes, "zero")
    columns: dict[str, tuple[float, float, float]] = {}
    dominant: dict[str, dict[str, Any]] = {}
    failures: list[str] = []

    if _norm(zero_delta) > args.max_zero_drift:
        failures.append(
            f"zero-action drift {_norm(zero_delta):.6f}m exceeds {args.max_zero_drift:.6f}m"
        )

    used_dominant_axes: set[str] = set()
    for axis_index, axis_name in enumerate(AXES):
        pos_delta = _probe_delta(probes, f"{axis_name}_pos")
        neg_delta = _probe_delta(probes, f"{axis_name}_neg")
        column = _scale(_sub(pos_delta, neg_delta), 1.0 / (2.0 * action_magnitude))
        columns[axis_name] = column
        abs_parts = [abs(part) for part in column]
        dominant_index = max(range(3), key=lambda idx: abs_parts[idx])
        dominant_axis = AXES[dominant_index]
        expected_gain = column[axis_index]
        off_axis_norm = _norm(tuple(column[idx] if idx != axis_index else 0.0 for idx in range(3)))
        common_drift = _scale(_add(pos_delta, neg_delta), 0.5)
        common_drift_norm = _norm(common_drift)
        command_response_norm = _norm(_scale(_sub(pos_delta, neg_delta), 0.5))
        common_drift_ratio = common_drift_norm / max(command_response_norm, 1.0e-12)

        dominant[axis_name] = {
            "column": list(column),
            "dominant_axis": dominant_axis,
            "dominant_gain": column[dominant_index],
            "expected_axis_gain": expected_gain,
            "off_axis_norm": off_axis_norm,
            "common_drift_norm": common_drift_norm,
            "common_drift_ratio": common_drift_ratio,
        }

        if dominant_axis != axis_name:
            failures.append(
                f"{axis_name} raw action dominantly moves world {dominant_axis}, not world {axis_name}"
            )
        if expected_gain < args.min_axis_gain:
            failures.append(
                f"{axis_name} expected-axis gain {expected_gain:.6f} is below {args.min_axis_gain:.6f}"
            )
        if abs(expected_gain) < args.min_diagonal_ratio * max(off_axis_norm, 1.0e-12):
            failures.append(
                f"{axis_name} expected-axis response is not dominant enough "
                f"(gain={expected_gain:.6f}, off_axis_norm={off_axis_norm:.6f})"
            )
        if common_drift_ratio > args.max_common_drift_ratio:
            failures.append(
                f"{axis_name} positive/negative probes have excessive common drift "
                f"(ratio={common_drift_ratio:.3f})"
            )
        if dominant_axis in used_dominant_axes:
            failures.append(f"multiple raw axes map dominantly to world {dominant_axis}")
        used_dominant_axes.add(dominant_axis)

    report = {
        "trace": str(path),
        "task": payload.get("task"),
        "action_magnitude": action_magnitude,
        "zero_delta": list(zero_delta),
        "zero_drift_norm": _norm(zero_delta),
        "dominant": dominant,
        "pass": not failures,
    }
    return report, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", type=Path)
    parser.add_argument("--max-zero-drift", type=float, default=0.004)
    parser.add_argument("--min-axis-gain", type=float, default=0.015)
    parser.add_argument("--min-diagonal-ratio", type=float, default=0.75)
    parser.add_argument("--max-common-drift-ratio", type=float, default=1.25)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report, failures = validate_summary(args.summary_json, args)
    if args.json:
        print(json.dumps({"report": report, "failures": failures}, indent=2, sort_keys=True))
    else:
        print(f"[action-calibration-check] summary={args.summary_json}")
        print(json.dumps(report, indent=2, sort_keys=True))
        if failures:
            print("[action-calibration-check] FAIL")
            for failure in failures:
                print(f"  fail: {failure}")
        else:
            print("[action-calibration-check] PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
