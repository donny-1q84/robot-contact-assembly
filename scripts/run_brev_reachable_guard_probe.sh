#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

BREV_BIN="${BREV_BIN:-/Users/Shenghan/bin/brev}"
ENV_NAME="${RCA_BREV_GUARD_ENV_NAME:-rca-reachable-guard-vm}"
REMOTE_ROOT="${RCA_BREV_GUARD_REMOTE_ROOT:-/home/ubuntu/projects/robot-contact-assembly}"
REMOTE_COMPOSE_ROOT="${RCA_BREV_GUARD_COMPOSE_ROOT:-/home/ubuntu/isaac-compose}"
PROVIDER="${RCA_BREV_GUARD_PROVIDER:-aws}"
GPU_NAME="${RCA_BREV_GUARD_GPU_NAME:-L40S}"
MIN_TOTAL_VRAM="${RCA_BREV_GUARD_MIN_TOTAL_VRAM:-40}"
MIN_DISK="${RCA_BREV_GUARD_MIN_DISK:-100}"
CREATE_TIMEOUT="${RCA_BREV_GUARD_CREATE_TIMEOUT:-900}"
INSTANCE_TYPE="${RCA_BREV_GUARD_INSTANCE_TYPE:-}"
WATCHDOG_MAX_MINUTES="${RCA_BREV_GUARD_WATCHDOG_MAX_MINUTES:-90}"
WATCHDOG_POLL_SECONDS="${RCA_BREV_GUARD_WATCHDOG_POLL_SECONDS:-60}"
WATCHDOG_WAIT_MAX_MINUTES="${RCA_BREV_GUARD_WATCHDOG_WAIT_MAX_MINUTES:-20}"
WATCHDOG_START_GRACE_SECONDS="${RCA_BREV_GUARD_WATCHDOG_START_GRACE_SECONDS:-2}"
PROBE_SCRIPT="${RCA_BREV_GUARD_PROBE_SCRIPT:-scripts/run_launchable_phase2_jointpos_reachable_guard_probe.sh}"
LOCAL_LOG_DIR="${RCA_BREV_GUARD_LOCAL_LOG_DIR:-${REPO_ROOT}/artifacts/launchable_logs}"
RUN_ID="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
WATCHDOG_DIR="${RCA_BREV_GUARD_WATCHDOG_DIR:-${REPO_ROOT}/artifacts/brev_paid_runs/${RUN_ID}_${ENV_NAME}}"
REMOTE_RESULTS="/home/ubuntu/rca-reachable-guard-results-${ENV_NAME}-${RUN_ID}.tar.gz"
REMOTE_DIAGNOSTICS="/home/ubuntu/rca-host-diagnostics-${ENV_NAME}-${RUN_ID}.txt"
CREATED_INSTANCE=0
WATCHDOG_PID=""

log() {
  echo "[reachable-guard-paid] $(date -u +"%Y-%m-%dT%H:%M:%SZ") $*" >&2
}

copy_if_present() {
  local remote_path="$1"
  local local_dir="$2"

  mkdir -p "${local_dir}"
  if ssh "${ENV_NAME}" "test -s '${remote_path}'" >/dev/null 2>&1; then
    log "copying ${remote_path} to ${local_dir}"
    "${BREV_BIN}" copy --host "${ENV_NAME}:${remote_path}" "${local_dir}/" || true
  else
    log "remote file not present: ${remote_path}"
  fi
}

delete_instance() {
  local ids

  if [[ "${CREATED_INSTANCE}" != "1" ]]; then
    return 0
  fi

  log "deleting Brev instance ${ENV_NAME}"
  "${BREV_BIN}" delete "${ENV_NAME}" || true
  for _ in $(seq 1 30); do
    local raw
    raw="$("${BREV_BIN}" ls instances --json --all 2>/dev/null || true)"
    printf '%s\n' "${raw}" > "${LOCAL_LOG_DIR}/latest_brev_instances_after_${ENV_NAME}.json" 2>/dev/null || true
    ids="$(
      REACHABLE_GUARD_TARGET="${ENV_NAME}" REACHABLE_GUARD_JSON="${raw}" python3 - <<'PY'
import json
import os

target = os.environ["REACHABLE_GUARD_TARGET"]
raw = os.environ.get("REACHABLE_GUARD_JSON", "").strip()
try:
    data = json.loads(raw) if raw else {}
except json.JSONDecodeError:
    raise SystemExit(0)

instances = []
if isinstance(data, dict):
    instances = data.get("workspaces") or data.get("instances") or []
elif isinstance(data, list):
    instances = data

seen: set[str] = set()
for item in instances:
    if not isinstance(item, dict):
        continue
    name = str(item.get("name") or item.get("workspaceName") or item.get("workspace_name") or "")
    ident = str(item.get("id") or item.get("workspaceId") or item.get("workspace_id") or "")
    if name != target:
        continue
    if ident and ident not in seen:
        seen.add(ident)
        print(ident)
PY
    )"
    while IFS= read -r id; do
      [[ -z "${id}" ]] && continue
      log "deleting Brev instance id=${id}"
      "${BREV_BIN}" delete "${id}" >/dev/null 2>&1 || true
    done <<< "${ids}"
    if python3 - "${ENV_NAME}" "${raw}" <<'PY'
import json
import sys

target = sys.argv[1]
raw = sys.argv[2].strip()
try:
    data = json.loads(raw) if raw else {}
except json.JSONDecodeError:
    raise SystemExit(1)
instances = data.get("workspaces") or data.get("instances") or []
for item in instances:
    if not isinstance(item, dict):
        continue
    if target in {str(item.get("name", "")), str(item.get("id", "")), str(item.get("workspaceId", ""))}:
        raise SystemExit(1)
raise SystemExit(0)
PY
    then
      log "cleanup confirmed for ${ENV_NAME}"
      return 0
    fi
    sleep 20
    log "waiting for ${ENV_NAME} to disappear"
    "${BREV_BIN}" delete "${ENV_NAME}" >/dev/null 2>&1 || true
  done

  log "manual cleanup required: ${ENV_NAME} still visible or Brev CLI query failed"
  return 1
}

verify_watchdog_alive() {
  local pid="$1"
  local launcher_log="$2"

  sleep "${WATCHDOG_START_GRACE_SECONDS}"
  if ! kill -0 "${pid}" 2>/dev/null; then
    log "billing watchdog exited before instance creation; refusing paid create"
    cat "${launcher_log}" >&2 2>/dev/null || true
    exit 2
  fi
}

cleanup() {
  local status=$?
  set +e
  log "cleanup status=${status}"
  if [[ "${CREATED_INSTANCE}" == "1" ]]; then
    copy_if_present "${REMOTE_RESULTS}" "${LOCAL_LOG_DIR}"
    copy_if_present "${REMOTE_DIAGNOSTICS}" "${LOCAL_LOG_DIR}"
  fi
  if [[ "${CREATED_INSTANCE}" == "1" ]]; then
    delete_instance || true
  else
    log "no Brev instance was created"
  fi
  "${BREV_BIN}" ls instances --json --all || true
  exit "${status}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "${RCA_ALLOW_PAID_BREV_CREATE:-0}" != "1" ]]; then
  cat >&2 <<'EOF'
[reachable-guard-paid] refusing to create a paid Brev instance.
[reachable-guard-paid] Set RCA_ALLOW_PAID_BREV_CREATE=1 and RCA_BREV_CREDITS_VERIFIED=1 only after confirming credits/budget and a manual deletion path in the Brev UI.
EOF
  exit 2
fi

RCA_PAID_RUN_PURPOSE="${RCA_PAID_RUN_PURPOSE:-post_contact_gate}" \
RCA_PAID_INSTANCE_NAME="${ENV_NAME}" \
RCA_PAID_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
RCA_BREV_CREDITS_VERIFIED="${RCA_BREV_CREDITS_VERIFIED:-0}" \
RCA_BREV_CLI="${BREV_BIN}" \
  "${SCRIPT_DIR}/paid_compute_preflight.sh"

mkdir -p "${LOCAL_LOG_DIR}" "${WATCHDOG_DIR}"

log "preflight Brev instance list"
"${BREV_BIN}" ls instances --json --all | tee "${LOCAL_LOG_DIR}/brev_pre_${ENV_NAME}_${RUN_ID}.json"

log "starting billing watchdog max_minutes=${WATCHDOG_MAX_MINUTES}"
nohup env \
  RCA_BREV_CLI="${BREV_BIN}" \
  RCA_BREV_WATCHDOG_INSTANCE_NAME="${ENV_NAME}" \
  RCA_BREV_WATCHDOG_MAX_MINUTES="${WATCHDOG_MAX_MINUTES}" \
  RCA_BREV_WATCHDOG_POLL_SECONDS="${WATCHDOG_POLL_SECONDS}" \
  RCA_BREV_WATCHDOG_WAIT_FOR_APPEAR=1 \
  RCA_BREV_WATCHDOG_WAIT_MAX_MINUTES="${WATCHDOG_WAIT_MAX_MINUTES}" \
  RCA_BREV_WATCHDOG_LEDGER_DIR="${WATCHDOG_DIR}" \
  "${SCRIPT_DIR}/brev_paid_run_watchdog.sh" >"${WATCHDOG_DIR}/watchdog_launcher.log" 2>&1 &
WATCHDOG_PID="$!"
printf '%s\n' "${WATCHDOG_PID}" > "${WATCHDOG_DIR}/watchdog.pid"
verify_watchdog_alive "${WATCHDOG_PID}" "${WATCHDOG_DIR}/watchdog_launcher.log"
disown "${WATCHDOG_PID}" 2>/dev/null || true

create_args=(
  "${ENV_NAME}"
  --provider "${PROVIDER}"
  --gpu-name "${GPU_NAME}"
  --min-total-vram "${MIN_TOTAL_VRAM}"
  --min-disk "${MIN_DISK}"
  --stoppable
  --timeout "${CREATE_TIMEOUT}"
)
if [[ -n "${INSTANCE_TYPE}" ]]; then
  create_args+=(--type "${INSTANCE_TYPE}")
fi

log "creating ${ENV_NAME} provider=${PROVIDER} gpu=${GPU_NAME} min_vram=${MIN_TOTAL_VRAM} min_disk=${MIN_DISK}"
CREATED_INSTANCE=1
"${BREV_BIN}" create "${create_args[@]}"

log "host GPU check"
"${BREV_BIN}" exec "${ENV_NAME}" --host "nvidia-smi"

log "bootstrapping remote workspace"
bash "${SCRIPT_DIR}/bootstrap_brev_workspace.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

log "syncing repository"
bash "${SCRIPT_DIR}/sync_to_brev.sh" "${ENV_NAME}" "${REMOTE_ROOT}"

log "installing Isaac runtime"
RCA_SKIP_STREAM_STACK="${RCA_SKIP_STREAM_STACK:-1}" \
  bash "${SCRIPT_DIR}/install_remote_isaaclab_runtime.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${REMOTE_COMPOSE_ROOT}"

log "starting Xvfb in task container"
ssh "${ENV_NAME}" "sudo docker exec -u root -i isaac-runner bash -s" <<'REMOTE_XVFB'
set -euo pipefail
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y xvfb xauth x11-xserver-utils x11-utils
pkill -TERM -x Xvfb 2>/dev/null || true
nohup Xvfb :99 -screen 0 1280x720x24 -ac -extension GLX >/tmp/rca-xvfb.log 2>&1 &
for _ in $(seq 1 20); do
  if DISPLAY=:99 xdpyinfo >/tmp/rca-xdpyinfo.txt 2>&1; then
    head -n 5 /tmp/rca-xdpyinfo.txt
    exit 0
  fi
  sleep 1
done
cat /tmp/rca-xvfb.log >&2 || true
cat /tmp/rca-xdpyinfo.txt >&2 || true
exit 1
REMOTE_XVFB

log "checking runtime"
RCA_REMOTE_DOCKER_EXEC_ENV='-u root -e DISPLAY=:99' \
  bash "${SCRIPT_DIR}/check_remote_runtime.sh" "${ENV_NAME}" "${REMOTE_ROOT}" "${REMOTE_COMPOSE_ROOT}"

log "running compact remote smoke"
RCA_REMOTE_DOCKER_EXEC_ENV='-u root -e DISPLAY=:99' \
  bash "${SCRIPT_DIR}/run_remote_smoke_test.sh" \
    "${ENV_NAME}" \
    "${REMOTE_ROOT}" \
    "${REMOTE_COMPOSE_ROOT}" \
    "RCA-PegInHole-Franka-JointPos-Contact-Play-v0" \
    3 \
    3 \
    20

log "running reachable joint-limit guard probe script=${PROBE_SCRIPT}"
RCA_REMOTE_DOCKER_EXEC_ENV='-u root -e DISPLAY=:99' \
  bash -c "source '${SCRIPT_DIR}/remote_common.sh'; rca_init_remote_vars '${ENV_NAME}' '${REMOTE_ROOT}' '${REMOTE_COMPOSE_ROOT}'; rca_remote_repo_exec 'bash ${PROBE_SCRIPT}'"

log "packaging remote artifacts"
ssh "${ENV_NAME}" "REMOTE_ROOT='${REMOTE_ROOT}' REMOTE_RESULTS='${REMOTE_RESULTS}' REMOTE_DIAGNOSTICS='${REMOTE_DIAGNOSTICS}' bash -s" <<'REMOTE_PACKAGE'
set -euo pipefail
REPO_DIR="${REMOTE_ROOT}/repo/robot-contact-assembly"
cd "${REPO_DIR}"
tar -czf "${REMOTE_RESULTS}" \
  artifacts/evaluations/scripted \
  artifacts/hydra \
  2>/tmp/rca-artifact-tar-warnings.log || {
    cat /tmp/rca-artifact-tar-warnings.log >&2 || true
    exit 1
  }
{
  date -u
  echo "## host nvidia-smi"
  nvidia-smi || true
  echo "## docker ps"
  sudo docker ps || true
  echo "## task container nvidia-smi"
  sudo docker exec -u root isaac-runner nvidia-smi || true
  echo "## disk"
  df -h || true
  echo "## artifact sizes"
  du -sh "${REPO_DIR}/artifacts" || true
  find "${REPO_DIR}/artifacts/evaluations/scripted" -maxdepth 2 -type f | sort | tail -80 || true
} > "${REMOTE_DIAGNOSTICS}"
REMOTE_PACKAGE

copy_if_present "${REMOTE_RESULTS}" "${LOCAL_LOG_DIR}"
copy_if_present "${REMOTE_DIAGNOSTICS}" "${LOCAL_LOG_DIR}"

log "paid guard probe completed"
