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

DOWN_DELTA="${RCA_ACTION_SEMANTICS_PROBE_DELTA_DOWN:-0,0,-0.0015}"
UP_DELTA="${RCA_ACTION_SEMANTICS_PROBE_DELTA_UP:-0,0,0.0015}"

run_probe() {
  local label="$1"
  local delta="$2"

  echo "[action-semantics-suite] running ${label} probe delta=${delta}"
  env -u RCA_ACTION_SEMANTICS_AGENT_ARGS \
    RCA_ACTION_SEMANTICS_PROBE_DELTA="${delta}" \
    "${SCRIPT_DIR}/run_remote_action_semantics_probe_trace.sh" \
      "${ENV_NAME}" \
      "${REMOTE_ROOT}" \
      "${COMPOSE_ROOT}" \
      "${TASK_NAME}" \
      "${NUM_ENVS}" \
      "${STEPS}" \
      "${SEED}"
}

run_probe "down" "${DOWN_DELTA}"
sleep 2
run_probe "up" "${UP_DELTA}"

echo "[action-semantics-suite] PASS: down/up action-response probes both passed"
