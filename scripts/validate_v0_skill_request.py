#!/usr/bin/env python3
"""Validate a V0 high-level skill request against the skill API contract.

This is an offline interface check for the language/planner boundary. It
accepts task parameters and skill selection, but rejects direct low-level
commands such as joint targets, Cartesian servo commands, or force commands.
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
DEFAULT_REQUEST = REPO_ROOT / "configs" / "v0_skill_request.example.json"


DIRECT_COMMAND_KEYS = {
    "raw_joint_targets",
    "joint_targets",
    "raw_joint_velocities",
    "joint_velocities",
    "direct_cartesian_servo_commands",
    "cartesian_servo",
    "direct_force_commands",
    "force_command",
    "wrench_command",
}


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


def _resolve(path: Path) -> Path:
    path = path.expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _find_direct_command_keys(value: Any, *, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            if str(key) in DIRECT_COMMAND_KEYS:
                found.append(path)
            found.extend(_find_direct_command_keys(child, prefix=path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_direct_command_keys(child, prefix=f"{prefix}[{index}]"))
    return found


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value}


def _object(value: Any, name: str, failures: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        failures.append(f"{name} must be an object")
        return {}
    return value


def build_report(request_path: Path, contract_path: Path) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    request = _load_json(request_path)
    contract = _load_json(contract_path)

    direct_keys = _find_direct_command_keys(request)
    if direct_keys:
        failures.append("request contains forbidden direct control keys: " + ", ".join(direct_keys))

    language = _object(contract.get("language_layer"), "contract.language_layer", failures)
    forbidden_outputs = _string_set(language.get("forbidden_outputs"))
    if not {"raw_joint_targets", "direct_cartesian_servo_commands", "direct_force_commands"}.issubset(
        forbidden_outputs
    ):
        failures.append("contract must forbid raw joint, Cartesian servo, and force command outputs")

    task_parameters = _object(request.get("task_parameters"), "request.task_parameters", failures)
    normalized = _object(contract.get("normalized_task_parameters"), "contract.normalized_task_parameters", failures)
    required_params = _string_set(normalized.get("required"))
    for key in sorted(required_params):
        if key not in task_parameters:
            failures.append(f"request.task_parameters missing required field: {key}")
        elif task_parameters.get(key) in (None, ""):
            failures.append(f"request.task_parameters.{key} must be non-empty")

    skill_selection = _object(request.get("skill_selection"), "request.skill_selection", failures)
    skill_contract = _object(contract.get("skill"), "contract.skill", failures)
    expected_skill_id = skill_contract.get("skill_id")
    skill_id = skill_selection.get("skill_id")
    if skill_id != expected_skill_id:
        failures.append(f"skill_selection.skill_id must be {expected_skill_id!r}, got {skill_id!r}")

    allowed_modes = _string_set(skill_contract.get("allowed_controller_modes"))
    controller_mode = skill_selection.get("controller_mode")
    if controller_mode not in allowed_modes:
        failures.append(
            "skill_selection.controller_mode must be one of "
            + ", ".join(sorted(allowed_modes))
            + f"; got {controller_mode!r}"
        )

    disallowed_modes = _string_set(skill_contract.get("disallowed_controller_modes"))
    if controller_mode in disallowed_modes:
        failures.append(f"skill_selection.controller_mode is explicitly disallowed: {controller_mode}")

    promotion = _object(contract.get("promotion_gates"), "contract.promotion_gates", failures)
    if promotion.get("requires_success_variation_result_gate_pass") is not True:
        failures.append("contract must require success-variation result gate before policy/API promotion")
    if promotion.get("requires_negative_control_fail_closed") is not True:
        failures.append("contract must require fail-closed negative control")

    adapter = _object(contract.get("robot_adapter_contract"), "contract.robot_adapter_contract", failures)
    if adapter.get("portability_rule") != "new_robot_requires_adapter_calibration_and_revalidation":
        failures.append("contract must require calibration and revalidation for a new robot adapter")

    execution_policy = request.get("execution_policy")
    if execution_policy is not None and not isinstance(execution_policy, dict):
        failures.append("request.execution_policy must be an object when provided")
        execution_policy = {}
    if isinstance(execution_policy, dict):
        max_attempts = execution_policy.get("max_attempts")
        if max_attempts is not None and (not isinstance(max_attempts, int) or max_attempts < 1):
            failures.append("request.execution_policy.max_attempts must be an integer >= 1")

    if request.get("instruction") and not isinstance(request.get("instruction"), str):
        failures.append("request.instruction must be a string when provided")
    if not request.get("instruction"):
        warnings.append("request has no natural-language instruction; task parameters are still checked")

    normalized_request = {
        "task_family": contract.get("task_family"),
        "skill_id": skill_id,
        "controller_mode": controller_mode,
        "task_parameters": {key: task_parameters.get(key) for key in sorted(required_params)},
        "validation_profile": task_parameters.get("validation_profile"),
        "not_claims": contract.get("not_claims"),
    }

    return {
        "request": _rel(request_path),
        "contract": _rel(contract_path),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "normalized_request": normalized_request,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, nargs="?", default=DEFAULT_REQUEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    request_path = _resolve(args.request)
    contract_path = _resolve(args.contract)
    report = build_report(request_path, contract_path)

    if args.output_json is not None:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-skill-request] wrote JSON: {_rel(output_json)}")

    print("[v0-skill-request] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "PASS":
        print("[v0-skill-request] PASS")
        return 0

    print("[v0-skill-request] FAIL")
    for failure in report["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
