#!/usr/bin/env python3
"""Classify successful-trace variation results from a manifest.

This is an offline evidence reducer. It reads planned variation cases and any
available trace artifacts, then labels each case as strict_success,
near_success, fail_closed, or missing. It does not run Isaac or create paid
compute resources.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_trace_frame_alignment as frame_audit  # noqa: E402
import check_final_contact_boundary_diagnostic as boundary_gate  # noqa: E402
import check_peg_in_hole_video_candidate as video_gate  # noqa: E402


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _resolve_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root must be an object: {_rel(path)}")
    return payload


def _trace_candidates(
    case: dict[str, Any],
    *,
    results_root: Path | None,
) -> list[Path]:
    candidates: list[Path] = []
    for key in ("trace_json", "result_trace_json"):
        path = _resolve_path(case.get(key) if isinstance(case.get(key), str) else None)
        if path is not None:
            candidates.append(path)
    case_id = case.get("case_id")
    if results_root is not None and isinstance(case_id, str):
        candidates.append(results_root / case_id / "video_trace.json")
    planned = _resolve_path(case.get("planned_trace_json") if isinstance(case.get("planned_trace_json"), str) else None)
    if planned is not None:
        candidates.append(planned)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped


def _first_existing_trace(
    case: dict[str, Any],
    *,
    results_root: Path | None,
) -> Path | None:
    for path in _trace_candidates(case, results_root=results_root):
        if path.is_file():
            return path
    return None


def _evaluate_video(trace: dict[str, Any]) -> dict[str, Any]:
    constants = video_gate._load_constants()
    return video_gate.evaluate_trace(
        trace,
        strict_lateral_tol=constants["socket_guide_clearance"],
        task_lateral_tol=constants["success_xy_tolerance"],
        axial_tol=constants["success_z_tolerance"],
        rot_tol=constants["success_rot_tolerance"],
        sustained_steps=5,
        min_visible_descent=0.030,
        min_start_axial=0.035,
        min_contact_force=0.5,
    )


def _evaluate_boundary(trace: dict[str, Any]) -> dict[str, Any]:
    constants = boundary_gate._load_constants()
    return boundary_gate.evaluate_trace(
        trace,
        xy_tol=constants["success_xy_tolerance"],
        axial_tol=constants["success_z_tolerance"],
        rot_tol=constants["success_rot_tolerance"],
        contact_min_force=0.5,
        boundary_contact_min_force=0.25,
        boundary_axial_band=0.001,
        max_boundary_step=0.00015,
        pop_lateral_jump=0.010,
        pop_lateral_abs=0.020,
        pop_axial_regress=0.004,
        sustained_steps=5,
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _near_success(metrics: dict[str, Any], thresholds: dict[str, Any]) -> tuple[bool, list[str]]:
    checks = [
        ("best_lateral", "best_lateral_max_m", lambda value, threshold: value <= threshold),
        ("best_axial", "best_axial_max_m", lambda value, threshold: value <= threshold),
        ("best_rot", "best_rot_max_rad", lambda value, threshold: value <= threshold),
        ("max_contact_force", "max_contact_force_min_n", lambda value, threshold: value >= threshold),
    ]
    failures: list[str] = []
    for metric_key, threshold_key, predicate in checks:
        value = _float_or_none(metrics.get(metric_key))
        threshold = _float_or_none(thresholds.get(threshold_key))
        if value is None or threshold is None:
            failures.append(f"{metric_key} or {threshold_key} missing")
            continue
        if not predicate(value, threshold):
            failures.append(f"{metric_key}={value} outside {threshold_key}={threshold}")
    return not failures, failures


def classify_case(
    case: dict[str, Any],
    *,
    thresholds: dict[str, Any],
    results_root: Path | None,
) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "<missing-case-id>")
    case_metadata = {
        "socket_delta_m": case.get("socket_delta_m"),
        "reset_joint_noise_rad": case.get("reset_joint_noise_rad"),
        "status": case.get("status"),
        "rationale": case.get("rationale"),
    }
    trace_path = _first_existing_trace(case, results_root=results_root)
    if trace_path is None:
        return {
            "case_id": case_id,
            "expected": case.get("expected"),
            "classification": "missing",
            "trace_json": None,
            "failure_reasons": ["trace artifact is missing"],
            **case_metadata,
        }

    try:
        trace = _load_json(trace_path)
        video = _evaluate_video(trace)
        boundary = _evaluate_boundary(trace)
        frame_report, frame_failures = frame_audit.audit_trace(trace_path)
    except Exception as exc:  # noqa: BLE001 - keep batch classifier fail-closed per case.
        return {
            "case_id": case_id,
            "expected": case.get("expected"),
            "classification": "fail_closed",
            "trace_json": _rel(trace_path),
            "failure_reasons": [f"trace evaluation failed: {exc}"],
            **case_metadata,
        }

    strict_success = bool(
        video.get("video_candidate_pass")
        and boundary.get("pass_gate")
        and not frame_failures
    )
    metrics = video.get("metrics") if isinstance(video.get("metrics"), dict) else {}
    near_success, near_failures = _near_success(metrics, thresholds)
    if strict_success:
        classification = "strict_success"
    elif near_success:
        classification = "near_success"
    else:
        classification = "fail_closed"

    failure_reasons: list[str] = []
    if not video.get("video_candidate_pass"):
        failure_reasons.extend(str(reason) for reason in video.get("failure_reasons", []))
    if not boundary.get("pass_gate"):
        failure_reasons.extend(str(reason) for reason in boundary.get("failure_reasons", []))
    failure_reasons.extend(str(reason) for reason in frame_failures)
    if classification == "fail_closed":
        failure_reasons.extend(near_failures)

    return {
        "case_id": case_id,
        "expected": case.get("expected"),
        "classification": classification,
        "trace_json": _rel(trace_path),
        **case_metadata,
        "strict_success": strict_success,
        "near_success": near_success,
        "gates": {
            "peg_video_candidate": bool(video.get("video_candidate_pass")),
            "final_contact_boundary": bool(boundary.get("pass_gate")),
            "trace_frame_alignment": not frame_failures,
        },
        "metrics": metrics,
        "boundary": {
            "first_sustained_success_step": boundary.get("first_sustained_success_step"),
            "unsafe_boundary_descent_count": boundary.get("unsafe_boundary_descent_count"),
            "pop_event_count": boundary.get("pop_event_count"),
        },
        "frame_audit": {
            "failures": frame_failures,
            "step_count": frame_report.get("step_count"),
            "post_metric_world_to_physical_tip_gap_mean": frame_report.get(
                "post_metric_world_to_physical_tip_gap_mean"
            ),
        },
        "failure_reasons": failure_reasons,
    }


def build_report(manifest: dict[str, Any], *, results_root: Path | None) -> dict[str, Any]:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("manifest must contain a cases list")
    thresholds = manifest.get("near_success_thresholds")
    if not isinstance(thresholds, dict):
        raise RuntimeError("manifest must contain near_success_thresholds")
    results = [
        classify_case(case, thresholds=thresholds, results_root=results_root)
        for case in cases
        if isinstance(case, dict)
    ]
    counts = Counter(str(result["classification"]) for result in results)
    return {
        "manifest": {
            "purpose": manifest.get("purpose"),
            "created_utc": manifest.get("created_utc"),
            "source_trace_json": manifest.get("source_trace_json"),
            "source_trace_sha256": manifest.get("source_trace_sha256"),
        },
        "summary": {
            "case_count": len(results),
            "strict_success_count": counts.get("strict_success", 0),
            "near_success_count": counts.get("near_success", 0),
            "fail_closed_count": counts.get("fail_closed", 0),
            "missing_count": counts.get("missing", 0),
            "classification_counts": dict(sorted(counts.items())),
        },
        "results": results,
    }


def _format_float(value: Any) -> str:
    parsed = _float_or_none(value)
    if parsed is None:
        return "-"
    return f"{parsed:.6g}"


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    rows = [
        "# Success Trace Variation Classification",
        "",
        f"- case_count: {summary['case_count']}",
        f"- strict_success_count: {summary['strict_success_count']}",
        f"- near_success_count: {summary['near_success_count']}",
        f"- fail_closed_count: {summary['fail_closed_count']}",
        f"- missing_count: {summary['missing_count']}",
        "",
        "| case | expected | classification | trace | best_lateral | best_axial | best_rot | max_contact |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for result in report["results"]:
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        rows.append(
            "| {case} | {expected} | {classification} | {trace} | {lateral} | {axial} | {rot} | {contact} |".format(
                case=result.get("case_id"),
                expected=result.get("expected"),
                classification=result.get("classification"),
                trace=result.get("trace_json") or "-",
                lateral=_format_float(metrics.get("best_lateral")),
                axial=_format_float(metrics.get("best_axial")),
                rot=_format_float(metrics.get("best_rot")),
                contact=_format_float(metrics.get("max_contact_force")),
            )
        )
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--json", action="store_true", help="Print the report JSON to stdout.")
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    results_root = args.results_root.resolve() if args.results_root is not None else None
    report = build_report(manifest, results_root=results_root)

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[success-variation-classifier] wrote JSON: {_rel(args.output_json)}")
    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(render_markdown(report), encoding="utf-8")
        print(f"[success-variation-classifier] wrote Markdown: {_rel(args.output_md)}")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))

    summary = report["summary"]
    print(
        "[success-variation-classifier] "
        f"cases={summary['case_count']} "
        f"strict_success={summary['strict_success_count']} "
        f"near_success={summary['near_success_count']} "
        f"fail_closed={summary['fail_closed_count']} "
        f"missing={summary['missing_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
