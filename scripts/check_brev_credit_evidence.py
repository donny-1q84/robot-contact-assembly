#!/usr/bin/env python3
"""Validate manual Brev credit-balance evidence before paid runs.

The Brev CLI does not expose a read-only credit-balance command in this
workflow, so paid-run approval must not be reduced to a bare environment
variable. This gate validates a git-ignored local JSON evidence file recorded
from the current Brev UI organization credits page. The default local evidence
path is configs/brev_credit_verification.local.json.

It does not create, start, stop, delete, copy to, or execute on Brev instances.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = REPO_ROOT / "configs" / "brev_credit_verification.local.json"
EXPECTED_ORG_ID = "org-3BaYGdtoRGmgc77Z7NHHhPSD254"
EXPECTED_ORG_NAME = "NCA-57cf-29515"
DEFAULT_MAX_AGE_MINUTES = 60


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


def _parse_iso_utc(value: Any, failures: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        failures.append("verified_at_utc must be an ISO-8601 UTC timestamp")
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        failures.append(f"verified_at_utc is not parseable: {value!r}")
        return None
    if parsed.tzinfo is None:
        failures.append("verified_at_utc must include UTC timezone")
        return None
    return parsed.astimezone(timezone.utc)


def _float_field(payload: dict[str, Any], key: str, failures: list[str]) -> float | None:
    value = payload.get(key)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        failures.append(f"{key} must be numeric")
        return None
    if parsed < 0:
        failures.append(f"{key} must be non-negative")
        return None
    return parsed


def build_report(
    *,
    evidence_path: Path,
    required_budget_eur: float,
    max_age_minutes: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    evidence_path = _resolve(evidence_path)
    failures: list[str] = []
    blockers: list[str] = []

    if required_budget_eur <= 0:
        failures.append("required_budget_eur must be positive")
    if max_age_minutes <= 0:
        failures.append("max_age_minutes must be positive")

    if not evidence_path.is_file():
        return {
            "evidence": _rel(evidence_path),
            "status": "BLOCKED",
            "failures": failures,
            "blockers": ["Brev credit evidence file is missing"],
            "required_budget_eur": required_budget_eur,
            "max_age_minutes": max_age_minutes,
            "next_action": "copy_template_and_record_current_brev_ui_credit_balance",
        }

    payload = _load_json(evidence_path)
    if payload.get("evidence_name") != "brev_credit_balance_verification":
        failures.append("evidence_name must be brev_credit_balance_verification")
    if payload.get("organization_id") != EXPECTED_ORG_ID:
        failures.append(f"organization_id must be {EXPECTED_ORG_ID}")
    if payload.get("organization_name") != EXPECTED_ORG_NAME:
        failures.append(f"organization_name must be {EXPECTED_ORG_NAME}")
    source = str(payload.get("source", ""))
    if "Brev UI" not in source:
        failures.append("source must explicitly mention Brev UI")

    verified_at = _parse_iso_utc(payload.get("verified_at_utc"), failures)
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_minutes = None
    if verified_at is not None:
        age_minutes = (now_utc - verified_at).total_seconds() / 60.0
        if age_minutes < -1:
            failures.append("verified_at_utc is in the future")
        elif age_minutes > max_age_minutes:
            blockers.append(
                f"Brev credit evidence is too old: {age_minutes:.1f} minutes > {max_age_minutes} minutes"
            )

    balance = _float_field(payload, "balance_eur", failures)
    evidence_budget = _float_field(payload, "budget_eur", failures)
    if balance is not None and balance + 1e-9 < required_budget_eur:
        blockers.append(
            f"Brev credit balance {balance:.2f} EUR is below required budget {required_budget_eur:.2f} EUR"
        )
    if evidence_budget is not None and evidence_budget + 1e-9 < required_budget_eur:
        failures.append(
            f"evidence budget_eur {evidence_budget:.2f} is below required budget {required_budget_eur:.2f}"
        )

    if failures:
        status = "FAIL"
        next_action = "fix_brev_credit_evidence_schema"
    elif blockers:
        status = "BLOCKED"
        next_action = "refresh_current_brev_ui_credit_balance_evidence"
    else:
        status = "PASS"
        next_action = "credit_balance_evidence_ready"

    return {
        "evidence": _rel(evidence_path),
        "status": status,
        "failures": failures,
        "blockers": blockers,
        "organization_id": payload.get("organization_id"),
        "organization_name": payload.get("organization_name"),
        "source": payload.get("source"),
        "verified_at_utc": payload.get("verified_at_utc"),
        "age_minutes": round(age_minutes, 2) if age_minutes is not None else None,
        "balance_eur": balance,
        "required_budget_eur": required_budget_eur,
        "evidence_budget_eur": evidence_budget,
        "max_age_minutes": max_age_minutes,
        "next_action": next_action,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--required-budget-eur", type=float, required=True)
    parser.add_argument("--max-age-minutes", type=int, default=DEFAULT_MAX_AGE_MINUTES)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_report(
        evidence_path=args.evidence,
        required_budget_eur=args.required_budget_eur,
        max_age_minutes=args.max_age_minutes,
    )
    if args.output_json is not None:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[brev-credit-evidence] wrote JSON: {_rel(output_json)}")

    print("[brev-credit-evidence] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "PASS":
        print("[brev-credit-evidence] PASS")
        return 0
    if report["status"] == "BLOCKED":
        print("[brev-credit-evidence] BLOCKED")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
        print(f"[brev-credit-evidence] next_action={report['next_action']}")
        return 1 if args.fail_on_blocked else 0

    print("[brev-credit-evidence] FAIL")
    for failure in report["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
