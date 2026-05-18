#!/usr/bin/env python3
"""Summarize scripted control-mode comparison results from pulled JSON artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path("artifacts/evaluations/scripted")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _iter_summary_paths(root: Path, since: str | None) -> list[Path]:
    if not root.exists():
        return []
    paths = []
    for path in root.glob("**/seed_*.json"):
        if path.name.endswith("_trace.json"):
            continue
        if since is not None:
            run_id = path.parent.name
            if run_id < since:
                continue
        paths.append(path)
    return sorted(paths)


def _control_label(summary: dict[str, Any]) -> str:
    task = str(summary.get("task") or "")
    mode = str(summary.get("scripted_control_mode") or "")
    if "JointPos" in task:
        return "jointpos+joint-ik"
    if "IK-Rel" in task:
        return "relative-cartesian-ik"
    if "IK-Abs" in task:
        return "absolute-cartesian-ik"
    return mode or "unknown"


def _trace_path(summary_path: Path, summary: dict[str, Any]) -> Path:
    local_candidate = summary_path.with_name(summary_path.stem + "_trace.json")
    if local_candidate.exists():
        return local_candidate
    trace_json = summary.get("trace_json")
    if isinstance(trace_json, str) and trace_json:
        trace_name = Path(trace_json).name
        candidate = summary_path.with_name(trace_name)
        if candidate.exists():
            return candidate
    return local_candidate


def _closest_strict_step(summary_path: Path, summary: dict[str, Any]) -> dict[str, Any] | None:
    trace_path = _trace_path(summary_path, summary)
    if not trace_path.exists():
        return None
    trace = _load_json(trace_path)
    steps = trace.get("steps")
    if not isinstance(steps, list):
        return None
    xy_tol = float(summary.get("active_success_xy_tolerance") or summary.get("success_xy_tolerance") or 0.005)
    z_tol = float(summary.get("active_success_z_tolerance") or summary.get("success_z_tolerance") or 0.045)
    rot_tol = float(summary.get("active_success_rot_tolerance") or summary.get("success_rot_tolerance") or 0.18)
    min_contact = float(summary.get("success_min_contact_force") or 0.0)

    def miss_score(step: dict[str, Any]) -> float:
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

    closest = min((s for s in steps if isinstance(s, dict)), key=miss_score, default=None)
    if closest is None:
        return None
    return {
        "step": closest.get("step"),
        "phase": closest.get("phase"),
        "lateral": closest.get("lateral"),
        "axial": closest.get("axial"),
        "rot": closest.get("rot"),
        "contact": closest.get("contact_force_magnitude"),
        "miss_score": miss_score(closest),
    }


def _fmt_float(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="Optional summary JSON paths. Defaults to scanning artifacts.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Artifact root to scan when no paths are given.")
    parser.add_argument("--since", type=str, default=None, help="Only include run directories with timestamp >= this string.")
    parser.add_argument("--limit", type=int, default=30, help="Maximum rows to print.")
    args = parser.parse_args()

    paths = args.paths or _iter_summary_paths(args.root, args.since)
    rows = []
    for path in paths:
        if not path.exists():
            continue
        summary = _load_json(path)
        if "task" not in summary or "success_step" not in summary:
            continue
        closest = _closest_strict_step(path, summary)
        rows.append((path, summary, closest))

    rows.sort(
        key=lambda item: (
            item[1].get("success_step") is None,
            float("inf") if item[2] is None else item[2]["miss_score"],
            str(item[0]),
        )
    )

    print(
        "| run | control | task | success | closest_step | lateral | axial | rot | contact | miss_score |"
    )
    print("| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for path, summary, closest in rows[: max(0, args.limit)]:
        success = summary.get("success_step")
        if closest is None:
            closest_step = "-"
            lateral = axial = rot = contact = miss_score = "-"
        else:
            closest_step = str(closest.get("step"))
            lateral = _fmt_float(closest.get("lateral"))
            axial = _fmt_float(closest.get("axial"))
            rot = _fmt_float(closest.get("rot"))
            contact = _fmt_float(closest.get("contact"))
            miss_score = _fmt_float(closest.get("miss_score"), digits=6)
        print(
            "| "
            + " | ".join(
                [
                    path.parent.name,
                    _control_label(summary),
                    str(summary.get("task")),
                    "-" if success is None else str(success),
                    closest_step,
                    lateral,
                    axial,
                    rot,
                    contact,
                    miss_score,
                ]
            )
            + " |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
