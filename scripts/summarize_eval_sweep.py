"""Summarize evaluation summary.json files from a checkpoint sweep."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _float_key(value: object) -> float:
    if value is None:
        return float("inf")
    return float(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize checkpoint sweep evaluation JSON files.")
    parser.add_argument(
        "--eval-root",
        type=Path,
        default=Path("artifacts/evaluations/policy"),
        help="Root directory containing evaluation timestamp folders.",
    )
    parser.add_argument(
        "--checkpoint-substring",
        type=str,
        default="",
        help="Only include summaries whose checkpoint_path contains this substring.",
    )
    parser.add_argument(
        "--task-substring",
        type=str,
        default="",
        help="Only include summaries whose task contains this substring.",
    )
    parser.add_argument(
        "--sort-by",
        type=str,
        choices=("final_rot", "final_lateral", "final_axial", "final_success_rate"),
        default="final_rot",
        help="Metric used for ascending sort.",
    )
    parser.add_argument(
        "--dedupe-checkpoint",
        action="store_true",
        help="Keep only the best row per checkpoint filename according to --sort-by.",
    )
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for summary_path in sorted(args.eval_root.glob("*/summary.json")):
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        checkpoint_path = str(data.get("checkpoint_path", ""))
        task = str(data.get("task", ""))
        if args.checkpoint_substring and args.checkpoint_substring not in checkpoint_path:
            continue
        if args.task_substring and args.task_substring not in task:
            continue
        rows.append(
            {
                "timestamp": summary_path.parent.name,
                "checkpoint": Path(checkpoint_path).name,
                "task": task,
                "final_success_rate": data.get("final_success_rate"),
                "final_lateral": data.get("final_lateral"),
                "final_axial": data.get("final_axial"),
                "final_rot": data.get("final_rot"),
            }
        )

    rows.sort(key=lambda row: _float_key(row[args.sort_by]))

    if args.dedupe_checkpoint:
        best_by_checkpoint: dict[str, dict[str, object]] = {}
        for row in rows:
            checkpoint = str(row["checkpoint"])
            if checkpoint not in best_by_checkpoint:
                best_by_checkpoint[checkpoint] = row
        rows = list(best_by_checkpoint.values())

    if not rows:
        print("No matching evaluation summaries found.")
        return

    header = (
        f"{'timestamp':<22} {'checkpoint':<12} {'success':>8} "
        f"{'lateral':>10} {'axial':>10} {'rot':>10}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['timestamp']:<22} {row['checkpoint']:<12} "
            f"{_float_key(row['final_success_rate']):>8.3f} "
            f"{_float_key(row['final_lateral']):>10.4f} "
            f"{_float_key(row['final_axial']):>10.4f} "
            f"{_float_key(row['final_rot']):>10.4f}"
        )


if __name__ == "__main__":
    main()
