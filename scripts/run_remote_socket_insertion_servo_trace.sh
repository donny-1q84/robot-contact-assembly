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
  --scripted-control-mode "${RCA_SOCKET_INSERTION_SERVO_CONTROL_MODE:-joint-ik}"
  --abs-control-mode waypoint
  --abs-pos-step-mode component
  --approach-axis world-z
  --joint-ik-step 0.035
  --insert-descent-mode joint-cache
  --joint-cache-live-polish
  --insert-pos-step 0.010
  --insert-rot-step 0.100
  --polish-xy-tol 0.020
  --polish-z-tol 0.055
  --polish-rot-tol 0.300
  --polish-rotation-mode current
  --settle-contact-retention
  --success-min-contact-force 0.5
  --socket-insertion-servo
  --socket-insertion-servo-entry-xy-tol "${RCA_SOCKET_INSERTION_SERVO_ENTRY_XY_TOL:-0.014}"
  --socket-insertion-servo-entry-z-tol "${RCA_SOCKET_INSERTION_SERVO_ENTRY_Z_TOL:-0.055}"
  --socket-insertion-servo-entry-rot-tol "${RCA_SOCKET_INSERTION_SERVO_ENTRY_ROT_TOL:-0.300}"
  --socket-insertion-servo-exit-xy-tol "${RCA_SOCKET_INSERTION_SERVO_EXIT_XY_TOL:-0.020}"
  --socket-insertion-servo-exit-z-tol "${RCA_SOCKET_INSERTION_SERVO_EXIT_Z_TOL:-0.070}"
  --socket-insertion-servo-exit-rot-tol "${RCA_SOCKET_INSERTION_SERVO_EXIT_ROT_TOL:-0.500}"
  --socket-insertion-servo-xy-gain "${RCA_SOCKET_INSERTION_SERVO_XY_GAIN:-0.85}"
  --socket-insertion-servo-xy-clamp "${RCA_SOCKET_INSERTION_SERVO_XY_CLAMP:-0.0025}"
  --socket-insertion-servo-z-gain "${RCA_SOCKET_INSERTION_SERVO_Z_GAIN:-1.0}"
  --socket-insertion-servo-z-step "${RCA_SOCKET_INSERTION_SERVO_Z_STEP:-0.0015}"
  --socket-insertion-servo-contact-preload-step "${RCA_SOCKET_INSERTION_SERVO_CONTACT_PRELOAD_STEP:-0.0010}"
  --socket-insertion-servo-contact-boundary-min-force "${RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_MIN_FORCE:-0.25}"
  --socket-insertion-servo-contact-boundary-tol "${RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_TOL:-0.0010}"
  --socket-insertion-servo-contact-boundary-step "${RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_STEP:-0.00015}"
  --socket-insertion-servo-contact-boundary-xy-gain "${RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_XY_GAIN:-0.0}"
  --socket-insertion-servo-contact-boundary-xy-clamp "${RCA_SOCKET_INSERTION_SERVO_CONTACT_BOUNDARY_XY_CLAMP:-0.0}"
  --socket-insertion-servo-rot-step "${RCA_SOCKET_INSERTION_SERVO_ROT_STEP:-0.030}"
  --stop-on-branch-jump
)

if [[ "${RCA_SOCKET_INSERTION_SERVO_MAINTAIN_CONTACT_PRELOAD:-0}" == "1" ]]; then
  DEFAULT_AGENT_ARGS+=(--socket-insertion-servo-maintain-contact-preload)
fi

if [[ -n "${RCA_SOCKET_INSERTION_SERVO_DESCEND_XY_TOL:-}" ]]; then
  DEFAULT_AGENT_ARGS+=(--socket-insertion-servo-descend-xy-tol "${RCA_SOCKET_INSERTION_SERVO_DESCEND_XY_TOL}")
fi

if [[ -n "${RCA_SOCKET_INSERTION_SERVO_DESCEND_ROT_TOL:-}" ]]; then
  DEFAULT_AGENT_ARGS+=(--socket-insertion-servo-descend-rot-tol "${RCA_SOCKET_INSERTION_SERVO_DESCEND_ROT_TOL}")
fi

if [[ -n "${RCA_SOCKET_INSERTION_SERVO_AGENT_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  AGENT_ARGS=(${RCA_SOCKET_INSERTION_SERVO_AGENT_ARGS})
else
  AGENT_ARGS=("${DEFAULT_AGENT_ARGS[@]}")
fi
if [[ -n "${RCA_SOCKET_INSERTION_SERVO_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_AGENT_ARGS=(${RCA_SOCKET_INSERTION_SERVO_EXTRA_ARGS})
  AGENT_ARGS+=("${EXTRA_AGENT_ARGS[@]}")
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
