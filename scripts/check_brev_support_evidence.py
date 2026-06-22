#!/usr/bin/env python3
"""Validate the Brev support draft's referenced local evidence bundle.

The incident bundle lives under ignored local artifacts. Fresh checkouts should
still be able to run the offline quality gate; when the local-only bundle is not
present, this checker records a skip instead of failing the whole gate.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys
import tarfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DRAFT = REPO_ROOT / "docs/brev_support_followup_2026-06-20.md"
LOCAL_INCIDENT_DIR = REPO_ROOT / "artifacts" / "brev_lifecycle_incidents"


def fail(message: str) -> None:
    print(f"[brev-support-evidence] FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_text(path: Path) -> str:
    if not path.is_file():
        fail(f"missing file: {path}")
    return path.read_text(encoding="utf-8", errors="replace")


def resolve_path(raw_path: str) -> Path:
    path = Path(raw_path.strip())
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_local_incident_archive(path: Path) -> bool:
    try:
        path.resolve().relative_to(LOCAL_INCIDENT_DIR.resolve())
    except ValueError:
        return False
    return True


def parse_current_archive(text: str) -> tuple[Path, str]:
    archive_refs: list[str] = []
    sha_refs: list[str] = []

    for line in text.splitlines():
        if "gmail_draft_attachment" in line or re.match(r"\s*attachment:", line):
            continue
        archive_refs.extend(re.findall(r"`?([^`\s]+\.tar\.gz)`?", line))
        sha_refs.extend(re.findall(r"sha256[=:]\s*([0-9a-f]{64})", line))

    if not archive_refs:
        fail("support draft does not reference a current evidence archive")
    if not sha_refs:
        fail("support draft does not reference a current evidence sha256")

    unique_archives = sorted(set(archive_refs))
    unique_shas = sorted(set(sha_refs))
    if len(unique_archives) != 1:
        fail("support draft references multiple current evidence archives: " + ", ".join(unique_archives))
    if len(unique_shas) != 1:
        fail("support draft references multiple current evidence sha256 values: " + ", ".join(unique_shas))

    return resolve_path(unique_archives[0]), unique_shas[0]


def tar_texts(archive: Path, required_names: tuple[str, ...]) -> dict[str, str]:
    try:
        with tarfile.open(archive, "r:gz") as tar:
            members = {Path(member.name).name: member for member in tar.getmembers() if member.isfile()}
            missing = [name for name in required_names if name not in members]
            if missing:
                fail("evidence archive is missing required file(s): " + ", ".join(missing))

            result: dict[str, str] = {}
            for name in required_names:
                extracted = tar.extractfile(members[name])
                if extracted is None:
                    fail(f"could not read archive member: {name}")
                result[name] = extracted.read().decode("utf-8", errors="replace")
            return result
    except tarfile.TarError as exc:
        fail(f"could not open evidence archive as tar.gz: {exc}")


def require_contains(text: str, needle: str, label: str) -> None:
    if needle not in text:
        fail(f"{label} missing required marker: {needle}")


def require_contains_any(text: str, needles: tuple[str, ...], label: str) -> None:
    if not any(needle in text for needle in needles):
        fail(f"{label} missing one of required markers: {', '.join(needles)}")


def main() -> int:
    draft = resolve_path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DRAFT
    draft_text = read_text(draft)
    archive, expected_sha = parse_current_archive(draft_text)

    if not archive.is_file():
        if is_local_incident_archive(archive):
            print("[brev-support-evidence] skipped: referenced local incident archive is not present")
            print(f"[brev-support-evidence] draft={draft}")
            print(f"[brev-support-evidence] archive={archive}")
            return 0
        fail(f"referenced evidence archive is missing: {archive}")

    actual_sha = sha256_file(archive)
    if actual_sha != expected_sha:
        fail(f"evidence archive sha mismatch: expected {expected_sha}, got {actual_sha}")

    sidecar = Path(f"{archive}.sha256")
    if not sidecar.is_file():
        fail(f"missing evidence archive sha sidecar: {sidecar}")
    sidecar_text = read_text(sidecar)
    if expected_sha not in sidecar_text:
        fail(f"evidence archive sha sidecar does not contain expected sha: {sidecar}")

    texts = tar_texts(
        archive,
        (
            "README.md",
            "SHA256SUMS.txt",
            "brev_ls_instances_json.txt",
            "brev_healthcheck.txt",
            "brev_paid_safety_status.txt",
            "project_status_report.txt",
            "paid_preflight_hold_block.txt",
            "local_quality_checks.txt",
            "support_followup_draft.md",
            "brev_launchable_lifecycle_hold.md",
        ),
    )

    require_contains(texts["brev_ls_instances_json.txt"], '"workspaces": null', "Brev instance snapshot")
    require_contains(texts["brev_paid_safety_status.txt"], "visible_instances=0", "Brev safety status")
    require_contains(texts["brev_paid_safety_status.txt"], "status=SAFE_NO_VISIBLE_PAID_INSTANCE", "Brev safety status")
    require_contains(texts["paid_preflight_hold_block.txt"], "Brev/Launchable lifecycle hold is active", "paid preflight hold proof")
    require_contains(texts["paid_preflight_hold_block.txt"], "[exit_status] 2", "paid preflight hold proof")
    require_contains(texts["local_quality_checks.txt"], "[local-quality] passed", "local quality evidence")
    require_contains(texts["local_quality_checks.txt"], "[exit_status] 0", "local quality evidence")
    require_contains(texts["project_status_report.txt"], "Brev lifecycle hold | BLOCKED", "project status evidence")
    require_contains(texts["project_status_report.txt"], "Contact-smoke bundle | READY", "project status evidence")
    require_contains_any(
        texts["project_status_report.txt"],
        (
            "Phase 2 contact gate | BLOCKED",
            "Phase 2 contact gate | PASS",
        ),
        "project status evidence",
    )

    print("[brev-support-evidence] passed")
    print(f"[brev-support-evidence] draft={draft}")
    print(f"[brev-support-evidence] archive={archive}")
    print(f"[brev-support-evidence] sha256={actual_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
