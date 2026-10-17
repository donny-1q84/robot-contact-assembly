#!/usr/bin/env python3
"""Local candidate for restart-safe timing. No cloud commands or paid authority.

The production hold remains mandatory. This module does not install supervision,
authorize creation, identify a deletion target, or prove provider cleanup. Its
caller must obtain a stable OS boot identity, not invent a new one on restart.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path

import seated_time_budget as budget

PHASES = ("create", "ready", "bootstrap", "sync", "install", "xvfb")


def _number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


@dataclass(frozen=True)
class Clock:
    utc: float
    monotonic: float
    boot_id: str

    def __post_init__(self):
        if not _number(self.utc) or not _number(self.monotonic):
            raise ValueError("clock values must be finite nonnegative numbers")
        if not isinstance(self.boot_id, str) or not self.boot_id.strip():
            raise ValueError("stable boot identity required")


def offsets() -> dict[str, int]:
    budget.validate()
    prep = budget.PREPARATION_SECONDS
    workload = prep + budget.WORKLOAD_SECONDS
    cleanup_start = workload + budget.OUTER_KILL_SECONDS
    return {
        "preparation": prep,
        "workload": workload,
        "cleanup_start": cleanup_start,
        "cleanup_end": cleanup_start + budget.CLEANUP_RESERVE_SECONDS,
        "hard_end": budget.TTL_SECONDS,
    }


@dataclass(frozen=True)
class Contract:
    run_id: str
    organization_id: str
    target_name: str
    anchor: Clock

    def __post_init__(self):
        for value in (self.run_id, self.organization_id, self.target_name):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("run/organization/target scope must be explicit")
        if not isinstance(self.anchor, Clock):
            raise ValueError("clock anchor required")

    def payload(self) -> dict:
        return {
            "schema": "local-paid-deadline-candidate-v1",
            **asdict(self),
            "offset_seconds": offsets(),
            "absolute_deadlines_utc": {
                key: self.anchor.utc + value for key, value in offsets().items()
            },
        }


def _encoded(contract: Contract) -> bytes:
    return (json.dumps(contract.payload(), sort_keys=True, allow_nan=False,
                       separators=(",", ":")) + "\n").encode()


def freeze(path: Path, contract: Contract) -> str:
    """Create once before creation; an interrupted/partial write must fail closed.

    fsync is requested, but this is not a power-loss/disk-removal durability test.
    The digest must be retained separately by the future supervisor, not re-trusted
    from a modified contract. It is integrity evidence, not an authorization token.
    """
    encoded = _encoded(contract)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return hashlib.sha256(encoded).hexdigest()


def restore(path: Path, expected_sha256: str, *, run_id: str,
            organization_id: str, target_name: str) -> Contract:
    """No fresh anchor/TTL fallback if state, hash or scope is missing/wrong."""
    encoded = path.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("frozen timing contract digest mismatch")
    payload = json.loads(encoded)
    contract = Contract(payload["run_id"], payload["organization_id"],
                        payload["target_name"], Clock(**payload["anchor"]))
    if (contract.run_id, contract.organization_id, contract.target_name) != (
            run_id, organization_id, target_name):
        raise ValueError("frozen timing contract scope mismatch")
    if encoded != _encoded(contract):
        raise ValueError("schema/allocation/deadlines changed or noncanonical contract")
    return contract


def elapsed(contract: Contract, now: Clock) -> float:
    if now.boot_id != contract.anchor.boot_id:
        raise ValueError("boot changed: immediate recovery, never resume paid work")
    wall = now.utc - contract.anchor.utc
    monotonic = now.monotonic - contract.anchor.monotonic
    if wall < 0 or monotonic < 0:
        raise ValueError("clock precedes frozen anchor: immediate recovery required")
    # Wall-clock rollback cannot add time; suspend/wall-clock advance consumes it.
    return max(wall, monotonic)


def timing_status(contract: Contract, now: Clock) -> dict:
    result = {"paid_start_allowed": False, "production_supervision_validated": False}
    try:
        age = elapsed(contract, now)
    except ValueError as exc:
        return {**result, "status": "CLOCK_UNCERTAIN_RECOVER_NOW", "reason": str(exc)}
    remaining = {key: max(0.0, seconds - age) for key, seconds in offsets().items()}
    if age >= offsets()["hard_end"]:
        status = "HARD_DEADLINE_MISSED"
    elif age >= offsets()["cleanup_end"]:
        status = "CLEANUP_DEADLINE_MISSED"
    elif age >= offsets()["cleanup_start"]:
        status = "CLEANUP_DUE"
    elif age >= offsets()["workload"]:
        status = "WORKLOAD_STOP_DUE"
    elif age >= offsets()["preparation"]:
        status = "PREPARATION_CLOSED"
    else:
        status = "WITHIN_PREPARATION_WINDOW"
    return {**result, "status": status, "elapsed_seconds": age,
            "remaining_seconds": remaining}


def preparation_admission(contract: Contract, now: Clock, phases: list[dict]) -> dict:
    """Audit same-host phase receipts before allowing even a timing-only decision.

    Receipts must later be emitted around actual bounded commands by the SAME
    local lifecycle clock. Remote mtimes/log timestamps are not phase receipts.
    No shortened workload/cleanup is substituted for a late/missing preparation.
    """
    status = timing_status(contract, now)
    rejected = {**status, "workload_timing_admissible": False}
    if status["status"] != "WITHIN_PREPARATION_WINDOW":
        return {**rejected, "reason": "preparation admission deadline closed or uncertain"}
    if not isinstance(phases, list) or len(phases) != len(PHASES):
        return {**rejected, "reason": "all six ordered preparation receipts required"}
    previous = contract.anchor
    durations = {}
    try:
        for name, phase in zip(PHASES, phases):
            if set(phase) != {"name", "start", "end", "exit_code"}:
                raise ValueError("invalid phase receipt fields")
            if phase["name"] != name or type(phase["exit_code"]) is not int or phase["exit_code"] != 0:
                raise ValueError("missing/reordered/failed preparation phase")
            start, end = Clock(**phase["start"]), Clock(**phase["end"])
            for sample in (start, end):
                elapsed(contract, sample)
                if sample.utc < previous.utc or sample.monotonic < previous.monotonic:
                    raise ValueError("phase clocks overlap or regress")
                previous = sample
            if end.utc > now.utc or end.monotonic > now.monotonic:
                raise ValueError("phase evidence is from the future")
            durations[name] = end.monotonic - start.monotonic
    except (ValueError, TypeError, KeyError) as exc:
        return {**rejected, "reason": str(exc)}
    # The workload allocation includes wall + positive + disabled-seat; outer
    # termination and the full 300-second cleanup reservation remain untouched.
    return {**status, "workload_timing_admissible": True,
            "phase_seconds_same_clock": durations,
            "reason": "timing only; OS supervision, scope, account and physical gates still required"}
