#!/usr/bin/env python3
"""Prepare the V0 scripted-skill dataset from successful variation traces.

This is an offline/read-only gate. It refuses to write the dataset manifest
unless the success-variation result gate has already passed:

- baseline positive control is still strict_success;
- enough non-baseline, non-negative variation traces are strict_success;
- the deliberate negative control is fail_closed;
- planned trace artifacts are not missing.

The output is a dataset manifest for later policy/API work. It is not a
learned policy, not sim-to-real evidence, and not cross-robot-ready.
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
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_success_variation_batch_results as result_gate  # noqa: E402
import classify_success_variation_results as classifier  # noqa: E402


DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "datasets" / "v0_scripted_skill_success_variations"
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "manifest.json"
DEFAULT_OUTPUT_MD = DEFAULT_OUTPUT_DIR / "README.md"
DEFAULT_SKILL_CONTRACT = REPO_ROOT / "configs" / "v0_skill_api_contract.json"
DEFAULT_NEGATIVE_CONTROL = result_gate.DEFAULT_NEGATIVE_CONTROL


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


def _resolve_repo_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_cases_by_id(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        return {}
    by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("case_id")
        if isinstance(case_id, str):
            by_id[case_id] = case
    return by_id


def _dataset_case(result: dict[str, Any], manifest_case: dict[str, Any]) -> dict[str, Any]:
    trace_path = _resolve_repo_path(result.get("trace_json") if isinstance(result.get("trace_json"), str) else None)
    if trace_path is None or not trace_path.is_file():
        raise RuntimeError(f"strict_success case has no trace artifact: {result.get('case_id')}")
    return {
        "case_id": result.get("case_id"),
        "trace_json": _rel(trace_path),
        "trace_sha256": _sha256(trace_path),
        "expected": result.get("expected"),
        "classification": result.get("classification"),
        "seed": manifest_case.get("seed"),
        "socket_delta_m": manifest_case.get("socket_delta_m"),
        "reset_joint_noise_rad": manifest_case.get("reset_joint_noise_rad"),
        "rationale": manifest_case.get("rationale"),
        "gates": result.get("gates"),
        "metrics": result.get("metrics"),
        "boundary": result.get("boundary"),
        "frame_audit": result.get("frame_audit"),
    }


def _negative_control_evidence(
    result: dict[str, Any] | None,
    manifest_case: dict[str, Any],
    *,
    negative_control_id: str,
) -> dict[str, Any]:
    trace_value = result.get("trace_json") if isinstance(result, dict) else None
    trace_path = _resolve_repo_path(trace_value if isinstance(trace_value, str) else None)
    evidence = {
        "case_id": negative_control_id,
        "expected": result.get("expected") if isinstance(result, dict) else None,
        "classification": result.get("classification") if isinstance(result, dict) else None,
        "trace_json": _rel(trace_path) if trace_path is not None and trace_path.is_file() else trace_value,
        "trace_sha256": _sha256(trace_path) if trace_path is not None and trace_path.is_file() else None,
        "socket_delta_m": manifest_case.get("socket_delta_m"),
        "reset_joint_noise_rad": manifest_case.get("reset_joint_noise_rad"),
        "rationale": manifest_case.get("rationale"),
        "excluded_from_training_cases": True,
        "exclusion_reason": "fail_closed_negative_control",
        "gate_requirement": "must classify fail_closed before the dataset can be generated",
        "gates": result.get("gates") if isinstance(result, dict) else None,
        "metrics": result.get("metrics") if isinstance(result, dict) else None,
        "boundary": result.get("boundary") if isinstance(result, dict) else None,
        "frame_audit": result.get("frame_audit") if isinstance(result, dict) else None,
        "failure_reasons": result.get("failure_reasons") if isinstance(result, dict) else None,
    }
    return evidence


def _build_dataset(
    manifest: dict[str, Any],
    classification: dict[str, Any],
    gate: dict[str, Any],
    *,
    source_manifest_path: Path,
    negative_control_id: str,
) -> dict[str, Any]:
    manifest_cases = _manifest_cases_by_id(manifest)
    dataset_cases: list[dict[str, Any]] = []
    excluded_cases: list[dict[str, Any]] = []
    negative_control_result: dict[str, Any] | None = None

    for result in classification.get("results", []):
        if not isinstance(result, dict):
            continue
        case_id = str(result.get("case_id") or "")
        manifest_case = manifest_cases.get(case_id, {})
        classification_label = result.get("classification")
        expected = result.get("expected")
        if case_id == negative_control_id:
            negative_control_result = result
        if classification_label == "strict_success" and expected != "fail_closed":
            dataset_cases.append(_dataset_case(result, manifest_case))
        else:
            excluded_cases.append(
                {
                    "case_id": case_id,
                    "expected": expected,
                    "classification": classification_label,
                    "trace_json": result.get("trace_json"),
                    "reason": (
                        "fail_closed_negative_control"
                        if case_id == negative_control_id
                        else "not strict_success training case"
                    ),
                }
            )

    return {
        "dataset_name": "v0_scripted_skill_success_variations",
        "dataset_version": 1,
        "source_manifest": _rel(source_manifest_path),
        "source_manifest_sha256": _sha256(source_manifest_path),
        "source_trace_json": manifest.get("source_trace_json"),
        "source_trace_sha256": manifest.get("source_trace_sha256"),
        "task": manifest.get("task"),
        "skill_api_contract": _rel(DEFAULT_SKILL_CONTRACT),
        "selection_policy": {
            "requires_success_variation_result_gate_pass": True,
            "includes_baseline_positive_control": True,
            "includes_only_strict_success_non_negative_cases": True,
            "excludes_negative_control_id": negative_control_id,
            "requires_negative_control_fail_closed_evidence": True,
            "near_success_cases_excluded_by_default": True,
        },
        "negative_control_evidence": _negative_control_evidence(
            negative_control_result,
            manifest_cases.get(negative_control_id, {}),
            negative_control_id=negative_control_id,
        ),
        "gate_summary": gate.get("summary"),
        "classification_summary": classification.get("summary"),
        "cases": dataset_cases,
        "excluded_cases": excluded_cases,
        "not_claims": [
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not a direct low-level VLM controller",
        ],
        "next_stage": [
            "review this dataset manifest before training",
            "design a skill API around scripted_success_baseline_or_residual_policy",
            "start residual-policy work only after this dataset is reviewed",
            "keep ROS 2 and external robot adapters behind calibration and safety gates",
        ],
    }


def _render_markdown(dataset: dict[str, Any]) -> str:
    rows = [
        "# V0 Scripted Skill Success Variations Dataset",
        "",
        f"- dataset_name: {dataset['dataset_name']}",
        f"- source_manifest: {dataset['source_manifest']}",
        f"- skill_api_contract: {dataset['skill_api_contract']}",
        f"- task: {dataset.get('task')}",
        f"- case_count: {len(dataset['cases'])}",
        "",
        "## What This Is Not",
        "",
    ]
    rows.extend(f"- {claim}" for claim in dataset["not_claims"])
    rows.extend(
        [
            "",
            "## Cases",
            "",
            "| case | trace | seed | socket_delta_m | reset_noise_rad | best_lateral | best_axial | best_rot | max_contact |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in dataset["cases"]:
        metrics = case.get("metrics") if isinstance(case.get("metrics"), dict) else {}
        rows.append(
            "| {case_id} | {trace} | {seed} | {socket_delta} | {noise} | {lateral} | {axial} | {rot} | {contact} |".format(
                case_id=case.get("case_id"),
                trace=case.get("trace_json"),
                seed=case.get("seed"),
                socket_delta=case.get("socket_delta_m"),
                noise=case.get("reset_joint_noise_rad"),
                lateral=metrics.get("best_lateral", "-"),
                axial=metrics.get("best_axial", "-"),
                rot=metrics.get("best_rot", "-"),
                contact=metrics.get("max_contact_force", "-"),
            )
        )

    rows.extend(["", "## Excluded Cases", "", "| case | classification | reason |", "| --- | --- | --- |"])
    for case in dataset["excluded_cases"]:
        rows.append(
            "| {case_id} | {classification} | {reason} |".format(
                case_id=case.get("case_id"),
                classification=case.get("classification"),
                reason=case.get("reason"),
            )
        )

    rows.extend(["", "## Next Stage", ""])
    rows.extend(f"- {step}" for step in dataset["next_stage"])
    return "\n".join(rows) + "\n"


def _build_report(
    *,
    manifest_path: Path,
    gate: dict[str, Any],
    dataset: dict[str, Any] | None,
    output_json: Path,
    output_md: Path,
    writes_outputs: bool,
) -> dict[str, Any]:
    failures = gate.get("failures") if isinstance(gate.get("failures"), list) else []
    dataset_cases = dataset.get("cases") if isinstance(dataset, dict) and isinstance(dataset.get("cases"), list) else []
    excluded_cases = (
        dataset.get("excluded_cases")
        if isinstance(dataset, dict) and isinstance(dataset.get("excluded_cases"), list)
        else []
    )
    return {
        "status": "READY_FOR_POLICY_API_REVIEW" if gate.get("pass") else "BLOCKED",
        "result_gate_pass": bool(gate.get("pass")),
        "manifest": _rel(manifest_path),
        "output_json": _rel(output_json),
        "output_md": _rel(output_md),
        "case_count": len(dataset_cases),
        "excluded_case_count": len(excluded_cases),
        "failures": failures,
        "side_effects": {
            "writes_dataset_artifacts": bool(writes_outputs),
            "creates_paid_instance": False,
            "runs_remote_code": False,
            "starts_isaac": False,
            "calls_ros_or_robot": False,
        },
        "not_claims": [
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not hardware execution approval",
        ],
    }


def _resolve_input_path(path: Path) -> Path:
    path = path.expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--negative-control-id", default=DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--allow-near-success", action="store_true")
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--dry-run", action="store_true", help="Report readiness without writing dataset artifacts.")
    parser.add_argument("--no-output", action="store_true", help="Alias for --dry-run for status/report callers.")
    args = parser.parse_args()

    manifest_path = _resolve_input_path(args.manifest)
    results_root = args.results_root.resolve() if args.results_root is not None else None
    manifest = _load_json(manifest_path)
    classification = classifier.build_report(manifest, results_root=results_root)
    gate = result_gate._build_gate(
        classification,
        min_strict_successes=max(1, args.min_strict_successes),
        negative_control_id=args.negative_control_id,
        allow_near_success=args.allow_near_success,
        allow_missing=args.allow_missing,
    )

    no_write = bool(args.dry_run or args.no_output)
    dataset: dict[str, Any] | None = None
    if gate["pass"]:
        dataset = _build_dataset(
            manifest,
            classification,
            gate,
            source_manifest_path=manifest_path,
            negative_control_id=args.negative_control_id,
        )
    report = _build_report(
        manifest_path=manifest_path,
        gate=gate,
        dataset=dataset,
        output_json=args.output_json,
        output_md=args.output_md,
        writes_outputs=bool(gate["pass"] and not no_write),
    )

    print("[success-variation-dataset] facts=" + json.dumps(report, indent=2, sort_keys=True))
    print("[success-variation-dataset] result_gate_pass=" + str(gate["pass"]))
    if not gate["pass"]:
        print("[success-variation-dataset] BLOCKED")
        for failure in gate["failures"]:
            print(f"- {failure}")
        return 1

    if no_write:
        print("[success-variation-dataset] DRY_RUN")
        print("[success-variation-dataset] would not write dataset artifacts")
        print(f"[success-variation-dataset] cases={report['case_count']}")
        print("[success-variation-dataset] READY_FOR_POLICY_API_REVIEW")
        return 0

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(dataset, indent=2, sort_keys=True), encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(_render_markdown(dataset), encoding="utf-8")
    print(f"[success-variation-dataset] wrote JSON: {_rel(args.output_json)}")
    print(f"[success-variation-dataset] wrote Markdown: {_rel(args.output_md)}")
    print(f"[success-variation-dataset] cases={len(dataset['cases'])}")
    print("[success-variation-dataset] READY_FOR_POLICY_API_REVIEW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
