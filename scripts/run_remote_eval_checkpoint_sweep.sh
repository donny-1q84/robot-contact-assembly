#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-v0}"
NUM_ENVS="${5:-32}"
STEPS="${6:-400}"
SEED="${7:-42}"
LOAD_RUN_REGEX="${8:-.*}"
CHECKPOINT_REGEX="${9:-model_.*\\.pt}"
MAX_CHECKPOINTS="${10:-0}"
EXPERIMENT_NAME="${11:-franka_peg_in_hole}"

"${SCRIPT_DIR}/sync_to_brev.sh" "${RCA_ENV_NAME}" "${RCA_REMOTE_ROOT}"

REMOTE_LOG_ROOT="${RCA_REMOTE_ROOT}/repo/robot-contact-assembly/logs/rsl_rl/${EXPERIMENT_NAME}"
RUN_DIR="$(
  ssh "${RCA_ENV_NAME}" \
    "find '${REMOTE_LOG_ROOT}' -mindepth 1 -maxdepth 1 -type d | grep -E '${LOAD_RUN_REGEX}' | sort | tail -n 1"
)"

if [[ -z "${RUN_DIR}" ]]; then
  echo "[checkpoint-sweep] no run matched regex=${LOAD_RUN_REGEX} under ${REMOTE_LOG_ROOT}" >&2
  exit 1
fi

mapfile -t CHECKPOINTS < <(
  ssh "${RCA_ENV_NAME}" \
    "find '${RUN_DIR}' -maxdepth 1 -type f -name 'model_*.pt' | sed 's#.*/##' | grep -E '${CHECKPOINT_REGEX}' | sort"
)

if [[ ${#CHECKPOINTS[@]} -eq 0 ]]; then
  echo "[checkpoint-sweep] no checkpoints matched regex=${CHECKPOINT_REGEX} in ${RUN_DIR}" >&2
  exit 1
fi

if [[ "${MAX_CHECKPOINTS}" =~ ^[0-9]+$ ]] && [[ "${MAX_CHECKPOINTS}" -gt 0 ]] && [[ ${#CHECKPOINTS[@]} -gt "${MAX_CHECKPOINTS}" ]]; then
  CHECKPOINTS=("${CHECKPOINTS[@]: -${MAX_CHECKPOINTS}}")
fi

echo "[checkpoint-sweep] task=${TASK_NAME}"
echo "[checkpoint-sweep] run_dir=${RUN_DIR}"
echo "[checkpoint-sweep] checkpoints=${#CHECKPOINTS[@]}"

for checkpoint in "${CHECKPOINTS[@]}"; do
  echo "[checkpoint-sweep] evaluating ${checkpoint}"
  bash "${SCRIPT_DIR}/run_remote_eval_policy.sh" \
    "${RCA_ENV_NAME}" \
    "${RCA_REMOTE_ROOT}" \
    "${RCA_REMOTE_COMPOSE_ROOT}" \
    "${TASK_NAME}" \
    "${NUM_ENVS}" \
    "${STEPS}" \
    "${SEED}" \
    "${LOAD_RUN_REGEX}" \
    "${checkpoint}"
done
