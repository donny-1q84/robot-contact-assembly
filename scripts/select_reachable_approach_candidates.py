#!/usr/bin/env python3
"""Find local trace states that are plausible reachable-approach waypoints."""

from __future__ import annotations

import argparse
import glob
import json
import math
import tarfile
from pathlib import Path
from typing import Any


DEFAULT_ARCHIVE_GLOB = "artifacts/launchable_logs/*.tar.gz"


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _vec_xy_distance(lhs: Any, rhs: Any) -> float | None:
    if not isinstance(lhs, list) or not isinstance(rhs, list) or len(lhs) < 2 or len(rhs) < 2:
        return None
    lx = _as_float(lhs[0])
    ly = _as_float(lhs[1])
    rx = _as_float(rhs[0])
    ry = _as_float(rhs[1])
    if None in (lx, ly, rx, ry):
        return None
    return math.hypot(float(lx) - float(rx), float(ly) - float(ry))


def _min_float_list_index(values: Any) -> int | None:
    if not isinstance(values, list) or not values:
        return None
    parsed = [_as_float(value) for value in values]
    candidates = [(index, value) for index, value in enumerate(parsed) if value is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[1])[0]


def _load_json_from_tar(tar: tarfile.TarFile, member_name: str) -> Any:
    extracted = tar.extractfile(member_name)
    if extracted is None:
        return None
    with extracted:
        return json.load(extracted)


def _steps_from_trace(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("steps"), list):
        return [step for step in payload["steps"] if isinstance(step, dict)]
    if isinstance(payload, list):
        return [step for step in payload if isinstance(step, dict)]
    return []


def _case_label(member_name: str) -> str:
    parent = member_name.rsplit("/", 1)[0]
    return parent.split("/")[-1]


def _score(row: dict[str, Any], args: argparse.Namespace) -> float:
    lateral = row["lateral"]
    axial = row["axial"]
    rot = row["rot"]
    margin = row["margin"]
    target_residual = row["target_to_post_action_xy"]
    margin_penalty = max(0.0, args.preferred_margin - margin) * args.margin_weight
    residual_penalty = 0.0 if target_residual is None else target_residual * args.residual_weight
    return lateral * args.lateral_weight + axial * args.axial_weight + rot * args.rot_weight + margin_penalty + residual_penalty


def _candidate_from_step(
    archive: Path,
    member_name: str,
    step: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    lateral = _as_float(step.get("lateral"))
    axial = _as_float(step.get("axial"))
    rot = _as_float(step.get("rot"))
    margin = _as_float(step.get("post_arm_joint_limit_margin_min"))
    if margin is None:
        margin = _as_float(step.get("arm_joint_limit_margin_min"))
    if lateral is None or axial is None or rot is None or margin is None:
        return None
    if lateral > args.max_lateral or axial > args.max_axial or rot > args.max_rot or margin < args.min_margin:
        return None

    target_pos = step.get("target_action_pos_w") or step.get("unbiased_target_action_pos_w")
    post_action_pos = step.get("post_action_pos_w") or step.get("action_pos_w")
    action_pos = step.get("action_pos_w")
    target_to_post_action_xy = _vec_xy_distance(target_pos, post_action_pos)
    target_to_action_xy = _vec_xy_distance(target_pos, action_pos)
    limiting_joint_index = _min_float_list_index(
        step.get("post_arm_joint_limit_margin") or step.get("arm_joint_limit_margin")
    )
    limiting_joint = step.get("min_arm_joint_limit_margin_joint_name")
    if limiting_joint is None and limiting_joint_index is not None:
        limiting_joint = f"panda_joint{limiting_joint_index + 1}"
    row = {
        "archive": str(archive),
        "archive_name": archive.name.removesuffix(".tar.gz"),
        "trace": member_name,
        "case": _case_label(member_name),
        "step": step.get("step"),
        "phase": step.get("phase"),
        "lateral": lateral,
        "axial": axial,
        "rot": rot,
        "margin": margin,
        "target_to_action_xy": target_to_action_xy,
        "target_to_post_action_xy": target_to_post_action_xy,
        "limiting_joint": limiting_joint,
        "limiting_joint_index": limiting_joint_index,
        "action_pos_w": action_pos,
        "target_action_pos_w": target_pos,
        "post_action_pos_w": post_action_pos,
    }
    row["score"] = _score(row, args)
    return row


def collect_candidates(archives: list[Path], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []
    for archive in archives:
        try:
            with tarfile.open(archive, "r:gz") as tar:
                trace_members = sorted(
                    member.name
                    for member in tar.getmembers()
                    if member.isfile() and member.name.endswith("_trace.json")
                )
                for member_name in trace_members:
                    try:
                        trace_payload = _load_json_from_tar(tar, member_name)
                    except Exception as exc:  # noqa: BLE001 - keep scanning other traces.
                        warnings.append(f"{archive}:{member_name}: {exc}")
                        continue
                    for step in _steps_from_trace(trace_payload):
                        row = _candidate_from_step(archive, member_name, step, args)
                        if row is not None:
                            candidates.append(row)
        except tarfile.TarError as exc:
            warnings.append(f"{archive}: {exc}")
    candidates.sort(key=lambda row: row["score"])
    return candidates[: args.top], warnings


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Reachable Approach Candidates",
        "",
        f"Archives scanned: `{payload['archives_scanned']}`",
        f"Candidates returned: `{len(payload['candidates'])}`",
        "",
        "| Archive | Case | Step | Phase | Lateral | Axial | Rot | Margin | Limiter | Target XY residual | Score |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for row in payload["candidates"]:
        residual = row["target_to_post_action_xy"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["archive_name"]),
                    str(row["case"]),
                    str(row["step"]),
                    str(row["phase"]),
                    f"{row['lateral']:.4f}",
                    f"{row['axial']:.4f}",
                    f"{row['rot']:.4f}",
                    f"{row['margin']:.4f}",
                    str(row["limiting_joint"] or "-"),
                    "-" if residual is None else f"{residual:.4f}",
                    f"{row['score']:.4f}",
                ]
            )
            + " |"
        )
    if payload["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="*", help="Archive paths to scan.")
    parser.add_argument("--glob", action="append", default=[], help="Archive glob to scan.")
    parser.add_argument("--top", type=int, default=30, help="Maximum candidates to return.")
    parser.add_argument("--max-lateral", type=float, default=0.12)
    parser.add_argument("--max-axial", type=float, default=0.09)
    parser.add_argument("--max-rot", type=float, default=1.10)
    parser.add_argument("--min-margin", type=float, default=0.02)
    parser.add_argument("--preferred-margin", type=float, default=0.08)
    parser.add_argument("--lateral-weight", type=float, default=10.0)
    parser.add_argument("--axial-weight", type=float, default=2.0)
    parser.add_argument("--rot-weight", type=float, default=0.5)
    parser.add_argument("--margin-weight", type=float, default=2.0)
    parser.add_argument("--residual-weight", type=float, default=2.0)
    parser.add_argument("--output-json", help="Write full JSON payload to this path.")
    parser.add_argument("--output-markdown", help="Write Markdown table to this path.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    paths: list[str] = []
    for pattern in args.glob:
        paths.extend(glob.glob(pattern))
    paths.extend(args.archives)
    if not paths:
        paths.extend(glob.glob(DEFAULT_ARCHIVE_GLOB))
    archives = sorted({Path(path) for path in paths})
    candidates, warnings = collect_candidates(archives, args)
    payload = {
        "archives_scanned": len(archives),
        "thresholds": {
            "max_lateral": args.max_lateral,
            "max_axial": args.max_axial,
            "max_rot": args.max_rot,
            "min_margin": args.min_margin,
            "preferred_margin": args.preferred_margin,
        },
        "warnings": warnings,
        "candidates": candidates,
    }
    json_text = json.dumps(payload, indent=2, sort_keys=True)
    markdown_text = render_markdown(payload)
    if args.output_json:
        output = Path(args.output_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json_text + "\n", encoding="utf-8")
    if args.output_markdown:
        output = Path(args.output_markdown)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown_text, encoding="utf-8")
    print(markdown_text if args.format == "markdown" else json_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
