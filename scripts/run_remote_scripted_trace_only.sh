#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/remote_common.sh"

rca_init_remote_vars "${1:-}" "${2:-}" "${3:-}"

TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
NUM_ENVS="${5:-1}"
STEPS="${6:-420}"
SEED="${7:-42}"
EXTRA_PLAY_ARGS="${8:-}"
TRACE_TIMEOUT_SECONDS="${RCA_TRACE_ONLY_TIMEOUT_SECONDS:-600}"
TRACE_TIMEOUT_KILL_SECONDS="${RCA_TRACE_ONLY_TIMEOUT_KILL_SECONDS:-45}"
VALIDATE_PEG_VIDEO_CANDIDATE="${RCA_VALIDATE_PEG_VIDEO_CANDIDATE:-1}"
VALIDATE_TRACE_FRAME_ALIGNMENT="${RCA_VALIDATE_TRACE_FRAME_ALIGNMENT:-1}"
VALIDATE_ACTION_RESPONSE="${RCA_VALIDATE_ACTION_RESPONSE:-1}"
VALIDATE_FINAL_CONTACT_BOUNDARY="${RCA_VALIDATE_FINAL_CONTACT_BOUNDARY:-0}"
ACTION_RESPONSE_MIN_COMMAND_NORM="${RCA_ACTION_RESPONSE_MIN_COMMAND_NORM:-1.0e-4}"
ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS="${RCA_ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS:-0}"
FORCE_APP_LAUNCHER="${RCA_FORCE_APP_LAUNCHER:-1}"
SCRIPTED_WATCHDOG_SECONDS="${RCA_SCRIPTED_WATCHDOG_SECONDS:-120}"
TRACE_PHASE_STEPS="${RCA_TRACE_PHASE_STEPS:-5}"
TRACE_DIR_NAME="${RCA_TRACE_ONLY_DIR_NAME:-}"
TRACE_REMOTE_DIR_OVERRIDE="${RCA_TRACE_ONLY_REMOTE_DIR:-}"
TRACE_VARIATION_CASE_ID="${RCA_TRACE_VARIATION_CASE_ID:-}"
TRACE_VARIATION_SOCKET_DELTA_M="${RCA_TRACE_VARIATION_SOCKET_DELTA_M:-}"
TRACE_VARIATION_RESET_JOINT_NOISE_RAD="${RCA_TRACE_VARIATION_RESET_JOINT_NOISE_RAD:-}"

TIMESTAMP_UTC="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
if [[ -z "${TRACE_DIR_NAME}" ]]; then
  TRACE_DIR_NAME="${TIMESTAMP_UTC}"
fi
REMOTE_TRACE_DIR="${TRACE_REMOTE_DIR_OVERRIDE:-/workspace/artifacts/videos/trace_only/${TRACE_DIR_NAME}}"
REMOTE_LOG_PATH="${REMOTE_TRACE_DIR}/trace_only.log"
REMOTE_COMMAND_PATH="${REMOTE_TRACE_DIR}/trace_command.txt"
REMOTE_RUN_PATH="${REMOTE_TRACE_DIR}/run_trace_only.sh"
REMOTE_HYDRA_DIR="/workspace/artifacts/hydra/trace_only_${TRACE_DIR_NAME//\//_}"
REMOTE_SUMMARY_PATH="${REMOTE_TRACE_DIR}/video_summary.json"
REMOTE_TRACE_PATH="${REMOTE_TRACE_DIR}/video_trace.json"
REMOTE_ACTION_RESPONSE_CHECK_PATH="${REMOTE_TRACE_DIR}/action_response_check.log"
REMOTE_FINAL_CONTACT_BOUNDARY_CHECK_PATH="${REMOTE_TRACE_DIR}/final_contact_boundary_check.log"
REMOTE_CANDIDATE_CHECK_PATH="${REMOTE_TRACE_DIR}/peg_video_candidate_check.log"
REMOTE_FRAME_AUDIT_PATH="${REMOTE_TRACE_DIR}/trace_frame_alignment_check.log"

echo "[trace-only] env=${RCA_ENV_NAME} task=${TASK_NAME} num_envs=${NUM_ENVS} steps=${STEPS} seed=${SEED}"
echo "[trace-only] timeout_seconds=${TRACE_TIMEOUT_SECONDS} timeout_kill_seconds=${TRACE_TIMEOUT_KILL_SECONDS}"
echo "[trace-only] force_app_launcher=${FORCE_APP_LAUNCHER}"
echo "[trace-only] scripted_watchdog_seconds=${SCRIPTED_WATCHDOG_SECONDS}"
echo "[trace-only] trace_phase_steps=${TRACE_PHASE_STEPS}"
echo "[trace-only] trace_dir_name=${TRACE_DIR_NAME}"
echo "[trace-only] remote_trace_dir=${REMOTE_TRACE_DIR}"
echo "[trace-only] validate_action_response=${VALIDATE_ACTION_RESPONSE}"
echo "[trace-only] action_response_min_command_norm=${ACTION_RESPONSE_MIN_COMMAND_NORM}"
echo "[trace-only] action_response_stop_after_first_success=${ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS}"
echo "[trace-only] validate_final_contact_boundary=${VALIDATE_FINAL_CONTACT_BOUNDARY}"
echo "[trace-only] validate_peg_video_candidate=${VALIDATE_PEG_VIDEO_CANDIDATE}"
echo "[trace-only] validate_trace_frame_alignment=${VALIDATE_TRACE_FRAME_ALIGNMENT}"
if [[ -n "${EXTRA_PLAY_ARGS}" ]]; then
  echo "[trace-only] extra_play_args=${EXTRA_PLAY_ARGS}"
fi
if [[ -n "${TRACE_VARIATION_CASE_ID}" ]]; then
  echo "[trace-only] variation_case_id=${TRACE_VARIATION_CASE_ID}"
  echo "[trace-only] variation_socket_delta_m=${TRACE_VARIATION_SOCKET_DELTA_M}"
  echo "[trace-only] variation_reset_joint_noise_rad=${TRACE_VARIATION_RESET_JOINT_NOISE_RAD}"
fi

rca_remote_container_exec "mkdir -p '${REMOTE_TRACE_DIR}' '${REMOTE_HYDRA_DIR}'"
rca_remote_container_exec "cat > '${REMOTE_COMMAND_PATH}' <<'EOF'
timeout --foreground --signal=TERM --kill-after=${TRACE_TIMEOUT_KILL_SECONDS}s ${TRACE_TIMEOUT_SECONDS} bash '${REMOTE_RUN_PATH}'
EOF"
rca_remote_container_exec "cat > '${REMOTE_RUN_PATH}' <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
export CARB_APP_PATH=/isaac-sim/kit
export ISAAC_PATH=/isaac-sim
export EXP_PATH=/isaac-sim/apps
export PYTHONPATH="${PYTHONPATH:-}"
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"
source /isaac-sim/setup_python_env.sh
export RESOURCE_NAME=IsaacSim
export LD_PRELOAD=/isaac-sim/kit/libcarb.so
export RCA_FORCE_APP_LAUNCHER='${FORCE_APP_LAUNCHER}'
export RCA_SCRIPTED_WATCHDOG_SECONDS='${SCRIPTED_WATCHDOG_SECONDS}'
export RCA_TRACE_PHASE_STEPS='${TRACE_PHASE_STEPS}'
export RCA_TRACE_VARIATION_CASE_ID='${TRACE_VARIATION_CASE_ID}'
export RCA_TRACE_VARIATION_SOCKET_DELTA_M='${TRACE_VARIATION_SOCKET_DELTA_M}'
export RCA_TRACE_VARIATION_RESET_JOINT_NOISE_RAD='${TRACE_VARIATION_RESET_JOINT_NOISE_RAD}'

/isaac-sim/kit/python/bin/python3 scripts/scripted_agent.py --task ${TASK_NAME} --headless --viz none --steps ${STEPS} --num_envs ${NUM_ENVS} --seed ${SEED} --summary-json '${REMOTE_SUMMARY_PATH}' --trace-json '${REMOTE_TRACE_PATH}' hydra.run.dir=${REMOTE_HYDRA_DIR} hydra.output_subdir=null ${EXTRA_PLAY_ARGS}
EOF
chmod +x '${REMOTE_RUN_PATH}'"

set +e
rca_remote_repo_exec "set -o pipefail && timeout --foreground --signal=TERM --kill-after=${TRACE_TIMEOUT_KILL_SECONDS}s ${TRACE_TIMEOUT_SECONDS} bash '${REMOTE_RUN_PATH}' 2>&1 | tee '${REMOTE_LOG_PATH}'"
status=$?
set -e

if [[ ${status} -ne 0 ]]; then
  if [[ ${status} -eq 124 ]]; then
    echo "[trace-only] playback timed out after ${TRACE_TIMEOUT_SECONDS}s" >&2
  fi
  echo "[trace-only] playback failed with status=${status}" >&2
  echo "[trace-only] inspect ${REMOTE_LOG_PATH} on the remote container" >&2
  exit "${status}"
fi

for required_path in "${REMOTE_SUMMARY_PATH}" "${REMOTE_TRACE_PATH}"; do
  if ! rca_remote_container_exec "test -s '${required_path}'" >/dev/null 2>&1; then
    echo "[trace-only] missing expected artifact: ${required_path}" >&2
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
    echo "[trace-only] action response check failed status=${action_response_status}" >&2
    validation_status="${action_response_status}"
  fi
fi

if [[ "${VALIDATE_PEG_VIDEO_CANDIDATE}" == "1" ]]; then
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/check_peg_in_hole_video_candidate.py '${REMOTE_TRACE_PATH}' 2>&1 | tee '${REMOTE_CANDIDATE_CHECK_PATH}'"
  candidate_status=$?
  set -e
  if [[ "${candidate_status}" -ne 0 ]]; then
    echo "[trace-only] peg video candidate check failed status=${candidate_status}" >&2
    validation_status="${candidate_status}"
  fi
fi

if [[ "${VALIDATE_FINAL_CONTACT_BOUNDARY}" == "1" ]]; then
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/check_final_contact_boundary_diagnostic.py '${REMOTE_TRACE_PATH}' 2>&1 | tee '${REMOTE_FINAL_CONTACT_BOUNDARY_CHECK_PATH}'"
  boundary_status=$?
  set -e
  if [[ "${boundary_status}" -ne 0 ]]; then
    echo "[trace-only] final-contact boundary check failed status=${boundary_status}" >&2
    validation_status="${boundary_status}"
  fi
fi

if [[ "${VALIDATE_TRACE_FRAME_ALIGNMENT}" == "1" ]]; then
  set +e
  rca_remote_repo_exec "set -o pipefail && /isaac-sim/kit/python/bin/python3 scripts/audit_trace_frame_alignment.py '${REMOTE_TRACE_PATH}' 2>&1 | tee '${REMOTE_FRAME_AUDIT_PATH}'"
  frame_status=$?
  set -e
  if [[ "${frame_status}" -ne 0 ]]; then
    echo "[trace-only] trace frame alignment check failed status=${frame_status}" >&2
    if [[ "${validation_status}" -eq 0 ]]; then
      validation_status="${frame_status}"
    fi
  fi
fi

echo "[trace-only] trace dir: ${REMOTE_TRACE_DIR}"
echo "[trace-only] summary:   ${REMOTE_SUMMARY_PATH}"
echo "[trace-only] trace:     ${REMOTE_TRACE_PATH}"
if [[ "${VALIDATE_ACTION_RESPONSE}" == "1" ]]; then
  echo "[trace-only] action_response_check: ${REMOTE_ACTION_RESPONSE_CHECK_PATH}"
fi
if [[ "${VALIDATE_FINAL_CONTACT_BOUNDARY}" == "1" ]]; then
  echo "[trace-only] final_contact_boundary_check: ${REMOTE_FINAL_CONTACT_BOUNDARY_CHECK_PATH}"
fi
if [[ "${VALIDATE_PEG_VIDEO_CANDIDATE}" == "1" ]]; then
  echo "[trace-only] candidate_check: ${REMOTE_CANDIDATE_CHECK_PATH}"
fi
if [[ "${VALIDATE_TRACE_FRAME_ALIGNMENT}" == "1" ]]; then
  echo "[trace-only] frame_audit:      ${REMOTE_FRAME_AUDIT_PATH}"
fi

if [[ "${validation_status}" -ne 0 ]]; then
  exit "${validation_status}"
fi
