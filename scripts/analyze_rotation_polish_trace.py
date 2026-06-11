#!/usr/bin/env python3
"""Analyze Launchable rotation-polish traces stored in local tar archives."""

from __future__ import annotations

import argparse
import json
import math
import tarfile
from pathlib import Path
from typing import Any


DEFAULT_LIMIT = 12


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _fmt(value: Any, digits: int = 4) -> str:
    number = _as_float(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}"


def _fmt_step(value: Any) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return "-"


def _normalize_quat(quat: Any) -> list[float] | None:
    if not isinstance(quat, list) or len(quat) != 4:
        return None
    values = [_as_float(item) for item in quat]
    if any(item is None for item in values):
        return None
    typed = [float(item) for item in values if item is not None]
    norm = math.sqrt(sum(item * item for item in typed))
    if norm <= 0.0:
        return None
    return [item / norm for item in typed]


def _quat_distance(lhs: Any, rhs: Any) -> float | None:
    lhs_q = _normalize_quat(lhs)
    rhs_q = _normalize_quat(rhs)
    if lhs_q is None or rhs_q is None:
        return None
    dot = abs(sum(left * right for left, right in zip(lhs_q, rhs_q)))
    return 2.0 * math.acos(max(-1.0, min(1.0, dot)))


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _load_json_member(tar: tarfile.TarFile, member_name: str) -> dict[str, Any]:
    extracted = tar.extractfile(member_name)
    if extracted is None:
        raise ValueError(f"member is not extractable: {member_name}")
    with extracted:
        loaded = json.load(extracted)
    if not isinstance(loaded, dict):
        raise ValueError(f"member JSON is not an object: {member_name}")
    return loaded


def _trace_members(tar: tarfile.TarFile) -> list[str]:
    members = []
    for member in tar.getmembers():
        if member.isfile() and member.name.endswith("_trace.json"):
            members.append(member.name)
    return sorted(members)


def _phase_segments(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not steps:
        return []
    segments = []
    start_index = 0
    current_phase = steps[0].get("phase")
    for index, step in enumerate(steps[1:], start=1):
        if step.get("phase") != current_phase:
            segment_steps = steps[start_index:index]
            segments.append(_segment_record(segment_steps, str(current_phase)))
            start_index = index
            current_phase = step.get("phase")
    segments.append(_segment_record(steps[start_index:], str(current_phase)))
    return segments


def _segment_record(segment_steps: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    first = segment_steps[0]
    last = segment_steps[-1]
    rots = [_as_float(step.get("rot")) for step in segment_steps]
    rots = [rot for rot in rots if rot is not None]
    contacts = [_as_float(step.get("contact_force_magnitude")) for step in segment_steps]
    contacts = [contact for contact in contacts if contact is not None]
    return {
        "start_step": first.get("step"),
        "end_step": last.get("step"),
        "phase": phase,
        "count": len(segment_steps),
        "start_rot": _as_float(first.get("rot")),
        "end_rot": _as_float(last.get("rot")),
        "min_rot": min(rots) if rots else None,
        "max_rot": max(rots) if rots else None,
        "start_axial": _as_float(first.get("axial")),
        "end_axial": _as_float(last.get("axial")),
        "start_lateral": _as_float(first.get("lateral")),
        "end_lateral": _as_float(last.get("lateral")),
        "start_contact": _as_float(first.get("contact_force_magnitude")),
        "end_contact": _as_float(last.get("contact_force_magnitude")),
        "mean_contact": _mean(contacts),
        "start_command_to_final_rot": _quat_distance(first.get("command_quat_w"), first.get("target_action_quat_w")),
        "end_command_to_final_rot": _quat_distance(last.get("command_quat_w"), last.get("target_action_quat_w")),
        "start_post_to_command_rot": _quat_distance(first.get("post_action_quat_w"), first.get("command_quat_w")),
        "end_post_to_command_rot": _quat_distance(last.get("post_action_quat_w"), last.get("command_quat_w")),
    }


def _ready_ranges(steps: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    ready = [step for step in steps if bool(step.get(key))]
    if not ready:
        return []
    ranges = []
    start = ready[0]
    previous = ready[0]
    for step in ready[1:]:
        if step.get("step") != previous.get("step", -10) + 1:
            ranges.append(_range_record(start, previous))
            start = step
        previous = step
    ranges.append(_range_record(start, previous))
    return ranges


def _range_record(start: dict[str, Any], end: dict[str, Any]) -> dict[str, Any]:
    return {
        "start_step": start.get("step"),
        "end_step": end.get("step"),
        "start_phase": start.get("phase"),
        "end_phase": end.get("phase"),
        "start_rot": _as_float(start.get("rot")),
        "end_rot": _as_float(end.get("rot")),
        "start_axial": _as_float(start.get("axial")),
        "end_axial": _as_float(end.get("axial")),
        "start_lateral": _as_float(start.get("lateral")),
        "end_lateral": _as_float(end.get("lateral")),
        "start_contact": _as_float(start.get("contact_force_magnitude")),
        "end_contact": _as_float(end.get("contact_force_magnitude")),
    }


def _ready_except_rot(steps: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    candidates = [
        step
        for step in steps
        if step.get("success_xy_ready")
        and step.get("success_axial_ready")
        and step.get("success_contact_ready")
    ]
    candidates.sort(key=lambda item: (_as_float(item.get("rot")) is None, _as_float(item.get("rot")) or 0.0))
    return [
        {
            "step": step.get("step"),
            "phase": step.get("phase"),
            "rot": _as_float(step.get("rot")),
            "lateral": _as_float(step.get("lateral")),
            "axial": _as_float(step.get("axial")),
            "contact": _as_float(step.get("contact_force_magnitude")),
            "depth_rotation_polish_active": bool(step.get("depth_rotation_polish_active")),
            "depth_rotation_polish_command_valid": bool(step.get("depth_rotation_polish_command_valid")),
            "command_to_final_rot": _quat_distance(step.get("command_quat_w"), step.get("target_action_quat_w")),
            "post_to_command_rot": _quat_distance(step.get("post_action_quat_w"), step.get("command_quat_w")),
        }
        for step in candidates[:limit]
    ]


def _summary_for_trace(trace: dict[str, Any], member_name: str, limit: int) -> dict[str, Any]:
    steps = trace.get("steps")
    if not isinstance(steps, list):
        raise ValueError(f"trace has no steps array: {member_name}")
    typed_steps = [step for step in steps if isinstance(step, dict)]
    segments = _phase_segments(typed_steps)
    depth_segments = [segment for segment in segments if segment.get("phase") == "depth-rot-polish"]
    rot_ready = _ready_ranges(typed_steps, "success_rot_ready")
    strict_ready = _ready_ranges(typed_steps, "success")
    ready_except_rot = _ready_except_rot(typed_steps, limit)
    summary = trace.get("summary") if isinstance(trace.get("summary"), dict) else {}
    depth_lengths = [int(segment["count"]) for segment in depth_segments if segment.get("count") is not None]
    worsening_depth = [
        segment
        for segment in depth_segments
        if _as_float(segment.get("end_rot")) is not None
        and _as_float(segment.get("start_rot")) is not None
        and float(segment["end_rot"]) > float(segment["start_rot"])
    ]
    return {
        "member": member_name,
        "steps": len(typed_steps),
        "phase_segment_count": len(segments),
        "depth_rotation_polish_segment_count": len(depth_segments),
        "depth_rotation_polish_step_count": summary.get("depth_rotation_polish_step_count"),
        "depth_rotation_polish_max_segment_len": max(depth_lengths) if depth_lengths else 0,
        "depth_rotation_polish_mean_segment_len": _mean([float(item) for item in depth_lengths]),
        "depth_rotation_polish_worsening_segment_count": len(worsening_depth),
        "rot_ready_count": sum(
            int((item.get("end_step") or 0) - (item.get("start_step") or 0) + 1) for item in rot_ready
        ),
        "rot_ready_ranges": rot_ready,
        "strict_ready_ranges": strict_ready,
        "ready_except_rot_best": ready_except_rot,
        "depth_rotation_polish_segments": depth_segments[:limit],
        "tail_depth_rotation_polish_segments": depth_segments[-limit:],
        "phase_segments_head": segments[:limit],
        "phase_segments_tail": segments[-limit:],
    }


def _markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_none_\n"
    lines = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = []
        for _, key in columns:
            value = row.get(key)
            if isinstance(value, float):
                values.append(_fmt(value))
            elif isinstance(value, bool):
                values.append("yes" if value else "no")
            else:
                values.append(str(value) if value is not None else "-")
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def _emit_markdown(results: list[dict[str, Any]]) -> str:
    lines = ["# Rotation Polish Trace Analysis", ""]
    for result in results:
        lines.extend(
            [
                f"## {result['member']}",
                "",
                f"- steps: `{result['steps']}`",
                f"- phase segments: `{result['phase_segment_count']}`",
                f"- depth-rot-polish segments: `{result['depth_rotation_polish_segment_count']}` "
                f"(steps={result['depth_rotation_polish_step_count']}, "
                f"max_len={result['depth_rotation_polish_max_segment_len']}, "
                f"mean_len={_fmt(result['depth_rotation_polish_mean_segment_len'])}, "
                f"worsening={result['depth_rotation_polish_worsening_segment_count']})",
                f"- rot-ready steps: `{result['rot_ready_count']}`",
                "",
                "### Rot-Ready Ranges",
                "",
                _markdown_table(
                    result["rot_ready_ranges"],
                    [
                        ("Start", "start_step"),
                        ("End", "end_step"),
                        ("Phase", "start_phase"),
                        ("End Phase", "end_phase"),
                        ("Rot", "start_rot"),
                        ("End Rot", "end_rot"),
                        ("Axial", "start_axial"),
                        ("Contact", "start_contact"),
                    ],
                ),
                "### Best XY/Z/Contact-Ready Steps By Rotation",
                "",
                _markdown_table(
                    result["ready_except_rot_best"],
                    [
                        ("Step", "step"),
                        ("Phase", "phase"),
                        ("Rot", "rot"),
                        ("Lat", "lateral"),
                        ("Ax", "axial"),
                        ("Contact", "contact"),
                        ("Polish", "depth_rotation_polish_active"),
                        ("Cmd-Final", "command_to_final_rot"),
                        ("Post-Cmd", "post_to_command_rot"),
                    ],
                ),
                "### Tail Depth-Polish Segments",
                "",
                _markdown_table(
                    result["tail_depth_rotation_polish_segments"],
                    [
                        ("Start", "start_step"),
                        ("End", "end_step"),
                        ("N", "count"),
                        ("Rot", "start_rot"),
                        ("End Rot", "end_rot"),
                        ("Ax", "start_axial"),
                        ("End Ax", "end_axial"),
                        ("Contact", "start_contact"),
                        ("End Contact", "end_contact"),
                        ("Cmd-Final", "start_command_to_final_rot"),
                        ("End Cmd-Final", "end_command_to_final_rot"),
                    ],
                ),
            ]
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path, help="Launchable result tarball(s).")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Rows per section.")
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for archive in args.archives:
        with tarfile.open(archive, "r:gz") as tar:
            for member in _trace_members(tar):
                trace = _load_json_member(tar, member)
                result = _summary_for_trace(trace, member, max(1, args.limit))
                result["archive"] = str(archive)
                results.append(result)

    if args.format == "json":
        print(json.dumps({"results": results}, indent=2, sort_keys=True))
    else:
        print(_emit_markdown(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
