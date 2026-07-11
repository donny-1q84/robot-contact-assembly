#!/usr/bin/env python3
"""Run one success-variation paid batch lifecycle after fresh UI balance evidence.

This is the highest-level paid entrypoint for the current success-variation
milestone. It is deliberately fail-closed: it only reaches the paid runner when
--run, --balance-eur, and --i-understand-this-can-create-paid-instance are all
provided. It first delegates to the prepare helper, then forces the aggregate
paid lifecycle preflight, then runs the guarded config runner, disarms the local env,
checks Brev safety, and finally either finalizes the dataset gate plus V0 offline
policy-readiness pipeline or writes a recovery rerun plan.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_RECOVERY_JSON = REPO_ROOT / "artifacts" / "analysis" / "success_trace_variation_recovery_plan_2026-06-25.json"
DEFAULT_RECOVERY_SH = REPO_ROOT / "artifacts" / "analysis" / "success_trace_variation_recovery_plan_2026-06-25.sh"
DEFAULT_CREDIT_EVIDENCE = REPO_ROOT / "configs" / "brev_credit_verification.local.json"


def _resolve(path: Path) -> Path:
    path = path.expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be numeric, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"must be non-negative, got {value!r}")
    return parsed


def _fmt(args: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in args)


def _read_config_value(config: Path, key: str) -> str | None:
    if not config.is_file():
        return None
    for raw_line in config.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, value = line.split("=", 1)
        if current_key == key:
            return value.strip()
    return None


def _run(label: str, args: list[str]) -> int:
    print(f"[success-variation-lifecycle] {label}: {_fmt(args)}", flush=True)
    result = subprocess.run(args, cwd=REPO_ROOT, check=False)
    print(f"[success-variation-lifecycle] {label}_exit={result.returncode}", flush=True)
    return int(result.returncode)


def _build_commands(args: argparse.Namespace) -> dict[str, list[str]]:
    config = _resolve(args.config)
    manifest = _resolve(args.manifest)
    recovery_json = _resolve(args.recovery_json)
    recovery_sh = _resolve(args.recovery_sh)
    credit_output_raw = _read_config_value(config, "RCA_BREV_CREDIT_EVIDENCE_JSON")
    credit_output = _resolve(Path(credit_output_raw)) if credit_output_raw else DEFAULT_CREDIT_EVIDENCE
    balance = "<current-brev-ui-balance>" if args.balance_eur is None else f"{args.balance_eur:.2f}"
    return {
        "prepare": [
            "python3",
            "scripts/prepare_success_variation_paid_batch.py",
            "--balance-eur",
            balance,
            "--budget-eur",
            f"{args.budget_eur:.2f}",
            "--config",
            str(config),
            "--credit-output",
            str(credit_output),
            "--force-credit",
            "--i-understand-this-arms-paid-run",
        ],
        "preflight": [
            "python3",
            "scripts/check_success_variation_paid_lifecycle_preflight.py",
            "--config",
            str(config),
            "--manifest",
            str(manifest),
            "--no-output",
            "--fail-on-blocked",
        ],
        "run": [
            "scripts/run_success_variation_batch_from_config.sh",
            str(config),
            "--run",
        ],
        "disarm": [
            "python3",
            "scripts/arm_success_variation_paid_env.py",
            "--config",
            str(config),
            "--output",
            str(config),
            "--disarm",
        ],
        "safety": ["./scripts/brev_paid_safety_status.sh"],
        "finalize": ["scripts/finalize_success_variation_batch.sh", str(manifest)],
        "policy_readiness": [
            "python3",
            "scripts/run_v0_offline_policy_readiness_pipeline.py",
            "--manifest",
            str(manifest),
        ],
        "recovery": [
            "python3",
            "scripts/plan_success_variation_recovery_batch.py",
            str(manifest),
            "--output-json",
            str(recovery_json),
            "--output-sh",
            str(recovery_sh),
        ],
    }


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _dry_run_report(args: argparse.Namespace, commands: dict[str, list[str]]) -> dict:
    config = _resolve(args.config)
    manifest = _resolve(args.manifest)
    return {
        "status": "DRY_RUN",
        "run_requested": bool(args.run),
        "balance_eur": None if args.balance_eur is None else round(args.balance_eur, 2),
        "budget_eur": round(args.budget_eur, 2),
        "config": _rel(config),
        "manifest": _rel(manifest),
        "execution_order": [
            "prepare",
            "preflight",
            "run",
            "disarm",
            "safety",
            "finalize",
            "policy_readiness",
        ],
        "failure_order": [
            "prepare",
            "preflight",
            "run",
            "disarm",
            "safety",
            "recovery",
        ],
        "commands": commands,
        "cleanup_guards": [
            "prepare failure disarms local paid env and reruns Brev safety",
            "preflight failure disarms local paid env and reruns Brev safety",
            "cleanup or Brev safety failure blocks finalize/policy readiness",
            "run failure disarms local paid env, reruns Brev safety, and writes a recovery plan",
            "KeyboardInterrupt disarms local paid env, reruns Brev safety, and writes a recovery plan",
            "success path requires final Brev safety to pass after policy-readiness handoff",
        ],
        "side_effects": {
            "writes_credit_evidence": False,
            "arms_local_env": False,
            "creates_paid_instance": False,
            "runs_remote_code": False,
            "copies_artifacts": False,
            "deletes_instances": False,
            "writes_recovery_plan": False,
        },
        "not_claims": [
            "not fresh Brev UI credit evidence",
            "not an armed local env",
            "not a paid run",
            "not success-variation result evidence",
            "not cleanup evidence",
        ],
    }


def _print_dry_run(args: argparse.Namespace, commands: dict[str, list[str]]) -> None:
    report = _dry_run_report(args, commands)
    print("[success-variation-lifecycle] DRY_RUN")
    print("[success-variation-lifecycle] would not create a paid instance")
    for label in ("prepare", "preflight", "run", "disarm", "safety", "finalize", "policy_readiness", "recovery"):
        print(f"- {label}: {_fmt(commands[label])}")
    print("[success-variation-lifecycle] facts=" + json.dumps(report, indent=2, sort_keys=True))


def _post_run_cleanup(commands: dict[str, list[str]]) -> int:
    """Disarm local paid acknowledgements and re-check Brev after arming or a paid run attempt."""

    disarm_status = _run("disarm", commands["disarm"])
    safety_status = _run("safety", commands["safety"])
    if disarm_status != 0:
        return disarm_status
    return safety_status


def _execute_lifecycle(args: argparse.Namespace, commands: dict[str, list[str]]) -> int:
    """Execute the paid lifecycle with fail-closed cleanup after local arming."""

    prepare_status = _run("prepare", commands["prepare"])
    if prepare_status != 0:
        cleanup_status = _post_run_cleanup(commands)
        if cleanup_status != 0:
            return cleanup_status
        return prepare_status

    cleanup_required = False
    cleanup_done = False
    try:
        cleanup_required = True
        preflight_status = _run("preflight", commands["preflight"])
        if preflight_status != 0:
            cleanup_status = _post_run_cleanup(commands)
            cleanup_done = True
            if cleanup_status != 0:
                return cleanup_status
            return preflight_status

        run_status = _run("run", commands["run"])
        cleanup_status = _post_run_cleanup(commands)
        cleanup_done = True
        if cleanup_status != 0:
            _run("recovery", commands["recovery"])
            return cleanup_status

        if run_status != 0:
            _run("recovery", commands["recovery"])
            return run_status

        finalize_status = _run("finalize", commands["finalize"])
        if finalize_status != 0:
            _run("recovery", commands["recovery"])
            return finalize_status

        policy_readiness_status = _run("policy_readiness", commands["policy_readiness"])
        if policy_readiness_status != 0:
            return policy_readiness_status

        final_safety_status = _run("safety_final", commands["safety"])
        if final_safety_status != 0:
            _run("recovery", commands["recovery"])
            return final_safety_status
        print("[success-variation-lifecycle] PASS")
        return 0
    except KeyboardInterrupt:
        print("[success-variation-lifecycle] INTERRUPTED")
        if cleanup_required and not cleanup_done:
            _post_run_cleanup(commands)
            cleanup_done = True
        _run("recovery", commands["recovery"])
        return 130
    finally:
        if cleanup_required and not cleanup_done:
            _post_run_cleanup(commands)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--balance-eur", type=_positive_float)
    parser.add_argument("--budget-eur", type=_positive_float, default=6.0)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--recovery-json", type=Path, default=DEFAULT_RECOVERY_JSON)
    parser.add_argument("--recovery-sh", type=Path, default=DEFAULT_RECOVERY_SH)
    parser.add_argument("--run", action="store_true", help="Actually run the paid lifecycle after all gates pass.")
    parser.add_argument("--dry-run", action="store_true", help="Print the lifecycle commands without side effects.")
    parser.add_argument(
        "--i-understand-this-can-create-paid-instance",
        action="store_true",
        help="Required with --run because the lifecycle can create one paid Brev instance.",
    )
    args = parser.parse_args()

    commands = _build_commands(args)
    if args.dry_run:
        _print_dry_run(args, commands)
        return 0

    blockers: list[str] = []
    if not args.run:
        blockers.append("pass --run only after checking the current Brev UI balance and budget")
    if args.balance_eur is None:
        blockers.append("pass --balance-eur with the current Brev UI organization balance")
    if not args.i_understand_this_can_create_paid_instance:
        blockers.append("pass --i-understand-this-can-create-paid-instance for this one deliberate paid batch")
    if blockers:
        print("[success-variation-lifecycle] BLOCKED")
        for blocker in blockers:
            print(f"- {blocker}")
        print("[success-variation-lifecycle] no paid instance was created")
        return 1

    return _execute_lifecycle(args, commands)


if __name__ == "__main__":
    raise SystemExit(main())
