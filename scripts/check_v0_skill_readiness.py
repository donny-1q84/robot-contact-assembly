#!/usr/bin/env python3
"""Check readiness of a V0 skill request for dataset/policy/API work.

This is a read-only local gate. It validates the high-level request, verifies
the V0 contract, checks the Phase 2 contact gate, checks the success-variation
result gate, and confirms whether the V0 scripted-skill dataset is present.

It does not call Brev, Isaac, ROS, or any robot.
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

import check_success_variation_batch_results as variation_gate  # noqa: E402
import check_v0_skill_api_contract as contract_gate  # noqa: E402
import classify_success_variation_results as classifier  # noqa: E402
import validate_v0_skill_request as request_gate  # noqa: E402


DEFAULT_REQUEST = REPO_ROOT / "configs" / "v0_skill_request.example.json"
DEFAULT_CONTRACT = REPO_ROOT / "configs" / "v0_skill_api_contract.json"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"


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


def _run_phase2_gate(skip: bool) -> dict[str, Any]:
    if skip:
        return {"status": "SKIPPED", "exit_code": None, "output_tail": ""}
    result = subprocess.run(
        ["python3", "scripts/check_phase2_contact_gate.py"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
        check=False,
    )
    return {
        "status": "PASS" if result.returncode == 0 else "BLOCKED",
        "exit_code": result.returncode,
        "output_tail": result.stdout[-2000:],
    }


def _variation_result_gate(
    manifest_path: Path,
    *,
    min_strict_successes: int,
    negative_control_id: str,
) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    report = classifier.build_report(manifest, results_root=None)
    gate = variation_gate._build_gate(
        report,
        min_strict_successes=max(1, min_strict_successes),
        negative_control_id=negative_control_id,
        allow_near_success=False,
        allow_missing=False,
    )
    return {
        "manifest": _rel(manifest_path),
        "classification_summary": report.get("summary"),
        "gate": gate,
    }


def _dataset_gate(dataset_path: Path, contract_path: Path) -> dict[str, Any]:
    if not dataset_path.is_file():
        return {
            "status": "MISSING",
            "path": _rel(dataset_path),
            "failures": ["V0 scripted-skill dataset manifest is missing"],
        }
    dataset = _load_json(dataset_path)
    failures: list[str] = []
    if dataset.get("dataset_name") != "v0_scripted_skill_success_variations":
        failures.append("dataset_name must be v0_scripted_skill_success_variations")
    if dataset.get("skill_api_contract") != _rel(contract_path):
        failures.append(
            f"dataset skill_api_contract must be {_rel(contract_path)}, got {dataset.get('skill_api_contract')}"
        )
    if not isinstance(dataset.get("cases"), list) or not dataset.get("cases"):
        failures.append("dataset must contain at least one strict-success case")
    not_claims = dataset.get("not_claims")
    if not isinstance(not_claims, list) or "not sim-to-real" not in not_claims:
        failures.append("dataset must preserve not sim-to-real non-claim")
    return {
        "status": "PASS" if not failures else "FAIL",
        "path": _rel(dataset_path),
        "failures": failures,
        "case_count": len(dataset.get("cases", [])) if isinstance(dataset.get("cases"), list) else None,
    }


def _next_action(blockers: list[str], variation: dict[str, Any], dataset: dict[str, Any]) -> str:
    if not blockers:
        return "ready_for_policy_api_review"
    failures = variation.get("gate", {}).get("failures") or []
    if any("missing planned trace artifacts" in str(failure) for failure in failures):
        return "run_fixed_budget_success_variation_batch_after_paid_ack"
    if variation.get("gate", {}).get("pass") and dataset.get("status") == "MISSING":
        return "run_success_variation_finalizer_to_prepare_dataset"
    return "resolve_v0_skill_readiness_blockers"


def build_report(
    *,
    request_path: Path,
    contract_path: Path,
    manifest_path: Path,
    dataset_path: Path,
    min_strict_successes: int,
    negative_control_id: str,
    skip_phase2: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    contract = contract_gate.build_report(contract_path)
    if contract.get("status") != "PASS":
        blockers.extend("contract: " + str(failure) for failure in contract.get("failures", []))

    request = request_gate.build_report(request_path, contract_path)
    if request.get("status") != "PASS":
        blockers.extend("request: " + str(failure) for failure in request.get("failures", []))

    phase2 = _run_phase2_gate(skip_phase2)
    if phase2.get("status") == "SKIPPED":
        warnings.append("Phase 2 contact gate check was skipped for isolated testing")
    elif phase2.get("status") != "PASS":
        blockers.append("Phase 2 contact gate is not PASS")

    variation = _variation_result_gate(
        manifest_path,
        min_strict_successes=min_strict_successes,
        negative_control_id=negative_control_id,
    )
    variation_gate_payload = variation.get("gate", {})
    if not variation_gate_payload.get("pass"):
        blockers.extend("success variation: " + str(failure) for failure in variation_gate_payload.get("failures", []))

    dataset = _dataset_gate(dataset_path, contract_path)
    if dataset.get("status") != "PASS":
        blockers.extend("dataset: " + str(failure) for failure in dataset.get("failures", []))

    unique_blockers = list(dict.fromkeys(blockers))
    status = "READY" if not unique_blockers else "BLOCKED"
    return {
        "readiness_name": "v0_skill_request_readiness",
        "status": status,
        "request": _rel(request_path),
        "contract": _rel(contract_path),
        "manifest": _rel(manifest_path),
        "dataset": _rel(dataset_path),
        "request_gate": request,
        "contract_gate": contract,
        "phase2_contact_gate": phase2,
        "success_variation_gate": variation,
        "dataset_gate": dataset,
        "blockers": unique_blockers,
        "warnings": warnings,
        "next_action": _next_action(unique_blockers, variation, dataset),
        "not_claims": [
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, nargs="?", default=DEFAULT_REQUEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--negative-control-id", default=variation_gate.DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--skip-phase2-contact-gate", action="store_true")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_report(
        request_path=_resolve(args.request),
        contract_path=_resolve(args.contract),
        manifest_path=_resolve(args.manifest),
        dataset_path=_resolve(args.dataset),
        min_strict_successes=args.min_strict_successes,
        negative_control_id=args.negative_control_id,
        skip_phase2=args.skip_phase2_contact_gate,
    )

    if args.output_json is not None:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-skill-readiness] wrote JSON: {_rel(output_json)}")

    print("[v0-skill-readiness] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == "READY":
        print("[v0-skill-readiness] READY")
        return 0

    print("[v0-skill-readiness] BLOCKED")
    for blocker in report["blockers"]:
        print(f"- {blocker}")
    print(f"[v0-skill-readiness] next_action={report['next_action']}")
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
