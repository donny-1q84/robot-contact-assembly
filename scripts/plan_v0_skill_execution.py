#!/usr/bin/env python3
"""Plan a gated V0 skill execution from a validated high-level request.

This is the offline bridge between the language/request layer and a future
skill execution surface. It validates the request and reuses the V0 readiness
gate, but it does not call Brev, Isaac, ROS, or any robot. If readiness is not
READY, the plan is explicitly BLOCKED and ready_for_execution is false.
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
import validate_v0_skill_request as request_gate  # noqa: E402


DEFAULT_REQUEST = REPO_ROOT / "configs" / "v0_skill_request.example.json"
DEFAULT_CONTRACT = REPO_ROOT / "configs" / "v0_skill_api_contract.json"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "plans" / "v0_skill_execution_plan.json"


def _side_effects(*, writes_execution_plan: bool) -> dict[str, bool]:
    return {
        "writes_execution_plan": writes_execution_plan,
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


def _request_summary(request_path: Path, contract_path: Path) -> dict[str, Any]:
    request = _load_json(request_path)
    validation = request_gate.build_report(request_path, contract_path)
    return {
        "request": _rel(request_path),
        "request_name": request.get("request_name"),
        "instruction": request.get("instruction"),
        "task_parameters": request.get("task_parameters"),
        "skill_selection": request.get("skill_selection"),
        "execution_policy": request.get("execution_policy"),
        "validation": validation,
    }


def _blocked_action(readiness: dict[str, Any]) -> str:
    next_action = readiness.get("next_action")
    if isinstance(next_action, str) and next_action:
        return next_action
    return "resolve_v0_skill_execution_blockers"


def build_plan(
    *,
    request_path: Path,
    contract_path: Path,
    manifest_path: Path,
    dataset_path: Path,
    min_strict_successes: int,
    negative_control_id: str,
    skip_phase2: bool,
) -> dict[str, Any]:
    request = _request_summary(request_path, contract_path)
    readiness = readiness_gate.build_report(
        request_path=request_path,
        contract_path=contract_path,
        manifest_path=manifest_path,
        dataset_path=dataset_path,
        min_strict_successes=min_strict_successes,
        negative_control_id=negative_control_id,
        skip_phase2=skip_phase2,
    )
    blockers: list[str] = []
    if request["validation"].get("status") != "PASS":
        blockers.extend("request: " + str(failure) for failure in request["validation"].get("failures", []))
    if readiness.get("status") != "READY":
        blockers.extend(str(blocker) for blocker in readiness.get("blockers", []))
    unique_blockers = list(dict.fromkeys(blockers))
    status = "READY" if not unique_blockers else "BLOCKED"

    return {
        "plan_name": "v0_skill_execution_plan",
        "status": status,
        "ready_for_execution": status == "READY",
        "request": request,
        "readiness": {
            "status": readiness.get("status"),
            "next_action": readiness.get("next_action"),
            "blockers": readiness.get("blockers"),
            "warnings": readiness.get("warnings"),
            "success_variation_gate": readiness.get("success_variation_gate", {}).get("gate"),
            "dataset_gate": readiness.get("dataset_gate"),
        },
        "execution_surface": {
            "skill_id": (request.get("skill_selection") or {}).get("skill_id"),
            "controller_mode": (request.get("skill_selection") or {}).get("controller_mode"),
            "allowed_command_boundary": "task_parameters_to_skill_controller",
            "forbidden_command_boundary": [
                "raw_joint_targets",
                "direct_cartesian_servo_commands",
                "direct_force_commands",
            ],
        },
        "blocked_next_action": None if status == "READY" else _blocked_action(readiness),
        "blockers": unique_blockers,
        "side_effects": _side_effects(writes_execution_plan=False),
        "not_claims": [
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a direct low-level VLM controller",
            "not a Brev or Isaac launcher",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, nargs="?", default=DEFAULT_REQUEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--negative-control-id", default=readiness_gate.variation_gate.DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--skip-phase2-contact-gate", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    plan = build_plan(
        request_path=_resolve(args.request),
        contract_path=_resolve(args.contract),
        manifest_path=_resolve(args.manifest),
        dataset_path=_resolve(args.dataset),
        min_strict_successes=args.min_strict_successes,
        negative_control_id=args.negative_control_id,
        skip_phase2=args.skip_phase2_contact_gate,
    )

    if not args.no_output:
        plan["side_effects"] = _side_effects(writes_execution_plan=True)
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-skill-execution-plan] wrote JSON: {_rel(output_json)}")

    print("[v0-skill-execution-plan] facts=" + json.dumps(plan, indent=2, sort_keys=True))
    print("[v0-skill-execution-plan] status=" + plan["status"])
    if plan["status"] == "READY":
        return 0
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
