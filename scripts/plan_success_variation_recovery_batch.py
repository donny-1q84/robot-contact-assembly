#!/usr/bin/env python3
"""Plan a success-variation recovery batch from current classified traces.

This is an offline helper for partial paid runs. It classifies the manifest,
uses a "skip cases that already satisfy the promotion contract" rule, and emits
a smaller rerun plan only for missing or failed non-negative cases plus missing
negative controls. It does not create Brev instances, run Isaac, or mutate the
manifest.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import classify_success_variation_results as classifier  # noqa: E402
import plan_success_variation_batch as batch_planner  # noqa: E402


DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "success_trace_variation_recovery_plan_2026-06-25.json"
DEFAULT_OUTPUT_SH = REPO_ROOT / "artifacts" / "analysis" / "success_trace_variation_recovery_plan_2026-06-25.sh"
DEFAULT_NEGATIVE_CONTROL = "socket_x_pos_25mm_negative_control"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _resolve(path: Path) -> Path:
    path = path.expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root must be an object: {_rel(path)}")
    return payload


def _case_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("manifest must contain cases list")
    mapped: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        if isinstance(case_id, str):
            mapped[case_id] = case
    return mapped


def _recovery_decision(result: dict[str, Any], *, negative_control_id: str) -> tuple[str, str]:
    case_id = str(result.get("case_id") or "")
    classification = str(result.get("classification") or "")
    expected = result.get("expected")
    if case_id == "baseline_replay":
        if classification == "strict_success":
            return "satisfied", "baseline positive control is already strict_success"
        return "blocked", "baseline positive control is no longer strict_success"

    if case_id == negative_control_id or expected == "fail_closed":
        if classification == "fail_closed":
            return "satisfied", "negative control already fails closed"
        if classification == "missing":
            return "rerun", "negative control trace is missing"
        return "blocked", f"negative control classified {classification}, expected fail_closed"

    if classification == "strict_success":
        return "satisfied", "non-negative variation is already strict_success"
    if classification == "missing":
        return "rerun", "trace artifact is missing"
    if classification in {"fail_closed", "near_success"}:
        return "rerun", f"non-negative variation classified {classification}"
    return "blocked", f"unknown classification: {classification}"


def build_recovery(
    manifest: dict[str, Any],
    *,
    results_root: Path | None,
    negative_control_id: str,
    env_name: str,
    remote_root: str,
    compose_root: str,
    task: str | None,
    steps: int,
) -> dict[str, Any]:
    classification = classifier.build_report(manifest, results_root=results_root)
    cases_by_id = _case_map(manifest)
    rerun_cases: list[dict[str, Any]] = []
    satisfied_cases: list[dict[str, Any]] = []
    blocked_cases: list[dict[str, Any]] = []

    for result in classification.get("results", []):
        if not isinstance(result, dict):
            continue
        case_id = str(result.get("case_id") or "")
        decision, reason = _recovery_decision(result, negative_control_id=negative_control_id)
        record = {
            "case_id": case_id,
            "expected": result.get("expected"),
            "classification": result.get("classification"),
            "trace_json": result.get("trace_json"),
            "decision": decision,
            "reason": reason,
        }
        if decision == "rerun":
            case = cases_by_id.get(case_id)
            if case is None:
                blocked_cases.append({**record, "decision": "blocked", "reason": "case is not in manifest"})
            else:
                rerun_cases.append(case)
        elif decision == "satisfied":
            satisfied_cases.append(record)
        else:
            blocked_cases.append(record)

    recovery_manifest = dict(manifest)
    recovery_manifest["cases"] = rerun_cases
    plan = batch_planner.build_plan(
        recovery_manifest,
        env_name=env_name,
        remote_root=remote_root,
        compose_root=compose_root,
        task=task,
        steps=max(1, steps),
        include_available=True,
    )
    status = "BLOCKED" if blocked_cases else ("READY" if rerun_cases else "NOTHING_TO_RERUN")
    return {
        "status": status,
        "manifest_created_utc": manifest.get("created_utc"),
        "source_trace_json": manifest.get("source_trace_json"),
        "classification_summary": classification.get("summary"),
        "rerun_case_count": len(rerun_cases),
        "satisfied_case_count": len(satisfied_cases),
        "blocked_case_count": len(blocked_cases),
        "rerun_case_ids": [case.get("case_id") for case in rerun_cases],
        "satisfied_cases": satisfied_cases,
        "blocked_cases": blocked_cases,
        "plan": plan,
        "not_claims": [
            "not a paid-run launcher",
            "not evidence that recovery cases will pass",
            "not a dataset or policy promotion gate",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--negative-control-id", default=DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--env-name", default="isaac-l40s")
    parser.add_argument("--remote-root", default="/home/ubuntu/projects/robot-contact-assembly")
    parser.add_argument("--compose-root", default="/home/ubuntu/isaac-compose")
    parser.add_argument("--task")
    parser.add_argument("--steps", type=int, default=220)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-sh", type=Path, default=DEFAULT_OUTPUT_SH)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    manifest_path = _resolve(args.manifest)
    results_root = _resolve(args.results_root) if args.results_root is not None else None
    recovery = build_recovery(
        _load_json(manifest_path),
        results_root=results_root,
        negative_control_id=args.negative_control_id,
        env_name=args.env_name,
        remote_root=args.remote_root,
        compose_root=args.compose_root,
        task=args.task,
        steps=args.steps,
    )

    if args.output_json is not None:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(recovery, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[success-variation-recovery] wrote JSON: {_rel(output_json)}")
    if args.output_sh is not None:
        output_sh = _resolve(args.output_sh)
        output_sh.parent.mkdir(parents=True, exist_ok=True)
        output_sh.write_text(batch_planner.render_shell(recovery["plan"]), encoding="utf-8")
        print(f"[success-variation-recovery] wrote shell: {_rel(output_sh)}")

    print("[success-variation-recovery] status=" + recovery["status"])
    print("[success-variation-recovery] rerun_cases=" + ",".join(recovery["rerun_case_ids"]))
    print("[success-variation-recovery] blocked_case_count=" + str(recovery["blocked_case_count"]))
    if args.fail_on_blocked and recovery["status"] == "BLOCKED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
