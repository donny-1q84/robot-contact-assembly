#!/usr/bin/env python3
"""Write a reviewed run packet for the success-variation paid batch.

This report is intentionally local and non-mutating. It runs the read-only
success-variation readiness gate, records the current facts/blockers, and writes
a compact JSON/Markdown packet with the exact check/run/finalize commands.

It does not create, delete, copy to, or execute on Brev instances. It also does
not write the ignored local env file; the packet only includes a template and
checklist for a deliberate one-run local env.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
DEFAULT_EXAMPLE_CONFIG = REPO_ROOT / "configs" / "success_variation_batch_run.env.example"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "success_variation_run_packet_2026-06-25.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "success_variation_run_packet_2026-06-25.md"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _resolve_repo_path(path: Path) -> Path:
    path = path.expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _read_config(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError(f"invalid config line {line_no}: {raw_line}")
        key, value = line.split("=", 1)
        if not (key.startswith("RCA_") or key == "BREV_BIN"):
            raise RuntimeError(f"disallowed config key on line {line_no}: {key}")
        values[key] = value
    return values


def _default_config_path() -> Path:
    if DEFAULT_LOCAL_CONFIG.is_file():
        return DEFAULT_LOCAL_CONFIG
    return DEFAULT_EXAMPLE_CONFIG


def _parse_readiness_output(text: str, *, exit_code: int | None) -> dict[str, Any]:
    marker = "[success-variation-readiness] facts="
    marker_index = text.find(marker)
    facts: dict[str, Any] = {}
    if marker_index >= 0:
        start = marker_index + len(marker)
        decoder = json.JSONDecoder()
        facts_value, _ = decoder.raw_decode(text[start:])
        if isinstance(facts_value, dict):
            facts = facts_value

    status = "UNKNOWN"
    blockers: list[str] = []
    collecting = False
    for line in text.splitlines():
        if line == "[success-variation-readiness] READY":
            status = "READY"
            collecting = False
        elif line == "[success-variation-readiness] BLOCKED":
            status = "BLOCKED"
            collecting = True
        elif collecting and line.startswith("- "):
            blockers.append(line[2:])
        elif collecting and line.startswith("["):
            collecting = False

    return {
        "status": status,
        "exit_code": exit_code,
        "facts": facts,
        "blockers": blockers,
        "raw_tail": text[-4000:],
    }


def _run_readiness(config: dict[str, str], manifest: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(config)
    result = subprocess.run(
        ["python3", "scripts/check_success_variation_batch_readiness.py", str(manifest)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=180,
    )
    return _parse_readiness_output(result.stdout, exit_code=result.returncode)


def _commands(config_path: Path, manifest: Path) -> dict[str, str]:
    config_ref = _rel(config_path)
    manifest_ref = _rel(manifest)
    return {
        "check_only": f"scripts/run_success_variation_batch_from_config.sh {config_ref} --check-only",
        "pre_batch_audit": (
            "python3 scripts/audit_success_variation_assumptions.py "
            f"{manifest_ref} --phase pre-batch "
            "--run-packet artifacts/analysis/success_variation_run_packet_2026-06-25.json "
            "--fail-on-blocked"
        ),
        "run": f"scripts/run_success_variation_batch_from_config.sh {config_ref} --run",
        "finalize": f"scripts/finalize_success_variation_batch.sh {manifest_ref}",
        "prepare_fail_closed_local_env": (
            "python3 scripts/prepare_success_variation_local_env.py "
            "--packet artifacts/analysis/success_variation_run_packet_2026-06-25.json"
        ),
        "write_credit_evidence_after_ui_check": (
            "python3 scripts/write_brev_credit_evidence.py "
            "--balance-eur <current-brev-ui-balance> --budget-eur 6.00 --force"
        ),
        "arm_paid_local_env_after_evidence": (
            "python3 scripts/arm_success_variation_paid_env.py "
            "--i-understand-this-arms-paid-run"
        ),
        "disarm_paid_local_env": "python3 scripts/arm_success_variation_paid_env.py --disarm",
        "safety": "./scripts/brev_paid_safety_status.sh",
    }


def _local_env_template(config: dict[str, str]) -> str:
    merged = {
        "RCA_SUCCESS_VARIATION_MANIFEST": "artifacts/manifests/success_trace_variations_2026-06-25.json",
        "RCA_SUCCESS_VARIATION_ENV_NAME": "rca-success-variation-batch-vm",
        "RCA_SUCCESS_VARIATION_REMOTE_ROOT": "/home/ubuntu/projects/robot-contact-assembly",
        "RCA_SUCCESS_VARIATION_COMPOSE_ROOT": "/home/ubuntu/isaac-compose",
        "RCA_SUCCESS_VARIATION_TASK": "RCA-PegInHole-Franka-JointPos-Contact-Play-v0",
        "RCA_SUCCESS_VARIATION_STEPS": "220",
        "RCA_SUCCESS_VARIATION_SEED": "42",
        "RCA_SUCCESS_VARIATION_INSTANCE_TYPE": "g6e.xlarge",
        "RCA_SUCCESS_VARIATION_MIN_DISK": "500",
        "RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES": "75",
        "RCA_SUCCESS_VARIATION_TRACE_TIMEOUT_SECONDS": "3600",
        "RCA_SUCCESS_VARIATION_TRACE_TIMEOUT_KILL_SECONDS": "60",
        "RCA_SUCCESS_VARIATION_AUTO_DISARM": "1",
        "RCA_PAID_BUDGET_EUR": "6.00",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR": "4.50",
        "RCA_BREV_CREDIT_EVIDENCE_JSON": "configs/brev_credit_verification.local.json",
        "RCA_BREV_CREDIT_EVIDENCE_MAX_AGE_MINUTES": "60",
        "RCA_PAID_ARMED_AT_UTC": "",
        "RCA_PAID_ARMING_MAX_AGE_MINUTES": "15",
        "RCA_ALLOW_PAID_BREV_CREATE": "0",
        "RCA_BREV_CREDITS_VERIFIED": "0",
        "RCA_ACK_BREV_LIFECYCLE_RISK": "0",
    }
    merged.update(config)
    merged["RCA_ALLOW_PAID_BREV_CREATE"] = "0"
    merged["RCA_BREV_CREDITS_VERIFIED"] = "0"
    merged["RCA_ACK_BREV_LIFECYCLE_RISK"] = "0"
    lines = [
        "# Copy into configs/success_variation_batch_run.local.env only for a single reviewed paid run.",
        "# Keep the three acknowledgement markers at 0 until the current Brev UI balance,",
        "# budget, lifecycle risk, and deletion path have just been checked.",
    ]
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
        "RCA_SUCCESS_VARIATION_AUTO_DISARM",
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
    lines.extend(f"{key}={merged[key]}" for key in ordered)
    return "\n".join(lines) + "\n"


def _build_packet(
    *,
    config_path: Path,
    manifest: Path,
    config: dict[str, str],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    facts = readiness.get("facts") if isinstance(readiness.get("facts"), dict) else {}
    return {
        "packet_name": "success_variation_paid_batch_run_packet",
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_path": _rel(config_path),
        "manifest": _rel(manifest),
        "readiness": readiness,
        "estimated_cost": {
            "budget_eur": facts.get("budget_eur"),
            "estimated_eur_per_hour": facts.get("estimated_eur_per_hour"),
            "estimated_max_cost_eur": facts.get("estimated_max_cost_eur"),
            "ttl_minutes": facts.get("ttl_minutes"),
            "live_instance_price": facts.get("instance_price"),
        },
        "commands": _commands(config_path, manifest),
        "one_run_local_env_template": _local_env_template(config),
        "safety_notes": [
            "This packet is read-only and does not create or delete Brev instances.",
            "Do not set RCA_ALLOW_PAID_BREV_CREATE=1 until running one deliberate paid batch.",
            "Generate a passing git-ignored Brev UI credit evidence JSON before setting RCA_BREV_CREDITS_VERIFIED=1.",
            "Paid local-env arming has an expiry timestamp; disarm stale acknowledgements before rechecking.",
            "Do not set RCA_ACK_BREV_LIFECYCLE_RISK=1 unless accepting one retry while lifecycle hold is active.",
            "After the run, use the finalizer before dataset, residual policy, VLM, ROS, or sim-to-real claims.",
        ],
    }


def _render_markdown(packet: dict[str, Any]) -> str:
    readiness = packet["readiness"]
    facts = readiness.get("facts") if isinstance(readiness.get("facts"), dict) else {}
    credit_evidence = facts.get("credit_evidence") if isinstance(facts.get("credit_evidence"), dict) else {}
    rows = [
        "# Success Variation Paid Batch Run Packet",
        "",
        f"- status: {readiness.get('status')}",
        f"- config: {packet['config_path']}",
        f"- manifest: {packet['manifest']}",
        f"- estimated_max_cost_eur: {packet['estimated_cost'].get('estimated_max_cost_eur')}",
        f"- ttl_minutes: {packet['estimated_cost'].get('ttl_minutes')}",
        f"- brev_safety_status: {facts.get('brev_safety_status')}",
        f"- phase2_contact_gate: {facts.get('phase2_contact_gate')}",
        f"- credit_evidence_status: {credit_evidence.get('status')}",
        "",
        "## Current Blockers",
        "",
    ]
    blockers = readiness.get("blockers") or []
    if blockers:
        rows.extend(f"- {blocker}" for blocker in blockers)
    else:
        rows.append("- none")

    rows.extend(["", "## Commands", ""])
    for key, value in packet["commands"].items():
        rows.append(f"- {key}: `{value}`")

    rows.extend(["", "## One-Run Local Env Template", "", "```bash"])
    rows.append(packet["one_run_local_env_template"].rstrip())
    rows.extend(["```", "", "## Safety Notes", ""])
    rows.extend(f"- {note}" for note in packet["safety_notes"])
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=_default_config_path())
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--readiness-output", type=Path, help="Parse saved readiness output instead of running the gate.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    config_path = _resolve_repo_path(args.config)
    manifest = _resolve_repo_path(args.manifest)
    config = _read_config(config_path)
    if args.readiness_output is not None:
        readiness_text = _resolve_repo_path(args.readiness_output).read_text(encoding="utf-8")
        readiness = _parse_readiness_output(readiness_text, exit_code=None)
    else:
        readiness = _run_readiness(config, manifest)

    packet = _build_packet(
        config_path=config_path,
        manifest=manifest,
        config=config,
        readiness=readiness,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(packet, indent=2, sort_keys=True), encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(_render_markdown(packet), encoding="utf-8")

    print(f"[success-variation-run-packet] wrote JSON: {_rel(args.output_json)}")
    print(f"[success-variation-run-packet] wrote Markdown: {_rel(args.output_md)}")
    print(f"[success-variation-run-packet] status={readiness.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
