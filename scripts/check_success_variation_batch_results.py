#!/usr/bin/env python3
"""Gate success-variation batch results before learned-policy work.

This is an offline semantic result gate. It reads the success-variation
manifest plus pulled trace artifacts and enforces the post-batch promotion
contract:

- baseline positive control remains strict_success;
- planned non-negative variations have trace artifacts;
- at least N non-baseline, non-negative variations are strict_success;
- the deliberate negative control is fail_closed;
- no case is classified near_success unless explicitly allowed.
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

import classify_success_variation_results as classifier  # noqa: E402


DEFAULT_MANIFEST = REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
DEFAULT_NEGATIVE_CONTROL = "socket_x_pos_25mm_negative_control"


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


def _is_non_negative_variation(result: dict[str, Any], *, negative_control_id: str) -> bool:
    case_id = str(result.get("case_id") or "")
    if case_id in {"baseline_replay", negative_control_id}:
        return False
    return result.get("expected") != "fail_closed"


def _build_gate(
    report: dict[str, Any],
    *,
    min_strict_successes: int,
    negative_control_id: str,
    allow_near_success: bool,
    allow_missing: bool,
) -> dict[str, Any]:
    results = [result for result in report.get("results", []) if isinstance(result, dict)]
    by_case = {str(result.get("case_id") or ""): result for result in results}
    failures: list[str] = []

    baseline = by_case.get("baseline_replay")
    if not baseline:
        failures.append("missing baseline_replay positive control")
    elif baseline.get("classification") != "strict_success":
        failures.append(
            f"baseline_replay must be strict_success, got {baseline.get('classification')}"
        )

    negative = by_case.get(negative_control_id)
    if not negative:
        failures.append(f"missing negative control: {negative_control_id}")
    elif negative.get("expected") != "fail_closed":
        failures.append(
            f"{negative_control_id} must have expected=fail_closed, got {negative.get('expected')}"
        )
    elif negative.get("classification") != "fail_closed":
        failures.append(
            f"{negative_control_id} must be fail_closed, got {negative.get('classification')}"
        )

    non_negative_variations = [
        result for result in results if _is_non_negative_variation(result, negative_control_id=negative_control_id)
    ]
    strict_variations = [
        result for result in non_negative_variations if result.get("classification") == "strict_success"
    ]
    near_variations = [
        result for result in non_negative_variations if result.get("classification") == "near_success"
    ]
    missing_variations = [
        result
        for result in results
        if result.get("case_id") != "baseline_replay" and result.get("classification") == "missing"
    ]

    if len(strict_variations) < min_strict_successes:
        failures.append(
            "strict non-baseline, non-negative variation successes "
            f"{len(strict_variations)} < required {min_strict_successes}"
        )
    if near_variations and not allow_near_success:
        failures.append(
            "near_success cases are not accepted for promotion: "
            + ", ".join(str(result.get("case_id")) for result in near_variations)
        )
    if missing_variations and not allow_missing:
        failures.append(
            "missing planned trace artifacts: "
            + ", ".join(str(result.get("case_id")) for result in missing_variations)
        )

    return {
        "pass": not failures,
        "failures": failures,
        "summary": {
            "case_count": len(results),
            "strict_success_count": report.get("summary", {}).get("strict_success_count"),
            "near_success_count": report.get("summary", {}).get("near_success_count"),
            "fail_closed_count": report.get("summary", {}).get("fail_closed_count"),
            "missing_count": report.get("summary", {}).get("missing_count"),
            "strict_non_negative_variation_count": len(strict_variations),
            "near_non_negative_variation_count": len(near_variations),
            "missing_non_baseline_count": len(missing_variations),
            "min_strict_successes": min_strict_successes,
            "negative_control_id": negative_control_id,
            "negative_control_classification": negative.get("classification") if negative else None,
            "baseline_classification": baseline.get("classification") if baseline else None,
            "allow_near_success": allow_near_success,
            "allow_missing": allow_missing,
        },
        "strict_variation_cases": [result.get("case_id") for result in strict_variations],
        "near_variation_cases": [result.get("case_id") for result in near_variations],
        "missing_cases": [result.get("case_id") for result in missing_variations],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    parser.add_argument("--results-root", type=Path)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--negative-control-id", default=DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--allow-near-success", action="store_true")
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    manifest_path = args.manifest.expanduser()
    if not manifest_path.is_absolute():
        manifest_path = REPO_ROOT / manifest_path
    results_root = args.results_root.resolve() if args.results_root is not None else None

    manifest = _load_json(manifest_path)
    report = classifier.build_report(manifest, results_root=results_root)
    gate = _build_gate(
        report,
        min_strict_successes=max(1, args.min_strict_successes),
        negative_control_id=args.negative_control_id,
        allow_near_success=args.allow_near_success,
        allow_missing=args.allow_missing,
    )
    payload = {
        "manifest": _rel(manifest_path),
        "classification_summary": report.get("summary"),
        "gate": gate,
    }
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[success-variation-result-gate] wrote JSON: {_rel(args.output_json)}")

    print("[success-variation-result-gate] facts=" + json.dumps(gate["summary"], indent=2, sort_keys=True))
    if gate["pass"]:
        print("[success-variation-result-gate] PASS")
        return 0

    print("[success-variation-result-gate] FAIL")
    for failure in gate["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
