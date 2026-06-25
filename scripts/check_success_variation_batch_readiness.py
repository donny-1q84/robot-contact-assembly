#!/usr/bin/env python3
"""Read-only readiness gate for the success-variation paid trace batch.

This script does not create, start, stop, delete, copy to, or execute on Brev
instances. It checks the local semantic contract plus the paid-run guard inputs
that must be explicit before the create/run/cleanup wrapper is allowed to
proceed.
"""

from __future__ import annotations

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

import classify_success_variation_results as classifier  # noqa: E402
import check_brev_credit_evidence as credit_gate  # noqa: E402


DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
LIFECYCLE_HOLD_FILE = REPO_ROOT / "docs" / "brev_launchable_lifecycle_hold.md"
DEFAULT_CREDIT_EVIDENCE = REPO_ROOT / "configs" / "brev_credit_verification.local.json"


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root must be an object: {_rel(path)}")
    return payload


def _parse_float_env(name: str, blockers: list[str]) -> float | None:
    value = os.environ.get(name, "").strip()
    if not value:
        blockers.append(f"set {name} to a positive number")
        return None
    try:
        parsed = float(value)
    except ValueError:
        blockers.append(f"{name} must be numeric, got {value!r}")
        return None
    if parsed <= 0:
        blockers.append(f"{name} must be positive, got {value!r}")
        return None
    return parsed


def _parse_positive_int_env(name: str, default: int, blockers: list[str]) -> int | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        blockers.append(f"{name} must be an integer, got {value!r}")
        return None
    if parsed <= 0:
        blockers.append(f"{name} must be positive, got {value!r}")
        return None
    return parsed


def _parse_ttl_minutes(blockers: list[str]) -> int | None:
    candidates = (
        "RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES",
        "RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES",
        "RCA_PAID_MAX_MINUTES",
    )
    for name in candidates:
        value = os.environ.get(name, "").strip()
        if not value:
            continue
        try:
            parsed = int(value)
        except ValueError:
            blockers.append(f"{name} must be an integer minute TTL, got {value!r}")
            return None
        if parsed <= 0:
            blockers.append(f"{name} must be positive, got {value!r}")
            return None
        return parsed
    blockers.append(
        "set an explicit TTL with RCA_SUCCESS_VARIATION_WATCHDOG_MAX_MINUTES, "
        "RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES, or RCA_PAID_MAX_MINUTES"
    )
    return None


def _run(args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def _check_phase2_gate(blockers: list[str], facts: dict[str, Any]) -> None:
    result = _run(["python3", "scripts/check_phase2_contact_gate.py"], timeout=60)
    facts["phase2_contact_gate_exit"] = result.returncode
    if result.returncode == 0:
        facts["phase2_contact_gate"] = "PASS"
    else:
        facts["phase2_contact_gate"] = "BLOCKED"
        facts["phase2_contact_gate_output"] = result.stdout[-2000:]
        blockers.append("Phase 2 contact gate is not PASS; do not run success variations")


def _check_brev_safety(blockers: list[str], facts: dict[str, Any]) -> None:
    try:
        result = _run(["./scripts/brev_paid_safety_status.sh"], timeout=90)
    except subprocess.TimeoutExpired:
        facts["brev_safety_status"] = "timeout"
        blockers.append("brev_paid_safety_status.sh timed out; Brev state is not safe to use")
        return

    facts["brev_safety_exit"] = result.returncode
    facts["brev_safety_output_tail"] = result.stdout[-3000:]
    status = None
    visible = None
    for line in result.stdout.splitlines():
        if line.startswith("[brev-safety] status="):
            status = line.split("=", 1)[1].strip()
        if line.startswith("[brev-safety] visible_instances="):
            visible = line.split("=", 1)[1].strip()
    facts["brev_safety_status"] = status
    facts["brev_visible_instances"] = visible
    if result.returncode != 0 or status != "SAFE_NO_VISIBLE_PAID_INSTANCE":
        blockers.append("Brev safety status must be SAFE_NO_VISIBLE_PAID_INSTANCE before creating the batch VM")


def _check_instance_price(blockers: list[str], facts: dict[str, Any]) -> None:
    instance_type = (
        os.environ.get("RCA_SUCCESS_VARIATION_INSTANCE_TYPE")
        or os.environ.get("RCA_FINAL_CONTACT_INSTANCE_TYPE")
        or "g6e.xlarge"
    ).strip()
    facts["instance_type"] = instance_type
    try:
        result = _run(["/Users/Shenghan/bin/brev", "search", "gpu", "--json"], timeout=60)
    except subprocess.TimeoutExpired:
        facts["instance_price_check"] = "timeout"
        blockers.append("Brev instance price search timed out; current instance availability/price is unknown")
        return

    facts["instance_price_search_exit"] = result.returncode
    if result.returncode != 0:
        facts["instance_price_search_output"] = result.stdout[-2000:]
        blockers.append("Brev instance price search failed; current instance availability/price is unknown")
        return
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        facts["instance_price_search_output"] = result.stdout[-2000:]
        blockers.append("Brev instance price search did not return parseable JSON")
        return
    if not isinstance(payload, list):
        blockers.append("Brev instance price search JSON root is not a list")
        return

    matches = [item for item in payload if isinstance(item, dict) and item.get("type") == instance_type]
    if not matches:
        blockers.append(f"selected instance type is not currently visible in Brev search: {instance_type}")
        return
    selected = matches[0]
    price = selected.get("price_per_hour")
    try:
        price_per_hour = float(price)
    except (TypeError, ValueError):
        blockers.append(f"selected instance type has no numeric price_per_hour: {instance_type}")
        return

    facts["instance_price"] = {
        "type": selected.get("type"),
        "cloud": selected.get("cloud"),
        "provider": selected.get("provider"),
        "gpu_name": selected.get("gpu_name"),
        "gpu_count": selected.get("gpu_count"),
        "total_vram_gb": selected.get("total_vram_gb"),
        "ram_gb": selected.get("ram_gb"),
        "stoppable": selected.get("stoppable"),
        "price_per_hour": price_per_hour,
    }
    if selected.get("stoppable") is not True:
        blockers.append(f"selected instance type is not stoppable: {instance_type}")
    estimate = facts.get("estimated_eur_per_hour")
    if isinstance(estimate, (int, float)) and price_per_hour > float(estimate):
        blockers.append(
            f"live Brev price_per_hour {price_per_hour:.4f} exceeds RCA_PAID_ESTIMATED_EUR_PER_HOUR {float(estimate):.4f}"
        )


def _check_manifest_contract(manifest_path: Path, blockers: list[str], facts: dict[str, Any]) -> None:
    if not manifest_path.is_file():
        blockers.append(f"manifest is missing: {_rel(manifest_path)}")
        return

    manifest = _load_json(manifest_path)
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        blockers.append("manifest.cases must be a list")
        return

    remote_policy = manifest.get("remote_run_policy")
    if not isinstance(remote_policy, dict):
        blockers.append("manifest.remote_run_policy must be present")
    else:
        if remote_policy.get("requires_budget_watchdog_pullback_delete") is not True:
            blockers.append("manifest must require budget/watchdog/pullback/delete for remote runs")

    report = classifier.build_report(manifest, results_root=None)
    facts["manifest_path"] = _rel(manifest_path)
    facts["classification_summary"] = report["summary"]

    by_case = {
        str(result.get("case_id")): result
        for result in report.get("results", [])
        if isinstance(result, dict)
    }
    baseline = by_case.get("baseline_replay")
    if not baseline or baseline.get("classification") != "strict_success":
        blockers.append("baseline_replay must remain a strict_success positive control")

    planned_missing = [
        result
        for result in report.get("results", [])
        if isinstance(result, dict)
        and result.get("case_id") != "baseline_replay"
        and result.get("classification") == "missing"
    ]
    facts["planned_missing_count"] = len(planned_missing)
    if not planned_missing:
        blockers.append("no missing planned variation cases remain to run")

    negative = by_case.get("socket_x_pos_25mm_negative_control")
    if not negative:
        blockers.append("manifest must include socket_x_pos_25mm_negative_control")
    else:
        facts["negative_control_classification"] = negative.get("classification")
        if negative.get("expected") != "fail_closed":
            blockers.append("socket_x_pos_25mm_negative_control must be expected=fail_closed")
        if negative.get("classification") == "strict_success":
            blockers.append("negative control is already strict_success; metric definition is invalid")


def _check_paid_env(blockers: list[str], facts: dict[str, Any]) -> None:
    if os.environ.get("RCA_ALLOW_PAID_BREV_CREATE") != "1":
        blockers.append("set RCA_ALLOW_PAID_BREV_CREATE=1 only for the deliberate paid batch run")
    credits_verified = os.environ.get("RCA_BREV_CREDITS_VERIFIED") == "1"
    if not credits_verified:
        blockers.append(
            "set RCA_BREV_CREDITS_VERIFIED=1 only after the current Brev UI/org credit balance covers this budget"
        )
    if LIFECYCLE_HOLD_FILE.is_file() and os.environ.get("RCA_ACK_BREV_LIFECYCLE_RISK") != "1":
        blockers.append(
            "Brev lifecycle hold is active; set RCA_ACK_BREV_LIFECYCLE_RISK=1 only for a consciously chosen single retry"
        )

    ttl_minutes = _parse_ttl_minutes(blockers)
    budget = _parse_float_env("RCA_PAID_BUDGET_EUR", blockers)
    hourly = _parse_float_env("RCA_PAID_ESTIMATED_EUR_PER_HOUR", blockers)
    credit_evidence_path = Path(os.environ.get("RCA_BREV_CREDIT_EVIDENCE_JSON", str(DEFAULT_CREDIT_EVIDENCE)))
    if not credit_evidence_path.is_absolute():
        credit_evidence_path = REPO_ROOT / credit_evidence_path
    credit_max_age = _parse_positive_int_env("RCA_BREV_CREDIT_EVIDENCE_MAX_AGE_MINUTES", 60, blockers)
    facts["ttl_minutes"] = ttl_minutes
    facts["budget_eur"] = budget
    facts["estimated_eur_per_hour"] = hourly
    facts["credit_evidence_path"] = _rel(credit_evidence_path)
    facts["credit_evidence_max_age_minutes"] = credit_max_age
    if budget is not None and credit_max_age is not None and credits_verified:
        credit_report = credit_gate.build_report(
            evidence_path=credit_evidence_path,
            required_budget_eur=budget,
            max_age_minutes=credit_max_age,
        )
        facts["credit_evidence"] = credit_report
        if credit_report.get("status") != "PASS":
            blockers.append(
                "RCA_BREV_CREDITS_VERIFIED=1 requires passing current Brev UI credit evidence"
            )
    elif not credits_verified:
        facts["credit_evidence"] = {
            "status": "NOT_CHECKED",
            "reason": "RCA_BREV_CREDITS_VERIFIED is not 1",
        }
    if ttl_minutes is not None and budget is not None and hourly is not None:
        estimated_max = hourly * ttl_minutes / 60.0
        facts["estimated_max_cost_eur"] = round(estimated_max, 4)
        if estimated_max - budget > 1e-9:
            blockers.append(
                f"estimated max cost {estimated_max:.4f} EUR exceeds budget {budget:.4f} EUR"
            )


def main() -> int:
    manifest_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_MANIFEST
    if not manifest_path.is_absolute():
        manifest_path = REPO_ROOT / manifest_path

    blockers: list[str] = []
    facts: dict[str, Any] = {}

    _check_manifest_contract(manifest_path, blockers, facts)
    _check_paid_env(blockers, facts)
    _check_phase2_gate(blockers, facts)
    _check_brev_safety(blockers, facts)
    _check_instance_price(blockers, facts)

    print("[success-variation-readiness] facts=" + json.dumps(facts, indent=2, sort_keys=True))
    if blockers:
        print("[success-variation-readiness] BLOCKED")
        for blocker in blockers:
            print(f"- {blocker}")
        return 2

    print("[success-variation-readiness] READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
