#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-v0}"
NUM_ENVS="${5:-32}"
STEPS="${6:-400}"
SEED="${7:-42}"
LOAD_RUN="${8:-.*}"
CHECKPOINT="${9:-model_.*.pt}"
EXTRA_EVAL_ARGS="${10:-}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_EVAL_DIR="/workspace/artifacts/evaluations/policy/${TIMESTAMP_UTC}"
REMOTE_LOG_PATH="${REMOTE_EVAL_DIR}/eval.log"
REMOTE_SUMMARY_PATH="${REMOTE_EVAL_DIR}/summary.json"
REMOTE_COMMAND_PATH="${REMOTE_EVAL_DIR}/eval_command.txt"
REMOTE_HYDRA_DIR="/workspace/artifacts/hydra/eval_${TIMESTAMP_UTC}"

echo "[eval-policy] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} steps=${STEPS} seed=${SEED}"
echo "[eval-policy] load_run=${LOAD_RUN} checkpoint=${CHECKPOINT}"
if [[ -n "${EXTRA_EVAL_ARGS}" ]]; then
  echo "[eval-policy] extra_eval_args=${EXTRA_EVAL_ARGS}"
fi

rca_remote_container_exec "mkdir -p '${REMOTE_EVAL_DIR}' '${REMOTE_HYDRA_DIR}'"
rca_remote_container_exec "cat > '${REMOTE_COMMAND_PATH}' <<'EOF'
/isaac-sim/python.sh scripts/evaluate_rsl_rl_checkpoint.py --task ${TASK_NAME} --headless --num_envs ${NUM_ENVS} --steps ${STEPS} --seed ${SEED} --load_run '${LOAD_RUN}' --checkpoint '${CHECKPOINT}' --summary-json '${REMOTE_SUMMARY_PATH}' hydra.run.dir=${REMOTE_HYDRA_DIR} hydra.output_subdir=null ${EXTRA_EVAL_ARGS}
EOF"

set +e
rca_remote_repo_exec "set -o pipefail && /isaac-sim/python.sh scripts/evaluate_rsl_rl_checkpoint.py --task ${TASK_NAME} --headless --num_envs ${NUM_ENVS} --steps ${STEPS} --seed ${SEED} --load_run '${LOAD_RUN}' --checkpoint '${CHECKPOINT}' --summary-json '${REMOTE_SUMMARY_PATH}' hydra.run.dir=${REMOTE_HYDRA_DIR} hydra.output_subdir=null ${EXTRA_EVAL_ARGS} 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
set -e
if [[ ${status} -ne 0 ]]; then
  echo "[eval-policy] evaluation failed with status=${status}" >&2
  echo "[eval-policy] inspect ${REMOTE_LOG_PATH} on the remote container" >&2
  exit "${status}"
fi

echo "[eval-policy] eval dir: ${REMOTE_EVAL_DIR}"
echo "[eval-policy] summary:  ${REMOTE_SUMMARY_PATH}"
echo "[eval-policy] command:  ${REMOTE_COMMAND_PATH}"
