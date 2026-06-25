#!/usr/bin/env python3
"""Train the V0 residual policy from an audited label dataset.

This script is deliberately downstream of
scripts/check_v0_policy_training_preflight.py. It refuses to train unless the
residual-label JSONL manifest, checksum, sample schema, and forbidden-token
checks pass first. It does not call Brev, Isaac, ROS, a vendor SDK, or any
robot. The default dry-run path also does not import torch or write a
checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_v0_policy_training_preflight as preflight_gate  # noqa: E402


DEFAULT_LABEL_DATASET_MANIFEST = REPO_ROOT / "artifacts" / "datasets" / "v0_residual_policy_labels" / "manifest.json"
DEFAULT_OUTPUT_CHECKPOINT = REPO_ROOT / "artifacts" / "policies" / "v0_residual_policy" / "model.pt"
DEFAULT_OUTPUT_METADATA = REPO_ROOT / "artifacts" / "policies" / "v0_residual_policy" / "metadata.json"
DEFAULT_OUTPUT_PLAN = REPO_ROOT / "artifacts" / "analysis" / "v0_residual_policy_training_plan.json"


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _build_plan(
    *,
    label_dataset_manifest: Path,
    checkpoint_path: Path,
    metadata_path: Path,
    preflight: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "plan_name": "v0_residual_policy_training",
        "status": "READY_FOR_LOCAL_TRAINING_DRY_RUN",
        "dry_run": bool(args.dry_run),
        "label_dataset_manifest": _rel(label_dataset_manifest),
        "jsonl": preflight.get("jsonl"),
        "jsonl_sha256": preflight.get("jsonl_sha256"),
        "checkpoint": _rel(checkpoint_path),
        "metadata": _rel(metadata_path),
        "sample_count": preflight.get("sample_count"),
        "feature_schema": preflight.get("feature_schema"),
        "label_names": preflight.get("label_names"),
        "hyperparameters": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "hidden_dim": args.hidden_dim,
            "layers": args.layers,
            "learning_rate": args.lr,
            "weight_decay": args.weight_decay,
            "validation_ratio": args.val_ratio,
            "seed": args.seed,
            "device": args.device,
        },
        "requires_for_real_training": [
            "same preflight remains READY immediately before training",
            "PyTorch import succeeds in the selected local/Isaac runtime",
            "checkpoint metadata records label manifest and JSONL checksums",
            "evaluation gate is added before policy promotion",
        ],
        "side_effects": {
            "writes_training_plan": not args.no_output,
            "writes_checkpoint": False,
            "writes_metadata": False,
            "imports_torch": False,
            "creates_paid_instance": False,
            "starts_isaac": False,
            "calls_ros_or_robot": False,
        },
        "not_claims": [
            "not trained policy" if args.dry_run else "not evaluated policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a Brev or Isaac launcher",
        ],
    }


def _build_blocked_report(
    *,
    label_dataset_manifest: Path,
    checkpoint_path: Path,
    metadata_path: Path,
    output_plan: Path,
    preflight: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "plan_name": "v0_residual_policy_training",
        "status": "BLOCKED",
        "dry_run": bool(args.dry_run),
        "no_output": bool(args.no_output),
        "label_dataset_manifest": _rel(label_dataset_manifest),
        "checkpoint": _rel(checkpoint_path),
        "metadata": _rel(metadata_path),
        "output_plan": _rel(output_plan),
        "preflight": preflight,
        "blockers": preflight.get("blockers", []),
        "ready_for_local_training_dry_run": False,
        "side_effects": {
            "writes_training_plan": False,
            "writes_checkpoint": False,
            "writes_metadata": False,
            "imports_torch": False,
            "creates_paid_instance": False,
            "starts_isaac": False,
            "calls_ros_or_robot": False,
        },
        "not_claims": [
            "not trained policy",
            "not evaluated policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a Brev or Isaac launcher",
        ],
    }


def _run_training(
    *,
    manifest: dict[str, Any],
    label_dataset_manifest: Path,
    checkpoint_path: Path,
    metadata_path: Path,
    preflight: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except ModuleNotFoundError as exc:
        raise SystemExit("PyTorch is required for real training; use --dry-run outside a PyTorch runtime.") from exc

    jsonl_path = _resolve(Path(str(manifest["jsonl"])))
    samples = _read_jsonl(jsonl_path)
    feature_schema = [str(name) for name in manifest["feature_schema"]]
    label_names = [str(name) for name in manifest["label_names"]]
    features = torch.tensor(
        [_vector_from_mapping(sample["features"], feature_schema) for sample in samples],
        dtype=torch.float32,
    )
    labels = torch.tensor(
        [_vector_from_mapping(sample["labels"], label_names) for sample in samples],
        dtype=torch.float32,
    )
    if features.shape[0] < 2:
        raise SystemExit("at least two samples are required for a train/validation split")

    generator = torch.Generator().manual_seed(args.seed)
    perm = torch.randperm(features.shape[0], generator=generator)
    val_count = max(1, int(round(features.shape[0] * args.val_ratio)))
    val_count = min(val_count, features.shape[0] - 1)
    val_idx = perm[:val_count]
    train_idx = perm[val_count:]

    x_mean = features[train_idx].mean(dim=0)
    x_std = features[train_idx].std(dim=0).clamp_min(1.0e-6)
    y_mean = labels[train_idx].mean(dim=0)
    y_std = labels[train_idx].std(dim=0).clamp_min(1.0e-6)
    x_norm = (features - x_mean) / x_std
    y_norm = (labels - y_mean) / y_std

    model = _build_model(
        nn,
        input_dim=x_norm.shape[1],
        output_dim=y_norm.shape[1],
        hidden_dim=args.hidden_dim,
        layers=args.layers,
    )
    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    model.to(device)

    loader = DataLoader(
        TensorDataset(x_norm[train_idx], y_norm[train_idx]),
        batch_size=args.batch_size,
        shuffle=True,
        generator=generator,
    )
    val_x = x_norm[val_idx].to(device)
    val_y = y_norm[val_idx].to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    best_val = float("inf")
    best_state = None

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        total_count = 0
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)
            pred = model(batch_x)
            loss = (pred - batch_y).pow(2).mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * batch_x.shape[0]
            total_count += batch_x.shape[0]

        model.eval()
        with torch.no_grad():
            val_loss = float((model(val_x) - val_y).pow(2).mean().item())
        if val_loss < best_val:
            best_val = val_loss
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        if epoch == 0 or epoch + 1 == args.epochs or (epoch + 1) % max(1, args.log_every) == 0:
            train_loss = total_loss / max(1, total_count)
            print(
                f"[v0-residual-policy-train] epoch={epoch + 1:04d} "
                f"train_loss={train_loss:.8f} val_loss={val_loss:.8f}",
                flush=True,
            )

    if best_state is not None:
        model.load_state_dict(best_state)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "model_state_dict": model.cpu().state_dict(),
        "feature_mean": x_mean,
        "feature_std": x_std,
        "label_mean": y_mean,
        "label_std": y_std,
        "feature_schema": feature_schema,
        "label_names": label_names,
        "label_dataset_manifest": _rel(label_dataset_manifest),
        "label_dataset_manifest_sha256": _sha256(label_dataset_manifest),
        "jsonl": manifest["jsonl"],
        "jsonl_sha256": manifest["jsonl_sha256"],
        "hidden_dim": args.hidden_dim,
        "layers": args.layers,
    }
    torch.save(checkpoint, checkpoint_path)

    metadata = {
        "status": "TRAINED_NEEDS_EVALUATION",
        "checkpoint": _rel(checkpoint_path),
        "checkpoint_sha256": _sha256(checkpoint_path),
        "label_dataset_manifest": _rel(label_dataset_manifest),
        "label_dataset_manifest_sha256": _sha256(label_dataset_manifest),
        "jsonl": manifest["jsonl"],
        "jsonl_sha256": manifest["jsonl_sha256"],
        "preflight_status": preflight.get("status"),
        "sample_count": len(samples),
        "train_samples": int(train_idx.numel()),
        "val_samples": int(val_idx.numel()),
        "best_val_loss": best_val,
        "feature_schema": feature_schema,
        "label_names": label_names,
        "not_claims": [
            "not evaluated policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a Brev or Isaac launcher",
        ],
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label-dataset-manifest", type=Path, default=DEFAULT_LABEL_DATASET_MANIFEST)
    parser.add_argument("--output-checkpoint", type=Path, default=DEFAULT_OUTPUT_CHECKPOINT)
    parser.add_argument("--output-metadata", type=Path, default=DEFAULT_OUTPUT_METADATA)
    parser.add_argument("--output-plan", type=Path, default=DEFAULT_OUTPUT_PLAN)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--lr", type=float, default=3.0e-4)
    parser.add_argument("--weight-decay", type=float, default=1.0e-5)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--log-every", type=int, default=25)
    args = parser.parse_args()

    label_manifest_path = _resolve(args.label_dataset_manifest)
    preflight = preflight_gate.build_preflight(
        label_dataset_manifest_path=label_manifest_path,
        training_script_path=Path(__file__).resolve(),
        require_torch=not args.dry_run,
        negative_control_id=preflight_gate.DEFAULT_NEGATIVE_CONTROL,
    )
    if preflight.get("status") == "BLOCKED":
        blocked_report = _build_blocked_report(
            label_dataset_manifest=label_manifest_path,
            checkpoint_path=_resolve(args.output_checkpoint),
            metadata_path=_resolve(args.output_metadata),
            output_plan=_resolve(args.output_plan),
            preflight=preflight,
            args=args,
        )
        print("[v0-residual-policy-train] facts=" + json.dumps(blocked_report, indent=2, sort_keys=True))
        print("[v0-residual-policy-train] BLOCKED")
        return 1

    checkpoint_path = _resolve(args.output_checkpoint)
    metadata_path = _resolve(args.output_metadata)
    plan = _build_plan(
        label_dataset_manifest=label_manifest_path,
        checkpoint_path=checkpoint_path,
        metadata_path=metadata_path,
        preflight=preflight,
        args=args,
    )
    if args.dry_run:
        if not args.no_output:
            output_plan = _resolve(args.output_plan)
            output_plan.parent.mkdir(parents=True, exist_ok=True)
            output_plan.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
            print(f"[v0-residual-policy-train] wrote dry-run plan: {_rel(output_plan)}")
        print("[v0-residual-policy-train] facts=" + json.dumps(plan, indent=2, sort_keys=True))
        print("[v0-residual-policy-train] READY_FOR_LOCAL_TRAINING_DRY_RUN")
        return 0

    manifest = _load_json(label_manifest_path)
    metadata = _run_training(
        manifest=manifest,
        label_dataset_manifest=label_manifest_path,
        checkpoint_path=checkpoint_path,
        metadata_path=metadata_path,
        preflight=preflight,
        args=args,
    )
    print(f"[v0-residual-policy-train] wrote checkpoint: {_rel(checkpoint_path)}")
    print(f"[v0-residual-policy-train] wrote metadata: {_rel(metadata_path)}")
    print("[v0-residual-policy-train] facts=" + json.dumps(metadata, indent=2, sort_keys=True))
    print("[v0-residual-policy-train] TRAINED_NEEDS_EVALUATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
