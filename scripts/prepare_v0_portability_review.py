#!/usr/bin/env python3
"""Prepare a V0 cross-robot portability review packet.

This is an offline packaging gate. It combines the V0 skill readiness gate, the
named external-robot adapter contract, and the portability boundary into one
review artifact that answers whether the current system is a direct drop-in for
other robot arms. The universal answer is no: only the language/request and
skill-target layers are reusable by default; each robot still needs its own
adapter, calibration, safety evidence, and revalidation.

It does not call Brev, start Isaac, call ROS, use a vendor SDK, or talk to a
robot.
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

import check_v0_portability_boundary as portability_gate  # noqa: E402


DEFAULT_REQUEST = portability_gate.DEFAULT_REQUEST
DEFAULT_CONTRACT = portability_gate.DEFAULT_CONTRACT
DEFAULT_MANIFEST = portability_gate.DEFAULT_MANIFEST
DEFAULT_DATASET = portability_gate.DEFAULT_DATASET
DEFAULT_ADAPTER = portability_gate.DEFAULT_ADAPTER
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "reviews" / "v0_portability"
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "review_packet.json"
DEFAULT_OUTPUT_MD = DEFAULT_OUTPUT_DIR / "README.md"
REUSE_SUMMARY = "language/request and skill-target layers are reusable; robot execution is adapter-specific"


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


def _command_text(command: list[str]) -> str:
    return " ".join(command)


def _next_commands(packet: dict[str, Any]) -> dict[str, list[str]]:
    adapter = str(packet["inputs"]["adapter"])
    manifest = str(packet["inputs"]["manifest"])
    dataset = str(packet["inputs"]["dataset"])
    return {
        "plan_named_adapter_manifest": [
            "python3",
            "scripts/plan_v0_robot_adapter_manifest.py",
            "--robot-id",
            "<target_robot_id>",
            "--robot-family",
            "<target_robot_family>",
            "--end-effector",
            "<tool_or_gripper>",
        ],
        "check_named_adapter_contract": [
            "python3",
            "scripts/check_v0_robot_adapter_contract.py",
            adapter,
        ],
        "check_portability_boundary": [
            "python3",
            "scripts/check_v0_portability_boundary.py",
            "--manifest",
            manifest,
            "--dataset",
            dataset,
            "--adapter",
            adapter,
        ],
        "unblock_v0_skill_readiness": [
            "python3",
            "scripts/run_success_variation_paid_lifecycle.py",
            "--balance-eur",
            "<current-brev-ui-balance>",
            "--run",
            "--i-understand-this-can-create-paid-instance",
        ],
    }


def build_packet(
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
    boundary = portability_gate.build_report(
        request_path=_resolve(request_path),
        contract_path=_resolve(contract_path),
        manifest_path=_resolve(manifest_path),
        dataset_path=_resolve(dataset_path),
        adapter_path=_resolve(adapter_path),
        min_strict_successes=min_strict_successes,
        negative_control_id=negative_control_id,
        skip_phase2=skip_phase2,
    )
    packet = {
        "packet_name": "v0_cross_robot_portability_review",
        "status": boundary["status"],
        "readiness_label": boundary["readiness_label"],
        "direct_drop_in_answer": "NO_DIRECT_DROP_IN",
        "reuse_summary": REUSE_SUMMARY,
        "universal_drop_in_ready": False,
        "named_robot_ready": boundary["named_robot_ready"],
        "target_robot_id": boundary["target_robot_id"],
        "portability_boundary": boundary["portability_boundary"],
        "inputs": {
            "request": _rel(_resolve(request_path)),
            "contract": _rel(_resolve(contract_path)),
            "manifest": _rel(_resolve(manifest_path)),
            "dataset": _rel(_resolve(dataset_path)),
            "adapter": _rel(_resolve(adapter_path)),
        },
        "gate_summary": {
            "skill_readiness_status": boundary["skill_readiness_status"],
            "adapter_status": boundary["adapter_status"],
            "blocker_count": len(boundary["blockers"]),
            "next_action": boundary["next_action"],
        },
        "reusable_layers": boundary["reusable_layers"],
        "robot_specific_layers": boundary["robot_specific_layers"],
        "current_blockers": boundary["blockers"],
        "manual_review_checklist": [
            "confirm V0 skill readiness is READY from real success-variation traces",
            "confirm the target robot has a named adapter manifest, not the template",
            "confirm URDF/USD, joint limits, TCP, fixture frames, and controller units are robot-specific",
            "confirm low-speed contact safety and abort behavior before hardware contact",
            "confirm strict success variations and fail-closed negative control are rerun for the named robot",
        ],
        "side_effects": {
            "writes_review_artifacts": True,
            "creates_paid_instance": False,
            "runs_remote_code": False,
            "starts_isaac": False,
            "calls_ros_or_robot": False,
        },
        "not_claims": list(boundary["not_claims"])
        + [
            "not a robot driver",
            "not hardware execution approval",
            "not evidence that arbitrary robot arms can be used without adaptation",
        ],
        "boundary_report": boundary,
    }
    packet["next_commands"] = _next_commands(packet)
    return packet


def _render_markdown(packet: dict[str, Any]) -> str:
    lines = [
        "# V0 Cross-Robot Portability Review",
        "",
        f"- status: {packet['status']}",
        f"- readiness_label: {packet['readiness_label']}",
        f"- direct_drop_in_answer: {packet['direct_drop_in_answer']}",
        f"- reuse_summary: {packet['reuse_summary']}",
        f"- universal_drop_in_ready: {str(packet['universal_drop_in_ready']).lower()}",
        f"- named_robot_ready: {str(packet['named_robot_ready']).lower()}",
        f"- target_robot_id: {packet['target_robot_id']}",
        f"- next_action: {packet['gate_summary']['next_action']}",
        "",
        "## Reusable Layers",
        "",
    ]
    lines.extend(f"- {item}" for item in packet["reusable_layers"])
    lines.extend(["", "## Robot-Specific Layers", ""])
    lines.extend(f"- {item}" for item in packet["robot_specific_layers"])
    lines.extend(["", "## Current Blockers", ""])
    if packet["current_blockers"]:
        lines.extend(f"- {item}" for item in packet["current_blockers"])
    else:
        lines.append("- none for the named robot low-speed review gate")
    lines.extend(["", "## Commands", "", "```bash"])
    for command in packet["next_commands"].values():
        lines.append(_command_text(command))
    lines.extend(["```", "", "## Manual Review Checklist", ""])
    lines.extend(f"- {item}" for item in packet["manual_review_checklist"])
    lines.extend(["", "## What This Is Not", ""])
    lines.extend(f"- {item}" for item in packet["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--negative-control-id", default=portability_gate.skill_gate.variation_gate.DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--skip-phase2-contact-gate", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    packet = build_packet(
        request_path=args.request,
        contract_path=args.contract,
        manifest_path=args.manifest,
        dataset_path=args.dataset,
        adapter_path=args.adapter,
        min_strict_successes=max(1, args.min_strict_successes),
        negative_control_id=args.negative_control_id,
        skip_phase2=args.skip_phase2_contact_gate,
    )

    if args.no_output:
        packet["side_effects"]["writes_review_artifacts"] = False
    else:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[v0-portability-review] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(packet), encoding="utf-8")
        print(f"[v0-portability-review] wrote Markdown: {_rel(output_md)}")

    print("[v0-portability-review] facts=" + json.dumps(packet, indent=2, sort_keys=True))
    print("[v0-portability-review] status=" + packet["status"])
    print("[v0-portability-review] readiness_label=" + packet["readiness_label"])
    print("[v0-portability-review] universal_drop_in_ready=false")
    if packet["status"] != "READY" and args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
