#!/usr/bin/env python3
"""Temporary non-overridable paid-start hold after the r34 orphan incident.

This is containment, not a claim that independent cleanup is implemented.
Remove/replace the hold only with reviewed supervisor integration and real
parent/process-group termination evidence. Never add an environment bypass.
Read-only account checks, artifact recovery and deletion remain available.
"""

from __future__ import annotations

import sys
import os


def report() -> dict[str, object]:
    return {
        "status": "BLOCKED",
        "incident": "r34-interrupted-paid-supervision",
        "paid_start_allowed": False,
        "reason": "Independent cleanup did not survive interrupted execution.",
        "next_action": (
            "Implement and test OS-managed, target-scoped supervision with bounded "
            "pullback/deletion and an absolute deadline before any further paid start."
        ),
    }


def main() -> int:
    # The variable identifies a real independent run, not an authorization flag.
    # Both entrypoints re-read its live hosted receipt and frozen source binding.
    if os.environ.get("RCA_HOSTED_CLEANUP_RUN"):
        try:
            import paid_run_hosted as hosted
            hosted.check_before_create(os.environ.get("RCA_PAID_INSTANCE_NAME", ""))
            print("[paid-supervision] independent hosted owner ready; exact frozen target only")
            return 0
        except Exception as exc:
            print("[paid-supervision] BLOCKED: hosted receipt invalid (" + type(exc).__name__ + ")", file=sys.stderr)
            return 2
    state = report()
    print(f"[paid-supervision] BLOCKED: {state['reason']}", file=sys.stderr)
    print(f"[paid-supervision] {state['next_action']}", file=sys.stderr)
    print("[paid-supervision] No risk acknowledgement overrides this hold; no paid instance was created.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
