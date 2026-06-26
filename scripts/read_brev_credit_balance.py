#!/usr/bin/env python3
"""Read the current Brev organization credit balance through the Brev API.

This is a read-only helper. It uses the local Brev CLI credentials to call the
same Brev control-plane host used by the CLI and returns only the organization
credit balance. It never prints tokens, card details, payment methods, or other
account data, and it does not create, start, stop, delete, copy to, or execute
on Brev instances.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
import urllib.error
import urllib.request


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_brev_credit_evidence as credit_gate  # noqa: E402


DEFAULT_CREDENTIALS = Path.home() / ".brev" / "credentials.json"
DEFAULT_BREV_BIN = Path.home() / "bin" / "brev"
DEFAULT_API_BASE = "https://brevapi.us-west-2-prod.control-plane.brev.dev"
DEFAULT_TIMEOUT_SECONDS = 15


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


def _load_token(credentials_path: Path) -> tuple[str | None, list[str]]:
    if not credentials_path.is_file():
        return None, [f"Brev credentials file is missing: {_rel(credentials_path)}"]
    try:
        payload = json.loads(credentials_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"Brev credentials file is unreadable: {_rel(credentials_path)} ({exc})"]
    token = payload.get("access_token")
    if not isinstance(token, str) or not token.strip():
        return None, ["Brev credentials do not contain an access_token"]
    return token, []


def _decimal(value: Any, failures: list[str]) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        failures.append(f"balance_usd is not numeric: {value!r} ({exc})")
        return None
    if parsed < 0:
        failures.append(f"balance_usd must be non-negative, got {value!r}")
        return None
    return parsed


def _side_effects(*, refresh_attempted: bool) -> dict[str, bool]:
    return {
        "reads_brev_api": True,
        "refreshes_brev_credentials_with_cli": refresh_attempted,
        "prints_token": False,
        "writes_credit_evidence": False,
        "writes_local_env": False,
        "creates_paid_instance": False,
        "runs_remote_code": False,
        "starts_isaac": False,
        "copies_artifacts": False,
        "deletes_instances": False,
    }


def _call_credits_endpoint(
    *,
    endpoint: str,
    token: str,
    timeout_seconds: int,
) -> tuple[int | None, dict[str, Any] | None, list[str]]:
    request = urllib.request.Request(
        endpoint,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return int(response.status), json.loads(response.read().decode("utf-8")), []
    except urllib.error.HTTPError as exc:
        return int(exc.code), None, [f"Brev credits endpoint returned HTTP {exc.code}"]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return None, None, [f"Brev credits endpoint could not be read: {exc}"]


def _refresh_credentials(*, brev_bin: Path, timeout_seconds: int) -> list[str]:
    if not brev_bin.is_file():
        return [f"Brev CLI not found for credential refresh: {_rel(brev_bin)}"]
    try:
        completed = subprocess.run(
            [str(brev_bin), "ls", "orgs", "--json"],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [f"Brev CLI credential refresh failed: {exc}"]
    if completed.returncode != 0:
        tail = (completed.stderr or "").strip().splitlines()[-3:]
        return ["Brev CLI credential refresh returned nonzero exit: " + " | ".join(tail)]
    return []


def build_report(
    *,
    credentials_path: Path,
    brev_bin: Path,
    api_base: str,
    organization_id: str,
    required_budget_eur: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    credentials_path = credentials_path.expanduser()
    endpoint = f"{api_base.rstrip('/')}/api/organizations/{organization_id}/credits"
    failures: list[str] = []
    blockers: list[str] = []
    token, token_failures = _load_token(credentials_path)
    failures.extend(token_failures)

    payload: dict[str, Any] | None = None
    http_status: int | None = None
    refresh_attempted = False
    if token:
        http_status, payload, endpoint_failures = _call_credits_endpoint(
            endpoint=endpoint,
            token=token,
            timeout_seconds=timeout_seconds,
        )
        failures.extend(endpoint_failures)
        if http_status in {401, 403}:
            refresh_attempted = True
            failures.clear()
            refresh_failures = _refresh_credentials(brev_bin=brev_bin, timeout_seconds=timeout_seconds)
            if refresh_failures:
                failures.extend(refresh_failures)
            else:
                token, token_failures = _load_token(credentials_path)
                failures.extend(token_failures)
                if token:
                    http_status, payload, endpoint_failures = _call_credits_endpoint(
                        endpoint=endpoint,
                        token=token,
                        timeout_seconds=timeout_seconds,
                    )
                    failures.extend(endpoint_failures)

    balance = None
    if payload is not None:
        balance = _decimal(payload.get("balance_usd"), failures)
    if balance is not None and balance + Decimal("0.000000001") < Decimal(str(required_budget_eur)):
        blockers.append(
            f"Brev API credit balance {balance} USD is below required budget {required_budget_eur:.2f}"
        )

    if failures:
        status = "UNAVAILABLE"
        next_action = "fall_back_to_current_brev_ui_balance_review"
    elif blockers:
        status = "BLOCKED"
        next_action = "add_brev_credits_or_reduce_budget_before_paid_run"
    else:
        status = "PASS"
        next_action = "write_fresh_credit_evidence_from_current_balance"

    return {
        "check_name": "brev_api_credit_balance",
        "status": status,
        "organization_id": organization_id,
        "endpoint": endpoint,
        "http_status": http_status,
        "balance_usd": None if balance is None else float(balance),
        "balance_usd_raw": None if balance is None else str(balance),
        "required_budget_eur": required_budget_eur,
        "currency_note": (
            "Brev API returns balance_usd; this project currently uses the same numeric "
            "budget threshold to fail closed. A zero balance blocks in any currency."
        ),
        "failures": failures,
        "blockers": blockers,
        "next_action": next_action,
        "credentials": _rel(credentials_path),
        "side_effects": _side_effects(refresh_attempted=refresh_attempted),
        "not_claims": [
            "not a Brev UI screenshot",
            "not a paid run",
            "not an armed local env",
            "not success-variation result evidence",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--brev-bin", type=Path, default=DEFAULT_BREV_BIN)
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--organization-id", default=credit_gate.EXPECTED_ORG_ID)
    parser.add_argument("--required-budget-eur", type=_positive_float, default=6.0)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_report(
        credentials_path=args.credentials,
        brev_bin=args.brev_bin.expanduser(),
        api_base=args.api_base,
        organization_id=args.organization_id,
        required_budget_eur=args.required_budget_eur,
        timeout_seconds=max(1, args.timeout_seconds),
    )
    if args.output_json is not None:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[brev-api-credit] wrote JSON: {_rel(output_json)}")

    print("[brev-api-credit] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "PASS":
        print("[brev-api-credit] PASS")
        return 0
    if report["status"] == "BLOCKED":
        print("[brev-api-credit] BLOCKED")
        for blocker in report["blockers"]:
            print(f"- {blocker}")
        print(f"[brev-api-credit] next_action={report['next_action']}")
        return 1 if args.fail_on_blocked else 0

    print("[brev-api-credit] UNAVAILABLE")
    for failure in report["failures"]:
        print(f"- {failure}")
    print(f"[brev-api-credit] next_action={report['next_action']}")
    return 1 if args.fail_on_blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
