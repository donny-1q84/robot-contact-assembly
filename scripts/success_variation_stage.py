"""Fixed workloads for corrected-geometry controls and the unchanged eight-case batch."""

from __future__ import annotations

import copy
from pathlib import Path

STAGES = ("variation-batch", "baseline-validation")
BASELINE = "baseline_replay"
NEGATIVE = "socket_x_pos_25mm_negative_control"
CONTROL_ROOT = "artifacts/videos/success_variations/corrected_geometry_controls_v2"
REPO_ROOT = Path(__file__).resolve().parents[1]


def validate_stage(stage: str) -> str:
    if stage not in STAGES:
        raise ValueError(f"unknown success-variation stage: {stage!r}")
    return stage


def workload_manifest(manifest: dict, stage: str) -> dict:
    """Never mutate the fixed manifest or relabel bootstrap controls as batch results."""
    validate_stage(stage)
    selected = copy.deepcopy(manifest)
    if stage == "variation-batch":
        return selected
    cases = manifest.get("cases", [])
    selected["cases"] = []
    for case_id, delta, expected in (
        (BASELINE, [0.0, 0.0, 0.0], "strict_success"),
        (NEGATIVE, [0.025, 0.0, 0.0], "fail_closed"),
    ):
        matches = [case for case in cases if case.get("case_id") == case_id]
        if len(matches) != 1:
            raise ValueError(f"exactly one {case_id} control is required")
        case = copy.deepcopy(matches[0])
        if (case.get("seed") != 42 or case.get("reset_joint_noise_rad") != 0.0
                or case.get("socket_delta_m") != delta or case.get("expected") != expected):
            raise ValueError(f"{case_id} fixed control settings have changed")
        for key in ("trace_json", "result_trace_json"):
            case.pop(key, None)
        case["status"] = "planned"
        case["planned_trace_json"] = f"{CONTROL_ROOT}/{case_id}/video_trace.json"
        selected["cases"].append(case)
    return selected


def baseline_destination(manifest: dict, root: Path = REPO_ROOT) -> Path:
    case = next(case for case in manifest["cases"] if case["case_id"] == BASELINE)
    path = root / case["planned_trace_json"]
    if (not path.resolve().is_relative_to((root / "artifacts/videos/success_variations").resolve())
            or path.name != "video_trace.json" or path.is_symlink()):
        raise ValueError("baseline destination must remain inside success_variations artifacts")
    return path


def baseline_preconditions(manifest: dict, root: Path = REPO_ROOT) -> list[str]:
    """A new run cannot overwrite or silently reuse a previous control attempt."""
    controls = workload_manifest(manifest, "baseline-validation")
    blockers = []
    for case in controls["cases"]:
        path = root / case["planned_trace_json"]
        if path.parent.exists() or path.is_symlink():
            blockers.append(f"review and preserve existing baseline-validation attempt before retry: {path.parent}")
    if baseline_destination(manifest, root).exists():
        blockers.append("a corrected baseline already exists; review its evidence before another baseline run")
    return blockers
