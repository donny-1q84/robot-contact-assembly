#!/usr/bin/env python3
"""Analyze native Abs IK scripted probe command tracking from trace JSON."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import tarfile
from pathlib import Path
from typing import Any


TRACE_SUFFIX = "_trace.json"
SUMMARY_SUFFIX = ".json"
HANDOFF_SUFFIX = "handoff_selection.json"
DEFAULT_ARM_JOINT_NAMES = [
    "panda_joint1",
    "panda_joint2",
    "panda_joint3",
    "panda_joint4",
    "panda_joint5",
    "panda_joint6",
    "panda_joint7",
]


def _load_json_file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object in {path}")
    return data


def _load_json_member(archive: Path, suffix: str, *, required: bool) -> tuple[dict[str, Any], str | None]:
    with tarfile.open(archive, "r:*") as tf:
        candidates = [member for member in tf.getmembers() if member.isfile() and member.name.endswith(suffix)]
        if suffix == SUMMARY_SUFFIX:
            candidates = [
                member
                for member in candidates
                if member.name.endswith("/seed_42.json") or "/seed_" in member.name and not member.name.endswith(TRACE_SUFFIX)
            ]
        if not candidates:
            if required:
                raise SystemExit(f"could not find *{suffix} in {archive}")
            return {}, None
        member = sorted(candidates, key=lambda item: item.name)[-1]
        file_obj = tf.extractfile(member)
        if file_obj is None:
            if required:
                raise SystemExit(f"could not read {member.name} in {archive}")
            return {}, None
        data = json.load(file_obj)
    if not isinstance(data, dict):
        raise SystemExit(f"expected JSON object in {archive}:{member.name}")
    return data, member.name


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _vec3(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) < 3:
        return None
    parsed = [_float_or_none(item) for item in value[:3]]
    if any(item is None for item in parsed):
        return None
    return [float(item) for item in parsed]


def _float_list(value: Any) -> list[float] | None:
    if not isinstance(value, list):
        return None
    parsed = [_float_or_none(item) for item in value]
    if any(item is None for item in parsed):
        return None
    return [float(item) for item in parsed]


def _sub(lhs: list[float], rhs: list[float]) -> list[float]:
    return [lhs[index] - rhs[index] for index in range(3)]


def _norm(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values))


def _xy_norm(values: list[float]) -> float:
    return math.sqrt(values[0] * values[0] + values[1] * values[1])


def _phase_counts(steps: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        phase = str(step.get("phase") or "unknown")
        counts[phase] = counts.get(phase, 0) + 1
    return dict(sorted(counts.items()))


def _step_number(step: dict[str, Any], fallback: int) -> int:
    parsed = _float_or_none(step.get("step"))
    return fallback if parsed is None else int(parsed)


def _record_for_step(step: dict[str, Any], index: int) -> dict[str, Any] | None:
    target = _vec3(step.get("target_pos_w"))
    command = _vec3(step.get("command_pos_w"))
    action = _vec3(step.get("action_pos_w"))
    post_action = _vec3(step.get("post_action_pos_w"))
    if target is None or command is None or action is None or post_action is None:
        return None
    unbiased_target_action = _vec3(step.get("unbiased_target_action_pos_w"))
    target_action_pos_offset = _vec3(step.get("target_action_pos_offset_w"))

    target_to_action = _sub(target, action)
    target_to_post_action = _sub(target, post_action)
    target_to_command = _sub(target, command)
    command_to_action = _sub(command, action)
    command_to_post_action = _sub(command, post_action)
    post_action_step_delta = _sub(post_action, action)
    unbiased_target_action_to_command = (
        _sub(unbiased_target_action, command) if unbiased_target_action is not None else None
    )
    unbiased_target_action_to_post_action = (
        _sub(unbiased_target_action, post_action) if unbiased_target_action is not None else None
    )
    command_request_xy = command_to_action[:2]
    post_response_xy = post_action_step_delta[:2]
    request_xy_norm_sq = sum(value * value for value in command_request_xy)
    response_ratio_xy = None
    if request_xy_norm_sq > 1.0e-12:
        response_ratio_xy = sum(
            post_response_xy[index] * command_request_xy[index] for index in range(2)
        ) / request_xy_norm_sq

    return {
        "index": index,
        "step": _step_number(step, index),
        "phase": step.get("phase"),
        "lateral": _float_or_none(step.get("lateral")),
        "axial": _float_or_none(step.get("axial")),
        "rot": _float_or_none(step.get("rot")),
        "contact_force_magnitude": _float_or_none(step.get("contact_force_magnitude")),
        "target_pos_w": target,
        "command_pos_w": command,
        "action_pos_w": action,
        "post_action_pos_w": post_action,
        "unbiased_target_action_pos_w": unbiased_target_action,
        "target_action_pos_offset_w": target_action_pos_offset,
        "physical_tip_rel_socket_pos": _vec3(step.get("physical_tip_rel_socket_pos")),
        "post_physical_tip_rel_socket_pos": _vec3(step.get("post_physical_tip_rel_socket_pos")),
        "pre_contact_force_socket": _vec3(step.get("pre_contact_force_socket")),
        "contact_force_socket": _vec3(step.get("contact_force_socket")),
        "target_to_action_w": target_to_action,
        "target_to_post_action_w": target_to_post_action,
        "target_to_command_w": target_to_command,
        "command_to_action_w": command_to_action,
        "command_to_post_action_w": command_to_post_action,
        "post_action_step_delta_w": post_action_step_delta,
        "unbiased_target_action_to_command_w": unbiased_target_action_to_command,
        "unbiased_target_action_to_post_action_w": unbiased_target_action_to_post_action,
        "target_to_action_xy": _xy_norm(target_to_action),
        "target_to_post_action_xy": _xy_norm(target_to_post_action),
        "target_to_command_xy": _xy_norm(target_to_command),
        "command_to_action_xy": _xy_norm(command_to_action),
        "command_to_post_action_xy": _xy_norm(command_to_post_action),
        "post_action_step_delta_xy": _xy_norm(post_action_step_delta),
        "unbiased_target_action_to_command_xy": (
            _xy_norm(unbiased_target_action_to_command) if unbiased_target_action_to_command is not None else None
        ),
        "unbiased_target_action_to_post_action_xy": (
            _xy_norm(unbiased_target_action_to_post_action)
            if unbiased_target_action_to_post_action is not None
            else None
        ),
        "target_action_pos_offset_xy": _xy_norm(target_action_pos_offset) if target_action_pos_offset is not None else None,
        "command_response_ratio_xy": response_ratio_xy,
        "arm_joint_pos": _float_list(step.get("arm_joint_pos")),
        "arm_joint_vel": _float_list(step.get("arm_joint_vel")),
        "arm_joint_limit_margin": _float_list(step.get("arm_joint_limit_margin")),
        "arm_joint_limit_margin_min": _float_or_none(step.get("arm_joint_limit_margin_min")),
        "post_arm_joint_pos": _float_list(step.get("post_arm_joint_pos")),
        "post_arm_joint_vel": _float_list(step.get("post_arm_joint_vel")),
        "post_arm_joint_limit_margin": _float_list(step.get("post_arm_joint_limit_margin")),
        "post_arm_joint_limit_margin_min": _float_or_none(step.get("post_arm_joint_limit_margin_min")),
        "joint_limit_centering_delta": _float_list(step.get("joint_limit_centering_delta")),
        "joint_limit_nullspace_delta": _float_list(step.get("joint_limit_nullspace_delta")),
        "joint_limit_nullspace_delta_norm": _float_or_none(step.get("joint_limit_nullspace_delta_norm")),
        "depth_rotation_polish_active": step.get("depth_rotation_polish_active"),
        "depth_rotation_polish_state": step.get("depth_rotation_polish_state"),
        "depth_rotation_polish_command_valid": step.get("depth_rotation_polish_command_valid"),
        "disable_socket_wall_collisions": step.get("disable_socket_wall_collisions"),
    }


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _mean_metric(records: list[dict[str, Any]], key: str) -> float | None:
    values = [_float_or_none(record.get(key)) for record in records]
    return _mean([value for value in values if value is not None])


def _axis_mean(records: list[dict[str, Any]], key: str) -> list[float] | None:
    vectors = [record.get(key) for record in records if isinstance(record.get(key), list)]
    if not vectors:
        return None
    return [statistics.fmean(vector[index] for vector in vectors) for index in range(3)]


def _axis_abs_mean(records: list[dict[str, Any]], key: str) -> list[float] | None:
    vectors = [record.get(key) for record in records if isinstance(record.get(key), list)]
    if not vectors:
        return None
    return [statistics.fmean(abs(vector[index]) for vector in vectors) for index in range(3)]


def _axis_max_abs(records: list[dict[str, Any]], key: str) -> list[float] | None:
    vectors = [record.get(key) for record in records if isinstance(record.get(key), list)]
    if not vectors:
        return None
    return [max(abs(vector[index]) for vector in vectors) for index in range(3)]


def _tail_summary(records: list[dict[str, Any]], tail_steps: int) -> dict[str, Any]:
    tail = records[-tail_steps:] if tail_steps > 0 else records
    if not tail:
        return {"size": 0}
    return {
        "size": len(tail),
        "start_step": tail[0]["step"],
        "end_step": tail[-1]["step"],
        "phase_counts": _phase_counts(tail),
        "metric_means": {
            "lateral": _mean_metric(tail, "lateral"),
            "axial": _mean_metric(tail, "axial"),
            "rot": _mean_metric(tail, "rot"),
            "contact_force_magnitude": _mean_metric(tail, "contact_force_magnitude"),
            "target_to_action_xy": _mean_metric(tail, "target_to_action_xy"),
            "target_to_post_action_xy": _mean_metric(tail, "target_to_post_action_xy"),
            "target_to_command_xy": _mean_metric(tail, "target_to_command_xy"),
            "command_to_action_xy": _mean_metric(tail, "command_to_action_xy"),
            "command_to_post_action_xy": _mean_metric(tail, "command_to_post_action_xy"),
            "post_action_step_delta_xy": _mean_metric(tail, "post_action_step_delta_xy"),
            "unbiased_target_action_to_command_xy": _mean_metric(tail, "unbiased_target_action_to_command_xy"),
            "unbiased_target_action_to_post_action_xy": _mean_metric(
                tail, "unbiased_target_action_to_post_action_xy"
            ),
            "target_action_pos_offset_xy": _mean_metric(tail, "target_action_pos_offset_xy"),
            "command_response_ratio_xy": _mean_metric(tail, "command_response_ratio_xy"),
            "joint_limit_nullspace_delta_norm": _mean_metric(tail, "joint_limit_nullspace_delta_norm"),
        },
        "delta_means_w": {
            "target_to_action_w": _axis_mean(tail, "target_to_action_w"),
            "target_to_post_action_w": _axis_mean(tail, "target_to_post_action_w"),
            "target_to_command_w": _axis_mean(tail, "target_to_command_w"),
            "command_to_action_w": _axis_mean(tail, "command_to_action_w"),
            "command_to_post_action_w": _axis_mean(tail, "command_to_post_action_w"),
            "post_action_step_delta_w": _axis_mean(tail, "post_action_step_delta_w"),
            "unbiased_target_action_to_command_w": _axis_mean(tail, "unbiased_target_action_to_command_w"),
            "unbiased_target_action_to_post_action_w": _axis_mean(
                tail, "unbiased_target_action_to_post_action_w"
            ),
            "target_action_pos_offset_w": _axis_mean(tail, "target_action_pos_offset_w"),
        },
        "delta_abs_means_w": {
            "target_to_action_w": _axis_abs_mean(tail, "target_to_action_w"),
            "target_to_post_action_w": _axis_abs_mean(tail, "target_to_post_action_w"),
            "target_to_command_w": _axis_abs_mean(tail, "target_to_command_w"),
            "command_to_action_w": _axis_abs_mean(tail, "command_to_action_w"),
            "command_to_post_action_w": _axis_abs_mean(tail, "command_to_post_action_w"),
            "post_action_step_delta_w": _axis_abs_mean(tail, "post_action_step_delta_w"),
            "unbiased_target_action_to_command_w": _axis_abs_mean(tail, "unbiased_target_action_to_command_w"),
            "unbiased_target_action_to_post_action_w": _axis_abs_mean(
                tail, "unbiased_target_action_to_post_action_w"
            ),
            "target_action_pos_offset_w": _axis_abs_mean(tail, "target_action_pos_offset_w"),
        },
        "delta_max_abs_w": {
            "command_to_action_w": _axis_max_abs(tail, "command_to_action_w"),
            "command_to_post_action_w": _axis_max_abs(tail, "command_to_post_action_w"),
        },
        "joint_nullspace_means": {
            "centering_delta": _axis_mean(tail, "joint_limit_centering_delta"),
            "nullspace_delta": _axis_mean(tail, "joint_limit_nullspace_delta"),
        },
        "joint_nullspace_abs_means": {
            "centering_delta": _axis_abs_mean(tail, "joint_limit_centering_delta"),
            "nullspace_delta": _axis_abs_mean(tail, "joint_limit_nullspace_delta"),
        },
        "joint_nullspace_max_abs": {
            "centering_delta": _axis_max_abs(tail, "joint_limit_centering_delta"),
            "nullspace_delta": _axis_max_abs(tail, "joint_limit_nullspace_delta"),
        },
        "socket_frame_means": {
            "physical_tip_rel_socket_pos": _axis_mean(tail, "physical_tip_rel_socket_pos"),
            "post_physical_tip_rel_socket_pos": _axis_mean(tail, "post_physical_tip_rel_socket_pos"),
            "pre_contact_force_socket": _axis_mean(tail, "pre_contact_force_socket"),
            "contact_force_socket": _axis_mean(tail, "contact_force_socket"),
        },
        "socket_frame_abs_means": {
            "physical_tip_rel_socket_pos": _axis_abs_mean(tail, "physical_tip_rel_socket_pos"),
            "post_physical_tip_rel_socket_pos": _axis_abs_mean(tail, "post_physical_tip_rel_socket_pos"),
            "pre_contact_force_socket": _axis_abs_mean(tail, "pre_contact_force_socket"),
            "contact_force_socket": _axis_abs_mean(tail, "contact_force_socket"),
        },
    }


def _best_record(records: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    scored = [(value, record) for record in records if (value := _float_or_none(record.get(key))) is not None]
    if not scored:
        return None
    return min(scored, key=lambda item: item[0])[1]


def _find_record_by_step(records: list[dict[str, Any]], step_number: int | None) -> dict[str, Any] | None:
    if step_number is None:
        return None
    for record in records:
        if record["step"] == step_number:
            return record
    return None


def _compact_record(record: dict[str, Any] | None) -> dict[str, Any] | None:
    if record is None:
        return None
    keys = [
        "index",
        "step",
        "phase",
        "lateral",
        "axial",
        "rot",
        "contact_force_magnitude",
        "target_pos_w",
        "command_pos_w",
        "action_pos_w",
        "post_action_pos_w",
        "unbiased_target_action_pos_w",
        "target_action_pos_offset_w",
        "post_physical_tip_rel_socket_pos",
        "contact_force_socket",
        "target_to_action_w",
        "target_to_post_action_w",
        "target_to_command_w",
        "command_to_action_w",
        "command_to_post_action_w",
        "post_action_step_delta_w",
        "unbiased_target_action_to_command_w",
        "unbiased_target_action_to_post_action_w",
        "target_to_action_xy",
        "target_to_post_action_xy",
        "target_to_command_xy",
        "command_to_action_xy",
        "command_to_post_action_xy",
        "post_action_step_delta_xy",
        "unbiased_target_action_to_command_xy",
        "unbiased_target_action_to_post_action_xy",
        "target_action_pos_offset_xy",
        "command_response_ratio_xy",
        "arm_joint_limit_margin_min",
        "post_arm_joint_limit_margin_min",
        "joint_limit_nullspace_delta_norm",
    ]
    return {key: record.get(key) for key in keys}


def _infer_abs_pos_step(records: list[dict[str, Any]]) -> float | None:
    values = [
        max(abs(value) for value in record["command_to_action_w"])
        for record in records
        if isinstance(record.get("command_to_action_w"), list)
        and (_float_or_none(record.get("target_to_command_xy")) or 0.0) > 1.0e-6
        and max(abs(value) for value in record["command_to_action_w"]) > 1.0e-6
    ]
    if not values:
        return None
    return statistics.median(values)


def _joint_name(joint_names: list[str], index: int) -> str:
    if 0 <= index < len(joint_names):
        return joint_names[index]
    return f"joint_{index}"


def _list_value_at(record: dict[str, Any], key: str, index: int) -> float | None:
    values = record.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return _float_or_none(values[index])


def _joint_limit_sample(
    record: dict[str, Any],
    index: int,
    joint_names: list[str],
    *,
    prefix: str,
) -> dict[str, Any]:
    return {
        "index": index,
        "name": _joint_name(joint_names, index),
        "step": record.get("step"),
        "phase": record.get("phase"),
        "margin": _list_value_at(record, f"{prefix}_limit_margin", index),
        "position": _list_value_at(record, f"{prefix}_pos", index),
        "velocity": _list_value_at(record, f"{prefix}_vel", index),
        "lateral": record.get("lateral"),
        "axial": record.get("axial"),
        "rot": record.get("rot"),
    }


def _joint_limit_summary(
    records: list[dict[str, Any]],
    joint_names: list[str],
    tail_steps: int,
    *,
    prefix: str,
) -> dict[str, Any]:
    margin_key = f"{prefix}_limit_margin"
    pos_key = f"{prefix}_pos"
    vel_key = f"{prefix}_vel"
    usable = [
        record
        for record in records
        if isinstance(record.get(margin_key), list)
        and len(record[margin_key]) > 0
    ]
    if not usable:
        return {"available": False}

    joint_count = max(len(record[margin_key]) for record in usable)
    tail = usable[-tail_steps:] if tail_steps > 0 else usable
    per_joint = []
    global_min_record = None
    global_min_index = None
    global_min_margin = float("inf")

    for index in range(joint_count):
        values = [
            (_list_value_at(record, margin_key, index), record)
            for record in usable
            if _list_value_at(record, margin_key, index) is not None
        ]
        values = [(float(value), record) for value, record in values if value is not None]
        if not values:
            continue
        min_margin, min_record = min(values, key=lambda item: item[0])
        if min_margin < global_min_margin:
            global_min_margin = min_margin
            global_min_record = min_record
            global_min_index = index

        tail_values = [
            value
            for record in tail
            if (value := _list_value_at(record, margin_key, index)) is not None
        ]
        per_joint.append(
            {
                "index": index,
                "name": _joint_name(joint_names, index),
                "min_margin": min_margin,
                "min_margin_step": min_record.get("step"),
                "position_at_min_margin": _list_value_at(min_record, pos_key, index),
                "velocity_at_min_margin": _list_value_at(min_record, vel_key, index),
                "count_at_or_below_zero": sum(1 for value, _ in values if value <= 0.0),
                "count_at_or_below_1e-4": sum(1 for value, _ in values if value <= 1.0e-4),
                "count_at_or_below_1e-3": sum(1 for value, _ in values if value <= 1.0e-3),
                "tail_mean_margin": _mean(tail_values),
                "tail_min_margin": min(tail_values) if tail_values else None,
            }
        )

    tail_limiter_counts: dict[str, int] = {}
    for record in tail:
        margins = record.get(margin_key)
        if not isinstance(margins, list):
            continue
        parsed = [_float_or_none(value) for value in margins]
        scored = [(value, index) for index, value in enumerate(parsed) if value is not None]
        if not scored:
            continue
        _, index = min(scored, key=lambda item: item[0])
        name = _joint_name(joint_names, index)
        tail_limiter_counts[name] = tail_limiter_counts.get(name, 0) + 1

    global_min = (
        _joint_limit_sample(global_min_record, int(global_min_index), joint_names, prefix=prefix)
        if global_min_record is not None and global_min_index is not None
        else None
    )
    return {
        "available": True,
        "sample_count": len(usable),
        "joint_names": joint_names,
        "global_min": global_min,
        "per_joint": per_joint,
        "tail_window": {
            "size": len(tail),
            "start_step": tail[0]["step"] if tail else None,
            "end_step": tail[-1]["step"] if tail else None,
            "limiting_joint_counts": dict(sorted(tail_limiter_counts.items())),
        },
    }


def _diagnosis_hints(
    tail: dict[str, Any],
    joint_limits: dict[str, Any],
    *,
    disable_socket_wall_collisions: bool,
) -> list[str]:
    hints: list[str] = []
    means = tail.get("metric_means") if isinstance(tail.get("metric_means"), dict) else {}
    deltas = tail.get("delta_abs_means_w") if isinstance(tail.get("delta_abs_means_w"), dict) else {}
    command_to_post = deltas.get("command_to_post_action_w") if isinstance(deltas.get("command_to_post_action_w"), list) else None
    target_to_command = deltas.get("target_to_command_w") if isinstance(deltas.get("target_to_command_w"), list) else None
    response_ratio = _float_or_none(means.get("command_response_ratio_xy"))
    if command_to_post is not None and max(command_to_post[:2]) >= 0.02:
        hints.append("tail command-to-post-action XY residual remains above 2 cm")
    if target_to_command is not None and max(target_to_command[:2]) >= 0.02:
        hints.append("tail command target itself remains short of the desired XY target")
    if response_ratio is not None and response_ratio < 0.2:
        hints.append("tail post-action movement makes little progress along the requested XY command")
    contact_force_mean = _float_or_none(means.get("contact_force_magnitude"))
    command_to_post_xy = _float_or_none(means.get("command_to_post_action_xy"))
    target_to_command_xy = _float_or_none(means.get("target_to_command_xy"))
    if (
        not disable_socket_wall_collisions
        and contact_force_mean is not None
        and command_to_post_xy is not None
        and target_to_command_xy is not None
        and contact_force_mean > 0.5
        and command_to_post_xy >= 0.02
        and target_to_command_xy <= 0.005
    ):
        hints.append(
            "contact persists while the commanded target is already at the desired XY; "
            "run the no-wall-collision diagnostic before another controller sweep"
        )
    if (
        disable_socket_wall_collisions
        and contact_force_mean is not None
        and command_to_post_xy is not None
        and target_to_command_xy is not None
        and contact_force_mean > 0.5
        and command_to_post_xy >= 0.02
        and target_to_command_xy <= 0.005
    ):
        hints.append(
            "contact still persists during a no-wall-collision diagnostic; verify wall parking/collision disable "
            "or inspect other contact sources before interpreting contact-force terms"
        )
    global_min = joint_limits.get("global_min") if isinstance(joint_limits.get("global_min"), dict) else None
    global_min_margin = _float_or_none(global_min.get("margin") if global_min else None)
    if global_min and global_min_margin is not None and global_min_margin <= 1.0e-4:
        hints.append(
            "arm joint limit margin reaches <=1e-4; "
            f"limiting_joint={global_min.get('name')} step={global_min.get('step')}"
        )
    return hints


def build_analysis(args: argparse.Namespace) -> dict[str, Any]:
    archive_members: dict[str, str | None] = {}
    if args.archive:
        trace, archive_members["trace_json"] = _load_json_member(args.archive, TRACE_SUFFIX, required=True)
        summary, archive_members["summary_json"] = _load_json_member(args.archive, SUMMARY_SUFFIX, required=False)
        handoff, archive_members["handoff_json"] = _load_json_member(args.archive, HANDOFF_SUFFIX, required=False)
    else:
        trace = _load_json_file(args.trace_json)
        summary = _load_json_file(args.summary_json)
        handoff = _load_json_file(args.handoff_json)

    raw_steps = trace.get("steps")
    steps = [step for step in raw_steps if isinstance(step, dict)] if isinstance(raw_steps, list) else []
    records = [record for index, step in enumerate(steps) if (record := _record_for_step(step, index)) is not None]
    tail = _tail_summary(records, args.tail_steps)
    summary_joint_names = summary.get("arm_joint_names")
    joint_names = (
        [str(name) for name in summary_joint_names]
        if isinstance(summary_joint_names, list) and summary_joint_names
        else DEFAULT_ARM_JOINT_NAMES
    )
    pre_joint_limits = _joint_limit_summary(records, joint_names, args.tail_steps, prefix="arm_joint")
    joint_limits = _joint_limit_summary(records, joint_names, args.tail_steps, prefix="post_arm_joint")
    selected_step = handoff.get("step") if isinstance(handoff, dict) else None
    selected_step_number = int(selected_step) if _float_or_none(selected_step) is not None else None

    disable_socket_wall_collisions = bool(summary.get("disable_socket_wall_collisions"))

    result = {
        "input": {
            "archive": str(args.archive) if args.archive else None,
            "trace_json": str(args.trace_json) if args.trace_json else None,
            "summary_json": str(args.summary_json) if args.summary_json else None,
            "handoff_json": str(args.handoff_json) if args.handoff_json else None,
            "archive_members": archive_members,
        },
        "summary": {
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
            "initial_joint_pos_overrides": summary.get("initial_joint_pos_overrides"),
            "target_action_pos_offset": summary.get("target_action_pos_offset"),
            "rotate_descent_mode": summary.get("rotate_descent_mode"),
            "rotate_descent_step_count": summary.get("rotate_descent_step_count"),
            "rotate_descent_first_step": summary.get("rotate_descent_first_step"),
            "rotate_descent_last_step": summary.get("rotate_descent_last_step"),
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
            "insert_rotation_gate_step_count": summary.get("insert_rotation_gate_step_count"),
            "insert_rotation_gate_first_step": summary.get("insert_rotation_gate_first_step"),
            "insert_rotation_gate_last_step": summary.get("insert_rotation_gate_last_step"),
            "insert_rotation_gate_max_rot": _float_or_none(summary.get("insert_rotation_gate_max_rot")),
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
            "depth_rotation_polish_step_count": summary.get("depth_rotation_polish_step_count"),
            "depth_rotation_polish_first_step": summary.get("depth_rotation_polish_first_step"),
            "depth_rotation_polish_last_step": summary.get("depth_rotation_polish_last_step"),
            "depth_rotation_polish_max_rot": _float_or_none(summary.get("depth_rotation_polish_max_rot")),
            "depth_rotation_polish_max_lateral": _float_or_none(
                summary.get("depth_rotation_polish_max_lateral")
            ),
            "depth_rotation_polish_min_axial": _float_or_none(summary.get("depth_rotation_polish_min_axial")),
            "steps_requested": summary.get("steps_requested"),
            "final_lateral": _float_or_none(summary.get("final_lateral")),
            "final_axial": _float_or_none(summary.get("final_axial")),
            "final_rot": _float_or_none(summary.get("final_rot")),
            "best_lateral": _float_or_none(summary.get("best_lateral")),
            "best_lateral_step": summary.get("best_lateral_step"),
        },
        "trace": {
            "raw_step_count": len(steps),
            "analyzed_step_count": len(records),
            "phase_counts": _phase_counts(steps),
            "inferred_abs_pos_step": _infer_abs_pos_step(records),
        },
        "representative_steps": {
            "first": _compact_record(records[0] if records else None),
            "best_lateral": _compact_record(_best_record(records, "lateral")),
            "selected_handoff": _compact_record(_find_record_by_step(records, selected_step_number)),
            "last": _compact_record(records[-1] if records else None),
        },
        "tail_window": tail,
        "pre_joint_limits": pre_joint_limits,
        "joint_limits": joint_limits,
        "diagnosis_hints": _diagnosis_hints(
            tail,
            joint_limits,
            disable_socket_wall_collisions=disable_socket_wall_collisions,
        ),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--trace-json", type=Path)
    source.add_argument("--archive", type=Path)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--handoff-json", type=Path)
    parser.add_argument("--tail-steps", type=int, default=50)
    args = parser.parse_args()

    print(json.dumps(build_analysis(args), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
