#!/usr/bin/env python3
"""Plan a V0 high-level skill request from a narrow natural-language instruction.

This is a deterministic local shim for the language-to-skill boundary. It is
not an LLM/VLM and does not command joints. Unsupported or ambiguous
instructions fail closed instead of guessing low-level behavior.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "requests" / "v0_skill_request_planned.json"


SOCKET_ALIASES = {
    "left": "left_socket",
    "left_socket": "left_socket",
    "right": "right_socket",
    "right_socket": "right_socket",
    "center": "center_socket",
    "centre": "center_socket",
    "center_socket": "center_socket",
}


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _normalize_instruction(instruction: str) -> str:
    normalized = instruction.strip().lower()
    normalized = normalized.replace("-", "_")
    normalized = re.sub(r"[^a-z0-9_\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _socket_from_instruction(normalized: str) -> str | None:
    tokens = normalized.split()
    for token in tokens:
        if token in SOCKET_ALIASES:
            return SOCKET_ALIASES[token]
    return None


def build_request(instruction: str, *, controller_mode: str, max_attempts: int) -> dict[str, Any]:
    normalized = _normalize_instruction(instruction)
    failures: list[str] = []
    if not normalized:
        failures.append("instruction is empty")

    if "insert" not in normalized.split():
        failures.append("instruction must request the high-level insert skill")
    if "peg" not in normalized.split():
        failures.append("instruction must name the peg object")

    socket_id = _socket_from_instruction(normalized)
    if socket_id is None:
        failures.append("instruction must specify a supported socket target: left, right, or center")

    if controller_mode not in {"scripted_success_baseline", "residual_policy_over_scripted_baseline"}:
        failures.append(f"controller mode is not allowed for V0 skill request: {controller_mode}")

    if max_attempts < 1:
        failures.append("max_attempts must be >= 1")

    request = {
        "request_name": "planned_insert_peg_request",
        "instruction": instruction,
        "task_parameters": {
            "object_id": "peg",
            "socket_id": socket_id,
            "target_pose_frame": "socket_fixture_frame",
            "tolerance_profile": "strict",
            "validation_profile": "strict_success",
        },
        "skill_selection": {
            "skill_id": "peg_in_hole",
            "controller_mode": controller_mode,
        },
        "execution_policy": {
            "max_attempts": max_attempts,
            "retry_policy": "none" if max_attempts == 1 else "bounded_revalidate",
        },
        "planner_notes": {
            "planner": "deterministic_v0_language_to_skill_shim",
            "not_claims": [
                "not learned policy",
                "not sim-to-real",
                "not cross-robot-ready",
                "not a direct low-level VLM controller",
            ],
        },
    }

    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "normalized_instruction": normalized,
        "request": request,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instruction", nargs="?", default="insert the peg into the left socket")
    parser.add_argument("--controller-mode", default="scripted_success_baseline")
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-output", action="store_true")
    args = parser.parse_args()

    report = build_request(
        args.instruction,
        controller_mode=args.controller_mode,
        max_attempts=args.max_attempts,
    )

    if report["status"] == "PASS" and not args.no_output:
        output_json = args.output_json.expanduser()
        if not output_json.is_absolute():
            output_json = REPO_ROOT / output_json
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report["request"], indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-skill-planner] wrote request JSON: {_rel(output_json)}")
    elif report["status"] != "PASS" and not args.no_output:
        print("[v0-skill-planner] blocked: request JSON was not written", file=sys.stderr)

    print("[v0-skill-planner] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "PASS":
        print("[v0-skill-planner] PASS")
        return 0

    print("[v0-skill-planner] FAIL")
    for failure in report["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
