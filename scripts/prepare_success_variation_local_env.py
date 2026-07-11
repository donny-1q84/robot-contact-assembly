#!/usr/bin/env python3
"""Write a fail-closed local env file from a success-variation run packet.

This helper prepares the ignored
`configs/success_variation_batch_run.local.env` file without granting paid-run
permission. It copies the packet's one-run env template and verifies the three
dangerous acknowledgement markers remain set to 0:

- RCA_ALLOW_PAID_BREV_CREATE=0
- RCA_BREV_CREDITS_VERIFIED=0
- RCA_ACK_BREV_LIFECYCLE_RISK=0

It does not create, delete, copy to, or execute on Brev instances.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


sys.dont_write_bytecode = True

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKET = REPO_ROOT / "artifacts" / "analysis" / "success_variation_run_packet_2026-06-25.json"
DEFAULT_OUTPUT = REPO_ROOT / "configs" / "success_variation_batch_run.local.env"
ACK_MARKERS = (
    "RCA_ALLOW_PAID_BREV_CREATE=0",
    "RCA_BREV_CREDITS_VERIFIED=0",
    "RCA_ACK_BREV_LIFECYCLE_RISK=0",
)


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


def _load_packet(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"run packet JSON root must be an object: {_rel(path)}")
    return payload


def _env_template(packet: dict[str, Any]) -> str:
    template = packet.get("one_run_local_env_template")
    if not isinstance(template, str) or not template.strip():
        raise RuntimeError("run packet is missing one_run_local_env_template")
    for marker in ACK_MARKERS:
        if marker not in template:
            raise RuntimeError(f"run packet template must keep fail-closed marker: {marker}")
    forbidden_markers = (
        "RCA_ALLOW_PAID_BREV_CREATE=1",
        "RCA_BREV_CREDITS_VERIFIED=1",
        "RCA_ACK_BREV_LIFECYCLE_RISK=1",
    )
    for marker in forbidden_markers:
        if marker in template:
            raise RuntimeError(f"run packet template must not grant paid-run acknowledgement: {marker}")
    if not template.endswith("\n"):
        template += "\n"
    return template


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Overwrite an existing local env file.")
    args = parser.parse_args()

    packet_path = _resolve_repo_path(args.packet)
    output_path = _resolve_repo_path(args.output)
    packet = _load_packet(packet_path)
    template = _env_template(packet)

    if output_path.exists() and not args.force:
        print(f"[success-variation-local-env] exists: {_rel(output_path)}")
        print("[success-variation-local-env] use --force to rewrite the fail-closed template")
        return 2

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(template, encoding="utf-8")
    print(f"[success-variation-local-env] wrote: {_rel(output_path)}")
    print("[success-variation-local-env] acknowledgements remain fail-closed: paid_create=0 credits_verified=0 lifecycle_ack=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
