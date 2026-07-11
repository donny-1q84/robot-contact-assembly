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
import tempfile
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_v0_portability_boundary as portability_gate  # noqa: E402
import plan_v0_robot_adapter_manifest as adapter_planner  # noqa: E402


DEFAULT_REQUEST = portability_gate.DEFAULT_REQUEST
DEFAULT_CONTRACT = portability_gate.DEFAULT_CONTRACT
DEFAULT_MANIFEST = portability_gate.DEFAULT_MANIFEST
DEFAULT_DATASET = portability_gate.DEFAULT_DATASET
DEFAULT_ADAPTER = portability_gate.DEFAULT_ADAPTER
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "reviews" / "v0_portability"
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "review_packet.json"
DEFAULT_OUTPUT_MD = DEFAULT_OUTPUT_DIR / "README.md"
REUSE_SUMMARY = "language/request and skill-target layers are reusable; robot execution is adapter-specific"
TARGET_PREVIEW_NOT_CLAIMS = [
    "not ready for hardware execution",
    "not autonomous hardware execution approval",
    "not verified on this robot",
    "not sim-to-real",
    "not direct drop-in precision on another robot arm",
]
ADAPTER_WORKPLAN_STEPS = [
    "name_target_robot_and_write_adapter_manifest",
    "fill_robot_model_joint_limits_tool_tcp_and_controller_sources",
    "fill_base_tool_socket_and_calibration_error_evidence",
    "validate_joint_cartesian_tool_state_and_force_feedback_interfaces",
    "fill_safety_timeout_workspace_collision_force_limit_and_low_speed_contact_evidence",
    "run_low_speed_no_contact_dry_run_before_any_contact_trial",
    "complete_v0_success_variation_batch_before_policy_or_external_robot_claims",
    "prove_adapter_frame_round_trip_and_named_robot_negative_control",
    "rerun_adapter_contract_and_portability_boundary_gates",
    "perform_manual_low_speed_named_robot_review_only_after_all_gates_are_ready",
]


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


def _adapter_identity_from_preview(packet: dict[str, Any]) -> tuple[str, str, str]:
    preview = packet.get("target_adapter_preview")
    if isinstance(preview, dict):
        target = preview.get("target_robot")
        if isinstance(target, dict):
            robot_id = str(target.get("robot_id") or "<target_robot_id>")
            robot_family = str(target.get("robot_family") or "<target_robot_family>")
            end_effector = str(target.get("end_effector") or "<tool_or_gripper>")
            return robot_id, robot_family, end_effector
    return "<target_robot_id>", "<target_robot_family>", "<tool_or_gripper>"


def _target_adapter_output_path(robot_id: str) -> str:
    if robot_id.startswith("<"):
        return "artifacts/adapters/v0_external_robot_adapter_<target_robot_id>.json"
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in robot_id)
    return f"artifacts/adapters/v0_external_robot_adapter_{safe}.json"


def _next_commands(packet: dict[str, Any]) -> dict[str, list[str]]:
    adapter = str(packet["inputs"]["adapter"])
    manifest = str(packet["inputs"]["manifest"])
    dataset = str(packet["inputs"]["dataset"])
    robot_id, robot_family, end_effector = _adapter_identity_from_preview(packet)
    return {
        "preview_named_adapter_manifest": [
            "python3",
            "scripts/plan_v0_robot_adapter_manifest.py",
            "--robot-id",
            robot_id,
            "--robot-family",
            robot_family,
            "--end-effector",
            end_effector,
            "--joint-trajectory-action",
            "<joint_trajectory_action_or_vendor_command>",
            "--joint-state-feedback",
            "<joint_state_feedback>",
            "--ee-pose-feedback",
            "<ee_pose_feedback>",
            "--cartesian-command-or-ik",
            "<cartesian_command_or_ik>",
            "--end-effector-command",
            "<end_effector_command>",
            "--force-torque-or-contact-feedback",
            "<force_torque_or_contact_feedback>",
            "--no-output",
        ],
        "write_named_adapter_manifest": [
            "python3",
            "scripts/plan_v0_robot_adapter_manifest.py",
            "--robot-id",
            robot_id,
            "--robot-family",
            robot_family,
            "--end-effector",
            end_effector,
            "--joint-trajectory-action",
            "<joint_trajectory_action_or_vendor_command>",
            "--joint-state-feedback",
            "<joint_state_feedback>",
            "--ee-pose-feedback",
            "<ee_pose_feedback>",
            "--cartesian-command-or-ik",
            "<cartesian_command_or_ik>",
            "--end-effector-command",
            "<end_effector_command>",
            "--force-torque-or-contact-feedback",
            "<force_torque_or_contact_feedback>",
            "--output-json",
            _target_adapter_output_path(robot_id),
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


def _provided(*values: str | None) -> bool:
    return any(value is not None and bool(value.strip()) for value in values)


def _target_adapter_preview(
    *,
    target_robot_id: str | None,
    target_robot_family: str | None,
    control_stack: str,
    end_effector: str | None,
    joint_trajectory_action: str | None,
    joint_state_feedback: str | None,
    ee_pose_feedback: str | None,
    cartesian_command_or_ik: str | None,
    end_effector_command: str | None,
    force_torque_or_contact_feedback: str | None,
    skill_status: str | None,
) -> dict[str, Any]:
    if not _provided(
        target_robot_id,
        target_robot_family,
        end_effector,
        joint_trajectory_action,
        joint_state_feedback,
        ee_pose_feedback,
        cartesian_command_or_ik,
        end_effector_command,
        force_torque_or_contact_feedback,
        skill_status,
    ):
        return {
            "status": "NOT_PROVIDED",
            "provided": False,
            "target_robot": None,
            "direct_use_ready": False,
            "transfer_readiness_level": "L0_TEMPLATE_OR_INCOMPLETE_ADAPTER",
            "adapter_contract_status": None,
            "blocker_count": None,
            "top_blockers": [],
            "next_action": "provide_named_target_robot_identity_before_external_arm_planning",
            "not_claims": TARGET_PREVIEW_NOT_CLAIMS,
        }

    missing = []
    if not target_robot_id or not target_robot_id.strip():
        missing.append("target_robot_id")
    if not target_robot_family or not target_robot_family.strip():
        missing.append("target_robot_family")
    if not end_effector or not end_effector.strip():
        missing.append("end_effector")
    if missing:
        return {
            "status": "BLOCKED_INCOMPLETE_TARGET",
            "provided": True,
            "target_robot": {
                "robot_id": target_robot_id,
                "robot_family": target_robot_family,
                "control_stack": control_stack,
                "end_effector": end_effector,
            },
            "direct_use_ready": False,
            "transfer_readiness_level": "L0_TEMPLATE_OR_INCOMPLETE_ADAPTER",
            "failures": [f"missing required target field: {name}" for name in missing],
            "adapter_contract_status": None,
            "blocker_count": None,
            "top_blockers": [],
            "next_action": "provide_robot_id_robot_family_and_end_effector",
            "not_claims": TARGET_PREVIEW_NOT_CLAIMS,
        }

    adapter = adapter_planner.build_adapter(
        template_path=adapter_planner.DEFAULT_TEMPLATE,
        robot_id=target_robot_id.strip(),
        robot_family=target_robot_family.strip(),
        control_stack=control_stack.strip(),
        end_effector=end_effector.strip(),
        joint_trajectory_action=joint_trajectory_action,
        joint_state_feedback=joint_state_feedback,
        ee_pose_feedback=ee_pose_feedback,
        cartesian_command_or_ik=cartesian_command_or_ik,
        end_effector_command=end_effector_command,
        force_torque_or_contact_feedback=force_torque_or_contact_feedback,
        skill_status=skill_status,
    )
    with tempfile.TemporaryDirectory(prefix="rca-adapter-preview-") as tmp_dir:
        preview_path = Path(tmp_dir) / "adapter.json"
        preview_path.write_text(json.dumps(adapter, indent=2, sort_keys=True), encoding="utf-8")
        checker = portability_gate.adapter_gate.build_report(preview_path)

    blockers = checker.get("blockers") if isinstance(checker.get("blockers"), list) else []
    return {
        "status": "PASS_SAFE_BLOCKED" if checker.get("status") == "BLOCKED" else checker.get("status"),
        "provided": True,
        "target_robot": adapter["target_robot"],
        "planned_adapter_name": adapter["adapter_name"],
        "ready_for_external_robot": adapter["ready_for_external_robot"],
        "direct_use_ready": False,
        "transfer_readiness_level": "L1_NAMED_ADAPTER_DRAFT_BLOCKED",
        "ready_for_hardware_execution": False,
        "manual_hardware_approval_required": True,
        "review_scope": "named_robot_low_speed_review_only",
        "adapter_contract_status": checker.get("status"),
        "blocker_count": len(blockers),
        "top_blockers": blockers[:8],
        "next_action": "fill_named_robot_adapter_evidence_then_rerun_portability_review",
        "planned_adapter": adapter,
        "not_claims": TARGET_PREVIEW_NOT_CLAIMS,
    }


def _adapter_workplan(boundary: dict[str, Any], target_preview: dict[str, Any]) -> dict[str, Any]:
    boundary_adapter_blockers = [
        str(item).removeprefix("robot_adapter: ")
        for item in boundary.get("blockers", [])
        if str(item).startswith("robot_adapter:")
    ]
    preview_top_blockers = (
        target_preview.get("top_blockers")
        if isinstance(target_preview.get("top_blockers"), list)
        else []
    )
    use_preview_blockers = bool(target_preview.get("provided")) and bool(preview_top_blockers)
    adapter_blocker_count = (
        int(target_preview.get("blocker_count"))
        if use_preview_blockers and isinstance(target_preview.get("blocker_count"), int)
        else len(boundary_adapter_blockers)
    )
    adapter_top_blockers = (
        [str(item) for item in preview_top_blockers[:12]]
        if use_preview_blockers
        else boundary_adapter_blockers[:12]
    )
    skill_blockers = [
        str(item).removeprefix("v0_skill_readiness: ")
        for item in boundary.get("blockers", [])
        if str(item).startswith("v0_skill_readiness:")
    ]
    evidence_groups = {
        "model_sources": sorted(portability_gate.adapter_gate.REQUIRED_MODEL_SOURCES),
        "calibration_evidence": sorted(portability_gate.adapter_gate.REQUIRED_CALIBRATION),
        "safety_evidence": sorted(portability_gate.adapter_gate.REQUIRED_SAFETY),
        "ros2_interfaces": sorted(portability_gate.adapter_gate.REQUIRED_ROS2),
        "command_contract": sorted(portability_gate.adapter_gate.REQUIRED_COMMAND_CONTRACT),
        "frame_contract": sorted(portability_gate.adapter_gate.REQUIRED_FRAME_CONTRACT),
        "runtime_guards": sorted(portability_gate.adapter_gate.REQUIRED_RUNTIME_GUARDS),
        "revalidation_evidence": sorted(portability_gate.adapter_gate.REQUIRED_REVALIDATION),
    }
    return {
        "status": (
            "READY_FOR_NAMED_ROBOT_LOW_SPEED_REVIEW"
            if boundary.get("status") == "READY"
            else "BLOCKED_NOT_DROP_IN"
        ),
        "direct_drop_in_answer": "NO_DIRECT_DROP_IN",
        "direct_use_ready": False,
        "transfer_readiness_level": boundary.get("transfer_readiness_level"),
        "transfer_required_before_use": boundary.get("transfer_required_before_use"),
        "ready_for_named_robot_low_speed_review": boundary.get("ready_for_named_robot_low_speed_review"),
        "ready_for_hardware_execution": False,
        "manual_hardware_approval_required": True,
        "review_scope": boundary.get("review_scope"),
        "execution_boundary": boundary["portability_boundary"],
        "target_preview_status": target_preview.get("status"),
        "target_robot": target_preview.get("target_robot"),
        "reusable_without_robot_rewrite": boundary["reusable_layers"],
        "must_be_robot_specific": boundary["robot_specific_layers"],
        "required_evidence_groups": evidence_groups,
        "minimum_ordered_steps": ADAPTER_WORKPLAN_STEPS,
        "current_skill_blocker_count": len(skill_blockers),
        "current_adapter_blocker_count": adapter_blocker_count,
        "top_skill_blockers": skill_blockers[:8],
        "top_adapter_blockers": adapter_top_blockers,
        "next_action": boundary["next_action"],
        "not_claims": [
            "not a universal robot-arm policy",
            "not direct drop-in precision on another robot arm",
            "not ready without named robot calibration and revalidation",
            "not autonomous hardware execution approval",
            "not hardware execution approval",
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
    target_robot_id: str | None,
    target_robot_family: str | None,
    control_stack: str,
    end_effector: str | None,
    joint_trajectory_action: str | None,
    joint_state_feedback: str | None,
    ee_pose_feedback: str | None,
    cartesian_command_or_ik: str | None,
    end_effector_command: str | None,
    force_torque_or_contact_feedback: str | None,
    skill_status: str | None,
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
    target_preview = _target_adapter_preview(
        target_robot_id=target_robot_id,
        target_robot_family=target_robot_family,
        control_stack=control_stack,
        end_effector=end_effector,
        joint_trajectory_action=joint_trajectory_action,
        joint_state_feedback=joint_state_feedback,
        ee_pose_feedback=ee_pose_feedback,
        cartesian_command_or_ik=cartesian_command_or_ik,
        end_effector_command=end_effector_command,
        force_torque_or_contact_feedback=force_torque_or_contact_feedback,
        skill_status=skill_status,
    )
    packet = {
        "packet_name": "v0_cross_robot_portability_review",
        "status": boundary["status"],
        "readiness_label": boundary["readiness_label"],
        "direct_drop_in_answer": "NO_DIRECT_DROP_IN",
        "reuse_summary": REUSE_SUMMARY,
        "universal_drop_in_ready": False,
        "direct_use_ready": False,
        "transfer_readiness_level": boundary["transfer_readiness_level"],
        "transfer_required_before_use": boundary["transfer_required_before_use"],
        "named_robot_ready": boundary["named_robot_ready"],
        "ready_for_named_robot_low_speed_review": boundary["ready_for_named_robot_low_speed_review"],
        "ready_for_hardware_execution": False,
        "manual_hardware_approval_required": True,
        "review_scope": boundary["review_scope"],
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
        "target_adapter_preview": target_preview,
        "adapter_workplan": _adapter_workplan(boundary, target_preview),
        "reusable_layers": boundary["reusable_layers"],
        "robot_specific_layers": boundary["robot_specific_layers"],
        "current_blockers": boundary["blockers"],
        "manual_review_checklist": [
            "confirm V0 skill readiness is READY from real success-variation traces",
            "confirm the target robot has a named adapter manifest, not the template",
            "confirm URDF/USD, joint limits, TCP, fixture frames, and controller units are robot-specific",
            "confirm joint command, Cartesian or IK, EE pose, tool command, and force/contact feedback interfaces are validated",
            "confirm calibration error bounds and frame round-trip checks are within the named robot limits",
            "confirm low-speed no-contact dry-run passes before any hardware contact trial",
            "confirm low-speed contact safety and abort behavior before hardware contact",
            "confirm strict success variations and fail-closed negative control are rerun for the named robot",
            "confirm a separate human hardware approval exists before any non-review robot execution",
        ],
        "side_effects": {
            "writes_review_artifacts": True,
            "writes_target_adapter_manifest": False,
            "creates_paid_instance": False,
            "runs_remote_code": False,
            "starts_isaac": False,
            "calls_ros_or_robot": False,
        },
        "not_claims": list(boundary["not_claims"])
        + [
            "not a robot driver",
            "not hardware execution approval",
            "not autonomous hardware execution approval",
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
        f"- direct_use_ready: {str(packet['direct_use_ready']).lower()}",
        f"- transfer_readiness_level: {packet['transfer_readiness_level']}",
        f"- reuse_summary: {packet['reuse_summary']}",
        f"- universal_drop_in_ready: {str(packet['universal_drop_in_ready']).lower()}",
        f"- named_robot_ready: {str(packet['named_robot_ready']).lower()}",
        f"- ready_for_hardware_execution: {str(packet['ready_for_hardware_execution']).lower()}",
        f"- review_scope: {packet['review_scope']}",
        f"- target_robot_id: {packet['target_robot_id']}",
        f"- next_action: {packet['gate_summary']['next_action']}",
        "",
        "## Reusable Layers",
        "",
    ]
    lines.extend(f"- {item}" for item in packet["reusable_layers"])
    lines.extend(["", "## Robot-Specific Layers", ""])
    lines.extend(f"- {item}" for item in packet["robot_specific_layers"])
    preview = packet.get("target_adapter_preview") if isinstance(packet.get("target_adapter_preview"), dict) else {}
    lines.extend(
        [
            "",
            "## Target Adapter Preview",
            "",
            f"- status: {preview.get('status')}",
            f"- target_robot: {preview.get('target_robot')}",
            f"- direct_use_ready: {str(preview.get('direct_use_ready')).lower()}",
            f"- transfer_readiness_level: {preview.get('transfer_readiness_level')}",
            f"- adapter_contract_status: {preview.get('adapter_contract_status')}",
            f"- blocker_count: {preview.get('blocker_count')}",
            f"- next_action: {preview.get('next_action')}",
        ]
    )
    top_blockers = preview.get("top_blockers") if isinstance(preview.get("top_blockers"), list) else []
    if top_blockers:
        lines.extend(["", "Top adapter blockers:"])
        lines.extend(f"- {item}" for item in top_blockers)
    workplan = packet.get("adapter_workplan") if isinstance(packet.get("adapter_workplan"), dict) else {}
    lines.extend(
        [
            "",
            "## Adapter Workplan",
            "",
            f"- status: {workplan.get('status')}",
            f"- direct_drop_in_answer: {workplan.get('direct_drop_in_answer')}",
            f"- direct_use_ready: {str(workplan.get('direct_use_ready')).lower()}",
            f"- transfer_readiness_level: {workplan.get('transfer_readiness_level')}",
            f"- ready_for_hardware_execution: {str(workplan.get('ready_for_hardware_execution')).lower()}",
            f"- review_scope: {workplan.get('review_scope')}",
            f"- execution_boundary: {workplan.get('execution_boundary')}",
            "",
            "Minimum ordered steps:",
        ]
    )
    steps = workplan.get("minimum_ordered_steps") if isinstance(workplan.get("minimum_ordered_steps"), list) else []
    lines.extend(f"- {item}" for item in steps)
    evidence_groups = (
        workplan.get("required_evidence_groups")
        if isinstance(workplan.get("required_evidence_groups"), dict)
        else {}
    )
    if evidence_groups:
        lines.extend(["", "Required evidence groups:"])
        for group_name, fields in evidence_groups.items():
            lines.append(f"- {group_name}: {', '.join(fields)}")
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
    parser.add_argument("--target-robot-id")
    parser.add_argument("--target-robot-family")
    parser.add_argument("--control-stack", default="ros2_joint_trajectory_or_vendor_bridge")
    parser.add_argument("--end-effector")
    parser.add_argument("--joint-trajectory-action")
    parser.add_argument("--joint-state-feedback")
    parser.add_argument("--ee-pose-feedback")
    parser.add_argument("--cartesian-command-or-ik")
    parser.add_argument("--end-effector-command")
    parser.add_argument("--force-torque-or-contact-feedback")
    parser.add_argument("--skill-status")
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
        target_robot_id=args.target_robot_id,
        target_robot_family=args.target_robot_family,
        control_stack=args.control_stack,
        end_effector=args.end_effector,
        joint_trajectory_action=args.joint_trajectory_action,
        joint_state_feedback=args.joint_state_feedback,
        ee_pose_feedback=args.ee_pose_feedback,
        cartesian_command_or_ik=args.cartesian_command_or_ik,
        end_effector_command=args.end_effector_command,
        force_torque_or_contact_feedback=args.force_torque_or_contact_feedback,
        skill_status=args.skill_status,
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
    print("[v0-portability-review] target_adapter_preview_status=" + str(packet["target_adapter_preview"]["status"]))
    if packet["status"] != "READY" and args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
