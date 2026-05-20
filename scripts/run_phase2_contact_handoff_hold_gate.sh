#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export RCA_GATE_COMMAND="${RCA_GATE_COMMAND:-contact_handoff_baseline}"
export RCA_GATE_PROFILE="${RCA_GATE_PROFILE:-cheap}"
export RCA_GATE_TASK="${RCA_GATE_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
export RCA_GATE_INSTANCE_NAME="${RCA_GATE_INSTANCE_NAME:-isaac-phase2-contact-handoff-hold-l4}"
export RCA_GATE_CREATE_TIMEOUT="${RCA_GATE_CREATE_TIMEOUT:-900}"
export RCA_GATE_READY_TIMEOUT_SECONDS="${RCA_GATE_READY_TIMEOUT_SECONDS:-900}"
export RCA_GATE_BUILD_STUCK_SECONDS="${RCA_GATE_BUILD_STUCK_SECONDS:-300}"
export RCA_GATE_DELETE_TIMEOUT_SECONDS="${RCA_GATE_DELETE_TIMEOUT_SECONDS:-1200}"
export RCA_GATE_EVAL_TIMEOUT_SECONDS="${RCA_GATE_EVAL_TIMEOUT_SECONDS:-1200}"
export RCA_GATE_STEPS="${RCA_GATE_STEPS:-400}"
export RCA_GATE_SEEDS="${RCA_GATE_SEEDS:-42}"
export RCA_BASELINE_CONTROLLER="${RCA_BASELINE_CONTROLLER:-current-joint}"
export RCA_BASELINE_TRACE_JSON="${RCA_BASELINE_TRACE_JSON:-1}"
export RCA_BASELINE_LOCAL_PRELOAD_TRACE="${RCA_BASELINE_LOCAL_PRELOAD_TRACE:-${REPO_ROOT}/artifacts/evaluations/scripted/2026-05-17T23-32-18Z/seed_42_trace.json}"
export RCA_BASELINE_REMOTE_PRELOAD_TRACE="${RCA_BASELINE_REMOTE_PRELOAD_TRACE:-/workspace/artifacts/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json}"
export RCA_BASELINE_EVAL_EXTRA_ARGS="${RCA_BASELINE_EVAL_EXTRA_ARGS:---deterministic-reset --socket-pos 0.22,0.04,0.22 --preload-trace-end-step 1543 --success-xy-tol 0.005 --success-z-tol 0.045 --success-rot-tol 0.18 --success-min-contact-force 0.5 --near-contact-xy-tol 0.015 --near-contact-z-tol 0.060 --near-contact-rot-tol 0.35 --near-contact-min-force 0.2}"

if [[ ! -s "${RCA_BASELINE_LOCAL_PRELOAD_TRACE}" ]]; then
  echo "[handoff-hold-gate] missing preload trace: ${RCA_BASELINE_LOCAL_PRELOAD_TRACE}" >&2
  exit 2
fi

exec "${SCRIPT_DIR}/run_guarded_phase2_gate.sh"
