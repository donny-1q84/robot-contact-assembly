#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_NAME="${1:-rca-peg-video-candidate-vm}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
VIDEO_LENGTH="${5:-420}"
SEED="${6:-42}"
SCRIPTED_STEPS="${7:-${VIDEO_LENGTH}}"
AGENT_MODE="${RCA_VIDEO_CANDIDATE_AGENT_MODE:-joint-response-socket}"
RECORDING_MODE="${RCA_VIDEO_CANDIDATE_RECORDING_MODE:-screen}"

BREV_BIN="${BREV_BIN:-/Users/Shenghan/bin/brev}"
INSTANCE_TYPE="${RCA_VIDEO_CANDIDATE_INSTANCE_TYPE:-g6e.xlarge}"
MIN_DISK="${RCA_VIDEO_CANDIDATE_MIN_DISK:-500}"
CREATE_TIMEOUT="${RCA_VIDEO_CANDIDATE_CREATE_TIMEOUT:-900}"
WATCHDOG_MAX_MINUTES="${RCA_VIDEO_CANDIDATE_WATCHDOG_MAX_MINUTES:-45}"
WATCHDOG_POLL_SECONDS="${RCA_VIDEO_CANDIDATE_WATCHDOG_POLL_SECONDS:-60}"
WATCHDOG_WAIT_MAX_MINUTES="${RCA_VIDEO_CANDIDATE_WATCHDOG_WAIT_MAX_MINUTES:-$(( (CREATE_TIMEOUT + 599) / 60 + 10 ))}"
WATCHDOG_START_GRACE_SECONDS="${RCA_VIDEO_CANDIDATE_WATCHDOG_START_GRACE_SECONDS:-2}"
WATCHDOG_DASHBOARD_URL="${RCA_VIDEO_CANDIDATE_DASHBOARD_URL:-https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments}"
DELETE_ATTEMPTS="${RCA_VIDEO_CANDIDATE_DELETE_ATTEMPTS:-45}"
DELETE_RETRY_INTERVAL_SECONDS="${RCA_VIDEO_CANDIDATE_DELETE_RETRY_INTERVAL_SECONDS:-10}"
VIDEO_TIMEOUT_SECONDS="${RCA_VIDEO_CANDIDATE_TIMEOUT_SECONDS:-900}"
VIDEO_TIMEOUT_KILL_SECONDS="${RCA_VIDEO_CANDIDATE_TIMEOUT_KILL_SECONDS:-45}"
CALIBRATION_STEPS_PER_PROBE="${RCA_VIDEO_CANDIDATE_CALIBRATION_STEPS_PER_PROBE:-8}"
CALIBRATION_TIMEOUT_SECONDS="${RCA_VIDEO_CANDIDATE_CALIBRATION_TIMEOUT_SECONDS:-900}"
CALIBRATION_DOWN_DELTA="${RCA_VIDEO_CANDIDATE_CALIBRATION_DOWN_DELTA:-0,0,-0.0002}"
CALIBRATION_UP_DELTA="${RCA_VIDEO_CANDIDATE_CALIBRATION_UP_DELTA:-0,0,0.0002}"
JOINT_RESPONSE_SUMMARY_PATH="/workspace/artifacts/calibration/joint_position_action/latest_seed_${SEED}.json"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
WATCHDOG_DIR="${RCA_VIDEO_CANDIDATE_WATCHDOG_LEDGER_DIR:-${REPO_ROOT}/artifacts/brev_paid_runs/${RUN_ID}_${ENV_NAME}}"
CREATED_INSTANCE=0
WATCHDOG_PID=""
RUN_STATUS=0

LEGACY_AGENT_ARGS=(
  --demo-reanchor-socket
  --demo-reanchor-initial-axial 0.050
  --demo-reanchor-orientation current
  --demo-reanchor-settle-steps 0
  --scripted-control-mode joint-ik
  --abs-control-mode waypoint
  --abs-pos-step-mode norm
  --approach-axis socket
  --target-action-pos-offset 0.036,-0.003,0.000
  --joint-ik-step 0.012
  --insert-descent-mode pose-target
  --insert-pos-step 0.006
  --insert-rot-step 0.060
  --insert-contact-force-aware-xy
  --insert-contact-force-min 0.5
  --insert-contact-force-scale 10.0
  --insert-contact-force-xy-gain 0.0015
  --insert-contact-force-xy-clamp 0.0015
  --insert-contact-force-xy-sign "${RCA_VIDEO_CANDIDATE_FORCE_XY_SIGN:-1.0}"
  --success-min-contact-force 0.5
)

JOINT_RESPONSE_SOCKET_AGENT_ARGS=(
  --demo-reanchor-socket
  --demo-reanchor-initial-axial 0.050
  --demo-reanchor-orientation current
  --demo-reanchor-settle-steps 0
  --scripted-control-mode joint-response
  --abs-control-mode waypoint
  --abs-pos-step-mode component
  --approach-axis world-z
  --joint-ik-step 0.035
  --insert-descent-mode joint-cache
  --joint-cache-live-polish
  --insert-pos-step 0.010
  --insert-rot-step 0.100
  --polish-xy-tol 0.020
  --polish-z-tol 0.055
  --polish-rot-tol 0.300
  --polish-rotation-mode current
  --settle-contact-retention
  --success-min-contact-force 0.5
  --success-hold-steps "${RCA_VIDEO_CANDIDATE_SUCCESS_HOLD_STEPS:-5}"
  --socket-insertion-servo
  --socket-insertion-servo-entry-xy-tol "${RCA_VIDEO_CANDIDATE_SOCKET_ENTRY_XY_TOL:-0.014}"
  --socket-insertion-servo-entry-z-tol "${RCA_VIDEO_CANDIDATE_SOCKET_ENTRY_Z_TOL:-0.055}"
  --socket-insertion-servo-entry-rot-tol "${RCA_VIDEO_CANDIDATE_SOCKET_ENTRY_ROT_TOL:-0.300}"
  --socket-insertion-servo-exit-xy-tol "${RCA_VIDEO_CANDIDATE_SOCKET_EXIT_XY_TOL:-0.020}"
  --socket-insertion-servo-exit-z-tol "${RCA_VIDEO_CANDIDATE_SOCKET_EXIT_Z_TOL:-0.070}"
  --socket-insertion-servo-exit-rot-tol "${RCA_VIDEO_CANDIDATE_SOCKET_EXIT_ROT_TOL:-0.500}"
  --socket-insertion-servo-xy-gain "${RCA_VIDEO_CANDIDATE_SOCKET_XY_GAIN:-0.85}"
  --socket-insertion-servo-xy-clamp "${RCA_VIDEO_CANDIDATE_SOCKET_XY_CLAMP:-0.0025}"
  --socket-insertion-servo-z-gain "${RCA_VIDEO_CANDIDATE_SOCKET_Z_GAIN:-1.0}"
  --socket-insertion-servo-z-step "${RCA_VIDEO_CANDIDATE_SOCKET_Z_STEP:-0.0002}"
  --socket-insertion-servo-contact-preload-step "${RCA_VIDEO_CANDIDATE_SOCKET_CONTACT_PRELOAD_STEP:-0.0002}"
  --socket-insertion-servo-contact-boundary-min-force "${RCA_VIDEO_CANDIDATE_SOCKET_CONTACT_BOUNDARY_MIN_FORCE:-0.25}"
  --socket-insertion-servo-contact-boundary-tol "${RCA_VIDEO_CANDIDATE_SOCKET_CONTACT_BOUNDARY_TOL:-0.0010}"
  --socket-insertion-servo-contact-boundary-step "${RCA_VIDEO_CANDIDATE_SOCKET_CONTACT_BOUNDARY_STEP:-0.00015}"
  --socket-insertion-servo-contact-boundary-xy-gain "${RCA_VIDEO_CANDIDATE_SOCKET_CONTACT_BOUNDARY_XY_GAIN:-0.15}"
  --socket-insertion-servo-contact-boundary-xy-clamp "${RCA_VIDEO_CANDIDATE_SOCKET_CONTACT_BOUNDARY_XY_CLAMP:-0.00035}"
  --socket-insertion-servo-maintain-contact-preload
  --socket-insertion-servo-rot-step "${RCA_VIDEO_CANDIDATE_SOCKET_ROT_STEP:-0.015}"
  --socket-insertion-servo-rotate-only-when-rot-misaligned
  --joint-response-json "${JOINT_RESPONSE_SUMMARY_PATH}"
  --joint-response-damping "${RCA_VIDEO_CANDIDATE_JOINT_RESPONSE_DAMPING:-0.0001}"
  --joint-response-max-delta "${RCA_VIDEO_CANDIDATE_JOINT_RESPONSE_MAX_DELTA:-0.04}"
  --trace-autoflush-every "${RCA_VIDEO_CANDIDATE_TRACE_AUTOFLUSH_EVERY:-1}"
  --stop-on-branch-jump
)

if [[ -n "${RCA_VIDEO_CANDIDATE_AGENT_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  AGENT_ARGS=(${RCA_VIDEO_CANDIDATE_AGENT_ARGS})
else
  case "${AGENT_MODE}" in
    joint-response-socket)
      AGENT_ARGS=("${JOINT_RESPONSE_SOCKET_AGENT_ARGS[@]}")
      ;;
    legacy-joint-ik)
      AGENT_ARGS=("${LEGACY_AGENT_ARGS[@]}")
      ;;
    *)
      echo "[peg-video-candidate] unsupported RCA_VIDEO_CANDIDATE_AGENT_MODE=${AGENT_MODE}" >&2
      exit 2
      ;;
  esac
fi

verify_watchdog_alive() {
  local pid="$1"
  local launcher_log="$2"

  sleep "${WATCHDOG_START_GRACE_SECONDS}"
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[peg-video-candidate] billing watchdog exited before instance creation; refusing paid create" >&2
    cat "${launcher_log}" >&2 2>/dev/null || true
    exit 2
  fi
}

start_billing_watchdog() {
  mkdir -p "${WATCHDOG_DIR}"
  echo "[peg-video-candidate] starting billing watchdog max_minutes=${WATCHDOG_MAX_MINUTES} ledger=${WATCHDOG_DIR}"
  nohup env \
    RCA_BREV_CLI="${BREV_BIN}" \
    RCA_BREV_WATCHDOG_INSTANCE_NAME="${ENV_NAME}" \
    RCA_BREV_WATCHDOG_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
    RCA_BREV_WATCHDOG_POLL_SECONDS="${WATCHDOG_POLL_SECONDS}" \
    RCA_BREV_WATCHDOG_WAIT_FOR_APPEAR=1 \
    RCA_BREV_WATCHDOG_WAIT_MAX_MINUTES="${WATCHDOG_WAIT_MAX_MINUTES}" \
    RCA_BREV_WATCHDOG_DASHBOARD_URL="${WATCHDOG_DASHBOARD_URL}" \
    RCA_BREV_WATCHDOG_LEDGER_DIR="${WATCHDOG_DIR}" \
    RCA_PAID_BUDGET_EUR="${RCA_PAID_BUDGET_EUR:-}" \
    RCA_PAID_ESTIMATED_EUR_PER_HOUR="${RCA_PAID_ESTIMATED_EUR_PER_HOUR:-}" \
    "${SCRIPT_DIR}/brev_paid_run_watchdog.sh" >"${WATCHDOG_DIR}/watchdog_launcher.log" 2>&1 &
  WATCHDOG_PID="$!"
  printf '%s\n' "${WATCHDOG_PID}" > "${WATCHDOG_DIR}/watchdog.pid"
  verify_watchdog_alive "${WATCHDOG_PID}" "${WATCHDOG_DIR}/watchdog_launcher.log"
  disown "${WATCHDOG_PID}" 2>/dev/null || true
}

matching_instance_tokens() {
  local raw
  raw="$("${BREV_BIN}" ls instances --json --all 2>/dev/null || true)"
  RCA_VIDEO_TARGET="${ENV_NAME}" RCA_VIDEO_INSTANCES_JSON="${raw}" python3 - <<'PY'
import json
import os

target = os.environ["RCA_VIDEO_TARGET"]
raw = os.environ.get("RCA_VIDEO_INSTANCES_JSON", "").strip()
try:
    data = json.loads(raw) if raw else {}
except json.JSONDecodeError:
    raise SystemExit(0)

if isinstance(data, dict):
    instances = data.get("workspaces") or data.get("instances") or []
elif isinstance(data, list):
    instances = data
else:
    instances = []

tokens: list[str] = []
for item in instances or []:
    if not isinstance(item, dict):
        continue
    name = str(item.get("name") or item.get("workspaceName") or item.get("workspace_name") or "")
    ident = str(item.get("id") or item.get("workspaceId") or item.get("workspace_id") or "")
    if target not in {name, ident}:
        continue
    for token in (name, ident):
        if token and token not in tokens:
            tokens.append(token)

for token in tokens:
    print(token)
PY
}

delete_instance() {
  local attempt tokens token

  echo "[peg-video-candidate] deleting Brev instance ${ENV_NAME}"
  "${BREV_BIN}" delete "${ENV_NAME}" || true
  for attempt in $(seq 1 "${DELETE_ATTEMPTS}"); do
    tokens="$(matching_instance_tokens || true)"
    if [[ -z "${tokens}" ]]; then
      echo "[peg-video-candidate] cleanup confirmed for ${ENV_NAME}"
      return 0
    fi

    while IFS= read -r token; do
      [[ -z "${token}" ]] && continue
      echo "[peg-video-candidate] deleting Brev instance token=${token} attempt=${attempt}"
      "${BREV_BIN}" delete "${token}" >/dev/null 2>&1 || true
    done <<< "${tokens}"

    sleep "${DELETE_RETRY_INTERVAL_SECONDS}"
  done

  echo "[peg-video-candidate] manual cleanup required: ${ENV_NAME} still visible or Brev CLI query failed" >&2
  "${BREV_BIN}" ls instances --json --all || true
  return 1
}

confirm_org_empty() {
  local attempt raw count parse_status

  echo "[peg-video-candidate] confirming Brev org is empty"
  for attempt in $(seq 1 "${DELETE_ATTEMPTS}"); do
    raw="$("${BREV_BIN}" ls instances --json --all 2>/dev/null || true)"
    set +e
    count="$(
      RCA_VIDEO_INSTANCES_JSON="${raw}" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("RCA_VIDEO_INSTANCES_JSON", "").strip()
try:
    data = json.loads(raw) if raw else {}
except json.JSONDecodeError:
    print("invalid")
    sys.exit(20)

if isinstance(data, dict):
    instances = data.get("workspaces") or data.get("instances") or []
elif isinstance(data, list):
    instances = data
else:
    instances = []

if instances is None:
    instances = []

print(len(instances))
PY
    )"
    parse_status=$?
    set -e
    if [[ "${parse_status}" -eq 0 && "${count}" == "0" ]]; then
      echo "[peg-video-candidate] org cleanup confirmed: ${raw}"
      return 0
    fi
    echo "[peg-video-candidate] org still not empty or unparsable attempt=${attempt}: ${raw}" >&2
    sleep "${DELETE_RETRY_INTERVAL_SECONDS}"
  done

  echo "[peg-video-candidate] manual cleanup required: Brev org is not confirmed empty" >&2
  "${BREV_BIN}" ls instances --json --all || true
  return 1
}

pull_remote_artifacts() {
  echo "[peg-video-candidate] pulling remote artifacts before cleanup"
  RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
    "${SCRIPT_DIR}/pull_artifacts.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${REPO_ROOT}/artifacts" || true
}

start_container_xvfb() {
  echo "[peg-video-candidate] starting Xvfb inside task container"
  ssh "${ENV_NAME}" "sudo docker exec -u root -i isaac-runner bash -s" <<'REMOTE_XVFB'
set -euo pipefail

copy_xvfb_logs() {
  mkdir -p /workspace/artifacts/runtime
  cp /tmp/rca-xvfb.log /workspace/artifacts/runtime/rca-xvfb.log 2>/dev/null || true
  cp /tmp/rca-xdpyinfo.txt /workspace/artifacts/runtime/rca-xdpyinfo.txt 2>/dev/null || true
  cp /tmp/rca-xvfb-apt.log /workspace/artifacts/runtime/rca-xvfb-apt.log 2>/dev/null || true
}
trap 'status=$?; copy_xvfb_logs; exit "${status}"' EXIT

apt-get update >/tmp/rca-xvfb-apt.log 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y xvfb xauth x11-xserver-utils x11-utils >>/tmp/rca-xvfb-apt.log 2>&1
pkill -TERM -x Xvfb 2>/dev/null || true
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 /tmp/rca-xvfb.log /tmp/rca-xdpyinfo.txt
mkdir -p /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix

nohup Xvfb :99 -screen 0 1280x720x24 -ac -nolisten tcp -extension GLX >/tmp/rca-xvfb.log 2>&1 &
xvfb_pid=$!
echo "${xvfb_pid}" >/tmp/rca-xvfb.pid

for _ in $(seq 1 20); do
  if ! kill -0 "${xvfb_pid}" 2>/dev/null; then
    echo "[xvfb] Xvfb exited before display became available" >&2
    cat /tmp/rca-xvfb.log >&2 || true
    cat /tmp/rca-xdpyinfo.txt >&2 || true
    exit 1
  fi
  if DISPLAY=:99 xdpyinfo >/tmp/rca-xdpyinfo.txt 2>&1; then
    head -n 5 /tmp/rca-xdpyinfo.txt
    exit 0
  fi
  sleep 1
done

echo "[xvfb] display :99 did not become available" >&2
cat /tmp/rca-xvfb.log >&2 || true
cat /tmp/rca-xdpyinfo.txt >&2 || true
exit 1
REMOTE_XVFB
}

cleanup() {
  local status=$?
  local cleanup_status=0
  set +e
  echo "[peg-video-candidate] cleanup status=${status}"
  if [[ "${CREATED_INSTANCE}" == "1" ]]; then
    pull_remote_artifacts
    delete_instance || cleanup_status=1
    confirm_org_empty || cleanup_status=1
  else
    echo "[peg-video-candidate] no Brev instance was created"
    confirm_org_empty || cleanup_status=1
  fi
  if [[ "${cleanup_status}" -ne 0 && "${status}" -eq 0 ]]; then
    status=1
  fi
  exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${RCA_ALLOW_PAID_BREV_CREATE:-0}" != "1" ]]; then
  cat >&2 <<'EOF'
[peg-video-candidate] refusing to create a paid Brev instance.
[peg-video-candidate] Set RCA_ALLOW_PAID_BREV_CREATE=1 and RCA_BREV_CREDITS_VERIFIED=1 only after confirming credits, budget, and deletion path.
EOF
  exit 2
fi

if [[ "${RCA_ISAACLAB_RUNTIME_PROFILE:-}" == "trace-only" ]]; then
  case "${RECORDING_MODE}" in
    screen|viewport|camera)
      cat >&2 <<EOF
[peg-video-candidate] refusing ${RECORDING_MODE} recording with RCA_ISAACLAB_RUNTIME_PROFILE=trace-only.
[peg-video-candidate] trace-only is for semantic/headless validation. Use the full runtime profile for Isaac UI/viewport/camera recording, or render an already validated trace locally with scripts/render_trace_video.py.
EOF
      exit 2
      ;;
  esac
fi

RCA_PAID_RUN_PURPOSE="${RCA_PAID_RUN_PURPOSE:-post_contact_gate}" \
RCA_PAID_INSTANCE_NAME="${ENV_NAME}" \
RCA_PAID_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
RCA_BREV_CREDITS_VERIFIED="${RCA_BREV_CREDITS_VERIFIED:-0}" \
RCA_BREV_CLI="${BREV_BIN}" \
  "${SCRIPT_DIR}/paid_compute_preflight.sh"

echo "[peg-video-candidate] creating Brev instance ${ENV_NAME} type=${INSTANCE_TYPE}"
CREATED_INSTANCE=1
start_billing_watchdog
"${BREV_BIN}" create "${ENV_NAME}" \
  --type "${INSTANCE_TYPE}" \
  --min-disk "${MIN_DISK}" \
  --stoppable \
  --timeout "${CREATE_TIMEOUT}"

echo "[peg-video-candidate] bootstrapping remote workspace"
RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
  "${SCRIPT_DIR}/bootstrap_brev_workspace.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

echo "[peg-video-candidate] syncing repository"
RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
  "${SCRIPT_DIR}/sync_to_brev.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

echo "[peg-video-candidate] installing Isaac Lab runtime"
RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
RCA_SKIP_STREAM_STACK="${RCA_SKIP_STREAM_STACK:-1}" \
  "${SCRIPT_DIR}/install_remote_isaaclab_runtime.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${COMPOSE_ROOT}"

start_container_xvfb

if [[ "${AGENT_MODE}" == "joint-response-socket" && "${RECORDING_MODE}" != "trace-replay" && -z "${RCA_VIDEO_CANDIDATE_AGENT_ARGS:-}" ]]; then
  echo "[peg-video-candidate] calibrating JointPositionAction response for video controller"
  RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
  RCA_REMOTE_DOCKER_EXEC_ENV="-u root -e DISPLAY=:99" \
  RCA_JOINT_RESPONSE_CALIBRATION_DOWN_DELTA="${CALIBRATION_DOWN_DELTA}" \
  RCA_JOINT_RESPONSE_CALIBRATION_UP_DELTA="${CALIBRATION_UP_DELTA}" \
    "${SCRIPT_DIR}/run_remote_joint_response_calibration.sh" \
      "${ENV_NAME}" \
      "${REMOTE_ROOT}" \
      "${COMPOSE_ROOT}" \
      "${TASK_NAME}" \
      "${CALIBRATION_STEPS_PER_PROBE}" \
      "${SEED}" \
      "${CALIBRATION_TIMEOUT_SECONDS}"
fi

echo "[peg-video-candidate] recording and validating scripted video candidate"
echo "[peg-video-candidate] recording_mode=${RECORDING_MODE}"
RUN_STATUS=0
set +e
case "${RECORDING_MODE}" in
  screen)
    RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
    RCA_REMOTE_DOCKER_EXEC_ENV="-u root -e DISPLAY=:99" \
    RCA_SCREEN_VIDEO_TIMEOUT_SECONDS="${VIDEO_TIMEOUT_SECONDS}" \
    RCA_SCREEN_VIDEO_TIMEOUT_KILL_SECONDS="${VIDEO_TIMEOUT_KILL_SECONDS}" \
    RCA_VALIDATE_PEG_VIDEO_CANDIDATE=1 \
    RCA_VALIDATE_ACTION_RESPONSE=1 \
    RCA_ACTION_RESPONSE_MIN_COMMAND_NORM="${RCA_VIDEO_CANDIDATE_ACTION_RESPONSE_MIN_COMMAND_NORM:-0.0002}" \
    RCA_ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS="${RCA_VIDEO_CANDIDATE_ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS:-1}" \
    RCA_VALIDATE_FINAL_CONTACT_BOUNDARY=1 \
    RCA_VALIDATE_TRACE_FRAME_ALIGNMENT=1 \
      "${SCRIPT_DIR}/run_remote_record_scripted_screen_video.sh" \
        "${ENV_NAME}" \
        "${REMOTE_ROOT}" \
        "${COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        1 \
        "${VIDEO_LENGTH}" \
        "${SEED}" \
        "${SCRIPTED_STEPS}" \
        "${AGENT_ARGS[*]}"
    ;;
  viewport)
    RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
    RCA_REMOTE_DOCKER_EXEC_ENV="-u root -e DISPLAY=:99" \
    RCA_VIDEO_TIMEOUT_SECONDS="${VIDEO_TIMEOUT_SECONDS}" \
    RCA_VIDEO_TIMEOUT_KILL_SECONDS="${VIDEO_TIMEOUT_KILL_SECONDS}" \
    RCA_VALIDATE_PEG_VIDEO_CANDIDATE=1 \
    RCA_VALIDATE_ACTION_RESPONSE=1 \
    RCA_ACTION_RESPONSE_MIN_COMMAND_NORM="${RCA_VIDEO_CANDIDATE_ACTION_RESPONSE_MIN_COMMAND_NORM:-0.0002}" \
    RCA_ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS="${RCA_VIDEO_CANDIDATE_ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS:-1}" \
    RCA_VALIDATE_FINAL_CONTACT_BOUNDARY=1 \
    RCA_VALIDATE_TRACE_FRAME_ALIGNMENT=1 \
    RCA_RECORD_SCRIPTED_SYNC_BEFORE_RUN=0 \
    RCA_AUTO_VIEWPORT_KIT_ARGS="${RCA_AUTO_VIEWPORT_KIT_ARGS:-1}" \
    RCA_VIDEO_BACKEND="${RCA_VIDEO_BACKEND:-viewport}" \
      "${SCRIPT_DIR}/run_remote_record_scripted_video.sh" \
        "${ENV_NAME}" \
        "${REMOTE_ROOT}" \
        "${COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        1 \
        "${VIDEO_LENGTH}" \
        "${SEED}" \
        "${SCRIPTED_STEPS}" \
        "${AGENT_ARGS[*]}"
    ;;
  camera)
    RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
    RCA_REMOTE_DOCKER_EXEC_ENV="-u root -e DISPLAY=:99" \
    RCA_VIDEO_TIMEOUT_SECONDS="${VIDEO_TIMEOUT_SECONDS}" \
    RCA_VIDEO_TIMEOUT_KILL_SECONDS="${VIDEO_TIMEOUT_KILL_SECONDS}" \
    RCA_VALIDATE_PEG_VIDEO_CANDIDATE=1 \
    RCA_VALIDATE_ACTION_RESPONSE=1 \
    RCA_ACTION_RESPONSE_MIN_COMMAND_NORM="${RCA_VIDEO_CANDIDATE_ACTION_RESPONSE_MIN_COMMAND_NORM:-0.0002}" \
    RCA_ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS="${RCA_VIDEO_CANDIDATE_ACTION_RESPONSE_STOP_AFTER_FIRST_SUCCESS:-1}" \
    RCA_VALIDATE_FINAL_CONTACT_BOUNDARY=1 \
    RCA_VALIDATE_TRACE_FRAME_ALIGNMENT=1 \
    RCA_RECORD_SCRIPTED_SYNC_BEFORE_RUN=0 \
    RCA_AUTO_VIEWPORT_KIT_ARGS=0 \
    RCA_VIDEO_BACKEND=camera \
      "${SCRIPT_DIR}/run_remote_record_scripted_video.sh" \
        "${ENV_NAME}" \
        "${REMOTE_ROOT}" \
        "${COMPOSE_ROOT}" \
        "${TASK_NAME}" \
        1 \
        "${VIDEO_LENGTH}" \
        "${SEED}" \
        "${SCRIPTED_STEPS}" \
        "${AGENT_ARGS[*]}"
    ;;
  trace-replay)
    RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
    RCA_REMOTE_DOCKER_EXEC_ENV="-u root -e DISPLAY=:99" \
    RCA_REPLAY_VIDEO_TIMEOUT_SECONDS="${VIDEO_TIMEOUT_SECONDS}" \
    RCA_REPLAY_VIDEO_TIMEOUT_KILL_SECONDS="${VIDEO_TIMEOUT_KILL_SECONDS}" \
    RCA_REPLAY_TRACE_SEED="${SEED}" \
      "${SCRIPT_DIR}/run_remote_replay_trace_video.sh" \
        "${ENV_NAME}" \
        "${REMOTE_ROOT}" \
        "${COMPOSE_ROOT}" \
        "${TASK_NAME}"
    ;;
  *)
    echo "[peg-video-candidate] unsupported RCA_VIDEO_CANDIDATE_RECORDING_MODE=${RECORDING_MODE}" >&2
    exit 2
    ;;
esac
RUN_STATUS=$?
set -e

if [[ "${RUN_STATUS}" -ne 0 ]]; then
  echo "[peg-video-candidate] candidate video validation failed status=${RUN_STATUS}" >&2
  exit "${RUN_STATUS}"
fi

echo "[peg-video-candidate] PASS: validated peg-in-hole video candidate recorded"
