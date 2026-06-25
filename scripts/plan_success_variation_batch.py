#!/usr/bin/env python3
"""Plan a manifest-driven successful-trace variation batch.

The planner turns each missing manifest case into explicit remote trace-only
commands. It does not create Brev instances or run paid compute; the output is a
reviewable contract for the runner layer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "artifacts/manifests/success_trace_variations_2026-06-25.json"


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


def _float_list(value: Any, *, length: int, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise RuntimeError(f"{label} must be a {length}-element list")
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} must contain numeric values") from exc


def _fmt_vec3(values: list[float]) -> str:
    return ",".join(f"{value:.6f}" for value in values)


def _planned_remote_dir(case: dict[str, Any]) -> str:
    planned_trace = case.get("planned_trace_json")
    if not isinstance(planned_trace, str) or not planned_trace.endswith("/video_trace.json"):
        raise RuntimeError(f"case {case.get('case_id')} is missing planned_trace_json ending in /video_trace.json")
    planned_dir = planned_trace[: -len("/video_trace.json")]
    if planned_dir.startswith("artifacts/"):
        return "/workspace/" + planned_dir
    if planned_dir.startswith("/workspace/artifacts/"):
        return planned_dir
    raise RuntimeError(f"case {case.get('case_id')} planned trace is outside artifacts/: {planned_trace}")


def _case_extra_args(
    case: dict[str, Any],
    *,
    base_socket_pos: list[float],
) -> list[str]:
    socket_delta = _float_list(case.get("socket_delta_m"), length=3, label=f"{case.get('case_id')}.socket_delta_m")
    reset_noise = float(case.get("reset_joint_noise_rad", 0.0) or 0.0)
    args: list[str] = []
    if any(abs(value) > 0.0 for value in socket_delta):
        socket_pos = [base_socket_pos[index] + socket_delta[index] for index in range(3)]
        args.extend(["--socket-pos", _fmt_vec3(socket_pos)])
    if reset_noise > 0.0:
        args.extend(["--reset-joint-noise-rad", f"{reset_noise:.6f}"])
    return args


def build_plan(
    manifest: dict[str, Any],
    *,
    env_name: str,
    remote_root: str,
    compose_root: str,
    task: str | None,
    steps: int,
    include_available: bool,
) -> dict[str, Any]:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("manifest must contain a cases list")
    base_socket_pos = _float_list(
        manifest.get("source_socket_frame_pos_m"),
        length=3,
        label="manifest.source_socket_frame_pos_m",
    )
    task_name = task or str(manifest.get("task") or "RCA-PegInHole-Franka-JointPos-Contact-Play-v0")
    planned_cases: list[dict[str, Any]] = []
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            continue
        if not include_available and raw_case.get("status") == "available":
            continue
        case_id = str(raw_case.get("case_id") or "")
        if not case_id:
            raise RuntimeError("manifest case is missing case_id")
        seed = int(raw_case.get("seed") or 42)
        socket_delta = _float_list(raw_case.get("socket_delta_m"), length=3, label=f"{case_id}.socket_delta_m")
        reset_noise = float(raw_case.get("reset_joint_noise_rad", 0.0) or 0.0)
        extra_args = _case_extra_args(raw_case, base_socket_pos=base_socket_pos)
        remote_trace_dir = _planned_remote_dir(raw_case)
        env = {
            "RCA_TRACE_ONLY_REMOTE_DIR": remote_trace_dir,
            "RCA_TRACE_ONLY_DIR_NAME": case_id,
            "RCA_TRACE_VARIATION_CASE_ID": case_id,
            "RCA_TRACE_VARIATION_SOCKET_DELTA_M": _fmt_vec3(socket_delta),
            "RCA_TRACE_VARIATION_RESET_JOINT_NOISE_RAD": f"{reset_noise:.6f}",
            "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_ACTION_RESPONSE": "0",
            "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_FINAL_CONTACT_BOUNDARY": "0",
            "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_PEG_VIDEO_CANDIDATE": "0",
            "RCA_JOINT_RESPONSE_SOCKET_VALIDATE_TRACE_FRAME_ALIGNMENT": "0",
        }
        if extra_args:
            env["RCA_SOCKET_INSERTION_SERVO_EXTRA_ARGS"] = " ".join(shlex.quote(arg) for arg in extra_args)
        command = [
            "scripts/run_remote_joint_response_socket_insertion_servo_trace.sh",
            env_name,
            remote_root,
            compose_root,
            task_name,
            "1",
            str(steps),
            str(seed),
        ]
        planned_cases.append(
            {
                "case_id": case_id,
                "expected": raw_case.get("expected"),
                "seed": seed,
                "socket_delta_m": socket_delta,
                "socket_pos_m": [base_socket_pos[index] + socket_delta[index] for index in range(3)],
                "reset_joint_noise_rad": reset_noise,
                "remote_trace_dir": remote_trace_dir,
                "planned_trace_json": raw_case.get("planned_trace_json"),
                "extra_agent_args": extra_args,
                "env": env,
                "command": command,
                "shell": shlex.join(["env", *[f"{key}={value}" for key, value in env.items()], *command]),
            }
        )
    return {
        "manifest_created_utc": manifest.get("created_utc"),
        "source_trace_json": manifest.get("source_trace_json"),
        "source_socket_frame_pos_m": base_socket_pos,
        "task": task_name,
        "steps": steps,
        "include_available": include_available,
        "case_count": len(planned_cases),
        "cases": planned_cases,
    }


def render_shell(plan: dict[str, Any]) -> str:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# Generated by scripts/plan_success_variation_batch.py.",
        "# This script assumes the remote environment already exists and is ready.",
        "",
    ]
    for case in plan["cases"]:
        lines.append(f"echo '[success-variation-batch] case={case['case_id']} expected={case.get('expected')}'")
        lines.append(str(case["shell"]))
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    parser.add_argument("--env-name", default="isaac-l40s")
    parser.add_argument("--remote-root", default="/home/ubuntu/projects/robot-contact-assembly")
    parser.add_argument("--compose-root", default="/home/ubuntu/isaac-compose")
    parser.add_argument("--task")
    parser.add_argument("--steps", type=int, default=220)
    parser.add_argument("--include-available", action="store_true")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-sh", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--shell", action="store_true")
    args = parser.parse_args()

    manifest = _load_json(args.manifest)
    plan = build_plan(
        manifest,
        env_name=args.env_name,
        remote_root=args.remote_root,
        compose_root=args.compose_root,
        task=args.task,
        steps=max(1, args.steps),
        include_available=args.include_available,
    )
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[success-variation-plan] wrote JSON: {_rel(args.output_json)}")
    if args.output_sh is not None:
        args.output_sh.parent.mkdir(parents=True, exist_ok=True)
        args.output_sh.write_text(render_shell(plan), encoding="utf-8")
        print(f"[success-variation-plan] wrote shell: {_rel(args.output_sh)}")
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
    if args.shell:
        print(render_shell(plan))
    print(f"[success-variation-plan] cases={plan['case_count']} steps={plan['steps']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
