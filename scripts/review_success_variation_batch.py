#!/usr/bin/env python3
"""Write a post-run review for the success-variation batch.

This script is deliberately read-only with respect to Brev. It classifies local
trace artifacts, applies the post-batch promotion gate, optionally snapshots
Brev cleanup state, and writes a compact JSON/Markdown decision record.
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

import classify_success_variation_results as classifier  # noqa: E402
import check_success_variation_batch_results as result_gate  # noqa: E402


DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "artifacts" / "analysis" / "success_trace_variation_batch_review_2026-06-25.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "artifacts" / "analysis" / "success_trace_variation_batch_review_2026-06-25.md"
)


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


def _run_brev_safety() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["./scripts/brev_paid_safety_status.sh"],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "checked": True,
            "status": "timeout",
            "visible_instances": None,
            "exit_code": None,
            "output_tail": "",
        }

    status = None
    visible = None
    for line in result.stdout.splitlines():
        if line.startswith("[brev-safety] status="):
            status = line.split("=", 1)[1].strip()
        elif line.startswith("[brev-safety] visible_instances="):
            visible = line.split("=", 1)[1].strip()
    return {
        "checked": True,
        "status": status,
        "visible_instances": visible,
        "exit_code": result.returncode,
        "output_tail": result.stdout[-3000:],
    }


def _decision(gate: dict[str, Any], brev_safety: dict[str, Any]) -> str:
    if brev_safety.get("checked") and brev_safety.get("status") != "SAFE_NO_VISIBLE_PAID_INSTANCE":
        return "cleanup_required"
    if gate.get("pass"):
        return "ready_for_dataset_policy_preparation"
    return "continue_variation_batch_or_debug"


def _next_steps(decision: str, gate: dict[str, Any], brev_safety: dict[str, Any]) -> list[str]:
    if decision == "cleanup_required":
        return [
            "Confirm and delete any visible Brev instances before doing more project work.",
            "Rerun ./scripts/brev_paid_safety_status.sh until it reports SAFE_NO_VISIBLE_PAID_INSTANCE.",
        ]
    if decision == "ready_for_dataset_policy_preparation":
        return [
            "Freeze the successful variation traces as the first V0 scripted-skill dataset.",
            "Start dataset packaging and residual-policy/API design; do not claim sim-to-real readiness yet.",
        ]
    failures = gate.get("failures") or []
    steps = ["Do not start learned policy, VLM, ROS, or sim-to-real work yet."]
    if any("missing planned trace artifacts" in str(failure) for failure in failures):
        steps.append("Run or rerun the fixed-budget success-variation batch to fill missing planned traces.")
    if any("must be fail_closed" in str(failure) for failure in failures):
        steps.append("Inspect the negative-control trace/metric path before trusting generalization.")
    if any("strict non-baseline" in str(failure) for failure in failures):
        steps.append("Debug failed variation cases or revise the scripted stabilizer before policy work.")
    return steps


def _render_markdown(review: dict[str, Any]) -> str:
    rows = [
        "# Success Variation Batch Review",
        "",
        f"- decision: {review['decision']}",
        f"- manifest: {review['manifest']}",
        f"- result_gate_pass: {review['gate']['pass']}",
        f"- brev_safety_status: {review['brev_safety'].get('status')}",
        f"- brev_visible_instances: {review['brev_safety'].get('visible_instances')}",
        "",
        "## Gate Summary",
        "",
    ]
    for key, value in review["gate"]["summary"].items():
        rows.append(f"- {key}: {value}")

    failures = review["gate"].get("failures") or []
    rows.extend(["", "## Failures", ""])
    if failures:
        rows.extend(f"- {failure}" for failure in failures)
    else:
        rows.append("- none")

    rows.extend(["", "## Cases", "", "| case | expected | classification | trace |", "| --- | --- | --- | --- |"])
    for result in review["classification"]["results"]:
        rows.append(
            "| {case} | {expected} | {classification} | {trace} |".format(
                case=result.get("case_id"),
                expected=result.get("expected"),
                classification=result.get("classification"),
                trace=result.get("trace_json") or "-",
            )
        )

    rows.extend(["", "## Next Steps", ""])
    rows.extend(f"- {step}" for step in review["next_steps"])
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--negative-control-id", default=result_gate.DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--allow-near-success", action="store_true")
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--skip-brev-safety", action="store_true")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    manifest_path = args.manifest.expanduser()
    if not manifest_path.is_absolute():
        manifest_path = REPO_ROOT / manifest_path
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
    brev_safety = (
        {"checked": False, "status": "skipped", "visible_instances": None, "exit_code": None, "output_tail": ""}
        if args.skip_brev_safety
        else _run_brev_safety()
    )
    decision = _decision(gate, brev_safety)
    review = {
        "manifest": _rel(manifest_path),
        "classification": classification,
        "gate": gate,
        "brev_safety": brev_safety,
        "decision": decision,
        "next_steps": _next_steps(decision, gate, brev_safety),
    }

    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(review, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[success-variation-review] wrote JSON: {_rel(args.output_json)}")
    if args.output_md is not None:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(_render_markdown(review), encoding="utf-8")
        print(f"[success-variation-review] wrote Markdown: {_rel(args.output_md)}")

    print(f"[success-variation-review] decision={decision}")
    print(f"[success-variation-review] result_gate_pass={gate['pass']}")
    print(f"[success-variation-review] brev_safety_status={brev_safety.get('status')}")
    if args.fail_on_blocked and decision != "ready_for_dataset_policy_preparation":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
