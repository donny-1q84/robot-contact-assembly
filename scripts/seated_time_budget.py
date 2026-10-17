#!/usr/bin/env python3
"""Reviewed seated diagnostic time allocation; no cloud or physics operations."""
import argparse

PREPARATION_SECONDS = 1080
WALL_SECONDS = 420
WALL_KILL_SECONDS = 10
CASE_SECONDS = 360
CASE_KILL_SECONDS = 10
CASE_REAP_SECONDS = 10
WORKLOAD_OVERHEAD_SECONDS = 30
WORKLOAD_SECONDS = (WALL_SECONDS + WALL_KILL_SECONDS
                    + 2 * (CASE_SECONDS + CASE_KILL_SECONDS + CASE_REAP_SECONDS)
                    + WORKLOAD_OVERHEAD_SECONDS)
OUTER_KILL_SECONDS = 60
CLEANUP_RESERVE_SECONDS = 300
TTL_SECONDS = 2700
MARGIN_SECONDS = 40


def validate():
    allocated = (PREPARATION_SECONDS + WORKLOAD_SECONDS + OUTER_KILL_SECONDS
                 + CLEANUP_RESERVE_SECONDS + MARGIN_SECONDS)
    if allocated != TTL_SECONDS or WORKLOAD_SECONDS != 1220:
        raise ValueError("seated time allocation must retain both cases and cleanup within 45min")


def shell_values():
    validate()
    return {
        "RCA_SEATED_PREPARATION_SECONDS": PREPARATION_SECONDS,
        "RCA_SEATED_WORKLOAD_SECONDS": WORKLOAD_SECONDS,
        "RCA_SEATED_WALL_SECONDS": WALL_SECONDS,
        "RCA_SEATED_WALL_KILL_SECONDS": WALL_KILL_SECONDS,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shell", action="store_true", required=True)
    parser.parse_args()
    for key, value in shell_values().items():
        print(f"{key}={value}")
