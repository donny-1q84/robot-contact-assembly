#!/usr/bin/env python3
"""Summarize scripted socket-pose sweep results from pulled evaluation JSON files."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SweepResult:
    path: Path
    run_id: str
    seed: int | None
    socket_pos: tuple[float, float, float] | None
    success_step: int | None
    final_success_rate: float
    final_lateral: float | None
    final_axial: float | None
    final_rot: float | None
    best_lateral: float | None
    best_lateral_step: int | None
    best_axial: float | None
    best_axial_step: int | None
    best_rot: float | None
    best_rot_step: int | None
    max_contact_force: float | None
    max_contact_force_step: int | None
    branch_jump_step: int | None
    branch_jump_joint_margin: float | None

    @property
    def succeeded(self) -> bool:
        return self.success_step is not None or self.final_success_rate > 0.0

    @property
    def near_success_score(self) -> float:
        lateral = self.best_lateral if self.best_lateral is not None else 1.0
        axial = self.best_axial if self.best_axial is not None else 1.0
        rot = self.best_rot if self.best_rot is not None else 3.14
        return lateral / 0.005 + axial / 0.008 + rot / 0.18


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _socket_pos(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    return (float(value[0]), float(value[1]), float(value[2]))


def _load_result(path: Path) -> SweepResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    return SweepResult(
        path=path,
        run_id=path.parent.name,
        seed=_int_or_none(data.get("seed")),
        socket_pos=_socket_pos(data.get("socket_pos_override")),
        success_step=_int_or_none(data.get("success_step")),
        final_success_rate=float(data.get("final_success_rate") or 0.0),
        final_lateral=_float_or_none(data.get("final_lateral")),
        final_axial=_float_or_none(data.get("final_axial")),
        final_rot=_float_or_none(data.get("final_rot")),
        best_lateral=_float_or_none(data.get("best_lateral")),
        best_lateral_step=_int_or_none(data.get("best_lateral_step")),
        best_axial=_float_or_none(data.get("best_axial")),
        best_axial_step=_int_or_none(data.get("best_axial_step")),
        best_rot=_float_or_none(data.get("best_rot")),
        best_rot_step=_int_or_none(data.get("best_rot_step")),
        max_contact_force=_float_or_none(data.get("max_contact_force_magnitude")),
        max_contact_force_step=_int_or_none(data.get("max_contact_force_magnitude_step")),
        branch_jump_step=_int_or_none(data.get("branch_jump_step")),
        branch_jump_joint_margin=_float_or_none(data.get("branch_jump_joint_limit_margin_min")),
    )


def _collect_results(root: Path, since: str | None) -> list[SweepResult]:
    results: list[SweepResult] = []
    for path in sorted(root.glob("*/seed_*.json")):
        if since is not None and path.parent.name < since:
            continue
        result = _load_result(path)
        if result.socket_pos is None:
            continue
        results.append(result)
    return results


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, tuple):
        return ",".join(f"{item:.3f}" for item in value)
    return str(value)


def _print_table(results: list[SweepResult]) -> None:
    headers = [
        "rank",
        "run",
        "seed",
        "socket",
        "success",
        "score",
        "best_lat",
        "best_ax",
        "best_rot",
        "final_lat",
        "final_ax",
        "final_rot",
        "max_contact",
        "branch",
        "json",
    ]
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join(["---"] * len(headers)) + " |")
    for rank, result in enumerate(results, start=1):
        success = "yes" if result.succeeded else "no"
        if result.success_step is not None:
            success = f"step {result.success_step}"
        row = [
            str(rank),
            result.run_id,
            _fmt(result.seed),
            _fmt(result.socket_pos, 3),
            success,
            _fmt(result.near_success_score),
            f"{_fmt(result.best_lateral)}@{_fmt(result.best_lateral_step)}",
            f"{_fmt(result.best_axial)}@{_fmt(result.best_axial_step)}",
            f"{_fmt(result.best_rot)}@{_fmt(result.best_rot_step)}",
            _fmt(result.final_lateral),
            _fmt(result.final_axial),
            _fmt(result.final_rot),
            f"{_fmt(result.max_contact_force)}@{_fmt(result.max_contact_force_step)}",
            _fmt(result.branch_jump_step),
            str(result.path),
        ]
        print("| " + " | ".join(row) + " |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("artifacts/evaluations/scripted"),
        help="Pulled scripted evaluation root.",
    )
    parser.add_argument("--since", help="Only include run directories with names >= this timestamp.")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    results = _collect_results(args.root, args.since)
    if not results:
        print("No socket-sweep result JSON files found.")
        return 1

    ranked = sorted(results, key=lambda result: (not result.succeeded, result.near_success_score))
    print("# Socket Sweep Summary\n")
    print(f"- root: `{args.root}`")
    if args.since is not None:
        print(f"- since: `{args.since}`")
    print(f"- results: `{len(results)}`")
    print(f"- successes: `{sum(result.succeeded for result in results)}`")
    print()
    _print_table(ranked[: args.limit])

    best = ranked[0]
    print("\n## Best Candidate\n")
    print(f"- run: `{best.run_id}`")
    print(f"- socket: `{_fmt(best.socket_pos, 3)}`")
    print(f"- success: `{'yes' if best.succeeded else 'no'}`")
    print(f"- score: `{best.near_success_score:.4f}`")
    print(f"- json: `{best.path}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
