#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export RCA_SCRIPTED_TRACE_JSON="${RCA_SCRIPTED_TRACE_JSON:-1}"
export RCA_GATE_COMMAND="${RCA_GATE_COMMAND:-scripted_eval}"
export RCA_GATE_TASK="${RCA_GATE_TASK:-RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0}"
export RCA_GATE_INSTANCE_NAME="${RCA_GATE_INSTANCE_NAME:-isaac-phase2-control-relik-l4}"
export RCA_GATE_INSTANCE_TYPE="${RCA_GATE_INSTANCE_TYPE:-g2-standard-4:nvidia-l4:1}"
export RCA_GATE_CREATE_TIMEOUT="${RCA_GATE_CREATE_TIMEOUT:-900}"
export RCA_GATE_READY_TIMEOUT_SECONDS="${RCA_GATE_READY_TIMEOUT_SECONDS:-900}"
export RCA_GATE_BUILD_STUCK_SECONDS="${RCA_GATE_BUILD_STUCK_SECONDS:-300}"
export RCA_GATE_DELETE_TIMEOUT_SECONDS="${RCA_GATE_DELETE_TIMEOUT_SECONDS:-1200}"
export RCA_GATE_EVAL_TIMEOUT_SECONDS="${RCA_GATE_EVAL_TIMEOUT_SECONDS:-900}"
export RCA_GATE_STEPS="${RCA_GATE_STEPS:-1900}"
export RCA_GATE_SEEDS="${RCA_GATE_SEEDS:-42}"
export RCA_SCRIPTED_EVAL_RETRIES="${RCA_SCRIPTED_EVAL_RETRIES:-0}"

# Control-mode comparison candidate:
# - DifferentialInverseKinematicsActionCfg with relative 6D pose deltas
# - scripted agent sends Cartesian delta actions directly to the task action term
# - no joint-cache replay, because the task action space is already Cartesian delta IK
export RCA_GATE_EXTRA_AGENT_ARGS="${RCA_GATE_EXTRA_AGENT_ARGS:---deterministic-reset --socket-pos 0.22,0.04,0.22 --scripted-control-mode mdp --position-control-mode direct --pos-gain 2.0 --rot-gain 2.0 --pos-clamp 0.08 --rot-clamp 0.30 --action-axis-signs 1,1,1 --rotate-control-mode stateful-waypoint --hold-orientation-during-descend --insert-after-alignment --insert-descent-mode vertical --insert-vertical-step 0.020 --hold-orientation-during-insert --polish-xy-tol 0.020 --polish-z-tol 0.050 --polish-rot-tol 0.20 --polish-rotation-mode current --polish-pos-gain 1.2 --polish-pos-clamp 0.008 --polish-rot-gain 0.55 --polish-rot-clamp 0.025 --settle-xy-tol 0.0045 --settle-rot-tol 0.18 --settle-pos-gain 0.8 --settle-pos-clamp 0.004 --settle-z-gain 0.8 --settle-z-clamp 0.004 --settle-rot-gain 0.55 --settle-rot-clamp 0.025 --settle-contact-retention --settle-contact-min-force 0.0 --settle-contact-preload-step 0.010 --settle-contact-force-aware-xy --settle-contact-force-scale 1.0 --settle-contact-force-xy-gain 0.003 --settle-contact-force-xy-clamp 0.002 --settle-contact-force-xy-sign 1.0 --settle-contact-xy-tol 0.005 --settle-contact-z-tol 0.045 --settle-contact-rot-tol 0.20 --settle-contact-exit-xy-tol 0.008 --settle-contact-exit-z-tol 0.055 --settle-contact-exit-rot-tol 0.24 --insert-abort-grace-steps 4 --insert-abort-xy-tol 0.022 --insert-abort-rot-tol 0.45 --branch-jump-xy-tol 0.08 --staged-approach --rotate-before-descend --success-xy-tol 0.005 --success-z-tol 0.045 --success-rot-tol 0.18 --success-min-contact-force 0.5 --debug-action-steps 4}"

exec "${SCRIPT_DIR}/run_guarded_phase2_gate.sh"
