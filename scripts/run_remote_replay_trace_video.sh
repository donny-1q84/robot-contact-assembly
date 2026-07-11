#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
TRACE_JSON="${RCA_REPLAY_TRACE_JSON:-${SCRIPT_DIR}/../artifacts/videos/trace_only/2026-06-21T20-05-25Z/video_trace.json}"
START_STEP="${RCA_REPLAY_TRACE_START_STEP:-0}"
END_STEP="${RCA_REPLAY_TRACE_END_STEP:-220}"
STRIDE="${RCA_REPLAY_TRACE_STRIDE:-1}"
FPS="${RCA_REPLAY_TRACE_FPS:-30}"
SEED="${RCA_REPLAY_TRACE_SEED:-42}"
VIDEO_TIMEOUT_SECONDS="${RCA_REPLAY_VIDEO_TIMEOUT_SECONDS:-900}"
VIDEO_TIMEOUT_KILL_SECONDS="${RCA_REPLAY_VIDEO_TIMEOUT_KILL_SECONDS:-45}"
FORCE_APP_LAUNCHER="${RCA_REPLAY_TRACE_FORCE_APP_LAUNCHER:-1}"
WRITE_PEG_FROM_TRACE="${RCA_REPLAY_TRACE_WRITE_PEG_FROM_TRACE:-1}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_INPUT_HOST_DIR="${RCA_REMOTE_ROOT}/repo/robot-contact-assembly/.tmp/trace_replay_inputs/${TIMESTAMP_UTC}"
REMOTE_INPUT_TRACE_HOST_PATH="${REMOTE_INPUT_HOST_DIR}/source_trace.json"
REMOTE_INPUT_TRACE_CONTAINER_PATH="/workspace/robot-contact-assembly/.tmp/trace_replay_inputs/${TIMESTAMP_UTC}/source_trace.json"
REMOTE_VIDEO_DIR="/workspace/artifacts/videos/isaac_trace_replay/${TIMESTAMP_UTC}"
REMOTE_EVAL_VIDEO_DIR="${REMOTE_VIDEO_DIR}/eval"
REMOTE_LOG_PATH="${REMOTE_VIDEO_DIR}/replay.log"
REMOTE_COMMAND_PATH="${REMOTE_VIDEO_DIR}/replay_command.txt"
REMOTE_RUN_PATH="${REMOTE_VIDEO_DIR}/run_replay.sh"
REMOTE_SUMMARY_PATH="${REMOTE_VIDEO_DIR}/replay_summary.json"

if [[ ! -f "${TRACE_JSON}" ]]; then
  echo "[trace-replay-remote] missing source trace JSON: ${TRACE_JSON}" >&2
  exit 2
fi

echo "[trace-replay-remote] env=${RCA_ENV_NAME} task=${TASK_NAME}"
echo "[trace-replay-remote] source_trace=${TRACE_JSON}"
echo "[trace-replay-remote] steps=${START_STEP}:${END_STEP}:${STRIDE} fps=${FPS} seed=${SEED}"
echo "[trace-replay-remote] timeout_seconds=${VIDEO_TIMEOUT_SECONDS} timeout_kill_seconds=${VIDEO_TIMEOUT_KILL_SECONDS}"

rca_remote_host_exec "mkdir -p '${REMOTE_INPUT_HOST_DIR}'"
rsync -az "${TRACE_JSON}" "${RCA_ENV_NAME}:${REMOTE_INPUT_TRACE_HOST_PATH}"

rca_remote_container_exec "mkdir -p '${REMOTE_VIDEO_DIR}' '${REMOTE_EVAL_VIDEO_DIR}'"
rca_remote_container_exec "cat > '${REMOTE_COMMAND_PATH}' <<'EOF'
timeout --foreground --signal=TERM --kill-after=${VIDEO_TIMEOUT_KILL_SECONDS}s ${VIDEO_TIMEOUT_SECONDS} bash '${REMOTE_RUN_PATH}'
EOF"

PEG_FROM_TRACE_ARG=""
if [[ "${WRITE_PEG_FROM_TRACE}" == "1" ]]; then
  PEG_FROM_TRACE_ARG="--write-peg-root-from-trace"
fi

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
export PYTHONPATH=\"\${PYTHONPATH:-}\"
export LD_LIBRARY_PATH=\"\${LD_LIBRARY_PATH:-}\"
source /isaac-sim/setup_python_env.sh
export RESOURCE_NAME=IsaacSim
export LD_PRELOAD=/isaac-sim/kit/libcarb.so
export RCA_FORCE_APP_LAUNCHER='${FORCE_APP_LAUNCHER}'
/isaac-sim/kit/python/bin/python3 scripts/replay_trace_in_isaac_video.py \
  --headless \
  --trace-json '${REMOTE_INPUT_TRACE_CONTAINER_PATH}' \
  --task '${TASK_NAME}' \
  --video-folder '${REMOTE_EVAL_VIDEO_DIR}' \
  --summary-json '${REMOTE_SUMMARY_PATH}' \
  --start-step '${START_STEP}' \
  --end-step '${END_STEP}' \
  --stride '${STRIDE}' \
  --fps '${FPS}' \
  --seed '${SEED}' \
  --num-envs 1 \
  --require-source-success \
  ${PEG_FROM_TRACE_ARG} &
child_pid=\$!
wait "\${child_pid}"
EOF
chmod +x '${REMOTE_RUN_PATH}'"

set +e
rca_remote_repo_exec "set -o pipefail && timeout --foreground --signal=TERM --kill-after=${VIDEO_TIMEOUT_KILL_SECONDS}s ${VIDEO_TIMEOUT_SECONDS} bash '${REMOTE_RUN_PATH}' 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
rca_remote_container_exec "pkill -f \"${REMOTE_SUMMARY_PATH}\" || true" >/dev/null 2>&1 || true
set -e

if [[ "${status}" -ne 0 ]]; then
  if [[ "${status}" -eq 124 ]]; then
    echo "[trace-replay-remote] replay timed out after ${VIDEO_TIMEOUT_SECONDS}s" >&2
  fi
  echo "[trace-replay-remote] replay failed status=${status}; inspect ${REMOTE_LOG_PATH}" >&2
  exit "${status}"
fi

if ! rca_remote_container_exec "test -f '${REMOTE_SUMMARY_PATH}'" >/dev/null 2>&1; then
  echo "[trace-replay-remote] replay completed but no summary was written" >&2
  exit 1
fi

if ! rca_remote_container_exec "test -s '${REMOTE_EVAL_VIDEO_DIR}/isaac_trace_replay.mp4'" >/dev/null 2>&1; then
  echo "[trace-replay-remote] replay completed but isaac_trace_replay.mp4 is missing or empty" >&2
  exit 1
fi

set +e
rca_remote_repo_exec "/isaac-sim/kit/python/bin/python3 - <<'PY'
import json
from pathlib import Path

summary_path = Path('${REMOTE_SUMMARY_PATH}')
summary = json.loads(summary_path.read_text(encoding='utf-8'))
frames = int(summary.get('frames_written') or 0)
source_success_step = summary.get('source_success_step')
if frames <= 0:
    raise SystemExit('frames_written must be positive')
if source_success_step is None:
    raise SystemExit('source_success_step must be present')
print('[trace-replay-remote] validated replay summary:', json.dumps({
    'frames_written': frames,
    'source_success_step': source_success_step,
    'video_path': summary.get('video_path'),
}, sort_keys=True))
PY"
summary_status=$?
set -e
if [[ "${summary_status}" -ne 0 ]]; then
  echo "[trace-replay-remote] replay summary validation failed status=${summary_status}" >&2
  exit "${summary_status}"
fi

echo "[trace-replay-remote] video dir: ${REMOTE_VIDEO_DIR}"
echo "[trace-replay-remote] video:     ${REMOTE_EVAL_VIDEO_DIR}/isaac_trace_replay.mp4"
echo "[trace-replay-remote] summary:   ${REMOTE_SUMMARY_PATH}"
