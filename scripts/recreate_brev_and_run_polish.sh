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
WATCHDOG_MAX_MINUTES="${RCA_RECREATE_WATCHDOG_MAX_MINUTES:-180}"
WATCHDOG_POLL_SECONDS="${RCA_RECREATE_WATCHDOG_POLL_SECONDS:-120}"
WATCHDOG_WAIT_MAX_MINUTES="${RCA_RECREATE_WATCHDOG_WAIT_MAX_MINUTES:-$(( (CREATE_TIMEOUT + 599) / 60 + 10 ))}"
WATCHDOG_START_GRACE_SECONDS="${RCA_RECREATE_WATCHDOG_START_GRACE_SECONDS:-2}"
WATCHDOG_DASHBOARD_URL="${RCA_RECREATE_WATCHDOG_DASHBOARD_URL:-https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments}"
DELETE_ATTEMPTS="${RCA_RECREATE_DELETE_ATTEMPTS:-30}"
DELETE_RETRY_INTERVAL_SECONDS="${RCA_RECREATE_DELETE_RETRY_INTERVAL_SECONDS:-20}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
WATCHDOG_DIR="${RCA_RECREATE_WATCHDOG_LEDGER_DIR:-/Volumes/Extreme Pro/Projects/robot-contact-assembly/artifacts/brev_paid_runs/${RUN_ID}_${ENV_NAME}}"
CREATED_INSTANCE=0
WATCHDOG_PID=""

start_billing_watchdog() {
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
  verify_watchdog_alive "${WATCHDOG_PID}" "${WATCHDOG_DIR}/watchdog_launcher.log"
  disown "${WATCHDOG_PID}" 2>/dev/null || true
}

verify_watchdog_alive() {
  local pid="$1"
  local launcher_log="$2"

  sleep "${WATCHDOG_START_GRACE_SECONDS}"
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[recreate] billing watchdog exited before instance creation; refusing paid create" >&2
    cat "${launcher_log}" >&2 2>/dev/null || true
    exit 2
  fi
}

matching_instance_tokens() {
  local raw
  raw="$("${BREV_BIN}" ls instances --json --all 2>/dev/null || true)"
  RECREATE_TARGET="${ENV_NAME}" RECREATE_INSTANCES_JSON="${raw}" python3 - <<'PY'
import json
import os

target = os.environ["RECREATE_TARGET"]
raw = os.environ.get("RECREATE_INSTANCES_JSON", "").strip()
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
for item in instances:
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

  echo "[recreate] deleting Brev instance ${ENV_NAME}"
  "${BREV_BIN}" delete "${ENV_NAME}" || true
  for attempt in $(seq 1 "${DELETE_ATTEMPTS}"); do
    tokens="$(matching_instance_tokens || true)"
    if [[ -z "${tokens}" ]]; then
      echo "[recreate] cleanup confirmed for ${ENV_NAME}"
      return 0
    fi

    while IFS= read -r token; do
      [[ -z "${token}" ]] && continue
      echo "[recreate] deleting Brev instance token=${token} attempt=${attempt}"
      "${BREV_BIN}" delete "${token}" >/dev/null 2>&1 || true
    done <<< "${tokens}"

    sleep "${DELETE_RETRY_INTERVAL_SECONDS}"
  done

  echo "[recreate] manual cleanup required: ${ENV_NAME} still visible or Brev CLI query failed" >&2
  "${BREV_BIN}" ls instances --json --all || true
  return 1
}

cleanup() {
  local status=$?
  set +e
  echo "[recreate] cleanup status=${status}"
  if [[ "${CREATED_INSTANCE}" == "1" ]]; then
    delete_instance || true
  else
    echo "[recreate] no Brev instance was created"
  fi
  exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${RCA_ALLOW_PAID_BREV_CREATE:-0}" != "1" ]]; then
  cat >&2 <<'EOF'
[recreate] refusing to create a paid Brev instance.
[recreate] Set RCA_ALLOW_PAID_BREV_CREATE=1 and RCA_BREV_CREDITS_VERIFIED=1 only after confirming credits/budget and a manual deletion path in the Brev UI.
EOF
  exit 2
fi

RCA_PAID_RUN_PURPOSE="${RCA_PAID_RUN_PURPOSE:-post_contact_gate}" \
RCA_PAID_INSTANCE_NAME="${ENV_NAME}" \
RCA_PAID_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
RCA_BREV_CREDITS_VERIFIED="${RCA_BREV_CREDITS_VERIFIED:-0}" \
RCA_BREV_CLI="${BREV_BIN}" \
  "${SCRIPT_DIR}/paid_compute_preflight.sh"

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
