#!/usr/bin/env python3
"""Validate the generated success-variation batch plan before paid compute.

This is a local, read-only gate. It checks that the manifest-driven planner will
run exactly the planned missing cases, route every remote trace to the expected
artifact path, include the fail-closed negative control, and avoid direct paid
or remote side effects. It does not create, delete, copy to, or execute on Brev instances.
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

import plan_success_variation_batch as planner  # noqa: E402


DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_NEGATIVE_CONTROL = "socket_x_pos_25mm_negative_control"
REQUIRED_RUNNER = "scripts/run_remote_joint_response_socket_insertion_servo_trace.sh"
FORBIDDEN_COMMAND_TOKENS = {"brev", "/Users/Shenghan/bin/brev", "create"}
REQUIRED_DISABLED_VALIDATORS = {
    "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_ACTION_RESPONSE",
    "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_FINAL_CONTACT_BOUNDARY",
    "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_PEG_VIDEO_CANDIDATE",
    "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_TRACE_FRAME_ALIGNMENT",
}
DIRECT_CREATE_MARKER = "brev " + "create"


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


def _fmt_vec3(values: list[float]) -> str:
    return ",".join(f"{value:.6f}" for value in values)


def _planned_remote_dir(planned_trace_json: str) -> str:
    if not planned_trace_json.startswith("artifacts/") or not planned_trace_json.endswith("/video_trace.json"):
        raise RuntimeError(f"planned trace must be under artifacts/ and end in /video_trace.json: {planned_trace_json}")
    return "/workspace/" + planned_trace_json[: -len("/video_trace.json")]


def _as_vec3(value: Any, *, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise RuntimeError(f"{label} must be a 3-element list")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} must contain numeric values") from exc


def _case_map(cases: list[Any]) -> dict[str, dict[str, Any]]:
    by_case: dict[str, dict[str, Any]] = {}
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            continue
        case_id = str(raw_case.get("case_id") or "")
        if not case_id:
            continue
        by_case[case_id] = raw_case
    return by_case


def build_report(
    manifest_path: Path,
    *,
    env_name: str,
    remote_root: str,
    compose_root: str,
    task: str | None,
    steps: int,
    negative_control_id: str = DEFAULT_NEGATIVE_CONTROL,
    include_available: bool = False,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("manifest must contain a cases list")
    manifest_cases = _case_map(cases)
    source_socket = _as_vec3(manifest.get("source_socket_frame_pos_m"), label="source_socket_frame_pos_m")

    plan = planner.build_plan(
        manifest,
        env_name=env_name,
        remote_root=remote_root,
        compose_root=compose_root,
        task=task,
        steps=max(1, steps),
        include_available=include_available,
    )
    plan_cases = [case for case in plan.get("cases", []) if isinstance(case, dict)]
    plan_by_case = {str(case.get("case_id") or ""): case for case in plan_cases}
    failures: list[str] = []

    planned_case_ids = [
        case_id
        for case_id, case in manifest_cases.items()
        if include_available or case.get("status") != "available"
    ]
    if sorted(plan_by_case) != sorted(planned_case_ids):
        failures.append(
            "planned case ids do not match manifest missing/planned cases: "
            f"plan={sorted(plan_by_case)} expected={sorted(planned_case_ids)}"
        )

    baseline = manifest_cases.get("baseline_replay")
    if not baseline or baseline.get("status") != "available":
        failures.append("baseline_replay must exist and remain status=available")
    elif "baseline_replay" in plan_by_case and not include_available:
        failures.append("baseline_replay must not be rerun by the default paid variation plan")

    negative = manifest_cases.get(negative_control_id)
    if not negative:
        failures.append(f"manifest must include negative control {negative_control_id}")
    elif negative.get("expected") != "fail_closed":
        failures.append(f"{negative_control_id} must be expected=fail_closed")
    elif negative_control_id not in plan_by_case:
        failures.append(f"{negative_control_id} must be included in the paid variation plan")

    for case_id, planned in plan_by_case.items():
        source = manifest_cases.get(case_id)
        if source is None:
            failures.append(f"plan contains case not present in manifest: {case_id}")
            continue
        planned_trace_json = source.get("planned_trace_json")
        if not isinstance(planned_trace_json, str):
            failures.append(f"{case_id} is missing planned_trace_json")
            continue
        try:
            expected_remote_dir = _planned_remote_dir(planned_trace_json)
        except RuntimeError as exc:
            failures.append(str(exc))
            continue

        if planned.get("remote_trace_dir") != expected_remote_dir:
            failures.append(
                f"{case_id} remote_trace_dir {planned.get('remote_trace_dir')} does not match {expected_remote_dir}"
            )
        if planned.get("planned_trace_json") != planned_trace_json:
            failures.append(f"{case_id} plan planned_trace_json does not match manifest")
        if not str(planned_trace_json).startswith("artifacts/videos/success_variations/"):
            failures.append(f"{case_id} planned trace is outside success_variations artifacts: {planned_trace_json}")

        env = planned.get("env") if isinstance(planned.get("env"), dict) else {}
        if env.get("RCA_TRACE_ONLY_REMOTE_DIR") != expected_remote_dir:
            failures.append(f"{case_id} RCA_TRACE_ONLY_REMOTE_DIR does not match planned artifact path")
        if env.get("RCA_TRACE_ONLY_DIR_NAME") != case_id:
            failures.append(f"{case_id} RCA_TRACE_ONLY_DIR_NAME must equal case_id")
        if env.get("RCA_TRACE_VARIATION_CASE_ID") != case_id:
            failures.append(f"{case_id} RCA_TRACE_VARIATION_CASE_ID must equal case_id")
        for key in REQUIRED_DISABLED_VALIDATORS:
            if env.get(key) != "0":
                failures.append(f"{case_id} must disable inline validator {key}=0 and classify after pullback")

        socket_delta = _as_vec3(source.get("socket_delta_m"), label=f"{case_id}.socket_delta_m")
        if env.get("RCA_TRACE_VARIATION_SOCKET_DELTA_M") != _fmt_vec3(socket_delta):
            failures.append(f"{case_id} RCA_TRACE_VARIATION_SOCKET_DELTA_M does not match manifest")
        reset_noise = float(source.get("reset_joint_noise_rad", 0.0) or 0.0)
        if env.get("RCA_TRACE_VARIATION_RESET_JOINT_NOISE_RAD") != f"{reset_noise:.6f}":
            failures.append(f"{case_id} RCA_TRACE_VARIATION_RESET_JOINT_NOISE_RAD does not match manifest")

        extra_args = env.get("RCA_SOCKET_INSERTION_SERVO_EXTRA_ARGS", "")
        absolute_socket = [source_socket[index] + socket_delta[index] for index in range(3)]
        if any(abs(value) > 0.0 for value in socket_delta):
            expected_socket_arg = f"--socket-pos {_fmt_vec3(absolute_socket)}"
            if expected_socket_arg not in extra_args:
                failures.append(f"{case_id} missing absolute socket override {expected_socket_arg}")
        if reset_noise > 0.0 and f"--reset-joint-noise-rad {reset_noise:.6f}" not in extra_args:
            failures.append(f"{case_id} missing reset-noise override")

        command = planned.get("command") if isinstance(planned.get("command"), list) else []
        if not command or command[0] != REQUIRED_RUNNER:
            failures.append(f"{case_id} command must start with {REQUIRED_RUNNER}")
        command_tokens = {str(token) for token in command}
        if FORBIDDEN_COMMAND_TOKENS.issubset(command_tokens):
            failures.append(f"{case_id} command appears to create Brev resources directly")
        if planned.get("shell") and DIRECT_CREATE_MARKER in str(planned["shell"]):
            failures.append(f"{case_id} shell contains direct Brev resource creation")

    planned_unique_seeds = sorted(
        {
            int(case.get("seed"))
            for case in plan_cases
            if isinstance(case.get("seed"), int)
        }
    )
    summary = {
        "manifest": _rel(manifest_path),
        "include_available": include_available,
        "manifest_case_count": len(manifest_cases),
        "planned_case_count": len(plan_cases),
        "planned_case_ids": sorted(plan_by_case),
        "planned_unique_seeds": planned_unique_seeds,
        "planned_unique_seed_count": len(planned_unique_seeds),
        "expected_case_ids": sorted(planned_case_ids),
        "negative_control_id": negative_control_id,
        "negative_control_in_plan": negative_control_id in plan_by_case,
        "runner": REQUIRED_RUNNER,
        "steps": plan.get("steps"),
        "task": plan.get("task"),
    }
    return {
        "pass": not failures,
        "failures": failures,
        "summary": summary,
        "plan": plan,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    parser.add_argument("--env-name", default="isaac-l40s")
    parser.add_argument("--remote-root", default="/home/ubuntu/projects/robot-contact-assembly")
    parser.add_argument("--compose-root", default="/home/ubuntu/isaac-compose")
    parser.add_argument("--task")
    parser.add_argument("--steps", type=int, default=220)
    parser.add_argument("--negative-control-id", default=DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--include-available", action="store_true")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.expanduser()
    if not manifest_path.is_absolute():
        manifest_path = REPO_ROOT / manifest_path

    try:
        report = build_report(
            manifest_path,
            env_name=args.env_name,
            remote_root=args.remote_root,
            compose_root=args.compose_root,
            task=args.task,
            steps=args.steps,
            negative_control_id=args.negative_control_id,
            include_available=args.include_available,
        )
    except Exception as exc:  # noqa: BLE001 - gate failures should be readable.
        report = {
            "pass": False,
            "failures": [str(exc)],
            "summary": {"manifest": _rel(manifest_path)},
        }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[success-variation-plan-gate] wrote JSON: {_rel(args.output_json)}")

    print("[success-variation-plan-gate] facts=" + json.dumps(report["summary"], indent=2, sort_keys=True))
    if report["pass"]:
        print("[success-variation-plan-gate] PASS")
        return 0

    print("[success-variation-plan-gate] BLOCKED")
    for failure in report["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
