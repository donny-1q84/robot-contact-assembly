#!/usr/bin/env python3
"""Check the V0 cross-robot portability boundary.

This is an offline claim gate. It answers one narrow question: whether the
current V0 language/skill system is directly reusable on arbitrary robot arms.
The answer is always no. A named robot may only proceed to low-speed review when
both the V0 skill readiness gate and that robot's adapter contract are READY.

It does not call Brev, Isaac, ROS, a vendor SDK, or any robot.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_v0_robot_adapter_contract as adapter_gate  # noqa: E402
import check_v0_skill_readiness as skill_gate  # noqa: E402


DEFAULT_REQUEST = REPO_ROOT / "configs" / "v0_skill_request.example.json"
DEFAULT_CONTRACT = REPO_ROOT / "configs" / "v0_skill_api_contract.json"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"
DEFAULT_ADAPTER = REPO_ROOT / "configs" / "v0_external_robot_adapter.template.json"


REUSABLE_LAYERS = [
    "language_request_schema",
    "skill_selection_boundary",
    "task_parameter_contract",
    "semantic_validation_gates",
    "dataset_and_policy_review_pipeline",
]

ROBOT_SPECIFIC_LAYERS = [
    "robot_model_and_joint_limits",
    "tool_geometry_and_tcp_transform",
    "base_tcp_socket_frame_calibration",
    "controller_interface_and_units",
    "rate_limits_timeouts_and_abort_conditions",
    "low_speed_contact_safety_validation",
    "strict_success_variation_revalidation",
]


def _side_effects(*, writes_boundary_report: bool) -> dict[str, bool]:
    return {
        "writes_boundary_report": writes_boundary_report,
        "writes_adapter_manifest": False,
        "creates_paid_instance": False,
        "runs_remote_code": False,
        "starts_isaac": False,
        "calls_ros_or_robot": False,
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


def _blockers_from_skill(readiness: dict[str, Any]) -> list[str]:
    if readiness.get("status") == "READY":
        return []
    blockers = readiness.get("blockers")
    if isinstance(blockers, list) and blockers:
        return ["v0_skill_readiness: " + str(item) for item in blockers]
    return ["v0_skill_readiness is not READY"]


def _blockers_from_adapter(adapter: dict[str, Any]) -> list[str]:
    if adapter.get("status") == "READY":
        return []
    blockers = adapter.get("blockers")
    failures = adapter.get("failures")
    output: list[str] = []
    if isinstance(failures, list):
        output.extend("robot_adapter_failure: " + str(item) for item in failures)
    if isinstance(blockers, list):
        output.extend("robot_adapter: " + str(item) for item in blockers)
    if not output:
        output.append("robot_adapter is not READY")
    return output


def _next_action(skill_readiness: dict[str, Any], adapter: dict[str, Any]) -> str:
    if skill_readiness.get("status") != "READY":
        return str(skill_readiness.get("next_action") or "make_v0_skill_readiness_ready")
    if adapter.get("status") != "READY":
        return str(adapter.get("next_action") or "fill_named_robot_adapter_evidence")
    return "manual_low_speed_named_robot_review_only"


def build_report(
    *,
    request_path: Path,
    contract_path: Path,
    manifest_path: Path,
    dataset_path: Path,
    adapter_path: Path,
    min_strict_successes: int,
    negative_control_id: str,
    skip_phase2: bool,
) -> dict[str, Any]:
    skill_readiness = skill_gate.build_report(
        request_path=_resolve(request_path),
        contract_path=_resolve(contract_path),
        manifest_path=_resolve(manifest_path),
        dataset_path=_resolve(dataset_path),
        min_strict_successes=min_strict_successes,
        negative_control_id=negative_control_id,
        skip_phase2=skip_phase2,
    )
    adapter = adapter_gate.build_report(_resolve(adapter_path))

    blockers = _blockers_from_skill(skill_readiness) + _blockers_from_adapter(adapter)
    ready = not blockers
    target_robot = adapter.get("target_robot") if isinstance(adapter.get("target_robot"), dict) else {}

    return {
        "check_name": "v0_cross_robot_portability_boundary",
        "status": "READY" if ready else "BLOCKED",
        "readiness_label": (
            "READY_FOR_NAMED_ROBOT_LOW_SPEED_REVIEW" if ready else "BLOCKED_NOT_DROP_IN"
        ),
        "universal_drop_in_ready": False,
        "named_robot_ready": ready,
        "portability_boundary": "language request -> skill target -> named robot adapter -> robot driver",
        "target_robot_id": target_robot.get("robot_id"),
        "skill_readiness_status": skill_readiness.get("status"),
        "adapter_status": adapter.get("status"),
        "request": _rel(_resolve(request_path)),
        "contract": _rel(_resolve(contract_path)),
        "manifest": _rel(_resolve(manifest_path)),
        "dataset": _rel(_resolve(dataset_path)),
        "adapter": _rel(_resolve(adapter_path)),
        "reusable_layers": REUSABLE_LAYERS,
        "robot_specific_layers": ROBOT_SPECIFIC_LAYERS,
        "blockers": list(dict.fromkeys(blockers)),
        "next_action": _next_action(skill_readiness, adapter),
        "side_effects": _side_effects(writes_boundary_report=False),
        "not_claims": [
            "not universal cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not hardware-ready without a named robot adapter",
            "not sim-to-real without robot-specific revalidation",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--negative-control-id", default=skill_gate.variation_gate.DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--skip-phase2-contact-gate", action="store_true")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_report(
        request_path=args.request,
        contract_path=args.contract,
        manifest_path=args.manifest,
        dataset_path=args.dataset,
        adapter_path=args.adapter,
        min_strict_successes=max(1, args.min_strict_successes),
        negative_control_id=args.negative_control_id,
        skip_phase2=args.skip_phase2_contact_gate,
    )

    if args.output_json is not None:
        report["side_effects"] = _side_effects(writes_boundary_report=True)
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-portability-boundary] wrote JSON: {_rel(output_json)}")

    print("[v0-portability-boundary] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "READY":
        print("[v0-portability-boundary] READY_FOR_NAMED_ROBOT_LOW_SPEED_REVIEW")
        print("[v0-portability-boundary] universal_drop_in_ready=false")
        return 0

    print("[v0-portability-boundary] BLOCKED_NOT_DROP_IN")
    print("[v0-portability-boundary] universal_drop_in_ready=false")
    for blocker in report["blockers"]:
        print(f"- {blocker}")
    print(f"[v0-portability-boundary] next_action={report['next_action']}")
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
