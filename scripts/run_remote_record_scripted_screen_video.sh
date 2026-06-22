#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
VIDEO_LENGTH="${6:-420}"
SEED="${7:-42}"
SCRIPTED_STEPS="${8:-${VIDEO_LENGTH}}"
EXTRA_PLAY_ARGS="${9:-}"
VIDEO_TIMEOUT_SECONDS="${RCA_SCREEN_VIDEO_TIMEOUT_SECONDS:-900}"
VIDEO_TIMEOUT_KILL_SECONDS="${RCA_SCREEN_VIDEO_TIMEOUT_KILL_SECONDS:-45}"
CAPTURE_SIZE="${RCA_SCREEN_CAPTURE_SIZE:-1280x720}"
CAPTURE_FPS="${RCA_SCREEN_CAPTURE_FPS:-20}"
DISPLAY_ID="${RCA_SCREEN_CAPTURE_DISPLAY:-:99}"
SCRIPTED_VIS_ARGS="${RCA_SCREEN_SCRIPTED_VIS_ARGS:---visualizer kit}"
FORCE_APP_LAUNCHER="${RCA_SCREEN_FORCE_APP_LAUNCHER:-1}"
VALIDATE_PEG_VIDEO_CANDIDATE="${RCA_VALIDATE_PEG_VIDEO_CANDIDATE:-1}"
VALIDATE_ACTION_RESPONSE="${RCA_VALIDATE_ACTION_RESPONSE:-0}"
VALIDATE_FINAL_CONTACT_BOUNDARY="${RCA_VALIDATE_FINAL_CONTACT_BOUNDARY:-0}"
VALIDATE_TRACE_FRAME_ALIGNMENT="${RCA_VALIDATE_TRACE_FRAME_ALIGNMENT:-0}"
ACTION_RESPONSE_MIN_COMMAND_NORM="${RCA_ACTION_RESPONSE_MIN_COMMAND_NORM:-1.0e-4}"
ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS="${RCA_ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS:-0}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_VIDEO_DIR="/workspace/artifacts/videos/scripted_screen/${TIMESTAMP_UTC}"
REMOTE_LOG_PATH="${REMOTE_VIDEO_DIR}/record.log"
REMOTE_FFMPEG_LOG_PATH="${REMOTE_VIDEO_DIR}/ffmpeg.log"
REMOTE_COMMAND_PATH="${REMOTE_VIDEO_DIR}/record_command.txt"
REMOTE_RUN_PATH="${REMOTE_VIDEO_DIR}/run_eval_screen.sh"
REMOTE_HYDRA_DIR="/workspace/artifacts/hydra/scripted_screen_video_${TIMESTAMP_UTC}"
REMOTE_SUMMARY_PATH="${REMOTE_VIDEO_DIR}/video_summary.json"
REMOTE_TRACE_PATH="${REMOTE_VIDEO_DIR}/video_trace.json"
REMOTE_MP4_PATH="${REMOTE_VIDEO_DIR}/screen_capture.mp4"
REMOTE_ACTION_RESPONSE_CHECK_PATH="${REMOTE_VIDEO_DIR}/action_response_check.log"
REMOTE_FINAL_CONTACT_BOUNDARY_CHECK_PATH="${REMOTE_VIDEO_DIR}/final_contact_boundary_check.log"
REMOTE_CANDIDATE_CHECK_PATH="${REMOTE_VIDEO_DIR}/peg_video_candidate_check.log"
REMOTE_FRAME_AUDIT_PATH="${REMOTE_VIDEO_DIR}/trace_frame_alignment_check.log"

rca_remote_container_write_file() {
  local remote_path="$1"
  local mode="$2"
  local content="$3"
  local encoded_content

  encoded_content="$(printf '%s' "${content}" | base64 | tr -d '\n')"
  rca_remote_container_exec "printf '%s' '${encoded_content}' | base64 -d > '${remote_path}' && chmod '${mode}' '${remote_path}'"
}

echo "[record-screen] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} steps=${SCRIPTED_STEPS} seed=${SEED}"
echo "[record-screen] timeout_seconds=${VIDEO_TIMEOUT_SECONDS} timeout_kill_seconds=${VIDEO_TIMEOUT_KILL_SECONDS}"
echo "[record-screen] display=${DISPLAY_ID} capture_size=${CAPTURE_SIZE} fps=${CAPTURE_FPS}"
echo "[record-screen] scripted_vis_args=${SCRIPTED_VIS_ARGS}"
echo "[record-screen] force_app_launcher=${FORCE_APP_LAUNCHER}"
echo "[record-screen] validate_peg_video_candidate=${VALIDATE_PEG_VIDEO_CANDIDATE}"
echo "[record-screen] validate_action_response=${VALIDATE_ACTION_RESPONSE}"
echo "[record-screen] action_response_min_command_norm=${ACTION_RESPONSE_MIN_COMMAND_NORM}"
echo "[record-screen] action_response_stop_after_first_success=${ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS}"
echo "[record-screen] validate_final_contact_boundary=${VALIDATE_FINAL_CONTACT_BOUNDARY}"
echo "[record-screen] validate_trace_frame_alignment=${VALIDATE_TRACE_FRAME_ALIGNMENT}"
if [[ -n "${EXTRA_PLAY_ARGS}" ]]; then
  echo "[record-screen] extra_play_args=${EXTRA_PLAY_ARGS}"
fi

rca_remote_container_exec "mkdir -p '${REMOTE_VIDEO_DIR}' '${REMOTE_HYDRA_DIR}'"
COMMAND_SCRIPT="$(cat <<EOF
timeout --foreground --signal=TERM --kill-after=${VIDEO_TIMEOUT_KILL_SECONDS}s ${VIDEO_TIMEOUT_SECONDS} bash '${REMOTE_RUN_PATH}'
EOF
)"
RUN_SCRIPT="$(cat <<EOF
#!/usr/bin/env bash
set -euo pipefail
export CARB_APP_PATH=/isaac-sim/kit
export ISAAC_PATH=/isaac-sim
export EXP_PATH=/isaac-sim/apps
export PYTHONPATH="\${PYTHONPATH:-}"
export LD_LIBRARY_PATH="\${LD_LIBRARY_PATH:-}"
export DISPLAY='${DISPLAY_ID}'
source /isaac-sim/setup_python_env.sh
export RESOURCE_NAME=IsaacSim
export LD_PRELOAD=/isaac-sim/kit/libcarb.so
export RCA_FORCE_APP_LAUNCHER='${FORCE_APP_LAUNCHER}'

/isaac-sim/kit/python/bin/python3 - <<'PY' >/tmp/rca-ffmpeg-path.txt
import imageio_ffmpeg

print(imageio_ffmpeg.get_ffmpeg_exe())
PY
read -r FFMPEG </tmp/rca-ffmpeg-path.txt
if [[ ! -x "\${FFMPEG}" ]]; then
  echo "[record-screen] missing executable ffmpeg from imageio_ffmpeg: \${FFMPEG}" >&2
  exit 2
fi
ffmpeg_pid=""
cleanup() {
  if [[ -n "\${ffmpeg_pid}" ]]; then
    kill "\${ffmpeg_pid}" >/dev/null 2>&1 || true
    wait "\${ffmpeg_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT TERM INT

"\${FFMPEG}" -y -f x11grab -video_size '${CAPTURE_SIZE}' -framerate '${CAPTURE_FPS}' -i '${DISPLAY_ID}' -pix_fmt yuv420p '${REMOTE_MP4_PATH}' >'${REMOTE_FFMPEG_LOG_PATH}' 2>&1 &
ffmpeg_pid="\$!"

/isaac-sim/kit/python/bin/python3 scripts/scripted_agent.py ${SCRIPTED_VIS_ARGS} --task ${TASK_NAME} --steps ${SCRIPTED_STEPS} --num_envs ${NUM_ENVS} --seed ${SEED} --summary-json '${REMOTE_SUMMARY_PATH}' --trace-json '${REMOTE_TRACE_PATH}' hydra.run.dir=${REMOTE_HYDRA_DIR} hydra.output_subdir=null ${EXTRA_PLAY_ARGS}
EOF
)"
rca_remote_container_write_file "${REMOTE_COMMAND_PATH}" 0644 "${COMMAND_SCRIPT}"
rca_remote_container_write_file "${REMOTE_RUN_PATH}" 0755 "${RUN_SCRIPT}"

set +e
rca_remote_repo_exec "set -o pipefail && timeout --foreground --signal=TERM --kill-after=${VIDEO_TIMEOUT_KILL_SECONDS}s ${VIDEO_TIMEOUT_SECONDS} bash '${REMOTE_RUN_PATH}' 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
rca_remote_container_exec "pkill -f '${REMOTE_MP4_PATH}' || true" >/dev/null 2>&1 || true
set -e

if [[ ${status} -ne 0 ]]; then
  if [[ ${status} -eq 124 ]]; then
    echo "[record-screen] playback timed out after ${VIDEO_TIMEOUT_SECONDS}s" >&2
  fi
  echo "[record-screen] playback failed with status=${status}" >&2
  echo "[record-screen] inspect ${REMOTE_LOG_PATH} and ${REMOTE_FFMPEG_LOG_PATH} on the remote container" >&2
  exit "${status}"
fi

for required_path in "${REMOTE_SUMMARY_PATH}" "${REMOTE_TRACE_PATH}" "${REMOTE_MP4_PATH}"; do
  if ! rca_remote_container_exec "test -s '${required_path}'" >/dev/null 2>&1; then
    echo "[record-screen] missing expected artifact: ${required_path}" >&2
    exit 1
  fi
done

validation_status=0
if [[ "${VALIDATE_ACTION_RESPONSE}" == "1" ]]; then
  ACTION_RESPONSE_EXTRA_ARGS=""
  if [[ "${ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS}" == "1" ]]; then
    ACTION_RESPONSE_EXTRA_ARGS="--stop-after-first-success"
  fi
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/check_scripted_action_response_trace.py '${REMOTE_TRACE_PATH}' --min-command-norm '${ACTION_RESPONSE_MIN_COMMAND_NORM}' ${ACTION_RESPONSE_EXTRA_ARGS} 2>&1 | tee '${REMOTE_ACTION_RESPONSE_CHECK_PATH}'"
  action_response_status=$?
  set -e
  if [[ "${action_response_status}" -ne 0 ]]; then
    echo "[record-screen] action-response check failed status=${action_response_status}" >&2
    validation_status="${action_response_status}"
  fi
fi

if [[ "${VALIDATE_PEG_VIDEO_CANDIDATE}" == "1" ]]; then
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/check_peg_in_hole_video_candidate.py '${REMOTE_TRACE_PATH}' 2>&1 | tee '${REMOTE_CANDIDATE_CHECK_PATH}'"
  candidate_status=$?
  set -e
  if [[ "${candidate_status}" -ne 0 ]]; then
    echo "[record-screen] peg video candidate check failed status=${candidate_status}" >&2
    validation_status="${candidate_status}"
  fi
fi

if [[ "${VALIDATE_FINAL_CONTACT_BOUNDARY}" == "1" ]]; then
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/check_final_contact_boundary_diagnostic.py '${REMOTE_TRACE_PATH}' 2>&1 | tee '${REMOTE_FINAL_CONTACT_BOUNDARY_CHECK_PATH}'"
  boundary_status=$?
  set -e
  if [[ "${boundary_status}" -ne 0 ]]; then
    echo "[record-screen] final-contact boundary check failed status=${boundary_status}" >&2
    validation_status="${boundary_status}"
  fi
fi

if [[ "${VALIDATE_TRACE_FRAME_ALIGNMENT}" == "1" ]]; then
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/audit_trace_frame_alignment.py '${REMOTE_TRACE_PATH}' 2>&1 | tee '${REMOTE_FRAME_AUDIT_PATH}'"
  frame_status=$?
  set -e
  if [[ "${frame_status}" -ne 0 ]]; then
    echo "[record-screen] trace frame alignment check failed status=${frame_status}" >&2
    if [[ "${validation_status}" -eq 0 ]]; then
      validation_status="${frame_status}"
    fi
  fi
fi

echo "[record-screen] video dir: ${REMOTE_VIDEO_DIR}"
echo "[record-screen] mp4:       ${REMOTE_MP4_PATH}"
echo "[record-screen] trace:     ${REMOTE_TRACE_PATH}"
if [[ "${VALIDATE_ACTION_RESPONSE}" == "1" ]]; then
  echo "[record-screen] action_response_check: ${REMOTE_ACTION_RESPONSE_CHECK_PATH}"
fi
if [[ "${VALIDATE_FINAL_CONTACT_BOUNDARY}" == "1" ]]; then
  echo "[record-screen] final_contact_boundary_check: ${REMOTE_FINAL_CONTACT_BOUNDARY_CHECK_PATH}"
fi
if [[ "${VALIDATE_PEG_VIDEO_CANDIDATE}" == "1" ]]; then
  echo "[record-screen] candidate_check: ${REMOTE_CANDIDATE_CHECK_PATH}"
fi
if [[ "${VALIDATE_TRACE_FRAME_ALIGNMENT}" == "1" ]]; then
  echo "[record-screen] frame_audit:      ${REMOTE_FRAME_AUDIT_PATH}"
fi

if [[ "${validation_status}" -ne 0 ]]; then
  exit "${validation_status}"
fi
