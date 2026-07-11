#!/usr/bin/env python3
"""Prepare, but do not run, one success-variation paid batch.

Use this only after reading the current Brev UI organization credit balance.
The helper writes fresh git-ignored credit evidence, arms the git-ignored local
env for one short-lived run, runs the normal read-only --check-only gate to
refresh the run packet, then runs the aggregate paid lifecycle preflight.

It does not create, start, stop, delete, copy to, or execute on Brev instances.
If the --check-only gate or aggregate preflight fails after arming, it disarms
the local env.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import read_brev_credit_balance as api_credit_gate  # noqa: E402

DEFAULT_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
DEFAULT_CREDIT_OUTPUT = REPO_ROOT / "configs" / "brev_credit_verification.local.json"
DEFAULT_RUN_PACKET = REPO_ROOT / "artifacts" / "analysis" / "success_variation_run_packet_2026-06-25.json"


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


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be numeric, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"must be non-negative, got {value!r}")
    return parsed


def _run(args: list[str]) -> int:
    print("[success-variation-paid-prepare] run: " + " ".join(args), flush=True)
    result = subprocess.run(args, cwd=REPO_ROOT, check=False)
    return int(result.returncode)


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


def _disarm(config: Path) -> None:
    print("[success-variation-paid-prepare] disarming local env after failed readiness", flush=True)
    _run(
        [
            "python3",
            "scripts/arm_success_variation_paid_env.py",
            "--config",
            str(config),
            "--output",
            str(config),
            "--disarm",
        ]
    )


def _load_api_credit_report(path: Path) -> dict:
    payload = json.loads(_resolve(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Brev API credit output must be a JSON object")
    return payload


def _api_credit_report(*, budget_eur: float, api_credit_output: Path | None) -> dict:
    if api_credit_output is not None:
        return _load_api_credit_report(api_credit_output)
    return api_credit_gate.build_report(
        credentials_path=api_credit_gate.DEFAULT_CREDENTIALS,
        brev_bin=api_credit_gate.DEFAULT_BREV_BIN,
        api_base=api_credit_gate.DEFAULT_API_BASE,
        organization_id=api_credit_gate.credit_gate.EXPECTED_ORG_ID,
        required_budget_eur=budget_eur,
        timeout_seconds=api_credit_gate.DEFAULT_TIMEOUT_SECONDS,
    )


def _api_credit_blockers(report: dict) -> list[str]:
    blockers = report.get("blockers")
    if isinstance(blockers, list) and blockers:
        return [str(item) for item in blockers]
    failures = report.get("failures")
    if isinstance(failures, list) and failures:
        return [str(item) for item in failures]
    status = report.get("status")
    if status and status != "PASS":
        return [f"Brev API credit balance status is {status}"]
    return []


def _dry_run_report(
    *,
    balance_eur: float,
    budget_eur: float,
    config: Path,
    credit_output: Path,
    run_packet: Path,
    credit_cmd: list[str],
    arm_cmd: list[str],
    check_cmd: list[str],
    preflight_cmd: list[str],
    api_credit_cmd: list[str],
) -> dict:
    return {
        "status": "DRY_RUN",
        "balance_eur": round(balance_eur, 2),
        "budget_eur": round(budget_eur, 2),
        "config": _rel(config),
        "credit_evidence": _rel(credit_output),
        "run_packet": _rel(run_packet),
        "side_effects": {
            "reads_brev_api": False,
            "writes_credit_evidence": False,
            "arms_local_env": False,
            "runs_check_only": False,
            "runs_aggregate_preflight": False,
            "creates_paid_instance": False,
            "runs_remote_code": False,
        },
        "steps": [
            {"step": "api_credit_check", "command": api_credit_cmd},
            {"step": "write_credit_evidence", "command": credit_cmd},
            {"step": "arm_local_env", "command": arm_cmd},
            {"step": "check_only", "command": check_cmd},
            {"step": "aggregate_preflight", "command": preflight_cmd},
        ],
        "cleanup_guards": [
            "Brev API credit BLOCKED or UNAVAILABLE stops before writing credit evidence or arming the local env",
            "check-only failure after arming disarms the local env",
            "aggregate preflight failure after arming disarms the local env",
            "KeyboardInterrupt after arming disarms the local env and exits 130",
            "unexpected exception after arming disarms the local env and exits 1",
        ],
        "next_command_after_review": [
            "python3",
            "scripts/prepare_success_variation_paid_batch.py",
            "--balance-eur",
            f"{balance_eur:.2f}",
            "--budget-eur",
            f"{budget_eur:.2f}",
            "--force-credit",
            "--i-understand-this-arms-paid-run",
        ],
        "not_claims": [
            "not fresh Brev UI credit evidence",
            "not an armed local env",
            "not a paid run",
            "not success-variation result evidence",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--balance-eur", type=_positive_float, required=True)
    parser.add_argument("--budget-eur", type=_positive_float, default=6.0)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--credit-output", type=Path, default=DEFAULT_CREDIT_OUTPUT)
    parser.add_argument("--max-age-minutes", type=int, default=60)
    parser.add_argument(
        "--brev-safety-output",
        type=Path,
        help="Use a saved brev_paid_safety_status.sh output for offline arm-helper validation.",
    )
    parser.add_argument(
        "--api-credit-output",
        type=Path,
        help="Use saved read_brev_credit_balance.py JSON output for offline tests; default reads live Brev API credits.",
    )
    parser.add_argument(
        "--force-credit",
        action="store_true",
        help="Overwrite existing credit evidence after re-checking the current Brev UI balance.",
    )
    parser.add_argument(
        "--i-understand-this-arms-paid-run",
        action="store_true",
        help="Required because this writes short-lived paid-run acknowledgements to the local env.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the intended steps without writing evidence, arming, or running check-only.",
    )
    args = parser.parse_args()

    config = _resolve(args.config)
    credit_output = _resolve(args.credit_output)
    run_packet_raw = _read_config_value(config, "RCA_SUCCESS_VARIATION_RUN_PACKET_JSON")
    run_packet = _resolve(Path(run_packet_raw)) if run_packet_raw else DEFAULT_RUN_PACKET
    if not args.i_understand_this_arms_paid_run:
        print("[success-variation-paid-prepare] BLOCKED")
        print("- pass --i-understand-this-arms-paid-run after checking the current Brev UI balance")
        return 1

    credit_cmd = [
        "python3",
        "scripts/write_brev_credit_evidence.py",
        "--balance-eur",
        f"{args.balance_eur:.2f}",
        "--budget-eur",
        f"{args.budget_eur:.2f}",
        "--output",
        str(credit_output),
        "--max-age-minutes",
        str(args.max_age_minutes),
    ]
    if args.force_credit:
        credit_cmd.append("--force")

    api_credit_cmd = [
        "python3",
        "scripts/read_brev_credit_balance.py",
        "--required-budget-eur",
        f"{args.budget_eur:.2f}",
    ]
    if args.api_credit_output is not None:
        api_credit_cmd = ["cat", str(_resolve(args.api_credit_output))]

    arm_cmd = [
        "python3",
        "scripts/arm_success_variation_paid_env.py",
        "--config",
        str(config),
        "--output",
        str(config),
        "--i-understand-this-arms-paid-run",
    ]
    if args.brev_safety_output is not None:
        arm_cmd.extend(["--brev-safety-output", str(_resolve(args.brev_safety_output))])

    check_cmd = [
        "scripts/run_success_variation_batch_from_config.sh",
        str(config),
        "--check-only",
    ]
    preflight_cmd = [
        "python3",
        "scripts/check_success_variation_paid_lifecycle_preflight.py",
        "--config",
        str(config),
        "--run-packet",
        str(run_packet),
        "--no-output",
        "--fail-on-blocked",
    ]
    if args.api_credit_output is not None:
        preflight_cmd.extend(["--api-credit-output", str(_resolve(args.api_credit_output))])

    if args.dry_run:
        report = _dry_run_report(
            balance_eur=args.balance_eur,
            budget_eur=args.budget_eur,
            config=config,
            credit_output=credit_output,
            run_packet=run_packet,
            credit_cmd=credit_cmd,
            arm_cmd=arm_cmd,
            check_cmd=check_cmd,
            preflight_cmd=preflight_cmd,
            api_credit_cmd=api_credit_cmd,
        )
        print("[success-variation-paid-prepare] DRY_RUN")
        print("- api_credit_check: " + " ".join(api_credit_cmd))
        print("- credit_evidence: " + " ".join(credit_cmd))
        print("- arm_local_env: " + " ".join(arm_cmd))
        print("- check_only: " + " ".join(check_cmd))
        print("- aggregate_preflight: " + " ".join(preflight_cmd))
        print("[success-variation-paid-prepare] would not create a paid instance")
        print("[success-variation-paid-prepare] facts=" + json.dumps(report, indent=2, sort_keys=True))
        return 0

    print(
        "[success-variation-paid-prepare] preparing one run from Brev UI balance "
        f"{args.balance_eur:.2f} EUR with budget {args.budget_eur:.2f} EUR"
    )
    print(f"[success-variation-paid-prepare] config={_rel(config)}")
    print(f"[success-variation-paid-prepare] credit_evidence={_rel(credit_output)}")

    try:
        api_credit = _api_credit_report(budget_eur=args.budget_eur, api_credit_output=args.api_credit_output)
    except Exception as exc:  # noqa: BLE001 - paid preparation must fail closed.
        print("[success-variation-paid-prepare] BLOCKED")
        print(f"- Brev API credit check failed before writing evidence or arming: {exc}")
        print("[success-variation-paid-prepare] no credit evidence was written")
        print("[success-variation-paid-prepare] local env was not armed")
        return 1
    print("[success-variation-paid-prepare] api_credit_status=" + str(api_credit.get("status")))
    print("[success-variation-paid-prepare] api_credit_balance_usd=" + str(api_credit.get("balance_usd")))
    if api_credit.get("status") != "PASS":
        print("[success-variation-paid-prepare] BLOCKED")
        for blocker in _api_credit_blockers(api_credit):
            print(f"- {blocker}")
        print("[success-variation-paid-prepare] no credit evidence was written")
        print("[success-variation-paid-prepare] local env was not armed")
        return 1

    status = _run(credit_cmd)
    if status != 0:
        return status

    status = _run(arm_cmd)
    if status != 0:
        return status

    try:
        status = _run(check_cmd)
        if status != 0:
            _disarm(config)
            return status

        status = _run(preflight_cmd)
        if status != 0:
            _disarm(config)
            return status
    except KeyboardInterrupt:
        print("[success-variation-paid-prepare] INTERRUPTED")
        _disarm(config)
        return 130
    except Exception as exc:
        print(f"[success-variation-paid-prepare] FAILED_AFTER_ARM: {exc}")
        _disarm(config)
        return 1

    print("[success-variation-paid-prepare] READY_FOR_SINGLE_PAID_RUN")
    print("[success-variation-paid-prepare] next: scripts/run_success_variation_batch_from_config.sh configs/success_variation_batch_run.local.env --run")
    print("[success-variation-paid-prepare] note: --run auto-disarms the local env on exit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
