#!/usr/bin/env python3
"""Check V0 residual-policy training preflight without training.

This is an offline train/eval script preflight. It verifies the residual-label
dataset manifest, JSONL checksum, sample schema, and forbidden low-level fields
before any V0 training script is implemented or run.
It does not train a policy, import torch, write a checkpoint, call Brev, start Isaac, call ROS, or talk to a robot.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL_DATASET_MANIFEST = REPO_ROOT / "artifacts" / "datasets" / "v0_residual_policy_labels" / "manifest.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_training_preflight.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_training_preflight.md"
READY_LABEL_DATASET_STATUS = "READY_FOR_LOCAL_POLICY_DATASET_REVIEW"
READY_STATUS = "READY_FOR_TRAINING_SCRIPT_IMPLEMENTATION"

FORBIDDEN_SAMPLE_TOKENS = [
    "raw_action",
    "joint_pos_des",
    "joint_pos_des_raw",
    "joint_response_delta",
    "action_pos_w",
    "action_quat_w",
    "command_pos_w",
    "command_quat_w",
    "direct_cartesian_servo_commands",
    "direct_force_commands",
    "raw_joint_targets",
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


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                raise RuntimeError(f"JSONL row {index} must be an object")
            rows.append(payload)
    return rows


def _finite_number(value: Any) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed)


def _check_numeric_mapping(mapping: Any, required_keys: list[str], label: str, failures: list[str]) -> None:
    if not isinstance(mapping, dict):
        failures.append(f"{label} must be an object")
        return
    missing = sorted(set(required_keys).difference(mapping.keys()))
    if missing:
        failures.append(f"{label} missing required keys: " + ", ".join(missing))
    for key in required_keys:
        if key in mapping and not _finite_number(mapping[key]):
            failures.append(f"{label}.{key} must be a finite number")


def build_preflight(
    *,
    label_dataset_manifest_path: Path,
    require_torch: bool,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    manifest = _load_required(label_dataset_manifest_path, failures, "V0 residual label dataset manifest")

    samples: list[dict[str, Any]] = []
    jsonl_path: Path | None = None
    expected_sample_count = 0
    feature_schema: list[str] = []
    label_names: list[str] = []

    if manifest:
        if manifest.get("dataset_name") != "v0_residual_policy_label_dataset":
            failures.append(f"dataset_name must be v0_residual_policy_label_dataset, got {manifest.get('dataset_name')}")
        if manifest.get("status") != READY_LABEL_DATASET_STATUS:
            failures.append(f"label dataset status must be {READY_LABEL_DATASET_STATUS}, got {manifest.get('status')}")
        if manifest.get("ready_for_training") is not False:
            failures.append("label dataset manifest must keep ready_for_training=false")
        if "socket_x_pos_25mm_negative_control" in set(map(str, manifest.get("source_case_ids", []))):
            failures.append("label dataset must exclude the fail_closed negative control")
        expected_sample_count = int(manifest.get("sample_count") or 0)
        if expected_sample_count <= 0:
            failures.append("label dataset sample_count must be positive")
        feature_schema = [str(item) for item in manifest.get("feature_schema", []) if isinstance(item, str)]
        label_names = [str(item) for item in manifest.get("label_names", []) if isinstance(item, str)]
        if not feature_schema:
            failures.append("label dataset feature_schema must be non-empty")
        if not label_names:
            failures.append("label dataset label_names must be non-empty")
        for label in label_names:
            lowered = label.lower()
            if "raw_joint" in lowered or "joint_pos" in lowered or "cartesian_servo" in lowered or "force_command" in lowered:
                failures.append(f"label name crosses forbidden low-level boundary: {label}")

        jsonl_value = manifest.get("jsonl")
        if not isinstance(jsonl_value, str) or not jsonl_value:
            failures.append("label dataset manifest must record jsonl")
        else:
            jsonl_path = _resolve(Path(jsonl_value))
            if not jsonl_path.is_file():
                failures.append(f"label dataset JSONL is missing: {_rel(jsonl_path)}")
            else:
                expected_sha = manifest.get("jsonl_sha256")
                if not isinstance(expected_sha, str) or not expected_sha:
                    failures.append("label dataset manifest must record jsonl_sha256")
                else:
                    actual_sha = _sha256(jsonl_path)
                    if actual_sha != expected_sha:
                        failures.append(f"label dataset JSONL checksum mismatch: {actual_sha} != {expected_sha}")
                try:
                    samples = _read_jsonl(jsonl_path)
                except Exception as exc:  # noqa: BLE001 - fail closed on dataset parse.
                    failures.append(f"label dataset JSONL could not be parsed: {exc}")

    if samples and expected_sample_count != len(samples):
        failures.append(f"label dataset sample_count {expected_sample_count} does not match JSONL rows {len(samples)}")

    forbidden_hits: dict[str, list[str]] = {}
    for index, sample in enumerate(samples):
        payload = json.dumps(sample, sort_keys=True)
        hits = [token for token in FORBIDDEN_SAMPLE_TOKENS if token in payload]
        if hits:
            forbidden_hits[str(index)] = hits
        _check_numeric_mapping(sample.get("features"), feature_schema, f"sample[{index}].features", failures)
        _check_numeric_mapping(sample.get("labels"), label_names, f"sample[{index}].labels", failures)
        if not isinstance(sample.get("case_id"), str) or not sample.get("case_id"):
            failures.append(f"sample[{index}].case_id must be a non-empty string")
        if not _finite_number(sample.get("step")):
            failures.append(f"sample[{index}].step must be numeric")
    if forbidden_hits:
        failures.append("label dataset JSONL contains forbidden low-level tokens: " + json.dumps(forbidden_hits, sort_keys=True))

    torch_available = importlib.util.find_spec("torch") is not None
    if require_torch and not torch_available:
        failures.append("PyTorch module is not available in this Python environment")
    elif not torch_available:
        warnings.append("PyTorch is not available in this Python environment; training must use the Isaac/PyTorch runtime")

    status = READY_STATUS if not failures else "BLOCKED"
    return {
        "preflight_name": "v0_policy_training_preflight",
        "status": status,
        "ready_for_training": False,
        "ready_for_training_launch": False,
        "training_script_status": "NOT_IMPLEMENTED",
        "label_dataset_manifest": _rel(label_dataset_manifest_path),
        "jsonl": _rel(jsonl_path) if jsonl_path is not None else None,
        "sample_count": len(samples),
        "manifest_sample_count": expected_sample_count,
        "feature_schema": feature_schema,
        "label_names": label_names,
        "jsonl_sha256": manifest.get("jsonl_sha256") if manifest else None,
        "forbidden_sample_tokens": FORBIDDEN_SAMPLE_TOKENS,
        "torch_available_by_spec": torch_available,
        "training_command_template": [
            "python3",
            "scripts/train_v0_residual_policy.py",
            "--label-dataset-manifest",
            _rel(label_dataset_manifest_path),
            "--output",
            "artifacts/policies/v0_residual_policy/model.pt",
        ],
        "required_before_training": [
            "implement train_v0_residual_policy.py against this manifest contract",
            "add an evaluator that checks the same manifest checksum before loading a checkpoint",
            "run training only in an explicit PyTorch/Isaac-compatible environment",
            "do not use Brev or paid GPU until a separate budget and cleanup plan is approved",
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


def _render_markdown(preflight: dict[str, Any]) -> str:
    lines = [
        "# V0 Policy Training Preflight",
        "",
        f"- status: {preflight['status']}",
        f"- ready_for_training: {preflight['ready_for_training']}",
        f"- ready_for_training_launch: {preflight['ready_for_training_launch']}",
        f"- training_script_status: {preflight['training_script_status']}",
        f"- label_dataset_manifest: {preflight['label_dataset_manifest']}",
        f"- jsonl: {preflight['jsonl']}",
        f"- sample_count: {preflight['sample_count']}",
        f"- torch_available_by_spec: {preflight['torch_available_by_spec']}",
        "",
        "## Training Command Template",
        "",
        "```bash",
        " ".join(preflight["training_command_template"]),
        "```",
        "",
        "## Required Before Training",
        "",
    ]
    lines.extend(f"- {item}" for item in preflight["required_before_training"])
    if preflight["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in preflight["blockers"])
    if preflight["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in preflight["warnings"])
    lines.extend(["", "## Not Claims", ""])
    lines.extend(f"- {item}" for item in preflight["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dataset-manifest", type=Path, default=DEFAULT_LABEL_DATASET_MANIFEST)
    parser.add_argument("--require-torch", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    preflight = build_preflight(
        label_dataset_manifest_path=_resolve(args.label_dataset_manifest),
        require_torch=args.require_torch,
    )
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(preflight, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-policy-training-preflight] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(preflight), encoding="utf-8")
        print(f"[v0-policy-training-preflight] wrote Markdown: {_rel(output_md)}")

    print("[v0-policy-training-preflight] facts=" + json.dumps(preflight, indent=2, sort_keys=True))
    print("[v0-policy-training-preflight] status=" + preflight["status"])
    if preflight["status"] != "BLOCKED":
        return 0
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
