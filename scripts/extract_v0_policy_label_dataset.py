#!/usr/bin/env python3
"""Extract a V0 residual-policy label dataset without training.

This is an offline dataset-preparation gate after the label dry-run. It writes
a bounded JSONL label dataset and a checksum manifest from allowed
skill-controller residual fields only. It does not train a policy, write a
checkpoint, call Brev, start Isaac, call ROS, or talk to a robot.
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
DEFAULT_LABEL_DRY_RUN = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_dry_run.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "datasets" / "v0_residual_policy_labels"
DEFAULT_OUTPUT_JSONL = DEFAULT_OUTPUT_DIR / "labels.jsonl"
DEFAULT_OUTPUT_MANIFEST = DEFAULT_OUTPUT_DIR / "manifest.json"
DEFAULT_OUTPUT_MD = DEFAULT_OUTPUT_DIR / "README.md"
READY_LABEL_DRY_RUN_STATUS = "READY_FOR_LABEL_DRY_RUN_REVIEW"
READY_STATUS = "READY_FOR_LOCAL_POLICY_DATASET_REVIEW"

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

FEATURE_SCHEMA: list[str] = [
    "case_seed",
    "socket_delta_x_m",
    "socket_delta_y_m",
    "socket_delta_z_m",
    "reset_joint_noise_rad",
    "lateral_m",
    "axial_m",
    "rot_rad",
    "contact_force_n",
    "success_flag",
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


def _number(value: Any, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
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


def _sample_from_step(case: dict[str, Any], step: dict[str, Any], *, trace_path: Path) -> dict[str, Any] | None:
    label = _label_from_step(step)
    if label is None:
        return None
    lateral = _number(step.get("lateral"))
    axial = _number(step.get("axial"))
    rot = _number(step.get("rot"))
    contact = _number(step.get("contact_force_magnitude"))
    if lateral is None or axial is None or rot is None or contact is None or not isinstance(step.get("success"), bool):
        return None
    socket_delta = _vector3(case.get("socket_delta_m")) or [0.0, 0.0, 0.0]
    seed = _number(case.get("seed"), default=-1.0)
    reset_noise = _number(case.get("reset_joint_noise_rad"), default=0.0)
    return {
        "case_id": case.get("case_id"),
        "trace_json": _rel(trace_path),
        "step": step.get("step"),
        "features": {
            "case_seed": seed,
            "socket_delta_x_m": socket_delta[0],
            "socket_delta_y_m": socket_delta[1],
            "socket_delta_z_m": socket_delta[2],
            "reset_joint_noise_rad": reset_noise,
            "lateral_m": lateral,
            "axial_m": axial,
            "rot_rad": rot,
            "contact_force_n": contact,
            "success_flag": 1.0 if step.get("success") else 0.0,
        },
        "labels": label,
    }


def _trace_samples(
    case: dict[str, Any],
    *,
    trace_path: Path,
    max_samples_per_case: int,
) -> tuple[list[dict[str, Any]], int, list[str]]:
    payload = _load_json(trace_path)
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise RuntimeError(f"trace JSON must contain a steps list: {_rel(trace_path)}")
    candidates: list[dict[str, Any]] = []
    forbidden_seen: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            continue
        forbidden_seen.update(FORBIDDEN_TRACE_FIELDS.intersection(step.keys()))
        if step.get("phase") != "socket-insertion-servo":
            continue
        sample = _sample_from_step(case, step, trace_path=trace_path)
        if sample is None:
            continue
        candidates.append(sample)
    return candidates[: max(1, max_samples_per_case)], len(candidates), sorted(forbidden_seen)


def _write_jsonl(path: Path, samples: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, sort_keys=True) + "\n")


def build_dataset(
    *,
    dataset_path: Path,
    label_dry_run_path: Path,
    max_samples_per_case: int,
    min_cases: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    failures: list[str] = []
    warnings: list[str] = []
    dataset = _load_required(dataset_path, failures, "dataset manifest")
    label_dry_run = _load_required(label_dry_run_path, failures, "policy label dry-run")

    cases = _dataset_cases(dataset)
    case_ids = [str(case.get("case_id")) for case in cases]
    if dataset and dataset.get("dataset_name") != "v0_scripted_skill_success_variations":
        failures.append(f"dataset_name must be v0_scripted_skill_success_variations, got {dataset.get('dataset_name')}")
    if len(cases) < min_cases:
        failures.append(f"dataset case count {len(cases)} < required {min_cases}")
    if "baseline_replay" not in case_ids:
        failures.append("dataset must include baseline_replay positive control")
    if "socket_x_pos_25mm_negative_control" in case_ids:
        failures.append("label dataset must not include the fail_closed negative control")

    if label_dry_run:
        if label_dry_run.get("status") != READY_LABEL_DRY_RUN_STATUS:
            failures.append(
                f"label dry-run status must be {READY_LABEL_DRY_RUN_STATUS}, got {label_dry_run.get('status')}"
            )
        if label_dry_run.get("ready_for_training") is not False:
            failures.append("label dry-run must keep ready_for_training=false")
        if label_dry_run.get("label_generation_status") != "DRY_RUN_PREVIEW_ONLY":
            failures.append("label dry-run must be DRY_RUN_PREVIEW_ONLY before full extraction")
        if label_dry_run.get("dataset") and not _same_repo_path(str(label_dry_run.get("dataset")), dataset_path):
            failures.append("label dry-run points at a different dataset path")

    label_names = [item["name"] for item in LABEL_SCHEMA]
    for name in label_names:
        lowered = name.lower()
        if "raw_joint" in lowered or "joint_pos" in lowered or "cartesian_servo" in lowered or "force_command" in lowered:
            failures.append(f"label channel crosses forbidden low-level boundary: {name}")

    samples: list[dict[str, Any]] = []
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
        try:
            case_samples, candidate_count, forbidden_seen = _trace_samples(
                case,
                trace_path=trace_path,
                max_samples_per_case=max_samples_per_case,
            )
        except Exception as exc:  # noqa: BLE001 - fail closed per case.
            failures.append(f"{case_id}: label dataset extraction failed: {exc}")
            continue
        if not case_samples:
            failures.append(f"{case_id}: no allowed label samples extracted")
        samples.extend(case_samples)
        case_reports.append(
            {
                "case_id": case_id,
                "trace_json": _rel(trace_path),
                "candidate_label_window_count": candidate_count,
                "sample_count": len(case_samples),
                "forbidden_trace_fields_present_but_excluded": forbidden_seen,
            }
        )

    status = READY_STATUS if not failures else "BLOCKED"
    manifest = {
        "dataset_name": "v0_residual_policy_label_dataset",
        "status": status,
        "ready_for_training": False,
        "dataset": _rel(dataset_path),
        "policy_label_dry_run": _rel(label_dry_run_path),
        "source_case_count": len(cases),
        "source_case_ids": case_ids,
        "sample_count": len(samples),
        "feature_schema": FEATURE_SCHEMA,
        "label_schema": LABEL_SCHEMA,
        "label_names": label_names,
        "case_reports": case_reports,
        "required_before_training": [
            "manual review of this manifest and JSONL samples",
            "train/eval script preflight that checks this manifest checksum",
            "negative-control exclusion remains verified",
            "explicit PyTorch environment selection before training",
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
    return manifest, samples


def _render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# V0 Residual Policy Label Dataset",
        "",
        f"- status: {manifest['status']}",
        f"- ready_for_training: {manifest['ready_for_training']}",
        f"- sample_count: {manifest['sample_count']}",
        f"- source_case_count: {manifest['source_case_count']}",
        f"- dataset: {manifest['dataset']}",
        f"- policy_label_dry_run: {manifest['policy_label_dry_run']}",
        "",
        "## Label Schema",
        "",
    ]
    lines.extend(f"- {item['name']}: {item['source']}" for item in manifest["label_schema"])
    lines.extend(["", "## Case Reports", ""])
    for report in manifest["case_reports"]:
        lines.append(
            "- {case_id}: sample_count={sample_count}, candidate_windows={candidate_count}".format(
                case_id=report["case_id"],
                sample_count=report["sample_count"],
                candidate_count=report["candidate_label_window_count"],
            )
        )
    lines.extend(["", "## Required Before Training", ""])
    lines.extend(f"- {item}" for item in manifest["required_before_training"])
    if manifest["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in manifest["blockers"])
    if manifest["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in manifest["warnings"])
    lines.extend(["", "## Not Claims", ""])
    lines.extend(f"- {item}" for item in manifest["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--policy-label-dry-run", type=Path, default=DEFAULT_LABEL_DRY_RUN)
    parser.add_argument("--max-samples-per-case", type=int, default=50)
    parser.add_argument("--min-cases", type=int, default=5)
    parser.add_argument("--output-jsonl", type=Path, default=DEFAULT_OUTPUT_JSONL)
    parser.add_argument("--output-manifest", type=Path, default=DEFAULT_OUTPUT_MANIFEST)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    output_jsonl = _resolve(args.output_jsonl)
    manifest, samples = build_dataset(
        dataset_path=_resolve(args.dataset),
        label_dry_run_path=_resolve(args.policy_label_dry_run),
        max_samples_per_case=max(1, args.max_samples_per_case),
        min_cases=max(1, args.min_cases),
    )
    if manifest["status"] != "BLOCKED" and not args.no_output:
        _write_jsonl(output_jsonl, samples)
        manifest["jsonl"] = _rel(output_jsonl)
        manifest["jsonl_sha256"] = _sha256(output_jsonl)
        manifest["sample_count"] = len(samples)
        output_manifest = _resolve(args.output_manifest)
        output_manifest.parent.mkdir(parents=True, exist_ok=True)
        output_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-policy-label-dataset] wrote manifest: {_rel(output_manifest)}")
        print(f"[v0-policy-label-dataset] wrote JSONL: {_rel(output_jsonl)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(manifest), encoding="utf-8")
        print(f"[v0-policy-label-dataset] wrote Markdown: {_rel(output_md)}")
    elif not args.no_output:
        print("[v0-policy-label-dataset] blocked; no dataset artifacts written")

    print("[v0-policy-label-dataset] facts=" + json.dumps(manifest, indent=2, sort_keys=True))
    print("[v0-policy-label-dataset] status=" + manifest["status"])
    if manifest["status"] != "BLOCKED":
        return 0
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
