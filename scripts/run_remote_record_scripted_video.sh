#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

SYNC_BEFORE_RUN="${RCA_RECORD_SCRIPTED_SYNC_BEFORE_RUN:-1}"
if [[ "${SYNC_BEFORE_RUN}" == "1" ]]; then
  "${SCRIPT_DIR}/sync_to_brev.sh" "${RCA_ENV_NAME}" "${RCA_REMOTE_ROOT}"
else
  echo "[record-scripted] skipping pre-record sync because RCA_RECORD_SCRIPTED_SYNC_BEFORE_RUN=${SYNC_BEFORE_RUN}"
fi

TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-Play-v0}"
NUM_ENVS="${5:-1}"
VIDEO_LENGTH="${6:-400}"
SEED="${7:-42}"
SCRIPTED_STEPS="${8:-${VIDEO_LENGTH}}"
EXTRA_PLAY_ARGS="${9:-}"
VIDEO_TIMEOUT_SECONDS="${RCA_VIDEO_TIMEOUT_SECONDS:-240}"
VIDEO_TIMEOUT_KILL_SECONDS="${RCA_VIDEO_TIMEOUT_KILL_SECONDS:-30}"
VIDEO_BACKEND="${RCA_VIDEO_BACKEND:-viewport}"
FORCE_APP_LAUNCHER="${RCA_RECORD_SCRIPTED_FORCE_APP_LAUNCHER:-${RCA_FORCE_APP_LAUNCHER:-0}}"
SCRIPTED_VIS_ARGS="${RCA_RECORD_SCRIPTED_VIS_ARGS:-}"
VALIDATE_PEG_VIDEO_CANDIDATE="${RCA_VALIDATE_PEG_VIDEO_CANDIDATE:-0}"
VALIDATE_ACTION_RESPONSE="${RCA_VALIDATE_ACTION_RESPONSE:-0}"
VALIDATE_FINAL_CONTACT_BOUNDARY="${RCA_VALIDATE_FINAL_CONTACT_BOUNDARY:-0}"
VALIDATE_TRACE_FRAME_ALIGNMENT="${RCA_VALIDATE_TRACE_FRAME_ALIGNMENT:-0}"
ACTION_RESPONSE_MIN_COMMAND_NORM="${RCA_ACTION_RESPONSE_MIN_COMMAND_NORM:-1.0e-4}"
ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS="${RCA_ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS:-0}"
AUTO_VIEWPORT_KIT_ARGS="${RCA_AUTO_VIEWPORT_KIT_ARGS:-0}"
VIEWPORT_KIT_ARGS='--kit_args "--enable omni.replicator.core --enable omni.kit.material.library --enable omni.kit.viewport.rtx"'

if [[ "${AUTO_VIEWPORT_KIT_ARGS}" == "1" && "${VIDEO_BACKEND}" == "viewport" && "${EXTRA_PLAY_ARGS}" != *"--kit_args"* ]]; then
  if [[ -n "${EXTRA_PLAY_ARGS}" ]]; then
    EXTRA_PLAY_ARGS="${EXTRA_PLAY_ARGS} ${VIEWPORT_KIT_ARGS}"
  else
    EXTRA_PLAY_ARGS="${VIEWPORT_KIT_ARGS}"
  fi
fi

if [[ "${VIDEO_BACKEND}" == "camera" ]]; then
  FORCE_APP_LAUNCHER="${RCA_RECORD_SCRIPTED_FORCE_APP_LAUNCHER:-${RCA_FORCE_APP_LAUNCHER:-1}}"
  SCRIPTED_VIS_ARGS="${RCA_RECORD_SCRIPTED_VIS_ARGS:---viz none}"
fi

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REMOTE_VIDEO_DIR="/workspace/artifacts/videos/scripted/${TIMESTAMP_UTC}"
REMOTE_LOG_PATH="${REMOTE_VIDEO_DIR}/record.log"
REMOTE_COMMAND_PATH="${REMOTE_VIDEO_DIR}/record_command.txt"
REMOTE_RUN_PATH="${REMOTE_VIDEO_DIR}/run_eval.sh"
REMOTE_HYDRA_DIR="/workspace/artifacts/hydra/scripted_video_${TIMESTAMP_UTC}"
REMOTE_SUMMARY_PATH="${REMOTE_VIDEO_DIR}/video_summary.json"
REMOTE_TRACE_PATH="${REMOTE_VIDEO_DIR}/video_trace.json"
REMOTE_ACTION_RESPONSE_CHECK_PATH="${REMOTE_VIDEO_DIR}/action_response_check.log"
REMOTE_FINAL_CONTACT_BOUNDARY_CHECK_PATH="${REMOTE_VIDEO_DIR}/final_contact_boundary_check.log"
REMOTE_CANDIDATE_CHECK_PATH="${REMOTE_VIDEO_DIR}/peg_video_candidate_check.log"
REMOTE_FRAME_AUDIT_PATH="${REMOTE_VIDEO_DIR}/trace_frame_alignment_check.log"
REMOTE_EVAL_VIDEO_DIR="${REMOTE_VIDEO_DIR}/eval"

echo "[record-scripted] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} video_length=${VIDEO_LENGTH} seed=${SEED}"
echo "[record-scripted] steps=${SCRIPTED_STEPS} timeout_seconds=${VIDEO_TIMEOUT_SECONDS} timeout_kill_seconds=${VIDEO_TIMEOUT_KILL_SECONDS}"
echo "[record-scripted] video_backend=${VIDEO_BACKEND}"
echo "[record-scripted] force_app_launcher=${FORCE_APP_LAUNCHER}"
echo "[record-scripted] scripted_vis_args=${SCRIPTED_VIS_ARGS:-<none>}"
echo "[record-scripted] validate_peg_video_candidate=${VALIDATE_PEG_VIDEO_CANDIDATE}"
echo "[record-scripted] validate_action_response=${VALIDATE_ACTION_RESPONSE}"
echo "[record-scripted] action_response_min_command_norm=${ACTION_RESPONSE_MIN_COMMAND_NORM}"
echo "[record-scripted] action_response_stop_after_first_success=${ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS}"
echo "[record-scripted] validate_final_contact_boundary=${VALIDATE_FINAL_CONTACT_BOUNDARY}"
echo "[record-scripted] validate_trace_frame_alignment=${VALIDATE_TRACE_FRAME_ALIGNMENT}"
echo "[record-scripted] auto_viewport_kit_args=${AUTO_VIEWPORT_KIT_ARGS}"
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
export RCA_FORCE_APP_LAUNCHER='${FORCE_APP_LAUNCHER}'
/isaac-sim/kit/python/bin/python3 scripts/scripted_agent.py ${SCRIPTED_VIS_ARGS} --task ${TASK_NAME} --headless --video --video_backend ${VIDEO_BACKEND} --video_folder '${REMOTE_EVAL_VIDEO_DIR}' --video_length ${VIDEO_LENGTH} --steps ${SCRIPTED_STEPS} --num_envs ${NUM_ENVS} --seed ${SEED} --summary-json '${REMOTE_SUMMARY_PATH}' --trace-json '${REMOTE_TRACE_PATH}' hydra.run.dir=${REMOTE_HYDRA_DIR} hydra.output_subdir=null ${EXTRA_PLAY_ARGS} &
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

validation_status=0
if [[ "${VALIDATE_ACTION_RESPONSE}" == "1" ]]; then
  if ! rca_remote_container_exec "test -f '${REMOTE_TRACE_PATH}'" >/dev/null 2>&1; then
    echo "[record-scripted] action-response validation requested but no trace JSON was written" >&2
    exit 1
  fi
  ACTION_RESPONSE_EXTRA_ARGS=""
  if [[ "${ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS}" == "1" ]]; then
    ACTION_RESPONSE_EXTRA_ARGS="--stop-after-first-success"
  fi
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/check_scripted_action_response_trace.py '${REMOTE_TRACE_PATH}' --min-command-norm '${ACTION_RESPONSE_MIN_COMMAND_NORM}' ${ACTION_RESPONSE_EXTRA_ARGS} 2>&1 | tee '${REMOTE_ACTION_RESPONSE_CHECK_PATH}'"
  action_response_status=$?
  set -e
  if [[ "${action_response_status}" -ne 0 ]]; then
    echo "[record-scripted] action-response check failed status=${action_response_status}" >&2
    validation_status="${action_response_status}"
  fi
fi

if [[ "${VALIDATE_PEG_VIDEO_CANDIDATE}" == "1" ]]; then
  if ! rca_remote_container_exec "test -f '${REMOTE_TRACE_PATH}'" >/dev/null 2>&1; then
    echo "[record-scripted] validation requested but no trace JSON was written" >&2
    exit 1
  fi
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/check_peg_in_hole_video_candidate.py '${REMOTE_TRACE_PATH}' 2>&1 | tee '${REMOTE_CANDIDATE_CHECK_PATH}'"
  candidate_status=$?
  set -e
  if [[ "${candidate_status}" -ne 0 ]]; then
    echo "[record-scripted] peg video candidate check failed status=${candidate_status}" >&2
    validation_status="${candidate_status}"
  fi
fi

if [[ "${VALIDATE_FINAL_CONTACT_BOUNDARY}" == "1" ]]; then
  if ! rca_remote_container_exec "test -f '${REMOTE_TRACE_PATH}'" >/dev/null 2>&1; then
    echo "[record-scripted] final-contact validation requested but no trace JSON was written" >&2
    exit 1
  fi
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/check_final_contact_boundary_diagnostic.py '${REMOTE_TRACE_PATH}' 2>&1 | tee '${REMOTE_FINAL_CONTACT_BOUNDARY_CHECK_PATH}'"
  boundary_status=$?
  set -e
  if [[ "${boundary_status}" -ne 0 ]]; then
    echo "[record-scripted] final-contact boundary check failed status=${boundary_status}" >&2
    validation_status="${boundary_status}"
  fi
fi

if [[ "${VALIDATE_TRACE_FRAME_ALIGNMENT}" == "1" ]]; then
  if ! rca_remote_container_exec "test -f '${REMOTE_TRACE_PATH}'" >/dev/null 2>&1; then
    echo "[record-scripted] trace-frame validation requested but no trace JSON was written" >&2
    exit 1
  fi
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/audit_trace_frame_alignment.py '${REMOTE_TRACE_PATH}' 2>&1 | tee '${REMOTE_FRAME_AUDIT_PATH}'"
  frame_status=$?
  set -e
  if [[ "${frame_status}" -ne 0 ]]; then
    echo "[record-scripted] trace frame alignment check failed status=${frame_status}" >&2
    if [[ "${validation_status}" -eq 0 ]]; then
      validation_status="${frame_status}"
    fi
  fi
fi

echo "[record-scripted] video dir: ${REMOTE_VIDEO_DIR}"
echo "[record-scripted] command:   ${REMOTE_COMMAND_PATH}"
echo "[record-scripted] trace:     ${REMOTE_TRACE_PATH}"
if [[ "${VALIDATE_ACTION_RESPONSE}" == "1" ]]; then
  echo "[record-scripted] action_response_check: ${REMOTE_ACTION_RESPONSE_CHECK_PATH}"
fi
if [[ "${VALIDATE_FINAL_CONTACT_BOUNDARY}" == "1" ]]; then
  echo "[record-scripted] final_contact_boundary_check: ${REMOTE_FINAL_CONTACT_BOUNDARY_CHECK_PATH}"
fi
if [[ "${VALIDATE_PEG_VIDEO_CANDIDATE}" == "1" ]]; then
  echo "[record-scripted] candidate_check: ${REMOTE_CANDIDATE_CHECK_PATH}"
fi
if [[ "${VALIDATE_TRACE_FRAME_ALIGNMENT}" == "1" ]]; then
  echo "[record-scripted] frame_audit:      ${REMOTE_FRAME_AUDIT_PATH}"
fi

if [[ "${validation_status}" -ne 0 ]]; then
  exit "${validation_status}"
fi
