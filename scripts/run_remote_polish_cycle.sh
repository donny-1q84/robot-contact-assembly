#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

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
EVAL_STEPS="${11:-400}"
MAX_CHECKPOINTS="${12:-0}"

echo "[polish-cycle] finetune ${RUN_NAME} from ${LOAD_RUN_REGEX}:${CHECKPOINT_NAME}"
bash "${SCRIPT_DIR}/run_remote_finetune_ppo.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${NUM_ENVS}" \
  "${MAX_ITERATIONS}" \
  "${SEED}" \
  "${RUN_NAME}" \
  "${LOAD_RUN_REGEX}" \
  "${CHECKPOINT_NAME}"

echo "[polish-cycle] sweep checkpoints for ${RUN_NAME}"
bash "${SCRIPT_DIR}/run_remote_eval_checkpoint_sweep.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${NUM_ENVS}" \
  "${EVAL_STEPS}" \
  "${SEED}" \
  ".*${RUN_NAME}.*" \
  'model_.*\.pt' \
  "${MAX_CHECKPOINTS}"

echo "[polish-cycle] capture runtime manifest"
bash "${SCRIPT_DIR}/capture_remote_runtime_manifest.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${COMPOSE_ROOT}"

echo "[polish-cycle] pull artifacts to local archive"
bash "${SCRIPT_DIR}/pull_artifacts.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${REPO_ROOT}/artifacts"

echo "[polish-cycle] local summary"
python3 "${SCRIPT_DIR}/summarize_eval_sweep.py" \
  --eval-root "${REPO_ROOT}/artifacts/evaluations/policy" \
  --checkpoint-substring "${RUN_NAME}" \
  --dedupe-checkpoint
