#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-Contact-Play-v0}"
STEPS_PER_PROBE="${5:-4}"
SEED="${6:-42}"
TIMEOUT_SECONDS="${7:-600}"
EXTRA_AGENT_ARGS="${8:-}"
RETRY_COUNT="${RCA_ACTION_CALIBRATION_RETRIES:-1}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_CALIBRATION_DIR="/workspace/artifacts/calibration/relative_ik_action/${TIMESTAMP_UTC}"
SUMMARY_PATH="${REMOTE_CALIBRATION_DIR}/seed_${SEED}.json"

echo "[action-calibration] env=${RCA_ENV_NAME} task=${TASK_NAME} steps_per_probe=${STEPS_PER_PROBE}"
echo "[action-calibration] seed=${SEED}"
echo "[action-calibration] timeout_seconds=${TIMEOUT_SECONDS}"
echo "[action-calibration] retries=${RETRY_COUNT}"
if [[ -n "${EXTRA_AGENT_ARGS}" ]]; then
  echo "[action-calibration] extra_agent_args=${EXTRA_AGENT_ARGS}"
fi
rca_remote_container_exec "mkdir -p '${REMOTE_CALIBRATION_DIR}'"

max_attempts=$((RETRY_COUNT + 1))
attempt=1
status=1

while (( attempt <= max_attempts )); do
  if (( attempt == 1 )); then
    LOG_PATH="${REMOTE_CALIBRATION_DIR}/seed_${SEED}.log"
  else
    LOG_PATH="${REMOTE_CALIBRATION_DIR}/seed_${SEED}_attempt_${attempt}.log"
  fi
  echo "[action-calibration] running attempt=${attempt}/${max_attempts} log=${LOG_PATH}"
  rca_remote_container_exec "rm -f '${SUMMARY_PATH}'"

  set +e
  rca_remote_repo_exec "set -o pipefail && timeout ${TIMEOUT_SECONDS} /isaac-sim/python.sh scripts/calibrate_relative_ik_action.py --task ${TASK_NAME} --headless --num_envs 1 --steps-per-probe ${STEPS_PER_PROBE} --seed ${SEED} --summary-json ${SUMMARY_PATH} ${EXTRA_AGENT_ARGS} 2>&1 | tee ${LOG_PATH}"
  status=$?
  if [[ ${status} -eq 0 ]]; then
    rca_remote_container_exec "test -s '${SUMMARY_PATH}'"
    status=$?
  fi
  set -e

  if [[ ${status} -eq 0 ]]; then
    break
  fi

  echo "[action-calibration] attempt=${attempt}/${max_attempts} failed with status=${status}" >&2
  if (( attempt < max_attempts )); then
    echo "[action-calibration] retrying in same instance after cleanup" >&2
    rca_remote_container_exec "pkill -f 'scripts/calibrate_relative_ik_action.py' || true"
    sleep 5
  fi
  attempt=$((attempt + 1))
done

if [[ ${status} -ne 0 ]]; then
  echo "[action-calibration] failed after ${max_attempts} attempt(s)" >&2
  exit "${status}"
fi

echo "[action-calibration] summaries:"
rca_remote_container_exec "ls -1 '${REMOTE_CALIBRATION_DIR}'"
echo "[action-calibration] output dir: ${REMOTE_CALIBRATION_DIR}"
