#!/usr/bin/env python3
"""Fail closed when scripted command deltas move the action frame the wrong way."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _vec3(row: dict[str, Any], key: str) -> list[float] | None:
    value = row.get(key)
    if not isinstance(value, list) or len(value) != 3:
        return None
    try:
        return [float(part) for part in value]
    except (TypeError, ValueError):
        return None


def _sub(lhs: list[float], rhs: list[float]) -> list[float]:
    return [lhs[i] - rhs[i] for i in range(3)]


def _dot(lhs: list[float], rhs: list[float]) -> float:
    return sum(lhs[i] * rhs[i] for i in range(3))


def _norm(vec: list[float]) -> float:
    return math.sqrt(_dot(vec, vec))


def _load_steps(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    steps = payload.get("steps") if isinstance(payload, dict) else payload
    if not isinstance(steps, list):
        raise ValueError(f"{path} does not contain a steps list")
    return [row for row in steps if isinstance(row, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_json", type=Path)
    parser.add_argument("--min-command-norm", type=float, default=1.0e-4)
    parser.add_argument("--min-actual-norm", type=float, default=1.0e-5)
    parser.add_argument("--min-cosine", type=float, default=0.0)
    parser.add_argument("--max-bad-fraction", type=float, default=0.0)
    parser.add_argument(
        "--stop-after-first-success",
        action="store_true",
        help=(
            "Assess command response only through the first successful task row. "
            "Use this for contact-rich traces where later stabilizing/contact-hold "
            "motions are validated by task-level boundary checks instead."
        ),
    )
    args = parser.parse_args()

    steps = _load_steps(args.trace_json)
    assessed: list[dict[str, Any]] = []
    skipped = 0
    first_success_step = None
    for row in steps:
        action_pos = _vec3(row, "action_pos_w")
        command_pos = _vec3(row, "command_pos_w")
        post_action_pos = _vec3(row, "post_action_pos_w")
        if action_pos is None or command_pos is None or post_action_pos is None:
            skipped += 1
            continue
        command_delta = _sub(command_pos, action_pos)
        actual_delta = _sub(post_action_pos, action_pos)
        command_norm = _norm(command_delta)
        actual_norm = _norm(actual_delta)
        if command_norm < args.min_command_norm or actual_norm < args.min_actual_norm:
            skipped += 1
            continue
        projection = _dot(command_delta, actual_delta)
        cosine = projection / max(command_norm * actual_norm, 1.0e-12)
        assessed.append(
            {
                "step": row.get("step"),
                "phase": row.get("phase"),
                "command_delta": command_delta,
                "actual_delta": actual_delta,
                "command_norm": command_norm,
                "actual_norm": actual_norm,
                "projection": projection,
                "cosine": cosine,
                "bad": cosine < args.min_cosine,
            }
        )
        if args.stop_after_first_success and row.get("success") is True:
            first_success_step = row.get("step")
            break

    bad = [row for row in assessed if row["bad"]]
    bad_fraction = (len(bad) / len(assessed)) if assessed else 1.0
    pass_gate = bool(assessed) and bad_fraction <= args.max_bad_fraction
    summary = {
        "trace": str(args.trace_json),
        "steps_total": len(steps),
        "steps_assessed": len(assessed),
        "steps_skipped": skipped,
        "bad_steps": len(bad),
        "bad_fraction": bad_fraction,
        "first_success_step": first_success_step,
        "min_cosine": min((row["cosine"] for row in assessed), default=None),
        "max_cosine": max((row["cosine"] for row in assessed), default=None),
        "pass": pass_gate,
        "stop_after_first_success": args.stop_after_first_success,
        "worst": min(assessed, key=lambda row: row["cosine"], default=None),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    if pass_gate:
        print("[action-response] PASS")
        return 0
    print("[action-response] FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
