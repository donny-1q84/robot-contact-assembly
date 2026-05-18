#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-400}"
SEED="${7:-42}"
CHECKPOINT="${8:-/workspace/artifacts/policies/phase2_contact_bc/bc_mlp.pt}"
TIMEOUT_SECONDS="${9:-900}"
EXTRA_EVAL_ARGS="${10:-}"
TRACE_JSON_ENABLED="${RCA_BC_TRACE_JSON:-1}"

"${SCRIPT_DIR}/sync_to_brev.sh" "${RCA_ENV_NAME}" "${RCA_REMOTE_ROOT}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_EVAL_DIR="/workspace/artifacts/evaluations/bc_policy/${TIMESTAMP_UTC}"
REMOTE_LOG_PATH="${REMOTE_EVAL_DIR}/eval.log"
REMOTE_SUMMARY_PATH="${REMOTE_EVAL_DIR}/summary.json"
REMOTE_TRACE_PATH="${REMOTE_EVAL_DIR}/trace.json"
REMOTE_COMMAND_PATH="${REMOTE_EVAL_DIR}/eval_command.txt"
TRACE_ARG=""
if [[ "${TRACE_JSON_ENABLED}" == "1" ]]; then
  TRACE_ARG="--trace-json '${REMOTE_TRACE_PATH}'"
fi

echo "[eval-bc] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} steps=${STEPS} seed=${SEED}"
echo "[eval-bc] checkpoint=${CHECKPOINT}"
echo "[eval-bc] timeout_seconds=${TIMEOUT_SECONDS}"

rca_remote_container_exec "mkdir -p '${REMOTE_EVAL_DIR}'"
rca_remote_container_exec "cat > '${REMOTE_COMMAND_PATH}' <<'EOF'
/isaac-sim/python.sh scripts/evaluate_contact_bc_policy.py --task '${TASK_NAME}' --headless --num_envs '${NUM_ENVS}' --steps '${STEPS}' --seed '${SEED}' --checkpoint '${CHECKPOINT}' --summary-json '${REMOTE_SUMMARY_PATH}' ${TRACE_ARG} ${EXTRA_EVAL_ARGS}
EOF"

set +e
rca_remote_repo_exec "set -o pipefail && timeout ${TIMEOUT_SECONDS} /isaac-sim/python.sh scripts/evaluate_contact_bc_policy.py --task '${TASK_NAME}' --headless --num_envs '${NUM_ENVS}' --steps '${STEPS}' --seed '${SEED}' --checkpoint '${CHECKPOINT}' --summary-json '${REMOTE_SUMMARY_PATH}' ${TRACE_ARG} ${EXTRA_EVAL_ARGS} 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
set -e
if [[ ${status} -ne 0 ]]; then
  echo "[eval-bc] evaluation failed with status=${status}" >&2
  echo "[eval-bc] inspect ${REMOTE_LOG_PATH}" >&2
  exit "${status}"
fi

echo "[eval-bc] eval dir: ${REMOTE_EVAL_DIR}"
echo "[eval-bc] summary:  ${REMOTE_SUMMARY_PATH}"
if [[ "${TRACE_JSON_ENABLED}" == "1" ]]; then
  echo "[eval-bc] trace:    ${REMOTE_TRACE_PATH}"
fi
echo "[eval-bc] command:  ${REMOTE_COMMAND_PATH}"
