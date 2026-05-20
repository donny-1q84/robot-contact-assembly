#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_GATE_INSTANCE_NAME="${RCA_GATE_INSTANCE_NAME:-isaac-phase2-contact-handoff-preload-dir-l4}"
export RCA_GATE_BUILD_STUCK_SECONDS="${RCA_GATE_BUILD_STUCK_SECONDS:-180}"
export RCA_GATE_READY_TIMEOUT_SECONDS="${RCA_GATE_READY_TIMEOUT_SECONDS:-600}"
export RCA_GATE_CREATE_TIMEOUT="${RCA_GATE_CREATE_TIMEOUT:-600}"
export RCA_BASELINE_CONTROLLER="preload-direction"
export RCA_BASELINE_EVAL_EXTRA_ARGS="${RCA_BASELINE_EVAL_EXTRA_ARGS:---deterministic-reset --socket-pos 0.22,0.04,0.22 --preload-trace-end-step 1543 --success-xy-tol 0.005 --success-z-tol 0.045 --success-rot-tol 0.18 --success-min-contact-force 0.5 --near-contact-xy-tol 0.015 --near-contact-z-tol 0.060 --near-contact-rot-tol 0.35 --near-contact-min-force 0.2 --max-action-delta 0.02 --preload-direction-hold-gain 0.35 --preload-direction-scale 1.0}"

exec "${SCRIPT_DIR}/run_phase2_contact_handoff_hold_gate.sh"
