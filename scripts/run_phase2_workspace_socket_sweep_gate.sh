#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_SCRIPTED_TRACE_JSON="${RCA_SCRIPTED_TRACE_JSON:-1}"
export RCA_GATE_COMMAND="${RCA_GATE_COMMAND:-scripted_socket_sweep}"
export RCA_GATE_TASK="${RCA_GATE_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
export RCA_GATE_INSTANCE_NAME="${RCA_GATE_INSTANCE_NAME:-isaac-phase2-workspace-socket-sweep-l4}"
export RCA_GATE_INSTANCE_TYPE="${RCA_GATE_INSTANCE_TYPE:-g2-standard-4:nvidia-l4:1}"
export RCA_GATE_CREATE_TIMEOUT="${RCA_GATE_CREATE_TIMEOUT:-900}"
export RCA_GATE_READY_TIMEOUT_SECONDS="${RCA_GATE_READY_TIMEOUT_SECONDS:-900}"
export RCA_GATE_BUILD_STUCK_SECONDS="${RCA_GATE_BUILD_STUCK_SECONDS:-300}"
export RCA_GATE_DELETE_TIMEOUT_SECONDS="${RCA_GATE_DELETE_TIMEOUT_SECONDS:-1200}"
export RCA_GATE_EVAL_TIMEOUT_SECONDS="${RCA_GATE_EVAL_TIMEOUT_SECONDS:-900}"
export RCA_GATE_STEPS="${RCA_GATE_STEPS:-1600}"
export RCA_GATE_SEEDS="${RCA_GATE_SEEDS:-42}"
export RCA_SCRIPTED_EVAL_RETRIES="${RCA_SCRIPTED_EVAL_RETRIES:-0}"
export RCA_SOCKET_SWEEP_STOP_ON_SUCCESS="${RCA_SOCKET_SWEEP_STOP_ON_SUCCESS:-1}"

# Local trace analysis showed that the old socket pose (0.22, 0.04, 0.19) pushes
# near-seat steps into a low joint-2 margin. This sweep raises the socket and moves it
# gradually outward/centerward before spending more time on controller polish.
export RCA_SOCKET_SWEEP_POSITIONS="${RCA_SOCKET_SWEEP_POSITIONS:-0.22,0.04,0.22;0.24,0.03,0.22;0.26,0.02,0.22;0.28,0.00,0.22}"

export RCA_GATE_EXTRA_AGENT_ARGS="${RCA_GATE_EXTRA_AGENT_ARGS:---deterministic-reset --scripted-control-mode joint-ik --joint-ik-step 0.035 --joint-limit-margin 0.005 --abs-control-mode waypoint --abs-pos-step 0.010 --abs-rot-step 0.10 --rotate-control-mode stateful-waypoint --hold-orientation-during-descend --insert-after-alignment --insert-descent-mode joint-cache --insert-vertical-step 0.020 --joint-cache-step 0.020 --joint-cache-step-scale 0.55 --joint-cache-total-limit 0.60 --joint-cache-live-polish --hold-orientation-during-insert --polish-xy-tol 0.020 --polish-z-tol 0.050 --polish-rot-tol 0.20 --polish-rotation-mode current --settle-xy-tol 0.0045 --settle-rot-tol 0.18 --settle-rot-gain 0.55 --settle-rot-clamp 0.025 --insert-abort-grace-steps 4 --insert-abort-xy-tol 0.022 --insert-abort-rot-tol 0.45 --branch-jump-xy-tol 0.08 --staged-approach --rotate-before-descend --debug-action-steps 4}"

exec "${SCRIPT_DIR}/run_guarded_phase2_gate.sh"
