#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-1200}"
SEED="${7:-42}"

DEFAULT_AGENT_ARGS=(
  --demo-reanchor-socket
  --demo-reanchor-initial-axial 0.050
  --demo-reanchor-orientation current
  --demo-reanchor-settle-steps 0
  --scripted-control-mode joint-ik
  --abs-control-mode waypoint
  --abs-pos-step-mode component
  --approach-axis world-z
  --joint-ik-step 0.035
  --insert-descent-mode joint-cache
  --joint-cache-live-polish
  --insert-pos-step 0.010
  --insert-rot-step 0.100
  --polish-xy-tol 0.020
  --polish-z-tol 0.050
  --polish-rot-tol 0.200
  --polish-rotation-mode current
  --settle-contact-retention
  --success-min-contact-force 0.5
  --final-contact-servo
  --final-contact-servo-entry-xy-tol "${RCA_FINAL_CONTACT_SERVO_ENTRY_XY_TOL:-0.008}"
  --final-contact-servo-entry-z-tol "${RCA_FINAL_CONTACT_SERVO_ENTRY_Z_TOL:-0.050}"
  --final-contact-servo-entry-rot-tol "${RCA_FINAL_CONTACT_SERVO_ENTRY_ROT_TOL:-0.180}"
  --final-contact-servo-exit-xy-tol "${RCA_FINAL_CONTACT_SERVO_EXIT_XY_TOL:-0.012}"
  --final-contact-servo-exit-rot-tol "${RCA_FINAL_CONTACT_SERVO_EXIT_ROT_TOL:-0.250}"
  --final-contact-servo-xy-gain "${RCA_FINAL_CONTACT_SERVO_XY_GAIN:-0.85}"
  --final-contact-servo-xy-clamp "${RCA_FINAL_CONTACT_SERVO_XY_CLAMP:-0.0025}"
  --final-contact-servo-z-gain "${RCA_FINAL_CONTACT_SERVO_Z_GAIN:-1.0}"
  --final-contact-servo-z-step "${RCA_FINAL_CONTACT_SERVO_Z_STEP:-0.002}"
  --final-contact-servo-orientation-mode "${RCA_FINAL_CONTACT_SERVO_ORIENTATION_MODE:-current}"
  --stop-on-branch-jump
)

if [[ "${RCA_FINAL_CONTACT_SERVO_HOLD_Z_WHEN_AXIAL_READY:-1}" == "1" ]]; then
  DEFAULT_AGENT_ARGS+=(--final-contact-servo-hold-z-when-axial-ready)
fi

if [[ "${RCA_FINAL_CONTACT_SERVO_METRIC_Z:-0}" == "1" ]]; then
  DEFAULT_AGENT_ARGS+=(--final-contact-servo-metric-z)
fi

if [[ "${RCA_FINAL_CONTACT_SERVO_METRIC_XY:-0}" == "1" ]]; then
  DEFAULT_AGENT_ARGS+=(--final-contact-servo-metric-xy)
fi

if [[ "${RCA_FINAL_CONTACT_SERVO_METRIC_ERROR:-0}" == "1" ]]; then
  DEFAULT_AGENT_ARGS+=(--final-contact-servo-metric-error)
fi

if [[ -n "${RCA_FINAL_CONTACT_SERVO_AGENT_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  AGENT_ARGS=(${RCA_FINAL_CONTACT_SERVO_AGENT_ARGS})
else
  AGENT_ARGS=("${DEFAULT_AGENT_ARGS[@]}")
fi

RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
  "${SCRIPT_DIR}/run_remote_scripted_trace_only.sh" \
    "${ENV_NAME}" \
    "${REMOTE_ROOT}" \
    "${COMPOSE_ROOT}" \
    "${TASK_NAME}" \
    "${NUM_ENVS}" \
    "${STEPS}" \
    "${SEED}" \
    "${AGENT_ARGS[*]}"
