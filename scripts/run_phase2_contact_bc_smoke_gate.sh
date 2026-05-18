#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_GATE_COMMAND="${RCA_GATE_COMMAND:-contact_bc_smoke}"
export RCA_GATE_TASK="${RCA_GATE_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
export RCA_GATE_INSTANCE_NAME="${RCA_GATE_INSTANCE_NAME:-isaac-phase2-contact-bc-smoke-l4}"
export RCA_GATE_INSTANCE_TYPE="${RCA_GATE_INSTANCE_TYPE:-g2-standard-4:nvidia-l4:1}"
export RCA_GATE_CREATE_TIMEOUT="${RCA_GATE_CREATE_TIMEOUT:-900}"
export RCA_GATE_READY_TIMEOUT_SECONDS="${RCA_GATE_READY_TIMEOUT_SECONDS:-900}"
export RCA_GATE_BUILD_STUCK_SECONDS="${RCA_GATE_BUILD_STUCK_SECONDS:-300}"
export RCA_GATE_DELETE_TIMEOUT_SECONDS="${RCA_GATE_DELETE_TIMEOUT_SECONDS:-1200}"
export RCA_GATE_EVAL_TIMEOUT_SECONDS="${RCA_GATE_EVAL_TIMEOUT_SECONDS:-1200}"
export RCA_GATE_STEPS="${RCA_GATE_STEPS:-400}"
export RCA_GATE_SEEDS="${RCA_GATE_SEEDS:-42}"
export RCA_BC_EPOCHS="${RCA_BC_EPOCHS:-250}"
export RCA_BC_TRACE_JSON="${RCA_BC_TRACE_JSON:-1}"
export RCA_BC_EVAL_EXTRA_ARGS="${RCA_BC_EVAL_EXTRA_ARGS:---deterministic-reset --socket-pos 0.22,0.04,0.22 --success-xy-tol 0.005 --success-z-tol 0.045 --success-rot-tol 0.18 --success-min-contact-force 0.5 --max-action-delta 0.05}"

exec "${SCRIPT_DIR}/run_guarded_phase2_gate.sh"
