#!/usr/bin/env python3
"""Validate an external-robot adapter manifest for the V0 skill API.

This is an offline, read-only gate. It does not call Brev, Isaac, ROS, a
vendor SDK, or any robot. Its purpose is to keep external-arm portability
behind robot-specific model, calibration, safety, interface, and revalidation
evidence.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_v0_skill_api_contract as skill_contract_gate  # noqa: E402


DEFAULT_ADAPTER = REPO_ROOT / "configs" / "v0_external_robot_adapter.template.json"

REQUIRED_MODEL_SOURCES = {
    "robot_urdf_or_usd",
    "joint_limits",
    "tool_geometry",
    "tcp_transform",
    "controller_interface_spec",
}
REQUIRED_CALIBRATION = {
    "base_frame_alignment",
    "tool_center_point",
    "socket_fixture_frame",
}
REQUIRED_SAFETY = {
    "joint_limit_check",
    "workspace_limit_check",
    "collision_or_clearance_check",
    "controller_timeout",
    "emergency_stop_path",
    "low_speed_contact_validation",
}
REQUIRED_ROS2 = {
    "joint_trajectory_action",
    "joint_state_feedback",
    "skill_status",
}
REQUIRED_COMMAND_CONTRACT = {
    "skill_target_schema",
    "command_frame",
    "command_units",
    "control_mode",
    "feedback_fields",
    "abort_conditions",
    "rate_limits",
}
REQUIRED_FRAME_CONTRACT = {
    "base_frame",
    "tool_frame",
    "tcp_frame",
    "socket_frame",
    "transform_source",
    "timestamp_source",
}
REQUIRED_RUNTIME_GUARDS = {
    "max_translation_step_m",
    "max_rotation_step_rad",
    "max_joint_delta_rad",
    "command_timeout_s",
    "stale_state_timeout_s",
    "abort_on_fault",
    "low_speed_mode_required",
}
REQUIRED_POSITIVE_RUNTIME_GUARDS = {
    "max_translation_step_m",
    "max_rotation_step_rad",
    "max_joint_delta_rad",
    "command_timeout_s",
    "stale_state_timeout_s",
}
REQUIRED_TRUE_RUNTIME_GUARDS = {
    "abort_on_fault",
    "low_speed_mode_required",
}
REQUIRED_REVALIDATION = {
    "phase2_contact_gate_equivalent",
    "strict_success_variation_batch",
    "negative_control_fail_closed",
    "low_speed_hardware_contact_trial",
}
REQUIRED_ALWAYS_NOT_CLAIMS = {
    "not universal cross-robot-ready",
    "not direct drop-in precision on another robot arm",
}
REQUIRED_BLOCKED_NOT_CLAIMS = {
    "not ready for hardware execution",
    "not verified on this robot",
    "not sim-to-real",
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


def _object(value: Any, name: str, failures: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        failures.append(f"{name} must be an object")
        return {}
    return value


def _missing_keys(value: dict[str, Any], required: set[str]) -> list[str]:
    return sorted(required - set(value))


def _evidence_value_present(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value.get("path") or value.get("uri") or value.get("source") or value.get("result"))
    if isinstance(value, list):
        return bool(value)
    return value is not None


def _check_evidence_map(
    *,
    name: str,
    payload: dict[str, Any],
    required: set[str],
    ready: bool,
    failures: list[str],
    blockers: list[str],
) -> None:
    missing = _missing_keys(payload, required)
    if missing:
        failures.append(f"{name} missing required entries: {', '.join(missing)}")
    for key in sorted(required & set(payload)):
        if not _evidence_value_present(payload.get(key)):
            blockers.append(f"{name}.{key} evidence is missing")
    if ready:
        for key in sorted(required & set(payload)):
            value = payload.get(key)
            if isinstance(value, str) and value and not _resolve(Path(value)).exists():
                blockers.append(f"{name}.{key} evidence path does not exist: {value}")


def _check_ros2_interfaces(
    *,
    payload: dict[str, Any],
    ready: bool,
    failures: list[str],
    blockers: list[str],
) -> None:
    missing = _missing_keys(payload, REQUIRED_ROS2)
    if missing:
        failures.append("ros2_interfaces missing required entries: " + ", ".join(missing))
    for name in sorted(REQUIRED_ROS2 & set(payload)):
        spec = payload.get(name)
        if not isinstance(spec, dict):
            failures.append(f"ros2_interfaces.{name} must be an object")
            continue
        if not _evidence_value_present(spec.get("interface")):
            blockers.append(f"ros2_interfaces.{name}.interface is missing")
        if spec.get("validated") is not True:
            blockers.append(f"ros2_interfaces.{name}.validated must be true before external robot use")
        if ready and isinstance(spec.get("interface"), str) and not spec["interface"].strip():
            blockers.append(f"ros2_interfaces.{name}.interface is blank")


def _check_required_contract_values(
    *,
    name: str,
    payload: dict[str, Any],
    required: set[str],
    failures: list[str],
    blockers: list[str],
) -> None:
    missing = _missing_keys(payload, required)
    if missing:
        failures.append(f"{name} missing required entries: {', '.join(missing)}")
    for key in sorted(required & set(payload)):
        if not _evidence_value_present(payload.get(key)):
            blockers.append(f"{name}.{key} is missing")


def _check_runtime_guards(
    *,
    payload: dict[str, Any],
    failures: list[str],
    blockers: list[str],
) -> None:
    missing = _missing_keys(payload, REQUIRED_RUNTIME_GUARDS)
    if missing:
        failures.append("runtime_guards missing required entries: " + ", ".join(missing))
    for key in sorted(REQUIRED_RUNTIME_GUARDS & set(payload)):
        value = payload.get(key)
        if not _evidence_value_present(value):
            blockers.append(f"runtime_guards.{key} is missing")
    for key in sorted(REQUIRED_POSITIVE_RUNTIME_GUARDS & set(payload)):
        value = payload.get(key)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            failures.append(f"runtime_guards.{key} must be a positive finite number")
            continue
        if not math.isfinite(parsed) or parsed <= 0.0:
            failures.append(f"runtime_guards.{key} must be a positive finite number")
    for key in sorted(REQUIRED_TRUE_RUNTIME_GUARDS & set(payload)):
        if payload.get(key) is not True:
            blockers.append(f"runtime_guards.{key} must be true before external robot use")


def build_report(adapter_path: Path) -> dict[str, Any]:
    adapter_path = _resolve(adapter_path)
    failures: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    adapter = _load_json(adapter_path)

    if adapter.get("skill_id") != "peg_in_hole":
        failures.append("skill_id must be peg_in_hole")

    ready = adapter.get("ready_for_external_robot")
    if not isinstance(ready, bool):
        failures.append("ready_for_external_robot must be a boolean")
        ready = False

    contract_ref = adapter.get("skill_api_contract")
    if not isinstance(contract_ref, str) or not contract_ref:
        failures.append("skill_api_contract must reference configs/v0_skill_api_contract.json")
        contract_ref = "configs/v0_skill_api_contract.json"
    contract_path = _resolve(Path(contract_ref))
    if _rel(contract_path) != "configs/v0_skill_api_contract.json":
        failures.append("skill_api_contract must be configs/v0_skill_api_contract.json")
    contract_report = skill_contract_gate.build_report(contract_path)
    if contract_report.get("status") != "PASS":
        failures.extend("skill contract: " + str(item) for item in contract_report.get("failures", []))

    target_robot = _object(adapter.get("target_robot"), "target_robot", failures)
    for key in ("robot_id", "robot_family", "control_stack", "end_effector"):
        if not _evidence_value_present(target_robot.get(key)):
            blockers.append(f"target_robot.{key} is missing")
    if target_robot.get("robot_id") == "replace_with_robot_id":
        blockers.append("target_robot.robot_id is still the template placeholder")

    _check_evidence_map(
        name="model_sources",
        payload=_object(adapter.get("model_sources"), "model_sources", failures),
        required=REQUIRED_MODEL_SOURCES,
        ready=bool(ready),
        failures=failures,
        blockers=blockers,
    )
    _check_evidence_map(
        name="calibration_evidence",
        payload=_object(adapter.get("calibration_evidence"), "calibration_evidence", failures),
        required=REQUIRED_CALIBRATION,
        ready=bool(ready),
        failures=failures,
        blockers=blockers,
    )
    _check_evidence_map(
        name="safety_evidence",
        payload=_object(adapter.get("safety_evidence"), "safety_evidence", failures),
        required=REQUIRED_SAFETY,
        ready=bool(ready),
        failures=failures,
        blockers=blockers,
    )
    _check_ros2_interfaces(
        payload=_object(adapter.get("ros2_interfaces"), "ros2_interfaces", failures),
        ready=bool(ready),
        failures=failures,
        blockers=blockers,
    )
    _check_required_contract_values(
        name="command_contract",
        payload=_object(adapter.get("command_contract"), "command_contract", failures),
        required=REQUIRED_COMMAND_CONTRACT,
        failures=failures,
        blockers=blockers,
    )
    _check_required_contract_values(
        name="frame_contract",
        payload=_object(adapter.get("frame_contract"), "frame_contract", failures),
        required=REQUIRED_FRAME_CONTRACT,
        failures=failures,
        blockers=blockers,
    )
    _check_runtime_guards(
        payload=_object(adapter.get("runtime_guards"), "runtime_guards", failures),
        failures=failures,
        blockers=blockers,
    )
    _check_evidence_map(
        name="revalidation_evidence",
        payload=_object(adapter.get("revalidation_evidence"), "revalidation_evidence", failures),
        required=REQUIRED_REVALIDATION,
        ready=bool(ready),
        failures=failures,
        blockers=blockers,
    )

    not_claims = adapter.get("not_claims")
    if not isinstance(not_claims, list):
        failures.append("not_claims must be a list")
        not_claims = []
    parsed_not_claims = {str(value) for value in not_claims}
    required_not_claims = set(REQUIRED_ALWAYS_NOT_CLAIMS)
    if not ready:
        required_not_claims.update(REQUIRED_BLOCKED_NOT_CLAIMS)
    missing_not_claims = sorted(required_not_claims - parsed_not_claims)
    if missing_not_claims:
        failures.append("not_claims missing required entries: " + ", ".join(missing_not_claims))

    if ready and blockers:
        failures.append("ready_for_external_robot cannot be true while adapter evidence blockers remain")
    if ready:
        warnings.append("READY only applies to this named robot adapter, not to arbitrary robot arms")

    unique_failures = list(dict.fromkeys(failures))
    unique_blockers = list(dict.fromkeys(blockers))
    status = "FAIL" if unique_failures else ("READY" if ready and not unique_blockers else "BLOCKED")
    next_action = "ready_for_low_speed_external_robot_review"
    if status == "BLOCKED":
        next_action = "fill_robot_specific_model_calibration_safety_ros2_and_revalidation_evidence"
    elif status == "FAIL":
        next_action = "fix_adapter_manifest_contract_errors"

    return {
        "adapter": _rel(adapter_path),
        "adapter_name": adapter.get("adapter_name"),
        "status": status,
        "ready_for_external_robot": bool(ready),
        "skill_api_contract": _rel(contract_path),
        "skill_contract_status": contract_report.get("status"),
        "target_robot": target_robot,
        "failures": unique_failures,
        "blockers": unique_blockers,
        "warnings": warnings,
        "next_action": next_action,
        "not_claims": list(not_claims),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("adapter", type=Path, nargs="?", default=DEFAULT_ADAPTER)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_report(args.adapter)
    if args.output_json is not None:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-robot-adapter] wrote JSON: {_rel(output_json)}")

    print("[v0-robot-adapter] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "READY":
        print("[v0-robot-adapter] READY")
        return 0
    if report["status"] == "BLOCKED":
        print("[v0-robot-adapter] BLOCKED")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
        print(f"[v0-robot-adapter] next_action={report['next_action']}")
        return 1 if args.fail_on_blocked else 0

    print("[v0-robot-adapter] FAIL")
    for failure in report["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
