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

CALIBRATION_STEPS_PER_PROBE="${RCA_JOINT_RESPONSE_CALIBRATION_STEPS_PER_PROBE:-8}"
CALIBRATION_TIMEOUT_SECONDS="${RCA_JOINT_RESPONSE_CALIBRATION_TIMEOUT_SECONDS:-900}"
SUMMARY_PATH="/workspace/artifacts/calibration/joint_position_action/latest_seed_${SEED}.json"

echo "[joint-response-suite] calibrating empirical JointPositionAction response"
"${SCRIPT_DIR}/run_remote_joint_response_calibration.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${CALIBRATION_STEPS_PER_PROBE}" \
  "${SEED}" \
  "${CALIBRATION_TIMEOUT_SECONDS}"

echo "[joint-response-suite] running down/up semantic probes with ${SUMMARY_PATH}"
RCA_ACTION_SEMANTICS_SCRIPTED_CONTROL_MODE=joint-response \
RCA_ACTION_SEMANTICS_EXTRA_AGENT_ARGS="--joint-response-json ${SUMMARY_PATH} --joint-response-damping ${RCA_JOINT_RESPONSE_DAMPING:-0.0001} --joint-response-max-delta ${RCA_JOINT_RESPONSE_MAX_DELTA:-0.04}" \
  "${SCRIPT_DIR}/run_remote_action_semantics_probe_suite.sh" \
    "${ENV_NAME}" \
    "${REMOTE_ROOT}" \
    "${COMPOSE_ROOT}" \
    "${TASK_NAME}" \
    "${NUM_ENVS}" \
    "${STEPS}" \
    "${SEED}"

echo "[joint-response-suite] PASS: calibrated joint-response down/up probes passed"
