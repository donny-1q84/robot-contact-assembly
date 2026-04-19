#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

"${SCRIPT_DIR}/sync_to_brev.sh" "${RCA_ENV_NAME}" "${RCA_REMOTE_ROOT}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-Play-v0}"
NUM_ENVS="${5:-1}"
VIDEO_LENGTH="${6:-400}"
SEED="${7:-42}"
SCRIPTED_STEPS="${8:-${VIDEO_LENGTH}}"
EXTRA_PLAY_ARGS="${9:-}"
VIDEO_TIMEOUT_SECONDS="${RCA_VIDEO_TIMEOUT_SECONDS:-240}"
VIDEO_TIMEOUT_KILL_SECONDS="${RCA_VIDEO_TIMEOUT_KILL_SECONDS:-30}"
VIDEO_BACKEND="${RCA_VIDEO_BACKEND:-viewport}"
VIEWPORT_KIT_ARGS='--kit_args "--enable omni.replicator.core --enable omni.kit.material.library --enable omni.kit.viewport.rtx"'

if [[ "${VIDEO_BACKEND}" == "viewport" && "${EXTRA_PLAY_ARGS}" != *"--kit_args"* ]]; then
  if [[ -n "${EXTRA_PLAY_ARGS}" ]]; then
    EXTRA_PLAY_ARGS="${EXTRA_PLAY_ARGS} ${VIEWPORT_KIT_ARGS}"
  else
    EXTRA_PLAY_ARGS="${VIEWPORT_KIT_ARGS}"
  fi
fi

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_VIDEO_DIR="/workspace/artifacts/videos/scripted/${TIMESTAMP_UTC}"
REMOTE_LOG_PATH="${REMOTE_VIDEO_DIR}/record.log"
REMOTE_COMMAND_PATH="${REMOTE_VIDEO_DIR}/record_command.txt"
REMOTE_RUN_PATH="${REMOTE_VIDEO_DIR}/run_eval.sh"
REMOTE_HYDRA_DIR="/workspace/artifacts/hydra/scripted_video_${TIMESTAMP_UTC}"
REMOTE_SUMMARY_PATH="${REMOTE_VIDEO_DIR}/video_summary.json"
REMOTE_EVAL_VIDEO_DIR="${REMOTE_VIDEO_DIR}/eval"

echo "[record-scripted] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} video_length=${VIDEO_LENGTH} seed=${SEED}"
echo "[record-scripted] steps=${SCRIPTED_STEPS} timeout_seconds=${VIDEO_TIMEOUT_SECONDS} timeout_kill_seconds=${VIDEO_TIMEOUT_KILL_SECONDS}"
echo "[record-scripted] video_backend=${VIDEO_BACKEND}"
if [[ -n "${EXTRA_PLAY_ARGS}" ]]; then
  echo "[record-scripted] extra_play_args=${EXTRA_PLAY_ARGS}"
fi

rca_remote_container_exec "mkdir -p '${REMOTE_VIDEO_DIR}' '${REMOTE_EVAL_VIDEO_DIR}' '${REMOTE_HYDRA_DIR}'"
rca_remote_container_exec "cat > '${REMOTE_COMMAND_PATH}' <<'EOF'
timeout --foreground --signal=TERM --kill-after=${VIDEO_TIMEOUT_KILL_SECONDS}s ${VIDEO_TIMEOUT_SECONDS} bash '${REMOTE_RUN_PATH}'
EOF"
rca_remote_container_exec "cat > '${REMOTE_RUN_PATH}' <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
child_pid=""
cleanup() {
  if [[ -n "\${child_pid}" ]]; then
    kill "\${child_pid}" >/dev/null 2>&1 || true
    sleep 2
    kill -9 "\${child_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT TERM INT
export CARB_APP_PATH=/isaac-sim/kit
export ISAAC_PATH=/isaac-sim
export EXP_PATH=/isaac-sim/apps
export PYTHONPATH="${PYTHONPATH:-}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
source /isaac-sim/setup_python_env.sh
export RESOURCE_NAME=IsaacSim
export LD_PRELOAD=/isaac-sim/kit/libcarb.so
/isaac-sim/kit/python/bin/python3 scripts/scripted_agent.py --task ${TASK_NAME} --headless --video --video_backend ${VIDEO_BACKEND} --video_folder '${REMOTE_EVAL_VIDEO_DIR}' --video_length ${VIDEO_LENGTH} --steps ${SCRIPTED_STEPS} --num_envs ${NUM_ENVS} --seed ${SEED} --summary-json '${REMOTE_SUMMARY_PATH}' hydra.run.dir=${REMOTE_HYDRA_DIR} hydra.output_subdir=null ${EXTRA_PLAY_ARGS} &
child_pid=\$!
wait "\${child_pid}"
EOF
chmod +x '${REMOTE_RUN_PATH}'"

set +e
rca_remote_repo_exec "set -o pipefail && timeout --foreground --signal=TERM --kill-after=${VIDEO_TIMEOUT_KILL_SECONDS}s ${VIDEO_TIMEOUT_SECONDS} bash '${REMOTE_RUN_PATH}' 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
rca_remote_container_exec "pkill -f \"${REMOTE_SUMMARY_PATH}\" || true" >/dev/null 2>&1 || true
set -e

if [[ ${status} -ne 0 ]]; then
  if [[ ${status} -eq 124 ]]; then
    echo "[record-scripted] playback timed out after ${VIDEO_TIMEOUT_SECONDS}s" >&2
  fi
  echo "[record-scripted] playback failed with status=${status}" >&2
  echo "[record-scripted] inspect ${REMOTE_LOG_PATH} on the remote container" >&2
  exit "${status}"
fi

if ! rca_remote_container_exec "test -f '${REMOTE_SUMMARY_PATH}'" >/dev/null 2>&1; then
  echo "[record-scripted] scripted rollout completed but no summary was written" >&2
  exit 1
fi

if ! rca_remote_container_exec "find '${REMOTE_EVAL_VIDEO_DIR}' -maxdepth 1 -name '*.mp4' | grep -q ."; then
  echo "[record-scripted] scripted rollout completed but no mp4 artifacts were written" >&2
  exit 1
fi

echo "[record-scripted] video dir: ${REMOTE_VIDEO_DIR}"
echo "[record-scripted] command:   ${REMOTE_COMMAND_PATH}"
