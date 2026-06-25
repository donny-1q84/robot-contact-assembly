#!/usr/bin/env python3
"""Check the offline V0 language instruction suite.

This regression gate exercises the deterministic V0 language-to-skill planner
over supported and rejected instructions. It checks that accepted instructions
produce high-level skill requests and that ambiguous, substring, force, or
low-level joint commands fail closed.

It does not call Brev, Isaac, ROS, hardware, an LLM, or a VLM, and it must not
emit raw joint, Cartesian servo, or direct force commands.
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

import plan_v0_skill_request as request_planner  # noqa: E402


DEFAULT_SUITE = REPO_ROOT / "configs" / "v0_language_instruction_suite.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_language_instruction_suite.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_language_instruction_suite.md"


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


def _case_failure_contains(failures: list[str], expected: str | None) -> bool:
    if not expected:
        return True
    return any(expected in failure for failure in failures)


def _request_text(report: dict[str, Any]) -> str:
    return json.dumps(report.get("request"), sort_keys=True)


def build_report(suite_path: Path) -> dict[str, Any]:
    suite = _load_json(suite_path)
    controller_mode = str(suite.get("controller_mode", "scripted_success_baseline"))
    max_attempts = int(suite.get("max_attempts", 1))
    forbidden_tokens = [str(token) for token in suite.get("forbidden_request_tokens", [])]
    cases_payload = suite.get("cases")
    failures: list[str] = []
    case_reports: list[dict[str, Any]] = []

    if not isinstance(cases_payload, list) or not cases_payload:
        failures.append("suite cases must be a non-empty list")
        cases_payload = []

    seen_case_ids: set[str] = set()
    for raw_case in cases_payload:
        if not isinstance(raw_case, dict):
            failures.append("suite case must be an object")
            continue
        case_id = str(raw_case.get("case_id", "")).strip()
        instruction = str(raw_case.get("instruction", ""))
        expected_status = str(raw_case.get("expected_status", "")).strip()
        expected_socket_id = raw_case.get("expected_socket_id")
        expected_failure_contains = raw_case.get("expected_failure_contains")
        case_failures: list[str] = []

        if not case_id:
            case_failures.append("case_id is required")
        if case_id in seen_case_ids:
            case_failures.append(f"duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)
        if expected_status not in {"PASS", "FAIL"}:
            case_failures.append(f"expected_status must be PASS or FAIL, got {expected_status!r}")

        planner_report = request_planner.build_request(
            instruction,
            controller_mode=controller_mode,
            max_attempts=max_attempts,
        )
        status = str(planner_report.get("status"))
        if status != expected_status:
            case_failures.append(f"expected status {expected_status}, got {status}")

        request = planner_report.get("request") if isinstance(planner_report.get("request"), dict) else {}
        task_parameters = request.get("task_parameters") if isinstance(request.get("task_parameters"), dict) else {}
        skill_selection = request.get("skill_selection") if isinstance(request.get("skill_selection"), dict) else {}
        if expected_status == "PASS":
            if expected_socket_id and task_parameters.get("socket_id") != expected_socket_id:
                case_failures.append(
                    f"expected socket_id {expected_socket_id}, got {task_parameters.get('socket_id')}"
                )
            if skill_selection.get("skill_id") != "peg_in_hole":
                case_failures.append(f"expected skill_id peg_in_hole, got {skill_selection.get('skill_id')}")
            if skill_selection.get("controller_mode") != controller_mode:
                case_failures.append(
                    f"expected controller_mode {controller_mode}, got {skill_selection.get('controller_mode')}"
                )
            request_text = _request_text(planner_report)
            for token in forbidden_tokens:
                if token in request_text:
                    case_failures.append(f"accepted request contains forbidden token: {token}")
        else:
            if not _case_failure_contains(
                [str(failure) for failure in planner_report.get("failures", [])],
                str(expected_failure_contains) if expected_failure_contains else None,
            ):
                case_failures.append(f"expected failure detail containing {expected_failure_contains!r}")

        case_status = "PASS" if not case_failures else "FAIL"
        if case_failures:
            failures.extend(f"{case_id}: {failure}" for failure in case_failures)
        case_reports.append(
            {
                "case_id": case_id,
                "instruction": instruction,
                "expected_status": expected_status,
                "actual_status": status,
                "case_status": case_status,
                "expected_socket_id": expected_socket_id,
                "actual_socket_id": task_parameters.get("socket_id"),
                "normalized_instruction": planner_report.get("normalized_instruction"),
                "failures": case_failures,
            }
        )

    return {
        "suite_name": suite.get("suite_name", "v0_language_instruction_suite"),
        "status": "PASS" if not failures else "FAIL",
        "suite": _rel(suite_path),
        "case_count": len(case_reports),
        "pass_count": sum(1 for case in case_reports if case["case_status"] == "PASS"),
        "failures": failures,
        "cases": case_reports,
        "not_claims": suite.get(
            "not_claims",
            [
                "not learned policy",
                "not sim-to-real",
                "not cross-robot-ready",
                "not an LLM or VLM evaluation",
            ],
        ),
    }


def _render_markdown(report: dict[str, Any]) -> str:
    rows = [
        "# V0 Language Instruction Suite",
        "",
        f"- status: {report['status']}",
        f"- suite: {report['suite']}",
        f"- cases: {report['pass_count']}/{report['case_count']} passing",
        "",
        "## Cases",
        "",
    ]
    rows.extend(
        f"- {case['case_id']}: {case['case_status']} "
        f"(expected={case['expected_status']}, actual={case['actual_status']}, socket={case['actual_socket_id']})"
        for case in report["cases"]
    )
    rows.extend(["", "## Failures", ""])
    rows.extend(f"- {failure}" for failure in report["failures"] or ["none"])
    rows.extend(["", "## What This Is Not", ""])
    rows.extend(f"- {claim}" for claim in report["not_claims"])
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", type=Path, nargs="?", default=DEFAULT_SUITE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    args = parser.parse_args()

    report = build_report(_resolve(args.suite))
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(report), encoding="utf-8")
        print(f"[v0-language-suite] wrote JSON: {_rel(output_json)}")
        print(f"[v0-language-suite] wrote Markdown: {_rel(output_md)}")

    print("[v0-language-suite] facts=" + json.dumps(report, indent=2, sort_keys=True))
    print("[v0-language-suite] status=" + report["status"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
