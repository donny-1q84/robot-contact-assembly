#!/usr/bin/env python3
"""Check whether a V0 residual policy may move to promotion review.

This read-only gate sits after supervised residual-policy evaluation. A
supervised residual-label score is not enough: policy promotion also needs an
Isaac closed-loop policy evaluation with the same checkpoint checksum, strict
success coverage, a fail-closed negative control, and a scripted-baseline
comparison.

It does not call Brev, start Isaac, ROS, a vendor SDK, or any robot. Passing
this gate is only readiness for manual policy-promotion review, not sim-to-real
or direct drop-in precision on another robot arm.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_success_variation_batch_results as variation_gate  # noqa: E402
import check_v0_skill_readiness as skill_readiness_gate  # noqa: E402


DEFAULT_REQUEST = REPO_ROOT / "configs" / "v0_skill_request.example.json"
DEFAULT_CONTRACT = REPO_ROOT / "configs" / "v0_skill_api_contract.json"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"
DEFAULT_SUPERVISED_EVAL = REPO_ROOT / "artifacts" / "evaluations" / "v0_residual_policy" / "summary.json"
DEFAULT_ISAAC_EVAL = REPO_ROOT / "artifacts" / "evaluations" / "v0_residual_policy_isaac" / "summary.json"

READY_STATUS = "READY_FOR_POLICY_PROMOTION_REVIEW"
SUPERVISED_STATUS = "SUPERVISED_EVAL_NEEDS_ISAAC_POLICY_GATE"
ISAAC_EVAL_NAME = "v0_residual_policy_isaac_closed_loop"


def _side_effects(*, writes_promotion_report: bool) -> dict[str, bool]:
    return {
        "writes_promotion_report": writes_promotion_report,
        "writes_checkpoint": False,
        "trains_policy": False,
        "creates_paid_instance": False,
        "runs_remote_code": False,
        "starts_isaac": False,
        "calls_ros_or_robot": False,
    }


def _rel(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _resolve(path: Path | str | None) -> Path | None:
    if path is None:
        return None
    resolved = Path(path).expanduser()
    if resolved.is_absolute():
        return resolved
    return REPO_ROOT / resolved


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root must be an object: {_rel(path)}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _negative_control_failure(prefix: str, evidence: dict[str, Any], *, negative_control_id: str) -> str | None:
    if not evidence:
        return f"{prefix} must preserve negative_control_evidence"
    if evidence.get("case_id") != negative_control_id:
        return (
            f"{prefix} negative_control_evidence.case_id must be {negative_control_id}, "
            f"got {evidence.get('case_id')}"
        )
    if evidence.get("expected") != "fail_closed":
        return f"{prefix} negative_control_evidence.expected must be fail_closed, got {evidence.get('expected')}"
    if evidence.get("classification") != "fail_closed":
        return (
            f"{prefix} negative_control_evidence.classification must be fail_closed, "
            f"got {evidence.get('classification')}"
        )
    if evidence.get("excluded_from_training_cases") is not True:
        return f"{prefix} negative_control_evidence must preserve excluded_from_training_cases=true"
    if not isinstance(evidence.get("trace_sha256"), str) or not evidence.get("trace_sha256"):
        return f"{prefix} negative_control_evidence must preserve trace_sha256"
    return None


def _negative_trace_sha(evidence: dict[str, Any]) -> str | None:
    value = evidence.get("trace_sha256")
    return value if isinstance(value, str) and value else None


def _skill_readiness(
    *,
    request_path: Path,
    contract_path: Path,
    manifest_path: Path,
    dataset_path: Path,
    min_strict_successes: int,
    negative_control_id: str,
    skip_phase2: bool,
) -> dict[str, Any]:
    return skill_readiness_gate.build_report(
        request_path=request_path,
        contract_path=contract_path,
        manifest_path=manifest_path,
        dataset_path=dataset_path,
        min_strict_successes=min_strict_successes,
        negative_control_id=negative_control_id,
        skip_phase2=skip_phase2,
    )


def _supervised_eval_gate(path: Path, failures: list[str], *, negative_control_id: str) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"supervised residual-policy evaluation summary is missing: {_rel(path)}")
        return {
            "path": _rel(path),
            "status": "MISSING",
            "checkpoint": None,
            "checkpoint_sha256": None,
            "metadata": None,
            "negative_control_evidence": None,
        }

    payload = _load_json(path)
    status = str(payload.get("status") or "BLOCKED")
    if status != SUPERVISED_STATUS:
        failures.append(f"supervised eval status must be {SUPERVISED_STATUS}, got {status}")

    metadata_path = _resolve(payload.get("metadata"))
    checkpoint_path = _resolve(payload.get("checkpoint"))
    checkpoint_sha: str | None = None
    metadata: dict[str, Any] = {}
    payload_negative = _as_dict(payload.get("negative_control_evidence"))
    metadata_negative: dict[str, Any] = {}

    if metadata_path is None or not metadata_path.is_file():
        failures.append(f"supervised eval metadata is missing: {_rel(metadata_path)}")
    else:
        metadata = _load_json(metadata_path)
        if metadata.get("status") != "TRAINED_NEEDS_EVALUATION":
            failures.append(f"training metadata status must be TRAINED_NEEDS_EVALUATION, got {metadata.get('status')}")
        metadata_negative = _as_dict(metadata.get("negative_control_evidence"))

    if checkpoint_path is None or not checkpoint_path.is_file():
        failures.append(f"supervised eval checkpoint is missing: {_rel(checkpoint_path)}")
    else:
        checkpoint_sha = _sha256(checkpoint_path)
        expected_checkpoint_sha = metadata.get("checkpoint_sha256") if metadata else None
        if expected_checkpoint_sha and checkpoint_sha != expected_checkpoint_sha:
            failures.append(f"checkpoint_sha256 mismatch against metadata: {checkpoint_sha} != {expected_checkpoint_sha}")
        metadata_checkpoint = _resolve(metadata.get("checkpoint")) if metadata else None
        if metadata_checkpoint is not None and metadata_checkpoint.is_file():
            metadata_checkpoint_sha = _sha256(metadata_checkpoint)
            if checkpoint_sha != metadata_checkpoint_sha:
                failures.append("supervised eval checkpoint is not the same checkpoint recorded in metadata")

    not_claims = [str(item) for item in _as_list(payload.get("not_claims"))]
    for required in (
        "not Isaac closed-loop evaluation",
        "not sim-to-real",
        "not cross-robot-ready",
        "not direct drop-in precision on another robot arm",
    ):
        if required not in not_claims:
            failures.append(f"supervised eval must preserve non-claim: {required}")
    payload_negative_failure = _negative_control_failure(
        "supervised eval", payload_negative, negative_control_id=negative_control_id
    )
    if payload_negative_failure:
        failures.append(payload_negative_failure)
    metadata_negative_failure = _negative_control_failure(
        "training metadata", metadata_negative, negative_control_id=negative_control_id
    )
    if metadata_negative_failure:
        failures.append(metadata_negative_failure)
    if _negative_trace_sha(payload_negative) and _negative_trace_sha(metadata_negative):
        if _negative_trace_sha(payload_negative) != _negative_trace_sha(metadata_negative):
            failures.append("supervised eval negative_control_evidence.trace_sha256 must match training metadata")

    return {
        "path": _rel(path),
        "status": status,
        "checkpoint": _rel(checkpoint_path),
        "checkpoint_sha256": checkpoint_sha,
        "metadata": _rel(metadata_path),
        "sample_count": payload.get("sample_count"),
        "negative_control_evidence": payload_negative or metadata_negative,
        "not_claims": not_claims,
    }


def _isaac_closed_loop_gate(
    path: Path,
    failures: list[str],
    *,
    expected_checkpoint_sha256: str | None,
    min_strict_successes: int,
    min_strict_success_rate: float,
    negative_control_id: str,
) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"Isaac closed-loop policy evaluation summary is missing: {_rel(path)}")
        return {
            "path": _rel(path),
            "status": "MISSING",
            "checkpoint_sha256": None,
            "strict_successes": None,
            "strict_trials": None,
            "strict_success_rate": None,
        }

    payload = _load_json(path)
    status = str(payload.get("status") or "BLOCKED")
    if status != "PASS":
        failures.append(f"Isaac closed-loop eval status must be PASS, got {status}")
    if payload.get("eval_name") != ISAAC_EVAL_NAME:
        failures.append(f"Isaac closed-loop eval_name must be {ISAAC_EVAL_NAME}, got {payload.get('eval_name')}")

    observed_checkpoint_sha = payload.get("policy_checkpoint_sha256") or payload.get("checkpoint_sha256")
    if not isinstance(observed_checkpoint_sha, str) or not observed_checkpoint_sha:
        failures.append("Isaac closed-loop eval must record policy_checkpoint_sha256")
    elif expected_checkpoint_sha256 is None:
        failures.append("cannot compare Isaac eval checkpoint because supervised checkpoint checksum is unavailable")
    elif observed_checkpoint_sha != expected_checkpoint_sha256:
        failures.append(
            "Isaac closed-loop checkpoint checksum must match supervised eval checkpoint: "
            f"{observed_checkpoint_sha} != {expected_checkpoint_sha256}"
        )

    strict_successes = _int(payload.get("strict_successes"), 0)
    strict_trials = _int(payload.get("strict_trials"), 0)
    strict_success_rate = _number(payload.get("strict_success_rate"), 0.0)
    if strict_successes < min_strict_successes:
        failures.append(
            f"Isaac closed-loop strict_successes must be >= {min_strict_successes}, got {strict_successes}"
        )
    if strict_trials < strict_successes or strict_trials < min_strict_successes:
        failures.append(f"Isaac closed-loop strict_trials must cover successes, got {strict_trials}")
    if strict_success_rate < min_strict_success_rate:
        failures.append(
            f"Isaac closed-loop strict_success_rate must be >= {min_strict_success_rate}, got {strict_success_rate}"
        )

    negative_control = _as_dict(payload.get("negative_control"))
    if negative_control.get("id") != negative_control_id:
        failures.append(f"negative_control.id must be {negative_control_id}, got {negative_control.get('id')}")
    if negative_control.get("result") != "fail_closed":
        failures.append("negative_control.result must be fail_closed")
    if negative_control.get("strict_success") is not False:
        failures.append("negative_control.strict_success must be false")

    baseline = _as_dict(payload.get("scripted_baseline_comparison"))
    if baseline.get("policy_not_worse_than_scripted_baseline") is not True:
        failures.append("scripted_baseline_comparison must mark policy_not_worse_than_scripted_baseline=true")
    if baseline.get("regression") is not False:
        failures.append("scripted_baseline_comparison.regression must be false")

    not_claims = [str(item) for item in _as_list(payload.get("not_claims"))]
    for required in (
        "not sim-to-real",
        "not cross-robot-ready",
        "not direct drop-in precision on another robot arm",
        "not external robot ready",
    ):
        if required not in not_claims:
            failures.append(f"Isaac closed-loop eval must preserve non-claim: {required}")

    return {
        "path": _rel(path),
        "status": status,
        "eval_name": payload.get("eval_name"),
        "checkpoint_sha256": observed_checkpoint_sha,
        "strict_successes": strict_successes,
        "strict_trials": strict_trials,
        "strict_success_rate": strict_success_rate,
        "negative_control": negative_control,
        "scripted_baseline_comparison": baseline,
        "not_claims": not_claims,
    }


def _next_action(blockers: list[str]) -> str:
    if not blockers:
        return "manual_policy_promotion_review"
    if any("V0 skill readiness" in blocker for blocker in blockers):
        return "finish_success_variation_batch_and_freeze_v0_skill_dataset"
    if any("supervised residual-policy evaluation summary is missing" in blocker for blocker in blockers):
        return "train_and_supervised_eval_v0_residual_policy_after_label_dataset"
    if any("Isaac closed-loop policy evaluation summary is missing" in blocker for blocker in blockers):
        return "run_isaac_closed_loop_policy_gate_with_same_checkpoint_and_negative_control"
    return "resolve_policy_promotion_gate_blockers"


def build_report(
    *,
    request_path: Path,
    contract_path: Path,
    manifest_path: Path,
    dataset_path: Path,
    supervised_eval_path: Path,
    isaac_eval_path: Path,
    min_strict_successes: int,
    min_isaac_strict_successes: int,
    min_isaac_strict_success_rate: float,
    negative_control_id: str,
    skip_phase2: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    skill_readiness = _skill_readiness(
        request_path=request_path,
        contract_path=contract_path,
        manifest_path=manifest_path,
        dataset_path=dataset_path,
        min_strict_successes=min_strict_successes,
        negative_control_id=negative_control_id,
        skip_phase2=skip_phase2,
    )
    if skill_readiness.get("status") != "READY":
        blockers.append(
            "V0 skill readiness must be READY before policy promotion; "
            f"got {skill_readiness.get('status')}"
        )
    if skip_phase2:
        warnings.append("Phase 2 contact gate check was skipped for isolated testing")

    supervised = _supervised_eval_gate(supervised_eval_path, blockers, negative_control_id=negative_control_id)
    isaac = _isaac_closed_loop_gate(
        isaac_eval_path,
        blockers,
        expected_checkpoint_sha256=supervised.get("checkpoint_sha256")
        if isinstance(supervised.get("checkpoint_sha256"), str)
        else None,
        min_strict_successes=min_isaac_strict_successes,
        min_strict_success_rate=min_isaac_strict_success_rate,
        negative_control_id=negative_control_id,
    )

    unique_blockers = list(dict.fromkeys(blockers))
    status = READY_STATUS if not unique_blockers else "BLOCKED"
    return {
        "gate_name": "v0_residual_policy_promotion_gate",
        "status": status,
        "ready_for_policy_promotion_review": status == READY_STATUS,
        "ready_for_hardware": False,
        "ready_for_external_robot": False,
        "ready_for_sim_to_real": False,
        "ready_for_cross_robot": False,
        "request": _rel(request_path),
        "manifest": _rel(manifest_path),
        "dataset": _rel(dataset_path),
        "supervised_eval": supervised,
        "isaac_closed_loop_eval": isaac,
        "skill_readiness_status": skill_readiness.get("status"),
        "skill_readiness_next_action": skill_readiness.get("next_action"),
        "min_isaac_strict_successes": min_isaac_strict_successes,
        "min_isaac_strict_success_rate": min_isaac_strict_success_rate,
        "negative_control_id": negative_control_id,
        "blockers": unique_blockers,
        "warnings": warnings,
        "next_action": _next_action(unique_blockers),
        "side_effects": _side_effects(writes_promotion_report=False),
        "required_before_policy_promotion": [
            "V0 skill readiness READY with strict success variations and fail-closed negative control",
            "supervised residual-policy evaluation summary from the trained checkpoint",
            "Isaac closed-loop policy gate with the same checkpoint checksum",
            "scripted-baseline comparison showing no regression",
            "negative control remains fail_closed under the policy",
        ],
        "not_claims": [
            "not sim-to-real",
            "not cross-robot-ready",
            "not external robot ready",
            "not direct drop-in precision on another robot arm",
            "not a Brev or Isaac launcher",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--supervised-eval", type=Path, default=DEFAULT_SUPERVISED_EVAL)
    parser.add_argument("--isaac-eval", type=Path, default=DEFAULT_ISAAC_EVAL)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--min-isaac-strict-successes", type=int, default=5)
    parser.add_argument("--min-isaac-strict-success-rate", type=float, default=0.8)
    parser.add_argument("--negative-control-id", default=variation_gate.DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--skip-phase2-contact-gate", action="store_true")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    report = build_report(
        request_path=_resolve(args.request) or DEFAULT_REQUEST,
        contract_path=_resolve(args.contract) or DEFAULT_CONTRACT,
        manifest_path=_resolve(args.manifest) or DEFAULT_MANIFEST,
        dataset_path=_resolve(args.dataset) or DEFAULT_DATASET,
        supervised_eval_path=_resolve(args.supervised_eval) or DEFAULT_SUPERVISED_EVAL,
        isaac_eval_path=_resolve(args.isaac_eval) or DEFAULT_ISAAC_EVAL,
        min_strict_successes=args.min_strict_successes,
        min_isaac_strict_successes=args.min_isaac_strict_successes,
        min_isaac_strict_success_rate=args.min_isaac_strict_success_rate,
        negative_control_id=args.negative_control_id,
        skip_phase2=args.skip_phase2_contact_gate,
    )

    if args.output_json is not None and not args.no_output:
        report["side_effects"] = _side_effects(writes_promotion_report=True)
        output_json = _resolve(args.output_json) or args.output_json
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-policy-promotion-gate] wrote JSON: {_rel(output_json)}")

    print("[v0-policy-promotion-gate] facts=" + json.dumps(report, indent=2, sort_keys=True))
    if report["status"] == READY_STATUS:
        print("[v0-policy-promotion-gate] READY_FOR_POLICY_PROMOTION_REVIEW")
        return 0

    print("[v0-policy-promotion-gate] BLOCKED")
    for blocker in report["blockers"]:
        print(f"- {blocker}")
    print(f"[v0-policy-promotion-gate] next_action={report['next_action']}")
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
