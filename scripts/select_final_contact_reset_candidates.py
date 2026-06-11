#!/usr/bin/env python3
"""Select final-contact reset/handoff candidates from scripted traces.

The output is a local-only planning artifact for the next learned-policy or
reset-based final-contact formulation. It should not be treated as a success
demonstration set unless target_gate_success candidates are present.
"""

from __future__ import annotations

import argparse
import glob
import json
import tarfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path("artifacts/evaluations/scripted")
DEFAULT_OUTPUT_JSON = Path("artifacts/reports/final_contact_reset_candidates_2026-06-09.json")
DEFAULT_OUTPUT_MD = Path("artifacts/reports/final_contact_reset_candidates_2026-06-09.md")


@dataclass(frozen=True)
class GateCfg:
    xy_tol: float
    z_tol: float
    rot_tol: float
    min_contact: float
    near_xy_tol: float
    near_z_tol: float
    near_rot_tol: float
    near_min_contact: float
    strict_miss_max: float


@dataclass(frozen=True)
class Candidate:
    category: str
    tags: list[str]
    run_id: str
    trace: str
    task: str
    scripted_control_mode: str
    socket_pos: list[float] | None
    step: int
    phase: str
    lateral: float
    axial: float
    rot: float
    contact: float
    strict_miss_score: float
    label_use: str
    reset_use: str


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _socket_pos(summary: dict[str, Any]) -> list[float] | None:
    value = summary.get("socket_pos_override")
    if not isinstance(value, list) or len(value) != 3:
        return None
    return [_float(item) for item in value]


def _strict_miss(lateral: float, axial: float, rot: float, contact: float, cfg: GateCfg) -> float:
    return (
        max(0.0, lateral - cfg.xy_tol) * 100.0
        + max(0.0, axial - cfg.z_tol) * 100.0
        + max(0.0, rot - cfg.rot_tol) * 10.0
        + max(0.0, cfg.min_contact - contact)
    )


def _trace_paths(root: Path, since: str | None, explicit: list[Path]) -> list[Path]:
    if explicit:
        paths: list[Path] = []
        for path in explicit:
            if path.is_dir():
                paths.extend(sorted(path.glob("**/seed_*_trace.json")))
            else:
                paths.append(path)
        return sorted(paths)
    paths = sorted(root.glob("*/seed_*_trace.json"))
    if since is not None:
        paths = [path for path in paths if path.parent.name >= since]
    return paths


def _load_trace_file(path: Path) -> tuple[str, str, dict[str, Any]]:
    return str(path), path.parent.name, json.loads(path.read_text(encoding="utf-8"))


def _load_archive_traces(archive: Path, since: str | None) -> list[tuple[str, str, dict[str, Any]]]:
    traces: list[tuple[str, str, dict[str, Any]]] = []
    with tarfile.open(archive, "r:*") as tar:
        members = [
            member
            for member in tar.getmembers()
            if member.isfile() and member.name.endswith("_trace.json")
        ]
        for member in sorted(members, key=lambda item: item.name):
            run_id = Path(member.name).parent.name
            if since is not None and run_id < since:
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            with extracted:
                data = json.load(extracted)
            if isinstance(data, dict):
                traces.append((f"{archive}::{member.name}", run_id, data))
    return traces


def _tags_for_step(step: dict[str, Any], cfg: GateCfg) -> tuple[list[str], float]:
    lateral = _float(step.get("lateral"))
    axial = _float(step.get("axial"))
    rot = _float(step.get("rot"))
    contact = _float(step.get("contact_force_magnitude"))
    miss = _strict_miss(lateral, axial, rot, contact, cfg)
    xy_ready = lateral < cfg.xy_tol
    z_ready = axial < cfg.z_tol
    rot_ready = rot < cfg.rot_tol
    contact_ready = contact >= cfg.min_contact
    near_xy = lateral < cfg.near_xy_tol
    near_z = axial < cfg.near_z_tol
    near_rot = rot < cfg.near_rot_tol
    near_contact = contact >= cfg.near_min_contact

    tags: list[str] = []
    if xy_ready and z_ready and rot_ready and contact_ready:
        tags.append("target_gate_success")
    if miss <= cfg.strict_miss_max:
        tags.append("strict_near_miss")
    if xy_ready and z_ready and contact_ready and not rot_ready:
        tags.append("rotation_only_miss")
    if xy_ready and near_z and contact_ready and not rot_ready:
        tags.append("depth_contact_rotation_conflict")
    if near_xy and near_z and near_rot and near_contact:
        tags.append("near_contact")
    if xy_ready and near_z and near_rot and not contact_ready:
        tags.append("low_rot_no_contact")
    return tags, miss


def _primary_category(tags: list[str]) -> str:
    priority = [
        "target_gate_success",
        "strict_near_miss",
        "rotation_only_miss",
        "depth_contact_rotation_conflict",
        "near_contact",
        "low_rot_no_contact",
    ]
    for tag in priority:
        if tag in tags:
            return tag
    return "uncategorized"


def _label_use(category: str) -> str:
    if category == "target_gate_success":
        return "strict-success-demonstration"
    if category in {"strict_near_miss", "rotation_only_miss"}:
        return "near-success-reset-not-success-label"
    return "diagnostic-reset-not-success-label"


def _reset_use(category: str) -> str:
    if category == "target_gate_success":
        return "positive-final-contact-seed"
    if category == "strict_near_miss":
        return "best-final-contact-reset-seed"
    if category == "rotation_only_miss":
        return "orientation-stabilization-reset-seed"
    if category == "depth_contact_rotation_conflict":
        return "depth-contact-axis-alignment-reset-seed"
    if category == "near_contact":
        return "near-contact-stabilization-reset-seed"
    if category == "low_rot_no_contact":
        return "contact-reacquisition-diagnostic-seed"
    return "diagnostic"


def _candidate_sort_key(candidate: Candidate) -> tuple[float, float, float, float]:
    return (
        candidate.strict_miss_score,
        candidate.axial,
        candidate.rot,
        -candidate.contact,
    )


def _select_candidates(
    trace_id: str,
    run_id: str,
    data: dict[str, Any],
    cfg: GateCfg,
    *,
    per_trace_limit: int,
    min_step_spacing: int,
) -> list[Candidate]:
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    task = str(summary.get("task") or "")
    mode = str(summary.get("scripted_control_mode") or "")
    socket_pos = _socket_pos(summary)
    raw_candidates: list[Candidate] = []
    for index, step in enumerate(data.get("steps") or []):
        if not isinstance(step, dict):
            continue
        tags, miss = _tags_for_step(step, cfg)
        if not tags:
            continue
        category = _primary_category(tags)
        raw_step = step.get("step")
        step_index = int(raw_step if raw_step is not None else index)
        raw_candidates.append(
            Candidate(
                category=category,
                tags=tags,
                run_id=run_id,
                trace=trace_id,
                task=task,
                scripted_control_mode=mode,
                socket_pos=socket_pos,
                step=step_index,
                phase=str(step.get("phase") or ""),
                lateral=_float(step.get("lateral")),
                axial=_float(step.get("axial")),
                rot=_float(step.get("rot")),
                contact=_float(step.get("contact_force_magnitude")),
                strict_miss_score=miss,
                label_use=_label_use(category),
                reset_use=_reset_use(category),
            )
        )

    selected: list[Candidate] = []
    selected_steps: list[int] = []
    for candidate in sorted(raw_candidates, key=_candidate_sort_key):
        if any(abs(candidate.step - step) < min_step_spacing for step in selected_steps):
            continue
        selected.append(candidate)
        selected_steps.append(candidate.step)
        if per_trace_limit > 0 and len(selected) >= per_trace_limit:
            break
    return selected


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, list):
        return ",".join(f"{_float(item):.3f}" for item in value)
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def _render_markdown(candidates: list[Candidate], cfg: GateCfg, limit: int) -> str:
    counts = Counter(candidate.category for candidate in candidates)
    tag_counts = Counter(tag for candidate in candidates for tag in candidate.tags)
    sorted_candidates = sorted(candidates, key=_candidate_sort_key)
    lines = [
        "# Final-Contact Reset Candidate Selection",
        "",
        "## Gate",
        "",
        "```text",
        f"target gate: xy < {cfg.xy_tol:.4f} m, z < {cfg.z_tol:.4f} m, rot < {cfg.rot_tol:.4f} rad, contact >= {cfg.min_contact:.3f}",
        f"near gate:   xy < {cfg.near_xy_tol:.4f} m, z < {cfg.near_z_tol:.4f} m, rot < {cfg.near_rot_tol:.4f} rad, contact >= {cfg.near_min_contact:.3f}",
        f"strict near miss threshold: {cfg.strict_miss_max:.4f}",
        "```",
        "",
        "## Aggregate",
        "",
        "```text",
        f"candidates: {len(candidates)}",
        f"categories: {dict(sorted(counts.items()))}",
        f"tags: {dict(sorted(tag_counts.items()))}",
        "```",
        "",
        "## Best Candidates",
        "",
    ]
    lines.append(
        _table(
            ["category", "run", "step", "phase", "miss", "lat", "ax", "rot", "contact", "reset_use"],
            [
                [
                    item.category,
                    item.run_id,
                    item.step,
                    item.phase,
                    _fmt(item.strict_miss_score),
                    _fmt(item.lateral),
                    _fmt(item.axial),
                    _fmt(item.rot),
                    _fmt(item.contact),
                    item.reset_use,
                ]
                for item in sorted_candidates[:limit]
            ],
        )
    )
    lines.extend(["", "## Candidate Categories", ""])
    for category in sorted(counts):
        rows = [
            item
            for item in sorted_candidates
            if item.category == category
        ][:limit]
        lines.extend([f"### {category}", ""])
        lines.append(
            _table(
                ["run", "step", "phase", "miss", "lat", "ax", "rot", "contact", "label_use"],
                [
                    [
                        item.run_id,
                        item.step,
                        item.phase,
                        _fmt(item.strict_miss_score),
                        _fmt(item.lateral),
                        _fmt(item.axial),
                        _fmt(item.rot),
                        _fmt(item.contact),
                        item.label_use,
                    ]
                    for item in rows
                ],
            )
        )
        lines.append("")
    lines.extend(
        [
            "## Interpretation",
            "",
            "- `target_gate_success` candidates can be used as positive success demonstrations.",
            "- All other categories are reset/handoff seeds or diagnostics, not strict-success labels.",
            "- If `target_gate_success` is empty, do not train another ordinary one-step BC policy expecting strict final insertion success.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "traces",
        nargs="*",
        type=Path,
        help="Trace JSON files, trace directories, or Launchable result archives. Defaults to scanning --root.",
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--since", default="2026-05-17T00-00-00Z")
    parser.add_argument("--archive", action="append", type=Path, default=[])
    parser.add_argument("--archive-glob", action="append", default=[])
    parser.add_argument("--task-contains", default="JointPos")
    parser.add_argument("--mode", default="")
    parser.add_argument("--xy-tol", type=float, default=0.005)
    parser.add_argument("--z-tol", type=float, default=0.045)
    parser.add_argument("--rot-tol", type=float, default=0.18)
    parser.add_argument("--min-contact", type=float, default=0.5)
    parser.add_argument("--near-xy-tol", type=float, default=0.015)
    parser.add_argument("--near-z-tol", type=float, default=0.060)
    parser.add_argument("--near-rot-tol", type=float, default=0.35)
    parser.add_argument("--near-min-contact", type=float, default=0.2)
    parser.add_argument("--strict-miss-max", type=float, default=0.20)
    parser.add_argument("--per-trace-limit", type=int, default=4)
    parser.add_argument("--min-step-spacing", type=int, default=25)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    cfg = GateCfg(
        xy_tol=args.xy_tol,
        z_tol=args.z_tol,
        rot_tol=args.rot_tol,
        min_contact=args.min_contact,
        near_xy_tol=args.near_xy_tol,
        near_z_tol=args.near_z_tol,
        near_rot_tol=args.near_rot_tol,
        near_min_contact=args.near_min_contact,
        strict_miss_max=args.strict_miss_max,
    )

    explicit_traces: list[Path] = []
    archives = list(args.archive)
    for path in args.traces:
        if str(path).endswith((".tar.gz", ".tgz")):
            archives.append(path)
        else:
            explicit_traces.append(path)
    for pattern in args.archive_glob:
        archives.extend(Path(match) for match in sorted(glob.glob(pattern)))

    if explicit_traces:
        trace_paths = _trace_paths(args.root, args.since, explicit_traces)
    elif archives:
        trace_paths = []
    else:
        trace_paths = _trace_paths(args.root, args.since, [])

    trace_payloads = [_load_trace_file(path) for path in trace_paths]
    for archive in archives:
        trace_payloads.extend(_load_archive_traces(archive, args.since))

    candidates: list[Candidate] = []
    for trace_id, run_id, data in trace_payloads:
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
        task = str(summary.get("task") or "")
        mode = str(summary.get("scripted_control_mode") or "")
        if args.task_contains and args.task_contains not in task:
            continue
        if args.mode and args.mode != mode:
            continue
        candidates.extend(
            _select_candidates(
                trace_id,
                run_id,
                data,
                cfg,
                per_trace_limit=args.per_trace_limit,
                min_step_spacing=max(0, args.min_step_spacing),
            )
        )

    candidates = sorted(candidates, key=_candidate_sort_key)
    payload = {
        "gate": asdict(cfg),
        "candidate_count": len(candidates),
        "category_counts": dict(sorted(Counter(candidate.category for candidate in candidates).items())),
        "tag_counts": dict(sorted(Counter(tag for candidate in candidates for tag in candidate.tags).items())),
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    markdown = _render_markdown(candidates, cfg, args.limit)

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[reset-candidates] wrote {args.output_json}")
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(markdown + "\n", encoding="utf-8")
        print(f"[reset-candidates] wrote {args.output_md}")
    if not args.output_json and not args.output_md:
        print(markdown)
    return 0 if candidates else 1


if __name__ == "__main__":
    raise SystemExit(main())
