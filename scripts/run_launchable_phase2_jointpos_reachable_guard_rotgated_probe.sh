#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_LAUNCHABLE_JOINTPOS_PROBE_LABEL="${RCA_LAUNCHABLE_JOINTPOS_PROBE_LABEL:-jointpos-reachable-jointlimit-guard-rotgated-probe}"

# Start from the tuned guard result, but separate insertion depth from orientation repair.
# The tuned run reached axial=0.1449m but let rotation drift to 0.4466rad. A 0.35rad gate
# targets the high-rotation windows without freezing almost the entire insertion trajectory.
export RCA_LAUNCHABLE_SCRIPTED_STEPS="${RCA_LAUNCHABLE_SCRIPTED_STEPS:-2200}"
export RCA_LAUNCHABLE_TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-3300}"
export RCA_LAUNCHABLE_HOLD_ORIENTATION_DURING_INSERT="${RCA_LAUNCHABLE_HOLD_ORIENTATION_DURING_INSERT:-0}"
export RCA_LAUNCHABLE_INSERT_ROTATION_GATED_DESCENT="${RCA_LAUNCHABLE_INSERT_ROTATION_GATED_DESCENT:-1}"
export RCA_LAUNCHABLE_INSERT_DESCENT_ROT_TOL="${RCA_LAUNCHABLE_INSERT_DESCENT_ROT_TOL:-0.35}"

exec "${SCRIPT_DIR}/run_launchable_phase2_jointpos_reachable_guard_tuned_probe.sh" "$@"
