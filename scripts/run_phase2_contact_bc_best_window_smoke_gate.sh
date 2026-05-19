#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export RCA_GATE_COMMAND="${RCA_GATE_COMMAND:-contact_bc_smoke}"
export RCA_GATE_TASK="${RCA_GATE_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
export RCA_GATE_INSTANCE_NAME="${RCA_GATE_INSTANCE_NAME:-isaac-phase2-contact-bc-best-window-l4}"
export RCA_GATE_INSTANCE_TYPE="${RCA_GATE_INSTANCE_TYPE:-g2-standard-4:nvidia-l4:1}"
export RCA_GATE_CREATE_TIMEOUT="${RCA_GATE_CREATE_TIMEOUT:-900}"
export RCA_GATE_READY_TIMEOUT_SECONDS="${RCA_GATE_READY_TIMEOUT_SECONDS:-900}"
export RCA_GATE_BUILD_STUCK_SECONDS="${RCA_GATE_BUILD_STUCK_SECONDS:-300}"
export RCA_GATE_DELETE_TIMEOUT_SECONDS="${RCA_GATE_DELETE_TIMEOUT_SECONDS:-1200}"
export RCA_GATE_EVAL_TIMEOUT_SECONDS="${RCA_GATE_EVAL_TIMEOUT_SECONDS:-1200}"
export RCA_GATE_STEPS="${RCA_GATE_STEPS:-400}"
export RCA_GATE_SEEDS="${RCA_GATE_SEEDS:-42}"
export RCA_BC_EPOCHS="${RCA_BC_EPOCHS:-300}"
export RCA_BC_TRACE_JSON="${RCA_BC_TRACE_JSON:-1}"
export RCA_BC_LOCAL_DATASET="${RCA_BC_LOCAL_DATASET:-${REPO_ROOT}/artifacts/datasets/phase2_contact_bc_best_window/phase2_contact_bc_best_window_dataset.jsonl}"
export RCA_BC_REMOTE_DATASET="${RCA_BC_REMOTE_DATASET:-/workspace/artifacts/datasets/phase2_contact_bc_best_window/phase2_contact_bc_best_window_dataset.jsonl}"
export RCA_BC_CHECKPOINT="${RCA_BC_CHECKPOINT:-/workspace/artifacts/policies/phase2_contact_bc_best_window/bc_mlp.pt}"
export RCA_BC_LOCAL_PRELOAD_TRACE="${RCA_BC_LOCAL_PRELOAD_TRACE:-${REPO_ROOT}/artifacts/evaluations/scripted/2026-05-17T23-32-18Z/seed_42_trace.json}"
export RCA_BC_REMOTE_PRELOAD_TRACE="${RCA_BC_REMOTE_PRELOAD_TRACE:-/workspace/artifacts/preload_traces/2026-05-17T23-32-18Z_seed_42_trace.json}"
export RCA_BC_EVAL_EXTRA_ARGS="${RCA_BC_EVAL_EXTRA_ARGS:---deterministic-reset --socket-pos 0.22,0.04,0.22 --preload-trace-end-step 1543 --success-xy-tol 0.005 --success-z-tol 0.045 --success-rot-tol 0.18 --success-min-contact-force 0.5 --max-action-delta 0.05}"

if [[ ! -s "${RCA_BC_LOCAL_DATASET}" ]]; then
  echo "[best-window-gate] missing dataset: ${RCA_BC_LOCAL_DATASET}" >&2
  echo "[best-window-gate] generate it with:" >&2
  echo "  python3 scripts/extract_contact_demo_dataset.py --profile best-window --output artifacts/datasets/phase2_contact_bc_best_window/phase2_contact_bc_best_window_dataset.jsonl" >&2
  exit 2
fi
if [[ ! -s "${RCA_BC_LOCAL_PRELOAD_TRACE}" ]]; then
  echo "[best-window-gate] missing preload trace: ${RCA_BC_LOCAL_PRELOAD_TRACE}" >&2
  exit 2
fi

exec "${SCRIPT_DIR}/run_guarded_phase2_gate.sh"
