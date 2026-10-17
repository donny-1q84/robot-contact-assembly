#!/usr/bin/env python3
"""Read-only macOS/Linux boot-session clock. No fallback or paid authority."""

from pathlib import Path
import re
import subprocess
import sys
import time

from paid_run_deadline import Clock


def boot_identity():
    if sys.platform == "darwin":
        result = subprocess.run(["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"],
                                stdin=subprocess.DEVNULL, capture_output=True,
                                timeout=2, check=True)
        if result.stderr:
            raise ValueError("kernel boot query returned diagnostics")
        raw = result.stdout
    elif sys.platform == "linux":
        # boot_id is stable for this boot; /random/uuid is NOT a substitute.
        raw = Path("/proc/sys/kernel/random/boot_id").read_bytes()
    else:
        raise ValueError("unsupported OS boot identity source")
    if not re.fullmatch(
            rb"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\n?", raw):
        raise ValueError("invalid kernel boot session UUID")
    value = raw.decode("ascii").strip().lower()
    if value == "00000000-0000-0000-0000-000000000000":
        raise ValueError("empty kernel boot session UUID")
    return sys.platform + ":" + value


def sample_os_clock():
    before = boot_identity()
    mono_start, wall_start = time.monotonic(), time.time()
    after = boot_identity()
    wall_end, mono_end = time.time(), time.monotonic()
    if before != after or wall_end < wall_start or mono_end < mono_start:
        raise ValueError("boot or clock changed during sampling")
    if mono_end - mono_start > 3 or wall_end - wall_start > 3:
        raise ValueError("OS clock sampling was delayed; no fresh timing claim")
    return Clock(wall_end, mono_end, after)
