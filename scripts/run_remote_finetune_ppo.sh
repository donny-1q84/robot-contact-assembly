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
RUN_NAME="${8:-phase1_polish}"
LOAD_RUN_REGEX="${9:-.*phase1_fix6_formal.*}"
CHECKPOINT_NAME="${10:-model_299.pt}"
EXTRA_TRAIN_ARGS="${11:-}"

RESUME_ARGS="--resume --load_run '${LOAD_RUN_REGEX}' --checkpoint ${CHECKPOINT_NAME}"
if [[ -n "${EXTRA_TRAIN_ARGS}" ]]; then
  RESUME_ARGS="${RESUME_ARGS} ${EXTRA_TRAIN_ARGS}"
fi

exec "${SCRIPT_DIR}/run_remote_train_ppo.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${NUM_ENVS}" \
  "${MAX_ITERATIONS}" \
  "${SEED}" \
  "${RUN_NAME}" \
  "${RESUME_ARGS}"
