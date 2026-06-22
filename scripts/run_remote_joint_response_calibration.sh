#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
STEPS_PER_PROBE="${5:-8}"
SEED="${6:-42}"
TIMEOUT_SECONDS="${7:-900}"
EXTRA_AGENT_ARGS="${8:-}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_CALIBRATION_DIR="/workspace/artifacts/calibration/joint_position_action/${TIMESTAMP_UTC}"
SUMMARY_PATH="${REMOTE_CALIBRATION_DIR}/seed_${SEED}.json"
LATEST_SUMMARY_PATH="/workspace/artifacts/calibration/joint_position_action/latest_seed_${SEED}.json"
CHECK_DOWN_PATH="${REMOTE_CALIBRATION_DIR}/seed_${SEED}_down_command_check.log"
CHECK_UP_PATH="${REMOTE_CALIBRATION_DIR}/seed_${SEED}_up_command_check.log"

echo "[joint-response-calibration] env=${RCA_ENV_NAME} task=${TASK_NAME} steps_per_probe=${STEPS_PER_PROBE}"
echo "[joint-response-calibration] seed=${SEED}"
echo "[joint-response-calibration] timeout_seconds=${TIMEOUT_SECONDS}"
if [[ -n "${EXTRA_AGENT_ARGS}" ]]; then
  echo "[joint-response-calibration] extra_agent_args=${EXTRA_AGENT_ARGS}"
fi

rca_remote_container_exec "mkdir -p '${REMOTE_CALIBRATION_DIR}'"
rca_remote_container_exec "rm -f '${SUMMARY_PATH}'"

rca_remote_repo_exec "set -o pipefail && timeout ${TIMEOUT_SECONDS} /isaac-sim/python.sh scripts/calibrate_joint_position_action.py --task ${TASK_NAME} --headless --num_envs 1 --steps-per-probe ${STEPS_PER_PROBE} --seed ${SEED} --summary-json ${SUMMARY_PATH} ${EXTRA_AGENT_ARGS} 2>&1 | tee '${REMOTE_CALIBRATION_DIR}/seed_${SEED}.log'"
rca_remote_container_exec "test -s '${SUMMARY_PATH}'"

rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/joint_response_control.py '${SUMMARY_PATH}' --desired-delta 0,0,-0.0015 2>&1 | tee '${CHECK_DOWN_PATH}'"
rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/joint_response_control.py '${SUMMARY_PATH}' --desired-delta 0,0,0.0015 2>&1 | tee '${CHECK_UP_PATH}'"

rca_remote_container_exec "cp '${SUMMARY_PATH}' '${LATEST_SUMMARY_PATH}'"
echo "[joint-response-calibration] latest summary: ${LATEST_SUMMARY_PATH}"
echo "[joint-response-calibration] down_check: ${CHECK_DOWN_PATH}"
echo "[joint-response-calibration] up_check: ${CHECK_UP_PATH}"
echo "[joint-response-calibration] output dir: ${REMOTE_CALIBRATION_DIR}"
rca_remote_container_exec "ls -1 '${REMOTE_CALIBRATION_DIR}'"
