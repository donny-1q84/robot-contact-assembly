#!/usr/bin/env python3
"""Prepare a Brev credit blocker support packet.

This helper is for the UI/API credit mismatch that blocks the fixed-budget
success-variation paid batch. It is read-only with respect to Brev: it may read
the Brev CLI/API through the diagnosis helper, but it does not open a browser,
write credit evidence, arm local env state, create paid instances, run remote
code, start Isaac, copy artifacts, or delete instances.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_brev_credit_evidence as credit_gate  # noqa: E402
import diagnose_brev_credit_blocker as diagnosis_gate  # noqa: E402


DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "brev_credit_support_packet.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "brev_credit_support_packet.md"


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


def _balance_arg(balance_eur: float | None) -> str:
    if balance_eur is None:
        return "<current-brev-ui-balance>"
    return f"{balance_eur:.2f}"


def _command_text(command: list[str]) -> str:
    return " ".join(command)


def _side_effects(*, writes_support_packet: bool) -> dict[str, bool]:
    return {
        "reads_brev_cli": True,
        "reads_brev_api": True,
        "opens_dashboard": False,
        "writes_support_packet": writes_support_packet,
        "writes_credit_evidence": False,
        "writes_local_env": False,
        "creates_paid_instance": False,
        "runs_remote_code": False,
        "starts_isaac": False,
        "copies_artifacts": False,
        "deletes_instances": False,
        "prints_token": False,
    }


def _status(diagnosis: dict[str, Any]) -> str:
    if diagnosis.get("paid_prepare_allowed") is True:
        return "NOT_BLOCKED_API_CREDIT_READY"
    consistency = diagnosis.get("credit_consistency")
    consistency_status = consistency.get("status") if isinstance(consistency, dict) else None
    if consistency_status == "UI_API_MISMATCH_API_BLOCKED":
        return "READY_FOR_SUPPORT_REVIEW"
    if consistency_status == "NO_UI_BALANCE_PROVIDED":
        return "NEEDS_CURRENT_UI_BALANCE"
    return "READY_FOR_SUPPORT_REVIEW"


def _support_message(packet: dict[str, Any]) -> str:
    diagnosis = packet["diagnosis"]
    expected = diagnosis.get("expected_organization") if isinstance(diagnosis.get("expected_organization"), dict) else {}
    active = diagnosis.get("active_organization") if isinstance(diagnosis.get("active_organization"), dict) else {}
    api_credit = diagnosis.get("api_credit_balance") if isinstance(diagnosis.get("api_credit_balance"), dict) else {}
    consistency = diagnosis.get("credit_consistency") if isinstance(diagnosis.get("credit_consistency"), dict) else {}
    balance_preview = diagnosis.get("balance_preview") if isinstance(diagnosis.get("balance_preview"), dict) else {}
    ui_balance = balance_preview.get("balance_eur")
    ui_line = (
        "I have not included a current UI balance in this packet."
        if ui_balance is None
        else f"The Brev UI balance I reviewed for this org is {ui_balance:.2f} EUR."
    )
    return "\n".join(
        [
            "Hi Brev Support,",
            "",
            "I am blocked on a credit mismatch for the robot-contact-assembly project.",
            ui_line,
            f"Expected org: {expected.get('name')} / {expected.get('id')}",
            f"Active CLI org: {active.get('name')} / {active.get('id')}",
            f"Brev API credit status: {api_credit.get('status')}",
            f"Brev API balance_usd: {api_credit.get('balance_usd')}",
            f"Credit consistency status: {consistency.get('status')}",
            f"Visible instances: {diagnosis.get('visible_instances')}",
            f"Workspaces null: {diagnosis.get('workspaces_null')}",
            "",
            "Could you please confirm whether credits were applied to this organization and why the org credits API still blocks this paid run?",
            "",
            "Best regards,",
            "Shenghan Gao",
        ]
    )


def _commands(balance_eur: float | None) -> dict[str, list[str]]:
    balance_arg = _balance_arg(balance_eur)
    return {
        "status_report_with_ui_balance": [
            "python3",
            "scripts/project_status_report.py",
            "--balance-eur",
            balance_arg,
            "--fail-on-blocked",
        ],
        "diagnose_credit_with_ui_balance": [
            "python3",
            "scripts/diagnose_brev_credit_blocker.py",
            "--balance-eur",
            balance_arg,
            "--no-output",
        ],
        "read_api_credit": [
            "python3",
            "scripts/read_brev_credit_balance.py",
            "--required-budget-eur",
            "6.00",
        ],
        "prepare_support_packet": [
            "python3",
            "scripts/prepare_brev_credit_support_packet.py",
            "--balance-eur",
            balance_arg,
        ],
    }


def build_packet(
    *,
    balance_eur: float | None,
    api_credit_output: Path | None,
    command_timeout_seconds: int,
) -> dict[str, Any]:
    diagnosis = diagnosis_gate.build_report(
        config_path=diagnosis_gate.DEFAULT_CONFIG,
        manifest_path=diagnosis_gate.DEFAULT_MANIFEST,
        run_packet_path=diagnosis_gate.DEFAULT_RUN_PACKET,
        balance_eur=balance_eur,
        api_credit_output=api_credit_output,
        command_timeout_seconds=max(1, command_timeout_seconds),
    )
    commands = _commands(balance_eur)
    packet: dict[str, Any] = {
        "packet_name": "brev_credit_blocker_support_packet",
        "status": _status(diagnosis),
        "dashboard_url": diagnosis.get("dashboard_url"),
        "expected_organization": diagnosis.get("expected_organization"),
        "active_organization": diagnosis.get("active_organization"),
        "api_credit_balance": diagnosis.get("api_credit_balance"),
        "balance_preview": diagnosis.get("balance_preview"),
        "credit_consistency": diagnosis.get("credit_consistency"),
        "paid_prepare_allowed": diagnosis.get("paid_prepare_allowed") is True,
        "visible_instances": diagnosis.get("visible_instances"),
        "workspaces_null": diagnosis.get("workspaces_null"),
        "diagnosis_status": diagnosis.get("status"),
        "diagnosis_next_action": diagnosis.get("next_action"),
        "likely_causes": diagnosis.get("likely_causes"),
        "safe_next_steps": diagnosis.get("safe_next_steps"),
        "next_commands": commands,
        "support_message": "",
        "side_effects": _side_effects(writes_support_packet=False),
        "not_claims": [
            "not fresh credit evidence",
            "not a paid run",
            "not an armed local env",
            "not success-variation result evidence",
            "not approval to bypass a blocked Brev API credit gate",
        ],
        "diagnosis": diagnosis,
    }
    packet["support_message"] = _support_message(packet)
    return packet


def _render_markdown(packet: dict[str, Any]) -> str:
    commands = packet.get("next_commands") if isinstance(packet.get("next_commands"), dict) else {}
    lines = [
        "# Brev Credit Blocker Support Packet",
        "",
        f"- status: {packet['status']}",
        f"- diagnosis_status: {packet['diagnosis_status']}",
        f"- paid_prepare_allowed: {str(packet['paid_prepare_allowed']).lower()}",
        f"- visible_instances: {packet['visible_instances']}",
        f"- workspaces_null: {packet['workspaces_null']}",
        f"- dashboard_url: {packet['dashboard_url']}",
        "",
        "## Credit State",
        "",
        "```json",
        json.dumps(
            {
                "expected_organization": packet["expected_organization"],
                "active_organization": packet["active_organization"],
                "api_credit_balance": packet["api_credit_balance"],
                "balance_preview": packet["balance_preview"],
                "credit_consistency": packet["credit_consistency"],
            },
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
        "## Support Message",
        "",
        "```text",
        packet["support_message"],
        "```",
        "",
        "## Commands",
        "",
        "```bash",
    ]
    lines.extend(_command_text(command) for command in commands.values())
    lines.extend(["```", "", "## Not Claims", ""])
    lines.extend(f"- {item}" for item in packet["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--balance-eur", type=_nonnegative_float)
    parser.add_argument("--api-credit-output", type=Path)
    parser.add_argument("--command-timeout-seconds", type=int, default=60)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    args = parser.parse_args()

    packet = build_packet(
        balance_eur=args.balance_eur,
        api_credit_output=args.api_credit_output,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        packet["side_effects"] = _side_effects(writes_support_packet=True)
        output_json.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[brev-credit-support] wrote JSON: {_rel(output_json)}")

        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(packet), encoding="utf-8")
        print(f"[brev-credit-support] wrote Markdown: {_rel(output_md)}")

    print("[brev-credit-support] facts=" + json.dumps(packet, indent=2, sort_keys=True))
    print("[brev-credit-support] status=" + str(packet["status"]))
    print("[brev-credit-support] paid_prepare_allowed=" + str(packet["paid_prepare_allowed"]))
    print("[brev-credit-support] next_action=" + str(packet["diagnosis_next_action"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
