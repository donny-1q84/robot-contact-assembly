#!/usr/bin/env python3
"""Summarize Launchable probe summaries stored in local tar archives."""

from __future__ import annotations

import argparse
import glob
import json
import math
import re
import sys
import tarfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ARCHIVE_GLOB = "artifacts/launchable_logs/*.tar.gz"


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


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get(data: dict[str, Any] | None, *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _round(value: Any, digits: int = 6) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    return round(number, digits)


def _fmt(value: Any, digits: int = 4) -> str:
    number = _as_float(value)
    if number is None:
        return "-"
    return f"{number:.{digits}f}"


def _load_json_member(tar: tarfile.TarFile, member_name: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        extracted = tar.extractfile(member_name)
        if extracted is None:
            return None, "member is not extractable"
        with extracted:
            loaded = json.load(extracted)
    except Exception as exc:  # noqa: BLE001 - report per-archive parsing errors.
        return None, str(exc)
    if not isinstance(loaded, dict):
        return None, "member JSON is not an object"
    return loaded, None


def _probe_summary_members(tar: tarfile.TarFile) -> list[str]:
    members = []
    for member in tar.getmembers():
        if member.isfile() and member.name.endswith("/probe_summary.json"):
            members.append(member.name)
    return sorted(members)


def _sibling(member_name: str, filename: str) -> str:
    return f"{member_name.rsplit('/', 1)[0]}/{filename}"


def _case_label(member_name: str) -> str:
    parts = member_name.split("/")
    parent = parts[-2] if len(parts) >= 2 else member_name
    tags: list[str] = []
    for index, part in enumerate(parts):
        if part.endswith("_matrix"):
            tags.append(part)
            for token in parts[index + 1 :]:
                if token == "evaluations":
                    break
                if re.fullmatch(r"20\d\d-\d\d-\d\dT.*", token):
                    continue
                tags.append(token)
            break
    return " / ".join([*tags, parent]) if tags else parent


def _short_archive_name(path: Path) -> str:
    return path.name.removesuffix(".tar.gz")


def _limiting_joint_counts(tracking: dict[str, Any] | None) -> dict[str, int]:
    counts = _get(tracking, "joint_limits", "tail_window", "limiting_joint_counts")
    if isinstance(counts, dict):
        return {str(key): int(value) for key, value in counts.items() if _as_int(value) is not None}
    return {}


def _top_limiter(counts: dict[str, int]) -> str | None:
    if not counts:
        return None
    joint, count = max(counts.items(), key=lambda item: item[1])
    return f"{joint}:{count}"


def _phase_counts(tracking: dict[str, Any] | None) -> dict[str, int]:
    counts = _get(tracking, "tail_window", "phase_counts")
    if isinstance(counts, dict):
        return {str(key): int(value) for key, value in counts.items() if _as_int(value) is not None}
    return {}


def _diagnosis_hints(tracking: dict[str, Any] | None) -> list[str]:
    hints = _get(tracking, "diagnosis_hints")
    if isinstance(hints, list):
        return [str(hint) for hint in hints]
    return []


def _extract_record(
    archive_path: Path,
    member_name: str,
    summary: dict[str, Any],
    tracking: dict[str, Any] | None,
) -> dict[str, Any]:
    decision = summary.get("decision") if isinstance(summary.get("decision"), dict) else {}
    scripted = summary.get("scripted_summary") if isinstance(summary.get("scripted_summary"), dict) else {}
    selected = summary.get("selected_handoff") if isinstance(summary.get("selected_handoff"), dict) else {}
    tail_metrics = _get(tracking, "tail_window", "metric_means")
    if not isinstance(tail_metrics, dict):
        tail_metrics = {}
    limiting_counts = _limiting_joint_counts(tracking)
    hints = _diagnosis_hints(tracking)

    return {
        "archive": str(archive_path),
        "archive_name": _short_archive_name(archive_path),
        "case": _case_label(member_name),
        "probe_dir": member_name.rsplit("/", 1)[0],
        "status": decision.get("status") or summary.get("status"),
        "reason": decision.get("reason"),
        "task": scripted.get("task"),
        "scripted_control_mode": scripted.get("scripted_control_mode"),
        "abs_control_mode": scripted.get("abs_control_mode"),
        "mdp_abs_action_frame": scripted.get("mdp_abs_action_frame"),
        "mdp_abs_orientation_command_mode": scripted.get("mdp_abs_orientation_command_mode"),
        "mdp_abs_ik_method": scripted.get("mdp_abs_ik_method"),
        "joint_step_limit_mode": scripted.get("joint_step_limit_mode"),
        "joint_limit_nullspace_gain": _round(scripted.get("joint_limit_nullspace_gain")),
        "max_joint_limit_nullspace_delta_norm": _round(
            scripted.get("max_joint_limit_nullspace_delta_norm")
        ),
        "reachable_approach": scripted.get("reachable_approach"),
        "reachable_approach_start_radius": _round(scripted.get("reachable_approach_start_radius")),
        "reachable_approach_final_radius": _round(scripted.get("reachable_approach_final_radius")),
        "reachable_approach_shrink_count": _as_int(scripted.get("reachable_approach_shrink_count")),
        "reachable_approach_margin_block_count": _as_int(
            scripted.get("reachable_approach_margin_block_count")
        ),
        "target_action_pos_offset": scripted.get("target_action_pos_offset"),
        "disable_socket_wall_collisions": scripted.get("disable_socket_wall_collisions"),
        "initial_joint_pos_overrides": scripted.get("initial_joint_pos_overrides"),
        "selected_step": _as_int(selected.get("step")),
        "selected_phase": selected.get("phase"),
        "selected_lateral": _round(selected.get("lateral")),
        "selected_axial": _round(selected.get("axial")),
        "selected_rot": _round(selected.get("rot")),
        "selected_contact_force": _round(selected.get("contact_force_magnitude")),
        "selected_strict_miss_score": _round(selected.get("strict_miss_score")),
        "passes_handoff_guard": selected.get("passes_handoff_guard"),
        "final_lateral": _round(scripted.get("final_lateral")),
        "final_axial": _round(scripted.get("final_axial")),
        "final_rot": _round(scripted.get("final_rot")),
        "final_success_rate": _round(scripted.get("final_success_rate")),
        "success_step": _as_int(scripted.get("success_step")),
        "best_lateral": _round(scripted.get("best_lateral")),
        "best_lateral_step": _as_int(scripted.get("best_lateral_step")),
        "best_axial": _round(scripted.get("best_axial")),
        "best_axial_step": _as_int(scripted.get("best_axial_step")),
        "best_rot": _round(scripted.get("best_rot")),
        "best_rot_step": _as_int(scripted.get("best_rot_step")),
        "min_arm_joint_limit_margin": _round(scripted.get("min_arm_joint_limit_margin")),
        "min_arm_joint_limit_margin_joint_name": scripted.get("min_arm_joint_limit_margin_joint_name"),
        "min_arm_joint_limit_margin_step": _as_int(scripted.get("min_arm_joint_limit_margin_step")),
        "rotate_xy_recovery_step_count": _as_int(scripted.get("rotate_xy_recovery_step_count")),
        "descend_xy_recovery_step_count": _as_int(scripted.get("descend_xy_recovery_step_count")),
        "rotate_descent_step_count": _as_int(scripted.get("rotate_descent_step_count")),
        "insert_rotation_gated_descent": scripted.get("insert_rotation_gated_descent"),
        "insert_descent_rot_tolerance": _round(scripted.get("insert_descent_rot_tolerance")),
        "insert_rotation_gate_descent_scale": _round(
            scripted.get("insert_rotation_gate_descent_scale")
        ),
        "insert_rotation_gate_min_descent_step": _round(
            scripted.get("insert_rotation_gate_min_descent_step")
        ),
        "insert_rotation_gate_near_depth_z_tolerance": _round(
            scripted.get("insert_rotation_gate_near_depth_z_tolerance")
        ),
        "insert_rotation_gate_near_depth_rot_tolerance": _round(
            scripted.get("insert_rotation_gate_near_depth_rot_tolerance")
        ),
        "insert_rotation_gate_near_depth_descent_scale": _round(
            scripted.get("insert_rotation_gate_near_depth_descent_scale")
        ),
        "insert_rotation_gate_near_depth_min_descent_step": _round(
            scripted.get("insert_rotation_gate_near_depth_min_descent_step")
        ),
        "insert_rotation_gate_allowed_descent_max": _round(
            scripted.get("insert_rotation_gate_allowed_descent_max")
        ),
        "insert_rotation_gate_step_count": _as_int(scripted.get("insert_rotation_gate_step_count")),
        "insert_rotation_gate_max_rot": _round(scripted.get("insert_rotation_gate_max_rot")),
        "depth_rotation_polish": scripted.get("depth_rotation_polish"),
        "depth_rotation_polish_xy_tolerance": _round(scripted.get("depth_rotation_polish_xy_tolerance")),
        "depth_rotation_polish_z_tolerance": _round(scripted.get("depth_rotation_polish_z_tolerance")),
        "depth_rotation_polish_contact_min_force": _round(
            scripted.get("depth_rotation_polish_contact_min_force")
        ),
        "depth_rotation_polish_exit_contact_min_force": _round(
            scripted.get("depth_rotation_polish_exit_contact_min_force")
        ),
        "depth_rotation_polish_orientation_mode": scripted.get("depth_rotation_polish_orientation_mode"),
        "depth_rotation_polish_rot_step": _round(scripted.get("depth_rotation_polish_rot_step")),
        "depth_rotation_polish_step_count": _as_int(scripted.get("depth_rotation_polish_step_count")),
        "depth_rotation_polish_max_rot": _round(scripted.get("depth_rotation_polish_max_rot")),
        "depth_rotation_polish_max_lateral": _round(scripted.get("depth_rotation_polish_max_lateral")),
        "depth_rotation_polish_min_axial": _round(scripted.get("depth_rotation_polish_min_axial")),
        "tail_lateral": _round(tail_metrics.get("lateral")),
        "tail_axial": _round(tail_metrics.get("axial")),
        "tail_rot": _round(tail_metrics.get("rot")),
        "tail_contact_force": _round(tail_metrics.get("contact_force_magnitude")),
        "tail_command_to_post_action_xy": _round(tail_metrics.get("command_to_post_action_xy")),
        "tail_target_to_command_xy": _round(tail_metrics.get("target_to_command_xy")),
        "tail_post_action_step_delta_xy": _round(tail_metrics.get("post_action_step_delta_xy")),
        "tail_phase_counts": _phase_counts(tracking),
        "tail_limiting_joint_counts": limiting_counts,
        "tail_top_limiter": _top_limiter(limiting_counts),
        "diagnosis_hints": hints,
    }


def _summarize_records(records: list[dict[str, Any]], warnings: list[dict[str, str]]) -> dict[str, Any]:
    status_counts = Counter(str(record.get("status") or "unknown") for record in records)
    mode_counts = Counter(str(record.get("scripted_control_mode") or "unknown") for record in records)

    def best_by(key: str, reverse: bool = False) -> dict[str, Any] | None:
        candidates = [record for record in records if _as_float(record.get(key)) is not None]
        if not candidates:
            return None
        chosen = sorted(candidates, key=lambda record: float(record[key]), reverse=reverse)[0]
        return {
            "archive_name": chosen.get("archive_name"),
            "case": chosen.get("case"),
            key: chosen.get(key),
            "status": chosen.get("status"),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "probe_count": len(records),
        "status_counts": dict(sorted(status_counts.items())),
        "scripted_control_mode_counts": dict(sorted(mode_counts.items())),
        "best_by_selected_strict_miss": best_by("selected_strict_miss_score"),
        "best_by_final_lateral": best_by("final_lateral"),
        "best_by_tail_command_to_post_action_xy": best_by("tail_command_to_post_action_xy"),
        "warning_count": len(warnings),
        "warnings": warnings,
    }


def _escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _record_markdown_row(record: dict[str, Any]) -> str:
    control_parts = [
        record.get("scripted_control_mode"),
        record.get("abs_control_mode"),
        record.get("mdp_abs_action_frame"),
        record.get("mdp_abs_ik_method"),
    ]
    control = " / ".join(str(part) for part in control_parts if part not in (None, ""))
    selected = (
        f"s{record.get('selected_step')} {record.get('selected_phase')}; "
        f"lat {_fmt(record.get('selected_lateral'))}, ax {_fmt(record.get('selected_axial'))}, "
        f"rot {_fmt(record.get('selected_rot'))}, miss {_fmt(record.get('selected_strict_miss_score'))}"
    )
    success_step = record.get("success_step")
    success = "-" if success_step is None else str(success_step)
    final = (
        f"lat {_fmt(record.get('final_lateral'))}, ax {_fmt(record.get('final_axial'))}, "
        f"rot {_fmt(record.get('final_rot'))}, success {success}"
    )
    if record.get("insert_rotation_gated_descent"):
        final += (
            f", gate {record.get('insert_rotation_gate_step_count')}@"
            f"{_fmt(record.get('insert_rotation_gate_descent_scale'))}"
        )
        if record.get("insert_rotation_gate_near_depth_z_tolerance") is not None:
            final += (
                f"/nearZ{_fmt(record.get('insert_rotation_gate_near_depth_z_tolerance'))}"
                f"/rot{_fmt(record.get('insert_rotation_gate_near_depth_rot_tolerance'))}"
                f"/scale{_fmt(record.get('insert_rotation_gate_near_depth_descent_scale'))}"
            )
    if record.get("depth_rotation_polish"):
        depth_mode = record.get("depth_rotation_polish_orientation_mode") or "target"
        final += (
            f", depth-rot {record.get('depth_rotation_polish_step_count')}@"
            f"xy{_fmt(record.get('depth_rotation_polish_xy_tolerance'))}/"
            f"z{_fmt(record.get('depth_rotation_polish_z_tolerance'))}/"
            f"{depth_mode}"
        )
        if record.get("depth_rotation_polish_exit_contact_min_force") is not None:
            final += f"/exitF{_fmt(record.get('depth_rotation_polish_exit_contact_min_force'))}"
    tail = (
        f"lat {_fmt(record.get('tail_lateral'))}, cmd-post "
        f"{_fmt(record.get('tail_command_to_post_action_xy'))}, step "
        f"{_fmt(record.get('tail_post_action_step_delta_xy'), digits=6)}"
    )
    hints = "; ".join(record.get("diagnosis_hints") or [])
    cells = [
        record.get("archive_name"),
        record.get("case"),
        record.get("status"),
        control or "-",
        selected,
        final,
        tail,
        record.get("tail_top_limiter") or "-",
        hints or "-",
    ]
    return "| " + " | ".join(_escape_md(cell) for cell in cells) + " |"


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    records = payload["records"]
    lines = [
        "# Launchable Probe Archive Summary",
        "",
        f"Generated: `{summary['generated_at']}`",
        f"Archives scanned: `{payload['archives_scanned']}`",
        f"Probe summaries: `{summary['probe_count']}`",
        f"Status counts: `{json.dumps(summary['status_counts'], sort_keys=True)}`",
        "",
    ]
    for key, title in [
        ("best_by_selected_strict_miss", "Best selected strict miss"),
        ("best_by_final_lateral", "Best final lateral"),
        ("best_by_tail_command_to_post_action_xy", "Best tail command residual"),
    ]:
        best = summary.get(key)
        if best:
            metric_key = next(metric for metric in best if metric not in {"archive_name", "case", "status"})
            lines.append(
                f"- {title}: `{best['archive_name']}` / `{best['case']}` "
                f"({metric_key}={best[metric_key]}, status={best['status']})"
            )
    lines.extend(
        [
            "",
            "| Archive | Case | Status | Control | Selected handoff | Final | Tail | Limiter | Hints |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    lines.extend(_record_markdown_row(record) for record in records)
    if summary["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(
            f"- `{warning['archive']}`: {warning['message']}" for warning in summary["warnings"]
        )
    lines.append("")
    return "\n".join(lines)


def collect_archives(args: argparse.Namespace) -> list[Path]:
    paths: list[str] = []
    for pattern in args.glob:
        paths.extend(glob.glob(pattern))
    paths.extend(args.archives)
    if not paths:
        paths.extend(glob.glob(DEFAULT_ARCHIVE_GLOB))
    return sorted({Path(path) for path in paths})


def build_payload(archives: list[Path]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for archive_path in archives:
        if not archive_path.exists():
            warnings.append({"archive": str(archive_path), "message": "archive does not exist"})
            continue
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                probe_members = _probe_summary_members(tar)
                if not probe_members:
                    continue
                names = set(tar.getnames())
                for probe_member in probe_members:
                    summary, error = _load_json_member(tar, probe_member)
                    if error is not None or summary is None:
                        warnings.append(
                            {
                                "archive": str(archive_path),
                                "message": f"{probe_member}: {error}",
                            }
                        )
                        continue
                    tracking_member = _sibling(probe_member, "tracking_analysis.json")
                    tracking = None
                    if tracking_member in names:
                        tracking, tracking_error = _load_json_member(tar, tracking_member)
                        if tracking_error is not None:
                            warnings.append(
                                {
                                    "archive": str(archive_path),
                                    "message": f"{tracking_member}: {tracking_error}",
                                }
                            )
                    records.append(_extract_record(archive_path, probe_member, summary, tracking))
        except tarfile.TarError as exc:
            warnings.append({"archive": str(archive_path), "message": str(exc)})

    records.sort(
        key=lambda record: (
            str(record.get("archive_name") or ""),
            str(record.get("case") or ""),
            str(record.get("probe_dir") or ""),
        )
    )
    return {
        "archives_scanned": len(archives),
        "archive_globs": [DEFAULT_ARCHIVE_GLOB],
        "summary": _summarize_records(records, warnings),
        "records": records,
    }


def write_text(path: str | None, text: str) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize local Launchable probe_summary.json files inside tar.gz archives."
    )
    parser.add_argument("archives", nargs="*", help="Archive paths to scan.")
    parser.add_argument(
        "--glob",
        action="append",
        default=[],
        help=f"Archive glob to scan. Defaults to {DEFAULT_ARCHIVE_GLOB!r} when no input is provided.",
    )
    parser.add_argument("--output-json", help="Write the JSON summary to this path.")
    parser.add_argument("--output-markdown", help="Write a Markdown summary table to this path.")
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Stdout format.",
    )
    args = parser.parse_args()

    archives = collect_archives(args)
    payload = build_payload(archives)
    json_text = json.dumps(payload, indent=2, sort_keys=True)
    markdown_text = render_markdown(payload)
    write_text(args.output_json, json_text + "\n")
    write_text(args.output_markdown, markdown_text)
    if args.format == "markdown":
        print(markdown_text)
    else:
        print(json_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
