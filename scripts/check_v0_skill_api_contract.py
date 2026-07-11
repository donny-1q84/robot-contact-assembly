#!/usr/bin/env python3
"""Validate the V0 skill API and robot-adapter contract.

This is an offline contract check. It does not call Brev, Isaac, ROS, or any
robot. Its purpose is to keep the project boundary explicit before learned
policy, VLM, ROS 2, or external robot adapter work starts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = REPO_ROOT / "configs" / "v0_skill_api_contract.json"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root must be an object: {_rel(path)}")
    return payload


def _list_field(payload: dict[str, Any], key: str, failures: list[str]) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        failures.append(f"{key} must be a list")
        return []
    return value


def _require_list_items(
    *,
    name: str,
    values: list[Any],
    required: set[str],
    failures: list[str],
) -> None:
    parsed = {str(value) for value in values}
    missing = sorted(required - parsed)
    if missing:
        failures.append(f"{name} missing required entries: {', '.join(missing)}")


def build_report(contract_path: Path) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    contract = _load_json(contract_path)

    if contract.get("contract_name") != "v0_contact_rich_assembly_skill_api":
        failures.append("contract_name must be v0_contact_rich_assembly_skill_api")
    if contract.get("task_family") != "peg_in_hole":
        failures.append("task_family must be peg_in_hole")

    language_layer = contract.get("language_layer")
    if not isinstance(language_layer, dict):
        failures.append("language_layer must be an object")
        language_layer = {}
    allowed_outputs = _list_field(language_layer, "allowed_outputs", failures)
    forbidden_outputs = _list_field(language_layer, "forbidden_outputs", failures)
    _require_list_items(
        name="language_layer.allowed_outputs",
        values=allowed_outputs,
        required={"task_parameters", "skill_selection", "failure_explanation_request"},
        failures=failures,
    )
    _require_list_items(
        name="language_layer.forbidden_outputs",
        values=forbidden_outputs,
        required={"raw_joint_targets", "direct_cartesian_servo_commands", "direct_force_commands"},
        failures=failures,
    )

    normalized = contract.get("normalized_task_parameters")
    if not isinstance(normalized, dict):
        failures.append("normalized_task_parameters must be an object")
        normalized = {}
    _require_list_items(
        name="normalized_task_parameters.required",
        values=_list_field(normalized, "required", failures),
        required={"object_id", "socket_id", "target_pose_frame", "tolerance_profile", "validation_profile"},
        failures=failures,
    )

    skill = contract.get("skill")
    if not isinstance(skill, dict):
        failures.append("skill must be an object")
        skill = {}
    if skill.get("skill_id") != "peg_in_hole":
        failures.append("skill.skill_id must be peg_in_hole")
    _require_list_items(
        name="skill.allowed_controller_modes",
        values=_list_field(skill, "allowed_controller_modes", failures),
        required={"scripted_success_baseline", "residual_policy_over_scripted_baseline"},
        failures=failures,
    )
    _require_list_items(
        name="skill.disallowed_controller_modes",
        values=_list_field(skill, "disallowed_controller_modes", failures),
        required={"language_to_raw_joint_control", "vlm_to_raw_joint_control"},
        failures=failures,
    )
    _require_list_items(
        name="skill.required_phases",
        values=_list_field(skill, "required_phases", failures),
        required={"approach", "align", "insert", "preload", "recover"},
        failures=failures,
    )

    validator = contract.get("semantic_validator")
    if not isinstance(validator, dict):
        failures.append("semantic_validator must be an object")
        validator = {}
    required_scripts = [str(value) for value in _list_field(validator, "required_scripts", failures)]
    _require_list_items(
        name="semantic_validator.required_scripts",
        values=required_scripts,
        required={
            "scripts/check_peg_in_hole_video_candidate.py",
            "scripts/check_final_contact_boundary_diagnostic.py",
            "scripts/audit_trace_frame_alignment.py",
            "scripts/check_success_variation_batch_results.py",
            "scripts/audit_success_variation_assumptions.py",
        },
        failures=failures,
    )
    for script in required_scripts:
        script_path = REPO_ROOT / script
        if not script_path.is_file():
            failures.append(f"semantic validator script is missing: {script}")

    promotion = contract.get("promotion_gates")
    if not isinstance(promotion, dict):
        failures.append("promotion_gates must be an object")
        promotion = {}
    required_true_gates = {
        "requires_phase2_contact_gate_pass",
        "requires_success_variation_result_gate_pass",
        "requires_post_batch_assumption_audit_pass",
        "requires_negative_control_fail_closed",
        "requires_no_missing_planned_traces",
        "requires_dataset_review_before_policy_training",
    }
    for gate_name in sorted(required_true_gates):
        if promotion.get(gate_name) is not True:
            failures.append(f"promotion_gates.{gate_name} must be true")
    min_strict = promotion.get("requires_min_strict_success_traces")
    if not isinstance(min_strict, int) or min_strict < 5:
        failures.append("promotion_gates.requires_min_strict_success_traces must be an integer >= 5")
    _require_list_items(
        name="promotion_gates.requires_strict_success_variation_coverage_groups",
        values=_list_field(promotion, "requires_strict_success_variation_coverage_groups", failures),
        required={"seed_or_reset", "socket_x", "socket_y", "socket_z"},
        failures=failures,
    )

    adapter = contract.get("robot_adapter_contract")
    if not isinstance(adapter, dict):
        failures.append("robot_adapter_contract must be an object")
        adapter = {}
    if adapter.get("portability_rule") != "new_robot_requires_adapter_calibration_and_revalidation":
        failures.append("robot_adapter_contract.portability_rule must require adapter calibration and revalidation")
    _require_list_items(
        name="robot_adapter_contract.required_model_sources",
        values=_list_field(adapter, "required_model_sources", failures),
        required={"robot_urdf_or_usd", "joint_limits", "tool_geometry", "tcp_transform", "controller_interface_spec"},
        failures=failures,
    )
    _require_list_items(
        name="robot_adapter_contract.required_calibration",
        values=_list_field(adapter, "required_calibration", failures),
        required={"base_frame_alignment", "tool_center_point", "socket_fixture_frame"},
        failures=failures,
    )
    _require_list_items(
        name="robot_adapter_contract.required_safety_gates",
        values=_list_field(adapter, "required_safety_gates", failures),
        required={
            "joint_limit_check",
            "workspace_limit_check",
            "collision_or_clearance_check",
            "controller_timeout",
            "emergency_stop_path",
            "low_speed_contact_validation",
        },
        failures=failures,
    )
    _require_list_items(
        name="robot_adapter_contract.required_command_contract",
        values=_list_field(adapter, "required_command_contract", failures),
        required={
            "skill_target_schema",
            "command_frame",
            "command_units",
            "control_mode",
            "feedback_fields",
            "abort_conditions",
            "rate_limits",
        },
        failures=failures,
    )
    _require_list_items(
        name="robot_adapter_contract.required_frame_contract",
        values=_list_field(adapter, "required_frame_contract", failures),
        required={
            "base_frame",
            "tool_frame",
            "tcp_frame",
            "socket_frame",
            "transform_source",
            "timestamp_source",
        },
        failures=failures,
    )
    _require_list_items(
        name="robot_adapter_contract.required_runtime_guards",
        values=_list_field(adapter, "required_runtime_guards", failures),
        required={
            "max_translation_step_m",
            "max_rotation_step_rad",
            "max_joint_delta_rad",
            "command_timeout_s",
            "stale_state_timeout_s",
            "abort_on_fault",
            "low_speed_mode_required",
        },
        failures=failures,
    )
    ros2_interfaces = adapter.get("ros2_interfaces")
    if not isinstance(ros2_interfaces, list):
        failures.append("robot_adapter_contract.ros2_interfaces must be a list")
        ros2_interfaces = []
    required_ros2 = {"joint_trajectory_action", "joint_state_feedback", "skill_status"}
    seen_ros2 = {
        str(item.get("name"))
        for item in ros2_interfaces
        if isinstance(item, dict) and item.get("required_for_external_robot") is True
    }
    missing_ros2 = sorted(required_ros2 - seen_ros2)
    if missing_ros2:
        failures.append("required ROS 2 interfaces missing or not required: " + ", ".join(missing_ros2))

    not_claims = [str(value) for value in _list_field(contract, "not_claims", failures)]
    _require_list_items(
        name="not_claims",
        values=not_claims,
        required={
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a direct low-level VLM controller",
        },
        failures=failures,
    )

    if "raw_joint_targets" not in forbidden_outputs:
        warnings.append("language layer should explicitly forbid raw_joint_targets")

    return {
        "contract": _rel(contract_path),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "contract_name": contract.get("contract_name"),
        "task_family": contract.get("task_family"),
        "skill_id": skill.get("skill_id"),
        "min_strict_success_traces": min_strict,
        "required_ros2_interfaces": sorted(seen_ros2),
        "not_claims": not_claims,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path, nargs="?", default=DEFAULT_CONTRACT)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    contract_path = args.contract.expanduser()
    if not contract_path.is_absolute():
        contract_path = REPO_ROOT / contract_path

    report = build_report(contract_path)
    if args.output_json is not None:
        output_json = args.output_json.expanduser()
        if not output_json.is_absolute():
            output_json = REPO_ROOT / output_json
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-skill-api-contract] wrote JSON: {_rel(output_json)}")

    print("[v0-skill-api-contract] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "PASS":
        print("[v0-skill-api-contract] PASS")
        return 0

    print("[v0-skill-api-contract] FAIL")
    for failure in report["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
