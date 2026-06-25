#!/usr/bin/env python3
"""Plan the first V0 residual-policy experiment after policy/API review.

This is an offline planning gate. It reads a READY V0 policy/API review packet
and the scripted-skill dataset, then proposes a residual-policy experiment over
the scripted baseline. It does not train a policy, call Brev, start Isaac, call
ROS, or talk to a robot.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REVIEW = REPO_ROOT / "artifacts" / "reviews" / "v0_policy_api" / "review_packet.json"
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "plans" / "v0_residual_policy_experiment_plan.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "plans" / "v0_residual_policy_experiment_plan.md"


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


def _load_optional_json(path: Path, failures: list[str], label: str) -> dict[str, Any]:
    if not path.is_file():
        failures.append(f"{label} is missing: {_rel(path)}")
        return {}
    return _load_json(path)


def _dataset_case_ids(dataset: dict[str, Any]) -> list[str]:
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        return []
    return [str(case.get("case_id")) for case in cases if isinstance(case, dict)]


def build_plan(review_path: Path, dataset_path: Path) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    review = _load_optional_json(review_path, failures, "policy/API review packet")
    dataset = _load_optional_json(dataset_path, failures, "scripted-skill dataset")

    if review and review.get("status") != "READY_FOR_POLICY_API_REVIEW":
        failures.append(f"policy/API review packet must be READY_FOR_POLICY_API_REVIEW, got {review.get('status')}")
    dataset_name = dataset.get("dataset_name")
    if dataset and dataset_name != "v0_scripted_skill_success_variations":
        failures.append(f"dataset_name must be v0_scripted_skill_success_variations, got {dataset_name}")

    case_ids = _dataset_case_ids(dataset)
    if dataset and len(case_ids) < 5:
        failures.append(f"dataset must contain at least 5 strict-success cases, got {len(case_ids)}")
    if "socket_x_pos_25mm_negative_control" in case_ids:
        failures.append("negative-control case must not be included in the policy training dataset")

    forbidden = set(review.get("proposed_api_boundary", {}).get("forbidden_outputs", []))
    if review and not {"raw_joint_targets", "direct_cartesian_servo_commands", "direct_force_commands"}.issubset(
        forbidden
    ):
        failures.append("policy/API review must preserve raw joint, Cartesian servo, and force command bans")

    review_claims = set(review.get("not_claims", []))
    dataset_claims = set(dataset.get("not_claims", []))
    if review and "not sim-to-real" not in review_claims:
        failures.append("policy/API review must preserve not sim-to-real non-claim")
    if dataset and "not learned policy" not in dataset_claims:
        failures.append("dataset must preserve not learned policy non-claim")

    if review.get("skill", {}).get("controller_mode") == "scripted_success_baseline":
        warnings.append("first learned policy should be residual over scripted baseline, not a replacement controller")

    status = "READY_FOR_LOCAL_POLICY_EXPERIMENT_DESIGN" if not failures else "BLOCKED"
    return {
        "plan_name": "v0_residual_policy_experiment_plan",
        "status": status,
        "ready_for_training": False,
        "review_packet": _rel(review_path),
        "dataset": _rel(dataset_path),
        "dataset_case_count": len(case_ids),
        "dataset_case_ids": case_ids,
        "experiment": {
            "name": "v0_temporal_residual_policy_over_scripted_baseline",
            "policy_family": "residual_policy_over_scripted_baseline",
            "training_stage": "design_only",
            "inputs": [
                "validated task parameters",
                "scripted baseline action",
                "recent contact metrics",
                "previous action or residual",
                "success-variation case id",
            ],
            "outputs": [
                "bounded residual correction in the skill-controller action space",
                "semantic validation summary",
            ],
            "forbidden_outputs": [
                "raw_joint_targets",
                "direct_cartesian_servo_commands",
                "direct_force_commands",
                "language_to_raw_joint_control",
                "vlm_to_raw_joint_control",
            ],
        },
        "required_before_training": [
            "manual review of the V0 policy/API packet",
            "dataset provenance and case-balance audit",
            "negative-control exclusion check",
            "local no-GPU dry-run of feature extraction",
            "separate budget and cleanup plan before any remote training or Isaac evaluation",
        ],
        "blockers": failures,
        "warnings": warnings,
        "not_claims": [
            "not trained policy",
            "not evaluated policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not direct drop-in precision on another robot arm",
            "not a Brev or Isaac launcher",
        ],
    }


def _render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# V0 Residual Policy Experiment Plan",
        "",
        f"- status: {plan['status']}",
        f"- ready_for_training: {plan['ready_for_training']}",
        f"- review_packet: {plan['review_packet']}",
        f"- dataset: {plan['dataset']}",
        f"- dataset_case_count: {plan['dataset_case_count']}",
        "",
        "## Experiment",
        "",
        f"- name: {plan['experiment']['name']}",
        f"- policy_family: {plan['experiment']['policy_family']}",
        f"- training_stage: {plan['experiment']['training_stage']}",
        "- inputs: " + ", ".join(plan["experiment"]["inputs"]),
        "- outputs: " + ", ".join(plan["experiment"]["outputs"]),
        "- forbidden_outputs: " + ", ".join(plan["experiment"]["forbidden_outputs"]),
        "",
        "## Required Before Training",
        "",
    ]
    lines.extend(f"- {item}" for item in plan["required_before_training"])
    if plan["blockers"]:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {item}" for item in plan["blockers"])
    if plan["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in plan["warnings"])
    lines.extend(["", "## Not Claims", ""])
    lines.extend(f"- {item}" for item in plan["not_claims"])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-packet", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-output", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    plan = build_plan(_resolve(args.review_packet), _resolve(args.dataset))
    if not args.no_output:
        output_json = _resolve(args.output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[v0-policy-experiment-plan] wrote JSON: {_rel(output_json)}")
        output_md = _resolve(args.output_md)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(_render_markdown(plan), encoding="utf-8")
        print(f"[v0-policy-experiment-plan] wrote Markdown: {_rel(output_md)}")

    print("[v0-policy-experiment-plan] facts=" + json.dumps(plan, indent=2, sort_keys=True))
    print("[v0-policy-experiment-plan] status=" + plan["status"])
    if plan["status"] != "BLOCKED":
        return 0
    if args.fail_on_blocked:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
