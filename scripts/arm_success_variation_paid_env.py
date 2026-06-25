#!/usr/bin/env python3
"""Arm the ignored success-variation local env for one paid batch.

This helper only edits configs/success_variation_batch_run.local.env. It does not create, start, stop, delete, copy to, or execute on Brev instances.

It refuses to arm unless:
- Brev UI credit evidence is fresh and covers the configured budget.
- Brev safety status is SAFE_NO_VISIBLE_PAID_INSTANCE.
- The existing local env has explicit budget, hourly estimate, TTL, and credit
  evidence settings.
- The operator passes --i-understand-this-arms-paid-run.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import subprocess
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_brev_credit_evidence as credit_gate  # noqa: E402


DEFAULT_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
DEFAULT_OUTPUT = DEFAULT_CONFIG
REQUIRED_KEYS = {
    "RCA_PAID_BUDGET_EUR",
    "RCA_PAID_ESTIMATED_EUR_PER_HOUR",
    "RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES",
    "RCA_BREV_CREDIT_EVIDENCE_JSON",
    "RCA_BREV_CREDIT_EVIDENCE_MAX_AGE_MINUTES",
    "RCA_PAID_ARMING_MAX_AGE_MINUTES",
}
ACK_KEYS = (
    "RCA_ALLOW_PAID_BREV_CREATE",
    "RCA_BREV_CREDITS_VERIFIED",
    "RCA_ACK_BREV_LIFECYCLE_RISK",
)
DISARMED_VALUES = {
    "RCA_ALLOW_PAID_BREV_CREATE": "0",
    "RCA_BREV_CREDITS_VERIFIED": "0",
    "RCA_ACK_BREV_LIFECYCLE_RISK": "0",
    "RCA_PAID_ARMED_AT_UTC": "",
}


def _armed_values() -> dict[str, str]:
    return {
        "RCA_ALLOW_PAID_BREV_CREATE": "1",
        "RCA_BREV_CREDITS_VERIFIED": "1",
        "RCA_ACK_BREV_LIFECYCLE_RISK": "1",
        "RCA_PAID_ARMED_AT_UTC": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


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
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise RuntimeError(f"invalid env key on line {line_no}: {key}")
        if not (key.startswith("RCA_") or key == "BREV_BIN"):
            raise RuntimeError(f"disallowed env key on line {line_no}: {key}")
        values[key] = value
    return values


def _write_env(path: Path, values: dict[str, str]) -> None:
    ordered = [
        "RCA_SUCCESS_VARIATION_MANIFEST",
        "RCA_SUCCESS_VARIATION_ENV_NAME",
        "RCA_SUCCESS_VARIATION_REMOTE_ROOT",
        "RCA_SUCCESS_VARIATION_COMPOSE_ROOT",
        "RCA_SUCCESS_VARIATION_TASK",
        "RCA_SUCCESS_VARIATION_STEPS",
        "RCA_SUCCESS_VARIATION_SEED",
        "RCA_SUCCESS_VARIATION_INSTANCE_TYPE",
        "RCA_SUCCESS_VARIATION_MIN_DISK",
        "RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES",
        "RCA_SUCCESS_VARIATION_TRACE_TIMEOUT_SECONDS",
        "RCA_SUCCESS_VARIATION_TRACE_TIMEOUT_KILL_SECONDS",
        "RCA_PAID_BUDGET_EUR",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR",
        "RCA_BREV_CREDIT_EVIDENCE_JSON",
        "RCA_BREV_CREDIT_EVIDENCE_MAX_AGE_MINUTES",
        "RCA_PAID_ARMED_AT_UTC",
        "RCA_PAID_ARMING_MAX_AGE_MINUTES",
        "RCA_ALLOW_PAID_BREV_CREATE",
        "RCA_BREV_CREDITS_VERIFIED",
        "RCA_ACK_BREV_LIFECYCLE_RISK",
    ]
    lines = [
        "# Armed for one deliberate success-variation paid batch.",
        "# This file is git-ignored. Run --check-only immediately before --run.",
    ]
    emitted: set[str] = set()
    for key in ordered:
        if key in values:
            lines.append(f"{key}={values[key]}")
            emitted.add(key)
    for key in sorted(set(values) - emitted):
        lines.append(f"{key}={values[key]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _float_value(values: dict[str, str], key: str, blockers: list[str]) -> float | None:
    raw = values.get(key, "").strip()
    if not raw:
        blockers.append(f"{key} is missing")
        return None
    try:
        parsed = float(raw)
    except ValueError:
        blockers.append(f"{key} must be numeric, got {raw!r}")
        return None
    if parsed <= 0:
        blockers.append(f"{key} must be positive, got {raw!r}")
        return None
    return parsed


def _int_value(values: dict[str, str], key: str, blockers: list[str]) -> int | None:
    raw = values.get(key, "").strip()
    if not raw:
        blockers.append(f"{key} is missing")
        return None
    try:
        parsed = int(raw)
    except ValueError:
        blockers.append(f"{key} must be an integer, got {raw!r}")
        return None
    if parsed <= 0:
        blockers.append(f"{key} must be positive, got {raw!r}")
        return None
    return parsed


def _parse_brev_safety_output(text: str, *, exit_code: int) -> dict[str, Any]:
    status = None
    for line in text.splitlines():
        if line.startswith("[brev-safety] status="):
            status = line.split("=", 1)[1].strip()
    return {
        "exit_code": exit_code,
        "status": status,
        "output_tail": text[-3000:],
    }


def _brev_safety(saved_output: Path | None = None) -> dict[str, Any]:
    if saved_output is not None:
        return _parse_brev_safety_output(saved_output.read_text(encoding="utf-8"), exit_code=0)
    result = subprocess.run(
        ["./scripts/brev_paid_safety_status.sh"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
        check=False,
    )
    return _parse_brev_safety_output(result.stdout, exit_code=result.returncode)


def build_report(config_path: Path, *, brev_safety_output: Path | None = None) -> dict[str, Any]:
    blockers: list[str] = []
    config_path = _resolve(config_path)
    if not config_path.is_file():
        return {
            "status": "BLOCKED",
            "config": _rel(config_path),
            "blockers": ["local env config is missing"],
        }
    values = _read_env(config_path)
    missing = sorted(REQUIRED_KEYS - set(values))
    if missing:
        blockers.append("local env missing required keys: " + ", ".join(missing))
    budget = _float_value(values, "RCA_PAID_BUDGET_EUR", blockers)
    _float_value(values, "RCA_PAID_ESTIMATED_EUR_PER_HOUR", blockers)
    _int_value(values, "RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES", blockers)
    max_age = _int_value(values, "RCA_BREV_CREDIT_EVIDENCE_MAX_AGE_MINUTES", blockers)
    _int_value(values, "RCA_PAID_ARMING_MAX_AGE_MINUTES", blockers)

    credit_report: dict[str, Any] | None = None
    credit_path_raw = values.get("RCA_BREV_CREDIT_EVIDENCE_JSON", "").strip()
    if budget is not None and max_age is not None and credit_path_raw:
        credit_report = credit_gate.build_report(
            evidence_path=_resolve(Path(credit_path_raw)),
            required_budget_eur=budget,
            max_age_minutes=max_age,
        )
        if credit_report.get("status") != "PASS":
            blockers.append("Brev UI credit evidence must pass before arming paid local env")

    safety = _brev_safety(_resolve(brev_safety_output) if brev_safety_output is not None else None)
    if safety.get("exit_code") != 0 or safety.get("status") != "SAFE_NO_VISIBLE_PAID_INSTANCE":
        blockers.append("Brev safety status must be SAFE_NO_VISIBLE_PAID_INSTANCE before arming paid local env")

    return {
        "status": "PASS" if not blockers else "BLOCKED",
        "config": _rel(config_path),
        "blockers": list(dict.fromkeys(blockers)),
        "credit_evidence": credit_report,
        "brev_safety": safety,
        "budget_eur": budget,
        "armed_values": {key: "1" for key in ACK_KEYS},
        "armed_at_key": "RCA_PAID_ARMED_AT_UTC",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--brev-safety-output",
        type=Path,
        help="Use a saved brev_paid_safety_status.sh output for offline validation tests.",
    )
    parser.add_argument("--i-understand-this-arms-paid-run", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disarm", action="store_true", help="Reset paid acknowledgements to 0 and clear the armed timestamp.")
    args = parser.parse_args()

    if args.disarm:
        config_path = _resolve(args.config)
        output_path = _resolve(args.output)
        values = _read_env(config_path)
        values.update(DISARMED_VALUES)
        _write_env(output_path, values)
        print(f"[success-variation-arm] disarmed env: {_rel(output_path)}")
        return 0

    report = build_report(args.config, brev_safety_output=args.brev_safety_output)
    print("[success-variation-arm] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "PASS":
        print("[success-variation-arm] BLOCKED")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
        return 1
    if not args.i_understand_this_arms_paid_run:
        print("[success-variation-arm] BLOCKED")
        print("- pass --i-understand-this-arms-paid-run to write paid acknowledgements")
        return 1
    if args.dry_run:
        print("[success-variation-arm] DRY_RUN_READY")
        return 0

    config_path = _resolve(args.config)
    output_path = _resolve(args.output)
    values = _read_env(config_path)
    values.update(_armed_values())
    _write_env(output_path, values)
    print(f"[success-variation-arm] wrote armed env: {_rel(output_path)}")
    print("[success-variation-arm] next: run check-only, then one deliberate --run if it is READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
