#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-120}"
SEED_CSV="${7:-42,43,44,45,46}"
TIMEOUT_SECONDS="${8:-900}"
EXTRA_AGENT_ARGS="${9:-}"
SCRIPTED_AGENT_ARGS="${RCA_SCRIPTED_AGENT_ARGS:-}"
RETRY_COUNT="${RCA_SCRIPTED_EVAL_RETRIES:-1}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_EVAL_DIR="/workspace/artifacts/evaluations/scripted/${TIMESTAMP_UTC}"

echo "[scripted-eval] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} steps=${STEPS}"
echo "[scripted-eval] seeds=${SEED_CSV}"
echo "[scripted-eval] timeout_seconds=${TIMEOUT_SECONDS}"
echo "[scripted-eval] retries=${RETRY_COUNT}"
if [[ -n "${EXTRA_AGENT_ARGS}" ]]; then
  echo "[scripted-eval] extra_agent_args=${EXTRA_AGENT_ARGS}"
fi
if [[ -n "${SCRIPTED_AGENT_ARGS}" ]]; then
  echo "[scripted-eval] scripted_agent_args=${SCRIPTED_AGENT_ARGS}"
fi
rca_remote_container_exec "mkdir -p '${REMOTE_EVAL_DIR}'"

for seed in ${SEED_CSV//,/ }; do
  SUMMARY_PATH="${REMOTE_EVAL_DIR}/seed_${seed}.json"
  max_attempts=$((RETRY_COUNT + 1))
  attempt=1
  seed_status=1

  while (( attempt <= max_attempts )); do
    if (( attempt == 1 )); then
      LOG_PATH="${REMOTE_EVAL_DIR}/seed_${seed}.log"
    else
      LOG_PATH="${REMOTE_EVAL_DIR}/seed_${seed}_attempt_${attempt}.log"
    fi
    echo "[scripted-eval] running seed=${seed} attempt=${attempt}/${max_attempts} log=${LOG_PATH}"
    rca_remote_container_exec "rm -f '${SUMMARY_PATH}'"

    set +e
    rca_remote_repo_exec "set -o pipefail && timeout ${TIMEOUT_SECONDS} /isaac-sim/python.sh scripts/scripted_agent.py --task ${TASK_NAME} --headless --num_envs ${NUM_ENVS} --steps ${STEPS} --seed ${seed} --summary-json ${SUMMARY_PATH} ${SCRIPTED_AGENT_ARGS} ${EXTRA_AGENT_ARGS} 2>&1 | tee ${LOG_PATH}"
    status=$?
    if [[ ${status} -eq 0 ]]; then
      rca_remote_container_exec "test -s '${SUMMARY_PATH}'"
      status=$?
    fi
    set -e

    if [[ ${status} -eq 0 ]]; then
      seed_status=0
      break
    fi

    echo "[scripted-eval] seed=${seed} attempt=${attempt}/${max_attempts} failed with status=${status}" >&2
    echo "[scripted-eval] inspect ${LOG_PATH} on the remote container for startup or controller errors" >&2
    if (( attempt < max_attempts )); then
      echo "[scripted-eval] retrying seed=${seed} in the same instance after cleanup" >&2
      rca_remote_container_exec "pkill -f 'scripts/scripted_agent.py' || true"
      sleep 5
    fi
    attempt=$((attempt + 1))
  done

  if [[ ${seed_status} -ne 0 ]]; then
    echo "[scripted-eval] seed=${seed} failed after ${max_attempts} attempt(s)" >&2
    exit "${status}"
  fi
done

echo "[scripted-eval] summaries:"
rca_remote_container_exec "ls -1 '${REMOTE_EVAL_DIR}'"
echo "[scripted-eval] output dir: ${REMOTE_EVAL_DIR}"
