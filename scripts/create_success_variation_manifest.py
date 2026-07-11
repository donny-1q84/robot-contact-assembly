#!/usr/bin/env python3
"""Create a local-first manifest for successful-trace variation runs.

The manifest is an experiment contract, not evidence that the variations have
already run. It keeps future paid trace-only batches small, explicit, and
classifiable before any GPU instance is opened.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_TRACE = REPO_ROOT / "artifacts/deliverables/2026-06-21-peg-in-hole-success-trace/video_trace.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts/manifests"
CONSTANTS_PATH = (
    REPO_ROOT
    / "source"
    / "robot_contact_assembly_tasks"
    / "robot_contact_assembly_tasks"
    / "tasks"
    / "manager_based"
    / "manipulation"
    / "peg_in_hole"
    / "constants.py"
)


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_trace_summary(trace_path: Path) -> dict[str, Any]:
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError(f"source trace has no summary object: {_rel(trace_path)}")
    return summary


def _load_source_socket_frame_pos() -> list[float]:
    spec = importlib.util.spec_from_file_location("rca_peg_constants", CONSTANTS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load constants from {_rel(CONSTANTS_PATH)}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [float(value) for value in module.SOCKET_FRAME_POS]


def _case(
    case_id: str,
    *,
    seed: int,
    socket_delta_m: tuple[float, float, float],
    reset_joint_noise_rad: float,
    expected: str,
    rationale: str,
    trace_json: str | None = None,
) -> dict[str, Any]:
    case: dict[str, Any] = {
        "case_id": case_id,
        "seed": seed,
        "socket_delta_m": [float(value) for value in socket_delta_m],
        "reset_joint_noise_rad": float(reset_joint_noise_rad),
        "expected": expected,
        "rationale": rationale,
        "status": "planned",
    }
    if trace_json:
        case["trace_json"] = trace_json
        case["status"] = "available"
    return case


def build_manifest(
    source_trace: Path,
    *,
    output_trace_root: str,
    created_utc: str | None = None,
) -> dict[str, Any]:
    source_trace = source_trace.resolve()
    if not source_trace.is_file():
        raise RuntimeError(f"source trace is missing: {_rel(source_trace)}")
    summary = _load_trace_summary(source_trace)
    seed = int(summary.get("seed") or 42)
    task = str(summary.get("task") or "RCA-PegInHole-Franka-JointPos-Contact-Play-v0")

    created = created_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    source_rel = _rel(source_trace)
    cases = [
        _case(
            "baseline_replay",
            seed=seed,
            socket_delta_m=(0.0, 0.0, 0.0),
            reset_joint_noise_rad=0.0,
            expected="strict_success",
            rationale="Original validated success trace; positive control for classifier and future batch.",
            trace_json=source_rel,
        ),
        _case(
            "seed_43_nominal",
            seed=seed + 1,
            socket_delta_m=(0.0, 0.0, 0.0),
            reset_joint_noise_rad=0.0,
            expected="unknown",
            rationale="Same nominal task with a different seed; should show whether success is seed-fragile.",
        ),
        _case(
            "seed_44_reset_noise",
            seed=seed + 2,
            socket_delta_m=(0.0, 0.0, 0.0),
            reset_joint_noise_rad=0.01,
            expected="unknown",
            rationale="Small reset perturbation to test robustness without changing socket pose.",
        ),
        _case(
            "socket_x_pos_1mm",
            seed=seed,
            socket_delta_m=(0.001, 0.0, 0.0),
            reset_joint_noise_rad=0.0,
            expected="unknown",
            rationale="Millimeter positive X socket perturbation.",
        ),
        _case(
            "socket_x_neg_1mm",
            seed=seed,
            socket_delta_m=(-0.001, 0.0, 0.0),
            reset_joint_noise_rad=0.0,
            expected="unknown",
            rationale="Millimeter negative X socket perturbation.",
        ),
        _case(
            "socket_y_pos_1mm",
            seed=seed,
            socket_delta_m=(0.0, 0.001, 0.0),
            reset_joint_noise_rad=0.0,
            expected="unknown",
            rationale="Millimeter positive Y socket perturbation.",
        ),
        _case(
            "socket_y_neg_1mm",
            seed=seed,
            socket_delta_m=(0.0, -0.001, 0.0),
            reset_joint_noise_rad=0.0,
            expected="unknown",
            rationale="Millimeter negative Y socket perturbation.",
        ),
        _case(
            "socket_z_pos_1mm",
            seed=seed,
            socket_delta_m=(0.0, 0.0, 0.001),
            reset_joint_noise_rad=0.0,
            expected="unknown",
            rationale="Millimeter positive Z socket perturbation.",
        ),
        _case(
            "socket_x_pos_25mm_negative_control",
            seed=seed,
            socket_delta_m=(0.025, 0.0, 0.0),
            reset_joint_noise_rad=0.0,
            expected="fail_closed",
            rationale="Deliberate large socket shift; semantic success gate should fail if the trace/controller is not regenerated correctly.",
        ),
    ]

    for case in cases:
        case.setdefault(
            "planned_trace_json",
            f"{output_trace_root.rstrip('/')}/{case['case_id']}/video_trace.json",
        )

    return {
        "manifest_version": 1,
        "created_utc": created,
        "purpose": "successful_trace_variation_batch",
        "task": task,
        "source_trace_json": source_rel,
        "source_trace_sha256": _sha256(source_trace),
        "source_summary": {
            "success_step": summary.get("success_step"),
            "final_success_rate": summary.get("final_success_rate"),
            "best_lateral": summary.get("best_lateral"),
            "best_axial": summary.get("best_axial"),
            "best_rot": summary.get("best_rot"),
            "max_contact_force_magnitude": summary.get("max_contact_force_magnitude"),
        },
        "source_socket_frame_pos_m": _load_source_socket_frame_pos(),
        "classification_contract": {
            "strict_success": "peg-video-candidate, final-contact-boundary, and trace-frame-alignment gates all pass",
            "near_success": "strict gates fail but relaxed near-contact metrics are met",
            "fail_closed": "trace exists but does not meet strict or near-success criteria",
            "missing": "planned case has no trace artifact yet",
        },
        "near_success_thresholds": {
            "best_lateral_max_m": 0.015,
            "best_axial_max_m": 0.060,
            "best_rot_max_rad": 0.35,
            "max_contact_force_min_n": 0.2,
        },
        "remote_run_policy": {
            "paid_compute_allowed": False,
            "requires_budget_watchdog_pullback_delete": True,
            "run_mode": "trace-only-first",
        },
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-trace", type=Path, default=DEFAULT_SOURCE_TRACE)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--output-trace-root",
        default="artifacts/videos/success_variations",
        help="Planned root for future per-case video_trace.json artifacts.",
    )
    parser.add_argument("--json", action="store_true", help="Print manifest JSON to stdout.")
    args = parser.parse_args()

    manifest = build_manifest(args.source_trace, output_trace_root=args.output_trace_root)
    output = args.output
    if output is None and not args.json:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output = DEFAULT_OUTPUT_DIR / f"success_trace_variations_{manifest['created_utc']}.json"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[success-variations] wrote manifest: {_rel(output)}")
        print(f"[success-variations] cases: {len(manifest['cases'])}")
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
