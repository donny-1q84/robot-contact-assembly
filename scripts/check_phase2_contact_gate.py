#!/usr/bin/env python3
"""Fail-closed gate for Phase 2 contact-physics validation.

This script does not run Isaac Sim. It only decides whether the repository has
archived evidence that the contact-physics smoke passed on an Isaac runtime.
Until that evidence exists, downstream controller sweeps, BC, RL, or paid GPU
runs should remain blocked.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


SEMANTIC_REQUIRED_MARKERS = (
    "CONTACT-SMOKE reset-joints: deterministic",
    "CONTACT-SMOKE phase free-space-settle: end",
    "CONTACT-SMOKE attach: PASS",
    "CONTACT-SMOKE free-space: PASS",
    "CONTACT-SMOKE phase local-guide-reanchor: end",
    "CONTACT-SMOKE contact-setup: local-guide reanchored",
    "CONTACT-SMOKE free-space-reanchored: PASS",
    "CONTACT-SMOKE press-control: local-wall-sweep",
    "CONTACT-SMOKE phase press-hold: end",
    "CONTACT-SMOKE press-force: PASS",
    "CONTACT-SMOKE press-tracking: PASS",
    "CONTACT-SMOKE press-blocked: PASS",
    "CONTACT-SMOKE press-no-clip: PASS",
    "CONTACT-SMOKE phase retreat-hold: end",
    "CONTACT-SMOKE release: PASS",
    "CONTACT-SMOKE joint-integrity: PASS",
    "CONTACT-SMOKE phase-sequence: PASS",
)
EPILOGUE_MARKERS = (
    "Contact physics smoke completed: all checks passed",
    "[contact-smoke] completed: contact physics is real",
)
FAIL_MARKER_RE = re.compile(r"CONTACT-SMOKE .*: FAIL")
GIT_HEAD_RE = re.compile(r"^\[contact-smoke\] git_head=(?!unknown$)(\S+)$", re.MULTILINE)
SOURCE_MANIFEST_HEAD_RE = re.compile(
    r"^\[contact-smoke\] source_manifest: git_head=(?!unknown$)(\S+)$",
    re.MULTILINE,
)
SOURCE_MANIFEST_PAYLOAD_RE = re.compile(
    r"^\[contact-smoke\] source_manifest: source_payload_sha256=([0-9a-f]{64})$",
    re.MULTILINE,
)
SOURCE_MANIFEST_SCOPE_RE = re.compile(
    r"^\[contact-smoke\] source_manifest: source_payload_scope=(\S+)$",
    re.MULTILINE,
)
EXPECTED_SOURCE_PAYLOAD_SCOPE = "runtime-v1"


def _has_source_evidence(text: str) -> bool:
    if GIT_HEAD_RE.search(text):
        return True
    return (
        "[contact-smoke] source_manifest_begin" in text
        and "[contact-smoke] source_manifest_end" in text
        and SOURCE_MANIFEST_HEAD_RE.search(text) is not None
    )


def _source_heads(text: str) -> set[str]:
    heads = {match.group(1) for match in GIT_HEAD_RE.finditer(text)}
    heads.update(match.group(1) for match in SOURCE_MANIFEST_HEAD_RE.finditer(text))
    return heads


def _source_payload_fingerprints(text: str) -> set[str]:
    return {match.group(1) for match in SOURCE_MANIFEST_PAYLOAD_RE.finditer(text)}


def _source_payload_scopes(text: str) -> set[str]:
    return {match.group(1) for match in SOURCE_MANIFEST_SCOPE_RE.finditer(text)}


def _load_source_payload_fingerprint(repo_root: Path) -> str | None:
    module_path = repo_root / "scripts" / "source_payload_fingerprint.py"
    if not module_path.is_file():
        return None
    result = subprocess.run(
        [sys.executable, str(module_path), str(repo_root)],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _current_git_head(repo_root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _candidate_logs(repo_root: Path, explicit_log: Path | None) -> list[Path]:
    if explicit_log is not None:
        return [explicit_log.expanduser().resolve()]

    log_dir = repo_root / "artifacts" / "launchable_logs"
    candidates = [log_dir / "contact_physics_smoke.log"]
    if log_dir.is_dir():
        candidates.extend(log_dir.rglob("*contact*smoke*.log"))

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _validate_log(
    path: Path,
    *,
    current_head: str | None,
    current_payload_sha256: str | None,
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    if not path.is_file():
        return False, [f"missing log: {path}"]

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, [f"could not read {path}: {exc}"]

    if FAIL_MARKER_RE.search(text):
        issues.append("FAIL marker present")

    logged_payload_fingerprints = _source_payload_fingerprints(text)
    logged_payload_scopes = _source_payload_scopes(text)
    payload_matches = (
        current_payload_sha256 is not None
        and current_payload_sha256 in logged_payload_fingerprints
    )

    if not _has_source_evidence(text):
        issues.append("missing source evidence: need non-unknown git_head or bundle source_manifest git_head")
    elif current_head is not None and current_head not in _source_heads(text) and not payload_matches:
        issues.append(
            "source HEAD mismatch: log does not reference current HEAD "
            f"{current_head} and runtime source payload did not match"
        )

    if EXPECTED_SOURCE_PAYLOAD_SCOPE not in logged_payload_scopes:
        issues.append(
            "missing or unsupported source payload scope: need "
            f"source_manifest source_payload_scope={EXPECTED_SOURCE_PAYLOAD_SCOPE}"
        )

    if not logged_payload_fingerprints:
        issues.append("missing source payload fingerprint: need source_manifest source_payload_sha256")
    elif current_payload_sha256 is not None and current_payload_sha256 not in logged_payload_fingerprints:
        issues.append(
            "source payload mismatch: log does not reference current payload "
            f"{current_payload_sha256}"
        )

    missing = [marker for marker in SEMANTIC_REQUIRED_MARKERS if marker not in text]
    if missing:
        issues.append("missing required marker(s): " + ", ".join(missing))

    return not issues, issues


def _run_local_quality(repo_root: Path) -> int:
    script = repo_root / "scripts" / "run_local_quality_checks.sh"
    if not script.is_file():
        print(f"[phase2-contact-gate] ERROR: missing {script}", file=sys.stderr)
        return 1
    return subprocess.run([str(script)], cwd=repo_root, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_default_repo_root(),
        help="Repository root. Defaults to this script's parent repo.",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Specific contact physics smoke log to validate.",
    )
    parser.add_argument(
        "--run-local-quality",
        action="store_true",
        help="Run scripts/run_local_quality_checks.sh before validating smoke evidence.",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.expanduser().resolve()
    print(f"[phase2-contact-gate] repo={repo_root}")

    smoke_runner = repo_root / "scripts" / "run_launchable_contact_physics_smoke.sh"
    if not smoke_runner.is_file():
        print(f"[phase2-contact-gate] ERROR: missing smoke runner: {smoke_runner}", file=sys.stderr)
        return 1

    if args.run_local_quality:
        quality_status = _run_local_quality(repo_root)
        if quality_status != 0:
            print(f"[phase2-contact-gate] BLOCKED: local quality checks failed ({quality_status})")
            return 2
    else:
        print("[phase2-contact-gate] local quality: skipped (use --run-local-quality to include it)")

    candidates = _candidate_logs(repo_root, args.log)
    current_head = _current_git_head(repo_root)
    current_payload_sha256 = _load_source_payload_fingerprint(repo_root)
    if current_head is not None:
        print(f"[phase2-contact-gate] current_head={current_head}")
    else:
        print("[phase2-contact-gate] current_head=unknown (source HEAD comparison skipped)")
    if current_payload_sha256 is not None:
        print(f"[phase2-contact-gate] current_payload_sha256={current_payload_sha256}")
    else:
        print("[phase2-contact-gate] current_payload_sha256=unknown (payload comparison skipped)")
    print("[phase2-contact-gate] checking smoke log candidates:")
    for path in candidates:
        print(f"  - {path}")

    saw_existing_log = False
    failed_logs: list[tuple[Path, list[str]]] = []
    for path in candidates:
        passed, issues = _validate_log(
            path,
            current_head=current_head,
            current_payload_sha256=current_payload_sha256,
        )
        if path.is_file():
            saw_existing_log = True
        if passed:
            print(f"[phase2-contact-gate] PASS: validated contact-physics smoke evidence: {path}")
            return 0
        failed_logs.append((path, issues))

    print("[phase2-contact-gate] BLOCKED: no valid contact-physics smoke PASS log was found.")
    if saw_existing_log:
        for path, issues in failed_logs:
            if not path.is_file():
                continue
            print(f"[phase2-contact-gate] invalid log: {path}")
            for issue in issues:
                print(f"  - {issue}")
    else:
        print("[phase2-contact-gate] no candidate log exists yet.")

    print("[phase2-contact-gate] next allowed paid action:")
    print("  1. Refresh Brev/NVIDIA login and confirm no active paid instances.")
    print("  2. Start the paid-run watchdog/deletion plan before creating anything.")
    print("  3. Run only ./scripts/run_launchable_contact_physics_smoke.sh on Isaac runtime.")
    print("  4. Pull and archive the smoke log with ./scripts/pull_contact_smoke_log.sh.")
    print("  5. Delete the instance and confirm the active list is empty.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
