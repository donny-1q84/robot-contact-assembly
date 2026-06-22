#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

"${SCRIPT_DIR}/sync_to_brev.sh" "${RCA_ENV_NAME}" "${RCA_REMOTE_ROOT}"

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-v0}"
NUM_ENVS="${5:-1}"
VIDEO_LENGTH="${6:-400}"
SEED="${7:-42}"
LOAD_RUN="${8:-.*}"
CHECKPOINT="${9:-model_.*.pt}"
EXTRA_PLAY_ARGS="${10:-}"
EXPERIMENT_NAME="${RCA_EXPERIMENT_NAME:-franka_peg_in_hole}"
VIDEO_TIMEOUT_SECONDS="${RCA_VIDEO_TIMEOUT_SECONDS:-240}"
VIDEO_TIMEOUT_KILL_SECONDS="${RCA_VIDEO_TIMEOUT_KILL_SECONDS:-30}"
VIDEO_BACKEND="${RCA_VIDEO_BACKEND:-viewport}"
AUTO_VIEWPORT_KIT_ARGS="${RCA_AUTO_VIEWPORT_KIT_ARGS:-0}"
VIEWPORT_KIT_ARGS='--kit_args "--enable omni.replicator.core --enable omni.kit.material.library --enable omni.kit.viewport.rtx"'

if [[ "${AUTO_VIEWPORT_KIT_ARGS}" == "1" && "${VIDEO_BACKEND}" == "viewport" && "${EXTRA_PLAY_ARGS}" != *"--kit_args"* ]]; then
  if [[ -n "${EXTRA_PLAY_ARGS}" ]]; then
    EXTRA_PLAY_ARGS="${EXTRA_PLAY_ARGS} ${VIEWPORT_KIT_ARGS}"
  else
    EXTRA_PLAY_ARGS="${VIEWPORT_KIT_ARGS}"
  fi
fi

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_VIDEO_DIR="/workspace/artifacts/videos/policy/${TIMESTAMP_UTC}"
REMOTE_LOG_PATH="${REMOTE_VIDEO_DIR}/record.log"
REMOTE_COMMAND_PATH="${REMOTE_VIDEO_DIR}/record_command.txt"
REMOTE_RUN_PATH="${REMOTE_VIDEO_DIR}/run_eval.sh"
REMOTE_HYDRA_DIR="/workspace/artifacts/hydra/video_${TIMESTAMP_UTC}"
REMOTE_SUMMARY_PATH="${REMOTE_VIDEO_DIR}/video_summary.json"

echo "[record-video] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} video_length=${VIDEO_LENGTH} seed=${SEED}"
echo "[record-video] load_run=${LOAD_RUN} checkpoint=${CHECKPOINT}"
echo "[record-video] timeout_seconds=${VIDEO_TIMEOUT_SECONDS}"
echo "[record-video] timeout_kill_seconds=${VIDEO_TIMEOUT_KILL_SECONDS}"
echo "[record-video] video_backend=${VIDEO_BACKEND}"
echo "[record-video] auto_viewport_kit_args=${AUTO_VIEWPORT_KIT_ARGS}"
if [[ -n "${EXTRA_PLAY_ARGS}" ]]; then
  echo "[record-video] extra_play_args=${EXTRA_PLAY_ARGS}"
fi

rca_remote_container_exec "mkdir -p '${REMOTE_VIDEO_DIR}' '${REMOTE_HYDRA_DIR}'"
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
/isaac-sim/kit/python/bin/python3 scripts/evaluate_rsl_rl_checkpoint.py --task ${TASK_NAME} --headless --video --video_backend ${VIDEO_BACKEND} --video_length ${VIDEO_LENGTH} --steps ${VIDEO_LENGTH} --num_envs ${NUM_ENVS} --seed ${SEED} --load_run '${LOAD_RUN}' --checkpoint '${CHECKPOINT}' --summary-json '${REMOTE_SUMMARY_PATH}' hydra.run.dir=${REMOTE_HYDRA_DIR} hydra.output_subdir=null ${EXTRA_PLAY_ARGS} &
child_pid=\$!
wait "\${child_pid}"
EOF
chmod +x '${REMOTE_RUN_PATH}'"

set +e
rca_remote_repo_exec "set -o pipefail && timeout --foreground --signal=TERM --kill-after=${VIDEO_TIMEOUT_KILL_SECONDS}s ${VIDEO_TIMEOUT_SECONDS} bash '${REMOTE_RUN_PATH}' 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
rca_remote_container_exec "pkill -f \"${REMOTE_SUMMARY_PATH}\" || true" >/dev/null 2>&1 || true
set -e

copy_status=0
if rca_remote_container_exec "test -f '${REMOTE_SUMMARY_PATH}'" >/dev/null 2>&1; then
  set +e
  rca_remote_container_exec "
set -euo pipefail
LOG_DIR=\"\$('/isaac-sim/kit/python/bin/python3' -c 'import json,sys; print(json.load(open(sys.argv[1], encoding=\"utf-8\"))[\"log_dir\"])' '${REMOTE_SUMMARY_PATH}')\"
VIDEO_SOURCE_DIR=\"\${LOG_DIR}/videos/eval\"
if [[ ! -d \"\${VIDEO_SOURCE_DIR}\" ]]; then
  echo \"[record-video] summary exists but no video directory at \${VIDEO_SOURCE_DIR}\" >&2
  exit 1
fi
mkdir -p '${REMOTE_VIDEO_DIR}/eval'
cp -R \"\${VIDEO_SOURCE_DIR}/.\" '${REMOTE_VIDEO_DIR}/eval/'
"
  copy_status=$?
  set -e
else
  copy_status=1
fi

if [[ ${status} -ne 0 ]]; then
  if [[ ${status} -eq 124 ]]; then
    echo "[record-video] playback timed out after ${VIDEO_TIMEOUT_SECONDS}s" >&2
  fi
  echo "[record-video] playback failed with status=${status}" >&2
  echo "[record-video] inspect ${REMOTE_LOG_PATH} on the remote container" >&2
  exit "${status}"
fi

if [[ ${copy_status} -ne 0 ]]; then
  echo "[record-video] evaluation completed but no video artifacts were copied" >&2
  echo "[record-video] inspect ${REMOTE_SUMMARY_PATH} and ${REMOTE_LOG_PATH} on the remote container" >&2
  exit 1
fi

echo "[record-video] video dir: ${REMOTE_VIDEO_DIR}"
echo "[record-video] command:   ${REMOTE_COMMAND_PATH}"
