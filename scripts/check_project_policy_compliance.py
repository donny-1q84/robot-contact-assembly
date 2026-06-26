#!/usr/bin/env python3
"""Static policy checks for the current project state.

These checks are intentionally lightweight and local. They protect the two
highest-risk process rules in this repo:

1. Paid Brev/Launchable work must go through the shared preflight.
2. Historical Phase 2 docs must not present old contact metrics as current
   completion evidence.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]

DIRECT_BREV_CREATE_RE = re.compile(
    r"""(?mx)
    (?:
      ["']?
      (?:\$\{?BREV_BIN\}?|/Users/Shenghan/bin/brev|\bbrev)
      ["']?
      \s+
      create
      \b
    )
    """
)
EXPECTED_DIRECT_CREATE_SCRIPTS = {
    "scripts/recreate_brev_and_run_polish.sh",
    "scripts/run_brev_reachable_guard_probe.sh",
    "scripts/run_guarded_phase2_gate.sh",
}
REMOTE_OPERATION_RE = re.compile(
    r"""(?mx)
    (?:
      (?<![A-Za-z0-9_.-])
      (?:ssh|rsync|scp|sftp)
      \s+
    )
    |
    (?:
      ["']?
      (?:\$\{?BREV_BIN\}?|/Users/Shenghan/bin/brev|\bbrev)
      ["']?
      \s+
      (?:exec|copy|port-forward|shell|open)
      \b
    )
    |
    (?:
      ["']
      (?:/Users/Shenghan/bin/brev|brev)
      ["']
      \s*,\s*
      ["']
      (?:exec|copy|port-forward|shell|open)
      ["']
    )
    """
)
REMOTE_OPERATION_EXEMPT_SCRIPTS = {
    "scripts/check_project_policy_compliance.py",
    "scripts/create_launchable_bundle.sh",
    "scripts/test_local_gates.py",
}
FORBIDDEN_GUARD_BYPASS_MARKERS = (
    "RCA_REMOTE_OPERATION_PREFLIGHT_DONE",
    "RCA_PAID_PREFLIGHT_SKIP_PHASE_GATE",
    "RCA_PAID_PREFLIGHT_ALLOW_NONEMPTY_ORG",
    "RCA_BREV_UI_WATCHDOG_SKIP_PREFLIGHT",
    "RCA_GATE_WATCHDOG_ENABLED",
    "RCA_RECREATE_WATCHDOG_ENABLED",
    "RCA_GATE_DELETE_ON_EXIT",
    "RCA_GATE_KEEP_ON_FAILURE",
    "RCA_RECREATE_DELETE_ON_EXIT",
    "RCA_RECREATE_KEEP_ON_FAILURE",
    "RCA_BREV_GUARD_DELETE_ON_EXIT",
    "RCA_BREV_GUARD_KEEP_ON_FAILURE",
)
FORBIDDEN_MARKER_EXEMPT_SCRIPTS = {
    "scripts/check_project_policy_compliance.py",
    "scripts/test_local_gates.py",
}

REQUIRED_DOC_MARKERS = {
    "AGENTS.md": (
        "scripts/check_phase2_contact_gate.py",
        "source_payload_sha256",
        "scripts/launchable_post_contact_gate.sh",
        "scripts/refresh_brev_login.sh",
        "scripts/brev_paid_safety_status.sh",
        "scripts/paid_compute_preflight.sh",
        "RCA_BREV_CREDITS_VERIFIED",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR",
        "scripts/prepare_contact_smoke_run.sh",
        "scripts/archive_contact_smoke_log.sh",
        "scripts/pull_contact_smoke_log.sh",
        "scripts/project_status_report.py",
        "scripts/check_contact_physics_wiring.py",
        "scripts/check_project_structure.py",
        "scripts/test_local_gates.py",
        "press-no-clip",
        "[contact-smoke] completed: contact physics is real",
        "scripts/remote_operation_preflight.sh",
    ),
    "README.md": (
        "Current blocking status",
        "scripts/check_phase2_contact_gate.py",
        "source_payload_sha256",
        ".claude/",
        "scripts/launchable_post_contact_gate.sh",
        "scripts/refresh_brev_login.sh",
        "scripts/brev_paid_safety_status.sh",
        "./scripts/paid_compute_preflight.sh",
        "RCA_BREV_CREDITS_VERIFIED",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR",
        "scripts/prepare_contact_smoke_run.sh",
        "scripts/archive_contact_smoke_log.sh",
        "scripts/pull_contact_smoke_log.sh",
        "scripts/project_status_report.py",
        "press-no-clip",
        "scripts/remote_operation_preflight.sh",
        "generated cache",
        "direct `ssh`, `rsync`, `scp`, `sftp`",
    ),
    "docs/current_project_handoff.md": (
        "2026-06-18 Current Overlay",
        "2026-06-19 Local Guard Overlay",
        "scripts/check_phase2_contact_gate.py",
        "scripts/refresh_brev_login.sh",
        "scripts/paid_compute_preflight.sh",
        "RCA_BREV_CREDITS_VERIFIED",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR",
        "scripts/prepare_contact_smoke_run.sh",
        "scripts/archive_contact_smoke_log.sh",
        "scripts/pull_contact_smoke_log.sh",
        "scripts/project_status_report.py",
        "press-no-clip",
        "scripts/remote_operation_preflight.sh",
        "PYTHONDONTWRITEBYTECODE=1",
        "robot-contact-assembly-contact-smoke-manual-preauth-*.tar.gz",
    ),
    "docs/phase2_cv_summary.md": (
        "Superseded by 2026-06-18 Audit",
        "Do not use this document as a resume/CV claim",
    ),
    "docs/phase2_il_contact_policy_plan.md": (
        "Blocked by Contact-Physics Gate",
        "do not train BC, run RL",
    ),
    "docs/aws_isaac_launchable_runbook.md": (
        "Contact-Smoke Only",
        "scripts/refresh_brev_login.sh",
        "scripts/paid_compute_preflight.sh",
        "scripts/brev_paid_safety_status.sh",
        "RCA_ALLOW_PAID_BREV_CREATE=1",
        "RCA_BREV_CREDITS_VERIFIED=1",
        "RCA_PAID_BUDGET_EUR=<explicit-budget>",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour>",
        "RCA_PAID_RUN_PURPOSE=contact_physics_smoke",
        "scripts/archive_contact_smoke_log.sh",
        "scripts/pull_contact_smoke_log.sh",
        "press-no-clip",
    ),
    "docs/project_quality_audit_2026-06-18.md": (
        "2026-06-19 Local Guard Overlay",
        "press-no-clip",
        "RCA_ALLOW_PAID_BREV_CREATE=1",
        "RCA_BREV_CREDITS_VERIFIED=1",
        "RCA_PAID_BUDGET_EUR=<explicit-budget>",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour>",
        "RCA_PAID_RUN_PURPOSE=contact_physics_smoke",
        "source_payload_sha256",
        ".claude/",
        "scripts/launchable_post_contact_gate.sh",
        "PYTHONDONTWRITEBYTECODE=1",
        "remote_operation_preflight.sh",
        "scripts/archive_contact_smoke_log.sh",
        "scripts/pull_contact_smoke_log.sh",
        "robot-contact-assembly-contact-smoke-manual-preauth-*.tar.gz",
    ),
    "docs/gpu_selection_policy.md": (
        "scripts/paid_compute_preflight.sh",
        "RCA_ALLOW_PAID_BREV_CREATE=1",
        "RCA_PAID_BUDGET_EUR=<explicit-budget>",
        "RCA_BREV_CREDITS_VERIFIED=1",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR=<conservative-eur-per-hour>",
        "RCA_PAID_RUN_PURPOSE=contact_physics_smoke",
    ),
    "scripts/create_launchable_bundle.sh": (
        ".rca_launchable_source_manifest.txt",
        "RCA_LAUNCHABLE_TMPDIR",
        "git_dirty=",
        "source_payload_scope=",
        "source_payload_sha256=",
        "--exclude '.claude/'",
        "--exclude '.env'",
        "--exclude '*.pem'",
        "--exclude '*credential*'",
        "--exclude '*.egg-info/'",
        "--exclude '__pycache__/'",
        "--exclude '*.pyc'",
        "--exclude '.DS_Store'",
    ),
    "scripts/run_launchable_contact_physics_smoke.sh": (
        "source_manifest_begin",
        "tee -a",
        "task extension install completed",
        "CONTACT-SMOKE press-no-clip: PASS",
        "pip install failed status",
        "missing Isaac Python",
        "missing project repo",
    ),
    "scripts/launchable_post_contact_gate.sh": (
        "check_phase2_contact_gate.py",
        "run_launchable_contact_physics_smoke.sh first",
    ),
    "scripts/prepare_contact_smoke_run.sh": (
        "create_launchable_bundle.sh",
        "RCA_CONTACT_SMOKE_BUNDLE_PATH",
        "Prepared bundle:",
        "pull_contact_smoke_log.sh",
    ),
    "scripts/archive_contact_smoke_log.sh": (
        "check_phase2_contact_gate.py",
        "contact_physics_smoke.log",
        "validating source log before archive",
        "canonical contact-smoke evidence",
    ),
    "scripts/pull_contact_smoke_log.sh": (
        "remote_operation_preflight.sh",
        "RCA_REMOTE_OPERATION_PURPOSE=contact_physics_smoke",
        "archive_contact_smoke_log.sh",
        "contact_physics_smoke.log",
    ),
    "scripts/project_status_report.py": (
        "FAILING_STATUSES",
        "check_phase2_contact_gate.py",
        "archive_contact_smoke_log.sh",
        "RCA_BREV_LIFECYCLE_HOLD_FILE",
        "RCA_BREV_CREDITS_VERIFIED",
        "RCA_PAID_ESTIMATED_EUR_PER_HOUR",
        "current_source_payload_scope",
        "source_payload_scope",
        "source_payload_sha256",
        "Contact-smoke bundle",
        "Brev lifecycle hold",
        "brev_launchable_lifecycle_hold.md",
        "Runtime source payload scope",
        "Runtime source payload SHA256",
    ),
    "scripts/create_brev_lifecycle_incident_bundle.sh": (
        "brev_healthcheck",
        "project_status_report.py",
        "paid_preflight_hold_block",
        "support_followup_draft.md",
        "This script does not create, start, stop, or delete paid resources.",
    ),
    "scripts/check_brev_lifecycle_hold_clearance.sh": (
        "READY_FOR_HUMAN_REVIEW",
        "Brev lifecycle hold | BLOCKED",
        "Contact-smoke bundle | READY",
        "paid_compute_preflight.sh",
        "visible_instances=0",
    ),
    "scripts/run_local_quality_checks.sh": (
        "PYTHONDONTWRITEBYTECODE=1",
        "check_project_structure.py",
        "compile(source",
        "generated cache hygiene",
    ),
    "scripts/check_project_structure.py": (
        "not the runtime source of truth",
        "source/robot_contact_assembly_tasks",
        "robot_contact_assembly_tasks",
    ),
    "scripts/check_phase2_contact_gate.py": (
        "EXPECTED_SOURCE_PAYLOAD_SCOPE",
        "source_payload_scope",
        "source HEAD mismatch",
        "source payload mismatch",
        "payload_matches",
        "current_head=",
        "current_payload_sha256=",
        "CONTACT-SMOKE press-no-clip: PASS",
    ),
    "scripts/source_payload_fingerprint.py": (
        "source_payload_fingerprint",
        "runtime-source fingerprint",
        "FINGERPRINT_SCOPE",
        "--scope",
        "INCLUDED_PREFIXES",
        "scripts/contact_physics_smoke.py",
        "scripts/run_launchable_contact_physics_smoke.sh",
        '".claude"',
        '".env"',
        '"credential"',
        ".rca_launchable_source_manifest.txt",
        "__pycache__",
    ),
    "scripts/remote_operation_preflight.sh": (
        "RCA_REMOTE_OPERATION_PURPOSE",
        "contact_physics_smoke",
        "check_phase2_contact_gate.py",
    ),
    "scripts/bootstrap_brev_workspace.sh": (
        "remote_operation_preflight.sh",
    ),
    "scripts/setup_remote_isaaclab.sh": (
        "remote_operation_preflight.sh",
    ),
    "scripts/start_live_code_port_forward.sh": (
        "remote_operation_preflight.sh",
    ),
    "scripts/push_single_file_to_brev.py": (
        "remote_operation_preflight.sh",
    ),
    "scripts/remote_common.sh": (
        "remote_operation_preflight.sh",
    ),
    "scripts/sync_to_brev.sh": (
        "remote_operation_preflight.sh",
    ),
    "scripts/install_remote_isaaclab_runtime.sh": (
        "remote_operation_preflight.sh",
    ),
    "scripts/pull_artifacts.sh": (
        "remote_operation_preflight.sh",
    ),
    "scripts/pull_contact_smoke_log.sh": (
        "remote_operation_preflight.sh",
    ),
    "scripts/run_remote_eval_final_contact_candidate_bc.sh": (
        "remote_operation_preflight.sh",
    ),
}


def fail(message: str) -> None:
    print(f"[policy-check] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(path: str) -> str:
    full_path = REPO_ROOT / path
    if not full_path.is_file():
        fail(f"missing required file: {path}")
    return full_path.read_text(encoding="utf-8", errors="replace")


def check_paid_create_scripts() -> None:
    create_scripts: list[Path] = []
    for path in sorted((REPO_ROOT / "scripts").glob("*.sh")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if DIRECT_BREV_CREATE_RE.search(text):
            create_scripts.append(path)

    if not create_scripts:
        fail("no direct Brev create scripts detected; update policy scanner if create flow changed")

    detected = {str(path.relative_to(REPO_ROOT)) for path in create_scripts}
    missing_expected = sorted(EXPECTED_DIRECT_CREATE_SCRIPTS - detected)
    if missing_expected:
        fail("direct Brev create scanner missed expected script(s): " + ", ".join(missing_expected))

    for path in create_scripts:
        rel_path = str(path.relative_to(REPO_ROOT))
        text = read(rel_path)
        if "paid_compute_preflight.sh" not in text:
            fail(f"{rel_path} can create paid compute but does not call paid_compute_preflight.sh")
        if "RCA_ALLOW_PAID_BREV_CREATE" not in text:
            fail(f"{rel_path} can create paid compute but does not require RCA_ALLOW_PAID_BREV_CREATE")
        if "RCA_BREV_CREDITS_VERIFIED" not in text:
            fail(f"{rel_path} can create paid compute but does not require RCA_BREV_CREDITS_VERIFIED")
        if "RCA_PAID_MAX_MINUTES" not in text:
            fail(f"{rel_path} does not forward a paid TTL into the preflight")
        if "brev_paid_run_watchdog.sh" not in text:
            fail(f"{rel_path} can create paid compute but does not start the billing watchdog")
        if "verify_watchdog_alive" not in text:
            fail(f"{rel_path} can create paid compute but does not verify the watchdog started before create")


def check_remote_operation_scripts() -> None:
    remote_scripts: list[Path] = []
    for pattern in ("*.sh", "*.py"):
        for path in sorted((REPO_ROOT / "scripts").glob(pattern)):
            rel_path = str(path.relative_to(REPO_ROOT))
            if rel_path in REMOTE_OPERATION_EXEMPT_SCRIPTS:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if REMOTE_OPERATION_RE.search(text):
                remote_scripts.append(path)

    for path in remote_scripts:
        rel_path = str(path.relative_to(REPO_ROOT))
        text = read(rel_path)
        has_remote_preflight = "remote_operation_preflight.sh" in text
        has_remote_common_gate = "remote_common.sh" in text and "rca_init_remote_vars" in text
        has_paid_preflight = "paid_compute_preflight.sh" in text and "RCA_ALLOW_PAID_BREV_CREATE" in text
        if not (has_remote_preflight or has_remote_common_gate or has_paid_preflight):
            fail(
                f"{rel_path} performs direct remote operations but does not use "
                "remote_operation_preflight.sh, remote_common.sh/rca_init_remote_vars, or paid_compute_preflight.sh"
            )


def check_doc_markers() -> None:
    for rel_path, markers in REQUIRED_DOC_MARKERS.items():
        text = read(rel_path)
        for marker in markers:
            if marker not in text:
                fail(f"{rel_path} missing marker: {marker}")


def check_gitignore_and_generated_metadata() -> None:
    gitignore = read(".gitignore")
    if "*.egg-info/" not in gitignore:
        fail(".gitignore must ignore generated *.egg-info/ directories")

    result = subprocess.run(
        ["git", "ls-files", "*egg-info*"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        fail(f"git ls-files failed: {result.stderr.strip()}")

    existing_tracked = []
    for rel_path in result.stdout.splitlines():
        if (REPO_ROOT / rel_path).exists():
            existing_tracked.append(rel_path)
    if existing_tracked:
        fail("generated egg-info files still exist in the tracked tree: " + ", ".join(existing_tracked))


def check_no_guard_bypass_markers() -> None:
    for pattern in ("*.sh", "*.py"):
        for path in sorted((REPO_ROOT / "scripts").glob(pattern)):
            rel_path = str(path.relative_to(REPO_ROOT))
            if rel_path in FORBIDDEN_MARKER_EXEMPT_SCRIPTS:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for marker in FORBIDDEN_GUARD_BYPASS_MARKERS:
                if marker in text:
                    fail(f"{rel_path} contains forbidden guard-bypass marker: {marker}")


def check_launchable_workload_gates() -> None:
    for path in sorted((REPO_ROOT / "scripts").glob("run_launchable_*.sh")):
        rel_path = str(path.relative_to(REPO_ROOT))
        if rel_path == "scripts/run_launchable_contact_physics_smoke.sh":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # Wrapper scripts that only set env vars and exec a guarded base script do
        # not define the Launchable repo root themselves.
        if "RCA_LAUNCHABLE_REPO_DIR" not in text:
            continue
        if "launchable_post_contact_gate.sh" not in text:
            fail(f"{rel_path} must call launchable_post_contact_gate.sh before running post-contact Launchable work")


def main() -> int:
    check_paid_create_scripts()
    check_remote_operation_scripts()
    check_doc_markers()
    check_gitignore_and_generated_metadata()
    check_no_guard_bypass_markers()
    check_launchable_workload_gates()
    print("[policy-check] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
