#!/usr/bin/env python3
"""Extract a small contact-phase behavior-cloning dataset from scripted traces."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_TRACE_ROOT = Path("artifacts/evaluations/scripted")
DEFAULT_OUTPUT = Path("artifacts/datasets/phase2_contact_bc/phase2_contact_bc_dataset.jsonl")

OBS_FIELDS: tuple[tuple[str, int], ...] = (
    ("physical_tip_rel_socket_pos", 3),
    ("pos_error", 3),
    ("axis_angle_error", 3),
    ("contact_force_socket", 3),
    ("contact_force_magnitude", 1),
    ("lateral", 1),
    ("axial", 1),
    ("rot", 1),
    ("joint_pos", 7),
    ("joint_vel", 7),
    ("joint_limit_margin", 7),
)


@dataclass(frozen=True)
class FilterCfg:
    profile: str
    action_mode: str
    phases: set[str]
    task_contains: str | None
    action_dim: int | None
    max_lateral: float
    max_axial: float
    max_rot: float
    min_contact: float
    strict_xy_tol: float
    strict_z_tol: float
    strict_rot_tol: float
    strict_min_contact: float
    window_radius: int
    max_windows: int


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _trace_paths(root: Path, since: str | None) -> list[Path]:
    if not root.exists():
        return []
    paths = []
    for path in root.glob("**/seed_*_trace.json"):
        if since is not None and path.parent.name < since:
            continue
        paths.append(path)
    return sorted(paths)


def _as_float_list(value: Any, expected_len: int, *, fill: float = 0.0) -> list[float] | None:
    if expected_len == 1 and isinstance(value, (int, float)):
        return [float(value)]
    if not isinstance(value, list):
        return [fill] * expected_len
    if len(value) != expected_len:
        return None
    try:
        return [float(x) for x in value]
    except (TypeError, ValueError):
        return None


def _obs_vector(step: dict[str, Any]) -> list[float] | None:
    values: list[float] = []
    for field, size in OBS_FIELDS:
        vector = _as_float_list(step.get(field), size)
        if vector is None:
            return None
        values.extend(vector)
    return values


def _strict_miss_score(step: dict[str, Any], cfg: FilterCfg) -> float:
    lateral = float(step.get("lateral") or 0.0)
    axial = float(step.get("axial") or 0.0)
    rot = float(step.get("rot") or 0.0)
    contact = float(step.get("contact_force_magnitude") or 0.0)
    return (
        max(0.0, lateral - cfg.strict_xy_tol) * 100.0
        + max(0.0, axial - cfg.strict_z_tol) * 100.0
        + max(0.0, rot - cfg.strict_rot_tol) * 10.0
        + max(0.0, cfg.strict_min_contact - contact)
    )


def _passes_filter(step: dict[str, Any], summary: dict[str, Any], cfg: FilterCfg) -> bool:
    if cfg.task_contains and cfg.task_contains not in str(summary.get("task") or ""):
        return False
    phase = str(step.get("phase") or "")
    if cfg.phases and phase not in cfg.phases:
        return False
    lateral = float(step.get("lateral") or 0.0)
    axial = float(step.get("axial") or 0.0)
    rot = float(step.get("rot") or 0.0)
    contact = float(step.get("contact_force_magnitude") or 0.0)
    if lateral > cfg.max_lateral or axial > cfg.max_axial or rot > cfg.max_rot or contact < cfg.min_contact:
        return False
    action = step.get("raw_action")
    if not isinstance(action, list):
        return False
    if cfg.action_dim is not None and len(action) != cfg.action_dim:
        return False
    return True


def _select_best_windows(paths: list[Path], cfg: FilterCfg) -> tuple[dict[Path, set[int]], list[dict[str, Any]]]:
    windows: list[dict[str, Any]] = []
    for path in paths:
        trace = _load_json(path)
        summary = trace.get("summary") or {}
        steps = trace.get("steps") or []
        scored_steps: list[tuple[float, int, dict[str, Any]]] = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or not _passes_filter(step, summary, cfg):
                continue
            if _obs_vector(step) is None:
                continue
            scored_steps.append((_strict_miss_score(step, cfg), index, step))
        if not scored_steps:
            continue
        score, center_index, center_step = min(scored_steps, key=lambda item: item[0])
        windows.append(
            {
                "trace": str(path),
                "run_id": path.parent.name,
                "task": summary.get("task"),
                "scripted_control_mode": summary.get("scripted_control_mode"),
                "summary_success_step": summary.get("success_step"),
                "center_index": center_index,
                "center_step": int(center_step.get("step") or -1),
                "center_strict_miss_score": score,
                "center_lateral": float(center_step.get("lateral") or 0.0),
                "center_axial": float(center_step.get("axial") or 0.0),
                "center_rot": float(center_step.get("rot") or 0.0),
                "center_contact": float(center_step.get("contact_force_magnitude") or 0.0),
            }
        )

    windows.sort(key=lambda item: item["center_strict_miss_score"])
    if cfg.max_windows > 0:
        windows = windows[: cfg.max_windows]

    allowed: dict[Path, set[int]] = {}
    for window in windows:
        path = Path(window["trace"])
        center_index = int(window["center_index"])
        start = max(0, center_index - cfg.window_radius)
        stop = center_index + cfg.window_radius
        allowed.setdefault(path, set()).update(range(start, stop + 1))
    return allowed, windows


def _sample_weight(strict_miss: float, active_success: bool, strict_success: bool) -> float:
    weight = 1.0 / (1.0 + strict_miss)
    if active_success:
        weight += 1.0
    if strict_success:
        weight += 2.0
    return weight


def _action_vector(step: dict[str, Any], cfg: FilterCfg) -> list[float] | None:
    raw_action = step.get("raw_action")
    if not isinstance(raw_action, list):
        return None
    if cfg.action_dim is not None and len(raw_action) != cfg.action_dim:
        return None
    try:
        action = [float(x) for x in raw_action]
    except (TypeError, ValueError):
        return None
    if cfg.action_mode == "absolute":
        return action
    if cfg.action_mode == "residual-current":
        joint_pos = _as_float_list(step.get("joint_pos"), len(action))
        if joint_pos is None:
            return None
        return [target - current for target, current in zip(action, joint_pos, strict=True)]
    raise ValueError(f"unsupported action_mode={cfg.action_mode!r}")


def _strict_success(step: dict[str, Any], cfg: FilterCfg) -> bool:
    return (
        float(step.get("lateral") or 0.0) < cfg.strict_xy_tol
        and float(step.get("axial") or 0.0) < cfg.strict_z_tol
        and float(step.get("rot") or 0.0) < cfg.strict_rot_tol
        and float(step.get("contact_force_magnitude") or 0.0) >= cfg.strict_min_contact
    )


def _extract(paths: Iterable[Path], cfg: FilterCfg) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    paths = list(paths)
    samples: list[dict[str, Any]] = []
    per_trace: list[dict[str, Any]] = []
    skipped_missing_obs = 0
    selected_windows: list[dict[str, Any]] = []
    allowed_indices_by_path: dict[Path, set[int]] | None = None

    if cfg.profile == "best-window":
        allowed_indices_by_path, selected_windows = _select_best_windows(paths, cfg)

    for path in paths:
        trace = _load_json(path)
        summary = trace.get("summary") or {}
        steps = trace.get("steps") or []
        before = len(samples)
        for index, step in enumerate(steps):
            if allowed_indices_by_path is not None and index not in allowed_indices_by_path.get(path, set()):
                continue
            if not isinstance(step, dict) or not _passes_filter(step, summary, cfg):
                continue
            obs = _obs_vector(step)
            if obs is None:
                skipped_missing_obs += 1
                continue
            action = _action_vector(step, cfg)
            if action is None:
                continue
            miss = _strict_miss_score(step, cfg)
            is_active_success = bool(step.get("success"))
            is_strict_success = _strict_success(step, cfg)
            samples.append(
                {
                    "observation": obs,
                    "action": action,
                    "action_mode": cfg.action_mode,
                    "sample_weight": _sample_weight(miss, is_active_success, is_strict_success),
                    "strict_miss_score": miss,
                    "active_success": is_active_success,
                    "strict_success": is_strict_success,
                    "step": int(step.get("step") or -1),
                    "run_id": path.parent.name,
                    "trace_path": str(path),
                    "phase": str(step.get("phase") or ""),
                    "task": summary.get("task"),
                    "scripted_control_mode": summary.get("scripted_control_mode"),
                }
            )
        added = len(samples) - before
        if added:
            per_trace.append(
                {
                    "trace": str(path),
                    "run_id": path.parent.name,
                    "task": summary.get("task"),
                    "scripted_control_mode": summary.get("scripted_control_mode"),
                    "samples": added,
                    "summary_success_step": summary.get("success_step"),
                }
            )

    metadata = {
        "num_samples": len(samples),
        "observation_dim": len(samples[0]["observation"]) if samples else 0,
        "action_dim": len(samples[0]["action"]) if samples else 0,
        "observation_fields": [{"name": name, "size": size} for name, size in OBS_FIELDS],
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
            "window_radius": cfg.window_radius,
            "max_windows": cfg.max_windows,
        },
        "active_success_samples": sum(1 for sample in samples if sample["active_success"]),
        "strict_success_samples": sum(1 for sample in samples if sample["strict_success"]),
        "skipped_missing_obs": skipped_missing_obs,
        "selected_windows": selected_windows,
        "traces": per_trace,
    }
    return samples, metadata


def _save_jsonl(path: Path, samples: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, sort_keys=True) + "\n")


def _save_npz(path: Path, samples: list[dict[str, Any]]) -> None:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "numpy is required only for .npz output. Use the default .jsonl output locally, "
            "or install numpy in the active Python environment."
        ) from exc

    arrays = {
        "observations": np.asarray([sample["observation"] for sample in samples], dtype=np.float32),
        "actions": np.asarray([sample["action"] for sample in samples], dtype=np.float32),
        "sample_weight": np.asarray([sample["sample_weight"] for sample in samples], dtype=np.float32),
        "strict_miss_score": np.asarray([sample["strict_miss_score"] for sample in samples], dtype=np.float32),
        "active_success": np.asarray([sample["active_success"] for sample in samples], dtype=np.bool_),
        "strict_success": np.asarray([sample["strict_success"] for sample in samples], dtype=np.bool_),
        "action_mode": np.asarray([sample.get("action_mode", "absolute") for sample in samples]),
        "step": np.asarray([sample["step"] for sample in samples], dtype=np.int32),
        "run_id": np.asarray([sample["run_id"] for sample in samples]),
        "trace_path": np.asarray([sample["trace_path"] for sample in samples]),
        "phase": np.asarray([sample["phase"] for sample in samples]),
    }
    np.savez_compressed(path, **arrays)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="*", type=Path, help="Trace JSON files. Defaults to scanning --root.")
    parser.add_argument("--root", type=Path, default=DEFAULT_TRACE_ROOT, help="Trace root used when no paths are given.")
    parser.add_argument("--since", type=str, default="2026-05-17T19-00-00Z", help="Minimum run directory timestamp.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output dataset path. Use .npz for NumPy output.")
    parser.add_argument(
        "--profile",
        choices=("all-traces", "best-window"),
        default="all-traces",
        help="Dataset profile. best-window keeps only windows around the lowest strict-miss traces.",
    )
    parser.add_argument(
        "--action-mode",
        choices=("absolute", "residual-current"),
        default="absolute",
        help="Target action representation. residual-current stores raw_action - current joint_pos.",
    )
    parser.add_argument("--window-radius", type=int, default=80, help="Step radius around each selected best-window center.")
    parser.add_argument("--max-windows", type=int, default=2, help="Maximum best windows to keep. Use 0 to keep all.")
    parser.add_argument(
        "--phases",
        type=str,
        default="polish,settle,contact-retention,insert",
        help="Comma-separated phases to include. Empty string includes all phases.",
    )
    parser.add_argument("--task-contains", type=str, default="JointPos", help="Only include traces whose task contains this string.")
    parser.add_argument("--action-dim", type=int, default=7, help="Only include actions with this dimension. Use 0 for any.")
    parser.add_argument("--max-lateral", type=float, default=0.03, help="Maximum lateral error in meters.")
    parser.add_argument("--max-axial", type=float, default=0.07, help="Maximum axial error in meters.")
    parser.add_argument("--max-rot", type=float, default=0.35, help="Maximum rotation error in radians.")
    parser.add_argument("--min-contact", type=float, default=0.0, help="Minimum contact-force magnitude.")
    parser.add_argument("--strict-xy-tol", type=float, default=0.005)
    parser.add_argument("--strict-z-tol", type=float, default=0.045)
    parser.add_argument("--strict-rot-tol", type=float, default=0.18)
    parser.add_argument("--strict-min-contact", type=float, default=0.5)
    args = parser.parse_args()

    phases = {p.strip() for p in args.phases.split(",") if p.strip()}
    cfg = FilterCfg(
        profile=args.profile,
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
        max_windows=args.max_windows,
    )

    paths = args.traces or _trace_paths(args.root, args.since)
    samples, metadata = _extract(paths, cfg)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.suffix == ".npz":
        _save_npz(args.output, samples)
    else:
        _save_jsonl(args.output, samples)
    metadata_path = args.output.with_suffix(".metadata.json")
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, sort_keys=True)

    print(f"[dataset] wrote {args.output}")
    print(f"[dataset] wrote {metadata_path}")
    print(
        "[dataset] "
        f"samples={metadata['num_samples']} obs_dim={metadata['observation_dim']} action_dim={metadata['action_dim']} "
        f"active_success={metadata['active_success_samples']} strict_success={metadata['strict_success_samples']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
