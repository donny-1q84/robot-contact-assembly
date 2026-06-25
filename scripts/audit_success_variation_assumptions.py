#!/usr/bin/env python3
"""Audit assumptions and metric sources for the success-variation batch.

This script is a read-only assumption-and-metric audit before paid compute or
post-batch promotion. It traces each critical success metric to concrete local
sources: the manifest, source trace checksum, classifier gates, result gate,
negative control, readiness packet, budget, and cleanup status.

It does not create, delete, copy to, or execute on Brev instances.
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
DEFAULT_RUN_PACKET = REPO_ROOT / "artifacts" / "analysis" / "success_variation_run_packet_2026-06-25.json"
DEFAULT_OUTPUT_JSON = REPO_ROOT / "artifacts" / "analysis" / "success_variation_assumption_audit_2026-06-25.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "artifacts" / "analysis" / "success_variation_assumption_audit_2026-06-25.md"
DEFAULT_NEGATIVE_CONTROL = result_gate.DEFAULT_NEGATIVE_CONTROL


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _resolve_repo_path(path: Path) -> Path:
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


def _trace_case(manifest: dict[str, Any], case_id: str) -> dict[str, Any] | None:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        return None
    for case in cases:
        if isinstance(case, dict) and case.get("case_id") == case_id:
            return case
    return None


def _source_trace_audit(manifest: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    source_value = manifest.get("source_trace_json")
    if not isinstance(source_value, str) or not source_value:
        blockers.append("manifest source_trace_json is missing")
        return {"status": "missing", "source_trace_json": source_value}
    source_path = _resolve_repo_path(Path(source_value))
    if not source_path.is_file():
        blockers.append(f"source trace is missing: {_rel(source_path)}")
        return {"status": "missing", "source_trace_json": _rel(source_path)}

    actual = _sha256(source_path)
    expected = manifest.get("source_trace_sha256")
    status = "pass" if actual == expected else "fail"
    if status != "pass":
        blockers.append("source trace sha256 does not match manifest source_trace_sha256")
    return {
        "status": status,
        "source_trace_json": _rel(source_path),
        "expected_sha256": expected,
        "actual_sha256": actual,
    }


def _metric_sources(
    manifest: dict[str, Any],
    classification: dict[str, Any],
    gate: dict[str, Any],
    run_packet: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    by_case = {
        str(result.get("case_id")): result
        for result in classification.get("results", [])
        if isinstance(result, dict)
    }
    readiness = run_packet.get("readiness") if isinstance(run_packet, dict) else None
    readiness_facts = readiness.get("facts") if isinstance(readiness, dict) else None
    readiness_blockers = readiness.get("blockers") if isinstance(readiness, dict) else None

    return [
        {
            "metric": "strict_success",
            "source": "scripts/classify_success_variation_results.py",
            "evidence_source": [
                "scripts/check_peg_in_hole_video_candidate.py",
                "scripts/check_final_contact_boundary_diagnostic.py",
                "scripts/audit_trace_frame_alignment.py",
            ],
            "current_evidence": {
                "baseline_replay": by_case.get("baseline_replay"),
                "strict_success_count": classification.get("summary", {}).get("strict_success_count"),
            },
            "interpretation": "semantic insertion success, not video existence and not learned policy",
        },
        {
            "metric": "negative_control_fail_closed",
            "source": "manifest case expected=fail_closed plus result gate",
            "evidence_source": "scripts/check_success_variation_batch_results.py",
            "current_evidence": by_case.get(DEFAULT_NEGATIVE_CONTROL),
            "interpretation": "large socket shift must not pass the same success metric",
        },
        {
            "metric": "planned_variation_coverage",
            "source": "manifest planned_trace_json entries and classifier missing labels",
            "evidence_source": "artifacts/manifests/success_trace_variations_2026-06-25.json",
            "current_evidence": {
                "case_count": classification.get("summary", {}).get("case_count"),
                "missing_count": classification.get("summary", {}).get("missing_count"),
                "strict_non_negative_variation_count": gate.get("summary", {}).get(
                    "strict_non_negative_variation_count"
                ),
            },
            "interpretation": "batch is incomplete until planned artifacts exist and classify cleanly",
        },
        {
            "metric": "paid_run_budget_and_cleanup",
            "source": "readiness packet from scripts/write_success_variation_run_packet.py",
            "evidence_source": "scripts/check_success_variation_batch_readiness.py",
            "current_evidence": {
                "readiness_status": readiness.get("status") if isinstance(readiness, dict) else None,
                "readiness_blockers": readiness_blockers,
                "estimated_cost": run_packet.get("estimated_cost") if isinstance(run_packet, dict) else None,
                "brev_safety_status": readiness_facts.get("brev_safety_status")
                if isinstance(readiness_facts, dict)
                else None,
            },
            "interpretation": "paid compute is allowed only after explicit budget, credit, lifecycle, and cleanup checks",
        },
        {
            "metric": "promotion_to_dataset_policy",
            "source": "result gate plus dataset prep gate",
            "evidence_source": [
                "scripts/check_success_variation_batch_results.py",
                "scripts/prepare_success_variation_dataset.py",
            ],
            "current_evidence": gate,
            "interpretation": "dataset/policy work is blocked until the result gate passes",
        },
    ]


def _build_audit(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    run_packet_path: Path | None,
    run_packet: dict[str, Any] | None,
    min_strict_successes: int,
    negative_control_id: str,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    source_trace = _source_trace_audit(manifest, blockers)
    classification = classifier.build_report(manifest, results_root=None)
    gate = result_gate._build_gate(
        classification,
        min_strict_successes=max(1, min_strict_successes),
        negative_control_id=negative_control_id,
        allow_near_success=False,
        allow_missing=False,
    )
    if not gate.get("pass"):
        blockers.extend(str(failure) for failure in gate.get("failures", []))

    remote_policy = manifest.get("remote_run_policy")
    if not isinstance(remote_policy, dict):
        blockers.append("manifest remote_run_policy is missing")
    elif remote_policy.get("requires_budget_watchdog_pullback_delete") is not True:
        blockers.append("manifest must require budget/watchdog/pullback/delete")

    negative_case = _trace_case(manifest, negative_control_id)
    if negative_case is None:
        blockers.append(f"negative control case missing: {negative_control_id}")
    elif negative_case.get("expected") != "fail_closed":
        blockers.append(f"{negative_control_id} must have expected=fail_closed")

    readiness = run_packet.get("readiness") if isinstance(run_packet, dict) else None
    if run_packet is None:
        warnings.append("run packet is missing; paid-run budget/cleanup facts are not included")
    elif isinstance(readiness, dict):
        if readiness.get("status") != "READY":
            blockers.extend(str(blocker) for blocker in (readiness.get("blockers") or []))
    else:
        blockers.append("run packet readiness object is missing")

    metric_sources = _metric_sources(manifest, classification, gate, run_packet)
    unique_blockers = list(dict.fromkeys(blockers))
    audit_status = "PASS" if not unique_blockers else "BLOCKED"
    return {
        "audit_name": "success_variation_assumption_metric_audit",
        "audit_status": audit_status,
        "manifest": _rel(manifest_path),
        "run_packet": _rel(run_packet_path) if run_packet_path is not None else None,
        "source_trace": source_trace,
        "classification_summary": classification.get("summary"),
        "result_gate": gate,
        "metric_sources": metric_sources,
        "blockers": unique_blockers,
        "warnings": warnings,
        "not_claims": [
            "not learned policy",
            "not sim-to-real",
            "not cross-robot-ready",
            "not a direct low-level VLM controller",
        ],
    }


def _render_markdown(audit: dict[str, Any]) -> str:
    rows = [
        "# Success Variation Assumption And Metric Audit",
        "",
        f"- audit_status: {audit['audit_status']}",
        f"- manifest: {audit['manifest']}",
        f"- run_packet: {audit.get('run_packet')}",
        f"- source_trace_status: {audit['source_trace'].get('status')}",
        "",
        "## Blockers",
        "",
    ]
    blockers = audit.get("blockers") or []
    if blockers:
        rows.extend(f"- {blocker}" for blocker in blockers)
    else:
        rows.append("- none")

    warnings = audit.get("warnings") or []
    rows.extend(["", "## Warnings", ""])
    if warnings:
        rows.extend(f"- {warning}" for warning in warnings)
    else:
        rows.append("- none")

    rows.extend(["", "## Metric Sources", ""])
    for item in audit["metric_sources"]:
        rows.extend(
            [
                f"### {item['metric']}",
                "",
                f"- source: {item['source']}",
                f"- evidence_source: {item['evidence_source']}",
                f"- interpretation: {item['interpretation']}",
                "",
            ]
        )

    rows.extend(["## Not Claims", ""])
    rows.extend(f"- {claim}" for claim in audit["not_claims"])
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?", default=DEFAULT_MANIFEST)
    parser.add_argument("--run-packet", type=Path, default=DEFAULT_RUN_PACKET)
    parser.add_argument("--min-strict-successes", type=int, default=5)
    parser.add_argument("--negative-control-id", default=DEFAULT_NEGATIVE_CONTROL)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    manifest_path = _resolve_repo_path(args.manifest)
    run_packet_path = _resolve_repo_path(args.run_packet) if args.run_packet is not None else None
    manifest = _load_json(manifest_path)
    run_packet = _load_json(run_packet_path) if run_packet_path is not None and run_packet_path.is_file() else None
    audit = _build_audit(
        manifest_path=manifest_path,
        manifest=manifest,
        run_packet_path=run_packet_path if run_packet is not None else None,
        run_packet=run_packet,
        min_strict_successes=args.min_strict_successes,
        negative_control_id=args.negative_control_id,
    )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf-8")
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(_render_markdown(audit), encoding="utf-8")

    print(f"[success-variation-assumption-audit] wrote JSON: {_rel(args.output_json)}")
    print(f"[success-variation-assumption-audit] wrote Markdown: {_rel(args.output_md)}")
    print(f"[success-variation-assumption-audit] status={audit['audit_status']}")
    if args.fail_on_blocked and audit["audit_status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
