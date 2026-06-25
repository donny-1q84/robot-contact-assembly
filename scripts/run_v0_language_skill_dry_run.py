#!/usr/bin/env python3
"""Run the V0 language-to-skill dry-run as one offline report.

This chains the deterministic language request planner, request validator, and
gated skill execution planner. It proves the language boundary can produce a
high-level skill request without ever emitting raw joint, Cartesian servo, or
force commands.

It does not call Brev, Isaac, ROS, a robot, an LLM, or a VLM. In the current
baseline-only state it should remain BLOCKED until the success-variation result
gate and V0 scripted-skill dataset are ready.
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

import plan_v0_skill_execution as execution_planner  # noqa: E402
import plan_v0_skill_request as request_planner  # noqa: E402
import validate_v0_skill_request as request_validator  # noqa: E402


DEFAULT_CONTRACT = REPO_ROOT / "configs" / "v0_skill_api_contract.json"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"
DEFAULT_REQUEST_JSON = REPO_ROOT / "artifacts" / "requests" / "v0_language_skill_dry_run_request.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "plans" / "v0_language_skill_dry_run.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "plans" / "v0_language_skill_dry_run.md"


def _side_effects(
    *,
    writes_request_artifact: bool,
    writes_dry_run_report: bool,
) -> dict[str, bool]:
    return {
        "writes_request_artifact": writes_request_artifact,
        "writes_dry_run_report": writes_dry_run_report,
        "creates_paid_instance": False,
        "runs_remote_code": False,
        "starts_isaac": False,
        "calls_llm_or_vlm": False,
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _build_report(
    *,
    instruction: str,
    controller_mode: str,
    max_attempts: int,
    request_path: Path,
    contract_path: Path,
    manifest_path: Path,
    dataset_path: Path,
    min_strict_successes: int,
    negative_control_id: str,
    skip_phase2: bool,
    write_request: bool,
) -> dict[str, Any]:
    request_report = request_planner.build_request(
        instruction,
        controller_mode=controller_mode,
        max_attempts=max_attempts,
    )
    request_pass = request_report.get("status") == "PASS"
    validation: dict[str, Any] | None = None
    execution_plan: dict[str, Any] | None = None
    blockers: list[str] = []

    if not request_pass:
        blockers.extend("language request: " + str(failure) for failure in request_report.get("failures", []))
    else:
        request_payload = request_report["request"]
        if write_request:
            _write_json(request_path, request_payload)
            validation_path = request_path
            request_artifact: str | None = _rel(request_path)
        else:
            with tempfile.TemporaryDirectory(prefix="rca-v0-language-skill-dry-run-") as tmp_dir_raw:
                validation_path = Path(tmp_dir_raw) / "request.json"
                _write_json(validation_path, request_payload)
                validation = request_validator.build_report(validation_path, contract_path)
                execution_plan = execution_planner.build_plan(
                    request_path=validation_path,
                    contract_path=contract_path,
                    manifest_path=manifest_path,
                    dataset_path=dataset_path,
                    min_strict_successes=min_strict_successes,
                    negative_control_id=negative_control_id,
                    skip_phase2=skip_phase2,
                )
            request_artifact = None

        if write_request:
            validation = request_validator.build_report(validation_path, contract_path)
            execution_plan = execution_planner.build_plan(
                request_path=validation_path,
                contract_path=contract_path,
                manifest_path=manifest_path,
                dataset_path=dataset_path,
                min_strict_successes=min_strict_successes,
                negative_control_id=negative_control_id,
                skip_phase2=skip_phase2,
            )

        if validation and validation.get("status") != "PASS":
            blockers.extend("request validation: " + str(failure) for failure in validation.get("failures", []))
        if execution_plan and execution_plan.get("status") != "READY":
            blockers.extend(str(blocker) for blocker in execution_plan.get("blockers", []))

    unique_blockers = list(dict.fromkeys(blockers))
    status = "READY_FOR_SKILL_EXECUTION_REVIEW" if request_pass and not unique_blockers else "BLOCKED"
    return {
        "report_name": "v0_language_skill_dry_run",
        "status": status,
        "ready_for_execution": status == "READY_FOR_SKILL_EXECUTION_REVIEW",
        "instruction": instruction,
        "normalized_instruction": request_report.get("normalized_instruction"),
        "request_artifact": request_artifact if request_pass else None,
        "request_planner_status": request_report.get("status"),
        "request_validation_status": validation.get("status") if validation else None,
        "execution_plan_status": execution_plan.get("status") if execution_plan else None,
        "blocked_next_action": (
            execution_plan.get("blocked_next_action") if execution_plan else "fix_language_instruction"
        ),
        "blockers": unique_blockers,
        "request_preview": request_report.get("request") if request_pass else None,
        "execution_surface": execution_plan.get("execution_surface") if execution_plan else None,
        "side_effects": _side_effects(
            writes_request_artifact=bool(request_pass and write_request),
            writes_dry_run_report=False,
        ),
        "not_claims": [
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a direct low-level VLM controller",
            "not an LLM or VLM call",
            "not a Brev or Isaac launcher",
            "not ROS or hardware execution",
        ],
    }


def _render_markdown(report: dict[str, Any]) -> str:
    rows = [
        "# V0 Language Skill Dry Run",
        "",
        f"- status: {report['status']}",
        f"- ready_for_execution: {report['ready_for_execution']}",
        f"- instruction: {report['instruction']}",
        f"- normalized_instruction: {report['normalized_instruction']}",
        f"- request_artifact: {report['request_artifact']}",
        f"- request_planner_status: {report['request_planner_status']}",
        f"- request_validation_status: {report['request_validation_status']}",
        f"- execution_plan_status: {report['execution_plan_status']}",
        f"- blocked_next_action: {report['blocked_next_action']}",
        "",
        "## Blockers",
        "",
    ]
    rows.extend(f"- {blocker}" for blocker in report["blockers"] or ["none"])
    rows.extend(["", "## What This Is Not", ""])
    rows.extend(f"- {claim}" for claim in report["not_claims"])
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instruction", nargs="?", default="insert the peg into the left socket")
    parser.add_argument("--controller-mode", default="scripted_success_baseline")
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--request-json", type=Path, default=DEFAULT_REQUEST_JSON)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument(
        "--negative-control-id",
        default=execution_planner.readiness_gate.variation_gate.DEFAULT_NEGATIVE_CONTROL,
    )
    parser.add_argument("--skip-phase2-contact-gate", action="store_true")
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = _build_report(
        instruction=args.instruction,
        controller_mode=args.controller_mode,
        max_attempts=args.max_attempts,
        request_path=_resolve(args.request_json),
        contract_path=_resolve(args.contract),
        manifest_path=_resolve(args.manifest),
        dataset_path=_resolve(args.dataset),
        min_strict_successes=args.min_strict_successes,
        negative_control_id=args.negative_control_id,
        skip_phase2=args.skip_phase2_contact_gate,
        write_request=not args.no_output,
    )

    if not args.no_output:
        report["side_effects"]["writes_dry_run_report"] = True
        output_json = _resolve(args.output_json)
        _write_json(output_json, report)
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(report), encoding="utf-8")
        print(f"[v0-language-skill-dry-run] wrote JSON: {_rel(output_json)}")
        print(f"[v0-language-skill-dry-run] wrote Markdown: {_rel(output_md)}")

    print("[v0-language-skill-dry-run] facts=" + json.dumps(report, indent=2, sort_keys=True))
    print("[v0-language-skill-dry-run] status=" + report["status"])
    if report["status"] == "READY_FOR_SKILL_EXECUTION_REVIEW":
        return 0
    return 1 if args.fail_on_blocked or report["request_planner_status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
