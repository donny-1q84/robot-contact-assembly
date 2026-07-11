#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_LAUNCHABLE_JOINTPOS_PROBE_LABEL="${RCA_LAUNCHABLE_JOINTPOS_PROBE_LABEL:-jointpos-reachable-jointlimit-guard-softgated-probe}"

# Follow up the hard rotation-gated run, which protected joint margin but froze descent
# for too many insertion steps. This keeps the same orientation gate, but allows a
# bounded Z descent while rotation is being repaired.
export RCA_LAUNCHABLE_SCRIPTED_STEPS="${RCA_LAUNCHABLE_SCRIPTED_STEPS:-2400}"
export RCA_LAUNCHABLE_TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-3600}"
export RCA_LAUNCHABLE_HOLD_ORIENTATION_DURING_INSERT="${RCA_LAUNCHABLE_HOLD_ORIENTATION_DURING_INSERT:-0}"
export RCA_LAUNCHABLE_INSERT_ROTATION_GATED_DESCENT="${RCA_LAUNCHABLE_INSERT_ROTATION_GATED_DESCENT:-1}"
export RCA_LAUNCHABLE_INSERT_DESCENT_ROT_TOL="${RCA_LAUNCHABLE_INSERT_DESCENT_ROT_TOL:-0.35}"
export RCA_LAUNCHABLE_INSERT_ROTATION_GATE_DESCENT_SCALE="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_DESCENT_SCALE:-0.25}"
export RCA_LAUNCHABLE_INSERT_ROTATION_GATE_MIN_DESCENT_STEP="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_MIN_DESCENT_STEP:-0.002}"

exec "${SCRIPT_DIR}/run_launchable_phase2_jointpos_reachable_guard_tuned_probe.sh" "$@"
