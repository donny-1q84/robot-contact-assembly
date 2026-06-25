#!/usr/bin/env python3
"""Dry-run V0 residual-policy feature extraction without training.

This is an offline schema and provenance gate. It reads the V0 scripted-skill
dataset, the dataset audit, and the residual-policy experiment plan, then builds
a compact feature preview from dataset manifest fields.
It does not train a policy, call Brev, start Isaac, call ROS, or talk to a robot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"
DEFAULT_DATASET_AUDIT = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_dataset_audit.json"
DEFAULT_EXPERIMENT_PLAN = REPO_ROOT / "artifacts" / "plans" / "v0_residual_policy_experiment_plan.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_feature_dry_run.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_feature_dry_run.md"
DEFAULT_NEGATIVE_CONTROL = "socket_x_pos_25mm_negative_control"
READY_EXPERIMENT_STATUS = "READY_FOR_LOCAL_POLICY_EXPERIMENT_DESIGN"

FEATURE_SCHEMA: list[dict[str, str]] = [
    {"name": "seed", "type": "float", "source": "dataset.cases[].seed"},
    {"name": "socket_delta_x_m", "type": "float", "source": "dataset.cases[].socket_delta_m[0]"},
    {"name": "socket_delta_y_m", "type": "float", "source": "dataset.cases[].socket_delta_m[1]"},
    {"name": "socket_delta_z_m", "type": "float", "source": "dataset.cases[].socket_delta_m[2]"},
    {"name": "socket_delta_norm_m", "type": "float", "source": "dataset.cases[].socket_delta_m"},
    {"name": "reset_joint_noise_rad", "type": "float", "source": "dataset.cases[].reset_joint_noise_rad"},
    {"name": "is_baseline_positive_control", "type": "float", "source": "dataset.cases[].case_id"},
    {"name": "best_lateral_m", "type": "float", "source": "dataset.cases[].metrics.best_lateral"},
    {"name": "best_axial_m", "type": "float", "source": "dataset.cases[].metrics.best_axial"},
    {"name": "best_rot_rad", "type": "float", "source": "dataset.cases[].metrics.best_rot"},
    {"name": "max_contact_force_n", "type": "float", "source": "dataset.cases[].metrics.max_contact_force"},
    {"name": "gate_peg_video_candidate", "type": "float", "source": "dataset.cases[].gates.peg_video_candidate"},
    {"name": "gate_final_contact_boundary", "type": "float", "source": "dataset.cases[].gates.final_contact_boundary"},
    {"name": "gate_trace_frame_alignment", "type": "float", "source": "dataset.cases[].gates.trace_frame_alignment"},
]


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


def _load_required(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"{label} is missing: {_rel(path)}")
        return {}
    return _load_json(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value: Any, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool_feature(value: Any) -> float:
    return 1.0 if bool(value) else 0.0


def _case_ids(dataset: dict[str, Any]) -> list[str]:
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        return []
    return [str(case.get("case_id")) for case in cases if isinstance(case, dict)]


def _same_repo_path(left: str | None, right: Path) -> bool:
    if not left:
        return False
    return _rel(_resolve(Path(left))) == _rel(right)


def _trace_check(case: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    case_id = str(case.get("case_id") or "<missing-case-id>")
    trace_value = case.get("trace_json")
    if not isinstance(trace_value, str) or not trace_value:
        return [f"{case_id}: trace_json must be a non-empty string"]
    trace_path = _resolve(Path(trace_value))
    if not trace_path.is_file():
        return [f"{case_id}: trace artifact is missing: {_rel(trace_path)}"]
    expected_sha = case.get("trace_sha256")
    if isinstance(expected_sha, str) and expected_sha:
        actual_sha = _sha256(trace_path)
        if actual_sha != expected_sha:
            failures.append(f"{case_id}: trace_sha256 mismatch: {actual_sha} != {expected_sha}")
    return failures


def _socket_delta(case: dict[str, Any]) -> tuple[list[float], list[str]]:
    case_id = str(case.get("case_id") or "<missing-case-id>")
    value = case.get("socket_delta_m")
    if not isinstance(value, list) or len(value) < 3:
        return [0.0, 0.0, 0.0], [f"{case_id}: socket_delta_m must contain at least 3 numbers"]
    delta: list[float] = []
    failures: list[str] = []
    for index in range(3):
        number = _number(value[index])
        if number is None:
            failures.append(f"{case_id}: socket_delta_m[{index}] is not numeric")
            delta.append(0.0)
        else:
            delta.append(number)
    return delta, failures


def _metric(metrics: dict[str, Any], key: str, case_id: str, failures: list[str]) -> float:
    value = _number(metrics.get(key))
    if value is None or not math.isfinite(value):
        failures.append(f"{case_id}: metrics.{key} must be a finite number")
        return 0.0
    return value


def _feature_record(case: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    case_id = str(case.get("case_id") or "<missing-case-id>")
    delta, delta_failures = _socket_delta(case)
    failures.extend(delta_failures)
    metrics = case.get("metrics") if isinstance(case.get("metrics"), dict) else {}
    gates = case.get("gates") if isinstance(case.get("gates"), dict) else {}
    seed = _number(case.get("seed"), default=-1.0)
    reset_noise = _number(case.get("reset_joint_noise_rad"), default=0.0)
    if seed is None or not math.isfinite(seed):
        failures.append(f"{case_id}: seed must be numeric or absent")
        seed = -1.0
    if reset_noise is None or not math.isfinite(reset_noise):
        failures.append(f"{case_id}: reset_joint_noise_rad must be numeric or absent")
        reset_noise = 0.0
    return {
        "case_id": case_id,
        "features": {
            "seed": seed,
            "socket_delta_x_m": delta[0],
            "socket_delta_y_m": delta[1],
            "socket_delta_z_m": delta[2],
            "socket_delta_norm_m": math.sqrt(sum(component * component for component in delta)),
            "reset_joint_noise_rad": reset_noise,
            "is_baseline_positive_control": 1.0 if case_id == "baseline_replay" else 0.0,
            "best_lateral_m": _metric(metrics, "best_lateral", case_id, failures),
            "best_axial_m": _metric(metrics, "best_axial", case_id, failures),
            "best_rot_rad": _metric(metrics, "best_rot", case_id, failures),
            "max_contact_force_n": _metric(metrics, "max_contact_force", case_id, failures),
            "gate_peg_video_candidate": _bool_feature(gates.get("peg_video_candidate")),
            "gate_final_contact_boundary": _bool_feature(gates.get("final_contact_boundary")),
            "gate_trace_frame_alignment": _bool_feature(gates.get("trace_frame_alignment")),
        },
        "target_status": "NOT_GENERATED",
    }


def build_dry_run(
    *,
    dataset_path: Path,
    dataset_audit_path: Path,
    experiment_plan_path: Path,
    min_cases: int,
    negative_control_id: str,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    dataset = _load_required(dataset_path, failures, "dataset manifest")
    dataset_audit = _load_required(dataset_audit_path, failures, "dataset audit")
    experiment_plan = _load_required(experiment_plan_path, failures, "policy experiment plan")

    if dataset and dataset.get("dataset_name") != "v0_scripted_skill_success_variations":
        failures.append(f"dataset_name must be v0_scripted_skill_success_variations, got {dataset.get('dataset_name')}")
    cases = dataset.get("cases") if isinstance(dataset.get("cases"), list) else []
    case_ids = _case_ids(dataset)
    if dataset and not isinstance(dataset.get("cases"), list):
        failures.append("dataset cases must be a list")
    if len(cases) < min_cases:
        failures.append(f"dataset case count {len(cases)} < required {min_cases}")
    if "baseline_replay" not in case_ids:
        failures.append("dataset must include baseline_replay positive control")
    if negative_control_id in case_ids:
        failures.append(f"dataset must exclude negative-control case {negative_control_id}")
    if len(case_ids) != len(set(case_ids)):
        failures.append("dataset case IDs must be unique")

    if dataset_audit:
        if dataset_audit.get("status") != "PASS":
            failures.append(f"dataset audit status must be PASS, got {dataset_audit.get('status')}")
        if dataset_audit.get("ready_for_training") is not False:
            failures.append("dataset audit must keep ready_for_training=false")
        audit_case_ids = dataset_audit.get("dataset_case_ids")
        if isinstance(audit_case_ids, list) and sorted(map(str, audit_case_ids)) != sorted(case_ids):
            failures.append("dataset audit case IDs do not match dataset case IDs")
        if dataset_audit.get("dataset") and not _same_repo_path(str(dataset_audit.get("dataset")), dataset_path):
            failures.append("dataset audit points at a different dataset path")

    if experiment_plan:
        if experiment_plan.get("status") != READY_EXPERIMENT_STATUS:
            failures.append(f"policy experiment plan must be {READY_EXPERIMENT_STATUS}, got {experiment_plan.get('status')}")
        if experiment_plan.get("ready_for_training") is not False:
            failures.append("policy experiment plan must keep ready_for_training=false")
        if experiment_plan.get("dataset") and not _same_repo_path(str(experiment_plan.get("dataset")), dataset_path):
            failures.append("policy experiment plan points at a different dataset path")
        forbidden = set(experiment_plan.get("experiment", {}).get("forbidden_outputs", []))
        if not {"raw_joint_targets", "direct_cartesian_servo_commands", "direct_force_commands"}.issubset(
            forbidden
        ):
            failures.append("policy experiment plan must preserve low-level command bans")

    feature_records: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            failures.append("dataset cases must be objects")
            continue
        case_id = str(case.get("case_id") or "<missing-case-id>")
        if case.get("classification") != "strict_success":
            failures.append(f"{case_id}: dataset case must be strict_success")
        if case.get("expected") == "fail_closed":
            failures.append(f"{case_id}: feature dry-run must not include fail_closed negative control")
        failures.extend(_trace_check(case))
        feature_records.append(_feature_record(case, failures))

    feature_names = [item["name"] for item in FEATURE_SCHEMA]
    target_schema = {
        "target_status": "NOT_GENERATED",
        "label_source": None,
        "forbidden_targets": [
            "raw_joint_targets",
            "direct_cartesian_servo_commands",
            "direct_force_commands",
            "language_to_raw_joint_control",
            "vlm_to_raw_joint_control",
        ],
    }
    status = "READY_FOR_FEATURE_EXTRACTION_REVIEW" if not failures else "BLOCKED"
    return {
        "dry_run_name": "v0_policy_feature_dry_run",
        "status": status,
        "ready_for_training": False,
        "dataset": _rel(dataset_path),
        "dataset_audit": _rel(dataset_audit_path),
        "policy_experiment_plan": _rel(experiment_plan_path),
        "sample_count": len(feature_records) if not failures else len(feature_records),
        "case_ids": case_ids,
        "feature_schema": FEATURE_SCHEMA,
        "feature_names": feature_names,
        "feature_count": len(feature_names),
        "sample_preview": feature_records[:3],
        "target_schema": target_schema,
        "required_before_training": [
            "manual review of this feature schema and sample preview",
            "explicit residual target design in the skill-controller action space",
            "separate no-GPU label-generation dry-run before any PyTorch training",
            "fixed budget, timeout, artifact plan, and cleanup plan before any paid Isaac evaluation",
        ],
        "blockers": failures,
        "warnings": warnings,
        "not_claims": [
            "not trained policy",
            "not evaluated policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a Brev or Isaac launcher",
        ],
    }


def _render_markdown(dry_run: dict[str, Any]) -> str:
    lines = [
        "# V0 Policy Feature Dry Run",
        "",
        f"- status: {dry_run['status']}",
        f"- ready_for_training: {dry_run['ready_for_training']}",
        f"- dataset: {dry_run['dataset']}",
        f"- dataset_audit: {dry_run['dataset_audit']}",
        f"- policy_experiment_plan: {dry_run['policy_experiment_plan']}",
        f"- sample_count: {dry_run['sample_count']}",
        f"- feature_count: {dry_run['feature_count']}",
        f"- target_status: {dry_run['target_schema']['target_status']}",
        "",
        "## Feature Schema",
        "",
    ]
    lines.extend(f"- {item['name']}: {item['source']}" for item in dry_run["feature_schema"])
    lines.extend(["", "## Sample Preview", ""])
    for sample in dry_run["sample_preview"]:
        lines.append(f"- {sample['case_id']}: {json.dumps(sample['features'], sort_keys=True)}")
    lines.extend(["", "## Required Before Training", ""])
    lines.extend(f"- {item}" for item in dry_run["required_before_training"])
    if dry_run["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in dry_run["blockers"])
    if dry_run["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in dry_run["warnings"])
    lines.extend(["", "## Not Claims", ""])
    lines.extend(f"- {item}" for item in dry_run["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--dataset-audit", type=Path, default=DEFAULT_DATASET_AUDIT)
    parser.add_argument("--policy-experiment-plan", type=Path, default=DEFAULT_EXPERIMENT_PLAN)
    parser.add_argument("--min-cases", type=int, default=5)
    parser.add_argument("--negative-control-id", default=DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    dry_run = build_dry_run(
        dataset_path=_resolve(args.dataset),
        dataset_audit_path=_resolve(args.dataset_audit),
        experiment_plan_path=_resolve(args.policy_experiment_plan),
        min_cases=max(1, args.min_cases),
        negative_control_id=args.negative_control_id,
    )
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(dry_run, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-policy-feature-dry-run] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(dry_run), encoding="utf-8")
        print(f"[v0-policy-feature-dry-run] wrote Markdown: {_rel(output_md)}")

    print("[v0-policy-feature-dry-run] facts=" + json.dumps(dry_run, indent=2, sort_keys=True))
    print("[v0-policy-feature-dry-run] status=" + dry_run["status"])
    if dry_run["status"] != "BLOCKED":
        return 0
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
