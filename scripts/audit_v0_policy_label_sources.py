#!/usr/bin/env python3
"""Audit V0 residual-policy label sources without generating labels.

This is an offline target-source gate after the feature dry-run. It verifies
that strict-success traces contain allowed skill-controller fields for a future
residual-target dry-run, and that raw joint or direct Cartesian/force command
fields remain excluded from target design. It does not train a policy, generate
labels, call Brev, start Isaac, call ROS, or talk to a robot.
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
DEFAULT_EXPERIMENT_PLAN = REPO_ROOT / "artifacts" / "plans" / "v0_residual_policy_experiment_plan.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_source_audit.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_source_audit.md"
READY_FEATURE_STATUS = "READY_FOR_FEATURE_EXTRACTION_REVIEW"
READY_EXPERIMENT_STATUS = "READY_FOR_LOCAL_POLICY_EXPERIMENT_DESIGN"
READY_STATUS = "READY_FOR_LABEL_SOURCE_REVIEW"

TARGET_CHANNEL_SCHEMA: list[dict[str, str]] = [
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
    vector = [_number(value[index]) for index in range(3)]
    if any(component is None for component in vector):
        return None
    return [float(component) for component in vector if component is not None]


def _same_repo_path(left: str | None, right: Path) -> bool:
    if not left:
        return False
    return _rel(_resolve(Path(left))) == _rel(right)


def _trace_payload(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if "steps" in payload or "summary" in payload:
        return payload
    raise RuntimeError(f"trace JSON must contain steps and summary: {_rel(path)}")


def _target_preview(step: dict[str, Any]) -> dict[str, float] | None:
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


def _outcome_fields_ready(step: dict[str, Any]) -> bool:
    for key in ("lateral", "axial", "rot", "contact_force_magnitude"):
        if _number(step.get(key)) is None:
            return False
    return isinstance(step.get("success"), bool)


def _audit_trace(trace_path: Path, *, min_label_source_steps: int) -> dict[str, Any]:
    payload = _trace_payload(trace_path)
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise RuntimeError(f"trace steps must be a list: {_rel(trace_path)}")
    ready_steps: list[dict[str, Any]] = []
    forbidden_present: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        forbidden_present.update(FORBIDDEN_TRACE_FIELDS.intersection(step.keys()))
        if step.get("phase") != "socket-insertion-servo":
            continue
        preview = _target_preview(step)
        if preview is None or not _outcome_fields_ready(step):
            continue
        ready_steps.append(
            {
                "step": step.get("step"),
                "target_preview": preview,
                "outcome_preview": {
                    "lateral": step.get("lateral"),
                    "axial": step.get("axial"),
                    "rot": step.get("rot"),
                    "contact_force_magnitude": step.get("contact_force_magnitude"),
                    "success": step.get("success"),
                },
            }
        )
    return {
        "trace_json": _rel(trace_path),
        "step_count": len(steps),
        "label_source_step_count": len(ready_steps),
        "first_label_source_step": ready_steps[0] if ready_steps else None,
        "min_label_source_steps": min_label_source_steps,
        "forbidden_trace_fields_present_but_excluded": sorted(forbidden_present),
        "pass": len(ready_steps) >= min_label_source_steps,
    }


def _dataset_cases(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        return []
    return [case for case in cases if isinstance(case, dict)]


def build_audit(
    *,
    dataset_path: Path,
    feature_dry_run_path: Path,
    experiment_plan_path: Path,
    min_cases: int,
    min_label_source_steps: int,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    dataset = _load_required(dataset_path, failures, "dataset manifest")
    feature_dry_run = _load_required(feature_dry_run_path, failures, "policy feature dry-run")
    experiment_plan = _load_required(experiment_plan_path, failures, "policy experiment plan")

    cases = _dataset_cases(dataset)
    case_ids = [str(case.get("case_id")) for case in cases]
    if dataset and dataset.get("dataset_name") != "v0_scripted_skill_success_variations":
        failures.append(f"dataset_name must be v0_scripted_skill_success_variations, got {dataset.get('dataset_name')}")
    if len(cases) < min_cases:
        failures.append(f"dataset case count {len(cases)} < required {min_cases}")
    if "baseline_replay" not in case_ids:
        failures.append("dataset must include baseline_replay positive control")
    if "socket_x_pos_25mm_negative_control" in case_ids:
        failures.append("dataset must exclude the fail_closed negative control from label source review")

    if feature_dry_run:
        if feature_dry_run.get("status") != READY_FEATURE_STATUS:
            failures.append(f"feature dry-run status must be {READY_FEATURE_STATUS}, got {feature_dry_run.get('status')}")
        if feature_dry_run.get("ready_for_training") is not False:
            failures.append("feature dry-run must keep ready_for_training=false")
        target_schema = feature_dry_run.get("target_schema") if isinstance(feature_dry_run.get("target_schema"), dict) else {}
        if target_schema.get("target_status") != "NOT_GENERATED":
            failures.append("feature dry-run target_status must remain NOT_GENERATED")
        if feature_dry_run.get("dataset") and not _same_repo_path(str(feature_dry_run.get("dataset")), dataset_path):
            failures.append("feature dry-run points at a different dataset path")

    if experiment_plan:
        if experiment_plan.get("status") != READY_EXPERIMENT_STATUS:
            failures.append(f"policy experiment plan must be {READY_EXPERIMENT_STATUS}, got {experiment_plan.get('status')}")
        experiment = experiment_plan.get("experiment") if isinstance(experiment_plan.get("experiment"), dict) else {}
        if experiment.get("policy_family") != "residual_policy_over_scripted_baseline":
            failures.append("policy experiment must be residual_policy_over_scripted_baseline")
        forbidden = set(experiment.get("forbidden_outputs", []))
        if not {"raw_joint_targets", "direct_cartesian_servo_commands", "direct_force_commands"}.issubset(
            forbidden
        ):
            failures.append("policy experiment plan must preserve raw joint, direct Cartesian, and force bans")

    target_channel_names = [channel["name"] for channel in TARGET_CHANNEL_SCHEMA]
    for name in target_channel_names:
        lowered = name.lower()
        if "raw_joint" in lowered or "joint_pos" in lowered or "cartesian_servo" in lowered or "force_command" in lowered:
            failures.append(f"target channel crosses forbidden low-level boundary: {name}")

    trace_cache: dict[Path, dict[str, Any]] = {}
    case_reports: list[dict[str, Any]] = []
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
        if trace_path not in trace_cache:
            try:
                trace_cache[trace_path] = _audit_trace(trace_path, min_label_source_steps=min_label_source_steps)
            except Exception as exc:  # noqa: BLE001 - fail closed per case.
                trace_cache[trace_path] = {
                    "trace_json": _rel(trace_path),
                    "step_count": 0,
                    "label_source_step_count": 0,
                    "first_label_source_step": None,
                    "min_label_source_steps": min_label_source_steps,
                    "forbidden_trace_fields_present_but_excluded": [],
                    "pass": False,
                    "error": str(exc),
                }
        trace_report = trace_cache[trace_path]
        if not trace_report.get("pass"):
            failures.append(f"{case_id}: trace lacks enough allowed residual target source steps")
        case_reports.append(
            {
                "case_id": case_id,
                "trace_json": _rel(trace_path),
                "label_source_step_count": trace_report.get("label_source_step_count", 0),
                "first_label_source_step": trace_report.get("first_label_source_step"),
                "forbidden_trace_fields_present_but_excluded": trace_report.get(
                    "forbidden_trace_fields_present_but_excluded", []
                ),
            }
        )

    status = READY_STATUS if not failures else "BLOCKED"
    return {
        "audit_name": "v0_policy_label_source_audit",
        "status": status,
        "ready_for_training": False,
        "ready_for_label_generation": False,
        "target_generation_status": "DESIGN_ONLY",
        "dataset": _rel(dataset_path),
        "policy_feature_dry_run": _rel(feature_dry_run_path),
        "policy_experiment_plan": _rel(experiment_plan_path),
        "dataset_case_count": len(cases),
        "case_ids": case_ids,
        "target_channel_schema": TARGET_CHANNEL_SCHEMA,
        "target_channel_names": target_channel_names,
        "case_reports": case_reports,
        "required_before_label_generation": [
            "manual review of allowed target channels",
            "implement a separate no-GPU label-generation dry-run over trace windows",
            "prove the label generator ignores raw_action and joint_pos_des even when traces contain them",
            "run a negative-control label-source audit before any policy training",
        ],
        "blockers": failures,
        "warnings": warnings,
        "not_claims": [
            "not generated labels",
            "not trained policy",
            "not evaluated policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a Brev or Isaac launcher",
        ],
    }


def _render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# V0 Policy Label Source Audit",
        "",
        f"- status: {audit['status']}",
        f"- ready_for_training: {audit['ready_for_training']}",
        f"- ready_for_label_generation: {audit['ready_for_label_generation']}",
        f"- target_generation_status: {audit['target_generation_status']}",
        f"- dataset: {audit['dataset']}",
        f"- policy_feature_dry_run: {audit['policy_feature_dry_run']}",
        f"- policy_experiment_plan: {audit['policy_experiment_plan']}",
        f"- dataset_case_count: {audit['dataset_case_count']}",
        "",
        "## Target Channel Schema",
        "",
    ]
    lines.extend(f"- {item['name']}: {item['source']}" for item in audit["target_channel_schema"])
    lines.extend(["", "## Case Reports", ""])
    for case in audit["case_reports"]:
        lines.append(
            "- {case_id}: label_source_step_count={count}, trace={trace}".format(
                case_id=case["case_id"],
                count=case["label_source_step_count"],
                trace=case["trace_json"],
            )
        )
    lines.extend(["", "## Required Before Label Generation", ""])
    lines.extend(f"- {item}" for item in audit["required_before_label_generation"])
    if audit["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in audit["blockers"])
    if audit["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in audit["warnings"])
    lines.extend(["", "## Not Claims", ""])
    lines.extend(f"- {item}" for item in audit["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--policy-feature-dry-run", type=Path, default=DEFAULT_FEATURE_DRY_RUN)
    parser.add_argument("--policy-experiment-plan", type=Path, default=DEFAULT_EXPERIMENT_PLAN)
    parser.add_argument("--min-cases", type=int, default=5)
    parser.add_argument("--min-label-source-steps", type=int, default=5)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    audit = build_audit(
        dataset_path=_resolve(args.dataset),
        feature_dry_run_path=_resolve(args.policy_feature_dry_run),
        experiment_plan_path=_resolve(args.policy_experiment_plan),
        min_cases=max(1, args.min_cases),
        min_label_source_steps=max(1, args.min_label_source_steps),
    )
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-policy-label-source-audit] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(audit), encoding="utf-8")
        print(f"[v0-policy-label-source-audit] wrote Markdown: {_rel(output_md)}")

    print("[v0-policy-label-source-audit] facts=" + json.dumps(audit, indent=2, sort_keys=True))
    print("[v0-policy-label-source-audit] status=" + audit["status"])
    if audit["status"] != "BLOCKED":
        return 0
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
