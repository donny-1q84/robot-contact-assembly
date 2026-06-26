#!/usr/bin/env python3
"""Diagnose why the fixed-budget Brev paid run is still credit-blocked.

This helper is read-only. It checks the active Brev organization, visible
instances, CLI version, API credit balance, and the existing credit review
packet. It does not open a browser, write credit evidence, arm local env state,
create paid instances, run remote code, start Isaac, copy artifacts, or delete
instances.
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

import check_brev_credit_evidence as credit_gate  # noqa: E402
import prepare_brev_credit_review as credit_review  # noqa: E402
import read_brev_credit_balance as api_credit_gate  # noqa: E402


DEFAULT_CONFIG = credit_review.DEFAULT_CONFIG
DEFAULT_MANIFEST = credit_review.DEFAULT_MANIFEST
DEFAULT_RUN_PACKET = credit_review.DEFAULT_RUN_PACKET
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "brev_credit_blocker_diagnosis.json"


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


def _nonnegative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be numeric, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"must be non-negative, got {value!r}")
    return parsed


def _run_brev(args: list[str], *, timeout_seconds: int) -> dict[str, Any]:
    command = [str(api_credit_gate.DEFAULT_BREV_BIN), *args]
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=max(1, timeout_seconds),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command": command,
            "exit_code": None,
            "stdout": "",
            "stderr_tail": str(exc),
            "json": None,
        }
    stdout = completed.stdout or ""
    parsed_json = None
    try:
        parsed_json = json.loads(stdout)
    except json.JSONDecodeError:
        parsed_json = None
    return {
        "command": command,
        "exit_code": int(completed.returncode),
        "stdout": stdout.strip(),
        "stderr_tail": "\n".join((completed.stderr or "").strip().splitlines()[-5:]),
        "json": parsed_json,
    }


def _active_org(orgs: dict[str, Any]) -> dict[str, Any]:
    payload = orgs.get("json")
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("is_active") is True:
                return item
    return {}


def _visible_instance_count(instances: dict[str, Any]) -> int | None:
    payload = instances.get("json")
    if not isinstance(payload, dict):
        return None
    workspaces = payload.get("workspaces")
    if workspaces is None:
        return 0
    if isinstance(workspaces, list):
        return len(workspaces)
    return None


def _status(*, review: dict[str, Any], active_org: dict[str, Any], visible_instances: int | None) -> tuple[str, str]:
    api_credit = review.get("api_credit_balance") if isinstance(review.get("api_credit_balance"), dict) else {}
    consistency = review.get("credit_consistency") if isinstance(review.get("credit_consistency"), dict) else {}
    if active_org.get("id") != credit_gate.EXPECTED_ORG_ID:
        return "WRONG_ACTIVE_ORG", "set_active_org_to_expected_project_org"
    if visible_instances not in {0, None}:
        return "PAID_INSTANCE_VISIBLE", "stop_or_delete_visible_paid_instances_before_retry"
    if consistency.get("status") == "UI_API_MISMATCH_API_BLOCKED":
        return "UI_API_MISMATCH_BLOCKED", str(consistency.get("next_action"))
    if api_credit.get("status") == "BLOCKED":
        return "API_CREDIT_BLOCKED", str(api_credit.get("next_action"))
    if api_credit.get("status") == "UNAVAILABLE":
        return "API_CREDIT_UNAVAILABLE", str(api_credit.get("next_action"))
    if consistency.get("paid_prepare_allowed") is True:
        return "READY_FOR_CREDIT_EVIDENCE_OR_PAID_PREFLIGHT", "rerun_paid_lifecycle_preflight_before_create"
    return "BLOCKED_REVIEW_REQUIRED", str(consistency.get("next_action") or review.get("status"))


def _likely_causes(status: str) -> list[str]:
    if status == "UI_API_MISMATCH_BLOCKED":
        return [
            "credits were added to a different Brev organization or account",
            "the browser UI is showing a stale or different logged-in session",
            "the credit top-up has not propagated to the organization credits API yet",
            "the paid run should remain blocked until the org credits API reports PASS",
        ]
    if status == "API_CREDIT_BLOCKED":
        return [
            "the active Brev organization has insufficient API-visible credits",
            "no current UI balance was provided for comparison",
            "paid prep should remain blocked before writing local evidence",
        ]
    if status == "WRONG_ACTIVE_ORG":
        return ["the Brev CLI active organization is not the project organization"]
    return []


def build_report(
    *,
    config_path: Path,
    manifest_path: Path,
    run_packet_path: Path,
    balance_eur: float | None,
    api_credit_output: Path | None,
    command_timeout_seconds: int,
) -> dict[str, Any]:
    orgs = _run_brev(["ls", "orgs", "--json"], timeout_seconds=command_timeout_seconds)
    instances = _run_brev(["ls", "instances", "--json", "--all"], timeout_seconds=command_timeout_seconds)
    version = _run_brev(["--version", "--no-check-latest"], timeout_seconds=command_timeout_seconds)
    active_org = _active_org(orgs)
    visible_instances = _visible_instance_count(instances)
    review = credit_review.build_packet(
        config_path=_resolve(config_path),
        manifest_path=_resolve(manifest_path),
        run_packet_path=_resolve(run_packet_path),
        command_timeout_seconds=command_timeout_seconds,
        brev_safety_output=None,
        source_status_output=None,
        open_requested=False,
        balance_eur=balance_eur,
        api_credit_output=api_credit_output,
    )
    status, next_action = _status(
        review=review,
        active_org=active_org,
        visible_instances=visible_instances,
    )
    return {
        "diagnosis_name": "brev_credit_blocker_diagnosis",
        "status": status,
        "next_action": next_action,
        "expected_organization": {
            "name": credit_gate.EXPECTED_ORG_NAME,
            "id": credit_gate.EXPECTED_ORG_ID,
        },
        "active_organization": active_org,
        "cli_version": version.get("stdout"),
        "orgs_command_exit": orgs.get("exit_code"),
        "instances_command_exit": instances.get("exit_code"),
        "visible_instances": visible_instances,
        "workspaces_null": visible_instances == 0,
        "dashboard_url": credit_review.BREV_ORG_DASHBOARD_URL,
        "api_credit_balance": review.get("api_credit_balance"),
        "balance_preview": review.get("balance_preview"),
        "credit_consistency": review.get("credit_consistency"),
        "paid_review_status": review.get("status"),
        "paid_prepare_allowed": (
            review.get("credit_consistency", {}).get("paid_prepare_allowed")
            if isinstance(review.get("credit_consistency"), dict)
            else False
        ),
        "likely_causes": _likely_causes(status),
        "safe_next_steps": [
            "confirm the Brev UI is logged into the same account and org shown in dashboard_url",
            "confirm any top-up or redeem code was applied to expected_organization.id",
            "rerun this diagnosis after top-up or login refresh",
            "only continue to paid prep after paid_prepare_allowed is true and the aggregate paid preflight passes",
        ],
        "side_effects": {
            "reads_brev_cli": True,
            "reads_brev_api": True,
            "opens_dashboard": False,
            "writes_credit_evidence": False,
            "writes_local_env": False,
            "creates_paid_instance": False,
            "runs_remote_code": False,
            "starts_isaac": False,
            "copies_artifacts": False,
            "deletes_instances": False,
        },
        "not_claims": [
            "not fresh credit evidence",
            "not a paid run",
            "not an armed local env",
            "not success-variation result evidence",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--run-packet", type=Path, default=DEFAULT_RUN_PACKET)
    parser.add_argument("--balance-eur", type=_nonnegative_float)
    parser.add_argument("--api-credit-output", type=Path)
    parser.add_argument("--command-timeout-seconds", type=int, default=60)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_report(
        config_path=args.config,
        manifest_path=args.manifest,
        run_packet_path=args.run_packet,
        balance_eur=args.balance_eur,
        api_credit_output=args.api_credit_output,
        command_timeout_seconds=max(1, args.command_timeout_seconds),
    )
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[brev-credit-diagnosis] wrote JSON: {_rel(output_json)}")

    print("[brev-credit-diagnosis] facts=" + json.dumps(report, indent=2, sort_keys=True))
    print("[brev-credit-diagnosis] status=" + report["status"])
    print("[brev-credit-diagnosis] active_org_id=" + str(report["active_organization"].get("id")))
    print("[brev-credit-diagnosis] api_credit_status=" + str(report.get("api_credit_balance", {}).get("status")))
    print("[brev-credit-diagnosis] api_credit_balance_usd=" + str(report.get("api_credit_balance", {}).get("balance_usd")))
    print(
        "[brev-credit-diagnosis] credit_consistency_status="
        + str(report.get("credit_consistency", {}).get("status"))
    )
    print("[brev-credit-diagnosis] paid_prepare_allowed=" + str(report["paid_prepare_allowed"]))
    print("[brev-credit-diagnosis] visible_instances=" + str(report["visible_instances"]))
    print("[brev-credit-diagnosis] next_action=" + str(report["next_action"]))
    if args.fail_on_blocked and not report["paid_prepare_allowed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
