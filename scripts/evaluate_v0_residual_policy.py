#!/usr/bin/env python3
"""Evaluate or preflight a trained V0 residual policy checkpoint.

This script is downstream of scripts/train_v0_residual_policy.py. Its dry-run
path verifies the checkpoint metadata, checkpoint checksum, label-dataset
manifest checksum, and JSONL checksum without importing torch. The real
supervised evaluation path imports torch and computes residual-label prediction
errors on the audited JSONL dataset.

It does not call Brev, Isaac, ROS, a vendor SDK, or any robot. Passing this
script is not a policy-promotion, sim-to-real, or hardware-readiness claim.
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
DEFAULT_METADATA = REPO_ROOT / "artifacts" / "policies" / "v0_residual_policy" / "metadata.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "evaluations" / "v0_residual_policy" / "summary.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "evaluations" / "v0_residual_policy" / "README.md"

READY_DRY_RUN_STATUS = "READY_FOR_LOCAL_SUPERVISED_EVAL_DRY_RUN"
EVALUATED_STATUS = "SUPERVISED_EVAL_NEEDS_ISAAC_POLICY_GATE"


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


def _vector_from_mapping(mapping: dict[str, Any], names: list[str]) -> list[float]:
    return [float(mapping[name]) for name in names]


def _build_model(torch_nn, *, input_dim: int, output_dim: int, hidden_dim: int, layers: int):
    modules: list[Any] = []
    current_dim = input_dim
    for _ in range(max(1, layers)):
        modules.append(torch_nn.Linear(current_dim, hidden_dim))
        modules.append(torch_nn.SiLU())
        current_dim = hidden_dim
    modules.append(torch_nn.Linear(current_dim, output_dim))
    return torch_nn.Sequential(*modules)


def build_preflight(metadata_path: Path) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    metadata_path = _resolve(metadata_path)
    metadata: dict[str, Any] = {}
    checkpoint_path: Path | None = None
    label_manifest_path: Path | None = None
    jsonl_path: Path | None = None
    label_manifest: dict[str, Any] = {}

    if not metadata_path.is_file():
        failures.append(f"training metadata is missing: {_rel(metadata_path)}")
    else:
        metadata = _load_json(metadata_path)
        if metadata.get("status") != "TRAINED_NEEDS_EVALUATION":
            failures.append(f"metadata status must be TRAINED_NEEDS_EVALUATION, got {metadata.get('status')}")

        checkpoint_value = metadata.get("checkpoint")
        if not isinstance(checkpoint_value, str) or not checkpoint_value:
            failures.append("metadata must record checkpoint")
        else:
            checkpoint_path = _resolve(Path(checkpoint_value))
            if not checkpoint_path.is_file():
                failures.append(f"checkpoint is missing: {_rel(checkpoint_path)}")
            else:
                expected_checkpoint_sha = metadata.get("checkpoint_sha256")
                actual_checkpoint_sha = _sha256(checkpoint_path)
                if expected_checkpoint_sha != actual_checkpoint_sha:
                    failures.append(
                        f"checkpoint_sha256 mismatch: {actual_checkpoint_sha} != {expected_checkpoint_sha}"
                    )

        label_manifest_value = metadata.get("label_dataset_manifest")
        if not isinstance(label_manifest_value, str) or not label_manifest_value:
            failures.append("metadata must record label_dataset_manifest")
        else:
            label_manifest_path = _resolve(Path(label_manifest_value))
            if not label_manifest_path.is_file():
                failures.append(f"label dataset manifest is missing: {_rel(label_manifest_path)}")
            else:
                expected_manifest_sha = metadata.get("label_dataset_manifest_sha256")
                actual_manifest_sha = _sha256(label_manifest_path)
                if expected_manifest_sha != actual_manifest_sha:
                    failures.append(
                        "label_dataset_manifest_sha256 mismatch: "
                        f"{actual_manifest_sha} != {expected_manifest_sha}"
                    )
                label_manifest = _load_json(label_manifest_path)
                if label_manifest.get("status") != "READY_FOR_LOCAL_POLICY_DATASET_REVIEW":
                    failures.append(
                        "label dataset manifest status must be READY_FOR_LOCAL_POLICY_DATASET_REVIEW, "
                        f"got {label_manifest.get('status')}"
                    )

        jsonl_value = metadata.get("jsonl") or label_manifest.get("jsonl")
        if not isinstance(jsonl_value, str) or not jsonl_value:
            failures.append("metadata or label dataset manifest must record jsonl")
        else:
            jsonl_path = _resolve(Path(jsonl_value))
            if not jsonl_path.is_file():
                failures.append(f"label dataset JSONL is missing: {_rel(jsonl_path)}")
            else:
                expected_jsonl_sha = metadata.get("jsonl_sha256") or label_manifest.get("jsonl_sha256")
                actual_jsonl_sha = _sha256(jsonl_path)
                if expected_jsonl_sha != actual_jsonl_sha:
                    failures.append(f"jsonl_sha256 mismatch: {actual_jsonl_sha} != {expected_jsonl_sha}")

        if metadata.get("feature_schema") != label_manifest.get("feature_schema") and label_manifest:
            failures.append("metadata feature_schema does not match label dataset manifest")
        if metadata.get("label_names") != label_manifest.get("label_names") and label_manifest:
            failures.append("metadata label_names does not match label dataset manifest")
        if "not evaluated policy" not in [str(item) for item in metadata.get("not_claims", [])]:
            failures.append("metadata must preserve not evaluated policy non-claim")

    status = READY_DRY_RUN_STATUS if not failures else "BLOCKED"
    return {
        "eval_preflight_name": "v0_residual_policy_evaluation",
        "status": status,
        "ready_for_supervised_eval": status == READY_DRY_RUN_STATUS,
        "metadata": _rel(metadata_path),
        "checkpoint": _rel(checkpoint_path) if checkpoint_path is not None else None,
        "label_dataset_manifest": _rel(label_manifest_path) if label_manifest_path is not None else None,
        "jsonl": _rel(jsonl_path) if jsonl_path is not None else None,
        "sample_count": metadata.get("sample_count"),
        "feature_schema": metadata.get("feature_schema") if isinstance(metadata.get("feature_schema"), list) else [],
        "label_names": metadata.get("label_names") if isinstance(metadata.get("label_names"), list) else [],
        "blockers": failures,
        "warnings": warnings,
        "not_claims": [
            "not Isaac closed-loop evaluation",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a Brev or Isaac launcher",
        ],
    }


def _run_supervised_eval(preflight: dict[str, Any], metadata_path: Path) -> dict[str, Any]:
    try:
        import torch
        from torch import nn
    except ModuleNotFoundError as exc:
        raise SystemExit("PyTorch is required for supervised residual-policy evaluation; use --dry-run otherwise.") from exc

    metadata = _load_json(_resolve(metadata_path))
    checkpoint_path = _resolve(Path(str(metadata["checkpoint"])))
    label_manifest_path = _resolve(Path(str(metadata["label_dataset_manifest"])))
    label_manifest = _load_json(label_manifest_path)
    jsonl_path = _resolve(Path(str(label_manifest["jsonl"])))
    samples = _read_jsonl(jsonl_path)
    feature_schema = [str(name) for name in metadata["feature_schema"]]
    label_names = [str(name) for name in metadata["label_names"]]

    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    model = _build_model(
        nn,
        input_dim=len(feature_schema),
        output_dim=len(label_names),
        hidden_dim=int(checkpoint["hidden_dim"]),
        layers=int(checkpoint["layers"]),
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    features = torch.tensor(
        [_vector_from_mapping(sample["features"], feature_schema) for sample in samples],
        dtype=torch.float32,
    )
    labels = torch.tensor(
        [_vector_from_mapping(sample["labels"], label_names) for sample in samples],
        dtype=torch.float32,
    )
    with torch.no_grad():
        pred_n = model((features - checkpoint["feature_mean"]) / checkpoint["feature_std"])
        pred = pred_n * checkpoint["label_std"] + checkpoint["label_mean"]
        errors = pred - labels
        mse = float(errors.pow(2).mean().item())
        max_abs = float(errors.abs().max().item())
        per_label_mae = errors.abs().mean(dim=0).tolist()

    if not math.isfinite(mse) or not math.isfinite(max_abs):
        raise SystemExit("evaluation produced non-finite metrics")

    return {
        "eval_name": "v0_residual_policy_supervised_eval",
        "status": EVALUATED_STATUS,
        "metadata": _rel(_resolve(metadata_path)),
        "checkpoint": _rel(checkpoint_path),
        "label_dataset_manifest": _rel(label_manifest_path),
        "jsonl": _rel(jsonl_path),
        "sample_count": len(samples),
        "mse": mse,
        "max_abs_error": max_abs,
        "per_label_mae": dict(zip(label_names, [float(value) for value in per_label_mae], strict=True)),
        "preflight_status": preflight.get("status"),
        "required_before_policy_promotion": [
            "run an Isaac closed-loop policy gate with the same checkpoint checksum",
            "compare against scripted baseline and negative controls",
            "keep ROS 2 and external robot use behind adapter calibration and safety gates",
        ],
        "not_claims": [
            "not Isaac closed-loop evaluation",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a Brev or Isaac launcher",
        ],
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# V0 Residual Policy Evaluation",
        "",
        f"- status: {payload['status']}",
        f"- metadata: {payload.get('metadata')}",
        f"- checkpoint: {payload.get('checkpoint')}",
        f"- label_dataset_manifest: {payload.get('label_dataset_manifest')}",
        f"- jsonl: {payload.get('jsonl')}",
        f"- sample_count: {payload.get('sample_count')}",
        "",
    ]
    if "mse" in payload:
        lines.extend(
            [
                "## Supervised Metrics",
                "",
                f"- mse: {payload['mse']}",
                f"- max_abs_error: {payload['max_abs_error']}",
                "",
            ]
        )
    blockers = payload.get("blockers")
    if blockers:
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {item}" for item in blockers)
        lines.append("")
    required = payload.get("required_before_policy_promotion")
    if required:
        lines.extend(["## Required Before Policy Promotion", ""])
        lines.extend(f"- {item}" for item in required)
        lines.append("")
    lines.extend(["## Not Claims", ""])
    lines.extend(f"- {item}" for item in payload["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    preflight = build_preflight(args.metadata)
    if preflight["status"] == "BLOCKED":
        print("[v0-residual-policy-eval] facts=" + json.dumps(preflight, indent=2, sort_keys=True))
        print("[v0-residual-policy-eval] BLOCKED")
        if args.fail_on_blocked:
            return 1
        return 0

    payload = preflight if args.dry_run else _run_supervised_eval(preflight, args.metadata)
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-residual-policy-eval] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(payload), encoding="utf-8")
        print(f"[v0-residual-policy-eval] wrote Markdown: {_rel(output_md)}")

    print("[v0-residual-policy-eval] facts=" + json.dumps(payload, indent=2, sort_keys=True))
    print("[v0-residual-policy-eval] status=" + payload["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
