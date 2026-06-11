#!/usr/bin/env python3
"""Extract a BC-compatible dataset around final-contact reset candidates.

This is a local preparation step for reset-based final-contact stabilization.
Samples extracted here are not strict-success labels unless the source
candidate category is target_gate_success.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import tarfile
from typing import Any

from extract_contact_demo_dataset import (
    FilterCfg,
    _action_vector,
    _obs_vector,
    _passes_filter,
    _sample_weight,
    _save_jsonl,
    _save_npz,
    _strict_miss_score,
    _strict_success,
    observation_fields,
)


DEFAULT_MANIFEST = Path("artifacts/reports/final_contact_reset_candidates_2026-06-09.json")
DEFAULT_OUTPUT = Path(
    "artifacts/datasets/phase2_contact_bc_final_contact_candidates/"
    "phase2_contact_bc_final_contact_candidates_dataset.jsonl"
)


def _load_trace_ref(trace_ref: str) -> dict[str, Any]:
    if "::" not in trace_ref:
        with open(trace_ref, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise RuntimeError(f"trace JSON is not an object: {trace_ref}")
        return loaded
    archive_path, member_name = trace_ref.split("::", 1)
    with tarfile.open(archive_path, "r:*") as tar:
        extracted = tar.extractfile(member_name)
        if extracted is None:
            raise RuntimeError(f"trace member is not extractable: {trace_ref}")
        with extracted:
            loaded = json.load(extracted)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"trace JSON is not an object: {trace_ref}")
    return loaded


def _candidate_step_index(steps: list[Any], candidate_step: int) -> int | None:
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        raw_step = step.get("step")
        source_step = int(raw_step if raw_step is not None else index)
        if source_step == candidate_step:
            return index
    return None


def _selected_candidates(manifest: dict[str, Any], categories: set[str], max_candidates: int) -> list[dict[str, Any]]:
    raw_candidates = manifest.get("candidates")
    if not isinstance(raw_candidates, list):
        raise RuntimeError("candidate manifest has no candidates array")
    candidates = [
        candidate
        for candidate in raw_candidates
        if isinstance(candidate, dict) and (not categories or str(candidate.get("category") or "") in categories)
    ]
    if max_candidates > 0:
        candidates = candidates[:max_candidates]
    return candidates


def _extract_candidate_windows(
    candidates: list[dict[str, Any]],
    cfg: FilterCfg,
    *,
    window_radius: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    selected_windows: list[dict[str, Any]] = []
    skipped_missing_trace = 0
    skipped_missing_step = 0
    skipped_missing_obs = 0
    trace_cache: dict[str, dict[str, Any]] = {}

    for candidate_index, candidate in enumerate(candidates):
        trace_ref = str(candidate.get("trace") or "")
        if not trace_ref:
            skipped_missing_trace += 1
            continue
        trace = trace_cache.get(trace_ref)
        if trace is None:
            trace = _load_trace_ref(trace_ref)
            trace_cache[trace_ref] = trace
        summary = trace.get("summary") if isinstance(trace.get("summary"), dict) else {}
        steps = trace.get("steps") if isinstance(trace.get("steps"), list) else []
        candidate_step = int(candidate.get("step"))
        center_index = _candidate_step_index(steps, candidate_step)
        if center_index is None:
            skipped_missing_step += 1
            continue
        start = max(0, center_index - window_radius)
        stop = min(len(steps), center_index + window_radius + 1)
        before = len(samples)
        for index in range(start, stop):
            step = steps[index]
            if not isinstance(step, dict) or not _passes_filter(step, summary, cfg):
                continue
            obs = _obs_vector(step, steps=steps, index=index, cfg=cfg)
            if obs is None:
                skipped_missing_obs += 1
                continue
            action = _action_vector(step, cfg)
            if action is None:
                continue
            miss = _strict_miss_score(step, cfg)
            is_active_success = bool(step.get("success"))
            is_strict_success = _strict_success(step, cfg)
            raw_step = step.get("step")
            source_step = int(raw_step if raw_step is not None else index)
            samples.append(
                {
                    "observation": obs,
                    "action": action,
                    "action_mode": cfg.action_mode,
                    "observation_mode": "base" if cfg.history_steps == 0 else "temporal-history",
                    "history_steps": cfg.history_steps,
                    "sample_weight": _sample_weight(miss, is_active_success, is_strict_success),
                    "strict_miss_score": miss,
                    "active_success": is_active_success,
                    "strict_success": is_strict_success,
                    "step": source_step,
                    "run_id": candidate.get("run_id"),
                    "trace_path": trace_ref,
                    "phase": str(step.get("phase") or ""),
                    "task": summary.get("task"),
                    "scripted_control_mode": summary.get("scripted_control_mode"),
                    "candidate_index": candidate_index,
                    "candidate_category": candidate.get("category"),
                    "candidate_step": candidate_step,
                    "candidate_strict_miss_score": candidate.get("strict_miss_score"),
                    "candidate_reset_use": candidate.get("reset_use"),
                    "candidate_label_use": candidate.get("label_use"),
                }
            )
        selected_windows.append(
            {
                "candidate_index": candidate_index,
                "category": candidate.get("category"),
                "run_id": candidate.get("run_id"),
                "trace": trace_ref,
                "candidate_step": candidate_step,
                "start_index": start,
                "stop_index_exclusive": stop,
                "samples": len(samples) - before,
                "candidate_strict_miss_score": candidate.get("strict_miss_score"),
                "candidate_reset_use": candidate.get("reset_use"),
                "candidate_label_use": candidate.get("label_use"),
            }
        )

    metadata = {
        "num_samples": len(samples),
        "observation_dim": len(samples[0]["observation"]) if samples else 0,
        "action_dim": len(samples[0]["action"]) if samples else 0,
        "observation_fields": observation_fields(cfg.history_steps),
        "filter": {
            "profile": cfg.profile,
            "action_mode": cfg.action_mode,
            "phases": sorted(cfg.phases),
            "task_contains": cfg.task_contains,
            "action_dim": cfg.action_dim,
            "max_lateral": cfg.max_lateral,
            "max_axial": cfg.max_axial,
            "max_rot": cfg.max_rot,
            "min_contact": cfg.min_contact,
            "strict_xy_tol": cfg.strict_xy_tol,
            "strict_z_tol": cfg.strict_z_tol,
            "strict_rot_tol": cfg.strict_rot_tol,
            "strict_min_contact": cfg.strict_min_contact,
            "window_radius": window_radius,
            "history_steps": cfg.history_steps,
        },
        "observation_mode": "base" if cfg.history_steps == 0 else "temporal-history",
        "history_steps": cfg.history_steps,
        "active_success_samples": sum(1 for sample in samples if sample["active_success"]),
        "strict_success_samples": sum(1 for sample in samples if sample["strict_success"]),
        "category_counts": dict(sorted(Counter(sample["candidate_category"] for sample in samples).items())),
        "selected_windows": selected_windows,
        "skipped_missing_trace": skipped_missing_trace,
        "skipped_missing_step": skipped_missing_step,
        "skipped_missing_obs": skipped_missing_obs,
    }
    return samples, metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output dataset path. Use .npz for NumPy output.")
    parser.add_argument(
        "--categories",
        default="strict_near_miss,rotation_only_miss,depth_contact_rotation_conflict",
        help="Comma-separated candidate categories. Empty string includes all categories.",
    )
    parser.add_argument("--max-candidates", type=int, default=0, help="Maximum candidates to consume. Use 0 for all.")
    parser.add_argument("--window-radius", type=int, default=40)
    parser.add_argument(
        "--action-mode",
        choices=("absolute", "residual-current"),
        default="residual-current",
        help="Target action representation. residual-current stores raw_action - current joint_pos.",
    )
    parser.add_argument("--history-steps", type=int, default=2)
    parser.add_argument(
        "--phases",
        default="",
        help="Comma-separated phases to include. Empty string includes all phases within candidate windows.",
    )
    parser.add_argument("--task-contains", default="JointPos")
    parser.add_argument("--action-dim", type=int, default=7, help="Only include actions with this dimension. Use 0 for any.")
    parser.add_argument("--max-lateral", type=float, default=0.03)
    parser.add_argument("--max-axial", type=float, default=0.08)
    parser.add_argument("--max-rot", type=float, default=0.60)
    parser.add_argument("--min-contact", type=float, default=0.0)
    parser.add_argument("--strict-xy-tol", type=float, default=0.005)
    parser.add_argument("--strict-z-tol", type=float, default=0.045)
    parser.add_argument("--strict-rot-tol", type=float, default=0.18)
    parser.add_argument("--strict-min-contact", type=float, default=0.5)
    args = parser.parse_args()

    with args.manifest.open("r", encoding="utf-8") as f:
        manifest = json.load(f)
    if not isinstance(manifest, dict):
        raise SystemExit(f"manifest JSON is not an object: {args.manifest}")
    categories = {item.strip() for item in args.categories.split(",") if item.strip()}
    candidates = _selected_candidates(manifest, categories, args.max_candidates)
    phases = {item.strip() for item in args.phases.split(",") if item.strip()}
    cfg = FilterCfg(
        profile="candidate-window",
        action_mode=args.action_mode,
        phases=phases,
        task_contains=args.task_contains or None,
        action_dim=args.action_dim if args.action_dim > 0 else None,
        max_lateral=args.max_lateral,
        max_axial=args.max_axial,
        max_rot=args.max_rot,
        min_contact=args.min_contact,
        strict_xy_tol=args.strict_xy_tol,
        strict_z_tol=args.strict_z_tol,
        strict_rot_tol=args.strict_rot_tol,
        strict_min_contact=args.strict_min_contact,
        window_radius=args.window_radius,
        max_windows=args.max_candidates,
        history_steps=max(0, args.history_steps),
    )
    samples, metadata = _extract_candidate_windows(candidates, cfg, window_radius=max(0, args.window_radius))
    metadata["manifest"] = str(args.manifest)
    metadata["candidate_categories"] = sorted(categories)
    metadata["candidate_count"] = len(candidates)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix == ".npz":
        _save_npz(args.output, samples)
    else:
        _save_jsonl(args.output, samples)
    metadata_path = args.output.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[candidate-dataset] wrote {args.output}")
    print(f"[candidate-dataset] wrote {metadata_path}")
    print(
        "[candidate-dataset] "
        f"samples={metadata['num_samples']} obs_dim={metadata['observation_dim']} action_dim={metadata['action_dim']} "
        f"active_success={metadata['active_success_samples']} strict_success={metadata['strict_success_samples']}"
    )
    return 0 if samples else 1


if __name__ == "__main__":
    raise SystemExit(main())
