#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-8}"
SEED="${7:-42}"

DEFAULT_AGENT_ARGS=(
  --demo-reanchor-socket
  --demo-reanchor-initial-axial "${RCA_ACTION_SEMANTICS_INITIAL_AXIAL:-0.050}"
  --demo-reanchor-orientation current
  --demo-reanchor-settle-steps 0
  --scripted-control-mode "${RCA_ACTION_SEMANTICS_SCRIPTED_CONTROL_MODE:-joint-ik}"
  --abs-control-mode waypoint
  --abs-pos-step-mode component
  --abs-pos-step "${RCA_ACTION_SEMANTICS_ABS_POS_STEP:-0.004}"
  --abs-rot-step 0.0
  --action-semantics-probe-delta "${RCA_ACTION_SEMANTICS_PROBE_DELTA:-0,0,-0.0015}"
  --action-semantics-probe-frame "${RCA_ACTION_SEMANTICS_PROBE_FRAME:-world}"
  --debug-action-steps "${RCA_ACTION_SEMANTICS_DEBUG_STEPS:-4}"
)

if [[ -n "${RCA_ACTION_SEMANTICS_AGENT_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  AGENT_ARGS=(${RCA_ACTION_SEMANTICS_AGENT_ARGS})
else
  AGENT_ARGS=("${DEFAULT_AGENT_ARGS[@]}")
  if [[ -n "${RCA_ACTION_SEMANTICS_EXTRA_AGENT_ARGS:-}" ]]; then
    # shellcheck disable=SC2206
    EXTRA_AGENT_ARGS=(${RCA_ACTION_SEMANTICS_EXTRA_AGENT_ARGS})
    AGENT_ARGS+=("${EXTRA_AGENT_ARGS[@]}")
  fi
fi

RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
RCA_VALIDATE_ACTION_RESPONSE=1 \
RCA_VALIDATE_PEG_VIDEO_CANDIDATE=0 \
RCA_VALIDATE_TRACE_FRAME_ALIGNMENT=0 \
RCA_TRACE_ONLY_TIMEOUT_SECONDS="${RCA_ACTION_SEMANTICS_TIMEOUT_SECONDS:-240}" \
  "${SCRIPT_DIR}/run_remote_scripted_trace_only.sh" \
    "${ENV_NAME}" \
    "${REMOTE_ROOT}" \
    "${COMPOSE_ROOT}" \
    "${TASK_NAME}" \
    "${NUM_ENVS}" \
    "${STEPS}" \
    "${SEED}" \
    "${AGENT_ARGS[*]}"
