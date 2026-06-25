#!/usr/bin/env python3
"""Run the offline V0 policy-readiness pipeline after skill data is ready.

This is a local orchestration gate for the post-success-variation phase. It
runs the review, dataset audit, residual-policy planning, feature dry-run,
label-source audit, label dry-run, label dataset extraction, training preflight,
and training dry-run in fail-closed order.

It is not a paid run, not a Brev or Isaac launcher, not ROS integration, not a
hardware robot adapter, and not proof of direct drop-in precision on another
robot arm. It does not create, start, stop, delete, copy to, or execute on Brev
instances.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_REQUEST = REPO_ROOT / "configs" / "v0_skill_request.example.json"
DEFAULT_CONTRACT = REPO_ROOT / "configs" / "v0_skill_api_contract.json"
DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_DATASET = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations" / "manifest.json"
DEFAULT_REVIEW_JSON = REPO_ROOT / "artifacts" / "reviews" / "v0_policy_api" / "review_packet.json"
DEFAULT_REVIEW_MD = REPO_ROOT / "artifacts" / "reviews" / "v0_policy_api" / "README.md"
DEFAULT_DATASET_AUDIT_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_dataset_audit.json"
DEFAULT_DATASET_AUDIT_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_dataset_audit.md"
DEFAULT_EXPERIMENT_JSON = REPO_ROOT / "artifacts" / "plans" / "v0_residual_policy_experiment_plan.json"
DEFAULT_EXPERIMENT_MD = REPO_ROOT / "artifacts" / "plans" / "v0_residual_policy_experiment_plan.md"
DEFAULT_FEATURE_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_feature_dry_run.json"
DEFAULT_FEATURE_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_feature_dry_run.md"
DEFAULT_LABEL_SOURCE_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_source_audit.json"
DEFAULT_LABEL_SOURCE_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_source_audit.md"
DEFAULT_LABEL_DRY_RUN_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_dry_run.json"
DEFAULT_LABEL_DRY_RUN_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_label_dry_run.md"
DEFAULT_LABEL_JSONL = REPO_ROOT / "artifacts" / "datasets" / "v0_residual_policy_labels" / "labels.jsonl"
DEFAULT_LABEL_MANIFEST = REPO_ROOT / "artifacts" / "datasets" / "v0_residual_policy_labels" / "manifest.json"
DEFAULT_LABEL_MD = REPO_ROOT / "artifacts" / "datasets" / "v0_residual_policy_labels" / "README.md"
DEFAULT_PREFLIGHT_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_training_preflight.json"
DEFAULT_PREFLIGHT_MD = REPO_ROOT / "artifacts" / "analysis" / "v0_policy_training_preflight.md"
DEFAULT_TRAINING_PLAN_JSON = REPO_ROOT / "artifacts" / "analysis" / "v0_residual_policy_training_plan.json"
DEFAULT_CHECKPOINT = REPO_ROOT / "artifacts" / "policies" / "v0_residual_policy" / "model.pt"
DEFAULT_SUMMARY_JSON = REPO_ROOT / "artifacts" / "plans" / "v0_offline_policy_readiness_pipeline.json"
DEFAULT_SUMMARY_MD = REPO_ROOT / "artifacts" / "plans" / "v0_offline_policy_readiness_pipeline.md"

READY_STATUS = "READY_FOR_LOCAL_TRAINING_DRY_RUN"
DRY_RUN_STATUS = "DRY_RUN"
BLOCKED_STATUS = "BLOCKED"

NOT_CLAIMS = [
    "not a paid run",
    "not a Brev or Isaac launcher",
    "not ROS integration",
    "not hardware robot execution",
    "not a trained policy in dry-run mode",
    "not sim-to-real",
    "not cross-robot-ready",
    "not direct drop-in precision on another robot arm",
]


@dataclass(frozen=True)
class Step:
    step_id: str
    description: str
    command: list[str]


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


def _display_command(command: list[str]) -> str:
    return " ".join(command)


def _script(name: str) -> str:
    return str(SCRIPT_DIR / name)


def _build_steps(args: argparse.Namespace) -> list[Step]:
    request = _resolve(args.request)
    contract = _resolve(args.contract)
    manifest = _resolve(args.manifest)
    dataset = _resolve(args.dataset)
    review_json = _resolve(args.review_json)
    review_md = _resolve(args.review_md)
    dataset_audit_json = _resolve(args.dataset_audit_json)
    dataset_audit_md = _resolve(args.dataset_audit_md)
    experiment_json = _resolve(args.experiment_json)
    experiment_md = _resolve(args.experiment_md)
    feature_json = _resolve(args.feature_json)
    feature_md = _resolve(args.feature_md)
    label_source_json = _resolve(args.label_source_json)
    label_source_md = _resolve(args.label_source_md)
    label_dry_run_json = _resolve(args.label_dry_run_json)
    label_dry_run_md = _resolve(args.label_dry_run_md)
    label_jsonl = _resolve(args.label_jsonl)
    label_manifest = _resolve(args.label_manifest)
    label_md = _resolve(args.label_md)
    preflight_json = _resolve(args.training_preflight_json)
    preflight_md = _resolve(args.training_preflight_md)
    training_plan_json = _resolve(args.training_plan_json)
    checkpoint = _resolve(args.output_checkpoint)

    review_cmd = [
        sys.executable,
        _script("prepare_v0_policy_api_review.py"),
        str(request),
        "--contract",
        str(contract),
        "--manifest",
        str(manifest),
        "--dataset",
        str(dataset),
        "--output-json",
        str(review_json),
        "--output-md",
        str(review_md),
    ]
    if args.skip_phase2_contact_gate:
        review_cmd.append("--skip-phase2-contact-gate")

    return [
        Step(
            "policy_api_review",
            "prepare V0 policy/API review packet",
            review_cmd,
        ),
        Step(
            "policy_dataset_audit",
            "audit the scripted-skill dataset and review-packet alignment",
            [
                sys.executable,
                _script("audit_v0_policy_dataset.py"),
                "--dataset",
                str(dataset),
                "--review-packet",
                str(review_json),
                "--output-json",
                str(dataset_audit_json),
                "--output-md",
                str(dataset_audit_md),
                "--fail-on-blocked",
            ],
        ),
        Step(
            "policy_experiment_plan",
            "plan the first residual-policy experiment",
            [
                sys.executable,
                _script("plan_v0_policy_experiment.py"),
                "--review-packet",
                str(review_json),
                "--dataset",
                str(dataset),
                "--output-json",
                str(experiment_json),
                "--output-md",
                str(experiment_md),
                "--fail-on-blocked",
            ],
        ),
        Step(
            "policy_feature_dry_run",
            "preview feature extraction without generating targets",
            [
                sys.executable,
                _script("plan_v0_policy_feature_dry_run.py"),
                "--dataset",
                str(dataset),
                "--dataset-audit",
                str(dataset_audit_json),
                "--policy-experiment-plan",
                str(experiment_json),
                "--output-json",
                str(feature_json),
                "--output-md",
                str(feature_md),
                "--fail-on-blocked",
            ],
        ),
        Step(
            "policy_label_source_audit",
            "audit residual-label source fields and raw-command exclusions",
            [
                sys.executable,
                _script("audit_v0_policy_label_sources.py"),
                "--dataset",
                str(dataset),
                "--policy-feature-dry-run",
                str(feature_json),
                "--policy-experiment-plan",
                str(experiment_json),
                "--output-json",
                str(label_source_json),
                "--output-md",
                str(label_source_md),
                "--fail-on-blocked",
            ],
        ),
        Step(
            "policy_label_dry_run",
            "preview residual-label generation without writing a training dataset",
            [
                sys.executable,
                _script("plan_v0_policy_label_dry_run.py"),
                "--dataset",
                str(dataset),
                "--policy-feature-dry-run",
                str(feature_json),
                "--policy-label-source-audit",
                str(label_source_json),
                "--output-json",
                str(label_dry_run_json),
                "--output-md",
                str(label_dry_run_md),
                "--fail-on-blocked",
            ],
        ),
        Step(
            "policy_label_dataset",
            "extract the local residual-policy label dataset",
            [
                sys.executable,
                _script("extract_v0_policy_label_dataset.py"),
                "--dataset",
                str(dataset),
                "--policy-label-dry-run",
                str(label_dry_run_json),
                "--max-samples-per-case",
                str(args.max_samples_per_case),
                "--output-jsonl",
                str(label_jsonl),
                "--output-manifest",
                str(label_manifest),
                "--output-md",
                str(label_md),
                "--fail-on-blocked",
            ],
        ),
        Step(
            "policy_training_preflight",
            "check local residual-policy training preflight",
            [
                sys.executable,
                _script("check_v0_policy_training_preflight.py"),
                "--label-dataset-manifest",
                str(label_manifest),
                "--output-json",
                str(preflight_json),
                "--output-md",
                str(preflight_md),
                "--fail-on-blocked",
            ],
        ),
        Step(
            "policy_training_dry_run",
            "write the no-checkpoint residual-policy training dry-run plan",
            [
                sys.executable,
                _script("train_v0_residual_policy.py"),
                "--label-dataset-manifest",
                str(label_manifest),
                "--output-checkpoint",
                str(checkpoint),
                "--output-plan",
                str(training_plan_json),
                "--dry-run",
            ],
        ),
    ]


def _run_step(step: Step) -> dict[str, Any]:
    result = subprocess.run(
        step.command,
        cwd=str(REPO_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return {
        "step_id": step.step_id,
        "description": step.description,
        "command": step.command,
        "returncode": result.returncode,
        "status": "PASS" if result.returncode == 0 else BLOCKED_STATUS,
        "output": result.stdout,
    }


def _build_summary(
    *,
    status: str,
    steps: list[Step],
    results: list[dict[str, Any]],
    blocked_step: str | None,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "pipeline_name": "v0_offline_policy_readiness_pipeline",
        "status": status,
        "ready_for_local_training_dry_run": status == READY_STATUS,
        "dry_run": dry_run,
        "blocked_step": blocked_step,
        "step_count": len(steps),
        "steps": [
            {
                "step_id": step.step_id,
                "description": step.description,
                "command": _display_command(step.command),
                "status": next(
                    (result["status"] for result in results if result["step_id"] == step.step_id),
                    "NOT_RUN" if not dry_run else DRY_RUN_STATUS,
                ),
            }
            for step in steps
        ],
        "not_claims": NOT_CLAIMS,
        "next_action": (
            "finish_success_variation_batch_and_freeze_v0_skill_dataset"
            if status == BLOCKED_STATUS
            else "review_training_dry_run_before_any_real_local_training"
        ),
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    rows = [
        "# V0 Offline Policy Readiness Pipeline",
        "",
        f"- status: {summary['status']}",
        f"- ready_for_local_training_dry_run: {summary['ready_for_local_training_dry_run']}",
        f"- blocked_step: {summary['blocked_step']}",
        f"- dry_run: {summary['dry_run']}",
        "",
        "## Steps",
        "",
    ]
    rows.extend(
        f"- {step['step_id']}: {step['status']} - `{step['command']}`"
        for step in summary["steps"]
    )
    rows.extend(["", "## What This Is Not", ""])
    rows.extend(f"- {claim}" for claim in summary["not_claims"])
    rows.extend(["", "## Next Action", "", str(summary["next_action"])])
    return "\n".join(rows) + "\n"


def _write_summary(summary: dict[str, Any], output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_render_markdown(summary), encoding="utf-8")
    print(f"[v0-offline-policy-readiness] wrote JSON: {_rel(output_json)}")
    print(f"[v0-offline-policy-readiness] wrote Markdown: {_rel(output_md)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--review-json", type=Path, default=DEFAULT_REVIEW_JSON)
    parser.add_argument("--review-md", type=Path, default=DEFAULT_REVIEW_MD)
    parser.add_argument("--dataset-audit-json", type=Path, default=DEFAULT_DATASET_AUDIT_JSON)
    parser.add_argument("--dataset-audit-md", type=Path, default=DEFAULT_DATASET_AUDIT_MD)
    parser.add_argument("--experiment-json", type=Path, default=DEFAULT_EXPERIMENT_JSON)
    parser.add_argument("--experiment-md", type=Path, default=DEFAULT_EXPERIMENT_MD)
    parser.add_argument("--feature-json", type=Path, default=DEFAULT_FEATURE_JSON)
    parser.add_argument("--feature-md", type=Path, default=DEFAULT_FEATURE_MD)
    parser.add_argument("--label-source-json", type=Path, default=DEFAULT_LABEL_SOURCE_JSON)
    parser.add_argument("--label-source-md", type=Path, default=DEFAULT_LABEL_SOURCE_MD)
    parser.add_argument("--label-dry-run-json", type=Path, default=DEFAULT_LABEL_DRY_RUN_JSON)
    parser.add_argument("--label-dry-run-md", type=Path, default=DEFAULT_LABEL_DRY_RUN_MD)
    parser.add_argument("--label-jsonl", type=Path, default=DEFAULT_LABEL_JSONL)
    parser.add_argument("--label-manifest", type=Path, default=DEFAULT_LABEL_MANIFEST)
    parser.add_argument("--label-md", type=Path, default=DEFAULT_LABEL_MD)
    parser.add_argument("--training-preflight-json", type=Path, default=DEFAULT_PREFLIGHT_JSON)
    parser.add_argument("--training-preflight-md", type=Path, default=DEFAULT_PREFLIGHT_MD)
    parser.add_argument("--training-plan-json", type=Path, default=DEFAULT_TRAINING_PLAN_JSON)
    parser.add_argument("--output-checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY_JSON)
    parser.add_argument("--summary-md", type=Path, default=DEFAULT_SUMMARY_MD)
    parser.add_argument("--max-samples-per-case", type=int, default=50)
    parser.add_argument("--skip-phase2-contact-gate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-summary", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    steps = _build_steps(args)
    print("[v0-offline-policy-readiness] not_claims=" + "; ".join(NOT_CLAIMS))

    if args.dry_run:
        for step in steps:
            print(f"[v0-offline-policy-readiness] DRY_RUN {step.step_id}: {_display_command(step.command)}")
        summary = _build_summary(
            status=DRY_RUN_STATUS,
            steps=steps,
            results=[],
            blocked_step=None,
            dry_run=True,
        )
        if not args.no_summary:
            _write_summary(summary, _resolve(args.summary_json), _resolve(args.summary_md))
        print("[v0-offline-policy-readiness] status=DRY_RUN")
        return 0

    results: list[dict[str, Any]] = []
    blocked_step: str | None = None
    for step in steps:
        print(f"[v0-offline-policy-readiness] running {step.step_id}: {step.description}")
        result = _run_step(step)
        results.append(result)
        print(result["output"], end="" if result["output"].endswith("\n") else "\n")
        print(f"[v0-offline-policy-readiness] step={step.step_id} status={result['status']}")
        if result["returncode"] != 0:
            blocked_step = step.step_id
            break

    status = READY_STATUS if blocked_step is None else BLOCKED_STATUS
    summary = _build_summary(
        status=status,
        steps=steps,
        results=results,
        blocked_step=blocked_step,
        dry_run=False,
    )
    if not args.no_summary:
        _write_summary(summary, _resolve(args.summary_json), _resolve(args.summary_md))

    print(f"[v0-offline-policy-readiness] status={status}")
    if blocked_step:
        print(f"[v0-offline-policy-readiness] blocked_step={blocked_step}")
        print(f"[v0-offline-policy-readiness] next_action={summary['next_action']}")
    return 1 if status == BLOCKED_STATUS and args.fail_on_blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
