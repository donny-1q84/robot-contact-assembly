#!/usr/bin/env python3
"""Prepare the Brev UI credit review before a paid success-variation run.

This is a read-only bridge between the blocked paid lifecycle preflight and the
manual Brev UI balance check. It prints the current blocker state, the Brev org
dashboard URL to review, and the exact follow-up commands for previewing and
writing fresh credit evidence and rerunning the paid lifecycle preflight.

By default it does not open a browser, write credit evidence, arm the local env,
create a paid instance, run remote code, start Isaac, or copy artifacts. Passing
--open-dashboard only opens the Brev org dashboard URL for manual review.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_brev_credit_evidence as credit_gate  # noqa: E402
import check_success_variation_paid_lifecycle_preflight as paid_preflight  # noqa: E402
import read_brev_credit_balance as api_credit_gate  # noqa: E402


DEFAULT_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_RUN_PACKET = REPO_ROOT / "artifacts" / "analysis" / "success_variation_run_packet_2026-06-25.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "brev_credit_review_packet.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "brev_credit_review_packet.md"
BREV_ORG_DASHBOARD_URL = f"https://brev.nvidia.com/org/{credit_gate.EXPECTED_ORG_ID}/environments"


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


def _command_text(command: list[str]) -> str:
    return " ".join(command)


def _nonnegative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be numeric, got {value!r}") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError(f"must be non-negative, got {value!r}")
    return parsed


def _status_from_preflight(preflight: dict[str, Any], api_credit: dict[str, Any] | None = None) -> str:
    if isinstance(api_credit, dict) and api_credit.get("status") == "BLOCKED":
        return "NEEDS_BREV_CREDIT_TOPUP"
    if preflight.get("status") == "READY_FOR_SINGLE_PAID_LIFECYCLE":
        return "READY_FOR_PAID_LIFECYCLE"
    credit = preflight.get("credit_evidence") if isinstance(preflight.get("credit_evidence"), dict) else {}
    credit_status = credit.get("status")
    if isinstance(api_credit, dict) and api_credit.get("status") == "PASS" and credit_status != "PASS":
        return "NEEDS_FRESH_BREV_CREDIT_EVIDENCE_WRITE"
    if credit_status != "PASS":
        return "NEEDS_BREV_UI_CREDIT_EVIDENCE"
    return str(preflight.get("status") or "BLOCKED")


def _load_api_credit_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Brev API credit output must be a JSON object")
    return payload


def _api_credit_report(
    *,
    required_budget_eur: float,
    timeout_seconds: int,
    skip_api_credit: bool,
    api_credit_output: Path | None,
) -> dict[str, Any]:
    if skip_api_credit:
        return {
            "check_name": "brev_api_credit_balance",
            "status": "SKIPPED",
            "next_action": "manual_brev_ui_balance_review",
            "side_effects": {
                "reads_brev_api": False,
                "writes_credit_evidence": False,
                "creates_paid_instance": False,
                "runs_remote_code": False,
            },
        }
    if api_credit_output is not None:
        try:
            return _load_api_credit_report(_resolve(api_credit_output))
        except Exception as exc:
            return {
                "check_name": "brev_api_credit_balance",
                "status": "UNAVAILABLE",
                "failures": [f"saved Brev API credit output is unreadable: {exc}"],
                "next_action": "fall_back_to_current_brev_ui_balance_review",
            }
    try:
        return api_credit_gate.build_report(
            credentials_path=api_credit_gate.DEFAULT_CREDENTIALS,
            brev_bin=api_credit_gate.DEFAULT_BREV_BIN,
            api_base=api_credit_gate.DEFAULT_API_BASE,
            organization_id=credit_gate.EXPECTED_ORG_ID,
            required_budget_eur=required_budget_eur,
            timeout_seconds=max(1, timeout_seconds),
        )
    except Exception as exc:
        return {
            "check_name": "brev_api_credit_balance",
            "status": "UNAVAILABLE",
            "failures": [f"Brev API credit check failed unexpectedly: {exc}"],
            "next_action": "fall_back_to_current_brev_ui_balance_review",
        }


def _credit_consistency(
    *,
    balance_preview: dict[str, Any],
    api_credit: dict[str, Any],
    credit_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Compare the manually read UI balance with the authoritative API gate."""

    ui_status = str(balance_preview.get("status") or "UNKNOWN")
    api_status = str(api_credit.get("status") or "UNKNOWN")
    ui_covers_budget = balance_preview.get("covers_budget")
    budget = balance_preview.get("budget_eur")
    api_balance = api_credit.get("balance_usd")
    api_blocks = api_credit.get("blockers") if isinstance(api_credit.get("blockers"), list) else []
    api_failures = api_credit.get("failures") if isinstance(api_credit.get("failures"), list) else []
    evidence_status = str(credit_evidence.get("status") or "UNKNOWN")
    evidence_balance = credit_evidence.get("balance_eur")

    if ui_status == "NOT_PROVIDED":
        if api_status == "PASS" and evidence_status == "PASS":
            status = "LOCAL_EVIDENCE_API_CONSISTENT_PASS"
            paid_prepare_allowed = True
            next_action = "rerun_paid_preflight_or_single_paid_lifecycle"
            message = "No new UI balance was provided, but fresh local credit evidence and the Brev API credit gate both pass."
        else:
            status = "NO_UI_BALANCE_PROVIDED"
            paid_prepare_allowed = False
            next_action = "read_current_brev_ui_balance_and_rerun_review"
            message = "No current Brev UI balance was provided for comparison."
    elif ui_covers_budget is False:
        status = "UI_BALANCE_BELOW_BUDGET"
        paid_prepare_allowed = False
        next_action = "add_brev_credits_before_paid_run"
        message = "The provided Brev UI balance does not cover the fixed run budget."
    elif api_status == "PASS":
        status = "CONSISTENT_PASS"
        paid_prepare_allowed = True
        next_action = "write_fresh_credit_evidence_and_rerun_paid_preflight"
        message = "The provided UI balance covers the budget and the Brev API credit gate passes."
    elif api_status == "BLOCKED":
        status = "UI_API_MISMATCH_API_BLOCKED"
        paid_prepare_allowed = False
        next_action = "confirm_credits_were_added_to_this_brev_org_then_rerun_api_credit_check"
        message = (
            "The provided UI balance covers the budget, but the Brev API still reports insufficient "
            "credits for this organization. Do not write credit evidence or arm paid prep until the API gate passes."
        )
    elif api_status in {"UNAVAILABLE", "SKIPPED"}:
        status = f"API_{api_status}_MANUAL_UI_REVIEW_REQUIRED"
        paid_prepare_allowed = False
        next_action = "restore_brev_api_credit_check_or_complete_manual_review_before_paid_run"
        message = (
            "A UI balance was provided, but the Brev API credit check is not authoritative. "
            "Keep paid prep blocked unless the API gate is restored or a manual review is explicitly accepted."
        )
    else:
        status = "UNKNOWN_API_CREDIT_STATE"
        paid_prepare_allowed = False
        next_action = "debug_brev_credit_gate_before_paid_run"
        message = "The Brev API credit status is not recognized by the review helper."

    return {
        "status": status,
        "paid_prepare_allowed": paid_prepare_allowed,
        "ui_balance_eur": balance_preview.get("balance_eur"),
        "ui_covers_budget": ui_covers_budget,
        "api_status": api_status,
        "api_balance_usd": api_balance,
        "local_credit_evidence_status": evidence_status,
        "local_credit_evidence_balance_eur": evidence_balance,
        "budget_eur": budget,
        "mismatch": status == "UI_API_MISMATCH_API_BLOCKED",
        "api_blockers": api_blocks,
        "api_failures": api_failures,
        "next_action": next_action,
        "message": message,
    }


def build_packet(
    *,
    config_path: Path,
    manifest_path: Path,
    run_packet_path: Path,
    command_timeout_seconds: int,
    brev_safety_output: Path | None,
    source_status_output: Path | None,
    open_requested: bool,
    balance_eur: float | None,
    skip_api_credit: bool = False,
    api_credit_output: Path | None = None,
) -> dict[str, Any]:
    preflight = paid_preflight.build_report(
        config_path=config_path,
        manifest_path=manifest_path,
        run_packet_path=run_packet_path,
        command_timeout_seconds=command_timeout_seconds,
        brev_safety_output=brev_safety_output,
        source_status_output=source_status_output,
        api_credit_output=api_credit_output,
    )
    budget = float(preflight.get("budget_eur") or 6.0)
    api_credit = _api_credit_report(
        required_budget_eur=budget,
        timeout_seconds=min(command_timeout_seconds, 15),
        skip_api_credit=skip_api_credit,
        api_credit_output=api_credit_output,
    )
    max_age = int(preflight.get("credit_max_age_minutes") or credit_gate.DEFAULT_MAX_AGE_MINUTES)
    credit_path = str(preflight.get("credit_evidence_path") or "configs/brev_credit_verification.local.json")
    balance_arg = f"{balance_eur:.2f}" if balance_eur is not None else "<current-brev-ui-balance>"
    balance_preview = {
        "status": "NOT_PROVIDED" if balance_eur is None else ("PASS" if balance_eur + 1e-9 >= budget else "BLOCKED"),
        "balance_eur": round(balance_eur, 2) if balance_eur is not None else None,
        "budget_eur": budget,
        "covers_budget": None if balance_eur is None else balance_eur + 1e-9 >= budget,
    }
    credit_evidence = (
        preflight.get("credit_evidence")
        if isinstance(preflight.get("credit_evidence"), dict)
        else {}
    )
    credit_consistency = _credit_consistency(
        balance_preview=balance_preview,
        api_credit=api_credit,
        credit_evidence=credit_evidence,
    )
    paid_unblock_plan = (
        preflight.get("unblock_plan")
        if isinstance(preflight.get("unblock_plan"), dict)
        else {}
    )
    paid_blocked_subchecks = (
        preflight.get("blocked_subchecks")
        if isinstance(preflight.get("blocked_subchecks"), dict)
        else {}
    )
    write_credit_command = [
        "python3",
        "scripts/write_brev_credit_evidence.py",
        "--balance-eur",
        balance_arg,
        "--budget-eur",
        f"{budget:.2f}",
        "--output",
        credit_path,
        "--max-age-minutes",
        str(max_age),
        "--force",
    ]
    preview_credit_command = [*write_credit_command, "--dry-run"]
    rerun_preflight_command = [
        "python3",
        "scripts/check_success_variation_paid_lifecycle_preflight.py",
        "--no-output",
    ]
    lifecycle_command = [
        "python3",
        "scripts/run_success_variation_paid_lifecycle.py",
        "--balance-eur",
        balance_arg,
        "--run",
        "--i-understand-this-can-create-paid-instance",
    ]
    prepare_paid_batch_command = [
        "python3",
        "scripts/prepare_success_variation_paid_batch.py",
        "--balance-eur",
        balance_arg,
        "--budget-eur",
        f"{budget:.2f}",
        "--force-credit",
        "--i-understand-this-arms-paid-run",
    ]
    preview_prepare_paid_batch_command = [*prepare_paid_batch_command, "--dry-run"]
    return {
        "packet_name": "brev_credit_review_packet",
        "status": _status_from_preflight(preflight, api_credit),
        "organization_name": credit_gate.EXPECTED_ORG_NAME,
        "organization_id": credit_gate.EXPECTED_ORG_ID,
        "dashboard_url": BREV_ORG_DASHBOARD_URL,
        "open_dashboard_requested": open_requested,
        "credit_evidence_path": credit_path,
        "budget_eur": budget,
        "balance_eur_for_preview": round(balance_eur, 2) if balance_eur is not None else None,
        "balance_placeholder_used": balance_eur is None,
        "balance_preview": balance_preview,
        "api_credit_balance": api_credit,
        "credit_consistency": credit_consistency,
        "credit_max_age_minutes": max_age,
        "paid_lifecycle_preflight": preflight,
        "paid_lifecycle_unblock_plan": paid_unblock_plan,
        "paid_lifecycle_blocked_subchecks": paid_blocked_subchecks,
        "next_commands": {
            "preview_credit_evidence": preview_credit_command,
            "write_credit_evidence": write_credit_command,
            "preview_prepare_paid_batch": preview_prepare_paid_batch_command,
            "prepare_paid_batch": prepare_paid_batch_command,
            "rerun_paid_lifecycle_preflight": rerun_preflight_command,
            "run_paid_lifecycle": lifecycle_command,
        },
        "instructions": [
            "Log in to Brev/NVIDIA in the browser if required.",
            "Prefer the read-only api_credit_balance result when it is PASS or BLOCKED; fall back to the UI only if the API check is SKIPPED or UNAVAILABLE.",
            "Open the organization dashboard and read the current organization credit balance from the Brev UI.",
            "If credit_consistency.status is UI_API_MISMATCH_API_BLOCKED, confirm the top-up landed in this exact organization before writing evidence or arming paid prep.",
            "Use the current UI balance in the preview_credit_evidence command first; do not reuse an old email or memory value.",
            "Pass --balance-eur to this review helper after reading the UI if you want concrete commands instead of placeholders.",
            "If the preview is correct, use the same current UI balance in the write_credit_evidence or preview_prepare_paid_batch command.",
            "Prefer the prepare_paid_batch command to write credit evidence, arm the local env, refresh the run packet, and rerun the aggregate preflight in one fail-closed step.",
            "Rerun the paid lifecycle preflight before any paid create.",
            "Use paid_lifecycle_unblock_plan as the ordered sequence; do not skip directly to the paid lifecycle command while it is BLOCKED.",
        ],
        "side_effects": {
            "opens_dashboard": open_requested,
            "writes_credit_evidence": False,
            "writes_local_env": False,
            "creates_paid_instance": False,
            "runs_remote_code": False,
            "starts_isaac": False,
            "copies_artifacts": False,
        },
        "not_claims": [
            "not fresh credit evidence",
            "not a paid run",
            "not an armed local env",
            "not success-variation result evidence",
        ],
    }


def _render_markdown(packet: dict[str, Any]) -> str:
    commands = packet["next_commands"]
    lines = [
        "# Brev Credit Review Packet",
        "",
        f"- status: {packet['status']}",
        f"- organization: {packet['organization_name']} / {packet['organization_id']}",
        f"- dashboard_url: {packet['dashboard_url']}",
        f"- credit_evidence_path: {packet['credit_evidence_path']}",
        f"- budget_eur: {packet['budget_eur']:.2f}",
        f"- balance_eur_for_preview: {packet['balance_eur_for_preview']}",
        f"- balance_placeholder_used: {packet['balance_placeholder_used']}",
        "",
        "## Brev API Credit Balance",
        "",
    ]
    api_credit = (
        packet.get("api_credit_balance")
        if isinstance(packet.get("api_credit_balance"), dict)
        else {}
    )
    credit_consistency = (
        packet.get("credit_consistency")
        if isinstance(packet.get("credit_consistency"), dict)
        else {}
    )
    lines.extend(
        [
            f"- status: {api_credit.get('status')}",
            f"- balance_usd: {api_credit.get('balance_usd')}",
            f"- required_budget_eur: {api_credit.get('required_budget_eur')}",
            f"- next_action: {api_credit.get('next_action')}",
            "",
            "## Credit Consistency",
            "",
            f"- status: {credit_consistency.get('status')}",
            f"- paid_prepare_allowed: {credit_consistency.get('paid_prepare_allowed')}",
            f"- ui_balance_eur: {credit_consistency.get('ui_balance_eur')}",
            f"- api_balance_usd: {credit_consistency.get('api_balance_usd')}",
            f"- local_credit_evidence_status: {credit_consistency.get('local_credit_evidence_status')}",
            f"- local_credit_evidence_balance_eur: {credit_consistency.get('local_credit_evidence_balance_eur')}",
            f"- mismatch: {credit_consistency.get('mismatch')}",
            f"- next_action: {credit_consistency.get('next_action')}",
            f"- message: {credit_consistency.get('message')}",
        ]
    )
    api_blockers = api_credit.get("blockers") if isinstance(api_credit.get("blockers"), list) else []
    if api_blockers:
        lines.extend(["", "API blockers:"])
        lines.extend(f"- {item}" for item in api_blockers)
    api_failures = api_credit.get("failures") if isinstance(api_credit.get("failures"), list) else []
    if api_failures:
        lines.extend(["", "API failures:"])
        lines.extend(f"- {item}" for item in api_failures)
    lines.extend(
        [
            "",
        "## Instructions",
        "",
        ]
    )
    lines.extend(f"- {item}" for item in packet["instructions"])
    blocked_subchecks = (
        packet.get("paid_lifecycle_blocked_subchecks")
        if isinstance(packet.get("paid_lifecycle_blocked_subchecks"), dict)
        else {}
    )
    if blocked_subchecks:
        lines.extend(["", "## Paid Lifecycle Blocked Subchecks", ""])
        for name, values in blocked_subchecks.items():
            values = values if isinstance(values, list) else []
            lines.append(f"- {name}: {len(values)}")
            lines.extend(f"  - {item}" for item in values)
    unblock_plan = (
        packet.get("paid_lifecycle_unblock_plan")
        if isinstance(packet.get("paid_lifecycle_unblock_plan"), dict)
        else {}
    )
    if unblock_plan:
        lines.extend(
            [
                "",
                "## Paid Lifecycle Unblock Plan",
                "",
                f"- status: {unblock_plan.get('status')}",
                f"- requires_current_brev_ui_balance: {unblock_plan.get('requires_current_brev_ui_balance')}",
            ]
        )
        ordered_steps = (
            unblock_plan.get("ordered_steps")
            if isinstance(unblock_plan.get("ordered_steps"), list)
            else []
        )
        lines.extend(f"- {item}" for item in ordered_steps)
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```bash",
            _command_text(commands["preview_credit_evidence"]),
            _command_text(commands["write_credit_evidence"]),
            _command_text(commands["preview_prepare_paid_batch"]),
            _command_text(commands["prepare_paid_batch"]),
            _command_text(commands["rerun_paid_lifecycle_preflight"]),
            _command_text(commands["run_paid_lifecycle"]),
            "```",
            "",
            "## Side Effects",
            "",
        ]
    )
    for key, value in packet["side_effects"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Not Claims", ""])
    lines.extend(f"- {item}" for item in packet["not_claims"])
    return "\n".join(lines) + "\n"


def _open_dashboard(url: str) -> int:
    open_bin = os.environ.get("RCA_OPEN_BIN", "open")
    completed = subprocess.run([open_bin, url], cwd=REPO_ROOT, check=False)
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--run-packet", type=Path, default=DEFAULT_RUN_PACKET)
    parser.add_argument("--command-timeout-seconds", type=int, default=120)
    parser.add_argument("--brev-safety-output", type=Path)
    parser.add_argument("--source-status-output", type=Path)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--balance-eur", type=_nonnegative_float)
    parser.add_argument("--skip-api-credit", action="store_true")
    parser.add_argument("--api-credit-output", type=Path)
    parser.add_argument("--open-dashboard", action="store_true")
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    if args.command_timeout_seconds <= 0:
        print("[brev-credit-review] FAIL")
        print("- --command-timeout-seconds must be positive")
        return 1

    config_path = _resolve(args.config)
    manifest_path = _resolve(args.manifest)
    run_packet_path = _resolve(args.run_packet)
    safety_output = _resolve(args.brev_safety_output) if args.brev_safety_output is not None else None
    source_status_output = _resolve(args.source_status_output) if args.source_status_output is not None else None
    packet = build_packet(
        config_path=config_path,
        manifest_path=manifest_path,
        run_packet_path=run_packet_path,
        command_timeout_seconds=args.command_timeout_seconds,
        brev_safety_output=safety_output,
        source_status_output=source_status_output,
        open_requested=args.open_dashboard,
        balance_eur=args.balance_eur,
        skip_api_credit=args.skip_api_credit,
        api_credit_output=args.api_credit_output,
    )

    if args.open_dashboard:
        open_status = _open_dashboard(packet["dashboard_url"])
        packet["open_dashboard_exit_code"] = open_status
        if open_status != 0:
            packet["status"] = "FAIL"
            packet.setdefault("failures", []).append("could not open Brev organization dashboard")

    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[brev-credit-review] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(packet), encoding="utf-8")
        print(f"[brev-credit-review] wrote Markdown: {_rel(output_md)}")

    print("[brev-credit-review] facts=" + json.dumps(packet, indent=2, sort_keys=True))
    print("[brev-credit-review] status=" + packet["status"])
    print("[brev-credit-review] dashboard_url=" + packet["dashboard_url"])
    api_credit = packet.get("api_credit_balance") if isinstance(packet.get("api_credit_balance"), dict) else {}
    print("[brev-credit-review] api_credit_status=" + str(api_credit.get("status")))
    print("[brev-credit-review] api_credit_balance_usd=" + str(api_credit.get("balance_usd")))
    credit_consistency = packet.get("credit_consistency") if isinstance(packet.get("credit_consistency"), dict) else {}
    print("[brev-credit-review] credit_consistency_status=" + str(credit_consistency.get("status")))
    print("[brev-credit-review] paid_prepare_allowed=" + str(credit_consistency.get("paid_prepare_allowed")))
    print("[brev-credit-review] balance_preview_status=" + str(packet["balance_preview"]["status"]))
    print("[brev-credit-review] preview_credit_evidence=" + _command_text(packet["next_commands"]["preview_credit_evidence"]))
    print("[brev-credit-review] write_credit_evidence=" + _command_text(packet["next_commands"]["write_credit_evidence"]))
    print("[brev-credit-review] preview_prepare_paid_batch=" + _command_text(packet["next_commands"]["preview_prepare_paid_batch"]))
    if packet["status"] == "FAIL":
        return 1
    if packet["status"] != "READY_FOR_PAID_LIFECYCLE" and args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
