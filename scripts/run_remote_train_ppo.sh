#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-v0}"
NUM_ENVS="${5:-256}"
MAX_ITERATIONS="${6:-300}"
SEED="${7:-42}"
RUN_NAME="${8:-phase1_baseline}"
EXTRA_TRAIN_ARGS="${9:-}"
EXPERIMENT_NAME="${RCA_EXPERIMENT_NAME:-franka_peg_in_hole}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_SESSION_DIR="/workspace/artifacts/train_runs/${TIMESTAMP_UTC}_${RUN_NAME}"
REMOTE_LOG_PATH="${REMOTE_SESSION_DIR}/train.log"
REMOTE_METADATA_PATH="${REMOTE_SESSION_DIR}/train_metadata.env"
REMOTE_COMMAND_PATH="${REMOTE_SESSION_DIR}/train_command.txt"

echo "[train-ppo] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} max_iterations=${MAX_ITERATIONS} seed=${SEED}"
echo "[train-ppo] run_name=${RUN_NAME} experiment_name=${EXPERIMENT_NAME}"
if [[ -n "${EXTRA_TRAIN_ARGS}" ]]; then
  echo "[train-ppo] extra_train_args=${EXTRA_TRAIN_ARGS}"
fi

rca_remote_container_exec "mkdir -p '${REMOTE_SESSION_DIR}'"

set +e
rca_remote_repo_exec "set -o pipefail && /isaac-sim/python.sh scripts/train_rsl_rl.py --task ${TASK_NAME} --headless --num_envs ${NUM_ENVS} --seed ${SEED} --max_iterations ${MAX_ITERATIONS} --run_name ${RUN_NAME} ${EXTRA_TRAIN_ARGS} 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
set -e
if [[ ${status} -ne 0 ]]; then
  echo "[train-ppo] training failed with status=${status}" >&2
  echo "[train-ppo] inspect ${REMOTE_LOG_PATH} on the remote container" >&2
  exit "${status}"
fi

rca_remote_container_exec "
set -euo pipefail
cat > '${REMOTE_COMMAND_PATH}' <<'EOF'
/isaac-sim/python.sh scripts/train_rsl_rl.py --task ${TASK_NAME} --headless --num_envs ${NUM_ENVS} --seed ${SEED} --max_iterations ${MAX_ITERATIONS} --run_name ${RUN_NAME} ${EXTRA_TRAIN_ARGS}
EOF
LOG_ROOT=\"/workspace/IsaacLab/logs/rsl_rl/${EXPERIMENT_NAME}\"
LATEST_RUN=\"\$(find \"\${LOG_ROOT}\" -mindepth 1 -maxdepth 1 -type d -name \"*${RUN_NAME}*\" | sort | tail -n 1 || true)\"
LATEST_CHECKPOINT=\"\"
if [[ -n \"\${LATEST_RUN}\" ]]; then
  LATEST_CHECKPOINT=\"\$(find \"\${LATEST_RUN}\" -maxdepth 1 -type f -name 'model_*.pt' | sort | tail -n 1 || true)\"
fi
{
  echo \"task=${TASK_NAME}\"
  echo \"experiment_name=${EXPERIMENT_NAME}\"
  echo \"run_name=${RUN_NAME}\"
  echo \"seed=${SEED}\"
  echo \"num_envs=${NUM_ENVS}\"
  echo \"max_iterations=${MAX_ITERATIONS}\"
  echo \"log_root=\${LOG_ROOT}\"
  echo \"latest_run=\${LATEST_RUN}\"
  echo \"latest_checkpoint=\${LATEST_CHECKPOINT}\"
} > '${REMOTE_METADATA_PATH}'
if [[ -n \"\${LATEST_CHECKPOINT}\" ]]; then
  cp \"\${LATEST_CHECKPOINT}\" '${REMOTE_SESSION_DIR}/'
fi
"

echo "[train-ppo] session dir: ${REMOTE_SESSION_DIR}"
echo "[train-ppo] metadata:    ${REMOTE_METADATA_PATH}"
echo "[train-ppo] command:     ${REMOTE_COMMAND_PATH}"
