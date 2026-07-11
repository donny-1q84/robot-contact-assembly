#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_LAUNCHABLE_JOINTPOS_PROBE_LABEL="${RCA_LAUNCHABLE_JOINTPOS_PROBE_LABEL:-jointpos-reachable-jointlimit-guard-neardepth-rotgate-probe}"

# Follow-up to the adaptive rotpolish trace analysis. The prior wrappers allowed
# full redescend once rot dropped below 0.35rad, but the strict success gate is
# 0.18rad and traces showed redescend beginning around rot=0.24rad near depth.
# Keep the early soft gate, then tighten only near insertion depth.
export RCA_LAUNCHABLE_SCRIPTED_STEPS="${RCA_LAUNCHABLE_SCRIPTED_STEPS:-3000}"
export RCA_LAUNCHABLE_TIMEOUT_SECONDS="${RCA_LAUNCHABLE_TIMEOUT_SECONDS:-4500}"
export RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_Z_TOL="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_Z_TOL:-0.065}"
export RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_ROT_TOL="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_ROT_TOL:-0.22}"
export RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_DESCENT_SCALE="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_DESCENT_SCALE:-0.10}"
export RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_MIN_DESCENT_STEP="${RCA_LAUNCHABLE_INSERT_ROTATION_GATE_NEAR_DEPTH_MIN_DESCENT_STEP:-0.0005}"

exec "${SCRIPT_DIR}/run_launchable_phase2_jointpos_reachable_guard_softgated_probe.sh" "$@"
