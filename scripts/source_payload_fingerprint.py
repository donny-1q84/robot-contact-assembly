#!/usr/bin/env python3
"""Compute the deterministic runtime-source fingerprint for the contact-smoke gate.

The Launchable tarball can include documentation and local runbooks, but those
files do not affect the Isaac runtime behavior that the contact-smoke gate
validates. Keep this fingerprint scoped to the runtime extension plus the smoke
runner itself, so a documentation-only edit after a PASS log does not force an
unnecessary paid smoke rerun.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


EXCLUDED_DIRS = {
    ".claude",
    ".git",
    "artifacts",
    "logs",
    "videos",
    "checkpoints",
    "tmp",
    "__pycache__",
}
EXCLUDED_SUFFIXES = {
    ".key",
    ".pem",
    ".pyc",
}
EXCLUDED_NAMES = {
    ".DS_Store",
    ".env",
    ".rca_launchable_source_manifest.txt",
}
EXCLUDED_NAME_PREFIXES = (
    ".env.",
)
EXCLUDED_NAME_FRAGMENTS = (
    "credential",
    "private",
    "secret",
)
INCLUDED_PATHS = {
    "scripts/contact_physics_smoke.py",
    "scripts/run_launchable_contact_physics_smoke.sh",
}
INCLUDED_PREFIXES = (
    "source/robot_contact_assembly_tasks/",
)
FINGERPRINT_SCOPE = "runtime-v1"


def _is_excluded(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    if any(part in EXCLUDED_DIRS or part.endswith(".egg-info") for part in rel.parts[:-1]):
        return True
    name = rel.name
    if name in EXCLUDED_NAMES:
        return True
    if any(name.startswith(prefix) for prefix in EXCLUDED_NAME_PREFIXES):
        return True
    if any(fragment in name.lower() for fragment in EXCLUDED_NAME_FRAGMENTS):
        return True
    if any(name.endswith(suffix) for suffix in EXCLUDED_SUFFIXES):
        return True
    if name.endswith(".egg-info"):
        return True
    return False


def _is_runtime_source(path: Path, root: Path) -> bool:
    rel = path.relative_to(root).as_posix()
    return rel in INCLUDED_PATHS or any(rel.startswith(prefix) for prefix in INCLUDED_PREFIXES)


def source_payload_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    root = root.resolve()
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and _is_runtime_source(path, root) and not _is_excluded(path, root)
    ]
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--scope", action="store_true", help="Print the fingerprint scope/version instead of the hash.")
    args = parser.parse_args()
    if args.scope:
        print(FINGERPRINT_SCOPE)
        return 0
    print(source_payload_fingerprint(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
