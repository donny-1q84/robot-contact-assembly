#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_NAME="${1:-isaac-l40s}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-IK-Rel-Polish-v0}"
NUM_ENVS="${5:-32}"
MAX_ITERATIONS="${6:-50}"
SEED="${7:-42}"
RUN_NAME="${8:-phase1_polish_v2}"
LOAD_RUN_REGEX="${9:-.*phase1_fix6_formal.*}"
CHECKPOINT_NAME="${10:-model_299.pt}"
EVAL_STEPS="${11:-400}"
MAX_CHECKPOINTS="${12:-0}"

BREV_BIN="${BREV_BIN:-/Users/Shenghan/bin/brev}"
GPU_NAME="${GPU_NAME:-L40S}"
MIN_TOTAL_VRAM="${MIN_TOTAL_VRAM:-40}"
MIN_DISK="${MIN_DISK:-500}"
CREATE_TIMEOUT="${CREATE_TIMEOUT:-900}"
DELETE_ON_EXIT="${RCA_RECREATE_DELETE_ON_EXIT:-1}"
KEEP_ON_FAILURE="${RCA_RECREATE_KEEP_ON_FAILURE:-0}"
WATCHDOG_ENABLED="${RCA_RECREATE_WATCHDOG_ENABLED:-1}"
WATCHDOG_MAX_MINUTES="${RCA_RECREATE_WATCHDOG_MAX_MINUTES:-180}"
WATCHDOG_POLL_SECONDS="${RCA_RECREATE_WATCHDOG_POLL_SECONDS:-120}"
WATCHDOG_WAIT_MAX_MINUTES="${RCA_RECREATE_WATCHDOG_WAIT_MAX_MINUTES:-$(( (CREATE_TIMEOUT + 599) / 60 + 10 ))}"
WATCHDOG_DASHBOARD_URL="${RCA_RECREATE_WATCHDOG_DASHBOARD_URL:-https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
WATCHDOG_DIR="${RCA_RECREATE_WATCHDOG_LEDGER_DIR:-/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/brev_paid_runs/${RUN_ID}_${ENV_NAME}}"
CREATED_INSTANCE=0
WATCHDOG_PID=""

start_billing_watchdog() {
  if [[ "${WATCHDOG_ENABLED}" != "1" ]]; then
    echo "[recreate] billing watchdog disabled by RCA_RECREATE_WATCHDOG_ENABLED=${WATCHDOG_ENABLED}"
    return 0
  fi

  mkdir -p "${WATCHDOG_DIR}"
  echo "[recreate] starting billing watchdog max_minutes=${WATCHDOG_MAX_MINUTES} ledger=${WATCHDOG_DIR}"
  nohup env \
    RCA_BREV_CLI="${BREV_BIN}" \
    RCA_BREV_WATCHDOG_INSTANCE_NAME="${ENV_NAME}" \
    RCA_BREV_WATCHDOG_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
    RCA_BREV_WATCHDOG_POLL_SECONDS="${WATCHDOG_POLL_SECONDS}" \
    RCA_BREV_WATCHDOG_WAIT_FOR_APPEAR=1 \
    RCA_BREV_WATCHDOG_WAIT_MAX_MINUTES="${WATCHDOG_WAIT_MAX_MINUTES}" \
    RCA_BREV_WATCHDOG_DASHBOARD_URL="${WATCHDOG_DASHBOARD_URL}" \
    RCA_BREV_WATCHDOG_LEDGER_DIR="${WATCHDOG_DIR}" \
    "${SCRIPT_DIR}/brev_paid_run_watchdog.sh" >"${WATCHDOG_DIR}/watchdog_launcher.log" 2>&1 &
  WATCHDOG_PID="$!"
  printf '%s\n' "${WATCHDOG_PID}" > "${WATCHDOG_DIR}/watchdog.pid"
  disown "${WATCHDOG_PID}" 2>/dev/null || true
}

cleanup() {
  local status=$?
  set +e
  echo "[recreate] cleanup status=${status}"
  if [[ "${CREATED_INSTANCE}" == "1" && "${DELETE_ON_EXIT}" == "1" && ( "${KEEP_ON_FAILURE}" != "1" || "${status}" == "0" ) ]]; then
    echo "[recreate] deleting Brev instance ${ENV_NAME}"
    "${BREV_BIN}" delete "${ENV_NAME}" || true
    "${BREV_BIN}" ls instances --json --all || true
  elif [[ "${CREATED_INSTANCE}" == "1" ]]; then
    echo "[recreate] skipping delete: CREATED_INSTANCE=${CREATED_INSTANCE} DELETE_ON_EXIT=${DELETE_ON_EXIT} KEEP_ON_FAILURE=${KEEP_ON_FAILURE} status=${status}"
    "${BREV_BIN}" ls instances --json --all || true
  else
    echo "[recreate] skipping delete: CREATED_INSTANCE=${CREATED_INSTANCE} DELETE_ON_EXIT=${DELETE_ON_EXIT} KEEP_ON_FAILURE=${KEEP_ON_FAILURE} status=${status}"
  fi
  exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${RCA_ALLOW_PAID_BREV_CREATE:-0}" != "1" ]]; then
  cat >&2 <<'EOF'
[recreate] refusing to create a paid Brev instance.
[recreate] Set RCA_ALLOW_PAID_BREV_CREATE=1 only after confirming credits/budget and a manual deletion path in the Brev UI.
EOF
  exit 2
fi

echo "[recreate] creating Brev instance ${ENV_NAME}"
CREATED_INSTANCE=1
start_billing_watchdog
"${BREV_BIN}" create "${ENV_NAME}" \
  --gpu-name "${GPU_NAME}" \
  --min-total-vram "${MIN_TOTAL_VRAM}" \
  --min-disk "${MIN_DISK}" \
  --stoppable \
  --timeout "${CREATE_TIMEOUT}"

echo "[recreate] bootstrapping remote workspace"
bash "${SCRIPT_DIR}/bootstrap_brev_workspace.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

echo "[recreate] syncing repository"
bash "${SCRIPT_DIR}/sync_to_brev.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

echo "[recreate] installing Isaac Lab runtime"
bash "${SCRIPT_DIR}/install_remote_isaaclab_runtime.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${COMPOSE_ROOT}"

echo "[recreate] checking runtime"
bash "${SCRIPT_DIR}/check_remote_runtime.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${COMPOSE_ROOT}"

echo "[recreate] running polish cycle"
bash "${SCRIPT_DIR}/run_remote_polish_cycle.sh" \
  "${ENV_NAME}" \
  "${REMOTE_ROOT}" \
  "${COMPOSE_ROOT}" \
  "${TASK_NAME}" \
  "${NUM_ENVS}" \
  "${MAX_ITERATIONS}" \
  "${SEED}" \
  "${RUN_NAME}" \
  "${LOAD_RUN_REGEX}" \
  "${CHECKPOINT_NAME}" \
  "${EVAL_STEPS}" \
  "${MAX_CHECKPOINTS}"
