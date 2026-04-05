#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-Polish-v0}"
NUM_ENVS="${5:-32}"
MAX_ITERATIONS="${6:-50}"
SEED="${7:-42}"
RUN_NAME="${8:-phase1_polish_v2}"
LOAD_RUN_REGEX="${9:-.*phase1_fix6_formal.*}"
CHECKPOINT_NAME="${10:-model_299.pt}"
EVAL_STEPS="${11:-400}"
MAX_CHECKPOINTS="${12:-0}"

GPU_NAME="${GPU_NAME:-L40S}"
MIN_TOTAL_VRAM="${MIN_TOTAL_VRAM:-40}"
MIN_DISK="${MIN_DISK:-500}"
CREATE_TIMEOUT="${CREATE_TIMEOUT:-900}"

echo "[recreate] creating Brev instance ${ENV_NAME}"
/Users/Shenghan/bin/brev create "${ENV_NAME}" \
  --gpu-name "${GPU_NAME}" \
  --min-total-vram "${MIN_TOTAL_VRAM}" \
  --min-disk "${MIN_DISK}" \
  --stoppable \
  --timeout "${CREATE_TIMEOUT}"

echo "[recreate] bootstrapping remote workspace"
bash "${SCRIPT_DIR}/bootstrap_brev_workspace.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

echo "[recreate] syncing repository"
bash "${SCRIPT_DIR}/sync_to_brev.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

echo "[recreate] installing Isaac Lab runtime"
bash "${SCRIPT_DIR}/install_remote_isaaclab_runtime.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${COMPOSE_ROOT}"

echo "[recreate] checking runtime"
bash "${SCRIPT_DIR}/check_remote_runtime.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${COMPOSE_ROOT}"

echo "[recreate] running polish cycle"
bash "${SCRIPT_DIR}/run_remote_polish_cycle.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${NUM_ENVS}" \
  "${MAX_ITERATIONS}" \
  "${SEED}" \
  "${RUN_NAME}" \
  "${LOAD_RUN_REGEX}" \
  "${CHECKPOINT_NAME}" \
  "${EVAL_STEPS}" \
  "${MAX_CHECKPOINTS}"
