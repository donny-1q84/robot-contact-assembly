#!/usr/bin/env python3
"""Prepare a V0 policy/API review packet after skill readiness is READY.

This is an offline packaging gate. It validates the high-level skill request,
success-variation result gate, and scripted-skill dataset via
check_v0_skill_readiness.py, then writes a compact review packet only when that
readiness gate is READY. It does not train a policy, call Brev, start Isaac,
call ROS, or talk to a robot.
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

import check_v0_skill_readiness as readiness_gate  # noqa: E402


DEFAULT_REQUEST = REPO_ROOT / "configs" / "v0_skill_request.example.json"
DEFAULT_CONTRACT = REPO_ROOT / "configs" / "v0_skill_api_contract.json"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "reviews" / "v0_policy_api"
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "review_packet.json"
DEFAULT_OUTPUT_MD = DEFAULT_OUTPUT_DIR / "README.md"


def _side_effects(*, writes_review_artifacts: bool) -> dict[str, bool]:
    return {
        "writes_review_artifacts": writes_review_artifacts,
        "writes_dataset_artifacts": False,
        "writes_policy_artifacts": False,
        "writes_checkpoint": False,
        "trains_policy": False,
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


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root must be an object: {_rel(path)}")
    return payload


def _dataset_summary(dataset_path: Path) -> dict[str, Any]:
    dataset = _load_json(dataset_path)
    cases = dataset.get("cases") if isinstance(dataset.get("cases"), list) else []
    return {
        "dataset": _rel(dataset_path),
        "dataset_name": dataset.get("dataset_name"),
        "dataset_version": dataset.get("dataset_version"),
        "case_count": len(cases),
        "case_ids": [case.get("case_id") for case in cases if isinstance(case, dict)],
        "source_manifest": dataset.get("source_manifest"),
        "selection_policy": dataset.get("selection_policy"),
        "not_claims": dataset.get("not_claims"),
    }


def _build_packet(readiness: dict[str, Any], dataset_path: Path) -> dict[str, Any]:
    request_gate = readiness.get("request_gate") if isinstance(readiness.get("request_gate"), dict) else {}
    contract_gate = readiness.get("contract_gate") if isinstance(readiness.get("contract_gate"), dict) else {}
    variation_gate = readiness.get("success_variation_gate", {}).get("gate", {})
    return {
        "review_name": "v0_policy_api_review_packet",
        "status": "READY_FOR_POLICY_API_REVIEW",
        "readiness_name": readiness.get("readiness_name"),
        "request": readiness.get("request"),
        "contract": readiness.get("contract"),
        "manifest": readiness.get("manifest"),
        "dataset": _dataset_summary(dataset_path),
        "normalized_request": request_gate.get("normalized_request"),
        "skill": {
            "skill_id": contract_gate.get("skill_id"),
            "task_family": contract_gate.get("task_family"),
            "controller_mode": request_gate.get("normalized_request", {}).get("controller_mode"),
        },
        "required_gate_summary": {
            "phase2_contact_gate": readiness.get("phase2_contact_gate", {}).get("status"),
            "success_variation_pass": variation_gate.get("pass"),
            "strict_variation_cases": variation_gate.get("strict_variation_cases"),
            "strict_variation_coverage_groups": variation_gate.get("summary", {}).get(
                "strict_variation_coverage_groups"
            ),
            "negative_control_classification": variation_gate.get("summary", {}).get(
                "negative_control_classification"
            ),
            "dataset_gate": readiness.get("dataset_gate", {}).get("status"),
        },
        "proposed_api_boundary": {
            "allowed_inputs": [
                "instruction",
                "task_parameters.object_id",
                "task_parameters.socket_id",
                "task_parameters.target_pose_frame",
                "task_parameters.tolerance_profile",
                "execution_policy.max_attempts",
            ],
            "allowed_outputs": [
                "skill_status",
                "semantic_validation_summary",
                "failure_explanation",
                "dataset_case_reference",
            ],
            "forbidden_outputs": [
                "raw_joint_targets",
                "raw_joint_velocities",
                "direct_cartesian_servo_commands",
                "direct_force_commands",
            ],
        },
        "manual_review_checklist": [
            "confirm dataset cases match the intended V0 scripted-skill family",
            "confirm negative control remains excluded from training data",
            "confirm policy work starts as residual over scripted baseline, not language-to-raw-control",
            "confirm ROS 2 or external-robot adapter work remains behind calibration and revalidation gates",
        ],
        "not_claims": [
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a direct low-level VLM controller",
        ],
        "next_stage": [
            "manual review of this packet",
            "freeze V0 skill API fields",
            "then design residual-policy or imitation-learning experiment over the scripted baseline",
        ],
    }


def _build_blocked_packet(readiness: dict[str, Any], dataset_path: Path) -> dict[str, Any]:
    blockers = readiness.get("blockers") if isinstance(readiness.get("blockers"), list) else []
    return {
        "review_name": "v0_policy_api_review_packet",
        "status": "BLOCKED",
        "readiness_status": readiness.get("status"),
        "readiness_name": readiness.get("readiness_name"),
        "request": readiness.get("request"),
        "contract": readiness.get("contract"),
        "manifest": readiness.get("manifest"),
        "dataset": _rel(dataset_path),
        "blockers": blockers,
        "next_action": readiness.get("next_action"),
        "side_effects": _side_effects(writes_review_artifacts=False),
        "not_claims": [
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a direct low-level VLM controller",
        ],
    }


def _render_markdown(packet: dict[str, Any]) -> str:
    rows = [
        "# V0 Policy/API Review Packet",
        "",
        f"- status: {packet['status']}",
        f"- request: {packet['request']}",
        f"- contract: {packet['contract']}",
        f"- manifest: {packet['manifest']}",
        f"- dataset: {packet['dataset']['dataset']}",
        f"- dataset_cases: {packet['dataset']['case_count']}",
        "",
        "## Gate Summary",
        "",
    ]
    for key, value in packet["required_gate_summary"].items():
        rows.append(f"- {key}: {value}")
    rows.extend(["", "## API Boundary", ""])
    rows.append("- allowed_inputs: " + ", ".join(packet["proposed_api_boundary"]["allowed_inputs"]))
    rows.append("- allowed_outputs: " + ", ".join(packet["proposed_api_boundary"]["allowed_outputs"]))
    rows.append("- forbidden_outputs: " + ", ".join(packet["proposed_api_boundary"]["forbidden_outputs"]))
    rows.extend(["", "## What This Is Not", ""])
    rows.extend(f"- {claim}" for claim in packet["not_claims"])
    rows.extend(["", "## Manual Review Checklist", ""])
    rows.extend(f"- {item}" for item in packet["manual_review_checklist"])
    rows.extend(["", "## Next Stage", ""])
    rows.extend(f"- {item}" for item in packet["next_stage"])
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, nargs="?", default=DEFAULT_REQUEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--negative-control-id", default=readiness_gate.variation_gate.DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--skip-phase2-contact-gate", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    args = parser.parse_args()

    request_path = _resolve(args.request)
    contract_path = _resolve(args.contract)
    manifest_path = _resolve(args.manifest)
    dataset_path = _resolve(args.dataset)
    readiness = readiness_gate.build_report(
        request_path=request_path,
        contract_path=contract_path,
        manifest_path=manifest_path,
        dataset_path=dataset_path,
        min_strict_successes=args.min_strict_successes,
        negative_control_id=args.negative_control_id,
        skip_phase2=args.skip_phase2_contact_gate,
    )

    print("[v0-policy-api-review] readiness_status=" + str(readiness.get("status")))
    if readiness.get("status") != "READY":
        packet = _build_blocked_packet(readiness, dataset_path)
        print("[v0-policy-api-review] facts=" + json.dumps(packet, indent=2, sort_keys=True))
        print("[v0-policy-api-review] BLOCKED")
        for blocker in readiness.get("blockers", []):
            print(f"- {blocker}")
        print(f"[v0-policy-api-review] next_action={readiness.get('next_action')}")
        return 1

    packet = _build_packet(readiness, dataset_path)
    packet["side_effects"] = _side_effects(writes_review_artifacts=not args.no_output)
    if args.no_output:
        print("[v0-policy-api-review] facts=" + json.dumps(packet, indent=2, sort_keys=True))
        print("[v0-policy-api-review] READY_FOR_POLICY_API_REVIEW")
        return 0

    output_json = _resolve(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    output_md = _resolve(args.output_md)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_render_markdown(packet), encoding="utf-8")
    print(f"[v0-policy-api-review] wrote JSON: {_rel(output_json)}")
    print(f"[v0-policy-api-review] wrote Markdown: {_rel(output_md)}")
    print("[v0-policy-api-review] READY_FOR_POLICY_API_REVIEW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
