#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_SCRIPTED_TRACE_JSON="${RCA_SCRIPTED_TRACE_JSON:-1}"
export RCA_GATE_COMMAND="${RCA_GATE_COMMAND:-scripted_eval}"
export RCA_GATE_TASK="${RCA_GATE_TASK:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
export RCA_GATE_INSTANCE_NAME="${RCA_GATE_INSTANCE_NAME:-isaac-phase2-jointik-l4}"
export RCA_GATE_INSTANCE_TYPE="${RCA_GATE_INSTANCE_TYPE:-g2-standard-4:nvidia-l4:1}"
export RCA_GATE_CREATE_TIMEOUT="${RCA_GATE_CREATE_TIMEOUT:-900}"
export RCA_GATE_READY_TIMEOUT_SECONDS="${RCA_GATE_READY_TIMEOUT_SECONDS:-900}"
export RCA_GATE_BUILD_STUCK_SECONDS="${RCA_GATE_BUILD_STUCK_SECONDS:-300}"
export RCA_GATE_EVAL_TIMEOUT_SECONDS="${RCA_GATE_EVAL_TIMEOUT_SECONDS:-420}"
export RCA_SCRIPTED_EVAL_RETRIES="${RCA_SCRIPTED_EVAL_RETRIES:-0}"
export RCA_GATE_STEPS="${RCA_GATE_STEPS:-800}"
export RCA_GATE_EXTRA_AGENT_ARGS="${RCA_GATE_EXTRA_AGENT_ARGS:---deterministic-reset --socket-pos 0.22,0.04,0.19 --scripted-control-mode joint-ik --joint-ik-step 0.08 --joint-limit-margin 0.02 --abs-control-mode waypoint --abs-pos-step 0.012 --abs-rot-step 0.12 --rotate-control-mode stateful-waypoint --hold-orientation-during-descend --insert-after-alignment --insert-descent-mode vertical --insert-vertical-step 0.018 --hold-orientation-during-insert --insert-abort-grace-steps 8 --insert-abort-xy-tol 0.03 --insert-abort-rot-tol 0.35 --stop-on-branch-jump --staged-approach --rotate-before-descend --debug-action-steps 8}"

exec "${SCRIPT_DIR}/run_guarded_phase2_gate.sh"
