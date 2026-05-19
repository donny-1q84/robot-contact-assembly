#!/usr/bin/env python3
"""Train a small behavior-cloning MLP on the extracted contact demo dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path("artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.jsonl")
DEFAULT_OUTPUT = Path("artifacts/policies/phase2_contact_bc/bc_mlp.pt")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="JSONL dataset from extract_contact_demo_dataset.py.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output torch checkpoint.")
    parser.add_argument("--epochs", type=int, default=250)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--lr", type=float, default=3.0e-4)
    parser.add_argument("--weight-decay", type=float, default=1.0e-5)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default="auto", help="auto, cpu, cuda, or cuda:0.")
    args = parser.parse_args()

    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except ModuleNotFoundError as exc:
        raise SystemExit("PyTorch is required to train the BC policy. Run this on the Isaac/PyTorch runtime.") from exc

    samples = _load_jsonl(args.dataset)
    if not samples:
        raise SystemExit(f"dataset is empty: {args.dataset}")
    action_modes = {str(sample.get("action_mode", "absolute")) for sample in samples}
    if len(action_modes) != 1:
        raise SystemExit(f"dataset mixes action modes: {sorted(action_modes)}")
    action_mode = next(iter(action_modes))

    obs = torch.tensor([sample["observation"] for sample in samples], dtype=torch.float32)
    act = torch.tensor([sample["action"] for sample in samples], dtype=torch.float32)
    weights = torch.tensor([sample.get("sample_weight", 1.0) for sample in samples], dtype=torch.float32).unsqueeze(-1)
    weights = weights / torch.clamp(weights.mean(), min=1.0e-6)

    generator = torch.Generator().manual_seed(args.seed)
    perm = torch.randperm(obs.shape[0], generator=generator)
    val_count = max(1, int(round(obs.shape[0] * args.val_ratio)))
    val_idx = perm[:val_count]
    train_idx = perm[val_count:]
    if train_idx.numel() == 0:
        raise SystemExit("not enough samples for a train/validation split")

    obs_mean = obs[train_idx].mean(dim=0)
    obs_std = obs[train_idx].std(dim=0).clamp_min(1.0e-6)
    act_mean = act[train_idx].mean(dim=0)
    act_std = act[train_idx].std(dim=0).clamp_min(1.0e-6)

    obs_n = (obs - obs_mean) / obs_std
    act_n = (act - act_mean) / act_std

    layers: list[nn.Module] = []
    in_dim = obs_n.shape[1]
    for _ in range(max(1, args.layers)):
        layers.append(nn.Linear(in_dim, args.hidden_dim))
        layers.append(nn.SiLU())
        in_dim = args.hidden_dim
    layers.append(nn.Linear(in_dim, act_n.shape[1]))
    model = nn.Sequential(*layers)

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    model.to(device)

    train_ds = TensorDataset(obs_n[train_idx], act_n[train_idx], weights[train_idx])
    val_obs = obs_n[val_idx].to(device)
    val_act = act_n[val_idx].to(device)
    val_weights = weights[val_idx].to(device)
    loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, generator=generator)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    best_val = float("inf")
    best_state = None
    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        total_count = 0
        for batch_obs, batch_act, batch_weights in loader:
            batch_obs = batch_obs.to(device)
            batch_act = batch_act.to(device)
            batch_weights = batch_weights.to(device)
            pred = model(batch_obs)
            loss = ((pred - batch_act).pow(2) * batch_weights).mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            total_loss += float(loss.item()) * batch_obs.shape[0]
            total_count += batch_obs.shape[0]

        model.eval()
        with torch.no_grad():
            val_pred = model(val_obs)
            val_loss = ((val_pred - val_act).pow(2) * val_weights).mean().item()
        if val_loss < best_val:
            best_val = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if epoch == 0 or (epoch + 1) % 25 == 0 or epoch + 1 == args.epochs:
            train_loss = total_loss / max(1, total_count)
            print(f"[bc] epoch={epoch + 1:04d} train_loss={train_loss:.6f} val_loss={val_loss:.6f}")

    if best_state is not None:
        model.load_state_dict(best_state)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "model_state_dict": model.cpu().state_dict(),
        "obs_mean": obs_mean,
        "obs_std": obs_std,
        "action_mean": act_mean,
        "action_std": act_std,
        "obs_dim": obs.shape[1],
        "action_dim": act.shape[1],
        "hidden_dim": args.hidden_dim,
        "layers": args.layers,
        "num_samples": len(samples),
        "train_samples": int(train_idx.numel()),
        "val_samples": int(val_idx.numel()),
        "best_val_loss": best_val,
        "dataset": str(args.dataset),
        "action_mode": action_mode,
    }
    torch.save(checkpoint, args.output)
    metadata_path = args.output.with_suffix(".metadata.json")
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "dataset": str(args.dataset),
                "output": str(args.output),
                "num_samples": len(samples),
                "train_samples": int(train_idx.numel()),
                "val_samples": int(val_idx.numel()),
                "obs_dim": int(obs.shape[1]),
                "action_dim": int(act.shape[1]),
                "action_mode": action_mode,
                "hidden_dim": args.hidden_dim,
                "layers": args.layers,
                "best_val_loss": best_val,
            },
            f,
            indent=2,
            sort_keys=True,
        )
    print(f"[bc] wrote {args.output}")
    print(f"[bc] wrote {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
