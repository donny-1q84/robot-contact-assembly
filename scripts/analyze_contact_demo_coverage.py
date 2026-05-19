#!/usr/bin/env python3
"""Audit scripted traces for IL/BC contact-demonstration coverage."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path("artifacts/evaluations/scripted")


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


@dataclass(frozen=True)
class StepMetric:
    run_id: str
    trace: str
    task: str
    scripted_control_mode: str
    socket_pos: list[float] | None
    index: int
    step: int
    phase: str
    lateral: float
    axial: float
    rot: float
    contact: float
    miss: float
    passes_gate: bool
    near_contact: bool


@dataclass(frozen=True)
class TraceCoverage:
    run_id: str
    trace: str
    task: str
    scripted_control_mode: str
    socket_pos: list[float] | None
    steps: int
    gate_pass_steps: int
    near_contact_steps: int
    longest_gate_streak: int
    longest_near_streak: int
    best_step: StepMetric
    final_miss: float
    final_lateral: float
    final_axial: float
    final_rot: float
    final_contact: float
    post_best_min_miss: float
    post_best_final_delta: float


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


def _miss(lateral: float, axial: float, rot: float, contact: float, cfg: GateCfg) -> float:
    return (
        max(0.0, lateral - cfg.xy_tol) * 100.0
        + max(0.0, axial - cfg.z_tol) * 100.0
        + max(0.0, rot - cfg.rot_tol) * 10.0
        + max(0.0, cfg.min_contact - contact)
    )


def _passes(lateral: float, axial: float, rot: float, contact: float, cfg: GateCfg) -> bool:
    return lateral < cfg.xy_tol and axial < cfg.z_tol and rot < cfg.rot_tol and contact >= cfg.min_contact


def _near(lateral: float, axial: float, rot: float, contact: float, cfg: GateCfg) -> bool:
    return (
        lateral < cfg.near_xy_tol
        and axial < cfg.near_z_tol
        and rot < cfg.near_rot_tol
        and contact >= cfg.near_min_contact
    )


def _longest_streak(values: list[bool]) -> int:
    best = 0
    current = 0
    for value in values:
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


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


def _load_trace(path: Path, cfg: GateCfg) -> tuple[dict[str, Any], list[StepMetric]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary") or {}
    task = str(summary.get("task") or "")
    scripted_control_mode = str(summary.get("scripted_control_mode") or "")
    socket_pos = _socket_pos(summary)
    metrics: list[StepMetric] = []
    for index, step in enumerate(data.get("steps") or []):
        if not isinstance(step, dict):
            continue
        lateral = _float(step.get("lateral"))
        axial = _float(step.get("axial"))
        rot = _float(step.get("rot"))
        contact = _float(step.get("contact_force_magnitude"))
        miss = _miss(lateral, axial, rot, contact, cfg)
        metrics.append(
            StepMetric(
                run_id=path.parent.name,
                trace=str(path),
                task=task,
                scripted_control_mode=scripted_control_mode,
                socket_pos=socket_pos,
                index=index,
                step=int(step.get("step") if step.get("step") is not None else index),
                phase=str(step.get("phase") or ""),
                lateral=lateral,
                axial=axial,
                rot=rot,
                contact=contact,
                miss=miss,
                passes_gate=_passes(lateral, axial, rot, contact, cfg),
                near_contact=_near(lateral, axial, rot, contact, cfg),
            )
        )
    return summary, metrics


def _coverage(path: Path, metrics: list[StepMetric]) -> TraceCoverage | None:
    if not metrics:
        return None
    best = min(metrics, key=lambda metric: (metric.miss, metric.axial, metric.lateral, metric.rot))
    final = metrics[-1]
    future = metrics[best.index :]
    post_best_min_miss = min(metric.miss for metric in future) if future else best.miss
    return TraceCoverage(
        run_id=path.parent.name,
        trace=str(path),
        task=best.task,
        scripted_control_mode=best.scripted_control_mode,
        socket_pos=best.socket_pos,
        steps=len(metrics),
        gate_pass_steps=sum(metric.passes_gate for metric in metrics),
        near_contact_steps=sum(metric.near_contact for metric in metrics),
        longest_gate_streak=_longest_streak([metric.passes_gate for metric in metrics]),
        longest_near_streak=_longest_streak([metric.near_contact for metric in metrics]),
        best_step=best,
        final_miss=final.miss,
        final_lateral=final.lateral,
        final_axial=final.axial,
        final_rot=final.rot,
        final_contact=final.contact,
        post_best_min_miss=post_best_min_miss,
        post_best_final_delta=final.miss - best.miss,
    )


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
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


def _render_markdown(coverages: list[TraceCoverage], cfg: GateCfg, limit: int) -> str:
    total_steps = sum(item.steps for item in coverages)
    gate_pass_steps = sum(item.gate_pass_steps for item in coverages)
    near_contact_steps = sum(item.near_contact_steps for item in coverages)
    traces_with_gate = sum(1 for item in coverages if item.gate_pass_steps > 0)
    traces_with_near = sum(1 for item in coverages if item.near_contact_steps > 0)
    sorted_best = sorted(coverages, key=lambda item: (item.best_step.miss, item.best_step.axial, item.best_step.lateral))
    sorted_sustained = sorted(
        coverages,
        key=lambda item: (item.longest_near_streak, -item.best_step.miss),
        reverse=True,
    )
    passing = [item for item in sorted_best if item.gate_pass_steps > 0]

    lines = [
        "# Contact Demonstration Coverage Audit",
        "",
        "## Gate",
        "",
        "```text",
        f"target gate: xy < {cfg.xy_tol:.4f} m, z < {cfg.z_tol:.4f} m, rot < {cfg.rot_tol:.4f} rad, contact >= {cfg.min_contact:.3f}",
        f"near gate:   xy < {cfg.near_xy_tol:.4f} m, z < {cfg.near_z_tol:.4f} m, rot < {cfg.near_rot_tol:.4f} rad, contact >= {cfg.near_min_contact:.3f}",
        "```",
        "",
        "## Aggregate",
        "",
        "```text",
        f"traces: {len(coverages)}",
        f"steps: {total_steps}",
        f"target-gate passing steps: {gate_pass_steps}",
        f"traces with target-gate steps: {traces_with_gate}",
        f"near-contact steps: {near_contact_steps}",
        f"traces with near-contact steps: {traces_with_near}",
        "```",
        "",
        "## Closest Target-Gate Steps",
        "",
    ]
    lines.append(
        _table(
            ["run", "task", "mode", "socket", "step", "phase", "miss", "lat", "ax", "rot", "contact", "near_streak"],
            [
                [
                    item.run_id,
                    item.task,
                    item.scripted_control_mode,
                    _fmt(item.socket_pos),
                    item.best_step.step,
                    item.best_step.phase,
                    _fmt(item.best_step.miss),
                    _fmt(item.best_step.lateral),
                    _fmt(item.best_step.axial),
                    _fmt(item.best_step.rot),
                    _fmt(item.best_step.contact),
                    item.longest_near_streak,
                ]
                for item in sorted_best[:limit]
            ],
        )
    )
    lines.extend(["", "## Traces With Target-Gate Passing Steps", ""])
    if passing:
        lines.append(
            _table(
                ["run", "task", "mode", "passes", "longest_pass", "best_step", "best_miss", "final_delta"],
                [
                    [
                        item.run_id,
                        item.task,
                        item.scripted_control_mode,
                        item.gate_pass_steps,
                        item.longest_gate_streak,
                        item.best_step.step,
                        _fmt(item.best_step.miss),
                        _fmt(item.post_best_final_delta),
                    ]
                    for item in passing[:limit]
                ],
            )
        )
    else:
        lines.append("_No target-gate passing steps._")
    lines.extend(["", "## Sustained Near-Contact Traces", ""])
    lines.append(
        _table(
            ["run", "task", "mode", "near_steps", "longest_near", "best_step", "best_miss", "final_delta"],
            [
                [
                    item.run_id,
                    item.task,
                    item.scripted_control_mode,
                    item.near_contact_steps,
                    item.longest_near_streak,
                    item.best_step.step,
                    _fmt(item.best_step.miss),
                    _fmt(item.post_best_final_delta),
                ]
                for item in sorted_sustained[:limit]
            ],
        )
    )
    lines.extend(
        [
            "",
            "## IL Interpretation",
            "",
            "- If a trace has many near-contact steps but few or no target-gate passing steps, it is useful for approach/contact-retention data but weak as a final insertion success label.",
            "- A positive final_delta means the rollout drifted away after its best contact state; one-step BC trained on that window can learn the approach but still destabilize after handoff.",
            "- Use this report to choose demonstration sources before spending GPU time on another learned-policy run.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="*", type=Path, help="Trace JSON files or directories. Defaults to scanning --root.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--since", default="2026-05-17T00-00-00Z")
    parser.add_argument("--task-contains", default="JointPos", help="Only include traces whose task contains this string. Empty string disables.")
    parser.add_argument("--mode", default="", help="Only include traces whose scripted_control_mode matches this value. Empty string disables.")
    parser.add_argument("--xy-tol", type=float, default=0.005)
    parser.add_argument("--z-tol", type=float, default=0.045)
    parser.add_argument("--rot-tol", type=float, default=0.18)
    parser.add_argument("--min-contact", type=float, default=0.5)
    parser.add_argument("--near-xy-tol", type=float, default=0.015)
    parser.add_argument("--near-z-tol", type=float, default=0.060)
    parser.add_argument("--near-rot-tol", type=float, default=0.35)
    parser.add_argument("--near-min-contact", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--output-json", type=Path)
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
    )
    coverages: list[TraceCoverage] = []
    for path in _trace_paths(args.root, args.since, args.traces):
        summary, metrics = _load_trace(path, cfg)
        task = str(summary.get("task") or "")
        mode = str(summary.get("scripted_control_mode") or "")
        if args.task_contains and args.task_contains not in task:
            continue
        if args.mode and args.mode != mode:
            continue
        item = _coverage(path, metrics)
        if item is not None:
            coverages.append(item)

    markdown = _render_markdown(coverages, cfg, args.limit)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(markdown + "\n", encoding="utf-8")
        print(f"[coverage] wrote {args.output_md}")
    else:
        print(markdown)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "gate": asdict(cfg),
            "coverages": [
                {
                    **{k: v for k, v in asdict(item).items() if k != "best_step"},
                    "best_step": asdict(item.best_step),
                }
                for item in coverages
            ],
        }
        args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[coverage] wrote {args.output_json}")
    return 0 if coverages else 1


if __name__ == "__main__":
    raise SystemExit(main())
