#!/usr/bin/env python3
"""Prepare, but do not run, one success-variation paid batch.

Use this only after reading the current Brev UI organization credit balance.
The helper writes fresh git-ignored credit evidence, arms the git-ignored local
env for one short-lived run, then runs the normal read-only --check-only gate.

It does not create, start, stop, delete, copy to, or execute on Brev instances.
If the final --check-only gate fails after arming, it disarms the local env.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
DEFAULT_CREDIT_OUTPUT = REPO_ROOT / "configs" / "brev_credit_verification.local.json"


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

    if args.dry_run:
        print("[success-variation-paid-prepare] DRY_RUN")
        print("- credit_evidence: " + " ".join(credit_cmd))
        print("- arm_local_env: " + " ".join(arm_cmd))
        print("- check_only: " + " ".join(check_cmd))
        print("[success-variation-paid-prepare] would not create a paid instance")
        return 0

    print(
        "[success-variation-paid-prepare] preparing one run from Brev UI balance "
        f"{args.balance_eur:.2f} EUR with budget {args.budget_eur:.2f} EUR"
    )
    print(f"[success-variation-paid-prepare] config={_rel(config)}")
    print(f"[success-variation-paid-prepare] credit_evidence={_rel(credit_output)}")

    status = _run(credit_cmd)
    if status != 0:
        return status

    status = _run(arm_cmd)
    if status != 0:
        return status

    status = _run(check_cmd)
    if status != 0:
        _disarm(config)
        return status

    print("[success-variation-paid-prepare] READY_FOR_SINGLE_PAID_RUN")
    print("[success-variation-paid-prepare] next: scripts/run_success_variation_batch_from_config.sh configs/success_variation_batch_run.local.env --run")
    print("[success-variation-paid-prepare] note: --run auto-disarms the local env on exit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
