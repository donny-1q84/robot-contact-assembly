#!/usr/bin/env python3
"""Print the current project status and next allowed action.

This is a read-only report. It intentionally does not call Brev, start Isaac,
or mutate files. Use the dedicated gate scripts for pass/fail enforcement:

- scripts/run_local_quality_checks.sh
- scripts/check_phase2_contact_gate.py
- scripts/paid_compute_preflight.sh
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
FAILING_STATUSES = {"BLOCKED", "STALE", "MISSING", "FAIL"}
BREV_LIFECYCLE_HOLD_FILE = Path(
    os.environ.get(
        "RCA_BREV_LIFECYCLE_HOLD_FILE",
        str(REPO_ROOT / "docs" / "brev_launchable_lifecycle_hold.md"),
    )
)
SUCCESS_VARIATION_MANIFEST = (
    REPO_ROOT / "artifacts" / "manifests" / "success_trace_variations_2026-06-25.json"
)
V0_POLICY_API_REVIEW_PACKET = (
    REPO_ROOT / "artifacts" / "reviews" / "v0_policy_api" / "review_packet.json"
)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return f"<git error: {result.stderr.strip()}>"
    return result.stdout.strip()


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def current_source_payload_sha256() -> str:
    result = run_script("python3", "scripts/source_payload_fingerprint.py")
    if result.returncode != 0:
        return "<unavailable>"
    return result.stdout.strip()


def current_source_payload_scope() -> str:
    result = run_script("python3", "scripts/source_payload_fingerprint.py", "--scope")
    if result.returncode != 0:
        return "<unavailable>"
    return result.stdout.strip()


def contact_gate_status() -> Check:
    result = run_script("python3", "scripts/check_phase2_contact_gate.py")
    if result.returncode == 0:
        pass_lines = [line for line in result.stdout.splitlines() if "PASS: validated" in line]
        detail = pass_lines[-1] if pass_lines else "Validated by scripts/check_phase2_contact_gate.py."
        return Check("Phase 2 contact gate", "PASS", detail)

    if "no candidate log exists yet" in result.stdout:
        detail = "No archived artifacts/launchable_logs/contact_physics_smoke.log exists."
    elif "source HEAD mismatch" in result.stdout or "source payload mismatch" in result.stdout:
        detail = "Only stale smoke logs exist; none references the current runtime source payload."
    elif "FAIL marker present" in result.stdout:
        detail = "Contact-smoke log contains FAIL markers."
    elif "missing source payload fingerprint" in result.stdout:
        detail = "Contact-smoke log exists but lacks source_payload_sha256 evidence."
    elif "missing required marker" in result.stdout:
        detail = "Contact-smoke log exists but lacks required PASS markers."
    else:
        detail = "No valid contact-smoke PASS log accepted by scripts/check_phase2_contact_gate.py."
    return Check("Phase 2 contact gate", "BLOCKED", detail)


def post_smoke_trace_status() -> Check:
    trace_root = REPO_ROOT / "artifacts" / "videos" / "trace_only"
    summaries = sorted(trace_root.glob("*/video_summary.json"), key=lambda path: path.stat().st_mtime)
    if not summaries:
        return Check(
            "Post-smoke insertion trace",
            "MISSING",
            "No post-smoke trace-only video_summary.json exists yet; regenerate one short scripted trace before route decisions.",
        )

    latest = summaries[-1]
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("Post-smoke insertion trace", "STALE", f"Latest trace summary is unreadable: {latest} ({exc})")

    success_step = data.get("success_step")
    final_success = float(data.get("final_success_rate") or 0.0)
    if success_step is not None or final_success > 0.0:
        return Check(
            "Post-smoke insertion trace",
            "PASS",
            f"Latest trace reports insertion success at {latest}: success_step={success_step}, final_success_rate={final_success:.3f}.",
        )

    best_lateral = data.get("best_lateral")
    best_axial = data.get("best_axial")
    best_rot = data.get("best_rot")
    max_contact = data.get("max_contact_force_magnitude")
    return Check(
        "Post-smoke insertion trace",
        "BLOCKED",
        "Latest trace exists but failed insertion; use it as controller/route evidence, not as a video success: "
        f"{latest} best_lateral={best_lateral} best_axial={best_axial} best_rot={best_rot} max_contact={max_contact}.",
    )


def success_variation_status() -> Check:
    if not SUCCESS_VARIATION_MANIFEST.is_file():
        return Check(
            "Success variation gate",
            "MISSING",
            f"Variation manifest is missing: {SUCCESS_VARIATION_MANIFEST}",
        )

    result = run_script(
        "python3",
        "scripts/check_success_variation_batch_results.py",
        str(SUCCESS_VARIATION_MANIFEST),
    )
    marker = "[success-variation-result-gate] facts="
    facts: dict[str, object] = {}
    if marker in result.stdout:
        facts_text = result.stdout.split(marker, 1)[1]
        try:
            facts = _json_prefix(facts_text)
        except (json.JSONDecodeError, ValueError):
            facts = {}

    baseline = facts.get("baseline_classification", "<unknown>")
    strict_non_negative = facts.get("strict_non_negative_variation_count", "<unknown>")
    min_strict = facts.get("min_strict_successes", "<unknown>")
    negative_id = facts.get("negative_control_id", "<unknown>")
    negative = facts.get("negative_control_classification", "<unknown>")
    missing = facts.get("missing_count", "<unknown>")

    detail = (
        f"manifest={SUCCESS_VARIATION_MANIFEST}; baseline={baseline}; "
        f"strict_non_negative_variations={strict_non_negative}/{min_strict}; "
        f"negative_control={negative_id}:{negative}; missing={missing}."
    )
    if result.returncode == 0:
        return Check("Success variation gate", "PASS", detail)
    return Check(
        "Success variation gate",
        "BLOCKED",
        detail
        + " Fill the planned trace-only batch before dataset, learned-policy, VLM, ROS, or external-arm claims.",
    )


def success_variation_dataset_prep_status() -> Check:
    result = run_script(
        "python3",
        "scripts/prepare_success_variation_dataset.py",
        str(SUCCESS_VARIATION_MANIFEST),
        "--no-output",
    )
    marker = "[success-variation-dataset] facts="
    if marker not in result.stdout:
        return Check(
            "V0 scripted-skill dataset prep",
            "FAIL",
            "Could not parse scripts/prepare_success_variation_dataset.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("V0 scripted-skill dataset prep", "FAIL", f"Dataset prep JSON parse failed: {exc}")

    status = "READY" if facts.get("status") == "READY_FOR_POLICY_API_REVIEW" else str(facts.get("status") or "BLOCKED")
    side_effects = facts.get("side_effects") if isinstance(facts.get("side_effects"), dict) else {}
    failures = facts.get("failures") if isinstance(facts.get("failures"), list) else []
    detail = (
        f"manifest={facts.get('manifest')}; result_gate_pass={facts.get('result_gate_pass')}; "
        f"case_count={facts.get('case_count')}; excluded_case_count={facts.get('excluded_case_count')}; "
        f"writes_dataset_artifacts={side_effects.get('writes_dataset_artifacts')}; "
        f"failures={len(failures)}; next_action="
        f"{'run_policy_api_review' if status == 'READY' else 'finish_success_variation_batch'}."
    )
    return Check("V0 scripted-skill dataset prep", status, detail)


def success_variation_recovery_plan_status() -> Check:
    result = run_script(
        "python3",
        "scripts/plan_success_variation_recovery_batch.py",
        str(SUCCESS_VARIATION_MANIFEST),
        "--no-output",
    )
    marker = "[success-variation-recovery] facts="
    if marker not in result.stdout:
        return Check(
            "Success variation recovery plan",
            "FAIL",
            "Could not parse scripts/plan_success_variation_recovery_batch.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("Success variation recovery plan", "FAIL", f"Recovery JSON parse failed: {exc}")

    raw_status = str(facts.get("status") or "BLOCKED")
    status = "READY" if raw_status in {"READY", "NOTHING_TO_RERUN"} else raw_status
    rerun_ids = facts.get("rerun_case_ids") if isinstance(facts.get("rerun_case_ids"), list) else []
    blocked_cases = facts.get("blocked_cases") if isinstance(facts.get("blocked_cases"), list) else []
    side_effects = facts.get("side_effects") if isinstance(facts.get("side_effects"), dict) else {}
    classification = facts.get("classification_summary") if isinstance(facts.get("classification_summary"), dict) else {}
    detail = (
        f"recovery_status={raw_status}; rerun_case_count={facts.get('rerun_case_count')}; "
        f"rerun_cases={','.join(str(case_id) for case_id in rerun_ids)}; "
        f"blocked_case_count={len(blocked_cases)}; missing={classification.get('missing_count')}; "
        f"negative_control_in_rerun={'socket_x_pos_25mm_negative_control' in rerun_ids}; "
        f"writes_recovery_artifacts={side_effects.get('writes_recovery_artifacts')}; "
        f"creates_paid_instance={side_effects.get('creates_paid_instance')}."
    )
    return Check("Success variation recovery plan", status, detail)


def success_variation_paid_lifecycle_preflight_status() -> Check:
    result = run_script(
        "python3",
        "scripts/check_success_variation_paid_lifecycle_preflight.py",
        "--no-output",
    )
    marker = "[success-variation-paid-preflight] facts="
    if marker not in result.stdout:
        return Check(
            "Success variation paid lifecycle preflight",
            "FAIL",
            "Could not parse scripts/check_success_variation_paid_lifecycle_preflight.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("Success variation paid lifecycle preflight", "FAIL", f"Preflight JSON parse failed: {exc}")

    status = str(facts.get("status") or "BLOCKED")
    blockers = facts.get("blockers") if isinstance(facts.get("blockers"), list) else []
    credit = facts.get("credit_evidence") if isinstance(facts.get("credit_evidence"), dict) else {}
    credit_blockers = credit.get("blockers") if isinstance(credit.get("blockers"), list) else []
    plan = facts.get("batch_plan_gate") if isinstance(facts.get("batch_plan_gate"), dict) else {}
    lifecycle_plan = facts.get("lifecycle_plan") if isinstance(facts.get("lifecycle_plan"), dict) else {}
    lifecycle_budget = lifecycle_plan.get("budget") if isinstance(lifecycle_plan.get("budget"), dict) else {}
    detail = (
        f"config={facts.get('config')}; credit={credit.get('status')}; "
        f"plan_exit={plan.get('exit_code')}; "
        f"watchdog_max_minutes={lifecycle_budget.get('watchdog_max_minutes')}; "
        f"estimated_max_cost_eur={lifecycle_budget.get('estimated_max_cost_eur')}; "
        f"blockers={len(blockers)}; "
        f"credit_blockers={len(credit_blockers)}; next_action={facts.get('next_action')}."
    )
    return Check("Success variation paid lifecycle preflight", status, detail)


def success_variation_pre_batch_assumption_audit_status() -> Check:
    result = run_script(
        "python3",
        "scripts/audit_success_variation_assumptions.py",
        str(SUCCESS_VARIATION_MANIFEST),
        "--phase",
        "pre-batch",
        "--run-packet",
        "artifacts/analysis/success_variation_run_packet_2026-06-25.json",
        "--no-output",
    )
    marker = "[success-variation-assumption-audit] facts="
    if marker not in result.stdout:
        return Check(
            "Success variation pre-batch assumption audit",
            "FAIL",
            "Could not parse scripts/audit_success_variation_assumptions.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check(
            "Success variation pre-batch assumption audit",
            "FAIL",
            f"Assumption audit JSON parse failed: {exc}",
        )

    audit_status = str(facts.get("audit_status") or "BLOCKED")
    blockers = facts.get("blockers") if isinstance(facts.get("blockers"), list) else []
    warnings = facts.get("warnings") if isinstance(facts.get("warnings"), list) else []
    source_trace = facts.get("source_trace") if isinstance(facts.get("source_trace"), dict) else {}
    classification = facts.get("classification_summary") if isinstance(facts.get("classification_summary"), dict) else {}
    detail = (
        f"audit_status={audit_status}; phase={facts.get('phase')}; "
        f"source_trace_status={source_trace.get('status')}; "
        f"missing={classification.get('missing_count')}; blockers={len(blockers)}; "
        f"warnings={len(warnings)}; run_packet={facts.get('run_packet')}."
    )
    status = "READY" if audit_status == "PASS" else "BLOCKED"
    return Check("Success variation pre-batch assumption audit", status, detail)


def brev_credit_review_status() -> Check:
    result = run_script("python3", "scripts/prepare_brev_credit_review.py", "--no-output")
    marker = "[brev-credit-review] facts="
    if marker not in result.stdout:
        return Check(
            "Brev UI credit review",
            "FAIL",
            "Could not parse scripts/prepare_brev_credit_review.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("Brev UI credit review", "FAIL", f"Brev credit review JSON parse failed: {exc}")

    packet_status = str(facts.get("status") or "BLOCKED")
    balance_preview = facts.get("balance_preview") if isinstance(facts.get("balance_preview"), dict) else {}
    side_effects = facts.get("side_effects") if isinstance(facts.get("side_effects"), dict) else {}
    preflight = facts.get("paid_lifecycle_preflight") if isinstance(facts.get("paid_lifecycle_preflight"), dict) else {}
    credit = preflight.get("credit_evidence") if isinstance(preflight.get("credit_evidence"), dict) else {}
    commands = facts.get("next_commands") if isinstance(facts.get("next_commands"), dict) else {}
    preview_credit_command = commands.get("preview_credit_evidence")
    write_command = commands.get("write_credit_evidence")
    preview_prepare_command = commands.get("preview_prepare_paid_batch")
    prepare_command = commands.get("prepare_paid_batch")
    detail = (
        f"packet_status={packet_status}; dashboard_url={facts.get('dashboard_url')}; "
        f"credit_evidence_path={facts.get('credit_evidence_path')}; "
        f"balance_preview_status={balance_preview.get('status')}; "
        f"credit_status={credit.get('status')}; budget_eur={facts.get('budget_eur')}; "
        f"writes_credit_evidence={side_effects.get('writes_credit_evidence')}; "
        f"creates_paid_instance={side_effects.get('creates_paid_instance')}; "
        f"preview_credit_command={' '.join(preview_credit_command) if isinstance(preview_credit_command, list) else '<missing>'}; "
        f"write_command={' '.join(write_command) if isinstance(write_command, list) else '<missing>'}; "
        f"preview_prepare_command={' '.join(preview_prepare_command) if isinstance(preview_prepare_command, list) else '<missing>'}; "
        f"prepare_command={' '.join(prepare_command) if isinstance(prepare_command, list) else '<missing>'}."
    )
    status = "READY" if packet_status == "READY_FOR_PAID_LIFECYCLE" else "BLOCKED"
    return Check("Brev UI credit review", status, detail)


def v0_language_instruction_suite_status() -> Check:
    result = run_script("python3", "scripts/check_v0_language_instruction_suite.py", "--no-output")
    marker = "[v0-language-suite] facts="
    if marker not in result.stdout:
        return Check(
            "V0 language instruction suite",
            "FAIL",
            "Could not parse scripts/check_v0_language_instruction_suite.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("V0 language instruction suite", "FAIL", f"Language suite JSON parse failed: {exc}")

    status = str(facts.get("status") or "FAIL")
    cases = facts.get("cases") if isinstance(facts.get("cases"), list) else []
    accepted_cases = sum(1 for case in cases if case.get("expected_status") == "PASS")
    rejected_cases = sum(1 for case in cases if case.get("expected_status") == "FAIL")
    not_claims = facts.get("not_claims") if isinstance(facts.get("not_claims"), list) else []
    detail = (
        f"suite={facts.get('suite')}; cases={facts.get('pass_count')}/{facts.get('case_count')}; "
        f"accepted_cases={accepted_cases}; rejected_cases={rejected_cases}; "
        f"not_cross_robot_ready={'not cross-robot-ready' in not_claims}."
    )
    return Check("V0 language instruction suite", status, detail)


def v0_language_skill_dry_run_status() -> Check:
    result = run_script(
        "python3",
        "scripts/run_v0_language_skill_dry_run.py",
        "insert the peg into the left socket",
        "--skip-phase2-contact-gate",
        "--no-output",
    )
    marker = "[v0-language-skill-dry-run] facts="
    if marker not in result.stdout:
        return Check(
            "V0 language skill dry-run",
            "FAIL",
            "Could not parse scripts/run_v0_language_skill_dry_run.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("V0 language skill dry-run", "FAIL", f"Language dry-run JSON parse failed: {exc}")

    raw_status = str(facts.get("status") or "BLOCKED")
    status = "READY" if raw_status == "READY_FOR_SKILL_EXECUTION_REVIEW" else raw_status
    blockers = facts.get("blockers") if isinstance(facts.get("blockers"), list) else []
    surface = facts.get("execution_surface") if isinstance(facts.get("execution_surface"), dict) else {}
    not_claims = facts.get("not_claims") if isinstance(facts.get("not_claims"), list) else []
    detail = (
        f"instruction={facts.get('instruction')!r}; "
        f"request_planner={facts.get('request_planner_status')}; "
        f"request_validation={facts.get('request_validation_status')}; "
        f"execution_plan={facts.get('execution_plan_status')}; "
        f"ready_for_execution={facts.get('ready_for_execution')}; "
        f"allowed_command_boundary={surface.get('allowed_command_boundary')}; "
        f"blockers={len(blockers)}; blocked_next_action={facts.get('blocked_next_action')}; "
        f"not_cross_robot_ready={'not cross-robot-ready' in not_claims}."
    )
    return Check("V0 language skill dry-run", status, detail)


def v0_skill_readiness_status() -> Check:
    result = run_script(
        "python3",
        "scripts/check_v0_skill_readiness.py",
        "--skip-phase2-contact-gate",
    )
    marker = "[v0-skill-readiness] facts="
    if marker not in result.stdout:
        return Check(
            "V0 skill readiness",
            "FAIL",
            "Could not parse scripts/check_v0_skill_readiness.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("V0 skill readiness", "FAIL", f"Readiness JSON parse failed: {exc}")

    status = str(facts.get("status") or "BLOCKED")
    next_action = facts.get("next_action", "<unknown>")
    blockers = facts.get("blockers") if isinstance(facts.get("blockers"), list) else []
    detail = (
        f"request={facts.get('request')}; dataset={facts.get('dataset')}; "
        f"next_action={next_action}; blockers={len(blockers)}. "
        "Phase 2 is checked separately in this report."
    )
    return Check("V0 skill readiness", status, detail)


def v0_policy_api_review_status() -> Check:
    readiness = v0_skill_readiness_status()
    if readiness.status == "FAIL":
        return Check(
            "V0 policy/API review packet",
            "FAIL",
            "Cannot evaluate policy/API review readiness because the V0 skill readiness check failed. "
            + readiness.detail,
        )
    if readiness.status != "READY":
        return Check(
            "V0 policy/API review packet",
            "BLOCKED",
            "Blocked until V0 skill readiness is READY; "
            "scripts/prepare_v0_policy_api_review.py must not write artifacts yet. "
            + readiness.detail,
        )
    if not V0_POLICY_API_REVIEW_PACKET.is_file():
        return Check(
            "V0 policy/API review packet",
            "MISSING",
            f"V0 skill readiness is READY but review packet is missing: {V0_POLICY_API_REVIEW_PACKET}",
        )
    return Check(
        "V0 policy/API review packet",
        "READY",
        f"Review packet exists and is gated by V0 skill readiness: {V0_POLICY_API_REVIEW_PACKET}",
    )


def v0_offline_policy_readiness_pipeline_status() -> Check:
    result = run_script(
        "python3",
        "scripts/run_v0_offline_policy_readiness_pipeline.py",
        "--skip-phase2-contact-gate",
        "--no-summary",
        "--no-output",
    )
    marker = "[v0-offline-policy-readiness] facts="
    if marker not in result.stdout:
        return Check(
            "V0 offline policy-readiness pipeline",
            "FAIL",
            "Could not parse scripts/run_v0_offline_policy_readiness_pipeline.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("V0 offline policy-readiness pipeline", "FAIL", f"Pipeline JSON parse failed: {exc}")

    raw_status = str(facts.get("status") or "BLOCKED")
    status = "READY" if raw_status == "READY_FOR_LOCAL_TRAINING_DRY_RUN" else raw_status
    steps = facts.get("steps") if isinstance(facts.get("steps"), list) else []
    run_steps = [step for step in steps if isinstance(step, dict) and step.get("status") not in {"NOT_RUN", "DRY_RUN"}]
    side_effects = facts.get("side_effects") if isinstance(facts.get("side_effects"), dict) else {}
    not_claims = facts.get("not_claims") if isinstance(facts.get("not_claims"), list) else []
    detail = (
        f"pipeline_status={raw_status}; blocked_step={facts.get('blocked_step')}; "
        f"ready_for_local_training_dry_run={facts.get('ready_for_local_training_dry_run')}; "
        f"steps_run={len(run_steps)}/{facts.get('step_count')}; no_output={facts.get('no_output')}; "
        f"writes_pipeline_summary={side_effects.get('writes_pipeline_summary')}; "
        f"writes_policy_artifacts={side_effects.get('writes_review_dataset_plan_or_training_artifacts')}; "
        f"not_paid_run={'not a paid run' in not_claims}; next_action={facts.get('next_action')}."
    )
    return Check("V0 offline policy-readiness pipeline", status, detail)


def v0_policy_training_preflight_status() -> Check:
    result = run_script("python3", "scripts/check_v0_policy_training_preflight.py", "--no-output")
    marker = "[v0-policy-training-preflight] facts="
    if marker not in result.stdout:
        return Check(
            "V0 policy training preflight",
            "FAIL",
            "Could not parse scripts/check_v0_policy_training_preflight.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("V0 policy training preflight", "FAIL", f"Training preflight JSON parse failed: {exc}")

    status = str(facts.get("status") or "BLOCKED")
    blockers = facts.get("blockers") if isinstance(facts.get("blockers"), list) else []
    detail = (
        f"label_dataset_manifest={facts.get('label_dataset_manifest')}; "
        f"training_script_status={facts.get('training_script_status')}; "
        f"ready_for_training={facts.get('ready_for_training')}; "
        f"ready_for_training_launch={facts.get('ready_for_training_launch')}; "
        f"blockers={len(blockers)}."
    )
    return Check("V0 policy training preflight", status, detail)


def v0_residual_policy_eval_status() -> Check:
    result = run_script("python3", "scripts/evaluate_v0_residual_policy.py", "--dry-run", "--no-output")
    marker = "[v0-residual-policy-eval] facts="
    if marker not in result.stdout:
        return Check(
            "V0 residual policy eval",
            "FAIL",
            "Could not parse scripts/evaluate_v0_residual_policy.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("V0 residual policy eval", "FAIL", f"Residual eval JSON parse failed: {exc}")

    status = str(facts.get("status") or "BLOCKED")
    blockers = facts.get("blockers") if isinstance(facts.get("blockers"), list) else []
    detail = (
        f"metadata={facts.get('metadata')}; checkpoint={facts.get('checkpoint')}; "
        f"ready_for_supervised_eval={facts.get('ready_for_supervised_eval')}; "
        f"sample_count={facts.get('sample_count')}; blockers={len(blockers)}."
    )
    return Check("V0 residual policy eval", "READY" if status != "BLOCKED" else "BLOCKED", detail)


def v0_policy_promotion_gate_status() -> Check:
    result = run_script(
        "python3",
        "scripts/check_v0_policy_promotion_gate.py",
        "--skip-phase2-contact-gate",
        "--no-output",
    )
    marker = "[v0-policy-promotion-gate] facts="
    if marker not in result.stdout:
        return Check(
            "V0 policy promotion gate",
            "FAIL",
            "Could not parse scripts/check_v0_policy_promotion_gate.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("V0 policy promotion gate", "FAIL", f"Policy promotion JSON parse failed: {exc}")

    status = str(facts.get("status") or "BLOCKED")
    blockers = facts.get("blockers") if isinstance(facts.get("blockers"), list) else []
    supervised = facts.get("supervised_eval") if isinstance(facts.get("supervised_eval"), dict) else {}
    isaac_eval = facts.get("isaac_closed_loop_eval") if isinstance(facts.get("isaac_closed_loop_eval"), dict) else {}
    detail = (
        f"skill_readiness={facts.get('skill_readiness_status')}; "
        f"supervised_eval={supervised.get('status')}; "
        f"isaac_closed_loop_eval={isaac_eval.get('status')}; "
        f"ready_for_policy_promotion_review={facts.get('ready_for_policy_promotion_review')}; "
        f"ready_for_external_robot={facts.get('ready_for_external_robot')}; "
        f"blockers={len(blockers)}; next_action={facts.get('next_action')}."
    )
    return Check("V0 policy promotion gate", "READY" if status != "BLOCKED" else "BLOCKED", detail)


def external_robot_adapter_status() -> Check:
    result = run_script("python3", "scripts/check_v0_robot_adapter_contract.py")
    marker = "[v0-robot-adapter] facts="
    if marker not in result.stdout:
        return Check(
            "External robot adapter",
            "FAIL",
            "Could not parse scripts/check_v0_robot_adapter_contract.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("External robot adapter", "FAIL", f"Adapter JSON parse failed: {exc}")

    status = str(facts.get("status") or "BLOCKED")
    target = facts.get("target_robot") if isinstance(facts.get("target_robot"), dict) else {}
    blockers = facts.get("blockers") if isinstance(facts.get("blockers"), list) else []
    detail = (
        f"adapter={facts.get('adapter')}; robot_id={target.get('robot_id')}; "
        f"ready_for_external_robot={facts.get('ready_for_external_robot')}; "
        f"blockers={len(blockers)}; next_action={facts.get('next_action')}."
    )
    return Check("External robot adapter", status, detail)


def cross_robot_portability_status() -> Check:
    result = run_script(
        "python3",
        "scripts/check_v0_portability_boundary.py",
        "--skip-phase2-contact-gate",
    )
    marker = "[v0-portability-boundary] facts="
    if marker not in result.stdout:
        return Check(
            "Cross-robot portability",
            "FAIL",
            "Could not parse scripts/check_v0_portability_boundary.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("Cross-robot portability", "FAIL", f"Portability JSON parse failed: {exc}")

    status = str(facts.get("status") or "BLOCKED")
    blockers = facts.get("blockers") if isinstance(facts.get("blockers"), list) else []
    detail = (
        f"readiness_label={facts.get('readiness_label')}; "
        f"universal_drop_in_ready={facts.get('universal_drop_in_ready')}; "
        f"target_robot_id={facts.get('target_robot_id')}; "
        f"skill_readiness={facts.get('skill_readiness_status')}; "
        f"adapter={facts.get('adapter_status')}; "
        f"blockers={len(blockers)}; next_action={facts.get('next_action')}."
    )
    return Check("Cross-robot portability", status, detail)


def v0_portability_review_packet_status() -> Check:
    result = run_script(
        "python3",
        "scripts/prepare_v0_portability_review.py",
        "--skip-phase2-contact-gate",
        "--no-output",
    )
    marker = "[v0-portability-review] facts="
    if marker not in result.stdout:
        return Check(
            "V0 portability review packet",
            "FAIL",
            "Could not parse scripts/prepare_v0_portability_review.py output.",
        )
    try:
        facts = _json_prefix(result.stdout.split(marker, 1)[1])
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("V0 portability review packet", "FAIL", f"Portability review JSON parse failed: {exc}")

    status = str(facts.get("status") or "BLOCKED")
    summary = facts.get("gate_summary") if isinstance(facts.get("gate_summary"), dict) else {}
    blockers = facts.get("current_blockers") if isinstance(facts.get("current_blockers"), list) else []
    target_preview = facts.get("target_adapter_preview") if isinstance(facts.get("target_adapter_preview"), dict) else {}
    workplan = facts.get("adapter_workplan") if isinstance(facts.get("adapter_workplan"), dict) else {}
    evidence_groups = (
        workplan.get("required_evidence_groups")
        if isinstance(workplan.get("required_evidence_groups"), dict)
        else {}
    )
    detail = (
        f"readiness_label={facts.get('readiness_label')}; "
        f"direct_drop_in_answer={facts.get('direct_drop_in_answer')}; "
        f"named_robot_ready={facts.get('named_robot_ready')}; "
        f"universal_drop_in_ready={facts.get('universal_drop_in_ready')}; "
        f"workplan_status={workplan.get('status')}; "
        f"workplan_direct_drop_in={workplan.get('direct_drop_in_answer')}; "
        f"workplan_skill_blockers={workplan.get('current_skill_blocker_count')}; "
        f"workplan_adapter_blockers={workplan.get('current_adapter_blocker_count')}; "
        f"workplan_evidence_groups={len(evidence_groups)}; "
        f"target_adapter_preview={target_preview.get('status')}; "
        f"target_adapter_blockers={target_preview.get('blocker_count')}; "
        f"skill_readiness={summary.get('skill_readiness_status')}; "
        f"adapter={summary.get('adapter_status')}; "
        f"blockers={len(blockers)}; next_action={summary.get('next_action')}."
    )
    return Check("V0 portability review packet", status, detail)


def _json_prefix(text: str) -> dict:
    decoder = json.JSONDecoder()
    value, _ = decoder.raw_decode(text.lstrip())
    if not isinstance(value, dict):
        raise ValueError("JSON prefix is not an object")
    return value


def action_semantics_probe_status() -> Check:
    trace_root = REPO_ROOT / "artifacts" / "videos" / "trace_only"
    traces = sorted(trace_root.glob("*/video_trace.json"), key=lambda path: path.stat().st_mtime)
    for trace in reversed(traces):
        try:
            trace_data = json.loads(trace.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = trace_data.get("steps") if isinstance(trace_data, dict) else trace_data
        if not isinstance(rows, list):
            continue
        if not any(
            isinstance(row, dict)
            and (row.get("phase") == "action-semantics-probe" or row.get("action_semantics_probe"))
            for row in rows
        ):
            continue

        log = trace.with_name("action_response_check.log")
        if log.is_file():
            try:
                data = _json_prefix(log.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                return Check("Action semantics probe", "STALE", f"Latest probe log is unreadable: {log} ({exc})")
        else:
            result = run_script("python3", "scripts/check_scripted_action_response_trace.py", str(trace))
            try:
                data = _json_prefix(result.stdout)
            except (json.JSONDecodeError, ValueError) as exc:
                return Check("Action semantics probe", "STALE", f"Could not parse action-response output for {trace}: {exc}")

        worst = data.get("worst") if isinstance(data.get("worst"), dict) else {}
        command_delta = worst.get("command_delta")
        actual_delta = worst.get("actual_delta")
        min_cosine = data.get("min_cosine")
        bad_steps = data.get("bad_steps")
        steps_assessed = data.get("steps_assessed")
        detail = (
            f"Latest action-semantics probe: {trace}; bad_steps={bad_steps}/{steps_assessed}, "
            f"min_cosine={min_cosine}, command_delta={command_delta}, actual_delta={actual_delta}."
        )
        if data.get("pass"):
            return Check("Action semantics probe", "PASS", detail)
        return Check("Action semantics probe", "BLOCKED", detail)

    return Check(
        "Action semantics probe",
        "MISSING",
        "No action-semantics-probe trace exists yet; do not infer controller semantics from insertion traces alone.",
    )


def local_policy_status() -> Check:
    required_files = (
        "scripts/run_local_quality_checks.sh",
        "scripts/check_contact_physics_wiring.py",
        "scripts/check_phase2_contact_gate.py",
        "scripts/paid_compute_preflight.sh",
        "scripts/prepare_contact_smoke_run.sh",
        "scripts/check_project_policy_compliance.py",
    )
    missing = [path for path in required_files if not (REPO_ROOT / path).is_file()]
    if missing:
        return Check("Local gates", "BLOCKED", "Missing gate file(s): " + ", ".join(missing))
    return Check(
        "Local gates",
        "READY",
        "Gate scripts are present; run ./scripts/run_local_quality_checks.sh for enforcement.",
    )


def historical_doc_status() -> Check:
    markers = {
        "docs/phase2_cv_summary.md": "Superseded by 2026-06-18 Audit",
        "docs/phase2_il_contact_policy_plan.md": "Blocked by Contact-Physics Gate",
        "docs/aws_isaac_launchable_runbook.md": "Contact-Smoke Only",
    }
    missing: list[str] = []
    for rel_path, marker in markers.items():
        path = REPO_ROOT / rel_path
        if not path.is_file() or marker not in path.read_text(encoding="utf-8", errors="replace"):
            missing.append(f"{rel_path}:{marker}")
    if missing:
        return Check("Historical docs", "BLOCKED", "Missing current-state marker(s): " + ", ".join(missing))
    return Check("Historical docs", "READY", "Old Phase 2 docs are marked as historical/superseded.")


def tracked_generated_metadata_status() -> Check:
    output = run_git("ls-files", "*egg-info*")
    existing = []
    for rel_path in output.splitlines():
        if rel_path and (REPO_ROOT / rel_path).exists():
            existing.append(rel_path)
    if existing:
        return Check("Generated metadata", "BLOCKED", "Tracked egg-info files still exist: " + ", ".join(existing))
    return Check("Generated metadata", "READY", "No existing tracked egg-info files remain.")


def brev_lifecycle_hold_status() -> Check:
    if BREV_LIFECYCLE_HOLD_FILE.is_file():
        return Check(
            "Brev lifecycle hold",
            "BLOCKED",
            f"Active hold file requires service recovery or RCA_ACK_BREV_LIFECYCLE_RISK=1 before any paid retry: {BREV_LIFECYCLE_HOLD_FILE}",
        )
    return Check("Brev lifecycle hold", "READY", "No local Brev/Launchable lifecycle hold file is active.")


def latest_contact_smoke_bundle_status() -> Check:
    bundle_dir = Path(os.environ.get("RCA_LAUNCHABLE_BUNDLE_DIR", REPO_ROOT / "artifacts" / "launchable"))
    bundles = sorted(bundle_dir.glob("robot-contact-assembly-contact-smoke-*.tar.gz"))
    if not bundles:
        return Check("Contact-smoke bundle", "MISSING", "No local contact-smoke bundle exists yet.")

    latest = max(bundles, key=lambda path: path.stat().st_mtime)
    result = subprocess.run(
        [
            "tar",
            "-xOzf",
            str(latest),
            "robot-contact-assembly/.rca_launchable_source_manifest.txt",
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return Check("Contact-smoke bundle", "STALE", f"Latest bundle has no readable source manifest: {latest}")

    manifest: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        manifest[key] = value

    current_payload = current_source_payload_sha256()
    current_scope = current_source_payload_scope()
    bundle_scope = manifest.get("source_payload_scope", "")
    if bundle_scope != current_scope:
        return Check(
            "Contact-smoke bundle",
            "STALE",
            f"Latest bundle scope {bundle_scope or '<missing>'} does not match current {current_scope}: {latest}",
        )
    bundle_payload = manifest.get("source_payload_sha256", "")
    if bundle_payload != current_payload:
        return Check(
            "Contact-smoke bundle",
            "STALE",
            f"Latest bundle payload {bundle_payload or '<missing>'} does not match current {current_payload}: {latest}",
        )
    return Check("Contact-smoke bundle", "READY", f"Latest bundle matches current runtime payload scope/hash: {latest}")


def dirty_tree_status() -> Check:
    status = run_git("status", "--short")
    if status:
        count = len(status.splitlines())
        return Check("Git worktree", "DIRTY", f"{count} changed path(s); review before committing.")
    return Check("Git worktree", "CLEAN", "No uncommitted changes.")


def checks() -> list[Check]:
    return [
        dirty_tree_status(),
        local_policy_status(),
        brev_lifecycle_hold_status(),
        latest_contact_smoke_bundle_status(),
        contact_gate_status(),
        post_smoke_trace_status(),
        success_variation_status(),
        success_variation_recovery_plan_status(),
        success_variation_dataset_prep_status(),
        success_variation_pre_batch_assumption_audit_status(),
        success_variation_paid_lifecycle_preflight_status(),
        brev_credit_review_status(),
        v0_language_instruction_suite_status(),
        v0_language_skill_dry_run_status(),
        v0_skill_readiness_status(),
        v0_policy_api_review_status(),
        v0_offline_policy_readiness_pipeline_status(),
        v0_policy_training_preflight_status(),
        v0_residual_policy_eval_status(),
        v0_policy_promotion_gate_status(),
        external_robot_adapter_status(),
        cross_robot_portability_status(),
        v0_portability_review_packet_status(),
        action_semantics_probe_status(),
        historical_doc_status(),
        tracked_generated_metadata_status(),
    ]


def next_allowed_action(
    contact_status: str,
    lifecycle_hold_status: str,
    post_trace_status: str,
    variation_status: str,
    action_probe_status: str,
) -> str:
    if contact_status == "PASS":
        if post_trace_status == "PASS":
            if variation_status != "PASS":
                return (
                    "The old contact-smoke and single successful insertion-trace loop is closed, "
                    "but V0 reproducibility is not proven. The next allowed physical step is the "
                    "fixed-budget success-variation trace-only batch from "
                    "artifacts/manifests/success_trace_variations_2026-06-25.json. Keep it blocked "
                    "until fresh Brev UI credit evidence is written, the ignored local env is armed "
                    "for one run, the pre-batch audit is READY, and the wrapper can enforce watchdog, "
                    "artifact pullback, deletion, and final empty-org confirmation. Do not start "
                    "dataset freezing, learned policy, VLM, ROS integration, external-arm adapter "
                    "work, or sim-to-real claims until at least 5 non-baseline strict successes and "
                    "the fail-closed negative control pass the result gate. Safe local contract "
                    "commands such as V0 skill readiness, policy/API review precheck, and external "
                    "adapter BLOCKED checks may still run because they do not claim execution readiness."
                )
            return (
                "The Phase 2 contact-smoke gate, post-smoke insertion trace, and success-variation "
                "result gate are satisfied. The next allowed step is to run "
                "scripts/finalize_success_variation_batch.sh, freeze the V0 scripted-skill dataset, "
                "then run scripts/prepare_v0_policy_api_review.py before reviewing learned-policy, "
                "VLM, ROS, or external-arm adapter work."
            )
        if action_probe_status == "BLOCKED":
            return (
                "Do not run a viewport video, another unchanged socket-insertion/final-contact trace, "
                "or the same action-semantics probe again. The latest action-semantics probe directly "
                "failed scripts/check_scripted_action_response_trace.py: a commanded world-Z down delta "
                "produced a large off-axis/opposite TCP movement. Next work is local-first control "
                "interface replacement: use scripts/calibrate_joint_position_action.py plus "
                "scripts/joint_response_control.py to build an empirical JointPositionAction "
                "response matrix, then use scripts/run_remote_joint_response_semantics_probe_suite.sh "
                "to prove both down/up semantic commands before any insertion trace. The XYZW "
                "action-frame inverse repair has already failed remote validation, "
                "so the old down/up suite is no longer an approved next paid action unless the "
                "controller itself changes first."
            )
        if action_probe_status == "PASS":
            return (
                "Use the passing action-semantics probe as the new controller gate, then regenerate "
                "one short insertion trace under the same controller before any viewport video."
            )
        if post_trace_status == "BLOCKED":
            return (
                "Do not run a viewport video or another unchanged socket-insertion/final-contact "
                "paid trace. The latest socket-insertion-servo trace now passes the WXYZ frame "
                "audit, but fails scripts/check_scripted_action_response_trace.py: the commanded "
                "insertion delta moved the action frame in the wrong direction. Next work is "
                "control-interface first: any candidate controller must pass an action-response "
                "gate, and any relative-IK calibration must pass "
                "scripts/check_action_calibration_summary.py before it can feed insertion control. "
                "The next guarded paid diagnostic is the down/up suite "
                "scripts/recreate_brev_and_run_action_semantics_probe_suite.sh, not a video run. "
                "Only after that semantic trace passes should final insertion phase ownership be "
                "replaced or one guarded paid insertion trace be considered."
            )
        return (
            "Regenerate exactly one short scripted trace under the validated task, then refresh "
            "contact-validity and demo-coverage reports before reopening controller/BC/RL work."
        )
    if lifecycle_hold_status == "BLOCKED":
        return (
            "The latest local change makes the guide-wall-sweep blocked check radius-aware: "
            "the cylindrical lower-end centerline should sit about one peg radius above the "
            "wall top during contact, while arm-servo diagnostics still require wall-top plane "
            "blocking. Keep the Brev lifecycle hold active until local quality passes, the "
            "current contact-smoke bundle is rebuilt, and `/Users/Shenghan/bin/brev ls instances --json --all` "
            "returns `{\"workspaces\": null}`. Only then consider one short smoke retry with "
            "`RCA_ACK_BREV_LIFECYCLE_RISK=1`, watchdog, pullback, immediate deletion, and final empty-org confirmation."
        )
    return (
        "Rerun local quality, rebuild the current contact-smoke bundle, and only then prepare one "
        "short paid smoke retry with explicit budget, watchdog, pullback, immediate deletion, and "
        "final empty-org confirmation."
    )


def current_decision(
    contact_status: str,
    lifecycle_hold_status: str,
    post_trace_status: str,
    variation_status: str,
    action_probe_status: str,
) -> str:
    if contact_status == "PASS":
        if post_trace_status == "PASS":
            if variation_status != "PASS":
                return (
                    "The Phase 2 contact-smoke gate and one strict post-smoke insertion trace are "
                    "satisfied, so the project is no longer blocked on the old contact/controller "
                    "proof loop. The active blocker is reproducibility: the success-variation result "
                    "gate still lacks the planned small socket/reset traces and the fail-closed "
                    "negative control. A prettier video is not the main next milestone."
                )
            return (
                "The Phase 2 contact-smoke gate, post-smoke insertion trace, and success-variation "
                "result gate are satisfied. The project may move to dataset finalization and then "
                "the offline policy-readiness pipeline."
            )
        if action_probe_status == "BLOCKED":
            return (
                "The Phase 2 contact-smoke gate is satisfied, but the dedicated action-semantics "
                "probe failed. The remaining blocker is the control/action interface, not contact "
                "physics and not video capture. Continuing to tune the current insertion script "
                "would repeat the old loop."
            )
        if action_probe_status == "PASS":
            return (
                "The Phase 2 contact-smoke gate and action-semantics probe are satisfied. The next "
                "evidence gap is a short insertion trace under the same passing controller."
            )
        if post_trace_status == "BLOCKED":
            return (
                "The Phase 2 contact-smoke gate is satisfied, and the fresh post-smoke trace shows the "
                "remaining blocker is controller/task formulation rather than contact-physics validation. "
                "Viewport video capture is not the main route until a semantic trace already passes."
            )
        if lifecycle_hold_status == "BLOCKED":
            return (
                "The Phase 2 contact-smoke gate is satisfied. Do not start new paid Brev work "
                "until the active lifecycle hold is deliberately cleared or acknowledged for a "
                "specific short run with explicit budget, TTL, watchdog, artifact pullback, "
                "immediate deletion, and final empty-org confirmation."
            )
        return (
            "The Phase 2 contact-smoke gate is satisfied. Post-contact diagnostics may resume, "
            "but any paid GPU work still needs explicit budget, TTL, watchdog, artifact pullback, "
            "immediate deletion, and final empty-org confirmation."
        )
    return (
        "Do not run controller sweeps, BC, RL, broad scripted probes, or any post-contact paid GPU "
        "job while the Phase 2 contact gate is BLOCKED."
    )


def render_markdown(all_checks: Iterable[Check]) -> str:
    check_list = list(all_checks)
    branch = run_git("branch", "--show-current") or "<unknown>"
    head = run_git("show", "-s", "--format=%h %s", "HEAD")
    contact = next((item for item in check_list if item.name == "Phase 2 contact gate"), None)
    contact_status = contact.status if contact else "BLOCKED"
    lifecycle_hold = next((item for item in check_list if item.name == "Brev lifecycle hold"), None)
    lifecycle_hold_status = lifecycle_hold.status if lifecycle_hold else "BLOCKED"
    post_trace = next((item for item in check_list if item.name == "Post-smoke insertion trace"), None)
    post_trace_status = post_trace.status if post_trace else "MISSING"
    variation = next((item for item in check_list if item.name == "Success variation gate"), None)
    variation_status = variation.status if variation else "MISSING"
    action_probe = next((item for item in check_list if item.name == "Action semantics probe"), None)
    action_probe_status = action_probe.status if action_probe else "MISSING"

    lines = [
        "# Current Project Status",
        "",
        f"- Repo: `{REPO_ROOT}`",
        f"- Branch: `{branch}`",
        f"- HEAD: `{head}`",
        f"- Runtime source payload scope: `{current_source_payload_scope()}`",
        f"- Runtime source payload SHA256: `{current_source_payload_sha256()}`",
        "- Paid compute used by this report: none",
        "",
        "## Status Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for item in check_list:
        detail = item.detail.replace("|", "\\|")
        lines.append(f"| {item.name} | {item.status} | {detail} |")

    lines.extend(
        [
            "",
            "## Current Decision",
            "",
            current_decision(
                contact_status,
                lifecycle_hold_status,
                post_trace_status,
                variation_status,
                action_probe_status,
            ),
            "",
            "## Next Allowed Action",
            "",
            next_allowed_action(
                contact_status,
                lifecycle_hold_status,
                post_trace_status,
                variation_status,
                action_probe_status,
            ),
            "",
            "## Commands",
            "",
            "```bash",
            "./scripts/brev_paid_safety_status.sh",
            "./scripts/run_local_quality_checks.sh",
            "python3 scripts/check_phase2_contact_gate.py",
            "python3 scripts/check_success_variation_batch_plan.py artifacts/manifests/success_trace_variations_2026-06-25.json",
            "python3 scripts/check_success_variation_batch_results.py artifacts/manifests/success_trace_variations_2026-06-25.json",
            "python3 scripts/prepare_success_variation_dataset.py artifacts/manifests/success_trace_variations_2026-06-25.json --dry-run",
            "python3 scripts/audit_success_variation_assumptions.py artifacts/manifests/success_trace_variations_2026-06-25.json --phase pre-batch --run-packet artifacts/analysis/success_variation_run_packet_2026-06-25.json --no-output",
            "python3 scripts/plan_success_variation_recovery_batch.py artifacts/manifests/success_trace_variations_2026-06-25.json --no-output",
            "python3 scripts/prepare_brev_credit_review.py --no-output",
            "python3 scripts/prepare_brev_credit_review.py --balance-eur <current-brev-ui-balance> --no-output",
            "python3 scripts/write_brev_credit_evidence.py --balance-eur <current-brev-ui-balance> --budget-eur 6.00 --dry-run",
            "python3 scripts/prepare_success_variation_paid_batch.py --balance-eur <current-brev-ui-balance> --force-credit --i-understand-this-arms-paid-run --dry-run",
            "python3 scripts/prepare_success_variation_paid_batch.py --balance-eur <current-brev-ui-balance> --force-credit --i-understand-this-arms-paid-run",
            "python3 scripts/check_v0_language_instruction_suite.py --no-output",
            "python3 scripts/check_v0_skill_readiness.py --skip-phase2-contact-gate",
            "python3 scripts/run_v0_language_skill_dry_run.py \"insert the peg into the left socket\" --skip-phase2-contact-gate --no-output",
            "python3 scripts/plan_v0_skill_execution.py --skip-phase2-contact-gate --no-output",
            "python3 scripts/prepare_v0_policy_api_review.py --skip-phase2-contact-gate",
            "python3 scripts/audit_v0_policy_dataset.py --no-output",
            "python3 scripts/plan_v0_policy_experiment.py --no-output",
            "python3 scripts/plan_v0_policy_feature_dry_run.py --no-output",
            "python3 scripts/audit_v0_policy_label_sources.py --no-output",
            "python3 scripts/plan_v0_policy_label_dry_run.py --no-output",
            "python3 scripts/extract_v0_policy_label_dataset.py --no-output",
            "python3 scripts/check_v0_policy_training_preflight.py --no-output",
            "python3 scripts/train_v0_residual_policy.py --dry-run --no-output",
            "python3 scripts/run_v0_offline_policy_readiness_pipeline.py --skip-phase2-contact-gate --no-summary --no-output",
            "python3 scripts/evaluate_v0_residual_policy.py --dry-run --no-output",
            "python3 scripts/check_v0_policy_promotion_gate.py --skip-phase2-contact-gate --no-output",
            "python3 scripts/check_v0_robot_adapter_contract.py",
            "python3 scripts/plan_v0_robot_adapter_manifest.py --robot-id <target_robot_id> --robot-family <target_robot_family> --end-effector <tool_or_gripper> --no-output",
            "python3 scripts/check_v0_portability_boundary.py --skip-phase2-contact-gate",
            "python3 scripts/prepare_v0_portability_review.py --skip-phase2-contact-gate --no-output",
            "python3 scripts/prepare_v0_portability_review.py --target-robot-id <target_robot_id> --target-robot-family <target_robot_family> --end-effector <tool_or_gripper> --skip-phase2-contact-gate --no-output",
            "scripts/run_success_variation_batch_from_config.sh configs/success_variation_batch_run.local.env --check-only",
            "python3 scripts/write_brev_credit_evidence.py --balance-eur <current-brev-ui-balance> --budget-eur 6.00 --force",
            "python3 scripts/arm_success_variation_paid_env.py --i-understand-this-arms-paid-run",
            "python3 scripts/check_success_variation_paid_lifecycle_preflight.py --no-output",
            "python3 scripts/run_success_variation_paid_lifecycle.py --balance-eur <current-brev-ui-balance> --run --i-understand-this-can-create-paid-instance",
            "scripts/run_success_variation_batch_from_config.sh configs/success_variation_batch_run.local.env --run",
            "scripts/finalize_success_variation_batch.sh artifacts/manifests/success_trace_variations_2026-06-25.json",
            "python3 scripts/run_v0_offline_policy_readiness_pipeline.py",
            "python3 scripts/arm_success_variation_paid_env.py --disarm",
            "python3 scripts/check_peg_in_hole_video_candidate.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json",
            "python3 scripts/check_final_contact_boundary_diagnostic.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json",
            "python3 scripts/audit_trace_frame_alignment.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json",
            "python3 scripts/check_scripted_action_response_trace.py artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json --min-command-norm 0.0002 --stop-after-first-success",
            "```",
            "",
            "## Historical Contact-Smoke Reference",
            "",
            "The old contact-smoke evidence path remains available through "
            "`scripts/pull_contact_smoke_log.sh` and `scripts/archive_contact_smoke_log.sh`, "
            "but it is not the active next step after Phase 2 PASS. Do not hand-set "
            "`RCA_BREV_CREDITS_VERIFIED` or `RCA_PAID_ESTIMATED_EUR_PER_HOUR` for the "
            "success-variation run; use `scripts/write_brev_credit_evidence.py` and "
            "`scripts/arm_success_variation_paid_env.py` so the ignored local env stays "
            "one-run and fail-closed.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="Exit nonzero if any check is BLOCKED, STALE, or MISSING.",
    )
    args = parser.parse_args()

    all_checks = checks()
    print(render_markdown(all_checks), end="")

    if args.fail_on_blocked and any(item.status in FAILING_STATUSES for item in all_checks):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
