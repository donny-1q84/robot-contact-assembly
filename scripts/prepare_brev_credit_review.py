#!/usr/bin/env python3
"""Prepare the Brev UI credit review before a paid success-variation run.

This is a read-only bridge between the blocked paid lifecycle preflight and the
manual Brev UI balance check. It prints the current blocker state, the Brev org
dashboard URL to review, and the exact follow-up commands for writing fresh
credit evidence and rerunning the paid lifecycle preflight.

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


DEFAULT_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
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


def _status_from_preflight(preflight: dict[str, Any]) -> str:
    if preflight.get("status") == "READY_FOR_SINGLE_PAID_LIFECYCLE":
        return "READY_FOR_PAID_LIFECYCLE"
    credit = preflight.get("credit_evidence") if isinstance(preflight.get("credit_evidence"), dict) else {}
    credit_status = credit.get("status")
    if credit_status != "PASS":
        return "NEEDS_BREV_UI_CREDIT_EVIDENCE"
    return str(preflight.get("status") or "BLOCKED")


def build_packet(
    *,
    config_path: Path,
    manifest_path: Path,
    command_timeout_seconds: int,
    brev_safety_output: Path | None,
    source_status_output: Path | None,
    open_requested: bool,
) -> dict[str, Any]:
    preflight = paid_preflight.build_report(
        config_path=config_path,
        manifest_path=manifest_path,
        command_timeout_seconds=command_timeout_seconds,
        brev_safety_output=brev_safety_output,
        source_status_output=source_status_output,
    )
    budget = float(preflight.get("budget_eur") or 6.0)
    max_age = int(preflight.get("credit_max_age_minutes") or credit_gate.DEFAULT_MAX_AGE_MINUTES)
    credit_path = str(preflight.get("credit_evidence_path") or "configs/brev_credit_verification.local.json")
    write_credit_command = [
        "python3",
        "scripts/write_brev_credit_evidence.py",
        "--balance-eur",
        "<current-brev-ui-balance>",
        "--budget-eur",
        f"{budget:.2f}",
        "--output",
        credit_path,
        "--max-age-minutes",
        str(max_age),
        "--force",
    ]
    rerun_preflight_command = [
        "python3",
        "scripts/check_success_variation_paid_lifecycle_preflight.py",
        "--no-output",
    ]
    lifecycle_command = [
        "python3",
        "scripts/run_success_variation_paid_lifecycle.py",
        "--balance-eur",
        "<current-brev-ui-balance>",
        "--run",
        "--i-understand-this-can-create-paid-instance",
    ]
    return {
        "packet_name": "brev_credit_review_packet",
        "status": _status_from_preflight(preflight),
        "organization_name": credit_gate.EXPECTED_ORG_NAME,
        "organization_id": credit_gate.EXPECTED_ORG_ID,
        "dashboard_url": BREV_ORG_DASHBOARD_URL,
        "open_dashboard_requested": open_requested,
        "credit_evidence_path": credit_path,
        "budget_eur": budget,
        "credit_max_age_minutes": max_age,
        "paid_lifecycle_preflight": preflight,
        "next_commands": {
            "write_credit_evidence": write_credit_command,
            "rerun_paid_lifecycle_preflight": rerun_preflight_command,
            "run_paid_lifecycle": lifecycle_command,
        },
        "instructions": [
            "Log in to Brev/NVIDIA in the browser if required.",
            "Open the organization dashboard and read the current organization credit balance from the Brev UI.",
            "Use the current UI balance in the write_credit_evidence command; do not reuse an old email or memory value.",
            "Rerun the paid lifecycle preflight before any paid create.",
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
        "",
        "## Instructions",
        "",
    ]
    lines.extend(f"- {item}" for item in packet["instructions"])
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```bash",
            _command_text(commands["write_credit_evidence"]),
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
    parser.add_argument("--command-timeout-seconds", type=int, default=120)
    parser.add_argument("--brev-safety-output", type=Path)
    parser.add_argument("--source-status-output", type=Path)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
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
    safety_output = _resolve(args.brev_safety_output) if args.brev_safety_output is not None else None
    source_status_output = _resolve(args.source_status_output) if args.source_status_output is not None else None
    packet = build_packet(
        config_path=config_path,
        manifest_path=manifest_path,
        command_timeout_seconds=args.command_timeout_seconds,
        brev_safety_output=safety_output,
        source_status_output=source_status_output,
        open_requested=args.open_dashboard,
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
    print("[brev-credit-review] write_credit_evidence=" + _command_text(packet["next_commands"]["write_credit_evidence"]))
    if packet["status"] == "FAIL":
        return 1
    if packet["status"] != "READY_FOR_PAID_LIFECYCLE" and args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
