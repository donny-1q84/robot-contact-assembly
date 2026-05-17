#!/usr/bin/env python3
"""Find scripted trace steps that satisfy a candidate relaxed contact-success gate."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Candidate:
    trace: Path
    run_id: str
    step: int
    phase: str
    lateral: float
    axial: float
    rot: float
    contact_force: float | None
    socket_pos: tuple[float, float, float] | None

    def passes(self, xy_tol: float, z_tol: float, rot_tol: float, min_contact_force: float) -> bool:
        if self.lateral >= xy_tol or self.axial >= z_tol or self.rot >= rot_tol:
            return False
        if min_contact_force <= 0.0:
            return True
        return self.contact_force is not None and self.contact_force >= min_contact_force

    def score(self, xy_tol: float, z_tol: float, rot_tol: float, min_contact_force: float) -> float:
        contact_gap = 0.0
        if min_contact_force > 0.0:
            contact_gap = max(0.0, min_contact_force - (self.contact_force or 0.0)) / min_contact_force
        return (
            max(0.0, self.lateral - xy_tol) / max(xy_tol, 1.0e-9)
            + max(0.0, self.axial - z_tol) / max(z_tol, 1.0e-9)
            + max(0.0, self.rot - rot_tol) / max(rot_tol, 1.0e-9)
            + contact_gap
        )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tuple3_or_none(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    return (float(value[0]), float(value[1]), float(value[2]))


def _collect_trace_paths(paths: list[Path], root: Path, since: str | None) -> list[Path]:
    if paths:
        trace_paths: list[Path] = []
        for path in paths:
            if path.is_dir():
                trace_paths.extend(sorted(path.glob("**/*_trace.json")))
            else:
                trace_paths.append(path)
        return trace_paths

    trace_paths = sorted(root.glob("*/seed_*_trace.json"))
    if since is not None:
        trace_paths = [path for path in trace_paths if path.parent.name >= since]
    return trace_paths


def _load_candidates(trace_path: Path) -> list[Candidate]:
    data = json.loads(trace_path.read_text(encoding="utf-8"))
    summary = data.get("summary", {})
    socket_pos = _tuple3_or_none(summary.get("socket_pos_override"))
    candidates: list[Candidate] = []
    for idx, step in enumerate(data.get("steps", [])):
        lateral = _float_or_none(step.get("lateral"))
        axial = _float_or_none(step.get("axial"))
        rot = _float_or_none(step.get("rot"))
        if lateral is None or axial is None or rot is None:
            continue
        candidates.append(
            Candidate(
                trace=trace_path,
                run_id=trace_path.parent.name,
                step=int(step.get("step", idx)),
                phase=str(step.get("phase", "")),
                lateral=lateral,
                axial=axial,
                rot=rot,
                contact_force=_float_or_none(step.get("contact_force_magnitude")),
                socket_pos=socket_pos,
            )
        )
    return candidates


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, tuple):
        return ",".join(f"{item:.3f}" for item in value)
    return str(value)


def _print_table(candidates: list[Candidate], args: argparse.Namespace, title: str) -> None:
    print(f"\n## {title}\n")
    if not candidates:
        print("_No matching steps._")
        return

    headers = ["rank", "run", "step", "phase", "socket", "lat", "ax", "rot", "contact", "score", "trace"]
    print("| " + " | ".join(headers) + " |")
    print("| " + " | ".join(["---"] * len(headers)) + " |")
    for rank, candidate in enumerate(candidates[: args.limit], start=1):
        row = [
            str(rank),
            candidate.run_id,
            str(candidate.step),
            candidate.phase,
            _fmt(candidate.socket_pos, 3),
            _fmt(candidate.lateral),
            _fmt(candidate.axial),
            _fmt(candidate.rot),
            _fmt(candidate.contact_force),
            _fmt(candidate.score(args.xy_tol, args.z_tol, args.rot_tol, args.min_contact_force)),
            str(candidate.trace),
        ]
        print("| " + " | ".join(row) + " |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", type=Path, nargs="*", help="Trace JSON files or directories. Defaults to root glob.")
    parser.add_argument("--root", type=Path, default=Path("artifacts/evaluations/scripted"))
    parser.add_argument("--since", help="Only include default-root run directories >= this timestamp.")
    parser.add_argument("--xy-tol", type=float, default=0.005)
    parser.add_argument("--z-tol", type=float, default=0.045)
    parser.add_argument("--rot-tol", type=float, default=0.18)
    parser.add_argument("--min-contact-force", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    trace_paths = _collect_trace_paths(args.traces, args.root, args.since)
    candidates = [candidate for path in trace_paths for candidate in _load_candidates(path)]
    passing = [c for c in candidates if c.passes(args.xy_tol, args.z_tol, args.rot_tol, args.min_contact_force)]
    passing.sort(key=lambda c: (c.run_id, c.step))
    closest = sorted(
        candidates,
        key=lambda c: (
            c.score(args.xy_tol, args.z_tol, args.rot_tol, args.min_contact_force),
            c.axial,
            c.lateral,
            c.rot,
        ),
    )

    print("# Relaxed Success Gate Analysis\n")
    print(f"- traces: `{len(trace_paths)}`")
    print(f"- steps: `{len(candidates)}`")
    print(
        f"- gate: lateral < `{args.xy_tol:.4f}m`, axial < `{args.z_tol:.4f}m`, "
        f"rot < `{args.rot_tol:.4f}rad`, contact >= `{args.min_contact_force:.3f}`"
    )
    print(f"- passing steps: `{len(passing)}`")
    _print_table(passing, args, "First Passing Steps")
    _print_table(closest, args, "Closest Steps")
    return 0 if candidates else 1


if __name__ == "__main__":
    raise SystemExit(main())
