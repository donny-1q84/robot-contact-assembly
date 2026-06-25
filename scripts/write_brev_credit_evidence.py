#!/usr/bin/env python3
"""Write git-ignored Brev UI credit evidence for one paid run.

Use this after manually checking the current Brev UI organization credit
balance. The script can write configs/brev_credit_verification.local.json by
default, validates it immediately, and refuses to write if the provided balance
does not cover the requested budget.

It does not create, start, stop, delete, copy to, or execute on Brev instances.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_brev_credit_evidence as credit_gate  # noqa: E402


DEFAULT_OUTPUT = REPO_ROOT / "configs" / "brev_credit_verification.local.json"
DEFAULT_SOURCE = "Brev UI organization credits page"
DEFAULT_INSTANCE_TYPE = "g6e.xlarge"


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be numeric, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"must be non-negative, got {value!r}")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--balance-eur", type=_positive_float, required=True)
    parser.add_argument("--budget-eur", type=_positive_float, default=6.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--checked-instance-type", default=DEFAULT_INSTANCE_TYPE)
    parser.add_argument("--checked-by", default="manual_ui_review")
    parser.add_argument("--max-age-minutes", type=int, default=credit_gate.DEFAULT_MAX_AGE_MINUTES)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output = _resolve(args.output)
    if args.budget_eur <= 0:
        print("[brev-credit-evidence-write] BLOCKED")
        print("- --budget-eur must be positive")
        return 1
    if args.balance_eur + 1e-9 < args.budget_eur:
        print("[brev-credit-evidence-write] BLOCKED")
        print(f"- balance {args.balance_eur:.2f} EUR is below budget {args.budget_eur:.2f} EUR")
        return 1
    if "Brev UI" not in args.source:
        print("[brev-credit-evidence-write] BLOCKED")
        print("- --source must mention Brev UI because the CLI has no balance command")
        return 1
    if output.exists() and not args.force:
        print(f"[brev-credit-evidence-write] exists: {_rel(output)}")
        print("[brev-credit-evidence-write] use --force after re-checking the current Brev UI balance")
        return 2

    payload = {
        "evidence_name": "brev_credit_balance_verification",
        "verified_at_utc": _utc_now(),
        "source": args.source,
        "organization_name": credit_gate.EXPECTED_ORG_NAME,
        "organization_id": credit_gate.EXPECTED_ORG_ID,
        "balance_eur": round(args.balance_eur, 2),
        "budget_eur": round(args.budget_eur, 2),
        "checked_instance_type": args.checked_instance_type,
        "checked_by": args.checked_by,
        "notes": "Generated from manually checked Brev UI balance; do not commit this local file.",
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = credit_gate.build_report(
        evidence_path=output,
        required_budget_eur=args.budget_eur,
        max_age_minutes=args.max_age_minutes,
    )
    print(f"[brev-credit-evidence-write] wrote: {_rel(output)}")
    print("[brev-credit-evidence-write] validation=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        print("[brev-credit-evidence-write] BLOCKED")
        return 1
    print("[brev-credit-evidence-write] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
