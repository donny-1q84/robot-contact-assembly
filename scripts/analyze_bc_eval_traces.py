#!/usr/bin/env python3
"""Offline audit for BC and deterministic handoff-controller evaluation traces."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path("artifacts/evaluations/bc_policy")


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
class StageStats:
    steps: int
    success_steps: int
    first_success_step: int | None
    near_contact_steps: int
    near_contact_fraction: float
    longest_near_contact_streak: int
    first_near_contact_step: int | None
    best_miss: float | None
    best_miss_step: int | None
    initial_miss: float | None
    final_miss: float | None
    final_lateral: float | None
    final_axial: float | None
    final_rot: float | None
    final_contact: float | None


@dataclass(frozen=True)
class TraceAudit:
    run_id: str
    trace: str
    task: str | None
    controller: str | None
    checkpoint: str | None
    action_mode: str | None
    preload: StageStats | None
    bc: StageStats
    handoff_miss: float | None
    best_vs_handoff_delta: float | None
    final_vs_handoff_delta: float | None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _step_id(step: dict[str, Any], fallback: int) -> int:
    for key in ("step", "eval_step", "source_trace_step"):
        value = step.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return fallback


def _miss(step: dict[str, Any], cfg: GateCfg) -> float:
    lateral = _float(step.get("lateral"))
    axial = _float(step.get("axial"))
    rot = _float(step.get("rot"))
    contact = _float(step.get("contact_force_magnitude"))
    return (
        max(0.0, lateral - cfg.xy_tol) * 100.0
        + max(0.0, axial - cfg.z_tol) * 100.0
        + max(0.0, rot - cfg.rot_tol) * 10.0
        + max(0.0, cfg.min_contact - contact)
    )


def _success(step: dict[str, Any], cfg: GateCfg) -> bool:
    return (
        _float(step.get("lateral")) < cfg.xy_tol
        and _float(step.get("axial")) < cfg.z_tol
        and _float(step.get("rot")) < cfg.rot_tol
        and _float(step.get("contact_force_magnitude")) >= cfg.min_contact
    )


def _near_contact(step: dict[str, Any], cfg: GateCfg) -> bool:
    return (
        _float(step.get("lateral")) < cfg.near_xy_tol
        and _float(step.get("axial")) < cfg.near_z_tol
        and _float(step.get("rot")) < cfg.near_rot_tol
        and _float(step.get("contact_force_magnitude")) >= cfg.near_min_contact
    )


def _stage_stats(steps: list[dict[str, Any]], cfg: GateCfg) -> StageStats:
    if not steps:
        return StageStats(
            steps=0,
            success_steps=0,
            first_success_step=None,
            near_contact_steps=0,
            near_contact_fraction=0.0,
            longest_near_contact_streak=0,
            first_near_contact_step=None,
            best_miss=None,
            best_miss_step=None,
            initial_miss=None,
            final_miss=None,
            final_lateral=None,
            final_axial=None,
            final_rot=None,
            final_contact=None,
        )

    best_miss: float | None = None
    best_miss_step: int | None = None
    initial_miss = _miss(steps[0], cfg)
    final_miss = _miss(steps[-1], cfg)
    success_steps = 0
    first_success_step = None
    near_steps = 0
    first_near_step = None
    longest_near = 0
    current_near = 0

    for fallback, step in enumerate(steps):
        step_num = _step_id(step, fallback)
        miss = _miss(step, cfg)
        if best_miss is None or miss < best_miss:
            best_miss = miss
            best_miss_step = step_num
        if _success(step, cfg):
            success_steps += 1
            if first_success_step is None:
                first_success_step = step_num
        if _near_contact(step, cfg):
            near_steps += 1
            current_near += 1
            longest_near = max(longest_near, current_near)
            if first_near_step is None:
                first_near_step = step_num
        else:
            current_near = 0

    final = steps[-1]
    return StageStats(
        steps=len(steps),
        success_steps=success_steps,
        first_success_step=first_success_step,
        near_contact_steps=near_steps,
        near_contact_fraction=near_steps / max(1, len(steps)),
        longest_near_contact_streak=longest_near,
        first_near_contact_step=first_near_step,
        best_miss=best_miss,
        best_miss_step=best_miss_step,
        initial_miss=initial_miss,
        final_miss=final_miss,
        final_lateral=_float(final.get("lateral")),
        final_axial=_float(final.get("axial")),
        final_rot=_float(final.get("rot")),
        final_contact=_float(final.get("contact_force_magnitude")),
    )


def _split_stages(steps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    preload: list[dict[str, Any]] = []
    bc: list[dict[str, Any]] = []
    for step in steps:
        stage = step.get("stage")
        if stage == "preload":
            preload.append(step)
        elif stage == "bc" or stage is None:
            bc.append(step)
    return preload, bc


def _audit_trace(path: Path, cfg: GateCfg) -> TraceAudit:
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = data.get("summary") or {}
    preload_steps, bc_steps = _split_stages(data.get("steps") or [])
    preload_stats = _stage_stats(preload_steps, cfg) if preload_steps else None
    bc_stats = _stage_stats(bc_steps, cfg)
    handoff_miss = preload_stats.final_miss if preload_stats is not None else None
    best_delta = None
    final_delta = None
    if handoff_miss is not None:
        if bc_stats.best_miss is not None:
            best_delta = bc_stats.best_miss - handoff_miss
        if bc_stats.final_miss is not None:
            final_delta = bc_stats.final_miss - handoff_miss
    return TraceAudit(
        run_id=path.parent.name,
        trace=str(path),
        task=summary.get("task"),
        controller=summary.get("controller"),
        checkpoint=summary.get("checkpoint"),
        action_mode=summary.get("action_mode"),
        preload=preload_stats,
        bc=bc_stats,
        handoff_miss=handoff_miss,
        best_vs_handoff_delta=best_delta,
        final_vs_handoff_delta=final_delta,
    )


def _trace_paths(root: Path, explicit: list[Path]) -> list[Path]:
    if explicit:
        paths: list[Path] = []
        for path in explicit:
            if path.is_dir():
                paths.extend(sorted(path.glob("**/trace.json")))
            else:
                paths.append(path)
        return sorted(paths)
    return sorted(root.glob("*/trace.json"))


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(lines)


def _render(audits: list[TraceAudit], cfg: GateCfg) -> str:
    lines = [
        "# Handoff Controller Evaluation Trace Audit",
        "",
        "## Gates",
        "",
        "```text",
        f"target: xy < {cfg.xy_tol:.4f} m, z < {cfg.z_tol:.4f} m, rot < {cfg.rot_tol:.4f} rad, contact >= {cfg.min_contact:.3f}",
        f"near:   xy < {cfg.near_xy_tol:.4f} m, z < {cfg.near_z_tol:.4f} m, rot < {cfg.near_rot_tol:.4f} rad, contact >= {cfg.near_min_contact:.3f}",
        "```",
        "",
        "## Summary",
        "",
    ]
    lines.append(
        _table(
            [
                "run",
                "controller",
                "preload",
                "controlled_steps",
                "controlled_success",
                "near_frac",
                "longest_near",
                "handoff_miss",
                "best_miss",
                "final_miss",
                "best_delta",
                "final_delta",
            ],
            [
                [
                    audit.run_id,
                    audit.controller or audit.action_mode or "legacy-absolute",
                    audit.preload.steps if audit.preload else 0,
                    audit.bc.steps,
                    audit.bc.success_steps,
                    _fmt(audit.bc.near_contact_fraction),
                    audit.bc.longest_near_contact_streak,
                    _fmt(audit.handoff_miss),
                    _fmt(audit.bc.best_miss),
                    _fmt(audit.bc.final_miss),
                    _fmt(audit.best_vs_handoff_delta),
                    _fmt(audit.final_vs_handoff_delta),
                ]
                for audit in audits
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `near_frac` measures how much of the controlled rollout stayed in the relaxed near-contact band.",
            "- `best_delta` and `final_delta` are relative to the handoff miss when a preload stage exists; positive values mean the controller made the state worse.",
            "- Legacy all-trace BC has no preload handoff, so its deltas are `n/a`.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="*", type=Path, help="BC trace JSON files or directories.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--xy-tol", type=float, default=0.005)
    parser.add_argument("--z-tol", type=float, default=0.045)
    parser.add_argument("--rot-tol", type=float, default=0.18)
    parser.add_argument("--min-contact", type=float, default=0.5)
    parser.add_argument("--near-xy-tol", type=float, default=0.015)
    parser.add_argument("--near-z-tol", type=float, default=0.060)
    parser.add_argument("--near-rot-tol", type=float, default=0.35)
    parser.add_argument("--near-min-contact", type=float, default=0.2)
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
    audits = [_audit_trace(path, cfg) for path in _trace_paths(args.root, args.traces)]
    markdown = _render(audits, cfg)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(markdown + "\n", encoding="utf-8")
        print(f"[bc-audit] wrote {args.output_md}")
    else:
        print(markdown)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(
            json.dumps(
                {
                    "gate": asdict(cfg),
                    "audits": [
                        {
                            **asdict(audit),
                        }
                        for audit in audits
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"[bc-audit] wrote {args.output_json}")
    return 0 if audits else 1


if __name__ == "__main__":
    raise SystemExit(main())
