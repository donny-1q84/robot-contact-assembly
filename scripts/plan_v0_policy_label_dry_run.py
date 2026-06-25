#!/usr/bin/env python3
"""Dry-run V0 residual-policy label generation without training.

This is an offline preview gate after label-source review. It builds a bounded
set of residual target previews from allowed skill-controller fields only, while
recording raw joint/action fields as excluded evidence.
It does not train a policy, write a checkpoint, call Brev, start Isaac, call ROS, or talk to a robot.
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
DEFAULT_FEATURE_DRY_RUN = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_feature_dry_run.json"
DEFAULT_LABEL_SOURCE_AUDIT = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_source_audit.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_dry_run.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_dry_run.md"
DEFAULT_NEGATIVE_CONTROL = "socket_x_pos_25mm_negative_control"
READY_FEATURE_STATUS = "READY_FOR_FEATURE_EXTRACTION_REVIEW"
READY_LABEL_SOURCE_STATUS = "READY_FOR_LABEL_SOURCE_REVIEW"
READY_STATUS = "READY_FOR_LABEL_DRY_RUN_REVIEW"

LABEL_SCHEMA: list[dict[str, str]] = [
    {
        "name": "residual_socket_offset_x_m",
        "source": "steps[].socket_insertion_servo_offset_socket[0]",
        "boundary": "skill_controller_task_parameter_residual",
    },
    {
        "name": "residual_socket_offset_y_m",
        "source": "steps[].socket_insertion_servo_offset_socket[1]",
        "boundary": "skill_controller_task_parameter_residual",
    },
    {
        "name": "residual_socket_offset_z_m",
        "source": "steps[].socket_insertion_servo_offset_socket[2]",
        "boundary": "skill_controller_task_parameter_residual",
    },
    {
        "name": "residual_preload_step_m",
        "source": "steps[].socket_insertion_servo_contact_preload_step",
        "boundary": "skill_controller_task_parameter_residual",
    },
    {
        "name": "residual_boundary_step_m",
        "source": "steps[].socket_insertion_servo_contact_boundary_step",
        "boundary": "skill_controller_task_parameter_residual",
    },
    {
        "name": "residual_descent_step_m",
        "source": "steps[].socket_insertion_servo_z_step",
        "boundary": "skill_controller_task_parameter_residual",
    },
    {
        "name": "residual_rotation_step_rad",
        "source": "steps[].socket_insertion_servo_rot_step",
        "boundary": "skill_controller_task_parameter_residual",
    },
]

FORBIDDEN_TRACE_FIELDS = {
    "raw_action",
    "joint_pos_des",
    "joint_pos_des_raw",
    "joint_response_delta",
    "action_pos_w",
    "action_quat_w",
    "command_pos_w",
    "command_quat_w",
    "insert_contact_force_socket",
}


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


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _vector3(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) < 3:
        return None
    parsed = [_number(value[index]) for index in range(3)]
    if any(component is None for component in parsed):
        return None
    return [float(component) for component in parsed if component is not None]


def _same_repo_path(left: str | None, right: Path) -> bool:
    if not left:
        return False
    return _rel(_resolve(Path(left))) == _rel(right)


def _negative_control_failure(prefix: str, evidence: dict[str, Any], *, negative_control_id: str) -> str | None:
    if not evidence:
        return f"{prefix} must preserve negative_control_evidence"
    if evidence.get("case_id") != negative_control_id:
        return (
            f"{prefix} negative_control_evidence.case_id must be {negative_control_id}, "
            f"got {evidence.get('case_id')}"
        )
    if evidence.get("expected") != "fail_closed":
        return f"{prefix} negative_control_evidence.expected must be fail_closed, got {evidence.get('expected')}"
    if evidence.get("classification") != "fail_closed":
        return (
            f"{prefix} negative_control_evidence.classification must be fail_closed, "
            f"got {evidence.get('classification')}"
        )
    if evidence.get("excluded_from_training_cases") is not True:
        return f"{prefix} negative_control_evidence must preserve excluded_from_training_cases=true"
    if not isinstance(evidence.get("trace_sha256"), str) or not evidence.get("trace_sha256"):
        return f"{prefix} negative_control_evidence must preserve trace_sha256"
    return None


def _negative_trace_sha(evidence: dict[str, Any]) -> str | None:
    value = evidence.get("trace_sha256")
    return value if isinstance(value, str) and value else None


def _dataset_cases(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict)]


def _label_from_step(step: dict[str, Any]) -> dict[str, float] | None:
    offset = _vector3(step.get("socket_insertion_servo_offset_socket"))
    preload = _number(step.get("socket_insertion_servo_contact_preload_step"))
    boundary = _number(step.get("socket_insertion_servo_contact_boundary_step"))
    descent = _number(step.get("socket_insertion_servo_z_step"))
    rotation = _number(step.get("socket_insertion_servo_rot_step"))
    if offset is None or preload is None or boundary is None or descent is None or rotation is None:
        return None
    return {
        "residual_socket_offset_x_m": offset[0],
        "residual_socket_offset_y_m": offset[1],
        "residual_socket_offset_z_m": offset[2],
        "residual_preload_step_m": preload,
        "residual_boundary_step_m": boundary,
        "residual_descent_step_m": descent,
        "residual_rotation_step_rad": rotation,
    }


def _outcome(step: dict[str, Any]) -> dict[str, Any] | None:
    lateral = _number(step.get("lateral"))
    axial = _number(step.get("axial"))
    rot = _number(step.get("rot"))
    contact = _number(step.get("contact_force_magnitude"))
    if lateral is None or axial is None or rot is None or contact is None or not isinstance(step.get("success"), bool):
        return None
    return {
        "lateral_m": lateral,
        "axial_m": axial,
        "rot_rad": rot,
        "contact_force_n": contact,
        "success": step.get("success"),
    }


def _trace_payload(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not isinstance(payload.get("steps"), list):
        raise RuntimeError(f"trace JSON must contain a steps list: {_rel(path)}")
    return payload


def _candidate_label_samples(
    *,
    case_id: str,
    trace_path: Path,
    max_samples_per_case: int,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    trace = _trace_payload(trace_path)
    candidates: list[dict[str, Any]] = []
    forbidden_seen: set[str] = set()
    for step in trace["steps"]:
        if not isinstance(step, dict):
            continue
        forbidden_seen.update(FORBIDDEN_TRACE_FIELDS.intersection(step.keys()))
        if step.get("phase") != "socket-insertion-servo":
            continue
        label = _label_from_step(step)
        outcome = _outcome(step)
        if label is None or outcome is None:
            continue
        candidates.append(
            {
                "case_id": case_id,
                "step": step.get("step"),
                "labels": label,
                "outcome": outcome,
                "label_source_fields": [item["source"] for item in LABEL_SCHEMA],
                "excluded_low_level_fields_present": sorted(forbidden_seen.intersection(step.keys())),
            }
        )
    return candidates[:max_samples_per_case], len(candidates), sorted(forbidden_seen)


def build_dry_run(
    *,
    dataset_path: Path,
    feature_dry_run_path: Path,
    label_source_audit_path: Path,
    min_cases: int,
    max_samples_per_case: int,
    negative_control_id: str,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    dataset = _load_required(dataset_path, failures, "dataset manifest")
    feature_dry_run = _load_required(feature_dry_run_path, failures, "policy feature dry-run")
    label_source_audit = _load_required(label_source_audit_path, failures, "policy label-source audit")

    cases = _dataset_cases(dataset)
    case_ids = [str(case.get("case_id")) for case in cases]
    dataset_negative = dataset.get("negative_control_evidence") if isinstance(dataset.get("negative_control_evidence"), dict) else {}
    feature_negative = (
        feature_dry_run.get("negative_control_evidence")
        if isinstance(feature_dry_run.get("negative_control_evidence"), dict)
        else {}
    )
    label_source_negative = (
        label_source_audit.get("negative_control_evidence")
        if isinstance(label_source_audit.get("negative_control_evidence"), dict)
        else {}
    )
    if dataset and dataset.get("dataset_name") != "v0_scripted_skill_success_variations":
        failures.append(f"dataset_name must be v0_scripted_skill_success_variations, got {dataset.get('dataset_name')}")
    if len(cases) < min_cases:
        failures.append(f"dataset case count {len(cases)} < required {min_cases}")
    if "baseline_replay" not in case_ids:
        failures.append("dataset must include baseline_replay positive control")
    if "socket_x_pos_25mm_negative_control" in case_ids:
        failures.append("label dry-run must not include the fail_closed negative control")
    dataset_negative_failure = _negative_control_failure(
        "dataset", dataset_negative, negative_control_id=negative_control_id
    )
    if dataset_negative_failure:
        failures.append(dataset_negative_failure)

    if feature_dry_run:
        if feature_dry_run.get("status") != READY_FEATURE_STATUS:
            failures.append(f"feature dry-run status must be {READY_FEATURE_STATUS}, got {feature_dry_run.get('status')}")
        if feature_dry_run.get("ready_for_training") is not False:
            failures.append("feature dry-run must keep ready_for_training=false")
        if feature_dry_run.get("dataset") and not _same_repo_path(str(feature_dry_run.get("dataset")), dataset_path):
            failures.append("feature dry-run points at a different dataset path")
        feature_negative_failure = _negative_control_failure(
            "policy feature dry-run", feature_negative, negative_control_id=negative_control_id
        )
        if feature_negative_failure:
            failures.append(feature_negative_failure)
        if _negative_trace_sha(dataset_negative) and _negative_trace_sha(feature_negative):
            if _negative_trace_sha(dataset_negative) != _negative_trace_sha(feature_negative):
                failures.append("policy feature dry-run negative_control_evidence.trace_sha256 must match dataset")

    if label_source_audit:
        if label_source_audit.get("status") != READY_LABEL_SOURCE_STATUS:
            failures.append(
                f"label-source audit status must be {READY_LABEL_SOURCE_STATUS}, got {label_source_audit.get('status')}"
            )
        if label_source_audit.get("ready_for_training") is not False:
            failures.append("label-source audit must keep ready_for_training=false")
        if label_source_audit.get("target_generation_status") != "DESIGN_ONLY":
            failures.append("label-source audit must be DESIGN_ONLY before the dry-run")
        if label_source_audit.get("dataset") and not _same_repo_path(str(label_source_audit.get("dataset")), dataset_path):
            failures.append("label-source audit points at a different dataset path")
        label_source_negative_failure = _negative_control_failure(
            "policy label-source audit", label_source_negative, negative_control_id=negative_control_id
        )
        if label_source_negative_failure:
            failures.append(label_source_negative_failure)
        if _negative_trace_sha(dataset_negative) and _negative_trace_sha(label_source_negative):
            if _negative_trace_sha(dataset_negative) != _negative_trace_sha(label_source_negative):
                failures.append("policy label-source audit negative_control_evidence.trace_sha256 must match dataset")

    label_names = [item["name"] for item in LABEL_SCHEMA]
    for name in label_names:
        lowered = name.lower()
        if "raw_joint" in lowered or "joint_pos" in lowered or "cartesian_servo" in lowered or "force_command" in lowered:
            failures.append(f"label channel crosses forbidden low-level boundary: {name}")

    max_samples = max(1, max_samples_per_case)
    sample_preview: list[dict[str, Any]] = []
    case_reports: list[dict[str, Any]] = []
    total_candidate_count = 0
    for case in cases:
        case_id = str(case.get("case_id") or "<missing-case-id>")
        if case.get("classification") != "strict_success":
            failures.append(f"{case_id}: dataset case must be strict_success")
        trace_value = case.get("trace_json")
        if not isinstance(trace_value, str) or not trace_value:
            failures.append(f"{case_id}: trace_json must be a non-empty string")
            continue
        trace_path = _resolve(Path(trace_value))
        if not trace_path.is_file():
            failures.append(f"{case_id}: trace artifact is missing: {_rel(trace_path)}")
            continue
        expected_sha = case.get("trace_sha256")
        if isinstance(expected_sha, str) and expected_sha and _sha256(trace_path) != expected_sha:
            failures.append(f"{case_id}: trace_sha256 mismatch")
            continue
        try:
            samples, candidate_count, forbidden_seen = _candidate_label_samples(
                case_id=case_id,
                trace_path=trace_path,
                max_samples_per_case=max_samples,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed per case.
            failures.append(f"{case_id}: label dry-run failed: {exc}")
            continue
        if candidate_count == 0:
            failures.append(f"{case_id}: no allowed residual label source windows found")
        total_candidate_count += candidate_count
        sample_preview.extend(samples)
        case_reports.append(
            {
                "case_id": case_id,
                "trace_json": _rel(trace_path),
                "candidate_label_window_count": candidate_count,
                "preview_sample_count": len(samples),
                "forbidden_trace_fields_present_but_excluded": forbidden_seen,
            }
        )

    status = READY_STATUS if not failures else "BLOCKED"
    return {
        "dry_run_name": "v0_policy_label_dry_run",
        "status": status,
        "ready_for_training": False,
        "label_generation_status": "DRY_RUN_PREVIEW_ONLY",
        "dataset": _rel(dataset_path),
        "policy_feature_dry_run": _rel(feature_dry_run_path),
        "policy_label_source_audit": _rel(label_source_audit_path),
        "dataset_case_count": len(cases),
        "case_ids": case_ids,
        "negative_control_evidence": dataset_negative or label_source_negative or feature_negative,
        "label_schema": LABEL_SCHEMA,
        "label_names": label_names,
        "candidate_label_window_count": total_candidate_count,
        "sample_preview_count": len(sample_preview),
        "sample_preview": sample_preview,
        "case_reports": case_reports,
        "required_before_training": [
            "manual review of label dry-run samples and label magnitudes",
            "full no-GPU label dataset extraction with checksum manifest",
            "negative-control fail-closed evidence remains outside label samples",
            "explicit PyTorch environment and budget plan before training",
        ],
        "blockers": failures,
        "warnings": warnings,
        "not_claims": [
            "not full label dataset",
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
        "# V0 Policy Label Dry Run",
        "",
        f"- status: {dry_run['status']}",
        f"- ready_for_training: {dry_run['ready_for_training']}",
        f"- label_generation_status: {dry_run['label_generation_status']}",
        f"- dataset: {dry_run['dataset']}",
        f"- policy_feature_dry_run: {dry_run['policy_feature_dry_run']}",
        f"- policy_label_source_audit: {dry_run['policy_label_source_audit']}",
        f"- candidate_label_window_count: {dry_run['candidate_label_window_count']}",
        f"- sample_preview_count: {dry_run['sample_preview_count']}",
        "",
        "## Negative Control Evidence",
        "",
        f"- case_id: {dry_run.get('negative_control_evidence', {}).get('case_id')}",
        f"- expected: {dry_run.get('negative_control_evidence', {}).get('expected')}",
        f"- classification: {dry_run.get('negative_control_evidence', {}).get('classification')}",
        f"- excluded_from_training_cases: {dry_run.get('negative_control_evidence', {}).get('excluded_from_training_cases')}",
        "",
        "## Label Schema",
        "",
    ]
    lines.extend(f"- {item['name']}: {item['source']}" for item in dry_run["label_schema"])
    lines.extend(["", "## Sample Preview", ""])
    for sample in dry_run["sample_preview"][:10]:
        lines.append(f"- {sample['case_id']} step {sample['step']}: {json.dumps(sample['labels'], sort_keys=True)}")
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
    parser.add_argument("--policy-feature-dry-run", type=Path, default=DEFAULT_FEATURE_DRY_RUN)
    parser.add_argument("--policy-label-source-audit", type=Path, default=DEFAULT_LABEL_SOURCE_AUDIT)
    parser.add_argument("--min-cases", type=int, default=5)
    parser.add_argument("--max-samples-per-case", type=int, default=5)
    parser.add_argument("--negative-control-id", default=DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    dry_run = build_dry_run(
        dataset_path=_resolve(args.dataset),
        feature_dry_run_path=_resolve(args.policy_feature_dry_run),
        label_source_audit_path=_resolve(args.policy_label_source_audit),
        min_cases=max(1, args.min_cases),
        max_samples_per_case=max(1, args.max_samples_per_case),
        negative_control_id=args.negative_control_id,
    )
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(dry_run, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-policy-label-dry-run] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(dry_run), encoding="utf-8")
        print(f"[v0-policy-label-dry-run] wrote Markdown: {_rel(output_md)}")

    print("[v0-policy-label-dry-run] facts=" + json.dumps(dry_run, indent=2, sort_keys=True))
    print("[v0-policy-label-dry-run] status=" + dry_run["status"])
    if dry_run["status"] != "BLOCKED":
        return 0
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
