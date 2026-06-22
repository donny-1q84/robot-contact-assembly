#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_NAME="${1:-rca-final-contact-servo-vm}"
REMOTE_ROOT="${2:-/home/ubuntu/projects/robot-contact-assembly}"
COMPOSE_ROOT="${3:-/home/ubuntu/isaac-compose}"
TASK_NAME="${4:-RCA-PegInHole-Franka-JointPos-Contact-Play-v0}"
STEPS="${5:-1200}"
SEED="${6:-42}"

BREV_BIN="${BREV_BIN:-/Users/Shenghan/bin/brev}"
INSTANCE_TYPE="${RCA_FINAL_CONTACT_INSTANCE_TYPE:-g6e.xlarge}"
MIN_DISK="${RCA_FINAL_CONTACT_MIN_DISK:-500}"
CREATE_TIMEOUT="${RCA_FINAL_CONTACT_CREATE_TIMEOUT:-900}"
WATCHDOG_MAX_MINUTES="${RCA_FINAL_CONTACT_WATCHDOG_MAX_MINUTES:-45}"
WATCHDOG_POLL_SECONDS="${RCA_FINAL_CONTACT_WATCHDOG_POLL_SECONDS:-60}"
WATCHDOG_WAIT_MAX_MINUTES="${RCA_FINAL_CONTACT_WATCHDOG_WAIT_MAX_MINUTES:-$(( (CREATE_TIMEOUT + 599) / 60 + 10 ))}"
WATCHDOG_START_GRACE_SECONDS="${RCA_FINAL_CONTACT_WATCHDOG_START_GRACE_SECONDS:-2}"
WATCHDOG_DASHBOARD_URL="${RCA_FINAL_CONTACT_DASHBOARD_URL:-https://brev.nvidia.com/org/org-3BaYGdtoRGmgc77Z7NHHhPSD254/environments}"
DELETE_ATTEMPTS="${RCA_FINAL_CONTACT_DELETE_ATTEMPTS:-45}"
DELETE_RETRY_INTERVAL_SECONDS="${RCA_FINAL_CONTACT_DELETE_RETRY_INTERVAL_SECONDS:-10}"
TRACE_TIMEOUT_SECONDS="${RCA_FINAL_CONTACT_TRACE_TIMEOUT_SECONDS:-900}"
TRACE_TIMEOUT_KILL_SECONDS="${RCA_FINAL_CONTACT_TRACE_TIMEOUT_KILL_SECONDS:-45}"
TRACE_RUNNER="${RCA_FINAL_CONTACT_TRACE_RUNNER:-${SCRIPT_DIR}/run_remote_final_contact_servo_trace.sh}"
VALIDATE_PEG_VIDEO_CANDIDATE="${RCA_FINAL_CONTACT_VALIDATE_PEG_VIDEO_CANDIDATE:-${RCA_VALIDATE_PEG_VIDEO_CANDIDATE:-1}}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
WATCHDOG_DIR="${RCA_FINAL_CONTACT_WATCHDOG_LEDGER_DIR:-${REPO_ROOT}/artifacts/brev_paid_runs/${RUN_ID}_${ENV_NAME}}"
CREATED_INSTANCE=0
WATCHDOG_PID=""

verify_watchdog_alive() {
  local pid="$1"
  local launcher_log="$2"

  sleep "${WATCHDOG_START_GRACE_SECONDS}"
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[final-contact-servo] billing watchdog exited before instance creation; refusing paid create" >&2
    cat "${launcher_log}" >&2 2>/dev/null || true
    exit 2
  fi
}

start_billing_watchdog() {
  mkdir -p "${WATCHDOG_DIR}"
  echo "[final-contact-servo] starting billing watchdog max_minutes=${WATCHDOG_MAX_MINUTES} ledger=${WATCHDOG_DIR}"
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
  RCA_FINAL_CONTACT_TARGET="${ENV_NAME}" RCA_FINAL_CONTACT_INSTANCES_JSON="${raw}" python3 - <<'PY'
import json
import os

target = os.environ["RCA_FINAL_CONTACT_TARGET"]
raw = os.environ.get("RCA_FINAL_CONTACT_INSTANCES_JSON", "").strip()
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

  echo "[final-contact-servo] deleting Brev instance ${ENV_NAME}"
  "${BREV_BIN}" delete "${ENV_NAME}" || true
  for attempt in $(seq 1 "${DELETE_ATTEMPTS}"); do
    tokens="$(matching_instance_tokens || true)"
    if [[ -z "${tokens}" ]]; then
      echo "[final-contact-servo] cleanup confirmed for ${ENV_NAME}"
      return 0
    fi

    while IFS= read -r token; do
      [[ -z "${token}" ]] && continue
      echo "[final-contact-servo] deleting Brev instance token=${token} attempt=${attempt}"
      "${BREV_BIN}" delete "${token}" >/dev/null 2>&1 || true
    done <<< "${tokens}"

    sleep "${DELETE_RETRY_INTERVAL_SECONDS}"
  done

  tokens="$(matching_instance_tokens || true)"
  if [[ -z "${tokens}" ]]; then
    echo "[final-contact-servo] cleanup confirmed for ${ENV_NAME}"
    return 0
  fi

  echo "[final-contact-servo] manual cleanup required: ${ENV_NAME} still visible or Brev CLI query failed" >&2
  "${BREV_BIN}" ls instances --json --all || true
  return 1
}

confirm_org_empty() {
  local attempt raw count parse_status

  echo "[final-contact-servo] confirming Brev org is empty"
  for attempt in $(seq 1 "${DELETE_ATTEMPTS}"); do
    raw="$("${BREV_BIN}" ls instances --json --all 2>/dev/null || true)"
    set +e
    count="$(
      RCA_FINAL_CONTACT_INSTANCES_JSON="${raw}" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("RCA_FINAL_CONTACT_INSTANCES_JSON", "").strip()
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
      echo "[final-contact-servo] org cleanup confirmed: ${raw}"
      return 0
    fi
    echo "[final-contact-servo] org still not empty or unparsable attempt=${attempt}: ${raw}" >&2
    sleep "${DELETE_RETRY_INTERVAL_SECONDS}"
  done

  echo "[final-contact-servo] manual cleanup required: Brev org is not confirmed empty" >&2
  "${BREV_BIN}" ls instances --json --all || true
  return 1
}

pull_remote_artifacts() {
  echo "[final-contact-servo] pulling remote artifacts before cleanup"
  RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
    "${SCRIPT_DIR}/pull_artifacts.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${REPO_ROOT}/artifacts" || true
}

start_container_xvfb() {
  echo "[final-contact-servo] starting Xvfb inside task container"
  "${BREV_BIN}" exec "${ENV_NAME}" \
    "sudo docker exec -u root isaac-runner bash -lc 'set -euo pipefail; apt-get update >/dev/null; DEBIAN_FRONTEND=noninteractive apt-get install -y xvfb xauth x11-xserver-utils x11-utils >/dev/null; pkill -TERM -x Xvfb 2>/dev/null || true; nohup Xvfb :99 -screen 0 1280x720x24 -ac -extension GLX >/tmp/rca-xvfb.log 2>&1 & sleep 2; DISPLAY=:99 xdpyinfo | head -5'"
}

cleanup() {
  local status=$?
  local cleanup_status=0
  set +e
  echo "[final-contact-servo] cleanup status=${status}"
  if [[ "${CREATED_INSTANCE}" == "1" ]]; then
    pull_remote_artifacts
    delete_instance || cleanup_status=1
    if confirm_org_empty; then
      cleanup_status=0
    else
      cleanup_status=1
    fi
  else
    echo "[final-contact-servo] no Brev instance was created"
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
[final-contact-servo] refusing to create a paid Brev instance.
[final-contact-servo] Set RCA_ALLOW_PAID_BREV_CREATE=1 and RCA_BREV_CREDITS_VERIFIED=1 only after confirming credits, budget, and deletion path.
EOF
  exit 2
fi

RCA_PAID_RUN_PURPOSE="${RCA_PAID_RUN_PURPOSE:-post_contact_gate}" \
RCA_PAID_INSTANCE_NAME="${ENV_NAME}" \
RCA_PAID_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
RCA_BREV_CREDITS_VERIFIED="${RCA_BREV_CREDITS_VERIFIED:-0}" \
RCA_BREV_CLI="${BREV_BIN}" \
  "${SCRIPT_DIR}/paid_compute_preflight.sh"

echo "[final-contact-servo] creating Brev instance ${ENV_NAME} type=${INSTANCE_TYPE}"
CREATED_INSTANCE=1
start_billing_watchdog
"${BREV_BIN}" create "${ENV_NAME}" \
  --type "${INSTANCE_TYPE}" \
  --min-disk "${MIN_DISK}" \
  --stoppable \
  --timeout "${CREATE_TIMEOUT}"

echo "[final-contact-servo] bootstrapping remote workspace"
RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
  "${SCRIPT_DIR}/bootstrap_brev_workspace.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

echo "[final-contact-servo] syncing repository"
RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
  "${SCRIPT_DIR}/sync_to_brev.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

echo "[final-contact-servo] installing Isaac Lab runtime"
RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
RCA_ISAACLAB_RUNTIME_PROFILE="${RCA_ISAACLAB_RUNTIME_PROFILE:-trace-only}" \
RCA_SKIP_STREAM_STACK="${RCA_SKIP_STREAM_STACK:-1}" \
  "${SCRIPT_DIR}/install_remote_isaaclab_runtime.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${COMPOSE_ROOT}"

start_container_xvfb

echo "[final-contact-servo] running trace-only final-contact servo validation"
set +e
RCA_REMOTE_OPERATION_PURPOSE=post_contact_gate \
RCA_REMOTE_DOCKER_EXEC_ENV="-u root -e DISPLAY=:99" \
RCA_TRACE_ONLY_TIMEOUT_SECONDS="${TRACE_TIMEOUT_SECONDS}" \
RCA_TRACE_ONLY_TIMEOUT_KILL_SECONDS="${TRACE_TIMEOUT_KILL_SECONDS}" \
RCA_VALIDATE_PEG_VIDEO_CANDIDATE="${VALIDATE_PEG_VIDEO_CANDIDATE}" \
  "${TRACE_RUNNER}" \
    "${ENV_NAME}" \
    "${REMOTE_ROOT}" \
    "${COMPOSE_ROOT}" \
    "${TASK_NAME}" \
    1 \
    "${STEPS}" \
    "${SEED}"
run_status=$?
set -e

if [[ "${run_status}" -ne 0 ]]; then
  echo "[final-contact-servo] trace validation failed status=${run_status}" >&2
  exit "${run_status}"
fi

if [[ "${VALIDATE_PEG_VIDEO_CANDIDATE}" == "1" ]]; then
  echo "[final-contact-servo] PASS: trace validated as peg-in-hole video candidate"
else
  echo "[final-contact-servo] PASS: trace runner completed; peg video candidate validation was disabled"
fi
