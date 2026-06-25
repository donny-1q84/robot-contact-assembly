#!/usr/bin/env python3
"""Check the success-variation paid lifecycle preflight without arming or running.

This aggregates the local evidence needed before the one-shot paid lifecycle:
credit evidence, Brev empty-org safety, local env armability, and the
success-variation batch plan. It does not write the local env, create a Brev
instance, run the batch, copy artifacts, start Isaac, or execute remote code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import arm_success_variation_paid_env as arm_gate  # noqa: E402
import check_brev_credit_evidence as credit_gate  # noqa: E402


DEFAULT_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "success_variation_paid_lifecycle_preflight.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "success_variation_paid_lifecycle_preflight.md"


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


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError(f"invalid env line {line_no}: {raw_line}")
        key, value = line.split("=", 1)
        if not (key.startswith("RCA_") or key == "BREV_BIN"):
            raise RuntimeError(f"disallowed env key on line {line_no}: {key}")
        values[key] = value
    return values


def _float_env(values: dict[str, str], key: str, blockers: list[str]) -> float | None:
    raw = values.get(key, "").strip()
    if not raw:
        blockers.append(f"{key} is missing")
        return None
    try:
        parsed = float(raw)
    except ValueError:
        blockers.append(f"{key} must be numeric, got {raw!r}")
        return None
    if parsed <= 0.0:
        blockers.append(f"{key} must be positive, got {raw!r}")
        return None
    return parsed


def _int_env(values: dict[str, str], key: str, default: int, blockers: list[str]) -> int | None:
    raw = values.get(key, str(default)).strip()
    try:
        parsed = int(raw)
    except ValueError:
        blockers.append(f"{key} must be an integer, got {raw!r}")
        return None
    if parsed <= 0:
        blockers.append(f"{key} must be positive, got {raw!r}")
        return None
    return parsed


def _run_capture(args: list[str], timeout_seconds: int) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "args": args,
            "exit_code": 124,
            "timed_out": True,
            "output_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
        }
    return {
        "args": args,
        "exit_code": int(completed.returncode),
        "timed_out": False,
        "output_tail": completed.stdout[-4000:],
    }


def build_report(
    *,
    config_path: Path,
    manifest_path: Path,
    command_timeout_seconds: int,
    brev_safety_output: Path | None = None,
) -> dict[str, Any]:
    config_path = _resolve(config_path)
    manifest_path = _resolve(manifest_path)
    blockers: list[str] = []
    failures: list[str] = []
    values: dict[str, str] = {}

    if not config_path.is_file():
        blockers.append(f"local env config is missing: {_rel(config_path)}")
    else:
        try:
            values = _read_env(config_path)
        except Exception as exc:  # noqa: BLE001 - config errors should fail closed.
            failures.append(f"local env config could not be parsed: {exc}")

    if not manifest_path.is_file():
        blockers.append(f"success-variation manifest is missing: {_rel(manifest_path)}")

    budget = _float_env(values, "RCA_PAID_BUDGET_EUR", blockers) if values else None
    credit_max_age = _int_env(values, "RCA_BREV_CREDIT_EVIDENCE_MAX_AGE_MINUTES", 60, blockers) if values else None
    credit_path_raw = values.get("RCA_BREV_CREDIT_EVIDENCE_JSON", "configs/brev_credit_verification.local.json")
    credit_path = _resolve(Path(credit_path_raw))
    credit_report: dict[str, Any] | None = None
    if budget is not None and credit_max_age is not None:
        credit_report = credit_gate.build_report(
            evidence_path=credit_path,
            required_budget_eur=budget,
            max_age_minutes=credit_max_age,
        )
        if credit_report.get("status") != "PASS":
            blockers.append("Brev UI credit evidence must pass before the paid lifecycle can be armed")

    arm_report: dict[str, Any] | None = None
    if not failures and config_path.is_file():
        arm_report = arm_gate.build_report(config_path, brev_safety_output=brev_safety_output)
        if arm_report.get("status") != "PASS":
            blockers.append("local env cannot be armed for the paid lifecycle yet")

    plan_report: dict[str, Any] | None = None
    if manifest_path.is_file():
        plan_report = _run_capture(
            ["python3", "scripts/check_success_variation_batch_plan.py", str(manifest_path)],
            timeout_seconds=command_timeout_seconds,
        )
        if plan_report["exit_code"] != 0:
            blockers.append("success-variation batch plan gate must pass before the paid lifecycle")

    status = "FAIL" if failures else ("BLOCKED" if blockers else "READY_FOR_SINGLE_PAID_LIFECYCLE")
    next_action = "run_success_variation_paid_lifecycle_after_current_ui_balance_review"
    if status == "BLOCKED":
        next_action = "refresh_credit_evidence_then_rerun_paid_lifecycle_preflight"
    elif status == "FAIL":
        next_action = "fix_paid_lifecycle_preflight_inputs"

    balance_placeholder = "<current-brev-ui-balance>"
    lifecycle_command = [
        "python3",
        "scripts/run_success_variation_paid_lifecycle.py",
        "--balance-eur",
        balance_placeholder,
        "--run",
        "--i-understand-this-can-create-paid-instance",
    ]
    return {
        "preflight_name": "success_variation_paid_lifecycle_preflight",
        "status": status,
        "config": _rel(config_path),
        "manifest": _rel(manifest_path),
        "credit_evidence_path": _rel(credit_path),
        "budget_eur": budget,
        "credit_max_age_minutes": credit_max_age,
        "credit_evidence": credit_report,
        "armability": arm_report,
        "batch_plan_gate": plan_report,
        "blockers": list(dict.fromkeys(blockers)),
        "failures": list(dict.fromkeys(failures)),
        "next_action": next_action,
        "lifecycle_command_template": lifecycle_command,
        "side_effects": {
            "writes_local_env": False,
            "creates_paid_instance": False,
            "runs_remote_code": False,
            "starts_isaac": False,
            "copies_artifacts": False,
        },
        "not_claims": [
            "not a paid run",
            "not armed local env",
            "not fresh credit evidence unless credit_evidence.status is PASS",
            "not success-variation result evidence",
        ],
    }


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Success Variation Paid Lifecycle Preflight",
        "",
        f"- status: {report['status']}",
        f"- config: {report['config']}",
        f"- manifest: {report['manifest']}",
        f"- credit_evidence_path: {report['credit_evidence_path']}",
        f"- budget_eur: {report['budget_eur']}",
        f"- next_action: {report['next_action']}",
        "",
        "## Lifecycle Command Template",
        "",
        "```bash",
        " ".join(report["lifecycle_command_template"]),
        "```",
        "",
        "## Blockers",
        "",
    ]
    if report["blockers"]:
        lines.extend(f"- {item}" for item in report["blockers"])
    else:
        lines.append("- none")
    if report["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {item}" for item in report["failures"])
    lines.extend(["", "## Side Effects", ""])
    for key, value in report["side_effects"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Not Claims", ""])
    lines.extend(f"- {item}" for item in report["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--command-timeout-seconds", type=int, default=120)
    parser.add_argument(
        "--brev-safety-output",
        type=Path,
        help="Use saved brev_paid_safety_status.sh output for offline tests; default runs the live safety check.",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    if args.command_timeout_seconds <= 0:
        print("[success-variation-paid-preflight] FAIL")
        print("- --command-timeout-seconds must be positive")
        return 1

    report = build_report(
        config_path=args.config,
        manifest_path=args.manifest,
        command_timeout_seconds=args.command_timeout_seconds,
        brev_safety_output=args.brev_safety_output,
    )
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[success-variation-paid-preflight] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(report), encoding="utf-8")
        print(f"[success-variation-paid-preflight] wrote Markdown: {_rel(output_md)}")

    print("[success-variation-paid-preflight] facts=" + json.dumps(report, indent=2, sort_keys=True))
    print("[success-variation-paid-preflight] status=" + report["status"])
    if report["status"] != "READY_FOR_SINGLE_PAID_LIFECYCLE":
        print("[success-variation-paid-preflight] no paid instance was created")
    if report["status"] == "FAIL":
        return 1
    if report["status"] == "BLOCKED" and args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
