#!/usr/bin/env python3
"""Select the next allowed project action from current gate evidence.

This is a read-only decision helper. It does not create Brev instances, write
credit evidence, arm local env state, start Isaac, call ROS, train a policy, or
write dataset artifacts. It reduces the current gate state to one prioritized
next action so the project does not drift into VLM, policy, video, or robot
adapter work before the reproducibility gate is actually unblocked.
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

import check_success_variation_batch_results as variation_gate  # noqa: E402
import check_v0_skill_readiness as skill_readiness_gate  # noqa: E402
import classify_success_variation_results as classifier  # noqa: E402
import diagnose_brev_credit_blocker as credit_diagnosis  # noqa: E402
import prepare_success_variation_dataset as dataset_gate  # noqa: E402
import prepare_v0_policy_api_review as policy_review_gate  # noqa: E402


DEFAULT_MANIFEST = variation_gate.DEFAULT_MANIFEST
DEFAULT_REQUEST = skill_readiness_gate.DEFAULT_REQUEST
DEFAULT_CONTRACT = skill_readiness_gate.DEFAULT_CONTRACT
DEFAULT_DATASET = skill_readiness_gate.DEFAULT_DATASET
DEFAULT_CONFIG = credit_diagnosis.DEFAULT_CONFIG
DEFAULT_RUN_PACKET = credit_diagnosis.DEFAULT_RUN_PACKET
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "next_project_action.json"


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


def _variation_report(manifest_path: Path) -> dict[str, Any]:
    manifest = dataset_gate._load_json(manifest_path)
    classification = classifier.build_report(manifest, results_root=None)
    gate = variation_gate._build_gate(
        classification,
        min_strict_successes=5,
        negative_control_id=variation_gate.DEFAULT_NEGATIVE_CONTROL,
        allow_near_success=False,
        allow_missing=False,
    )
    return {
        "manifest": _rel(manifest_path),
        "classification_summary": classification.get("summary"),
        "gate": gate,
    }


def _policy_review_status(
    *,
    request_path: Path,
    contract_path: Path,
    manifest_path: Path,
    dataset_path: Path,
    skip_phase2: bool,
) -> dict[str, Any]:
    readiness = skill_readiness_gate.build_report(
        request_path=request_path,
        contract_path=contract_path,
        manifest_path=manifest_path,
        dataset_path=dataset_path,
        min_strict_successes=5,
        negative_control_id=variation_gate.DEFAULT_NEGATIVE_CONTROL,
        skip_phase2=skip_phase2,
    )
    if readiness.get("status") != "READY":
        return policy_review_gate._build_blocked_packet(readiness, dataset_path)
    return {"status": "READY", "next_action": "prepare_v0_policy_api_review"}


def _dataset_status(manifest_path: Path) -> dict[str, Any]:
    manifest = dataset_gate._load_json(manifest_path)
    classification = classifier.build_report(manifest, results_root=None)
    gate = variation_gate._build_gate(
        classification,
        min_strict_successes=5,
        negative_control_id=variation_gate.DEFAULT_NEGATIVE_CONTROL,
        allow_near_success=False,
        allow_missing=False,
    )
    return {
        "status": "READY_TO_PREPARE" if gate.get("pass") else "BLOCKED",
        "gate_pass": bool(gate.get("pass")),
        "gate_summary": gate.get("summary"),
        "failures": gate.get("failures", []),
    }


def _commands(balance_eur: float | None) -> dict[str, list[str]]:
    balance_arg = f"{balance_eur:.2f}" if balance_eur is not None else "<current-brev-ui-balance>"
    return {
        "diagnose_credit_default": [
            "python3",
            "scripts/diagnose_brev_credit_blocker.py",
            "--no-output",
        ],
        "diagnose_credit_with_ui_balance": [
            "python3",
            "scripts/diagnose_brev_credit_blocker.py",
            "--balance-eur",
            balance_arg,
            "--no-output",
        ],
        "review_credit_with_ui_balance": [
            "python3",
            "scripts/prepare_brev_credit_review.py",
            "--balance-eur",
            balance_arg,
            "--no-output",
        ],
        "paid_lifecycle_dry_run": [
            "python3",
            "scripts/run_success_variation_paid_lifecycle.py",
            "--balance-eur",
            balance_arg,
            "--dry-run",
        ],
        "paid_lifecycle_single_run": [
            "python3",
            "scripts/run_success_variation_paid_lifecycle.py",
            "--balance-eur",
            balance_arg,
            "--run",
            "--i-understand-this-can-create-paid-instance",
        ],
        "finalize_success_variation_dataset": [
            "scripts/finalize_success_variation_batch.sh",
            "artifacts/manifests/success_trace_variations_2026-06-25.json",
        ],
        "policy_api_review": [
            "python3",
            "scripts/prepare_v0_policy_api_review.py",
        ],
        "offline_policy_readiness": [
            "python3",
            "scripts/run_v0_offline_policy_readiness_pipeline.py",
            "--skip-phase2-contact-gate",
            "--no-summary",
            "--no-output",
        ],
    }


def _select(
    *,
    credit: dict[str, Any],
    variation: dict[str, Any],
    dataset: dict[str, Any],
    policy: dict[str, Any],
    commands: dict[str, list[str]],
) -> dict[str, Any]:
    credit_allowed = credit.get("paid_prepare_allowed") is True
    credit_status = str(credit.get("status") or "UNKNOWN")
    consistency = credit.get("credit_consistency") if isinstance(credit.get("credit_consistency"), dict) else {}
    variation_gate_payload = variation.get("gate") if isinstance(variation.get("gate"), dict) else {}
    variation_pass = variation_gate_payload.get("pass") is True

    if not credit_allowed:
        return {
            "status": "BLOCKED",
            "priority": 1,
            "next_action": "resolve_brev_credit_blocker",
            "reason": "Brev credit/API gate is not ready; paid prep and paid success-variation batch must remain blocked.",
            "blocking_gate": "brev_credit",
            "credit_diagnosis_status": credit_status,
            "credit_consistency_status": consistency.get("status"),
            "paid_compute_allowed": False,
            "allowed_commands": [
                commands["diagnose_credit_default"],
                commands["diagnose_credit_with_ui_balance"],
                commands["review_credit_with_ui_balance"],
            ],
            "forbidden_until_resolved": [
                "write_brev_credit_evidence",
                "arm_success_variation_paid_env",
                "run_success_variation_paid_lifecycle --run",
                "dataset_freeze",
                "policy_training",
                "vlm_or_ros_execution_claims",
            ],
        }

    if not variation_pass:
        return {
            "status": "READY_FOR_NEXT_ACTION",
            "priority": 2,
            "next_action": "run_fixed_budget_success_variation_trace_batch",
            "reason": "Credit gate is ready, but success-variation traces and the fail-closed negative control are missing.",
            "blocking_gate": "success_variation_reproducibility",
            "paid_compute_allowed": True,
            "allowed_commands": [
                commands["paid_lifecycle_dry_run"],
                commands["paid_lifecycle_single_run"],
            ],
            "forbidden_until_resolved": [
                "dataset_freeze",
                "policy_training",
                "vlm_or_ros_execution_claims",
                "external_robot_execution_claims",
            ],
        }

    if dataset.get("status") != "READY_TO_PREPARE":
        return {
            "status": "BLOCKED",
            "priority": 3,
            "next_action": "inspect_success_variation_result_gate",
            "reason": "Variation gate state is inconsistent with dataset readiness.",
            "blocking_gate": "dataset_preparation",
            "paid_compute_allowed": False,
            "allowed_commands": [commands["finalize_success_variation_dataset"]],
            "forbidden_until_resolved": ["policy_training", "vlm_or_ros_execution_claims"],
        }

    if policy.get("status") != "READY":
        return {
            "status": "READY_FOR_NEXT_ACTION",
            "priority": 4,
            "next_action": "finalize_success_variation_dataset_then_prepare_policy_api_review",
            "reason": "Variation gate is ready; freeze the V0 scripted-skill dataset before policy/API work.",
            "blocking_gate": "v0_dataset",
            "paid_compute_allowed": False,
            "allowed_commands": [
                commands["finalize_success_variation_dataset"],
                commands["policy_api_review"],
            ],
            "forbidden_until_resolved": ["policy_training", "vlm_or_ros_execution_claims"],
        }

    return {
        "status": "READY_FOR_NEXT_ACTION",
        "priority": 5,
        "next_action": "run_offline_policy_readiness_pipeline",
        "reason": "V0 skill readiness and policy/API review are ready; proceed to offline residual-policy preparation.",
        "blocking_gate": None,
        "paid_compute_allowed": False,
        "allowed_commands": [commands["offline_policy_readiness"]],
        "forbidden_until_resolved": ["hardware_robot_execution_claims"],
    }


def build_report(
    *,
    balance_eur: float | None,
    api_credit_output: Path | None,
    skip_phase2: bool,
    credit_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_path = _resolve(DEFAULT_MANIFEST)
    request_path = _resolve(DEFAULT_REQUEST)
    contract_path = _resolve(DEFAULT_CONTRACT)
    dataset_path = _resolve(DEFAULT_DATASET)
    commands = _commands(balance_eur)
    credit = (
        credit_report
        if credit_report is not None
        else credit_diagnosis.build_report(
            config_path=_resolve(DEFAULT_CONFIG),
            manifest_path=manifest_path,
            run_packet_path=_resolve(DEFAULT_RUN_PACKET),
            balance_eur=balance_eur,
            api_credit_output=api_credit_output,
            command_timeout_seconds=60,
        )
    )
    variation = _variation_report(manifest_path)
    dataset = _dataset_status(manifest_path)
    policy = _policy_review_status(
        request_path=request_path,
        contract_path=contract_path,
        manifest_path=manifest_path,
        dataset_path=dataset_path,
        skip_phase2=skip_phase2,
    )
    decision = _select(
        credit=credit,
        variation=variation,
        dataset=dataset,
        policy=policy,
        commands=commands,
    )
    return {
        "selector_name": "next_project_action_selector",
        "decision": decision,
        "credit": {
            "status": credit.get("status"),
            "paid_prepare_allowed": credit.get("paid_prepare_allowed"),
            "api_credit_balance": credit.get("api_credit_balance"),
            "credit_consistency": credit.get("credit_consistency"),
            "active_organization": credit.get("active_organization"),
            "visible_instances": credit.get("visible_instances"),
        },
        "success_variation": {
            "gate_pass": variation.get("gate", {}).get("pass"),
            "summary": variation.get("gate", {}).get("summary"),
            "failures": variation.get("gate", {}).get("failures"),
        },
        "dataset": dataset,
        "policy_api_review": {
            "status": policy.get("status"),
            "next_action": policy.get("next_action"),
        },
        "side_effects": {
            "writes_action_report": False,
            "writes_credit_evidence": False,
            "writes_local_env": False,
            "writes_dataset_artifacts": False,
            "writes_policy_artifacts": False,
            "creates_paid_instance": False,
            "runs_remote_code": False,
            "starts_isaac": False,
            "calls_ros_or_robot": False,
            "trains_policy": False,
        },
        "not_claims": [
            "not success-variation result evidence",
            "not a paid run",
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--balance-eur", type=_nonnegative_float)
    parser.add_argument("--api-credit-output", type=Path)
    parser.add_argument("--skip-phase2-contact-gate", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_report(
        balance_eur=args.balance_eur,
        api_credit_output=args.api_credit_output,
        skip_phase2=args.skip_phase2_contact_gate,
    )
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        report["side_effects"]["writes_action_report"] = True
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[next-project-action] wrote JSON: {_rel(output_json)}")

    decision = report["decision"]
    print("[next-project-action] facts=" + json.dumps(report, indent=2, sort_keys=True))
    print("[next-project-action] status=" + str(decision["status"]))
    print("[next-project-action] next_action=" + str(decision["next_action"]))
    print("[next-project-action] blocking_gate=" + str(decision["blocking_gate"]))
    print("[next-project-action] paid_compute_allowed=" + str(decision["paid_compute_allowed"]))
    print("[next-project-action] reason=" + str(decision["reason"]))
    if args.fail_on_blocked and decision["status"] == "BLOCKED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
