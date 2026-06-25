#!/usr/bin/env python3
"""Plan a V0 external-robot adapter manifest for a named robot.

This is an offline deterministic helper. It does not call Brev, Isaac, ROS, a
vendor SDK, or any robot. The generated manifest is deliberately not ready for
hardware execution: it names the target robot and optional ROS 2 interface
strings, then leaves model, calibration, safety, and revalidation evidence as
explicit blockers for the adapter contract checker.
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

import check_v0_robot_adapter_contract as adapter_gate  # noqa: E402


DEFAULT_TEMPLATE = REPO_ROOT / "configs" / "v0_external_robot_adapter.template.json"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "adapters" / "v0_external_robot_adapter_planned.json"
PLACEHOLDER_PREFIXES = ("replace_with_", "todo", "tbd")


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


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    lowered = value.strip().lower()
    return not lowered or any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)


def _interface(value: str | None) -> dict[str, Any]:
    return {
        "interface": _clean(value),
        "validated": False,
    }


def _side_effects(*, writes_adapter_manifest: bool) -> dict[str, bool]:
    return {
        "writes_adapter_manifest": writes_adapter_manifest,
        "creates_paid_instance": False,
        "runs_remote_code": False,
        "starts_isaac": False,
        "calls_ros_or_robot": False,
    }


def build_adapter(
    *,
    template_path: Path,
    robot_id: str,
    robot_family: str,
    control_stack: str,
    end_effector: str,
    joint_trajectory_action: str | None,
    joint_state_feedback: str | None,
    skill_status: str | None,
) -> dict[str, Any]:
    adapter = _load_json(template_path)
    adapter["adapter_name"] = f"v0_external_robot_adapter_{robot_id}"
    adapter["ready_for_external_robot"] = False
    adapter["target_robot"] = {
        "robot_id": robot_id,
        "robot_family": robot_family,
        "control_stack": control_stack,
        "end_effector": end_effector,
    }
    adapter["ros2_interfaces"] = {
        "joint_trajectory_action": _interface(joint_trajectory_action),
        "joint_state_feedback": _interface(joint_state_feedback),
        "skill_status": _interface(skill_status),
    }
    return adapter


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    failures: list[str] = []
    for field in ("robot_id", "robot_family", "control_stack", "end_effector"):
        value = getattr(args, field)
        if _is_placeholder(value):
            failures.append(f"{field.replace('_', '-')} must name the target robot; placeholders are not accepted")

    template_path = _resolve(args.template)
    output_json = _resolve(args.output_json)
    adapter: dict[str, Any] | None = None
    checker_report: dict[str, Any] | None = None
    if not failures:
        adapter = build_adapter(
            template_path=template_path,
            robot_id=args.robot_id.strip(),
            robot_family=args.robot_family.strip(),
            control_stack=args.control_stack.strip(),
            end_effector=args.end_effector.strip(),
            joint_trajectory_action=args.joint_trajectory_action,
            joint_state_feedback=args.joint_state_feedback,
            skill_status=args.skill_status,
        )
        if args.no_output:
            with tempfile.TemporaryDirectory(prefix="rca-adapter-plan-") as tmp_dir:
                preview_path = Path(tmp_dir) / "adapter.json"
                preview_path.write_text(json.dumps(adapter, indent=2, sort_keys=True), encoding="utf-8")
                checker_report = adapter_gate.build_report(preview_path)
        else:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            output_json.write_text(json.dumps(adapter, indent=2, sort_keys=True), encoding="utf-8")
            checker_report = adapter_gate.build_report(output_json)

    if failures:
        status = "FAIL"
        next_action = "provide_named_robot_identity_and_interfaces"
    elif checker_report is not None and checker_report.get("status") == "READY":
        status = "PASS_READY"
        next_action = "review_named_robot_adapter_for_low_speed_manual_hardware_gate"
    else:
        status = "PASS_SAFE_BLOCKED"
        next_action = "review_named_robot_adapter_blockers"

    return {
        "status": status,
        "failures": failures,
        "template": _rel(template_path),
        "output_json": None if args.no_output else _rel(output_json),
        "adapter": adapter,
        "adapter_contract_status": None if checker_report is None else checker_report.get("status"),
        "adapter_contract_blockers": [] if checker_report is None else checker_report.get("blockers", []),
        "next_action": next_action,
        "side_effects": _side_effects(writes_adapter_manifest=adapter is not None and not args.no_output),
        "not_claims": [
            "not ready for hardware execution",
            "not verified on this robot",
            "not sim-to-real",
            "not direct drop-in precision on another robot arm",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot-id", required=True)
    parser.add_argument("--robot-family", required=True)
    parser.add_argument("--control-stack", default="ros2_joint_trajectory_or_vendor_bridge")
    parser.add_argument("--end-effector", required=True)
    parser.add_argument("--joint-trajectory-action")
    parser.add_argument("--joint-state-feedback")
    parser.add_argument("--skill-status")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-output", action="store_true")
    args = parser.parse_args()

    report = build_report(args)
    if report["status"] == "FAIL" and not args.no_output:
        print("[v0-robot-adapter-planner] blocked: adapter manifest was not written", file=sys.stderr)

    print("[v0-robot-adapter-planner] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] in {"PASS_SAFE_BLOCKED", "PASS_READY"}:
        if report["output_json"] is not None:
            print(f"[v0-robot-adapter-planner] wrote adapter JSON: {report['output_json']}")
        print(f"[v0-robot-adapter-planner] {report['status']}")
        return 0

    print("[v0-robot-adapter-planner] FAIL")
    for failure in report["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
