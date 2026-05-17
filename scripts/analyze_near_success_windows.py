#!/usr/bin/env python3
"""Analyze near-success windows in scripted contact-rollout traces."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_XY_TOLERANCE = 0.005
DEFAULT_AXIAL_TOLERANCE = 0.008
DEFAULT_ROT_TOLERANCE = 0.18


@dataclass(frozen=True)
class StepScore:
    trace: Path
    step_index: int
    step: int
    phase: str
    lateral: float
    axial: float
    rot: float
    xy_tolerance: float
    axial_tolerance: float
    rot_tolerance: float
    contact_force: float | None
    joint_margin_min: float | None
    joint_margin_argmin: int | None
    branch_jump: bool

    @property
    def xy_gap(self) -> float:
        return max(0.0, self.lateral - self.xy_tolerance)

    @property
    def axial_gap(self) -> float:
        return max(0.0, self.axial - self.axial_tolerance)

    @property
    def rot_gap(self) -> float:
        return max(0.0, self.rot - self.rot_tolerance)

    @property
    def normalized_gap(self) -> float:
        return (
            self.xy_gap / max(self.xy_tolerance, 1e-9)
            + self.axial_gap / max(self.axial_tolerance, 1e-9)
            + self.rot_gap / max(self.rot_tolerance, 1e-9)
        )

    @property
    def success_axes(self) -> int:
        return int(self.xy_gap == 0.0) + int(self.axial_gap == 0.0) + int(self.rot_gap == 0.0)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _joint_margin(step: dict[str, Any]) -> tuple[float | None, int | None]:
    margins = step.get("post_joint_limit_margin") or step.get("joint_limit_margin")
    if not isinstance(margins, list) or not margins:
        margin = _float_or_none(step.get("post_joint_limit_margin_min") or step.get("joint_limit_margin_min"))
        return margin, None
    numeric = [float(value) for value in margins]
    min_value = min(numeric)
    return min_value, numeric.index(min_value)


def _score_steps(trace_path: Path) -> list[StepScore]:
    data = json.loads(trace_path.read_text(encoding="utf-8"))
    scored: list[StepScore] = []
    for idx, step in enumerate(data.get("steps", [])):
        lateral = _float_or_none(step.get("lateral"))
        axial = _float_or_none(step.get("axial"))
        rot = _float_or_none(step.get("rot"))
        if lateral is None or axial is None or rot is None:
            continue
        joint_margin, joint_margin_argmin = _joint_margin(step)
        scored.append(
            StepScore(
                trace=trace_path,
                step_index=idx,
                step=int(step.get("step", idx)),
                phase=str(step.get("phase", "")),
                lateral=lateral,
                axial=axial,
                rot=rot,
                xy_tolerance=float(step.get("success_xy_tolerance", DEFAULT_XY_TOLERANCE)),
                axial_tolerance=float(step.get("success_z_tolerance", DEFAULT_AXIAL_TOLERANCE)),
                rot_tolerance=float(step.get("success_rot_tolerance", DEFAULT_ROT_TOLERANCE)),
                contact_force=_float_or_none(step.get("contact_force_magnitude")),
                joint_margin_min=joint_margin,
                joint_margin_argmin=joint_margin_argmin,
                branch_jump=bool(step.get("branch_jump")),
            )
        )
    return scored


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _row(score: StepScore) -> list[str]:
    return [
        score.trace.parent.name,
        str(score.step),
        score.phase,
        _fmt(score.lateral),
        _fmt(score.axial),
        _fmt(score.rot),
        str(score.success_axes),
        _fmt(score.normalized_gap),
        _fmt(score.contact_force),
        _fmt(score.joint_margin_min),
        "n/a" if score.joint_margin_argmin is None else str(score.joint_margin_argmin),
        "1" if score.branch_jump else "0",
    ]


def _print_table(title: str, rows: list[StepScore], limit: int) -> None:
    print(f"\n## {title}\n")
    if not rows:
        print("_No matching steps._")
        return
    headers = [
        "run",
        "step",
        "phase",
        "lat",
        "ax",
        "rot",
        "axes",
        "gap",
        "contact",
        "jlim",
        "jlim_i",
        "branch",
    ]
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join(["---"] * len(headers)) + " |")
    for score in rows[:limit]:
        print("| " + " | ".join(_row(score)) + " |")


def _trace_summary(trace_path: Path, scores: list[StepScore]) -> None:
    if not scores:
        print(f"- `{trace_path}`: no scoreable steps")
        return
    best_overall = min(scores, key=lambda score: score.normalized_gap)
    best_axial = min(scores, key=lambda score: score.axial)
    best_xy = min(scores, key=lambda score: score.lateral)
    best_rot = min(scores, key=lambda score: score.rot)
    branch_steps = [score for score in scores if score.branch_jump]
    near_seat = [score for score in scores if score.axial <= 0.05]
    low_margin_near_seat = [
        score
        for score in near_seat
        if score.joint_margin_min is not None and score.joint_margin_min <= 0.02
    ]

    print(f"- `{trace_path.parent.name}`")
    print(
        "  - best overall: "
        f"step `{best_overall.step}`, phase `{best_overall.phase}`, "
        f"lat `{best_overall.lateral:.4f}`, ax `{best_overall.axial:.4f}`, "
        f"rot `{best_overall.rot:.4f}`, gap `{best_overall.normalized_gap:.2f}`"
    )
    print(
        "  - independent minima: "
        f"lat `{best_xy.lateral:.4f}`@`{best_xy.step}`, "
        f"ax `{best_axial.axial:.4f}`@`{best_axial.step}`, "
        f"rot `{best_rot.rot:.4f}`@`{best_rot.step}`"
    )
    print(
        "  - near-seat steps: "
        f"`{len(near_seat)}` total, `{len(low_margin_near_seat)}` with joint margin <= `0.02rad`, "
        f"branch jumps `{len(branch_steps)}`"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", type=Path, nargs="+", help="Trace JSON files to analyze.")
    parser.add_argument("--limit", type=int, default=8, help="Rows to print per table.")
    parser.add_argument("--near-seat-axial", type=float, default=0.05)
    parser.add_argument("--low-joint-margin", type=float, default=0.02)
    args = parser.parse_args()

    per_trace = [(trace, _score_steps(trace)) for trace in args.traces]
    all_scores = [score for _, scores in per_trace for score in scores]

    print("# Near-Success Window Analysis")
    print("\nSuccess thresholds are read from each trace step. Defaults are:")
    print(
        f"- XY <= `{DEFAULT_XY_TOLERANCE}m`, axial <= `{DEFAULT_AXIAL_TOLERANCE}m`, "
        f"rotation <= `{DEFAULT_ROT_TOLERANCE}rad`"
    )
    print("\n## Per-Trace Summary\n")
    for trace, scores in per_trace:
        _trace_summary(trace, scores)

    ranked = sorted(all_scores, key=lambda score: score.normalized_gap)
    near_seat = sorted(
        [score for score in all_scores if score.axial <= args.near_seat_axial],
        key=lambda score: (score.axial, score.normalized_gap),
    )
    xy_rot_ready = sorted(
        [score for score in all_scores if score.xy_gap == 0.0 and score.rot_gap == 0.0],
        key=lambda score: (score.axial, score.normalized_gap),
    )
    low_joint_margin = sorted(
        [
            score
            for score in all_scores
            if score.joint_margin_min is not None
            and score.joint_margin_min <= args.low_joint_margin
            and score.axial <= args.near_seat_axial
        ],
        key=lambda score: (score.joint_margin_min or 0.0, score.axial),
    )
    branch_jumps = sorted(
        [score for score in all_scores if score.branch_jump],
        key=lambda score: score.step,
    )

    _print_table("Closest Overall Steps", ranked, args.limit)
    _print_table(f"Near-Seat Steps (axial <= {args.near_seat_axial:.3f}m)", near_seat, args.limit)
    _print_table("XY + Rotation Ready Steps", xy_rot_ready, args.limit)
    _print_table(
        f"Near-Seat Steps With Joint Margin <= {args.low_joint_margin:.3f}rad",
        low_joint_margin,
        args.limit,
    )
    _print_table("Branch-Jump Steps", branch_jumps, args.limit)

    if ranked:
        best = ranked[0]
        print("\n## Diagnosis\n")
        print(
            "- The best simultaneous step still needs "
            f"`+{best.xy_gap:.4f}m` XY tolerance, "
            f"`+{best.axial_gap:.4f}m` axial tolerance, and "
            f"`+{best.rot_gap:.4f}rad` rotation tolerance beyond the current success gate."
        )
        if low_joint_margin:
            print(
                "- Near-seat samples repeatedly occur with very low joint-limit margin. "
                "Treat the current socket pose/controller path as a workspace-constrained setup."
            )
        if branch_jumps:
            print(
                "- Branch jumps are present in the same near-contact region. "
                "Avoid another threshold-only polish run before changing geometry, socket pose, or the insertion controller."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
