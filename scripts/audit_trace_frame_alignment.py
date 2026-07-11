#!/usr/bin/env python3
"""Audit scripted traces for frame/time-base mismatches before paid reruns.

The scripted trace stores several controller-side fields before ``env.step`` and
the task outcome metrics after ``env.step``. This tool makes those relationships
explicit and flags traces where socket-frame command offsets were rotated with
the legacy XYZW convention instead of the task's WXYZ socket frame.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable


def _vec3(value: object) -> tuple[float, float, float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError):
        return None


def _quat4(value: object) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    except (TypeError, ValueError):
        return None


def _norm(values: Iterable[float]) -> float:
    return math.sqrt(sum(float(value) * float(value) for value in values))


def _sub(lhs: tuple[float, float, float], rhs: tuple[float, float, float]) -> tuple[float, float, float]:
    return (lhs[0] - rhs[0], lhs[1] - rhs[1], lhs[2] - rhs[2])


def _add(lhs: tuple[float, float, float], rhs: tuple[float, float, float]) -> tuple[float, float, float]:
    return (lhs[0] + rhs[0], lhs[1] + rhs[1], lhs[2] + rhs[2])


def _qmul_wxyz(
    lhs: tuple[float, float, float, float],
    rhs: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    w1, x1, y1, z1 = lhs
    w2, x2, y2, z2 = rhs
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def _qconj_wxyz(q: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return (q[0], -q[1], -q[2], -q[3])


def rotate_wxyz(
    quat: tuple[float, float, float, float],
    vec: tuple[float, float, float],
) -> tuple[float, float, float]:
    rotated = _qmul_wxyz(_qmul_wxyz(quat, (0.0, vec[0], vec[1], vec[2])), _qconj_wxyz(quat))
    return (rotated[1], rotated[2], rotated[3])


def _qmul_xyzw(
    lhs: tuple[float, float, float, float],
    rhs: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x1, y1, z1, w1 = lhs
    x2, y2, z2, w2 = rhs
    return (
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    )


def _qconj_xyzw(q: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return (-q[0], -q[1], -q[2], q[3])


def rotate_legacy_xyzw(
    quat: tuple[float, float, float, float],
    vec: tuple[float, float, float],
) -> tuple[float, float, float]:
    rotated = _qmul_xyzw(_qmul_xyzw(quat, (vec[0], vec[1], vec[2], 0.0)), _qconj_xyzw(quat))
    return (rotated[0], rotated[1], rotated[2])


def audit_trace(trace_path: Path) -> tuple[dict[str, object], list[str]]:
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError(f"trace steps must be a list: {trace_path}")

    same_step_metric_gaps: list[float] = []
    next_step_metric_gaps: list[float] = []
    proxy_tip_gaps: list[float] = []
    post_proxy_tip_gaps: list[float] = []
    offset_rows = 0
    offset_wxyz_closer = 0
    offset_legacy_closer = 0
    offset_wxyz_errors: list[float] = []
    offset_legacy_errors: list[float] = []

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        metric = _vec3(step.get("metric_tip_rel_socket_pos"))
        if metric is not None and isinstance(step.get("lateral"), (int, float)):
            same_step_metric_gaps.append(abs(math.hypot(metric[0], metric[1]) - float(step["lateral"])))
        if idx + 1 < len(steps) and isinstance(step.get("lateral"), (int, float)):
            next_metric = _vec3(steps[idx + 1].get("metric_tip_rel_socket_pos"))
            if next_metric is not None:
                next_step_metric_gaps.append(abs(math.hypot(next_metric[0], next_metric[1]) - float(step["lateral"])))

        socket_pos = _vec3(step.get("socket_pos_w"))
        socket_quat = _quat4(step.get("socket_quat_w"))
        physical_tip_pos = _vec3(step.get("physical_tip_pos_w"))
        if metric is not None and socket_pos is not None and socket_quat is not None and physical_tip_pos is not None:
            metric_tip_world = _add(socket_pos, rotate_wxyz(socket_quat, metric))
            proxy_tip_gaps.append(_norm(_sub(metric_tip_world, physical_tip_pos)))

        post_metric = _vec3(step.get("post_metric_tip_rel_socket_pos"))
        post_socket_pos = _vec3(step.get("post_socket_pos_w"))
        post_socket_quat = _quat4(step.get("post_socket_quat_w"))
        post_physical_tip_pos = _vec3(step.get("post_physical_tip_pos_w"))
        if (
            post_metric is not None
            and post_socket_pos is not None
            and post_socket_quat is not None
            and post_physical_tip_pos is not None
        ):
            post_metric_tip_world = _add(post_socket_pos, rotate_wxyz(post_socket_quat, post_metric))
            post_proxy_tip_gaps.append(_norm(_sub(post_metric_tip_world, post_physical_tip_pos)))

        offset_socket = _vec3(step.get("socket_insertion_servo_offset_socket"))
        offset_w = _vec3(step.get("socket_insertion_servo_offset_w"))
        if (
            bool(step.get("socket_insertion_servo_active"))
            and socket_quat is not None
            and offset_socket is not None
            and offset_w is not None
            and _norm(offset_socket) > 1.0e-9
        ):
            offset_rows += 1
            wxyz_expected = rotate_wxyz(socket_quat, offset_socket)
            legacy_expected = rotate_legacy_xyzw(socket_quat, offset_socket)
            wxyz_error = _norm(_sub(offset_w, wxyz_expected))
            legacy_error = _norm(_sub(offset_w, legacy_expected))
            offset_wxyz_errors.append(wxyz_error)
            offset_legacy_errors.append(legacy_error)
            if wxyz_error <= legacy_error:
                offset_wxyz_closer += 1
            else:
                offset_legacy_closer += 1

    def max_or_none(values: list[float]) -> float | None:
        return max(values) if values else None

    def mean_or_none(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    report: dict[str, object] = {
        "trace": str(trace_path),
        "step_count": len(steps),
        "same_step_metric_lateral_gap_max": max_or_none(same_step_metric_gaps),
        "next_step_metric_lateral_gap_max": max_or_none(next_step_metric_gaps),
        "metric_world_to_physical_proxy_gap_mean": mean_or_none(proxy_tip_gaps),
        "metric_world_to_physical_proxy_gap_max": max_or_none(proxy_tip_gaps),
        "post_metric_world_to_physical_tip_gap_mean": mean_or_none(post_proxy_tip_gaps),
        "post_metric_world_to_physical_tip_gap_max": max_or_none(post_proxy_tip_gaps),
        "socket_offset_rows": offset_rows,
        "socket_offset_wxyz_closer": offset_wxyz_closer,
        "socket_offset_legacy_closer": offset_legacy_closer,
        "socket_offset_wxyz_error_max": max_or_none(offset_wxyz_errors),
        "socket_offset_legacy_error_max": max_or_none(offset_legacy_errors),
    }

    failures: list[str] = []
    if offset_rows and offset_legacy_closer > offset_wxyz_closer:
        failures.append("socket-frame offsets match legacy XYZW rotation more often than task WXYZ rotation")
    proxy_gap_mean = report["metric_world_to_physical_proxy_gap_mean"]
    if isinstance(proxy_gap_mean, float) and proxy_gap_mean > 0.020:
        failures.append("physical-tip proxy is more than 2cm from the task metric tip on average")
    post_proxy_gap_mean = report["post_metric_world_to_physical_tip_gap_mean"]
    if isinstance(post_proxy_gap_mean, float) and post_proxy_gap_mean > 0.020:
        failures.append("post-step physical tip is more than 2cm from the post-step task metric tip on average")
    return report, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="Path to video_trace.json")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text.",
    )
    args = parser.parse_args()

    report, failures = audit_trace(args.trace)
    if args.json:
        print(json.dumps({"report": report, "failures": failures}, indent=2, sort_keys=True))
    else:
        print(f"[trace-frame-audit] trace={report['trace']}")
        for key, value in report.items():
            if key != "trace":
                print(f"  {key}: {value}")
        if failures:
            print("[trace-frame-audit] FAIL")
            for failure in failures:
                print(f"  fail: {failure}")
        else:
            print("[trace-frame-audit] PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
