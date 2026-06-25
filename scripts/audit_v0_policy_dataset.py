#!/usr/bin/env python3
"""Audit the V0 policy dataset before any residual-policy training.

This is an offline provenance and case-balance gate. It checks the V0
scripted-skill dataset and optional policy/API review packet.
It does not train a policy, call Brev, start Isaac, call ROS, or talk to a robot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"
DEFAULT_REVIEW = REPO_ROOT / "artifacts" / "reviews" / "v0_policy_api" / "review_packet.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_dataset_audit.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_dataset_audit.md"
DEFAULT_CONTRACT = "configs/v0_skill_api_contract.json"
DEFAULT_NEGATIVE_CONTROL = "socket_x_pos_25mm_negative_control"
REQUIRED_COVERAGE_GROUPS = {"seed_or_reset", "socket_x", "socket_y", "socket_z"}


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _coverage_groups(case: dict[str, Any]) -> set[str]:
    groups: set[str] = set()
    case_id = str(case.get("case_id") or "")
    if case_id.startswith("seed_") or case.get("reset_joint_noise_rad") is not None:
        groups.add("seed_or_reset")
    delta = case.get("socket_delta_m")
    if isinstance(delta, list) and len(delta) >= 3:
        axes = ("socket_x", "socket_y", "socket_z")
        for index, axis in enumerate(axes):
            try:
                value = float(delta[index])
            except (TypeError, ValueError):
                value = 0.0
            if abs(value) > 1e-12:
                groups.add(axis)
    for axis in ("socket_x", "socket_y", "socket_z"):
        if axis in case_id:
            groups.add(axis)
    return groups


def _trace_check(case: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    trace_value = case.get("trace_json")
    if not isinstance(trace_value, str) or not trace_value:
        return ["case trace_json must be a non-empty string"]
    trace_path = _resolve(Path(trace_value))
    if not trace_path.is_file():
        return [f"trace artifact is missing: {_rel(trace_path)}"]
    expected_sha = case.get("trace_sha256")
    if isinstance(expected_sha, str) and expected_sha:
        actual_sha = _sha256(trace_path)
        if actual_sha != expected_sha:
            failures.append(f"trace_sha256 mismatch for {case.get('case_id')}: {actual_sha} != {expected_sha}")
    return failures


def build_audit(
    *,
    dataset_path: Path,
    review_path: Path,
    min_cases: int,
    negative_control_id: str,
    require_review: bool,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    dataset: dict[str, Any] = {}
    review: dict[str, Any] = {}

    if not dataset_path.is_file():
        failures.append(f"dataset manifest is missing: {_rel(dataset_path)}")
    else:
        dataset = _load_json(dataset_path)

    if require_review:
        if not review_path.is_file():
            failures.append(f"policy/API review packet is missing: {_rel(review_path)}")
        else:
            review = _load_json(review_path)
    elif review_path.is_file():
        review = _load_json(review_path)
    else:
        warnings.append("policy/API review packet was not checked")

    cases = dataset.get("cases") if isinstance(dataset.get("cases"), list) else []
    excluded_cases = dataset.get("excluded_cases") if isinstance(dataset.get("excluded_cases"), list) else []
    case_ids = [str(case.get("case_id")) for case in cases if isinstance(case, dict)]
    excluded_case_ids = [str(case.get("case_id")) for case in excluded_cases if isinstance(case, dict)]
    duplicate_ids = sorted({case_id for case_id in case_ids if case_ids.count(case_id) > 1})
    coverage = sorted(set().union(*(_coverage_groups(case) for case in cases)) if cases else set())

    if dataset:
        if dataset.get("dataset_name") != "v0_scripted_skill_success_variations":
            failures.append(f"dataset_name must be v0_scripted_skill_success_variations, got {dataset.get('dataset_name')}")
        if dataset.get("skill_api_contract") != DEFAULT_CONTRACT:
            failures.append(f"dataset skill_api_contract must be {DEFAULT_CONTRACT}")
        if len(cases) < min_cases:
            failures.append(f"dataset case count {len(cases)} < required {min_cases}")
        if duplicate_ids:
            failures.append("dataset case IDs must be unique: " + ", ".join(duplicate_ids))
        if "baseline_replay" not in case_ids:
            failures.append("dataset must include baseline_replay positive control")
        if negative_control_id in case_ids:
            failures.append(f"dataset must exclude negative-control case {negative_control_id}")
        if negative_control_id not in excluded_case_ids:
            failures.append(f"dataset excluded_cases must record negative-control case {negative_control_id}")
        else:
            excluded_negative = next(
                (
                    case
                    for case in excluded_cases
                    if isinstance(case, dict) and str(case.get("case_id")) == negative_control_id
                ),
                {},
            )
            if excluded_negative.get("expected") != "fail_closed":
                failures.append(
                    f"excluded negative-control expected must be fail_closed, got {excluded_negative.get('expected')}"
                )
            if excluded_negative.get("classification") != "fail_closed":
                failures.append(
                    "excluded negative-control classification must be fail_closed, "
                    f"got {excluded_negative.get('classification')}"
                )
            if excluded_negative.get("reason") != "fail_closed_negative_control":
                failures.append(
                    "excluded negative-control reason must be fail_closed_negative_control, "
                    f"got {excluded_negative.get('reason')}"
                )
        negative_evidence = (
            dataset.get("negative_control_evidence")
            if isinstance(dataset.get("negative_control_evidence"), dict)
            else {}
        )
        if not negative_evidence:
            failures.append("dataset must record negative_control_evidence")
        else:
            if negative_evidence.get("case_id") != negative_control_id:
                failures.append(
                    "negative_control_evidence.case_id must match negative_control_id "
                    f"{negative_control_id}, got {negative_evidence.get('case_id')}"
                )
            if negative_evidence.get("expected") != "fail_closed":
                failures.append(
                    f"negative_control_evidence.expected must be fail_closed, got {negative_evidence.get('expected')}"
                )
            if negative_evidence.get("classification") != "fail_closed":
                failures.append(
                    "negative_control_evidence.classification must be fail_closed, "
                    f"got {negative_evidence.get('classification')}"
                )
            if negative_evidence.get("excluded_from_training_cases") is not True:
                failures.append("negative_control_evidence must mark excluded_from_training_cases=true")
            if negative_evidence.get("exclusion_reason") != "fail_closed_negative_control":
                failures.append("negative_control_evidence must preserve fail_closed_negative_control reason")
            trace_value = negative_evidence.get("trace_json")
            if not isinstance(trace_value, str) or not trace_value:
                failures.append("negative_control_evidence.trace_json must be present")
            else:
                trace_path = _resolve(Path(trace_value))
                if not trace_path.is_file():
                    failures.append(f"negative_control_evidence trace is missing: {_rel(trace_path)}")
                elif isinstance(negative_evidence.get("trace_sha256"), str):
                    actual = _sha256(trace_path)
                    if actual != negative_evidence.get("trace_sha256"):
                        failures.append("negative_control_evidence.trace_sha256 does not match trace_json")
        missing_coverage = sorted(REQUIRED_COVERAGE_GROUPS.difference(coverage))
        if missing_coverage:
            failures.append("dataset missing required coverage groups: " + ", ".join(missing_coverage))
        not_claims = dataset.get("not_claims")
        if not isinstance(not_claims, list) or "not learned policy" not in not_claims or "not sim-to-real" not in not_claims:
            failures.append("dataset must preserve not learned policy and not sim-to-real non-claims")
        source_manifest = dataset.get("source_manifest")
        if not isinstance(source_manifest, str) or not source_manifest:
            failures.append("dataset must record source_manifest")
        else:
            source_path = _resolve(Path(source_manifest))
            if not source_path.is_file():
                failures.append(f"dataset source_manifest is missing: {_rel(source_path)}")
            elif isinstance(dataset.get("source_manifest_sha256"), str):
                actual = _sha256(source_path)
                if actual != dataset.get("source_manifest_sha256"):
                    failures.append("dataset source_manifest_sha256 does not match source_manifest")

    for case in cases:
        if not isinstance(case, dict):
            failures.append("dataset cases must be objects")
            continue
        case_id = case.get("case_id")
        if case.get("classification") != "strict_success":
            failures.append(f"dataset case must be strict_success: {case_id}")
        if case.get("expected") == "fail_closed":
            failures.append(f"dataset case must not be expected fail_closed: {case_id}")
        failures.extend(_trace_check(case))

    if review:
        if review.get("status") != "READY_FOR_POLICY_API_REVIEW":
            failures.append(f"policy/API review status must be READY_FOR_POLICY_API_REVIEW, got {review.get('status')}")
        review_dataset = review.get("dataset") if isinstance(review.get("dataset"), dict) else {}
        if review_dataset.get("dataset") and review_dataset.get("dataset") != _rel(dataset_path):
            failures.append("policy/API review packet points at a different dataset path")
        review_case_ids = review_dataset.get("case_ids")
        if isinstance(review_case_ids, list) and sorted(map(str, review_case_ids)) != sorted(case_ids):
            failures.append("policy/API review case_ids do not match dataset case_ids")
        review_negative = (
            review_dataset.get("negative_control_evidence")
            if isinstance(review_dataset.get("negative_control_evidence"), dict)
            else {}
        )
        if not review_negative:
            failures.append("policy/API review must preserve negative_control_evidence")
        else:
            if review_negative.get("case_id") != negative_control_id:
                failures.append(
                    "policy/API review negative_control_evidence.case_id must match "
                    f"{negative_control_id}, got {review_negative.get('case_id')}"
                )
            if review_negative.get("classification") != "fail_closed":
                failures.append(
                    "policy/API review negative_control_evidence.classification must be fail_closed, "
                    f"got {review_negative.get('classification')}"
                )
            if review_negative.get("excluded_from_training_cases") is not True:
                failures.append("policy/API review must preserve negative control training exclusion")
        forbidden = set(review.get("proposed_api_boundary", {}).get("forbidden_outputs", []))
        if not {"raw_joint_targets", "direct_cartesian_servo_commands", "direct_force_commands"}.issubset(forbidden):
            failures.append("policy/API review must preserve raw joint, Cartesian servo, and force command bans")

    status = "PASS" if not failures else "BLOCKED"
    return {
        "audit_name": "v0_policy_dataset_audit",
        "status": status,
        "dataset": _rel(dataset_path),
        "review_packet": _rel(review_path),
        "dataset_case_count": len(cases),
        "dataset_case_ids": case_ids,
        "coverage_groups": coverage,
        "required_coverage_groups": sorted(REQUIRED_COVERAGE_GROUPS),
        "negative_control_id": negative_control_id,
        "ready_for_training": False,
        "failures": failures,
        "warnings": warnings,
        "not_claims": [
            "not trained policy",
            "not evaluated policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not a Brev or Isaac launcher",
        ],
    }


def _render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# V0 Policy Dataset Audit",
        "",
        f"- status: {audit['status']}",
        f"- ready_for_training: {audit['ready_for_training']}",
        f"- dataset: {audit['dataset']}",
        f"- review_packet: {audit['review_packet']}",
        f"- dataset_case_count: {audit['dataset_case_count']}",
        f"- coverage_groups: {', '.join(audit['coverage_groups'])}",
        "",
        "## Cases",
        "",
    ]
    lines.extend(f"- {case_id}" for case_id in audit["dataset_case_ids"])
    if audit["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in audit["failures"])
    if audit["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in audit["warnings"])
    lines.extend(["", "## Not Claims", ""])
    lines.extend(f"- {claim}" for claim in audit["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--review-packet", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--min-cases", type=int, default=5)
    parser.add_argument("--negative-control-id", default=DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--skip-review-packet", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    audit = build_audit(
        dataset_path=_resolve(args.dataset),
        review_path=_resolve(args.review_packet),
        min_cases=max(1, args.min_cases),
        negative_control_id=args.negative_control_id,
        require_review=not args.skip_review_packet,
    )
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-policy-dataset-audit] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(audit), encoding="utf-8")
        print(f"[v0-policy-dataset-audit] wrote Markdown: {_rel(output_md)}")

    print("[v0-policy-dataset-audit] facts=" + json.dumps(audit, indent=2, sort_keys=True))
    print("[v0-policy-dataset-audit] status=" + audit["status"])
    if audit["status"] == "PASS":
        return 0
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
