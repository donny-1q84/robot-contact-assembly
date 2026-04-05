#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-v0}"
NUM_ENVS="${5:-1}"
VIDEO_LENGTH="${6:-400}"
SEED="${7:-42}"
LOAD_RUN="${8:-.*}"
CHECKPOINT="${9:-model_.*.pt}"
EXTRA_PLAY_ARGS="${10:-}"
EXPERIMENT_NAME="${RCA_EXPERIMENT_NAME:-franka_peg_in_hole}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_VIDEO_DIR="/workspace/artifacts/videos/policy/${TIMESTAMP_UTC}"
REMOTE_LOG_PATH="${REMOTE_VIDEO_DIR}/record.log"
REMOTE_COMMAND_PATH="${REMOTE_VIDEO_DIR}/record_command.txt"
REMOTE_HYDRA_DIR="/workspace/artifacts/hydra/video_${TIMESTAMP_UTC}"

echo "[record-video] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} video_length=${VIDEO_LENGTH} seed=${SEED}"
echo "[record-video] load_run=${LOAD_RUN} checkpoint=${CHECKPOINT}"
if [[ -n "${EXTRA_PLAY_ARGS}" ]]; then
  echo "[record-video] extra_play_args=${EXTRA_PLAY_ARGS}"
fi

rca_remote_container_exec "mkdir -p '${REMOTE_VIDEO_DIR}' '${REMOTE_HYDRA_DIR}'"
rca_remote_container_exec "cat > '${REMOTE_COMMAND_PATH}' <<'EOF'
/isaac-sim/python.sh scripts/evaluate_rsl_rl_checkpoint.py --task ${TASK_NAME} --headless --video --video_length ${VIDEO_LENGTH} --steps ${VIDEO_LENGTH} --num_envs ${NUM_ENVS} --seed ${SEED} --load_run '${LOAD_RUN}' --checkpoint '${CHECKPOINT}' hydra.run.dir=${REMOTE_HYDRA_DIR} hydra.output_subdir=null ${EXTRA_PLAY_ARGS}
EOF"

set +e
rca_remote_repo_exec "set -o pipefail && /isaac-sim/python.sh scripts/evaluate_rsl_rl_checkpoint.py --task ${TASK_NAME} --headless --video --video_length ${VIDEO_LENGTH} --steps ${VIDEO_LENGTH} --num_envs ${NUM_ENVS} --seed ${SEED} --load_run '${LOAD_RUN}' --checkpoint '${CHECKPOINT}' hydra.run.dir=${REMOTE_HYDRA_DIR} hydra.output_subdir=null ${EXTRA_PLAY_ARGS} 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
set -e
if [[ ${status} -ne 0 ]]; then
  echo "[record-video] playback failed with status=${status}" >&2
  echo "[record-video] inspect ${REMOTE_LOG_PATH} on the remote container" >&2
  exit "${status}"
fi

rca_remote_container_exec "
set -euo pipefail
LOG_ROOT=\"/workspace/robot-contact-assembly/logs/rsl_rl/${EXPERIMENT_NAME}\"
LATEST_RUN=\"\$(find \"\${LOG_ROOT}\" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1 || true)\"
VIDEO_SOURCE_DIR=\"\${LATEST_RUN}/videos/eval\"
if [[ ! -d \"\${VIDEO_SOURCE_DIR}\" ]]; then
  echo '[record-video] no evaluation video directory found under latest run' >&2
  exit 1
fi
mkdir -p '${REMOTE_VIDEO_DIR}/eval'
cp -R \"\${VIDEO_SOURCE_DIR}/.\" '${REMOTE_VIDEO_DIR}/eval/'
"

echo "[record-video] video dir: ${REMOTE_VIDEO_DIR}"
echo "[record-video] command:   ${REMOTE_COMMAND_PATH}"
