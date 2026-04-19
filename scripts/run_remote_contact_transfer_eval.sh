#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
REMOTE_COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-v0}"
EVAL_NUM_ENVS="${5:-32}"
EVAL_STEPS="${6:-400}"
SEED="${7:-42}"
LOAD_RUN="${8:-.*phase1_fix6_formal.*}"
CHECKPOINT="${9:-model_50.pt}"
VIDEO_LENGTH="${10:-400}"
EXTRA_EVAL_ARGS="${11:-}"
EXTRA_PLAY_ARGS="${12:-}"
VIDEO_NUM_ENVS="${RCA_VIDEO_NUM_ENVS:-1}"
VIDEO_REQUIRED="${RCA_VIDEO_REQUIRED:-0}"

echo "[contact-transfer] task=${TASK_NAME} eval_num_envs=${EVAL_NUM_ENVS} eval_steps=${EVAL_STEPS} seed=${SEED}"
echo "[contact-transfer] load_run=${LOAD_RUN} checkpoint=${CHECKPOINT}"
echo "[contact-transfer] video_required=${VIDEO_REQUIRED}"

"${SCRIPT_DIR}/run_remote_eval_policy.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${REMOTE_COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${EVAL_NUM_ENVS}" \
  "${EVAL_STEPS}" \
  "${SEED}" \
  "${LOAD_RUN}" \
  "${CHECKPOINT}" \
  "${EXTRA_EVAL_ARGS}"

set +e
"${SCRIPT_DIR}/run_remote_record_video.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${REMOTE_COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${VIDEO_NUM_ENVS}" \
  "${VIDEO_LENGTH}" \
  "${SEED}" \
  "${LOAD_RUN}" \
  "${CHECKPOINT}" \
  "${EXTRA_PLAY_ARGS}"
video_status=$?
set -e

if [[ ${video_status} -ne 0 ]]; then
  if [[ "${VIDEO_REQUIRED}" == "1" ]]; then
    echo "[contact-transfer] video stage failed with status=${video_status}" >&2
    exit "${video_status}"
  fi
  echo "[contact-transfer] warning: video stage failed with status=${video_status}; keeping eval artifacts" >&2
fi

echo "[contact-transfer] remote artifacts are ready under ${REMOTE_ROOT}/artifacts"
echo "[contact-transfer] pull them locally with:"
echo "  ./scripts/pull_artifacts.sh ${ENV_NAME} ${REMOTE_ROOT}"
